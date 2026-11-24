"""Ligne de commande : python -m src.re2020.plans plan.pdf [-o plan.json] [--controle plan.png]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .controle import image_controle
from .extraction import extraire_plan


def resume(r: dict) -> str:
    L = [f"Plan : {r['source']} — échelle 1:{r['echelle']['denominateur']['valeur']} ({r['echelle']['denominateur']['tag']})"]
    n = r["nord"]
    L.append(f"Nord : {n['valeur']}° / haut de feuille ({n['tag']}, confiance {n['confiance']})" if n["valeur"] is not None
             else "Nord : NON DÉTECTÉ → passer --nord")
    for niv in r["niveaux"]:
        e, m = niv["emprise_m"], niv["murs_exterieurs"]
        L.append(f"- {niv['niveau']['valeur']} ({niv['forme']['valeur']}) : emprise {e['largeur']['valeur']} x {e['profondeur']['valeur']} m ; "
                 f"surface int. {niv['surface_interieure_m2']['valeur']} m² (pièces lues {niv['surface_pieces_etiquetees_m2']['valeur']} m²) ; "
                 f"mur {m['couche_pleine_m']['valeur']} + hachures ext. {m['bande_hachuree_ext_m']['valeur']} / int. "
                 f"{m['bande_hachuree_int_m']['valeur']} m → {m['isolation']['valeur']}")
        for b in niv["baies"]:
            flag = "  ⚠ " + b["a_verifier"] if b.get("a_verifier") else ""
            o = b["orientation"] or b["facade"]
            L.append(f"    {b['nom'] or '?':8s} {o:3s} {b['largeur_m']['valeur']:.2f} x {b['hauteur_m']['valeur']:.2f} m{flag}")
    bat = r["batiment"]
    L.append(f"Baies par orientation (m²) : {bat['baies_par_orientation_m2']} — total {bat['baies_total_m2']}")
    pt = bat["ponts_thermiques"]
    L.append("Ponts thermiques (ml) : " + " ; ".join(f"{v['liaison']} {v['valeur']}" for v in pt.values()))
    L.append(f"Surface intérieure totale : {bat['surface_interieure_totale_m2']['valeur']} m² (HSP supposée {bat['hauteur_sous_plafond_m']['valeur']} m)")
    if r["alertes"]:
        L.append("Alertes :")
        L += [f"  ⚠ {a}" for a in r["alertes"]]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extraction d'un plan PDF vectoriel → JSON tracé (RE2020 / Pléiades)")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--sortie", help="fichier JSON (défaut : <pdf>.json)")
    ap.add_argument("--controle", help="image PNG de contrôle (détections superposées au plan)")
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--hsp", type=float, default=2.50, help="hauteur sous plafond supposée (m)")
    ap.add_argument("--echelle", type=int, help="dénominateur d'échelle si non lisible (ex. 100)")
    ap.add_argument("--nord", type=float, help="angle du nord / haut de feuille (°, positif vers la droite)")
    a = ap.parse_args(argv)
    r = extraire_plan(a.pdf, page=a.page, hsp_m=a.hsp, denominateur=a.echelle, angle_nord_deg=a.nord)
    sortie = Path(a.sortie or Path(a.pdf).with_suffix(".json"))
    sortie.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.controle:
        image_controle(a.pdf, r, a.controle)
    print(resume(r))
    print(f"\nJSON : {sortie}" + (f" ; contrôle : {a.controle}" if a.controle else ""))


if __name__ == "__main__":
    main()
