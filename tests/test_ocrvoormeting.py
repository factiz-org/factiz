"""Screenshots beter lezen, lokaal (PLAN #32.34): de keuze tussen lezingen, de eigen check in de top 5, en de eisen
vooraf."""

import pytest

from doublecheck import ocrvoormeting as ov

HINDI = "भारत की राष्ट्रपति भारत के उप-राष्ट्रपति"
BRIJ = "Ma are mid eo fear ara mi derne"


def test_the_surest_reading_wins_only_when_it_is_mostly_in_its_own_script():
    lezingen = [("Latin", BRIJ, 40.0), ("Devanagari", HINDI, 61.0), ("Telugu", "abc def", 90.0)]
    assert ov.kies_lezing(lezingen, 0.5) == ("Devanagari", HINDI)  # Telugu las Latijn: telt niet
    assert ov.kies_lezing([("Latin", BRIJ, 40.0), ("Devanagari", "xyz", 70.0)], 0.5) == ("Latin", BRIJ)
    assert ov.kies_lezing([("Latin", "", -1.0)], 0.5) == ("Latin", "")


def test_easyocr_detections_become_lines_from_top_to_bottom():
    vondsten = [([[0, 50], [10, 50], [10, 60], [0, 60]], "second", 0.5),
                ([[30, 10], [40, 10], [40, 20], [30, 20]], "world", 0.9),
                ([[0, 10], [10, 10], [10, 20], [0, 20]], "hello", 0.7)]
    tekst, zekerheid = ov.easy_tekst(vondsten, hoogte=100)
    assert tekst == "hello world\nsecond" and zekerheid == pytest.approx(0.7)
    assert ov.easy_tekst([], hoogte=100) == ("", -1.0)


def test_the_own_check_counts_by_its_group_in_the_five_from_the_database():
    kandidaten = [{"claim": f"gfc-{i}"} for i in range(8)]
    assert ov.eigen_in_top5(kandidaten, ["g7"], {"gfc-4": "g7"})
    assert not ov.eigen_in_top5(kandidaten, ["g7"], {"gfc-6": "g7"})  # pas op plaats 7
    assert ov.eigen_in_top5(kandidaten, ["gfc-2"], {})  # een claim zonder groep is zijn eigen groep


def _rij(id_, variant, top5, groep="G19"):
    return {"id": id_, "groep": groep, "variant": variant, "top5": top5, "seconden": 1.0, "een_lezer": 1.0}


def test_counting_refuses_while_a_text_of_g19_has_no_reading_label():
    rijen = [_rij("a", "V0", False)]
    with pytest.raises(ov.Weigering):
        ov.telling(rijen, {})
    with pytest.raises(ov.Weigering):
        ov.telling(rijen, {("a", "V0"): "misschien"})
    assert ov.telling(rijen + [_rij("b", "V0", True, "B39")], {("a", "V0"): "nee"})["V0"]["B39 top 5"] == 1


def test_a_variant_is_a_candidate_only_when_all_four_requirements_hold():
    g19 = [f"g{i}" for i in range(19)]
    b39 = [f"b{i}" for i in range(39)]
    rijen, labels = [], {}
    for v, top_g, top_b, ja in (("V0", 3, 30, 2), ("V1", 8, 29, 7), ("V2", 8, 28, 9)):
        rijen += [_rij(i, v, n < top_g) for n, i in enumerate(g19)]
        rijen += [_rij(i, v, n < top_b, "B39") for n, i in enumerate(b39)]
        labels |= {(i, v): ("ja" if n < ja else "nee") for n, i in enumerate(g19)}
    uit = ov.telling(rijen, labels)
    assert uit["V1"]["kandidaat"] and not uit["V2"]["kandidaat"]  # V2 verliest 2 bij de bewaking
    assert uit["V1"]["G19 top 5"] == 8 and uit["V1"]["G19 leesbaar ja"] == 7
    traag = [{**r, "een_lezer": 6.0} if r["variant"] == "V1" else r for r in rijen]
    assert not ov.telling(traag, labels)["V1"]["kandidaat"]


def test_the_sets_are_the_19_missed_of_209_and_the_other_39():
    assert len(ov.G19) == 19 and ov.G19[0] == "n-sn-002" and ov.G19[-1] == "n-sn-057"
    assert ov.LEZERS_EASY["Telugu"] == ["te", "en"] and "hi" in ov.LEZERS_EASY["Devanagari"]
