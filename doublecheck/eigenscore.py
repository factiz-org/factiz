"""Een eigen beoordeling voor factcheckers en redacties zonder Lin e.a. en zonder teken (PLAN #32.29d, PO 2026-11-03).

Haiku leest per site de openbare pagina's (de voorpagina en hoogstens vijf pagina's over de redactie, de werkwijze, de
correcties, het geld en de code) en zegt eerst wat de site is: een redactie, een factchecker of iets anders. Dan per
vraag ja of nee, met een citaat. Een punt telt alleen als het citaat letterlijk op een van die pagina's staat.
- *Redacties:* de negen vragen naar de openbare criteria van de beoordelaars achter Lin e.a. (#32.29b). De eerste,
  geen herhaald nepnieuws, kan een model niet uit de eigen pagina's halen; die 30 punten geven we zelf, behalve bij een
  signaal van buiten (genoemd bij EUvsDisinfo, of op de lijst met staatsmedia).
- *Factcheckers:* de vijf principes van de code van het IFCN, elk 20 punten.
*Goed* vanaf 65, *laag* tot en met 40, zoals bij Lin. Een factchecker of redactie van een staat of partij (met citaat,
of op de lijst met staatsmedia) is nooit *goed*. Eerst de ijking, met eisen vooraf.

    python -m doublecheck.eigenscore ijkset|ophalen [--set ijk]|indienen [--set ijk]|ophalen-antwoorden|ijktellen
"""

from __future__ import annotations

import json
import random
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "eigenscore"
VERSIE = "eigenscore-v1"
GOED, LAAG = 65, 40
MAX_LINKS, MAX_TEKENS, MAX_VOORPAGINA, MIN_CITAAT = 5, 6000, 4000, 12
BUDGET = 3.0  # PO 2026-11-03, PLAN #32.29d: de lijst en de scores samen binnen $3

# (vraag, punten, wat het model zoekt); "nepnieuws" geven we zelf
VRAGEN = {
    "redactie": [
        ("nepnieuws", 30, None),
        ("correcties", 15, "a published corrections policy, or visible corrections or clarifications"),
        ("mening", 10, "news and opinion are labelled separately"),
        ("koppen", 10, "the headlines on the front page are factual, not sensational or misleading (quote one)"),
        ("code", 10, "a published editorial code or ethics policy, or membership of a press council or ombudsman"),
        ("eigenaar", 10, "who owns the outlet and how it is financed"),
        ("leiding", 5, "who is in charge: the editor-in-chief or editorial leadership by name"),
        ("auteurs", 5, "articles carry the names of their authors"),
        ("reclame", 5, "advertising and sponsored content are labelled as such"),
    ],
    "factchecker": [
        ("partijloos", 20, "a commitment to nonpartisanship and fairness"),
        ("bronnen", 20, "a commitment to show sources so readers can check them"),
        ("geld", 20, "who funds the organisation and how it is organised"),
        ("werkwijze", 20, "a published methodology: how claims are chosen, checked and rated"),
        ("correcties", 20, "an open and honest corrections policy"),
    ],
}
_SOORT = {"newsroom": "redactie", "fact-checker": "factchecker", "other": "anders"}
# Een padstuk dat met een van deze begint, gaat over de redactie, de werkwijze, de correcties, het geld of de code
PADBEGIN = (
    "about", "who-we-are", "our-team", "how-we-work", "team", "staff", "masthead", "impressum", "imprint", "contact",
    "methodolog", "metodolog", "principles", "principios", "principi", "standards", "ethic", "etic", "etik", "deontolog",
    "code-of", "codigo", "kodeks", "editorial", "politica-editorial", "corrections", "correc", "korekt", "korrektur",
    "transparen", "funding", "financ", "finanz", "ownership",
    "quienes", "nosotros", "sobre", "contacto", "expediente", "quem-somos", "ueber-uns", "uber-uns", "wir-ueber",
    "redaktion", "redazione", "redakcija", "redakce", "kontakt", "a-propos", "qui-sommes", "charte", "chi-siamo",
    "o-nas", "o-nama", "o-nás", "za-", "apie", "hakkimizda", "hakkinda", "gywm")
# Een linktekst met een van deze woorden, in de grote schriften
LINKWOORDEN = (
    "about", "who we are", "our team", "methodolog", "corrections", "transparen", "funding", "ethic", "impressum",
    "quiénes", "quienes", "nosotros", "sobre", "metodolog", "correcc", "correç", "financ", "ética", "código", "equipo",
    "expediente", "über uns", "uber uns", "redaktion", "kontakt", "à propos", "qui sommes", "chi siamo", "redazione",
    "о нас", "про нас", "о проекте", "за ", "методолог", "корекц", "коррекц", "исправлен", "редакц", "контакт",
    "关于", "联系我们", "من نحن", "عن ", "منهجي", "אודות", "हमारे बारे", "के बारे")
GOKPADEN = ("about", "about-us", "quienes-somos", "nosotros", "sobre", "sobre-nosotros", "quem-somos", "metodologia",
            "methodology", "impressum", "ueber-uns", "contacto")  # alleen als de voorpagina geen links geeft
MIN_TEKST = 1500  # minder tekst op alle pagina's samen: niet te beoordelen, geen band


class Weigering(Exception):
    """Tellen kan niet: de ijking is niet compleet, of een antwoord ontbreekt."""


# --- de pagina's ---------------------------------------------------------------------------------

class _Lezer(HTMLParser):
    """De zichtbare tekst en de links van een pagina; script, style en noscript tellen niet."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tekst, self.links, self._weg, self._link = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._weg += 1
        elif tag == "a":
            self._link = [dict(attrs).get("href") or "", ""]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._weg = max(0, self._weg - 1)
        elif tag == "a" and self._link is not None:
            self.links.append(tuple(self._link))
            self._link = None

    def handle_data(self, data):
        if not self._weg:
            self.tekst.append(data)
            if self._link is not None:
                self._link[1] += data


def tekst_en_links(html: str, basis: str) -> tuple[str, list[tuple[str, str]]]:
    """De tekst van een pagina (witruimte samengevoegd) en haar links als (adres, linktekst), absoluut gemaakt."""
    lezer = _Lezer()
    lezer.feed(html or "")
    tekst = " ".join(" ".join(lezer.tekst).split())
    return tekst, [(urljoin(basis, h), " ".join(t.split())) for h, t in lezer.links if h]


def _site(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def kies_links(links: list[tuple[str, str]], basis: str, n: int = MAX_LINKS) -> list[str]:
    """Hoogstens `n` links op dezelfde site die over de redactie, de werkwijze, de correcties, het geld of de code gaan,
    naar het adres of de linktekst; zonder anker, elk één keer, in de volgorde van de pagina."""
    uit, eigen = [], _site(basis)
    for url, tekst in links:
        delen = urlsplit(url)
        if delen.scheme not in ("http", "https") or _site(url) != eigen:
            continue
        schoon = urlunsplit((delen.scheme, delen.netloc, delen.path, delen.query, ""))
        pad = (delen.path or "").lower()
        if schoon in uit or schoon.rstrip("/") == basis.rstrip("/"):
            continue
        if any(stuk.startswith(PADBEGIN) for stuk in pad.split("/") if stuk) \
                or any(w in tekst.lower() for w in LINKWOORDEN):
            uit.append(schoon)
        if len(uit) == n:
            break
    return uit


# --- de vraag ------------------------------------------------------------------------------------

SYSTEEM = ("You assess the transparency of a news website or fact-checking organisation from its own public pages. "
           "Answer only from the page texts given. Quote the exact words from a page; never paraphrase, never guess.")

VRAAG_V1 = """Website: {site}

First say what this site is:
- "newsroom": a news organisation (newspaper, broadcaster, news agency, news website or magazine);
- "fact-checker": an organisation whose main work is checking claims;
- "other": anything else (shop, blog, company, government, party, campaign, encyclopedia, platform).

Say whether the pages state that the site is run or funded by a government, a state agency or a political party
("staat_of_partij"), with the exact quote ("staat_citaat"), or false and an empty quote.

Then answer each question below with "ja": true only if a page shows it, with the exact quote (at least a few words,
copied character for character) and the page number [P1], [P2], ... Otherwise "ja": false and an empty quote.

For a newsroom:
{redactie}

For a fact-checker:
{factchecker}

Pages:
{paginas}"""

VRAGEN_TEKST = {"eigenscore-v1": VRAAG_V1}

_SCHEMA = {"type": "object", "additionalProperties": False,
           "required": ["soort", "staat_of_partij", "staat_citaat", "antwoorden"],
           "properties": {
               "soort": {"type": "string", "enum": list(_SOORT)},
               "staat_of_partij": {"type": "boolean"}, "staat_citaat": {"type": "string"},
               "antwoorden": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["vraag", "ja", "citaat", "pagina"],
                   "properties": {"vraag": {"type": "string"}, "ja": {"type": "boolean"},
                                  "citaat": {"type": "string"}, "pagina": {"type": "integer"}}}}}}


def verzoek(site: str, paginas: list[dict], versie: str = VERSIE, max_tokens: int = 3000) -> dict:
    """De vraag aan Haiku voor één site, met vaste JSON; de pagina's genummerd [P1], [P2], ... Met 1.500 tokens werd
    een antwoord met lange citaten (Arabisch, Duits) afgebroken in de eerste ijking; daarom 3.000."""
    from doublecheck.modellen import MODELLEN

    if versie not in VRAGEN_TEKST:
        raise ValueError(f"eigenscore {versie!r} bestaat niet in de code")

    def lijst(soort):
        return "\n".join(f'- "{v}": {wat}' for v, _, wat in VRAGEN[soort] if wat)

    blokken = "\n\n".join(f"[P{i}] {p['url']}\n{p['tekst'][:MAX_VOORPAGINA if i == 1 else MAX_TEKENS]}"
                          for i, p in enumerate(paginas, 1))
    tekst = VRAGEN_TEKST[versie].format(site=site, redactie=lijst("redactie"), factchecker=lijst("factchecker"),
                                        paginas=blokken)
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": max_tokens, "system": SYSTEEM,
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def _vlak(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def _gevonden(citaat: str, paginas: list[dict]) -> bool:
    c = _vlak(citaat)
    return len(c) >= MIN_CITAAT and any(c in _vlak(p["tekst"]) for p in paginas)


def leesbaar(paginas: list[dict]) -> bool:
    """Genoeg tekst om te beoordelen (`MIN_TEKST` tekens op alle pagina's samen)."""
    return sum(len(p["tekst"]) for p in paginas) >= MIN_TEKST


def band(totaal: int) -> str:
    return "goed" if totaal >= GOED else "laag" if totaal <= LAAG else "wisselend"


def lees(tekst: str | None, paginas: list[dict], signaal: bool, staat: bool = False) -> dict:
    """De punten uit het antwoord. Een ja telt alleen met een citaat dat op een van de pagina's staat (hoofdletters en
    witruimte tellen niet). `signaal`: een signaal van buiten over nepnieuws (EUvsDisinfo, staatsmedia) neemt bij een
    redactie de 30 punten weg; `staat`: de lijst met staatsmedia, die goed uitsluit. Onleesbaar of *anders*: geen band."""
    leeg = {"soort": None, "punten": {}, "totaal": None, "band": None, "staat": False, "niet gevonden": [],
            "te weinig tekst": not leesbaar(paginas)}
    if leeg["te weinig tekst"]:
        return leeg
    try:
        d = json.loads(tekst) if isinstance(tekst, str) else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or d.get("soort") not in _SOORT or not isinstance(d.get("antwoorden"), list):
        return leeg
    soort = _SOORT[d["soort"]]
    if soort == "anders":
        return {**leeg, "soort": soort}
    # de naam van de vraag, ook als het model de uitleg erachter zet ("partijloos: a commitment ...")
    ja = {str(a.get("vraag")).split(":")[0].strip().lower(): a.get("citaat") or "" for a in d["antwoorden"]
          if isinstance(a, dict) and a.get("ja") is True}
    punten, mis = {}, []
    for vraag, max_, wat in VRAGEN[soort]:
        if wat is None:
            punten[vraag] = 0 if signaal else max_
        elif vraag in ja and _gevonden(ja[vraag], paginas):
            punten[vraag] = max_
        else:
            punten[vraag] = 0
            if vraag in ja:
                mis.append(vraag)
    van_staat = staat or (d.get("staat_of_partij") is True and _gevonden(d.get("staat_citaat") or "", paginas))
    totaal = sum(punten.values())
    b = band(totaal)
    if van_staat and b == "goed":
        b = "wisselend"
    return {**leeg, "soort": soort, "punten": punten, "totaal": totaal, "band": b, "staat": van_staat,
            "niet gevonden": mis}


# --- de ijking -----------------------------------------------------------------------------------

def trek_ijkset(kandidaten: dict[str, str], aantallen: dict[str, int], zaad: int) -> list[str]:
    """Per band van Lin e.a. een vast aantal sites, getrokken met een vast zaad; de volgorde van de invoer telt niet."""
    uit = []
    for b in ("goed", "wisselend", "laag"):
        hier = sorted(s for s, x in kandidaten.items() if x == b)
        uit += random.Random(f"{zaad}-{b}").sample(hier, min(aantallen.get(b, 0), len(hier)))
    return uit


def ijk_eisen(redacties: list[tuple[str, str]], factcheckers: dict[str, list]) -> dict[str, bool]:
    """De eisen van PLAN #32.29d. `redacties`: per site (band van Lin, eigen band), zonder de sites die het model
    *anders* noemt; hoogstens 2 in een andere band en nooit goed tegen laag. `factcheckers`: de eigen banden van de
    sites met een IFCN-teken (hoogstens 1 niet goed) en van de propagandasites (geen enkele goed)."""
    anders = sum(lin != eigen for lin, eigen in redacties)
    tegen = any({lin, eigen} == {"goed", "laag"} for lin, eigen in redacties)
    met = factcheckers["met teken"]
    return {"redacties in dezelfde band": anders <= 2, "nooit goed tegen laag": not tegen,
            "factcheckers met teken goed": sum(b != "goed" for b in met) <= 1,
            "geen propaganda goed": not any(b == "goed" for b in factcheckers["propaganda"])}


# --- de stappen ----------------------------------------------------------------------------------

IJKSET, IJKLIN = UIT / "ijkset.json", UIT / "ijkset-lin.json"
PROPAGANDA = ("globalfactchecking.com", "lapsha.media", "piyao.org.cn")  # PLAN #32.29d, met bron
AANTALLEN, ZAAD_REDACTIES, ZAAD_FACTCHECKERS, N_FACTCHECKERS = {"goed": 7, "wisselend": 4, "laag": 3}, 32293, 32294, 15
SCHATTING_PER_SITE = 0.002  # Haiku via de Batch API, ruim


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    return [json.loads(r) for r in inhoud[:inhoud.rfind("\n") + 1].splitlines() if r.strip()]


def _schrijf(pad: Path, regels: list[dict]) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as fh:
        for r in regels:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _lin_band(oordelen: list) -> str | None:
    from doublecheck import bronnen as br

    lin = [float(br.reden(h).split()[-1]) for _, h in oordelen if br.reden(h).startswith("Lin e.a. ")]
    return br._band_lin(lin[0]) if lin else None


def _ijkset() -> None:  # pragma: no cover - op de bestanden
    """De ijkset, vóór de eerste score: 14 nieuwssites met een Lin-score uit onze zoekresultaten (minstens 2 keer
    genoemd), 15 IFCN-leden die actief zijn, en de 3 propagandasites. De banden van Lin gaan in een eigen bestand, dat
    alleen `ijktellen` leest."""
    import collections
    import csv

    from doublecheck import bronnen as br
    from doublecheck import bronnenlijst as bl
    from doublecheck import bronnendekking as bd

    if IJKSET.exists():
        raise Weigering(f"{IJKSET.name} ligt al vast")
    sites = json.loads(br.BESTAND.read_text(encoding="utf-8"))["sites"]
    urls = [u for r in bd._jsonl(bd.RESULTATEN) for u in r["urls"]]
    ontwikkel, toets = bl.antwoorden()
    urls += [u for _, bronnen, _ in ontwikkel + toets for u in set(bl._webadressen(bronnen))]
    tel, banden = collections.Counter(), {}
    for u in urls:
        b = br.beoordeel(u, sites)
        if b["soort"] == "overig" and (lin := _lin_band(b["bronnen"])):
            tel[b["site"]] += 1
            banden[b["site"]] = lin
    kandidaten = {s: banden[s] for s, n in tel.items() if n >= 2}
    redacties = trek_ijkset(kandidaten, AANTALLEN, ZAAD_REDACTIES)
    ifcn = sorted({_site("https://" + r["website"].split("://")[-1]) for r in csv.DictReader(
        (bl.EXTERN / "ifcn" / "organisaties.tsv").open(encoding="utf-8"), delimiter="\t")
        if r["status"] == "actief" and r["website"].strip()} - {""})
    factcheckers = random.Random(ZAAD_FACTCHECKERS).sample(ifcn, N_FACTCHECKERS)
    UIT.mkdir(parents=True, exist_ok=True)
    IJKSET.write_text(json.dumps({"redacties": redacties, "factcheckers": factcheckers, "propaganda": list(PROPAGANDA)},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    IJKLIN.write_text(json.dumps({s: kandidaten[s] for s in redacties}, ensure_ascii=False), encoding="utf-8")
    print(f"ijkset: {len(redacties)} redacties (uit {len(kandidaten)} met een Lin-score), {len(factcheckers)} "
          f"factcheckers met een IFCN-teken, {len(PROPAGANDA)} propagandasites")


def _sites(welke: str) -> list[str]:  # pragma: no cover - op de bestanden
    if welke == "ijk":
        d = json.loads(IJKSET.read_text(encoding="utf-8"))
        return d["redacties"] + d["factcheckers"] + d["propaganda"]
    raise Weigering(f"onbekende set {welke!r}; eerst de ijking (PLAN #32.29d)")


def _ophalen(welke: str) -> None:  # pragma: no cover - netwerk
    """Per site de voorpagina en hoogstens vijf pagina's, beleefd (per host één verzoek, robots.txt); alleen de tekst
    wordt bewaard, nooit de HTML. Hervatbaar."""
    import concurrent.futures as cf
    import threading

    from doublecheck import beeldindexmeting as bm

    pad = UIT / f"paginas-{welke}.jsonl"
    gedaan = {r["site"] for r in _jsonl(pad)}
    werk = [s for s in _sites(welke) if s not in gedaan]
    web, slot = bm.Beleefd(), threading.Lock()

    def html(url: str) -> str | None:
        if not web.mag(url):
            return None
        a = web._vraag(url)
        if a is None or a.status_code != 200 or "html" not in (a.headers.get("content-type") or ""):
            return None
        return a.text

    def doe(site: str) -> None:
        basis, paginas, status = f"https://{site}/", [], "ok"
        try:
            voor = html(basis) or html(f"https://www.{site}/")
            if voor is None:
                status = "niet opgehaald"
            else:
                tekst, links = tekst_en_links(voor, basis)
                paginas.append({"url": basis, "tekst": tekst[:MAX_TEKENS]})
                gekozen = kies_links(links, basis)
                if len(gekozen) < 2:
                    gekozen += [basis + g for g in GOKPADEN if basis + g not in gekozen]
                for u in gekozen:
                    h = html(u)
                    if h:
                        paginas.append({"url": u, "tekst": tekst_en_links(h, u)[0][:MAX_TEKENS]})
                    if len(paginas) > MAX_LINKS:
                        break
        except Exception as e:  # noqa: BLE001 - alleen de soort fout
            status = f"fout {type(e).__name__}"
        with slot:
            _schrijf(pad, [{"site": site, "status": status, "paginas": paginas}])
            print(f"{site}: {status}, {len(paginas)} pagina's", flush=True)

    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(doe, werk))


def _uitgegeven() -> float:  # pragma: no cover - een bestand
    return sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"]
               for b in _jsonl(UIT / "batches.jsonl"))


def _indienen(welke: str, opnieuw: tuple[str, ...] = ()) -> None:  # pragma: no cover - netwerk
    """Eén vraag per site met pagina's, via de Batch API (openbare pagina's), binnen de grens. `opnieuw`: sites waarvan
    het antwoord afgebroken was; hun nieuwe antwoord vervangt het oude."""
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart = UIT / "kaart.jsonl"
    gevraagd = {r["site"] for r in _jsonl(kaart)} - set(opnieuw)
    werk = [r for r in _jsonl(UIT / f"paginas-{welke}.jsonl") if leesbaar(r["paginas"]) and r["site"] not in gevraagd]
    if not werk:
        print("niets te vragen")
        return
    schatting = SCHATTING_PER_SITE * len(werk)
    if _uitgegeven() + schatting > BUDGET:
        raise Weigering(f"de grens: ${_uitgegeven():.2f} plus ${schatting:.2f} komt boven ${BUDGET:.2f}")
    begin = len(_jsonl(kaart))
    verzoeken = [{"custom_id": f"es-{i:05d}", "params": verzoek(r["site"], r["paginas"])}
                 for i, r in enumerate(werk, begin)]
    batch = client.messages.batches.create(requests=verzoeken)
    _schrijf(kaart, [{"custom_id": v["custom_id"], "site": r["site"], "set": welke, "batch": batch.id}
                     for v, r in zip(verzoeken, werk)])
    _schrijf(UIT / "batches.jsonl", [{"id": batch.id, "set": welke, "aantal": len(werk), "schatting": schatting}])
    print(f"batch {batch.id}: {len(werk)} sites, schatting ${schatting:.3f}; samen ${_uitgegeven():.2f} van "
          f"${BUDGET:.2f}")


def _antwoorden() -> None:  # pragma: no cover - netwerk
    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart = {r["custom_id"]: r for r in _jsonl(UIT / "kaart.jsonl")}
    alle = _jsonl(UIT / "batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog")
            continue
        werkelijk, mis, regels = 0.0, 0, []
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded" or r.custom_id not in kaart:
                mis += 1
                continue
            werkelijk += kosten_batch(bc.gebruik_uit(r.result.message), "haiku")
            regels.append({"site": kaart[r.custom_id]["site"], "versie": VERSIE,
                           "antwoord": "".join(getattr(x, "text", "") or "" for x in r.result.message.content)})
        _schrijf(UIT / "antwoorden.jsonl", regels)
        b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
        print(f"batch {b['id']}: ${werkelijk:.3f}, {mis} mislukt")
    (UIT / "batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(f"samen ${_uitgegeven():.2f} van ${BUDGET:.2f}")


def _signalen() -> tuple[set[str], dict]:  # pragma: no cover - op de database
    """De sites die EUvsDisinfo als bron van desinformatie noemt (de namen die een domein zijn), en de lijst met
    staatsmedia."""
    import sqlite3

    from doublecheck import zoekcontrole as zc

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    namen = {n.lower().removeprefix("www.") for (n,) in conn.execute("SELECT naam FROM actor")
             if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", (n or "").lower())}
    return namen, zc._staat()


def beoordeel_site(site: str, antwoord: str | None, paginas: list[dict], euvs: set[str], staat: dict) -> dict:
    """De score van één site, met de signalen van buiten."""
    from doublecheck import staatsmedia

    van_staat = staatsmedia.label(f"https://{site}/", staat) is not None
    return lees(antwoord, paginas, signaal=site in euvs or van_staat, staat=van_staat)


def _ijktellen() -> None:  # pragma: no cover - op de bestanden
    ijk = json.loads(IJKSET.read_text(encoding="utf-8"))
    antwoorden = {r["site"]: r["antwoord"] for r in _jsonl(UIT / "antwoorden.jsonl")}
    paginas = {r["site"]: r["paginas"] for r in _jsonl(UIT / "paginas-ijk.jsonl")}
    open_ = [s for s in ijk["redacties"] + ijk["factcheckers"] + ijk["propaganda"]
             if leesbaar(paginas.get(s) or []) and s not in antwoorden]
    if open_:
        raise Weigering(f"{len(open_)} sites zonder antwoord, bijvoorbeeld {open_[0]}")
    euvs, staat = _signalen()
    score = {s: beoordeel_site(s, antwoorden.get(s), paginas.get(s) or [], euvs, staat)
             for s in ijk["redacties"] + ijk["factcheckers"] + ijk["propaganda"]}
    lin = json.loads(IJKLIN.read_text(encoding="utf-8"))
    redacties = [(lin[s], score[s]["band"]) for s in ijk["redacties"]
                 if not score[s]["te weinig tekst"] and score[s]["soort"] not in ("anders", None)]
    fc = {"met teken": [score[s]["band"] for s in ijk["factcheckers"] if not score[s]["te weinig tekst"]],
          "propaganda": [score[s]["band"] for s in ijk["propaganda"] if not score[s]["te weinig tekst"]]}
    eisen = ijk_eisen(redacties, fc)
    uit = {"versie": VERSIE, "eisen": eisen, "per site": {
        s: {**score[s], "lin": lin.get(s), "pagina's": len(paginas.get(s) or [])} for s in score}}
    (UIT / "ijkuitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    for groep in ("redacties", "factcheckers", "propaganda"):
        print(groep)
        for s in ijk[groep]:
            r = uit["per site"][s]
            totaal, n = ("-" if r["totaal"] is None else r["totaal"]), r["pagina's"]
            print(f"  {s:32} soort {r['soort'] or '-':11} punten {totaal:>4} band {r['band'] or '-':9} "
                  f"lin {r['lin'] or '-':9} pagina's {n}")
    print("eisen:", eisen)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Een eigen beoordeling voor sites zonder Lin en zonder teken (#32.29d)")
    parser.add_argument("stap", choices=("ijkset", "ophalen", "indienen", "ophalen-antwoorden", "ijktellen"))
    parser.add_argument("--set", default="ijk")
    parser.add_argument("--opnieuw", default="", help="sites met een afgebroken antwoord, met komma's")
    args = parser.parse_args()
    {"ijkset": _ijkset, "ophalen": lambda: _ophalen(args.set), "indienen": lambda: _indienen(args.set, tuple(x for x in args.opnieuw.split(",") if x)),
     "ophalen-antwoorden": _antwoorden, "ijktellen": _ijktellen}[args.stap]()


if __name__ == "__main__":
    main()
