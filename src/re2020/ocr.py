"""OCR local des pages de plans dont le texte est dessiné en traits (polices SHX d'AutoCAD, PDF « aplatis »,
cartouches en image). Moteur RapidOCR (ONNX), qui tourne sur le poste : rien n'est envoyé à l'extérieur.

Utilisé seulement sur les pages riches en traits et pauvres en texte, avec un cache par page.
"""
from __future__ import annotations

import re
from functools import lru_cache

RESOLUTION = 200  # dpi
_moteur = None


def disponible() -> bool:
    import importlib.util

    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def page_a_ocr(page) -> bool:
    """Beaucoup de dessin, peu de vrai texte : le texte est probablement dessiné en traits."""
    return len(page.chars) < 400 and len(page.lines) + len(page.curves) + len(page.rects) > 500


def corriger(texte: str) -> str:
    """Corrections OCR courantes : « 08OOO » → « 08000 » (O lus à la place de 0 dans les nombres)."""
    def code(m):
        t = m.group(0)
        return t.replace("O", "0").replace("o", "0") if sum(c.isdigit() for c in t) >= 2 else t
    return re.sub(r"\b[0-9Oo]{5}\b", code, texte)


@lru_cache(maxsize=64)
def _ocr(chemin: str, num_page: int) -> tuple:
    global _moteur
    import numpy as np
    import pdfplumber
    from rapidocr_onnxruntime import RapidOCR

    if _moteur is None:
        _moteur = RapidOCR()
    with pdfplumber.open(chemin) as pdf:
        img = pdf.pages[num_page].to_image(resolution=RESOLUTION).original.convert("RGB")
    res, _ = _moteur(np.array(img))
    f = 72 / RESOLUTION
    out = []
    for boite, texte, conf in res or []:
        if float(conf) < 0.6 or not texte.strip():
            continue
        xs, ys = [p[0] for p in boite], [p[1] for p in boite]
        out.append((corriger(texte.strip()), min(xs) * f, min(ys) * f, max(xs) * f, max(ys) * f, float(conf)))
    return tuple(out)


def textes_page(page) -> list[tuple]:
    """[(texte, x0, top, x1, bottom, confiance)] en points PDF, ou [] si OCR indisponible / inutile."""
    if not disponible() or not page_a_ocr(page):
        return []
    try:
        items = _ocr(str(page.pdf.stream.name), page.page_number - 1)
    except Exception:
        return []
    # on ne garde que ce qui n'est pas déjà du vrai texte (sinon les étiquettes seraient lues deux fois)
    vrais = [(c["x0"], c["top"], c["x1"], c["bottom"]) for c in page.chars]
    def recouvre(it):
        _, x0, t, x1, b, _ = it
        return any(cx0 < x1 and cx1 > x0 and ct < b and cb > t for cx0, ct, cx1, cb in vrais)
    return [it for it in items if not recouvre(it)]


def blocs(items: list[tuple]) -> list[str]:
    """Regroupe les textes en blocs (cases de cartouche) : empilés avec des abscisses qui se recouvrent."""
    items = sorted(items, key=lambda t: (t[2], t[1]))
    groupes: list[list[tuple]] = []
    for it in items:
        h = it[4] - it[2]
        for g in groupes:
            dernier = g[-1]
            if 0 <= it[2] - dernier[4] < 1.6 * max(h, 4) and min(it[3], dernier[3]) - max(it[1], dernier[1]) > -2:
                g.append(it)
                break
        else:
            groupes.append([it])
    return ["\n".join(t[0] for t in g) for g in groupes]
