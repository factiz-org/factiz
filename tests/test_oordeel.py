"""De meetset en een eerste oordelaar voor laag 3 (PLAN #29.1, #29.2, B25).

Niets hiervan bereikt een gebruiker. De vraag is alleen: hoe goed kan de
engine oordelen over checks die hij nog niet kende? Twee eerlijkheden zitten
in de opzet: de toets is gescheiden in de tijd (leren van vroeger, toetsen op
later), en precisie wordt naast het basisniveau gezet, want factcheckers
kiezen vooral claims die onwaar blijken.
"""

import numpy as np
import pytest

from doublecheck import oordeel as od
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

MODEL = "testmodel-v1"


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _claim(conn, cid, vector, oordelen, datum, taal="en"):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
                 (cid, f"claim {cid}", taal))
    for i, o in enumerate(oordelen):
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                     " url, review_date, language) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (cid, f"P{i}", o, o, f"https://x/{cid}/{i}", datum, taal))
    save_text_fingerprint(conn, cid, TextFingerprint(vector=_v(*vector), model_version=MODEL))


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    _claim(c, "oud1", (1, 0, 0), ["onwaar"], "2024-01-01")
    _claim(c, "oud2", (0.95, 0.31, 0), ["onwaar"], "2024-02-01")
    _claim(c, "oud3", (0, 1, 0), ["waar"], "2024-03-01")
    _claim(c, "gemengd", (0, 0, 1), ["onwaar", "waar"], "2024-04-01")
    _claim(c, "onbekend", (0.5, 0.5, 0), ["onbekend"], "2024-05-01")
    _claim(c, "nieuw1", (0.99, 0.1, 0), ["onwaar"], "2026-01-01")
    _claim(c, "nieuw2", (0.1, 0.99, 0), ["onwaar"], "2026-02-01")
    c.commit()
    yield c
    c.close()


def test_the_set_is_split_in_time_and_keeps_only_unanimous_known_verdicts(conn):
    leer, toets = od.meetset(conn, MODEL, scheiding="2025-07-01")
    assert sorted(r.claim_id for r in leer) == ["oud1", "oud2", "oud3"]
    assert sorted(r.claim_id for r in toets) == ["nieuw1", "nieuw2"]


def test_the_neighbour_judge_abstains_when_neighbours_disagree_or_are_far(conn):
    leer, toets = od.meetset(conn, MODEL, scheiding="2025-07-01")
    uitkomst = od.knn_oordeel(toets, leer, k=2, drempel=0.5)
    per = {r.claim_id: u for r, u in zip(toets, uitkomst)}
    # nieuw1 ligt bij twee onware buren: oordeel onwaar.
    assert per["nieuw1"].voorspelling == "onwaar"
    # nieuw2 ligt bij een ware buur en een onware: geen eensgezindheid, dus geen oordeel.
    assert per["nieuw2"].voorspelling is None
    streng = od.knn_oordeel(toets, leer, k=1, drempel=0.999)
    assert all(u.voorspelling is None for u in streng)


def test_precision_is_reported_next_to_the_base_rate(conn):
    leer, toets = od.meetset(conn, MODEL, scheiding="2025-07-01")
    uitkomst = od.knn_oordeel(toets, leer, k=2, drempel=0.5)
    m = od.meet(toets, uitkomst, nieuw_onder=0.92)
    assert m["alle"]["basis_onwaar"] == 1.0
    assert m["alle"]["dekking"] == 0.5
    assert m["alle"]["precisie_onwaar"] == 1.0
    assert set(m) == {"alle", "bekend", "nieuw"}
