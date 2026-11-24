"""Additieve schemamigratie (defect gevonden bij taak 7.3).

`CREATE TABLE IF NOT EXISTS` raakt een bestaande tabel niet aan, dus een nieuwe
kolom bereikte een bestaande database nooit. Tot nu toe was de "oplossing" de
tabel droppen — onacceptabel zodra er betwistingen in staan die onder een
bewaartermijn en verwijderrecht vallen (DR9, B11).
"""

import sqlite3

import pytest

from doublecheck.storage import connect, init_schema


def test_missing_column_is_added_to_an_existing_database(tmp_path):
    pad = str(tmp_path / "oud.db")
    oud = connect(pad)
    # Een database zoals hij vóór taak 4.9 bestond: testpair zonder `kind`.
    oud.execute(
        "CREATE TABLE testpair ("
        " testpair_id INTEGER PRIMARY KEY, claim_id TEXT NOT NULL,"
        " is_same INTEGER NOT NULL, provenance TEXT NOT NULL,"
        " language TEXT NOT NULL, model_version TEXT NOT NULL,"
        " payload BLOB NOT NULL) STRICT"
    )
    oud.execute(
        "INSERT INTO testpair (claim_id, is_same, provenance, language,"
        " model_version, payload) VALUES ('c1', 1, 'origineel', 'nl', 'm1', x'00')"
    )
    oud.commit()
    oud.close()

    conn = connect(pad)
    init_schema(conn)

    kolommen = {rij["name"] for rij in conn.execute("PRAGMA table_info(testpair)")}
    assert {"numbers", "negations", "kind"} <= kolommen
    # En de bestaande rij is er nog — geen drop-and-recreate.
    rij = conn.execute("SELECT claim_id, kind FROM testpair").fetchone()
    assert rij["claim_id"] == "c1"
    assert rij["kind"] == "text"
    conn.close()


def test_migration_is_idempotent(tmp_path):
    pad = str(tmp_path / "herhaal.db")
    conn = connect(pad)
    init_schema(conn)
    init_schema(conn)
    init_schema(conn)

    kolommen = [rij["name"] for rij in conn.execute("PRAGMA table_info(testpair)")]
    assert len(kolommen) == len(set(kolommen))
    conn.close()


def test_migration_never_touches_dispute_data(tmp_path):
    """Betwistingen mogen nooit sneuvelen door een schemawijziging."""
    pad = str(tmp_path / "betwisting.db")
    conn = connect(pad)
    init_schema(conn)
    conn.execute(
        "INSERT INTO dispute (created_at, disputed_category, dispute_text)"
        " VALUES ('2026-08-29T10:00:00+00:00', 'matched', 'klopt niet')"
    )
    conn.commit()
    conn.close()

    conn = connect(pad)
    init_schema(conn)
    assert conn.execute("SELECT COUNT(*) AS n FROM dispute").fetchone()["n"] == 1
    conn.close()
