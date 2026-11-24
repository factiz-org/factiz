"""Wat de factchecks ons leren: hoe het bericht eruitzag, welke truc het gebruikte en hoe de factchecker erachter kwam
(PLAN #32.39, PO 2026-11-04).

Een gespreide steekproef van 2.000 factcheckartikelen met een onwaar, misleidend of deels waar oordeel (de helft
Engels, de helft uit 2023–2026, hoogstens 40 per redactie), en 200 uit M4FC waar mensen al zeiden hoe de check ging.
Per artikel beleefd de titel en de alineatekst (per host één verzoek, robots.txt, als FactizResearch), tijdelijk op
schijf tot het nakijken klaar is (`opruimen`). Haiku leest elk artikel via de Batch API (openbare artikelen) met een
vast JSON-schema (`truc-v1`). Een methode telt alleen met een citaat dat letterlijk in het artikel staat.

    python -m doublecheck.werkwijze set|ophalen|indienen [--proef N]|antwoorden|lezen|tellen|opruimen
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import random
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "werkwijze"
LABELS = WORTEL / "docs" / "steekproeven" / "32.39-werkwijze.json"
M4FC = WORTEL / "data" / "extern" / "m4fc" / "M4FC.json"
VERSIE = "truc-v1"
ONWAAR = ("onwaar", "misleidend", "deels-waar")
PER_TAAL = {"en": 1000, "es": 150, "pt": 150, "de": 150}
REST = 550  # de andere talen samen
N_M4FC = 200
RECENT = 2023  # de helft van elke taal uit 2023–2026
RESERVE = 1.4  # zoveel kandidaten per plek: een deel is niet op te halen
MAX_PER_REDACTIE = 40
ZAAD = 3243
BUDGET = 1.00  # PLAN #32.39: grens $1
SCHATTING = 0.0003  # per artikel: ~2.700 tokens in en 400 uit, Haiku in de batch
MAX_TEKENS, MIN_TEKST, MIN_CITAAT = 8000, 800, 12
N_NAKIJKEN = 100
DRADEN = 12
KOP = {"User-Agent": "Mozilla/5.0 (FactizResearch; #32.39, leest factcheckartikelen om te leren hoe factcheckers "
                     "werken, bewaart geen beelden; https://factiz.org)"}

# Wat het model kiest (Engels, de artikelen zijn in alle talen) en hoe wij het noemen
VORMEN = {"video": "video", "photo": "foto", "post screenshot": "screenshot van een post",
          "quote card or graphic": "citaatkaart of grafiek", "front page or cover": "voorpagina of cover",
          "document or letter": "document of brief", "fake website or article": "nagemaakte website of artikel",
          "audio": "audio", "text only": "alleen tekst", "other": "anders", "unclear": "onduidelijk"}
TRUCS = {"fabricated": "verzonnen", "imposter": "nagemaakt", "manipulated": "bewerkt", "ai-generated": "AI-gemaakt",
         "false connection": "vals verband", "false context": "valse context", "misleading": "misleidend",
         "satire": "satire", "unclear": "onduidelijk"}
NAGEDAAN = {"news outlet": "medium", "person": "persoon", "government or institution": "overheid of instelling",
            "organisation or company": "organisatie of bedrijf", "none": "niemand"}
ONDERWERPEN = ("politics", "war and conflict", "health", "migration", "climate and environment", "economy",
               "science and technology", "crime and justice", "disasters", "religion", "celebrities", "sports",
               "other")
METHODEN = {
    "reverse image search": "omgekeerd zoeken op het beeld",
    "keyword search": "zoeken op woorden",
    "checked with the source": "bij de bron zelf nagegaan",
    "official data or documents": "officiële cijfers of documenten",
    "news reports": "het echte nieuws",
    "no credible report": "geen betrouwbare bron meldt het",
    "geolocation": "de plek bepaald",
    "ai detection": "AI-detector of kenmerken van AI",
    "image forensics or metadata": "het beeld of de metadata onderzocht",
    "the account behind the post": "het account achter het bericht",
    "expert": "een deskundige",
    "archive or earlier version": "het archief of een eerdere versie",
    "other": "anders",
}
# De strategieën van M4FC (`verification_strategy`) in onze methoden; "other" en "not enough information" tellen niet
M4FC_METHODE = {"reverse image search": "reverse image search", "keyword search": "keyword search",
                "geolocation": "geolocation", "ai detectors": "ai detection",
                "forensic": "image forensics or metadata", "profiling": "the account behind the post"}


class Weigering(Exception):
    """Indienen of tellen kan niet: boven de grens, of een nagekeken artikel zonder label."""


# --- de steekproef ---------------------------------------------------------------------------------------------

def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def steekproef(rijen: list[dict], dood: set[str], per_taal: dict[str, int] = PER_TAAL, rest: int = REST,
               reserve: float = RESERVE, max_per: int = MAX_PER_REDACTIE, zaad: int = ZAAD,
               dode_hosts: frozenset[str] = frozenset()) -> list[dict]:
    """De kandidaten, in een vaste volgorde. Per taal (de andere talen samen als *rest*) de helft uit `RECENT` en
    later; is een helft te klein, dan vult de andere helft aan. Per plek `reserve` keer zoveel kandidaten als nodig,
    hoogstens `max_per` per redactie, alleen een onwaar, misleidend of deels waar oordeel, nooit een dode link."""
    gezien, pool = set(), collections.defaultdict(list)
    geschud = sorted(rijen, key=lambda r: (r["url"], r.get("claim") or ""))
    random.Random(zaad).shuffle(geschud)
    for r in geschud:
        if r["oordeel"] not in ONWAAR or r["url"] in dood or r["url"] in gezien or _host(r["url"]) in dode_hosts:
            continue
        gezien.add(r["url"])
        groep = r["language"] if r["language"] in per_taal else "rest"
        pool[(groep, "recent" if r["jaar"] >= RECENT else "ouder")].append(r)
    doelen = {}
    for groep, n in [*per_taal.items(), ("rest", rest)]:
        recent, ouder = math.ceil(n / 2), n // 2
        if len(pool[(groep, "ouder")]) < ouder * reserve:
            tekort = ouder - int(len(pool[(groep, "ouder")]) / reserve)
            recent, ouder = recent + tekort, ouder - tekort
        elif len(pool[(groep, "recent")]) < recent * reserve:
            tekort = recent - int(len(pool[(groep, "recent")]) / reserve)
            recent, ouder = recent - tekort, ouder + tekort
        doelen[(groep, "recent")], doelen[(groep, "ouder")] = recent, ouder
    per_uitgever, uit = collections.Counter(), []
    for laag, doel in doelen.items():
        genomen = 0
        for r in pool[laag]:
            if genomen >= round(doel * reserve):
                break
            if per_uitgever[r["publisher"]] >= max_per:
                continue
            per_uitgever[r["publisher"]] += 1
            genomen += 1
            uit.append({**r, "id": hashlib.sha1(r["url"].encode()).hexdigest()[:16], "laag": list(laag),
                        "quotum": doel})
    return uit


def m4fc_methoden(strategie: str) -> set[str]:
    """De strategieën die mensen bij M4FC opschreven ("reverse image search; keyword search"), als onze methoden."""
    return {M4FC_METHODE[s.strip()] for s in strategie.split(";") if s.strip() in M4FC_METHODE}


def m4fc_steekproef(rijen: list[dict], n: int = N_M4FC, reserve: float = RESERVE, zaad: int = ZAAD) -> list[dict]:
    """Artikelen uit M4FC waarbij mensen een methode noemden die wij kennen, in een vaste volgorde."""
    gezien, kandidaten = set(), []
    for r in sorted(rijen, key=lambda r: r["article_url"]):
        if r["article_url"] in gezien or not m4fc_methoden(r.get("verification_strategy") or ""):
            continue
        gezien.add(r["article_url"])
        kandidaten.append(r)
    random.Random(zaad).shuffle(kandidaten)
    return [{"url": r["article_url"], "publisher": r["fc_org"], "language": r["fc_language"],
             "jaar": int((r.get("fc_pub_date") or "0")[:4] or 0), "oordeel": r["verdict"], "claim": r["claim"],
             "m4fc": r["verification_strategy"], "id": hashlib.sha1(r["article_url"].encode()).hexdigest()[:16],
             "laag": ["m4fc", "alle"], "quotum": n} for r in kandidaten[:round(n * reserve)]]


def kies_leesbaar(rijen: list[dict], leesbaar: set[str]) -> list[dict]:
    """Per plek de eerste leesbare artikelen, in de volgorde van de steekproef, tot het quotum."""
    genomen, uit = collections.Counter(), []
    for r in rijen:
        laag = tuple(r["laag"])
        if r["id"] in leesbaar and genomen[laag] < r["quotum"]:
            genomen[laag] += 1
            uit.append(r)
    return uit


# --- de vraag ----------------------------------------------------------------------------------------------------

SYSTEEM = ("You read one fact-check article and describe, only from what the article itself says, what the debunked "
           "post looked like, which trick it used, and how the fact-checker found out. You never judge the claim "
           "yourself and you never add what the article does not say.")

VRAAG_V1 = """Article: {url}
Title: {titel}

{tekst}

Answer in JSON:
- fact_check: true if this page is a fact-check of a claim; false if it is something else (an index page, a paywall, an
  error page, a news story without a debunked claim).
- vorm: what the debunked post looked like: {vormen}.
- truc: the main trick, one of:
  - fabricated: made up, entirely false
  - imposter: it pretends to come from a real outlet, person or institution (a logo, a fake account, a fake front page)
  - manipulated: a real image, video, audio or document that was edited
  - ai-generated: an image, video or voice made with AI
  - false connection: the headline, caption or visuals do not match the content
  - false context: genuine content shared with a false date, place or story
  - misleading: true facts used to mislead (cherry-picking, missing context)
  - satire: satire or parody taken as real
  - unclear: the article does not say
- nagedaan and wie: if the trick is imposter, who was imitated ({nagedaan}) and the name; otherwise "none" and "".
- verhaal: the false story in one sentence, in English.
- onderwerp: the topic.
- methoden: every method the fact-checker says they used to find out. For each, a quote of 5 to 25 words copied
  exactly from the article, in its own language, never translated:
  - reverse image search: searched the image or video frames (Google Lens, TinEye, Yandex, InVID) and found a copy
  - keyword search: searched the web or social media with keywords
  - checked with the source: asked or checked the outlet, person or institution the post names (their own website,
    account or spokesperson)
  - official data or documents: official statistics, records, laws or reports
  - news reports: what credible news media reported about the real event
  - no credible report: no credible outlet or official source reported it
  - geolocation: located where the image or video was taken
  - ai detection: AI detection tools or visible signs of AI
  - image forensics or metadata: metadata, error level analysis, visual inconsistencies
  - the account behind the post: who posted it first, the account's history or network
  - expert: asked an expert
  - archive or earlier version: the Wayback Machine or an earlier version of the page or post
  - other
  An empty list if the article does not say how."""

VRAGEN = {"truc-v1": VRAAG_V1}

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["fact_check", "vorm", "truc", "nagedaan", "wie", "verhaal", "onderwerp", "methoden"],
          "properties": {
              "fact_check": {"type": "boolean"},
              "vorm": {"type": "string", "enum": list(VORMEN)},
              "truc": {"type": "string", "enum": list(TRUCS)},
              "nagedaan": {"type": "string", "enum": list(NAGEDAAN)},
              "wie": {"type": "string"},
              "verhaal": {"type": "string"},
              "onderwerp": {"type": "string", "enum": list(ONDERWERPEN)},
              "methoden": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False, "required": ["methode", "citaat"],
                  "properties": {"methode": {"type": "string", "enum": list(METHODEN)},
                                 "citaat": {"type": "string"}}}}}}


def verzoek(artikel: dict, tekst: dict, versie: str = VERSIE) -> dict:
    """De vraag aan Haiku over één artikel (`tekst`: titel en alineatekst), met vaste JSON."""
    from doublecheck.modellen import MODELLEN

    if versie not in VRAGEN:
        raise ValueError(f"werkwijze {versie!r} bestaat niet in de code")
    inhoud = VRAGEN[versie].format(url=artikel["url"], titel=tekst["titel"], tekst=tekst["tekst"][:MAX_TEKENS],
                                   vormen=", ".join(VORMEN), nagedaan=", ".join(NAGEDAAN))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 1500, "system": SYSTEEM,
            "messages": [{"role": "user", "content": [{"type": "text", "text": inhoud}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}}


def _vlak(tekst: str) -> str:
    return " ".join((tekst or "").split()).casefold()


def citaat_staat_erin(citaat: str, artikel: str) -> bool:
    """Het citaat staat letterlijk in het artikel; hoofdletters en witruimte tellen niet, te kort telt nooit."""
    c = _vlak(citaat)
    return len(c) >= MIN_CITAAT and c in _vlak(artikel)


def lees_antwoord(tekst: str | None, artikel: str) -> dict:
    """Het antwoord van Haiku, streng gelezen: een ongeldig antwoord telt niet, en een methode telt alleen met een
    citaat dat letterlijk in het artikel staat."""
    try:
        d = json.loads(tekst) if isinstance(tekst, str) else None
    except json.JSONDecodeError:
        d = None
    nodig = ("fact_check", "vorm", "truc", "nagedaan", "wie", "verhaal", "onderwerp", "methoden")
    if (not isinstance(d, dict) or any(k not in d for k in nodig) or d["vorm"] not in VORMEN
            or d["truc"] not in TRUCS or d["nagedaan"] not in NAGEDAAN or not isinstance(d["methoden"], list)
            or not all(isinstance(m, dict) and m.get("methode") in METHODEN and isinstance(m.get("citaat"), str)
                       for m in d["methoden"])):
        return {"leesbaar": False}
    methoden, niet, citaten = [], [], {}
    for m in d["methoden"]:
        naam = METHODEN[m["methode"]]
        if citaat_staat_erin(m["citaat"], artikel):
            if naam not in methoden:
                methoden.append(naam)
                citaten[naam] = m["citaat"]
        elif naam not in niet:
            niet.append(naam)
    return {"leesbaar": True, "factcheck": d["fact_check"] is True, "vorm": VORMEN[d["vorm"]],
            "truc": TRUCS[d["truc"]], "nagedaan": NAGEDAAN[d["nagedaan"]], "wie": str(d["wie"]),
            "verhaal": str(d["verhaal"]), "onderwerp": d["onderwerp"], "methoden": methoden,
            "niet gevonden": [n for n in niet if n not in methoden], "citaten": citaten}


def binnen_grens(geschat: float, uitgegeven: float, grens: float = BUDGET) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} al uitgegeven plus ${geschat:.2f} is meer dan ${grens:.2f}")


# --- het tellen --------------------------------------------------------------------------------------------------

def telling_nakijken(gelezen: list[dict], labels: dict[str, dict], nakijken: list[str]) -> dict:
    """Per veld (vorm, truc, methode) hoeveel van de nagekeken artikelen goed zijn; de eis is 90 van de 100. Weigert
    zolang een nagekeken artikel geen label heeft voor elk veld."""
    open_ = [i for i in nakijken if not all(labels.get(i, {}).get(v) in ("goed", "fout")
                                            for v in ("vorm", "truc", "methode"))]
    if open_:
        raise Weigering(f"{len(open_)} van de {len(nakijken)} nog zonder label in {LABELS.name}; eerst nakijken")
    uit = {}
    for veld in ("vorm", "truc", "methode"):
        goed = sum(labels[i][veld] == "goed" for i in nakijken)
        uit[veld] = {"goed": goed, "van": len(nakijken), "gehaald": goed * 10 >= len(nakijken) * 9}
    return uit


def m4fc_overeenkomst(gelezen: list[dict]) -> dict:
    """Per methode die mensen bij M4FC noemden: bij hoeveel artikelen, en hoe vaak Haiku haar ook noemt."""
    uit = collections.defaultdict(lambda: {"mensen": 0, "haiku ook": 0})
    for r in gelezen:
        if not r.get("m4fc") or not r.get("leesbaar") or not r.get("factcheck"):
            continue
        for m in sorted(m4fc_methoden(r["m4fc"])):
            naam = METHODEN[m]
            uit[naam]["mensen"] += 1
            uit[naam]["haiku ook"] += naam in r["methoden"]
    return dict(uit)


def kaart(gelezen: list[dict]) -> dict:
    """Hoe vaak elke vorm, truc en methode voorkomt, ook per taal en periode; alleen echte factchecks."""
    echt = [r for r in gelezen if r.get("leesbaar") and r.get("factcheck")]
    uit = {"artikelen": len(echt), "vorm": collections.Counter(), "truc": collections.Counter(),
           "methode": collections.Counter(), "nagedaan": collections.Counter(), "onderwerp": collections.Counter(),
           "per laag": collections.defaultdict(lambda: {"artikelen": 0, "vorm": collections.Counter(),
                                                         "truc": collections.Counter(),
                                                         "methode": collections.Counter()})}
    for r in echt:
        laag = uit["per laag"]["/".join(r["laag"])]
        laag["artikelen"] += 1
        for veld in ("vorm", "truc"):
            uit[veld][r[veld]] += 1
            laag[veld][r[veld]] += 1
        for m in r["methoden"]:
            uit["methode"][m] += 1
            laag["methode"][m] += 1
        for veld in ("nagedaan", "onderwerp"):
            if r.get(veld):
                uit[veld][r[veld]] += 1
    uit["per laag"] = dict(uit["per laag"])
    return uit


# --- de bestanden en het netwerk ---------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad)


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _dood() -> tuple[set[str], frozenset[str]]:  # pragma: no cover - op de bestanden
    """De adressen die al een 403, 404 of 410 gaven (de beeldoogst) of dood zijn (de bonnetjes), en de hosts die bij de
    beeldoogst bijna nooit iets gaven (minstens 20 keer gevraagd, minder dan 10% een 200)."""
    import sqlite3

    dood, per_host = set(), collections.defaultdict(collections.Counter)
    for r in _jsonl(WORTEL / "data" / "beeldoogst" / "artikelen.jsonl"):
        per_host[r["host"]][r["status"] == 200] += 1
        if r["status"] in (403, 404, 410):
            dood.add(r["url"])
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    dood |= {u for (u,) in conn.execute("SELECT url FROM linkstatus WHERE uitkomst = 'dood'")}
    hosts = frozenset(h.removeprefix("www.") for h, c in per_host.items()
                      if sum(c.values()) >= 20 and c[True] * 10 < sum(c.values()))
    return dood, hosts


def _set() -> None:  # pragma: no cover - op de database
    import sqlite3

    if (UIT / "set.jsonl").exists():
        raise Weigering("de set ligt al vast")
    m4fc = m4fc_steekproef(json.loads(M4FC.read_text(encoding="utf-8")))
    dood, hosts = _dood()
    dood |= {r["url"] for r in m4fc}
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    rijen = [{"url": u, "publisher": p, "language": t, "jaar": int(d[:4] or 0), "oordeel": o, "claim": c}
             for u, p, t, d, o, c in conn.execute(
                 "SELECT f.url, f.publisher, f.language, f.review_date, f.verdict_normalized, c.canonical_text "
                 "FROM factcheck f JOIN claim c USING (claim_id) WHERE f.url LIKE 'http%'")]
    db = steekproef(rijen, dood, dode_hosts=hosts)
    _schrijf(UIT / "set.jsonl", db + m4fc)
    lagen = collections.Counter("/".join(r["laag"]) for r in db + m4fc)
    print(f"{len(db)} kandidaten uit de database en {len(m4fc)} uit M4FC; {len(hosts)} hosts overgeslagen")
    for laag, n in sorted(lagen.items()):
        print(f"  {laag:14} {n}")


def _ophalen() -> None:  # pragma: no cover - netwerk
    """Elk artikel van de set, per host één verzoek tegelijk met robots.txt; hervatbaar. Weert een host ons drie keer
    op rij, dan slaan we de rest van die host over."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import httpx

    from doublecheck.beeldindexmeting import Beleefd
    from doublecheck.screeningmeting import alineatekst
    from doublecheck.sheffield import lees

    klaar = {r["id"] for r in _jsonl(UIT / "ophaal.jsonl")}
    per_host = collections.defaultdict(list)
    for r in _jsonl(UIT / "set.jsonl"):
        if r["id"] not in klaar:
            per_host[_host(r["url"])].append(r)
    beleefd = Beleefd()
    beleefd.web = httpx.Client(headers=KOP, follow_redirects=True, timeout=30)
    slot, teller = threading.Lock(), collections.Counter()

    def host_werk(lijst):
        geweerd = 0
        for r in lijst:
            titel, tekst = "", ""
            if geweerd >= 3:
                status = "host weert"
            elif not beleefd.mag(r["url"]):
                status = "robots"
            else:
                a = beleefd._vraag(r["url"])
                status = a.status_code if a is not None else "fout"
                geweerd = geweerd + 1 if status in (401, 403, 429) else 0
                if status == 200 and "html" in a.headers.get("content-type", ""):
                    titel = lees(a.text)[0]
                    tekst = alineatekst(a.text)[:MAX_TEKENS]
            with slot:
                _schrijf(UIT / "ophaal.jsonl", [{"id": r["id"], "status": status, "tekens": len(tekst)}])
                if len(tekst) >= MIN_TEKST:
                    _schrijf(UIT / "teksten.jsonl", [{"id": r["id"], "titel": titel, "tekst": tekst}])
                    teller["leesbaar"] += 1
                teller["klaar"] += 1
                if teller["klaar"] % 200 == 0:
                    print(f"{teller['klaar']} gevraagd, {teller['leesbaar']} leesbaar", flush=True)

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(host_werk, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {teller['klaar']} gevraagd, {teller['leesbaar']} leesbaar")


def _uitgegeven() -> float:  # pragma: no cover - een bestand
    return sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"]
               for b in _jsonl(UIT / "batches.jsonl"))


def _indienen(proef: int | None) -> None:  # pragma: no cover - netwerk
    import anthropic

    from doublecheck.varianten import laad_sleutel

    teksten = {r["id"]: r for r in _jsonl(UIT / "teksten.jsonl")}
    gevraagd = {r["id"] for r in _jsonl(UIT / "kaart.jsonl")}
    werk = [r for r in kies_leesbaar(_jsonl(UIT / "set.jsonl"), set(teksten)) if r["id"] not in gevraagd]
    werk = werk[:proef] if proef else werk
    if not werk:
        print("niets te vragen")
        return
    binnen_grens(SCHATTING * len(werk), _uitgegeven())
    laad_sleutel()
    batch = anthropic.Anthropic().messages.batches.create(
        requests=[{"custom_id": f"ww-{r['id']}", "params": verzoek(r, teksten[r["id"]])} for r in werk])
    _schrijf(UIT / "kaart.jsonl", [{"custom_id": f"ww-{r['id']}", "id": r["id"], "batch": batch.id} for r in werk])
    _schrijf(UIT / "batches.jsonl", [{"id": batch.id, "aantal": len(werk), "schatting": SCHATTING * len(werk)}])
    print(f"batch {batch.id}: {len(werk)} artikelen, schatting ${SCHATTING * len(werk):.3f}; samen "
          f"${_uitgegeven():.2f} van ${BUDGET:.2f}")


def _antwoorden() -> None:  # pragma: no cover - netwerk
    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart_ = {r["custom_id"]: r for r in _jsonl(UIT / "kaart.jsonl")}
    alle = _jsonl(UIT / "batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog")
            continue
        werkelijk, mis, regels_ = 0.0, 0, []
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded" or r.custom_id not in kaart_:
                mis += 1
                continue
            werkelijk += kosten_batch(bc.gebruik_uit(r.result.message), "haiku")
            regels_.append({"id": kaart_[r.custom_id]["id"], "versie": VERSIE,
                            "antwoord": "".join(getattr(x, "text", "") or "" for x in r.result.message.content)})
        _schrijf(UIT / "antwoorden.jsonl", regels_)
        b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
        print(f"batch {b['id']}: ${werkelijk:.3f}, {mis} mislukt")
    (UIT / "batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(f"samen ${_uitgegeven():.2f} van ${BUDGET:.2f}")


def _gelezen() -> list[dict]:  # pragma: no cover - op de bestanden
    teksten = {r["id"]: r for r in _jsonl(UIT / "teksten.jsonl")}
    sets = {r["id"]: r for r in _jsonl(UIT / "set.jsonl")}
    uit = []
    for a in _jsonl(UIT / "antwoorden.jsonl"):
        s = sets[a["id"]]
        tekst = teksten.get(a["id"], {}).get("tekst", "")
        uit.append({"id": a["id"], "url": s["url"], "publisher": s["publisher"], "laag": s["laag"],
                    "m4fc": s.get("m4fc"), **lees_antwoord(a["antwoord"], tekst)})
    return uit


def _nakijk_ids(gelezen: list[dict]) -> list[str]:
    echt = sorted(r["id"] for r in gelezen if r.get("leesbaar") and r.get("factcheck"))
    return sorted(random.Random(ZAAD + 1).sample(echt, min(N_NAKIJKEN, len(echt))))


def _lezen() -> None:  # pragma: no cover - op de bestanden
    gelezen = _gelezen()
    (UIT / "gelezen.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in gelezen),
                                       encoding="utf-8")
    teller = collections.Counter("onleesbaar" if not r["leesbaar"] else "factcheck" if r["factcheck"]
                                 else "geen factcheck" for r in gelezen)
    print(dict(teller), "| methoden zonder letterlijk citaat:",
          sum(len(r.get("niet gevonden") or []) for r in gelezen))
    if not LABELS.exists():
        LABELS.write_text(json.dumps({
            "toelichting": "PLAN #32.39: per nagekeken artikel of de vorm, de truc en de methoden van Haiku kloppen "
                           "met het artikel (goed of fout). 'claude' zijn de 100 van Claude, 'po' de 50 van de PO.",
            "claude": {}, "po": {}}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in [g for g in gelezen if g["id"] in set(_nakijk_ids(gelezen))][:10]:
        print(f"- {r['id']} {r['url']}\n  {r['vorm']} | {r['truc']} | {r['nagedaan']} {r['wie']} | {r['methoden']}"
              f"\n  {r['verhaal']}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    gelezen = _jsonl(UIT / "gelezen.jsonl")
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    nakijken = telling_nakijken(gelezen, labels["claude"], _nakijk_ids(gelezen))
    uit = {"versie": VERSIE, "nakijken": nakijken, "m4fc": m4fc_overeenkomst(gelezen), "kaart": kaart(gelezen),
           "kosten": round(_uitgegeven(), 4)}
    (UIT / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: uit[k] for k in ("nakijken", "m4fc", "kosten")}, ensure_ascii=False, indent=1))
    k = uit["kaart"]
    print(f"{k['artikelen']} factchecks")
    for veld in ("vorm", "truc", "methode", "nagedaan"):
        print(veld, k[veld].most_common())


def _opruimen() -> None:  # pragma: no cover - een bestand
    pad = UIT / "teksten.jsonl"
    if pad.exists():
        pad.unlink()
        print("de teksten van de artikelen zijn weg")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Wat de factchecks ons leren (PLAN #32.39)")
    parser.add_argument("stap", choices=("set", "ophalen", "indienen", "antwoorden", "lezen", "tellen", "opruimen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    {"set": _set, "ophalen": _ophalen, "indienen": lambda: _indienen(args.proef), "antwoorden": _antwoorden,
     "lezen": _lezen, "tellen": _tellen, "opruimen": _opruimen}[args.stap]()


if __name__ == "__main__":
    main()
