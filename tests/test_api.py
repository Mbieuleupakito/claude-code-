import pytest
from fastapi.testclient import TestClient

from re2020.api import creer_app

from .plan_synthetique import generer


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(creer_app(tmp_path_factory.mktemp("etudes")))


@pytest.fixture(scope="module")
def plan_pdf(tmp_path_factory):
    p = tmp_path_factory.mktemp("plan") / "plan.pdf"
    generer(p)
    return p.read_bytes()


def test_page_accueil(client):
    r = client.get("/")
    assert r.status_code == 200 and "Lancer l'étude" in r.text and "H2d" in r.text
    assert "http" not in r.text.split("<script>")[0].lower().replace("http-equiv", "")  # aucune ressource externe


def test_etude_complete(client, plan_pdf):
    r = client.post("/api/etudes", files={"fichier": ("plan.pdf", plan_pdf, "application/pdf")},
                    data={"zone": "H1b", "altitude_m": "150", "date_pc": "2026-11-17", "projet": "Test"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j["verdict"]) == {"Bbio", "Cep", "Cep_nr"} and j["seuils_approx"] is True
    pdf = client.get(j["liens"]["rapport"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(j["liens"]["controle"]).headers["content-type"] == "image/png"
    assert client.get(j["liens"]["etude"]).json()["projet"] == "Test"
    assert any(e["id"] == j["id"] and e["statut"] == "ok" for e in client.get("/api/etudes").json())


def test_formats_refuses(client):
    for nom, msg in (("plan.dwg", "DWG"), ("plan.dxf", "DXF"), ("plan.pdf", "pas un PDF")):
        r = client.post("/api/etudes", files={"fichier": (nom, b"garbage", "application/octet-stream")},
                        data={"zone": "H1b", "altitude_m": "150", "date_pc": "2026-11-17"})
        assert r.status_code == 415 and msg in r.json()["detail"]


def test_plan_sans_murs(client):
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 100, "Ech : 1 : 100")
    c.save()
    r = client.post("/api/etudes", files={"fichier": ("vide.pdf", buf.getvalue(), "application/pdf")},
                    data={"zone": "H1b", "altitude_m": "150", "date_pc": "2026-11-17"})
    assert r.status_code == 422 and "non exploitable" in r.json()["detail"]
    assert client.get("/api/etudes/inexistant").status_code == 404
    assert client.get("/api/etudes/..").status_code == 404
