"use client";

import { AlertCircle, ChevronRight, FileUp, Loader2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type Config } from "@/lib/api";

const FORMATS = ["pdf", "dxf", "dwg", "docx", "odt", "ods", "xlsx", "xlsm", "txt", "csv", "png", "jpg", "jpeg", "tif", "tiff"];

export default function NouvelleEtude() {
  const router = useRouter();
  const [config, setConfig] = useState<Config | null>(null);
  const [fichiers, setFichiers] = useState<File[]>([]);
  const [survol, setSurvol] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [lieuASaisir, setLieuASaisir] = useState(false);
  const champCommune = useRef<HTMLInputElement>(null);
  const entreeFichier = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setErreur(e.message));
  }, []);

  function choisir(liste: FileList | null | undefined) {
    setErreur(null);
    if (!liste?.length) return;
    const ajout: File[] = [];
    for (const f of Array.from(liste)) {
      const ext = f.name.toLowerCase().split(".").pop() ?? "";
      if (!FORMATS.includes(ext)) return setErreur(`« ${f.name} » : format non pris en charge (${FORMATS.join(", ")})`);
      ajout.push(f);
    }
    setFichiers((avant) => [...avant, ...ajout.filter((f) => !avant.some((a) => a.name === f.name && a.size === f.size))]);
  }

  async function envoyer(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    if (!fichiers.length) return setErreur("Ajouter au moins un plan (PDF, DXF ou DWG), et si possible la notice thermique");
    const fd = new FormData(ev.currentTarget);
    for (const [k, v] of Array.from(fd.entries())) if (v === "") fd.delete(k);
    fd.delete("fichiers");
    for (const f of fichiers) fd.append("fichiers", f);
    setEnvoi(true);
    setErreur(null);
    try {
      const r = await api.creer(fd);
      router.push(`/etude/?id=${r.id}`);
    } catch (e: any) {
      setErreur(e.message);
      setEnvoi(false);
      if (e.code === "zone_a_saisir") {
        setLieuASaisir(true);
        setTimeout(() => { champCommune.current?.scrollIntoView({ behavior: "smooth", block: "center" }); champCommune.current?.focus(); }, 50);
      }
    }
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="entete">
        <div>
          <h1>Nouvelle étude</h1>
          <p>Les documents sont lus sur ce poste. Comptez quelques secondes pour la lecture et les calculs</p>
        </div>
      </div>

      <form onSubmit={envoyer} className="pile">
        <section className="carte carte-corps pile" style={{ gap: 16 }}>
          <h2>Dossier du projet</h2>
          <p className="second" style={{ marginTop: -8 }}>Plans (PDF, DXF, DWG), coupe, notice thermique (PDF, Word, Excel) : tout est lu. Plus le dossier est complet, plus le résultat est précis</p>
          {fichiers.map((f) => (
            <div className="depot rempli" key={f.name + f.size}>
              <div>
                <div>{f.name}</div>
                <div className="muet mono">{(f.size / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 0 })} Ko</div>
              </div>
              <button type="button" className="bouton discret" onClick={() => setFichiers(fichiers.filter((x) => x !== f))} aria-label={`Retirer ${f.name}`}><X strokeWidth={1.5} /></button>
            </div>
          ))}
          <div className={`depot${survol ? " survol" : ""}`} role="button" tabIndex={0}
            onClick={() => entreeFichier.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && entreeFichier.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setSurvol(true); }}
            onDragLeave={() => setSurvol(false)}
            onDrop={(e) => { e.preventDefault(); setSurvol(false); choisir(e.dataTransfer.files); }}>
            <FileUp strokeWidth={1.5} />
            <strong>{fichiers.length ? "Ajouter d'autres fichiers" : "Déposer les fichiers du dossier ici"}</strong>
            <span className="muet">ou cliquer pour les choisir · PDF, DXF, DWG, Word, LibreOffice, Excel · un ou plusieurs fichiers</span>
          </div>
          <input ref={entreeFichier} type="file" accept=".pdf,.dxf,.dwg,.docx,.odt,.ods,.xlsx,.xlsm,.txt,.csv,.png,.jpg,.jpeg,.tif,.tiff" multiple hidden onChange={(e) => { choisir(e.target.files); e.target.value = ""; }} />
        </section>

        <section className="carte carte-corps pile" style={{ gap: 16 }}>
          <h2>Projet</h2>
          <div className="grille-champs">
            <div className="champ" style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="projet">Nom du projet</label>
              <input id="projet" name="projet" className="entree" placeholder="Maison Dupont, lot 3" />
            </div>
            <div className="champ" style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="commune">Adresse ou commune du chantier</label>
              <input id="commune" name="commune" ref={champCommune} className="entree" placeholder="ex. 3 chemin du Haut du Theux, 08000 Charleville-Mézières (lu dans le dossier si vide)"
                style={lieuASaisir ? { borderColor: "var(--critique)", boxShadow: "0 0 0 3px rgba(192,48,47,0.15)" } : undefined}
                onChange={() => setLieuASaisir(false)} />
              <span className="aide">Sert à déduire la zone climatique et l'altitude. Seuls la commune et le code postal sont envoyés aux services publics (BAN, IGN), jamais l'adresse complète</span>
            </div>
            <div className="champ">
              <label htmlFor="zone">Zone climatique</label>
              <select id="zone" name="zone" className="entree" defaultValue="">
                <option value="">Lue ou déduite du lieu du projet</option>
                {(config?.zones ?? []).map((z) => <option key={z}>{z}</option>)}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="altitude_m">Altitude (m)</label>
              <input id="altitude_m" name="altitude_m" type="number" min={0} max={3000} className="entree" placeholder="Lue, ou cherchée d'après la commune" />
            </div>
            <div className="champ">
              <label htmlFor="date_pc">Date de dépôt du permis</label>
              <input id="date_pc" name="date_pc" type="date" className="entree" />
              <span className="aide">Lue dans la notice si vide. Fixe les seuils (décret 2026-200 à partir du 1er juillet 2026)</span>
            </div>
            <div className="champ">
              <label htmlFor="sref">Sref (m²)</label>
              <input id="sref" name="sref" type="number" step="0.1" min={10} className="entree" placeholder="Lue dans le dossier si vide" />
            </div>
            <div className="champ">
              <label htmlFor="systeme">Système de chauffage et ECS</label>
              <select id="systeme" name="systeme" className="entree" defaultValue="">
                <option value="">Lu dans la notice</option>
                {(config?.systemes ?? []).map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="hsp_m">Hauteur sous plafond (m)</label>
              <input id="hsp_m" name="hsp_m" type="number" step="0.01" className="entree" placeholder="Lue sur la coupe si vide" />
              <span className="aide">Sinon 2,50 m supposé</span>
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
                <select id="structure" name="structure" className="entree" defaultValue="">
                  <option value="">Lu dans la notice</option>
                  {Object.entries(config?.structures ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="champ">
                <label htmlFor="plancher">Plancher intermédiaire (ACV)</label>
                <select id="plancher" name="plancher" className="entree" defaultValue="">
                  <option value="">Lu dans la notice</option>
                  {Object.entries(config?.planchers ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="champ">
                <label htmlFor="menuiserie">Menuiseries (ACV)</label>
                <select id="menuiserie" name="menuiserie" className="entree" defaultValue="">
                  <option value="">Lu dans la notice</option>
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

        {erreur ? (
          <div className="message erreur"><AlertCircle strokeWidth={1.5} />
            <div>
              {lieuASaisir ? <strong style={{ display: "block", marginBottom: 4 }}>Il manque le lieu du chantier : tapez l'adresse, la commune ou le code postal ci-dessus (vos fichiers sont gardés), puis relancez.</strong> : null}
              {erreur}
            </div>
          </div>
        ) : null}
        {envoi ? <div className="message info"><Loader2 strokeWidth={1.5} />Lecture du dossier, estimation et ACV en cours</div> : null}

        <div style={{ display: "flex", gap: 8 }}>
          <button className="bouton principal" type="submit" disabled={envoi}>Lancer l'étude</button>
          <button className="bouton discret" type="button" onClick={() => router.push("/")}>Annuler</button>
        </div>
      </form>
    </div>
  );
}
