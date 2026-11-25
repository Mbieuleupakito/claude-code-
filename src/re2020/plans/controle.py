"""Image de contrôle : superpose aux pages de plans ce que l'outil a détecté (à regarder avant de saisir)."""
from __future__ import annotations

import math
from pathlib import Path

import pdfplumber
from PIL import Image


def image_controle(chemins_pdf, resultat: dict, sortie_png, resolution: int = 110) -> None:
    """Vert = contour des murs ; orange = baie appariée ; rouge = baie à vérifier ; bleu = nord lu (symbole).
    Plusieurs pages de plans → images empilées verticalement."""
    chemins = [Path(c) for c in (chemins_pdf if isinstance(chemins_pdf, (list, tuple)) else [chemins_pdf])]
    groupes: dict[tuple, list] = {}
    for n in resultat["niveaux"]:
        groupes.setdefault((n.get("_fichier", 0), n.get("_page", resultat.get("page", 0))), []).append(n)
    images = []
    nord = resultat["nord"]
    for i_g, ((ifi, ipa), niveaux) in enumerate(sorted(groupes.items())):
        with pdfplumber.open(chemins[ifi]) as pdf:
            im = pdf.pages[ipa].to_image(resolution=resolution)
            for n in niveaux:
                im.draw_line([tuple(c) for c in n["_contour_pt"]], stroke=(0, 170, 0), stroke_width=3)
                for b in n["baies"]:
                    coul = (220, 0, 0) if b.get("a_verifier") else (255, 140, 0)
                    x0, y0, x1, y1 = b["_ouverture_pt"]
                    im.draw_line([(x0, y0), (x1, y1)], stroke=coul, stroke_width=7)
                    im.draw_line([tuple(b["_etiquette_pt"]), ((x0 + x1) / 2, (y0 + y1) / 2)], stroke=coul, stroke_width=1)
            if nord.get("valeur") is not None and i_g == 0:
                a = math.radians(nord["valeur"])
                for (cx, cy) in nord.get("_symboles_pt", []):
                    im.draw_line([(cx, cy), (cx + 25 * math.sin(a), cy - 25 * math.cos(a))], stroke=(0, 0, 255), stroke_width=3)
            images.append(im.annotated.convert("RGB"))
    if len(images) == 1:
        images[0].save(sortie_png)
        return
    largeur = max(i.width for i in images)
    total = Image.new("RGB", (largeur, sum(i.height for i in images) + 8 * (len(images) - 1)), "white")
    y = 0
    for i in images:
        total.paste(i, (0, y))
        y += i.height + 8
    total.save(sortie_png)
