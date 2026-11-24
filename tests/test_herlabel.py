"""Taallabels corrigeren met de detector (PLAN.md #12.6, B14).

`ingest` neemt de taal uit het eerste factcheck-`languageCode`, en die bron is
aantoonbaar onbetrouwbaar: van de 57 claims gelabeld `en` waren er 6 werkelijk
Engels, 27 Nederlands en 20 Spaans (BENCHMARK.md §26a). De `en`-rij in de
benchmark meet daardoor vrijwel geen Engels — en per-marktcijfers zijn de kern
van B14.

Twee ontwerpregels, allebei omdat de detector óók niet onfeilbaar is:
- de uitgeversbewering wordt **bewaard**, niet overschreven, zodat elke correctie
  auditeerbaar en omkeerbaar is;
- twijfel verandert niets: bij `None` blijft het uitgeverslabel staan.
"""

import pytest

from doublecheck.reindex import reindex_languages
from doublecheck.storage import connect, init_schema

NEDERLANDS = "Het vaccin bevat microchips om mensen te volgen en te sturen"
ENGELS = "The vaccine contains microchips to track and control the people"
SPAANS = "La vacuna contiene microchips para rastrear y controlar a las personas"


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _claim(conn, claim_id, tekst, label):
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
        (claim_id, tekst, label),
    )


def test_a_disagreement_is_reported_not_applied(conn):
    """Signaleren, niet overschrijven — teruggedraaid na meting (§32).

    De eerste versie corrigeerde het label. Van de 126 correcties waren er 54
    aantoonbaar fout: Spaanse claims met een Duitse naam erin werden Duits. Op
    de uitgeverspagina's stond `<html lang="es">`; de bron had gelijk.
    """
    _claim(conn, "claim-a", NEDERLANDS, "en")

    rapport = reindex_languages(conn)

    assert rapport.gecorrigeerd == 1, "de tegenspraak hoort geteld te worden"
    rij = conn.execute("SELECT * FROM claim WHERE claim_id = 'claim-a'").fetchone()
    assert rij["language"] == "en", "maar het label blijft van de uitgever"


def test_the_publisher_claim_is_kept_for_audit(conn):
    """Overschrijven zonder spoor zou de correctie onnavolgbaar maken."""
    _claim(conn, "claim-a", NEDERLANDS, "en")

    reindex_languages(conn)

    rij = conn.execute("SELECT * FROM claim WHERE claim_id = 'claim-a'").fetchone()
    assert rij["language_reported"] == "en"
    assert rij["language"] == "en"


def test_a_correct_label_is_left_alone(conn):
    _claim(conn, "claim-a", ENGELS, "en")
    _claim(conn, "claim-b", SPAANS, "es")

    rapport = reindex_languages(conn)

    assert rapport.gecorrigeerd == 0
    for claim_id, verwacht in (("claim-a", "en"), ("claim-b", "es")):
        rij = conn.execute(
            "SELECT language FROM claim WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        assert rij["language"] == verwacht


def test_uncertainty_leaves_the_publisher_label_standing(conn):
    """De detector mag alleen spreken als hij het weet (§27c)."""
    _claim(conn, "claim-a", "Pfizer 2024", "en")

    rapport = reindex_languages(conn)

    assert rapport.gecorrigeerd == 0
    assert rapport.onbeslist == 1
    rij = conn.execute("SELECT language FROM claim WHERE claim_id = 'claim-a'").fetchone()
    assert rij["language"] == "en"


def test_running_twice_changes_nothing_more(conn):
    """Hervatbaar en idempotent, net als het herindexeren van fingerprints."""
    _claim(conn, "claim-a", NEDERLANDS, "en")

    eerste = reindex_languages(conn)
    tweede = reindex_languages(conn)

    assert eerste.gecorrigeerd == tweede.gecorrigeerd == 1
    rij = conn.execute("SELECT * FROM claim WHERE claim_id = 'claim-a'").fetchone()
    assert (rij["language"], rij["language_reported"]) == ("en", "en")


def test_a_second_pass_never_loses_the_original_report(conn):
    """`language_reported` blijft de úítgeversbewering, niet de vorige correctie."""
    _claim(conn, "claim-a", NEDERLANDS, "en")

    reindex_languages(conn)
    reindex_languages(conn)

    rij = conn.execute("SELECT * FROM claim WHERE claim_id = 'claim-a'").fetchone()
    assert rij["language_reported"] == "en"
    assert rij["language"] == "en"
