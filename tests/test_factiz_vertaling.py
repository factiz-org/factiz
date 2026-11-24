"""De vertaling van een bewering op het platform (PLAN #33.5, SPECS E9.S3 AC6, B32): nooit zonder het origineel, altijd
met de woorden dat het een machinevertaling is en uit welke taal."""

import json

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import i18n
from tests.test_publiceren import REGISTER, _check, _claim, _lab, _variant

HINDI = "यह तस्वीर अयोध्या के रेलवे स्टेशन की है"
ARABISCH = "هذا الفيديو يظهر انفجارا في بيروت"


def _factcheck(client, taal, nummer):
    return client.get(f"/api/{taal}/factcheck/{nummer}").json()


def _rijen(client, taal):
    return {r["nummer"]: r for r in client.get(f"/api/{taal}/archief").json()["rijen"]}


def _site(tmp_path_factory, **extra):
    map_ = tmp_path_factory.mktemp("vertaling")
    lab = _lab(map_)
    n = {"hindi": _claim(lab, 1, HINDI, taal="hi"), "arabisch": _claim(lab, 2, ARABISCH, taal="ar"),
         "engels": _claim(lab, 3, "The moon is made of cheese", taal="en"),
         "nederlands": _claim(lab, 4, "De maan is van kaas", taal="nl"),
         "spaans": _claim(lab, 5, "La luna es de queso", taal="es")}
    for i, (naam, c) in enumerate(n.items()):
        _check(lab, c, f"https://snopes.com/{i}", datum=f"2024-0{i + 1}-01", taal={"hindi": "hi", "arabisch": "ar",
               "engels": "en", "nederlands": "nl", "spaans": "es"}[naam])
    _variant(lab, n["hindi"], "This picture shows the railway station of Ayodhya")
    _variant(lab, n["arabisch"], "This video shows an explosion in Beirut")
    _variant(lab, n["spaans"], "The moon is made of cheese, they say")
    lab.commit()
    nummers = {k: pb.nummer(v) for k, v in n.items()}
    vertalingen = {taal: {nummers[k]: tekst for k, tekst in per.items()} for taal, per in extra.items()}
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11",
                       vertalingen=vertalingen, vertaalmaker="claude-haiku-5-5, weergave-v1")
    return TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False), nummers


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.fixture(scope="module")
def site_nl(tmp_path_factory):
    """Een uitgave waarin het Nederlands zijn leesproef haalde: Hindi, Engels en Spaans hebben een Nederlandse
    vertaling, het Arabisch (nog) niet."""
    return _site(tmp_path_factory, nl={"hindi": "Deze foto toont het station van Ayodhya",
                                       "engels": "De maan is gemaakt van kaas", "spaans": "De maan is van kaas, zeggen ze"})


def test_a_claim_in_another_language_shows_its_translation_above_and_the_original_below(site):
    client, n = site
    g = _factcheck(client, "en", n["hindi"])
    assert g["vertaling"] == {"tekst": "This picture shows the railway station of Ayodhya", "taal": "en",
                              "regel": "Machine-translated from Hindi. Original:"}
    assert g["bewering"] == HINDI and g["taal"] == "hi" and g["richting"] == "ltr"
    # de bewering in de titel hoogstens 45 tekens, zodat het oordeel in de zoekresultaten blijft staan (#34.2bq)
    assert g["kop"]["titel"] == f"{g['stempel']} {g['volgens']}: “This picture shows the railway station of …”"     # #34.2bw
    arabisch = _factcheck(client, "en", n["arabisch"])
    assert arabisch["bewering"] == ARABISCH and arabisch["taal"] == "ar" and arabisch["richting"] == "rtl"
    assert arabisch["vertaling"]["regel"] == "Machine-translated from Arabic. Original:"


def test_the_other_site_languages_show_the_english_translation_and_say_that_it_is_english(site):
    client, n = site
    for taal, regel in [("nl", "Machinevertaling in het Engels, uit het Hindi. Origineel:"),
                        ("de", "Maschinelle Übersetzung ins Englische, Originalsprache Hindi. Original:"),
                        ("es", "Traducción automática al inglés, del hindi. Original:"),
                        ("fr", "Traduction automatique en anglais, langue d'origine : hindi. Original :")]:
        g = _factcheck(client, taal, n["hindi"])
        assert g["vertaling"]["regel"] == regel, taal
        assert g["vertaling"]["taal"] == "en" and g["vertaling"]["tekst"].startswith("This picture shows"), taal
        assert g["bewering"] == HINDI, taal                                   # nooit zonder het origineel


def test_a_claim_in_the_language_of_the_site_or_in_english_stands_as_it_is(site):
    client, n = site
    for taal, nummer, eigen in [("en", n["engels"], "The moon is made of cheese"),
                                ("nl", n["engels"], "The moon is made of cheese"),       # Engels blijft Engels
                                ("nl", n["nederlands"], "De maan is van kaas"),
                                ("en", n["nederlands"], "De maan is van kaas"),          # er ligt geen vertaling
                                ("es", n["spaans"], "La luna es de queso")]:             # de taal van de site zelf
        g = _factcheck(client, taal, nummer)
        assert g["bewering"] == eigen and g["vertaling"] is None and g["richting"] == "ltr", (taal, eigen)
    # dezelfde Spaanse bewering op de Engelse site: daar wel
    assert _factcheck(client, "en", n["spaans"])["vertaling"]["regel"] == "Machine-translated from Spanish. Original:"


def test_a_list_shows_the_translation_with_the_original_beneath_it_and_search_finds_it_by_english_words(site):
    client, n = site
    rijen = _rijen(client, "en")
    hindi = rijen[n["hindi"]]
    assert (hindi["href"], hindi["tekst"], hindi["taal"]) == (f"/fact-checks/{n['hindi']}/", "This picture shows the railway station of Ayodhya", "en")
    assert hindi["origineel"] == {"regel": "Machine-translated from Hindi. Original:", "tekst": HINDI, "taal": "hi", "richting": "ltr"}
    assert (rijen[n["arabisch"]]["origineel"]["tekst"], rijen[n["arabisch"]]["origineel"]["richting"]) == (ARABISCH, "rtl")
    assert (rijen[n["engels"]]["tekst"], rijen[n["engels"]]["taal"], rijen[n["engels"]]["origineel"]) == (
        "The moon is made of cheese", "en", None)
    # Hindi, Arabisch en Spaans; niet Engels of Nederlands
    assert {r["nummer"] for r in rijen.values() if r["origineel"]} == {n["hindi"], n["arabisch"], n["spaans"]}
    gevonden = client.post("/api/en/zoek", data={"q": "railway station"}).json()["rijen"]
    assert [r["href"] for r in gevonden] == [f"/fact-checks/{n['hindi']}/"] and gevonden[0]["origineel"]["tekst"] == HINDI
    assert sum(1 for r in _rijen(client, "nl").values() if r["origineel"]) == 3


def test_every_language_a_claim_can_have_carries_a_name_in_the_five_site_languages():
    assert i18n.taalnaam_in("nl", "hi") == "Hindi" and i18n.taalnaam_in("es", "hi") == "hindi"
    assert i18n.taalnaam_in("en", "pt") == "Portuguese" and i18n.taalnaam_in("de", "so") == "Somali"
    assert i18n.taalnaam_in("fr", "xx") == "xx" and i18n.taalnaam_in("nl", "und") == "und"   # onbekend blijft de code
    for code in i18n.TAALNAAM:
        for taal in i18n.TALEN:
            assert i18n.taalnaam_in(taal, code) not in ("", code), (taal, code)
    for code in ("so", "bs", "om", "sl", "sr", "ti", "uk"):                # erbij gekomen met de herstelde labels
        assert i18n.taalnaam(code) != code


# --- een vertaling in de taal van de site zelf gaat voor de Engelse -------------------------------------------------

def test_a_translation_in_the_language_of_the_site_comes_before_the_english_one(site_nl):
    client, n = site_nl
    hindi = _factcheck(client, "nl", n["hindi"])
    assert hindi["vertaling"] == {"tekst": "Deze foto toont het station van Ayodhya", "taal": "nl",
                                  "regel": "Machinevertaling uit het Hindi. Origineel:"}
    assert hindi["bewering"] == HINDI and hindi["kop"]["titel"] == f"{hindi['stempel']} {hindi['volgens']}: ‘Deze foto toont het station van Ayodhya’"
    # ook een Engelse bewering staat nu in het Nederlands, met het Engels eronder
    engels = _factcheck(client, "nl", n["engels"])
    assert engels["vertaling"] == {"tekst": "De maan is gemaakt van kaas", "taal": "nl",
                                   "regel": "Machinevertaling uit het Engels. Origineel:"}
    assert (engels["bewering"], engels["taal"], engels["richting"]) == ("The moon is made of cheese", "en", "ltr")
    # het Arabisch heeft geen Nederlandse vertaling: dan de Engelse, en de regel zegt dat ze Engels is
    arabisch = _factcheck(client, "nl", n["arabisch"])
    assert arabisch["vertaling"]["taal"] == "en" and arabisch["vertaling"]["tekst"].startswith("This video shows an explosion in Beirut")
    assert arabisch["vertaling"]["regel"] == "Machinevertaling in het Engels, uit het Arabisch. Origineel:"
    # een Nederlandse bewering blijft zoals ze is
    assert _factcheck(client, "nl", n["nederlands"])["vertaling"] is None


def test_the_other_sites_do_not_get_the_dutch_translation(site_nl):
    client, n = site_nl
    hindi = _factcheck(client, "de", n["hindi"])["vertaling"]
    assert hindi["taal"] == "en" and hindi["tekst"].startswith("This picture shows")
    engels_de = client.get(f"/api/de/factcheck/{n['engels']}")
    assert engels_de.json()["vertaling"] is None and "kaas" not in engels_de.text
    assert _factcheck(client, "en", n["hindi"])["vertaling"]["regel"] == "Machine-translated from Hindi. Original:"


def test_lists_and_search_follow_the_language_of_the_site(site_nl):
    client, n = site_nl
    rijen = _rijen(client, "nl")
    assert (rijen[n["hindi"]]["href"], rijen[n["hindi"]]["taal"]) == (f"/nl/fact-checks/{n['hindi']}/", "nl")
    assert rijen[n["hindi"]]["tekst"].startswith("Deze foto toont")
    engels = rijen[n["engels"]]
    assert (engels["tekst"], engels["taal"]) == ("De maan is gemaakt van kaas", "nl")
    assert (engels["origineel"]["regel"], engels["origineel"]["tekst"], engels["origineel"]["taal"]) == (
        "Machinevertaling uit het Engels. Origineel:", "The moon is made of cheese", "en")
    assert rijen[n["arabisch"]]["taal"] == "en" and rijen[n["arabisch"]]["tekst"].startswith("This video shows")
    # alles behalve de Nederlandse bewering
    assert {r["nummer"] for r in rijen.values() if r["origineel"]} == set(n.values()) - {n["nederlands"]}
    gevonden = client.post("/api/nl/zoek", data={"q": "gemaakt kaas"}).json()["rijen"]
    assert [r["href"] for r in gevonden] == [f"/nl/fact-checks/{n['engels']}/"]
    # de woorden van de vraag staan gemarkeerd, ook in de vertaling (E9.S12)
    assert gevonden[0]["taal"] == "nl" and gevonden[0]["stukken"] == [
        ["De maan is ", False], ["gemaakt", True], [" van ", False], ["kaas", True]]
    engels_site = json.dumps(client.get("/api/en/archief").json(), ensure_ascii=False)   # de Engelse site kent de Nederlandse niet
    assert "Deze foto toont" not in engels_site and "This picture shows" in engels_site
