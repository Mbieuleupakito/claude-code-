"""Lecture d'un dossier complet (plans « peints » + notice) : tout est tiré des documents."""
from pathlib import Path

import pytest

from re2020.documents import lire_dossier
from re2020.etude import Parametres, realiser_etude
from re2020.plans import extraire_plan

from .plan_synthetique import generer_dossier_peint

MINI = Path(__file__).parents[1] / "data/examples/mini_projet/dossier_mini_projet.pdf"


def v(d):
    return d["valeur"]


@pytest.fixture(scope="module")
def dossier_synthetique(tmp_path_factory):
    p = tmp_path_factory.mktemp("dossier") / "dossier.pdf"
    generer_dossier_peint(p)
    return p


def test_plan_peint_legende_et_cotes_ecrites(dossier_synthetique):
    r = extraire_plan(dossier_synthetique)
    ech = r["echelle"]["denominateur"]
    assert v(ech) == 80 and ech["tag"] == "déduit"          # aucune mention : échelle tirée des cotes écrites
    assert v(r["nord"]) == 0 and r["nord"]["tag"] == "lu"   # « NORD ↑ »
    (n,) = r["niveaux"]
    assert v(n["niveau"]) == "RDC"
    assert abs(v(n["surface_interieure_m2"]) - 11.2 * 7.2) < 0.3
    assert abs(v(n["murs_exterieurs"]["couche_pleine_m"]) - 0.40) < 0.02
    baies = sorted((b["nom"], b["orientation"], v(b["largeur_m"]), v(b["hauteur_m"])) for b in n["baies"])
    assert baies == [("F", "N", 1.2, 1.35), ("F", "S", 1.2, 1.35), ("F", "S", 1.2, 1.35), ("PV", "S", 1.8, 2.15)]
    assert all(b["hauteur_m"]["tag"] == "lu" for b in n["baies"])   # dimensions par type écrites sur le plan
    assert v(r["batiment"]["hauteur_etage_m"]) == 2.8 and v(r["batiment"]["hauteur_sous_plafond_m"]) == 2.5


def test_notice_lue(dossier_synthetique):
    d = lire_dossier(dossier_synthetique)
    i = d["infos"]
    assert (v(i["zone"]), v(i["altitude_m"]), v(i["date_pc"]), v(i["q4"])) == ("H2b", 35.0, "2026-09-15", 0.6)
    assert v(i["residentiel"]) is True
    up = {p["type_paroi"]: v(p["Up"]) for p in d["parois"]}
    assert up == {"mur_ext": 0.21, "plancher_bas": 0.18, "plafond": 0.11}
    men = {m["repere"]: m for m in d["menuiseries"]}   # tableau accolé au précédent : séparé quand même
    assert v(men["F"]["U"]) == 1.3 and v(men["F"]["g"]) == 0.48 and v(men["PV"]["quantite"]) == 1
    assert v(d["ponts_thermiques"]["total_W_K"]) == 14.72
    assert v(d["chauffage"]["generateur"]) == "pompe à chaleur" and v(d["ecs"]["type"]) == "chauffe-eau thermodynamique"
    assert v(d["ventilation"]["type"]).startswith("simple flux")
    assert all(x["tag"] == "lu" and "p.2" in x["source"] for x in (i["zone"], men["F"]["U"]))


def test_etude_sans_saisie(dossier_synthetique):
    e = realiser_etude(dossier_synthetique, Parametres())
    assert e["parametres"]["zone"] == "H2b" and e["parametres_sources"]["zone"]["tag"] == "lu"
    assert e["hypotheses"]["U_murs"]["tag"] == "lu" and e["hypotheses"]["Sref"]["tag"] == "lu"
    assert abs(v(e["hypotheses"]["Uw"]) - (1.3 * 4.86 + 1.5 * 3.87) / 8.73) < 0.01
    assert e["entrees"]["ponts_W_K"] == 14.72
    assert e["acv"]["hypotheses"]["structure"]["valeur"] == "brique"
    assert all(c["statut"] == "ok" for c in e["controles"]) and len(e["controles"]) >= 4
    assert not e["tertiaire"] and e["verdict"]["Bbio"] != "hors périmètre (tertiaire)"


def test_saisie_prioritaire_sur_le_dossier(dossier_synthetique):
    e = realiser_etude(dossier_synthetique, Parametres(zone="H1a", altitude_m=500, date_pc="2026-12-01"))
    assert e["parametres"]["zone"] == "H1a" and e["parametres_sources"]["zone"]["source"] == "saisi par le thermicien"


@pytest.mark.skipif(not MINI.exists(), reason="dossier du mini-projet non présent (exclu de git)")
def test_mini_projet_pavillon_de_bureaux():
    """Dossier d'entraînement (20 pages) : valeurs de contrôle de la notice."""
    e = realiser_etude(MINI, Parametres())
    p = e["plan"]
    assert [v(n["niveau"]) for n in p["niveaux"]] == ["RDC", "R+1"]
    assert p["pages_plans"] == ["dossier_mini_projet.pdf p.16", "dossier_mini_projet.pdf p.17"]
    assert all(abs(v(n["surface_interieure_m2"]) - 122.77) < 0.2 for n in p["niveaux"])
    assert p["batiment"]["baies_par_orientation_m2"] == {"O": 3.64, "S": 16.7, "E": 3.64, "N": 11.2}
    assert len(e["controles"]) == 18 and all(c["statut"] == "ok" for c in e["controles"])
    alleges = [v(b["allege_m"]) for n in p["niveaux"] for b in n["baies"]]
    assert alleges.count(0.9) == 7 and alleges.count(3.9) == 9 and alleges.count(0.0) == 2
    assert (e["parametres"]["zone"], e["parametres"]["altitude_m"]) == ("H1c", 214.0)
    assert e["tertiaire"] and e["verdict"]["Bbio"] == "hors périmètre (tertiaire)"
    assert e["entrees"]["ponts_W_K"] == 14.54 and e["hypotheses"]["q4"]["valeur"] == 0.8
    assert v(p["batiment"]["hauteur_sous_plafond_m"]) == 2.7 and v(p["batiment"]["hauteur_etage_m"]) == 3.0
    assert e["acv"]["hypotheses"]["structure"]["valeur"] == "ossature_bois"
    assert e["acv"]["hypotheses"]["menuiseries"]["valeur"] == "alu"


def test_garde_fou_lecture_insuffisante():
    """Un plan sans baie et aux murs aberrants ne donne pas de verdict, mais la liste de ce qu'il faut fournir."""
    import json
    plan = json.loads((Path(__file__).parents[1] / "data/examples/domene_m01/domene_m01_extraction.json").read_text(encoding="utf-8"))
    for n in plan["niveaux"]:
        n["baies"] = []
        n["murs_exterieurs"]["couche_pleine_m"]["valeur"] = 1.0
    from re2020.etude import etude_depuis_plan
    e = etude_depuis_plan(plan, Parametres(zone="H1c", altitude_m=220, date_pc="2026-10-12"))
    assert e["qualite"]["niveau"] == "insuffisante"
    assert set(e["verdict"].values()) == {"lecture insuffisante"}
    assert e["alertes"][0].startswith("LECTURE DU PLAN INSUFFISANTE")
    assert any("notice" in c for c in e["qualite"]["conseils"])
