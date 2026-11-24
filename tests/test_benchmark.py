import json

import numpy as np
import pytest

from doublecheck.benchmark import list_failures, record_run, run_benchmark
from doublecheck.config import ModelVersions, Thresholds
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, save_test_pair

VERSIE = "testmodel-v1"
DREMPELS = Thresholds(text_match=0.85, text_related=0.70, image_same=10)
VERSIES = ModelVersions(text_embedding=VERSIE, image_hash="phash-test-v1")


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    richtingen = {
        "claim-a": [1.0, 0.0, 0.0],
        "claim-b": [0.0, 1.0, 0.0],
        "claim-c": [0.0, 0.0, 1.0],
    }
    for claim_id, richting in richtingen.items():
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (claim_id, f"tekst van {claim_id}"),
        )
        save_text_fingerprint(conn, claim_id, _fp(richting))

    # 1. zelfde-paar, exact → matched op de juiste claim (dekking).
    save_test_pair(conn, TestPair("claim-a", True, "origineel", "nl", _fp([1, 0, 0])))
    # 2. zelfde-paar dat te ver afdrijft → none (gemist, geen fout).
    save_test_pair(conn, TestPair("claim-a", True, "inkorting", "nl",
                                  _fp([0.5, 0.5, 0.71])))
    # 3. zelfde-paar dat op de VERKEERDE claim matcht → verkeerde koppeling.
    save_test_pair(conn, TestPair("claim-a", True, "vervorming", "nl", _fp([0, 1, 0])))
    # 4. lijkend-maar-anders dat tóch matcht → verkeerde koppeling.
    save_test_pair(conn, TestPair("claim-a", False, "cijferwissel", "nl",
                                  _fp([1, 0, 0])))
    # 5. hardste-buur: artefact ís claim-a en mag zichzelf matchen — geen fout.
    save_test_pair(conn, TestPair("claim-b", False, "hardste-buur:claim-a", "nl",
                                  _fp([1, 0, 0])))
    yield conn
    conn.close()


def test_benchmark_counts_wrong_links_and_coverage(conn):
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)

    nl = resultaat.per_language["nl"]
    assert nl.pairs == 5
    assert nl.same_pairs == 3
    assert nl.lookalike_pairs == 2
    assert nl.wrong_links == 2
    assert nl.correct_matches == 1
    assert nl.dekking == pytest.approx(1 / 3)

    fouten = [uitkomst for uitkomst in resultaat.outcomes if uitkomst.fout]
    assert {fout.provenance for fout in fouten} == {"vervorming", "cijferwissel"}


def test_benchmark_refuses_stale_testset(conn):
    with pytest.raises(Exception) as fout:
        run_benchmark(conn, DREMPELS, "ander-model-v9")

    assert "testset" in str(fout.value) or "model" in str(fout.value)


def test_benchmark_records_thresholds(conn):
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)

    run_id = record_run(conn, DREMPELS, VERSIES, resultaat)

    rij = conn.execute(
        "SELECT * FROM benchmark_run WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert rij["text_match"] == DREMPELS.text_match
    assert rij["text_related"] == DREMPELS.text_related
    assert rij["image_same"] == DREMPELS.image_same
    assert rij["model_version_text"] == VERSIE
    assert rij["model_version_image"] == "phash-test-v1"
    assert rij["pairs"] == 5
    assert rij["wrong_links"] == 2
    assert rij["correct_matches"] == 1
    assert rij["started_at"]

    per_taal = json.loads(rij["results_per_language"])
    assert per_taal["nl"]["wrong_links"] == 2


def test_every_run_adds_its_own_record(conn):
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)
    andere_drempels = Thresholds(text_match=0.95, text_related=0.80, image_same=10)

    eerste = record_run(conn, DREMPELS, VERSIES, resultaat)
    tweede = record_run(conn, andere_drempels, VERSIES,
                        run_benchmark(conn, andere_drempels, VERSIE))

    assert tweede > eerste
    rijen = conn.execute(
        "SELECT text_match FROM benchmark_run ORDER BY run_id"
    ).fetchall()
    assert [rij["text_match"] for rij in rijen] == [0.85, 0.95]


def test_failures_are_listable(conn):
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)
    run_id = record_run(conn, DREMPELS, VERSIES, resultaat)

    fouten = list_failures(conn, run_id)

    assert len(fouten) == 2
    assert {fout.provenance for fout in fouten} == {"vervorming", "cijferwissel"}

    vervorming = next(f for f in fouten if f.provenance == "vervorming")
    assert vervorming.is_same is True
    assert vervorming.target_claim_id == "claim-a"
    assert vervorming.matched_claim_id == "claim-b"
    assert vervorming.similarity == pytest.approx(1.0, abs=1e-5)
    assert vervorming.target_text == "tekst van claim-a"
    assert vervorming.matched_text == "tekst van claim-b"


def test_failures_belong_to_their_run(conn):
    eerste = record_run(conn, DREMPELS, VERSIES,
                        run_benchmark(conn, DREMPELS, VERSIE))
    strenger = Thresholds(text_match=0.95, text_related=0.80, image_same=10)
    tweede = record_run(conn, strenger, VERSIES,
                        run_benchmark(conn, strenger, VERSIE))

    assert len(list_failures(conn, eerste)) == 2
    assert len(list_failures(conn, tweede)) == 2
    assert list_failures(conn, run_id=999) == []


def test_neighbour_pair_matching_its_own_anchor_is_no_error(conn):
    resultaat = run_benchmark(conn, DREMPELS, VERSIE)

    buur = [u for u in resultaat.outcomes if u.provenance.startswith("hardste-buur")]
    assert len(buur) == 1
    assert buur[0].category == "matched"
    assert buur[0].matched_claim_id == "claim-a"
    assert buur[0].fout is False
