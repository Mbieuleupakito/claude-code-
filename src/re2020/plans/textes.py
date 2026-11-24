"""Lecture des textes d'un plan PDF vectoriel : échelle, niveaux, étiquettes de baies, pièces.

Les mots sont regroupés en « phrases » (mots alignés et proches), y compris le texte tourné à 90°
(baies des façades latérales). Tout est exprimé dans un repère local (u = sens de lecture,
v = sens « vers la ligne suivante ») pour traiter le texte horizontal et vertical de la même façon.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

POUCE_M = 0.0254
PT_PAR_POUCE = 72.0


@dataclass
class Phrase:
    texte: str
    x0: float
    top: float
    x1: float
    bottom: float
    sens: str  # "ltr" (horizontal), "btt" (tourné +90°, lu de bas en haut), "ttb" (tourné -90°)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2

    def uv(self) -> tuple[float, float]:
        """Centre dans le repère de lecture (u le long de la ligne, v vers la ligne suivante)."""
        if self.sens == "btt":
            return (-self.cy, self.cx)
        if self.sens == "ttb":
            return (self.cy, -self.cx)
        return (self.cx, self.cy)

    @property
    def hauteur_ligne(self) -> float:
        return (self.x1 - self.x0) if self.sens in ("btt", "ttb") else (self.bottom - self.top)


# --------------------------------------------------------------------------- extraction des phrases

def _sens_mot(page, w) -> str:
    if w["upright"]:
        return "ltr"
    for c in page.chars:
        if not c["upright"] and w["x0"] - 0.5 <= c["x0"] <= w["x1"] + 0.5 and w["top"] - 0.5 <= c["top"] <= w["bottom"] + 0.5:
            return "btt" if c["matrix"][1] > 0 else "ttb"
    return "btt"


def phrases_de_page(page, ecart_max: float = 4.0) -> list[Phrase]:
    """Regroupe les mots de la page en phrases (même ligne, écart < ``ecart_max`` pt)."""
    mots = [w for w in page.extract_words(char_dir_rotated="btt") if w["upright"]]
    tournes = {}
    for sens in ("btt", "ttb"):
        for w in page.extract_words(char_dir_rotated=sens):
            if not w["upright"] and _sens_mot(page, w) == sens:
                tournes[(round(w["x0"], 1), round(w["top"], 1))] = (w, sens)
    items = [(w, "ltr") for w in mots] + list(tournes.values())

    def cle(item):  # (sens, coordonnée de ligne, position le long de la ligne)
        w, s = item
        if s == "ltr":
            return (s, w["top"], w["x0"])
        if s == "btt":
            return (s, w["x0"], -w["bottom"])
        return (s, w["x0"], w["top"])

    items.sort(key=cle)
    phrases: list[Phrase] = []
    for w, s in items:
        if phrases:
            p = phrases[-1]
            if p.sens == s == "ltr":
                meme = abs(w["top"] - p.top) < 1.5 and -1 < w["x0"] - p.x1 < ecart_max
            elif p.sens == s == "btt":
                meme = abs(w["x0"] - p.x0) < 1.5 and -1 < p.top - w["bottom"] < ecart_max
            elif p.sens == s == "ttb":
                meme = abs(w["x0"] - p.x0) < 1.5 and -1 < w["top"] - p.bottom < ecart_max
            else:
                meme = False
            if meme:
                p.texte += " " + w["text"]
                p.x0, p.top = min(p.x0, w["x0"]), min(p.top, w["top"])
                p.x1, p.bottom = max(p.x1, w["x1"]), max(p.bottom, w["bottom"])
                continue
        phrases.append(Phrase(w["text"], w["x0"], w["top"], w["x1"], w["bottom"], s))
    return phrases


# --------------------------------------------------------------------------- échelle

RE_ECHELLE = re.compile(r"(?:[ée]ch(?:elle)?\.?)\s*:?\s*1\s*[:/]\s*(\d{2,4})", re.I)


def m_par_pt(denominateur: float) -> float:
    """Mètres réels représentés par 1 point PDF à l'échelle 1/denominateur."""
    return POUCE_M / PT_PAR_POUCE * denominateur


def lire_echelles(phrases: list[Phrase], fenetre_pt: float = 80.0) -> list[tuple[int, Phrase]]:
    """Retourne les mentions d'échelle (dénominateur, phrase « Ech »).

    Les mots d'une même mention peuvent être espacés : on recolle les phrases de la même ligne
    situées à moins de ``fenetre_pt`` à droite du mot « Ech ».
    """
    out = []
    for p in phrases:
        if p.sens != "ltr" or not re.match(r"[ée]ch", p.texte, re.I):
            continue
        suite = sorted((q for q in phrases if q.sens == "ltr" and abs(q.top - p.top) < 2
                        and 0 <= q.x0 - p.x0 < fenetre_pt), key=lambda q: q.x0)
        m = RE_ECHELLE.search(" ".join(q.texte for q in suite))
        if m:
            out.append((int(m.group(1)), p))
    return out


# --------------------------------------------------------------------------- niveaux

RE_NIVEAU = re.compile(
    r"\b(R\s?\+\s?\d+|R\s?-\s?\d+|R\.?D\.?C\.?|rez[- ]de[- ]chauss[ée]e|[ée]tage\s*\d*|combles?|sous[- ]sol)\b", re.I)


def normaliser_niveau(txt: str) -> str:
    t = re.sub(r"\s", "", txt).upper().replace(".", "")
    if t in ("R+0", "RDC") or t.startswith("REZ"):
        return "RDC"
    if t.startswith("ETAGE") or t.startswith("ÉTAGE"):
        n = re.sub(r"\D", "", t)
        return f"R+{n or 1}"
    if t.startswith("SOUS"):
        return "R-1"
    if t.startswith("COMBLE"):
        return "COMBLES"
    return t


def lire_niveaux(phrases: list[Phrase]) -> list[tuple[str, Phrase]]:
    out = []
    for p in phrases:
        if p.sens == "ltr":
            m = RE_NIVEAU.search(p.texte)
            if m:
                out.append((normaliser_niveau(m.group(1)), p))
    return out


# --------------------------------------------------------------------------- étiquettes de baies

RE_DIMS = re.compile(r"(?:^|\s)(\d{2,3})\s*x\s*(\d{2,3})\s*(?:ht\.?)?(?:\s|$)", re.I)
RE_ALLEGE = re.compile(r"\ball(?:[èe]ge)?\.?\s*(\d{1,3})\b", re.I)
RE_NOM_BAIE = re.compile(r"^([A-Za-z]{1,5}\s?\d{1,3}[a-z]?)$")
RE_SURFACE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m[²2]$")


@dataclass
class EtiquetteBaie:
    nom: str | None
    largeur_m: float
    hauteur_m: float
    allege_m: float | None
    x: float  # centre de l'étiquette (pt)
    y: float
    sens: str
    complement: str  # texte additionnel lu (ex. « PV », « bso »)


def _voisine(base: Phrase, phrases: list[Phrase], dv_min: float, dv_max: float, du_max: float, cond) -> Phrase | None:
    bu, bv = base.uv()
    best, dmin = None, 1e9
    for q in phrases:
        if q is base or q.sens != base.sens or not cond(q):
            continue
        qu, qv = q.uv()
        dv, du = qv - bv, abs(qu - bu)
        if dv_min <= dv <= dv_max and du <= du_max and abs(dv) + du < dmin:
            best, dmin = q, abs(dv) + du
    return best


def lire_etiquettes_baies(phrases: list[Phrase]) -> list[EtiquetteBaie]:
    """Étiquettes « Nom / L x H ht. / all.X » (cm), empilées sur 2 ou 3 lignes."""
    out = []
    for p in phrases:
        m = RE_DIMS.search(" " + p.texte + " ")
        if not m:
            continue
        h = max(p.hauteur_ligne, 3.0)
        prefixe = p.texte[: m.start()].strip() if m.start() > 0 else ""
        nom_ph = _voisine(p, phrases, -2.6 * h, -0.4 * h, 25, lambda q: RE_NOM_BAIE.match(q.texte) is not None)
        all_ph = _voisine(p, phrases, 0.4 * h, 2.6 * h, 25, lambda q: RE_ALLEGE.search(q.texte) is not None)
        reste = (p.texte[m.end():] if m.end() < len(p.texte) else "").strip()
        complement = " ".join(t for t in (prefixe, reste) if t)
        out.append(EtiquetteBaie(
            nom=nom_ph.texte.replace(" ", "") if nom_ph else None,
            largeur_m=int(m.group(1)) / 100, hauteur_m=int(m.group(2)) / 100,
            allege_m=int(RE_ALLEGE.search(all_ph.texte).group(1)) / 100 if all_ph else None,
            x=p.cx, y=p.cy, sens=p.sens, complement=complement))
    return out


def lire_pieces(phrases: list[Phrase]) -> list[dict]:
    """Pièces étiquetées « Nom / 12.3 m² »."""
    out = []
    for p in phrases:
        m = RE_SURFACE.match(p.texte.strip())
        if not m:
            continue
        h = max(p.hauteur_ligne, 3.0)
        nom = _voisine(p, phrases, -2.6 * h, -0.4 * h, 30, lambda q: not RE_SURFACE.match(q.texte) and not RE_DIMS.search(q.texte))
        out.append({"nom": nom.texte if nom else None, "surface_m2": float(m.group(1).replace(",", ".")), "x": p.cx, "y": p.cy})
    return out
