"""Soort en vorm van een factcheck, alleen waar het zeker is (PLAN #34.2ak, SPECS E9.S19).

Geen taalmodel: de voormeting liet zien dat de soort uit de bewering alleen niet te lezen is (BENCHMARK §260). Wat wel
zeker is:

- *de soort volgens de redactie*: als de woorden van een redactie haar noemen (*Altered*, *Missing context*, *Satire*,
  *Fabricated*, *AI-generated*). Alleen woorden die op de nagelezen lijst staan tellen
  (`docs/steekproeven/34.2ak-soortwoorden.json`), na dezelfde normalisatie als de vertaalde woorden van een redactie
  (`oordeellezer.sleutel`). Bij meer soorten telt de meest bijzondere (`SOORTEN` op volgorde).
- *de vorm*: *video* of *beeld* als de Engelse tekst van de bewering het zegt (de bewering zelf als die Engels is,
  anders de Engelse versie): video 191 van 198 gelijk aan het artikel, beeld 140 van 147. Noemt ze beide, dan video.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from doublecheck.oordeellezer import sleutel as woordsleutel

WORTEL = Path(__file__).resolve().parent.parent
WOORDEN = WORTEL / "docs" / "steekproeven" / "34.2ak-soortwoorden.json"
VERSIE = "soortwoorden-v2"
SOORTEN = ("ai", "bewerkt", "satire", "verzonnen", "context")     # de meest bijzondere eerst
VORMEN = ("video", "beeld")
_VIDEO = re.compile(r"\b(videos?|clips?|footage)\b")
_BEELD = re.compile(r"\b(photos?|photographs?|pictures?|pics?|images?|screenshots?)\b")


def lees_woorden(pad: str | Path = WOORDEN) -> dict[str, str]:
    """De nagelezen woorden: per sleutel een soort uit `SOORTEN`; wat *geen* soort noemt, valt weg."""
    d = json.loads(Path(pad).read_text(encoding="utf-8"))
    uit = {}
    for sleutel, w in d["woorden"].items():
        if w["soort"] not in SOORTEN + ("geen",):
            raise ValueError(f"onbekende soort {w['soort']!r} bij {sleutel!r}")
        if w["soort"] != "geen":
            uit[sleutel] = w["soort"]
    return uit


def soort_van(oordelen: list[str], woorden: dict[str, str]) -> str:
    """De soort volgens de redacties van een factcheck, of leeg: alleen woorden van de lijst, de meest bijzondere."""
    gevonden = {woorden.get(woordsleutel(o)) for o in oordelen if o and o.strip()} - {None}
    return next((s for s in SOORTEN if s in gevonden), "")


def vorm_van(engels: str) -> str:
    """De vorm die de Engelse tekst van een bewering noemt: video, beeld of leeg."""
    tekst = (engels or "").casefold()
    if _VIDEO.search(tekst):
        return "video"
    if _BEELD.search(tekst):
        return "beeld"
    return ""
