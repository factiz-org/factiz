"""`POST /dispute` zonder toestemming (E6.S3-AC1, AC2)."""

import io

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.storage import connect, init_schema
from tests.beelden import kop_screenshot

ARTEFACT = "Minister Jansen is afgetreden vanwege het datalek"
BETWISTING = "Dit is niet mijn bewering; de gevonden claim gaat over iets anders."


@pytest.fixture
def client_en_conn():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


def test_dispute_without_consent_stores_no_artifact(client_en_conn):
    client, conn = client_en_conn

    respons = client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
    })

    assert respons.status_code == 200
    body = respons.json()
    assert body["stored_artifact"] is False
    assert body["artifact_expires_at"] is None
    assert body["deletion_key"] is None

    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["artifact_bytes"] is None
    assert rij["consent_at"] is None
    # Het artefact is tekst: die tekst mag nergens in de rij staan (DR3).
    dump = "\n".join(conn.iterdump())
    assert "Jansen" not in dump
    assert "afgetreden" not in dump


def test_dispute_stores_fingerprint_category_and_text(client_en_conn):
    client, conn = client_en_conn

    client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "related",
        "dispute_text": BETWISTING,
        "claim_id": "gfc-abc123",
    })

    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["disputed_category"] == "related"
    assert rij["dispute_text"] == BETWISTING
    assert rij["claim_id"] == "gfc-abc123"
    assert rij["created_at"]
    assert rij["text_payload"] is not None
    assert rij["text_model_version"]


def test_absent_consent_counts_as_refusal(client_en_conn):
    """AC1: toestemming is expliciet; afwezigheid is weigering, geen default-ja."""
    client, conn = client_en_conn

    body = client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "none",
        "dispute_text": BETWISTING,
    }).json()

    assert body["stored_artifact"] is False
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM dispute WHERE consent_at IS NOT NULL"
    ).fetchone()["n"] == 0


def test_dispute_needs_text_and_valid_category(client_en_conn):
    client, _ = client_en_conn

    zonder_tekst = client.post("/dispute", json={
        "text": ARTEFACT, "disputed_category": "matched", "dispute_text": "  ",
    })
    assert zonder_tekst.status_code == 422

    onbekende_categorie = client.post("/dispute", json={
        "text": ARTEFACT, "disputed_category": "verzonnen", "dispute_text": BETWISTING,
    })
    assert onbekende_categorie.status_code == 422

    zonder_artefact = client.post("/dispute", json={
        "disputed_category": "matched", "dispute_text": BETWISTING,
    })
    assert zonder_artefact.status_code == 422


def test_caller_cannot_smuggle_extra_fields(client_en_conn):
    client, _ = client_en_conn

    respons = client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
        "artifact_bytes": "c21va2tlbA==",
    })

    assert respons.status_code == 422


def test_dispute_accepts_an_image(client_en_conn):
    client, conn = client_en_conn
    buffer = io.BytesIO()
    kop_screenshot([ARTEFACT]).save(buffer, format="PNG")

    respons = client.post(
        "/dispute",
        files={"image": ("kop.png", buffer.getvalue(), "image/png")},
        data={"disputed_category": "matched", "dispute_text": BETWISTING},
    )

    assert respons.status_code == 200
    assert respons.json()["stored_artifact"] is False
    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["image_hash"]
    assert rij["image_model_version"]
    assert rij["artifact_bytes"] is None
