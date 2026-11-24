"""Zoeken dat meedenkt (PLAN #34.2ac, SPECS E9.S14): een land, redactie, thema of onderdeel in de vraag verruimt en
versmalt nooit; alleen de volledige naam van een persoon of een dossier gaat meteen naar die pagina; een geplakte link
van een factcheck gaat naar die factcheck; een vraag naar de site zelf wijst naar die pagina; en het woord dat je typt,
wordt afgemaakt als de vraag dan iets vindt. De vraag wordt nergens bewaard."""

import pytest
from starlette.testclient import TestClient

from doublecheck import dossiers as ds
from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db
from tests.test_publiceren import REGISTER, _check, _claim, _lab
from tests.test_publiceren_dossiers import AKKOORD


def _vijf(nl, en, de, es, fr):
    return {"nl": nl, "en": en, "de": de, "es": es, "fr": fr}


LANDEN = {"IN": _vijf("India", "India", "Indien", "India", "Inde"),
          "RU": _vijf("Rusland", "Russia", "Russland", "Rusia", "Russie"),
          "LK": _vijf("Sri Lanka", "Sri Lanka", "Sri Lanka", "Sri Lanka", "Sri Lanka"),
          "US": _vijf("Verenigde Staten", "United States", "Vereinigte Staaten", "Estados Unidos", "États-Unis")}
THEMAS = [{"sleutel": "health", "naam": _vijf("Gezondheid", "Health", "Gesundheit", "Salud", "Santé"), "omschrijving": "x",
           "onderdelen": [{"sleutel": "vaccines", "naam": _vijf("Vaccins", "Vaccines", "Impfstoffe", "Vacunas", "Vaccins"),
                           "omschrijving": "x"}]},
          {"sleutel": "war", "naam": _vijf("Oorlog en conflict", "War and conflict", "Krieg und Konflikte",
                                           "Guerra y conflictos", "Guerre et conflits"), "omschrijving": "x", "onderdelen": []}]
ZELENSKY = _vijf("Volodymyr Zelensky", "Volodymyr Zelenskyy", "Wolodymyr Selenskyj", "Volodímir Zelenski",
                 "Volodymyr Zelensky")
KYIV = _vijf("Kiev", "Kyiv", "Kiew", "Kiev", "Kiev")

# sleutel: (tekst, taal, redactie, indeling)
BEWERINGEN = {
    "vac1": ("The vaccine causes autism in children", "en", "snopes.com", ("health", "vaccines", "US")),
    "vac2": ("A vaccine was tested on orphans", "en", "snopes.com", ("health", "vaccines", "")),
    "vac3": ("Vaccines contain microchips", "en", "snopes.com", ("health", "vaccines", "")),
    "jab": ("The jab makes you magnetic", "en", "snopes.com", ("health", "vaccines", "")),
    "india_vac": ("A vaccine trial killed children in Bihar", "en", "snopes.com", ("health", "vaccines", "IN")),
    "india_woord": ("India bans beef exports", "en", "snopes.com", ("economy", "", "IN")),
    "india_ander": ("Russia threatens India with sanctions", "en", "snopes.com", ("war", "", "RU")),
    "india_ander_vac": ("Vaccine shipments to India were stopped", "en", "snopes.com", ("health", "", "US")),
    "modi": ("Modi will ban cash next week", "en", "snopes.com", ("economy", "", "IN")),
    "sri": ("Sri Lanka bans fertiliser", "en", "snopes.com", ("economy", "", "LK")),
    "colombo": ("Colombo runs out of fuel", "en", "snopes.com", ("economy", "", "LK")),
    "maldita_vac": ("La vacuna mata a los niños", "es", "maldita.es", ("health", "", "")),
    "snopes_vac": ("La vacuna cura el cáncer", "es", "snopes.com", ("health", "", "")),
    "maldita_woord": ("Maldita was paid to censor the news", "en", "snopes.com", ("", "", "")),
    "gezond": ("Gezondheid gaat boven alles, zegt de minister", "nl", "snopes.com", ("", "", "")),
    "tanks": ("Tanks were seen in the capital", "en", "snopes.com", ("war", "", "RU")),
    "zelensky1": ("Zelensky bought a villa in Florida", "en", "snopes.com", ("war", "", "")),
    "zelensky2": ("Zelensky fled to London", "en", "afp.com", ("war", "", "")),
    "kiew": ("Kyiv was bombed yesterday", "en", "snopes.com", ("war", "", "")),
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("meedenken")
    lab = _lab(map_)
    claims = {k: _claim(lab, i, tekst, taal=taal) for i, (k, (tekst, taal, _, _)) in enumerate(BEWERINGEN.items(), start=1)}
    for i, (k, c) in enumerate(claims.items(), start=1):
        _, taal, redactie, _ = BEWERINGEN[k]
        _check(lab, c, f"https://{redactie}/{k}/", datum=f"2024-{1 + i % 12:02d}-{1 + i % 27:02d}", taal=taal)
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in claims.items()}
    indeling = {nr[k]: {"thema": th, "onderdeel": deel, "tweede": "", "land": land}
                for k, (_, _, _, (th, deel, land)) in BEWERINGEN.items() if th in ("health", "war")}
    for k, (_, _, _, (th, _, land)) in BEWERINGEN.items():
        if th not in ("health", "war") and land:
            indeling[nr[k]] = {"thema": "war", "onderdeel": "", "tweede": "", "land": land}
    namen = {"namen": {
        "Q3874799": {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["zelensky1"], nr["zelensky2"]]},
        "Q1899": {"soort": "plaats", "namen": KYIV, "wikis": 200, "paginas": [nr["kiew"], nr["tanks"]]}},
        "per_pagina": {nr["zelensky1"]: ["Q3874799"], nr["zelensky2"]: ["Q3874799"], nr["kiew"]: ["Q1899"],
                       nr["tanks"]: ["Q1899"]}}
    ruw = {"soort": "verhaal", "status": "akkoord", "akkoord": AKKOORD, "thema": "war", "onderdeel": "", "verwant": [],
           "naam": _vijf("De villa van Zelensky", "Zelensky's villa", "Selenskyjs Villa", "La villa de Zelenski",
                         "La villa de Zelensky"),
           "inleiding": _vijf("x", "x", "x", "x", "x"), "nagelezen": {t: False for t in ds.SITETALEN}, "item": []}
    dossier = ds.keur("zelensky-villa", ruw, {"goedgekeurd_door": "PO", "datum": "2026-11-12",
                                               "factchecks": [{"nummer": nr["zelensky1"]}]})
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-13", namen=namen,
                           indeling=indeling, themas=THEMAS, landen=LANDEN, dossiers=[dossier])
    pub = db.Publicatie(manifest["bestand"])
    assert pub.afkortingen_klaar(30)
    return TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False), pub, nr


def _vind(pub, vraag, **extra):
    return set(pub.treffers(vraag, **extra))


def _zoek(client, vraag, taal="nl", **extra):
    return client.post(f"/api/{taal}/zoek", data={"q": vraag, **extra}).json()


# --- een land, redactie, thema of onderdeel verruimt (AC3) ------------------------------------------------------------

def test_a_country_in_the_question_also_finds_the_fact_checks_about_it_without_the_word(site):
    _, pub, nr = site
    gevonden = _vind(pub, "vaccine india")
    assert nr["india_vac"] in gevonden                     # over India, zonder het woord
    assert nr["india_ander_vac"] in gevonden               # het woord, over een ander land
    assert nr["vac1"] not in gevonden                      # wel vaccine, niet India
    # het land alleen: alles met het woord blijft, ook over een ander land, en de factchecks over India komen erbij
    assert {nr["india_woord"], nr["india_ander"], nr["india_ander_vac"], nr["india_vac"], nr["modi"]} <= _vind(pub, "India")


def test_a_country_never_narrows_what_the_word_found(site):
    _, pub, _ = site
    for vraag in ("india", "Russia", "vaccine india", "sri lanka"):
        assert _vind(pub, vraag, letterlijk=True) <= _vind(pub, vraag), vraag


def test_a_country_of_two_words_is_read_as_one_name(site):
    _, pub, nr = site
    assert {nr["sri"], nr["colombo"]} <= _vind(pub, "Sri Lanka")
    assert _vind(pub, "Sri Lanka", letterlijk=True) == {nr["sri"]}


def test_between_quotes_or_literally_the_words_only(site):
    client, pub, nr = site
    assert nr["india_vac"] not in _vind(pub, '"india"') and nr["modi"] not in _vind(pub, '"india"')
    assert _vind(pub, "india", letterlijk=True) == {nr["india_woord"], nr["india_ander"], nr["india_ander_vac"]}
    assert _zoek(client, "india", letterlijk="1")["gelezen"] == []
    assert _zoek(client, '"india"')["gelezen"] == []


def test_the_page_says_what_it_read_in_the_language_of_the_site(site):
    client, _, _ = site
    nl = _zoek(client, "tanks rusland")["gelezen"]
    assert [(g["soort"], g["waarde"], g["woord"], g["naam"]) for g in nl] == [("land", "RU", "rusland", "Rusland")]
    assert "rusland" in nl[0]["tekst"] and "Rusland" in nl[0]["tekst"]
    de = _zoek(client, "Russia", taal="de")["gelezen"]
    assert de[0]["naam"] == "Russland" and de[0]["woord"] == "Russia"


def test_a_newsroom_in_the_question_also_finds_its_fact_checks(site):
    client, pub, nr = site
    assert nr["maldita_vac"] in _vind(pub, "maldita vacuna") and nr["snopes_vac"] not in _vind(pub, "maldita vacuna")
    # haar naam als woord blijft gevonden
    assert {nr["maldita_woord"], nr["maldita_vac"]} <= _vind(pub, "Maldita")
    assert [g["soort"] for g in _zoek(client, "maldita vacuna", taal="es")["gelezen"]] == ["redactie"]


def test_a_theme_or_part_widens_and_its_page_stands_on_top(site):
    client, pub, nr = site
    gevonden = _vind(pub, "gezondheid")
    assert nr["gezond"] in gevonden and {nr["vac1"], nr["jab"], nr["maldita_vac"]} <= gevonden
    uit = _zoek(client, "gezondheid")
    assert uit["doorsturen"] is None
    assert uit["ingangen"][0]["soort"] == "thema" and uit["ingangen"][0]["thema"] == "health"
    # een onderdeel: het woord in elke vorm, of de factchecks in dat onderdeel
    assert {nr["vac1"], nr["vac3"], nr["jab"], nr["india_ander_vac"]} <= _vind(pub, "Vaccines")
    assert _zoek(client, "vaccines", taal="en")["gelezen"][0]["soort"] == "onderdeel"
    # een thema van meer woorden
    assert nr["tanks"] in _vind(pub, "Oorlog en conflict")


# --- doorsturen bij de volledige naam van een persoon of een dossier (AC4) ---------------------------------------------

def test_the_full_name_of_a_person_goes_straight_to_the_name_page(site):
    client, _, _ = site
    uit = _zoek(client, "Volodymyr Zelensky")
    assert uit["doorsturen"] == {"href": "/nl/names/Q3874799/", "soort": "naam", "naam": "Volodymyr Zelensky"}
    assert _zoek(client, "wolodymyr selenskyj", taal="de")["doorsturen"]["href"] == "/de/names/Q3874799/"


@pytest.mark.parametrize("vraag,extra", [("zelensky", {}), ('"Volodymyr Zelensky"', {}),
                                         ("Volodymyr Zelensky", {"letterlijk": "1"}),
                                         ("Volodymyr Zelensky", {"jaar": "2024"}), ("Kyiv", {}), ("gezondheid", {}),
                                         ("Volodymyr Zelensky villa", {})])
def test_a_part_of_a_name_a_place_a_theme_quotes_or_filters_never_redirect(site, vraag, extra):
    client, _, _ = site
    assert _zoek(client, vraag, **extra)["doorsturen"] is None


def test_the_title_of_a_dossier_goes_straight_to_the_dossier(site):
    client, _, _ = site
    assert _zoek(client, "De villa van Zelensky")["doorsturen"]["href"] == "/nl/dossiers/zelensky-villa/"
    assert _zoek(client, "zelensky's villa", taal="en")["doorsturen"]["href"] == "/dossiers/zelensky-villa/"


# --- een geplakte link (AC5) ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("link", ["https://www.snopes.com/vac2/", "http://snopes.com/vac2", "snopes.com/vac2/",
                                  "https://www.snopes.com/vac2/?utm_source=whatsapp#top", "HTTPS://WWW.SNOPES.COM/vac2/",
                                  "  https://m.snopes.com/vac2/  "])
def test_a_pasted_link_of_a_fact_check_goes_to_that_fact_check(site, link):
    client, _, nr = site
    assert _zoek(client, link)["doorsturen"] == {"href": f"/nl/fact-checks/{nr['vac2']}/", "soort": "factcheck",
                                                 "naam": BEWERINGEN["vac2"][0]}


def test_a_pasted_link_of_factiz_goes_to_that_fact_check(site):
    client, _, nr = site
    for link in (f"https://factiz.org/nl/fact-checks/{nr['jab']}/", f"factiz.org/fact-checks/{nr['jab']}"):
        assert _zoek(client, link, taal="de")["doorsturen"]["href"] == f"/de/fact-checks/{nr['jab']}/", link


def test_a_link_that_is_not_in_the_release_searches_as_usual(site):
    client, _, _ = site
    uit = _zoek(client, "https://example.com/vac2/")
    assert uit["doorsturen"] is None and uit["totaal"] == 0
    assert _zoek(client, "https://www.snopes.com/bestaat-niet/")["doorsturen"] is None


# --- een vraag naar de site zelf (AC6) ------------------------------------------------------------------------------

@pytest.mark.parametrize("vraag,taal,pad", [("privacy", "nl", "/nl/about/"), ("over factiz", "nl", "/nl/about/"),
                                            ("about", "en", "/about/"), ("api", "de", "/de/platform/"),
                                            ("bronnen", "nl", "/nl/sources/"), ("licenties", "nl", "/nl/sources/"),
                                            ("redacties", "nl", "/nl/newsrooms/"), ("contact", "fr", "/fr/about/")])
def test_a_question_about_the_site_points_to_its_page(site, vraag, taal, pad):
    client, _, _ = site
    ingangen = _zoek(client, vraag, taal=taal)["ingangen"]
    assert {"soort": "pagina", "href": pad}.items() <= ingangen[0].items(), ingangen
    assert any(i.get("href") == pad for i in client.post(f"/api/{taal}/suggesties", data={"q": vraag}).json()["ingangen"])


# --- het woord afmaken (AC2) ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("vraag,aanvulling", [("vacc", "vaccine"), ("Vacc", "Vaccine"), ("the vacc", "the vaccine"),
                                              ("orphans vacc", "orphans vaccine"), ("beef vacc", None),
                                              ("vaccine", None), ("va", None), ("vacc ", None), ('"vacc"', None),
                                              ("zzzq", None)])
def test_the_word_being_typed_is_completed_only_when_the_question_then_finds_something(site, vraag, aanvulling):
    client, pub, _ = site
    assert pub.aanvulling(vraag) == aanvulling
    assert client.post("/api/en/suggesties", data={"q": vraag}).json()["aanvulling"] == aanvulling


def test_a_completion_keeps_the_letters_as_typed(site):
    _, pub, _ = site
    assert pub.aanvulling("Zelen") == "Zelensky"
    assert pub.aanvulling("Child") == "Children"


def test_the_completed_question_comes_first_among_the_suggestions_with_its_count(site):
    client, _, _ = site
    uit = client.post("/api/en/suggesties", data={"q": "vacc"}).json()
    assert uit["zoekvragen"][0] == {"tekst": "vaccine", "aantal": "5"}
    assert [z["tekst"] for z in uit["zoekvragen"]].count("vaccine") == 1
