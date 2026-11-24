"""De voormeting voor de radar (PLAN #37.0): de lat staat vooraf, en tellen weigert zolang iets geen label heeft."""

import pytest

from doublecheck import radarvoormeting as rv

MAATSTAF = [{"id": "afp-01", "datum": "2026-11-12"}, {"id": "afp-02", "datum": "2026-11-03"},
            {"id": "afp-03", "datum": "2026-10-30"}]


def test_a_source_only_counts_when_it_was_at_least_two_days_before_the_fact_check():
    assert rv.dagen_eerder("2026-11-04", "2026-11-12") == 8
    assert rv.dagen_eerder(None, "2026-11-12") is None
    labels = {"afp-01": {"notes": [{"datum": "2026-11-04", "zelfde": True}]},
              "afp-02": {"notes": [{"datum": "2026-11-02", "zelfde": True}]},       # één dag eerder: telt niet
              "afp-03": {"archief": [{"datum": "2026-10-01", "zelfde": False}]}}     # niet dezelfde bewering
    uit = rv.tellen(MAATSTAF, labels, [])
    assert uit["eerder_in_een_bron"] == 1 and uit["per_bron"] == {"notes": 1, "archief": 0}
    assert uit["mediaan_dagen_eerder"] == 8 and uit["terug_gehaald"] is True      # 1 van 3 is een derde


def test_the_week_passes_with_three_checkable_candidates_of_which_one_nobody_checked():
    leeg = {c["id"]: {} for c in MAATSTAF}
    week = [{"post": "1", "te_checken": True, "al_gecheckt": True}, {"post": "2", "te_checken": True, "al_gecheckt": True},
            {"post": "3", "te_checken": True, "al_gecheckt": False}, {"post": "4", "te_checken": False}]
    uit = rv.tellen(MAATSTAF, leeg, week)
    assert uit["week_te_checken"] == 3 and uit["week_nog_niet_gecheckt"] == 1 and uit["vooruit_gehaald"] is True
    assert uit["terug_gehaald"] is False and uit["radar"] is True
    assert rv.tellen(MAATSTAF, leeg, week[:2])["radar"] is False


def test_counting_refuses_while_a_fact_check_or_a_candidate_has_no_label():
    with pytest.raises(rv.Weigering, match="zonder label"):
        rv.tellen(MAATSTAF, {"afp-01": {}}, [])
    with pytest.raises(rv.Weigering, match="zonder label"):
        rv.tellen(MAATSTAF, {c["id"]: {} for c in MAATSTAF}, [{"post": "9"}])


def test_an_old_check_in_the_archive_says_the_claim_comes_back_not_that_it_circulates_now():
    labels = {"afp-01": {"archief": [{"datum": "2024-03-27", "zelfde": True}]},
              "afp-02": {"archief": [{"datum": "2026-10-20", "zelfde": True}]}, "afp-03": {}}
    uit = rv.tellen(MAATSTAF, labels, [])
    assert uit["per_bron"] == {"notes": 0, "archief": 1} and uit["eerder_in_een_bron"] == 1
