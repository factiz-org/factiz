"""De artikellezer in `/resolve` (#30.11b).

Een tekst van meerdere eenheden die langs de gewone weg geen `matched` gaf,
leest de lezer met de beste claims over de eenheden; vanaf `artikel_vloer`
en met `artikel_zelfde` wordt het `matched`. Het antwoord noemt die drempels
(verplichting 8). Vingerafdrukken en lezer zijn nep.
"""

import dataclasses

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import artikellezer
from conformance.suite import GESLAAGD, Waarneming, _v2
from doublecheck.config import ArtikellezerSettings, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

KOP = "NATO is secretly preparing an attack on Russia this winter"
ZIN = "Exercises near the border are only a cover for that plan."
ARTIKEL = f"{KOP}\n{ZIN}"


def _eenheid(*xs):
    v = np.asarray(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _config(aan=True):
    basis = load_config()
    drempels = dataclasses.replace(basis.thresholds, artikel_vloer=0.70, artikel_zelfde=0.80)
    return dataclasses.replace(basis, thresholds=drempels,
                               artikellezer=ArtikellezerSettings(aan=aan, model="nep", pad="nep", diepte=5))


@pytest.fixture
def dienst(monkeypatch):
    """Eén claim; de kop ligt er op 0,74 van, het artikel als geheel op 0,5."""
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    versie = load_config().model_versions.text_embedding
    save_text_fingerprint(conn, "seed-zeespiegel", TextFingerprint(_eenheid(1, 0, 0), versie))
    richting = {ARTIKEL: _eenheid(0.5, np.sqrt(0.75), 0), KOP: _eenheid(0.74, np.sqrt(1 - 0.74**2), 0),
                ZIN: _eenheid(0, 0, 1)}
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, v: TextFingerprint(richting[tekst], v))
    monkeypatch.setattr(api, "fingerprint_texts", lambda teksten, v: [TextFingerprint(richting[t], v) for t in teksten])
    score = {"waarde": 0.9}
    monkeypatch.setattr(artikellezer, "scores_lezer", lambda paren, pad, model: [score["waarde"] for _ in paren])
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), score
    api.app.dependency_overrides.clear()
    conn.close()


def _zet(config):
    api.app.dependency_overrides[api.get_config] = lambda: config


def test_a_sure_reader_finds_the_claim_an_article_makes_below_the_judges_floor(dienst):
    client, _ = dienst
    _zet(_config(aan=False))
    assert client.post("/resolve", json={"text": ARTIKEL}).json()["category"] == "none"
    _zet(_config(aan=True))
    body = client.post("/resolve", json={"text": ARTIKEL}).json()
    assert body["category"] == "matched"
    assert body["claim"]["id"] == "seed-zeespiegel"
    assert body["similarity"] == pytest.approx(0.74, abs=1e-5)
    assert body["thresholds"]["text_match_read"] == 0.70
    assert body["thresholds"]["reader_same"] == 0.80
    assert _v2([Waarneming("lezer", 200, body)]).stand == GESLAAGD


def test_an_unsure_reader_changes_nothing(dienst):
    client, score = dienst
    score["waarde"] = 0.5
    _zet(_config(aan=True))
    assert client.post("/resolve", json={"text": ARTIKEL}).json()["category"] == "none"


def test_one_sentence_never_reaches_the_reader(dienst, monkeypatch):
    client, _ = dienst

    def nooit(paren, pad, model):
        raise AssertionError("één zin gaat niet langs de lezer")

    monkeypatch.setattr(artikellezer, "scores_lezer", nooit)
    _zet(_config(aan=True))
    client.post("/resolve", json={"text": KOP})


def test_discovery_names_the_reader_thresholds_only_when_it_is_on(dienst):
    client, _ = dienst
    _zet(_config(aan=True))
    assert client.get("/.well-known/doublecheck").json()["thresholds"]["text_match_read"] == 0.70
    _zet(_config(aan=False))
    assert "text_match_read" not in client.get("/.well-known/doublecheck").json()["thresholds"]
