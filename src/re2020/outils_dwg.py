"""Convertisseur DWG → DXF installé SUR LE POSTE : LibreDWG (logiciel libre, GNU), version Windows officielle.

Le lanceur l'installe une seule fois (téléchargement depuis GitHub, empreinte SHA256 vérifiée) dans ``outils/libredwg``.
Aucun fichier client n'est envoyé : seul l'outil est téléchargé, la conversion se fait ensuite hors ligne.
Si ODA File Converter est installé, il reste prioritaire.

Usage manuel : python -m re2020.outils_dwg
"""
from __future__ import annotations

import hashlib
import platform
import sys
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
DOSSIER = RACINE / "outils" / "libredwg"
VERSION = "0.14"
URL = f"https://github.com/LibreDWG/libredwg/releases/download/{VERSION}/libredwg-{VERSION}-win64.zip"
SHA256 = "1ad7e15344d20b3426c3435b078d82fb84b35062815946b2cca9c5fc9810fea8"  # publiée dans les notes de version 0.14


def chemin_dwg2dxf() -> Path | None:
    for nom in ("dwg2dxf.exe", "dwg2dxf"):
        f = DOSSIER / nom
        if f.is_file():
            return f
    return None


def installer(force: bool = False) -> Path | None:
    """Télécharge et décompresse LibreDWG (Windows 64 bits). Retourne le chemin de dwg2dxf.exe ou None."""
    if chemin_dwg2dxf() and not force:
        return chemin_dwg2dxf()
    if platform.system() != "Windows":
        print("  LibreDWG automatique : Windows seulement (ailleurs : installer libredwg ou ODA File Converter).")
        return None
    if RE_HORS_LIGNE():
        return None
    DOSSIER.mkdir(parents=True, exist_ok=True)
    zip_ = DOSSIER / "libredwg.zip"
    print("  Installation du lecteur de DWG (LibreDWG, 12 Mo, une seule fois)…")
    try:
        urllib.request.urlretrieve(URL, zip_)
    except OSError as exc:
        print(f"  Téléchargement impossible ({exc}) : les DWG ne seront pas lus (installer ODA File Converter).")
        return None
    if hashlib.sha256(zip_.read_bytes()).hexdigest() != SHA256:
        zip_.unlink(missing_ok=True)
        print("  Fichier téléchargé non conforme (empreinte SHA256) : supprimé, DWG non lus.")
        return None
    with zipfile.ZipFile(zip_) as z:
        z.extractall(DOSSIER)
    zip_.unlink(missing_ok=True)
    f = chemin_dwg2dxf()
    print("  Lecteur de DWG installé." if f else "  dwg2dxf.exe introuvable dans l'archive.")
    return f


def RE_HORS_LIGNE() -> bool:
    import os

    return os.environ.get("RE2020_HORS_LIGNE") == "1"


if __name__ == "__main__":
    sys.exit(0 if installer(force="--force" in sys.argv) else 1)
