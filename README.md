# re2020-assistant — paquet de démarrage
Voir CLAUDE.md. Installer (Python 3.12) : `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,api,rapport]"` —
Tester : `.venv/bin/python -m pytest`.

## Application locale (dépôt d'un plan → feuille de route PDF)
```
.venv/bin/python -m re2020.api        # puis ouvrir http://127.0.0.1:8000
```
Études stockées dans `./etudes/` (SQLite + fichiers, ignoré par git). Rien ne sort du poste.
WeasyPrint peut afficher un avertissement « HarfBuzz-Subset » : sans effet (installer `libharfbuzz-subset0` pour le supprimer).

## Écarts du modèle avec Pléiades
```
.venv/bin/python -m re2020.estimation.references
```
Les plans PDF et RSET clients sont ignorés par git (règle 5 de CLAUDE.md) : les garder en local.

## Extraction d'un plan PDF
```
.venv/bin/python -m re2020.plans data/examples/domene_m01/plan_ankha_M01.pdf --controle controle.png
```
Sort un JSON (valeurs tracées `lu` / `déduit` / `supposé`), un résumé dans le terminal et une image de contrôle
(vert = emprise, orange = baies appariées, rouge = à vérifier, bleu = nord lu).
