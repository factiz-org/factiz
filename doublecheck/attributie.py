"""Attributie als bonnetje (DR10, B23, #24.6).

Een attributie zegt bij welke actor een claim verscheen (`waargenomen`) of
aan welke operatie een bron hem toeschreef (`toegeschreven`), altijd mét bron,
datum, link en bewijsniveau. Het systeem leidt zelf nooit een attributie af;
het bewaart wie het zei. De categorisering en de DR7-telling lezen deze tabel
niet (E7.S2-AC2): een attributie is context naast het oordeel.

Aliassen: dezelfde operatie heet bij drie onderzoekers anders. `vind_actor`
reconcilieert via een sleutel die alleen hoofdletters en witruimte gladstrijkt;
alles daarbuiten ("Storm-1679" tegenover "Storm 1679") is een aliasbesluit dat
iemand expliciet registreert, geen normalisatie die stilletjes samenvoegt.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Iterable

BRONSOORTEN = ("factchecker", "overheid", "tracker", "onderzoek", "platform")
ACTORSOORTEN = ("operatie", "outlet", "netwerk", "platform")
NIVEAUS = ("waargenomen", "toegeschreven")


def _sleutel(naam: str) -> str:
    """Reconciliatiesleutel: casefold en witruimte samenvouwen, verder niets."""
    return " ".join(naam.casefold().split())


def actor_id_voor(naam: str, soort: str) -> str:
    """Stabiel, schriftonafhankelijk id: een hash van soort en sleutel, zodat een
    Cyrillische of Arabische outletnaam nooit tot een lege slug verschraalt."""
    digest = hashlib.sha256(f"{soort}\n{_sleutel(naam)}".encode("utf-8")).hexdigest()
    return f"{soort}:{digest[:12]}"


def registreer_bron(
    conn: sqlite3.Connection,
    *,
    bron_id: str,
    naam: str,
    soort: str,
    licentie: str,
    attributietekst: str,
    url: str,
    herverdeelbaar: bool,
) -> None:
    """Een bron bestaat pas als licentie en attributietekst er zijn; het schema
    weigert lege waarden (E7.S1-AC1)."""
    conn.execute(
        """
        INSERT INTO bron (bron_id, naam, soort, licentie, attributietekst, url, herverdeelbaar)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bron_id) DO UPDATE SET
            naam = excluded.naam, soort = excluded.soort, licentie = excluded.licentie,
            attributietekst = excluded.attributietekst, url = excluded.url,
            herverdeelbaar = excluded.herverdeelbaar
        """,
        (bron_id, naam, soort, licentie, attributietekst, url, int(herverdeelbaar)),
    )
    conn.commit()


def registreer_actor(
    conn: sqlite3.Connection,
    *,
    naam: str,
    soort: str,
    aliassen: Iterable[str] = (),
    actor_id: str | None = None,
) -> str:
    """Maakt (of vindt) een actor en legt naam en aliassen als sleutels vast."""
    actor_id = actor_id or actor_id_voor(naam, soort)
    conn.execute(
        "INSERT INTO actor (actor_id, naam, soort) VALUES (?, ?, ?)"
        " ON CONFLICT(actor_id) DO NOTHING",
        (actor_id, naam, soort),
    )
    for alias in (naam, *aliassen):
        conn.execute(
            "INSERT INTO actor_alias (sleutel, actor_id) VALUES (?, ?)"
            " ON CONFLICT(sleutel) DO NOTHING",
            (_sleutel(alias), actor_id),
        )
    conn.commit()
    return actor_id


def vind_actor(conn: sqlite3.Connection, naam: str) -> str | None:
    """Onbekend blijft onbekend (E7.S3-AC1): geen gokken op deelstrings."""
    rij = conn.execute(
        "SELECT actor_id FROM actor_alias WHERE sleutel = ?", (_sleutel(naam),)
    ).fetchone()
    return rij[0] if rij else None


def voeg_attributie(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    actor_id: str,
    bron_id: str,
    datum: str,
    url: str,
    niveau: str,
    grond: str = "",
) -> bool:
    """Eén bonnetje; dubbelen (zelfde claim, actor, bron en link) tellen niet
    opnieuw. Ontbreekt bron, datum, link of niveau, dan weigert het schema."""
    # Geen `OR IGNORE`: dat slikt in SQLite ook CHECK-overtredingen in. Alleen
    # de UNIQUE-botsing (hetzelfde bonnetje nog eens) mag stil wegvallen.
    cursor = conn.execute(
        """
        INSERT INTO attributie
            (claim_id, actor_id, bron_id, datum, url, niveau, grond)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(claim_id, actor_id, bron_id, url) DO NOTHING
        """,
        (claim_id, actor_id, bron_id, datum, url, niveau, grond),
    )
    conn.commit()
    return cursor.rowcount == 1


@dataclass(frozen=True)
class Attributie:
    claim_id: str
    actor: str
    actor_soort: str
    bron: str
    bron_soort: str
    datum: str
    url: str
    niveau: str
    grond: str


def attributies_voor(conn: sqlite3.Connection, claim_ids: Iterable[str]) -> list[Attributie]:
    ids = list(dict.fromkeys(claim_ids))
    if not ids:
        return []
    plekken = ",".join("?" for _ in ids)
    rijen = conn.execute(
        f"""
        SELECT a.claim_id, ac.naam, ac.soort, b.naam, b.soort, a.datum, a.url, a.niveau, a.grond
        FROM attributie a
        JOIN actor ac ON ac.actor_id = a.actor_id
        JOIN bron b ON b.bron_id = a.bron_id
        WHERE a.claim_id IN ({plekken})
        ORDER BY a.datum, ac.naam
        """,
        ids,
    ).fetchall()
    return [Attributie(*rij) for rij in rijen]


def aandeel_met_attributie(conn: sqlite3.Connection) -> tuple[int, int, float]:
    """Het poortcijfer van E7.S4-AC3: claims met minstens één bonnetje."""
    totaal = conn.execute("SELECT count(*) FROM claim").fetchone()[0]
    met = conn.execute("SELECT count(DISTINCT claim_id) FROM attributie").fetchone()[0]
    return met, totaal, (met / totaal if totaal else 0.0)


def main() -> None:
    import os

    from doublecheck.storage import connect, init_schema

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    init_schema(conn)  # additief: maakt de attributietabellen aan in een bestaande database
    met, totaal, aandeel = aandeel_met_attributie(conn)
    bronnen = conn.execute("SELECT naam, soort FROM bron ORDER BY naam").fetchall()
    actoren = conn.execute("SELECT soort, count(*) FROM actor GROUP BY soort").fetchall()
    print(f"claims met minstens één attributie: {met} van {totaal} ({aandeel:.1%})")
    print("bronnen:", ", ".join(f"{n} [{s}]" for n, s in bronnen) or "geen")
    print("actoren:", ", ".join(f"{s} {n}" for s, n in actoren) or "geen")


if __name__ == "__main__":
    main()
