"""Anoniem tellen (PLAN #34.2ba, SPECS E9.S26, B78): per dag, soort pagina en taal een getal, en per dag en taal de
zoekvragen, die zonder resultaat en de geplakte berichten. Nooit een IP-adres, cookie, zoektekst, adres of user-agent."""

import re
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import i18n, tellen
from tests.test_publiceren import REGISTER, _check, _claim, _lab

DAG = "2026-11-15"
GEHEIM = "qzxwvplorbtrek dit is een geheime zoekvraag van iemand"
SITE = Path(__file__).resolve().parent.parent / "site" / "src"


@pytest.fixture(scope="module")
def uitgave(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("tellen")
    lab = _lab(map_)
    for i in range(3):
        _check(lab, _claim(lab, 1 + i, f"A bridge collapsed in town number {i}"), f"https://snopes.com/b{i}")
    lab.commit()
    return pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum=DAG)["bestand"]


@pytest.fixture
def app(uitgave, tmp_path, monkeypatch):
    monkeypatch.setattr(tellen, "vandaag", lambda: DAG)
    bestand = tmp_path / "tellingen.db"
    toepassing = fa.maak_app(uitgave, tellingen=bestand)
    return TestClient(toepassing), toepassing.state.teller, bestand


def _rijen(bestand):
    with sqlite3.connect(bestand) as c:
        return sorted(c.execute("SELECT dag, wat, taal, n FROM telling"))


def test_a_visit_and_a_search_are_counted_by_day_kind_and_language(app):
    client, teller, bestand = app
    assert client.post("/api/tel", data={"soort": "factcheck", "taal": "nl"}).status_code == 204
    client.post("/api/tel", data={"soort": "factcheck", "taal": "nl"})
    client.post("/api/tel", data={"soort": "lijst", "taal": "en"})
    assert client.post("/api/nl/zoek", data={"q": "bridge"}).json()["totaal"] > 0
    assert client.post("/api/nl/zoek", data={"q": GEHEIM}).json()["totaal"] == 0
    teller.wegschrijven()
    assert _rijen(bestand) == [(DAG, "factcheck", "nl", 2), (DAG, "lijst", "en", 1), (DAG, "zoek", "nl", 2),
                               (DAG, "zoek-bericht", "nl", 1), (DAG, "zoek-zonder", "nl", 1)]


def test_the_next_page_of_a_search_and_an_empty_question_do_not_count_again(app):
    client, teller, bestand = app
    client.post("/api/nl/zoek", data={"q": "bridge", "p": "2"})
    client.post("/api/nl/zoek", data={"q": ""})
    teller.wegschrijven()
    assert _rijen(bestand) == []


def test_only_day_kind_language_and_a_number_are_kept_and_never_the_question(app):
    client, teller, bestand = app
    client.post("/api/nl/zoek", data={"q": GEHEIM}, headers={"user-agent": "Mozilla/5.0 test", "x-forwarded-for": "203.0.113.9"})
    client.post("/api/tel", data={"soort": "over", "taal": "de"})
    teller.wegschrijven()
    with sqlite3.connect(bestand) as c:
        tabellen = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        kolommen = [r[1] for r in c.execute("PRAGMA table_info(telling)")]
    assert tabellen == ["telling"] and kolommen == ["dag", "wat", "taal", "n"]
    inhoud = b"".join(f.read_bytes() for f in bestand.parent.glob("tellingen.db*"))
    for spoor in (b"qzxwvplorbtrek", b"203.0.113.9", b"Mozilla"):
        assert spoor not in inhoud


def test_an_unknown_kind_or_language_is_refused_and_a_robot_counts_apart(app):
    client, teller, bestand = app
    assert client.post("/api/tel", data={"soort": "<script>", "taal": "nl"}).status_code == 400
    assert client.post("/api/tel", data={"soort": "factcheck", "taal": "xx"}).status_code == 400
    assert client.post("/api/tel", data={"soort": "factcheck", "taal": "nl", "robot": "1"}).status_code == 204
    teller.wegschrijven()
    assert _rijen(bestand) == [(DAG, "robot", "nl", 1)]


def test_two_counters_on_one_file_add_up(tmp_path, monkeypatch):
    monkeypatch.setattr(tellen, "vandaag", lambda: DAG)
    a, b = tellen.Teller(tmp_path / "t.db", interval=0), tellen.Teller(tmp_path / "t.db", interval=0)
    for teller in (a, b, a):
        teller.tel("start", "en")
        teller.wegschrijven()
    assert _rijen(tmp_path / "t.db") == [(DAG, "start", "en", 3)]


def test_without_a_file_nothing_is_counted_and_no_file_appears(uitgave, tmp_path, monkeypatch):
    monkeypatch.delenv("FACTIZ_TELLINGEN", raising=False)
    monkeypatch.chdir(tmp_path)
    toepassing = fa.maak_app(uitgave)
    client = TestClient(toepassing)
    assert client.post("/api/tel", data={"soort": "start", "taal": "en"}).status_code == 204
    client.post("/api/en/zoek", data={"q": "bridge"})
    toepassing.state.teller.wegschrijven()
    assert toepassing.state.teller.bestand is None and list(tmp_path.iterdir()) == []


def test_the_overview_shows_each_day_with_the_share_of_searches_without_result(tmp_path, monkeypatch):
    monkeypatch.setattr(tellen, "vandaag", lambda: DAG)
    t = tellen.Teller(tmp_path / "t.db", interval=0)
    for wat, n in (("factcheck", 5), ("zoek", 4), ("zoek-zonder", 1), ("robot", 7)):
        t.tel(wat, "nl", n)
    t.wegschrijven()
    tekst = tellen.overzicht(tmp_path / "t.db")
    assert DAG in tekst and "factcheck 5" in tekst and "zoekvragen 4" in tekst and "zonder resultaat 1 (25%)" in tekst
    assert "robots 7" in tekst


def test_the_site_reports_the_kind_of_page_without_waiting_and_never_forwards_the_counter():
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    # na elke doorverwijzing, vóór de pagina; zonder await, zodat een bezoeker nooit wacht
    assert router.index("Astro.redirect(pagina.g.doorsturen") < router.index("tel(pagina.soort, taal, Astro.request)")
    assert "await tel(" not in router
    platform = (SITE / "lib" / "platform.js").read_text(encoding="utf-8")
    tel = platform[platform.index("export function tel("):]
    # sinds B80 telt de site zelf, met het platform in TypeScript (`telBezoek`); een teller die faalt breekt niets
    assert "telBezoek(" in tel and "catch" in tel and "user-agent" in tel and "await" not in tel
    assert "x-forwarded-for" not in tel.lower() and "cookie" not in tel.lower()
    doorgegeven = {p.stem for p in (SITE / "pages" / "[taal]" / "api").rglob("*.js")}
    assert "tel" not in doorgegeven


@pytest.mark.parametrize("taal", i18n.TALEN)
def test_about_says_what_we_count(taal):
    zin = i18n.tekst(taal, "over_privacy_tellen")
    assert zin and "!" not in zin and "—" not in zin
    over = (SITE / "components" / "site" / "paginas" / "Over.astro").read_text(encoding="utf-8")
    assert "over_privacy_tellen" in over


def test_the_overview_reads_the_counts_of_the_worker_from_d1_the_same_way(tmp_path, monkeypatch):
    # de Worker telt in D1 (`TELLINGEN`, PLAN #34.2bo stap 8); het overzicht leest daar alleen, met dezelfde vraag
    monkeypatch.setattr(tellen, "vandaag", lambda: DAG)
    t = tellen.Teller(tmp_path / "t.db", interval=0)
    for wat, n in (("factcheck", 5), ("start", 2), ("zoek", 4), ("zoek-zonder", 1), ("robot", 7)):
        t.tel(wat, "nl", n)
    t.wegschrijven()
    gevraagd = []

    def wrangler(args):
        gevraagd.append(args)
        return '[{"results": [' + ",".join(
            f'{{"dag": "{d}", "wat": "{w}", "taal": "{l}", "n": {n}}}' for d, w, l, n in _rijen(tmp_path / "t.db")) + \
            '], "success": true, "meta": {}}]'

    assert tellen.overzicht_d1("factiz-tellingen", 14, voer_uit=wrangler) == tellen.overzicht(tmp_path / "t.db")
    [args] = gevraagd
    assert args[:5] == ["d1", "execute", "factiz-tellingen", "--remote", "--json"]
    assert args[-1].lstrip().upper().startswith("SELECT") and "LIMIT 14" in args[-1]
    with pytest.raises(SystemExit):
        tellen.overzicht_d1("factiz-tellingen", voer_uit=lambda args: '[{"success": false}]')


def test_the_worker_counts_into_its_own_d1_with_the_same_table():
    worker = (SITE / "lib" / "gegevens-worker.js").read_text(encoding="utf-8")
    erbij = re.search(r"const ERBIJ = '([^']+)'", worker).group(1)
    assert erbij.startswith("INSERT INTO telling (dag, wat, taal, n) VALUES (?, ?, ?, 1)")
    assert "ON CONFLICT (dag, wat, taal) DO UPDATE SET n = n + 1" in erbij
    assert "PRIMARY KEY (dag, wat, taal)" in tellen.SCHEMA
    config = re.sub(r"^\s*//.*$", "", (SITE.parent / "wrangler.jsonc").read_text(encoding="utf-8"), flags=re.M)
    import json
    banden = {d["binding"]: d["database_name"] for d in json.loads(config)["d1_databases"]}
    assert banden["TELLINGEN"] == "factiz-tellingen" and banden["DB"].startswith("factiz-20")


def test_a_page_counts_even_when_it_is_the_first_thing_a_fresh_server_shows(uitgave, tmp_path):
    # Over leest niets uit de uitgave, en een bezoek uit de paginacache ook niet: de teller moet er dan toch zijn
    # (op factiz.org telde een nieuwe Worker die zo begon niets, 2026-11-16)
    import os
    import subprocess
    import urllib.request

    from tests import websitebouw
    from tests.test_site_html import _vrije_poort, _wacht

    poort, tellingen = _vrije_poort(), tmp_path / "tellingen.db"
    omgeving = {k: v for k, v in os.environ.items() if k not in ("FACTIZ_VINDBAAR", "FACTIZ_GEHEUGEN")}
    omgeving |= {"HOST": "127.0.0.1", "PORT": str(poort), "FACTIZ_PUBLICATIE": str(uitgave), "FACTIZ_TELLINGEN": str(tellingen)}
    node = subprocess.Popen(["node", str(websitebouw.site())], env=omgeving, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        _wacht(f"http://127.0.0.1:{poort}/robots.txt")                      # telt niet: geen pagina van de site
        verzoek = urllib.request.Request(f"http://127.0.0.1:{poort}/fr/about/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(verzoek, timeout=30) as r:
            assert r.status == 200
    finally:
        node.terminate()
        node.wait(timeout=10)
    assert [r[1:] for r in _rijen(tellingen)] == [("over", "fr", 1)]
