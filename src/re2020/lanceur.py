"""Lanceur utilisé par lancer.bat / lancer.command : met l'outil à jour (git pull), réinstalle les composants si
pyproject.toml a changé, puis démarre le serveur dans un processus neuf (donc avec le code à jour).

Usage : python -m re2020.lanceur [options de re2020.api]
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _git_pull() -> None:
    if not (RACINE / ".git").exists() or not shutil.which("git"):
        return
    print("  Recherche d'une mise à jour…")
    try:
        r = subprocess.run(["git", "-C", str(RACINE), "pull", "--ff-only"], capture_output=True, text=True, timeout=60)
        msg = (r.stdout + r.stderr).strip().splitlines()
        if r.returncode == 0:
            print("  " + ("Outil déjà à jour." if any("Already up to date" in l or "Déjà à jour" in l for l in msg) else "Mise à jour installée."))
        else:
            print("  Mise à jour impossible (pas d'Internet ou fichiers modifiés à la main) : l'outil démarre avec la version actuelle.")
    except (OSError, subprocess.TimeoutExpired):
        print("  Mise à jour impossible : l'outil démarre avec la version actuelle.")


def _composants() -> None:
    pyproject = RACINE / "pyproject.toml"
    marque = Path(sys.prefix) / "pyproject.installe"
    empreinte = hashlib.sha256(pyproject.read_bytes()).hexdigest()
    if marque.exists() and marque.read_text().strip() == empreinte:
        return
    print("  Installation des composants (quelques minutes la première fois)…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", f"{RACINE}[api,rapport]"])
    if r.returncode == 0:
        marque.write_text(empreinte)
    else:
        print("  L'installation des composants a échoué : envoyer une capture de cette fenêtre.")


def _lecteur_dwg() -> None:
    """Sous Windows : installe une fois LibreDWG (lecture des DWG sur le poste) si ODA File Converter n'est pas là."""
    try:
        from re2020.formats import trouver_oda
        from re2020.outils_dwg import chemin_dwg2dxf, installer

        if not trouver_oda() and not chemin_dwg2dxf():
            installer()
    except Exception as exc:  # jamais bloquant
        print(f"  Lecteur de DWG non installé ({exc}).")


def main() -> int:
    _git_pull()
    _composants()
    _lecteur_dwg()
    return subprocess.call([sys.executable, "-m", "re2020.api", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
