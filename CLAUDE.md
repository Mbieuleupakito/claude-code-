# Assistant d'étude RE2020 (énergie + ACV) pour Pléiades — DEEP-WATT

## Objectif
Faire gagner du temps aux thermiciens (cible : diviser par 2 le temps d'une étude, ex. 5 h → 2,5 h) en
préparant la saisie dans Pléiades (Izuba). L'outil lit les documents de l'architecte, déduit les données
manquantes, propose des solutions conformes et sort un PDF « feuille de route » avec les valeurs à saisir.
Le thermicien resaisit et vérifie : le rapport doit être globalement correct et cohérent, pas parfait.
Périmètre actuel : RE2020 énergie + ACV, maison individuelle d'abord. Hors périmètre : autres réglementations.

## Règles de conduite (importantes)
1. Chaque valeur est tracée : `lu` (sur le plan/document), `déduit` (calcul ou catalogue), `supposé` (hypothèse),
   avec un niveau de confiance. Jamais de valeur inventée sans étiquette.
2. L'outil ne remplace pas Pléiades : il estime (avec fourchette) et prépare la saisie. Il ne promet pas la
   conformité réglementaire. Résultats officiels = Pléiades/moteur CSTB.
3. Pas de pénalité automatique oubliée : alerter sur les isolants non certifiés (+15 % sur λ).
4. Les seuils dépendent de la date de dépôt du PC (décret 2026-200 : PC ≥ 1er juillet 2026). Tant que MbHSP/McHSP
   sont inconnus, marquer les seuils « approx ».
5. Confidentialité : les plans et données clients restent locaux ; ne pas les envoyer vers des services tiers.
6. Pas de lecture de DWG : demander un PDF vectoriel ou un DXF.

## Architecture visée
- `src/re2020/seuils.py` : seuils et modulations (fait, testé) ; date de PC → HSP applicable ou non ;
  `hsp_implicites` retrouve MbHSP/McHSP depuis un seuil Pléiades. Paquet `re2020` en layout `src/`, Python 3.12, `.venv`.
- `src/re2020/trace.py` : `val(valeur, tag, source, confiance)` — format commun des valeurs tracées.
- `src/re2020/plans/` : extraction PDF vectoriel (pdfplumber + shapely) → JSON normalisé (fait) :
  `textes.py` (échelle, niveaux, étiquettes de baies, pièces), `echelle.py` (mention vérifiée par cotes écrites :
  lignes de cote + largeurs de baies ; mention fausse → alerte), `murs.py` (formes remplies d'épaisseur murale,
  rectangles ou polygones → vues → contour quelconque → façades, couche pleine, bandes hachurées ITE/ITI,
  ouvertures dans le mur ou l'isolant, angles, refends), `nord.py`, `extraction.py`, `controle.py`.
  CLI : `cd src && python -m re2020.plans plan.pdf --controle plan.png`.
  Tests : plans synthétiques (rectangle ITE, L en ITI avec échelle fausse) + Domène M01 ; Charleville en attente du PDF.
  Limites : murs dessinés en aplat (pas seulement en traits), HSP non lue (coupe), pas de DXF.
- `src/re2020/catalogues/` : compositions Pléiades, matériaux, Ψ Th-Bât, fiches ACV (INIES) — `data/catalogues/`.
- `src/re2020/estimation/` : déperditions, besoins, Bbio/Cep simplifiés avec fourchette ; calibrage sur les cas de `data/references/`.
- `src/re2020/acv/` : quantités par lot (13 lots), fiche par défaut → fiche spécifique recommandée, estimation Ic construction.
- `src/re2020/rapport/` : PDF feuille de route dans l'ordre de saisie Pléiades (voir docs/knowledge.md §3).
- `tests/` : tests de non-régression sur Charleville, Boumnich, Domène.

## Feuille de route de développement
1. Valider `seuils.py` (test OK). Compléter avec MbHSP/McHSP/MiHSP quand le texte du décret 2026-200 est disponible.
2. Extraction de plans : fait (Domène M01 + plans synthétiques). Reste : valider sur le PDF Charleville
   (test prêt, valeurs RSET), murs dessinés en traits seuls, lecture des coupes (HSP, hauteurs d'étage), DXF.
3. Moteur d'estimation simplifié : calibrer sur Charleville puis Domène/Boumnich/Les Ulis ; objectif ± 5 points de Bbio.
4. Générateur de propositions : combinaisons isolant/épaisseur/système vérifiant les seuils, avec coût (catalogue produits).
5. ACV : catalogue élément → fiche (modèle Boumnich) et estimation d'Ic construction par lot.
6. Rapport PDF feuille de route + interface web simple.
7. Calibrage massif avec OPEE (data.gouv.fr) et RSEE XSD.

## Données de départ
`data/catalogues/` (compositions et matériaux Pléiades, Ψ Th-Bât), `data/references/` (résultats Pléiades, RSET Charleville),
`data/examples/` (Charleville lot 3, Domène M01 avec plan ANKHA), `docs/knowledge.md` (synthèse).
À récupérer par l'utilisateur : OPEE (2 ZIP), XSD RSEE, Th-Bât 2026-04-29, annexe XI, accès webservice INIES, RSET/.plxm des autres projets.

## Utilisateur
Honoré (alternant ingénieur thermique du bâtiment & data, DEEP-WATT, Grenoble). Il travaille souvent depuis son
téléphone : donner des instructions courtes, indiquer les fichiers modifiés plutôt que tout renvoyer.
