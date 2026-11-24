"""Verwijderrecht: de indiener wist zijn eigen artefact (E6.S3-AC4, B11)."""

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.storage import connect, init_schema

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


def _betwist(client, toestemming=True):
    return client.post("/dispute", json={
        "text": ARTEFACT,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
        "consent_to_store_artifact": toestemming,
    }).json()


def _artefact(conn):
    return conn.execute("SELECT artifact_bytes FROM dispute").fetchone()["artifact_bytes"]


def test_deletion_key_removes_artifact(client_en_conn):
    client, conn = client_en_conn
    betwisting = _betwist(client)
    assert _artefact(conn) is not None

    respons = client.request(
        "DELETE",
        f"/dispute/{betwisting['dispute_id']}",
        json={"deletion_key": betwisting["deletion_key"]},
    )

    assert respons.status_code == 200
    assert respons.json()["artifact_present"] is False
    assert _artefact(conn) is None


def test_deletion_keeps_fingerprint_and_dispute_text(client_en_conn):
    """Het artefact verdwijnt, de analysewaarde blijft — dat is de afspraak."""
    client, conn = client_en_conn
    betwisting = _betwist(client)

    client.request("DELETE", f"/dispute/{betwisting['dispute_id']}",
                   json={"deletion_key": betwisting["deletion_key"]})

    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["artifact_bytes"] is None
    assert rij["artifact_mime"] is None
    assert rij["dispute_text"] == BETWISTING
    assert rij["text_payload"] is not None
    assert rij["disputed_category"] == "matched"


def test_wrong_key_leaves_artifact_untouched(client_en_conn):
    client, conn = client_en_conn
    betwisting = _betwist(client)

    respons = client.request(
        "DELETE",
        f"/dispute/{betwisting['dispute_id']}",
        json={"deletion_key": "niet-de-juiste-sleutel-maar-lang-genoeg-xxxxx"},
    )

    assert respons.status_code == 403
    assert _artefact(conn) is not None


def test_unknown_dispute_is_not_found(client_en_conn):
    client, _ = client_en_conn

    respons = client.request("DELETE", "/dispute/9999",
                             json={"deletion_key": "wat-dan-ook-lang-genoeg-xxxxxxx"})

    assert respons.status_code == 404


def test_deletion_is_idempotent(client_en_conn):
    client, conn = client_en_conn
    betwisting = _betwist(client)
    sleutel = {"deletion_key": betwisting["deletion_key"]}
    pad = f"/dispute/{betwisting['dispute_id']}"

    eerste = client.request("DELETE", pad, json=sleutel)
    tweede = client.request("DELETE", pad, json=sleutel)

    assert eerste.status_code == 200
    assert tweede.status_code == 200
    assert tweede.json()["artifact_present"] is False
    assert _artefact(conn) is None


def test_dispute_without_artifact_has_nothing_to_delete(client_en_conn):
    client, _ = client_en_conn
    betwisting = _betwist(client, toestemming=False)

    assert betwisting["deletion_key"] is None
    respons = client.request(
        "DELETE", f"/dispute/{betwisting['dispute_id']}",
        json={"deletion_key": "er-is-geen-sleutel-uitgegeven-xxxxxxxxx"},
    )
    assert respons.status_code == 403
