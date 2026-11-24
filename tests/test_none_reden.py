"""`none` met een reden (PLAN #25.35, SPECS E3.S2-AC5, PROTOCOL §6).

Een kale `none` kan twee dingen betekenen die niets met elkaar te maken hebben:
er is gezocht en niets gevonden, of er kón niet goed gezocht worden. Een
afnemer die een icoontje toont, moet die twee scheiden. De reden zet geen
categorie en verandert er geen (DR4); ze zegt alleen wat een `none` waard is.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.categorize import reden_voor_none
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

GEVONDEN = "De zeespiegel daalt al tien jaar wereldwijd"
NEDERLANDS = "Bananen bevatten meer vitamine C dan sinaasappels"
SWAHILI = "Ndizi zina vitamini C zaidi kuliko machungwa yote duniani"


def _eenheid(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return vector


@pytest.fixture
def client(monkeypatch):
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    save_text_fingerprint(conn, "seed-zeespiegel",
                          TextFingerprint(_eenheid([1.0, 0.0, 0.0]), config.model_versions.text_embedding))
    richtingen = {GEVONDEN: [1.0, 0.0, 0.0], NEDERLANDS: [0.0, 0.0, 1.0], SWAHILI: [0.0, 1.0, 0.0]}
    monkeypatch.setattr(api, "fingerprint_text",
                        lambda tekst, versie: TextFingerprint(_eenheid(richtingen[tekst]), versie))
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def _vraag(client, **verzoek):
    respons = client.post("/resolve", json=verzoek)
    assert respons.status_code == 200
    return respons.json()


def test_nothing_found_in_a_covered_language_is_not_found(client):
    antwoord = _vraag(client, text=NEDERLANDS)
    assert antwoord["category"] == "none"
    assert antwoord["reason"] == "not_found"


def test_a_language_outside_the_index_is_out_of_scope(client):
    antwoord = _vraag(client, text=SWAHILI)
    assert antwoord["category"] == "none"
    assert antwoord["reason"] == "out_of_scope"


def test_an_image_alone_against_an_index_without_images_is_low_confidence(client):
    versie = load_config().model_versions.image_hash
    antwoord = _vraag(client, image_fingerprint={"scheme": versie, "hash": "ab" * 32})
    assert antwoord["category"] == "none"
    assert antwoord["reason"] == "low_confidence"


def test_only_none_carries_a_reason(client):
    antwoord = _vraag(client, text=GEVONDEN)
    assert antwoord["category"] == "matched"
    assert antwoord["reason"] is None


def test_an_uncertain_language_is_never_called_out_of_scope():
    """We zeggen alleen wat we weten: geen taal herkend, dan is er gezocht
    zoals voor elke tekst."""
    assert reden_voor_none(zoektekst="ok", taal=None, index_talen={"nl"}) == "not_found"


def test_only_the_image_route_ran_when_there_was_no_text_to_search():
    assert reden_voor_none(zoektekst=None, taal=None, index_talen={"nl"}) == "low_confidence"
    assert reden_voor_none(zoektekst="tekst", taal="sw", index_talen={"nl"}) == "out_of_scope"
    assert reden_voor_none(zoektekst="tekst", taal="nl", index_talen={"nl"}) == "not_found"


def test_the_demo_says_what_a_none_is_worth(client):
    pagina = client.get("/").text
    assert "data.reason === 'out_of_scope'" in pagina
    assert "data.reason === 'low_confidence'" in pagina
