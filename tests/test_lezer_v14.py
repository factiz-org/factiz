"""Eén goede bron is genoeg voor groen (`lezer-v14`, B61, PLAN #32.56, BENCHMARK §238; PO 2026-11-07: "mag"): als de lezer
*klopt* zegt, niets het tegenspreekt en de bewering niet over een beeld gaat."""

import json

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc

BERICHT = "Kenyan cult leader Paul Mackenzie is sentenced to 200 years in prison"


def _oordeel(oordeel="klopt", steunt=(1,), tegen=(), over_beeld=False):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Dit klopt.",
            "over_beeld": over_beeld, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": True}


def _res(*bronnen):
    return [{"nr": i, "url": f"https://www.{site}/a{i}", "titel": "t", "site": site, "soort": soort, "band": band,
             "fragment": "f", "factcheck": False, "staatsmedia": None}
            for i, (site, band, soort) in enumerate(bronnen, 1)]


def _kleur(lezer, antwoord=None, res=None, beeld=False):
    res = res if res is not None else _res(("bbc.com", "goed", "overig"), ("blog.example", None, "overig"))
    return zc.na_lezen(zc.lees_oordeel(json.dumps(antwoord or _oordeel())), BERICHT, res, [], lezer, beeld,
                       gezocht=True, jaar=2026)["kleur"]


def test_v14_is_v13_with_one_good_source_enough_and_has_its_own_fingerprint():
    v13, v14 = zc.LEZERS["lezer-v13"], zc.LEZERS["lezer-v14"]
    assert {k: v for k, v in v14.items() if k != "regel"} == {k: v for k, v in v13.items() if k != "regel"}
    assert (v13["regel"], v14["regel"]) == ("ruim", "een")
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v14"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v13"})


def test_one_good_source_that_confirms_turns_green_in_v14_only():
    assert _kleur("lezer-v14") == "groen"
    assert _kleur("lezer-v13") is None


def test_never_green_with_one_source_when_it_is_not_good_contradicted_doubted_or_about_an_image():
    assert _kleur("lezer-v14", res=_res(("blog.example", None, "overig"))) is None
    assert _kleur("lezer-v14", res=_res(("x.com", None, "platform"), ("bbc.com", "laag", "overig"))) is None
    tegen = _res(("bbc.com", "goed", "overig"), ("reuters.com", "goed", "overig"))
    assert _kleur("lezer-v14", _oordeel(steunt=(1,), tegen=(2,)), res=tegen) is None
    assert _kleur("lezer-v14", _oordeel("onzeker")) is None
    assert _kleur("lezer-v14", _oordeel(over_beeld=True), beeld=True) is None  # een beeld: nog steeds twee bronnen
    twee = _res(("bbc.com", "goed", "overig"), ("reuters.com", "goed", "overig"))
    assert _kleur("lezer-v14", _oordeel(steunt=(1, 2), over_beeld=True), res=twee, beeld=True) == "groen"


def test_an_official_source_counts_as_one_good_source():
    assert _kleur("lezer-v14", res=_res(("gov.uk", None, "officieel"))) == "groen"
