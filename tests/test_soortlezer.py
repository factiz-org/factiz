"""De soort nepnieuws, de voormeting (PLAN #34.2aj): de vraag krijgt nooit het artikel, het antwoord wordt streng
gelezen, en de telling en de lat zijn de eisen die vooraf in PLAN staan."""

import json

from doublecheck import soortlezer as sl


def _item(**extra):
    return {"bewering": "Video shows a flood in Valencia", "engels": "", "oordelen": ["False context"], "label": "onwaar",
            **extra}


def test_the_question_holds_only_the_claim_the_rating_words_and_the_verdict_never_an_article():
    verzoek = sl.soortverzoek([_item(artikel="DIT IS HET ARTIKEL", engels="A video shows a flood")])
    tekst = verzoek["messages"][0]["content"][0]["text"]
    assert "Video shows a flood in Valencia" in tekst and "False context" in tekst and "onwaar" in tekst
    assert "English: A video shows a flood" in tekst and "DIT IS HET ARTIKEL" not in tekst
    schema = verzoek["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]
    # dezelfde schaal als truc-v1 uit het artikel (#32.39), anders valt er niets te vergelijken
    assert set(schema["soort"]["enum"]) == set(sl.TRUCS) and set(schema["vorm"]["enum"]) == set(sl.VORMEN)
    assert "haiku" in verzoek["model"]


def test_an_answer_counts_only_with_a_known_form_and_kind_on_a_number_that_appears_once():
    tekst = json.dumps({"antwoorden": [{"nr": 1, "vorm": "video", "soort": "false context"},
                                       {"nr": 2, "vorm": "video", "soort": "invented kind"},
                                       {"nr": 3, "vorm": "photo", "soort": "satire"}, {"nr": 3, "vorm": "photo", "soort": "satire"},
                                       {"nr": 9, "vorm": "photo", "soort": "satire"}]})
    assert sl.lees_soorten(tekst, 4) == [{"vorm": "video", "soort": "false context"}, None, None, None]
    assert sl.lees_soorten("geen json", 2) == [None, None]
    assert sl.lees_soorten(None, 1) == [None]


def test_neighbours_that_get_confused_are_counted_as_one_kind_and_unclear_as_none():
    assert sl.groep("false context") == sl.groep("false connection") == "uit zijn verband"
    assert sl.groep("imposter") == sl.groep("manipulated")
    assert sl.groep("misleading") != sl.groep("false context")
    assert sl.groep("unclear") is None and sl.groep(None) is None
    assert set(sl.GROEPEN) == set(sl.TRUCS) - {"unclear"}


def test_the_count_measures_precision_on_the_confirmed_coverage_on_all_and_agreement_with_the_article():
    rijen = [
        {"soort": "false context", "truc": "false connection", "bevestigd": True},   # zelfde groep: goed
        {"soort": "fabricated", "truc": "false context", "bevestigd": True},         # fout
        {"soort": "unclear", "truc": "satire", "bevestigd": True},                   # niet gedekt
        {"soort": "satire", "truc": "satire", "bevestigd": None},
        {"soort": "misleading", "truc": "unclear", "bevestigd": False},              # artikel zegt niets: telt niet mee
    ]
    t = sl.telling(rijen)
    assert (t["n"], t["gedekt"], t["bevestigd"], t["bevestigd_gedekt"], t["bevestigd_goed"]) == (5, 4, 3, 2, 1)
    assert t["precisie"] == 0.5 and t["dekking"] == 0.8
    assert t["overeenkomst_n"] == 3 and abs(t["overeenkomst"] - 2 / 3) < 1e-9
    assert t["per_groep"]["uit zijn verband"] == {"artikel": 2, "zelfde": 1}


def test_the_bar_is_the_one_fixed_in_the_plan():
    assert (sl.PRECISIE, sl.DEKKING, sl.OVEREENKOMST) == (0.90, 0.50, 0.75)
    goed = {"precisie": .92, "dekking": .6, "overeenkomst": .8, "bevestigd_goed": 23, "bevestigd_gedekt": 25,
            "gedekt": 6, "n": 10}
    assert sl.lat(goed) == (True, [])
    gehaald, mis = sl.lat({**goed, "precisie": .85, "dekking": .3})
    assert not gehaald and len(mis) == 2 and "precisie" in mis[0] and "dekking" in mis[1]
