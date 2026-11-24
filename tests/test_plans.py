from pathlib import Path

import pytest

from re2020.plans import extraire_plan
from re2020.plans import nord
from re2020.plans.textes import RE_DIMS, RE_ECHELLE, m_par_pt, normaliser_niveau

from .plan_synthetique import generer

DOMENE = Path(__file__).parents[1] / "data/examples/domene_m01/plan_ankha_M01.pdf"


# ---------------------------------------------------------------- fonctions pures

def test_echelle():
    assert RE_ECHELLE.search("Ech : 1 : 100").group(1) == "100"
    assert RE_ECHELLE.search("ECHELLE 1/50").group(1) == "50"
    assert abs(m_par_pt(100) - 0.035278) < 1e-6


def test_niveaux_et_dims():
    assert normaliser_niveau("R+0") == "RDC" and normaliser_niveau("R + 1") == "R+1"
    m = RE_DIMS.search(" 270 x 215ht. ")
    assert (m.group(1), m.group(2)) == ("270", "215")


def test_azimuts():
    assert nord.azimut((0, 1), 0) == 180  # façade vers le bas de la feuille, nord en haut → Sud
    assert nord.secteur(nord.azimut((1, 0), 0)) == "E"
    # nord tourné de 57° vers la gauche : la façade du haut regarde le NE
    az = nord.azimut((0, -1), -57.1)
    assert abs(az - 57.1) < 0.1 and nord.secteur(az) == "NE"
    assert nord.proche_limite(66) and not nord.proche_limite(45)


# ---------------------------------------------------------------- plan synthétique

@pytest.mark.parametrize("angle", [0.0, -57.0, 90.0])
def test_plan_synthetique(tmp_path, angle):
    pdf = tmp_path / "plan.pdf"
    generer(pdf, angle_nord_deg=angle)
    r = extraire_plan(pdf)
    assert r["echelle"]["denominateur"]["valeur"] == 100
    assert abs(r["nord"]["valeur"] - angle) < 1
    (niv,) = r["niveaux"]
    assert niv["niveau"]["valeur"] == "RDC"
    assert abs(niv["emprise_m"]["largeur"]["valeur"] - 10) < 0.02
    assert abs(niv["emprise_m"]["profondeur"]["valeur"] - 8) < 0.02
    assert abs(niv["murs_exterieurs"]["couche_pleine_m"]["valeur"] - 0.20) < 0.01
    assert abs(niv["murs_exterieurs"]["bande_hachuree_ext_m"]["valeur"] - 0.15) < 0.02
    assert niv["murs_exterieurs"]["isolation"]["valeur"] == "ITE probable"
    (b,) = niv["baies"]
    assert b["nom"] == "F1" and b["facade"] == "bas"
    assert (b["largeur_m"]["valeur"], b["hauteur_m"]["valeur"], b["allege_m"]["valeur"]) == (1.2, 1.35, 0.9)
    assert abs(b["largeur_mesuree_plan_m"]["valeur"] - 1.2) < 0.12 and "a_verifier" not in b
    attendu = nord.secteur(nord.azimut((0, 1), angle))
    assert b["orientation"] == attendu
    assert niv["surface_pieces_etiquetees_m2"]["valeur"] == 38.5


def test_tags_obligatoires(tmp_path):
    """Règle 1 : toute valeur tracée porte un tag lu/déduit/supposé et une confiance."""
    pdf = tmp_path / "plan.pdf"
    generer(pdf)
    r = extraire_plan(pdf)

    def parcours(o):
        if isinstance(o, dict):
            if "valeur" in o:
                assert o["tag"] in ("lu", "déduit", "supposé") and o["confiance"] in ("haute", "moyenne", "faible")
            for v in o.values():
                parcours(v)
        elif isinstance(o, list):
            for v in o:
                parcours(v)

    parcours(r)
    assert r["batiment"]["hauteur_sous_plafond_m"]["tag"] == "supposé"


# ---------------------------------------------------------------- non-régression Domène M01 (donnée client locale)

@pytest.mark.skipif(not DOMENE.exists(), reason="plan client Domène non présent (exclu de git)")
def test_domene_m01():
    r = extraire_plan(DOMENE)
    assert abs(r["nord"]["valeur"] - (-57.1)) < 2 and r["nord"]["confiance"] == "haute"
    assert [n["niveau"]["valeur"] for n in r["niveaux"]] == ["RDC", "R+1"]
    for n in r["niveaux"]:
        assert (n["emprise_m"]["largeur"]["valeur"], n["emprise_m"]["profondeur"]["valeur"]) == (7.2, 8.25)
        assert n["murs_exterieurs"]["isolation"]["valeur"].startswith("ITE")
    baies = {b["nom"]: b for n in r["niveaux"] for b in n["baies"]}
    assert len(baies) == 10 and all("a_verifier" not in b for b in baies.values())
    assert baies["Mext21"]["orientation"] == "SO" and baies["Mext21"]["largeur_m"]["valeur"] == 2.7
    assert baies["Mext20"]["orientation"] == "SE"  # étiquette verticale
    assert r["batiment"]["baies_total_m2"] == 20.15
    assert 95 < r["batiment"]["surface_interieure_totale_m2"]["valeur"] < 110  # Sref Pléiades Domène : 105,5
    assert not r["alertes"]
