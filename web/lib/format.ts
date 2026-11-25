// Formats français, chiffres tabulaires gérés en CSS.

export function nombre(x: number | null | undefined, decimales = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return x.toLocaleString("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: 0 });
}

export function euros(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return x.toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
}

export function date(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

export function heure(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** « mur / plancher bas » → « Mur / plancher bas » ; « plancher_bas » → « Plancher bas ». */
export function libelle(s: string): string {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
