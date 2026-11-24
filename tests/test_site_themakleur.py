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
    66 tekens per volle regel, mediaan 60, in het Engels en het Nederlands. Sinds 2026-11-24 (PO: "ook hier is de minimal
    width een beetje kort") op 17 px en de leesmaat van 48ch: ongeveer 66 tekens, nooit breder dan lopende tekst."""
    regel = re.search(r"\.fz \.rij-bewering, \.fz \.rij-origineel \{ max-width: (?:(\d+)ch|var\(--maat-tekst\)); \}", CSS)
    assert regel and (regel.group(1) is None or int(regel.group(1)) <= 48)
    assert re.search(r"--maat-tekst: (\d+)ch;", CSS) and int(re.search(r"--maat-tekst: (\d+)ch;", CSS).group(1)) <= 48


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


def test_reading_text_has_one_size_of_seventeen_pixels_and_the_measure_grows_with_it():
    """De leesmaat (PO 2026-11-24, na een proef met 15,5, 17 en 18 pixels: "17 pixels"). Op 15,5 pixels was de regel met
    gemiddeld 67 tekens goed, maar de letter klein en de kolom 493 px; op 17 pixels telt een regel nog steeds ongeveer 66
    tekens en wordt de kolom 541 px, omdat de maat in ch staat. Eén klasse voor lopende tekst in een lang stuk (een eigen
    check, Over, Platform, de databasepagina, de inleiding van een dossier), met de leeskop van 18 px erboven."""
    assert re.search(r"--lees: 17px;", CSS)
    regel = re.search(r"\.fz \.leestekst[^{]*\{([^}]*)\}", CSS).group(1)
    assert "font-size: var(--lees)" in regel and "line-height: 1.6" in regel and "max-width: var(--maat-tekst)" in regel
    for kiezer in (r"\.fz \.fz-eigen-tekst p", r"\.fz \.fz-eigen-uitzoeken"):
        assert re.search(kiezer + r"[^{]*\{[^}]*font-size: var\(--lees\)", CSS), kiezer
    # de inleiding van een eigen check blijft een stap groter dan de tekst eronder
    kort = re.search(r"\.fz \.fz-eigen-kort \{([^}]*)\}", CSS).group(1)
    assert re.search(r"font-size: (19|20)px", kort), kort
    paginas = WORTEL / "site" / "src" / "components" / "site" / "paginas"
    eigen = (paginas / "EigenCheck.astro").read_text(encoding="utf-8")
    koppen = re.findall(r'<div class="sectiekop"><h2([^>]*)>', eigen)
    assert koppen and all('class="leeskop"' in k for k in koppen), koppen
    for naam in ("Over.astro", "Platform.astro"):
        bron = (paginas / naam).read_text(encoding="utf-8")
        assert '<p class="leading-relaxed">' not in bron and 'class="leestekst"' in bron, naam
    dossier = (paginas / "Dossier.astro").read_text(encoding="utf-8")
    assert '<p class="leestekst">{d.inleiding}</p>' in dossier


def _token(blok: str, naam: str) -> str:
    return re.search(r"--" + naam + r":\s*(#[0-9a-fA-F]{6})", blok).group(1)


def test_running_text_is_not_white_on_pitch_black_nor_black_on_white():
    """De inkt van lopende tekst (PO 2026-11-24: "Nu lijkt het heel erg wit op pikzwart, wat niet zo prettig leest. En in
    light modus is dit misschien ook zo"). Lichte tekst op bijna zwart straalt uit, vooral bij wie astigmatisch is; de
    richtlijn van Material voor donker is een grond van #121212 met tekst op 87% wit, ongeveer 14:1. Wij: een eigen inkt
    voor lopende tekst (`--tekst`) van 12:1 tot 15:1 op de grond, in licht en donker; koppen en knoppen houden `--inkt`;
    en de donkere grond niet meer zo zwart als #0a0a0a. Ruim boven AAA (7:1)."""
    licht = re.search(r"\.fz \{(.*?)\n\}", CSS, re.S).group(1)
    donker = re.search(r'@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-weergave="licht"\]\) \.fz \{(.*?)\}', CSS, re.S).group(1)
    gekozen = re.search(r':root\[data-weergave="donker"\] \.fz \{(.*?)\}', CSS, re.S).group(1)
    for naam in ("grond", "paneel", "inkt", "tekst", "lijn"):
        assert _token(donker, naam) == _token(gekozen, naam), naam
    for blok in (licht, donker):
        grond, paneel, tekst, inkt = (_token(blok, n) for n in ("grond", "paneel", "tekst", "inkt"))
        for vlak in (grond, paneel):
            assert 12 <= _contrast(tekst, vlak) <= 15.5, (tekst, vlak, _contrast(tekst, vlak))
        assert _contrast(inkt, grond) > _contrast(tekst, grond)
    assert sum(_rgb(_token(donker, "grond"))) > sum(_rgb("#0a0a0a"))
    for kiezer in (r"\.fz \.fz-eigen-tekst p", r"\.fz \.fz-eigen-uitzoeken", r"\.fz main article \.leestekst"):
        assert re.search(kiezer + r"[^{]*\{[^}]*color: var\(--tekst\)", CSS), kiezer


def test_every_kind_of_text_follows_one_scale():
    """De volle ronde over tekst (PO 2026-11-24: "Doe maar even gewoon een full sweep op alle teksten en regels en de
    breedte van blokken tekst"), gemeten op 14 pagina's op 1440 en 390 px. Een bewering in een rij leest als titel op
    17 px tot ongeveer 66 tekens; de inleiding van elke pagina op de leesmaat; zinnen in een kaart nooit onder 14 px en
    een noot nooit onder 12,5; geen blok tekst breder dan de maat (een bijschrift van 234 tekens per regel, een tijdlijn
    van 95); de bronnen van een eigen check in kolommen van de leesmaat in plaats van één smalle strook."""
    def regel(kiezer):
        return re.search(r"\.fz " + kiezer + r" \{([^}]*)\}", CSS).group(1)
    bewering = regel(r"\.rij-bewering")
    assert "font-size: 17px" in bewering
    assert re.search(r"\.fz \.rij-bewering, \.fz \.rij-origineel \{ max-width: var\(--maat-tekst\); \}", CSS)
    for kiezer, minimum in ((r"\.ck-zin", 14), (r"\.ck-naam", 14), (r"\.ck-namen", 14), (r"\.ck-noot", 13),
                            (r"\.filteruitleg", 12.5), (r"\.fz-eigen-zin", 16)):
        maat = float(re.search(r"font-size: ([\d.]+)px", regel(kiezer)).group(1))
        assert maat >= minimum, (kiezer, maat)
    assert re.search(r"\.fz \.fz-eigen-tijd li > \* \+ \* \{[^}]*\}", CSS)
    assert re.search(r"\.fz \.fz-eigen-tijd li > :last-child \{[^}]*max-width: var\(--maat-tekst\)", CSS)
    bronnen = re.search(r"^\.fz \.fz-eigen-bronnen \{([^}]*)\}", CSS, re.M).group(1)
    assert "columns:" in bronnen
    paginas = WORTEL / "site" / "src" / "components" / "site" / "paginas"
    verkennen = (paginas / "Verkennen.astro").read_text(encoding="utf-8")
    assert re.search(r'<figcaption class="[^"]*max-w-\[var\(--maat-tekst\)\]', verkennen)
    for p in paginas.glob("*.astro"):
        tekst = p.read_text(encoding="utf-8")
        assert "text-[15.5px] leading-relaxed" not in tekst and "text-[17px] leading-relaxed" not in tekst, p.name
