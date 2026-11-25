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

    phrases: list[Phrase] = []
    # texte horizontal : chaque mot (de gauche à droite) rejoint la phrase de la même ligne qui finit juste avant lui
    horiz = sorted((it for it in items if it[1] == "ltr"), key=lambda it: (it[0]["x0"], it[0]["top"]))
    ouvertes: list[Phrase] = []
    for w, s_ in horiz:
        h = w["bottom"] - w["top"]
        ec = max(ecart_max, 0.6 * h)
        cible = None
        for p in ouvertes:
            if abs(w["top"] - p.top) < max(1.5, 0.15 * h) and -1 < w["x0"] - p.x1 < ec:
                cible = p
                break
        if cible:
            cible.texte += " " + w["text"]
            cible.x0, cible.top = min(cible.x0, w["x0"]), min(cible.top, w["top"])
            cible.x1, cible.bottom = max(cible.x1, w["x1"]), max(cible.bottom, w["bottom"])
        else:
            p = Phrase(w["text"], w["x0"], w["top"], w["x1"], w["bottom"], "ltr")
            ouvertes.append(p)
            phrases.append(p)
        ouvertes = [p for p in ouvertes if w["x0"] - p.x1 < 60]  # les phrases loin derrière sont closes
    # texte vertical
    vert = sorted((it for it in items if it[1] != "ltr"), key=cle)
    for w, s_ in vert:
        if phrases and phrases[-1].sens == s_:
            p = phrases[-1]
            ec = max(ecart_max, 0.6 * (w["x1"] - w["x0"]))
            if s_ == "btt":
                meme = abs(w["x0"] - p.x0) < 1.5 and -1 < p.top - w["bottom"] < ec
            else:
                meme = abs(w["x0"] - p.x0) < 1.5 and -1 < w["top"] - p.bottom < ec
            if meme:
                p.texte += " " + w["text"]
                p.x0, p.top = min(p.x0, w["x0"]), min(p.top, w["top"])
                p.x1, p.bottom = max(p.x1, w["x1"]), max(p.bottom, w["bottom"])
                continue
        phrases.append(Phrase(w["text"], w["x0"], w["top"], w["x1"], w["bottom"], s_))
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
    r"(?<![\w'’])(R\s?\+\s?\d+|R\s?-\s?\d+|R\.?D\.?C\.?|rez[- ]de[- ]chauss[ée]e|(?:1er|1e|\d+e|premier|second|deuxi[eè]me)\s+[ée]tage"
    r"|(?<!d['’])[ée]tage\s+\d+(?![,.]\d)|combles?|sous[- ]sol)\b", re.I)


def normaliser_niveau(txt: str) -> str:
    t = re.sub(r"\s", "", txt).upper().replace(".", "")
    if t in ("R+0", "RDC") or t.startswith("REZ"):
        return "RDC"
    if "ETAGE" in t or "ÉTAGE" in t:
        if t.startswith(("1ER", "1E", "PREMIER")):
            return "R+1"
        if t.startswith(("SECOND", "DEUXI")):
            return "R+2"
        n = re.sub(r"\D", "", t)
        return f"R+{n or 1}"
    if t.startswith("SOUS"):
        return "R-1"
    if t.startswith("COMBLE"):
        return "COMBLES"
    return t


RE_PAS_TITRE = re.compile(r"\b(vide|tr[ée]mie|vers|depuis|acc[eè]s|monte|descend|niveau\s+fini)\b", re.I)


def lire_niveaux(phrases: list[Phrase]) -> list[tuple[str, Phrase]]:
    """Titres de vue (« PLAN RDC », « R+1 »…). « Vide sur RDC » ou « vers R+1 » ne sont pas des titres."""
    out = []
    for p in phrases:
        if p.sens == "ltr" and not RE_PAS_TITRE.search(p.texte):
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
    tag_l: str = "lu"
    src_l: str = "étiquette (cm)"
    tag_h: str = "lu"
    src_h: str = "étiquette (cm)"


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
    """Pièces étiquetées « Nom / 12.3 m² » : la surface peut partager sa phrase avec d'autres mots (« Dgt 12 m2 »)."""
    out = []
    for p in phrases:
        for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s*m[²2](?![\w³])", p.texte):
            s = float(m.group(1).replace(",", "."))
            if not 0.5 <= s <= 300:
                continue
            avant = p.texte[: m.start()].strip()
            nom = avant if re.search(r"[A-Za-zÀ-ÿ]{2,}", avant) and not RE_SURFACE.search(avant) else None
            if nom is None:
                h = max(p.hauteur_ligne, 3.0)
                ph = _voisine(p, phrases, -2.6 * h, -0.4 * h, 30,
                              lambda q: not re.search(r"\d\s*m[²2]", q.texte) and not RE_DIMS.search(q.texte)
                              and re.search(r"[A-Za-zÀ-ÿ]{2,}", q.texte) is not None)
                nom = ph.texte if ph else None
            out.append({"nom": nom, "surface_m2": s, "x": p.cx, "y": p.cy})
    return out


# --------------------------------------------------------------------------- légende, dimensions par type, hauteurs, nord écrit

import unicodedata as _ud


def sans_accents(t: str) -> str:
    return _ud.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _nb(t: str) -> float:
    return float(t.replace(",", "."))


def lire_legende(phrases: list[Phrase], pastilles: list[tuple[tuple, tuple]]) -> dict:
    """Légende couleur → texte : petites pastilles colorées suivies d'un libellé sur la même ligne.
    ``pastilles`` : [((x0, top, x1, bottom), couleur)]."""
    out = {}
    for (x0, t, x1, b), c in pastilles:
        cy = (t + b) / 2
        cand = [p for p in phrases if p.sens == "ltr" and abs(p.cy - cy) < 6 and 0 <= p.x0 - x1 < 30]
        if cand:
            p = min(cand, key=lambda p: p.x0 - x1)
            out.setdefault(c, p.texte.strip())
    return out


RE_TYPE_DIMS = re.compile(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{2,40}?)\s*:?\s*(\d+[.,]\d+)\s*[×x]\s*(\d+[.,]\d+)\s*m\b")


def lire_dimensions_types(texte: str) -> list[dict]:
    """« fenêtres 1,23 × 1,48 m, porte vitrée 1,80 × 2,20 m » → [{nom, largeur, hauteur}]."""
    out = []
    for m in RE_TYPE_DIMS.finditer(texte):
        mots = re.split(r"[:,;·]", m.group(1))[-1].strip()
        out.append({"nom": mots, "largeur_m": _nb(m.group(2)), "hauteur_m": _nb(m.group(3))})
    return out


def correspond(libelle_legende: str, nom_type: str) -> bool:
    """« Fenêtre F » ↔ « fenêtres » ; « Porte vitrée PV » ↔ « porte vitrée »."""
    a = [w.rstrip("s") for w in re.findall(r"[a-z]{3,}", sans_accents(libelle_legende))]
    b = [w.rstrip("s") for w in re.findall(r"[a-z]{3,}", sans_accents(nom_type))]
    return bool(b) and all(w in a for w in b)


RE_METRE = re.compile(r"(?<![\d,.])(\d{1,3}[.,]\d{1,2})\s*m(?![²2³3a-zA-Z])")


def valeurs_metriques(texte: str) -> list[float]:
    """Longueurs écrites en mètres (« 16,00 m », « 15,12 × 8,12 m »), sans les surfaces (m²)."""
    vals = [_nb(x) for x in RE_METRE.findall(texte)]
    for m in re.finditer(r"(\d{1,3}[.,]\d{1,2})\s*[×x]\s*(\d{1,3}[.,]\d{1,2})\s*m(?![²2])", texte):
        vals += [_nb(m.group(1)), _nb(m.group(2))]
    return sorted({v for v in vals if 0.3 <= v <= 200})


RE_H_ETAGE = re.compile(r"hauteur\s+d['’]\s*[ée]tage\s*:?\s*(\d+[.,]\d+)\s*m", re.I)
RE_HSP = re.compile(r"(?:hauteur\s+sous\s+plafond|HSP)\s*:?\s*(\d+[.,]\d+)\s*m", re.I)


def lire_hauteurs(texte: str) -> dict:
    out = {}
    if (m := RE_H_ETAGE.search(texte)):
        out["hauteur_etage_m"] = _nb(m.group(1))
    if (m := RE_HSP.search(texte)):
        out["hsp_m"] = _nb(m.group(1))
    return out


FLECHES = {"↑": 0.0, "⬆": 0.0, "↗": 45.0, "→": 90.0, "➡": 90.0, "↘": 135.0, "↓": 180.0, "⬇": 180.0,
           "↙": -135.0, "←": -90.0, "⬅": -90.0, "↖": -45.0}


def lire_nord_texte(texte: str) -> float | None:
    """« NORD ↑ » → 0° (nord vers le haut de la feuille)."""
    m = re.search(r"\b(?:nord|N)\s*([↑⬆↗→➡↘↓⬇↙←⬅↖])", texte, re.I)
    return FLECHES[m.group(1)] if m else None


def famille(nom: str | None) -> str:
    """Famille d'une baie pour la rapprocher d'une notice : « F1 » → « F », « PF12b » → « PF », « Mext21 » → « MEXT »."""
    return re.sub(r"\d+[A-Z]?$", "", (nom or "").upper().strip())


def meme_repere(nom_plan: str | None, repere: str) -> bool:
    n, r = (nom_plan or "").upper().strip(), repere.upper().strip()
    return n == r or famille(n) == r
