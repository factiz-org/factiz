"""De gegevenslaag van de site: ingangen onder `/api/<taal>/`, alleen lezen, in vijf talen (PLAN #33.2 tot #33.6,
SPECS E9). De pagina's maakt de site in `site/` (B76); de eigen pagina's van het platform zijn weg sinds #34.2f, stap 4.

    uvicorn --factory factiz_site.app:maak_app --port 8799 --no-access-log

Zonder `FACTIZ_PUBLICATIE` leest ze de nieuwste `data/publicatie/<datum>/publicatie.db`. Zonder logboek van verzoeken:
een zoekvraag wordt nergens bewaard (DR3, B21).
"""

from __future__ import annotations

import functools
import contextlib
from datetime import date
import json
import math
import os
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from factiz_site import db, i18n, netwerk, tellen
from factiz_site import deelbeeld as dl

PAKKET = Path(__file__).resolve().parent
WORTEL = PAKKET.parent
CONTACT = "info@factiz.org"
# Wat erin zit en wat nog niet (#34.2az, E9.S25): grote redacties die een bezoeker verwacht, met een stuk van hun naam
# zoals de uitgave hem schrijft; onder BIJNA_GEEN factchecks noemt de site ze als nog bijna afwezig
GROTE_REDACTIES = (("AFP", "afp"), ("Reuters", "reuters"), ("Snopes", "snopes"), ("Correctiv", "correctiv"),
                   ("Full Fact", "full fact"))
BIJNA_GEEN = 50
MAX_BERICHT = 8192       # bytes van een zoekformulier
# de naam van de eigen redactie in het archief, zoals `publiceren.EIGEN_BRON` haar zet (de database is het contract)
EIGEN_REDACTIE = "Factiz"
# de velden van een eigen check die een machinevertaling heeft (`eigenvertaling.TEKSTEN`, #37.8)
EIGEN_TEKSTEN = ("kop", "oordeel_zin", "bewering", "kort", "tekst", "niet_weten", "bereik")


def eigen_in(c: dict, taal: str) -> dict | None:
    """Een eigen check zoals de site haar in `taal` toont (#37.8, B85): zichzelf in haar eigen taal, met een geldige
    machinevertaling de vertaalde velden over het origineel heen (met `brontaal` en de maker), anders niets."""
    if c["taal"] == taal:
        return c
    v = (c.get("vertalingen") or {}).get(taal)
    if not v:
        return None
    f = v["velden"]
    uit = {**c, **{k: f[k] for k in EIGEN_TEKSTEN if f.get(k)}, "brontaal": c["taal"], "vertaling_maker": v["maker"],
           "vertaling_nagelezen": bool(v.get("nagelezen"))}
    if isinstance(f.get("nog_uitzoeken"), list):
        uit["nog_uitzoeken"] = f["nog_uitzoeken"]
    if isinstance(f.get("tijdlijn"), list):
        uit["tijdlijn"] = [{**r, "wat": w} for r, w in zip(c.get("tijdlijn") or [], f["tijdlijn"])]
    beelden = c.get("beeld") or []
    if beelden and isinstance(f.get("beeld_bijschrift"), list) and isinstance(f.get("beeld_alt"), list):
        uit["beeld"] = [{**b, "bijschrift": s, "alt": a} for b, s, a in zip(beelden, f["beeld_bijschrift"], f["beeld_alt"])]
    if c.get("rekensom") and isinstance(f.get("rekensom"), list):
        uit["rekensom"] = [{**r, "geval": x[0], "som": x[1], "uitkomst": x[2]} for r, x in zip(c["rekensom"], f["rekensom"])]
    return uit
FILTERS = ("taal", "jaar", "oordeel", "soort", "vorm", "redactie", "thema", "onderdeel", "land", "naam")
# De volgorde waarin een filter in het formulier en boven de lijst staat: het algemeenste eerst (DESIGN §4t).
FILTERVOLGORDE = ("thema", "onderdeel", "oordeel", "soort", "vorm", "taal", "jaar", "land", "redactie")
# Een naam is geen keuzelijst (het zijn er duizenden): wie van de pagina van een naam komt, ziet haar als een stukje
# boven de lijst dat weg kan, en het formulier houdt haar vast (DESIGN §4u).
STUKVOLGORDE = FILTERVOLGORDE + ("naam",)
# Hoeveel waarden een filter met vinkjes meteen toont; de rest staat onder *Meer* (DESIGN §4v).
BOVEN = {"oordeel": 8, "taal": 8, "jaar": 6, "soort": 5, "vorm": 2}
# Het netwerk van namen (PLAN #34.2ai): zoveel namen krijgen hun naam onder de cirkel (de rest bij aanwijzen of kiezen),
# hoogstens zoveel tekens lang, en de breedte van een teken voor de ruimte die een label vraagt (Geist, 11 punten)
NETWERK_LABELS = 30
# Contextkaarten naast een factcheck (PLAN #34.2an, SPECS E9.S21): hoogstens zoveel tegelijk
CONTEXT_MAX = 4
LABEL_TEKENS = 22
LETTERBREEDTE = 6.3
# De talen waarin de vaste pagina's (Platform, Over Factiz) bestaan: sinds 2026-11-11 alle vijf. Bestaat een vaste
# pagina ooit in minder talen, dan wijst het menu van een andere taal naar de Engelse en staat dat erbij (D14).
# Niets van buiten: geen beeld, lettertype of script van een ander. Een script mag sinds B75, maar alleen van de site
# zelf en nooit om bezoekers te volgen; het zoekveld post naar de site zelf.
KOPPEN = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; "
                                "base-uri 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    # een redactie ziet alleen dat de bezoeker van factiz.org kwam, nooit welke pagina (PLAN #34.2k)
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class Weggelaten:
    """Een weggelaten naam (maatregel 2, #34.2bw) gaat nooit als merkteken naar buiten: in elk antwoord met gegevens onder
    `/api/<taal>/` wordt het ⟦naam weggelaten⟧ in de taal van de site (`i18n.gemerkt`)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        delen = scope.get("path", "").split("/") if scope["type"] == "http" else []
        if len(delen) < 3 or delen[1] != "api" or delen[2] not in i18n.TALEN:
            await self.app(scope, receive, send)
            return
        merk = i18n.WEGGELATEN.encode()
        door = json.dumps(i18n.gemerkt(delen[2]), ensure_ascii=False)[1:-1].encode()
        begin: dict = {}

        async def stuur(bericht):
            if bericht["type"] == "http.response.start":
                begin.update(bericht)
                return
            if bericht["type"] == "http.response.body" and begin:
                inhoud = bericht.get("body", b"")
                soort = dict(begin.get("headers") or []).get(b"content-type", b"")
                if soort.startswith(b"application/json") and merk in inhoud and not bericht.get("more_body"):
                    inhoud = inhoud.replace(merk, door)
                    begin["headers"] = [(k, str(len(inhoud)).encode() if k.lower() == b"content-length" else v)
                                        for k, v in begin["headers"]]
                    bericht = {**bericht, "body": inhoud}
                await send(dict(begin))
                begin.clear()
            await send(bericht)

        await self.app(scope, receive, stuur)


class Koppen:
    """Zet de beveiligingskoppen op elk antwoord, ook op een fout en op een bestand."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def stuur(bericht):
            if bericht["type"] == "http.response.start":
                namen = {k.lower() for k, _ in bericht["headers"]}
                bericht["headers"] = list(bericht["headers"]) + [
                    (k.lower().encode(), v.encode()) for k, v in KOPPEN.items() if k.lower().encode() not in namen]
            await send(bericht)

        await self.app(scope, receive, stuur)


def _standaard_pad() -> Path:
    gezet = os.environ.get("FACTIZ_PUBLICATIE")
    if gezet:
        return Path(gezet)
    kandidaten = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not kandidaten:
        raise db.Ongeldig("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    return kandidaten[-1]


def _kort(tekst: str, n: int = 220) -> str:
    """Een bewering in een lijst: afgekapt op een woord."""
    tekst = " ".join((tekst or "").split())
    if len(tekst) <= n:
        return tekst
    knip = tekst[:n].rsplit(" ", 1)[0] if " " in tekst[:n] else tekst[:n]
    return knip.rstrip(",.;:") + " …"


def _link(url: str | None) -> str:
    """Alleen een gewoon webadres wordt een link; al het andere (een script-adres, een leeg veld) niet. Een adres op
    factiz.org zelf (een eigen factcheck, #37.4) wordt een pad op deze site, zodat het ook in een voorbeeld werkt."""
    url = (url or "").strip()
    if url.startswith("https://factiz.org/"):
        return url[len("https://factiz.org"):]
    return url if url.startswith(("https://", "http://")) else ""


_STUK = re.compile(r"(\[[0-9]+\]|\[FEIT NODIG: [^\]]*\])")
EIGEN_OORDELEN = ("onwaar", "misleidend", "context", "grotendeels", "klopt", "onbewezen")


def stukken(tekst: str) -> list[dict]:
    """Een zin van een eigen factcheck in stukken (#37.4): tekst `t`, het nummer van een bron `n` tegen het woord ervoor,
    en wat een mens nog moet nagaan `nodig`. Zo zet de site de nummers als verwijzing zonder HTML uit de tekst."""
    uit: list[dict] = []
    for deel in _STUK.split(" ".join((tekst or "").split())):
        if not deel:
            continue
        if deel.startswith("[FEIT NODIG: "):
            uit.append({"nodig": deel[len("[FEIT NODIG: "):-1]})
        elif re.fullmatch(r"\[[0-9]+\]", deel):
            if uit and "t" in uit[-1]:
                uit[-1]["t"] = uit[-1]["t"].rstrip()
                if not uit[-1]["t"]:
                    uit.pop()
            uit.append({"n": int(deel[1:-1])})
        else:
            uit.append({"t": deel})
    return uit


def alineas(tekst: str) -> list[list[dict]]:
    return [stukken(a) for a in (tekst or "").strip().split("\n\n") if a.strip()]


def _host(url: str) -> str:
    m = re.match(r"https?://([^/:?#]+)", url or "")
    host = m.group(1).lower() if m else ""
    return host[4:] if host.startswith("www.") else host


def vertaald(taal: str, rij: dict) -> dict | None:
    """De tekst die boven het origineel getoond wordt, met haar taal, of niets. Een bewering in de taal van de site
    staat zoals ze is. Anders gaat een vertaling in de taal van de site voor; ligt die er niet, dan de Engelse, behalve
    bij een bewering die zelf Engels is. Het sjabloon zet het origineel er altijd bij (B32). Zonder vertaling, en ging de
    bewering in hoofdletters rond: haar normale schrift (`normaal`, #34.2ae), met het citaat eronder."""
    if rij["taal"] != taal and rij.get("vertaling"):
        return {"tekst": rij["vertaling"], "taal": taal}
    if rij["taal"] not in (taal, db.VERTAALTAAL) and rij.get("vertaling_en"):
        return {"tekst": rij["vertaling_en"], "taal": db.VERTAALTAAL}
    if rij.get("normaal"):
        return {"tekst": rij["normaal"], "taal": rij["taal"], "normaal": True}
    return None


def omveld(taal: str, p: dict, ook_als: list[dict], toeschrijvingen: list[dict], dossiers: dict[str, dict]) -> dict | None:
    """Het omveld van een bewering (PLAN #34.2h): wanneer redacties haar checkten, per jaar; waar een bron haar het eerst
    zag; aan welk netwerk een dossier haar toeschrijft (B62); en hoe ze nog meer luidt. Alleen wat er is, en alleen met
    de bron erbij: een eerste keer zonder wie het zag, of een netwerk zonder wie het vaststelde, staat er nooit. Niets als
    er niets te zeggen is buiten de telling die al op de pagina staat."""
    data = sorted(k["datum"][:10] for k in p["checks_lijst"] if k.get("datum"))
    per_jaar: dict[int, int] = {}
    for d in data:
        per_jaar[int(d[:4])] = per_jaar.get(int(d[:4]), 0) + 1
    jaren = [{"jaar": j, "aantal": per_jaar.get(j, 0)} for j in range(min(per_jaar), max(per_jaar) + 1)] if per_jaar else []
    gezien = sorted((o for o in p["opgedoken"] if o.get("datum")), key=lambda o: o["datum"])
    eerst_gezien = {"naam": gezien[0]["naam"], "datum": datum_in(taal, gezien[0]["datum"]),
                    "volgens": i18n.tekst(taal, "opgedoken_volgens", bron=gezien[0]["bron_naam"])} if gezien else None
    toegeschreven = [{"naam": dossiers[t["sleutel"]]["naam"][taal], "href": i18n.pad(taal, "dossiers", t["sleutel"]),
                      "door": t["bron"], "url": _link(t["url"]),
                      "netwerk_door": (dossiers[t["sleutel"]].get("vastgesteld") or {}).get("door", "")}
                     for t in toeschrijvingen]
    if len(jaren) < 2 and not eerst_gezien and not toegeschreven and not ook_als:
        return None
    return {"jaren": jaren, "eerst": datum_in(taal, data[0]) if data else "", "laatst": datum_in(taal, data[-1]) if data else "",
            "eerst_gezien": eerst_gezien, "toegeschreven": toegeschreven,
            "ook_als": {"aantal": len(ook_als), "voorbeelden": ook_als[:2]} if ook_als else None}


def datum_in(taal: str, iso: str) -> str:
    return i18n.datum(taal, iso) or ""


TITEL_BEWERING = 45


def lokaal_eerst(checks: list[dict], taal: str, claimtaal: str) -> list[dict]:
    """De checks zo dicht mogelijk bij de lezer (#34.2bp, SPECS E9.S31 AC5): eerst in de taal van de site, dan in de taal
    van de bewering, dan de nieuwste; bij gelijk de volgorde van de uitgave. Het land van een redactie staat niet in de
    gegevens."""
    op_datum = sorted(checks, key=lambda k: k.get("datum") or "", reverse=True)
    return sorted(op_datum, key=lambda k: (k.get("taal") != taal, k.get("taal") != claimtaal))


def kopgegevens(taal: str, nummer: str, p: dict, g: dict) -> dict:
    """Wat een zoekmachine en een AI-zoeker van een factcheck lezen (PLAN #34.2m, DESIGNSYSTEEM §6). Wie zoekt op "is it
    true that…" of "is … a hoax", krijgt treffers op de bewering zelf; dus de bewering in de titel, met het label, en het
    antwoord eerst: het oordeel van de redacties (nooit een eigen, DR2), wie checkte en wanneer. De gegevens als JSON-LD:
    de bewering als `Claim` met de artikelen van de redacties als `citation`, geen `ClaimReview` (die hoort bij hen)."""
    t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
    # een weggelaten naam (#34.2bw) in een titel en omschrijving als [naam weggelaten]; boven het antwoord de sticker
    getoond = i18n.plat(taal, g["vertaling"]["tekst"] if g["vertaling"] else g["bewering"])
    # eerst het oordeel, dan de bewering tot 45 tekens tussen de aanhalingstekens van de taal (#34.2bq, #34.2bw): een titel
    # die Google afkapt of herbouwt, toont zo nooit een kale bewering over iemand (Salumäki, Radio France)
    # sinds 2026-11-19 het stempel met wie het zegt (PLAN #34.2cc, DESIGN §4y): *Onwaar volgens Vera Files: ‘…’*
    kop = i18n.oordeel_kop(taal, p["label"], i18n.volgens_namen(p.get("volgens")))
    # de vraag zoals een zoeker haar typt (#34.2cf, B87), alleen in haar eigen taal: dan is de titel het oordeel met de
    # vraag (nooit een kale bewering, en met de namen), anders de bewering afgekapt op 45 tekens
    zv = p.get("zoekvraag")
    vraag_kop = zv["vraag"] if zv and zv.get("taal") == taal else ""
    vraag = i18n.plat(taal, vraag_kop)
    titel = (t("factcheck_titel_vraag", oordeel=kop, vraag=vraag) if vraag
             else t("factcheck_titel", oordeel=kop, bewering=_kort(getoond, TITEL_BEWERING)))
    label = kop if p["label"] in i18n.LABELS else ""
    checks = p["checks_lijst"]
    gedateerd = sorted((k for k in checks if i18n.datum(taal, (k.get("datum") or "")[:10])), key=lambda k: k["datum"])
    nieuwste = gedateerd[-1] if gedateerd else (checks[0] if checks else None)
    datum = i18n.datum(taal, nieuwste["datum"][:10]) if gedateerd else ""
    n = p.get("redacties") or len({k["redactie"] for k in checks})
    if n > 1:
        zin = (t("antwoord_meer", n=i18n.getal(taal, n), redactie=nieuwste["redactie"], datum=datum) if datum
               else t("antwoord_meer_zonder_datum", n=i18n.getal(taal, n)))
    elif nieuwste:
        zin = (t("antwoord_een", redactie=nieuwste["redactie"], datum=datum) if datum
               else t("antwoord_een_zonder_datum", redactie=nieuwste["redactie"]))
    else:
        zin = ""
    antwoord = " ".join(x for x in (f"{label}." if label else "", zin) if x)
    met_voet = f"{antwoord} {t('omschrijving_voet')}".strip()
    omschrijving = met_voet if len(met_voet) <= 160 else _kort(antwoord, 158)
    if vraag:   # het oordeel, de vraag, en wie het wanneer checkte; past dat niet, dan zonder wie en wanneer
        voorop = f"{label}." if label else ""
        omschrijving = next((x for x in (" ".join(y for y in (voorop, vraag, zin) if y), " ".join(y for y in (voorop, vraag) if y))
                             if len(x) <= 160), omschrijving)

    adres = i18n.BASIS + i18n.pad(taal, "fact-checks", nummer)
    claim: dict = {"@type": "Claim", "text": i18n.plat(taal, p["bewering"].strip()), "inLanguage": p["taal"]}
    gezien = sorted((o for o in p.get("opgedoken") or [] if o.get("datum")), key=lambda o: o["datum"])
    if gezien:   # de plek en de datum, nooit een link naar de bron van het nepnieuws
        claim["firstAppearance"] = {"@type": "CreativeWork", "name": gezien[0]["naam"], "datePublished": gezien[0]["datum"][:10]}
    citaties = [{"@type": "CreativeWork", "url": _link(k["url"]), "inLanguage": k["taal"],
                 "author": {"@type": "Organization", "name": k["redactie"]},
                 **({"datePublished": k["datum"][:10]} if i18n.datum(taal, (k.get("datum") or "")[:10]) else {})}
                # ook de checks van dezelfde bewering bij een andere redactie (*Ook gecheckt door*, #34.2bp, #34.2bq)
                for k in [*checks, *lokaal_eerst(p.get("ook_checks") or [], taal, p["taal"])]
                if k.get("link") != "offline" and _link(k.get("url"))]
    if citaties:
        claim["citation"] = citaties
    kruimel = [(t("nav_start"), i18n.BASIS + i18n.pad(taal)), (t("nav_lijst"), i18n.BASIS + i18n.pad(taal, "fact-checks")),
               (titel, adres)]
    # wanneer de pagina het laatst veranderde: de dag van haar nieuwste check, zoals `lastmod` in de sitemap (PLAN #34.2bz)
    gewijzigd = (p.get("laatste_datum") or "")[:10]
    ld = {"@context": "https://schema.org", "@type": "WebPage", "@id": adres, "url": adres, "name": titel,
          "description": omschrijving, "inLanguage": taal,
          **({"dateModified": gewijzigd} if i18n.datum(taal, gewijzigd) else {}),
          "isPartOf": {"@type": "WebSite", "name": "Factiz", "url": i18n.BASIS + "/"}, "mainEntity": claim,
          "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": i, "name": naam, "item": url} for i, (naam, url) in enumerate(kruimel, 1)]}}
    # een `<` wordt \u003c: geen bewering kan het blok openbreken met </script>
    tekst = json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return {"titel": titel, "omschrijving": omschrijving,
            "antwoord": {"kop": vraag_kop or t("antwoord_kop"), "label": label, "zin": zin}, "ld": tekst}


def melden(taal: str, nummer: str, gedaan: dict[str, bool]) -> dict:
    """De link om een fout te melden (PLAN #34.2at, SPECS E9.S24): een mail aan het adres van Factiz met het nummer en de
    taal in het onderwerp, en in de mail alleen wat de machine op deze pagina deed, om aan te kruisen. Geen formulier,
    niets bewaard (B75); het adres staat er ook als tekst, want een mailto werkt niet bij iedereen."""
    t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
    regels = [t("melden_kop"), ""] + [f"[ ] {t(sleutel)}" for sleutel, ja in gedaan.items() if ja] + \
        [f"[ ] {t('melden_anders')}", "", t("melden_pagina", adres=i18n.BASIS + i18n.pad(taal, "fact-checks", nummer))]
    onderwerp = t("melden_onderwerp", nummer=nummer, code=taal)
    href = f"mailto:{CONTACT}?subject={quote(onderwerp, safe='')}&body={quote(chr(13) + chr(10)).join(quote(r, safe='') for r in regels)}"
    return {"vraag": t("melden_vraag"), "tekst": t("melden_tekst"), "href": href, "adres": CONTACT, "redactie": t("melden_redactie")}


def vertaalregel(taal: str, brontaal: str, vertaaltaal: str, normaal: bool = False) -> str:
    """*Machine translation from Hindi. Original:* in de taal van de site; staat er op een andere site dan de Engelse
    de Engelse vertaling, dan zegt de regel dat ze Engels is. Bij het normale schrift van een bewering in hoofdletters:
    *As it circulated, in capitals:* (#34.2ae)."""
    if normaal:
        return i18n.tekst(taal, "zo_geschreven")
    sleutel = "vertaling_uit" if vertaaltaal == taal else "vertaling_engels_uit"
    return i18n.tekst(taal, sleutel, bron=i18n.taalnaam_in(taal, brontaal))


def waarom_gegevens(taal: str, nummer: str, punten: dict | None) -> dict | None:
    """*Waarom het niet klopt* als gegevens (PLAN #34.2j, B77): de punten van EUvsDisinfo in het Engels, zoals hun
    weerlegging, met de link, de herkomst en een regel om een fout te melden (een mailto met het paginanummer; niets
    opgeslagen, B75). De gemeten foutmarge staat niet meer op de pagina (PO 2026-11-22). Nooit in de vorm van een eigen
    oordeel: geen label, geen kleur."""
    if not punten:
        return None
    t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
    onderwerp = f"{t('waarom_onderwerp')}: {nummer}"
    return {"kop": t("waarom_kop"), "bron": "EUvsDisinfo", "punten": punten["punten"], "taal": "en",
            "url": _link(punten["url"]), "lees": t("waarom_lees"), "herkomst": t("waarom_herkomst"),
            "engels": t("waarom_engels") if taal != "en" else "",
            "meld": f"mailto:{CONTACT}?subject={quote(onderwerp)}", "meld_tekst": t("waarom_meld")}


def samenvatting_gegevens(taal: str, checks: list[dict], gevonden: dict | None) -> dict | None:
    """Bij een overzicht van de wereldlijst (#37.12, B91, SPECS E10.S6): wat de redacties vonden en waar het rondging, in de
    taal van de site als de machinevertaling er is (met die regel, punt 5), anders in het Engels zoals Factiz het schreef,
    elke zin met de redacties die haar dragen en het anker van hun check op deze pagina (`check-<n>`, in de volgorde waarin
    de pagina de checks toont). Geen eigen oordeel: geen label, geen kleur."""
    if not gevonden:
        return None
    rijen = gevonden["rijen"]
    t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
    plek: dict[str, dict] = {}
    for i, k in enumerate(checks):
        plek.setdefault(k["url"], {"naam": k["redactie"], "anker": f"check-{i}"})

    def zin(r: dict) -> dict:
        return {"zin": r["zin"], "bronnen": [plek[u] for u in r["bronnen"] if u in plek]}
    return {"kop": t("samenvatting_kop"), "vond": [zin(r) for r in rijen if r["soort"] == "vond"],
            "rondgang_kop": t("rondgang_kop"), "rondgang": [zin(r) for r in rijen if r["soort"] == "rondgang"],
            "door": t("samenvatting_door"), "taal": gevonden["taal"],
            "engels": t("samenvatting_engels") if gevonden["taal"] != taal else "",
            "vertaald": (t("eigen_vertaling", bron=i18n.taalnaam_in(taal, gevonden["brontaal"]))
                         if gevonden["taal"] == taal and taal != gevonden["brontaal"] else "")}


def paren(filters: dict) -> list[tuple[str, str]]:
    """De filters als paren van sleutel en waarde, op alfabet: een filter met meer waarden geeft meer paren."""
    uit = []
    for sleutel, waarde in filters.items():
        if isinstance(waarde, (tuple, list)):
            uit += [(sleutel, w) for w in waarde]
        elif waarde:
            uit.append((sleutel, waarde))
    return sorted(uit)


# De trappen van de wereldkaart (PLAN #34.2am, SPECS E9.S20 AC1, AC2): bij de verhouding vaste grenzen rond 1× (even
# vaak als gemiddeld), bij het aantal de grenzen van vijf even grote groepen landen, afgerond tot een leesbaar getal.
VERHOUDING_GRENZEN = (1.0, 1.5, 2.0, 3.0)


def _rond(n: float) -> int:
    """Twee cijfers die tellen: 1473 wordt 1500, 237 wordt 240; onder de honderd blijft het getal."""
    if n < 100:
        return int(round(n))
    stap = 10 ** (len(str(int(n))) - 2)
    return int(round(n / stap) * stap)


def grenzen_aantal(waarden: list[int]) -> list[int]:
    """Hoogstens vier grenzen tussen vijf even grote groepen van de landen met een factcheck, oplopend en elk anders."""
    w = sorted(v for v in waarden if v > 0)
    uit: list[int] = []
    for q in (0.2, 0.4, 0.6, 0.8):
        g = _rond(w[min(len(w) - 1, int(q * len(w)))]) if w else 0
        if g > max(uit[-1] if uit else 1, w[0] if w else 0):
            uit.append(g)
    return uit


def trap(waarde: float, grenzen) -> int:
    """De trap van een waarde: 1 onder de eerste grens, en één hoger bij elke grens die ze haalt."""
    return 1 + sum(waarde >= g for g in grenzen)


def kenmerken(taal: str, kenmerk: tuple[str, str] | None) -> list[dict]:
    """De soort volgens de redactie en de vorm van een factcheck, elk met hun woord en de lijst met dat filter; leeg
    als geen van beide zeker is (SPECS E9.S19)."""
    soort, vorm = kenmerk or ("", "")
    uit = []
    if soort:
        uit.append({"wat": "soort", "waarde": soort, "naam": i18n.tekst(taal, "soort_" + soort),
                    "regel": i18n.tekst(taal, "soort_volgens"), "href": lijst_url(taal, {"soort": (soort,)})})
    if vorm:
        uit.append({"wat": "vorm", "waarde": vorm, "naam": i18n.tekst(taal, "vorm_" + vorm), "regel": "",
                    "href": lijst_url(taal, {"vorm": (vorm,)})})
    return uit


def lijst_url(taal: str, filters: dict, blad: int = 1) -> str:
    """Het adres van de lijst met deze filters: de sleutels op alfabet, het eerste blad zonder nummer."""
    delen = paren(filters) + ([("p", str(blad))] if blad > 1 else [])
    vraag = urlencode(sorted(delen))
    return i18n.pad(taal, "fact-checks") + (f"?{vraag}" if vraag else "")


def _vouw(tekst: str) -> tuple[str, list[int]]:
    """De tekst zonder hoofdletters en accenten, met voor elk teken daarvan de plek in de tekst zelf: zo is een treffer
    in de gevouwen tekst terug te leggen op de echte."""
    gevouwen, plek = [], []
    for i, teken in enumerate(tekst):
        for kaal in unicodedata.normalize("NFKD", teken.casefold()):
            if unicodedata.category(kaal) != "Mn" or not gevouwen:
                gevouwen.append(kaal)
                plek.append(i)
    return "".join(gevouwen), plek


def _raak(tekst: str, termen: list[str]) -> list[tuple[int, int]]:
    """Waar de stukken van de vraag in de tekst staan, als begin en eind in de tekst zelf. Een stuk telt als heel
    woord waar dat kan; staat het nergens als heel woord (een schrift zonder spaties, een deel van een woord), dan
    waar het als deel staat. Hoofdletters en accenten tellen niet, zoals bij het zoeken zelf. Een stuk met spaties is
    een reeks woorden, met tussen de woorden een spatie, streepje of ander teken (Bill Gates, Corona-Virus); een stuk
    dat op * eindigt, is het begin van een woord, en dan telt het hele woord (biolab* in biolaboratorios, #34.2y)."""
    gevouwen, plek = _vouw(tekst)
    vakken: list[tuple[int, int]] = []
    for term in termen:
        begin = len(term) > 1 and term.endswith("*")
        woorden = _vouw(term[:-1] if begin else term)[0].split()
        if not woorden:
            continue
        heel, deel = [], []
        for m in re.finditer(r"[\W_]+".join(map(re.escape, woorden)) + (r"[^\W_]*" if begin else ""), gevouwen):
            i, eind = m.span()
            vak = (plek[i], plek[eind - 1] + 1)
            los_voor = i == 0 or not gevouwen[i - 1].isalnum()
            los_na = eind == len(gevouwen) or not gevouwen[eind].isalnum()
            if los_voor and los_na:
                heel.append(vak)
            elif not begin:
                deel.append(vak)
        vakken += heel or deel
    samen: list[tuple[int, int]] = []
    for begin, eind in sorted(vakken):
        # een klinkerteken of ander combinerend teken hoort bij het teken ervoor: het vak loopt door tot het volgende
        while eind < len(tekst) and unicodedata.category(tekst[eind]).startswith("M"):
            eind += 1
        if samen and begin <= samen[-1][1]:
            samen[-1] = (samen[-1][0], max(samen[-1][1], eind))
        else:
            samen.append((begin, eind))
    return samen


def markeer(tekst: str, termen: list[str]) -> list[tuple[str, bool]]:
    """De tekst in stukken, met bij elk stuk of het een woord van de vraag is. De tekst zelf verandert niet: het
    sjabloon zet de stukken achter elkaar en ontsnapt elk stuk zoals alle tekst uit de database."""
    uit, vorige = [], 0
    for begin, eind in _raak(tekst, termen):
        if begin > vorige:
            uit.append((tekst[vorige:begin], False))
        uit.append((tekst[begin:eind], True))
        vorige = eind
    if vorige < len(tekst):
        uit.append((tekst[vorige:], False))
    return uit


def fragment(tekst: str, termen: list[str], n: int = 220) -> str:
    """Een bewering in een lijst met treffers: het begin, of bij een lange bewering het stuk rond het eerste woord van
    de vraag, zodat te zien is waarom zij gevonden is."""
    tekst = " ".join((tekst or "").split())
    raak = _raak(tekst, termen)
    if not raak or raak[0][1] <= n - 40:
        return _kort(tekst, n)
    begin = max(0, raak[0][0] - 80)
    begin = tekst.find(" ", begin) + 1 if begin and " " in tekst[begin:raak[0][0]] else begin
    return "… " + _kort(tekst[begin:], n)


# Een vraag naar de site zelf (PLAN #34.2ac, SPECS E9.S14 AC6): per vaste pagina haar naam in het menu (in elke taal)
# en de woorden waarmee iemand haar zoekt. Alleen een ingang, nooit een doorsturing: "over" is ook een gewoon woord.
VASTE_INGANGEN = {
    "about": ("nav_over", {"over", "about", "uber", "acerca", "a propos", "propos", "over factiz", "about factiz",
                           "privacy", "privacidad", "datenschutz", "confidentialite", "vie privee", "contact", "kontakt",
                           "contacto", "impressum", "factiz"}),
    "platform": ("nav_platform", {"platform", "plattform", "plataforma", "plateforme", "api", "open data"}),
    "sources": ("nav_bronnen", {"bronnen", "sources", "quellen", "fuentes", "licentie", "licenties", "license", "licenses",
                                "licence", "licences", "lizenz", "lizenzen", "licencia", "licencias", "cc by"}),
    "newsrooms": ("nav_redacties", {"redacties", "newsrooms", "redaktionen", "redacciones", "redactions", "factcheckers",
                                    "fact checkers", "faktenchecker", "verificadores", "fact-checkers"}),
}


def vaste_ingangen(vraag: str, taal: str) -> list[dict]:
    """De vaste pagina's die bij een vraag naar de site zelf horen: de hele vraag is hun naam of een van hun woorden."""
    sleutel = db.sleutel(vraag)
    if not sleutel:
        return []
    uit = []
    for pagina, (naamsleutel, woorden) in VASTE_INGANGEN.items():
        namen = {db.sleutel(i18n.tekst(t, naamsleutel)) for t in i18n.TALEN}
        if sleutel in namen or sleutel in {db.sleutel(w) for w in woorden}:
            uit.append({"soort": "pagina", "pagina": pagina, "naam": i18n.tekst(taal, naamsleutel), "aantal": None,
                        "href": i18n.pad(taal, pagina)})
    return uit


def ingang_href(taal: str, i: dict) -> str:
    """Het adres van een ingang op de site."""
    if i.get("href"):
        return i["href"]
    if i["soort"] == "naam":
        return i18n.pad(taal, "names", i["nummer"])
    if i["soort"] == "thema":
        return i18n.pad(taal, "themes", i["thema"])
    if i["soort"] == "onderdeel":
        return i18n.pad(taal, "themes", i["thema"], i["onderdeel"])
    if i["soort"] == "dossier":
        return i18n.pad(taal, "dossiers", i["sleutel"])
    if i["soort"] == "factcheck":
        return i18n.pad(taal, "fact-checks", i["nummer"])
    return lijst_url(taal, {"redactie": i["redactie"]})


DEELBEELD_GEHEUGEN = 256       # de laatste deelplaatjes in het geheugen (~60 KB per stuk)
NUMMER = re.compile(r"[0-9a-f]{16}")


def deelgegevens(pub: "db.Publicatie", taal: str, nummer: str) -> dict | None:
    """Wat op het deelplaatje van een factcheck komt (PLAN #34.2aq, SPECS E9.S23): dezelfde kop, hetzelfde label en dezelfde
    zin als op de pagina. Kan het lettertype het schrift van de kop niet tonen, dan de Engelse versie, en anders geen
    bewering (AC2)."""
    if taal not in i18n.TALEN or not NUMMER.fullmatch(nummer):
        return None
    p = pub.pagina(nummer)
    if p is None:
        return None
    p["vertaling"], p["vertaling_en"] = p["vertalingen"].get(taal), p["vertalingen"].get(db.VERTAALTAAL)
    v = vertaald(taal, p)
    getoond = i18n.plat(taal, v["tekst"] if v else p["bewering"])
    g = {"vertaling": v, "bewering": p["bewering"], "label": i18n.label(taal, p["label"])}
    engels = i18n.plat(taal, p["vertaling_en"] or (p["bewering"] if p["taal"] == db.VERTAALTAAL else ""))
    tekst = getoond if dl.kan_tonen(getoond) else (engels if dl.kan_tonen(engels or "") else "")
    zin = kopgegevens(taal, nummer, p, g)["antwoord"]["zin"]
    if not dl.kan_tonen(zin):   # een naam in een schrift zonder lettertype: de telling van de pagina, geen blokjes
        zin = i18n.telregel(taal, p["redacties"], len(json.loads(p["talen"] or "[]")), p["eerste_datum"], p["laatste_datum"])
    # het stempel met wie het zegt (PLAN #34.2cc, DESIGN §4y); een naam in een schrift zonder lettertype: geen *volgens*
    # de vormen van lang naar kort: het plaatje neemt de eerste die past, alle namen of *en N andere*
    namen = i18n.volgens_namen(p.get("volgens"))
    vormen = [v for v in dict.fromkeys(i18n.volgens(taal, p["label"], namen, hoogstens=h) for h in (4, 3, 2, 1)) if v]
    return {"bewering": tekst, "label": i18n.stempel(taal, p["label"]), "volgens": [v for v in vormen if dl.kan_tonen(v)],
            "klasse": p["label"], "zin": zin, "thema": p.get("thema")}


@functools.lru_cache(maxsize=DEELBEELD_GEHEUGEN)
def deelbeeld_bytes(pub: "db.Publicatie", taal: str, nummer: str) -> bytes | None:
    """Het deelplaatje, getekend bij de eerste vraag en daarna uit het geheugen (AC3): niets vooraf."""
    g = deelgegevens(pub, taal, nummer)
    return dl.teken(**g) if g else None


def ingangsgegevens(pub: "db.Publicatie", taal: str, soort: str, sleutel: str, deel: str | None = None) -> dict | None:
    """Wat op het plaatje van een thema, onderdeel of dossier komt (PLAN #34.2ar, E9.S23 AC6): de soort en de naam zoals in
    de kop van de pagina, en het aantal factchecks."""
    if taal not in i18n.TALEN:
        return None
    t = lambda k, **w: i18n.tekst(taal, k, **w)
    if soort == "thema":
        thema = pub.thema(sleutel)
        onderdeel = pub.deel(sleutel, deel) if thema and deel else None
        if thema is None or (deel is not None and onderdeel is None):
            return None
        _, totaal = pub.lijst(vertaal=taal, thema=sleutel, **({"onderdeel": deel} if onderdeel else {}))
        return {"kicker": thema["naam"][taal] if onderdeel else t("nav_themas"),
                "titel": (onderdeel or thema)["naam"][taal], "thema": sleutel, "dossier": None,
                "regel": t("lijst_een" if totaal == 1 else "lijst_meer", n=i18n.getal(taal, totaal))}
    if soort == "dossier":
        d = pub.dossier(sleutel)
        if d is None:
            return None
        st = d["stand"]
        aantal = t("lijst_een" if st["factchecks"] == 1 else "lijst_meer", n=i18n.getal(taal, st["factchecks"]))
        return {"kicker": t("dossier_soort_" + d["soort"]), "titel": d["naam"][taal], "thema": d["thema"], "dossier": sleutel,
                "regel": f"{aantal}, {i18n.telregel(taal, st['redacties'], st['talen'], st['eerste'] or '', st['laatste'] or '')}"}
    return None


@functools.lru_cache(maxsize=DEELBEELD_GEHEUGEN)
def ingangsbeeld_bytes(pub: "db.Publicatie", taal: str, soort: str, sleutel: str, deel: str | None = None) -> bytes | None:
    """Het plaatje van een thema, onderdeel of dossier, getekend bij de eerste vraag (E9.S23 AC3, AC6)."""
    g = ingangsgegevens(pub, taal, soort, sleutel, deel)
    return dl.teken_ingang(**g) if g else None


def maak_app(pad: str | Path | None = None, tellingen: str | Path | None = None) -> Starlette:
    pub = db.Publicatie(pad or _standaard_pad())
    # anoniem tellen (#34.2ba, E9.S26, B78): alleen met een bestand, uit de aanroep of uit FACTIZ_TELLINGEN
    teller = tellen.Teller(tellingen if tellingen is not None else os.environ.get("FACTIZ_TELLINGEN") or None)

    def themanaam(taal: str, thema: str, onderdeel: str = "") -> str:
        ding = pub.deel(thema, onderdeel) if onderdeel else pub.thema(thema)
        return ding["naam"][taal] if ding else ""

    def landnaam(taal: str, code: str) -> str:
        return pub.landen.get(code, {}).get(taal, "")

    def filterdelen(taal: str, gekozen: dict, sorteer: str | None, zoeken: bool, tellingen: dict) -> dict:
        """Wat het filterformulier, de stukjes erboven en de volgorde nodig hebben. `tellingen` zijn de aantallen per
        filterwaarde binnen wat nu getoond wordt (`db.facetten_van` of die van een zoekvraag): een waarde die niets zou
        tonen, wordt niet aangeboden, behalve als zij gekozen is (SPECS E9.S12)."""
        def gekozen_rij(soort: str) -> list[str]:
            waarde = gekozen.get(soort)
            return list(waarde) if isinstance(waarde, (tuple, list)) else [waarde] if waarde else []

        thema = pub.thema(gekozen["thema"]) if gekozen.get("thema") else None
        namen = {"thema": lambda w: themanaam(taal, w), "onderdeel": lambda w: themanaam(taal, gekozen["thema"], w),
                 "oordeel": lambda w: i18n.label(taal, w), "taal": lambda w: i18n.taalnaam_in(taal, w), "jaar": lambda w: w,
                 "land": lambda w: landnaam(taal, w), "redactie": lambda w: w,
                 "soort": lambda w: i18n.tekst(taal, "soort_" + w), "vorm": lambda w: i18n.tekst(taal, "vorm_" + w),
                 "naam": lambda w: pub.naam(w)["naam"][taal]}
        # de volgorde van de waarden: het meest voorkomende eerst, jaren van nieuw naar oud, thema's zoals de lijst
        vast = {"thema": [th["sleutel"] for th in pub.themas],
                "onderdeel": [o["sleutel"] for o in (thema["onderdelen"] if thema else [])],
                "oordeel": [o for o, _ in pub.facetten["oordeel"]], "taal": [c for c, _ in pub.facetten["taal"]],
                "jaar": [j for j, _ in pub.facetten["jaar"]], "land": [c for c, _ in pub.facetten["land"]],
                "redactie": [r for r, _ in pub.facetten["redactie"]],
                "soort": [w for w, _ in pub.facetten["soort"]], "vorm": [w for w, _ in pub.facetten["vorm"]]}
        lijsten: dict[str, list[dict]] = {}
        for soort in db.FACETTEN:
            aan, tel = gekozen_rij(soort), tellingen.get(soort, {})
            lijsten[soort] = [{"waarde": w, "naam": namen[soort](w), "aantal": i18n.getal(taal, tel.get(w, 0)), "aan": w in aan}
                              for w in vast[soort] if tel.get(w) or w in aan]
        for soort in ("land", "redactie"):
            lijsten[soort].sort(key=lambda k: k["naam"].casefold())
        groepen = []
        for soort in db.MEER:
            # wat gekozen is staat altijd in beeld; de rest van de lange lijsten onder *Meer*
            boven = [k for k in lijsten[soort] if k["aan"]]
            boven += [k for k in lijsten[soort] if not k["aan"]][:max(0, BOVEN[soort] - len(boven))]
            orde = {k["waarde"]: i for i, k in enumerate(lijsten[soort])}
            boven.sort(key=lambda k: orde[k["waarde"]])
            groepen.append({"soort": soort, "kop": i18n.tekst(taal, "filter_" + soort), "boven": boven,
                            # wat de soort en de vorm tellen, onder hun kop (SPECS E9.S19 AC5)
                            "uitleg": i18n.tekst(taal, f"filter_{soort}_uitleg") if soort in ("soort", "vorm") else "",
                            "meer": [k for k in lijsten[soort] if k not in boven]})
        actief = {k: v for k, v in gekozen.items() if v not in (None, "", ())}
        volgorde = {"sorteer": sorteer} if sorteer else {}
        stukjes = []
        for soort in STUKVOLGORDE:
            for waarde in gekozen_rij(soort):
                # het thema weghalen neemt zijn onderdeel mee; van een filter met meer waarden gaat alleen deze weg
                rest = {k: v for k, v in actief.items() if k != soort and not (soort == "thema" and k == "onderdeel")}
                over = tuple(w for w in gekozen_rij(soort) if w != waarde)
                if soort in db.MEER and over:
                    rest[soort] = over
                stukjes.append({"soort": soort, "kop": i18n.tekst(taal, "filter_" + soort), "naam": namen[soort](waarde),
                                "paren": paren({**rest, **volgorde}), "url": lijst_url(taal, {**rest, **volgorde})})
        opties = ([("", "sorteer_relevantie")] if zoeken else []) + [
            ("nieuw" if zoeken else "", "sorteer_nieuw"), ("oud", "sorteer_oud"), ("redacties", "sorteer_redacties")]
        # een paar thema's boven de lijst, met hun aantal; ze staan ook in het formulier (DESIGN §4v)
        promotie = [] if gekozen.get("thema") or zoeken else [
            {"waarde": k["waarde"], "naam": k["naam"], "aantal": k["aantal"],
             "url": lijst_url(taal, {**actief, "thema": k["waarde"], **volgorde})}
            for k in sorted(lijsten["thema"], key=lambda k: -tellingen.get("thema", {}).get(k["waarde"], 0))[:6]]
        return {"lijsten": lijsten, "groepen": [g for g in groepen if g["boven"]], "sorteer": sorteer or "",
                "promotie": promotie,
                "volgordes": [{"waarde": w, "naam": i18n.tekst(taal, k), "aan": w == (sorteer or ""),
                               "url": lijst_url(taal, {**actief, **({"sorteer": w} if w else {})})} for w, k in opties],
                "stukjes": stukjes, "velden": [s for s in ("thema", "onderdeel", "land", "redactie") if lijsten[s]],
                "gekozen": {k: gekozen.get(k) or "" for k in FILTERS}, "paren": paren(actief),
                "alles": paren({**actief, **volgorde})}

    def lees_lijstvraag(vraag) -> tuple[dict, str | None, int, bool]:
        """De filters, de volgorde en het blad uit het adres van een lijst. Alleen bekende sleutels, elk één keer, en
        alleen waarden die in de database voorkomen: al het andere bestaat niet (404). Het formulier stuurt ook lege
        keuzes mee; die vallen weg, net als een onderdeel dat niet bij het gekozen thema hoort, en `opruimen` zegt dan
        dat het naar het ene adres van die lijst moet (SPECS E9.S10 AC4)."""
        enkel = [k for k, _ in vraag.multi_items() if k not in db.MEER]
        if set(vraag.keys()) - set(FILTERS) - {"p", "sorteer"} or len(enkel) != len(set(enkel)):
            raise HTTPException(404)
        gekozen: dict = {soort: vraag.get(soort) or None for soort in FILTERS if soort not in db.MEER}
        opruimen = any(waarde == "" for waarde in vraag.values()) or vraag.get("p") == "1"
        for soort in db.MEER:
            # een filter met vinkjes: elke waarde moet bestaan; een lege of een dubbele valt weg
            ruw_rij = vraag.getlist(soort)
            rij = tuple(sorted({w for w in ruw_rij if w}))
            if any(not pub.kent(soort, w) for w in rij):
                raise HTTPException(404)
            opruimen = opruimen or len(rij) != len(ruw_rij)
            gekozen[soort] = rij or None
        for soort, waarde in gekozen.items():
            if waarde is not None and soort not in db.MEER and soort != "onderdeel" and not pub.kent(soort, waarde):
                raise HTTPException(404)
        sorteer = vraag.get("sorteer") or None
        if sorteer is not None and sorteer not in db.LIJST_VOLGORDES:
            raise HTTPException(404)
        if gekozen["onderdeel"] is not None and not (
                gekozen["thema"] and pub.deel(gekozen["thema"], gekozen["onderdeel"])):
            gekozen["onderdeel"], opruimen = None, True
        ruw = vraag.get("p") or "1"
        if not (ruw.isascii() and ruw.isdigit()) or len(ruw) > 6 or int(ruw) < 1:
            raise HTTPException(404)
        blad = int(ruw)
        return gekozen, sorteer, blad, opruimen

    def rij_gegevens(taal: str, r: dict) -> dict:
        """Een rij van een lijst als gegevens, zoals de kaart van de site (`Rij.jsx`) haar toont: de vertaling met het origineel eronder, of
        de bewering zoals ze is (B32)."""
        v = vertaald(taal, r)
        return {"nummer": r["nummer"], "href": eigen_href(r["nummer"], taal) or i18n.pad(taal, "fact-checks", r["nummer"]),
                "tekst": _kort(v["tekst"] if v else r["bewering"]), "taal": v["taal"] if v else r["taal"],
                "richting": "ltr" if v and not v.get("normaal") else r["richting"],
                "origineel": {"regel": vertaalregel(taal, r["taal"], v["taal"], v.get("normaal", False)), "tekst": _kort(r["bewering"], 140),
                              "taal": r["taal"], "richting": r["richting"]} if v else None,
                "label": i18n.label(taal, r["label"]), "datum": i18n.datum(taal, r["laatste_datum"]) or "",
                # het oordeel als stempel met wie het zegt (PLAN #34.2cc, DESIGN §4y): *Onwaar* · volgens DW en BR24
                "stempel": i18n.stempel(taal, r["label"]), "volgens": i18n.volgens(taal, r["label"], i18n.volgens_namen(r.get("volgens"))),
                # de soort voor de kleur van het label, altijd met het woord (PLAN #34.2l, DESIGNSYSTEEM §4)
                "soort": r["label"] if r["label"] in i18n.LABELS else "geen",
                # de taal alleen als de bewering in een andere taal staat en er geen vertaling bij is: anders zegt de regel bij
                # het origineel het al, en een losse code zonder naam zegt niemand iets
                "taalnaam": "" if (v and not v.get("normaal")) or r["taal"] == taal or i18n.taalnaam_in(taal, r["taal"]) == r["taal"]
                            else i18n.taalnaam_in(taal, r["taal"]),
                # wat een rij in een lijst zegt zonder te klikken (#443, #2281): het thema en hoeveel redacties het natrokken
                "thema": {"sleutel": r["thema"], "naam": themanaam(taal, r["thema"])} if r.get("thema") and themanaam(taal, r["thema"]) else None,
                # het land waar de bewering over gaat, uit de themaronde (PLAN #34.2w), in de taal van de site
                "land": {"code": r["land"], "naam": landnaam(taal, r["land"])} if r.get("land") and landnaam(taal, r["land"]) else None,
                # de soort volgens de redactie en de vorm (PLAN #34.2ak, SPECS E9.S19), met een lijnicoon op de site
                "kenmerken": kenmerken(taal, r.get("kenmerk")),
                "redacties": i18n.tekst(taal, "redacties_een" if r.get("redacties") == 1 else "redacties_meer",
                                        n=i18n.getal(taal, r.get("redacties") or 0)) if r.get("redacties") else "",
                # een eigen factcheck van Factiz (#37.4): de rij krijgt het zegel, ook in grijstinten te zien (D12)
                **({"eigen": i18n.tekst(taal, "eigen_oordeel_" + o)} if (o := eigen_oordeel(r["nummer"])) else {})}

    def eigen_href(nummer: str, taal: str = "") -> str:
        """De eigen factcheck zelf bij haar pagina in het archief (#37.4, PO 2026-11-18: "we zitten al op Factiz, dus we
        kunnen het resultaat direct op deze pagina presenteren"), in de taal van de site als ze daarin bestaat of vertaald
        is (#37.8), anders in haar eigen taal; of niets."""
        sleutel = pub.eigen_paginas.get(nummer)
        c = next((c for c in pub.eigen if c["sleutel"] == sleutel), None) if sleutel else None
        if not c:
            return ""
        return c["paden"][taal if taal and eigen_in(c, taal) else c["taal"]]

    def eigen_oordeel(nummer: str) -> str:
        """Het oordeel van een eigen factcheck bij haar pagina in het archief, of niets."""
        sleutel = pub.eigen_paginas.get(nummer)
        return next((c["oordeel"] for c in pub.eigen if c["sleutel"] == sleutel), "") if sleutel else ""

    def api_archief(taal: str):
        def antwoord(request: Request) -> Response:
            # De interne ingang van de proef in Astro (PLAN #34.0): dezelfde lijst, filters, tellingen en volgorde als de
            # start en /fact-checks/, met dezelfde functies, als gegevens. Geen zoekvraag: die gaat nooit in een adres.
            gekozen, sorteer, blad, _ = lees_lijstvraag(request.query_params)
            rijen, totaal = pub.lijst(blad=blad, vertaal=taal, sorteer=sorteer, **gekozen)
            bladen = max(1, math.ceil(totaal / db.PER_BLAD))
            if blad > bladen and totaal:
                raise HTTPException(404)
            actief = {k: v for k, v in gekozen.items() if v is not None}
            gegevens = {
                "taal": taal, "totaal": totaal, "blad": blad, "bladen": bladen,
                "aantal": i18n.tekst(taal, "lijst_een" if totaal == 1 else "lijst_meer", n=i18n.getal(taal, totaal)),
                "paren": paren({**actief, **({"sorteer": sorteer} if sorteer else {})}),
                "rijen": [rij_gegevens(taal, r) for r in rijen],
                "filters": filterdelen(taal, gekozen, sorteer, zoeken=False, tellingen=pub.facetten_van(**gekozen)),
                "tellingen": {k: i18n.getal(taal, v) for k, v in pub.tellingen.items()},
                # tot wanneer de site bij is, voor de voet en de sitemap (PLAN #34.2bz)
                "actueel": actueel(taal),
                # Factiz Radar, de eigen checks in deze taal, voor het menu en de ringen op de start (PO 2026-11-19)
                "radar": radar(taal),
                "dossiers": [dossierkaart(taal, d) for d in pub.dossiers[:4]],
                # hoeveel dossiers er zijn, voor de link naar alle dossiers op de start (PO 2026-11-23: "Hier dan ook een cijfer.")
                "dossiers_aantal": i18n.getal(taal, len(pub.dossiers)),
                # of de uitgave namen heeft: zonder namen bestaat het register niet, en wijst de voet er niet heen
                "namen": pub.heeft_namen,
            }
            return Response(json.dumps(gegevens, ensure_ascii=False, separators=(",", ":")),
                            media_type="application/json", headers={"Cache-Control": "public, max-age=300"})
        return antwoord

    def json_antwoord(gegevens: dict) -> Response:
        return Response(json.dumps(gegevens, ensure_ascii=False, separators=(",", ":")), media_type="application/json",
                        headers={"Cache-Control": "public, max-age=300"})

    def eens(taal: str, eigen: list[dict], ook: list[dict]) -> dict | None:
        """Wie het checkte en wat elk zegt (PLAN #34.2cd, SPECS E9.S31 AC7; PO 2026-11-22: "Dus je ziet de drie stempels met
        daarachter de betreffende redactie. That's it."): elke redactie één keer, met haar nieuwste oordeel, van deze pagina
        en onder Ook gecheckt door, in de volgorde van de pagina; tot vier allemaal, daarboven drie en *N andere*, zoals bij
        *volgens*. Hun oordelen, nooit een eigen (DR2); pas vanaf twee redacties met een oordeel. Elke redactie linkt naar
        haar eigen check eronder (PO 2026-11-22: "1"): `check-<n>` op deze pagina, `ook-<n>` onder Ook gecheckt door."""
        per: dict[str, tuple[str, str]] = {}
        anker: dict[str, str] = {}
        for k, a in [*((k, f"check-{i}") for i, k in enumerate(eigen)), *((k, f"ook-{i}") for i, k in enumerate(ook))]:
            if k["oordeel"] in i18n.LABELS:
                nu = (k.get("datum") or "", k["oordeel"])
                if k["redactie"] not in per or nu > per[k["redactie"]]:
                    per[k["redactie"]], anker[k["redactie"]] = nu, a
        if len(per) < 2:
            return None
        namen = list(per)
        heel = len(namen) <= 4
        toon = namen if heel else namen[:3]
        return {"tekst": i18n.tekst(taal, "eens_kop"),
                "redacties": [{"naam": n, "soort": per[n][1], "woord": i18n.stempel(taal, per[n][1]), "anker": anker[n]}
                              for n in toon],
                "meer": "" if heel else i18n.tekst(taal, "stempel_andere", n=i18n.getal(taal, len(namen) - 3)),
                "anker": "ook-gecheckt" if ook else "bronnen"}

    def check_gegevens(taal: str, k: dict) -> dict:
        """Eén check als gegevens: de redactie, haar eigen woorden, de datum en de taal, en de link naar het artikel of
        het archief; de woorden in een andere taal dan de site letterlijk vertaald (#34.2o)."""
        t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
        return {
            "redactie": k["redactie"], "oordeel": _kort(k["oordeel_eigen"] or "", 300), "oordeel_taal": k["taal"],
            "oordeel_richting": i18n.richting(k["taal"]), "datum": i18n.datum(taal, k["datum"]) or t("geen_datum"),
            "taal": i18n.taalnaam(k["taal"]), "taal_code": k["taal"], "offline": k["link"] == "offline",
            "url": "" if k["link"] == "offline" else _link(k["url"]),
            "archief": _link(k.get("archief_url")) if k["link"] == "offline" else "",
            "archief_tekst": (t("check_archief_van", datum=i18n.datum(taal, k["archief_datum"]))
                              if i18n.datum(taal, k.get("archief_datum")) else t("check_archief")),
            "glos": k["glossen"].get(taal) if k["taal"] != taal else None,
            "glos_regel": t("oordeel_glos", bron=i18n.taalnaam_in(taal, k["taal"]))
            if k["taal"] != taal and k["glossen"].get(taal) else "",
        }

    def api_factcheck(taal: str):
        def antwoord(request: Request) -> Response:
            # De factcheckpagina als gegevens (PLAN #34.2): dezelfde functies als `factcheck`, met de teksten al in de
            # taal van de site, zodat een voorkant nooit iets anders zegt dan het platform.
            nummer = request.path_params["nummer"]
            p = pub.pagina(nummer)
            if p is None:
                # het nummer van een andere formulering wijst blijvend naar de bewering, zoals de pagina (`factcheck`)
                doel = pub.verwijzing(nummer)
                if doel:
                    return RedirectResponse(f"/api/{taal}/factcheck/{doel}", status_code=301)
                raise HTTPException(404)
            p["vertaling"], p["vertaling_en"] = p["vertalingen"].get(taal), p["vertalingen"].get(db.VERTAALTAAL)
            # de check die het dichtst bij de lezer staat eerst (#34.2bp): ook in het antwoord, de bronnen en de context
            p["checks_lijst"] = lokaal_eerst(p["checks_lijst"], taal, p["taal"])
            t = lambda sleutel, **w: i18n.tekst(taal, sleutel, **w)
            v = vertaald(taal, p)
            # een voorlopige vertaling (B93) is geen eigen tekst: zoekmachines zien de pagina in die taal niet
            eigen = i18n.eigen_talen(p["taal"], [t_ for t_ in p["vertalingen"] if t_ not in p["voorlopig"]])
            varianten = pub.varianten(nummer, taal)
            ding = lambda sleutel, *pad_: {"sleutel": sleutel, "naam": themanaam(taal, *pad_), "href": i18n.pad(taal, "themes", *pad_)}
            gegevens = {
                "nummer": nummer, "href": i18n.pad(taal, "fact-checks", nummer),
                "vindbaar": {"index": taal in eigen, "talen": list(eigen), "x_default": i18n.x_default(eigen)},
                "bewering": p["bewering"], "taal": p["taal"], "richting": p["richting"],
                # de tekst boven het citaat: een vertaling, of het normale schrift van een bewering in hoofdletters
                "vertaling": {"tekst": v["tekst"], "taal": v["taal"],
                              "regel": vertaalregel(taal, p["taal"], v["taal"], v.get("normaal", False))} if v else None,
                # de banner boven een voorlopige vertaling (B93; PO: "machinevertaling - wacht op nieuwe vertaling")
                "voorlopig": t("vertaling_voorlopig") if v and v["taal"] in p["voorlopig"] else "",
                "label": i18n.label(taal, p["label"]), "label_klasse": p["label"],
                "stempel": i18n.stempel(taal, p["label"]), "volgens": i18n.volgens(taal, p["label"], i18n.volgens_namen(p.get("volgens"))),
                # het deelplaatje (PLAN #34.2aq): getekend als iemand het vraagt, met de versie van de uitgave in het adres
                "deelbeeld": {"src": f"/deelbeeld/{taal}/{nummer}.jpg?v={pub.release}",
                              "alt": f"{_kort(i18n.plat(taal, v['tekst'] if v else p['bewering']), 200)} · {i18n.label(taal, p['label'])}"},
                # een naam die Factiz bewust weglaat (#34.2bw, SPECS E9.S8 AC13): de site zet de voetnoot onder de bewering
                "weggelaten": i18n.WEGGELATEN in p["bewering"],
                "telregel": i18n.telregel(taal, p["redacties"], len(json.loads(p["talen"] or "[]")), p["eerste_datum"],
                                          p["laatste_datum"]),
                "eerder": [t("eerder", label=i18n.label(taal, k), jaar=j) for k, j in json.loads(p["eerder"] or "[]")],
                "checks": [check_gegevens(taal, k) for k in p["checks_lijst"]],
                "herkomst": [t("record_bron", naamsvermelding=b["naamsvermelding"], licentie=b["licentie"]) for b in p["bronnen"]],
                "opgedoken": [{"niveau": t("niveau_" + o["niveau"]) if o["niveau"] in ("waargenomen", "toegeschreven") else "",
                               "naam": o["naam"], "volgens": t("opgedoken_volgens", bron=o["bron_naam"]),
                               "datum": i18n.datum(taal, o["datum"]) or "", "url": _link(o["url"])} for o in p["opgedoken"]],
                "varianten": {"telling": t("ook_als_telling", n=i18n.getal(taal, varianten["checks"]),
                                           talen=t("talen_een" if varianten["talen"] == 1 else "talen_meer",
                                                   n=i18n.getal(taal, varianten["talen"]))),
                              # per rij ook wie het natrok, in welke taal en wanneer voor het eerst, zoals de pagina: zo
                              # is te zien dat hetzelfde bericht rondging
                              "rijen": [{**rij_gegevens(taal, r), "redactienamen": r["redactienamen"],
                                         "taal_eigen": i18n.taalnaam(r["taal"]),
                                         "eerste": i18n.datum(taal, r["eerste_datum"]) or ""}
                                        for r in varianten["rijen"]]} if varianten else None,
                "formuleringen": [{"tekst": _kort(f["tekst"], 400), "taal": f["taal"], "richting": f["richting"]}
                                  for f in p["formuleringen"]],
                # de contextkaarten naast de factcheck (PLAN #34.2an, SPECS E9.S21)
                "context": context(taal, p),
                "dossiers": [{"sleutel": d["sleutel"], "naam": d["naam"][taal], "href": i18n.pad(taal, "dossiers", d["sleutel"])}
                             for d in pub.dossiers_van(nummer)],
                "thema": ding(p["thema"], p["thema"]) if p["thema"] and themanaam(taal, p["thema"]) else None,
                "onderdeel": ding(p["onderdeel"], p["thema"], p["onderdeel"])
                if p["thema"] and p["onderdeel"] and themanaam(taal, p["thema"], p["onderdeel"]) else None,
                # het tweede thema, zoals de pagina het noemt (alleen naast een eerste)
                "tweede": ding(p["tweede"], p["tweede"])
                if p["thema"] and themanaam(taal, p["thema"]) and p["tweede"] and themanaam(taal, p["tweede"]) else None,
                "land": {"code": p["land"], "naam": landnaam(taal, p["land"]), "href": lijst_url(taal, {"land": p["land"]})}
                if p["land"] and landnaam(taal, p["land"]) else None,
                "kenmerken": kenmerken(taal, p.get("kenmerk")),
                "namen": [{"nummer": n["nummer"], "naam": n["naam"][taal], "soort": n["soort"],
                           "href": i18n.pad(taal, "names", n["nummer"])} for n in pub.namen_van(nummer)],
            }
            # hoe de bewering nog meer luidt: de andere formuleringen uit dezelfde groep, dan de versies uit een dossier
            ook_als = [{"tekst": f["tekst"], "taal": f["taal"], "richting": f["richting"]} for f in gegevens["formuleringen"]]
            if gegevens["varianten"]:
                ook_als += [{"tekst": r["tekst"], "taal": r["taal"], "richting": r["richting"]}
                            for r in gegevens["varianten"]["rijen"]]
            gegevens["omveld"] = omveld(taal, p, ook_als, pub.toeschrijvingen(nummer),
                                        {d["sleutel"]: d for d in pub.dossiers_van(nummer)})
            # de checks van dezelfde bewering elders: voor de bronnen in de kop en voor Ook gecheckt door (#34.2bp)
            zelfde = pub.zelfde(nummer, taal)
            p["ook_checks"] = [k for r in zelfde for k in r["checks_lijst"]]
            # de kern van de eerste stap naar zoekmachines (B73 punt 5, PLAN #34.2bt): meer dan één redactie, Ook gecheckt
            # door, of in een dossier; dezelfde regel als `db._sitemap_waar`
            gegevens["vindbaar"]["kern"] = p["redacties"] > 1 or bool(zelfde) or bool(pub.dossiers_van(nummer))
            # maatregel 2 (#34.2bw): in geen stand naar een zoekmachine; lezen kan iedereen
            gegevens["vindbaar"]["afgeschermd"] = p["afgeschermd"]
            gegevens["kop"] = kopgegevens(taal, nummer, p, gegevens)
            # een fout melden (PLAN #34.2at, SPECS E9.S24): een mail met alleen wat de machine op deze pagina deed
            gegevens["melden"] = melden(taal, nummer, {
                "melden_vertaling": bool(v and not v.get("normaal")), "melden_thema": bool(gegevens["thema"]),
                "melden_land": bool(gegevens["land"]), "melden_namen": bool(gegevens["namen"]),
                "melden_kenmerk": bool(gegevens["kenmerken"])})
            # Ook gecheckt door (#34.2bp, SPECS E9.S31): de checks van de pagina's met dezelfde bewering bij een andere
            # redactie, elk met haar eigen oordeel en de bewering zoals die pagina haar toont; de dichtstbijzijnde eerst
            ook = lokaal_eerst([{**k, "_rij": rij_gegevens(taal, r)} for r in zelfde for k in r["checks_lijst"]],
                               taal, p["taal"])
            namen = list(dict.fromkeys(k["redactie"] for k in ook))
            gegevens["ook_gecheckt"] = {
                "regel": t("ook_gecheckt_regel", namen=i18n.opsomming(taal, namen)),
                "telling": t("redacties_een" if len(namen) == 1 else "redacties_meer", n=i18n.getal(taal, len(namen))),
                "checks": [{**check_gegevens(taal, k), "bewering": k["_rij"]} for k in ook]} if ook else None
            # wat alle redacties zeggen (PLAN #34.2cd, SPECS E9.S31 AC7): op deze pagina en onder Ook gecheckt door samen
            gegevens["eens"] = eens(taal, p["checks_lijst"], ook)
            # Lijkt op (#34.2p): wat al bij Komt ook voor als of bij Ook gecheckt door staat, niet nog eens
            al = {r["nummer"] for r in (varianten or {}).get("rijen", [])} | {r["nummer"] for r in zelfde}
            lijkt = [rij_gegevens(taal, r) for r in pub.lijkt_op(nummer, taal) if r["nummer"] not in al]
            per_label = Counter((r["label"], r["soort"]) for r in lijkt)
            gegevens["lijkt_op"] = {
                "telling": t("lijkt_op_een" if len(lijkt) == 1 else "lijkt_op_meer", n=i18n.getal(taal, len(lijkt))),
                "per_label": [{"label": label, "soort": soort, "n": n} for (label, soort), n in per_label.most_common()],
                "rijen": lijkt} if lijkt else None
            gegevens["waarom"] = waarom_gegevens(taal, nummer, pub.waarom(nummer))
            gegevens["samenvatting"] = samenvatting_gegevens(taal, p["checks_lijst"], pub.samenvatting(nummer, taal, p["taal"]))
            # een eigen factcheck (#37.4): de site gaat meteen naar de check zelf
            if eigen := eigen_href(nummer, taal):
                gegevens["eigen_href"] = eigen
            return json_antwoord(gegevens)
        return antwoord

    def actueel(taal: str) -> dict:
        """De dag van de uitgave en van de nieuwste check erin (PLAN #34.2bz)."""
        uitgave, factcheck = db.uitgave_dag(pub.release), pub.nieuwste_datum[:10]
        return {"uitgave": uitgave, "uitgave_tekst": i18n.datum(taal, uitgave), "factcheck": factcheck,
                "factcheck_tekst": i18n.datum(taal, factcheck)}

    def radar(taal: str) -> dict | None:
        """Factiz Radar in het menu en op de start (PLAN #37.4, PO 2026-11-19: "Ja, bouw het"): hoeveel eigen checks er in
        deze taal gepubliceerd zijn, hoeveel van de zeven dagen tot en met de dag van de uitgave (dan pulseren de ringen),
        en de nieuwste; zonder gepubliceerde check niets. De dag van de uitgave, niet die van vandaag, zodat het antwoord
        bij een uitgave vastligt."""
        checks = [x for c in pub.eigen if not c["concept"] and (x := eigen_in(c, taal))]
        if not checks:
            return None
        dag = db.uitgave_dag(pub.release)

        def nieuw(c: dict) -> bool:
            g = (c.get("gepubliceerd") or "")[:10]
            try:
                return 0 <= (date.fromisoformat(dag) - date.fromisoformat(g)).days < 7
            except ValueError:
                return False
        n_nieuw = sum(1 for c in checks if nieuw(c))
        eerste = sorted(checks, key=lambda c: c.get("gepubliceerd") or "", reverse=True)[0]
        return {"href": i18n.pad(taal, "radar"), "aantal": len(checks), "nieuw": n_nieuw,
                "aantal_tekst": i18n.tekst(taal, "radar_aantal_een" if len(checks) == 1 else "radar_aantal",
                                           n=i18n.getal(taal, len(checks))),
                "nieuw_tekst": i18n.tekst(taal, "radar_nieuw_een" if n_nieuw == 1 else "radar_nieuw",
                                          n=i18n.getal(taal, n_nieuw)) if n_nieuw else "",
                "nieuwste": {"kop": eerste["kop"], "href": eerste["paden"][taal]}}

    def dossierkaart(taal: str, d: dict) -> dict:
        """Een dossier als kaart (PLAN #34.2s): dezelfde velden op de start en op het overzicht."""
        return {"sleutel": d["sleutel"], "naam": d["naam"][taal], "soort": d["soort"],
                "soort_tekst": i18n.tekst(taal, "dossier_soort_" + d["soort"]), "thema": d["thema"],
                "href": i18n.pad(taal, "dossiers", d["sleutel"]), "inleiding": _kort(d["inleiding"][taal], 200),
                "aantal": i18n.tekst(taal, "lijst_een" if d["stand"]["factchecks"] == 1 else "lijst_meer",
                                     n=i18n.getal(taal, d["stand"]["factchecks"])),
                "laatste": i18n.datum(taal, d["stand"]["laatste"]) or "", "concept": bool(d.get("concept")),
                "concept_tekst": i18n.tekst(taal, "dossier_concept") if d.get("concept") else ""}

    def api_dossiers(taal: str):
        def antwoord(request: Request) -> Response:
            # Het overzicht als gegevens (PLAN #34.2s): elk dossier van de uitgave, de nieuwste aanvulling boven.
            if not pub.dossiers:
                raise HTTPException(404)
            return json_antwoord({"titel": i18n.tekst(taal, "nav_dossiers"), "inleiding": i18n.tekst(taal, "dossiers_inleiding"),
                                  "laatste_kop": i18n.tekst(taal, "dossier_laatste"),
                                  "dossiers": [dossierkaart(taal, d) for d in pub.dossiers]})
        return antwoord

    def api_dossier(taal: str):
        def antwoord(request: Request) -> Response:
            # Het dossier als gegevens (PLAN #34.2): dezelfde tijdlijn als `dossier_pagina`, per jaar, de nieuwste boven.
            sleutel = request.path_params["sleutel"]
            d = pub.dossier(sleutel)
            if d is None:
                raise HTTPException(404)
            t = lambda s, **w: i18n.tekst(taal, s, **w)
            jaren: list[dict] = []
            for it in pub.tijdlijn(sleutel, taal):
                jaar = it["datum"][:4]
                if not jaren or jaren[-1]["jaar"] != jaar:
                    jaren.append({"jaar": jaar, "kop": jaar or t("dossier_zonder_datum"), "regels": []})
                regel = {"soort": it["soort"], "soort_tekst": t("item_" + it["soort"]), "datum": i18n.datum(taal, it["datum"]) or ""}
                if it.get("rij"):
                    regel["rij"] = {**rij_gegevens(taal, it["rij"]), "redacties": it.get("redacties") or []}
                    if it.get("niveau") in ("waargenomen", "toegeschreven") and it.get("bron"):
                        regel["niveau"] = t("dossier_niveau_" + it["niveau"], bron=it["bron"])
                        regel["url"] = _link(it.get("url"))
                else:
                    regel.update({"titel": it["titel"][taal], "bron": it["bron"], "url": _link(it.get("url"))})
                jaren[-1]["regels"].append(regel)
            s = d["stand"]
            gegevens = {
                "sleutel": sleutel, "naam": d["naam"][taal], "soort": d["soort"], "soort_tekst": t("dossier_soort_" + d["soort"]),
                "deelbeeld": {"src": f"/deelbeeld/{taal}/dossier/{sleutel}.jpg?v={pub.release}",
                              "alt": f"{t('dossier_soort_' + d['soort'])} · {d['naam'][taal]}"},
                "concept": bool(d.get("concept")), "inleiding": d["inleiding"][taal], "thema_sleutel": d["thema"],
                "stand": {"eerste": i18n.datum(taal, s["eerste"]) or t("geen_datum"), "factchecks": i18n.getal(taal, s["factchecks"]),
                          "redacties": i18n.getal(taal, s["redacties"]), "talen": i18n.getal(taal, s["talen"]),
                          "laatste": i18n.datum(taal, s["laatste"]) or t("geen_datum")},
                "vastgesteld": {"door": d["vastgesteld"]["door"], "datum": i18n.datum(taal, d["vastgesteld"].get("datum")) or "",
                                "url": _link(d["vastgesteld"].get("url"))} if d.get("vastgesteld") else None,
                "jaren": jaren,
                "thema": {"naam": themanaam(taal, d["thema"]), "href": i18n.pad(taal, "themes", d["thema"])}
                if d["thema"] and themanaam(taal, d["thema"]) else None,
                # het onderdeel van het thema, zoals de pagina het noemt
                "onderdeel": {"naam": themanaam(taal, d["thema"], d["onderdeel"]),
                              "href": i18n.pad(taal, "themes", d["thema"], d["onderdeel"])}
                if d["thema"] and themanaam(taal, d["thema"]) and d.get("onderdeel")
                and themanaam(taal, d["thema"], d["onderdeel"]) else None,
                "verwant": [{"sleutel": w["sleutel"], "naam": w["naam"][taal], "href": i18n.pad(taal, "dossiers", w["sleutel"])}
                            for w in d.get("verwant") or []],
                # begrippen om verder te zoeken (#34.2ca, SPECS E9.S7 AC9): elk een zoekvraag naar het archief
                "begrippen": d["begrippen"].get(taal) or d["begrippen"].get("en") or [],
            }
            return json_antwoord(gegevens)
        return antwoord

    def radargroep(c: dict) -> str:
        """Waar een eigen check op de Radar van een taal staat (B85, PO 2026-11-19): uit die taal zelf, internationaal
        (een vertaling met reikwijdte internationaal), of uit een ander land."""
        if "brontaal" not in c:
            return "hier"
        return "internationaal" if c.get("reikwijdte") == "internationaal" else "elders"

    def eigen_vindbaar(c: dict, taal: str) -> bool:
        """Zoekmachines zien een eigen check in haar eigen taal en in een vertaling die de redactie las (PLAN #37.11); een
        concept nooit. `publiceren.eigen_adressen` zette de talen erbij."""
        return not c["concept"] and taal in (c.get("vindbaar_in") or [])

    def eigenrij(taal: str, c: dict) -> dict:
        """Een eigen factcheck als kaart, met dezelfde velden als een rij van het archief (`rij_gegevens`, `Rij.jsx`; PO
        2026-11-21: "zullen we alles een beetje gelijk trekken"): het zegel met het oordeel, de datum, de kop van de check
        (wat we vonden), en het thema, het land, de soort en de vorm van haar pagina in het archief. Een vertaling krijgt de
        regel met het origineel eronder, een concept zegt dat het er een is."""
        t = lambda s, **w: i18n.tekst(taal, s, **w)
        nummer = next((nr for nr, sl in pub.eigen_paginas.items() if sl == c["sleutel"]), "")
        p = pub.pagina(nummer) if nummer else None
        thema, land = (p or {}).get("thema"), (p or {}).get("land")
        bron = next((x for x in pub.eigen if x["sleutel"] == c["sleutel"]), c) if "brontaal" in c else None
        return {"nummer": nummer, "href": c["paden"][taal], "eigen": t("eigen_oordeel_" + c["oordeel"]),
                "soort": p["label"] if p and p["label"] in i18n.LABELS else "geen",
                "datum": i18n.datum(taal, c.get("gepubliceerd") or "") or "",
                "tekst": c["kop"], "taal": taal, "richting": i18n.richting(taal),
                "origineel": {"regel": vertaalregel(taal, c["brontaal"], taal), "tekst": _kort(bron["kop"], 140),
                              "taal": c["brontaal"], "richting": i18n.richting(c["brontaal"])} if bron else None,
                "thema": {"sleutel": thema, "naam": themanaam(taal, thema)} if thema and themanaam(taal, thema) else None,
                "land": {"code": land, "naam": landnaam(taal, land)} if land and landnaam(taal, land) else None,
                "kenmerken": kenmerken(taal, (p or {}).get("kenmerk")),
                "concept": t("eigen_concept") if c["concept"] else ""}

    def eigenkaart(taal: str, c: dict) -> dict:
        """Een eigen factcheck in een lijst (#37.4), met haar adres in deze taal (PLAN #37.11) en haar kaart (`eigenrij`)."""
        return {"sleutel": c["sleutel"], "kop": c["kop"], "oordeel": c["oordeel"], "rij": eigenrij(taal, c),
                "oordeel_tekst": i18n.tekst(taal, "eigen_oordeel_" + c["oordeel"]),
                "datum": i18n.datum(taal, c.get("gepubliceerd") or "") or "", "gepubliceerd_iso": c.get("gepubliceerd") or "",
                "href": c["paden"][taal], "concept": c["concept"], "vertaald": "brontaal" in c,
                "vindbaar": eigen_vindbaar(c, taal), "groep": radargroep(c)}

    def maandpad(taal: str, maand: str) -> str:
        """De Radar van een maand (`2026-11`): `/nl/radar/2026/11/`."""
        return i18n.pad(taal, "radar", *maand.split("-"))

    def radar_zijkolom(taal: str, checks: list[dict]) -> dict:
        """De zijkolom van Factiz Radar (PLAN #37.4, PO 2026-11-19: "Ja, bouw het"): hoe het werkt, wat we vonden (de
        tellingen van het archief voor de redactie Factiz, zodat elke link precies die checks toont), de dossiers waar de
        checks in staan, en een tip. Alles uit de uitgave; de volgorde ligt vast: meeste eerst, dan op naam of plek."""
        t = lambda s, **w: i18n.tekst(taal, s, **w)
        tel = pub.facetten_van(redactie=EIGEN_REDACTIE)

        def rij(wat: str, naam) -> list[dict]:
            paren_ = sorted((tel.get(wat) or {}).items(), key=lambda x: (-x[1], x[0]))
            return [{"naam": naam(w), "aantal": i18n.getal(taal, n),
                     "href": lijst_url(taal, {"redactie": EIGEN_REDACTIE, wat: (w,)})} for w, n in paren_ if n]
        plek = {d["sleutel"]: i for i, d in enumerate(pub.dossiers)}
        per: dict[str, list] = {}
        for c in checks:
            if c["concept"]:
                continue
            nummer = next((nr for nr, sl in pub.eigen_paginas.items() if sl == c["sleutel"]), "")
            for d in pub.dossiers_van(nummer) if nummer else []:
                per.setdefault(d["sleutel"], [d, 0])[1] += 1
        dossiers = sorted(per.values(), key=lambda x: (-x[1], plek.get(x[0]["sleutel"], 0)))
        onderwerp = quote(t("radar_tip_onderwerp"), safe="")
        # de maanden met een check in deze taal, de nieuwste eerst (PLAN #37.11): de weg naar de Radar per maand
        per_maand: dict[str, int] = {}
        for c in checks:
            per_maand[c["maand"]] = per_maand.get(c["maand"], 0) + 1
        return {"maanden": [{"naam": i18n.maand_jaar(taal, m), "href": maandpad(taal, m), "aantal": i18n.getal(taal, n)}
                            for m, n in sorted(per_maand.items(), reverse=True)],
                "oordelen": rij("oordeel", lambda w: i18n.stempel(taal, w)),
                "soorten": rij("soort", lambda w: t(f"soort_{w}")),
                "vormen": rij("vorm", lambda w: t(f"vorm_{w}")),
                "dossiers": [{"naam": d["naam"][taal], "href": i18n.pad(taal, "dossiers", d["sleutel"]),
                              "aantal": i18n.getal(taal, n)} for d, n in dossiers],
                "archief": lijst_url(taal, {"redactie": EIGEN_REDACTIE}),
                "tip": {"href": f"mailto:{CONTACT}?subject={onderwerp}", "adres": CONTACT}}

    def eigen_lijst(taal: str, jaar: str = "", maand: str = "") -> dict:
        """De eigen factchecks in de taal van de site (#37.4, B82), alle of van één jaar of maand (PLAN #37.11); in een taal
        of periode zonder check is er geen lijst. De zijkolom telt altijd de hele Radar."""
        orde = {"hier": 0, "internationaal": 1, "elders": 2}
        alle = sorted((x for c in pub.eigen if (x := eigen_in(c, taal))), key=lambda c: orde[radargroep(c)])
        periode = f"{jaar}-{maand}" if maand else jaar
        checks = [c for c in alle if c["maand"].startswith(periode)] if jaar else alle
        if not checks:
            raise HTTPException(404)
        return {"titel": i18n.tekst(taal, "eigen_titel"), "inleiding": i18n.tekst(taal, "eigen_inleiding"),
                "periode": {"tekst": i18n.maand_jaar(taal, periode) if maand else jaar, "jaar": jaar,
                            "jaar_href": i18n.pad(taal, "radar", jaar), "maand": maand,
                            "href": i18n.pad(taal, "radar", jaar, maand)} if jaar else None,
                "checks": [eigenkaart(taal, c) for c in checks], "zijkolom": radar_zijkolom(taal, alle)}

    def api_eigen_lijst(taal: str):
        def antwoord(request: Request) -> Response:
            return json_antwoord(eigen_lijst(taal))
        return antwoord

    def _periode(jaar: str, maand: str = "00") -> bool:
        """Een jaar van vier cijfers en een maand van twee (01 tot 12); `00` als er geen maand is."""
        return (len(jaar) == 4 and jaar.isascii() and jaar.isdigit() and len(maand) == 2 and maand.isascii()
                and maand.isdigit() and int(maand) <= 12)

    def api_eigen_periode(taal: str):
        def antwoord(request: Request) -> Response:
            # De Radar van een maand, of de check op haar adres (PLAN #37.11): `/api/nl/eigen/2026/11[/<naam>]`. De naam
            # van een andere taal van dezelfde check stuurt door naar de naam in deze taal.
            jaar, maand = request.path_params["jaar"], request.path_params["maand"]
            naam = request.path_params.get("naam")
            if not _periode(jaar, maand) or maand == "00":
                raise HTTPException(404)
            if naam is None:
                return json_antwoord(eigen_lijst(taal, jaar, maand))
            staart = f"/radar/{jaar}/{maand}/{naam}/"
            c = next((c for c in pub.eigen if any(p.endswith(staart) for p in (c.get("paden") or {}).values())), None)
            if c is None or taal not in c["paden"]:
                raise HTTPException(404)
            if not c["paden"][taal].endswith(staart):
                return json_antwoord({"doorsturen": c["paden"][taal]})
            return eigen_antwoord(taal, c["sleutel"])
        return antwoord

    def api_eigen(taal: str):
        def antwoord(request: Request) -> Response:
            # Een eigen factcheck op haar werknaam (het oude adres, #37.4), of de Radar van een jaar (PLAN #37.11)
            sleutel = request.path_params["sleutel"]
            if sleutel[:1].isdigit():
                if not _periode(sleutel):
                    raise HTTPException(404)
                return json_antwoord(eigen_lijst(taal, sleutel))
            return eigen_antwoord(taal, sleutel)
        return antwoord

    def eigen_antwoord(taal: str, sleutel: str) -> Response:
        # Een eigen factcheck (#37.4, B82, DESIGN §4x), in haar eigen taal of als machinevertaling (#37.8, B85).
        c = next((x for c in pub.eigen if c["sleutel"] == sleutel and (x := eigen_in(c, taal))), None)
        if c is None or c["oordeel"] not in EIGEN_OORDELEN:
            raise HTTPException(404)
        t = lambda s, **w: i18n.tekst(taal, s, **w)
        oordeel = t("eigen_oordeel_" + c["oordeel"])
        kenmerken = (([t("soort_" + c["soort"])] if c.get("soort") else [])
                     + ([t("vorm_" + c["vorm"])] if c.get("vorm") else []))
        posts = c.get("posts") or 0
        gegevens = {
            "sleutel": c["sleutel"], "taal": taal, "brontaal": c.get("brontaal", c["taal"]), "concept": c["concept"],
            # haar adres in deze taal en in elke taal waarin ze er is, en waar zoekmachines haar zien (PLAN #37.11)
            "href": c["paden"][taal], "paden": c["paden"],
            "vindbaar_in": [] if c["concept"] else list(c.get("vindbaar_in") or []),
            "vindbaar": eigen_vindbaar(c, taal),
            "maand": {"tekst": i18n.maand_jaar(taal, c["maand"]), "href": maandpad(taal, c["maand"])},
            # een machinevertaling zegt dat ze er een is, en of de redactie haar las, met de link naar het origineel
            "vertaling": {"tekst": t("eigen_vertaling_nagelezen" if c["vertaling_nagelezen"] else "eigen_vertaling",
                                     bron=i18n.taalnaam_in(taal, c["brontaal"])),
                          "origineel": c["paden"][c["brontaal"]], "link": t("eigen_origineel"),
                          "nagelezen": c["vertaling_nagelezen"]}
            if "brontaal" in c else None,
            # haar pagina in het archief, voor de zijbalk, het thema en de verbanden van elke factcheck (PO 2026-11-19)
            "nummer": next((nr for nr, sl in pub.eigen_paginas.items() if sl == c["sleutel"]), ""),
            "kop": c["kop"], "oordeel": c["oordeel"], "oordeel_tekst": oordeel, "oordeel_zin": stukken(c["oordeel_zin"]),
            "kenmerken": " · ".join(kenmerken), "bewering": c["bewering"], "platform": c["platform"],
            "eerst_gezien": i18n.datum(taal, c["eerst_gezien"]) or "",
            "posts_tekst": t("eigen_post") if posts == 1 else t("eigen_posts", n=i18n.getal(taal, posts)) if posts else "",
            "bereik": c.get("bereik") or "",
            "kort": stukken(c["kort"]), "tekst": alineas(c["tekst"]), "niet_weten": alineas(c.get("niet_weten") or ""),
            "beelden": [{"rol": b["rol"], "stempel": oordeel if b["rol"] == "rondgaat" and b.get("stempel") else "",
                         "bijschrift": b.get("bijschrift") or "", "alt": b.get("alt") or "", "link": _link(b.get("link")),
                         "host": _host(_link(b.get("link"))), "pad": b.get("pad") or "",
                         "breedte": b.get("breedte") or 0, "hoogte": b.get("hoogte") or 0} for b in c.get("beeld") or []],
            "rekensom": [{"geval": r["geval"], "som": r["som"], "uitkomst": r["uitkomst"]} for r in c.get("rekensom") or []],
            "tijdlijn": [{"datum": i18n.datum(taal, r["datum"]) or "", "tijd": r.get("tijd") or "",
                          "wat": " ".join(re.sub(r"\s*\[[0-9]+\]", "", r["wat"]).split())} for r in c.get("tijdlijn") or []],
            "bronnen": [{"nr": b["nr"], "soort_tekst": t("eigen_bron_" + b["soort"]), "uitgever": b["uitgever"],
                         "titel": b["titel"], "datum": i18n.datum(taal, b["datum"]) or "",
                         "url": "" if b.get("prive") else _link(b.get("url")),
                         "host": "" if b.get("prive") else _host(_link(b.get("url"))),
                         "archief": _link(b.get("archief")), "prive": bool(b.get("prive")),
                         # een post die niet meer te zien is, zonder kopie (B84), of waarvan geen kopie te maken was
                         "weg": bool(b.get("weg")), "geen_kopie": str(b.get("geen_kopie") or "")}
                        for b in c["bron"]],
            "auteur": c["auteur"], "nalezer": c.get("nalezer") or "",
            # in welke taal de redactie een check in een andere taal las (B85 punt 5)
            "nagelezen_in": c.get("nagelezen_in") or "",
            "gepubliceerd": i18n.datum(taal, c.get("gepubliceerd") or "") or "",
            "gepubliceerd_iso": c.get("gepubliceerd") or "",
            "nog_doen": [stukken(n) for n in c.get("nog_doen") or []] if c["concept"] else [],
            # wat nog uit te zoeken is, ook bij een gepubliceerde check, met de oproep om bij te dragen (B84)
            "nog_uitzoeken": list(c.get("nog_uitzoeken") or []),
            "bijdragen": {"href": f"mailto:{CONTACT}?subject={quote(t('eigen_bijdragen_onderwerp', kop=c['kop']), safe='')}",
                          "adres": CONTACT},
        }
        return json_antwoord(gegevens)

    def api_sitemap(taal: str):
        def antwoord(request: Request) -> Response:
            # De factchecks voor de sitemaps per taal en stand (1, 2 of 3), en de namen (PLAN #34.2bt, SPECS E9.S8 AC4): de site maakt er
            # de sitemaps van; welke stand geldt, weet alleen de site. Elke andere vraag: niet gevonden.
            vraag = request.query_params
            sleutels = set(vraag.keys())
            if len(vraag.multi_items()) != len(sleutels):
                raise HTTPException(404)
            if sleutels == {"soort"}:
                if vraag["soort"] != "namen" or not pub.heeft_namen:
                    raise HTTPException(404)
                return json_antwoord({"regels": [{"href": i18n.pad(taal, "names", q)} for q in pub.sitemap_namen()]})
            if "stand" not in sleutels or sleutels - {"stand", "deel"} or vraag["stand"] not in ("1", "2", "3"):
                raise HTTPException(404)
            stand = int(vraag["stand"])
            totaal = pub.sitemap_telling(taal, stand)
            delen = -(-totaal // db.SITEMAP_DEEL)
            if "deel" not in sleutels:
                return json_antwoord({"stand": stand, "per_deel": db.SITEMAP_DEEL, "totaal": totaal, "delen": delen})
            deel = vraag["deel"]
            if not deel.isdigit() or str(int(deel)) != deel or int(deel) >= delen:
                raise HTTPException(404)
            return json_antwoord({"stand": stand, "deel": int(deel), "regels": [
                {"href": i18n.pad(taal, "fact-checks", nummer), "lastmod": datum}
                for nummer, datum in pub.sitemap_deel(taal, stand, int(deel))]})
        return antwoord

    def api_namen(taal: str):
        def antwoord(request: Request) -> Response:
            # Het register als gegevens (PLAN #34.2r): dezelfde letters en namen als `namen_pagina`, nooit een telling.
            if not pub.heeft_namen:
                raise HTTPException(404)
            vraag = request.query_params
            if set(vraag.keys()) - {"soort", "letter"} or len(vraag.multi_items()) != len(vraag.keys()):
                raise HTTPException(404)
            soort, letter = vraag.get("soort"), vraag.get("letter")
            if (soort is None) != (letter is None) or (soort is not None and (
                    soort not in db.NAAMSOORTEN or letter not in pub.letters(taal, soort))):
                raise HTTPException(404)
            teken = lambda x: "#" if x == "0" else x.upper()
            groepen = [{"soort": s, "kop": i18n.tekst(taal, "namen_soort_" + s), "letters": [
                {"letter": x, "teken": teken(x), "label": i18n.tekst(taal, "namen_andere") if x == "0" else "",
                 "href": i18n.pad(taal, "names") + "?" + urlencode([("letter", x), ("soort", s)])}
                for x in pub.letters(taal, s)]} for s in db.NAAMSOORTEN]
            return json_antwoord({
                "groepen": [g for g in groepen if g["letters"]], "concept": pub.namen_concept,
                "gekozen": {"soort": soort, "letter": letter, "teken": teken(letter)} if soort else None,
                "namen": [{"nummer": n["nummer"], "naam": n["naam"][taal], "href": i18n.pad(taal, "names", n["nummer"])}
                          for n in pub.register(taal, soort, letter)] if soort else []})
        return antwoord

    def api_naam(taal: str):
        def antwoord(request: Request) -> Response:
            # Een naam als gegevens (PLAN #34.2r): een ingang, geen oordeel; dezelfde rijen als `naam_pagina`.
            n = pub.naam(request.path_params["nummer"])
            if n is None:
                raise HTTPException(404)
            rijen, totaal = pub.lijst(vertaal=taal, naam=n["nummer"])
            return json_antwoord({
                "nummer": n["nummer"], "naam": n["naam"][taal], "soort": n["soort"],
                "soort_tekst": i18n.tekst(taal, "naam_soort_" + n["soort"]), "concept": pub.namen_concept,
                "zin": i18n.tekst(taal, "naam_zin"), "bedoeld": i18n.tekst(taal, "naam_bedoeld"),
                "omschrijving": i18n.tekst(taal, "naam_omschrijving", naam=n["naam"][taal]),
                "wikidata": f"https://www.wikidata.org/wiki/{n['nummer']}",
                "aantal": i18n.tekst(taal, "lijst_een" if totaal == 1 else "lijst_meer", n=i18n.getal(taal, totaal)),
                "rijen": [rij_gegevens(taal, r) for r in rijen], "alle": lijst_url(taal, {"naam": n["nummer"]}),
                "alle_tekst": i18n.tekst(taal, "naam_alle")})
        return antwoord

    def themakaart(taal: str, th: dict) -> dict:
        """Een thema als kaart (PLAN #34.2u): naam, aantal en link, met de onderdelen erbij."""
        return {"sleutel": th["sleutel"], "naam": th["naam"][taal], "href": i18n.pad(taal, "themes", th["sleutel"]),
                "aantal": i18n.tekst(taal, "lijst_een" if th["aantal"] == 1 else "lijst_meer", n=i18n.getal(taal, th["aantal"])),
                "onderdelen": [{"sleutel": o["sleutel"], "naam": o["naam"][taal], "aantal": i18n.getal(taal, o["aantal"]),
                                "href": i18n.pad(taal, "themes", th["sleutel"], o["sleutel"])} for o in th["onderdelen"]]}

    def api_themas(taal: str):
        def antwoord(request: Request) -> Response:
            # Het overzicht van de thema's als gegevens (PLAN #34.2u): dezelfde thema's als `themas_pagina`.
            if not pub.themas:
                raise HTTPException(404)
            return json_antwoord({"titel": i18n.tekst(taal, "nav_themas"), "inleiding": i18n.tekst(taal, "themas_inleiding"),
                                  "themas": [themakaart(taal, th) for th in pub.themas]})
        return antwoord

    def api_thema(taal: str):
        def antwoord(request: Request) -> Response:
            # Een thema of onderdeel als gegevens (PLAN #34.2u): dezelfde rijen en dossiers als `thema_pagina`.
            sleutel, deel_sleutel = request.path_params["thema"], request.path_params.get("onderdeel")
            thema = pub.thema(sleutel)
            deel = pub.deel(sleutel, deel_sleutel) if thema and deel_sleutel else None
            if thema is None or (deel_sleutel is not None and deel is None):
                raise HTTPException(404)
            filters = {"thema": sleutel, **({"onderdeel": deel_sleutel} if deel else {})}
            rijen, totaal = pub.lijst(vertaal=taal, **filters)
            kop = deel["naam"][taal] if deel else thema["naam"][taal]
            kaart = themakaart(taal, thema)
            return json_antwoord({
                "sleutel": sleutel, "kop": kop, "thema_naam": thema["naam"][taal], "thema_href": kaart["href"],
                "deel": {"sleutel": deel_sleutel, "naam": deel["naam"][taal]} if deel else None,
                "kicker": i18n.tekst(taal, "nav_themas"), "omschrijving": i18n.tekst(taal, "thema_omschrijving", naam=kop),
                # het deelplaatje (PLAN #34.2ar): getekend als iemand het vraagt, met de versie van de uitgave in het adres
                "deelbeeld": {"src": f"/deelbeeld/{taal}/thema/{sleutel}{'/' + deel_sleutel if deel else ''}.jpg?v={pub.release}",
                              "alt": f"{thema['naam'][taal] if deel else i18n.tekst(taal, 'nav_themas')} · {kop}"},
                "aantal": i18n.tekst(taal, "lijst_een" if totaal == 1 else "lijst_meer", n=i18n.getal(taal, totaal)),
                "alle": lijst_url(taal, filters), "alle_tekst": i18n.tekst(taal, "thema_alle"),
                "onderdelen_kop": i18n.tekst(taal, "thema_onderdelen"), "onderdelen": [] if deel else kaart["onderdelen"],
                "dossiers": [dossierkaart(taal, d) for d in pub.dossiers_bij(sleutel, deel_sleutel if deel else None)],
                "rijen": [rij_gegevens(taal, r) for r in rijen]})
        return antwoord

    def api_verkennen(taal: str):
        def antwoord(request: Request) -> Response:
            # Verkennen (PLAN #34.2ah, SPECS E9.S17): de ring van thema's, de tijd en het waar, aan één keuze. Eén adres per
            # weergave: alleen `thema` en, bij een thema, `maat=verhouding`; al het andere bestaat niet.
            vraag = request.query_params
            if set(vraag.keys()) - {"thema", "maat"} or len(vraag.multi_items()) != len(vraag.keys()):
                raise HTTPException(404)
            sleutel, maat = vraag.get("thema"), vraag.get("maat")
            thema = pub.thema(sleutel) if sleutel is not None else None
            if (sleutel is not None and thema is None) or (maat is not None and (maat != "verhouding" or thema is None)):
                raise HTTPException(404)
            basis = i18n.pad(taal, "explore")
            naam = thema["naam"][taal] if thema else ""
            tal = lambda n: i18n.tekst(taal, "lijst_een" if n == 1 else "lijst_meer", n=i18n.getal(taal, n))  # noqa: E731
            filters = {"thema": sleutel} if thema else {}
            g = pub.verkennen(sleutel if thema else None)
            met_thema = pub.met_thema if pub.themas else 0

            ring = {"kop": i18n.tekst(taal, "verken_ring_kop"), "kies": i18n.tekst(taal, "verken_kies"),
                    "alles": i18n.tekst(taal, "verken_alles"), "totaal": met_thema,
                    "totaal_tekst": i18n.tekst(taal, "verken_met_thema", n=i18n.getal(taal, met_thema)),
                    "regel": i18n.tekst(taal, "verken_van_totaal", n=i18n.getal(taal, thema["aantal"]),
                                        totaal=i18n.getal(taal, met_thema)) if thema else "",
                    "themas": [{"sleutel": th["sleutel"], "naam": th["naam"][taal], "aantal": th["aantal"],
                                "aantal_tekst": tal(th["aantal"]), "getal": i18n.getal(taal, th["aantal"]),
                                "href": f"{basis}?thema={th['sleutel']}",
                                "aan": th["sleutel"] == sleutel} for th in pub.themas]}
            gekozen = {"sleutel": sleutel, "naam": naam, "aantal": thema["aantal"], "aantal_tekst": tal(thema["aantal"]),
                       "lijst": lijst_url(taal, filters), "lijst_tekst": i18n.tekst(taal, "verken_naar_lijst", thema=naam),
                       "onderdelen_kop": i18n.tekst(taal, "thema_onderdelen"),
                       "onderdelen": [{"sleutel": o["sleutel"], "naam": o["naam"][taal], "aantal": o["aantal"],
                                       "aantal_tekst": tal(o["aantal"]), "getal": i18n.getal(taal, o["aantal"]),
                                       "href": i18n.pad(taal, "themes", sleutel, o["sleutel"])}
                                      for o in thema["onderdelen"]]} if thema else None

            nieuwste = pub.nieuwste_datum
            noot = []
            if g["eerder"]:
                noot.append(i18n.tekst(taal, "verken_eerder", jaar=g["jaren"][0][0], n=i18n.getal(taal, g["eerder"])))
            if g["zonder_datum"]:
                noot.append(i18n.tekst(taal, "verken_zonder_datum", n=i18n.getal(taal, g["zonder_datum"])))
            tijd = {"kop": i18n.tekst(taal, "verken_tijd_kop"),
                    "regel": i18n.tekst(taal, "verken_tijd_regel", thema=naam) if thema else i18n.tekst(taal, "verken_tijd_regel_alles"),
                    "jaren": [{"jaar": j, "aantal": n, "aantal_tekst": tal(n), "getal": i18n.getal(taal, n),
                               "lopend": j == nieuwste[:4],
                               "href": lijst_url(taal, {**filters, "jaar": j})} for j, n in g["jaren"]],
                    "eerder": g["eerder"], "zonder_datum": g["zonder_datum"], "noot": " ".join(noot)}

            def tiental(x: float) -> str:
                tekst = f"{x:.1f}"
                return tekst if taal == "en" else tekst.replace(".", ",")

            if maat == "verhouding":
                landen = [{"code": c, "naam": landnaam(taal, c), "aantal": a, "van": van, "waarde": f,
                           "tekst": i18n.tekst(taal, "verken_verhouding_waarde", x=tiental(f), n=i18n.getal(taal, a),
                                               van=i18n.getal(taal, van)),
                           "href": lijst_url(taal, {**filters, "land": c})} for c, f, a, van in pub.verhoudingen(sleutel)]
                waar_noot = i18n.tekst(taal, "verken_noot_verhouding", thema=naam, land=i18n.getal(taal, db.VERHOUDING_LAND),
                                       min=i18n.getal(taal, db.VERHOUDING_THEMA))
            else:
                rijen = sorted(g["landen"], key=lambda r: (-r[1], landnaam(taal, r[0]).casefold()))[:db.VERKEN_LANDEN]
                landen = [{"code": c, "naam": landnaam(taal, c), "aantal": a, "waarde": a, "tekst": i18n.getal(taal, a),
                           "href": lijst_url(taal, {**filters, "land": c})} for c, a in rijen]
                waar_noot = ""
            # de wereldkaart: elk land met zijn maat en trap, op naam, en de legenda (E9.S20)
            if maat == "verhouding":
                grenzen = VERHOUDING_GRENZEN
                kaart = [{"code": c, "naam": landnaam(taal, c), "waarde": f, "trap": trap(f, grenzen),
                          "tekst": i18n.tekst(taal, "verken_verhouding_waarde", x=tiental(f), n=i18n.getal(taal, a),
                                              van=i18n.getal(taal, van)),
                          "href": lijst_url(taal, {**filters, "land": c})} for c, f, a, van in pub.verhoudingen(sleutel, hoeveel=None)]
                naam_van = lambda x: f"{tiental(x)}×"  # noqa: E731
            else:
                grenzen = grenzen_aantal([a for _, a in g["landen"]])
                kaart = [{"code": c, "naam": landnaam(taal, c), "waarde": a, "trap": trap(a, grenzen), "tekst": i18n.getal(taal, a),
                          "href": lijst_url(taal, {**filters, "land": c})} for c, a in g["landen"] if a]
                naam_van = lambda x: i18n.getal(taal, int(x))  # noqa: E731
            kaart.sort(key=lambda r: (db._alfabet(r["naam"]), r["code"]))
            if maat == "verhouding":
                legenda = ([{"trap": 1, "tekst": i18n.tekst(taal, "verken_trap_onder", x=naam_van(grenzen[0]))}]
                           + [{"trap": i + 2, "tekst": f"{tiental(van)}–{naam_van(tot)}"}
                              for i, (van, tot) in enumerate(zip(grenzen, grenzen[1:]))]
                           + [{"trap": len(grenzen) + 1, "tekst": i18n.tekst(taal, "verken_trap_vanaf", x=naam_van(grenzen[-1]))}])
            elif kaart:
                laagste = min(r["waarde"] for r in kaart)
                randen = [laagste] + list(grenzen)
                legenda = [{"trap": i + 1, "tekst": naam_van(van) if tot - 1 <= van else f"{naam_van(van)}–{naam_van(tot - 1)}"}
                           for i, (van, tot) in enumerate(zip(randen, randen[1:]))]
                legenda.append({"trap": len(randen), "tekst": i18n.tekst(taal, "verken_trap_vanaf", x=naam_van(randen[-1]))})
            else:
                legenda = []
            waar = {"kop": i18n.tekst(taal, "verken_waar_kop"),
                    "kaart": kaart, "legenda": legenda, "alle_kop": i18n.tekst(taal, "verken_alle_landen", n=i18n.getal(taal, len(kaart))),
                    "te_klein": i18n.tekst(taal, "verken_te_klein"), "kaart_bron": i18n.tekst(taal, "verken_kaart_bron"),
                    "kaart_leeg": i18n.tekst(taal, "verken_kaart_leeg"), "kaart_geen": i18n.tekst(taal, "verken_kaart_geen"),
                    "regel": i18n.tekst(taal, "verken_waar_regel", thema=naam) if thema else i18n.tekst(taal, "verken_waar_regel_alles"),
                    "maat": maat or "aantal", "landen": landen, "noot": waar_noot,
                    "gemiddeld": i18n.tekst(taal, "verken_gemiddeld") if maat else "",
                    "leeg": i18n.tekst(taal, "verken_geen_land") if maat and not landen else "",
                    "maten": [{"waarde": w, "naam": i18n.tekst(taal, f"verken_maat_{w}"), "aan": (maat or "aantal") == w,
                               "href": f"{basis}?maat=verhouding&thema={sleutel}" if w == "verhouding" else f"{basis}?thema={sleutel}"}
                              for w in ("aantal", "verhouding")] if thema else []}
            # het netwerk van namen hoort bij Verkennen, en bestaat alleen als de uitgave namen heeft (E9.S18 AC7)
            net = {"href": i18n.pad(taal, "explore", "network"), "titel": i18n.tekst(taal, "netwerk_titel"),
                   "regel": i18n.tekst(taal, "netwerk_open_regel")} if pub.heeft_namen else None
            return json_antwoord({"titel": i18n.tekst(taal, "nav_verkennen"), "inleiding": i18n.tekst(taal, "verken_inleiding"),
                                  "alles_href": basis, "gekozen": gekozen, "ring": ring, "tijd": tijd, "waar": waar,
                                  "netwerk": net})
        return antwoord

    def kort(naam: str) -> str:
        return naam if len(naam) <= LABEL_TEKENS else naam[:LABEL_TEKENS - 1].rstrip() + "…"

    schikkingen: dict[tuple[int, int], dict] = {}
    schikslot = threading.Lock()

    def schikking() -> dict:
        """Waar elke naam van het netwerk staat (E9.S18 AC4): één keer per uitgave en drempel gerekend, met voor een label
        de breedste schrijfwijze over de vijf talen, dus in elke taal dezelfde plek."""
        sleutel = (db.NETWERK_NAMEN, db.NETWERK_SAMEN)
        with schikslot:
            return schikkingen[sleutel] if sleutel in schikkingen else _schik(sleutel)

    def _schik(sleutel: tuple[int, int]) -> dict:
        net = pub.netwerk()
        hoogste = max((a for _, a, _ in net["namen"]), default=1)
        stralen = [4 + 22 * math.sqrt(a / hoogste) for _, a, _ in net["namen"]]
        labels = [max(len(kort(pub.naam(q)["naam"][t])) for t in db.SITETALEN) * LETTERBREEDTE + 6
                  if i < NETWERK_LABELS else 0.0 for i, (q, _, _) in enumerate(net["namen"])]
        volg = {q: i for i, (q, _, _) in enumerate(net["namen"])}
        s = netwerk.schik(stralen, [(volg[a], volg[b], k) for a, b, k in net["randen"]], labels)
        schikkingen[sleutel] = {**s, "stralen": [round(r, 1) for r in stralen], "labels": [w > 0 for w in labels]}
        return schikkingen[sleutel]

    if pub.heeft_namen:
        # het netwerk vooraf, in een eigen draad (een halve seconde tot een seconde): het opstarten wacht er niet op
        threading.Thread(target=schikking, daemon=True).start()

    def context(taal: str, p: dict) -> list[dict]:
        """De contextkaarten van een factcheck (SPECS E9.S21), in vaste volgorde en hoogstens `CONTEXT_MAX`: het dossier,
        waar, de namen, wanneer, soort en vorm, de redactie. Elk alleen met gegevens, elk met een vraag, een zin die
        zegt wat ze telt en een link; dezelfde functies als Verkennen, het netwerk en de dossiers."""
        tal = lambda n: i18n.tekst(taal, "lijst_een" if n == 1 else "lijst_meer", n=i18n.getal(taal, n))  # noqa: E731
        thema = p["thema"] if p.get("thema") and pub.thema(p["thema"]) else None
        themanaam_ = themanaam(taal, thema) if thema else ""
        jaar = (p.get("laatste_datum") or "")[:4]
        verkennen = i18n.pad(taal, "explore")
        kaarten: list[dict] = []

        dossiers = pub.dossiers_van(p["nummer"])
        if dossiers:
            d = dossiers[0]
            jaren = pub.dossier_jaren(d["sleutel"])
            st = d["stand"]
            kaarten.append({
                "soort": "dossier", "vraag": i18n.tekst(taal, "context_dossier_vraag"), "naam": d["naam"][taal],
                "thema": d.get("thema") or "", "jaren": [{"jaar": j, "aantal": n, "aan": j == jaar} for j, n in jaren.items()],
                "zin": i18n.tekst(taal, "context_dossier_zin", n=i18n.getal(taal, st["factchecks"]),
                                  redacties=i18n.getal(taal, st["redacties"]), talen=i18n.getal(taal, st["talen"]),
                                  van=i18n.datum(taal, st["eerste"]), tot=i18n.datum(taal, st["laatste"])),
                "href": i18n.pad(taal, "dossiers", d["sleutel"]), "link": i18n.tekst(taal, "context_dossier_link")})

        land = p.get("land") if p.get("land") and landnaam(taal, p["land"]) else None
        if land:
            alle = dict(pub.facetten["land"]).get(land, 0)
            zin = i18n.tekst(taal, "context_waar_zin", land=landnaam(taal, land), n=tal(alle))
            href = f"{verkennen}?thema={thema}" if thema else verkennen
            if thema:
                binnen = pub.facetten_van(thema=thema)["land"].get(land, 0)
                zin = i18n.tekst(taal, "context_waar_thema", land=landnaam(taal, land), n=tal(alle),
                                 m=i18n.getal(taal, binnen), thema=themanaam_)
                verhouding = next((f for c, f, _, _ in pub.verhoudingen(thema, hoeveel=None) if c == land), None)
                if verhouding is not None:
                    x = f"{verhouding:.1f}" if taal == "en" else f"{verhouding:.1f}".replace(".", ",")
                    zin += " " + i18n.tekst(taal, "context_waar_verhouding", x=f"{x}×")
                    href = f"{verkennen}?maat=verhouding&thema={thema}"
            kaarten.append({"soort": "waar", "vraag": i18n.tekst(taal, "context_waar_vraag"), "code": land,
                            "thema": thema or "", "zin": zin,
                            "href": href, "link": i18n.tekst(taal, "context_waar_link")})

        if pub.heeft_namen:
            net = pub.netwerk()
            in_net = {q for q, _, _ in net["namen"]}
            buren: dict[str, list[tuple[str, int]]] = {}
            for a, b, k in net["randen"]:
                buren.setdefault(a, []).append((b, k))
                buren.setdefault(b, []).append((a, k))
            netwerk_pad = i18n.pad(taal, "explore", "network")
            rijen = []
            for n in pub.namen_van(p["nummer"]):
                if n["nummer"] not in in_net:
                    continue
                top = sorted(buren.get(n["nummer"], []), key=lambda b: (-b[1], db._alfabet(pub.naam(b[0])["naam"][taal])))[:2]
                regel = (i18n.tekst(taal, "context_namen_samen", namen=", ".join(
                    f"{pub.naam(q)['naam'][taal]} ({i18n.getal(taal, k)})" for q, k in top)) if top else
                    i18n.tekst(taal, "context_namen_geen", samen=i18n.getal(taal, db.NETWERK_SAMEN)))
                rijen.append({"naam": n["naam"][taal], "href": f"{netwerk_pad}?naam={n['nummer']}", "regel": regel})
            if rijen:
                kaarten.append({"soort": "namen", "vraag": i18n.tekst(taal, "context_namen_vraag"), "namen": rijen[:3],
                                "noot": i18n.tekst(taal, "context_namen_noot"), "href": netwerk_pad,
                                "link": i18n.tekst(taal, "context_namen_link")})

        if thema:
            g = pub.verkennen(thema)
            if g["jaren"] and any(n for _, n in g["jaren"]):
                piek_jaar, piek = max(g["jaren"], key=lambda r: (r[1], r[0]))
                zin = i18n.tekst(taal, "context_wanneer_zin", thema=themanaam_, n=tal(g["totaal"]), jaar=piek_jaar,
                                 piek=i18n.getal(taal, piek))
                if jaar:
                    zin += " " + i18n.tekst(taal, "context_wanneer_deze", jaar=jaar)
                kaarten.append({"soort": "wanneer", "vraag": i18n.tekst(taal, "context_wanneer_vraag"), "thema": thema,
                                "jaren": [{"jaar": j, "aantal": n, "aan": j == jaar} for j, n in g["jaren"]], "zin": zin,
                                "href": f"{verkennen}?thema={thema}", "link": i18n.tekst(taal, "context_wanneer_link")})

        soort, vorm = p.get("kenmerk") or ("", "")
        if soort or vorm:
            filters = {"thema": thema} if thema else {}
            tellen = pub.facetten_van(**filters) if thema else {w: dict(pub.facetten[w]) for w in ("soort", "vorm")}
            rijen = []
            for wat, waarde in (("soort", soort), ("vorm", vorm)):
                if not waarde:
                    continue
                n = tellen[wat].get(waarde, 0)
                sleutel = f"context_{wat}_{'thema' if thema else 'alle'}"
                rijen.append({"wat": wat, "waarde": waarde, "naam": i18n.tekst(taal, f"{wat}_{waarde}"),
                              "regel": i18n.tekst(taal, "soort_volgens") if wat == "soort" else "",
                              "zin": i18n.tekst(taal, sleutel, n=tal(n), thema=themanaam_),
                              "href": lijst_url(taal, {**filters, wat: (waarde,)})})
            kaarten.append({"soort": "kenmerk", "vraag": i18n.tekst(taal, "context_kenmerk_vraag"), "rijen": rijen})

        if p.get("checks_lijst"):
            redactie = p["checks_lijst"][0]["redactie"]
            n = dict(pub.facetten["redactie"]).get(redactie, 0)
            kaarten.append({"soort": "redactie", "vraag": i18n.tekst(taal, "context_redactie_vraag"), "naam": redactie,
                            "zin": i18n.tekst(taal, "context_redactie_zin", n=tal(n)),
                            "href": lijst_url(taal, {"redactie": redactie}), "link": i18n.tekst(taal, "context_redactie_link")})
        return kaarten[:CONTEXT_MAX]

    def api_netwerk(taal: str):
        def antwoord(request: Request) -> Response:
            # Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18): een naam kiezen licht hem en zijn buren op. Eén adres
            # per weergave: alleen `naam`, en alleen een naam die in het netwerk staat.
            if not pub.heeft_namen:
                raise HTTPException(404)
            vraag = request.query_params
            if set(vraag.keys()) - {"naam"} or len(vraag.multi_items()) != len(vraag.keys()):
                raise HTTPException(404)
            s = schikking()          # eerst de schikking: die wacht op de draad die het netwerk al rekent
            net = pub.netwerk()
            keuze = vraag.get("naam")
            if keuze is not None and keuze not in {q for q, _, _ in net["namen"]}:
                raise HTTPException(404)
            basis = i18n.pad(taal, "explore", "network")
            naam = lambda q: pub.naam(q)["naam"][taal]  # noqa: E731
            tal = lambda n: i18n.tekst(taal, "lijst_een" if n == 1 else "lijst_meer", n=i18n.getal(taal, n))  # noqa: E731
            buren = {(b if a == keuze else a): k for a, b, k in net["randen"] if keuze in (a, b)}
            knopen = [{"id": q, "naam": naam(q), "kort": kort(naam(q)), "soort": pub.naam(q)["soort"], "aantal": a,
                       "aantal_tekst": tal(a), "thema": th, "x": x, "y": y, "r": r, "label": label,
                       "href": f"{basis}?naam={q}", "pagina": i18n.pad(taal, "names", q), "aan": q == keuze,
                       "buur": q in buren}
                      for (q, a, th), (x, y), r, label in zip(net["namen"], s["plek"], s["stralen"], s["labels"])]
            veel = [k for _, _, k in net["randen"]] or [1]
            laag, hoog = min(veel), max(veel)
            randen = [{"a": a, "b": b, "samen": k, "aan": keuze in (a, b),
                       "dikte": round(1 + 3 * (math.log(k / laag) / math.log(hoog / laag) if hoog > laag else 0), 2)}
                      for a, b, k in net["randen"]]
            gekozen = None
            if keuze:
                n = pub.naam(keuze)
                aantal = next(a for q, a, _ in net["namen"] if q == keuze)
                thema = next(th for q, _, th in net["namen"] if q == keuze)
                samen = lambda k: i18n.tekst(taal, "netwerk_samen_een" if k == 1 else "netwerk_samen", n=i18n.getal(taal, k))  # noqa: E731
                gekozen = {
                    "id": keuze, "naam": naam(keuze), "soort_naam": i18n.tekst(taal, "naam_soort_" + n["soort"]),
                    "aantal_tekst": tal(aantal),
                    "thema": {"sleutel": thema, "naam": themanaam(taal, thema)} if thema else None,
                    "thema_regel": i18n.tekst(taal, "netwerk_thema", thema=themanaam(taal, thema)) if thema else "",
                    "pagina": i18n.pad(taal, "names", keuze), "pagina_tekst": i18n.tekst(taal, "netwerk_naar_naam", naam=naam(keuze)),
                    "lijst": lijst_url(taal, {"naam": keuze}), "lijst_tekst": i18n.tekst(taal, "netwerk_naar_lijst", naam=naam(keuze)),
                    "buren_kop": i18n.tekst(taal, "netwerk_buren"),
                    "buren": [{"id": q, "naam": naam(q), "samen": k, "samen_getal": i18n.getal(taal, k), "samen_tekst": samen(k),
                               "href": f"{basis}?naam={q}"}
                              for q, k in sorted(buren.items(), key=lambda b: (-b[1], db._alfabet(naam(b[0]))))],
                    "geen_buren": i18n.tekst(taal, "netwerk_geen_buren", naam=naam(keuze),
                                             samen=i18n.getal(taal, db.NETWERK_SAMEN)) if not buren else ""}
            return json_antwoord({
                "titel": i18n.tekst(taal, "netwerk_titel"),
                "inleiding": i18n.tekst(taal, "netwerk_inleiding", n=i18n.getal(taal, len(knopen)),
                                        samen=i18n.getal(taal, db.NETWERK_SAMEN)),
                "let_op": i18n.tekst(taal, "netwerk_let_op"), "alles_href": basis, "alles": i18n.tekst(taal, "netwerk_alles"),
                "verkennen_href": i18n.pad(taal, "explore"), "verkennen": i18n.tekst(taal, "nav_verkennen"),
                "breed": s["breed"], "hoog": s["hoog"], "knopen": knopen, "randen": randen, "gekozen": gekozen,
                # naast het netwerk staan de namen op alfabet, nooit op hun aantal (E9.S11 AC5, E9.S18 AC5)
                "namen_kop": i18n.tekst(taal, "netwerk_namen_kop"), "kies_regel": i18n.tekst(taal, "netwerk_kies_regel"),
                "namen": [{"id": k["id"], "naam": k["naam"], "href": k["href"], "aan": k["aan"]}
                          for k in sorted(knopen, key=lambda k: (db._alfabet(k["naam"]), k["id"]))],
                "tekst": {"zoek": i18n.tekst(taal, "netwerk_zoek"), "geen": i18n.tekst(taal, "netwerk_zoek_geen"),
                          "schuif": i18n.tekst(taal, "netwerk_schuif")}})
        return antwoord

    def dekking(taal: str) -> list[str]:
        """Wat erin zit en wat nog niet (PLAN #34.2az, E9.S25), uit de uitgave geteld: hoeveel factchecks van hoeveel
        redacties en wie de meeste leverde; en welke grote redacties nog bijna ontbreken, en waarom."""
        redacties = pub.facetten["redactie"]
        zinnen = [i18n.tekst(taal, "dekking_zin", n=i18n.getal(taal, pub.tellingen["paginas"]),
                             r=i18n.getal(taal, len(redacties)), top=i18n.opsomming(taal, [n for n, _ in redacties[:3]]))]
        weinig = [naam for naam, stuk in GROTE_REDACTIES
                  if sum(a for n, a in redacties if stuk in n.casefold()) < BIJNA_GEEN]
        if weinig:
            zinnen.append(i18n.tekst(taal, "dekking_ontbreekt", namen=i18n.opsomming(taal, weinig)))
        return zinnen

    def api_redacties(taal: str):
        def antwoord(request: Request) -> Response:
            # De redacties als gegevens (PLAN #34.2t): dezelfde lijst als `redacties`, elk met de lijst met dat filter.
            return json_antwoord({"titel": i18n.tekst(taal, "nav_redacties"), "inleiding": i18n.tekst(taal, "redacties_inleiding"),
                                  "dekking": dekking(taal),
                                  "redacties": [{"naam": n, "aantal": i18n.getal(taal, a), "href": lijst_url(taal, {"redactie": n})}
                                                for n, a in pub.facetten["redactie"]]})
        return antwoord

    def api_bronnen(taal: str):
        def antwoord(request: Request) -> Response:
            # De bronnen als gegevens (PLAN #34.2t): elke bron van de uitgave met haar licentie en naamsvermelding. Bij
            # EUvsDisinfo de gemeten foutmarge van *Waarom het niet klopt* (B77: op de pagina over de methode, sinds die niet
            # meer bij het blok staat, PO 2026-11-22).
            m = pub.waarom_meting
            meting = i18n.tekst(taal, "waarom_meting", punten=i18n.getal(taal, m["punten"]),
                                fout=i18n.getal(taal, m["niet_gedragen"])) if m else ""
            return json_antwoord({"titel": i18n.tekst(taal, "bronnen_titel"), "inleiding": i18n.tekst(taal, "bronnen_inleiding"),
                                  "licentie_kop": i18n.tekst(taal, "bronnen_licentie"),
                                  "vermelding_kop": i18n.tekst(taal, "bronnen_vermelding"),
                                  "meting_kop": i18n.tekst(taal, "waarom_kop"),
                                  "bronnen": [{"naam": b["naam"], "licentie": b["licentie"], "naamsvermelding": b["naamsvermelding"],
                                               "url": _link(b.get("url")), "meting": meting if b["bron"] == "euvsdisinfo" else ""}
                                              for b in pub.bronnen()]})
        return antwoord

    def lees_zoekbericht(velden: dict) -> tuple[str, int, str | None, dict]:
        """De vraag, het blad, de volgorde en de filters uit het bericht van een zoekformulier. Dezelfde filters als de
        lijst (E9.S10 AC3); een keuze die niet bestaat doet hier niets: de vraag telt."""
        gekozen: dict = {soort: None for soort in FILTERS}
        vraag = db.schoon(" ".join((velden.get("q") or [""])[0].split()))[:db.MAX_PLAKTEKST]   # een geplakt bericht mag langer
        ruw = (velden.get("p") or ["1"])[0]
        blad = int(ruw) if ruw.isascii() and ruw.isdigit() and 0 < len(ruw) <= 4 and int(ruw) >= 1 else 1
        for soort in FILTERS:
            if soort in db.MEER:
                rij = tuple(sorted({w for w in velden.get(soort) or [] if w and pub.kent(soort, w)}))
                gekozen[soort] = rij or None
                continue
            waarde = (velden.get(soort) or [""])[0]
            if waarde and soort != "onderdeel" and pub.kent(soort, waarde):
                gekozen[soort] = waarde
        deel = (velden.get("onderdeel") or [""])[0]
        if deel and gekozen["thema"] and pub.deel(gekozen["thema"], deel):
            gekozen["onderdeel"] = deel
        volgorde = (velden.get("sorteer") or [""])[0]
        sorteer = volgorde if volgorde in db.ZOEK_VOLGORDES else None
        return vraag, blad, sorteer, gekozen

    async def lees_bericht(request: Request) -> dict | None:
        """Het bericht van een zoekformulier, of niets als het te groot is. De vraag staat in het bericht, nooit in het
        adres (E9.S6 AC3)."""
        lengte = request.headers.get("content-length", "0")
        if not lengte.isdigit() or int(lengte) > MAX_BERICHT:
            return None
        bericht = await request.body()
        if len(bericht) > MAX_BERICHT:
            return None
        try:
            return parse_qs(bericht.decode("utf-8", "replace"), keep_blank_values=True, max_num_fields=96)
        except ValueError:
            return {}

    def api_suggesties(taal: str):
        async def antwoord(request: Request) -> Response:
            # Suggesties tijdens het typen (PLAN #34.2b, DESIGNSYSTEEM §4): hoogstens 10, in drie groepen: zoekvragen
            # (de vraag zelf, het woord afgemaakt, en de vraag binnen een thema met haar aantal), ingangen, en een paar
            # factchecks (#359, #361, #404, #356). De vraag komt in het bericht en wordt nergens bewaard.
            velden = await lees_bericht(request)
            if velden is None:
                return PlainTextResponse("Too large", status_code=413)
            ruw = db.schoon((velden.get("q") or [""])[0])[:db.MAX_VRAAG]
            vraag = " ".join(ruw.split())
            ingangen, woorden = await run_in_threadpool(lambda: pub.suggesties(vraag, taal))
            ingangen = vaste_ingangen(vraag, taal) + ingangen
            # het woord dat je typt, afgemaakt (#34.2ac): op de vraag zoals getypt, dus niets na een spatie
            aanvulling = await run_in_threadpool(lambda: pub.aanvulling(ruw.lstrip()))
            uit = await run_in_threadpool(lambda: pub.zoek_ruim(vraag, 1, taal)) if len(vraag) >= 2 else {
                "rijen": [], "totaal": 0, "deels": False, "facetten": {}, "termen": [], "markeer": []}
            totaal = 0 if uit["deels"] else uit["totaal"]
            zoekvragen = []
            if totaal:
                # bij een verbeterde spelfout (#34.2i) is de verbeterde vraag de eerste suggestie
                zoekvragen.append({"tekst": uit.get("verbeterd") or vraag, "aantal": i18n.getal(taal, totaal),
                                   **({"verbeterd": True} if uit.get("verbeterd") else {})})
                themas = sorted(uit["facetten"].get("thema", {}).items(), key=lambda x: -x[1])
                for sleutel, n in [x for x in themas if x[1] < totaal][:2]:
                    zoekvragen.append({"tekst": uit.get("verbeterd") or vraag, "thema": sleutel, "thema_naam": themanaam(taal, sleutel),
                                       "aantal": i18n.getal(taal, n)})
            # de vraag met het woord afgemaakt bovenaan (#34.2ac), met haar aantal: dat is wat het grijs in het veld belooft
            if aanvulling and (n := await run_in_threadpool(lambda: pub.tel(aanvulling))):
                zoekvragen.insert(0, {"tekst": aanvulling, "aantal": i18n.getal(taal, n)})
            gezien = {z["tekst"].casefold() for z in zoekvragen if not z.get("thema")}
            zoekvragen += [{"tekst": w} for w in woorden if w != vraag.casefold() and w not in gezien][:max(0, 4 - len(zoekvragen))]
            ruimte = 10 - len(zoekvragen)
            ingangen = ingangen[:min(4, ruimte)]

            soort = {"naam": lambda i: i18n.tekst(taal, "naam_soort_" + i["naamsoort"]),
                     "pagina": lambda i: i18n.tekst(taal, "ingang_pagina"),
                     "dossier": lambda i: i18n.tekst(taal, "ingang_dossier"),
                     "thema": lambda i: i18n.tekst(taal, "filter_thema"), "onderdeel": lambda i: i18n.tekst(taal, "filter_onderdeel"),
                     "redactie": lambda i: i18n.tekst(taal, "filter_redactie")}
            termen = uit["markeer"]          # de woorden van de vraag en de vormen waarmee gevonden is (#34.2y)
            factchecks = [{"nummer": r["nummer"], "href": i18n.pad(taal, "fact-checks", r["nummer"]),
                           "stukken": markeer(fragment((vertaald(taal, r) or {}).get("tekst") or r["bewering"], termen, 110), termen),
                           "label": i18n.label(taal, r["label"]), "stempel": i18n.stempel(taal, r["label"]),
                           "soort": r["label"] if r["label"] in i18n.LABELS else "geen"}
                          for r in (uit["rijen"] if totaal else [])][:max(0, ruimte - len(ingangen))][:3]
            gegevens = {"vraag": vraag, "totaal": totaal, "zoekvragen": zoekvragen, "aanvulling": aanvulling,
                        "ingangen": [{"soort": i["soort"], "soort_tekst": soort[i["soort"]](i), "naam": i["naam"],
                                      "aantal": "" if i["aantal"] is None else i18n.tekst(
                                          taal, "lijst_een" if i["aantal"] == 1 else "lijst_meer", n=i18n.getal(taal, i["aantal"])),
                                      "href": ingang_href(taal, i)} for i in ingangen],
                        "factchecks": factchecks}
            return Response(json.dumps(gegevens, ensure_ascii=False, separators=(",", ":")), media_type="application/json",
                            headers={"Cache-Control": "no-store"})
        return antwoord

    def api_zoek(taal: str):
        async def antwoord(request: Request) -> Response:
            # Zoeken als gegevens (PLAN #34.2): dezelfde zoekfunctie, filters en ingangen als de zoekpagina. De vraag
            # komt in het bericht en wordt nergens bewaard; het antwoord gaat niet in een tussengeheugen.
            velden = await lees_bericht(request)
            if velden is None:
                return PlainTextResponse("Too large", status_code=413)
            vraag, blad, sorteer, gekozen = lees_zoekbericht(velden)
            letterlijk = (velden.get("letterlijk") or [""])[0] == "1"
            uit = await run_in_threadpool(lambda: pub.zoek_ruim(vraag, blad, taal, sorteer, letterlijk, bericht=True, **gekozen))
            termen, totaal, zonder = uit["markeer"], uit["totaal"], uit["zonder_filters"]
            # tellen (#34.2ba): een vraag op het eerste blad; zonder resultaat ook als een geplakt bericht alleen zwakke
            # treffers heeft, want de site noemt dat geen treffer (E9.S6 AC4). Nooit de vraag zelf.
            if blad == 1 and vraag.strip():
                teller.tel("zoek", taal)
                if not totaal or (uit.get("bericht") and uit["deels"]):
                    teller.tel("zoek-zonder", taal)
                if uit.get("bericht"):
                    teller.tel("zoek-bericht", taal)
            # meteen naar een pagina (#34.2ac): een geplakte link altijd, een persoon of dossier alleen zonder filters
            doel = pub.doorsturen(vraag, letterlijk) if blad == 1 else None
            if doel and doel["soort"] != "factcheck" and any(gekozen.values()):
                doel = None
            doorsturen = {"href": ingang_href(taal, doel), "soort": doel["soort"],
                          "naam": doel["naam"][taal] if isinstance(doel["naam"], dict) else doel["naam"]} if doel else None

            def gelezen(g: dict) -> dict:
                naam = {"land": lambda: landnaam(taal, g["waarde"]), "redactie": lambda: g["waarde"],
                        "thema": lambda: themanaam(taal, g["waarde"]),
                        "onderdeel": lambda: themanaam(taal, g.get("thema", ""), g["waarde"])}[g["soort"]]()
                return {**g, "naam": naam, "tekst": i18n.tekst(taal, f"zoek_gelezen_{g['soort']}", woord=g["woord"], naam=naam)}

            def rij(r: dict) -> dict:
                g = rij_gegevens(taal, r)
                v = vertaald(taal, r)
                g["stukken"] = markeer(fragment(v["tekst"] if v else r["bewering"], termen, 220), termen)
                if g["origineel"]:
                    g["origineel"]["stukken"] = markeer(fragment(r["bewering"], termen, 140), termen)
                return g

            gegevens = {
                "totaal": totaal, "deels": uit["deels"], "gezocht": bool(uit["termen"]), "blad": blad, "verbeterd": uit["verbeterd"],
                # een geplakt bericht (#34.2au): eerlijk zeggen dat het om gelijkenis in woorden gaat, en op welke woorden
                "bericht": bool(uit.get("bericht")),
                "bericht_kop": i18n.tekst(taal, "zoek_bericht_niets" if not totaal else "zoek_bericht_zwak_kop" if uit["deels"]
                                          else "zoek_bericht_een" if totaal == 1 else "zoek_bericht_meer",
                                          n=i18n.getal(taal, totaal)) if uit.get("bericht") else "",
                # bij treffers de woorden die telden; zonder treffers telden alle woorden, dus geen lijst maar dat gezegd
                "bericht_uitleg": (i18n.tekst(taal, "zoek_bericht_zwak", n=i18n.getal(taal, totaal)) if uit["deels"] and totaal
                                   else i18n.tekst(taal, "zoek_bericht_uitleg", woorden=", ".join(uit["termen"][:6]))
                                   if uit["termen"] and totaal else "") if uit.get("bericht") else "",
                "aantal": i18n.tekst(taal, "zoek_een" if totaal == 1 else "zoek_meer", n=i18n.getal(taal, totaal)),
                "rijen": [rij(r) for r in uit["rijen"]],
                "filters": filterdelen(taal, gekozen, sorteer, zoeken=True, tellingen=uit["facetten"]),
                "zonder_filters": (i18n.tekst(taal, "zoek_zonder", aantal=i18n.tekst(
                    taal, "zoek_een" if zonder == 1 else "zoek_meer", n=i18n.getal(taal, zonder)))
                    if zonder > totaal and not totaal else ""),
                "ingangen": [dict(i, href=ingang_href(taal, i)) for i in vaste_ingangen(vraag, taal) + pub.ingangen(vraag, taal)]
                if blad == 1 else [],
                "gelezen": [gelezen(g) for g in uit["gelezen"]], "letterlijk": letterlijk, "doorsturen": doorsturen,
                # niets gevonden: wat erin zit en wie nog ontbreekt (#34.2az), zodat niemand denkt dat niemand het checkte
                "dekking": dekking(taal) if not totaal else [],
            }
            return Response(json.dumps(gegevens, ensure_ascii=False, separators=(",", ":"), default=str),
                            media_type="application/json", headers={"Cache-Control": "no-store"})
        return antwoord

    def robots(request: Request) -> Response:
        # Niets wordt aan zoekmachines aangeboden tot de PO dat per stap openzet (#33.9, B73).
        return PlainTextResponse("User-agent: *\nDisallow: /\n", headers={"Cache-Control": "public, max-age=3600"})

    async def niet_gevonden(request: Request, fout: Exception) -> Response:
        # Het platform is sinds #34.2f stap 4 alleen de gegevenslaag: een adres zonder ingang is een kale 404.
        return PlainTextResponse("Not found", status_code=404, headers={"Cache-Control": "public, max-age=300"})

    async def kapot(request: Request, fout: Exception) -> Response:
        # Geen technische details naar buiten; de koppen hier zelf, want deze fout gaat buiten de tussenlaag om.
        return PlainTextResponse("Error", status_code=500, headers=KOPPEN)

    def api_deelbeeld(taal: str):
        async def antwoord(request: Request) -> Response:
            # Het deelplaatje (PLAN #34.2aq): getekend buiten de hoofdlus, een jaar te bewaren, want het adres van de
            # site draagt de versie van de uitgave (`?v=`).
            inhoud = await run_in_threadpool(deelbeeld_bytes, pub, taal, request.path_params["nummer"])
            if inhoud is None:
                raise HTTPException(404)
            return Response(inhoud, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})
        return antwoord

    def api_ingangsbeeld(taal: str, soort: str):
        async def antwoord(request: Request) -> Response:
            # Het plaatje van een thema, onderdeel of dossier (PLAN #34.2ar), zoals dat van een factcheck.
            sleutel = request.path_params.get("thema") or request.path_params.get("sleutel") or ""
            inhoud = await run_in_threadpool(ingangsbeeld_bytes, pub, taal, soort, sleutel, request.path_params.get("onderdeel"))
            if inhoud is None:
                raise HTTPException(404)
            return Response(inhoud, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})
        return antwoord

    # Alleen de ingangen (PLAN #34.2f, stap 4): de pagina's maakt de site in `site/`, die ook `/static` serveert.
    routes = []
    for taal in i18n.TALEN:
        routes += [Route(f"/api/{taal}/archief", api_archief(taal), methods=["GET"]),
                   Route(f"/api/{taal}/factcheck/{{nummer}}", api_factcheck(taal), methods=["GET"]),
                   Route(f"/api/{taal}/deelbeeld/{{nummer}}.jpg", api_deelbeeld(taal), methods=["GET"]),
                   Route(f"/api/{taal}/deelbeeld/thema/{{thema}}.jpg", api_ingangsbeeld(taal, "thema"), methods=["GET"]),
                   Route(f"/api/{taal}/deelbeeld/thema/{{thema}}/{{onderdeel}}.jpg", api_ingangsbeeld(taal, "thema"),
                         methods=["GET"]),
                   Route(f"/api/{taal}/deelbeeld/dossier/{{sleutel}}.jpg", api_ingangsbeeld(taal, "dossier"), methods=["GET"]),
                   Route(f"/api/{taal}/dossier/{{sleutel}}", api_dossier(taal), methods=["GET"]),
                   Route(f"/api/{taal}/dossiers", api_dossiers(taal), methods=["GET"]),
                   Route(f"/api/{taal}/eigen", api_eigen_lijst(taal), methods=["GET"]),
                   Route(f"/api/{taal}/eigen/{{sleutel}}", api_eigen(taal), methods=["GET"]),
                   Route(f"/api/{taal}/eigen/{{jaar}}/{{maand}}", api_eigen_periode(taal), methods=["GET"]),
                   Route(f"/api/{taal}/eigen/{{jaar}}/{{maand}}/{{naam}}", api_eigen_periode(taal), methods=["GET"]),
                   Route(f"/api/{taal}/redacties", api_redacties(taal), methods=["GET"]),
                   Route(f"/api/{taal}/bronnen", api_bronnen(taal), methods=["GET"]),
                   Route(f"/api/{taal}/themas", api_themas(taal), methods=["GET"]),
                   Route(f"/api/{taal}/verkennen", api_verkennen(taal), methods=["GET"]),
                   Route(f"/api/{taal}/netwerk", api_netwerk(taal), methods=["GET"]),
                   Route(f"/api/{taal}/thema/{{thema}}", api_thema(taal), methods=["GET"]),
                   Route(f"/api/{taal}/thema/{{thema}}/{{onderdeel}}", api_thema(taal), methods=["GET"]),
                   Route(f"/api/{taal}/namen", api_namen(taal), methods=["GET"]),
                   Route(f"/api/{taal}/sitemap", api_sitemap(taal), methods=["GET"]),
                   Route(f"/api/{taal}/naam/{{nummer}}", api_naam(taal), methods=["GET"]),
                   Route(f"/api/{taal}/zoek", api_zoek(taal), methods=["POST"]),
                   Route(f"/api/{taal}/suggesties", api_suggesties(taal), methods=["POST"])]
    async def api_tel(request: Request) -> Response:
        """Een bezoek, gemeld door de site (#34.2ba, E9.S26): soort pagina, taal en of het een robot was. Alleen voor de
        site: zij stuurt deze ingang niet door. Een onbekende soort of taal wordt geweigerd."""
        velden = await lees_bericht(request)
        veld = lambda naam: ((velden or {}).get(naam) or [""])[0]
        soort, taal = veld("soort"), veld("taal")
        if soort not in tellen.SOORTEN or taal not in i18n.TALEN:
            return PlainTextResponse("Bad request", status_code=400)
        teller.tel("robot" if veld("robot") == "1" else soort, taal)
        return Response(status_code=204)

    @contextlib.asynccontextmanager
    async def leven(app):
        yield
        teller.stop()                        # wat nog in het geheugen staat, bij het stoppen weg naar het bestand

    routes += [Route("/robots.txt", robots, methods=["GET"]), Route("/api/tel", api_tel, methods=["POST"])]
    app = Starlette(routes=routes, exception_handlers={404: niet_gevonden, 500: kapot}, lifespan=leven)
    app.add_middleware(Weggelaten)
    app.add_middleware(Koppen)
    app.state.publicatie = pub
    app.state.teller = teller
    return app
