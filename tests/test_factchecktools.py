import json
from pathlib import Path

import httpx
import pytest

from doublecheck.factchecktools import parse_response, search_claims

SAMPLE_PATH = Path(__file__).parent / "fixtures" / "factchecktools_sample.json"


def _sample():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def test_client_parses_sample_response():
    claims = parse_response(_sample())

    assert len(claims) == 3

    eerste = claims[0]
    assert eerste.text == "Coronavaccins veranderen je DNA"
    assert eerste.claimant == "Sociale media"
    assert eerste.claim_date == "2021-04-28T00:00:00Z"
    assert len(eerste.factchecks) == 2

    check = eerste.factchecks[0]
    assert check.publisher == "Nieuwscheckers"
    assert check.verdict_original == "Onjuist"
    assert check.url == "https://nieuwscheckers.nl/factcheck/vaccin-dna"
    assert check.review_date == "2021-05-04T00:00:00Z"
    assert check.language == "nl"

    tweede_uitgever = eerste.factchecks[1].publisher
    assert tweede_uitgever == "AFP Factcheck Nederland"


def test_missing_fields_survive_parsing_for_later_refusal():
    claims = parse_response(_sample())

    zonder_url = claims[1].factchecks[0]
    assert zonder_url.url is None
    assert zonder_url.publisher == "Skeptical Science"

    zonder_datum = claims[2].factchecks[0]
    assert zonder_datum.review_date is None
    assert zonder_datum.verdict_original is None
    assert zonder_datum.url == "https://www.snopes.com/fact-check/shark-highway"


def test_empty_response_gives_no_claims():
    assert parse_response({}) == []


def test_search_by_publisher_site_without_query():
    verzoeken = []

    def handler(request):
        verzoeken.append(request)
        return httpx.Response(200, json={"claims": [{"text": "x", "claimReview": []}]})

    claims = search_claims(
        api_key="test-sleutel",
        review_publisher_site_filter="nieuwscheckers.nl",
        transport=httpx.MockTransport(handler),
    )

    assert len(claims) == 1
    params = verzoeken[0].url.params
    assert params["reviewPublisherSiteFilter"] == "nieuwscheckers.nl"
    assert "query" not in params


def test_search_without_query_or_site_is_refused():
    with pytest.raises(ValueError):
        search_claims(api_key="test-sleutel")


def test_search_paginates_and_sends_key():
    paginas = {
        None: {
            "claims": [{"text": "claim een", "claimReview": []}],
            "nextPageToken": "token-2",
        },
        "token-2": {"claims": [{"text": "claim twee", "claimReview": []}]},
    }
    verzoeken = []

    def handler(request):
        verzoeken.append(request)
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=paginas[token])

    claims = search_claims(
        "vaccin",
        api_key="test-sleutel",
        language_code="nl",
        transport=httpx.MockTransport(handler),
    )

    assert [claim.text for claim in claims] == ["claim een", "claim twee"]
    assert verzoeken[0].url.params["key"] == "test-sleutel"
    assert verzoeken[0].url.params["query"] == "vaccin"
    assert verzoeken[0].url.params["languageCode"] == "nl"
    assert "pageToken" not in verzoeken[0].url.params
    assert verzoeken[1].url.params["pageToken"] == "token-2"
