"""API FastAPI locale : déposer un plan PDF, récupérer le JSON de l'étude et le PDF « feuille de route ».

Tout reste sur la machine (CLAUDE.md, règle 5) : stockage SQLite + fichiers dans ``RE2020_DONNEES``
(défaut ``./etudes``), page web sans ressource externe, serveur lié à 127.0.0.1.

Lancer : ``python -m re2020.api`` (ouvre le navigateur sur http://127.0.0.1:8000)
Depuis le téléphone (même wifi) : ``python -m re2020.api --reseau --mot-de-passe XXXX``
Ou double-cliquer ``lancer.bat`` (Windows) / ``lancer.command`` (Mac).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .acv import CatalogueACV
from .catalogues import Catalogue
from .estimation.references import comparer
from .etude import Parametres, realiser_etude
from .formats import ACCEPTES
from .plans.controle import image_controle
from .rapport import generer_html, generer_pdf
from .seuils import ZONES

WEB = Path(__file__).resolve().parent / "web"  # site Next.js compilé (npm run build dans web/)
STRUCTURES = {"parpaing": "Blocs béton", "brique": "Brique", "beton": "Béton banché", "ossature_bois": "Ossature bois"}
PLANCHERS = {"hourdis": "Poutrelles-hourdis", "bois": "Bois"}
MENUISERIES_ACV = {"pvc": "PVC", "alu": "Aluminium"}

SCHEMA = """CREATE TABLE IF NOT EXISTS etudes (id TEXT PRIMARY KEY, cree TEXT, projet TEXT, fichier TEXT,
            parametres TEXT, statut TEXT, erreur TEXT, synthese TEXT)"""


def creer_app(dossier: str | Path | None = None, mot_de_passe: str | None = None) -> FastAPI:
    mot_de_passe = mot_de_passe or os.environ.get("RE2020_MOT_DE_PASSE") or None
    racine = Path(dossier or os.environ.get("RE2020_DONNEES", "etudes")).resolve()
    racine.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(racine / "etudes.sqlite", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute(SCHEMA)
    catalogue = Catalogue()
    app = FastAPI(title="Assistant RE2020 — DEEP-WATT", version="0.2.0",
                  description="Prépare la saisie Pléiades à partir des plans. Estimation, pas un calcul réglementaire.")

    if mot_de_passe:
        @app.middleware("http")
        async def authentification(request: Request, call_next):
            """Mot de passe d'accès (authentification HTTP Basic, identifiant libre)."""
            h = request.headers.get("authorization", "")
            ok = False
            if h.startswith("Basic "):
                try:
                    _, _, mdp = base64.b64decode(h[6:]).decode("utf-8").partition(":")
                    ok = secrets.compare_digest(mdp, mot_de_passe)
                except (ValueError, UnicodeDecodeError):
                    ok = False
            if not ok:
                return Response("Mot de passe requis", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="Assistant RE2020"'})
            return await call_next(request)

    def dossier_etude(i: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", i):
            raise HTTPException(404, "étude inconnue")
        d = racine / i
        if not d.is_dir():
            raise HTTPException(404, "étude inconnue")
        return d

    def liens(i: str) -> dict:
        d = racine / i
        pdf_ok = (d / "feuille_de_route.pdf").exists()
        return {"etude": f"/api/etudes/{i}", "rapport_html": f"/api/etudes/{i}/rapport.html",
                "rapport": f"/api/etudes/{i}/rapport.pdf" if pdf_ok else f"/api/etudes/{i}/rapport.html",
                "pdf_disponible": pdf_ok, "controle": f"/api/etudes/{i}/controle.png"}

    @app.get("/api/config")
    def config():
        return {"zones": ZONES, "systemes": [s["nom"] for s in catalogue.systemes()], "structures": STRUCTURES,
                "planchers": PLANCHERS, "menuiseries": MENUISERIES_ACV}

    cache_refs: dict = {}

    @app.get("/api/references")
    def references():
        if "v" not in cache_refs:
            cache_refs["v"] = comparer(catalogue)
        return cache_refs["v"]

    @app.get("/api/catalogues")
    def catalogues():
        acv = CatalogueACV()
        return {"compositions": [{"nom": c["nom"], "type_paroi": c["type_paroi"], "U": c["U"], "up_pleiades": c["up_pleiades"],
                                  "epaisseur_cm": c["epaisseur_cm"], "couches": c["couches"], "alertes": c.get("alertes", [])}
                                 for c in catalogue.compositions()],
                "isolants": catalogue.isolants(), "menuiseries": catalogue.menuiseries(), "systemes": catalogue.systemes(),
                "fiches_acv": {"lots": acv.lots, "elements": list(acv.elements.values())}}

    @app.delete("/api/etudes/{i}")
    def supprimer(i: str):
        d = dossier_etude(i)
        for f in d.iterdir():
            f.unlink()
        d.rmdir()
        db.execute("DELETE FROM etudes WHERE id=?", (i,))
        db.commit()
        return {"supprime": i}

    def accueil():
        return PAGE.replace("{{ZONES}}", "".join(f"<option>{z}</option>" for z in ZONES)).replace(
            "{{SYSTEMES}}", "".join(f"<option>{s['nom']}</option>" for s in catalogue.systemes()))

    @app.post("/api/etudes")
    async def creer_etude(fichiers: list[UploadFile] = File(default=[]), fichier: UploadFile | None = File(None),
                          zone: str | None = Form(None), altitude_m: float | None = Form(None),
                          date_pc: str | None = Form(None), projet: str = Form("Projet sans nom"), sref: float | None = Form(None),
                          nb_logements: int = Form(1), hsp_m: float | None = Form(None), systeme: str | None = Form(None),
                          mb_hsp: float | None = Form(None), mc_hsp: float | None = Form(None),
                          echelle: int | None = Form(None), angle_nord_deg: float | None = Form(None),
                          structure: str | None = Form(None), plancher: str | None = Form(None), menuiserie: str | None = Form(None)):
        envois = [f for f in ([fichier] if fichier else []) + list(fichiers) if f is not None]
        if not envois:
            raise HTTPException(422, "Ajouter au moins un PDF (plans, notice thermique…).")
        contenus = []
        for f in envois:
            nom = Path(f.filename or "fichier").name
            ext = Path(nom).suffix.lower()
            if ext not in ACCEPTES:
                raise HTTPException(415, f"« {nom} » : format non pris en charge (PDF, DXF, DWG, Word, Excel, texte, images).")
            c = await f.read()
            if ext == ".pdf" and not c.startswith(b"%PDF"):
                raise HTTPException(415, f"« {nom} » n'est pas un vrai PDF.")
            contenus.append((nom, c))
        i = uuid.uuid4().hex[:12]
        d = racine / i
        d.mkdir()
        chemins = []
        for k, (nom, c) in enumerate(contenus):
            sur = re.sub(r"[^\w.\- ]", "_", nom)[:120] or f"fichier_{k + 1}"
            ch = d / f"{k + 1:02d}_{sur}"
            ch.write_bytes(c)
            chemins.append(ch)
        p = Parametres(zone=zone or None, altitude_m=altitude_m, date_pc=date_pc or None, projet=projet, sref=sref or None,
                       nb_logements=nb_logements, hsp_m=hsp_m or None, systeme=systeme or None, mb_hsp=mb_hsp, mc_hsp=mc_hsp,
                       echelle=echelle or None, angle_nord_deg=angle_nord_deg, structure=structure or None,
                       plancher=plancher or None, menuiserie=menuiserie or None)
        noms = " + ".join(n for n, _ in contenus)
        ligne = [i, datetime.now().isoformat(timespec="seconds"), projet, noms, json.dumps(p.__dict__)]
        try:
            e = realiser_etude(chemins, p, catalogue, dossier_travail=d)
        except (ValueError, KeyError) as exc:
            db.execute("INSERT INTO etudes VALUES (?,?,?,?,?,?,?,?)", (*ligne, "erreur", str(exc), None))
            db.commit()
            raise HTTPException(422, f"Dossier non exploitable : {exc}")
        (d / "etude.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "feuille_de_route.html").write_text(generer_html(e), encoding="utf-8")
        try:
            generer_pdf(e, d / "feuille_de_route.pdf")
        except Exception:  # WeasyPrint sans ses bibliothèques système (souvent sous Windows) : HTML imprimable
            pass
        plans = [d / n if (d / n).exists() else next(d.glob(f"*{n}")) for n in e["fichiers"]["plans"]]
        image_controle(plans, e["plan"], d / "controle.png")
        synthese = {"verdict": e["verdict"], "Bbio": e["estimation"]["Bbio"], "Cep": e["estimation"]["Cep"],
                    "Cep_nr": e["estimation"]["Cep_nr"], "seuils": {k: e["seuils"][k]["valeur"] for k in ("Bbio_max", "Cep_max", "Cep_nr_max")},
                    "seuils_approx": e["seuils"]["approx"], "alertes": e["alertes"],
                    "acv": {"Ic_construction_defaut": e["acv"]["Ic_construction"]["par_defaut"],
                            "Ic_construction_top_fiches": e["acv"]["Ic_construction"]["top_fiches"],
                            "Ic_construction_max": e["acv"]["Ic_construction_max"]["valeur"],
                            "Ic_energie": e["acv"]["Ic_energie"], "verdict": e["acv"]["verdict"]},
                    "zone": e["parametres"]["zone"], "sref": e["entrees"]["sref"],
                    "controles": {"ok": sum(c["statut"] == "ok" for c in e["controles"]),
                                  "ecarts": sum(c["statut"] == "écart" for c in e["controles"])}}
        db.execute("INSERT INTO etudes VALUES (?,?,?,?,?,?,?,?)", (*ligne, "ok", None, json.dumps(synthese, ensure_ascii=False)))
        db.commit()
        return {"id": i, **synthese, "liens": liens(i)}

    @app.get("/api/etudes")
    def lister():
        return [{"id": r["id"], "cree": r["cree"], "projet": r["projet"], "fichier": r["fichier"], "statut": r["statut"],
                 "erreur": r["erreur"], "synthese": json.loads(r["synthese"]) if r["synthese"] else None,
                 "liens": liens(r["id"]) if r["statut"] == "ok" else None}
                for r in db.execute("SELECT * FROM etudes ORDER BY cree DESC")]

    @app.get("/api/etudes/{i}")
    def lire(i: str):
        e = json.loads((dossier_etude(i) / "etude.json").read_text(encoding="utf-8"))
        return {**e, "id": i, "liens": liens(i)}

    @app.get("/api/etudes/{i}/rapport.pdf")
    def rapport(i: str):
        if not (dossier_etude(i) / "feuille_de_route.pdf").exists():
            raise HTTPException(404, "PDF indisponible (WeasyPrint) : utiliser rapport.html puis Imprimer → PDF")
        return FileResponse(dossier_etude(i) / "feuille_de_route.pdf", media_type="application/pdf", filename=f"feuille_de_route_{i}.pdf")

    @app.get("/api/etudes/{i}/rapport.html", response_class=HTMLResponse)
    def rapport_html(i: str):
        return (dossier_etude(i) / "feuille_de_route.html").read_text(encoding="utf-8")

    @app.get("/api/etudes/{i}/controle.png")
    def controle(i: str):
        return FileResponse(dossier_etude(i) / "controle.png", media_type="image/png")

    if (WEB / "index.html").exists():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="site")
    else:  # site non compilé : page simple de secours
        app.get("/", response_class=HTMLResponse)(accueil)
    return app


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Assistant RE2020</title><style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#1d1d1d}
h1{color:#0b3d5c;font-size:1.4em} label{display:block;margin:8px 0 2px;font-weight:600}
input,select{width:100%;padding:8px;box-sizing:border-box;border:1px solid #bbb;border-radius:6px}
.l2{display:grid;grid-template-columns:1fr 1fr;gap:12px} button{margin-top:16px;padding:10px 18px;background:#0b3d5c;color:#fff;border:0;border-radius:6px;font-size:1em}
#res{margin-top:20px} .ok{color:#2e7d32}.ko{color:#c62828}.moy{color:#e65100} .note{color:#666;font-size:.9em} li{margin:3px 0}
</style></head><body>
<h1>Assistant RE2020 — feuille de route Pléiades</h1>
<p class="note">Déposez le plan de l'architecte (PDF vectoriel). Tout reste sur ce poste. Estimation pour préparer la saisie : les résultats officiels sont ceux de Pléiades.</p>
<form id="f">
<label>Plan (PDF vectoriel)</label><input type="file" name="fichier" accept=".pdf" required>
<label>Projet</label><input name="projet" placeholder="Nom du projet">
<div class="l2"><div><label>Zone climatique</label><select name="zone">{{ZONES}}</select></div>
<div><label>Altitude (m)</label><input name="altitude_m" type="number" value="200" required></div></div>
<div class="l2"><div><label>Date de dépôt du PC</label><input name="date_pc" type="date" required></div>
<div><label>Sref (m², facultatif)</label><input name="sref" type="number" step="0.1"></div></div>
<div class="l2"><div><label>Système</label><select name="systeme">{{SYSTEMES}}</select></div>
<div><label>HSP (m)</label><input name="hsp_m" type="number" step="0.01" value="2.5"></div></div>
<div class="l2"><div><label>Structure (ACV)</label><select name="structure"><option value="parpaing">Blocs béton</option><option value="brique">Brique</option><option value="beton">Béton banché</option><option value="ossature_bois">Ossature bois</option></select></div>
<div><label>Menuiseries (ACV)</label><select name="menuiserie"><option value="pvc">PVC</option><option value="alu">Aluminium</option></select></div></div>
<button>Lancer l'étude</button></form><div id="res"></div>
<h2>Mes études</h2><ul id="liste" class="note"></ul>
<script>
const f=document.getElementById('f'),res=document.getElementById('res');
const cls={"conforme probable":"ok","non conforme probable":"ko","incertain":"moy"};
const esc=t=>String(t??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function lister(){const r=await fetch('/api/etudes');if(!r.ok)return;const l=await r.json();
 document.getElementById('liste').innerHTML=l.map(e=>e.statut==='ok'?`<li>${e.cree.replace('T',' ')} — ${esc(e.projet)} : <a href="/api/etudes/${e.id}/rapport.html" target="_blank">feuille de route</a> · <a href="/api/etudes/${e.id}/controle.png" target="_blank">contrôle</a></li>`:`<li>${e.cree.replace('T',' ')} — ${esc(e.projet)} : erreur (${esc(e.erreur)})</li>`).join('')||'<li>Aucune étude pour l’instant.</li>';}
lister();
f.onsubmit=async ev=>{ev.preventDefault();res.textContent='Analyse en cours…';
 const fd=new FormData(f);for(const k of ['sref']) if(!fd.get(k)) fd.delete(k);
 const r=await fetch('/api/etudes',{method:'POST',body:fd});const j=await r.json();
 if(!r.ok){res.innerHTML='<p class="ko">'+(j.detail||'Erreur')+'</p>';return;}
 const ind=['Bbio','Cep','Cep_nr'].map(k=>`<li>${k} : <b>${j[k].valeur}</b> [${j[k].fourchette.join(' – ')}] / max ${j.seuils[k+'_max']} → <span class="${cls[j.verdict[k]]}">${j.verdict[k]}</span></li>`).join('');
 res.innerHTML=`<h2>Résultat</h2><ul>${ind}</ul>${j.seuils_approx?'<p class="moy">Seuils « approx » (MbHSP/McHSP inconnus).</p>':''}
 <p><a href="${j.liens.rapport}">Feuille de route (PDF)</a> · <a href="${j.liens.rapport_html}" target="_blank">version web</a> · <a href="${j.liens.controle}" target="_blank">Image de contrôle</a> · <a href="${j.liens.etude}" target="_blank">JSON</a></p>
 <p>Ic construction (DED) : <b>${j.acv.Ic_construction_defaut.valeur}</b> → avec FDES prioritaires ${j.acv.Ic_construction_top_fiches.valeur} / max ${j.acv.Ic_construction_max} — Ic énergie ${j.acv.Ic_energie.valeur}</p>
 <h3>Alertes</h3><ul>${j.alertes.map(a=>'<li>'+a.replace(/</g,'&lt;')+'</li>').join('')}</ul>`;lister();};
</script></body></html>"""


def _ip_locale() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
            so.connect(("10.255.255.255", 1))  # aucune donnée envoyée : sert seulement à choisir l'interface
            return so.getsockname()[0]
    except OSError:
        return "adresse-de-ce-pc"


def main(argv=None):
    import uvicorn

    ap = argparse.ArgumentParser(description="Assistant RE2020 — serveur local")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--reseau", action="store_true", help="accessible depuis le téléphone / le réseau local (mot de passe obligatoire)")
    ap.add_argument("--mot-de-passe", default=os.environ.get("RE2020_MOT_DE_PASSE"))
    ap.add_argument("--sans-navigateur", action="store_true")
    a = ap.parse_args(argv)
    if a.reseau and not a.mot_de_passe:
        ap.error("--reseau exige --mot-de-passe (les plans clients ne doivent pas être accessibles sans protection)")
    hote = "0.0.0.0" if a.reseau else "127.0.0.1"
    url = f"http://127.0.0.1:{a.port}"
    print(f"\n  Assistant RE2020 prêt : {url}")
    if a.reseau:
        print(f"  Depuis le téléphone (même wifi) : http://{_ip_locale()}:{a.port}  (mot de passe demandé)")
    print("  Fermer cette fenêtre pour arrêter.\n")
    if not a.sans_navigateur:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(creer_app(mot_de_passe=a.mot_de_passe), host=hote, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
