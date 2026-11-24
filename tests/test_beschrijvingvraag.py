"""Wat een foto toont, in woorden (beschrijving-v1, PLAN #32.17).

Haiku krijgt alleen het beeld en schrijft in één Engelse zin wat de foto toont, zoals een factchecker het virale beeld
beschrijft, met twee zoekvragen. Een onleesbaar antwoord, of een beeld zonder foto, is geen beschrijving: dan zoekt
deze sleutel niets.
"""

import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

from doublecheck import beschrijvingvraag as bs
from doublecheck.modellen import MODELLEN


def _png(maat=(2400, 1600)) -> bytes:
    rng = np.random.default_rng(0)
    buf = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (maat[1], maat[0], 3), dtype=np.uint8)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("tekst", ["", "geen json", "[]", "null", '{"foto": true}',
                                   '{"foto": true, "beschrijving": 3, "zoekvragen": []}',
                                   '{"foto": true, "beschrijving": "Photo shows a fire.", "zoekvragen": "fire"}',
                                   '{"foto": "ja", "beschrijving": "Photo shows a fire.", "zoekvragen": []}'])
def test_an_unreadable_answer_is_never_a_description(tekst):
    assert bs.lees_beschrijving(tekst) is None


def test_an_image_without_a_photo_gives_no_description():
    assert bs.lees_beschrijving(json.dumps({"foto": False, "beschrijving": "Text on a white background.",
                                            "zoekvragen": ["text"]})) is None
    assert bs.lees_beschrijving(json.dumps({"foto": True, "beschrijving": "  ", "zoekvragen": ["x"]})) is None


def test_a_description_keeps_at_most_two_search_queries_without_empty_ones():
    uit = bs.lees_beschrijving(json.dumps({"foto": True, "beschrijving": " Photo shows a flooded  street. ",
                                           "zoekvragen": ["flooded street", " ", "flood", "third"]}))
    assert uit == {"beschrijving": "Photo shows a flooded street.", "zoekvragen": ["flooded street", "flood"]}


def test_the_question_sends_only_a_small_jpeg_and_the_fixed_question():
    params = bs.verzoek(_png())
    inhoud = params["messages"][0]["content"]
    beeld = next(b for b in inhoud if b["type"] == "image")
    klein = Image.open(io.BytesIO(base64.b64decode(beeld["source"]["data"])))
    assert beeld["source"]["media_type"] == "image/jpeg" and klein.format == "JPEG"
    assert max(klein.size) <= bs.MAX_ZIJDE
    # geen tekst van de post, geen OCR: alleen de vaste vraag
    assert [b["text"] for b in inhoud if b["type"] == "text"] == [bs.VRAGEN["beschrijving-v1"]["vraag"]]
    assert params["model"] == MODELLEN["haiku"]["id"]
    assert params["output_config"]["format"]["schema"] == bs._SCHEMA


def test_the_question_forbids_faces_judging_and_the_post_text():
    vraag = bs.VRAGEN["beschrijving-v1"]["vraag"].lower()
    assert "face" in vraag and "do not judge" in vraag and "text of the post" in vraag


def test_an_unknown_version_is_refused():
    with pytest.raises(ValueError):
        bs.verzoek(_png((300, 200)), "beschrijving-v9")


def test_a_description_searches_the_memory_like_a_claim():
    assert bs.als_beweringen({"beschrijving": "Photo shows a fire.", "zoekvragen": ["fire"]}) == [
        {"bewering": "Photo shows a fire.", "zoekvragen": ["fire"]}]
    assert bs.als_beweringen(None) == []


def test_a_description_in_another_script_keeps_every_letter():
    for zin in ("तस्वीर में बाढ़ से भरी सड़क दिखती है", "照片显示一条被洪水淹没的街道", "صورة تظهر شارعا غمرته المياه"):
        uit = bs.lees_beschrijving(json.dumps({"foto": True, "beschrijving": zin, "zoekvragen": [zin]}, ensure_ascii=False))
        assert uit == {"beschrijving": zin, "zoekvragen": [zin]}
