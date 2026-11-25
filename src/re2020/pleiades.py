"""Lecture des rapports Pléiades (export .odt « rapport d'étude » ou leur texte) : compositions de parois couche
par couche, parois opaques (Up, surfaces), menuiseries, ponts thermiques, résultats Bbio/Cep/Ic.

Sert à enrichir la base (``data/references/projets_pleiades.json``) avec des compositions RÉELLES de projets
conformes, et à vérifier le calcul d'U de l'outil contre Pléiades. Tout est lu sur le poste.

Usage : python -m re2020.pleiades rapport1.odt rapport2.odt … [--json sortie.json]
"""
from __future__ import annotations

import html
import json
import re
import sys
import zipfile
from pathlib import Path


def texte_odt(chemin: str | Path) -> str:
    """Texte d'un .odt/.ods : une ligne par paragraphe, cellules de tableau séparées par « | »."""
    x = zipfile.ZipFile(chemin).read("content.xml").decode("utf-8")
    x = re.sub(r"<text:tab/>", "\t", x)
    x = re.sub(r"<text:line-break/>", " ", x)
    x = re.sub(r"</text:p>|</text:h>|<table:table-row[^>]*>", "\n", x)
    x = re.sub(r"</table:table-cell>", " | ", x)
    t = html.unescape(re.sub(r"<[^>]+>", "", x))
    return re.sub(r"\n\s*\n+", "\n", t)


def _lignes(t: str) -> list[str]:
    return [l.strip(" |\t") for l in t.splitlines()]


def _num(s: str) -> float | None:
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- compositions de paroi

def compositions(t: str) -> list[dict]:
    """Blocs « Composante : … » de la bibliothèque projet : couches (épaisseur cm, λ, ρ, CS, R) et Up indicatif."""
    L = [l for l in _lignes(t) if l != ""]
    out = []
    for i, l in enumerate(L):
        if not l.startswith("Composante"):
            continue
        # en-tête de la composition : on remonte jusqu'au nom (ligne avant « Type de paroi »)
        j = i
        while j > 0 and L[j] != "Type de paroi":
            j -= 1
        if j == 0 or i - j > 40:
            continue
        nom = L[j - 1]
        entete = L[j:i]
        champ = lambda cle: next((entete[k + 1] for k, x in enumerate(entete[:-1]) if x == cle), None)
        up = None
        if (m := re.search(r"Up indicatif\s*:\s*([\d.,]+)", " ".join(entete))):
            up = _num(m.group(1))
        # couches : après les 6 en-têtes de colonnes (Epaisseur, λ, ρ, CS, U, R) → groupes de 7 lignes
        k = i + 1
        while k < len(L) and L[k] != "(m².K)/W" and k < i + 16:
            k += 1
        k += 1  # après l'unité de la dernière colonne « R (m².K)/W »
        couches = []
        while k + 6 < len(L) and L[k] != "Total" and not L[k].startswith("Composante"):
            nomc, vals = L[k], [_num(v) for v in L[k + 1:k + 7]]
            if any(v is None for v in vals[:2]):
                break
            ep, lam, rho, cs, u, r = vals
            couches.append({"materiau": nomc, "epaisseur_cm": ep, "lambda_W_mK": lam, "masse_vol_kg_m3": rho,
                            "chaleur_massique_Wh_kgK": cs, "R_m2K_W": r})
            k += 7
        if not couches:
            continue
        r_tot = None
        if k < len(L) and L[k] == "Total" and k + 2 < len(L):
            r_tot = _num(L[k + 2])
        out.append({"nom": nom, "type_paroi": champ("Type de paroi"), "nature": champ("Nature de paroi"),
                    "origine_isolant": champ("Origine des données sur l’isolant") or champ("Origine des données sur l'isolant"),
                    "composante": l.split(":", 1)[-1].strip(), "couches": couches, "R_total_m2K_W": r_tot,
                    "Up_pleiades": up, "epaisseur_totale_cm": round(sum(c["epaisseur_cm"] for c in couches), 1)})
    return out


# --------------------------------------------------------------------------- tableaux de synthèse

def parois_opaques(t: str) -> list[dict]:
    """Tableau « Parois opaques » : nature, libellé, système constructif, ép. isolant, R, Up, surface, b."""
    L = _lignes(t)
    try:
        d = next(i for i, l in enumerate(L) if l == "Parois opaques")
        f = next(i for i in range(d, len(L)) if L[i].startswith("Parois vitrées"))
    except StopIteration:
        return []
    bloc = [l for l in L[d + 1:f]]
    # saute l'en-tête (jusqu'à « Coeff. b »)
    try:
        bloc = bloc[next(i for i, l in enumerate(bloc) if l.startswith("Coeff")) + 1:]
    except StopIteration:
        return []
    out, nature = [], None
    i = 0
    while i < len(bloc):
        l = bloc[i]
        if l in ("Plancher haut", "Plancher bas", "Paroi verticale", "Plancher intermédiaire"):
            nature = l
            i += 1
            continue
        if l == "":
            i += 1
            continue
        vals = bloc[i:i + 8]
        if len(vals) < 8:
            break
        lib, systeme, ep, r, orig, up, surf, b = vals
        if _num(up) is None:
            i += 1
            continue
        out.append({"nature": nature, "libelle": lib, "systeme_constructif": systeme, "ep_isolant_cm": _num(ep),
                    "R_isolant": _num(r), "origine": orig, "Up": _num(up), "surface_m2": _num(surf), "b": b})
        i += 8
    return out


def resultats(t: str) -> dict:
    """Résultats « Projet / Max » (Bbio, Cep, Cep,nr, Ic énergie, besoins et consommations par poste) et déperditions."""
    out = {}
    L = [l for l in _lignes(t) if l != ""]
    lignes_res = {"Besoins Bioclimatique": "Bbio", "Consommation énergie Primaire non renouvelable": "Cep_nr",
                  "Consommation énergie Primaire": "Cep", "Indice Carbone Energie": "Ic_energie",
                  "Indice Carbone Construction": "Ic_construction", "Degrés-heures": "DH"}
    postes = {"Besoins de chauffage": "besoin_chauffage", "Besoins de climatisation": "besoin_froid",
              "Besoins d’éclairage": "besoin_eclairage", "Consommations de chauffage": "conso_chauffage",
              "Consommations d’ECS": "conso_ecs", "Consommations de climatisation": "conso_froid",
              "Consommations d’éclairage": "conso_eclairage"}
    for i, l in enumerate(L[:-2]):
        for lib, cle in lignes_res.items():
            if l == lib and cle not in out:
                vals = [_num(re.sub(r"[^\d,.]", "", x.split("kg")[0].split("kWh")[0].split("points")[0]) or "x") for x in L[i + 1:i + 3]]
                out[cle] = vals[0]
                if len(vals) > 1 and vals[1] is not None:
                    out[cle + "_max"] = vals[1]
        for lib, cle in postes.items():
            if l == lib and cle not in out:
                m = re.search(r"(?:(\d+)\s*x\s*)?([\d,.]+)", L[i + 1])
                if m:  # « 2 x 20,5 kWh/m² » : coefficient de pondération du Bbio x besoin
                    out[cle] = _num(m.group(2))
    for cle, motif in {"deperditions_W_K": r"Deperditions totales\s*:\s*([\d.,]+)",
                       "deperditions_opaques_W_K": r"Deperditions parois opaques\s*:\s*([\d.,]+)",
                       "deperditions_vitrees_W_K": r"Deperditions parois vitr[ée]es\s*:\s*([\d.,]+)",
                       "deperditions_ponts_W_K": r"Deperditions ponts thermiques\s*:\s*([\d.,]+)"}.items():
        if (m := re.search(motif, t)):
            out[cle] = _num(m.group(1))
    return out


def projet(t: str) -> dict:
    """Département / zone, altitude, générateurs (sans l'adresse : donnée client)."""
    out = {}
    if (m := re.search(r"(\d{2}|2[AB]) - ([^(\n|]+?)\s*\((H\d\s?[abc])\)", t)):
        out["departement"], out["zone"] = m.group(1), m.group(3).replace(" ", "")
    if (m := re.search(r"Altitude\s*:\s*(\d+)\s*m", t)):
        out["altitude_m"] = int(m.group(1))
    out["generateurs"] = sorted(set(g.strip() for g in re.findall(r"G[ée]n[ée]rateur [^:\n]*:\s*([^\n|]+)", t)))
    return out


def menuiseries(t: str) -> list[dict]:
    """Tableau « Parois vitrées » : libellé, protection, cadre, vitrage, Uw, Sw, Tl, surface."""
    L = [l for l in _lignes(t)]
    try:
        d = next(i for i, l in enumerate(L) if l.startswith("Parois vitrées"))
        d = next(i for i in range(d, len(L)) if L[i].startswith("Coeff b")) + 1
    except StopIteration:
        return []
    out = []
    i = d
    while i < len(L) and len(out) < 200:
        l = L[i]
        if re.match(r"^(Nord|Sud|Est|Ouest|Nord-Est|Nord-Ouest|Sud-Est|Sud-Ouest|Horizontal)[^:]*:", l):
            typ = l.split(":", 1)[1].strip()
            debut = i + 1
            if not typ:  # « Ouest : » puis « Fenêtre » sur la ligne suivante
                typ, debut = L[i + 1], i + 2
            v = [x for x in L[debut:debut + 16] if x != ""]
            if len(v) >= 11 and _num(v[6]) is not None:
                out.append({"orientation": l.split(":")[0].strip(), "type": typ, "libelle": v[0],
                            "protection": v[1], "cadre": v[2], "vitrage": v[3], "Ug": _num(v[4]), "Uw": _num(v[6]),
                            "origine_Uw": v[7], "Sw": _num(v[8]), "Tl": _num(v[9]), "surface_m2": _num(v[10])})
            i += 12
            continue
        if l.startswith(("Ponts thermiques", "Synthèse", "Bibliothèques")):
            break
        i += 1
    return out


def ponts_thermiques(t: str) -> list[dict]:
    """Ponts thermiques structurels de la bibliothèque : nom (référence Th-Bât) et ψ."""
    L = [l for l in _lignes(t) if l != ""]
    out = []
    for i, l in enumerate(L[:-4]):
        if re.match(r"^(ITE|ITI|ITR|MOB|Rupteur|Planelle)\b|^\d+(\.\d+)+\s*-", l) and _num(L[i + 3]) is not None \
                and L[i + 2] in ("CSTB", "Th-Bât", "Valeur par défaut", "Calcul", "Avis Technique", "Saisie"):
            out.append({"nom": l, "classe": L[i + 1], "origine": L[i + 2], "psi_W_mK": _num(L[i + 3])})
    return out


def lire_rapport(chemin: str | Path) -> dict:
    chemin = Path(chemin)
    t = texte_odt(chemin) if chemin.suffix.lower() in (".odt", ".ods") else chemin.read_text(encoding="utf-8", errors="ignore")
    return {"fichier": chemin.name, "projet": projet(t), "compositions": compositions(t),
            "parois_opaques": parois_opaques(t), "menuiseries": menuiseries(t), "ponts_thermiques": ponts_thermiques(t),
            "resultats": resultats(t)}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sortie = None
    if "--json" in args:
        i = args.index("--json")
        sortie = args[i + 1]
        del args[i:i + 2]
    res = [lire_rapport(a) for a in args]
    for r in res:
        print(f"== {r['fichier']} : {r['projet']} ; {len(r['compositions'])} composition(s), {len(r['parois_opaques'])} paroi(s), "
              f"{len(r['menuiseries'])} menuiserie(s), {len(r['ponts_thermiques'])} Ψ ; {r['resultats']}")
        for c in r["compositions"]:
            print(f"   {c['nom']} ({c['type_paroi']}, {c['nature']}) Up {c['Up_pleiades']} : "
                  + " + ".join(f"{x['materiau']} {x['epaisseur_cm']:g} cm" for x in c["couches"]))
    if sortie:
        Path(sortie).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
