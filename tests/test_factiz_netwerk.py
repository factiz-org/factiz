"""Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18): welke namen samen voorkomen in nagetrokken beweringen, en in welk
thema. De gegevens nagerekend op een proefuitgave, de schikking zonder overlap en in elke taal gelijk."""

import itertools
import random

import pytest
from starlette.testclient import TestClient

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db, netwerk
from tests.test_factiz_namen import VIJANDIG, WHO, ZELENSKY, _vijf
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
Z, FLORIDA, ALESUND, WHO_Q, VIJAND = "Q3874799", "Q812", "Q62266", "Q7817", "Q99"


def _maak(tmp_path_factory, met_namen=True):
    map_ = tmp_path_factory.mktemp("netwerk")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "jacht": _claim(lab, 2, "Zelensky bought two yachts for 75 million dollars"),
         "hindi": _claim(lab, 3, "Zelensky bought a casino"),
         "who": _claim(lab, 4, "WHO says masks do not work in Florida"),
         "knoflook": _claim(lab, 5, "WHO admits garlic water cures covid")}
    # elke persoon heeft pagina's van minstens twee redacties nodig (SPECS E9.S11 AC2)
    hosts = ["https://snopes.com", "https://maldita.es", "https://factcheck.afp.com", "https://snopes.com", "https://maldita.es"]
    for i, (c, host) in enumerate(zip(n.values(), hosts)):
        _check(lab, c, f"{host}/{i}", datum=f"2024-0{i + 1}-01")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    oorlog = {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"}
    gezond = {"thema": "health", "onderdeel": "covid", "tweede": "", "land": ""}
    indeling = {nr["villa"]: oorlog, nr["jacht"]: oorlog, nr["hindi"]: oorlog, nr["who"]: gezond, nr["knoflook"]: gezond}
    namen = {"namen": {
        Z: {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["villa"], nr["jacht"], nr["hindi"]]},
        FLORIDA: {"soort": "plaats", "namen": _vijf("Florida"), "wikis": 250, "paginas": [nr["villa"], nr["who"]]},
        ALESUND: {"soort": "plaats", "namen": _vijf("Ålesund"), "wikis": 90, "paginas": [nr["villa"], nr["jacht"]]},
        WHO_Q: {"soort": "organisatie", "namen": WHO, "wikis": 200, "paginas": [nr["who"], nr["knoflook"]]},
        VIJAND: {"soort": "organisatie", "namen": _vijf(VIJANDIG), "wikis": 9, "paginas": [nr["who"], nr["knoflook"]]}},
        "per_pagina": {nr["villa"]: [Z, FLORIDA, ALESUND], nr["jacht"]: [Z, ALESUND], nr["hindi"]: [Z],
                       nr["who"]: [WHO_Q, FLORIDA, VIJAND], nr["knoflook"]: [WHO_Q, VIJAND]}}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11", indeling=indeling,
                           themas=THEMAS, landen=LANDEN, namen=namen if met_namen else None)
    return manifest["bestand"]


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    return _maak(tmp_path_factory)


@pytest.fixture
def site(bestand, monkeypatch):
    # de echte drempels (70 namen, 25 samen) haalt een proefuitgave van vijf beweringen nooit
    monkeypatch.setattr(db, "NETWERK_NAMEN", 4)
    monkeypatch.setattr(db, "NETWERK_SAMEN", 1)
    return TestClient(fa.maak_app(bestand), follow_redirects=False)


def _paren(g):
    return {(frozenset((r["a"], r["b"])), r["samen"]) for r in g["randen"]}


def test_the_network_holds_the_names_in_most_fact_checks_and_every_pair_above_the_threshold(site):
    g = site.get("/api/nl/netwerk").json()
    assert g["titel"] and g["inleiding"] and g["let_op"] and g["gekozen"] is None
    # de vier met de meeste factchecks; bij gelijke aantallen het laagste nummer van Wikidata eerst
    assert {k["id"] for k in g["knopen"]} == {Z, VIJAND, FLORIDA, WHO_Q}
    knoop = {k["id"]: k for k in g["knopen"]}
    assert knoop[Z]["aantal"] == 3 and knoop[Z]["naam"] == "Volodymyr Zelensky" and knoop[Z]["soort"] == "persoon"
    assert _paren(g) == {(frozenset((Z, FLORIDA)), 1), (frozenset((FLORIDA, WHO_Q)), 1), (frozenset((FLORIDA, VIJAND)), 1),
                         (frozenset((WHO_Q, VIJAND)), 2)}
    # het thema waarin een naam het vaakst voorkomt; bij gelijkspel het eerste thema van de uitgave
    assert (knoop[Z]["thema"], knoop[WHO_Q]["thema"], knoop[FLORIDA]["thema"]) == ("war", "health", "health")
    assert knoop[Z]["href"] == f"/nl/explore/network/?naam={Z}" and knoop[Z]["pagina"] == f"/nl/names/{Z}/"
    # de lijst naast het netwerk staat op alfabet, nooit op aantal (SPECS E9.S11 AC5)
    assert [n["naam"] for n in g["namen"]] == sorted((n["naam"] for n in g["namen"]), key=db._alfabet)


def test_a_higher_threshold_keeps_only_the_pairs_that_reach_it(site, monkeypatch):
    monkeypatch.setattr(db, "NETWERK_SAMEN", 2)
    assert _paren(site.get("/api/nl/netwerk").json()) == {(frozenset((WHO_Q, VIJAND)), 2)}


def test_the_real_thresholds_are_the_agreed_ones():
    assert (db.NETWERK_NAMEN, db.NETWERK_SAMEN) == (70, 25)


def test_the_layout_fits_the_canvas_overlaps_nothing_and_is_the_same_in_every_language_and_every_time(site, bestand):
    g = site.get("/api/en/netwerk").json()
    for k in g["knopen"]:
        assert k["r"] <= k["x"] <= g["breed"] - k["r"] and k["r"] <= k["y"] <= g["hoog"] - k["r"], k
    for a, b in itertools.combinations(g["knopen"], 2):
        assert ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** .5 >= a["r"] + b["r"] - 0.5, (a["id"], b["id"])
    plek = {k["id"]: (k["x"], k["y"], k["r"]) for k in g["knopen"]}
    for taal in TALEN:
        assert {k["id"]: (k["x"], k["y"], k["r"]) for k in site.get(f"/api/{taal}/netwerk").json()["knopen"]} == plek, taal
    opnieuw = TestClient(fa.maak_app(bestand)).get("/api/en/netwerk").json()
    assert {k["id"]: (k["x"], k["y"], k["r"]) for k in opnieuw["knopen"]} == plek
    # meer factchecks, een grotere cirkel
    assert plek[Z][2] > plek[WHO_Q][2]


def test_choosing_a_name_lights_it_up_with_its_neighbours_and_links_to_its_page_and_list(site):
    g = site.get(f"/api/nl/netwerk?naam={WHO_Q}").json()
    k = g["gekozen"]
    assert k["id"] == WHO_Q and k["naam"] == "Wereldgezondheidsorganisatie" and k["soort_naam"] == "Organisatie"
    assert k["pagina"] == f"/nl/names/{WHO_Q}/" and k["lijst"] == f"/nl/fact-checks/?naam={WHO_Q}"
    assert site.get(f"/api/nl/archief?naam={WHO_Q}").json()["totaal"] == 2 and "2" in k["aantal_tekst"]
    assert k["thema"] == {"sleutel": "health", "naam": "Gezondheid"}
    # de buren: wie het vaakst samen voorkomt eerst
    assert [(b["id"], b["samen"]) for b in k["buren"]] == [(VIJAND, 2), (FLORIDA, 1)]
    assert k["buren"][0]["href"] == f"/nl/explore/network/?naam={VIJAND}"
    licht = {x["id"]: (x["aan"], x["buur"]) for x in g["knopen"]}
    assert licht == {WHO_Q: (True, False), VIJAND: (False, True), FLORIDA: (False, True), Z: (False, False)}
    assert {frozenset((r["a"], r["b"])) for r in g["randen"] if r["aan"]} == {frozenset((WHO_Q, VIJAND)),
                                                                               frozenset((WHO_Q, FLORIDA))}
    assert [n["id"] for n in g["namen"] if n["aan"]] == [WHO_Q]


@pytest.mark.parametrize("taal", TALEN)
def test_every_language_has_its_words_and_addresses(site, taal):
    g = site.get(f"/api/{taal}/netwerk?naam={Z}").json()
    voor = "" if taal == "en" else f"/{taal}"
    assert g["alles_href"] == f"{voor}/explore/network/" and g["verkennen_href"] == f"{voor}/explore/"
    assert g["gekozen"]["naam"] == ZELENSKY[taal] and g["gekozen"]["buren_kop"] and g["tekst"]["zoek"]
    assert all(k["href"].startswith(f"{voor}/explore/network/?naam=Q") for k in g["knopen"])


@pytest.mark.parametrize("adres", [f"/api/nl/netwerk?naam={ALESUND}", "/api/nl/netwerk?naam=Q1", "/api/nl/netwerk?naam=",
                                   "/api/nl/netwerk?naam=x", f"/api/nl/netwerk?naam={Z}&naam={WHO_Q}",
                                   "/api/nl/netwerk?thema=war"])
def test_an_address_that_is_not_one_view_does_not_exist(site, adres):
    assert site.get(adres).status_code == 404


def test_explore_points_to_the_network_only_when_the_release_has_names(site, tmp_path_factory):
    assert site.get("/api/nl/verkennen").json()["netwerk"]["href"] == "/nl/explore/network/"
    zonder = TestClient(fa.maak_app(_maak(tmp_path_factory, met_namen=False)), follow_redirects=False)
    assert zonder.get("/api/nl/netwerk").status_code == 404
    assert zonder.get("/api/nl/verkennen").json()["netwerk"] is None


# --- de schikking zelf -----------------------------------------------------------------------------------------------

def _dozen(plek, stralen, labels):
    """De ruimte die een cirkel met zijn label inneemt: het label staat eronder (zoals de site het tekent)."""
    uit = []
    for (x, y), r, w in zip(plek, stralen, labels):
        half = max(r, w / 2)
        uit.append((x - half, x + half, y - r, y + r + (netwerk.LABEL_HOOG if w else 0)))
    return uit


@pytest.mark.parametrize("zaad", [1, 2, 3])
def test_a_dense_network_gets_a_layout_without_any_overlap_inside_its_canvas(zaad):
    rnd = random.Random(zaad)
    n = 70
    stralen = [4 + rnd.random() * 22 for _ in range(n)]
    labels = [rnd.choice([0, 0, 40 + rnd.random() * 90]) for _ in range(n)]
    randen = [(i, j, rnd.randint(25, 1800)) for i, j in itertools.combinations(range(n), 2) if rnd.random() < .09]
    s = netwerk.schik(stralen, randen, labels)
    dozen = _dozen(s["plek"], stralen, labels)
    for x0, x1, y0, y1 in dozen:
        assert x0 >= -0.01 and y0 >= -0.01 and x1 <= s["breed"] + 0.01 and y1 <= s["hoog"] + 0.01
    for a, b in itertools.combinations(dozen, 2):
        assert min(a[1], b[1]) - max(a[0], b[0]) <= 0.5 or min(a[3], b[3]) - max(a[2], b[2]) <= 0.5, (a, b)
    assert netwerk.schik(stralen, randen, labels)["plek"] == s["plek"]


def test_a_network_of_none_or_one_name_still_has_a_canvas():
    assert netwerk.schik([], [], [])["plek"] == []
    een = netwerk.schik([10], [], [50])
    (x, y), = een["plek"]
    assert 0 < x < een["breed"] and 0 < y < een["hoog"]
