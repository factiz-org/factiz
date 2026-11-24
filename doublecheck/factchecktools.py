"""Client voor de Google Fact Check Tools API (E2.S1) — corpus-import.

Uitsluitend voor het opbouwen van de index: zoekopdrachten die wíj kiezen.
Artefacten van gebruikers gaan hier nooit doorheen (DR3).

De parser is bewust tolerant: ontbrekende velden worden None in plaats van
weggegooid, zodat de importlaag (taak 2.2) claims zonder URL of datum kan
weigeren en loggen in plaats van ze stil te laten verdwijnen (DR1).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


@dataclass(frozen=True)
class RawFactcheck:
    publisher: str | None
    publisher_site: str | None
    url: str | None
    review_date: str | None
    verdict_original: str | None
    language: str | None


@dataclass(frozen=True)
class RawClaim:
    text: str | None
    claimant: str | None
    claim_date: str | None
    factchecks: tuple[RawFactcheck, ...]


def parse_response(data: dict) -> list[RawClaim]:
    claims = []
    for entry in data.get("claims", []):
        reviews = tuple(
            RawFactcheck(
                publisher=(review.get("publisher") or {}).get("name"),
                publisher_site=(review.get("publisher") or {}).get("site"),
                url=review.get("url"),
                review_date=review.get("reviewDate"),
                verdict_original=review.get("textualRating"),
                language=review.get("languageCode"),
            )
            for review in entry.get("claimReview", [])
        )
        claims.append(
            RawClaim(
                text=entry.get("text"),
                claimant=entry.get("claimant"),
                claim_date=entry.get("claimDate"),
                factchecks=reviews,
            )
        )
    return claims


def search_claims(
    query: str | None = None,
    *,
    api_key: str,
    language_code: str | None = None,
    review_publisher_site_filter: str | None = None,
    page_size: int = 100,
    max_pages: int = 10,
    timeout: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> list[RawClaim]:
    if not query and not review_publisher_site_filter:
        raise ValueError("geef een query of een reviewPublisherSiteFilter op")

    resultaten: list[RawClaim] = []
    basis: dict = {"key": api_key, "pageSize": page_size}
    if query:
        basis["query"] = query
    if review_publisher_site_filter:
        basis["reviewPublisherSiteFilter"] = review_publisher_site_filter
    if language_code:
        basis["languageCode"] = language_code

    with httpx.Client(transport=transport, timeout=timeout) as client:
        token: str | None = None
        for _ in range(max_pages):
            params = dict(basis)
            if token:
                params["pageToken"] = token
            respons = client.get(API_URL, params=params)
            respons.raise_for_status()
            data = respons.json()
            resultaten.extend(parse_response(data))
            token = data.get("nextPageToken")
            if not token:
                break
    return resultaten
