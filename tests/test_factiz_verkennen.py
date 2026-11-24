"""Verkennen (PLAN #34.2ah, SPECS E9.S17): de ring van onderwerpen, de tijd en het waar, als gegevens van het platform.
Dezelfde tellingen als de filters van de lijst: een jaar of een land telt hier wat de lijst met dat filter toont."""

from urllib.parse import parse_qsl, urlsplit

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")

# claim: (tekst, datum van de check, thema, onderdeel, tweede thema, land)
CLAIMS = {
    "vaccin": ("Vaccines contain microchips", "2024-02-01", "health", "vaccines", "", "IN"),
    "knoflook": ("Garlic water cures covid", "2020-05-01", "health", "covid", "", "IN"),
    "zout": ("Salt water cures covid", "2020-06-01", "health", "covid", "", ""),
    "biolab": ("Ukraine hosts secret biolabs", "2022-03-01", "war", "ukraine", "health", "UA"),
    "front": ("A video shows the front line near Kharkiv", "2022-04-01", "war", "ukraine", "", "UA"),
    "grens": ("Troops crossed the border at Ladakh", "2026-10-01", "war", "", "", "IN"),
    "asiel": ("Asielzoekers krijgen gratis een huis", "2012-01-01", "migration", "", "", "NL"),
    "los": ("Something nobody could file", "", None, "", "", ""),
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("verkennen")
    lab = _lab(map_)
    nr, indeling = {}, {}
    for i, (sleutel, (tekst, datum, thema, deel, tweede, land)) in enumerate(CLAIMS.items(), start=1):
        claim = _claim(lab, i, tekst, taal="nl" if sleutel == "asiel" else "en")
        _check(lab, claim, f"https://snopes.com/{sleutel}", datum=datum)
        nr[sleutel] = pb.nummer(claim)
        if thema:
            indeling[nr[sleutel]] = {"thema": thema, "onderdeel": deel, "tweede": tweede, "land": land}
    lab.commit()
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11", indeling=indeling,
                       themas=THEMAS, landen=LANDEN)
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    client.bestand = manifest["bestand"]        # voor de vergelijking met de TypeScript-kant (#34.2bo)
    return client, nr


@pytest.fixture
def lage_drempels(monkeypatch):
    # de echte drempels (300 en 20) haalt een proefuitgave van acht beweringen nooit
    monkeypatch.setattr(db, "VERHOUDING_LAND", 2)
    monkeypatch.setattr(db, "VERHOUDING_THEMA", 1)


def _lijst(client, href):
    """Hoeveel factchecks de lijst toont op het adres waar een staaf of een rij heen wijst."""
    deel = urlsplit(href)
    taal = deel.path.strip("/").split("/")[0] if deel.path.count("/") > 2 else "en"
    vraag = "&".join(f"{k}={v}" for k, v in parse_qsl(deel.query))
    antwoord = client.get(f"/api/{taal}/archief?{vraag}")
    assert antwoord.status_code == 200, href
    return antwoord.json()["totaal"]


def test_without_a_choice_the_ring_shows_every_theme_and_time_and_place_count_everything(site):
    client, _ = site
    g = client.get("/api/nl/verkennen").json()
    assert g["titel"] == "Verkennen" and g["inleiding"] and g["gekozen"] is None
    ring = g["ring"]
    # een factcheck met een tweede thema telt bij beide; het midden telt elke factcheck met een thema één keer
    assert [(t["sleutel"], t["aantal"], t["aan"]) for t in ring["themas"]] == [
        ("health", 4, False), ("war", 3, False), ("migration", 1, False)]
    assert ring["totaal"] == 7 and ring["totaal_tekst"] == "7 factchecks met een thema"
    assert ring["themas"][0]["href"] == "/nl/explore/?thema=health" and ring["themas"][0]["aantal_tekst"] == "4 factchecks"
    tijd = g["tijd"]
    assert [j["jaar"] for j in tijd["jaren"]] == [str(j) for j in range(2016, 2027)]
    assert {j["jaar"]: j["aantal"] for j in tijd["jaren"] if j["aantal"]} == {"2020": 2, "2022": 2, "2024": 1, "2026": 1}
    assert [j["jaar"] for j in tijd["jaren"] if j["lopend"]] == ["2026"]
    assert tijd["eerder"] == 1 and tijd["zonder_datum"] == 1
    # wat buiten de jaren valt, staat eronder; geen uitleg over hoe er geteld is (PO 2026-11-22)
    assert "Van voor 2016: 1." in tijd["noot"] and "Zonder datum: 1." in tijd["noot"] and "oktober" not in tijd["noot"]
    waar = g["waar"]
    assert waar["maat"] == "aantal" and waar["maten"] == []           # de verhouding hoort bij een thema
    assert [(r["code"], r["aantal"]) for r in waar["landen"]] == [("IN", 3), ("UA", 2), ("NL", 1)]
    assert waar["landen"][0]["naam"] == "India" and waar["landen"][0]["href"] == "/nl/fact-checks/?land=IN"
    assert "met_land" not in waar and "tweede" not in g["ring"]


def test_a_chosen_theme_narrows_time_and_place_and_names_its_parts(site):
    client, _ = site
    g = client.get("/api/nl/verkennen?thema=health").json()
    assert g["gekozen"]["sleutel"] == "health" and g["gekozen"]["naam"] == "Gezondheid" and g["gekozen"]["aantal"] == 4
    assert g["gekozen"]["lijst"] == "/nl/fact-checks/?thema=health"
    assert [(o["sleutel"], o["aantal"], o["href"]) for o in g["gekozen"]["onderdelen"]] == [
        ("vaccines", 1, "/nl/themes/health/vaccines/"), ("covid", 2, "/nl/themes/health/covid/")]
    assert [t["sleutel"] for t in g["ring"]["themas"] if t["aan"]] == ["health"]
    assert g["ring"]["regel"] == "4 van de 7 factchecks met een thema"
    assert g["alles_href"] == "/nl/explore/"
    assert {j["jaar"]: j["aantal"] for j in g["tijd"]["jaren"] if j["aantal"]} == {"2020": 2, "2022": 1, "2024": 1}
    assert g["tijd"]["eerder"] == 0 and g["tijd"]["zonder_datum"] == 0
    assert [(r["code"], r["aantal"]) for r in g["waar"]["landen"]] == [("IN", 2), ("UA", 1)]
    assert [(m["waarde"], m["aan"], m["href"]) for m in g["waar"]["maten"]] == [
        ("aantal", True, "/nl/explore/?thema=health"), ("verhouding", False, "/nl/explore/?maat=verhouding&thema=health")]


@pytest.mark.parametrize("adres", ["/api/nl/verkennen", "/api/nl/verkennen?thema=health", "/api/nl/verkennen?thema=war",
                                   "/api/en/verkennen?thema=migration"])
def test_every_year_and_country_opens_the_list_that_shows_exactly_that_many(site, adres):
    client, _ = site
    g = client.get(adres).json()
    for j in g["tijd"]["jaren"]:
        if j["aantal"]:
            assert _lijst(client, j["href"]) == j["aantal"], (adres, j)
            assert ("thema", g["gekozen"]["sleutel"]) in parse_qsl(urlsplit(j["href"]).query) if g["gekozen"] else True
    for r in g["waar"]["landen"]:
        assert _lijst(client, r["href"]) == r["aantal"], (adres, r)
    if g["gekozen"]:
        assert _lijst(client, g["gekozen"]["lijst"]) == g["gekozen"]["aantal"]


def test_the_ratio_is_the_share_of_the_theme_in_a_country_over_its_share_everywhere(site, lage_drempels):
    client, _ = site
    g = client.get("/api/nl/verkennen?maat=verhouding&thema=health").json()
    waar = g["waar"]
    assert waar["maat"] == "verhouding" and [m["aan"] for m in waar["maten"]] == [False, True]
    # met een land: 6 factchecks, waarvan 3 over gezondheid (de helft). India: 2 van 3, Oekraïne: 1 van 2.
    rijen = [(r["code"], round(r["waarde"], 3), r["aantal"], r["van"]) for r in waar["landen"]]
    assert rijen == [("IN", 1.333, 2, 3), ("UA", 1.0, 1, 2)]
    assert waar["landen"][0]["tekst"] == "1,3× (2 van 3)"
    assert client.get("/api/en/verkennen?maat=verhouding&thema=health").json()["waar"]["landen"][0]["tekst"] == "1.3× (2 of 3)"
    assert "2" in waar["noot"] and "1" in waar["noot"] and "Gezondheid" in waar["noot"]
    assert "%" not in waar["noot"] and all("%" not in r["tekst"] for r in waar["landen"])


def test_a_country_below_either_threshold_has_no_ratio(site, monkeypatch):
    client, _ = site
    monkeypatch.setattr(db, "VERHOUDING_LAND", 3)       # alleen India heeft 3 factchecks met dit land
    monkeypatch.setattr(db, "VERHOUDING_THEMA", 2)      # en 2 daarvan over gezondheid
    assert [r["code"] for r in client.get("/api/nl/verkennen?maat=verhouding&thema=health").json()["waar"]["landen"]] == ["IN"]
    monkeypatch.setattr(db, "VERHOUDING_THEMA", 3)
    g = client.get("/api/nl/verkennen?maat=verhouding&thema=health").json()
    assert g["waar"]["landen"] == [] and g["waar"]["leeg"]


def test_the_real_thresholds_are_the_agreed_ones():
    assert (db.VERHOUDING_LAND, db.VERHOUDING_THEMA, db.VERKEN_JAREN, db.VERKEN_LANDEN) == (300, 20, 11, 10)


@pytest.mark.parametrize("taal", TALEN)
def test_every_language_has_its_own_words_and_addresses(site, taal):
    client, _ = site
    g = client.get(f"/api/{taal}/verkennen?thema=war").json()
    voor = "" if taal == "en" else f"/{taal}"
    assert g["alles_href"] == f"{voor}/explore/" and g["gekozen"]["lijst"] == f"{voor}/fact-checks/?thema=war"
    assert g["titel"] and g["tijd"]["kop"] and g["waar"]["kop"] and g["ring"]["kop"]
    # bij het aantal geen zin dat tellen geen nepnieuws meten is (PO 2026-11-22: "Ja, alle drie weg"); de verhouding
    # houdt haar legenda
    assert g["waar"]["noot"] == "" and client.get(f"/api/{taal}/verkennen").json()["waar"]["noot"] == ""
    assert client.get(f"/api/{taal}/verkennen?thema=war&maat=verhouding").json()["waar"]["noot"]
    assert all(t["href"].startswith(f"{voor}/explore/?thema=") for t in g["ring"]["themas"])


@pytest.mark.parametrize("adres", ["/api/nl/verkennen?thema=sport", "/api/nl/verkennen?thema=", "/api/nl/verkennen?thema=War",
                                   "/api/nl/verkennen?maat=verhouding", "/api/nl/verkennen?thema=health&maat=aantal",
                                   "/api/nl/verkennen?thema=health&maat=procent", "/api/nl/verkennen?land=IN",
                                   "/api/nl/verkennen?thema=health&thema=war", "/api/nl/verkennen?thema=vaccines"])
def test_an_address_that_is_not_one_view_does_not_exist(site, adres):
    client, _ = site
    assert client.get(adres).status_code == 404


# --- de wereldkaart (PLAN #34.2am, SPECS E9.S20) -----------------------------------------------------------------------

def test_the_map_gets_every_country_with_its_value_a_step_and_a_legend(site):
    client, _ = site
    waar = client.get("/api/nl/verkennen").json()["waar"]
    kaart = {r["code"]: r for r in waar["kaart"]}
    assert set(kaart) == {"IN", "UA", "NL"} and kaart["IN"]["waarde"] == 3 and kaart["IN"]["href"] == "/nl/fact-checks/?land=IN"
    assert all(1 <= r["trap"] <= 5 for r in kaart.values())
    # meer factchecks, nooit een lichtere trap
    volgorde = sorted(kaart.values(), key=lambda r: r["waarde"])
    assert [r["trap"] for r in volgorde] == sorted(r["trap"] for r in volgorde)
    assert 1 <= len(waar["legenda"]) <= 5 and all(t["tekst"] and "%" not in t["tekst"] for t in waar["legenda"])
    assert [t["trap"] for t in waar["legenda"]] == sorted(t["trap"] for t in waar["legenda"])
    assert waar["alle_kop"] and waar["te_klein"] and waar["kaart_bron"]
    # de lijst onder de kaart staat op naam
    assert [r["naam"] for r in waar["kaart"]] == sorted(r["naam"] for r in waar["kaart"])


def test_with_the_ratio_the_map_shows_every_country_above_the_thresholds_not_only_the_top_ten(site, lage_drempels, monkeypatch):
    client, _ = site
    monkeypatch.setattr(db, "VERKEN_LANDEN", 1)
    waar = client.get("/api/nl/verkennen?maat=verhouding&thema=health").json()["waar"]
    assert [r["code"] for r in waar["landen"]] == ["IN"]                 # de staven: de top
    assert {r["code"] for r in waar["kaart"]} == {"IN", "UA"}            # de kaart: alles boven de drempels
    trap = {r["code"]: r["trap"] for r in waar["kaart"]}
    assert trap["IN"] >= trap["UA"]
    assert any("1" in t["tekst"] for t in waar["legenda"])


def test_a_step_follows_its_bounds(site):
    from factiz_site import app as fa_
    grenzen = fa_.grenzen_aantal([1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987])
    assert grenzen == sorted(set(grenzen)) and len(grenzen) <= 4
    assert fa_.trap(0.5, [1, 2]) == 1 and fa_.trap(1, [1, 2]) == 2 and fa_.trap(5, [1, 2]) == 3
