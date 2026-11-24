"""Thema's en landen op het platform (PLAN #33.4, SPECS E9.S5 AC2): pagina's die zich vanzelf vullen, en filters."""

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")


def _n(nl, en, de, es, fr):
    return {"nl": nl, "en": en, "de": de, "es": es, "fr": fr}


THEMAS = [
    {"sleutel": "health", "naam": _n("Gezondheid", "Health", "Gesundheit", "Salud", "Santé"), "omschrijving": "x",
     "onderdelen": [{"sleutel": "vaccines", "naam": _n("Vaccins", "Vaccines", "Impfstoffe", "Vacunas", "Vaccins")},
                    {"sleutel": "covid", "naam": _n("Corona", "Covid-19", "Corona", "Covid-19", "Covid-19")}]},
    {"sleutel": "war", "naam": _n("Oorlog en conflict", "War and conflict", "Krieg und Konflikte", "Guerra y conflictos",
                                  "Guerre et conflits"), "omschrijving": "x",
     "onderdelen": [{"sleutel": "ukraine", "naam": _n("Rusland en Oekraïne", "Russia and Ukraine",
                                                      "Russland und die Ukraine", "Rusia y Ucrania", "Russie et Ukraine")}]},
    {"sleutel": "migration", "naam": _n("Migratie", "Migration", "Migration", "Migración", "Migration"),
     "omschrijving": "x", "onderdelen": []},
]
LANDEN = {"IN": _n("India", "India", "Indien", "India", "Inde"), "UA": _n("Oekraïne", "Ukraine", "Ukraine", "Ucrania", "Ukraine"),
          "NL": _n("Nederland", "Netherlands", "Niederlande", "Países Bajos", "Pays-Bas")}


def _pad(taal, pad):
    return pad if taal == "en" else f"/{taal}{pad}"


def _site(tmp_path_factory, met_themas=True):
    map_ = tmp_path_factory.mktemp("themas")
    lab = _lab(map_)
    n = {"vaccin": _claim(lab, 1, "Vaccines contain microchips"),
         "corona": _claim(lab, 2, "Garlic water cures covid"),
         "biolab": _claim(lab, 3, "Ukraine hosts secret biolabs"),
         "front": _claim(lab, 4, "A video shows the front line near Kharkiv"),
         "asiel": _claim(lab, 5, "Asielzoekers krijgen gratis een huis", taal="nl"),
         "zonder": _claim(lab, 6, "Something nobody could file")}
    for i, c in enumerate(n.values()):
        _check(lab, c, f"https://snopes.com/{i}", datum=f"2024-0{i + 1}-01")
    indeling = {pb.nummer(n["vaccin"]): {"thema": "health", "onderdeel": "vaccines", "tweede": "", "land": "IN"},
                pb.nummer(n["corona"]): {"thema": "health", "onderdeel": "covid", "tweede": "", "land": ""},
                pb.nummer(n["biolab"]): {"thema": "war", "onderdeel": "ukraine", "tweede": "health", "land": "UA"},
                pb.nummer(n["front"]): {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"},
                pb.nummer(n["asiel"]): {"thema": "migration", "onderdeel": "", "tweede": "", "land": "NL"}}
    lab.commit()
    extra = {"indeling": indeling, "themas": THEMAS, "landen": LANDEN} if met_themas else {}
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11", **extra)
    return TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False), {k: pb.nummer(v) for k, v in n.items()}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.fixture(scope="module")
def kaal(tmp_path_factory):
    return _site(tmp_path_factory, met_themas=False)


def _hrefs(client, adres):
    return [r["href"] for r in client.get(adres).json()["rijen"]]


def test_the_overview_names_every_theme_in_the_language_of_the_site_with_its_parts_and_counts(site):
    client, _ = site
    nl = client.get("/api/nl/themas")
    assert nl.status_code == 200
    themas = {th["sleutel"]: th for th in nl.json()["themas"]}
    assert (themas["health"]["naam"], themas["health"]["href"]) == ("Gezondheid", "/nl/themes/health/")
    # een bewering met een tweede thema telt bij beide thema's mee
    assert [(th["naam"], th["aantal"]) for th in themas.values()] == [
        ("Gezondheid", "3 factchecks"), ("Oorlog en conflict", "2 factchecks"), ("Migratie", "1 factcheck")]
    assert ("Vaccins", "/nl/themes/health/vaccines/") in [(o["naam"], o["href"]) for o in themas["health"]["onderdelen"]]
    for taal, naam in (("de", "Gesundheit"), ("es", "Salud"), ("fr", "Santé"), ("en", "Health")):
        assert naam in [th["naam"] for th in client.get(f"/api/{taal}/themas").json()["themas"]], taal


@pytest.mark.parametrize("taal", TALEN)
def test_a_theme_and_a_part_fill_themselves_in_every_language(site, taal):
    client, n = site
    thema = client.get(f"/api/{taal}/thema/war")
    assert thema.status_code == 200
    g = thema.json()
    assert set(r["href"] for r in g["rijen"]) == {_pad(taal, f"/fact-checks/{n['biolab']}/"), _pad(taal, f"/fact-checks/{n['front']}/")}
    assert _pad(taal, "/themes/war/ukraine/") in [o["href"] for o in g["onderdelen"]]
    assert g["alle"] == f'{_pad(taal, "/fact-checks/")}?thema=war'
    deel = client.get(f"/api/{taal}/thema/health/vaccines")
    assert deel.status_code == 200 and [r["href"] for r in deel.json()["rijen"]] == [_pad(taal, f"/fact-checks/{n['vaccin']}/")]
    assert deel.json()["thema_href"] == _pad(taal, "/themes/health/")              # terug naar het thema


def test_a_theme_or_part_the_file_does_not_know_is_not_found(site):
    client, _ = site
    for fout in ("astrology", "health/ukraine", "vaccines", "health/vaccines/x", "HEALTH"):
        assert client.get(f"/api/en/thema/{fout}").status_code == 404, fout


def test_the_list_filters_on_theme_part_and_country_and_refuses_what_does_not_belong_together(site):
    client, n = site
    gezondheid = set(_hrefs(client, "/api/en/archief?thema=health"))
    assert gezondheid == {f"/fact-checks/{n[k]}/" for k in ("vaccin", "corona", "biolab")}     # ook als tweede thema
    assert _hrefs(client, "/api/en/archief?onderdeel=covid&thema=health") == [f"/fact-checks/{n['corona']}/"]
    assert set(_hrefs(client, "/api/en/archief?land=UA")) == {f"/fact-checks/{n[k]}/" for k in ("biolab", "front")}
    assert _hrefs(client, "/api/en/archief?land=UA&thema=health") == [f"/fact-checks/{n['biolab']}/"]
    for fout in ("?thema=astrology", "?land=ZZ", "?land=ua"):
        assert client.get("/api/en/archief" + fout).status_code == 404, fout
    # een onderdeel zonder zijn thema komt uit het formulier (een ander thema gekozen) en valt dan weg (E9.S10 AC4)
    for vraag, paren in (("?onderdeel=covid", []), ("?onderdeel=ukraine&thema=health", [["thema", "health"]])):
        r = client.get("/api/en/archief" + vraag)
        assert r.status_code == 200 and r.json()["paren"] == paren, vraag
    # het formulier toont het gekozen thema, de onderdelen van dat thema en de landen, in de taal van de site
    f = client.get("/api/nl/archief?thema=health").json()["filters"]
    assert f["gekozen"]["thema"] == "health"
    assert ("health", "Gezondheid", True) in [(k["waarde"], k["naam"], k["aan"]) for k in f["lijsten"]["thema"]]
    assert [(k["waarde"], k["naam"]) for k in f["lijsten"]["onderdeel"]] == [("vaccines", "Vaccins"), ("covid", "Corona")]
    # alleen de landen van de factchecks binnen het thema, met hun aantal; Nederland zou niets tonen (E9.S12)
    assert [(k["waarde"], k["naam"], k["aantal"]) for k in f["lijsten"]["land"]] == [("IN", "India", "1"), ("UA", "Oekraïne", "1")]
    alle = client.get("/api/nl/archief").json()["filters"]["lijsten"]["land"]
    assert ("NL", "Nederland") in [(k["waarde"], k["naam"]) for k in alle]


def test_a_fact_check_names_its_theme_part_and_country_as_links_and_one_without_a_theme_names_none(site):
    client, n = site
    g = client.get(f"/api/nl/factcheck/{n['biolab']}").json()
    assert (g["thema"]["href"], g["thema"]["naam"]) == ("/nl/themes/war/", "Oorlog en conflict")
    assert (g["onderdeel"]["href"], g["onderdeel"]["naam"]) == ("/nl/themes/war/ukraine/", "Rusland en Oekraïne")
    assert (g["tweede"]["href"], g["tweede"]["naam"]) == ("/nl/themes/health/", "Gezondheid")          # het tweede thema
    assert (g["land"]["href"], g["land"]["naam"]) == ("/nl/fact-checks/?land=UA", "Oekraïne")
    assert client.get(f"/api/es/factcheck/{n['biolab']}").json()["land"]["naam"] == "Ucrania"
    zonder = client.get(f"/api/nl/factcheck/{n['zonder']}")
    assert [zonder.json()[k] for k in ("thema", "onderdeel", "tweede", "land")] == [None] * 4
    assert "/themes/" not in zonder.text and "?land=" not in zonder.text


def test_a_file_without_themes_gives_a_site_without_themes_that_still_works(kaal):
    client, n = kaal
    assert client.get("/api/en/archief").status_code == 200
    assert client.get(f"/api/en/factcheck/{n['vaccin']}").status_code == 200
    assert client.get("/api/en/themas").status_code == 404 and client.get("/api/en/thema/health").status_code == 404
    assert client.get("/api/en/archief?thema=health").status_code == 404
    for pad in ("/api/en/archief", f"/api/en/factcheck/{n['vaccin']}"):
        assert "/themes/" not in client.get(pad).text, pad
