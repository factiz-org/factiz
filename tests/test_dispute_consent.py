"""Betwisting mét expliciete toestemming (E6.S3-AC4, DR9)."""

import hashlib
import io
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema
from tests.beelden import kop_screenshot

ARTEFACT = "Minister Jansen is afgetreden vanwege het datalek"
BETWISTING = "De resolver koppelde dit aan de verkeerde claim."


@pytest.fixture
def client_en_conn():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


def _beeld():
    buffer = io.BytesIO()
    kop_screenshot([ARTEFACT]).save(buffer, format="PNG")
    return buffer.getvalue()


def test_consented_dispute_stores_artifact_with_expiry(client_en_conn):
    client, conn = client_en_conn
    beeld = _beeld()

    body = client.post(
        "/dispute",
        files={"image": ("kop.png", beeld, "image/png")},
        data={
            "disputed_category": "matched",
            "dispute_text": BETWISTING,
            "consent_to_store_artifact": "true",
        },
    ).json()

    assert body["stored_artifact"] is True
    assert body["artifact_expires_at"]
    assert body["deletion_key"]

    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["artifact_bytes"] == beeld
    assert rij["artifact_mime"] == "image/png"
    # DR9: alle drie de voorwaarden staan er ook echt.
    assert rij["consent_at"]
    assert rij["artifact_expires_at"]
    assert rij["deletion_key_hash"]


def test_expiry_follows_the_configured_retention_period(client_en_conn):
    client, conn = client_en_conn
    dagen = load_config().retention.artifact_days

    client.post(
        "/dispute",
        files={"image": ("kop.png", _beeld(), "image/png")},
        data={
            "disputed_category": "matched",
            "dispute_text": BETWISTING,
            "consent_to_store_artifact": "true",
        },
    )

    rij = conn.execute(
        "SELECT consent_at, artifact_expires_at FROM dispute"
    ).fetchone()
    gegeven = datetime.fromisoformat(rij["consent_at"])
    vervalt = datetime.fromisoformat(rij["artifact_expires_at"])
    assert (vervalt - gegeven) == timedelta(days=dagen)


def test_deletion_key_is_stored_hashed_never_in_plain(client_en_conn):
    client, conn = client_en_conn

    body = client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
        "consent_to_store_artifact": True,
    }).json()

    sleutel = body["deletion_key"]
    assert len(sleutel) >= 32

    dump = "\n".join(conn.iterdump())
    assert sleutel not in dump, "verwijdersleutel staat leesbaar in de database"

    rij = conn.execute("SELECT deletion_key_hash FROM dispute").fetchone()
    assert rij["deletion_key_hash"] == hashlib.sha256(sleutel.encode()).hexdigest()


def test_text_artefact_is_the_text_itself(client_en_conn):
    """Bij een tekstbetwisting ís de tekst het artefact."""
    client, conn = client_en_conn

    client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "related",
        "dispute_text": BETWISTING,
        "consent_to_store_artifact": True,
    })

    rij = conn.execute("SELECT artifact_bytes, artifact_mime FROM dispute").fetchone()
    assert rij["artifact_bytes"].decode("utf-8") == ARTEFACT
    assert rij["artifact_mime"] == "text/plain"


def test_deletion_key_is_returned_only_once(client_en_conn):
    """De sleutel is niet opnieuw op te vragen — hij bestaat alleen gehasht."""
    client, conn = client_en_conn

    client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
        "consent_to_store_artifact": True,
    })

    kolommen = {rij["name"] for rij in conn.execute("PRAGMA table_info(dispute)")}
    assert "deletion_key" not in kolommen
    assert "deletion_key_hash" in kolommen
