"""De nieuwe controle op 500 berichten uit ronde 4 (PLAN #32.11)."""

import pytest

from doublecheck import controle500 as c


def _a(kleur, streng=None, seconden=3.0, kosten=0.01, oordeel="klopt"):
    return {"kleur": kleur, "kleur_streng": streng if streng is not None else kleur, "seconden": seconden,
            "kosten": kosten, "oordeel": oordeel, "route": "zoeken", "staatsmedia": 0}


STUKKEN = [{"id": "w1", "deel": "W"}, {"id": "w2", "deel": "W"}, {"id": "b1", "deel": "B"}, {"id": "o1", "deel": "O"}]


def test_an_alarm_on_a_true_message_and_green_on_fake_news_must_be_read_before_counting():
    antwoorden = {"w1": _a("oranje"), "w2": _a("groen"), "b1": _a("rood"), "o1": _a("groen")}
    with pytest.raises(c.Weigering):
        c.telling(STUKKEN, antwoorden, {"w1": "vals"})
    uit = c.telling(STUKKEN, antwoorden, {"w1": "vals", "o1": "set fout"})
    assert uit["W"]["vals alarm"] == 1 and uit["O"]["vals groen"] == 0
    assert uit["eisen"]["ware berichten"] == "niet gehaald"  # 1 van 2 is meer dan 3 van 300
    assert uit["eisen"]["nepberichten: hoogstens 1 op 100 onterecht groen"]


def test_the_level_of_b45_is_the_strictest_one_met():
    stukken = [{"id": f"w{i}", "deel": "W"} for i in range(300)]
    for vals, niveau in ((3, "99%"), (4, "98%"), (9, "97%"), (10, "niet gehaald")):
        antwoorden = {f"w{i}": _a("rood" if i < vals else "groen") for i in range(300)}
        uit = c.telling(stukken, antwoorden, {f"w{i}": "vals" for i in range(vals)})
        assert uit["W"]["vals alarm"] == vals and uit["eisen"]["ware berichten"] == niveau
    # een rood dat bij lezing een fout in de set blijkt, telt niet als vals alarm
    antwoorden = {f"w{i}": _a("rood" if i < 5 else "groen") for i in range(300)}
    uit = c.telling(stukken, antwoorden, {**{f"w{i}": "vals" for i in range(3)}, "w3": "set fout", "w4": "set fout"})
    assert uit["W"]["vals alarm"] == 3 and uit["eisen"]["ware berichten"] == "99%"


def test_without_fact_checkers_the_results_lose_every_ifcn_signatory():
    res = [{"nr": 1, "factcheck": True}, {"nr": 2, "factcheck": False}, {"nr": 3, "factcheck": True}]
    assert [r["nr"] for r in c.zonder_factcheckers(res)] == [1]
