"""Perceptuele beeldhash, altijd mét modelversie (E1.S2, DR6).

Zelfde vorm als de tekst-fingerprint: de hash en zijn versie zijn onlosmakelijk,
en vergelijken over versies heen weigert luid in plaats van stil door te rekenen.

Afbeeldingen worden uitsluitend in het geheugen geopend; er wordt nooit iets
naar schijf geschreven (DR3). Welke algoritmeversies bestaan staat hier, welke
er gebruikt wordt komt uit config.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import imagehash
from PIL import Image

from doublecheck.search import ModelVersionMismatchError


class UnknownHashVersionError(Exception):
    """Config vraagt een beeldhash-versie die deze code niet kent."""


# versie → (hash_size voor imagehash.phash, aantal bits)
_ALGORITMEN = {
    "phash-64-v1": (8, 64),
    "phash-256-v1": (16, 256),
}
# PDQ staat apart: het is geen imagehash-variant maar een eigen algoritme met een
# eigen bitlengte, en dus een eigen gelijkheidsdrempel (E1.S4, #4P.1). Toegevoegd
# omdat pHash 10% randafsnijding niet overleeft — afstand 14–20 bij drempel 10,
# en op schaal 249 van 250 gemist (BENCHMARK.md §9).
_PDQ_VERSIES = {"pdq-256-v1": 256}


@dataclass(frozen=True)
class ImageFingerprint:
    hash_hex: str
    model_version: str
    bits: int


# Een decompressiebom: klein op schijf, enorm ontvouwd. De byte-limiet in de API
# zegt niets over het aantal pixels — een PNG van 76 KB kan 400 megapixels
# worden, en dan kost één verzoek tientallen seconden OCR-werk. 12 MP dekt een
# 4K-schermafbeelding ruim (3840x2160 = 8,3 MP) en snijdt de bom af
# (veiligheidssweep 2026-08-31). De grens gaat over verwerkingskosten, niet over
# beeldkwaliteit: PDQ verkleint zelf naar 64x64 en OCR heeft geen 20 MP nodig.
MAX_IMAGE_PIXELS = 12_000_000


class TeGroteAfbeelding(ValueError):
    """De afbeelding heeft na decompressie te veel pixels om te verwerken."""


def as_image(bron) -> Image.Image:
    if isinstance(bron, Image.Image):
        _bewaak_pixels(bron)
        return bron
    if isinstance(bron, (bytes, bytearray)):
        # `Image.open` leest alleen de kop; de maat staat er dan al in, dus we
        # kunnen weigeren vóór het decoderen — het dure deel gebeurt niet.
        afbeelding = Image.open(io.BytesIO(bron))
        _bewaak_pixels(afbeelding)
        return afbeelding
    raise TypeError(f"kan geen afbeelding maken van {type(bron).__name__}")


def _bewaak_pixels(afbeelding: Image.Image) -> None:
    breedte, hoogte = afbeelding.size
    if breedte * hoogte > MAX_IMAGE_PIXELS:
        raise TeGroteAfbeelding(
            f"afbeelding is {breedte}x{hoogte} = {breedte * hoogte} pixels;"
            f" grens ligt op {MAX_IMAGE_PIXELS}"
        )


def pdq_met_kwaliteit(afbeelding: Image.Image) -> tuple[str, int]:
    """De PDQ-hash en de kwaliteit die PDQ er zelf bij geeft (0–100): een
    vlak of bijna leeg beeld geeft een hash die weinig zegt (#25.11)."""
    # Import hier, niet bovenaan: pdqhash is een C-extensie en hoort alleen
    # geladen te worden als er echt met PDQ gewerkt wordt.
    import numpy as np
    import pdqhash

    bits, kwaliteit = pdqhash.compute(np.asarray(afbeelding.convert("RGB")))
    getal = 0
    for bit in bits:
        getal = (getal << 1) | int(bit)
    return f"{getal:064x}", int(kwaliteit)


def _pdq_hex(afbeelding: Image.Image) -> str:
    return pdq_met_kwaliteit(afbeelding)[0]


def fingerprint_image(bron, model_version: str) -> ImageFingerprint:
    if model_version not in _ALGORITMEN and model_version not in _PDQ_VERSIES:
        raise UnknownHashVersionError(
            f"onbekende beeldhash-versie {model_version!r};"
            f" bekend: {sorted(_ALGORITMEN) + sorted(_PDQ_VERSIES)}"
        )
    afbeelding = as_image(bron).convert("RGB")
    if model_version in _PDQ_VERSIES:
        return ImageFingerprint(
            hash_hex=_pdq_hex(afbeelding),
            model_version=model_version,
            bits=_PDQ_VERSIES[model_version],
        )
    hash_size, bits = _ALGORITMEN[model_version]
    hash_waarde = imagehash.phash(afbeelding, hash_size=hash_size)
    return ImageFingerprint(
        hash_hex=str(hash_waarde), model_version=model_version, bits=bits
    )


def hamming_distance(een: ImageFingerprint, twee: ImageFingerprint) -> int:
    if een.model_version != twee.model_version:
        raise ModelVersionMismatchError(
            f"beeldhashes van verschillende versies: {een.model_version!r} en"
            f" {twee.model_version!r}; vergelijken over versies heen mag niet"
        )
    return (int(een.hash_hex, 16) ^ int(twee.hash_hex, 16)).bit_count()


def fingerprint_van_hex(hash_hex: str, model_version: str) -> ImageFingerprint:
    """Een door de client berekende hash inlezen (PROTOCOL §4, #11.1).

    Valideert streng: een fingerprint van de verkeerde lengte of met tekens die
    geen hex zijn, is geen fingerprint. Stil accepteren zou een vergelijking
    opleveren waarvan niemand de betekenis kent.
    """
    if model_version not in _ALGORITMEN and model_version not in _PDQ_VERSIES:
        raise UnknownHashVersionError(f"unknown image hash version {model_version!r}")
    bits = 256 if model_version in _PDQ_VERSIES else _ALGORITMEN[model_version].bits
    schoon = (hash_hex or "").strip().lower()
    if len(schoon) != bits // 4:
        raise ValueError(
            f"hash of {len(schoon)} characters; {model_version!r} expects {bits // 4}"
        )
    try:
        int(schoon, 16)
    except ValueError:
        raise ValueError("hash is geen hexadecimale tekenreeks") from None
    return ImageFingerprint(hash_hex=schoon, model_version=model_version, bits=bits)
