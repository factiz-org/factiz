"""Eén commando voor een uitgave (PLAN #34.2bo stap 9): eerst wat op de Mac gebeurt, dan pas het account, met een akkoord
van de PO, in een vaste volgorde die na een fout hervat zonder twee keer in dezelfde database te importeren."""

import json

import pytest

from doublecheck import uitrol as ur

CONFIG = """// de site als Worker
{
  "name": "factiz-site",
  // DB: de uitgave. TELLINGEN: de tellingen
  "d1_databases": [
    { "binding": "DB", "database_name": "factiz-2026-11-16", "database_id": "086a5ec4-4f41-4ed4-8076-f8a974b46ad2" },
    { "binding": "TELLINGEN", "database_name": "factiz-tellingen", "database_id": "eb27ad4d-8b89-482c-adc2-31944946ebdd" }
  ]
}
"""


def test_the_worker_gets_the_new_database_and_nothing_else_in_its_config_changes():
    nieuw = ur.zet_database(CONFIG, "factiz-2026-11-17", "b0dbf87c-8874-40f7-8d09-65205794616f")
    assert ur.lees_database(CONFIG) == ("factiz-2026-11-16", "086a5ec4-4f41-4ed4-8076-f8a974b46ad2")
    assert ur.lees_database(nieuw) == ("factiz-2026-11-17", "b0dbf87c-8874-40f7-8d09-65205794616f")
    assert nieuw.replace("factiz-2026-11-17", "factiz-2026-11-16").replace(
        "b0dbf87c-8874-40f7-8d09-65205794616f", "086a5ec4-4f41-4ed4-8076-f8a974b46ad2") == CONFIG
    with pytest.raises(ur.Weigering):
        ur.zet_database(CONFIG.replace('"binding": "DB"', '"binding": "X"'), "factiz-2026-11-17", "b0dbf87c-8874-40f7-8d09-65205794616f")
    with pytest.raises(ur.Weigering):
        ur.zet_database(CONFIG, "factiz-2026-11-17", "geen-id")


def test_without_a_name_a_release_takes_today_or_today_with_the_next_letter():
    assert ur.volgende_naam(set(), "2026-11-17") == "2026-11-17"
    assert ur.volgende_naam({"2026-11-16", "2026-11-17"}, "2026-11-17") == "2026-11-17b"
    assert ur.volgende_naam({"2026-11-17", "2026-11-17b", "2026-11-17c"}, "2026-11-17") == "2026-11-17d"


def test_going_live_needs_the_words_of_the_po_with_a_date():
    assert ur.akkoord('2026-11-17, PO: "Yes, release it"') == '2026-11-17, PO: "Yes, release it"'
    for fout in ("", "ja", 'PO: "ja"', '2026-11-17, Claude: "ja"', '2026-11-17, PO: ""'):
        with pytest.raises(ur.Weigering):
            ur.akkoord(fout)


def test_going_live_refuses_when_the_preparation_is_not_finished(tmp_path):
    map_ = tmp_path / "2026-11-17"
    assert ur.niet_klaar(map_, "2026-11-17") == ["de SQL voor D1 ontbreekt (voorbereiden)",
                                                   "het geheugen ontbreekt (voorbereiden)"]
    (map_ / "geheugen").mkdir(parents=True)
    (map_ / "klaar.json").write_text(json.dumps({"release": "2026-11-17", "delen": []}))
    (map_ / "geheugen" / "index.json").write_text(json.dumps({"release": "2026-11-16", "stukken": []}))
    assert ur.niet_klaar(map_, "2026-11-17") == ["het geheugen is van 2026-11-16, niet van 2026-11-17"]
    (map_ / "geheugen" / "index.json").write_text(json.dumps({"release": "2026-11-17", "stukken": []}))
    assert ur.niet_klaar(map_, "2026-11-17") == []


def test_after_a_failure_it_resumes_where_it_stopped_and_never_imports_twice(tmp_path):
    stand = tmp_path / "uitrol.json"
    gedaan = []

    def stap(naam, faalt=False):
        def doe(s):
            if faalt:
                raise RuntimeError(f"{naam} mislukt")
            gedaan.append(naam)
            return {"klaar": naam}
        return doe

    eerst = {n: stap(n, faalt=(n == "nakijken")) for n in ur.LIVE}
    with pytest.raises(RuntimeError):
        ur.voer_uit(eerst, stand, akkoord_='2026-11-17, PO: "ja"', release="2026-11-17")
    assert gedaan == ["aanmaken", "importeren"]
    bewaard = json.loads(stand.read_text())
    assert list(bewaard["stappen"]) == ["aanmaken", "importeren"] and bewaard["akkoord"] == '2026-11-17, PO: "ja"'
    ur.voer_uit({n: stap(n) for n in ur.LIVE}, stand, akkoord_='2026-11-17, PO: "ja"', release="2026-11-17")
    assert gedaan == ["aanmaken", "importeren", *ur.LIVE[2:]]                    # importeren één keer
    assert list(json.loads(stand.read_text())["stappen"]) == list(ur.LIVE)
    # een stand van een andere uitgave hervat nooit
    with pytest.raises(ur.Weigering):
        ur.voer_uit({n: stap(n) for n in ur.LIVE}, stand, akkoord_='2026-11-17, PO: "ja"', release="2026-11-18")


def test_every_step_sees_what_the_earlier_steps_found():
    gezien = {}

    def stap(naam):
        def doe(s):
            gezien[naam] = dict(s["stappen"])
            return {"van": naam}
        return doe

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        ur.voer_uit({n: stap(n) for n in ur.LIVE}, Path(d) / "uitrol.json", akkoord_='2026-11-17, PO: "ja"',
                    release="2026-11-17")
    assert gezien["importeren"] == {"aanmaken": {"van": "aanmaken"}}


def test_factiz_org_counts_as_live_only_with_the_new_release_and_closed_robots():
    html = '<img src="/deelbeeld/en/0123456789abcdef.jpg?v=2026-11-17">'
    assert ur.live_klopt(200, html, "User-agent: *\nDisallow: /\n", "2026-11-17") == []
    assert ur.live_klopt(200, html.replace("2026-11-17", "2026-11-16b"), "User-agent: *\nDisallow: /\n",
                         "2026-11-17") == ["factiz.org toont nog niet de uitgave 2026-11-17"]
    assert ur.live_klopt(500, html, "User-agent: *\nAllow: /\n", "2026-11-17") == [
        "de factcheckpagina gaf 500", "robots.txt zet de site niet dicht"]
    # een andere uitgave met dezelfde dag als begin telt niet
    assert ur.live_klopt(200, html.replace("2026-11-17", "2026-11-17b"), "User-agent: *\nDisallow: /\n",
                         "2026-11-17") == ["factiz.org toont nog niet de uitgave 2026-11-17"]


def test_the_version_comes_from_what_wrangler_says_after_deploying():
    uit = "Uploaded factiz-site (15.69 sec)\nDeployed factiz-site triggers (5.21 sec)\n  factiz.org (custom domain)\n" \
          "Current Version ID: 44d77b5b-52b4-462a-a32a-d9b2635e5d1e\n"
    assert ur.versie_uit(uit) == "44d77b5b-52b4-462a-a32a-d9b2635e5d1e"
    with pytest.raises(ur.Weigering):
        ur.versie_uit("Uploaded factiz-site\n✘ [ERROR] partially updated")


def test_a_release_that_already_runs_is_never_rolled_out_again():
    assert ur.al_live(CONFIG, "2026-11-16", None) is True                       # de Worker leest haar al
    assert ur.al_live(CONFIG, "2026-11-17", None) is False
    assert ur.al_live(CONFIG, "2026-11-17", {"stappen": {"aanmaken": {}, "uitrollen": {}}}) is True
    assert ur.al_live(CONFIG, "2026-11-17", {"stappen": {"aanmaken": {}}}) is False


def test_in_an_open_step_factiz_org_counts_as_live_only_with_the_open_robots_and_the_sitemap():
    """PLAN #34.2bt: na het openzetten zegt robots.txt de sitemap en zet het de site niet meer dicht."""
    html = '<meta property="og:image" content="https://factiz.org/deelbeeld/en/0001.jpg?v=2026-11-17">'
    open_ = "User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://factiz.org/sitemap.xml\n"
    assert ur.live_klopt(200, html, open_, "2026-11-17", stand=1) == []
    assert ur.live_klopt(200, html, "User-agent: *\nDisallow: /\n", "2026-11-17", stand=2) == [
        "robots.txt staat niet open zoals stand 2 zegt"]
    assert ur.live_klopt(200, html, open_, "2026-11-17") == ["robots.txt zet de site niet dicht"]
    assert ur.LIVE[-1] == "melden"
