import json
from dataclasses import replace

import pytest

from re2020.estimation import entrees_depuis_plan, estimer
from re2020.estimation.modele import CALAGE, entrees_calage
from re2020.estimation.references import comparer

C = json.loads(CALAGE.read_text(encoding="utf-8"))
DOMENE = CALAGE.parents[1] / "examples/domene_m01/domene_m01_extraction.json"


@pytest.fixture(scope="module")
def charleville():
    return estimer(entrees_calage(C), "RSET")


def test_calage_charleville(charleville):
    r = charleville
    assert abs(r["besoins_kWh_m2"]["chauffage"]["valeur"] - 28.9) < 0.2
    assert abs(r["besoins_kWh_m2"]["froid"]["valeur"] - 1.0) < 0.2
    assert abs(r["besoins_kWh_m2"]["eclairage"]["valeur"] - 1.8) < 0.1
    assert abs(r["Bbio"]["valeur"] - 68.9) < 0.5
    assert abs(r["Cep"]["valeur"] - 40.3) < 0.5 and abs(r["Cep_nr"]["valeur"] - 40.3) < 0.5


def test_deperditions_par_poste_charleville(charleville):
    for poste, ref in C["deperditions_W_K"].items():
        assert abs(charleville["deperditions_W_K"][poste] - ref) / ref < 0.05, poste


def test_fourchette_et_tags(charleville):
    b = charleville["Bbio"]
    assert b["tag"] == "déduit" and b["fourchette"][0] < b["valeur"] < b["fourchette"][1]
    assert set(charleville["sensibilite_Bbio_points"]) == {"U", "ponts", "geometrie", "apports", "modele"}


def test_sens_physique():
    e = entrees_calage(C)
    base = estimer(e)["Bbio"]["valeur"]
    assert estimer(replace(e, zone="H3"))["Bbio"]["valeur"] < base
    assert estimer(replace(e, U={**e.U, "murs": 0.30}))["Bbio"]["valeur"] > base
    assert estimer(replace(e, altitude_m=900))["Bbio"]["valeur"] > base


def test_domene_depuis_plan_et_alerte_psi():
    plan = json.loads(DOMENE.read_text(encoding="utf-8"))
    e, h = entrees_depuis_plan(plan, "H1c", 220, sref=105.5)
    assert h["U_murs"]["tag"] == "supposé" and h["Sref"]["tag"] == "lu"
    assert not h["alertes"]
    e2, h2 = entrees_depuis_plan(plan, "H1c", 220, sref=105.5, retour_isolant_menuiseries=False)
    assert h2["ratio_psi"]["valeur"] > 0.33 and any("Ratio Ψ" in a for a in h2["alertes"])
    assert estimer(e2)["Bbio"]["valeur"] > estimer(e)["Bbio"]["valeur"]


def test_comparaison_references_affiche_les_ecarts():
    lignes = comparer()
    charl = lignes[0]
    assert abs(charl["ecart_Bbio"]) < 0.5
    domene = next(l for l in lignes if l["cas"] == "Domène M01 (plan ANKHA)")
    assert domene["dans_fourchette"]           # au moins une variante Pléiades dans la fourchette
    assert abs(domene["ecart_Bbio"]) < 15      # écart actuel −10,5 : affiché, pas caché
    assert any(l["Bbio_estime"] is None and "plan absent" in l["note"] for l in lignes)
