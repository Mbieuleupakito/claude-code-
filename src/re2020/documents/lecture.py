"""Lecture de tout le texte et de tous les tableaux d'un dossier PDF : chaque donnée trouvée devient une
valeur « lu » avec sa page source. Les tableaux sont reconnus par leurs en-têtes, pas par leur position,
pour s'adapter aux notices de différents bureaux.

Ce qui est cherché :
- infos générales (usage, zone climatique, altitude, date de dépôt du PC, Q4, occupants, adresse) ;
- parois opaques (Up, composition, R des isolants) ;
- menuiseries (Uw / Ud / Urc, g, TL, dimensions, quantités) ;
- ponts thermiques (Ψ, linéaires, ΣΨ·L) ;
- tableaux de baies (façade, niveau, repère, dimensions, allège), de locaux, de bilan des façades,
  surfaces de référence (Sref…) ;
- ventilation, chauffage, ECS, éclairage, production locale ; hauteurs (HSP, hauteur d'étage).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pdfplumber

from .. import ocr
from ..catalogues.db import type_paroi
from ..localisation import candidats as candidats_lieu
from ..plans.textes import lire_hauteurs
from ..trace import val


def _sa(t: str | None) -> str:
    """Minuscules sans accents, espaces normalisés."""
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _nb(t: str | None) -> float | None:
    if not t:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", t.replace(" ", "").replace(" ", "") if re.fullmatch(r"[\d\s,. ]+", t.strip()) else t)
    return float(m.group(0).replace(",", ".")) if m else None


def _cellule(t: str | None) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\n", " ")).strip()


class _Lecteur:
    def __init__(self):
        self.d: dict = {"infos": {}, "parois": [], "menuiseries": [], "ponts_thermiques": {"liaisons": []},
                        "baies": [], "locaux": [], "bilan_facades": [], "surfaces": {}, "ventilation": {},
                        "chauffage": {}, "ecs": {}, "eclairage": {}, "hauteurs": {}, "pages_lues": [],
                        "localisation_candidats": [], "cotes_ngf": [], "dates": []}

    def lu(self, valeur, source, unite=None, conf="haute", **extra):
        return val(valeur, "lu", source, conf, unite, **extra)

    # ------------------------------------------------------------------ tableaux
    MOTS_ENTETE = ("ref", "repere", "designation", "liaison", "facade", "niveau", "local", "surface", "composition",
                   "performance", "vitrage", "quantite", "allege", "longueur", "hauteur", "element", "valeur", "psi", "ψ")

    def _est_entete(self, r: list[str]) -> bool:
        cellules = [_sa(c) for c in r if c]
        return sum(1 for c in cellules if any(c.replace(" ", "").startswith(m) for m in self.MOTS_ENTETE)) >= 2 \
            and not any(re.search(r"\d", c) for c in cellules)

    def tableau(self, t: list[list], src: str):
        """Découpe d'abord les tableaux accolés (une ligne d'en-tête au milieu = nouveau tableau)."""
        lignes = [r for r in t if r and any(c for c in r)]
        segment: list[list] = []
        for r in lignes:
            if segment and self._est_entete([_cellule(c) for c in r if c]):
                self._tableau(segment, src)
                segment = []
            segment.append(r)
        if segment:
            self._tableau(segment, src)

    def _tableau(self, t: list[list], src: str):
        # colonnes vides retirées (cellules fusionnées)
        n = max(len(r) for r in t)
        garder = [j for j in range(n) if any(j < len(r) and r[j] not in (None, "") for r in t)]
        lignes = [[_cellule(r[j] if j < len(r) else "") for j in garder] for r in t]
        if len(lignes) < 2:
            return
        tete = [_sa(c) for c in lignes[0]]
        h = " | ".join(tete) + " | " + " | ".join(c.replace(" ", "") for c in tete)  # en-têtes coupés (« Repè re »)
        if len(tete) == 2 and not any(k in h for k in ("liaison", "facade", "local")):
            self._cle_valeur(lignes, src)
        elif "liaison" in h and ("ψ" in lignes[0][1].lower() or "psi" in h or "w/(m.k)" in h):
            self._ponts(lignes, src)
        elif "facade" in h and "repere" in h:
            self._baies(lignes, src)
        elif "facade" in h and "brute" in h:
            self._bilan(lignes, src)
        elif "local" in h and "surface" in h:
            self._locaux(lignes, src)
        elif "repere" in h and ("performance" in h or "vitrage" in h or "uw" in h):
            self._menuiseries(lignes, src)
        elif ("up" in h or "u " in h or "w/(" in h) and ("designation" in h or "composition" in h):
            self._parois(lignes, src)

    def _cle_valeur(self, lignes, src):
        for cle, v in lignes:
            k = _sa(cle)
            I, S = self.d["infos"], self.d["surfaces"]
            if not v:
                continue
            if k.startswith("usage"):
                I["usage"] = self.lu(v, src)
            elif "zone climatique" in k:
                if (m := re.search(r"\bH[123][a-d]?\b", v, re.I)):
                    I["zone"] = self.lu(m.group(0)[:2].upper() + m.group(0)[2:].lower(), src)
                if "altitude" in k and (m := re.search(r"(\d+)\s*m\b", v)):
                    I["altitude_m"] = self.lu(float(m.group(1)), src, "m", note="fictive" if "fictiv" in _sa(v) else None)
            elif k.startswith("altitude") and (m := re.search(r"(\d+)\s*m\b", v)):
                I["altitude_m"] = self.lu(float(m.group(1)), src, "m")
            elif "depot" in k and "pc" in k:
                if (m := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)):
                    I["date_pc"] = self.lu(f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", src)
                elif (m := re.search(r"\b(20\d\d)\b", v)):
                    I["date_pc"] = self.lu(f"{m.group(1)}-01-01", src, conf="moyenne",
                                           note=f"année seule lue (« {v} ») : date exacte à confirmer")
            elif re.fullmatch(r"q4( ?pa)?( surf)?", k) or k.startswith("permeabilite"):
                I["q4"] = self.lu(_nb(v), src, "m³/(h.m²)")
            elif "occupant" in k:
                I["occupants"] = self.lu(_nb(v), src)
            elif k.startswith(("adresse", "commune", "localisation", "lieu", "situation")):
                I.setdefault("adresse", self.lu(v, src))
                self.d["localisation_candidats"] += candidats_lieu(f"adresse du projet : {v}", src, 3.0)
            elif "bruit" in k:
                I["exposition_bruit"] = self.lu(v, src)
            elif "emprise" in k:
                I["emprise_m2"] = self.lu(_nb(v), src, "m²")
            elif k.startswith("sref"):
                S["sref"] = self.lu(_nb(v), src, "m²")
            elif "surface par niveau" in k:
                S["surface_par_niveau"] = self.lu(_nb(v), src, "m²")
            elif "murs bruts" in k:
                nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", v)]
                if len(nums) >= 2:
                    S["murs_bruts"] = self.lu(nums[0], src, "m²")
                    S["murs_nets"] = self.lu(nums[1], src, "m²")
            elif "plancher bas" in k and "toiture" in k:
                S["plancher_bas"] = self.lu(_nb(v), src, "m²")
                S["toiture"] = self.lu(_nb(v), src, "m²")
            elif "surface utile" in k and _nb(v):
                S["surface_utile"] = self.lu(_nb(v), src, "m²")
            elif "shab" in k and _nb(v):
                S["shab"] = self.lu(_nb(v), src, "m²")

    def _parois(self, lignes, src):
        tete = [_sa(c) for c in lignes[0]]
        iu = next(i for i, c in enumerate(tete) if c.startswith("up") or c.startswith("u ") or "w/(" in c)
        ides = next((i for i, c in enumerate(tete) if "designation" in c), 1)
        icomp = next((i for i, c in enumerate(tete) if "composition" in c), None)
        ir = next((i for i, c in enumerate(tete) if c.startswith("r ") or c.startswith("r des")), None)
        for r in lignes[1:]:
            des = r[ides]
            up = _nb(r[iu]) if re.search(r"\d", r[iu]) else None
            comp = r[icomp] if icomp is not None else ""
            couches = [{"materiau": m.group(1).strip(" ,;"), "epaisseur_mm": float(m.group(2)),
                        **({"lambda": float(m.group(3).replace(",", "."))} if m.group(3) else {})}
                       for m in re.finditer(r"([A-Za-zÀ-ÿ'’][A-Za-zÀ-ÿ'’ ]{1,40}?)\s+(\d+)\s*mm(?:\s*,\s*λ\s*=\s*(\d+[.,]\d+))?", comp)]
            self.d["parois"].append({
                "ref": r[0], "designation": des, "type_paroi": type_paroi(des),
                "Up": self.lu(up, src, "W/m².K", note="Up global (ponts intégrés compris)") if up is not None else None,
                "composition": comp, "couches": couches, "R_isolants": r[ir] if ir is not None else ""})

    def _menuiseries(self, lignes, src):
        for r in lignes[1:]:
            txt = " ; ".join(r)
            code = r[0]
            dims = re.search(r"(\d+[.,]\d+)\s*[×x]\s*(\d+[.,]\d+)", txt)
            u = re.search(r"\b(U[wdr]c?)\s*(?:moyen)?\s*[≤<=]*\s*(\d+[.,]\d+)", txt)
            g = re.search(r"\bg\s*[≥>=]+\s*(\d+[.,]\d+)", txt)
            tl = re.search(r"\bTL\s*[≥>=]+\s*(\d+)\s*%", txt)
            q = re.search(r"(\d+)\s*\((\d+[.,]\d+)\s*m²\)", r[-1])
            self.d["menuiseries"].append({
                "repere": code, "designation": r[1] if len(r) > 1 else "", "texte": txt,
                "largeur_m": self.lu(float(dims.group(1).replace(",", ".")), src, "m") if dims else None,
                "hauteur_m": self.lu(float(dims.group(2).replace(",", ".")), src, "m") if dims else None,
                "U": self.lu(float(u.group(2).replace(",", ".")), src, "W/m².K", grandeur=u.group(1)) if u else None,
                "g": self.lu(float(g.group(1).replace(",", ".")), src) if g else None,
                "TL": self.lu(float(tl.group(1)) / 100, src) if tl else None,
                "quantite": self.lu(int(q.group(1)), src) if q else None,
                "surface_m2": self.lu(float(q.group(2).replace(",", ".")), src, "m²") if q else None,
                "opaque": bool(re.search(r"\bUd\b|porte pleine", txt, re.I)),
                "toiture": bool(re.search(r"Urc|lanterneau|fen[eê]tre de toit|velux", txt, re.I)),
            })

    def _ponts(self, lignes, src):
        P = self.d["ponts_thermiques"]
        for r in lignes[1:]:
            nom = r[0]
            if _sa(nom).startswith("total"):
                P["total_W_K"] = self.lu(_nb(r[-1]), src, "W/K")
                continue
            psi, L, pl = (_nb(r[1]), _nb(r[2]) if len(r) > 2 else None, _nb(r[3]) if len(r) > 3 else None)
            if psi is None:
                continue
            P["liaisons"].append({"liaison": nom, "psi": self.lu(psi, src, "W/m.K"),
                                  "longueur_m": self.lu(L, src, "m") if L is not None else None,
                                  "psi_L": self.lu(pl if pl is not None else (psi * L if L else None), src, "W/K")})
        if "total_W_K" not in P and P["liaisons"]:
            tot = sum((l["psi_L"]["valeur"] or 0) for l in P["liaisons"])
            P["total_W_K"] = val(round(tot, 2), "déduit", f"Σ Ψ·L du tableau ({src})", "haute", "W/K")

    def _baies(self, lignes, src):
        tete = [_sa(c) for c in lignes[0]]
        idx = {k: next((i for i, c in enumerate(tete) if k in c), None) for k in ("facade", "niveau", "repere", "position", "largeur", "allege")}
        for r in lignes[1:]:
            dims = re.search(r"(\d+[.,]\d+)\s*[×x]\s*(\d+[.,]\d+)", r[idx["largeur"]] if idx["largeur"] is not None else "")
            al = r[idx["allege"]] if idx["allege"] is not None else ""
            self.d["baies"].append({
                "facade": r[idx["facade"]], "niveau": r[idx["niveau"]] if idx["niveau"] is not None else "",
                "repere": r[idx["repere"]] if idx["repere"] is not None else "",
                "position": r[idx["position"]] if idx["position"] is not None else "",
                "largeur_m": self.lu(float(dims.group(1).replace(",", ".")), src, "m") if dims else None,
                "hauteur_m": self.lu(float(dims.group(2).replace(",", ".")), src, "m") if dims else None,
                "allege_m": self.lu(_nb(al), src, "m") if re.search(r"\d", al) else None})

    def _bilan(self, lignes, src):
        tete = [_sa(c) for c in lignes[0]]
        col = lambda k: next((i for i, c in enumerate(tete) if k in c), None)
        for r in lignes[1:]:
            ligne = {"facade": r[0]}
            for k, nom in (("longueur", "longueur_int_m"), ("hauteur", "hauteur_m"), ("brute", "brut_m2"), ("baies", "baies_m2"), ("nette", "net_m2")):
                i = col(k)
                if i is not None and _nb(r[i]) is not None:
                    ligne[nom] = self.lu(_nb(r[i]), src)
            self.d["bilan_facades"].append(ligne)

    def _locaux(self, lignes, src):
        tete = [_sa(c) for c in lignes[0]]
        isurf = next(i for i, c in enumerate(tete) if "surface" in c)
        for r in lignes[1:]:
            s = _nb(r[isurf])
            if s is None:
                continue
            self.d["locaux"].append({"local": r[0], "surface_m2": self.lu(s, src, "m²"), "total": _sa(r[0]).startswith("total")})

    # ------------------------------------------------------------------ texte libre
    section = ""

    def texte(self, t: str, src: str):
        s = _sa(t)
        if (m := re.match(r"\s*\d+\.\s+([a-z ,']+)", s)):
            self.section = m.group(1)
        V, C, E, L = self.d["ventilation"], self.d["chauffage"], self.d["ecs"], self.d["eclairage"]
        if "ventilation" in self.section or "ventilation" in s or "vmc" in s or "cta" in s or "flux" in s:
            if "double flux" in s and "type" not in V:
                V["type"] = self.lu("double flux", src)
            elif ("simple flux" in s or "vmc" in s) and "type" not in V:
                V["type"] = self.lu("simple flux hygro B" if "hygro b" in s else "simple flux", src)
            if "debit_m3h" not in V and (m := re.search(r"(\d{2,5})\s*m[³3]/h", t)) and "double flux" in s:
                V["debit_m3h"] = self.lu(float(m.group(1)), src, "m³/h")
            if "rendement" not in V and (m := re.search(r"rendement (?:thermique )?(?:de )?(\d{2})\s*%", s)):
                V["rendement"] = self.lu(int(m.group(1)) / 100, src)
            if "puissance_Wh_m3" not in V and (m := re.search(r"(\d+[.,]\d+)\s*Wh/m[³3]", t)):
                V["puissance_Wh_m3"] = self.lu(float(m.group(1).replace(",", ".")), src, "Wh/m³")
            if "horaires" not in V and (m := re.search(r"de (\d{1,2}) ?h a (\d{1,2}) ?h", s)):
                jours = 5 if "lundi au vendredi" in s else 7
                V["horaires"] = self.lu(f"{m.group(1)} h – {m.group(2)} h, {jours} j/7", src)
                V["fraction_fonctionnement"] = val(round((int(m.group(2)) - int(m.group(1))) * jours / 168, 3), "déduit",
                                                   f"horaires lus ({src})", "haute")
        if ("chauffage" in s or "chauffage" in self.section) and "generateur" not in C:
            for cle, nom in (("reseau de chaleur", "réseau de chaleur urbain"), ("pompe a chaleur", "pompe à chaleur"),
                             ("pac ", "pompe à chaleur"), ("chaudiere", "chaudière"), ("granule", "bois granulés"),
                             ("effet joule", "effet Joule"), ("radiateurs electriques", "effet Joule")):
                if cle in s:
                    C["generateur"] = self.lu(nom, src)
                    break
            if (m := re.search(r"emission par ([a-z ]+?)(?:,|\.| a | regime)", s)):
                C["emetteurs"] = self.lu(m.group(1).strip(), src)
            if (m := re.search(r"regime (\d{2}) ?/ ?(\d{2})", s)):
                C["regime"] = self.lu(f"{m.group(1)}/{m.group(2)} °C", src)
        if "ecs" in s and "type" not in E:
            for cle, nom in (("thermodynamique", "chauffe-eau thermodynamique"), ("double service", "PAC double service"),
                             ("solaire", "chauffe-eau solaire"), ("ballon electrique", "ballon électrique (effet Joule)"),
                             ("cumulus", "ballon électrique (effet Joule)")):
                if cle in s:
                    E["type"] = self.lu(nom, src)
                    if (m := re.search(r"(\d{2,4})\s*l\b", s)):
                        E["volume_l"] = self.lu(float(m.group(1)), src, "L")
                    if "usage faible" in s:
                        E["usage"] = self.lu("faible", src)
                    break
        if "eclairage" in s and "puissances_W_m2" not in L:
            p = [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*W/m²", t)]
            if p:
                L["puissances_W_m2"] = self.lu(p, src, "W/m²")
                L["detection_presence"] = self.lu("detection de presence" in s, src)
        if "production locale" in s and "production_locale" not in self.d["infos"]:
            m = re.search(r"production locale[^:]*:\s*([^.(]+)", t, re.I)
            if m:
                self.d["infos"]["production_locale"] = self.lu(m.group(1).strip(), src)
        for m in re.finditer(r"\b(\d{2})/(\d{2})/(20\d{2})\b", t):
            if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
                self.d["dates"].append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", src))
        for m in re.finditer(r"NGF\s*:?\s*\+?\s*(\d{1,4}[.,]\d{1,3})", t):
            z = float(m.group(1).replace(",", "."))
            if -10 < z < 4800:
                self.d["cotes_ngf"].append((z, src))
        h = lire_hauteurs(t)
        for k, v in h.items():
            self.d["hauteurs"].setdefault(k, self.lu(v, src, "m"))


def _lire_pdf(lect: _Lecteur, ch: Path):
    with pdfplumber.open(ch) as pdf:
        pages = [(i, p, p.extract_text() or "") for i, p in enumerate(pdf.pages)]
        # la notice (données du projet) passe avant les autres pages (exercices, annexes) qui pourraient la contredire
        pages.sort(key=lambda x: (0 if re.search(r"notice|cctp|descriptif", x[2], re.I) else 1, x[0]))
        for i, p, txt in pages:
            src = f"{ch.name} p.{i + 1}"
            _lire_bloc(lect, src, p.extract_tables(), txt)
            # cartouche / titres dessinés en traits : OCR local, case par case (chantier, architecte, maître d'ouvrage…)
            for bloc in ocr.blocs(ocr.textes_page(p)):
                lect.d["localisation_candidats"] += candidats_lieu(bloc.replace("\n", " · "), src + " (OCR)", 1.2)
                for m in re.finditer(r"\b(\d{2})/(\d{2})/(20\d{2})\b", bloc):
                    lect.d["dates"].append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", src + " (OCR)"))


def _lire_bloc(lect: _Lecteur, src: str, tableaux: list, txt: str):
    lect.section = ""
    poids = 1.5 if re.search(r"notice|rset|cctp|descriptif|attestation", txt, re.I) else 1.0
    lect.d["localisation_candidats"] += candidats_lieu(txt, src, poids)
    n_avant = len(str(lect.d))
    for t in tableaux:
        lect.tableau(t, src)
    # texte libre, paragraphe par paragraphe (puces, lignes vides)
    for bloc in re.split(r"\n(?=\(cid:127\)|•|-\s|\d+\.\s)", txt):
        lect.texte(bloc.replace("(cid:127)", "").replace("\n", " "), src)
    if len(str(lect.d)) > n_avant:
        lect.d["pages_lues"].append(src)


def _lire_docx(lect: _Lecteur, ch: Path):
    import docx

    d = docx.Document(str(ch))
    tableaux = [[[c.text for c in r.cells] for r in t.rows] for t in d.tables]
    texte = "\n".join(p.text for p in d.paragraphs)
    _lire_bloc(lect, ch.name, tableaux, texte)


def _lire_xlsx(lect: _Lecteur, ch: Path):
    import openpyxl

    wb = openpyxl.load_workbook(str(ch), data_only=True, read_only=True)
    for ws in wb.worksheets:
        lignes = [["" if v is None else (f"{v:g}".replace(".", ",") if isinstance(v, float) else str(v)) for v in r]
                  for r in ws.iter_rows(values_only=True)]
        tableaux, cour = [], []
        for r in lignes + [[]]:  # une ligne vide sépare deux tableaux
            if any(c.strip() for c in r):
                cour.append(r)
            elif cour:
                tableaux.append(cour)
                cour = []
        texte = "\n".join(" ".join(c for c in r if c) for r in lignes)
        _lire_bloc(lect, f"{ch.name} ({ws.title})", tableaux, texte)


def _lire_odt(lect: _Lecteur, ch: Path):
    """OpenDocument (.odt/.ods, LibreOffice) : tableaux + texte. Un rapport d'étude Pléiades exporté en .odt
    apporte en plus ses compositions de parois couche par couche (Up « lu »)."""
    import zipfile
    import xml.etree.ElementTree as ET

    from ..pleiades import compositions, texte_odt

    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0", "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    racine = ET.fromstring(zipfile.ZipFile(ch).read("content.xml"))
    tableaux = []
    for t in racine.iter(f"{{{ns['table']}}}table"):
        lignes = [[" ".join("".join(p.itertext()) for p in c.iter(f"{{{ns['text']}}}p"))
                   for c in r.iter(f"{{{ns['table']}}}table-cell")] for r in t.iter(f"{{{ns['table']}}}table-row")]
        if lignes:
            tableaux.append(lignes)
    texte = texte_odt(ch)
    _lire_bloc(lect, ch.name, tableaux, texte.replace(" | ", " "))
    for c in compositions(texte):
        if c["Up_pleiades"] is None or c["nature"] in (None, "Autre", "Non définie"):
            continue
        des = f"{c['nom']} ({c['nature']})"
        lect.d["parois"].append({
            "ref": c["nom"], "designation": des, "type_paroi": {"Paroi verticale": "mur_ext", "Plancher haut": "plafond",
                                                                   "Plancher bas": "plancher_bas"}.get(c["type_paroi"], type_paroi(des)),
            "Up": lect.lu(c["Up_pleiades"], f"{ch.name} (bibliothèque Pléiades)", "W/m².K", note="Up indicatif Pléiades"),
            "composition": " + ".join(f"{x['materiau']} {x['epaisseur_cm']:g} cm" for x in c["couches"]),
            "couches": [{"materiau": x["materiau"], "epaisseur_mm": x["epaisseur_cm"] * 10, "lambda": x["lambda_W_mK"]}
                        for x in c["couches"]],
            "R_isolants": ""})


def _lire_texte(lect: _Lecteur, ch: Path):
    import csv

    brut = ch.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = brut.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    tableaux = []
    if ch.suffix.lower() == ".csv":
        sep = ";" if texte.count(";") > texte.count(",") else ","
        tableaux = [list(csv.reader(texte.splitlines(), delimiter=sep))]
    _lire_bloc(lect, ch.name, tableaux, texte)


LECTEURS = {".pdf": _lire_pdf, ".docx": _lire_docx, ".odt": _lire_odt, ".ods": _lire_odt, ".xlsx": _lire_xlsx, ".xlsm": _lire_xlsx, ".txt": _lire_texte, ".csv": _lire_texte}


def lire_dossier(chemins) -> dict:
    """Lit tous les tableaux et tout le texte des documents donnés (PDF, Word, Excel, texte).
    Retourne un dict de valeurs « lu » (avec le fichier et la page source)."""
    lect = _Lecteur()
    chemins = [Path(c) for c in (chemins if isinstance(chemins, (list, tuple)) else [chemins])]
    for ch in chemins:
        lecteur = LECTEURS.get(ch.suffix.lower())
        if lecteur:
            lecteur(lect, ch)
    d = lect.d
    # altitude du terrain : cotes NGF des plans (« NGF: +161,00 ») → groupe le plus bas, valeur la plus fréquente
    if d["cotes_ngf"] and "altitude_m" not in d["infos"]:
        zs = [z for z, _ in d["cotes_ngf"]]
        bas = [z for z in zs if z <= min(zs) + 1.0]
        compte: dict[float, int] = {}
        for z in bas:
            compte[round(z, 1)] = compte.get(round(z, 1), 0) + 1
        z0 = max(compte, key=lambda z: (compte[z], -z))
        srcs = sorted({src for z, src in d["cotes_ngf"] if round(z, 1) == z0})
        d["infos"]["altitude_m"] = val(round(z0), "lu", f"cote NGF du rez-de-chaussée (+{z0:.2f} m) lue sur {', '.join(srcs[:3])}",
                                       "haute" if compte[z0] >= 2 else "moyenne", "m",
                                       note=f"{len(zs)} cotes NGF lues ; altitude du terrain ≈ niveau du rez-de-chaussée")
    # usage : résidentiel ou tertiaire
    u = _sa(d["infos"].get("usage", {}).get("valeur"))
    if u:
        d["infos"]["residentiel"] = val(bool(re.search(r"maison|logement|habitation|residen", u)), "déduit", "usage lu", "haute")
    return d
