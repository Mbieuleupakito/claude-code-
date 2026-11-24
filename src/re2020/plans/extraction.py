"""Extraction d'un plan d'architecte (PDF vectoriel) vers un JSON normalisé et tracé.

Ce que l'on lit / déduit :
- échelle (mention « Ech : 1 : 100 ») → mètres par point ;
- niveaux (blocs de murs pleins) et leur nom (« R+0 », « R+1 », « RDC »...) ;
- murs extérieurs : emprise, épaisseur de la couche pleine, bandes hachurées extérieure / intérieure
  (isolant probable → ITE / ITI) ;
- baies : étiquettes « Nom / L x H ht. / all.X » + interruptions de la bande hachurée → façade ;
- symbole du nord → azimut et orientation (8 secteurs) de chaque façade ;
- pièces étiquetées (m²), surfaces intérieures, linéaires de ponts thermiques.

Hypothèses de dessin (à confirmer sur d'autres agences) : murs en aplats rectangulaires pleins,
isolant en hachures diagonales, plan orthogonal (façades parallèles aux bords de la feuille).
"""
from __future__ import annotations

import math
import statistics as st
from collections import Counter
from pathlib import Path

import pdfplumber

from ..trace import val
from . import nord as nord_mod
from .textes import (lire_echelles, lire_etiquettes_baies, lire_niveaux, lire_pieces, m_par_pt,
                     phrases_de_page)

COTES = ("haut", "droite", "bas", "gauche")
NORMALES = {"haut": (0, -1), "droite": (1, 0), "bas": (0, 1), "gauche": (-1, 0)}


# --------------------------------------------------------------------------- outils géométriques

def _couleur(o):
    c = o.get("non_stroking_color") if o.get("fill") else o.get("stroking_color")
    if isinstance(c, (list, tuple)):
        return tuple(round(float(v), 2) for v in c)
    return (c,)


def _blanc(c) -> bool:
    return all(v == 1 for v in c if isinstance(v, (int, float))) and len(c) in (1, 3) and c != (None,)


def _fusion(intervalles, tol=0.5):
    out = []
    for a, b in sorted(intervalles):
        if out and a <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _quantile(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, int(q * (len(vals) - 1))))]


def _grouper(rects, tol=2.0):
    """Regroupe des rectangles qui se touchent (union-find)."""
    parent = list(range(len(rects)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(rects):
        for j in range(i + 1, len(rects)):
            b = rects[j]
            if a["x0"] - tol <= b["x1"] and b["x0"] - tol <= a["x1"] and a["top"] - tol <= b["bottom"] and b["top"] - tol <= a["bottom"]:
                parent[find(i)] = find(j)
    groupes = {}
    for i, r in enumerate(rects):
        groupes.setdefault(find(i), []).append(r)
    return list(groupes.values())


# --------------------------------------------------------------------------- murs et bandes

def _murs_pleins(page, k):
    out = []
    for r in page.rects:
        if not r.get("fill") or _blanc(_couleur(r)):
            continue
        ep, lg = min(r["width"], r["height"]) * k, max(r["width"], r["height"]) * k
        if 0.04 <= ep <= 0.6 and lg >= 0.4:
            out.append(r)
    return out


def _local(h, cote, B):
    """(début, fin) le long de la façade et (d0, d1) en profondeur (positive vers l'extérieur), en pt."""
    x0, y0, x1, y1 = B
    if cote == "haut":
        return (h["x0"], h["x1"]), (y0 - h["bottom"], y0 - h["top"])
    if cote == "bas":
        return (h["x0"], h["x1"]), (h["top"] - y1, h["bottom"] - y1)
    if cote == "gauche":
        return (h["top"], h["bottom"]), (x0 - h["x1"], x0 - h["x0"])
    return (h["top"], h["bottom"]), (h["x0"] - x1, h["x1"] - x1)


def _etendue(cote, B):
    x0, y0, x1, y1 = B
    return (x0, x1) if cote in ("haut", "bas") else (y0, y1)


def _bande(hachures, cote, B, ep_struct, k, interieure=False):
    """Épaisseur (pt) de la bande hachurée collée à la face extérieure (ou intérieure) du mur."""
    lo, hi = _etendue(cote, B)
    marge = 0.5 / k  # on ignore 0,5 m près des angles
    prof = (0.3 if interieure else 0.6) / k
    d0s, d1s = [], []
    for h in hachures:
        (a0, a1), (d0, d1) = _local(h, cote, B)
        if a0 < lo + marge or a1 > hi - marge:
            continue
        if interieure and d1 <= -ep_struct + 0.5 and d0 >= -ep_struct - prof:
            d0s.append(d0)
        elif not interieure and d0 >= -0.5 and d1 <= prof:
            d1s.append(d1)
    if interieure:
        return max(0.0, -ep_struct - _quantile(d0s, 0.05)) if d0s else 0.0
    return max(0.0, _quantile(d1s, 0.95)) if d1s else 0.0


def _ouvertures(hachures, cote, B, bande_pt, k, ep_min_m=0.25):
    """Interruptions de la bande hachurée extérieure le long d'une façade → [(début, fin)] en pt."""
    if bande_pt <= 0:
        return []
    lo, hi = _etendue(cote, B)
    sel = []
    for h in hachures:
        (a0, a1), (d0, d1) = _local(h, cote, B)
        if d0 >= -0.5 and d1 <= bande_pt + 0.5:
            sel.append((a0, a1))
    iv = _fusion(sel)
    return [(a[1], b[0]) for a, b in zip(iv, iv[1:]) if (b[0] - a[1]) * k >= ep_min_m and lo < a[1] and b[0] < hi]


def _couleur_hachures(lignes, B, k):
    x0, y0, x1, y1 = B
    d = 1.0 / k
    c = Counter()
    for o in lignes:
        dx, dy = o["x1"] - o["x0"], o["bottom"] - o["top"]
        if dx > 0.3 and dy > 0.3 and 0.4 < dx / dy < 2.5 and dx * k < 0.5:
            if x0 - d <= o["x0"] and o["x1"] <= x1 + d and y0 - d <= o["top"] and o["bottom"] <= y1 + d:
                c[_couleur(o)] += 1
    return c.most_common(1)[0][0] if c else None


# --------------------------------------------------------------------------- extraction principale

def extraire_plan(chemin: str | Path, page: int = 0, hsp_m: float = 2.50,
                  denominateur: int | None = None, angle_nord_deg: float | None = None) -> dict:
    """Lit un plan PDF vectoriel et retourne le JSON normalisé (valeurs tracées lu/déduit/supposé)."""
    chemin = Path(chemin)
    with pdfplumber.open(chemin) as pdf:
        p = pdf.pages[page]
        return _extraire_page(p, chemin.name, page, hsp_m, denominateur, angle_nord_deg)


def _extraire_page(p, nom_source, num_page, hsp_m, denominateur, angle_nord_deg):
    alertes: list[str] = []
    phrases = phrases_de_page(p)

    # ---- échelle
    mentions = lire_echelles(phrases)
    if denominateur:
        ech = val(denominateur, "lu", "fourni par l'utilisateur", "haute")
    elif mentions:
        denoms = Counter(d for d, _ in mentions)
        d, n = denoms.most_common(1)[0]
        conf = "haute" if len(denoms) == 1 else "moyenne"
        ech = val(d, "lu", f"mention « Ech 1:{d} » ({n} occurrence(s))", conf)
        if len(denoms) > 1:
            alertes.append(f"Plusieurs échelles sur la feuille : {dict(denoms)} → 1:{d} retenue pour tout le plan.")
        denominateur = d
    else:
        raise ValueError("Échelle introuvable sur le plan : passer denominateur=100 (ou la valeur lue sur le cartouche).")
    k = m_par_pt(denominateur)

    # ---- murs pleins → blocs (un bloc = une vue en plan d'un niveau)
    murs = _murs_pleins(p, k)
    blocs = []
    for g in _grouper(murs):
        bx0, by0 = min(r["x0"] for r in g), min(r["top"] for r in g)
        bx1, by1 = max(r["x1"] for r in g), max(r["bottom"] for r in g)
        if (bx1 - bx0) * k >= 3 and (by1 - by0) * k >= 3 and len(g) >= 4:
            blocs.append({"rects": g, "bbox": (bx0, by0, bx1, by1)})
    if not blocs:
        raise ValueError("Aucun mur plein détecté : style de dessin non reconnu (murs non remplis ?). "
                         "Demander un PDF avec murs en aplat ou un DXF.")

    # ---- noms des niveaux (association gloutonne étiquette ↔ bloc la plus proche)
    niveaux_lus = lire_niveaux(phrases)
    paires = []
    for ib, b in enumerate(blocs):
        x0, y0, x1, y1 = b["bbox"]
        for il, (nom, ph) in enumerate(niveaux_lus):
            dx = max(x0 - ph.cx, 0, ph.cx - x1)
            dy = max(y0 - ph.cy, 0, ph.cy - y1)
            paires.append((math.hypot(dx, dy), ib, il))
    pris_b, pris_l = set(), set()
    for dist, ib, il in sorted(paires):
        if ib in pris_b or il in pris_l:
            continue
        nom, ph = niveaux_lus[il]
        blocs[ib]["niveau"] = val(nom, "lu", f"titre de vue « {ph.texte} »", "haute" if dist < 150 else "moyenne")
        pris_b.add(ib)
        pris_l.add(il)
    for i, b in enumerate(blocs):
        if "niveau" not in b:
            b["niveau"] = val(f"NIVEAU_{i}", "supposé", "aucun titre de vue trouvé", "faible")
            alertes.append(f"Bloc {i} sans titre de niveau : vérifier.")

    # ---- nord
    if angle_nord_deg is not None:
        nord = val(round(angle_nord_deg, 1), "lu", "fourni par l'utilisateur", "haute", "°")
    else:
        fleches = nord_mod.detecter_fleches_nord(p.lines)
        if fleches:
            angles = [nord_mod.angle_nord_depuis_haut(f["vecteur_nord"]) for f in fleches]
            angle_nord_deg = st.median(angles)
            ecart = max(abs(((a - angle_nord_deg + 180) % 360) - 180) for a in angles)
            conf = "haute" if (len(angles) > 1 and ecart < 3) else "moyenne"
            if ecart >= 3:
                alertes.append(f"Symboles du nord incohérents ({[round(a) for a in angles]}°) : vérifier.")
                conf = "faible"
            nord = val(round(angle_nord_deg, 1), "déduit", f"symbole du nord ({len(fleches)} trouvé(s))", conf, "°",
                       explication="angle du nord par rapport au haut de la feuille, positif vers la droite (négatif = vers la gauche)",
                       _symboles_pt=[f["centre"] for f in fleches])
        else:
            nord = val(None, "supposé", "symbole du nord non détecté", "faible", "°")
            alertes.append("Nord non détecté : saisir l'orientation à la main (angle_nord_deg).")

    # ---- textes
    etiquettes = lire_etiquettes_baies(phrases)
    pieces = lire_pieces(phrases)

    # ---- analyse de chaque bloc
    gaps_tous = []  # (bloc, cote, a, b)
    for ib, b in enumerate(blocs):
        ext = [r for r in b["rects"] if min(r["width"], r["height"]) * k >= 0.12]
        if not ext:
            ext = b["rects"]
        B = (min(r["x0"] for r in ext), min(r["top"] for r in ext), max(r["x1"] for r in ext), max(r["bottom"] for r in ext))
        b["B"] = B
        lignes = p.lines
        coul = _couleur_hachures(lignes, B, k)
        hach = [o for o in lignes if _couleur(o) == coul and (o["x1"] - o["x0"]) * k < 0.5 and (o["bottom"] - o["top"]) * k < 0.5] if coul else []
        cotes = {}
        for c in COTES:
            if c in ("haut", "bas"):
                edge = B[1] if c == "haut" else B[3]
                sur = [r for r in ext if abs((r["top"] if c == "haut" else r["bottom"]) - edge) < 1 and r["width"] > r["height"]]
                long_pt = B[2] - B[0]
                cov = sum(iv[1] - iv[0] for iv in _fusion([(r["x0"], r["x1"]) for r in sur]))
            else:
                edge = B[0] if c == "gauche" else B[2]
                sur = [r for r in ext if abs((r["x0"] if c == "gauche" else r["x1"]) - edge) < 1 and r["height"] > r["width"]]
                long_pt = B[3] - B[1]
                cov = sum(iv[1] - iv[0] for iv in _fusion([(r["top"], r["bottom"]) for r in sur]))
            ep = st.median([min(r["width"], r["height"]) for r in sur]) if sur else 0.0
            ext_pt = _bande(hach, c, B, ep, k) if hach else 0.0
            int_pt = _bande(hach, c, B, ep, k, interieure=True) if hach else 0.0
            gaps = _ouvertures(hach, c, B, ext_pt, k)
            for a, bb in gaps:
                gaps_tous.append((ib, c, a, bb))
            cotes[c] = {"long_pt": long_pt, "couverture": cov / long_pt if long_pt else 0, "ep_pt": ep,
                        "ext_pt": ext_pt, "int_pt": int_pt}
            if long_pt and cov / long_pt < 0.9:
                alertes.append(f"{b['niveau']['valeur']} façade {c} : mur plein sur {cov / long_pt:.0%} de la longueur seulement "
                               "(plan non rectangulaire ou retrait) → contrôler l'emprise.")
        b["cotes"] = cotes

    # ---- appariement étiquettes ↔ ouvertures
    def centre_gap(g):
        ib, c, a, bb = g
        B = blocs[ib]["B"]
        m = (a + bb) / 2
        return {"haut": (m, B[1]), "bas": (m, B[3]), "gauche": (B[0], m), "droite": (B[2], m)}[c]

    paires = []
    for ie, e in enumerate(etiquettes):
        for ig, g in enumerate(gaps_tous):
            gx, gy = centre_gap(g)
            d = math.hypot(e.x - gx, e.y - gy)
            if d < 80:
                paires.append((d, ie, ig))
    pris_e, pris_g, baies = set(), set(), []
    for d, ie, ig in sorted(paires):
        if ie in pris_e or ig in pris_g:
            continue
        pris_e.add(ie)
        pris_g.add(ig)
        e, (ib, c, a, bb) = etiquettes[ie], gaps_tous[ig]
        larg_plan = (bb - a) * k
        ecart = larg_plan - e.largeur_m
        baies.append((ib, c, e, larg_plan, abs(ecart) <= 0.12, (a, bb)))
    for ie, e in enumerate(etiquettes):
        if ie in pris_e:
            continue
        # étiquette sans ouverture détectée : façade la plus proche du bloc le plus proche
        best = None
        for ib, b in enumerate(blocs):
            B = b["B"]
            for c in COTES:
                d = {"haut": abs(e.y - B[1]), "bas": abs(e.y - B[3]), "gauche": abs(e.x - B[0]), "droite": abs(e.x - B[2])}[c]
                inside = (B[0] - 60 <= e.x <= B[2] + 60) and (B[1] - 60 <= e.y <= B[3] + 60)
                if inside and (best is None or d < best[0]):
                    best = (d, ib, c)
        if best:
            baies.append((best[1], best[2], e, None, False, None))
            alertes.append(f"Baie {e.nom or '?'} ({e.largeur_m:.2f} x {e.hauteur_m:.2f}) : ouverture non trouvée dans le mur, "
                           f"façade {best[2]} supposée.")
        else:
            alertes.append(f"Étiquette {e.nom or '?'} hors des plans : ignorée.")
    for ig, (ib, c, a, bb) in enumerate(gaps_tous):
        if ig not in pris_g:
            alertes.append(f"{blocs[ib]['niveau']['valeur']} façade {c} : ouverture de {(bb - a) * k:.2f} m sans étiquette "
                           "(porte, baie non cotée ou artefact) → à vérifier.")

    # ---- assemblage par niveau
    ordre = lambda b: (lambda n: -1 if n == "R-1" else (0 if n == "RDC" else (99 if n == "COMBLES" else int(n[2:]) if n.startswith("R+") and n[2:].isdigit() else 50)))(b["niveau"]["valeur"])
    idx_tri = sorted(range(len(blocs)), key=lambda i: ordre(blocs[i]))
    niveaux_out = []
    for ib in idx_tri:
        b = blocs[ib]
        B, cotes = b["B"], b["cotes"]
        larg, prof = (B[2] - B[0]) * k, (B[3] - B[1]) * k
        ep_struct = st.median([cotes[c]["ep_pt"] for c in COTES]) * k
        ep_ext = st.median([cotes[c]["ext_pt"] for c in COTES]) * k
        ep_int = st.median([cotes[c]["int_pt"] for c in COTES]) * k
        li = larg - 2 * (ep_struct + ep_int)
        pi = prof - 2 * (ep_struct + ep_int)
        if ep_ext >= 0.05 and ep_int >= 0.05:
            iso = "ITE + doublage intérieur probables"
        elif ep_ext >= 0.05:
            iso = "ITE probable"
        elif ep_int >= 0.05:
            iso = "ITI probable"
        else:
            iso = "aucune bande hachurée : isolation non lisible"

        facades = {}
        for c in COTES:
            long_int = (li if c in ("haut", "bas") else pi)
            f = {"longueur_interieure_m": val(round(long_int, 2), "déduit", "emprise des murs pleins - épaisseurs", "moyenne", "m")}
            if angle_nord_deg is not None:
                az = nord_mod.azimut(NORMALES[c], angle_nord_deg)
                f["azimut_deg"] = val(round(az, 1), "déduit", "normale extérieure + nord", nord["confiance"], "°")
                f["orientation"] = val(nord_mod.secteur(az), "déduit", "secteur de 45°", "faible" if nord_mod.proche_limite(az) else nord["confiance"],
                                       **({"a_verifier": "azimut proche d'une limite de secteur"} if nord_mod.proche_limite(az) else {}))
            facades[c] = f

        baies_niv = []
        for (jb, c, e, larg_plan, coherent, seg) in baies:
            if jb != ib:
                continue
            d = {"nom": e.nom, "facade": c,
                 "orientation": facades[c].get("orientation", {}).get("valeur"),
                 "largeur_m": val(e.largeur_m, "lu", "étiquette (cm)", "haute", "m"),
                 "hauteur_m": val(e.hauteur_m, "lu", "étiquette (cm)", "haute", "m"),
                 "surface_m2": val(round(e.largeur_m * e.hauteur_m, 2), "déduit", "L x H de l'étiquette", "haute", "m²")}
            if e.allege_m is not None:
                d["allege_m"] = val(e.allege_m, "lu", "étiquette « all. »", "haute", "m")
            if e.complement:
                d["mention"] = e.complement
            if larg_plan is not None:
                d["largeur_mesuree_plan_m"] = val(round(larg_plan, 2), "déduit", "interruption de la bande isolant", "moyenne", "m")
                if not coherent:
                    d["a_verifier"] = "largeur mesurée ≠ largeur de l'étiquette (tableau, coffre ou erreur d'appariement)"
            else:
                d["a_verifier"] = "façade supposée (ouverture non détectée dans le mur)"
            d["_ouverture_pt"] = [round(v, 1) for v in seg] if seg else None
            d["_etiquette_pt"] = [round(e.x, 1), round(e.y, 1)]
            baies_niv.append(d)
        baies_niv.sort(key=lambda d: (COTES.index(d["facade"]), d["nom"] or ""))

        pieces_niv = [pc for pc in pieces if B[0] <= pc["x"] <= B[2] and B[1] <= pc["y"] <= B[3]]
        s_pieces = sum(pc["surface_m2"] for pc in pieces_niv)
        niveaux_out.append({
            "niveau": b["niveau"],
            "emprise_m": {"largeur": val(round(larg, 2), "déduit", "murs pleins (face ext. de la couche pleine)", "haute", "m"),
                          "profondeur": val(round(prof, 2), "déduit", "murs pleins (face ext. de la couche pleine)", "haute", "m")},
            "murs_exterieurs": {
                "couche_pleine_m": val(round(ep_struct, 3), "déduit", "aplat du mur", "moyenne", "m",
                                       a_verifier="structure probable : nature (béton, brique, ossature) à lire sur la notice/coupe"),
                "bande_hachuree_ext_m": val(round(ep_ext, 3), "déduit", "hachures côté extérieur", "moyenne", "m"),
                "bande_hachuree_int_m": val(round(ep_int, 3), "déduit", "hachures côté intérieur", "moyenne", "m"),
                "isolation": val(iso, "déduit", "position des bandes hachurées", "moyenne",
                                 a_verifier="épaisseur et nature de l'isolant à confirmer (coupe, notice, CCTP)"),
            },
            "dimensions_interieures_m": {"largeur": val(round(li, 2), "déduit", "emprise - murs - bande intérieure", "moyenne", "m"),
                                         "profondeur": val(round(pi, 2), "déduit", "emprise - murs - bande intérieure", "moyenne", "m")},
            "surface_interieure_m2": val(round(li * pi, 1), "déduit", "dimensions intérieures (cloisons et trémie comprises)", "moyenne", "m²"),
            "surface_pieces_etiquetees_m2": val(round(s_pieces, 1), "lu", f"somme de {len(pieces_niv)} étiquettes de pièces", "haute", "m²"),
            "pieces": [{"nom": pc["nom"], "surface_m2": pc["surface_m2"]} for pc in pieces_niv],
            "facades": facades,
            "baies": baies_niv,
            "_bbox_pt": [round(v, 1) for v in B],
        })

    # ---- synthèse bâtiment
    hsp = val(hsp_m, "supposé", "valeur par défaut (non lisible sur un plan) → lire la coupe", "faible", "m")
    perimetres = [2 * (n["dimensions_interieures_m"]["largeur"]["valeur"] + n["dimensions_interieures_m"]["profondeur"]["valeur"]) for n in niveaux_out]
    toutes_baies = [d for n in niveaux_out for d in n["baies"]]
    par_orient: dict[str, float] = {}
    for d in toutes_baies:
        o = d["orientation"] or d["facade"]
        par_orient[o] = round(par_orient.get(o, 0) + d["surface_m2"]["valeur"], 2)
    murs_orient = {}
    for n in niveaux_out:
        for c, f in n["facades"].items():
            o = f.get("orientation", {}).get("valeur") or c
            brut = f["longueur_interieure_m"]["valeur"] * hsp_m
            murs_orient[o] = murs_orient.get(o, 0) + brut
    murs_orient = {o: {"brut_m2": round(v, 1), "net_m2": round(v - par_orient.get(o, 0), 1)} for o, v in murs_orient.items()}
    s_int = sum(n["surface_interieure_m2"]["valeur"] for n in niveaux_out)
    s_pcs = sum(n["surface_pieces_etiquetees_m2"]["valeur"] for n in niveaux_out)
    nb = len(niveaux_out)

    pt = {
        "plancher_bas_mur_ml": val(round(perimetres[0], 1), "déduit", "périmètre intérieur du niveau le plus bas", "moyenne", "m"),
        "plancher_intermediaire_mur_ml": val(round(sum(perimetres[1:]), 1), "déduit", "périmètres intérieurs des niveaux supérieurs", "moyenne", "m"),
        "toiture_mur_ml": val(round(perimetres[-1], 1), "supposé", "périmètre du dernier niveau (toiture au-dessus supposée)", "faible", "m"),
        "angles_sortants_ml": val(round(4 * hsp_m * nb, 1), "déduit", "4 angles x HSP x niveaux (plan rectangulaire)", "moyenne", "m"),
        "menuiseries_appuis_ml": val(round(sum(d["largeur_m"]["valeur"] for d in toutes_baies), 1), "déduit", "Σ largeurs des baies", "haute", "m"),
        "menuiseries_linteaux_ml": val(round(sum(d["largeur_m"]["valeur"] for d in toutes_baies), 1), "déduit", "Σ largeurs des baies", "haute", "m"),
        "menuiseries_tableaux_ml": val(round(sum(2 * d["hauteur_m"]["valeur"] for d in toutes_baies), 1), "déduit", "Σ 2 x hauteurs des baies", "haute", "m"),
    }

    batiment = {
        "nombre_niveaux": val(nb, "déduit", "blocs de murs détectés", "haute"),
        "hauteur_sous_plafond_m": hsp,
        "surface_interieure_totale_m2": val(round(s_int, 1), "déduit", "Σ surfaces intérieures des niveaux", "moyenne", "m²",
                                            note="proche de la Sref/SHAB ; retirer trémie d'escalier et parties < 1,80 m si besoin"),
        "surface_pieces_etiquetees_totale_m2": val(round(s_pcs, 1), "lu", "Σ étiquettes de pièces", "haute", "m²",
                                                   note="hors circulations ou pièces non étiquetées"),
        "baies_par_orientation_m2": par_orient,
        "baies_total_m2": round(sum(par_orient.values()), 2),
        "murs_par_orientation_m2": murs_orient,
        "ponts_thermiques": pt,
    }
    manquants = ["hauteurs d'étage et HSP (coupe)", "compositions exactes murs / plancher bas / toiture (notice, CCTP)",
                 "menuiseries : Uw, Sw, TLw, occultations", "type de toiture (combles perdus / rampants / terrasse)",
                 "refends et planchers intermédiaires : nature (ponts thermiques)", "systèmes chauffage / ECS / ventilation"]
    return {
        "source": nom_source,
        "page": num_page,
        "echelle": {"denominateur": ech, "m_par_pt": round(k, 6)},
        "nord": nord,
        "niveaux": niveaux_out,
        "batiment": batiment,
        "alertes": alertes,
        "manquants": manquants,
    }
