"""Het logo als beelden (PLAN #23.18, DESIGN §4h): het icoon van de site, de avatar, het beeld bij delen en het
woordmerk voor kop en voet, uit de twee SVG's van de PO in `factiz_site/static/merk/`. Eén plek sinds PLAN #34.2f: de
site en het platform lezen allebei uit `factiz_site/static/`.

Zoals `velden` tekent dit script zelf, met Pillow: het leest de vormen uit de SVG (een rechthoek met
afgeronde hoeken en paden met M, L, H, V, C en Z) en vult ze, vier keer zo groot getekend en daarna verkleind, zodat
de randen zacht zijn. Geen download, geen beeldmodel; hetzelfde commando geeft dezelfde bytes
(`tests/test_merkbeelden.py`). Een gat in een letter (de a) is een eigen vorm binnen de vorm: even-oneven, zoals
de SVG het vult.

    python -m doublecheck.merkbeelden
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

WORTEL = Path(__file__).resolve().parent.parent
MERK = WORTEL / "factiz_site" / "static" / "merk"
LOGO = MERK / "logo.svg"           # van de PO, 2026-11-09; ook het icoon van de site
WOORDMERK = MERK / "woordmerk.svg"  # van de PO, 2026-11-09: het logo met "factiz" erachter, de letters zwart
INLINE = WORTEL / "factiz_site" / "static" / "merk" / "woordmerk-inline.svg"  # voor kop en voet: de letters in de tekstkleur
DEELBASIS = WORTEL / "factiz_site" / "static" / "beeld" / "delen.jpg"  # de uitsnede van corpus (`velden`), zonder tekst
ORANJE = "#FF5900"
CORPUS = WORTEL / "factiz_site" / "static" / "beeld" / "corpus.webp"  # het veld corpus van `velden`, 2000×900
GEIST = WORTEL / "factiz_site" / "fonts" / "geist-latin-wght-normal.woff2"  # de letter van de site (SIL OFL)
GITHUB_MAP = WORTEL / ".github" / "assets"
PAYOFF = "For a world that can't be fooled."  # B86: overal Engels, nooit vertaald
OMSCHRIJVING = "An open archive of fact-checks from newsrooms worldwide"

_SVG = "{http://www.w3.org/2000/svg}"
_TEKENS = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_STAPPEN = 24      # rechte stukjes per kromme
_OVERMAAT = 4      # zo veel groter getekend, daarna verkleind: zachte randen


def paden(d: str) -> list[list[tuple[float, float]]]:
    """De vormen van een SVG-pad als lijsten punten, elke vorm gesloten. Alleen de absolute opdrachten die in het
    logo staan (M, L, H, V, C, Z); een andere opdracht weigert, liever dan een verkeerd beeld."""
    tekens = _TEKENS.findall(d)
    vormen: list[list[tuple[float, float]]] = []
    vorm: list[tuple[float, float]] = []
    x = y = 0.0
    opdracht = None
    i = 0

    def getal() -> float:
        nonlocal i
        waarde = float(tekens[i])
        i += 1
        return waarde

    while i < len(tekens):
        if tekens[i].isalpha():
            opdracht = tekens[i]
            i += 1
            if opdracht not in "MLHVCZ":
                raise ValueError(f"padopdracht {opdracht} wordt niet getekend")
            if opdracht == "Z":
                if vorm:
                    vorm.append(vorm[0])
                    vormen.append(vorm)
                vorm = []
                continue
        if opdracht == "M":
            if vorm:
                vormen.append(vorm)
            x, y = getal(), getal()
            vorm = [(x, y)]
            opdracht = "L"  # coördinaten na een M zijn lijnen (SVG)
        elif opdracht == "L":
            x, y = getal(), getal()
            vorm.append((x, y))
        elif opdracht == "H":
            x = getal()
            vorm.append((x, y))
        elif opdracht == "V":
            y = getal()
            vorm.append((x, y))
        elif opdracht == "C":
            x1, y1, x2, y2, x3, y3 = (getal() for _ in range(6))
            x0, y0 = x, y
            for stap in range(1, _STAPPEN + 1):
                t = stap / _STAPPEN
                a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                vorm.append((a * x0 + b * x1 + c * x2 + e * x3, a * y0 + b * y1 + c * y2 + e * y3))
            x, y = x3, y3
        else:
            raise ValueError(f"getal zonder opdracht in {d[:30]}")
    if vorm:
        vormen.append(vorm)
    return vormen


def teken(svg: str, hoogte: int, letters: str | None = None) -> Image.Image:
    """De SVG als RGBA-beeld van `hoogte` pixels hoog; `letters` vervangt de kleur zwart (de letters van het
    woordmerk)."""
    wortel = ET.fromstring(svg)
    breedte_vb, hoogte_vb = (float(v) for v in wortel.get("viewBox").split()[2:])
    schaal = hoogte * _OVERMAAT / hoogte_vb
    maat = (round(breedte_vb * hoogte / hoogte_vb) * _OVERMAAT, hoogte * _OVERMAAT)
    beeld = Image.new("RGBA", maat, (0, 0, 0, 0))
    for element in wortel:
        kleur = element.get("fill")
        if letters and kleur == "black":
            kleur = letters
        masker = Image.new("L", maat, 0)
        if element.tag == f"{_SVG}rect":
            b, h, r = (float(element.get(k, 0)) * schaal for k in ("width", "height", "rx"))
            ImageDraw.Draw(masker).rounded_rectangle((0, 0, b - 1, h - 1), radius=r, fill=255)
        elif element.tag == f"{_SVG}path":
            for vorm in paden(element.get("d")):
                los = Image.new("L", maat, 0)
                ImageDraw.Draw(los).polygon([(px * schaal, py * schaal) for px, py in vorm], fill=255)
                masker = ImageChops.logical_xor(masker.convert("1"), los.convert("1")).convert("L")
        else:
            continue
        vlak = Image.new("RGBA", maat, ImageColor.getrgb(kleur) + (255,))
        beeld = Image.composite(vlak, beeld, masker)
    return beeld.resize((maat[0] // _OVERMAAT, maat[1] // _OVERMAAT), Image.LANCZOS)


def _png(beeld: Image.Image) -> bytes:
    buf = io.BytesIO()
    beeld.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def vol_vierkant(maat: int) -> Image.Image:
    """Het logo op het volle oranje vierkant: voor iOS (dat zelf afrondt) en voor een avatar (rond uitgesneden)."""
    vlak = Image.new("RGB", (maat, maat), ImageColor.getrgb(ORANJE))
    logo = teken(LOGO.read_text(encoding="utf-8"), maat)
    vlak.paste(logo, (0, 0), logo)
    return vlak


def favicon_ico() -> bytes:
    logo = teken(LOGO.read_text(encoding="utf-8"), 48)
    buf = io.BytesIO()
    logo.save(buf, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    return buf.getvalue()


def deelbeeld() -> bytes:
    """Het beeld bij delen: de uitsnede van corpus met een zachte sluier en het woordmerk in wit, in het midden."""
    basis = Image.open(DEELBASIS).convert("RGB")
    sluier = Image.new("RGB", basis.size, (12, 13, 16))
    basis = Image.blend(basis, sluier, 0.25)
    merk = teken(WOORDMERK.read_text(encoding="utf-8"), 160, letters="white")
    basis.paste(merk, ((basis.width - merk.width) // 2, (basis.height - merk.height) // 2), merk)
    buf = io.BytesIO()
    basis.save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def _geist(grootte: int, gewicht: int) -> ImageFont.FreeTypeFont:
    letter = ImageFont.truetype(str(GEIST), grootte)
    letter.set_variation_by_axes([gewicht])
    return letter


def github_beeld(maat: tuple[int, int], uitsnede: tuple[int, int, int, int], merk: int, links: int, boven: int,
                 payoff: int, omschrijving: int) -> bytes:
    """Een beeld voor het openbare repo op donker (PLAN #34.2bl): het veld corpus met een sluier, links het woordmerk in
    wit, de pay-off en wat Factiz is; de lichtstreep van het veld onderin blijft vrij van tekst."""
    basis = Image.open(CORPUS).convert("RGB").crop(uitsnede).resize(maat, Image.LANCZOS)
    basis = Image.blend(basis, Image.new("RGB", maat, (12, 13, 16)), 0.25)
    woordmerk = teken(WOORDMERK.read_text(encoding="utf-8"), merk, letters="white")
    basis.paste(woordmerk, (links, boven), woordmerk)
    tekst = ImageDraw.Draw(basis)
    y = boven + merk + round(merk * 0.42)
    tekst.text((links + 4, y), PAYOFF, font=_geist(payoff, 560), fill=(255, 255, 255))
    tekst.text((links + 4, y + round(payoff * 1.45)), OMSCHRIJVING, font=_geist(omschrijving, 400), fill=(196, 202, 212))
    buf = io.BytesIO()
    basis.save(buf, "JPEG", quality=90, optimize=True, progressive=True)  # de korrel van het veld maakt een PNG ~1 MB
    return buf.getvalue()


# de social preview (GitHub vraagt 1280×640, onder 1 MB) en de banner boven de README
GITHUB = {
    "social-preview.jpg": lambda: github_beeld((1280, 640), (200, 0, 2000, 900), 118, 96, 128, 48, 30),
    "banner.jpg": lambda: github_beeld((1600, 520), (0, 120, 2000, 770), 112, 96, 84, 46, 29),
}


def inline_woordmerk() -> str:
    """Het woordmerk voor kop en voet: het oranje en wit van het logo vast, de letters in de tekstkleur, en voor een
    schermlezer verborgen (de link draagt de naam)."""
    svg = WOORDMERK.read_text(encoding="utf-8").strip()
    svg = svg.replace('fill="black"', 'fill="currentColor"')
    svg = re.sub(r'<svg width="\d+" height="\d+" ', '<svg class="woordmerk" aria-hidden="true" focusable="false" ', svg)
    # In HTML hoeft een SVG geen naamruimte; zo staat er geen http://-adres in de pagina.
    return svg.replace(' xmlns="http://www.w3.org/2000/svg"', "") + "\n"


def woordmerk_wit() -> str:
    """Het woordmerk voor een donkere grond, om te downloaden: de letters wit."""
    return WOORDMERK.read_text(encoding="utf-8").replace('fill="black"', 'fill="white"')


BEELDEN = {
    "apple-touch-icon.png": lambda: _png(vol_vierkant(180)),
    "favicon.ico": favicon_ico,
    "avatar.png": lambda: _png(vol_vierkant(1024)),
    "og.jpg": deelbeeld,
    "woordmerk-wit.svg": lambda: woordmerk_wit().encode("utf-8"),
    # het woordmerk op het deelplaatje per factcheck (PLAN #34.2aq): het platform plakt het, het tekent niets uit `doublecheck`
    "woordmerk-deel.png": lambda: _png(teken(WOORDMERK.read_text(encoding="utf-8"), 34)),
}

HERKOMST = """# Het logo en de beelden eruit (PLAN #23.18, DESIGN §4h)

Eén plek voor de site en het platform (PLAN #34.2f): `factiz_site/static/merk/`, gemaakt door
`python -m doublecheck.merkbeelden`; `tests/test_merkbeelden.py` eist dezelfde bytes.

- `logo.svg` en `woordmerk.svg`: van de PO, 2026-11-09. `logo.svg` is ook het icoon van de site.
- Getekend door het script, uit de vormen in die twee SVG's (geen download, geen beeldmodel):
  - `woordmerk-wit.svg`: de letters wit, voor een donkere grond.
  - `avatar.png`: 1024×1024, het logo op het volle oranje vierkant; de ovalen blijven binnen een cirkel.
  - `og.jpg`: 1200×630, het beeld bij delen: `../beeld/delen.jpg` (de uitsnede van corpus) met het woordmerk in wit.
  - `apple-touch-icon.png` (180×180, het volle vierkant) en `favicon.ico` (16, 32 en 48 pixels).
  - `woordmerk-deel.png`: 34 pixels hoog, de letters zwart, voor het deelplaatje per factcheck (PLAN #34.2aq).
- Voor het openbare repo (PLAN #34.2bl), in `.github/assets/`: `social-preview.jpg` (1280×640, in te stellen bij Settings,
  Social preview) en `banner.jpg` (boven de README), op het veld corpus met het woordmerk in wit, de pay-off en wat Factiz
  is, in Geist, de letter van de site.
- In kop en voet staat het woordmerk inline, uit `factiz_site/static/merk/woordmerk-inline.svg`: de letters in de tekstkleur.
"""


def main() -> None:  # pragma: no cover - schrijft de bestanden
    INLINE.write_text(inline_woordmerk(), encoding="utf-8")
    for naam, maak in BEELDEN.items():
        (MERK / naam).write_bytes(maak())
        print(f"{naam}: {(MERK / naam).stat().st_size // 1024} KB")
    GITHUB_MAP.mkdir(parents=True, exist_ok=True)
    for naam, maak in GITHUB.items():
        (GITHUB_MAP / naam).write_bytes(maak())
        print(f".github/assets/{naam}: {(GITHUB_MAP / naam).stat().st_size // 1024} KB")
    (MERK / "HERKOMST.md").write_text(HERKOMST, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    main()
