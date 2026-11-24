"""Rapport « feuille de route » : valeurs à saisir dans Pléiades, dans l'ordre de saisie (docs/knowledge.md §3).

Chaque valeur affiche son étiquette (lu / déduit / supposé) et sa confiance. La dernière section liste
toutes les hypothèses (« supposé ») à valider. HTML → PDF avec WeasyPrint.
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
    cls = {"conforme probable": "ok", "non conforme probable": "ko", "incertain": "moy"}
    lignes = []
    for k, kmax, u in (("Bbio", "Bbio_max", "pts"), ("Cep", "Cep_max", "kWhep/m²"), ("Cep_nr", "Cep_nr_max", "kWhep/m²")):
        lignes.append([k, fv(est[k]), fv(s[kmax], u), f"<span class='{cls[e['verdict'][k]]}'>{e['verdict'][k]}</span>"])
    H.append(table(["Indicateur", "Estimation [fourchette]", "Seuil max", "Verdict"], lignes))
    if s["approx"]:
        H.append("<p class='alerte'>Seuils « approx » : MbHSP/McHSP inconnus (décret 2026-200).</p>")
    H.append(f"<p>Sref : {fv(e['_trace_sref'])} — Ic construction max : {fv(e['ic_construction_max']['Ic_construction_max'])} "
             f"<span class='note'>(ACV non estimée dans cette version)</span></p>")

    # ---- 1. bibliothèque projet
    H.append("<h2>1. Bibliothèque projet</h2><p class='etape'>Pléiades › Bibliothèque › Parois / Menuiseries / Ponts thermiques</p>")
    p0 = e["propositions"]["propositions"][0] if e["propositions"]["propositions"] else None
    lignes = [["Mur extérieur", fv(hyp["U_murs"]), escape(plan["niveaux"][0]["murs_exterieurs"]["isolation"]["valeur"]),
               escape(f"{p0['murs']['isolant']} {p0['murs']['epaisseur_cm']} cm (U {p0['murs']['U']})") if p0 else "—"],
              ["Plancher haut / toiture", fv(hyp["U_toiture"]), "type de toiture à lire sur la coupe",
               escape(f"{p0['toiture']['isolant']} {p0['toiture']['epaisseur_cm']} cm (U {p0['toiture']['U']})") if p0 else "—"],
              ["Plancher bas", fv(hyp["U_plancher_bas"]), "", escape(f"{p0['plancher_bas']['isolant']} {p0['plancher_bas']['epaisseur_cm']} cm (U {p0['plancher_bas']['U']})") if p0 else "—"]]
    H.append("<h3>Parois</h3>" + table(["Paroi", "U retenu pour l'estimation", "Remarque", "Proposition n°1 (étape 5)"], lignes))
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
        ["Zonage", "1 bâtiment, 1 zone, 1 groupe (maison individuelle) <span class='tag suppose'>supposé</span>"],
        ["Génération (bâtiment)", fv(hyp["systeme"])],
        ["Ventilation (groupe)", "simple flux hygroréglable B <span class='tag suppose'>supposé</span>"],
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
                   [[str(p["rang"]), escape(f"{p['murs']['isolant']} {p['murs']['epaisseur_cm']} cm"),
                     escape(f"{p['toiture']['isolant']} {p['toiture']['epaisseur_cm']} cm"),
                     escape(f"{p['plancher_bas']['isolant']} {p['plancher_bas']['epaisseur_cm']} cm"),
                     escape(p["menuiseries"]["nom"]), escape(p["systeme"]), fv(p["Bbio"]), fv(p["Cep"]), fv(p["cout_eur"])]
                    for p in pr["propositions"]]) if pr["propositions"] else "<p class='alerte'>Aucune combinaison du catalogue ne passe les seuils estimés.</p>")

    # ---- 11. ACV
    H.append("<h2>11. ACV</h2><p class='etape'>Pléiades › ACV : inventaire par lot, PCE, fiches</p>")
    H.append(f"<p>Seuil Ic construction : {fv(e['ic_construction_max']['Ic_construction_max'])}. "
             "Inventaire par lot et Ic construction : à faire dans Pléiades (module ACV de l'outil à venir). "
             "Remplacer les DED par des FDES spécifiques dès qu'elles existent (gain majeur).</p>")

    # ---- 12. hypothèses, alertes, manquants
    H.append("<h2>12. Hypothèses à valider, alertes, données manquantes</h2>")
    sup = list(_suppositions({"plan": plan, "hypotheses": hyp}))
    H.append(table(["Donnée", "Valeur supposée", "Raison"],
                   [[escape(c), fv(v), escape(v.get("source", ""))] for c, v in sup]))
    H.append("<h3>Alertes</h3><ul>" + "".join(f"<li class='alerte'>{escape(a)}</li>" for a in e["alertes"]) + "</ul>")
    H.append("<h3>Données à récupérer</h3><ul>" + "".join(f"<li>{escape(m)}</li>" for m in e["manquants"]) + "</ul>")
    H.append("</body></html>")
    return "".join(H)


def generer_pdf(etude: dict, sortie: str | Path) -> Path:
    from weasyprint import HTML

    sortie = Path(sortie)
    HTML(string=generer_html(etude)).write_pdf(sortie)
    return sortie
