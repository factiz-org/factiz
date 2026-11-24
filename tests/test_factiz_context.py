"""Contextkaarten naast een factcheck (PLAN #34.2an, SPECS E9.S21): hoogstens vier, in vaste volgorde, alleen met
gegevens, met dezelfde getallen als Verkennen, het netwerk en de lijst, en elke link bestaat."""

from urllib.parse import urlsplit

import pytest
from starlette.testclient import TestClient

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db
from tests.test_factiz_dossiers import INLEIDING, NAAM, _dossier
from tests.test_factiz_namen import WHO, ZELENSKY, _vijf
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
Z, FLORIDA, WHO_Q, X = "Q3874799", "Q812", "Q7817", "Q99"

# claim: (tekst, host, datum, eigen woorden, thema, land)
CLAIMS = {
    "villa": ("Zelensky bought a villa in Florida", "https://snopes.com", "2024-03-05", "False", "war", "UA"),
    "jacht": ("Zelensky bought two yachts", "https://maldita.es", "2023-12-01", "False", "war", "UA"),
    "hindi": ("Zelensky bought a casino", "https://factcheck.afp.com", "2024-06-07", "False", "war", "UA"),
    "who": ("WHO says masks do not work in Florida", "https://snopes.com", "2021-05-01", "False", "health", "IN"),
    "knoflook": ("WHO admits garlic water cures covid", "https://maldita.es", "2021-01-01", "False", "health", "IN"),
    "vloed": ("A video shows a flood in Valencia", "https://snopes.com", "2024-11-01", "Altered", "health", ""),
    "kaal": ("Something nobody could file", "https://snopes.com", "", "False", None, ""),
}


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("context")
    lab = _lab(map_)
    nr, indeling = {}, {}
    for i, (sleutel, (tekst, host, datum, eigen, thema, land)) in enumerate(CLAIMS.items(), start=1):
        claim = _claim(lab, i, tekst)
        _check(lab, claim, f"{host}/{sleutel}", datum=datum, eigen=eigen)
        nr[sleutel] = pb.nummer(claim)
        if thema:
            indeling[nr[sleutel]] = {"thema": thema, "onderdeel": "", "tweede": "", "land": land}
    lab.commit()
    namen = {"namen": {
        Z: {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["villa"], nr["jacht"], nr["hindi"]]},
        FLORIDA: {"soort": "plaats", "namen": _vijf("Florida"), "wikis": 250, "paginas": [nr["villa"], nr["who"]]},
        WHO_Q: {"soort": "organisatie", "namen": WHO, "wikis": 200, "paginas": [nr["who"], nr["knoflook"]]},
        X: {"soort": "organisatie", "namen": _vijf("Xorg"), "wikis": 9, "paginas": [nr["who"], nr["knoflook"]]}},
        "per_pagina": {nr["villa"]: [Z, FLORIDA], nr["jacht"]: [Z], nr["hindi"]: [Z], nr["who"]: [WHO_Q, FLORIDA, X],
                       nr["knoflook"]: [WHO_Q, X]}}
    dossiers = [_dossier("zelensky-luxury", [nr["villa"], nr["jacht"], nr["hindi"]], naam=NAAM, inleiding=INLEIDING)]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11", indeling=indeling,
                           themas=THEMAS, landen=LANDEN, namen=namen, dossiers=dossiers,
                           soortwoorden={"Altered": "bewerkt"})
    return manifest["bestand"], nr


@pytest.fixture
def site(bestand, monkeypatch):
    monkeypatch.setattr(db, "NETWERK_NAMEN", 4)
    monkeypatch.setattr(db, "NETWERK_SAMEN", 1)
    monkeypatch.setattr(db, "VERHOUDING_LAND", 1)
    monkeypatch.setattr(db, "VERHOUDING_THEMA", 1)
    pad, nr = bestand
    return TestClient(fa.maak_app(pad), follow_redirects=False), nr


def _context(client, nr, taal="nl"):
    return client.get(f"/api/{taal}/factcheck/{nr}").json()["context"]


def test_a_fact_check_in_a_dossier_shows_the_dossier_first_and_at_most_four_cards(site):
    client, nr = site
    kaarten = _context(client, nr["villa"])
    assert [k["soort"] for k in kaarten] == ["dossier", "waar", "namen", "wanneer"]
    dossier = kaarten[0]
    assert dossier["href"] == "/nl/dossiers/zelensky-luxury/" and dossier["naam"] == NAAM["nl"]
    assert [(j["jaar"], j["aantal"], j["aan"]) for j in dossier["jaren"]] == [("2023", 1, False), ("2024", 2, True)]
    assert "3" in dossier["zin"]


def test_without_a_dossier_or_a_kind_the_next_cards_move_up(site):
    client, nr = site
    assert [k["soort"] for k in _context(client, nr["knoflook"])] == ["waar", "namen", "wanneer", "redactie"]
    assert [k["soort"] for k in _context(client, nr["vloed"])] == ["wanneer", "kenmerk", "redactie"]
    assert [k["soort"] for k in _context(client, nr["kaal"])] == ["redactie"]


def test_the_cards_count_what_explore_the_network_and_the_list_count(site):
    client, nr = site
    waar, namen, wanneer = _context(client, nr["villa"])[1:4]
    assert waar["code"] == "UA" and waar["thema"] == "war"
    ua = client.get("/api/nl/archief?land=UA").json()["totaal"]
    ua_oorlog = client.get("/api/nl/archief?land=UA&thema=war").json()["totaal"]
    assert f"{ua} factchecks" in waar["zin"] and f"{ua_oorlog} over Oorlog en conflict" in waar["zin"]
    # geen uitleg over hoe Factiz telt (PO 2026-11-22: "Dat soort uitlegzinnetjes ... Hier kan het ook weg.")
    assert "noot" not in waar and "%" not in waar["zin"]
    verkennen = client.get("/api/nl/verkennen?thema=war").json()["tijd"]["jaren"]
    assert [(j["jaar"], j["aantal"]) for j in wanneer["jaren"]] == [(j["jaar"], j["aantal"]) for j in verkennen]
    assert [j["jaar"] for j in wanneer["jaren"] if j["aan"]] == ["2024"]
    net = client.get(f"/api/nl/netwerk?naam={Z}").json()["gekozen"]["buren"]
    zelensky = next(n for n in namen["namen"] if n["href"].endswith(f"naam={Z}"))
    assert all(b["naam"] in zelensky["regel"] for b in net[:2]) and namen["noot"]


def test_a_kind_and_a_form_count_within_the_theme_and_link_to_the_list_with_both_filters(site):
    client, nr = site
    kenmerk = next(k for k in _context(client, nr["vloed"]) if k["soort"] == "kenmerk")
    rijen = {r["wat"]: r for r in kenmerk["rijen"]}
    assert set(rijen) == {"soort", "vorm"}
    assert rijen["vorm"]["href"] == "/nl/fact-checks/?thema=health&vorm=video"
    assert rijen["soort"]["href"] == "/nl/fact-checks/?soort=bewerkt&thema=health"
    assert client.get("/api/nl/archief?thema=health&vorm=video").json()["totaal"] == 1 and "1" in rijen["vorm"]["zin"]


def _api(href):
    deel = urlsplit(href)
    stukken = deel.path.strip("/").split("/")
    taal = stukken.pop(0) if stukken[0] in TALEN else "en"
    vraag = f"?{deel.query}" if deel.query else ""
    if stukken[0] == "explore":
        return f"/api/{taal}/netwerk{vraag}" if stukken[1:] == ["network"] else f"/api/{taal}/verkennen{vraag}"
    if stukken[0] == "fact-checks":
        return f"/api/{taal}/archief{vraag}"
    if stukken[0] == "dossiers":
        return f"/api/{taal}/dossier/{stukken[1]}"
    raise AssertionError(href)


@pytest.mark.parametrize("taal", TALEN)
def test_every_card_asks_a_question_says_what_it_counts_and_every_link_exists(site, taal):
    client, nr = site
    for sleutel in CLAIMS:
        for k in _context(client, nr[sleutel], taal):
            assert k["vraag"] and "%" not in str(k), (sleutel, k)
            links = [k["href"]] if k.get("href") else []
            links += [r["href"] for r in k.get("rijen", [])] + [n["href"] for n in k.get("namen", [])]
            assert links, (sleutel, k["soort"])
            for href in links:
                assert client.get(_api(href)).status_code == 200, (sleutel, href)


def test_the_real_maximum_is_four():
    assert fa.CONTEXT_MAX == 4
