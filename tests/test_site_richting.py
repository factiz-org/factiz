"""Een pagina van rechts naar links (PLAN #34.2bd, SPECS E9.S29): de richting komt uit de taal, de opmaak gebruikt begin
en eind in plaats van links en rechts, pijlen opzij draaien mee, en een bewering houdt haar eigen kant."""

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site" / "src"
BRONNEN = [f for map_ in ("components", "layouts", "pages") for f in (SITE / map_).rglob("*")
           if f.suffix in (".astro", ".jsx", ".js") and f.is_file()]
STIJLEN = [SITE / "styles" / "site.css", SITE / "styles" / "global.css"]

# klassen van Tailwind die aan links of rechts vastzitten
FYSIEK = re.compile(r"(?<![\w-])(?:-?[mp][lr]-[\w\[\].%/-]+|(?:left|right)-[\w\[\].%/-]+|text-(?:left|right)(?![\w-])"
                    r"|border-[lr](?![\w])|border-[lr]-[\w\[\]-]+|rounded-[lr](?![\w])|rounded-[lr]-[\w\[\]-]+)")
# eigenschappen in de opmaak die aan links of rechts vastzitten
FYSIEKE_REGEL = re.compile(r"(?:margin|padding|border)-(?:left|right)|text-align:\s*(?:left|right)|(?<![\w-])(?:left|right):")
# waar links of rechts bewust blijft, met de reden
BEWUST = {
    '.fz .rij-bewering[dir="rtl"]': "een bewering van rechts naar links staat rechts in haar kaart, op elke pagina (AC4)",
    '.fz .rij-bewering:not([dir="rtl"])': "een bewering van links naar rechts staat links, ook op een pagina van rechts (AC4)",
    ".fz-venster": "midden op het scherm: links 50% en een halve breedte terug is in beide richtingen hetzelfde",
}


def _zonder_commentaar(tekst: str) -> str:
    """Zonder commentaar: blokken met /* */ (ook {/* */} in JSX) en regels die met // beginnen."""
    tekst = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", "", tekst, flags=re.S)
    return re.sub(r"^[ \t]*//[^\n]*", "", tekst, flags=re.M)


def test_the_direction_of_a_page_comes_from_its_language():
    talen = (SITE / "lib" / "talen.js").read_text(encoding="utf-8")
    assert "export const RTL = new Set(['ar', 'fa', 'he', 'ur']);" in talen
    assert "export const richting = (taal) => (RTL.has(taal) ? 'rtl' : 'ltr');" in talen
    site = (SITE / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert '<html lang={BCP47[taal]} dir={richting(taal)}>' in site and 'dir="ltr"' not in site


def test_no_component_is_tied_to_left_or_right():
    gevonden = [(f.name, m.group(0)) for f in BRONNEN for m in FYSIEK.finditer(_zonder_commentaar(f.read_text(encoding="utf-8")))]
    assert gevonden == [], gevonden


def test_no_style_is_tied_to_left_or_right_except_where_written_down():
    for stijl in STIJLEN:
        for regel in _zonder_commentaar(stijl.read_text(encoding="utf-8")).splitlines():
            if FYSIEKE_REGEL.search(regel) and "translateX" not in regel:
                assert any(regel.lstrip().startswith(sel) for sel in BEWUST), (stijl.name, regel.strip())


def test_an_arrow_that_points_sideways_turns_with_the_page():
    for f in BRONNEN:
        tekst = _zonder_commentaar(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"[→←]", tekst):
            voor = tekst[max(0, m.start() - 40):m.start()]
            assert voor.endswith('<span class="pijl" aria-hidden="true">') or voor.endswith("<kbd>"), (f.name, voor)
    css = (SITE / "styles" / "site.css").read_text(encoding="utf-8")
    assert re.search(r'\[dir="rtl"\] \.fz \.pijl \{[^}]*scaleX\(-1\)', css)


def test_a_claim_keeps_its_own_side_and_the_country_bars_grow_from_the_start():
    css = (SITE / "styles" / "site.css").read_text(encoding="utf-8")
    assert '.fz .rij-bewering[dir="rtl"] { margin-left: auto; }' in css
    assert '.fz .rij-bewering:not([dir="rtl"]) { margin-right: auto; }' in css
    assert re.search(r'\[dir="rtl"\] \.fz \.vk-land svg \{[^}]*scaleX\(-1\)', css)


def test_a_timeline_stays_left_to_right_and_a_translated_heading_takes_its_own_direction():
    """AC5: de jaren op Verkennen en in de kaarten naast een factcheck draaien niet om, anders staat 2026 boven het begin
    van de lijn. AC4: de kop van een vertaalde bewering neemt de richting van haar eigen tekst."""
    verkennen = (SITE / "components" / "site" / "paginas" / "Verkennen.astro").read_text(encoding="utf-8")
    kaarten = (SITE / "components" / "site" / "ContextKaarten.astro").read_text(encoding="utf-8")
    assert '<ol class="vk-jaren" dir="ltr"' in verkennen
    assert '<span class="ck-staafjes" dir="ltr"' in kaarten and '<span class="ck-as" dir="ltr"' in kaarten
    factcheck = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    assert "lang={p.vertaling.taal} dir=\"auto\"><MetWeg tekst={p.vertaling.tekst} ster={p.weggelaten} /></h1>" in factcheck


def test_every_arrow_is_the_same_short_arrow():
    """PO 2026-11-23: "Erken overigens bij die link overal zo'n lange pijl, maar ik wil die korte pijl." Eén onderdeel
    (`Pijl.astro`), een korte lijn met een punt, in plaats van het teken → dat in Geist lang is."""
    pijl = (SITE / "components" / "site" / "Pijl.astro").read_text(encoding="utf-8")
    assert '<svg class="pijl"' in pijl and 'aria-hidden="true"' in pijl
    for f in BRONNEN:
        tekst = _zonder_commentaar(f.read_text(encoding="utf-8"))
        assert '<span class="pijl" aria-hidden="true">' not in tekst, f.name
