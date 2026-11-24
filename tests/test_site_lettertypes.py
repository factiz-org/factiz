"""De lettertypes van de site (PLAN #34.2aw, B78): Geist voor alles wat wij schrijven en voor de lijst, Newsreader alleen
voor de kop van een factcheck, met Noto Serif per schrift erachter. Pakketten van Fontsource met een vaste versie, bij
het bouwen gebundeld en van de site zelf geladen; elk deel draagt de tekens waarvoor het is, dus een pagina laadt alleen
wat ze nodig heeft (PO 2026-11-15: "alle resultaten in Geist ... alleen voor de fact-check zelf de headline")."""

import json
import re
from pathlib import Path

from tests import websitebouw

WORTEL = Path(__file__).resolve().parent.parent
SITE = WORTEL / "site"
CSS = (SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
# de lijst van lettertypen, door `site/scripts/lettertypen.mjs` gemaakt uit de pakketten (PLAN #34.2bs)
LIJST = (SITE / "src" / "styles" / "lettertypen.css").read_text(encoding="utf-8")
PAKKET = json.loads((SITE / "package.json").read_text(encoding="utf-8"))
SCHRIFTEN = ("Noto Naskh Arabic", "Noto Serif Devanagari", "Noto Serif SC", "Noto Serif TC", "Noto Serif JP")

# Het schrift van elke sitetaal (PO 2026-11-16, "Ja, bouw C"): alleen die schriften komen in Noto, elk ander uit het
# toestel. Een nieuwe sitetaal moet hier staan, zodat iemand beslist of haar schrift een lettertype meekrijgt.
SCHRIFT_VAN_TAAL = {"en": "Latijn", "nl": "Latijn", "de": "Latijn", "es": "Latijn", "fr": "Latijn", "pt": "Latijn",
                    "id": "Latijn", "tr": "Latijn", "ru": "Cyrillisch", "uk": "Cyrillisch", "zh": "Chinees", "ja": "Japans",
                    "hi": "Devanagari", "ar": "Arabisch", "fa": "Arabisch"}
# per schrift de lettertypen naast Geist en Noto Sans (die het Latijn, Cyrillisch, Grieks en Vietnamees dragen), en de
# delen van hun pakket die mee mogen: alleen dat schrift zelf
NOTO_PER_SCHRIFT = {
    "Arabisch": {"Noto Sans Arabic": r"arabic", "Noto Naskh Arabic": r"arabic"},
    "Devanagari": {"Noto Sans Devanagari": r"devanagari", "Noto Serif Devanagari": r"devanagari"},
    "Chinees": {"Noto Sans SC": r"\[\d+\]", "Noto Sans TC": r"\[\d+\]", "Noto Serif SC": r"\[\d+\]", "Noto Serif TC": r"\[\d+\]"},
    "Japans": {"Noto Sans JP": r"\[\d+\]", "Noto Serif JP": r"\[\d+\]"},
}
LATIJN = r"latin|latin-ext|cyrillic|cyrillic-ext|greek|greek-ext|vietnamese"
VLAKKEN = [(naam, re.search(r"font-family:\s*'([^']+)'", vlak).group(1),
            re.search(r"@fontsource-variable/([a-z-]+)/files/", vlak).group(1))
           for naam, vlak in re.findall(r"/\* ([a-z0-9\[\]-]+) \*/\n@font-face \{([^}]*)\}", LIJST)]


def _stapel(naam: str) -> list[str]:
    regel = re.search(rf"--{naam}:\s*([^;]+);", CSS)
    assert regel, naam
    verwijzing = re.fullmatch(r"var\(--([a-z-]+)\)", regel.group(1).strip())
    if verwijzing:
        return _stapel(verwijzing.group(1))
    return [d.strip().strip('"') for d in regel.group(1).split(",")]


def test_japanese_and_traditional_chinese_put_their_own_noto_first():
    """PLAN #34.2bs: een browser kiest op de volgorde van de lijst, niet op de taal; zonder dit stond een Japanse pagina
    in de Chinese letters en laadde ze 4,2 MB aan lettertypen."""
    for soort in ("sans", "serif"):
        zh, tw, ja = (_stapel(f"{soort}-{v}") for v in ("zh", "tw", "ja"))
        cjk = lambda s: [f for f in s if re.search(r" (SC|TC|JP) Variable$", f)]
        rest = lambda s: [f for f in s if f not in cjk(s)]
        assert rest(zh) == rest(tw) == rest(ja)
        assert [f.split()[-2] for f in cjk(zh)] == ["SC", "TC", "JP"]
        assert [f.split()[-2] for f in cjk(tw)] == ["TC", "SC", "JP"]
        assert [f.split()[-2] for f in cjk(ja)] == ["JP", "SC", "TC"]
    regels = {k.strip(): v for k, v in re.findall(r"^(\.fz[^{\n]*)\{([^}]*)\}", CSS, re.M)}
    assert "--sans: var(--sans-ja); --serif: var(--serif-ja);" in regels[".fz:lang(ja)"]
    assert "--sans: var(--sans-tw); --serif: var(--serif-tw);" in regels[".fz:lang(zh-Hant)"]
    assert "font-family: var(--sans)" in regels['.fz [lang|="ja"]']
    assert "--sans: var(--sans-zh)" in regels['.fz:lang(ja) [lang="zh"]']
    # de taal van een Chinese pagina is traditioneel Chinees: de regel hoort bij wat de site echt in lang zet
    talen = json.loads((WORTEL / "factiz_site" / "teksten" / "sitetalen.json").read_text(encoding="utf-8"))["talen"]
    assert {t["code"]: t["bcp47"] for t in talen}["zh"] == "zh-Hant"


def _pakket(familie: str) -> str:
    """'Noto Serif SC Variable' -> '@fontsource-variable/noto-serif-sc'."""
    return "@fontsource-variable/" + familie.removesuffix(" Variable").lower().replace(" ", "-")


def test_only_the_heading_of_a_fact_check_is_set_in_newsreader():
    gebruik = []
    for bestand in (SITE / "src").rglob("*"):
        if bestand.suffix in (".astro", ".jsx", ".js", ".css") and bestand.is_file():
            for regel in bestand.read_text(encoding="utf-8").splitlines():
                if "var(--serif)" in regel:
                    gebruik.append((bestand.name, regel.strip()))
    # en de bewering van een eigen factcheck (#37.4, DESIGN §4x): ook wat een ander zei (§4h), sinds 2026-11-19 op het vlak
    # zoals bij een factcheck; de kop van een eigen check is ons eigen woord en staat in Geist
    eigen = [(n, r) for n, r in gebruik if n == "EigenCheck.astro" and r.startswith("<blockquote data-nosnippet class=")]
    gebruik = [g for g in gebruik if g not in eigen]
    assert len(eigen) == 1
    assert len(gebruik) == 2 and all(naam == "Factcheck.astro" and re.search(r"<h1 (data-nosnippet )?class=", regel)
                                     for naam, regel in gebruik), gebruik
    # de lijst is Geist, iets zwaarder dan de tekst eromheen
    lijst = re.search(r"\.fz \.rij-bewering \{([^}]*)\}", CSS).group(1)
    assert "font-family" not in lijst and "font-weight: 500" in lijst
    assert re.search(r"\.fz \{[^}]*font-family: var\(--sans\)", CSS)


def test_the_heading_falls_back_on_noto_for_every_other_script():
    stapel = _stapel("serif")
    assert stapel[:2] == ["Newsreader Variable", "Noto Serif Variable"] and stapel[-1] == "serif"
    for schrift in SCHRIFTEN:
        assert f"{schrift} Variable" in stapel, schrift
    assert _stapel("sans")[0] == "Geist Variable" and _stapel("mono")[0] == "Geist Mono Variable"


def test_every_font_comes_from_a_package_with_a_fixed_version():
    afhankelijk = PAKKET["dependencies"]
    # de site leest de lettertypen alleen uit de lijst, nooit een heel stijlblad van een pakket
    assert '@import "./lettertypen.css";' in CSS and "@fontsource" not in CSS
    geladen = sorted({"@fontsource-variable/" + pakket for _, _, pakket in VLAKKEN})
    assert len(geladen) == 15 and len(VLAKKEN) > 100
    for naam in geladen:
        assert re.fullmatch(r"\d+\.\d+\.\d+", afhankelijk.get(naam, "")), naam
    # elk lettertype in een stapel heeft zijn pakket, en elk pakket in de lijst staat in een stapel
    stapels = [f for f in _stapel("serif") + _stapel("sans") + _stapel("mono") if f.endswith(" Variable")]
    assert sorted({_pakket(f) for f in stapels}) == geladen
    for naam, familie, pakket in VLAKKEN:
        assert _pakket(familie) == "@fontsource-variable/" + pakket, naam
    # Newsreader met de as voor optische grootte, zodat de kop scherp blijft van telefoon tot breed scherm
    assert {naam.rsplit("-", 2)[-2] for naam, familie, _ in VLAKKEN if familie == "Newsreader Variable"} == {"opsz"}


def test_the_font_list_is_what_the_script_makes_from_the_packages():
    """PLAN #34.2bs (c): na een nieuwe versie van een pakket `npm --prefix site run lettertypen`."""
    import subprocess
    uit = subprocess.run(["node", "scripts/lettertypen.mjs", "--toets"], cwd=SITE, capture_output=True, text=True,
                         timeout=60)
    assert uit.returncode == 0, uit.stdout + uit.stderr


def test_only_the_scripts_of_the_site_languages_come_in_noto_the_rest_from_the_device():
    """PLAN #34.2bs (a), SPECS E9.S28 AC1: een bewering in het Telugu of Thai staat in de letters van het toestel."""
    talen = json.loads((WORTEL / "factiz_site" / "teksten" / "sitetalen.json").read_text(encoding="utf-8"))["talen"]
    assert {t["code"] for t in talen} == set(SCHRIFT_VAN_TAAL)
    verwacht = {"Noto Sans", "Noto Serif"} | {f for s in set(SCHRIFT_VAN_TAAL.values()) for f in NOTO_PER_SCHRIFT.get(s, {})}
    in_stapels = {f.removesuffix(" Variable") for f in _stapel("sans") + _stapel("serif") if f.startswith("Noto ")}
    assert in_stapels == verwacht
    assert {familie.removesuffix(" Variable") for _, familie, _ in VLAKKEN if familie.startswith("Noto ")} == verwacht
    # na de eigen lettertypen die van het toestel, zodat de browser elk ander schrift daar zoekt
    assert _stapel("sans")[-5:] == ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"]
    assert _stapel("serif")[-3:] == ["ui-serif", "Georgia", "serif"]


def test_a_font_for_one_script_brings_only_the_parts_of_that_script():
    """PLAN #34.2bs (b): het Latijnse of wiskundige deel van Noto Sans Arabic haalde de browser op voor een teken dat Geist
    mist; Devanagari alleen uit Noto Sans Devanagari, zoals op het deelplaatje."""
    delen = {f"{f} Variable": d for s in NOTO_PER_SCHRIFT.values() for f, d in s.items()}
    delen |= {"Noto Sans Variable": LATIJN, "Noto Serif Variable": LATIJN}
    for naam, familie, pakket in VLAKKEN:
        deel = re.fullmatch(rf"{pakket}-(.+)-(?:wght|opsz)-normal", naam).group(1)
        if familie in delen:
            assert re.fullmatch(delen[familie], deel), (familie, deel)


def test_the_share_image_still_draws_every_script_in_noto():
    """PLAN #34.2bs (d): de pakketten blijven, ook die de browser niet meer laadt."""
    from factiz_site.deelbeeld import NOTO
    for pakket in NOTO:
        assert re.fullmatch(r"\d+\.\d+\.\d+", PAKKET["dependencies"].get(f"@fontsource-variable/{pakket}", "")), pakket
    assert {"noto-sans-telugu", "noto-sans-thai", "noto-sans-kr"} <= set(NOTO)


def test_the_built_fonts_come_from_the_site_and_each_part_names_its_characters():
    websitebouw.site()
    opmaak = "".join(f.read_text(encoding="utf-8") for f in (SITE / "dist" / "client" / "_astro").glob("*.css"))
    vlakken = re.findall(r"@font-face\{([^}]*)\}", opmaak)
    assert len(vlakken) > 100
    families = set()
    for vlak in vlakken:
        families.add(re.search(r"font-family:\s*([^;]+)", vlak).group(1).strip().strip('"'))
        bronnen = re.findall(r"url\(([^)]+)\)", vlak)
        assert bronnen and all(b.strip("'\"").startswith("/_astro/") for b in bronnen), vlak[:120]
        assert "unicode-range:" in vlak, vlak[:120]
    assert {"Geist Variable", "Newsreader Variable", "Noto Naskh Arabic Variable", "Noto Serif SC Variable"} <= families
    assert "fonts.googleapis" not in opmaak and "url(http" not in opmaak


def test_a_right_to_left_claim_starts_on_the_right_of_its_card():
    assert re.search(r'\.fz \.rij-bewering\[dir="rtl"\] \{ margin-left: auto; \}', CSS)


NOTO_SANS = ("Noto Sans Arabic", "Noto Sans Devanagari", "Noto Sans SC", "Noto Sans TC", "Noto Sans JP")


def test_what_we_write_is_geist_with_noto_sans_for_the_scripts_of_the_site_languages():
    """PLAN #34.2as en #34.2bs, SPECS E9.S28 AC1: menu's, knoppen en tekst in Geist, en de schriften van de sitetalen in
    Noto Sans; Chinees: traditioneel na vereenvoudigd."""
    stapel = _stapel("sans")
    assert stapel[:2] == ["Geist Variable", "Noto Sans Variable"] and stapel[-1] == "sans-serif"
    noto = [f.removesuffix(" Variable") for f in stapel]
    assert [f for f in noto if f.startswith("Noto Sans ")] == list(NOTO_SANS)


def test_the_names_of_the_languages_never_pull_in_a_font_of_their_own():
    """PLAN #34.2bs: de taalkiezer en de voet noemen elke taal in haar eigen schrift; die namen staan in de letters van het
    toestel, behalve de naam van de taal van de pagina zelf. Anders haalde elke pagina ~0,6 MB op voor vier woorden."""
    kiezer = (SITE / "src" / "components" / "site" / "Taalkiezer.jsx").read_text(encoding="utf-8")
    voet = (SITE / "src" / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert '<span className="taalnaam' in kiezer and "{l.naam}" in kiezer
    assert voet.count('class="taalnaam') == 2
    regel = re.search(r"\.fz \.taalnaam \{ font-family: ([^;]+); \}", CSS)
    assert regel and "Noto" not in regel.group(1) and regel.group(1).startswith('"Geist Variable"')
    # de naam van de taal van de pagina in de letters van de pagina, voor elke sitetaal buiten het Latijn en Cyrillisch
    talen = json.loads((WORTEL / "factiz_site" / "teksten" / "sitetalen.json").read_text(encoding="utf-8"))["talen"]
    eigen = {t["bcp47"] for t in talen if SCHRIFT_VAN_TAAL[t["code"]] not in ("Latijn", "Cyrillisch")}
    assert eigen == {"ar", "fa", "hi", "ja", "zh-Hant"}
    for code in eigen:
        assert f":root:lang({code}) .fz .taalnaam:lang({code})" in CSS, code
    # na de regels per taal, zodat ze daar niet door overschreven worden
    assert CSS.index(".fz .taalnaam {") > CSS.index('.fz [lang|="ja"] {')
