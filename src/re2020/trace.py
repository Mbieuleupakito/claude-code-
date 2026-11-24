"""Traçabilité des valeurs : chaque donnée sortie par l'outil porte son origine (CLAUDE.md, règle 1).

- ``lu``      : lu tel quel sur le plan / document (texte, cote, étiquette) ;
- ``déduit``  : calculé à partir de la géométrie, d'un catalogue ou d'autres valeurs ;
- ``supposé`` : hypothèse par défaut, à confirmer par le thermicien.
"""
from __future__ import annotations

TAGS = ("lu", "déduit", "supposé")
CONFIANCES = ("haute", "moyenne", "faible")


def val(valeur, tag: str, source: str, confiance: str = "moyenne", unite: str | None = None, **extra) -> dict:
    """Construit une valeur tracée (dict sérialisable en JSON)."""
    if tag not in TAGS:
        raise ValueError(f"tag inconnu : {tag!r} (attendu : {TAGS})")
    if confiance not in CONFIANCES:
        raise ValueError(f"confiance inconnue : {confiance!r} (attendu : {CONFIANCES})")
    if isinstance(valeur, float):
        valeur = round(valeur, 3)
    out = {"valeur": valeur}
    if unite:
        out["unite"] = unite
    out.update(tag=tag, source=source, confiance=confiance)
    out.update(extra)
    return out
