"""De bewaking van factiz.org (PLAN #34.2bv): de Worker telt storingen (antwoorden van 500 of hoger) zonder iets van de
bezoeker, en `factiz_site.bewaking` vraagt elk uur pagina's op die niet uit de cache komen, kijkt robots.txt na bij de stand
en meldt een nieuwe storing; geen mail, geen dienst van een ander."""

import plistlib
import random
import re
from pathlib import Path

from factiz_site import bewaking as bw
from factiz_site import i18n, tellen

WORTEL = Path(__file__).resolve().parent.parent
SITE = WORTEL / "site" / "src"
DICHT = "User-agent: *\nDisallow: /\n"
OPEN = "User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: https://factiz.org/sitemap.xml\n"


def _haal(standen: dict, robots: str = DICHT):
    def haal(pad):
        status, duur = standen.get(pad, (200, 0.3))
        return status, duur, robots if pad == "/robots.txt" else ""
    return haal


def _vandaag():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def test_the_check_reads_the_step_and_the_release_from_the_config_of_the_worker():
    config = (WORTEL / "site" / "wrangler.jsonc").read_text(encoding="utf-8")
    assert bw.stand_uit(config) == 2                                  # stand 2 sinds 2026-11-22 (PO: "etappe 2 live", B73)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d[a-z]?", bw.uitgave_uit(config))
    from doublecheck import indexnow
    assert indexnow.stand_uit is bw.stand_uit                         # één regel voor de uitrol en de bewaking


def test_every_round_asks_new_fact_checks_and_share_images_that_cannot_come_from_the_cache():
    rng = random.Random(1)
    paden = bw.adressen(["0123456789abcdef", "fedcba9876543210"], rng)
    assert paden[:len(bw.VAST)] == list(bw.VAST) and "/robots.txt" in paden
    plaatjes = [p for p in paden if p.startswith("/deelbeeld/")]
    assert len(plaatjes) == 2 and all(re.fullmatch(r"/deelbeeld/[a-z]+/[0-9a-f]{16}\.jpg", p) for p in plaatjes)
    paginas = [p for p in paden if "/fact-checks/" in p and p != "/fact-checks/"]
    assert len(paginas) == 2 and all(i18n.taal_van_pad(p) in i18n.TALEN for p in paginas)


def test_a_good_round_says_good_and_every_kind_of_trouble_is_named():
    paden = ["/", "/nl/", "/robots.txt", "/fact-checks/0123456789abcdef/"]
    goed = bw.nakijken(paden, 0, [], None, haal=_haal({}))
    assert goed["goed"] is True and goed["problemen"] == [] and goed["gevraagd"] == 4
    mis = bw.nakijken(paden, 0, None, None, haal=_haal({"/nl/": (500, 1.0), "/": (0, 45.0),
                                                        "/fact-checks/0123456789abcdef/": (200, 31.0)}))
    assert mis["goed"] is False
    assert mis["problemen"] == ["/ gaf geen antwoord", "/nl/ gaf 500", "/fact-checks/0123456789abcdef/ duurde 31 s"]


def test_robots_must_match_the_step_in_the_config():
    assert bw.robots_klopt(DICHT, 0) is None and bw.robots_klopt(OPEN, 1) is None
    assert bw.robots_klopt(OPEN, 0) == "robots.txt staat open, maar de stand is 0"
    assert bw.robots_klopt(DICHT, 2) == "robots.txt past niet bij stand 2"
    r = bw.nakijken(["/robots.txt"], 3, None, None, haal=_haal({}, robots=DICHT))
    assert r["problemen"] == ["robots.txt past niet bij stand 3"]


def test_a_new_server_error_since_the_last_round_is_trouble_and_an_old_one_is_not():
    dag = _vandaag()
    rijen = [(dag, "storing", "en", 2), (dag, "storing", "nl", 1), (dag, "factcheck", "en", 40), ("2020-01-01", "storing", "en", 5)]
    assert bw.storingen(rijen) == {"2020-01-01": 5, dag: 3}
    eerste = bw.nakijken(["/"], 0, rijen, None, haal=_haal({}))
    assert eerste["problemen"] == ["3 nieuwe storing(en) vandaag, 3 samen"]
    tweede = bw.nakijken(["/"], 0, rijen, eerste, haal=_haal({}))
    assert tweede["goed"] is True                                     # dezelfde drie: geen nieuwe melding


def test_the_worker_counts_a_server_error_without_anything_of_the_visitor():
    midden = (SITE / "middleware.js").read_text(encoding="utf-8")
    assert "if (antwoord.status >= 500) telStoring(context.url);" in midden and "telStoring(context.url);\n    throw fout;" in midden
    platform = (SITE / "lib" / "platform.js").read_text(encoding="utf-8")
    functie = platform[platform.index("export function telStoring"):platform.index("export function tel(")]
    assert "telBezoek('storing', taal)" in functie and "headers" not in functie and "search" not in functie
    gedeeld = (SITE / "platform" / "gedeeld.ts").read_text(encoding="utf-8")
    assert "'storing'" in re.search(r"const WAT = new Set\(\[[^\]]+\]\);", gedeeld).group(0)
    assert "storing" in tellen.WAT
    assert "storingen 2" in tellen._regels([("2026-11-17", "storing", "en", 2), ("2026-11-17", "start", "en", 5)])


def test_the_daily_job_runs_the_check_with_a_notice_and_logs_in_data():
    """PO 2026-11-17: "Uurlijkse check vind ik iets te veel, is dagelijks genoeg?": elke dag, 's ochtends."""
    taak = plistlib.loads((WORTEL / "deploy" / "org.factiz.bewaking.plist").read_bytes())
    assert taak["Label"] == "org.factiz.bewaking" and "StartInterval" not in taak
    assert taak["StartCalendarInterval"] == {"Hour": 9, "Minute": 7}
    # launchd begint met een kale PATH; wrangler heeft node nodig om de storingen in D1 te lezen
    assert any(Path(map_, "node").exists() for map_ in taak["EnvironmentVariables"]["PATH"].split(":"))
    opdracht = taak["ProgramArguments"][-1]
    assert "-m factiz_site.bewaking --melding" in opdracht and ">> data/bewaking/launchd.log" in opdracht
