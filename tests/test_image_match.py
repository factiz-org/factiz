"""Zelfde beeld, andere bewering → `related` (E1.S2-AC4, E3.S2-AC2, B8)."""

import pytest

from doublecheck.categorize import Category, categorize
from doublecheck.config import Thresholds, load_config
from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.search import search_image
from doublecheck.storage import connect, init_schema, save_image_fingerprint
from tests.beelden import jpeg_hercompressie, vormen

VERSIE = "phash-64-v1"
DREMPELS = Thresholds(text_match=0.85, text_related=0.70, image_same=10)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for claim_id, tekst, seed in [
        ("claim-protest", "De foto toont een protest in Den Haag in 2023", 1),
        ("claim-brand", "De foto toont een brand in Rotterdam", 2),
    ]:
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, 'nl')",
            (claim_id, tekst),
        )
        save_image_fingerprint(conn, claim_id, fingerprint_image(vormen(seed), VERSIE))
    conn.commit()
    yield conn
    conn.close()


def test_same_image_different_claim_is_related(conn):
    # Hetzelfde beeld als claim-protest, maar het bijschrift beweert iets
    # anders — de tekstroute vindt niets.
    artefact = fingerprint_image(jpeg_hercompressie(vormen(1), 60), VERSIE)
    kandidaten = search_image(conn, artefact)

    assert kandidaten[0].claim_id == "claim-protest"

    uitkomst = categorize(
        None, DREMPELS, image_distance=kandidaten[0].distance
    )

    assert uitkomst.category == Category.RELATED
    assert uitkomst.category != Category.MATCHED
    assert "beeld" in uitkomst.matched_on
    assert "tekst" not in uitkomst.matched_on


def test_image_and_text_together_are_matched():
    uitkomst = categorize(0.97, DREMPELS, image_distance=0)

    assert uitkomst.category == Category.MATCHED
    assert set(uitkomst.matched_on) == {"tekst", "beeld"}


def test_partial_text_match_is_reported_as_partial():
    uitkomst = categorize(0.75, DREMPELS)

    assert uitkomst.category == Category.RELATED
    assert uitkomst.matched_on == ("tekst-gedeeltelijk",)


def test_distant_image_does_not_make_it_related(conn):
    vreemd = fingerprint_image(vormen(9), VERSIE)
    kandidaten = search_image(conn, vreemd)

    uitkomst = categorize(None, DREMPELS, image_distance=kandidaten[0].distance)

    assert uitkomst.category == Category.NONE
    assert uitkomst.matched_on == ()


def test_image_search_never_crosses_model_versions(conn):
    andere_versie = fingerprint_image(vormen(1), "phash-256-v1")

    assert search_image(conn, andere_versie) == []


def test_empty_image_index_returns_no_candidates():
    leeg = connect(":memory:")
    init_schema(leeg)

    assert search_image(leeg, fingerprint_image(vormen(1), VERSIE)) == []
    leeg.close()


def test_image_threshold_comes_from_config(conn):
    drempel = load_config().thresholds.image_same
    ruim_erbuiten = Thresholds(
        text_match=0.85, text_related=0.70, image_same=drempel
    )

    dichtbij = categorize(None, ruim_erbuiten, image_distance=drempel)
    eraf = categorize(None, ruim_erbuiten, image_distance=drempel + 1)

    assert dichtbij.category == Category.RELATED
    assert eraf.category == Category.NONE
