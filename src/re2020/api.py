"""API FastAPI locale : déposer un plan PDF, récupérer le JSON de l'étude et le PDF « feuille de route ».

Tout reste sur la machine (CLAUDE.md, règle 5) : stockage SQLite + fichiers dans ``RE2020_DONNEES``
(défaut ``./etudes``), page web sans ressource externe, serveur lié à 127.0.0.1.

Lancer : ``python -m re2020.api``  puis ouvrir http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .catalogues import Catalogue
from .etude import Parametres, realiser_etude
from .plans.controle import image_controle
from .rapport import generer_pdf
from .seuils import ZONES

SCHEMA = """CREATE TABLE IF NOT EXISTS etudes (id TEXT PRIMARY KEY, cree TEXT, projet TEXT, fichier TEXT,
            parametres TEXT, statut TEXT, erreur TEXT, synthese TEXT)"""


def creer_app(dossier: str | Path | None = None) -> FastAPI:
    racine = Path(dossier or os.environ.get("RE2020_DONNEES", "etudes")).resolve()
    racine.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(racine / "etudes.sqlite", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute(SCHEMA)
    catalogue = Catalogue()
    app = FastAPI(title="Assistant RE2020 — DEEP-WATT", version="0.2.0",
                  description="Prépare la saisie Pléiades à partir des plans. Estimation, pas un calcul réglementaire.")

    def dossier_etude(i: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", i):
            raise HTTPException(404, "étude inconnue")
        d = racine / i
        if not d.is_dir():
            raise HTTPException(404, "étude inconnue")
        return d

    @app.get("/", response_class=HTMLResponse)
    def accueil():
        return PAGE.replace("{{ZONES}}", "".join(f"<option>{z}</option>" for z in ZONES)).replace(
            "{{SYSTEMES}}", "".join(f"<option>{s['nom']}</option>" for s in catalogue.systemes()))

    @app.post("/api/etudes")
    async def creer_etude(fichier: UploadFile = File(...), zone: str = Form(...), altitude_m: float = Form(...),
                          date_pc: str = Form(...), projet: str = Form("Projet sans nom"), sref: float | None = Form(None),
                          nb_logements: int = Form(1), hsp_m: float = Form(2.5), systeme: str | None = Form(None),
                          mb_hsp: float | None = Form(None), mc_hsp: float | None = Form(None),
                          echelle: int | None = Form(None), angle_nord_deg: float | None = Form(None)):
        nom = (fichier.filename or "plan").lower()
        if nom.endswith(".dwg"):
            raise HTTPException(415, "DWG non lu : fournir un PDF vectoriel (ou un DXF).")
        if nom.endswith(".dxf"):
            raise HTTPException(415, "DXF pas encore pris en charge : fournir un PDF vectoriel.")
        contenu = await fichier.read()
        if not contenu.startswith(b"%PDF"):
            raise HTTPException(415, "Le fichier n'est pas un PDF.")
        i = uuid.uuid4().hex[:12]
        d = racine / i
        d.mkdir()
        (d / "plan.pdf").write_bytes(contenu)
        p = Parametres(zone=zone, altitude_m=altitude_m, date_pc=date_pc, projet=projet, sref=sref or None,
                       nb_logements=nb_logements, hsp_m=hsp_m, systeme=systeme or None, mb_hsp=mb_hsp, mc_hsp=mc_hsp,
                       echelle=echelle or None, angle_nord_deg=angle_nord_deg)
        ligne = [i, datetime.now().isoformat(timespec="seconds"), projet, fichier.filename, json.dumps(p.__dict__)]
        try:
            e = realiser_etude(d / "plan.pdf", p, catalogue)
        except (ValueError, KeyError) as exc:
            db.execute("INSERT INTO etudes VALUES (?,?,?,?,?,?,?,?)", (*ligne, "erreur", str(exc), None))
            db.commit()
            raise HTTPException(422, f"Plan non exploitable : {exc}")
        (d / "etude.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        generer_pdf(e, d / "feuille_de_route.pdf")
        image_controle(d / "plan.pdf", e["plan"], d / "controle.png")
        synthese = {"verdict": e["verdict"], "Bbio": e["estimation"]["Bbio"], "Cep": e["estimation"]["Cep"],
                    "Cep_nr": e["estimation"]["Cep_nr"], "seuils": {k: e["seuils"][k]["valeur"] for k in ("Bbio_max", "Cep_max", "Cep_nr_max")},
                    "seuils_approx": e["seuils"]["approx"], "alertes": e["alertes"]}
        db.execute("INSERT INTO etudes VALUES (?,?,?,?,?,?,?,?)", (*ligne, "ok", None, json.dumps(synthese, ensure_ascii=False)))
        db.commit()
        return {"id": i, **synthese, "liens": {"etude": f"/api/etudes/{i}", "rapport": f"/api/etudes/{i}/rapport.pdf",
                                               "controle": f"/api/etudes/{i}/controle.png"}}

    @app.get("/api/etudes")
    def lister():
        return [{"id": r["id"], "cree": r["cree"], "projet": r["projet"], "fichier": r["fichier"], "statut": r["statut"],
                 "erreur": r["erreur"]} for r in db.execute("SELECT * FROM etudes ORDER BY cree DESC")]

    @app.get("/api/etudes/{i}")
    def lire(i: str):
        return json.loads((dossier_etude(i) / "etude.json").read_text(encoding="utf-8"))

    @app.get("/api/etudes/{i}/rapport.pdf")
    def rapport(i: str):
        return FileResponse(dossier_etude(i) / "feuille_de_route.pdf", media_type="application/pdf", filename=f"feuille_de_route_{i}.pdf")

    @app.get("/api/etudes/{i}/controle.png")
    def controle(i: str):
        return FileResponse(dossier_etude(i) / "controle.png", media_type="image/png")

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
<button>Lancer l'étude</button></form><div id="res"></div>
<script>
const f=document.getElementById('f'),res=document.getElementById('res');
const cls={"conforme probable":"ok","non conforme probable":"ko","incertain":"moy"};
f.onsubmit=async ev=>{ev.preventDefault();res.textContent='Analyse en cours…';
 const fd=new FormData(f);for(const k of ['sref']) if(!fd.get(k)) fd.delete(k);
 const r=await fetch('/api/etudes',{method:'POST',body:fd});const j=await r.json();
 if(!r.ok){res.innerHTML='<p class="ko">'+(j.detail||'Erreur')+'</p>';return;}
 const ind=['Bbio','Cep','Cep_nr'].map(k=>`<li>${k} : <b>${j[k].valeur}</b> [${j[k].fourchette.join(' – ')}] / max ${j.seuils[k+'_max']} → <span class="${cls[j.verdict[k]]}">${j.verdict[k]}</span></li>`).join('');
 res.innerHTML=`<h2>Résultat</h2><ul>${ind}</ul>${j.seuils_approx?'<p class="moy">Seuils « approx » (MbHSP/McHSP inconnus).</p>':''}
 <p><a href="${j.liens.rapport}">Télécharger la feuille de route (PDF)</a> · <a href="${j.liens.controle}" target="_blank">Image de contrôle</a> · <a href="${j.liens.etude}" target="_blank">JSON</a></p>
 <h3>Alertes</h3><ul>${j.alertes.map(a=>'<li>'+a.replace(/</g,'&lt;')+'</li>').join('')}</ul>`;};
</script></body></html>"""


app = None  # créé à la demande (uvicorn re2020.api:creer_app --factory)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(creer_app(), host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
