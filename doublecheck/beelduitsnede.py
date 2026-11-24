"""Het beeldgebied uit een screenshot, en hashen op uitsneden (PLAN.md #26.3).

PDQ is een hash over het hele beeld. Komt er een kader omheen (een
screenshot van een post) of wordt het bijgesneden, dan verandert de hash te
veel: in de pilot van #25.11 vond een kopie in een kader het origineel nooit
terug, een bijgesneden kopie ook nooit (BENCHMARK §88).

Twee ingrepen, allebei nooit slechter dan nu, want de hash van het hele
beeld doet altijd mee:

- **vraagkant**: het beeldgebied uit een screenshot knippen (de langste reeks
  rijen met fotoachtige inhoud tussen vlakke randen van de app) en die
  uitsnede ook hashen. Binnen een gevonden gebied zoekt het verder met de
  randkleur van dat gebied als achtergrond, want een kader zit vaak in een
  kader;
- **indexkant**: per geïndexeerd beeld ook een paar vaste uitsneden hashen,
  tegen een bijgesneden kopie.

Elke extra hash is een extra kans op een verkeerde treffer; daarom zijn het
er weinig en wordt elke ingreep apart op valse treffers gemeten. Alleen in het
geheugen (DR3).
"""

from __future__ import annotations

import numpy as np

from doublecheck.image_fingerprint import as_image, pdq_met_kwaliteit

# (naam, (links, boven, rechts, onder) als fractie van breedte en hoogte)
UITSNEDEN = (
    ("midden80", (0.10, 0.10, 0.90, 0.90)),
    ("zonder_boven15", (0.0, 0.15, 1.0, 1.0)),
    ("zonder_onder15", (0.0, 0.0, 1.0, 0.85)),
)

_WERKBREEDTE = 512      # rekenen op een verkleinde kopie; de uitsnede komt uit het origineel
_DREMPEL_AFWIJKING = 60  # som van |R|,|G|,|B|-verschil met de achtergrond
_DICHT = 0.6            # aandeel van de breedte dat een fotorij afwijkt
_GAT = 2                # zoveel lege rijen mag een reeks overbruggen
_MIN_AANDEEL = 0.20     # kleiner dan dit deel van het kader: geen beeldgebied
_MAX_AANDEEL = 0.95     # groter: het hele beeld is al de foto
_RAND_EGAAL = 0.6       # zoveel van wat buiten het gebied valt, heeft de achtergrondkleur
_TOLERANTIE_EGAAL = 30


def _achtergrond(rgb: np.ndarray) -> np.ndarray:
    """De meest voorkomende kleur langs de rand, grof gekwantiseerd."""
    rand = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]) // 16
    kleuren, aantallen = np.unique(rand, axis=0, return_counts=True)
    return kleuren[int(np.argmax(aantallen))].astype(np.int32) * 16 + 8


def _langste_reeks(rijen: np.ndarray) -> tuple[int, int] | None:
    beste, start, laatste = None, None, None
    for i, waar in enumerate(rijen):
        if not waar:
            continue
        if start is None or i - laatste > _GAT + 1:
            start = i
        laatste = i
        if beste is None or laatste - start > beste[1] - beste[0]:
            beste = (start, laatste + 1)
    return beste


def _gebied(rgb: np.ndarray) -> tuple[int, int, int, int] | None:
    """Eén laag: de rechthoek met fotoachtige inhoud, in de coördinaten van
    `rgb`, of `None` als er geen is of als het al het hele beeld is."""
    h, b = rgb.shape[:2]
    if h < 8 or b < 8:
        return None
    afwijkend = np.abs(rgb.astype(np.int32) - _achtergrond(rgb)).sum(axis=2) > _DREMPEL_AFWIJKING
    reeks = _langste_reeks(afwijkend.mean(axis=1) >= _DICHT)
    if reeks is None:
        return None
    boven, onder = reeks
    kolommen = np.nonzero(afwijkend[boven:onder].mean(axis=0) >= _DICHT)[0]
    if not len(kolommen):
        return None
    links, rechts = int(kolommen[0]), int(kolommen[-1]) + 1
    aandeel = (onder - boven) * (rechts - links) / (h * b)
    if aandeel < _MIN_AANDEEL or aandeel >= _MAX_AANDEEL:
        return None
    # Een app-rand is effen: buiten het gebied heeft het meeste de
    # achtergrondkleur, op wat tekst en knoppen na. Een foto zonder kader
    # heeft dat nergens, ook niet waar ze rustig is.
    buiten = np.ones((h, b), dtype=bool)
    buiten[boven:onder, links:rechts] = False
    egaal = np.abs(rgb.astype(np.int32) - _achtergrond(rgb)).sum(axis=2) <= _TOLERANTIE_EGAAL
    if egaal[buiten].mean() < _RAND_EGAAL:
        return None
    return links, boven, rechts, onder


def beeldgebied(beeld) -> tuple[int, int, int, int] | None:
    """(links, boven, rechts, onder) van de foto in een screenshot, in pixels
    van het origineel; `None` als het beeld geen kader heeft of geen foto
    bevat. Zoekt tot drie lagen diep: een kader in een kader."""
    beeld = as_image(beeld).convert("RGB")
    schaal = min(1.0, _WERKBREEDTE / beeld.width)
    klein = np.asarray(beeld.resize((max(1, round(beeld.width * schaal)), max(1, round(beeld.height * schaal))))
                       if schaal < 1 else beeld)
    totaal = None
    x0 = y0 = 0
    deel = klein
    for _ in range(3):
        gebied = _gebied(deel)
        if gebied is None:
            break
        links, boven, rechts, onder = gebied
        x0, y0 = x0 + links, y0 + boven
        totaal = (x0, y0, x0 + (rechts - links), y0 + (onder - boven))
        deel = deel[boven:onder, links:rechts]
    if totaal is None:
        return None
    links, boven, rechts, onder = (round(v / schaal) for v in totaal)
    return links, boven, min(rechts, beeld.width), min(onder, beeld.height)


def vraaghashes(beeld, versie: str) -> list[str]:
    """De hash van het hele beeld, plus die van het beeldgebied als er een is."""
    if versie != "pdq-256-v1":
        raise ValueError(f"uitsneden zijn gemeten met pdq-256-v1, niet met {versie!r}")
    beeld = as_image(beeld).convert("RGB")
    hashes = [pdq_met_kwaliteit(beeld)[0]]
    gebied = beeldgebied(beeld)
    if gebied is not None:
        hashes.append(pdq_met_kwaliteit(beeld.crop(gebied))[0])
    return hashes


def indexhashes(beeld, versie: str) -> list[str]:
    """De hash van het hele beeld, plus die van de vaste uitsneden."""
    if versie != "pdq-256-v1":
        raise ValueError(f"uitsneden zijn gemeten met pdq-256-v1, niet met {versie!r}")
    beeld = as_image(beeld).convert("RGB")
    b, h = beeld.size
    uit = [pdq_met_kwaliteit(beeld)[0]]
    for _, (l, t, r, o) in UITSNEDEN:
        uit.append(pdq_met_kwaliteit(beeld.crop((int(b * l), int(h * t), int(b * r), int(h * o))))[0])
    return uit



# --- panelen (#32.15 stap 2b) ------------------------------------------------------------------
#
# Een factchecker zet het virale beeld vaak in een collage: twee of drie beelden naast elkaar, met een effen band of
# zonder ruimte ertussen, en een stempel erop. De index kent dan alleen het geheel, en een kopie van één van de
# beelden lijkt daar te weinig op (BENCHMARK §185). Hier wordt het geheel geknipt waar een effen band of een rechte
# naad over het hele blok loopt, tot twee lagen diep, en per stuk ook het beeldgebied gezocht (de foto in een post).

PANELEN = "panelen-v1"
MAX_PANELEN = 8
_MIN_PANEEL = 0.15       # van de zijde van het hele beeld
_MIN_PIXELS = 100        # in het origineel
_EFFEN_AANDEEL = 0.97    # zoveel van een kolom ligt dicht bij haar mediaan: een effen band
_EFFEN_TOLERANTIE = 30
_NAAD = 0.6              # zoveel rijen springen hard op dezelfde kolom: een naad
_SPRONG = 90             # som van |R|,|G|,|B|-verschil over twee kolommen
_NAAD_BOVEN_BUREN = 2.5  # de naad steekt zoveel keer boven zijn buurt uit (geen textuur)
_ZELFDE_VAK = 0.9        # overlap waarboven twee vakken hetzelfde zijn


def _effen(blok: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per kolom: is ze effen (een band tussen twee beelden, of de rand), en haar kleur."""
    mediaan = np.median(blok, axis=0)
    return (np.abs(blok - mediaan[None]).sum(axis=2) <= _EFFEN_TOLERANTIE).mean(axis=0) >= _EFFEN_AANDEEL, mediaan


def _naden(blok: np.ndarray) -> list[int]:
    """Kolommen waar bijna elke rij hard springt, en de buren niet: de grens tussen twee geplakte beelden."""
    b = blok.shape[1]
    if b < 8:
        return []
    sprong = np.zeros(b)
    sprong[1:-1] = (np.abs(blok[:, 2:] - blok[:, :-2]).sum(axis=2) > _SPRONG).mean(axis=0)
    uit = []
    for x in range(2, b - 2):
        buurt = np.concatenate([sprong[max(0, x - 8):x - 1], sprong[x + 2:x + 9]])
        if sprong[x] >= _NAAD and sprong[x] == sprong[x - 1:x + 2].max() and \
                sprong[x] >= _NAAD_BOVEN_BUREN * max(float(np.median(buurt)), 0.05):
            if not uit or x - uit[-1] > 3:
                uit.append(x)
    return uit


def _stukken(blok: np.ndarray, achtergrond: np.ndarray) -> list[tuple[int, int]]:
    """De stukken langs de kolommen van een blok. Een effen band binnenin scheidt twee stukken; aan de rand gaat hij
    er alleen af als hij de randkleur van het geheel heeft, want een effen lucht hoort bij de foto. Een naad scheidt
    ook."""
    effen, kleur = _effen(blok)
    b = blok.shape[1]
    weg = np.zeros(b, dtype=bool)
    x = 0
    while x < b:
        if not effen[x]:
            x += 1
            continue
        z = x
        while z < b and effen[z]:
            z += 1
        aan_rand = x == 0 or z == b
        if not aan_rand or (np.abs(kleur[x:z] - achtergrond).sum(axis=1) <= _EFFEN_TOLERANTIE).mean() >= 0.5:
            weg[x:z] = True
        x = z
    grenzen = set(_naden(blok))
    stukken, start = [], None
    for x in range(b + 1):
        if x == b or weg[x] or x in grenzen:
            if start is not None:
                stukken.append((start, x))
            start = None if (x == b or weg[x]) else x
        elif start is None:
            start = x
    return [s for s in stukken if s[1] - s[0] >= 4]


def _knip(rgb: np.ndarray, vak: tuple[int, int, int, int], diepte: int,
          achtergrond: np.ndarray) -> list[tuple[int, int, int, int]]:
    """XY-snede: eerst langs de kolommen, anders langs de rijen; de bladeren zijn de panelen."""
    l, t, r, o = vak
    blok = rgb[t:o, l:r]
    for as_ in (1, 0):
        stukken = _stukken(blok if as_ == 1 else blok.transpose(1, 0, 2), achtergrond)
        if len(stukken) >= 2 and diepte > 0:
            uit = []
            for a, z in stukken:
                deel = (l + a, t, l + z, o) if as_ == 1 else (l, t + a, r, t + z)
                uit += _knip(rgb, deel, diepte - 1, achtergrond)
            return uit
        if len(stukken) == 1:   # alleen effen randen eraf
            a, z = stukken[0]
            if (z - a) < (blok.shape[1] if as_ == 1 else blok.shape[0]):
                blok = blok[:, a:z] if as_ == 1 else blok[a:z]
                l, t, r, o = (l + a, t, l + z, o) if as_ == 1 else (l, t + a, r, t + z)
    return [(l, t, r, o)]


def _overlap(a, b) -> float:
    bl, bt, br, bo = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    snede = max(0, br - bl) * max(0, bo - bt)
    opp = lambda v: (v[2] - v[0]) * (v[3] - v[1])  # noqa: E731
    return snede / (opp(a) + opp(b) - snede) if snede else 0.0


def panelen(beeld) -> list[tuple[int, int, int, int]]:
    """(links, boven, rechts, onder) van de panelen in een beeld, in pixels van het origineel, de grootste eerst;
    leeg voor een gewone foto. Een paneel is een stuk van een collage of het beeldgebied van het geheel of van een
    stuk; minstens 100 pixels en 15% van de zijde, nooit (bijna) het hele beeld, hooguit `MAX_PANELEN`."""
    beeld = as_image(beeld).convert("RGB")
    schaal = min(1.0, _WERKBREEDTE / beeld.width)
    klein = beeld.resize((max(1, round(beeld.width * schaal)), max(1, round(beeld.height * schaal)))) \
        if schaal < 1 else beeld
    rgb = np.asarray(klein).astype(np.int32)
    h, b = rgb.shape[:2]
    stukken = [tuple(round(v / schaal) for v in vak) for vak in _knip(rgb, (0, 0, b, h), 2, _achtergrond(rgb))]
    heel = (0, 0, beeld.width, beeld.height)
    kandidaten = list(stukken)
    for vak in [heel] + stukken:
        gebied = beeldgebied(beeld.crop(vak))
        if gebied:
            kandidaten.append((vak[0] + gebied[0], vak[1] + gebied[1], vak[0] + gebied[2], vak[1] + gebied[3]))
    uit = []
    for vak in sorted(kandidaten, key=lambda v: -(v[2] - v[0]) * (v[3] - v[1])):
        vb, vh = vak[2] - vak[0], vak[3] - vak[1]
        if min(vb, vh) < _MIN_PIXELS or vb < _MIN_PANEEL * beeld.width or vh < _MIN_PANEEL * beeld.height:
            continue
        if _overlap(vak, heel) > _ZELFDE_VAK or any(_overlap(vak, w) > _ZELFDE_VAK for w in uit):
            continue
        uit.append(vak)
    return uit[:MAX_PANELEN]
