"""Marktdefinities voor uitrol per taalgebied (PLAN.md #11.4, B14).

De corpussweep was hardgecodeerd op Nederlands. B14 zegt markt-voor-markt, dus
een markt hoort data te zijn en geen code: uitgevers, zoektermen en taalcode
staan in één tabel, zodat een nieuwe markt een regel is en geen functie.

Uitgevers zijn niet gegokt maar getoetst tegen de API — `aosfatos.org` viel af
omdat het 100% Portugees levert, wat een Spaanse benchmark zou vervuilen
(BENCHMARK.md §22a).
"""

import pytest

from doublecheck.ingest import MARKTEN, Markt, sweep


def test_every_market_is_complete():
    for code, markt in MARKTEN.items():
        assert isinstance(markt, Markt), code
        assert markt.language_code == code
        assert markt.publisher_sites, code
        assert markt.queries, code


def test_dutch_market_is_unchanged():
    """Regressie: de bestaande NL-sweep moet dezelfde bronnen houden."""
    nl = MARKTEN["nl"]
    assert "nieuwscheckers.nl" in nl.publisher_sites
    assert "dpa-factchecking.com" in nl.publisher_sites
    assert "vaccin" in nl.queries


def test_spanish_market_spans_more_than_one_country():
    """DR7 telt oordelen van onafhankelijke uitgevers; één land is te smal."""
    es = MARKTEN["es"]
    assert {"maldita.es", "chequeado.com", "colombiacheck.com"} <= set(es.publisher_sites)
    assert len(es.publisher_sites) >= 5


def test_portuguese_publisher_is_not_in_the_spanish_market():
    """`aosfatos.org` levert Portugees; gemeten, niet aangenomen."""
    assert "aosfatos.org" not in MARKTEN["es"].publisher_sites


def test_unknown_market_is_refused(monkeypatch):
    with pytest.raises(KeyError):
        sweep(conn=None, api_key="x", markt="xx")


def test_sweep_queries_in_the_market_language(monkeypatch):
    """Een zoekterm mag niet in de verkeerde taal worden opgehaald."""
    gezien = []

    def nep_search(term=None, *, api_key, language_code=None,
                   review_publisher_site_filter=None, max_pages=1):
        gezien.append((term, language_code, review_publisher_site_filter))
        return []

    monkeypatch.setattr("doublecheck.ingest.search_claims", nep_search)
    monkeypatch.setattr("doublecheck.ingest.import_claims",
                        lambda *a, **k: __import__("doublecheck.ingest", fromlist=["ImportReport"]).ImportReport(0, 0, 0, 0, 0, ()))
    monkeypatch.setattr("doublecheck.ingest.ConfigFingerprinter", lambda: None)

    sweep(conn=None, api_key="x", markt="es")

    talen = {taal for term, taal, site in gezien if term is not None}
    assert talen == {"es"}
    sites = {site for term, taal, site in gezien if site is not None}
    assert "maldita.es" in sites


def test_every_market_has_a_share_in_the_testset():
    """Een markt zonder aandeel levert geen testparen en dus geen benchmarkcijfer."""
    from doublecheck.testset import DEFAULT_LANGUAGE_SHARES

    for code in MARKTEN:
        assert code in DEFAULT_LANGUAGE_SHARES, code
    assert abs(sum(DEFAULT_LANGUAGE_SHARES.values()) - 1.0) < 1e-9


def test_ocr_covers_every_market_language():
    """Een markt zonder OCR-taalpakket leest zijn eigen screenshots niet."""
    from doublecheck.config import load_config

    pakketten = set(load_config().ocr.languages.split("+"))
    verwacht = {"nl": "nld", "es": "spa"}
    for code in MARKTEN:
        assert verwacht[code] in pakketten, code
