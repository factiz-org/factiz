"""Een uitleg die helpt (`lezer-v12`, PLAN #32.49, BENCHMARK §235; PO 2026-11-07: "Gemini wint op de meeste punten omdat
Gemini simpelweg langere antwoorden geeft met meer context, en wij vaak erg kortaf zijn"): dezelfde oordelen als v11, een
uitleg van drie tot vijf feitelijke zinnen, en ook bij een check uit de database een uitleg."""

from types import SimpleNamespace

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc


def test_v12_asks_for_three_to_five_factual_sentences_instead_of_one():
    v11, v12 = zc.LEZERS["lezer-v11"], zc.LEZERS["lezer-v12"]
    assert "one short sentence" in v11["vraag"] and "one short sentence" not in v12["vraag"]
    assert "three to five" in v12["vraag"] and "what really happened" in v12["vraag"]
    assert "no judging words" in v12["vraag"]
    assert "Do not mention our database" in v12["vraag"]  # ruis voor de lezer (de proef van 2026-11-07)
    assert "concise" not in v12["systeem"]
    # alles wat niet over de uitleg gaat, blijft zoals in v11
    zelfde = {k: v for k, v in v11.items() if k not in ("systeem", "vraag")}
    assert {k: v for k, v in v12.items() if k in zelfde} == zelfde
    assert v12["uitleg_database"] is True and v12["max_tokens"] > 600
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v12"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v11"})


def test_v12_gets_room_for_the_longer_explanation_and_older_readers_keep_theirs():
    def cfg(lezer):
        return SimpleNamespace(berichtcontrole=SimpleNamespace(lezer=lezer, model_id="claude-sonnet-5-5", beeld=False))
    assert zc.leesverzoek("x", [], None, cfg("lezer-v12"), checks=[])["max_tokens"] == zc.LEZERS["lezer-v12"]["max_tokens"]
    assert zc.leesverzoek("x", [], None, cfg("lezer-v11"), checks=[])["max_tokens"] == 600


CHECK = {"soort": "check van een redactie", "url": "https://www.snopes.com/x", "redactie": "Snopes", "oordeel": "onwaar",
         "datum": "2026-10-01", "titel": None, "rol": "spreekt tegen"}


def _kring1(kleur="rood"):
    return zc.uit_kring1({"oordeel": "onwaar", "kleur": kleur, "bronnen": [CHECK]}, "bericht", {"reader": "lezer-v12"})


def _gelezen(oordeel="klopt niet", kleur="rood", uitkomst="klopt niet", uitleg="De video komt van een ander incident."):
    return {"route": "zoeken", "oordeel": oordeel, "kleur": kleur, "uitkomst": uitkomst, "uitleg": uitleg,
            "anders": "Het was een ander vliegtuig.", "kosten": 0.02,
            "bronnen": [{"url": "https://www.bbc.com/a", "site": "bbc.com", "rol": "spreekt tegen", "band": "goed"},
                        {**CHECK}]}


def test_a_database_answer_keeps_its_colour_and_gets_the_explanation_of_the_reader():
    uit = zc.met_uitleg(_kring1(), _gelezen())
    assert (uit["route"], uit["kleur"], uit["uitkomst"], uit["oordeel"]) == ("database", "rood", "klopt niet", "onwaar")
    assert uit["uitleg"] == "De video komt van een ander incident." and uit["anders"] == "Het was een ander vliegtuig."
    assert [b["url"] for b in uit["bronnen"]] == ["https://www.snopes.com/x", "https://www.bbc.com/a"]
    assert uit["kosten"] == 0.02


def test_a_reader_that_disagrees_with_the_check_never_explains_it_the_editors_sentence_stays():
    for gelezen in (_gelezen("klopt", "groen", "klopt", "Het klopt."), _gelezen("onzeker", None, "onzeker", "Onduidelijk.")):
        uit = zc.met_uitleg(_kring1(), gelezen)
        assert uit["kleur"] == "rood" and uit["uitleg"] == "Dit is al gecontroleerd: Snopes noemde het onwaar."
        assert uit["anders"] is None and uit["kosten"] == 0.02
    assert zc.met_uitleg(_kring1("oranje"), _gelezen("misleidend", "oranje", "misleidend"))["uitleg"].startswith("De video")
    assert zc.met_uitleg(_kring1("groen"), _gelezen("klopt", "groen", "klopt", "Het klopt."))["uitleg"] == "Het klopt."


def test_without_a_reading_the_database_answer_stays_as_it_was():
    uit = zc.met_uitleg(_kring1(), None)
    assert uit == {**_kring1(), "uitleg": "Dit is al gecontroleerd: Snopes noemde het onwaar."}


# --- de hele controle: een treffer in de database krijgt een lezing voor de uitleg ----------------------------------

import sqlite3  # noqa: E402

from tests.test_eenlezing import BERICHT, SITES, Reeks, _config, _oordeel, _zoek  # noqa: E402

KRING1 = {"oordeel": "onwaar", "kleur": "rood", "bronnen": [CHECK]}


def test_in_v12_a_database_hit_is_read_for_its_explanation_and_keeps_the_verdict_of_the_check():
    model = Reeks({"verder_zoeken": []}, {**_oordeel("klopt niet"), "uitleg": "Het was een ander incident."})
    kosten = sqlite3.connect(":memory:")
    uit = zc.controleer(kosten, BERICHT, _config(lezer="lezer-v12"), model, _zoek([]), lambda t: KRING1, SITES,
                        "2026-11-07", zoek_checks=lambda t: [])
    assert (uit["route"], uit["kleur"], uit["uitkomst"]) == ("database", "rood", "klopt niet")
    assert uit["uitleg"] == "Het was een ander incident." and len(model.verzoeken) == 2 and uit["kosten"] > 0


def test_in_v11_a_database_hit_still_answers_at_once_without_a_model():
    model = Reeks()
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v11"), model, _zoek([]),
                        lambda t: KRING1, SITES, "2026-11-07", zoek_checks=lambda t: [])
    assert uit["route"] == "database" and uit["uitleg"] is None and model.verzoeken == []


def test_when_the_reading_fails_the_database_answer_comes_anyway():
    def kapot(**_):
        raise RuntimeError("de lezer antwoordt niet")
    model = Reeks()
    model.create = kapot
    uit = zc.controleer(sqlite3.connect(":memory:"), BERICHT, _config(lezer="lezer-v12"), model, _zoek([]),
                        lambda t: KRING1, SITES, "2026-11-07", zoek_checks=lambda t: [])
    assert (uit["kleur"], uit["uitleg"]) == ("rood", "Dit is al gecontroleerd: Snopes noemde het onwaar.")


def test_the_fingerprint_of_v12_changes_when_the_rule_for_agreeing_with_the_check_changes(monkeypatch):
    arm = {"lezer": "lezer-v12", "speurvraag_model": "claude-haiku-5-5"}
    voor = mt.vingerafdruk(arm)
    monkeypatch.setattr(zc, "EENS_MET_CHECK", {**zc.EENS_MET_CHECK, "rood": ("klopt niet",)})
    assert mt.vingerafdruk(arm) != voor
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v11"}) == mt.vingerafdruk({**arm, "lezer": "lezer-v11"})
