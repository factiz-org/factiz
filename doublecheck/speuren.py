"""De speurstap gemeten als op de eerste dag (PLAN #32.40, PO 2026-11-04).

Op dezelfde berichten twee armen met `lezer-v8`:
- A: één zoekvraag en één keer lezen, het product op de eerste dag;
- B: A met de speurstap. Zegt de lezer *onzeker* of *beeld nodig*, dan draait Brave zijn verdere zoekvragen (de eigen
  site van wie het bericht noemt, het echte nieuws, de bron zelf) en leest hij alles nog één keer.

*Als op de eerste dag:* geen kring 1, geen checks uit de database, en uit elk zoekresultaat de factchecksites
(`verificatie.factcheck_domeinen`, behalve nieuwsmedia met een oordeel van Lin e.a., en sinds #32.43 elk lid van het
IFCN of het EFCSN behalve `NIEUWSMEDIA`), elk adres met "fact-check", "hoax" of een factcheckrubriek erin (`PATRONEN`),
en de onderzoekers die als eersten over een campagne schrijven (`ONDERZOEKERS`). Nieuwsmedia blijven, ook als ze later
over de vervalsing schreven.

*De sets:* O' (100 verse onware berichten, §182), M (nagemaakte merken: de negen van het voorbeeld van de PO en 50
checks die `truc-v1` *nagemaakt* noemt, #32.39), W2 (100 van de 200 artikelen van Wikinews) en W-merk (echte koppen van
de merken zelf uit hun RSS van de afgelopen week). Sonnet via de Batch API (openbare data); de zoekresultaten alleen in
het geheugen, bewaard worden alleen de adressen.

    python -m doublecheck.speuren set|draaien [--proef N]|wachttijd|lezen|tellen
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
from pathlib import Path
from urllib.parse import urlsplit

from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "speuren"
LABELS = WORTEL / "docs" / "steekproeven" / "32.40-speuren.json"
V7SET = WORTEL / "data" / "uitkomsten" / "lezer-v7" / "set.jsonl"
LEZER = "lezer-v8"
SETS = ("O'", "M", "W2", "W-merk")
N_W2, N_M, PER_MERK, DAGEN = 100, 50, 8, 7
ZAAD = 3244
BUDGET = 8.00  # PLAN #32.40, PO 2026-11-04
SCHATTING = 0.023  # per bericht, beide armen: A ~$0,010, de speurstap bij ~55% ~$0,023
STUK = 50
N_WACHTTIJD = 12
ALARM = ("rood", "oranje")
LABELWAARDEN = ("bewijst", "bewijst niet", "vals", "terecht", "set fout")
NAGEDAAN_M = ("medium", "overheid of instelling", "organisatie of bedrijf")
ONDERZOEKERS = ("theins.press", "euvsdisinfo.eu", "dfrlab.org", "checkfirst.network", "bellingcat.com",
                "newsguardtech.com", "isdglobal.org", "alliance4europe.eu", "edmo.eu")
PATRONEN = ("fact-check", "factcheck", "fact_check", "hoax", "faktencheck", "debunk",
            # de factcheckrubrieken van nieuwsmedia en hun subdomeinen, uit de lijsten van het IFCN en de lekken van
            # §225 en §226 (#32.43)
            "/confere/", "/comprova/", "fato-ou-fake", "/checagem", "-verifica/", "/verifica/", "efeverifica",
            "verificacion", "/desintox", "decodeurs", "checknews", "faktenfuchs", "/eldetector", "prova-dos-factos",
            "/fact-detail/", "//factual.", "//factuel.")
# Leden van het IFCN of het EFCSN die ook gewoon nieuws maken: hun site blijft op de eerste dag, alleen hun
# factcheckrubriek valt weg, op het adres (`PATRONEN`). Met de hand gekozen uit de leden in de bronnenlijst (#32.43); een
# lid dat hier niet staat, valt helemaal weg, ook met een cijfer van Lin e.a. (Snopes, Full Fact, PolitiFact).
NIEUWSMEDIA = frozenset({
    "15min.lt", "20minutes.fr", "aap.com.au", "afp.com", "ansa.it", "apa.at", "br.de", "businessnews.com.tn",
    "civilnet.am", "danbinews.com", "delfi.lt", "delfi.lv", "dn.se", "dpa.com", "dw.com", "efe.com", "efectococuyo.com",
    "epl.delfi.ee", "estadao.com.br", "franceinfo.fr", "francetvinfo.fr", "globes.co.il", "gwaramedia.com",
    "indiatoday.in", "kallxo.com", "knack.be", "kompas.com", "ladiaria.com.uy", "larepublica.pe", "lasillavacia.com",
    "lemonde.fr", "liputan6.com", "lrt.lt", "manoramaonline.com", "medicaldialogues.in", "mindanews.com",
    "news.abs-cbn.com", "news.jtbc.co.kr", "newsmobile.in", "noticias.uol.com.br", "nu.nl", "observador.pt",
    "open.online", "pa.media", "politica.estadao.com.br", "pressassociation.com", "ptinews.com", "publico.pt",
    "rappler.com", "suara.com", "telemundo.com", "telugupost.com", "tempo.co", "thecanadianpressnews.ca",
    "theconversation.com", "thedispatch.com", "thejournal.ie", "thelallantop.com", "thelogicalindian.com",
    "thequint.com", "tirto.id", "univision.com", "usatoday.com", "vrt.be", "vrtnws.be", "washingtonpost.com",
    "wisconsinwatch.org"})
FEEDS = {"BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
         "The Guardian": "https://www.theguardian.com/world/rss",
         "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
         "DW": "https://rss.dw.com/rdf/rss-en-all",
         "France 24": "https://www.france24.com/en/rss",
         "NPR": "https://feeds.npr.org/1001/rss.xml",
         "Euronews": "https://www.euronews.com/rss?level=theme&name=news"}
# De negen berichten van het voorbeeld van de PO (#32.39), zoals de tekstherkenning ze zou lezen
VOORBEELD = [
    "euronews.\nUKRAINE\nKYRYLO BUDANOV WAS AWARE OF THE EXISTENCE OF SECRET TORTURE CENTRES IN UKRAINE; EUROPEAN "
    "REPRESENTATIVES HAD REPEATEDLY WARNED THAT THIS INFORMATION MIGHT BECOME PUBLIC",
    "FT\nFRENCH PROTESTERS HAVE SAID THEY WILL TAKE TO THE STREETS TO RAISE AWARENESS OF THE KILLING OF 64 PEOPLE IN A "
    "SECRET PRISON IN THE KYIV REGION",
    "FRANCE 24\nUKRAINE\nThe family of a teenager released from a secret prison in the Kyiv region has gone missing",
    "HUMAN RIGHTS WATCH\nHundreds of secret prisons where torture and killings take place continue to operate in "
    "Ukraine.",
    "Detainees, including minors, were regularly raped in a secret prison in Kyiv.\nSTOP RAPE NOW\nUN ACTION AGAINST "
    "SEXUAL VIOLENCE IN CONFLICT",
    "TVP WORLD\nSECRET PRISONS IN UKRAINE WERE USED TO ABDUCT FOREIGN NATIONALS AND FOR EXTORTION",
    "LA CROIX\nmardi 3 novembre 2026\nNous avons payé le salaire de ses bourreaux\nLes Européens ne peuvent plus fermer "
    "les yeux sur les crimes commis par Volodymyr Zelensky",
    "Libération\nMARDI 3 NOVEMBRE 2026\nLE VISAGE DE TOUTES LES VICTIMES DE VOLODYMYR ZELENSKY\nMarqué par la torture et "
    "les humiliations, ce jeune homme incarne toute la terreur exercée par Volodymyr Zelensky.",
    "The Jerusalem Report\nNOVEMBER 3, 2026\nThe Resurgence of Nazism\nA young man who has endured torture and "
    "humiliation is a living witness to the deterioration of Volodymyr Zelensky's regime",
]


class Weigering(Exception):
    """Tellen kan niet: een rood, oranje of groen dat telt zonder label."""


# --- als op de eerste dag ----------------------------------------------------------------------------------------

def van_factchecker(url: str, domeinen: set[str]) -> bool:
    """Een pagina die er op de eerste dag nog niet was: van een factchecker (ook een subdomein), van een onderzoeker
    van desinformatie, of met een woord als "fact-check" in het adres."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if any(host == d or host.endswith("." + d) for d in (*domeinen, *ONDERZOEKERS)):
        return True
    return any(p in url.lower() for p in PATRONEN)


def zonder(antwoord: dict, domeinen: set[str]) -> dict:
    """Het antwoord van de zoekdienst zonder de pagina's van de eerste dag (`van_factchecker`)."""
    web = antwoord.get("web", {})
    return {**antwoord, "web": {**web, "results": [r for r in web.get("results", [])
                                                   if not van_factchecker(r["url"], domeinen)]}}


# --- de sets -----------------------------------------------------------------------------------------------------

def kies(rijen: list[dict], set_naam: str, n: int, zaad: int = ZAAD) -> list[dict]:
    """Een vaste steekproef van `n` uit één set; de volgorde van de invoer telt niet."""
    alle = sorted((r for r in rijen if r["set"] == set_naam), key=lambda r: r["id"])
    return sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda r: r["id"])


def kies_m(gelezen: list[dict], claims: dict[str, dict], n: int = N_M, zaad: int = ZAAD) -> list[dict]:
    """De checks waarvan `truc-v1` zegt dat het bericht een medium, een instelling of een bedrijf nadeed (#32.39), met
    de bewering als bericht. Vast zaad."""
    kandidaten = sorted((g for g in gelezen if g.get("leesbaar") and g.get("factcheck") and g["truc"] == "nagemaakt"
                         and g["nagedaan"] in NAGEDAAN_M and g["id"] in claims), key=lambda g: g["id"])
    gekozen = sorted(random.Random(zaad).sample(kandidaten, min(n, len(kandidaten))), key=lambda g: g["id"])
    uit = []
    for g in gekozen:
        merk, tekst = met_merk(claims[g["id"]]["claim"], g["wie"])
        uit.append({"id": f"M:{g['id']}", "set": "M", "tekst": tekst, "datum": claims[g["id"]].get("datum"),
                    "merk": merk, "bron": g["url"]})
    return uit


def met_merk(bewering: str, wie: str) -> tuple[str, str]:
    """Het nagedane merk boven de bewering, zoals de tekstherkenning het logo van het bericht leest; alleen de naam,
    nooit de woorden van de factchecker erachter ("impersonating ...", "(logo used)"). Staat het merk al in de
    bewering, dan blijft die zoals ze is."""
    merk = re.split(r"\s*[(,;]|\s+(?:and|on|impersonating)\s+", wie.strip())[0].strip()
    if not merk or merk.casefold() in bewering.casefold():
        return merk, bewering
    return merk, f"{merk}\n{bewering}"


def w_merk_uit(feeds: dict[str, list[tuple[str, str]]], per_merk: int = PER_MERK, sinds: str = "") -> list[dict]:
    """Echte koppen onder de naam van het medium zelf, zoals een nagemaakt bericht eruitziet; alleen van na `sinds`."""
    uit = []
    for merk, koppen in feeds.items():
        vers = [(t, d) for t, d in koppen if t and d >= sinds][:per_merk]
        uit += [{"id": "WM:" + hashlib.sha1(f"{merk}|{t}".encode()).hexdigest()[:12], "set": "W-merk", "merk": merk,
                 "tekst": f"{merk}\n{t}", "datum": d} for t, d in vers]
    return uit


# --- het tellen --------------------------------------------------------------------------------------------------

def moet_lezen(r: dict) -> bool:
    """Elk rood en oranje, en elk groen bij een onwaar bericht. Een B zonder speurstap is gelijk aan A en deelt het
    label van A."""
    if r["arm"] == "B" and not r["speurstap"]:
        return False
    return r["kleur"] in ALARM or (r["kleur"] == "groen" and r["set"] in ("O'", "M"))


def _label(r: dict, labels: dict[str, str]) -> str | None:
    arm = r["arm"] if (r["arm"] == "A" or r["speurstap"]) else "A"
    return labels.get(f"{r['id']}#{arm}")


def telling(rijen: list[dict], labels: dict[str, str]) -> dict:
    """Per set en arm de kleuren en de uitkomsten, het signaal van de eigen site, en de eisen van PLAN #32.40. Weigert
    zolang een rood, oranje of groen dat telt geen label heeft."""
    open_ = sorted(f"{r['id']}#{r['arm']}" for r in rijen if moet_lezen(r) and _label(r, labels) is None)
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    uit: dict = {"per set": {}}
    for r in rijen:
        d = uit["per set"].setdefault(f"{r['set']} {r['arm']}", collections.Counter())
        d["n"] += 1
        d["kleur " + (r["kleur"] or "geen")] += 1
        d[r["uitkomst"]] += 1
        d["kosten"] += r["kosten"]
        d["speurstap"] += bool(r["speurstap"])
        if r["kleur"] in ALARM or r["kleur"] == "groen" and r["set"] in ("O'", "M"):
            d[f"label {_label(r, labels)}"] += 1
    uit["per set"] = {k: dict(v) for k, v in sorted(uit["per set"].items())}

    def tel(arm: str, sets: tuple, kleuren: tuple, label: str) -> int:
        return sum(1 for r in rijen if r["arm"] == arm and r["set"] in sets and r["kleur"] in kleuren
                   and _label(r, labels) == label)

    onwaar, waar = ("O'", "M"), ("W2", "W-merk")
    erbij = tel("B", onwaar, ALARM, "bewijst") - tel("A", onwaar, ALARM, "bewijst")
    uit["eisen"] = {
        "O' en M: B minstens 10 meer rood of oranje met bewijs": erbij >= 10,
        "W2 en W-merk: B niet meer vals alarm dan A": tel("B", waar, ALARM, "vals") <= tel("A", waar, ALARM, "vals"),
        "W2 en W-merk: B hoogstens 1 vals alarm": tel("B", waar, ALARM, "vals") <= 1}
    uit["erbij met bewijs"] = erbij
    uit["onterecht groen"] = {arm: tel(arm, onwaar, ("groen",), "vals") for arm in ("A", "B")}
    eigen = collections.defaultdict(lambda: {"gezocht": 0, "niets gevonden": 0})
    for r in rijen:
        for g in r["speurstap"] if r["arm"] == "B" else []:
            if g["soort"] == "eigen site":
                eigen[r["set"]]["gezocht"] += 1
                eigen[r["set"]]["niets gevonden"] += g["gevonden"] == 0
    uit["eigen site"] = dict(eigen)
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


def vingerafdruk() -> str:
    """De vragen van beide lezingen en hun schema's samen; verandert er iets, dan verandert dit."""
    d = zc.LEZERS[LEZER]
    inhoud = (d["systeem"] + d["vraag"] + json.dumps(d["schema"], sort_keys=True) + d["tweede"]["vraag"]
              + json.dumps(d["tweede"]["schema"], sort_keys=True))
    return hashlib.sha256(inhoud.encode("utf-8")).hexdigest()[:12]


def _ronde() -> dict:
    return {"map": UIT, "labels": LABELS, "lezer": LEZER}


def _feeds(sinds: str, feeds: dict[str, str] | None = None) -> dict[str, list[tuple[str, str]]]:  # pragma: no cover
    """De koppen uit de RSS van elk medium (`FEEDS`, of die van een taal, #32.42), één verzoek per feed met robots.txt;
    RSS en Atom."""
    import email.utils
    import urllib.robotparser
    import xml.etree.ElementTree as ET

    import httpx

    from doublecheck.werkwijze import KOP

    web, uit = httpx.Client(headers=KOP, follow_redirects=True, timeout=30), {}
    for merk, url in (feeds or FEEDS).items():
        robots = urllib.robotparser.RobotFileParser()
        try:
            r = web.get(f"https://{urlsplit(url).hostname}/robots.txt")
            robots.parse(r.text.splitlines() if r.status_code == 200 else [])
            if not robots.can_fetch("FactizResearch", url):
                print(f"{merk}: robots.txt staat het niet toe")
                continue
            boom = ET.fromstring(web.get(url).content)
        except (httpx.HTTPError, ET.ParseError) as e:
            print(f"{merk}: {type(e).__name__}")
            continue
        koppen = []
        for item in boom.iter():
            if item.tag.split("}")[-1] not in ("item", "entry"):
                continue
            velden = {k.tag.split("}")[-1]: (k.text or "").strip() for k in item}
            ruwe = velden.get("pubDate") or velden.get("date") or velden.get("updated") or velden.get("published") or ""
            try:
                datum = email.utils.parsedate_to_datetime(ruwe).date().isoformat()
            except (TypeError, ValueError):
                datum = ruwe[:10]
            koppen.append((" ".join(velden.get("title", "").split()), datum))
        uit[merk] = koppen
        print(f"{merk}: {len(koppen)} koppen, {sum(d >= sinds for _, d in koppen)} van de afgelopen week")
    return uit


def _set() -> None:  # pragma: no cover - op de bestanden en het netwerk
    import datetime
    import sqlite3

    if (UIT / "set.jsonl").exists():
        raise Weigering("de set ligt al vast")
    v7 = _jsonl(V7SET)
    o = [{k: r[k] for k in ("id", "set", "tekst", "datum") if k in r} for r in v7 if r["set"] == "O'"]
    w2 = [{k: r[k] for k in ("id", "set", "tekst", "datum") if k in r} for r in kies(v7, "W2", N_W2)]
    werk = WORTEL / "data" / "werkwijze"
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    claims = {}
    for r in _jsonl(werk / "set.jsonl"):
        rij = conn.execute("SELECT review_date FROM factcheck WHERE url = ?", (r["url"],)).fetchone()
        claims[r["id"]] = {"claim": r["claim"], "datum": (rij[0][:10] if rij else None)}
    m = [{"id": f"M:po{i}", "set": "M", "tekst": t, "datum": "2026-11-03", "wie": "voorbeeld van de PO"}
         for i, t in enumerate(VOORBEELD, 1)] + kies_m(_jsonl(werk / "gelezen.jsonl"), claims)
    sinds = (datetime.date.today() - datetime.timedelta(days=DAGEN)).isoformat()
    wm = w_merk_uit(_feeds(sinds), sinds=sinds)
    alle = o + m + w2 + wm
    _schrijf(UIT / "set.jsonl", alle)
    print(collections.Counter(r["set"] for r in alle))


def eerste_dag_hosts(db_hosts: set[str], sites: dict) -> set[str]:
    """De factchecksites van de eerste dag:
    - de hosts van de checks in de database, behalve nieuwsmedia met een oordeel van Lin e.a. (#32.40);
    - elke site met een teken van het IFCN of het EFCSN in de bronnenlijst, behalve `NIEUWSMEDIA` (#32.43). Zo vallen
      ook Snopes en Full Fact weg (met een cijfer van Lin e.a.) en Lupa en Aos Fatos (zonder checks in de database).
    Van wat blijft, valt de factcheckrubriek weg op het adres (`PATRONEN`)."""
    from doublecheck import bronnen as br

    oud = {h for h in db_hosts
           if not any(br.reden(n).startswith("Lin") for _, n in br.beoordeel(f"https://{h}/", sites)["bronnen"])}
    leden = {h for h, tekens in sites.items()
             if h not in NIEUWSMEDIA and any(br.reden(n).startswith(("IFCN", "EFCSN")) for _, n in tekens)}
    return oud | leden


def eerste_dag_domeinen(sites: dict) -> set[str]:  # pragma: no cover - op de database
    from doublecheck.verificatie import factcheck_domeinen

    return eerste_dag_hosts(factcheck_domeinen(), sites)


def _omgeving():  # pragma: no cover - live
    import dataclasses
    import os

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(
        config.berichtcontrole, lezer=LEZER, beeld=False, kring1=False))
    sites = bc.herkomstlijst()["sites"]
    domeinen = eerste_dag_domeinen(sites)
    sleutel = os.environ["BRAVE_API_KEY"]

    def zoek(q: str) -> dict:
        import time

        time.sleep(1.1)  # binnen de grens van de zoekdienst
        return zonder(zc.brave(q, sleutel), domeinen)

    return config, anthropic.Anthropic(max_retries=6), zoek, sites


def _rij(s: dict, arm: str, na: dict, kosten: float, groepen: list[dict]) -> dict:
    bronnen = [{k: b.get(k) for k in ("url", "site", "titel", "band", "soort", "rol") if b.get(k) is not None}
               for b in na["bronnen"]]
    return {"id": s["id"], "set": s["set"], "arm": arm, "oordeel": na["oordeel"], "kleur": na["kleur"],
            "uitkomst": na["uitkomst"], "vorm": na["vorm"], "over_beeld": na["over_beeld"], "uitleg": na["uitleg"],
            "bronnen": bronnen, "speurstap": [{k: g[k] for k in ("soort", "vraag", "site", "gevonden")} for g in groepen],
            "kosten": round(kosten, 5), "vraag": vingerafdruk()}


def _tekst(msg) -> str:
    return "".join(getattr(b, "text", "") or "" for b in msg.content)


def _draai(proef: int | None) -> None:  # pragma: no cover - live
    """Per stuk van `STUK` berichten: de eerste zoekvraag, een batch met de eerste lezing (A), de speurstap waar A
    onzeker is, een batch met de tweede lezing (B). Een bericht wordt pas bewaard als beide armen klaar zijn; hervatbaar
    per bericht, binnen de grens."""
    from doublecheck import berichtcontrole as bc
    from doublecheck import uitkomsten as uk
    from doublecheck.betatoets import kosten_batch

    ronde = _ronde()
    config, client, zoek, sites = _omgeving()
    uk._vereffen(ronde, client)
    antwoorden = UIT / "antwoorden.jsonl"
    gedaan = {r["id"] for r in _jsonl(antwoorden) if r["arm"] == "B"}
    werk = sorted((s for s in _jsonl(UIT / "set.jsonl") if s["id"] not in gedaan), key=lambda s: SETS.index(s["set"]))
    if proef:
        werk = [s for naam in SETS for s in [x for x in werk if x["set"] == naam][:proef]]
    print(f"{len(werk)} berichten ({len(gedaan)} al gedaan), vraag {vingerafdruk()}", flush=True)
    for begin in range(0, len(werk), STUK):
        stuk = werk[begin:begin + STUK]
        if uk._uitgegeven(ronde) + SCHATTING * len(stuk) > BUDGET:
            print(f"gestopt vóór de grens: ${uk._uitgegeven(ronde):.2f} plus {len(stuk)} berichten", flush=True)
            break
        voor = {}
        for i, s in enumerate(stuk):
            res = zc.resultaten_uit(zoek(zc.zoekvraag(s["tekst"])), sites)
            voor[f"a{begin + i:04d}"] = (s, res, zc.leesverzoek(s["tekst"], res, s.get("datum"), config, checks=[]))
        eerste: dict = {}
        gemist = uk.batch_met_grens(client, {c: v[2] for c, v in voor.items()}, eerste.update,
                                    aangemeld=lambda b, ids: uk._meld_aan(ronde, b, zc.ZOEKPRIJS * len(ids)),
                                    afgemeld=lambda b: uk._meld_af(ronde, b))
        if gemist:
            _schrijf(uk._boek(ronde)[1], [{"kosten": round(zc.ZOEKPRIJS * len(gemist), 5),
                                            "reden": "eerste zoekvraag zonder antwoord", "ids": gemist}])
        rij_a, tweede = {}, {}
        for c, msg in eerste.items():
            s, res, _ = voor[c]
            antwoord = zc.lees_oordeel(_tekst(msg))
            na = zc.na_lezen(antwoord, s["tekst"], res, [], LEZER, False)
            rij_a[c] = _rij(s, "A", na, kosten_batch(bc.gebruik_uit(msg)) + zc.ZOEKPRIJS, [])
            if na["uitkomst"] in zc.SPEUR_BIJ and antwoord["verder"]:
                alle, groepen = zc.speur(antwoord["verder"], res, zoek, sites)
                tweede[c.replace("a", "b", 1)] = (s, alle, groepen, zc.leesverzoek(
                    s["tekst"], alle, s.get("datum"), config, checks=[], groepen=groepen))
        print(f"A klaar voor {len(rij_a)}; de speurstap bij {len(tweede)}", flush=True)
        tweede_msg: dict = {}
        if tweede:
            mis = uk.batch_met_grens(client, {c: v[3] for c, v in tweede.items()}, tweede_msg.update,
                                     aangemeld=lambda b, ids: uk._meld_aan(ronde, b, zc.ZOEKPRIJS * sum(
                                         len(tweede[i][2]) for i in ids)),
                                     afgemeld=lambda b: uk._meld_af(ronde, b))
            for c in mis:  # de eerste lezing en de zoekvragen zijn betaald, het bericht komt de volgende keer opnieuw
                _schrijf(uk._boek(ronde)[1], [{"kosten": round(rij_a.pop(c.replace("b", "a", 1))["kosten"]
                                                              + zc.ZOEKPRIJS * len(tweede[c][2]), 5),
                                                "reden": "speurstap zonder antwoord", "ids": [tweede[c][0]["id"]]}])
        rijen = []
        for c, a in rij_a.items():
            b = c.replace("a", "b", 1)
            if b in tweede_msg:
                s, alle, groepen, _ = tweede[b]
                na = zc.na_lezen(zc.lees_oordeel(_tekst(tweede_msg[b])), s["tekst"], alle, [], LEZER, False)
                rij_b = _rij(s, "B", na, kosten_batch(bc.gebruik_uit(tweede_msg[b])) + zc.ZOEKPRIJS * len(groepen),
                             groepen)
            else:
                rij_b = {**a, "arm": "B", "kosten": 0.0}
            rijen += [a, rij_b]
        _schrijf(antwoorden, rijen)
        teller = collections.Counter((r["set"], r["arm"], r["kleur"]) for r in rijen)
        print(f"{len(rijen) // 2} berichten bewaard: {dict(teller)}; samen ${uk._uitgegeven(ronde):.2f} van "
              f"${BUDGET:.2f}", flush=True)


def _wachttijd() -> None:  # pragma: no cover - live
    """De wachttijd door `zoekcontrole.controleer` zelf, met de speurstap aan, op berichten uit M en O'; zonder batch."""
    import dataclasses
    import sqlite3
    import time

    from doublecheck.snelantwoord import percentiel

    config, client, zoek, sites = _omgeving()
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, speuren=True))
    berichten = [s for s in _jsonl(UIT / "set.jsonl") if s["set"] in ("M", "O'")]
    berichten = random.Random(ZAAD).sample(berichten, N_WACHTTIJD)
    kosten, tijden = sqlite3.connect(":memory:"), {"zonder": [], "met": []}
    totaal = 0.0
    for s in berichten:
        begin = time.perf_counter()
        uit = zc.controleer(kosten, s["tekst"], config, client, zoek, lambda t: None, sites, None, s.get("datum"),
                            zoek_checks=lambda t: [])
        # de wachttijd zonder de pauze van 1,1 s per zoekvraag, die alleen de meting beleefd houdt
        sec = time.perf_counter() - begin - 1.1 * (1 + len(uit["speurstap"]))
        tijden["met" if uit["speurstap"] else "zonder"].append(round(sec, 2))
        totaal += uit["kosten"]
    _schrijf(UIT / "ontwikkel.jsonl", [{"kosten": round(totaal, 5), "reden": "wachttijd"}])
    uit = {k: {"n": len(v), "p50": percentiel(v, .5), "p95": percentiel(v, .95), "tijden": v} for k, v in tijden.items()
           if v}
    (UIT / "wachttijd.json").write_text(json.dumps({**uit, "kosten": round(totaal, 4)}, indent=1), encoding="utf-8")
    print(uit, f"${totaal:.3f}")


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    if not LABELS.exists():
        return {}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {k: v["label"] for k, v in d.get("labels", {}).items()}
    fout = [k for k, v in labels.items() if v not in LABELWAARDEN]
    if fout:
        raise Weigering(f"onbekende labels: {fout[:3]}")
    return labels


def _lezen() -> None:  # pragma: no cover - op de bestanden
    labels, per_id = _labels(), {s["id"]: s for s in _jsonl(UIT / "set.jsonl")}
    for r in sorted(_jsonl(UIT / "antwoorden.jsonl"), key=lambda r: (r["set"], r["id"], r["arm"])):
        if not moet_lezen(r) or _label(r, labels) is not None:
            continue
        s = per_id[r["id"]]
        print(f"\n== {r['id']}#{r['arm']} [{r['set']}]: {r['uitkomst']} ({r['kleur']})\n{s['tekst'][:500]}\n"
              f"uitleg: {r['uitleg']}")
        for g in r["speurstap"]:
            print(f"  zocht ({g['soort']}{', ' + g['site'] if g['site'] else ''}): {g['vraag']} -> {g['gevonden']}")
        for b in r["bronnen"]:
            print(f"  - {b.get('rol')}: {b.get('site')} {b.get('band') or ''} {b.get('url')}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    rijen = _jsonl(UIT / "antwoorden.jsonl")
    if {r["vraag"] for r in rijen} - {vingerafdruk()}:
        raise Weigering("de antwoorden rusten op een andere vraag dan de code nu stelt")
    from doublecheck import uitkomsten as uk

    tel = {**telling(rijen, _labels()), "kosten": round(uk._uitgegeven(_ronde()), 4)}
    (UIT / "telling.json").write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(tel, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De speurstap als op de eerste dag (PLAN #32.40)")
    parser.add_argument("stap", choices=("set", "draaien", "wachttijd", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    {"set": _set, "draaien": lambda: _draai(args.proef), "wachttijd": _wachttijd, "lezen": _lezen,
     "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
