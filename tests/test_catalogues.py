import pytest

from re2020.catalogues import Catalogue, u_paroi


@pytest.fixture(scope="module")
def cat(tmp_path_factory):
    return Catalogue(tmp_path_factory.mktemp("db") / "catalogues.sqlite")  # base SQLite sur disque


def test_u_calcule_proche_de_pleiades(cat):
    """Le calcul multicouche retrouve les Up affichés par Pléiades (± 3 %)."""
    comps = cat.compositions()
    assert len(comps) == 7
    for c in comps:
        assert abs(c["U"]["valeur"] - c["up_pleiades"]) / c["up_pleiades"] < 0.03, c["nom"]
        assert c["U"]["tag"] == "déduit"


def test_rapprochement_noms_materiaux(cat):
    m = cat.materiau("Polyuréthane TMS 0.020")
    assert m["nom"].startswith("Polyuréthane TMS 0.020") and m["lambda_W_mK"] == 0.02
    assert cat.materiau("Plâtre courant d’enduit intérieur ( 1000 ≤ ρ ≤ 1300)")["lambda_W_mK"] == 0.57
    assert cat.materiau("inexistant xyz") is None


def test_recherche_par_type_et_u_cible(cat):
    murs = cat.rechercher("mur_ext", 0.15)
    assert [c["nom"] for c in murs] == ["MUR EXTERIEUR"]
    assert cat.rechercher("mur_ext", 0.10) == []
    assert [c["nom"] for c in cat.rechercher("plafond", 0.12, texte="laine de verre")] == ["PLAFOND sous comble perdu"]
    assert cat.rechercher("plafond", 0.12, texte="polyurethane") == []


def test_alerte_certification(cat):
    c = cat.composition("PLAFOND sous comble perdu")
    assert any("ACERMI" in a for a in c["alertes"])  # « Laine de verre 30 » : certification inconnue


def test_penalite_isolant_non_certifie():
    iso = {"nom": "Ouate", "lambda_W_mK": 0.040, "certifie": False}
    certif = {"nom": "Ouate", "lambda_W_mK": 0.040, "certifie": True}
    u_nc = u_paroi("plafond", [(30, iso)])
    u_c = u_paroi("plafond", [(30, certif)])
    assert u_nc["U"] > u_c["U"]
    r_iso_nc = 1 / u_nc["U"] - 0.14
    assert abs(r_iso_nc - 0.30 / (0.040 * 1.15)) < 0.01  # λ x 1,15
    assert any("non certifié" in a for a in u_nc["alertes"])


def test_epaisseur_pour_u_cible(cat):
    lv = next(i for i in cat.isolants("mur") if i["nom"] == "Laine de verre λ32")
    r = cat.epaisseur_isolant("mur_ext", lv, 0.18, r_support=0.20)
    assert r["epaisseur_cm"] == 18 and r["U"] <= 0.18
    ouate = next(i for i in cat.isolants("plafond") if not i["certifie"])
    assert cat.epaisseur_isolant("plafond", ouate, 0.10)["lambda_utilise"] == pytest.approx(0.046)


def test_psi(cat):
    assert cat.psi_defaut("plancher_bas_mur", "ITE")["valeur"] == 0.60
    assert cat.psi_defaut("menuiserie", "ITE", retour_isolant=True)["valeur"] == 0.15
    assert cat.psi_defaut("refend_mur", "ITI")["tag"] == "supposé"
    lignes = cat.psi_table("liaison_mur_mur", "ITE")
    assert {l["variante"] for l in lignes} == {"37_angle_rentrant", "38_angle_sortant"}


def test_produits(cat):
    assert len(cat.menuiseries()) >= 3 and cat.menuiseries()[0]["Uw"] <= cat.menuiseries()[-1]["Uw"]
    assert any(s["nom"].startswith("PAC air/eau double service") for s in cat.systemes())
