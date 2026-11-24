"""De bewering uit een artikel (PLAN #30.11, laag 2 van B36).

Een artikel of een lange post legt nu als één tekst naast de claims, en dan
verdunt de kop in de rest en wijst de rechter de lange invoer af (§131). Een
tekst met twee of meer zinnen wordt daarom gezocht als de hele tekst plus
elke zin. De zin houdt zijn zinseinde: een vraagteken is wat de vraagvorm
(#25.36) herkent.

Een zin eindigt op een regeleinde (de kop) of een zinseinde. Latijnse einders
alleen vóór wit of het eind, zodat "3.5" heel blijft; schriften met een eigen
einde (CJK 。, Devanagari ।, Arabisch ؟, Urdu ۔, Amhaars ።, Birmaans ။, Khmer ។)
zetten er geen spatie achter en splitsen altijd. Thai heeft geen zinseinde en
blijft één eenheid: dan het pad van nu.

De ondergrens telt tekens zonder spaties, en een breed teken (Han, kana,
Hangul) voor drie: een Chinese zin is drie tot vier keer korter dan dezelfde
zin in het Engels, en met één per teken viel "疫苗导致自闭症。" (acht tekens)
eruit. Bijgesteld vóór de eerste meting (PLAN #30.11).
"""

from __future__ import annotations

import re
import unicodedata

# Vastgelegd vóór het bouwen (PLAN #30.11): vanaf 12 tekens zonder spaties
# (de grens van `[ocr] min_chars`), hoogstens de eerste 12 zinnen.
MIN_TEKENS = 12
MAX_ZINNEN = 12
BREED = 3

_EINDE = re.compile(r"[.!?…]+(?=\s|$)|[。！？؟।॥։።။۔។៕]+|\n")


def _lengte(zin: str) -> int:
    return sum(BREED if unicodedata.east_asian_width(t) in "WF" else 1 for t in zin if not t.isspace())


def zinnen(tekst: str) -> list[str]:
    """De zinnen van een tekst, elk met zijn zinseinde."""
    uit, begin = [], 0
    for einde in _EINDE.finditer(tekst):
        uit.append(tekst[begin:einde.end()].strip())
        begin = einde.end()
    uit.append(tekst[begin:].strip())
    return [zin for zin in uit if zin]


def eenheden(tekst: str) -> list[str]:
    """Wat de resolver zoekt: bij twee of meer zinnen die meetellen de hele
    tekst en dan elke zin, anders alleen de tekst zoals hij binnenkwam."""
    tellen = [z for z in zinnen(tekst) if _lengte(z) >= MIN_TEKENS][:MAX_ZINNEN]
    if len(tellen) < 2:
        return [tekst]
    uit = [tekst]
    for zin in tellen:
        if zin not in uit:
            uit.append(zin)
    return uit
