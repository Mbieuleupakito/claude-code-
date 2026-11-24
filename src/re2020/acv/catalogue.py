"""Catalogue des fiches ACV par élément : valeur par défaut (DED / forfait) et fiche spécifique recommandée.

Les valeurs livrées sont des ordres de grandeur SUPPOSÉS (data/catalogues/fiches_acv.json). ``importer_csv``
les remplace par les vraies fiches (export INIES / Pléiades), qui deviennent alors « lu ».

Format CSV (séparateur ; ou ,) : element;type;nom;id_inies;ic_kg_uf;role
  role = defaut | specifique
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

from ..catalogues import DOSSIER_DATA

FICHIER = DOSSIER_DATA / "fiches_acv.json"


class CatalogueACV:
    def __init__(self, chemin: Path = FICHIER):
        d = json.loads(Path(chemin).read_text(encoding="utf-8"))
        self.lots = {int(k): v for k, v in d["lots"].items()}
        self.ic_chantier = d["ic_chantier_kg_m2"]
        self.elements = {e["id"]: copy.deepcopy(e) for e in d["elements"]}
        for e in self.elements.values():
            for role in ("defaut", "specifique"):
                if e.get(role):
                    e[role].setdefault("tag", "supposé")
                    e[role].setdefault("source", "ordre de grandeur (fiches_acv.json), à remplacer par INIES")

    def element(self, ident: str) -> dict:
        return self.elements[ident]

    def importer_csv(self, chemin: str | Path) -> int:
        """Remplace les valeurs par celles d'un export de fiches réelles. Retourne le nombre de fiches importées."""
        texte = Path(chemin).read_text(encoding="utf-8-sig")
        dialecte = csv.Sniffer().sniff(texte.splitlines()[0], delimiters=";,")
        n = 0
        for ligne in csv.DictReader(texte.splitlines(), dialect=dialecte):
            e = self.elements.get(ligne["element"].strip())
            if e is None:
                raise KeyError(f"élément ACV inconnu dans le CSV : {ligne['element']!r}")
            role = (ligne.get("role") or "specifique").strip()
            e[role] = {"type": ligne["type"].strip(), "nom": ligne.get("nom", "").strip(),
                       "id_inies": ligne.get("id_inies", "").strip(), "ic": float(ligne["ic_kg_uf"].replace(",", ".")),
                       "tag": "lu", "source": f"fiche importée ({Path(chemin).name})"}
            n += 1
        return n
