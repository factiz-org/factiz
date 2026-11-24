"""De speurstap (PLAN #32.40, PO 2026-11-04): zegt de lezer *onzeker*, dan zoekt hij zelf verder zoals een
factchecker, op de eigen site van wie het bericht noemt, naar het echte nieuws en naar de bron zelf, en leest hij alles
nog één keer. Standaard uit; de kleur volgt dezelfde regels."""

import dataclasses
import json
import sqlite3

import pytest

from doublecheck import berichtcontrole as bc
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "euronews.com": [["goed", "Lin e.a. 0.82"]]}
BERICHT = "euronews. UKRAINE: Kyrylo Budanov was aware of secret torture centres in Ukraine."


def _config(**instellingen):
    config = load_config()
    standaard = {"lezer": "lezer-v8"}
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole,
                                                                           **{**standaard, **instellingen}))


def _brave(*urls):
    return {"web": {"results": [{"url": u, "title": f"titel {u}", "description": f"fragment {u}"} for u in urls]}}


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class _Antwoord:
    def __init__(self, d):
        self.content, self.usage, self.stop_reason = [_Blok(json.dumps(d))], _Gebruik(), "end_turn"


def _oordeel(oordeel="onzeker", steunt=(), tegen=(), verder=()):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Uitleg.",
            "over_beeld": False, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
            "verder_zoeken": list(verder)}


class Reeks:
    """Een nepmodel dat per vraag het volgende antwoord geeft."""

    def __init__(self, *antwoorden):
        self.antwoorden, self.verzoeken, self.messages = list(antwoorden), [], self

    def create(self, **params):
        self.verzoeken.append(params)
        return _Antwoord(self.antwoorden[len(self.verzoeken) - 1])


EIGEN = {"soort": "eigen site", "vraag": "Budanov secret torture centres", "site": "https://www.euronews.com/news"}
NIEUWS = {"soort": "echt nieuws", "vraag": "Budanov torture centres Ukraine November 2026", "site": ""}


def test_the_further_searches_are_read_strictly_and_never_more_than_three():
    verder = zc.speurvragen([EIGEN, NIEUWS, {"soort": "eigen site", "vraag": "x y", "site": "geen domein"},
                             {"soort": "raden", "vraag": "a b", "site": ""}, {"soort": "bron zelf", "vraag": " ", "site": ""},
                             NIEUWS, {"soort": "bron zelf", "vraag": "UN report secret prisons", "site": "ohchr.org"},
                             {"soort": "echt nieuws", "vraag": "vierde", "site": ""}])
    assert verder == [{"soort": "eigen site", "vraag": "Budanov secret torture centres", "site": "euronews.com"},
                      {"soort": "echt nieuws", "vraag": "Budanov torture centres Ukraine November 2026", "site": ""},
                      {"soort": "bron zelf", "vraag": "UN report secret prisons", "site": "ohchr.org"}]
    assert zc.speurvragen(None) == [] and zc.speurvragen("geen lijst") == []


def test_a_search_on_a_named_website_uses_the_site_operator_and_the_real_news_does_not():
    assert zc.brave_vraag({"soort": "eigen site", "vraag": "Budanov", "site": "euronews.com"}) == \
        "site:euronews.com Budanov"
    assert zc.brave_vraag({"soort": "bron zelf", "vraag": "rapport", "site": ""}) == "rapport"
    assert zc.brave_vraag({"soort": "echt nieuws", "vraag": "Budanov", "site": "euronews.com"}) == "Budanov"


def test_the_step_numbers_new_results_after_the_first_and_counts_a_page_once():
    eerste = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"), SITES)
    antwoorden = {"site:euronews.com Budanov secret torture centres": _brave(),
                  NIEUWS["vraag"]: _brave("https://edition.cnn.com/b", "https://www.euronews.com/c")}
    alle, groepen = zc.speur(zc.speurvragen([EIGEN, NIEUWS]), eerste, antwoorden.__getitem__, SITES)
    assert [r["nr"] for r in alle] == [1, 2, 3] and alle[2]["url"] == "https://www.euronews.com/c"
    assert [(g["soort"], g["nrs"], g["gevonden"]) for g in groepen] == [("eigen site", [], 0),
                                                                     ("echt nieuws", [2, 3], 2)]


def test_the_first_reading_asks_for_further_searches_and_the_second_never():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    eerste = zc.leesverzoek(BERICHT, res, None, _config(), checks=[])
    assert "verder_zoeken" in eerste["output_config"]["format"]["schema"]["required"]
    groepen = [{"soort": "eigen site", "vraag": "Budanov", "site": "euronews.com", "nrs": [], "gevonden": 0}]
    tweede = zc.leesverzoek(BERICHT, res, None, _config(), checks=[], groepen=groepen)
    assert "verder_zoeken" not in tweede["output_config"]["format"]["schema"]["properties"]
    tekst = tweede["messages"][0]["content"]
    assert "(eigen site, on euronews.com): Budanov" in tekst and "(no results)" in tekst
    with pytest.raises(bc.VersieFout):
        zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v7"), checks=[], groepen=groepen)


def test_an_answer_without_further_searches_reads_as_an_empty_list():
    assert zc.lees_oordeel(json.dumps({**_oordeel(), "verder_zoeken": "nee"}))["verder"] == []
    assert zc.lees_oordeel(json.dumps(_oordeel(verder=[EIGEN])))["verder"][0]["site"] == "euronews.com"


def _controleer(model, config, gezocht):
    def zoek(q):
        gezocht.append(q)
        return (_brave("https://www.euronews.com/c", "https://www.nytimes.com/d") if q.startswith("Budanov torture")
                else _brave("https://www.nytimes.com/a"))
    kosten = sqlite3.connect(":memory:")
    return zc.controleer(kosten, BERICHT, config, model, zoek, lambda t: None, SITES, "2026-11-04",
                         zoek_checks=lambda t: []), kosten


def test_without_the_switch_the_check_never_searches_further():
    model, gezocht = Reeks(_oordeel(verder=[EIGEN, NIEUWS])), []
    uit, _ = _controleer(model, _config(speuren=False), gezocht)
    assert len(gezocht) == 1 and len(model.verzoeken) == 1 and uit["uitkomst"] == "onzeker"


def test_with_the_switch_an_uncertain_answer_searches_further_and_reads_once_more():
    model = Reeks(_oordeel(verder=[EIGEN, NIEUWS]), _oordeel("klopt niet", tegen=(2, 3)))
    gezocht = []
    uit, kosten = _controleer(model, _config(speuren=True), gezocht)
    assert gezocht[1:] == ["site:euronews.com Budanov secret torture centres", NIEUWS["vraag"]]
    assert len(model.verzoeken) == 2 and uit["kleur"] == "rood"
    assert [g["soort"] for g in uit["speurstap"]] == ["eigen site", "echt nieuws"]
    assert bc.uitgegeven(kosten, "2026-11-04") == pytest.approx(uit["kosten"])
    assert uit["kosten"] > 3 * zc.ZOEKPRIJS


def test_a_confident_first_answer_does_not_search_further():
    model, gezocht = Reeks(_oordeel("klopt niet", tegen=(1,), verder=[NIEUWS])), []
    uit, _ = _controleer(model, _config(speuren=True), gezocht)
    assert len(gezocht) == 1 and len(model.verzoeken) == 1 and uit["kleur"] == "rood" and uit["speurstap"] == []
