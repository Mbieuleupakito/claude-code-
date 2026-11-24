"""Seuils RE2020 (maison individuelle ou accolée) : Bbio_max, Cep_max, Cep,nr_max, Ic construction_max.

Source : annexe à l'article R.172-4 (chapitres 1 à 3), lue le 2026-11-24.
LIMITE : les coefficients de hauteur sous plafond (MbHSP, McHSP, MiHSP, décret 2026-200, PC déposés
à partir du 1er juillet 2026) ne sont PAS connus. Ils sont passés en paramètres (défaut 0.0) et
doivent être renseignés dès qu'on a le texte officiel. Tant que ce n'est pas fait, le résultat est
marqué "approx".
"""
from __future__ import annotations

BBIO_MOY = 63.0
CEP_NR_MOY = 55.0
CEP_MOY = 75.0
IC_ENERGIE_MOY = 160.0  # 200 si réseau de chaleur urbain (jusqu'en 2027)

ZONES = ["H1a", "H1b", "H1c", "H2a", "H2b", "H2c", "H2d", "H3"]
# altitude : 0 = <400 m ; 1 = 400-800 m ; 2 = >800 m
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
IC_CONSTR_MOY = [(2022, 640.0), (2025, 530.0), (2028, 475.0), (2031, 415.0)]


def alt_class(altitude_m: float) -> int:
    return 0 if altitude_m < 400 else (1 if altitude_m <= 800 else 2)


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


def seuils_energie(zone, altitude_m, s_moy, s_combles=0.0, sref=None,
                   mb_hsp=0.0, mc_hsp=0.0, bruit_h2d_h3=False):
    """Retourne Bbio_max, Cep,nr_max, Cep_max (+ drapeau approx si HSP non renseigné)."""
    a = alt_class(altitude_m)
    comb = 0.4 * s_combles / sref if (s_combles and sref) else 0.0
    mb_bruit = 0.1 if bruit_h2d_h3 and zone in ("H2d", "H3") else 0.0
    bbio = BBIO_MOY * (1 + MB_GEO[a][zone] + comb + mbsurf_moy(s_moy) + mb_bruit + mb_hsp)
    f_c = 1 + MC_GEO[a][zone] + comb + mcsurf_moy(s_moy) + mc_hsp
    return {
        "Bbio_max": round(bbio, 1),
        "Cep_nr_max": round(CEP_NR_MOY * f_c, 1),
        "Cep_max": round(CEP_MOY * f_c, 1),
        "approx": mb_hsp == 0.0 and mc_hsp == 0.0,
    }


def ic_construction_max(annee_pc, s_moy, s_combles=0.0, sref=None, zone="H1a", altitude_m=0,
                        ic_lot1=0.0, ic_lot2=0.0, ic_lot13=0.0, mi_hsp=0.0, mi_ded=0.0):
    moy = [v for (y, v) in IC_CONSTR_MOY if annee_pc >= y][-1] if annee_pc >= 2022 else 640.0
    mi_surf = 0.36 - 3.6 * s_moy / 1000 if s_moy <= 120 else -0.072
    mi_comb = 0.4 * s_combles / sref if (s_combles and sref) else 0.0
    mi_geo_kg = 30.0 if (zone in ("H2d", "H3") and altitude_m < 400) else 0.0
    mi_infra = max(0.0, ic_lot2 - 40)
    mi_vrd = max(0.0, ic_lot1 - 20)
    mi_pv = max(0.0, ic_lot13 - 20)
    # NB : les Mi sans unité (comb, surf, hsp, ded) sont relatifs ; Mi_geo/infra/vrd/pv sont en kg/m².
    ic_max = moy * (1 + mi_comb + mi_surf + mi_hsp + mi_ded) + mi_geo_kg + mi_infra + mi_vrd + mi_pv
    return {"Ic_construction_max": round(ic_max, 1), "moyen": moy,
            "approx": True,  # formule d'assemblage exacte non lue : à vérifier dans l'annexe
            }


if __name__ == "__main__":
    # Charleville (H1b, <400 m, 212.2 m2, 1 logement) : RSET -> Bbio_max 71.6 ; Cep_nr_max 49.9 ; Cep_max 68.1
    print(seuils_energie("H1b", 100, 212.2, mb_hsp=0.079, mc_hsp=0.039))
    print(seuils_energie("H1b", 100, 212.2))  # sans HSP : 66.6 / 47.7 / 65.1
    # Boumnich : Ic construction_max 492.5 (Sref 229.2, PC 2025-2027)
    print(ic_construction_max(2026, 229.2))
