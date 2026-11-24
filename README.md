# re2020-assistant — paquet de démarrage
Voir CLAUDE.md. Installer (Python 3.12) : `python3.12 -m venv .venv && .venv/bin/pip install -e .[dev]` —
Tester : `.venv/bin/python -m pytest`.
Les plans PDF et RSET clients sont ignorés par git (règle 5 de CLAUDE.md) : les garder en local.

## Extraction d'un plan PDF
```
cd src && ../.venv/bin/python -m re2020.plans ../data/examples/domene_m01/plan_ankha_M01.pdf --controle controle.png
```
Sort un JSON (valeurs tracées `lu` / `déduit` / `supposé`), un résumé dans le terminal et une image de contrôle
(vert = emprise, orange = baies appariées, rouge = à vérifier, bleu = nord lu).
