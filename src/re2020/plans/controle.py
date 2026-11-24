"""Image de contrôle : superpose au plan ce que l'outil a détecté (à regarder avant de saisir)."""
from __future__ import annotations

import math

import pdfplumber


def image_controle(chemin_pdf, resultat: dict, sortie_png, resolution: int = 110) -> None:
    with pdfplumber.open(chemin_pdf) as pdf:
        p = pdf.pages[resultat.get("page", 0)]
        im = p.to_image(resolution=resolution)
        for n in resultat["niveaux"]:
            x0, y0, x1, y1 = n["_bbox_pt"]
            im.draw_rect((x0, y0, x1, y1), fill=None, stroke=(0, 170, 0), stroke_width=3)
            for b in n["baies"]:
                ex, ey = b["_etiquette_pt"]
                coul = (220, 0, 0) if b.get("a_verifier") else (255, 140, 0)
                if b["_ouverture_pt"]:
                    a, c = b["_ouverture_pt"]
                    f = b["facade"]
                    if f in ("haut", "bas"):
                        y = y0 if f == "haut" else y1
                        im.draw_rect((a, y - 4, c, y + 4), fill=coul + (120,), stroke=coul, stroke_width=1)
                        cx, cy = (a + c) / 2, y
                    else:
                        x = x0 if f == "gauche" else x1
                        im.draw_rect((x - 4, a, x + 4, c), fill=coul + (120,), stroke=coul, stroke_width=1)
                        cx, cy = x, (a + c) / 2
                    im.draw_line([(ex, ey), (cx, cy)], stroke=coul, stroke_width=1)
                else:
                    im.draw_circle((ex, ey), radius=6, fill=None, stroke=coul)
        nord = resultat["nord"]
        if nord.get("valeur") is not None:
            a = math.radians(nord["valeur"])
            for (cx, cy) in nord.get("_symboles_pt", []):
                im.draw_line([(cx, cy), (cx + 25 * math.sin(a), cy - 25 * math.cos(a))], stroke=(0, 0, 255), stroke_width=3)
        im.save(sortie_png)
