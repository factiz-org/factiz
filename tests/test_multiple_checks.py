"""DR7 door de hele importketen (E2.S4, PLAN.md #2.7).

Checks van verschillende uitgevers, binnengekomen in verschillende
importruns, horen aan één claim_id te hangen — en telling, talen en oudste
datum zijn opvraagbaar als telling, niet als score.
"""

import pytest

from doublecheck.evidence import build_evidence
from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.feed import API_GEBONDEN
from doublecheck.ingest import import_claims
from doublecheck.storage import connect, init_schema
from tests.test_ingest import NEP

TEKST = "Het nieuwe EU-verdrag verbiedt contant geld vanaf 2027"


def _check(publisher, url, review_date, language="nl", verdict="Onwaar"):
    return RawFactcheck(
        publisher=publisher,
        publisher_site=None,
        url=url,
        review_date=review_date,
        verdict_original=verdict,
        language=language,
    )


def _claim(text, checks):
    return RawClaim(text=text, claimant=None, claim_date=None, factchecks=tuple(checks))


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)

    # Run 1: één uitgever ziet de claim.
    import_claims(conn, [
        _claim(TEKST, [
            _check("Nieuwscheckers", "https://nieuwscheckers.nl/factcheck/contant",
                   "2024-05-01T00:00:00Z"),
        ])
    ], fingerprinter=NEP, source=API_GEBONDEN)
    # Run 2 (latere corpus-sweep): dezelfde claim in andere casing, twee
    # andere uitgevers, waaronder een Engelstalige met een oudere datum.
    import_claims(conn, [
        _claim("het nieuwe eu-verdrag verbiedt contant geld vanaf 2027", [
            _check("AFP Factcheck Nederland",
                   "https://factchecknederland.afp.com/contant-geld",
                   "2023-11-15T00:00:00Z"),
            _check("Full Fact", "https://fullfact.org/europe/cash-ban",
                   "2024-01-10T00:00:00Z", language="en", verdict="False"),
        ])
    ], fingerprinter=NEP, source=API_GEBONDEN)

    yield conn
    conn.close()


def test_multiple_checks_one_claim_id(conn):
    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 1

    rijen = conn.execute(
        "SELECT DISTINCT claim_id, publisher FROM factcheck"
    ).fetchall()
    assert len({rij["claim_id"] for rij in rijen}) == 1
    assert {rij["publisher"] for rij in rijen} == {
        "Nieuwscheckers",
        "AFP Factcheck Nederland",
        "Full Fact",
    }


def test_count_languages_and_oldest_date_are_queryable(conn):
    claim_id = conn.execute("SELECT claim_id FROM claim").fetchone()["claim_id"]

    bewijs = build_evidence(conn, claim_id, register={}, onbekend="telt-mee")

    assert bewijs.check_count == 3
    assert bewijs.publisher_count == 3
    assert bewijs.languages == ("en", "nl")
    assert bewijs.oldest_date == "2023-11-15"
