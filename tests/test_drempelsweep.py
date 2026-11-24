"""Drempelsweep als besluitgereedschap (PLAN.md #7.4)."""

import numpy as np
import pytest

from doublecheck.benchmark import sweep_thresholds
from doublecheck.config import Thresholds
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, save_test_pair

VERSIE = "testmodel-v1"


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-a', 'een claim', 'nl')"
    )
    save_text_fingerprint(conn, "claim-a", _fp([1.0, 0.0]))
    # Een zelfde-paar op similariteit 0.8: gevonden bij drempel 0.75, niet bij 0.85.
    save_test_pair(conn, TestPair("claim-a", True, "vervorming", "nl",
                                  _fp([0.8, 0.6])))
    conn.commit()
    yield conn
    conn.close()


def test_sweep_reports_a_row_per_threshold(conn):
    rijen = sweep_thresholds(conn, VERSIE, matches=(0.75, 0.85),
                             related=0.70)

    assert [rij.text_match for rij in rijen] == [0.75, 0.85]
    assert all(rij.pairs == 1 for rij in rijen)


def test_lower_threshold_finds_more(conn):
    los, streng = sweep_thresholds(conn, VERSIE, matches=(0.75, 0.85),
                                   related=0.70)

    assert los.correct_matches == 1
    assert streng.correct_matches == 0


def test_sweep_does_not_change_config(conn):
    """Een sweep is een experiment, geen configwijziging (DR6)."""
    from doublecheck.config import load_config

    voor = load_config().thresholds
    sweep_thresholds(conn, VERSIE, matches=(0.75, 0.95), related=0.70)

    assert load_config().thresholds == voor


def test_sweep_refuses_when_nothing_is_measurable(conn):
    """Alles ongeldig is iets anders dan iets ongeldig: dan is er niets te
    meten en hoort dat een fout te zijn, geen lege tabel."""
    with pytest.raises(ValueError):
        sweep_thresholds(conn, VERSIE, matches=(0.60,), related=0.70)


def test_sweep_skips_thresholds_below_the_related_value_instead_of_crashing(conn):
    """Regressie: 12.5 zette `text_related` op 0,80, waarna de sweep op zijn
    eigen standaardwaarden (vanaf 0,75) omviel met een ValueError.

    Overslaan is hier juist, want zo'n combinatie is betekenisloos — maar het
    moet luid: stille afkapping leest als "alles gemeten" terwijl dat niet zo is.
    """
    rijen = sweep_thresholds(conn, VERSIE, matches=(0.75, 0.85, 0.90),
                             related=0.80)

    assert [rij.text_match for rij in rijen] == [0.85, 0.90]
