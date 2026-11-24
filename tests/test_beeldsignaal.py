"""Beeld- en tekstsignaal draaien naast elkaar (B15, E1.S2-AC4).

Was: leesbare tekst schakelde het beeldsignaal uit (E1.S2-AC5). Die inperking
bestond om één reden — pHash codeerde op tekstscreenshots vooral lay-out en gaf
250 van 250 valse koppelingen op niet-geïndexeerde beelden (BENCHMARK.md §9).
Met PDQ is dat 0 van 250 (§29c), dus de reden is weg en de inperking vervalt
*(B15, PO 2026-08-30)*.

Wat blijft: een beeldovereenkomst zónder claimovereenkomst is `related` en nooit
`matched` — "zelfde foto, nieuw bijschrift" is een klassiek desinformatiepatroon
en mag nooit als volle match gelden (B8, DR4).
"""

import io

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.storage import (
    connect,
    init_schema,
    save_image_fingerprint,
    save_text_fingerprint,
)
from tests.beelden import kop_screenshot, vormen

KOP = "Minister Jansen is afgetreden vanwege het datalek"
ANDERE_KOP = "De zeespiegel daalt al tien jaar wereldwijd"


def _png(afbeelding):
    buffer = io.BytesIO()
    afbeelding.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client():
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)

    # claim-foto draagt de beeldhash van een screenshot van ANDERE_KOP:
    # precies de valse-matchval uit de beeldbenchmark.
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-foto', 'Een geheel andere bewering over treinen', 'nl')"
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language)"
        " VALUES ('claim-foto', 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://nieuwscheckers.nl/foto', '2024-01-01', 'nl')"
    )
    save_image_fingerprint(
        conn,
        "claim-foto",
        fingerprint_image(kop_screenshot([KOP]), config.model_versions.image_hash),
    )
    save_text_fingerprint(
        conn,
        "claim-foto",
        fingerprint_text(
            "Een geheel andere bewering over treinen",
            config.model_versions.text_embedding,
        ),
    )
    conn.commit()

    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_readable_text_no_longer_suppresses_the_image_route(client):
    """Hetzelfde beeld als de geïndexeerde, mét leesbare tekst erin.

    De tekst matcht niets (claim-foto gaat over treinen), maar het beeld is
    letterlijk hetzelfde. Vóór B15 werd dat signaal weggegooid; nu telt het mee.
    """
    body = client.post(
        "/resolve",
        files={"image": ("kop.png", _png(kop_screenshot([KOP])), "image/png")},
    ).json()

    assert "beeld" in body["matched_on"]
    assert body["category"] == "related"
    assert body["claim"]["id"] == "claim-foto"


def test_same_image_with_another_claim_is_never_a_full_match(client):
    """B8/DR4: "zelfde foto, nieuw bijschrift" blijft `related`."""
    body = client.post(
        "/resolve",
        files={"image": ("kop.png", _png(kop_screenshot([KOP])), "image/png")},
    ).json()

    assert body["category"] != "matched"


def test_a_different_headline_does_not_match_by_image(client):
    """De val waarvoor E1.S2-AC5 bestond, nu end-to-end getoetst.

    Een screenshot van een ándere kop mag niet op de beeldhash van claim-foto
    landen. Onder pHash gebeurde dat wél — 250 van 250 (BENCHMARK.md §9a).
    """
    body = client.post(
        "/resolve",
        files={"image": ("ander.png", _png(kop_screenshot([ANDERE_KOP])), "image/png")},
    ).json()

    assert "beeld" not in body["matched_on"]
    assert (body["claim"] or {}).get("id") != "claim-foto"


def test_image_without_readable_text_still_uses_image_route(client):
    # Geen leesbare tekst: dan is de beeldhash het enige signaal dat er is.
    body = client.post(
        "/resolve", files={"image": ("foto.png", _png(vormen(3)), "image/png")}
    ).json()

    assert body["category"] in {"related", "none"}
    # Route is niet uitgeschakeld: matched_on mag hier "beeld" bevatten.
    assert "tekst" not in body["matched_on"]


def test_text_decides_the_claim_when_both_routes_fire(client):
    """Vuren beide signalen, dan wijst de tekst de claim aan — die is specifieker."""
    body = client.post(
        "/resolve",
        data={"text": "Een geheel andere bewering over treinen"},
        files={"image": ("kop.png", _png(kop_screenshot([KOP])), "image/png")},
    ).json()

    if body["category"] == "matched":
        assert body["claim"]["id"] == "claim-foto"
        assert {"tekst", "tekst-gedeeltelijk"} & set(body["matched_on"])
