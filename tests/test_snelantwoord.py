"""Het snelle antwoord (PLAN #32.0o): wat Factiz zonder taalmodel kan zeggen, en
wanneer dat genoeg is. De regels die vóór de meting vastlagen."""

import pytest

from doublecheck import snelantwoord as sn


def _antwoord(categorie, *oordelen):
    checks = [{"verdict_normalized": o, "publisher": "AFP"} for o in oordelen]
    return {"category": categorie, "evidence": {"checks": checks} if checks else None}


def test_only_matched_with_checks_that_all_point_one_way_is_a_fast_answer():
    assert sn.snel_oordeel(_antwoord("matched", "onwaar", "misleidend")) == "onwaar"
    assert sn.snel_oordeel(_antwoord("matched", "waar", "waar")) == "waar"
    assert sn.snel_oordeel(_antwoord("matched", "onwaar", "waar")) is None
    assert sn.snel_oordeel(_antwoord("matched", "deels-waar")) is None
    assert sn.snel_oordeel(_antwoord("matched", "satire")) is None
    assert sn.snel_oordeel(_antwoord("related", "onwaar")) is None
    assert sn.snel_oordeel(_antwoord("none")) is None


def test_a_fast_answer_is_right_wrong_or_goes_on_to_the_deep_check():
    assert sn.uitkomst("onwaar", "onwaar") == "goed" and sn.uitkomst("misleidend", "onwaar") == "goed"
    assert sn.uitkomst("waar", "waar") == "goed"
    assert sn.uitkomst("waar", "onwaar") == "fout" and sn.uitkomst("onwaar", "waar") == "fout"
    assert sn.uitkomst("waar", None) == "verder"


def test_the_count_names_a_wrong_fast_answer_on_a_true_message_apart_and_needs_it_read():
    rijen = [{"id": "a", "groep": "bekend", "label": "onwaar", "snel": "onwaar", "seconden": 0.2},
             {"id": "b", "groep": "bekend", "label": "onwaar", "snel": None, "seconden": 0.3},
             {"id": "c", "groep": "waar", "label": "waar", "snel": "onwaar", "seconden": 0.25}]
    with pytest.raises(sn.Weigering):
        sn.telling(rijen, {})
    t = sn.telling(rijen, {"c": "vals"})
    assert t["groepen"]["bekend"] == {"n": 2, "snel": 1, "goed": 1, "fout": 0, "verder": 1}
    assert t["groepen"]["waar"]["fout"] == 1 and t["fout bij een waar bericht"] == 1
    assert t["alles"]["snel"] == 2 and t["tijd"]["p50"] == 0.25
    assert sn.telling(rijen, {"c": "set fout"})["fout bij een waar bericht"] == 0


def test_the_percentile_is_the_nearest_rank():
    assert sn.percentiel([0.1, 0.2, 0.3, 0.4], 0.5) == 0.2
    assert sn.percentiel([float(i) for i in range(1, 101)], 0.95) == 95.0
