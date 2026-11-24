import sqlite3

import numpy as np
import pytest

from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import (
    TestPair,
    build_testset,
    load_test_pairs,
    save_test_pair,
    _negation_variant,
)
from tests.test_ingest import NEP

KANARIE = "KANARIE-9f3a het geheime artefact dat nergens mag belanden"


def _fingerprint(model_version="testmodel-v1"):
    vector = np.array([0.6, 0.8, 0.0], dtype=np.float32)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=model_version)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
        ("claim-a", "een corpusclaim", "nl"),
    )
    yield conn
    conn.close()


def test_testset_contains_no_artifacts(conn):
    # De artefact-kant (de kanarietekst) wordt gefingerprint en direct
    # weggegooid — alleen verwijzing, label, herkomst en fingerprint blijven.
    paar = TestPair(
        claim_id="claim-a",
        is_same=True,
        provenance="parafrase",
        language="nl",
        fingerprint=_fingerprint(),
    )
    save_test_pair(conn, paar)

    dump = "\n".join(conn.iterdump())
    assert "KANARIE-9f3a" not in dump
    assert "geheime artefact" not in dump

    kolommen = {
        rij["name"] for rij in conn.execute("PRAGMA table_info(testpair)")
    }
    assert kolommen == {
        "testpair_id",
        "claim_id",
        "is_same",
        "provenance",
        "language",
        "model_version",
        "payload",
        "numbers",
        "negations",
        "kind",
        # Hash over vaste proefteksten (#11.5) — draagt geen artefactinhoud.
        "derivation_version",
        # Eén van zes taalcodes (#12.4) — minder informatie dan `numbers`, dat
        # letterlijke getallen uit het artefact draagt en hier al staat.
        "artefact_language",
    }


def test_testpair_roundtrip(conn):
    met_signaturen = TextFingerprint(
        vector=_fingerprint().vector,
        model_version="testmodel-v2",
        numbers=frozenset({"17", "2015"}),
        negations=frozenset({"niet"}),
    )
    origineel = TestPair(
        claim_id="claim-a",
        is_same=False,
        provenance="lookalike:claim-a",
        language="en",
        fingerprint=met_signaturen,
    )
    save_test_pair(conn, origineel)

    paren = load_test_pairs(conn)
    assert len(paren) == 1
    paar = paren[0]
    assert paar.claim_id == "claim-a"
    assert paar.is_same is False
    assert paar.provenance == "lookalike:claim-a"
    assert paar.language == "en"
    assert paar.fingerprint.model_version == "testmodel-v2"
    assert np.array_equal(paar.fingerprint.vector, _fingerprint().vector)
    assert paar.fingerprint.numbers == frozenset({"17", "2015"})
    assert paar.fingerprint.negations == frozenset({"niet"})


def _synthetisch_corpus(conn, aantal_nl=20, aantal_en=10):
    """Corpus met genoeg materiaal voor alle paarsoorten: patronen én cijfers."""
    for i in range(aantal_nl):
        claim_id = f"nl-{i}"
        tekst = f"De heffing is {10 + i} procent gestegen in 20{15 + i % 10}"
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim_id, tekst, "nl"),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, ?, 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl')",
            (claim_id, f"Uitgever-{i % 2}", f"https://voorbeeld.nl/{claim_id}"),
        )
        save_text_fingerprint(conn, claim_id, NEP(tekst))
    for i in range(aantal_en):
        claim_id = f"en-{i}"
        tekst = f"The tax is {30 + i} percent higher than in 19{80 + i}"
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim_id, tekst, "en"),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, ?, 'onwaar', 'False', ?, '2024-01-01', 'en')",
            (claim_id, f"Publisher-{i % 2}", f"https://example.org/{claim_id}"),
        )
        save_text_fingerprint(conn, claim_id, NEP(tekst))
    conn.commit()


def test_testset_size_and_language_split(conn):
    _synthetisch_corpus(conn)

    rapport = build_testset(
        conn, NEP, total=50, language_shares={"nl": 0.6, "en": 0.4}
    )

    assert rapport.total == 50
    assert rapport.per_language == {"nl": 30, "en": 20}
    assert rapport.same_pairs > 0
    assert rapport.lookalike_pairs > 0
    assert rapport.same_pairs + rapport.lookalike_pairs == 50

    paren = load_test_pairs(conn)
    assert len(paren) == 50
    soorten = {paar.provenance.split(":")[0] for paar in paren}
    assert {"origineel", "vervorming", "ontkenning", "cijferwissel"} <= soorten


def test_rebuild_replaces_previous_testset(conn):
    _synthetisch_corpus(conn)

    build_testset(conn, NEP, total=40, language_shares={"nl": 0.5, "en": 0.5})
    build_testset(conn, NEP, total=30, language_shares={"nl": 0.5, "en": 0.5})

    assert len(load_test_pairs(conn)) == 30


def test_negation_variant_skips_already_negated_claims():
    assert _negation_variant("De belasting is gestegen", "nl") == (
        "De belasting is niet gestegen"
    )
    assert _negation_variant("The tax is higher", "en") == "The tax is not higher"
    assert _negation_variant("De belasting is niet gestegen", "nl") is None
    assert _negation_variant("Er is geen bewijs voor", "nl") is None
    # Frans bouwt sinds 11.3 wél een ontkenning; de beperking was een aanname
    # die het corpus weerlegde (BENCHMARK.md §20).
    assert _negation_variant("Les impôts sont élevés", "fr") == (
        "Les impôts ne sont pas élevés"
    )
    assert _negation_variant("Les impôts ne sont pas élevés", "fr") is None


def test_testpair_requires_existing_claim(conn):
    zwevend = TestPair(
        claim_id="bestaat-niet",
        is_same=True,
        provenance="origineel",
        language="nl",
        fingerprint=_fingerprint(),
    )

    with pytest.raises(sqlite3.IntegrityError):
        save_test_pair(conn, zwevend)
