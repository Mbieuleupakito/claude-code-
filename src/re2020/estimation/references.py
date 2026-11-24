"""Comparaison du modèle simplifié avec les résultats Pléiades de data/references (écarts affichés, pas cachés)."""
from __future__ import annotations

import json
from pathlib import Path

from ..catalogues import Catalogue
from .hypotheses import entrees_depuis_plan
from .modele import CALAGE, entrees_calage, estimer

RACINE = Path(__file__).resolve().parents[3] / "data"

# Cas disposant d'une géométrie exploitable : (nom, json plan, zone, altitude, filtre sur resultats_references.json)
CAS_PLANS = [("Domène M01 (plan ANKHA)", RACINE / "examples/domene_m01/domene_m01_extraction.json", "H1c", 220,
              {"ville": "Domène", "O_SREF": "105.5"})]


def comparer(catalogue: Catalogue | None = None) -> list[dict]:
    cat = catalogue or Catalogue()
    lignes = []
    c = json.loads(CALAGE.read_text(encoding="utf-8"))
    r = estimer(entrees_calage(c), "RSET")
    lignes.append({"cas": "Charleville (entrées du RSET, cas de calage)", "Bbio_pleiades": [c["bbio"]],
                   "Bbio_estime": r["Bbio"]["valeur"], "fourchette": r["Bbio"]["fourchette"],
                   "Cep_pleiades": [c["cep"]], "Cep_estime": r["Cep"]["valeur"],
                   "note": "calage : l'écart Bch est nul par construction"})
    refs = json.loads((RACINE / "references/resultats_references.json").read_text(encoding="utf-8"))
    utilises = set()
    for nom, chemin, zone, alt, filtre in CAS_PLANS:
        if not chemin.exists():
            continue
        plan = json.loads(chemin.read_text(encoding="utf-8"))
        cibles = [x for x in refs if all(x.get(k) == v for k, v in filtre.items())]
        utilises.update(id(x) for x in cibles)
        sref = float(cibles[0]["O_SREF"]) if cibles else None
        for retour, suffixe in ((True, ""), (False, " — sans retour d'isolant")):
            e, _ = entrees_depuis_plan(plan, zone, alt, sref=sref, catalogue=cat, retour_isolant_menuiseries=retour)
            r = estimer(e)
            lignes.append({"cas": nom + suffixe, "Bbio_pleiades": sorted(float(x["O_Bbio_pts_annuel"]) for x in cibles),
                           "Bbio_estime": r["Bbio"]["valeur"], "fourchette": r["Bbio"]["fourchette"],
                           "Cep_pleiades": sorted(float(x["O_Cep_annuel"]) for x in cibles), "Cep_estime": r["Cep"]["valeur"],
                           "note": f"{len(cibles)} variantes Pléiades (enveloppe inconnue) ; hypothèses par défaut"
                                   + ("" if retour else " ; sensibilité aux menuiseries")})
    for x in refs:
        if id(x) not in utilises:
            lignes.append({"cas": f"{x['ville']} {x['O_SREF']} m² ({x['zone']})", "Bbio_pleiades": [float(x["O_Bbio_pts_annuel"])],
                           "Bbio_estime": None, "fourchette": None, "Cep_pleiades": [float(x["O_Cep_annuel"])], "Cep_estime": None,
                           "note": "non estimable : plan absent (déposer le PDF pour l'ajouter)"})
    for l in lignes:
        if l["Bbio_estime"] is not None and l["Bbio_pleiades"]:
            ref = sum(l["Bbio_pleiades"]) / len(l["Bbio_pleiades"])
            l["ecart_Bbio"] = round(l["Bbio_estime"] - ref, 1)
            l["dans_fourchette"] = any(l["fourchette"][0] <= b <= l["fourchette"][1] for b in l["Bbio_pleiades"])
    return lignes


def tableau(lignes: list[dict]) -> str:
    out = [f"{'Cas':48s} {'Bbio Pléiades':>16s} {'Bbio estimé':>11s} {'fourchette':>13s} {'écart':>6s}  Cep Pl./est."]
    for l in lignes:
        bp = "/".join(f"{b:g}" for b in l["Bbio_pleiades"])
        be = "-" if l["Bbio_estime"] is None else f"{l['Bbio_estime']:.1f}"
        fo = "-" if not l["fourchette"] else f"{l['fourchette'][0]:.0f}–{l['fourchette'][1]:.0f}"
        ec = "-" if "ecart_Bbio" not in l else f"{l['ecart_Bbio']:+.1f}"
        cp = "/".join(f"{c:g}" for c in l["Cep_pleiades"]) + " / " + ("-" if l["Cep_estime"] is None else f"{l['Cep_estime']:.1f}")
        out.append(f"{l['cas'][:48]:48s} {bp:>16s} {be:>11s} {fo:>13s} {ec:>6s}  {cp}   ({l['note']})")
    return "\n".join(out)


if __name__ == "__main__":
    print(tableau(comparer()))
