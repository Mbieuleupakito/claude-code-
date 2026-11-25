"use client";

import { AlertTriangle, CheckCircle2, CircleHelp, XCircle } from "lucide-react";
import type { Tag, Valeur, Verdict as TVerdict, VerdictIc } from "@/lib/api";
import { nombre } from "@/lib/format";

const CLASSE: Record<Tag, string> = { lu: "lu", "déduit": "deduit", "supposé": "suppose" };
const TITRE: Record<Tag, string> = {
  lu: "Lu sur le document",
  "déduit": "Déduit (calcul ou catalogue)",
  "supposé": "Supposé : hypothèse à valider",
};

/** Pastille de provenance : la signature de l'interface. */
export function Pastille({ tag, confiance, source }: { tag: Tag; confiance?: string; source?: string }) {
  const titre = `${TITRE[tag]}${confiance ? ` · confiance ${confiance}` : ""}${source ? `\n${source}` : ""}`;
  return <span className={`pastille ${CLASSE[tag]}`} title={titre} aria-label={titre} role="img" />;
}

export function V({ v, decimales = 2, unite }: { v?: Valeur<any> | null; decimales?: number; unite?: string }) {
  if (!v) return <span className="muet">—</span>;
  const x = v.valeur;
  const texte = typeof x === "number" ? nombre(x, decimales) : x === null || x === undefined ? "—" : String(x);
  const u = unite ?? v.unite ?? "";
  return (
    <span className="valeur chiffres">
      <span>{texte}{u && texte !== "—" ? ` ${u}` : ""}</span>
      <Pastille tag={v.tag} confiance={v.confiance} source={v.source} />
    </span>
  );
}

export function LegendeProvenance() {
  return (
    <div className="legende-prov">
      <span><span className="pastille lu" /> Lu sur le plan</span>
      <span><span className="pastille deduit" /> Déduit</span>
      <span><span className="pastille suppose" /> Supposé, à valider</span>
    </div>
  );
}

const VERDICTS: Record<string, { classe: string; Icone: typeof CheckCircle2; texte: string }> = {
  "conforme probable": { classe: "bon", Icone: CheckCircle2, texte: "Conforme probable" },
  "sous le seuil": { classe: "bon", Icone: CheckCircle2, texte: "Sous le seuil" },
  incertain: { classe: "attention", Icone: AlertTriangle, texte: "Incertain" },
  "non conforme probable": { classe: "critique", Icone: XCircle, texte: "Non conforme probable" },
  "au-dessus du seuil": { classe: "critique", Icone: XCircle, texte: "Au-dessus du seuil" },
};

export function Verdict({ v }: { v: TVerdict | VerdictIc | string }) {
  const d = VERDICTS[v] ?? { classe: "", Icone: CircleHelp, texte: v };
  return (
    <span className={`verdict ${d.classe}`}>
      <d.Icone strokeWidth={1.5} aria-hidden />
      {d.texte}
    </span>
  );
}
