"""Moteur d'estimation simplifié : déperditions par poste, besoins, Bbio, Cep / Cep,nr, avec fourchette.

Ce n'est PAS le moteur Th-BCE : c'est une méthode saisonnière (pertes x rigueur - apports utilisés),
calée sur le RSET de Charleville. Les écarts avec Pléiades sont montrés par ``references.py``.

    H     = Σ U·A + Σ ψ·L + 0,34·(qv + q_perm)                        (W/K)
    Q     = K_CAL · H · ΔT · heures · rigueur(zone, altitude)         (kWh)   K_CAL : intermittence, consignes
    G     = apports internes + Σ A_baie · Sw · Fs · I(orientation)    (kWh)
    Bch   = (Q - η(G/Q, τ) · G) / Sref
    Bbio  = 2·Bch + 2·Bfr + 5·Bécl
    Cep   = Σ consommations x coefficient d'énergie primaire (électricité 2,3 ; bois 1 ; gaz 1)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..trace import val
from . import climat

CALAGE = Path(__file__).resolve().parents[3] / "data" / "references" / "charleville_calage.json"

FS_BAIES = 0.65           # cadre + occultations + masques proches (supposé)
INERTIE_KJ_K_M2 = 110.0   # inertie moyenne (supposé)
PERM_FACTEUR = 0.823      # débit de perméabilité = facteur x Q4 x ATbât (lu : RSET Charleville 204,29 / (0,6 x 413,5))
QV_M3H_M2 = 52.18 / 212.2  # simple flux hygro B, débit conventionnel par m² (lu : RSET Charleville)
COEF_EP = {"electricite": 2.3, "bois": 1.0, "gaz": 1.0}
COEF_EP_NR = {"electricite": 2.3, "bois": 0.0, "gaz": 1.0}


@dataclass
class Entrees:
    sref: float
    zone: str
    altitude_m: float
    surfaces: dict          # {"murs": m², "toiture": m², "plancher_bas": m²}
    U: dict                 # {"murs", "toiture", "plancher_bas", "baies"} en W/m².K
    baies: dict             # {orientation: m²}
    Sw: float
    ponts_W_K: float        # Σ ψ·L
    q4: float = 0.6
    qv_m3h: float | None = None
    nb_logements: int = 1
    systeme: dict = field(default_factory=dict)
    # incertitudes relatives (demi-largeur) pour la fourchette
    incertitude: dict = field(default_factory=lambda: {"U": 0.10, "ponts": 0.25, "geometrie": 0.05, "apports": 0.15, "modele": 0.08})


def _eta(gamma: float, tau_h: float) -> float:
    a = 1 + tau_h / 15
    if abs(gamma - 1) < 1e-6:
        return a / (a + 1)
    return (1 - gamma ** a) / (1 - gamma ** (a + 1))


def deperditions(e: Entrees) -> dict:
    s_baies = sum(e.baies.values())
    at = e.surfaces["murs"] + e.surfaces["toiture"] + s_baies
    qv = e.qv_m3h if e.qv_m3h is not None else QV_M3H_M2 * e.sref
    d = {
        "murs": e.U["murs"] * e.surfaces["murs"],
        "toiture": e.U["toiture"] * e.surfaces["toiture"],
        "plancher_bas": e.U["plancher_bas"] * e.surfaces["plancher_bas"],
        "baies": e.U["baies"] * s_baies,
        "ponts_thermiques": e.ponts_W_K,
        "ventilation": 0.34 * qv,
        "permeabilite": 0.34 * PERM_FACTEUR * e.q4 * at,
    }
    d["total"] = sum(d.values())
    return d


def _brut(e: Entrees, k_cal: float) -> dict:
    dep = deperditions(e)
    H = dep["total"]
    Q = k_cal * H * climat.DT_MOYEN_H1B * climat.HEURES_CHAUFFE * climat.rigueur(e.zone, e.altitude_m) / 1000
    gi = climat.APPORTS_INTERNES_W_M2 * e.sref * climat.HEURES_CHAUFFE / 1000
    gs = sum(a * e.Sw * FS_BAIES * climat.IRRADIATION[o] * climat.SOLEIL[e.zone] for o, a in e.baies.items())
    G = gi + gs
    tau = INERTIE_KJ_K_M2 * e.sref / 3.6 / H
    eta = _eta(G / Q, tau) if Q > 0 else 0.0
    bch = max(0.0, (Q - eta * G) / e.sref)
    s_baies = sum(e.baies.values())
    ratio = s_baies / e.sref
    bfr = 11.1 * climat.ETE[e.zone] * e.Sw * s_baies / e.sref  # 11,1 : calé sur Charleville (Bfr 1,0)
    becl = min(4.0, max(1.0, 1.8 * (0.214 / max(ratio, 0.05)) ** 0.3))  # 1,8 pour 21,4 % de baies (Charleville)
    return {"deperditions_W_K": dep, "Q_kWh": Q, "apports_kWh": G, "eta": eta,
            "Bch": bch, "Bfr": bfr, "Becl": becl, "Bbio": 2 * bch + 2 * bfr + 5 * becl}


def besoin_ecs_kwh(sref: float, nb_logements: int = 1) -> float:
    """Besoin ECS annuel (kWh), loi simplifiée calée sur Charleville (≈ 2 500 kWh pour 212 m²)."""
    return nb_logements * 1250 + 6 * sref


def consommations(e: Entrees, besoins: dict) -> dict:
    s = e.systeme or {"nom": "PAC air/eau double service", "energie": "electricite", "rendement_chauffage": 2.58, "rendement_ecs": 2.6}
    ecs = besoin_ecs_kwh(e.sref, e.nb_logements) / e.sref
    par_energie = {"electricite": 0.0, "bois": 0.0, "gaz": 0.0}
    if s.get("energie") == "bois":
        pb = s.get("part_bois", 0.7)
        ch_bois = besoins["Bch"] * pb / s["rendement_chauffage_bois"]
        ch_elec = besoins["Bch"] * (1 - pb) / s["rendement_chauffage"]
        par_energie["bois"] += ch_bois
        par_energie["electricite"] += ch_elec
        ch = ch_bois + ch_elec
    else:
        ch = besoins["Bch"] / s["rendement_chauffage"]
        par_energie[s.get("energie", "electricite")] += ch
    ecs_ef = ecs / s["rendement_ecs"]
    par_energie["electricite"] += ecs_ef + besoins["Becl"]
    cep = sum(v * COEF_EP[k] for k, v in par_energie.items())
    cep_nr = sum(v * COEF_EP_NR[k] for k, v in par_energie.items())
    return {"chauffage": ch, "ecs": ecs_ef, "eclairage": besoins["Becl"], "par_energie": par_energie,
            "Cep": cep, "Cep_nr": cep_nr, "systeme": s["nom"]}


def _k_cal() -> float:
    """Facteur de calage : reproduit exactement le besoin de chauffage du RSET Charleville."""
    c = json.loads(CALAGE.read_text(encoding="utf-8"))
    e = entrees_calage(c)
    cible = c["besoins_kWh_m2"]["chauffage"] * c["sref"]
    # Bch·Sref = k·Q1 - η(k)·G : résolution par dichotomie
    lo, hi = 0.2, 2.0
    for _ in range(60):
        k = (lo + hi) / 2
        if _brut(e, k)["Bch"] * c["sref"] < cible:
            lo = k
        else:
            hi = k
    return (lo + hi) / 2


def entrees_calage(c: dict) -> Entrees:
    return Entrees(sref=c["sref"], zone=c["zone"], altitude_m=c["altitude_m"],
                   surfaces={k: c["surfaces_m2"][k] for k in ("murs", "toiture", "plancher_bas")},
                   U=c["U"], baies=c["baies_par_orientation_m2"], Sw=c["Sw_baies"],
                   ponts_W_K=c["ponts_thermiques"]["deperdition_W_K"], q4=c["permeabilite"]["q4_m3h_m2"],
                   qv_m3h=c["ventilation"]["qv_m3h"])


K_CAL = _k_cal()


def _perturbee(e: Entrees, param: str, sens: int) -> tuple[Entrees, float]:
    """Entrées avec un seul paramètre décalé de ±incertitude ; retourne aussi le facteur sur K_CAL."""
    r = sens * e.incertitude[param]
    if param == "U":
        return replace(e, U={k: v * (1 + r) for k, v in e.U.items()}), 1.0
    if param == "ponts":
        return replace(e, ponts_W_K=e.ponts_W_K * (1 + r)), 1.0
    if param == "geometrie":
        return replace(e, surfaces={k: v * (1 + r) for k, v in e.surfaces.items()}), 1.0
    if param == "apports":
        return replace(e, Sw=e.Sw * (1 - r)), 1.0
    return e, 1 + r  # "modele" : incertitude propre au modèle simplifié


def estimer(e: Entrees, sources: str = "plan + hypothèses") -> dict:
    """Estimation complète, avec fourchette = ± somme quadratique des sensibilités à chaque incertitude."""
    centre = _brut(e, K_CAL)
    conso = consommations(e, centre)
    cles = ("Bch", "Bfr", "Becl", "Bbio", "Cep", "Cep_nr")
    ecarts = {c: 0.0 for c in cles}
    sensibilites = {}
    for p in e.incertitude:
        res = []
        for sens in (-1, 1):
            ep, fk = _perturbee(e, p, sens)
            b = _brut(ep, K_CAL * fk)
            cs = consommations(ep, b)
            res.append({**{c: b[c] for c in cles[:4]}, "Cep": cs["Cep"], "Cep_nr": cs["Cep_nr"]})
        for c in cles:
            d = abs(res[1][c] - res[0][c]) / 2
            ecarts[c] += d * d
        sensibilites[p] = round(abs(res[1]["Bbio"] - res[0]["Bbio"]) / 2, 1)
    ref = {**{c: centre[c] for c in cles[:4]}, "Cep": conso["Cep"], "Cep_nr": conso["Cep_nr"]}

    def fourchette(c, unite, arrondi=1):
        d = ecarts[c] ** 0.5
        return val(round(ref[c], arrondi), "déduit", f"modèle simplifié calé sur Charleville ({sources})", "moyenne", unite,
                   fourchette=[round(max(0.0, ref[c] - d), arrondi), round(ref[c] + d, arrondi)])

    dep = {k: round(v, 1) for k, v in centre["deperditions_W_K"].items()}
    return {
        "deperditions_W_K": dep,
        "deperditions_W_K_m2": round(dep["total"] / e.sref, 2),
        "besoins_kWh_m2": {"chauffage": fourchette("Bch", "kWh/m².an"), "froid": fourchette("Bfr", "kWh/m².an"),
                           "eclairage": fourchette("Becl", "kWh/m².an")},
        "Bbio": fourchette("Bbio", "points"),
        "Cep": fourchette("Cep", "kWhep/m².an"),
        "Cep_nr": fourchette("Cep_nr", "kWhep/m².an"),
        "sensibilite_Bbio_points": sensibilites,
        "consommations_kWhef_m2": {k: round(v, 1) for k, v in conso.items() if isinstance(v, float)},
        "systeme": conso["systeme"],
        "parametres": {"K_CAL": round(K_CAL, 4), "eta_apports": round(centre["eta"], 3), "Fs_baies": FS_BAIES,
                       "incertitudes": e.incertitude},
        "avertissement": "Estimation simplifiée pour préparer la saisie : résultats officiels = Pléiades / moteur CSTB.",
    }
