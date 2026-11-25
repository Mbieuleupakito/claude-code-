import type { Metadata, Viewport } from "next";
import Coquille from "@/components/Coquille";
import "./globals.css";

export const metadata: Metadata = {
  title: "Feuille de route RE2020",
  description: "Prépare la saisie Pléiades d'une étude RE2020 à partir des plans de l'architecte",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function Racine({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <Coquille>{children}</Coquille>
      </body>
    </html>
  );
}
