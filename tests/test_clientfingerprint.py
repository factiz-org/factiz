"""Het artefact hoeft het apparaat niet te verlaten — voor beeld (PROTOCOL 11.1).

PDQ is een DCT over een 64×64 verkleining: dat draait in een browser zonder
model. En beeld is juist de virale vorm. De privacybelofte uit DR3 — *"alleen
de fingerprint"* — is voor screenshots dus vandaag hard te maken, terwijl tekst
een eigen schema en een eigen benchmark vergt (§4).

Twee dingen worden hier vastgehouden.

**Ontdekking gaat vooraf.** Een fingerprint is schemaspecifiek, dus een client
moet eerst kunnen ópvragen welk schema deze resolver spreekt. Zonder §3 kan
§4 niet werken, en tot nu bestond §3 alleen op papier (§9).

**Een vreemd schema wordt luid geweigerd.** Dat was de stille faalvorm: de
beeldzoeker filtert op modelversie, dus een fingerprint van een ánder schema
leverde nul rijen en daarmee een keurige `none`. Verplichting 7 eist het
tegenovergestelde — weigeren, niet stil doorrekenen. Deze route maakt die helft
van de conformantietest voor het eerst waarneembaar.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.storage import connect, init_schema, save_image_fingerprint
from tests.beelden import kop_screenshot

KOP = "Minister Jansen is vanochtend afgetreden"


def _png(afbeelding) -> bytes:
    buffer = io.BytesIO()
    afbeelding.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client():
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-jansen', ?, 'nl')", (KOP,)
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " ('claim-jansen', 'FACTLY', 'onwaar', 'Onjuist', 'https://factly.in/a',"
        " '2024-03-14', 'nl', 'datacommons-ccby')"
    )
    beeld = _png(kop_screenshot([KOP]))
    save_image_fingerprint(
        conn, "claim-jansen",
        fingerprint_image(beeld, config.model_versions.image_hash),
    )
    conn.commit()
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), beeld
    api.app.dependency_overrides.clear()
    conn.close()


def test_discovery_tells_a_client_which_scheme_to_use(client):
    dienst, _ = client
    document = dienst.get("/.well-known/doublecheck").json()

    config = load_config()
    assert document["protocol"] == "0.1"
    beeldschemas = [s["id"] for s in document["schemes"]["image"]]
    assert beeldschemas == [config.model_versions.image_hash]
    assert document["schemes"]["image"][0]["encoding"] == "hex"
    # Zonder drempels kan een afnemer een antwoord niet narekenen (§2.8).
    assert document["thresholds"]["image_same"] == config.thresholds.image_same
    # Zonder scope kan hij een `none` niet lezen (§6).
    assert document["scope"]["claims"] == 1
    # `markets` en `languages` zijn niet hetzelfde, en dat is B14: een markt is
    # live als zijn eigen benchmark bestaat en slaagt, niet als zijn corpus
    # bestaat. Deze fixture heeft een Nederlandse claim en geen testparen, dus
    # de taal zit in de index en de markt is niet beloofd.
    assert document["scope"]["languages"] == ["nl"]
    assert document["scope"]["markets"] == []


def test_a_client_supplied_image_fingerprint_resolves_like_the_image(client):
    dienst, beeld = client
    config = load_config()
    hash_hex = fingerprint_image(beeld, config.model_versions.image_hash).hash_hex

    via_beeld = dienst.post(
        "/resolve", files={"image": ("kop.png", beeld, "image/png")}
    ).json()
    via_fingerprint = dienst.post("/resolve", json={
        "image_fingerprint": {
            "scheme": config.model_versions.image_hash, "hash": hash_hex
        }
    }).json()

    assert via_fingerprint["claim"]["id"] == via_beeld["claim"]["id"] == "claim-jansen"
    assert "beeld" in via_fingerprint["matched_on"]
    assert via_fingerprint["schemes_used"] == {
        "image": config.model_versions.image_hash
    }


def test_a_fingerprint_from_another_scheme_is_refused_out_loud(client):
    """De stille faalvorm: de zoeker filtert op versie, dus een vreemd schema
    gaf nul rijen en daarmee een nette `none` (§2.7)."""
    dienst, _ = client
    respons = dienst.post("/resolve", json={
        "image_fingerprint": {"scheme": "phash-64-v1", "hash": "00" * 8}
    })
    assert respons.status_code == 409
    detail = respons.json()["detail"]
    assert "phash-64-v1" in detail and load_config().model_versions.image_hash in detail


def test_a_fingerprint_that_is_not_a_hash_is_refused(client):
    dienst, _ = client
    versie = load_config().model_versions.image_hash
    for onzin in ("", "geen hex", "ab", "zz" * 32):
        respons = dienst.post("/resolve", json={
            "image_fingerprint": {"scheme": versie, "hash": onzin}
        })
        assert respons.status_code == 422, onzin


def test_the_fingerprint_route_never_sees_an_artifact(client):
    """Dat is het hele punt: er ís geen artefact om te bewaren (DR3)."""
    dienst, beeld = client
    versie = load_config().model_versions.image_hash
    hash_hex = fingerprint_image(beeld, versie).hash_hex
    respons = dienst.post("/resolve", json={
        "image_fingerprint": {"scheme": versie, "hash": hash_hex}
    })
    assert respons.status_code == 200
    # Geen OCR, dus ook geen waargenomen bronnen: er is niets om in te kijken.
    assert respons.json()["observed_sources"] == []
