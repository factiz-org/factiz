"""De velden van de site: wazige kleurvelden met filmkorrel (PLAN.md #23.14, DESIGN §4h).

De beelden op factiz.org zijn geen foto's en geen werk van een beeldmodel. Dit
script tekent ze: lichtstrepen, opgeteld als licht, lang vervaagd in de
bewegingsrichting met een zachte gloed eromheen, licht vervormd zodat het
organisch oogt. Daarna het filmkarakter: zwart is nooit zwart, wit brandt zacht
af, een warme gloed lekt rond het felste licht, de hoeken zakken weg, en de
korrel zit het sterkst in de middentonen.

Elk veld heeft een vaste seed, dus hetzelfde commando geeft hetzelfde beeld
(`tests/test_velden.py`). Elk veld heeft ook tekstzones: daar blijft het rustig
en donker genoeg voor witte tekst, na de schaduwlaag die de pagina erover legt.

Het veld `corpus` is getekend uit de checks zelf: elk lichtspoor is een taal
van de index, van links naar rechts de maanden, en hoe feller, hoe meer checks
die maand. De tellingen staan in `velden_corpus.json`, zodat het beeld zonder
database opnieuw te tekenen is.

    python -m doublecheck.velden tellen   # de tellingen uit de database (alleen lezen)
    python -m doublecheck.velden          # alle basisvelden en HERKOMST-basis.md
"""

from __future__ import annotations

import io
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

VERSIE = "velden-v1"
WORTEL = Path(__file__).resolve().parent.parent
# Eén map voor de site en het platform (PLAN #34.2f): de basisvelden hier, met hun herkomst in HERKOMST-basis.md, en de
# velden per thema en dossier ernaast, met HERKOMST.md (`velden platform`).
UIT = WORTEL / "factiz_site" / "static" / "beeld"
HERKOMST_BASIS = UIT / "HERKOMST-basis.md"
DELEN = UIT / "delen.jpg"
TELLINGEN = Path(__file__).with_name("velden_corpus.json")
BEGIN = "2015-01"  # daarvoor staan 18 losse checks; die tekenen geen spoor
ONBEPAALD = "und"  # een taalcode, geen taal: die checks tekenen geen spoor

_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


@dataclass(frozen=True)
class Zone:
    """Waar witte tekst op het veld komt, als deel van breedte en hoogte
    (x0, y0, x1, y1), met het contrast dat hij moet halen en de dekking van
    de schaduwlaag die de pagina daar minstens over het veld legt."""

    naam: str
    vak: tuple[float, float, float, float]
    minimum: float
    schaduw: float


@dataclass(frozen=True)
class Veld:
    breedte: int
    hoogte: int
    seed: int
    zwart: str
    rust: float  # hoeveel het licht in de tekstzones gedempt wordt
    gebruik: str
    zones: tuple[Zone, ...]


_KAART = (Zone("kop", (0.10, 0.38, 0.90, 0.58), 3.0, 0.22), Zone("tekst", (0.06, 0.72, 0.94, 0.97), 4.5, 0.42))

VELDEN: dict[str, Veld] = {
    # De band ligt onder, de kop en de tekst erboven: zo blijft de tekst op
    # donker, ook als een smal scherm alleen het midden van het beeld toont.
    "corpus": Veld(2000, 900, 1, "#121316", 0.35, "bovenaan de homepage; een uitsnede is de afbeelding bij delen",
                   (Zone("balk", (0.0, 0.0, 1.0, 0.09), 4.5, 0.2), Zone("kop", (0.0, 0.10, 1.0, 0.46), 3.0, 0.2),
                    Zone("tekst", (0.0, 0.40, 1.0, 0.62), 4.5, 0.2))),
    "nacht": Veld(2000, 900, 3, "#14120f", 0.35, "de voet van elke pagina",
                  (Zone("kop", (0.15, 0.08, 0.85, 0.30), 3.0, 0.20), Zone("tekst", (0.15, 0.28, 0.85, 0.45), 4.5, 0.30),
                   Zone("kaart", (0.10, 0.50, 0.90, 0.95), 4.5, 0.40))),
    "groen": Veld(2000, 600, 11, "#0d1712", 0.45, "de band bovenaan de andere pagina's en op try.factiz.org",
                  (Zone("balk", (0.0, 0.0, 1.0, 0.20), 4.5, 0.30), Zone("kop", (0.0, 0.20, 0.70, 0.62), 3.0, 0.20),
                   Zone("tekst", (0.0, 0.60, 0.70, 0.95), 4.5, 0.30))),
    "hemel": Veld(900, 1125, 5, "#2a3340", 0.45, "de kaart Check a claim", _KAART),
    "olijf": Veld(900, 1125, 8, "#2a2a1e", 0.45, "de kaart Ask a question", _KAART),
    "leisteen": Veld(900, 1125, 21, "#15181c", 0.5, "de kaart The numbers en de blog", _KAART),
}


# --- bouwstenen ----------------------------------------------------------------

def _rgb(kleur: str) -> np.ndarray:
    kleur = kleur.lstrip("#")
    return np.array([int(kleur[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


def _vlak(w: int, h: int, kleur: str) -> np.ndarray:
    return np.ones((h, w, 3), np.float32) * _rgb(kleur)


def _verloop(w: int, h: int, boven: str, onder: str) -> np.ndarray:
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    return _rgb(boven) * (1 - t) + _rgb(onder) * t + np.zeros((h, w, 3), np.float32)


def _ruis1d(n: int, schaal: float, rng: np.random.Generator) -> np.ndarray:
    r = ndimage.gaussian_filter1d(rng.standard_normal(n).astype(np.float32), schaal, mode="wrap")
    return (r - r.min()) / (np.ptp(r) + 1e-6)


def _ruis2d(h: int, w: int, schaal: float, rng: np.random.Generator) -> np.ndarray:
    r = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), schaal, mode="wrap")
    return r / (np.abs(r).max() + 1e-6)


def _streep(licht: np.ndarray, rng: np.random.Generator, *, cx: float, cy: float, lengte: float, dikte: float,
            kleur: str, sterkte: float, buig: float = 0.0, staart: bool = True) -> None:
    """Eén lichtspoor dat breekt en zwelt over zijn lengte; met een staart
    begint het kort en loopt het lang uit naar rechts."""
    h, w, _ = licht.shape
    x = np.arange(w, dtype=np.float32)[None, :]
    y = np.arange(h, dtype=np.float32)[:, None]
    u = (x - cx) / (lengte / 2)
    if staart:
        u = np.where(u < 0, u * 2.2, u * 0.8)
    venster = np.clip(1 - u * u, 0, 1) ** 1.5
    breuk = 0.25 + 0.75 * _ruis1d(w, 40, rng)[None, :] ** 1.3
    zwel = 0.7 + 0.6 * _ruis1d(w, 90, rng)[None, :]
    midden = cy + buig * np.sin((x / w) * math.pi * 1.3 + cx / 300)
    band = np.exp(-0.5 * ((y - midden) / (dikte * zwel)) ** 2)
    tint = np.clip(_rgb(kleur) + 0.12 * (_ruis1d(w, 120, rng)[None, :, None] - 0.5), 0, 1)
    licht += (band * venster * breuk)[..., None] * tint * sterkte


def _vervaag(beeld: np.ndarray, sy: float, sx: float) -> np.ndarray:
    """Gaussisch vervagen. Een brede vervaging gaat op een verkleind beeld en
    wordt daarna weer vergroot: bij een veeg van honderden pixels zie je dat
    verschil niet, en het scheelt het meeste rekenwerk."""
    h, w, _ = beeld.shape
    fy, fx = max(1, int(sy // 6)), max(1, int(sx // 6))
    if fy == fx == 1:
        return np.stack([ndimage.gaussian_filter(beeld[..., k], (sy, sx), mode="reflect") for k in range(3)], -1)
    klein = ndimage.uniform_filter(beeld, (fy, fx, 1), mode="reflect")[fy // 2::fy, fx // 2::fx]
    uit = []
    for k in range(3):
        kanaal = ndimage.gaussian_filter(klein[..., k], (sy / fy, sx / fx), mode="reflect")
        uit.append(np.asarray(Image.fromarray(kanaal.astype(np.float32), "F").resize((w, h), Image.BILINEAR)))
    return np.stack(uit, -1)


def _gloed(licht: np.ndarray, sy: float, sx: float) -> np.ndarray:
    """Een scherpe kern plus een wijde nevel, zoals licht in een lens."""
    return 0.75 * _vervaag(licht, sy, sx) + 0.55 * _vervaag(licht, sy * 5, sx * 2.5)


def _vervorm(beeld: np.ndarray, sterkte: float, schaal: float, rng: np.random.Generator) -> np.ndarray:
    h, w, _ = beeld.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dy = sterkte * _ruis2d(h, w, schaal, rng)
    dx = sterkte * 0.5 * _ruis2d(h, w, schaal * 1.3, rng)
    return np.stack([ndimage.map_coordinates(beeld[..., k], [yy + dy, xx + dx], order=1, mode="reflect")
                     for k in range(3)], -1)


def _draai(beeld: np.ndarray, graden: float) -> np.ndarray:
    return np.stack([ndimage.rotate(beeld[..., k], graden, reshape=False, mode="reflect", order=1)
                     for k in range(3)], -1)


def _kleurrand(beeld: np.ndarray, px: int) -> np.ndarray:
    """Rood en blauw een paar pixels uit elkaar, zoals in een goedkope lens.
    Aan de rand herhaald, niet rondgeschoven: dat gaf een lijn langs de kant."""
    uit = beeld.copy()
    uit[..., 0] = ndimage.shift(beeld[..., 0], (0, px), mode="nearest", order=0)
    uit[..., 2] = ndimage.shift(beeld[..., 2], (0, -px), mode="nearest", order=0)
    return uit


def _licht_op(grond: np.ndarray, licht: np.ndarray, plafond: float = 1.2) -> np.ndarray:
    """Licht telt op zoals op film: nooit feller dan wit."""
    return 1 - (1 - grond) * (1 - np.clip(licht, 0, plafond))


def _masker(veld: Veld) -> np.ndarray:
    """De tekstzones als zacht vlak: 1 in een zone, naar 0 eromheen."""
    h, w = veld.hoogte, veld.breedte
    masker = np.zeros((h, w), np.float32)
    for zone in veld.zones:
        x0, y0, x1, y1 = zone.vak
        masker[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1
    # Zo zacht dat er geen rand of baan te zien is: een tiende van de lange kant.
    return _vervaag(np.repeat(masker[..., None], 3, -1), 0.1 * max(h, w), 0.1 * max(h, w))[..., 0]


def _analoog(beeld: np.ndarray, rng: np.random.Generator, zwart: str, korrel: float = 0.03,
             gloed: float = 0.08) -> np.ndarray:
    """Het filmkarakter (PO 2026-10-27: "in de visual een analoge, grainy
    look"): zwart is nooit zwart, wit brandt zacht af, het licht lekt amber in
    de emulsie, de hoeken zakken weg, en de korrel zit het sterkst in de
    middentonen, in klonten van twee groottes."""
    h, w, _ = beeld.shape
    fel = np.clip((beeld @ _LUMA - 0.55) / 0.45, 0, 1)
    beeld = beeld + gloed * ndimage.gaussian_filter(fel, 18)[..., None] * _rgb("#ff9a4a")
    boven = np.clip(beeld - 0.78, 0, None)
    beeld = np.minimum(beeld, 0.78) + 0.22 * (1 - np.exp(-boven / 0.22))
    beeld = _rgb(zwart) * (1 - beeld) + beeld * 0.98
    grijs = (beeld @ _LUMA)[..., None]
    beeld = grijs + 1.1 * (beeld - grijs)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    beeld = beeld * (1 - 0.16 * np.clip(r - 0.55, 0, 1) ** 1.4)[..., None]
    beeld = _vervaag(beeld, 0.7, 0.7)
    fijn = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 0.55)
    grof = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 1.4)
    klont = 0.7 * fijn / fijn.std() + 0.45 * grof / grof.std()
    kleur = np.stack([ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 0.8)
                      for _ in range(3)], -1)
    kleur /= kleur.std()
    lum = beeld @ _LUMA
    sterkte = korrel * (0.55 + 1.8 * lum * (1 - lum))
    return np.clip(beeld + sterkte[..., None] * (klont[..., None] + 0.22 * kleur), 0, 1)


# --- de zes velden ---------------------------------------------------------------

def _nacht(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Blauw en wit op bijna zwart, horizontale vegen die links ontspringen."""
    w, h = veld.breedte, veld.hoogte
    grond = _vlak(w, h, "#1d1b18")
    licht = np.zeros_like(grond)
    for _ in range(18):
        _streep(licht, rng, cx=rng.uniform(-0.19 * w, 0.55 * w), cy=h * (0.42 + 0.58 * rng.random() ** 0.8),
                lengte=rng.uniform(0.6 * w, 1.6 * w), dikte=rng.uniform(8, 34) * h / 900,
                kleur=str(rng.choice(["#4a78b0", "#86acd6", "#dfe7f0", "#3a5f8f", "#a9c3df"])),
                sterkte=rng.uniform(0.3, 0.75), buig=rng.uniform(-25, 25))
    for _ in range(8):
        _streep(licht, rng, cx=rng.uniform(-0.06 * w, 0.3 * w), cy=h * rng.uniform(0.05, 0.4),
                lengte=rng.uniform(0.3 * w, 0.7 * w), dikte=rng.uniform(6, 20) * h / 900,
                kleur=str(rng.choice(["#4a78b0", "#86acd6"])), sterkte=rng.uniform(0.2, 0.5))
    _streep(licht, rng, cx=0.05 * w, cy=0.97 * h, lengte=0.5 * w, dikte=18, kleur="#c9773a", sterkte=0.45)
    _streep(licht, rng, cx=0.1 * w, cy=0.84 * h, lengte=0.4 * w, dikte=14, kleur="#5f7a4a", sterkte=0.4)
    licht = _vervorm(_gloed(licht, 7, 90), 12, 90, rng) * (1 - veld.rust * rust)[..., None]
    return _kleurrand(_vervaag(_licht_op(grond, licht), 1.5, 4), 3)


def _groen(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Het merk: mint en wit op groen-zwart."""
    w, h = veld.breedte, veld.hoogte
    grond = _verloop(w, h, "#0c1712", "#10251c")
    licht = np.zeros_like(grond)
    for _ in range(24):
        _streep(licht, rng, cx=rng.uniform(0.2 * w, 1.2 * w), cy=h * rng.uniform(0.2, 1.0),
                lengte=rng.uniform(0.5 * w, 1.4 * w), dikte=rng.uniform(8, 36) * h / 900,
                kleur=str(rng.choice(["#2f9c72", "#7fd1ae", "#d8efe4", "#1f6f52", "#a8d8c2"])),
                sterkte=rng.uniform(0.2, 0.65), buig=rng.uniform(-50, 50) * h / 900)
    _streep(licht, rng, cx=0.95 * w, cy=0.95 * h, lengte=0.45 * w, dikte=16, kleur="#d6a54a", sterkte=0.35)
    licht = _vervorm(_gloed(licht, 8, 80), 34 * h / 900, 80, rng) * (1 - veld.rust * rust)[..., None]
    return _kleurrand(_vervaag(_licht_op(grond, licht), 1.5, 4), 3)


def _hemel(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Hemelsblauw met wolkachtige vegen, schuin."""
    w, h = veld.breedte, veld.hoogte
    grond = _verloop(w, h, "#5d88c4", "#7aa1d6")
    licht = np.zeros_like(grond)
    for _ in range(22):
        _streep(licht, rng, cx=rng.uniform(-200, w + 200), cy=h * rng.uniform(0.15, 1.0),
                lengte=rng.uniform(0.4 * w, 1.1 * w), dikte=rng.uniform(12, 45),
                kleur=str(rng.choice(["#eef2f8", "#dfe6f2", "#f3dcc4", "#cfe0d6"])),
                sterkte=rng.uniform(0.15, 0.5), buig=rng.uniform(-30, 30), staart=False)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for kleur, fx, fy, r, a in (("#f1f4f9", 0.25, 0.22, 240, 0.3), ("#f4dcc2", 0.05, 0.62, 160, 0.3),
                                ("#d8e6dc", 0.35, 0.68, 200, 0.2), ("#eef2f8", 0.9, 0.3, 220, 0.3)):
        wolk = np.exp(-(((xx - fx * w) / (r * 2.2)) ** 2 + ((yy - fy * h) / (r * 0.6)) ** 2) / 2)
        licht += wolk[..., None] * _rgb(kleur) * a
    licht = _vervorm(_draai(_gloed(licht, 14, 70), 12), 40, 90, rng) * (1 - veld.rust * rust)[..., None]
    beeld = _licht_op(grond, licht, 1.0) * (1 - 0.25 * rust)[..., None]
    return _vervaag(beeld, 2, 2)


def _olijf(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Olijfgroen met goud en een blauwe vlek, onscherp als blad in de zon."""
    w, h = veld.breedte, veld.hoogte
    beeld = _verloop(w, h, "#6f7850", "#7d7c55")
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for kleur, fx, fy, r in (("#5c8fc8", 0.85, 0.12, 170), ("#d6a640", 0.8, 0.62, 230), ("#e8cf86", 0.55, 0.28, 150),
                             ("#c79a92", 0.75, 0.8, 120), ("#6a7a4c", 0.15, 0.4, 260), ("#b8b39a", 0.45, 0.25, 160),
                             ("#d9a23a", 0.98, 0.85, 140)):
        vlek = np.exp(-(((xx - fx * w) / (r * 1.3)) ** 2 + ((yy - fy * h) / r) ** 2) / 2)[..., None]
        beeld = beeld * (1 - 0.8 * vlek) + _rgb(kleur) * 0.8 * vlek
    licht = np.zeros_like(beeld)
    for _ in range(10):
        _streep(licht, rng, cx=rng.uniform(0, w), cy=h * rng.uniform(0.2, 0.95), lengte=rng.uniform(0.4 * w, w),
                dikte=rng.uniform(15, 40), kleur=str(rng.choice(["#e8cf86", "#b8c4d6", "#d6a640"])), sterkte=0.25)
    beeld = _licht_op(beeld, _vervaag(licht, 10, 60), 1.0)
    beeld = _vervorm(_draai(_vervaag(beeld, 30, 60), -8), 40, 90, rng)
    return beeld * (1 - 0.3 * rust)[..., None]


def _leisteen(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Grijs en blauwzwart, schuine vegen als wind over water."""
    w, h = veld.breedte, veld.hoogte
    beeld = _verloop(w, h, "#7d838b", "#14181d")
    licht = np.zeros_like(beeld)
    for _ in range(55):
        y = h * rng.uniform(-0.05, 0.8)
        _streep(licht, rng, cx=rng.uniform(-100, w + 100), cy=y, lengte=rng.uniform(0.5 * w, 1.6 * w),
                dikte=rng.uniform(6, 34), kleur=str(rng.choice(["#c9ced6", "#e5e8ec", "#8d96a3", "#aab4c2"])),
                sterkte=rng.uniform(0.15, 0.5) * (1 - y / h) ** 0.7, buig=rng.uniform(-12, 12))
    licht = _vervorm(_draai(_gloed(licht, 5, 60), -13), 8, 60, rng) * (1 - veld.rust * rust)[..., None]
    beeld = beeld * (1 - 0.35 * np.clip(_vervaag(licht, 20, 20), 0, 1))  # schaduw tussen de vegen
    return _licht_op(beeld, licht, 1.0) * (1 - 0.2 * rust)[..., None]


# Kleur per schrift: wat bij elkaar hoort, licht in dezelfde tint. Nooit rood.
_SCHRIFTKLEUR = {"latijn": "#9cbde3", "indisch": "#e2b45c", "arabisch": "#6fc7a8", "cyrillisch": "#b9b3e8",
                 "oost": "#f0d9c0", "overig": "#c6d2dc"}
_SCHRIFT = {**{t: "indisch" for t in "hi bn ta te ml kn mr gu pa si as or ne".split()},
            **{t: "arabisch" for t in "ar fa ur ps ku".split()},
            **{t: "cyrillisch" for t in "ru uk bg sr mk be kk mn".split()},
            **{t: "oost" for t in "zh ja ko th my km lo".split()},
            **{t: "overig" for t in "he am el ka hy".split()}}


def _corpus(veld: Veld, rng: np.random.Generator, rust: np.ndarray) -> np.ndarray:
    """Een lange sluitertijd op het geheugen: elk spoor een taal, de tijd van
    links naar rechts, de helderheid het aantal checks per maand."""
    tellingen = lees_tellingen()
    w, h = veld.breedte, veld.hoogte
    talen = sorted(tellingen["talen"], key=lambda t: (-sum(tellingen["talen"][t]), t))
    volgorde = talen[0::2][::-1] + talen[1::2]  # de grote talen in het midden
    grootste = sum(tellingen["talen"][talen[0]])
    maanden = len(tellingen["maanden"])
    grond = _vlak(w, h, "#121418")
    licht = np.zeros_like(grond)
    x = np.arange(w, dtype=np.float32)
    y = np.arange(h, dtype=np.float32)[:, None]
    for i, taal in enumerate(volgorde):
        reeks = np.log1p(np.array(tellingen["talen"][taal], np.float32)) / np.log1p(1200)
        waarde = np.interp(x, np.linspace(-0.02 * w, 1.02 * w, maanden), reeks)
        cy = h * (0.66 + 0.28 * i / max(len(volgorde) - 1, 1))
        dikte = (4 + 8 * (sum(tellingen["talen"][taal]) / grootste) ** 0.4) * h / 900
        buig = 22 * h / 900 * np.sin(x / w * math.pi * 1.1 + i * 0.35)
        band = np.exp(-0.5 * ((y - cy - buig[None, :]) / dikte) ** 2)
        licht += (band * waarde[None, :])[..., None] * _rgb(_SCHRIFTKLEUR[_SCHRIFT.get(taal, "latijn")]) * 0.9
    licht = _gloed(licht, 5, 34)
    nevel = _vervaag(licht, 0.12 * h, 0.2 * w)  # het licht dat in de lucht blijft hangen
    licht = _vervorm(licht + 0.9 * nevel, 18, 70, rng) * (1 - veld.rust * rust)[..., None]
    return _kleurrand(_vervaag(_licht_op(grond, licht * 1.15, 1.3), 1, 3), 2)


_TEKENAARS: dict[str, Callable[[Veld, np.random.Generator, np.ndarray], np.ndarray]] = {
    "corpus": _corpus, "nacht": _nacht, "groen": _groen, "hemel": _hemel, "olijf": _olijf, "leisteen": _leisteen,
}


def _teken(veld: Veld, familie: str) -> np.ndarray:
    vorm, korrel = (np.random.default_rng([veld.seed, stroom]) for stroom in (0, 1))
    return _analoog(_TEKENAARS[familie](veld, vorm, _masker(veld)), korrel, veld.zwart)


def teken(naam: str) -> np.ndarray:
    """Het veld als getallen van 0 tot 1, vóór het opslaan. Twee aparte
    stromen uit de seed: één voor de vorm, één voor de korrel. Een naam van het
    platform (`thema-…-band`, `dossier-…-kaart`) tekent met de tekenaar van zijn
    familie."""
    if naam in VELDEN:
        return _teken(VELDEN[naam], naam)
    familie, veld = platform_velden()[naam]
    return _teken(veld, familie)


# --- de velden van het platform (PLAN #33.6d, DESIGN §4w) ------------------------------
#
# Het platform (`factiz_site/`) leent geen code uit het lab, dus het draagt zijn eigen kopie van de beelden. Drie zijn
# dezelfde als op factiz.org (de start, de band, de voet); daarbij heeft elk thema en elk dossier een eigen veld, als
# band en als kaart, met een tekenaar uit de vijf families en een eigen seed. De familie zegt niets over waar of onwaar:
# zij maakt een plek herkenbaar, en de naam staat er altijd in tekst bij.

PLATFORM_UIT = WORTEL / "factiz_site" / "static" / "beeld"
PLATFORM_CSS = WORTEL / "factiz_site" / "static" / "velden.css"
THEMAS = WORTEL / "content" / "themas.json"
DOSSIERS = WORTEL / "content" / "dossiers"
GEDEELD = ("corpus", "nacht", "groen")
GEDEELD_GEBRUIK = {"corpus": "bovenaan de start, met het zoekveld", "nacht": "de voet",
                   "groen": "de band van de pagina's zonder eigen veld"}
BAND = (2000, 600)
KAART = (900, 1125)

# De band: de kop van de site bovenaan over de hele breedte, het kruimelpad, het label en de kop links. De pagina legt er
# een egale sluier van 0,4 over (`.kaartveld` in `site/src/styles/site.css`, onderaan 0,55).
_BAND = (Zone("balk", (0.0, 0.0, 1.0, 0.22), 4.5, 0.4), Zone("tekst", (0.0, 0.18, 0.72, 0.96), 4.5, 0.4))

# Per thema een familie en een seed. Een seed blijft bij zijn thema, ook als de volgorde van de lijst verandert.
# De familie is ook de kleur van de tegel van het thema op de site (PLAN #34.2ag, `site/src/components/site/ThemaTegel.jsx`):
# macht (leisteen), conflict en veiligheid (nacht), gezondheid en wetenschap (groen), geld en aarde (olijf), mensen
# (hemel). `tests/test_site_themakleur.py` eist dat ze gelijk blijven.
THEMA_VELDEN: dict[str, tuple[str, int]] = {
    "politics": ("leisteen", 101), "elections": ("leisteen", 102), "war": ("nacht", 103), "world": ("leisteen", 104),
    "health": ("groen", 105), "crime": ("nacht", 106), "economy": ("olijf", 107), "disasters": ("nacht", 108),
    "climate": ("olijf", 109), "migration": ("hemel", 110), "society": ("hemel", 111), "science": ("groen", 112),
    "people": ("hemel", 113),
}
STANDAARD_FAMILIE = "groen"  # een dossier zonder bekend thema


def _dossier_thema(map_: Path) -> str | None:
    import tomllib

    with (map_ / "dossier.toml").open("rb") as f:
        return tomllib.load(f).get("thema")


# een dossier waarvan het veld uit de sleutel ergens te licht is voor witte tekst, krijgt een vaste andere seed (§4h)
DOSSIER_SEEDS = {"migranten-zondebok": 2000}


def dossier_seed(sleutel: str) -> int:
    """Vast per dossier, uit de sleutel: hetzelfde dossier krijgt altijd hetzelfde beeld."""
    import zlib

    return DOSSIER_SEEDS.get(sleutel, 1000 + zlib.crc32(sleutel.encode("utf-8")) % 9000)


def _platformveld(familie: str, seed: int, maat: tuple[int, int], gebruik: str) -> Veld:
    basis = VELDEN[familie]
    zones = _BAND if maat == BAND else _KAART
    return Veld(maat[0], maat[1], seed, basis.zwart, basis.rust, gebruik, zones)


def platform_velden(themas: Path = THEMAS, dossiers: Path = DOSSIERS) -> dict[str, tuple[str, Veld]]:
    """Elk thema van `content/themas.json` en elk dossier in `content/dossiers/`, als band en als kaart."""
    uit: dict[str, tuple[str, Veld]] = {}
    sleutels = [t["sleutel"] for t in json.loads(themas.read_text(encoding="utf-8"))["themas"]]
    for sleutel in sleutels:
        familie, seed = THEMA_VELDEN[sleutel]
        uit[f"thema-{sleutel}-band"] = (familie, _platformveld(familie, seed, BAND, f"de band van het thema {sleutel}"))
        uit[f"thema-{sleutel}-kaart"] = (familie, _platformveld(familie, seed, KAART, f"de kaart van het thema {sleutel}"))
    for map_ in sorted(p for p in dossiers.iterdir() if (p / "dossier.toml").exists()):
        familie = THEMA_VELDEN.get(_dossier_thema(map_) or "", (STANDAARD_FAMILIE, 0))[0]
        seed = dossier_seed(map_.name)
        uit[f"dossier-{map_.name}-band"] = (familie, _platformveld(familie, seed, BAND, f"de band van het dossier {map_.name}"))
        uit[f"dossier-{map_.name}-kaart"] = (familie, _platformveld(familie, seed, KAART, f"de kaart van het dossier {map_.name}"))
    return uit


KLEIN_MAAT = (800, 240)


def kleine_velden(namen) -> dict[str, str]:
    """De kleine versie van elke themaband, voor de kaarten op de start en het overzicht (PLAN #34.2bq: de band is
    2000×600 en ~120 KB, op een kaart van een paar honderd pixels): naam → de band waaruit ze verkleind is."""
    return {f"{n[:-5]}-klein": n for n in namen if n.startswith("thema-") and n.endswith("-band")}


def klein_webp(band: Path) -> bytes:
    with Image.open(band) as beeld:
        klein = beeld.convert("RGB").resize(KLEIN_MAAT, Image.LANCZOS)
    buf = io.BytesIO()
    klein.save(buf, "WEBP", quality=80, method=6)
    return buf.getvalue()


def platform_css(namen: list[str]) -> str:
    """Eén regel per veld: de klasse zet het beeld, de opmaak van de site (`site.css`) doet de rest. Thema's eerst, dossiers
    daarna, zodat een dossier met beide klassen zijn eigen beeld krijgt en anders dat van zijn thema. De kleine versies
    van de themabanden staan erbij (`kleine_velden`)."""
    namen = [*namen, *kleine_velden(namen)]
    regels = ["/* Gemaakt door `python -m doublecheck.velden platform` (PLAN #33.6d, DESIGN §4w). Niet met de hand",
              "   bewerken: de beelden en hun herkomst staan in static/beeld/. */"]
    regels += [f".veld-{naam} {{ --beeld: url(/static/beeld/{naam}.webp); }}" for naam in GEDEELD]
    for naam in sorted(namen, key=lambda n: (not n.startswith("thema-"), n)):
        sleutel, vorm = naam.rsplit("-", 1)
        regels.append(f".veld-{vorm}-{sleutel} {{ --beeld: url(/static/beeld/{naam}.webp); }}")
    return "\n".join(regels) + "\n"


def maak_platform(uit: Path = PLATFORM_UIT) -> list[Path]:
    """Elk veld van het platform, velden.css en HERKOMST.md. De drie gedeelde beelden zijn de basisvelden zelf, in
    dezelfde map (sinds PLAN #34.2f geen kopie meer)."""
    uit.mkdir(parents=True, exist_ok=True)
    regels, paden = [], []
    for naam in GEDEELD:
        pad = uit / f"{naam}.webp"
        if uit != UIT:
            pad.write_bytes((UIT / f"{naam}.webp").read_bytes())
        regels.append(f"- `{pad.name}`: het basisveld (seed {VELDEN[naam].seed}, `HERKOMST-basis.md`); "
                      f"{GEDEELD_GEBRUIK[naam]}.")
        paden.append(pad)
    velden = platform_velden()
    for naam, (familie, veld) in velden.items():
        pad = uit / f"{naam}.webp"
        pad.write_bytes(webp(_teken(veld, familie)))
        pixels = np.asarray(Image.open(pad).convert("RGB"))
        zones = ", ".join(f"{z.naam} {contrast_wit(pixels, z):.1f}:1".replace(".", ",") for z in veld.zones)
        regels.append(f"- `{pad.name}`: familie {familie}, seed {veld.seed}, {veld.breedte}×{veld.hoogte}, "
                      f"{pad.stat().st_size // 1024} KB; {veld.gebruik}; wit in de tekstzones: {zones}.")
        paden.append(pad)
    for naam, band in kleine_velden(velden).items():
        pad = uit / f"{naam}.webp"
        pad.write_bytes(klein_webp(uit / f"{band}.webp"))
        regels.append(f"- `{pad.name}`: verkleind uit `{band}.webp` tot {KLEIN_MAAT[0]}×{KLEIN_MAAT[1]}, "
                      f"{pad.stat().st_size // 1024} KB; de kaart van het thema op de start en het overzicht.")
        paden.append(pad)
    PLATFORM_CSS.write_text(platform_css(list(velden)), encoding="utf-8")
    (uit / "HERKOMST.md").write_text("\n".join([
        "# Herkomst van de beelden van het platform (PLAN #33.6d, DESIGN §4w)",
        "",
        f"Gemaakt met `python -m doublecheck.velden platform`, script {VERSIE}, op {date.today().isoformat()}.",
        "Geen foto, geen beeldmodel, geen download, geen licentie: dezelfde tekenaars als de velden van factiz.org",
        "(`HERKOMST-basis.md`), met per thema en per dossier een eigen seed. Witte tekst haalt in elke",
        "tekstzone zijn contrast na de sluier van de pagina (`tests/test_velden_platform.py`).",
        "",
        *regels,
        "",
    ]), encoding="utf-8")
    return paden


def webp(beeld: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray((np.clip(beeld, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, "WEBP", quality=80, method=6)
    return buf.getvalue()


def deelbeeld(corpus: np.ndarray) -> bytes:
    """De afbeelding bij delen (Open Graph): corpus op 1200×630, zonder
    tekst; als JPEG, want niet elke app leest WebP."""
    beeld = Image.fromarray((np.clip(corpus, 0, 1) * 255 + 0.5).astype(np.uint8))
    beeld = beeld.resize((1400, 630), Image.LANCZOS).crop((100, 0, 1300, 630))
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=85, optimize=True, progressive=True)
    return buf.getvalue()


def contrast_wit(pixels: np.ndarray, zone: Zone) -> float:
    """Wit tegen de lichtste 5% van de pixels in de zone (WCAG), nadat de
    pagina er de schaduwlaag van de zone over gelegd heeft."""
    h, w, _ = pixels.shape
    x0, y0, x1, y1 = zone.vak
    vak = pixels[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].astype(np.float64) / 255 * (1 - zone.schaduw)
    lineair = np.where(vak <= 0.03928, vak / 12.92, ((vak + 0.055) / 1.055) ** 2.4)
    licht = np.percentile(lineair.reshape(-1, 3) @ _LUMA.astype(np.float64), 95)
    return 1.05 / (licht + 0.05)


# --- de tellingen achter corpus ----------------------------------------------------

def lees_tellingen() -> dict:
    return json.loads(TELLINGEN.read_text(encoding="utf-8"))


def bijschrift_corpus(tellingen: dict) -> str:
    """Wat onder het beeld staat. Geen aantal talen of checks: de kop van de
    site telt de talen al, en het totaal loopt na de releasekaart door."""
    van, tot = tellingen["maanden"][0][:4], tellingen["maanden"][-1][:4]
    return f"Each streak is one language, {van} to {tot}. The brighter, the more fact-checks that month."


def tellen(conn) -> dict:
    """Checks per taal en maand, alleen wat in de index staat (B28). Wat geen
    spoor tekent wordt geteld: zonder datum, vóór het begin, zonder taal."""
    from doublecheck.toelating import buiten_index

    buiten = buiten_index(conn)
    rijen = [(taal, (datum or "")[:7]) for claim_id, taal, datum in conn.execute(
        "SELECT f.claim_id, c.language, f.review_date FROM factcheck f JOIN claim c USING(claim_id)")
        if claim_id not in buiten]
    gedateerd = [m for _, m in rijen if m]
    eind = max(gedateerd)
    maanden, (jaar, maand) = [], map(int, BEGIN.split("-"))
    while f"{jaar}-{maand:02d}" <= eind:
        maanden.append(f"{jaar}-{maand:02d}")
        jaar, maand = (jaar + 1, 1) if maand == 12 else (jaar, maand + 1)
    plek = {m: i for i, m in enumerate(maanden)}
    talen: dict[str, list[int]] = {}
    zonder_taal = 0
    for taal, m in rijen:
        if m in plek:
            if taal == ONBEPAALD:
                zonder_taal += 1
            else:
                talen.setdefault(taal, [0] * len(maanden))[plek[m]] += 1
    return {
        "_meta": "De tellingen achter het veld corpus (doublecheck/velden.py, PLAN #23.14): checks in de index per "
                 "taal en maand, vanaf BEGIN. Opnieuw met `python -m doublecheck.velden tellen`.",
        "datum": date.today().isoformat(),
        "checks_in_index": len(rijen),
        "checks_getekend": sum(map(sum, talen.values())),
        "zonder_datum": len(rijen) - len(gedateerd),
        "voor_begin": sum(1 for m in gedateerd if m < BEGIN),
        "zonder_taal": zonder_taal,
        "talen_in_index": sorted({taal for taal, _ in rijen}),
        "maanden": maanden,
        "talen": dict(sorted(talen.items())),
    }


# --- uitvoer -------------------------------------------------------------------

def _getal(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _herkomst(regels: list[str], tellingen: dict) -> str:
    return "\n".join([
        "# Herkomst van de beelden (PLAN #23.14, DESIGN §4h)",
        "",
        f"Gemaakt met `python -m doublecheck.velden`, script {VERSIE}, op {date.today().isoformat()}.",
        "Geen foto, geen beeldmodel, geen download, geen licentie: lichtstrepen, vervaagd en met",
        "filmkorrel, uit een vaste seed. Hetzelfde commando geeft hetzelfde beeld, en witte tekst",
        "haalt in elke tekstzone zijn contrast na de schaduwlaag van de pagina (`tests/test_velden.py`).",
        "",
        *regels,
        "",
        f"Corpus is getekend uit de stand van de database op {tellingen['datum']}: "
        f"{_getal(tellingen['checks_in_index'])} checks in de index,",
        f"in {len(tellingen['talen_in_index'])} taalcodes. {_getal(tellingen['checks_getekend'])} checks tekenen "
        f"een spoor, één per taal;",
        f"niet getekend: {_getal(tellingen['zonder_datum'])} zonder datum, {tellingen['voor_begin']} van vóór "
        f"{BEGIN[:4]}, {_getal(tellingen['zonder_taal'])} zonder vastgestelde taal ({ONBEPAALD}).",
        f"Bijschrift: \"{bijschrift_corpus(tellingen)}\"",
        "",
    ])


def maak(uit: Path = UIT) -> list[Path]:
    """Alle basisvelden, de afbeelding bij delen en HERKOMST-basis.md."""
    uit.mkdir(parents=True, exist_ok=True)
    tellingen = lees_tellingen()
    regels, paden = [], []
    for naam, veld in VELDEN.items():
        beeld = teken(naam)
        pad = uit / f"{naam}.webp"
        pad.write_bytes(webp(beeld))
        pixels = np.asarray(Image.open(pad).convert("RGB"))
        zones = ", ".join(f"{z.naam} {contrast_wit(pixels, z):.1f}:1".replace(".", ",") for z in veld.zones)
        regels.append(f"- `{pad.name}`: seed {veld.seed}, {veld.breedte}×{veld.hoogte}, "
                      f"{pad.stat().st_size // 1024} KB; {veld.gebruik}; wit in de tekstzones: {zones}.")
        paden.append(pad)
        if naam == "corpus":
            delen = uit / DELEN.name
            delen.write_bytes(deelbeeld(beeld))
            regels.append(f"- `{delen.name}`: uitsnede van corpus, 1200×630, {delen.stat().st_size // 1024} KB, "
                          "JPEG; de afbeelding bij delen (Open Graph), zonder tekst.")
            paden.append(delen)
    (uit / HERKOMST_BASIS.name).write_text(_herkomst(regels, tellingen), encoding="utf-8")
    return paden


def main() -> None:
    import argparse
    import os
    import sqlite3

    parser = argparse.ArgumentParser(description="De velden van de site (PLAN #23.14)")
    parser.add_argument("stap", nargs="?", choices=("maken", "tellen", "platform"), default="maken",
                        help="maken: alle basisvelden en HERKOMST-basis.md; tellen: de tellingen achter corpus uit de database; "
                             "platform: de beelden van het platform, velden.css en hun HERKOMST.md")
    args = parser.parse_args()
    if args.stap == "platform":
        for pad in maak_platform():
            print(f"{pad.relative_to(WORTEL)}: {pad.stat().st_size // 1024} KB")
        print(f"{PLATFORM_CSS.relative_to(WORTEL)}")
        return
    if args.stap == "tellen":
        pad = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
        conn = sqlite3.connect(f"file:{pad}?mode=ro", uri=True)
        tellingen = tellen(conn)
        TELLINGEN.write_text(json.dumps(tellingen, ensure_ascii=False, separators=(",", ":")) + "\n",
                             encoding="utf-8")
        print(f"{TELLINGEN.name}: {len(tellingen['talen'])} talen, {len(tellingen['maanden'])} maanden, "
              f"{tellingen['checks_getekend']} van {tellingen['checks_in_index']} checks getekend")
        return
    for pad in maak():
        print(f"{pad.relative_to(WORTEL)}: {pad.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
