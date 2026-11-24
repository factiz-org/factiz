"""De foto bij de bron in de echte controle (PLAN #32.54, DESIGN §4m; PO 2026-11-08: "graag"): na het oordeel, op het
onbewerkte beeld in het geheugen, alleen als `[berichtcontrole] fotobron` een versie noemt. Het antwoord in twee lagen:
het nieuws mag groen zijn, de foto staat apart, en het bericht als geheel krijgt geen groen als de foto er niet is."""

import dataclasses
import io
import json
import sqlite3

import pytest

from doublecheck import api
from doublecheck import berichtcontrole as bc
from doublecheck import fotobron as fb
from doublecheck import zoekcontrole as zc
from doublecheck.config import ConfigError, load_config
from tests.beelden import vormen

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]]}
BERICHT = "Flooding in Valencia on Tuesday left streets under water."


def _bytes(beeld) -> bytes:
    uit = io.BytesIO()
    beeld.convert("RGB").save(uit, format="PNG")
    return uit.getvalue()


FOTO, ANDERE = _bytes(vormen(7, 640, 480)), _bytes(vormen(11, 640, 480))


def _config(**instellingen):
    config = load_config()
    standaard = {"lezer": "lezer-v18", "speurvraag_model": "claude-haiku-5-5", "beeld": False}
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole,
                                                                           **{**standaard, **instellingen}))


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class _Antwoord:
    def __init__(self, d):
        self.content, self.usage, self.stop_reason = [_Blok(json.dumps(d))], _Gebruik(), "end_turn"


class Reeks:
    def __init__(self, *antwoorden):
        self.antwoorden, self.verzoeken = antwoorden, []

    def create(self, **params):
        self.verzoeken.append(params)
        return _Antwoord(self.antwoorden[len(self.verzoeken) - 1])

    @property
    def messages(self):
        return self


def _model():
    klopt = {"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [], "uitleg": "Dit klopt: het water stond hoog [1].",
             "over_beeld": False, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
             "zou_gemeld": True}
    return Reeks({"verder_zoeken": []}, klopt)


def _zoek(q):
    return {"web": {"results": [{"url": "https://www.nytimes.com/valencia", "title": "Valencia floods",
                                 "description": "Streets under water in Valencia."},
                                {"url": "https://www.cnn.com/valencia", "title": "Floods in Spain",
                                 "description": "Valencia flooding on Tuesday."}]}}


def _haler(beeld_op_pagina, gevraagd=None):
    def beelden_van(url):
        if gevraagd is not None:
            gevraagd.append(url)
        return [url + "/foto.jpg"]
    return beelden_van, lambda u: beeld_op_pagina


def _controleer(config, haler, beeld=FOTO):
    return zc.controleer(sqlite3.connect(":memory:"), BERICHT, config, _model(), _zoek, lambda t: None, SITES,
                         "2026-11-09", beeld=beeld, zoek_checks=lambda t: [], foto_haler=lambda: haler)


def test_the_switch_names_a_version_or_is_off_and_an_unknown_version_is_refused(tmp_path):
    assert load_config().berichtcontrole.fotobron in fb.VERSIES  # aan sinds de release van 2026-11-09 (B66)
    tekst = open("config.toml", encoding="utf-8").read().replace("[berichtcontrole]\n",
                                                                 '[berichtcontrole]\nfotobron = "fotobron-v9"\n', 1)
    pad = tmp_path / "config.toml"
    pad.write_text(tekst, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(pad)


def test_with_the_switch_off_the_photo_is_never_looked_up():
    gevraagd = []
    uit = _controleer(_config(fotobron=""), _haler(ANDERE, gevraagd))
    assert uit["kleur"] == "groen" and gevraagd == [] and "foto" not in uit


def test_green_without_the_photo_at_its_sources_becomes_news_confirmed_photo_not_found():
    uit = _controleer(_config(fotobron="fotobron-v2"), _haler(ANDERE))
    assert uit["kleur"] is None and uit["uitkomst"] == fb.UITKOMST and uit["kleur_nieuws"] == "groen"
    assert uit["foto"]["gevonden"] is None and uit["versies"]["photo"] == "fotobron-v2"


def test_green_with_the_photo_at_a_confirming_source_stays_green_with_the_page():
    uit = _controleer(_config(fotobron="fotobron-v2"), _haler(FOTO))
    assert uit["kleur"] == "groen" and uit["foto"]["gevonden"] == "https://www.nytimes.com/valencia"


def test_a_failing_page_means_not_found_and_never_green():
    def kapot(url):
        raise OSError("geen verbinding")
    uit = _controleer(_config(fotobron="fotobron-v2"), (kapot, lambda u: None))
    assert uit["kleur"] is None and uit["uitkomst"] == fb.UITKOMST


def test_without_an_image_the_answer_is_as_before():
    gevraagd = []
    uit = _controleer(_config(fotobron="fotobron-v2"), _haler(ANDERE, gevraagd), beeld=None)
    assert uit["kleur"] == "groen" and gevraagd == []


def test_the_endpoint_gives_the_two_layers(monkeypatch):
    from fastapi.testclient import TestClient

    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": SITES})
    monkeypatch.setattr(bc, "bericht_uit", lambda tekst, beeld, ocr: BERICHT)
    monkeypatch.setattr(api, "_checks_uit_database", lambda conn, config, tekst: [])
    monkeypatch.setattr(fb, "haler", lambda: _haler(ANDERE))
    api.app.dependency_overrides[api.get_anthropic] = _model
    api.app.dependency_overrides[api.get_zoeker] = lambda: _zoek
    api.app.dependency_overrides[api.get_config] = lambda: _config(aan=True, fotobron="fotobron-v2")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        d = TestClient(api.app).post("/check", files={"image": ("f.png", FOTO, "image/png")}).json()
    finally:
        api.app.dependency_overrides.clear()
    assert d["outcome"] == "photo_not_at_source" and d["colour"] is None and d["news_colour"] == "green"
    assert d["photo"] == {"found": False, "page": None, "checked": 2}


def test_the_page_shows_the_news_and_the_photo_as_two_layers():
    from doublecheck.checkui import pagina

    html = pagina(True, True)
    assert "photo_not_at_source" in html and "News confirmed, photo not found" in html
    assert "None of the reliable sources that confirm this news shows this photo." in html
    assert "The photo appears at" in html


def test_a_green_from_the_database_also_needs_the_photo_at_a_source_as_in_the_measurement():
    """In de meting gold de regel voor elk groen antwoord, ook uit kring 1 (de database); het product doet hetzelfde,
    en de lezer die de uitleg geeft, zoekt de foto niet nog eens."""
    check = {"soort": "check van een redactie", "url": "https://www.snopes.com/x", "redactie": "Snopes",
             "oordeel": "waar", "rol": "zelfde bewering"}
    gevraagd = []
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(fotobron="fotobron-v2"), _model(), _zoek,
                        lambda t: {"oordeel": "waar", "kleur": "groen", "bronnen": [check]}, SITES, "2026-11-09",
                        beeld=FOTO, zoek_checks=lambda t: [], foto_haler=lambda: _haler(ANDERE, gevraagd))
    assert uit["route"] == "database" and uit["kleur"] is None and uit["uitkomst"] == fb.UITKOMST
    assert sorted(gevraagd) == ["https://www.cnn.com/valencia", "https://www.nytimes.com/valencia"]

