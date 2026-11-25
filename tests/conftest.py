import pytest


@pytest.fixture(autouse=True)
def hors_ligne(monkeypatch):
    """Les tests n'appellent jamais Internet (altitude en ligne simulée là où c'est testé)."""
    monkeypatch.setenv("RE2020_HORS_LIGNE", "1")


@pytest.fixture(autouse=True)
def sans_convertisseur_dwg(monkeypatch, tmp_path):
    """Les tests ne dépendent pas d'un LibreDWG / ODA installé sur le poste (cas « DWG non convertible » testé)."""
    import shutil

    import re2020.formats as formats
    import re2020.outils_dwg as outils

    monkeypatch.setattr(outils, "DOSSIER", tmp_path / "pas_de_libredwg")
    monkeypatch.setattr(formats, "trouver_oda", lambda: None)
    vrai_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None if n in ("dwg2dxf", "ODAFileConverter") else vrai_which(n, *a, **k))
