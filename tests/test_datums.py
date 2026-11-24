"""Datumhygiëne op `review_date` (PLAN.md #21.4).

Het logboek van 21.2 ving "2923-01-02" als nieuwste check: 12,3% van de
feeddatums bleek ongeldig, en dezelfde waarden staan in de DR1-bonnetjes van
de resolver. Eén regel, op één plek (de import in `import_claims`), plus een
retro-schoonmaak voor wat er al staat.

De regel is mechanisch en verzint nooit een waarde: een datum is de kale
ISO-vorm, een echte kalenderdag, niet vóór het web (1995) en niet in de
toekomst — anders wordt het veld leeg (de bestaande "geen datum"-conventie
van het schema, dat `NOT NULL` is). "2-12-30" wordt dus níét "2012-12-30":
extraheren uit een tijdstempel mag, repareren is verzinnen (§58).
"""

from __future__ import annotations

from datetime import date

import pytest

from doublecheck.datums import geldige_review_datum, schoonmaak
from doublecheck.storage import connect, init_schema

VANDAAG = date(2026, 9, 2)


def test_a_valid_iso_date_passes_unchanged():
    assert geldige_review_datum("2024-03-14", vandaag=VANDAAG) == "2024-03-14"
    assert geldige_review_datum("1995-01-01", vandaag=VANDAAG) == "1995-01-01"
    # De grensdag zelf is geldig: een check van vandaag bestaat.
    assert geldige_review_datum("2026-09-02", vandaag=VANDAAG) == "2026-09-02"


def test_a_timestamp_keeps_only_its_date_part():
    """De Google-API levert RFC3339; de datum eruit halen is extraheren,
    geen verzinnen."""
    assert (
        geldige_review_datum("2021-03-03T09:00:00Z", vandaag=VANDAAG)
        == "2021-03-03"
    )


def test_missing_and_malformed_dates_become_empty_never_repaired():
    for waarde in (None, "", "  ", "2-12-30", "20204-08-0", "banaan",
                   "03-03-2021", "2021/03/03"):
        assert geldige_review_datum(waarde, vandaag=VANDAAG) == "", waarde


def test_an_impossible_calendar_date_is_refused():
    assert geldige_review_datum("2021-02-30", vandaag=VANDAAG) == ""
    assert geldige_review_datum("2021-13-01", vandaag=VANDAAG) == ""
    # Maar een echte schrikkeldag bestaat.
    assert geldige_review_datum("2024-02-29", vandaag=VANDAAG) == "2024-02-29"


def test_future_and_preweb_dates_are_refused():
    """"2923-01-02" en epoch-"1970-01-01" zijn de gemeten gevallen (§58)."""
    for waarde in ("2923-01-02", "2026-09-03", "1994-12-31", "1970-01-01",
                   "1936-12-11"):
        assert geldige_review_datum(waarde, vandaag=VANDAAG) == "", waarde


def test_cleanup_empties_only_the_corrupt_rows():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('c1', 'een claim', 'nl')"
    )
    rijen = [
        ("2024-03-14", "https://x.example/goed"),
        ("1970-01-01", "https://x.example/epoch"),
        ("2923-01-02", "https://x.example/toekomst"),
        ("", "https://x.example/leeg"),
    ]
    for datum, url in rijen:
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source) VALUES"
            " ('c1', 'p', 'onwaar', 'x', ?, ?, 'nl', 'datacommons-ccby')",
            (url, datum),
        )
    conn.commit()

    telling = schoonmaak(conn, vandaag=VANDAAG)

    assert telling.geleegd == 2
    assert telling.al_leeg == 1
    over = dict(conn.execute("SELECT url, review_date FROM factcheck"))
    assert over["https://x.example/goed"] == "2024-03-14"
    assert over["https://x.example/epoch"] == ""
    assert over["https://x.example/toekomst"] == ""
    assert over["https://x.example/leeg"] == ""


def test_cleanup_is_idempotent():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('c1', 'een claim', 'nl')"
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " ('c1', 'p', 'onwaar', 'x', 'https://x.example/a', '2923-01-02',"
        " 'nl', 'datacommons-ccby')"
    )
    conn.commit()
    assert schoonmaak(conn, vandaag=VANDAAG).geleegd == 1
    assert schoonmaak(conn, vandaag=VANDAAG).geleegd == 0


def test_the_import_refuses_a_corrupt_date_at_the_door():
    """Eén afdwingpunt: `import_claims` is de enige INSERT, dus feed- én
    API-import dragen de regel zonder eigen kopie."""
    import numpy as np

    from doublecheck.embedding import TextFingerprint
    from doublecheck.factchecktools import RawClaim, RawFactcheck
    from doublecheck.ingest import import_claims

    class _NepFingerprinter:
        model_version = "testmodel-v1"

        def __call__(self, tekst):
            vector = np.ones(3, dtype=np.float32) / np.sqrt(3)
            vector.setflags(write=False)
            return TextFingerprint(vector, self.model_version)

    conn = connect(":memory:")
    init_schema(conn)
    claims = [
        RawClaim(
            text="De zeespiegel daalt al tien jaar wereldwijd",
            claimant=None,
            claim_date=None,
            factchecks=(
                RawFactcheck(
                    publisher="Nieuwscheckers",
                    publisher_site="nieuwscheckers.nl",
                    url="https://nieuwscheckers.nl/zeespiegel",
                    review_date="2923-01-02",
                    verdict_original="Onjuist",
                    language="nl",
                ),
            ),
        )
    ]
    import_claims(conn, claims, fingerprinter=_NepFingerprinter(),
                  source="datacommons-ccby")

    datum, = conn.execute("SELECT review_date FROM factcheck").fetchone()
    assert datum == ""
