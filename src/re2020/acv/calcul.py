"""Estimation ACV : quantités par lot (déduites du plan ou supposées), Ic construction, Ic énergie.

    Ic construction = Σ_lots Σ_éléments quantité x Ic(fiche) / Sref + Ic chantier
    Ic énergie      = 50 ans x Σ consommation (kWhef/m².an) x facteur CO2 de l'usage

Trois scénarios :
- « par défaut »   : DED / forfaits partout (ce que donne Pléiades sans recherche de fiches) ;
- « top N »        : fiches spécifiques sur les N postes qui pèsent le plus (gain réaliste, cf. Boumnich
                     578,3 → < 492,5 en remplaçant des DED) ;
- « tout spécifique » : borne basse si toutes les fiches spécifiques existent.
"""
from __future__ import annotations

from ..seuils import IC_ENERGIE_MOY, ic_construction_max
from ..trace import val
from .catalogue import CatalogueACV

# Facteurs d'émission RE2020 (kg éq. CO2 / kWh ef) par usage et énergie
FACTEURS_CO2 = {"electricite": {"chauffage": 0.079, "ecs": 0.065, "eclairage": 0.069, "refroidissement": 0.064, "autres": 0.064},
                "bois": 0.030, "gaz": 0.227}
DUREE_ANS = 50
STRUCTURES = {"parpaing": "mur_parpaing", "brique": "mur_brique", "beton": "mur_beton", "ossature_bois": "mur_ossature_bois"}
PLANCHERS = {"hourdis": "plancher_hourdis", "bois": "plancher_bois"}
MENUISERIES = {"pvc": "menuiserie_pvc", "alu": "menuiserie_alu"}
TOP_N = 5


def ic_energie(conso: dict) -> dict:
    """Ic énergie (kg éq. CO2/m²) à partir des consommations estimées (kWhef/m².an)."""
    pe = conso["par_energie"]
    fe = FACTEURS_CO2["electricite"]
    ecs_elec = conso["ecs"] if pe.get("electricite", 0) >= conso["ecs"] + conso["eclairage"] - 1e-6 else 0.0
    ch_elec = max(0.0, pe["electricite"] - ecs_elec - conso["eclairage"])
    annuel = (ch_elec * fe["chauffage"] + ecs_elec * fe["ecs"] + conso["eclairage"] * fe["eclairage"]
              + pe.get("bois", 0.0) * FACTEURS_CO2["bois"] + pe.get("gaz", 0.0) * FACTEURS_CO2["gaz"])
    reseau = pe.get("reseau_chaleur", 0.0) > 0
    return {"Ic_energie": val(round(DUREE_ANS * annuel, 1), "déduit",
                              "consommations estimées x facteurs CO2 RE2020 x 50 ans"
                              + (" — SANS le réseau de chaleur (contenu CO2 à prendre dans la bibliothèque Pléiades)" if reseau else ""),
                              "faible" if reseau else "moyenne", "kgéqCO2/m²", **({"partiel": True} if reseau else {})),
            "Ic_energie_max": val(IC_ENERGIE_MOY, "déduit", "seuil moyen maison individuelle (modulations non appliquées)",
                                  "faible", "kgéqCO2/m²", note="approx")}


def quantites(plan: dict, entrees, systeme: str, nb_logements: int = 1, dossier: dict | None = None) -> list[dict]:
    """Quantités par élément (valeurs tracées). ``entrees`` : Entrees du modèle énergétique ; ``dossier`` : notice lue."""
    dossier = dossier or {}
    terrasse = any("terrasse" in p["designation"].lower() for p in dossier.get("parois", []))
    emetteurs = (dossier.get("chauffage", {}).get("emetteurs") or {}).get("valeur", "") or ""
    vmc_df = (dossier.get("ventilation", {}).get("type") or {}).get("valeur") == "double flux"
    ecs_type = (dossier.get("ecs", {}).get("type") or {}).get("valeur", "") or ""
    bardage = any("bardage" in p["designation"].lower() or "bardage" in p.get("composition", "").lower()
                  for p in dossier.get("parois", []) if p["type_paroi"] == "mur_ext")
    src_d = lambda cle: (dossier.get(cle, {}).get("type") or dossier.get(cle, {}).get("generateur") or {}).get("source", "dossier")
    niv = plan["niveaux"]
    sref = entrees.sref
    q = []

    def ajout(ident, valeur, tag, source, conf="moyenne"):
        q.append({"element": ident, "quantite": val(round(valeur, 2), tag, source, conf)})

    ite = "ITE" in niv[0]["murs_exterieurs"]["isolation"]["valeur"]
    perim = sum(f["longueur_ext_m"]["valeur"] for f in niv[0]["facades"])
    s_murs = entrees.surfaces["murs"]
    s_int = [n["surface_interieure_m2"]["valeur"] for n in niv]
    pieces = sum(len(n["pieces"]) for n in niv)

    ajout("vrd_forfait", sref, "déduit", "forfait x Sref")
    ajout("semelle_filante", perim, "déduit", "périmètre extérieur du niveau bas (plan)")
    ajout("dallage", niv[0]["surface_emprise_m2"]["valeur"], "déduit", "emprise du niveau bas (plan)")
    ajout("isolant_sous_dallage", entrees.surfaces["plancher_bas"], "déduit", "surface intérieure du niveau bas")
    ajout("__structure__", s_murs, "déduit", "murs extérieurs nets (plan, baies déduites)")
    if len(niv) > 1:
        ajout("__plancher__", sum(s_int[1:]), "déduit", "surfaces intérieures des niveaux supérieurs")
    if terrasse:
        src_t = next(p["Up"]["source"] for p in dossier["parois"] if "terrasse" in p["designation"].lower() and p.get("Up"))
        for ident in ("dalle_beton_toiture", "isolant_toiture_terrasse", "etancheite_toiture"):
            ajout(ident, entrees.surfaces["toiture"], "déduit", f"toiture-terrasse lue ({src_t}) x surface du plancher haut")
    else:
        toiture = entrees.surfaces["toiture"] * 1.15
        ajout("charpente_fermettes", toiture, "supposé", "plancher haut x 1,15 (toiture en pente supposée)", "faible")
        ajout("couverture_tuiles", toiture, "supposé", "plancher haut x 1,15 (toiture en pente supposée)", "faible")
        ajout("isolation_combles", entrees.surfaces["toiture"], "supposé", "combles perdus supposés", "faible")
    ajout("cloison_placo", 0.9 * sref, "supposé", "ratio 0,9 m² de cloison par m² de Sref", "faible")
    ajout("doublage", s_murs, "déduit", "murs extérieurs nets")
    ajout("plafond_placo", sum(s_int), "déduit", "surfaces intérieures de tous les niveaux")
    if pieces:
        ajout("porte_interieure", pieces, "lu", f"{pieces} pièce(s) étiquetée(s) sur le plan")
    else:
        ajout("porte_interieure", round(sref / 12), "supposé", "1 porte pour 12 m²", "faible")
    if ite:
        ajout("ite_isolant", s_murs, "déduit", "murs extérieurs nets (ITE lue sur le plan)")
    if not bardage:
        ajout("enduit_facade", s_murs, "supposé", "façades enduites supposées", "faible")
    ajout("__menuiserie__", sum(entrees.baies.values()), "déduit", "Σ baies (étiquettes du plan)")
    ajout("porte_entree", nb_logements, "supposé", "1 porte d'entrée par logement", "moyenne")
    ajout("carrelage", sref, "supposé", "revêtement de sol sur toute la Sref", "faible")
    ajout("peinture", 2 * s_murs + 2 * 0.9 * sref + sum(s_int), "supposé", "doublages + 2 faces de cloisons + plafonds", "faible")
    s = systeme.lower().split(" + ecs")[0]  # partie chauffage du système
    if "réseau de chaleur" in s:
        ajout("sous_station", 1, "déduit", f"réseau de chaleur lu ({src_d('chauffage')})")
    if "radiateur" in emetteurs and "joule" not in s and "électrique" not in emetteurs:
        ajout("radiateur_eau", max(1, round(sref / 15)), "supposé", "radiateurs à eau lus, 1 pour 15 m² supposé", "faible")
    if "ballon électrique" in ecs_type:
        ajout("ballon_electrique", nb_logements, "déduit", f"ECS lue ({src_d('ecs')})")
    if "pac" in s:
        ajout("pac_air_eau", nb_logements, "déduit", f"système : {systeme}")
        ajout("plancher_chauffant", sref, "supposé", "émetteur plancher chauffant supposé avec PAC", "faible")
    if "granul" in s:
        ajout("poele_granules", nb_logements, "déduit", f"système : {systeme}")
    if "radiateur" in s or "joule" in s:
        ajout("radiateur_elec", max(1, round(sref / 15)), "supposé", "1 radiateur pour 15 m²", "faible")
    if "thermodynamique" in s or "cet" in s:
        ajout("cet", nb_logements, "déduit", f"système : {systeme}")
    if vmc_df:
        ajout("cta_double_flux", 1, "déduit", f"double flux lu ({src_d('ventilation')})")
    else:
        ajout("vmc_sf", nb_logements, "supposé", "VMC simple flux hygro par logement", "moyenne")
    ajout("reseaux_cvc", sref, "déduit", "forfait x Sref")
    ajout("sanitaires", nb_logements, "déduit", "forfait par logement")
    ajout("courant_fort", sref, "déduit", "forfait x Sref")
    ajout("courant_faible", sref, "déduit", "forfait x Sref")
    return q


def estimer_acv(plan: dict, entrees, estimation: dict, date_pc, zone: str, altitude_m: float, systeme: str,
                nb_logements: int = 1, structure: str = "parpaing", plancher: str = "hourdis", menuiserie: str = "pvc",
                catalogue: CatalogueACV | None = None, dossier: dict | None = None, sources: dict | None = None) -> dict:
    """``sources`` : {structure|plancher|menuiseries: valeur tracée} quand le choix vient du dossier (sinon supposé)."""
    cat = catalogue or CatalogueACV()
    sref = entrees.sref
    rempl = {"__structure__": STRUCTURES[structure], "__plancher__": PLANCHERS[plancher], "__menuiserie__": MENUISERIES[menuiserie]}
    lignes = []
    for item in quantites(plan, entrees, systeme, nb_logements, dossier):
        ident = rempl.get(item["element"], item["element"])
        e = cat.element(ident)
        qte = item["quantite"]["valeur"]
        d, s = e["defaut"], e.get("specifique")
        lignes.append({"lot": e["lot"], "element": ident, "libelle": e["libelle"], "uf": e["uf"], "quantite": item["quantite"],
                       "fiche_defaut": d, "fiche_specifique": s,
                       "ic_defaut_kg_m2": qte * d["ic"] / sref,
                       "ic_specifique_kg_m2": qte * (s or d)["ic"] / sref})
    for l in lignes:
        l["gain_kg_m2"] = l["ic_defaut_kg_m2"] - l["ic_specifique_kg_m2"]
    top = sorted((l for l in lignes if l["gain_kg_m2"] > 0), key=lambda l: -l["gain_kg_m2"])[:TOP_N]
    ids_top = {l["element"] for l in top}

    def total(choix):
        return sum(choix(l) for l in lignes) + cat.ic_chantier

    ic_def = total(lambda l: l["ic_defaut_kg_m2"])
    ic_top = total(lambda l: l["ic_specifique_kg_m2"] if l["element"] in ids_top else l["ic_defaut_kg_m2"])
    ic_spe = total(lambda l: l["ic_specifique_kg_m2"])
    par_lot = {}
    for l in lignes:
        lot = par_lot.setdefault(l["lot"], {"libelle": cat.lots[l["lot"]], "defaut": 0.0, "specifique": 0.0})
        lot["defaut"] += l["ic_defaut_kg_m2"]
        lot["specifique"] += l["ic_specifique_kg_m2"]
    par_lot = {k: {"libelle": v["libelle"], "defaut": round(v["defaut"], 1), "specifique": round(v["specifique"], 1)}
               for k, v in sorted(par_lot.items())}

    ic_l = {k: round(par_lot.get(k, {"defaut": 0})["defaut"], 1) for k in (1, 2, 13)}
    smax = ic_construction_max(date_pc, sref / nb_logements, zone=zone, altitude_m=altitude_m,
                               ic_lot1=ic_l[1], ic_lot2=ic_l[2], ic_lot13=ic_l[13])
    ic_max = smax["Ic_construction_max"]["valeur"]
    src = "quantités du plan x fiches du catalogue ACV (valeurs SUPPOSÉES tant que non importées d'INIES)"
    tag_fiches = "lu" if all(l["fiche_defaut"]["tag"] == "lu" for l in lignes) else "supposé"
    conf = "moyenne" if tag_fiches == "lu" else "faible"

    def v(x):
        return val(round(x, 1), tag_fiches, src, conf, "kgéqCO2/m²", fourchette=[round(x * 0.8, 1), round(x * 1.2, 1)])

    verdict = {}
    for nom, x in (("par_defaut", ic_def), ("top_fiches", ic_top), ("tout_specifique", ic_spe)):
        verdict[nom] = "sous le seuil" if x * 1.2 <= ic_max else "au-dessus du seuil" if x * 0.8 > ic_max else "incertain"
    ene = ic_energie(estimation["consommations_kWhef_m2"] | {"par_energie": estimation["par_energie_kWhef_m2"]})
    alertes = []
    if tag_fiches == "supposé":
        alertes.append("ACV : fiches du catalogue = ordres de grandeur supposés. Importer les fiches INIES/Pléiades "
                       "(CatalogueACV.importer_csv) avant de s'y fier.")
    if verdict["par_defaut"] != "sous le seuil":
        alertes.append(f"Ic construction avec DED ({ic_def:.0f}) proche ou au-dessus du seuil ({ic_max:.0f}) : "
                       f"rechercher des FDES pour {', '.join(l['libelle'] for l in top[:3])}.")
    return {
        "Ic_construction": {"par_defaut": v(ic_def), "top_fiches": v(ic_top), "tout_specifique": v(ic_spe)},
        "Ic_construction_max": smax["Ic_construction_max"],
        "verdict": verdict,
        "Ic_chantier": val(cat.ic_chantier, "supposé", "forfait chantier (ordre de grandeur)", "faible", "kgéqCO2/m²"),
        "par_lot": par_lot,
        "elements": [{**l, "ic_defaut_kg_m2": round(l["ic_defaut_kg_m2"], 2), "ic_specifique_kg_m2": round(l["ic_specifique_kg_m2"], 2),
                      "gain_kg_m2": round(l["gain_kg_m2"], 2)} for l in sorted(lignes, key=lambda l: (l["lot"], l["element"]))],
        "recommandations": [{"element": l["libelle"], "lot": l["lot"], "gain_kg_m2": round(l["gain_kg_m2"], 1),
                             "remplacer": f"{l['fiche_defaut']['type']} → {l['fiche_specifique']['type']} « {l['fiche_specifique']['nom']} »"}
                            for l in top],
        "Ic_energie": ene["Ic_energie"], "Ic_energie_max": ene["Ic_energie_max"],
        "hypotheses": {"structure": (sources or {}).get("structure") or val(structure, "supposé", "nature des murs non lue", "faible"),
                       "plancher_intermediaire": (sources or {}).get("plancher") or val(plancher, "supposé", "non lu", "faible"),
                       "menuiseries": (sources or {}).get("menuiseries") or val(menuiserie, "supposé", "matériau des menuiseries non lu", "faible")},
        "alertes": alertes,
    }
