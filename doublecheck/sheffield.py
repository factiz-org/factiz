"""De rest van de Sheffield-set: lesstof voor een volgende artikellezer.

De zeefrun van de artikellezer (BENCHMARK §136) liet zien wat de lezer mist:
nieuws over hetzelfde onderwerp dat de bewering niet doet. De set van de
Universiteit van Sheffield (Leite e.a., CIKM 2024; CC BY 4.0, Zenodo
10514307) noemt per ontkrachting van EUvsDisinfo de artikelen die de
desinformatie verspreidden (10.682) en betrouwbare artikelen over hetzelfde
onderwerp (7.567). #28.5 haalde er 1.019 van op voor de netwerktoets
(`artikelen.jsonl`, P2 van de zeef); deze module haalt de rest, naar een
eigen bestand, zodat P2 niet verandert (PO 2026-10-21: "haal de rest van de
Sheffield-set op, beleefd per host en alleen de tekst").

- **Alleen tekst:** titel, beschrijving en de eerste 2.000 tekens alineatekst,
  nooit ruwe HTML.
- **Beleefd:** per host één verzoek tegelijk met `PAUZE` seconden ertussen, en
  robots.txt: verbiedt die het artikel, dan halen we het nergens op, ook niet
  uit het archief. Lukt de link zelf niet (RT, Sputnik en andere zijn vanuit de
  EU niet te bereiken), dan de Wayback-kopie van rond de datum: alleen
  leesvragen, samen hoogstens één per `WAYBACK_PAUZE` seconden.
- **Hervatbaar** per artikel: wat in `UIT` staat, komt niet nog eens.
- **De claim** van een artikel is die van zijn ontkrachting, als die eenduidig
  aan onze EUvsDisinfo-checks koppelt (datum plus verspreidend domein, zoals
  #28.5); artikelen met een claim gaan eerst. Welke helft een artikel heeft,
  beslist de lesstof, niet het ophalen: niets uit een zaak van de toetshelft
  wordt lesstof.

    python -m doublecheck.sheffield ophalen [--proef N] [--threads 8]
    python -m doublecheck.sheffield tellen
"""

from __future__ import annotations

import collections
import csv
import html as _html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "extern" / "euvsdisinfo-sheffield"
BASIS = MAP / "euvsdisinfo_base.csv"
P2 = MAP / "artikelen.jsonl"
UIT = MAP / "lesstof-artikelen.jsonl"
EIGEN = WORTEL / "data" / "euvsdisinfo_all_texts_rename.csv"
TEKENS = 2000
MIN_TEKST = 200  # minder alineatekst dan dit: ook het archief proberen
PAUZE = 2.0
WAYBACK_PAUZE = 3.0
AGENT = "FactizResearch"
KOP = {"User-Agent": f"Mozilla/5.0 ({AGENT}; #30.11b, leest de tekst van artikelen uit de Sheffield-set, beleefd)"}


def dom(d: str) -> str:
    """Het domein, ook achter de vertaalproxy van Google (`rt-com.translate.goog`)."""
    d = d.strip().lower().removeprefix("www.")
    if d.endswith(".translate.goog"):
        d = d.removesuffix(".translate.goog").replace("--", "\0").replace("-", ".").replace("\0", "-")
    return d.removeprefix("www.")


def ontproxy(url: str) -> str:
    """Een link via de vertaalproxy van Google terug naar de site zelf."""
    s = urlsplit(url)
    if not s.netloc.endswith(".translate.goog"):
        return url
    vraag = "&".join(d for d in s.query.split("&") if d and not d.startswith("_x_tr"))
    return f"{s.scheme}://{dom(s.netloc)}{s.path}" + (f"?{vraag}" if vraag else "")


def _iso(datum: str) -> str:
    d, m, j = datum.split("-")
    return f"{j}-{m}-{d}"


def zaakclaims(rijen: list[dict], eigen: dict[str, list[tuple[str, set[str]]]],
               claim_van: dict[str, str]) -> dict[str, str]:
    """Per ontkrachting (debunk_id) onze claim: de datum en de domeinen van haar
    desinformatie-artikelen wijzen naar precies één eigen EUvsDisinfo-zaak
    (`eigen`: per ISO-datum de zaken met hun domeinen), en die zaak staat in
    onze index (`claim_van`: pad van de zaak naar claim)."""
    zaken: dict[str, dict] = collections.defaultdict(lambda: {"datum": None, "domeinen": set()})
    for r in rijen:
        if r["class"] == "disinformation":
            zaken[r["debunk_id"]]["datum"] = _iso(r["debunk_date"])
            zaken[r["debunk_id"]]["domeinen"].add(dom(r["article_domain"]))
    uit = {}
    for debunk, z in zaken.items():
        kandidaten = [pad for pad, domeinen in eigen.get(z["datum"], []) if domeinen & z["domeinen"]]
        if len(kandidaten) == 1 and kandidaten[0] in claim_van:
            uit[debunk] = claim_van[kandidaten[0]]
    return uit


def taken(rijen: list[dict], zaakclaim: dict[str, str], klaar: set[str]) -> list[dict]:
    """Elk artikel één keer, met al zijn ontkrachtingen; wat al opgehaald is
    niet; artikelen met een claim eerst, verder in de volgorde van de set."""
    per_artikel: dict[str, dict] = {}
    for r in rijen:
        if r["article_id"] in klaar:
            continue
        t = per_artikel.setdefault(r["article_id"], {
            "article_id": r["article_id"], "article_url": ontproxy(r["article_url"]),
            "domein": dom(r["article_domain"]), "klasse": r["class"], "taal": r["article_language"],
            "debunks": [], "datum": _iso(r["debunk_date"]), "claim_id": None})
        if r["debunk_id"] not in t["debunks"]:
            t["debunks"].append(r["debunk_id"])
        t["datum"] = min(t["datum"], _iso(r["debunk_date"]))
        t["claim_id"] = t["claim_id"] or zaakclaim.get(r["debunk_id"])
    return sorted(per_artikel.values(), key=lambda t: t["claim_id"] is None)


def _meta(pagina: str, naam: str) -> str:
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(naam) + r'["\'][^>]*content=["\']([^"\']*)', pagina,
                  re.I) or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']'
                                     + re.escape(naam) + r'["\']', pagina, re.I)
    return _html.unescape(m.group(1)).strip() if m else ""


def lees(pagina: str) -> tuple[str, str, str]:
    """(titel, beschrijving, alineatekst) uit een webpagina; nooit HTML."""
    from doublecheck.screeningmeting import alineatekst

    titel = _meta(pagina, "og:title") or (re.search(r"<title[^>]*>(.*?)</title>", pagina, re.I | re.S) or [None, ""])[1]
    titel = _html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"\s+", " ", titel))).strip()
    beschrijving = _meta(pagina, "og:description") or _meta(pagina, "description")
    return titel[:300], beschrijving[:600], alineatekst(pagina)[:TEKENS]


def regels(pad: Path) -> list[dict]:
    """De regels van een JSONL-bestand. Gesplitst op `\\n` en niet met
    `splitlines()`: die knipt ook op U+2028, U+2029 en U+0085, en die staan
    onvertaald in de tekst van artikelen (`ensure_ascii=False`)."""
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").split("\n") if r.strip()]


def _klaar() -> set[str]:
    return {r["article_id"] for pad in (P2, UIT) for r in regels(pad)}


def _set() -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with open(BASIS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _koppeling(rijen: list[dict]) -> dict[str, str]:  # pragma: no cover - op de productiedatabase
    import sqlite3

    csv.field_size_limit(sys.maxsize)
    eigen = collections.defaultdict(list)
    with open(EIGEN, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            d, m, j = r["Date"].split(".")
            eigen[f"{j}-{m}-{d}"].append(
                (r["Links"].split("euvsdisinfo.eu", 1)[-1], {dom(x) for x in re.split(r"[,;\s]+", r["Outlets"]) if x.strip()}))
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    claim_van = {u.split("euvsdisinfo.eu", 1)[1]: c for c, u in conn.execute(
        "SELECT claim_id, url FROM factcheck WHERE url LIKE '%euvsdisinfo.eu/report/%'")}
    return zaakclaims(rijen, eigen, claim_van)


def ophalen(proef: int = 0, threads: int = 8) -> collections.Counter:  # pragma: no cover - haalt webpagina's op
    import concurrent.futures as cf
    import threading
    import time
    import urllib.robotparser

    import httpx

    from doublecheck.artikelbeelden import _haal

    rijen = _set()
    todo = taken(rijen, _koppeling(rijen), _klaar())
    if proef:
        todo = todo[:proef]
    met_claim = sum(t["claim_id"] is not None for t in todo)
    print(f"te doen: {len(todo):,} artikelen, {met_claim:,} met een claim;"
          f" {collections.Counter(t['klasse'] for t in todo)}", flush=True)
    slot, teller = threading.Lock(), collections.Counter()
    archief, archief_laatst = threading.Lock(), [0.0]

    def uit_archief(web, url: str, datum: str):
        """Eén leesvraag aan de Wayback Machine, samen hoogstens één per
        WAYBACK_PAUZE; bij een 503 tot drie keer, steeds later."""
        for poging in range(3):
            with archief:
                wacht = archief_laatst[0] + WAYBACK_PAUZE - time.monotonic()
                if wacht > 0:
                    time.sleep(wacht)
                antwoord = _haal(web, f"https://web.archive.org/web/{datum.replace('-', '')}id_/{url}")
                archief_laatst[0] = time.monotonic()
            if antwoord is not None and antwoord.status_code != 503:
                return antwoord
            time.sleep(30 * (poging + 1))
        return antwoord

    def host_werk(werk: list[dict]) -> None:
        with httpx.Client(headers=KOP, timeout=20, follow_redirects=True) as web:
            host = urlsplit(werk[0]["article_url"]).hostname or ""
            robots = None
            antwoord = _haal(web, f"https://{host}/robots.txt")
            if antwoord is not None and antwoord.status_code == 200:
                robots = urllib.robotparser.RobotFileParser()
                robots.parse(antwoord.text.splitlines())
            for t in werk:
                titel = beschrijving = tekst = ""
                bron, fout = None, None
                if robots is not None and not robots.can_fetch(AGENT, t["article_url"]):
                    fout = "robots.txt verbiedt"
                else:
                    antwoord = _haal(web, t["article_url"])
                    if antwoord is not None and antwoord.status_code == 200 and "html" in antwoord.headers.get(
                            "content-type", "html"):
                        titel, beschrijving, tekst = lees(antwoord.text[:5_000_000])
                        bron = "live"
                    else:
                        fout = f"http {antwoord.status_code}" if antwoord is not None else "niet bereikbaar"
                    if len(tekst) < MIN_TEKST:
                        kopie = uit_archief(web, t["article_url"], t["datum"])
                        if kopie is not None and kopie.status_code == 200:
                            k_titel, k_beschrijving, k_tekst = lees(kopie.text[:5_000_000])
                            if len(k_tekst) > len(tekst):
                                titel, beschrijving, tekst, bron = k_titel, k_beschrijving, k_tekst, "wayback"
                        elif not (titel or tekst):
                            fout = f"{fout} / wayback {kopie.status_code if kopie is not None else 'niet bereikbaar'}"
                    time.sleep(PAUZE)
                gelukt = bool(titel or tekst)
                regel = {**t, "bron": bron if gelukt else None, "fout": None if gelukt else fout,
                         "titel": titel, "beschrijving": beschrijving, "tekst": tekst}
                with slot:
                    with UIT.open("a", encoding="utf-8") as uit:
                        uit.write(json.dumps(regel, ensure_ascii=False) + "\n")
                    teller[regel["bron"] or "mislukt"] += 1
                    if sum(teller.values()) % 200 == 0:
                        print(f"  {sum(teller.values()):,} van {len(todo):,}: {dict(teller)}", flush=True)

    # Eerst alles met een claim, dan de rest; binnen elke ronde per host één rij.
    for ronde in ([t for t in todo if t["claim_id"]], [t for t in todo if not t["claim_id"]]):
        per_host = collections.defaultdict(list)
        for t in ronde:
            per_host[urlsplit(t["article_url"]).hostname or ""].append(t)
        with cf.ThreadPoolExecutor(threads) as pool:
            list(pool.map(host_werk, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {dict(teller)}", flush=True)
    return teller


def tellen() -> dict:  # pragma: no cover - leest de uitvoer
    alle = regels(UIT)
    uit = {
        "artikelen": len(alle),
        "per_klasse_en_bron": {f"{k} / {b}": n for (k, b), n in sorted(collections.Counter(
            (r["klasse"], r["bron"] or "mislukt") for r in alle).items())},
        "met_claim": sum(r["claim_id"] is not None for r in alle),
        "met_alineatekst": sum(len(r["tekst"]) >= MIN_TEKST for r in alle),
        "fouten": dict(collections.Counter((r["fout"] or "")[:40] for r in alle if r["fout"]).most_common(10)),
    }
    print(json.dumps(uit, ensure_ascii=False, indent=1))
    return uit


def main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="De rest van de Sheffield-set ophalen, alleen de tekst (#30.11b)")
    parser.add_argument("stap", choices=("ophalen", "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="alleen de eerste N artikelen")
    parser.add_argument("--threads", type=int, default=8, help="hosts tegelijk; per host altijd één verzoek")
    args = parser.parse_args()
    if args.stap == "ophalen":
        ophalen(args.proef, args.threads)
    else:
        tellen()


if __name__ == "__main__":
    main()
