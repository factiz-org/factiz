"""Bonnetjes die blijven (PLAN #25.9).

Elke uitslag rust op een link naar de check van een redactie (DR1). Links
sterven: 5,2% van de bonnetjes is dood en Logically Facts helemaal (§67).
Dan blijft het oordeel staan en zegt het antwoord eerlijk dat de bron offline
is, met een archiefkopie als die er is. Streng in één richting: ten onrechte
"offline" zeggen is een foute uitspraak over een redactie, dus pas na twee
dode waarnemingen met minstens een dag ertussen.
"""

import threading
import time

from doublecheck.bonnetjes import (
    archief_uit_cdx,
    archiefgroepen,
    is_offline,
    link_status,
    neem_waar,
    ronde,
    sla_op,
    sleutel,
)
from doublecheck.config import load_config
from tests.test_api import MATCHED_TEKST, client  # noqa: F401  (fixture)

URL = "https://nieuwscheckers.nl/factcheck/zeespiegel-daalt"
T0 = "2026-10-14T10:00:00+00:00"
T12 = "2026-10-14T22:00:00+00:00"
T25 = "2026-10-15T11:00:00+00:00"
T50 = "2026-10-16T12:00:00+00:00"
T60 = "2026-10-16T22:00:00+00:00"


def _reeks(*waarnemingen):
    rij = None
    for uitkomst, tijdstip in waarnemingen:
        rij = neem_waar(rij, URL, uitkomst, tijdstip)
    return rij


# --- de regel voor offline ------------------------------------------------------


def test_one_dead_observation_never_makes_a_link_offline():
    rij = _reeks(("dood", T0))
    assert not is_offline(rij, 24)
    assert link_status(rij, 24)["status"] == "unclear"
    assert link_status(rij, 24)["offline_since"] is None


def test_two_dead_observations_a_day_apart_make_a_link_offline():
    rij = _reeks(("dood", T0), ("zacht-dood", T25))
    assert is_offline(rij, 24)
    status = link_status(rij, 24)
    assert status["status"] == "offline"
    assert status["offline_since"] == "2026-10-14"
    assert status["checked_on"] == "2026-10-15"


def test_two_dead_observations_within_a_day_are_not_enough():
    assert not is_offline(_reeks(("dood", T0), ("dood", T12)), 24)


def test_a_live_observation_ends_the_offline_series():
    rij = _reeks(("dood", T0), ("dood", T25), ("levend", T50))
    assert not is_offline(rij, 24)
    assert link_status(rij, 24)["status"] == "live"
    assert link_status(rij, 24)["last_seen_live"] == "2026-10-16"
    # Een nieuwe dode waarneming begint een nieuwe reeks, niet de oude.
    rij = neem_waar(rij, URL, "dood", T60)
    assert not is_offline(rij, 24)


def test_an_unclear_observation_neither_kills_nor_revives_a_link():
    """Een robotcontrole of time-out zegt niets over de link (#25.6)."""
    assert is_offline(_reeks(("dood", T0), ("onduidelijk", T12), ("dood", T25)), 24)
    rij = _reeks(("levend", T0), ("onduidelijk", T25))
    assert not is_offline(rij, 24)
    assert link_status(rij, 24)["status"] == "unclear"
    assert link_status(rij, 24)["last_seen_live"] == "2026-10-14"


def test_the_offline_rule_never_drops_below_a_day():
    """Twijfel versoepelt nooit: een kortere tussenpoos maakt een tijdelijke
    storing tot een uitspraak over een redactie."""
    assert load_config().bonnetjes.offline_na_uren >= 24


# --- archiefkopieën -------------------------------------------------------------


def test_the_archive_copy_is_the_latest_capture_before_the_link_died():
    regels = [
        ["original", "timestamp"],
        ["http://www.logicallyfacts.com/en/fact-check/x/", "20230101000000"],
        ["https://logicallyfacts.com/en/fact-check/x", "20240601120000"],
        ["https://logicallyfacts.com/en/fact-check/x", "20251101000000"],
        ["https://logicallyfacts.com/en/fact-check/ander", "20240101000000"],
    ]
    doden = {"https://www.logicallyfacts.com/en/fact-check/x": "2025-06-01T00:00:00+00:00"}
    gevonden = archief_uit_cdx(regels, doden)
    assert gevonden == {
        "https://www.logicallyfacts.com/en/fact-check/x": (
            "https://web.archive.org/web/20240601120000/https://logicallyfacts.com/en/fact-check/x",
            "2024-06-01",
        )
    }


def test_a_link_without_a_capture_before_its_death_gets_no_archive_copy():
    regels = [["original", "timestamp"], ["https://logicallyfacts.com/x", "20251101000000"]]
    assert archief_uit_cdx(regels, {"https://logicallyfacts.com/x": "2025-06-01T00:00:00+00:00"}) == {}


def test_the_resume_rows_of_the_archive_service_are_not_captures():
    """Met `showResumeKey` eindigt de uitvoer op een lege regel en een sleutel."""
    regels = [["original", "timestamp"], ["https://a.example/x", "20240101000000"], [], ["a.example/x 2024"]]
    assert set(archief_uit_cdx(regels, {"https://a.example/x": "2025-01-01T00:00:00+00:00"})) == {"https://a.example/x"}


def test_a_capture_that_was_not_a_working_page_is_no_archive_copy():
    """Een opname van een foutpagina of doorverwijzing is geen kopie van de check."""
    regels = [
        ["original", "timestamp", "statuscode"],
        ["https://a.example/x", "20240101000000", "200"],
        ["https://a.example/x", "20240601000000", "301"],
        ["https://a.example/x", "20240701000000", "404"],
    ]
    kopie = archief_uit_cdx(regels, {"https://a.example/x": "2025-01-01T00:00:00+00:00"})
    assert kopie["https://a.example/x"][1] == "2024-01-01"


def test_a_site_that_died_whole_gets_one_list_the_rest_single_lookups():
    doden = {f"https://www.logicallyfacts.com/en/{i}": "2026-10-14T00:00:00+00:00" for i in range(60)}
    doden["https://factly.in/een"] = "2026-10-14T00:00:00+00:00"
    groot, los = archiefgroepen(doden, 50)
    assert set(groot) == {"logicallyfacts.com"} and len(groot["logicallyfacts.com"]) == 60
    assert los == {"https://factly.in/een": "2026-10-14T00:00:00+00:00"}


def test_the_url_key_ignores_scheme_www_case_and_trailing_slash():
    assert sleutel("http://www.Example.com/A/b/") == sleutel("https://example.com/a/b")
    assert sleutel("https://example.com/a?p=1#kop") == sleutel("https://example.com/a?p=1")
    assert sleutel("https://example.com/a?p=1") != sleutel("https://example.com/a?p=2")


def test_the_link_status_carries_the_archive_copy():
    rij = _reeks(("dood", T0), ("dood", T25))
    rij = {**rij, "archief_url": "https://web.archive.org/web/2024/x", "archief_datum": "2024-06-01"}
    status = link_status(rij, 24)
    assert status["archive_url"] == "https://web.archive.org/web/2024/x"
    assert status["archived_on"] == "2024-06-01"


# --- de ronde -------------------------------------------------------------------


def test_a_host_behind_a_robot_check_is_skipped_after_the_probe():
    urls = [f"https://bots.example/{i}" for i in range(30)] + ["https://ok.example/1"]
    gevraagd, regels = [], []

    def controleer(url):
        gevraagd.append(url)
        return "onduidelijk" if "bots" in url else "levend"

    ronde(urls, controleer, lambda host: None, proef=10, pauze=0, schrijf=regels.append)
    assert sum("bots" in u for u in gevraagd) == 10
    overgeslagen = [r for r in regels if r["uitkomst"] == "overgeslagen"]
    assert len(overgeslagen) == 20 and all(r["reden"] == "robotcontrole" for r in overgeslagen)
    assert {"url": "https://ok.example/1", "uitkomst": "levend"}.items() <= next(
        r for r in regels if r["url"] == "https://ok.example/1").items()


def test_robots_txt_forbidden_links_are_never_requested():
    class Verbod:
        def can_fetch(self, agent, url):
            return "/prive/" not in url

    urls = ["https://a.example/prive/1", "https://a.example/open/1"]
    gevraagd, regels = [], []
    ronde(urls, lambda u: gevraagd.append(u) or "levend", lambda host: Verbod(), proef=10, pauze=0,
          schrijf=regels.append)
    assert gevraagd == ["https://a.example/open/1"]
    assert {r["url"]: r["uitkomst"] for r in regels}["https://a.example/prive/1"] == "verboden"


def test_a_round_resumes_without_asking_again():
    urls = ["https://a.example/1", "https://a.example/2"]
    gevraagd = []
    ronde(urls, lambda u: gevraagd.append(u) or "levend", lambda host: None, proef=10, pauze=0,
          schrijf=lambda r: None, gedaan={"https://a.example/1"})
    assert gevraagd == ["https://a.example/2"]


def test_requests_to_one_host_never_overlap():
    """Beleefd: per host één verzoek tegelijk, hosts wel naast elkaar."""
    bezig, hoogste, slot = {}, {}, threading.Lock()

    def controleer(url):
        host = url.split("/")[2]
        with slot:
            bezig[host] = bezig.get(host, 0) + 1
            hoogste[host] = max(hoogste.get(host, 0), bezig[host])
        time.sleep(0.005)
        with slot:
            bezig[host] -= 1
        return "levend"

    urls = [f"https://{h}.example/{i}" for h in ("a", "b", "c") for i in range(8)]
    ronde(urls, controleer, lambda host: None, proef=10, pauze=0, threads=4, schrijf=lambda r: None)
    assert hoogste == {"a.example": 1, "b.example": 1, "c.example": 1}


# --- het antwoord ---------------------------------------------------------------


def _verbinding():
    import doublecheck.api as api

    return api.app.dependency_overrides[api.get_conn]()


def test_a_check_with_an_offline_link_stays_in_the_answer_and_counts(client):  # noqa: F811
    voor = client.post("/resolve", json={"text": MATCHED_TEKST}).json()["evidence"]
    sla_op(_verbinding(), {**_reeks(("dood", T0), ("dood", T25)),
                           "archief_url": "https://web.archive.org/web/2024/x", "archief_datum": "2024-03-20"})
    na = client.post("/resolve", json={"text": MATCHED_TEKST}).json()
    assert na["category"] == "matched"
    bewijs = na["evidence"]
    assert bewijs["check_count"] == voor["check_count"]
    assert bewijs["publisher_count"] == voor["publisher_count"]
    check = next(c for c in bewijs["checks"] if c["url"] == URL)
    assert check["verdict_original"] == "Onjuist"
    assert check["link"] == {
        "status": "offline", "checked_on": "2026-10-15", "offline_since": "2026-10-14",
        "last_seen_live": None, "archive_url": "https://web.archive.org/web/2024/x",
        "archived_on": "2024-03-20",
    }


def test_a_link_that_was_never_checked_carries_no_status(client):  # noqa: F811
    checks = client.post("/resolve", json={"text": MATCHED_TEKST}).json()["evidence"]["checks"]
    assert checks and all(c["link"] is None for c in checks)


def test_the_demo_labels_an_offline_source_calmly_with_its_archive_copy(client):  # noqa: F811
    pagina = client.get("/").text
    assert "Source offline since at least" in pagina
    assert "Archived copy" in pagina
    assert "No archived copy found" in pagina


def test_an_interrupted_round_resumes_without_a_broken_line(tmp_path):
    """Een herstart midden in een schrijfactie laat een halve regel achter;
    die gaat weg, zodat de hervatte ronde er niet aan vast schrijft."""
    from doublecheck.beeldindex import herstel
    from doublecheck.bonnetjes import lees_ronde

    pad = tmp_path / "ronde.jsonl"
    pad.write_text('{"url": "https://a.example/1", "uitkomst": "levend", "tijdstip": "t"}\n{"url": "https://a.ex',
                   encoding="utf-8")
    herstel(pad)
    with pad.open("a", encoding="utf-8") as uit:
        uit.write('{"url": "https://a.example/2", "uitkomst": "dood", "tijdstip": "t"}\n')
    assert [r["url"] for r in lees_ronde(pad)] == ["https://a.example/1", "https://a.example/2"]
