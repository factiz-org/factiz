"""*Niet bevestigd* niet bij oud nieuws en niet bij een onafhankelijke bevestiging zonder band (`lezer-v10`, PLAN
#32.43, PO 2026-11-06): dezelfde vraag aan het model als v9, de twee regels van §223 pas na het lezen. De regels maken
van *niet bevestigd* alleen weer *onzeker*, en het antwoord zegt welke regel het deed."""

import dataclasses
import json
import sqlite3

from doublecheck import meting as mt
from doublecheck import narekening as nr
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config

BERICHT = "Salzburg, 20.08.2005: Brücke über die Salzach eingestürzt, zwei Tote."
NIEUW = "Am 3. November 2026 stürzte in Salzburg eine Brücke ein."


def _oordeel(oordeel="onzeker", steunt=(), tegen=(), zou_gemeld=True):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Uitleg.",
            "over_beeld": False, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": zou_gemeld}


def _res(*bronnen):
    """Zoekresultaten met de velden van `resultaten_uit`; per bron (site, band, soort, staatsmedia)."""
    return [{"nr": i, "url": f"https://{site}/a", "titel": "t", "site": site, "soort": soort, "band": band,
             "fragment": "f", "factcheck": False, "staatsmedia": staat}
            for i, (site, band, soort, staat) in enumerate(bronnen, 1)]


def _na(lezer, bericht=BERICHT, res=(), antwoord=None, jaar=2026):
    antwoord = antwoord or _oordeel()
    return zc.na_lezen(zc.lees_oordeel(json.dumps(antwoord)), bericht, list(res) or _res(("blog.example", "laag",
                                                                                           "overig", None)),
                       [], lezer, False, gezocht=True, jaar=jaar)


def test_v10_asks_the_model_exactly_what_v9_asks():
    v9, v10 = zc.LEZERS["lezer-v9"], zc.LEZERS["lezer-v10"]
    assert {k: v for k, v in v10.items() if k != "uitzonderingen"} == v9
    assert v10["uitzonderingen"] == ("oud jaartal", "zonder band")


def test_the_fingerprint_of_v10_carries_its_rules_and_v9_keeps_its_own():
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v10"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v9"})


def test_a_message_whose_newest_year_is_three_years_back_is_old():
    assert zc.oud_jaartal(BERICHT, 2026)
    assert zc.oud_jaartal("Elecciones de 2019 y 2023", 2026)
    assert not zc.oud_jaartal("Gab es 2016 164.000, sind es 2024 ganze 188.000", 2026)
    assert not zc.oud_jaartal("Geen jaartal, dus de waarschuwing blijft", 2026)
    assert not zc.oud_jaartal("Bestelnummer 12023 en 20230", 2026)
    assert zc.oud_jaartal("Wahl 2024", 2027) and not zc.oud_jaartal("Wahl 2024", 2026)


def test_doubt_never_loosens_a_future_year_or_an_unknown_day_keeps_the_warning():
    assert not zc.oud_jaartal("Seit 2019 geplant, fertig bis 2030", 2026)
    assert not zc.oud_jaartal(BERICHT, None)


def test_the_year_rule_is_the_measured_rule_and_only_stricter_from_2030():
    for tekst in (BERICHT, NIEUW, "Elecciones de 2019 y 2023", "Bestelnummer 12023", "Sem ano", "1999 e 2003",
                  "Em 2024 e 2025"):
        assert zc.oud_jaartal(tekst, 2026) == nr.oud_volgens_tekst({"tekst": tekst}), tekst
    assert nr.oud_volgens_tekst({"tekst": "Seit 2019 geplant, fertig bis 2030"})


def test_an_unbanded_confirmation_counts_unless_platform_state_media_banded_or_contradicting():
    STAAT = {"domeinen": {"rt.com": {"naam": "RT"}}}
    gevallen = [("terra.com.br", None, "overig", None, True), ("x.com", None, "platform", None, False),
                ("rt.com", None, "overig", "RT", False), ("blog.net", "laag", "overig", None, False),
                ("a.pt", "wisselend", "overig", None, False), ("bbc.com", "goed", "overig", None, False)]
    for site, band, soort, staat, verwacht in gevallen:
        bron = {"url": f"https://{site}/a", "site": site, "band": band, "soort": soort, "staatsmedia": staat,
                "rol": "bevestigt"}
        assert zc.bevestigd_zonder_band([bron]) is verwacht, site
        assert nr.bevestigd_zonder_band({"bronnen": [bron]}, STAAT) is verwacht, site
    tegen = {"url": "https://terra.com.br/a", "site": "terra.com.br", "band": None, "soort": "overig",
             "rol": "spreekt tegen"}
    assert not zc.bevestigd_zonder_band([tegen])


def test_an_old_year_turns_not_confirmed_into_unsure_and_says_why():
    v9, v10 = _na("lezer-v9"), _na("lezer-v10")
    assert v9["uitkomst"] == "niet bevestigd" and v9["onbevestigd_weg"] is None
    assert v10["uitkomst"] == "onzeker" and v10["onbevestigd_weg"] == "oud jaartal"
    assert _na("lezer-v10", NIEUW)["uitkomst"] == "niet bevestigd"


def test_an_unbanded_independent_source_that_confirms_turns_not_confirmed_into_unsure():
    res = _res(("terra.com.br", None, "overig", None))
    uit = _na("lezer-v10", NIEUW, res, _oordeel(steunt=(1,)))
    assert uit["uitkomst"] == "onzeker" and uit["onbevestigd_weg"] == "zonder band"
    for bron in (("x.com", None, "platform", None), ("rt.com", None, "overig", "RT"),
                 ("blog.net", "laag", "overig", None)):
        assert _na("lezer-v10", NIEUW, _res(bron), _oordeel(steunt=(1,)))["uitkomst"] == "niet bevestigd", bron
    assert _na("lezer-v10", NIEUW, res, _oordeel(steunt=(1,), tegen=(1,)))["uitkomst"] == "niet bevestigd"
    assert _na("lezer-v10", NIEUW, res, _oordeel())["uitkomst"] == "niet bevestigd"


def test_the_rules_change_nothing_but_not_confirmed():
    for antwoord, bericht in ((_oordeel(), BERICHT), (_oordeel("klopt niet", tegen=(1,)), BERICHT),
                              (_oordeel("geen bewering"), BERICHT), (_oordeel(zou_gemeld=False), BERICHT),
                              (_oordeel(steunt=(1,)), NIEUW)):
        res = _res(("bbc.com", "goed", "overig", None), ("terra.com.br", None, "overig", None))
        v9, v10 = _na("lezer-v9", bericht, res, antwoord), _na("lezer-v10", bericht, res, antwoord)
        verschil = {k for k in v9 if v9[k] != v10[k]}
        assert verschil <= {"uitkomst", "onbevestigd_weg"}
        if verschil:
            assert (v9["uitkomst"], v10["uitkomst"]) == ("niet bevestigd", "onzeker")


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class _Model:
    def __init__(self, *antwoorden):
        self.antwoorden, self.messages = list(antwoorden), self

    def create(self, **_):
        a = type("A", (), {})()
        a.content, a.usage, a.stop_reason = [_Blok(json.dumps(self.antwoorden.pop(0)))], _Gebruik(), "end_turn"
        return a


def test_the_check_takes_the_year_from_the_day_of_the_check():
    config = load_config()
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(
        config.berichtcontrole, lezer="lezer-v10", speurvraag_model="claude-haiku-5-5"))
    zoek = lambda q: {"web": {"results": [{"url": "https://blog.example/x", "title": "t", "description": "d"}]}}  # noqa: E731

    def controle(dag):
        model = _Model({"verder_zoeken": [{"soort": "echt nieuws", "vraag": "Salzburg Brücke", "site": ""}]},
                       _oordeel())
        return zc.controleer(sqlite3.connect(":memory:"), "Wahl 2023: Ergebnis gefälscht", config, model, zoek,
                             lambda t: None, {}, dag, zoek_checks=lambda t: [])

    assert controle("2026-11-06")["uitkomst"] == "onzeker"
    assert controle("2025-11-06")["uitkomst"] == "niet bevestigd"
    assert controle("2026-11-06")["versies"]["reader"] == "lezer-v10"


def test_a_run_keeps_why_a_message_lost_not_confirmed_and_can_count_it():
    plan = {"onwaar": ["O"], "waar": ["W"], "eisen": [
        {"naam": "O: hoogstens 1 keer niet bevestigd weg", "tel": {"arm": "C", "sets": ["O"], "weg": True},
         "op": "<=", "waarde": 1}]}
    item = {"id": "o1", "set": "O"}
    rij = mt._rij(item, "C", {"oordeel": "onzeker", "kleur": None, "uitkomst": "onzeker", "bronnen": [],
                              "onbevestigd_weg": "oud jaartal"}, 0.02, [], "abc")
    assert rij["onbevestigd_weg"] == "oud jaartal"
    rijen = [rij, {**rij, "id": "o2", "onbevestigd_weg": None}, {**rij, "id": "o3", "onbevestigd_weg": "zonder band"}]
    uit = mt.telling(rijen, {}, plan, {r["id"]: {"id": r["id"]} for r in rijen})
    assert uit["eisen"]["O: hoogstens 1 keer niet bevestigd weg"] == {"waarde": 2, "gehaald": False}
    assert uit["per set"]["O C"]["niet bevestigd weg: oud jaartal"] == 1
    assert uit["per set"]["O C"]["niet bevestigd weg: zonder band"] == 1
