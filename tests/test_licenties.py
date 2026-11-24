"""Wat deze repo uitdeelt, en onder welke voorwaarden (PLAN.md #15.2, B13).

B13 splitst het werk in drie stukken met ongelijke bescherming: de specificatie
vrij, de code copyleft, het merk op conformantie. Die driedeling is alleen echt
als de bestanden er staan én als alles wat we meesturen ook meegestuurd mág
worden. Het corpus is CC BY, en CC BY is niet gratis: naamsvermelding,
licentievermelding en het melden van bewerkingen zijn voorwaarden. Een fixture
die corpustekst herdistribueert zonder die drie is een licentieschending, hoe
klein hij ook is.
"""

import json
import pathlib
import subprocess

WORTEL = pathlib.Path(__file__).resolve().parent.parent


def _getrackt(patroon: str) -> list[pathlib.Path]:
    uit = subprocess.run(
        ["git", "ls-files", patroon],
        cwd=WORTEL,
        capture_output=True,
        text=True,
        check=True,
    )
    return [WORTEL / regel for regel in uit.stdout.split("\n") if regel]


def test_the_three_pieces_each_have_their_licence_file():
    ontbreekt = [
        naam
        for naam in ("LICENSE", "LICENSE-PROTOCOL.md", "TRADEMARK.md", "README.md")
        if not (WORTEL / naam).exists()
    ]
    assert ontbreekt == [], f"B13-driedeling mist bestand(en): {ontbreekt}"


def test_the_readme_says_which_piece_falls_under_what():
    tekst = (WORTEL / "README.md").read_text(encoding="utf-8")
    for verwacht in ("AGPL-3.0", "CC BY 4.0", "LICENSE-PROTOCOL.md", "TRADEMARK.md"):
        assert verwacht in tekst, f"README noemt {verwacht} niet"


def test_the_code_licence_is_the_real_agpl_including_its_network_clause():
    """Section 13 is het enige verschil met GPL, en de hele reden voor B13."""
    tekst = (WORTEL / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in tekst
    assert "Version 3, 19 November 2007" in tekst
    assert "13. Remote Network Interaction" in tekst, (
        "zonder de netwerkclausule is dit GPL en dekt het een gehoste resolver niet"
    )


def test_the_specification_licence_states_that_implementing_is_unrestricted():
    """B13(a): implementeren is onbeperkt. Zonder die zin blijft de vraag hangen
    of een implementatie een afgeleid werk van de spec is."""
    tekst = (WORTEL / "LICENSE-PROTOCOL.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in tekst
    assert "onbeperkt" in tekst.lower()
    assert "creativecommons.org/licenses/by/4.0" in tekst


# JSON dat geen data is maar gereedschapsconfiguratie: geen herkomstregel
# nodig, wél een opgeschreven reden — anders groeit dit stilletjes tot een
# achterdeur in de guard.
GEEN_DATA = {
    ".claude/launch.json": "startconfiguratie voor de ontwikkelomgeving;"
                           " schema is van de editor, bevat geen corpusdata",
    "site/package.json": "het npm-manifest van de site in Astro (B76, #34.2f); afhankelijkheden, geen data",
    "site/package-lock.json": "de vastgezette versies van die afhankelijkheden; door npm geschreven, geen data",
}


def test_every_redistributed_data_file_declares_where_it_came_from():
    """Een JSON-fixture zonder herkomstregel is niet te beoordelen op licentie."""
    zonder = []
    for pad in _getrackt("*.json"):
        relatief = pad.relative_to(WORTEL).as_posix()
        if relatief in GEEN_DATA:
            continue
        inhoud = json.loads(pad.read_text(encoding="utf-8"))
        if isinstance(inhoud, dict) and "_meta" in inhoud:
            continue
        if isinstance(inhoud, dict) and "toelichting" in inhoud:
            continue
        zonder.append(relatief)
    assert zonder == [], f"datafixture(s) zonder herkomstregel: {zonder}"


def test_nothing_is_exempt_from_the_data_guard_without_a_reason():
    leeg = [pad for pad, reden in GEEN_DATA.items() if not reden.strip()]
    assert leeg == []
    bestaat = {p.relative_to(WORTEL).as_posix() for p in _getrackt("*.json")}
    weg = sorted(set(GEEN_DATA) - bestaat)
    assert weg == [], f"uitzondering voor bestand dat niet (meer) bestaat: {weg}"


def test_redistributed_corpus_text_carries_its_attribution():
    """CC BY vereist naamsvermelding, licentie én het melden van bewerkingen.

    De bronkant van de vertaalfixture is letterlijke corpustekst; de doelkant
    is een bewerking daarvan. Beide voorwaarden gelden dus.
    """
    fixture = json.loads(
        (WORTEL / "doublecheck" / "vertalingen.json").read_text(encoding="utf-8")
    )
    meta = fixture["_meta"]
    assert "CC BY" in meta, "herkomstregel noemt de licentie van het bronmateriaal niet"
    assert "vertaal" in meta.lower() or "bewerk" in meta.lower(), (
        "CC BY eist dat een bewerking als bewerking herkenbaar is"
    )
    zonder = [
        paar["claim_id"]
        for paar in fixture["paren"]
        if not paar.get("publisher") or not paar.get("url")
    ]
    assert zonder == [], (
        f"{len(zonder)} vertaalparen herdistribueren CC BY-tekst zonder "
        f"naamsvermelding: {zonder[:5]}"
    )
