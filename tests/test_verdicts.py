import pytest

from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.feed import API_GEBONDEN
from doublecheck.ingest import import_claims
from doublecheck.seed import load_seed
from doublecheck.storage import connect, init_schema
from doublecheck.verdicts import NORMALIZED_CATEGORIES, normalize_verdict
from tests.test_ingest import NEP


def test_verdict_normalization_keeps_original():
    conn = connect(":memory:")
    init_schema(conn)
    import_claims(conn, fingerprinter=NEP, source=API_GEBONDEN, raw_claims=[
        RawClaim(
            text="Global warming stopped in 1998",
            claimant=None,
            claim_date=None,
            factchecks=(
                RawFactcheck(
                    publisher="PolitiFact",
                    publisher_site=None,
                    url="https://politifact.com/factchecks/x",
                    review_date="2020-11-19T00:00:00Z",
                    verdict_original="Pants on Fire",
                    language="en",
                ),
            ),
        )
    ])

    rij = conn.execute(
        "SELECT verdict_normalized, verdict_original FROM factcheck"
    ).fetchone()
    assert rij["verdict_normalized"] == "onwaar"
    assert rij["verdict_original"] == "Pants on Fire"
    conn.close()


def test_known_labels_fall_into_fixed_set():
    verwacht = {
        "False": "onwaar",
        "Pants on Fire": "onwaar",
        "Onwaar": "onwaar",
        "Onjuist": "onwaar",
        "Onzin": "onwaar",
        "True": "waar",
        "Waar": "waar",
        "Half True": "deels-waar",
        "Grotendeels onjuist": "deels-waar",
        "Mostly false": "deels-waar",
        "Misleading": "misleidend",
        "Missing Context": "misleidend",
        "Unproven": "onbewezen",
        "Labeled Satire": "onwaar",   # B56: satire alleen als vaststaat dat het als grap bedoeld is
    }
    for label, categorie in verwacht.items():
        assert normalize_verdict(label) == categorie, label
        assert categorie in NORMALIZED_CATEGORIES


def test_unknown_label_stays_onbekend():
    assert normalize_verdict("Vier Pinokkio's") == "onbekend"
    assert normalize_verdict("Sort of true-ish") == "onbekend"
    assert normalize_verdict("") == "onbekend"
    assert normalize_verdict(None) == "onbekend"
    # Substring-matchen zou hier "waar" raden — dat mag dus niet gebeuren.
    assert normalize_verdict("not true") == "onbekend"


def test_casing_and_punctuation_variants_match():
    assert normalize_verdict("FALSE.") == "onwaar"
    assert normalize_verdict("  false ") == "onwaar"
    assert normalize_verdict("Half-True") == "deels-waar"
    assert normalize_verdict("half_true") == "deels-waar"


def test_seed_verdicts_are_consistent_with_mapper():
    for claim in load_seed():
        for check in claim["factchecks"]:
            assert (
                normalize_verdict(check["verdict_original"])
                == check["verdict_normalized"]
            ), f"{claim['claim_id']}: {check['verdict_original']!r}"
