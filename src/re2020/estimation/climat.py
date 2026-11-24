"""Données climatiques simplifiées par zone RE2020 (TOUTES supposées : ordres de grandeur, recalées
indirectement par le calage sur Charleville). À remplacer par les fichiers météo RE2020 si besoin."""
from __future__ import annotations

# Facteur de rigueur hivernale relatif à H1b (≈ rapport de degrés-jours)
RIGUEUR = {"H1a": 0.93, "H1b": 1.00, "H1c": 0.95, "H2a": 0.82, "H2b": 0.78, "H2c": 0.75, "H2d": 0.78, "H3": 0.55}
# Ensoleillement de saison de chauffe relatif à H1
SOLEIL = {"H1a": 1.0, "H1b": 1.0, "H1c": 1.05, "H2a": 1.1, "H2b": 1.15, "H2c": 1.2, "H2d": 1.3, "H3": 1.35}
# Sévérité estivale relative à H1b (besoin de froid conventionnel)
ETE = {"H1a": 0.9, "H1b": 1.0, "H1c": 1.6, "H2a": 0.8, "H2b": 1.6, "H2c": 2.2, "H2d": 3.5, "H3": 3.5}

HEURES_CHAUFFE = 5800          # octobre → mai
DT_MOYEN_H1B = 12.5            # 19 °C - température extérieure moyenne de saison (≈ 6,5 °C)
APPORTS_INTERNES_W_M2 = 4.5    # occupants + équipements, scénario conventionnel logement

# Irradiation verticale sur la saison de chauffe en H1 (kWh/m²)
IRRADIATION = {"S": 380, "SE": 300, "SO": 300, "E": 200, "O": 200, "NE": 125, "NO": 125, "N": 100}


def rigueur(zone: str, altitude_m: float) -> float:
    """Rigueur relative, majorée d'environ 6 % par 100 m au-dessus de 150 m."""
    return RIGUEUR[zone] * (1 + 0.0006 * max(0.0, altitude_m - 150))
