# re2020-assistant — paquet de démarrage
Voir CLAUDE.md. Installer : `pip install -e .[dev]` — Lancer : `python -m pytest`.
Les plans PDF et RSET clients sont ignorés par git (règle 5 de CLAUDE.md) : les garder en local.

## Extraction d'un plan PDF
```
python -m src.re2020.plans data/examples/domene_m01/plan_ankha_M01.pdf --controle controle.png
```
Sort un JSON (valeurs tracées `lu` / `déduit` / `supposé`), un résumé dans le terminal et une image de contrôle
(vert = emprise, orange = baies appariées, rouge = à vérifier, bleu = nord lu).
