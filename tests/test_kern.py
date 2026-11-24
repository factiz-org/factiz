"""De dienst leunt niet op meetcode (PLAN #32.7c): de controle en de API lenen alleen uit de kern; de metingen
lenen uit de kern, niet andersom. Elke vraag aan een model staat in een kernmodule, met dezelfde tekst als gemeten."""

import ast
from pathlib import Path

from doublecheck import feitstap, feitvraag, leraar, machinevraag, modellen, verificatie, vloer, vloervraag
from doublecheck import beweringvraag, zoekcontrole, zoekeerst, zoekherstel

DIENST = ("api", "berichtcontrole")
METINGEN = {"verificatie", "feitstap", "zoekherstel", "vloer", "leraar", "snelantwoord", "betatoets",
            "gebruikerstoets", "herkomst", "koppen", "modelpoort", "fundament", "herstel", "routemeting",
            "zoekeerst", "eindtoets", "beeldronde", "beeldbevestiging", "beeldcontrole", "databaselezer",
            "bronnendekking", "eigenscore", "tekstlezer"}


def _imports(module: str) -> set[str]:
    boom = ast.parse((Path("doublecheck") / f"{module}.py").read_text(encoding="utf-8"))
    uit = set()
    for n in ast.walk(boom):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("doublecheck"):
            uit |= {a.name for a in n.names} if n.module == "doublecheck" else {n.module.split(".")[1]}
    return uit


def test_the_service_never_borrows_from_a_measurement():
    for module in DIENST:
        assert not (_imports(module) & METINGEN), f"{module} leent uit {_imports(module) & METINGEN}"


def test_the_measurements_borrow_the_very_same_questions_from_the_core():
    assert verificatie.VRAGEN is machinevraag.VRAGEN and verificatie.verzoek is machinevraag.verzoek
    assert feitstap.VERSIES["v3"]["vraag_b"] is feitvraag.KERN["v3"]["vraag_b"] is feitvraag.VRAAG_V3B
    assert vloer.VRAGEN is vloervraag.VRAGEN and zoekherstel.EXTRACTIEVRAAG is beweringvraag.EXTRACTIEVRAAG
    assert leraar.MODELLEN is modellen.MODELLEN
    assert zoekeerst.VRAAG is zoekcontrole.LEZERS["lezer-v1"]["vraag"] and zoekeerst.leesverzoek is zoekcontrole.leesverzoek
    from doublecheck import databaselezer
    assert databaselezer.zc is zoekcontrole, "de lezer met de database komt uit de kern, zoals het product haar zou gebruiken"


def test_the_image_search_in_the_core_borrows_from_no_measurement():
    beeldmetingen = {"beeldindex", "beeldindexmeting", "kadermeting", "beeldstilte", "beeldtekstmeting", "beeldmotor",
                     "vindronde", "opmaakmeting"}
    assert not (_imports("beeldvraag") & (METINGEN | beeldmetingen))
    assert not (_imports("beschrijvingvraag") & (METINGEN | beeldmetingen))
    assert not (_imports("beeldrolvraag") & (METINGEN | beeldmetingen | {"vindronde", "beeldbevestiging"}))


def test_the_image_measurements_borrow_the_very_same_points_from_the_core():
    from doublecheck import beeldbevestiging, beeldindexmeting, beeldvraag, beschrijvingvraag

    assert beeldindexmeting.puntkenmerken is beeldvraag.puntkenmerken
    assert beeldindexmeting.puntvergelijking is beeldvraag.puntvergelijking
    assert beeldbevestiging.bs is beschrijvingvraag and beeldbevestiging.bv is beeldvraag
    from doublecheck import opmaakmeting
    assert opmaakmeting.bv is beeldvraag, "de opmaakregel komt uit de kern, zoals het product haar zou gebruiken"


def test_the_image_step_of_the_product_borrows_from_no_measurement_and_the_measurements_borrow_from_it():
    """#32.35: de beeldstap van `/check` staat in de kern; de meting van §201 leent er dezelfde kenmerken uit."""
    from doublecheck import beeldbevestiging, beeldstap

    beeldmetingen = {"beeldindex", "beeldindexmeting", "kadermeting", "beeldstilte", "beeldtekstmeting", "beeldmotor",
                     "vindronde", "opmaakmeting", "beeldoogst", "beeldindexbouw", "eigenaanvoer"}
    assert not (_imports("beeldstap") & (METINGEN | beeldmetingen))
    assert beeldbevestiging.artikelbeeld is beeldstap.beeldkenmerken
