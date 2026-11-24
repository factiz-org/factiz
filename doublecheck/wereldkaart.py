"""De vormen van de wereldkaart voor Verkennen (PLAN #34.2am, SPECS E9.S20 AC4).

Uit Natural Earth 1:110 miljoen (versie 5.1.2, publiek domein), gedownload met een ja van de PO naar
`data/extern/naturalearth/` (buiten git). Geprojecteerd met Equal Earth (Šavrič, Patterson en Jenny, 2018): gelijke
oppervlakte, zodat een groot land op een kaart die tellingen kleurt niet zwaarder weegt dan het is. Vereenvoudigd met
Douglas-Peucker, eilandjes die op deze schaal niets zijn weg (het land zelf nooit), Antarctica weg. De landcode is
`ISO_A2_EH` (Frankrijk en Noorwegen hebben in `ISO_A2` geen code); een vorm zonder code valt weg.

    python -m doublecheck.wereldkaart

Schrijft `site/src/kaart/wereld.json`: de breedte, de hoogte, per landcode één SVG-pad, en de herkomst onder `_meta`
(zoals elk gegevensbestand in de repo, `tests/test_licenties.py`). Het bronbestand
wordt alleen als gegevens gelezen.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
BRON = WORTEL / "data" / "extern" / "naturalearth" / "ne_110m_admin_0_countries.geojson"
UIT = WORTEL / "site" / "src" / "kaart" / "wereld.json"   # niet in een map data/: die sluit .gitignore uit
BREED = 1000.0
MARGE = 4.0              # punten rond de kaart
TOLERANTIE = 0.6         # punten: wat Douglas-Peucker mag wegschuiven
KLEINSTE = 3.0           # vierkante punten: een eiland kleiner dan dit valt weg, behalve het grootste van een land
WEG = {"AQ"}             # Antarctica: groot en zonder factchecks
HERKOMST = ("Grenzen: Natural Earth, Admin 0 Countries 1:110m, versie 5.1.2 (naturalearthdata.com), publiek domein. "
            "Geprojecteerd met Equal Earth (Šavrič, Patterson en Jenny, 2018), vereenvoudigd en zonder Antarctica door "
            "Factiz (`python -m doublecheck.wereldkaart`). Een grens op deze kaart is geen standpunt van Factiz.")
_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796


def projecteer(lengte: float, breedte: float) -> tuple[float, float]:
    """Equal Earth op de eenheidsbol: (x, y) met y omhoog."""
    lam, phi = math.radians(lengte), math.radians(breedte)
    theta = math.asin(math.sqrt(3) / 2 * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = 2 * math.sqrt(3) * lam * math.cos(theta) / (3 * (9 * _A4 * t6 * t2 + 7 * _A3 * t6 + 3 * _A2 * t2 + _A1))
    y = theta * (_A1 + _A2 * t2 + t6 * (_A3 + _A4 * t2))
    return x + 0.0, y + 0.0


def vereenvoudig(punten: list[tuple[float, float]], tolerantie: float) -> list[tuple[float, float]]:
    """Douglas-Peucker: de punten die verder dan `tolerantie` van de lijn tussen de uiteinden liggen, blijven."""
    if len(punten) < 3:
        return list(punten)
    (x1, y1), (x2, y2) = punten[0], punten[-1]
    dx, dy = x2 - x1, y2 - y1
    lengte = math.hypot(dx, dy)
    verst, plek = -1.0, 0
    for i, (x, y) in enumerate(punten[1:-1], 1):
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / lengte if lengte else math.hypot(x - x1, y - y1)
        if d > verst:
            verst, plek = d, i
    if verst <= tolerantie:
        return [punten[0], punten[-1]]
    return vereenvoudig(punten[:plek + 1], tolerantie)[:-1] + vereenvoudig(punten[plek:], tolerantie)


def _oppervlak(ring: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def _ringen(geometrie: dict) -> list[list[list[float]]]:
    """De buitenranden: een gat in een land (een meer, een enclave) laten we weg, de enclave heeft haar eigen vorm."""
    if geometrie["type"] == "Polygon":
        return [geometrie["coordinates"][0]]
    return [veelhoek[0] for veelhoek in geometrie["coordinates"]]


def bouw(bron: dict) -> dict:
    """De kaart als gegevens: breedte, hoogte en per landcode één pad."""
    landen: dict[str, list[list[tuple[float, float]]]] = {}
    for land in bron["features"]:
        code = (land["properties"].get("ISO_A2_EH") or "").strip()
        if len(code) != 2 or not code.isalpha() or code in WEG:
            continue
        landen.setdefault(code, []).extend([[projecteer(lon, lat) for lon, lat in ring] for ring in _ringen(land["geometry"])])
    alle = [p for ringen in landen.values() for ring in ringen for p in ring]
    links, rechts = min(x for x, _ in alle), max(x for x, _ in alle)
    onder, boven = min(y for _, y in alle), max(y for _, y in alle)
    schaal = (BREED - 2 * MARGE) / (rechts - links)
    hoog = round((boven - onder) * schaal + 2 * MARGE, 1)
    paden = {}
    for code, ringen in sorted(landen.items()):
        punten = [[(MARGE + (x - links) * schaal, MARGE + (boven - y) * schaal) for x, y in ring] for ring in ringen]
        grootste = max(range(len(punten)), key=lambda i: _oppervlak(punten[i]))
        stukken = []
        for i, ring in enumerate(punten):
            if i != grootste and _oppervlak(ring) < KLEINSTE:
                continue
            kort = vereenvoudig(ring, TOLERANTIE)
            if len(kort) < 4 and i == grootste:
                kort = ring                 # een land blijft zichtbaar, hoe klein ook
            if len(kort) < 4:
                continue
            stukken.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in kort[:-1]) + "Z")
        paden[code] = "".join(stukken)
    return {"_meta": {"herkomst": HERKOMST}, "breed": BREED, "hoog": hoog, "landen": paden}


def main() -> None:  # pragma: no cover - CLI
    bron = json.loads(BRON.read_text(encoding="utf-8"))
    kaart = bouw(bron)
    UIT.parent.mkdir(parents=True, exist_ok=True)
    UIT.write_text(json.dumps(kaart, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(kaart['landen'])} landen, {kaart['breed']:.0f} bij {kaart['hoog']:.0f}, {UIT.stat().st_size} bytes: {UIT}")


if __name__ == "__main__":  # pragma: no cover
    main()
