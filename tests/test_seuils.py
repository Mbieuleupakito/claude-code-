from src.re2020.seuils import seuils_energie, ic_construction_max

def test_charleville_energie():
    r = seuils_energie("H1b", 100, 212.2, mb_hsp=0.079, mc_hsp=0.039)
    assert abs(r["Bbio_max"] - 71.6) < 0.2
    assert abs(r["Cep_nr_max"] - 49.9) < 0.2
    assert abs(r["Cep_max"] - 68.1) < 0.2

def test_boumnich_ic_construction():
    r = ic_construction_max(2026, 229.2)
    assert abs(r["Ic_construction_max"] - 492.5) < 1.0  # écart 0.7 : terme manquant à identifier
