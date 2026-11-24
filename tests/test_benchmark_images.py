import pytest

from doublecheck.benchmark import run_benchmark
from doublecheck.benchmark_images import (
    build_image_pairs,
    build_synthetic_image_index,
    render_claim,
)
from doublecheck.config import Thresholds
from doublecheck.storage import connect, init_schema
from doublecheck.testset import load_test_pairs

VERSIE = "phash-64-v1"
DREMPELS = Thresholds(text_match=0.85, text_related=0.70, image_same=10)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for i in range(8):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, 'nl')",
            (f"claim-{i}", f"Bewering nummer {i} over het klimaat in Nederland"),
        )
    conn.commit()
    yield conn
    conn.close()


def test_render_claim_gives_a_readable_screenshot():
    afbeelding = render_claim("Minister Jansen is afgetreden")

    assert afbeelding.size[0] > 100
    assert afbeelding.mode == "RGB"


def test_synthetic_index_gives_every_claim_an_image_fingerprint(conn):
    aantal = build_synthetic_image_index(conn, VERSIE).toegevoegd

    assert aantal == 8
    rijen = conn.execute(
        "SELECT COUNT(*) AS n FROM fingerprint WHERE kind = 'image'"
    ).fetchone()
    assert rijen["n"] == 8


def test_image_pairs_carry_image_fingerprints(conn):
    build_synthetic_image_index(conn, VERSIE)

    rapport = build_image_pairs(conn, VERSIE, per_claim_limit=4)

    paren = load_test_pairs(conn)
    assert len(paren) == rapport.total
    assert all(paar.kind == "image" for paar in paren)
    soorten = {paar.provenance for paar in paren}
    assert soorten == {
        "beeld-origineel",
        "beeld-hercompressie",
        "beeld-bijsnijden",
        "beeld-onbekend",
    }


def test_image_pairs_are_scored_separately(conn):
    build_synthetic_image_index(conn, VERSIE)
    build_image_pairs(conn, VERSIE, per_claim_limit=4)

    resultaat = run_benchmark(conn, DREMPELS, VERSIE, image_model_version=VERSIE)

    assert "image" in resultaat.per_kind
    beeld = resultaat.per_kind["image"]
    assert beeld.pairs == len(load_test_pairs(conn))
    # Identieke en hercomprimeerde beelden horen teruggevonden te worden.
    per_soort = {
        uitkomst.provenance: uitkomst
        for uitkomst in resultaat.outcomes
        if uitkomst.provenance in ("beeld-origineel", "beeld-hercompressie")
    }
    assert per_soort["beeld-origineel"].fout is False
    assert per_soort["beeld-hercompressie"].fout is False


def test_unknown_image_is_not_matched(conn):
    build_synthetic_image_index(conn, VERSIE)
    build_image_pairs(conn, VERSIE, per_claim_limit=4)

    resultaat = run_benchmark(conn, DREMPELS, VERSIE, image_model_version=VERSIE)

    onbekend = [u for u in resultaat.outcomes if u.provenance == "beeld-onbekend"]
    assert onbekend
    assert all(uitkomst.fout is False for uitkomst in onbekend)
