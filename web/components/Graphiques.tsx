"use client";

import { useState } from "react";
import type { Valeur } from "@/lib/api";
import { nombre } from "@/lib/format";
import { Verdict } from "./Valeurs";

/** Indicateur contre seuil : valeur (point), fourchette (bande), seuil (trait). */
export function Jauge({ titre, v, seuil, unite, verdict, note }: {
  titre: string; v: Valeur; seuil: number; unite: string; verdict: string; note?: string;
}) {
  const [b, h] = v.fourchette ?? [v.valeur, v.valeur];
  const max = Math.max(seuil * 1.25, h * 1.08, 1);
  const pct = (x: number) => `${Math.min(100, Math.max(0, (x / max) * 100))}%`;
  return (
    <div className="carte indicateur">
      <div className="indicateur-tete">
        <span>{titre}</span>
        <Verdict v={verdict} />
      </div>
      <div className="indicateur-valeur">
        {nombre(v.valeur, 1)}
        <small>{unite}</small>
      </div>
      <div className="jauge" role="img"
        aria-label={`${titre} estimé ${nombre(v.valeur, 1)}, fourchette ${nombre(b, 1)} à ${nombre(h, 1)}, seuil ${nombre(seuil, 1)} ${unite}`}>
        <div className="jauge-piste" />
        <div className="jauge-bande" style={{ left: pct(b), width: `calc(${pct(h)} - ${pct(b)})` }} />
        <div className="jauge-seuil" style={{ left: pct(seuil) }} title={`Seuil ${nombre(seuil, 1)}`} />
        <div className="jauge-point" style={{ left: pct(v.valeur) }} title={`Estimation ${nombre(v.valeur, 1)}`} />
      </div>
      <div className="jauge-legende">
        <span>Fourchette {nombre(b, 0)}–{nombre(h, 0)}</span>
        <span>Seuil {nombre(seuil, 1)}</span>
      </div>
      {note ? <div className="muet" style={{ fontSize: 12 }}>{note}</div> : null}
    </div>
  );
}

type Survol = { x: number; y: number; texte: string } | null;

/** Barres horizontales triées, une seule série (une teinte), valeur en bout de barre + infobulle. */
export function BarresH({ donnees, unite, decimales = 1 }: {
  donnees: { nom: string; valeur: number; detail?: string }[]; unite: string; decimales?: number;
}) {
  const [survol, setSurvol] = useState<Survol>(null);
  const max = Math.max(...donnees.map((d) => d.valeur), 1);
  return (
    <div className="barres" style={{ position: "relative" }} onMouseLeave={() => setSurvol(null)}>
      {donnees.map((d) => (
        <div className="barre-ligne" key={d.nom}>
          <span className="nom" title={d.nom}>{d.nom}</span>
          <div className="barre-zone"
            onMouseMove={(e) => {
              const r = (e.currentTarget.parentElement?.parentElement as HTMLElement).getBoundingClientRect();
              setSurvol({ x: e.clientX - r.left, y: e.clientY - r.top, texte: `${d.nom} : ${nombre(d.valeur, decimales)} ${unite}${d.detail ? ` · ${d.detail}` : ""}` });
            }}>
            <div className="barre-remplie" style={{ width: `${(d.valeur / max) * 100}%` }} />
          </div>
          <span className="val">{nombre(d.valeur, decimales)}</span>
        </div>
      ))}
      {survol ? <div className="infobulle" style={{ left: survol.x, top: survol.y }}>{survol.texte}</div> : null}
    </div>
  );
}

/** Deux séries par ligne (ex. ACV : fiches par défaut / fiches spécifiques), légende + valeurs + infobulle. */
export function BarresPaires({ donnees, series, unite }: {
  donnees: { nom: string; a: number; b: number }[]; series: [string, string]; unite: string;
}) {
  const [survol, setSurvol] = useState<Survol>(null);
  const max = Math.max(...donnees.map((d) => Math.max(d.a, d.b)), 1);
  return (
    <div>
      <div className="legende">
        <span><i style={{ background: "var(--serie-1)" }} />{series[0]}</span>
        <span><i style={{ background: "var(--serie-2)" }} />{series[1]}</span>
      </div>
      <div className="barres paire" style={{ position: "relative" }} onMouseLeave={() => setSurvol(null)}>
        {donnees.map((d) => (
          <div className="barre-ligne" key={d.nom}>
            <span className="nom" title={d.nom}>{d.nom}</span>
            <div className="barre-zone"
              onMouseMove={(e) => {
                const r = (e.currentTarget.parentElement?.parentElement as HTMLElement).getBoundingClientRect();
                setSurvol({ x: e.clientX - r.left, y: e.clientY - r.top,
                  texte: `${d.nom} : ${series[0].toLowerCase()} ${nombre(d.a, 1)} · ${series[1].toLowerCase()} ${nombre(d.b, 1)} ${unite}` });
              }}>
              <div className="barre-remplie s1" style={{ width: `${(d.a / max) * 100}%` }} />
              <div className="barre-remplie s2" style={{ width: `${(d.b / max) * 100}%` }} />
            </div>
            <span className="val">{nombre(d.a, 0)} / {nombre(d.b, 0)}</span>
          </div>
        ))}
        {survol ? <div className="infobulle" style={{ left: survol.x, top: survol.y }}>{survol.texte}</div> : null}
      </div>
    </div>
  );
}
