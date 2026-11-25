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
from .formats import MESSAGE_DWG, preparer
from .localisation import candidats_saisie, localiser
from .plans import extraire_plan
from .plans.textes import famille, meme_repere, normaliser_niveau, sans_accents
from .propositions import proposer
from .seuils import ZONES, seuils_energie, zone_normalisee
from .trace import val


@dataclass
class Parametres:
    zone: str | None = None            # sinon lue dans la notice
    altitude_m: float | None = None    # sinon lue dans la notice
    date_pc: str | None = None         # AAAA-MM-JJ (dépôt du permis) ; sinon lue dans la notice
    projet: str = "Projet sans nom"
    commune: str | None = None         # « 38420 », « Domène », « Grenoble (38) » : sert à déduire zone et altitude
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


def realiser_etude(fichiers, p: Parametres, catalogue: Catalogue | None = None,
                   catalogue_acv: CatalogueACV | None = None, dossier_travail=None) -> dict:
    """``fichiers`` : un ou plusieurs fichiers du dossier (PDF, DXF, DWG, Word, Excel, texte, images). Tout ce qui est
    lisible est lu ; les DXF/DWG sont redessinés en PDF vectoriel dans ``dossier_travail``."""
    liste = list(fichiers) if isinstance(fichiers, (list, tuple)) else [fichiers]
    prep = preparer(liste, dossier_travail)
    non_lus = [f"{nom} : {raison}" for nom, raison in prep["non_lus"]]
    if not prep["plans"]:
        raise ValueError("Aucun plan lisible dans le dossier (PDF vectoriel, DXF ou DWG attendu)"
                         + (" — " + " ; ".join(non_lus) if non_lus else ""))
    plan = extraire_plan(prep["plans"], hsp_m=p.hsp_m, denominateur=p.echelle, angle_nord_deg=p.angle_nord_deg)
    dossier = lire_dossier(prep["documents"])
    _hauteurs_des_coupes(plan, prep, p)
    if p.angle_nord_deg is None and plan["nord"]["valeur"] is None and dossier.get("baies_orientation"):
        nord = nord_par_baies(plan, dossier["baies_orientation"])
        if nord is not None:  # plan relu avec ce nord : façades et baies orientées
            plan = extraire_plan(prep["plans"], hsp_m=p.hsp_m, denominateur=p.echelle, angle_nord_deg=nord["valeur"])
            plan["nord"] = nord
            plan["alertes"] = [a for a in plan["alertes"] if "Nord non détecté" not in a] + [
                f"Nord déduit ({nord['valeur']:g}° depuis le haut de la feuille) en comparant les baies du plan aux surfaces "
                f"par orientation du dossier : {nord['source']}. À confirmer."]
    dossier["_diagnostic"] = diagnostic(prep, plan)
    e = etude_depuis_plan(plan, p, catalogue, catalogue_acv, dossier)
    e["fichiers"] = {"plans": [f.name for f in prep["plans"]], "documents": [f.name for f in prep["documents"]],
                     "non_lus": non_lus}
    dwg = [nom for nom, raison in prep["non_lus"] if raison == MESSAGE_DWG]
    autres = [f"{nom} : {raison}" for nom, raison in prep["non_lus"] if raison != MESSAGE_DWG]
    e["alertes"] = ([f"{len(dwg)} fichier(s) {MESSAGE_DWG} ({', '.join(dwg)})"] if dwg else []) \
        + [f"Fichier non lu : {x}" for x in autres] + e["alertes"]
    return e


def diagnostic(prep: dict, plan: dict) -> list[str]:
    """Ce que l'outil a pu lire dans chaque fichier (pour expliquer un échec)."""
    import pdfplumber

    out = []
    for f in prep["documents"]:
        if f.suffix.lower() != ".pdf":
            out.append(f"{f.name} : lu")
            continue
        try:
            with pdfplumber.open(f) as pdf:
                n_car = sum(len(p.chars) for p in pdf.pages)
                n_pages = len(pdf.pages)
                n_img = sum(len(p.images) for p in pdf.pages)
        except Exception:
            out.append(f"{f.name} : illisible")
            continue
        if n_car == 0:
            out.append(f"{f.name} : {n_pages} page(s), AUCUN texte lisible" + (" (images ou scan)" if n_img else " (textes vectorisés en traits ?)"))
        else:
            out.append(f"{f.name} : {n_pages} page(s), {n_car} caractères de texte")
    out += [f"{nom} : non lu ({raison})" for nom, raison in prep["non_lus"]]
    out.append("plans de niveau reconnus : " + (", ".join(plan.get("pages_plans", [])) or "aucun"))
    return out


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
            if not stock.get(cle):
                cle = (n["niveau"]["valeur"], b["orientation"], famille(b["nom"]))
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
            n_plan = sum(1 for n in plan["niveaux"] for b in n["baies"] if meme_repere(b["nom"], m["repere"]))
            out.append(_ligne(f"Nombre de {m['designation'].split(' ')[0].lower()}s ({m['repere']})", n_plan, m["quantite"]["valeur"], tol=0))
    return out


def _hauteurs_des_coupes(plan: dict, prep: dict, p: Parametres) -> None:
    """HSP et hauteur d'étage lues sur les cotes d'une coupe DXF/DWG, si le plan ne les donne pas."""
    from .formats import hauteurs_coupe
    from .plans.extraction import batiment
    from .trace import val as _val

    if p.hsp_m is not None or plan["batiment"]["hauteur_sous_plafond_m"]["tag"] != "supposé":
        return
    coupes = [(n, c) for n, c in prep.get("cotes_verticales", []) if re.search(r"coupe", n, re.I)] or prep.get("cotes_verticales", [])
    for nom, cotes in coupes:
        h = hauteurs_coupe(cotes)
        if not h:
            continue
        hsp = _val(h["hsp_m"], "lu", f"cote verticale la plus fréquente de « {nom} » ({len(cotes)} cotes)", "haute", "m")
        het = _val(h["hauteur_etage_m"], "déduit", f"HSP + plancher {h['plancher_m']:g} m coté sur « {nom} »", "haute", "m") \
            if h.get("hauteur_etage_m") else None
        plan["batiment"] = batiment(plan["niveaux"], hsp, het)
        plan["manquants"] = [m for m in plan.get("manquants", []) if not m.startswith("hauteurs")]
        return


def nord_par_baies(plan: dict, baies_orientation: dict) -> dict | None:
    """Plan sans symbole du nord : on teste les 4 orientations de la feuille et on garde celle dont les surfaces de baies
    par côté (haut / droite / bas / gauche) collent le mieux aux surfaces par orientation écrites dans le dossier (RSET)."""
    cote = {}
    for n in plan["niveaux"]:
        for b in n["baies"]:
            if b.get("cote_feuille"):
                cote[b["cote_feuille"]] = cote.get(b["cote_feuille"], 0) + b["surface_m2"]["valeur"]
    lu = {o: v["valeur"] for o, v in baies_orientation.items() if o in ("N", "E", "S", "O")}
    if len(cote) < 3 or sum(lu.values()) <= 0:
        return None
    tc, tl = sum(cote.values()), sum(lu.values())
    ordre = ["N", "E", "S", "O"]  # orientation du côté « haut » quand le nord est à 0°, puis sens horaire
    cotes = ["haut", "droite", "bas", "gauche"]
    scores = []
    for k, angle in enumerate((0, 90, 180, 270)):
        # nord à « angle » depuis le haut (sens horaire) : le côté haut regarde vers l'orientation ordre[-k]
        err = sum(abs(cote.get(c, 0) / tc - lu.get(ordre[(i - k) % 4], 0) / tl) for i, c in enumerate(cotes))
        scores.append((err, angle))
    scores.sort()
    (e1, a1), (e2, _) = scores[0], scores[1]
    if e1 > 0.6 or e2 - e1 < 0.15:
        return None
    return val(a1, "déduit", f"écart de répartition {e1:.2f} (suivant : {e2:.2f})", "moyenne", "°",
               explication="angle du nord par rapport au haut de la feuille, positif vers la droite")


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
    inf = dossier.get("infos", {})
    if choix["structure"] is None and inf.get("structure"):
        choix["structure"] = inf["structure"]["valeur"]
        sources["structure"] = val(choix["structure"], "lu", f"« {inf['structure'].get('note') or choix['structure']} » ({inf['structure']['source']})", "haute")
    if choix["menuiserie"] is None and inf.get("menuiseries") and inf["menuiseries"]["valeur"] in ("alu", "pvc", "bois"):
        choix["menuiserie"] = inf["menuiseries"]["valeur"]
        sources["menuiseries"] = val(choix["menuiserie"], "lu", f"« {inf['menuiseries'].get('note')} » ({inf['menuiseries']['source']})", "haute")
    return {"structure": choix["structure"] or "parpaing", "plancher": choix["plancher"] or "hourdis",
            "menuiserie": choix["menuiserie"] or "pvc"}, sources


def qualite_lecture(plan: dict, entrees, estimation: dict, dossier: dict) -> dict:
    """Le plan a-t-il été lu assez bien pour donner un verdict ? Sinon : raisons et documents à fournir."""
    graves, mineurs, conseils = [], [], []
    niv = plan["niveaux"]
    if not any(n["niveau"]["tag"] == "lu" for n in niv):
        mineurs.append("aucun titre de niveau (RDC, R+1…) trouvé sur le plan")
    if len(niv) > 4:
        graves.append(f"{len(niv)} vues détectées : le document contient sans doute un plan de masse, des façades ou des détails")
        conseils.append("déposer les plans de niveaux (RDC, étages) plutôt que le dossier de permis complet, ou un fichier par niveau")
    nb_baies = sum(len(n["baies"]) for n in niv)
    if nb_baies == 0:
        graves.append("aucune baie lue")
        conseils.append("plans avec étiquettes de baies (« F1 / 120 x 135 ») ou tableau des menuiseries dans la notice")
    sans_etiq = sum(1 for n in niv for b in n["baies"] if b["nom"] is None)
    if nb_baies and sans_etiq / nb_baies > 0.5:
        mineurs.append(f"{sans_etiq} baie(s) sur {nb_baies} sans étiquette : hauteurs supposées")
    ep = [n["murs_exterieurs"]["couche_pleine_m"]["valeur"] for n in niv]
    if any(x > 0.7 for x in ep):
        graves.append(f"épaisseur de mur lue aberrante ({max(ep):.2f} m) : murs mal reconnus")
        conseils.append("PDF vectoriel avec murs en aplat, ou DXF avec un calque de murs")
    if entrees.U["murs"] > 0.8:
        graves.append(f"U des murs déduit aberrant ({entrees.U['murs']:.2f} W/m².K)")
    if not dossier.get("parois"):
        mineurs.append("pas de notice thermique : parois, menuiseries et systèmes supposés")
        conseils.append("notice thermique (PDF, Word ou Excel) : Up des parois, Uw, ponts thermiques, systèmes")
    if plan["nord"]["valeur"] is None:
        mineurs.append("nord non lu : orientations inconnues")
        conseils.append("plan avec flèche du nord, ou saisir l'angle du nord dans les options avancées")
    if plan["echelle"]["denominateur"]["confiance"] != "haute":
        mineurs.append("échelle non vérifiée par une cote écrite")
    bbio = estimation["Bbio"]["valeur"]
    if not 20 <= bbio <= 200:
        graves.append(f"Bbio estimé hors plage plausible ({bbio:.0f})")
    if not 20 <= entrees.sref <= 5000:
        graves.append(f"Sref hors plage plausible ({entrees.sref:.0f} m²)")
    niveau = "insuffisante" if graves else ("moyenne" if mineurs else "bonne")
    return {"niveau": niveau, "graves": graves, "mineurs": mineurs, "conseils": list(dict.fromkeys(conseils))}


def etude_depuis_plan(plan: dict, p: Parametres, catalogue: Catalogue | None = None,
                      catalogue_acv: CatalogueACV | None = None, dossier: dict | None = None) -> dict:
    cat = catalogue or Catalogue()
    dossier = dossier or {}
    inf = dict(dossier.get("infos", {}))
    alertes_lieu = []
    if inf.get("zone") and inf["zone"]["valeur"] not in ZONES:  # zone incomplète (« H1 ») : on la déduit du lieu
        alertes_lieu.append(f"Zone climatique lue incomplète (« {inf['zone']['valeur']} ») : déduite du lieu du projet.")
        inf.pop("zone")
    if p.zone not in (None, ""):
        try:
            zone_normalisee(p.zone)
        except ValueError:
            alertes_lieu.append(f"Zone saisie « {p.zone} » incomplète : déduite du lieu du projet.")
            p.zone = None
    lieu = {}
    if p.commune:
        saisie = candidats_saisie(p.commune)
        if not saisie:
            raise ValueError(f"Commune « {p.commune} » non reconnue : taper le code postal (ex. 38420) ou choisir la zone climatique.")
        lieu = localiser(saisie)
    elif (p.zone in (None, "") and not inf.get("zone")) or (p.altitude_m is None and not inf.get("altitude_m")):
        lieu = localiser(dossier.get("localisation_candidats", []))
        if lieu.get("note"):
            alertes_lieu.append("Localisation : " + lieu["note"])
    if p.zone in (None, "") and not (inf.get("zone") or lieu.get("zone")):
        lus = dossier.get("_diagnostic", [])
        raise ValueError("ZONE_A_SAISIR : le lieu du chantier n'a pas été trouvé dans le dossier (ni zone climatique, ni code "
                         "postal, ni département). Taper la commune ou le code postal du chantier, ou choisir la zone."
                         + (" Ce que l'outil a pu lire : " + " ; ".join(lus) if lus else ""))
    zone_v, zone_t = _param("zone", p.zone, inf.get("zone") or lieu.get("zone"), "Zone climatique")
    alt_lu = inf.get("altitude_m") or lieu.get("altitude_m")
    if p.altitude_m is None and not alt_lu:
        alt_lu = val(100.0, "supposé", "altitude introuvable (hors ligne ou commune inconnue) : classe < 400 m supposée", "faible", "m")
        alertes_lieu.append("Altitude non trouvée : terrain supposé sous 400 m. La saisir si le projet est plus haut "
                            "(les seuils changent à 400 m et 800 m).")
    alt_v, alt_t = _param("altitude", p.altitude_m, alt_lu, "Altitude")
    dpc_lu = inf.get("date_pc")
    if p.date_pc in (None, "") and not dpc_lu:
        dates = sorted(dossier.get("dates", []))
        if dates:
            d_plan, src_d = dates[-1]
            dpc_lu = val(d_plan, "supposé", f"date de dépôt du PC introuvable : date la plus récente des plans ({src_d}) supposée", "faible")
            alertes_lieu.append(f"Date de dépôt du PC non trouvée : date des plans ({d_plan}) supposée (elle fixe les seuils : la saisir).")
        else:
            dpc_lu = val(date.today().isoformat(), "supposé", "date de dépôt du PC introuvable : date du jour supposée", "faible")
            alertes_lieu.append("Date de dépôt du PC non trouvée : date du jour supposée (elle fixe les seuils : la saisir).")
    dpc_v, dpc_t = _param("date_pc", p.date_pc, dpc_lu, "Date de dépôt du permis")
    zone = zone_normalisee(zone_v)
    controles = controles_croises(plan, dossier) if dossier else []
    if dossier:
        _alleges(plan, dossier, controles)
    entrees, hyp = entrees_depuis_plan(plan, zone, float(alt_v), sref=p.sref, catalogue=cat, dossier=dossier,
                                       systeme=p.systeme, retour_isolant_menuiseries=p.retour_isolant_menuiseries)
    entrees.nb_logements = p.nb_logements
    sref = entrees.sref
    seuils = seuils_energie(zone, float(alt_v), sref / p.nb_logements, dpc_v, mb_hsp=p.mb_hsp, mc_hsp=p.mc_hsp)
    rp = (dossier or {}).get("resultats_pleiades") or {}
    if all(rp.get(k) for k in ("Bbio_max", "Cep_max", "Cep_nr_max")) and p.mb_hsp is None:
        # seuils calculés par Pléiades pour CE projet (RSET) : exacts, modulations HSP comprises
        for k in ("Bbio_max", "Cep_max", "Cep_nr_max"):
            seuils[k] = {**rp[k], "note": f"seuil calculé par Pléiades (outil : {seuils[k]['valeur']:g} approx)"}
        seuils["approx"] = False
    estimation = estimer(entrees, "plan + dossier" if dossier.get("pages_lues") else "plan + hypothèses")
    choix_acv, src_acv = choix_constructifs(dossier, p)
    modes = {n["murs_exterieurs"]["isolation"]["valeur"][:3] for n in plan["niveaux"]}
    iso_mode = next(iter(modes)) if len(modes) == 1 and next(iter(modes)) in ("ITE", "ITI") else None
    structure_connue = p.structure or (choix_acv["structure"] if "structure" in src_acv else None)
    props = proposer(entrees, seuils, cat, isolation=iso_mode, structure=structure_connue)
    acv = estimer_acv(plan, entrees, estimation, dpc_v, zone, float(alt_v), entrees.systeme["nom"], p.nb_logements,
                      choix_acv["structure"], choix_acv["plancher"], choix_acv["menuiserie"], catalogue_acv, dossier, src_acv)

    tertiaire = inf.get("residentiel", {}).get("valeur") is False
    qualite = qualite_lecture(plan, entrees, estimation, dossier)
    alertes = alertes_lieu + list(plan["alertes"]) + list(hyp.get("alertes", []))
    if hyp.get("baies_par_orientation", {}).get("tag") == "lu":
        alertes = [("Baies : surfaces par orientation lues dans le dossier et utilisées pour l'estimation "
                    f"({hyp['baies_par_orientation']['note']}) ; les hauteurs supposées du plan ne servent qu'au repérage."
                    if "baies sans étiquette" in a else a) for a in alertes]
    if qualite["niveau"] == "insuffisante":
        alertes.insert(0, "LECTURE DU PLAN INSUFFISANTE : " + " ; ".join(qualite["graves"])
                       + (". À fournir : " + " ; ".join(qualite["conseils"]) if qualite["conseils"] else ""))
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
        verdict[k] = ("lecture insuffisante" if qualite["niveau"] == "insuffisante" else
                      "hors périmètre (tertiaire)" if tertiaire else
                      "conforme probable" if h <= smax else "non conforme probable" if b > smax else "incertain")
    if qualite["niveau"] == "insuffisante":
        acv["verdict"] = {k: "lecture insuffisante" for k in acv["verdict"]}
    elif tertiaire:
        acv["verdict"] = {k: "hors périmètre (tertiaire)" for k in acv["verdict"]}

    # données encore manquantes : on retire ce que le dossier a fourni
    infd = dossier.get("infos", {})
    trouve = {"hauteurs": bool(dossier.get("hauteurs")), "compositions": bool(dossier.get("parois")),
              "menuiseries": bool(dossier.get("menuiseries") or dossier.get("vitrages")),
              "systèmes": bool(dossier.get("chauffage")), "type de toiture": bool(infd.get("type_toiture")),
              "nature": bool(dossier.get("ponts_thermiques", {}).get("liaisons"))}
    manquants = [m for m in plan["manquants"] if not any(m.startswith(k) and v for k, v in trouve.items())]

    params = asdict(p) | {"zone": zone, "altitude_m": float(alt_v), "date_pc": dpc_v}
    return {
        "projet": p.projet,
        "date_rapport": date.today().isoformat(),
        "parametres": params,
        "parametres_sources": {"zone": zone_t, "altitude_m": alt_t, "date_pc": dpc_t, **({"lieu": lieu["lieu"]} if lieu.get("lieu") else {})},
        "usage": inf.get("usage"),
        "tertiaire": tertiaire,
        "qualite": qualite,
        "plan": plan,
        "resultats_pleiades": (dossier or {}).get("resultats_pleiades") or {},
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
