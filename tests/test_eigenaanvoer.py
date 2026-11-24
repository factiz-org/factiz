"""Eigen aanvoer, de proef van route A (PLAN #32.19).

De grote factcheckers zetten ClaimReview nog in hun eigen artikelen, maar komen niet meer in de open feed. De proef
haalt die beleefd op: de sitemap uit robots.txt, per site één verzoek tegelijk, en uit elk artikel alleen de
ClaimReview. Bewaard worden het adres, de bewering, het oordeel, de datum en of het adres al in de database staat;
nooit de pagina.
"""

import itertools
import json

import pytest

from doublecheck import eigenaanvoer as ea


def _pagina(*blokken: str) -> str:
    scripts = "".join(f'<script type="application/ld+json">{b}</script>' for b in blokken)
    return f"<html><head><title>x</title>{scripts}</head><body><p>De tekst van het artikel.</p></body></html>"


REVIEW = {"@context": "https://schema.org", "@type": "ClaimReview", "url": "https://factcheck.afp.com/doc.afp.com.ABC1",
          "claimReviewed": "Photo shows a flooded airport in Dubai in October 2026", "datePublished": "2026-10-14",
          "author": {"@type": "Organization", "name": "AFP Fact Check", "url": "https://factcheck.afp.com"},
          "reviewRating": {"@type": "Rating", "alternateName": "False"}}


def test_a_claimreview_is_found_alone_in_a_list_and_in_a_graph():
    alleen = ea.claimreviews(_pagina(json.dumps(REVIEW)))
    lijst = ea.claimreviews(_pagina(json.dumps([{"@type": "NewsArticle"}, REVIEW])))
    graaf = ea.claimreviews(_pagina(json.dumps({"@context": "https://schema.org",
                                                "@graph": [{"@type": "WebPage"}, {**REVIEW, "@type": ["ClaimReview"]}]})))
    assert [r["claimReviewed"] for r in alleen + lijst + graaf] == [REVIEW["claimReviewed"]] * 3


def test_broken_json_and_pages_without_a_claimreview_give_nothing():
    assert ea.claimreviews(_pagina('{"@type": "ClaimReview", "claimReviewed": "x",}')) == []
    assert ea.claimreviews(_pagina(json.dumps({"@type": "NewsArticle", "headline": "x"}))) == []
    assert ea.claimreviews("<html><body>geen gestructureerde data</body></html>") == []
    assert ea.claimreviews("") == []


SITE = {"naam": "AFP Fact Check", "host": "factcheck.afp.com", "taal": "en"}


def test_a_check_keeps_only_what_we_store_and_never_the_page():
    c = ea.check_uit(REVIEW, "https://factcheck.afp.com/doc.afp.com.ABC1", SITE)
    assert set(c) == {"adres", "site", "taal", "bewering", "oordeel", "categorie", "datum", "uitgever"}
    assert (c["bewering"], c["oordeel"], c["categorie"], c["datum"], c["taal"]) == (
        REVIEW["claimReviewed"], "False", "onwaar", "2026-10-14", "en")
    zonder = ea.check_uit({**REVIEW, "reviewRating": {"name": "Altered photo"}}, REVIEW["url"], SITE)
    assert zonder["categorie"] == "onbekend"


def test_a_sitemap_index_and_a_urlset_are_read_with_their_dates():
    index = ('<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
             '<sitemap><loc>https://x.org/sitemap-2026-10.xml</loc><lastmod>2026-10-31T10:00:00+00:00</lastmod></sitemap>'
             '<sitemap><loc>https://x.org/sitemap-2025-01.xml</loc><lastmod>2025-02-01</lastmod></sitemap></sitemapindex>')
    urls, kinderen = ea.sitemap(index)
    assert urls == [] and kinderen == [("https://x.org/sitemap-2026-10.xml", "2026-10-31"),
                                       ("https://x.org/sitemap-2025-01.xml", "2025-02-01")]
    assert ea.kinderen_kiezen(kinderen, "2026-10-02") == ["https://x.org/sitemap-2026-10.xml"]
    urlset = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
              'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
              '<url><loc>https://x.org/a</loc><lastmod>2026-10-20</lastmod></url>'
              '<url><loc>https://x.org/b</loc><news:news><news:publication_date>2026-10-05T08:00:00Z'
              '</news:publication_date></news:news></url>'
              '<url><loc>https://x.org/c</loc></url></urlset>')
    urls, kinderen = ea.sitemap(urlset)
    assert kinderen == [] and urls == [("https://x.org/a", "2026-10-20"), ("https://x.org/b", "2026-10-05"),
                                       ("https://x.org/c", None)]
    assert ea.sitemap("geen xml") == ([], [])


def test_only_checks_inside_the_window_count():
    assert ea.in_venster("2026-10-02") and ea.in_venster("2026-11-01")
    assert not ea.in_venster("2026-10-01") and not ea.in_venster("2026-11-02") and not ea.in_venster(None)


def test_an_address_already_in_the_database_is_not_new():
    bekend = {ea.adres("https://www.snopes.com/fact-check/dubai-airport/")}
    assert ea.adres("http://snopes.com/fact-check/dubai-airport?utm_source=x") in bekend
    assert ea.adres("https://www.snopes.com/fact-check/other/") not in bekend


_TELLER = itertools.count()


def _c(site, taal, nieuw=True, categorie="onwaar", adres=None):
    return {"site": site, "taal": taal, "nieuw": nieuw, "categorie": categorie,
            "adres": adres or f"https://{site}/{next(_TELLER)}"}


def test_the_goals_count_as_registered():
    checks = ([_c("AFP Factual", "es") for _ in range(200)] + [_c("Snopes", "en") for _ in range(90)]
              + [_c("AFP Checamos", "pt") for _ in range(10)] + [_c("AFP Faktencheck", "de") for _ in range(50)])
    gelezen = {c["adres"]: "klopt" for c in checks[:30]}
    sites = {"AFP Factual": {"status": [200]}, "Snopes": {"status": [200]}}
    uit = ea.telling(checks, sites, gelezen)
    assert uit["per taal"]["es"]["nieuw"] == 200 and uit["doelen"]["1. minstens 300 nieuwe checks in en, es en pt"]
    assert uit["doelen"]["2. minstens 95% van de oordelen herkend"]
    assert uit["doelen"]["3. bij de 30 gelezen hoogstens 1 fout"] and uit["doelen"]["4. geen site die ons weert"]
    minder = [c for c in checks if c["taal"] != "pt"][:299]
    assert not ea.telling(minder, sites, gelezen)["doelen"]["1. minstens 300 nieuwe checks in en, es en pt"]
    onbekend = [{**c, "categorie": "onbekend"} if i % 10 == 0 else c for i, c in enumerate(checks)]
    assert not ea.telling(onbekend, sites, gelezen)["doelen"]["2. minstens 95% van de oordelen herkend"]
    fout = {**gelezen, checks[0]["adres"]: "klopt niet", checks[1]["adres"]: "klopt niet"}
    assert not ea.telling(checks, sites, fout)["doelen"]["3. bij de 30 gelezen hoogstens 1 fout"]
    geweerd = {**sites, "Snopes": {"status": [200, 403]}}
    assert not ea.telling(checks, geweerd, gelezen)["doelen"]["4. geen site die ons weert"]


def test_counting_refuses_while_a_sampled_check_has_no_label():
    checks = [_c("Snopes", "en", adres=f"https://snopes.com/{i}") for i in range(40)]
    with pytest.raises(ea.Weigering):
        ea.telling(checks, {}, {}, steekproef=ea.steekproef(checks))
    gelezen = {a: "klopt" for a in ea.steekproef(checks)}
    assert ea.telling(checks, {}, gelezen, steekproef=ea.steekproef(checks))["gelezen"] == 30


def test_the_sample_is_thirty_new_checks_and_the_same_every_time():
    checks = [_c("Snopes", "en", adres=f"https://snopes.com/{i}") for i in range(100)] + \
             [_c("Snopes", "en", nieuw=False, adres=f"https://snopes.com/oud{i}") for i in range(10)]
    s = ea.steekproef(checks)
    assert len(s) == 30 and s == ea.steekproef(list(reversed(checks))) and not any("oud" in a for a in s)


def test_a_plain_text_sitemap_and_a_date_in_the_address_are_understood():
    urls, kinderen = ea.sitemap("https://leadstories.com/hoax-alert/2026/10/fact-check-x.html\n"
                                "https://leadstories.com/hoax-alert/2025/03/fact-check-y.html\n")
    assert kinderen == [] and [u for u, _ in urls] == ["https://leadstories.com/hoax-alert/2026/10/fact-check-x.html",
                                                       "https://leadstories.com/hoax-alert/2025/03/fact-check-y.html"]
    assert ea.datum_uit_adres("https://maldita.es/desinfo/20261030/x/") == "2026-10-30"
    assert ea.datum_uit_adres("https://estadao.com.br/arc/outboundfeeds/sitemap/2026-10-15/?outputType=xml") == "2026-10-15"
    assert ea.in_venster(ea.datum_uit_adres("https://leadstories.com/hoax-alert/2026/10/x.html"))
    assert not ea.in_venster(ea.datum_uit_adres("https://leadstories.com/hoax-alert/2026/09/x.html"))
    assert ea.datum_uit_adres("https://snopes.com/fact-check/x/") is None


def test_daily_sitemaps_are_chosen_by_the_date_in_their_address():
    kinderen = [(f"https://x.br/sitemap/2026-{m:02d}-{d:02d}/", "2026-10-31") for m in (1, 10, 11) for d in (1, 15)]
    gekozen = ea.kinderen_kiezen(kinderen)
    assert gekozen == ["https://x.br/sitemap/2026-11-01/", "https://x.br/sitemap/2026-10-15/"]


def test_quote_marks_in_a_claim_are_decoded_and_double_slashes_never_hide_a_known_address():
    r = {**REVIEW, "claimReviewed": "Musk says: &quot;I have a plan&quot; &#039;today&#039;"}
    assert ea.check_uit(r, REVIEW["url"], SITE)["bewering"] == "Musk says: \"I have a plan\" 'today'"
    assert ea.adres("https://www.snopes.com//fact-check/musk-midterms/") == ea.adres("https://snopes.com/fact-check/musk-midterms")


def test_a_page_that_trickles_in_is_cut_off_at_the_time_limit():
    """Le Monde hield een verbinding minutenlang open (#32.66): de leestijd per verzoek per keer was 30 s, maar een
    server die elke paar seconden een stukje stuurt, liep nooit af. Nu heeft een verzoek ook een grens voor het geheel."""
    tijd = iter(range(0, 1000, 10))
    stukjes = (b"x" * 10 for _ in range(1000))
    assert ea._lees_binnen(stukjes, klok=lambda: next(tijd), grens=60, max_bytes=10_000) is None


def test_a_page_that_arrives_in_time_is_read_whole_and_a_huge_one_is_refused():
    tijd = iter(range(100))
    assert ea._lees_binnen([b"ab", b"cd"], klok=lambda: next(tijd), grens=60, max_bytes=10) == b"abcd"
    tijd = iter(range(100))
    assert ea._lees_binnen([b"x" * 8, b"x" * 8], klok=lambda: next(tijd), grens=60, max_bytes=10) is None
