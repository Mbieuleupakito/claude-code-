"""Chaîne complète d'une étude : plan → hypothèses → seuils → estimation → propositions (→ rapport)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .catalogues import Catalogue
from .estimation import entrees_depuis_plan, estimer
from .plans import extraire_plan
from .propositions import proposer
from .seuils import ic_construction_max, seuils_energie, zone_normalisee
from .trace import val


@dataclass
class Parametres:
    zone: str
    altitude_m: float
    date_pc: str                       # AAAA-MM-JJ (dépôt du permis de construire)
    projet: str = "Projet sans nom"
    sref: float | None = None          # sinon surface intérieure du plan
    nb_logements: int = 1
    hsp_m: float = 2.50
    systeme: str | None = None
    mb_hsp: float | None = None        # modulations HSP si connues (Pléiades)
    mc_hsp: float | None = None
    retour_isolant_menuiseries: bool | None = None
    echelle: int | None = None
    angle_nord_deg: float | None = None


def realiser_etude(pdf: str | Path, p: Parametres, catalogue: Catalogue | None = None) -> dict:
    plan = extraire_plan(pdf, hsp_m=p.hsp_m, denominateur=p.echelle, angle_nord_deg=p.angle_nord_deg)
    return etude_depuis_plan(plan, p, catalogue)


def etude_depuis_plan(plan: dict, p: Parametres, catalogue: Catalogue | None = None) -> dict:
    cat = catalogue or Catalogue()
    zone = zone_normalisee(p.zone)
    entrees, hyp = entrees_depuis_plan(plan, zone, p.altitude_m, sref=p.sref, catalogue=cat, systeme=p.systeme,
                                       retour_isolant_menuiseries=p.retour_isolant_menuiseries)
    entrees.nb_logements = p.nb_logements
    sref = entrees.sref
    seuils = seuils_energie(zone, p.altitude_m, sref / p.nb_logements, p.date_pc, mb_hsp=p.mb_hsp, mc_hsp=p.mc_hsp)
    ic = ic_construction_max(p.date_pc, sref / p.nb_logements, zone=zone, altitude_m=p.altitude_m)
    estimation = estimer(entrees)
    props = proposer(entrees, seuils, cat)

    alertes = list(plan["alertes"]) + list(hyp.get("alertes", []))
    if seuils["approx"]:
        alertes.append("Seuils « approx » : MbHSP/McHSP (décret 2026-200) inconnus pour ce PC → les lire dans Pléiades "
                       "et les fournir pour un seuil exact.")
    alertes.append("Certification des isolants à vérifier (ACERMI) : si non certifié, majorer λ de 15 % dans Pléiades "
                   "(non automatique).")
    verdict = {}
    for k, kmax in (("Bbio", "Bbio_max"), ("Cep", "Cep_max"), ("Cep_nr", "Cep_nr_max")):
        est, smax = estimation[k], seuils[kmax]["valeur"]
        b, h = est["fourchette"]
        verdict[k] = ("conforme probable" if h <= smax else "non conforme probable" if b > smax else "incertain")

    return {
        "projet": p.projet,
        "date_rapport": date.today().isoformat(),
        "parametres": asdict(p),
        "plan": plan,
        "hypotheses": hyp,
        "entrees": {"sref": sref, "surfaces_m2": {k: round(v, 1) for k, v in entrees.surfaces.items()},
                    "U": {k: round(v, 3) for k, v in entrees.U.items()}, "Sw": entrees.Sw,
                    "ponts_W_K": round(entrees.ponts_W_K, 1), "baies_m2": entrees.baies},
        "seuils": seuils,
        "ic_construction_max": ic,
        "estimation": estimation,
        "verdict": verdict,
        "propositions": props,
        "alertes": alertes,
        "manquants": plan["manquants"],
        "_trace_sref": val(sref, hyp["Sref"]["tag"], hyp["Sref"]["source"], hyp["Sref"]["confiance"], "m²"),
    }
