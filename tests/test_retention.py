"""Bewaartermijn: verlopen artefacten verdwijnen, de betwisting blijft (E6.S3-AC3)."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from doublecheck.dispute import record_dispute
from doublecheck.embedding import TextFingerprint
from doublecheck.retention import sweep_expired_artifacts
from doublecheck.storage import connect, init_schema

BETWISTING = "De resolver koppelde dit aan de verkeerde claim."
NU = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _fingerprint():
    vector = np.array([0.6, 0.8], dtype=np.float32)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version="testmodel-v1")


def _betwisting(conn, *, dagen_geleden, bewaartermijn=90):
    return record_dispute(
        conn,
        disputed_category="matched",
        dispute_text=BETWISTING,
        text_fingerprint=_fingerprint(),
        artifact=b"het artefact",
        artifact_mime="text/plain",
        consent=True,
        retention_days=bewaartermijn,
        now=NU - timedelta(days=dagen_geleden),
    )


def _rij(conn, dispute_id):
    return conn.execute(
        "SELECT * FROM dispute WHERE dispute_id = ?", (dispute_id,)
    ).fetchone()


def test_expired_artifact_is_deleted_but_dispute_remains(conn):
    verlopen = _betwisting(conn, dagen_geleden=100)

    aantal = sweep_expired_artifacts(conn, now=NU)

    assert aantal == 1
    rij = _rij(conn, verlopen.dispute_id)
    assert rij["artifact_bytes"] is None
    assert rij["artifact_mime"] is None
    # De analysewaarde overleeft de bewaartermijn.
    assert rij["dispute_text"] == BETWISTING
    assert rij["text_payload"] is not None
    assert rij["disputed_category"] == "matched"


def test_artifact_within_the_period_is_kept(conn):
    vers = _betwisting(conn, dagen_geleden=10)

    aantal = sweep_expired_artifacts(conn, now=NU)

    assert aantal == 0
    assert _rij(conn, vers.dispute_id)["artifact_bytes"] is not None


def test_sweep_is_idempotent(conn):
    _betwisting(conn, dagen_geleden=100)

    eerste = sweep_expired_artifacts(conn, now=NU)
    tweede = sweep_expired_artifacts(conn, now=NU)

    assert (eerste, tweede) == (1, 0)


def test_sweep_only_touches_what_expired(conn):
    verlopen = _betwisting(conn, dagen_geleden=200)
    vers = _betwisting(conn, dagen_geleden=1)
    zonder = record_dispute(
        conn, disputed_category="none", dispute_text=BETWISTING,
        text_fingerprint=_fingerprint(), now=NU,
    )

    aantal = sweep_expired_artifacts(conn, now=NU)

    assert aantal == 1
    assert _rij(conn, verlopen.dispute_id)["artifact_bytes"] is None
    assert _rij(conn, vers.dispute_id)["artifact_bytes"] is not None
    assert _rij(conn, zonder.dispute_id)["artifact_bytes"] is None
    # Alle drie de betwistingen bestaan nog.
    assert conn.execute("SELECT COUNT(*) AS n FROM dispute").fetchone()["n"] == 3


def test_expiry_boundary_is_inclusive(conn):
    """Precies op de vervaldatum is de termijn verstreken."""
    op_de_grens = _betwisting(conn, dagen_geleden=90)

    assert sweep_expired_artifacts(conn, now=NU) == 1
    assert _rij(conn, op_de_grens.dispute_id)["artifact_bytes"] is None
