"""Générateur de propositions : combinaisons isolant / épaisseur / menuiserie / système qui respectent
les seuils RE2020 estimés, classées par coût quand un prix existe.

Méthode : pour chaque paroi, front de Pareto (U, coût) des compositions complètes (systèmes constructifs x isolant x épaisseur) ;
puis combinaisons de ces fronts x menuiseries x systèmes, évaluées avec le modèle simplifié. Une
combinaison est retenue si Bbio, Cep et Cep,nr estimés restent sous les seuils avec une marge de
prudence (l'estimation n'est pas un calcul réglementaire). Les seuils « approx » (MbHSP inconnu) sont
signalés.
"""
from __future__ import annotations

import itertools
from dataclasses import replace

from . import compositions
from .catalogues import Catalogue
from .estimation.modele import K_CAL, Entrees, _brut, consommations, estimer
from .trace import val

SURFACE = {"mur": "murs", "plafond": "toiture", "plancher_bas": "plancher_bas"}
MARGE = 0.05  # 5 % sous le seuil


def options_paroi(cat: Catalogue, usage: str, surface_m2: float, isolation: str | None = None,
                  structure: str | None = None) -> list[dict]:
    """Front de Pareto (U croissant, coût décroissant) des COMPOSITIONS complètes d'une paroi (système constructif
    cohérent avec le projet x isolant compatible x épaisseur)."""
    opts = compositions.options(usage, cat.isolants(), surface_m2, isolation, structure)
    for o in opts:
        o["lambda_retenu"] = next((c["lambda_W_mK"] for c in o["couches"] if c.get("isolant")), None)
    # front de Pareto : par coût croissant, on garde une option seulement si elle améliore U
    opts.sort(key=lambda o: (o["cout"] if o["cout"] is not None else 0, o["U"]))
    front, meilleur_u = [], float("inf")
    for o in opts:
        if o["U"] < meilleur_u - 1e-4:
            front.append(o)
            meilleur_u = o["U"]
    # on garde au plus 8 points répartis le long du front
    front.sort(key=lambda o: o["U"])
    if len(front) > 8:
        idx = sorted({round(i * (len(front) - 1) / 7) for i in range(8)})
        front = [front[i] for i in idx]
    return front


def _paroi(o: dict) -> dict:
    return {"isolant": o["isolant"], "epaisseur_cm": o["epaisseur_cm"], "U": o["U"], "systeme": o["systeme_nom"],
            "composition": o["composition"], "couches": o["couches"], "epaisseur_totale_cm": o["epaisseur_totale_cm"],
            "ref_projet": o.get("ref_projet")}


def proposer(e: Entrees, seuils: dict, cat: Catalogue | None = None, n: int = 5, isolation: str | None = None,
             structure: str | None = None) -> dict:
    """``e`` : entrées de base (géométrie, Ψ...) ; ``seuils`` : sortie de seuils_energie(). ``isolation`` (ITE / ITI lu
    sur le plan) et ``structure`` (lue dans la notice) restreignent les murs aux systèmes cohérents avec le projet."""
    cat = cat or Catalogue()
    smax = {k: seuils[k]["valeur"] for k in ("Bbio_max", "Cep_max", "Cep_nr_max")}
    fronts = {u: options_paroi(cat, u, e.surfaces[SURFACE[u]], isolation, structure) for u in ("mur", "plafond", "plancher_bas")}
    s_baies = sum(e.baies.values())
    candidats = []
    for mur, toit, pb, men, sysm in itertools.product(fronts["mur"], fronts["plafond"], fronts["plancher_bas"],
                                                      cat.menuiseries(), cat.systemes()):
        ee = replace(e, U={"murs": mur["U"], "toiture": toit["U"], "plancher_bas": pb["U"], "baies": men["Uw"]},
                     Sw=men["Sw"], systeme=sysm)
        b = _brut(ee, K_CAL)
        cs = consommations(ee, b)
        if b["Bbio"] > smax["Bbio_max"] * (1 - MARGE) or cs["Cep"] > smax["Cep_max"] * (1 - MARGE) \
                or cs["Cep_nr"] > smax["Cep_nr_max"] * (1 - MARGE):
            continue
        couts = [mur["cout"], toit["cout"], pb["cout"],
                 men["prix_eur_m2"] * s_baies if men["prix_eur_m2"] is not None else None, sysm.get("prix_eur")]
        cout = None if any(c is None for c in couts) else sum(couts)
        candidats.append((cout if cout is not None else float("inf"), -min(smax["Bbio_max"] - b["Bbio"], 1e9),
                          {"mur": mur, "toiture": toit, "plancher_bas": pb, "menuiserie": men, "systeme": sysm, "cout": cout, "e": ee}))
    candidats.sort(key=lambda c: (c[0], c[1]))
    retenus, vus = [], set()
    for _, _, c in candidats:
        cle = (c["systeme"]["nom"], c["menuiserie"]["nom"])  # diversité : une proposition par couple système/menuiserie
        if cle in vus and len(candidats) > n:
            continue
        vus.add(cle)
        retenus.append(c)
        if len(retenus) == n:
            break
    out = []
    for i, c in enumerate(retenus, 1):
        r = estimer(c["e"], "proposition")
        alertes = [f"Isolant non certifié « {c[k]['isolant']} » : λ majoré de 15 % (déjà appliqué ici)"
                   for k in ("mur", "toiture", "plancher_bas") if not c[k]["certifie"]]
        if r["Bbio"]["fourchette"][1] > smax["Bbio_max"]:
            alertes.append("Le haut de la fourchette Bbio dépasse le seuil : marge à confirmer dans Pléiades.")
        out.append({
            "rang": i,
            "murs": _paroi(c["mur"]), "toiture": _paroi(c["toiture"]), "plancher_bas": _paroi(c["plancher_bas"]),
            "menuiseries": {"nom": c["menuiserie"]["nom"], "Uw": c["menuiserie"]["Uw"], "Sw": c["menuiserie"]["Sw"]},
            "systeme": c["systeme"]["nom"],
            "Bbio": r["Bbio"], "Cep": r["Cep"], "Cep_nr": r["Cep_nr"],
            "marges": {"Bbio": round(smax["Bbio_max"] - r["Bbio"]["valeur"], 1), "Cep": round(smax["Cep_max"] - r["Cep"]["valeur"], 1),
                       "Cep_nr": round(smax["Cep_nr_max"] - r["Cep_nr"]["valeur"], 1)},
            "cout_eur": val(round(c["cout"]) if c["cout"] is not None else None, "supposé",
                            "prix indicatifs du catalogue produits (à remplacer par les prix fournisseur)", "faible", "€ HT"),
            "alertes": alertes,
        })
    return {
        "seuils": {k: seuils[k] for k in ("Bbio_max", "Cep_max", "Cep_nr_max")},
        "seuils_approx": seuils["approx"],
        "nb_combinaisons_testees": len(fronts["mur"]) * len(fronts["plafond"]) * len(fronts["plancher_bas"])
                                   * len(cat.menuiseries()) * len(cat.systemes()),
        "nb_conformes": len(candidats),
        "propositions": out,
        # autres systèmes constructifs qui atteignent le même U que la proposition n°1 (au choix du thermicien)
        "variantes": {k: [_paroi(dict(o, systeme_nom=o["systeme_nom"])) | {"cout_eur": o["cout"]}
                          for o in compositions.meilleures_par_systeme(u, cat.isolants(), out[0][k]["U"], e.surfaces[SURFACE[u]],
                                                                       isolation, structure)]
                      for k, u in (("murs", "mur"), ("toiture", "plafond"), ("plancher_bas", "plancher_bas"))} if out else {},
        "avertissement": ("Seuils « approx » (MbHSP/McHSP inconnus) : marges probablement sous-estimées. " if seuils["approx"] else "")
                         + "Propositions à vérifier dans Pléiades ; DH (confort d'été) non évalué.",
    }
