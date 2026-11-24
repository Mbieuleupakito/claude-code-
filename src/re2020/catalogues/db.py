"""Chargement des catalogues JSON de ``data/catalogues`` dans SQLite et recherches.

Tables : materiaux, compositions, couches, psi, isolants, menuiseries, systemes.
La base est reconstruite depuis les JSON (source de vérité versionnée) ; le fichier SQLite est local.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import unicodedata
from pathlib import Path

from ..trace import val
from .parois import RSI_RSE, est_isolant, u_paroi

DOSSIER_DATA = Path(__file__).resolve().parents[3] / "data" / "catalogues"

SCHEMA = """
CREATE TABLE materiaux (nom TEXT PRIMARY KEY, cle TEXT, categorie TEXT, lambda REAL, r REAL, masse_vol REAL,
                        cp REAL, certifie INTEGER, tag TEXT, source TEXT);
CREATE TABLE compositions (id INTEGER PRIMARY KEY, nom TEXT, categorie TEXT, type_paroi TEXT, up_pleiades REAL,
                           epaisseur_cm REAL);
CREATE TABLE couches (composition_id INTEGER, ordre INTEGER, materiau TEXT, epaisseur_cm REAL, source TEXT);
CREATE TABLE psi (liaison TEXT, variante TEXT, isolation TEXT, valeur REAL, source TEXT);
CREATE TABLE isolants (nom TEXT PRIMARY KEY, lambda REAL, certifie INTEGER, usages TEXT, prix_eur_m2_cm REAL);
CREATE TABLE menuiseries (nom TEXT PRIMARY KEY, uw REAL, sw REAL, prix_eur_m2 REAL);
CREATE TABLE systemes (nom TEXT PRIMARY KEY, data TEXT);
"""

# Ψ par défaut (W/m.K) lus dans le RSET Charleville (Th-Bât 2026, valeurs tabulées, ITE maçonnerie)
PSI_RSET_ITE = {
    "plancher_bas_mur": 0.60, "plancher_intermediaire_mur": 0.05, "plancher_haut_mur": 0.05, "refend_mur": 0.03,
    "angle_saillant": 0.05, "angle_rentrant": 0.03, "menuiserie_sans_retour": 0.62, "menuiserie_avec_retour": 0.15,
}
# Ψ par défaut en ITI maçonnerie : table Th-Bât (catalogue_psi_th_bat.json) ou valeur supposée
PSI_ITI = {
    "plancher_bas_mur": (0.18, "Th-Bât l.5 isolé sous chape, ITI maçonnerie"),
    "plancher_intermediaire_mur": (0.96, "Th-Bât l.22 béton, ITI maçonnerie"),
    "plancher_haut_mur": (0.07, "Th-Bât l.31 plafond léger, ITI maçonnerie"),
    "refend_mur": (0.60, "SUPPOSÉ (refend béton en ITI, absent de la table)"),
    "angle_saillant": (0.02, "Th-Bât l.38, ITI maçonnerie"),
    "angle_rentrant": (0.18, "Th-Bât l.37, ITI maçonnerie"),
    "menuiserie_sans_retour": (0.05, "SUPPOSÉ (menuiserie au nu intérieur en ITI)"),
    "menuiserie_avec_retour": (0.05, "SUPPOSÉ (menuiserie au nu intérieur en ITI)"),
}


def cle(nom: str) -> str:
    """Clé de rapprochement des noms de matériaux (sans accents, ponctuation, parenthèses)."""
    n = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\(.*?\)", " ", n)
    return re.sub(r"[^a-z0-9.]+", " ", n).strip()


def type_paroi(nom: str) -> str:
    n = cle(nom)
    if "cloison" in n:
        return "cloison"
    if "plancher bas" in n:
        return "plancher_bas"
    if "plancher" in n:
        return "plancher_interm"
    if "plafond" in n or "toiture" in n or "comble perdu" in n or "rampant" in n:
        return "plafond"
    if "garage" in n or "lnc" in n or "non chauffe" in n:
        return "mur_lnc"
    return "mur_ext"


class Catalogue:
    def __init__(self, chemin_db: str | Path = ":memory:", dossier: Path = DOSSIER_DATA):
        self.dossier = Path(dossier)
        self.cx = sqlite3.connect(str(chemin_db), check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self._charger()

    # ------------------------------------------------------------------ chargement
    def _json(self, nom):
        return json.loads((self.dossier / nom).read_text(encoding="utf-8"))

    def _charger(self):
        cx = self.cx
        for t in ("materiaux", "compositions", "couches", "psi", "isolants", "menuiseries", "systemes"):
            cx.execute(f"DROP TABLE IF EXISTS {t}")
        cx.executescript(SCHEMA)
        for m in self._json("materiaux_generiques.json")["materiaux"]:
            self._ajout_mat(m, "générique", m.get("tag", "supposé"), m.get("source", ""))
        for m in self._json("catalogue_materiaux_perso.json"):
            self._ajout_mat(m, m.get("categorie", ""), "lu", "matériau perso Pléiades")
        for i, c in enumerate(self._json("catalogue_compositions.json")):
            cx.execute("INSERT INTO compositions VALUES (?,?,?,?,?,?)",
                       (i, c["nom"].strip(), c.get("categorie"), type_paroi(c["nom"]), c.get("UpIndic_pleiades"), c.get("epaisseur_totale_cm")))
            for j, co in enumerate(c["couches"]):
                cx.execute("INSERT INTO couches VALUES (?,?,?,?,?)", (i, j, co["materiau"], co["epaisseur_cm"], co.get("source")))
        psi = self._json("catalogue_psi_th_bat.json")
        for liaison, t in psi.items():
            if not isinstance(t, dict) or not t.get("colonnes"):
                continue
            for variante, vals in t["lignes"].items():
                for iso, v in zip(t["colonnes"], vals):
                    cx.execute("INSERT INTO psi VALUES (?,?,?,?,?)", (liaison, variante, iso, v, "Th-Bât (catalogue_psi_th_bat.json)"))
        prod = self._json("produits.json")
        for p in prod["isolants"]:
            cx.execute("INSERT INTO isolants VALUES (?,?,?,?,?)",
                       (p["nom"], p["lambda_W_mK"], int(p["certifie"]), ",".join(p["usages"]), p.get("prix_eur_m2_cm")))
        for p in prod["menuiseries"]:
            cx.execute("INSERT INTO menuiseries VALUES (?,?,?,?)", (p["nom"], p["Uw"], p["Sw"], p.get("prix_eur_m2")))
        for p in prod["systemes"]:
            cx.execute("INSERT INTO systemes VALUES (?,?)", (p["nom"], json.dumps(p, ensure_ascii=False)))
        cx.commit()

    def _ajout_mat(self, m, categorie, tag, source):
        c = m.get("certifie")
        self.cx.execute("INSERT OR REPLACE INTO materiaux VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (m["nom"], cle(m["nom"]), categorie, m.get("lambda_W_mK"), m.get("R_m2K_W"), m.get("masse_vol_kg_m3"),
                         m.get("chaleur_massique_J_kgK"), None if c is None else int(c), tag, source))

    # ------------------------------------------------------------------ matériaux
    def materiau(self, nom: str) -> dict | None:
        """Recherche exacte, puis par clé normalisée, puis par préfixe (« Polyuréthane TMS 0.020 » → nom long)."""
        k = cle(nom)
        rows = self.cx.execute("SELECT * FROM materiaux").fetchall()
        for test in (lambda r: r["nom"] == nom, lambda r: r["cle"] == k,
                     lambda r: r["cle"].startswith(k) or k.startswith(r["cle"])):
            hits = [r for r in rows if test(r)]
            if hits:
                r = min(hits, key=lambda r: len(r["nom"]))
                return {"nom": r["nom"], "lambda_W_mK": r["lambda"], "R_m2K_W": r["r"], "masse_vol_kg_m3": r["masse_vol"],
                        "certifie": None if r["certifie"] is None else bool(r["certifie"]), "tag": r["tag"], "source": r["source"]}
        return None

    # ------------------------------------------------------------------ compositions
    def compositions(self, type_p: str | None = None) -> list[dict]:
        q = "SELECT * FROM compositions" + (" WHERE type_paroi=?" if type_p else "") + " ORDER BY id"
        return [self.composition(r["id"]) for r in self.cx.execute(q, (type_p,) if type_p else ())]

    def composition(self, ident) -> dict:
        r = self.cx.execute("SELECT * FROM compositions WHERE id=? OR nom=?", (ident, ident)).fetchone()
        if r is None:
            raise KeyError(ident)
        couches = self.cx.execute("SELECT * FROM couches WHERE composition_id=? ORDER BY ordre", (r["id"],)).fetchall()
        mats, manquants = [], []
        for c in couches:
            m = self.materiau(c["materiau"])
            if m is None:
                manquants.append(c["materiau"])
            else:
                mats.append((c["epaisseur_cm"], m))
        res = {"id": r["id"], "nom": r["nom"], "type_paroi": r["type_paroi"], "up_pleiades": r["up_pleiades"],
               "epaisseur_cm": r["epaisseur_cm"], "couches": [(c["materiau"], c["epaisseur_cm"]) for c in couches]}
        if manquants:
            res["U"] = val(None, "supposé", f"matériau(x) inconnu(s) : {manquants}", "faible", "W/m².K")
            res["alertes"] = [f"Matériau absent du catalogue : {m}" for m in manquants]
            return res
        u = u_paroi(r["type_paroi"], mats)
        res["U"] = val(u["U"], "déduit", "calcul multicouche (Rsi + Σe/λ + ΣR + Rse)", "moyenne", "W/m².K")
        res["isolants"] = [m["nom"] for _, m in mats if est_isolant(m)]
        res["alertes"] = u["alertes"]
        return res

    def rechercher(self, type_p: str, u_cible: float, texte: str | None = None) -> list[dict]:
        """Compositions du type demandé avec U <= u_cible (et contenant ``texte``), triées par U croissant."""
        out = []
        for c in self.compositions(type_p):
            if texte and cle(texte) not in cle(" ".join(n for n, _ in c["couches"]) + " " + c["nom"]):
                continue
            u = c["U"]["valeur"]
            if u is not None and u <= u_cible:
                out.append(c)
        return sorted(out, key=lambda c: (c["U"]["valeur"], c["epaisseur_cm"] or 0))

    # ------------------------------------------------------------------ isolants / produits
    def isolants(self, usage: str | None = None) -> list[dict]:
        rows = self.cx.execute("SELECT * FROM isolants").fetchall()
        return [{"nom": r["nom"], "lambda_W_mK": r["lambda"], "certifie": bool(r["certifie"]), "usages": r["usages"].split(","),
                 "prix_eur_m2_cm": r["prix_eur_m2_cm"]} for r in rows if usage is None or usage in r["usages"].split(",")]

    def menuiseries(self) -> list[dict]:
        return [{"nom": r["nom"], "Uw": r["uw"], "Sw": r["sw"], "prix_eur_m2": r["prix_eur_m2"]}
                for r in self.cx.execute("SELECT * FROM menuiseries ORDER BY uw")]

    def systemes(self) -> list[dict]:
        return [json.loads(r["data"]) for r in self.cx.execute("SELECT data FROM systemes")]

    def epaisseur_isolant(self, type_p: str, isolant: dict, u_cible: float, r_support: float = 0.0, pas_cm: float = 2.0) -> dict:
        """Épaisseur d'isolant (arrondie au pas supérieur) pour atteindre u_cible, support de résistance r_support."""
        rsi, rse = RSI_RSE[type_p]
        lam = isolant["lambda_W_mK"] * (1.15 if isolant.get("certifie") is False else 1.0)
        r_iso = max(0.0, 1 / u_cible - rsi - rse - r_support)
        ep = math.ceil(r_iso * lam * 100 / pas_cm) * pas_cm
        u = 1 / (rsi + rse + r_support + ep / 100 / lam)
        return {"epaisseur_cm": ep, "U": round(u, 4), "lambda_utilise": lam}

    # ------------------------------------------------------------------ ponts thermiques
    def psi_defaut(self, liaison: str, isolation: str, retour_isolant: bool = False) -> dict:
        """Ψ par défaut d'une liaison selon le mode d'isolation (« ITE » / « ITI »), valeur tracée."""
        if liaison == "menuiserie":
            liaison = "menuiserie_avec_retour" if retour_isolant else "menuiserie_sans_retour"
        if isolation.upper().startswith("ITE"):
            v = PSI_RSET_ITE[liaison]
            return val(v, "déduit", "Th-Bât 2026 tabulé (lu dans le RSET Charleville, ITE)", "moyenne", "W/m.K")
        v, src = PSI_ITI[liaison]
        return val(v, "supposé" if "SUPPOSÉ" in src else "déduit", src, "faible" if "SUPPOSÉ" in src else "moyenne", "W/m.K")

    def psi_table(self, liaison: str, isolation: str | None = None) -> list[dict]:
        q = "SELECT * FROM psi WHERE liaison=?" + (" AND isolation=?" if isolation else "")
        return [dict(r) for r in self.cx.execute(q, (liaison, isolation) if isolation else (liaison,))]
