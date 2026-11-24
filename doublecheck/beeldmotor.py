"""De voormeting voor de beeldmotor: staat het virale beeld in het artikel van de factchecker? (PLAN #32.14)

De eigen beeldindex (#30.4a) herkent alleen beelden die een factchecker zelf in zijn artikel zet. Dit haalt per
artikel van de 40 beeldclaims van O' (#32.12) alleen tekst uit de HTML: per beeld in het inhoudsblok het adres, de
alt-tekst, het bijschrift en de woorden ervoor en erna. De beelden zelf worden niet geopend en nooit bewaard (DR3,
B35). Claude leest per artikel of het virale beeld erin staat (`docs/steekproeven/32.14-beeldmotor.json`).

    python -m doublecheck.beeldmotor set|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from doublecheck.artikelbeelden import _GEEN_INHOUD, _INHOUD, _grootste_uit_srcset, _te_klein

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "beeldmotor"
LABELS = WORTEL / "docs" / "steekproeven" / "32.14-beeldmotor.json"
DREMPEL = 24  # PLAN #32.14: bij 24 van de 40 (60%) het voorstel de beeldindex te bouwen
_RAND = 250   # zoveel tekens tekst voor en na een beeld
_ONDERSCHRIFT = ("figcaption", "wp-caption-text", "caption")


class Weigering(Exception):
    """Tellen kan niet: een artikel zonder label."""


class _Lezer(HTMLParser):
    """De tekst en de beelden van het inhoudsblok, in volgorde; een blok herkend aan zijn klasse gaat voor, anders
    het eerste `<article>` (zoals `artikelbeelden`)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stukken: dict[str, list] = {"blok": [], "article": []}
        self._in = {"blok": None, "article": None}
        self._articles = 0
        self._onderschrift = 0  # diepte binnen een bijschrift

    def _waar(self) -> list[str]:
        return [k for k, v in self._in.items() if v]

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for waar in self._waar():
            if tag == self._in[waar][0]:
                self._in[waar] = (tag, self._in[waar][1] + 1)
        if not self._in["blok"] and _INHOUD.search(a.get("class", "")):
            self._in["blok"] = (tag, 1)
        if tag == "article" and not self._in["article"] and self._articles == 0:
            self._in["article"] = ("article", 1)
            self._articles += 1
        if self._onderschrift:
            self._onderschrift += 1
        elif tag == "figcaption" or any(w in a.get("class", "") for w in _ONDERSCHRIFT[1:]):
            self._onderschrift = 1
        if tag == "img":
            for waar in self._waar():
                self.stukken[waar].append(("beeld", a))

    def handle_endtag(self, tag):
        if self._onderschrift:
            self._onderschrift -= 1
        for waar in self._waar():
            naam, diepte = self._in[waar]
            if tag == naam:
                self._in[waar] = (naam, diepte - 1) if diepte > 1 else None

    def handle_data(self, data):
        tekst = " ".join(data.split())
        if tekst:
            for waar in self._waar():
                self.stukken[waar].append(("onderschrift" if self._onderschrift else "tekst", tekst))


def beelden_met_tekst(html: str, basis: str) -> list[dict]:
    """Per beeld in het inhoudsblok (geen logo, pictogram of piepklein beeld, elk adres één keer): het adres, de
    alt-tekst, het bijschrift direct erna, en de gewone tekst ervoor en erna. Alleen tekst, nooit het beeld."""
    lezer = _Lezer()
    lezer.feed(html)
    stukken = lezer.stukken["blok"] or lezer.stukken["article"]
    uit, gezien = [], set()
    for i, (soort, inhoud) in enumerate(stukken):
        if soort != "beeld" or _te_klein(inhoud):
            continue
        bron = (_grootste_uit_srcset(inhoud["srcset"]) if inhoud.get("srcset") else None) \
            or inhoud.get("data-src") or inhoud.get("data-lazy-src") or inhoud.get("src")
        if not bron or bron.startswith("data:"):
            continue
        adres = urljoin(basis, bron.strip())
        if urlsplit(adres).path.lower().endswith((".svg", ".gif")) or _GEEN_INHOUD.search(adres) or adres in gezien:
            continue
        gezien.add(adres)
        bijschrift, j = [], i + 1
        while j < len(stukken) and stukken[j][0] == "onderschrift":
            bijschrift.append(stukken[j][1])
            j += 1
        voor = " ".join(t for s, t in stukken[:i] if s == "tekst")[-_RAND:]
        na = " ".join(t for s, t in stukken[j:] if s == "tekst")[:_RAND]
        uit.append({"adres": adres, "alt": inhoud.get("alt", "").strip(), "bijschrift": " ".join(bijschrift),
                    "voor": voor, "na": na})
    return uit


def telling(stukken: list[dict], labels: dict[str, dict]) -> dict:
    """De drie tellingen van PLAN #32.14, per redactie, en de beslisregel. Weigert zolang een artikel geen label
    heeft. `labels[id]`: viraal (ja, nee, onduidelijk), origineel (ja, nee), bereikbaar (ja of nee)."""
    open_ = [s["id"] for s in stukken if s["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} artikelen zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    tel, per = Counter(), defaultdict(Counter)
    for s in stukken:
        lab = labels[s["id"]]
        treffer = lab["viraal"] == "ja" and lab["bereikbaar"] is True
        for d in (tel, per[s["redactie"]]):
            d["n"] += 1
            d["viraal"] += treffer
            d["viraal " + lab["viraal"]] += 1
            d["origineel"] += lab["origineel"] == "ja"
            d["bereikbaar"] += lab["bereikbaar"] is True
    return {"n": tel["n"], "viraal beeld in een bereikbaar artikel": tel["viraal"],
            "viraal ja/nee/onduidelijk": [tel["viraal ja"], tel["viraal nee"], tel["viraal onduidelijk"]],
            "origineel": tel["origineel"], "bereikbaar": tel["bereikbaar"],
            "per redactie": {k: dict(v) for k, v in sorted(per.items())},
            "beslisregel: minstens 24 van 40": tel["viraal"] >= DREMPEL}


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def lees_labels() -> dict[str, dict]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r for r in d.get("artikelen", [])}


def _maak_set() -> list[dict]:  # pragma: no cover - op de database en de antwoorden van #32.12
    import sqlite3

    from doublecheck import versetoets as vt

    set_ = {s["id"]: s for s in _jsonl(vt.UIT / "set.jsonl")}
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    uit = []
    for a in _jsonl(vt.UIT / "antwoorden.jsonl"):
        if not (a["id"].startswith("O:") and a.get("over_beeld")):
            continue
        claim = a["id"][2:]
        publisher, url, datum = conn.execute(
            "SELECT publisher, url, review_date FROM factcheck WHERE claim_id = ? AND language = 'en' "
            "ORDER BY factcheck_id LIMIT 1", (claim,)).fetchone()
        uit.append({"id": claim, "tekst": set_[a["id"]]["tekst"], "redactie": publisher, "url": url, "datum": datum})
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "set.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    print(f"{len(uit)} beeldclaims; {dict(Counter(r['redactie'] for r in uit))}")
    return uit


def _ophalen(pauze: float = 2.0) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf
    import threading
    import time

    import httpx

    from doublecheck.artikelbeelden import _haal
    from doublecheck.beeldindex import _KOP, _robots, mag

    pad = UIT / "artikelen.jsonl"
    klaar = {r["id"] for r in _jsonl(pad)}
    per_host = defaultdict(list)
    for s in _jsonl(UIT / "set.jsonl"):
        if s["id"] not in klaar:
            per_host[urlsplit(s["url"]).hostname].append(s)
    slot = threading.Lock()

    def host_werk(werk):
        with httpx.Client(headers=_KOP, follow_redirects=True, timeout=20) as web:
            robots = _robots(web, urlsplit(werk[0]["url"]).hostname)
            for s in werk:
                status, beelden = "verboden", []
                if mag(robots, s["url"]):
                    pagina = _haal(web, s["url"])
                    status = "fout" if pagina is None else pagina.status_code
                    if pagina is not None and pagina.status_code == 200:
                        beelden = beelden_met_tekst(pagina.text, str(pagina.url))
                with slot, pad.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": s["id"], "url": s["url"], "status": status, "beelden": beelden},
                                        ensure_ascii=False) + "\n")
                    print(f"{s['id']} {s['redactie']}: {status}, {len(beelden)} beelden", flush=True)
                time.sleep(pauze)

    with cf.ThreadPoolExecutor(4) as pool:
        list(pool.map(host_werk, per_host.values()))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De voormeting voor de beeldmotor (PLAN #32.14)")
    parser.add_argument("stap", choices=("set", "ophalen", "lezen", "tellen"))
    args = parser.parse_args()
    if args.stap == "set":
        _maak_set()
        return
    if args.stap == "ophalen":
        _ophalen()
        return
    stukken = _jsonl(UIT / "set.jsonl")
    if args.stap == "lezen":
        artikelen = {r["id"]: r for r in _jsonl(UIT / "artikelen.jsonl")}
        labels = lees_labels()
        for s in stukken:
            if s["id"] in labels:
                continue
            a = artikelen.get(s["id"], {})
            print(f"\n=== {s['id']} [{s['redactie']}, {s['datum']}] status {a.get('status')}\nCLAIM: {s['tekst']}\n"
                  f"URL: {s['url']}")
            for i, b in enumerate(a.get("beelden", []), 1):
                print(f"  ({i}) {b['adres'][-70:]}\n      alt: {b['alt'][:120]!r} | bijschrift: {b['bijschrift'][:160]!r}"
                      f"\n      voor: ...{b['voor'][-160:]!r}\n      na: {b['na'][:120]!r}...")
        return
    print(json.dumps(telling(stukken, lees_labels()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
