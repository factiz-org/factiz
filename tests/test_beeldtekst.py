"""Een beeldtreffer telt alleen als de tekst klopt (PLAN.md #26.3, BENCHMARK §93).

Memes op hetzelfde sjabloon lijken als beeld op elkaar, ook voor PDQ: het
onderschrift is maar een strook. Lezen beide beelden als tekst, dan moet die
tekst overeenkomen; een foto zonder tekst verandert niets.
"""

import numpy as np

from doublecheck import beeldtekst as bt
from doublecheck import beeldtekstmeting as btm
from doublecheck.ocr import OcrResult

LEEG = OcrResult(text="", readable=False)


def _vergelijk(a: str, b: str) -> float:
    return 1.0 if a == b else 0.2


def test_a_photo_without_text_keeps_its_image_match():
    tekst = OcrResult(text="ONE DOES NOT SIMPLY WALK INTO MORDOR", readable=True)
    assert bt.beeldtreffer_telt(LEEG, tekst, _vergelijk, 0.79)
    assert bt.beeldtreffer_telt(tekst, LEEG, _vergelijk, 0.79)
    assert bt.beeldtreffer_telt(LEEG, LEEG, _vergelijk, 0.79)


def test_two_images_with_text_must_say_the_same():
    a = OcrResult(text="ONE DOES NOT SIMPLY WALK INTO MORDOR", readable=True)
    b = OcrResult(text="ONE DOES NOT SIMPLY FILE TAXES ON TIME", readable=True)
    assert bt.beeldtreffer_telt(a, a, _vergelijk, 0.79)
    assert not bt.beeldtreffer_telt(a, b, _vergelijk, 0.79)


def test_the_threshold_itself_still_counts():
    a = OcrResult(text="x" * 20, readable=True)
    b = OcrResult(text="y" * 20, readable=True)
    assert bt.beeldtreffer_telt(a, b, lambda *_: 0.79, 0.79)
    assert not bt.beeldtreffer_telt(a, b, lambda *_: 0.7899, 0.79)


def test_the_measurement_counts_each_query_with_and_without_the_rule():
    """Een kopie van indexbeeld 0 met dezelfde tekst blijft goed; een meme op
    hetzelfde sjabloon met een andere tekst is zonder de regel vals en met de
    regel niets."""
    # (pdq, dino, beste) zoals Routes.vraag ze geeft: beide vragen wijzen beeld 0 aan.
    raak = ((0, 10), (0, 0.99), (0, 0.99))
    uitkomsten = [("kopie", 0, raak), ("meme", None, raak)]
    ocr_vraag = {"kopie": OcrResult(text="zelfde", readable=True),
                 "meme": OcrResult(text="ander onderschrift", readable=True)}
    index_ocr = [OcrResult(text="zelfde", readable=True)]
    uit = btm.tel(uitkomsten, ocr_vraag, index_ocr, _vergelijk,
                  drempel_pdq=31, drempels_dino={v: 0.95 for v in btm.VARIANTEN}, drempel_tekst=0.79)
    for variant in btm.VARIANTEN:
        zonder, met = uit[variant]["zonder"], uit[variant]["met"]
        assert (zonder["goed"], zonder["vals"]) == (1, 1)
        assert (met["goed"], met["vals"]) == (1, 0)


def test_index_text_is_read_once_per_image_and_kept_as_text_only():
    """Wat de meting van een beeld bewaart, is de gelezen tekst; het beeld
    zelf niet (DR3-analoog)."""
    gelezen = []

    def lees(beeld):
        gelezen.append(beeld.size)
        return OcrResult(text="t", readable=False)

    from PIL import Image
    beelden = [Image.new("RGB", (80, 80)), Image.new("RGB", (90, 90))]
    teksten = btm.lees_alles(beelden, lees)
    assert gelezen == [(80, 80), (90, 90)]
    assert all(isinstance(t, OcrResult) for t in teksten)
    assert not np.any([hasattr(t, "size") for t in teksten])
