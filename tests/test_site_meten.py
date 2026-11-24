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
