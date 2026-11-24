import sqlite3

import numpy as np
import pytest

from doublecheck.storage import connect, init_schema


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _insert_claim(conn, claim_id="claim-1"):
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
        (claim_id, "De zeespiegel daalt al tien jaar", "nl"),
    )


def _insert_factcheck(conn, claim_id="claim-1", publisher="Nieuwscheckers",
                      url="https://nieuwscheckers.nl/check/1", review_date="2024-05-01"):
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (claim_id, publisher, "onwaar", "Onjuist", url, review_date, "nl"),
    )


def test_schema_roundtrip(conn):
    _insert_claim(conn)
    _insert_factcheck(conn, publisher="Nieuwscheckers")
    _insert_factcheck(conn, publisher="AFP Factcheck",
                      url="https://factchecknederland.afp.com/check/9",
                      review_date="2024-06-12")
    vector = np.array([0.1, -0.5, 0.25, 1.0], dtype=np.float32)
    conn.execute(
        "INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
        " VALUES (?, ?, ?, ?)",
        ("claim-1", "text", "testmodel-v1", vector.tobytes()),
    )
    conn.commit()

    claim = conn.execute(
        "SELECT canonical_text, language FROM claim WHERE claim_id = ?", ("claim-1",)
    ).fetchone()
    assert claim["canonical_text"] == "De zeespiegel daalt al tien jaar"
    assert claim["language"] == "nl"

    publishers = {
        row["publisher"]
        for row in conn.execute(
            "SELECT publisher FROM factcheck WHERE claim_id = ?", ("claim-1",)
        )
    }
    assert publishers == {"Nieuwscheckers", "AFP Factcheck"}

    fingerprint = conn.execute(
        "SELECT kind, model_version, payload FROM fingerprint WHERE claim_id = ?",
        ("claim-1",),
    ).fetchone()
    assert fingerprint["kind"] == "text"
    assert fingerprint["model_version"] == "testmodel-v1"
    assert np.array_equal(
        np.frombuffer(fingerprint["payload"], dtype=np.float32), vector
    )


def test_factcheck_without_url_or_date_is_rejected(conn):
    _insert_claim(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_factcheck(conn, url=None)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_factcheck(conn, review_date=None)


def test_factcheck_requires_existing_claim(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_factcheck(conn, claim_id="bestaat-niet")


def test_same_claim_same_url_gets_no_second_factcheck(conn):
    _insert_claim(conn)
    _insert_factcheck(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_factcheck(conn, review_date="2024-06-01")


def test_same_claim_same_model_gets_no_second_fingerprint(conn):
    _insert_claim(conn)
    args = ("claim-1", "text", "testmodel-v1", b"\x00\x01")
    sql = (
        "INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
        " VALUES (?, ?, ?, ?)"
    )
    conn.execute(sql, args)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, args)
