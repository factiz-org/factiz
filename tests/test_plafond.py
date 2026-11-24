"""Het plafond van screenshots (P5 van fase 0, PLAN #32.0c): de regels die vóór de
eerste vraag aan het model vastlagen."""

import pytest

from doublecheck import plafond as p
from doublecheck.config import load_config


def test_the_media_type_comes_from_the_bytes_not_the_file_name():
    assert p.media_soort(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert p.media_soort(b"\xff\xd8\xff\xe0....") == "image/jpeg"
    assert p.media_soort(b"GIF89a....") == "image/gif"
    assert p.media_soort(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"


def test_the_image_goes_first_and_the_question_is_the_one_of_round_4():
    stuk = {"id": "b-1", "tekst": "ocr tekst", "datum": None}
    geheugen = [{"claim": "gfc-1", "redactie": "BOOM", "datum": "2021-01-01", "oordeel": "onwaar", "tekst": "x"}]
    params = p.verzoek(stuk, geheugen, b"\x89PNG\r\n\x1a\n....", load_config(None))
    inhoud = params["messages"][0]["content"]
    assert inhoud[0]["type"] == "image" and inhoud[0]["source"]["media_type"] == "image/png"
    assert "The message is the image above." in inhoud[1]["text"] and "Factiz memory" in inhoud[1]["text"]
    assert "ocr tekst" not in inhoud[1]["text"]  # het model leest het beeld zelf
    assert params["model"] == load_config(None).berichtcontrole.model_id
    assert params["tools"][0]["type"] == "web_search_20250305"


def _uit(stand, oordeel, eigen=False, bronnen=({"soort": "web", "url": "https://factly.in/x"},)):
    return {"stand": stand, "oordeel": oordeel, "eigen_bewijs": eigen, "bronnen": list(bronnen)}


def test_red_with_the_own_check_counts_without_reading():
    stukken = [{"id": "a", "helft": "toets"}, {"id": "b", "helft": "ontwikkel"}]
    telling = p.telling(stukken, {"a": _uit(1, "klopt niet", eigen=True), "b": _uit(8, "klopt")}, {})
    assert telling["alles"]["rood met bewijs"] == 1 and telling["alles"]["groen"] == 1
    assert telling["eisen"]["minstens 85% rood met bewijs"] is False
    assert telling["toetshelft"]["rood met bewijs"] == 1


def test_the_count_refuses_while_a_red_with_another_source_is_unread():
    stukken = [{"id": "a", "helft": "ontwikkel"}]
    with pytest.raises(p.Weigering):
        p.telling(stukken, {"a": _uit(5, "klopt niet")}, {})
    telling = p.telling(stukken, {"a": _uit(5, "klopt niet")}, {"a": "bewijst via factcheck"})
    assert telling["alles"]["rood met bewijs"] == 1 and telling["eisen"]["minstens 85% rood met bewijs"] is True
