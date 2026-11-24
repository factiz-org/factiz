"""De geschiedenis van een bewering in het antwoord (PROTOCOL §11.7, E7.S5).

Een screenshot erin, de geschiedenis eruit (PO 2026-10-12): de checks zeggen
wie de bewering wanneer ontkrachtte, de attributies waar en wanneer ze
opdook. Bonnetjes, geen bevestiging: ze veranderen nooit de categorie en
tellen nooit mee bij de redacties (DR7).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import attributie as at
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

TEKST = "Ukraine is governed by Nazis."


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def dienst(monkeypatch):
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    for cid, tekst, uitgever, url, datum, taal, richting in (
        ("A", TEKST, "EUvsDisinfo", "https://euvsdisinfo.eu/report/a", "2016-02-04", "en", (1, 0, 0)),
        ("B", "In der Ukraine regieren Nazis.", "BR24 Faktenfuchs", "https://br.de/b", "2023-02-24", "de",
         (0.95, 0.31, 0)),
    ):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, ?, 'cl-1')",
                     (cid, tekst, taal))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, ?, 'onwaar', 'False', ?, ?, ?)",
                     (cid, uitgever, url, datum, taal))
        save_text_fingerprint(conn, cid, TextFingerprint(_v(*richting), config.model_versions.text_embedding))
    at.registreer_bron(conn, bron_id="euvsdisinfo", naam="EUvsDisinfo", soort="overheid", licentie="CC BY 4.0",
                       attributietekst="EUvsDisinfo", url="https://euvsdisinfo.eu", herverdeelbaar=True)
    at.registreer_bron(conn, bron_id="communitynotes", naam="Community Notes (X)", soort="platform",
                       licentie="X Developer Agreement", attributietekst="Community Notes",
                       url="https://communitynotes.x.com", herverdeelbaar=False)
    kanaal = at.registreer_actor(conn, naam="Vremya Pokazhet", soort="outlet")
    x = at.registreer_actor(conn, naam="X", soort="platform")
    at.voeg_attributie(conn, claim_id="B", actor_id=x, bron_id="communitynotes", datum="2025-03-15",
                       url="https://x.com/i/birdwatch/n/1", niveau="waargenomen")
    at.voeg_attributie(conn, claim_id="A", actor_id=kanaal, bron_id="euvsdisinfo", datum="2016-02-04",
                       url="https://euvsdisinfo.eu/report/a", niveau="waargenomen")
    conn.commit()
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, v: TextFingerprint(_v(1, 0, 0), v))
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


def test_an_answer_carries_the_history_of_the_whole_cluster_by_date(dienst):
    client, _ = dienst
    bewijs = client.post("/resolve", json={"text": TEKST}).json()["evidence"]
    assert bewijs["attributions"] == [
        {"actor": "Vremya Pokazhet", "actor_kind": "outlet", "source": "EUvsDisinfo", "source_kind": "overheid",
         "level": "waargenomen", "date": "2016-02-04", "url": "https://euvsdisinfo.eu/report/a"},
        {"actor": "X", "actor_kind": "platform", "source": "Community Notes (X)", "source_kind": "platform",
         "level": "waargenomen", "date": "2025-03-15", "url": "https://x.com/i/birdwatch/n/1"},
    ]


def test_attributions_never_change_the_category_or_the_count_of_newsrooms(dienst):
    """Een bewering die op tien kanalen verscheen, is daarmee niet tien keer
    ontkracht (DR7), en een attributie maakt geen `related` tot `matched`."""
    client, conn = dienst
    met = client.post("/resolve", json={"text": TEKST}).json()
    conn.execute("DELETE FROM attributie")
    conn.commit()
    zonder = client.post("/resolve", json={"text": TEKST}).json()
    assert zonder["evidence"]["attributions"] == []
    for veld in ("category", "similarity", "matched_on", "claim"):
        assert met[veld] == zonder[veld], veld
    for veld in ("checks", "check_count", "publisher_count", "languages", "oldest_date"):
        assert met["evidence"][veld] == zonder["evidence"][veld], veld
