"""Een tekening per thema en per dossier (PLAN #34.2ap, SPECS E9.S22): de tekentaal van de routeplaatjes van Ideelab,
abstracter en met korrel, op het veld. De vormen staan als gegevens in `site/src/lib/platen.js` (één bron voor de site en
het deelplaatje, #34.2aq) en uitgeschreven in `factiz_site/static/platen.json`. Wat op de pagina's staat, toetst
`tests/test_site_html.py`."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parent.parent
PLATEN = json.loads((WORTEL / "factiz_site" / "static" / "platen.json").read_text(encoding="utf-8"))
BRON = (WORTEL / "site" / "src" / "lib" / "platen.js").read_text(encoding="utf-8")
PLAAT = (WORTEL / "site" / "src" / "components" / "site" / "Plaat.jsx").read_text(encoding="utf-8")
THEMAS = [t["sleutel"] for t in json.loads((WORTEL / "content" / "themas.json").read_text(encoding="utf-8"))["themas"]]
DOSSIERS = sorted(p.name for p in (WORTEL / "content" / "dossiers").iterdir() if (p / "dossier.toml").exists())
SOORTEN = {"regel", "blok", "stip", "lijn", "ring", "vlak"}     # vlak: een gevuld pad, voor een kaart of een voorwerp (2026-11-19)


@pytest.mark.skipif(shutil.which("node") is None, reason="node ontbreekt")
def test_the_written_out_drawings_match_their_source():
    r = subprocess.run(["node", "site/scripts/platen.mjs", "--controleer"], cwd=WORTEL, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_theme_and_every_dossier_has_its_own_drawing():
    tekeningen = set(PLATEN["platen"])
    assert {f"thema:{t}" for t in THEMAS} <= tekeningen, {f"thema:{t}" for t in THEMAS} - tekeningen
    assert {f"dossier:{d}" for d in DOSSIERS} <= tekeningen, {f"dossier:{d}" for d in DOSSIERS} - tekeningen


def test_a_drawing_has_only_shapes_without_words_and_one_shape_at_full_colour():
    """Vijf soorten vormen, zonder woorden en zonder eigen kleur (de kleur komt van de familie), en alleen de vorm die de
    betekenis draagt op volle kleur (een dekking van 0,8 of meer); geen vinkje of kruis, want dat leest als een oordeel
    (AC3)."""
    for sleutel, vormen in PLATEN["platen"].items():
        assert {v["v"] for v in vormen} <= SOORTEN, sleutel
        assert any(v["o"] >= 0.8 and not v.get("open") for v in vormen), sleutel
        assert all(0 < v["o"] <= 1 for v in vormen), sleutel
    for tekst in (BRON, PLAAT):
        assert "<text" not in tekst and "Vink" not in tekst and "Kruis" not in tekst


def test_a_drawing_uses_at_most_three_kinds_of_shapes():
    """E9.S22 AC1: hoogstens drie soorten vormen in één tekening, ook nu er een gevuld vlak bij is."""
    for sleutel, vormen in PLATEN["platen"].items():
        assert len({v["v"] for v in vormen}) <= 3, (sleutel, sorted({v["v"] for v in vormen}))


def test_a_filled_shape_is_drawn_filled_on_the_site_and_on_the_share_image():
    """Een vlak is een pad met een vulling in de kleur van de familie, op de site (`Plaat.jsx`) en op het deelplaatje
    (Python en TypeScript), en een gesloten pad (Z) sluit daar ook."""
    assert "case 'vlak'" in PLAAT
    from factiz_site import deelbeeld as dl
    [punten] = dl._pad("M10 10 L20 10 L20 20 Z")
    assert punten[0] == punten[-1] == (10.0, 10.0) and len(punten) == 4
    laag = dl._vormen([{"v": "vlak", "d": "M10 10 L50 10 L50 50 L10 50 Z", "o": 0.9}], (60, 60), 1.0, (37, 37, 82))
    assert laag.getpixel((30, 30))[3] > 200 and laag.getpixel((55, 55))[3] == 0
    ts = (WORTEL / "site" / "src" / "platform" / "deelbeeld-teken.ts").read_text(encoding="utf-8")
    assert "v.v === 'vlak'" in ts


def test_the_drawing_has_no_script_and_no_file_from_elsewhere():
    for tekst in (BRON, PLAAT):
        assert "http" not in tekst
        assert "useEffect" not in tekst and "useState" not in tekst
