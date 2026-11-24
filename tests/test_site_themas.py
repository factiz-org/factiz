"""Een pagina per thema in de nieuwe site (PLAN #34.2u, DESIGN §4w): het overzicht en de pagina van een thema of
onderdeel, met de gegevens van het platform; navigatie wijst naar de pagina, de knoppen in de lijst blijven filters."""

from pathlib import Path

import pytest

from tests.test_factiz_dossiers import TALEN, _site

SITE = Path(__file__).resolve().parent.parent / "site" / "src"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.mark.parametrize("taal", TALEN)
def test_the_overview_as_data_gives_every_theme_with_its_count_and_its_parts(site, taal):
    client, _ = site
    g = client.get(f"/api/{taal}/themas").json()
    assert g["titel"] and g["inleiding"]
    voor = "" if taal == "en" else f"/{taal}"
    sleutels = [th["sleutel"] for th in g["themas"]]
    assert "war" in sleutels and "health" in sleutels and "migration" not in sleutels   # een thema zonder pagina niet
    oorlog = next(th for th in g["themas"] if th["sleutel"] == "war")
    assert oorlog["href"] == f"{voor}/themes/war/" and oorlog["aantal"]
    assert [(o["sleutel"], o["href"]) for o in oorlog["onderdelen"]] == [("ukraine", f"{voor}/themes/war/ukraine/")]
    assert oorlog["onderdelen"][0]["aantal"]


def test_a_theme_as_data_gives_its_parts_dossiers_newest_fact_checks_and_the_list_with_the_filter(site):
    client, nr = site
    g = client.get("/api/nl/thema/war").json()
    assert g["kop"] == "Oorlog en conflict" and g["deel"] is None and g["thema_naam"] == "Oorlog en conflict"
    assert g["alle"] == "/nl/fact-checks/?thema=war" and g["alle_tekst"] and g["aantal"]
    assert [o["sleutel"] for o in g["onderdelen"]] == ["ukraine"]
    assert [d["sleutel"] for d in g["dossiers"]] == ["zelensky-luxury"]
    assert {"naam", "soort_tekst", "aantal", "href"} <= set(g["dossiers"][0])         # dezelfde kaart als op de start
    assert f"/nl/fact-checks/{nr['villa']}/" in [r["href"] for r in g["rijen"]]


def test_a_part_as_data_names_itself_under_its_theme_and_filters_on_both(site):
    client, _ = site
    g = client.get("/api/nl/thema/war/ukraine").json()
    assert g["kop"] == "Rusland en Oekraïne" and g["deel"] == {"sleutel": "ukraine", "naam": "Rusland en Oekraïne"}
    assert g["thema_href"] == "/nl/themes/war/" and g["onderdelen"] == []
    assert g["alle"] == "/nl/fact-checks/?onderdeel=ukraine&thema=war"


@pytest.mark.parametrize("pad", ["/api/nl/thema/sport", "/api/nl/thema/health/ukraine", "/api/nl/thema/war/onbekend",
                                 "/api/nl/thema/migration", "/api/nl/thema/War", "/api/nl/thema/%3Cx%3E"])
def test_a_theme_or_part_that_does_not_exist_is_not_found_as_data(site, pad):
    client, _ = site
    assert client.get(pad).status_code == 404


def test_the_site_has_the_theme_pages_and_navigation_points_to_them_while_the_list_keeps_its_filters():
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'themes'" in router and "/api/${taal}/themas" in router and "/api/${taal}/thema/" in router
    for bestand, plek in (("components/site/Menu.jsx", "het menu"), ("components/site/paginas/Start.astro", "de start"),
                          ("layouts/Site.astro", "de voet"), ("components/site/paginas/Dossier.astro", "een dossier"),
                          ("lib/talen.js", "naarSite")):
        tekst = (SITE / bestand).read_text(encoding="utf-8")
        assert "?thema=" not in tekst, plek
    factcheck = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    kruimel = factcheck[factcheck.index("<Kruimel"):factcheck.index("/>", factcheck.index("<Kruimel"))]
    assert "pad(taal, 'themes', p.thema.sleutel)" in kruimel and "?thema=" not in kruimel
    lijst = (SITE / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    assert "?thema=" in lijst                                                   # in de lijst blijft het een filter
    thema = (SITE / "components" / "site" / "paginas" / "Thema.astro").read_text(encoding="utf-8")
    assert "<DossierKaart" in thema and "<Bibliotheek client:load" in thema and "vast={vast}" in thema
    assert "g.onderdelen.map(" in thema and "start_nieuwste" not in thema and "g.alle_tekst" not in thema   # E9.S27 AC6
    assert "veld-band-thema-${g.sleutel}" in thema                               # bovenaan de band van het thema, met de kop erop
    themas = (SITE / "components" / "site" / "paginas" / "Themas.astro").read_text(encoding="utf-8")
    assert "g.themas.map(" in themas and "th.onderdelen.map(" in themas


def test_the_list_on_a_theme_keeps_the_theme_in_every_question_and_never_in_the_address():
    """PLAN #34.2bb, SPECS E9.S27 AC2 en AC3: het vaste deel gaat mee in elke vraag aan het platform, staat niet in het
    adres en is geen stukje of filter; de lijst van Factchecks zelf heeft geen vast deel."""
    archief = (SITE / "lib" / "archief.jsx").read_text(encoding="utf-8")
    assert "vast = []" in archief
    vragen = [r for r in archief.splitlines() if "fetch(`/${taal}/api/" in r]
    assert len(vragen) >= 5 and all("metVast(" in r for r in vragen), vragen
    assert "const adresMet = (schoon) => `${basis}${eigen(schoon).length" in archief
    bieb = (SITE / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    assert "vast = []" in bieb and "!vastSoorten.has('thema') &&" in bieb
    assert "f.stukjes.filter((s) => !vastSoorten.has(s.soort))" in bieb
    assert "vastSoorten.has('thema') && !vastSoorten.has('onderdeel') && <Vinkjes soort=\"onderdeel\"" in bieb   # AC2
    lijst = (SITE / "components" / "site" / "paginas" / "Lijst.astro").read_text(encoding="utf-8")
    assert "vast=" not in lijst


def test_the_theme_cards_on_the_start_and_the_overview_use_the_small_band():
    """PLAN #34.2bq: een kaart van een paar honderd pixels krijgt de band van 800×240 (~12 KB), niet die van 2000×600."""
    from pathlib import Path
    paginas = Path(__file__).resolve().parent.parent / "site" / "src" / "components" / "site" / "paginas"
    for naam in ("Start.astro", "Themas.astro"):
        tekst = (paginas / naam).read_text(encoding="utf-8")
        assert "veld-klein-thema-" in tekst and "veld-band-thema-" not in tekst, naam


def test_the_quick_themes_above_the_list_only_show_where_the_filter_column_is_hidden():
    """PO 2026-11-16, "deze kan wel weg volgens mij, staat al links": breed staan de thema's in de filterkolom, dus de rij
    erboven alleen op een telefoon, waar de filterkolom in een lade zit (dezelfde grens, `md`)."""
    import re
    tekst = (SITE / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    rij = re.search(r'<div className="([^"]*)"[^>]*data-rij="themas"', tekst)
    kolom = re.search(r'<aside[^>]*className="filterkolom ([^"]*)"', tekst)
    assert rij and "md:hidden" in rij.group(1).split()
    assert kolom and "max-md:hidden" in kolom.group(1).split()


def test_the_start_shows_ten_themes_five_in_a_row_then_the_latest_fact_checks_then_the_dossiers():
    """PO 2026-11-23: "Fact-checks moet omhoog. Ik denk dat je even een korte selectie moet zien van thema's. Misschien kunnen
    we er vijf op een rij doen en er tien tonen, bijvoorbeeld, en daaronder gelijk de laatste fact-checks en daaronder de
    dossiers." De eerste tien in de vaste volgorde van `content/themas.json`; de rest staat onder Alle thema's."""
    from pathlib import Path
    start = (Path(__file__).resolve().parent.parent / "site" / "src" / "components" / "site" / "paginas" / "Start.astro"
             ).read_text(encoding="utf-8")
    assert "themas.slice(0, 10).map(" in start and "lg:grid-cols-5" in start
    assert start.index('aria-labelledby="themas"') < start.index('aria-labelledby="nieuwste"') < start.index('aria-labelledby="dossiers"')


def test_each_see_all_link_on_the_start_says_how_many_there_are_and_is_easy_to_tap():
    """PO 2026-11-23, bij "All themes" en "All dossiers": "Hier dan ook een cijfer." Een getal zegt dat er meer is dan de
    tien thema's, vier dossiers en zes factchecks op de start; op een aanraakscherm is de link 44 px hoog."""
    import json
    import re
    from pathlib import Path
    wortel = Path(__file__).resolve().parent.parent
    start = (wortel / "site" / "src" / "components" / "site" / "paginas" / "Start.astro").read_text(encoding="utf-8")
    for sleutel in ("start_alle_themas", "start_alle_dossiers", "start_alle_factchecks"):
        assert f"t('{sleutel}'" in start, sleutel
        for taal in ("en", "nl", "de", "es", "fr"):
            assert "{n}" in json.loads((wortel / "factiz_site" / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))["teksten"][sleutel]
    assert "g.dossiers_aantal" in start
    css = (wortel / "site" / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(pointer: coarse\) \{ \.fz \.sectiekop > a \{[^}]*min-height: 2\.75rem", css)
