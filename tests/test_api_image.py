import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint, fingerprint_text
from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.storage import (
    connect,
    init_schema,
    save_image_fingerprint,
    save_text_fingerprint,
)
from tests.beelden import jpeg_hercompressie, kop_screenshot, vormen

KOP = "Minister Jansen is afgetreden vanwege het datalek"


def _png(afbeelding):
    buffer = io.BytesIO()
    afbeelding.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client():
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)

    # Eén claim met tekst én beeld, één claim met alleen beeld.
    def _factcheck(claim_id, uitgever, url):
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, ?, 'onwaar', 'Onjuist', ?, '2025-01-20', 'nl')",
            (claim_id, uitgever, url),
        )

    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-jansen', ?, 'nl')",
        (KOP,),
    )
    _factcheck("claim-jansen", "Nieuwscheckers", "https://nieuwscheckers.nl/jansen")
    save_text_fingerprint(
        conn,
        "claim-jansen",
        fingerprint_text(KOP, config.model_versions.text_embedding),
    )
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-protest', 'De foto toont een protest in Den Haag', 'nl')"
    )
    _factcheck("claim-protest", "AFP Factcheck Nederland",
               "https://factchecknederland.afp.com/protest")
    save_image_fingerprint(
        conn,
        "claim-protest",
        fingerprint_image(vormen(1), config.model_versions.image_hash),
    )
    conn.commit()

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


def test_resolve_accepts_image(client):
    respons = client.post(
        "/resolve",
        files={"image": ("screenshot.png", _png(kop_screenshot([KOP])), "image/png")},
    )

    assert respons.status_code == 200
    body = respons.json()
    assert body["category"] in {"matched", "related", "assessed", "none"}
    assert _tel_categoriesleutels(body) == 1


def test_screenshot_of_known_headline_resolves_like_the_text(client):
    via_beeld = client.post(
        "/resolve",
        files={"image": ("kop.png", _png(kop_screenshot([KOP])), "image/png")},
    ).json()
    via_tekst = client.post("/resolve", json={"text": KOP}).json()

    assert via_beeld["category"] == via_tekst["category"] == "matched"
    assert via_beeld["claim"]["id"] == via_tekst["claim"]["id"] == "claim-jansen"
    assert "tekst" in via_beeld["matched_on"]
    assert via_beeld["evidence"] is not None


def test_same_image_different_claim_is_related_via_api(client):
    # Zelfde beeld als claim-protest (na hercompressie), geen leesbare tekst.
    respons = client.post(
        "/resolve",
        files={
            "image": (
                "foto.jpg",
                _png(jpeg_hercompressie(vormen(1), 60)),
                "image/jpeg",
            )
        },
    )

    body = respons.json()
    assert body["category"] == "related"
    assert body["claim"]["id"] == "claim-protest"
    assert body["matched_on"] == ["beeld"]
    assert body["evidence"] is None


def test_observed_source_is_reported_as_observed(client):
    afbeelding = kop_screenshot([KOP, "nieuwscheckers.nl"])

    body = client.post(
        "/resolve", files={"image": ("kop.png", _png(afbeelding), "image/png")}
    ).json()

    bronnen = body["observed_sources"]
    assert bronnen == [{"kind": "domein", "value": "nieuwscheckers.nl",
                        "status": "waargenomen"}]


def test_oversized_image_is_clear_error_not_none(client):
    respons = client.post(
        "/resolve",
        files={
            "image": ("groot.png", b"\x89PNG" + b"0" * api.MAX_IMAGE_BYTES,
                      "image/png")
        },
    )

    assert respons.status_code == 413
    assert "category" not in respons.json()


def test_unreadable_image_is_clear_error_not_none(client):
    respons = client.post(
        "/resolve",
        files={"image": ("kapot.png", b"dit is geen afbeelding", "image/png")},
    )

    assert respons.status_code == 422
    assert "category" not in respons.json()


def test_image_without_text_or_match_is_none(client):
    respons = client.post(
        "/resolve", files={"image": ("ruis.png", _png(vormen(42)), "image/png")}
    )

    body = respons.json()
    assert body["category"] == "none"
    assert body["claim"] is None
    assert body["matched_on"] == []
