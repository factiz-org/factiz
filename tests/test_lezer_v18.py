"""`lezer-v18` (PLAN #32.54; PO 2026-11-08: "Mag je ook doorvoeren"): v17 met een eerste zin van de uitleg die bij de
uitkomst past. Zegt de lezer *klopt* maar geven de regels geen kleur, dan begint de uitleg niet met "Dit klopt"."""

import json

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc

RES = [{"nr": 1, "url": "https://www.bbc.com/a", "titel": "Train derails in Germany", "site": "bbc.com", "soort": "overig",
        "band": "goed", "fragment": "Three people died when a train derailed.", "factcheck": False, "staatsmedia": None}]


def test_v18_asks_the_same_question_as_v17_and_only_adds_the_rule_after_reading():
    v17, v18 = zc.LEZERS["lezer-v17"], zc.LEZERS["lezer-v18"]
    assert {k: v for k, v in v18.items() if k != "eerste_zin"} == v17 and v18["eerste_zin"] is True
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v18"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v17"})


def test_a_first_sentence_that_says_true_or_false_follows_an_outcome_without_colour():
    assert zc.eerste_zin("Dit klopt grotendeels: drie mensen kwamen om [1]. De trein reed te hard [1].", "onzeker") == (
        "Mogelijk klopt dit, maar we vonden niet genoeg betrouwbare bronnen om het te bevestigen: drie mensen kwamen om "
        "[1]. De trein reed te hard [1].")
    assert zc.eerste_zin("Dit klopt niet: de foto is oud [1].", "niet bevestigd") == (
        "Mogelijk klopt dit niet, maar we vonden geen betrouwbare bron die het tegenspreekt: de foto is oud [1].")
    assert zc.eerste_zin("Dit is misleidend.\n\nDe foto is oud [1].", "onzeker") == (
        "Mogelijk is dit misleidend, maar we vonden geen betrouwbare bron die het tegenspreekt.\n\nDe foto is oud [1].")


def test_a_first_sentence_that_fits_its_outcome_stays_as_it_is():
    for uitleg, uitkomst in (("Dit klopt: het gebeurde [1].", "klopt"), ("Dit klopt niet: oud [1].", "klopt niet"),
                             ("De trein ontspoorde [1].", "onzeker"), ("Dit klopt: het gebeurde [1].", "foto niet bij de bron")):
        assert zc.eerste_zin(uitleg, uitkomst) == uitleg


def _oordeel(**kw):
    return {"oordeel": "klopt", "steunt": [1], "spreekt_tegen": [], "uitleg": "Dit klopt: drie mensen kwamen om [1].",
            "over_beeld": False, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": False, **kw}


def test_v18_changes_the_explanation_and_never_the_colour_or_the_outcome():
    """Eén bron met band *laag* draagt geen groen: de uitkomst is *onzeker*."""
    bericht = "Train derails in Germany"
    zelf = [{**RES[0], "band": "laag"}]
    v17 = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), bericht, zelf, [], "lezer-v17", False, gezocht=True, jaar=2026)
    v18 = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel())), bericht, zelf, [], "lezer-v18", False, gezocht=True, jaar=2026)
    assert (v17["kleur"], v17["uitkomst"]) == (v18["kleur"], v18["uitkomst"]) == (None, "onzeker")
    assert v17["uitleg"].startswith("Dit klopt:") and v18["uitleg"].startswith("Mogelijk klopt dit, maar")


def test_the_product_reads_with_v18_and_looks_for_the_photo_at_its_source():
    """De release van 2026-11-09 (PO: "yes", B66): `lezer-v18` en de foto bij de bron in config."""
    from doublecheck.config import load_config

    c = load_config("config.toml").berichtcontrole
    assert c.lezer == "lezer-v18" and c.fotobron == "fotobron-v2"
