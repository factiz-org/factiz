"""Handgemaakte seed-claims: het dev-corpus voor de kernlus van etappe 1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SEED_PATH = Path(__file__).parent / "seed.json"


def load_seed(path: str | Path = SEED_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["claims"]


def seed_database(conn: sqlite3.Connection, path: str | Path = SEED_PATH) -> int:
    """Laadt de seed in de database; herladen maakt geen duplicaten."""
    claims = load_seed(path)
    for claim in claims:
        bestaat = conn.execute(
            "SELECT 1 FROM claim WHERE claim_id = ?", (claim["claim_id"],)
        ).fetchone()
        if bestaat:
            continue
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim["claim_id"], claim["canonical_text"], claim["language"]),
        )
        for check in claim["factchecks"]:
            conn.execute(
                "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
                " verdict_original, url, review_date, language)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    claim["claim_id"],
                    check["publisher"],
                    check["verdict_normalized"],
                    check["verdict_original"],
                    check["url"],
                    check["review_date"],
                    check["language"],
                ),
            )
    conn.commit()
    return len(claims)
