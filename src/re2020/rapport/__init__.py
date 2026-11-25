"""Rapport « feuille de route » : valeurs à saisir dans Pléiades, dans l'ordre de saisie (docs/knowledge.md §3).

Chaque valeur affiche son étiquette (lu / déduit / supposé) et sa confiance. La dernière section liste
toutes les hypothèses (« supposé ») à valider. HTML → PDF avec WeasyPrint, ou xhtml2pdf (100 % Python) si WeasyPrint ne fonctionne pas (Windows).
"""
from __future__ import annotations

from html import escape
from pathlib import Path

CSS = """
@page { size: A4; margin: 14mm 12mm 16mm 12mm;
        @bottom-center { content: "Feuille de route RE2020 — estimation, pas un calcul réglementaire — p. " counter(page) "/" counter(pages);
                         font-size: 7.5pt; color: #666; } }
body { font-family: "DejaVu Sans", sans-serif; font-size: 8.6pt; color: #1d1d1d; }
h1 { font-size: 15pt; margin: 0 0 2mm; color: #0b3d5c; }
h2 { font-size: 11pt; margin: 6mm 0 2mm; padding: 1mm 2mm; background: #0b3d5c; color: white; }
h3 { font-size: 9.5pt; margin: 3mm 0 1mm; color: #0b3d5c; }
table { border-collapse: collapse; width: 100%; margin: 1mm 0 2mm; }
th, td { border: 0.3pt solid #bbb; padding: 0.8mm 1.4mm; text-align: left; vertical-align: top; }
th { background: #e8eef3; font-weight: bold; }
.tag { font-size: 6.5pt; padding: 0 1mm; border-radius: 1mm; color: white; white-space: nowrap; }
.lu { background: #2e7d32; } .deduit { background: #1565c0; } .suppose { background: #e65100; }
.conf { font-size: 6.5pt; color: #555; }
.ok { color: #2e7d32; font-weight: bold; } .ko { color: #c62828; font-weight: bold; } .moy { color: #e65100; font-weight: bold; }
.alerte { color: #b71c1c; }
.note { color: #555; font-size: 7.5pt; }
.etape { font-size: 7.5pt; color: #0b3d5c; font-weight: bold; }
"""

CLASSE_TAG = {"lu": "lu", "déduit": "deduit", "supposé": "suppose"}


def badge(v: dict) -> str:
    t = v.get("tag")
    if not t:
        return ""
    return f' <span class="tag {CLASSE_TAG[t]}">{escape(t)}</span><span class="conf"> {escape(v.get("confiance", ""))}</span>'


def fv(v, unite: str | None = None, nd: int | None = None) -> str:
    """Formate une valeur tracée (ou brute) avec son badge."""
    if isinstance(v, dict) and "valeur" in v:
        x = v["valeur"]
        u = v.get("unite", unite) or ""
        if isinstance(x, float) and nd is not None:
            x = round(x, nd)
        txt = "—" if x is None else (f"{x:g}" if isinstance(x, float) else str(x))
        s = f"{escape(txt)} {escape(u)}".strip()
        if v.get("fourchette"):
            s += f' <span class="note">[{v["fourchette"][0]:g} – {v["fourchette"][1]:g}]</span>'
        return s + badge(v)
    if v is None:
        return "—"
    return escape(f"{v:g}" if isinstance(v, float) else str(v)) + (f" {escape(unite)}" if unite else "")


def table(entetes, lignes) -> str:
    h = "".join(f"<th>{escape(e)}</th>" for e in entetes)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes)
    return f"<table><tr>{h}</tr>{b}</table>"


def _suppositions(o, chemin=""):
    """Toutes les valeurs « supposé » de l'étude, pour la liste des hypothèses à valider."""
    if isinstance(o, dict):
        if o.get("tag") == "supposé" and "valeur" in o:
            yield chemin, o
        for k, v in o.items():
            if not k.startswith("_"):
                yield from _suppositions(v, f"{chemin}/{k}" if chemin else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _suppositions(v, f"{chemin}[{i}]")


def generer_html(e: dict) -> str:
    plan, hyp, est, s, par = e["plan"], e["hypotheses"], e["estimation"], e["seuils"], e["parametres"]
    bat = plan["batiment"]
    H = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"]
    H.append(f"<h1>Feuille de route RE2020 — {escape(e['projet'])}</h1>")
    H.append(f"<p class='note'>Rapport du {e['date_rapport']} — plan : {escape(plan['source'])} — zone {escape(par['zone'])}, "
             f"altitude {par['altitude_m']:g} m, dépôt de PC {escape(par['date_pc'])}. "
             "Étiquettes : <span class='tag lu'>lu</span> sur le document, <span class='tag deduit'>déduit</span> calculé, "
             "<span class='tag suppose'>supposé</span> hypothèse à valider. "
             "<b>Estimation pour préparer la saisie : les résultats officiels sont ceux de Pléiades / moteur CSTB.</b></p>")

    # ---- synthèse
    H.append("<h2>Synthèse</h2>")
    cls = {"conforme probable": "ok", "non conforme probable": "ko", "incertain": "moy", "hors périmètre (tertiaire)": "moy",
           "lecture insuffisante": "ko"}
    q = e.get("qualite") or {}
    if q.get("niveau") == "insuffisante":
        H.append("<p class='alerte'><b>Lecture du plan insuffisante : les chiffres ci-dessous ne sont pas exploitables.</b> "
                 + escape(" ; ".join(q["graves"])) + ". À fournir : " + escape(" ; ".join(q["conseils"])) + ".</p>")
    lignes = []
    for k, kmax, u in (("Bbio", "Bbio_max", "pts"), ("Cep", "Cep_max", "kWhep/m²"), ("Cep_nr", "Cep_nr_max", "kWhep/m²")):
        lignes.append([k, fv(est[k]), fv(s[kmax], u), f"<span class='{cls[e['verdict'][k]]}'>{e['verdict'][k]}</span>"])
    H.append(table(["Indicateur", "Estimation [fourchette]", "Seuil max", "Verdict"], lignes))
    if s["approx"]:
        H.append("<p class='alerte'>Seuils « approx » : MbHSP/McHSP inconnus (décret 2026-200).</p>")
    a = e["acv"]
    H.append(f"<p>Sref : {fv(e['_trace_sref'])} — Ic construction (DED) : {fv(a['Ic_construction']['par_defaut'])} / max "
             f"{fv(a['Ic_construction_max'])} — avec FDES prioritaires : {fv(a['Ic_construction']['top_fiches'])} — "
             f"Ic énergie : {fv(a['Ic_energie'])}</p>")

    # ---- dossier lu et contrôles croisés
    dos = e.get("dossier") or {}
    if dos.get("pages_lues") or e.get("controles"):
        H.append("<h2>Dossier lu et contrôles croisés</h2>")
        if e.get("tertiaire"):
            H.append(f"<p class='alerte'>Usage « {escape(str(e['usage']['valeur']))} » : seuils et modèle de l'outil = maison "
                     "individuelle. Les données d'entrée ci-dessous restent valables ; Bbio/Cep à calculer dans Pléiades.</p>")
        H.append(f"<p class='note'>Pages exploitées : {escape(', '.join(dos.get('pages_lues', [])))}"
                 f" · plans : {escape(', '.join(plan.get('pages_plans', [])))}</p>")
        src = e.get("parametres_sources", {})
        H.append(table(["Donnée", "Valeur"], [["Zone climatique", fv(src.get("zone"))], ["Altitude", fv(src.get("altitude_m"), "m")],
                                               ["Dépôt du permis", fv(src.get("date_pc"))]]
                       + [[escape(k.replace("_", " ").capitalize()), fv(v)] for k, v in dos.get("infos", {}).items()
                          if isinstance(v, dict) and k not in ("zone", "altitude_m", "date_pc", "residentiel")]))
        if e.get("controles"):
            H.append("<h3>Contrôles croisés : plan mesuré / dossier écrit</h3>" + table(
                ["Grandeur", "Plan", "Dossier", "Écart", "Statut"],
                [[escape(c["grandeur"]), f"{c['plan']:g} {escape(c['unite'])}" if c["plan"] is not None else "—",
                  f"{c['dossier']:g} {escape(c['unite'])}" if c["dossier"] is not None else "—",
                  f"{c['ecart_pct']:+.1f} %" if c["ecart_pct"] is not None else "—",
                  f"<span class='{'ok' if c['statut'] == 'ok' else 'ko'}'>{escape(c['statut'])}</span>"] for c in e["controles"]]))

    # ---- 1. bibliothèque projet
    H.append("<h2>1. Bibliothèque projet</h2><p class='etape'>Pléiades › Bibliothèque › Parois / Menuiseries / Ponts thermiques</p>")
    p0 = e["propositions"]["propositions"][0] if e["propositions"]["propositions"] else None
    def compo(k):
        return (escape(p0[k]["composition"]) + f" <span class='muet'>(U {p0[k]['U']})</span>") if p0 else "—"
    lignes = [["Mur extérieur", fv(hyp["U_murs"]), escape(plan["niveaux"][0]["murs_exterieurs"]["isolation"]["valeur"]), compo("murs")],
              ["Plancher haut / toiture", fv(hyp["U_toiture"]), "type de toiture à lire sur la coupe", compo("toiture")],
              ["Plancher bas", fv(hyp["U_plancher_bas"]), "", compo("plancher_bas")]]
    H.append("<h3>Parois</h3>" + table(["Paroi", "U retenu pour l'estimation", "Remarque", "Composition proposée n°1 (ext. → int.)"], lignes))
    if p0:
        H.append("<h3>Compositions à créer dans la bibliothèque (proposition n°1)</h3>")
        for k, titre in (("murs", "Mur extérieur"), ("toiture", "Plancher haut / toiture"), ("plancher_bas", "Plancher bas")):
            c = p0[k]
            ref = f" — modèle : projet « {escape(c['ref_projet'])} »" if c.get("ref_projet") else ""
            H.append(f"<p><strong>{titre}</strong> : {escape(c['systeme'])}{ref} — épaisseur totale {c['epaisseur_totale_cm']:g} cm, "
                     f"U {c['U']} W/m².K</p>")
            H.append(table(["Couche (ext. → int.)", "Épaisseur", "λ (W/m.K)", "R (m².K/W)", "Origine"],
                           [[escape(x["materiau"]) + (" <span class='ko'>non certifié : λ +15 %</span>" if x.get("isolant") and not x.get("certifie", True) else ""),
                             f"{x['epaisseur_cm']:g} cm", f"{x['lambda_W_mK']:g}" if x.get("lambda_W_mK") else "—", f"{x['R_m2K_W']:g}",
                             escape(x.get("tag", "")) + (f" — {escape(x['note'])}" if x.get("note") else "")] for x in c["couches"]]))
    H.append("<h3>Menuiseries</h3>" + table(["Uw", "Sw", "Proposition n°1"],
             [[fv(hyp["Uw"]), fv(hyp["Sw"]), escape(f"{p0['menuiseries']['nom']} (Uw {p0['menuiseries']['Uw']}, Sw {p0['menuiseries']['Sw']})") if p0 else "—"]]))
    H.append("<h3>Ponts thermiques (Ψ)</h3>" + table(["Liaison", "Ψ (W/m.K)", "Source"],
             [[escape(d["liaison"]), fv(d["psi"]), escape(d["psi"]["source"])] for d in hyp["ponts_thermiques"]]))

    # ---- 2. données par défaut
    H.append("<h2>2. Données par défaut</h2><p class='etape'>Pléiades › Données par défaut</p>")
    H.append(table(["Donnée", "Valeur"], [["Hauteur sous plafond", fv(bat["hauteur_sous_plafond_m"])],
                                          ["Échelle du plan", fv(plan["echelle"]["denominateur"]) + f" <span class='note'>(1 pt = {plan['echelle']['m_par_pt']} m)</span>"]]))

    # ---- 3. géométrie
    H.append("<h2>3. Géométrie</h2><p class='etape'>Pléiades › Géométrie : fond de plan, orientation, enveloppe, baies, hauteurs</p>")
    n = plan["nord"]
    H.append(f"<p><b>Orientation :</b> nord à {fv(n)} du haut de la feuille "
             f"<span class='note'>({escape(n.get('explication', ''))})</span></p>")
    for niv in plan["niveaux"]:
        m = niv["murs_exterieurs"]
        H.append(f"<h3>{escape(niv['niveau']['valeur'])} — {escape(niv['forme']['valeur'])}</h3>")
        H.append(table(["Emprise", "Surface emprise", "Couche pleine", "Bande ext.", "Bande int.", "Isolation", "Surface int."],
                       [[fv(niv["emprise_m"]["largeur"]) + " x " + fv(niv["emprise_m"]["profondeur"]), fv(niv["surface_emprise_m2"]),
                         fv(m["couche_pleine_m"]), fv(m["bande_hachuree_ext_m"]), fv(m["bande_hachuree_int_m"]), fv(m["isolation"]),
                         fv(niv["surface_interieure_m2"])]]))
        H.append(table(["Façade", "Côté feuille", "Long. ext.", "Long. int.", "Azimut", "Orientation"],
                       [[f["id"], escape(f["cote_feuille"] or "oblique"), fv(f["longueur_ext_m"]), fv(f["longueur_int_m"]),
                         fv(f.get("azimut_deg")), fv(f.get("orientation"))] for f in niv["facades"]]))
        if niv["baies"]:
            H.append(table(["Baie", "Façade", "Orientation", "Largeur", "Hauteur", "Allège", "Surface", "Remarque"],
                           [[escape(b["nom"] or "?"), b["facade"], escape(b["orientation"] or "—"), fv(b["largeur_m"]), fv(b["hauteur_m"]),
                             fv(b.get("allege_m")), fv(b["surface_m2"]),
                             "<span class='alerte'>" + escape(b["a_verifier"]) + "</span>" if b.get("a_verifier") else escape(b.get("mention", ""))]
                            for b in niv["baies"]]))

    # ---- 4. toitures
    H.append("<h2>4. Toitures</h2><p class='etape'>Pléiades › Toitures</p>")
    H.append(table(["Donnée", "Valeur"], [["Surface plancher haut", fv(bat["plancher_haut_m2"])],
                                          ["Type de toiture", "<span class='alerte'>non lu : combles perdus / rampants / terrasse à préciser</span>"]]))

    # ---- 5. parties de bâtiment
    H.append("<h2>5. Parties de bâtiment et usages</h2><p class='etape'>Pléiades › Partie de bâtiment, usage des pièces</p>")
    H.append(table(["Niveau", "Pièce", "Surface"], [[escape(niv["niveau"]["valeur"]), escape(pc["nom"] or "?"), f"{pc['surface_m2']:g} m² <span class='tag lu'>lu</span>"]
                                                   for niv in plan["niveaux"] for pc in niv["pieces"]]))
    H.append(f"<p>Surface des pièces étiquetées : {fv(bat['surface_pieces_etiquetees_totale_m2'])} — surface intérieure : "
             f"{fv(bat['surface_interieure_totale_m2'])} — Sref retenue : {fv(e['_trace_sref'])}</p>")

    # ---- 6. masques
    H.append("<h2>6. Masques</h2><p class='etape'>Pléiades › Masques proches et lointains</p>"
             "<p class='alerte'>Non lus sur le plan : casquettes, débords et masques lointains à saisir.</p>")

    # ---- 7. ponts thermiques
    H.append("<h2>7. Ponts thermiques</h2><p class='etape'>Pléiades › Ponts thermiques (longueurs)</p>")
    H.append(table(["Liaison", "Longueur", "Ψ", "Ψ·L (W/K)"],
                   [[escape(d["liaison"]), f"{d['longueur_m']:g} m", fv(d["psi"]), f"{d['longueur_m'] * d['psi']['valeur']:.1f}"]
                    for d in hyp["ponts_thermiques"]]))
    H.append(f"<p>Ratio Ψ : {fv(hyp['ratio_psi'])} <span class='note'>(exigence art. 22.II : ≤ 0,33)</span></p>")

    # ---- 8. RE2020
    H.append("<h2>8. RE2020 : météo, zonage, systèmes</h2><p class='etape'>Pléiades › RE2020</p>")
    H.append(table(["Donnée", "Valeur"], [
        ["Zone climatique / altitude", f"{escape(par['zone'])} / {par['altitude_m']:g} m <span class='tag lu'>lu</span>"],
        ["Usage", fv(e.get("usage")) if e.get("usage") else "maison individuelle <span class='tag suppose'>supposé</span>"],
        ["Zonage", "1 bâtiment, 1 zone, 1 groupe (maison individuelle) <span class='tag suppose'>supposé</span>"],
        ["Génération (bâtiment)", fv(hyp["systeme"])],
        ["Ventilation (groupe)", fv(hyp["ventilation"]) if hyp.get("ventilation") else "simple flux hygroréglable B <span class='tag suppose'>supposé</span>"],
        ["Perméabilité Q4Pa-surf", fv(hyp["q4"])],
    ]))

    # ---- 9. Th-BCE
    H.append("<h2>9. Calcul Th-BCE : estimation à comparer</h2><p class='etape'>Pléiades › Th-BCE (Th-DB systèmes fictifs pour Bbio/DH)</p>")
    d = est["deperditions_W_K"]
    H.append(table(["Poste", "Déperditions (W/K)"], [[escape(k.replace("_", " ")), f"{v:.1f}"] for k, v in d.items()]))
    H.append(table(["Besoin", "Estimation"], [[k, fv(v)] for k, v in est["besoins_kWh_m2"].items()]))
    H.append(f"<p class='note'>Sensibilité du Bbio (± points) : {escape(str(est['sensibilite_Bbio_points']))}. {escape(est['avertissement'])}</p>")

    # ---- 10. propositions
    pr = e["propositions"]
    H.append("<h2>10. Propositions conformes (estimation)</h2>")
    H.append(f"<p class='note'>{pr['nb_combinaisons_testees']} combinaisons testées, {pr['nb_conformes']} sous les seuils avec 5 % de marge. "
             f"{escape(pr['avertissement'])}</p>")
    H.append(table(["#", "Murs", "Toiture", "Plancher bas", "Menuiseries", "Système", "Bbio", "Cep", "Coût"],
                   [[str(p["rang"]), escape(p["murs"]["composition"]), escape(p["toiture"]["composition"]),
                     escape(p["plancher_bas"]["composition"]),
                     escape(p["menuiseries"]["nom"]), escape(p["systeme"]), fv(p["Bbio"]), fv(p["Cep"]), fv(p["cout_eur"])]
                    for p in pr["propositions"]]) if pr["propositions"] else "<p class='alerte'>Aucune combinaison du catalogue ne passe les seuils estimés.</p>")
    if pr.get("variantes"):
        H.append("<h3>Autres systèmes constructifs au même U que la proposition n°1</h3><p class='note'>Au choix selon la "
                 "structure retenue par l'architecte ; coûts indicatifs supposés.</p>")
        for k, titre in (("murs", "Murs"), ("toiture", "Toiture"), ("plancher_bas", "Plancher bas")):
            v = pr["variantes"].get(k) or []
            if v:
                H.append(f"<p><strong>{titre}</strong></p>" + table(["Système", "Composition (ext. → int.)", "U", "Coût indicatif"],
                         [[escape(x["systeme"]), escape(x["composition"]), f"{x['U']}",
                           f"{x['cout_eur']:,} € HT".replace(",", " ") if x.get("cout_eur") is not None else "—"] for x in v]))

    # ---- 11. ACV
    a = e["acv"]
    H.append("<h2>11. ACV</h2><p class='etape'>Pléiades › ACV : inventaire par lot, PCE, fiches</p>")
    vcls = {"sous le seuil": "ok", "au-dessus du seuil": "ko", "incertain": "moy", "hors périmètre (tertiaire)": "moy",
            "lecture insuffisante": "ko"}
    H.append(table(["Indicateur", "Estimation [fourchette]", "Seuil max", "Verdict"], [
        ["Ic construction — fiches par défaut (DED)", fv(a["Ic_construction"]["par_defaut"]), fv(a["Ic_construction_max"]),
         f"<span class='{vcls[a['verdict']['par_defaut']]}'>{a['verdict']['par_defaut']}</span>"],
        [f"Ic construction — FDES sur les {len(a['recommandations'])} plus gros postes", fv(a["Ic_construction"]["top_fiches"]), "",
         f"<span class='{vcls[a['verdict']['top_fiches']]}'>{a['verdict']['top_fiches']}</span>"],
        ["Ic construction — toutes fiches spécifiques (borne basse)", fv(a["Ic_construction"]["tout_specifique"]), "",
         f"<span class='{vcls[a['verdict']['tout_specifique']]}'>{a['verdict']['tout_specifique']}</span>"],
        ["Ic énergie", fv(a["Ic_energie"]), fv(a["Ic_energie_max"]), ""]]))
    H.append("<h3>Fiches à rechercher en priorité (INIES)</h3>" + table(["Lot", "Élément", "Remplacement", "Gain"],
             [[str(r["lot"]), escape(r["element"]), escape(r["remplacer"]), f"−{r['gain_kg_m2']:g} kg/m²"] for r in a["recommandations"]]))
    H.append("<h3>Inventaire par lot (quantités à saisir)</h3>" + table(["Lot", "Élément", "Quantité", "UF", "Fiche par défaut", "Ic (kg/m²)"],
             [[str(l["lot"]), escape(l["libelle"]), fv(l["quantite"]), escape(l["uf"]),
               escape(f"{l['fiche_defaut']['type']} {l['fiche_defaut']['ic']:g}") + badge(l["fiche_defaut"]), f"{l['ic_defaut_kg_m2']:.1f}"]
              for l in a["elements"]]))
    H.append(table(["Lot", "Ic par défaut", "Ic fiches spécifiques"],
                   [[f"{k} — {escape(v['libelle'])}", f"{v['defaut']:g}", f"{v['specifique']:g}"] for k, v in a["par_lot"].items()]))
    H.append(f"<p class='note'>Ic chantier : {fv(a['Ic_chantier'])}. Hypothèses : structure {fv(a['hypotheses']['structure'])}, "
             f"plancher {fv(a['hypotheses']['plancher_intermediaire'])}, menuiseries {fv(a['hypotheses']['menuiseries'])}.</p>")

    # ---- 12. hypothèses, alertes, manquants
    H.append("<h2>12. Hypothèses à valider, alertes, données manquantes</h2>")
    sup = list(_suppositions({"plan": plan, "hypotheses": hyp, "acv": {"hypotheses": e["acv"]["hypotheses"]}}))
    H.append(table(["Donnée", "Valeur supposée", "Raison"],
                   [[escape(c), fv(v), escape(v.get("source", ""))] for c, v in sup]))
    H.append("<h3>Alertes</h3><ul>" + "".join(f"<li class='alerte'>{escape(a)}</li>" for a in e["alertes"]) + "</ul>")
    H.append("<h3>Données à récupérer</h3><ul>" + "".join(f"<li>{escape(m)}</li>" for m in e["manquants"]) + "</ul>")
    H.append("</body></html>")
    return "".join(H)


CSS_SIMPLE = """
@page { size: a4 portrait; margin: 1.4cm 1.2cm 1.8cm 1.2cm;
        @frame pied { -pdf-frame-content: pied; bottom: 0.6cm; height: 0.8cm; left: 1.2cm; right: 1.2cm; } }
body { font-family: Helvetica; font-size: 8pt; color: #1d1d1d; }
h1 { font-size: 15pt; color: #0b3d5c; margin: 0 0 4pt 0; }
h2 { font-size: 11pt; background-color: #0b3d5c; color: #ffffff; padding: 3pt; margin: 12pt 0 4pt 0; }
h3 { font-size: 9.5pt; color: #0b3d5c; margin: 8pt 0 2pt 0; }
table { width: 100%; margin: 2pt 0 6pt 0; }
th, td { border: 0.3pt solid #bbbbbb; padding: 2pt; text-align: left; vertical-align: top; }
th { background-color: #e8eef3; font-weight: bold; }
.tag { font-size: 6.5pt; color: #ffffff; }
.lu { background-color: #2e7d32; } .deduit { background-color: #1565c0; } .suppose { background-color: #e65100; }
.conf { font-size: 6.5pt; color: #555555; }
.ok { color: #2e7d32; font-weight: bold; } .ko { color: #c62828; font-weight: bold; } .moy { color: #e65100; font-weight: bold; }
.alerte { color: #b71c1c; } .note { color: #555555; font-size: 7.5pt; } .muet { color: #777777; }
.etape { font-size: 7.5pt; color: #0b3d5c; font-weight: bold; }
"""


POLICES = [  # (normal, gras) : polices avec λ, Ψ, →, ≤ (Helvetica ne les a pas)
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def _polices() -> str:
    import os

    for normal, gras in POLICES:
        if os.path.exists(normal):
            gras = gras if os.path.exists(gras) else normal
            return (f"@font-face {{ font-family: Rapport; src: url('{normal}'); }}"
                    f"@font-face {{ font-family: Rapport; src: url('{gras}'); font-weight: bold; }}"
                    "body, h1, h2, h3, th, td, p, span, li { font-family: Rapport; }")
    return ""


def generer_pdf(etude: dict, sortie: str | Path, moteur: str | None = None) -> Path:
    """PDF de la feuille de route. WeasyPrint (rendu le plus fidèle) s'il fonctionne ; sinon xhtml2pdf, 100 % Python
    (Windows sans GTK) : le PDF est toujours produit. ``moteur`` = "weasyprint" | "xhtml2pdf" pour forcer."""
    sortie = Path(sortie)
    html = generer_html(etude)
    if moteur != "xhtml2pdf":
        try:
            from weasyprint import HTML

            HTML(string=html).write_pdf(sortie)
            return sortie
        except Exception:  # ImportError / OSError : bibliothèques GTK absentes (Windows)
            if moteur == "weasyprint":
                raise
    from xhtml2pdf import pisa

    simple = html.replace(f"<style>{CSS}</style>", f"<style>{_polices()}{CSS_SIMPLE}</style>").replace(
        "</body>", "<div id='pied' class='note'>Feuille de route RE2020 — estimation, pas un calcul réglementaire — "
                   "p. <pdf:pagenumber/> / <pdf:pagecount/></div></body>")
    opts = {}
    try:  # xhtml2pdf récent : lectures locales confinées ; on autorise le dossier des polices, et aucun accès réseau
        from xhtml2pdf.config.resources import ResourceAccessPolicy

        dossiers = sorted({str(Path(n).parent) for n, _ in POLICES if Path(n).exists()})
        opts["resource_policy"] = ResourceAccessPolicy(allow_remote=False, base_dir=Path.cwd(),
                                                       extra_roots=[Path(d) for d in dossiers])
    except ImportError:
        pass
    with open(sortie, "wb") as f:
        res = pisa.CreatePDF(simple, dest=f, encoding="utf-8", **opts)
    if res.err:
        raise RuntimeError(f"PDF non généré ({res.err} erreur(s) xhtml2pdf)")
    return sortie
