"""De foto bij de bron (PLAN #32.54, 3b en 3c; PO 2026-11-08: "dat mag en start proef"): groen bij een bericht met een
foto alleen als een goede bron die het nieuws bevestigt, ook deze foto toont. Factiz beoordeelt geen pixels; het beeld
is een sleutel. Alleen de pagina's die het zoeken al vond, beleefd, en het beeld alleen in het geheugen."""

import io

from doublecheck import fotobron as fb
from tests.beelden import jpeg_hercompressie, vormen


def _bytes(beeld, formaat="PNG") -> bytes:
    uit = io.BytesIO()
    beeld.convert("RGB").save(uit, format=formaat)
    return uit.getvalue()


FOTO = vormen(7, 640, 480)
ANDERE = vormen(11, 640, 480)
BRONNEN = [{"url": "https://www.bbc.com/a", "rol": "bevestigt", "band": "goed"},
           {"url": "https://blog.example/b", "rol": "bevestigt", "band": None},
           {"url": "https://apnews.com/c", "rol": "bevestigt", "band": "goed"},
           {"url": "https://snopes.com/d", "rol": "zelfde bewering", "band": None},
           {"url": "https://www.reuters.com/e", "rol": "spreekt tegen", "band": "goed"}]
GROEN = {"oordeel": "klopt", "kleur": "groen", "uitkomst": "klopt", "uitleg": "Dit klopt: de brand was op dinsdag [1].",
         "bronnen": BRONNEN}


def _zoek(paginas: dict, beelden: dict, beeld=FOTO):
    gevraagd = []

    def beelden_van(url):
        gevraagd.append(url)
        return paginas.get(url)

    vondst = fb.zoek(_bytes(beeld), fb.paginas(BRONNEN), beelden_van, lambda u: beelden.get(u))
    return vondst, gevraagd


def test_only_good_pages_that_confirm_the_message_are_opened_in_their_order_and_at_most_five():
    assert fb.paginas(BRONNEN) == ["https://www.bbc.com/a", "https://apnews.com/c"]
    veel = [{"url": f"https://n{i}.org/x", "rol": "bevestigt", "band": "goed"} for i in range(8)]
    assert fb.paginas(veel) == [f"https://n{i}.org/x" for i in range(fb.MAX_PAGINAS)]


def test_a_recompressed_copy_on_a_confirming_page_keeps_the_green():
    kopie = _bytes(jpeg_hercompressie(FOTO.resize((480, 360)), 60), "JPEG")
    vondst, gevraagd = _zoek({"https://www.bbc.com/a": ["https://bbc.com/1.jpg"],
                              "https://apnews.com/c": ["https://apnews.com/2.jpg"]},
                             {"https://bbc.com/1.jpg": _bytes(ANDERE), "https://apnews.com/2.jpg": kopie})
    assert vondst["gevonden"] == "https://apnews.com/c" and vondst["beeld"] == "https://apnews.com/2.jpg"
    assert vondst["versie"] == fb.VERSIE and gevraagd == ["https://www.bbc.com/a", "https://apnews.com/c"]
    uit = fb.toepassen(GROEN, vondst)
    assert uit["kleur"] == "groen" and uit["uitkomst"] == "klopt" and uit["foto"]["gevonden"] == "https://apnews.com/c"


def test_green_without_the_photo_at_its_sources_loses_its_colour_but_says_the_news_holds():
    vondst, _ = _zoek({"https://www.bbc.com/a": ["https://bbc.com/1.jpg"], "https://apnews.com/c": []},
                      {"https://bbc.com/1.jpg": _bytes(ANDERE)})
    assert vondst["gevonden"] is None and vondst["geopend"] == 2 and vondst["beelden"] == 1
    uit = fb.toepassen(GROEN, vondst)
    assert uit["kleur"] is None and uit["uitkomst"] == fb.UITKOMST == "foto niet bij de bron"
    assert uit["uitleg"].startswith(fb.ZIN) and "Dit klopt: de brand was op dinsdag [1]." in uit["uitleg"]
    assert uit["oordeel"] == "klopt" and GROEN["kleur"] == "groen", "het oordeel van de lezer blijft; het origineel ook"


def test_a_page_that_does_not_open_counts_as_not_found_and_is_reported():
    vondst, _ = _zoek({"https://www.bbc.com/a": None, "https://apnews.com/c": None}, {})
    assert vondst["gevonden"] is None and vondst["geopend"] == 0 and vondst["paginas"] == 2
    assert fb.toepassen(GROEN, vondst)["kleur"] is None


def test_only_a_green_answer_is_touched():
    rood = {**GROEN, "kleur": "rood", "uitkomst": "klopt niet", "oordeel": "klopt niet"}
    leeg = {"versie": fb.VERSIE, "gevonden": None, "paginas": 0, "geopend": 0, "beelden": 0}
    assert fb.toepassen(rood, leeg) == rood and fb.toepassen(GROEN, None) == GROEN
    assert fb.moet_zoeken(GROEN, True) and not fb.moet_zoeken(GROEN, False) and not fb.moet_zoeken(rood, True)


def test_at_most_ten_images_per_page_are_fetched_and_a_broken_image_is_skipped():
    adressen = [f"https://bbc.com/{i}.jpg" for i in range(15)]
    gehaald = []

    def beeld_van(u):
        gehaald.append(u)
        return b"geen beeld" if u.endswith("0.jpg") else _bytes(ANDERE)

    vondst = fb.zoek(_bytes(FOTO), ["https://www.bbc.com/a"], lambda u: adressen, beeld_van)
    assert len(gehaald) == fb.MAX_BEELDEN and vondst["beelden"] == fb.MAX_BEELDEN - 1 and vondst["gevonden"] is None


# --- versie 2 (#32.54, na §248) -------------------------------------------------------------------------------------

def test_v2_also_opens_an_official_page_that_confirms_the_message():
    bronnen = BRONNEN + [{"url": "https://ttparliament.org/x", "rol": "bevestigt", "band": None, "soort": "officieel"}]
    assert "https://ttparliament.org/x" not in fb.paginas(bronnen)
    assert fb.paginas(bronnen, versie="fotobron-v2")[-1] == "https://ttparliament.org/x"


def test_v2_finds_a_photo_that_fills_only_part_of_a_screenshot():
    from PIL import Image, ImageDraw

    scherm = Image.new("RGB", (900, 1100), "white")
    teken = ImageDraw.Draw(scherm)
    for i in range(6):
        teken.text((40, 30 + i * 28), f"Regel {i} van een bericht met tekst boven de foto", fill="black")
    teken.rectangle((38, 228, 862, 852), outline=(200, 200, 200), width=2)
    scherm.paste(FOTO.resize((820, 620)), (40, 230))
    v1 = fb.zoek(_bytes(scherm), ["https://a.org/p"], lambda u: ["https://a.org/1.jpg"], lambda u: _bytes(FOTO))
    v2 = fb.zoek(_bytes(scherm), ["https://a.org/p"], lambda u: ["https://a.org/1.jpg"], lambda u: _bytes(FOTO),
                 versie="fotobron-v2")
    assert v2["gevonden"] == "https://a.org/p" and v2["versie"] == "fotobron-v2"
    assert v1["versie"] == "fotobron-v1"


def test_v2_still_does_not_take_another_photo_for_the_same_one():
    v2 = fb.zoek(_bytes(FOTO), ["https://a.org/p"], lambda u: ["https://a.org/1.jpg"], lambda u: _bytes(ANDERE),
                 versie="fotobron-v2")
    assert v2["gevonden"] is None


def test_looking_at_the_pages_at_the_same_time_gives_the_same_answer_as_one_after_the_other():
    """#32.54, B66: het product bekijkt de pagina's tegelijk; dan telt de eerste pagina in de volgorde die de foto heeft."""
    paginas = ["https://a.org/1", "https://b.org/2", "https://c.org/3"]
    beelden = {"https://a.org/1": ["https://a.org/x.jpg"], "https://b.org/2": ["https://b.org/y.jpg"],
               "https://c.org/3": ["https://c.org/z.jpg"]}
    inhoud = {"https://a.org/x.jpg": _bytes(ANDERE), "https://b.org/y.jpg": _bytes(FOTO), "https://c.org/z.jpg": _bytes(FOTO)}
    na_elkaar = fb.zoek(_bytes(FOTO), paginas, beelden.get, inhoud.get)
    tegelijk = fb.zoek(_bytes(FOTO), paginas, beelden.get, inhoud.get, tegelijk=5)
    assert na_elkaar["gevonden"] == tegelijk["gevonden"] == "https://b.org/2"
    assert na_elkaar["geopend"] == 2 and tegelijk["geopend"] == 3
