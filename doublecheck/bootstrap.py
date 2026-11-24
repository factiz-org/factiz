"""Van schone kloon naar werkend corpus, met één commando *(PLAN.md #15.3, B13)*.

De repo levert geen database. Dat is geen omissie: het corpus bestaat uit
factchecks van andermans uitgevers, en wat wij mogen doorgeven is niet het
materiaal maar de weg ernaartoe. Die weg is deze module.

**De bron staat hier, niet in iemands hoofd.** Tot 15.3 stond de feed-URL
nergens in de repo — `feed.py` vroeg om "het gedownloade data.json" en liet in
het midden waarvandaan. Een specificatie met een onvindbare grondstof is geen
open source maar een demo.

**Ramen vóór draaien.** Dit commando haalt ~190 MB op en embedt tienduizenden
claims. `plan()` zegt dat eerst, met de bron en de omvang erbij. Dat is een les
uit de clusteringrun die 76 minuten op 273% CPU stond omdat de raming pas
achteraf gemaakt werd (BENCHMARK.md §38).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from doublecheck.feed import API_GEBONDEN, HERDISTRIBUEERBAAR, parse_feed

# De CC BY-compilatie van Data Commons. De Fact Check Tools API levert dezelfde
# data onder voorwaarden die herdistributie, databases én afgeleide werken
# verbieden — zie PROTOCOL.md §11.5 voor de vergelijking.
FEED_URL = "https://storage.googleapis.com/datacommons-feeds/claimreview/latest/data.json"

STANDAARD_CACHE = Path("data/datacommons-claimreview.json")
STANDAARD_DB = "doublecheck.db"


# ---------------------------------------------------------------------------
# Herkomst: wat mag mee naar buiten
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HerkomstRapport:
    totaal: int
    herdistribueerbaar: int
    gebonden: int
    per_bron: dict[str, int]
    # Attributies uit een bron die niet herverdeeld mag worden (E7.S1-AC2),
    # per bronnaam; Community Notes valt hieronder (#25.16).
    gebonden_attributies: dict[str, int] = field(default_factory=dict)
    # De herkomsten die mee mogen: de CC BY-feed, plus elke bron die het
    # register herverdeelbaar noemt (EUvsDisinfo, "euvsdisinfo:…").
    vrij: frozenset[str] = frozenset({HERDISTRIBUEERBAAR})

    @property
    def mag_uitgegeven_worden(self) -> bool:
        """Eén gebonden record is genoeg om de hele uitgave te blokkeren."""
        return self.gebonden == 0 and not self.gebonden_attributies and self.totaal > 0

    def toelichting(self) -> str:
        regels = [f"{self.totaal} factchecks, verdeeld over {len(self.per_bron)} bron(nen):"]
        for bron, aantal in sorted(self.per_bron.items(), key=lambda p: -p[1]):
            merk = "  mag mee" if bron in self.vrij else "  GEBONDEN"
            regels.append(f"  {aantal:>8}  {bron:<24}{merk}")
        for bron, aantal in sorted(self.gebonden_attributies.items()):
            regels.append(f"  {aantal:>8}  attributies uit {bron}  GEBONDEN (niet herverdeelbaar)")
        if self.gebonden_attributies and not self.gebonden:
            regels.append("")
            regels.append(
                "NIET UITGEEFBAAR — attributies uit een bron die niet herverdeeld mag worden"
                " (bronregister, E7.S1-AC2). Geef een database zonder die bron uit."
            )
        if self.gebonden:
            gebonden = sorted(b for b in self.per_bron if b not in self.vrij)
            regels.append("")
            regels.append(
                f"NIET UITGEEFBAAR — {self.gebonden} record(s) uit een gebonden bron "
                f"({', '.join(gebonden)})."
                + (" De Fact Check Tools API verbiedt herdistributie, databases en afgeleide"
                   " werken (B13). Bouw het corpus opnieuw met `python -m doublecheck.bootstrap`."
                   if API_GEBONDEN in gebonden else
                   " Het bronregister noemt die bron niet herverdeelbaar (E7.S1-AC2).")
            )
        elif self.mag_uitgegeven_worden:
            regels.append("")
            regels.append("Uitgeefbaar — alles mag volgens feed en bronregister herverdeeld worden.")
        return "\n".join(regels)


def herkomstrapport(conn: sqlite3.Connection) -> HerkomstRapport:
    """Waar komt alles in deze database vandaan?

    Dit is de reden dat `factcheck.source` verplicht is (#14.5). Een uitgave
    controleren op licentie moet een commando zijn, geen geheugenoefening.
    """
    per_bron = {
        rij[0]: rij[1]
        for rij in conn.execute(
            "SELECT source, count(*) FROM factcheck GROUP BY source"
        )
    }
    totaal = sum(per_bron.values())
    # Een herkomst als "euvsdisinfo:mendeley-…" hoort bij bron "euvsdisinfo";
    # mag die volgens het register herverdeeld worden, dan mag de check mee.
    herverdeelbare_bronnen = {
        rij[0] for rij in conn.execute("SELECT bron_id FROM bron WHERE herverdeelbaar = 1")
    }
    vrij = frozenset({HERDISTRIBUEERBAAR} | {
        bron for bron in per_bron if bron.split(":", 1)[0] in herverdeelbare_bronnen
    })
    herdistribueerbaar = sum(aantal for bron, aantal in per_bron.items() if bron in vrij)
    gebonden_attributies = {
        rij[0]: rij[1]
        for rij in conn.execute(
            "SELECT b.naam, count(*) FROM attributie a JOIN bron b ON b.bron_id = a.bron_id"
            " WHERE b.herverdeelbaar = 0 GROUP BY b.naam"
        )
    }
    return HerkomstRapport(
        totaal=totaal,
        herdistribueerbaar=herdistribueerbaar,
        gebonden=totaal - herdistribueerbaar,
        per_bron=per_bron,
        gebonden_attributies=gebonden_attributies,
        vrij=vrij,
    )


# ---------------------------------------------------------------------------
# Ophalen
# ---------------------------------------------------------------------------


def _feedgrootte(url: str) -> int | None:
    """Omvang van de feed, zonder hem op te halen. `None` als dat niet lukt."""
    import urllib.request

    try:
        verzoek = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(verzoek, timeout=30) as antwoord:
            lengte = antwoord.headers.get("Content-Length")
        return int(lengte) if lengte else None
    except Exception:
        return None


def download_bestand(url: str, doel: Path, voortgang=None) -> Path:
    """Haalt de feed op naar `doel`.

    Schrijft eerst naar `.deel` en hernoemt pas na afloop: een afgebroken
    download laat anders een half bestand achter dat er compleet uitziet en bij
    de volgende run stilzwijgend hergebruikt wordt.
    """
    import urllib.request

    doel.parent.mkdir(parents=True, exist_ok=True)
    tijdelijk = doel.with_suffix(doel.suffix + ".deel")
    with urllib.request.urlopen(url, timeout=120) as antwoord, open(tijdelijk, "wb") as uit:
        totaal = int(antwoord.headers.get("Content-Length") or 0)
        gehaald = 0
        while blok := antwoord.read(1 << 20):
            uit.write(blok)
            gehaald += len(blok)
            if voortgang is not None:
                voortgang(gehaald, totaal)
    tijdelijk.replace(doel)
    return doel


# ---------------------------------------------------------------------------
# Plannen en uitvoeren
# ---------------------------------------------------------------------------


def _mb(bytes_: int) -> str:
    return f"{bytes_ / 1024 / 1024:.0f} MB"


def plan(
    *,
    db: str = STANDAARD_DB,
    cache: Path = STANDAARD_CACHE,
    url: str = FEED_URL,
    max_claims: int | None = None,
    groottelezer=_feedgrootte,
) -> list[str]:
    """Wat dit commando gaat doen, vóórdat het iets doet. Raakt niets aan."""
    cache = Path(cache)
    regels = ["Bootstrap corpus — wat er gaat gebeuren:", ""]

    if cache.exists():
        regels.append(f"1. feed hergebruiken uit {cache} ({_mb(cache.stat().st_size)})")
    else:
        grootte = groottelezer(url)
        omvang = _mb(grootte) if grootte else "omvang onbekend"
        regels.append(f"1. feed downloaden — {omvang}")
        regels.append(f"   {url}")
        regels.append(f"   naar {cache}")

    hoeveel = f"de eerste {max_claims}" if max_claims else "alle"
    regels += [
        f"2. {hoeveel} claims importeren in {db}, zonder embedden",
        "3. embedden in batches (het zware deel; minuten tot uren op het volle corpus)",
        "4. clusteren op de configdrempel",
        "",
        "Licentie: de feed staat onder CC BY 4.0. Wie het corpus doorgeeft,",
        "vermeldt de uitgevers — elke factcheck draagt uitgever en verwijzing.",
    ]
    return regels


@dataclass(frozen=True)
class BootstrapRapport:
    feed_claims: int
    claims: int
    checks: int
    geweigerd: int
    fingerprints: int
    clusters: int


def bootstrap(
    *,
    db: str = STANDAARD_DB,
    cache: Path = STANDAARD_CACHE,
    url: str = FEED_URL,
    max_claims: int | None = None,
    vernieuw: bool = False,
    downloader=download_bestand,
    fingerprinter=None,
    veto=None,
    voortgang=None,
    meldkorrel: int = 5000,
) -> BootstrapRapport:
    """Bouwt een werkend corpus uit de CC BY-feed — of vult een bestaand
    corpus idempotent bij (#22.2): claims dedupliceren op claim_id, checks op
    (claim_id, url), dus dezelfde feed nogmaals importeren voegt niets toe.

    `veto=None` betekent clusteren zonder NLI-veto: deze functie laadt uit
    zichzelf nooit een model dat de aanroeper niet gevraagd heeft.
    `vernieuw=True` haalt de feed opnieuw op ook als de cache bestaat — de
    cache-hergebruik is voor de schone kloon een feature en voor de
    versheidscadans een val. Elke run wordt vastgelegd in `importrun`.
    """
    import json
    from datetime import datetime, timezone

    from doublecheck.clustering import build_clusters
    from doublecheck.config import load_config
    from doublecheck.ingest import import_claims
    from doublecheck.reindex import reindex_text
    from doublecheck.storage import connect, init_schema, registreer_importrun

    def meld(regel: str) -> None:
        if voortgang is not None:
            voortgang(regel)

    gestart = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache = Path(cache)
    if cache.exists() and not vernieuw:
        meld(f"feed al aanwezig: {cache} ({_mb(cache.stat().st_size)})")
    else:
        meld(f"feed {'vernieuwen' if cache.exists() else 'ophalen'} van {url}")
        downloader(url, cache)

    feed = json.loads(cache.read_text(encoding="utf-8"))
    claims = parse_feed(feed)
    meld(f"feed gelezen: {len(claims)} ClaimReviews met claimtekst")
    gebruikt = claims[:max_claims] if max_claims else claims

    config = load_config()
    conn = connect(db)
    init_schema(conn)
    # Een corpus uit de feed draagt de witte lijst van uitgevers (B28): anders
    # zou een schone kloon stil elke host toelaten.
    from doublecheck.toelating import zet_aan

    zet_aan(conn)
    try:
        # Uitgesteld embedden: stuk voor stuk kost 28 s per duizend claims, de
        # gebatchte herindexering daarna is orden sneller (#14.4).
        rapport = import_claims(
            conn, gebruikt, source=HERDISTRIBUEERBAAR, uitgesteld=True
        )
        meld(
            f"geïmporteerd: {rapport.accepted_claims} claims, "
            f"{rapport.accepted_factchecks} checks, "
            f"{len(rapport.refusals)} geweigerd"
        )

        argumenten = {} if fingerprinter is None else {"fingerprinter": fingerprinter}

        # Melden bij het passeren van een korrel, niet bij `gedaan % korrel == 0`.
        # `reindex_text` werkt in batches van 256, en 5.000 is daar geen veelvoud
        # van: de eerste versie zweeg tien minuten lang (#15.3).
        gemeld = [0]

        def voortgang_embedden(gedaan: int, totaal: int) -> None:
            if voortgang is None:
                return
            if gedaan - gemeld[0] >= meldkorrel or gedaan == totaal:
                gemeld[0] = gedaan
                meld(f"  embedden {gedaan}/{totaal}")

        herindex = reindex_text(
            conn,
            config.model_versions.text_embedding,
            voortgang=voortgang_embedden,
            **argumenten,
        )
        meld(f"geëmbed: {herindex.nieuwe_fingerprints} nieuwe fingerprints")

        clusters = build_clusters(
            conn,
            config.model_versions.text_embedding,
            config.thresholds.cluster_same,
            veto=veto,
        )
        meld(f"geclusterd: {clusters.clusters} clusters uit {clusters.claims} claims")

        registreer_importrun(
            conn, gestart_op=gestart, bron=url, rapport=rapport,
            nieuwe_fingerprints=herindex.nieuwe_fingerprints,
        )

        return BootstrapRapport(
            feed_claims=len(claims),
            claims=rapport.accepted_claims,
            checks=rapport.accepted_factchecks,
            geweigerd=len(rapport.refusals),
            fingerprints=herindex.nieuwe_fingerprints,
            clusters=clusters.clusters,
        )
    finally:
        conn.close()


def main() -> None:
    import argparse

    from doublecheck.storage import connect, importruns, init_schema

    parser = argparse.ArgumentParser(
        prog="python -m doublecheck.bootstrap",
        description="Schone kloon → werkend corpus, uit de CC BY-feed (#15.3);"
                    " met --vernieuw de versheidscadans (#22.2).",
    )
    parser.add_argument("--db", default=STANDAARD_DB)
    parser.add_argument("--cache", default=str(STANDAARD_CACHE),
                        help="waar de opgehaalde feed blijft staan")
    parser.add_argument("--url", default=FEED_URL)
    parser.add_argument("--max", type=int, default=None,
                        help="alleen de eerste N claims — voor een snelle proef")
    parser.add_argument("--met-veto", action="store_true",
                        help="clusteren mét het NLI-veto (langzamer; zie §44)")
    parser.add_argument("--plan", action="store_true",
                        help="alleen zeggen wat er gaat gebeuren")
    parser.add_argument("--herkomst", action="store_true",
                        help="alleen melden waar de inhoud van --db vandaan komt")
    parser.add_argument("--vernieuw", action="store_true",
                        help="haal de feed opnieuw op, ook als de cache bestaat"
                             " (#22.2, de versheidscadans)")
    parser.add_argument("--runs", action="store_true",
                        help="alleen de jongste herimportruns tonen")
    args = parser.parse_args()

    if args.runs:
        conn = connect(args.db)
        init_schema(conn)
        rijen = importruns(conn)
        if not rijen:
            print("nog geen herimportruns vastgelegd")
        for run in rijen:
            print(f"[{run['run_id']}] {run['gestart_op']}"
                  f"  +{run['nieuwe_claims']} claims"
                  f" +{run['nieuwe_factchecks']} checks"
                  f"  {run['geweigerd']} geweigerd  ({run['bron']})")
        conn.close()
        return

    if args.herkomst:
        conn = connect(args.db)
        init_schema(conn)
        print(herkomstrapport(conn).toelichting())
        conn.close()
        return

    for regel in plan(db=args.db, cache=Path(args.cache), url=args.url,
                      max_claims=args.max):
        print(regel)
    if args.plan:
        return
    print()

    veto = None
    if args.met_veto:
        from doublecheck.config import load_config
        from doublecheck.nli import same_language_veto

        config = load_config()
        veto = same_language_veto(
            config.model_versions.nli, config.thresholds.nli_contradiction
        )

    rapport = bootstrap(db=args.db, cache=Path(args.cache), url=args.url,
                        max_claims=args.max, vernieuw=args.vernieuw,
                        veto=veto, voortgang=print)
    print()
    print(f"klaar: {rapport.claims} claims in {args.db}")

    conn = connect(args.db)
    print()
    print(herkomstrapport(conn).toelichting())
    conn.close()


if __name__ == "__main__":
    main()
