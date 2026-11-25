"use client";

import { useEffect, useState } from "react";
import { api, type LigneReference } from "@/lib/api";
import { nombre } from "@/lib/format";

/** Pour chaque cas : fourchette estimée (bande), estimation (point plein), résultats Pléiades (losanges). */
function Comparaison({ lignes }: { lignes: LigneReference[] }) {
  const valeurs = lignes.flatMap((l) => [...l.Bbio_pleiades, ...(l.fourchette ?? [])]);
  const max = Math.ceil(Math.max(...valeurs, 1) / 20) * 20;
  const pct = (x: number) => `${(x / max) * 100}%`;
  const graduations = Array.from({ length: max / 20 + 1 }, (_, i) => i * 20);
  return (
    <div>
      <div className="legende">
        <span><i style={{ background: "var(--accent-doux)", height: 8 }} />Fourchette estimée</span>
        <span><i style={{ background: "var(--accent)", width: 8, height: 8, borderRadius: 4 }} />Estimation</span>
        <span><i style={{ background: "var(--texte)", width: 8, height: 8, transform: "rotate(45deg)", borderRadius: 1 }} />Résultat Pléiades</span>
      </div>
      <div className="barres">
        {lignes.map((l) => (
          <div className="barre-ligne" key={l.cas} style={{ gridTemplateColumns: "minmax(120px, 260px) minmax(0, 1fr) 64px" }}>
            <span className="nom" title={l.cas}>{l.cas}</span>
            <div className="barre-zone" style={{ height: 24 }}>
              {graduations.map((g) => (
                <div key={g} style={{ position: "absolute", left: pct(g), top: 0, bottom: 0, width: 1, background: "var(--grille)" }} />
              ))}
              {l.fourchette ? (
                <div style={{ position: "absolute", top: 7, height: 10, borderRadius: 5, background: "var(--accent-doux)", left: pct(l.fourchette[0]), width: `calc(${pct(l.fourchette[1])} - ${pct(l.fourchette[0])})` }} />
              ) : null}
              {l.Bbio_pleiades.map((b, i) => (
                <div key={i} title={`Pléiades ${nombre(b, 1)}`} style={{ position: "absolute", top: 8, left: pct(b), width: 8, height: 8, marginLeft: -4, background: "var(--texte)", transform: "rotate(45deg)", borderRadius: 1, boxShadow: "0 0 0 2px var(--surface)" }} />
              ))}
              {l.Bbio_estime !== null ? (
                <div title={`Estimation ${nombre(l.Bbio_estime, 1)}`} style={{ position: "absolute", top: 6, left: pct(l.Bbio_estime), width: 12, height: 12, marginLeft: -6, borderRadius: 6, background: "var(--accent)", boxShadow: "0 0 0 2px var(--surface)" }} />
              ) : null}
            </div>
            <span className="val">{l.ecart_Bbio !== undefined ? `${l.ecart_Bbio > 0 ? "+" : ""}${nombre(l.ecart_Bbio, 1)}` : "—"}</span>
          </div>
        ))}
        <div className="barre-ligne" style={{ gridTemplateColumns: "minmax(120px, 260px) minmax(0, 1fr) 64px" }}>
          <span />
          <div style={{ position: "relative", height: 16 }}>
            {graduations.map((g) => (
              <span key={g} className="muet chiffres" style={{ position: "absolute", left: pct(g), transform: "translateX(-50%)", fontSize: 12 }}>{g}</span>
            ))}
          </div>
          <span className="muet" style={{ fontSize: 12, textAlign: "right" }}>écart</span>
        </div>
      </div>
    </div>
  );
}

export default function Modele() {
  const [lignes, setLignes] = useState<LigneReference[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => { api.references().then(setLignes).catch((e) => setErreur(e.message)); }, []);

  return (
    <>
      <div className="entete">
        <div>
          <h1>Fiabilité du modèle</h1>
          <p>Bbio estimé par l'outil comparé aux résultats Pléiades des projets de référence. L'écart est affiché, pas corrigé à la main</p>
        </div>
      </div>
      {erreur ? <div className="message erreur">{erreur}</div> : null}
      {!lignes && !erreur ? <div className="chargement">Calcul des cas de référence</div> : null}
      {lignes ? (
        <div className="pile">
          <div className="carte carte-corps">
            <h3>Bbio, points</h3>
            <p className="muet" style={{ fontSize: 13, margin: "2px 0 16px" }}>Objectif : écart de ± 5 points. Plusieurs losanges = plusieurs variantes Pléiades du même projet</p>
            <Comparaison lignes={lignes.filter((l) => l.Bbio_estime !== null)} />
          </div>
          <div className="carte tableau-conteneur">
            <table>
              <thead><tr><th>Cas</th><th className="n">Bbio Pléiades</th><th className="n">Bbio estimé</th><th className="n">Fourchette</th><th className="n">Écart</th><th className="n">Cep Pléiades</th><th className="n">Cep estimé</th><th>Remarque</th></tr></thead>
              <tbody>
                {lignes.map((l) => (
                  <tr key={l.cas}>
                    <td>{l.cas}</td>
                    <td className="n">{l.Bbio_pleiades.map((b) => nombre(b, 1)).join(" / ")}</td>
                    <td className="n">{nombre(l.Bbio_estime, 1)}</td>
                    <td className="n">{l.fourchette ? `${nombre(l.fourchette[0], 0)}–${nombre(l.fourchette[1], 0)}` : "—"}</td>
                    <td className="n">{l.ecart_Bbio !== undefined ? `${l.ecart_Bbio > 0 ? "+" : ""}${nombre(l.ecart_Bbio, 1)}` : "—"}</td>
                    <td className="n">{l.Cep_pleiades.map((c) => nombre(c, 1)).join(" / ")}</td>
                    <td className="n">{nombre(l.Cep_estime, 1)}</td>
                    <td className="second" style={{ fontSize: 13 }}>{l.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muet" style={{ fontSize: 13, maxWidth: 760 }}>
            Pour resserrer l'écart, ajouter les plans PDF et les RSET des projets sans plan : chaque nouveau cas complet sert au calage.
          </p>
        </div>
      ) : null}
    </>
  );
}
