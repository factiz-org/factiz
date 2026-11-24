"""PDQ als crop-bestendige beeldhash (PLAN.md #4P.1, #4P.2, E1.S4).

Aanleiding: pHash haalt E1.S2-AC2 niet. Een 10% randafsnijding geeft afstand
14–20 bij drempel 10, en op schaal werd 249 van de 250 bijgesneden beelden
gemist (BENCHMARK.md §9). PDQ is de industriestandaard voor precies dit
probleem.

PDQ is 256 bits tegen pHash's 64, dus de gelijkheidsdrempel is een andere
grootheid. Drempel en hashversie horen bij elkaar en komen allebei uit config
(DR6); vergelijken over versies heen blijft verboden.
"""

import pytest
from PIL import Image

from doublecheck.image_fingerprint import (
    UnknownHashVersionError,
    fingerprint_image,
    hamming_distance,
)
from doublecheck.search import ModelVersionMismatchError
from tests.beelden import schaakbord, vormen

PDQ = "pdq-256-v1"
PHASH = "phash-64-v1"
# Drempel voor PDQ: 31 van 256, de canonieke waarde van het algoritme. Gemeten
# scheidt die netjes — varianten van hetzelfde beeld blijven eronder, en
# verschillende tekstkoppen liggen op 42–74 (§29b). Niet die van pHash: 256 bits
# is een andere grootheid dan 64.
DREMPEL = 31


def _snij(afbeelding, deel=0.10):
    breedte, hoogte = afbeelding.size
    dx, dy = int(breedte * deel), int(hoogte * deel)
    return afbeelding.crop((dx, dy, breedte - dx, hoogte - dy))


def test_pdq_version_is_registered_and_isolated():
    """De versie bestaat náást pHash en vergelijken ertussen weigert (DR6)."""
    beeld = vormen(1)
    pdq = fingerprint_image(beeld, PDQ)
    phash = fingerprint_image(beeld, PHASH)

    assert pdq.model_version == PDQ and pdq.bits == 256
    assert phash.model_version == PHASH and phash.bits == 64
    with pytest.raises(ModelVersionMismatchError):
        hamming_distance(pdq, phash)


def test_unknown_version_still_refuses():
    with pytest.raises(UnknownHashVersionError):
        fingerprint_image(vormen(1), "pdq-bestaat-niet")


@pytest.mark.xfail(
    strict=True,
    reason="E1.S4-AC1 gehaald? Nee — de aanname in de spec is weerlegd. PDQ is"
    " niet crop-toleranter dan pHash maar juist slechter: genormaliseerd 0,469"
    " tegen 0,250 bij 10% randafsnijding, oftewel praktisch willekeurig (0,5)."
    " Gemeten over drie beeldsoorten, met een positieve controle op schalen die"
    " wél slaagt (BENCHMARK.md §29a). PDQ is gebouwd voor hercompressie, schalen"
    " en spiegelen — niet voor bijsnijden.",
)
@pytest.mark.parametrize("seed", (1, 2, 3, 4, 5))
def test_pdq_crop_10pct_below_threshold(seed):
    """Blijft staan als historische bevinding, net als de pHash-xfail uit 4.3."""
    beeld = vormen(seed)
    afstand = hamming_distance(
        fingerprint_image(beeld, PDQ), fingerprint_image(_snij(beeld), PDQ)
    )
    assert afstand <= DREMPEL, f"seed {seed}: afstand {afstand}"


@pytest.mark.parametrize("kwaliteit", (90, 75, 60))
def test_pdq_survives_recompression(kwaliteit):
    import io

    beeld = vormen(7)
    buffer = io.BytesIO()
    beeld.save(buffer, format="JPEG", quality=kwaliteit)
    buffer.seek(0)

    afstand = hamming_distance(
        fingerprint_image(beeld, PDQ), fingerprint_image(buffer.getvalue(), PDQ)
    )
    assert afstand <= DREMPEL, f"kwaliteit {kwaliteit}: afstand {afstand}"


def test_pdq_still_separates_different_images():
    """Crop-tolerantie mag niet betekenen dat álles op elkaar lijkt."""
    afstand = hamming_distance(
        fingerprint_image(vormen(1), PDQ), fingerprint_image(schaakbord(), PDQ)
    )
    assert afstand > DREMPEL, f"verschillende beelden op afstand {afstand}"


def test_pdq_writes_nothing_to_disk(tmp_path, monkeypatch):
    """DR3 blijft gelden: alleen in het geheugen (E1.S2-AC3)."""
    monkeypatch.chdir(tmp_path)
    fingerprint_image(vormen(3), PDQ)
    assert list(tmp_path.iterdir()) == []


def test_grayscale_and_rgba_are_accepted():
    """PDQ krijgt een RGB-array; andere modi mogen niet omvallen."""
    for modus in ("L", "RGBA", "P"):
        beeld = vormen(2).convert(modus)
        assert fingerprint_image(beeld, PDQ).bits == 256


def test_pdq_separates_text_screenshots_where_phash_collides():
    """De echte reden voor de v1-inperking (E1.S2-AC5, BENCHMARK.md §9a).

    pHash zette verschillende koppen op afstand 0–6 van 64 — één paar zelfs op
    exact 0, identieke hashes voor andere tekst. Dat gaf 250 van 250 valse
    koppelingen op niet-geïndexeerde screenshots.
    """
    from PIL import ImageDraw

    def screenshot(tekst):
        beeld = Image.new("RGB", (640, 360), "white")
        tekenaar = ImageDraw.Draw(beeld)
        for regel, stuk in enumerate(tekst.split("|")):
            tekenaar.text((30, 40 + regel * 34), stuk, fill="black")
        return beeld

    koppen = [
        "Het vaccin bevat microchips|om mensen te volgen",
        "De zeespiegel daalt al|tien jaar wereldwijd",
        "Pfizer verzweeg duizend|doden tijdens de testfase",
    ]
    fingerprints = [fingerprint_image(screenshot(k), PDQ) for k in koppen]
    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            afstand = hamming_distance(fingerprints[i], fingerprints[j])
            assert afstand > DREMPEL, f"koppen {i}/{j} op afstand {afstand}"
