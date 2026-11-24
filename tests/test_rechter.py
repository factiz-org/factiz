"""De rechter in het aanvraagpad (PLAN #30.3, B36): hij leest de bovenste
kandidaten boven de vloer, zet ze op zijn eigen volgorde, en een kandidaat
die hij niet las, kan met de rechter aan nooit `matched` worden.
"""

import dataclasses
import sqlite3

import pytest

from doublecheck import rechter
from doublecheck.config import load_config
from doublecheck.search import Candidate


def _config(aan=True, diepte=3, vloer=0.79):
    c = load_config()
    return dataclasses.replace(
        c, thresholds=dataclasses.replace(c.thresholds, rechter_zelfde=0.99, rechter_vloer=vloer),
        rechter=dataclasses.replace(c.rechter, aan=aan, model="rechter-d@x", pad="x", diepte=diepte))


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE claim (claim_id TEXT, canonical_text TEXT)")
    conn.executemany("INSERT INTO claim VALUES (?, ?)", [(f"c{i}", f"tekst {i}") for i in range(6)])
    return conn


KANDIDATEN = [Candidate("c0", 0.95), Candidate("c1", 0.90), Candidate("c2", 0.85), Candidate("c3", 0.80),
              Candidate("c4", 0.70)]


def test_with_the_judge_off_nothing_changes():
    assert rechter.herorden(_conn(), _config(aan=False), "vraag", KANDIDATEN, scorer=None) == KANDIDATEN


def test_the_judge_reads_only_the_top_candidates_above_the_floor_and_reorders_them():
    gelezen = []

    def scorer(vraag, teksten):
        gelezen.extend(teksten)
        return [{"tekst 0": 0.1, "tekst 1": 0.995, "tekst 2": 0.5}[t] for t in teksten]

    uit = rechter.herorden(_conn(), _config(diepte=3), "vraag", KANDIDATEN, scorer=scorer)
    assert gelezen == ["tekst 0", "tekst 1", "tekst 2"]
    assert [k.claim_id for k in uit] == ["c1", "c2", "c0", "c3", "c4"]
    assert [k.rechter for k in uit] == [0.995, 0.5, 0.1, None, None]


def test_with_the_judge_on_an_unread_candidate_is_never_a_yes():
    assert rechter.oordeel(Candidate("c3", 0.80), _config()) == 0.0
    assert rechter.oordeel(Candidate("c3", 0.80), _config(aan=False)) is None
    assert rechter.oordeel(dataclasses.replace(Candidate("c1", 0.9), rechter=0.995), _config()) == 0.995


def test_weights_that_do_not_match_the_configured_version_are_refused(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"andere gewichten")
    with pytest.raises(rechter.Weigering):
        rechter.controleer_versie(str(tmp_path), "rechter-d@000000000000")
    assert rechter.controleer_versie(str(tmp_path), rechter.versie(tmp_path)) is None


def test_the_best_candidate_is_the_one_furthest_above_its_own_threshold():
    config = _config(diepte=5)
    config = dataclasses.replace(config, thresholds=dataclasses.replace(config.thresholds, rechter_veto=0.3))
    # c0 ligt boven de matchdrempel en haalt het veto ruim; c3 scoort hoger maar mist de strenge drempel
    scores = {"tekst 0": 0.6, "tekst 1": 0.1, "tekst 2": 0.2, "tekst 3": 0.9}
    uit = rechter.herorden(_conn(), config, "vraag", KANDIDATEN, scorer=lambda v, t: [scores[x] for x in t])
    assert uit[0].claim_id == "c0"


def test_a_measurement_can_watch_what_the_judge_read_without_the_texts():
    gezien = []
    rechter.waarnemer = gezien.append
    try:
        rechter.herorden(_conn(), _config(diepte=2), "vraag", KANDIDATEN, scorer=lambda v, t: [0.4, 0.7])
    finally:
        rechter.waarnemer = None
    assert gezien == [[("c0", 0.95, 0.4, None), ("c1", 0.90, 0.7, None)]]


def test_the_watcher_also_sees_where_the_number_and_negation_rule_steps_in():
    gezien = []
    rechter.waarnemer = gezien.append
    try:
        rechter.herorden(_conn(), _config(diepte=2), "vraag", KANDIDATEN, scorer=lambda v, t: [0.4, 0.7],
                         tegenspraak=lambda tekst: tekst == "tekst 1")
    finally:
        rechter.waarnemer = None
    assert gezien == [[("c0", 0.95, 0.4, False), ("c1", 0.90, 0.7, True)]]
