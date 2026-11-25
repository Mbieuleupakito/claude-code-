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
import re
import statistics as st
from collections import Counter
from pathlib import Path

import pdfplumber
from shapely.geometry import Point

from .. import ocr
from ..trace import val
from . import nord as nord_mod
from .echelle import consensus, ratios_lignes_de_cote
from .murs import (analyser_facades, couleur, couleur_hachures, couleur_murs, formes_remplies, marqueurs_ouvertures, murs,
                   vues_en_plan)
from .textes import (EtiquetteBaie, correspond, lire_dimensions_types, lire_echelles, lire_etiquettes_baies, lire_hauteurs,
                     lire_legende, lire_niveaux, lire_nord_texte, lire_pieces, m_par_pt, phrases_de_page, valeurs_metriques)

RE_VIDE = re.compile(r"\bvide\s+sur\b|\bdouble\s+hauteur\b", re.I)

MANQUANTS = ["hauteurs d'étage et HSP (coupe)", "compositions murs / plancher bas / toiture (notice, CCTP)",
             "menuiseries : Uw, Sw, TLw, occultations", "type de toiture (combles perdus / rampants / terrasse)",
             "nature des refends et planchers (ponts thermiques)", "systèmes chauffage / ECS / ventilation"]

DISTANCE_ETIQUETTE_M = 3.0  # distance max étiquette ↔ ouverture


def extraire_plan(chemin, page: int | None = None, hsp_m: float | None = None, denominateur: int | None = None,
                  angle_nord_deg: float | None = None) -> dict:
    """Lit un ou plusieurs PDF vectoriels et retourne le JSON normalisé (valeurs tracées lu / déduit / supposé).

    ``chemin`` : un PDF ou une liste de PDF (plans, coupe, notice…). Sans ``page``, toutes les pages sont
    parcourues et les vues en plan titrées (« RDC », « R+1 »…) sont gardées. ``denominateur`` force
    l'échelle (1:N) ; ``angle_nord_deg`` force le nord ; ``hsp_m`` force la hauteur sous plafond.
    """
    chemins = [Path(c) for c in (chemin if isinstance(chemin, (list, tuple)) else [chemin])]
    resultats, textes, echecs = [], [], []
    for ic, ch in enumerate(chemins):
        with pdfplumber.open(ch) as pdf:
            pages = [page] if page is not None else range(len(pdf.pages))
            for i in pages:
                p = pdf.pages[i]
                textes.append(p.extract_text() or "")
                try:
                    r = _Extraction(p, denominateur, angle_nord_deg).run(ch.name, i)
                except ValueError as exc:
                    if page is not None and len(chemins) == 1:
                        raise
                    echecs.append(str(exc))
                    continue
                r["_fichier"] = ic
                resultats.append(r)
    resultats = _echelle_par_fichier(resultats, chemins, angle_nord_deg) if denominateur is None else resultats
    if not resultats:
        raise ValueError(echecs[0] if len(echecs) == 1 else
                         "Aucun plan de niveau reconnu dans le dossier (murs non remplis ?). Demander un PDF avec murs "
                         "en aplat, ou un DXF.")
    titres = [r for r in resultats if any(n["niveau"]["tag"] == "lu" for n in r["niveaux"])]
    return _fusionner(titres or resultats, "\n".join(textes), hsp_m, [c.name for c in chemins])


def _echelle_par_fichier(resultats: list[dict], chemins: list[Path], angle_nord_deg) -> list[dict]:
    """Les pages d'un même fichier calées sur les surfaces de pièces partagent la même échelle de dessin. Une pièce
    non étiquetée (vide sur séjour, trémie, placard) ne fait que SOUS-estimer l'échelle : on retient la plus grande
    et on relit les autres pages à cette échelle."""
    out = []
    for ic, ch in enumerate(chemins):
        rs = [r for r in resultats if r["_fichier"] == ic]
        cal = [r for r in rs if "pièces" in r["echelle"]["denominateur"]["source"]]
        if len(cal) < 2:
            out += rs
            continue
        d = max(r["echelle"]["denominateur"]["valeur"] for r in cal)
        src = (f"calée sur les surfaces de pièces écrites, commune aux {len(cal)} plans du fichier "
               "(la page la plus cohérente fixe l'échelle)")
        with pdfplumber.open(ch) as pdf:
            for r in rs:
                if r in cal and abs(r["echelle"]["denominateur"]["valeur"] - d) / d > 0.02:
                    try:
                        r2 = _Extraction(pdf.pages[r["page"]], None, angle_nord_deg, (d, src)).run(ch.name, r["page"])
                        r2["_fichier"] = ic
                        r = r2
                    except ValueError:
                        pass
                out.append(r)
    return out


def _fusionner(resultats: list[dict], texte: str, hsp_force: float | None, noms: list[str]) -> dict:
    """Assemble les niveaux trouvés sur plusieurs pages (un niveau = la meilleure vue portant ce titre)."""
    par_niveau: dict[str, dict] = {}
    for r in resultats:
        for n in r["niveaux"]:
            if len(resultats) > 1 and n["niveau"]["tag"] != "lu":
                continue
            n["_page"] = r["page"]
            n["_fichier"] = r["_fichier"]
            nom = n["niveau"]["valeur"]
            score = (len(n["baies"]), n["surface_interieure_m2"]["valeur"])
            if nom not in par_niveau or score > par_niveau[nom][0]:
                par_niveau[nom] = (score, n)
    niveaux = [n for _, n in sorted(par_niveau.values(), key=lambda x: _ordre(x[1]["niveau"]["valeur"]))]
    if not niveaux:
        niveaux = [n for r in resultats for n in r["niveaux"]]
    pages_utiles = {(n["_fichier"], n["_page"]) for n in niveaux}
    gardes = [r for r in resultats if (r["_fichier"], r["page"]) in pages_utiles] or resultats
    ref = gardes[0]
    nord = next((r["nord"] for r in gardes if r["nord"]["valeur"] is not None), ref["nord"])
    h = lire_hauteurs(texte)
    if hsp_force is not None:
        hsp = val(hsp_force, "lu", "fourni par l'utilisateur", "haute", "m")
    elif "hsp_m" in h:
        hsp = val(h["hsp_m"], "lu", "« hauteur sous plafond » écrite dans le dossier (coupe)", "haute", "m")
    else:
        hsp = val(2.50, "supposé", "valeur par défaut (non lisible sur un plan) → lire la coupe", "faible", "m")
    h_etage = val(h["hauteur_etage_m"], "lu", "« hauteur d'étage » écrite dans le dossier", "haute", "m") if "hauteur_etage_m" in h else None
    alertes = []
    for r in gardes:
        pref = f"p.{r['page'] + 1} : " if len(gardes) > 1 or r["page"] else ""
        alertes += [pref + a for a in r["alertes"] if pref + a not in alertes]
    return {
        "source": " + ".join(noms),
        "page": ref["page"],
        "pages_plans": sorted({f"{noms[r['_fichier']]} p.{r['page'] + 1}" for r in gardes}),
        "echelle": ref["echelle"],
        "echelles_par_page": {f"p.{r['page'] + 1}": r["echelle"]["denominateur"]["valeur"] for r in gardes},
        "nord": nord,
        "niveaux": niveaux,
        "batiment": batiment(niveaux, hsp, h_etage),
        "alertes": alertes,
        "manquants": MANQUANTS,
    }


class _Extraction:
    def __init__(self, page, denominateur, angle_nord_deg, echelle_commune=None):
        self.p = page
        self.denominateur_force = denominateur
        self.echelle_commune = echelle_commune  # (D, source) : échelle déduite des autres pages du même fichier
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
            v.couleur = couleur_murs(v, self.formes)
            marqueurs_ouvertures(v, self.formes, k, v.couleur)
        # une vue dont l'intérieur fait moins de 9 m² n'est pas un niveau de bâtiment (cartouche, détail, hachures…)
        return [v for v in vues if v.interieur is not None and v.interieur.area * k * k >= 9]

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
    def _calage_pieces(self):
        """Échelle déduite des surfaces de pièces écrites (« SÉJOUR 80 m² ») : on cherche une échelle où les murs
        sont reconnus, puis on ajuste pour que la surface intérieure mesurée ≈ somme des pièces / 0,95
        (cloisons et trémies). Retourne (m/pt, nb de pièces) ou None."""
        pieces = lire_pieces(self.phrases)
        if len(pieces) < 2:
            return None
        estimations = []
        for D in (20, 25, 33, 50, 75, 100, 125, 150, 200, 250, 500):
            k = m_par_pt(D)
            for v in self._geometrie(k):
                dedans = [pc for pc in pieces if v.enveloppe.contains(Point(pc["x"], pc["y"]))]
                if len(dedans) < 2 or v.interieur is None:
                    continue
                s_pieces = sum(pc["surface_m2"] for pc in dedans)
                k_est = math.sqrt(s_pieces / 0.95 / v.interieur.area)
                if abs(k_est - k) / k < 0.45:  # les murs sont reconnus à une échelle proche de celle estimée
                    estimations.append((len(dedans), k_est))
            if estimations:
                break
        if not estimations:
            return None
        n, k_est = max(estimations)
        return k_est, n

    def _echelle(self):
        mentions = lire_echelles(self.phrases)
        if self.denominateur_force:
            d = self.denominateur_force
            return m_par_pt(d), val(d, "lu", "fourni par l'utilisateur", "haute"), True
        if self.echelle_commune:
            d, src = self.echelle_commune
            return m_par_pt(d), val(d, "déduit", src, "moyenne"), True
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
        longueurs = []
        for v in vues0:  # dimensions extérieures et intérieures mesurées, à rapprocher des cotes écrites
            x0, y0, x1, y1 = v.enveloppe.bounds
            longueurs += [x1 - x0, y1 - y0]
            if v.interieur is not None:
                ix0, iy0, ix1, iy1 = v.interieur.bounds
                longueurs += [ix1 - ix0, iy1 - iy0]
        ecrites = valeurs_metriques(self.texte)
        r_texte = [x / L for x in ecrites for L in longueurs if L > 20]
        cons = consensus(r_cotes + r_baies + r_texte, tol=0.015, mini=2)
        n_texte = sum(1 for r in r_texte if cons and abs(r - cons[0]) <= 0.015 * cons[0])
        src_cotes = (f"{len(r_cotes)} ligne(s) de cote, {len(r_baies)} largeur(s) de baie, "
                     f"{n_texte} dimension(s) écrite(s) rapprochée(s) du contour")
        if cons:
            k_cal, n = cons
            d_cal = round(k_cal / m_par_pt(1))
            if k_mention and (abs(k_cal - k_mention) / k_mention <= 0.03 or n < 3):
                return k_mention, val(d, "lu", f"mention « Ech 1:{d} », confirmée par {n} cote(s) écrite(s) ({src_cotes})", "haute"), True
            if k_mention:
                self.alertes.append(f"Échelle : la mention dit 1:{d} mais {n} cote(s) écrite(s) donnent 1:{d_cal} "
                                    "(PDF réduit à l'impression ?) → cotes retenues.")
            return k_cal, val(d_cal, "déduit", f"calibrée sur {n} cote(s) écrite(s) ({src_cotes})", "haute" if n >= 3 else "moyenne"), k_mention is None or abs(k_cal - k0) / k0 < 0.01
        cal = self._calage_pieces()
        if cal:
            k_p, n_p = cal
            d_p = round(k_p / m_par_pt(1))
            if k_mention and abs(k_p - k_mention) / k_mention <= 0.10:
                return k_mention, val(d, "lu", f"mention « Ech 1:{d} », cohérente avec {n_p} surfaces de pièces écrites", "haute"), True
            if k_mention:
                self.alertes.append(f"Échelle : la mention dit 1:{d} mais les surfaces des {n_p} pièces écrites donnent ≈ 1:{d_p} "
                                    "(plan réduit à l'impression ?) → échelle des pièces retenue, à vérifier sur une cote.")
            return k_p, val(d_p, "déduit", f"calée sur {n_p} surfaces de pièces écrites (± 5 %)", "moyenne"), True
        if k_mention:
            self.alertes.append("Échelle non vérifiée par une cote écrite : contrôler une dimension connue.")
            return k_mention, val(d, "lu", f"mention « Ech 1:{d} » (aucune cote pour la vérifier)", "moyenne"), True
        raise ValueError("Échelle introuvable (ni mention ni cote écrite) : passer denominateur=100 ou la valeur du cartouche.")

    # ------------------------------------------------------------------ nord
    def _nord(self):
        if self.angle_force is not None:
            return val(round(self.angle_force, 1), "lu", "fourni par l'utilisateur", "haute", "°")
        fleches = nord_mod.detecter_fleches_nord(self.p.lines)
        if not fleches and (a := lire_nord_texte(self.texte)) is not None:
            return val(a, "lu", "flèche « NORD » écrite sur le plan", "moyenne", "°",
                       explication="angle du nord par rapport au haut de la feuille, positif vers la droite")
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
        self.texte = self.p.extract_text() or ""
        # texte dessiné en traits (SHX, cartouche aplati) : OCR local, ajouté aux phrases et au texte de la page
        self.ocr = ocr.textes_page(self.p)
        if self.ocr:
            from .textes import Phrase
            self.phrases += [Phrase(t, x0, top, x1, bottom, "ltr") for (t, x0, top, x1, bottom, _) in self.ocr]
            self.texte += "\n" + "\n".join(t for t, *_ in self.ocr)
        self.etiquettes = lire_etiquettes_baies(self.phrases)
        self.formes = formes_remplies(self.p)
        if not self.formes:
            raise ValueError("Aucun mur détecté : page sans formes remplies.")
        k, ech, _ = self._echelle()
        vues = self._geometrie(k)
        if not vues:
            raise ValueError("Aucun mur détecté : style de dessin non reconnu (murs non remplis ?). "
                             "Demander un PDF avec murs en aplat, ou un DXF.")
        apparies, libres = self._apparier(vues, k)
        libres = self._baies_en_aplat(vues, k, apparies, libres)
        # ouvertures sans étiquette : < 0,60 m = bruit (hachures) ; sinon baie à largeur mesurée et hauteur supposée
        self.ignorees = sum(1 for (iv, jf, a, b) in libres if (b - a) * k < 0.6)
        libres = [o for o in libres if (o[3] - o[2]) * k >= 0.6]
        for (iv, jf, a, b) in libres:
            f = vues[iv].facades[jf]
            larg = round((b - a) * k, 2)
            cx, cy = f.point((a + b) / 2)
            haut = 2.15 if larg >= 1.6 else 1.35
            self.etiquettes.append(EtiquetteBaie(nom=None, largeur_m=larg, hauteur_m=haut, allege_m=None, x=cx, y=cy, sens="ltr",
                                                 complement="sans étiquette", tag_l="déduit", src_l="largeur mesurée sur le plan",
                                                 tag_h="supposé", src_h="hauteur courante supposée (baie sans étiquette)"))
            apparies.append((len(self.etiquettes) - 1, (iv, jf, a, b)))
        nord = self._nord()
        angle = nord["valeur"]
        niveaux = self._niveaux(vues, k)
        pieces = lire_pieces(self.phrases)

        out_niv = []
        for iv in sorted(range(len(vues)), key=lambda i: _ordre(niveaux[i]["valeur"])):
            out_niv.append(self._niveau(vues[iv], iv, niveaux[iv], k, angle, nord, apparies, pieces))
        if libres:
            par_facade: dict = {}
            for (iv, jf, a, b) in libres:
                par_facade.setdefault((iv, jf), []).append((b - a) * k)
            for (iv, jf), largeurs in par_facade.items():
                f = vues[iv].facades[jf]
                self.alertes.append(f"{niveaux[iv]['valeur']} façade F{jf + 1}{' (' + f.nom_cote + ')' if f.nom_cote else ''} : "
                                    f"{len(largeurs)} ouverture(s) sans étiquette ({', '.join(f'{x:.2f}' for x in sorted(largeurs))} m) "
                                    "comptée(s) avec une hauteur supposée : vérifier.")
        if self.ignorees:
            self.alertes.append(f"{self.ignorees} petite(s) interruption(s) de mur de moins de 0,60 m ignorée(s) (motifs de hachures, joints).")
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
            "alertes": self.alertes,
        }

    def _baies_en_aplat(self, vues, k, apparies, libres):
        """Ouvertures dessinées en aplat de couleur : type par la légende, dimensions par le texte du plan."""
        pastilles = []
        for pg, c in self.formes:
            x0, y0, x1, y1 = pg.bounds
            if 3 <= x1 - x0 <= 25 and 3 <= y1 - y0 <= 25:
                pastilles.append(((x0, y0, x1, y1), c))
        legende = lire_legende(self.phrases, pastilles)
        types = lire_dimensions_types(self.texte)
        restants = []
        for (iv, jf, a, b) in libres:
            f = vues[iv].facades[jf]
            c = next((c for (m0, m1, c) in f.marqueurs if m0 < b and m1 > a), None)
            if c is None:
                restants.append((iv, jf, a, b))
                continue
            lib = legende.get(c, "")
            dernier = lib.split()[-1] if lib else ""
            code = dernier if re.fullmatch(r"[A-Z]{1,4}\d*", dernier) else (lib or "baie")
            dims = next((t for t in types if lib and correspond(lib, t["nom"])), None)
            cx, cy = f.point((a + b) / 2)
            src = f"dimensions « {dims['nom']} » écrites sur le plan" if dims else ""
            e = EtiquetteBaie(nom=code, largeur_m=dims["largeur_m"] if dims else round((b - a) * k, 2),
                              hauteur_m=dims["hauteur_m"] if dims else 1.35, allege_m=None, x=cx, y=cy, sens="ltr",
                              complement=lib, tag_l="lu" if dims else "déduit",
                              src_l=src or "largeur mesurée sur le plan", tag_h="lu" if dims else "supposé",
                              src_h=src or "hauteur courante supposée (non écrite)")
            self.etiquettes.append(e)
            apparies.append((len(self.etiquettes) - 1, (iv, jf, a, b)))
        return restants

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
                  "longueur_int_m": val(round(max(l_int, 0.0), 2), "déduit", "contour - épaisseurs aux angles", "moyenne", "m"),
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
                 "largeur_m": val(e.largeur_m, e.tag_l, e.src_l, "haute" if e.tag_l == "lu" else "moyenne", "m"),
                 "hauteur_m": val(e.hauteur_m, e.tag_h, e.src_h, "haute" if e.tag_h == "lu" else "faible", "m"),
                 "surface_m2": val(round(e.largeur_m * e.hauteur_m, 2), "déduit", "largeur x hauteur", "haute" if e.tag_h == "lu" else "faible", "m²"),
                 "largeur_mesuree_plan_m": val(round(larg_plan, 2), "déduit", "ouverture dans le mur / l'isolant", "moyenne", "m")}
            if e.allege_m is not None:
                d["allege_m"] = val(e.allege_m, "lu", "étiquette « all. »", "haute", "m")
            if e.complement:
                d["mention"] = e.complement
            if e.complement == "sans étiquette":
                d["a_verifier"] = "baie sans étiquette : hauteur supposée, type et dimensions à vérifier"
            elif abs(larg_plan - e.largeur_m) > 0.12:
                d["a_verifier"] = "largeur mesurée ≠ largeur écrite (tableau, coffre ou mauvais appariement)"
            d["_ouverture_pt"] = [round(c, 1) for c in (*f.point(a), *f.point(b))]
            d["_etiquette_pt"] = [round(e.x, 1), round(e.y, 1)]
            baies.append(d)
        baies.sort(key=lambda d: (int(d["facade"][1:]), d["nom"] or ""))

        s_int = v.interieur.area * k * k if v.interieur is not None else 0.0
        p_int = v.interieur.length * k if v.interieur is not None else 0.0
        pcs = [pc for pc in pieces if v.enveloppe.contains(Point(pc["x"], pc["y"]))]
        # « Vide sur séjour » : la partie non étiquetée de l'étage est un vide (double hauteur), pas du plancher
        vide = None
        if any(RE_VIDE.search(ph.texte) and v.enveloppe.contains(Point(ph.cx, ph.cy)) for ph in self.phrases) and pcs:
            s_v = s_int - sum(pc["surface_m2"] for pc in pcs) / 0.95
            if s_v > 2:
                vide = val(round(s_v, 1), "déduit", "« vide sur… » écrit : surface intérieure − pièces étiquetées / 0,95",
                           "faible", "m²")
        return {
            "surface_vide_m2": vide,
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

def batiment(niv, hsp_v: dict, h_etage_v: dict | None = None) -> dict:
    """Synthèse bâtiment. Hauteur des murs = hauteur d'étage (plancher à plancher) si elle est lue, sinon HSP."""
    hsp = hsp_v["valeur"]
    hm = h_etage_v["valeur"] if h_etage_v else hsp
    nom_h = "hauteur d'étage" if h_etage_v else "HSP"
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
            murs_o[o] = murs_o.get(o, 0) + f["longueur_int_m"]["valeur"] * hm
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
        "refend_mur_ml": val(round(nref * hm, 1), D, f"{nref} jonction(s) x {nom_h}", "faible", "m", liaison="refend / mur"),
        "angle_saillant_ml": val(round(sal * hm, 1), D, f"{sal} angle(s) x {nom_h}", "moyenne", "m", liaison="angle de mur saillant"),
        "angle_rentrant_ml": val(round(ren * hm, 1), D, f"{ren} angle(s) x {nom_h}", "moyenne", "m", liaison="angle de mur rentrant"),
        "menuiserie_appui_ml": val(round(larg, 1), D, "Σ largeurs des baies", "haute", "m", liaison="menuiserie / mur : appui"),
        "menuiserie_linteau_ml": val(round(larg, 1), D, "Σ largeurs des baies", "haute", "m", liaison="menuiserie / mur : linteau"),
        "menuiserie_tableaux_ml": val(round(2 * haut, 1), D, "Σ 2 x hauteurs des baies", "haute", "m", liaison="menuiserie / mur : tableaux"),
    }
    s_int = sum(n["surface_interieure_m2"]["valeur"] - ((n.get("surface_vide_m2") or {}).get("valeur") or 0) for n in niv)
    out = {
        "nombre_niveaux": val(nb, D, "vues en plan détectées", "haute"),
        "hauteur_sous_plafond_m": hsp_v,
        "surface_interieure_totale_m2": val(round(s_int, 1), D, "Σ surfaces intérieures (vides de double hauteur retirés)", "moyenne", "m²",
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
    if h_etage_v:
        out["hauteur_etage_m"] = h_etage_v
    return out


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
