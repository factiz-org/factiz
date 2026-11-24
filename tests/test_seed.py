import pytest

from doublecheck.seed import load_seed, seed_database
from doublecheck.storage import connect, init_schema


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    yield conn
    conn.close()


def test_seed_loads_expected_claims(conn):
    total = conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"]
    assert total >= 20

    dutch = conn.execute(
        "SELECT COUNT(*) AS n FROM claim WHERE language = 'nl'"
    ).fetchone()["n"]
    assert dutch >= 5

    paar = {
        row["claim_id"]: row["canonical_text"]
        for row in conn.execute(
            "SELECT claim_id, canonical_text FROM claim WHERE claim_id IN (?, ?)",
            ("seed-jansen-afgetreden", "seed-jansen-niet-afgetreden"),
        )
    }
    assert set(paar) == {"seed-jansen-afgetreden", "seed-jansen-niet-afgetreden"}
    assert "niet" not in paar["seed-jansen-afgetreden"]
    assert "niet" in paar["seed-jansen-niet-afgetreden"]

    oordelen = {
        row["claim_id"]: row["verdict_normalized"]
        for row in conn.execute(
            "SELECT claim_id, verdict_normalized FROM factcheck WHERE claim_id IN (?, ?)",
            ("seed-jansen-afgetreden", "seed-jansen-niet-afgetreden"),
        )
    }
    assert oordelen["seed-jansen-afgetreden"] == "onwaar"
    assert oordelen["seed-jansen-niet-afgetreden"] == "waar"

    meermaals_gecheckt = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        " SELECT claim_id FROM factcheck"
        " GROUP BY claim_id HAVING COUNT(DISTINCT publisher) >= 2)"
    ).fetchone()["n"]
    assert meermaals_gecheckt >= 1


def test_every_seed_claim_has_a_factcheck(conn):
    zonder_check = conn.execute(
        "SELECT claim.claim_id FROM claim"
        " LEFT JOIN factcheck ON factcheck.claim_id = claim.claim_id"
        " WHERE factcheck.factcheck_id IS NULL"
    ).fetchall()
    assert zonder_check == []


def test_seed_is_idempotent(conn):
    voor = conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"]
    seed_database(conn)
    na = conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"]
    assert na == voor
