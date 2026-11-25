"""Compositions complètes, base des projets Pléiades, ODT et PDF sans WeasyPrint."""
import json
import zipfile
from pathlib import Path

import pytest

from re2020 import compositions as C
from re2020.catalogues import Catalogue
from re2020.pleiades import compositions as lire_compositions, resultats

RACINE = Path(__file__).resolve().parents[1]
PROJETS = json.loads((RACINE / "data/references/projets_pleiades.json").read_text(encoding="utf-8"))["projets"]
RS = {"Paroi verticale": (0.13, 0.04), "Plancher haut": (0.10, 0.04), "Plancher bas": (0.17, 0.0)}


def test_u_multicouche_egal_pleiades():
    """Notre U (Rsi + ΣR + Rse) retrouve l'Up indicatif Pléiades des projets réels (hors ossature bois)."""
    n = 0
    for p in PROJETS:
        for c in p["compositions"]:
            if c["type_paroi"] not in RS or c["nature"] in (None, "Autre", "Non définie") or "MOB" in c["nom"]:
                continue
            rsi, rse = RS[c["type_paroi"]]
            u = 1 / (rsi + rse + sum(x["R_m2K_W"] for x in c["couches"]))
            assert abs(u - c["Up_pleiades"]) <= 0.006, (p["id"], c["nom"], u, c["Up_pleiades"])
            n += 1
    assert n >= 9


def test_base_sans_donnees_client():
    brut = json.dumps(PROJETS, ensure_ascii=False).lower()
    for mot in ("adresse", "chemin sous", "balan", "maître d'ouvrage", "marcilloles"):
        assert mot not in brut


def test_systeme_reproduit_mur_pleiades():
    """Le système « parpaing + ITI » avec la laine λ32 14 cm redonne le mur du projet de référence (Up 0,21)."""
    s = next(x for x in C.systemes() if x["id"] == "mur_parpaing_iti_ossature")
    iso = [i for i in Catalogue().isolants() if i["nom"] == "Laine de verre λ32"]
    o = next(o for o in C.declinaisons(s, iso) if o["epaisseur_cm"] == 14)
    assert abs(o["U"] - 0.21) <= 0.006
    assert [c["materiau"] for c in o["couches"]] == ["Enduit extérieur", "Parpaing de 20", "Laine de verre λ32", "Placoplatre BA 13"]


def test_parement_coherent_et_ite():
    cat = Catalogue()
    for o in C.options("mur", cat.isolants(), 100):
        derniere = o["couches"][-1]["materiau"]
        if o["systeme"].endswith("doublage_colle") or o["systeme"] == "mur_gelis30_doublage":
            assert derniere == "Placoplatre BA 10"  # complexe collé
        if o["systeme"].endswith("iti_ossature"):
            assert derniere == "Placoplatre BA 13"  # ossature métallique
    ite = C.compatibles("mur", isolation="ITE")
    assert ite and all(s["isolation"] == "ITE" for s in ite)
    assert all(s["structure"] == "brique" for s in C.compatibles("mur", structure="brique"))


def test_isolant_non_certifie_penalise():
    s = next(x for x in C.systemes() if x["id"] == "plafond_combles_perdus")
    ouate = [i for i in Catalogue().isolants() if "Ouate de cellulose λ40" in i["nom"]]
    o = next(o for o in C.declinaisons(s, ouate) if o["epaisseur_cm"] == 40)
    assert o["certifie"] is False
    assert abs(o["couches"][0]["lambda_W_mK"] - 0.046) < 1e-6  # 0,040 x 1,15


def test_meilleures_par_systeme_atteignent_u():
    cat = Catalogue()
    v = C.meilleures_par_systeme("mur", cat.isolants(), 0.20, 120)
    assert len(v) >= 5 and all(o["U"] <= 0.20 for o in v)


def _odt(tmp_path, paragraphes):
    contenu = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
               'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
               + "".join(f"<text:p>{p}</text:p>" for p in paragraphes) + "</office:text></office:body></office:document-content>")
    f = tmp_path / "rapport.odt"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", contenu)
    return f


def test_lecture_rapport_pleiades_odt(tmp_path):
    from re2020.pleiades import texte_odt

    lignes = ["Mur extérieur", "Type de paroi", "Paroi verticale", "Nature de paroi", "Mur extérieur",
              "Valeur Up", "Calcul automatique - Up indicatif : 0.21 W/(m².K)", "Composante : Simple",
              "Epaisseur", "(cm)", "λ", "W/(m.K)", "ρ", "kg/m3", "CS", "Wh/(kg.K)", "U", "W/(m².K)", "R", "(m².K)/W",
              "Enduit extérieur", "2.0", "1.150", "1700", "0.278", "57.50", "0.02",
              "Parpaing de 20", "20.0", "1.053", "1300", "0.180", "5.26", "0.19",
              "Total", "", "0.22", "4.60",
              "Besoins Bioclimatique", "62,4 points", "65,6 points"]
    t = texte_odt(_odt(tmp_path, lignes))
    c = lire_compositions(t)
    assert c[0]["nom"] == "Mur extérieur" and c[0]["Up_pleiades"] == 0.21
    assert [x["materiau"] for x in c[0]["couches"]] == ["Enduit extérieur", "Parpaing de 20"]
    r = resultats(t)
    assert r["Bbio"] == 62.4 and r["Bbio_max"] == 65.6


def test_pdf_sans_weasyprint(tmp_path):
    """Windows sans GTK : le PDF est quand même produit (xhtml2pdf), avec les compositions complètes."""
    pytest.importorskip("xhtml2pdf")
    from re2020.etude import Parametres, realiser_etude
    from re2020.rapport import generer_html, generer_pdf

    from .plan_synthetique import generer_dossier_peint

    plan = tmp_path / "dossier.pdf"
    generer_dossier_peint(plan)
    e = realiser_etude(plan, Parametres())
    p0 = e["propositions"]["propositions"][0]
    assert " + " in p0["murs"]["composition"] and len(p0["murs"]["couches"]) >= 3
    assert "Compositions à créer dans la bibliothèque" in generer_html(e)
    f = generer_pdf(e, tmp_path / "f.pdf", moteur="xhtml2pdf")
    assert f.read_bytes()[:4] == b"%PDF" and f.stat().st_size > 20000
