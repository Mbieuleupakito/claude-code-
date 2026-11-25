"""Formats d'entrée autres que le PDF.

- DXF : redessiné en PDF vectoriel à une échelle exacte (1:100), avec les vrais textes, pour réutiliser toute la
  lecture de plans. Les calques servent à reconnaître les murs dessinés en simples traits (« MURS », « A-WALL »…) :
  leurs contours fermés deviennent des aplats. Les hachures (isolant) sont dessinées ligne par ligne.
- DWG : format fermé, converti en DXF SUR LE POSTE par ODA File Converter (gratuit) ou LibreDWG (dwg2dxf) s'ils
  sont installés ; aucun fichier n'est envoyé à l'extérieur.
- Word (.docx), LibreOffice (.odt, .ods, dont les rapports Pléiades), Excel (.xlsx), texte (.txt, .csv) : lus par documents.lecture comme une notice.
- Images : conservées mais non lues (pas de géométrie exploitable dans un scan).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PLANS = {".pdf", ".dxf", ".dwg"}
DOCUMENTS = {".pdf", ".docx", ".odt", ".ods", ".xlsx", ".xlsm", ".txt", ".csv"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
ACCEPTES = PLANS | DOCUMENTS | IMAGES

RE_CALQUE_MUR = re.compile(r"mur|wall|voile|cloison|ma[cç]onn|struct|a-wall|porteur", re.I)
UNITES_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}  # $INSUNITS → mètres


class FormatNonLu(ValueError):
    pass


# --------------------------------------------------------------------------- DWG → DXF

def trouver_oda() -> str | None:
    """Chemin d'ODA File Converter. L'installeur Windows crée un dossier versionné (« ODAFileConverter 26.4.0 ») que
    ezdxf ne cherche pas : on le trouve et on l'indique à ezdxf."""
    import glob

    import ezdxf

    candidats = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.expanduser(r"~\AppData\Local\Programs")):
        candidats += sorted(glob.glob(os.path.join(base, "ODA", "ODAFileConverter*", "ODAFileConverter.exe")), reverse=True)
    candidats += glob.glob("/Applications/ODAFileConverter*.app/Contents/MacOS/ODAFileConverter")
    candidats += [x for x in (shutil.which("ODAFileConverter"),) if x]
    for c in candidats:
        if os.path.isfile(c):
            if c.lower().endswith(".exe"):
                ezdxf.options.set("odafc-addon", "win_exec_path", f'"{c}"')
            else:
                ezdxf.options.set("odafc-addon", "unix_exec_path", c)
            return c
    return None


def dwg_vers_dxf(dwg: Path, dossier_sortie: Path) -> Path:
    from ezdxf.addons import odafc

    sortie = dossier_sortie / (dwg.stem + ".dxf")
    trouver_oda()
    if odafc.is_installed():
        odafc.convert(str(dwg), str(sortie), version="R2018", replace=True)
        return sortie
    if shutil.which("dwg2dxf"):
        subprocess.run(["dwg2dxf", "-y", "-o", str(sortie), str(dwg)], check=True, capture_output=True, timeout=300)
        return sortie
    raise FormatNonLu(MESSAGE_DWG)


MESSAGE_DWG = ("DWG non lus : installer ODA File Converter (gratuit, https://www.opendesign.com/guestfiles/oda_file_converter, "
               "version Windows), puis relancer l'étude : les DWG seront convertis sur ce poste. Sinon demander à l'architecte "
               "un PDF vectoriel ou un DXF.")


# --------------------------------------------------------------------------- DXF → PDF vectoriel

def _couleur(e, doc) -> tuple[float, float, float]:
    from ezdxf import colors

    if e.dxf.hasattr("true_color"):
        r, g, b = colors.int2rgb(e.dxf.true_color)
    else:
        aci = e.dxf.get("color", 256)
        if aci in (0, 256):
            try:
                aci = doc.layers.get(e.dxf.layer).color
            except Exception:
                aci = 7
        aci = abs(aci) or 7
        r, g, b = colors.aci2rgb(aci) if aci != 7 else (0, 0, 0)  # 7 = noir sur papier blanc
    return r / 255, g / 255, b / 255


def _sombre(c):
    """Une couleur trop claire pour un aplat de mur sur papier blanc est assombrie."""
    return c if min(c) < 0.75 else (0.35, 0.35, 0.35)


def dxf_vers_pdf(dxf: Path, sortie: Path, echelle: int = 100) -> Path:
    import ezdxf
    from ezdxf import bbox, disassemble, path as epath
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    doc = ezdxf.readfile(str(dxf))
    msp = doc.modelspace()
    entites = [e for e in disassemble.recursive_decompose(msp) if not e.dxf.get("invisible", 0)]
    ext = bbox.extents(entites, fast=True)
    if not ext.has_data:
        raise FormatNonLu(f"« {dxf.name} » : DXF vide (rien dans l'espace objet).")
    unite = UNITES_M.get(doc.header.get("$INSUNITS", 0))
    if unite is None:  # sans unité déclarée : une maison fait 5 à 50 m
        unite = 0.001 if max(ext.size.x, ext.size.y) > 1000 else (0.01 if max(ext.size.x, ext.size.y) > 200 else 1.0)
    pt = 72 / 0.0254 / echelle * unite  # points PDF par unité du dessin
    marge = 60.0
    W = ext.size.x * pt + 2 * marge
    H = ext.size.y * pt + 2 * marge + 40
    X = lambda x: marge + (x - ext.extmin.x) * pt
    Y = lambda y: marge + 40 + (y - ext.extmin.y) * pt

    fonte = "Helvetica"
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", r"C:\Windows\Fonts\arial.ttf", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(f):
            pdfmetrics.registerFont(TTFont("Plan", f))
            fonte = "Plan"
            break

    c = canvas.Canvas(str(sortie), pagesize=(W, H))
    c.setLineWidth(0.24)

    # 1. murs dessinés en traits : contours fermés des calques de murs → aplats
    segs_mur = []
    for e in entites:
        if RE_CALQUE_MUR.search(e.dxf.layer) and e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
            pts = [(v.x, v.y) for v in epath.make_path(e).flattening(0.01 / unite)]
            segs_mur += [LineString([a, b]) for a, b in zip(pts, pts[1:]) if a != b]
    if segs_mur:
        for pg in polygonize(unary_union(segs_mur)):
            ep_moy = 2 * pg.area / pg.length * unite if pg.length else 0
            if 0.04 <= ep_moy <= 0.8:  # forme d'épaisseur murale (pas une pièce)
                chemin = c.beginPath()
                xs = list(pg.exterior.coords)
                chemin.moveTo(X(xs[0][0]), Y(xs[0][1]))
                for x, y in xs[1:]:
                    chemin.lineTo(X(x), Y(y))
                chemin.close()
                c.setFillColorRGB(0.35, 0.35, 0.35)
                c.drawPath(chemin, fill=1, stroke=0)

    # 2. aplats (hachures pleines, SOLID) puis hachures à motif, puis traits, puis textes
    for e in entites:
        t = e.dxftype()
        coul = _couleur(e, doc)
        if t == "HATCH" and e.dxf.solid_fill:
            for p in epath.from_hatch(e):
                pts = list(p.flattening(0.01 / unite))
                if len(pts) < 3:
                    continue
                chemin = c.beginPath()
                chemin.moveTo(X(pts[0].x), Y(pts[0].y))
                for v in pts[1:]:
                    chemin.lineTo(X(v.x), Y(v.y))
                chemin.close()
                c.setFillColorRGB(*_sombre(coul))
                c.drawPath(chemin, fill=1, stroke=0)
        elif t in ("SOLID", "TRACE", "3DFACE"):
            pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx3, e.dxf.vtx2] if t != "3DFACE" else [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
            chemin = c.beginPath()
            chemin.moveTo(X(pts[0][0]), Y(pts[0][1]))
            for v in pts[1:]:
                chemin.lineTo(X(v[0]), Y(v[1]))
            chemin.close()
            c.setFillColorRGB(*_sombre(coul))
            c.drawPath(chemin, fill=1, stroke=0)
    for e in entites:
        t = e.dxftype()
        coul = _couleur(e, doc)
        c.setStrokeColorRGB(*coul)
        if t == "HATCH" and not e.dxf.solid_fill:
            from ezdxf.render import hatching
            try:
                for ligne in hatching.hatch_entity(e, max_lines=20000):
                    c.line(X(ligne.start.x), Y(ligne.start.y), X(ligne.end.x), Y(ligne.end.y))
            except Exception:
                pass
        elif t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            pts = list(epath.make_path(e).flattening(0.005 / unite))
            for a, b in zip(pts, pts[1:]):
                c.line(X(a.x), Y(a.y), X(b.x), Y(b.y))
    c.setFillColorRGB(0, 0, 0)
    for e in entites:
        t = e.dxftype()
        if t in ("TEXT", "ATTRIB", "MTEXT"):
            texte = e.plain_text() if t == "MTEXT" else e.dxf.text
            h = (e.dxf.char_height if t == "MTEXT" else e.dxf.height) * pt
            ins = e.dxf.insert
            rot = e.dxf.get("rotation", 0)
            c.saveState()
            c.translate(X(ins.x), Y(ins.y))
            c.rotate(rot)
            c.setFont(fonte, max(3.0, min(h, 30)))
            for i, ligne in enumerate(str(texte).splitlines()):
                c.drawString(0, -i * h * 1.2, ligne)
            c.restoreState()
    c.setFont(fonte, 9)
    c.drawString(marge, 20, f"Ech : 1 : {echelle}")
    c.drawString(marge + 120, 20, f"{dxf.name} (rendu vectoriel du DXF)")
    c.showPage()
    c.save()
    return sortie


# --------------------------------------------------------------------------- tri des fichiers d'un dossier

def preparer(fichiers: list, dossier_travail: Path | None = None) -> dict:
    """Range les fichiers par usage. Retourne {plans: [pdf], documents: [fichiers lisibles], non_lus: [(nom, raison)]}."""
    travail = Path(dossier_travail or tempfile.mkdtemp(prefix="re2020_"))
    plans, docs, non_lus = [], [], []
    for f in map(Path, fichiers):
        ext = f.suffix.lower()
        try:
            if ext == ".pdf":
                plans.append(f)
                docs.append(f)
            elif ext in (".dxf", ".dwg"):
                dxf = dwg_vers_dxf(f, travail) if ext == ".dwg" else f
                pdf = dxf_vers_pdf(dxf, travail / (f.stem + "_dxf.pdf"))
                plans.append(pdf)
                docs.append(pdf)
            elif ext in DOCUMENTS:
                docs.append(f)
            elif ext in IMAGES:
                non_lus.append((f.name, "image (scan) : pas de géométrie lisible, demander un PDF vectoriel ou un DXF"))
            else:
                non_lus.append((f.name, f"format {ext or 'inconnu'} non pris en charge"))
        except FormatNonLu as exc:
            non_lus.append((f.name, str(exc)))
        except Exception as exc:  # fichier abîmé, version DXF exotique…
            non_lus.append((f.name, f"illisible ({type(exc).__name__} : {exc})"))
    return {"plans": plans, "documents": docs, "non_lus": non_lus}

