"""Wat federatie nodig heeft, en wat wij ervan waarmaken (PROTOCOL 11.3).

Het besluit is *ontwerpen voor federatie, één instantie draaien*: één canonieke
resolver wint op dekking, maar de specificatie moet de gevallen dekken waar die
niet kan — privacy, soevereiniteit, een markt die wij niet doen. En het
dragende argument gaat de andere kant op dan je verwacht: **forkbaarheid is de
voorwaarde voor afhankelijkheid.** Niemand bouwt op iets wat hij niet kan
verlaten.

Twee dingen ontbraken daarvoor, en allebei zijn ze klein.

**Een antwoord zei niet wie het gaf.** §7 schrijft voor dat een client
antwoorden naast elkaar toont *met de bron erbij*. Zonder een veld dat de
resolver noemt, kan dat alleen zolang niemand een antwoord doorgeeft of bewaart.

**Claimidentiteit was een gelukkig toeval.** Onze claim-id's zijn afgeleid van
de claimtekst, dus twee resolvers met dezelfde tekst komen zonder overleg op
hetzelfde id uit — precies wat B16 zegt dat ClaimReview mist. Maar het stond
nergens opgeschreven, dus een tweede implementatie met willekeurige id's zou
federatie stilzwijgend breken.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.ingest import claim_id_for_text
from doublecheck.storage import connect, init_schema

KOP = "De zeespiegel daalt al tien jaar wereldwijd"


@pytest.fixture
def client():
    from doublecheck.embedding import fingerprint_text
    from doublecheck.storage import save_text_fingerprint

    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
        (claim_id_for_text(KOP), KOP),
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " (?, 'FACTLY', 'onwaar', 'Onjuist', 'https://factly.in/a', '2024-03-14',"
        " 'nl', 'datacommons-ccby')", (claim_id_for_text(KOP),))
    save_text_fingerprint(
        conn, claim_id_for_text(KOP),
        fingerprint_text(KOP, load_config().model_versions.text_embedding),
    )
    conn.commit()
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_the_same_text_gives_the_same_identity_without_coordination():
    """Dit is wat federatie draagt: geen register, geen autoriteit."""
    varianten = [
        KOP,
        KOP.upper(),
        f"  {KOP}  ",
        KOP.replace(" ", "  "),
    ]
    ids = {claim_id_for_text(v) for v in varianten}
    assert len(ids) == 1, f"dezelfde bewering, verschillende id's: {ids}"


def test_a_different_claim_gets_a_different_identity():
    assert claim_id_for_text(KOP) != claim_id_for_text("Bananen bevatten vitamine C")


def test_the_identity_is_the_digest_of_the_canonical_text():
    """De afleiding staat vast, anders kan een tweede implementatie hem niet
    naspelen. Prefix is lokaal; het cijfermerk erna is wat vergeleken wordt."""
    import hashlib
    import re

    genormaliseerd = re.sub(r"\s+", " ", KOP.strip().casefold())
    verwacht = hashlib.sha256(genormaliseerd.encode("utf-8")).hexdigest()[:16]
    assert claim_id_for_text(KOP).rsplit("-", 1)[1] == verwacht


def test_discovery_says_which_resolver_answered(client):
    document = client.get("/.well-known/doublecheck").json()
    config = load_config()
    assert document["resolver"]["id"] == config.resolver.id
    assert document["resolver"]["name"] == config.resolver.name
    assert document["claim_id"]["algorithm"] == "sha256"
    assert document["claim_id"]["preprocessing"] == ["strip", "collapse-whitespace", "casefold"]
    assert document["claim_id"]["hex_chars"] == 16


def test_every_answer_says_which_resolver_gave_it(client):
    """Zonder dit kan §7's "met de bron erbij" alleen zolang niemand het
    antwoord doorgeeft."""
    body = client.post("/resolve", json={"text": "Iets volstrekt onbekends"}).json()
    assert body["resolver"] == load_config().resolver.id


def test_a_matched_claim_id_can_be_recomputed_by_the_client(client):
    """De federatie-eigenschap, van buitenaf narekenbaar: het id van een
    teruggegeven claim volgt uit zijn eigen tekst."""
    body = client.post("/resolve", json={"text": KOP}).json()
    if body["category"] != "matched":
        pytest.skip("geen match in deze omgeving")
    claim = body["claim"]
    assert claim["id"] == claim_id_for_text(claim["text"])
