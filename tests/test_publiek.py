"""De publieke oppervlakte van de repo (PLAN #23.1, B20).

Vóór de repo publiek gaat is dit de poort: de vier stukken dragen elk hun
licentie, de Engelse README is de voordeur, en er lekt geen privébestand
mee. Deze tests draaien op de werkkopie zodat een vergeten bestand de
suite breekt en niet pas de launch.
"""

import pathlib
import subprocess

WORTEL = pathlib.Path(__file__).resolve().parent.parent


def test_four_pieces_each_carry_their_licence():
    """B13 + B20: specificatie CC BY, toets MIT, implementatie AGPL,
    merk op de toetsvoorwaarde — en beide README's vertellen het."""
    agpl = (WORTEL / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in agpl

    mit = (WORTEL / "conformance" / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in mit
    assert "Permission is hereby granted" in mit

    proto = (WORTEL / "LICENSE-PROTOCOL.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in proto

    for naam in ("README.md", "README.nl.md"):
        tekst = (WORTEL / naam).read_text(encoding="utf-8")
        for stuk in ("AGPL", "MIT", "CC BY", "TRADEMARK.md"):
            assert stuk in tekst, (naam, stuk)


def test_the_english_readme_is_the_front_door():
    """#22.7: de launch is Engelstalig, dus de voordeur ook. De NL-versie
    blijft bestaan en beide wijzen naar elkaar."""
    tekst = (WORTEL / "README.md").read_text(encoding="utf-8")
    assert tekst.startswith("# Factiz")
    assert "resolver layer" in tekst
    assert "README.nl.md" in tekst
    # De kernbeloftes staan op de voordeur zelf.
    laag = tekst.lower()
    assert "truth percentage" in laag or "never" in laag
    assert "fingerprint" in laag
    # Launch-copy-discipline (VOICE): geen em-dash in de Engelse voordeur.
    assert "—" not in tekst

    nl = (WORTEL / "README.nl.md").read_text(encoding="utf-8")
    assert "README.md" in nl
    assert "MIT" in nl


def test_security_reporting_and_contributing_exist():
    beveiliging = (WORTEL / "SECURITY.md").read_text(encoding="utf-8")
    assert "security@factiz.org" in beveiliging

    bijdragen = (WORTEL / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "pytest" in bijdragen
    assert "PLAN.md" in bijdragen
    # De eerlijkheidsregels die een PR nooit mag breken staan erin.
    assert "truth" in bijdragen.lower()
    assert "config" in bijdragen.lower()


def test_env_example_exists_and_carries_no_value():
    """De sleutel heeft een voorbeeldbestand, nooit een voorbeeldwaarde."""
    tekst = (WORTEL / ".env.example").read_text(encoding="utf-8")
    assert "GOOGLE_FACTCHECK_API_KEY=" in tekst
    for regel in tekst.splitlines():
        regel = regel.strip()
        if regel and not regel.startswith("#"):
            _, _, waarde = regel.partition("=")
            assert waarde == "", regel


def test_no_private_file_is_tracked_by_git():
    """DR3-verlengstuk voor de repo zelf: geen .env, geen database."""
    uitvoer = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=WORTEL,
        check=True,
    ).stdout.splitlines()
    assert ".env" not in uitvoer
    assert not [pad for pad in uitvoer if pad.endswith(".db")]
    assert ".env.example" in uitvoer

    gitignore = (WORTEL / ".gitignore").read_text(encoding="utf-8")
    for patroon in (".env", "*.db", "data/"):
        assert patroon in gitignore, patroon


def test_contributors_find_conduct_templates_and_a_way_into_the_documents():
    """PLAN #34.2bl, stap 4: wie mee wil doen, vindt een gedragscode, sjablonen voor issues en pull requests, losse
    taken en een Engelse ingang tot de Nederlandse documenten."""
    gedrag = (WORTEL / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "Contributor Covenant" in gedrag
    assert "@factiz.org" in gedrag

    sjablonen = WORTEL / ".github" / "ISSUE_TEMPLATE"
    assert len(list(sjablonen.glob("*.yml"))) >= 4
    assert (WORTEL / ".github" / "pull_request_template.md").exists()

    taken = (WORTEL / "docs" / "GOOD-FIRST-ISSUES.md").read_text(encoding="utf-8")
    assert "PLAN #" in taken

    ingang = (WORTEL / "docs" / "README.md").read_text(encoding="utf-8")
    for woord in ("bewering", "oordeel", "uitgave", "PROTOCOL.md"):
        assert woord in ingang, woord

    for naam in ("README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "docs/README.md",
                 "docs/GOOD-FIRST-ISSUES.md"):
        assert "—" not in (WORTEL / naam).read_text(encoding="utf-8"), naam


def test_commits_carry_no_claude_co_author_line_from_now_on():
    """PO 2026-11-24: Claude gaat eruit als co-auteur. De werkafspraak zegt het, zodat elke sessie het volgt."""
    afspraak = (WORTEL / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Geen regel `Co-Authored-By: Claude" in afspraak
