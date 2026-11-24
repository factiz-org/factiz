"""EUvsDisinfo als eerste bron buiten de ClaimReview-feed (E7.S4, #24.6).

De database van de EEAS East StratCom Task Force (17.000+ gevallen, alleen
Engels) heeft geen officiële export; de CC BY 4.0-snapshot op Mendeley
(yhdtkszvgp v3, 2015-01-06 t/m 2022-11-22, 14.497 gevallen) is de bron voor de
eerste import, en de EEAS-reuse-regel ("reuse is authorised, provided the
source is acknowledged") dekt de inhoud zelf. Wat daarna kwam, haalt `--server`
op bij de MCP-server die EUvsDisinfo op aanvraag aanbiedt (PLAN #35.3), vanaf
`VANAF`: dezelfde gevallen, dezelfde import, een eigen herkomst. De server
geeft de nieuwste eerst; een geval krijgt de datum waarop de desinformatie
verscheen en verschijnt later, dus het ophalen loopt door tot een bladzijde
zonder iets nieuws.

Elk geval wordt één claim (de Engelse samenvatting van de desinformatie) met
één check (uitgever EUvsDisinfo, oordeel "disinformation") en per genoemde
outlet een attributie van niveau `waargenomen`: de EEAS zag de claim daar
verschijnen. Dat is géén toeschrijving aan een operatie — dat niveau komt pas
van trackers die een netwerk benoemen.

Wat dit bewust níét doet: de EEAS tot onafhankelijke redactie bombarderen. De
uitgever komt binnen als onbekend en telt niet mee voor DR7 tot het
uitgeversregister er een besluit over neemt (RUNBOOK, poortwachters).

De snapshot is een scrape, en dat is te zien (#25.25). Waar de site een lange
outletlijst afkapte, staat de knoptekst in het veld: aan de laatste outlet
vast ("rayalauma.comShow more") of los erachter. In 368 van de 14.497
gevallen is de lijst dus onvolledig; wat achter de knop zat, ontbreekt in de
snapshot. En de kolom noemt soms een platform in plaats van een outlet
("Twitter", "t.me"); die wordt een actor van de soort `platform`. `herstel`
brengt een database van vóór deze regels in orde.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import html
import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

from doublecheck.attributie import (
    registreer_actor,
    registreer_bron,
    vind_actor,
    voeg_attributie,
    aandeel_met_attributie,
)
from doublecheck.datums import geldige_review_datum
from doublecheck.factchecktools import RawClaim, RawFactcheck

BRON_ID = "euvsdisinfo"
HERKOMST = "euvsdisinfo:mendeley-yhdtkszvgp-v3"
HERKOMST_SERVER = "euvsdisinfo:mcp"     # wat de server bracht (PLAN #35.3); dezelfde bron, dus dezelfde regels
SERVER = "https://mcp.euvsd.info/mcp"
# PO 2026-11-23: "Qua binnenhalen, doe voor nu alleen 2026, de rest doen we later, als ik weer wat promotiebudget heb".
# Wat tussen de momentopname (tot 2022-11-22) en deze dag ligt, komt mee zodra deze dag vroeger wordt.
VANAF = "2026-01-01"
OPSLAG = Path(__file__).resolve().parent.parent / "data" / "euvsdisinfo" / "server.jsonl"
LIMIT = 100        # het meeste dat de server per vraag geeft
PAUZE = 2.0        # seconden tussen twee vragen
BRON = dict(
    bron_id=BRON_ID,
    naam="EUvsDisinfo (EEAS East StratCom Task Force)",
    soort="overheid",
    licentie=(
        "EEAS legal notice: reuse is authorised, provided the source is "
        "acknowledged; snapshot: Mendeley Data yhdtkszvgp v3, CC BY 4.0"
    ),
    attributietekst="EUvsDisinfo, European External Action Service",
    url="https://euvsdisinfo.eu/disinformation-cases/",
    herverdeelbaar=True,
)

# Kolommen worden op betekenis gevonden, niet op exacte naam: de snapshot is een
# hernoemde scrape en een volgende versie mag anders heten. Ontbreekt een
# essentiële kolom, dan stopt de import met de echte koppen in de melding.
_KOLOMSLEUTELS = {
    "datum": ("date", "publi"),
    "url": ("link", "url"),
    "titel": ("title",),
    "outlets": ("outlet",),
    "landen": ("countr",),
    "claim": ("disinfo", "claim", "summary"),
    "weerlegging": ("fact", "disproof", "rebut", "response", "information"),
}
_ESSENTIEEL = ("datum", "url", "claim", "outlets")


@dataclass(frozen=True)
class Geval:
    datum: str
    url: str
    titel: str
    claim: str
    weerlegging: str
    outlets: tuple[str, ...]
    landen: tuple[str, ...]


def _kolommen(koppen: list[str]) -> dict[str, int]:
    gevonden: dict[str, int] = {}
    laag = [k.strip().casefold() for k in koppen]
    for veld, sleutels in _KOLOMSLEUTELS.items():
        for i, kop in enumerate(laag):
            if any(s in kop for s in sleutels) and i not in gevonden.values():
                gevonden[veld] = i
                break
    ontbrekend = [v for v in _ESSENTIEEL if v not in gevonden]
    if ontbrekend:
        raise ValueError(
            f"kolommen niet gevonden: {ontbrekend}; koppen in het bestand: {koppen}"
        )
    return gevonden


SITE = "https://euvsdisinfo.eu"

_KNOP = "Show more"

# Platforms die de snapshot in de outletkolom noemt. Alleen wat er echt in
# staat en ondubbelzinnig een platform is; yandex.ru is ook een nieuwsportaal
# en blijft een outlet (#25.25).
PLATFORMS = frozenset({"twitter", "t.me", "zen.yandex.ru", "rutube.ru",
                       # de server geeft links, dus domeinen (PLAN #35.3)
                       "twitter.com", "x.com", "telegram.me", "youtube.com", "facebook.com", "instagram.com",
                       "tiktok.com", "vk.com", "ok.ru", "dzen.ru"})


def _soort(naam: str) -> str:
    return "platform" if naam.strip().casefold() in PLATFORMS else "outlet"


def _iso_datum(tekst: str) -> str:
    """De snapshot schrijft dd.mm.yyyy; ClaimReview-datums zijn ISO. Alles wat
    daarna nog ongeldig is, wordt leeg en dus geen bonnetje (DR1)."""
    tekst = tekst.strip()
    delen = tekst.split(".")
    if len(delen) == 3 and all(d.isdigit() for d in delen) and len(delen[2]) == 4:
        dag, maand, jaar = delen
        tekst = f"{jaar}-{int(maand):02d}-{int(dag):02d}"
    return geldige_review_datum(tekst)


def _volledige_url(tekst: str) -> str:
    """Relatieve rapportlinks ('/report/...') worden absolute EUvsDisinfo-URL's."""
    tekst = tekst.strip()
    if tekst.startswith("/"):
        return SITE + tekst
    return tekst


def _splits_outlets(tekst: str) -> list[str]:
    """Outlets staan als lijst in één veld; scheidingstekens variëren."""
    delen: list[str] = []
    for scheiding in (";", "|", "\n"):
        tekst = tekst.replace(scheiding, ",")
    for deel in tekst.split(","):
        deel = deel.strip()
        if deel.endswith(_KNOP):
            deel = deel[: -len(_KNOP)].strip()
        if deel and deel not in delen:
            delen.append(deel)
    return delen


def lees_csv(pad: Path, *, max_gevallen: int | None = None) -> list[Geval]:
    gevallen: list[Geval] = []
    with open(pad, encoding="utf-8", newline="") as f:
        lezer = csv.reader(f)
        koppen = next(lezer)
        kol = _kolommen(koppen)

        def cel(rij: list[str], veld: str) -> str:
            i = kol.get(veld)
            return rij[i].strip() if i is not None and i < len(rij) else ""

        for rij in lezer:
            if not any(rij):
                continue
            gevallen.append(
                Geval(
                    datum=_iso_datum(cel(rij, "datum")),
                    url=_volledige_url(cel(rij, "url")),
                    titel=cel(rij, "titel"),
                    claim=cel(rij, "claim"),
                    weerlegging=cel(rij, "weerlegging"),
                    outlets=tuple(_splits_outlets(cel(rij, "outlets"))),
                    landen=tuple(_splits_outlets(cel(rij, "landen"))),
                )
            )
            if max_gevallen is not None and len(gevallen) >= max_gevallen:
                break
    return gevallen


def naar_rawclaims(gevallen: Iterable[Geval]) -> list[RawClaim]:
    """Een geval wordt een claim met één check. Zonder datum of link geen
    check (DR1), en dan ook geen claim: een bonnetje zonder bon is er geen."""
    raw: list[RawClaim] = []
    for g in gevallen:
        if not g.claim or not g.url or not g.datum:
            continue
        raw.append(
            RawClaim(
                text=g.claim,
                claimant=None,
                claim_date=g.datum,
                factchecks=(
                    RawFactcheck(
                        publisher="EUvsDisinfo",
                        publisher_site="euvsdisinfo.eu",
                        url=g.url,
                        review_date=g.datum,
                        verdict_original="disinformation",
                        language="en",
                    ),
                ),
            )
        )
    return raw


_ALINEA = re.compile(r"</(?:p|div|li|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_LABEL = re.compile(r"<[^>]+>")


def platte_tekst(tekst: str) -> str:
    """HTML van de server als platte tekst: een alinea, regel of lijstpunt eindigt met een spatie, de labels gaan
    eruit, de tekens van HTML (`&amp;`) worden weer wat ze zijn, en alle witruimte wordt één spatie."""
    zonder = _LABEL.sub("", _ALINEA.sub(" ", tekst or ""))
    return " ".join(html.unescape(zonder).split())


def _outlet(url: str) -> str:
    """De site waar EUvsDisinfo de bewering zag: de host van de link, zonder www."""
    host = (urlsplit((url or "").strip()).hostname or "").lower()
    return host.removeprefix("www.")


def uit_server(rij: dict) -> Geval:
    """Een geval zoals de server het geeft, als `Geval`: platte tekst, de dag van de tijdstempel (UTC), de link zonder
    schuine streep aan het eind zoals in de momentopname, en per link naar de desinformatie haar site, elk één keer."""
    ts = rij.get("date")
    datum = (datetime.datetime.fromtimestamp(ts, datetime.UTC).date().isoformat()
             if isinstance(ts, (int, float)) and ts > 0 else "")
    outlets: list[str] = []
    for link in rij.get("linksToDisinformation") or []:
        naam = _outlet(link.get("url") or "")
        if naam and naam not in outlets:
            outlets.append(naam)
    return Geval(datum=geldige_review_datum(datum), url=(rij.get("url") or "").strip().rstrip("/"),
                 titel=platte_tekst(rij.get("title") or ""), claim=platte_tekst(rij.get("claim") or ""),
                 weerlegging=platte_tekst(rij.get("fact") or ""), outlets=tuple(outlets),
                 landen=tuple(c["title"] for c in rij.get("countries") or [] if c.get("title")))


def ophalen(roep: Callable[[int, int], list[dict]], *, sinds: str, bekend: set[str], limit: int = LIMIT,
            pauze: float = PAUZE) -> list[Geval]:
    """De gevallen vanaf `sinds` die niet in `bekend` staan (links), nieuwste eerst. Bladzijde na bladzijde tot de
    eerste met een geval van voor `sinds`, of tot een bladzijde zonder iets nieuws: een geval verschijnt soms weken na
    zijn datum, maar nooit een hele bladzijde later."""
    uit: list[Geval] = []
    gezien = set(bekend)
    offset = 0
    while True:
        rijen = roep(offset, limit)
        nieuw = 0
        klaar = not rijen
        for g in map(uit_server, rijen):
            if g.datum and g.datum < sinds:
                klaar = True
                continue
            if g.url not in gezien:
                uit.append(g)
                gezien.add(g.url)
                nieuw += 1
        if klaar or not nieuw or len(rijen) < limit:
            return uit
        offset += limit
        time.sleep(pauze)


def roep_server(offset: int, limit: int) -> list[dict]:  # pragma: no cover - de server
    """Eén vraag aan de server (JSON-RPC, zonder sessie), met de sleutel uit `.env`."""
    import os
    import urllib.request
    import uuid

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    verzoek = urllib.request.Request(SERVER, data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "cases", "arguments": {"limit": limit, "offset": offset}}}).encode(), headers={
        "Authorization": f"Bearer {os.environ['EUVSDISINFO_API_KEY']}", "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream", "mcp-session-id": str(uuid.uuid4()),
        "User-Agent": "FactizResearch/1.0 (+https://factiz.org)"})
    with urllib.request.urlopen(verzoek, timeout=120) as antwoord:
        ruw = antwoord.read().decode("utf-8")
    regels = [r[5:].strip() for r in ruw.splitlines() if r.startswith("data:")] or [ruw]
    bericht = json.loads(regels[-1])
    if "error" in bericht:
        raise RuntimeError(f"de server zegt: {bericht['error']}")
    return bericht["result"]["structuredContent"]["cases"]


def bewaar(gevallen: Iterable[Geval], pad: Path = OPSLAG) -> int:
    """Zet wat de server gaf bij de rest, elk geval één keer (op zijn link): de weerlegging staat nergens anders, en
    Waarom het niet klopt leest haar hier."""
    al = {g.url for g in bewaarde(pad)}
    nieuw = [g for g in gevallen if g.url not in al]
    if nieuw:
        pad.parent.mkdir(parents=True, exist_ok=True)
        with pad.open("a", encoding="utf-8") as f:
            for g in nieuw:
                f.write(json.dumps(asdict(g), ensure_ascii=False) + "\n")
    return len(nieuw)


def bewaarde(pad: Path = OPSLAG) -> list[Geval]:
    """Wat de server eerder gaf, in de volgorde waarin het binnenkwam."""
    if not pad.is_file():
        return []
    uit = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        if regel.strip():
            r = json.loads(regel)
            uit.append(Geval(**{**r, "outlets": tuple(r["outlets"]), "landen": tuple(r["landen"])}))
    return uit


def nieuw_voor_lab(conn: sqlite3.Connection, gevallen: Iterable[Geval]) -> list[Geval]:
    """De gevallen waarvan het lab de link nog niet heeft, met of zonder schuine streep aan het eind."""
    bekend = {u.rstrip("/") for (u,) in conn.execute(
        "SELECT url FROM factcheck WHERE url LIKE 'https://euvsdisinfo.eu/%'")}
    return [g for g in gevallen if g.url.rstrip("/") not in bekend]


@dataclass(frozen=True)
class AttributieRapport:
    gevallen: int
    attributies_nieuw: int
    outlets_nieuw: int
    claims_zonder_rij: int


def importeer(conn: sqlite3.Connection, gevallen: list[Geval], *, uitgesteld: bool = True,
              herkomst: str = HERKOMST):
    """Registreert de bron (E7.S1), importeert de claims langs de gewone weg
    (taalpoort B14, herkomst 15.3) en hangt per outlet een `waargenomen`-
    attributie aan elke claim die de import heeft toegelaten."""
    from doublecheck.ingest import claim_id_for_text, import_claims

    registreer_bron(conn, **BRON)
    rapport = import_claims(conn, naar_rawclaims(gevallen), source=herkomst, uitgesteld=uitgesteld)

    nieuw = 0
    outlets_nieuw = 0
    zonder_rij = 0
    for g in gevallen:
        if not g.claim or not g.url or not g.datum:
            continue
        claim_id = claim_id_for_text(g.claim)
        bestaat = conn.execute("SELECT 1 FROM claim WHERE claim_id = ?", (claim_id,)).fetchone()
        if not bestaat:
            zonder_rij += 1  # geweigerd door de import (taalpoort, lege tekst): dan ook geen bonnetje
            continue
        for outlet in g.outlets:
            actor_id = vind_actor(conn, outlet)
            if actor_id is None:
                actor_id = registreer_actor(conn, naam=outlet, soort=_soort(outlet))
                outlets_nieuw += 1
            if voeg_attributie(
                conn,
                claim_id=claim_id,
                actor_id=actor_id,
                bron_id=BRON_ID,
                datum=g.datum,
                url=g.url,
                niveau="waargenomen",
                grond="outlet of propagation according to EUvsDisinfo",
            ):
                nieuw += 1
    return rapport, AttributieRapport(len(gevallen), nieuw, outlets_nieuw, zonder_rij)


@dataclass(frozen=True)
class HerstelRapport:
    afgekapt: int       # outlets met de knoptekst aan hun naam
    samengevoegd: int   # waarvan de schone naam al een actor was
    knoppen: int        # de knop als losse "outlet"
    platforms: int      # outlets die een platform zijn
    bonnetjes_weg: int  # dubbelen na het samenvoegen, plus die van de losse knop


def _verhuis(conn: sqlite3.Connection, oud: str, naam: str, soort: str) -> tuple[bool, int]:
    """Alle bonnetjes van actor `oud` naar de actor met `naam` (bestaand of
    nieuw), daarna `oud` weg. Geeft terug of die actor al bestond en hoeveel
    bonnetjes als dubbel vervielen."""
    conn.execute("DELETE FROM actor_alias WHERE actor_id = ?", (oud,))
    bestaand = vind_actor(conn, naam)
    nieuw = bestaand or registreer_actor(conn, naam=naam, soort=soort)
    voor = conn.execute("SELECT count(*) FROM attributie WHERE actor_id = ?", (oud,)).fetchone()[0]
    verhuisd = conn.execute(
        """
        INSERT INTO attributie (claim_id, actor_id, bron_id, datum, url, niveau, grond)
        SELECT claim_id, ?, bron_id, datum, url, niveau, grond FROM attributie WHERE actor_id = ?
        ON CONFLICT(claim_id, actor_id, bron_id, url) DO NOTHING
        """,
        (nieuw, oud),
    ).rowcount
    conn.execute("DELETE FROM attributie WHERE actor_id = ?", (oud,))
    conn.execute("DELETE FROM actor WHERE actor_id = ?", (oud,))
    return bestaand is not None, voor - verhuisd


def herstel(conn: sqlite3.Connection) -> HerstelRapport:
    """Een database die vóór #25.25 is geïmporteerd: de knoptekst uit de
    outletnamen, en platforms als platform. Elk bonnetje gaat mee naar de
    schone actor; alleen een dubbel vervalt, en de losse knop, die geen outlet
    is. Een tweede keer doet niets."""
    afgekapt = samengevoegd = knoppen = platforms = weg = 0
    for actor_id, naam in conn.execute("SELECT actor_id, naam FROM actor WHERE soort = 'outlet'").fetchall():
        if not naam.endswith(_KNOP):
            continue
        schoon = naam[: -len(_KNOP)].strip()
        if not schoon:
            knoppen += 1
            weg += conn.execute("DELETE FROM attributie WHERE actor_id = ?", (actor_id,)).rowcount
            conn.execute("DELETE FROM actor_alias WHERE actor_id = ?", (actor_id,))
            conn.execute("DELETE FROM actor WHERE actor_id = ?", (actor_id,))
            continue
        afgekapt += 1
        bestond, dubbel = _verhuis(conn, actor_id, schoon, _soort(schoon))
        samengevoegd += bestond
        weg += dubbel
    # Pas hierna: een afgekapte "t.meShow more" kan zojuist bij de outlet t.me
    # zijn gekomen.
    for actor_id, naam in conn.execute("SELECT actor_id, naam FROM actor WHERE soort = 'outlet'").fetchall():
        if _soort(naam) == "platform":
            platforms += 1
            weg += _verhuis(conn, actor_id, naam, "platform")[1]
    conn.commit()
    return HerstelRapport(afgekapt, samengevoegd, knoppen, platforms, weg)


def _van_server(conn: sqlite3.Connection) -> None:  # pragma: no cover - de server en het lab
    """Wat de server sinds `VANAF` heeft en het lab nog niet: bewaren, dan importeren met embedden, zodat de index
    van het lab heel blijft. Is de server niet bereikbaar, dan zegt dit dat en gaat de routine verder zonder."""
    import urllib.error

    bekend = {g.url for g in bewaarde()} | {u.rstrip("/") for (u,) in conn.execute(
        "SELECT url FROM factcheck WHERE url LIKE 'https://euvsdisinfo.eu/%'")}
    try:
        gevallen = ophalen(roep_server, sinds=VANAF, bekend=bekend)
    except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, ValueError) as fout:
        print(f"EUvsDisinfo: de server gaf geen gevallen ({type(fout).__name__}: {str(fout)[:200]}); niets nieuw")
        return
    bewaar(gevallen)
    voor_lab = nieuw_voor_lab(conn, bewaarde())
    if not voor_lab:
        print(f"EUvsDisinfo: niets nieuw sinds {VANAF}")
        return
    rapport, attr = importeer(conn, voor_lab, uitgesteld=False, herkomst=HERKOMST_SERVER)
    dagen = sorted(g.datum for g in voor_lab if g.datum)
    print(f"EUvsDisinfo: {len(voor_lab)} nieuwe gevallen ({dagen[0] if dagen else '?'} tot {dagen[-1] if dagen else '?'}); "
          f"import: {rapport}; attributies nieuw: {attr.attributies_nieuw}")


def main() -> None:
    import os

    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="EUvsDisinfo-snapshot importeren (E7.S4)")
    parser.add_argument("--bestand", type=Path)
    parser.add_argument("--herstel", action="store_true",
                        help="een database van vóór #25.25 in orde brengen: knoptekst en platforms")
    parser.add_argument("--max", type=int, default=None, help="alleen de eerste N gevallen")
    parser.add_argument("--embed", action="store_true", help="direct embedden i.p.v. reindex later")
    parser.add_argument("--server", action="store_true",
                        help=f"de nieuwe gevallen vanaf {VANAF} van de server ophalen en in het lab zetten (PLAN #35.3)")
    args = parser.parse_args()

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    init_schema(conn)  # additief: maakt de attributietabellen aan in een bestaande database
    if args.herstel:
        print(herstel(conn))
        return
    if args.server:
        _van_server(conn)
        return
    if args.bestand is None:
        parser.error("--bestand is nodig, behalve bij --herstel")
    gevallen = lees_csv(args.bestand, max_gevallen=args.max)
    rapport, attr = importeer(conn, gevallen, uitgesteld=not args.embed)
    met, totaal, aandeel = aandeel_met_attributie(conn)
    print(f"gevallen gelezen: {attr.gevallen}")
    print(f"import: {rapport}")
    print(f"attributies nieuw: {attr.attributies_nieuw}, outlets nieuw: {attr.outlets_nieuw}, "
          f"claims zonder rij (geweigerd): {attr.claims_zonder_rij}")
    print(f"poortcijfer: {met} van {totaal} claims met attributie ({aandeel:.1%})")
    if not args.embed:
        print("Nu: python -m doublecheck.reindex  (embedt de nieuwe claims), daarna de "
              "poortwachters: benchmark (B14, alle markten) en uitgeverkwaliteit.")


if __name__ == "__main__":
    main()
