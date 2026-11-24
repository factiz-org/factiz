"""Claimvarianten in de index (PLAN #25.17, stap 5).

De varianten zijn vertalingen van claims, geschreven door een taalmodel en
gemeten in BENCHMARK §84. In de index zijn het extra vingerafdrukken van
dezelfde claim: de resolver zoekt over claims én varianten, maar een claim
komt maar één keer terug, met de beste gelijkenis van zijn rijen. Alleen met
de schakelaar `[varianten] in_resolver` aan, en een antwoord dat via een
vertaling kwam zegt dat (B12: narekenbaar).
"""

import dataclasses
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from doublecheck import variantenbatch as vb
from doublecheck.config import VariantSettings, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.search import (
    ModelVersionMismatchError,
    ensure_variants_match_version,
    search_text,
    variant_sets,
)
from doublecheck.storage import connect, init_schema, save_text_fingerprint, save_variant

VERSIE = "testmodel-v1"


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    v = v / np.linalg.norm(v)
    v.setflags(write=False)
    return v


def _db(pad=":memory:"):
    conn = connect(pad)
    init_schema(conn)
    for cid, tekst, taal, richting in (("A", "Bill Gates wants to chip everyone", "en", (1, 0, 0, 0)),
                                       ("B", "De zeespiegel daalt al tien jaar", "nl", (0, 1, 0, 0))):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)", (cid, tekst, taal))
        save_text_fingerprint(conn, cid, TextFingerprint(_v(*richting), VERSIE))
    # De Tamil-variant van A ligt bijna op de zoekvraag; A's eigen rij niet.
    save_variant(conn, "A", "ta", "பில் கேட்ஸ் அனைவருக்கும் சிப் பொருத்த விரும்புகிறார்",
                 "claude-haiku-5-5", "vertalingen-v1", TextFingerprint(_v(0, 0, 1, 0.05), VERSIE))
    save_variant(conn, "A", "es", "Bill Gates quiere ponerle un chip a todos",
                 "claude-haiku-5-5", "vertalingen-v1", TextFingerprint(_v(0.9, 0, 0.3, 0), VERSIE))
    conn.commit()
    return conn


@pytest.mark.parametrize("pad", [":memory:", "bestand"])
def test_a_claim_is_found_through_its_translation_and_returned_once(tmp_path, pad):
    conn = _db(str(tmp_path / "v.db") if pad == "bestand" else ":memory:")
    vraag = TextFingerprint(_v(0, 0, 1, 0), VERSIE)
    uit = search_text(conn, vraag, limit=5, varianten=True)
    assert [k.claim_id for k in uit] == ["A", "B"]                 # A één keer, ondanks drie rijen
    assert uit[0].similarity == pytest.approx(float(_v(0, 0, 1, 0.05) @ _v(0, 0, 1, 0)))
    assert uit[0].via == {"language": "ta", "generator": "claude-haiku-5-5", "prompt": "vertalingen-v1"}
    assert uit[1].via is None                                      # B via zijn eigen claimrij


def test_without_the_switch_the_variants_are_invisible():
    conn = _db()
    vraag = TextFingerprint(_v(0, 0, 1, 0), VERSIE)
    uit = search_text(conn, vraag, limit=5)
    assert [k.claim_id for k in uit] == ["A", "B"]
    assert uit[0].similarity == pytest.approx(0.0, abs=1e-6) and uit[0].via is None


def test_variants_of_another_model_version_are_never_compared():
    """DR6: een variant draagt de modelversie van zijn vingerafdruk."""
    conn = _db()
    save_variant(conn, "B", "en", "Sea level has been falling for ten years", "claude-haiku-5-5",
                 "vertalingen-v1", TextFingerprint(_v(0, 0, 1, 0), "ander-model"))
    uit = search_text(conn, TextFingerprint(_v(0, 0, 1, 0), VERSIE), varianten=True)
    assert uit[0].claim_id == "A"
    ensure_variants_match_version(conn, VERSIE)                    # er zijn er voor deze versie: goed
    with pytest.raises(ModelVersionMismatchError):
        ensure_variants_match_version(conn, "weer-een-ander-model")


def test_a_deleted_claim_takes_its_variants_along():
    conn = _db()
    conn.execute("DELETE FROM claim WHERE claim_id = 'A'")
    assert conn.execute("SELECT count(*) FROM claim_variant").fetchone()[0] == 0


def test_a_new_variant_is_seen_by_the_next_search(tmp_path):
    """De matrixcache (#22.1) geldt ook voor de varianten, en veroudert niet."""
    conn = _db(str(tmp_path / "v.db"))
    vraag = TextFingerprint(_v(0, 0, 0, 1), VERSIE)
    assert search_text(conn, vraag, varianten=True)[0].similarity < 0.5
    save_variant(conn, "B", "en", "Sea level has been falling for ten years", "claude-haiku-5-5",
                 "vertalingen-v1", TextFingerprint(_v(0, 0, 0, 1), VERSIE))
    conn.commit()
    beste = search_text(conn, vraag, varianten=True)[0]
    assert beste.claim_id == "B" and beste.similarity > 0.9999


def _regels(map_, claims):
    with (map_ / "regels.jsonl").open("w", encoding="utf-8") as uit:
        for cid in claims:
            uit.write(json.dumps({"claim_id": cid, "model": "claude-haiku-5-5", "prompt": "vertalingen-v1",
                                  "tokens": [1, 1], "geweigerd": False,
                                  "varianten": [{"soort": "vertaling", "taal": "en", "tekst": f"tekst van {cid}"}]})
                      + "\n")

    def vinger(teksten, versie):
        from types import SimpleNamespace
        return [SimpleNamespace(vector=_v(0, 0, 0, 1)) for _ in teksten]

    vb.embed(map_, VERSIE, vinger, portie=4)


def test_importing_is_repeatable_and_skips_claims_that_left_the_index(tmp_path):
    conn = _db()
    conn.execute("DELETE FROM claim_variant")
    _regels(tmp_path, ["A", "B", "verdwenen"])
    assert vb.importeer(conn, tmp_path, VERSIE) == 2
    assert vb.importeer(conn, tmp_path, VERSIE) == 2               # opnieuw: zelfde stand, niets dubbel
    rij = conn.execute("SELECT claim_id, language, text, generator, prompt_version, model_version"
                       " FROM claim_variant ORDER BY claim_id").fetchall()
    assert [tuple(r) for r in rij] == [("A", "en", "tekst van A", "claude-haiku-5-5", "vertalingen-v1", VERSIE),
                                       ("B", "en", "tekst van B", "claude-haiku-5-5", "vertalingen-v1", VERSIE)]


@pytest.fixture
def client(monkeypatch):
    import doublecheck.api as api

    config = load_config()
    versie = config.model_versions.text_embedding
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('A', ?, 'en')",
                 ("Bill Gates wants to put a microchip in everyone",))
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES ('A', 'FACTLY', 'onwaar', 'False', 'https://factly.in/a/',"
                 " '2024-01-01', 'en')")
    save_text_fingerprint(conn, "A", TextFingerprint(_v(1, 0, 0, 0), versie))
    save_variant(conn, "A", "ta", "பில் கேட்ஸ் அனைவருக்கும் மைக்ரோசிப் பொருத்த விரும்புகிறார்",
                 "claude-haiku-5-5", "vertalingen-v1", TextFingerprint(_v(0, 0, 1, 0), versie))
    conn.commit()
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, v: TextFingerprint(_v(0, 0, 1, 0), v))
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield api, config
    api.app.dependency_overrides.clear()
    conn.close()


def test_a_match_through_a_translation_says_so(client):
    api, config = client
    api.app.dependency_overrides[api.get_config] = lambda: dataclasses.replace(
        config, varianten=VariantSettings(in_resolver=True))
    antwoord = TestClient(api.app).post("/resolve", json={"text": "பில் கேட்ஸ் சிப்"}).json()
    assert antwoord["category"] == "matched" and antwoord["claim"]["id"] == "A"
    assert antwoord["via"] == {"language": "ta", "generator": "claude-haiku-5-5", "prompt": "vertalingen-v1"}


def test_with_the_switch_off_the_answer_never_uses_a_translation(client):
    api, config = client
    api.app.dependency_overrides[api.get_config] = lambda: dataclasses.replace(
        config, varianten=VariantSettings(in_resolver=False))
    antwoord = TestClient(api.app).post("/resolve", json={"text": "பில் கேட்ஸ் சிப்"}).json()
    assert antwoord["category"] == "none" and antwoord.get("via") is None


def test_the_benchmark_follows_the_same_switch(monkeypatch):
    """Elk cijfer gaat over het product (#3.3): de benchmark zoekt met de
    varianten precies als de resolver dat doet."""
    import doublecheck.benchmark as bm

    gezien = []
    monkeypatch.setattr(bm, "search_text", lambda conn, fp, **kw: gezien.append(kw.get("varianten")) or [])
    assert bm._met_varianten(dataclasses.replace(load_config(), varianten=VariantSettings(in_resolver=True)))
    assert not bm._met_varianten(dataclasses.replace(load_config(), varianten=VariantSettings(in_resolver=False)))


def test_a_benchmark_run_records_which_variant_set_it_searched():
    """Een releasekaart citeert runs; een run moet zeggen of hij met varianten
    zocht, zoals hij drempels en modelversies vastlegt (DR6)."""
    import doublecheck.benchmark as bm
    from doublecheck.config import load_config

    conn = _db()
    assert bm._variantenset(conn, VERSIE) == "claude-haiku-5-5/vertalingen-v1 · 2 varianten"
    assert bm._variantenset(conn, "ander-model") == ""
    config = load_config()
    resultaat = bm.BenchmarkResult(per_language={}, outcomes=(), variantenset="claude-haiku-5-5/vertalingen-v1 · 2 varianten")
    run = bm.record_run(conn, config.thresholds, config.model_versions, resultaat)
    assert conn.execute("SELECT variant_set FROM benchmark_run WHERE run_id = ?", (run,)).fetchone()[0] \
        == "claude-haiku-5-5/vertalingen-v1 · 2 varianten"


def test_an_empty_variant_table_is_a_start_not_a_mismatch():
    """Zoals bij de claimindex (E3.S1-AC2): een schone kloon zonder varianten
    is een legitieme beginstand. Alleen varianten van uitsluitend een ánder
    model zijn een mismatch (DR6)."""
    conn = _db()
    conn.execute("DELETE FROM claim_variant")
    ensure_variants_match_version(conn, VERSIE)
    assert [k.claim_id for k in search_text(conn, TextFingerprint(_v(1, 0, 0, 0), VERSIE), varianten=True)] == ["A", "B"]


def test_the_variant_sets_are_counted_from_what_the_search_uses(tmp_path):
    """Per generator en promptversie de talen en het aantal; alleen varianten
    van dit model (DR6), en een nieuwe variant telt meteen mee (#22.1)."""
    conn = _db(str(tmp_path / "v.db"))
    save_variant(conn, "B", "en", "Sea level has been falling for ten years", "claude-haiku-5-5",
                 "vertalingen-v1", TextFingerprint(_v(0, 0, 0, 1), "ander-model"))
    conn.commit()
    assert variant_sets(conn, VERSIE) == [
        {"generator": "claude-haiku-5-5", "prompt": "vertalingen-v1", "languages": ["es", "ta"], "count": 2}]
    save_variant(conn, "B", "pt", "O nível do mar está caindo há dez anos", "claude-haiku-5-5",
                 "vertalingen-v1", TextFingerprint(_v(0, 0, 0, 1), VERSIE))
    conn.commit()
    assert variant_sets(conn, VERSIE)[0]["languages"] == ["es", "pt", "ta"]
    assert variant_sets(conn, "nog-een-model") == []


def test_discovery_says_the_resolver_searches_through_translations(client):
    """Een afnemer moet vóór zijn eerste vraag kunnen zien dat er via
    vertalingen gezocht wordt (PROTOCOL §3), niet pas aan een `via` achteraf."""
    api, config = client
    api.app.dependency_overrides[api.get_config] = lambda: dataclasses.replace(
        config, varianten=VariantSettings(in_resolver=True))
    document = TestClient(api.app).get("/.well-known/doublecheck").json()
    assert document["variants"] == [
        {"generator": "claude-haiku-5-5", "prompt": "vertalingen-v1", "languages": ["ta"], "count": 1}]


def test_discovery_names_no_variants_with_the_switch_off(client):
    api, config = client
    api.app.dependency_overrides[api.get_config] = lambda: dataclasses.replace(
        config, varianten=VariantSettings(in_resolver=False))
    assert TestClient(api.app).get("/.well-known/doublecheck").json()["variants"] == []
