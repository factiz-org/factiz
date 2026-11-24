"""Kleur en icoon per onderwerp (PLAN #34.2ag, SPECS E9.S16): vijf families met de namen van de velden, gemeten op
kleurenblindheid, contrast en afstand tot de kleuren van het oordeel, in licht en donker; per thema een icoon uit Lucide
in eigen code; en dezelfde familie als het veld van het thema."""

import itertools
import json
import math
import re
from pathlib import Path

import pytest

from doublecheck import velden

WORTEL = Path(__file__).resolve().parent.parent
CSS = (WORTEL / "site" / "src" / "styles" / "site.css").read_text(encoding="utf-8")
TEGEL = (WORTEL / "site" / "src" / "components" / "site" / "ThemaTegel.jsx").read_text(encoding="utf-8")
THEMAS = [t["sleutel"] for t in json.loads((WORTEL / "content" / "themas.json").read_text(encoding="utf-8"))["themas"]]
FAMILIES = ("leisteen", "nacht", "groen", "olijf", "hemel")

# Machado e.a. (2009), ernst 1,0, in lineair RGB
ZICHT = {"gewoon": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
         "deuteranopie": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
         "protanopie": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
         "tritanopie": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]}


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h):
    return [_lin(int(h[i:i + 2], 16)) for i in (1, 3, 5)]


def _contrast(a, b):
    la, lb = (0.2126 * r + 0.7152 * g + 0.0722 * bl for r, g, bl in (_rgb(a), _rgb(b)))
    hoog, laag = max(la, lb), min(la, lb)
    return (hoog + 0.05) / (laag + 0.05)


def _lab(lin):
    r, g, b = lin
    x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (
        0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _de(a, b, m):
    zie = lambda h: [max(0.0, min(1.0, sum(m[i][j] * v for j, v in enumerate(_rgb(h))))) for i in range(3)]  # noqa: E731
    return math.dist(_lab(zie(a)), _lab(zie(b)))


def _blok(begin: str) -> str:
    i = CSS.index(begin)
    j = CSS.index("{", i) + 1
    diepte = 1
    while diepte:
        diepte += {"{": 1, "}": -1}.get(CSS[j], 0)
        j += 1
    return CSS[i:j]


def _tokens(blok: str, voorvoegsel: str) -> dict[str, str]:
    return dict(re.findall(r"--" + voorvoegsel + r"([a-z]+):\s*(#[0-9a-fA-F]{6})", blok))


STANDEN = {"licht": _blok(".fz {"), "donker": _blok("@media (prefers-color-scheme: dark)")}
GEKOZEN_DONKER = _blok(':root[data-weergave="donker"] .fz')


def test_dark_chosen_in_the_footer_has_the_same_family_colours_as_dark_from_the_device():
    assert _tokens(GEKOZEN_DONKER, "f-") == _tokens(STANDEN["donker"], "f-")


@pytest.mark.parametrize("stand", STANDEN)
def test_the_five_families_stay_apart_for_every_kind_of_sight(stand):
    f = _tokens(STANDEN[stand], "f-")
    kleuren = [f[k] for k in FAMILIES]
    for naam, m in ZICHT.items():
        kleinste = min(_de(a, b, m) for a, b in itertools.combinations(kleuren, 2))
        assert kleinste >= 20, (stand, naam, round(kleinste, 1))


@pytest.mark.parametrize("stand", STANDEN)
def test_an_icon_is_readable_on_its_tile_and_a_tile_on_its_panel(stand):
    blok = STANDEN[stand]
    f = _tokens(blok, "f-")
    icoon, paneel = f["icoon"], re.search(r"--paneel:\s*(#[0-9a-fA-F]{6})", blok).group(1)
    for k in FAMILIES:
        assert _contrast(f[k], icoon) >= 3, (stand, k, round(_contrast(f[k], icoon), 2))
        assert _contrast(f[k], paneel) >= 3, (stand, k, round(_contrast(f[k], paneel), 2))


@pytest.mark.parametrize("stand", STANDEN)
def test_no_family_looks_like_a_verdict(stand):
    blok = STANDEN[stand]
    f = _tokens(blok, "f-")
    oordelen = dict(re.findall(r"--([a-z]+)-stip:\s*(#[0-9a-fA-F]{6})", blok))
    assert len(oordelen) == 7
    for k in FAMILIES:
        dichtst = min(_de(f[k], o, ZICHT["gewoon"]) for o in oordelen.values())
        assert dichtst >= 18, (stand, k, round(dichtst, 1))


def test_every_theme_has_a_family_and_an_icon_and_its_field_belongs_to_that_family():
    rijen = re.findall(r"^\s+([a-z]+): \{ familie: '([a-z]+)', icoon: '([a-z-]+)' \}", TEGEL, re.M)
    familie = {t: f for t, f, _ in rijen}
    iconen = {t: i for t, _, i in rijen}
    assert set(familie) == set(THEMAS)
    assert set(familie.values()) == set(FAMILIES)
    assert {t: velden.THEMA_VELDEN[t][0] for t in THEMAS} == familie
    # elk icoon staat in eigen code, en de licentie van Lucide staat erbij
    for icoon in iconen.values():
        assert re.search(r"^\s+'" + re.escape(icoon) + r"': \[", TEGEL, re.M), icoon
    assert "ISC" in TEGEL and "Lucide Contributors" in TEGEL
    assert len(set(iconen.values())) == len(iconen), "twee thema's met hetzelfde icoon"


def test_the_old_swatch_is_gone_from_the_site():
    bronnen = [p for p in (WORTEL / "site" / "src").rglob("*") if p.suffix in (".jsx", ".astro", ".css")]
    assert not [p.name for p in bronnen if re.search(r"\bstaal\b", p.read_text(encoding="utf-8"))]


def test_the_icon_in_a_tile_keeps_its_own_size():
    """Een regel die een beeld over de hele breedte van zijn vak zet, raakt alleen het eigen beeld van dat vak (`> svg`),
    nooit het icoon in een tegel erbinnen: dat blijft op zijn eigen maat binnen het raster van 24 (de ring van Verkennen
    rekte het icoon uit tot de rand van de tegel, PO 2026-11-15)."""
    for kiezer, regels in re.findall(r"([^{}\n]*\bsvg)\s*\{([^}]*)\}", CSS):
        if re.search(r"(?<![-\w])width:\s*100%", regels):
            assert re.search(r">\s*svg$", kiezer.strip()), kiezer
    for maat, tegel, icoon in (("", 16, 11), ("-midden", 20, 13), ("-groot", 30, 18)):
        regel = re.search(rf"\.fz \.tegel{maat} svg \{{ width: (\d+)px; height: (\d+)px; \}}", CSS)
        assert regel and int(regel.group(1)) == icoon and icoon / tegel <= 0.7, maat


def test_a_claim_in_a_list_stays_a_readable_line():
    """Een leesbare regel (PO 2026-11-15: "Leesbaarheid werkt volgens mij tot 55-64 characters"): de bewering en het
    origineel in een kaart hoogstens 44ch breed, in Geist (PLAN #34.2aw); in de browser gemeten op echte beweringen 50 tot
    66 tekens per volle regel, mediaan 60, in het Engels en het Nederlands."""
    regel = re.search(r"\.fz \.rij-bewering, \.fz \.rij-origineel \{ max-width: (\d+)ch; \}", CSS)
    assert regel and int(regel.group(1)) <= 48


def test_a_stretched_bar_has_square_corners():
    """PO 2026-11-15: "hoekjes van de chart hebben radius dat werkt hier niet". De balken van Verkennen zijn een SVG die
    uitrekt (`preserveAspectRatio="none"`); een ronding wordt daar een scheve punt. Dus geen `rx` in zo'n tekening."""
    pagina = (WORTEL / "site" / "src" / "components" / "site" / "paginas" / "Verkennen.astro").read_text(encoding="utf-8")
    for svg in re.findall(r"<svg[^>]*preserveAspectRatio=\"none\"[^>]*>(.*?)</svg>", pagina, flags=re.S):
        assert " rx=" not in svg, svg[:120]


def test_running_text_keeps_one_measure_of_about_seventy_characters():
    """De maat van een regel (PO 2026-11-20: "de ideale breedte ... zo rond de 60 characters"): lopende tekst op één maat,
    48ch, in Geist gemeten 68 tot 73 tekens per volle regel (in de browser, op Over, een check en een dossier); een kop in
    een lijst op 52ch, ongeveer 75; en geen pagina die een alinea weer op 62ch of breder zet."""
    assert re.search(r"--maat-tekst: 48ch;", CSS) and re.search(r"--maat-kop: 52ch;", CSS)
    for kiezer in (r"\.fz \.fz-eigen-kort", r"\.fz \.fz-eigen-tekst p", r"\.fz \.fz-eigen-uitzoeken", r"\.fz main header p",
                   r"\.fz \.fz-eigen-bronnen li"):
        assert re.search(kiezer + r"[^{]*\{[^}]*max-width: var\(--maat-tekst\)", CSS), kiezer
    # de bewering van een eigen check, in de schreef, op de maat van een kop (PO 2026-11-23: "voldoet deze ook aan onze
    # character count?"): zonder grens liep ze tot 78 tekens, met 52ch 59 tot 67, zoals de kop van een factcheck (64)
    eigen = (WORTEL / "site" / "src" / "components" / "site" / "paginas" / "EigenCheck.astro").read_text(encoding="utf-8")
    assert re.search(r'<blockquote data-nosnippet class="max-w-\[var\(--maat-kop\)\]', eigen)
    for p in (WORTEL / "site" / "src" / "components").rglob("*"):
        if p.suffix in (".astro", ".jsx"):
            for alinea in re.findall(r"<p [^>]*>", p.read_text(encoding="utf-8")):
                assert not re.search(r"max-w-\[(6\d|7\d)ch\]", alinea), (p.name, alinea)
