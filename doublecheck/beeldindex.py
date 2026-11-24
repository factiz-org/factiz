"""De beelden die rondgingen indexeren (PLAN.md #25.11).

Tot nu toe had de productie-index geen enkele beeldhash: een screenshot werd
alleen gevonden via de tekst die de OCR erop las. Een factcheckartikel toont
het virale beeld meestal zelf. Dit leest per artikel het deelbeeld en de
beelden in het inhoudsblok (de selectie uit #25.12), uitsluitend in het
geheugen (DR3), en bewaart alleen wat een beeld niet terug kan geven: de
PDQ-hash, de kwaliteit die PDQ erbij geeft, de maat, en de adressen van beeld
en artikel. Bij het oogsten maken we ook de kopieën waarmee gemeten wordt
(opnieuw gecomprimeerd, half zo groot, met een stempel, bijgesneden, in een
kader) en bewaren daarvan alleen de hash.

Gemeten met de regel dat een vraag nooit de beelden van haar eigen claim
vindt. De kruistoets zet het beeld van de ene redactie tegen dat van de
andere: dat zijn echte kopieën, met hun eigen stempel en compressie. In de
resolver alleen met een release (B22).

    python -m doublecheck.beeldindex oogsten [--max 50]
    python -m doublecheck.beeldindex meten
"""

from __future__ import annotations

import collections
import io
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from doublecheck.image_fingerprint import as_image, pdq_met_kwaliteit

MAP = Path("data/beeldindex")
MAX_BEELDEN = 6
MIN_KWALITEIT = 50          # onder deze PDQ-kwaliteit zegt een hash weinig (vlakke beelden)
MIN_ZIJDE = 200             # zoals de HTML-filter van #25.12, maar op de echte maat
_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(axis=1)


# --- één beeld ------------------------------------------------------------------

def _jpeg(beeld: Image.Image, kwaliteit: int) -> Image.Image:
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=kwaliteit)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _stempel(beeld: Image.Image) -> Image.Image:
    """Een rode band met "FALSE" over het midden, zoals redacties hun kopie
    van het virale beeld merken."""
    uit = beeld.copy()
    b, h = uit.size
    band = max(12, h // 5)
    teken = ImageDraw.Draw(uit)
    teken.rectangle([0, (h - band) // 2, b, (h + band) // 2], fill=(200, 20, 20))
    lettertype = ImageFont.load_default(size=max(10, int(band * 0.7)))
    teken.text((b // 2, h // 2), "FALSE", fill="white", font=lettertype, anchor="mm")
    return uit


def _bijgesneden(beeld: Image.Image, fractie: float = 0.10) -> Image.Image:
    b, h = beeld.size
    return beeld.crop((int(b * fractie), int(h * fractie), int(b * (1 - fractie)), int(h * (1 - fractie))))


def _kader(beeld: Image.Image) -> Image.Image:
    """Het beeld als deel van een schermafbeelding: een witte kop met regels
    erboven en een strook eronder, zoals een post in een tijdlijn."""
    b, h = beeld.size
    kop, voet = int(h * 0.30), int(h * 0.12)
    uit = Image.new("RGB", (b, h + kop + voet), "white")
    uit.paste(beeld, (0, kop))
    teken = ImageDraw.Draw(uit)
    for i, breedte in enumerate((0.45, 0.85, 0.7)):
        y = int(kop * (0.2 + 0.25 * i))
        teken.rectangle([int(b * 0.05), y, int(b * breedte), y + max(4, kop // 10)], fill=(90, 90, 90))
    return uit


def verwerk_beeld(inhoud: bytes, versie: str) -> dict:
    """Hash, kwaliteit, maat en de hashes van de vijf kopieën; het beeld zelf
    verlaat deze functie niet."""
    if versie != "pdq-256-v1":
        raise ValueError(f"de beeldindex kent alleen pdq-256-v1, niet {versie!r}")
    beeld = as_image(inhoud).convert("RGB")
    hexa, kwaliteit = pdq_met_kwaliteit(beeld)
    b, h = beeld.size
    kopieen = {
        "jpeg50": _jpeg(beeld, 50),
        "half": beeld.resize((max(1, b // 2), max(1, h // 2))),
        "stempel": _stempel(beeld),
        "bijgesneden": _bijgesneden(beeld),
        "kader": _kader(beeld),
    }
    return {"pdq": hexa, "kwaliteit": kwaliteit, "breedte": b, "hoogte": h,
            "proeven": {soort: pdq_met_kwaliteit(k)[0] for soort, k in kopieen.items()}}


# --- het oogsten ----------------------------------------------------------------

def pilotartikelen(conn: sqlite3.Connection, m4fc_urls: set[str]) -> list[tuple[str, str]]:
    """De artikelen waar een echte wilde kopie kan bestaan: in clusters met
    twee of meer redacties (hosts), plus de M4FC-artikelen."""
    rijen = conn.execute(
        "SELECT c.claim_id, c.cluster_id, f.url FROM claim c JOIN factcheck f ON f.claim_id = c.claim_id"
    ).fetchall()
    hosts = collections.defaultdict(set)
    for _, cluster, url in rijen:
        if cluster:
            hosts[cluster].add(urlsplit(url).hostname)
    m4fc = {_gelijk(u) for u in m4fc_urls}
    gekozen = {(cid, url) for cid, cluster, url in rijen
               if (cluster and len(hosts[cluster]) >= 2) or _gelijk(url) in m4fc}
    return sorted(gekozen)


def _gelijk(url: str) -> str:
    """Hetzelfde artikel, ook als de een er een slash achter zet en de ander
    niet (M4FC tegenover de feed)."""
    return url.strip().rstrip("/").lower()


def herstel(pad: Path) -> None:
    """Knipt een halve laatste regel af, zodat een hervatte oogst er niet
    aan vast schrijft."""
    if not pad.exists():
        return
    inhoud = pad.read_bytes()
    if inhoud and not inhoud.endswith(b"\n"):
        pad.write_bytes(inhoud[:inhoud.rfind(b"\n") + 1])


def mag(robots, url: str) -> bool:
    """Geen robots.txt (of onleesbaar): geen verbod."""
    return robots is None or robots.can_fetch(_AGENT, url)


_AGENT = "FactizResearch"
_KOP = {"User-Agent": f"Mozilla/5.0 ({_AGENT}; hashes the images in fact-check articles for an image index, stores no"
                      " image; https://factiz.org)"}
OPNIEUW = {"fout", 429, 503}   # een artikel met deze uitkomst wordt bij hervatten nog eens geprobeerd


def _robots(web, host: str):
    import urllib.robotparser

    from doublecheck.artikelbeelden import _haal

    antwoord = _haal(web, f"https://{host}/robots.txt")
    if antwoord is None or antwoord.status_code != 200:
        return None
    lezer = urllib.robotparser.RobotFileParser()
    lezer.parse(antwoord.text.splitlines())
    return lezer


def _lees(map_: Path) -> list[dict]:
    pad = map_ / "regels.jsonl"
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    inhoud = inhoud[:inhoud.rfind("\n") + 1]
    return [json.loads(r) for r in inhoud.splitlines() if r.strip()]


def laatste(regels: list[dict]) -> list[dict]:
    """Per artikel de laatste regel: een hervatte oogst schrijft een tweede poging achter de eerste."""
    return list({r["url"]: r for r in regels}.values())


def oogst(map_: Path, artikelen: list[tuple[str, str]], versie: str, *, threads: int = 6,
          pauze: float = 2.0, max_beelden: int = MAX_BEELDEN, verwerk=None,
          wacht_bij_limiet: float = 60.0) -> collections.Counter:
    """Per host één verzoek tegelijk met `pauze` ertussen; hosts parallel.
    Hervatbaar: een artikel met een regel wordt overgeslagen, behalve na een
    netwerkfout, 429 of 503 (`OPNIEUW`). Bij 429 of 503 eerst
    `wacht_bij_limiet` seconden wachten en het één keer opnieuw vragen.
    `verwerk(inhoud)` maakt van de bytes van een beeld wat er bewaard wordt;
    één beeld tegelijk, zodat het rekenen binnen twee kernen blijft."""
    import concurrent.futures as cf
    import threading
    import time

    import httpx

    from doublecheck.api import MAX_IMAGE_BYTES
    from doublecheck.artikelbeelden import _haal, beelden_uit_artikel

    verwerk = verwerk or (lambda inhoud: verwerk_beeld(inhoud, versie))
    rekenen = threading.Lock()
    herstel(map_ / "regels.jsonl")
    klaar = {r["url"] for r in laatste(_lees(map_)) if r["status"] not in OPNIEUW}
    per_host = collections.defaultdict(list)
    for cid, url in artikelen:
        if url not in klaar:
            per_host[urlsplit(url).hostname].append((cid, url))
    map_.mkdir(parents=True, exist_ok=True)
    schrijf = threading.Lock()
    teller = collections.Counter()

    def host_werk(werk):
        with httpx.Client(headers=_KOP, follow_redirects=True, timeout=20) as web:
            robots = _robots(web, urlsplit(werk[0][1]).hostname)
            for cid, url in werk:
                beelden, status = [], "verboden"
                if mag(robots, url):
                    pagina = _haal(web, url)
                    if pagina is not None and pagina.status_code in (429, 503):
                        time.sleep(wacht_bij_limiet)
                        pagina = _haal(web, url)
                    status = "fout" if pagina is None else pagina.status_code
                    adressen = beelden_uit_artikel(pagina.text, str(pagina.url))[:max_beelden] \
                        if pagina is not None and pagina.status_code == 200 else []
                    for adres in adressen:
                        time.sleep(pauze)
                        if not mag(robots, adres) and urlsplit(adres).hostname == urlsplit(url).hostname:
                            continue
                        antwoord = _haal(web, adres)
                        if antwoord is None or antwoord.status_code != 200 or len(antwoord.content) > MAX_IMAGE_BYTES:
                            continue
                        try:
                            with rekenen:
                                beelden.append({"beeld": adres, **verwerk(antwoord.content)})
                        except Exception:   # geen beeld, kapot of te groot: overslaan, nooit loggen (DR3)
                            continue
                with schrijf:
                    with (map_ / "regels.jsonl").open("a", encoding="utf-8") as uit:
                        uit.write(json.dumps({"claim_id": cid, "url": url, "versie": versie, "status": status,
                                              "beelden": beelden}, ensure_ascii=False) + "\n")
                    teller["artikelen"] += 1
                    teller["met beeld"] += bool(beelden)
                    teller["beelden"] += len(beelden)
                    teller[f"status {status}"] += 1
                    if teller["artikelen"] % 100 == 0:
                        print(f"  {dict(teller)}", flush=True)
                time.sleep(pauze)

    with cf.ThreadPoolExecutor(threads) as pool:
        list(pool.map(host_werk, sorted(per_host.values(), key=len, reverse=True)))
    return teller


# --- meten ----------------------------------------------------------------------

@dataclass(frozen=True)
class Beeld:
    claim_id: str
    artikel: str
    url: str
    pdq: bytes
    kwaliteit: int
    proeven: dict = field(default_factory=dict, compare=False)


def afstand(een: bytes, twee: bytes) -> int:
    return int(_POPCOUNT[np.frombuffer(een, dtype=np.uint8) ^ np.frombuffer(twee, dtype=np.uint8)].sum())


def _matrix(beelden) -> np.ndarray:
    if not beelden:
        return np.empty((0, 32), dtype=np.uint8)
    return np.vstack([np.frombuffer(b.pdq, dtype=np.uint8) for b in beelden])


def _afstanden(vraag: bytes, matrix: np.ndarray) -> np.ndarray:
    return _POPCOUNT[matrix ^ np.frombuffer(vraag, dtype=np.uint8)].sum(axis=1)


def beelden_uit_regels(regels: list[dict], min_zijde: int = MIN_ZIJDE) -> list[Beeld]:
    """De beelden die een virale foto kunnen zijn: de HTML geeft niet altijd
    een maat op, dus de echte maat beslist."""
    return [Beeld(r["claim_id"], r["url"], b["beeld"], bytes.fromhex(b["pdq"]), b["kwaliteit"], b.get("proeven", {}))
            for r in regels for b in r["beelden"]
            if min(b.get("breedte", min_zijde), b.get("hoogte", min_zijde)) >= min_zijde]


def sjablonen(beelden: list[Beeld], groep: dict[str, str], drempel: int, min_groepen: int = 3) -> set[int]:
    """Huisstijl, geen viraal beeld. Drie vormen: hetzelfde adres bij claims
    in twee of meer clusters (een auteursfoto, een oordeelsmeter); (bijna)
    dezelfde hash bij twee of meer clusters van één redactie (een kaartje in
    de huisstijl); of (bijna) dezelfde hash bij `min_groepen` of meer clusters
    over redacties heen. Een virale foto bij twee redacties blijft staan."""
    groepen = np.array([groep.get(b.claim_id, b.claim_id) for b in beelden], dtype=object)
    hosts = np.array([urlsplit(b.artikel).hostname for b in beelden], dtype=object)
    per_url = collections.defaultdict(set)
    for b, g in zip(beelden, groepen):
        per_url[b.url].add(g)
    weg = {i for i, b in enumerate(beelden) if len(per_url[b.url]) >= 2}
    matrix = _matrix(beelden)
    for i, b in enumerate(beelden):
        if i in weg:
            continue
        dichtbij = np.nonzero(_afstanden(b.pdq, matrix) <= drempel)[0]
        if len(set(groepen[dichtbij])) >= min_groepen \
                or len(set(groepen[dichtbij[hosts[dichtbij] == hosts[i]]])) >= 2:
            weg.add(i)
    return weg


def verzamelartikelen(regels: list[dict], groep: dict[str, str]) -> set[str]:
    """Artikelen die beweringen uit verschillende clusters checken (een
    speech, een debat): hun beelden horen bij geen van die beweringen."""
    per_url = collections.defaultdict(set)
    for r in regels:
        per_url[r["url"]].add(groep.get(r["claim_id"], r["claim_id"]))
    return {url for url, gs in per_url.items() if len(gs) >= 2}


def _dichtste(vraag: bytes, matrix: np.ndarray, uitsluiten: np.ndarray | None):
    d = _afstanden(vraag, matrix).astype(np.int64)
    if uitsluiten is not None:
        d[uitsluiten] = 10_000
    j = int(np.argmin(d)) if len(d) else -1
    return j, (int(d[j]) if j >= 0 else 10_000)


def kruistoets(beelden: list[Beeld], groep: dict[str, str], drempel: int) -> collections.Counter:
    """Elk beeld als vraag tegen alle andere, zonder de beelden van de eigen
    claim. Goed als de dichtste binnen `drempel` in hetzelfde cluster valt."""
    matrix = _matrix(beelden)
    claims = np.array([b.claim_id for b in beelden], dtype=object)
    uit = collections.Counter(goed=0, fout=0, niets=0, goed_andere_host=0, fout_andere_host=0)
    for b in beelden:
        j, d = _dichtste(b.pdq, matrix, claims == b.claim_id)
        if j < 0 or d > drempel:
            uit["niets"] += 1
            continue
        if groep.get(beelden[j].claim_id, beelden[j].claim_id) == groep.get(b.claim_id, b.claim_id):
            uit["goed"] += 1
            uit["goed_andere_host"] += urlsplit(beelden[j].artikel).hostname != urlsplit(b.artikel).hostname
        else:
            uit["fout"] += 1
            uit["fout_andere_host"] += urlsplit(beelden[j].artikel).hostname != urlsplit(b.artikel).hostname
    return uit


def kopietoets(beelden: list[Beeld], groep: dict[str, str], drempel: int) -> dict[str, dict[str, int]]:
    """Per soort kopie: vindt een bewerkte versie van een geïndexeerd beeld
    haar eigen claim (of het cluster daarvan) terug?"""
    matrix = _matrix(beelden)
    uit: dict[str, dict[str, int]] = {}
    for b in beelden:
        for soort, hexa in b.proeven.items():
            tel = uit.setdefault(soort, {"goed": 0, "fout": 0, "niets": 0})
            j, d = _dichtste(bytes.fromhex(hexa), matrix, None)
            if j < 0 or d > drempel:
                tel["niets"] += 1
            elif groep.get(beelden[j].claim_id, beelden[j].claim_id) == groep.get(b.claim_id, b.claim_id):
                tel["goed"] += 1
            else:
                tel["fout"] += 1
    return uit


def valse_treffers(buiten: list[bytes], beelden: list[Beeld], drempel: int) -> int:
    """Hoeveel beelden die niet in de index staan toch binnen `drempel` van
    een geïndexeerd beeld vallen."""
    matrix = _matrix(beelden)
    return sum(1 for h in buiten if len(matrix) and int(_afstanden(h, matrix).min()) <= drempel)


# --- opdrachtregel --------------------------------------------------------------

def _m4fc_beeld(map_: Path, sleutel: str) -> Path | None:
    """M4FC noemt zijn beelden `00703.png` bij sleutel `703`."""
    for naam in (sleutel, sleutel.zfill(5)):
        gevonden = next(Path(map_).glob(f"{naam}.*"), None)
        if gevonden is not None:
            return gevonden
    return None


def _m4fc(pad: Path) -> dict:
    bestand = pad / "gekoppeld.json"
    return json.loads(bestand.read_text(encoding="utf-8")) if bestand.exists() else {}


def _meet(conn, config, map_: Path) -> None:
    import random

    from doublecheck.benchmark import upper_bound_95
    from doublecheck.benchmark_images import render_claim

    drempel = config.thresholds.image_same
    regels = _lees(map_)
    groep = {cid: (cl or cid) for cid, cl in conn.execute("SELECT claim_id, cluster_id FROM claim")}
    verzameld = verzamelartikelen(regels, groep)
    alle = beelden_uit_regels([r for r in regels if r["url"] not in verzameld])
    status = collections.Counter(str(r["status"]) for r in regels)
    print(f"{len(regels)} artikelen ({dict(status.most_common(6))}), {sum(bool(r['beelden']) for r in regels)}"
          f" met beeld, {sum(len(r['beelden']) for r in regels)} beelden, {len(alle)} van {MIN_ZIJDE} pixels of meer")
    goed = [b for b in alle if b.kwaliteit >= MIN_KWALITEIT]
    weg = sjablonen(goed, groep, drempel)
    index = [b for i, b in enumerate(goed) if i not in weg]
    print(f"verzamelartikelen: {len(verzameld)}; kwaliteit < {MIN_KWALITEIT}: {len(alle) - len(goed)};"
          f" sjablonen: {len(weg)}; in de index: {len(index)}"
          f" bij {len({b.claim_id for b in index})} claims")
    voorbeelden = collections.Counter(urlsplit(goed[i].url).hostname for i in weg).most_common(5)
    print(f"  sjablonen vooral bij: {voorbeelden}")

    kruis = kruistoets(index, groep, drempel)
    n = sum(kruis[k] for k in ("goed", "fout", "niets"))
    print(f"kruistoets ({n} vragen, eigen claim uitgesloten): goed {kruis['goed']} (andere redactie"
          f" {kruis['goed_andere_host']}), fout {kruis['fout']} (andere redactie {kruis['fout_andere_host']}),"
          f" niets {kruis['niets']};"
          f" fout per treffer: bovengrens {upper_bound_95(kruis['fout'], kruis['goed'] + kruis['fout']):.1%}")
    for soort, tel in sorted(kopietoets(index, groep, drempel).items()):
        print(f"kopie {soort:<12} goed {tel['goed']:>5}  fout {tel['fout']:>3}  niets {tel['niets']:>5}")

    random.seed(25_11)
    teksten = [t for (t,) in conn.execute("SELECT canonical_text FROM claim ORDER BY random() LIMIT 3000")]
    buiten = []
    for tekst in teksten:
        if len(buiten) == 1000:
            break
        try:
            buiten.append(bytes.fromhex(pdq_met_kwaliteit(render_claim(tekst[:200]))[0]))
        except Exception:
            continue
    vals = valse_treffers(buiten, index, drempel)
    print(f"valse treffers op {len(buiten)} beelden buiten de index: {vals}"
          f" (bovengrens {upper_bound_95(vals, len(buiten)):.2%})")

    m4fc = _m4fc(Path("data/extern/m4fc"))
    if m4fc:
        per_artikel = collections.defaultdict(list)
        for b in index:
            per_artikel[_gelijk(b.artikel)].append(b)
        matrix = _matrix(index)
        claims = np.array([b.claim_id for b in index], dtype=object)
        tel = collections.Counter()
        for sleutel, item in m4fc.items():
            pad = _m4fc_beeld(Path("data/extern/m4fc/beelden"), sleutel)
            if pad is None:
                continue
            try:
                h = bytes.fromhex(pdq_met_kwaliteit(Image.open(pad))[0])
            except Exception:
                continue
            tel["beelden"] += 1
            eigen = per_artikel.get(_gelijk(item["article_url"]), [])
            tel["in eigen artikel teruggevonden"] += any(afstand(h, b.pdq) <= drempel for b in eigen)
            j, d = _dichtste(h, matrix, claims == item["claim_id"]) if len(index) else (-1, 10_000)
            if j < 0 or d > drempel:
                tel["elders: niets"] += 1
            elif groep.get(index[j].claim_id) == groep.get(item["claim_id"], item["claim_id"]):
                tel["elders: goed"] += 1
            else:
                tel["elders: fout"] += 1
        print(f"M4FC: {dict(tel)}")


def main() -> None:
    import argparse
    import os

    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="De beelden die rondgingen indexeren (#25.11)")
    parser.add_argument("stap", choices=("oogsten", "meten"))
    parser.add_argument("--map", default=str(MAP))
    parser.add_argument("--max", type=int, help="hooguit zoveel artikelen (proef)")
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()
    config = load_config()
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    map_ = Path(args.map)
    if args.stap == "oogsten":
        m4fc_urls = {v["article_url"] for v in _m4fc(Path("data/extern/m4fc")).values()}
        artikelen = pilotartikelen(conn, m4fc_urls)
        if args.max:
            artikelen = artikelen[:args.max]
        print(f"oogsten: {len(artikelen)} artikelen", flush=True)
        print(f"klaar: {dict(oogst(map_, artikelen, config.model_versions.image_hash, threads=args.threads))}",
              flush=True)
    else:
        _meet(conn, config, map_)


if __name__ == "__main__":
    main()
