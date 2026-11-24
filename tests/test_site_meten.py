"""Meten met Google Analytics, alleen na een ja (B88, SPECS E9.S36, PLAN #34.2cg)."""

import json
import re
import subprocess
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
BRON = WORTEL / "site" / "src"
CODE = sorted(p for p in BRON.rglob("*") if p.suffix in {".js", ".jsx", ".ts", ".astro", ".mjs"})
TALEN = [t["code"] for t in json.loads((WORTEL / "factiz_site" / "teksten" / "sitetalen.json").read_text(encoding="utf-8"))["talen"]]


def _node(script: str):
    uit = subprocess.run(["node", "--input-type=module", "-e", script], cwd=WORTEL / "site", capture_output=True, text=True,
                         check=True)
    return json.loads(uit.stdout)


def test_only_a_short_typed_query_without_contact_details_goes_to_analytics():
    """AC3: hoogstens acht woorden, geen e-mailadres, telefoonnummer of reeks van zes of meer cijfers; een jaartal mag."""
    gevallen = ["bill gates chips", "  zelensky   yacht ", "covid 2021", "a b c d e f g h i", "mail jan@example.com",
                "bel 06 12345678", "pas 123456", "", "x" * 101, "Marc Van Ranst corona"]
    script = ("import('./src/lib/meten.js').then((m) => console.log(JSON.stringify("
              f"{json.dumps(gevallen)}.map((q) => m.zoektermVoorMeten(q)))))")
    assert _node(script) == ["bill gates chips", "zelensky yacht", "covid 2021", None, None, None, None, None, None,
                             "Marc Van Ranst corona"]


def test_a_pasted_message_or_a_query_without_a_yes_is_never_measured():
    """De zoekvraag gaat alleen mee na een ja, en nooit bij een geplakt bericht (AC3, B21)."""
    script = ("globalThis.window = globalThis; globalThis.localStorage = { w: {}, getItem(k) { return this.w[k] ?? null }, "
              "setItem(k, v) { this.w[k] = v }, removeItem(k) { delete this.w[k] } };"
              "import('./src/lib/meten.js').then((m) => { const uit = [];"
              "m.meetZoekterm('bill gates chips', false); uit.push((window.factizMeten || []).length);"
              "localStorage.setItem(m.SLEUTEL, 'ja');"
              "m.meetZoekterm('Help little Ana who has cancer, share please', true); uit.push((window.factizMeten || []).length);"
              "m.meetZoekterm('bill gates chips', false); uit.push(window.factizMeten.length);"
              "m.meetZoekterm('bill gates chips', false); uit.push(window.factizMeten.length);"
              "console.log(JSON.stringify(uit)) })")
    assert _node(script) == [0, 0, 1, 1]       # dezelfde vraag twee keer na elkaar telt één keer


def test_analytics_loads_only_from_google_itself_after_a_yes_with_signals_and_ads_off():
    """AC2 en B88 punt 3: het script van Google zelf (nooit via factiz.org), Google signals en advertenties uit."""
    meten = (BRON / "lib" / "meten.js").read_text(encoding="utf-8")
    assert "https://www.googletagmanager.com/gtag/js?id=" in meten
    for regel in ("allow_google_signals: false", "allow_ad_personalization_signals: false", "ad_storage: 'denied'",
                  "ad_user_data: 'denied'", "ad_personalization: 'denied'"):
        assert regel in meten, regel
    for pad in CODE:
        tekst = pad.read_text(encoding="utf-8")
        if "googletagmanager" in tekst or "google-analytics" in tekst:
            assert pad.name in {"meten.js", "astro.config.mjs"}, pad
    # het laden zit achter de keuze: alleen `laadAnalytics` maakt het script, en de banner roept het alleen bij ja aan
    banner = (BRON / "components" / "site" / "Meten.jsx").read_text(encoding="utf-8")
    assert re.search(r"if \(k === 'ja'\) laadAnalytics\(id\)", banner)
    assert meten.count("createElement('script')") == 1


def test_the_banner_offers_yes_and_no_alike_and_no_after_yes_wipes_the_cookies():
    """AC1, AC2: ja en nee even groot en even makkelijk; wie na ja nee kiest, krijgt de cookies van Analytics gewist."""
    banner = (BRON / "components" / "site" / "Meten.jsx").read_text(encoding="utf-8")
    knoppen = re.findall(r'<button type="button" className="([^"]+)" onClick=\{\(\) => kies\(\'(ja|nee)\'\)\}', banner)
    assert sorted(k for _, k in knoppen) == ["ja", "nee"] and len({c for c, _ in knoppen}) == 1
    assert "wisAnalytics(id)" in banner
    meten = (BRON / "lib" / "meten.js").read_text(encoding="utf-8")
    assert "export const SLEUTEL = 'factiz-meten';" in meten and "_ga" in meten and "ga-disable-" in meten


def test_without_a_measurement_id_there_is_no_banner_and_the_old_promise_stays():
    """AC1: zonder meet-ID (`FACTIZ_GA`) geen banner en niets van Google, en de voet en de privacypagina zeggen wat ze zeiden."""
    site = (BRON / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "meetId()" in site and "{ga && <Meten client:idle" in site
    assert "t(ga ? 'voet_meten' : 'voet_geen_cookies')" in site
    over = (BRON / "components" / "site" / "paginas" / "Over.astro").read_text(encoding="utf-8")
    assert "t(ga ? 'over_privacy_p1_meten' : 'over_privacy_p1')" in over and "{ga && <p" in over
    script = ("import('./src/lib/meetid.js').then((m) => { const uit = [];"
              "for (const w of [undefined, '', 'G-ABC123XY', 'UA-1234-1', 'G-<script>']) {"
              "if (w === undefined) delete process.env.FACTIZ_GA; else process.env.FACTIZ_GA = w; uit.push(m.meetId()) }"
              "console.log(JSON.stringify(uit)) })")
    assert _node(script) == [None, None, "G-ABC123XY", None, None]


def test_every_language_says_what_is_measured_why_and_how_to_say_no():
    """AC5: in vijftien talen de banner, de voet en de privacypagina."""
    for taal in TALEN:
        teksten = json.loads((WORTEL / "factiz_site" / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))["teksten"]
        for sleutel in ("meten_vraag", "meten_ja", "meten_nee", "meten_meer", "meten_aanpassen", "voet_meten",
                        "over_privacy_p1_meten", "over_privacy_meten"):
            assert teksten.get(sleutel), (taal, sleutel)
    nl = json.loads((WORTEL / "factiz_site" / "teksten" / "nl.json").read_text(encoding="utf-8"))["teksten"]
    for woord in ("Google Analytics", "geplakt bericht", "twee maanden", "VS", "nee"):
        assert woord in nl["over_privacy_meten"], woord


def _keuzes(gevallen: list[tuple[str | None, bool]]) -> list:
    """Per geval (wat er in de opslag staat, of de browser Global Privacy Control stuurt) wat `keuze()` zegt."""
    script = ("globalThis.window = globalThis; const opslag = { w: {}, getItem(k) { return this.w[k] ?? null }, "
              "setItem(k, v) { this.w[k] = v }, removeItem(k) { delete this.w[k] } }; globalThis.localStorage = opslag;"
              "import('./src/lib/meten.js').then((m) => { const uit = []; const nu = Date.now(), dag = 86400000;"
              f"for (const [waarde, gpc] of {json.dumps(gevallen)}) {{ opslag.w = {{}};"
              "Object.defineProperty(globalThis, 'navigator', { value: { globalPrivacyControl: gpc }, configurable: true });"
              "if (waarde !== null) opslag.setItem(m.SLEUTEL, waarde.replace(/DAGEN\\((\\d+)\\)/, (_, d) => String(nu - d * dag)));"
              "uit.push([m.keuze(), opslag.getItem(m.SLEUTEL)]) }"
              "console.log(JSON.stringify(uit)) })")
    return _node(script)


def test_a_choice_counts_for_a_year_then_the_question_comes_back():
    """PO 2026-11-24: een keuze geldt niet eeuwig. Na twaalf maanden vragen we opnieuw (de CNIL: hoogstens dertien); een
    keuze van vóór deze regel (alleen 'ja' of 'nee') telt vanaf nu."""
    uit = _keuzes([('{"k":"ja","t":DAGEN(300)}', False), ('{"k":"ja","t":DAGEN(400)}', False),
                   ('{"k":"nee","t":DAGEN(400)}', False), ("nee", False), ("onzin{", False)])
    assert [k for k, _ in uit] == ["ja", None, None, "nee", None]
    assert uit[1][1] is None and uit[2][1] is None                 # een verlopen keuze wordt gewist
    assert json.loads(uit[3][1])["k"] == "nee"                     # de oude vorm krijgt een datum


def test_global_privacy_control_counts_as_no_and_an_explicit_yes_still_wins():
    """Stuurt de browser Global Privacy Control, dan vragen we niets en meten we niet; wie zelf ja zegt, meet wel."""
    uit = _keuzes([(None, True), ('{"k":"ja","t":DAGEN(1)}', True), (None, False)])
    assert [k for k, _ in uit] == ["nee", "ja", None]
    assert uit[0][1] is None                                       # het signaal wordt niet als keuze opgeslagen


def test_the_analytics_cookies_expire_after_thirteen_months_not_two_years():
    meten = (BRON / "lib" / "meten.js").read_text(encoding="utf-8")
    m = re.search(r"COOKIE_SECONDEN = (\d+) \* 24 \* 3600", meten)
    assert m and 390 <= int(m.group(1)) <= 400 and "cookie_expires: COOKIE_SECONDEN" in meten


def test_the_banner_is_a_small_card_that_never_hides_the_end_of_the_page():
    """PO 2026-11-24 ("Hoe houden we hem toch subtiel"): op een groter scherm een kaart van 22rem in de hoek (in een taal van
    rechts naar links de andere hoek), op een telefoon compact onderaan; geen grijze laag; zolang ze er staat, krijgt de pagina
    onderaan ruimte zodat niets eronder verdwijnt (WCAG 2.4.11); inschuiven alleen zonder voorkeur voor minder beweging."""
    css = (BRON / "styles" / "site.css").read_text(encoding="utf-8")
    blok = css[css.index(".fz .fz-meten {"):]
    blok = blok[:blok.index("@keyframes fz-meten-in")]
    assert "width: 22rem" in blok and "inset-inline: auto 1.25rem" in blok and "margin: 0 auto" not in blok
    assert "prefers-reduced-motion: reduce" in blok and "animation: none" in blok
    assert "fz-overlay" not in blok and "backdrop" not in blok
    assert "html.fz-meten-open { scroll-padding-bottom: var(--fz-meten-ruimte" in css
    assert "html.fz-meten-open body.fz { padding-bottom: var(--fz-meten-ruimte" in css
    banner = (BRON / "components" / "site" / "Meten.jsx").read_text(encoding="utf-8")
    assert "classList.add('fz-meten-open')" in banner and "classList.remove('fz-meten-open')" in banner
    assert "'--fz-meten-ruimte'" in banner and "ResizeObserver" in banner


def test_the_link_in_the_banner_and_the_button_in_the_footer_are_easy_to_tap():
    """De mobiele meting vond de knop in de voet 20 px hoog; de link in de banner is een regel in de zin, met een groter
    tikvlak zonder de regelafstand te verstoren."""
    css = (BRON / "styles" / "site.css").read_text(encoding="utf-8")
    assert ".fz .fz-meten a.link { display: inline; min-height: 0; padding-block:" in css
    assert re.search(r"\.fz \.fz-meten-aanpassen \{[^}]*min-height: 2\.75rem", css)
    banner = (BRON / "components" / "site" / "Meten.jsx").read_text(encoding="utf-8")
    assert 'className="link fz-meten-aanpassen' in banner


def test_the_question_is_short_and_names_google_analytics_in_every_language():
    """Eén zin met wie meet en dat het cookies zet; de rest staat achter "What we measure". Een ander schrift telt meer of
    minder tekens, dus de grens is een veelvoud van het Engels (de oude vraag was 170 tekens)."""
    en = json.loads((WORTEL / "factiz_site" / "teksten" / "en.json").read_text(encoding="utf-8"))["teksten"]["meten_vraag"]
    assert len(en) <= 100 and "cookies" in en
    for taal in TALEN:
        vraag = json.loads((WORTEL / "factiz_site" / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))["teksten"]["meten_vraag"]
        assert "Google Analytics" in vraag and len(vraag) <= 1.75 * len(en), (taal, len(vraag))
