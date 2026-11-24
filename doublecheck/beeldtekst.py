"""Een beeldtreffer telt alleen als de tekst klopt (PLAN.md #26.3, BENCHMARK §93).

De stiltetoets voor beelden vond de zwakte van elke beeldroute: memes op
hetzelfde sjabloon. Het onderschrift is maar een strook van het beeld, dus
PDQ zet 102 van 900 verschillende memes binnen de drempel, en DINOv2, dat
beschrijft wat er te zien is, nog meer. Wat een meme van een andere meme
onderscheidt, is de tekst.

De regel: lezen beide beelden als tekst (de OCR van de resolver, `readable`),
dan moet de tekst van de vraag op die van het geïndexeerde beeld lijken, met
de tekstvingerafdruk van de motor op of boven `text_related`. Leest een van
beide geen tekst, zoals een foto zonder onderschrift, dan verandert er niets.
Vergeleken wordt de tekst ín het beeld, niet de claimtekst van de redactie:
die is vaak een samenvatting of een vertaling, en dan zou de regel terechte
treffers weggooien.
"""

from __future__ import annotations

from typing import Callable

from doublecheck.ocr import OcrResult


def beeldtreffer_telt(vraag: OcrResult, index: OcrResult, vergelijk: Callable[[str, str], float],
                      drempel: float) -> bool:
    """Of een beeldtreffer mag blijven staan. `vergelijk` geeft de gelijkenis
    van twee teksten (in de motor: de tekstvingerafdruk)."""
    if not (vraag.readable and index.readable):
        return True
    return vergelijk(vraag.text, index.text) >= drempel
