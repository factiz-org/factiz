"""Signaal 2 van B62, de voormeting: hoe vaak draagt een nepbeeld het merk van een nieuwsmedium? (PLAN #32.58, PO 2026-11-07:
"altijd plakken ze dan zo'n logo erin, terwijl je bij echte nieuwsbronnen niet in elk shot een logo ziet"; "graag")."""

import json

from doublecheck import merkinbeeld as mb


def test_haiku_sees_the_image_and_only_says_which_news_brand_it_presents_itself_as():
    v = mb.verzoek(b"\x89PNG", "image/png")
    inhoud = v["messages"][0]["content"]
    assert inhoud[0]["type"] == "image" and inhoud[0]["source"]["media_type"] == "image/png"
    assert v["model"] == "claude-haiku-5-5" and "true" not in inhoud[1]["text"].lower().split()
    schema = v["output_config"]["format"]["schema"]
    assert schema["properties"]["hoe"]["enum"] == ["logo", "sjabloon", "naam", "geen"]


def test_the_answer_is_read_strictly_and_a_brand_without_how_counts_as_none():
    assert mb.lees(json.dumps({"merk": "Euronews", "hoe": "logo"})) == {"merk": "Euronews", "hoe": "logo"}
    assert mb.lees(json.dumps({"merk": "", "hoe": "geen"})) == {"merk": "", "hoe": "geen"}
    assert mb.lees(json.dumps({"merk": "BBC", "hoe": "geen"})) == {"merk": "", "hoe": "geen"}
    assert mb.lees("kapot") == {"merk": "", "hoe": "geen"}


def test_a_brand_name_is_matched_to_a_known_outlet_and_its_own_sites():
    assert mb.medium("Euronews") == ("Euronews", ("euronews.com",))
    assert mb.medium("bbc news") == ("BBC News", ("bbc.com", "bbc.co.uk"))
    assert mb.medium("Onbekende Krant") is None and mb.medium("") is None
