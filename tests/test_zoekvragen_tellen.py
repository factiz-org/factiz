"""Wat mensen zoeken, anoniem en opgeteld (B94, PLAN #37.17; PO 2026-11-23: "ik zou het wel graag weten, wat mensen zoeken,
zolang het maar anoniem is en niet gekoppeld aan cookie", en "Akkoord met de grenzen van B94"): per dag en sitetaal de
getypte zoekvraag met haar aantal; nooit een IP, cookie, user-agent of tijdstip, een robot of een geplakt bericht; wat in
zeven dagen minder dan drie keer kwam, gaat weg."""

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from factiz_site import i18n, tellen

WORTEL = Path(__file__).resolve().parent.parent
SITE = WORTEL / "site"


def _node(script: str):
    uit = subprocess.run(["node", "--input-type=module", "-e", script], cwd=SITE, capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


def _module():
    """De regel en de SQL zoals de site ze gebruikt (`src/lib/zoekvragen.js`)."""
    return _node("import('./src/lib/zoekvragen.js').then((m) => console.log(JSON.stringify("
                 "{ schema: m.SCHEMA, erbij: m.ERBIJ, opruimen: m.OPRUIMEN })))")


def test_only_a_plain_first_typed_search_by_a_person_is_kept_and_without_contact_details():
    gevallen = [
        ("q=Zelensky++Yacht", {"bericht": False}, False),            # gewoon: kleine letters, spaties samen
        ("q=zelensky+yacht&letterlijk=1", {"bericht": False}, False),  # tussen aanhalingstekens mag
        ("q=zelensky&thema=war", {"bericht": False}, False),         # met een filter: een klik verder, niet nog eens
        ("q=zelensky&thema=", {"bericht": False}, False),            # een leeg veld telt niet als filter
        ("q=zelensky&p=2", {"bericht": False}, False),               # het tweede blad
        ("q=zelensky&sorteer=oud", {"bericht": False}, False),       # een andere volgorde
        ("q=zelensky", {"bericht": False}, True),                    # een robot
        ("q=Help+little+Ana+share", {"bericht": True}, False),       # een geplakt bericht
        ("q=a+b+c+d+e+f+g+h+i", {"bericht": False}, False),          # meer dan acht woorden
        ("q=mail+jan%40example.com", {"bericht": False}, False),     # een e-mailadres
        ("q=bel+06+12345678", {"bericht": False}, False),            # een telefoonnummer
        ("q=covid+2021", {"bericht": False}, False),                 # een jaartal mag
        ("q=zelensky", None, False),                                 # geen antwoord van het platform
    ]
    script = ("import('./src/lib/zoekvragen.js').then((m) => console.log(JSON.stringify("
              f"{json.dumps(gevallen)}.map(([b, body, robot]) => m.zoekvraagVoorTellen(b, body, robot)))))")
    assert _node(script) == ["zelensky yacht", "zelensky yacht", None, "zelensky", None, None, None, None, None, None,
                             None, "covid 2021", None]


def _db(tmp_path, rijen):
    m = _module()
    c = sqlite3.connect(tmp_path / "t.db")
    c.execute(m["schema"])
    for dag, taal, vraag, n in rijen:
        for _ in range(n):
            c.execute(m["erbij"], (dag, taal, vraag))
    c.commit()
    return c, m


def test_what_came_fewer_than_three_times_in_seven_days_goes_and_the_rest_stays(tmp_path):
    vandaag = "2026-12-20"
    grens = "2026-12-13"                                     # zeven dagen terug: hun week is helemaal voorbij
    c, m = _db(tmp_path, [
        ("2026-12-01", "nl", "jan de vries", 1),             # één keer, ooit: weg
        ("2026-12-01", "nl", "zelensky yacht", 1),           # samen drie keer in zeven dagen: blijft, ook de latere dag
        ("2026-12-03", "nl", "zelensky yacht", 2),
        ("2026-12-02", "de", "drei tage", 1),                # drie keer, maar verspreid over meer dan zeven dagen: weg
        ("2026-12-08", "de", "drei tage", 1),
        ("2026-12-13", "de", "drei tage", 1),
        ("2026-12-10", "en", "bill gates chips", 2),         # twee keer: weg
        ("2026-12-12", "en", "nato expansion", 5),           # vaak: blijft
        ("2026-12-19", "en", "een vraag van gisteren", 1),   # te nieuw om te beoordelen: blijft voorlopig
    ])
    for sql in m["opruimen"]:
        c.execute(sql, (grens,))
    c.commit()
    over = {(d, t, v): (n, vast) for d, t, v, n, vast in c.execute("SELECT dag, taal, vraag, n, vast FROM zoekvraag")}
    assert over == {("2026-12-01", "nl", "zelensky yacht"): (1, 1), ("2026-12-03", "nl", "zelensky yacht"): (2, 1),
                    ("2026-12-12", "en", "nato expansion"): (5, 1), ("2026-12-19", "en", "een vraag van gisteren"): (1, 0)}
    # een tweede keer opruimen verandert niets aan wat al bleef
    for sql in m["opruimen"]:
        c.execute(sql, (grens,))
    assert c.execute("SELECT count(*) FROM zoekvraag").fetchone()[0] == 4
    assert _node(f"import('./src/lib/zoekvragen.js').then((m) => console.log(JSON.stringify(m.opruimdag('{vandaag}'))))") == grens


def test_the_overview_shows_per_language_only_what_was_searched_at_least_three_times(tmp_path, monkeypatch):
    monkeypatch.setattr(tellen, "vandaag", lambda: "2026-12-20")
    c, _ = _db(tmp_path, [("2026-12-15", "nl", "zelensky yacht", 2), ("2026-12-18", "nl", "zelensky yacht", 2),
                          ("2026-12-19", "nl", "jan de vries", 1), ("2026-12-19", "en", "nato expansion", 3),
                          ("2026-11-01", "en", "oud nieuws", 9)])
    c.close()
    tekst = tellen.zoekvragen(tmp_path / "t.db", dagen=7)
    assert "zelensky yacht" in tekst and "nato expansion" in tekst
    assert "jan de vries" not in tekst and "oud nieuws" not in tekst
    assert tekst.index("en") < tekst.index("nato expansion") and "4" in tekst.split("zelensky yacht")[0].splitlines()[-1]


def test_the_overview_reads_the_searches_of_the_worker_from_d1_the_same_way(tmp_path, monkeypatch):
    monkeypatch.setattr(tellen, "vandaag", lambda: "2026-12-20")
    gezien = []

    def voer_uit(args):
        gezien.append(args)
        return json.dumps([{"success": True, "results": [{"taal": "nl", "vraag": "zelensky yacht", "n": 4}]}])

    tekst = tellen.zoekvragen_d1("factiz-tellingen", dagen=7, voer_uit=voer_uit)
    assert "zelensky yacht" in tekst
    assert gezien[0][:5] == ["d1", "execute", "factiz-tellingen", "--remote", "--json"]
    assert "HAVING SUM(n) >= 3" in gezien[0][-1]


def test_the_site_counts_a_search_in_both_ways_in_and_never_waits_for_it():
    platform = (SITE / "src" / "lib" / "platform.js").read_text(encoding="utf-8")
    deel = platform[platform.index("export function telZoekvraag("):]
    deel = deel[:deel.index("\n}\n")]
    assert "zoekvraagVoorTellen(" in deel and "catch" in deel and "await" not in deel
    assert "user-agent" in deel and "cookie" not in deel.lower() and "x-forwarded-for" not in deel.lower()
    for pad in (SITE / "src" / "pages" / "[taal]" / "api" / "zoek.js", SITE / "src" / "lib" / "start.js"):
        assert "telZoekvraag(" in pad.read_text(encoding="utf-8"), pad
    # de suggesties tijdens het typen tellen niet: dat zijn halve woorden
    assert "telZoekvraag" not in (SITE / "src" / "pages" / "[taal]" / "api" / "suggesties.js").read_text(encoding="utf-8")
    for naam in ("gegevens-worker.js", "gegevens-node.js"):
        tekst = (SITE / "src" / "lib" / naam).read_text(encoding="utf-8")
        assert "zetVraagteller(" in tekst and "OPRUIMEN" in tekst, naam


@pytest.mark.parametrize("taal", i18n.TALEN)
def test_the_site_no_longer_promises_that_a_search_is_never_kept(taal):
    for sleutel in ("zoek_privacy", "over_privacy_p1", "over_privacy_p1_meten", "over_privacy_tellen"):
        zin = i18n.tekst(taal, sleutel)
        assert zin and "!" not in zin and "—" not in zin, sleutel
    if taal in ("nl", "en"):
        woord = {"nl": "anoniem", "en": "anonymous"}[taal]
        for sleutel in ("zoek_privacy", "over_privacy_p1", "over_privacy_p1_meten", "over_privacy_tellen"):
            assert woord in i18n.tekst(taal, sleutel).lower(), (taal, sleutel)
