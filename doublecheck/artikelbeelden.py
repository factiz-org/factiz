"""De virale tekst uit de screenshots in het factcheckartikel (PLAN.md #25.12).

Een claim in ClaimReview is de samenvatting van de redactie; de virale post
zegt het anders, en vaak in een andere taal. Factcheckartikelen citeren die
post zelden in hun eigen tekst (§82: FACTLY citeert zijn eigen kader, Lupa de
uitspraak die al onze claim is), maar ze tonen hem wel: als screenshot. Die
beelden lezen we met de OCR per schrift (#25.21), en wat erop staat wordt een
extra formulering van dezelfde claim, met herkomst (artikel, beeld, OCR).

Alleen tekst en vingerafdruk, nooit het beeld: de beelden gaan alleen door
het geheugen (DR3). De regels hebben de vorm van de claimvarianten, zodat
embedden en meten hetzelfde gereedschap gebruiken (`variantenbatch`), en de
meting is daarmee even eerlijk: een zoekvraag vindt nooit de formuleringen
van haar eigen claim, alleen die van een andere redactie die dezelfde post
checkte. In de index pas met een release (B22).

    python -m doublecheck.artikelbeelden proef [--max-beelden 4]
    python -m doublecheck.artikelbeelden embedden [--deel 0/2]
    python -m doublecheck.artikelbeelden meten
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

OCR_VERSIE = "ocr-per-schrift-v1"
SOORT = "ocr-artikelbeeld"
MAP = "data/artikelbeelden"

# Wat in de bestandsnaam of het pad op een logo, pictogram, reclame of een
# oproep van de redactie zelf wijst ("Follow Factly's WhatsApp Channel").
_GEEN_INHOUD = re.compile(
    r"logo|icon|avatar|gravatar|sprite|emoji|placeholder|share|banner|/ads?/|badge|favicon"
    r"|whatsapp|follow|subscribe|newsletter",
    re.IGNORECASE)
_MIN_ZIJDE = 200

# Het blok met de artikeltekst. Daarbuiten staan de miniaturen van andere
# artikelen ("gerelateerd") en reclame; die horen niet bij deze claim.
_INHOUD = re.compile(
    r"\b(entry-content|post-content|post-body|article-body|article__body|article-content|story-body"
    r"|single-content|td-post-content|content-body|post-entry|news-content|article-text)\b",
    re.IGNORECASE)


class _Beelden(HTMLParser):
    """Het deelbeeld, en de beelden binnen het inhoudsblok. Een blok herkend
    aan zijn klasse gaat voor; anders het eerste `<article>`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og: list[str] = []
        self.in_blok: list[dict] = []
        self.in_article: list[dict] = []
        self._blok = None        # (tag, diepte) van het inhoudsblok waar we in zitten
        self._article = None
        self._articles_gezien = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta" and (a.get("property") or a.get("name")) in ("og:image", "twitter:image"):
            self.og.append(a.get("content", ""))
            return
        if tag == "img":
            if self._blok:
                self.in_blok.append(a)
            elif self._article:
                self.in_article.append(a)
            return
        if self._blok and tag == self._blok[0]:
            self._blok = (tag, self._blok[1] + 1)
        elif not self._blok and _INHOUD.search(a.get("class", "")):
            self._blok = (tag, 1)
        if tag == "article":
            if self._article:
                self._article = ("article", self._article[1] + 1)
            elif self._articles_gezien == 0:
                self._article = ("article", 1)
            self._articles_gezien += 1

    def handle_endtag(self, tag):
        if self._blok and tag == self._blok[0]:
            self._blok = (tag, self._blok[1] - 1) if self._blok[1] > 1 else None
        if self._article and tag == "article":
            self._article = ("article", self._article[1] - 1) if self._article[1] > 1 else None


def _grootste_uit_srcset(srcset: str) -> str | None:
    beste, beste_maat = None, -1.0
    for deel in srcset.split(","):
        stukken = deel.strip().split()
        if not stukken:
            continue
        maat = 0.0
        if len(stukken) > 1 and stukken[1][:-1].replace(".", "", 1).isdigit():
            maat = float(stukken[1][:-1])
        if maat > beste_maat:
            beste, beste_maat = stukken[0], maat
    return beste


def _te_klein(a: dict) -> bool:
    for sleutel in ("width", "height"):
        waarde = a.get(sleutel, "").strip().removesuffix("px")
        if waarde.isdigit() and int(waarde) < _MIN_ZIJDE:
            return True
    return False


def beelden_uit_artikel(html: str, basis: str) -> list[str]:
    """De beelden van een artikel die een screenshot kunnen zijn: het
    deelbeeld eerst, dan de beelden in het inhoudsblok; geen logo's,
    pictogrammen, plaatshouders, oproepen of piepkleine beelden, en elk adres
    één keer. Zonder herkenbaar inhoudsblok alleen het deelbeeld: liever
    minder dan de beelden van andere artikelen."""
    lezer = _Beelden()
    lezer.feed(html)
    kandidaten = list(lezer.og)
    for a in (lezer.in_blok or lezer.in_article):
        if _te_klein(a):
            continue
        bron = (_grootste_uit_srcset(a["srcset"]) if a.get("srcset") else None) \
            or a.get("data-src") or a.get("data-lazy-src") or a.get("src")
        if bron:
            kandidaten.append(bron)
    gezien, uit = set(), []
    for bron in kandidaten:
        bron = bron.strip()
        if not bron or bron.startswith("data:"):
            continue
        adres = urljoin(basis, bron)
        pad = urlsplit(adres).path.lower()
        if pad.endswith((".svg", ".gif")) or _GEEN_INHOUD.search(adres) or adres in gezien:
            continue
        gezien.add(adres)
        uit.append(adres)
    return uit


def schoon_ocr(tekst: str) -> str:
    """De gelezen tekst zonder stempels en oordeelregels ("FALSE", "FACT
    CHECK"): die zijn van de factchecker, niet van de virale post."""
    from doublecheck.ruwetest import OORDEELWOORDEN

    stempels = {w.casefold() for w in OORDEELWOORDEN}
    regels = []
    for regel in tekst.splitlines():
        kaal = re.sub(r"\s+", " ", regel).strip()
        sleutel = kaal.casefold().strip(" .!:-–—|")
        if len(sleutel) < 3 or sleutel in stempels:
            continue
        regels.append(kaal)
    return " ".join(regels).strip()


def regel(claim_id: str, url: str, teksten: list[tuple[str, str, str]]) -> dict:
    """Eén artikel: per beeld (adres, tekst, taal) een formulering, in de vorm
    van de claimvarianten."""
    return {"claim_id": claim_id, "url": url, "ocr": OCR_VERSIE, "geweigerd": False,
            "varianten": [{"soort": SOORT, "taal": taal, "tekst": tekst, "beeld": beeld}
                          for beeld, tekst, taal in teksten]}


def _haal(web, url: str):
    """Het antwoord, of `None` bij elk adres dat niet op te halen is: een
    netwerkfout, maar ook een ongeldige hostnaam in andermans artikel."""
    import httpx

    try:
        return web.get(url)
    except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError):
        return None


def al_gelezen(map_) -> set[str]:
    from doublecheck.variantenbatch import lees_regels

    return {r["url"] for r in lees_regels(Path(map_))}


# --- opdrachtregel -------------------------------------------------------------

def _proef(map_: Path, conn, feed: str, max_beelden: int) -> None:
    import collections
    import concurrent.futures as cf
    import dataclasses
    import json
    import threading
    import time

    import httpx
    import py3langid

    from doublecheck.api import MAX_IMAGE_BYTES
    from doublecheck.config import load_config
    from doublecheck.evidence import _host
    from doublecheck.natuurlijk import groepen_uit_feed
    from doublecheck.ocr import extract_text

    instellingen = dataclasses.replace(load_config().ocr, per_schrift=True)
    claims = set().union(*groepen_uit_feed(conn, feed))
    klaar = al_gelezen(map_)
    artikelen = [(cid, url) for cid, url in conn.execute("SELECT claim_id, url FROM factcheck ORDER BY url")
                 if cid in claims and url not in klaar]
    per_host = collections.defaultdict(list)
    for cid, url in artikelen:
        per_host[_host(url)].append((cid, url))
    print(f"proef: {len(claims)} claims, {len(artikelen)} artikelen te lezen over {len(per_host)} hosts", flush=True)
    map_.mkdir(parents=True, exist_ok=True)
    schrijf, ocr_een = threading.Lock(), threading.Lock()   # één OCR tegelijk: de CPU blijft voor het embedden
    teller = collections.Counter()

    def host_werk(werk):
        kop = {"User-Agent": "Mozilla/5.0 (FactizResearch; #25.12, leest de screenshots in factcheckartikelen)"}
        with httpx.Client(headers=kop, follow_redirects=True, timeout=20) as web:
            for cid, url in werk:
                teksten = []
                pagina = _haal(web, url)
                beelden = beelden_uit_artikel(pagina.text, str(pagina.url))[:max_beelden] \
                    if pagina is not None and pagina.status_code == 200 else []
                for beeld in beelden:
                    time.sleep(2)
                    antwoord = _haal(web, beeld)
                    if antwoord is None or antwoord.status_code != 200 or len(antwoord.content) > MAX_IMAGE_BYTES:
                        continue
                    try:
                        with ocr_een:
                            gelezen = extract_text(antwoord.content, instellingen)
                    except Exception:   # geen beeld, of kapot: overslaan, nooit loggen (DR3)
                        continue
                    tekst = schoon_ocr(gelezen.text) if gelezen.readable else ""
                    if len(tekst) >= 20:
                        teksten.append((beeld, tekst, py3langid.classify(tekst)[0]))
                with schrijf:
                    with (map_ / "regels.jsonl").open("a", encoding="utf-8") as uit:
                        uit.write(json.dumps(regel(cid, url, teksten), ensure_ascii=False) + "\n")
                    teller["artikelen"] += 1
                    teller["met tekst"] += bool(teksten)
                    teller["teksten"] += len(teksten)
                    if teller["artikelen"] % 100 == 0:
                        print(f"  {dict(teller)}", flush=True)
                time.sleep(2)

    with cf.ThreadPoolExecutor(6) as pool:
        list(pool.map(host_werk, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {dict(teller)}", flush=True)


def main() -> None:
    import argparse
    import os
    import sqlite3

    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="De virale tekst uit de screenshots in het artikel (#25.12)")
    parser.add_argument("stap", choices=("proef", "embedden", "meten"))
    parser.add_argument("--map", default=MAP)
    parser.add_argument("--max-beelden", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--deel", default="0/1")
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    args = parser.parse_args()
    map_ = Path(args.map)
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    if args.stap == "proef":
        _proef(map_, conn, args.feed, args.max_beelden)
    elif args.stap == "embedden":
        import torch
        from threadpoolctl import threadpool_limits

        from doublecheck.embedding import fingerprint_texts
        from doublecheck.variantenbatch import embed

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        i, n = (int(x) for x in args.deel.split("/"))
        print(f"nieuw embed: {embed(map_, load_config().model_versions.text_embedding, fingerprint_texts, deel=(i, n))}")
    else:
        from doublecheck.variantenbatch import _meet

        _meet(map_, conn, load_config(), args.feed)


if __name__ == "__main__":
    main()
