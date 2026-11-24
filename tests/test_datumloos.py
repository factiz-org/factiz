"""Factchecks zonder datum (PLAN.md #14.3, DR1 aangepast).

Bij de omzetting naar de CC BY-bron bleek 10,3% van de records geen
`datePublished` te dragen — 10.193 claims die we weigerden (BENCHMARK.md §36a).
De weigering was niet houdbaar: een factcheck zonder datum is nog steeds een
factcheck, met een aanwijsbare uitgever en een aanwijsbare URL.

DR1 eist voortaan bron-URL en uitgever; de datum wordt gerapporteerd wanneer hij
bekend is en anders expliciet als onbekend. Dat is eerlijker dan weigeren én
eerlijker dan een datum verzinnen.
"""

import pytest

from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.feed import API_GEBONDEN
from doublecheck.ingest import _weigergrond, import_claims
from doublecheck.storage import connect, init_schema


class _NepFingerprinter:
    model_version = "testmodel-v1"

    def __call__(self, tekst):
        import numpy as np

        from doublecheck.embedding import TextFingerprint

        vector = np.ones(3, dtype=np.float32) / np.sqrt(3)
        vector.setflags(write=False)
        return TextFingerprint(vector=vector, model_version="testmodel-v1")


def _check(**vervang):
    velden = dict(publisher="Nieuwscheckers", publisher_site="nieuwscheckers.nl",
                  url="https://nieuwscheckers.nl/a", review_date="2024-03-01",
                  verdict_original="Onjuist", language="nl")
    velden.update(vervang)
    return RawFactcheck(**velden)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def test_a_missing_date_is_no_longer_a_refusal():
    assert _weigergrond(_check(review_date=None)) is None


def test_publisher_and_url_are_still_required():
    """DR1 blijft staan op de twee velden die een bron aanwijsbaar maken."""
    assert _weigergrond(_check(publisher=None)) == "geen_uitgever"
    assert _weigergrond(_check(url=None)) == "geen_url"


def test_a_dateless_check_is_stored_with_an_empty_date(conn):
    claim = RawClaim(text="Het vaccin bevat microchips om mensen te volgen",
                     claimant=None, claim_date=None,
                     factchecks=(_check(review_date=None),))

    import_claims(conn, [claim], fingerprinter=_NepFingerprinter(),
                  source=API_GEBONDEN)

    rij = conn.execute("SELECT review_date FROM factcheck").fetchone()
    assert rij["review_date"] == ""


def test_evidence_reports_the_oldest_known_date(conn):
    """Een onbekende datum mag de oudste niet naar voren trekken."""
    from doublecheck.evidence import build_evidence

    claim = RawClaim(text="Het vaccin bevat microchips om mensen te volgen",
                     claimant=None, claim_date=None,
                     factchecks=(
                         _check(url="https://a.nl/1", review_date=None),
                         _check(url="https://a.nl/2", review_date="2021-06-02",
                                publisher="AFP"),
                     ))
    import_claims(conn, [claim], fingerprinter=_NepFingerprinter(),
                  source=API_GEBONDEN)
    claim_id = conn.execute("SELECT claim_id FROM claim").fetchone()["claim_id"]

    bewijs = build_evidence(conn, claim_id)

    assert bewijs.oldest_date == "2021-06-02"


def test_evidence_says_unknown_when_no_check_has_a_date(conn):
    """Niet verzinnen en niet leeg doen alsof: expliciet onbekend."""
    from doublecheck.evidence import build_evidence

    claim = RawClaim(text="Het vaccin bevat microchips om mensen te volgen",
                     claimant=None, claim_date=None,
                     factchecks=(_check(review_date=None),))
    import_claims(conn, [claim], fingerprinter=_NepFingerprinter(),
                  source=API_GEBONDEN)
    claim_id = conn.execute("SELECT claim_id FROM claim").fetchone()["claim_id"]

    assert build_evidence(conn, claim_id).oldest_date is None
