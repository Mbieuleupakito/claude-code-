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
