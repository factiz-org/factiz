"""Een artikel per zin (PLAN #30.11): welke eenheden de rechter leest, en
welke uitkomst wint.

Eén plek voor de resolver en de terugkijktoets, zodat de zeef meet wat de
resolver doet. De categorie per eenheid zet `categorize` (DR4); hier wordt
alleen gekozen: `matched` vóór `related` vóór `none`, bij gelijke categorie
de grootste marge boven de rechterdrempel, dan de hoogste gelijkenis, dan de
eerste eenheid.
"""

from __future__ import annotations

from doublecheck.categorize import Category, rechterdrempel

RANG = {Category.MATCHED: 3, Category.ASSESSED: 2, Category.RELATED: 1, Category.NONE: 0}
# Vastgelegd vóór het bouwen: de rechter leest bij een artikel hoogstens drie eenheden.
GELEZEN = 3


def te_lezen(lijsten: list, config) -> list[int]:
    """Bij één eenheid die ene (de rechter kiest zelf wat boven de vloer
    ligt, zoals vóór #30.11); bij een artikel de drie eenheden met de hoogste
    beste gelijkenis vanaf de vloer, en zonder rechter geen."""
    if len(lijsten) == 1:
        return [0]
    if not config.rechter.aan:
        return []
    vloer = config.thresholds.rechter_vloer
    kandidaat = [i for i, lijst in enumerate(lijsten) if lijst and lijst[0].similarity >= vloer]
    return sorted(kandidaat, key=lambda i: -lijsten[i][0].similarity)[:GELEZEN]


def marge(beste, config, crosslinguaal: bool = False) -> float:
    """Hoe ver de rechter boven zijn eigen drempel voor deze kandidaat zit; 0
    zonder rechter of zonder score."""
    if not config.rechter.aan or beste is None or beste.rechter is None:
        return 0.0
    return beste.rechter - rechterdrempel(beste.similarity, config.thresholds, crosslinguaal)


def winnaar(uitslagen: list[tuple]):
    """De beste van (uitkomst, beste kandidaat, marge, ...) per eenheid; wat
    erachter staat, gaat ongelezen mee."""
    def sleutel(i_u):
        i, (uitkomst, beste, m, *_) = i_u
        return (RANG[uitkomst.category], m, beste.similarity if beste is not None else -1.0, -i)

    return max(enumerate(uitslagen), key=sleutel)[1]
