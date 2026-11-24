"""Een echte kop op de eigen site van het genoemde medium mag groen worden (`lezer-v11`, PLAN #32.46, PO 2026-11-07: "pak
eerst maar door, maken we v10 gelijk wat completer"): v10 plus de regel van §232, na het lezen, in `kleur_van`."""

import json

from doublecheck import meting as mt
from doublecheck import narekening as nr
from doublecheck import zoekcontrole as zc

KOP = "DW\nZambia's civil service overhaul raises questions"


def _oordeel(oordeel="klopt", steunt=(1,), tegen=(), over_beeld=False):
    return {"oordeel": oordeel, "steunt": list(steunt), "spreekt_tegen": list(tegen), "uitleg": "Uitleg.",
            "over_beeld": over_beeld, "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0},
            "zou_gemeld": True}


def _res(*bronnen):
    return [{"nr": i, "url": f"https://www.{site}/a", "titel": titel, "site": site, "soort": "overig", "band": band,
             "fragment": "f", "factcheck": False, "staatsmedia": None}
            for i, (site, band, titel) in enumerate(bronnen, 1)]


def _na(lezer, bericht=KOP, res=None, antwoord=None):
    res = res if res is not None else _res(("dw.com", "goed", "Zambia’s civil service overhaul raises questions | DW"))
    return zc.na_lezen(zc.lees_oordeel(json.dumps(antwoord or _oordeel())), bericht, res, [], lezer, False, gezocht=True,
                       jaar=2026)


def test_v11_asks_the_model_exactly_what_v10_asks_and_adds_only_the_headline_rule():
    v10, v11 = zc.LEZERS["lezer-v10"], zc.LEZERS["lezer-v11"]
    assert {k: v for k, v in v11.items() if k != "eigen_kop"} == v10 and v11["eigen_kop"] is True
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v11"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v10"})


def test_a_real_headline_word_for_word_on_the_own_good_site_of_the_named_outlet_turns_green_in_v11_only():
    assert _na("lezer-v10")["kleur"] is None
    uit = _na("lezer-v11")
    assert (uit["kleur"], uit["uitkomst"]) == ("groen", "klopt")
    assert _na("lezer-v11", "dw.\nZambia's civil service overhaul raises questions")["kleur"] == "groen"


def test_never_green_from_another_site_without_band_another_title_a_contradiction_or_doubt():
    titel = "Zambia's civil service overhaul raises questions"
    for res in (_res(("blog.example", "goed", titel)), _res(("dw.com", None, titel)), _res(("dw.com", "goed", "Zambia cuts jobs")),
                _res(("bbc.com", "goed", titel))):
        assert _na("lezer-v11", res=res)["kleur"] is None, res
    res = _res(("dw.com", "goed", titel), ("blog.example", None, "Fake"))
    assert _na("lezer-v11", res=res, antwoord=_oordeel(tegen=(2,)))["kleur"] is None
    assert _na("lezer-v11", antwoord=_oordeel("onzeker"))["kleur"] is None
    assert _na("lezer-v11", antwoord=_oordeel(over_beeld=True))["kleur"] is None
    assert _na("lezer-v11", bericht=titel)["kleur"] is None
    assert _na("lezer-v11", bericht="DW\nZambia overhaul")["kleur"] is None


def test_the_measured_rule_of_232_is_the_rule_of_the_product():
    rij = {"oordeel": "klopt", "bronnen": [{"site": "dw.com", "band": "goed", "rol": "bevestigt",
                                            "titel": "Zambia's civil service overhaul raises questions"}]}
    assert nr.eigen_kop(rij, KOP)
    assert not nr.eigen_kop({**rij, "bronnen": rij["bronnen"] + [{"site": "x.org", "rol": "spreekt tegen"}]}, KOP)
    assert nr.MEDIUMSITES is zc.MEDIA
