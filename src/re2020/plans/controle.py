"""Image de contrôle : superpose au plan ce que l'outil a détecté (à regarder avant de saisir)."""
from __future__ import annotations

import math

import pdfplumber


def image_controle(chemin_pdf, resultat: dict, sortie_png, resolution: int = 110) -> None:
    """Vert = contour des murs ; orange = baie appariée ; rouge = baie à vérifier ; bleu = nord lu."""
    with pdfplumber.open(chemin_pdf) as pdf:
        im = pdf.pages[resultat.get("page", 0)].to_image(resolution=resolution)
        for n in resultat["niveaux"]:
            im.draw_line([tuple(c) for c in n["_contour_pt"]], stroke=(0, 170, 0), stroke_width=3)
            for b in n["baies"]:
                coul = (220, 0, 0) if b.get("a_verifier") else (255, 140, 0)
                x0, y0, x1, y1 = b["_ouverture_pt"]
                im.draw_line([(x0, y0), (x1, y1)], stroke=coul, stroke_width=7)
                im.draw_line([tuple(b["_etiquette_pt"]), ((x0 + x1) / 2, (y0 + y1) / 2)], stroke=coul, stroke_width=1)
        nord = resultat["nord"]
        if nord.get("valeur") is not None:
            a = math.radians(nord["valeur"])
            for (cx, cy) in nord.get("_symboles_pt", []):
                im.draw_line([(cx, cy), (cx + 25 * math.sin(a), cy - 25 * math.cos(a))], stroke=(0, 0, 255), stroke_width=3)
        im.save(sortie_png)
