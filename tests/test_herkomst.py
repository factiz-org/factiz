"""De herkomstcontrole (PLAN #32.3e): een screenshot dat een site met band goed noemt,
krijgt één zoekvraag beperkt tot die site; gelijk, anders of niet gevonden. De regels
die vóór de meting vastlagen. Een nep-client staat in voor Anthropic."""

import dataclasses
import json
import sqlite3

import pytest

from doublecheck import berichtcontrole as bc
from doublecheck import herkomst as hk
from doublecheck.config import load_config

SITES = {"bbc.com": [["goed", "x"]], "dw.com": [["goed", "x"]], "nypost.com": [["laag", "x"]],
         "kyivpost.com": [["wisselend", "x"]]}
BERICHT = ("https://www.bbc.com/news BBC Four in EU-Qatar bribery inquiry to stay in custody Four people were detained "
           "by police on 12 March in Brussels.")
TABEL = {("klopt", "web"): {"stand": 7, "n": 300, "aandeel waar": 0.92},
         ("klopt niet", "web"): {"stand": 3, "n": 200, "aandeel waar": 0.04},
         ("onzeker", "web"): {"stand": 5, "n": 100, "aandeel waar": 0.5},
         ("onzeker", "geen bron"): {"stand": 5, "n": 100, "aandeel waar": 0.5}}


def _config(**instellingen):
    config = load_config(None)
    instellingen = {"aan": True, "herkomst": "herkomst-v1", "vloer": "", "detail": "", "vorm": "", **instellingen}
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _blokken(uitkomst, verschillen=(), citaten=(), url="https://www.bbc.com/news/world-1"):
    regel = json.dumps({"uitkomst": uitkomst, "url": url, "verschillen": list(verschillen)})
    tekst = [{"type": "text", "text": "I searched bbc.com and found the article.",
              "citations": [{"type": "web_search_result_location", "url": url, "cited_text": c, "title": "BBC"}
                            for c in citaten]},
             {"type": "text", "text": "\n" + regel, "citations": None}]
    return tekst


def test_only_the_first_site_with_a_good_band_triggers_the_step():
    assert bc.herkomst_site(BERICHT, SITES, frozenset()) == "bbc.com"
    assert bc.herkomst_site("https://www.kyivpost.com/news KYIVPOST Kazakhstan unrest", SITES) is None
    assert bc.herkomst_site("Shared from youtube.com and bbc.com: a video", SITES, frozenset()) == "bbc.com"
    assert bc.herkomst_site("BBC reports that four people were detained.", SITES) is None  # een naam is geen domein
    assert bc.herkomst_site("https://edition.dw.com/en/x DW headline", SITES, frozenset()) == "dw.com"


def test_a_site_the_search_tool_does_not_reach_never_triggers_the_step():
    assert "bbc.com" in bc.GEEN_TOEGANG and "reuters.com" in bc.GEEN_TOEGANG
    assert bc.herkomst_site(BERICHT, SITES, bc.GEEN_TOEGANG) is None
    assert bc.herkomst_site(BERICHT + " Also on dw.com and rferl.org.", {**SITES, "rferl.org": [["goed", "x"]]},
                            bc.GEEN_TOEGANG) == "rferl.org"


def test_the_question_searches_once_and_only_on_that_site():
    params = bc.herkomstverzoek(BERICHT, "bbc.com", "herkomst-v1", _config())
    zoek = params["tools"][0]
    assert zoek["type"] == "web_search_20250305" and zoek["max_uses"] == 1 and zoek["allowed_domains"] == ["bbc.com"]
    assert params["model"] == _config().berichtcontrole.model_id and BERICHT in params["messages"][0]["content"]
    with pytest.raises(bc.VersieFout):
        bc.herkomstverzoek(BERICHT, "bbc.com", "herkomst-v9", _config())


def test_v2_does_not_count_an_edited_headline_with_the_same_facts():
    v1 = bc.herkomstverzoek(BERICHT, "bbc.com", "herkomst-v1", _config())["messages"][0]["content"]
    v2 = bc.herkomstverzoek(BERICHT, "bbc.com", "herkomst-v2", _config())["messages"][0]["content"]
    assert "edit a headline after publication" in v2 and "edit a headline" not in v1
    assert v2.replace(bc.KOPREGEL, "") == v1 and BERICHT in v2 and "bbc.com" in v2


def test_the_answer_is_read_from_its_last_json_line_and_anything_else_is_no_outcome():
    h = bc.lees_herkomst(_blokken("anders", [{"soort": "inhoud", "woorden": "12 March", "juist": "21 March"}],
                                  ["Police detained four people on 21 March."]))
    assert h["uitkomst"] == "anders" and h["verschillen"][0]["juist"] == "21 March"
    assert h["passages"] == [{"soort": "web", "url": "https://www.bbc.com/news/world-1",
                              "citaat": "Police detained four people on 21 March."}]
    assert bc.lees_herkomst([{"type": "text", "text": "No JSON here."}])["uitkomst"] is None
    assert bc.lees_herkomst([{"type": "text", "text": '{"uitkomst": "misschien"}'}])["uitkomst"] is None
    raar = bc.lees_herkomst(_blokken("anders", [{"soort": "kleur", "woorden": "a", "juist": "b"}]))
    assert raar["uitkomst"] == "anders" and raar["verschillen"] == []


def _na(oordeel="klopt", kleur="groen"):
    return {"oordeel": oordeel, "stand": {"stand": 7 if kleur == "groen" else 3, "woorden": "x", "laag": "web"},
            "feit": None, "kleur": kleur, "regels": [], "meting": None}


WEB = [{"soort": "web", "url": "https://www.bbc.com/a", "citaat": "Four were detained in Brussels."}]


def test_a_changed_fact_that_the_site_states_otherwise_makes_it_red_with_the_real_article():
    h = bc.lees_herkomst(_blokken("anders", [{"soort": "inhoud", "woorden": "12 March", "juist": "21 March"}],
                                  ["Police detained four people on 21 March."]))
    uit = bc.met_herkomst(TABEL, _na(), BERICHT, h, WEB)
    assert uit["oordeel"] == "klopt niet" and uit["kleur"] == "rood" and "vervalst artikel" in uit["regels"]
    c = uit["correcties"][0]
    assert BERICHT[c["begin"]:c["eind"]] == "12 March" and c["juist"] == "21 March"
    assert c["url"] == "https://www.bbc.com/news/world-1" and "21 March" in c["citaat"]


def test_a_difference_the_site_does_not_state_literally_is_never_red_but_never_green_either():
    h = bc.lees_herkomst(_blokken("anders", [{"soort": "inhoud", "woorden": "12 March", "juist": "21 March"}],
                                  ["Police detained four people last week."]))
    uit = bc.met_herkomst(TABEL, _na(), BERICHT, h, WEB)
    assert uit["oordeel"] == "onzeker" and uit["kleur"] is None and "andere herkomst" in uit["regels"]


def test_not_found_or_another_author_takes_away_green_and_leaves_red():
    niet = bc.lees_herkomst(_blokken("niet gevonden", url=""))
    uit = bc.met_herkomst(TABEL, _na(), BERICHT, niet, WEB)
    assert uit["oordeel"] == "onzeker" and uit["kleur"] is None and uit["regels"] == ["herkomst niet gevonden"]
    rood = bc.met_herkomst(TABEL, _na("klopt niet", "rood"), BERICHT, niet, WEB)
    assert rood["kleur"] == "rood" and rood["oordeel"] == "klopt niet" and rood["regels"] == ["herkomst niet gevonden"]
    schrijver = bc.lees_herkomst(_blokken("anders", [{"soort": "herkomst", "woorden": "By Tobias Wren",
                                                      "juist": "By Jessica Parker"}], ["By Jessica Parker"]))
    uit = bc.met_herkomst(TABEL, _na(), BERICHT, schrijver, WEB)
    assert uit["kleur"] is None and "andere herkomst" in uit["regels"] and "correcties" not in uit


def test_the_same_article_or_no_readable_answer_changes_nothing():
    for h in (bc.lees_herkomst(_blokken("gelijk", citaten=["Four people were detained by police."])),
              bc.lees_herkomst([{"type": "text", "text": "kapot"}])):
        assert bc.met_herkomst(TABEL, _na(), BERICHT, h, WEB) == _na()


class _Nep:
    """De machine zegt *klopt* met een bron; de herkomstvraag antwoordt met `herkomst`."""

    def __init__(self, herkomst):
        self.herkomst, self.verzoeken, self.messages = herkomst, [], self

    def create(self, **params):
        self.verzoeken.append(params)
        tools = params.get("tools") or []
        if tools and tools[0].get("allowed_domains"):
            return _Antwoord(self.herkomst)
        return _Antwoord([{"type": "text", "text": "BEWERING: x\nOORDEEL: klopt\nUITLEG: y",
                           "citations": [{"type": "web_search_result_location", "url": "https://www.bbc.com/a",
                                          "cited_text": "Four were detained in Brussels.", "title": "BBC"}]}])


class _Blok:
    def __init__(self, d):
        self.__dict__.update(d)
        self._d = d

    def model_dump(self):
        return dict(self._d)


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 1000, 200, 0, 0
    server_tool_use = type("S", (), {"web_search_requests": 1})()


class _Antwoord:
    def __init__(self, blokken):
        self.content = [_Blok(b) for b in blokken]
        self.usage, self.stop_reason = _Gebruik(), "end_turn"


RFERL = BERICHT.replace("https://www.bbc.com/news BBC", "https://www.rferl.org/news RFERL")


def _beoordeel(nep, config, monkeypatch):
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": {**SITES, "rferl.org": [["goed", "x"]]}})
    return bc.beoordeel(sqlite3.connect(":memory:"), {"tekst": RFERL, "geheugen": [], "kandidaten": []}, nep,
                        config, "2026-10-28", TABEL, {})


def test_the_check_asks_the_site_alongside_the_machine_and_applies_the_outcome(monkeypatch):
    nep = _Nep(_blokken("niet gevonden", url=""))
    uit = _beoordeel(nep, _config(), monkeypatch)
    assert any((p.get("tools") or [{}])[0].get("allowed_domains") == ["rferl.org"] for p in nep.verzoeken)
    assert uit["kleur"] is None and "herkomst niet gevonden" in uit["regels"]
    assert uit["versies"]["provenance"] == "herkomst-v1" and uit["herkomst"]["uitkomst"] == "niet gevonden"


def test_off_by_default_and_no_question_without_a_good_site(monkeypatch):
    assert load_config(None).berichtcontrole.herkomst == ""
    nep = _Nep(_blokken("niet gevonden", url=""))
    uit = _beoordeel(nep, _config(herkomst=""), monkeypatch)
    assert uit["kleur"] == "groen" and len(nep.verzoeken) == 1
    nep = _Nep(_blokken("niet gevonden", url=""))
    monkeypatch.setattr(bc, "herkomstlijst", lambda: {"sites": {}})
    uit = bc.beoordeel(sqlite3.connect(":memory:"), {"tekst": BERICHT, "geheugen": [], "kandidaten": []}, nep,
                       _config(), "2026-10-28", TABEL, {})
    assert uit["kleur"] == "groen" and len(nep.verzoeken) == 1


# --- de meting -----------------------------------------------------------------------------------

def _artikel(i, site):
    return {"id": f"b-{i:04d}", "sleutel": f"S:https://www.{site}/x/{i}", "tekst": f"Kop {i}\nBegin {i}.", "zaak": None}


def test_the_new_set_takes_good_sites_only_at_most_six_per_site_and_replaces_what_was_rejected():
    sites = {**SITES, **{f"site{k}.com": [["goed", "x"]] for k in range(20)}}
    artikelen = [_artikel(i, "bbc.com") for i in range(10)] + [_artikel(100 + i, "nypost.com") for i in range(5)] \
        + [_artikel(200 + 10 * k + i, f"site{k}.com") for i in range(8) for k in range(20)]
    andere = ["bbc.com", "dw.com", "kyivpost.com"]
    set_ = hk.kies_nieuw(artikelen, sites, andere)
    assert sum(s["sub"] == "A" for s in set_) == 40 and all(sum(s["sub"] == x for s in set_) == 10
                                                            for x in ("B-krant", "B-schrijver", "B-feit", "B-kop"))
    assert not any("nypost" in s["sleutel"] for s in set_)
    assert sum("bbc.com" in s["sleutel"] for s in set_) <= 6
    assert all(s["toon_domein"] != s["sleutel"].split("/")[2].removeprefix("www.") for s in set_ if s["sub"] == "B-krant")
    assert all(s["schrijver"] for s in set_ if s["sub"] == "B-schrijver") and all(s["helft"] == "nieuw" for s in set_)
    weg = next(s for s in set_ if s["sub"] == "B-feit")["bron_id"]
    opnieuw = hk.kies_nieuw(artikelen, sites, andere, {weg})
    assert weg not in {s["bron_id"] for s in opnieuw} and sum(s["sub"] == "B-feit" for s in opnieuw) == 10
    assert [s["id"] for s in opnieuw if s["sub"] == "A"] == [s["id"] for s in set_ if s["sub"] == "A"]


def _stuk(i, sub):
    echt = sub == "A"
    return {"id": f"{sub}:{i}", "sub": sub, "verwacht": {"inhoud": "waar" if echt or sub in ("B-krant", "B-schrijver")
                                                         else "onwaar", "herkomst": "echt" if echt else "vals"}}


def _u(uitkomst, rood=False, inhoud=False):
    return {"uitkomst": uitkomst, "rood": rood, "inhoud": inhoud}


def test_the_count_needs_every_loss_miss_and_detail_read_and_applies_the_four_requirements():
    stukken = [_stuk(i, "A") for i in range(20)] + [_stuk(i, "B-feit") for i in range(10)] + [_stuk(99, "B-kop")]
    antw = {f"A:{i}": _u("gelijk") for i in range(19)} | {"A:19": _u("niet gevonden")}
    antw |= {f"B-feit:{i}": _u("anders", rood=True, inhoud=True) for i in range(8)}
    antw |= {"B-feit:8": _u("gelijk"), "B-feit:9": _u("niet gevonden")}  # B-kop:99 loopt niet
    labels = {("A:19", "verlies"): "niet op de site", ("B-feit:8", "gemist"): "stap fout"}
    labels |= {(f"B-feit:{i}", "detail"): "juist" for i in range(8)}
    with pytest.raises(hk.Weigering):
        hk.telling(stukken, antw, {k: v for k, v in labels.items() if k[1] != "detail"}, [3.0] * 10)
    t = hk.telling(stukken, antw, labels, [3.0] * 9 + [12.0])
    assert t["echt"] == {"n": 20, "rood": 0, "kwijt": 1} and t["vals"] == {"n": 10, "niet groen": 9}
    assert t["loopt niet"] == {"B-kop": 1}
    assert t["eisen"] == {"geen echt artikel rood": True, "hoogstens 10% van de echte artikelen kwijt": True,
                          "minstens 70% van de vervalsingen niet groen": True,
                          "het veranderde detail juist in minstens 80%": True, "p95 hoogstens 10 s": False}
    rood = hk.telling(stukken, {**antw, "A:0": _u("anders", rood=True, inhoud=True)},
                      {**labels, ("A:0", "verlies"): "ocr"}, [3.0] * 10)
    assert rood["eisen"]["geen echt artikel rood"] is False and rood["eisen"]["p95 hoogstens 10 s"] is True
