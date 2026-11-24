"""De meting van #25.36 (stap b en e): de meetset door het echte pad.

Elk paar is een claim en een post in de tegenvorm. Gevonden is alleen wat
naar díe claim wijst, of naar een claim in hetzelfde cluster (dezelfde
bewering, andere woorden). Een treffer op iets anders is geen succes, en een
`matched` op iets anders gaat naar de leesproef. De toetshelft blijft dicht tot
stap e: de meting weigert hem zolang de opzet dat zegt.
"""

import pytest

from doublecheck import vraagmeting as vm


def test_only_the_expected_claim_or_its_cluster_counts_as_found():
    clusters = {"a": "cl-1", "a2": "cl-1", "b": None}
    assert vm.resolve_uitkomst({"category": "matched", "claim": {"id": "a"}}, "a", clusters) == "gevonden"
    assert vm.resolve_uitkomst({"category": "matched", "claim": {"id": "a2"}}, "a", clusters) == "gevonden"
    assert vm.resolve_uitkomst({"category": "related", "claim": {"id": "a"}}, "a", clusters) == "verwant"
    assert vm.resolve_uitkomst({"category": "matched", "claim": {"id": "b"}}, "a", clusters) == "ander matched"
    assert vm.resolve_uitkomst({"category": "related", "claim": {"id": "b"}}, "a", clusters) == "ander verwant"
    assert vm.resolve_uitkomst({"category": "none", "claim": None}, "a", clusters) == "niets"


def test_ask_counts_the_expected_claim_first_or_anywhere_in_what_it_shows():
    clusters = {"a": None, "b": None, "c": None}
    eerst = {"results": [{"claim": {"id": "a"}}, {"claim": {"id": "b"}}]}
    later = {"results": [{"claim": {"id": "b"}}, {"claim": {"id": "a"}}]}
    assert vm.ask_uitkomst(eerst, "a", clusters) == "eerste"
    assert vm.ask_uitkomst(later, "a", clusters) == "getoond"
    assert vm.ask_uitkomst({"results": [{"claim": {"id": "c"}}]}, "a", clusters) == "ander"
    assert vm.ask_uitkomst({"results": []}, "a", clusters) == "niets"


def test_the_test_half_stays_closed_until_step_e():
    paren = [{"helft": "ontwikkel"}, {"helft": "toets"}]
    assert vm.kies_helft(paren, "ontwikkel") == [{"helft": "ontwikkel"}]
    with pytest.raises(vm.Dicht):
        vm.kies_helft(paren, "toets")
    assert vm.kies_helft(paren, "toets", stap_e=True) == [{"helft": "toets"}]


def test_a_pair_that_failed_the_read_test_is_left_out():
    paren = [{"helft": "ontwikkel", "lezing": "goed"}, {"helft": "ontwikkel", "lezing": "betekenisfout"},
             {"helft": "ontwikkel", "lezing": None}]
    assert vm.kies_helft(paren, "ontwikkel") == [{"helft": "ontwikkel", "lezing": "goed"},
                                                  {"helft": "ontwikkel", "lezing": None}]


def test_the_report_counts_per_direction_and_language():
    regels = [{"richting": "vraag", "taal": "en", "resolve": "gevonden", "ask": "eerste"},
              {"richting": "vraag", "taal": "en", "resolve": "niets", "ask": "niets"},
              {"richting": "bewering", "taal": "si", "resolve": "verwant", "ask": "getoond"}]
    tabel = vm.tel(regels)
    assert tabel[("vraag", "en")]["resolve"] == {"gevonden": 1, "niets": 1}
    assert tabel[("bewering", "si")]["ask"] == {"getoond": 1}
    assert tabel[("alle", "alle")]["n"] == 3


def test_only_texts_the_rule_changes_go_through_the_silence_check():
    teksten = [("a", "Vaccines cause autism."), ("b", "Is it true that vaccines cause autism?"), ("c", "Rain")]
    assert [s for s, _ in vm.geraakt(teksten)] == ["b"]


def test_a_new_match_with_the_rule_goes_to_the_read_test():
    regels = [{"sleutel": "a", "uit": {"categorie": "related"}, "aan": {"categorie": "matched"}},
              {"sleutel": "b", "uit": {"categorie": "matched"}, "aan": {"categorie": "matched"}},
              {"sleutel": "c", "uit": {"categorie": "none"}, "aan": {"categorie": "related"}}]
    assert [r["sleutel"] for r in vm.nieuwe_matches(regels)] == ["a"]
