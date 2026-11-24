"""Een label voor staatsmedia (PLAN #32.11): een label bij de bron, geen oordeel."""

from doublecheck import staatsmedia as sm

RSF = {"CHN": 22.0, "AUS": 75.0, "IRN": 21.0}


def _rij(naam, site, iso3):
    return {"itemLabel": {"value": naam}, "site": {"value": site}, "iso3": {"value": iso3}}


def test_government_owned_media_count_only_in_countries_without_press_freedom():
    lijst = sm.bouw([_rij("Shenzhen Press Group", "http://www.sznews.com/", "CHN"),
                     _rij("ABC Radio National", "https://www.abc.net.au/rn", "AUS"),
                     _rij("Zonder land", "https://onbekend.example/", "")], RSF, "2026-10-29")
    assert "sznews.com" in lijst["domeinen"] and "abc.net.au" not in lijst["domeinen"]
    assert "onbekend.example" not in lijst["domeinen"]  # twijfel versoepelt nooit, maar een label zonder land is geen bewijs
    assert lijst["domeinen"]["sznews.com"]["bron"].startswith("Wikidata")


def test_the_official_and_reviewed_lists_are_always_in_with_their_source():
    lijst = sm.bouw([], RSF, "2026-10-29")
    assert lijst["domeinen"]["rt.com"]["bron"].startswith("EU")
    assert lijst["domeinen"]["globaltimes.cn"]["bron"].startswith("VS")
    assert lijst["domeinen"]["presstv.ir"]["bron"].startswith("Claude") and lijst["domeinen"]["presstv.ir"]["reden"]


def test_a_subdomain_carries_the_label_of_its_site_and_nothing_else_does():
    lijst = sm.bouw([], RSF, "2026-10-29")
    assert sm.label("https://actualidad.rt.com/x", lijst)["naam"].startswith("RT")
    assert sm.label("https://www.presstv.ir/Detail/1", lijst) is not None
    assert sm.label("https://www.art.com/x", lijst) is None  # geen achtervoegsel zonder punt
    assert sm.label("https://www.bbc.com/news", lijst) is None
