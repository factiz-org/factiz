"""Meteen de kern, en een echte kop klopt (`lezer-v13`, PLAN #32.51, BENCHMARK §236, B60; PO 2026-11-07: "Wat Gemini goed
doet, is gelijk naar de kern gaan, terwijl wij altijd in onze eerste zin iets herhalen wat mensen al zelf kunnen zien";
"Ja, B60")."""

import json

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc

KOP = "NPR\nThe economy propelled Democrats to victory. What can they actually do about it?"
TITEL = "The economy propelled Democrats to victory. What can they actually do about it? : NPR"


def test_v13_begins_with_the_verdict_and_the_core_and_never_restates_the_message():
    v12, v13 = zc.LEZERS["lezer-v12"], zc.LEZERS["lezer-v13"]
    assert "Begin with the verdict and the core fact" in v13["vraag"] and "never begin by restating" in v13["vraag"]
    assert "empty line" in v13["vraag"] and "Do not mention our database" in v13["vraag"]
    assert "Begin with the verdict" not in v12["vraag"]
    assert {k: v for k, v in v13.items() if k in v12 and k != "vraag"} == {k: v for k, v in v12.items() if k != "vraag"}
    assert v13["kop_klopt"] is True and v13["zonder_database"] is True
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v13"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v12"})


def test_our_database_leaves_the_explanation_but_a_database_in_the_news_stays():
    assert zc.zonder_database("Full Fact (database-check van 2026-10-09) beoordeelde dit als onwaar: de video is oud.") \
        == "Full Fact beoordeelde dit als onwaar: de video is oud."
    assert zc.zonder_database("Casten daagt Waters uit. De factchecks uit de database gaan over andere beweringen.") \
        == "Casten daagt Waters uit."
    assert zc.zonder_database("Full Fact (ook in de database, 2026-10-27), AFP en Reuters melden dat het AI is.") \
        == "Full Fact, AFP en Reuters melden dat het AI is."
    nieuws = "De cijfers komen uit een militaire database van het Amerikaanse ministerie van Defensie."
    assert zc.zonder_database(nieuws) == nieuws
    assert zc.zonder_database("Dit klopt niet: de video is oud.\n\nDe factcheck in onze database gaat over iets anders. "
                              "AFP vond de bron.") == "Dit klopt niet: de video is oud.\n\nAFP vond de bron."


def _oordeel(oordeel="geen bewering", steunt=(), tegen=(), vorm="zelf", uitleg="Dit is een kop van NPR."):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": uitleg,
            "over_beeld": False, "checks": [], "vorm": vorm, "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": False}


def _res(*bronnen):
    return [{"nr": i, "url": f"https://www.{site}/a{i}", "titel": titel, "site": site, "soort": "overig", "band": band,
             "fragment": "f", "factcheck": False, "staatsmedia": None}
            for i, (site, band, titel) in enumerate(bronnen, 1)]


def _na(lezer, antwoord=None, bericht=KOP, res=None):
    res = res if res is not None else _res(("cbsnews.com", "goed", "Economy was top issue"), ("npr.org", "goed", TITEL))
    return zc.na_lezen(zc.lees_oordeel(json.dumps(antwoord or _oordeel())), bericht, res, [], lezer, False,
                       gezocht=True, jaar=2026)


def test_b60_a_real_headline_on_the_own_site_of_the_named_outlet_is_true_and_green_with_that_page_as_source():
    uit = _na("lezer-v13")
    assert (uit["kleur"], uit["uitkomst"]) == ("groen", "klopt")
    assert [(b["site"], b["rol"]) for b in uit["bronnen"]] == [("npr.org", "bevestigt de kop")]
    assert (_na("lezer-v12")["kleur"], _na("lezer-v12")["uitkomst"]) == (None, "geen bewering")


def test_b60_never_without_the_own_site_the_name_enough_words_or_with_a_contradiction():
    titel = TITEL
    gevallen = [
        dict(res=_res(("cbsnews.com", "goed", titel))),                     # niet de site van NPR
        dict(res=_res(("npr.org", None, titel))),                           # geen band goed
        dict(res=_res(("npr.org", "goed", "Democrats win the House"))),     # een andere kop
        dict(bericht="The economy propelled Democrats to victory. What can they actually do about it?"),  # geen medium
        dict(bericht="NPR\nDemocrats win"),                                  # te kort
        dict(antwoord=_oordeel(tegen=(1,))),                                 # iets spreekt het tegen
        dict(antwoord=_oordeel(vorm="over een bewering")),                   # over een bewering van een ander
        dict(antwoord=_oordeel("satire")),
    ]
    for g in gevallen:
        uit = _na("lezer-v13", **g)
        assert uit["kleur"] is None and uit["uitkomst"] != "klopt", g


def test_v13_cleans_our_database_out_of_the_explanation_and_v12_does_not():
    zin = "Dit klopt: de kop staat op npr.org. De factchecks uit de database gaan over iets anders."
    assert _na("lezer-v13", _oordeel(uitleg=zin))["uitleg"] == "Dit klopt: de kop staat op npr.org."
    assert _na("lezer-v12", _oordeel(uitleg=zin))["uitleg"] == zin


def test_the_headline_rule_of_v11_still_only_needs_a_confirming_source():
    assert zc.eigen_kop(KOP, _res(("npr.org", "goed", TITEL))) is True
    assert zc.kop_treffers(KOP, _res(("cbsnews.com", "goed", TITEL), ("npr.org", "goed", TITEL)))[0]["site"] == "npr.org"
