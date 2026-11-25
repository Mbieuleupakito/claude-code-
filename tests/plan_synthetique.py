"""Génère un plan PDF vectoriel minimal (maison 10 x 8 m au 1:100) pour tester l'extraction sans données client."""
import math

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

M = 72 / 0.0254 / 100  # points par mètre au 1:100


def generer(chemin, angle_nord_deg=0.0):
    W, H = landscape(A4)
    c = canvas.Canvas(str(chemin), pagesize=(W, H))
    Y = lambda y: H - y  # repère « haut de page » comme pdfplumber
    x0, y0, L, P, ep, iso = 150.0, 120.0, 10 * M, 8 * M, 0.20 * M, 0.15 * M
    # murs pleins (aplat)
    c.setFillColorRGB(0, 0.5, 0.75)
    for (x, y, w, h) in ((x0, y0, L, ep), (x0, y0 + P - ep, L, ep), (x0, y0, ep, P), (x0 + L - ep, y0, ep, P)):
        c.rect(x, Y(y + h), w, h, fill=1, stroke=0)
    # cloison intérieure
    c.rect(x0 + 5 * M, Y(y0 + P - ep), 0.07 * M, P - 2 * ep, fill=1, stroke=0)
    # bande isolant hachurée à l'extérieur, interrompue par la baie F1 (façade bas, 3,00 → 4,20 m)
    c.setStrokeColorRGB(0.8, 0.2, 0.2)
    c.setLineWidth(0.24)
    trou = (x0 + 3 * M, x0 + 4.2 * M)
    pas = 3.0
    x = x0 - iso
    while x < x0 + L + iso - iso:
        for yb in (y0 - iso, y0 + P):  # haut et bas
            morceaux = [(x, x + iso)]
            if yb == y0 + P:  # découpe exacte de la hachure au droit de la baie
                morceaux = [(a, b) for a, b in ((x, min(x + iso, trou[0])), (max(x, trou[1]), x + iso)) if b - a > 0.05]
            for a, b in morceaux:
                c.line(a, Y(yb + a - x), b, Y(yb + b - x))
        x += pas
    y = y0 - iso
    while y < y0 + P + iso - iso:
        for xb in (x0 - iso, x0 + L):  # gauche et droite
            c.line(xb, Y(y), xb + iso, Y(y + iso))
        y += pas
    # textes
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 6)
    cx = (trou[0] + trou[1]) / 2
    for i, t in enumerate(("F1", "120 x 135ht.", "all.90")):
        c.drawCentredString(cx, Y(y0 + P + iso + 10 + 7 * i), t)
    c.drawCentredString(x0 + 2.5 * M, Y(y0 + 3.8 * M), "Séjour")
    c.drawCentredString(x0 + 2.5 * M, Y(y0 + 3.8 * M + 7), "38.5 m²")
    c.setFont("Helvetica", 9)
    c.drawString(x0, Y(y0 + P + 70), "RDC projet")
    c.drawString(x0, Y(y0 + P + 82), "Ech : 1 : 100")
    # symbole du nord : cercle + diamètre + pointe
    nx, ny, r = x0 + L + 60, y0 + P + 70, 10.0
    pts = [(nx + r * math.cos(2 * math.pi * i / 36), ny + r * math.sin(2 * math.pi * i / 36)) for i in range(37)]
    c.setStrokeColorRGB(0, 0, 0)
    for (a, b) in zip(pts, pts[1:]):
        c.line(a[0], Y(a[1]), b[0], Y(b[1]))
    t = math.radians(angle_nord_deg)
    ux, uy = math.sin(t), -math.cos(t)  # vers le nord, repère page
    tip, tail = (nx + r * ux, ny + r * uy), (nx - r * ux, ny - r * uy)
    c.line(tail[0], Y(tail[1]), tip[0], Y(tip[1]))
    for s in (1, -1):
        a = math.atan2(-uy, -ux) + s * math.radians(30)
        c.line(tip[0], Y(tip[1]), tip[0] + 4 * math.cos(a), Y(tip[1] + 4 * math.sin(a)))
    c.showPage()
    c.save()


def generer_l(chemin, angle_nord_deg=90.0):
    """Maison en L dessinée « à la Charleville » : murs en polygones (pas des rectangles), ouvertures coupées
    dans la structure, isolant hachuré à l'intérieur (ITI), dessin au 1:50 alors que la mention dit 1:100,
    lignes de cote écrites (« 10.00 », « 8.00 », « 6.00 ») pour recalibrer l'échelle."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union

    W, H = 1190.0, 842.0
    M = 72 / 0.0254 / 50  # dessin réel au 1:50
    ox, oy = 150.0, 120.0
    P = lambda x, y: (ox + x * M, oy + y * M)  # mètres → points (repère haut de page)
    ext = Polygon([P(0, 0), P(10, 0), P(10, 5), P(6, 5), P(6, 8), P(0, 8)])
    ep, iso = 0.30 * M, 0.12 * M
    i1 = ext.buffer(-ep, join_style="mitre")
    i2 = ext.buffer(-(ep + iso), join_style="mitre")
    trous = [box(*P(1, 7.5), *P(3, 8.5)),        # F1 façade bas (x 1→3, 2,00 m)
             box(*P(9.5, 1), *P(10.5, 2.2)),     # F2 façade droite (y 1→2,2, 1,20 m)
             box(*P(7, 4.5), *P(8, 5.5))]        # F3 façade du retrait (x 7→8, 1,00 m)
    trou = unary_union(trous)
    murs = ext.difference(i1).difference(trou)
    bande = i1.difference(i2).difference(trou)

    c = canvas.Canvas(str(chemin), pagesize=(W, H))
    Y = lambda y: H - y
    c.setFillColorRGB(0.35, 0.32, 0.18)  # aplat olive (style Charleville)
    for pg in getattr(murs, "geoms", [murs]):
        path = c.beginPath()
        xs = list(pg.exterior.coords)
        path.moveTo(xs[0][0], Y(xs[0][1]))
        for x, y in xs[1:]:
            path.lineTo(x, Y(y))
        path.close()
        c.drawPath(path, fill=1, stroke=0)
    c.setStrokeColorRGB(0.89, 0.68, 0.17)  # hachure jaune = isolant
    c.setLineWidth(0.24)
    x0, y0, x1, y1 = ext.bounds
    s = -(y1 - y0)
    while s < x1 - x0:
        seg = LineString([(x0 + s, y0), (x0 + s + (y1 - y0), y1)]).intersection(bande)
        for g in getattr(seg, "geoms", [seg]):
            if not g.is_empty and g.length > 0.2:
                (a, b), (cc, d) = g.coords[0], g.coords[-1]
                c.line(a, Y(b), cc, Y(d))
        s += 3.0
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    # lignes de cote
    c.setFont("Helvetica", 7)
    for (xa, ya), (xb, yb), txt in ((P(0, -1), P(10, -1), "10.00"), (P(0, 9), P(6, 9), "6.00")):
        c.line(xa, Y(ya), xb, Y(yb))
        c.drawCentredString((xa + xb) / 2, Y(ya - 3), txt)
    (xa, ya), (xb, yb) = P(-1, 0), P(-1, 8)
    c.line(xa, Y(ya), xb, Y(yb))
    c.saveState()
    c.translate(xa - 3, Y((ya + yb) / 2))
    c.rotate(90)
    c.drawCentredString(0, 0, "8.00")
    c.restoreState()
    # étiquettes de baies
    c.setFont("Helvetica", 6)
    for (xm, ym), lignes in ((P(2, 8.6), ("F1", "200 x 215ht.", "all.0")),
                             (P(11.3, 1.4), ("F2", "120 x 135ht.", "all.90")),
                             (P(7.5, 4.0), ("F3", "100 x 125ht.", "all.100"))):
        for i, t in enumerate(lignes):
            c.drawCentredString(xm, Y(ym + 7 * i), t)
    c.drawCentredString(*(lambda q: (q[0], Y(q[1])))(P(3, 3)), "Séjour")
    c.drawCentredString(*(lambda q: (q[0], Y(q[1] + 7)))(P(3, 3)), "30.5 m²")
    c.setFont("Helvetica", 9)
    c.drawString(*(lambda q: (q[0], Y(q[1])))(P(0, 10.5)), "R+0 projet")
    c.drawString(*(lambda q: (q[0], Y(q[1])))(P(0, 10.9)), "Ech : 1 : 100")
    # symbole du nord
    nx, ny = P(12, 9)
    r = 10.0
    pts = [(nx + r * math.cos(2 * math.pi * i / 36), ny + r * math.sin(2 * math.pi * i / 36)) for i in range(37)]
    for (a, b) in zip(pts, pts[1:]):
        c.line(a[0], Y(a[1]), b[0], Y(b[1]))
    t = math.radians(angle_nord_deg)
    ux, uy = math.sin(t), -math.cos(t)
    tip, tail = (nx + r * ux, ny + r * uy), (nx - r * ux, ny - r * uy)
    c.line(tail[0], Y(tail[1]), tip[0], Y(tip[1]))
    for sg in (1, -1):
        a = math.atan2(-uy, -ux) + sg * math.radians(30)
        c.line(tip[0], Y(tip[1]), tip[0] + 4 * math.cos(a), Y(tip[1] + 4 * math.sin(a)))
    c.showPage()
    c.save()


def generer_dossier_peint(chemin):
    """Dossier de 2 pages « style plan d'entraînement » : murs = grand aplat recouvert par l'intérieur blanc,
    baies = aplats de couleur sur le mur avec légende, dimensions écrites, « NORD ↑ », pas de mention d'échelle
    (dessin au 1:80) ; page 2 = notice avec tableaux (infos, parois, menuiseries, ponts thermiques)."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    W, H = 842.0, 595.0
    M = 72 / 0.0254 / 80
    c = canvas.Canvas(str(chemin) + ".p1.pdf", pagesize=(W, H))
    fonte = "Helvetica"
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(f):
            pdfmetrics.registerFont(TTFont("DejaVu", f))
            fonte = "DejaVu"
    Y = lambda y: H - y
    x0, y0, L, P, ep = 120.0, 130.0, 12.0 * M, 8.0 * M, 0.40 * M   # extérieur 12 x 8 m, mur 40 cm → intérieur 11,2 x 7,2
    c.setFillColorRGB(0.12, 0.6, 0.88)
    c.rect(x0, Y(y0 + P), L, P, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.rect(x0 + ep, Y(y0 + P - ep), L - 2 * ep, P - 2 * ep, fill=1, stroke=0)
    c.setFillColorRGB(1, 0.5, 0.15)  # fenêtres F 1,20 m : 2 au sud, 1 au nord
    for xm in (2.0, 7.0):
        c.rect(x0 + xm * M, Y(y0 + P), 1.2 * M, ep, fill=1, stroke=1)
    c.rect(x0 + 5.0 * M, Y(y0 + ep), 1.2 * M, ep, fill=1, stroke=1)
    c.setFillColorRGB(1, 0, 1)  # porte vitrée PV 1,80 m au sud
    c.rect(x0 + 9.5 * M, Y(y0 + P), 1.8 * M, ep, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(fonte, 14)
    c.drawString(60, Y(50), "Plan RDC · niveau +0,00")
    c.setFont(fonte, 8)
    c.drawString(60, Y(66), "Dimensions intérieures 11,20 × 7,20 m · hauteur d'étage 2,80 m")
    c.drawString(x0 + L / 2 - 20, Y(y0 - 20), "NORD ↑")
    c.drawString(x0 + L / 2 - 60, Y(y0 + P + 30), "12,00 m (extérieur) · 11,20 m (intérieur)")
    for i, (coul, txt) in enumerate((((0.12, 0.6, 0.88), "Mur 1a"), ((1, 0.5, 0.15), "Fenêtre F"), ((1, 0, 1), "Porte vitrée PV"))):
        c.setFillColorRGB(*coul)
        c.rect(60 + 120 * i, Y(560), 12, 8, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(78 + 120 * i, Y(558), txt)
    c.drawString(60, Y(578), "Menuiseries : fenêtres 1,20 × 1,35 m, porte vitrée 1,80 × 2,15 m.")
    c.showPage()
    c.save()

    st = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(chemin) + ".p2.pdf")
    style = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTNAME", (0, 0), (-1, -1), fonte)])
    t = lambda d: Table(d, style=style)
    doc.build([
        Paragraph("Notice thermique", st["Title"]),
        t([["Usage", "Maison individuelle"], ["Zone climatique / altitude", "H2b / 35 m"],
           ["Date du dépôt de PC", "15/09/2026"], ["Q4", "0,6 m³/(h.m²)"], ["Sref", "80,6 m²"]]),
        t([["Réf.", "Désignation", "Up W/(m².K)", "Composition"],
           ["1a", "Mur extérieur maçonnerie", "0,21", "Brique 200 mm, λ = 0,30 Laine de verre 120 mm, λ = 0,032"],
           ["2a", "Plancher bas", "0,18", "Dalle béton 200 mm PSE 120 mm, λ = 0,031"],
           ["3a", "Plafond sous combles", "0,11", "Laine soufflée 350 mm, λ = 0,040"]]),
        t([["Repère", "Désignation", "Vitrage", "Performance globale", "Quantité"],
           ["F", "Fenêtre 1,20 × 1,35 m", "g ≥ 0,48 ; TL ≥ 65 %", "Uw ≤ 1,30", "3 (4,86 m²)"],
           ["PV", "Porte vitrée 1,80 × 2,15 m", "g ≥ 0,50", "Uw ≤ 1,50", "1 (3,87 m²)"]]),
        t([["Liaison", "Ψ W/(m.K)", "Linéaire m", "Ψ × L W/K"], ["Plancher bas / mur", "0,40", "36,8", "14,72"],
           ["Total", "", "", "14,72"]]),
        Paragraph("6. Ventilation", st["Heading2"]),
        Paragraph("VMC simple flux hygroréglable type B.", st["Normal"]),
        Paragraph("7. Chauffage, ECS", st["Heading2"]),
        Paragraph("Chauffage : pompe à chaleur air/eau, émission par plancher chauffant. ECS : chauffe-eau thermodynamique 200 L.", st["Normal"]),
        Paragraph("Coupe : hauteur sous plafond 2,50 m.", st["Normal"]),
    ])
    from pypdf import PdfWriter
    w = PdfWriter()
    for part in (str(chemin) + ".p1.pdf", str(chemin) + ".p2.pdf"):
        w.append(part)
    with open(chemin, "wb") as fh:
        w.write(fh)


def generer_dxf(chemin):
    """Plan DXF « d'agence » : murs en simples traits sur le calque MURS (contours fermés), baies laissées en
    trous avec étiquettes sur le calque TEXTE, symbole du nord en bloc (cercle + flèche), titre de niveau.
    Maison 10 x 8 m extérieur, murs 30 cm, unités en mètres."""
    import ezdxf
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6
    for nom, couleur in (("MURS", 7), ("MENUISERIES", 4), ("TEXTE", 7), ("NORD", 7)):
        doc.layers.add(nom, color=couleur)
    msp = doc.modelspace()
    ext = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
    mur = ext.difference(ext.buffer(-0.30, join_style="mitre"))
    trous = [box(2, -0.1, 3.2, 0.4), box(6, -0.1, 8.0, 0.4), box(9.6, 5, 10.1, 6.0)]   # F1, PF1 (sud = bas), F2 (est)
    for pg in getattr(mur.difference(unary_union(trous)), "geoms", []):
        msp.add_lwpolyline(list(pg.exterior.coords), close=True, dxfattribs={"layer": "MURS"})
    for (xa, xb) in ((2, 3.2), (6, 8.0)):
        msp.add_line((xa, 0.15), (xb, 0.15), dxfattribs={"layer": "MENUISERIES"})
    msp.add_line((9.85, 5), (9.85, 6.0), dxfattribs={"layer": "MENUISERIES"})
    t = {"layer": "TEXTE", "height": 0.18}
    for x, y, lignes in ((2.6, -0.6, ("F1", "120 x 135ht.", "all.90")), (7.0, -0.6, ("PF1", "200 x 215ht.", "all.0")),
                         (10.6, 5.5, ("F2", "100 x 125ht.", "all.100"))):
        for i, l in enumerate(lignes):
            msp.add_text(l, dxfattribs={**t, "insert": (x - 0.4, y - 0.3 * i)})
    msp.add_text("RDC", dxfattribs={"layer": "TEXTE", "height": 0.4, "insert": (0, -2.2)})
    msp.add_text("Séjour", dxfattribs={**t, "insert": (3, 4)})
    msp.add_text("40.5 m²", dxfattribs={**t, "insert": (3, 3.7)})
    blk = doc.blocks.new("NORD")
    blk.add_circle((0, 0), 0.5)
    blk.add_line((0, -0.5), (0, 0.5))
    blk.add_line((0, 0.5), (-0.15, 0.25))
    blk.add_line((0, 0.5), (0.15, 0.25))
    msp.add_blockref("NORD", (12, 9), dxfattribs={"layer": "NORD"})
    doc.saveas(str(chemin))


def generer_notice_docx(chemin):
    import docx

    d = docx.Document()
    d.add_heading("Notice thermique", 1)
    t = d.add_table(rows=0, cols=2)
    for k, v in (("Usage", "Maison individuelle"), ("Zone climatique / altitude", "H3 / 120 m"), ("Date du dépôt de PC", "02/03/2027"),
                 ("Q4", "0,6 m³/(h.m²)")):
        r = t.add_row().cells
        r[0].text, r[1].text = k, v
    d.add_paragraph("")
    t = d.add_table(rows=1, cols=3)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text, t.rows[0].cells[2].text = "Réf.", "Désignation", "Up W/(m².K)"
    for ref, des, up in (("M1", "Mur extérieur béton ITE", "0,19"), ("T1", "Toiture combles perdus", "0,10")):
        r = t.add_row().cells
        r[0].text, r[1].text, r[2].text = ref, des, up
    d.add_paragraph("6. Ventilation")
    d.add_paragraph("VMC simple flux hygroréglable B.")
    d.add_paragraph("7. Chauffage")
    d.add_paragraph("Chauffage par pompe à chaleur air/eau, émission par plancher chauffant.")
    d.save(str(chemin))


def generer_notice_xlsx(chemin):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Menuiseries"
    ws.append(["Repère", "Désignation", "Performance globale", "Quantité"])
    ws.append(["F", "Fenêtre 1,20 × 1,35 m g ≥ 0,45", "Uw ≤ 1,20", "2 (3,24 m²)"])
    ws.append(["PF", "Porte-fenêtre 2,00 × 2,15 m g ≥ 0,50", "Uw ≤ 1,40", "1 (4,30 m²)"])
    wb.save(str(chemin))
