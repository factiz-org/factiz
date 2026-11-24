"""Het beeldgebied uit een screenshot, en hashen op uitsneden (PLAN #26.3).

Een gebruiker stuurt een screenshot van een post: het virale beeld in een
kader met tekst en knoppen. De hash van het hele screenshot vindt het beeld
nooit terug (BENCHMARK §88). Eerst het beeldgebied eruit knippen en dát
hashen; en aan de indexkant ook een paar uitsneden, tegen een bijgesneden
kopie. De hash van het hele beeld doet altijd mee, dus het wordt nooit
slechter dan nu.
"""

import numpy as np
from PIL import Image, ImageDraw

from doublecheck import beelduitsnede as bu
from doublecheck.beeldindex import _kader, afstand
from doublecheck.benchmark_images import render_claim
from doublecheck.image_fingerprint import pdq_met_kwaliteit

VERSIE = "pdq-256-v1"


def _foto(zaad=1, maat=(640, 480)):
    """Zoals een echte foto: een verloop met ruis eronder, nergens een
    volmaakt egaal vlak, en vormen erop."""
    rng = np.random.default_rng(zaad)
    b, h = maat
    verloop = np.linspace(60, 200, b)[None, :, None] + np.linspace(0, 40, h)[:, None, None]
    ruis = rng.normal(0, 6, (h, b, 3))
    basis = np.clip(verloop * np.array([0.8, 1.0, 1.2]) + ruis, 0, 255).astype(np.uint8)
    beeld = Image.fromarray(basis)
    teken = ImageDraw.Draw(beeld)
    for _ in range(60):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.ellipse([x, y, x + rng.integers(20, 160), y + rng.integers(20, 160)],
                      fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def _h(beeld):
    return bytes.fromhex(pdq_met_kwaliteit(beeld)[0])


def test_the_photo_is_cut_from_a_screenshot_frame():
    foto = _foto()
    kader = _kader(foto)                       # kop van 30% en voet van 12% eromheen
    links, boven, rechts, onder = bu.beeldgebied(kader)
    assert abs(boven - int(480 * 0.30)) <= 4 and abs(onder - (int(480 * 0.30) + 480)) <= 4
    assert links <= 4 and rechts >= 636


def test_an_image_without_a_frame_or_without_a_photo_is_left_alone():
    """Een foto zonder kader hoeft niet geknipt; een screenshot met alleen
    tekst heeft geen beeldgebied, en dan knippen we niets willekeurigs."""
    assert bu.beeldgebied(_foto()) is None
    assert bu.beeldgebied(render_claim("Een bewering die alleen uit tekst bestaat, zonder foto erin.")) is None


def test_the_cut_out_finds_the_original_where_the_whole_screenshot_does_not():
    foto, kader = _foto(), _kader(_foto())
    origineel = _h(foto)
    hashes = [bytes.fromhex(h) for h in bu.vraaghashes(kader, VERSIE)]
    assert len(hashes) == 2                                    # het hele beeld en de uitsnede
    assert afstand(hashes[0], origineel) > 31                  # zoals §88: het kader verslaat de hash
    assert afstand(hashes[1], origineel) <= 31


def test_a_cropped_copy_finds_one_of_the_index_cuts():
    foto = _foto(zaad=3)
    index = [bytes.fromhex(h) for h in bu.indexhashes(foto, VERSIE)]
    assert len(index) == len(bu.UITSNEDEN) + 1
    b, h = foto.size
    kopie = foto.crop((int(b * 0.1), int(h * 0.1), int(b * 0.9), int(h * 0.9)))
    vraag = _h(kopie)
    assert afstand(vraag, index[0]) > 31                       # tegen het hele beeld: mis
    assert min(afstand(vraag, x) for x in index[1:]) <= 31     # tegen een uitsnede: raak
