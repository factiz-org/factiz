"""Wat buiten Factiz gelezen wordt, is Engels (PO 2026-10-13).

De code en de documenten zijn Nederlands; de site, de cijferpagina, de
foutmeldingen van de API en de uitvoer van de conformantiesuite niet. Een
foutmelding komt via de demo bij een gebruiker ("Server: ..."), dus een
Nederlandse melding is een Nederlandse zin op een Engelse site.
"""

import pathlib
import re

WORTEL = pathlib.Path(__file__).resolve().parent.parent
NEDERLANDS = re.compile(r"\b(geen|niet|onleesbare?|afbeelding|verzoek(en)?|betwisting\w*|artefact|"
                        r"probeer|opnieuw|klopt|tekens|groter|lege?|bevat|verwacht)\b", re.IGNORECASE)


def _meldingen(pad: str) -> list[str]:
    bron = (WORTEL / pad).read_text(encoding="utf-8")
    return re.findall(r'detail\s*=\s*f?"([^"]*)"|"detail":\s*f?"([^"]*)"', bron)


def test_api_error_messages_are_english():
    for pad in ("doublecheck/api.py", "doublecheck/ratelimit.py"):
        for paar in _meldingen(pad):
            tekst = "".join(paar)
            assert not NEDERLANDS.search(tekst), f"{pad}: {tekst}"


def test_the_resolver_names_itself_in_english():
    config = (WORTEL / "config.toml").read_text(encoding="utf-8")
    naam = re.search(r'^name\s*=\s*"([^"]*)"', config, flags=re.M).group(1)
    assert naam.startswith("Factiz") and not NEDERLANDS.search(naam), naam
