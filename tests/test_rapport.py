import json
from pathlib import Path

import pdfplumber
import pytest

from re2020.etude import Parametres, etude_depuis_plan
from re2020.rapport import generer_html, generer_pdf

DOMENE = Path(__file__).parents[1] / "data/examples/domene_m01/domene_m01_extraction.json"

ORDRE_PLEIADES = ["1. Bibliothèque projet", "2. Données par défaut", "3. Géométrie", "4. Toitures",
                  "5. Parties de bâtiment", "6. Masques", "7. Ponts thermiques", "8. RE2020", "9. Calcul Th-BCE",
                  "10. Propositions", "11. ACV", "12. Hypothèses à valider"]


@pytest.fixture(scope="module")
def etude():
    plan = json.loads(DOMENE.read_text(encoding="utf-8"))
    return etude_depuis_plan(plan, Parametres(zone="H1-c", altitude_m=220, date_pc="2026-10-12", projet="Domène M01", sref=105.5))


def test_etude_complete(etude):
    assert set(etude["verdict"]) == {"Bbio", "Cep", "Cep_nr"}
    assert etude["seuils"]["approx"] is True
    assert any("approx" in a for a in etude["alertes"]) and any("ACERMI" in a for a in etude["alertes"])
    assert etude["propositions"]["propositions"]


def test_html_dans_l_ordre_de_saisie(etude):
    html = generer_html(etude)
    positions = [html.index(t) for t in ORDRE_PLEIADES]
    assert positions == sorted(positions)
    assert "Mext21" in html and "supposé" in html and "pas un calcul réglementaire" in html


def test_pdf(etude, tmp_path):
    pdf = generer_pdf(etude, tmp_path / "rapport.pdf")
    with pdfplumber.open(pdf) as d:
        assert len(d.pages) >= 3
        texte = "".join(p.extract_text() for p in d.pages)
    assert "Feuille de route RE2020" in texte and "Hypothèses à valider" in texte
