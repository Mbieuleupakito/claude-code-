// Copie le site compilé (out/) dans le paquet Python (src/re2020/web) : l'utilisateur n'a besoin que de Python.
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ici = dirname(fileURLToPath(import.meta.url));
const source = join(ici, "..", "out");
const cible = join(ici, "..", "..", "src", "re2020", "web");
if (!existsSync(source)) throw new Error("out/ absent : lancer next build d'abord");
rmSync(cible, { recursive: true, force: true });
cpSync(source, cible, { recursive: true });
console.log(`Site publié dans ${cible}`);
