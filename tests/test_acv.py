import json
from pathlib import Path

import pytest

from re2020.acv import CatalogueACV, estimer_acv, ic_energie
from re2020.estimation import entrees_depuis_plan, estimer
from re2020.estimation.modele import CALAGE, entrees_calage

DOMENE = Path(__file__).parents[1] / "data/examples/domene_m01/domene_m01_extraction.json"


@pytest.fixture(scope="module")
def domene():
    plan = json.loads(DOMENE.read_text(encoding="utf-8"))
    e, _ = entrees_depuis_plan(plan, "H1c", 220, sref=105.5)
    return plan, e, estimer(e)


def acv(domene, **kw):
    plan, e, est = domene
    return estimer_acv(plan, e, est, "2026-10-12", "H1c", 220, e.systeme["nom"], **kw)


def test_ordres_de_grandeur(domene):
    r = acv(domene)
    ic = {k: v["valeur"] for k, v in r["Ic_construction"].items()}
    assert ic["tout_specifique"] < ic["top_fiches"] < ic["par_defaut"]
    assert 450 < ic["par_defaut"] < 750          # Boumnich (Pléiades, avec DED) : 578,3
    gain = 1 - ic["top_fiches"] / ic["par_defaut"]
    assert 0.10 < gain < 0.30                    # Boumnich : −15 % en remplaçant des DED
    assert 50 < r["Ic_energie"]["valeur"] < 90   # Boumnich : 68,5
    assert set(r["par_lot"]) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
    assert len(r["recommandations"]) == 5
    gains = [x["gain_kg_m2"] for x in r["recommandations"]]
    assert gains == sorted(gains, reverse=True)


def test_valeurs_supposees_signalees(domene):
    r = acv(domene)
    assert r["Ic_construction"]["par_defaut"]["tag"] == "supposé" and r["Ic_construction"]["par_defaut"]["confiance"] == "faible"
    assert any("INIES" in a for a in r["alertes"])
    assert r["hypotheses"]["structure"]["tag"] == "supposé"


def test_quantites_tracees(domene):
    r = acv(domene)
    q = {l["element"]: l["quantite"] for l in r["elements"]}
    assert q["menuiserie_pvc"]["valeur"] == pytest.approx(20.15) and q["menuiserie_pvc"]["tag"] == "déduit"
    assert q["porte_interieure"]["tag"] == "lu"            # pièces étiquetées sur le plan
    assert q["ite_isolant"]["tag"] == "déduit"             # ITE lue sur le plan
    assert q["pac_air_eau"]["valeur"] == 1


def test_choix_constructifs(domene):
    base = acv(domene)["Ic_construction"]["par_defaut"]["valeur"]
    assert acv(domene, structure="ossature_bois")["Ic_construction"]["par_defaut"]["valeur"] < base
    assert acv(domene, structure="beton")["Ic_construction"]["par_defaut"]["valeur"] > base
    assert acv(domene, menuiserie="alu")["Ic_construction"]["par_defaut"]["valeur"] > base


def test_import_csv_fiches_reelles(domene, tmp_path):
    plan, e, est = domene
    cat = CatalogueACV()
    csv = tmp_path / "fiches.csv"
    csv.write_text("element;type;nom;id_inies;ic_kg_uf;role\nmur_parpaing;FDES collective;Mur blocs béton;12345;30,5;specifique\n",
                   encoding="utf-8")
    assert cat.importer_csv(csv) == 1
    assert cat.element("mur_parpaing")["specifique"] == {"type": "FDES collective", "nom": "Mur blocs béton", "id_inies": "12345",
                                                         "ic": 30.5, "tag": "lu", "source": "fiche importée (fiches.csv)"}
    r = estimer_acv(plan, e, est, "2026-10-12", "H1c", 220, e.systeme["nom"], catalogue=cat)
    mur = next(l for l in r["elements"] if l["element"] == "mur_parpaing")
    assert mur["fiche_specifique"]["tag"] == "lu"
    with pytest.raises(KeyError):
        csv.write_text("element;type;nom;id_inies;ic_kg_uf;role\ninconnu;FDES;x;1;1;specifique\n", encoding="utf-8")
        cat.importer_csv(csv)


def test_ic_energie_charleville():
    est = estimer(entrees_calage(json.loads(CALAGE.read_text(encoding="utf-8"))))
    r = ic_energie(est["consommations_kWhef_m2"] | {"par_energie": est["par_energie_kWhef_m2"]})
    # 50 ans x (11,2 x 0,079 + 4,5 x 0,065 + 1,8 x 0,069) ≈ 65 kg/m²
    assert abs(r["Ic_energie"]["valeur"] - 65.2) < 1.0
