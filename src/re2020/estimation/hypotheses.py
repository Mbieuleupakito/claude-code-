"""Construit les entrées du modèle à partir du JSON d'un plan + hypothèses tracées (supposé / catalogue)."""
from __future__ import annotations

from ..catalogues import Catalogue
from ..catalogues.parois import u_paroi
from ..trace import val
from .modele import Entrees

# Hypothèses par défaut quand le plan ne dit rien (toutes « supposé »)
DEFAUTS = {
    "lambda_isolant": 0.032,     # W/m.K, isolant courant certifié
    "R_structure": 0.20,         # m².K/W, maçonnerie courante 20 cm
    "U_toiture": 0.12,
    "U_plancher_bas": 0.15,
    "Uw": 1.30,
    "Sw": 0.42,
    "q4": 0.6,
    "systeme": "PAC air/eau double service",
    "retour_isolant_menuiseries": True,   # bonne pratique ITE ; sans retour, le ratio Ψ dépasse souvent 0,33
}


def u_mur_depuis_plan(niveau: dict, h: dict) -> tuple[float, str]:
    m = niveau["murs_exterieurs"]
    ext = m["bande_hachuree_ext_m"]["valeur"]
    intr = m["bande_hachuree_int_m"]["valeur"]
    iso = {"nom": "isolant supposé", "lambda_W_mK": h["lambda_isolant"], "certifie": True}
    couches = [(100 * m["couche_pleine_m"]["valeur"], {"nom": "structure", "R_m2K_W": h["R_structure"]})]
    if ext >= 0.03:
        couches.append((100 * ext, iso))
    if intr >= 0.03:  # doublage : plaque de plâtre 1,3 cm + isolant
        couches += [(100 * intr - 1.3, iso), (1.3, {"nom": "plâtre", "lambda_W_mK": 0.25})]
    u = u_paroi("mur_ext", couches)["U"]
    return u, f"bandes hachurées du plan (ext. {ext:.2f} m, int. {intr:.2f} m) x λ {h['lambda_isolant']} supposé"


def entrees_depuis_plan(plan: dict, zone: str, altitude_m: float, sref: float | None = None,
                        catalogue: Catalogue | None = None, dossier: dict | None = None, **choix) -> tuple[Entrees, dict]:
    """Retourne (Entrees, hypothèses tracées utilisées). ``dossier`` : sortie de lire_dossier() (notice…)."""
    cat = catalogue or Catalogue()
    h = {**DEFAUTS, **{k: v for k, v in choix.items() if v is not None}}
    bat, niv = plan["batiment"], plan["niveaux"]
    iso_mode = "ITE" if any("ITE" in n["murs_exterieurs"]["isolation"]["valeur"] for n in niv) else "ITI"
    hyp = {}

    sref_lu = (dossier or {}).get("surfaces", {}).get("sref")
    if sref is None and sref_lu:
        sref = sref_lu["valeur"]
        hyp["Sref"] = sref_lu
    elif sref is None:
        sref = bat["surface_interieure_totale_m2"]["valeur"]
        hyp["Sref"] = val(sref, "déduit", "surface intérieure totale du plan (≈ Sref)", "moyenne", "m²")
    else:
        hyp["Sref"] = val(sref, "lu", "fourni par le thermicien", "haute", "m²")

    if "U_murs" in choix and choix["U_murs"] is not None:
        u_mur = choix["U_murs"]
        hyp["U_murs"] = val(u_mur, "lu", "fourni par le thermicien / composition choisie", "haute", "W/m².K")
    else:
        us = [u_mur_depuis_plan(n, h) for n in niv]
        u_mur = sum(u for u, _ in us) / len(us)
        hyp["U_murs"] = val(round(u_mur, 3), "supposé", us[0][1], "faible", "W/m².K")
    for cle_u, nom in (("U_toiture", "toiture"), ("U_plancher_bas", "plancher bas"), ("Uw", "baies (Uw)")):
        tag = "lu" if cle_u in choix and choix[cle_u] is not None else "supposé"
        hyp[cle_u] = val(h[cle_u], tag, "fourni" if tag == "lu" else f"valeur courante RE2020 pour {nom}", "haute" if tag == "lu" else "faible", "W/m².K")
    hyp["Sw"] = val(h["Sw"], "supposé" if "Sw" not in choix else "lu", "facteur solaire menuiserie courante", "faible")

    murs = sum(v["net_m2"] for v in bat["murs_par_orientation_m2"].values())
    surfaces = {"murs": murs, "toiture": bat["plancher_haut_m2"]["valeur"], "plancher_bas": bat["plancher_bas_m2"]["valeur"]}
    baies = dict(bat["baies_par_orientation_m2"])

    pt = bat["ponts_thermiques"]
    liaisons = {"plancher_bas_mur_ml": "plancher_bas_mur", "plancher_intermediaire_mur_ml": "plancher_intermediaire_mur",
                "plancher_haut_mur_ml": "plancher_haut_mur", "refend_mur_ml": "refend_mur", "angle_saillant_ml": "angle_saillant",
                "angle_rentrant_ml": "angle_rentrant"}
    detail_pt, total = [], 0.0
    for k, liaison in liaisons.items():
        psi = cat.psi_defaut(liaison, iso_mode)
        L = pt[k]["valeur"]
        total += psi["valeur"] * L
        detail_pt.append({"liaison": pt[k]["liaison"], "longueur_m": L, "psi": psi})
    L_men = pt["menuiserie_appui_ml"]["valeur"] + pt["menuiserie_linteau_ml"]["valeur"] + pt["menuiserie_tableaux_ml"]["valeur"]
    psi_men = cat.psi_defaut("menuiserie", iso_mode, h["retour_isolant_menuiseries"])
    total += psi_men["valeur"] * L_men
    detail_pt.append({"liaison": "menuiseries / mur (appui + linteau + tableaux)", "longueur_m": round(L_men, 1), "psi": psi_men})
    hyp["ponts_thermiques"] = detail_pt
    hyp["menuiseries_retour_isolant"] = val(h["retour_isolant_menuiseries"], "lu" if "retour_isolant_menuiseries" in choix else "supposé",
                                            "choix du thermicien" if "retour_isolant_menuiseries" in choix else "bonne pratique ITE", "faible")
    hyp["ratio_psi"] = val(round(total / sref, 3), "déduit", "Σ ψ·L / Sref", "moyenne", "W/(m².K)",
                           note="exigence art. 22.II : <= 0,33")
    hyp["alertes"] = []
    if total / sref > 0.33:
        hyp["alertes"].append(f"Ratio Ψ estimé {total / sref:.2f} > 0,33 (art. 22.II) : traiter les ponts thermiques "
                              "(retour d'isolant en tableau, rupteurs) ou justifier par l'art. 22.I.")

    systeme = next((s for s in cat.systemes() if s["nom"] == h["systeme"]), cat.systemes()[0])
    hyp["systeme"] = val(systeme["nom"], "lu" if "systeme" in choix else "supposé", "choix du thermicien" if "systeme" in choix else "système courant en maison individuelle", "moyenne" if "systeme" in choix else "faible")
    hyp["q4"] = val(h["q4"], "supposé", "perméabilité visée (exigence MI : 0,6)", "moyenne", "m³/(h.m²)")

    e = Entrees(sref=sref, zone=zone, altitude_m=altitude_m, surfaces=surfaces,
                U={"murs": u_mur, "toiture": h["U_toiture"], "plancher_bas": h["U_plancher_bas"], "baies": h["Uw"]},
                baies=baies, Sw=h["Sw"], ponts_W_K=total, q4=h["q4"], systeme=systeme)
    if dossier:
        appliquer_dossier(e, hyp, plan, dossier, choix, cat)
    return e, hyp


FRACTION_VITREE = 0.70   # part vitrée d'une menuiserie (Sw ≈ g x fraction vitrée), supposée
RENDEMENTS_GENERATEUR = {  # rendement global génération + distribution + émission, supposé faute de donnée lue
    "réseau de chaleur urbain": ("reseau_chaleur", 0.85),
    "chaudière": ("gaz", 0.88),
    "effet Joule": ("electricite", 0.95),
}
RENDEMENTS_ECS = {"ballon électrique (effet Joule)": 0.85, "chauffe-eau thermodynamique": 2.4, "PAC double service": 2.6,
                  "chauffe-eau solaire": 2.0}


def appliquer_dossier(e: Entrees, hyp: dict, plan: dict, dossier: dict, choix: dict, cat: Catalogue) -> None:
    """Remplace les hypothèses par les valeurs lues dans le dossier (notice, tableaux), sauf choix explicite."""
    alertes = hyp.setdefault("alertes", [])
    # ---- parois : Up de la notice
    for p in dossier.get("parois", []):
        if not p.get("Up"):
            continue
        cle = {"mur_ext": ("U_murs", "murs"), "plafond": ("U_toiture", "toiture"), "plancher_bas": ("U_plancher_bas", "plancher_bas")}.get(p["type_paroi"])
        if cle and choix.get(cle[0]) is None:
            e.U[cle[1]] = p["Up"]["valeur"]
            hyp[cle[0]] = {**p["Up"], "note": f"{p['ref']} {p['designation']} (Up global de la notice)"}
    # ---- menuiseries : Uw et Sw pondérés par les surfaces de baies du plan, lanterneau ajouté à la toiture
    men = {m["repere"].upper(): m for m in dossier.get("menuiseries", [])}
    if men:
        a_tot = su = ssw = 0.0
        for n in plan["niveaux"]:
            for b in n["baies"]:
                m = men.get((b["nom"] or "").upper())
                a = b["surface_m2"]["valeur"]
                if not m or not m.get("U"):
                    continue
                a_tot += a
                su += a * m["U"]["valeur"]
                ssw += 0 if m.get("opaque") else a * (m["g"]["valeur"] if m.get("g") else 0.5) * FRACTION_VITREE
        if a_tot and choix.get("Uw") is None:
            e.U["baies"] = su / a_tot
            hyp["Uw"] = val(round(su / a_tot, 3), "déduit", "Uw / Ud de la notice pondérés par les surfaces de baies du plan", "haute", "W/m².K")
        if a_tot and choix.get("Sw") is None:
            e.Sw = ssw / a_tot
            hyp["Sw"] = val(round(ssw / a_tot, 3), "déduit", f"g de la notice x fraction vitrée {FRACTION_VITREE} supposée (portes pleines : 0)", "moyenne")
        for m in men.values():
            if m.get("toiture") and m.get("U") and m.get("surface_m2") and e.surfaces["toiture"] > 0:
                at, al = e.surfaces["toiture"], m["surface_m2"]["valeur"]
                e.U["toiture"] = (e.U["toiture"] * (at - al) + m["U"]["valeur"] * al) / at
                hyp["U_toiture"] = val(round(e.U["toiture"], 3), "déduit", f"Up toiture + {m['designation']} (U {m['U']['valeur']})", "haute", "W/m².K")
    # ---- ponts thermiques : tableau de la notice
    P = dossier.get("ponts_thermiques", {})
    if P.get("liaisons") and P.get("total_W_K"):
        e.ponts_W_K = P["total_W_K"]["valeur"]
        hyp["ponts_thermiques"] = [{"liaison": l["liaison"], "longueur_m": l["longueur_m"]["valeur"] if l.get("longueur_m") else 0,
                                    "psi": l["psi"]} for l in P["liaisons"]]
        hyp["ratio_psi"] = val(round(e.ponts_W_K / e.sref, 3), "déduit", "Σ Ψ·L de la notice / Sref", "haute", "W/(m².K)",
                               note="exigence art. 22.II : <= 0,33")
        alertes[:] = [a for a in alertes if not a.startswith("Ratio Ψ estimé")]
    # ---- perméabilité
    q4 = dossier.get("infos", {}).get("q4")
    if q4 and q4.get("valeur") and choix.get("q4") is None:
        e.q4 = q4["valeur"]
        hyp["q4"] = q4
    # ---- ventilation : double flux → débit utile = débit x (1 - rendement) x fraction de fonctionnement
    V = dossier.get("ventilation", {})
    if V.get("type", {}).get("valeur") == "double flux" and V.get("debit_m3h"):
        eta = V["rendement"]["valeur"] if V.get("rendement") else 0.75
        frac = V["fraction_fonctionnement"]["valeur"] if V.get("fraction_fonctionnement") else 1.0
        e.qv_m3h = V["debit_m3h"]["valeur"] * (1 - eta) * frac
        hyp["ventilation"] = val(f"double flux {V['debit_m3h']['valeur']:g} m³/h, rendement {eta:.0%}"
                                 + (f", {V['horaires']['valeur']}" if V.get("horaires") else ""), "lu", V["type"]["source"], "haute",
                                 debit_equivalent_m3h=round(e.qv_m3h, 1))
    elif V.get("type"):
        hyp["ventilation"] = V["type"]
    # ---- systèmes
    C, E = dossier.get("chauffage", {}), dossier.get("ecs", {})
    gen = C.get("generateur", {}).get("valeur")
    if gen and choix.get("systeme") is None:
        if gen == "pompe à chaleur":
            sys_ = next(s for s in cat.systemes() if s["nom"].startswith("PAC air/eau"))
            rend_src = "catalogue (PAC air/eau)"
        elif gen == "bois granulés":
            sys_ = next(s for s in cat.systemes() if "granul" in s["nom"].lower())
            rend_src = "catalogue (poêle à granulés)"
        else:
            energie, rend = RENDEMENTS_GENERATEUR.get(gen, ("electricite", 0.95))
            sys_ = {"nom": gen, "energie": energie, "rendement_chauffage": rend, "rendement_ecs": 0.85}
            rend_src = f"rendement global {rend} supposé"
        sys_ = dict(sys_)
        ecs = E.get("type", {}).get("valeur")
        if ecs:
            sys_["nom"] = f"{gen} + ECS {ecs}"
            sys_["energie_ecs"] = "electricite"
            sys_["rendement_ecs"] = RENDEMENTS_ECS.get(ecs, sys_.get("rendement_ecs", 0.85))
        e.systeme = sys_
        hyp["systeme"] = val(sys_["nom"], "lu", C["generateur"]["source"], "haute", rendements=rend_src)
    # ---- usage : tertiaire → besoins d'ECS faibles, résultats indicatifs
    inf = dossier.get("infos", {})
    if inf.get("residentiel") and inf["residentiel"]["valeur"] is False:
        faible = E.get("usage", {}).get("valeur") == "faible"
        e.ecs_kwh_m2 = 1.0 if faible else 3.0
        hyp["besoin_ecs"] = val(e.ecs_kwh_m2, "supposé", f"usage « {inf['usage']['valeur']} »" + (" , ECS faible (notice)" if faible else ""),
                                "faible", "kWh/m².an")
        alertes.append(f"Usage « {inf['usage']['valeur']} » (tertiaire) : les seuils et le modèle de l'outil sont ceux de la maison "
                       "individuelle. Géométrie, parois et ponts thermiques restent valables ; Bbio/Cep et verdicts sont indicatifs, "
                       "à calculer dans Pléiades avec le scénario tertiaire.")
