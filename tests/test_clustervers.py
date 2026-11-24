"""Verse clusters voor het clusterbewuste cijfer (PLAN.md #12.3, DR6-analoog).

Aanleiding: de benchmark *leest* `claim.cluster_id` en bouwt niet. Het
clusterbewuste cijfer hing dus af van wanneer de clusters voor het laatst
gebouwd waren, zonder enige controle dat dat met de huidige drempel en
modelversie gebeurde. Bij etappe 12 sloeg dat cijfer daadwerkelijk even op
clusters van een ándere drempel (BENCHMARK.md §23e).

Dezelfde klasse fout als §19c, en dezelfde remedie: vastleggen waarmee gebouwd
is, en luid weigeren bij een mismatch. Het strikte cijfer raakt clusters niet en
blijft dus gewoon draaien — dat is het uitgangspunt (E2.S5-AC6).
"""

import numpy as np
import pytest

from doublecheck.benchmark import run_benchmark
from doublecheck.clustering import (
    ClusterStateMismatchError,
    build_clusters,
    ensure_clusters_match,
)
from doublecheck.config import Thresholds
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, save_test_pair

VERSIE = "testmodel-v1"
DREMPELS = Thresholds(text_match=0.85, text_related=0.70, image_same=10, cluster_same=0.90)


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for naam, richting in (("claim-a", [1.0, 0.0]), ("claim-b", [0.99, 0.14])):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (naam, f"tekst van {naam}"),
        )
        save_text_fingerprint(conn, naam, _fp(richting))
    save_test_pair(conn, TestPair("claim-a", True, "origineel", "nl", _fp([1.0, 0.0])))
    yield conn
    conn.close()


def test_unclustered_database_is_not_a_mismatch(conn):
    """De legitieme beginstand, net als bij een lege index en een lege testset."""
    ensure_clusters_match(conn, VERSIE, 0.90)


def test_fresh_clusters_pass_the_guard(conn):
    build_clusters(conn, VERSIE, 0.90)
    ensure_clusters_match(conn, VERSIE, 0.90)


def test_clusters_from_another_threshold_are_refused(conn):
    build_clusters(conn, VERSIE, 0.90)
    with pytest.raises(ClusterStateMismatchError) as fout:
        ensure_clusters_match(conn, VERSIE, 0.93)
    assert "0.9" in str(fout.value)


def test_clusters_from_another_model_version_are_refused(conn):
    build_clusters(conn, VERSIE, 0.90)
    with pytest.raises(ClusterStateMismatchError):
        ensure_clusters_match(conn, "ander-model-v2", 0.90)


def test_assignments_without_recorded_state_are_refused(conn):
    """Onbekende herkomst — precies het geval dat §23e liet misgaan."""
    build_clusters(conn, VERSIE, 0.90)
    conn.execute("DELETE FROM cluster_state")
    with pytest.raises(ClusterStateMismatchError):
        ensure_clusters_match(conn, VERSIE, 0.90)


def test_strict_benchmark_runs_without_any_clusters(conn):
    """Het strikte cijfer raakt clusters niet en mag er nooit op stuklopen."""
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)
    assert resultaat.totals.pairs == 1


def test_cluster_aware_benchmark_refuses_on_stale_clusters(conn):
    build_clusters(conn, VERSIE, 0.90)
    andere = Thresholds(
        text_match=0.85, text_related=0.70, image_same=10, cluster_same=0.95
    )
    with pytest.raises(ClusterStateMismatchError):
        run_benchmark(conn, andere, VERSIE, cluster_aware=True)


def test_cluster_aware_benchmark_runs_on_fresh_clusters(conn):
    build_clusters(conn, VERSIE, DREMPELS.cluster_same)
    resultaat = run_benchmark(conn, DREMPELS, VERSIE, cluster_aware=True)
    assert resultaat.totals.pairs == 1
