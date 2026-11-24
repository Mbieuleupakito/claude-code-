"""Calcul du coefficient U d'une paroi multicouche, avec pénalité isolant non certifié (+15 % sur λ)."""
from __future__ import annotations

# Résistances superficielles (m².K/W) par type de paroi : (Rsi, Rse). Rse = 0,04 comme Pléiades.
RSI_RSE = {
    "mur_ext": (0.13, 0.04),
    "mur_lnc": (0.13, 0.04),
    "plafond": (0.10, 0.04),        # flux ascendant
    "plancher_bas": (0.17, 0.04),   # flux descendant
    "plancher_interm": (0.17, 0.17),
    "cloison": (0.13, 0.04),
}
PENALITE_NON_CERTIFIE = 1.15


def couche_r(epaisseur_cm: float, materiau: dict, penaliser: bool = True) -> tuple[float, bool]:
    """(R de la couche, pénalité appliquée ?). ``materiau`` porte ``lambda_W_mK`` ou ``R_m2K_W``."""
    if materiau.get("R_m2K_W") is not None:
        return float(materiau["R_m2K_W"]), False
    lam = float(materiau["lambda_W_mK"])
    pen = penaliser and est_isolant(materiau) and materiau.get("certifie") is False
    if pen:
        lam *= PENALITE_NON_CERTIFIE
    return epaisseur_cm / 100 / lam, pen


def est_isolant(materiau: dict) -> bool:
    lam = materiau.get("lambda_W_mK")
    return lam is not None and lam <= 0.065 and materiau.get("nom", "").lower() != "air"


def u_paroi(type_paroi: str, couches: list[tuple[float, dict]], penaliser: bool = True) -> dict:
    """U (W/m².K) d'une paroi ``[(épaisseur_cm, matériau), ...]`` + alertes de certification."""
    rsi, rse = RSI_RSE[type_paroi]
    r = rsi + rse
    alertes = []
    for ep, m in couches:
        rc, pen = couche_r(ep, m, penaliser)
        r += rc
        if est_isolant(m):
            if m.get("certifie") is False:
                alertes.append(f"Isolant non certifié « {m['nom']} » : λ majoré de 15 % ({'appliqué' if pen else 'NON appliqué'}) "
                               "— Pléiades ne le fait pas automatiquement.")
            elif m.get("certifie") is None:
                alertes.append(f"Certification ACERMI inconnue pour « {m['nom']} » : si non certifié, majorer λ de 15 %.")
    return {"U": round(1 / r, 4), "R_total": round(r, 3), "alertes": alertes}
