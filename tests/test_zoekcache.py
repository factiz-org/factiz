"""De in-proces matrixcache onder de zoek (PLAN.md #22.1).

De 316 ms p95 van §53 zat niet in de wiskunde maar in het per-query opnieuw
laden en parsen van alle 80k payload-blobs. De cache houdt per verbinding één
matrix per (soort, modelversie) in het proces; SQLite blijft de bron van
waarheid.

Dit is de faalklasse die dit project vijf keer beet: **afgeleide staat die
veroudert zonder dat iets het merkt** (§17a, §39, §45, §46, §48c, §51d). De
verversingscheck — `PRAGMA data_version` plus `total_changes`, per aanroep —
is daarom het eigenlijke onderwerp van deze tests: elke route waarlangs de
index kan veranderen (eigen schrijfactie, ándere verbinding, update, delete)
moet de eerstvolgende zoek zichtbaar zijn. De uitkomsten zelf moeten
bit-identiek zijn aan brute force: zelfde volgorde, zelfde gelijkenis, ook
bij exacte gelijkstand.

De cache geldt alleen voor bestandsdatabases: bij `:memory:` staat
`data_version` stil en is er geen veilige verbindingsidentiteit (de suite
betrapte een id-hergebruik-botsing), dus daar blijft het brute force —
gelijk gedrag, geen cache. Deze tests draaien daarom op `tmp_path`.
"""

from __future__ import annotations

import numpy as np
import pytest

from doublecheck.embedding import TextFingerprint
from doublecheck.image_fingerprint import ImageFingerprint, hamming_distance
from doublecheck.search import (
    ensure_index_matches_version,
    ModelVersionMismatchError,
    search_image,
    search_text,
)
from doublecheck.storage import (
    connect,
    init_schema,
    save_image_fingerprint,
    save_text_fingerprint,
)

VERSIE = "testmodel-v1"


def _vector(zaad, dim=8):
    rng = np.random.default_rng(zaad)
    v = rng.normal(size=dim).astype(np.float32)
    v /= np.linalg.norm(v)
    v.setflags(write=False)
    return v


def _db(pad, n=12):
    conn = connect(pad)
    init_schema(conn)
    for i in range(n):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, 'nl')", (f"c{i:02d}", f"claim {i}"),
        )
        save_text_fingerprint(conn, f"c{i:02d}", TextFingerprint(_vector(i), VERSIE))
    conn.commit()
    return conn


def test_a_warm_search_reads_no_payloads(tmp_path):
    """Het mechanisme zelf: na de eerste zoek komt er geen payload-SELECT
    meer — alleen de goedkope verversingscheck."""
    conn = _db(str(tmp_path / "zoek.db"))
    search_text(conn, TextFingerprint(_vector(100), VERSIE))
    gezien = []
    conn.set_trace_callback(gezien.append)
    search_text(conn, TextFingerprint(_vector(101), VERSIE))
    conn.set_trace_callback(None)
    payload_reads = [s for s in gezien if "payload" in s.lower()]
    assert payload_reads == [], payload_reads


def test_cached_results_equal_brute_force_exactly(tmp_path):
    conn = _db(str(tmp_path / "zoek.db"), n=20)
    rows = conn.execute(
        "SELECT claim_id, payload FROM fingerprint WHERE kind='text'"
        " AND model_version=?", (VERSIE,)).fetchall()
    matrix = np.vstack([np.frombuffer(r["payload"], np.float32) for r in rows])
    for zaad in range(200, 210):
        fp = TextFingerprint(_vector(zaad), VERSIE)
        sims = matrix @ fp.vector
        volgorde = np.argsort(-sims, kind="stable")[:5]
        verwacht = [(rows[i]["claim_id"], float(sims[i])) for i in volgorde]
        # Tweemaal: koud (bouwt) en warm (cache) geven hetzelfde.
        for _ in range(2):
            uit = search_text(conn, fp)
            assert [(k.claim_id, k.similarity) for k in uit] == verwacht


def test_an_exact_tie_keeps_insertion_order(tmp_path):
    """Twee identieke vectoren: de volgorde is de opslagvolgorde, vóór en
    ná de cache (stabiele argsort over dezelfde rijvolgorde)."""
    conn = connect(str(tmp_path / "zoek.db"))
    init_schema(conn)
    for cid in ("eerst", "tweede"):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, 'zelfde tekst', 'nl')", (cid,))
        save_text_fingerprint(conn, cid, TextFingerprint(_vector(7), VERSIE))
    conn.commit()
    for _ in range(2):
        uit = search_text(conn, TextFingerprint(_vector(7), VERSIE), limit=2)
        assert [k.claim_id for k in uit] == ["eerst", "tweede"]


def test_an_insert_on_the_same_connection_is_seen_immediately(tmp_path):
    conn = _db(str(tmp_path / "zoek.db"), n=3)
    doel = TextFingerprint(_vector(999), VERSIE)
    assert search_text(conn, doel)[0].similarity < 0.99
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('nieuw', 'nieuwe claim', 'nl')")
    save_text_fingerprint(conn, "nieuw", TextFingerprint(_vector(999), VERSIE))
    beste = search_text(conn, doel)[0]
    assert beste.claim_id == "nieuw" and beste.similarity > 0.9999


def test_a_commit_from_another_connection_is_seen(tmp_path):
    pad = str(tmp_path / "zoek.db")
    a = _db(pad, n=3)
    doel = TextFingerprint(_vector(888), VERSIE)
    search_text(a, doel)  # warmt de cache van verbinding a
    b = connect(pad)
    b.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('elders', 'van een andere verbinding', 'nl')")
    save_text_fingerprint(b, "elders", TextFingerprint(_vector(888), VERSIE))
    b.commit()
    b.close()
    beste = search_text(a, doel)[0]
    assert beste.claim_id == "elders" and beste.similarity > 0.9999


def test_an_updated_vector_is_seen(tmp_path):
    conn = _db(str(tmp_path / "zoek.db"), n=3)
    doel = TextFingerprint(_vector(777), VERSIE)
    search_text(conn, doel)
    conn.execute(
        "UPDATE fingerprint SET payload = ? WHERE claim_id = 'c01'",
        (_vector(777).tobytes(),))
    beste = search_text(conn, doel)[0]
    assert beste.claim_id == "c01" and beste.similarity > 0.9999


def test_a_cascade_delete_is_seen(tmp_path):
    conn = _db(str(tmp_path / "zoek.db"), n=3)
    doel = TextFingerprint(_vector(1), VERSIE)
    assert search_text(conn, doel)[0].claim_id == "c01"
    conn.execute("DELETE FROM claim WHERE claim_id = 'c01'")
    assert all(k.claim_id != "c01" for k in search_text(conn, doel))


def test_model_versions_stay_separated(tmp_path):
    conn = _db(str(tmp_path / "zoek.db"), n=3)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('anders', 'andere versie', 'nl')")
    save_text_fingerprint(conn, "anders", TextFingerprint(_vector(5), "ander-model"))
    conn.commit()
    uit = search_text(conn, TextFingerprint(_vector(5), VERSIE))
    assert all(k.claim_id != "anders" for k in uit)
    uit_ander = search_text(conn, TextFingerprint(_vector(5), "ander-model"))
    assert [k.claim_id for k in uit_ander] == ["anders"]


def test_image_search_matches_the_reference_distance(tmp_path):
    """De gevectoriseerde hamming moet exact de referentie geven, in
    dezelfde volgorde (afstand, dan opslagvolgorde)."""
    rng = np.random.default_rng(42)
    conn = connect(str(tmp_path / "zoek.db"))
    init_schema(conn)
    hexen = [bytes(rng.integers(0, 256, 32, dtype=np.uint8)).hex() for _ in range(9)]
    for i, h in enumerate(hexen):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, 'beeldclaim', 'nl')", (f"b{i}",))
        save_image_fingerprint(
            conn, f"b{i}", ImageFingerprint(hash_hex=h, model_version="pdq-test", bits=256))
    conn.commit()
    query = ImageFingerprint(
        hash_hex=bytes(rng.integers(0, 256, 32, dtype=np.uint8)).hex(),
        model_version="pdq-test", bits=256)
    referentie = sorted(
        (hamming_distance(query, ImageFingerprint(h, "pdq-test", 256)), f"b{i}")
        for i, h in enumerate(hexen))
    for _ in range(2):  # koud en warm
        uit = search_image(conn, query, limit=9)
        assert [(k.distance, k.claim_id) for k in uit] == referentie


def test_the_version_guard_stays_fresh(tmp_path):
    """`ensure_index_matches_version` leunt op dezelfde verversingscheck:
    een nieuwe versie die ná het warmlopen verschijnt, telt direct mee."""
    conn = _db(str(tmp_path / "zoek.db"), n=2)
    ensure_index_matches_version(conn, VERSIE)  # warm
    with pytest.raises(ModelVersionMismatchError):
        ensure_index_matches_version(conn, "nog-niet-bestaand")
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('v2', 'nieuwe versie', 'nl')")
    save_text_fingerprint(conn, "v2", TextFingerprint(_vector(3), "nog-niet-bestaand"))
    ensure_index_matches_version(conn, "nog-niet-bestaand")  # nu wél aanwezig


def test_a_memory_database_stays_correct_without_the_cache():
    """Bij `:memory:` is er geen veilige verbindingsidentiteit, dus geen
    cache — maar het gedrag is identiek: brute force, direct vers."""
    conn = _db(":memory:", n=3)
    doel = TextFingerprint(_vector(555), VERSIE)
    search_text(conn, doel)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('vers', 'geheugendatabase', 'nl')")
    save_text_fingerprint(conn, "vers", TextFingerprint(_vector(555), VERSIE))
    assert search_text(conn, doel)[0].claim_id == "vers"


# --- Gedeeld over verbindingen (PLAN #25.14d b, BENCHMARK §77) -------------
#
# De API opent per vraag een verse verbinding. Met een cache per verbinding
# laadde elke vraag de hele index opnieuw: onder bge-m3 (109.600 x 1024) werd
# dat 4,1 s p50 in de belastingtest. De cache is nu per bestand; een eigen
# ongecommitte schrijfactie houdt een verbinding op haar eigen slot, zodat
# niemand anders die ziet.


def _payloadlezingen(conn, actie):
    gezien = []
    conn.set_trace_callback(gezien.append)
    try:
        actie()
    finally:
        conn.set_trace_callback(None)
    return [s for s in gezien if "payload" in s.lower()]


def test_a_fresh_connection_to_the_same_file_reuses_the_matrix(tmp_path):
    pad = str(tmp_path / "zoek.db")
    eerste = _db(pad)
    search_text(eerste, TextFingerprint(_vector(100), VERSIE))
    eerste.close()
    # Zoals de API: per vraag een nieuwe verbinding.
    for zaad in (101, 102):
        vraag = connect(pad)
        init_schema(vraag)
        assert _payloadlezingen(
            vraag, lambda: search_text(vraag, TextFingerprint(_vector(zaad), VERSIE))) == []
        vraag.close()


def test_an_uncommitted_write_never_leaks_to_another_connection(tmp_path):
    pad = str(tmp_path / "zoek.db")
    schrijver = _db(pad, n=3)
    doel = TextFingerprint(_vector(4242), VERSIE)
    search_text(schrijver, doel)
    schrijver.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('ongecommit', 'nog niet vastgelegd', 'nl')")
    save_text_fingerprint(schrijver, "ongecommit", TextFingerprint(_vector(4242), VERSIE))
    assert search_text(schrijver, doel)[0].claim_id == "ongecommit"  # eigen schrijfactie

    lezer = connect(pad)
    assert all(k.claim_id != "ongecommit" for k in search_text(lezer, doel))
    schrijver.commit()
    assert search_text(lezer, doel)[0].claim_id == "ongecommit"


def test_a_replaced_database_file_is_noticed(tmp_path):
    """Een nieuwe database op dezelfde plek (een uitrol doet `mv`) mag de
    oude matrix niet erven."""
    pad = tmp_path / "zoek.db"
    oud = _db(str(pad), n=3)
    doel = TextFingerprint(_vector(31337), VERSIE)
    search_text(oud, doel)
    oud.close()

    nieuw_pad = str(tmp_path / "nieuw.db")
    nieuw = _db(nieuw_pad, n=3)
    nieuw.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('vervangen', 'uit de nieuwe database', 'nl')")
    save_text_fingerprint(nieuw, "vervangen", TextFingerprint(_vector(31337), VERSIE))
    nieuw.commit()
    nieuw.close()
    (tmp_path / "nieuw.db").replace(pad)

    vraag = connect(str(pad))
    assert search_text(vraag, doel)[0].claim_id == "vervangen"


def test_parallel_cold_requests_load_the_index_once(tmp_path, monkeypatch):
    import threading

    from doublecheck import search as zoek

    pad = str(tmp_path / "zoek.db")
    _db(pad, n=20).close()
    bouwbeurten = []
    echt = zoek._tekstmatrix

    def geteld(conn, versie):
        bouwbeurten.append(versie)
        return echt(conn, versie)

    monkeypatch.setattr(zoek, "_tekstmatrix", geteld)
    start = threading.Barrier(4)

    def vraag(zaad):
        conn = connect(pad)
        start.wait()
        search_text(conn, TextFingerprint(_vector(zaad), VERSIE))
        conn.close()

    draden = [threading.Thread(target=vraag, args=(z,)) for z in range(4)]
    for d in draden:
        d.start()
    for d in draden:
        d.join()
    assert bouwbeurten == [VERSIE]
