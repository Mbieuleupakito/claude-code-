# re2020-assistant — feuille de route Pléiades (DEEP-WATT)
Voir CLAUDE.md pour le projet. Tout tourne en local : les plans clients ne quittent pas le poste.

## Lancer en un clic
1. Installer **Python 3.12** (https://www.python.org/downloads/, cocher « Add python.exe to PATH » sous Windows) et **git**.
2. Récupérer le projet une fois :
   `git clone https://github.com/Mbieuleupakito/claude-code-.git` puis `git checkout claude/new-session-ie2k04`.
3. Double-cliquer :
   - Windows : **`lancer.bat`** — Mac : **`lancer.command`** (Linux : `./lancer.command`).
   La première fois, il installe tout (quelques minutes). Ensuite le navigateur s'ouvre sur http://127.0.0.1:8000.
4. Déposer le plan PDF, remplir zone / altitude / date de PC → **Lancer l'étude** → feuille de route, image de contrôle.
   Les études restent listées dans « Mes études » (dossier `etudes/`).

Depuis le **téléphone** (même wifi que le PC) : `lancer_telephone.bat` (Windows) ou
`./lancer.command --reseau --mot-de-passe XXXX`, puis ouvrir l'adresse affichée sur le téléphone.
Mise à jour de l'outil : `mettre_a_jour.bat` (ou `git pull`).

Si le PDF ne peut pas être produit (WeasyPrint sans ses bibliothèques, fréquent sous Windows), la feuille de route
s'ouvre en version web : **Imprimer → Enregistrer en PDF** depuis le navigateur.

## Plus tard : serveur interne pour l'équipe
`Dockerfile` + `docker-compose.yml` : sur un PC/serveur du bureau, créer `.env` avec `RE2020_MOT_DE_PASSE=...`,
puis `docker compose up -d` → http://<serveur>:8000 pour tout le monde (études dans `./etudes`).

## Développeurs
- Installer : `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,api,rapport]"` — tester : `.venv/bin/python -m pytest`.
- Plans clients (PDF, RSET) ignorés par git : les déposer dans `data/examples/...` pour les tests de non-régression.
- Lire un plan seul : `.venv/bin/python -m re2020.plans plan.pdf --controle controle.png`
- Écarts du modèle avec Pléiades : `.venv/bin/python -m re2020.estimation.references`
- WeasyPrint peut afficher un avertissement « HarfBuzz-Subset » : sans effet.

## ACV : remplacer les ordres de grandeur par les vraies fiches
Les valeurs de `data/catalogues/fiches_acv.json` sont supposées. Remplir `data/catalogues/fiches_acv_modele.csv`
(export INIES / Pléiades) puis : `cat = CatalogueACV(); cat.importer_csv("mes_fiches.csv")` → les fiches passent en « lu ».
