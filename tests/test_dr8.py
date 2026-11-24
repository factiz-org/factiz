"""Kritieke afdwinging DR8 (E3.S4, PLAN.md #3R.2).

Een vastgestelde tegenspraak resulteert nooit in `matched`, ongeacht de
similariteit — het Jansen-scenario uit de seed mag nooit meer de voordeur door.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.categorize import Category, categorize
from doublecheck.config import Thresholds, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.relation import extract_negations, extract_numbers
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

AFGETREDEN = "Minister Jansen is afgetreden vanwege het datalek"


def test_contradiction_never_matched():
    drempels = Thresholds(text_match=0.85, text_related=0.70, image_same=10)
    for similariteit in np.linspace(-1.0, 1.0, 201):
        uitkomst = categorize(float(similariteit), drempels, contradiction=True)
        assert uitkomst.category != Category.MATCHED, similariteit
    # Boven de matchdrempel degradeert een tegenspraak naar related, niet none.
    assert categorize(0.99, drempels, contradiction=True).category == Category.RELATED


@pytest.fixture
def client(monkeypatch):
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    richting = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    save_text_fingerprint(
        conn,
        "seed-jansen-niet-afgetreden",
        TextFingerprint(richting, config.model_versions.text_embedding),
    )

    def nep_fingerprint(text, model_version):
        # Embedding-nabijheid nagebootst (identieke richting), maar de
        # signaturen komen uit de échte extractie.
        return TextFingerprint(
            vector=richting,
            model_version=model_version,
            numbers=extract_numbers(text),
            negations=extract_negations(text),
        )

    monkeypatch.setattr(api, "fingerprint_text", nep_fingerprint)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_negation_flip_resolves_as_related_with_relation(client):
    body = client.post("/resolve", json={"text": AFGETREDEN}).json()

    assert body["category"] == "related"
    assert body["relation"] == "tegenspraak"
    assert body["claim"]["id"] == "seed-jansen-niet-afgetreden"
    assert body["evidence"] is None


def test_agreeing_artefact_still_matches_without_relation(client):
    body = client.post(
        "/resolve",
        json={"text": "Minister Jansen is niet afgetreden vanwege het datalek"},
    ).json()

    assert body["category"] == "matched"
    assert body["relation"] is None
