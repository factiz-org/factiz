"""De meting van #25.31: de stance in de taal van de zin, uit en aan."""

from doublecheck.zinstaalmeting import criterium, tel


def _oordeel(doc, claim):
    return "terecht" if doc.startswith("goed") else "vals"


def test_counting_shows_what_the_rule_removes_and_adds():
    uit = {("goed-1", "c1"), ("fout-1", "c2"), ("fout-2", "c3")}
    aan = {("goed-1", "c1"), ("fout-2", "c3")}
    t = tel(uit, aan, _oordeel)
    assert t["uit"] == {"terecht": 1, "vals": 2} and t["aan"] == {"terecht": 1, "vals": 1}
    assert t["weg"] == [("fout-1", "c2", "vals")] and t["erbij"] == []


def test_the_rule_passes_only_without_losing_a_rightful_flag_and_with_two_false_gone():
    """Vastgelegd vóór het meten (PLAN #25.31)."""
    goed = tel({("goed-1", "c1"), ("fout-1", "c2"), ("fout-2", "c3")}, {("goed-1", "c1")}, _oordeel)
    assert criterium([goed])["gehaald"]
    kost = tel({("goed-1", "c1"), ("fout-1", "c2"), ("fout-2", "c3")}, set(), _oordeel)
    assert not criterium([kost])["gehaald"]
    te_weinig = tel({("goed-1", "c1"), ("fout-1", "c2")}, {("goed-1", "c1")}, _oordeel)
    assert not criterium([te_weinig])["gehaald"]
