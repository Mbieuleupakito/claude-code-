"use client";

import { useEffect, useState } from "react";
import { Pastille, V } from "@/components/Valeurs";
import { api } from "@/lib/api";
import { euros, libelle, nombre } from "@/lib/format";

const ONGLETS = [
  ["compositions", "Compositions"], ["isolants", "Isolants"], ["menuiseries", "Menuiseries"],
  ["systemes", "Systèmes"], ["acv", "Fiches ACV"],
] as const;

export default function Catalogues() {
  const [c, setC] = useState<any>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [onglet, setOnglet] = useState<(typeof ONGLETS)[number][0]>("compositions");
  useEffect(() => { api.catalogues().then(setC).catch((e) => setErreur(e.message)); }, []);

  return (
    <>
      <div className="entete">
        <div>
          <h1>Catalogues</h1>
          <p>Données utilisées pour les calculs, chargées depuis le dossier data/catalogues</p>
        </div>
      </div>
      <nav className="sommaire" role="tablist" aria-label="Catalogues">
        {ONGLETS.map(([k, nom]) => (
          <a key={k} role="tab" aria-selected={onglet === k} href={`#${k}`}
            onClick={(e) => { e.preventDefault(); setOnglet(k); }}
            style={onglet === k ? { background: "var(--surface-2)", color: "var(--texte)" } : undefined}>{nom}</a>
        ))}
      </nav>
      {erreur ? <div className="message erreur">{erreur}</div> : null}
      {!c && !erreur ? <div className="chargement">Chargement</div> : null}

      {c && onglet === "compositions" ? (
        <div className="carte tableau-conteneur">
          <table>
            <thead><tr><th>Composition</th><th>Type</th><th>Couches</th><th className="n">U calculé</th><th className="n">Up Pléiades</th><th className="n">Écart</th></tr></thead>
            <tbody>
              {c.compositions.map((x: any) => (
                <tr key={x.nom}>
                  <td>{x.nom}{x.alertes?.length ? <div style={{ fontSize: 12, color: "var(--attention)" }}>{x.alertes[0]}</div> : null}</td>
                  <td className="second">{libelle(x.type_paroi)}</td>
                  <td className="second" style={{ fontSize: 13 }}>{x.couches.map(([m, e]: [string, number]) => `${m} ${nombre(e, 1)} cm`).join(" · ")}</td>
                  <td className="n"><V v={x.U} decimales={3} /></td>
                  <td className="n">{nombre(x.up_pleiades, 3)}</td>
                  <td className="n">{x.U.valeur && x.up_pleiades ? `${nombre(((x.U.valeur - x.up_pleiades) / x.up_pleiades) * 100, 1)} %` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {c && onglet === "isolants" ? (
        <div className="carte tableau-conteneur">
          <table>
            <thead><tr><th>Isolant</th><th className="n">λ (W/m.K)</th><th>Certifié</th><th>Usages</th><th className="n">Prix indicatif</th></tr></thead>
            <tbody>
              {c.isolants.map((x: any) => (
                <tr key={x.nom}>
                  <td>{x.nom}</td>
                  <td className="n">{nombre(x.lambda_W_mK, 3)}</td>
                  <td>{x.certifie ? "Oui" : <span style={{ color: "var(--attention)" }}>Non : λ majoré de 15 %</span>}</td>
                  <td className="second">{x.usages.map(libelle).join(", ")}</td>
                  <td className="n"><span className="valeur">{x.prix_eur_m2_cm != null ? `${nombre(x.prix_eur_m2_cm, 2)} €/m²/cm` : "—"}<Pastille tag="supposé" source="prix indicatif à remplacer" /></span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {c && onglet === "menuiseries" ? (
        <div className="carte tableau-conteneur">
          <table>
            <thead><tr><th>Menuiserie</th><th className="n">Uw</th><th className="n">Sw</th><th className="n">Prix indicatif</th></tr></thead>
            <tbody>
              {c.menuiseries.map((x: any) => (
                <tr key={x.nom}><td>{x.nom}</td><td className="n">{nombre(x.Uw, 2)}</td><td className="n">{nombre(x.Sw, 2)}</td>
                  <td className="n"><span className="valeur">{euros(x.prix_eur_m2)}/m²<Pastille tag="supposé" source="prix indicatif à remplacer" /></span></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {c && onglet === "systemes" ? (
        <div className="carte tableau-conteneur">
          <table>
            <thead><tr><th>Système</th><th>Énergie</th><th className="n">Rendement chauffage</th><th className="n">Rendement ECS</th><th className="n">Prix indicatif</th></tr></thead>
            <tbody>
              {c.systemes.map((x: any) => (
                <tr key={x.nom}>
                  <td>{x.nom}{x.source_rendements ? <div className="muet" style={{ fontSize: 12 }}>{x.source_rendements}</div> : null}</td>
                  <td className="second">{libelle(x.energie)}</td>
                  <td className="n">{nombre(x.rendement_chauffage, 2)}</td><td className="n">{nombre(x.rendement_ecs, 2)}</td>
                  <td className="n"><span className="valeur">{euros(x.prix_eur)}<Pastille tag="supposé" source="prix indicatif à remplacer" /></span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {c && onglet === "acv" ? (
        <div className="pile" style={{ gap: 12 }}>
          <div className="message info">Ordres de grandeur supposés tant que les fiches INIES réelles ne sont pas importées (modèle : data/catalogues/fiches_acv_modele.csv)</div>
          <div className="carte tableau-conteneur">
            <table>
              <thead><tr><th>Lot</th><th>Élément</th><th>UF</th><th className="n">Par défaut</th><th className="n">Spécifique</th><th>Fiche à chercher</th></tr></thead>
              <tbody>
                {c.fiches_acv.elements.map((x: any) => (
                  <tr key={x.id}>
                    <td className="rang">{x.lot}</td><td>{x.libelle}</td><td className="second">{x.uf}</td>
                    <td className="n"><span className="valeur">{x.defaut.type} {nombre(x.defaut.ic, 1)}<Pastille tag={x.defaut.tag} source={x.defaut.source} /></span></td>
                    <td className="n">{x.specifique ? <span className="valeur">{nombre(x.specifique.ic, 1)}<Pastille tag={x.specifique.tag} source={x.specifique.source} /></span> : "—"}</td>
                    <td className="second" style={{ fontSize: 13 }}>{x.specifique ? `${x.specifique.type} « ${x.specifique.nom} »` : "forfait"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}
