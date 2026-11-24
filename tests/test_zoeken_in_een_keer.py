"""Alle eenheden van een artikel in één matrixproduct (#30.11).

Twaalf zinnen los zoeken leest de matrix van claims en varianten twaalf keer
(p95 223 ms per keer, §84). `search_texts` leest hem één keer en geeft per
vingerafdruk wat `search_text` zou geven: dezelfde claims in dezelfde
volgorde, elke claim één keer, met de variant waarlangs hij kwam.
"""

import numpy as np
import pytest

from doublecheck.embedding import TextFingerprint
from doublecheck.search import search_text, search_texts
from doublecheck.storage import connect, init_schema, save_text_fingerprint, save_variant

VERSIE = "testmodel-v1"


def _eenheid(rng):
    v = rng.normal(size=16).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def conn():
    rng = np.random.default_rng(3011)
    conn = connect(":memory:")
    init_schema(conn)
    for i in range(60):
        cid = f"c{i}"
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')", (cid, f"claim {i}"))
        save_text_fingerprint(conn, cid, TextFingerprint(_eenheid(rng), VERSIE))
        if i % 3 == 0:
            save_variant(conn, cid, "es", f"variante {i}", "claude-haiku-5-5", "vertalingen-v1",
                         TextFingerprint(_eenheid(rng), VERSIE))
    conn.commit()
    yield conn, [TextFingerprint(_eenheid(rng), VERSIE) for _ in range(7)]
    conn.close()


@pytest.mark.parametrize("varianten", [False, True])
def test_one_product_gives_what_each_search_alone_gives(conn, varianten):
    conn, vragen = conn
    samen = search_texts(conn, vragen, 5, varianten=varianten)
    assert len(samen) == len(vragen)
    for vraag, lijst in zip(vragen, samen):
        los = search_text(conn, vraag, 5, varianten=varianten)
        assert [k.claim_id for k in lijst] == [k.claim_id for k in los]
        assert [k.via for k in lijst] == [k.via for k in los]
        assert [k.similarity for k in lijst] == pytest.approx([k.similarity for k in los], abs=1e-6)


def test_no_units_means_no_search(conn):
    conn, _ = conn
    assert search_texts(conn, [], 5, varianten=True) == []
