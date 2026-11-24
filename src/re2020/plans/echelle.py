"""Échelle du plan : mention « Ech 1:N » vérifiée (ou remplacée) par des cotes écrites.

Un PDF imprimé « ajusté à la page » garde la mention 1:100 alors que le dessin est réduit : on ne fait
donc confiance à la mention que si des cotes écrites la confirment. Deux sources de cotes :
- lignes de cote : un nombre « 3.60 » / « 3,60 » (m) posé le long d'un trait parallèle ;
- étiquettes de baies : largeur écrite (cm) comparée à la largeur mesurée de l'ouverture.
"""
from __future__ import annotations

import re

from .textes import Phrase

RE_COTE_M = re.compile(r"^(\d{1,2})[.,](\d{2})$")


def ratios_lignes_de_cote(phrases: list[Phrase], lignes) -> list[float]:
    """Ratios m/pt tirés des couples (texte de cote, trait parallèle voisin)."""
    out = []
    for p in phrases:
        m = RE_COTE_M.match(p.texte.strip())
        if not m:
            continue
        valeur = float(f"{m.group(1)}.{m.group(2)}")
        if valeur < 0.3:
            continue
        h = max(p.hauteur_ligne, 3.0)
        horiz = p.sens == "ltr"
        best = None
        for o in lignes:
            dx, dy = o["x1"] - o["x0"], o["bottom"] - o["top"]
            if horiz and dy < 0.3 and dx > 5 and o["x0"] - 1 <= p.cx <= o["x1"] + 1:
                d = min(abs(o["top"] - p.top), abs(o["top"] - p.bottom))
                lg = dx
            elif not horiz and dx < 0.3 and dy > 5 and o["top"] - 1 <= p.cy <= o["bottom"] + 1:
                d = min(abs(o["x0"] - p.x0), abs(o["x0"] - p.x1))
                lg = dy
            else:
                continue
            if d <= 2.5 * h and (best is None or (d, -lg) < best[:2]):
                best = (d, -lg, lg)
        if best:
            out.append(valeur / best[2])
    return out


def consensus(ratios: list[float], tol=0.02, mini=2) -> tuple[float, int] | None:
    """Valeur la plus soutenue (à ±tol près) et son nombre d'appuis, ou None."""
    best = None
    for r in ratios:
        appuis = [x for x in ratios if abs(x - r) <= tol * r]
        if len(appuis) >= mini and (best is None or len(appuis) > best[1]):
            best = (sorted(appuis)[len(appuis) // 2], len(appuis))
    return best
