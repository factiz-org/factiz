"""Namen in de nieuwe site (PLAN #34.2r, SPECS E9.S11, DESIGN §4u): het register en de pagina van een naam, met de
gegevens van het platform; een naam is een ingang, nooit een oordeel."""

from pathlib import Path

import pytest

from tests.test_factiz_namen import TALEN, WHO, ZELENSKY, _site

SITE = Path(__file__).resolve().parent.parent / "site" / "src"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


def test_the_register_as_data_gives_per_kind_the_letters_with_names_and_never_a_count(site):
    client, _ = site
    g = client.get("/api/nl/namen").json()
    assert [x["soort"] for x in g["groepen"]] == ["persoon", "organisatie", "plaats"]
    assert [x["kop"] for x in g["groepen"]] == ["Personen", "Organisaties", "Plaatsen"]
    plaats = next(x for x in g["groepen"] if x["soort"] == "plaats")
    assert [l["letter"] for l in plaats["letters"]] == ["a", "f"]
    assert plaats["letters"][0]["href"] == "/nl/names/?letter=a&soort=plaats"
    organisatie = next(x for x in g["groepen"] if x["soort"] == "organisatie")
    andere = next(l for l in organisatie["letters"] if l["letter"] == "0")
    assert andere["teken"] == "#" and andere["label"] == "Andere tekens"
    assert g["gekozen"] is None and g["namen"] == []
    assert "aantal" not in str(g) and "telling" not in str(g)              # een register, geen ranglijst


def test_a_letter_as_data_lists_its_names_with_their_page_in_the_language_of_the_site(site):
    client, _ = site
    g = client.get("/api/nl/namen?letter=a&soort=plaats").json()
    assert g["gekozen"] == {"soort": "plaats", "letter": "a", "teken": "A"}
    assert g["namen"] == [{"nummer": "Q62266", "naam": "Ålesund", "href": "/nl/names/Q62266/"}]
    de = client.get("/api/de/namen?letter=w&soort=persoon").json()
    assert [n["naam"] for n in de["namen"]] == [ZELENSKY["de"]]
    assert client.get("/api/en/namen?letter=w&soort=organisatie").json()["namen"][0]["naam"] == WHO["en"]


@pytest.mark.parametrize("vraag", ["?soort=plaats", "?letter=a", "?letter=zz&soort=plaats", "?letter=a&soort=dier",
                                   "?letter=A&soort=plaats", "?letter=a&soort=plaats&p=2", "?letter=b&soort=plaats"])
def test_a_register_question_that_does_not_exist_is_not_found_as_data_either(site, vraag):
    client, _ = site
    assert client.get("/api/nl/namen" + vraag).status_code == 404


@pytest.mark.parametrize("taal", TALEN)
def test_a_name_as_data_gives_its_kind_wikidata_the_newest_fact_checks_and_the_list_with_the_filter(site, taal):
    client, _ = site
    n = client.get(f"/api/{taal}/naam/Q3874799").json()
    assert n["nummer"] == "Q3874799" and n["naam"] == ZELENSKY[taal]
    assert n["wikidata"] == "https://www.wikidata.org/wiki/Q3874799"
    assert len(n["rijen"]) == 3 and all(r["href"].startswith(("/fact-checks/", f"/{taal}/fact-checks/")) for r in n["rijen"])
    voor = "" if taal == "en" else f"/{taal}"
    assert n["alle"] == f"{voor}/fact-checks/?naam=Q3874799"
    assert n["soort_tekst"] and n["zin"] and n["bedoeld"] and n["aantal"]


@pytest.mark.parametrize("nummer", ["Q999", "q812", "Q812x", "P31", "Q0", "%3Cscript%3E"])
def test_an_unknown_or_malformed_name_is_not_found_as_data(site, nummer):
    client, _ = site
    assert client.get(f"/api/nl/naam/{nummer}").status_code == 404


def test_without_names_in_the_release_there_is_no_register_and_no_name(tmp_path_factory):
    client, _ = _site(tmp_path_factory, met_namen=False)
    assert client.get("/api/nl/namen").status_code == 404
    assert client.get("/api/nl/naam/Q812").status_code == 404


def test_the_site_has_the_register_and_the_name_page_in_the_footer_not_in_the_head():
    """De pagina's in Astro lezen alleen de ingangen; de voet wijst naar het register, de kop niet: een naam vind je via
    zoeken, een factcheck of het filter (PO 2026-11-12: "names lijkt me helemaal geen eigen pagina waard in het menu")."""
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'names'" in router and "/api/${taal}/namen" in router and "/api/${taal}/naam/${sleutel}" in router
    kop = (SITE / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "namen: pad(taal, 'names')" in kop and "naarPlatform(taal, 'names/')" not in kop
    voet = kop[kop.index("<footer"):]
    assert "href={links.namen}" in voet                                       # het register staat in de voet
    menu = (SITE / "components" / "site" / "Menu.jsx").read_text(encoding="utf-8")
    assert "links.namen" not in menu                                          # en niet in de kop (PO 2026-11-12)
    register = (SITE / "components" / "site" / "paginas" / "Namen.astro").read_text(encoding="utf-8")
    assert "g.groepen.map(" in register and "l.teken" in register and "aantal" not in register
    naam = (SITE / "components" / "site" / "paginas" / "Naam.astro").read_text(encoding="utf-8")
    assert "n.zin" in naam and "n.wikidata" in naam and "<Rij r={r} />" in naam and "n.alle" in naam
    factcheck = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    assert "href={pad(taal, 'names', n.nummer)}" in factcheck                # de namen wijzen naar hun pagina
