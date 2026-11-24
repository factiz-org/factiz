"""De keuzelijsten van de site (PLAN #34.2af, DESIGNSYSTEEM §4): één stijl voor de taalkeuze, de volgorde, het menu en
licht of donker. Regels die hun inhoud laten ademen, dezelfde zachte achtergrond onder de muis en bij het toetsenbord,
een zichtbare focus, en zacht openen behalve bij `prefers-reduced-motion`."""

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site" / "src"
CSS = re.sub(r"/\*.*?\*/", "", (SITE / "styles" / "site.css").read_text(encoding="utf-8"), flags=re.S)


def _regels(kiezer: str, css: str = CSS) -> list[str]:
    """De inhoud van elke regel waarvan de kiezer precies `kiezer` noemt (ook in een lijst met komma's)."""
    uit = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if kiezer in [k.strip() for k in m.group(1).split(",")]:
            uit.append(m.group(2))
    return uit


def _rem(waarde: str) -> float:
    m = re.fullmatch(r"([\d.]+)(rem|px)", waarde.strip())
    return float(m.group(1)) / (16 if m.group(2) == "px" else 1)


def test_a_choice_has_room_for_its_content_and_is_large_enough_to_tap():
    [basis] = [r for r in _regels(".fz-keuze") if "display: flex" in r]
    assert not re.search(r"(?<![-\w])height\s*:", basis), "een vaste hoogte laat twee regels in elkaar lopen"
    assert _rem(re.search(r"min-height:\s*([^;]+)", basis).group(1)) >= 2.25
    assert re.search(r"pointer:\s*coarse\)\s*\{\s*\.fz-keuze\s*\{\s*min-height:\s*2\.75rem", CSS)


def test_the_mouse_the_keyboard_and_radix_highlight_a_choice_the_same_way_and_focus_shows():
    achtergrond = {k: [r for r in _regels(k) if "background" in r] for k in
                   (".fz-keuze:hover", ".fz .fz-keuze:focus-visible", ".fz-keuze[data-highlighted]")}
    # geen rand om een regel: de algemene focusregel van de site (`.fz :focus-visible`) gaat er niet voor (PO 2026-11-13:
    # "deze border mag weg")
    assert any("outline: none" in r for r in _regels(".fz .fz-keuze:focus-visible"))
    assert all(achtergrond.values()), achtergrond
    # een link (taal, menu) krijgt een ring bij het toetsenbord; in een lijst van Radix toont de achtergrond waar je staat
    ring = " ".join(_regels("a.fz-keuze:focus-visible"))
    assert "outline" in ring or "box-shadow" in ring


def test_the_panel_has_round_corners_and_opens_softly_only_without_reduced_motion():
    [paneel] = [r for r in _regels(".fz-keuzes") if "border-radius" in r]
    assert "12px" in paneel and "padding: 6px" in paneel
    zacht = re.search(r"@media \(prefers-reduced-motion: no-preference\)\s*\{(.*?)\n\}", CSS, re.S).group(1)
    assert ".fz-keuzes" in zacht and "animation" in zacht
    assert not any("animation" in r for r in _regels(".fz-keuzes", CSS.replace(zacht, "")))


def test_the_chosen_value_carries_a_check_in_the_accent_colour_not_bold_text():
    assert any("var(--accent)" in r for r in _regels(".fz-keuze .keuze-vink"))
    assert not any("font-weight: 600" in r for r in _regels('.fz-keuze[data-state="checked"]'))
