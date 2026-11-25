from pathlib import Path

import pytest

from re2020 import localisation as L
from re2020.etude import Parametres, realiser_etude

DOMENE = Path(__file__).parents[1] / "data/examples/domene_m01/plan_ankha_M01.pdf"


def test_table_des_zones_complete():
    assert len(L.ZONE_DEPARTEMENT) == 96 and set(L.ZONE_DEPARTEMENT) == set(L.DEPARTEMENTS)
    # cas de référence du projet
    assert (L.ZONE_DEPARTEMENT["08"], L.ZONE_DEPARTEMENT["38"], L.ZONE_DEPARTEMENT["91"], L.ZONE_DEPARTEMENT["67"]) == ("H1b", "H1c", "H1a", "H1b")


@pytest.mark.parametrize("cp,dep", [("38420", "38"), ("08000", "08"), ("20090", "2A"), ("20200", "2B"), ("97400", None), ("1234", None)])
def test_departement_du_code_postal(cp, dep):
    assert L.departement_du_code_postal(cp) == dep


def test_adresse_du_chantier_plutot_que_l_architecte():
    t = ("Bureau d'Etudes Energie DEEP WATT 26 Rue Paul Helbronner 38100 Grenoble\n"
         "Adresse du projet : 3 Chemin du Haut du Theux 08000 Charleville-Mézières")
    c = L.choisir(L.candidats(t, "RSET"))
    assert (c["departement"], c["zone"], c["commune"]) == ("08", "H1b", "Charleville-Mézières")
    assert c["autres_departements"] == ["38"]


def test_formes_ecrites():
    assert L.choisir(L.candidats("Adresse Grenoble (38), terrain fictif", "notice", 3))["commune"] == "Grenoble"
    assert L.choisir(L.candidats("Construction d'une maison en Haute-Savoie", "notice"))["zone"] == "H1c"
    c = L.choisir(L.candidats("8 route de Savoie, 38420 DOMENE Adresse : 27 rue du tour de l'eau, 38400 Saint Martin d'Hères", "plan"))
    assert (c["commune"], c["code_postal"]) == ("Domene", "38420")


def test_altitude_en_ligne_simulee(monkeypatch):
    monkeypatch.delenv("RE2020_HORS_LIGNE")
    L.altitude_commune.cache_clear()
    appels = []

    def faux_get(url, timeout=6.0):
        appels.append(url)
        if "geocodage" in url:
            assert "Domene" in url and "38420" in url and "route" not in url   # seule la commune est envoyée
            return {"features": [{"geometry": {"coordinates": [5.836, 45.203]}, "properties": {"city": "Domène"}}]}
        return {"elevations": [221.4]}

    monkeypatch.setattr(L, "_get_json", faux_get)
    r = L.localiser(L.candidats("8 route de Savoie, 38420 DOMENE", "plan"))
    assert r["zone"]["valeur"] == "H1c" and r["altitude_m"]["valeur"] == 221 and r["altitude_m"]["tag"] == "déduit"
    assert len(appels) == 2
    L.altitude_commune.cache_clear()


def test_hors_ligne_pas_d_appel(monkeypatch):
    L.altitude_commune.cache_clear()
    monkeypatch.setattr(L, "_get_json", lambda *a, **k: pytest.fail("appel réseau en mode hors ligne"))
    assert "altitude_m" not in L.localiser(L.candidats("38420 DOMENE", "plan"))


@pytest.mark.skipif(not DOMENE.exists(), reason="plan client Domène non présent")
def test_etude_sans_zone_ni_altitude_ni_date():
    e = realiser_etude(DOMENE, Parametres(sref=105.5))
    src = e["parametres_sources"]
    assert e["parametres"]["zone"] == "H1c" and src["zone"]["tag"] == "déduit" and "Isère" in src["zone"]["source"]
    assert "38420" in src["lieu"]["valeur"]
    assert src["altitude_m"]["tag"] == "supposé" and src["date_pc"]["tag"] == "supposé"
    assert any(a.startswith("Altitude non trouvée") for a in e["alertes"])
