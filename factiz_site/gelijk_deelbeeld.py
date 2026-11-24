"""Het deelplaatje in TypeScript naast dat in Python (B80, PLAN #34.2bo stap 5).

    python -m factiz_site.gelijk_deelbeeld [<publicatie.db>] [--uit data/deelbeeld-vergelijk]

Pillow en resvg zetten een rand net anders, dus de plaatjes zijn nooit gelijk op de byte. Per adres tellen hier: dezelfde
status, dezelfde maat, het gemiddelde verschil per pixel (0 tot 255, over de drie kleuren) en het ergste vak (`verschil`).
Dat tweede vangt wat het gemiddelde verdunt: een teken in de verkeerde volgorde, een andere regelval of een woord dat
ontbreekt. Een stip of een nukta ziet geen maat die de rand van Pillow verdraagt; daarvoor zijn de vellen. Op een kopie van de uitgave, met een set die alle vijftien talen van de site
raakt en elk schrift met een lettertype (ook de schriften die de uitgave altijd vertaald toont: daar gaan de vertalingen
er in de kopie af), lange en korte beweringen, rechts naar links met cijfers en Latijnse woorden, thema's, onderdelen en
dossiers. De plaatjes blijven in het geheugen; alleen de vellen om naar te kijken gaan naar `--uit`, Python links en
TypeScript rechts. De TypeScript-kant heeft de voorraad nodig: `node scripts/deelbeeld-voorraad.ts` in `site/`.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from factiz_site import i18n

WORTEL = Path(__file__).resolve().parent.parent
SITE = WORTEL / "site"
UIT = WORTEL / "data" / "deelbeeld-vergelijk"

# De maat van een vak: 16 bij 16 pixels, beide plaatjes eerst vervaagd met een straal van 1,5 en het kleinste verschil over
# een verschuiving van hoogstens 3 pixels opzij en 1 omhoog of omlaag. Zo valt weg wat Pillow anders doet (de hinting van
# FreeType op elke rand, elk teken op een hele pixel, een opgetelde verschuiving van een paar pixels langs een regel) en
# blijft over wat er anders staat.
VAK = 16
VERVAAG = 1.5
SCHUIF = (3, 1)
# De grenzen, gemeten op 2026-11-16 (174 plaatjes van de set hieronder, en fouten met Pillow aan beide kanten in
# `tests/test_platform_ts_deelbeeld.py`). Het vak: TypeScript naast Python hoogstens 27,2 (een Turkse bewering), terwijl
# een echte fout hoger komt: een stip van een Arabische letter weg 35,6, een ander veld 43,4, een klinkerteken in het Hindi
# weg 57,1, een ander label 79, twee woorden om 101, een woord weg 150. Een nukta (17,4) valt eronder. Het gemiddelde:
# hoogstens 3,86 (drie dichte regels Thai, de rand van elk teken en de JPEG: Pillow 4:2:0, jpeg-js 4:4:4); een band zonder
# tekening geeft 20. Een fout in de tekst tilt het gemiddelde nauwelijks (0,04 tot 2,1), dus dat is alleen een vangnet.
GEMIDDELD = 5.0
VAK_GRENS = 31.0

# Schriften die de uitgave altijd vertaald toont: per taal van de bewering het schrift, voor de kopie zonder vertaling.
SCHRIFTEN = {"ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "gu": "Gujarati", "pa": "Gurmukhi",
             "si": "Sinhala", "th": "Thai", "km": "Khmer", "ko": "Hangul", "am": "Ethiopisch", "he": "Hebreeuws",
             "bn": "Bengaals", "as": "Bengaals (Assamees)", "mr": "Devanagari (Marathi)", "ne": "Devanagari (Nepali)",
             "ur": "Arabisch (Urdu)", "mn": "Cyrillisch (Mongools)", "tl": "Latijn (Filipijns)", "pl": "Latijn (Pools)"}
# Zelf gezet in de kopie: wat de uitgave niet heeft (Grieks staat er niet in) of zelden zo scherp (rechts naar links met
# cijfers en Latijn, een schrift zonder lettertype). De Griekse, Georgische en Birmaanse zinnen komen uit het corpus
# (`tests/schriften.py`).
GEZET = {
    "grieks": ("el", "Ρομπότ του διαδικτύου τσακώνονται στη Wikipedia για τον Μέγα Αλέξανδρο"),
    "arabisch-latijn": ("ar", "قال بيل غيتس إن لقاح COVID-19 يحتوي على شريحة 5G منذ عام 2021 حسب منشور على Facebook"),
    "perzisch-cijfers": ("fa", "زلنسکی در سال ۲۰۲۳ یک ویلا به ارزش ۸ میلیون دلار در Florida خرید (منبع: BBC)"),
    "hebreeuws-cijfers": ("he", "משרד הבריאות: 3 מתוך 10 חיסונים של Pfizer פגומים לפי דו\"ח מ-2022"),
    "arabisch-lang": ("ar", " ".join(["زعم منشور متداول على مواقع التواصل الاجتماعي أن الحكومة قررت إلغاء الدعم عن الخبز"] * 4)),
    "tamil-lang": ("ta", " ".join(["தடுப்பூசி போட்டவர்கள் இரண்டு ஆண்டுகளில் இறந்துவிடுவார்கள் என்று பரவும் தகவல்"] * 4)),
    "georgisch": ("ka", "ქრისტეს ხატი ჭიანჭველებმა დაწვას გადაარჩინეს"),
    "birmaans": ("my", "ဇီလန်စကီး အိမ်ဝယ်ခဲ့သည်"),
    "emoji": ("en", "🚨 BREAKING: the moon landing was filmed in a studio in 1969 🎬"),
}


def _node(bestand: Path, adressen: list[str], voorraad: Path | None = None) -> list[dict]:
    """De TypeScript-kant: `voorraad` is de map van `node scripts/deelbeeld-voorraad.ts`, standaard `data/deelbeeld/`."""
    omgeving = {**os.environ, **({"FACTIZ_DEELBEELD": str(voorraad)} if voorraad else {})}
    uit = subprocess.run(["node", "scripts/platform-vraag.ts", str(bestand)], input=json.dumps(adressen, ensure_ascii=False),
                         capture_output=True, text=True, cwd=SITE, timeout=3600, env=omgeving)
    if uit.returncode != 0:
        raise RuntimeError(uit.stderr[-3000:])
    return json.loads(uit.stdout)


def _python(bestand: Path, adressen: list[str]) -> list[tuple[int, bytes]]:
    from starlette.testclient import TestClient

    from factiz_site import app as fa
    c = TestClient(fa.maak_app(bestand), follow_redirects=False)
    return [(r.status_code, r.content if r.status_code == 200 else b"") for r in (c.get(a) for a in adressen)]


def verschil(py: bytes, ts: bytes) -> dict:
    """De maat van beide, het gemiddelde verschil per pixel en het ergste vak: per vak het kleinste verschil over een
    verschuiving binnen `SCHUIF`, op de vervaagde plaatjes (`VERVAAG`). Een rand die Pillow een pixel verder legt is geen
    fout, een teken dat er niet staat wel."""
    a = Image.open(io.BytesIO(py)).convert("RGB")
    b = Image.open(io.BytesIO(ts)).convert("RGB")
    if a.size != b.size:
        return {"maat": [a.size, b.size], "gemiddeld": None, "vak": None}
    gemiddeld = float(np.abs(np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)).mean())
    x = np.asarray(a.filter(ImageFilter.GaussianBlur(VERVAAG)), dtype=np.float32)
    y = np.asarray(b.filter(ImageFilter.GaussianBlur(VERVAAG)), dtype=np.float32)
    h, w = x.shape[:2]
    sx, sy = SCHUIF
    rand = np.pad(y, ((sy, sy), (sx, sx), (0, 0)), mode="edge")
    vakken = None
    for dy in range(-sy, sy + 1):
        for dx in range(-sx, sx + 1):
            d = np.abs(x - rand[sy + dy:sy + dy + h, sx + dx:sx + dx + w]).mean(axis=2)
            v = d[: h - h % VAK, : w - w % VAK].reshape(h // VAK, VAK, w // VAK, VAK).mean(axis=(1, 3))
            vakken = v if vakken is None else np.minimum(vakken, v)
    return {"maat": list(a.size), "gemiddeld": round(gemiddeld, 3), "vak": round(float(vakken.max()), 1)}


def kopie(bron: Path, map_: Path, zaad: int = 2026) -> tuple[Path, list[tuple[str, str]]]:
    """Een kopie van de uitgave met de schriften zichtbaar, en de adressen met wat ze toetsen."""
    doel = map_ / "publicatie.db"
    shutil.copyfile(bron, doel)
    c = sqlite3.connect(doel)
    kans = random.Random(zaad)
    adressen: list[tuple[str, str]] = []

    def kies(sql: str, *waarden, n: int = 1) -> list[str]:
        rijen = [r[0] for r in c.execute(sql, waarden)]
        return kans.sample(rijen, min(n, len(rijen)))

    kort = "SELECT nummer FROM pagina WHERE taal = ? AND length(bewering) BETWEEN 15 AND 70 ORDER BY nummer"
    lang = "SELECT nummer FROM pagina WHERE taal = ? AND length(bewering) > 230 ORDER BY nummer"
    # elke taal van de site: een korte en een lange bewering in die taal, en een willekeurige (vertaald of Engels)
    for taal in i18n.TALEN:
        for nr in kies(kort, taal) + kies(lang, taal):
            adressen.append((f"/api/{taal}/deelbeeld/{nr}.jpg", f"{taal}: eigen taal"))
        for nr in kies("SELECT nummer FROM pagina ORDER BY nummer"):
            adressen.append((f"/api/{taal}/deelbeeld/{nr}.jpg", f"{taal}: willekeurig"))
    # de schriften die anders vertaald staan: de vertalingen eraf in de kopie
    for code, schrift in SCHRIFTEN.items():
        nrs = kies(kort, code) + kies(lang, code)
        c.executemany("DELETE FROM vertaling WHERE pagina = ?", [(nr,) for nr in nrs])
        for nr, taal in zip(nrs, ("en", "ar")):
            adressen.append((f"/api/{taal}/deelbeeld/{nr}.jpg", f"{schrift}"))
    # zelf gezet, op Engelse pagina's met een redactie die er al was
    plekken = kies("SELECT nummer FROM pagina WHERE taal = 'en' ORDER BY nummer", n=len(GEZET))
    for (naam, (code, tekst)), nr in zip(GEZET.items(), plekken):
        c.execute("UPDATE pagina SET bewering = ?, taal = ? WHERE nummer = ?", (tekst, code, nr))
        c.execute("DELETE FROM vertaling WHERE pagina = ?", (nr,))
        for taal in ("en", "fa"):
            adressen.append((f"/api/{taal}/deelbeeld/{nr}.jpg", f"gezet: {naam}"))
    # een redactie met een naam van rechts naar links in een Engelse zin, en omgekeerd
    for nr in kies("SELECT pagina FROM check_ WHERE redactie IN ('فکت‌نامه', 'המשרוקית של גלובס', 'منصة تأكد') "
                   "ORDER BY pagina", n=3):
        adressen.append((f"/api/en/deelbeeld/{nr}.jpg", "redactie van rechts naar links"))
    # thema's, onderdelen en dossiers
    themas = [r[0] for r in c.execute("SELECT sleutel FROM thema WHERE ouder IS NULL ORDER BY volg")]
    delen = [r for r in c.execute("SELECT ouder, sleutel FROM thema WHERE ouder IS NOT NULL ORDER BY volg")]
    dossiers = [r[0] for r in c.execute("SELECT sleutel FROM dossier ORDER BY sleutel")]
    for thema in themas:
        for taal in ("en", "ar"):
            adressen.append((f"/api/{taal}/deelbeeld/thema/{thema}.jpg", "thema"))
    for i, taal in enumerate(i18n.TALEN):
        ouder, deel = delen[(i * 7) % len(delen)]
        adressen.append((f"/api/{taal}/deelbeeld/thema/{ouder}/{deel}.jpg", "onderdeel"))
        adressen.append((f"/api/{taal}/deelbeeld/thema/{themas[i % len(themas)]}.jpg", "thema"))
        adressen.append((f"/api/{taal}/deelbeeld/dossier/{dossiers[i % len(dossiers)]}.jpg", "dossier"))
    for d in dossiers:
        adressen.append((f"/api/fa/deelbeeld/dossier/{d}.jpg", "dossier"))
    # wat niet bestaat
    nr = plekken[0]
    for a in (f"/api/en/deelbeeld/{nr}.png", f"/api/en/deelbeeld/{nr[:-1]}.jpg", f"/api/en/deelbeeld/{nr.upper()}.jpg",
              "/api/en/deelbeeld/thema/geen.jpg", f"/api/en/deelbeeld/thema/{themas[0]}/geen.jpg",
              "/api/en/deelbeeld/dossier/geen.jpg", "/api/en/deelbeeld/dossier/a/b.jpg", "/api/en/deelbeeld/.jpg",
              "/api/en/deelbeeld/thema.jpg", f"/api/xx/deelbeeld/{nr}.jpg", f"/api/en/deelbeeld/zelf/{nr}.jpg"):
        adressen.append((a, "bestaat niet"))
    c.commit()
    c.close()
    return doel, adressen


def _onderschrift(beeld: Image.Image, tekst: str, x: int, y: int) -> None:
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:  # pragma: no cover - een oude Pillow
        font = ImageFont.load_default()
    ImageDraw.Draw(beeld).text((x, y), tekst, fill=(20, 20, 20), font=font)


def vellen(paren: list[tuple[str, dict, bytes, bytes]], uit: Path, per_vel: int = 4, schaal: float = 0.5) -> list[Path]:
    """Vellen om naar te kijken: per adres Python links en TypeScript rechts, verkleind, met het adres en de maat erboven."""
    uit.mkdir(parents=True, exist_ok=True)
    for oud in uit.glob("vel-*.png"):
        oud.unlink()
    w, h = round(1200 * schaal), round(630 * schaal)
    paden = []
    for v in range(0, len(paren), per_vel):
        stuk = paren[v:v + per_vel]
        vel = Image.new("RGB", (2 * w + 30, len(stuk) * (h + 30) + 10), (235, 235, 235))
        for i, (label, m, py, ts) in enumerate(stuk):
            y = 10 + i * (h + 30)
            _onderschrift(vel, f"{label}   gemiddeld {m['gemiddeld']}   vak {m['vak']}", 10, y)
            vel.paste(Image.open(io.BytesIO(py)).convert("RGB").resize((w, h), Image.LANCZOS), (10, y + 20))
            vel.paste(Image.open(io.BytesIO(ts)).convert("RGB").resize((w, h), Image.LANCZOS), (w + 20, y + 20))
        pad = uit / f"vel-{v // per_vel + 1:03d}.png"
        vel.save(pad, optimize=True)
        paden.append(pad)
    return paden


def vergelijk(bestand: Path, adressen: list[tuple[str, str]], voorraad: Path | None = None) -> list[dict]:
    """Per adres de status aan beide kanten en, bij 200, het verschil."""
    lijst = [a for a, _ in adressen]
    ts = _node(bestand, lijst, voorraad)
    py = _python(bestand, lijst)
    uit = []
    for (adres, wat), t, (status, inhoud) in zip(adressen, ts, py):
        r = {"adres": adres, "wat": wat, "status": [status, t["status"]], "fout": t.get("fout", "")[:400]}
        if status == t["status"] == 200:
            r["py"], r["ts"] = inhoud, base64.b64decode(t["bytes"])
            r.update(verschil(r["py"], r["ts"]))
        uit.append(r)
    return uit


def afwijkingen(uitslag: list[dict]) -> list[dict]:
    """Wat niet gelijk genoeg is: een andere status, een andere maat, of een verschil boven een grens."""
    return [r for r in uitslag if r["status"][0] != r["status"][1] or (r["status"][0] == 200 and (
        r["gemiddeld"] is None or r["gemiddeld"] > GEMIDDELD or r["vak"] > VAK_GRENS))]


def _standaard() -> Path:
    return sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))[-1]


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - een opdracht
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("bestand", nargs="?", type=Path, default=None)
    p.add_argument("--uit", type=Path, default=UIT)
    a = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tijdelijk:
        bestand, adressen = kopie(a.bestand or _standaard(), Path(tijdelijk))
        uitslag = vergelijk(bestand, adressen)
    beelden = [r for r in uitslag if "py" in r]
    paden = vellen([(f"{r['wat']}  {r['adres']}", r, r["py"], r["ts"]) for r in beelden], a.uit)
    per_wat: dict[str, list[dict]] = {}
    for r in beelden:
        per_wat.setdefault(r["wat"], []).append(r)
    print(f"{len(uitslag)} adressen, {len(beelden)} plaatjes, {len(paden)} vellen in {a.uit}")
    print(f"{'wat':<34} {'n':>3} {'gemiddeld':>10} {'hoogste':>8} {'vak':>6}")
    for wat, rijen in sorted(per_wat.items()):
        g = [r["gemiddeld"] for r in rijen if r["gemiddeld"] is not None]
        v = [r["vak"] for r in rijen if r["vak"] is not None]
        print(f"{wat:<34} {len(rijen):>3} {np.mean(g):>10.2f} {max(g):>8.2f} {max(v):>6.1f}")
    alle = [r["gemiddeld"] for r in beelden if r["gemiddeld"] is not None]
    print(f"alles: gemiddeld {np.mean(alle):.2f}, hoogste {max(alle):.2f}; grens {GEMIDDELD}, vak {VAK_GRENS}")
    fout = afwijkingen(uitslag)
    for r in fout:
        print("AFWIJKING", r["adres"], r["wat"], r["status"], r.get("gemiddeld"), r.get("vak"), r["fout"])
    return 1 if fout else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
