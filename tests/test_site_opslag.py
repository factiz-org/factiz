"""Wat de site in de browser van een bezoeker bewaart (PLAN #34.2g, B75; docs/voorstellen/2026-11-12-b75-instellingen.md).

Alleen een instelling die de bezoeker zelf kiest, op het eigen apparaat, onder één sleutel per instelling, en dat staat bij
de knop en op de privacypagina. Geen cookie, geen andere opslag in de browser, en niets dat naar de server gaat.
"""

import json
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
BRON = WORTEL / "site" / "src"
CODE = sorted(p for p in BRON.rglob("*") if p.suffix in {".js", ".jsx", ".ts", ".astro", ".mjs"})
TALEN = ("en", "nl", "de", "es", "fr")


def test_the_site_keeps_nothing_in_the_browser_but_a_setting_the_visitor_chose():
    assert CODE
    for pad in CODE:
        tekst = pad.read_text(encoding="utf-8")
        assert not re.search(r"sessionStorage|indexedDB|caches\.open|sendBeacon|serviceWorker", tekst), pad
        # B88: de keuze over meten (`meten.js`, `Meten.jsx`), en alleen `meten.js` raakt cookies aan: om die van Analytics
        # te wissen als iemand na ja nee zegt
        if "document.cookie" in tekst:
            assert pad.name == "meten.js", pad
        if "localStorage" in tekst:
            assert pad.name in {"weergave.js", "Weergave.jsx", "meten.js", "Meten.jsx"}, pad


def test_the_one_key_holds_only_the_choice_and_system_removes_it():
    weergave = (BRON / "lib" / "weergave.js").read_text(encoding="utf-8")
    assert re.search(r"export const SLEUTEL = 'factiz-weergave';", weergave)
    knop = (BRON / "components" / "site" / "Weergave.jsx").read_text(encoding="utf-8")
    assert re.findall(r"localStorage\.setItem\(([^,]+),", knop) == ["SLEUTEL"]
    assert "localStorage.removeItem(SLEUTEL)" in knop and "if (w === 'systeem')" in knop
    assert re.search(r"const opties = \['systeem', 'licht', 'donker'\];", knop)
    # de keuze gaat nergens heen: geen fetch of formulier in de schakelaar en het stukje in de kop
    assert "fetch(" not in knop and "fetch(" not in weergave


def test_the_switch_and_the_privacy_page_say_where_the_choice_stays():
    for taal in TALEN:
        teksten = json.loads((WORTEL / "factiz_site" / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))["teksten"]
        assert teksten["weergave_hier"] and teksten["over_privacy_weergave"], taal
    assert "t('weergave_hier')" in (BRON / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "t('over_privacy_weergave')" in (BRON / "components" / "site" / "paginas" / "Over.astro").read_text(encoding="utf-8")


def test_a_newsroom_sees_only_that_the_visitor_came_from_factiz_never_which_page():
    """PLAN #34.2k: een link naar een redactie stuurt alleen de herkomst mee ("https://factiz.org/"), zodat zij in haar
    eigen statistieken ziet dat wij haar lezers brengen; nooit het pad, dus niet welke bewering iemand las. Binnen de site
    het hele adres (Terug naar resultaten kijkt waar je vandaan kwam)."""
    kop = (BRON / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert '<meta name="referrer" content="strict-origin-when-cross-origin">' in kop
    for pad in CODE:
        assert "noreferrer" not in pad.read_text(encoding="utf-8"), pad
    assert "t('over_privacy_herkomst')" in (BRON / "components" / "site" / "paginas" / "Over.astro").read_text(encoding="utf-8")
