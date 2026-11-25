"use client";

import { AlertCircle, ChevronRight, FileUp, Loader2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type Config } from "@/lib/api";

export default function NouvelleEtude() {
  const router = useRouter();
  const [config, setConfig] = useState<Config | null>(null);
  const [fichier, setFichier] = useState<File | null>(null);
  const [survol, setSurvol] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const entreeFichier = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setErreur(e.message));
  }, []);

  function choisir(f: File | undefined) {
    setErreur(null);
    if (!f) return;
    const nom = f.name.toLowerCase();
    if (nom.endsWith(".dwg")) return setErreur("Les fichiers DWG ne sont pas lus : demander un PDF vectoriel à l'architecte");
    if (!nom.endsWith(".pdf")) return setErreur("Choisir un plan au format PDF vectoriel");
    setFichier(f);
  }

  async function envoyer(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    if (!fichier) return setErreur("Ajouter le plan PDF");
    const fd = new FormData(ev.currentTarget);
    for (const [k, v] of Array.from(fd.entries())) if (v === "") fd.delete(k);
    fd.set("fichier", fichier);
    setEnvoi(true);
    setErreur(null);
    try {
      const r = await api.creer(fd);
      router.push(`/etude/?id=${r.id}`);
    } catch (e: any) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="entete">
        <div>
          <h1>Nouvelle étude</h1>
          <p>Le plan est lu sur ce poste. Comptez quelques secondes pour la lecture et les calculs</p>
        </div>
      </div>

      <form onSubmit={envoyer} className="pile">
        <section className="carte carte-corps pile" style={{ gap: 16 }}>
          <h2>Plan de l'architecte</h2>
          {fichier ? (
            <div className="depot rempli">
              <div>
                <div>{fichier.name}</div>
                <div className="muet mono">{(fichier.size / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 0 })} Ko</div>
              </div>
              <button type="button" className="bouton discret" onClick={() => setFichier(null)} aria-label="Retirer le plan"><X strokeWidth={1.5} /></button>
            </div>
          ) : (
            <div className={`depot${survol ? " survol" : ""}`} role="button" tabIndex={0}
              onClick={() => entreeFichier.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && entreeFichier.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setSurvol(true); }}
              onDragLeave={() => setSurvol(false)}
              onDrop={(e) => { e.preventDefault(); setSurvol(false); choisir(e.dataTransfer.files[0]); }}>
              <FileUp strokeWidth={1.5} />
              <strong>Déposer le plan PDF ici</strong>
              <span className="muet">ou cliquer pour le choisir · PDF vectoriel, plans de niveaux avec étiquettes de baies</span>
            </div>
          )}
          <input ref={entreeFichier} type="file" accept=".pdf,application/pdf" hidden onChange={(e) => choisir(e.target.files?.[0])} />
        </section>

        <section className="carte carte-corps pile" style={{ gap: 16 }}>
          <h2>Projet</h2>
          <div className="grille-champs">
            <div className="champ" style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="projet">Nom du projet</label>
              <input id="projet" name="projet" className="entree" placeholder="Maison Dupont, lot 3" />
            </div>
            <div className="champ">
              <label htmlFor="zone">Zone climatique</label>
              <select id="zone" name="zone" className="entree" defaultValue="H1c" required>
                {(config?.zones ?? ["H1c"]).map((z) => <option key={z}>{z}</option>)}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="altitude_m">Altitude (m)</label>
              <input id="altitude_m" name="altitude_m" type="number" min={0} max={3000} defaultValue={200} className="entree" required />
            </div>
            <div className="champ">
              <label htmlFor="date_pc">Date de dépôt du permis</label>
              <input id="date_pc" name="date_pc" type="date" className="entree" required />
              <span className="aide">Fixe les seuils applicables (décret 2026-200 à partir du 1er juillet 2026)</span>
            </div>
            <div className="champ">
              <label htmlFor="sref">Sref (m²)</label>
              <input id="sref" name="sref" type="number" step="0.1" min={10} className="entree" placeholder="Lue sur le plan si vide" />
            </div>
            <div className="champ">
              <label htmlFor="systeme">Système de chauffage et ECS</label>
              <select id="systeme" name="systeme" className="entree">
                {(config?.systemes ?? []).map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="hsp_m">Hauteur sous plafond (m)</label>
              <input id="hsp_m" name="hsp_m" type="number" step="0.01" defaultValue={2.5} className="entree" />
              <span className="aide">Rarement cotée sur le plan : à lire sur la coupe</span>
            </div>
          </div>

          <details className="avance">
            <summary><ChevronRight strokeWidth={1.5} />Options avancées</summary>
            <div className="grille-champs" style={{ marginTop: 16 }}>
              <div className="champ">
                <label htmlFor="nb_logements">Logements</label>
                <input id="nb_logements" name="nb_logements" type="number" min={1} defaultValue={1} className="entree" />
              </div>
              <div className="champ">
                <label htmlFor="structure">Structure des murs (ACV)</label>
                <select id="structure" name="structure" className="entree">
                  {Object.entries(config?.structures ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="champ">
                <label htmlFor="plancher">Plancher intermédiaire (ACV)</label>
                <select id="plancher" name="plancher" className="entree">
                  {Object.entries(config?.planchers ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="champ">
                <label htmlFor="menuiserie">Menuiseries (ACV)</label>
                <select id="menuiserie" name="menuiserie" className="entree">
                  {Object.entries(config?.menuiseries ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="champ">
                <label htmlFor="mb_hsp">MbHSP</label>
                <input id="mb_hsp" name="mb_hsp" type="number" step="0.001" className="entree" placeholder="Inconnu" />
              </div>
              <div className="champ">
                <label htmlFor="mc_hsp">McHSP</label>
                <input id="mc_hsp" name="mc_hsp" type="number" step="0.001" className="entree" placeholder="Inconnu" />
                <span className="aide">Lus dans Pléiades : rendent les seuils exacts</span>
              </div>
              <div className="champ">
                <label htmlFor="echelle">Échelle forcée (1:N)</label>
                <input id="echelle" name="echelle" type="number" min={1} className="entree" placeholder="Lue et vérifiée sur le plan" />
              </div>
              <div className="champ">
                <label htmlFor="angle_nord_deg">Nord forcé (°)</label>
                <input id="angle_nord_deg" name="angle_nord_deg" type="number" step="0.1" className="entree" placeholder="Lu sur le symbole du nord" />
                <span className="aide">Angle depuis le haut de la feuille, positif vers la droite</span>
              </div>
            </div>
          </details>
        </section>

        {erreur ? <div className="message erreur"><AlertCircle strokeWidth={1.5} />{erreur}</div> : null}
        {envoi ? <div className="message info"><Loader2 strokeWidth={1.5} />Lecture du plan, estimation et ACV en cours</div> : null}

        <div style={{ display: "flex", gap: 8 }}>
          <button className="bouton principal" type="submit" disabled={envoi}>Lancer l'étude</button>
          <button className="bouton discret" type="button" onClick={() => router.push("/")}>Annuler</button>
        </div>
      </form>
    </div>
  );
}
