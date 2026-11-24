import pytest

from doublecheck.image_fingerprint import (
    UnknownHashVersionError,
    fingerprint_image,
    hamming_distance,
)
from doublecheck.search import ModelVersionMismatchError
from tests.beelden import bijsnijden, jpeg_hercompressie, schaakbord, verloop, vormen

VERSIE = "phash-64-v1"
# Sinds #4P.3 beschrijft config de PDQ-hash (256 bits, drempel 31). Dit bestand
# meet nog pHash, dus het pint zijn eigen drempel: 10 van 64 was de waarde die
# bij deze hash hoorde. Drempel en hashversie zijn één paar; de configwaarde
# lenen voor een ándere hash meet niets.
DREMPEL = 10


def test_different_images_above_threshold():
    drempel = DREMPEL
    paren = [
        (vormen(1), vormen(2)),
        (schaakbord(), vormen(3)),
        (verloop(), schaakbord()),
        (vormen(1), schaakbord()),
    ]

    for een, twee in paren:
        afstand = hamming_distance(
            fingerprint_image(een, VERSIE), fingerprint_image(twee, VERSIE)
        )
        assert afstand > drempel, f"visueel verschillende beelden op afstand {afstand}"


@pytest.mark.xfail(
    strict=True,
    reason="bekende pHash-blinde vlek: structuurloze beelden (kaal verloop, egaal"
    " vlak) comprimeren tot bijna identieke hashes — afstand 6 bij drempel 10."
    " Gemeld aan PO (PLAN.md #4.1, 2026-08-28); mitigatie hoort bij 4.4"
    " (detailarme invoer → geen beeldmatch).",
)
def test_featureless_images_are_also_distinguished():
    drempel = DREMPEL

    afstand = hamming_distance(
        fingerprint_image(verloop(horizontaal=True), VERSIE),
        fingerprint_image(verloop(horizontaal=False), VERSIE),
    )

    assert afstand > drempel


def test_identical_image_has_distance_zero():
    afbeelding = vormen(7)

    afstand = hamming_distance(
        fingerprint_image(afbeelding, VERSIE), fingerprint_image(afbeelding, VERSIE)
    )

    assert afstand == 0


def test_image_fingerprint_records_model_version():
    fingerprint = fingerprint_image(vormen(4), VERSIE)

    assert fingerprint.model_version == VERSIE
    assert len(fingerprint.hash_hex) == 16  # 64 bits hexadecimaal
    assert fingerprint.bits == 64


def test_distance_refuses_across_model_versions():
    een = fingerprint_image(vormen(5), VERSIE)
    twee = fingerprint_image(vormen(5), "phash-256-v1")

    with pytest.raises(ModelVersionMismatchError):
        hamming_distance(een, twee)


def test_unknown_hash_version_refuses():
    with pytest.raises(UnknownHashVersionError):
        fingerprint_image(vormen(6), "gedachtenlezer-v9")


def test_accepts_raw_bytes():
    import io

    buffer = io.BytesIO()
    vormen(8).save(buffer, format="PNG")

    uit_bytes = fingerprint_image(buffer.getvalue(), VERSIE)
    uit_object = fingerprint_image(vormen(8), VERSIE)

    assert uit_bytes.hash_hex == uit_object.hash_hex


def test_jpeg_q60_below_threshold():
    drempel = DREMPEL

    for seed in (1, 2, 3, 4):
        origineel = vormen(seed)
        na_whatsapp = jpeg_hercompressie(origineel, 60)

        afstand = hamming_distance(
            fingerprint_image(origineel, VERSIE),
            fingerprint_image(na_whatsapp, VERSIE),
        )
        assert afstand <= drempel, f"seed {seed}: hercompressie gaf afstand {afstand}"


def test_heavier_compression_stays_recognisable():
    drempel = DREMPEL

    for kwaliteit in (80, 60, 40, 25):
        afstand = hamming_distance(
            fingerprint_image(vormen(9), VERSIE),
            fingerprint_image(jpeg_hercompressie(vormen(9), kwaliteit), VERSIE),
        )
        assert afstand <= drempel, f"kwaliteit {kwaliteit}: afstand {afstand}"


@pytest.mark.xfail(
    strict=True,
    reason="pHash is niet bestand tegen 10% randafsnijding: afstand 14–20 bij"
    " drempel 10. Alternatieven gemeten en afgewezen (zie PLAN.md #4.3);"
    " besluit ligt bij de PO — bevinding 2026-08-28.",
)
def test_crop_10pct_below_threshold():
    drempel = DREMPEL

    for seed in (1, 2, 3, 4, 5):
        afstand = hamming_distance(
            fingerprint_image(vormen(seed), VERSIE),
            fingerprint_image(bijsnijden(vormen(seed), 0.10), VERSIE),
        )
        assert afstand <= drempel, f"seed {seed}: bijsnijden gaf afstand {afstand}"


def test_mild_crop_stays_below_threshold():
    """Wat wél lukt: tot ~5% randafsnijding blijft binnen de drempel."""
    drempel = DREMPEL

    for seed in (1, 2, 3, 4, 5):
        afstand = hamming_distance(
            fingerprint_image(vormen(seed), VERSIE),
            fingerprint_image(bijsnijden(vormen(seed), 0.02), VERSIE),
        )
        assert afstand <= drempel, f"seed {seed}: afstand {afstand}"
