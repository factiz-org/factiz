"""De terugkijktoets (PLAN #28.6 c): had het geheugen het toen al, en vond het dat?

Per vraag het geheugen zoals het was op de dag van de latere check: alleen
claims met een check strikt vóór die dag. Wat goed is, legden mensen vast:
een eerdere check van dezelfde virale post, of een Community Note die naar de
check linkt. Ons eigen model bepaalt nooit wat goed is.
"""

import pytest

from doublecheck.search import Candidate
from doublecheck.terugkijk import _bovengrens, eerste_datums, gatklasse, in_de_tijd, paren, steekproef, tel, uitkomst


def _k(claim, s=0.9):
    return Candidate(claim, s, None)


def test_the_memory_only_holds_claims_checked_before_that_day():
    eerste = {"oud": "2024-01-01", "zelfde-dag": "2024-05-01", "later": "2024-06-01"}
    kandidaten = [_k("later"), _k("zelfde-dag"), _k("oud")]
    assert in_de_tijd(kandidaten, eerste, "2024-05-01").claim_id == "oud"
    assert in_de_tijd([_k("later")], eerste, "2024-05-01") is None


def test_undated_claims_stay_out_unless_the_sensitivity_run_asks():
    eerste = {"oud": "2024-01-01"}
    kandidaten = [_k("zonder-datum"), _k("oud")]
    assert in_de_tijd(kandidaten, eerste, "2024-05-01").claim_id == "oud"
    assert in_de_tijd(kandidaten, eerste, "2024-05-01", met_ongedateerd=True).claim_id == "zonder-datum"


def test_only_admitted_checks_with_a_valid_date_set_when_a_claim_entered_memory():
    rijen = [("a", "2023-03-01", True), ("a", "2021-07-09", True), ("a", "2019-01-01", False),
             ("b", "", True), ("c", "2924-01-01", True)]
    assert eerste_datums(rijen) == {"a": "2021-07-09"}


def test_a_later_check_is_paired_with_strictly_earlier_checks_of_the_same_post():
    per_post = {"twitter.com/x/status/1": {
        "u1": ("c1", "2020-01-01", "afp.com"),
        "u2": ("c2", "2020-01-01", "boomlive.in"),  # dezelfde dag: geen paar
        "u3": ("c3", "2021-02-01", "afp.com"),
    }}
    uit = {p["url"]: p for p in paren(per_post)}
    assert set(uit) == {"u3"}
    assert uit["u3"]["doelen"] == {"c1", "c2"} and uit["u3"]["andere_redactie"]
    assert uit["u3"]["dagen"] == 397 and not uit["u3"]["zelfde_tekst"]


def test_a_check_under_several_posts_is_asked_once_with_all_its_earlier_claims():
    per_post = {"p1": {"u1": ("c1", "2020-01-01", "a.org"), "u9": ("c9", "2020-03-01", "b.org")},
                "p2": {"u2": ("c2", "2020-02-01", "a.org"), "u9": ("c9", "2020-03-01", "b.org")}}
    uit = paren(per_post)
    assert len(uit) == 1 and uit[0]["doelen"] == {"c1", "c2"} and uit[0]["dagen"] == 29


def test_identical_claim_text_is_flagged_so_it_can_be_reported_apart():
    per_post = {"p": {"u1": ("c1", "2020-01-01", "a.org"), "u2": ("c1", "2020-06-01", "a.org")}}
    (paar,) = paren(per_post)
    assert paar["zelfde_tekst"] and not paar["andere_redactie"]


def test_found_only_when_the_match_is_a_claim_people_linked():
    assert uitkomst("matched", False, "c1", {"c1", "c2"}) == "gevonden"
    assert uitkomst("matched", False, "c7", {"c1"}) == "ander record"
    assert uitkomst("related", True, "c1", {"c1"}) == "tegenspraak"
    assert uitkomst("related", False, "c1", {"c1"}) == "verwant"
    assert uitkomst("none", False, None, {"c1"}) == "niets"


def test_gaps_fall_in_three_classes():
    assert [gatklasse(d) for d in (0, 29, 30, 364, 365, 2000)] == \
        ["0-29", "0-29", "30-364", "30-364", "365+", "365+"]


def test_the_sample_to_read_is_fixed_and_at_most_the_asked_size():
    rijen = [{"vraag": str(i)} for i in range(500)]
    assert steekproef(rijen, 100) == steekproef(rijen, 100) and len(steekproef(rijen, 100)) == 100
    assert len(steekproef(rijen[:40], 100)) == 40


def test_counting_refuses_while_a_sampled_other_record_has_no_label():
    uitkomsten = [{"bron": "post", "vraag": "u1", "kandidaat": "c9", "uitkomst": "ander record"},
                  {"bron": "post", "vraag": "u2", "kandidaat": "c1", "uitkomst": "gevonden"}]
    with pytest.raises(ValueError, match="u1"):
        tel(uitkomsten, {})
    telling = tel(uitkomsten, {("post", "u1", "c9"): "zelfde"})
    assert telling["post"]["gevonden"] == 1 and telling["post"]["ander record"] == 1
    assert telling["post"]["ander record gelezen"] == {"zelfde": 1}


def test_the_upper_bound_is_one_when_every_read_record_was_wrong():
    assert _bovengrens(1, 1) == 1.0 and _bovengrens(0, 0) == 1.0
    assert 0.0 < _bovengrens(6, 1461) < 0.01
