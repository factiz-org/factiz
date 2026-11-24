"""De vloerstap in de controle (B50, PLAN #32.0m, SPECS AC13): als de machine zonder
bron twijfelt, vragen twee korte vragen zonder zoeken of de bewering duidelijk in
strijd is met algemeen bekende kennis. Een nep-client staat in voor Anthropic."""

import dataclasses
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as bc
from doublecheck import vloer as vl
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

ONZIN = "Barack Obama was born in Honolulu, Hawaii, in 1961 and weighed 50 pounds at birth."
NEDERLANDS = "Barack Obama werd in 1961 geboren in Honolulu en woog bij zijn geboorte vijftig pond, zeggen ze."
TABEL = {("onzeker", "geen bron"): {"stand": 5, "n": 100, "aandeel waar": 0.5},
         ("let op", "geen bron"): {"stand": 5, "n": 60, "aandeel waar": 0.3},
         ("klopt niet", "web"): {"stand": 3, "n": 200, "aandeel waar": 0.04},
         ("klopt niet", "algemene kennis"): {"stand": 3, "n": 40, "aandeel waar": 0.0}}
WEB = {"type": "web_search_result_location", "url": "https://www.bbc.com/x", "cited_text": "Obama weighed 8 pounds.",
       "title": "BBC"}


class _Blok:
    def __init__(self, **velden):
        self.__dict__.update(velden)

    def model_dump(self):
        return dict(self.__dict__)


def _antwoord(tekst, citaties=None, zoek=1):
    return _Blok(content=[_Blok(type="text", text=tekst, citations=citaties)], stop_reason="end_turn",
                 usage=_Blok(input_tokens=1_000, output_tokens=200, cache_read_input_tokens=0,
                             cache_creation_input_tokens=0, server_tool_use=_Blok(web_search_requests=zoek)))


def _schema(params):
    return params.get("output_config", {}).get("format", {}).get("schema", {}).get("properties", {})


class _Nep:
    """De machine zegt `oordeel`; de vloervragen zeggen per sleutel wat in `vloer` staat."""

    def __init__(self, oordeel="onzeker", citaties=None, vloer=("clearly false", "clearly false")):
        self.oordeel, self.citaties, self.vloer = oordeel, citaties, dict(zip("AB", vloer))
        self.verzoeken, self.messages = [], self

    def create(self, **params):
        self.verzoeken.append(params)
        if "tools" in params:
            return _antwoord(f"Gezocht.\nBEWERING: Obama weighed 50 pounds at birth\nOORDEEL: {self.oordeel}\n"
                             "UITLEG: Geen bron gevonden.", self.citaties)
        props = _schema(params)
        if "oordeel" in props and "enum" in props["oordeel"]:
            sleutel = "A" if params["messages"][0]["content"].startswith("Message:") else "B"
            return _antwoord(json.dumps({"waarom": "x", "oordeel": self.vloer[sleutel]}), zoek=0)
        if "vorm" in props:
            return _antwoord(json.dumps({"waarom": "", "vorm": "zelf", "beeld": False}), zoek=0)
        return _antwoord(json.dumps({"richting": "geen", "feit": "", "waarom": ""}), zoek=0)


def _vloervragen(nep):
    return [p for p in nep.verzoeken if "enum" in _schema(p).get("oordeel", {})]


def _config(**instellingen):
    config = load_config(None)
    instellingen = {"aan": True, "vloer": "vloer-v1", **instellingen}
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _beoordeel(nep, tekst=ONZIN, config=None, tabel=None):
    return bc.beoordeel(sqlite3.connect(":memory:"), {"tekst": tekst, "geheugen": [], "kandidaten": []}, nep,
                        config or _config(), "2026-10-28", TABEL if tabel is None else tabel, {})


def test_unsure_without_a_source_becomes_false_on_common_knowledge_when_both_questions_say_so():
    nep = _Nep()
    uit = _beoordeel(nep)
    assert uit["oordeel"] == "klopt niet" and uit["kleur"] == "rood"
    assert uit["stand"] == {"stand": 3, "woorden": "waarschijnlijk onwaar", "laag": "algemene kennis"}
    assert "algemene kennis" in uit["regels"] and uit["versies"]["floor"] == "vloer-v1"
    assert uit["meting"] == {"n": 40, "aandeel waar": 0.0}
    assert len(_vloervragen(nep)) == 2 and all("tools" not in p for p in _vloervragen(nep))
    assert ONZIN in _vloervragen(nep)[0]["messages"][0]["content"]


def test_one_question_that_is_not_sure_leaves_the_verdict_of_the_machine():
    uit = _beoordeel(_Nep(vloer=("clearly false", "not clearly false")))
    assert uit["oordeel"] == "onzeker" and uit["kleur"] is None and "algemene kennis" not in uit["regels"]


def test_the_floor_is_not_asked_with_a_source_with_another_verdict_in_another_language_or_when_off():
    gevallen = [(_Nep(citaties=[WEB]), ONZIN, _config()), (_Nep(oordeel="klopt niet"), ONZIN, _config()),
                (_Nep(), NEDERLANDS, _config()), (_Nep(), ONZIN, _config(vloer=""))]
    for nep, tekst, config in gevallen:
        uit = _beoordeel(nep, tekst, config)
        assert _vloervragen(nep) == [] and "algemene kennis" not in uit["regels"]


def test_without_a_calibrated_class_of_at_least_stand_3_no_floor_question_is_asked():
    for tabel in ({k: v for k, v in TABEL.items() if k[1] != "algemene kennis"},
                  {**TABEL, ("klopt niet", "algemene kennis"): {"stand": 5, "n": 12, "aandeel waar": 0.0}}):
        nep = _Nep()
        uit = _beoordeel(nep, tabel=tabel)
        assert _vloervragen(nep) == [] and uit["oordeel"] == "onzeker"


def test_an_unknown_floor_version_or_another_model_refuses_before_any_question():
    for config in (_config(vloer="vloer-v9"), _config(vloer_model="claude-sonnet-5-5")):
        nep = _Nep()
        with pytest.raises(bc.VersieFout):
            _beoordeel(nep, config=config)
        assert nep.verzoeken == []


def test_the_floor_asks_exactly_the_questions_of_the_pre_measurement():
    config = _config()
    for sleutel in vl.SLEUTELS:
        assert bc.vloerverzoek(ONZIN, sleutel, config) == vl.verzoek(ONZIN, sleutel, config)


def test_the_cost_of_the_floor_questions_is_booked():
    zonder = _beoordeel(_Nep(), config=_config(vloer=""))
    met = _beoordeel(_Nep())
    assert met["kosten"] > zonder["kosten"]


def test_floor_v2_is_on_after_its_round_and_the_layer_is_calibrated():
    config = load_config(None)
    assert config.berichtcontrole.vloer == "vloer-v2" and config.berichtcontrole.vloer_model == "claude-haiku-5-5"
    klasse = bc.ijktabel(config)[("klopt niet", "algemene kennis")]
    assert klasse["n"] >= 30 and klasse["stand"] == 3


def test_floor_v2_also_comes_when_the_machine_is_unsure_with_sources_and_v1_does_not():
    met_bron = _beoordeel(_Nep(citaties=[WEB]), config=_config(vloer="vloer-v2"))
    assert met_bron["oordeel"] == "klopt niet" and "algemene kennis" in met_bron["regels"]
    assert _beoordeel(_Nep(citaties=[WEB]), config=_config(vloer="vloer-v1"))["oordeel"] == "onzeker"
    nep = _Nep(oordeel="klopt niet", citaties=[WEB])
    _beoordeel(nep, config=_config(vloer="vloer-v2"))
    assert _vloervragen(nep) == []  # alleen bij onzeker of let op
    nep = _Nep(citaties=[WEB])
    _beoordeel(nep, NEDERLANDS, _config(vloer="vloer-v2"))
    assert _vloervragen(nep) == []  # alleen Engels
