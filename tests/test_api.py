import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

MATCHED_TEKST = "De zeespiegel daalt al tien jaar wereldwijd"
RELATED_TEKST = "De zeespiegel zakt al een decennium overal ter wereld"
NONE_TEKST = "Bananen bevatten meer vitamine C dan sinaasappels"


def _eenheid(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return vector


@pytest.fixture
def client(monkeypatch):
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)

    zeespiegel = _eenheid([1.0, 0.0, 0.0])
    save_text_fingerprint(
        conn,
        "seed-zeespiegel",
        TextFingerprint(zeespiegel, config.model_versions.text_embedding),
    )
    # Similariteit precies tussen de related- en matchdrempel in, wat de
    # configwaarden ook zijn.
    tussenin = (config.thresholds.text_match + config.thresholds.text_related) / 2
    richtingen = {
        MATCHED_TEKST: zeespiegel,
        RELATED_TEKST: _eenheid([tussenin, np.sqrt(1 - tussenin**2), 0.0]),
        NONE_TEKST: _eenheid([0.0, 0.0, 1.0]),
    }

    def nep_fingerprint(text, model_version):
        return TextFingerprint(richtingen[text], model_version)

    monkeypatch.setattr(api, "fingerprint_text", nep_fingerprint)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def _tel_categoriesleutels(obj):
    if isinstance(obj, dict):
        return sum(1 for sleutel in obj if sleutel == "category") + sum(
            _tel_categoriesleutels(waarde) for waarde in obj.values()
        )
    if isinstance(obj, list):
        return sum(_tel_categoriesleutels(item) for item in obj)
    return 0


def test_resolve_returns_exactly_one_category(client):
    verwacht = {
        MATCHED_TEKST: "matched",
        RELATED_TEKST: "related",
        NONE_TEKST: "none",
    }
    for tekst, categorie in verwacht.items():
        respons = client.post("/resolve", json={"text": tekst})
        assert respons.status_code == 200
        body = respons.json()
        assert body["category"] == categorie
        assert body["category"] in {"matched", "related", "assessed", "none"}
        assert _tel_categoriesleutels(body) == 1


def test_matched_response_contains_claim_similarity_and_evidence(client):
    body = client.post("/resolve", json={"text": MATCHED_TEKST}).json()

    assert body["category"] == "matched"
    assert body["claim"]["id"] == "seed-zeespiegel"
    assert body["similarity"] == pytest.approx(1.0, abs=1e-5)
    assert body["thresholds"]["text_match"] == load_config().thresholds.text_match

    bewijs = body["evidence"]
    assert body["claim"]["text"] == MATCHED_TEKST
    assert bewijs["check_count"] == 1
    check = bewijs["checks"][0]
    assert check["publisher"] == "Nieuwscheckers"
    assert check["review_date"] == "2024-03-14"
    assert check["url"]
    assert check["language"] == "nl"


def test_none_response_has_no_claim_and_no_evidence(client):
    body = client.post("/resolve", json={"text": NONE_TEKST}).json()

    assert body["category"] == "none"
    assert body["claim"] is None
    assert body["evidence"] is None


def test_unreadable_or_oversized_text_is_clear_error_not_none(client):
    leeg = client.post("/resolve", json={"text": "   "})
    assert leeg.status_code == 422
    assert "category" not in leeg.json()

    te_groot = client.post("/resolve", json={"text": "x" * (api.MAX_TEXT_LENGTH + 1)})
    assert te_groot.status_code == 413
    assert "category" not in te_groot.json()


def test_caller_cannot_request_a_match(client):
    respons = client.post(
        "/resolve", json={"text": NONE_TEKST, "force_match": True}
    )

    assert respons.status_code == 422


def test_response_impossible_without_category():
    assert api.ResolveResponse.model_fields["category"].is_required()

    with pytest.raises(ValidationError):
        api.ResolveResponse(
            claim=None,
            similarity=None,
            thresholds={"text_match": 0.85, "text_related": 0.7, "image_same": 10},
            evidence=None,
        )
