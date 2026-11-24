"""Modelversie-guard (E2.S3-AC2, DR6, PLAN.md #2.6).

Een index die met een andere modelversie is gebouwd en niet herbouwd is, laat
de resolver luid weigeren — nooit stil `none` teruggeven omdat de zoeklaag
binnen een lege versie filtert.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.embedding import TextFingerprint
from doublecheck.search import ModelVersionMismatchError, ensure_index_matches_version
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint


def _fingerprint(model_version):
    vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    return TextFingerprint(vector=vector, model_version=model_version)


@pytest.fixture
def verouderde_index():
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    save_text_fingerprint(conn, "seed-zeespiegel", _fingerprint("verouderd-model-v1"))
    yield conn
    conn.close()


def test_resolver_refuses_on_version_mismatch(verouderde_index, monkeypatch):
    def embedder_mag_niet_draaien(*args, **kwargs):
        raise AssertionError("embedder aangeroepen ondanks versiemismatch")

    monkeypatch.setattr(api, "fingerprint_text", embedder_mag_niet_draaien)
    api.app.dependency_overrides[api.get_conn] = lambda: verouderde_index
    try:
        respons = TestClient(api.app).post(
            "/resolve", json={"text": "De zeespiegel daalt al tien jaar wereldwijd"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respons.status_code == 503
    body = respons.json()
    assert "category" not in body
    assert "verouderd-model-v1" in body["detail"]


def test_empty_index_is_not_a_mismatch():
    conn = connect(":memory:")
    init_schema(conn)

    ensure_index_matches_version(conn, "welke-versie-dan-ook")
    conn.close()


def test_index_with_current_version_passes(verouderde_index):
    save_text_fingerprint(
        verouderde_index, "seed-5g-vogels", _fingerprint("huidig-model-v2")
    )

    ensure_index_matches_version(verouderde_index, "huidig-model-v2")


def test_mismatch_error_names_both_versions(verouderde_index):
    with pytest.raises(ModelVersionMismatchError) as fout:
        ensure_index_matches_version(verouderde_index, "huidig-model-v2")

    melding = str(fout.value)
    assert "verouderd-model-v1" in melding
    assert "huidig-model-v2" in melding
