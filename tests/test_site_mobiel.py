"""De site op een telefoon (2026-11-17, PO: "Wil je nog even volledige sweep op mobiel view doen, overflow, weergave op
320px"). Gemeten met headless Chrome op 320 tot 414 px (`site/scripts/mobiel.mjs`); deze tests houden vast wat daar
misging, zonder browser:

- de datum in een rij van de lijst duwde de pagina tot 104 px breder dan het scherm (in het Russisch);
- een zoekveld van 15 px: iOS zoomt dan in zodra je erin tikt, en de pagina schuift opzij;
- tikdoelen onder 44 px (DESIGN §5, DESIGNSYSTEEM: 44 px).
"""

from __future__ import annotations

import re

from tests import websitebouw

SRC = websitebouw.SITE / "src"
CSS = SRC / "styles" / "site.css"


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def _regel(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_a_list_row_never_makes_a_phone_screen_wider_than_the_screen():
    """Een rij is een raster met één kolom die mag krimpen; oordeel en datum lopen door naar een tweede regel als ze niet
    naast elkaar passen, en het label wordt nooit breder dan de rij."""
    css = _css()
    assert "grid-template-columns: minmax(0, 1fr)" in _regel(css, ".fz .rij")
    assert "flex-wrap: wrap" in _regel(css, ".fz .rij-kop")
    assert "max-width: 100%" in _regel(css, ".fz .label")


def _klassen_van_invoer(bron: str) -> list[str]:
    """De klassen van elk input-, textarea- en select-element in een bestand; een klasse uit een variabele wordt opgezocht."""
    uit = []
    for m in re.finditer(r"<(input|textarea|select)\b([^>]*?)/?>", bron, re.S):
        attrs = m.group(2)
        if re.search(r'type="(checkbox|radio|hidden)"', attrs):
            continue
        letterlijk = re.search(r'class(?:Name)?="([^"]*)"', attrs)
        variabele = re.search(r"className=\{(\w+)\}", attrs)
        if letterlijk:
            uit.append(letterlijk.group(1))
        elif variabele:
            def_ = re.search(r"const " + variabele.group(1) + r" = ([^;]*);", bron, re.S)
            assert def_, variabele.group(1)
            uit += re.findall(r"'([^']*)'", def_.group(1))
    return uit


def test_no_text_field_is_smaller_than_16px_on_a_touch_screen_so_ios_does_not_zoom_in():
    """Safari op iOS zoomt in op een veld onder 16 px zodra je erin tikt (het zoekveld op de start en het zoekvenster). Elk
    veld met een kleinere letter krijgt op een aanraakscherm 16 px; de klasse `invoer` regelt dat in de opmaak."""
    gezien = 0
    for bestand in sorted((SRC / "components").rglob("*")):
        if bestand.suffix not in (".jsx", ".astro"):
            continue
        for klassen in _klassen_van_invoer(bestand.read_text(encoding="utf-8")):
            gezien += 1
            woorden = klassen.split()
            klein = [w for w in woorden if (m := re.fullmatch(r"text-\[(\d+(?:\.\d+)?)px\]", w)) and float(m.group(1)) < 16]
            if klein:
                assert "pointer-coarse:text-[16px]" in woorden, (bestand.name, klassen)
            if "invoer" in woorden:
                assert re.search(r"@media \(pointer: coarse\) \{ \.fz \.invoer \{[^}]*font-size: 16px", _css())
    assert gezien >= 3


def test_on_a_touch_screen_the_small_links_the_sweep_found_are_44_px():
    """De link naar de maker in de voet, *Alle thema's* en *Alle landen als lijst* bij Verkennen, en een kort woord in een
    lijst ("LCI", "Fiji") waren lager of smaller dan 44 px."""
    css = _css()
    assert re.search(r"@media \(pointer: coarse\) \{ \.fz \.voet-licenties a, \.fz \.voet-maker a \{ min-height: 2\.75rem;", css)
    assert re.search(r"@media \(pointer: coarse\) \{ \.fz \.vk-alles \{[^}]*min-height: 2\.75rem", css)
    assert re.search(r"@media \(pointer: coarse\) \{ \.fz \.vk-alle summary \{ padding-block: \.75rem; \}", css)
    assert re.search(r"\.fz \.voet-b li a \{ min-width: 2\.75rem; \}", css)
    for naam in ("Themas.astro", "Redacties.astro", "Verkennen.astro"):
        bron = (SRC / "components" / "site" / "paginas" / naam).read_text(encoding="utf-8")
        assert 'class="link min-w-11 truncate"' in bron and 'class="link min-w-0 truncate"' not in bron, naam


def test_long_words_and_long_buttons_wrap_instead_of_running_off_a_phone_screen():
    """Een lange themanaam in het Russisch werd afgekapt op de start; de knop naar alle factchecks met een naam liep in het
    Duits 29 px buiten het scherm."""
    start = (SRC / "components" / "site" / "paginas" / "Start.astro").read_text(encoding="utf-8")
    assert re.search(r'<span class="min-w-0 [^"]*hyphens-auto \[overflow-wrap:anywhere\]">\{th\.naam\}', start)
    naam = (SRC / "components" / "site" / "paginas" / "Naam.astro").read_text(encoding="utf-8")
    assert '<a class="knop h-auto min-h-11 whitespace-normal py-2" href={n.alle}>' in naam


def test_the_search_button_in_the_header_shows_a_short_word_on_a_phone_and_no_keys_on_a_touch_screen():
    """Op 320 px stond in de zoekknop van de kop alleen "S.": op een telefoon het korte woord (`zoek_knop`), en in een knop
    die daar te smal voor is alleen de loep; de naam voor een schermlezer blijft de hele zin. De regel met pijltjes en Enter
    onder het zoekvenster hoort bij een toetsenbord, niet bij een aanraakscherm."""
    palet = (SRC / "components" / "site" / "Zoekpalet.jsx").read_text(encoding="utf-8")
    knop = palet[palet.index('className="zoekknop @container"'):palet.index("</DialogPrimitive.Trigger>")]
    assert "aria-label={tekst.knop}" in knop
    assert re.search(r'className="[^"]*max-sm:hidden" aria-hidden="true">\{tekst\.knop\}', knop)
    assert re.search(r'className="[^"]*@max-\[4\.5rem\]:hidden sm:hidden" aria-hidden="true">\{tekst\.kort \?\? tekst\.knop\}', knop)
    assert re.search(r'<div className="[^"]*pointer-coarse:hidden">\s*<span><kbd>↑</kbd>', palet)
    site = (SRC / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "kort: t('zoek_knop')" in site


def test_a_list_grid_on_a_phone_has_one_column_that_may_shrink_and_a_cut_off_link_keeps_its_ellipsis():
    """Een raster zonder kolombreedte wordt zo breed als zijn langste regel: in het Russisch liep een onderwerp bij de thema's
    88 px buiten zijn kaart. Op een telefoon één kolom van `grid-cols-1` (minmax(0, 1fr)); een link die afkapt blijft op een
    aanraakscherm een blok, anders tekent de browser geen beletselteken."""
    for bestand in sorted((SRC / "components" / "site" / "paginas").glob("*.astro")):
        for klassen in re.findall(r'<ul class="([^"]*)"', bestand.read_text(encoding="utf-8")):
            woorden = klassen.split()
            if "grid" in woorden and any(re.fullmatch(r"(sm|md|lg):grid-cols-\d", w) for w in woorden):
                assert any(re.fullmatch(r"grid-cols-\d", w) for w in woorden), (bestand.name, klassen)
    assert re.search(r"\.fz a\.link\.truncate \{ display: block; line-height: 2\.75rem; \}", _css())
