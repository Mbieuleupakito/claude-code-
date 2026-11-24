"""Seuils RE2020 (maison individuelle ou accolée) : Bbio_max, Cep,nr_max, Cep_max, Ic construction_max.

Source : annexe à l'article R.172-4 (chapitres 1 à 3), lue le 2026-11-24.

Hauteur sous plafond (décret 2026-200) : les modulations MbHSP / McHSP / MiHSP s'appliquent aux PC
déposés à partir du 1er juillet 2026. Leur formule n'est PAS encore connue : on peut les fournir
(lues dans Pléiades, ou retrouvées avec ``hsp_implicites``) ; sinon le résultat est marqué « approx »
(CLAUDE.md, règle 4). Pour un PC antérieur, elles ne s'appliquent pas.
"""
from __future__ import annotations

from datetime import date

from .trace import val

SOURCE = "annexe art. R.172-4 (chap. 1 à 3)"
DATE_DECRET_HSP = date(2026, 7, 1)

BBIO_MOY = 63.0
CEP_NR_MOY = 55.0
CEP_MOY = 75.0
IC_ENERGIE_MOY = 160.0  # 200 si réseau de chaleur urbain (jusqu'en 2027)

ZONES = ["H1a", "H1b", "H1c", "H2a", "H2b", "H2c", "H2d", "H3"]
# classe d'altitude : 0 = <= 400 m ; 1 = 400-800 m ; 2 = > 800 m
MB_GEO = {
    0: dict(zip(ZONES, [0.15, 0.2, 0.2, -0.05, 0.0, -0.1, 0.05, -0.1])),
    1: dict(zip(ZONES, [0.4, 0.5, 0.45, 0.15, 0.3, 0.05, 0.1, -0.05])),
    2: dict(zip(ZONES, [0.75, 0.85, 0.75, 0.55, 0.65, 0.35, 0.25, 0.1])),
}
MC_GEO = {
    0: dict(zip(ZONES, [0.1, 0.15, 0.1, -0.05, 0.0, -0.1, -0.1, -0.15])),
    1: dict(zip(ZONES, [0.4, 0.5, 0.4, 0.15, 0.3, 0.05, 0.0, -0.1])),
    2: dict(zip(ZONES, [0.75, 0.85, 0.75, 0.55, 0.6, 0.35, 0.25, 0.15])),
}
# Ic construction moyen (kg éq. CO2/m²) selon l'année de dépôt du PC
IC_CONSTR_MOY = [(2022, 640.0), (2025, 530.0), (2028, 475.0), (2031, 415.0)]


def zone_normalisee(zone: str) -> str:
    z = zone.replace("-", "").replace(" ", "")
    z = z[:2].upper() + z[2:].lower()
    if z not in ZONES:
        raise ValueError(f"zone climatique inconnue : {zone!r} (attendu : {ZONES})")
    return z


def _date(d) -> date:
    if isinstance(d, date):
        return d
    if isinstance(d, int):
        return date(d, 1, 1)
    return date.fromisoformat(str(d))


def alt_class(altitude_m: float) -> int:
    return 0 if altitude_m <= 400 else (1 if altitude_m <= 800 else 2)


def mbsurf_moy(s_moy: float) -> float:
    if s_moy <= 100:
        return (49 - 0.49 * s_moy) / BBIO_MOY
    if s_moy <= 150:
        return (18 - 0.18 * s_moy) / BBIO_MOY
    return -9 / BBIO_MOY


def mcsurf_moy(s_moy: float) -> float:
    if s_moy <= 100:
        return (49.5 - 0.55 * s_moy) / CEP_NR_MOY
    if s_moy <= 150:
        return (14.5 - 0.2 * s_moy) / CEP_NR_MOY
    return -15.5 / CEP_NR_MOY


def _comb(s_combles, sref):
    return 0.4 * s_combles / sref if (s_combles and sref) else 0.0


def _hsp_applicable(date_pc, mb_hsp, mc_hsp) -> tuple[bool, float, float, bool]:
    """(applicable, mb, mc, approx)."""
    applicable = _date(date_pc) >= DATE_DECRET_HSP
    if not applicable:
        if mb_hsp or mc_hsp:
            raise ValueError("MbHSP/McHSP ne s'appliquent qu'aux PC déposés à partir du 2026-07-01")
        return False, 0.0, 0.0, False
    approx = mb_hsp is None or mc_hsp is None
    return True, mb_hsp or 0.0, mc_hsp or 0.0, approx


def _bases(zone, altitude_m, s_moy, s_combles, sref, bruit_h2d_h3):
    a = alt_class(altitude_m)
    comb = _comb(s_combles, sref)
    mb_bruit = 0.1 if bruit_h2d_h3 and zone in ("H2d", "H3") else 0.0
    fb = 1 + MB_GEO[a][zone] + comb + mbsurf_moy(s_moy) + mb_bruit
    fc = 1 + MC_GEO[a][zone] + comb + mcsurf_moy(s_moy)
    return fb, fc


def seuils_energie(zone, altitude_m, s_moy, date_pc, s_combles=0.0, sref=None,
                   mb_hsp=None, mc_hsp=None, bruit_h2d_h3=False) -> dict:
    """Bbio_max, Cep,nr_max, Cep_max (valeurs tracées) et drapeau ``approx``.

    ``s_moy`` : surface moyenne des logements (= Sref pour une maison individuelle).
    ``mb_hsp`` / ``mc_hsp`` : modulations hauteur sous plafond si connues (None = inconnues).
    """
    zone = zone_normalisee(zone)
    applicable, mb, mc, approx = _hsp_applicable(date_pc, mb_hsp, mc_hsp)
    fb, fc = _bases(zone, altitude_m, s_moy, s_combles, sref, bruit_h2d_h3)
    if approx:
        note = "approx : MbHSP/McHSP inconnus (décret 2026-200) → seuil sous-estimé probable"
    elif applicable:
        note = f"MbHSP={mb} ; McHSP={mc} fournis"
    else:
        note = "PC < 2026-07-01 : pas de modulation HSP"
    conf = "faible" if approx else "haute"
    return {
        "Bbio_max": val(round(BBIO_MOY * (fb + mb), 1), "déduit", SOURCE, conf, note=note),
        "Cep_nr_max": val(round(CEP_NR_MOY * (fc + mc), 1), "déduit", SOURCE, conf, "kWhep/m².an", note=note),
        "Cep_max": val(round(CEP_MOY * (fc + mc), 1), "déduit", SOURCE, conf, "kWhep/m².an", note=note),
        "approx": approx,
    }


def hsp_implicites(zone, altitude_m, s_moy, bbio_max=None, cep_max=None, s_combles=0.0, sref=None,
                   bruit_h2d_h3=False) -> dict:
    """Retrouve MbHSP / McHSP à partir de seuils calculés par Pléiades (RSET ou fiche résultats)."""
    zone = zone_normalisee(zone)
    fb, fc = _bases(zone, altitude_m, s_moy, s_combles, sref, bruit_h2d_h3)
    out = {}
    if bbio_max is not None:
        out["mb_hsp"] = round(bbio_max / BBIO_MOY - fb, 3)
    if cep_max is not None:
        out["mc_hsp"] = round(cep_max / CEP_MOY - fc, 3)
    return out


def ic_construction_moyen(date_pc) -> float:
    an = _date(date_pc).year
    return [v for (y, v) in IC_CONSTR_MOY if an >= y][-1] if an >= 2022 else IC_CONSTR_MOY[0][1]


def ic_construction_max(date_pc, s_moy, s_combles=0.0, sref=None, zone="H1a", altitude_m=0,
                        ic_lot1=0.0, ic_lot2=0.0, ic_lot13=0.0, mi_hsp=0.0, mi_ded=0.0) -> dict:
    """Ic construction_max (kg éq. CO2/m²). Toujours « approx » : formule d'assemblage non relue."""
    zone = zone_normalisee(zone)
    moy = ic_construction_moyen(date_pc)
    mi_surf = 0.36 - 3.6 * s_moy / 1000 if s_moy <= 120 else -0.072
    mi_comb = _comb(s_combles, sref)
    mi_geo_kg = 30.0 if (zone in ("H2d", "H3") and altitude_m <= 400) else 0.0
    mi_infra = max(0.0, ic_lot2 - 40)
    mi_vrd = max(0.0, ic_lot1 - 20)
    mi_pv = max(0.0, ic_lot13 - 20)
    # Mi sans unité (comb, surf, hsp, ded) relatifs ; Mi_geo/infra/vrd/pv en kg/m².
    ic_max = moy * (1 + mi_comb + mi_surf + mi_hsp + mi_ded) + mi_geo_kg + mi_infra + mi_vrd + mi_pv
    return {
        "Ic_construction_max": val(round(ic_max, 1), "déduit", SOURCE, "moyenne", "kgéqCO2/m²",
                                   note="approx : assemblage à relire (écart 0,7 sur Boumnich)"),
        "moyen": moy,
        "approx": True,
    }


if __name__ == "__main__":
    print(seuils_energie("H1b", 100, 212.2, "2026-11-17", mb_hsp=0.079, mc_hsp=0.039))
    print(ic_construction_max(2026, 229.2))
