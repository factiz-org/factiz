"""Datamodel voor betwistingen met de DR9-guard (E6.S3-AC5, AC7).

DR9: een bewaard artefact bestaat uitsluitend met toestemming, vervaldatum én
verwijdersleutel tegelijk. Dat wordt op schemaniveau afgedwongen, zodat geen
enkel codepad het kan omzeilen — dezelfde aanpak als DR1.
"""

import sqlite3

import pytest

from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

BASIS = (
    "2026-08-28T10:00:00+00:00",
    "matched",
    "Dit is niet dezelfde bewering als de mijne",
)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _betwisting(conn, *, artefact=None, toestemming=None, vervalt=None, sleutel=None):
    conn.execute(
        "INSERT INTO dispute (created_at, disputed_category, dispute_text,"
        " artifact_bytes, artifact_mime, consent_at, artifact_expires_at,"
        " deletion_key_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        BASIS + (artefact, "image/png" if artefact else None,
                 toestemming, vervalt, sleutel),
    )


def test_artifact_requires_consent_expiry_and_key(conn):
    compleet = {
        "artefact": b"\x89PNG-nep",
        "toestemming": "2026-08-28T10:00:00+00:00",
        "vervalt": "2026-11-26T10:00:00+00:00",
        "sleutel": "a" * 64,
    }

    # Alle drie aanwezig: mag.
    _betwisting(conn, **compleet)
    assert conn.execute("SELECT COUNT(*) AS n FROM dispute").fetchone()["n"] == 1

    # Elk van de drie afzonderlijk weglaten: de database weigert.
    for ontbrekend in ("toestemming", "vervalt", "sleutel"):
        onvolledig = dict(compleet, **{ontbrekend: None})
        with pytest.raises(sqlite3.IntegrityError):
            _betwisting(conn, **onvolledig)


def test_dispute_without_artifact_needs_no_consent(conn):
    """Zonder artefact is er niets te beschermen — de betwisting mag gewoon."""
    _betwisting(conn)

    rij = conn.execute("SELECT artifact_bytes, consent_at FROM dispute").fetchone()
    assert rij["artifact_bytes"] is None
    assert rij["consent_at"] is None


def test_dispute_columns_are_explicit(conn):
    """Schemawijziging dwingt een bewuste review af (zoals bij de testset)."""
    kolommen = {rij["name"] for rij in conn.execute("PRAGMA table_info(dispute)")}

    assert kolommen == {
        "dispute_id",
        "created_at",
        "disputed_category",
        "dispute_text",
        "claim_id",
        "text_model_version",
        "text_payload",
        "image_model_version",
        "image_hash",
        "consent_at",
        "artifact_expires_at",
        "deletion_key_hash",
        "artifact_bytes",
        "artifact_mime",
    }


def test_config_exposes_retention_period():
    """AC5: de bewaartermijn komt uit config, niet uit code (DR6)."""
    config = load_config()

    assert config.retention.artifact_days > 0
