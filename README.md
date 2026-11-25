# re2020-assistant — feuille de route Pléiades (DEEP-WATT)
Voir CLAUDE.md pour le projet. Tout tourne en local : les plans clients ne quittent pas le poste.

## Lancer en un clic
1. Installer **Python 3.12** (https://www.python.org/downloads/, cocher « Add python.exe to PATH » sous Windows) et **git**.
2. Récupérer le projet une fois :
   `git clone https://github.com/Mbieuleupakito/claude-code-.git` puis `git checkout claude/new-session-ie2k04`.
3. Double-cliquer :
   - Windows : **`lancer.bat`** — Mac : **`lancer.command`** (Linux : `./lancer.command`).
   La première fois, il installe tout (quelques minutes). Ensuite le navigateur s'ouvre sur http://127.0.0.1:8000.
4. Déposer **tout le dossier** (plans en PDF, DXF ou DWG ; coupe ; notice en PDF, Word ou Excel) → **Lancer l'étude**. Zone,
   altitude, date de PC, Sref, parois, menuiseries, Ψ, ventilation, systèmes, hauteurs sont lus dans les documents
   (les saisir seulement s'ils manquent). La fiche montre les **contrôles croisés** plan mesuré / dossier écrit.
   Les études restent listées dans « Mes études » (dossier `etudes/`).

Depuis le **téléphone** (même wifi que le PC) : `lancer_telephone.bat` (Windows) ou
`./lancer.command --reseau --mot-de-passe XXXX`, puis ouvrir l'adresse affichée sur le téléphone.
Mise à jour de l'outil : `mettre_a_jour.bat` (ou `git pull`).

Si le PDF ne peut pas être produit (WeasyPrint sans ses bibliothèques, fréquent sous Windows), la feuille de route
s'ouvre en version web : **Imprimer → Enregistrer en PDF** depuis le navigateur.

## Le site (web/)
Pages : Études, Nouvelle étude (glisser-déposer du plan), fiche d'étude (verdicts avec fourchette, plan annoté,
enveloppe, ponts thermiques, propositions, ACV, hypothèses à valider), Fiabilité du modèle, Catalogues.
Le site est compilé dans `src/re2020/web/` (déjà inclus) : **Node n'est pas nécessaire pour l'utiliser**.
Pour le modifier : `cd web && npm install`, puis `npm run dev` (http://localhost:3000, l'API Python doit tourner sur
le port 8000) ; `npm run build` recompile et republie dans `src/re2020/web/`.

## Plus tard : serveur interne pour l'équipe
`Dockerfile` + `docker-compose.yml` : sur un PC/serveur du bureau, créer `.env` avec `RE2020_MOT_DE_PASSE=...`,
puis `docker compose up -d` → http://<serveur>:8000 pour tout le monde (études dans `./etudes`).

## Développeurs
- Installer : `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,api,rapport]"` — tester : `.venv/bin/python -m pytest`.
- Plans clients (PDF, RSET) ignorés par git : les déposer dans `data/examples/...` pour les tests de non-régression.
- Lire un plan seul : `.venv/bin/python -m re2020.plans plan.pdf --controle controle.png`
- Écarts du modèle avec Pléiades : `.venv/bin/python -m re2020.estimation.references`
- WeasyPrint peut afficher un avertissement « HarfBuzz-Subset » : sans effet.

## Serveur MCP 21st (composants d'interface, pour le futur frontend)
Déclaré dans `.mcp.json` (serveur HTTP `https://21st.dev/api/mcp`). Clé gratuite sur https://21st.dev/mcp, puis :
- Windows : `setx API_KEY_21ST "ta_cle"` (rouvrir le terminal) — Mac/Linux : `export API_KEY_21ST=ta_cle` ;
- relancer Claude Code dans le dossier du projet et accepter le serveur « 21st » (`/mcp` pour vérifier).
Ne jamais lui envoyer de plans ou de données clients (règle 5) : il ne sert qu'à l'interface.

## Skill « unslop » (design de l'interface)
`.claude/skills/unslop/` (heydamir/unslop, CC BY 4.0) : demander à Claude Code « unslop la page web » pour retravailler
une interface qui fait « générée par IA ». Disponible automatiquement dans les sessions ouvertes sur ce projet.

## ACV : remplacer les ordres de grandeur par les vraies fiches
Les valeurs de `data/catalogues/fiches_acv.json` sont supposées. Remplir `data/catalogues/fiches_acv_modele.csv`
(export INIES / Pléiades) puis : `cat = CatalogueACV(); cat.importer_csv("mes_fiches.csv")` → les fiches passent en « lu ».

## Fichiers DWG
Le DWG est un format fermé : il est converti en DXF **sur ce poste** si **ODA File Converter** (gratuit) est installé
(https://www.opendesign.com/guestfiles/oda_file_converter), ou LibreDWG (`dwg2dxf`). Sinon l'outil le signale et lit le
reste du dossier. Rien n'est envoyé sur Internet.
