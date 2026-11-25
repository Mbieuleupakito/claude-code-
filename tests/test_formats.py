"""Autres formats que le PDF : DXF (plans), DWG (conversion locale), Word / Excel (notice), images (non lues)."""
import pytest

from re2020.documents import lire_dossier
from re2020.etude import Parametres, realiser_etude
from re2020.formats import preparer
from re2020.plans.textes import famille, meme_repere

from .plan_synthetique import generer_dxf, generer_notice_docx, generer_notice_xlsx


@pytest.fixture(scope="module")
def dossier(tmp_path_factory):
    d = tmp_path_factory.mktemp("formats")
    generer_dxf(d / "plan.dxf")
    generer_notice_docx(d / "notice.docx")
    generer_notice_xlsx(d / "menuiseries.xlsx")
    (d / "plan.dwg").write_bytes(b"AC1032 pas un vrai dwg")
    (d / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    return d


def v(x):
    return x["valeur"]


def test_familles():
    assert famille("F12") == "F" and famille("PF1b") == "PF" and famille("Mext21") == "MEXT"
    assert meme_repere("F1", "F") and meme_repere("PV", "PV") and not meme_repere("PF1", "F")


def test_tri_des_fichiers(dossier):
    p = preparer([dossier / n for n in ("plan.dxf", "notice.docx", "menuiseries.xlsx", "plan.dwg", "photo.jpg")], dossier)
    assert [f.name for f in p["plans"]] == ["plan_dxf.pdf"]
    assert {f.name for f in p["documents"]} == {"plan_dxf.pdf", "notice.docx", "menuiseries.xlsx"}
    raisons = dict(p["non_lus"])
    assert "ODA File Converter" in raisons["plan.dwg"] and "image" in raisons["photo.jpg"]


def test_notice_word_et_excel(dossier):
    d = lire_dossier([dossier / "notice.docx", dossier / "menuiseries.xlsx"])
    assert (v(d["infos"]["zone"]), v(d["infos"]["date_pc"])) == ("H3", "2027-03-02")
    assert {p["type_paroi"]: v(p["Up"]) for p in d["parois"]} == {"mur_ext": 0.19, "plafond": 0.10}
    assert v(d["chauffage"]["generateur"]) == "pompe à chaleur"
    men = {m["repere"]: m for m in d["menuiseries"]}
    assert v(men["F"]["U"]) == 1.2 and v(men["PF"]["quantite"]) == 1
    assert "menuiseries.xlsx (Menuiseries)" in men["F"]["U"]["source"]


def test_plan_dxf_murs_en_traits(dossier):
    e = realiser_etude([dossier / n for n in ("plan.dxf", "notice.docx", "menuiseries.xlsx", "plan.dwg", "photo.jpg")],
                       Parametres(), dossier_travail=dossier)
    p = e["plan"]
    assert v(p["echelle"]["denominateur"]) == 100 and p["echelle"]["denominateur"]["tag"] == "lu"   # échelle exacte du rendu
    assert v(p["nord"]) == 0                                                                        # bloc « NORD »
    (n,) = p["niveaux"]
    assert v(n["niveau"]) == "RDC" and abs(v(n["surface_interieure_m2"]) - 9.4 * 7.4) < 0.3
    assert abs(v(n["murs_exterieurs"]["couche_pleine_m"]) - 0.30) < 0.02
    baies = sorted((b["nom"], b["orientation"], v(b["largeur_m"]), v(b["allege_m"])) for b in n["baies"])
    assert baies == [("F1", "S", 1.2, 0.9), ("F2", "E", 1.0, 1.0), ("PF1", "S", 2.0, 0.0)]
    assert abs(v(e["hypotheses"]["Uw"]) - (1.62 * 1.2 + 1.25 * 1.2 + 4.3 * 1.4) / 7.17) < 0.01
    assert all(c["statut"] == "ok" for c in e["controles"])
    assert len(e["fichiers"]["non_lus"]) == 2 and any(a.startswith("Fichier non lu : plan.dwg") for a in e["alertes"])
