"""De vooruitblik (PLAN #28.6 d): een release bevroren, gescoord op checks
die er nog niet waren toen hij uitkwam."""

import json

import pytest

from doublecheck import vooruitblik as vb


def _feed(elementen, nieuwste="2026-10-20T03:00:00+00:00"):
    # `dateModified` is het moment van ophalen, dus elke keer anders.
    return {"@context": "https://schema.org", "@type": "DataFeed",
            "dataFeedElement": [{"dateCreated": nieuwste}, *elementen],
            "dateModified": "2026-10-21T00:00:00+00:00", "name": "test"}


def _check(url, datum, post, claim="x"):
    return {"item": [{"url": url, "datePublished": datum, "claimReviewed": claim,
                      "itemReviewed": {"appearance": [{"url": post}]}}]}


def test_a_freeze_is_written_once_and_never_moved(tmp_path):
    pad = tmp_path / "bevroren.json"
    record = {"release": "factiz-1-rechter", "moment": "2026-10-17T21:00:00+00:00"}
    vb.bevries(pad, record)
    with pytest.raises(vb.AlBevroren):
        vb.bevries(pad, record | {"moment": "2026-10-20T00:00:00+00:00"})
    data = json.loads(pad.read_text())
    assert data["bevroren"] == [record] and data["toelichting"]


def test_the_index_fingerprint_ignores_order_but_not_membership():
    assert vb.index_vingerafdruk(["b", "a"]) == vb.index_vingerafdruk(["a", "b"])
    assert vb.index_vingerafdruk(["a", "b"]) != vb.index_vingerafdruk(["a", "c"])


def test_the_stand_of_a_feed_is_its_newest_element_not_its_download_moment(tmp_path):
    pad = tmp_path / "feed.json"
    pad.write_text(json.dumps(_feed([{"dateCreated": "2026-10-19T01:02:03+00:00"}])))
    assert vb.feedstand(pad) == "2026-10-20T030000"


def test_a_download_with_a_known_feed_date_is_dropped_and_only_two_are_kept(tmp_path):
    map_ = tmp_path / "feed"
    for datum in ("2026-10-06", "2026-10-13", "2026-10-20"):
        nieuw = tmp_path / "download.json"
        nieuw.write_text(json.dumps(_feed([], f"{datum}T03:00:00+00:00")))
        assert vb.bewaar(nieuw, map_) == map_ / f"feed-{datum}T030000.json"
    nieuw.write_text(json.dumps(_feed([], "2026-10-20T03:00:00+00:00")))
    assert vb.bewaar(nieuw, map_) is None
    assert not nieuw.exists()
    assert sorted(p.name for p in map_.iterdir()) == ["feed-2026-10-13T030000.json", "feed-2026-10-20T030000.json"]


def test_a_fresh_positive_is_a_later_check_of_a_post_checked_before_the_freeze():
    post = "https://twitter.com/iemand/status/1"
    elementen = [
        _check("https://redactie.a/oud", "2026-09-01", post),       # in het geheugen van de bevriezing
        _check("https://redactie.b/nieuw", "2026-10-12", post, "y"),  # vers: na de bevriezing, zelfde post
        _check("https://redactie.c/los", "2026-10-13", "https://twitter.com/ander/status/2"),
        _check("https://redactie.d/vroeg", "2026-10-02", post),     # vóór de bevriezing: geen vers stuk
    ]
    geheugen = {"https://redactie.a/oud": "claim-oud", "https://redactie.d/vroeg": "claim-vroeg"}
    vers = vb.verse_positieven(elementen, geheugen, "2026-10-05")
    assert [(v["url"], sorted(v["doelen"])) for v in vers] == [
        ("https://redactie.b/nieuw", ["claim-oud", "claim-vroeg"])]
    assert vb.nieuwe_checks(elementen, "2026-10-05") == 2


def test_the_feed_is_only_downloaded_when_its_version_mark_changed(tmp_path):
    pad = tmp_path / "etag.json"
    assert vb.nieuwe_versie('"abc"', pad)  # nog niets gezien
    vb.onthoud_versie('"abc"', pad)
    assert not vb.nieuwe_versie('"abc"', pad)
    assert vb.nieuwe_versie('"def"', pad)
    assert vb.nieuwe_versie(None, pad)  # geen kenmerk: twijfel versoepelt nooit, dus toch ophalen


def test_the_refresh_runs_the_corpus_builder_behind_the_heat_guard_on_two_cores(tmp_path):
    feed = tmp_path / "feed-2026-10-28T141842.json"
    opdracht, omgeving = vb.bijwerkopdracht(feed, tmp_path / "hitte.log")
    assert opdracht[1:4] == ["-m", "doublecheck.hittewacht", "--log"]
    assert opdracht[opdracht.index("--") + 1:] == [opdracht[0], "-m", "doublecheck.bootstrap", "--cache", str(feed),
                                                   "--met-veto"]
    assert omgeving["OMP_NUM_THREADS"] == "2" and omgeving["MKL_NUM_THREADS"] == "2"
