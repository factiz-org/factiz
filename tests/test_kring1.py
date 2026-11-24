"""De eerste kring van de controle (PLAN #32.7a): raakt het bericht een check uit de database die één kant op
wijst, dan dat antwoord meteen, zonder model. Het snelle antwoord zat op 1.489 antwoorden nooit fout (§172)."""

import dataclasses
import sqlite3

import numpy as np
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import berichtcontrole as controle
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

TABEL = {("klopt niet", "redactie"): {"stand": 1, "n": 80, "aandeel waar": 0.0},
         ("klopt", "redactie"): {"stand": 9, "n": 40, "aandeel waar": 1.0}}
TEKST = "De zeespiegel daalt al tien jaar wereldwijd"


def _check(oordeel, uitgever="Nieuwscheckers"):
    return {"publisher": uitgever, "verdict_normalized": oordeel, "verdict_original": oordeel,
            "url": f"https://example.org/{uitgever}", "review_date": "2024-03-14", "language": "nl"}


def _resolve(categorie="matched", oordelen=("onwaar",)):
    return {"category": categorie, "claim": {"id": "c1", "text": "De zeespiegel daalt", "cluster_size": 1},
            "evidence": {"checks": [_check(o) for o in oordelen]} if categorie == "matched" else None}


def test_a_matched_check_that_points_one_way_answers_without_the_model():
    uit = controle.snel_antwoord(_resolve(), TABEL, TEKST, "bge-m3-v1")
    assert uit["oordeel"] == "klopt niet" and uit["kleur"] == "rood" and uit["stand"]["laag"] == "redactie"
    assert uit["kosten"] == 0 and uit["versies"]["route"] == "database" and uit["gelezen"] == TEKST
    assert uit["bronnen"] == [{"soort": "check van een redactie", "url": "https://example.org/Nieuwscheckers",
                               "redactie": "Nieuwscheckers", "oordeel": "onwaar", "datum": "2024-03-14",
                               "titel": None, "citaat": None}]
    assert uit["bewering"] == "De zeespiegel daalt" and uit["uitleg"] is None and uit["meting"]["n"] == 80
    waar = controle.snel_antwoord(_resolve(oordelen=("waar", "waar")), TABEL, TEKST, "bge-m3-v1")
    assert waar["oordeel"] == "klopt" and waar["kleur"] == "groen"


def test_related_mixed_or_unclear_checks_go_on_to_the_model():
    assert controle.snel_antwoord(_resolve("related"), TABEL, TEKST, "v") is None
    assert controle.snel_antwoord(_resolve(oordelen=("onwaar", "waar")), TABEL, TEKST, "v") is None
    assert controle.snel_antwoord(_resolve(oordelen=("onduidelijk",)), TABEL, TEKST, "v") is None
    assert controle.snel_antwoord(_resolve(oordelen=()), TABEL, TEKST, "v") is None


class _GeenModel:
    """Elke vraag aan een model is hier een fout."""

    def __init__(self):
        self.messages = self

    def create(self, **_):
        raise AssertionError("de eerste kring vraagt geen model")


def test_the_endpoint_answers_from_the_database_before_any_model_call(monkeypatch):
    config = load_config()
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, aan=True))
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    vector = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    save_text_fingerprint(conn, "seed-zeespiegel", TextFingerprint(vector, config.model_versions.text_embedding))
    monkeypatch.setattr(api, "fingerprint_text", lambda text, versie: TextFingerprint(vector, versie))
    monkeypatch.setattr(controle, "ijktabel", lambda config: TABEL)
    monkeypatch.setattr(controle, "herkomstlijst", lambda: {"_meta": {"versie": "bronnen-v7"}, "sites": {}})  # zonder de lijst uit het lab, data/ staat niet in git
    api.app.dependency_overrides[api.get_anthropic] = _GeenModel
    api.app.dependency_overrides[api.get_zoeker] = lambda: (lambda q: (_ for _ in ()).throw(
        AssertionError("de eerste kring zoekt niet")))
    api.app.dependency_overrides[api.get_config] = lambda: config
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_kostenconn] = lambda: sqlite3.connect(":memory:", check_same_thread=False)
    try:
        antwoord = TestClient(api.app).post("/check", json={"text": TEKST})
    finally:
        api.app.dependency_overrides.clear()
    assert antwoord.status_code == 200, antwoord.text
    d = antwoord.json()
    assert d["verdict"] == "klopt niet" and d["colour"] == "red" and d["route"] == "database"
    assert d["sources"][0]["kind"] == "check van een redactie" and d["sources"][0]["publisher"] == "Nieuwscheckers"
    assert "category" not in d
