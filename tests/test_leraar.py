"""De leraarladder (PLAN #31.2, E8.S2): de regels die vóór de meting vastlagen."""

import json

import pytest

from doublecheck import leraar


def test_the_answer_is_false_or_no_verdict_with_one_reason():
    assert leraar.lees_oordeel(json.dumps({"oordeel": "onwaar", "reden": " Debunked hoax. "})) == \
        ("onwaar", "Debunked hoax.")
    assert leraar.lees_oordeel(json.dumps({"oordeel": "geen-oordeel", "reden": ""})) == ("geen-oordeel", "")
    assert leraar.lees_oordeel('{"oordeel": "onwaar", "reden": "cut') == ("onleesbaar", None)
    assert leraar.lees_oordeel(json.dumps({"oordeel": "waar", "reden": "x"})) == ("onleesbaar", None)


def test_the_question_never_offers_true_as_an_answer():
    schema = leraar.verzoek({"id": "b-000001", "tekst": "x"}, "haiku")["params"]["output_config"]["format"]["schema"]
    assert schema["properties"]["oordeel"]["enum"] == ["onwaar", "geen-oordeel"]


def test_how_an_answer_counts_depends_only_on_the_label():
    assert leraar.uitkomst("onwaar", "onwaar") == "herkend"
    assert leraar.uitkomst("onwaar", "geen-oordeel") == "gemist"
    assert leraar.uitkomst("waar", "onwaar") == "valse vlag"
    assert leraar.uitkomst("waar", "geen-oordeel") == "goed"
    assert leraar.uitkomst("neutraal", "onwaar") == "te lezen"
    assert leraar.uitkomst("neutraal", "geen-oordeel") == "goed"


def _stuk(i, soort, label, helft="ontwikkel", bron="b", vers=False):
    return {"id": f"b-{i:06d}", "sleutel": f"k{i}", "soort": soort, "label": label, "helft": helft, "bron": bron,
            "vers": vers, "taal": "en"}


def test_the_sample_keeps_the_layers_and_always_takes_every_fact_and_every_fresh_piece():
    stukken = [_stuk(i, "artikel", "waar") for i in range(60)] + [_stuk(100 + i, "tekst", "onwaar") for i in range(40)] \
        + [_stuk(200, "feit", "waar", bron="n3-kern"), _stuk(201, "tekst", "onwaar", vers=True)]
    gekozen = leraar.steekproef(stukken, 10, zaad=3001)
    ids = {s["id"] for s in gekozen}
    assert "b-000200" in ids and "b-000201" in ids
    gewoon = [s for s in gekozen if s["soort"] != "feit" and not s["vers"]]
    assert sum(s["soort"] == "artikel" for s in gewoon) == 6 and sum(s["soort"] == "tekst" for s in gewoon) == 4
    assert [s["id"] for s in gekozen] == [s["id"] for s in leraar.steekproef(stukken, 10, zaad=3001)]


def test_the_count_refuses_while_a_flag_on_web_text_has_no_label():
    stukken = [_stuk(1, "webtekst", "neutraal")]
    with pytest.raises(leraar.Weigering):
        leraar.telling(stukken, {"b-000001": "onwaar"}, {})


def test_the_count_separates_recognised_false_flags_the_core_and_fresh_pieces():
    stukken = [_stuk(1, "tekst", "onwaar"), _stuk(2, "tekst", "onwaar", vers=True), _stuk(3, "artikel", "waar"),
               _stuk(4, "feit", "waar", bron="n3-kern"), _stuk(5, "webtekst", "neutraal"),
               _stuk(6, "webtekst", "neutraal"), _stuk(7, "tekst", "onwaar", helft="toets")]
    oordelen = {"b-000001": "onwaar", "b-000002": "geen-oordeel", "b-000003": "onwaar", "b-000004": "onwaar",
                "b-000005": "onwaar", "b-000006": "geen-oordeel", "b-000007": "onwaar"}
    uit = leraar.telling(stukken, oordelen, {"k5": "vals"})
    o = uit["ontwikkel"]
    assert o["per soort en label"]["tekst onwaar"] == {"n": 1, "herkend": 1}
    assert o["vers"] == {"n": 1, "herkend": 0}
    assert o["valse vlag op waar"] == {"n": 2, "vlag": 2}
    assert o["kern"] == {"n": 1, "vlag": 1}
    assert o["webtekst"] == {"n": 2, "vlag": 1, "terecht": 0}
    assert uit["toets"]["per soort en label"]["tekst onwaar"] == {"n": 1, "herkend": 1}


def test_a_batch_above_the_remaining_budget_is_refused():
    with pytest.raises(leraar.Weigering):
        leraar.binnen_budget(geschat=12.0, al_uitgegeven=40.0, budget=50.0)
    leraar.binnen_budget(geschat=9.0, al_uitgegeven=40.0, budget=50.0)
