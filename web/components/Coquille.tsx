"use client";

import { BookOpen, FilePlus2, FolderOpen, Gauge, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const LIENS = [
  { href: "/", nom: "Études", icone: FolderOpen },
  { href: "/nouvelle/", nom: "Nouvelle étude", icone: FilePlus2 },
  { href: "/modele/", nom: "Fiabilité du modèle", icone: Gauge },
  { href: "/catalogues/", nom: "Catalogues", icone: BookOpen },
];

function Marque() {
  return (
    <div className="marque">
      <div className="marque-signe" aria-hidden><span /></div>
      <div>
        <div className="marque-nom">Feuille de route</div>
        <div className="marque-sous">RE2020 · Pléiades</div>
      </div>
    </div>
  );
}

export default function Coquille({ children }: { children: React.ReactNode }) {
  const chemin = usePathname() || "/";
  const [ouvert, setOuvert] = useState(false);
  const [version, setVersion] = useState<string>("");
  useEffect(() => {
    fetch("/api/version").then((r) => r.json()).then((v) => setVersion(`Version ${v.version}${v.commit ? ` · ${v.commit} du ${v.date}` : ""}`)).catch(() => {});
  }, []);
  useEffect(() => setOuvert(false), [chemin]);
  const actif = (href: string) => (href === "/" ? chemin === "/" || chemin.startsWith("/etude") : chemin.startsWith(href));

  return (
    <>
      <header className="tete-mobile">
        <Marque />
        <button className="bouton discret" aria-label={ouvert ? "Fermer le menu" : "Ouvrir le menu"} onClick={() => setOuvert(!ouvert)}>
          {ouvert ? <X /> : <Menu />}
        </button>
      </header>
      <div className="coquille">
        <div className="colonne-barre">
          <aside className={`barre${ouvert ? " ouverte" : ""}`}>
            <div className="masque-mobile"><Marque /></div>
            <nav className="nav" aria-label="Navigation principale">
              <div className="nav-titre">Navigation</div>
              {LIENS.map(({ href, nom, icone: Icone }) => (
                <Link key={href} href={href} aria-current={actif(href) ? "page" : undefined}>
                  <Icone strokeWidth={1.5} />
                  {nom}
                </Link>
              ))}
            </nav>
            <p className="barre-pied">
              Estimation pour préparer la saisie. Les résultats officiels sont ceux de Pléiades.
              <br />Les plans restent sur ce poste.
              {version ? <><br /><span className="mono">{version}</span></> : null}
            </p>
          </aside>
        </div>
        <main className="contenu">{children}</main>
      </div>
    </>
  );
}
