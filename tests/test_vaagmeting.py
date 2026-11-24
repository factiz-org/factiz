"""Vage claimteksten opsporen (PLAN.md #25.26)."""

import numpy as np
import pytest

from doublecheck import vaagmeting as vm


def test_the_nearest_claim_counts_a_variant_as_its_claim():
    """Een variant is een vertaling van een claim: raakt een stuk de variant,
    dan raakt het de claim."""
    stukken = np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]], dtype=np.float32)
    claims = np.array([[1.0, 0.0]], dtype=np.float32)
    varianten = np.array([[0.0, 1.0]], dtype=np.float32)
    ids, gelijkenis = vm.dichtste(stukken, claims, ["c1"], varianten, ["c2"], blok=2)
    assert ids == ["c1", "c2", "c2"]
    assert gelijkenis[0] == pytest.approx(1.0) and gelijkenis[2] == pytest.approx(0.8)


def test_a_claim_is_a_magnet_only_with_enough_distinct_close_pieces():
    ids = ["a"] * 5 + ["b"] * 4 + ["c"] * 6
    gelijkenis = np.array([0.75] * 5 + [0.95] * 4 + [0.69] * 6)
    assert vm.trekkers(ids, gelijkenis, drempel=0.70, minimum=5) == {"a": 5}


def test_counting_refuses_a_magnet_without_a_label():
    with pytest.raises(vm.Weigering):
        vm.uitslag({"a": 7}, {}, {})


def test_the_count_says_how_many_magnets_are_vague_and_which_flags_they_caused():
    trekkers = {"a": 9, "b": 6, "c": 5}
    labels = {"a": "vaag", "b": "bewering", "c": "vaag"}
    vlaggen = [{"claim_id": "a", "label": "vals"}, {"claim_id": "a", "label": "vals"},
               {"claim_id": "z", "label": "vals"}, {"claim_id": "b", "label": "terecht"}]
    uit = vm.uitslag(trekkers, labels, {"vlaggen": vlaggen})
    assert (uit["trekkers"], uit["vaag"], uit["bewering"]) == (3, 2, 1)
    assert uit["valse_vlaggen_bij_vaag"] == 2 and uit["valse_vlaggen"] == 3


def test_a_pool_without_flags_still_counts_its_trekkers(tmp_path):
    """#25.33: de verse pool heeft geen vlaggen van #21.9; de telling van de
    trekkers moet daar ook kunnen, met nul valse vlaggen erbij."""
    from doublecheck.vaagmeting import lees_vlaggen, uitslag

    assert lees_vlaggen(tmp_path) == {"vlaggen": []}
    t = uitslag({"c1": 6}, {"c1": "vaag"}, lees_vlaggen(tmp_path))
    assert t["vaag"] == 1 and t["valse_vlaggen"] == 0
