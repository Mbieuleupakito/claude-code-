import json
from pathlib import Path

import pytest

from re2020.catalogues import Catalogue
from re2020.estimation import entrees_depuis_plan
from re2020.propositions import MARGE, options_paroi, proposer
from re2020.seuils import seuils_energie

DOMENE = Path(__file__).parents[1] / "data/examples/domene_m01/domene_m01_extraction.json"


@pytest.fixture(scope="module")
def cas():
    cat = Catalogue()
    e, _ = entrees_depuis_plan(json.loads(DOMENE.read_text(encoding="utf-8")), "H1c", 220, sref=105.5, catalogue=cat)
    return cat, e, seuils_energie("H1c", 220, 105.5, "2026-10-12")


def test_front_de_pareto(cas):
    cat, e, _ = cas
    front = options_paroi(cat, "mur", e.surfaces["murs"])
    us = [o["U"] for o in front]
    couts = [o["cout"] for o in front]
    assert us == sorted(us) and couts == sorted(couts, reverse=True)  # plus isolant = plus cher


def test_isolant_non_certifie_penalise(cas):
    cat, e, _ = cas
    ouate = [o for o in options_paroi(cat, "plafond", 50) if o["isolant"].startswith("Ouate")]
    assert all(o["lambda_retenu"] == pytest.approx(0.046) for o in ouate)


def test_propositions_conformes_et_classees(cas):
    cat, e, s = cas
    r = proposer(e, s, cat)
    assert r["seuils_approx"] is True and "approx" in r["avertissement"]
    props = r["propositions"]
    assert 1 <= len(props) <= 5 and r["nb_conformes"] >= len(props)
    couts = [p["cout_eur"]["valeur"] for p in props]
    assert couts == sorted(couts)
    for p in props:
        assert p["Bbio"]["valeur"] <= s["Bbio_max"]["valeur"] * (1 - MARGE) + 0.1
        assert p["Cep"]["valeur"] <= s["Cep_max"]["valeur"] and p["Cep_nr"]["valeur"] <= s["Cep_nr_max"]["valeur"]
        assert p["cout_eur"]["tag"] == "supposé"


def test_seuils_inatteignables(cas):
    cat, e, s = cas
    dur = {k: ({**v, "valeur": 10.0} if isinstance(v, dict) else v) for k, v in s.items()}
    assert proposer(e, dur, cat)["propositions"] == []
