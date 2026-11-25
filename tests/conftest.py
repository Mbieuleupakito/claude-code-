import pytest


@pytest.fixture(autouse=True)
def hors_ligne(monkeypatch):
    """Les tests n'appellent jamais Internet (altitude en ligne simulée là où c'est testé)."""
    monkeypatch.setenv("RE2020_HORS_LIGNE", "1")
