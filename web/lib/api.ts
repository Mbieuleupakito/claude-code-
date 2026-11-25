// Accès à l'API locale (même origine) et types des données renvoyées par le moteur Python.

export type Tag = "lu" | "déduit" | "supposé";
export type Confiance = "haute" | "moyenne" | "faible";

export interface Valeur<T = number> {
  valeur: T;
  unite?: string;
  tag: Tag;
  source: string;
  confiance: Confiance;
  fourchette?: [number, number];
  note?: string;
  a_verifier?: string;
  [cle: string]: unknown;
}

export type Verdict = "conforme probable" | "non conforme probable" | "incertain";
export type VerdictIc = "sous le seuil" | "au-dessus du seuil" | "incertain";

export interface Liens {
  etude: string;
  rapport: string;
  rapport_html: string;
  pdf_disponible: boolean;
  controle: string;
}

export interface Synthese {
  verdict: Record<"Bbio" | "Cep" | "Cep_nr", Verdict>;
  Bbio: Valeur;
  Cep: Valeur;
  Cep_nr: Valeur;
  seuils: Record<"Bbio_max" | "Cep_max" | "Cep_nr_max", number>;
  seuils_approx: boolean;
  alertes: string[];
  acv?: {
    Ic_construction_defaut: Valeur;
    Ic_construction_top_fiches: Valeur;
    Ic_construction_max: number;
    Ic_energie: Valeur;
    verdict: Record<string, VerdictIc>;
  };
  zone?: string;
  sref?: number;
}

export interface EtudeListe {
  id: string;
  cree: string;
  projet: string;
  fichier: string;
  statut: "ok" | "erreur";
  erreur: string | null;
  synthese: Synthese | null;
  liens: Liens | null;
}

export interface Baie {
  nom: string | null;
  facade: string;
  cote_feuille: string | null;
  orientation: string | null;
  largeur_m: Valeur;
  hauteur_m: Valeur;
  allege_m?: Valeur;
  surface_m2: Valeur;
  largeur_mesuree_plan_m: Valeur;
  mention?: string;
  a_verifier?: string;
}

export interface Facade {
  id: string;
  cote_feuille: string | null;
  longueur_ext_m: Valeur;
  longueur_int_m: Valeur;
  azimut_deg?: Valeur;
  orientation?: Valeur<string>;
}

export interface Niveau {
  niveau: Valeur<string>;
  forme: Valeur<string>;
  emprise_m: { largeur: Valeur; profondeur: Valeur };
  surface_emprise_m2: Valeur;
  murs_exterieurs: {
    couche_pleine_m: Valeur;
    bande_hachuree_ext_m: Valeur;
    bande_hachuree_int_m: Valeur;
    isolation: Valeur<string>;
  };
  surface_interieure_m2: Valeur;
  perimetre_interieur_m: Valeur;
  angles: { saillants: number; rentrants: number };
  pieces: { nom: string | null; surface_m2: number }[];
  facades: Facade[];
  baies: Baie[];
}

export interface Couche {
  materiau: string;
  epaisseur_cm: number;
  lambda_W_mK: number | null;
  R_m2K_W: number;
  tag: string;
  isolant?: boolean;
  certifie?: boolean;
  note?: string;
}

export interface ParoiProposee {
  isolant: string | null;
  epaisseur_cm: number | null;
  U: number;
  systeme?: string;
  composition?: string;
  couches?: Couche[];
  epaisseur_totale_cm?: number;
  cout_eur?: number | null;
}

export interface Proposition {
  rang: number;
  murs: ParoiProposee;
  toiture: ParoiProposee;
  plancher_bas: ParoiProposee;
  menuiseries: { nom: string; Uw: number; Sw: number };
  systeme: string;
  Bbio: Valeur;
  Cep: Valeur;
  Cep_nr: Valeur;
  marges: Record<string, number>;
  cout_eur: Valeur<number | null>;
  alertes: string[];
}

export interface ElementAcv {
  lot: number;
  element: string;
  libelle: string;
  uf: string;
  quantite: Valeur;
  fiche_defaut: { type: string; ic: number; tag: Tag };
  fiche_specifique: { type: string; nom: string; ic: number; tag: Tag } | null;
  ic_defaut_kg_m2: number;
  ic_specifique_kg_m2: number;
  gain_kg_m2: number;
}

export interface Controle {
  grandeur: string;
  plan: number | null;
  dossier: number | null;
  unite: string;
  ecart_pct: number | null;
  statut: "ok" | "écart" | "absent";
  detail?: string;
}

export interface Etude {
  id: string;
  dossier?: Record<string, any>;
  controles?: Controle[];
  parametres_sources?: Record<string, Valeur<any>>;
  usage?: Valeur<string> | null;
  tertiaire?: boolean;
  qualite?: { niveau: "bonne" | "moyenne" | "insuffisante"; graves: string[]; mineurs: string[]; conseils: string[] };
  fichiers?: { plans: string[]; documents: string[]; non_lus: string[] };
  liens: Liens;
  projet: string;
  date_rapport: string;
  parametres: Record<string, string | number | boolean | null>;
  plan: {
    source: string;
    pages_plans?: string[];
    echelle: { denominateur: Valeur; m_par_pt: number };
    nord: Valeur<number | null> & { explication?: string };
    niveaux: Niveau[];
    batiment: Record<string, any>;
    alertes: string[];
  };
  hypotheses: Record<string, any>;
  entrees: { sref: number; surfaces_m2: Record<string, number>; U: Record<string, number>; baies_m2: Record<string, number> };
  seuils: Record<"Bbio_max" | "Cep_max" | "Cep_nr_max", Valeur> & { approx: boolean };
  estimation: {
    deperditions_W_K: Record<string, number>;
    besoins_kWh_m2: Record<string, Valeur>;
    Bbio: Valeur;
    Cep: Valeur;
    Cep_nr: Valeur;
    sensibilite_Bbio_points: Record<string, number>;
    systeme: string;
  };
  verdict: Record<"Bbio" | "Cep" | "Cep_nr", Verdict>;
  propositions: { propositions: Proposition[]; nb_combinaisons_testees: number; nb_conformes: number; avertissement: string;
    variantes?: Record<string, ParoiProposee[]> };
  acv: {
    Ic_construction: Record<"par_defaut" | "top_fiches" | "tout_specifique", Valeur>;
    Ic_construction_max: Valeur;
    verdict: Record<"par_defaut" | "top_fiches" | "tout_specifique", VerdictIc>;
    par_lot: Record<string, { libelle: string; defaut: number; specifique: number }>;
    elements: ElementAcv[];
    recommandations: { element: string; lot: number; gain_kg_m2: number; remplacer: string }[];
    Ic_energie: Valeur;
    Ic_energie_max: Valeur;
    hypotheses: Record<string, Valeur<string>>;
  };
  alertes: string[];
  manquants: string[];
}

export interface Config {
  zones: string[];
  systemes: string[];
  structures: Record<string, string>;
  planchers: Record<string, string>;
  menuiseries: Record<string, string>;
}

export interface LigneReference {
  cas: string;
  Bbio_pleiades: number[];
  Bbio_estime: number | null;
  fourchette: [number, number] | null;
  Cep_pleiades: number[];
  Cep_estime: number | null;
  note: string;
  ecart_Bbio?: number;
  dans_fourchette?: boolean;
}

async function lire<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  const texte = await r.text();
  let corps: any = null;
  try {
    corps = texte ? JSON.parse(texte) : null;
  } catch {
    corps = null;
  }
  if (!r.ok) {
    const d = corps?.detail;
    const e = new Error(typeof d === "string" ? d : d?.message ?? `Erreur ${r.status}`) as Error & { code?: string };
    if (d && typeof d === "object") e.code = d.code;
    throw e;
  }
  return corps as T;
}

export const api = {
  etudes: () => lire<EtudeListe[]>("/api/etudes"),
  etude: (id: string) => lire<Etude>(`/api/etudes/${id}`),
  creer: (donnees: FormData) => lire<{ id: string }>("/api/etudes", { method: "POST", body: donnees }),
  supprimer: (id: string) => lire<{ supprime: string }>(`/api/etudes/${id}`, { method: "DELETE" }),
  config: () => lire<Config>("/api/config"),
  references: () => lire<LigneReference[]>("/api/references"),
  catalogues: () => lire<any>("/api/catalogues"),
};

/** Toutes les valeurs « supposé » d'un objet, avec leur chemin, pour la liste des hypothèses à valider. */
export function suppositions(o: unknown, chemin = ""): { chemin: string; v: Valeur<any> }[] {
  const out: { chemin: string; v: Valeur<any> }[] = [];
  if (Array.isArray(o)) {
    o.forEach((x, i) => out.push(...suppositions(x, `${chemin} ${i + 1}`)));
  } else if (o && typeof o === "object") {
    const r = o as Record<string, unknown>;
    if (r.tag === "supposé" && "valeur" in r) out.push({ chemin, v: r as unknown as Valeur<any> });
    for (const [k, x] of Object.entries(r)) {
      if (!k.startsWith("_")) out.push(...suppositions(x, chemin ? `${chemin} › ${k}` : k));
    }
  }
  return out;
}
