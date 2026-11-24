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
                        catalogue: Catalogue | None = None, **choix) -> tuple[Entrees, dict]:
    """Retourne (Entrees, hypothèses tracées utilisées)."""
    cat = catalogue or Catalogue()
    h = {**DEFAUTS, **{k: v for k, v in choix.items() if v is not None}}
    bat, niv = plan["batiment"], plan["niveaux"]
    iso_mode = "ITE" if any("ITE" in n["murs_exterieurs"]["isolation"]["valeur"] for n in niv) else "ITI"
    hyp = {}

    if sref is None:
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
    return e, hyp
