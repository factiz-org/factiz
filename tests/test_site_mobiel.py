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


# De tweede ronde (PLAN #34.2ci, PO 2026-11-24: "deze nemen we wel mee in een grote responsive sweep voor mobiel, op alle
# punten"): dezelfde meting op elke soort pagina en open stand in vijftien talen, nu ook de Radar, de wereldlijst, de
# uitslag van een zoekvraag en de vraag om te meten.


def test_a_button_never_runs_off_a_phone_screen_but_wraps_to_a_second_line():
    """De knop *Archived copy from …* bij een check die offline is, liep op 320 px tot 30 px buiten het scherm (in het
    Portugees), en de vraag om te meten schoof mee, want een vaste kaart volgt de bredere pagina. Het was de tweede knop
    met dezelfde fout (in #34.2by de knop bij een naam). Nu geldt het voor elke knop: nooit breder dan zijn plek, en op een
    aanraakscherm een tweede regel als het woord niet past, minstens 44 px hoog."""
    css = _css()
    assert "max-width: 100%" in _regel(css, ".fz .knop")
    m = re.search(r"@media \(pointer: coarse\) \{ \.fz \.knop \{([^}]*)\}", css)
    assert m, "de regel voor een knop op een aanraakscherm"
    for eis in ("height: auto", "min-height: 2.75rem", "white-space: normal", "text-align: center"):
        assert eis in m.group(1), eis
    # de rij met thema's boven de lijst schuift opzij: daar blijft elke knop op één regel
    biblio = (SRC / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    rij = biblio[biblio.index('data-rij="themas"'):]
    assert re.match(r'[^<]*<button [^>]*className="knop shrink-0"', rij[rij.index("{f.promotie.map"):].split("\n", 1)[1])


def test_the_source_factiz_itself_is_shown_by_name_not_as_a_bare_slash():
    """Bij Bronnen stond onder de redactie en de wereldlijst van Factiz een link met alleen "/": de link naar factiz.org
    wordt op de site een pad. Een pad op de site staat er als factiz.org, en is zo ook een tikdoel van 44 px breed."""
    bron = (SRC / "components" / "site" / "paginas" / "Bronnen.astro").read_text(encoding="utf-8")
    link = re.search(r'<a class="link break-all" href=\{b\.url\}[^>]*>\{([^}]*)\}</a>', bron)
    assert link and link.group(1).strip() != "b.url", "de tekst van de link is niet het kale adres"
    assert "factiz.org" in bron


def test_a_short_first_word_of_the_breadcrumb_is_44_px_wide_on_a_touch_screen():
    """*Home* in het Hindi (होम) was een tikdoel van 17 bij 44 px, *Namen* (नाम) 18, *Home* in het Perzisch (خانه) 20. Het woord
    blijft vooraan, op één lijn met de kop eronder: gecentreerd sprong *Home* in."""
    regel = re.search(r"@media \(pointer: coarse\) \{[^@]*\.fz \[data-kruimel\] a \{([^}]*)\}", _css())
    assert regel and "min-width: 2.75rem" in regel.group(1) and "justify-content" not in regel.group(1)


def test_a_line_on_a_list_card_never_starts_with_a_loose_dot():
    """Op een kaart in de lijst stond op 320 px een stip vooraan de tweede regel ("• Video"). Elk stuk krijgt zijn stip, de
    regel schuift één stip naar het begin en knipt die strook af: de stip vóór het eerste stuk van elke regel valt weg, ook
    van rechts naar links."""
    css = _css()
    voet = _regel(css, ".fz .rij-voet")
    assert "margin-inline-start: calc(-1 * var(--stip))" in voet and "clip-path: inset(0 0 0 var(--stip))" in voet
    assert re.search(r'\[dir="rtl"\] \.fz \.rij-voet \{ clip-path: inset\(0 var\(--stip\) 0 0\); \}', css)
    assert ".fz .rij-voet > *::before {" in css and ".fz .rij-voet > * + *::before" not in css


def test_a_feature_with_who_says_it_moves_to_the_next_line_as_a_whole():
    """*Altered or imitated* en *according to the newsroom* stonden op 320 px als twee smalle kolommen naast elkaar, op een
    kaart en als knop op de pagina. Naam en regel staan nu in één tekstvak naast het icoon, dat breekt als een zin."""
    rij = (SRC / "components" / "site" / "Rij.jsx").read_text(encoding="utf-8")
    assert re.search(r'<span className="kenmerk-tekst">\{k\.naam\}\{k\.regel && <>\{\' \'\}<span className="kenmerk-regel">', rij)
    for naam in ("Factcheck.astro", "EigenCheck.astro"):
        bron = (SRC / "components" / "site" / "paginas" / naam).read_text(encoding="utf-8")
        assert '<span class="kenmerk-tekst">{k.naam}{k.regel && <> <span class="kenmerk-regel">' in bron, naam
    assert "min-width: 0" in _regel(_css(), ".fz .kenmerk-tekst")


def test_the_magnifier_sits_in_the_middle_of_a_search_button_too_narrow_for_a_word():
    """Op 320 px stond de loep links in een zoekknop met lege ruimte rechts; zonder woord staat hij in het midden."""
    palet = (SRC / "components" / "site" / "Zoekpalet.jsx").read_text(encoding="utf-8")
    knop = palet[palet.index('className="zoekknop @container"'):palet.index("</DialogPrimitive.Trigger>")]
    assert re.search(r'<Loep className="[^"]*\bmx-auto\b[^"]*" />', knop)


def test_the_phone_sweep_also_measures_the_results_of_a_search():
    """Een zoekvraag gaat als POST, nooit in het adres; de meting verstuurt daarom zelf het formulier (`#zoek=<vraag>`)."""
    script = (websitebouw.SITE / "scripts" / "mobiel.mjs").read_text(encoding="utf-8")
    assert "staat?.startsWith('zoek=')" in script and "f.method = 'post'" in script


def test_the_phone_sweep_refuses_a_page_that_loaded_without_its_styles():
    """Tijdens de meting bouwde iets anders de site opnieuw: de opmaak kreeg een nieuwe naam, en 774 van de 960 pagina's
    werden zonder opmaak gemeten (een logo van 398 px, de verborgen filterkolom). Zo'n pagina is nu een fout, geen uitslag."""
    script = (websitebouw.SITE / "scripts" / "mobiel.mjs").read_text(encoding="utf-8")
    assert "s.href?.includes('/_astro/')" in script and "if (!opmaak) return { fout:" in script


def test_a_long_verdict_stamp_gets_a_second_line_instead_of_running_off_a_phone_screen():
    """In het Russisch liep het stempel "ЛОЖНОЕ ИЛИ ВВОДЯЩЕЕ В ЗАБЛУЖДЕНИЕ" op een kaart 16 px buiten een scherm van 320
    px, en het grote stempel op de factcheckpagina ook. Het stempel mag nu breken, gecentreerd, en is nooit breder dan zijn
    plek."""
    stempel = _regel(_css(), ".fz .fz-stempel")
    assert "white-space: nowrap" not in stempel
    assert "max-width: 100%" in stempel and "text-align: center" in stempel


def test_the_two_answers_to_the_measuring_question_grow_with_a_second_line():
    """De knoppen van de vraag om te meten waren 44 px hoog, vast. In het Arabisch is *نعم، يمكن القياس* te lang voor de
    helft van een scherm van 320 px: de knop krijgt dan een tweede regel en groeit mee, en beide blijven even breed."""
    knop = _regel(_css(), ".fz .fz-meten-knop")
    assert "flex: 1 1 0" in knop and "height: auto" in knop and "min-height: 2.75rem" in knop


def test_the_button_to_search_only_these_words_is_44_px_tall_on_a_touch_screen():
    """In de uitslag van een zoekvraag die een land, redactie of thema las, staat de knop *Alleen op deze woorden zoeken* in
    de zin: in het Chinees en Japans 20 px hoog. Op een aanraakscherm krijgt hij boven en onder 12 px, en een even grote
    negatieve marge, dus de regel wordt niet hoger."""
    biblio = (SRC / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    knop = re.search(r'<button type="button" className="([^"]*)" onClick=\{\(\) => a\.zoek\(a\.vraag, undefined, true\)\}>', biblio)
    assert knop and {"pointer-coarse:py-3", "pointer-coarse:-my-3"} <= set(knop.group(1).split())
