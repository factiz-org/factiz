"""Jongste oordeel voorop (PO 2026-10-15, B30 aangevuld, DESIGN §4c).

Verschuift het oordeel over de jaren, dan zegt het label wat redacties het
laatst zeiden, met eronder wat er eerder gezegd werd. Het lab in Wuhan: in
2020 "onwaar", in 2025 "onbewezen". Zonder deze regel zei het label "Known to
be false", op grond van een oordeel uit 2020 over een open vraag.
"""

from doublecheck.verdicts import labelklasse_in_tijd


def test_a_verdict_that_shifts_over_the_years_shows_the_newest_first():
    assert labelklasse_in_tijd([("onwaar", "2020-01-25"), ("onbewezen", "2025-03-01")]) == \
        ("onbewezen", [("onwaar", "2020")])


def test_the_same_side_over_the_years_is_no_shift():
    assert labelklasse_in_tijd([("onwaar", "2016-05-01"), ("misleidend", "2022-02-01")]) == \
        ("onwaar-of-misleidend", [])


def test_newsrooms_contradicting_each_other_in_one_year_stay_disputed():
    assert labelklasse_in_tijd([("waar", "2024-01-10"), ("onwaar", "2024-05-02")]) == ("omstreden", [])


def test_a_later_verdict_overrides_an_earlier_one_on_the_other_side():
    assert labelklasse_in_tijd([("waar", "2019-03-01"), ("onwaar", "2023-01-01"), ("onwaar", "2024-06-01")]) == \
        ("onwaar", [("waar", "2019")])


def test_undated_checks_never_decide_a_shift():
    """Zonder datum is er geen volgorde: dan geldt de regel van altijd."""
    assert labelklasse_in_tijd([("onwaar", ""), ("waar", "2020-01-01")]) == ("omstreden", [])


def test_an_unnormalised_verdict_says_nothing_about_a_shift():
    assert labelklasse_in_tijd([("onwaar", "2020-01-01"), ("onbekend", "2025-01-01")]) == ("onwaar", [])


def test_the_demo_and_the_filter_follow_the_same_rule():
    import pathlib

    wortel = pathlib.Path(__file__).resolve().parent.parent
    demo = (wortel / "doublecheck" / "webui.py").read_text(encoding="utf-8")
    assert "function klasseInTijd" in demo and "Earlier: " in demo
    filter_ = (wortel / "doublecheck" / "claimfilter.py").read_text(encoding="utf-8")
    assert "labelklasse_in_tijd" in filter_
