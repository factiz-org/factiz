"""Incrementeel clusteren (PLAN #25.4).

Een volledige herbouw vermenigvuldigt alle vectoren met elkaar en liep de
laptop heet. Incrementeel: alleen nog niet bekeken claims, in porties, met
dezelfde regels als de herbouw (volledige koppeling, DR8 vóór het veto, nooit
twee clusters samenvoegen). Elke portie wordt apart vastgelegd, dus het is
hervatbaar.
"""

import numpy as np
import pytest

from doublecheck.clustering import (
    ClusterStateMismatchError,
    build_clusters,
    cluster_incrementeel,
    markeer_bekeken_volgens,
)
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

MODEL = "testmodel-v1"
DREMPEL = 0.93


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    v = v / np.linalg.norm(v)
    v.setflags(write=False)
    return v


def _claim(conn, cid, tekst, vector, taal="en"):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
                 (cid, tekst, taal))
    save_text_fingerprint(conn, cid, TextFingerprint(vector=vector, model_version=MODEL))


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    _claim(c, "a", "The vaccine contains a tracking microchip", _v(1, 0, 0, 0))
    _claim(c, "b", "Vaccines contain tracking microchips", _v(0.99, 0.14, 0, 0))
    _claim(c, "los", "The moon landing was staged in a studio", _v(0, 0, 1, 0))
    c.commit()
    build_clusters(c, MODEL, DREMPEL)
    yield c
    c.close()


def _cluster(conn, cid):
    return conn.execute("SELECT cluster_id FROM claim WHERE claim_id = ?", (cid,)).fetchone()[0]


def test_a_full_build_marks_every_claim_as_seen(conn):
    assert conn.execute("SELECT count(*) FROM claim WHERE cluster_bekeken = 0").fetchone()[0] == 0
    assert _cluster(conn, "a") == _cluster(conn, "b") is not None


def test_a_new_claim_joins_only_under_complete_linkage(conn):
    _claim(conn, "n1", "A tracking microchip is in the vaccine", _v(0.995, 0.07, 0, 0))   # dicht bij a én b
    _claim(conn, "n2", "The vaccine contains a chip", _v(0.96, -0.28, 0, 0))              # dicht bij a, niet bij b
    conn.commit()
    rapport = cluster_incrementeel(conn, MODEL, DREMPEL)
    assert _cluster(conn, "n1") == _cluster(conn, "a")
    assert _cluster(conn, "n2") is None
    assert rapport.aangesloten == 1 and rapport.geblokkeerd_koppeling >= 1
    assert conn.execute("SELECT count(*) FROM claim WHERE cluster_bekeken = 0").fetchone()[0] == 0


def test_new_claims_pair_with_an_old_loner_and_with_each_other(conn):
    _claim(conn, "n3", "The moon landing was filmed in a studio", _v(0.05, 0, 0.999, 0))
    _claim(conn, "n4", "Bill Gates created the virus", _v(0, 0, 0, 1))
    _claim(conn, "n5", "The virus was made by Bill Gates", _v(0, 0.02, 0, 0.9998))
    conn.commit()
    rapport = cluster_incrementeel(conn, MODEL, DREMPEL)
    assert _cluster(conn, "n3") == _cluster(conn, "los") is not None
    assert _cluster(conn, "n4") == _cluster(conn, "n5") is not None
    assert rapport.nieuwe_clusters == 2


def test_contradiction_and_veto_block_joining(conn):
    _claim(conn, "n6", "The vaccine does not contain a tracking microchip", _v(0.997, 0.05, 0, 0))
    _claim(conn, "n7", "The moon landing was filmed in a Hollywood studio", _v(0.04, 0, 0.999, 0))
    conn.commit()
    rapport = cluster_incrementeel(conn, MODEL, DREMPEL, veto=lambda a, b, ta, tb: "Hollywood" in a + b)
    assert _cluster(conn, "n6") is None          # DR8: negatieflip
    assert _cluster(conn, "n7") is None          # veto
    assert rapport.geblokkeerd_tegenspraak >= 1 and rapport.geblokkeerd_veto >= 1


def test_work_is_cut_in_portions_and_resumable(conn):
    for i in range(5):
        _claim(conn, f"p{i}", f"Unrelated claim number {i} about topic {i}", _v(*np.eye(4)[i % 4] + 0.01 * i))
    conn.commit()
    eerste = cluster_incrementeel(conn, MODEL, DREMPEL, portie=2, max_porties=1)
    assert eerste.verwerkt == 2 and eerste.resterend == 3
    tweede = cluster_incrementeel(conn, MODEL, DREMPEL, portie=2)
    assert tweede.verwerkt == 3 and tweede.resterend == 0


def test_it_refuses_a_state_built_with_other_settings(conn):
    _claim(conn, "n8", "Whatever", _v(0, 1, 0, 0))
    conn.commit()
    with pytest.raises(ClusterStateMismatchError):
        cluster_incrementeel(conn, MODEL, 0.95)


def test_claims_from_an_earlier_build_can_be_marked_as_seen(conn, tmp_path):
    """Eenmalig voor de bestaande database: wat in de vorige volledige bouw
    zat, is al bekeken; alleen wat erna kwam moet nog."""
    import shutil

    oud = tmp_path / "oud.db"
    schijf = connect(str(oud))
    init_schema(schijf)
    schijf.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('a', 'x', 'en')")
    schijf.commit()
    schijf.close()
    conn.execute("UPDATE claim SET cluster_bekeken = 0")
    gemarkeerd = markeer_bekeken_volgens(conn, str(oud))
    assert gemarkeerd == 1
    assert conn.execute("SELECT cluster_bekeken FROM claim WHERE claim_id='a'").fetchone()[0] == 1
    assert conn.execute("SELECT cluster_bekeken FROM claim WHERE claim_id='b'").fetchone()[0] == 0


def test_after_a_model_switch_the_clusters_start_over_and_build_incrementally(conn):
    """#25.14c: een nieuw model maakt de oude clusters ongeldig (DR6). Opnieuw
    beginnen wist toewijzingen en markeringen en legt de nieuwe toestand vast;
    daarna bouwt het incrementele pad, hervatbaar, alles opnieuw op."""
    from doublecheck.clustering import begin_opnieuw

    nieuw = "testmodel-v2"
    for cid, v in (("a", _v(1, 0, 0, 0)), ("b", _v(0.99, 0.14, 0, 0)), ("los", _v(0, 0, 1, 0))):
        save_text_fingerprint(conn, cid, TextFingerprint(vector=v, model_version=nieuw))
    with pytest.raises(ClusterStateMismatchError):
        cluster_incrementeel(conn, nieuw, 0.91)
    begin_opnieuw(conn, nieuw, 0.91, veto_version="")
    assert conn.execute("SELECT count(*) FROM claim WHERE cluster_id IS NOT NULL OR cluster_bekeken = 1"
                        ).fetchone()[0] == 0
    assert tuple(conn.execute("SELECT model_version, threshold, veto_version FROM cluster_state").fetchone()) \
        == (nieuw, 0.91, "")
    cluster_incrementeel(conn, nieuw, 0.91, portie=1)
    assert _cluster(conn, "a") == _cluster(conn, "b") is not None
    assert _cluster(conn, "los") is None
    assert conn.execute("SELECT count(*) FROM claim WHERE cluster_bekeken = 0").fetchone()[0] == 0
