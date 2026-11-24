"""De testset voor Ask Factiz (PLAN #24.10 b): wanneer telt een antwoord als goed?"""

import json

import pytest

from doublecheck.vraagtoets import (STILTE, STILTE_WEB, VRAGEN, beoordeel, is_goed, kies_poort, stiltepoort,
                                  tel_getoond, tel_regels, tel_vals, trek)


def test_a_member_of_the_evergreen_group_is_a_good_answer():
    vraag = {"leden": ["a", "b"]}
    assert is_goed("b", "wat dan ook", vraag) and not is_goed("c", "wat dan ook", vraag)


def test_for_the_po_examples_a_keyword_decides():
    vraag = {"trefwoorden": ["biolab", "lugar"]}
    assert is_goed("x", "The Lugar Center in Tbilisi makes bioweapons", vraag)
    assert not is_goed("x", "Sunscreen causes skin cancer", vraag)


def test_only_rows_ask_factiz_would_show_count_as_shown():
    """Ask Factiz toont alleen `matched` en `related`; een goede claim onder de
    verwantdrempel staat wel in de top vijf, maar de lezer ziet hem niet."""
    vraag = {"leden": ["goed"]}
    uitslag = beoordeel([("ander", "t", "related"), ("goed", "t", "none")], vraag)
    assert uitslag == {"eerste": False, "top5": True, "getoond": False, "getoonde_regels": 1}


def test_the_question_set_was_fixed_before_the_resolver_saw_it():
    doc = json.loads(VRAGEN.read_text(encoding="utf-8"))
    assert len(doc["vragen"]) == 53
    assert all(v.get("leden") or v.get("trefwoorden") for v in doc["vragen"])
    assert "vóór de resolver" in doc["_meta"]


def test_the_gate_shows_the_most_without_a_single_false_row_in_silence():
    rijen = {0.1: (45, 3), 0.3: (40, 0), 0.5: (40, 0), 0.7: (30, 0)}
    assert kies_poort(rijen) == 0.5
    assert kies_poort({0.1: (45, 1)}) is None


def test_the_silence_set_was_fixed_before_measuring():
    doc = json.loads(STILTE.read_text(encoding="utf-8"))
    assert len(doc["vragen"]) == 50 and "vóór het meten" in doc["_meta"]


def test_the_sample_from_the_pool_is_reproducible():
    assert trek(5, 100, 2410) == trek(5, 100, 2410)
    assert trek(5, 100, 2410) != trek(5, 100, 2411)
    assert len(trek(500, 100, 1)) == 100


def test_rows_are_counted_per_gate():
    uitkomsten = [{"regels": [{"score": 0.95}, {"score": 0.6}]}, {"regels": [{"score": 0.72}]}]
    assert tel_regels(uitkomsten) == {0.5: 3, 0.7: 2, 0.9: 1}


def test_each_row_through_the_gate_is_read_before_it_counts():
    """Tellen weigert zolang een regel vanaf de laagste poort geen label heeft
    (zoals de stiltetoets van #28.6 g)."""
    uitkomsten = [{"id": "s1", "regels": [{"claim": "c1", "score": 0.95}, {"claim": "c2", "score": 0.4}]}]
    with pytest.raises(ValueError, match="s1"):
        tel_vals(uitkomsten, {})


def test_borderline_rows_count_in_favour_of_the_gate():
    """Een randgeval telt niet als vals; het verslag noemt ze apart."""
    uitkomsten = [{"id": "s1", "regels": [{"claim": "c1", "score": 0.95}, {"claim": "c2", "score": 0.75}]},
                  {"id": "s2", "regels": [{"claim": "c3", "score": 0.85}]}]
    labels = {("s1", "c1"): "randgeval", ("s1", "c2"): "vals", ("s2", "c3"): "terecht"}
    telling = tel_vals(uitkomsten, labels)
    assert telling[0.7] == {"vals": 1, "terecht": 1, "randgeval": 1, "stukken_met_vals": 1}
    assert telling[0.9] == {"vals": 0, "terecht": 0, "randgeval": 1, "stukken_met_vals": 0}


def test_the_rule_fixed_before_measuring_keeps_07_only_without_false_rows():
    """PLAN #24.10: nul valse regels op 0,7 houdt 0,7; anders de laagste uit
    {0,8, 0,9} zonder valse regels; anders geen poort."""
    assert stiltepoort({0.7: 0, 0.8: 0, 0.9: 0}) == 0.7
    assert stiltepoort({0.7: 2, 0.8: 0, 0.9: 0}) == 0.8
    assert stiltepoort({0.7: 5, 0.8: 1, 0.9: 0}) == 0.9
    assert stiltepoort({0.7: 179, 0.8: 122, 0.9: 60}) is None


def test_the_labels_of_the_web_silence_cover_every_row_through_the_gate():
    doc = json.loads(STILTE_WEB.read_text(encoding="utf-8"))
    assert {r["label"] for r in doc["regels"]} <= {"vals", "terecht", "randgeval"}
    assert all(r["score"] >= 0.7 for r in doc["regels"])
    assert len({(r["stuk"], r["claim"]) for r in doc["regels"]}) == len(doc["regels"])


def test_what_the_page_shows_is_counted_per_card():
    """#24.10 (c): de pagina toont elk cluster één keer; het cijfer telt de
    kaarten die de lezer ziet, ook als er niets getoond wordt."""
    assert tel_getoond([False, True]) == {"getoond": True, "eerste_getoond": False, "niets": False, "kaarten": 2}
    assert tel_getoond([]) == {"getoond": False, "eerste_getoond": False, "niets": True, "kaarten": 0}
