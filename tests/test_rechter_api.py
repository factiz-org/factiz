"""De rechter in het antwoord (#30.3, PROTOCOL verplichting 2 en 8).

Met de rechter aan kan `matched` vallen tussen `rechter_vloer` en
`text_match`, maar alleen als de rechter `rechter_zelfde` haalt. Een afnemer
die alleen `text_match` ziet, leest dat als een `matched` onder de drempel.
Het antwoord noemt daarom elke drempel die het bepaald kan hebben. De echte
rechter laadt hier niet: een nep-rechter geeft per kandidaattekst een score.
"""

import dataclasses

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
import doublecheck.rechter as rechter
from conformance.suite import GESLAAGD, Waarneming, _v2
from doublecheck.config import FeitenSettings, RechterSettings, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

ZELFDE = "De zeespiegel daalt al tien jaar wereldwijd"
PARAFRASE = "De zeespiegel zakt al een decennium overal ter wereld"


def _eenheid(richting):
    vector = np.asarray(richting, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def _config(aan: bool):
    basis = load_config()
    drempels = dataclasses.replace(basis.thresholds, rechter_vloer=0.79, rechter_zelfde=0.95,
                                   rechter_veto=0.6)
    return dataclasses.replace(basis, thresholds=drempels,
                               rechter=RechterSettings(aan=aan, model="nep", pad="nep", diepte=5),
                               feiten=FeitenSettings(aan=False))


@pytest.fixture
def dienst(monkeypatch):
    """Een dienst met één claim, een vraag op 0,83 (tussen vloer en
    `text_match`) en een rechter die per test een score krijgt."""
    config = _config(True)
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    claim = _eenheid([1.0, 0.0, 0.0])
    save_text_fingerprint(conn, "seed-zeespiegel", TextFingerprint(claim, config.model_versions.text_embedding))
    richtingen = {ZELFDE: claim, PARAFRASE: _eenheid([0.83, np.sqrt(1 - 0.83**2), 0.0])}
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, versie: TextFingerprint(richtingen[tekst], versie))
    uitslag = {}
    monkeypatch.setattr(rechter, "scores", lambda vraag, teksten, pad, model: [uitslag[vraag] for _ in teksten])
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_config] = lambda: config
    yield TestClient(api.app), uitslag
    api.app.dependency_overrides.clear()
    conn.close()


def test_a_judged_match_below_text_match_reports_the_threshold_that_allowed_it(dienst):
    client, uitslag = dienst
    uitslag[PARAFRASE] = 0.97
    body = client.post("/resolve", json={"text": PARAFRASE}).json()
    assert body["category"] == "matched"
    assert body["similarity"] < body["thresholds"]["text_match"]
    assert body["thresholds"]["text_match_judged"] == 0.79
    assert body["thresholds"]["judge_same"] == 0.95
    assert body["thresholds"]["judge_veto"] == 0.6
    # Van buitenaf: geen `matched` onder de laagste gemelde tekstdrempel.
    assert _v2([Waarneming("rechter", 200, body)]).stand == GESLAAGD


def test_below_text_match_an_unsure_judge_never_gives_matched(dienst):
    client, uitslag = dienst
    uitslag[PARAFRASE] = 0.94
    assert client.post("/resolve", json={"text": PARAFRASE}).json()["category"] == "related"


def test_above_text_match_the_judge_can_veto(dienst):
    client, uitslag = dienst
    uitslag[ZELFDE] = 0.5
    assert client.post("/resolve", json={"text": ZELFDE}).json()["category"] == "related"
    uitslag[ZELFDE] = 0.7
    assert client.post("/resolve", json={"text": ZELFDE}).json()["category"] == "matched"


def test_discovery_names_the_judge_thresholds_only_when_the_judge_is_on(dienst):
    client, _ = dienst
    drempels = client.get("/.well-known/doublecheck").json()["thresholds"]
    assert drempels["text_match_judged"] == 0.79
    api.app.dependency_overrides[api.get_config] = lambda: _config(False)
    drempels = client.get("/.well-known/doublecheck").json()["thresholds"]
    assert not {"text_match_judged", "judge_same", "judge_veto"} & set(drempels)
