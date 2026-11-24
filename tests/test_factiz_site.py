"""Het geraamte van het platform (PLAN #33.2, SPECS E9.S2–S4): een site die alleen leest, in vijf talen."""

import ast
import json
import re
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db as fdb
from factiz_site import i18n
from tests.test_publiceren import CCBY, EU, REGISTER, _check, _claim, _lab

PAKKET = Path(fa.__file__).resolve().parent
TALEN = ("en", "nl", "de", "es", "fr")
VIJANDIG = '<script>alert(1)</script> "><img src=x onerror=alert(1)> ‮omgekeerd‬ ' + "می‌خواهم"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; "
       "frame-ancestors 'none'")


def _pad(taal, pad):
    return pad if taal == "en" else f"/{taal}{pad}"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("platform")
    lab = _lab(map_)
    gewoon = _claim(lab, 1, "Zelensky bought a villa in Florida", cluster="cl-1")
    spaans = _claim(lab, 2, "Zelenski compró una villa en Florida", taal="es", cluster="cl-1")
    arabisch = _claim(lab, 3, "زيلينسكي اشترى فيلا في فلوريدا", taal="ar")
    vijandig = _claim(lab, 4, VIJANDIG)
    lang = _claim(lab, 5, "woord " * 1400)
    zonder_label = _claim(lab, 6, "Something a newsroom looked at")
    _check(lab, gewoon, "https://snopes.com/villa", datum="2024-03-01", eigen="False")
    _check(lab, gewoon, "https://factcheck.afp.com/villa", datum="2024-03-05", eigen="Faux", taal="fr")
    _check(lab, spaans, "https://maldita.es/villa", datum="2023-12-31", eigen="Bulo", taal="es")
    _check(lab, arabisch, "https://euvsdisinfo.eu/report/villa", bron=EU, eigen="Disinformation", taal="ar")
    _check(lab, vijandig, "https://snopes.com/x", eigen='<b>False</b> "><script>x</script>')
    _check(lab, lang, "https://snopes.com/lang")
    _check(lab, zonder_label, "https://snopes.com/onbekend", oordeel="onbekend", eigen="See article", datum="")
    lab.execute("INSERT INTO linkstatus (url, uitkomst, gecontroleerd_op, laatst_levend, dood_sinds, laatst_dood, "
                "archief_url, archief_datum) VALUES (?,?,?,?,?,?,?,?)",
                ("https://snopes.com/villa", "dood", "2026-11-02T10:00:00", "2026-01-01T10:00:00", "2026-11-01T09:00:00",
                 "2026-11-02T10:00:00", "https://web.archive.org/web/2025/https://snopes.com/villa", "2025-05-05"))
    lab.execute("INSERT INTO actor (actor_id, naam, soort) VALUES ('outlet:1', 'tsargrad.tv', 'outlet')")
    lab.execute("INSERT INTO attributie (claim_id, actor_id, bron_id, datum, url, niveau, grond) VALUES (?,?,?,?,?,?,?)",
                (arabisch, "outlet:1", "euvsdisinfo", "2022-11-22", "https://euvsdisinfo.eu/report/villa", "waargenomen", "g"))
    lab.commit()
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-10")
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    nummers = {"gewoon": pb.nummer(gewoon), "spaans": pb.nummer(spaans), "arabisch": pb.nummer(arabisch),
               "vijandig": pb.nummer(vijandig), "lang": pb.nummer(lang), "zonder_label": pb.nummer(zonder_label)}
    return client, nummers, manifest["bestand"]


def _ingangen(nummers):
    """De ingangen die de site leest: de start, de bronnen en elke factcheck (niet het nummer van een andere formulering)."""
    return ["archief", "bronnen"] + [f"factcheck/{n}" for k, n in nummers.items() if k != "spaans"]


@pytest.mark.parametrize("taal", TALEN)
def test_every_kind_of_page_answers_in_every_language_with_that_language_in_the_data(site, taal):
    client, nummers, _ = site
    for ingang in _ingangen(nummers):
        r = client.get(f"/api/{taal}/{ingang}")
        assert r.status_code == 200, (taal, ingang, r.status_code)
        assert r.headers["content-type"] == "application/json", (taal, ingang)
    assert client.get(f"/api/{taal}/archief").json()["taal"] == taal
    # de vaste woorden staan in de taal van de site, en elke link blijft binnen die taal
    g = client.get(f"/api/{taal}/factcheck/{nummers['gewoon']}").json()
    assert g["label"] == i18n.label(taal, "onwaar") and g["href"] == _pad(taal, f"/fact-checks/{nummers['gewoon']}/")


def test_every_answer_carries_the_policy_and_never_a_cookie(site):
    client, nummers, _ = site
    for pad in ["/api/en/archief", "/api/nl/archief", f"/api/en/factcheck/{nummers['gewoon']}", "/api/en/bronnen",
                "/robots.txt", "/api/en/bestaat-niet", "/api/en/factcheck/0000000000000000", "/fact-checks/",
                f"/api/en/factcheck/{nummers['spaans']}"]:
        r = client.get(pad)
        h = r.headers
        assert h["content-security-policy"] == CSP, pad
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin", pad
        assert h["x-frame-options"] == "DENY" and "max-age=" in h["strict-transport-security"], pad
        assert "camera=()" in h["permissions-policy"], pad
        assert "set-cookie" not in h, pad


def test_hostile_text_from_the_database_stays_plain_text(site):
    """De gegevens geven de tekst zoals ze is, als tekst: het ontsnappen doet de voorkant. Een teken dat de leesrichting
    van de rest van de pagina omdraait, gaat er al in de gegevens uit; het verbindingsteken van het Perzisch blijft."""
    client, nummers, _ = site
    g = client.get(f"/api/en/factcheck/{nummers['vijandig']}").json()
    assert g["bewering"].startswith("<script>alert(1)</script> \"><img src=x onerror=alert(1)>")
    assert g["checks"][0]["oordeel"] == '<b>False</b> "><script>x</script>'
    tekst = json.dumps(g, ensure_ascii=False)
    assert "\u202e" not in tekst and "\u202c" not in tekst and "omgekeerd" in g["bewering"]
    assert "می‌خواهم" in g["bewering"]
    # een heel lange bewering breekt de gegevens niet
    assert client.get(f"/api/en/factcheck/{nummers['lang']}").status_code == 200


def test_a_claim_keeps_its_own_language_and_direction_inside_a_page_in_another_language(site):
    client, nummers, _ = site
    arabisch = client.get(f"/api/nl/factcheck/{nummers['arabisch']}").json()
    assert arabisch["taal"] == "ar" and arabisch["richting"] == "rtl"
    gewoon = client.get(f"/api/en/factcheck/{nummers['gewoon']}").json()
    assert gewoon["taal"] == "en" and gewoon["richting"] == "ltr"
    # een lange bewering staat er volledig: de voorkant kort haar in de kop in en zet de hele eronder
    lang = client.get(f"/api/en/factcheck/{nummers['lang']}").json()
    assert lang["bewering"].split() == ["woord"] * 1400 and lang["taal"] == "en" and lang["richting"] == "ltr"
    # de andere formulering, in haar eigen taal
    assert {"tekst": "Zelenski compró una villa en Florida", "taal": "es", "richting": "ltr"} in gewoon["formuleringen"]


def test_the_label_the_count_and_the_sources_follow_the_language_of_the_site(site):
    client, nummers, _ = site
    en = client.get(f"/api/en/factcheck/{nummers['gewoon']}").json()
    assert en["label"] == "Known to be false" and en["telregel"] == "3 newsrooms, 3 languages, 2023–2024"
    nl = client.get(f"/api/nl/factcheck/{nummers['gewoon']}").json()
    assert nl["label"] == "Bekend als onwaar" and nl["telregel"] == "3 redacties, 3 talen, 2023–2024"
    # de check in de taal van de site eerst, dan in de taal van de bewering (Engels), dan de nieuwste (#34.2bp, E9.S31
    # AC5), met het oordeel in de eigen woorden van de redactie, onvertaald
    assert [k["oordeel"] for k in en["checks"]] == ["False", "Faux", "Bulo"] == [k["oordeel"] for k in nl["checks"]]
    assert en["checks"][0]["datum"] == "1 March 2024" and nl["checks"][0]["datum"] == "1 maart 2024"
    for taal, oordelen, datum in (("de", ["False", "Faux", "Bulo"], "1. März 2024"),
                                  ("es", ["Bulo", "False", "Faux"], "31 de diciembre de 2023"),
                                  ("fr", ["Faux", "False", "Bulo"], "5 mars 2024")):
        checks = client.get(f"/api/{taal}/factcheck/{nummers['gewoon']}").json()["checks"]
        assert [k["oordeel"] for k in checks] == oordelen and checks[0]["datum"] == datum, taal
    # geen eigen oordeel en geen percentage
    getoond = {k: en[k] for k in ("label", "telregel", "eerder", "checks", "herkomst", "kop")}
    assert "%" not in json.dumps(getoond, ensure_ascii=False)
    # zonder label: de eigen woorden van de redactie, en een datum die ontbreekt wordt niet verzonnen
    zonder = client.get(f"/api/en/factcheck/{nummers['zonder_label']}").json()
    assert zonder["label"] == "Fact-checked"
    assert zonder["checks"][0]["oordeel"] == "See article" and zonder["checks"][0]["datum"] == "No date"


def test_a_dead_link_shows_its_archive_copy(site):
    client, nummers, _ = site
    snopes = next(k for k in client.get(f"/api/en/factcheck/{nummers['gewoon']}").json()["checks"] if k["redactie"] == "Snopes")
    assert snopes["offline"] is True and snopes["url"] == ""
    assert snopes["archief"] == "https://web.archive.org/web/2025/https://snopes.com/villa"
    assert "Archived copy" in snopes["archief_tekst"]


def test_where_it_turned_up_names_the_outlet_as_text_and_never_as_a_link(site):
    client, nummers, _ = site
    g = client.get(f"/api/en/factcheck/{nummers['arabisch']}").json()
    o = g["opgedoken"][0]
    assert o["naam"] == "tsargrad.tv" and "EUvsDisinfo" in o["volgens"] and o["datum"] == "22 November 2022"
    # de enige link is die naar de bron die het zag, nooit naar de plek zelf: ook niet in de gegevens voor zoekmachines
    assert o["url"] == "https://euvsdisinfo.eu/report/villa"
    links = _waarden({**g, "kop": {**g["kop"], "ld": json.loads(g["kop"]["ld"])}}, ("url", "href", "item", "@id", "archief"))
    assert links and not any("tsargrad" in w for w in links)


def _waarden(ding, sleutels):
    """Elke tekst onder een van deze sleutels, hoe diep ook."""
    if isinstance(ding, dict):
        return [w for k, v in ding.items() for w in ([v] if k in sleutels and isinstance(v, str) else _waarden(v, sleutels))]
    if isinstance(ding, list):
        return [w for v in ding for w in _waarden(v, sleutels)]
    return []


def test_an_unknown_or_malformed_number_is_a_plain_not_found(site):
    client, nummers, _ = site
    for pad in ["/api/en/factcheck/0000000000000000", "/api/en/factcheck/ABCDEF0123456789", "/api/en/factcheck/kort",
                "/api/en/factcheck/..%2F..%2Fetc%2Fpasswd", "/api/nl/bestaat-niet", "/api/xx/factcheck/0000000000000000"]:
        r = client.get(pad)
        assert r.status_code == 404, pad
        assert "Traceback" not in r.text and "sqlite" not in r.text.lower()


def test_the_number_of_another_wording_leads_to_the_page_of_the_claim_in_the_same_language(site):
    client, nummers, _ = site
    r = client.get(f"/api/de/factcheck/{nummers['spaans']}")
    assert r.status_code == 301 and r.headers["location"] == f"/api/de/factcheck/{nummers['gewoon']}"
    assert client.get(r.headers["location"]).json()["href"] == f"/de/fact-checks/{nummers['gewoon']}/"


def test_no_page_is_offered_to_search_engines_yet_and_nothing_follows_the_browser_language(site):
    client, _, _ = site
    assert "Disallow: /" in client.get("/robots.txt").text
    r = client.get("/api/en/archief", headers={"accept-language": "nl-NL,nl;q=0.9"})
    assert r.status_code == 200 and r.json()["taal"] == "en" and r.json()["aantal"] == "5 fact-checks"


def test_only_reading_is_possible(site):
    client, nummers, bestand = site
    for pad in (f"/api/en/factcheck/{nummers['gewoon']}", "/api/en/archief", "/api/en/bronnen"):
        for methode in ("post", "put", "delete", "patch"):
            assert getattr(client, methode)(pad).status_code == 405, (methode, pad)
    with pytest.raises(sqlite3.OperationalError):
        fdb.Publicatie(bestand)._conn().execute("DELETE FROM pagina")


def test_the_site_refuses_a_file_with_another_schema(site, tmp_path):
    _, _, bestand = site
    kopie = tmp_path / "ander.db"
    kopie.write_bytes(Path(bestand).read_bytes())
    conn = sqlite3.connect(kopie)
    conn.execute("UPDATE meta SET waarde = '99' WHERE sleutel = 'schema'")
    conn.commit()
    conn.close()
    with pytest.raises(fdb.Ongeldig, match="schema"):
        fdb.Publicatie(kopie)


def test_the_sources_page_names_every_source_with_its_licence_and_credit(site):
    client, _, _ = site
    bronnen = client.get("/api/en/bronnen").json()["bronnen"]
    assert any("CC BY 4.0" in b["licentie"] for b in bronnen)
    assert any("EUvsDisinfo, European External Action Service" in b["naamsvermelding"] for b in bronnen)
    assert any("Data Commons" in b["naam"] for b in bronnen)


def test_every_fixed_text_exists_in_all_five_languages_with_the_same_blanks_to_fill(site):
    basis = i18n.teksten("en")
    assert len(basis) >= 40
    for taal in TALEN:
        ruw = json.loads((PAKKET / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))
        assert isinstance(ruw["_meta"]["nagelezen"], bool) and ruw["_meta"]["herkomst"]
        t = i18n.teksten(taal)
        assert set(t) == set(basis), (taal, set(t) ^ set(basis))
        for sleutel, waarde in t.items():
            plat = waarde if isinstance(waarde, str) else " ".join(waarde)
            basis_plat = basis[sleutel] if isinstance(basis[sleutel], str) else " ".join(basis[sleutel])
            assert plat.strip(), (taal, sleutel)
            assert set(re.findall(r"\{(\w+)\}", plat)) == set(re.findall(r"\{(\w+)\}", basis_plat)), (taal, sleutel)
    with pytest.raises(KeyError):
        i18n.tekst("en", "bestaat_niet")


def test_the_platform_borrows_no_code_from_the_lab():
    """Het platform leent niets uit `doublecheck`: de database is het contract (B71). Sinds #34.2f stap 4 heeft het geen
    sjablonen en geen opmaak meer; de site in `site/` maakt de pagina's."""
    for pad in PAKKET.rglob("*.py"):
        for knoop in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
            namen = ([a.name for a in knoop.names] if isinstance(knoop, ast.Import)
                     else [knoop.module or ""] if isinstance(knoop, ast.ImportFrom) else [])
            assert not any(n == "doublecheck" or n.startswith("doublecheck.") for n in namen), pad
    assert not (PAKKET / "templates").exists() and not (PAKKET / "static" / "platform.css").exists()


def test_the_first_page_counts_from_the_database_and_lists_the_newest_fact_checks(site):
    client, nummers, _ = site
    g = client.get("/api/en/archief").json()
    # vijf pagina's in de proefdatabase (zes beweringen, waarvan twee dezelfde in een andere taal), in twee talen
    assert i18n.tekst("en", "start_titel", paginas=g["tellingen"]["paginas"], talen=g["tellingen"]["talen"]) == \
        "5 claims that newsrooms have checked, in 2 languages"
    hrefs = [r["href"] for r in g["rijen"]]
    assert hrefs.index(f"/fact-checks/{nummers['gewoon']}/") < hrefs.index(f"/fact-checks/{nummers['lang']}/")
    assert f"/nl/fact-checks/{nummers['gewoon']}/" in [r["href"] for r in client.get("/api/nl/archief").json()["rijen"]]


def test_the_brand_files_live_in_one_place_and_the_site_serves_them():
    """Het logo, het icoon en het beeld bij delen staan op één plek (`factiz_site/static/merk/`); de site serveert die
    map zelf (`site/public/static`), ook `/favicon.ico`, dat een browser uit zichzelf opvraagt. Het platform serveert
    sinds #34.2f stap 4 geen bestanden meer."""
    merk = PAKKET / "static" / "merk"
    for naam, begin in [("favicon.ico", b"\x00\x00\x01\x00"), ("logo.svg", b"<svg"), ("apple-touch-icon.png", b"\x89PNG"),
                        ("og.jpg", b"\xff\xd8"), ("woordmerk-inline.svg", b"<svg")]:
        inhoud = (merk / naam).read_bytes()
        assert inhoud.lstrip().startswith(begin) and len(inhoud) > 300, naam
    publiek = PAKKET.parent / "site" / "public"
    assert (publiek / "static").resolve() == (PAKKET / "static").resolve()
    assert (publiek / "favicon.ico").resolve() == (merk / "favicon.ico").resolve()


# --- het omveld van een bewering (PLAN #34.2h, DESIGNSYSTEEM §4) ------------------------------------------------------

def test_the_context_of_a_claim_shows_when_it_was_checked_year_by_year(site):
    client, nummers, _ = site
    o = client.get(f"/api/en/factcheck/{nummers['gewoon']}").json()["omveld"]
    # drie checks in één groep: 31 december 2023, en twee in maart 2024; de jaren ertussen tellen mee als ze leeg zijn
    assert o["jaren"] == [{"jaar": 2023, "aantal": 1}, {"jaar": 2024, "aantal": 2}]
    assert o["eerst"] == "31 December 2023" and o["laatst"] == "5 March 2024"
    # ook bekend als: de andere formulering uit dezelfde groep, met haar taal
    assert o["ook_als"]["aantal"] >= 1
    assert {"tekst": "Zelenski compró una villa en Florida", "taal": "es", "richting": "ltr"} in o["ook_als"]["voorbeelden"]


def test_first_seen_names_the_earliest_place_with_the_source_that_saw_it(site):
    client, nummers, _ = site
    gezien = client.get(f"/api/en/factcheck/{nummers['arabisch']}").json()["omveld"]["eerst_gezien"]
    assert gezien["naam"] == "tsargrad.tv" and gezien["datum"] == "22 November 2022"
    assert "EUvsDisinfo" in gezien["volgens"]      # nooit een eerste keer zonder wie het zag


def test_a_claim_with_nothing_beyond_its_count_gets_no_context_block(site):
    client, nummers, _ = site
    assert client.get(f"/api/en/factcheck/{nummers['lang']}").json()["omveld"] is None
