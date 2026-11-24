"""'Beweringen eerst' voor screenshots (PLAN #32.6, P4 §162): bij een screenshot haalt
Haiku eerst de beweringen en zoekvragen uit de gemaskeerde tekst, en het geheugen
zoekt met alles samen. Een nep-client staat in voor Anthropic."""

import dataclasses
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as bc
from doublecheck import verificatie as v
from doublecheck import zoekherstel as zh
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

TEKST = "CHOLA PRINCESS KUNDAVAI rare photo #tamil #memes"
GEHAALD = [{"bewering": "Photo shows the Chola princess Kundavai",
            "zoekvragen": ["Kundavai real photo", "Chola princess photograph British Museum"]}]


def _config(**instellingen):
    config = load_config(None)
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


class _Blok:
    def __init__(self, **velden):
        self.__dict__.update(velden)

    def model_dump(self):
        return dict(self.__dict__)


class _Nep:
    def __init__(self):
        self.verzoeken, self.messages = [], self

    def create(self, **params):
        self.verzoeken.append(params)
        return _Blok(content=[_Blok(type="text", text=json.dumps({"beweringen": GEHAALD}))],
                     usage=_Blok(input_tokens=1_000, output_tokens=200, server_tool_use=None))


def _k(claim, gelijkenis):
    return {"claim": claim, "gelijkenis": gelijkenis, "oordeel": "onwaar"}


def test_the_claims_question_is_exactly_the_one_measured_in_p4():
    params = bc.beweringenverzoek(TEKST, _config(beweringen="beweringen-v1"))
    assert params == zh.extractieverzoek("x", TEKST, "haiku")["params"]
    assert "tools" not in params and isinstance(params["messages"][0]["content"], str)


def test_an_unknown_claims_version_or_another_model_refuses():
    with pytest.raises(bc.VersieFout):
        bc.beweringenverzoek(TEKST, _config(beweringen="beweringen-v9"))
    with pytest.raises(bc.VersieFout):
        bc.beweringenverzoek(TEKST, _config(beweringen="beweringen-v1", beweringen_model="claude-sonnet-5-5"))


def test_the_memory_keeps_the_best_similarity_per_check_and_five_checks():
    lijsten = [[_k("a", 0.8), _k("b", 0.6)], [_k("b", 0.9), _k("c", 0.7)],
               [_k(x, 0.65) for x in "defg"]]
    geheugen = bc.geheugen_uit(lijsten)
    assert [(k["claim"], k["gelijkenis"]) for k in geheugen][:3] == [("b", 0.9), ("a", 0.8), ("c", 0.7)]
    assert len(geheugen) == v.N_GEHEUGEN
    verborgen = bc.geheugen_uit(lijsten, frozenset({"b"}))
    assert "b" not in {k["claim"] for k in verborgen} and len(verborgen) == v.N_GEHEUGEN


def test_one_search_gives_the_same_memory_as_before():
    lijst = [_k(x, 0.9 - i / 100) for i, x in enumerate("abcdefgh")]
    assert bc.geheugen_uit([lijst]) == v.geheugen_voor("a", {"kandidaten": lijst})


def test_the_claims_step_only_asks_for_a_screenshot_and_only_when_switched_on():
    for config, screenshot in ((_config(beweringen="beweringen-v1"), False), (_config(beweringen=""), True)):
        nep = _Nep()
        assert bc.beweringen_vragen(TEKST, nep, config, screenshot) == ([], 0.0) and nep.verzoeken == []
    nep = _Nep()
    gehaald, kosten = bc.beweringen_vragen(TEKST, nep, _config(beweringen="beweringen-v1"), True)
    assert gehaald == GEHAALD and len(nep.verzoeken) == 1
    assert nep.verzoeken[0]["messages"][0]["content"].endswith(TEKST)
    assert 0 < kosten < 0.001  # Haiku, zonder batchkorting


def test_the_cost_of_the_claims_step_is_booked_with_the_check():
    from tests.test_berichtcontrole import TABEL, ZINNEN, NepClient, _machinetekst, _voorbereid

    voorbereid = {**_voorbereid(), "kosten": 0.25}
    zonder = bc.beoordeel(sqlite3.connect(":memory:"), _voorbereid(), NepClient([(_machinetekst("klopt niet"), 0)]),
                          _config(aan=True), "2026-10-28", TABEL, ZINNEN)
    met = bc.beoordeel(sqlite3.connect(":memory:"), voorbereid, NepClient([(_machinetekst("klopt niet"), 0)]),
                       _config(aan=True, beweringen="beweringen-v1"), "2026-10-28", TABEL, ZINNEN)
    assert met["kosten"] == pytest.approx(zonder["kosten"] + 0.25)
    assert met["versies"]["claims"] == "beweringen-v1"


def test_claims_first_stays_off_until_it_is_measured():
    c = load_config(None).berichtcontrole
    assert c.beweringen == "" and c.beweringen_model == "claude-haiku-5-5"


def test_with_the_daily_cap_reached_a_screenshot_asks_no_model_at_all(monkeypatch):
    monkeypatch.setattr(bc, "extract_text", lambda beeld, ocr: _Blok(text="5G spreads the coronavirus"))
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"_meta": {"versie": "bronnen-v7"}, "sites": {}})  # zonder de lijst uit het lab, data/ staat niet in git
    monkeypatch.setattr(bc, "voorbereiden", lambda conn, config, tekst, client=None, screenshot=False:
                        (client.messages.create(**bc.beweringenverzoek(tekst, config)), {})[1])
    conn = connect(":memory:")
    init_schema(conn)
    kosten = sqlite3.connect(":memory:", check_same_thread=False)
    bc.boek(kosten, bc.date.today().isoformat(), 5.0)
    nep = _Nep()
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, beweringen="beweringen-v1")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: kosten
    try:
        antwoord = TestClient(api.app).post("/check", files={"image": ("s.png", b"\x89PNG", "image/png")})
    finally:
        api.app.dependency_overrides.clear()
    assert antwoord.status_code == 503 and antwoord.json()["detail"]["reason"] == "cap" and nep.verzoeken == []


# --- de voormeting (PLAN #32.6) ---------------------------------------------------------------

from doublecheck import beweringeneerst as be  # noqa: E402


def _g(*claims, oordeel="onwaar"):
    return [{"claim": c, "gelijkenis": 0.9 - i / 100, "oordeel": oordeel} for i, c in enumerate(claims)]


def test_the_round_asks_again_only_when_other_checks_are_among_the_best_five():
    assert not be.veranderd(_g("a", "b", "c"), _g("b", "a", "c"))
    assert be.veranderd(_g("a", "b", "c"), _g("a", "b", "d"))
    assert not be.veranderd(_g(*"abcde"), _g(*"abcde") + _g("f"))


def test_a_false_check_on_top_that_was_not_there_before_is_counted():
    assert be.onwaar_bovenaan_nieuw(_g("a", oordeel="waar"), _g("b"))
    assert not be.onwaar_bovenaan_nieuw(_g("b"), _g("b")) and not be.onwaar_bovenaan_nieuw(_g("a"), _g("b"))
    assert not be.onwaar_bovenaan_nieuw(_g("a"), _g("c", oordeel="waar"))


def test_the_expectation_counts_found_misses_and_drops_a_lost_own_check():
    stukken = [{"id": "e1", "set": "E", "eigen": ["x"], "geheugen": _g("x", "a")},   # bewezen, houdt x
               {"id": "e2", "set": "E", "eigen": ["y"], "geheugen": _g("y", "a")},   # bewezen, raakt y kwijt
               {"id": "e3", "set": "E", "eigen": ["z"], "geheugen": _g("a", "b")},   # misser, vindt z
               {"id": "e4", "set": "E", "eigen": ["q"], "geheugen": _g("a", "b")},   # misser, blijft mis
               {"id": "e5", "set": "E", "eigen": ["r"], "geheugen": _g("a")},        # bewezen met een andere bron
               {"id": "w1", "set": "W", "eigen": ["w"], "geheugen": _g("w", oordeel="waar")}]
    nieuw = {"e1": _g("x", "c"), "e2": _g(*"abcde"), "e3": _g("z", "a"), "e4": _g("a", "b"), "e5": _g("a", "b"),
             "w1": _g("v") + _g("w", oordeel="waar")}
    uit = be.voormeting(stukken, nieuw, {"e1", "e2", "e5"})
    assert uit["E"]["verwachting"] == 3 and uit["E"]["eigen kwijt"] == 1 and uit["E"]["eigen gevonden"] == 1
    assert uit["W"]["onwaar bovenaan, nieuw"] == 1 and uit["door naar de ronde"] is False


def test_proven_in_round_4_means_red_with_the_own_check_or_an_unrejected_source():
    stuk = {"id": "e1", "eigen": ["x"]}
    eigen = {"stand": 1, "oordeel": "klopt niet", "bronnen": [{"soort": "geheugen", "claim": "x"}]}
    ander = {"stand": 1, "oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "https://a.org"}]}
    assert be.bewezen_in_ronde4(stuk, eigen, {}) and be.bewezen_in_ronde4(stuk, ander, {})
    assert not be.bewezen_in_ronde4(stuk, ander, {("e1", "klopt niet"): "past niet"})
    assert not be.bewezen_in_ronde4(stuk, {**eigen, "stand": 5, "oordeel": "onzeker"}, {})
