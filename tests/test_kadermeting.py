"""De meting van #26.3: kaders die de knipregel nooit zag (PLAN #26.3)."""

import numpy as np
from PIL import Image

from doublecheck import kadermeting as km


def _foto(zaad=1, maat=(400, 300)):
    rng = np.random.default_rng(zaad)
    return Image.fromarray(rng.integers(0, 255, (maat[1], maat[0], 3), dtype=np.uint8))


def test_every_copy_keeps_the_photo_or_a_known_part_of_it():
    """Een kader legt de foto ongeschonden in een groter beeld; daar draait
    de meting om, dus dat moet echt zo zijn."""
    foto = _foto()
    for naam, maak in km.KOPIEEN.items():
        kopie = maak(foto)
        assert isinstance(kopie, Image.Image), naam
        if naam.startswith("kader"):
            assert kopie.width >= foto.width and kopie.height > foto.height, naam


def test_the_measurement_counts_every_query_once_per_method():
    beelden = [_foto(zaad=i) for i in range(6)]
    uit = km.meet(beelden[:3], beelden[3:], drempel=31)
    for methode in km.METHODEN:
        for soort in km.KOPIEEN:
            tel = uit["gevonden"][methode][soort]
            assert tel["goed"] + tel["fout"] + tel["niets"] == 3
        assert 0 <= uit["vals"][methode]["treffers"] <= uit["vals"][methode]["vragen"]


def test_the_embedding_threshold_is_set_on_one_half_and_tested_on_the_other():
    """De drempel komt uit de ene helft van de beelden buiten de index (geen
    enkele valse treffer daar); de valse treffers tellen op de andere helft."""
    index = [_foto(zaad=i) for i in range(3)]
    buiten = [_foto(zaad=i) for i in range(10, 14)]

    def vectoren(beelden):
        v = np.array([np.asarray(b.resize((8, 8))).astype(np.float32).ravel() for b in beelden])
        v -= v.mean(axis=1, keepdims=True)
        return {"klein": v / np.linalg.norm(v, axis=1, keepdims=True)}

    uit = km.meet_embedding(index, buiten, vectoren)["klein"]
    assert uit["drempel"] > 0
    assert uit["vals"]["vragen"] == 2 * (1 + len(km.KOPIEEN) + len(km.SNEDEN))
    for soort in list(km.KOPIEEN) + list(km.SNEDEN):
        tel = uit["gevonden"][soort]
        assert tel["goed"] + tel["fout"] + tel["niets"] == 3


def test_the_union_trusts_pdq_first_and_falls_back_on_the_embedding():
    """Bijna gelijke pixels zijn sterker bewijs dan een gelijkende
    beschrijving: wijzen ze verschillende beelden aan, dan wint PDQ (#26.3)."""
    kwargs = dict(drempel_pdq=31, drempel_dino=0.95)
    assert km.beslis((2, 10), (5, 0.99), **kwargs) == 2
    assert km.beslis((2, 40), (5, 0.99), **kwargs) == 5
    assert km.beslis((2, 40), (5, 0.90), **kwargs) is None
    assert km.beslis((2, 31), None, **kwargs) == 2       # alleen PDQ
    assert km.beslis(None, (5, 0.95), **kwargs) == 5     # alleen DINOv2


def test_the_combination_counts_every_query_once_per_variant():
    index = [_foto(zaad=i) for i in range(3)]
    buiten = [_foto(zaad=i) for i in range(10, 14)]

    def vectoren(beelden):
        v = np.array([np.asarray(b.resize((8, 8))).astype(np.float32).ravel() for b in beelden])
        v -= v.mean(axis=1, keepdims=True)
        return {"cls": v / np.linalg.norm(v, axis=1, keepdims=True)}

    uit = km.meet_combinatie(index, buiten, vectoren, drempel_pdq=31)
    assert set(uit) == set(km.VARIANTEN)
    for variant in km.VARIANTEN:
        assert uit[variant]["vals"]["vragen"] == 2 * (1 + len(km.KOPIEEN) + len(km.SNEDEN))
        for soort in list(km.KOPIEEN) + list(km.SNEDEN):
            tel = uit[variant]["gevonden"][soort]
            assert tel["goed"] + tel["fout"] + tel["niets"] == 3
    # Een opnieuw gecomprimeerde kopie vindt PDQ altijd; de vereniging dus ook.
    assert uit["pdq_of_dino"]["gevonden"]["jpeg60"]["goed"] == 3
