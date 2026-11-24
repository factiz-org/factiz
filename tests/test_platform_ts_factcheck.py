"""De factcheckpagina van de TypeScript-kant naast de Python-kant (B80, PLAN #34.2bo stap 3): per uitgave elk nummer in
elke sitetaal hetzelfde antwoord na inlezen, dezelfde 404 voor een nummer dat er niet is, en dezelfde 301 met hetzelfde
adres voor het nummer van een andere formulering. De uitgaven komen uit de toetsen van het platform: elk heeft een
kenmerk dat de pagina anders maakt (vertalingen, hoofdletters, dossiers en versies, netwerken, namen, thema's en landen,
waarom het niet klopt, lijkt op, vijandige tekst)."""

import pytest
from starlette.testclient import TestClient

from factiz_site import app as fa
from factiz_site import db as fdb
from factiz_site import gelijk_factcheck as gf
from factiz_site import i18n
from tests.test_factiz_api import met_waarom  # noqa: F401  (een fixture)
from tests.test_factiz_context import bestand as context_bestand  # noqa: F401
from tests.test_factiz_dossiers import _site as _dossiersite
from tests.test_factiz_melden import client as melden_client  # noqa: F401
from tests.test_factiz_namen import _site as _namensite
from tests.test_factiz_site import site as skelet  # noqa: F401
from tests.test_factiz_themas import _site as _themasite
from tests.test_factiz_vertaling import _site as _vertaalsite
from tests.test_hoofdletters import uitgave as hoofdletters  # noqa: F401


def _bestand(client):
    return client.app.state.publicatie.pad


def _vergelijk(bestand, grenzen=None):
    """Elk nummer van de uitgave, een andere formulering en wat niet bestaat, in elke taal; de verschillen in woorden."""
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    return gf.verschillen(client, bestand, gf.adressen(fdb.Publicatie(bestand)), grenzen)


def test_every_fact_check_of_the_skeleton_answers_the_same_and_another_wording_moves_to_the_same_claim(skelet):
    client, nr, bestand = skelet
    assert _vergelijk(bestand) == []
    # het Spaans is een andere formulering van de villa: blijvend naar de bewering, in elke taal hetzelfde adres
    adressen = [f"/api/{taal}/factcheck/{nr['spaans']}" for taal in i18n.TALEN]
    ts = gf.ts_antwoorden(bestand, adressen)
    assert [t["status"] for t in ts] == [301] * len(i18n.TALEN)
    assert [t["adres"] for t in ts] == [client.get(a).headers["location"] for a in adressen]
    assert {t["adres"] for t in ts} == {f"/api/{taal}/factcheck/{nr['gewoon']}" for taal in i18n.TALEN}


@pytest.mark.parametrize("concepten", [False, True])
def test_dossiers_versions_networks_glosses_and_similar_pages_answer_the_same(tmp_path_factory, concepten):
    client, _ = _dossiersite(tmp_path_factory, concepten=concepten)
    assert _vergelijk(client.bestand) == []


def test_a_release_without_dossiers_answers_the_same(tmp_path_factory):
    client, _ = _dossiersite(tmp_path_factory, met_dossiers=False)
    assert _vergelijk(client.bestand) == []


@pytest.mark.parametrize("concept", [False, True])
def test_names_answer_the_same(tmp_path_factory, concept):
    client, _ = _namensite(tmp_path_factory, concept=concept)
    assert _vergelijk(client.bestand) == []


def test_themes_a_second_theme_parts_and_countries_answer_the_same(tmp_path_factory):
    client, _ = _themasite(tmp_path_factory)
    assert _vergelijk(_bestand(client)) == []


def test_context_cards_answer_the_same_with_the_limits_of_the_release(context_bestand):
    bestand, _ = context_bestand
    assert _vergelijk(bestand) == []


def test_context_cards_answer_the_same_with_a_network_and_a_ratio_like_the_context_tests(context_bestand, monkeypatch):
    # de grenzen van tests/test_factiz_context.py: vier namen in het netwerk, een lijn bij één factcheck samen, en een
    # verhouding bij elk land, zodat de kaart van de namen en de verhouding iets te zeggen hebben
    grenzen = {"NETWERK_NAMEN": 4, "NETWERK_SAMEN": 1, "VERHOUDING_LAND": 1, "VERHOUDING_THEMA": 1}
    for naam, waarde in grenzen.items():
        monkeypatch.setattr(fdb, naam, waarde)
    bestand, nr = context_bestand
    assert _vergelijk(bestand, grenzen) == []
    villa = gf.ts_antwoorden(bestand, [f"/api/en/factcheck/{nr['villa']}"], grenzen)[0]["body"]
    kaarten = {k["soort"]: k for k in villa["context"]}
    assert "often with" in kaarten["namen"]["namen"][0]["regel"] and "×" in kaarten["waar"]["zin"]


def test_reporting_an_error_answers_the_same(melden_client):
    client, _ = melden_client
    assert _vergelijk(_bestand(client)) == []


@pytest.mark.parametrize("extra", [{}, {"nl": {"hindi": "Deze foto toont het station van Ayodhya", "engels": "De maan is "
                                                "gemaakt van kaas", "spaans": "De maan is van kaas, zeggen ze"},
                                         "de": {"arabisch": "Dieses Video zeigt eine Explosion in Beirut"}}])
def test_translations_in_the_language_of_the_site_or_in_english_answer_the_same(tmp_path_factory, extra):
    client, _ = _vertaalsite(tmp_path_factory, **extra)
    assert _vergelijk(_bestand(client)) == []


def test_why_it_is_false_answers_the_same(met_waarom):
    client, _ = met_waarom
    assert _vergelijk(_bestand(client)) == []


def test_a_claim_in_capitals_with_its_normal_writing_answers_the_same(hoofdletters):
    manifest, _ = hoofdletters
    assert _vergelijk(manifest["bestand"]) == []
