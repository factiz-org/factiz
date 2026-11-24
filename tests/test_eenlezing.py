"""Eén lezing met de zoekvragen vooraf, en de uitkomst *niet bevestigd* (B57, PLAN #32.41): Haiku bedenkt de
zoekvragen zoals een factchecker, alles gaat tegelijk naar de zoekdienst, Sonnet leest één keer; wat betrouwbare media
zouden melden als het waar was, maar niemand betrouwbaars meldt, is *niet bevestigd*, zonder kleur."""

import dataclasses
import json
import sqlite3
import threading

import pytest

from doublecheck import api
from doublecheck import berichtcontrole as bc
from doublecheck import speurvraag as sv
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "euronews.com": [["goed", "Lin e.a. 0.82"]]}
BERICHT = "euronews. UKRAINE: Kyrylo Budanov was aware of secret torture centres in Ukraine."
EIGEN = {"soort": "eigen site", "vraag": "Budanov secret torture centres", "site": "euronews.com"}
NIEUWS = {"soort": "echt nieuws", "vraag": "Budanov torture centres Ukraine November 2026", "site": ""}


def _config(**instellingen):
    config = load_config()
    standaard = {"lezer": "lezer-v9", "speurvraag_model": "claude-haiku-5-5"}
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


def _oordeel(oordeel="onzeker", steunt=(), tegen=(), zou_gemeld=True, vorm="zelf"):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Uitleg.",
            "over_beeld": False, "checks": [], "vorm": vorm, "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": zou_gemeld}


class Reeks:
    def __init__(self, *antwoorden):
        self.antwoorden, self.verzoeken, self.messages = list(antwoorden), [], self

    def create(self, **params):
        self.verzoeken.append(params)
        return _Antwoord(self.antwoorden[len(self.verzoeken) - 1])


# --- de vraag aan Haiku, in de kern ---------------------------------------------------------------------------

def test_haiku_plans_the_searches_with_a_fixed_schema_and_never_judges():
    params = sv.verzoek(BERICHT, "2026-11-03", "claude-haiku-5-5")
    assert params["model"] == "claude-haiku-5-5" and "tools" not in params
    assert params["output_config"]["format"]["schema"]["required"] == ["verder_zoeken"]
    tekst = params["messages"][0]["content"]
    assert BERICHT in tekst and "2026-11-03" in tekst and "never judge" in params["system"]


def test_haiku_has_room_to_think_and_still_answer():
    assert sv.verzoek(BERICHT, None, "claude-haiku-5-5")["max_tokens"] >= 1000


def test_with_the_image_haiku_sees_the_blackened_picture_first():
    params = sv.verzoek(BERICHT, None, "claude-haiku-5-5", beeld=b"\x89PNG....")
    blokken = params["messages"][0]["content"]
    assert blokken[0]["type"] == "image" and blokken[1]["type"] == "text"


def test_the_planned_searches_are_read_strictly():
    tekst = json.dumps({"verder_zoeken": [EIGEN, NIEUWS, {"soort": "raden", "vraag": "x", "site": ""}]})
    assert sv.lees(tekst) == [EIGEN, NIEUWS]
    assert sv.lees("geen JSON") == [] and sv.lees(json.dumps({"verder_zoeken": "nee"})) == []


# --- tegelijk zoeken -------------------------------------------------------------------------------------------

def test_the_message_and_the_planned_searches_run_at_the_same_time_and_a_failure_is_no_result():
    gestart, samen = [], threading.Barrier(3, timeout=5)

    def zoek(q):
        gestart.append(q)
        samen.wait()  # alle drie tegelijk, anders loopt de test vast
        if q.startswith("site:"):
            raise OSError("402")
        return _brave("https://www.nytimes.com/a") if q == zc.zoekvraag(BERICHT) else \
            _brave("https://www.nytimes.com/a", "https://www.euronews.com/c")

    alle, groepen = zc.zoek_tegelijk(BERICHT, [EIGEN, NIEUWS], zoek, SITES)
    assert len(gestart) == 3
    assert [r["url"] for r in alle] == ["https://www.nytimes.com/a", "https://www.euronews.com/c"]
    assert [(g["soort"], g["nrs"], g["gevonden"], g["fout"]) for g in groepen] == [
        ("eigen site", [], 0, True), ("echt nieuws", [1, 2], 2, False)]


# --- de lezer en niet bevestigd --------------------------------------------------------------------------------

def test_v9_reads_once_with_the_results_per_search_and_asks_whether_it_would_be_reported():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    params = zc.leesverzoek(BERICHT, res, None, _config(), checks=[], groepen=[])
    schema = params["output_config"]["format"]["schema"]
    assert "zou_gemeld" in schema["required"] and "verder_zoeken" not in schema["properties"]
    assert "Search 1, the message itself:" in params["messages"][0]["content"]


def _na(antwoord, steunt_urls=(), gezocht=True):
    res = zc.resultaten_uit(_brave(*steunt_urls) if steunt_urls else _brave("https://blog.example/x"), SITES)
    return zc.na_lezen(zc.lees_oordeel(json.dumps(antwoord)), BERICHT, res, [], "lezer-v9", False, gezocht=gezocht)


def test_what_reliable_media_would_report_but_none_does_is_not_confirmed_without_a_colour():
    uit = _na(_oordeel("onzeker", steunt=(1,)))
    assert uit["uitkomst"] == "niet bevestigd" and uit["kleur"] is None


def test_never_not_confirmed_for_a_small_matter_without_own_searches_or_when_a_good_source_confirms():
    assert _na(_oordeel("onzeker", zou_gemeld=False))["uitkomst"] == "onzeker"
    assert _na(_oordeel("onzeker"), gezocht=False)["uitkomst"] == "onzeker"
    assert _na(_oordeel("klopt grotendeels", steunt=(1,)), steunt_urls=("https://www.nytimes.com/a",))["uitkomst"] \
        == "onzeker"
    assert _na(_oordeel("onzeker", vorm="over een bewering"))["uitkomst"] == "over een bewering"
    assert _na(_oordeel("geen bewering"))["uitkomst"] == "geen bewering"


def test_older_readers_never_say_not_confirmed():
    res = zc.resultaten_uit(_brave("https://blog.example/x"), SITES)
    uit = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), BERICHT, res, [], "lezer-v7", False, gezocht=True)
    assert uit["uitkomst"] == "onzeker"


def test_the_api_calls_it_unconfirmed():
    assert api._UITKOMST_EN["niet bevestigd"] == "unconfirmed"


# --- de hele controle ------------------------------------------------------------------------------------------

def _zoek(gezocht):
    slot = threading.Lock()

    def zoek(q):
        with slot:
            gezocht.append(q)
        return _brave("https://blog.example/x")
    return zoek


def test_one_haiku_question_one_reading_and_all_searches_at_once():
    model = Reeks({"verder_zoeken": [EIGEN, NIEUWS]}, _oordeel("onzeker", steunt=(1,)))
    gezocht, kosten = [], sqlite3.connect(":memory:")
    uit = zc.controleer(kosten, BERICHT, _config(), model, _zoek(gezocht), lambda t: None, SITES, "2026-11-05",
                        zoek_checks=lambda t: [])
    assert model.verzoeken[0]["model"] == "claude-haiku-5-5" and len(model.verzoeken) == 2
    assert sorted(gezocht) == sorted([zc.zoekvraag(BERICHT), "site:euronews.com Budanov secret torture centres",
                                      NIEUWS["vraag"]])
    assert uit["uitkomst"] == "niet bevestigd" and uit["kleur"] is None
    assert [g["soort"] for g in uit["speurstap"]] == ["eigen site", "echt nieuws"]
    assert bc.uitgegeven(kosten, "2026-11-05") == pytest.approx(uit["kosten"]) and uit["kosten"] > 3 * zc.ZOEKPRIJS


def test_without_a_model_for_the_searches_the_check_refuses_before_any_cost():
    model, gezocht = Reeks(), []
    with pytest.raises(bc.VersieFout):
        zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(speurvraag_model=""), model, _zoek(gezocht),
                      lambda t: None, SITES, None, zoek_checks=lambda t: [])
    assert model.verzoeken == [] and gezocht == []


def test_a_failed_search_is_no_search_of_its_own():
    assert not zc.zelf_gezocht([{"soort": "echt nieuws", "fout": True}]) and not zc.zelf_gezocht([])
    assert zc.zelf_gezocht([{"soort": "echt nieuws", "fout": True}, {"soort": "bron zelf", "fout": False}])


def test_a_fact_check_about_the_same_claim_means_a_reliable_source_reports_it():
    res = zc.resultaten_uit(_brave("https://blog.example/x"), SITES)
    check = {"claim": "c1", "tekst": "De foto is echt", "redactie": "Snopes", "oordeel": "waar", "datum": "2023-05-08",
             "url": "https://www.snopes.com/x", "beeld": False}
    antwoord = zc.lees_oordeel(json.dumps({**_oordeel("onzeker"), "checks": [{"nr": 1, "zelfde": True}]}))
    uit = zc.na_lezen(antwoord, BERICHT, res, [check], "lezer-v9", False, gezocht=True)
    assert uit["uitkomst"] == "onzeker"


def test_the_endpoint_says_unconfirmed_and_lists_the_searches_it_made(monkeypatch):
    from fastapi.testclient import TestClient

    from doublecheck.storage import connect, init_schema

    model = Reeks({"verder_zoeken": [EIGEN, NIEUWS]}, _oordeel("onzeker", steunt=(1,)))
    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    monkeypatch.setattr(api, "_checks_uit_database", lambda conn, config, tekst: [])
    api.app.dependency_overrides[api.get_anthropic] = lambda: model
    api.app.dependency_overrides[api.get_zoeker] = lambda: (lambda q: _brave("https://blog.example/x"))
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        d = TestClient(api.app).post("/check", json={"text": BERICHT}).json()
    finally:
        api.app.dependency_overrides.clear()
    assert d["outcome"] == "unconfirmed" and d["colour"] is None
    assert d["searches"] == [{"kind": "own_site", "query": EIGEN["vraag"], "site": "euronews.com", "found": 1},
                             {"kind": "real_news", "query": NIEUWS["vraag"], "site": None, "found": 1}]
