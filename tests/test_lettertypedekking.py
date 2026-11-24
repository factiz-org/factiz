"""Een claim die het lettertype niet kan tekenen, hoort niet in de beeldbenchmark.

*(PLAN.md #18.3, BENCHMARK.md §51d)*

`render_claim` tekende met een lettertype zonder CJK- en Thaise glieven, dus
Japanse en Chinese claims werden blokjes. **23 van de 435 CJK-paren in de eigen
steekproef van de beeldbenchmark kregen een exact identieke PDQ-hash** — twee
losstaande claims, dezelfde vingerafdruk. Latijn: 0 van 435.

Dat is de faalvorm uit §17a in de beeldroute: het meetharnas ziet er voor Latijn
prima uit en meet elders niets. En het is gevaarlijker dan een gemiste meting,
want identieke hashes zijn *valse koppelingen* — precies wat de beeldbenchmark
hoort te tellen.

De remedie is niet "een beter lettertype" alleen. Er is geen lettertype dat elk
schrift dekt: zelfs Arial Unicode mist Ethiopisch, en Amhaars zit in het corpus.
Dus: een terugvallijst per tekst, en **weigeren in plaats van blokjes tekenen**
wanneer niets past. Wat niet gerenderd kan worden, wordt geteld en gemeld.
"""

from __future__ import annotations

import io
import itertools

import pytest

from doublecheck.benchmark_images import (
    OngedekteTekst,
    kan_renderen,
    render_claim,
)
from doublecheck.config import load_config
from doublecheck.image_fingerprint import fingerprint_image
from tests.schriften import PANEEL


def _hash(tekst: str) -> str:
    buffer = io.BytesIO()
    render_claim(tekst).save(buffer, format="PNG")
    versie = load_config().model_versions.image_hash
    return fingerprint_image(buffer.getvalue(), versie).hash_hex


CJK = [
    "網傳「雞眼用香蕉皮就可以治好」的影片",
    "上野千鶴子氏が安倍晋三の国葬について発言した",
    "中国政府が新しい移民法を発表したという投稿",
    "台灣衛福部宣布新冠疫苗政策的最新調整內容",
]


def test_two_different_cjk_claims_never_share_a_fingerprint():
    """Dit is de fout zelf: vier claims, en drie paren waren identiek."""
    if not all(kan_renderen(t) for t in CJK):
        pytest.skip("geen lettertype met CJK-glieven op deze machine")
    hashes = [_hash(t) for t in CJK]
    botsingen = [
        (a, b) for (a, ha), (b, hb) in itertools.combinations(enumerate(hashes), 2)
        if ha == hb
    ]
    assert botsingen == [], f"identieke vingerafdruk voor {botsingen}"


@pytest.mark.parametrize("schrift", sorted(PANEEL))
def test_a_script_is_either_drawn_properly_or_refused(schrift):
    """Nooit stilzwijgend blokjes: of het lukt, of het weigert luid."""
    tekst = PANEEL[schrift]
    if kan_renderen(tekst):
        render_claim(tekst)
        return
    with pytest.raises(OngedekteTekst):
        render_claim(tekst)


def test_a_text_no_font_can_draw_is_refused_and_not_drawn():
    """Tengwar staat in het private-gebruik-gebied: geen enkel lettertype
    heeft hier glieven, en dan is blokjes tekenen het verkeerde antwoord."""
    onmogelijk = " "
    assert not kan_renderen(onmogelijk)
    with pytest.raises(OngedekteTekst):
        render_claim(onmogelijk)


def test_latin_still_renders_and_stays_distinguishable():
    a = _hash("The moon landing was staged in a Hollywood studio")
    b = _hash("Vaccines contain microchips for tracking people")
    assert a != b
