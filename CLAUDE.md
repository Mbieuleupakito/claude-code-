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
   Seule exception, demandée par l'utilisateur : commune + code postal vers les services publics (BAN, IGN) pour
   l'altitude ; jamais l'adresse complète ni les documents. RE2020_HORS_LIGNE=1 coupe tout appel.
6. Formats : PDF vectoriel et DXF lus directement ; DWG seulement converti SUR LE POSTE (ODA File Converter ou
   LibreDWG installés), jamais par un service en ligne ; Word/Excel/texte lus comme une notice ; images non lues
   (signalées). Le DXF est redessiné en PDF vectoriel à 1:100 (`formats.py`) ; murs en traits reconnus par calque.

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
  Échelle : mention vérifiée par les cotes écrites ; à défaut, calée sur les surfaces de pièces écrites (« SÉJOUR 80 m² »),
  commune à toutes les pages d'un même fichier (la plus grande : un vide non étiqueté ne fait que la sous-estimer).
  Poché des murs = couleur dominante (flèches de coupe, repères NGF écartés) ; contour refermé même avec une baie de 4 m ;
  tronçon de façade sans mur = grande baie ; « Vide sur RDC » retiré de la surface intérieure et ignoré comme titre.
  OCR local (`src/re2020/ocr.py`, RapidOCR/ONNX, rien n'est envoyé) pour les textes dessinés en traits : cartouche
  (adresse, titre « PLAN R+1 PROJET »), pages pauvres en texte seulement.
  Tests : plans synthétiques (rectangle ITE, L en ITI, dossier « peint » + notice) + Domène M01 + mini-projet bureaux
  (`data/examples/mini_projet/`, 18 contrôles croisés concordants) + Charleville (PDF client gitignoré : 2 niveaux,
  1:63 retrouvé alors que 1:250 est écrit, plancher bas 130,6 m² vs 126,7 RSET, baie O double hauteur).
  Limites : pas de nord sur les plans Charleville (à saisir) ; hauteurs des baies non étiquetées supposées → baies
  +23 % (test xfail) : prochaine étape = lire les élévations (échelle fausse aussi, vantaux un par un) ; HSP non lue.
- `src/re2020/documents/` (fait) : lecture de TOUT le dossier PDF (notice, tableaux, coupe…) : tableaux reconnus par
  leurs en-têtes (infos projet, parois Up, menuiseries Uw/g/TL, Ψ·L, baies + allèges, locaux, bilan façades, Sref),
  texte libre par section (ventilation, chauffage, ECS, éclairage, HSP). Valeurs « lu » avec page source. Remplacent
  les hypothèses (`estimation/hypotheses.appliquer_dossier`). `etude.controles_croises` compare plan mesuré / dossier écrit.
  Plans : PDF multi-pages (pages de plans trouvées seules), murs « peints » (aplat + intérieur blanc), baies en aplats
  de couleur typées par la légende, échelle calée sur les cotes écrites, « NORD ↑ » écrit, hauteurs lues.
  Usage tertiaire détecté → verdicts « hors périmètre » (seuils et modèle = maison individuelle).
- `src/re2020/localisation.py` (fait) : lieu du projet (codes postaux, « Ville (38) », départements ; l'adresse du chantier
  est préférée à celles des intervenants) → zone climatique par département (tableau de l'arrêté, hors ligne) ; altitude
  en ligne (Base Adresse Nationale + altimétrie IGN) en n'envoyant que commune + code postal, désactivable
  (RE2020_HORS_LIGNE=1) ; sinon altitude lue sur les cotes NGF des plans, sinon < 400 m supposé. Champ « Adresse ou
  commune du chantier » dans le formulaire (adresse complète acceptée, seule la commune part). Lieu introuvable →
  erreur 422 `zone_a_saisir` et le champ est mis en avant. Date de PC absente → date des plans, sinon du jour + alerte.
- `src/re2020/catalogues/` (fait) : JSON de `data/catalogues` → SQLite ; U multicouche (± 3 % des Up Pléiades),
  recherche par type de paroi / U cible / matériau, épaisseur pour un U cible, λ +15 % si non certifié, Ψ ITE/ITI.
- `src/re2020/estimation/` (fait) : modèle saisonnier calé sur le RSET Charleville (`data/references/charleville_calage.json`),
  fourchette par sensibilités ; `references.py` affiche les écarts (Charleville −0,1 ; Domène M01 −10,5 pts de Bbio).
- `src/re2020/compositions.py` + `data/catalogues/systemes_constructifs.json` (fait) : COMPOSITIONS COMPLÈTES ext. → int.
  (enduit + parpaing / brique R 1,45 / Gélis 30 / béton / MOB / monomur / béton cellulaire + isolant + parement), couches
  fixes lues dans les rapports Pléiades DEEP-WATT ; isolant variable choisi parmi les familles compatibles avec la pose
  (`poses` dans `produits.json` : iti_ossature, doublage_colle, ite_enduit, combles_soufflage, rampants, sous_dallage,
  sous_chape, mob) ; parement cohérent (BA13 sur ossature, BA10 en complexe collé, plâtre derrière ITE) ; λ +15 % si
  non certifié. Murs filtrés par le mode d'isolation lu (ITE/ITI) et la structure lue dans la notice.
- `src/re2020/propositions.py` (fait) : front de Pareto compositions x menuiseries x systèmes, sous seuils −5 %, tri par
  coût ; « variantes » = meilleure composition de chaque autre système au même U que la proposition n°1.
- `src/re2020/pleiades.py` (fait) : lecture des rapports d'étude Pléiades (.odt) : compositions couche par couche, parois,
  menuiseries, Ψ, résultats Projet/Max. `python -m re2020.pleiades rapport.odt --json sortie.json`. Base anonymisée
  `data/references/projets_pleiades.json` (Charleville, MI Isère H1c ITI, Domène A180, cas OPCO tertiaire) ; notre U
  multicouche = Up Pléiades à ±0,006 (test). Un .odt déposé dans une étude est lu comme notice (Up « lu »).
- `src/re2020/etude.py` + `src/re2020/rapport/` (fait) : chaîne complète et PDF feuille de route dans l'ordre Pléiades,
  avec le tableau couche par couche des compositions à créer. PDF : WeasyPrint, sinon xhtml2pdf (100 % Python, police
  Arial/DejaVu embarquée, aucun accès réseau) → PDF garanti sous Windows sans GTK.
- `src/re2020/api.py` (fait) : FastAPI locale + page web (dépôt du plan → verdict, PDF ou HTML imprimable, image de contrôle,
  « Mes études ») ; études en SQLite dans `etudes/`. Lanceurs `lancer.bat` / `lancer.command` (installation auto au 1er
  lancement) ; `--reseau --mot-de-passe` pour le téléphone ; `Dockerfile` pour un serveur interne (phase entreprise).
- `web/` (fait) : site Next.js 15 / TypeScript, compilé en pages statiques publiées dans `src/re2020/web/` et servies
  par l'API (pas de Node pour l'utilisateur). Pages : études, nouvelle étude, fiche d'étude (jauges seuil/fourchette,
  plan annoté, baies, déperditions, Ψ, propositions, ACV par lot, hypothèses), fiabilité du modèle, catalogues.
  Design : neutres graphite + un accent, pastille de provenance lu/déduit/supposé, clair/sombre, mobile.
  Après modification : `cd web && npm run build` puis committer `src/re2020/web/`.
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
6. Rapport PDF + API + site Next.js local : fait.
7. Calibrage massif avec OPEE (data.gouv.fr) et RSEE XSD.

## Données de départ
`data/catalogues/` (compositions et matériaux Pléiades, Ψ Th-Bât), `data/references/` (résultats Pléiades, RSET Charleville),
`data/examples/` (Charleville lot 3, Domène M01 avec plan ANKHA), `docs/knowledge.md` (synthèse).
Drive DEEP-WATT (lu) : comparatif global des isolants, guides des isolants et de la maçonnerie → λ et usages des isolants.
À récupérer par l'utilisateur : OPEE (2 ZIP), XSD RSEE, Th-Bât 2026-04-29, annexe XI, accès webservice INIES, RSET/.plxm des autres projets.

## Utilisateur
Honoré (alternant ingénieur thermique du bâtiment & data, DEEP-WATT, Grenoble). Il travaille souvent depuis son
téléphone : donner des instructions courtes, indiquer les fichiers modifiés plutôt que tout renvoyer.
