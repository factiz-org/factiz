"""De eindtoets van de hele keten, met labels van de PO (PLAN #32.8)."""

import pytest

from doublecheck import eindtoets as e

DAG = """{{Current events|year=2026|month=10|day=27|top=yes}}
'''Armed conflicts and attacks'''
*[[Gaza war]]
**[[Israeli bombing of the Gaza Strip]]
***Three people, including a child, are killed in an [[Israel]]i [[airstrike]] against a [[tent]] in [[Khan Yunis]], [[Gaza Strip]]. [https://english.aawsat.com/x (Asharq Al-Awsat)]
**The casualty toll in [[Taraba State|Taraba]] increases to 62. [https://apnews.com/article/x (AP)] [https://www.bbc.com/news/y (BBC)]
*[[War on drugs]]
"""


def test_a_portal_day_gives_its_event_sentences_without_markup_or_sources():
    assert e.portal_zinnen(DAG) == [
        "Three people, including a child, are killed in an Israeli airstrike against a tent in Khan Yunis, Gaza Strip.",
        "The casualty toll in Taraba increases to 62."]


def _a(kleur, oordeel="klopt niet", seconden=4.0, kosten=0.05):
    return {"kleur": kleur, "oordeel": oordeel, "seconden": seconden, "kosten": kosten}


def test_the_count_refuses_while_a_message_has_no_label_of_the_po():
    stukken = [{"id": "k1", "deel": "K"}, {"id": "w1", "deel": "W"}]
    antwoorden = {"k1": _a("rood"), "w1": _a("rood")}
    with pytest.raises(e.Weigering):
        e.telling(stukken, antwoorden, {"k1": "klopt"})
    uit = e.telling(stukken, antwoorden, {"k1": "klopt", "w1": "klopt niet"})
    assert uit["per deel"]["W"]["onterecht rood"] == 1 and uit["per deel"]["K"]["klopt"] == 1
    assert uit["samen"]["n"] == 2 and uit["samen"]["klopt"] == 1


def test_green_on_a_false_message_and_no_colour_are_counted_apart():
    stukken = [{"id": "v1", "deel": "V"}, {"id": "v2", "deel": "V"}, {"id": "w1", "deel": "W"}]
    antwoorden = {"v1": _a("groen", "klopt"), "v2": _a(None, "onzeker"), "w1": _a(None, "onzeker")}
    uit = e.telling(stukken, antwoorden, {"v1": "klopt niet", "v2": "te voorzichtig", "w1": "klopt"})
    assert uit["per deel"]["V"]["onterecht groen"] == 1 and uit["per deel"]["V"]["geen kleur"] == 1
    assert uit["per deel"]["V"]["te voorzichtig"] == 1 and uit["per deel"]["W"]["geen kleur"] == 1
    assert uit["tijd"]["p95"] == 4.0 and uit["kosten per bericht"] == 0.05
