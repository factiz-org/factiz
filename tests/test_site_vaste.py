"""Redacties, Over en Bronnen in de nieuwe site (PLAN #34.2t): dezelfde gegevens en teksten als op het platform."""

from pathlib import Path

import pytest

from factiz_site import app as fa
from tests.test_factiz_dossiers import TALEN, _site

SITE = Path(__file__).resolve().parent.parent / "site" / "src"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.mark.parametrize("taal", TALEN)
def test_the_newsrooms_as_data_name_every_newsroom_with_its_count_and_its_list(site, taal):
    client, _ = site
    g = client.get(f"/api/{taal}/redacties").json()
    assert g["titel"] and g["inleiding"]
    namen = [r["naam"] for r in g["redacties"]]
    assert "Snopes" in namen and "EUvsDisinfo" in namen and len(namen) == len(set(namen))
    snopes = next(r for r in g["redacties"] if r["naam"] == "Snopes")
    voor = "" if taal == "en" else f"/{taal}"
    assert snopes["href"] == f"{voor}/fact-checks/?redactie=Snopes" and snopes["aantal"]
    # elke redactie met het aantal factchecks dat zij natrok, de meeste eerst
    assert [(r["naam"], r["aantal"]) for r in g["redacties"]] == [("Snopes", "4"), ("AFP", "1"), ("EUvsDisinfo", "1"),
                                                                  ("Maldita", "1")]


def test_the_sources_as_data_name_every_source_with_its_licence_credit_and_link(site):
    client, _ = site
    g = client.get("/api/nl/bronnen").json()
    assert g["titel"] == "Bronnen en licenties" and g["licentie_kop"] == "Licentie" and g["vermelding_kop"]
    namen = " ".join(b["naam"] for b in g["bronnen"])
    assert "Data Commons" in namen and "EUvsDisinfo" in namen
    assert any("CC BY 4.0" in b["licentie"] for b in g["bronnen"])
    assert any("EUvsDisinfo, European External Action Service" in b["naamsvermelding"] for b in g["bronnen"])
    assert all(b["url"] is None or b["url"].startswith("https://") for b in g["bronnen"])


def test_the_site_has_the_three_pages_and_the_footer_points_to_them():
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'newsrooms'" in router and "soort === 'about'" in router and "soort === 'sources'" in router
    assert "/api/${taal}/redacties" in router and "/api/${taal}/bronnen" in router
    kop = (SITE / "layouts" / "Site.astro").read_text(encoding="utf-8")
    for naam, pad in (("over", "about"), ("bronnen", "sources"), ("redacties", "newsrooms")):
        assert f"{naam}: pad(taal, '{pad}')" in kop and f"naarPlatform(taal, '{pad}/')" not in kop
    over = (SITE / "components" / "site" / "paginas" / "Over.astro").read_text(encoding="utf-8")
    for sleutel in ("over_wat_kop", "over_wat_p1", "over_wat_p2", "over_fout_kop", "over_fout_p1", "over_fout_adres",
                    "over_privacy_kop", "over_privacy_p1", "over_privacy_weergave", "over_privacy_herkomst"):
        # B88: de eerste privacyzin heeft een vorm voor als er gemeten kan worden (`over_privacy_p1_meten`)
        assert f"t('{sleutel}')" in over or f"'{sleutel}')" in over, sleutel
    assert 'id="corrections"' in over and 'id="privacy"' in over and "{CONTACT}" in over
    assert "mailto:" not in over                                              # het adres als tekst (B75, zoals nu)
    redacties = (SITE / "components" / "site" / "paginas" / "Redacties.astro").read_text(encoding="utf-8")
    assert "g.redacties.map(" in redacties and "<bdi>" in redacties             # een naam in elk schrift
    bronnen = (SITE / "components" / "site" / "paginas" / "Bronnen.astro").read_text(encoding="utf-8")
    assert "g.bronnen.map(" in bronnen and "b.naamsvermelding" in bronnen and "b.licentie" in bronnen


def test_the_contact_address_of_the_site_is_the_one_of_the_platform():
    platform = (SITE / "lib" / "platform.js").read_text(encoding="utf-8")
    assert f"export const CONTACT = '{fa.CONTACT}';" in platform


def test_the_platform_page_is_the_fixed_text_and_the_site_no_longer_links_to_the_old_platform():
    """PLAN #34.2t, Platform ook: de vier delen met hun stand en ankers, uit de woordenlijsten; nergens nog een link naar
    het oude platform."""
    pagina = (SITE / "components" / "site" / "paginas" / "Platform.astro").read_text(encoding="utf-8")
    for anker in ("products", "developers", "how-it-works", "documentation"):
        assert f'id="{anker}"' in pagina, anker
    for sleutel in ("platform_kop", "platform_inleiding", "platform_producten", "platform_producten_stand",
                    "platform_producten_p1", "platform_producten_p2", "platform_ontwikkelaars_stand",
                    "platform_ontwikkelaars_p1", "platform_ontwikkelaars_p2", "platform_motorkap_stand",
                    "platform_documentatie_stand", "platform_documentatie_p1"):
        assert f"t('{sleutel}')" in pagina, sleutel
    assert "t(`platform_motorkap_stap${i}`)" in pagina and "[1, 2, 3, 4, 5, 6]" in pagina
    assert "pad(taal, 'fact-checks')" in pagina and "pad(taal, 'sources')" in pagina
    router = (SITE / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'platform'" in router
    for bestand in SITE.rglob("*"):
        if bestand.suffix in (".astro", ".jsx", ".js"):
            tekst = bestand.read_text(encoding="utf-8")
            assert "naarPlatform" not in tekst and "127.0.0.1:8799/" not in tekst, bestand.name
