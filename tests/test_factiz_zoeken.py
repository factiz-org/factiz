"""Lijsten, filters en zoeken op het platform (PLAN #33.3, SPECS E9.S5 AC1 en E9.S6)."""

import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import zoekproef
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("zoeken")
    lab = _lab(map_)
    n = {}
    # dertig Engelse beweringen van Snopes, één per dag in januari 2024: genoeg om te bladeren
    for i in range(1, 31):
        c = _claim(lab, i, f"Ordinary claim number {i} about the weather")
        _check(lab, c, f"https://snopes.com/{i}", datum=f"2024-01-{i:02d}")
    n["villa"] = _claim(lab, 101, "Zelensky bought a villa in Florida", cluster="cl-v")
    n["palacete"] = _claim(lab, 102, "Zelenski adquirió un palacete en Florida", taal="es", cluster="cl-v")
    n["mansion"] = _claim(lab, 103, "Un político compró una mansión con dinero público", taal="es")
    n["arabisch"] = _claim(lab, 104, "زيلينسكي اشترى فيلا في فلوريدا", taal="ar")
    n["chinees"] = _claim(lab, 105, "泽连斯基在佛罗里达州购买了别墅", taal="zh")
    n["vaccin"] = _claim(lab, 106, "新冠疫苗含有芯片", taal="zh")
    n["waar"] = _claim(lab, 107, "The Eiffel Tower is in Paris")
    n["geen"] = _claim(lab, 108, "Something a newsroom looked at")
    # schriften waarin een woord uit letters én klinkertekens bestaat, en een schrift zonder spaties
    n["hindi"] = _claim(lab, 109, "यूक्रेन में गुप्त जैविक प्रयोगशालाएं हैं", taal="hi")
    n["tamil"] = _claim(lab, 110, "உக்ரைனில் ரகசிய உயிரியல் ஆய்வகங்கள் உள்ளன", taal="ta")
    n["thai"] = _claim(lab, 111, "เซเลนสกีซื้อวิลล่าในฟลอริดา", taal="th")
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2025-03-01")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2025-03-05", taal="fr")
    _check(lab, n["palacete"], "https://maldita.es/palacete", datum="2025-02-01", taal="es")
    _check(lab, n["mansion"], "https://maldita.es/mansion", datum="2023-06-01", taal="es", oordeel="misleidend")
    _check(lab, n["arabisch"], "https://afp.com/ar", datum="2025-01-01", taal="ar")
    _check(lab, n["chinees"], "https://afp.com/zh", datum="2022-05-05", taal="zh")
    _check(lab, n["vaccin"], "https://afp.com/vaccin", datum="2021-05-05", taal="zh")
    _check(lab, n["waar"], "https://snopes.com/toren", datum="2020-01-01", oordeel="waar", eigen="True")
    _check(lab, n["geen"], "https://snopes.com/onbekend", datum="", oordeel="onbekend", eigen="See article")
    _check(lab, n["hindi"], "https://afp.com/hi", datum="2019-01-01", taal="hi")
    _check(lab, n["tamil"], "https://afp.com/ta", datum="2018-01-01", taal="ta")
    _check(lab, n["thai"], "https://afp.com/th", datum="2017-01-01", taal="th")
    lab.commit()
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-10")
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    return client, {k: pb.nummer(v) for k, v in n.items()}, manifest["bestand"]


def _hrefs(client, adres):
    return [r["href"] for r in client.get(adres).json()["rijen"]]


def _zoek(client, vraag, taal="en", **extra):
    return client.post(f"/api/{taal}/zoek", data={"q": vraag, **extra})


def _treffers(r):
    return [rij["href"] for rij in r.json()["rijen"]]


# --- de lijst -----------------------------------------------------------------------------------------------------

def test_the_list_shows_twenty_five_per_page_the_newest_first_and_leafs_on(site):
    client, n, _ = site
    r = client.get("/api/en/archief")
    g = r.json()
    assert r.status_code == 200 and g["aantal"] == "40 fact-checks"        # 41 beweringen, twee ervan dezelfde
    eerste = [rij["href"] for rij in g["rijen"]]
    assert len(eerste) == 25 and eerste[0] == f"/fact-checks/{n['villa']}/"   # 5 maart 2025 is de nieuwste
    assert (g["blad"], g["bladen"]) == (1, 2)                                 # een volgend blad, geen vorig
    assert fa.lijst_url("en", {}, 2) == "/fact-checks/?p=2"
    tweede = client.get("/api/en/archief?p=2").json()
    assert len(tweede["rijen"]) == 15 and not {rij["href"] for rij in tweede["rijen"]} & set(eerste)
    assert (tweede["blad"], tweede["bladen"]) == (2, 2) and fa.lijst_url("en", {}, 1) == "/fact-checks/"
    # een bewering zonder datum staat achteraan, niet vooraan
    assert tweede["rijen"][-1]["href"] == f"/fact-checks/{n['geen']}/"
    for fout in ("?p=3", "?p=0", "?p=x", "?p=-1"):
        assert client.get("/api/en/archief" + fout).status_code == 404, fout


def test_each_filter_narrows_the_list_and_filters_combine(site):
    client, n, _ = site
    spaans = client.get("/api/en/archief?taal=es").json()
    assert [r["href"] for r in spaans["rijen"]] == [f"/fact-checks/{n['mansion']}/"] and spaans["aantal"] == "1 fact-check"
    assert len(_hrefs(client, "/api/en/archief?jaar=2025")) == 2
    assert _hrefs(client, "/api/en/archief?oordeel=waar") == [f"/fact-checks/{n['waar']}/"]
    assert _hrefs(client, "/api/en/archief?oordeel=geen") == [f"/fact-checks/{n['geen']}/"]
    maldita = _hrefs(client, "/api/en/archief?redactie=Maldita")
    assert set(maldita) == {f"/fact-checks/{n['villa']}/", f"/fact-checks/{n['mansion']}/"}
    assert _hrefs(client, "/api/en/archief?redactie=Maldita&jaar=2023") == [f"/fact-checks/{n['mansion']}/"]
    assert _hrefs(client, "/api/en/archief?taal=zh&jaar=2021") == [f"/fact-checks/{n['vaccin']}/"]
    leeg = client.get("/api/en/archief?taal=es&jaar=2020")
    assert leeg.status_code == 200 and leeg.json()["rijen"] == [] and leeg.json()["aantal"] == "0 fact-checks"


def test_a_filter_value_the_database_does_not_know_is_not_found(site):
    client, _, _ = site
    for fout in ("?taal=xx", "?jaar=1066", "?oordeel=nep", "?redactie=Niemand", "?taal=es&vreemd=1", "?jaar=20250",
                 "?taal=" + quote("<script>")):
        r = client.get("/api/en/archief" + fout)
        assert r.status_code == 404 and "<script>" not in r.text, fout


def test_filters_are_in_the_address_keep_the_other_choices_and_say_in_words_what_is_chosen(site):
    client, _, _ = site
    f = client.get("/api/nl/archief?taal=es").json()["filters"]
    assert f["gekozen"]["taal"] == ["es"]                                     # de gekozen taal staat aangevinkt
    assert [(s["kop"], s["naam"], s["url"]) for s in f["stukjes"]] == [("Taal", "Spaans", "/nl/fact-checks/")]   # in woorden
    # een jaar erbij kiezen houdt de taal: het formulier stuurt beide, en dat adres bestaat
    assert client.get("/api/nl/archief?jaar=2023&taal=es").status_code == 200
    # bladeren houdt het filter
    snopes = client.get("/api/en/archief?redactie=Snopes").json()
    assert snopes["bladen"] == 2 and snopes["paren"] == [["redactie", "Snopes"]]
    assert fa.lijst_url("en", {"redactie": "Snopes"}, 2) == "/fact-checks/?p=2&redactie=Snopes"
    tweede = client.get("/api/en/archief?p=2&redactie=Snopes").json()
    assert tweede["blad"] == 2 and tweede["rijen"] and tweede["paren"] == [["redactie", "Snopes"]]


@pytest.mark.parametrize("taal", TALEN)
def test_the_list_the_newsrooms_and_search_exist_in_every_language(site, taal):
    client, _, _ = site
    for r in (client.get(f"/api/{taal}/archief"), client.get(f"/api/{taal}/redacties"), _zoek(client, "villa", taal)):
        assert r.status_code == 200 and r.headers["content-type"] == "application/json", taal


def test_the_newsrooms_count_each_newsroom_and_lead_to_its_fact_checks(site):
    client, _, _ = site
    redacties = {r["naam"]: r for r in client.get("/api/de/redacties").json()["redacties"]}
    assert redacties["Snopes"]["href"] == "/de/fact-checks/?redactie=Snopes"
    assert {naam: r["aantal"] for naam, r in redacties.items()} == {"Snopes": "33", "Maldita": "2", "AFP": "7"}
    assert _hrefs(client, "/api/de/archief?redactie=Maldita")


# --- zoeken -------------------------------------------------------------------------------------------------------

def test_search_finds_a_claim_by_its_words_in_any_script_and_without_accents(site):
    client, n, _ = site
    assert _treffers(_zoek(client, "villa")) == [f"/fact-checks/{n['villa']}/"]
    assert _treffers(_zoek(client, "florida zelensky")) == [f"/fact-checks/{n['villa']}/"]     # alle woorden, elke volgorde
    assert _treffers(_zoek(client, "mansion")) == [f"/fact-checks/{n['mansion']}/"]            # zonder accent
    assert _treffers(_zoek(client, "palacete")) == [f"/fact-checks/{n['villa']}/"]             # een andere formulering
    assert _treffers(_zoek(client, "فيلا")) == [f"/fact-checks/{n['arabisch']}/"]
    assert _treffers(_zoek(client, "佛罗里达")) == [f"/fact-checks/{n['chinees']}/"]             # geen spaties
    assert _treffers(_zoek(client, "疫苗")) == [f"/fact-checks/{n['vaccin']}/"]                 # twee tekens
    assert _treffers(_zoek(client, "mansi")) == [f"/fact-checks/{n['mansion']}/"]              # een deel van een woord
    # een woord met klinkertekens blijft één woord (Devanagari, Tamil), en Thai heeft geen spaties
    assert _treffers(_zoek(client, "जैविक")) == [f"/fact-checks/{n['hindi']}/"]
    assert _treffers(_zoek(client, "गुप्त जैविक")) == [f"/fact-checks/{n['hindi']}/"]
    assert _treffers(_zoek(client, "உயிரியல்")) == [f"/fact-checks/{n['tamil']}/"]
    assert _treffers(_zoek(client, "วิลล่า")) == [f"/fact-checks/{n['thai']}/"]
    # de uitkomst linkt in de taal van de site
    assert _treffers(_zoek(client, "villa", taal="fr")) == [f"/fr/fact-checks/{n['villa']}/"]
    assert _zoek(client, "villa").json()["aantal"] == "1 result" and _zoek(client, "villa", taal="nl").json()["aantal"] == "1 resultaat"


def test_search_leafs_through_many_hits_without_the_question_ever_entering_an_address(site):
    client, _, _ = site
    r = _zoek(client, "weather")
    assert r.status_code == 200 and len(_treffers(r)) == 25
    assert r.json()["aantal"] == "30 results" and r.json()["totaal"] == 30 and r.json()["blad"] == 1
    assert r.headers["cache-control"] == "no-store"
    # verder bladeren stuurt de vraag opnieuw in het bericht; geen adres in de gegevens draagt haar
    assert "weather" not in " ".join(re.findall(r'"(?:href|url)":"([^"]*)"', r.text))
    tweede = _zoek(client, "weather", p="2")
    assert len(_treffers(tweede)) == 5 and tweede.json()["blad"] == 2 and not set(_treffers(tweede)) & set(_treffers(r))
    # de vraag in het adres doet niets
    assert client.get("/api/en/zoek?q=villa").status_code == 405


def test_nothing_found_is_said_apart_from_an_empty_question(site):
    client, _, _ = site
    r = _zoek(client, "kwetsbaarheid")
    assert r.status_code == 200 and r.json()["rijen"] == [] and r.json()["totaal"] == 0 and r.json()["gezocht"] is True
    leeg = _zoek(client, "   ")
    assert leeg.status_code == 200 and leeg.json()["gezocht"] is False and leeg.json()["rijen"] == []


@pytest.mark.parametrize("vraag", ['" OR 1=1 --', "*", "NEAR(a b)", "a AND", "villa*", "^villa", "col:villa", "(", '""',
                                   "<script>alert(1)</script>", "villa' ; DROP TABLE pagina; --", "\u202evilla",
                                   "%_%", "a" * 5000])
def test_a_hostile_or_broken_question_is_just_a_question(site, vraag):
    client, _, _ = site
    r = _zoek(client, vraag)
    assert r.status_code == 200, vraag
    assert "<script>alert(1)" not in r.text and "sqlite" not in r.text.lower() and "Traceback" not in r.text
    assert "\u202e" not in r.text
    assert client.get("/api/en/archief").status_code == 200          # de database staat er nog


def test_a_question_that_is_too_large_is_refused_and_other_methods_do_nothing(site):
    client, _, _ = site
    assert client.post("/api/en/zoek", content=b"q=" + b"a" * 20000,
                       headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 413
    assert client.put("/api/en/zoek").status_code == 405 and client.delete("/api/en/zoek").status_code == 405
    assert client.post("/api/en/archief").status_code == 405


def test_the_first_page_is_a_way_in_verdicts_languages_and_years(site):
    client, _, _ = site
    g = client.get("/api/nl/archief").json()
    # het filterformulier van de lijst zelf, met vinkjes die nog niet aan staan (E9.S12)
    groepen = {gr["soort"]: {k["waarde"]: k["aan"] for k in gr["boven"]} for gr in g["filters"]["groepen"]}
    for naam, waarde in (("oordeel", "onwaar"), ("taal", "es"), ("jaar", "2025")):
        assert groepen[naam].get(waarde) is False, (naam, waarde)
    assert client.get("/api/nl/redacties").status_code == 200


def test_the_local_server_keeps_no_log_of_requests():
    start = json.loads((Path(__file__).resolve().parent.parent / ".claude" / "launch.json").read_text())
    # één preview sinds 2026-11-23 (PO): de site in Node, die de uitgave zelf leest en geen log bijhoudt; draait er ooit
    # weer een Python-platform, dan zonder log van verzoeken (PLAN #33.6)
    assert [c["name"] for c in start["configurations"]] == ["factiz"]
    for c in start["configurations"]:
        if "factiz_site" in " ".join(c["runtimeArgs"]):
            assert "--no-access-log" in " ".join(c["runtimeArgs"]), c["name"]


# --- de zoekproef -------------------------------------------------------------------------------------------------

def test_the_trial_question_is_a_piece_of_the_claim_itself():
    assert zoekproef.vraag_uit("one two three four five six seven", "en") == "four five six"
    assert zoekproef.vraag_uit("泽连斯基在佛罗里达州购买了别墅", "zh") == "罗里达州"
    assert zoekproef.vraag_uit("kort", "en") == "kort"
    assert zoekproef.groep("fa") == "arabisch" and zoekproef.groep("hi") == "indiaas" and zoekproef.groep("th") == "zonder spaties"
    assert zoekproef.groep("es") == "latijns" and zoekproef.groep("ru") == "overig"


def test_the_trial_counts_per_group_and_fails_below_its_requirement(site):
    _, _, bestand = site
    uitslag = zoekproef.meet(bestand, per_groep=2, zaad=1)
    assert set(uitslag["per_groep"]) <= {"latijns", "arabisch", "indiaas", "zonder spaties", "overig"}
    assert uitslag["goed"] <= uitslag["vragen"] and uitslag["per_groep"]["latijns"]["vragen"] == 2
    assert zoekproef.gehaald({"vragen": 50, "goed": 45, "per_groep": {"a": {"vragen": 10, "goed": 8}}}) is True
    assert zoekproef.gehaald({"vragen": 50, "goed": 44, "per_groep": {"a": {"vragen": 10, "goed": 10}}}) is False
    assert zoekproef.gehaald({"vragen": 50, "goed": 46, "per_groep": {"a": {"vragen": 10, "goed": 7}}}) is False
