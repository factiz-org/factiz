"""Een beeld opzoeken in de beeldindex (PLAN #32.15).

De index bewaart per beeld alleen hashes en een vector; een vraag brengt die van het hele beeld en van het beeldgebied
mee. PDQ gaat voor, DINOv2 beslist alleen boven zijn drempel, en kenmerken van een andere modelversie worden nooit
vergeleken (DR6). Een nepmodel staat in voor DINOv2, zodat de tests het echte model niet hoeven te laden.
"""

import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from doublecheck import beeldvraag as bv
from doublecheck.kadermeting import _kader_b


def _nep(beelden):
    """Een vector uit de grove kleurverdeling: hetzelfde beeld geeft dezelfde vector, een ander beeld een andere."""
    uit = []
    for b in beelden:
        klein = np.asarray(b.convert("RGB").resize((8, 16)), dtype=np.float32).ravel()
        v = klein - klein.mean()
        uit.append(v / (np.linalg.norm(v) or 1.0))
    return {"cls": np.vstack(uit), "vlakjes": np.vstack(uit)}


def _foto(zaad=1, maat=(640, 480)) -> Image.Image:
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, tuple(int(c) for c in rng.integers(0, 255, 3)))
    teken = ImageDraw.Draw(beeld)
    for _ in range(40):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.ellipse([x, y, x + rng.integers(20, 160), y + rng.integers(20, 160)],
                      fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def _bytes(beeld: Image.Image) -> bytes:
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _index(*beelden):
    kenmerken = [bv.indexkenmerken(b, vectoren=_nep) for b in beelden]
    return bv.Beeldindex.bouw([{"beeld": f"b{i}"} for i in range(len(beelden))], kenmerken)


def test_an_index_image_keeps_only_hashes_and_a_vector_never_the_pixels():
    k = bv.indexkenmerken(_bytes(_foto()), vectoren=_nep)
    assert len(k["pdq"]) == 4 and all(len(h) == 64 for h in k["pdq"])
    assert k["versies"] == bv.VERSIES and k["kwaliteit"] >= bv.MIN_KWALITEIT
    assert len(json.dumps(k)) < 2_500, "er hoort geen beeld in de kenmerken te zitten"


def test_a_screenshot_brings_its_image_area_as_a_second_query_and_a_photo_does_not():
    foto = _foto(2)
    assert len(bv.vraagkenmerken(foto, vectoren=_nep)["pdq"]) == 1
    post = bv.vraagkenmerken(_kader_b(foto), vectoren=_nep)
    assert len(post["pdq"]) == 2 and len(post["vectoren"]) == 2 and post["gebied"] is not None


def test_an_index_image_as_query_carries_the_same_features_as_asking_with_it():
    beeld = _kader_b(_foto(3))
    assert bv.vraag_uit_index(bv.indexkenmerken(beeld, vectoren=_nep)) == bv.vraagkenmerken(beeld, vectoren=_nep)


def test_pdq_goes_first_and_a_description_below_its_threshold_never_decides():
    assert bv.beslis((1, 20), (2, 0.99), drempel_pdq=31, drempel_dino=0.954) == 1
    assert bv.beslis((1, 40), (2, 0.95), drempel_pdq=31, drempel_dino=0.954) is None
    assert bv.beslis((1, 40), (2, 0.96), drempel_pdq=31, drempel_dino=0.954) == 2
    assert bv.beslis(None, None, drempel_pdq=31, drempel_dino=0.954) is None


def test_a_post_around_a_checked_image_finds_that_image():
    index = _index(_foto(1), _foto(2), _foto(3))
    treffer = bv.zoek(index, bv.vraagkenmerken(_kader_b(_foto(2)), vectoren=_nep), drempel_pdq=31, drempel_dino=0.954)
    assert treffer is not None and treffer["beeld"] == "b1"


def test_an_unrelated_image_finds_nothing():
    index = _index(_foto(1), _foto(2))
    assert bv.zoek(index, bv.vraagkenmerken(_foto(9), vectoren=_nep), drempel_pdq=31, drempel_dino=0.99) is None


def test_left_out_images_are_never_found():
    index = _index(_foto(1), _foto(2))
    vraag = bv.vraagkenmerken(_foto(2), vectoren=_nep)
    weg = np.array([False, True])
    assert bv.zoek(index, vraag, drempel_pdq=31, drempel_dino=0.99, uitsluiten=weg) is None
    r = bv.routes(index, vraag, weg)
    assert r["pdq"][0] == 0 and r["dino"][0] == 0


def test_features_of_another_model_version_are_never_compared():
    k = bv.indexkenmerken(_foto(1), vectoren=_nep)
    with pytest.raises(bv.Versiefout):
        bv.Beeldindex.bouw([{}], [{**k, "versies": {**k["versies"], "dino": "facebook/dinov2-base@x"}}])
    index = _index(_foto(1))
    vraag = bv.vraagkenmerken(_foto(1), vectoren=_nep)
    with pytest.raises(bv.Versiefout):
        bv.routes(index, {**vraag, "versies": {**vraag["versies"], "pdq": "pdq-256-v2"}})


def test_a_flat_image_never_takes_the_pdq_route():
    vlak = Image.new("RGB", (640, 480), (200, 200, 200))
    index = _index(vlak, _foto(1))
    assert set(index.eigenaar.tolist()) == {1}
    assert len(index.vectoren) == 2


def test_a_vector_survives_its_text_form_closely_enough_for_the_threshold():
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=384), rng.normal(size=384)
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    terug = [bv.vector_uit_tekst(bv.vector_naar_tekst(x)) for x in (a, b)]
    assert abs(float(terug[0] @ terug[1]) - float(a @ b)) < 1e-3


# --- panelen (#32.15 stap 2b) ------------------------------------------------------------------

from doublecheck import beelduitsnede as bu  # noqa: E402


def _collage(*beelden, gat=14, achtergrond=(255, 255, 255), rand=20):
    b = sum(x.width for x in beelden) + gat * (len(beelden) - 1) + 2 * rand
    h = max(x.height for x in beelden) + 2 * rand
    uit = Image.new("RGB", (b, h), achtergrond)
    x = rand
    for beeld in beelden:
        uit.paste(beeld, (x, rand))
        x += beeld.width + gat
    return uit


def _past(vak, links, boven, breedte, hoogte, marge=8):
    l, t, r, o = vak
    return abs(l - links) <= marge and abs(t - boven) <= marge and abs(r - links - breedte) <= marge \
        and abs(o - boven - hoogte) <= marge


def test_a_collage_of_two_photos_with_a_gap_falls_apart_into_its_two_photos():
    a, b = _foto(4, (420, 360)), _foto(5, (420, 360))
    vakken = bu.panelen(_collage(a, b))
    assert any(_past(v, 20, 20, 420, 360) for v in vakken)
    assert any(_past(v, 20 + 420 + 14, 20, 420, 360) for v in vakken)


def test_two_photos_glued_without_a_gap_are_cut_at_the_seam():
    a, b = _foto(6, (400, 360)), _foto(7, (400, 360))
    vakken = bu.panelen(_collage(a, b, gat=0, rand=0))
    assert any(_past(v, 0, 0, 400, 360) for v in vakken) and any(_past(v, 400, 0, 400, 360) for v in vakken)


def test_a_plain_photo_gives_no_panels_and_a_tiny_piece_never_counts():
    assert bu.panelen(_foto(8)) == []
    klein = _collage(_foto(9, (700, 500)), _foto(10, (60, 500)))
    assert all((v[2] - v[0]) >= 100 for v in bu.panelen(klein))
    assert len(bu.panelen(_collage(*[_foto(20 + i, (200, 300)) for i in range(12)], rand=4))) <= bu.MAX_PANELEN


def _index_met(*beelden, panelen=True):
    kenmerken = [bv.indexkenmerken(b, vectoren=_nep, panelen=panelen) for b in beelden]
    return bv.Beeldindex.bouw([{"beeld": f"b{i}"} for i in range(len(beelden))], kenmerken)


def test_a_photo_inside_a_collage_is_found_through_its_panel_and_not_without():
    foto = _foto(11, (420, 360))
    collage = _collage(_foto(12, (420, 360)), foto)
    vraag = bv.vraagkenmerken(foto, vectoren=_nep)
    met = _index_met(_foto(13), collage)
    zonder = _index_met(_foto(13), collage, panelen=False)
    assert bv.zoek(met, vraag, drempel_pdq=0, drempel_dino=0.97)["beeld"] == "b1"
    assert bv.zoek(zonder, vraag, drempel_pdq=0, drempel_dino=0.97) is None


def test_the_panels_of_a_left_out_image_are_left_out_too():
    foto = _foto(14, (420, 360))
    index = _index_met(_foto(15), _collage(_foto(16, (420, 360)), foto))
    vraag = bv.vraagkenmerken(foto, vectoren=_nep)
    assert bv.zoek(index, vraag, drempel_pdq=0, drempel_dino=0.97, uitsluiten=np.array([False, True])) is None


def test_panels_of_another_version_are_never_mixed_and_a_query_still_fits():
    k = [bv.indexkenmerken(_collage(_foto(17, (300, 300)), _foto(18, (300, 300))), vectoren=_nep, panelen=True)
         for _ in range(2)]
    k[1] = {**k[1], "panelen": {**k[1]["panelen"], "versie": "panelen-v0"}}
    with pytest.raises(bv.Versiefout):
        bv.Beeldindex.bouw([{}, {}], k)
    index = bv.Beeldindex.bouw([{}], k[:1])
    assert index.versies["panelen"] == bu.PANELEN
    bv.routes(index, bv.vraagkenmerken(_foto(17), vectoren=_nep))


def test_a_flat_panel_says_too_little_and_stays_out_of_the_index():
    y, x = np.mgrid[0:360, 0:400]
    vlak = Image.fromarray(np.stack([40 + x * 0.3, 40 + y * 0.4, 90 + x * 0.1], axis=2).astype(np.uint8))
    collage = _collage(_foto(19, (400, 360)), vlak, gat=0, rand=0)
    assert any(_past(v, 400, 0, 400, 360) for v in bu.panelen(collage)), "het knippen ziet het vlak wel"
    delen = bv.indexkenmerken(collage, vectoren=_nep, panelen=True)["panelen"]["delen"]
    assert any(bu._overlap(d["vak"], (0, 0, 400, 360)) > 0.8 for d in delen)
    assert not any(bu._overlap(d["vak"], (400, 0, 800, 360)) > 0.8 for d in delen)
    assert all(d["kwaliteit"] >= bv.MIN_KWALITEIT for d in delen)


# --- de punten als bevestiging (#32.17) -------------------------------------------------------------

def _blokken(zaad, maat=(640, 480)) -> Image.Image:
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, tuple(int(c) for c in rng.integers(0, 255, 3)))
    teken = ImageDraw.Draw(beeld)
    for _ in range(max(60, maat[0] * maat[1] // 5000)):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.rectangle([x, y, x + rng.integers(4, 60), y + rng.integers(4, 60)],
                        fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


BEVESTIG = {"drempel_pdq": 31, "min_punten": 50, "min_dekking": 0.10}


def test_points_carry_their_version_and_another_version_is_refused():
    k = bv.puntkenmerken(_blokken(1))
    assert k["versie"] == bv.PUNTVERSIE and k["des"].shape[1] == 128 and len(k["sterkte"]) == len(k["des"])
    with pytest.raises(bv.Versiefout):
        bv.puntvergelijking(k, {**k, "versie": "sift-1000-v0"})


def test_a_framed_and_stamped_copy_is_confirmed_by_points():
    foto = _blokken(2)
    kopie = _kader_b(foto)
    ImageDraw.Draw(kopie).ellipse([40, 40, 200, 200], outline=(220, 0, 0), width=12)
    assert bv.bevestigd(None, *bv.puntvergelijking(bv.puntkenmerken(kopie), bv.puntkenmerken(foto)), **BEVESTIG)


def test_a_shared_app_bar_is_never_a_confirmation():
    balk = _blokken(3, (640, 40))

    def post(zaad):
        uit = Image.new("RGB", (640, 640), (255, 255, 255))
        uit.paste(balk, (0, 0))
        uit.paste(_blokken(zaad, (640, 590)), (0, 50))
        return uit
    n, dekking = bv.puntvergelijking(bv.puntkenmerken(post(4)), bv.puntkenmerken(post(5)))
    assert n >= BEVESTIG["min_punten"], "de balk alleen geeft genoeg punten"
    assert not bv.bevestigd(None, n, dekking, **BEVESTIG), (n, dekking)


def test_confirmed_by_pdq_or_by_enough_points_over_enough_of_the_question():
    assert bv.bevestigd(31, 0, 0.0, **BEVESTIG)
    assert not bv.bevestigd(32, 49, 0.9, **BEVESTIG)
    assert bv.bevestigd(None, 50, 0.10, **BEVESTIG)
    assert not bv.bevestigd(None, 50, 0.099, **BEVESTIG)
    assert not bv.bevestigd(None, 49, 1.0, **BEVESTIG)


def test_the_strongest_points_are_the_strongest_and_keep_their_version():
    k = bv.puntkenmerken(_blokken(6, (900, 700)))
    s = bv.sterkste(k, 100)
    assert len(s["des"]) == len(s["xy"]) == len(s["sterkte"]) == 100 and s["versie"] == k["versie"]
    assert s["sterkte"].min() >= np.sort(k["sterkte"])[-100]
    assert s["maat"] == k["maat"]


def test_points_survive_the_way_to_disk_and_back_unchanged():
    k = bv.puntkenmerken(_blokken(7))
    terug = bv.punten_uit_bytes(bv.punten_naar_bytes(k))
    assert bv.puntvergelijking(k, terug)[0] == len(k["des"]) or bv.puntvergelijking(k, terug)[0] >= 0.9 * len(k["des"])
    assert np.array_equal(terug["des"], k["des"]) and np.array_equal(terug["xy"], k["xy"])
    assert terug["versie"] == k["versie"] and tuple(terug["maat"]) == tuple(k["maat"])


def test_a_whole_question_landing_on_one_clump_of_points_is_never_a_match():
    """§189: de vorm klapte in tot een punt (schaal 0), zodat 50 tot 90 punten van de vraag 'pasten' op één klont punten
    in een ander beeld. Elk punt hoort bij hoogstens één paar, en een ingeklapte vorm telt nooit."""
    rng = np.random.default_rng(8)
    des = rng.integers(0, 255, (120, 128)).astype(np.float32)
    vraag = {"versie": bv.PUNTVERSIE, "xy": rng.uniform(0, 600, (120, 2)).astype(np.float32), "des": des,
             "sterkte": np.ones(120, dtype=np.float32), "maat": (640, 640)}
    klont = np.full((120, 2), 300.0, dtype=np.float32) + rng.uniform(-0.4, 0.4, (120, 2)).astype(np.float32)
    index = {"versie": bv.PUNTVERSIE, "xy": klont, "des": des.copy(), "sterkte": np.ones(120, dtype=np.float32),
             "maat": (640, 640)}
    n, dekking = bv.puntvergelijking(vraag, index)
    assert not bv.bevestigd(None, n, dekking, **BEVESTIG), (n, dekking)
    # dezelfde punten op hun plaats, verschoven en verkleind: wel een treffer
    echt = {**index, "xy": (vraag["xy"] * 0.8 + 20).astype(np.float32)}
    assert bv.bevestigd(None, *bv.puntvergelijking(vraag, echt), **BEVESTIG)


# --- de opmaak eruit (#32.22) ---------------------------------------------------------------------------------------

def _opmaakbeeld(foto_zaad, stempel=True, balk=True, maat=(640, 640), plek=None):
    """Een deelbeeld zoals een redactie het maakt: een foto, met haar vaste balk onderaan en haar stempel erop."""
    uit = _blokken(foto_zaad, maat)
    if balk:
        uit.paste(_blokken(900, (maat[0], 70)), (0, maat[1] - 70))
    if stempel:
        uit.paste(_blokken(901, (170, 170)), plek or (maat[0] - 200, 30))
    return uit


def _andere(*zaden):
    """Per ander artikel de punten van zijn beelden; hier één beeld per artikel."""
    return [[bv.puntkenmerken(_opmaakbeeld(z))] for z in zaden]


def _in_opmaak(xy, maat=(640, 640)):
    return (xy[:, 1] >= maat[1] - 76) | ((xy[:, 0] >= maat[0] - 206) & (xy[:, 1] <= 206))


def test_a_stamp_and_bar_on_the_images_of_four_other_articles_are_layout_and_the_photo_is_not():
    beeld = bv.puntkenmerken(_opmaakbeeld(10))
    masker = bv.opmaakmasker(beeld, _andere(11, 12, 13, 14))
    opmaak = _in_opmaak(beeld["xy"])
    # met precies vier andere artikelen moet een punt in alle vier gevonden worden; in de echte referentie zijn het er
    # tot 79, en ziet de regel meer van de opmaak
    assert masker[opmaak].mean() >= 0.4, "het stempel en de balk zijn opmaak"
    assert masker[~opmaak].mean() <= 0.05, "de foto is geen opmaak"


def test_three_other_articles_are_not_enough_to_call_something_layout():
    beeld = bv.puntkenmerken(_opmaakbeeld(10))
    assert not bv.opmaakmasker(beeld, _andere(11, 12, 13)).any()


def test_a_shared_stamp_and_bar_no_longer_confirm_but_the_same_photo_still_does():
    vraag = bv.puntkenmerken(_opmaakbeeld(20))
    ander = bv.puntkenmerken(_opmaakbeeld(21))
    zelfde = bv.puntkenmerken(_opmaakbeeld(20))
    andere = _andere(11, 12, 13, 14, 15)
    voor = bv.puntvergelijking(vraag, ander)
    assert bv.bevestigd(None, *voor, **BEVESTIG), f"zonder de regel bevestigt de opmaak alleen al: {voor}"
    na = bv.puntvergelijking(vraag, bv.zonder_punten(ander, bv.opmaakmasker(ander, andere)))
    assert not bv.bevestigd(None, *na, **BEVESTIG), na
    blijft = bv.puntvergelijking(vraag, bv.zonder_punten(zelfde, bv.opmaakmasker(zelfde, andere)))
    assert bv.bevestigd(None, *blijft, **BEVESTIG), blijft


def test_points_without_layout_keep_their_version_and_size_and_only_lose_the_layout():
    k = bv.puntkenmerken(_opmaakbeeld(30))
    masker = np.zeros(len(k["des"]), dtype=bool)
    masker[:10] = True
    z = bv.zonder_punten(k, masker)
    assert z["versie"] == k["versie"] and tuple(z["maat"]) == tuple(k["maat"])
    assert len(z["des"]) == len(z["xy"]) == len(z["sterkte"]) == len(k["des"]) - 10
    assert np.array_equal(z["xy"], k["xy"][10:])


def test_layout_is_never_found_with_points_of_another_version():
    k = bv.puntkenmerken(_opmaakbeeld(31))
    with pytest.raises(bv.Versiefout):
        bv.opmaakmasker(k, [[{**a, "versie": "sift-1000-v0"}] for [a] in _andere(11, 12, 13, 14)])


def test_an_article_without_points_never_counts_as_another_article():
    k = bv.puntkenmerken(_opmaakbeeld(32))
    leeg = {"versie": bv.PUNTVERSIE, "xy": np.empty((0, 2), np.float32), "des": np.empty((0, 128), np.float32),
            "sterkte": np.empty(0, np.float32), "maat": (10, 10)}
    assert not bv.opmaakmasker(k, _andere(11, 12, 13) + [[leeg], []]).any()


def test_an_article_with_the_stamp_on_two_of_its_images_still_counts_once():
    """De ratiotoets op de samengevoegde punten van een artikel faalt als het stempel er twee keer in staat (twee even
    goede tegenhangers); daarom per beeld, en het artikel telt als een van zijn beelden het punt heeft."""
    beeld = bv.puntkenmerken(_opmaakbeeld(10))
    dubbel = [[bv.puntkenmerken(_opmaakbeeld(z)), bv.puntkenmerken(_opmaakbeeld(z + 50))] for z in (11, 12, 13, 14)]
    samen = [[{**a, "xy": np.vstack([a["xy"], b["xy"]]), "des": np.vstack([a["des"], b["des"]]),
               "sterkte": np.concatenate([a["sterkte"], b["sterkte"]])}] for a, b in dubbel]
    opmaak = _in_opmaak(beeld["xy"])
    assert bv.opmaakmasker(beeld, dubbel)[opmaak].mean() >= 0.4
    assert bv.opmaakmasker(beeld, samen)[opmaak].mean() <= 0.1, "samengevoegd ziet de ratiotoets het stempel niet"


# --- de opmaak op haar vaste plek (#32.23) ---------------------------------------------------------------------------

def _in_stempel(xy, links, boven, rand=6):
    return (xy[:, 0] >= links - rand) & (xy[:, 0] <= links + 170 + rand) & (xy[:, 1] >= boven - rand) \
        & (xy[:, 1] <= boven + 170 + rand)


def _stempels(plek, *zaden, maat=(640, 640)):
    return [[bv.puntkenmerken(_opmaakbeeld(z, balk=False, maat=maat, plek=plek))] for z in zaden]


def test_a_stamp_at_the_same_place_is_layout_and_at_another_place_it_is_not():
    beeld = bv.puntkenmerken(_opmaakbeeld(40, balk=False, plek=(440, 30)))
    stempel = _in_stempel(beeld["xy"], 440, 30)
    zelfde = bv.opmaakmasker(beeld, _stempels((440, 30), 41, 42, 43, 44), plek=bv.OPMAAK_PLEK)
    elders = _stempels((30, 400), 41, 42, 43, 44)
    assert zelfde[stempel].mean() >= 0.4, "op dezelfde plek is het stempel opmaak"
    assert bv.opmaakmasker(beeld, elders)[stempel].mean() >= 0.4, "zonder plek ziet opmaak-v1 het stempel overal"
    assert bv.opmaakmasker(beeld, elders, plek=bv.OPMAAK_PLEK)[stempel].mean() <= 0.05, "op een andere plek niet"


def test_text_that_recurs_at_other_places_is_not_layout_by_place():
    """Dezelfde letters staan in veel screenshots van een site, maar steeds ergens anders (§195)."""
    beeld = bv.puntkenmerken(_opmaakbeeld(50, balk=False, plek=(60, 60)))
    andere = [[bv.puntkenmerken(_opmaakbeeld(z, balk=False, plek=(60 + 90 * i, 60 + 80 * i)))]
              for i, z in enumerate((51, 52, 53, 54, 55), start=1)]
    assert bv.opmaakmasker(beeld, andere)[_in_stempel(beeld["xy"], 60, 60)].mean() >= 0.4
    assert not bv.opmaakmasker(beeld, andere, plek=bv.OPMAAK_PLEK).any()


def test_an_image_of_another_shape_never_counts_for_the_place():
    beeld = bv.puntkenmerken(_opmaakbeeld(60, maat=(640, 640)))
    breed = [[bv.puntkenmerken(_opmaakbeeld(z, maat=(640, 360), plek=(440, 30)))] for z in (61, 62, 63, 64)]
    assert not bv.opmaakmasker(beeld, breed, plek=bv.OPMAAK_PLEK).any()
    # binnen 5% van dezelfde vorm telt het beeld wel
    bijna = [[bv.puntkenmerken(_opmaakbeeld(z, maat=(640, 620), plek=(440, 30)))] for z in (61, 62, 63, 64)]
    assert bv.opmaakmasker(beeld, bijna, plek=bv.OPMAAK_PLEK)[_in_stempel(beeld["xy"], 440, 30)].mean() >= 0.4


def test_layout_by_place_never_removes_more_than_layout_by_count():
    beeld = bv.puntkenmerken(_opmaakbeeld(70))
    andere = _andere(71, 72, 73, 74, 75, 76) + _stempels((30, 400), 77, 78)
    v1, v2 = bv.opmaakmasker(beeld, andere), bv.opmaakmasker(beeld, andere, plek=bv.OPMAAK_PLEK)
    assert np.all(v2 <= v1) and v2.sum() < v1.sum()
    assert bv.OPMAAK_V2 == "opmaak-v2" and bv.OPMAAK_PLEK == 0.03 and bv.OPMAAK_VORM == 0.05


# --- de rest van de foto moet ook passen (#32.24) --------------------------------------------------------------------

def _grijs(beeld):
    return bv.grijs_voor_punten(beeld)


def _rest(vraag, index, opmaak=None):
    pv, pi = bv.puntkenmerken(vraag), bv.puntkenmerken(index)
    n, dekking, vorm = bv.puntvorm(pv, pi)
    assert bv.bevestigd(None, n, dekking, **BEVESTIG), f"de punten bevestigen al: {n, dekking}"
    xy = pi["xy"][opmaak(pi["xy"])] if opmaak else None
    return bv.restcontrole(_grijs(vraag), _grijs(index), vorm, opmaak_xy=xy)


def test_the_form_comes_from_the_very_same_comparison():
    vraag, index = bv.puntkenmerken(_blokken(80)), bv.puntkenmerken(_kader_b(_blokken(80)))
    n, dekking, vorm = bv.puntvorm(vraag, index)
    assert (n, dekking) == bv.puntvergelijking(vraag, index) and vorm.shape == (2, 3)
    leeg = {**vraag, "xy": vraag["xy"][:0], "des": vraag["des"][:0], "sterkte": vraag["sterkte"][:0]}
    assert bv.puntvorm(vraag, leeg) == (0, 0.0, None), "zonder vorm geen vorm"


def test_the_same_photo_with_a_stamp_and_a_bar_keeps_its_confirmation():
    foto = _blokken(82)
    deel = _kader_b(foto)
    deel.paste(_blokken(901, (170, 170)), (40, 40))
    uit = _rest(foto, deel)
    assert uit["goed"] and uit["vakken"] >= 30, uit


def test_two_different_photos_with_the_same_pasted_logo_are_not_the_same_photo():
    # het logo beslaat een stuk van de foto, zoals een partijlogo of een geplakte vlag; de rest van de twee foto's verschilt
    logo = _blokken(902, (220, 220))
    a, b = _blokken(83), _blokken(84)
    a.paste(logo, (300, 200))
    b.paste(logo, (280, 180))
    uit = _rest(a, b)
    assert not uit["goed"] and uit["kloppen"] * 2 < uit["vakken"], uit


def test_flat_squares_and_layout_squares_never_count():
    vraag = Image.new("RGB", (640, 480), (255, 255, 255))
    vraag.paste(_blokken(85, (320, 240)), (0, 0))
    uit = _rest(vraag, vraag.copy())
    assert uit["vakken"] <= 18, "het witte deel zegt niets"
    alles_opmaak = _rest(vraag, vraag.copy(), opmaak=lambda xy: np.ones(len(xy), dtype=bool))
    assert alles_opmaak["vakken"] < uit["vakken"]


def test_too_few_squares_to_judge_is_never_a_confirmation():
    vraag = Image.new("RGB", (640, 480), (255, 255, 255))
    vraag.paste(_blokken(86, (75, 55)), (0, 0))
    pv = bv.puntkenmerken(vraag)
    uit = bv.restcontrole(_grijs(vraag), _grijs(vraag), np.float32([[1, 0, 0], [0, 1, 0]]))
    assert uit["vakken"] < bv.REST_VAKKEN and not uit["goed"], (uit, len(pv["des"]))
    assert bv.REST == "rest-v1"


def test_the_pixels_for_the_rest_check_are_in_the_frame_of_the_points():
    groot = _blokken(87, (2000, 1200))
    assert _grijs(groot).shape[::-1] == tuple(bv.puntkenmerken(groot)["maat"])
