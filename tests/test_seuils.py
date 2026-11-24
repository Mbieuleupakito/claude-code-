from datetime import date

import pytest

from re2020.seuils import (hsp_implicites, ic_construction_max, ic_construction_moyen, seuils_energie,
                           zone_normalisee)

PC_CHARLEVILLE = date(2026, 11, 17)  # RSET : dépôt de PC 17/11/2026


def v(r, k):
    return r[k]["valeur"]


def test_charleville_energie_avec_hsp():
    r = seuils_energie("H1-b", 100, 212.2, PC_CHARLEVILLE, mb_hsp=0.079, mc_hsp=0.039)
    assert abs(v(r, "Bbio_max") - 71.6) < 0.2  # RSET
    assert abs(v(r, "Cep_nr_max") - 49.9) < 0.2
    assert abs(v(r, "Cep_max") - 68.1) < 0.2
    assert r["approx"] is False and r["Bbio_max"]["confiance"] == "haute"


def test_hsp_inconnu_apres_decret_est_approx():
    r = seuils_energie("H1b", 100, 212.2, PC_CHARLEVILLE)
    assert r["approx"] is True and r["Bbio_max"]["confiance"] == "faible"
    assert (v(r, "Bbio_max"), v(r, "Cep_nr_max"), v(r, "Cep_max")) == (66.6, 47.8, 65.1)
    assert "approx" in r["Bbio_max"]["note"]


def test_pc_avant_decret_sans_hsp():
    r = seuils_energie("H1b", 100, 212.2, "2026-06-30")
    assert r["approx"] is False
    with pytest.raises(ValueError):
        seuils_energie("H1b", 100, 212.2, "2026-06-30", mb_hsp=0.05)


def test_tags():
    r = seuils_energie("H2a", 900, 90, PC_CHARLEVILLE)
    for k in ("Bbio_max", "Cep_nr_max", "Cep_max"):
        assert r[k]["tag"] == "déduit" and r[k]["source"]


def test_hsp_implicites_charleville():
    h = hsp_implicites("H1b", 100, 212.2, bbio_max=71.6, cep_max=68.1)
    assert abs(h["mb_hsp"] - 0.079) < 0.003 and abs(h["mc_hsp"] - 0.039) < 0.003


def test_zone():
    assert zone_normalisee("h2-d") == "H2d"
    with pytest.raises(ValueError):
        zone_normalisee("H4")


@pytest.mark.parametrize("an,attendu", [(2022, 640), (2024, 640), (2025, 530), (2027, 530), (2028, 475), (2031, 415)])
def test_ic_moyen_par_annee(an, attendu):
    assert ic_construction_moyen(an) == attendu


def test_boumnich_ic_construction():
    r = ic_construction_max(2026, 229.2)
    assert abs(v(r, "Ic_construction_max") - 492.5) < 1.0  # écart 0.7 : terme manquant à identifier
    assert r["approx"] is True
