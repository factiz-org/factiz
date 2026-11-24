"""Namen op het platform (PLAN #33.7, SPECS E9.S11, DESIGN §4u): een naam is een ingang, geen oordeel."""

import json
import re

import pytest
from starlette.testclient import TestClient

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
ZELENSKY = {"en": "Volodymyr Zelensky", "nl": "Volodymyr Zelensky", "de": "Wolodymyr Selenskyj",
            "es": "Volodímir Zelenski", "fr": "Volodymyr Zelensky"}
WHO = {"en": "World Health Organization", "nl": "Wereldgezondheidsorganisatie", "de": "Weltgesundheitsorganisation",
       "es": "Organización Mundial de la Salud", "fr": "Organisation mondiale de la santé"}
SOORT = {"en": ("Person", "Organisation", "Place"), "nl": ("Persoon", "Organisatie", "Plaats"),
         "de": ("Person", "Organisation", "Ort"), "es": ("Persona", "Organización", "Lugar"),
         "fr": ("Personne", "Organisation", "Lieu")}
VIJANDIG = "<img src=x onerror=alert(1)>"


def _pad(taal, pad):
    return pad if taal == "en" else f"/{taal}{pad}"


def _vijf(tekst):
    return {taal: tekst for taal in TALEN}


def _site(tmp_path_factory, met_namen=True, concept=False):
    map_ = tmp_path_factory.mktemp("namen")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "jacht": _claim(lab, 2, "Zelensky bought two yachts for 75 million dollars"),
         "hindi": _claim(lab, 3, "ज़ेलेंस्की ने एक कैसीनो खरीदा", taal="hi"),
         "who": _claim(lab, 4, "WHO says masks do not work in Florida"),
         "knoflook": _claim(lab, 5, "WHO admits garlic water cures covid"),
         "los": _claim(lab, 6, "The moon is made of cheese")}
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2024-03-05")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr")
    _check(lab, n["jacht"], "https://maldita.es/jacht", datum="2023-12-01", taal="es")
    _check(lab, n["hindi"], "https://snopes.com/casino", datum="2024-06-07", taal="hi")
    _check(lab, n["who"], "https://snopes.com/who", datum="2021-05-01")
    _check(lab, n["knoflook"], "https://snopes.com/garlic", datum="2021-01-01")
    _check(lab, n["los"], "https://snopes.com/moon", datum="2020-01-01")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    namen = {"namen": {
        "Q3874799": {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["villa"], nr["jacht"], nr["hindi"]]},
        "Q812": {"soort": "plaats", "namen": _vijf("Florida"), "wikis": 250, "paginas": [nr["villa"], nr["who"]]},
        "Q62266": {"soort": "plaats", "namen": _vijf("Ålesund"), "wikis": 90, "paginas": [nr["villa"], nr["jacht"]]},
        "Q7817": {"soort": "organisatie", "namen": WHO, "wikis": 200, "paginas": [nr["who"], nr["knoflook"]]},
        "Q99": {"soort": "organisatie", "namen": _vijf(VIJANDIG), "wikis": 9, "paginas": [nr["who"], nr["knoflook"]]}},
        "per_pagina": {nr["villa"]: ["Q3874799", "Q812", "Q62266"], nr["jacht"]: ["Q3874799", "Q62266"],
                       nr["hindi"]: ["Q3874799"], nr["who"]: ["Q7817", "Q812", "Q99"], nr["knoflook"]: ["Q7817", "Q99"]}}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11",
                           vertalingen={"nl": {nr["hindi"]: "Zelensky kocht een casino"},
                                        "en": {nr["hindi"]: "Zelensky bought a casino"}}, vertaalmaker="proef",
                           namen=namen if met_namen else None, namen_concept=concept)
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    client.bestand = manifest["bestand"]        # voor de vergelijking met de TypeScript-kant (#34.2bo)
    return client, nr


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.fixture(scope="module")
def kaal(tmp_path_factory):
    return _site(tmp_path_factory, met_namen=False)


@pytest.fixture(scope="module")
def voorbeeld(tmp_path_factory):
    return _site(tmp_path_factory, concept=True)


@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_lists_its_names_as_links_in_the_language_of_the_site(site, taal):
    client, n = site
    namen = client.get(f"/api/{taal}/factcheck/{n['villa']}").json()["namen"]
    # in de volgorde waarin het model ze noemde, met de naam in de taal van de site
    assert [(x["href"], x["naam"]) for x in namen] == [
        (_pad(taal, "/names/Q3874799/"), ZELENSKY[taal]), (_pad(taal, "/names/Q812/"), "Florida"),
        (_pad(taal, "/names/Q62266/"), "Ålesund")]


def test_a_fact_check_without_names_shows_no_such_line(site):
    client, n = site
    r = client.get(f"/api/en/factcheck/{n['los']}")
    assert r.json()["namen"] == [] and "/names/Q" not in r.text


@pytest.mark.parametrize("taal", TALEN)
def test_a_name_shows_the_name_its_kind_and_which_one_is_meant(site, taal):
    client, n = site
    r = client.get(f"/api/{taal}/naam/Q3874799")
    assert r.status_code == 200
    g = r.json()
    assert g["naam"] == ZELENSKY[taal] and g["soort_tekst"] == SOORT[taal][0]
    assert g["wikidata"] == "https://www.wikidata.org/wiki/Q3874799"
    hrefs = [rij["href"] for rij in g["rijen"]]
    assert sorted(hrefs) == sorted(_pad(taal, f"/fact-checks/{n[k]}/") for k in ("villa", "jacht", "hindi"))
    assert _pad(taal, f"/fact-checks/{n['who']}/") not in hrefs
    assert g["alle"] == f"{_pad(taal, '/fact-checks/')}?naam=Q3874799"             # door naar de lijst met filters


def test_a_name_says_the_name_appears_and_never_that_the_person_claimed_something(site):
    client, _ = site
    en = client.get("/api/en/naam/Q3874799").json()
    assert "Fact-checks in which this name appears" in en["zin"] and "says nothing about who made a claim" in en["zin"]
    nl = client.get("/api/nl/naam/Q3874799").json()
    assert "Factchecks waarin deze naam voorkomt" in nl["zin"] and "zegt niets over wie een bewering deed" in nl["zin"]
    tekst = json.dumps([en, nl], ensure_ascii=False).lower().replace("says nothing", "")
    for woord in ("claimed", "said", "spread", "beweerde", "verspreidde"):
        assert woord not in tekst, woord


def test_the_list_filters_on_a_name_and_the_name_is_a_piece_that_can_go(site):
    client, n = site
    r = client.get("/api/nl/archief?naam=Q812")
    assert r.status_code == 200
    g = r.json()
    assert {rij["nummer"] for rij in g["rijen"]} == {n["villa"], n["who"]}
    assert [(s["kop"], s["naam"], s["url"]) for s in g["filters"]["stukjes"]] == [("Naam", "Florida", "/nl/fact-checks/")]
    # het formulier houdt de naam vast als de bezoeker er een filter bij kiest
    assert g["filters"]["gekozen"]["naam"] == "Q812" and ["naam", "Q812"] in g["paren"]
    samen = client.get("/api/nl/archief?jaar=2024&naam=Q812").json()
    assert [rij["nummer"] for rij in samen["rijen"]] == [n["villa"]]
    naam = next(s for s in samen["filters"]["stukjes"] if s["soort"] == "naam")
    assert naam["url"] == "/nl/fact-checks/?jaar=2024"                                 # de naam weg, het jaar blijft
    assert client.get("/api/nl/archief").json()["filters"]["gekozen"]["naam"] == ""


@pytest.mark.parametrize("vraag", ["?naam=Q999", "?naam=q812", "?naam=Q812x", "?naam=%3Cscript%3E", "?naam=Q812&naam=Q7817"])
def test_a_name_filter_that_does_not_exist_is_not_found(site, vraag):
    client, _ = site
    assert client.get("/api/en/archief" + vraag).status_code == 404


def test_search_keeps_the_name_filter(site):
    client, n = site
    g = client.post("/api/en/zoek", data={"q": "Zelensky", "naam": "Q812"}).json()
    assert [rij["nummer"] for rij in g["rijen"]] == [n["villa"]]
    assert [(s["kop"], s["naam"]) for s in g["filters"]["stukjes"]] == [("Name", "Florida")]
    assert g["filters"]["gekozen"]["naam"] == "Q812"


def test_the_register_shows_per_kind_the_letters_that_have_names_and_no_counts(site):
    client, _ = site
    r = client.get("/api/nl/namen")
    assert r.status_code == 200
    groepen = {g["soort"]: g for g in r.json()["groepen"]}
    assert [g["kop"] for g in r.json()["groepen"]] == ["Personen", "Organisaties", "Plaatsen"]
    letters = {s: [x["href"] for x in g["letters"]] for s, g in groepen.items()}
    assert "/nl/names/?letter=v&soort=persoon" in letters["persoon"]
    # een letter zonder namen staat er niet; wat niet met een letter begint wel
    assert letters["plaats"] == ["/nl/names/?letter=a&soort=plaats", "/nl/names/?letter=f&soort=plaats"]
    assert "/nl/names/?letter=0&soort=organisatie" in letters["organisatie"]
    # nergens een telling
    zichtbaar = [g["kop"] for g in groepen.values()] + [x[k] for g in groepen.values() for x in g["letters"] for k in ("teken", "label")]
    assert not any(re.search(r"\d", w) for w in zichtbaar), zichtbaar


def test_a_letter_lists_its_names_on_the_alphabet_of_the_site_language(site):
    client, _ = site
    plaats = client.get("/api/nl/namen?letter=a&soort=plaats").json()["namen"]
    assert [(x["nummer"], x["naam"]) for x in plaats] == [("Q62266", "Ålesund")]                  # Å staat bij de A
    de = client.get("/api/de/namen?letter=w&soort=persoon").json()["namen"]
    assert [x["naam"] for x in de].count("Wolodymyr Selenskyj") == 1
    assert client.get("/api/en/namen?letter=w&soort=persoon").status_code == 404     # in het Engels begint hij met een V
    en = [x["naam"] for x in client.get("/api/en/namen?letter=w&soort=organisatie").json()["namen"]]
    assert "World Health Organization" in en and "Wereldgezondheidsorganisatie" not in en


@pytest.mark.parametrize("vraag", ["?soort=plaats", "?letter=a", "?letter=zz&soort=plaats", "?letter=a&soort=dier",
                                   "?letter=A&soort=plaats", "?letter=a&soort=plaats&p=2", "?letter=b&soort=plaats"])
def test_a_register_address_that_does_not_exist_is_not_found(site, vraag):
    client, _ = site
    assert client.get("/api/en/namen" + vraag).status_code == 404


@pytest.mark.parametrize("pad", ["/api/en/naam/Q999", "/api/en/naam/q812", "/api/en/naam/Q812x", "/api/en/naam/P31",
                                 "/api/en/naam/Q0", "/api/en/naam/Q812/extra"])
def test_an_unknown_or_malformed_name_is_not_found(site, pad):
    client, _ = site
    assert client.get(pad).status_code == 404


def test_a_name_from_the_database_stays_plain_text(site):
    """De gegevens geven de naam zoals ze is, als tekst: het ontsnappen doet de voorkant."""
    client, n = site
    assert client.get("/api/en/naam/Q99").json()["naam"] == VIJANDIG
    assert client.get("/api/en/namen?letter=0&soort=organisatie").json()["namen"] == [
        {"nummer": "Q99", "naam": VIJANDIG, "href": "/names/Q99/"}]
    assert VIJANDIG in [x["naam"] for x in client.get(f"/api/en/factcheck/{n['who']}").json()["namen"]]
    stukjes = client.get("/api/en/archief?naam=Q99").json()["filters"]["stukjes"]
    assert [s["naam"] for s in stukjes] == [VIJANDIG]


def test_a_file_without_names_gives_a_site_without_names_that_still_works(kaal):
    client, n = kaal
    for pad in ("/api/en/namen", "/api/en/naam/Q812", "/api/en/archief?naam=Q812"):
        assert client.get(pad).status_code == 404, pad
    for pad in ("/api/en/archief", f"/api/en/factcheck/{n['villa']}", "/api/en/redacties"):
        r = client.get(pad)
        assert r.status_code == 200 and "/names/" not in r.text, pad


def test_names_the_po_has_not_read_say_so(voorbeeld, site):
    client, _ = voorbeeld
    assert client.get("/api/nl/naam/Q812").json()["concept"] is True
    assert client.get("/api/en/namen").json()["concept"] is True
    echt, _ = site
    assert echt.get("/api/en/naam/Q812").json()["concept"] is False
    assert echt.get("/api/en/namen").json()["concept"] is False


def test_every_name_answer_carries_the_policy_and_never_a_cookie(site):
    client, _ = site
    for pad in ("/api/en/namen", "/api/de/naam/Q812", "/api/en/namen?letter=f&soort=plaats", "/api/en/naam/Q999"):
        h = client.get(pad).headers
        assert "default-src 'none'" in h["content-security-policy"] and "set-cookie" not in h, pad
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin", pad
