"""Een steekproef voor de PO om op het oog na te kijken (PO 2026-11-07: "zo af en toe een random selectie met 25 checks
... Engelse taal en dingen die rondgaan in westerse media ... wat jouw oordeel is met label en kleur").

De kaartenbak is een meting die al gedraaid is, als op de eerste dag: alleen Engelse berichten uit westerse media,
nepnieuws dat een westerse factchecker onderzocht (`WESTERSE_FACTCHECKERS`) en echte koppen van westerse media
(`WESTERSE_MEDIA`). Daaruit een vaste, willekeurige trekking. Per kaart wat Factiz zei (kleur, uitkomst, uitleg,
bronnen) en apart wat de redactie zei, voor na het oordeel van de PO. Kost niets: geen nieuwe vragen.

    python -m doublecheck.poproef trekken --meting 32.43-en [--n 25] [--zaad <ronde>]
    python -m doublecheck.poproef pagina --zaad <ronde>
    python -m doublecheck.poproef berichten --zaad <ronde>   # een ronde zoals het product: eerst nieuwe berichten
    python -m doublecheck.poproef nieuws --zaad <ronde>      # een ronde uit het nieuws zelf: koppen en foto's

Een ronde uit het nieuws zelf (PO 2026-11-07: "echt random nieuwsfeiten, foto's en berichten"; "periodiek ... om de
voortgang te checken"): `nieuws` haalt de feeds van `FEEDS`, trekt 20 koppen en 5 nieuwsfoto's van de afgelopen twee
dagen, elk medium even zwaar, en schrijft het meetplan; dan `meting ... set`, `draaien --proef 1`, `draaien`, `trekken
--meting poproef-<ronde> --zaad <ronde> --titel <tekst>` en `pagina`. De foto's gaan alleen in het geheugen naar het
model; op de pagina staat een link.

Een ronde zoals het product (PO 2026-11-07: "dat is inderdaad wat ik wil testen met de kaartenbak"): `berichten` kiest
westerse berichten die de PO nog niet zag, een meetplan zonder *eerste dag* draait ze door `/check` zoals het product
(kring 1, de database, de factchecksites), en `trekken` maakt er de kaarten van.

`pagina` vult `poproef_pagina.html` met de kaarten van die ronde in `data/poproef/kaartenbak.html`, de pagina voor de
PO; de keuzes van de PO staan in de database van die pagina, per ronde (`rondes/<ronde>/keuzes/<kaart>`).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "poproef"
WESTERSE_FACTCHECKERS = frozenset({"Snopes", "Full Fact", "PolitiFact", "FactCheck.org", "Lead Stories", "Reuters",
                                   "AFP", "USA Today", "Check Your Fact", "AAP FactCheck", "Deutsche Welle",
                                   "The Journal", "Science Feedback", "Health Feedback"})
WESTERSE_MEDIA = frozenset({"BBC News", "The Guardian", "NPR", "DW", "France 24", "Euronews"})
# Een ronde uit het nieuws zelf (PO 2026-11-07: "echt random nieuwsfeiten, foto's en berichten"; "ik wil periodiek even
# zo'n test doen om de voortgang te checken"): Engelstalige media uit het hele spectrum, vastgelegd vóór de eerste ronde.
FEEDS = {
    "BBC News": "https://feeds.bbci.co.uk/news/rss.xml",
    "The Guardian": "https://www.theguardian.com/uk/rss",
    "Sky News": "https://feeds.skynews.com/feeds/rss/home.xml",
    "The Independent": "https://www.independent.co.uk/news/rss",
    "Daily Mail": "https://www.dailymail.co.uk/news/index.rss",
    "The Sun": "https://www.thesun.co.uk/feed/",
    "Daily Mirror": "https://www.mirror.co.uk/?service=rss",
    "Daily Express": "https://www.express.co.uk/posts/rss/1/news",
    "GB News": "https://www.gbnews.com/feeds/news.rss",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "CNN": "http://rss.cnn.com/rss/edition.rss",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/news",
    "Fox News": "https://moxie.foxnews.com/google-publisher/latest.xml",
    "New York Post": "https://nypost.com/feed/",
    "The Hill": "https://thehill.com/feed/",
    "HuffPost": "https://www.huffpost.com/section/front-page/feed",
    "Breitbart": "https://feeds.feedburner.com/breitbart",
    "Newsmax": "https://www.newsmax.com/rss/Newsfront/16/",
    "Euronews": "https://www.euronews.com/rss",
    "DW": "https://rss.dw.com/rdf/rss-en-all",
    "France 24": "https://www.france24.com/en/rss",
    "Politico Europe": "https://www.politico.eu/feed/",
}
N_KOPPEN, N_FOTOS, DAGEN = 20, 5, 2
# Wie we zijn, zonder te doen alsof we een browser zijn; een site die dit weigert, valt weg en wordt gemeld
AGENT = {"User-Agent": "FactizResearch/1.0 (https://factiz.org; kaartenbak, leest RSS en een foto, PLAN #32.45)"}


def westers(item: dict) -> bool:
    """Nepnieuws van een westerse factchecker (set O), een echte kop van westerse media (set W-merk), of een kop of foto
    uit de feeds van een nieuwsronde (K en F). Oud nieuws van Wikinews (W) blijft erbuiten: dat gaat nu niet rond."""
    return ((item["set"] == "O" and item.get("publisher") in WESTERSE_FACTCHECKERS)
            or (item["set"] == "W-merk" and item.get("merk") in WESTERSE_MEDIA) or item["set"] in ("K", "F"))


def uit_feed(xml: bytes, merk: str) -> list[dict]:
    """De berichten uit één RSS- of Atom-feed: kop, adres van het artikel, datum, en de foto als die erbij staat
    (`media:content`, `media:thumbnail` of een `enclosure` van het type image)."""
    import email.utils
    import xml.etree.ElementTree as ET

    uit = []
    for item in ET.fromstring(xml).iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        velden, foto, link = {}, None, None
        for k in item:
            naam = k.tag.split("}")[-1]
            velden[naam] = (k.text or "").strip()
            if naam in ("content", "thumbnail") and k.get("url") and foto is None and k.get("medium", "image") == "image":
                foto = k.get("url")
            if naam == "enclosure" and (k.get("type") or "").startswith("image") and foto is None:
                foto = k.get("url")
            if naam == "link" and k.get("href") and link is None:
                link = k.get("href")
        ruwe = velden.get("pubDate") or velden.get("date") or velden.get("updated") or velden.get("published") or ""
        try:
            datum = email.utils.parsedate_to_datetime(ruwe).date().isoformat()
        except (TypeError, ValueError):
            datum = ruwe[:10]
        titel = " ".join(velden.get("title", "").split())
        if titel:
            uit.append({"merk": merk, "titel": titel, "url": velden.get("link") or link, "datum": datum, "foto": foto})
    return uit


def _om_de_beurt(rng: random.Random, per_merk: dict[str, list[dict]], n: int) -> list[dict]:
    """`n` berichten, elk medium om de beurt in een willekeurige volgorde, binnen een medium een willekeurig bericht:
    elk medium weegt even zwaar, hoeveel koppen het ook heeft."""
    merken = sorted(per_merk)
    rng.shuffle(merken)
    uit = []
    while len(uit) < n and any(per_merk[m] for m in merken):
        for m in merken:
            if per_merk[m] and len(uit) < n:
                uit.append(per_merk[m].pop(rng.randrange(len(per_merk[m]))))
    return uit


def nieuwsronde(items: list[dict], n_koppen: int = N_KOPPEN, n_fotos: int = N_FOTOS, zaad: str = "") -> list[dict]:
    """Een ronde uit het nieuws zelf: `n_fotos` nieuwsfoto's met hun bijschrift (set F, het beeld gaat mee) en `n_koppen`
    koppen (set K), de helft met de naam van het medium erboven en de helft als kale tekst, zoals mensen het doorsturen.
    Niemand weet vooraf of het klopt. Vast zaad; de volgorde van de invoer telt niet."""
    import hashlib

    rng = random.Random(zaad)
    alle = sorted(items, key=lambda i: (i["merk"], i["url"] or "", i["titel"]))
    met_foto: dict[str, list[dict]] = {}
    for i in alle:
        if i.get("foto"):
            met_foto.setdefault(i["merk"], []).append(i)
    fotos = _om_de_beurt(rng, met_foto, n_fotos)
    gekozen = {id(i) for i in fotos}
    rest: dict[str, list[dict]] = {}
    for i in alle:
        if id(i) not in gekozen:
            rest.setdefault(i["merk"], []).append(i)
    koppen = _om_de_beurt(rng, rest, n_koppen)
    met_naam = set(rng.sample(range(len(koppen)), len(koppen) // 2))

    def bericht(i: dict, set_: str, tekst: str) -> dict:
        sleutel = hashlib.sha1(f"{i['merk']}|{i['titel']}".encode()).hexdigest()[:12]
        uit = {"id": f"{set_}:{sleutel}", "set": set_, "tekst": tekst, "titel": i["titel"], "merk": i["merk"],
               "datum": i["datum"], "url": i["url"]}
        return {**uit, "beeld": i["foto"]} if set_ == "F" else uit

    return ([bericht(i, "F", i["titel"]) for i in fotos]
            + [bericht(i, "K", f"{i['merk']}\n{i['titel']}" if n in met_naam else i["titel"])
               for n, i in enumerate(koppen)])


def voorraad(rijen: list[dict], items: dict[str, dict]) -> list[dict]:
    """De antwoorden over Engelse berichten uit westerse media (`westers`)."""
    return [r for r in rijen if westers({**items[r["id"]], "set": r["set"]})]


def nieuwe_berichten(items: list[dict], gezien: set[str], n: int = 25, zaad: str = "") -> list[dict]:
    """Voor een ronde zoals het product: `n` westerse berichten die de PO nog niet zag, vast en willekeurig; ze gaan
    daarna door een meetplan zonder *eerste dag* (met kring 1, de database en de factchecksites)."""
    alle = sorted((i for i in items if westers(i) and i["id"] not in gezien), key=lambda i: i["id"])
    return sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda i: i["id"])


def _kaart(r: dict, item: dict, urls: dict[str, str], is_factcheck=None) -> dict:
    if r["set"] in ("K", "F"):
        factcheck = r.get("route") == "database" or any(
            b.get("redactie") or (is_factcheck is not None and is_factcheck(b.get("url") or "")) for b in r["bronnen"])
        onthulling = {"soort": "nieuws", "door": item["merk"], "oordeel": None, "datum": item.get("datum"),
                      "url": item.get("url"), "factcheck": factcheck}
    elif r["set"] == "O":
        onthulling = {"soort": "factcheck", "door": item["publisher"], "oordeel": item.get("oordeel"),
                      "datum": item.get("datum"), "url": urls.get(r["id"])}
    else:
        onthulling = {"soort": "echte kop", "door": item["merk"], "oordeel": "waar", "datum": item.get("datum"),
                      "url": None}
    return {"id": r["id"], "bericht": item["tekst"], "kleur": r["kleur"], "uitkomst": r["uitkomst"],
            "uitleg": r.get("uitleg"), "route": r.get("route", "zoeken"),
            "bronnen": [{"site": b.get("site") or b.get("redactie"), "titel": b.get("titel") or (
                f"Check van {b['redactie']}: {b.get('oordeel')}" if b.get("redactie") else None), "url": b["url"],
                         "rol": b.get("rol") or ("check in de database" if b.get("redactie") else None),
                         "band": b.get("band")} for b in r["bronnen"] if b.get("url")],
            "foto": item.get("beeld") if r["set"] == "F" else None, "onthulling": onthulling}


def trek(rijen: list[dict], items: dict[str, dict], n: int = 25, zaad: str = "", urls: dict[str, str] | None = None,
         is_factcheck=None) -> list[dict]:
    """Een vaste, willekeurige trekking van `n` kaarten uit de voorraad; de volgorde van de invoer telt niet.
    `is_factcheck(url)`: of een bron een factcheck is, voor de kaart van een nieuwsronde."""
    alle = sorted(voorraad(rijen, items), key=lambda r: r["id"])
    gekozen = random.Random(zaad).sample(alle, min(n, len(alle)))
    return [_kaart(r, items[r["id"]], urls or {}, is_factcheck) for r in gekozen]


def vul(sjabloon: str, data: dict) -> str:
    """De pagina met de kaarten erin, als JSON in een scripttag; een `</` in een bericht kan die tag nooit sluiten."""
    return sjabloon.replace("/*KAARTEN*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def _feeds_ophalen() -> tuple[list[dict], list[str]]:  # pragma: no cover - het netwerk
    """Alle berichten uit `FEEDS`, één verzoek per feed, met robots.txt; welke media antwoordden."""
    import urllib.robotparser
    from urllib.parse import urlsplit

    import httpx

    items, media = [], []
    with httpx.Client(headers=AGENT, follow_redirects=True, timeout=30) as web:
        for merk, url in FEEDS.items():
            try:
                robots = urllib.robotparser.RobotFileParser()
                r = web.get(f"https://{urlsplit(url).hostname}/robots.txt")
                robots.parse(r.text.splitlines() if r.status_code == 200 else [])
                if not robots.can_fetch("FactizResearch", url):
                    print(f"{merk}: robots.txt staat het niet toe")
                    continue
                nieuw = uit_feed(web.get(url).content, merk)
            except Exception as fout:  # noqa: BLE001 - een feed die niet antwoordt, valt weg en wordt gemeld
                print(f"{merk}: {type(fout).__name__}")
                continue
            print(f"{merk}: {len(nieuw)} berichten, {sum(bool(i['foto']) for i in nieuw)} met een foto")
            items += nieuw
            media.append(merk)
    return items, media


def _nieuws(zaad: str) -> None:  # pragma: no cover - het netwerk en de bestanden
    """De berichten van een nieuwsronde en haar meetplan zoals het product (de lezer uit config, geen *eerste dag*)."""
    import datetime

    from doublecheck.config import load_config

    items, media = _feeds_ophalen()
    sinds = (datetime.date.today() - datetime.timedelta(days=DAGEN)).isoformat()
    vers = [i for i in items if (i["datum"] or "") >= sinds]
    ronde = nieuwsronde(vers, N_KOPPEN, N_FOTOS, zaad)
    UIT.mkdir(parents=True, exist_ok=True)
    bron = UIT / f"{zaad}-berichten.jsonl"
    bron.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in ronde), encoding="utf-8")
    (UIT / f"{zaad}-voorraad.json").write_text(json.dumps({"items": len(vers), "media": media}, ensure_ascii=False),
                                               encoding="utf-8")
    c = load_config(None).berichtcontrole
    plan = {"taak": f"poproef-{zaad}",
            "toelichting": (f"Een ronde van de kaartenbak uit het nieuws zelf (PLAN #32.45, PO 2026-11-07): {N_KOPPEN} "
                            f"koppen en {N_FOTOS} nieuwsfoto's van de afgelopen {DAGEN} dagen, willekeurig uit {len(vers)} "
                            f"berichten van {len(media)} media (`poproef.FEEDS`). Zoals het product: kring 1, de database, "
                            "de factchecksites en de lezer uit config. Geen eisen: de keuzes van de PO zijn de labels."),
            "map": f"data/meting/poproef-{zaad}", "labels": f"docs/steekproeven/poproef-{zaad}-meting.json",
            "budget": 1.5, "zaad": 3252,
            "sets": {"K": {"bron": str(bron.relative_to(WORTEL)), "set": "K"},
                     "F": {"bron": str(bron.relative_to(WORTEL)), "set": "F", "beeld": True}},
            "armen": {"C": {"lezer": c.lezer, "speurvraag_model": c.speurvraag_model}},
            "onwaar": [], "waar": [], "eisen": [], "zoekvragen_max": 5 * (N_KOPPEN + N_FOTOS)}
    pad = WORTEL / "docs" / "meetplannen" / f"poproef-{zaad}.json"
    pad.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(ronde)} berichten uit {len(vers)} van {len(media)} media in {bron.name}; meetplan {pad.name}")


def _urls(items: dict[str, dict]) -> dict[str, str]:  # pragma: no cover - op de database
    """Per bericht van set O het adres van de factcheck zelf, uit de database."""
    import sqlite3

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    uit = {}
    for i, item in items.items():
        if item.get("claim_id"):
            rij = conn.execute("SELECT url FROM factcheck WHERE claim_id = ? AND publisher = ? ORDER BY review_date DESC",
                               (item["claim_id"], item.get("publisher"))).fetchone()
            if rij:
                uit[i] = rij[0]
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import datetime

    from doublecheck import meting as mt

    parser = argparse.ArgumentParser(description="Een steekproef voor de PO")
    parser.add_argument("stap", choices=("nieuws", "berichten", "trekken", "pagina"))
    parser.add_argument("--meting")
    parser.add_argument("--bron", default="data/talen/vers/en.jsonl")
    parser.add_argument("--titel")
    parser.add_argument("--voorraad", type=int, help="bij een ronde zoals het product: waaruit `berichten` trok")
    parser.add_argument("--n", type=int, default=25)
    parser.add_argument("--zaad", default=datetime.date.today().isoformat())
    args = parser.parse_args()
    if args.stap == "pagina":
        data = json.loads((UIT / f"{args.zaad}.json").read_text(encoding="utf-8"))
        sjabloon = (Path(__file__).parent / "poproef_pagina.html").read_text(encoding="utf-8")
        (UIT / "kaartenbak.html").write_text(vul(sjabloon, data), encoding="utf-8")
        print(UIT / "kaartenbak.html")
        return
    if args.stap == "nieuws":
        _nieuws(args.zaad)
        return
    if args.stap == "berichten":
        gezien = {k["id"] for p in UIT.glob("*.json") for k in json.loads(p.read_text(encoding="utf-8"))["kaarten"]}
        uit = nieuwe_berichten(mt._jsonl(WORTEL / args.bron), gezien, args.n, args.zaad)
        doel = UIT / f"{args.zaad}-berichten.jsonl"
        doel.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in uit), encoding="utf-8")
        print(f"{len(uit)} berichten uit {sum(westers(i) and i['id'] not in gezien for i in mt._jsonl(WORTEL / args.bron))}"
              f" westerse die de PO nog niet zag, in {doel}")
        return
    plan = mt.lees_plan(f"docs/meetplannen/{args.meting}.json")
    rijen = mt._jsonl(plan["_map"] / "antwoorden.jsonl")
    items = {s["id"]: s for s in mt._jsonl(WORTEL / next(iter(plan["sets"].values()))["bron"])}
    nieuws = "K" in plan["sets"]
    is_factcheck = None
    if nieuws:
        from doublecheck import berichtcontrole as bc
        from doublecheck.speuren import eerste_dag_domeinen, van_factchecker

        hosts = eerste_dag_domeinen(bc.herkomstlijst()["sites"])
        is_factcheck = lambda u: van_factchecker(u, hosts)  # noqa: E731
    kaarten = trek(rijen, items, args.n, args.zaad, _urls(items), is_factcheck)
    sidecar = UIT / f"{args.zaad}-voorraad.json"
    extra = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    UIT.mkdir(parents=True, exist_ok=True)
    doel = UIT / f"{args.zaad}.json"
    modus = "eerste dag" if any(s.get("eerste_dag") for s in plan["sets"].values()) else "product"
    doel.write_text(json.dumps({"ronde": args.zaad, "titel": args.titel, "modus": modus, "meting": args.meting,
                                "soort": "nieuws" if nieuws else "meetsets", "media": extra.get("media"),
                                "lezer": plan["armen"]["C"]["lezer"],
                                "voorraad": args.voorraad or extra.get("items") or len(voorraad(rijen, items)),
                                "kaarten": kaarten}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(kaarten)} kaarten uit {len(voorraad(rijen, items))} in {doel}")


if __name__ == "__main__":
    main()
