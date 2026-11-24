"""Extraction d'un plan d'architecte (PDF vectoriel) vers un JSON normalisé et tracé.

Étapes :
1. textes (échelle, niveaux, étiquettes de baies, pièces, cotes) ;
2. murs = formes remplies d'épaisseur murale → vues en plan → enveloppe (polygone quelconque) → façades ;
3. par façade : couche pleine, bandes hachurées (isolant probable → ITE / ITI), ouvertures
   (trous dans le mur ou dans la bande isolant) ;
4. échelle : mention « Ech 1:N » vérifiée par les cotes écrites (lignes de cote, largeurs de baies) ;
5. nord (symbole) → azimut et orientation de chaque façade et baie ;
6. surfaces et linéaires de ponts thermiques par type de liaison.

Chaque valeur sortie est tracée (lu / déduit / supposé + confiance), cf. CLAUDE.md règle 1.
"""
from __future__ import annotations

import math
import statistics as st
from collections import Counter
from pathlib import Path

import pdfplumber
from shapely.geometry import Point

from ..trace import val
from . import nord as nord_mod
from .echelle import consensus, ratios_lignes_de_cote
from .murs import analyser_facades, couleur, couleur_hachures, formes_remplies, murs, vues_en_plan
from .textes import lire_echelles, lire_etiquettes_baies, lire_niveaux, lire_pieces, m_par_pt, phrases_de_page

DISTANCE_ETIQUETTE_M = 3.0  # distance max étiquette ↔ ouverture


def extraire_plan(chemin: str | Path, page: int = 0, hsp_m: float = 2.50, denominateur: int | None = None,
                  angle_nord_deg: float | None = None) -> dict:
    """Lit un plan PDF vectoriel et retourne le JSON normalisé (valeurs tracées lu / déduit / supposé).

    ``denominateur`` : force l'échelle (1:N) ; ``angle_nord_deg`` : force le nord (° depuis le haut de la
    feuille, positif vers la droite) ; ``hsp_m`` : hauteur sous plafond supposée.
    """
    chemin = Path(chemin)
    with pdfplumber.open(chemin) as pdf:
        return _Extraction(pdf.pages[page], hsp_m, denominateur, angle_nord_deg).run(chemin.name, page)


class _Extraction:
    def __init__(self, page, hsp_m, denominateur, angle_nord_deg):
        self.p = page
        self.hsp = hsp_m
        self.denominateur_force = denominateur
        self.angle_force = angle_nord_deg
        self.alertes: list[str] = []

    # ------------------------------------------------------------------ géométrie à échelle donnée
    def _geometrie(self, k):
        vues = vues_en_plan(murs(self.formes, k), k)
        for v in vues:
            coul = couleur_hachures(self.p.lines, v.enveloppe, k)
            hach = [o for o in self.p.lines if coul is not None and couleur(o) == coul
                    and max(o["x1"] - o["x0"], o["bottom"] - o["top"]) * k < 0.5] if coul else []
            analyser_facades(v, hach, k)
        return vues

    def _apparier(self, vues, k):
        """Étiquettes de baies ↔ ouvertures (glouton, plus proches d'abord)."""
        ouvertures = [(iv, jf, a, b) for iv, v in enumerate(vues) for jf, f in enumerate(v.facades) for (a, b) in f.ouvertures]
        paires = []
        for ie, e in enumerate(self.etiquettes):
            for io, (iv, jf, a, b) in enumerate(ouvertures):
                cx, cy = vues[iv].facades[jf].point((a + b) / 2)
                d = math.hypot(e.x - cx, e.y - cy) * k
                if d < DISTANCE_ETIQUETTE_M:
                    paires.append((d, ie, io))
        pris_e, pris_o, out = set(), set(), []
        for d, ie, io in sorted(paires):
            if ie in pris_e or io in pris_o:
                continue
            pris_e.add(ie)
            pris_o.add(io)
            out.append((ie, ouvertures[io]))
        libres = [o for io, o in enumerate(ouvertures) if io not in pris_o]
        return out, libres

    # ------------------------------------------------------------------ échelle
    def _echelle(self):
        mentions = lire_echelles(self.phrases)
        if self.denominateur_force:
            d = self.denominateur_force
            return m_par_pt(d), val(d, "lu", "fourni par l'utilisateur", "haute"), True
        k_mention, d = None, None
        if mentions:
            denoms = Counter(x for x, _ in mentions)
            d = denoms.most_common(1)[0][0]
            k_mention = m_par_pt(d)
            if len(denoms) > 1:
                self.alertes.append(f"Plusieurs échelles sur la feuille {dict(denoms)} : 1:{d} retenue.")
        k0 = k_mention or m_par_pt(100)
        vues0 = self._geometrie(k0)
        apparies, _ = self._apparier(vues0, k0)
        r_baies = []
        for ie, (iv, jf, a, b) in apparies:
            r_baies.append(self.etiquettes[ie].largeur_m / (b - a))
        r_cotes = ratios_lignes_de_cote(self.phrases, self.p.lines)
        cons = consensus(r_cotes + r_baies, tol=0.03, mini=2)
        src_cotes = f"{len(r_cotes)} ligne(s) de cote, {len(r_baies)} largeur(s) de baie"
        if cons:
            k_cal, n = cons
            d_cal = round(k_cal / m_par_pt(1))
            if k_mention and abs(k_cal - k_mention) / k_mention <= 0.03:
                return k_mention, val(d, "lu", f"mention « Ech 1:{d} », confirmée par {n} cote(s) écrite(s) ({src_cotes})", "haute"), True
            if k_mention:
                self.alertes.append(f"Échelle : la mention dit 1:{d} mais {n} cote(s) écrite(s) donnent 1:{d_cal} "
                                    "(PDF réduit à l'impression ?) → cotes retenues.")
            return k_cal, val(d_cal, "déduit", f"calibrée sur {n} cote(s) écrite(s) ({src_cotes})", "haute" if n >= 3 else "moyenne"), k_mention is None or abs(k_cal - k0) / k0 < 0.01
        if k_mention:
            self.alertes.append("Échelle non vérifiée par une cote écrite : contrôler une dimension connue.")
            return k_mention, val(d, "lu", f"mention « Ech 1:{d} » (aucune cote pour la vérifier)", "moyenne"), True
        raise ValueError("Échelle introuvable (ni mention ni cote écrite) : passer denominateur=100 ou la valeur du cartouche.")

    # ------------------------------------------------------------------ nord
    def _nord(self):
        if self.angle_force is not None:
            return val(round(self.angle_force, 1), "lu", "fourni par l'utilisateur", "haute", "°")
        fleches = nord_mod.detecter_fleches_nord(self.p.lines)
        if not fleches:
            self.alertes.append("Nord non détecté : saisir l'orientation à la main (--nord).")
            return val(None, "supposé", "symbole du nord non détecté", "faible", "°")
        angles = [nord_mod.angle_nord_depuis_haut(f["vecteur_nord"]) for f in fleches]
        a = st.median(angles)
        ecart = max(abs(((x - a + 180) % 360) - 180) for x in angles)
        conf = "haute" if len(angles) > 1 and ecart < 3 else "moyenne"
        if ecart >= 3:
            conf = "faible"
            self.alertes.append(f"Symboles du nord incohérents ({[round(x) for x in angles]}°) : vérifier.")
        return val(round(a, 1), "déduit", f"symbole du nord ({len(fleches)} trouvé(s))", conf, "°",
                   explication="angle du nord par rapport au haut de la feuille, positif vers la droite",
                   _symboles_pt=[f["centre"] for f in fleches])

    # ------------------------------------------------------------------ principal
    def run(self, nom_source, num_page):
        self.phrases = phrases_de_page(self.p)
        self.etiquettes = lire_etiquettes_baies(self.phrases)
        self.formes = formes_remplies(self.p)
        k, ech, _ = self._echelle()
        vues = self._geometrie(k)
        if not vues:
            raise ValueError("Aucun mur détecté : style de dessin non reconnu (murs non remplis ?). "
                             "Demander un PDF avec murs en aplat, ou un DXF.")
        apparies, libres = self._apparier(vues, k)
        nord = self._nord()
        angle = nord["valeur"]
        niveaux = self._niveaux(vues, k)
        pieces = lire_pieces(self.phrases)

        out_niv = []
        for iv in sorted(range(len(vues)), key=lambda i: _ordre(niveaux[i]["valeur"])):
            out_niv.append(self._niveau(vues[iv], iv, niveaux[iv], k, angle, nord, apparies, pieces))
        for (iv, jf, a, b) in libres:
            f = vues[iv].facades[jf]
            self.alertes.append(f"{niveaux[iv]['valeur']} façade F{jf + 1}{' (' + f.nom_cote + ')' if f.nom_cote else ''} : "
                                f"ouverture de {(b - a) * k:.2f} m sans étiquette (porte, baie non cotée ou artefact).")
        pris = {ie for ie, _ in apparies}
        for ie, e in enumerate(self.etiquettes):
            if ie not in pris:
                self.alertes.append(f"Étiquette {e.nom or '?'} ({e.largeur_m:.2f} x {e.hauteur_m:.2f}) sans ouverture "
                                    "trouvée dans un mur : baie non comptée, à placer à la main.")
        return {
            "source": nom_source,
            "page": num_page,
            "echelle": {"denominateur": ech, "m_par_pt": round(k, 6)},
            "nord": nord,
            "niveaux": out_niv,
            "batiment": self._batiment(out_niv),
            "alertes": self.alertes,
            "manquants": ["hauteurs d'étage et HSP (coupe)", "compositions murs / plancher bas / toiture (notice, CCTP)",
                          "menuiseries : Uw, Sw, TLw, occultations", "type de toiture (combles perdus / rampants / terrasse)",
                          "nature des refends et planchers (ponts thermiques)", "systèmes chauffage / ECS / ventilation"],
        }

    def _niveaux(self, vues, k):
        lus = lire_niveaux(self.phrases)
        paires = sorted((v.enveloppe.distance(Point(ph.cx, ph.cy)) * k, iv, il)
                        for iv, v in enumerate(vues) for il, (_, ph) in enumerate(lus))
        res, pv, pl = {}, set(), set()
        for d, iv, il in paires:
            if iv in pv or il in pl:
                continue
            nom, ph = lus[il]
            res[iv] = val(nom, "lu", f"titre de vue « {ph.texte} »", "haute" if d < 6 else "moyenne")
            pv.add(iv)
            pl.add(il)
        for iv in range(len(vues)):
            if iv not in res:
                res[iv] = val(f"NIVEAU_{iv}", "supposé", "aucun titre de vue trouvé", "faible")
                self.alertes.append(f"Vue {iv} sans titre de niveau : vérifier.")
        return res

    def _niveau(self, v, iv, niveau, k, angle, nord, apparies, pieces):
        x0, y0, x1, y1 = v.enveloppe.bounds
        ep, ext, intr = v.ep_struct_pt * k, v.ep_ext_pt * k, v.ep_int_pt * k
        if ext >= 0.05 and intr >= 0.05:
            iso = "ITE + doublage intérieur probables"
        elif ext >= 0.05:
            iso = "ITE probable"
        elif intr >= 0.05:
            iso = "ITI probable"
        else:
            iso = "aucune bande hachurée : isolation non lisible sur le plan"
        d_int = ep + intr
        n = len(v.facades)
        facades = []
        for jf, f in enumerate(v.facades):
            prev, nxt = v.facades[jf - 1], v.facades[(jf + 1) % n]
            l_int = f.longueur_pt * k - d_int * (_signe_coin(prev, f, v) + _signe_coin(f, nxt, v))
            fd = {"id": f"F{jf + 1}", "cote_feuille": f.nom_cote,
                  "longueur_ext_m": val(round(f.longueur_pt * k, 2), "déduit", "contour extérieur des murs", "haute", "m"),
                  "longueur_int_m": val(round(l_int, 2), "déduit", "contour - épaisseurs aux angles", "moyenne", "m"),
                  "couche_pleine_m": round(f.ep_pt * k, 3),
                  "bande_ext_m": round(f.ext_pt * k, 3), "bande_int_m": round(f.int_pt * k, 3)}
            if angle is not None:
                az = nord_mod.azimut(f.n, angle)
                lim = nord_mod.proche_limite(az)
                fd["azimut_deg"] = val(round(az, 1), "déduit", "normale extérieure + nord", nord["confiance"], "°")
                fd["orientation"] = val(nord_mod.secteur(az), "déduit", "secteur de 45°", "faible" if lim else nord["confiance"],
                                        **({"a_verifier": "azimut proche d'une limite de secteur"} if lim else {}))
            facades.append(fd)

        baies = []
        for ie, (jv, jf, a, b) in apparies:
            if jv != iv:
                continue
            e, f = self.etiquettes[ie], v.facades[jf]
            larg_plan = (b - a) * k
            d = {"nom": e.nom, "facade": f"F{jf + 1}", "cote_feuille": f.nom_cote,
                 "orientation": facades[jf].get("orientation", {}).get("valeur"),
                 "largeur_m": val(e.largeur_m, "lu", "étiquette (cm)", "haute", "m"),
                 "hauteur_m": val(e.hauteur_m, "lu", "étiquette (cm)", "haute", "m"),
                 "surface_m2": val(round(e.largeur_m * e.hauteur_m, 2), "déduit", "L x H de l'étiquette", "haute", "m²"),
                 "largeur_mesuree_plan_m": val(round(larg_plan, 2), "déduit", "ouverture dans le mur / l'isolant", "moyenne", "m")}
            if e.allege_m is not None:
                d["allege_m"] = val(e.allege_m, "lu", "étiquette « all. »", "haute", "m")
            if e.complement:
                d["mention"] = e.complement
            if abs(larg_plan - e.largeur_m) > 0.12:
                d["a_verifier"] = "largeur mesurée ≠ largeur écrite (tableau, coffre ou mauvais appariement)"
            d["_ouverture_pt"] = [round(c, 1) for c in (*f.point(a), *f.point(b))]
            d["_etiquette_pt"] = [round(e.x, 1), round(e.y, 1)]
            baies.append(d)
        baies.sort(key=lambda d: (int(d["facade"][1:]), d["nom"] or ""))

        s_int = v.interieur.area * k * k if v.interieur is not None else 0.0
        p_int = v.interieur.length * k if v.interieur is not None else 0.0
        pcs = [pc for pc in pieces if v.enveloppe.contains(Point(pc["x"], pc["y"]))]
        return {
            "niveau": niveau,
            "forme": val("rectangulaire" if n == 4 else f"polygonale ({n} façades)", "déduit", "contour des murs", "haute"),
            "emprise_m": {"largeur": val(round((x1 - x0) * k, 2), "déduit", "boîte englobante des murs", "haute", "m"),
                          "profondeur": val(round((y1 - y0) * k, 2), "déduit", "boîte englobante des murs", "haute", "m")},
            "surface_emprise_m2": val(round(v.enveloppe.area * k * k, 1), "déduit", "contour extérieur des murs", "haute", "m²"),
            "murs_exterieurs": {
                "couche_pleine_m": val(round(ep, 3), "déduit", "aplat du mur (médiane des façades)", "moyenne", "m",
                                       a_verifier="nature (béton, brique, ossature) : notice / coupe"),
                "bande_hachuree_ext_m": val(round(ext, 3), "déduit", "hachures côté extérieur", "moyenne", "m"),
                "bande_hachuree_int_m": val(round(intr, 3), "déduit", "hachures côté intérieur", "moyenne", "m"),
                "isolation": val(iso, "déduit", "position des bandes hachurées", "moyenne",
                                 a_verifier="épaisseur, nature et certification (ACERMI) de l'isolant à confirmer"),
            },
            "surface_interieure_m2": val(round(s_int, 1), "déduit", "contour intérieur (cloisons et trémie comprises)", "moyenne", "m²"),
            "perimetre_interieur_m": val(round(p_int, 2), "déduit", "contour intérieur des murs extérieurs", "moyenne", "m"),
            "angles": {"saillants": v.convexes, "rentrants": v.concaves},
            "refends_en_facade": val(v.refends, "déduit", "murs intérieurs >= 12 cm touchant la façade", "faible",
                                     a_verifier="porteur ou non : à confirmer"),
            "surface_pieces_etiquetees_m2": val(round(sum(pc["surface_m2"] for pc in pcs), 1), "lu",
                                                f"somme de {len(pcs)} étiquette(s) de pièces", "haute", "m²"),
            "pieces": [{"nom": pc["nom"], "surface_m2": pc["surface_m2"]} for pc in pcs],
            "facades": facades,
            "baies": baies,
            "_contour_pt": [[round(x, 1), round(y, 1)] for x, y in v.enveloppe.exterior.coords],
        }

    def _batiment(self, niv):
        hsp = self.hsp
        nb = len(niv)
        pinter = [n["perimetre_interieur_m"]["valeur"] for n in niv]
        toutes = [b for n in niv for b in n["baies"]]
        baies_o: dict[str, float] = {}
        for b in toutes:
            o = b["orientation"] or b["facade"]
            baies_o[o] = round(baies_o.get(o, 0) + b["surface_m2"]["valeur"], 2)
        murs_o: dict[str, float] = {}
        for n in niv:
            for f in n["facades"]:
                o = f.get("orientation", {}).get("valeur") or f["id"]
                murs_o[o] = murs_o.get(o, 0) + f["longueur_int_m"]["valeur"] * hsp
        murs_o = {o: {"brut_m2": round(s, 1), "net_m2": round(s - baies_o.get(o, 0), 1)} for o, s in murs_o.items()}
        larg = sum(b["largeur_m"]["valeur"] for b in toutes)
        haut = sum(b["hauteur_m"]["valeur"] for b in toutes)
        sal = sum(n["angles"]["saillants"] for n in niv)
        ren = sum(n["angles"]["rentrants"] for n in niv)
        nref = sum(n["refends_en_facade"]["valeur"] for n in niv)
        D, S = "déduit", "supposé"
        pt = {
            "plancher_bas_mur_ml": val(round(pinter[0], 1), D, "périmètre intérieur du niveau bas", "moyenne", "m",
                                       liaison="mur / plancher bas"),
            "plancher_intermediaire_mur_ml": val(round(sum(pinter[1:]), 1), D, "périmètres intérieurs des niveaux supérieurs", "moyenne", "m",
                                                 liaison="mur / plancher intermédiaire"),
            "plancher_haut_mur_ml": val(round(pinter[-1], 1), S, "périmètre du dernier niveau (toiture au-dessus supposée)", "faible", "m",
                                        liaison="mur / plancher haut ou toiture"),
            "refend_mur_ml": val(round(nref * hsp, 1), D, f"{nref} jonction(s) x HSP", "faible", "m", liaison="refend / mur"),
            "angle_saillant_ml": val(round(sal * hsp, 1), D, f"{sal} angle(s) x HSP", "moyenne", "m", liaison="angle de mur saillant"),
            "angle_rentrant_ml": val(round(ren * hsp, 1), D, f"{ren} angle(s) x HSP", "moyenne", "m", liaison="angle de mur rentrant"),
            "menuiserie_appui_ml": val(round(larg, 1), D, "Σ largeurs des baies", "haute", "m", liaison="menuiserie / mur : appui"),
            "menuiserie_linteau_ml": val(round(larg, 1), D, "Σ largeurs des baies", "haute", "m", liaison="menuiserie / mur : linteau"),
            "menuiserie_tableaux_ml": val(round(2 * haut, 1), D, "Σ 2 x hauteurs des baies", "haute", "m", liaison="menuiserie / mur : tableaux"),
        }
        s_int = sum(n["surface_interieure_m2"]["valeur"] for n in niv)
        return {
            "nombre_niveaux": val(nb, D, "vues en plan détectées", "haute"),
            "hauteur_sous_plafond_m": val(hsp, S, "valeur par défaut (non lisible sur un plan) → lire la coupe", "faible", "m"),
            "surface_interieure_totale_m2": val(round(s_int, 1), D, "Σ surfaces intérieures", "moyenne", "m²",
                                                note="proche de la Sref ; retirer trémie et parties < 1,80 m si besoin"),
            "surface_pieces_etiquetees_totale_m2": val(round(sum(n["surface_pieces_etiquetees_m2"]["valeur"] for n in niv), 1),
                                                       "lu", "Σ étiquettes de pièces", "haute", "m²"),
            "plancher_bas_m2": val(niv[0]["surface_interieure_m2"]["valeur"], D, "surface intérieure du niveau bas", "moyenne", "m²"),
            "plancher_haut_m2": val(niv[-1]["surface_interieure_m2"]["valeur"], S, "surface intérieure du dernier niveau", "faible", "m²"),
            "baies_par_orientation_m2": baies_o,
            "baies_total_m2": round(sum(baies_o.values()), 2),
            "murs_par_orientation_m2": murs_o,
            "ponts_thermiques": pt,
        }


def _signe_coin(f1, f2, v) -> int:
    """+1 si le coin entre f1 et f2 est saillant, -1 s'il est rentrant (pour corriger les longueurs)."""
    cross = f1.t[0] * f2.t[1] - f1.t[1] * f2.t[0]
    if abs(cross) < 1e-6:
        return 0
    return 1 if (cross > 0) == v.enveloppe.exterior.is_ccw else -1


def _ordre(n: str) -> int:
    if n == "R-1":
        return -1
    if n == "RDC":
        return 0
    if n.startswith("R+") and n[2:].isdigit():
        return int(n[2:])
    return 99 if n == "COMBLES" else 50
