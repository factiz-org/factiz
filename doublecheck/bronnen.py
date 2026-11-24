"""De lijst met betrouwbare bronnen, versie 2 (PLAN #32.3c): eerst wat voor bron het
is, dan pas hoe goed.

Versie 1 (`bronnenlijst.py`, de meting van #32.3b) las de citeerregels van
Wikipedia als oordeel over kwaliteit, en noemde zo Wikipedia, YouTube en X
onbetrouwbaar. De PO (2026-10-28): "het zou daarom bizar zijn als wij Wikipedia
zomaar een onbetrouwbare bron noemen". Nu:

- de soort: platform (wie het post bepaalt het), naslag, officieel of overig;
- de band, alleen uit oordelen over een uitgever: goed (Lin e.a. 0,65 of hoger,
  PO: "0,65 lijkt me dan de grens"; *generally reliable* bij Wikipedia; een
  actieve factchecker van het IFCN; een lid van de EBU uit een land met 70 of
  meer bij RSF), wisselend (Lin e.a. tussen 0,40 en 0,65) of laag (Lin e.a. 0,40
  of lager, de grens van de onderzoekers zelf; *generally unreliable* of
  *deprecated* bij Wikipedia). Zeggen twee oordelen over dezelfde uitgever iets
  anders, dan telt het strengste. Een platform krijgt nooit een band.

Versie 3 (PLAN #32.29, PO 2026-11-02): daarbij de tekens die de PO aannam (EFCSN, JTI, Trust Project, een
IFCN-lidmaatschap in vernieuwing), alleen bij de Spaanse en Portugese redacties die de PO een voor een koos
(`docs/steekproeven/32.29-keuzes-po.json`). Een redactie zonder teken krijgt geen band, ook niet op een eigen oordeel:
"Maybe just use the LIN score and skip everything without IFCN and other factcheck rating, better to be clear?"
Een teken wint niet van een lager oordeel.

Versie 4 (PLAN #32.29d, PO 2026-11-03: "Bronnen zo bouwen"): dezelfde tekens in alle talen, uit de volle lijsten in
`data/bronnen/extern/`: het IFCN (actief en in vernieuwing, niet verlopen), het EFCSN, een certificaat van de JTI en het
Trust Project (alleen waar de titel van de site bij de naam past). Een eigen score zonder teken kwam niet door de ijking
(BENCHMARK §204) en zit er niet in. De keuze *twijfel* van de PO gaat voor een teken uit een lijst.

Versie 5 (PLAN #32.42, B58, PO 2026-11-05: "es-, pt- and de.wikinews.org count as reliable, as in English"): versie 4
met die keuze erop (`PO_BANDEN`). Wikinews in het Engels was al *goed* (Lin e.a. 0,85 voor en.wikinews.org); de andere
talen vielen terug op wikinews.org, waar het strengste oordeel *laag* is (Wikipedia).

Versie 6 (B64, PO 2026-11-08: "ja eens, doen we het zo"): versie 5, en een publieke omroep die lid is van de EBU, in een
land met 75 of meer bij RSF, is *goed* ook als Lin e.a. hem *wisselend* noemt (ORF 0,60, RTBF 0,64, WDR, NDR, SWR, STV);
zegt een oordeel *laag*, dan blijft het *laag*, en de grens van 0,65 blijft. Daarbij Wikinews in het Nederlands en Frans
zoals in de andere talen van V1 (B58, B63; `PO_BANDEN_V6`).

Versie 7 (#32.66, PO 2026-11-09: "Ja, bouw v7"): versie 6, en een medium dat naar een nieuw adres verhuisde, houdt daar
zijn oordeel. franceinfo stond alleen als francetvinfo.fr in de lijst, maar publiceert op franceinfo.fr. Gevonden door de
voorpagina van elke site in de lijst één keer op te vragen (`doorverwijzingen`); elke kandidaat is met de hand nagekeken
(`docs/steekproeven/32.66-verhuizingen.json`), want een doorverwijzing kan ook naar een nieuwe eigenaar, een groep of een
domein te koop gaan, en dan hoort het oude oordeel er niet bij. Alleen *zelfde* telt; twijfel versoepelt nooit.
Daarbij verliezen 14 verlopen *goede* domeinen die nu een gokwebsite, spam of te koop tonen hun oordeel. In gebruik
sinds de tussenrelease van 2026-11-09 (B69, PO: "Ja, release v7").

    python -m doublecheck.bronnen bouwen|dekking|doorverwijzingen|verhuizingen
"""

from __future__ import annotations

import json
import re

from doublecheck import bronnenlijst as bl

BESTAND_V7 = bl.MAP / "bronnen-v7.json"  # versie 7 legt de verhuisde media op versie 6 (#32.66)
VERSIE_V7 = "bronnen-v7"
DOORVERWIJZINGEN = bl.MAP / "doorverwijzingen.jsonl"
VERHUIZINGEN = bl.WORTEL / "docs" / "steekproeven" / "32.66-verhuizingen.json"
# De versie die de controle gebruikt: versie 7 sinds de tussenrelease van 2026-11-09 (B69, PO: "Ja, release v7")
BESTAND = BESTAND_V7
VERSIE = VERSIE_V7
BESTAND_V6 = bl.MAP / "bronnen-v6.json"  # versie 6 (B64), de basis van versie 7
VERSIE_V6 = "bronnen-v6"
BESTAND_V5 = bl.MAP / "bronnen-v5.json"  # versie 6 legt de regel voor publieke omroepen op versie 5 (B64)
VERSIE_V5 = "bronnen-v5"
OMROEP_RSF = 75.0  # B64: een publieke omroep van de EBU telt als goed vanaf deze persvrijheid, ook als Lin wisselend zegt
# B58 en B63 (PO 2026-11-05, 2026-11-08): Wikinews in het Nederlands en Frans zoals in de andere talen van V1
PO_BANDEN_V6 = {h: ("goed", "B58 en B63: zoals en.wikinews.org") for h in ("nl.wikinews.org", "fr.wikinews.org")}
BESTAND_V4 = bl.MAP / "bronnen-v4.json"  # de bouw op de lijsten; versie 5 legt daar de keuze van de PO op
VERSIE_V4 = "bronnen-v4"
# B58 (PO 2026-11-05): Wikinews in de talen van V1 zoals in het Engels
PO_BANDEN = {h: ("goed", "PO 2026-11-05, B58: zoals en.wikinews.org")
             for h in ("es.wikinews.org", "pt.wikinews.org", "de.wikinews.org")}
BESTAND_V2 = bl.MAP / "bronnen-v2.json"  # de lijst van vóór #32.29
BESTAND_V3 = bl.MAP / "bronnen-v3.json"  # de lijst van #32.29, voor de dekking ervoor en erna
VOORSTEL = bl.WORTEL / "docs" / "steekproeven" / "32.29-bronnen-es-pt.json"
KEUZES = bl.WORTEL / "docs" / "steekproeven" / "32.29-keuzes-po.json"
# Per teken de regel die de PO erover koos (#32.29); None: telde al in versie 2.
TEKENS = {"IFCN actief": None, "IFCN vernieuwing": "vernieuwing", "EFCSN": "efcsn", "JTI": "jti",
          "Trust Project": "trust"}
GEEN_BAND = "eigen"  # de regel van de redacties zonder teken: geen band (PO 2026-11-02)
# De taal van een site naar zijn landdomein, voor de dekking per taal; een .com zegt niets over de taal.
TALEN = {"es": (".es", ".cat", ".mx", ".ar", ".cl", ".pe", ".ve", ".ec", ".bo", ".py", ".uy", ".cr", ".gt", ".hn",
                ".sv", ".ni", ".pa", ".do", ".cu", ".pr", ".com.co"),
         "pt": (".pt", ".br", ".ao", ".mz"),
         "de": (".de", ".at")}
GOED, LAAG = 0.65, 0.40
BANDEN = ("laag", "wisselend", "goed")  # strengste eerst
PLATFORMS = frozenset({
    "youtube.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "tiktok.com", "reddit.com", "quora.com",
    "medium.com", "substack.com", "blogspot.com", "wordpress.com", "linkedin.com", "t.me", "grokipedia.com"})
NASLAG = frozenset({"wikipedia.org", "britannica.com"})
SPIEGELS = {"wikiwand.com": "wikipedia.org", "wiki2.org": "wikipedia.org"}
# Waar een voorpagina heen kan sturen zonder dat het medium verhuisde: toestemming, inloggen, een controle op robots, of
# een domein dat te koop of geparkeerd is (#32.66).
NIET_VERHUISD = frozenset({
    "consent.yahoo.com", "guce.yahoo.com", "consent.google.com", "accounts.google.com", "consent.youtube.com",
    "login.microsoftonline.com", "challenges.cloudflare.com", "cookielaw.org", "privacy-mgmt.com", "sourcepoint.com",
    "godaddy.com", "sedo.com", "dan.com", "afternic.com", "hugedomains.com", "parkingcrew.net", "bodis.com",
    "domainmarket.com", "atom.com", "squadhelp.com", "namecheap.com", "buydomains.com", "undeveloped.com",
    "porkbun.com", "sav.com", "uniregistry.com", "domainnamesales.com"})
_TWEEDE_NIVEAU = frozenset({"co", "com", "org", "net", "gov", "gob", "ac", "edu", "or", "ne", "go"})


def _band_lin(pc1: float) -> str:
    return "goed" if pc1 >= GOED else "laag" if pc1 <= LAAG else "wisselend"


def _site(naam: str, namen) -> str | None:
    """Het langste deel van de naam dat voorkomt in `namen`."""
    delen = naam.split(".")
    return next((d for i in range(len(delen) - 1) if (d := ".".join(delen[i:])) in namen), None)


def _telt_teken(teken: str, regels: dict) -> bool:
    if teken not in TEKENS:
        raise ValueError(f"onbekend teken {teken!r}")
    return TEKENS[teken] is None or regels.get(TEKENS[teken]) == "ja"


def tekens_uit(voorstel: dict, keuzes: dict) -> dict[str, list[str]]:
    """Per adres de tekens die tellen: alleen bij een redactie die de PO *goed* koos, alleen een teken waarvan de PO
    de regel aannam, nooit bij de redacties zonder teken; een verbeterd adres vervangt dat uit het voorstel. Een
    gekozen redactie zonder enig teken is een fout in de keuzes; een redactie met alleen een afgewezen teken telt niet."""
    regels, adressen, uit = keuzes["regels"], keuzes.get("adressen", {}), {}
    for groep in voorstel["groepen"]:
        if groep["regel"] == GEEN_BAND:
            continue
        for r in groep["redacties"]:
            if keuzes["redacties"].get(r["domein"], {}).get("keuze") != "goed":
                continue
            if not r["tekens"]:
                raise ValueError(f"{r['domein']} is gekozen, maar heeft geen teken")
            tellen = [t for t in r["tekens"] if _telt_teken(t, regels)]
            if not tellen:
                continue
            for adres in adressen.get(r["domein"], {}).get("adressen", [r["domein"]]):
                uit.setdefault(adres, set()).update(f"{t}, PO {keuzes['datum']}" for t in tellen)
    return {adres: sorted(t) for adres, t in sorted(uit.items())}


def _tsv(tekst: str) -> list[dict]:
    import csv
    import io

    return list(csv.DictReader(io.StringIO(tekst), delimiter="\t"))


def tekens_lijsten(ifcn: str, efcsn: str, jti: str, trust: str, twijfel: frozenset[str] = frozenset()
                   ) -> dict[str, list[str]]:
    """Per adres de tekens uit de volle lijsten (de inhoud van de tsv-bestanden in `data/bronnen/extern/`): het IFCN
    actief of in vernieuwing, het EFCSN, een JTI-certificaat en het Trust Project waar de titel past. Een adres waar de
    PO *twijfel* koos, krijgt geen teken."""
    uit: dict[str, set[str]] = {}

    def zet(adres: str, teken: str) -> None:
        naam = bl.host(adres.strip()) if adres and adres.strip() else ""
        if naam and naam not in twijfel:
            uit.setdefault(naam, set()).add(teken)

    for r in _tsv(ifcn):
        if r["status"] in ("actief", "vernieuwing"):
            zet(r["website"], "IFCN" if r["status"] == "actief" else "IFCN vernieuwing")
    for r in _tsv(efcsn):
        zet(r["website"], "EFCSN")
    for r in _tsv(jti):
        for site in (r["sites"] or "").split():
            zet(site, "JTI")
    for r in _tsv(trust):
        if r["past"] == "ja":
            zet(r["site"], "Trust Project")
    return {adres: sorted(t) for adres, t in sorted(uit.items())}


def _samen(*delen: dict[str, list[str]]) -> dict[str, list[str]]:
    uit: dict[str, set[str]] = {}
    for deel in delen:
        for adres, tekens in deel.items():
            uit.setdefault(adres, set()).update(tekens)
    return {adres: sorted(t) for adres, t in sorted(uit.items())}


def per_taal(sites: dict[str, list]) -> dict[str, dict[str, int]]:
    """Per taal het aantal websites per band, naar het landdomein (`TALEN`)."""
    uit = {taal: dict.fromkeys(("goed", "wisselend", "laag"), 0) for taal in TALEN}
    for naam, oordelen in sites.items():
        taal = next((t for t, eind in TALEN.items() if naam.endswith(eind)), None)
        if taal and oordelen:
            uit[taal][min((b for b, _ in oordelen), key=BANDEN.index)] += 1
    return uit


def bouw(lin: str, wikipedia: list[str], ifcn: list[str], ebu: list[tuple[str, str]], rsf: dict[str, float],
         datum: str, tekens: dict[str, list[str]] | None = None) -> dict:
    """Per website de banden met hun herkomst; platforms en de citeerregels van Wikipedia over zichzelf en over
    platforms tellen niet. `tekens`: de tekens die de PO aannam, per adres (`tekens_uit`)."""
    sites: dict[str, set[tuple[str, str]]] = {}
    buiten = PLATFORMS | NASLAG | set(SPIEGELS)

    def zet(naam: str, band: str, bron: str, citeerregel: bool = False) -> None:
        if naam and _site(naam, PLATFORMS) is None and not (citeerregel and _site(naam, buiten)):
            sites.setdefault(naam, set()).add((band, bron))

    for naam, pc1 in bl.lin_cijfers(lin).items():
        zet(naam, _band_lin(pc1), f"Lin e.a. {pc1:.2f}")
    for tekst in wikipedia:
        for naam, s in bl.wikipedia_oordelen(tekst):
            zet(naam, "goed" if s == "A" else "laag", "Wikipedia", citeerregel=True)
    for url in ifcn:
        zet(bl.host(url), "goed", "IFCN")
    for naam, land in ebu:
        if rsf.get(land, 0.0) >= bl.RSF_GRENS:
            zet(bl.host(naam), "goed", f"EBU, RSF {land} {rsf[land]:.1f}")
    for naam, herkomst in (tekens or {}).items():
        for h in herkomst:
            zet(naam, "goed", h)
    vast = {naam: sorted([list(o) for o in oordelen]) for naam, oordelen in sorted(sites.items())}
    return {"_meta": {"versie": VERSIE_V4, "datum": datum, "plan": "PLAN #32.3c, #32.29, #32.29d",
                      "grenzen": {"goed": GOED, "laag": LAAG, "rsf": bl.RSF_GRENS},
                      "vingerafdruk": bl.vingerafdruk(vast)}, "sites": vast}


def met_po_banden(lijst: dict, po: dict[str, tuple[str, str]], datum: str) -> dict:
    """Versie 5: versie 4 met de banden die de PO zelf koos (B58); zo'n adres krijgt alleen dat oordeel, en de rest
    blijft zoals het was. Met een eigen vingerafdruk, en die van versie 4 erbij."""
    sites = {**lijst["sites"], **{h: [[band, waarom]] for h, (band, waarom) in po.items()}}
    meta = {**lijst["_meta"], "versie": VERSIE_V5, "datum": datum, "plan": lijst["_meta"].get("plan", "") + ", #32.42 (B58)",
            "basis": lijst["_meta"].get("vingerafdruk"), "vingerafdruk": bl.vingerafdruk(sites)}
    return {"_meta": meta, "sites": sites}


def _rsf(waarom: str) -> float:
    m = re.search(r"RSF \S+ ([0-9.]+)", waarom)
    return float(m.group(1)) if m else 0.0


def met_omroepen(lijst: dict, po: dict[str, tuple[str, str]], datum: str) -> dict:
    """Versie 6 (B64): versie 5, en een publieke omroep van de EBU in een land met `OMROEP_RSF` of meer bij RSF is
    *goed*, ook als Lin e.a. hem *wisselend* noemt; niet als een oordeel *laag* zegt. Daarbij de banden van `po`."""
    sites = {}
    for naam, oordelen in lijst["sites"].items():
        banden = {b for b, _ in oordelen}
        omroep = any(b == "goed" and str(w).startswith("EBU, RSF") and _rsf(str(w)) >= OMROEP_RSF for b, w in oordelen)
        if omroep and "wisselend" in banden and "laag" not in banden:
            gemengd = ", ".join(str(w) for b, w in oordelen if b == "wisselend")
            oordelen = [o for o in oordelen if o[0] != "wisselend"] + [
                ["goed", f"B64: publieke omroep van de EBU, RSF {OMROEP_RSF:.0f} of meer; {gemengd} telt niet"]]
        sites[naam] = oordelen
    sites.update({h: [[band, waarom]] for h, (band, waarom) in po.items()})
    meta = {**lijst["_meta"], "versie": VERSIE_V6, "datum": datum, "plan": lijst["_meta"].get("plan", "") + ", #32.59 (B64)",
            "basis": lijst["_meta"].get("vingerafdruk"), "vingerafdruk": bl.vingerafdruk(sites)}
    return {"_meta": meta, "sites": sites}


def _domein(naam: str) -> str:
    """Het geregistreerde domein: de laatste twee delen, of drie bij een landdomein met een tweede niveau (bbc.co.uk)."""
    d = naam.split(".")
    n = 3 if len(d) >= 3 and len(d[-1]) == 2 and d[-2] in _TWEEDE_NIVEAU else 2
    return ".".join(d[-n:])


def verhuizing(oud: str, eind_url: str | None, sites: dict[str, list]) -> str | None:
    """Het nieuwe domein als de voorpagina van `oud` doorstuurt naar een website die nog niet in de lijst staat; None bij
    een doorverwijzing binnen de site, naar een site met een eigen oordeel, een platform, naslag, een pagina voor
    toestemming of een domein te koop. Een kandidaat, geen besluit: elke wordt met de hand nagekeken."""
    naam = bl.host(eind_url or "")
    if not naam or _site(naam, sites) or _site(naam, PLATFORMS) or _site(naam, NASLAG) or _site(naam, NIET_VERHUISD):
        return None
    nieuw = _domein(naam)
    return None if nieuw == _domein(oud) else nieuw


def met_verhuizingen(lijst: dict, verhuizingen: dict[str, str], datum: str,
                     overgenomen: dict[str, str] | None = None) -> dict:
    """Versie 7 (#32.66): versie 6, en elk nieuw domein (sleutel) krijgt de oordelen van zijn oude adres (waarde), met
    de verhuizing erbij. Nooit over een eigen oordeel heen, en nooit van een adres dat niet in de lijst staat. Een domein
    in `overgenomen` (verlopen, nu van een ander: een casino, spam, te koop) verliest zijn oordeel; een *laag* domein
    nooit, want twijfel versoepelt nooit."""
    overgenomen = overgenomen or {}
    sites = dict(lijst["sites"])
    for oud, waarom in sorted(overgenomen.items()):
        if oud not in sites or any(b == "laag" for b, _ in sites[oud]):
            raise ValueError(f"{oud}: niet in de lijst, of laag (blijft laag)")
        del sites[oud]
    for nieuw, oud in sorted(verhuizingen.items()):
        if oud not in lijst["sites"]:
            raise ValueError(f"{oud} staat niet in {lijst['_meta'].get('versie')}")
        if _site(nieuw, lijst["sites"]):
            raise ValueError(f"{nieuw} heeft al een eigen oordeel")
        sites[nieuw] = [[band, f"verhuisd van {oud}: {waarom}"] for band, waarom in lijst["sites"][oud]]
    meta = {**lijst["_meta"], "versie": VERSIE_V7, "datum": datum, "plan": lijst["_meta"].get("plan", "") + ", #32.66",
            "basis": lijst["_meta"].get("vingerafdruk"), "overgenomen": dict(sorted(overgenomen.items())),
            "vingerafdruk": bl.vingerafdruk(sites)}
    return {"_meta": meta, "sites": sites}


_VERHUISD = re.compile(r"^verhuisd van [^:]+: ")


def reden(tekst: str) -> str:
    """De reden van een oordeel zonder de verhuizing ervoor: versie 7 schrijft "verhuisd van francetvinfo.fr: Lin e.a.
    0.85"; wie de reden leest (IFCN, EFCSN, Lin e.a.), leest zo hetzelfde als op het oude adres (#32.66)."""
    return _VERHUISD.sub("", str(tekst))


def beoordeel(url: str, sites: dict[str, list]) -> dict:
    """Wat voor bron een adres is, en hoe goed: de soort, de band (of geen) en de oordelen waar die vandaan komt."""
    naam = bl.host(url)
    spiegel = _site(naam, SPIEGELS)
    if spiegel:
        naam = SPIEGELS[spiegel]
    if (platform := _site(naam, PLATFORMS)) is not None:
        return {"site": platform, "soort": "platform", "band": None, "bronnen": []}
    site = _site(naam, sites)
    oordelen = sites.get(site, []) if site else []
    soort = "naslag" if _site(naam, NASLAG) else "officieel" if naam and bl.officieel(naam) else "overig"
    uit = {"site": site or _site(naam, NASLAG) or naam, "soort": soort,
           "band": min((b for b, _ in oordelen), key=BANDEN.index) if oordelen else None, "bronnen": oordelen}
    return {**uit, "spiegel van": SPIEGELS[spiegel]} if spiegel else uit


def _lees(pad) -> dict:  # pragma: no cover - een bestand
    return json.loads(pad.read_text(encoding="utf-8"))


def _doorverwijzingen(tegelijk: int = 16) -> None:  # pragma: no cover - netwerk
    """Van elke site in versie 6 één keer de voorpagina, met robots.txt: waar stuurt ze heen? Alleen het eindadres en de
    status, nooit de pagina; per site één verzoek tegelijk; hervatbaar (#32.66)."""
    import concurrent.futures as cf
    import threading
    import urllib.robotparser

    import httpx

    from doublecheck import eigenaanvoer as ea

    lijst = _lees(BESTAND_V6)
    gedaan = set()
    if DOORVERWIJZINGEN.exists():
        gedaan = {json.loads(r)["site"] for r in DOORVERWIJZINGEN.read_text(encoding="utf-8").splitlines() if r.strip()}
    werk = [h for h in sorted(lijst["sites"]) if h not in gedaan]
    print(f"{len(lijst['sites'])} sites, {len(werk)} te doen", flush=True)
    slot, teller = threading.Lock(), [0]

    def doe(host: str) -> None:
        uit = {"site": host, "eind": None, "status": None}
        with httpx.Client(headers=ea.KOP, follow_redirects=True, timeout=10, max_redirects=8) as web:
            for schema in ("https", "http"):
                try:
                    r = web.get(f"{schema}://{host}/robots.txt")
                    robots = urllib.robotparser.RobotFileParser()
                    robots.parse(r.text.splitlines() if r.status_code == 200 else [])
                    if not robots.can_fetch(ea.NAAM, f"{schema}://{host}/"):
                        uit["status"] = "robots"
                        break
                    with web.stream("GET", f"{schema}://{host}/") as a:
                        uit["eind"], uit["status"] = str(a.url), a.status_code
                    break
                except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError) as fout:
                    uit["status"] = type(fout).__name__
        with slot:
            with DOORVERWIJZINGEN.open("a", encoding="utf-8") as f:
                f.write(json.dumps(uit, ensure_ascii=False) + "\n")
            teller[0] += 1
            if teller[0] % 500 == 0:
                print(f"  {teller[0]} van {len(werk)}", flush=True)

    with cf.ThreadPoolExecutor(tegelijk) as pool:
        list(pool.map(doe, werk))
    print("klaar", flush=True)


def _verhuizingen() -> None:  # pragma: no cover - de bestanden
    """De kandidaten uit de doorverwijzingen naar het labelbestand; labels die er al staan, blijven."""
    sites = _lees(BESTAND_V6)["sites"]
    kandidaten: dict[str, dict] = {}
    for regel in DOORVERWIJZINGEN.read_text(encoding="utf-8").splitlines():
        r = json.loads(regel)
        if (nieuw := verhuizing(r["site"], r["eind"], sites)) is not None:
            k = kandidaten.setdefault(nieuw, {"oud": [], "eind": r["eind"], "band": []})
            k["oud"].append(r["site"])
            k["band"].append(min((b for b, _ in sites[r["site"]]), key=BANDEN.index))
    oud = _lees(VERHUIZINGEN) if VERHUIZINGEN.exists() else {"labels": {}}
    labels = {n: oud["labels"].get(n, {"label": "", "oud": k["oud"][0] if len(k["oud"]) == 1 else "", "waarom": ""})
              for n, k in sorted(kandidaten.items())}
    VERHUIZINGEN.write_text(json.dumps({
        "toelichting": "PLAN #32.66: per nieuw domein waar de voorpagina van een site uit bronnen-v6 heen stuurt. Label "
                       "zelfde (hetzelfde medium, verhuisd: krijgt het oordeel van `oud`), ander (een nieuwe eigenaar, "
                       "een groep, een ander medium, te koop) of twijfel (telt niet).",
        "kandidaten": dict(sorted(kandidaten.items())), "labels": labels,
        "overgenomen": oud.get("overgenomen", {})}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    zonder = sum(not v["label"] for v in labels.values())
    print(f"{len(kandidaten)} kandidaten, {zonder} zonder label; {VERHUIZINGEN}")


def main() -> None:  # pragma: no cover - CLI, op de gedownloade bestanden en de antwoorden van de rondes
    import argparse
    from collections import Counter
    from datetime import date

    parser = argparse.ArgumentParser(description="De lijst met betrouwbare bronnen, versie 4 (PLAN #32.3c, #32.29d)")
    parser.add_argument("stap", choices=("bouwen", "dekking", "doorverwijzingen", "verhuizingen"))
    args = parser.parse_args()
    if args.stap == "doorverwijzingen":
        return _doorverwijzingen()
    if args.stap == "verhuizingen":
        return _verhuizingen()
    if args.stap == "bouwen" and BESTAND_V6.exists():
        if BESTAND_V7.exists():
            raise SystemExit(f"{BESTAND_V7.name} ligt al vast; een andere lijst is een nieuwe versie (besluit van de PO)")
        v6 = _lees(BESTAND_V6)
        if v6["_meta"]["versie"] != VERSIE_V6 or not bl.vastgelegd(v6):
            raise SystemExit(f"{BESTAND_V6.name} is niet {VERSIE_V6} of ligt niet vast")
        labels = _lees(VERHUIZINGEN)["labels"]
        if open_ := sorted(n for n, v in labels.items() if v["label"] not in ("zelfde", "ander", "twijfel")):
            raise SystemExit(f"{len(open_)} kandidaten zonder label in {VERHUIZINGEN.name}: {', '.join(open_[:10])}")
        verhuisd = {v.get("adres") or n: v["oud"] for n, v in labels.items() if v["label"] == "zelfde"}
        overgenomen = _lees(VERHUIZINGEN).get("overgenomen", {})
        lijst = met_verhuizingen(v6, verhuisd, date.today().isoformat(), overgenomen)
        BESTAND_V7.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{VERSIE_V7}: {len(verhuisd)} verhuisde media, {len(overgenomen)} overgenomen domeinen zonder band; "
              f"vingerafdruk {lijst['_meta']['vingerafdruk'][:12]}")
        return
    if args.stap == "bouwen" and BESTAND_V5.exists():
        v5 = _lees(BESTAND_V5)
        if v5["_meta"]["versie"] != VERSIE_V5 or not bl.vastgelegd(v5):
            raise SystemExit(f"{BESTAND_V5.name} is niet {VERSIE_V5} of ligt niet vast")
        lijst = met_omroepen(v5, PO_BANDEN_V6, date.today().isoformat())
        BESTAND_V6.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
        anders = sorted(n for n in lijst["sites"] if lijst["sites"][n] != v5["sites"].get(n))
        print(f"{VERSIE_V6}: {len(anders)} adressen anders dan {VERSIE_V5}: {', '.join(anders)}; "
              f"vingerafdruk {lijst['_meta']['vingerafdruk'][:12]}")
        return
    if args.stap == "bouwen" and BESTAND_V4.exists():
        v4 = _lees(BESTAND_V4)
        if v4["_meta"]["versie"] != VERSIE_V4 or not bl.vastgelegd(v4):
            raise SystemExit(f"{BESTAND_V4.name} is niet {VERSIE_V4} of ligt niet vast")
        lijst = met_po_banden(v4, PO_BANDEN, date.today().isoformat())
        BESTAND_V5.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{VERSIE_V5}: {len(PO_BANDEN)} adressen met de keuze van de PO; vingerafdruk {lijst['_meta']['vingerafdruk'][:12]}")
        return
    if args.stap == "bouwen":
        if BESTAND_V4.exists():
            raise SystemExit(f"{BESTAND_V4.name} ligt al vast; een andere lijst is een nieuwe versie (besluit van de PO)")
        keuzes = _lees(KEUZES)
        twijfel = frozenset(d for d, r in keuzes["redacties"].items() if r["keuze"] == "twijfel")
        lijsten = tekens_lijsten(*(((bl.EXTERN / naam).read_text(encoding="utf-8")) for naam in
                                   ("ifcn/organisaties.tsv", "efcsn/leden.tsv", "jti/gecertificeerd.tsv",
                                    "trust/merken.tsv")), twijfel=twijfel)
        tekens = _samen(tekens_uit(_lees(VOORSTEL), keuzes), lijsten)
        lijst = bouw(**bl.invoer(), datum=date.today().isoformat(), tekens=tekens)
        BESTAND_V4.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
        tel = Counter(min((b for b, _ in o), key=BANDEN.index) for o in lijst["sites"].values())
        print(f"{len(lijst['sites'])} websites met een band: {dict(tel)}; {len(tekens)} adressen met een teken; "
              f"vingerafdruk {lijst['_meta']['vingerafdruk'][:12]}")
        return
    voor, na = _lees(BESTAND_V3), _lees(BESTAND)
    assert bl.vastgelegd(voor) and bl.vastgelegd(na) and na["_meta"]["versie"] == VERSIE
    print("Websites per band, per taal naar het landdomein (voor -> na):")
    pv, pn = per_taal(voor["sites"]), per_taal(na["sites"])
    for taal in TALEN:
        print(f"  {taal}: " + ", ".join(f"{b} {pv[taal][b]} -> {pn[taal][b]}" for b in ("goed", "wisselend", "laag")))
    voorstel, adressen = _lees(VOORSTEL), _lees(KEUZES).get("adressen", {})

    def goed(domein: str, lijst: dict) -> bool:
        """Een redactie is goed als een van haar adressen (met de verbeteringen bij de keuzes) goed is."""
        return any(beoordeel("https://" + a, lijst["sites"])["band"] == "goed"
                   for a in adressen.get(domein, {}).get("adressen", [domein]))

    print("De redacties uit het voorstel van #32.29 (goed voor -> na):")
    print(f"  al goed: {len(voorstel['al_goed'])}, na de bouw nog goed "
          f"{sum(goed(d, na) for d in voorstel['al_goed'])}")
    for groep in voorstel["groepen"]:
        for taal in ("es", "pt"):
            rs = [r["domein"] for r in groep["redacties"] if r["taal"] == taal]
            if rs:
                print(f"  groep {groep['id']} {taal}: {len(rs)} redacties, goed {sum(goed(d, voor) for d in rs)} -> "
                      f"{sum(goed(d, na) for d in rs)}")
    ontwikkel, toets = bl.antwoorden()
    print("Websites in de antwoorden van de rondes (Engels), per soort en band (voor -> na):")
    for naam, lijst in (("voor", voor), ("na", na)):
        tel = Counter()
        for _, bronnen, _ in ontwikkel + toets:
            for url in set(bl._webadressen(bronnen)):
                b = beoordeel(url, lijst["sites"])
                tel[(b["soort"], b["band"])] += 1
        n = sum(tel.values())
        print(f"  {naam}: {n} keer een website; " + ", ".join(
            f"{s} {b or '-'} {k}" for (s, b), k in sorted(tel.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
