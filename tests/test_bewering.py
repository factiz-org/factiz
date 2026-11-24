"""Het model leest, Factiz zoekt het bonnetje (PLAN #30.12): de regels die
vóór de meting vastlagen."""

import json

import pytest

from doublecheck import bewering


def test_an_answer_with_a_claim_gives_that_one_sentence():
    antwoord = json.dumps({"doet_bewering": True, "bewering": "  Photo shows floods in Chennai in 2015. "})
    assert bewering.lees_antwoord(antwoord) == ("bewering", "Photo shows floods in Chennai in 2015.")


def test_an_answer_without_a_checkable_claim_gives_no_sentence():
    assert bewering.lees_antwoord(json.dumps({"doet_bewering": False, "bewering": "A cat."})) == ("geen", None)
    assert bewering.lees_antwoord(json.dumps({"doet_bewering": True, "bewering": "  "})) == ("geen", None)


def test_a_cut_off_answer_is_marked_for_resubmission():
    assert bewering.lees_antwoord('{"doet_bewering": true, "bewering": "Photo sh') == ("onleesbaar", None)


def test_the_request_asks_for_the_claim_only_and_never_for_a_verdict(tmp_path):
    beeld = tmp_path / "00001.png"
    beeld.write_bytes(b"\x89PNG\r\n\x1a\n")
    met_beeld = bewering.verzoek({"id": "P3-00001", "beeld": str(beeld)})
    tekst = bewering.verzoek({"id": "N1-00001", "tekst": "Some web text."})
    assert met_beeld["custom_id"] == "P3-00001"
    assert met_beeld["params"]["messages"][0]["content"][0]["source"]["media_type"] == "image/png"
    assert "Some web text." in tekst["params"]["messages"][0]["content"][0]["text"]
    schema = tekst["params"]["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"doet_bewering", "bewering"}
    for woord in ("true or false", "debunk", "verdict", "fact-checked"):
        assert woord not in bewering.VRAAG.lower().replace("do not judge", "")


def test_parts_follow_what_the_user_sends():
    met_tekst = {"P3:00001": True, "P3:00002": False}
    assert bewering.deel_van("P3", "P3:00001", met_tekst) == "screenshot met tekst"
    assert bewering.deel_van("P3", "P3:00002", met_tekst) == "foto zonder tekst"
    assert bewering.deel_van("P2", "P2:x#c", met_tekst) == "artikel"
    assert bewering.deel_van("P1", "P1:x", met_tekst) == "tekst"
    assert bewering.deel_van("N1", "N1:p:x", met_tekst) is None


def test_the_combination_keeps_the_current_match_and_otherwise_takes_the_sentence():
    assert bewering.combinatie("gevonden", "ander") == "gevonden"
    assert bewering.combinatie("ander", "gevonden") == "ander"
    assert bewering.combinatie("verwant", "gevonden") == "gevonden"
    assert bewering.combinatie("niets", "ander") == "ander"
    assert bewering.combinatie("niets", "verwant") == "verwant"
    assert bewering.combinatie("verwant", "niets") == "verwant"
    assert bewering.combinatie("niets", "niets") == "niets"


def _rij(set_, sleutel, helft, deel, huidig, uitkomst, kandidaat=None, bron=None):
    return {"set": set_, "sleutel": sleutel, "helft": helft, "deel": deel, "huidig": huidig,
            "huidig_kandidaat": None, "uitkomst": uitkomst, "kandidaat": kandidaat, "bron": bron}


def test_labels_are_per_pair_so_no_label_of_another_hit_comes_along():
    rijen = [_rij("P3", "P3:1", "ontwikkel", "screenshot met tekst", "niets", "ander", "gfc-b")]
    labels = {bewering.paar("P3:1", "gfc-a"): "zelfde"}
    with pytest.raises(bewering.Weigering):
        bewering.telling(rijen, labels)


def test_counting_refuses_while_a_match_on_web_text_has_no_label():
    rijen = [_rij("N1", "N1:p:1", "ontwikkel", None, "niets", "matched", "gfc-a")]
    with pytest.raises(bewering.Weigering):
        bewering.telling(rijen, {})


def test_the_count_splits_routes_and_parts_and_counts_every_wrong_match():
    rijen = [
        _rij("P3", "P3:1", "ontwikkel", "screenshot met tekst", "niets", "gevonden", "gfc-a"),
        _rij("P3", "P3:2", "ontwikkel", "screenshot met tekst", "verwant", "ander", "gfc-b"),
        _rij("P3", "P3:3", "ontwikkel", "foto zonder tekst", "niets", "niets"),
        _rij("P2", "P2:x#c", "ontwikkel", "artikel", "gevonden", "niets"),
        _rij("N1", "N1:p:1", "ontwikkel", None, "niets", "matched", "gfc-c"),
        _rij("N1", "N1:p:2", "ontwikkel", None, "niets", "none"),
        _rij("N3", "N3:f#0", "ontwikkel", None, "niets", "rood", "gfc-d", bron="kern"),
        _rij("N3", "N3:paar:1", "ontwikkel", None, "niets", "omstreden", "gfc-e", bron="paar"),
    ]
    labels = {bewering.paar("P3:2", "gfc-b"): "anders", bewering.paar("N1:p:1", "gfc-c"): "vals"}
    uit = bewering.telling(rijen, labels)["ontwikkel"]
    assert uit["delen"]["screenshot met tekst"]["combinatie"] == {"n": 2, "gevonden": 1, "zelfde": 0, "anders": 1,
                                                                  "verwant": 0, "niets": 0}
    assert uit["delen"]["screenshot met tekst"]["huidig"]["verwant"] == 1
    assert uit["delen"]["foto zonder tekst"]["combinatie"]["niets"] == 1
    assert uit["delen"]["artikel"]["combinatie"]["gevonden"] == 1
    assert uit["N1"] == {"n": 2, "matched": 1, "terecht": 0, "vals": 1}
    assert uit["N3"] == {"n": 2, "rood": 2, "kern_rood": 1}
    # Juist: twee keer gevonden; fout: een andere bewering, een valse webtekst, twee rode oordelen.
    assert uit["precisie"] == {"juist": 2, "fout": 4}


def test_the_main_number_is_the_mean_of_text_articles_and_images():
    assert bewering.hoofdgetal(p1=0.40, p2=0.10, p3=0.25) == pytest.approx(0.25)


# Stap 2b (PLAN #30.12): Haiku kiest uit de vijf kandidaten van Factiz.

def test_the_decider_sees_numbered_candidates_with_their_date_and_never_a_verdict():
    vraag = bewering.beslis_vraag("Photo shows floods in Chennai.",
                                  [{"tekst": "Floods in Chennai in 2015", "datum": "2015-12-03"},
                                   {"tekst": "Chennai floods 2021", "datum": "2021-11-10"}])
    assert "Photo shows floods in Chennai." in vraag
    assert "1. Floods in Chennai in 2015 (checked 2015-12-03)" in vraag
    assert "2. Chennai floods 2021 (checked 2021-11-10)" in vraag
    for woord in ("verdict", "rating", "debunked"):
        assert woord not in vraag.lower()


def test_a_choice_outside_the_candidates_is_unreadable():
    assert bewering.lees_keuze('{"keuze": 2}', 3) == 2
    assert bewering.lees_keuze('{"keuze": 0}', 3) == 0
    assert bewering.lees_keuze('{"keuze": 4}', 3) is None
    assert bewering.lees_keuze('{"keuze": 1', 3) is None


def test_a_choice_becomes_an_outcome_like_categorize_would_give_it():
    verwacht = {"gfc-a"}
    assert bewering.uitkomst_keuze("P3", None, verwacht, False, None) == "niets"
    assert bewering.uitkomst_keuze("P3", "gfc-a", verwacht, False, None) == "gevonden"
    assert bewering.uitkomst_keuze("P3", "gfc-b", verwacht, False, None) == "ander"
    assert bewering.uitkomst_keuze("P3", "gfc-a", verwacht, True, None) == "verwant"  # DR8
    assert bewering.uitkomst_keuze("N1", "gfc-b", set(), False, None) == "matched"
    assert bewering.uitkomst_keuze("N1", "gfc-b", set(), True, None) == "related"
    assert bewering.uitkomst_keuze("N1", None, set(), False, None) == "none"
    assert bewering.uitkomst_keuze("N3", "gfc-b", set(), False, "rood") == "rood"
    assert bewering.uitkomst_keuze("N3", "gfc-b", set(), False, "groen") == "matched"


def test_the_first_match_in_production_order_wins_over_any_number_of_routes():
    assert bewering.combinatie("niets", "verwant", "gevonden", "ander") == "gevonden"
    assert bewering.combinatie("niets", "niets", "niets", "verwant") == "verwant"


def _route(route, uitkomst, kandidaat=None, label=None):
    return {"route": route, "uitkomst": uitkomst, "kandidaat": kandidaat, "label": label}


def test_the_count_of_step_2b_adds_the_routes_in_production_order():
    rijen = [
        {"set": "P3", "sleutel": "P3:1", "helft": "ontwikkel", "deel": "screenshot met tekst", "bron": None,
         "routes": [_route("huidig", "niets"), _route("bewering", "verwant"), _route("beslisser", "gevonden", "gfc-a")]},
        {"set": "P3", "sleutel": "P3:2", "helft": "ontwikkel", "deel": "foto zonder tekst", "bron": None,
         "routes": [_route("huidig", "niets"), _route("bewering", "niets"), _route("beslisser", "niets"),
                    _route("tweede vraag", "ander", "gfc-x")]},
        {"set": "N1", "sleutel": "N1:p:1", "helft": "ontwikkel", "deel": None, "bron": None,
         "routes": [_route("huidig", "none"), _route("bewering", "none"), _route("beslisser", "matched", "gfc-c")]},
        {"set": "N3", "sleutel": "N3:f#0", "helft": "ontwikkel", "deel": None, "bron": "kern",
         "routes": [_route("huidig", "niets"), _route("bewering", "niets"), _route("beslisser", "rood", "gfc-d")]},
    ]
    labels = {bewering.paar("P3:2", "gfc-x"): "zelfde", bewering.paar("N1:p:1", "gfc-c"): "vals"}
    uit = bewering.telling_routes(rijen, labels)["ontwikkel"]
    assert [s["route"] for s in uit["stappen"]] == ["huidig", "bewering", "beslisser", "tweede vraag"]
    na_beslisser, na_tweede = uit["stappen"][2], uit["stappen"][3]
    assert na_beslisser["delen"]["screenshot met tekst"]["gevonden"] == 1
    assert na_beslisser["N1"] == {"n": 1, "matched": 1, "terecht": 0, "vals": 1}
    assert na_beslisser["N3"] == {"n": 1, "rood": 1, "kern_rood": 1}
    assert na_tweede["delen"]["foto zonder tekst"]["zelfde"] == 1
    assert na_tweede["precisie"] == {"juist": 2, "fout": 2}
    assert uit["stappen"][0]["delen"]["screenshot met tekst"]["gevonden"] == 0


def test_the_count_of_step_2b_refuses_an_unlabelled_choice():
    rijen = [{"set": "P3", "sleutel": "P3:1", "helft": "ontwikkel", "deel": "foto zonder tekst", "bron": None,
              "routes": [_route("huidig", "niets"), _route("beslisser", "ander", "gfc-b")]}]
    with pytest.raises(bewering.Weigering):
        bewering.telling_routes(rijen, {})
