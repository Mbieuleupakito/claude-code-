"""Localisation du projet → zone climatique (sans Internet) et altitude (en ligne, facultatif).

Zone climatique : tableau officiel par département (arrêté du 4 août 2021, annexe ; même découpage que la RT 2012).
Le département vient du code postal, d'un « (38) » ou du nom du département trouvés dans le dossier ; l'adresse du
chantier est préférée à celle de l'architecte ou du bureau d'études (cartouche).

Altitude : Base Adresse Nationale (commune → coordonnées) puis altimétrie IGN, services publics de l'État. Seuls la
commune et le code postal sont envoyés, jamais l'adresse complète ni les plans. Désactivable : RE2020_HORS_LIGNE=1.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from functools import lru_cache

from .trace import val

ZONES_PAR_DEPARTEMENT = {
    "H1a": "02 14 27 59 60 61 62 75 76 77 78 80 91 92 93 94 95",
    "H1b": "08 10 21 25 39 51 52 54 55 57 58 67 68 70 71 88 89 90",
    "H1c": "01 03 05 15 19 23 38 42 43 63 69 73 74 87",
    "H2a": "22 29 35 50 56",
    "H2b": "16 17 18 28 36 37 41 44 45 49 53 72 79 85 86",
    "H2c": "09 12 24 31 32 33 40 46 47 64 65 81 82",
    "H2d": "04 07 26 48 84",
    "H3": "06 11 13 2A 2B 30 34 66 83",
}
ZONE_DEPARTEMENT = {d: z for z, ds in ZONES_PAR_DEPARTEMENT.items() for d in ds.split()}

DEPARTEMENTS = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence", "05": "Hautes-Alpes", "06": "Alpes-Maritimes",
    "07": "Ardèche", "08": "Ardennes", "09": "Ariège", "10": "Aube", "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône",
    "14": "Calvados", "15": "Cantal", "16": "Charente", "17": "Charente-Maritime", "18": "Cher", "19": "Corrèze",
    "2A": "Corse-du-Sud", "2B": "Haute-Corse", "21": "Côte-d'Or", "22": "Côtes-d'Armor", "23": "Creuse", "24": "Dordogne",
    "25": "Doubs", "26": "Drôme", "27": "Eure", "28": "Eure-et-Loir", "29": "Finistère", "30": "Gard", "31": "Haute-Garonne",
    "32": "Gers", "33": "Gironde", "34": "Hérault", "35": "Ille-et-Vilaine", "36": "Indre", "37": "Indre-et-Loire", "38": "Isère",
    "39": "Jura", "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire", "44": "Loire-Atlantique",
    "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne", "48": "Lozère", "49": "Maine-et-Loire", "50": "Manche", "51": "Marne",
    "52": "Haute-Marne", "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse", "56": "Morbihan", "57": "Moselle",
    "58": "Nièvre", "59": "Nord", "60": "Oise", "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dôme",
    "64": "Pyrénées-Atlantiques", "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales", "67": "Bas-Rhin", "68": "Haut-Rhin",
    "69": "Rhône", "70": "Haute-Saône", "71": "Saône-et-Loire", "72": "Sarthe", "73": "Savoie", "74": "Haute-Savoie",
    "75": "Paris", "76": "Seine-Maritime", "77": "Seine-et-Marne", "78": "Yvelines", "79": "Deux-Sèvres", "80": "Somme",
    "81": "Tarn", "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse", "85": "Vendée", "86": "Vienne", "87": "Haute-Vienne",
    "88": "Vosges", "89": "Yonne", "90": "Territoire de Belfort", "91": "Essonne", "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis", "94": "Val-de-Marne", "95": "Val-d'Oise",
}


def _sa(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()).strip()


NOMS_DEPARTEMENTS = sorted(((_sa(n), c) for c, n in DEPARTEMENTS.items()), key=lambda x: -len(x[0]))


def departement_du_code_postal(cp: str) -> str | None:
    cp = cp.strip()
    if not re.fullmatch(r"\d{5}", cp) or cp.startswith(("97", "98", "00")):
        return None
    if cp.startswith("20"):
        return "2A" if int(cp) < 20200 else "2B"
    return cp[:2] if cp[:2] in DEPARTEMENTS else None


MOTS_CHANTIER = r"chantier|projet|terrain|parcelle|construction|operation|situation|lieu|adresse du (?:projet|terrain)|commune"
MOTS_INTERVENANTS = (r"architect|atelier|agence|bureau d.?etudes|\bbet\b|maitre d.?(?:oeuvre|ouvrage)|cabinet|sarl|sas\b|"
                     r"\btel\b|telephone|www\.|@|siret|deep ?watt|contact|editeur|izuba")


def candidats(texte: str, source: str, poids: float = 1.0) -> list[dict]:
    """Repère codes postaux « 38420 DOMÈNE », « Grenoble (38) », noms de départements, avec un score de confiance
    (adresse du chantier > texte neutre > coordonnées d'un intervenant)."""
    out = []
    for ligne in texte.splitlines():
        l_sa = _sa(ligne)
        bonus = 2.0 if re.search(MOTS_CHANTIER, l_sa) else 0.0
        malus = 3.0 if re.search(MOTS_INTERVENANTS, l_sa) else 0.0
        score = poids + bonus - malus
        for m in re.finditer(r"\b(\d{5})\s+([A-ZÀ-Ÿa-zà-ÿ][\wÀ-ÿ'’ -]{1,40}?)(?=[,;:.·)\n]|$|\s{2,}|\s+(?:tel|cedex|france|adresse|t[ée]l)\b)", ligne, re.I):
            d = departement_du_code_postal(m.group(1))
            if d:
                out.append({"departement": d, "code_postal": m.group(1), "commune": m.group(2).strip().title(),
                            "score": score + 1.0, "source": source, "extrait": ligne.strip()[:120]})
        for m in re.finditer(r"([A-ZÀ-Ÿ][\wÀ-ÿ'’ -]{1,40}?)\s*\((\d{2}|2[AB])\)", ligne):
            if m.group(2) in DEPARTEMENTS:
                out.append({"departement": m.group(2), "code_postal": None, "commune": m.group(1).strip().title(),
                            "score": score + 0.5, "source": source, "extrait": ligne.strip()[:120]})
        for nom, code in NOMS_DEPARTEMENTS:
            if re.search(rf"\b{re.escape(nom)}\b", l_sa) and not re.search(r"\b(?:rue|avenue|boulevard|chemin|route|place) ", l_sa):
                out.append({"departement": code, "code_postal": None, "commune": None, "score": score - 0.5,
                            "source": source, "extrait": ligne.strip()[:120]})
                break
    return out


def _nettoyer_commune(c: str | None) -> str | None:
    if not c:
        return None
    c = re.sub(r"^(?:adresse|commune|lieu|situation|localisation|projet|terrain)\s*:?\s*", "", c.strip(), flags=re.I)
    return c.strip(" -,") or None


def choisir(cands: list[dict]) -> dict | None:
    """Département le mieux étayé (somme des scores), et la commune la plus précise pour ce département."""
    if not cands:
        return None
    total: dict[str, float] = {}
    for c in cands:
        total[c["departement"]] = total.get(c["departement"], 0) + max(c["score"], 0.1)
    dep = max(total, key=total.get)
    du_dep = sorted((c for c in cands if c["departement"] == dep), key=lambda c: (-c["score"], c["code_postal"] is None))
    meilleur = du_dep[0]
    commune = next((c for c in du_dep if c["commune"] and c["code_postal"]), None) or next((c for c in du_dep if c["commune"]), None)
    autres = sorted({c["departement"] for c in cands} - {dep})
    return {"departement": dep, "nom_departement": DEPARTEMENTS[dep], "zone": ZONE_DEPARTEMENT[dep],
            "commune": _nettoyer_commune(commune["commune"]) if commune else None, "code_postal": commune["code_postal"] if commune else None,
            "source": meilleur["source"], "extrait": meilleur["extrait"],
            "confiance": "haute" if meilleur["score"] >= 2 else "moyenne", "autres_departements": autres}


# --------------------------------------------------------------------------- altitude en ligne (services de l'État)

def _get_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"User-Agent": "re2020-assistant"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


@lru_cache(maxsize=256)
def altitude_commune(commune: str, code_postal: str | None) -> dict | None:
    """{altitude_m, lon, lat, commune, source} ou None (hors ligne, introuvable, service indisponible)."""
    if os.environ.get("RE2020_HORS_LIGNE") == "1" or not commune:
        return None
    q = {"q": commune, "type": "municipality", "limit": 1, **({"postcode": code_postal} if code_postal else {})}
    feat = None
    for base in ("https://data.geopf.fr/geocodage/search", "https://api-adresse.data.gouv.fr/search/"):
        try:
            r = _get_json(base + "?" + urllib.parse.urlencode(q))
            if r.get("features"):
                feat = r["features"][0]
                break
        except Exception:
            continue
    if not feat:
        return None
    lon, lat = feat["geometry"]["coordinates"][:2]
    try:
        r = _get_json("https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json?"
                      + urllib.parse.urlencode({"lon": lon, "lat": lat, "resource": "ign_rge_alti_wld", "zonly": "true"}))
        z = r["elevations"][0]
        z = z["z"] if isinstance(z, dict) else z
    except Exception:
        return None
    if z is None or z < -100:
        return None
    nom = feat.get("properties", {}).get("city") or feat.get("properties", {}).get("name") or commune
    return {"altitude_m": round(float(z)), "lon": lon, "lat": lat, "commune": nom,
            "source": "altimétrie IGN au centre de la commune (Base Adresse Nationale)"}


def localiser(cands: list[dict]) -> dict:
    """``cands`` : candidats() de tout le dossier. Retourne lieu (lu), zone (déduite), altitude (en ligne si possible)."""
    choix = choisir(cands)
    if not choix:
        return {}
    lieu = " ".join(x for x in (choix["code_postal"], choix["commune"]) if x) or choix["nom_departement"]
    out = {
        "lieu": val(f"{lieu} ({choix['nom_departement']}, {choix['departement']})", "lu", f"{choix['source']} : « {choix['extrait']} »",
                    choix["confiance"]),
        "zone": val(choix["zone"], "déduit", f"département {choix['departement']} ({choix['nom_departement']}) → tableau des zones "
                    "climatiques de l'arrêté du 4 août 2021", choix["confiance"]),
        "departement": choix["departement"],
    }
    if choix["autres_departements"]:
        out["note"] = (f"autres départements cités dans le dossier : {', '.join(choix['autres_departements'])} "
                       "(adresse d'un intervenant ?) — vérifier la zone")
    alt = altitude_commune(choix["commune"], choix["code_postal"]) if choix["commune"] else None
    if alt:
        out["altitude_m"] = val(alt["altitude_m"], "déduit", f"{alt['source']} : {alt['commune']}", "moyenne", "m",
                                note="altitude au centre de la commune : vérifier celle du terrain si la commune est vallonnée")
    return out
