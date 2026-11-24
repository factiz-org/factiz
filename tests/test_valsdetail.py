"""Een echt verhaal met één vals detail (B48, PLAN #32.3a): de detailvraag na
*klopt*, en de controle in code die bepaalt of er een *maar* komt."""

import dataclasses
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as bc
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

BERICHT = ("Russia on Friday rejected blame for the death of former KGB agent Alexander Litvinenko. "
           "The ex-spy died in  2003 after being poisoned with a radioactive substance.")
BRONNEN = [{"soort": "web", "url": "https://www.france24.com/a",
            "citaat": "The ex-spy died in 2006 after a radioactive substance was slipped into his tea."},
           {"soort": "web", "url": "https://www.cnn.com/b", "citaat": "Russia on Friday rejected blame."}]
TABEL = bc.ijktabel(load_config(None))


def _na(oordeel="klopt", stand=8):
    return {"oordeel": oordeel, "stand": {"stand": stand, "woorden": "x", "laag": "web"}, "feit": None,
            "kleur": bc.kleur(stand, oordeel), "regels": [], "meting": None}


def test_a_false_detail_named_by_a_cited_passage_becomes_mostly_true_and_never_green():
    d = {"woorden": "2003", "juist": "2006", "bron": 1, "citaat": "died in 2006"}
    na = bc.met_detail(TABEL, _na(), BERICHT, BRONNEN, [d])
    assert na["oordeel"] == "klopt grotendeels" and na["kleur"] is None and "vals detail" in na["regels"]
    [c] = na["correcties"]
    assert c["woorden"] == "2003" and c["juist"] == "2006" and c["url"] == "https://www.france24.com/a"
    assert BERICHT[c["begin"]:c["eind"]] == "2003"
    assert na["stand"]["stand"] < 7


def test_words_not_in_the_message_or_a_value_not_in_the_passage_give_no_but():
    zelfde = _na()
    for d in ({"woorden": "1999", "juist": "2006", "bron": 1, "citaat": ""},
              {"woorden": "2003", "juist": "2007", "bron": 1, "citaat": ""},
              {"woorden": "2003", "juist": "2006", "bron": 9, "citaat": ""},
              {"woorden": "2003", "juist": "2003", "bron": 1, "citaat": ""}):
        assert bc.met_detail(TABEL, zelfde, BERICHT, BRONNEN, [d]) == zelfde


def test_words_that_the_passage_also_states_are_not_contradicted():
    d = {"woorden": "rejected blame", "juist": "Russia", "bron": 2, "citaat": ""}
    assert bc.met_detail(TABEL, _na(), BERICHT, BRONNEN, [d]) == _na()


def test_two_false_details_make_it_false():
    bronnen = BRONNEN + [{"soort": "web", "url": "https://x.org", "citaat": "a former FSB officer"}]
    ds = [{"woorden": "2003", "juist": "2006", "bron": 1, "citaat": ""},
          {"woorden": "KGB agent", "juist": "FSB officer", "bron": 3, "citaat": ""}]
    na = bc.met_detail(TABEL, _na(), BERICHT, bronnen, ds)
    assert na["oordeel"] == "klopt niet" and na["kleur"] == "rood" and len(na["correcties"]) == 2


def test_only_a_true_verdict_gets_a_but():
    d = {"woorden": "2003", "juist": "2006", "bron": 1, "citaat": ""}
    onzeker = _na("onzeker", 5)
    assert bc.met_detail(TABEL, onzeker, BERICHT, BRONNEN, [d]) == onzeker


def test_the_place_of_the_words_is_found_despite_spacing_and_case():
    assert bc.plaats("He died in  2003 in London", "died in 2003") == (3, 16)
    assert bc.plaats("THE EX-SPY", "the ex-spy") == (0, 10)
    assert bc.plaats("nothing here", "2003") is None


def test_the_detail_question_only_reads_the_cited_passages():
    params = bc.detailverzoek(BERICHT, {"uitleg": "Litvinenko overleed in 2006.", "bronnen": BRONNEN},
                              "detail-v1", load_config(None))
    inhoud = params["messages"][0]["content"]
    assert BERICHT in inhoud and "[B1] https://www.france24.com/a" in inhoud and "Litvinenko overleed in 2006." in inhoud
    assert "tools" not in params and params["model"] == load_config(None).berichtcontrole.model_id


def test_reading_the_detail_answer_strictly():
    tekst = ('{"waarom": "x", "details": [{"woorden": "2003", "juist": "2006", "bron": 1, "citaat": "died in 2006"},'
             ' {"woorden": "", "juist": "x", "bron": 2, "citaat": ""}, {"woorden": "a", "juist": "b", "bron": "één",'
             ' "citaat": ""}]}')
    assert bc.lees_detail(tekst) == [{"woorden": "2003", "juist": "2006", "bron": 1, "citaat": "died in 2006"}]
    assert bc.lees_detail("geen json") == [] and bc.lees_detail('{"details": "x"}') == []


def test_the_second_step_searches_only_for_a_detail_the_note_names():
    notitie = bc.lees_notitie('{"waarom": "x", "details": [], "notitie": {"afwijking": true, "woorden": "2003",'
                              ' "juist": "2006"}}')
    assert notitie == {"afwijking": True, "woorden": "2003", "juist": "2006"}
    assert bc.lees_notitie('{"details": [], "notitie": {"afwijking": false, "woorden": "", "juist": ""}}') is None
    params = bc.zoekverzoek(BERICHT, notitie, "detail-v2", load_config(None))
    assert params["tools"][0]["type"] == "web_search_20250305" and "2003" in params["messages"][0]["content"]


def test_a_found_source_must_state_the_correct_value_itself():
    blokken = [{"type": "text", "text": "WOORDEN: 2003\nJUIST: 2006",
                "citations": [{"type": "web_search_result_location", "url": "https://www.bbc.com/x",
                               "cited_text": "Litvinenko died in London in November 2006.", "title": "t"}]}]
    details, passages = bc.lees_zoekdetail(blokken)
    na = bc.met_detail(TABEL, _na(), BERICHT, BRONNEN, details, passages)
    assert na["oordeel"] == "klopt grotendeels" and na["correcties"][0]["url"] == "https://www.bbc.com/x"
    zonder = [{"type": "text", "text": "WOORDEN: 2003\nJUIST: 2006", "citations": [
        {"type": "web_search_result_location", "url": "https://x.org", "cited_text": "He died in London.", "title": ""}]}]
    details, passages = bc.lees_zoekdetail(zonder)
    assert bc.met_detail(TABEL, _na(), BERICHT, BRONNEN, details, passages) == _na()


def test_the_passages_of_one_page_count_together_in_the_second_step():
    blokken = [{"type": "text", "text": "WOORDEN: 2003\nJUIST: November 2006", "citations": [
        {"type": "web_search_result_location", "url": "https://www.bbc.com/x", "cited_text": "Litvinenko died in London in", "title": ""},
        {"type": "web_search_result_location", "url": "https://www.bbc.com/x", "cited_text": "November 2006 after drinking tea.", "title": ""}]}]
    details, passages = bc.lees_zoekdetail(blokken)
    assert len(passages) == 1 and details[0]["bron"] == 1
    assert bc.met_detail(TABEL, _na(), BERICHT, BRONNEN, details, passages)["oordeel"] == "klopt grotendeels"


# De detailvraag in de controle zelf (B48 aan, PLAN #32.3a): een nep-client staat in voor Anthropic.
class _Blok:
    def __init__(self, **velden):
        self.__dict__.update(velden)

    def model_dump(self):
        return dict(self.__dict__)


class _Antwoord:
    def __init__(self, blokken):
        self.content = blokken
        self.usage = _Blok(input_tokens=4_000, output_tokens=400, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0, server_tool_use=_Blok(web_search_requests=1))
        self.stop_reason = "end_turn"


def _schema(params):
    return params.get("output_config", {}).get("format", {}).get("schema", {}).get("properties", {})


class _Nep:
    """De machine zegt *klopt* met een webpassage; de detailvraag geeft `details` terug."""

    def __init__(self, details):
        self.details, self.verzoeken, self.messages = details, [], self

    def create(self, **params):
        self.verzoeken.append(params)
        if "tools" in params:
            return _Antwoord([
                _Blok(type="text", text="Litvinenko died after being poisoned. ", citations=[
                    {"type": "web_search_result_location", "url": BRONNEN[0]["url"], "cited_text": BRONNEN[0]["citaat"],
                     "title": "France 24"}]),
                _Blok(type="text", text="\nBEWERING: Russia rejected blame for Litvinenko's death\nOORDEEL: klopt\n"
                                        "UITLEG: Klopt.", citations=None)])
        if "details" in _schema(params):
            return _Antwoord([_Blok(type="text", text=json.dumps(
                {"waarom": "x", "details": self.details, "notitie": {"afwijking": False, "woorden": "", "juist": ""}}),
                citations=None)])
        return _Antwoord([_Blok(type="text", text=json.dumps({"waarom": "", "vorm": "zelf", "beeld": False}),
                                citations=None)])


def _config(**instellingen):
    config = load_config(None)
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _beoordeel(nep, config):
    return bc.beoordeel(sqlite3.connect(":memory:"), {"tekst": BERICHT, "geheugen": [], "kandidaten": []}, nep,
                        config, "2026-10-28", TABEL, {})


DETAIL = {"woorden": "2003", "juist": "2006", "bron": 1, "citaat": "died in 2006"}


def test_the_detail_question_is_switched_on_in_the_check():
    assert load_config(None).berichtcontrole.detail == "detail-v3"


def test_the_check_asks_the_detail_question_after_true_and_returns_the_place_of_the_words():
    uit = _beoordeel(_Nep([DETAIL]), _config(aan=True, detail="detail-v3"))
    assert uit["oordeel"] == "klopt grotendeels" and uit["kleur"] is None and "vals detail" in uit["regels"]
    [c] = uit["correcties"]
    assert uit["gelezen"][c["begin"]:c["eind"]] == "2003" and c["juist"] == "2006"
    assert uit["versies"]["detail"] == "detail-v3"


def test_without_the_detail_question_true_stays_true_and_nothing_extra_is_asked():
    nep = _Nep([DETAIL])
    uit = _beoordeel(nep, _config(aan=True, detail=""))
    assert uit["oordeel"] == "klopt" and uit["correcties"] == []
    assert not any("details" in _schema(p) for p in nep.verzoeken)


def test_an_unknown_detail_version_refuses_before_any_question():
    nep = _Nep([DETAIL])
    with pytest.raises(bc.VersieFout):
        _beoordeel(nep, _config(aan=True, detail="detail-v9"))
    assert nep.verzoeken == []

