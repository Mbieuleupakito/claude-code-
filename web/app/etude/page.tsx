"use client";

import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, Download, FileJson, Printer, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { BarresH, BarresPaires, Jauge } from "@/components/Graphiques";
import { LegendeProvenance, Pastille, V, Verdict } from "@/components/Valeurs";
import { api, suppositions, type Etude, type Valeur } from "@/lib/api";
import { date, euros, libelle, nombre } from "@/lib/format";

const NOMS_HYPOTHESES: Record<string, string> = {
  hauteur_sous_plafond_m: "Hauteur sous plafond", plancher_haut_m2: "Surface du plancher haut",
  plancher_haut_mur_ml: "Linéaire plancher haut / mur", U_murs: "U des murs", U_toiture: "U de la toiture",
  U_plancher_bas: "U du plancher bas", Uw: "Uw des menuiseries", Sw: "Sw des menuiseries", q4: "Perméabilité Q4Pa-surf",
  systeme: "Système", structure: "Structure des murs (ACV)", plancher_intermediaire: "Plancher intermédiaire (ACV)",
  menuiseries: "Menuiseries (ACV)", menuiseries_retour_isolant: "Retour d'isolant en tableau", isolation: "Isolation",
};

function nomHypothese(chemin: string): string {
  const morceaux = chemin.split(" › ");
  const cle = morceaux[morceaux.length - 1];
  const niveau = chemin.match(/niveaux (\d+)/);
  const base = NOMS_HYPOTHESES[cle] ?? libelle(cle);
  return niveau ? `${base} · niveau ${niveau[1]}` : base;
}

const POSTES: Record<string, string> = {
  permeabilite: "Perméabilité", ponts_thermiques: "Ponts thermiques", baies: "Baies", murs: "Murs",
  ventilation: "Ventilation", plancher_bas: "Plancher bas", toiture: "Toiture",
};

const SECTIONS = [
  ["synthese", "Synthèse"], ["dossier", "Dossier lu"], ["plan", "Plan lu"], ["enveloppe", "Enveloppe"], ["ponts", "Ponts thermiques"],
  ["propositions", "Propositions"], ["acv", "ACV"], ["hypotheses", "À valider"],
] as const;

export default function Page() {
  return <Suspense fallback={<div className="chargement">Chargement</div>}><FicheEtude /></Suspense>;
}

function FicheEtude() {
  const id = useSearchParams().get("id") ?? "";
  const router = useRouter();
  const [e, setE] = useState<Etude | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return setErreur("Étude non précisée");
    api.etude(id).then(setE).catch((x) => setErreur(x.message));
  }, [id]);

  async function supprimer() {
    if (!e || !confirm(`Supprimer l'étude « ${e.projet} » et ses fichiers ?`)) return;
    await api.supprimer(e.id);
    router.push("/");
  }

  if (erreur) return <div className="message erreur">{erreur}</div>;
  if (!e) return <div className="chargement">Chargement</div>;

  const p = e.parametres;
  const s = e.seuils;
  const bat = e.plan.batiment;
  const acv = e.acv;

  return (
    <>
      <div className="entete">
        <div>
          <Link href="/" className="second" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 8 }}>
            <ArrowLeft size={16} strokeWidth={1.5} />Études
          </Link>
          <h1>{e.projet}</h1>
          <p className="chiffres">
            {String(p.zone)} · {nombre(Number(p.altitude_m), 0)} m · permis déposé le {date(String(p.date_pc))} · Sref {nombre(e.entrees.sref, 1)} m² · <span className="mono">{e.plan.source}</span>
          </p>
        </div>
        <div className="actions-etude" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a className="bouton principal" href={e.liens.rapport} target="_blank" rel="noreferrer">
            <Download strokeWidth={1.5} />Feuille de route{e.liens.pdf_disponible ? " (PDF)" : ""}
          </a>
          {e.liens.pdf_disponible ? (
            <a className="bouton" href={e.liens.rapport_html} target="_blank" rel="noreferrer"><Printer strokeWidth={1.5} />Version web</a>
          ) : null}
          <a className="bouton discret" href={e.liens.etude} target="_blank" rel="noreferrer"><FileJson strokeWidth={1.5} />JSON</a>
          <button className="bouton discret danger" onClick={supprimer}><Trash2 strokeWidth={1.5} />Supprimer</button>
        </div>
      </div>

      <nav className="sommaire" aria-label="Sections de l'étude">
        {SECTIONS.map(([ancre, nom]) => <a key={ancre} href={`#${ancre}`}>{nom}</a>)}
      </nav>

      <div className="pile" style={{ gap: 40 }}>
        {/* ------------------------------------------------ synthèse */}
        <section id="synthese" className="section">
          <h2>Synthèse</h2>
          <p className="section-intro">Estimation simplifiée calée sur un RSET Pléiades, avec sa fourchette. Le point est l'estimation, la bande la fourchette, le trait le seuil.</p>
          <div className="indicateurs">
            <Jauge titre="Bbio" v={e.estimation.Bbio} seuil={s.Bbio_max.valeur} unite="points" verdict={e.verdict.Bbio} />
            <Jauge titre="Cep" v={e.estimation.Cep} seuil={s.Cep_max.valeur} unite="kWhep/m²" verdict={e.verdict.Cep} />
            <Jauge titre="Cep,nr" v={e.estimation.Cep_nr} seuil={s.Cep_nr_max.valeur} unite="kWhep/m²" verdict={e.verdict.Cep_nr} />
            <Jauge titre="Ic construction, fiches par défaut" v={acv.Ic_construction.par_defaut} seuil={acv.Ic_construction_max.valeur}
              unite="kg/m²" verdict={acv.verdict.par_defaut}
              note={`Avec FDES sur 5 postes : ${nombre(acv.Ic_construction.top_fiches.valeur, 0)} · Ic énergie ${nombre(acv.Ic_energie.valeur, 0)} / ${nombre(acv.Ic_energie_max.valeur, 0)}`} />
          </div>
          {e.tertiaire ? (
            <div className="note-approx"><AlertTriangle strokeWidth={1.5} />Usage « {String(e.usage?.valeur)} » : les seuils et le modèle de l'outil sont ceux de la maison individuelle. Les données lues (géométrie, parois, baies, ponts thermiques, systèmes) restent valables pour la saisie ; Bbio et Cep sont indicatifs, à calculer dans Pléiades.</div>
          ) : null}
          {s.approx && !e.tertiaire ? (
            <div className="note-approx"><AlertTriangle strokeWidth={1.5} />Seuils approchés : MbHSP et McHSP sont inconnus pour ce permis. Les lire dans Pléiades et les saisir dans les options avancées pour un seuil exact.</div>
          ) : null}
        </section>

        {/* ------------------------------------------------ dossier lu */}
        <SectionDossier e={e} />

        {/* ------------------------------------------------ plan */}
        <section id="plan" className="section">
          <h2>Plan lu</h2>
          <p className="section-intro">Ce que l'outil a reconnu sur le plan. À regarder avant de saisir : si un contour ou une baie est mal placé, la feuille de route l'est aussi.</p>
          <div className="colonnes-plan">
            <div className="carte carte-corps">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="plan-image" src={e.liens.controle} alt="Plan avec les détections : contour des murs, baies, nord" />
              <div className="plan-legende">
                <span><i style={{ background: "#00aa00" }} />Contour des murs</span>
                <span><i style={{ background: "#ff8c00" }} />Baie appariée à son étiquette</span>
                <span><i style={{ background: "#dc0000" }} />Baie à vérifier</span>
                <span><i style={{ background: "#0000ff" }} />Nord lu</span>
              </div>
            </div>
            <div className="pile" style={{ gap: 16 }}>
              <div className="carte carte-corps">
                <dl className="liste-def">
                  <dt>Échelle</dt><dd><V v={e.plan.echelle.denominateur} /></dd>
                  <dt>Nord</dt><dd><V v={e.plan.nord as any} decimales={1} /></dd>
                  <dt>Niveaux</dt><dd><V v={bat.nombre_niveaux} /></dd>
                  <dt>Surface intérieure</dt><dd><V v={bat.surface_interieure_totale_m2} decimales={1} /></dd>
                  <dt>Pièces étiquetées</dt><dd><V v={bat.surface_pieces_etiquetees_totale_m2} decimales={1} /></dd>
                  <dt>Hauteur sous plafond</dt><dd><V v={bat.hauteur_sous_plafond_m} /></dd>
                </dl>
              </div>
              {e.plan.niveaux.map((n) => (
                <div className="carte carte-corps" key={n.niveau.valeur}>
                  <h3 style={{ marginBottom: 12 }}>{n.niveau.valeur} <span className="muet" style={{ fontWeight: 400 }}>· {n.forme.valeur}</span></h3>
                  <dl className="liste-def">
                    <dt>Emprise</dt><dd className="chiffres">{nombre(n.emprise_m.largeur.valeur, 2)} × {nombre(n.emprise_m.profondeur.valeur, 2)} m</dd>
                    <dt>Mur</dt><dd><V v={n.murs_exterieurs.couche_pleine_m} /></dd>
                    <dt>Isolant extérieur</dt><dd><V v={n.murs_exterieurs.bande_hachuree_ext_m} /></dd>
                    <dt>Doublage intérieur</dt><dd><V v={n.murs_exterieurs.bande_hachuree_int_m} /></dd>
                    <dt>Isolation</dt><dd><V v={n.murs_exterieurs.isolation} /></dd>
                    <dt>Surface intérieure</dt><dd><V v={n.surface_interieure_m2} decimales={1} /></dd>
                  </dl>
                </div>
              ))}
              {e.plan.alertes.length ? (
                <div className="carte"><ul className="liste-alertes">{e.plan.alertes.map((a) => <li key={a}><AlertTriangle />{a}</li>)}</ul></div>
              ) : null}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------ enveloppe */}
        <section id="enveloppe" className="section">
          <h2>Enveloppe</h2>
          <div className="pile">
            <div className="carte">
              <div className="carte-tete"><h3>Baies</h3><LegendeProvenance /></div>
              <div className="tableau-conteneur">
                <table>
                  <thead><tr>
                    <th>Niveau</th><th>Baie</th><th>Orientation</th><th className="n">Largeur</th><th className="n">Hauteur</th>
                    <th className="n">Allège</th><th className="n">Surface</th><th>Remarque</th>
                  </tr></thead>
                  <tbody>
                    {e.plan.niveaux.flatMap((n) => n.baies.map((b) => (
                      <tr key={`${n.niveau.valeur}-${b.nom}-${b.facade}`}>
                        <td className="second">{n.niveau.valeur}</td>
                        <td>{b.nom ?? "?"} <span className="muet mono">{b.facade}</span></td>
                        <td>{b.orientation ?? "—"}</td>
                        <td className="n"><V v={b.largeur_m} /></td>
                        <td className="n"><V v={b.hauteur_m} /></td>
                        <td className="n"><V v={b.allege_m} /></td>
                        <td className="n"><V v={b.surface_m2} /></td>
                        <td className={b.a_verifier ? "" : "muet"} style={b.a_verifier ? { color: "var(--attention)" } : undefined}>{b.a_verifier ?? b.mention ?? ""}</td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="colonnes-2">
              <div className="carte carte-corps">
                <h3>Surface vitrée par orientation</h3>
                <p className="muet" style={{ fontSize: 13, margin: "2px 0 16px" }}>m², total {nombre(bat.baies_total_m2, 2)} m²</p>
                <BarresH unite="m²" decimales={2}
                  donnees={Object.entries(bat.baies_par_orientation_m2 as Record<string, number>).sort((a, b) => b[1] - a[1]).map(([o, v]) => ({ nom: o, valeur: v }))} />
              </div>
              <div className="carte carte-corps">
                <h3>Déperditions par poste</h3>
                <p className="muet" style={{ fontSize: 13, margin: "2px 0 16px" }}>W/K, total {nombre(e.estimation.deperditions_W_K.total, 1)} W/K</p>
                <BarresH unite="W/K"
                  donnees={Object.entries(e.estimation.deperditions_W_K).filter(([k]) => k !== "total").sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ nom: POSTES[k] ?? libelle(k), valeur: v }))} />
              </div>
            </div>
            <div className="carte">
              <div className="carte-tete"><h3>Parois retenues pour l'estimation</h3><p>À remplacer par les compositions réelles dans la bibliothèque Pléiades</p></div>
              <div className="tableau-conteneur">
                <table>
                  <thead><tr><th>Paroi</th><th className="n">U</th><th>Origine</th></tr></thead>
                  <tbody>
                    {[["Murs extérieurs", "U_murs"], ["Plancher haut, toiture", "U_toiture"], ["Plancher bas", "U_plancher_bas"], ["Menuiseries (Uw)", "Uw"]].map(([nom, cle]) => (
                      <tr key={cle}><td>{nom}</td><td className="n"><V v={e.hypotheses[cle]} decimales={3} /></td><td className="second">{e.hypotheses[cle]?.source}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------ ponts thermiques */}
        <section id="ponts" className="section">
          <h2>Ponts thermiques</h2>
          <div className="carte">
            <div className="carte-tete">
              <h3>Linéaires et Ψ par liaison</h3>
              <p className="chiffres">Ratio Ψ {nombre(e.hypotheses.ratio_psi.valeur, 2)} W/(m².K) · exigence ≤ 0,33</p>
            </div>
            <div className="tableau-conteneur">
              <table>
                <thead><tr><th>Liaison</th><th className="n">Longueur</th><th className="n">Ψ (W/m.K)</th><th className="n">Ψ·L (W/K)</th><th>Source du Ψ</th></tr></thead>
                <tbody>
                  {(e.hypotheses.ponts_thermiques as any[]).map((d) => (
                    <tr key={d.liaison}>
                      <td>{libelle(d.liaison)}</td>
                      <td className="n">{nombre(d.longueur_m, 1)} m</td>
                      <td className="n"><V v={d.psi} /></td>
                      <td className="n">{nombre(d.longueur_m * d.psi.valeur, 1)}</td>
                      <td className="second">{d.psi.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------ propositions */}
        <section id="propositions" className="section">
          <h2>Propositions</h2>
          <p className="section-intro">
            {e.propositions.nb_combinaisons_testees.toLocaleString("fr-FR")} combinaisons testées, {e.propositions.nb_conformes.toLocaleString("fr-FR")} sous les seuils avec 5 % de marge. Classées par coût, prix indicatifs à remplacer par vos prix fournisseur.
          </p>
          {e.propositions.propositions.length ? (
            <div className="carte tableau-conteneur">
              <table>
                <thead><tr>
                  <th>#</th><th>Murs</th><th>Toiture</th><th>Plancher bas</th><th>Menuiseries</th><th>Système</th>
                  <th className="n">Bbio</th><th className="n">Cep</th><th className="n">Coût</th>
                </tr></thead>
                <tbody>
                  {e.propositions.propositions.map((x) => (
                    <tr key={x.rang}>
                      <td className="rang">{x.rang}</td>
                      <td>{x.murs.isolant}<div className="muet chiffres">{x.murs.epaisseur_cm} cm · U {nombre(x.murs.U, 3)}</div></td>
                      <td>{x.toiture.isolant}<div className="muet chiffres">{x.toiture.epaisseur_cm} cm · U {nombre(x.toiture.U, 3)}</div></td>
                      <td>{x.plancher_bas.isolant}<div className="muet chiffres">{x.plancher_bas.epaisseur_cm} cm · U {nombre(x.plancher_bas.U, 3)}</div></td>
                      <td>{x.menuiseries.nom}<div className="muet chiffres">Uw {nombre(x.menuiseries.Uw, 2)} · Sw {nombre(x.menuiseries.Sw, 2)}</div></td>
                      <td>{x.systeme}</td>
                      <td className="n chiffres">{nombre(x.Bbio.valeur, 1)}<div className="muet">marge {nombre(x.marges.Bbio, 1)}</div></td>
                      <td className="n chiffres">{nombre(x.Cep.valeur, 1)}<div className="muet">marge {nombre(x.marges.Cep, 1)}</div></td>
                      <td className="n"><span className="valeur">{euros(x.cout_eur.valeur)}<Pastille tag={x.cout_eur.tag} confiance={x.cout_eur.confiance} source={x.cout_eur.source} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="carte vide">Aucune combinaison du catalogue ne passe les seuils estimés</div>}
        </section>

        {/* ------------------------------------------------ ACV */}
        <section id="acv" className="section">
          <h2>ACV</h2>
          <p className="section-intro">Quantités tirées du plan. Les valeurs de fiches sont des ordres de grandeur tant que les fiches INIES réelles ne sont pas importées.</p>
          <div className="colonnes-2">
            <div className="carte carte-corps">
              <h3>Ic construction par lot</h3>
              <p className="muet" style={{ fontSize: 13, margin: "2px 0 16px" }}>kg éq. CO₂/m²</p>
              <BarresPaires unite="kg/m²" series={["Fiches par défaut", "Fiches spécifiques"]}
                donnees={Object.entries(acv.par_lot).map(([lot, v]) => ({ nom: `${lot} · ${v.libelle}`, a: v.defaut, b: v.specifique }))} />
            </div>
            <div className="pile" style={{ gap: 16 }}>
              <div className="carte carte-corps">
                <h3 style={{ marginBottom: 12 }}>Trois scénarios</h3>
                <dl className="liste-def">
                  <dt>Tout en fiches par défaut</dt><dd><V v={acv.Ic_construction.par_defaut} decimales={0} /> <Verdict v={acv.verdict.par_defaut} /></dd>
                  <dt>FDES sur les 5 plus gros postes</dt><dd><V v={acv.Ic_construction.top_fiches} decimales={0} /> <Verdict v={acv.verdict.top_fiches} /></dd>
                  <dt>Toutes fiches spécifiques</dt><dd><V v={acv.Ic_construction.tout_specifique} decimales={0} /> <Verdict v={acv.verdict.tout_specifique} /></dd>
                  <dt>Seuil</dt><dd><V v={acv.Ic_construction_max} decimales={0} /></dd>
                  <dt>Ic énergie</dt><dd><V v={acv.Ic_energie} decimales={0} /> <span className="muet">/ {nombre(acv.Ic_energie_max.valeur, 0)}</span></dd>
                </dl>
              </div>
              <div className="carte">
                <div className="carte-tete"><h3>Fiches à chercher en priorité</h3><p>INIES</p></div>
                <table>
                  <tbody>
                    {acv.recommandations.map((r) => (
                      <tr key={r.element}>
                        <td>{r.element}<div className="muet" style={{ fontSize: 12 }}>Lot {r.lot} · {r.remplacer}</div></td>
                        <td className="n chiffres">−{nombre(r.gain_kg_m2, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <details className="avance" style={{ marginTop: 16 }}>
            <summary><ChevronRight strokeWidth={1.5} />Inventaire par lot, quantités à saisir</summary>
            <div className="carte tableau-conteneur" style={{ marginTop: 12 }}>
              <table>
                <thead><tr><th>Lot</th><th>Élément</th><th className="n">Quantité</th><th>UF</th><th>Fiche par défaut</th><th className="n">Ic (kg/m²)</th></tr></thead>
                <tbody>
                  {acv.elements.map((l) => (
                    <tr key={l.element}>
                      <td className="rang">{l.lot}</td><td>{l.libelle}</td>
                      <td className="n"><V v={l.quantite} decimales={1} /></td><td className="second">{l.uf}</td>
                      <td className="second">{l.fiche_defaut.type} {nombre(l.fiche_defaut.ic, 1)}</td>
                      <td className="n chiffres">{nombre(l.ic_defaut_kg_m2, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>

        {/* ------------------------------------------------ hypothèses */}
        <section id="hypotheses" className="section">
          <h2>À valider avant la saisie</h2>
          <div className="colonnes-2">
            <div className="carte">
              <div className="carte-tete"><h3>Hypothèses</h3><p>Valeurs supposées par l'outil</p></div>
              <div className="tableau-conteneur">
                <table>
                  <tbody>
                    {suppositions({ plan: e.plan, hypotheses: e.hypotheses, acv: { hypotheses: acv.hypotheses } }).map(({ chemin, v }) => (
                      <tr key={chemin}>
                        <td>{nomHypothese(chemin)}<div className="muet" style={{ fontSize: 12 }}>{v.source}</div></td>
                        <td className="n"><V v={v} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="pile" style={{ gap: 16 }}>
              <div className="carte">
                <div className="carte-tete"><h3>Alertes</h3></div>
                <ul className="liste-alertes">{e.alertes.map((a) => <li key={a}><AlertTriangle />{a}</li>)}</ul>
              </div>
              <div className="carte">
                <div className="carte-tete"><h3>Documents à récupérer</h3></div>
                <ul className="liste-alertes">{e.manquants.map((m) => <li key={m} className="second">{m}</li>)}</ul>
              </div>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}


const NOMS_INFOS: Record<string, string> = {
  usage: "Usage", adresse: "Adresse", occupants: "Occupants", q4: "Perméabilité Q4Pa-surf", exposition_bruit: "Exposition au bruit",
  emprise_m2: "Emprise au sol", production_locale: "Production locale",
};

function Ligne({ nom, v, decimales = 2 }: { nom: string; v?: Valeur<any> | null; decimales?: number }) {
  if (!v) return null;
  return <><dt>{nom}</dt><dd><V v={v} decimales={decimales} /></dd></>;
}

function SectionDossier({ e }: { e: Etude }) {
  const d = e.dossier ?? {};
  const ctrl = e.controles ?? [];
  const src = e.parametres_sources ?? {};
  if (!d.pages_lues?.length && !ctrl.length) {
    return (
      <section id="dossier" className="section">
        <h2>Dossier lu</h2>
        <div className="carte vide">Aucune notice ni tableau trouvé : ajouter la notice thermique au dossier rend le résultat plus précis</div>
      </section>
    );
  }
  const nOk = ctrl.filter((c) => c.statut === "ok").length;
  return (
    <section id="dossier" className="section">
      <h2>Dossier lu</h2>
      <p className="section-intro">
        Données écrites dans le dossier (notice, tableaux, coupe), utilisées à la place des hypothèses. Pages et fichiers exploités : {d.pages_lues?.join(", ")}
        {e.plan.pages_plans?.length ? ` · plans : ${e.plan.pages_plans.join(", ")}` : ""}.
      </p>
      <div className="pile">
        {ctrl.length ? (
          <div className="carte">
            <div className="carte-tete">
              <h3>Contrôles croisés : plan mesuré / dossier écrit</h3>
              <p className="chiffres">{nOk} sur {ctrl.length} concordants</p>
            </div>
            <div className="tableau-conteneur">
              <table>
                <thead><tr><th>Grandeur</th><th className="n">Plan</th><th className="n">Dossier</th><th className="n">Écart</th><th>Statut</th></tr></thead>
                <tbody>
                  {ctrl.map((c) => (
                    <tr key={c.grandeur}>
                      <td>{c.grandeur}{c.detail ? <div className="muet" style={{ fontSize: 12 }}>{c.detail}</div> : null}</td>
                      <td className="n chiffres">{c.plan === null ? "—" : `${nombre(c.plan, 2)} ${c.unite}`}</td>
                      <td className="n chiffres">{c.dossier === null ? "—" : `${nombre(c.dossier, 2)} ${c.unite}`}</td>
                      <td className="n chiffres">{c.ecart_pct === null ? "—" : Math.abs(c.ecart_pct) < 0.05 ? "0 %" : `${c.ecart_pct > 0 ? "+" : ""}${nombre(c.ecart_pct, 1)} %`}</td>
                      <td>{c.statut === "ok"
                        ? <span className="verdict bon"><CheckCircle2 strokeWidth={1.5} />Concordant</span>
                        : <span className="verdict attention"><AlertTriangle strokeWidth={1.5} />{c.statut === "écart" ? "Écart" : "Absent"}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div className="colonnes-2">
          <div className="carte carte-corps">
            <h3 style={{ marginBottom: 12 }}>Projet</h3>
            <dl className="liste-def">
              <Ligne nom="Zone climatique" v={src.zone} />
              <Ligne nom="Altitude" v={src.altitude_m} decimales={0} />
              <Ligne nom="Dépôt du permis" v={src.date_pc} />
              {Object.entries(d.infos ?? {}).filter(([k]) => k in NOMS_INFOS).map(([k, v]) => <Ligne key={k} nom={NOMS_INFOS[k]} v={v as Valeur<any>} />)}
              <Ligne nom="Sref" v={d.surfaces?.sref} decimales={1} />
              <Ligne nom="Hauteur sous plafond" v={d.hauteurs?.hsp_m} />
              <Ligne nom="Hauteur d'étage" v={d.hauteurs?.hauteur_etage_m} />
            </dl>
          </div>
          <div className="carte carte-corps">
            <h3 style={{ marginBottom: 12 }}>Systèmes</h3>
            <dl className="liste-def">
              <Ligne nom="Chauffage" v={d.chauffage?.generateur} />
              <Ligne nom="Émetteurs" v={d.chauffage?.emetteurs} />
              <Ligne nom="Régime" v={d.chauffage?.regime} />
              <Ligne nom="ECS" v={d.ecs?.type} />
              <Ligne nom="Volume ECS" v={d.ecs?.volume_l} decimales={0} />
              <Ligne nom="Ventilation" v={d.ventilation?.type} />
              <Ligne nom="Débit" v={d.ventilation?.debit_m3h} decimales={0} />
              <Ligne nom="Rendement de l'échangeur" v={d.ventilation?.rendement} />
              <Ligne nom="Puissance des ventilateurs" v={d.ventilation?.puissance_Wh_m3} />
              <Ligne nom="Horaires" v={d.ventilation?.horaires} />
              <Ligne nom="Éclairage" v={d.eclairage?.puissances_W_m2 ? { ...d.eclairage.puissances_W_m2, valeur: d.eclairage.puissances_W_m2.valeur.join(" / ") } : null} />
            </dl>
          </div>
        </div>

        {d.parois?.length ? (
          <div className="carte">
            <div className="carte-tete"><h3>Parois de la notice</h3><p>À créer dans la bibliothèque Pléiades</p></div>
            <div className="tableau-conteneur">
              <table>
                <thead><tr><th>Réf.</th><th>Paroi</th><th className="n">Up</th><th>Composition</th></tr></thead>
                <tbody>
                  {d.parois.map((p: any) => (
                    <tr key={p.ref}>
                      <td className="rang">{p.ref}</td>
                      <td>{p.designation}<div className="muet" style={{ fontSize: 12 }}>{libelle(p.type_paroi)}</div></td>
                      <td className="n">{p.Up ? <V v={p.Up} /> : <span className="muet">sans objet</span>}</td>
                      <td className="second" style={{ fontSize: 13 }}>
                        {p.couches?.length ? p.couches.map((c: any) => `${c.materiau} ${nombre(c.epaisseur_mm, 0)} mm${c.lambda ? ` (λ ${nombre(c.lambda, 3)})` : ""}`).join(" · ") : p.composition}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {d.menuiseries?.length ? (
          <div className="carte">
            <div className="carte-tete"><h3>Menuiseries de la notice</h3></div>
            <div className="tableau-conteneur">
              <table>
                <thead><tr><th>Repère</th><th>Désignation</th><th className="n">U</th><th className="n">g</th><th className="n">TL</th><th className="n">Quantité</th><th className="n">Surface</th></tr></thead>
                <tbody>
                  {d.menuiseries.map((m: any) => (
                    <tr key={m.repere}>
                      <td className="rang">{m.repere}</td><td>{m.designation}</td>
                      <td className="n">{m.U ? <span className="valeur chiffres">{String(m.U.grandeur ?? "U")} {nombre(m.U.valeur, 2)}<Pastille tag={m.U.tag} source={m.U.source} /></span> : "—"}</td>
                      <td className="n"><V v={m.g} /></td>
                      <td className="n"><V v={m.TL} /></td>
                      <td className="n"><V v={m.quantite} decimales={0} /></td>
                      <td className="n"><V v={m.surface_m2} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
