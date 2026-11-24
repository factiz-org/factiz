"""De routine per week voor een nieuwe uitgave (PLAN #35.2; PO 2026-11-17: "Ok, nee dan is wekelijkse verversen prima",
"Yes, build it"): wanneer ze begint, wat nieuw is, de stappen die hervatten en nooit twee keer betalen, de grens per
week, en de melding aan de PO. Live gaat een uitgave alleen met een ja van de PO; de routine rolt nooit zelf uit."""

from __future__ import annotations

import json

import pytest

from doublecheck import verversen as vv

LOG = """2026-11-09T03:17:05+00:00 nieuwe stand feed-2026-11-09T030636.json
2026-11-16T03:17:02+00:00 nieuwe stand feed-2026-11-15T081042.json
2026-11-17T14:52:09+00:00 inhalen met de hand uit feed-2026-11-15T081042.json (PLAN #35.1)
2026-11-17T15:27:40+00:00 database bijgewerkt uit feed-2026-11-15T081042.json: uitgang 0
2026-11-18T04:17:00+00:00 geen nieuwe versie (etag)
"""


def test_the_routine_starts_from_the_last_feed_the_lab_was_updated_from_without_error():
    assert vv.laatste_bijwerking(LOG) == "feed-2026-11-15T081042.json"
    mislukt = LOG + "2026-11-23T04:40:00+00:00 database bijgewerkt uit feed-2026-11-22T080000.json: uitgang 1\n"
    assert vv.laatste_bijwerking(mislukt) == "feed-2026-11-15T081042.json"
    assert vv.laatste_bijwerking("2026-11-18T04:17:00+00:00 geen nieuwe versie (etag)\n") is None


def test_a_feed_that_already_has_an_edition_starts_nothing_unless_asked():
    assert vv.moet_verversen("feed-2026-11-15T081042.json", {}) is True
    gedaan = {"feed": "feed-2026-11-15T081042.json", "release": "2026-11-18"}
    assert vv.moet_verversen("feed-2026-11-15T081042.json", gedaan) is False
    assert vv.moet_verversen("feed-2026-11-22T080000.json", gedaan) is True
    assert vv.moet_verversen(None, {}) is False
    assert vv.moet_verversen("feed-2026-11-15T081042.json", gedaan, toch=True) is True


def test_what_is_new_is_what_the_new_edition_has_and_the_live_one_not_and_what_left_is_named_too():
    nieuw, weg = vv.verschil({"a", "b", "c"}, {"b", "c", "d", "e"})
    assert nieuw == ["d", "e"] and weg == ["a"]


def test_the_steps_run_in_order_and_a_second_run_skips_what_is_done(tmp_path):
    gedaan = []

    def stap(naam, kosten=0.0):
        def f(stand):
            gedaan.append(naam)
            return {"kosten": kosten}
        return f

    stappen = {"bouwen": stap("bouwen"), "themas": stap("themas", 0.12), "herbouwen": stap("herbouwen")}
    pad = tmp_path / "stand.json"
    stand = vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    assert gedaan == ["bouwen", "themas", "herbouwen"] and set(stand["stappen"]) == set(stappen)
    vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    assert gedaan == ["bouwen", "themas", "herbouwen"]
    assert json.loads(pad.read_text())["kosten"] == pytest.approx(0.12)


def test_a_failed_step_stops_the_routine_and_the_next_run_resumes_there(tmp_path):
    keer = {"n": 0}

    def wankel(stand):
        keer["n"] += 1
        if keer["n"] == 1:
            raise vv.Weigering("de batch liep nog")
        return {"kosten": 0.5}

    pad = tmp_path / "stand.json"
    stappen = {"bouwen": lambda s: {}, "vertalingen": wankel, "herbouwen": lambda s: {}}
    with pytest.raises(vv.Weigering):
        vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    assert list(json.loads(pad.read_text())["stappen"]) == ["bouwen"]
    stand = vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    assert list(stand["stappen"]) == ["bouwen", "vertalingen", "herbouwen"] and keer["n"] == 2


def test_the_state_of_one_edition_is_never_used_for_another(tmp_path):
    pad = tmp_path / "stand.json"
    vv.voer_uit({"bouwen": lambda s: {}}, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    with pytest.raises(vv.Weigering):
        vv.voer_uit({"bouwen": lambda s: {}}, pad, release="2026-11-25", feed="feed-y", grens=5.0)


def test_the_week_stops_before_a_step_that_would_go_over_the_limit(tmp_path):
    pad = tmp_path / "stand.json"
    stappen = {"themas": lambda s: {"kosten": 4.0}, "vertalingen": lambda s: {"kosten": 3.0}}
    with pytest.raises(vv.Weigering, match="grens"):
        vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0,
                    schattingen={"vertalingen": 2.0})
    assert list(json.loads(pad.read_text())["stappen"]) == ["themas"]


def test_the_message_to_the_po_says_what_is_in_it_what_it_cost_and_how_to_go_live():
    stand = {"release": "2026-11-18", "feed": "feed-2026-11-15T081042.json", "kosten": 1.234,
             "stappen": {"bouwen": {"nieuw": 270, "weg": 3, "per_taal": {"en": 120, "hi": 80, "es": 70}},
                         "vertalingen": {"kosten": 1.1, "tekst": "270 beweringen in 14 talen"},
                         "namen": {"kosten": 0.13, "wacht": "200 nieuwe namen wachten op een lezing"},
                         "voorbereiden": {"nakijken": "in orde"}}}
    dekking = {"paginas": 270, "thema": 270, "land": 251, "namen": 160, "vertalingen": {"en": 140, "nl": 150, "es": 230}}
    tekst = vv.melding(stand, live="2026-11-16b", grens=10.0, dekking=dekking)
    for deel in ("2026-11-18", "270", "en 120", "hi 80", "$1.23", "$10.00", "200 nieuwe namen wachten op een lezing",
                 "python -m doublecheck.uitrol live 2026-11-18 --akkoord", "een thema: 270 van 270", "een land: 251 van 270",
                 "namen: 160 van 270", "es 230, nl 150, en 140", "vertalingen: $1.10", "PLAN #35.2a"):
        assert deel in tekst, deel
    assert "3 niet meer" in tekst and "2026-11-16b" in tekst
    # de tellingen van een stap zelf (over alle uitgaven) horen niet in wat de PO leest
    assert "270 beweringen in 14 talen" not in tekst


def test_the_routine_waits_while_the_lab_is_being_updated_from_a_new_feed():
    assert vv.lab_bezig(LOG) is False
    assert vv.lab_bezig(LOG + "2026-11-23T04:17:00+00:00 nieuwe stand feed-2026-11-22T080000.json\n") is True
    klaar = LOG + ("2026-11-23T04:17:00+00:00 nieuwe stand feed-2026-11-22T080000.json\n"
                   "2026-11-23T05:01:00+00:00 database bijgewerkt uit feed-2026-11-22T080000.json: uitgang 0\n")
    assert vv.lab_bezig(klaar) is False and vv.laatste_bijwerking(klaar) == "feed-2026-11-22T080000.json"


def test_run_up_to_a_step_stops_there_and_the_next_run_continues(tmp_path):
    gedaan = []
    stappen = {n: (lambda n: lambda s: gedaan.append(n) or {})(n) for n in ("bouwen", "themas", "herbouwen")}
    pad = tmp_path / "stand.json"
    vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0, tot="bouwen")
    assert gedaan == ["bouwen"]
    vv.voer_uit(stappen, pad, release="2026-11-18", feed="feed-x", grens=5.0)
    assert gedaan == ["bouwen", "themas", "herbouwen"]


def test_under_the_routine_a_step_checks_the_room_left_this_week_and_marks_its_batches(monkeypatch):
    from doublecheck import routinegrens as rg

    monkeypatch.delenv("FACTIZ_ROUTINE", raising=False)
    assert rg.uitgave() is None and rg.merk({"id": "b"}) == {"id": "b"} and not rg.past(0.01)
    monkeypatch.setenv("FACTIZ_ROUTINE", "2026-11-18")
    monkeypatch.setenv("FACTIZ_ROUTINE_RUIMTE", "2.50")
    assert rg.merk({"id": "b"}) == {"id": "b", "routine": "2026-11-18"}
    assert rg.past(2.0) and not rg.past(2.0, marge=1.3) and not rg.past(2.6)
    batches = [{"id": "a", "routine": "2026-11-18", "schatting": 0.4, "werkelijk": 0.31},
               {"id": "b", "routine": "2026-11-18", "schatting": 0.2, "werkelijk": None},
               {"id": "c", "routine": "2026-11-11", "schatting": 9.0, "werkelijk": 8.0},
               {"id": "d", "schatting": 3.0, "werkelijk": 2.0}]
    assert rg.kosten(batches, "2026-11-18") == (pytest.approx(0.51), 1)
    monkeypatch.setenv("FACTIZ_ROUTINE_RUIMTE", "geen getal")
    assert rg.ruimte() == 0.0


def test_the_three_batch_steps_use_the_limit_of_the_routine_and_mark_their_batches():
    """Thema's, namen (lezen en kiezen) en vertalingen: onder de routine haar ruimte, met de hand hun eigen grens."""
    from pathlib import Path

    for naam in ("themas", "namen", "weergave", "privepersonen", "relevantie", "waarom"):
        bron = (Path(vv.WORTEL) / "doublecheck" / f"{naam}.py").read_text(encoding="utf-8")
        assert "if rg.uitgave():" in bron and "rg.past(" in bron and "rg.merk(" in bron, naam
    for module, indienen, ophalen, pad in vv.BATCHSTAPPEN.values():
        assert indienen[-1].endswith("indienen") and ophalen[-1].endswith("ophalen"), module
        assert pad.name.endswith("batches.jsonl"), module


def test_euvsdisinfo_comes_into_the_lab_before_the_build_and_its_reasons_before_the_rebuild():
    """PLAN #35.3: de nieuwe gevallen van EUvsDisinfo (vanaf 2026) gaan het lab in voor `bouwen`, en hun punten van
    Waarom het niet klopt (eerst gelezen, dan de tweede lezing) komen voor `herbouwen`, zodat ze meegaan."""
    stappen = list(vv.maak_stappen("2026-11-24", 10.0, 1))
    assert stappen[:2] == ["euvsdisinfo", "bouwen"]
    assert stappen.index("bouwen") < stappen.index("waarom") < stappen.index("waarom-lezing") < stappen.index("herbouwen")
