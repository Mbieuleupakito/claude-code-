# Connaissances consolidées (RE2020 énergie + ACV, Pléiades)

Tout ce qui suit vient des documents du Drive DEEP-WATT, des tutoriels Izuba et des textes officiels. Les
sections « Hypothèse » sont des déductions de Claude à vérifier.

## 1. Indicateurs
- Bbio = 2 × besoin chauffage + 2 × besoin froid + 5 × besoin éclairage (kWh/m²Sref). Vérifié : Charleville 28,9 / 1,0 / 1,8 → 68,8 (RSET 68,9).
- Cep = Σ énergie finale × coefficient primaire ; électricité 2,3, gaz/fioul/bois/réseau chaleur 1. Usages mobiliers exclus. Vérifié : (11,2 + 4,5 + 1,8) × 2,3 = 40,25 (RSET 40,3).
- Cep,nr : électricité 2,3 ; bois 0 ; réseau de chaleur 1 − taux EnR.
- DH : seuil 1250 °C.h (catégorie 1), 1850 (catégorie 2), < 350 sans pénalité.
- Ic construction = Ic composants + Ic chantier ; ACV sur 50 ans, 13 lots, données INIES (FDES, PEP, DED, forfaits).
- DED : pénalisantes (+100 % ou +30 %), à remplacer par des FDES quand elles existent (gain ACV majeur).

## 2. Seuils (maison individuelle)
Voir `src/re2020/seuils.py` (valeurs et formules). Manque : MbHSP/McHSP/MiHSP (décret 2026-200, PC ≥ 1er juillet 2026), formule d'assemblage exacte de l'Ic construction_max, catégories de contraintes.

## 3. Pléiades : ordre de saisie
Bibliothèque projet (parois, menuiseries, ponts thermiques) → données par défaut → géométrie (fond de plan DWG, orientation, échelle, enveloppe, parois intérieures, sens des compositions, baies, hauteur des niveaux, casquettes) → toitures → partie de bâtiment et usage des pièces → masques → ponts thermiques → RE2020 : météo, masques lointains, zonage bâtiment/zone/groupe + locaux tampons, systèmes (génération au bâtiment, émetteurs au groupe, ventilation au groupe ou zone) → Th-BCE → ACV (inventaire par lot, PCE, macro-composants, fiches).
Mode de calcul « Th-DB (DH-Bbio) Systèmes fictifs » pour Bbio/DH seuls ; Th-BCE complet pour Cep.
Isolants non certifiés : pénalité 15 % non appliquée automatiquement dans Pléiades → l'outil doit alerter.

## 4. RSET / RSEE (structure à reproduire)
Ch.1 administratif ; Ch.2 exigences (Bbio, Cep, Cep,nr, DH, moyens art. 19-34) ; Ch.3 indicateurs pédagogiques ; Ch.4 enveloppe/équipements/génération ; Ch.5 sensibilités. Attestation PC : Sref, Bbio, DH, engagement Ic construction, éclairage naturel, ventilation.
Cas de référence complet : `data/references/charleville_rset.txt`.

## 5. Cas calibrés
- Charleville : Sref 212,2 ; H1b ; Bbio 68,9 (max 71,6) ; Cep 40,3 (max 68,1) ; DH 197,4 ; murs ITE U 0,18 ; toiture 0,10 ; plancher bas 0,10 ; baies 45,5 m² Uw ≈ 1,35 ; ratio Ψ 0,25 ; PAC double service ; ventilation SF hygro B.
- Boumnich : Sref 229,2 ; Bbio 81,9 (max 82,6) ; Cep 53,6 (max 84,0) ; DH 336,5 ; Ic énergie 68,5 ; Ic construction 578,3 → < 492,5 (remplacement de DED par fiches).
- Domène (3 variantes 105,5 m² ; 180,84 m²), Les Ulis 195,61 m², Strasbourg 2101,64 m² : voir `data/references/resultats_references.json`.
- Domène M01 (plan ANKHA) : extraction + estimation Bbio 83–95 → trop large, le but du calibrage est de resserrer.

## 6. Ponts thermiques (Th-Bât, valeurs tabulées lues dans le RSET Charleville, ITE)
Dallage isolé en sous-face ψ 0,6 (≈ 50 % du total) ; plancher intermédiaire 0,05 ; mur/plancher haut 0,05 ; refend béton 0,03 ; angle de mur 0,05 ; menuiserie ITE sans retour d'isolant 0,62, avec retour 0,15. Murs donnant sur l'extérieur ou un local non chauffé : +30 % (tables). Exigence moyen : ratio Ψ ≤ 0,33 (art. 22.II) ou température de surface > 15 °C ; Ψ9 ≤ 0,60.

## 7. Lecture de plans (leçons)
- PDF vectoriel > DXF aplati (un DXF converti depuis PDF n'a qu'un calque « 0 » et pas de texte) > raster.
- Murs : remplissage bleu (0, 0,5, 0,75) dans le plan ANKHA ; hachures extérieures = ITE probable ; échelle 1:100 sur A3, 1 pt = 0,03528 m ; vérifier avec une cote écrite.
- Étiquettes de baies « Mext 21 / 270 x 215ht. / all.0 » = largeur × hauteur / allège en cm.
- Symbole du nord : lire la direction de la flèche (pas supposer que le haut est le nord).
- Hauteur sous plafond rarement cotée : demander ou déduire (hypothèse à marquer).

## 8. Sources externes à brancher
OPEE (data.gouv.fr, RSEE ouverts), XSD RSEE (site RT-RE-Bâtiment), webservice INIES, Th-Bât 2026-04-29, annexe XI (lots forfaitaires), Maestro (outil de l'État), moteur CSTB (sur demande DHUP).
