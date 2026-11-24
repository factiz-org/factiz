"""Het deelplaatje per factcheck (PLAN #34.2aq, SPECS E9.S23, DESIGNSYSTEEM §4).

Wie een factcheck deelt in een app, laat de ontvanger dit plaatje zien: bovenaan een band met het veld en de tekening van
het thema, daaronder op een effen vlak de bewering, het oordeel als label in woorden en wie het checkte. Nooit een veld of
tekening achter de bewering of het label (D11), nooit een eigen oordeel.

Zuinig: niets wordt vooraf gemaakt. Het platform tekent een plaatje als iemand het opvraagt (`app.deelbeeld_bytes`, met
een geheugen voor de laatste) en het adres draagt de versie van de uitgave, zodat een cache het tot de volgende uitgave
houdt. Getekend met Pillow, zonder iets uit `doublecheck`: het lettertype is Geist (`fonts/`), de tekeningen en de kleuren
van de families komen uit `static/platen.json` (uitgeschreven uit de site), het woordmerk uit `static/merk/`.
"""

from __future__ import annotations

import functools
import io
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

MAP = Path(__file__).resolve().parent
STATIC = MAP / "static"
FONTS = MAP / "fonts"

BREED, HOOG = 1200, 630
BAND = 228                    # de hoogte van de band met het veld
MARGE = 64                    # de rand rond de tekst
MAX_REGELS = 3                # de bewering: hoogstens zoveel regels
GROOTTES = (52, 46, 40)       # zo groot als past
ZIN_GROOTTE = 24
LABEL_GROOTTE = 26
STEMPEL_HOOGTE = 52           # het stempel even hoog als het oude label, zodat de rest op zijn plek blijft
OVERMAAT = 3                  # de tekening zoveel groter, daarna verkleind: zachte randen
PANEEL, INKT, ZACHT = (255, 255, 255), (23, 23, 23), (95, 100, 97)
PAPIER = (252, 252, 251)

# de kleuren van het label zoals op de site (`site.css`, de lichte tokens; `tests/test_factiz_deelbeeld.py` houdt ze gelijk)
LABELKLEUREN = {
    "onwaar": {"inkt": "#7a3600", "vlak": "#fbe0c2", "rand": "#eeb27a", "stip": "#c45f0a"},
    "misleidend": {"inkt": "#5c5000", "vlak": "#fbf7dc", "rand": "#e5d98f", "stip": "#a38900"},
    "deels": {"inkt": "#5f5240", "vlak": "#f3eee5", "rand": "#ddd1bd", "stip": "#9c8763"},
    "waar": {"inkt": "#1d4a8c", "vlak": "#e8f0fc", "rand": "#bdd1f1", "stip": "#3a6fc6"},
    "omstreden": {"inkt": "#573a8e", "vlak": "#f1ecfa", "rand": "#d6caef", "stip": "#7b58c2"},
    "satire": {"inkt": "#86306a", "vlak": "#fbedf6", "rand": "#edc6df", "stip": "#b4468c"},
    "onbewezen": {"inkt": "#474d5c", "vlak": "#f0f1f4", "rand": "#d1d5dd", "stip": "#868d9e"},
}
GEEN_LABEL = {"inkt": "#171717", "vlak": "#ffffff", "rand": "#d9dbd9", "stip": "#8b908d"}
KLASSE_KLEUR = {"onwaar": "onwaar", "onwaar-of-misleidend": "onwaar", "misleidend": "misleidend", "deels-waar": "deels",
                "waar": "waar", "omstreden": "omstreden", "satire": "satire", "onbewezen": "onbewezen"}

LETTERTYPES = tuple(f"geist-{deel}-wght-normal.woff2" for deel in ("latin", "latin-ext", "cyrillic", "cyrillic-ext", "vietnamese"))
# Achter Geist Noto Sans per schrift (PLAN #34.2as, SPECS E9.S28), dezelfde pakketten als de site; in `fonts/noto/`
# gekopieerd met `python -m factiz_site.lettertypen`. Chinees, Japans en Koreaans delen tekens: de tekst kiest de variant.
NOTO = ("noto-sans", "noto-sans-arabic", "noto-sans-hebrew", "noto-sans-devanagari", "noto-sans-bengali", "noto-sans-tamil",
        "noto-sans-telugu", "noto-sans-malayalam", "noto-sans-kannada", "noto-sans-gujarati", "noto-sans-gurmukhi",
        "noto-sans-sinhala", "noto-sans-thai", "noto-sans-khmer", "noto-sans-ethiopic",
        "noto-sans-sc", "noto-sans-tc", "noto-sans-jp", "noto-sans-kr")
CJK = ("noto-sans-sc", "noto-sans-tc", "noto-sans-jp", "noto-sans-kr")
# tekens die alleen in traditioneel Chinees zo geschreven worden: daaraan herken je een tekst uit Taiwan of Hongkong
TRADITIONEEL = frozenset("這個們說國會灣為與經裡發時對學來無後電視嗎點關選舉實體開長門問間現認讓應過還運動語錢錄東車書買賣見親頭題麼樣"
                         "誤錯臺灣區華際總統黨權議論號網絡變顯聞報導戰爭軍隊將傳們")
# schriften zonder spaties tussen de woorden: een regel breekt daar per teken
_GEEN_SPATIES = re.compile(r"[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def _reeksen(tekst: str) -> tuple[tuple[int, int], ...]:
    reeksen = []
    for deel in tekst.split(","):
        a, _, b = deel.strip().upper().replace("U+", "").partition("-")
        reeksen.append((int(a, 16), int(b or a, 16)))
    return tuple(reeksen)


@functools.cache
def _bereik() -> tuple[tuple[str, tuple[tuple[int, int], ...]], ...]:
    """Per bestand de tekens die het dekt, uit het stijlblad van zijn pakket: eerst Geist in de volgorde van
    `LETTERTYPES`, dan Noto Sans per schrift in de volgorde van `NOTO`. Een pad is ten opzichte van `FONTS`."""
    css = (FONTS / "geist.css").read_text(encoding="utf-8")
    uit = []
    for bestand in LETTERTYPES:
        blok = re.search(r"url\(\./files/" + re.escape(bestand) + r"\)[^}]*?unicode-range: ([^;]+);", css, re.S)
        uit.append((bestand, _reeksen(blok.group(1))))
    for pakket in NOTO:
        stijl = FONTS / "noto" / pakket / "index.css"
        if not stijl.exists():
            continue
        for naam, reeks in re.findall(r"url\(\./files/([^)]+\.woff2)\)[^}]*?unicode-range: ([^;]+);",
                                      stijl.read_text(encoding="utf-8"), re.S):
            uit.append((f"noto/{pakket}/files/{naam}", _reeksen(reeks)))
    return tuple(uit)


@functools.cache
def _volgorde(cjk: str) -> tuple[tuple[str, tuple[tuple[int, int], ...]], ...]:
    """`_bereik` met de variant `cjk` vóór de andere drie, voor de tekens die ze delen."""
    is_cjk = lambda b: b.startswith("noto/noto-sans-") and b.split("/")[1] in CJK
    gewoon = [r for r in _bereik() if not is_cjk(r[0])]
    eerst = [r for r in _bereik() if r[0].split("/")[1:2] == [cjk]]
    rest = [r for r in _bereik() if is_cjk(r[0]) and r[0].split("/")[1] != cjk]
    return tuple(gewoon + eerst + rest)


def cjk_variant(tekst: str) -> str:
    """Japans bij kana, Koreaans bij hangul, traditioneel Chinees bij een traditioneel teken, anders vereenvoudigd."""
    if any("\u3040" <= ch <= "\u30ff" for ch in tekst):
        return "noto-sans-jp"
    if any("\uac00" <= ch <= "\ud7af" or "\u1100" <= ch <= "\u11ff" or "\u3130" <= ch <= "\u318f" for ch in tekst):
        return "noto-sans-kr"
    if any(ch in TRADITIONEEL for ch in tekst):
        return "noto-sans-tc"
    return "noto-sans-sc"


@functools.lru_cache(maxsize=8192)
def _bestand_voor(teken: str, cjk: str = "noto-sans-sc") -> str | None:
    code = ord(teken)
    for bestand, reeksen in _volgorde(cjk):
        if any(a <= code <= b for a, b in reeksen):
            return bestand
    return None


def onzichtbaar(teken: str) -> bool:
    """Een teken dat niets tekent maar het vormen stuurt (zero width joiner, richtingsteken): hoort bij zijn stuk."""
    return unicodedata.category(teken) == "Cf"


def kan_tonen(tekst: str) -> bool:
    """Heeft elk teken van deze tekst een lettertype (Geist, of Noto Sans per schrift)? Anders geen bewering op het
    plaatje, en een naam maakt plaats voor de telling."""
    cjk = cjk_variant(tekst)
    return bool(tekst.strip()) and all(ch.isspace() or onzichtbaar(ch) or _bestand_voor(ch, cjk) for ch in tekst)


@functools.cache
def _font(bestand: str, grootte: int, gewicht: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONTS / bestand), grootte, layout_engine=ImageFont.Layout.RAQM)
    font.set_variation_by_axes([gewicht])
    return font


def _stukken(tekst: str) -> list[tuple[str, str]]:
    """De tekst in stukken per lettertypebestand; een spatie of een onzichtbaar teken blijft bij het stuk waar het in staat."""
    stukken: list[tuple[str, str]] = []
    cjk = cjk_variant(tekst)
    for ch in tekst:
        los = ch.isspace() or onzichtbaar(ch)
        bestand = LETTERTYPES[0] if los else (_bestand_voor(ch, cjk) or LETTERTYPES[0])
        if stukken and (los or stukken[-1][0] == bestand):
            stukken[-1] = (stukken[-1][0], stukken[-1][1] + ch)
        else:
            stukken.append((bestand, ch))
    return stukken


def _rtl(tekst: str) -> bool:
    return any(unicodedata.bidirectional(ch) in ("R", "AL") for ch in tekst)


def _basis_rtl(tekst: str) -> bool:
    """De richting van een regel: die van haar eerste sterke teken."""
    for ch in tekst:
        richting = unicodedata.bidirectional(ch)
        if richting in ("R", "AL"):
            return True
        if richting == "L":
            return False
    return False


def _breedte(tekst: str, grootte: int, gewicht: int) -> float:
    return sum(_font(b, grootte, gewicht).getlength(s) for b, s in _stukken(tekst))


def _plaatsing(tekst: str, links: float, rechts: float | None, grootte: int, gewicht: int) -> list[tuple[float, str, str, str]]:
    """Waar elk stuk komt: (x, bestand, stuk, richting). Een regel van links naar rechts begint bij `links`. Een regel van
    rechts naar links eindigt bij `rechts` (zonder `rechts`: bij `links` plus haar breedte) en zet haar stukken van rechts
    naar links, elk in zijn eigen richting: een getal of een Latijns woord in een Arabische zin blijft leesbaar."""
    stukken = _stukken(tekst)
    breed = [(b, s, _font(b, grootte, gewicht).getlength(s)) for b, s in stukken]
    if not _basis_rtl(tekst):
        uit, x = [], links
        for b, s, w in breed:
            uit.append((x, b, s, "rtl" if _rtl(s) else "ltr"))
            x += w
        return uit
    x = rechts if rechts is not None else links + sum(w for *_, w in breed)
    uit = []
    for b, s, w in breed:
        x -= w
        uit.append((x, b, s, "rtl" if _rtl(s) else "ltr"))
    return uit


def _schrijf(teken: ImageDraw.ImageDraw, x: float, y: float, tekst: str, grootte: int, gewicht: int, kleur,
             anker: str = "la", rechts: float | None = None) -> None:
    for plek, bestand, stuk, richting in _plaatsing(tekst, x, rechts, grootte, gewicht):
        teken.text((plek, y), stuk, font=_font(bestand, grootte, gewicht), fill=kleur, anchor=anker, direction=richting)


def _delen(tekst: str) -> list[tuple[str, str]]:
    """De tekst in stukken om af te breken, elk met wat ervoor hoort: een spatie tussen woorden, niets tussen twee tekens
    van een schrift zonder spaties (Chinees, Japans, Thai, Khmer). Een teken dat op het vorige zit (een klinkerteken),
    blijft daarbij."""
    delen: list[tuple[str, str]] = []
    for woord in tekst.split():
        tussen, los = " " if delen else "", ""
        for ch in woord:
            if unicodedata.category(ch) in ("Mn", "Mc", "Me") and not los and delen and _GEEN_SPATIES.match(delen[-1][0][-1]):
                delen[-1] = (delen[-1][0] + ch, delen[-1][1])
            elif _GEEN_SPATIES.match(ch):
                if los:
                    delen.append((los, tussen)); tussen, los = "", ""
                delen.append((ch, tussen)); tussen = ""
            else:
                los += ch
        if los:
            delen.append((los, tussen))
    return delen


def _regels(tekst: str, grootte: int, breedte: float, max_regels: int, gewicht: int = 600) -> tuple[list[str], bool]:
    """De tekst in regels die passen; wat niet past wordt afgekapt met een beletselteken, na een heel woord, of in een
    schrift zonder spaties na een heel teken."""
    regels, huidig = [], ""
    for stuk, tussen in _delen(tekst):
        proef = f"{huidig}{tussen}{stuk}" if huidig else stuk
        if _breedte(proef, grootte, gewicht) <= breedte:
            huidig = proef
            continue
        if huidig:
            regels.append(huidig)
        huidig = stuk
        if len(regels) == max_regels:
            break
    else:
        if huidig:
            regels.append(huidig)
        if len(regels) <= max_regels:
            return regels, False
    regels = regels[:max_regels]
    laatste = regels[-1]
    while laatste and _breedte(laatste + "…", grootte, gewicht) > breedte:
        laatste = laatste.rsplit(" ", 1)[0] if " " in laatste else laatste[:-1]
    regels[-1] = laatste + "…"
    return regels, True


def regels(tekst: str, grootte: int) -> list[str]:
    return _regels(tekst, grootte, BREED - 2 * MARGE, MAX_REGELS)[0]


@functools.cache
def _platen() -> dict:
    return json.loads((STATIC / "platen.json").read_text(encoding="utf-8"))


# --- de tekening ---------------------------------------------------------------------------------------------------------

_TEKENS = re.compile(r"[MLHVCSZ]|-?(?:\d+\.?\d*|\.\d+)")


def _pad(d: str) -> list[list[tuple[float, float]]]:
    """Een pad uit de tekeningen (alleen M, L, H, V, C, S en Z, absoluut) als lijnstukken; een kromme in 20 stappen, en Z
    sluit het stuk naar zijn begin."""
    stukken = _TEKENS.findall(d)
    lijnen: list[list[tuple[float, float]]] = []
    i, opdracht, x, y, vorige_c = 0, "", 0.0, 0.0, None
    getal = lambda: float(stukken[i])
    while i < len(stukken):
        if stukken[i] == "Z":
            x, y = lijnen[-1][0]
            lijnen[-1].append((x, y)); opdracht, vorige_c = "", None
            i += 1
            continue
        if stukken[i] in "MLHVCS":
            opdracht = stukken[i]
            i += 1
            continue
        if opdracht == "M":
            x, y = float(stukken[i]), float(stukken[i + 1]); i += 2
            lijnen.append([(x, y)]); opdracht, vorige_c = "L", None
        elif opdracht == "L":
            x, y = float(stukken[i]), float(stukken[i + 1]); i += 2
            lijnen[-1].append((x, y)); vorige_c = None
        elif opdracht == "H":
            x = getal(); i += 1; lijnen[-1].append((x, y)); vorige_c = None
        elif opdracht == "V":
            y = getal(); i += 1; lijnen[-1].append((x, y)); vorige_c = None
        elif opdracht in "CS":
            if opdracht == "C":
                c1 = (float(stukken[i]), float(stukken[i + 1])); i += 2
            else:
                c1 = (2 * x - vorige_c[0], 2 * y - vorige_c[1]) if vorige_c else (x, y)
            c2 = (float(stukken[i]), float(stukken[i + 1])); eind = (float(stukken[i + 2]), float(stukken[i + 3])); i += 4
            for s in range(1, 21):
                t = s / 20
                lijnen[-1].append(tuple((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
                                        for p0, p1, p2, p3 in zip((x, y), c1, c2, eind)))
            x, y = eind
            vorige_c = c2
        else:
            raise ValueError(f"onbekende opdracht in een pad: {opdracht}")
    return lijnen


def _streep(lijn: list[tuple[float, float]], streep: str | None) -> list[list[tuple[float, float]]]:
    """Een lijn in stukjes volgens een streeppatroon (`3 3`): aan, uit, aan."""
    if not streep:
        return [lijn]
    patroon = [float(s) for s in streep.split()]
    uit, stuk, aan, k, over = [], [lijn[0]], True, 0, patroon[0]
    for (x0, y0), (x1, y1) in zip(lijn, lijn[1:]):
        lengte = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        pos = 0.0
        while lengte - pos > over:
            pos += over
            punt = (x0 + (x1 - x0) * pos / lengte, y0 + (y1 - y0) * pos / lengte)
            if aan:
                uit.append(stuk + [punt])
            stuk, aan = [punt], not aan
            k = (k + 1) % len(patroon)
            over = patroon[k]
        over -= lengte - pos
        stuk.append((x1, y1))
    if aan and len(stuk) > 1:
        uit.append(stuk)
    return uit


def _vormen(vormen: list[dict], maat: tuple[int, int], schaal: float, kleur: tuple[int, int, int]) -> Image.Image:
    """De vormen van een tekening als RGBA-beeld van `maat`, met `schaal` pixels per eenheid van het raster."""
    s = schaal * OVERMAAT
    groot = (maat[0] * OVERMAAT, maat[1] * OVERMAAT)
    laag = Image.new("RGBA", groot, (0, 0, 0, 0))

    def leg(masker: Image.Image, rgb, dekking: float) -> None:
        nonlocal laag
        vlak = Image.new("RGBA", groot, tuple(rgb) + (0,))
        vlak.putalpha(masker.point(lambda v: round(v * dekking)))
        laag = Image.alpha_composite(laag, vlak)

    def lijn_masker(lijnen, breedte) -> Image.Image:
        masker = Image.new("L", groot, 0)
        teken = ImageDraw.Draw(masker)
        for lijn in lijnen:
            punten = [(px * s, py * s) for px, py in lijn]
            teken.line(punten, fill=255, width=max(1, round(breedte * s)), joint="curve")
            for px, py in (punten[0], punten[-1]):    # ronde uiteinden
                r = breedte * s / 2
                teken.ellipse((px - r, py - r, px + r, py + r), fill=255)
        return masker

    for v in vormen:
        masker = Image.new("L", groot, 0)
        teken = ImageDraw.Draw(masker)
        if v["v"] in ("regel", "blok"):
            r = v["h"] / 2 if v["v"] == "regel" else v["r"]
            teken.rounded_rectangle((v["x"] * s, v["y"] * s, (v["x"] + v["w"]) * s, (v["y"] + v["h"]) * s), radius=r * s, fill=255)
            leg(masker, kleur, v["o"])
        elif v["v"] == "stip":
            x, y, r = v["x"] * s, v["y"] * s, v["r"] * s
            teken.ellipse((x - r, y - r, x + r, y + r), fill=255)
            if v.get("open"):
                leg(masker, PAPIER, 0.8)
                rand = Image.new("L", groot, 0)
                ImageDraw.Draw(rand).ellipse((x - r, y - r, x + r, y + r), outline=255, width=max(1, round(0.9 * s)))
                leg(rand, kleur, 0.45)
            else:
                leg(masker, kleur, v["o"])
        elif v["v"] == "lijn":
            lijnen = [deel for lijn in _pad(v["d"]) for deel in _streep(lijn, v.get("streep"))]
            leg(lijn_masker(lijnen, v["w"]), kleur, v["o"])
        elif v["v"] == "ring":
            cirkel = [(v["x"] + v["r"] * np.cos(t), v["y"] + v["r"] * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 121)]
            leg(lijn_masker(_streep(cirkel, v.get("streep")), v["w"]), kleur, v["o"])
        elif v["v"] == "vlak":       # een gevuld pad: een kaart of een voorwerp (2026-11-19)
            for stuk in _pad(v["d"]):
                if len(stuk) > 2:
                    teken.polygon([(px * s, py * s) for px, py in stuk], fill=255)
            leg(masker, kleur, v["o"])
    return laag.resize(maat, Image.LANCZOS)


def _band(thema: str | None, dossier: str | None = None) -> Image.Image:
    """Het veld met de tekening rechts, zoals in de kop van een thema of dossier (E9.S22): bij een dossier zijn eigen veld
    en tekening, anders die van het thema."""
    bronnen = [STATIC / "beeld" / f"dossier-{dossier}-band.webp"] if dossier else []
    bronnen += [STATIC / "beeld" / f"thema-{thema}-band.webp"] if thema else []
    bron = next((b for b in bronnen if b.exists()), STATIC / "beeld" / "delen.jpg")
    veld = Image.open(bron).convert("RGB")
    schaal = max(BREED / veld.width, BAND / veld.height)
    veld = veld.resize((round(veld.width * schaal), round(veld.height * schaal)), Image.LANCZOS)
    links, boven = (veld.width - BREED) // 2, (veld.height - BAND) // 2
    band = veld.crop((links, boven, links + BREED, boven + BAND)).convert("RGBA")
    # de sluier van `.kaartveld` op de site: van 0,1 bovenaan naar 0,55 onderaan
    sluier = np.linspace(0.1, 0.55, BAND, dtype=np.float32)[:, None].repeat(BREED, 1)
    laag = Image.new("RGBA", (BREED, BAND), (12, 13, 16, 0))
    laag.putalpha(Image.fromarray(np.round(sluier * 255).astype(np.uint8)))
    band = Image.alpha_composite(band, laag)
    platen = _platen()
    vormen = (platen["platen"].get(f"dossier:{dossier}") if dossier else None) or \
        (platen["platen"].get(f"thema:{thema}") if thema else None)
    if vormen:
        familie = platen["familie"].get(thema or "")
        kleur = ImageColor.getrgb(platen["kleur"][familie]) if familie else ZACHT
        vak_x, vak_b = BREED // 2, BREED // 2       # de rechterhelft, zoals de kop van een thema
        vel_schaal = max(vak_b / 160, BAND / 68)
        vel = Image.new("RGBA", (BREED, BAND), (0, 0, 0, 0))
        ImageDraw.Draw(vel).rounded_rectangle((vak_x + 26 * vel_schaal, 13 * vel_schaal, BREED + 40, BAND + 40),
                                              radius=3 * vel_schaal, fill=PAPIER + (round(0.72 * 255),))
        band = Image.alpha_composite(band, vel)
        vorm_schaal = min(vak_b / 160, BAND / 68)
        laag = _vormen(vormen, (vak_b, BAND), vorm_schaal, kleur)
        vervaag = np.clip((1 - np.linspace(0, 1, BAND)) / 0.45, 0, 1).astype(np.float32)[:, None].repeat(vak_b, 1)
        alfa = np.asarray(laag.getchannel("A"), dtype=np.float32) * vervaag
        laag.putalpha(Image.fromarray(np.round(alfa).astype(np.uint8)))
        band.alpha_composite(laag, (vak_x, 0))
    # geen korrel erover: die zit al in het veld (PLAN #34.2bf)
    return band.convert("RGB")


def _stempel(teken: ImageDraw.ImageDraw, x: float, y: float, woord: str, klasse: str | None) -> float:
    """Het oordeel als stempel, zoals op de site (PLAN #34.2cc, DESIGN §4y): het woord in hoofdletters in een dubbel kader in
    de kleur van het oordeel, zonder vlak; rechtop, want een schuin kader zetten Pillow en resvg te verschillend. Geeft de
    breedte."""
    kleuren = {k: ImageColor.getrgb(v) for k, v in LABELKLEUREN.get(KLASSE_KLEUR.get(klasse or ""), GEEN_LABEL).items()}
    hoogte, binnen = STEMPEL_HOOGTE, 20
    woord = woord.upper()
    breedte = round(binnen * 2 + _breedte(woord, LABEL_GROOTTE, 700))
    x0, y0 = round(x), round(y)
    teken.rectangle((x0, y0, x0 + breedte, y0 + hoogte), outline=kleuren["stip"], width=3)
    teken.rectangle((x0 + 6, y0 + 6, x0 + breedte - 6, y0 + hoogte - 6), outline=kleuren["stip"], width=2)
    _schrijf(teken, x0 + binnen, y0 + hoogte / 2, woord, LABEL_GROOTTE, 700, kleuren["inkt"], anker="lm")
    return breedte


def _label(teken: ImageDraw.ImageDraw, x: float, y: float, label: str, klasse: str | None) -> float:
    """Het label zoals op de site: een pil met een stip en het woord; geeft de hoogte."""
    kleuren = {k: ImageColor.getrgb(v) for k, v in LABELKLEUREN.get(KLASSE_KLEUR.get(klasse or ""), GEEN_LABEL).items()}
    hoogte, binnen, stip = 52, 22, 12
    breedte = binnen * 2 + stip + 12 + _breedte(label, LABEL_GROOTTE, 600)
    teken.rounded_rectangle((x, y, x + breedte, y + hoogte), radius=hoogte / 2, fill=kleuren["vlak"], outline=kleuren["rand"], width=2)
    teken.ellipse((x + binnen, y + (hoogte - stip) / 2, x + binnen + stip, y + (hoogte + stip) / 2), fill=kleuren["stip"])
    _schrijf(teken, x + binnen + stip + 12, y + hoogte / 2, label, LABEL_GROOTTE, 600, kleuren["inkt"], anker="lm")
    return hoogte


def _basis(thema: str | None, dossier: str | None = None) -> tuple[Image.Image, Image.Image]:
    """Het wit met de band erboven en het woordmerk rechtsonder; geeft het beeld en het woordmerk."""
    beeld = Image.new("RGB", (BREED, HOOG), PANEEL)
    beeld.paste(_band(thema, dossier), (0, 0))
    merk = Image.open(STATIC / "merk" / "woordmerk-deel.png").convert("RGBA")
    beeld.paste(merk, (BREED - MARGE - merk.width, HOOG - 52 - merk.height), merk)
    return beeld, merk


def _jpeg(beeld: Image.Image) -> bytes:
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=86, optimize=True, progressive=True)
    return buf.getvalue()


def teken_ingang(*, kicker: str, titel: str, regel: str, thema: str | None, dossier: str | None = None) -> bytes:
    """Het plaatje van een thema, onderdeel of dossier (PLAN #34.2ar, E9.S23 AC6): de soort klein, de naam groot en het
    aantal eronder, onder de band met het veld en de tekening."""
    beeld, merk = _basis(thema, dossier)
    teken_ = ImageDraw.Draw(beeld)
    boven = BAND + 44
    if kicker and kan_tonen(kicker):
        _schrijf(teken_, MARGE, boven, kicker, ZIN_GROOTTE, 600, ZACHT)
    regel_y = HOOG - 52 - ZIN_GROOTTE * 1.2
    ruimte = regel_y - 24 - (boven + ZIN_GROOTTE * 1.2 + 14)
    if titel and kan_tonen(titel):
        for grootte in (64, 56, 48):
            regels_, afgekapt = _regels(titel, grootte, BREED - 2 * MARGE, 2, 700)
            if not afgekapt and len(regels_) * grootte * 1.12 <= ruimte:
                break
        for i, r in enumerate(regels_):
            _schrijf(teken_, MARGE, boven + ZIN_GROOTTE * 1.2 + 14 + i * grootte * 1.12, r, grootte, 700, INKT, rechts=BREED - MARGE)
    regel_regels, _ = _regels(regel, ZIN_GROOTTE, BREED - 2 * MARGE - merk.width - 32, 1, 400)
    if regel_regels and kan_tonen(regel_regels[0]):
        _schrijf(teken_, MARGE, regel_y, regel_regels[0], ZIN_GROOTTE, 400, ZACHT)
    return _jpeg(beeld)


def teken(*, bewering: str, label: str, klasse: str | None, zin: str, thema: str | None,
          volgens: list[str] | tuple[str, ...] = ()) -> bytes:
    """Het plaatje als JPEG van 1200 bij 630. `bewering` is leeg als het lettertype haar schrift niet kan tonen; `label` is
    het woord op het stempel en `volgens` wie het zegt, klein ernaast (PLAN #34.2cc): de vormen van lang naar kort, en de
    eerste die heel past (anders de kortste, afgekapt)."""
    beeld, merk = _basis(thema)
    teken_ = ImageDraw.Draw(beeld)
    # van onder naar boven: de zin, het label, en de bewering in wat er overblijft; zonder bewering staan het label en de
    # zin midden in het vlak
    zin_y = HOOG - 52 - ZIN_GROOTTE * 1.2
    if not bewering:
        zin_y = BAND + (HOOG - BAND - (52 + 18 + ZIN_GROOTTE * 1.2)) / 2 + 52 + 18
    zin_regels, _ = _regels(zin, ZIN_GROOTTE, BREED - 2 * MARGE - merk.width - 32, 1, 400)
    if zin_regels:
        _schrijf(teken_, MARGE, zin_y, zin_regels[0], ZIN_GROOTTE, 400, ZACHT)
    label_y = zin_y - 18 - 52
    breedte = _stempel(teken_, MARGE, label_y, label, klasse)
    if volgens:
        ruimte = BREED - MARGE - (MARGE + breedte + 18)
        for vorm in volgens:
            volgens_regels, afgekapt = _regels(vorm, ZIN_GROOTTE, ruimte, 1, 500)
            if not afgekapt:
                break
        if volgens_regels:
            _schrijf(teken_, MARGE + breedte + 18, label_y + STEMPEL_HOOGTE / 2, volgens_regels[0], ZIN_GROOTTE, 500, ZACHT,
                     anker="lm")
    if bewering:
        boven, onder = BAND + 36, label_y - 28
        for grootte in GROOTTES:
            regels_, afgekapt = _regels(bewering, grootte, BREED - 2 * MARGE, MAX_REGELS)
            past = len(regels_) * grootte * 1.18 <= onder - boven
            if past and (not afgekapt or grootte == GROOTTES[-1]):
                break
        while len(regels_) * grootte * 1.18 > onder - boven and len(regels_) > 1:
            regels_ = regels_[:-1]
            regels_[-1] = regels_[-1].rstrip("…").rsplit(" ", 1)[0] + "…"
        for i, regel in enumerate(regels_):
            _schrijf(teken_, MARGE, boven + i * grootte * 1.18, regel, grootte, 600, INKT, rechts=BREED - MARGE)
    return _jpeg(beeld)
