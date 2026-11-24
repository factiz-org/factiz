"""Een uitleg die alleen zegt wat de bronnen zeggen (`lezer-v15`, PLAN #32.56, BENCHMARK §240; PO 2026-11-07: "ja graag"): elke
zin met het nummer van zijn bron, de code laat weg wat geen bron heeft of een medium noemt dat er niet in staat, en bij B61
telt het bericht zelf niet als die ene goede bron."""

import json

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc

RES = [{"nr": 1, "url": "https://www.bbc.com/a", "titel": "Train derails in Germany", "site": "bbc.com", "soort": "overig",
        "band": "goed", "fragment": "Three people died when a train derailed.", "factcheck": False, "staatsmedia": None},
       {"nr": 2, "url": "https://news.yahoo.com/b", "titel": "Germany train crash kills three | Reuters", "site": "yahoo.com",
        "soort": "overig", "band": "goed", "fragment": "Reuters reports a landslide.", "factcheck": False,
        "staatsmedia": None}]
CHECKS = [{"redactie": "Snopes", "url": "https://snopes.com/x", "tekst": "c", "oordeel": "onwaar", "datum": "2026-01-01"}]


def test_v15_asks_for_the_number_of_a_source_behind_every_sentence():
    v14, v15 = zc.LEZERS["lezer-v14"], zc.LEZERS["lezer-v15"]
    assert "[n]" in v15["vraag"] and "[D1]" in v15["vraag"] and "only outlets" in v15["vraag"]
    assert {k: v for k, v in v15.items() if k not in ("vraag", "met_bronnen", "eigen_niet")} == {
        k: v for k, v in v14.items() if k != "vraag"}
    assert v15["met_bronnen"] is True and v15["eigen_niet"] is True
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v15"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v14"})


def test_only_sentences_with_a_valid_source_number_stay():
    uitleg = ("Dit klopt: drie mensen kwamen om bij een treinongeluk [1].\n\n"
              "Reuters meldt een aardverschuiving als oorzaak [2]. De trein vervoerde 100 mensen. "
              "Snopes noemde een eerder bericht onwaar [D1]. Volgens bron [7] reed de trein te hard.")
    assert zc.met_bronnen(uitleg, RES, CHECKS) == ("Dit klopt: drie mensen kwamen om bij een treinongeluk [1].\n\n"
                                                   "Reuters meldt een aardverschuiving als oorzaak [2]. "
                                                   "Snopes noemde een eerder bericht onwaar [D1].")


def test_a_sentence_that_names_an_outlet_its_sources_do_not_carry_is_dropped_but_via_a_wire_stays():
    uitleg = "Newsweek meldt drie doden [1]. Reuters meldt een aardverschuiving [2]. De BBC meldt drie doden [1]."
    assert zc.met_bronnen(uitleg, RES, []) == "Reuters meldt een aardverschuiving [2]. De BBC meldt drie doden [1]."


def test_a_bare_verdict_may_stand_without_a_number_and_nothing_left_means_no_explanation():
    assert zc.met_bronnen("Dit klopt niet. De video is oud [1].", RES, []) == "Dit klopt niet. De video is oud [1]."
    assert zc.met_bronnen("De trein reed te hard.", RES, []) == ""


def _oordeel(uitleg="Dit klopt: het gebeurde [1]. Het was op dinsdag."):
    return {"oordeel": "klopt", "steunt": [1], "spreekt_tegen": [], "uitleg": uitleg, "over_beeld": False, "checks": [],
            "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0}, "zou_gemeld": True}


def test_v15_cleans_the_explanation_and_v14_does_not():
    bericht = "Train derails in Germany after landslide"
    v15 = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), bericht, RES, [], "lezer-v15", False, gezocht=True, jaar=2026)
    v14 = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), bericht, RES, [], "lezer-v14", False, gezocht=True, jaar=2026)
    assert v15["uitleg"] == "Dit klopt: het gebeurde [1]." and v14["uitleg"].endswith("dinsdag.")


def test_b61_does_not_count_the_message_itself_as_its_one_good_source():
    zelf = [{**RES[0], "titel": "Train derails in Germany after landslide - Wikinews"}]
    bericht = "Train derails in Germany after landslide Monday, July 28, 2025 A regional train derailed"
    def kleur(lezer, res):
        return zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), bericht, res, [], lezer, False, gezocht=True,
                           jaar=2026)["kleur"]
    assert kleur("lezer-v14", zelf) == "groen" and kleur("lezer-v15", zelf) is None
    assert kleur("lezer-v15", [{**RES[0], "titel": "German rail accident: three dead"}]) == "groen"


def test_a_number_after_the_full_stop_belongs_to_its_own_sentence_and_does_not_carry_the_next():
    """Het model zet het nummer vaak ná de punt ("... oud. [4]"); dan hoort het bij die zin, en de volgende zin zonder
    nummer valt weg (§241: 7 van de 994 zinnen bleven anders staan)."""
    assert zc.zinnen("Dit klopt niet. [4] De foto is oud. [1][2] Het was in 2019.") == [
        "Dit klopt niet [4].", "De foto is oud [1][2].", "Het was in 2019."]
    uitleg = "De trein ontspoorde. [1] Er waren 100 passagiers. Snopes noemde het onwaar. [D1]"
    assert zc.met_bronnen(uitleg, RES, CHECKS) == "De trein ontspoorde [1]. Snopes noemde het onwaar [D1]."
