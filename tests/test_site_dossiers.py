"""Het overzicht van de dossiers in de nieuwe site (PLAN #34.2s, SPECS E9.S7, DESIGN §4w): elk dossier van de uitgave
als dezelfde kaart als op de start, de nieuwste aanvulling boven, met de gegevens van het platform."""

from pathlib import Path

import pytest

from tests.test_factiz_dossiers import NAAM, TALEN, _site

SITE = Path(__file__).resolve().parent.parent / "site" / "src"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.mark.parametrize("taal", TALEN)
def test_the_overview_as_data_gives_every_published_dossier_with_its_card_in_the_language_of_the_site(site, taal):
    client, _ = site
    g = client.get(f"/api/{taal}/dossiers").json()
    assert g["inleiding"] and g["titel"]
    sleutels = [d["sleutel"] for d in g["dossiers"]]
    assert sorted(sleutels) == ["doppelganger", "zelensky-luxury"]             # een concept staat in geen uitgave
    d = next(x for x in g["dossiers"] if x["sleutel"] == "zelensky-luxury")
    voor = "" if taal == "en" else f"/{taal}"
    assert d["naam"] == NAAM[taal] and d["href"] == f"{voor}/dossiers/zelensky-luxury/"
    assert d["soort"] == "verhaal" and d["soort_tekst"] and d["inleiding"] and d["aantal"] and d["laatste"]
    assert d["concept"] is False


def test_the_overview_puts_the_newest_addition_on_top_and_uses_the_same_cards_as_the_start(site):
    client, _ = site
    alles = client.get("/api/nl/dossiers").json()["dossiers"]
    start = client.get("/api/nl/archief").json()["dossiers"]
    assert [d["sleutel"] for d in start] == [d["sleutel"] for d in alles][:4]
    for s in start:                                                            # dezelfde kaart, dezelfde velden
        a = next(d for d in alles if d["sleutel"] == s["sleutel"])
        assert {k: a[k] for k in s} == s


def test_a_concept_preview_says_which_dossier_is_a_concept(tmp_path_factory):
    client, _ = _site(tmp_path_factory, concepten=True)
    g = client.get("/api/nl/dossiers").json()
    concept = next(d for d in g["dossiers"] if d["sleutel"] == "in-de-maak")
    assert concept["concept"] is True and concept["concept_tekst"]


def test_without_dossiers_in_the_release_there_is_no_overview(tmp_path_factory):
    client, _ = _site(tmp_path_factory, met_dossiers=False)
    assert client.get("/api/nl/dossiers").status_code == 404


def test_the_site_has_the_overview_and_the_head_the_footer_and_the_start_point_to_it():
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'dossiers' && !sleutel" in router and "/api/${taal}/dossiers`" in router
    kop = (SITE / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "dossier: pad(taal, 'dossiers')," in kop and "'zelensky-luxury'" not in kop
    overzicht = (SITE / "components" / "site" / "paginas" / "Dossiers.astro").read_text(encoding="utf-8")
    assert "<DossierKaart" in overzicht and "g.dossiers.map(" in overzicht
    start = (SITE / "components" / "site" / "paginas" / "Start.astro").read_text(encoding="utf-8")
    assert "<DossierKaart" in start and "pad(taal, 'dossiers')" in start      # dezelfde kaart, en Alle dossiers
    kaart = (SITE / "components" / "site" / "DossierKaart.astro").read_text(encoding="utf-8")
    assert 'aria-hidden="true"' in kaart and "kaartveld" in kaart             # het veld is leeg: nooit tekst erop
