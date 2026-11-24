"""De lezer met de database op tekst (PLAN #32.30, stap 2): `lezer-v3` en `lezer-v5` op dezelfde zoekresultaten, met
één zoekvraag en één keer kring 1 per bericht, en de eisen zoals vooraf vastgelegd."""

import dataclasses
import json
import sqlite3

import pytest

from doublecheck import tekstlezer as tl
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "factcheck.org": [["goed", "IFCN"]], "pesacheck.org": [["goed", "IFCN vernieuwing"]]}
CHECKS = [{"claim": "c1", "tekst": "Een bewering", "redactie": "BOOM", "oordeel": "onwaar", "datum": "2026-08-01",
           "url": "https://www.boomlive.in/x", "beeld": False}]


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class NepModel:
    def __init__(self, d):
        self.d, self.verzoeken, self.messages = d, [], self

    def create(self, **params):
        self.verzoeken.append(params)
        antwoord = type("A", (), {})()
        antwoord.content, antwoord.usage, antwoord.stop_reason = [_Blok(json.dumps(self.d))], _Gebruik(), "end_turn"
        return antwoord


def _brave(*urls):
    return {"web": {"results": [{"url": u, "title": f"t{i}", "description": f"f{i}"} for i, u in enumerate(urls)]}}


def _configs():
    c = load_config()
    return {arm: dataclasses.replace(c, berichtcontrole=dataclasses.replace(c.berichtcontrole, lezer=lezer, beeld=False))
            for arm, lezer in tl.LEZERS.items()}


def test_both_readers_read_the_same_search_and_the_first_ring_is_asked_once():
    gezocht, gevraagd, checks = [], [], []
    zoek = lambda q: gezocht.append(q) or _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa
    snel = lambda t: gevraagd.append(t)  # noqa: E731 - geeft None: kring 1 heeft niets
    nep = NepModel({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [], "uitleg": "", "checks": []})
    uit = tl.twee({"id": "W:1", "set": "W", "tekst": "Een waar bericht.", "datum": None}, _configs(), nep, zoek, snel,
                  SITES, lambda tekst, verborgen: checks.append(verborgen) or CHECKS)
    assert len(gezocht) == 1 and len(gevraagd) == 1 and checks == [frozenset()]
    assert [uit[a]["kleur"] for a in tl.ARMEN] == ["groen", "groen"]
    assert "[D1] BOOM" not in nep.verzoeken[0]["messages"][0]["content"]
    assert "[D1] BOOM" in nep.verzoeken[1]["messages"][0]["content"]
    assert uit["5"]["kosten"] < uit["3"]["kosten"] + 0.01  # de zoekvraag één keer betaald, bij arm 3


def test_unknown_fake_news_skips_the_first_ring_drops_fact_checkers_and_hides_its_own_check():
    gevraagd, checks = [], []
    zoek = lambda q: _brave("https://www.factcheck.org/x", "https://pesacheck.org/y", "https://www.nytimes.com/a")  # noqa
    nep = NepModel({"oordeel": "onzeker", "steunt": [], "spreekt_tegen": [], "uitleg": "", "checks": []})
    tl.twee({"id": "O:gfc-9", "set": "O'", "tekst": "Een nepbericht.", "datum": "2026-09-01", "claim": "gfc-9",
             "verborgen": frozenset({"gfc-9", "gfc-10"})}, _configs(), nep, zoek, lambda t: gevraagd.append(t), SITES,
            lambda tekst, verborgen: checks.append(verborgen) or [])
    assert gevraagd == [] and checks == [frozenset({"gfc-9", "gfc-10"})]
    tekst = nep.verzoeken[0]["messages"][0]["content"]
    assert "factcheck.org" not in tekst and "pesacheck.org" not in tekst and "[1] nytimes.com" in tekst


def test_an_answer_from_the_first_ring_is_the_same_in_both_arms_and_costs_nothing():
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    nep = NepModel({})
    uit = tl.twee({"id": "W:2", "set": "W", "tekst": "x", "datum": None}, _configs(), nep, lambda q: _brave(),
                  lambda t: snel, SITES, lambda tekst, verborgen: [])
    assert uit["3"]["route"] == uit["5"]["route"] == "database" and nep.verzoeken == []
    assert uit["3"]["kosten"] == uit["5"]["kosten"] == 0.0


def _rij(id_, set_, arm, kleur):
    return {"id": id_, "set": set_, "arm": arm, "kleur": kleur, "oordeel": "-", "kosten": 0.0, "seconden": 1.0}


def test_the_count_refuses_while_an_alarm_on_a_true_message_or_a_green_on_fake_news_has_no_label():
    rijen = [_rij("W:1", "W", "5", "rood"), _rij("W:1", "W", "3", None), _rij("O:1", "O'", "3", "groen"),
             _rij("O:1", "O'", "5", None)]
    with pytest.raises(tl.Weigering):
        tl.telling(rijen, {("W:1", "5"): "vals"})
    tel = tl.telling(rijen, {("W:1", "5"): "vals", ("O:1", "3"): "vals"})
    assert tel["W"]["5"]["vals alarm"] == 1 and tel["W"]["3"]["vals alarm"] == 0
    assert tel["O'"]["3"]["vals groen"] == 1


def test_the_requirements_are_those_set_in_advance():
    rijen, labels = [], {}
    for i in range(300):
        rijen += [_rij(f"W:{i}", "W", "3", "groen"), _rij(f"W:{i}", "W", "5", "rood" if i < 3 else "groen")]
    for i in range(3):
        labels[(f"W:{i}", "5")] = "vals"
    for i in range(50):
        rijen += [_rij(f"V:{i}", "W'", "3", None), _rij(f"V:{i}", "W'", "5", None)]
    for i in range(100):
        rijen += [_rij(f"O:{i}", "O'", "3", None), _rij(f"O:{i}", "O'", "5", None)]
    eisen = tl.telling(rijen, labels)["eisen"]
    # 3 van 300 haalt B45, maar het zijn er meer dan bij lezer-v3 (0): eis 1 niet gehaald
    assert eisen == {"W: hoogstens 3 van 300 vals alarm": True, "W: niet meer vals alarm dan lezer-v3": False,
                     "W': niet meer vals alarm dan lezer-v3": True, "O': niet meer onterecht groen dan lezer-v3": True}


def test_a_label_that_does_not_exist_is_refused():
    with pytest.raises(tl.Weigering):
        tl.lees_labels({"toelichting": "", "oordelen": [{"id": "W:1", "arm": "5", "label": "misschien"}]})


def test_the_measurement_borrows_the_reader_and_the_lookup_from_the_core():
    assert tl.zc is zc
