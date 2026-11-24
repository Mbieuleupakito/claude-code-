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
