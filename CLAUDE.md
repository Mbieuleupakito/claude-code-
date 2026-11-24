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
  CLI : `python -m re2020.plans plan.pdf --controle plan.png`.
  Tests : plans synthétiques (rectangle ITE, L en ITI avec échelle fausse) + Domène M01 ; Charleville en attente du PDF.
  Limites : murs dessinés en aplat (pas seulement en traits), HSP non lue (coupe), pas de DXF.
- `src/re2020/catalogues/` (fait) : JSON de `data/catalogues` → SQLite ; U multicouche (± 3 % des Up Pléiades),
  recherche par type de paroi / U cible / matériau, épaisseur pour un U cible, λ +15 % si non certifié, Ψ ITE/ITI.
- `src/re2020/estimation/` (fait) : modèle saisonnier calé sur le RSET Charleville (`data/references/charleville_calage.json`),
  fourchette par sensibilités ; `references.py` affiche les écarts (Charleville −0,1 ; Domène M01 −10,5 pts de Bbio).
- `src/re2020/propositions.py` (fait) : front de Pareto isolant x épaisseur, x menuiseries x systèmes, sous seuils −5 %, tri par coût.
- `src/re2020/etude.py` + `src/re2020/rapport/` (fait) : chaîne complète et PDF feuille de route (WeasyPrint) dans l'ordre Pléiades.
- `src/re2020/api.py` (fait) : FastAPI locale + page web (dépôt du plan → verdict, PDF, image de contrôle) ; études en SQLite dans `etudes/`.
- `src/re2020/acv/` (fait) : quantités par lot déduites du plan (ou supposées), catalogue `data/catalogues/fiches_acv.json`
  (DED / FDES : ORDRES DE GRANDEUR SUPPOSÉS → importer les vraies fiches via `CatalogueACV.importer_csv`, modèle
  `fiches_acv_modele.csv`), Ic construction en 3 scénarios (DED / FDES sur les 5 plus gros postes / tout FDES), seuil
  avec modulations lots 1-2-13, Ic énergie (facteurs CO2 RE2020 x 50 ans), fiches INIES à rechercher en priorité.
- `tests/` : tests de non-régression sur Charleville, Boumnich, Domène.

## Feuille de route de développement
1. Valider `seuils.py` (test OK). Compléter avec MbHSP/McHSP/MiHSP quand le texte du décret 2026-200 est disponible.
2. Extraction de plans : fait (Domène M01 + plans synthétiques). Reste : valider sur le PDF Charleville
   (test prêt, valeurs RSET), murs dessinés en traits seuls, lecture des coupes (HSP, hauteurs d'étage), DXF.
3. Estimation : faite et calée sur Charleville. Écart Domène M01 −10,5 pts (objectif ± 5) : il faut les plans et RSET
   de Boumnich / Les Ulis / Domène 180 pour recaler (climat par zone, apports, Ψ menuiseries).
4. Propositions : fait ; remplacer les prix indicatifs (supposés) de `data/catalogues/produits.json` par les prix fournisseur.
5. ACV : fait (ordres de grandeur cohérents avec Boumnich : DED ≈ 600, −15 à −20 % avec FDES, Ic énergie ≈ 69).
   Reste : importer les fiches INIES réelles, calibrer sur l'ACV Pléiades de Boumnich (inventaire par lot à récupérer).
6. Rapport PDF + API/page web locale : fait. Frontend Next.js plus tard.
7. Calibrage massif avec OPEE (data.gouv.fr) et RSEE XSD.

## Données de départ
`data/catalogues/` (compositions et matériaux Pléiades, Ψ Th-Bât), `data/references/` (résultats Pléiades, RSET Charleville),
`data/examples/` (Charleville lot 3, Domène M01 avec plan ANKHA), `docs/knowledge.md` (synthèse).
À récupérer par l'utilisateur : OPEE (2 ZIP), XSD RSEE, Th-Bât 2026-04-29, annexe XI, accès webservice INIES, RSET/.plxm des autres projets.

## Utilisateur
Honoré (alternant ingénieur thermique du bâtiment & data, DEEP-WATT, Grenoble). Il travaille souvent depuis son
téléphone : donner des instructions courtes, indiquer les fichiers modifiés plutôt que tout renvoyer.
