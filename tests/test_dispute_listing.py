"""Betwistingen als analysemateriaal (E6.S3-AC6)."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from doublecheck.dispute import delete_artifact, list_disputes, record_dispute
from doublecheck.embedding import TextFingerprint
from doublecheck.image_fingerprint import ImageFingerprint
from doublecheck.retention import sweep_expired_artifacts
from doublecheck.storage import connect, init_schema

NU = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
GEHEIM = b"dit is de artefactinhoud die nergens in een lijst mag opduiken"


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _tekst_fp():
    vector = np.array([0.6, 0.8], dtype=np.float32)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version="testmodel-v1")


def _beeld_fp():
    return ImageFingerprint(hash_hex="a1b2c3d4e5f60718", model_version="phash-64-v1", bits=64)


def test_disputes_are_listable_as_error_cases(conn):
    record_dispute(
        conn,
        disputed_category="matched",
        dispute_text="Dit is niet mijn bewering, de claim gaat over iets anders",
        claim_id="gfc-abc123",
        text_fingerprint=_tekst_fp(),
        now=NU,
    )
    record_dispute(
        conn,
        disputed_category="none",
        dispute_text="Deze claim is wél gecheckt, door Nieuwscheckers",
        image_fingerprint=_beeld_fp(),
        artifact=GEHEIM,
        artifact_mime="image/png",
        consent=True,
        retention_days=90,
        now=NU,
    )

    gevallen = list_disputes(conn)

    assert len(gevallen) == 2
    eerste, tweede = gevallen
    assert eerste.disputed_category == "matched"
    assert eerste.claim_id == "gfc-abc123"
    assert eerste.dispute_text.startswith("Dit is niet mijn bewering")
    assert eerste.has_text_fingerprint is True
    assert eerste.has_image_fingerprint is False
    assert eerste.has_artifact is False

    assert tweede.disputed_category == "none"
    assert tweede.has_image_fingerprint is True
    assert tweede.has_artifact is True
    assert tweede.artifact_expires_at


def test_listing_never_exposes_artifact_content(conn):
    record_dispute(
        conn, disputed_category="matched", dispute_text="fout",
        text_fingerprint=_tekst_fp(), artifact=GEHEIM, artifact_mime="text/plain",
        consent=True, retention_days=90, now=NU,
    )

    gevallen = list_disputes(conn)

    velden = " ".join(str(waarde) for waarde in gevallen[0].__dict__.values())
    assert "artefactinhoud" not in velden
    assert not hasattr(gevallen[0], "artifact_bytes")


def test_listing_shows_artifact_gone_after_deletion(conn):
    betwisting = record_dispute(
        conn, disputed_category="related", dispute_text="fout",
        text_fingerprint=_tekst_fp(), artifact=GEHEIM, artifact_mime="text/plain",
        consent=True, retention_days=90, now=NU,
    )
    assert list_disputes(conn)[0].has_artifact is True

    delete_artifact(conn, betwisting.dispute_id, betwisting.deletion_key)

    geval = list_disputes(conn)[0]
    assert geval.has_artifact is False
    # Het foutgeval blijft bruikbaar zonder het artefact.
    assert geval.dispute_text == "fout"
    assert geval.has_text_fingerprint is True


def test_listing_shows_artifact_gone_after_expiry(conn):
    record_dispute(
        conn, disputed_category="matched", dispute_text="fout",
        text_fingerprint=_tekst_fp(), artifact=GEHEIM, artifact_mime="text/plain",
        consent=True, retention_days=90, now=NU - timedelta(days=100),
    )
    sweep_expired_artifacts(conn, now=NU)

    geval = list_disputes(conn)[0]
    assert geval.has_artifact is False
    assert geval.has_text_fingerprint is True


def test_listing_can_filter_on_stored_artifact(conn):
    record_dispute(conn, disputed_category="none", dispute_text="zonder",
                   text_fingerprint=_tekst_fp(), now=NU)
    record_dispute(conn, disputed_category="matched", dispute_text="met",
                   text_fingerprint=_tekst_fp(), artifact=GEHEIM,
                   artifact_mime="text/plain", consent=True, retention_days=90, now=NU)

    met_artefact = list_disputes(conn, only_with_artifact=True)

    assert len(met_artefact) == 1
    assert met_artefact[0].dispute_text == "met"
