"""V1 en V2 van de radar (PLAN #32.69): het virale beeld en het origineel uit hetzelfde factcheckartikel."""

import json

import pytest

from doublecheck import beeldpaar as bp

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
       b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


def _rol(artikel, beelden, rollen):
    return {"artikel": artikel, "beelden": beelden, "rollen": rollen}


def test_a_pair_is_a_viral_image_without_a_stamp_word_and_the_original_of_the_same_article_capped_per_site():
    rollen = [_rol(f"https://a.org/{i}", [f"https://a.org/v{i}.jpg", f"https://a.org/o{i}.jpg"], ["viraal", "origineel"])
              for i in range(5)]
    rollen += [_rol("https://b.org/1", ["https://b.org/FAKE-1.jpg", "https://b.org/o1.jpg"], ["viraal", "origineel"]),
               _rol("https://b.org/2", ["https://b.org/v2.jpg", "https://b.org/x2.jpg"], ["viraal", "bewijs"]),
               _rol("https://c.org/1", ["https://c.org/v1.jpg", "https://c.org/o1.jpg"], ["viraal", "origineel"])]
    claims = {f"a.org/{i}": {"tekst": f"claim {i}", "oordeel": "onwaar", "taal": "en"} for i in range(5)}
    claims.update({"b.org/1": {"tekst": "b", "oordeel": "onwaar", "taal": "es"},
                   "c.org/1": {"tekst": "c", "oordeel": "misleidend", "taal": "nl"}})
    paren = bp.kies_paren(rollen, {}, claims, n=10, per_host=3, zaad=1)
    hosts = [p["host"] for p in paren]
    assert hosts.count("a.org") == 3 and "c.org" in hosts and "b.org" not in hosts
    p = next(p for p in paren if p["host"] == "c.org")
    assert (p["viraal"], p["origineel"], p["claim"], p["soort"]) == ("https://c.org/v1.jpg", "https://c.org/o1.jpg", "c",
                                                                     "paar")
    assert p["id"].startswith("P:") and bp.kies_paren(rollen, {}, claims, n=10, per_host=3, zaad=1) == paren


def test_a_sham_pair_puts_the_viral_image_next_to_the_original_of_another_article_preferably_of_the_same_site():
    paren = [{"id": f"P:{i}", "soort": "paar", "host": h, "artikel": f"https://{h}/{i}", "viraal": f"v{i}",
              "origineel": f"o{i}", "claim": f"c{i}", "context_origineel": ""} for i, h in enumerate(["a", "a", "b", "c"])]
    schijn = bp.schijnparen(paren, n=3, zaad=2)
    assert len(schijn) == 3 and all(s["soort"] == "schijn" and s["id"].startswith("S:") for s in schijn)
    for s in schijn:
        bron = next(p for p in paren if p["viraal"] == s["viraal"])
        assert s["origineel"] != bron["origineel"] and s["artikel_origineel"] != bron["artikel"]
    a = [s for s in schijn if s["host"] == "a"]
    assert all(s["artikel_origineel"].startswith("https://a/") for s in a)


@pytest.mark.parametrize("model", ["sonnet", "opus", "fable"])
def test_the_question_shows_both_images_with_the_claim_and_the_caption_and_asks_the_same_of_every_model(model):
    from doublecheck.modellen import MODELLEN

    p = {"id": "P:abc", "claim": "This photo shows Gaza in 2023", "context_origineel": "Photo: Reuters, Syria 2016"}
    v = bp.paarverzoek(p, PNG, PNG, model)
    assert v["custom_id"] == f"{model}-abc" and v["params"]["model"] == MODELLEN[model]["id"]
    inhoud = v["params"]["messages"][0]["content"]
    assert [b["type"] for b in inhoud[:4]] == ["text", "image", "text", "image"]
    tekst = inhoud[-1]["text"]
    assert "This photo shows Gaza in 2023" in tekst and "Photo: Reuters, Syria 2016" in tekst
    assert set(v["params"]["output_config"]["format"]["schema"]["required"]) == {
        "stempel", "afgeleid", "veranderingen", "wat_echt", "uitleg"}
    # Fable denkt altijd, en dat denken telt mee in de grens van de uitvoer (RESEARCH §12)
    assert v["params"]["max_tokens"] >= (8000 if model == "fable" else 3000)


def test_an_answer_outside_the_fixed_words_is_doubt_and_unknown_changes_are_dropped():
    a = bp.lees_paar(json.dumps({"stempel": False, "afgeleid": "ja", "veranderingen": ["andere context", "magie"],
                                 "wat_echt": "Syrië, 2016", "uitleg": "x"}))
    assert a["afgeleid"] == "ja" and a["veranderingen"] == ["andere context"] and a["stempel"] is False
    assert bp.lees_paar(json.dumps({"afgeleid": "misschien"}))["afgeleid"] == "twijfel"
    assert bp.lees_paar("kapot") == {"stempel": None, "afgeleid": "twijfel", "veranderingen": [], "wat_echt": "",
                                     "uitleg": ""}


def test_the_count_refuses_while_a_pair_has_no_label_and_scores_link_change_other_photo_and_sham_per_model():
    paren = [{"id": f"P:{i}", "soort": "paar"} for i in range(1, 6)] + [{"id": "S:1", "soort": "schijn"}]
    antw = {"opus": {"P:1": {"afgeleid": "ja", "veranderingen": ["andere context"]},
                     "P:2": {"afgeleid": "ja", "veranderingen": ["tekst toegevoegd"]},
                     "P:3": {"afgeleid": "nee", "veranderingen": []},
                     "P:4": {"afgeleid": "ja", "veranderingen": ["andere context", "bewerkt"]},
                     "P:5": {"afgeleid": "nee", "veranderingen": []},
                     "S:1": {"afgeleid": "nee", "veranderingen": []}}}
    with pytest.raises(bp.Weigering):
        bp.telling(paren, antw, {"P:1": "andere context"})
    labels = {"P:1": "andere context", "P:2": "bewerkt", "P:3": "geen bron", "P:4": "andere context",
              "P:5": "andere foto"}
    t = bp.telling(paren, antw, labels)["opus"]
    # P:2: "tekst toegevoegd" is geen bewerking van wat er op de foto staat; P:4 ziet een bewerking die er niet is;
    # P:3 telt niet mee; P:5 is een andere opname van dezelfde gebeurtenis, dus terecht nee
    assert t == {"paren": 3, "gekoppeld": 3, "verandering goed": 2, "andere context": 2, "valse bewerking": 1,
                 "andere foto": 1, "andere foto nee": 1, "schijn": 1, "schijn nee": 1}


@pytest.mark.parametrize("context,bron", [
    ("La imagen original fue publicada por la agencia Reuters en 2015", "persbureau"),
    ("Foto: AFP/Getty Images", "persbureau"),
    ("The original photo was posted on Facebook in 2019", "sociale media"),
    ("Una captura del archivo de Wayback Machine", "archief"),
    ("Imagen de Shutterstock", "beeldbank"),
    ("Publicada por El País en su web", "media"),
    ("", "onbekend"),
])
def test_where_an_original_comes_from_is_read_from_the_text_around_it(context, bron):
    assert bp.bron_van(context) == bron
