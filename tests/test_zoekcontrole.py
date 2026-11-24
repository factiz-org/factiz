"""De controle per bericht, de simpele versie (B51, PLAN #32.10): eerst de database, anders gewoon zoeken;
Sonnet leest de top 10 en de bronnenlijst beslist. Een nepzoeker en een nepmodel staan in voor Brave en Anthropic."""

import dataclasses
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as bc
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "infowars.com": [["laag", "Lin e.a. 0.10"]]}
BERICHT = "At least 68 people are killed in a collision between two high speed trains near Toledo, Spain."


def _png() -> bytes:
    """Een echt, klein beeld: het zwartmaken van B55 opent het (#32.36)."""
    import io

    from PIL import Image

    uit = io.BytesIO()
    Image.new("RGB", (64, 32), "white").save(uit, format="PNG")
    return uit.getvalue()


PNG = _png()


def _config(**instellingen):
    config = load_config()
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _brave(*urls):
    return {"web": {"results": [{"url": u, "title": f"titel {i}", "description": f"fragment {i}"}
                                for i, u in enumerate(urls)]}}


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class _Antwoord:
    def __init__(self, d):
        self.content, self.usage, self.stop_reason = [_Blok(json.dumps(d))], _Gebruik(), "end_turn"


class NepModel:
    def __init__(self, oordeel="klopt", steunt=(1, 2), tegen=()):
        self.d = {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Twee kranten."}
        self.verzoeken = []
        self.messages = self

    def create(self, **params):
        self.verzoeken.append(params)
        return _Antwoord(self.d)


def test_the_reader_reads_the_message_and_the_results_and_never_searches_itself():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"), SITES)
    params = zc.leesverzoek(BERICHT, res, "2026-10-28", _config(), checks=[])  # de lezer van het product leest checks
    assert "tools" not in params and params["model"] == _config().berichtcontrole.model_id
    assert params["output_config"]["format"]["schema"] == zc.LEZERS[_config().berichtcontrole.lezer]["schema"]
    tekst = params["messages"][0]["content"]
    assert BERICHT in tekst and "[1] nytimes.com (goed)" in tekst and "2026-10-28" in tekst
    with pytest.raises(bc.VersieFout):
        zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v9"))


def test_the_image_goes_along_only_when_the_switch_is_on():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    zonder = zc.leesverzoek(BERICHT, res, None, _config(beeld=False), beeld=PNG, checks=[])
    assert isinstance(zonder["messages"][0]["content"], str)
    met = zc.leesverzoek(BERICHT, res, None, _config(beeld=True), beeld=PNG, checks=[])
    blokken = met["messages"][0]["content"]
    assert blokken[0]["type"] == "image" and blokken[1] == {"type": "text", "text": zonder["messages"][0]["content"]}


def test_the_sources_shown_are_the_cited_results_with_their_band_and_role():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b",
                                   "https://www.infowars.com/c"), SITES)
    bronnen = zc.bronnen_van({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [3], "uitleg": ""}, res)
    assert [(b["site"], b["band"], b["rol"]) for b in bronnen] == [("nytimes.com", "goed", "bevestigt"),
                                                                  ("cnn.com", "goed", "bevestigt"),
                                                                  ("infowars.com", "laag", "spreekt tegen")]


def test_a_check_from_the_database_answers_without_searching_or_asking_the_model():
    nep, gezocht = NepModel(), []
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": [{"soort": "check van een redactie", "url": "u"}]}
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(), nep, lambda q: gezocht.append(q),
                        lambda tekst: snel, SITES, "2026-10-29")
    assert uit["route"] == "database" and uit["kleur"] == "rood" and uit["kosten"] == 0
    assert gezocht == [] and nep.verzoeken == []


def test_otherwise_one_search_and_one_reading_and_the_source_list_decides():
    """De simpele versie tot en met `lezer-v7`; één lezing met zoekvragen vooraf (v9) staat in test_eenlezing."""
    nep, gezocht = NepModel("klopt", steunt=(1, 2)), []
    zoek = lambda q: gezocht.append(q) or _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa: E731
    kosten = sqlite3.connect(":memory:")
    uit = zc.controleer(kosten, BERICHT, _config(lezer="lezer-v7"), nep, zoek, lambda tekst: None, SITES, "2026-10-29",
                        zoek_checks=lambda t: [])
    assert gezocht == [zc.zoekvraag(BERICHT)] and len(nep.verzoeken) == 1
    assert uit["route"] == "zoeken" and uit["oordeel"] == "klopt" and uit["kleur"] == "groen"
    assert uit["versies"]["reader"] == "lezer-v7" and uit["versies"]["search"] == "brave-v1"
    assert bc.uitgegeven(kosten, "2026-10-29") == pytest.approx(uit["kosten"]) and uit["kosten"] > zc.ZOEKPRIJS
    een_krant = NepModel("klopt", steunt=(1,))
    assert zc.controleer(kosten, BERICHT, _config(lezer="lezer-v7"), een_krant, zoek, lambda t: None, SITES, None,
                         zoek_checks=lambda t: [])["kleur"] is None


def test_the_endpoint_answers_with_the_verdict_the_colour_and_the_sources(monkeypatch):
    nep, gezocht = NepModel("klopt", steunt=(1, 2)), []
    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_zoeker] = lambda: (
        lambda q: gezocht.append(q) or _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"))
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        antwoord = TestClient(api.app).post("/check", json={"text": BERICHT + " Call me at +31 6 12345678."})
    finally:
        api.app.dependency_overrides.clear()
    assert antwoord.status_code == 200, antwoord.text
    d = antwoord.json()
    assert d["verdict"] == "klopt" and d["colour"] == "green" and d["route"] == "search"
    assert [(s["publisher"], s["band"], s["role"]) for s in d["sources"]] == [("nytimes.com", "goed", "confirms"),
                                                                            ("cnn.com", "goed", "confirms")]
    assert "scale" not in d and "category" not in d
    # alleen de gemaskeerde tekst gaat naar de zoeker en het model (B43)
    assert "12345678" not in gezocht[0] and "12345678" not in nep.verzoeken[0]["messages"][0]["content"]


def test_the_daily_cap_is_checked_only_after_the_database_and_before_any_search():
    volgorde = []
    snel_ja = lambda t: {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}  # noqa: E731
    zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(), NepModel(), lambda q: volgorde.append("zoek"),
                  snel_ja, SITES, "d", bewaak=lambda: volgorde.append("grens"))
    assert volgorde == []

    def vol():
        raise bc.Plafond("dagplafond bereikt")

    nep = NepModel()
    with pytest.raises(bc.Plafond):
        zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(), nep, lambda q: volgorde.append("zoek"),
                      lambda t: None, SITES, "d", bewaak=vol, zoek_checks=lambda t: [])
    assert volgorde == [] and nep.verzoeken == []


def test_a_fact_check_by_an_ifcn_signatory_counts_as_a_good_contradiction_whatever_its_band():
    sites = {**SITES, "boomlive.in": [["goed", "IFCN"], ["wisselend", "Lin e.a. 0.64"]]}
    res = zc.resultaten_uit(_brave("https://www.boomlive.in/fake", "https://www.infowars.com/c",
                                   "https://www.boomlive.in/other"), sites)
    assert res[0]["band"] == "wisselend" and res[0]["factcheck"] is True and res[1]["factcheck"] is False
    assert zc.kleur_van({"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [1]}, res) == "rood"
    assert zc.kleur_van({"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [2]}, res) is None
    # alleen als tegenspraak: bevestigen blijft aan de band gebonden
    assert zc.kleur_van({"oordeel": "klopt", "steunt": [1, 3], "spreekt_tegen": []}, res) is None


def test_with_the_check_on_the_service_warms_the_text_model_at_startup_and_never_when_it_is_off(monkeypatch):
    geladen = []
    monkeypatch.setattr(api, "los_op", lambda conn, config, tekst, *_: geladen.append(tekst))
    monkeypatch.setattr(api, "_ruim_op", lambda pad: None)
    monkeypatch.setattr(api, "load_config", lambda *a: _config(aan=False))
    with TestClient(api.app):
        pass
    assert geladen == []
    monkeypatch.setattr(api, "load_config", lambda *a: _config(aan=True))
    with TestClient(api.app):
        pass
    assert geladen[0] == api.WARMTEKST and len(geladen) <= 2  # de vaste zin, en waar er een is een claim uit de index


STAAT = {"domeinen": {"kayhan.ir": {"naam": "Kayhan", "land": "Iran", "bron": "Claude, de PO kijkt na"}}}


def test_each_result_carries_the_state_media_label():
    res = zc.resultaten_uit(_brave("https://kayhan.ir/x", "https://www.nytimes.com/a"), SITES, STAAT)
    assert res[0]["staatsmedia"] == "Kayhan" and res[1]["staatsmedia"] is None


def test_misleading_is_orange_with_the_same_bar_as_red():
    sites = {**SITES, "boomlive.in": [["goed", "IFCN"], ["wisselend", "Lin e.a. 0.64"]]}
    res = zc.resultaten_uit(_brave("https://www.boomlive.in/x", "https://www.infowars.com/c"), sites, STAAT)
    assert zc.kleur_van({"oordeel": "misleidend", "steunt": [], "spreekt_tegen": [1]}, res) == "oranje"
    assert zc.kleur_van({"oordeel": "misleidend", "steunt": [], "spreekt_tegen": [2]}, res) is None


def test_green_with_one_good_and_one_other_independent_outlet_but_never_with_state_media_as_the_other():
    sites = {**SITES, "eyeradio.org": [], "lemonde.fr": [["goed", "Lin e.a. 0.67"]]}
    res = zc.resultaten_uit(_brave("https://www.lemonde.fr/a", "https://www.eyeradio.org/b", "https://kayhan.ir/c",
                                   "https://www.infowars.com/d", "https://www.youtube.com/e"), sites, STAAT)
    ruim = lambda steunt: zc.kleur_van({"oordeel": "klopt", "steunt": steunt, "spreekt_tegen": []}, res, "ruim")  # noqa: E731
    assert ruim([1, 2]) == "groen"
    assert zc.kleur_van({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": []}, res) is None  # v1: streng
    assert ruim([1, 3]) is None  # staatsmedia
    assert ruim([1, 4]) is None  # band laag
    assert ruim([1, 5]) is None  # platform
    assert ruim([2]) is None  # geen goede


def test_reader_v2_may_say_misleading_and_v1_stays_exactly_as_measured():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES, STAAT)
    v1 = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v1"))
    v2 = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v2"))
    assert "misleidend" not in json.dumps(v1["output_config"]) and '"misleidend"' in v2["messages"][0]["content"]
    assert "misleidend" in v2["output_config"]["format"]["schema"]["properties"]["oordeel"]["enum"]
    assert zc.lees_oordeel(json.dumps({"oordeel": "misleidend", "steunt": [], "spreekt_tegen": [1], "uitleg": ""}))[
        "oordeel"] == "misleidend"


def test_a_check_that_only_says_misleading_answers_orange_from_the_database():
    from doublecheck import berichtcontrole as bc
    tabel = {("klopt niet", "redactie"): {"stand": 1, "n": 80, "aandeel waar": 0.0}}
    resolve = lambda *o: {"category": "matched", "claim": {"text": "x"}, "evidence": {"checks": [  # noqa: E731
        {"publisher": f"P{i}", "verdict_normalized": v, "url": "u", "review_date": "d"} for i, v in enumerate(o)]}}
    assert bc.snel_antwoord(resolve("misleidend", "misleidend"), tabel, "t", "v")["kleur"] == "oranje"
    assert bc.snel_antwoord(resolve("misleidend", "misleidend"), tabel, "t", "v")["oordeel"] == "misleidend"
    assert bc.snel_antwoord(resolve("onwaar", "misleidend"), tabel, "t", "v")["oordeel"] == "klopt niet"


def test_reader_v3_never_gives_green_to_a_claim_about_an_image_it_cannot_see():
    """#32.12, de regel van #31.15 terug: dat de gebeurtenis echt is, bevestigt het beeld niet."""
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"), SITES, STAAT)
    beeld = {"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [], "over_beeld": True}
    assert zc.kleur_van(beeld, res, "ruim") is None
    assert zc.kleur_van(beeld, res, "ruim", beeld_gezien=True) == "groen"
    assert zc.kleur_van({**beeld, "over_beeld": False}, res, "ruim") == "groen"
    # een goede tegenspraak blijft rood, ook zonder het beeld
    assert zc.kleur_van({"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [1], "over_beeld": True}, res) == "rood"


def test_the_image_field_is_read_strictly_and_its_absence_in_v1_and_v2_changes_nothing():
    lees = lambda **d: zc.lees_oordeel(json.dumps(  # noqa: E731
        {"oordeel": "klopt", "steunt": [1], "spreekt_tegen": [], "uitleg": "", **d}))
    assert lees()["over_beeld"] is False  # v1 en v2 kennen het veld niet
    assert lees(over_beeld=True)["over_beeld"] is True and lees(over_beeld=False)["over_beeld"] is False
    assert lees(over_beeld="nee")["over_beeld"] is True  # twijfel versoepelt nooit
    assert zc.lees_oordeel("geen JSON")["over_beeld"] is False  # onzeker geeft toch nooit groen


def test_reader_v3_asks_the_four_points_and_v1_and_v2_stay_as_measured():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES, STAAT)
    v3 = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v3"))
    schema = v3["output_config"]["format"]["schema"]
    assert "over_beeld" in schema["required"] and schema["properties"]["over_beeld"] == {"type": "boolean"}
    assert "misleidend" in schema["properties"]["oordeel"]["enum"] and zc.LEZERS["lezer-v3"]["regel"] == "ruim"
    vraag = v3["messages"][0]["content"]
    for punt in ("photo or video", "cause, perpetrator, place", "itself a fact-check", "old article"):
        assert punt in vraag, punt
    for oud in ("lezer-v1", "lezer-v2"):
        assert "over_beeld" not in json.dumps(zc.leesverzoek(BERICHT, res, None, _config(lezer=oud)))
    assert zc.LEZERS["lezer-v2"]["vraag"] is zc.VRAAG_V2 and zc.LEZERS["lezer-v1"]["vraag"] is zc.VRAAG


def test_the_check_knows_whether_the_reader_saw_the_image():
    nep = NepModel("klopt", steunt=(1, 2))
    nep.d["over_beeld"] = True
    zoek = lambda q: _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa: E731
    kosten = sqlite3.connect(":memory:")
    zonder = zc.controleer(kosten, BERICHT, _config(lezer="lezer-v3", beeld=False), nep, zoek, lambda t: None, SITES,
                           None, beeld=PNG)
    assert zonder["kleur"] is None and zonder["over_beeld"] is True  # het beeld ging niet mee
    met = zc.controleer(kosten, BERICHT, _config(lezer="lezer-v3", beeld=True), nep, zoek, lambda t: None, SITES, None,
                        beeld=PNG)
    assert met["kleur"] == "groen"
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    assert zc.controleer(kosten, BERICHT, _config(), nep, zoek, lambda t: snel, SITES, None)["over_beeld"] is False


def test_the_endpoint_says_when_a_claim_about_an_image_got_no_colour(monkeypatch):
    nep = NepModel("klopt", steunt=(1, 2))
    nep.d["over_beeld"] = True
    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_zoeker] = lambda: (
        lambda q: _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"))
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, lezer="lezer-v3")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        d = TestClient(api.app).post("/check", json={"text": "Video shows " + BERICHT}).json()
    finally:
        api.app.dependency_overrides.clear()
    assert d["colour"] is None and d["about_image"] is True


# --- #32.13: het antwoord in twee lagen ---------------------------------------------------------------------------

def _twee(oordeel="misleidend", steunt=(), tegen=(1,), feit="Floods hit Rasuwa on 26 August.", feit_steunt=(1, 2),
          anders="The video shows floods in Arunachal Pradesh in June."):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "over_beeld": False,
            "feit": feit, "feit_steunt": list(feit_steunt), "anders": anders}


def test_reader_v4_asks_for_the_underlying_fact_and_what_really_happened_and_v3_stays_as_measured():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES, STAAT)
    v4 = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v4"))
    schema = v4["output_config"]["format"]["schema"]
    assert {"feit", "feit_steunt", "anders", "over_beeld"} <= set(schema["required"])
    assert schema["properties"]["feit_steunt"] == {"type": "array", "items": {"type": "integer"}}
    vraag = v4["messages"][0]["content"]
    for punt in ("underlying fact", "how it really is", "without the image", "same language as the message",
                 "photo or video", "itself a fact-check"):
        assert punt in vraag, punt
    assert zc.LEZERS["lezer-v4"]["regel"] == "ruim" and zc.LEZERS["lezer-v3"]["vraag"] is zc.VRAAG_V3
    assert "feit_steunt" not in json.dumps(zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v3")))


def test_the_two_new_sentences_are_read_strictly_and_older_readers_have_none():
    lees = lambda **d: zc.lees_oordeel(json.dumps(  # noqa: E731
        {"oordeel": "misleidend", "steunt": [], "spreekt_tegen": [1], "uitleg": "", **d}))
    assert (lees()["feit"], lees()["feit_steunt"], lees()["anders"]) == ("", [], "")  # v1 tot en met v3
    d = lees(feit="  Floods hit Rasuwa. ", feit_steunt=[1, "2", 3], anders="From India.")
    assert (d["feit"], d["feit_steunt"], d["anders"]) == ("Floods hit Rasuwa.", [1, 3], "From India.")
    assert lees(feit=["x"], anders=7)["feit"] == "" and lees(feit=["x"], anders=7)["anders"] == ""
    assert zc.lees_oordeel("geen JSON")["feit"] == ""


def test_what_is_confirmed_shows_only_when_the_claim_is_not_true_and_its_sources_carry_green():
    sites = {**SITES, "eyeradio.org": []}
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b", "https://kayhan.ir/c",
                                   "https://www.eyeradio.org/d", "https://www.infowars.com/e"), sites, STAAT)
    assert zc.feit_van(_twee(), res, "oranje") == "Floods hit Rasuwa on 26 August."
    assert zc.feit_van(_twee(feit_steunt=(1, 4)), res, None) is not None  # de ruime regel, zoals groen
    assert zc.feit_van(_twee(feit_steunt=(1, 3)), res, None) is None  # staatsmedia als tweede
    assert zc.feit_van(_twee(feit_steunt=(1, 5)), res, None) is None  # band laag
    assert zc.feit_van(_twee(feit_steunt=(1,)), res, None) is None  # één bron
    assert zc.feit_van(_twee(feit_steunt=(1, 9)), res, None) is None  # een nummer dat er niet is
    assert zc.feit_van(_twee(oordeel="klopt"), res, None) is None  # dan is het feit de bewering zelf
    assert zc.feit_van(_twee(feit=""), res, "rood") is None
    # bij een bewering over een beeld, ook bij *klopt*: het feit is de gebeurtenis zonder het beeld
    beeld = {**_twee(oordeel="klopt", tegen=()), "over_beeld": True}
    assert zc.feit_van(beeld, res, None) is not None
    assert zc.feit_van(beeld, res, "groen") is None  # met het beeld gezien is de bewering zelf groen


def test_what_really_happened_shows_only_with_red_or_orange():
    assert zc.anders_van(_twee(), "oranje") == "The video shows floods in Arunachal Pradesh in June."
    assert zc.anders_van(_twee(oordeel="klopt niet"), "rood") is not None
    assert zc.anders_van(_twee(), None) is None  # zonder goede tegenspraak geen inzetje
    assert zc.anders_van(_twee(anders=""), "rood") is None


def test_the_check_returns_both_layers_and_the_endpoint_passes_them_on(monkeypatch):
    nep = NepModel()
    nep.d = {**_twee(), "uitleg": "De video komt uit India."}
    zoek = lambda q: _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa: E731
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v4"), nep, zoek, lambda t: None,
                        SITES, None)
    assert uit["kleur"] == "oranje" and uit["feit"] == "Floods hit Rasuwa on 26 August."
    assert uit["anders"].startswith("The video shows")
    assert [b["rol"] for b in uit["bronnen"]] == ["spreekt tegen", "bevestigt het feit"]
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    db = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(), nep, zoek, lambda t: snel, SITES, None)
    assert db["feit"] is None and db["anders"] is None  # kring 1 verandert niet

    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_zoeker] = lambda: zoek
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, lezer="lezer-v4")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        d = TestClient(api.app).post("/check", json={"text": BERICHT}).json()
    finally:
        api.app.dependency_overrides.clear()
    assert d["colour"] == "orange" and d["fact"] == "Floods hit Rasuwa on 26 August."
    assert d["what_happened"].startswith("The video shows")
    assert [s["role"] for s in d["sources"]] == ["contradicts", "confirms_fact"]


# --- lezer-v5: de lezer leest ook de beste checks uit de database (#32.28) ---------------------------------------

CHECKS = [{"claim": "gfc-1", "tekst": "PM Modi's pictures with Nita Ambani and Tulsi Gowda show preferential treatment",
           "redactie": "FACTLY", "oordeel": "misleidend", "datum": "2021-11-10",
           "url": "https://factly.in/unrelated-photos-of-pm-modi/", "beeld": False},
          {"claim": "gfc-2", "tekst": "Old photo of a flood in Assam shared as Hyderabad", "redactie": "BOOM",
           "oordeel": "onwaar", "datum": "2020-10-15", "url": "https://www.boomlive.in/old-flood/", "beeld": True},
          {"claim": "gfc-3", "tekst": "The floods in Hyderabad killed 50 people", "redactie": "Newschecker",
           "oordeel": "waar", "datum": "2020-10-16", "url": "https://newschecker.in/floods/", "beeld": False}]


def test_reader_v5_reads_the_database_checks_as_their_own_kind_of_source_with_their_verdict():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    v5 = zc.leesverzoek(BERICHT, res, "2021-11-10", _config(lezer="lezer-v5"), checks=CHECKS)
    tekst = v5["messages"][0]["content"]
    assert "[1] nytimes.com (goed)" in tekst and "Fact-checks from our database" in tekst
    assert "[D1] FACTLY, 2021-11-10, rated misleading" in tekst and CHECKS[0]["tekst"] in tekst
    assert "[D2] BOOM, 2020-10-15, rated false" in tekst and CHECKS[1]["url"] in tekst
    assert "[D3] Newschecker, 2020-10-16, rated true" in tekst
    # de zin over het beeld staat alleen bij de check waarvan het beeld de screenshot bevestigt
    assert tekst.count(zc.BEELDZIN) == 1 and tekst.index(zc.BEELDZIN) > tekst.index("[D2]") > tekst.index("[D1]")
    assert v5["output_config"]["format"]["schema"] is zc.SCHEMA_V5 and "checks" in zc.SCHEMA_V5["required"]
    assert zc.LEZERS["lezer-v5"]["regel"] == "ruim" and zc.LEZERS["lezer-v3"]["vraag"] is zc.VRAAG_V3
    leeg = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v5"), checks=[])["messages"][0]["content"]
    assert "Fact-checks from our database" in leeg and "(none)" in leeg and "\n[D1] " not in leeg


def test_reader_v5_never_runs_without_the_database_checks_and_older_readers_never_get_them():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    with pytest.raises(bc.VersieFout):
        zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v5"))
    with pytest.raises(bc.VersieFout):
        zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v3"), checks=CHECKS)
    oud = zc.leesverzoek(BERICHT, res, None, _config(lezer="lezer-v3"))["messages"][0]["content"]
    assert "Fact-checks from our database" not in oud


def test_the_reader_says_per_check_whether_it_is_the_same_claim_and_only_a_plain_yes_counts():
    d = {"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [], "uitleg": "", "over_beeld": False,
         "checks": [{"nr": 1, "zelfde": True}, {"nr": 2, "zelfde": False}, {"nr": 3, "zelfde": "yes"},
                    {"nr": True, "zelfde": True}, "D4", {"nr": 2}]}
    assert zc.lees_oordeel(json.dumps(d))["zelfde"] == [1]
    assert zc.lees_oordeel(json.dumps({**d, "checks": None}))["zelfde"] == []
    assert zc.lees_oordeel(json.dumps({k: v for k, v in d.items() if k != "checks"}))["zelfde"] == []
    assert zc.lees_oordeel("geen json")["zelfde"] == []


def _v5(oordeel="klopt niet", zelfde=(1,), steunt=(), tegen=()):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "",
            "over_beeld": False, "zelfde": list(zelfde)}


def test_a_database_check_the_reader_matches_counts_as_a_good_contradiction_like_the_first_ring():
    assert zc.TEGEN_IN_DATABASE == bc.ONWAAR  # dezelfde oordelen als kring 1
    res = zc.resultaten_uit(_brave("https://www.infowars.com/c"), SITES)  # alleen een lage band
    assert zc.kleur_van(_v5("klopt niet", zelfde=(2,)), res, "ruim", checks=CHECKS) == "rood"
    assert zc.kleur_van(_v5("misleidend", zelfde=(1,)), res, "ruim", checks=CHECKS) == "oranje"
    assert zc.kleur_van(_v5("klopt niet", zelfde=()), res, "ruim", checks=CHECKS) is None
    assert zc.kleur_van(_v5("klopt niet", zelfde=(3,)), res, "ruim", checks=CHECKS) is None  # die check zegt waar
    assert zc.kleur_van(_v5("klopt niet", zelfde=(7,)), res, "ruim", checks=CHECKS) is None  # bestaat niet
    assert zc.kleur_van(_v5("klopt niet", zelfde=(2,)), res, "ruim") is None  # zonder checks telt er geen


def test_a_matched_false_check_blocks_green_and_a_matched_true_check_never_makes_green_on_its_own():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"), SITES)
    assert zc.kleur_van(_v5("klopt", zelfde=(), steunt=(1, 2)), res, "ruim", checks=CHECKS) == "groen"
    assert zc.kleur_van(_v5("klopt", zelfde=(2,), steunt=(1, 2)), res, "ruim", checks=CHECKS) is None
    assert zc.kleur_van(_v5("klopt", zelfde=(3,), steunt=(1,)), res, "ruim", checks=CHECKS) is None


def test_the_sources_show_the_matched_checks_as_checks_from_the_database():
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a"), SITES)
    bronnen = zc.bronnen_van(_v5("klopt niet", zelfde=(2, 3), steunt=(1,)), res, CHECKS)
    assert [(b["url"], b["rol"]) for b in bronnen] == [("https://www.nytimes.com/a", "bevestigt"),
                                                      (CHECKS[1]["url"], "spreekt tegen"),
                                                      (CHECKS[2]["url"], "zelfde bewering")]
    assert [b["soort"] for b in bronnen[1:]] == ["check van een redactie"] * 2
    assert bronnen[1]["redactie"] == "BOOM" and bronnen[1]["oordeel"] == "onwaar"
    assert zc.bronnen_van(_v5("klopt niet", zelfde=(2,)), res) == []  # zonder checks geen checks


def test_the_check_with_reader_v5_passes_the_database_checks_through_to_the_reading_and_the_colour():
    nep = NepModel("klopt niet", steunt=(), tegen=())
    nep.d["checks"] = [{"nr": 2, "zelfde": True}, {"nr": 1, "zelfde": False}]
    zoek = lambda q: _brave("https://www.infowars.com/c")  # noqa: E731
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v5"), nep, zoek, lambda t: None,
                        SITES, None, checks=CHECKS)
    assert "[D2] BOOM" in nep.verzoeken[0]["messages"][0]["content"]
    assert uit["kleur"] == "rood" and uit["versies"]["reader"] == "lezer-v5"
    assert [b["url"] for b in uit["bronnen"]] == [CHECKS[1]["url"]]
    with pytest.raises(bc.VersieFout):
        zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v5"), nep, zoek, lambda t: None,
                      SITES, None)


# --- lezer-v5 in het product: het opzoeken in POST /check (#32.30) -------------------------------------------------

GEHEUGEN = [{"claim": "gfc-2", "gelijkenis": 0.83, "tekst": "Old photo of a flood in Assam shared as Hyderabad",
             "redactie": "BOOM", "oordeel": "onwaar", "datum": "2020-10-15", "url": "https://www.boomlive.in/old-flood/"}]


def test_the_lookup_turns_the_database_candidates_into_checks_for_the_reader():
    assert zc.checks_uit(GEHEUGEN) == [{"claim": "gfc-2", "tekst": GEHEUGEN[0]["tekst"], "redactie": "BOOM",
                                       "oordeel": "onwaar", "datum": "2020-10-15", "url": GEHEUGEN[0]["url"],
                                       "beeld": False}]
    assert zc.checks_uit([]) == []


def test_the_database_checks_are_looked_up_only_after_the_first_ring_misses_and_only_for_reader_v5():
    gevraagd = []

    def zoek_checks(tekst):
        gevraagd.append(tekst)
        return zc.checks_uit(GEHEUGEN)

    zoek = lambda q: _brave("https://www.infowars.com/c")  # noqa: E731
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v5"), NepModel(), zoek, lambda t: snel,
                  SITES, None, zoek_checks=zoek_checks)
    zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v3"), NepModel(), zoek, lambda t: None,
                  SITES, None, zoek_checks=zoek_checks)
    assert gevraagd == []  # kring 1 gaf antwoord, en lezer-v3 leest geen checks
    nep = NepModel("klopt niet", steunt=(), tegen=())
    nep.d["checks"] = [{"nr": 1, "zelfde": True}]
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v5"), nep, zoek, lambda t: None,
                        SITES, None, zoek_checks=zoek_checks)
    assert gevraagd == [BERICHT] and "[D1] BOOM" in nep.verzoeken[0]["messages"][0]["content"]
    assert uit["kleur"] == "rood" and uit["bronnen"][0]["rol"] == "spreekt tegen"


def test_reader_v5_without_a_lookup_still_refuses_before_any_search():
    gezocht = []
    with pytest.raises(bc.VersieFout):
        zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v5"), NepModel(),
                      lambda q: gezocht.append(q), lambda t: None, SITES, None)
    assert gezocht == []


def test_the_endpoint_looks_up_the_checks_and_shows_a_matched_check_with_its_role(monkeypatch):
    nep = NepModel("klopt niet", steunt=(), tegen=())
    nep.d["checks"] = [{"nr": 1, "zelfde": True}]
    zoek = lambda q: _brave("https://www.nytimes.com/a")  # noqa: E731
    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    monkeypatch.setattr(api, "_checks_uit_database", lambda conn, config, tekst: zc.checks_uit(GEHEUGEN))
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_zoeker] = lambda: zoek
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, lezer="lezer-v5")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        d = TestClient(api.app).post("/check", json={"text": BERICHT}).json()
    finally:
        api.app.dependency_overrides.clear()
    assert d["colour"] == "red" and d["versions"]["reader"] == "lezer-v5"
    check = d["sources"][0]
    assert check["kind"] == "check van een redactie" and check["publisher"] == "BOOM"
    assert check["rating"] == "false" and check["role"] == "contradicts"


# --- lezer-v6: alle uitkomsten van besluit A en B48 (#32.31) --------------------------------------------------------

DETAIL_BERICHT = "Russian missiles hit Kyiv on Sunday morning and knocked out power across the country."


def _v6(oordeel="klopt", steunt=(1, 2), tegen=(), vorm="zelf", detail=None, over_beeld=False, zelfde=()):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "", "zelfde": list(zelfde),
            "over_beeld": over_beeld, "vorm": vorm, "detail": detail or {"woorden": "", "juist": "", "nr": 0},
            "feit": "", "feit_steunt": [], "anders": ""}


def _res(*urls, titel="titel", fragment="fragment"):
    return zc.resultaten_uit({"web": {"results": [{"url": u, "title": titel, "description": fragment} for u in urls]}},
                             SITES)


def _na(antwoord, res, bericht=BERICHT, checks=None, beeld_gezien=False):
    return zc.na_lezen(antwoord, bericht, res, checks, "lezer-v6", beeld_gezien)


def test_reader_v6_offers_every_outcome_and_asks_the_form_and_the_detail():
    v6 = zc.LEZERS["lezer-v6"]
    assert v6["database"] and v6["regel"] == "ruim" and v6["schema"] is zc.SCHEMA_V6
    assert set(zc.SCHEMA_V6["properties"]["oordeel"]["enum"]) == {
        "geen bewering", "satire", "klopt", "klopt grotendeels", "klopt niet", "misleidend", "onzeker"}
    assert {"vorm", "detail", "checks", "over_beeld"} <= set(zc.SCHEMA_V6["required"])
    assert zc.SCHEMA_V6["properties"]["vorm"]["enum"] == ["zelf", "over een bewering"]
    tekst = zc.leesverzoek(BERICHT, _res("https://www.nytimes.com/a"), None, _config(lezer="lezer-v6"),
                           checks=CHECKS)["messages"][0]["content"]
    for stuk in ('"geen bewering"', '"satire"', '"klopt grotendeels"', '"over een bewering"', "[D1] FACTLY",
                 "If in doubt, \"zelf\"", "detail"):
        assert stuk in tekst
    # de regel van v3 dat een ontkrachting *klopt* heet, valt weg; v5 blijft zoals gemeten
    assert "judge the message: it is \"klopt\"" not in tekst and "judge the message: it is \"klopt\"" in zc.VRAAG_V5
    assert "geen bewering" not in zc.VRAAG_V5 and zc.LEZERS["lezer-v5"]["schema"] is zc.SCHEMA_V5


def test_the_outcomes_are_those_of_decision_a_b48_b57_and_the_photo_at_the_source():
    assert set(zc.UITKOMSTEN) == {"geen bewering", "satire", "klopt", "klopt grotendeels", "klopt niet", "misleidend",
                                  "over een bewering", "beeld nodig", "niet bevestigd", "onzeker",
                                  "foto niet bij de bron"}


def test_no_claim_never_gets_a_colour_even_with_good_outlets():
    uit = _na(_v6("geen bewering"), _res("https://www.nytimes.com/a", "https://edition.cnn.com/b"))
    assert uit["kleur"] is None and uit["uitkomst"] == "geen bewering"


def test_satire_needs_a_source_that_says_so_and_is_otherwise_uncertain():
    res = _res("https://www.infowars.com/c")
    assert _na(_v6("satire", steunt=(1,)), res)["uitkomst"] == "satire"
    assert _na(_v6("satire", steunt=()), res)["uitkomst"] == "onzeker"
    assert _na(_v6("satire", steunt=(5,)), res)["uitkomst"] == "onzeker"  # een nummer dat niet bestaat
    satire = [{**CHECKS[0], "oordeel": "satire"}]
    assert _na(_v6("satire", steunt=(), zelfde=(1,)), res, checks=satire)["uitkomst"] == "satire"
    assert _na(_v6("satire", steunt=(1,)), res)["kleur"] is None


def test_a_message_about_a_claim_gets_no_colour_but_the_claim_keeps_its_verdict_and_colour():
    res = _res("https://www.nytimes.com/a")
    uit = _na(_v6("klopt niet", steunt=(), tegen=(1,), vorm="over een bewering"), res)
    assert uit["kleur"] is None and uit["uitkomst"] == "over een bewering"
    assert uit["oordeel"] == "klopt niet" and uit["kleur_bewering"] == "rood"
    zelf = _na(_v6("klopt niet", steunt=(), tegen=(1,)), res)
    assert zelf["kleur"] == "rood" and zelf["uitkomst"] == "klopt niet" and zelf["kleur_bewering"] is None


def test_the_form_and_the_detail_are_read_strictly():
    basis = {"oordeel": "klopt", "steunt": [], "spreekt_tegen": [], "uitleg": "", "over_beeld": False, "checks": []}
    assert zc.lees_oordeel(json.dumps({**basis, "vorm": "over een bewering"}))["vorm"] == "over een bewering"
    for vorm in ("Over een bewering", "about a claim", None, 1):
        assert zc.lees_oordeel(json.dumps({**basis, "vorm": vorm}))["vorm"] == "zelf"  # bij twijfel zelf
    assert zc.lees_oordeel(json.dumps(basis))["vorm"] == "zelf"
    goed = {"woorden": " Sunday ", "juist": "Friday", "nr": 2}
    assert zc.lees_oordeel(json.dumps({**basis, "detail": goed}))["detail"] == {"woorden": "Sunday", "juist": "Friday",
                                                                               "nr": 2}
    for fout in ({"woorden": 3, "juist": "Friday", "nr": 2}, {"woorden": "Sunday", "juist": "Friday", "nr": True},
                 {"woorden": "Sunday", "juist": "Friday", "nr": "2"}, "Sunday", None):
        assert zc.lees_oordeel(json.dumps({**basis, "detail": fout}))["detail"] == {"woorden": "", "juist": "",
                                                                                   "nr": 0}
    for oordeel in ("geen bewering", "satire", "klopt grotendeels"):
        assert zc.lees_oordeel(json.dumps({**basis, "oordeel": oordeel}))["oordeel"] == oordeel
    assert zc.lees_oordeel("geen json")["vorm"] == "zelf"


def test_mostly_true_needs_the_wrong_words_in_the_message_and_the_right_value_in_the_cited_result():
    res = _res("https://www.nytimes.com/a", "https://edition.cnn.com/b",
               fragment="Russian missiles hit Kyiv on Friday morning and knocked out power.")
    uit = _na(_v6("klopt grotendeels", detail={"woorden": "sunday", "juist": "Friday", "nr": 2}), res, DETAIL_BERICHT)
    assert uit["uitkomst"] == "klopt grotendeels" and uit["kleur"] is None  # nooit groen, ook met twee goede
    c = uit["correctie"]
    assert c["woorden"] == "Sunday" and DETAIL_BERICHT[c["begin"]:c["eind"]] == "Sunday" and c["juist"] == "Friday"
    assert c["url"] == "https://edition.cnn.com/b" and c["site"] == "cnn.com"
    for fout in ({"woorden": "Monday", "juist": "Friday", "nr": 2},   # staat niet in het bericht
                 {"woorden": "Sunday", "juist": "Saturday", "nr": 2},  # staat niet in het resultaat
                 {"woorden": "Sunday", "juist": "Friday", "nr": 7},    # dat resultaat bestaat niet
                 {"woorden": "Kyiv", "juist": "Kyiv", "nr": 1},        # geen verschil
                 {"woorden": "", "juist": "", "nr": 0}):
        uit = _na(_v6("klopt grotendeels", detail=fout), res, DETAIL_BERICHT)
        assert uit["uitkomst"] == "onzeker" and uit["correctie"] is None and uit["kleur"] is None


def test_mostly_true_never_takes_its_right_value_from_a_low_source_or_one_that_also_has_the_wrong_words():
    laag = _res("https://www.infowars.com/c", fragment="The strikes on Friday morning.")
    uit = _na(_v6("klopt grotendeels", detail={"woorden": "Sunday", "juist": "Friday", "nr": 1}), laag, DETAIL_BERICHT)
    assert uit["uitkomst"] == "onzeker"
    beide = _res("https://www.nytimes.com/a", fragment="Strikes on Friday, and again on Sunday.")
    uit = _na(_v6("klopt grotendeels", detail={"woorden": "Sunday", "juist": "Friday", "nr": 1}), beide, DETAIL_BERICHT)
    assert uit["uitkomst"] == "onzeker"


def test_a_claim_about_an_image_without_the_image_needs_the_image_unless_a_good_source_contradicts_it():
    res = _res("https://www.nytimes.com/a", "https://edition.cnn.com/b")
    assert _na(_v6("klopt", over_beeld=True), res)["uitkomst"] == "beeld nodig"
    assert _na(_v6("onzeker", steunt=(), over_beeld=True), res)["uitkomst"] == "beeld nodig"
    rood = _na(_v6("klopt niet", steunt=(), tegen=(1,), over_beeld=True), res)
    assert rood["kleur"] == "rood" and rood["uitkomst"] == "klopt niet"
    assert _na(_v6("klopt", over_beeld=True), res, beeld_gezien=True)["uitkomst"] == "klopt"


def test_without_a_colour_true_false_and_misleading_are_uncertain_with_the_readers_lean_alongside():
    een = _res("https://www.nytimes.com/a")
    uit = _na(_v6("klopt", steunt=(1,)), een)
    assert uit["kleur"] is None and uit["uitkomst"] == "onzeker" and uit["oordeel"] == "klopt"
    assert _na(_v6("klopt niet", steunt=(), tegen=()), een)["uitkomst"] == "onzeker"
    groen = _na(_v6("klopt"), _res("https://www.nytimes.com/a", "https://edition.cnn.com/b"))
    assert groen["kleur"] == "groen" and groen["uitkomst"] == "klopt"
    oranje = _na(_v6("misleidend", steunt=(), tegen=(1,)), een)
    assert oranje["kleur"] == "oranje" and oranje["uitkomst"] == "misleidend"


def test_older_readers_go_through_the_same_function_with_the_same_colours():
    res = _res("https://www.infowars.com/c")
    v5 = _v5("klopt niet", zelfde=(2,))
    uit = zc.na_lezen({**v5, "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0}}, BERICHT, res, CHECKS,
                      "lezer-v5", False)
    assert uit["kleur"] == zc.kleur_van(v5, res, "ruim", checks=CHECKS) == "rood" and uit["uitkomst"] == "klopt niet"


def test_the_check_with_reader_v6_returns_the_outcome_the_form_and_the_correction():
    nep = NepModel("klopt grotendeels", steunt=(1, 2))
    nep.d.update({"over_beeld": False, "checks": [], "vorm": "zelf",
                  "detail": {"woorden": "Sunday", "juist": "Friday", "nr": 1}})
    zoek = lambda q: {"web": {"results": [  # noqa: E731
        {"url": "https://www.nytimes.com/a", "title": "Strikes on Friday", "description": "Missiles hit Kyiv."},
        {"url": "https://edition.cnn.com/b", "title": "Kyiv", "description": "Power cut."}]}}
    uit = zc.controleer(sqlite3.connect(":memory:"), DETAIL_BERICHT, _config(lezer="lezer-v6"), nep, zoek,
                        lambda t: None, SITES, None, checks=[])
    assert uit["uitkomst"] == "klopt grotendeels" and uit["kleur"] is None and uit["vorm"] == "zelf"
    assert uit["correctie"]["juist"] == "Friday" and uit["versies"]["reader"] == "lezer-v6"
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    db = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v6"), nep, zoek, lambda t: snel,
                       SITES, None)
    assert db["route"] == "database" and db["uitkomst"] == "klopt niet" and db["correctie"] is None


# --- lezer-v7: de zin uit vorm-v2 terug en een strengere *klopt grotendeels* (#32.32) ------------------------------

def test_reader_v7_brings_back_the_sentence_from_form_v2_and_judges_a_reported_statement_on_whether_it_was_said():
    v7 = zc.LEZERS["lezer-v7"]
    assert v7["database"] and v7["schema"] is zc.SCHEMA_V6 and v7["detail"] == "streng"
    tekst = zc.leesverzoek(BERICHT, _res("https://www.nytimes.com/a"), None, _config(lezer="lezer-v7"),
                           checks=CHECKS)["messages"][0]["content"]
    assert ("If the claim is that a person said, wrote or did something, and the message states that as fact, the "
            "message asserts it") in tekst
    assert '"..., reports X"' in tekst and "casts doubt on something in its own voice" in tekst
    assert "a news report on what a party says, alleges or accuses others of" not in tekst
    assert "a news report on what a party says, alleges or accuses others of" in zc.VRAAG_V6  # v6 blijft als gemeten
    assert '"over een bewering"' in tekst and "If in doubt, \"zelf\"" in tekst


def test_reader_v7_names_what_can_be_defended_and_is_no_wrong_detail():
    tekst = zc.VRAAG_V7
    for stuk in ("changed over time", '"suspended" and "deleted"', "a description that is also true",
                 "If in doubt, it is not a wrong detail"):
        assert stuk in tekst and stuk not in zc.VRAAG_V6


def test_the_strict_correction_needs_a_reliable_source_for_the_right_value():
    anders = _res("https://www.example.org/a", fragment="Russian missiles hit Kyiv on Friday morning.")
    assert anders[0]["band"] is None and anders[0]["soort"] != "platform"
    d = _v6("klopt grotendeels", steunt=(), detail={"woorden": "Sunday", "juist": "Friday", "nr": 1})
    assert zc.verbetering(d, DETAIL_BERICHT, anders) is not None  # v6 laat een site zonder band toe
    assert zc.verbetering(d, DETAIL_BERICHT, anders, streng=True) is None
    goed = _res("https://www.nytimes.com/a", fragment="Russian missiles hit Kyiv on Friday morning.")
    assert zc.verbetering({**d, "detail": {**d["detail"]}}, DETAIL_BERICHT, goed, streng=True)["juist"] == "Friday"


def test_the_strict_correction_gives_no_but_when_a_confirming_result_has_the_same_words():
    res = zc.resultaten_uit({"web": {"results": [
        {"url": "https://www.nytimes.com/a", "title": "Strikes on Friday", "description": "Missiles hit Kyiv."},
        {"url": "https://edition.cnn.com/b", "title": "Kyiv", "description": "The Sunday strikes cut power."}]}}, SITES)
    d = _v6("klopt grotendeels", steunt=(2,), detail={"woorden": "Sunday", "juist": "Friday", "nr": 1})
    assert zc.verbetering(d, DETAIL_BERICHT, res) is not None
    assert zc.verbetering(d, DETAIL_BERICHT, res, streng=True) is None  # een bevestigende bron zegt het ook zo
    zonder = {**d, "steunt": []}
    assert zc.verbetering(zonder, DETAIL_BERICHT, res, streng=True) is not None
    uit = zc.na_lezen(d, DETAIL_BERICHT, res, [], "lezer-v7", False)
    assert uit["uitkomst"] == "onzeker" and uit["correctie"] is None
    assert zc.na_lezen(d, DETAIL_BERICHT, res, [], "lezer-v6", False)["uitkomst"] == "klopt grotendeels"


# --- lezer-v7 in het product: de negen uitkomsten in `POST /check` (#32.32) ----------------------------------------

def _post_v7(monkeypatch, antwoord: dict, resultaten: list[dict], bericht: str = BERICHT) -> dict:
    nep = NepModel()
    nep.d = antwoord
    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    monkeypatch.setattr(api, "_checks_uit_database", lambda conn, config, tekst: [])
    api.app.dependency_overrides[api.get_anthropic] = lambda: nep
    api.app.dependency_overrides[api.get_zoeker] = lambda: (lambda q: {"web": {"results": resultaten}})
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, lezer="lezer-v7")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        return TestClient(api.app).post("/check", json={"text": bericht}).json()
    finally:
        api.app.dependency_overrides.clear()


TWEE_KRANTEN = [{"url": "https://www.nytimes.com/a", "title": "Train crash near Toledo", "description": "Many died."},
                {"url": "https://edition.cnn.com/b", "title": "Toledo collision", "description": "A deadly crash."}]


def test_the_endpoint_says_which_of_the_nine_outcomes_it_is_and_no_claim_never_gets_a_colour(monkeypatch):
    # tien uitkomsten sinds B57, elf met de foto bij de bron (#32.54)
    assert set(api._UITKOMST_EN) == set(zc.UITKOMSTEN) and len(set(api._UITKOMST_EN.values())) == 11
    d = _post_v7(monkeypatch, _v6("geen bewering", steunt=()), TWEE_KRANTEN)
    assert d["outcome"] == "no_claim" and d["colour"] is None and d["correction"] is None
    groen = _post_v7(monkeypatch, _v6("klopt"), TWEE_KRANTEN)
    assert groen["outcome"] == "true" and groen["colour"] == "green"


def test_mostly_true_comes_with_the_correction_and_where_the_wrong_words_sit_in_what_was_read(monkeypatch):
    res = [{"url": "https://www.nytimes.com/a", "title": "Train crash near Toledo",
            "description": "At least 77 people were killed when two trains collided."}, TWEE_KRANTEN[1]]
    d = _post_v7(monkeypatch, _v6("klopt grotendeels", steunt=(2,), detail={"woorden": "68", "juist": "77", "nr": 1}),
                 res)
    assert d["outcome"] == "mostly_true" and d["colour"] is None
    c = d["correction"]
    assert c["words"] == "68" and c["should_be"] == "77" and c["publisher"] == "nytimes.com"
    assert c["url"] == "https://www.nytimes.com/a" and d["read"][c["start"]:c["end"]] == "68"


def test_a_message_about_someone_elses_claim_gets_no_colour_but_the_claim_itself_does(monkeypatch):
    d = _post_v7(monkeypatch, _v6("klopt niet", steunt=(), tegen=(1,), vorm="over een bewering"), TWEE_KRANTEN)
    assert d["outcome"] == "about_a_claim" and d["colour"] is None and d["claim_colour"] == "red"
    assert _post_v7(monkeypatch, _v6("klopt niet", steunt=(), tegen=(1,)), TWEE_KRANTEN)["claim_colour"] is None


# --- B55: het beeld gaat zwartgemaakt mee (#32.36) ------------------------------------------------------------------

def test_the_check_sends_the_blacked_image_and_only_with_the_switch_on(monkeypatch):
    gezien = []
    monkeypatch.setattr("doublecheck.opknippen.zwart_beeld", lambda b, ocr: (gezien.append(b) or b"ZWART", 2))
    nep = NepModel()
    zoek = lambda q: _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa: E731
    zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(beeld=True), nep, zoek, lambda t: None, SITES, None,
                  beeld=PNG, checks=[])
    blokken = nep.verzoeken[-1]["messages"][0]["content"]
    assert gezien == [PNG] and blokken[0]["type"] == "image"
    import base64
    assert base64.b64decode(blokken[0]["source"]["data"]) == b"ZWART"
    zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(beeld=False), nep, zoek, lambda t: None, SITES, None,
                  beeld=PNG, checks=[])
    assert gezien == [PNG] and isinstance(nep.verzoeken[-1]["messages"][0]["content"], str)


def test_factiz_itself_is_never_a_source_so_a_page_of_ours_cannot_carry_its_own_verdict():
    # #32.68: zodra factiz.org zelf pagina's publiceert over wat er rondgaat, kan de zoekdienst die teruggeven. Telt zo'n
    # pagina als bron, dan draagt Factiz zijn eigen oordeel (geen kringloop, ROUTEKAART-V1 §6). Ook een subdomein telt
    # niet, en de nummering blijft doorlopen, want de uitleg verwijst naar [n].
    res = zc.resultaten_uit(_brave("https://www.nytimes.com/a", "https://factiz.org/nl/rondgaat/vogue-cover/",
                                   "https://www.factiz.org/en/circulating/vogue-cover/", "https://try.factiz.org/check",
                                   "https://edition.cnn.com/b", "https://notfactiz.org/x"), SITES)
    assert [(r["nr"], r["site"]) for r in res] == [(1, "nytimes.com"), (2, "cnn.com"), (3, "notfactiz.org")]
    assert zc.van_factiz("https://FACTIZ.org/x") and not zc.van_factiz("https://factiz.org.evil.com/x")
