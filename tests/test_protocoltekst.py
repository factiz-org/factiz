"""Het protocol in het Engels, normatief (PLAN #23.12, PO 2026-10-14).

Het protocol wil een standaard worden die andere resolvers implementeren, en
dat lukt niet in het Nederlands. De Engelse tekst is de normatieve, met
dezelfde paragraafnummers als de Nederlandse had: de conformantiesuite, de
code en de documenten verwijzen ernaar met §-nummers, en die moeten blijven
kloppen.
"""

import pathlib
import re

WORTEL = pathlib.Path(__file__).resolve().parent.parent
PROTOCOL = (WORTEL / "docs" / "PROTOCOL.md").read_text(encoding="utf-8")

# De paragrafen waar de verwijzingen op rusten; §2.1 tot en met §2.10 zijn de
# genummerde verplichtingen in §2.
PARAGRAFEN = {"1", "2", "2b", "3", "4", "5", "6", "7", "8", "9", "10", "11",
              *(f"11.{n}" for n in range(1, 8)), *(f"2.{n}" for n in range(1, 11))}
_VERWIJZING = re.compile(r"PROTOCOL(?:\.md)?`?\)?\s*§\s*(\d+[a-z]?(?:\.\d+)?)")


def _paragrafen(tekst: str) -> set[str]:
    nummers = set(re.findall(r"^#{2,3} (\d+[a-z]?(?:\.\d+)?)[. ]", tekst, re.M))
    verplichtingen = tekst.split("\n## 2. ", 1)[1].split("\n## ", 1)[0]
    nummers |= {f"2.{n}" for n in re.findall(r"^(\d+)\. \*\*MUST", verplichtingen, re.M)}
    return nummers


def _verwijzingen() -> set[tuple[str, str]]:
    gevonden = set()
    for pad in sorted((WORTEL / "conformance").glob("*.py")):
        # De suite verwijst alleen naar het protocol.
        for nummer in re.findall(r"§\s*(\d+[a-z]?(?:\.\d+)?)", pad.read_text(encoding="utf-8")):
            gevonden.add((pad.name, nummer.rstrip(".")))
    bestanden = [*(WORTEL / "doublecheck").glob("*.py"), *(WORTEL / "tests").glob("*.py"),
                 *(WORTEL / "docs").glob("*.md"), *WORTEL.glob("*.md")]
    for pad in bestanden:
        for nummer in _VERWIJZING.findall(pad.read_text(encoding="utf-8")):
            gevonden.add((pad.name, nummer))
    return gevonden


def test_the_numbered_sections_are_the_ones_every_reference_relies_on():
    assert _paragrafen(PROTOCOL) >= PARAGRAFEN


def test_every_reference_into_the_protocol_points_to_an_existing_section():
    bestaand = _paragrafen(PROTOCOL)
    verwijzingen = _verwijzingen()
    assert len(verwijzingen) >= 20, "de zoeker vindt de verwijzingen niet meer"
    los = sorted((bestand, nummer) for bestand, nummer in verwijzingen if nummer not in bestaand)
    assert los == []


def test_the_english_text_is_the_normative_one():
    kop = PROTOCOL.split("\n## ", 1)[0]
    assert kop.startswith("# Resolver protocol v0.1")
    assert "English text is normative" in kop


def test_the_prose_is_english():
    """Waarden op de draad blijven letterlijk (`tekst`, `waargenomen`); de
    lopende tekst niet."""
    proza = re.sub(r"```.*?```", "", PROTOCOL, flags=re.S)
    proza = re.sub(r"`[^`\n]*`", "", proza)
    nederlands = {"het", "een", "wordt", "niet", "zijn", "wij", "naar", "deze", "ook", "maar"}
    gevonden = sorted({woord for woord in re.findall(r"\w+", proza.lower()) if woord in nederlands})
    assert gevonden == []
