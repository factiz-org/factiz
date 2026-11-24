"""Bewaartermijn afdwingen op de betwistingsroute (E6.S3-AC3, B11).

Een artefact dat zijn vervaldatum heeft bereikt wordt gewist; de betwisting
zelf blijft bestaan met zijn fingerprint, categorie en tekst. Zo overleeft de
analysewaarde de bewaartermijn en het privacyrisico niet.

Het commando rapporteert uitsluitend aantallen, nooit inhoud (DR3).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def sweep_expired_artifacts(
    conn: sqlite3.Connection, now: datetime | None = None
) -> int:
    """Wist verlopen artefacten en geeft terug hoeveel er zijn gewist.

    Herhaalbaar: een tweede run vindt niets meer. De vervaldatum is inclusief —
    precies op de datum is de termijn verstreken.
    """
    moment = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    cursor = conn.execute(
        "UPDATE dispute SET artifact_bytes = NULL, artifact_mime = NULL"
        " WHERE artifact_bytes IS NOT NULL"
        "   AND artifact_expires_at IS NOT NULL"
        "   AND artifact_expires_at <= ?",
        (moment,),
    )
    conn.commit()
    return cursor.rowcount


def main() -> None:
    import argparse

    from doublecheck.config import load_config
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(
        description="Verlopen artefacten van betwistingen wissen"
    )
    parser.add_argument("--db", default="doublecheck.db")
    args = parser.parse_args()

    config = load_config()
    conn = connect(args.db)
    init_schema(conn)

    gewist = sweep_expired_artifacts(conn)
    resterend = conn.execute(
        "SELECT COUNT(*) AS n FROM dispute WHERE artifact_bytes IS NOT NULL"
    ).fetchone()["n"]
    betwistingen = conn.execute(
        "SELECT COUNT(*) AS n FROM dispute"
    ).fetchone()["n"]

    print(f"bewaartermijn: {config.retention.artifact_days} dagen")
    print(f"  artefacten gewist:            {gewist}")
    print(f"  artefacten nog bewaard:       {resterend}")
    print(f"  betwistingen totaal (blijven): {betwistingen}")
    conn.close()


if __name__ == "__main__":
    main()
