"""Chaîne complète d'une étude : dossier PDF (plans + notice…) → plan lu → données écrites lues → hypothèses →
seuils → estimation → propositions → ACV (→ rapport). Les contrôles croisés plan / notice sont produits."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

from .acv import CatalogueACV, estimer_acv
from .catalogues import Catalogue
from .documents import lire_dossier
from .estimation import entrees_depuis_plan, estimer
from .plans import extraire_plan
from .plans.textes import normaliser_niveau, sans_accents
from .propositions import proposer
from .seuils import seuils_energie, zone_normalisee
from .trace import val


@dataclass
class Parametres:
    zone: str | None = None            # sinon lue dans la notice
    altitude_m: float | None = None    # sinon lue dans la notice
    date_pc: str | None = None         # AAAA-MM-JJ (dépôt du permis) ; sinon lue dans la notice
    projet: str = "Projet sans nom"
    sref: float | None = None          # sinon lue dans la notice, sinon surface intérieure du plan
    nb_logements: int = 1
    hsp_m: float | None = None         # sinon lue sur la coupe, sinon 2,50 supposé
    systeme: str | None = None         # sinon lu dans la notice, sinon PAC supposée
    mb_hsp: float | None = None        # modulations HSP si connues (Pléiades)
    mc_hsp: float | None = None
    retour_isolant_menuiseries: bool | None = None
    echelle: int | None = None
    angle_nord_deg: float | None = None
    structure: str | None = None       # ACV : parpaing | brique | beton | ossature_bois (sinon lu dans la notice)
    plancher: str | None = None        # ACV : hourdis | bois
    menuiserie: str | None = None      # ACV : pvc | alu


def realiser_etude(pdfs, p: Parametres, catalogue: Catalogue | None = None,
                   catalogue_acv: CatalogueACV | None = None) -> dict:
    """``pdfs`` : un PDF ou une liste (plans, coupe, notice thermique…). Tout est lu."""
    liste = list(pdfs) if isinstance(pdfs, (list, tuple)) else [pdfs]
    plan = extraire_plan(liste, hsp_m=p.hsp_m, denominateur=p.echelle, angle_nord_deg=p.angle_nord_deg)
    dossier = lire_dossier(liste)
    return etude_depuis_plan(plan, p, catalogue, catalogue_acv, dossier)


def _param(nom: str, fourni, lu: dict | None, libelle: str):
    if fourni not in (None, ""):
        return fourni, val(fourni, "lu", "saisi par le thermicien", "haute")
    if lu:
        return lu["valeur"], lu
    raise ValueError(f"{libelle} introuvable dans le dossier : la saisir dans le formulaire.")


ORIENT = {"sud": "S", "nord": "N", "est": "E", "ouest": "O", "sud-est": "SE", "sud-ouest": "SO", "nord-est": "NE", "nord-ouest": "NO"}


def _alleges(plan: dict, dossier: dict, controles: list) -> None:
    """Rattache aux baies du plan les allèges du tableau de baies (même niveau, orientation, repère)."""
    stock: dict[tuple, list] = {}
    for b in dossier.get("baies", []):
        o = ORIENT.get(sans_accents(b["facade"]).strip())
        if o is None:
            continue
        stock.setdefault((normaliser_niveau(b["niveau"]), o, b["repere"].upper()), []).append(b)
    n_plan = n_ok = 0
    for n in plan["niveaux"]:
        for b in n["baies"]:
            n_plan += 1
            cle = (n["niveau"]["valeur"], b["orientation"], (b["nom"] or "").upper())
            if stock.get(cle):
                ligne = stock[cle].pop(0)
                n_ok += 1
                if ligne.get("allege_m") and "allege_m" not in b:
                    b["allege_m"] = ligne["allege_m"]
    n_doc = sum(1 for b in dossier.get("baies", []) if ORIENT.get(sans_accents(b["facade"]).strip()))
    if n_doc:
        controles.append(_ligne("Baies : nombre (plan / tableau de baies)", n_plan, n_doc, tol=0))
        if n_ok < max(n_plan, n_doc):
            restes = [f"{k[0]} {k[1]} {k[2]}" for k, v in stock.items() for _ in v]
            controles[-1]["detail"] = f"{n_ok} baies appariées" + (f" ; non trouvées sur le plan : {', '.join(restes)}" if restes else "")


def _ligne(grandeur: str, plan_v, doc_v, tol: float = 0.02, unite: str = "") -> dict:
    if plan_v is None or doc_v is None:
        return {"grandeur": grandeur, "plan": plan_v, "dossier": doc_v, "unite": unite, "ecart_pct": None, "statut": "absent"}
    ecart = (plan_v - doc_v) / doc_v * 100 if doc_v else 0.0
    ok = abs(plan_v - doc_v) <= max(tol * abs(doc_v), 0.051 if tol else 0)
    return {"grandeur": grandeur, "plan": round(plan_v, 2), "dossier": round(doc_v, 2), "unite": unite,
            "ecart_pct": round(ecart, 1), "statut": "ok" if ok else "écart"}


def controles_croises(plan: dict, dossier: dict) -> list[dict]:
    """Compare ce que l'outil mesure sur le plan à ce que le dossier écrit."""
    bat, S = plan["batiment"], dossier.get("surfaces", {})
    out = []
    v = lambda d, k: d[k]["valeur"] if d.get(k) else None
    if S.get("surface_par_niveau"):
        for n in plan["niveaux"]:
            out.append(_ligne(f"Surface intérieure {n['niveau']['valeur']}", n["surface_interieure_m2"]["valeur"], v(S, "surface_par_niveau"), unite="m²"))
    if S.get("sref"):
        out.append(_ligne("Sref (surface intérieure totale)", bat["surface_interieure_totale_m2"]["valeur"], v(S, "sref"), unite="m²"))
    bilan = {sans_accents(l["facade"]): l for l in dossier.get("bilan_facades", [])}
    for nom, o in (("sud", "S"), ("nord", "N"), ("est", "E"), ("ouest", "O")):
        if nom in bilan and bilan[nom].get("baies_m2"):
            out.append(_ligne(f"Baies façade {nom.capitalize()}", bat["baies_par_orientation_m2"].get(o, 0.0), bilan[nom]["baies_m2"]["valeur"], unite="m²"))
    if "total" in bilan and bilan["total"].get("baies_m2"):
        out.append(_ligne("Baies : surface totale", bat["baies_total_m2"], bilan["total"]["baies_m2"]["valeur"], unite="m²"))
    murs = bat["murs_par_orientation_m2"].values()
    if S.get("murs_bruts"):
        out.append(_ligne("Murs bruts", sum(m["brut_m2"] for m in murs), v(S, "murs_bruts"), unite="m²"))
    if S.get("murs_nets"):
        out.append(_ligne("Murs nets des baies", sum(m["net_m2"] for m in murs), v(S, "murs_nets"), unite="m²"))
    pt = bat["ponts_thermiques"]
    for mot, cle in (("plancher bas", "plancher_bas_mur_ml"), ("intermediaire", "plancher_intermediaire_mur_ml"),
                     ("toiture|acrotere|plancher haut", "plancher_haut_mur_ml"), ("angle", "angle_saillant_ml")):
        l = next((l for l in dossier.get("ponts_thermiques", {}).get("liaisons", [])
                  if re.search(mot, sans_accents(l["liaison"])) and l.get("longueur_m")), None)
        if l:
            out.append(_ligne(f"Linéaire {l['liaison']}", pt[cle]["valeur"], l["longueur_m"]["valeur"], unite="m"))
    for m in dossier.get("menuiseries", []):
        if m.get("quantite") and not m.get("toiture"):
            n_plan = sum(1 for n in plan["niveaux"] for b in n["baies"] if (b["nom"] or "").upper() == m["repere"].upper())
            out.append(_ligne(f"Nombre de {m['designation'].split(' ')[0].lower()}s ({m['repere']})", n_plan, m["quantite"]["valeur"], tol=0))
    return out


def choix_constructifs(dossier: dict, p: Parametres) -> tuple[dict, dict]:
    """Structure des murs, plancher intermédiaire, matériau des menuiseries : saisis, sinon lus dans la notice."""
    choix = {"structure": p.structure, "plancher": p.plancher, "menuiserie": p.menuiserie}
    sources = {}
    for par in dossier.get("parois", []):
        t = sans_accents(par["designation"] + " " + par.get("composition", ""))
        src = (par.get("Up") or {}).get("source") or "notice"
        if par["type_paroi"] == "mur_ext" and choix["structure"] is None:
            for mot, v in (("ossature bois", "ossature_bois"), ("brique", "brique"), ("beton banche", "beton"), ("voile", "beton"),
                           ("parpaing", "parpaing"), ("bloc", "parpaing")):
                if mot in t:
                    choix["structure"] = v
                    sources["structure"] = val(v, "lu", f"{par['ref']} {par['designation']} ({src})", "haute")
                    break
        if par["type_paroi"] == "plancher_interm" and choix["plancher"] is None:
            v = "bois" if "bois" in t else "hourdis"
            choix["plancher"] = v
            sources["plancher"] = val(v, "lu" if v == "bois" else "déduit", f"{par['ref']} {par['designation']} : {par.get('composition', '')[:60]}", "moyenne")
    if choix["menuiserie"] is None and dossier.get("menuiseries"):
        brut = sans_accents(" ".join(m.get("texte", "") for m in dossier["menuiseries"] if not m.get("opaque")))
        v = "alu" if "alumin" in brut else "pvc" if "pvc" in brut else None
        if v:
            choix["menuiserie"] = v
            sources["menuiseries"] = val(v, "lu", "tableau des menuiseries de la notice", "haute")
    return {"structure": choix["structure"] or "parpaing", "plancher": choix["plancher"] or "hourdis",
            "menuiserie": choix["menuiserie"] or "pvc"}, sources


def etude_depuis_plan(plan: dict, p: Parametres, catalogue: Catalogue | None = None,
                      catalogue_acv: CatalogueACV | None = None, dossier: dict | None = None) -> dict:
    cat = catalogue or Catalogue()
    dossier = dossier or {}
    inf = dossier.get("infos", {})
    zone_v, zone_t = _param("zone", p.zone, inf.get("zone"), "Zone climatique")
    alt_v, alt_t = _param("altitude", p.altitude_m, inf.get("altitude_m"), "Altitude")
    dpc_v, dpc_t = _param("date_pc", p.date_pc, inf.get("date_pc"), "Date de dépôt du permis")
    zone = zone_normalisee(zone_v)
    controles = controles_croises(plan, dossier) if dossier else []
    if dossier:
        _alleges(plan, dossier, controles)
    entrees, hyp = entrees_depuis_plan(plan, zone, float(alt_v), sref=p.sref, catalogue=cat, dossier=dossier,
                                       systeme=p.systeme, retour_isolant_menuiseries=p.retour_isolant_menuiseries)
    entrees.nb_logements = p.nb_logements
    sref = entrees.sref
    seuils = seuils_energie(zone, float(alt_v), sref / p.nb_logements, dpc_v, mb_hsp=p.mb_hsp, mc_hsp=p.mc_hsp)
    estimation = estimer(entrees, "plan + dossier" if dossier.get("pages_lues") else "plan + hypothèses")
    props = proposer(entrees, seuils, cat)
    choix_acv, src_acv = choix_constructifs(dossier, p)
    acv = estimer_acv(plan, entrees, estimation, dpc_v, zone, float(alt_v), entrees.systeme["nom"], p.nb_logements,
                      choix_acv["structure"], choix_acv["plancher"], choix_acv["menuiserie"], catalogue_acv, dossier, src_acv)

    tertiaire = inf.get("residentiel", {}).get("valeur") is False
    alertes = list(plan["alertes"]) + list(hyp.get("alertes", []))
    if seuils["approx"]:
        alertes.append("Seuils « approx » : MbHSP/McHSP (décret 2026-200) inconnus pour ce PC → les lire dans Pléiades "
                       "et les fournir pour un seuil exact.")
    alertes += acv["alertes"]
    if acv["Ic_energie"].get("partiel"):
        alertes.append("Ic énergie partiel : le contenu CO2 du réseau de chaleur est à prendre dans la bibliothèque Pléiades.")
    alertes.append("Certification des isolants à vérifier (ACERMI) : si non certifié, majorer λ de 15 % dans Pléiades "
                   "(non automatique).")
    ecarts = [c for c in controles if c["statut"] == "écart"]
    if ecarts:
        alertes.append("Écarts entre le plan et le dossier : " + " ; ".join(c["grandeur"] for c in ecarts) + " (voir contrôles croisés).")
    verdict = {}
    for k, kmax in (("Bbio", "Bbio_max"), ("Cep", "Cep_max"), ("Cep_nr", "Cep_nr_max")):
        est, smax = estimation[k], seuils[kmax]["valeur"]
        b, h = est["fourchette"]
        verdict[k] = ("hors périmètre (tertiaire)" if tertiaire else
                      "conforme probable" if h <= smax else "non conforme probable" if b > smax else "incertain")
    if tertiaire:
        acv["verdict"] = {k: "hors périmètre (tertiaire)" for k in acv["verdict"]}

    # données encore manquantes : on retire ce que le dossier a fourni
    trouve = {"hauteurs": bool(dossier.get("hauteurs")), "compositions": bool(dossier.get("parois")),
              "menuiseries": bool(dossier.get("menuiseries")), "systèmes": bool(dossier.get("chauffage"))}
    manquants = [m for m in plan["manquants"]
                 if not ((m.startswith("hauteurs") and trouve["hauteurs"]) or (m.startswith("compositions") and trouve["compositions"])
                         or (m.startswith("menuiseries") and trouve["menuiseries"]) or (m.startswith("systèmes") and trouve["systèmes"]))]

    params = asdict(p) | {"zone": zone, "altitude_m": float(alt_v), "date_pc": dpc_v}
    return {
        "projet": p.projet,
        "date_rapport": date.today().isoformat(),
        "parametres": params,
        "parametres_sources": {"zone": zone_t, "altitude_m": alt_t, "date_pc": dpc_t},
        "usage": inf.get("usage"),
        "tertiaire": tertiaire,
        "plan": plan,
        "dossier": dossier,
        "controles": controles,
        "hypotheses": hyp,
        "entrees": {"sref": sref, "surfaces_m2": {k: round(v, 1) for k, v in entrees.surfaces.items()},
                    "U": {k: round(v, 3) for k, v in entrees.U.items()}, "Sw": round(entrees.Sw, 3),
                    "ponts_W_K": round(entrees.ponts_W_K, 2), "baies_m2": entrees.baies,
                    "qv_equivalent_m3h": round(entrees.qv_m3h, 1) if entrees.qv_m3h is not None else None},
        "seuils": seuils,
        "estimation": estimation,
        "verdict": verdict,
        "propositions": props,
        "acv": acv,
        "alertes": alertes,
        "manquants": manquants,
        "_trace_sref": val(sref, hyp["Sref"]["tag"], hyp["Sref"]["source"], hyp["Sref"]["confiance"], "m²"),
    }
