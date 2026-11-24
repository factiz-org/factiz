"""Elke markt draagt zijn eigen cijfer (PLAN.md B14-aanscherping).

B14 zei: een markt gaat live wanneer zijn benchmark bestaat en slaagt. De
ES-uitrol liet zien dat dat niet genoeg is — Frans ging van 0 naar 3 fouten en
Nederlands van 5 naar 8 zónder codewijziging, puur doordat de index
verdrievoudigde (BENCHMARK.md §22d). G1 hoort bij de índex, niet bij een taal.

Aangescherpt: bij elke uitbreiding worden álle markten opnieuw gemeten, en de
poort ligt op het totaalcijfer. Hier mechanisch afgedwongen, want de faalvorm is
stil: een markt die wel corpus heeft maar geen testparen levert géén cijfer op,
terwijl niets dat zegt.
"""

import numpy as np
import pytest

from doublecheck.benchmark import MarktZonderCijferError, run_benchmark
from doublecheck.config import Thresholds
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, save_test_pair

VERSIE = "testmodel-v1"
DREMPELS = Thresholds(text_match=0.90, text_related=0.80, image_same=10)


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for claim_id, taal in (("claim-nl", "nl"), ("claim-es", "es")):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim_id, f"tekst van {claim_id}", taal),
        )
        save_text_fingerprint(conn, claim_id, _fp([1.0, 0.0]))
    yield conn
    conn.close()


def test_a_market_with_corpus_but_no_pairs_is_refused(conn):
    """De stille faalvorm: markt bestaat, corpus bestaat, cijfer niet."""
    save_test_pair(conn, TestPair("claim-nl", True, "origineel", "nl", _fp([1.0, 0.0])))

    with pytest.raises(MarktZonderCijferError) as fout:
        run_benchmark(conn, DREMPELS, VERSIE)
    assert "es" in str(fout.value)


def test_all_markets_measured_passes(conn):
    for claim_id, taal in (("claim-nl", "nl"), ("claim-es", "es")):
        save_test_pair(
            conn, TestPair(claim_id, True, "origineel", taal, _fp([1.0, 0.0]))
        )

    resultaat = run_benchmark(conn, DREMPELS, VERSIE)
    assert set(resultaat.per_language) >= {"nl", "es"}


def test_a_market_without_corpus_is_not_demanded(conn):
    """Een markt zonder corpus is nog niet uitgerold; die hoeft geen cijfer."""
    conn.execute("DELETE FROM claim WHERE language = 'es'")
    save_test_pair(conn, TestPair("claim-nl", True, "origineel", "nl", _fp([1.0, 0.0])))

    run_benchmark(conn, DREMPELS, VERSIE)


def test_a_language_that_is_not_a_market_needs_no_number(conn):
    """Catalaans kwam mee met verificat.cat maar is geen markt (B14): het zit in
    de index zonder precisiebelofte, dus het hoeft geen benchmarkrij."""
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-ca', 'text', 'ca')"
    )
    save_text_fingerprint(conn, "claim-ca", _fp([0.0, 1.0]))
    for claim_id, taal in (("claim-nl", "nl"), ("claim-es", "es")):
        save_test_pair(
            conn, TestPair(claim_id, True, "origineel", taal, _fp([1.0, 0.0]))
        )

    run_benchmark(conn, DREMPELS, VERSIE)
