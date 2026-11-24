"""Een getal in de uitleg alleen als de aangewezen bron het noemt (`lezer-v16`, PLAN #32.56, BENCHMARK §241; PO 2026-11-07:
"yes"): de meest voorkomende fout van v15 was een datum uit eigen kennis in een zin die wel een bronnummer had."""

import json

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc

RES = [{"nr": 1, "url": "https://www.bbc.com/a", "titel": "Train derails in Germany on 24 January 2011", "site": "bbc.com",
        "soort": "overig", "band": "goed", "fragment": "Three people died; damage of $1,776,000.", "factcheck": False,
        "staatsmedia": None},
       {"nr": 2, "url": "https://www.dw.com/b", "titel": "Rail crash", "site": "dw.com", "soort": "overig", "band": "goed",
        "fragment": "The train carried 3.5 thousand passengers in 2010.", "factcheck": False, "staatsmedia": None}]
CHECKS = [{"redactie": "Snopes", "url": "https://snopes.com/x", "tekst": "Video shows 2019 floods", "oordeel": "onwaar",
           "datum": "2026-01-05"}]


def test_v16_is_v15_with_the_number_rule_and_one_more_line_in_the_question():
    v15, v16 = zc.LEZERS["lezer-v15"], zc.LEZERS["lezer-v16"]
    assert v16["getallen"] is True and "only if the result you cite states it" in v16["vraag"]
    assert {k: v for k, v in v16.items() if k not in ("vraag", "getallen")} == {
        k: v for k, v in v15.items() if k != "vraag"}
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v16"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v15"})


def test_a_number_its_own_source_does_not_state_drops_the_sentence():
    uitleg = ("Het ongeluk gebeurde op 24 januari 2011 [1]. Het gebeurde op 25 januari 2011 [1]. "
              "In 2010 vervoerde de trein 3,5 duizend reizigers [2]. De schade was 1.776.000 dollar [1].")
    assert zc.met_bronnen(uitleg, RES, CHECKS, getallen=True) == (
        "Het ongeluk gebeurde op 24 januari 2011 [1]. In 2010 vervoerde de trein 3,5 duizend reizigers [2]. "
        "De schade was 1.776.000 dollar [1].")


def test_a_number_counts_only_from_the_sources_the_sentence_cites():
    assert zc.met_bronnen("In 2010 ontspoorde de trein [1].", RES, CHECKS, getallen=True) == ""
    assert zc.met_bronnen("In 2010 ontspoorde de trein [1][2].", RES, CHECKS, getallen=True) == (
        "In 2010 ontspoorde de trein [1][2].")


def test_a_check_carries_its_own_date_and_text_and_the_message_its_own_numbers():
    assert zc.met_bronnen("Snopes beoordeelde dit op 5 januari 2026 [D1].", RES, CHECKS, getallen=True) == (
        "Snopes beoordeelde dit op 5 januari 2026 [D1].")
    assert zc.met_bronnen("De video toont de overstroming van 2019 [D1].", RES, CHECKS, getallen=True) == (
        "De video toont de overstroming van 2019 [D1].")
    zin = "Het bericht noemt 65% armoede, maar geen bron zegt dat [1]."
    assert zc.met_bronnen(zin, RES, CHECKS, getallen=True) == ""
    assert zc.met_bronnen(zin, RES, CHECKS, bericht="65% of people live in poverty", getallen=True) == zin


def test_without_the_rule_v15_keeps_the_sentence():
    assert zc.met_bronnen("Het gebeurde op 25 januari 2011 [1].", RES, CHECKS) == "Het gebeurde op 25 januari 2011 [1]."


def _oordeel(uitleg):
    return {"oordeel": "klopt", "steunt": [1], "spreekt_tegen": [], "uitleg": uitleg, "over_beeld": False, "checks": [],
            "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0}, "zou_gemeld": True}


def test_na_lezen_applies_the_rule_for_v16_with_the_message_and_not_for_v15():
    bericht = "Train derails in Germany, 65 injured"
    uitleg = "Dit klopt: de trein ontspoorde op 24 januari 2011 [1]. Er waren 65 gewonden [1]. Het was op 26 januari [1]."
    def lees(lezer):
        return zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel(uitleg))), bericht, RES, [], lezer, False, gezocht=True,
                           jaar=2026)["uitleg"]
    assert lees("lezer-v16") == "Dit klopt: de trein ontspoorde op 24 januari 2011 [1]. Er waren 65 gewonden [1]."
    assert lees("lezer-v15").endswith("Het was op 26 januari [1].")


def test_the_row_keeps_the_raw_explanation_when_given():
    uit = {"oordeel": "klopt", "kleur": "groen", "uitkomst": "klopt", "bronnen": [], "uitleg": "kort"}
    item = {"id": "W:1", "set": "W"}
    assert mt._rij(item, "C", uit, 0.0, [], "v", {}, ruw="lang en kort")["uitleg_ruw"] == "lang en kort"
    assert "uitleg_ruw" not in mt._rij(item, "C", uit, 0.0, [], "v")
