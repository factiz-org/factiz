"""Rommel uit de index (#25.2, #25.19): claims die geen bewering zijn of
alleen van geweerde bronnen komen.

Nooit stil. Zonder `--uitvoeren` is het een rapport. Met `--uitvoeren` wordt
eerst een rapportbestand geschreven met elke verwijderde claim en zijn
bonnetjes, en pas dan verwijderd (claims met hun checks, fingerprints en
bonnetjes via ON DELETE CASCADE). Een claim die in de testset zit wordt
nooit weggehaald: dat zou de benchmark stil veranderen.

De maat is dezelfde als de weigerregel bij de import (`is_geen_bewering`),
zodat wat nu wordt opgeruimd ook niet terugkomt.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from doublecheck.ingest import is_geen_bewering
from doublecheck.uitgeverkwaliteit import is_geweerd, is_geweerde_host


@dataclass(frozen=True)
class Rommel:
    claim_id: str
    tekst: str
    taal: str
    checks: tuple[str, ...]
    # "geen_bewering" (#25.2), "geweerde_uitgever" (#25.19 a: elke check komt
    # van een uitgever die op naam geweerd is) of "geweerde_host" (#25.19 b:
    # elke check is geweerd, minstens één op zijn host).
    reden: str = "geen_bewering"


@dataclass(frozen=True)
class LosseCheck:
    """Een geweerde check bij een claim die blijft, omdat een echte redactie
    hem ook checkte: alleen de rij gaat weg (#25.19 b)."""
    claim_id: str
    url: str
    uitgever: str


def _geweerd(url: str, uitgever: str) -> bool:
    return is_geweerd(uitgever) or is_geweerde_host(url)


def vind_rommel(conn: sqlite3.Connection) -> list[Rommel]:
    """Dezelfde twee regels als de weigering bij de import, zodat wat nu
    wordt opgeruimd ook niet terugkomt."""
    checks: dict[str, list[tuple[str, str]]] = {}
    for claim_id, url, uitgever in conn.execute(
            "SELECT claim_id, url, publisher FROM factcheck ORDER BY url"):
        checks.setdefault(claim_id, []).append((url, uitgever))
    gevonden: list[Rommel] = []
    for claim_id, tekst, taal in conn.execute("SELECT claim_id, canonical_text, language FROM claim"):
        eigen = checks.get(claim_id, [])
        urls = tuple(url for url, _ in eigen)
        if is_geen_bewering(tekst):
            gevonden.append(Rommel(claim_id, tekst, taal, urls, "geen_bewering"))
        elif eigen and all(_geweerd(url, uitgever) for url, uitgever in eigen):
            reden = "geweerde_host" if any(is_geweerde_host(url) for url, _ in eigen) else "geweerde_uitgever"
            gevonden.append(Rommel(claim_id, tekst, taal, urls, reden))
    return gevonden


def vind_geweerde_checks(conn: sqlite3.Connection) -> list[LosseCheck]:
    """Geweerde checks bij claims die blijven: de claim heeft ook een echte
    check en is een bewering. De claims zelf vindt `vind_rommel`."""
    rommel = {r.claim_id for r in vind_rommel(conn)}
    per_claim: dict[str, list[tuple[str, str]]] = {}
    for claim_id, url, uitgever in conn.execute(
            "SELECT claim_id, url, publisher FROM factcheck ORDER BY claim_id, url"):
        per_claim.setdefault(claim_id, []).append((url, uitgever))
    return [LosseCheck(claim_id, url, uitgever)
            for claim_id, eigen in per_claim.items() if claim_id not in rommel
            for url, uitgever in eigen if _geweerd(url, uitgever)]


def haal_uit_testset(conn: sqlite3.Connection, claim_ids, *, rapportpad: Path,
                     reden: str = "testparen die naar rommel verwijzen; de benchmark verandert hierdoor bewust") -> int:
    """De testparen die naar deze claims verwijzen, als eigen, bewuste stap
    (PO 2026-10-13): eerst een rapport van elk paar, dan weg. Ook een
    hardste-buur die zo'n claim als buur heeft. Het verandert de benchmark: een
    volgende run is niet één op één vergelijkbaar met een run van daarvóór."""
    ids = list(claim_ids)
    if not ids:
        return 0
    plekken = ",".join("?" * len(ids))
    paren = conn.execute(
        f"SELECT testpair_id, claim_id, is_same, provenance, language FROM testpair"
        f" WHERE claim_id IN ({plekken}) OR provenance IN ({plekken}) ORDER BY testpair_id",
        ids + [f"hardste-buur:{i}" for i in ids],
    ).fetchall()
    if not paren:
        return 0
    rapportpad = Path(rapportpad)
    if rapportpad.exists():
        raise FileExistsError(f"{rapportpad} bestaat al; het rapport van een eerdere ronde blijft staan")
    rapportpad.parent.mkdir(parents=True, exist_ok=True)
    rapportpad.write_text(json.dumps({
        "datum": date.today().isoformat(),
        "reden": reden,
        "aantal": len(paren),
        "verwijderd": [dict(zip(("testpair_id", "claim_id", "is_same", "provenance", "language"), tuple(p)))
                       for p in paren],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with conn:
        conn.executemany("DELETE FROM testpair WHERE testpair_id = ?", [(p[0],) for p in paren])
    return len(paren)


def ruim_op(conn: sqlite3.Connection, rommel: list[Rommel], *, rapportpad: Path,
            losse_checks: list[LosseCheck] = ()) -> int:
    ids = [r.claim_id for r in rommel]
    if not ids and not losse_checks:
        return 0
    plekken = ",".join("?" * len(ids))
    in_testset = ids and conn.execute(
        f"SELECT count(*) FROM testpair WHERE claim_id IN ({plekken})"
        f" OR provenance IN ({plekken})",
        ids + [f"hardste-buur:{i}" for i in ids],
    ).fetchone()[0]
    if in_testset:
        raise ValueError(
            f"{in_testset} testpaar/paren verwijzen naar deze claims; weghalen zou de"
            " benchmark stil veranderen. Haal ze eerst bewust uit de testset."
        )
    rapportpad = Path(rapportpad)
    if rapportpad.exists():
        raise FileExistsError(f"{rapportpad} bestaat al; het rapport van een eerdere ronde blijft staan")
    rapportpad.parent.mkdir(parents=True, exist_ok=True)
    rapportpad.write_text(json.dumps({
        "datum": date.today().isoformat(),
        "regels": {
            "geen_bewering": "is_geen_bewering (#25.2): één woord in een schrift met spaties, of een labelzin",
            "geweerde_uitgever": "elke check komt van een uitgever die op naam geweerd is (#25.19)",
            "geweerde_host": "elke check is geweerd, minstens één op zijn host (#25.19 b)",
            "losse_checks": "een geweerde check bij een claim die een echte redactie ook checkte; alleen de rij gaat weg",
        },
        "aantal": len(rommel),
        "verwijderd": [asdict(r) | {"checks": list(r.checks)} for r in rommel],
        "losse_checks": [asdict(c) for c in losse_checks],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with conn:
        conn.executemany("DELETE FROM claim WHERE claim_id = ?", [(i,) for i in ids])
        conn.executemany("DELETE FROM factcheck WHERE claim_id = ? AND url = ?",
                         [(c.claim_id, c.url) for c in losse_checks])
    return len(ids)


def main() -> None:
    import argparse
    import os

    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Rommel uit de index (#25.2)")
    parser.add_argument("--uitvoeren", action="store_true", help="echt verwijderen (anders alleen rapport)")
    parser.add_argument("--testparen-eerst", action="store_true",
                        help="bewust: eerst de testparen die naar rommel verwijzen weghalen, met een rapport")
    args = parser.parse_args()
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    rommel = vind_rommel(conn)
    checks = sum(len(r.checks) for r in rommel)
    import collections

    per_reden = collections.Counter(r.reden for r in rommel)
    losse = vind_geweerde_checks(conn)
    print(f"rommel: {len(rommel)} claims met {checks} checks · {dict(per_reden)}"
          f" · losse geweerde checks bij echte claims: {len(losse)}")
    for r in sorted(rommel, key=lambda r: -len(r.checks))[:15]:
        print(f"  {len(r.checks):>3}  [{r.taal}] {r.tekst[:60]!r}")
    if args.uitvoeren:
        from datetime import datetime

        stempel = datetime.now().strftime('%Y-%m-%dT%H%M%S')
        if args.testparen_eerst:
            paarpad = Path("data") / f"testparen-weg-{stempel}.json"
            print(f"testparen weggehaald: {haal_uit_testset(conn, [r.claim_id for r in rommel], rapportpad=paarpad)}; rapport: {paarpad}")
        pad = Path("data") / f"opruimrapport-{stempel}.json"
        n = ruim_op(conn, rommel, rapportpad=pad, losse_checks=losse)
        print(f"verwijderd: {n} claims en {len(losse)} losse checks; rapport: {pad}")
    else:
        print("droogloop: niets verwijderd (gebruik --uitvoeren)")


if __name__ == "__main__":
    main()
