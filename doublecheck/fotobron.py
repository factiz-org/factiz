"""De foto bij de bron (PLAN #32.54, 3b en 3c): het beeld is een sleutel, geen bewijs.

Bij een bericht met een foto zegt de lezer soms *klopt* omdat het nieuws klopt, terwijl de foto bij iets anders hoort:
een echte gebeurtenis met een verkeerde foto (§234). Factiz beoordeelt geen pixels. Na de lezer kijkt deze stap of de
foto in grote lijnen op de pagina's staat die het bericht al bevestigen: de bronnen met rol *bevestigt* en band *goed*,
hoogstens `MAX_PAGINAS`, met per pagina hoogstens `MAX_BEELDEN` beelden van het artikel. Dezelfde foto: PDQ binnen de
drempel over het geheel en de vaste uitsneden, of genoeg punten met één gelijkvormigheid (`beeldvraag.bevestigd`, de
drempels van `[beeldstap]`).

Versie 2 (na §248): ook het beeldgebied en de panelen van het beeld als vraag (een foto die maar een deel van een
screenshot vult), en ook een bevestigende bron met soort *officieel*, met of zonder band.

Gevonden: groen blijft, met de pagina. Niet gevonden: geen kleur, de uitkomst *foto niet bij de bron*, en de uitleg
begint met `ZIN`. Geen nieuwe zoekvraag. Het ophalen is van de aanroeper (`beelden_van`, `beeld_van`): beleefd, en het
beeld alleen in het geheugen (B35, DR3).
"""

from __future__ import annotations

from typing import Callable

from doublecheck import beeldvraag as bv

VERSIE = "fotobron-v1"
VERSIES = ("fotobron-v1", "fotobron-v2")
MAX_DELEN = 4  # v2: het hele beeld, het beeldgebied en de grootste panelen
MAX_PAGINAS = 5
MAX_BEELDEN = 10
UITKOMST = "foto niet bij de bron"
ZIN = "Het nieuws klopt, maar deze foto vonden we niet bij dat nieuws."


def paginas(bronnen: list[dict], versie: str = VERSIE) -> list[str]:
    """De pagina's waar de foto moet staan: de goede bronnen die het bericht bevestigen, in hun volgorde; bij v2 ook
    een officiële bron die het bevestigt."""
    uit = []
    for b in bronnen:
        telt = b.get("band") == "goed" or (versie == "fotobron-v2" and b.get("soort") == "officieel")
        if b.get("rol") == "bevestigt" and telt and b.get("url") and b["url"] not in uit:
            uit.append(b["url"])
    return uit[:MAX_PAGINAS]


def _delen(beeld: bytes, versie: str) -> list:
    """De vragen: bij v1 het hele beeld; bij v2 ook het beeldgebied en de panelen, hoogstens `MAX_DELEN`."""
    if versie == "fotobron-v1":
        return [beeld]
    from doublecheck.beelduitsnede import beeldgebied, panelen
    from doublecheck.image_fingerprint import as_image

    geheel = as_image(beeld).convert("RGB")
    vakken = []
    gebied = beeldgebied(geheel)
    for vak in ([gebied] if gebied else []) + panelen(geheel):
        if vak not in vakken:
            vakken.append(vak)
    return [beeld] + [geheel.crop(v) for v in vakken][:MAX_DELEN - 1]


def moet_zoeken(uit: dict, met_beeld: bool) -> bool:
    """Alleen een groen antwoord bij een bericht met een beeld."""
    return met_beeld and uit.get("kleur") == "groen"


def _afstand(een: str, twee: str) -> int:
    return (int(een, 16) ^ int(twee, 16)).bit_count()


def _vergelijk(vraag: dict, beeld: dict, drempel_pdq: int, min_punten: int, min_dekking: float) -> dict:
    hashes = vraag["pdq"] if vraag["kwaliteit"] >= bv.MIN_KWALITEIT else []
    pdq = (min(_afstand(a, b) for a in hashes for b in beeld["pdq"])
           if hashes and beeld["kwaliteit"] >= bv.MIN_KWALITEIT else None)
    n, dekking = bv.puntvergelijking(vraag["punten"], beeld["punten"])
    return {"pdq": pdq, "punten": n, "dekking": round(dekking, 4),
            "zelfde": bv.bevestigd(pdq, n, dekking, drempel_pdq=drempel_pdq, min_punten=min_punten,
                                   min_dekking=min_dekking)}


def _beter(v: dict, beste: dict | None) -> bool:
    return beste is None or (v["punten"], -(v["pdq"] or 256)) > (beste["punten"], -(beste["pdq"] or 256))


def _op_pagina(pagina: str, vragen: list[dict], beelden_van, beeld_van, drempels: tuple) -> dict:
    """Eén pagina: of ze opende, hoeveel beelden gelezen, de beste vergelijking, en het eerste beeld dat de foto is."""
    from doublecheck.beeldstap import beeldkenmerken

    uit = {"geopend": 0, "beelden": 0, "beste": None, "gevonden": None}
    adressen = beelden_van(pagina)
    if adressen is None:
        return uit
    uit["geopend"] = 1
    for adres in adressen[:MAX_BEELDEN]:
        inhoud = beeld_van(adres)
        if not inhoud:
            continue
        try:
            kenmerken = beeldkenmerken(inhoud)
        except Exception:  # noqa: BLE001 - een beeld dat niet te lezen is, telt niet
            continue
        uit["beelden"] += 1
        for i, vraag in enumerate(vragen):
            v = _vergelijk(vraag, kenmerken, *drempels)
            if _beter(v, uit["beste"]):
                uit["beste"] = {"pagina": pagina, "beeld": adres, "deel": i,
                                **{k: v[k] for k in ("pdq", "punten", "dekking")}}
            if v["zelfde"]:
                uit["gevonden"] = adres
                return uit
    return uit


def zoek(beeld: bytes, paginas_: list[str], beelden_van: Callable[[str], list[str] | None],
         beeld_van: Callable[[str], bytes | None], *, drempel_pdq: int = 31, min_punten: int = 50,
         min_dekking: float = 0.10, versie: str = VERSIE, tegelijk: int = 1) -> dict:
    """Staat de foto op een van de pagina's? `beelden_van(pagina)` geeft de beeldadressen van het artikel, of `None` als
    de pagina niet opent; `beeld_van(adres)` de bytes of `None`. Na elkaar stopt het bij de eerste vondst; met
    `tegelijk` > 1 (het product) worden de pagina's tegelijk bekeken en telt de eerste pagina in de volgorde die de foto
    heeft, zodat de uitkomst dezelfde is. Bewaart alleen adressen en getallen, nooit een beeld."""
    from doublecheck.beeldstap import beeldkenmerken

    if versie not in VERSIES:
        raise ValueError(f"onbekende versie {versie!r}")
    vragen = [beeldkenmerken(d) for d in _delen(beeld, versie)]
    drempels = (drempel_pdq, min_punten, min_dekking)
    uit = {"versie": versie, "gevonden": None, "beeld": None, "paginas": len(paginas_), "geopend": 0, "beelden": 0,
           "delen": len(vragen), "beste": None}
    if tegelijk > 1 and len(paginas_) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(min(tegelijk, len(paginas_))) as pool:
            per = list(pool.map(lambda p: _op_pagina(p, vragen, beelden_van, beeld_van, drempels), paginas_))
    else:
        per = []
        for pagina in paginas_:
            per.append(_op_pagina(pagina, vragen, beelden_van, beeld_van, drempels))
            if per[-1]["gevonden"]:
                break
    for pagina, d in zip(paginas_, per):
        uit["geopend"] += d["geopend"]
        uit["beelden"] += d["beelden"]
        if d["beste"] is not None and _beter(d["beste"], uit["beste"]):
            uit["beste"] = d["beste"]
        if d["gevonden"] and uit["gevonden"] is None:
            uit["gevonden"], uit["beeld"] = pagina, d["gevonden"]
    return uit


def toepassen(uit: dict, vondst: dict | None) -> dict:
    """De regel van 3(c): groen blijft alleen als de foto bij een bevestigende goede bron staat. Raakt alleen groen; het
    oordeel van de lezer blijft staan."""
    if vondst is None or uit.get("kleur") != "groen":
        return uit
    if vondst.get("gevonden"):
        return {**uit, "foto": vondst, "kleur_nieuws": "groen"}
    uitleg = (uit.get("uitleg") or "").strip()
    return {**uit, "kleur": None, "uitkomst": UITKOMST, "uitleg": ZIN + ("\n\n" + uitleg if uitleg else ""),
            "foto": vondst, "kleur_nieuws": "groen"}


AGENT = "FactizResearch"  # dezelfde naam als in de metingen, zodat robots.txt hetzelfde zegt (DESIGN §4m)
KOP = {"User-Agent": "Mozilla/5.0 (FactizResearch; checks whether a photo appears on a source page, stores no image; "
                     "https://factiz.org)"}
WACHTTIJD = 4.0  # seconden per verzoek; een pagina die niet op tijd antwoordt, telt als niet geopend


def haler(timeout: float = WACHTTIJD):  # pragma: no cover - het netwerk
    """Het ophalen voor het product: robots.txt per host (onthouden zolang de controle loopt), dan de pagina en haar
    beelden, elk hoogstens `timeout` seconden. Alles alleen in het geheugen. Geeft (`beelden_van`, `beeld_van`)."""
    import urllib.robotparser
    from urllib.parse import urlsplit

    import httpx

    from doublecheck.api import MAX_IMAGE_BYTES
    from doublecheck.artikelbeelden import beelden_uit_artikel

    web, robots = httpx.Client(headers=KOP, follow_redirects=True, timeout=timeout), {}

    def mag(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        if host not in robots:
            lezer = urllib.robotparser.RobotFileParser()
            try:
                r = web.get(f"https://{host}/robots.txt")
                lezer.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                lezer.parse([])
            robots[host] = lezer
        return robots[host].can_fetch(AGENT, url)

    def beelden_van(url: str) -> list[str] | None:
        if not mag(url):
            return None
        r = web.get(url)
        return beelden_uit_artikel(r.text, str(r.url)) if r.status_code == 200 else None

    def beeld_van(url: str) -> bytes | None:
        if not mag(url):
            return None
        r = web.get(url)
        return r.content if r.status_code == 200 and len(r.content) <= MAX_IMAGE_BYTES else None

    return beelden_van, beeld_van
