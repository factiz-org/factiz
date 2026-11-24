"""Bewijstoestand telt over het cluster heen (E2.S5-AC3, AC5 — DR7)."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.evidence import build_evidence
from doublecheck.storage import connect, init_schema, save_text_fingerprint

VERSIE = "testmodel-v1"


def _fp(richting, versie=VERSIE):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=versie)


# Expliciet, zodat deze test niet meebeweegt met `uitgevers.json` (#17.7).
# Drie hosts die écht in `uitgevers.json` staan, zodat de API-test dezelfde
# weg loopt als productie. Nieuwscheckers stond hier eerst, maar heeft één
# check in het CC BY-corpus en hoort dus terecht niet in het register (#17.7).
_REGISTER = {
    "factly.in": "FACTLY",
    "dpa-factchecking.com": "dpa",
    "verafiles.org": "Vera Files",
}


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    leden = [
        ("nl-1", "Dit zijn beelden van de aardbeving in Turkije", "nl",
         "FACTLY", "https://factly.in/a", "2024-03-01"),
        ("de-1", "Das sind Bilder des Erdbebens in der Türkei", "de",
         "dpa-factchecking", "https://dpa-factchecking.com/de/1", "2023-11-15"),
        ("fr-1", "Ce sont des images du séisme en Turquie", "fr",
         "Vera Files", "https://verafiles.org/fr/1", "2024-01-20"),
    ]
    for claim_id, tekst, taal, uitgever, url, datum in leden:
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language, cluster_id)"
            " VALUES (?, ?, ?, 'cl-aardbeving')",
            (claim_id, tekst, taal),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, ?, 'onwaar', 'Onjuist', ?, ?, ?)",
            (claim_id, uitgever, url, datum, taal),
        )
    conn.commit()
    yield conn
    conn.close()


def test_evidence_counts_across_the_cluster(conn):
    bewijs = build_evidence(conn, "nl-1", register=_REGISTER, onbekend="telt-niet-mee")

    assert bewijs.check_count == 3
    assert bewijs.publisher_count == 3
    assert bewijs.languages == ("de", "fr", "nl")
    assert bewijs.oldest_date == "2023-11-15"
    assert bewijs.cluster_size == 3


def test_evidence_of_an_unclustered_claim_is_unchanged(conn):
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('los', 'Een losse bewering', 'nl')"
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language)"
        " VALUES ('los', 'Knack', 'onwaar', 'Onjuist', 'https://knack.be/1',"
        " '2024-05-05', 'nl')"
    )
    conn.commit()

    bewijs = build_evidence(conn, "los")

    assert bewijs.check_count == 1
    assert bewijs.cluster_size == 1


def test_matched_response_shows_cluster_size(conn):
    config = load_config()
    for claim_id, richting in [("nl-1", [1.0, 0.0]), ("de-1", [0.99, 0.14]),
                               ("fr-1", [0.98, 0.2])]:
        save_text_fingerprint(
            conn, claim_id, _fp(richting, config.model_versions.text_embedding)
        )
    conn.commit()

    def nep(text, model_version):
        return _fp([1.0, 0.0], model_version)

    api.app.dependency_overrides[api.get_conn] = lambda: conn
    origineel = api.fingerprint_text
    api.fingerprint_text = nep
    try:
        body = TestClient(api.app).post(
            "/resolve", json={"text": "Dit zijn beelden van de aardbeving in Turkije"}
        ).json()
    finally:
        api.fingerprint_text = origineel
        api.app.dependency_overrides.clear()

    assert body["category"] == "matched"
    # Het claim-ID blijft het dichtstbijzijnde lid (E5.S1-contract intact).
    assert body["claim"]["id"] == "nl-1"
    # Maar de bewijstoestand telt over het cluster.
    assert body["claim"]["cluster_size"] == 3
    assert body["evidence"]["publisher_count"] == 3
    assert body["evidence"]["languages"] == ["de", "fr", "nl"]
