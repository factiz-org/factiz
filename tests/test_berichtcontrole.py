"""De controle per bericht, `POST /check` (B43, B44, B45; PLAN #31.12, SPECS
E5.S4). Een nep-client staat in voor Anthropic: de suite vraagt nooit een model
iets en kost niets."""

import dataclasses
import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as controle
from doublecheck import verificatie as v
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

FEIT = "vaccines-autism"
ZINNEN = {FEIT: "Vaccines do not cause autism."}
GEHEUGEN = [{"claim": "c1", "gelijkenis": 0.81, "tekst": "Vaccines cause autism", "redactie": "Newtral",
             "oordeel": "onwaar", "datum": "2020-04-01", "url": "https://www.newtral.es/vacunas-autismo/"}]
TABEL = {("klopt niet", "redactie"): {"stand": 1, "n": 80, "aandeel waar": 0.0},
         ("klopt", "web"): {"stand": 7, "n": 120, "aandeel waar": 0.95}}


class _Blok:
    def __init__(self, **velden):
        self.__dict__.update(velden)

    def model_dump(self):
        return dict(self.__dict__)


class _Gebruik:
    def __init__(self, zoek, cache_lees=0):
        self.input_tokens, self.output_tokens = 4_000, 400
        self.cache_read_input_tokens, self.cache_creation_input_tokens = cache_lees, 0
        self.server_tool_use = _Blok(web_search_requests=zoek)


class _Antwoord:
    def __init__(self, tekst, zoek=0):
        self.content = [_Blok(type="text", text=tekst, citations=None)]
        self.usage = _Gebruik(zoek)
        self.stop_reason = "end_turn"


def _machinetekst(oordeel, bron="[F1]"):
    return f"Steps done {bron}.\nBEWERING: Vaccines cause autism\nOORDEEL: {oordeel}\nUITLEG: Zie de check."


class NepClient:
    """Geeft de machine-antwoorden op volgorde, en de feitenstap per sleutel."""

    def __init__(self, machine, feit=None, vorm=None):
        self.machine = list(machine)
        self.feit = feit or {}
        self.vorm = vorm or {"waarom": "", "vorm": "zelf", "beeld": False}
        self.verzoeken = []
        self._slot = threading.Lock()
        self.messages = self

    def create(self, **params):
        with self._slot:
            self.verzoeken.append(params)
            if "tools" in params:
                tekst, zoek = self.machine.pop(0)
                return _Antwoord(tekst, zoek)
        if _is_vormvraag(params):
            return _Antwoord(json.dumps(self.vorm))
        vraag = params["messages"][0]["content"]
        sleutel = "B" if "short English sentence" in vraag else "A"
        return _Antwoord(json.dumps(self.feit.get(sleutel, {"richting": "geen", "feit": "", "waarom": ""})))


def _is_vormvraag(params):
    return "vorm" in params.get("output_config", {}).get("format", {}).get("schema", {}).get("properties", {})


def _config(**instellingen):
    config = load_config()
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _voorbereid(tekst="Vaccines cause autism, doctors confirm.", kandidaten=()):
    return {"tekst": tekst, "geheugen": GEHEUGEN, "kandidaten": [list(k) for k in kandidaten]}


def _conn():
    return sqlite3.connect(":memory:", check_same_thread=False)


def _machineverzoeken(nep):
    return [p for p in nep.verzoeken if "tools" in p]


def test_only_the_masked_text_reaches_the_model():
    tekst = controle.bericht_uit("Call 06-12345678 or mail jan.devries @gmail.com: vaccines cause autism!", None,
                                 load_config().ocr)
    nep = NepClient([(_machinetekst("klopt niet"), 0)])
    controle.beoordeel(_conn(), _voorbereid(tekst), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    verstuurd = json.dumps([p["messages"] for p in nep.verzoeken])
    assert "12345678" not in verstuurd and "jan.devries" not in verstuurd
    assert "vaccines cause autism" in verstuurd


def test_a_screenshot_is_read_on_the_server_and_never_sent_as_an_image(monkeypatch):
    monkeypatch.setattr(controle, "extract_text", lambda beeld, ocr: _Blok(text="5G spreads the coronavirus"))
    tekst = controle.bericht_uit(None, b"\x89PNG...", load_config().ocr)
    assert tekst == "5G spreads the coronavirus"
    nep = NepClient([(_machinetekst("klopt niet"), 0)])
    controle.beoordeel(_conn(), _voorbereid(tekst), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    for params in nep.verzoeken:
        inhoud = params["messages"][0]["content"]
        assert isinstance(inhoud, str) or all(blok["type"] == "text" for blok in inhoud)


def test_a_caption_and_the_text_in_the_image_go_together():
    assert controle.samenstellen("Look at this", "5G spreads it") == \
        "Look at this\n[Text in the attached image: 5G spreads it]"
    assert controle.samenstellen(None, "5G spreads it") == "5G spreads it"
    assert controle.samenstellen("Look at this", "") == "Look at this"


def test_unsure_without_a_search_is_asked_once_more_with_the_instruction_to_search():
    nep = NepClient([(_machinetekst("onzeker", bron=""), 0), (_machinetekst("klopt niet"), 1)])
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    eerste, tweede = _machineverzoeken(nep)
    assert uit["oordeel"] == "klopt niet" and uit["herkansing"] is True
    assert controle.HERKANSING["herkansing-v1"] in json.dumps(tweede["messages"])
    assert controle.HERKANSING["herkansing-v1"] not in json.dumps(eerste["messages"])


def test_unsure_after_a_search_is_not_asked_again():
    nep = NepClient([(_machinetekst("onzeker", bron=""), 1)])
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert len(_machineverzoeken(nep)) == 1 and uit["oordeel"] == "onzeker" and uit["herkansing"] is False


def test_the_fixed_part_is_marked_for_caching_and_the_text_is_that_of_the_measurement():
    config = _config(aan=True)
    params = controle.machineverzoek("Vaccines cause autism", GEHEUGEN, "2026-10-27", config)
    s = {"id": "controle", "soort": "tekst", "tekst": "Vaccines cause autism", "datum": "2026-10-27"}
    meting = v.verzoek(s, GEHEUGEN, "a", [], "sonnet", config.berichtcontrole.vraag)["params"]
    assert params["system"] == [{"type": "text", "text": meting["system"], "cache_control": {"type": "ephemeral"}}]
    assert params["messages"] == meting["messages"] and params["tools"] == meting["tools"]
    assert params["tools"][0]["type"] == "web_search_20250305"


def test_a_model_other_than_the_one_in_config_refuses_to_run():
    with pytest.raises(controle.VersieFout):
        controle.machineverzoek("Vaccines cause autism", GEHEUGEN, "2026-10-27", _config(aan=True, model_id="claude-x"))


def test_the_cost_counts_cache_reads_cache_writes_and_searches():
    kosten = controle.kosten({"in": 1_000, "uit": 100, "cache_lees": 3_000, "cache_schrijf": 2_000, "zoek": 1})
    assert kosten == pytest.approx((1_000 * 2 + 100 * 10 + 3_000 * 0.2 + 2_000 * 2.5) / 1e6 + 0.01)


def test_the_daily_cap_stops_the_check_before_any_model_call():
    conn = _conn()
    controle.boek(conn, "2026-10-27", 2.0)
    nep = NepClient([(_machinetekst("klopt niet"), 0)])
    with pytest.raises(controle.Plafond):
        controle.beoordeel(conn, _voorbereid(), nep, _config(aan=True, dagplafond_dollar=2.0), "2026-10-27",
                           TABEL, ZINNEN)
    assert nep.verzoeken == []


def test_each_check_is_booked_as_one_amount_per_day_without_content():
    conn = _conn()
    nep = NepClient([(_machinetekst("klopt niet"), 1)])
    uit = controle.beoordeel(conn, _voorbereid(), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert controle.uitgegeven(conn, "2026-10-27") == pytest.approx(uit["kosten"])
    assert conn.execute("SELECT * FROM controle_kosten").fetchall() == [("2026-10-27", pytest.approx(uit["kosten"]))]


def test_stand_10_needs_both_keys_of_the_fact_step():
    ja = {"richting": "bevestigt", "feit": "V1", "waarom": ""}
    voorbereid = _voorbereid("Vaccines do not cause autism.", [(FEIT, 0.9)])
    beide = NepClient([(_machinetekst("klopt", bron=""), 1)], feit={"A": ja, "B": ja})
    uit = controle.beoordeel(_conn(), voorbereid, beide, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert uit["stand"]["stand"] == 10 and uit["feit"] == FEIT
    een = NepClient([(_machinetekst("klopt", bron=""), 1)], feit={"A": ja})
    uit = controle.beoordeel(_conn(), voorbereid, een, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert uit["stand"]["stand"] != 10 and uit["feit"] is None


def test_a_check_from_the_database_is_shown_as_a_check_of_an_editor():
    nep = NepClient([(_machinetekst("klopt niet"), 0)])
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert uit["bronnen"] == [{"soort": "check van een redactie", "url": GEHEUGEN[0]["url"], "redactie": "Newtral",
                               "oordeel": "onwaar", "datum": "2020-04-01", "titel": None, "citaat": None}]
    assert uit["stand"] == {"stand": 1, "woorden": "zeer waarschijnlijk onwaar", "laag": "redactie"}


def test_no_batch_files_or_dynamic_filtering_in_the_request_path():
    import inspect

    bron = inspect.getsource(controle)
    for verboden in ("batches", ".files", "web_search_20260209", "web_fetch"):
        assert verboden not in bron, verboden


def test_the_check_is_off_by_default_and_asks_no_model():
    assert load_config().berichtcontrole.aan is False
    nep = NepClient([])
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    try:
        antwoord = TestClient(api.app).post("/check", json={"text": "Vaccines cause autism"})
    finally:
        api.app.dependency_overrides.clear()
    assert antwoord.status_code == 503 and nep.verzoeken == []


def test_the_measured_share_of_the_class_comes_with_the_stand():
    nep = NepClient([(_machinetekst("klopt niet"), 0)])
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True), "2026-10-27", TABEL, ZINNEN)
    assert uit["meting"] == {"n": 80, "aandeel waar": 0.0}


def test_an_established_fact_comes_with_its_sentence_and_at_least_four_sources():
    feit = controle.feitinfo(FEIT)
    assert feit["zin"] == "Vaccines do not cause autism."
    assert len(feit["bronnen"]) >= 4 and all(b["url"].startswith("https://") for b in feit["bronnen"])


# --- de vormvraag en de twee regels (PLAN #31.15) -------------------------------------------

ZELF = {"vorm": "zelf", "beeld": False, "gelezen": True}
OVER = {"vorm": "over een bewering", "beeld": False, "gelezen": True}
BEELD = {"vorm": "zelf", "beeld": True, "gelezen": True}
OORDELEN = ("klopt", "klopt niet", "let op", "onzeker", "geen bewering", "satire")


def test_the_form_question_gets_only_the_masked_text_and_never_searches():
    params = controle.vormverzoek("Vaccines cause autism", "vorm-v1", _config(aan=True))
    assert params["model"] == _config().berichtcontrole.model_id and "tools" not in params
    assert "Vaccines cause autism" in params["messages"][0]["content"]
    assert params["output_config"]["format"]["type"] == "json_schema"


def test_an_unknown_form_question_refuses_to_run():
    with pytest.raises(controle.VersieFout):
        controle.vormverzoek("Vaccines cause autism", "vorm-v0", _config(aan=True))


def test_an_unreadable_form_answer_applies_no_rule():
    for tekst in ("no json", '{"vorm": "misschien", "beeld": false, "waarom": ""}', '{"vorm": "zelf"}', "[]"):
        assert controle.lees_vorm(tekst) == {"vorm": "zelf", "beeld": False, "gelezen": False}
    assert controle.lees_vorm('{"waarom": "x", "vorm": "over een bewering", "beeld": true}') == \
        {"vorm": "over een bewering", "beeld": True, "gelezen": True}


def test_a_message_about_a_claim_loses_its_colour_but_keeps_the_stand_of_that_claim():
    uit = controle.regels({}, "klopt niet", {"stand": 1, "laag": "redactie"}, None, [], OVER)
    assert uit["kleur"] is None and uit["stand"]["stand"] == 1 and uit["oordeel"] == "klopt niet"
    assert uit["regels"] == ["over een bewering"]
    assert controle.regels({}, "klopt niet", {"stand": 1, "laag": "redactie"}, None, [], ZELF)["kleur"] == "rood"


def test_a_true_verdict_on_what_an_image_shows_becomes_uncertain_and_red_stays_red():
    uit = controle.regels(TABEL, "klopt", {"stand": 7, "laag": "web"}, None, [{"soort": "web"}], BEELD)
    assert uit["oordeel"] == "onzeker" and uit["stand"]["stand"] == 5 and uit["kleur"] is None
    assert uit["regels"] == ["beeld"]
    tien = controle.regels(TABEL, "klopt", {"stand": 10, "laag": "feitenbasis"}, FEIT, [], BEELD)
    assert tien["stand"]["stand"] == 5 and tien["feit"] is None
    rood = controle.regels(TABEL, "klopt niet", {"stand": 1, "laag": "redactie"}, None, [], BEELD)
    assert rood["kleur"] == "rood" and rood["regels"] == []


def test_the_rules_never_make_anything_red_or_green():
    for oordeel in OORDELEN:
        for stand in range(11):
            for vorm in (ZELF, OVER, BEELD, {"vorm": "over een bewering", "beeld": True, "gelezen": True}):
                voor = controle.kleur(stand, oordeel)
                na = controle.regels({}, oordeel, {"stand": stand, "laag": "web"}, None, [], vorm)["kleur"]
                assert na in (voor, None), (oordeel, stand, vorm)


def test_uncertain_is_5_for_every_source_in_the_calibration_so_rule_2_never_colours():
    tabel = controle.ijktabel(load_config())
    for laag in ("redactie", "web", "geen bron", "feitenbasis"):
        bronnen = {"redactie": [{"soort": "geheugen"}], "web": [{"soort": "web"}]}.get(laag, [])
        uit = controle.regels(tabel, "klopt", {"stand": 9, "laag": laag}, None, bronnen, BEELD)
        assert uit["stand"]["stand"] == 5 and uit["kleur"] is None, laag


def test_from_v2_the_form_question_gets_the_claim_the_machine_judged():
    params = controle.vormverzoek("Officials say the story is disinfo", "vorm-v2", _config(aan=True),
                                  bewering="Het verhaal is desinformatie")
    assert "Het verhaal is desinformatie" in params["messages"][0]["content"]
    with pytest.raises(ValueError):
        controle.vormverzoek("Officials say the story is disinfo", "vorm-v2", _config(aan=True))


TABEL_KLOPT = {**TABEL, ("klopt", "redactie"): {"stand": 9, "n": 290, "aandeel waar": 0.99},
               ("onzeker", "redactie"): {"stand": 5, "n": 7, "aandeel waar": 0.86}}


def test_a_red_verdict_on_a_message_about_a_claim_comes_back_without_colour():
    nep = NepClient([(_machinetekst("klopt niet"), 0)], vorm={"waarom": "", "vorm": "over een bewering", "beeld": False})
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True, vorm="vorm-v2"), "2026-10-27", TABEL,
                             ZINNEN)
    assert uit["kleur"] is None and uit["regels"] == ["over een bewering"] and uit["stand"]["stand"] == 1
    vormvraag = [p for p in nep.verzoeken if _is_vormvraag(p)]
    assert len(vormvraag) == 1 and "Vaccines cause autism" in vormvraag[0]["messages"][0]["content"]


def test_a_true_verdict_on_what_an_image_shows_comes_back_uncertain_with_its_measurement():
    nep = NepClient([(_machinetekst("klopt"), 0)], vorm={"waarom": "", "vorm": "zelf", "beeld": True})
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True, vorm="vorm-v2"), "2026-10-27",
                             TABEL_KLOPT, ZINNEN)
    assert uit["oordeel"] == "onzeker" and uit["stand"]["stand"] == 5 and uit["kleur"] is None
    assert uit["regels"] == ["beeld"] and uit["meting"] == {"n": 7, "aandeel waar": 0.86}


def test_the_form_question_is_only_asked_for_red_or_green():
    nep = NepClient([(_machinetekst("onzeker", bron=""), 1)])
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True, vorm="vorm-v2"), "2026-10-27", TABEL,
                             ZINNEN)
    assert uit["kleur"] is None and not [p for p in nep.verzoeken if _is_vormvraag(p)]


def test_without_a_form_question_in_config_no_rule_applies():
    nep = NepClient([(_machinetekst("klopt niet"), 0)], vorm={"waarom": "", "vorm": "over een bewering", "beeld": False})
    uit = controle.beoordeel(_conn(), _voorbereid(), nep, _config(aan=True, vorm=""), "2026-10-27", TABEL, ZINNEN)
    assert uit["kleur"] == "rood" and uit["regels"] == [] and not [p for p in nep.verzoeken if _is_vormvraag(p)]


def test_the_measured_form_question_is_in_config():
    assert load_config().berichtcontrole.vorm == "vorm-v2"
