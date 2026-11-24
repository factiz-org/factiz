"""Welke eenheid van een artikel de rechter leest en welke wint (#30.11).

Eén plek voor resolver en terugkijktoets, zodat de zeef meet wat de resolver
doet. De categorie per eenheid zet `categorize` (DR4); hier wordt gekozen.
"""

import dataclasses

from doublecheck import artikel
from doublecheck.categorize import categorize
from doublecheck.config import RechterSettings, load_config
from doublecheck.search import Candidate


def _config(aan=True):
    basis = load_config()
    drempels = dataclasses.replace(basis.thresholds, rechter_vloer=0.79, rechter_zelfde=0.95, rechter_veto=0.6)
    return dataclasses.replace(basis, thresholds=drempels,
                               rechter=RechterSettings(aan=aan, model="nep", pad="nep", diepte=5))


def test_one_unit_is_always_read_as_before():
    assert artikel.te_lezen([[]], _config()) == [0]
    assert artikel.te_lezen([[Candidate("a", 0.5)]], _config(aan=False)) == [0]


def test_the_judge_reads_the_three_units_closest_to_a_claim_above_the_floor():
    lijsten = [[Candidate("a", s)] for s in (0.80, 0.70, 0.86, 0.84, 0.82)] + [[]]
    assert artikel.te_lezen(lijsten, _config()) == [2, 3, 4]
    assert artikel.te_lezen(lijsten, _config(aan=False)) == []


def test_matched_beats_related_and_then_the_widest_margin_wins():
    config = _config()
    t = config.thresholds
    gerelateerd = (categorize(0.85, t), Candidate("a", 0.85), 0.0)
    krap = (categorize(0.83, t, rechter=0.96), dataclasses.replace(Candidate("b", 0.83), rechter=0.96), 0.01)
    ruim = (categorize(0.80, t, rechter=0.99), dataclasses.replace(Candidate("c", 0.80), rechter=0.99), 0.04)
    assert artikel.winnaar([gerelateerd, krap, ruim]) is ruim
    assert artikel.winnaar([gerelateerd, krap]) is krap


def test_with_everything_equal_the_first_unit_wins():
    t = _config().thresholds
    eerste = (categorize(0.9, t), Candidate("a", 0.9), 0.0)
    tweede = (categorize(0.9, t), Candidate("b", 0.9), 0.0)
    assert artikel.winnaar([eerste, tweede]) is eerste


def test_the_margin_is_the_distance_above_the_judges_own_threshold():
    config = _config()
    assert artikel.marge(dataclasses.replace(Candidate("a", 0.83), rechter=0.97), config) == 0.97 - 0.95
    assert artikel.marge(dataclasses.replace(Candidate("a", 0.90), rechter=0.70), config) == 0.70 - 0.6
    assert artikel.marge(Candidate("a", 0.9), _config(aan=False)) == 0.0


def test_what_a_caller_carries_along_comes_back_with_the_winner():
    t = _config().thresholds
    eerste = (categorize(0.80, t), Candidate("a", 0.80), 0.0, True, False)
    tweede = (categorize(0.95, t), Candidate("b", 0.95), 0.0, False, True)
    assert artikel.winnaar([eerste, tweede]) is tweede
