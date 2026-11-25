#!/bin/bash
# Assistant RE2020 - double-cliquer pour lancer (Mac ; sous Linux : ./lancer.command).
# Options : --reseau --mot-de-passe XXXX pour l'ouvrir depuis le téléphone (même wifi).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Première utilisation : installation (quelques minutes)…"
  PY=$(command -v python3.12 || true)
  if [ -z "$PY" ]; then
    echo "Python 3.12 introuvable : l'installer depuis https://www.python.org/downloads/ puis relancer."
    read -r -p "Entrée pour fermer"; exit 1
  fi
  "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip \
    && .venv/bin/python -m pip install -e ".[api,rapport]" || { echo "Échec de l'installation."; read -r -p "Entrée pour fermer"; exit 1; }
fi
exec .venv/bin/python -m re2020.lanceur "$@"
