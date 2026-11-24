"""De meting van B48 (PLAN #32.3a): wat telt als gevangen, wat als een onterechte
*maar*, en dat alleen de toetshelft de eisen beslist."""

import pytest

from doublecheck import detailmeting as dm


def _rij(i, soort, helft="toets", voor=("klopt", "groen"), na=("klopt", "groen"), woorden=None, nieuw=None, bron="nieuw"):
    correcties = [{"woorden": woorden}] if woorden else []
    return {"id": i, "soort": soort, "bron": bron, "helft": helft, "nieuw": nieuw,
            "voor": {"oordeel": voor[0], "kleur": voor[1]}, "na": {"oordeel": na[0], "kleur": na[1], "correcties": correcties}}


def test_a_caught_detail_needs_the_invented_words_marked():
    goed = _rij("a", "vals", na=("klopt grotendeels", None), woorden="275,000 troops", nieuw="275,000")
    fout = _rij("b", "vals", na=("klopt grotendeels", None), woorden="Moscow", nieuw="275,000")
    assert dm.gevangen(goed, {}) and not dm.gevangen(fout, {})


def test_red_from_the_machine_counts_as_caught_and_a_mark_without_a_known_detail_is_read():
    assert dm.gevangen(_rij("a", "vals", voor=("klopt niet", "rood"), na=("klopt niet", "rood")), {})
    onbekend = _rij("c", "vals", na=("klopt grotendeels", None), woorden="2003", nieuw=None)
    with pytest.raises(dm.Weigering):
        dm.gevangen(onbekend, {})
    assert dm.gevangen(onbekend, {("c", "markering"): "juist"})


def test_a_but_on_a_real_article_must_be_read_and_counts_unless_justified():
    rijen = [_rij("w1", "echt", na=("klopt grotendeels", None), woorden="Friday", bron="W5")]
    with pytest.raises(dm.Weigering):
        dm.telling(rijen, {})
    assert dm.telling(rijen, {("w1", "maar"): "terecht"})["eisen"]["echte artikelen: hoogstens 1 van de 100 een onterechte maar"]
    telling = dm.telling(rijen, {("w1", "maar"): "onterecht"})
    assert telling["toets"]["echt"]["onterechte maar"] == 1


def test_the_count_refuses_while_a_green_on_an_invented_detail_is_unread_and_only_the_test_half_decides():
    rijen = [_rij("n1", "vals"), _rij("d1", "vals", helft="ontwikkel")]
    with pytest.raises(dm.Weigering):
        dm.telling(rijen, {("d1", "groen"): "vals"})
    telling = dm.telling(rijen, {("n1", "groen"): "set fout", ("d1", "groen"): "vals"})
    assert telling["toets"]["vals"]["n"] == 0 and telling["ontwikkel"]["vals"]["groen na"] == 1
    assert telling["eisen"]["verzonnen details: nooit groen"] is True
    telling = dm.telling(rijen, {("n1", "groen"): "vals", ("d1", "groen"): "vals"})
    assert telling["eisen"]["verzonnen details: nooit groen"] is False
    assert telling["eisen"]["verzonnen details: minstens 90% gevangen"] is False


def test_a_rejected_new_article_is_replaced_by_the_next_in_the_same_order():
    artikelen = [{"id": f"a{i:03d}", "tekst": f"Kop {i}"} for i in range(100)]
    voor = dm.kies_nieuw(artikelen, {"a000"}, set())
    weg = {voor[2]["bron_id"], voor[5]["bron_id"]}
    na = dm.kies_nieuw(artikelen, {"a000"}, weg)
    gebleven = [s["bron_id"] for s in voor if s["bron_id"] not in weg]
    assert [s["bron_id"] for s in na][:38] == gebleven and len(na) == 40 and not weg & {s["bron_id"] for s in na}
