"""Eigen aanvoer, de proef van route A (PLAN #32.19, RESEARCH §8.5).

De open feed van Google bevat alleen checks die met Google's eigen invoerhulp gemaakt zijn, en dat worden er steeds
minder (RESEARCH §8.4). AFP, Snopes, Full Fact, EFE en anderen zetten hun ClaimReview nog in hun eigen artikelen. Deze
proef haalt die beleefd op, voor één maand, en telt wat er nieuw is.

Vastgelegd vóór het ophalen, in PLAN #32.19:
- **beleefd**: robots.txt voor FactizResearch, per site één verzoek tegelijk en minstens 2 seconden ertussen (of de
  wachttijd die de site vraagt), de naam en factiz.org in elk verzoek;
- **het venster**: checks met een datum van 2 oktober tot en met 1 november 2026, via de sitemap uit robots.txt;
- **bewaard**: per check het adres, de site, de taal, de bewering, het oordeel en de datum, en of het adres al in de
  database staat; nooit de pagina of een beeld, en niets in de database (B22);
- **de doelen**: 300 nieuwe checks in het Engels, Spaans en Portugees, 95% van de oordelen herkend, hoogstens 1 fout
  bij 30 gelezen, en geen site die ons weert.

    python -m doublecheck.eigenaanvoer verken     (per site robots.txt en de sitemaps, een paar verzoeken)
    python -m doublecheck.eigenaanvoer proef      (de artikelen in het venster; hervatbaar)
    python -m doublecheck.eigenaanvoer lezen|tellen
"""

from __future__ import annotations

import collections
import html
import json
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "aanvoer" / "proef"
LABELS = WORTEL / "docs" / "steekproeven" / "32.19-eigenaanvoer.json"
VAN, TOT = "2026-10-02", "2026-11-01"
STEEKPROEF_N, ZAAD = 30, 3219
KERNTALEN = ("en", "es", "pt")
NAAM = "FactizResearch"
KOP = {"User-Agent": f"Mozilla/5.0 (compatible; {NAAM}/0.1; fact-check index trial, stores only links, claims and "
                     "verdicts; +https://factiz.org)"}
MIN_PAUZE = 2.0
GRENS_VERZOEK = 60.0   # seconden voor een heel verzoek: een server die druppelt, loopt anders nooit af (#32.66)
MAX_PAGINA = 30_000_000
MAX_ARTIKELEN = 600          # per site; daarboven afgekapt en gemeld
MAX_KINDEREN = 35            # deelsitemaps per index, de nieuwste (een maand aan sitemaps per dag)
GEWEERD = (403, 429)

# De sites van PLAN #32.19. `pad` beperkt de sitemap tot artikelen; zonder pad telt alles van de host.
SITES = [
    {"naam": "AFP Fact Check", "host": "factcheck.afp.com", "taal": "en", "pad": r"/doc\.afp\.com\."},
    {"naam": "AFP Factual", "host": "factual.afp.com", "taal": "es", "pad": r"/doc\.afp\.com\."},
    {"naam": "AFP Faktencheck", "host": "faktencheck.afp.com", "taal": "de", "pad": r"/doc\.afp\.com\."},
    {"naam": "AFP Checamos", "host": "checamos.afp.com", "taal": "pt", "pad": r"/doc\.afp\.com\."},
    # B68 (2026-11-09): de factcheckers van de talen van V1 die nog ontbraken
    {"naam": "AFP Factuel", "host": "factuel.afp.com", "taal": "fr", "pad": r"/doc\.afp\.com\."},
    {"naam": "Correctiv", "host": "correctiv.org", "taal": "de", "pad": r"/faktencheck/"},
    {"naam": "dpa-Faktencheck", "host": "dpa-factchecking.com", "taal": "de", "pad": r"/germany/"},
    {"naam": "Polígrafo", "host": "poligrafo.iol.pt", "taal": "pt", "pad": r"/fact-check/"},
    {"naam": "Observador", "host": "observador.pt", "taal": "pt", "pad": r"/factchecks/"},
    {"naam": "Knack", "host": "www.knack.be", "taal": "nl", "pad": r"/factcheck/"},
    # B68: AFP Factuel weigert (403); Franse factcheckers in de plaats
    {"naam": "Les Décodeurs", "host": "www.lemonde.fr", "taal": "fr", "pad": r"/les-decodeurs/article/"},
    {"naam": "CheckNews", "host": "www.liberation.fr", "taal": "fr", "pad": r"/checknews/"},
    # franceinfo is verhuisd van francetvinfo.fr naar franceinfo.fr
    {"naam": "franceinfo Vrai ou faux", "host": "www.franceinfo.fr", "taal": "fr", "pad": r"/vrai-ou-fake/"},
    {"naam": "Les Surligneurs", "host": "www.lessurligneurs.eu", "taal": "fr", "pad": None},
    {"naam": "Snopes", "host": "www.snopes.com", "taal": "en", "pad": r"/fact-check/[^/]+/?$"},
    {"naam": "Full Fact", "host": "fullfact.org", "taal": "en", "pad": r"^/(?!about|blog|latest|search|newsletter)"
                                                                     r"[a-z-]+/[^/]+/?$"},
    {"naam": "Lead Stories", "host": "leadstories.com", "taal": "en", "pad": r"/\d{4}/\d{2}/"},
    {"naam": "AAP FactCheck", "host": "www.aap.com.au", "taal": "en", "pad": r"/factcheck/"},
    {"naam": "EFE Verifica", "host": "verifica.efe.com", "taal": "es", "pad": None},
    {"naam": "Annie Lab", "host": "annielab.org", "taal": None, "pad": None},
    {"naam": "Maldita", "host": "maldita.es", "taal": "es", "pad": r"/(desinfo|malditobulo)/\d{8}/"},
    {"naam": "Newtral", "host": "www.newtral.es", "taal": "es", "pad": r"/\d{8}/?$"},
    {"naam": "Factchequeado", "host": "factchequeado.com", "taal": "es", "pad": None},
    {"naam": "Aos Fatos", "host": "www.aosfatos.org", "taal": "pt", "pad": r"/noticias/"},
    {"naam": "Estadão Verifica", "host": "www.estadao.com.br", "taal": "pt", "pad": r"/estadao-verifica/"},
]


class Weigering(Exception):
    """Tellen kan niet: een check uit de steekproef zonder label."""


# --- uit een artikel: alleen de ClaimReview ---------------------------------------------------

_LDJSON = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def _alle(x):
    if isinstance(x, dict):
        soort = x.get("@type")
        if "ClaimReview" in (soort if isinstance(soort, list) else [soort]):
            yield x
            return
        for v in x.values():
            if isinstance(v, (dict, list)):
                yield from _alle(v)
    elif isinstance(x, list):
        for v in x:
            yield from _alle(v)


def claimreviews(html: str) -> list[dict]:
    """De ClaimReview-objecten in de JSON-LD van een pagina: los, in een lijst of in een `@graph`. Een blok dat geen
    geldige JSON is, telt niet."""
    uit = []
    for blok in _LDJSON.findall(html or ""):
        try:
            uit.extend(_alle(json.loads(blok.strip())))
        except (json.JSONDecodeError, ValueError):
            continue
    return uit


def adres(url: str) -> str:
    """Een adres zonder schema, www, zoekdeel en slotstreep: zo vergelijken we met de database."""
    deel = urlsplit(url or "")
    return (deel.hostname or "").lower().removeprefix("www.") + re.sub(r"/{2,}", "/", unquote(deel.path)).rstrip("/")


def check_uit(review: dict, pagina: str, site: dict) -> dict:
    """Wat we van één check bewaren: het adres (dat van de review als het op dezelfde site staat, anders de pagina),
    de site, de taal, de bewering, het oordeel met zijn categorie, de datum en de uitgever. Nooit de pagina."""
    from doublecheck import feed
    from doublecheck.taal import corpus_taal
    from doublecheck.verdicts import normalize_verdict

    eigen = review.get("url") if isinstance(review.get("url"), str) else None
    host = site["host"].removeprefix("www.")
    adres_ = eigen if eigen and adres(eigen).startswith(host) else pagina
    bewering = " ".join(html.unescape(str(review.get("claimReviewed") or "")).split())
    oordeel = feed._oordeel(review)
    return {"adres": adres_, "site": site["naam"], "taal": site.get("taal") or corpus_taal(bewering) or "und",
            "bewering": bewering, "oordeel": oordeel, "categorie": normalize_verdict(oordeel, host),
            "datum": (str(review.get("datePublished") or "")[:10]) or None, "uitgever": feed._uitgever(review)[0]}


# --- de sitemap ------------------------------------------------------------------------------

def _kaal(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _datum(tekst: str | None) -> str | None:
    tekst = (tekst or "").strip()
    return tekst[:10] if re.match(r"\d{4}-\d{2}-\d{2}", tekst) else None


_ADRESDATUM = re.compile(r"/(20\d{2})[-/]?(\d{2})(?:[-/]?(\d{2}))?(?=[/?.]|$)")


def datum_uit_adres(url: str) -> str | None:
    """De datum die in een adres staat (/2026/10/, /20261030/, /2026-10-15/). Bij alleen een maand de 28e: dan valt
    oktober in het venster en september niet. Alleen om vooraf te kiezen; wat telt is de datum van de check."""
    for jaar, maand, dag in _ADRESDATUM.findall(urlsplit(url or "").path):
        if 1 <= int(maand) <= 12 and (not dag or 1 <= int(dag) <= 31):
            return f"{jaar}-{maand}-{dag or '28'}"
    return None


def sitemap(xml: str) -> tuple[list[tuple[str, str | None]], list[tuple[str, str | None]]]:
    """(artikelen, deelsitemaps) uit een sitemap, elk met zijn datum (lastmod, of de publicatiedatum van een
    nieuwssitemap); een sitemap als tekst is een adres per regel; onleesbaar is leeg."""
    try:
        wortel = ET.fromstring(xml)
    except ET.ParseError:
        regels = [r.strip() for r in (xml or "").splitlines()]
        return [(r, None) for r in regels if r.startswith(("http://", "https://"))], []
    urls, kinderen = [], []
    for el in wortel:
        soort = _kaal(el.tag)
        if soort not in ("url", "sitemap"):
            continue
        loc, datum = None, None
        for kind in el.iter():
            naam = _kaal(kind.tag)
            if naam == "loc" and loc is None:
                loc = (kind.text or "").strip()
            elif naam in ("lastmod", "publication_date") and datum is None:
                datum = _datum(kind.text)
        if loc:
            (urls if soort == "url" else kinderen).append((loc, datum))
    return urls, kinderen


def kinderen_kiezen(kinderen: list[tuple[str, str | None]], van: str = VAN, n: int = MAX_KINDEREN) -> list[str]:
    """De deelsitemaps die het venster kunnen raken: met een datum vanaf het venster, de nieuwste eerst; zonder datum
    die met 2026 in de naam, anders de laatste n."""
    # de datum in het adres eerst: een sitemap per dag valt binnen het venster; een lastmod alleen vanaf het begin
    kinderen = [(loc, datum_uit_adres(loc), datum) for loc, datum in kinderen]
    gedateerd = sorted([(loc, a or d) for loc, a, d in kinderen if (a and van <= a <= TOT) or (not a and d and d >= van)],
                       key=lambda k: k[1], reverse=True)
    kinderen = [(loc, a or d) for loc, a, d in kinderen]
    if gedateerd or any(k[1] for k in kinderen):
        return [k[0] for k in gedateerd[:n]]
    met_jaar = [k[0] for k in kinderen if "2026" in k[0]]
    return (met_jaar or [k[0] for k in kinderen])[-n:]


def in_venster(datum: str | None) -> bool:
    return bool(datum) and VAN <= datum[:10] <= TOT


# --- tellen ---------------------------------------------------------------------------------

def steekproef(checks: list[dict]) -> list[str]:
    """30 nieuwe checks om te lezen, elke keer dezelfde (zaad 3219)."""
    nieuw = sorted({c["adres"] for c in checks if c["nieuw"]})
    return sorted(random.Random(ZAAD).sample(nieuw, min(STEEKPROEF_N, len(nieuw))))


def telling(checks: list[dict], sites: dict[str, dict], gelezen: dict[str, str],
            steekproef: list[str] | None = None) -> dict:
    """Per taal en per site de checks, de nieuwe en de herkende oordelen; de vier doelen van PLAN #32.19. Weigert
    zolang een check uit de steekproef geen label heeft."""
    if steekproef is not None:
        open_ = [a for a in steekproef if a not in gelezen]
        if open_:
            raise Weigering(f"{len(open_)} checks uit de steekproef zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    per_taal, per_site = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for c in checks:
        for d in (per_taal[c["taal"]], per_site[c["site"]]):
            d["checks"] += 1
            d["nieuw"] += bool(c["nieuw"])
            d["oordeel herkend"] += c["categorie"] != "onbekend"
    labels = [gelezen[a] for a in (steekproef if steekproef is not None else gelezen) if a in gelezen]
    fouten = sum(v == "klopt niet" for v in labels)
    geweerd = sorted(n for n, s in sites.items() if any(x in GEWEERD for x in s.get("status", [])))
    nieuw_kern = sum(per_taal[t]["nieuw"] for t in KERNTALEN)
    herkend = sum(c["categorie"] != "onbekend" for c in checks) / len(checks) if checks else 0.0
    doelen = {"1. minstens 300 nieuwe checks in en, es en pt": nieuw_kern >= 300,
              "2. minstens 95% van de oordelen herkend": herkend >= 0.95,
              "3. bij de 30 gelezen hoogstens 1 fout": len(labels) >= STEEKPROEF_N and fouten <= 1,
              "4. geen site die ons weert": not geweerd}
    return {"per taal": {t: dict(v) for t, v in sorted(per_taal.items())},
            "per site": {s: dict(v) for s, v in sorted(per_site.items())},
            "nieuw in en, es en pt": nieuw_kern, "oordelen herkend": round(herkend, 4), "gelezen": len(labels),
            "fouten": fouten, "geweerd": geweerd, "doelen": doelen, "gehaald": all(doelen.values())}


# --- ophalen, beleefd -------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    return [json.loads(r) for r in inhoud[:inhoud.rfind("\n") + 1].splitlines() if r.strip()]


_SLOT = threading.Lock()


def _schrijf(pad: Path, regels: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with _SLOT, pad.open("a", encoding="utf-8") as f:
        for r in regels:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _lees_binnen(stukjes, klok=time.monotonic, grens: float = GRENS_VERZOEK,
                 max_bytes: int = MAX_PAGINA) -> bytes | None:
    """De hele pagina, of None als ze te lang onderweg is of te groot: de leestijd per stukje alleen houdt een server
    die elke paar seconden een beetje stuurt niet tegen (Le Monde, #32.66)."""
    begin, uit = klok(), bytearray()
    for stuk in stukjes:
        uit += stuk
        if len(uit) > max_bytes or klok() - begin > grens:
            return None
    return bytes(uit)


class _Site:  # pragma: no cover - netwerk
    """Eén site: robots.txt voor FactizResearch, één verzoek tegelijk, de pauze die de site vraagt (minstens 2 s)."""

    def __init__(self, site: dict):
        import httpx

        self.site, self.web = site, httpx.Client(headers=KOP, follow_redirects=True, timeout=30)
        self.status: list = []
        self.laatst, self.pauze, self.robots, self.sitemaps = 0.0, MIN_PAUZE, None, []

    def haal(self, url: str):
        import httpx

        wacht = self.laatst + self.pauze - time.monotonic()
        if wacht > 0:
            time.sleep(wacht)
        try:
            with self.web.stream("GET", url) as r:
                inhoud = _lees_binnen(r.iter_bytes())
                kop = {k: v for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length")}
                a = None if inhoud is None else httpx.Response(r.status_code, headers=kop, content=inhoud,
                                                                request=r.request)
        except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError):
            a = None
        self.laatst = time.monotonic()
        self.status.append(a.status_code if a is not None else "fout")
        return a

    def lees_robots(self) -> None:
        import urllib.robotparser

        a = self.haal(f"https://{self.site['host']}/robots.txt")
        tekst = a.text if a is not None and a.status_code == 200 else ""
        self.robots = urllib.robotparser.RobotFileParser()
        self.robots.parse(tekst.splitlines())
        vertraging = self.robots.crawl_delay(NAAM)
        if vertraging:
            self.pauze = max(MIN_PAUZE, float(vertraging))
        self.sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", tekst) or [f"https://{self.site['host']}/sitemap.xml"]

    def mag(self, url: str) -> bool:
        return self.robots is None or self.robots.can_fetch(NAAM, url)

    def xml(self, url: str) -> str:
        import gzip

        if not self.mag(url):
            return ""
        a = self.haal(url)
        if a is None or a.status_code != 200:
            return ""
        inhoud = a.content[:30_000_000]
        if inhoud[:2] == b"\x1f\x8b":
            try:
                inhoud = gzip.decompress(inhoud)
            except OSError:
                return ""
        return inhoud.decode("utf-8", errors="replace")


def _kandidaten(s: _Site) -> tuple[list[tuple[str, str | None]], dict]:  # pragma: no cover - netwerk
    """De artikeladressen in het venster uit de sitemaps, tot twee lagen diep."""
    pad = re.compile(s.site["pad"]) if s.site.get("pad") else None
    gezien, uit, info = set(), {}, {"sitemaps": [], "afgekapt": False}
    rij = [(u, 0) for u in s.sitemaps]
    while rij:
        url, diepte = rij.pop(0)
        if url in gezien or len(gezien) > 45:
            continue
        gezien.add(url)
        urls, kinderen = sitemap(s.xml(url))
        info["sitemaps"].append({"adres": url, "artikelen": len(urls), "deelsitemaps": len(kinderen)})
        if kinderen and diepte < 2:
            rij += [(k, diepte + 1) for k in kinderen_kiezen(kinderen)]
        for loc, datum in urls:
            if urlsplit(loc).hostname != s.site["host"] and urlsplit(loc).hostname != s.site["host"].removeprefix("www."):
                continue
            if pad and not pad.search(urlsplit(loc).path):
                continue
            datum = datum_uit_adres(loc) or datum
            if datum is not None and datum < VAN:
                continue
            uit.setdefault(loc, datum)
    lijst = sorted(uit.items(), key=lambda x: x[1] or "", reverse=True)
    if len(lijst) > MAX_ARTIKELEN:
        info["afgekapt"] = len(lijst)
        lijst = lijst[:MAX_ARTIKELEN]
    return lijst, info


def _verken() -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    def doe(site):
        s = _Site(site)
        s.lees_robots()
        lijst, info = _kandidaten(s)
        return {"site": site["naam"], "robots: sitemaps": s.sitemaps, "pauze": s.pauze,
                "artikelen in het venster (sitemap)": len(lijst), **info, "status": s.status}

    with cf.ThreadPoolExecutor(8) as pool:
        uit = list(pool.map(doe, SITES))
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / "verken.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in uit:
        print(f"{r['site']}: {r['artikelen in het venster (sitemap)']} artikelen, {len(r['sitemaps'])} sitemaps gelezen, "
              f"pauze {r['pauze']} s, status {collections.Counter(r['status'])}", flush=True)


def _bekend() -> set[str]:  # pragma: no cover - op de database
    import sqlite3

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    return {adres(u) for (u,) in conn.execute("SELECT url FROM factcheck WHERE url IS NOT NULL AND url != ''")}


def _proef() -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    bekend = _bekend()
    gedaan = {r["pagina"] for r in _jsonl(MAP / "artikelen.jsonl")}

    def doe(site):
        s = _Site(site)
        s.lees_robots()
        lijst, info = _kandidaten(s)
        tel = collections.Counter()
        for url, _ in lijst:
            if url in gedaan:
                continue
            if not s.mag(url):
                _schrijf(MAP / "artikelen.jsonl", [{"site": site["naam"], "pagina": url, "status": "robots"}])
                continue
            a = s.haal(url)
            status = a.status_code if a is not None else "fout"
            reviews = claimreviews(a.text) if a is not None and a.status_code == 200 else []
            del a   # de pagina blijft in het geheugen en gaat nu weg
            checks = []
            for r in reviews:
                c = check_uit(r, url, site)
                if in_venster(c["datum"]) and c["bewering"]:
                    checks.append({**c, "nieuw": adres(c["adres"]) not in bekend and adres(url) not in bekend})
            _schrijf(MAP / "artikelen.jsonl", [{"site": site["naam"], "pagina": url, "status": status,
                                                "claimreviews": len(reviews), "in het venster": len(checks)}])
            _schrijf(MAP / "checks.jsonl", checks)
            tel["artikelen"] += 1
            tel["met ClaimReview"] += bool(reviews)
            tel["checks in het venster"] += len(checks)
        samen = {"site": site["naam"], **info, "pauze": s.pauze, "status": dict(collections.Counter(s.status)),
                 "statuslijst": sorted({x for x in s.status if isinstance(x, int)}), **tel}
        _schrijf(MAP / "sites.jsonl", [samen])
        print(f"{site['naam']}: {dict(tel)}, status {samen['status']}", flush=True)

    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(doe, SITES))


def lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    return json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {})


def _uniek(checks: list[dict]) -> list[dict]:
    """Een check één keer, ook als een pagina twee keer gelezen is (een hervatte run)."""
    return list({(c["adres"], c["bewering"]): c for c in checks}.values())


def _sites() -> dict[str, dict]:
    uit = {}
    for r in _jsonl(MAP / "sites.jsonl"):
        d = uit.setdefault(r["site"], {"status": []})
        d["status"] += r.get("statuslijst", [])
    return uit


def _lezen() -> None:  # pragma: no cover - schrijft een leespagina
    import html

    checks = {c["adres"]: c for c in _uniek(_jsonl(MAP / "checks.jsonl"))}
    rijen = [f"<tr><td>#{i}</td><td>{html.escape(c['site'])} · {c['datum']}<br><b>{html.escape(c['bewering'])}</b>"
             f"<br>oordeel: {html.escape(str(c['oordeel']))} → {c['categorie']}<br>"
             f"<a href='{html.escape(a)}'>{html.escape(a)}</a></td></tr>"
             for i, a in enumerate(steekproef(list(checks.values()))) for c in [checks[a]]]
    (MAP / "lezen.html").write_text("<!doctype html><meta charset=utf-8><title>Eigen aanvoer lezen</title>"
                                    "<style>body{font:13px sans-serif}td{padding:6px;border-bottom:1px solid #ccc;"
                                    "vertical-align:top}</style><table>" + "".join(rijen) + "</table>", encoding="utf-8")
    print(f"{len(rijen)} checks te lezen: {MAP / 'lezen.html'}")


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    checks = _uniek(_jsonl(MAP / "checks.jsonl"))
    uit = telling(checks, _sites(), lees_labels(), steekproef(checks))
    artikelen = _jsonl(MAP / "artikelen.jsonl")
    uit["artikelen"] = {"opgehaald": len(artikelen),
                        "status": dict(collections.Counter(str(a["status"]) for a in artikelen)),
                        "met ClaimReview": sum(1 for a in artikelen if a.get("claimreviews"))}
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Eigen aanvoer, de proef van route A (PLAN #32.19)")
    parser.add_argument("stap", choices=("verken", "proef", "lezen", "tellen"))
    args = parser.parse_args()
    if args.stap == "verken":
        _verken()
    elif args.stap == "proef":
        _proef()
    elif args.stap == "lezen":
        _lezen()
    else:
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
