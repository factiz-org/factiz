"""Het beeld dat rondgaat, bij een eigen factcheck (PLAN #37.4, #37.5, B70, B82, DESIGN §4x).

Claude legt de post zelf vast, via de openbare insluitpagina van X in headless Chrome (`site/scripts/postbeeld.mjs`),
zonder inloggen. Het ruwe beeld blijft in het geheugen; op schijf komt alleen de bewerkte versie:

- zoals het rondging, met account en gezichten (PO 2026-11-18: "account, en gezichten kunnen blijven, allemaal op de
  openbare weg"); vervaagd alleen waar de check dat per beeld zegt, met een reden (`vervaag`, `vervaag_reden`: een
  minderjarige, gruwelijk beeld);
- zonder de knop om antwoorden te lezen, en nooit met een Community Note erin (DR3, #37.1): dan weigert de stap;
- verkleind tot hoogstens 640 pixels breed, als citaat (artikel 15a Auteurswet), met het oordeel als stempel schuin over
  het midden, zodat wie het beeld knipt de stempel meeknipt;
- als JPEG zonder metadata in `factiz_site/static/redactie/<sleutel>/<bestand>`, met de maat en het oordeel van het
  stempel in `content/redactie/<sleutel>/beelden.json`. `erbij` zet het pad en de maat in de check voor de uitgave en
  weigert een beeld met een ander oordeel dan de check (dan eerst opnieuw maken).

Welke post bij een check hoort, staat in `data/redactie/<sleutel>/beeld.json` (`{"post": "<nummer>"}`), buiten git: het
nummer wijst naar het account, en een post van een privépersoon linken we niet.

    python -m doublecheck.redactiebeeld maken [--sleutel a,b]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
from pathlib import Path

from doublecheck import redactie

WORTEL = Path(__file__).resolve().parent.parent
STATISCH = WORTEL / "factiz_site" / "static" / "redactie"
DOSSIERS = WORTEL / "data" / "redactie"
SCRIPT = WORTEL / "site" / "scripts" / "postbeeld.mjs"
LETTER = WORTEL / "factiz_site" / "fonts" / "noto" / "noto-sans" / "files" / "noto-sans-latin-wght-normal.woff2"
BREED = 640
# De kleuren van het label per oordeel, die van de site in het lichte thema (`--<soort>-inkt`, site.css)
INKT = {"onwaar": (122, 54, 0), "misleidend": (92, 80, 0), "context": (95, 82, 64), "grotendeels": (95, 82, 64),
        "klopt": (29, 74, 140), "onbewezen": (71, 77, 92)}


TOELICHTING = ("De beelden van deze eigen check zoals `python -m doublecheck.redactiebeeld maken` ze maakte (PLAN #37.5): "
               "per bestand het oordeel van het stempel en de maat in pixels. Het beeld is een citaat van een openbare post "
               "op X, verkleind en gestempeld door Factiz.")


class Weg(Exception):
    """De post staat niet meer op X (verwijderd, of het account geschorst)."""


def _vervaag(beeld, vak: list[float]):
    """Eén vak (x, y, breedte, hoogte, als deel van het beeld) onleesbaar: eerst grof gemaakt, dan vervaagd."""
    from PIL import Image, ImageFilter

    b, h = beeld.size
    x0, y0 = max(0, round(vak[0] * b)), max(0, round(vak[1] * h))
    x1, y1 = min(b, round((vak[0] + vak[2]) * b)), min(h, round((vak[1] + vak[3]) * h))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    stuk = beeld.crop((x0, y0, x1, y1))
    grof = stuk.resize((max(1, (x1 - x0) // 24), max(1, (y1 - y0) // 24)), Image.Resampling.BILINEAR)
    stuk = grof.resize(stuk.size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(6))
    beeld.paste(stuk, (x0, y0))


def label(oordeel: str, taal: str) -> str:
    """Het woord op het stempel, in de taal van de check (`redactie.oordeel_tekst`)."""
    return redactie.oordeel_tekst(oordeel, taal)


def _lettertype(teken: str, tekst: str) -> Path | None:
    """Het lettertype voor een teken van het stempel: het Latijn van Noto Sans zoals altijd, anders Noto Sans in het schrift
    van het teken (dezelfde bestanden als het deelplaatje, factiz_site/deelbeeld.py)."""
    from factiz_site import deelbeeld as db

    code = ord(teken)
    for bestand, reeksen in db._volgorde(db.cjk_variant(tekst)):
        if bestand.startswith("noto/") and any(a <= code <= b for a, b in reeksen):
            pad = db.FONTS / bestand
            return LETTER if pad == LETTER else pad
    return None


# schriften waarin letters los staan: daar krijgt het stempel ruimte tussen de letters; in de andere (Arabisch, Devanagari)
# hangen de letters aan elkaar en gaat een woord in één keer
def _los(pad: Path) -> bool:
    naam = pad.name
    return pad == LETTER or naam.startswith(("noto-sans-latin", "noto-sans-cyrillic", "noto-sans-greek", "noto-sans-vietnamese",
                                             "noto-sans-jp", "noto-sans-tc", "noto-sans-sc", "noto-sans-kr"))


def _stempel(beeld, tekst: str, inkt: tuple[int, int, int]):
    """Het oordeel in hoofdletters, in een dubbel kader op een doorschijnend lichte ondergrond (de tekst eronder blijft
    te lezen), 12 graden schuin over het midden."""
    from PIL import Image, ImageDraw, ImageFont

    b = beeld.size[0]
    tekst = tekst.upper()
    paden = [LETTER if ch.isspace() else (_lettertype(ch, tekst) or LETTER) for ch in tekst]
    # de stukken: een los teken, of een woord in een schrift waarin de letters aan elkaar hangen (een spatie blijft erbij)
    stukken: list[tuple[str, Path]] = []
    for ch, pad in zip(tekst, paden):
        if stukken and not _los(pad) and (stukken[-1][1] == pad or ch.isspace()) and not _los(stukken[-1][1]):
            stukken[-1] = (stukken[-1][0] + ch, stukken[-1][1])
        elif stukken and ch.isspace() and not _los(stukken[-1][1]):
            stukken[-1] = (stukken[-1][0] + ch, stukken[-1][1])
        else:
            stukken.append((ch, pad))
    grootte = max(18, round(b * 0.068))
    while True:     # een lang oordeel (ONTBREKENDE CONTEXT) kleiner, zodat het stempel schuin binnen het beeld blijft
        fonts = {}
        for pad in {p for _, p in stukken} | {LETTER}:
            fonts[pad] = ImageFont.truetype(str(pad), grootte)
            fonts[pad].set_variation_by_axes([800])
        letter = fonts[LETTER]
        ruimte = round(grootte * 0.12)
        breedtes = [fonts[p].getlength(t) for t, p in stukken]
        tekstbreed = round(sum(breedtes) + ruimte * (len(stukken) - 1))
        if tekstbreed + 1.4 * grootte <= 0.72 * b or grootte <= 18:
            break
        grootte -= 2
    boven, onder = letter.getbbox("ÀMg")[1], letter.getbbox("MX")[3]
    for t, p in stukken:          # een ander schrift kan hoger of lager reiken dan het Latijn
        if p != LETTER and t.strip():
            vak_t = fonts[p].getbbox(t)
            boven, onder = min(boven, vak_t[1]), max(onder, vak_t[3])
    lijn, rand = max(2, round(grootte * 0.07)), round(grootte * 0.6)
    vak = (tekstbreed + 2 * rand, (onder - boven) + 2 * round(grootte * 0.32))
    laag = Image.new("RGBA", (vak[0] + 4 * lijn, vak[1] + 4 * lijn), (0, 0, 0, 0))
    teken = ImageDraw.Draw(laag)
    buiten = (lijn, lijn, laag.size[0] - lijn - 1, laag.size[1] - lijn - 1)
    teken.rounded_rectangle(buiten, radius=lijn * 2, fill=(255, 255, 255, 150), outline=inkt + (255,), width=lijn)
    binnen = (buiten[0] + 2 * lijn, buiten[1] + 2 * lijn, buiten[2] - 2 * lijn, buiten[3] - 2 * lijn)
    teken.rounded_rectangle(binnen, radius=lijn, outline=inkt + (255,), width=max(1, lijn // 2))
    x, y = (laag.size[0] - tekstbreed) / 2, (laag.size[1] - (onder - boven)) / 2 - boven
    for (t, p), w in zip(stukken, breedtes):
        teken.text((x, y), t, font=fonts[p], fill=inkt + (255,))
        x += w + ruimte
    laag = laag.rotate(12, resample=Image.Resampling.BICUBIC, expand=True)
    plek = ((beeld.size[0] - laag.size[0]) // 2, (beeld.size[1] - laag.size[1]) // 2)
    beeld.paste(laag, plek, laag)


def bewerk(png: bytes, meta: dict, oordeel: str, taal: str = "nl", vervaag: list | None = None) -> bytes:
    """Het vastgelegde beeld van een post (`postbeeld.mjs`) klaar voor de site, in het geheugen. `meta` zegt in pixels
    van de pagina hoe breed de post is (`w`) en waar de bediening begint (`onder`); `vervaag` zijn de vakken die
    onleesbaar moeten, als deel van het geknipte beeld. Weigert een post met een Community Note erin."""
    from PIL import Image

    if meta.get("onbeschikbaar") or meta.get("fout") or meta.get("tekst") == "Niet gevonden" or meta.get("h", 0) < 100:
        raise Weg(meta.get("tekst") or meta.get("fout") or "de post laat niets zien")
    if meta.get("note"):
        raise redactie.Weigering("er staat een Community Note in de post; die komt nooit op de site")
    beeld = Image.open(io.BytesIO(png)).convert("RGB")
    schaal = beeld.size[0] / meta["w"] if meta.get("w") else 1
    onder = round(meta.get("onder", meta.get("h", beeld.size[1] / schaal)) * schaal)
    beeld = beeld.crop((0, 0, beeld.size[0], max(1, min(beeld.size[1], onder))))
    for vak in vervaag or []:
        _vervaag(beeld, vak)
    if beeld.size[0] > BREED:
        beeld = beeld.resize((BREED, round(beeld.size[1] * BREED / beeld.size[0])), Image.Resampling.LANCZOS)
    _stempel(beeld, label(oordeel, taal), INKT[oordeel])
    uit = io.BytesIO()
    beeld.save(uit, format="JPEG", quality=86, optimize=True, progressive=True)   # een nieuw beeld: geen metadata
    return uit.getvalue()


def vastleggen(nummers: list[str]) -> dict[str, tuple[bytes | None, dict]]:  # pragma: no cover - met Chrome en X
    """Per postnummer het ruwe beeld (alleen in het geheugen) en wat de pagina erover zei. Een nummer mag `:<taal>`
    dragen: dan staan de knoppen en de datum van X in die taal (die van de check), anders in het Nederlands."""
    uit = subprocess.run(["node", str(SCRIPT), *nummers], capture_output=True, text=True, check=True, timeout=60 * len(nummers) + 60)
    gezien = {}
    for regel in uit.stdout.splitlines():
        meta = json.loads(regel)
        ruw = meta.pop("beeld")
        gezien[meta["nummer"]] = (base64.b64decode(ruw) if ruw else None, meta)
    return gezien


def erbij(check: dict, statisch: Path = STATISCH, inhoud: Path = redactie.MAP) -> dict:
    """De check met het pad en de maat van elk beeld dat gemaakt is, voor de uitgave. Weigert een beeld waarvan het
    stempel een ander oordeel zegt dan de check: dan eerst `maken`."""
    sleutel = check["sleutel"]
    lijst = inhoud / sleutel / "beelden.json"
    gemaakt = json.loads(lijst.read_text(encoding="utf-8")) if lijst.exists() else {}
    beelden = []
    for b in check.get("beeld") or []:
        b = dict(b)
        info = gemaakt.get(b.get("bestand") or "")
        if info and (statisch / sleutel / b["bestand"]).exists():
            if info["oordeel"] != check["oordeel"]:
                raise redactie.Weigering(f"{sleutel}: het stempel op {b['bestand']} zegt {info['oordeel']}, de check "
                                         f"{check['oordeel']}; maak het beeld opnieuw (redactiebeeld maken)")
            b.update(pad=f"/static/redactie/{sleutel}/{b['bestand']}", breedte=info["breedte"], hoogte=info["hoogte"])
        beelden.append(b)
    return {**check, "beeld": beelden} if check.get("beeld") else dict(check)


def maak(sleutels: list[str] | None = None) -> None:  # pragma: no cover - met Chrome en X
    from PIL import Image

    checks = [c for c in redactie.lees_alle() if not sleutels or c["sleutel"] in sleutels]
    taken = []
    for c in checks:
        pad = DOSSIERS / c["sleutel"] / "beeld.json"
        beeld = next((b for b in c.get("beeld") or [] if b.get("rol") == "rondgaat" and b.get("bestand")), None)
        if not beeld or not pad.exists():
            print(f"{c['sleutel']}: geen post of geen beeld dat rondgaat in de check")
            continue
        taken.append((c, beeld, json.loads(pad.read_text(encoding="utf-8"))["post"]))
    gezien = vastleggen([f"{post}:{c['taal']}" for c, _, post in taken])
    for c, b, post in taken:
        ruw, meta = gezien.get(post, (None, {"fout": "niet vastgelegd"}))
        try:
            klaar = bewerk(ruw or b"", meta, c["oordeel"], c["taal"], b.get("vervaag"))
        except Weg as e:
            print(f"{c['sleutel']}: de post is weg ({e})")
            continue
        except redactie.Weigering as e:
            print(f"{c['sleutel']}: geweigerd, {e}")
            continue
        doel = STATISCH / c["sleutel"] / b["bestand"]
        doel.parent.mkdir(parents=True, exist_ok=True)
        doel.write_bytes(klaar)
        maat = Image.open(io.BytesIO(klaar)).size
        lijst = redactie.MAP / c["sleutel"] / "beelden.json"
        gemaakt = json.loads(lijst.read_text(encoding="utf-8")) if lijst.exists() else {}
        gemaakt[b["bestand"]] = {"oordeel": c["oordeel"], "breedte": maat[0], "hoogte": maat[1]}
        gemaakt["toelichting"] = TOELICHTING     # de herkomst van het bestand (tests/test_licenties.py)
        lijst.write_text(json.dumps(gemaakt, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{c['sleutel']}: {doel.relative_to(WORTEL)}, {maat[0]} bij {maat[1]}")


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(prog="python -m doublecheck.redactiebeeld")
    sub = p.add_subparsers(dest="stap", required=True)
    m = sub.add_parser("maken")
    m.add_argument("--sleutel", help="alleen deze checks, met komma's")
    a = p.parse_args(argv)
    if a.stap == "maken":
        maak(a.sleutel.split(",") if a.sleutel else None)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
