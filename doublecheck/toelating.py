"""Wat de index toelaat (B28, SPECS E2.S6).

Buiten de index is niet weg. Claim en checks blijven in de database, als
bonnetje; wie de claim zelf opvraagt, ziet hem nog. Maar het zoeken slaat hem
over (resolver, batchcontrole, varianten, beeld), en zijn checks tellen niet
mee in het bewijs van een cluster.

**Vage claims (#25.28).** Een claimtekst die niets toetsbaars zegt, een
onderschrift, een groet, "Something to think about.", trekt elke gewone zin
aan die erop lijkt: 54 van de 76 trekkers op mC4 waren vaag, en ze verklaarden
7 van de 12 valse vlaggen (BENCHMARK §99). De lijst staat in
`vage_claims.json` en is gelijk aan de labels *vaag* van de trekkersmeting;
`python -m doublecheck.vaagmeting toepassen` schrijft hem. Een claim-id is de
hash van de tekst, dus de lijst geldt ook in een schone kloon.

**Een witte lijst van uitgevers (#25.29).** Iedereen mag ClaimReview
publiceren en niemand controleert het: in de feed stonden winkelrecensies, een
casino-app en proefsites naast echte redacties. In een database die de
toelating draagt (een rij in `toelating`), is een claim alleen vindbaar met een
check van een host uit het uitgeversregister, en tonen antwoorden alleen zulke
checks. Het register is met de hand nagekeken
(`docs/steekproeven/25.29-uitgevers.json`); een nieuwe host wacht in
`te_beoordelen`. Een corpus uit `bootstrap` draagt de toelating; de
testdatabases van de suite niet, daar zijn de hosts verzonnen.

**Geen afgeleide tabel.** Het zoeken leest de lijsten bij het bouwen van de
matrix, en die bouw hangt al aan de stand van de database (search.py): een
import of `zet_aan` maakt hem vanzelf opnieuw. Een tabel die na elke import en
elke lijstwijziging opnieuw berekend moet worden, is de faalklasse "afgeleide
staat die veroudert zonder dat iets het merkt" (§17a, §39, §45).

    python -m doublecheck.toelating [aan] [--testparen-weg]
"""

from __future__ import annotations

import functools
import json
import sqlite3
from pathlib import Path

VAGE_CLAIMS_PATH = Path(__file__).parent / "vage_claims.json"


@functools.cache
def vage_claims(path: Path = VAGE_CLAIMS_PATH) -> frozenset[str]:
    if not Path(path).exists():
        return frozenset()
    return frozenset(json.loads(Path(path).read_text(encoding="utf-8"))["claims"])


@functools.cache
def register() -> dict[str, str]:
    """Het nagekeken register, één keer per proces gelezen: het verandert
    alleen met een uitrol, net als de config."""
    from doublecheck.uitgevers import load_hosts

    return load_hosts()


def staat_aan(conn: sqlite3.Connection) -> bool:
    try:
        return conn.execute("SELECT 1 FROM toelating").fetchone() is not None
    except sqlite3.OperationalError:
        # Een database van vóór de tabel, alleen-lezend geopend.
        return False


def zet_aan(conn: sqlite3.Connection) -> None:
    from datetime import datetime, timezone

    with conn:
        conn.execute("INSERT OR IGNORE INTO toelating (id, sinds) VALUES (1, ?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"),))


def toegelaten(conn: sqlite3.Connection, url: str) -> bool:
    """Mag deze check als bonnetje in het antwoord (SPECS E2.S6-AC3)?"""
    from doublecheck.evidence import _host

    return not staat_aan(conn) or (_host(url) or "") in register()


def _bereken(conn: sqlite3.Connection) -> frozenset[str]:
    buiten = set(vage_claims())
    if staat_aan(conn):
        from doublecheck.evidence import _host

        hosts = register()
        met_redactie = {claim_id for claim_id, url in conn.execute("SELECT claim_id, url FROM factcheck")
                        if (_host(url) or "") in hosts}
        buiten |= {r[0] for r in conn.execute("SELECT claim_id FROM claim")} - met_redactie
    return frozenset(buiten)


def buiten_index(conn: sqlite3.Connection) -> frozenset[str]:
    """De claim-ids die het zoeken overslaat. In dezelfde cache als de
    matrix: één berekening per stand van de database."""
    from doublecheck.search import _gecachet

    return _gecachet(conn, "buiten_index", lambda: _bereken(conn))


def per_reden(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Voor het rapport: welke aanwezige claims waarom buiten de index staan.
    Een vage claim van een onbekende uitgever telt als vaag."""
    aanwezig = {r[0] for r in conn.execute("SELECT claim_id FROM claim")}
    vaag = set(vage_claims()) & aanwezig
    return {"vaag": vaag, "onbekende_uitgever": (set(buiten_index(conn)) & aanwezig) - vaag}


def testparen_buiten_index(conn: sqlite3.Connection) -> list[tuple]:
    """Testparen op een claim buiten de index, ook een hardste buur die er
    een als buur heeft. Die meten iets wat de resolver niet meer kan vinden."""
    buiten = buiten_index(conn)
    return [rij for rij in conn.execute(
        "SELECT testpair_id, claim_id, is_same, provenance, language FROM testpair ORDER BY testpair_id")
        if rij[1] in buiten or (rij[3].startswith("hardste-buur:") and rij[3].split(":", 1)[1] in buiten)]


def haal_testparen_weg(conn: sqlite3.Connection, *, rapportpad: Path) -> int:
    """Als eigen, bewuste stap, met een rapport van elk paar: het verandert
    de benchmark (zoals bij de rommel, #28.6 g)."""
    from doublecheck.opruimen import haal_uit_testset

    buiten = buiten_index(conn)
    ids = set()
    for _, claim_id, _, herkomst, _ in testparen_buiten_index(conn):
        buur = herkomst.split(":", 1)[1] if herkomst.startswith("hardste-buur:") else None
        # Alleen de claim buiten de index: een paar op een gewone claim met
        # een vage buur gaat weg via die buur, de andere paren blijven.
        ids |= {c for c in (claim_id, buur) if c in buiten}
    return haal_uit_testset(conn, sorted(ids), rapportpad=rapportpad,
                            reden="testparen op een claim buiten de index (B28); de benchmark verandert hierdoor bewust")


def main() -> None:
    import argparse
    import os
    from datetime import datetime

    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Wat de index toelaat (B28)")
    parser.add_argument("stap", nargs="?", choices=("aan",),
                        help="aan: de witte lijst van uitgevers geldt voor deze database")
    parser.add_argument("--testparen-weg", action="store_true",
                        help="bewust: de testparen op een claim buiten de index weghalen, met een rapport")
    args = parser.parse_args()
    from doublecheck.storage import init_schema

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    init_schema(conn)
    if args.stap == "aan":
        zet_aan(conn)
    print(f"witte lijst van uitgevers: {'aan' if staat_aan(conn) else 'uit'} ({len(register())} hosts)")
    for reden, ids in per_reden(conn).items():
        checks = sum(conn.execute(f"SELECT count(*) FROM factcheck WHERE claim_id IN ({','.join('?' * len(deel))})",
                                  deel).fetchone()[0]
                     for deel in (sorted(ids)[i:i + 900] for i in range(0, len(ids), 900)))
        print(f"buiten de index, {reden}: {len(ids)} claims met {checks} checks")
    from doublecheck.evidence import _host

    hosts = register()
    verborgen = sum((_host(url) or "") not in hosts
                    for (url,) in conn.execute("SELECT url FROM factcheck")) if staat_aan(conn) else 0
    print(f"checks die geen bonnetje meer zijn (host buiten het register): {verborgen}")
    paren = testparen_buiten_index(conn)
    print(f"testparen op een claim buiten de index: {len(paren)}")
    if args.testparen_weg and paren:
        pad = Path("data") / f"testparen-weg-{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json"
        print(f"testparen weggehaald: {haal_testparen_weg(conn, rapportpad=pad)}; rapport: {pad}")


if __name__ == "__main__":
    main()
