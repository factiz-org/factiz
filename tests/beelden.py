"""Deterministische testafbeeldingen voor de beeldtaken (etappe 4).

Fotoachtig genoeg om zich onder JPEG-hercompressie en bijsnijden te gedragen
zoals een echte screenshot: zachte verlopen met structuur eroverheen.
"""

import numpy as np
from PIL import Image, ImageDraw


def verloop(breedte=256, hoogte=256, horizontaal=True):
    as_x = np.linspace(0, 255, breedte, dtype=np.float32)
    as_y = np.linspace(0, 255, hoogte, dtype=np.float32)
    veld = (
        np.tile(as_x, (hoogte, 1))
        if horizontaal
        else np.tile(as_y[:, None], (1, breedte))
    )
    return Image.fromarray(veld.astype(np.uint8), mode="L").convert("RGB")


def vormen(seed, breedte=256, hoogte=256, horizontaal=True):
    """Verloop met een handvol vlakken erop — deterministisch per seed."""
    rng = np.random.default_rng(seed)
    afbeelding = verloop(breedte, hoogte, horizontaal)
    tekenaar = ImageDraw.Draw(afbeelding)
    for _ in range(6):
        x0, y0 = rng.integers(0, breedte - 60, 2)
        vlak = int(rng.integers(40, 90))
        kleur = tuple(int(waarde) for waarde in rng.integers(0, 256, 3))
        if rng.integers(0, 2):
            tekenaar.rectangle([x0, y0, x0 + vlak, y0 + vlak], fill=kleur)
        else:
            tekenaar.ellipse([x0, y0, x0 + vlak, y0 + vlak], fill=kleur)
    return afbeelding


def schaakbord(breedte=256, hoogte=256, vak=32):
    veld = np.indices((hoogte, breedte)).sum(axis=0) // vak % 2 * 255
    return Image.fromarray(veld.astype(np.uint8), mode="L").convert("RGB")


def jpeg_hercompressie(afbeelding, kwaliteit):
    """Slaat op als JPEG en leest terug — alles in het geheugen (DR3)."""
    import io

    buffer = io.BytesIO()
    afbeelding.convert("RGB").save(buffer, format="JPEG", quality=kwaliteit)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def bijsnijden(afbeelding, fractie):
    """Snijdt aan elke rand `fractie` van de afmeting weg."""
    breedte, hoogte = afbeelding.size
    dx, dy = int(breedte * fractie), int(hoogte * fractie)
    return afbeelding.crop((dx, dy, breedte - dx, hoogte - dy))


LETTERTYPE = "/System/Library/Fonts/Supplemental/Arial.ttf"


def kop_screenshot(regels, breedte=900, hoogte=260, korrel=False):
    """Screenshot-achtig beeld met een kop erin."""
    from PIL import ImageFont

    afbeelding = Image.new("RGB", (breedte, hoogte), "white")
    tekenaar = ImageDraw.Draw(afbeelding)
    lettertype = ImageFont.truetype(LETTERTYPE, 34)
    for nummer, regel in enumerate(regels):
        tekenaar.text((30, 40 + nummer * 60), regel, font=lettertype, fill="black")
    if korrel:
        rng = np.random.default_rng(0)
        veld = np.array(afbeelding, dtype=np.int16)
        veld += rng.integers(-18, 18, veld.shape, dtype=np.int16)
        afbeelding = Image.fromarray(np.clip(veld, 0, 255).astype(np.uint8))
    return afbeelding
