import numpy as np
import pytest

from doublecheck.embedding import TextFingerprint
from doublecheck.search import search_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint


def _fingerprint(richting, model_version="testmodel-v1"):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=model_version)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for claim_id in ("claim-a", "claim-b", "claim-c"):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim_id, f"tekst van {claim_id}", "nl"),
        )
    yield conn
    conn.close()


def test_search_returns_nearest(conn):
    save_text_fingerprint(conn, "claim-a", _fingerprint([1.0, 0.0, 0.0]))
    save_text_fingerprint(conn, "claim-b", _fingerprint([0.0, 1.0, 0.0]))
    save_text_fingerprint(conn, "claim-c", _fingerprint([0.6, 0.8, 0.0]))

    kandidaten = search_text(conn, _fingerprint([1.0, 0.0, 0.0]), limit=2)

    assert [k.claim_id for k in kandidaten] == ["claim-a", "claim-c"]
    assert kandidaten[0].similarity == pytest.approx(1.0, abs=1e-5)
    assert kandidaten[1].similarity == pytest.approx(0.6, abs=1e-5)


def test_empty_index_returns_none(conn):
    kandidaten = search_text(conn, _fingerprint([1.0, 0.0, 0.0]))

    assert kandidaten == []


def test_search_never_compares_across_model_versions(conn):
    save_text_fingerprint(conn, "claim-a", _fingerprint([1.0, 0.0, 0.0], "model-v1"))
    save_text_fingerprint(conn, "claim-b", _fingerprint([1.0, 0.0, 0.0], "model-v2"))

    kandidaten = search_text(conn, _fingerprint([1.0, 0.0, 0.0], "model-v1"))

    assert [k.claim_id for k in kandidaten] == ["claim-a"]


def test_limit_caps_number_of_candidates(conn):
    save_text_fingerprint(conn, "claim-a", _fingerprint([1.0, 0.0, 0.0]))
    save_text_fingerprint(conn, "claim-b", _fingerprint([0.9, 0.1, 0.0]))
    save_text_fingerprint(conn, "claim-c", _fingerprint([0.8, 0.2, 0.0]))

    kandidaten = search_text(conn, _fingerprint([1.0, 0.0, 0.0]), limit=1)

    assert len(kandidaten) == 1
    assert kandidaten[0].claim_id == "claim-a"
