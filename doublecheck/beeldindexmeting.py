"""De beeldindex meten op echte screenshots (PLAN #32.15, stap 1 en 2).

Vastgelegd vóór het ophalen, in PLAN #32.15:

- **de index van de voormeting**: de artikelen van §88, die van R1 en die van R2, zonder de hosts die we niet kunnen
  of willen ophalen (`UITGESLOTEN`); per artikel het deelbeeld en hooguit 4 beelden uit het inhoudsblok, met alleen
  hun kenmerken (`beeldvraag.indexkenmerken`); huisstijl en verzamelartikelen eruit, zoals in §88;
- **R1**: de beweringen die twee of meer redacties checkten; een beeld van redactie A tegen de index zonder de
  artikelen van A over die bewering, geteld per bewering;
- **R2**: 100 verse beeldclaims (zaad 3215); Google Vision zoekt met de beelden uit het artikel naar kopieën op het
  open web, niet van een factchecksite, hooguit 5 per claim; die kopieën tegen de hele index;
- **S**: nieuwsfoto's (S1) en portretten (S2) van Wikimedia Commons, de rest van M4FC (S3) en memes (S4), elk als
  origineel en in kader B; ze mogen niets vinden;
- **routes**: PDQ alleen, DINOv2 alleen (heel beeld en beeldgebied) en de combinatie (`beeldvraag.beslis`), met de
  drempels 31 en 0,954;
- **lezen**: elke treffer buiten de eigen bewering wordt gelezen en gelabeld in `LABELS`; memes zijn vals op de
  constructie (hetzelfde sjabloon met een ander onderschrift, §93).

Beelden staan alleen in het werkgeheugen (DR3, B35); bewaard worden de kenmerken en de adressen.

    python -m doublecheck.beeldindexmeting set
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldindexmeting oogsten [--max 50]
    python -m doublecheck.beeldindexmeting vision
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldindexmeting vragen --set R2|S1|S2|S3|S4
    python -m doublecheck.beeldindexmeting zoeken|lezen|tellen
"""

from __future__ import annotations

import collections
import json
import random
import re
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from doublecheck import beeldvraag as bv

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "beeldindex" / "pdq-256-v1+dinov2-small-ed25f3a3"
PANEELMAP = MAP / "panelen"        # stap 2b: de artikelen van R2 opnieuw, met panelen
OUD = WORTEL / "data" / "beeldindex" / "regels.jsonl"      # de oogst van §88
LABELS = WORTEL / "docs" / "steekproeven" / "32.15-beeldindex.json"
KOP = {"User-Agent": "Mozilla/5.0 (FactizResearch; image index measurement, stores no image; https://factiz.org)"}

# Hun beelden komen met JavaScript (§88), de site weigert (Logically), of het zijn illustraties bij verhalen van
# staatsmedia (EUvsDisinfo, een voorstel aan de PO).
UITGESLOTEN = frozenset({
    "youturn.in", "en.youturn.in", "share.youturn.in", "boatos.org", "thip.media",
    "logicallyfacts.com", "logically.ai", "logically.in", "euvsdisinfo.eu"})
BEELDWOORDEN = re.compile(r"photo|video|image|picture|footage|clip|show", re.IGNORECASE)
R2_VANAF, R2_N, R2_ZAAD = "2026-04-01", 100, 3215
MAX_KOPIEEN = 5
MAX_BEELDEN = 5          # het deelbeeld en hooguit 4 uit het inhoudsblok
MIN_ZIJDE = 200
DREMPEL_PDQ, DREMPEL_DINO = 31, 0.954     # config `image_same`; §92, niet opnieuw geijkt in stap 2
VARIANTEN = ("pdq", "dino", "combinatie")
VORMEN = ("origineel", "kader_b")
SETS_S = ("S1", "S2", "S3", "S4")
GEVONDEN, ANDERE, VALS = "zelfde beeld, zelfde bewering", "zelfde beeld, andere bewering", "ander beeld"
LABELWAARDEN = (GEVONDEN, ANDERE, VALS)

# S1 en S2, vastgelegd in PLAN #32.15
S1_N, S1_ZAAD = 300, 3216
S2_PERSONEN = ("Narendra Modi", "Donald Trump", "Joe Biden", "Rahul Gandhi", "Amit Shah", "Rodrigo Duterte",
               "Yogi Adityanath", "Kamala Harris", "Vladimir Putin", "Barack Obama")
S2_PER_PERSOON = 20
S4_SJABLONEN, S4_PER_SJABLOON, S4_EERDER = 50, 9, 1000   # onderschriften 0-500 in §93, 500-1000 in §94


class Weigering(Exception):
    pass


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


# --- de set ----------------------------------------------------------------------

def r1_groepen(rijen: list[tuple]) -> dict[str, list[str]]:
    """De beweringen (cluster, anders claim) met twee of meer redacties die we kunnen ophalen, met die redacties.
    `rijen`: (claim, cluster, url, ...)."""
    hosts = collections.defaultdict(set)
    for claim, cluster, url, *_ in rijen:
        if host(url) not in UITGESLOTEN:
            hosts[cluster or claim].add(host(url))
    return {g: sorted(h) for g, h in sorted(hosts.items()) if len(h) >= 2}


def r2_kandidaten(rijen: list[tuple]) -> list[dict]:
    """De verse beeldclaims: Engels, sinds 1 april 2026, een beeldwoord in de claim, een host die we kunnen ophalen;
    op volgorde van claim. `rijen`: (claim, cluster, url, uitgever, taal, datum, tekst)."""
    kandidaten = {}
    for claim, cluster, url, uitgever, taal, datum, tekst in sorted(rijen):
        if taal == "en" and (datum or "") >= R2_VANAF and BEELDWOORDEN.search(tekst or "") \
                and host(url) not in UITGESLOTEN and claim not in kandidaten:
            kandidaten[claim] = {"claim_id": claim, "groep": cluster or claim, "url": url, "uitgever": uitgever,
                                 "datum": datum, "tekst": tekst}
    return list(kandidaten.values())


def r2_claims(rijen: list[tuple]) -> list[dict]:
    """100 van de kandidaten, getrokken met zaad 3215."""
    lijst = r2_kandidaten(rijen)
    return sorted(random.Random(R2_ZAAD).sample(lijst, min(R2_N, len(lijst))), key=lambda c: c["claim_id"])


def artikelen(rijen: list[tuple], oud: set[str], r1: dict, r2: list[dict]) -> list[tuple[str, str]]:
    """De artikelen van de voormeting, elk adres één keer (de claims erbij komen bij het meten uit de database)."""
    r2_urls = {c["url"] for c in r2}
    uit = {}
    for claim, cluster, url, *_ in sorted(rijen):
        if host(url) in UITGESLOTEN or url in uit:
            continue
        if url in oud or (cluster or claim) in r1 or url in r2_urls:
            uit[url] = claim
    return [(c, u) for u, c in uit.items()]


# --- de index van de meting ---------------------------------------------------------

def index_uit_regels(regels: list[dict], claims_van: dict[str, list[str]], groep: dict[str, str]):
    """De beeldindex van de meting: per artikel de laatste regel, alleen de beelden van 200 pixels of meer met genoeg
    PDQ-kwaliteit (§88), zonder verzamelartikelen en huisstijl. Geeft de index en een telling van wat eruit ging."""
    import numpy as np

    from doublecheck.beeldindex import Beeld, laatste, sjablonen

    tel = collections.Counter()
    beelden, kenmerken = [], []
    for r in laatste(regels):
        if r["status"] != 200:
            continue
        claims = claims_van.get(r["url"]) or [r["claim_id"]]
        groepen = {groep.get(c, c) for c in claims}
        if len(groepen) >= 2:
            tel["verzamelartikel"] += len(r["beelden"])
            continue
        for b in r["beelden"]:
            if min(b["breedte"], b["hoogte"]) < MIN_ZIJDE:
                tel["te klein"] += 1
            elif b["kwaliteit"] < bv.MIN_KWALITEIT:
                tel["vlak"] += 1
            else:
                beelden.append({"claim_id": claims[0], "groep": next(iter(groepen)), "artikel": r["url"],
                                "host": host(r["url"]), "beeld": b["beeld"]})
                kenmerken.append(b)
    proef = [Beeld(b["claim_id"], b["artikel"], b["beeld"], bytes.fromhex(k["pdq"][0]), k["kwaliteit"])
             for b, k in zip(beelden, kenmerken)]
    weg = sjablonen(proef, groep, DREMPEL_PDQ)
    tel["huisstijl"] = len(weg)
    houden = [i for i in range(len(beelden)) if i not in weg]
    index = bv.Beeldindex.bouw([beelden[i] for i in houden], [kenmerken[i] for i in houden])
    tel["in de index"] = len(index)
    return index, {"groep": np.array([b["groep"] for b in index.beelden], dtype=object),
                   "host": np.array([b["host"] for b in index.beelden], dtype=object),
                   "kenmerken": [kenmerken[i] for i in houden]}, tel


def _kandidaat(index, j_waarde) -> list | None:
    if j_waarde is None:
        return None
    j, waarde = j_waarde
    b = index.beelden[j]
    return [b["beeld"], b["groep"], b["artikel"], round(waarde, 4) if isinstance(waarde, float) else waarde]


def treffer(index, vraag: dict, meta: dict, uitsluiten=None) -> dict:
    """De beste kandidaat per route, als regel: genoeg om de varianten te tellen bij elke drempel zonder de index."""
    r = bv.routes(index, vraag, uitsluiten)
    return {**meta, **{k: _kandidaat(index, r[k]) for k in ("pdq", "dino", "dino_gebied")}}


def keuze(t: dict, variant: str, *, drempel_pdq: int = DREMPEL_PDQ, drempel_dino: float = DREMPEL_DINO) -> list | None:
    """De treffer van een variant: PDQ alleen, DINOv2 alleen (heel beeld en gebied), of de combinatie van §92."""
    pdq = t["pdq"] if variant in ("pdq", "combinatie") else None
    dino = t["dino_gebied"] if variant in ("dino", "combinatie") else None
    gekozen = bv.beslis(pdq and (0, pdq[3]), dino and (1, dino[3]), drempel_pdq=drempel_pdq, drempel_dino=drempel_dino)
    return None if gekozen is None else (pdq, dino)[gekozen]


# --- de kopieën van R2 ------------------------------------------------------------------

def verboden(url: str, factchecksites: set[str], eigen: str) -> bool:
    """Een kopie van een factchecker telt niet: een site uit onze database of het IFCN, ergens in het adres (ook een
    beeldserver als i0.wp.com/factly.in), het eigen artikel, of een woord als "fact-check"."""
    laag = unquote(url).lower()
    h = host(url)
    if h == eigen or eigen in laag:
        return True
    if any(w in laag for w in ("fact-check", "factcheck", "fact_check", "hoax")):
        return True
    return any(h == d or h.endswith("." + d) or f"/{d}/" in laag for d in factchecksites)


def kopieen(antwoorden: list[dict], factchecksites: set[str], eigen: str) -> list[dict]:
    """De kandidaat-kopieën uit de antwoorden van Web Detection, in volgorde: eerst de volledige, dan de
    gedeeltelijke, per soort in de volgorde van de antwoorden; elk beeldadres één keer, de pagina erbij als die
    bekend is. Een kopie op een pagina van een factchecker telt niet."""
    uit, gezien = {"vol": [], "deels": []}, set()
    for antwoord in antwoorden:
        web = ((antwoord.get("responses") or [{}])[0]).get("webDetection") or {}
        paren = []
        for p in web.get("pagesWithMatchingImages") or []:
            for soort, sleutel in (("vol", "fullMatchingImages"), ("deels", "partialMatchingImages")):
                paren += [(soort, b.get("url"), p.get("url")) for b in p.get(sleutel) or []]
        paren += [("vol", b.get("url"), None) for b in web.get("fullMatchingImages") or []]
        paren += [("deels", b.get("url"), None) for b in web.get("partialMatchingImages") or []]
        for soort, beeld, pagina in paren:
            if not beeld or not beeld.startswith("http") or beeld in gezien:
                continue
            if verboden(beeld, factchecksites, eigen) or (pagina and verboden(pagina, factchecksites, eigen)):
                continue
            gezien.add(beeld)
            uit[soort].append({"beeld": beeld, "pagina": pagina, "soort": soort})
    return uit["vol"] + uit["deels"]


# --- S1, S2 en S4: de lijsten --------------------------------------------------------------

_NAAMRUIMTEN = re.compile(r"^(file|image|category|portal|wikipedia|template|help|special|talk|user|wp|w|wikt|"
                          r"commons|draft|module|mos):", re.IGNORECASE)


def portal_artikelen(wikitekst: str) -> list[str]:
    """De artikelen waar een dag van Portal:Current events naar linkt, in volgorde, elk één keer."""
    uit = []
    for doel in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", wikitekst):
        doel = doel.strip().replace("_", " ")
        if doel and not _NAAMRUIMTEN.match(doel) and doel not in uit:
            uit.append(doel)
    return uit


def foto_van_commons(info: dict) -> bool:
    """Een foto, geen kaart of logo: JPEG en minstens 800 pixels breed."""
    return info.get("mime") == "image/jpeg" and info.get("width", 0) >= 800 and bool(info.get("thumburl"))


_GEEN_PORTRET = re.compile(r"signature|caricature|cartoon|logo|map|painting|statue|wax|mural|video|coat of arms|"
                           r"flag|poster|graffiti|stamp|coin|banknote|meme|drawing|art\b", re.IGNORECASE)


def imgflip_sjablonen(html: str) -> list[dict]:
    """De sjablonen op een pagina van imgflip.com/memetemplates, in volgorde: naam en het adres van het volle beeld
    (de pagina toont een verkleining onder /4/)."""
    uit = []
    for naam, bron in re.findall(r'<img class="shadow"[^>]*alt="([^"]*) Meme Template"[^>]*src="([^"]+)"', html):
        bron = ("https:" + bron if bron.startswith("//") else bron).replace("i.imgflip.com/4/", "i.imgflip.com/")
        uit.append({"naam": naam, "url": bron})
    return uit


def sleutel_imgflip(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1].split(".")[0]


# --- tellen -------------------------------------------------------------------------------

def labelsleutel(t: dict, kandidaat: list) -> str:
    return f"{t['set']}|{t['vraag']}|{t['vorm']}|{kandidaat[0]}"


def oordeel(t: dict, kandidaat: list | None, labels: dict[str, str]) -> str | None:
    """Wat een treffer is: `None` zonder treffer; bij R1 en R2 in de eigen bewering meteen gevonden; een meme is vals
    op de constructie; anders het label (en `"open"` zonder label)."""
    if kandidaat is None:
        return None
    if t["set"] in ("R1", "R2") and kandidaat[1] == t["groep"]:
        return GEVONDEN
    if t["set"] == "S4":
        return VALS
    return labels.get(labelsleutel(t, kandidaat), "open")


def te_lezen(treffers: list[dict], labels: dict[str, str], **drempels) -> list[tuple[dict, list]]:
    """Elke treffer van een variant die een label nodig heeft en er nog geen heeft, elk paar één keer."""
    uit, gezien = [], set()
    for t in treffers:
        for variant in VARIANTEN:
            k = keuze(t, variant, **drempels)
            if oordeel(t, k, labels) == "open" and labelsleutel(t, k) not in gezien:
                gezien.add(labelsleutel(t, k))
                uit.append((t, k))
    return uit


def telling(treffers: list[dict], labels: dict[str, str], aantallen: dict[str, int], **drempels) -> dict:
    """Per set en variant: R1 per bewering, R2 per claim (ook apart via volledige en gedeeltelijke kopieën), S per vraag
    en vorm met de valse treffers en hun bovengrens. Weigert zolang een treffer die telt geen label heeft."""
    from doublecheck.cijfers import _bovengrens

    open_ = te_lezen(treffers, labels, **drempels)
    if open_:
        raise Weigering(f"{len(open_)} treffers zonder label in {LABELS.name}, bijvoorbeeld "
                        f"{labelsleutel(*open_[0])}")
    uit: dict = {}
    for v in VARIANTEN:
        gevonden = collections.defaultdict(set)     # set -> groepen of claims
        per_soort = collections.defaultdict(set)
        s = collections.defaultdict(collections.Counter)
        for t in treffers:
            k = keuze(t, v, **drempels)
            o = oordeel(t, k, labels)
            if t["set"] in ("R1", "R2"):
                # R1 vraagt of een andere redactie het beeld heeft; de eigen redactie in een ander cluster telt niet
                if o == GEVONDEN and (t["set"] == "R2" or host(k[2]) != t.get("host")):
                    gevonden[t["set"]].add(t["groep"])
                    if t["set"] == "R2":
                        per_soort[t["soort"]].add(t["groep"])
                s[t["set"]][o or "niets"] += 1
            else:
                s[t["set"]]["vragen"] += 1
                s[t["set"]][o or "niets"] += 1
        d = {"R1": {"n": aantallen.get("R1", 0), "gevonden": len(gevonden["R1"]), "treffers": dict(s["R1"])},
             "R2": {"n": aantallen.get("R2", 0), "gevonden": len(gevonden["R2"]),
                    "via volledige kopie": len(per_soort["vol"]), "via gedeeltelijke kopie": len(per_soort["deels"]),
                    "treffers": dict(s["R2"])}}
        for naam in SETS_S:
            c = s[naam]
            d[naam] = {"vragen": c["vragen"], "vals": c[VALS], "zelfde beeld": c[GEVONDEN] + c[ANDERE],
                       "bovengrens": _bovengrens(c[VALS], c["vragen"])}
        n = sum(d[x]["vragen"] for x in ("S1", "S2", "S3"))
        k = sum(d[x]["vals"] for x in ("S1", "S2", "S3"))
        d["S1-S3"] = {"vragen": n, "vals": k, "per 1.000": 1000 * k / n if n else None, "bovengrens": _bovengrens(k, n)}
        uit[v] = d
    return uit


# --- de puntenproef (stap 2d) -------------------------------------------------------------------------
#
# Lokale punten (SIFT) met een geometrische controle: twee beelden zijn hetzelfde als genoeg punten met één
# gelijkvormigheid op elkaar passen. Ongevoelig voor kader, stempel, uitsnede en collage. Alleen in het werkgeheugen.

PUNTEN_MIN, DEKKING_MIN = 20, 0.10     # vooraf vastgelegd in PLAN #32.15 stap 2d
# de punten zelf staan sinds #32.17 in de kern; deze meting leent ze
puntkenmerken, puntvergelijking = bv.puntkenmerken, bv.puntvergelijking
RATIO, RANSAC_PX, MAX_PUNTEN = bv.RATIO, bv.RANSAC_PX, bv.MAX_PUNTEN


def punttreffer(punten: int, dekking: float) -> bool:
    """Hetzelfde beeld: genoeg punten, en niet alleen een gedeeld logo of een knoppenbalk van een app."""
    return punten >= PUNTEN_MIN and dekking >= DEKKING_MIN


def punt_telling(regels: list[dict], labels: dict[str, str], n: int = R2_N) -> dict:
    """Stap 2d: per claim gevonden als een kopie haar beste treffer in de eigen bewering heeft (of zo gelabeld is);
    een treffer elders telt pas na een label. `beste` is [beeld, groep, artikel, punten, dekking] of `None`."""
    gevonden, per_soort, vals, open_ = set(), collections.defaultdict(set), 0, []
    for r in regels:
        k = r["beste"]
        if k is None:
            continue
        oordeel_ = GEVONDEN if k[1] == r["groep"] else labels.get(labelsleutel(r, k), "open")
        if oordeel_ == "open":
            open_.append(labelsleutel(r, k))
        elif oordeel_ == GEVONDEN:
            gevonden.add(r["claim_id"])
            per_soort[r["soort"]].add(r["claim_id"])
        elif oordeel_ == VALS:
            vals += 1
    if open_:
        raise Weigering(f"{len(open_)} treffers zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    return {"n": n, "gevonden": len(gevonden), "via volledige kopie": len(per_soort["vol"]),
            "via gedeeltelijke kopie": len(per_soort["deels"]), "vals": vals, "gehaald": len(gevonden) >= 50}


def met_panelen(oud: list[dict], nieuw: list[dict]) -> list[dict]:
    """De oogst van stap 2 met daarachter die van stap 2b; een artikel dat in 2b niet binnenkwam, houdt zijn regel uit
    stap 2 (`laatste` neemt de laatste regel per adres)."""
    return oud + [r for r in nieuw if r["status"] == 200]


def beslisregel_panelen(uitslag: dict) -> dict:
    """De eis van stap 2b: met panelen bij minstens 50 van de 100 verse claims de check gevonden."""
    regel = {"R2 minstens 50 van 100": uitslag["combinatie"]["R2"]["gevonden"] >= 50}
    return {**regel, "gehaald": all(regel.values())}


def beslisregel(uitslag: dict) -> dict:
    """De drie regels van #32.15, op de combinatie; S4 beslist niet, maar boven 5% gaat de tekstregel mee."""
    c, p = uitslag["combinatie"], uitslag["pdq"]
    s = c["S1-S3"]
    regels = {"1. R2 minstens 50 van 100": c["R2"]["gevonden"] >= 50,
              "2. R1 de combinatie minstens 3x PDQ alleen": c["R1"]["gevonden"] >= 3 * p["R1"]["gevonden"],
              "3. S1-S3 hoogstens 1 vals per 1.000": bool(s["vragen"]) and s["vals"] * 1000 <= s["vragen"]}
    memes = c["S4"]
    return {**regels, "gehaald": all(regels.values()),
            "S4 boven 5% (tekstregel mee in stap 5)": bool(memes["vragen"]) and memes["vals"] > 0.05 * memes["vragen"]}


# --- ophalen, beleefd ------------------------------------------------------------------------

def is_beeld(inhoud: bytes) -> bool:
    return inhoud.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8")) or (inhoud[:4] == b"RIFF"
                                                                        and inhoud[8:12] == b"WEBP")


class Beleefd:  # pragma: no cover - netwerk
    """Eén verzoek tegelijk per host, `pauze` seconden ertussen, robots.txt; bij 429 of 503 wachten zolang de server
    vraagt (hooguit tien minuten) en één keer opnieuw. Geeft de bytes, nooit naar schijf."""

    def __init__(self, pauze: float = 2.0):
        import httpx

        self.web = httpx.Client(headers=KOP, follow_redirects=True, timeout=30)
        self.pauze = pauze
        self._sloten = collections.defaultdict(threading.Lock)
        self._algemeen = threading.Lock()
        self._laatst: dict[str, float] = {}
        self._robots: dict[str, object] = {}

    def _slot(self, naam: str) -> threading.Lock:
        with self._algemeen:
            return self._sloten[naam]

    def _vraag(self, url: str, data: dict | None = None):
        import httpx

        from doublecheck.artikelbeelden import _haal

        def haal():
            if data is None:
                return _haal(self.web, url)
            try:
                return self.web.post(url, data=data)
            except httpx.HTTPError:
                return None

        h = host(url)
        with self._slot(h):
            wacht = self._laatst.get(h, 0) + self.pauze - time.monotonic()
            if wacht > 0:
                time.sleep(wacht)
            antwoord = haal()
            if antwoord is not None and antwoord.status_code in (429, 503):
                try:
                    na = min(600.0, float(antwoord.headers.get("retry-after", 60)))
                except ValueError:
                    na = 60.0
                time.sleep(na)
                antwoord = haal()
            self._laatst[h] = time.monotonic()
            return antwoord

    def mag(self, url: str) -> bool:
        import urllib.robotparser

        h = host(url)
        if h not in self._robots:
            antwoord = self._vraag(f"https://{urlsplit(url).hostname}/robots.txt")
            lezer = None
            if antwoord is not None and antwoord.status_code == 200:
                lezer = urllib.robotparser.RobotFileParser()
                lezer.parse(antwoord.text.splitlines())
            self._robots[h] = lezer
        lezer = self._robots[h]
        return lezer is None or lezer.can_fetch("FactizResearch", url)

    def beeld(self, url: str) -> bytes | None:
        from doublecheck.api import MAX_IMAGE_BYTES

        if not self.mag(url):
            return None
        antwoord = self._vraag(url)
        if antwoord is None or antwoord.status_code != 200 or len(antwoord.content) > MAX_IMAGE_BYTES \
                or not is_beeld(antwoord.content):
            return None
        return antwoord.content

    def json(self, url: str, params: dict) -> dict:
        """Een vraag aan de API van MediaWiki, als POST: vijftig titels passen niet in een adres (414)."""
        antwoord = self._vraag(url, data={k: str(v) for k, v in params.items()})
        if antwoord is None or antwoord.status_code != 200:
            raise RuntimeError(f"{host(url)} gaf {getattr(antwoord, 'status_code', 'geen antwoord')}")
        return antwoord.json()


# --- de bestanden ------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    return [json.loads(r) for r in inhoud[:inhoud.rfind("\n") + 1].splitlines() if r.strip()]


def _schrijf(pad: Path, regels: list[dict], slot: threading.Lock) -> None:
    with slot:
        with pad.open("a", encoding="utf-8") as f:
            for r in regels:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    labels = json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {})
    fout = {k: v for k, v in labels.items() if v not in LABELWAARDEN}
    if fout:
        raise Weigering(f"onbekende labels in {LABELS.name}: {list(fout.items())[:3]}")
    return labels


def _db():  # pragma: no cover - op de database
    import sqlite3

    return sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)


def _rijen(conn) -> list[tuple]:  # pragma: no cover - op de database
    return conn.execute(
        "SELECT c.claim_id, c.cluster_id, f.url, f.publisher, f.language, f.review_date, c.canonical_text "
        "FROM claim c JOIN factcheck f ON f.claim_id = c.claim_id WHERE f.url IS NOT NULL AND f.url != ''").fetchall()


def _set() -> dict:  # pragma: no cover - op de database
    rijen = _rijen(_db())
    oud = {json.loads(r)["url"] for r in OUD.read_text(encoding="utf-8").splitlines() if r.strip()}
    r1 = r1_groepen(rijen)
    r2 = r2_claims(rijen)
    tekst_van = collections.defaultdict(list)
    for claim, cluster, _, _, _, _, tekst in rijen:
        tekst_van[cluster or claim].append(tekst or "")
    lijst = artikelen(rijen, oud, r1, r2)
    kandidaten = len(r2_kandidaten(rijen))
    uit = {"artikelen": lijst, "r1": r1, "r2": r2, "uitgesloten": sorted(UITGESLOTEN),
           "aantallen": {"artikelen": len(lijst), "hosts": len({host(u) for _, u in lijst}), "R1": len(r1),
                         "R1 met een beeldwoord": sum(any(BEELDWOORDEN.search(t) for t in tekst_van[g]) for g in r1),
                         "R2 kandidaten": kandidaten, "R2": len(r2),
                         "R2 per uitgever": dict(collections.Counter(c["uitgever"] for c in r2).most_common())}}
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / "set.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit["aantallen"]


def _lees_set() -> dict:
    pad = MAP / "set.json"
    if not pad.exists():
        raise Weigering("eerst: python -m doublecheck.beeldindexmeting set")
    return json.loads(pad.read_text(encoding="utf-8"))


def _rekenen():  # pragma: no cover - laadt het model
    import torch

    torch.set_num_threads(2)   # hoogstens twee kernen (PO)
    from doublecheck.beeldembedding import alle_vectoren

    return alle_vectoren


def _oogsten(max_artikelen: int | None, threads: int, panelen: bool = False) -> None:  # pragma: no cover - netwerk
    from doublecheck.beeldindex import oogst
    from doublecheck.beelduitsnede import PANELEN

    vectoren = _rekenen()
    lijst = [tuple(a) for a in _lees_set()["artikelen"]]
    if panelen:     # stap 2b: alleen de artikelen van R2
        r2 = {c["url"] for c in _lees_set()["r2"]}
        lijst = [a for a in lijst if a[1] in r2]
    if max_artikelen:   # de proef: één artikel per host, zoveel hosts als gevraagd
        per_host = {}
        for c, u in lijst:
            per_host.setdefault(host(u), (c, u))
        lijst = list(per_host.values())[:max_artikelen]
    begin = time.monotonic()
    teller = oogst(PANEELMAP if panelen else MAP, lijst,
                   "pdq-256-v1+" + bv.BEELDMODEL + ("+" + PANELEN if panelen else ""), threads=threads,
                   max_beelden=MAX_BEELDEN,
                   verwerk=lambda inhoud: bv.indexkenmerken(inhoud, vectoren=vectoren, panelen=panelen))
    print(f"klaar: {dict(teller)} in {time.monotonic() - begin:.0f} s", flush=True)


def _factchecksites() -> set[str]:  # pragma: no cover - op de database en de lijst van het IFCN
    import csv

    from doublecheck.bronnenlijst import EXTERN
    from doublecheck.bronnenlijst import host as bl_host
    from doublecheck.verificatie import factcheck_domeinen

    ifcn = {bl_host(r["site"]) for r in csv.DictReader((EXTERN / "ifcn" / "actief.tsv").open(encoding="utf-8"),
                                                       delimiter="\t") if r.get("site")}
    return {d for d in factcheck_domeinen() | ifcn if d}


def _vision() -> None:  # pragma: no cover - met Google Cloud Vision
    import base64
    import os

    import httpx

    from doublecheck.beeldindex import _lees, laatste
    from doublecheck.beeldzoeken import MAX_RESULTATEN, VISION
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = os.environ.get("GOOGLE_VISION_API_KEY")
    if not sleutel:
        raise SystemExit("GOOGLE_VISION_API_KEY ontbreekt in .env")
    regels = {r["url"]: r for r in laatste(_lees(MAP))}
    pad = MAP / "r2-vision.jsonl"
    klaar = {r["claim_id"] for r in _jsonl(pad)}
    web, slot, n = Beleefd(), threading.Lock(), 0
    for c in _lees_set()["r2"]:
        if c["claim_id"] in klaar:
            continue
        r = regels.get(c["url"])
        adressen = [b["beeld"] for b in (r or {}).get("beelden", [])
                    if min(b["breedte"], b["hoogte"]) >= MIN_ZIJDE][:MAX_BEELDEN]
        antwoorden = []
        for adres in adressen:
            inhoud = web.beeld(adres)
            if inhoud is None:
                continue
            verzoek = {"requests": [{"image": {"content": base64.b64encode(inhoud).decode()},
                                     "features": [{"type": "WEB_DETECTION", "maxResults": MAX_RESULTATEN}]}]}
            del inhoud
            for poging in range(4):
                antwoord = httpx.post(VISION, params={"key": sleutel}, json=verzoek, timeout=60)
                if antwoord.status_code == 200:
                    antwoorden.append({"beeld": adres, **antwoord.json()})
                    n += 1
                    break
                if antwoord.status_code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Vision {antwoord.status_code}")
                time.sleep(5 * 2 ** poging)
        _schrijf(pad, [{"claim_id": c["claim_id"], "url": c["url"], "status": (r or {}).get("status"),
                        "antwoorden": antwoorden}], slot)
        print(f"{c['claim_id']}: {len(adressen)} beelden, {len(antwoorden)} zoekvragen", flush=True)
    print(f"klaar: {n} zoekvragen aan Vision deze run", flush=True)


def _maak_vragen(naam: str, werk: list[dict], maak, threads: int = 8,
                 zonder: frozenset = frozenset()) -> None:  # pragma: no cover - netwerk
    """Per werkstuk de bytes beleefd ophalen (het eerste adres dat lukt), `maak(beeld)` geeft per vorm de kenmerken;
    één regel per vraag en vorm in `vragen/<naam>.jsonl`. Hervatbaar per werkstuk. Werk op een host uit `zonder`
    blijft liggen voor een volgende run (een host die een ander proces op dat moment al vraagt)."""
    import concurrent.futures as cf
    import io

    from PIL import Image

    pad = MAP / "vragen" / f"{naam}.jsonl"
    pad.parent.mkdir(parents=True, exist_ok=True)
    klaar = {r["werk"] for r in _jsonl(pad)} | {r["werk"] for r in _jsonl(pad.with_suffix(".mislukt.jsonl"))}
    web, slot, rekenen = Beleefd(), threading.Lock(), threading.Lock()
    tel = collections.Counter()
    per_host = collections.defaultdict(list)
    for w in werk:
        if w["werk"] not in klaar and host(w["adressen"][0]) not in zonder:
            per_host[host(w["adressen"][0])].append(w)

    def doe(lijst):
        for w in lijst:
            inhoud = next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)
            regels = []
            if inhoud is not None:
                try:
                    with rekenen:
                        begin = time.monotonic()
                        beeld = Image.open(io.BytesIO(inhoud)).convert("RGB")
                        for vorm, kenmerken in maak(beeld, w):
                            regels.append({**{k: v for k, v in w.items() if k != "adressen"}, "vorm": vorm,
                                           "seconden": round(time.monotonic() - begin, 3), **kenmerken})
                except Exception:   # kapot of geen beeld: overslaan, nooit loggen (DR3)
                    regels = []
                del inhoud
            if regels:
                _schrijf(pad, regels, slot)
            else:
                _schrijf(pad.with_suffix(".mislukt.jsonl"), [{"werk": w["werk"]}], slot)
            with slot:
                tel["gelukt" if regels else "mislukt"] += 1
                if sum(tel.values()) % 50 == 0:
                    print(f"  {naam}: {dict(tel)}", flush=True)

    with cf.ThreadPoolExecutor(threads) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"{naam}: {dict(tel)}", flush=True)


def _vormen(vectoren):  # pragma: no cover - met het model
    from doublecheck.kadermeting import _kader_b

    def maak(beeld, _w):
        beeld.thumbnail((bv.MAX_ZIJDE, bv.MAX_ZIJDE))
        yield "origineel", bv.vraagkenmerken(beeld, vectoren=vectoren)
        yield "kader_b", bv.vraagkenmerken(_kader_b(beeld), vectoren=vectoren)
    return maak


def _werk_r2() -> list[dict]:  # pragma: no cover - op de antwoorden van Vision
    """Per claim de kandidaat-kopieën; de eerste vijf die lukken tellen (`_maak_vragen` met `adressen` van één)."""
    sites = _factchecksites()
    werk = []
    for r in _jsonl(MAP / "r2-vision.jsonl"):
        c = next(x for x in _lees_set()["r2"] if x["claim_id"] == r["claim_id"])
        for i, k in enumerate(kopieen(r["antwoorden"], sites, host(c["url"]))):
            werk.append({"werk": f"{c['claim_id']}#{i}", "set": "R2", "vraag": k["beeld"], "groep": c["groep"],
                         "claim_id": c["claim_id"], "soort": k["soort"], "pagina": k["pagina"], "rang": i,
                         "adressen": [k["beeld"]]})
    return werk


def _api(web: Beleefd, basis: str, params: dict) -> dict:  # pragma: no cover - netwerk
    return web.json(basis, {**params, "format": "json", "formatversion": 2, "maxlag": 5})


def _werk_s1(web: Beleefd) -> list[dict]:  # pragma: no cover - netwerk
    from datetime import date, timedelta

    wiki = "https://en.wikipedia.org/w/api.php"
    tussen = MAP / "vragen" / "S1-titels.json"     # alleen titels, zodat een herstart niet opnieuw begint
    stand = json.loads(tussen.read_text(encoding="utf-8")) if tussen.exists() else {}
    titels = stand.get("artikelen")
    if titels is None:
        titels = []
        dag = date(2026, 9, 1)
        while dag <= date(2026, 10, 28):
            d = _api(web, wiki, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                 "titles": f"Portal:Current events/{dag.year} {dag:%B} {dag.day}"})
            pagina = d["query"]["pages"][0]
            if "revisions" in pagina:
                titels += [t for t in portal_artikelen(pagina["revisions"][0]["slots"]["main"]["content"])
                           if t not in titels]
            dag += timedelta(days=1)
        tussen.parent.mkdir(parents=True, exist_ok=True)
        tussen.write_text(json.dumps({"artikelen": titels}, ensure_ascii=False), encoding="utf-8")
    bestanden = set(stand.get("bestanden") or [])
    if not bestanden:
        for i in range(0, len(titels), 50):
            vervolg: dict = {}
            while True:
                d = _api(web, wiki, {"action": "query", "prop": "images", "imlimit": "max",
                                     "titles": "|".join(titels[i:i + 50]), **vervolg})
                for p in d.get("query", {}).get("pages", []):
                    bestanden |= {x["title"] for x in p.get("images", [])
                                  if x["title"].lower().endswith((".jpg", ".jpeg"))}
                if "continue" not in d:
                    break
                vervolg = {k: v for k, v in d["continue"].items()}
        tussen.write_text(json.dumps({"artikelen": titels, "bestanden": sorted(bestanden)}, ensure_ascii=False),
                          encoding="utf-8")
    fotos = []
    lijst = sorted(bestanden)
    for i in range(0, len(lijst), 50):
        d = _api(web, "https://commons.wikimedia.org/w/api.php",
                 {"action": "query", "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 1024,
                  "titles": "|".join(lijst[i:i + 50])})
        fotos += [(p["title"], p["imageinfo"][0]) for p in d["query"].get("pages", [])
                  if p.get("imageinfo") and foto_van_commons(p["imageinfo"][0])]
    print(f"S1: {len(titels)} artikelen, {len(bestanden)} JPEG-bestanden, {len(fotos)} foto's", flush=True)
    gekozen = random.Random(S1_ZAAD).sample(sorted(fotos), min(S1_N, len(fotos)))
    return [{"werk": t, "set": "S1", "vraag": info["thumburl"], "nr": nr, "titel": t, "adressen": [info["thumburl"]]}
            for nr, (t, info) in enumerate(gekozen)]


def _werk_s2(web: Beleefd) -> list[dict]:  # pragma: no cover - netwerk
    commons = "https://commons.wikimedia.org/w/api.php"
    werk, nr = [], 0
    for persoon in S2_PERSONEN:
        gekozen, rij, bekeken = [], [f"Category:{persoon}"], set()
        while rij and len(gekozen) < S2_PER_PERSOON and len(bekeken) < 40:
            categorie = rij.pop(0)
            bekeken.add(categorie)
            d = _api(web, commons, {"action": "query", "generator": "categorymembers", "gcmtitle": categorie,
                                    "gcmtype": "file|subcat", "gcmlimit": 200, "prop": "imageinfo",
                                    "iiprop": "url|size|mime", "iiurlwidth": 1024})
            leden = sorted(d.get("query", {}).get("pages", []), key=lambda p: p["title"])
            for p in leden:
                if p["title"].startswith("Category:"):
                    if not _GEEN_PORTRET.search(p["title"]) and p["title"] not in bekeken:
                        rij.append(p["title"])
                elif p.get("imageinfo") and foto_van_commons(p["imageinfo"][0]) \
                        and not _GEEN_PORTRET.search(p["title"]) and p["title"] not in {g[0] for g in gekozen}:
                    gekozen.append((p["title"], p["imageinfo"][0]["thumburl"]))
        for titel, url in gekozen[:S2_PER_PERSOON]:
            werk.append({"werk": titel, "set": "S2", "vraag": url, "nr": nr, "persoon": persoon, "titel": titel,
                         "adressen": [url]})
            nr += 1
        print(f"S2: {persoon}: {min(len(gekozen), S2_PER_PERSOON)}", flush=True)
    return werk


def _werk_s3() -> list[dict]:  # pragma: no cover - op M4FC
    from doublecheck.beeldstilte import M4FC_JSON, M4FC_REST

    items = json.loads(M4FC_JSON.read_text(encoding="utf-8"))
    eerder = _jsonl(M4FC_REST.parent / "rest-status.jsonl")
    indices = sorted({r["index"] for r in eerder if r["bestand"]})
    return [{"werk": str(i), "set": "S3", "vraag": items[i]["image_url"] or items[i]["wayback_image_url"], "nr": nr,
             "adressen": [a for a in (items[i].get("image_url"), items[i].get("wayback_image_url")) if a]}
            for nr, i in enumerate(indices)]


def _werk_s4(web: Beleefd) -> list[dict]:  # pragma: no cover - netwerk
    antwoord = web._vraag("https://api.imgflip.com/get_memes")
    gezien = {sleutel_imgflip(m["url"]) for m in antwoord.json()["data"]["memes"]}   # de 100 van §93 en §94
    sjablonen = []
    for pagina in range(1, 8):
        if len(sjablonen) >= S4_SJABLONEN:
            break
        a = web._vraag(f"https://imgflip.com/memetemplates?page={pagina}")
        for s in imgflip_sjablonen(a.text if a is not None and a.status_code == 200 else ""):
            if sleutel_imgflip(s["url"]) not in gezien and s["url"] not in {x["url"] for x in sjablonen}:
                sjablonen.append(s)
    # een sjabloon is soms een PNG terwijl de verkleining een JPEG is
    return [{"werk": s["url"], "set": "S4", "vraag": s["url"], "nr": nr, "naam": s["naam"], "rang": nr,
             "adressen": [s["url"], s["url"].rsplit(".", 1)[0] + ".png"]} for nr, s in enumerate(sjablonen[:S4_SJABLONEN])]


def _memes(vectoren):  # pragma: no cover - met het model
    from doublecheck.beeldstilte import maak_meme, onderschriften, splits
    from doublecheck.kadermeting import _kader_b

    rijen = _jsonl(WORTEL / "data" / "stiltetoets" / "regels.jsonl")
    teksten = onderschriften(rijen, S4_EERDER + S4_SJABLONEN * S4_PER_SJABLOON)[S4_EERDER:]

    def maak(sjabloon, w):
        sjabloon.thumbnail((bv.MAX_ZIJDE, bv.MAX_ZIJDE))
        for k in range(S4_PER_SJABLOON):
            meme = maak_meme(sjabloon, *splits(teksten[w["rang"] * S4_PER_SJABLOON + k]))
            yield f"origineel#{k}", bv.vraagkenmerken(meme, vectoren=vectoren)
            yield f"kader_b#{k}", bv.vraagkenmerken(_kader_b(meme), vectoren=vectoren)
    return maak


def _vragen(naam: str, zonder: frozenset = frozenset()) -> None:  # pragma: no cover - netwerk en model
    vectoren = _rekenen()
    if naam == "R2":
        def maak(beeld, _w):
            beeld.thumbnail((bv.MAX_ZIJDE, bv.MAX_ZIJDE))
            yield "origineel", bv.vraagkenmerken(beeld, vectoren=vectoren)
        alle = _werk_r2()
        # hooguit vijf kopieën per claim die lukken: in rondes van vijf kandidaten tot elke claim er vijf heeft
        pad = MAP / "vragen" / "R2.jsonl"
        for _ in range(20):
            gelukt = collections.Counter(r["claim_id"] for r in _jsonl(pad))
            geprobeerd = {r["werk"] for r in _jsonl(pad)} | {r["werk"] for r in _jsonl(pad.with_suffix(".mislukt.jsonl"))}
            volgende, per_claim = [], collections.Counter()
            for w in alle:
                if w["werk"] in geprobeerd or gelukt[w["claim_id"]] + per_claim[w["claim_id"]] >= MAX_KOPIEEN:
                    continue
                per_claim[w["claim_id"]] += 1
                volgende.append(w)
            if not volgende:
                break
            _maak_vragen("R2", volgende, maak)
        return
    web = Beleefd(pauze=2.0)
    werk = {"S1": lambda: _werk_s1(web), "S2": lambda: _werk_s2(web), "S3": _werk_s3, "S4": lambda: _werk_s4(web)}
    lijst_pad = MAP / "vragen" / f"{naam}-lijst.json"
    if lijst_pad.exists():
        lijst = json.loads(lijst_pad.read_text(encoding="utf-8"))
    else:
        lijst = werk[naam]()
        lijst_pad.parent.mkdir(parents=True, exist_ok=True)
        lijst_pad.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
    _maak_vragen(naam, lijst, _memes(vectoren) if naam == "S4" else _vormen(vectoren), zonder=zonder)


def _bouw_index(panelen: bool = False):  # pragma: no cover - op de oogst en de database
    from doublecheck.beeldindex import _lees

    conn = _db()
    groep = {c: (cl or c) for c, cl in conn.execute("SELECT claim_id, cluster_id FROM claim")}
    claims_van = collections.defaultdict(list)
    for c, u in conn.execute("SELECT claim_id, url FROM factcheck WHERE url IS NOT NULL"):
        claims_van[u].append(c)
    regels = met_panelen(_lees(MAP), _lees(PANEELMAP)) if panelen else _lees(MAP)
    return index_uit_regels(regels, claims_van, groep)


def _zoeken(panelen: bool = False) -> None:  # pragma: no cover - op de bestanden
    import numpy as np

    begin = time.monotonic()
    index, info, tel = _bouw_index(panelen)
    achter = "-panelen" if panelen else ""
    print(f"index: {dict(tel)}; gebouwd in {time.monotonic() - begin:.0f} s; vectoren "
          f"{index.vectoren.nbytes / 1e6:.1f} MB, hashes {index.pdq.nbytes / 1e6:.1f} MB", flush=True)
    r1 = _lees_set()["r1"]
    uit, tijden = [], []
    for i, b in enumerate(index.beelden):
        if b["groep"] not in r1:
            continue
        weg = (info["host"] == b["host"]) & (info["groep"] == b["groep"])
        t0 = time.monotonic()
        uit.append(treffer(index, bv.vraag_uit_index(info["kenmerken"][i]),
                           {"set": "R1", "vraag": f"{b['artikel']} {b['beeld']}", "vorm": "origineel",
                            "groep": b["groep"], "host": b["host"]}, np.asarray(weg)))
        tijden.append(time.monotonic() - t0)
    for naam in ("R2",) + SETS_S:
        for v in _jsonl(MAP / "vragen" / f"{naam}.jsonl"):
            meta = {k: v.get(k) for k in ("set", "vraag", "vorm", "groep", "soort", "nr", "claim_id", "persoon")}
            t0 = time.monotonic()
            uit.append(treffer(index, v, meta))
            tijden.append(time.monotonic() - t0)
    (MAP / f"treffers{achter}.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in uit),
                                        encoding="utf-8")
    groepen_met_vraag = {t["groep"] for t in uit if t["set"] == "R1"}
    hosts_met_vraag = collections.defaultdict(set)
    for t in uit:
        if t["set"] == "R1":
            hosts_met_vraag[t["groep"]].add(t["host"])
    info_uit = {"index": dict(tel), "R1 groepen": len(r1), "R1 met een vraag": len(groepen_met_vraag),
                "R1 met beelden van twee redacties": sum(len(h) >= 2 for h in hosts_met_vraag.values()),
                "zoektijd p50 s": float(np.percentile(tijden, 50)), "zoektijd p95 s": float(np.percentile(tijden, 95)),
                "geheugen index MB": round((index.vectoren.nbytes + index.pdq.nbytes) / 1e6, 1),
                "vectoren": len(index.vectoren), "hashes": len(index.pdq)}
    (MAP / f"zoeken{achter}.json").write_text(json.dumps(info_uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(info_uit, ensure_ascii=False, indent=1))
    print(f"{len(uit)} vragen; te lezen: {len(te_lezen(uit, lees_labels()))}", flush=True)


def paren(open_: list[tuple[dict, list]]) -> list[dict]:
    """De te lezen treffers per beeldpaar (set, vraag, beeld in de index): het label gaat over de twee beelden, dus
    origineel en kader B van dezelfde vraag op hetzelfde indexbeeld krijgen het samen."""
    uit: dict[tuple, dict] = {}
    for t, k in open_:
        sleutel = (t["set"], t["vraag"].split("#")[0], k[0])
        p = uit.setdefault(sleutel, {"t": t, "k": k, "sleutels": []})
        p["sleutels"].append(labelsleutel(t, k))
    return list(uit.values())


def _lezen(panelen: bool = False) -> None:  # pragma: no cover - schrijft een leespagina naast de bestanden
    import html

    achter = "-panelen" if panelen else ""
    treffers = _jsonl(MAP / f"treffers{achter}.jsonl")
    lijst = paren(te_lezen(treffers, lees_labels()))
    conn = _db()
    tekst = dict(conn.execute("SELECT claim_id, substr(canonical_text, 1, 300) FROM claim"))
    groep_tekst = {}
    for c, cl in conn.execute("SELECT claim_id, cluster_id FROM claim"):
        groep_tekst.setdefault(cl or c, tekst.get(c, ""))
    rijen = []
    for nr, p in enumerate(lijst):
        t, k = p["t"], p["k"]
        vraag_beeld = t["vraag"].split(" ", 1)[1] if t["set"] == "R1" else t["vraag"]
        uitleg = groep_tekst.get(t.get("groep") or "", "") or t.get("persoon") or t.get("titel") or ""
        rijen.append(f"<tr><td><b>#{nr}</b> {t['set']} · {len(p['sleutels'])} vorm(en) · pdq {t['pdq'] and t['pdq'][3]}"
                     f" · dino {t['dino_gebied'] and t['dino_gebied'][3]}<br><b>vraag:</b> {html.escape(uitleg)}"
                     f"<br><b>index:</b> {html.escape(groep_tekst.get(k[1], ''))}<br>"
                     f"<a href='{html.escape(k[2])}'>{html.escape(k[2][:70])}</a></td>"
                     f"<td><img loading=lazy src='{html.escape(vraag_beeld)}'></td>"
                     f"<td><img loading=lazy src='{html.escape(k[0])}'></td></tr>")
    pagina = ("<!doctype html><meta charset=utf-8><title>Beeldindex lezen</title><style>body{font:12px sans-serif}"
              "table{border-collapse:collapse}td{vertical-align:top;border-bottom:1px solid #ccc;padding:4px;"
              "width:260px}img{width:250px;height:190px;object-fit:contain;background:#eee}</style><table>"
              + "".join(rijen) + "</table>")
    (MAP / f"lezen{achter}.html").write_text(pagina, encoding="utf-8")
    (MAP / f"lezen{achter}.json").write_text(json.dumps([p["sleutels"] for p in lijst], ensure_ascii=False),
                                             encoding="utf-8")
    print(f"{len(lijst)} beeldparen te lezen ({sum(len(p['sleutels']) for p in lijst)} treffers): "
          f"{MAP / f'lezen{achter}.html'}")


def _tellen(panelen: bool = False) -> None:  # pragma: no cover - op de bestanden
    treffers = _jsonl(MAP / ("treffers-panelen.jsonl" if panelen else "treffers.jsonl"))
    s = _lees_set()
    uitslag = telling(treffers, lees_labels(), {"R1": len(s["r1"]), "R2": len(s["r2"])})
    regel = beslisregel_panelen(uitslag) if panelen else beslisregel(uitslag)
    (MAP / ("uitslag-stap2b.json" if panelen else "uitslag-stap2.json")).write_text(json.dumps({"uitslag": uitslag, "beslisregel": regel},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"uitslag": uitslag, "beslisregel": regel}, ensure_ascii=False, indent=1))


def _punten() -> None:  # pragma: no cover - netwerk
    """Stap 2d: de 387 beelden van de artikelen van R2 en de 275 kopieën opnieuw ophalen, alleen in het geheugen;
    elke kopie tegen elk indexbeeld. Op schijf per kopie alleen de beste treffer en de punten per groep."""
    import concurrent.futures as cf

    import cv2

    from doublecheck.beeldindex import _lees, laatste

    cv2.setNumThreads(2)    # hoogstens twee kernen (PO)
    groep_van = {c["url"]: c["groep"] for c in _lees_set()["r2"]}
    web, rekenen = Beleefd(), threading.Lock()

    def haal(werk):
        uit = []
        for w in werk:
            inhoud = web.beeld(w["adres"])
            if inhoud is None:
                continue
            try:
                with rekenen:
                    uit.append({**w, "kenmerken": puntkenmerken(inhoud)})
            except Exception:   # kapot of geen beeld: overslaan, nooit loggen (DR3)
                pass
            del inhoud
        return uit

    def per_host(werk):
        groepen = collections.defaultdict(list)
        for w in werk:
            groepen[host(w["adres"])].append(w)
        with cf.ThreadPoolExecutor(8) as pool:
            return [x for lijst in pool.map(haal, groepen.values()) for x in lijst]

    begin = time.monotonic()
    index = per_host([{"adres": b["beeld"], "groep": groep_van[r["url"]], "artikel": r["url"]}
                      for r in laatste(_lees(PANEELMAP)) if r["status"] == 200 and r["url"] in groep_van
                      for b in r["beelden"] if min(b["breedte"], b["hoogte"]) >= MIN_ZIJDE])
    print(f"index: {len(index)} beelden in {time.monotonic() - begin:.0f} s", flush=True)
    vragen = _jsonl(MAP / "vragen" / "R2.jsonl")
    kopieen_ = per_host([{"adres": v["vraag"], **{k: v[k] for k in ("vraag", "claim_id", "groep", "soort")}}
                         for v in vragen])
    print(f"kopieën: {len(kopieen_)} van {len(vragen)} opgehaald", flush=True)
    regels, tijden = [], []
    for k in kopieen_:
        t0 = time.monotonic()
        uitslagen = [(*puntvergelijking(k["kenmerken"], i["kenmerken"]), i) for i in index]
        tijden.append(time.monotonic() - t0)
        treffers = sorted((u for u in uitslagen if punttreffer(u[0], u[1])), key=lambda u: -u[0])
        per_groep = {}
        for n, dekking, i in uitslagen:
            if n > per_groep.get(i["groep"], (0,))[0]:
                per_groep[i["groep"]] = (n, round(dekking, 3))
        beste = treffers[0] if treffers else None
        regels.append({"set": "R2", "vraag": k["vraag"], "vorm": "origineel", "claim_id": k["claim_id"],
                       "groep": k["groep"], "soort": k["soort"],
                       "beste": [beste[2]["adres"], beste[2]["groep"], beste[2]["artikel"], beste[0],
                                 round(beste[1], 3)] if beste else None,
                       "eigen": per_groep.get(k["groep"], (0, 0.0))})
    (MAP / "punten.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels),
                                      encoding="utf-8")
    import numpy as np
    print(f"vergelijken: {np.percentile(tijden, 50):.2f} s per kopie (p50), {np.percentile(tijden, 95):.2f} s (p95); "
          f"samen {time.monotonic() - begin:.0f} s", flush=True)


def _punten_lezen() -> None:  # pragma: no cover - schrijft een leespagina naast de bestanden
    import html

    regels, labels = _jsonl(MAP / "punten.jsonl"), lees_labels()
    open_ = [r for r in regels if r["beste"] and r["beste"][1] != r["groep"]
             and labelsleutel(r, r["beste"]) not in labels]
    rijen = [f"<tr><td>#{nr} punten {r['beste'][3]} · dekking {r['beste'][4]}<br>{html.escape(r['beste'][2])}</td>"
             f"<td><img loading=lazy src='{html.escape(r['vraag'])}'></td>"
             f"<td><img loading=lazy src='{html.escape(r['beste'][0])}'></td></tr>" for nr, r in enumerate(open_)]
    (MAP / "lezen-punten.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Punten lezen</title><style>body{font:12px sans-serif}"
        "img{width:300px;height:230px;object-fit:contain;background:#eee}</style><table>" + "".join(rijen)
        + "</table>", encoding="utf-8")
    (MAP / "lezen-punten.json").write_text(json.dumps([labelsleutel(r, r["beste"]) for r in open_]), encoding="utf-8")
    print(f"{len(open_)} treffers elders te lezen: {MAP / 'lezen-punten.html'}")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De beeldindex meten op echte screenshots (PLAN #32.15)")
    parser.add_argument("stap", choices=("set", "oogsten", "vision", "vragen", "zoeken", "lezen", "tellen",
                                         "punten", "punten-lezen", "punten-tellen"))
    parser.add_argument("--max", type=int, help="oogsten: de proef, één artikel per host")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--set", dest="welke", choices=("R2",) + SETS_S)
    parser.add_argument("--panelen", action="store_true",
                        help="stap 2b: oogsten, zoeken, lezen en tellen met panelen bij de artikelen van R2")
    parser.add_argument("--zonder-host", action="append", default=[],
                        help="vragen: werk op deze host laten liggen (een ander proces vraagt die host al)")
    args = parser.parse_args()
    if args.stap == "set":
        print(json.dumps(_set(), ensure_ascii=False, indent=1))
    elif args.stap == "oogsten":
        _oogsten(args.max, args.threads, args.panelen)
    elif args.stap == "vision":
        _vision()
    elif args.stap == "vragen":
        if not args.welke:
            raise SystemExit("--set R2|S1|S2|S3|S4")
        _vragen(args.welke, frozenset(args.zonder_host))
    elif args.stap == "punten":
        _punten()
    elif args.stap == "punten-lezen":
        _punten_lezen()
    elif args.stap == "punten-tellen":
        uit = punt_telling(_jsonl(MAP / "punten.jsonl"), lees_labels())
        (MAP / "uitslag-stap2d.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(uit, ensure_ascii=False, indent=1))
    elif args.stap == "zoeken":
        _zoeken(args.panelen)
    elif args.stap == "lezen":
        _lezen(args.panelen)
    else:
        _tellen(args.panelen)


if __name__ == "__main__":
    main()
