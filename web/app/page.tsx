"use client";

import { FilePlus2, FileText, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Verdict } from "@/components/Valeurs";
import { api, type EtudeListe } from "@/lib/api";
import { date, heure, nombre } from "@/lib/format";

export default function Etudes() {
  const router = useRouter();
  const [etudes, setEtudes] = useState<EtudeListe[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.etudes().then(setEtudes).catch((e) => setErreur(e.message));
  }, []);

  const filtrees = useMemo(
    () => (etudes ?? []).filter((e) => `${e.projet} ${e.fichier}`.toLowerCase().includes(q.trim().toLowerCase())),
    [etudes, q],
  );

  return (
    <>
      <div className="entete">
        <div>
          <h1>Études</h1>
          <p>Chaque étude part d'un plan PDF et produit la feuille de route à saisir dans Pléiades</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {etudes && etudes.length > 0 ? (
            <div className="recherche">
              <Search strokeWidth={1.5} />
              <input className="entree" placeholder="Rechercher" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Rechercher une étude" />
            </div>
          ) : null}
          <Link className="bouton principal" href="/nouvelle/"><FilePlus2 strokeWidth={1.5} />Nouvelle étude</Link>
        </div>
      </div>

      {erreur ? <div className="message erreur">{erreur}</div> : null}
      {!etudes && !erreur ? <div className="chargement">Chargement</div> : null}

      {etudes && etudes.length === 0 ? (
        <div className="carte vide">
          <FileText strokeWidth={1.5} />
          <h2>Aucune étude pour l’instant</h2>
          <p>Déposez le plan PDF de l'architecte pour obtenir la première feuille de route</p>
          <Link className="bouton principal" href="/nouvelle/">Nouvelle étude</Link>
        </div>
      ) : null}

      {etudes && etudes.length > 0 ? (
        <div className="carte tableau-conteneur">
          <table>
            <thead>
              <tr>
                <th>Projet</th>
                <th className="masque-mobile">Créée le</th>
                <th className="masque-mobile">Zone</th>
                <th className="n masque-mobile">Sref (m²)</th>
                <th className="n">Bbio / max</th>
                <th>Verdict Bbio</th>
                <th className="n masque-mobile">Ic constr. (DED)</th>
              </tr>
            </thead>
            <tbody>
              {filtrees.map((e) => {
                const s = e.synthese;
                const ouvrir = () => e.statut === "ok" && router.push(`/etude/?id=${e.id}`);
                return (
                  <tr key={e.id} className={e.statut === "ok" ? "cliquable" : ""} tabIndex={e.statut === "ok" ? 0 : -1}
                    onClick={ouvrir} onKeyDown={(k) => k.key === "Enter" && ouvrir()}>
                    <td>
                      <div>{e.projet}</div>
                      <div className="mono muet">{e.fichier}</div>
                    </td>
                    <td className="masque-mobile second">{date(e.cree)} <span className="muet">{heure(e.cree)}</span></td>
                    <td className="masque-mobile">{s?.zone ?? "—"}</td>
                    <td className="n masque-mobile">{s?.sref ? nombre(s.sref, 1) : "—"}</td>
                    <td className="n">{s ? <>{nombre(s.Bbio.valeur, 1)} <span className="muet">/ {nombre(s.seuils.Bbio_max, 1)}</span></> : "—"}</td>
                    <td>{e.statut === "ok" && s ? <Verdict v={s.verdict.Bbio} /> : <span className="verdict critique" title={e.erreur ?? ""}>Plan non exploitable</span>}</td>
                    <td className="n masque-mobile">{s?.acv ? <>{nombre(s.acv.Ic_construction_defaut.valeur, 0)} <span className="muet">/ {nombre(s.acv.Ic_construction_max, 0)}</span></> : "—"}</td>
                  </tr>
                );
              })}
              {filtrees.length === 0 ? <tr><td colSpan={7} className="muet">Aucune étude ne correspond à « {q} »</td></tr> : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
