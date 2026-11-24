"""De rol van elk beeld in een factcheckartikel (PLAN #32.21): viraal, origineel, bewijs, huisstijl of onbekend."""

import json

from doublecheck import beeldrolvraag as br


def _beelden(n):
    return [{"alt": f"beeld {i}", "onderschrift": "", "voor": "The viral post claims ...", "na": "", "deel": i == 0}
            for i in range(n)]


def _antwoord(*paren):
    return json.dumps({"rollen": [{"beeld": b, "rol": r} for b, r in paren]})


def test_an_unreadable_answer_never_makes_an_image_viral():
    assert br.lees_rollen("geen json", 3) == ["onbekend"] * 3
    assert br.lees_rollen(json.dumps({"iets": 1}), 2) == ["onbekend"] * 2
    assert br.lees_rollen(None, 1) == ["onbekend"]


def test_each_image_gets_its_role_in_dutch():
    assert br.lees_rollen(_antwoord(("B1", "viral"), ("B2", "original"), ("B3", "evidence"), ("B4", "house")), 4) \
        == ["viraal", "origineel", "bewijs", "huisstijl"]


def test_a_missing_image_and_an_unknown_role_word_are_unknown():
    assert br.lees_rollen(_antwoord(("B1", "viral"), ("B3", "fake")), 3) == ["viraal", "onbekend", "onbekend"]
    assert br.lees_rollen(_antwoord(("B9", "viral"), ("X", "viral")), 2) == ["onbekend", "onbekend"]


def test_an_image_named_twice_with_different_roles_is_unknown():
    assert br.lees_rollen(_antwoord(("B1", "viral"), ("B1", "evidence"), ("B2", "viral"), ("B2", "viral")), 2) \
        == ["onbekend", "viraal"]


def test_the_request_numbers_the_images_and_carries_no_image():
    v = br.verzoek("Photo shows X.", "Fact check: X", _beelden(3))
    inhoud = v["messages"][0]["content"]
    assert all(blok["type"] == "text" for blok in inhoud)
    tekst = " ".join(blok["text"] for blok in inhoud)
    assert "[B1]" in tekst and "[B3]" in tekst and "[B4]" not in tekst
    assert "Photo shows X." in tekst and "share image" in tekst
    assert v["model"].startswith("claude-haiku")
    assert v["output_config"]["format"]["type"] == "json_schema"


def test_too_many_images_are_cut_and_the_context_stays_short():
    beelden = _beelden(br.MAX_BEELDEN + 5)
    beelden[1]["voor"] = "x" * 5000
    tekst = " ".join(b["text"] for b in br.verzoek("c", "t", beelden)["messages"][0]["content"])
    assert f"[B{br.MAX_BEELDEN}]" in tekst and f"[B{br.MAX_BEELDEN + 1}]" not in tekst
    assert "x" * (br.MAX_CONTEXT + 1) not in tekst


def _jpeg_bytes():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
    return buf.getvalue()


def test_v2_shows_only_the_share_image_and_keeps_the_roles_of_v1():
    v = br.verzoek("Photo shows X.", "Fact check: X", _beelden(3), versie="rol-v2", deelbeeld=_jpeg_bytes())
    inhoud = v["messages"][0]["content"]
    assert [blok["type"] for blok in inhoud] == ["image", "text"]
    tekst = inhoud[1]["text"]
    assert "[B1] the article's share image, shown above" in tekst and "shown above" not in tekst.split("\n[B2]")[1]
    for regel in br.VRAAG_V1.split("\n"):
        if regel.startswith('- "'):
            assert regel in tekst   # dezelfde vijf rollen, woord voor woord


def test_v2_never_runs_without_the_share_image_and_v1_never_sees_an_image():
    import pytest

    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v2")
    geen_deel = [dict(b, deel=False) for b in _beelden(2)]
    with pytest.raises(ValueError):
        br.verzoek("c", "t", geen_deel, versie="rol-v2", deelbeeld=_jpeg_bytes())
    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v1", deelbeeld=_jpeg_bytes())


# --- rol-v3: elk beeld gaat mee (#32.26) -------------------------------------------------------------------------------

def test_v3_shows_every_image_after_its_label_in_order_and_keeps_the_roles_of_v1():
    import base64

    v = br.verzoek("Photo shows X.", "Fact check: X", _beelden(3), versie="rol-v3", beelden_bytes=[_jpeg_bytes()] * 3)
    inhoud = v["messages"][0]["content"]
    assert [b["type"] for b in inhoud] == ["text", "image", "text", "image", "text", "image", "text"]
    assert [inhoud[i]["text"] for i in (0, 2, 4)] == ["[B1]", "[B2]", "[B3]"]
    assert base64.b64decode(inhoud[1]["source"]["data"])[:2] == b"\xff\xd8", "een JPEG, alleen in het geheugen"
    tekst = inhoud[-1]["text"]
    for regel in br.VRAAG_V1.split("\n"):
        if regel.startswith('- "'):
            assert regel in tekst   # dezelfde vijf rollen, woord voor woord
    assert "made by the fact-checker" in tekst and "next to the original" in tekst, "de regel van de PO"
    assert "never guess \"viral\"" in tekst and "from the images themselves" in tekst


def test_v3_refuses_a_missing_image_and_never_takes_a_lone_share_image():
    import pytest

    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(3), versie="rol-v3", beelden_bytes=[_jpeg_bytes()] * 2)
    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v3", beelden_bytes=[_jpeg_bytes(), None])
    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v3")
    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v3", beelden_bytes=[_jpeg_bytes()] * 2, deelbeeld=_jpeg_bytes())
    with pytest.raises(ValueError):
        br.verzoek("c", "t", _beelden(2), versie="rol-v2", deelbeeld=_jpeg_bytes(), beelden_bytes=[_jpeg_bytes()] * 2)


def test_v3_sends_at_most_the_first_twelve_images():
    beelden = _beelden(br.MAX_BEELDEN + 2)
    v = br.verzoek("c", "t", beelden, versie="rol-v3", beelden_bytes=[_jpeg_bytes()] * br.MAX_BEELDEN)
    assert sum(b["type"] == "image" for b in v["messages"][0]["content"]) == br.MAX_BEELDEN
