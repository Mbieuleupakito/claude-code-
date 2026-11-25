"""Murs, enveloppe et façades d'une vue en plan (shapely).

- Les murs sont les formes remplies (rectangles ou polygones quelconques) dont l'épaisseur moyenne
  2·aire/périmètre est celle d'un mur (4 à 80 cm).
- Les vues en plan (niveaux) sont les groupes de murs proches ; l'enveloppe est le contour extérieur
  des murs après « fermeture » morphologique (qui referme les ouvertures coupées dans les murs).
- Chaque arête du contour est une façade : normale extérieure, épaisseur de la couche pleine,
  bandes hachurées extérieure / intérieure (isolant probable), ouvertures.
"""
from __future__ import annotations

import math
import statistics as st
from collections import Counter
from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

# --------------------------------------------------------------------------- outils


def couleur(o):
    c = o.get("non_stroking_color") if o.get("fill") else o.get("stroking_color")
    if isinstance(c, (list, tuple)):
        return tuple(round(float(v), 2) for v in c)
    return (c,)


def _vegetal(c) -> bool:
    """Aplat nettement vert : arbres, haies, pelouses (jamais des murs)."""
    nums = [v for v in c if isinstance(v, (int, float))]
    # un vert presque noir (poché AutoCAD « 0,39,8 ») n'est pas de la végétation
    return len(nums) == 3 and nums[1] >= 0.3 and nums[1] > nums[0] + 0.08 and nums[1] > nums[2] + 0.08


def _clair(c) -> bool:
    nums = [v for v in c if isinstance(v, (int, float))]
    if not nums:
        return True
    if len(nums) == 4:  # CMJN
        return max(nums) < 0.1
    return min(nums) > 0.9


def fusion(intervalles, tol=0.5):
    out = []
    for a, b in sorted(intervalles):
        if out and a <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def quantile(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, int(q * (len(vals) - 1))))]


def polygones(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


# --------------------------------------------------------------------------- formes remplies → murs


def _sous_chemins(curve):
    """Découpe le chemin d'une courbe pdfplumber en sous-chemins (listes de points)."""
    path = curve.get("path")
    if not path:
        return [curve["pts"]]
    out, cur = [], []
    for op in path:
        kind, pts = op[0], op[1:]
        if kind == "m":
            if len(cur) >= 3:
                out.append(cur)
            cur = [pts[0]]
        elif kind in ("l", "c", "v", "y"):
            cur.append(pts[-1])
        elif kind == "h" and len(cur) >= 3:
            out.append(cur)
            cur = []
    if len(cur) >= 3:
        out.append(cur)
    return out


def _polygones_remplis(page):
    """Toutes les formes remplies (rectangles et chemins) : [(polygone, couleur, claire ?)]."""
    out = []
    for r in page.rects:
        if r.get("fill") and r["width"] > 0 and r["height"] > 0:
            c = couleur(r)
            out.append((box(r["x0"], r["top"], r["x1"], r["bottom"]), c, _clair(c)))
    for cv in page.curves:
        if not cv.get("fill"):
            continue
        c = couleur(cv)
        geom = None
        for sp in _sous_chemins(cv):
            pg = Polygon(sp).buffer(0)
            if pg.is_empty:
                continue
            geom = pg if geom is None else geom.symmetric_difference(pg)  # règle pair-impair
        for pg in polygones(geom) if geom is not None else []:
            if pg.area > 0:
                out.append((pg, c, _clair(c)))
    return out


def formes_remplies(page) -> list[tuple[Polygon, tuple]]:
    """Formes remplies foncées, « peintes » : une forme claire posée DANS une forme foncée la recouvre
    (sinon elle serait invisible). Ex. : grand aplat bleu + intérieur blanc = anneau de murs."""
    toutes = _polygones_remplis(page)
    claires = [pg for pg, _, clair in toutes if clair]
    out = []
    for pg, c, clair in toutes:
        if clair:
            continue
        dedans = [cl for cl in claires if cl.area < pg.area * 0.999 and cl.within(pg.buffer(0.5))]
        if dedans:
            pg = pg.difference(unary_union(dedans))
        for morceau in polygones(pg):
            if morceau.area > 0:
                out.append((morceau, c))
    return out


def epaisseur_moyenne(pg: Polygon) -> float:
    return 2 * pg.area / pg.length if pg.length else 0.0


def murs(formes, k, ep_min=0.04, ep_max=0.8, long_min=0.4) -> list[Polygon]:
    """Formes dont l'épaisseur moyenne est celle d'un mur (en m, via k = m/pt)."""
    # aplats d'une même couleur qui se touchent = un seul mur (AutoCAD découpe souvent le poché en bandes fines)
    par_couleur: dict = {}
    for pg, c in formes:
        if not _vegetal(c):  # arbres, haies, pelouses : jamais des murs (mais une baie peut être un aplat vert)
            par_couleur.setdefault(c, []).append(pg)
    fusionnes = []
    for c, pgs in par_couleur.items():
        if len(pgs) > 1:
            u = unary_union([g.buffer(0.3, join_style="mitre") for g in pgs]).buffer(-0.3, join_style="mitre")
            fusionnes += [(g, c) for g in polygones(u)]
        else:
            fusionnes += [(pgs[0], c)]
    cands = []
    for pg, c in fusionnes:
        ep = epaisseur_moyenne(pg) * k
        x0, y0, x1, y1 = pg.bounds
        if ep_min <= ep <= ep_max and max(x1 - x0, y1 - y0) * k >= long_min:
            cands.append((pg, c))
    # le poché des murs est la couleur dominante ; les couleurs marginales (flèches de coupe, repères NGF,
    # symboles) sont écartées. Plusieurs matériaux de murs de couleurs différentes restent acceptés.
    aire: dict = {}
    for pg, c in cands:
        aire[c] = aire.get(c, 0.0) + pg.area
    if not aire:
        return []
    maxi = max(aire.values())
    return [pg for pg, c in cands if aire[c] >= 0.2 * maxi]


def fermeture(geom, r):
    return geom.buffer(r, join_style="mitre", mitre_limit=10).buffer(-r, join_style="mitre", mitre_limit=10)


# --------------------------------------------------------------------------- vues en plan


@dataclass
class Facade:
    p: tuple
    q: tuple
    t: tuple  # direction unitaire p → q
    n: tuple  # normale extérieure unitaire (repère page)
    longueur_pt: float
    ep_pt: float = 0.0
    ext_pt: float = 0.0
    int_pt: float = 0.0
    ouvertures: list = field(default_factory=list)  # [(a, b)] le long de p → q, en pt
    marqueurs: list = field(default_factory=list)   # [(a, b, couleur)] baies dessinées en aplat de couleur
    couverture: float = 1.0

    def local(self, x, y):
        dx, dy = x - self.p[0], y - self.p[1]
        return dx * self.t[0] + dy * self.t[1], dx * self.n[0] + dy * self.n[1]

    def point(self, a, d=0.0):
        return (self.p[0] + a * self.t[0] + d * self.n[0], self.p[1] + a * self.t[1] + d * self.n[1])

    @property
    def nom_cote(self) -> str | None:
        nx, ny = self.n
        for nom, (ax, ay) in {"haut": (0, -1), "droite": (1, 0), "bas": (0, 1), "gauche": (-1, 0)}.items():
            if nx * ax + ny * ay > 0.97:
                return nom
        return None


@dataclass
class Vue:
    murs: list
    enveloppe: Polygon
    facades: list
    interieur: Polygon | None = None
    convexes: int = 0
    concaves: int = 0
    refends: int = 0
    ep_struct_pt: float = 0.0
    ep_ext_pt: float = 0.0
    ep_int_pt: float = 0.0


def vues_en_plan(murs_pg, k, fermeture_m=1.6, part_min=0.15, surface_min_m2=9.0) -> list[Vue]:
    """Regroupe les murs en vues (niveaux) et calcule l'enveloppe de chacune."""
    if not murs_pg:
        return []
    r = fermeture_m / k
    union = unary_union(murs_pg)
    groupes = polygones(unary_union([g.buffer(r) for g in polygones(union)]))
    vues = []
    for zone in groupes:
        membres = [g for g in polygones(union) if g.intersects(zone)]
        plus_grand = max(g.area for g in membres)
        gros = [g for g in membres if g.area >= part_min * plus_grand]
        coque = unary_union(gros).convex_hull.buffer(0.3 / k)
        # les petits morceaux gardés sont ceux DANS l'emprise (tronçon de mur entre deux baies) ;
        # ceux dehors (muret de terrasse, clôture) sont écartés
        gardes = gros + [g for g in membres if g.area < part_min * plus_grand and g.intersection(coque).area >= 0.8 * g.area]
        if not gardes:
            continue
        env = _enveloppe(gardes, k, r)
        if env is None:
            continue
        if env.area * k * k < surface_min_m2 or equerre(env) < 0.6:
            continue  # trop petit, ou contour non orthogonal (arbre, talus, courbe de niveau)
        murs_vue = [m for m in murs_pg if m.intersects(env.buffer(0.5))]
        vues.append(Vue(murs=murs_vue, enveloppe=env, facades=_facades(env, k)))
    return vues


def _enveloppe(gardes, k, r) -> Polygon | None:
    """Contour extérieur des murs fermé par une fermeture morphologique. Une grande baie (coulissant de 4 m) laisse
    le contour ouvert : on élargit alors la fermeture jusqu'à obtenir un anneau qui entoure les murs."""
    u = unary_union(gardes)
    premier = None
    for f in (1.0, 1.5, 2.0, 2.5, 3.0):
        pgs = sorted(polygones(fermeture(u, r * f)), key=lambda g: g.area, reverse=True)
        if not pgs:
            continue
        env = Polygon(pgs[0].exterior).simplify(0.3)
        premier = premier or env
        # anneau fermé : l'enveloppe contient presque tous les murs et couvre l'essentiel de leur emprise
        # (un contour resté ouvert ne garde qu'un « C » mince le long des murs)
        if env.intersection(u).area >= 0.9 * u.area and env.area >= 0.5 * u.convex_hull.area:
            return env
    return premier


def equerre(env: Polygon) -> float:
    """Part du contour (en longueur) parallèle ou perpendiculaire à la direction principale du bâtiment."""
    coords = list(env.exterior.coords)
    segs = [(math.hypot(b[0] - a[0], b[1] - a[1]), math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90)
            for a, b in zip(coords, coords[1:]) if a != b]
    if not segs:
        return 0.0
    total = sum(l for l, _ in segs)
    meilleur = 0.0
    for _, a0 in segs:
        ok = sum(l for l, a in segs if min(abs(a - a0), 90 - abs(a - a0)) < 4)
        meilleur = max(meilleur, ok / total)
    return meilleur


def _facades(env: Polygon, k, long_min_m=0.5) -> list[Facade]:
    coords = list(env.exterior.coords)[:-1]
    # fusion des sommets presque alignés
    pts = []
    for i, c in enumerate(coords):
        a, b = coords[i - 1], coords[(i + 1) % len(coords)]
        v1 = (c[0] - a[0], c[1] - a[1])
        v2 = (b[0] - c[0], b[1] - c[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) > 1e-3 * math.hypot(*v1) * math.hypot(*v2):
            pts.append(c)
    out = []
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        lg = math.hypot(q[0] - p[0], q[1] - p[1])
        if lg * k < long_min_m:
            continue
        t = ((q[0] - p[0]) / lg, (q[1] - p[1]) / lg)
        n = (t[1], -t[0])
        m = ((p[0] + q[0]) / 2 + n[0], (p[1] + q[1]) / 2 + n[1])
        if env.contains(Point(m)):
            n = (-n[0], -n[1])
        out.append(Facade(p=p, q=q, t=t, n=n, longueur_pt=lg))
    return out


def coins(env: Polygon, k: float | None = None, court_m: float = 0.5) -> tuple[int, int]:
    """(angles saillants, angles rentrants) du contour. Un décroché de moins de ``court_m`` (débord de poché à un
    angle : un saillant + un rentrant collés) ne compte pas."""
    coords = list(env.exterior.coords)[:-1]
    n = len(coords)
    signe = 1 if env.exterior.is_ccw else -1
    tours = []
    for i, c in enumerate(coords):
        a, b = coords[i - 1], coords[(i + 1) % n]
        v1, v2 = (c[0] - a[0], c[1] - a[1]), (b[0] - c[0], b[1] - c[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        norme = math.hypot(*v1) * math.hypot(*v2) or 1.0
        tours.append(0 if abs(cross) / norme < math.sin(math.radians(20)) else (1 if cross * signe > 0 else -1))
    if k:
        for i in range(n):  # arête i → i+1 courte entre deux tours opposés : décroché parasite
            j = (i + 1) % n
            if math.dist(coords[i], coords[j]) * k < court_m and tours[i] * tours[j] == -1:
                tours[i] = tours[j] = 0
    return sum(t == 1 for t in tours), sum(t == -1 for t in tours)


def coins_facades(facades: list) -> tuple[int, int]:
    """Angles comptés entre façades consécutives (façades < 50 cm déjà écartées : les débords de poché ne comptent
    pas). Deux façades parallèles qui se suivent = petit décroché, pas d'angle."""
    conv = conc = 0
    for i, f in enumerate(facades):
        g = facades[(i + 1) % len(facades)]
        cross = f.t[0] * g.t[1] - f.t[1] * g.t[0]
        if abs(cross) < math.sin(math.radians(20)):
            continue
        # normale extérieure : on tourne vers l'extérieur (angle rentrant) si la façade suivante part du côté de n
        if g.t[0] * f.n[0] + g.t[1] * f.n[1] > 0:
            conc += 1
        else:
            conv += 1
    return conv, conc


# --------------------------------------------------------------------------- analyse des façades


def couleur_hachures(lignes, env: Polygon, k):
    zone = env.buffer(1.0 / k)
    c = Counter()
    for o in lignes:
        dx, dy = o["x1"] - o["x0"], o["bottom"] - o["top"]
        if dx > 0.3 and dy > 0.3 and 0.4 < dx / dy < 2.5 and max(dx, dy) * k < 0.5:
            if zone.contains(Point((o["x0"] + o["x1"]) / 2, (o["top"] + o["bottom"]) / 2)):
                c[couleur(o)] += 1
    return c.most_common(1)[0][0] if c else None


def _seg(o):
    (x0, y0), (x1, y1) = o["pts"][0], o["pts"][-1]
    return x0, y0, x1, y1


def analyser_facades(vue: Vue, hachures, k, ouverture_min_m=0.25):
    union = unary_union(vue.murs)
    marge = 0.5 / k
    for f in vue.facades:
        # épaisseur de la couche pleine : rayons vers l'intérieur
        eps = []
        for s in range(1, 10):
            a = f.longueur_pt * s / 10
            ray = LineString([f.point(a, 0.5), f.point(a, -1.0 / k)])
            inter = ray.intersection(union)
            parts = [g for g in getattr(inter, "geoms", [inter]) if not g.is_empty and g.length > 0]
            if parts:
                face = Point(f.point(a, 0))
                first = min(parts, key=lambda g: g.distance(face))
                if first.distance(face) < 1.0:  # le rayon entre dans le mur dès la façade (pas une ouverture)
                    eps.append(first.length)
        f.ep_pt = st.median(eps) if eps else 0.0
        # couverture de la couche pleine le long de la façade → ouvertures dans le mur
        prof = min(0.05 / k, f.ep_pt / 2) if f.ep_pt else 0.05 / k
        bande = LineString([f.point(0, -prof), f.point(f.longueur_pt, -prof)])
        inter = bande.intersection(union)
        iv = []
        for g in getattr(inter, "geoms", [inter]):
            if g.is_empty or g.length == 0:
                continue
            a0, _ = f.local(*g.coords[0])
            a1, _ = f.local(*g.coords[-1])
            iv.append((min(a0, a1), max(a0, a1)))
        iv = fusion(iv)
        f.couverture = sum(b - a for a, b in iv) / f.longueur_pt
        gaps = [(a[1], b[0]) for a, b in zip(iv, iv[1:]) if (b[0] - a[1]) * k >= ouverture_min_m]
        if f.couverture < 0.15 and f.longueur_pt * k >= 0.6:
            # tronçon de façade presque sans mur (refermé par l'enveloppe) : grande baie vitrée ; seuls les bouts de
            # mur des angles voisins sont retirés
            bornes = [0.0] + [x for a, b in iv for x in (a, b)] + [f.longueur_pt]
            gaps = [(a, b) for a, b in zip(bornes[::2], bornes[1::2]) if (b - a) * k >= ouverture_min_m]
        # bandes hachurées
        d1s, d0s, locs = [], [], []
        for h in hachures:
            x0, y0, x1, y1 = _seg(h)
            a0, d0 = f.local(x0, y0)
            a1, d1 = f.local(x1, y1)
            a0, a1, d0, d1 = min(a0, a1), max(a0, a1), min(d0, d1), max(d0, d1)
            if a1 < -0.5 or a0 > f.longueur_pt + 0.5:
                continue
            locs.append((a0, a1, d0, d1))
            if marge <= a0 and a1 <= f.longueur_pt - marge:
                if d0 >= -0.5 and d1 <= 0.6 / k:
                    d1s.append(d1)
                elif d1 <= -f.ep_pt + 0.5 and d0 >= -f.ep_pt - 0.3 / k:
                    d0s.append(d0)
        f.ext_pt = max(0.0, quantile(d1s, 0.95)) if len(d1s) >= 3 else 0.0
        f.int_pt = max(0.0, -f.ep_pt - quantile(d0s, 0.05)) if len(d0s) >= 3 else 0.0
        if f.ext_pt > 0:  # interruptions de la bande isolant extérieure
            ivh = fusion([(a0, a1) for (a0, a1, d0, d1) in locs if d0 >= -0.5 and d1 <= f.ext_pt + 0.5])
            gaps += [(a[1], b[0]) for a, b in zip(ivh, ivh[1:]) if (b[0] - a[1]) * k >= ouverture_min_m
                     and 0 < a[1] and b[0] < f.longueur_pt]
        f.ouvertures = [tuple(g) for g in fusion(gaps, tol=0.0)] if gaps else []

    # synthèse de la vue
    poids = [f.longueur_pt for f in vue.facades]

    def moy(attr):
        return sum(getattr(f, attr) * w for f, w in zip(vue.facades, poids)) / sum(poids) if poids else 0.0

    vue.ep_struct_pt = st.median([f.ep_pt for f in vue.facades]) if vue.facades else 0.0
    vue.ep_ext_pt = moy("ext_pt")
    vue.ep_int_pt = moy("int_pt")
    d = vue.ep_struct_pt + vue.ep_int_pt
    inter = vue.enveloppe.buffer(-d, join_style="mitre", mitre_limit=10) if d > 0 else vue.enveloppe
    vue.interieur = max(polygones(inter), key=lambda g: g.area) if polygones(inter) else None
    vue.convexes, vue.concaves = coins_facades(vue.facades) if len(vue.facades) >= 3 else coins(vue.enveloppe, k)
    vue.refends = _refends(vue, k)


def _refends(vue: Vue, k, ep_min_m=0.12) -> int:
    """Nombre de jonctions refend (mur intérieur épais) / façade."""
    if vue.interieur is None:
        return 0
    ceinture = vue.enveloppe.difference(vue.interieur.buffer(-0.02 / k))
    n = 0
    for m in vue.murs:
        if epaisseur_moyenne(m) * k < ep_min_m:
            continue
        coeur = m.intersection(vue.interieur.buffer(-0.05 / k))
        if coeur.is_empty or coeur.area < 0.5 * m.area:
            continue  # mur de façade, pas un refend
        contact = m.buffer(0.05 / k).intersection(ceinture)
        n += len(polygones(contact))
    return n


def couleur_murs(vue: Vue, formes) -> tuple | None:
    """Couleur dominante (en surface) des murs de la vue."""
    aires = Counter()
    for pg, c in formes:
        inter = pg.intersection(vue.enveloppe)
        if not inter.is_empty:
            aires[c] += inter.area
    return aires.most_common(1)[0][0] if aires else None


def marqueurs_ouvertures(vue: Vue, formes, k, couleur_mur) -> None:
    """Baies dessinées comme des aplats de couleur posés SUR le mur (au lieu d'un trou) : chaque aplat
    d'une autre couleur que le mur, qui traverse l'épaisseur du mur, devient une ouverture de la façade."""
    for pg, c in formes:
        if c == couleur_mur:
            continue
        x0, y0, x1, y1 = pg.bounds
        if max(x1 - x0, y1 - y0) * k > 6 or not pg.intersects(vue.enveloppe):
            continue
        meilleur = None
        for f in vue.facades:
            pts = [f.local(x, y) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
            a0, a1 = min(p[0] for p in pts), max(p[0] for p in pts)
            d0, d1 = min(p[1] for p in pts), max(p[1] for p in pts)
            ep = f.ep_pt or 0.2 / k
            if a1 < 0 or a0 > f.longueur_pt or d0 < -ep - 2 or d1 > ep + 2:
                continue
            if (min(d1, 0.5) - max(d0, -ep)) < 0.5 * ep:  # ne traverse pas le mur
                continue
            recouvrement = min(a1, f.longueur_pt) - max(a0, 0)
            if meilleur is None or recouvrement > meilleur[0]:
                meilleur = (recouvrement, f, max(a0, 0), min(a1, f.longueur_pt))
        if meilleur and meilleur[0] * k >= 0.25:
            _, f, a0, a1 = meilleur
            f.marqueurs.append((a0, a1, c))
            f.ouvertures = [tuple(g) for g in fusion(list(f.ouvertures) + [(a0, a1)], tol=0.0)]
