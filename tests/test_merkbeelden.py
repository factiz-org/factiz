"""Het logo op elke plek (PLAN #23.18, DESIGN §4h): het icoon van de site, de avatar, het beeld bij delen en het
woordmerk in kop en voet, allemaal uit de twee SVG's van de PO.

De beelden tekent één script uit de vormen in de SVG zelf (`doublecheck.merkbeelden`), zoals `velden`:
geen download, geen beeldmodel, en hetzelfde commando geeft dezelfde bytes. Deze tests tekenen alles opnieuw.
"""

import io
import re

import numpy as np
import pytest
from PIL import Image

from doublecheck import merkbeelden as mb

ORANJE = (0xFF, 0x59, 0x00)


def test_the_path_reader_follows_lines_and_closes_a_shape():
    vormen = mb.paden("M0 0H10V10L0 10Z")
    assert vormen == [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]


def test_the_path_reader_keeps_a_hole_as_its_own_shape_and_ends_a_curve_on_its_end_point():
    vormen = mb.paden("M0 0C1 2 3 4 5 6ZM7 7H8V8Z")
    assert len(vormen) == 2
    assert vormen[0][0] == (0.0, 0.0) and vormen[0][-2] == pytest.approx((5.0, 6.0))
    assert vormen[1][0] == (7.0, 7.0)


def test_an_unknown_path_command_is_refused_instead_of_drawn_wrong():
    with pytest.raises(ValueError):
        mb.paden("M0 0Q1 1 2 2Z")


def test_the_site_icon_is_the_logo_of_the_po():
    # één bestand: de site wijst naar het logo in `factiz_site/static/merk/` (PLAN #34.2f); het platform heeft sinds
    # stap 4 geen eigen pagina's meer
    wortel = mb.WORTEL
    assert '/static/merk/logo.svg' in (wortel / "site" / "src" / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert (wortel / "factiz_site" / "static" / "merk" / "logo.svg").is_file()


def test_the_logo_drawn_from_its_shapes_is_orange_with_white_ovals_and_round_corners():
    beeld = np.asarray(mb.teken(mb.LOGO.read_text(encoding="utf-8"), 340))
    assert beeld.shape == (340, 340, 4)
    assert beeld[0, 0, 3] == 0  # de hoek is afgerond, dus doorzichtig
    assert tuple(beeld[170, 20, :3]) == ORANJE and beeld[170, 20, 3] == 255  # links van de ovalen
    for x, y in ((117, 248), (150, 180), (178, 104)):  # het midden van elk ovaal, in de maat van 340
        assert tuple(beeld[y, x, :3]) == (255, 255, 255), (x, y)


def test_the_letters_of_the_wordmark_follow_the_text_colour_and_the_logo_keeps_its_own():
    inline = mb.inline_woordmerk()
    bron = mb.WOORDMERK.read_text(encoding="utf-8")
    assert re.findall(r' d="([^"]+)"', inline) == re.findall(r' d="([^"]+)"', bron)  # dezelfde vormen
    assert inline.count('fill="currentColor"') == 6  # f, a, c, t, i, z
    assert inline.count('fill="#FF5900"') == 1 and inline.count('fill="white"') == 3
    assert 'aria-hidden="true"' in inline and 'focusable="false"' in inline
    assert mb.INLINE.read_text(encoding="utf-8") == inline


def test_the_white_wordmark_differs_from_the_po_file_only_in_the_letters():
    wit = mb.woordmerk_wit()
    assert wit.replace('fill="white"', 'fill="black"').count('fill="black"') == \
        mb.WOORDMERK.read_text(encoding="utf-8").replace('fill="white"', 'fill="black"').count('fill="black"')
    assert 'fill="black"' not in wit
    assert re.findall(r' d="([^"]+)"', wit) == re.findall(r' d="([^"]+)"', mb.WOORDMERK.read_text(encoding="utf-8"))


@pytest.mark.parametrize("naam", sorted(mb.BEELDEN))
def test_every_brand_image_is_exactly_what_the_script_draws(naam):
    pad = mb.MERK / naam
    assert pad.read_bytes() == mb.BEELDEN[naam](), f"{naam}: draai python -m doublecheck.merkbeelden"




def test_the_avatar_fills_the_square_and_survives_a_round_crop():
    beeld = np.asarray(Image.open(mb.MERK / "avatar.png").convert("RGB")).astype(int)
    assert beeld.shape == (1024, 1024, 3)
    assert tuple(beeld[0, 0]) == ORANJE  # het volle vierkant, geen doorzichtige hoek
    wit = np.argwhere(beeld.min(axis=2) > 200)
    afstand = np.hypot(wit[:, 0] - 511.5, wit[:, 1] - 511.5)
    assert len(wit) and afstand.max() < 512 * 0.92  # elk wit punt ruim binnen de cirkel


def test_the_touch_icon_is_the_full_square_for_ios():
    beeld = Image.open(mb.MERK / "apple-touch-icon.png")
    assert beeld.size == (180, 180) and beeld.mode == "RGB"
    assert beeld.getpixel((0, 0)) == ORANJE


def test_the_old_favicon_file_carries_the_three_sizes_a_browser_asks_for():
    ico = Image.open(io.BytesIO((mb.MERK / "favicon.ico").read_bytes()))
    assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info["sizes"])


def test_the_share_image_is_the_corpus_crop_with_the_wordmark_in_white():
    beeld = np.asarray(Image.open(mb.MERK / "og.jpg").convert("RGB")).astype(int)
    assert beeld.shape == (630, 1200, 3)
    oranje = np.all(np.abs(beeld - ORANJE) < 30, axis=2)
    assert oranje.sum() > 5000  # het logo staat erop
    rijen, kolommen = np.nonzero(oranje)
    assert 200 < rijen.mean() < 430 and 300 < kolommen.mean() < 700  # links van het midden, in de hoogte gecentreerd
    letters = beeld[230:400, 560:950].min(axis=2) > 220
    assert letters.sum() > 3000  # de letters in wit


@pytest.mark.parametrize("naam", sorted(mb.GITHUB))
def test_every_github_image_is_exactly_what_the_script_draws(naam):
    """De social preview en de banner van het openbare repo (PLAN #34.2bl): getekend, niet geplakt."""
    pad = mb.GITHUB_MAP / naam
    assert pad.read_bytes() == mb.GITHUB[naam](), f"{naam}: draai python -m doublecheck.merkbeelden"


def test_the_social_preview_has_the_size_github_asks_for_and_stays_dark_behind_the_text():
    beeld = Image.open(mb.GITHUB_MAP / "social-preview.jpg").convert("RGB")
    assert beeld.size == (1280, 640) and (mb.GITHUB_MAP / "social-preview.jpg").stat().st_size < 1_000_000
    grond = np.asarray(beeld).astype(int)[40:400, 40:1240].mean()
    assert grond < 70, grond                                     # op donker: de tekst wit op een donkere grond
