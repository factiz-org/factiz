"""De bewering uit een artikel in `/resolve` (#30.11).

Met `[artikel] per_zin` aan wordt een tekst met twee of meer zinnen gezocht
als de hele tekst plus elke zin; per eenheid beslist `categorize` (DR4), en
de beste uitkomst wint. Eén zin: het pad van nu. Vingerafdrukken en rechter
zijn nep: per tekst een vaste richting en een vaste score.
"""

import dataclasses

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
import doublecheck.rechter as rechter
from doublecheck.config import ArtikelSettings, FeitenSettings, RechterSettings, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

KOP = "Vaccines secretly contain tracking microchips"
ANDERS = "The ministry published new figures on Monday."
ARTIKEL = f"{KOP}\nThe claim spread fast on Telegram this week. {ANDERS}"
LOS = "Vaccines secretly contain tracking microchips."


def _eenheid(*xs):
    v = np.asarray(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _config(per_zin=True, rechter_aan=False):
    basis = load_config()
    drempels = dataclasses.replace(basis.thresholds, rechter_vloer=0.79, rechter_zelfde=0.95, rechter_veto=0.6)
    return dataclasses.replace(basis, thresholds=drempels, artikel=ArtikelSettings(per_zin=per_zin),
                               rechter=RechterSettings(aan=rechter_aan, model="nep", pad="nep", diepte=5),
                               feiten=FeitenSettings(aan=False))


@pytest.fixture
def dienst(monkeypatch):
    """Eén claim; de kop ligt erop, het artikel als geheel en de andere zinnen
    liggen er ver vanaf."""
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    versie = load_config().model_versions.text_embedding
    save_text_fingerprint(conn, "seed-zeespiegel", TextFingerprint(_eenheid(1, 0, 0), versie))
    richting = {KOP: _eenheid(1, 0, 0), LOS: _eenheid(1, 0, 0), ARTIKEL: _eenheid(0.5, 0.86, 0),
                "The claim spread fast on Telegram this week.": _eenheid(0, 0, 1),
                ANDERS: _eenheid(0, 1, 0)}
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, v: TextFingerprint(richting[tekst], v))
    monkeypatch.setattr(api, "fingerprint_texts", lambda teksten, v: [TextFingerprint(richting[t], v)
                                                                       for t in teksten])
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), richting
    api.app.dependency_overrides.clear()
    conn.close()


def _zet(config):
    api.app.dependency_overrides[api.get_config] = lambda: config


def test_a_headline_inside_an_article_is_found_per_sentence(dienst):
    client, _ = dienst
    _zet(_config(per_zin=False))
    assert client.post("/resolve", json={"text": ARTIKEL}).json()["category"] != "matched"
    _zet(_config(per_zin=True))
    body = client.post("/resolve", json={"text": ARTIKEL}).json()
    assert body["category"] == "matched"
    assert body["claim"]["id"] == "seed-zeespiegel"
    assert body["similarity"] == pytest.approx(1.0, abs=1e-5)


def test_one_sentence_takes_the_path_it_always_took(dienst):
    client, _ = dienst
    _zet(_config(per_zin=False))
    uit = client.post("/resolve", json={"text": LOS}).json()
    _zet(_config(per_zin=True))
    assert client.post("/resolve", json={"text": LOS}).json() == uit


def test_the_judge_reads_only_the_three_closest_sentences(dienst, monkeypatch):
    """Vier zinnen tussen vloer en `text_match`; alleen de vierde zou de
    rechter overtuigen, maar die leest hij niet: geen `matched`."""
    client, richting = dienst
    zinnen = [f"Sentence number {i} about the vaccine chips." for i in range(4)]
    for i, zin in enumerate(zinnen):
        richting[zin] = _eenheid(0.86 - 0.02 * i, np.sqrt(1 - (0.86 - 0.02 * i) ** 2), 0)
    tekst = " ".join(zinnen)
    richting[tekst] = _eenheid(0, 0, 1)
    monkeypatch.setattr(rechter, "scores", lambda vraag, teksten, pad, model: [
        0.99 if vraag == zinnen[3] else 0.1 for _ in teksten])
    _zet(_config(per_zin=True, rechter_aan=True))
    assert client.post("/resolve", json={"text": tekst}).json()["category"] == "related"
    monkeypatch.setattr(rechter, "scores", lambda vraag, teksten, pad, model: [
        0.99 if vraag == zinnen[2] else 0.1 for _ in teksten])
    body = client.post("/resolve", json={"text": tekst}).json()
    assert body["category"] == "matched"
    assert body["similarity"] == pytest.approx(0.82, abs=1e-5)
