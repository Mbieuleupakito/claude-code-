from pathlib import Path

import pytest
from shapely.geometry import Polygon

from re2020.plans import extraire_plan, nord
from re2020.plans.echelle import consensus
from re2020.plans.textes import RE_DIMS, RE_ECHELLE, m_par_pt, normaliser_niveau

from .plan_synthetique import generer, generer_l

DATA = Path(__file__).parents[1] / "data/examples"
DOMENE = DATA / "domene_m01/plan_ankha_M01.pdf"
CHARLEVILLE = next(iter(sorted((DATA / "charleville").glob("PLAN*.pdf"))), None)


def v(d):
    return d["valeur"]


# ---------------------------------------------------------------- fonctions pures

def test_echelle_textes():
    assert RE_ECHELLE.search("Ech : 1 : 100").group(1) == "100"
    assert RE_ECHELLE.search("ECHELLE 1/50").group(1) == "50"
    assert abs(m_par_pt(100) - 0.035278) < 1e-6
    assert consensus([0.0352, 0.0353, 0.0351, 0.07]) [1] == 3
    assert consensus([0.03, 0.07]) is None


def test_niveaux_et_dims():
    assert normaliser_niveau("R+0") == "RDC" and normaliser_niveau("R + 1") == "R+1"
    m = RE_DIMS.search(" 270 x 215ht. ")
    assert (m.group(1), m.group(2)) == ("270", "215")


def test_azimuts():
    assert nord.azimut((0, 1), 0) == 180  # façade vers le bas de la feuille, nord en haut → Sud
    assert nord.secteur(nord.azimut((1, 0), 0)) == "E"
    az = nord.azimut((0, -1), -57.1)  # nord tourné de 57° vers la gauche : la façade du haut regarde le NE
    assert abs(az - 57.1) < 0.1 and nord.secteur(az) == "NE"
    assert nord.proche_limite(66) and not nord.proche_limite(45)


def _tags_ok(o):
    if isinstance(o, dict):
        if "valeur" in o:
            assert o["tag"] in ("lu", "déduit", "supposé") and o["confiance"] in ("haute", "moyenne", "faible"), o
        for x in o.values():
            _tags_ok(x)
    elif isinstance(o, list):
        for x in o:
            _tags_ok(x)


# ---------------------------------------------------------------- plan rectangulaire, ITE, murs en rectangles

@pytest.mark.parametrize("angle", [0.0, -57.0, 90.0])
def test_plan_rectangulaire_ite(tmp_path, angle):
    pdf = tmp_path / "plan.pdf"
    generer(pdf, angle_nord_deg=angle)
    r = extraire_plan(pdf)
    assert v(r["echelle"]["denominateur"]) == 100
    assert abs(v(r["nord"]) - angle) < 1
    (niv,) = r["niveaux"]
    assert v(niv["niveau"]) == "RDC" and v(niv["forme"]) == "rectangulaire"
    assert abs(v(niv["emprise_m"]["largeur"]) - 10) < 0.02 and abs(v(niv["emprise_m"]["profondeur"]) - 8) < 0.02
    m = niv["murs_exterieurs"]
    assert abs(v(m["couche_pleine_m"]) - 0.20) < 0.01 and abs(v(m["bande_hachuree_ext_m"]) - 0.15) < 0.02
    assert v(m["isolation"]) == "ITE probable"
    (b,) = niv["baies"]
    assert b["nom"] == "F1" and b["cote_feuille"] == "bas"
    assert (v(b["largeur_m"]), v(b["hauteur_m"]), v(b["allege_m"])) == (1.2, 1.35, 0.9)
    assert abs(v(b["largeur_mesuree_plan_m"]) - 1.2) < 0.12 and "a_verifier" not in b
    assert b["orientation"] == nord.secteur(nord.azimut((0, 1), angle))
    assert v(niv["surface_pieces_etiquetees_m2"]) == 38.5
    # intérieur : 10 x 8 moins 20 cm de mur (pas de doublage) → 9,6 x 7,6
    assert abs(v(niv["surface_interieure_m2"]) - 9.6 * 7.6) < 0.5
    pt = r["batiment"]["ponts_thermiques"]
    assert abs(v(pt["plancher_bas_mur_ml"]) - 2 * (9.6 + 7.6)) < 0.2
    assert v(pt["angle_saillant_ml"]) == 4 * 2.5 and v(pt["angle_rentrant_ml"]) == 0


def test_tags_obligatoires(tmp_path):
    """Règle 1 : toute valeur tracée porte un tag lu/déduit/supposé et une confiance."""
    pdf = tmp_path / "plan.pdf"
    generer(pdf)
    r = extraire_plan(pdf)
    _tags_ok(r)
    assert r["batiment"]["hauteur_sous_plafond_m"]["tag"] == "supposé"


# ---------------------------------------------------------------- plan en L, ITI, murs en polygones, échelle fausse

def test_plan_en_l_iti_echelle_recalee(tmp_path):
    pdf = tmp_path / "plan_l.pdf"
    generer_l(pdf, angle_nord_deg=90.0)
    r = extraire_plan(pdf)
    _tags_ok(r)
    # la mention « 1:100 » est fausse : le dessin est au 1:50, retrouvé grâce aux cotes écrites
    ech = r["echelle"]["denominateur"]
    assert v(ech) == 50 and ech["tag"] == "déduit" and ech["confiance"] == "haute"
    assert any("mention dit 1:100" in a for a in r["alertes"])
    (niv,) = r["niveaux"]
    assert v(niv["forme"]).startswith("polygonale (6")
    assert niv["angles"] == {"saillants": 5, "rentrants": 1}
    assert abs(v(niv["surface_emprise_m2"]) - 68.0) < 0.5
    m = niv["murs_exterieurs"]
    assert abs(v(m["couche_pleine_m"]) - 0.30) < 0.02 and abs(v(m["bande_hachuree_int_m"]) - 0.12) < 0.02
    assert v(m["isolation"]) == "ITI probable"
    interieur = Polygon([(0, 0), (10, 0), (10, 5), (6, 5), (6, 8), (0, 8)]).buffer(-0.42, join_style="mitre")
    assert abs(v(niv["surface_interieure_m2"]) - interieur.area) < 0.5
    assert abs(v(niv["perimetre_interieur_m"]) - interieur.length) < 0.2
    baies = {b["nom"]: b for b in niv["baies"]}
    assert set(baies) == {"F1", "F2", "F3"} and all("a_verifier" not in b for b in baies.values())
    # nord vers la droite : bas de feuille = Est, droite = Nord ; F3 donne dans le retrait du L, vers le bas → Est
    assert (baies["F1"]["orientation"], baies["F2"]["orientation"], baies["F3"]["orientation"]) == ("E", "N", "E")
    assert abs(v(baies["F1"]["largeur_mesuree_plan_m"]) - 2.0) < 0.05
    assert r["batiment"]["baies_par_orientation_m2"] == {"E": 5.55, "N": 1.62}
    assert not [a for a in r["alertes"] if "sans étiquette" in a or "sans ouverture" in a]


# ---------------------------------------------------------------- non-régression sur plans clients (locaux, exclus de git)

@pytest.mark.skipif(not DOMENE.exists(), reason="plan client Domène non présent (exclu de git)")
def test_domene_m01():
    r = extraire_plan(DOMENE)
    assert v(r["echelle"]["denominateur"]) == 100 and r["echelle"]["denominateur"]["confiance"] == "haute"
    assert abs(v(r["nord"]) - (-57.1)) < 2 and r["nord"]["confiance"] == "haute"
    assert [v(n["niveau"]) for n in r["niveaux"]] == ["RDC", "R+1"]
    for n in r["niveaux"]:
        assert (v(n["emprise_m"]["largeur"]), v(n["emprise_m"]["profondeur"])) == (7.2, 8.25)
        assert v(n["murs_exterieurs"]["isolation"]).startswith("ITE")
        assert abs(v(n["murs_exterieurs"]["couche_pleine_m"]) - 0.20) < 0.01
    baies = {b["nom"]: b for n in r["niveaux"] for b in n["baies"]}
    assert len(baies) == 10 and all("a_verifier" not in b for b in baies.values())
    assert baies["Mext21"]["orientation"] == "SO" and v(baies["Mext21"]["largeur_m"]) == 2.7
    assert baies["Mext20"]["orientation"] == "SE"  # étiquette verticale
    assert r["batiment"]["baies_total_m2"] == 20.15
    assert abs(v(r["batiment"]["surface_interieure_totale_m2"]) - 105.5) / 105.5 < 0.05  # Sref Pléiades : 105,5
    assert not r["alertes"]


@pytest.mark.skipif(CHARLEVILLE is None, reason="plan client Charleville non présent : déposer le PDF dans data/examples/charleville/")
def test_charleville_lot3():
    """Valeurs de référence : RSET Pléiades (data/references/charleville_rset.txt). Tolérances larges :
    l'outil prépare la saisie, il ne remplace pas Pléiades. Mentions d'échelle fausses (1:250 écrit, ≈ 1:63 réel) :
    l'échelle est retrouvée par les surfaces de pièces écrites."""
    # ces plans n'ont ni flèche du nord ni « NORD » écrit (vérifié) : le nord est saisi, en haut de la feuille
    # comme dans le RSET (façade des portes-fenêtres au sud)
    r = extraire_plan(CHARLEVILLE, angle_nord_deg=0)
    bat = r["batiment"]
    assert v(bat["nombre_niveaux"]) == 2
    assert [v(n["niveau"]) for n in r["niveaux"]] == ["RDC", "R+1"]
    assert 60 <= v(r["echelle"]["denominateur"]) <= 66
    assert abs(v(bat["plancher_bas_m2"]) - 126.7) / 126.7 < 0.10  # « Planchers bas 126,7 m² » du RSET
    pt = bat["ponts_thermiques"]
    assert abs(v(pt["plancher_bas_mur_ml"]) - 45.02) / 45.02 < 0.10
    o = bat["baies_par_orientation_m2"]["O"]  # grande baie double hauteur du séjour
    assert abs(o - 17.44) / 17.44 < 0.25
    assert all(v(n["murs_exterieurs"]["isolation"]).startswith("ITE") for n in r["niveaux"])


@pytest.mark.skipif(CHARLEVILLE is None, reason="plan client Charleville non présent : déposer le PDF dans data/examples/charleville/")
@pytest.mark.xfail(reason="hauteurs des baies supposées (pas d'étiquette sur le plan) : les lire sur les élévations "
                          "(échelle fausse, vantaux dessinés un par un) ; SHAB < surface intérieure", strict=False)
def test_charleville_lot3_baies_et_shab():
    r = extraire_plan(CHARLEVILLE, angle_nord_deg=0)
    bat = r["batiment"]
    assert abs(bat["baies_total_m2"] - 45.5) / 45.5 < 0.15
    for o, ref in {"S": 18.4, "O": 17.44, "E": 8.85}.items():
        assert abs(bat["baies_par_orientation_m2"].get(o, 0) - ref) / ref < 0.25, o
    assert abs(v(bat["surface_interieure_totale_m2"]) - 212.2) / 212.2 < 0.10
