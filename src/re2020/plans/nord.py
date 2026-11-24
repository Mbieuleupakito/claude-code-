"""Symbole du nord et orientation des façades.

Détection : un cercle (polyligne de petits segments) traversé par un diamètre dont une extrémité
porte une pointe de flèche (au moins deux petits segments qui en partent). La direction
centre → pointe donne le nord sur la feuille.

Conventions : coordonnées PDF (x vers la droite, y vers le bas). Les azimuts sont comptés en degrés
dans le sens horaire depuis le nord géographique (0 = N, 90 = E, 180 = S, 270 = O).
"""
from __future__ import annotations

import math
from collections import defaultdict

SECTEURS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def _seg(o):
    (x0, y0), (x1, y1) = o["pts"][0], o["pts"][-1]
    return x0, y0, x1, y1


def detecter_fleches_nord(lignes, rayon_min: float = 3.0, rayon_max: float = 25.0) -> list[dict]:
    """Retourne les symboles trouvés : {centre, rayon, vecteur_nord (unitaire, repère page)}."""
    segs = [_seg(o) for o in lignes if len(o.get("pts", [])) >= 2]
    grille = defaultdict(list)  # extrémités indexées par case de 2 pt
    for i, (x0, y0, x1, y1) in enumerate(segs):
        for x, y in ((x0, y0), (x1, y1)):
            grille[(int(x // 2), int(y // 2))].append((x, y, i))

    def autour(x, y, r):
        for gx in range(int((x - r) // 2), int((x + r) // 2) + 1):
            for gy in range(int((y - r) // 2), int((y + r) // 2) + 1):
                yield from grille.get((gx, gy), ())

    trouves = []
    for i, (x0, y0, x1, y1) in enumerate(segs):
        lg = math.hypot(x1 - x0, y1 - y0)
        r = lg / 2
        if not (rayon_min <= r <= rayon_max):
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # cercle : beaucoup d'extrémités de petits segments à distance ~r du centre
        def sur(x, y):
            return abs(math.hypot(x - cx, y - cy) - r) < 0.12 * r

        sur_cercle = {j for (_, _, j) in autour(cx, cy, r * 1.15)
                      if j != i and sur(segs[j][0], segs[j][1]) and sur(segs[j][2], segs[j][3])
                      and math.hypot(segs[j][2] - segs[j][0], segs[j][3] - segs[j][1]) < 0.8 * r}
        if len(sur_cercle) < 10:
            continue
        # cercle presque complet : les segments couvrent au moins 300° (secteurs de 10°)
        secteurs = set()
        for j in sur_cercle:
            for t in (0.0, 0.5, 1.0):
                x = segs[j][0] + t * (segs[j][2] - segs[j][0])
                y = segs[j][1] + t * (segs[j][3] - segs[j][1])
                secteurs.add(int(math.degrees(math.atan2(y - cy, x - cx)) % 360 // 10))
        if len(secteurs) < 30:
            continue
        # pointe : extrémité du diamètre d'où partent deux petits segments, de part et d'autre de l'axe
        for (px, py), (ax, ay) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
            ux, uy = (ax - px) / lg, (ay - py) / lg  # de la pointe vers l'arrière
            cotes = set()
            for (x, y, j) in autour(px, py, 0.4):
                if j == i or j in sur_cercle or math.hypot(x - px, y - py) > 0.3:
                    continue
                sx0, sy0, sx1, sy1 = segs[j]
                l = math.hypot(sx1 - sx0, sy1 - sy0)
                if not (0.15 * r <= l <= 0.7 * r):
                    continue
                ox, oy = (sx1 - sx0, sy1 - sy0) if math.hypot(sx0 - px, sy0 - py) < 0.3 else (sx0 - sx1, sy0 - sy1)
                cos = (ox * ux + oy * uy) / l
                if 0.4 <= cos <= 0.97:  # branche inclinée de 15° à 65° vers l'arrière
                    cotes.add(1 if ux * oy - uy * ox > 0 else -1)
            if cotes == {1, -1}:
                vx, vy = px - ax, py - ay
                n = math.hypot(vx, vy)
                trouves.append({"centre": (round(cx, 1), round(cy, 1)), "rayon": round(r, 1),
                                "vecteur_nord": (vx / n, vy / n)})
                break
    # dédoublonnage (même centre)
    uniques = []
    for t in trouves:
        if all(math.hypot(t["centre"][0] - u["centre"][0], t["centre"][1] - u["centre"][1]) > 2 for u in uniques):
            uniques.append(t)
    return uniques


def angle_nord_depuis_haut(vecteur_nord) -> float:
    """Angle du nord par rapport au haut de la feuille, en degrés, positif vers la droite (horaire)."""
    vx, vy = vecteur_nord
    return math.degrees(math.atan2(vx, -vy))


def azimut(normale_page, angle_nord_deg: float) -> float:
    """Azimut (0 = N, sens horaire) d'une direction donnée dans le repère page (y vers le bas)."""
    nx, ny = normale_page
    return (math.degrees(math.atan2(nx, -ny)) - angle_nord_deg) % 360


def secteur(az: float) -> str:
    return SECTEURS[int(((az + 22.5) % 360) // 45)]


def proche_limite(az: float, marge: float = 7.5) -> bool:
    """Vrai si l'azimut est à moins de ``marge`` degrés d'une limite entre deux secteurs."""
    d = (az - 22.5) % 45
    return d < marge or d > 45 - marge
