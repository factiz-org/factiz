"""Kritieke afdwinging van DR4 (kritiek AC E3.S2, PLAN.md #1.6).

Onder de matchdrempel is de uitkomst nooit `matched` — ook niet als het de
enige kandidaat is. Deze tests horen te falen zodra iemand dat ooit breekt.
"""

from pathlib import Path

import numpy as np
import pytest

from doublecheck.categorize import Category, categorize
from doublecheck.config import Thresholds, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.search import search_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint


def test_below_threshold_never_matched():
    drempelparen = [(0.85, 0.70), (0.95, 0.94), (0.50, 0.20), (0.30, 0.10)]
    for match, related in drempelparen:
        drempels = Thresholds(text_match=match, text_related=related, image_same=10)
        onder_de_drempel = np.append(
            np.linspace(-1.0, match - 1e-6, 400),
            np.nextafter(match, -np.inf),
        )
        for similariteit in onder_de_drempel:
            uitkomst = categorize(float(similariteit), drempels)
            assert uitkomst.category != Category.MATCHED, (
                f"matched bij similariteit {similariteit!r} onder drempel {match}"
            )


def test_only_candidate_below_threshold_is_not_matched():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
        ("enige-kandidaat", "de enige claim in de index", "nl"),
    )
    opgeslagen = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    save_text_fingerprint(
        conn, "enige-kandidaat", TextFingerprint(opgeslagen, "testmodel-v1")
    )
    # cos(60°) = 0.5: ruim onder de echte matchdrempel uit config.
    query = np.array([0.5, np.sqrt(3) / 2, 0.0], dtype=np.float32)

    kandidaten = search_text(conn, TextFingerprint(query, "testmodel-v1"))
    assert len(kandidaten) == 1

    uitkomst = categorize(kandidaten[0].similarity, load_config().thresholds)
    assert uitkomst.category != Category.MATCHED
    conn.close()


def test_only_categorize_module_constructs_categorization():
    pakket = Path(__file__).parent.parent / "doublecheck"
    overtreders = [
        bestand.name
        for bestand in pakket.rglob("*.py")
        if bestand.name != "categorize.py"
        and "Categorization(" in bestand.read_text(encoding="utf-8")
    ]
    assert overtreders == [], (
        f"alleen categorize.py mag een Categorization bouwen, ook gevonden in: {overtreders}"
    )
