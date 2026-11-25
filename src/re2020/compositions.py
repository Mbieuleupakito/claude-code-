"""Compositions complètes de parois (pas seulement l'isolant) : systèmes constructifs de
``data/catalogues/systemes_constructifs.json`` (enduit + bloc/brique/béton/ossature + isolant + parement), dont
les couches fixes viennent des rapports Pléiades DEEP-WATT. La couche isolante est déclinée en familles
compatibles avec la mise en œuvre (ITI sur ossature, doublage collé, ITE sous enduit, soufflage…) x épaisseurs.

Les parements suivent la logique de chantier : BA13 sur ossature métallique, BA10 pour un complexe collé,
enduit plâtre derrière une ITE.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .catalogues.parois import RSI_RSE

DATA = Path(__file__).resolve().parents[2] / "data" / "catalogues" / "systemes_constructifs.json"
RS = {"mur": RSI_RSE["mur_ext"], "plafond": RSI_RSE["plafond"], "plancher_bas": (0.17, 0.0)}  # terre-plein : pas de Rse (Pléiades)


@lru_cache(maxsize=1)
def systemes() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["systemes"]


@lru_cache(maxsize=1)
def projets_reference() -> dict:
    f = DATA.parents[1] / "references" / "projets_pleiades.json"
    try:
        return {p["id"]: p["libelle"] for p in json.loads(f.read_text(encoding="utf-8"))["projets"]}
    except (OSError, KeyError, ValueError):
        return {}


def _plage(p):
    a, b, pas = p
    out, x = [], a
    while x <= b + 1e-9:
        out.append(round(x, 1))
        x += pas
    return out


def _r_couche(c: dict, ep_cm: float | None = None, lam: float | None = None) -> float:
    if c.get("R") is not None and ep_cm is None:
        return float(c["R"])
    return (ep_cm if ep_cm is not None else c["ep_cm"]) / 100 / (lam if lam is not None else c["lambda"])


def compatibles(paroi: str, isolation: str | None = None, structure: str | None = None) -> list[dict]:
    """Systèmes d'une paroi cohérents avec le projet : mode d'isolation lu sur le plan (ITE / ITI) et structure
    lue dans la notice. Sans information, tous les systèmes de la paroi."""
    s = [x for x in systemes() if x["paroi"] == paroi]
    if paroi == "mur" and isolation in ("ITE", "ITI"):
        s2 = [x for x in s if x["isolation"] == isolation]
        s = s2 or s
    if paroi == "mur" and structure:
        s2 = [x for x in s if x["structure"] == structure]
        s = s2 or s
    return s


def declinaisons(sys_: dict, isolants: list[dict]) -> list[dict]:
    """Toutes les variantes d'un système : isolant compatible x épaisseur → U, R, couches, coût."""
    rsi, rse = RS[sys_["paroi"]]
    fixes = [c for c in sys_["couches"] if not c.get("isolant")]
    r_fixe = sum(_r_couche(c) for c in fixes)
    var = next((c for c in sys_["couches"] if c.get("isolant")), None)
    out = []

    def ligne(iso, ep, lam_eff, r_iso):
        couches = []
        for c in sys_["couches"]:
            if c.get("isolant"):
                nom = iso["nom"] + (f" entre {c['mixte']['materiau'].lower()}s ({round(100 * c['mixte']['part'])} %)" if c.get("mixte") else "")
                couches.append({"materiau": nom, "epaisseur_cm": ep, "lambda_W_mK": round(lam_eff, 4), "R_m2K_W": round(r_iso, 2),
                                "tag": "déduit", "isolant": True, "certifie": iso["certifie"]})
            else:
                couches.append({"materiau": c["materiau"], "epaisseur_cm": c["ep_cm"], "lambda_W_mK": c.get("lambda"),
                                "R_m2K_W": round(_r_couche(c), 2), "tag": c.get("tag", "supposé"), **({"note": c["note"]} if c.get("note") else {})})
        r = rsi + rse + r_fixe + r_iso
        return {"systeme": sys_["id"], "systeme_nom": sys_["nom"], "structure": sys_["structure"], "isolation": sys_["isolation"],
                "ref_projet": projets_reference().get(sys_.get("ref_projet"), sys_.get("ref_projet")), "isolant": iso["nom"] if iso else None, "epaisseur_cm": ep,
                "certifie": iso["certifie"] if iso else True, "biosource": iso.get("biosource", False) if iso else False,
                "U": round(1 / r, 3), "R_total": round(r, 2), "couches": couches,
                "epaisseur_totale_cm": round(sum(c["epaisseur_cm"] for c in couches), 1),
                "composition": " + ".join(f"{c['materiau']} {c['epaisseur_cm']:g} cm" for c in couches),
                "_prix_m2": (sys_.get("cout_hors_isolant_eur_m2"), iso.get("prix_eur_m2_cm") if iso else 0.0)}

    if var is None:
        return [ligne(None, None, None, 0.0)] if sys_.get("sans_isolant") else []
    for iso in isolants:
        if not set(var["poses"]) & set(iso.get("poses", [])):
            continue
        lam = iso["lambda_W_mK"] * (1.0 if iso["certifie"] else 1.15)  # +15 % si non certifié
        for ep in _plage(var["ep_cm"]):
            lam_eff = lam
            if var.get("mixte"):
                m = var["mixte"]
                lam_eff = (1 - m["part"]) * lam + m["part"] * m["lambda"]
            out.append(ligne(iso, ep, lam_eff, ep / 100 / lam_eff))
    return out


def cout(o: dict, surface_m2: float) -> float | None:
    fixe, prix_iso = o["_prix_m2"]
    if fixe is None or prix_iso is None:
        return None
    return round((fixe + prix_iso * (o["epaisseur_cm"] or 0)) * surface_m2)


def options(paroi: str, isolants: list[dict], surface_m2: float, isolation: str | None = None,
            structure: str | None = None) -> list[dict]:
    out = []
    for s in compatibles(paroi, isolation, structure):
        for o in declinaisons(s, isolants):
            o = dict(o)
            o["cout"] = cout(o, surface_m2)
            out.append(o)
    return out


def meilleures_par_systeme(paroi: str, isolants: list[dict], u_cible: float, surface_m2: float,
                           isolation: str | None = None, structure: str | None = None) -> list[dict]:
    """Pour chaque système compatible : la variante la moins chère (puis la plus mince) qui atteint U ≤ u_cible."""
    res = []
    for s in compatibles(paroi, isolation, structure):
        ok = [dict(o, cout=cout(o, surface_m2)) for o in declinaisons(s, isolants) if o["U"] <= u_cible + 1e-9]
        if ok:
            res.append(min(ok, key=lambda o: (o["cout"] if o["cout"] is not None else 1e12, o["epaisseur_totale_cm"])))
    return sorted(res, key=lambda o: (o["cout"] if o["cout"] is not None else 1e12))
