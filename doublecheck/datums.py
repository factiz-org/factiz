"""Datumhygiëne voor `review_date` (PLAN.md #21.4, BENCHMARK §58).

Het logboek van de batchcontrole (#21.2) ving "2923-01-02" als nieuwste check:
12,3% van de feeddatums bleek ongeldig, en dezelfde waarden stonden in de
DR1-bonnetjes van de resolver én in het discovery-antwoord van de API. De
oorzaak: de import gaf `datePublished` rauw door.

Eén regel, op één plek. `geldige_review_datum` draait in `import_claims` — de
enige INSERT, dus feed- én API-import dragen de regel zonder eigen kopie — en
`schoonmaak` past dezelfde regel toe op wat er al staat.

De regel verzint nooit een waarde. "2-12-30" wordt níét "2012-12-30" — dat zou
een gok als feit in een bonnetje zetten. De enige transformatie is extractie:
de datum uit een RFC3339-tijdstempel. Al het andere wordt leeg, de bestaande
"geen datum"-conventie van het schema (`NOT NULL`).

Wat de regel bewust laat staan: de gemengde pre-2017-staart (§58c). Daar staan
aantoonbare typo's (een COVID-check op 2001) náást echte archieven (Boatos.org
2013, MyGoPen 2015), en geen jaargrens scheidt die twee zonder waarheid te
vernietigen. De grens ligt op 1995 — vóór het web bestond geen online
factcheck — en dat vangt de epoch- en typo-uitschieters wél.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date

# Vóór het web bestond geen online factcheck; dit vangt epoch-junk (1970-01-01)
# en 1936 zonder echte archieven te raken (§58c: oudste plausibele rij 2011).
OUDSTE_PLAUSIBEL = date(1995, 1, 1)


def geldige_review_datum(waarde: str | None, vandaag: date | None = None) -> str:
    """De datum als hij te vertrouwen is, anders `""` — nooit een reparatie.

    Te vertrouwen is: kale ISO-vorm (`YYYY-MM-DD`; een RFC3339-tijdstempel
    wordt tot zijn datumdeel geknipt), een echte kalenderdag, niet vóór 1995
    en niet ná `vandaag`. `vandaag` is injecteerbaar voor tests; standaard de
    dag van de import of schoonmaak.
    """
    if not waarde:
        return ""
    vandaag = vandaag or date.today()
    kaal = waarde.strip()
    if len(kaal) > 10 and kaal[10] in "T ":  # RFC3339: 2021-03-03T09:00:00Z
        kaal = kaal[:10]
    try:
        ontleed = date.fromisoformat(kaal)
    except ValueError:
        return ""
    # `fromisoformat` accepteert sinds 3.11 ook compacte ("20240314") en
    # weekvormen; een bonnetje draagt één canonieke vorm, dus de rondgang
    # moet exact terugkomen.
    if ontleed.isoformat() != kaal:
        return ""
    if ontleed < OUDSTE_PLAUSIBEL or ontleed > vandaag:
        return ""
    return kaal


@dataclass(frozen=True)
class Schoonmaakverslag:
    gecontroleerd: int
    geleegd: int
    ingekort: int  # tijdstempel → datumdeel; extractie, geen reparatie
    al_leeg: int
    geleegde_waarden: tuple[str, ...]


def schoonmaak(
    conn: sqlite3.Connection, vandaag: date | None = None
) -> Schoonmaakverslag:
    """Past de datumregel toe op bestaande rijen. Legen of inkorten, nooit
    invullen; idempotent, dus veilig om te herhalen."""
    vandaag = vandaag or date.today()
    al_leeg = conn.execute(
        "SELECT COUNT(*) FROM factcheck WHERE review_date = ''"
    ).fetchone()[0]
    afwijkend = [
        (rij[0], geldige_review_datum(rij[0], vandaag=vandaag))
        for rij in conn.execute("SELECT DISTINCT review_date FROM factcheck")
        if rij[0] and geldige_review_datum(rij[0], vandaag=vandaag) != rij[0]
    ]
    geleegd = ingekort = 0
    geleegde_waarden = []
    for oud, schoon in sorted(afwijkend):
        aantal = conn.execute(
            "UPDATE factcheck SET review_date = ? WHERE review_date = ?",
            (schoon, oud),
        ).rowcount
        if schoon:
            ingekort += aantal
        else:
            geleegd += aantal
            geleegde_waarden.append(oud)
    conn.commit()
    totaal = conn.execute("SELECT COUNT(*) FROM factcheck").fetchone()[0]
    return Schoonmaakverslag(
        gecontroleerd=totaal,
        geleegd=geleegd,
        ingekort=ingekort,
        al_leeg=al_leeg,
        geleegde_waarden=tuple(geleegde_waarden),
    )


def _meting(conn: sqlite3.Connection, vandaag: date) -> list[tuple[str, int]]:
    """Ongeldige datums per uitgever — lezen vóór het legen, net als bij de
    uitgeverkwaliteit: de meting toont wáár de rommel vandaan komt."""
    telling: dict[str, int] = {}
    for publisher, waarde in conn.execute(
        "SELECT publisher, review_date FROM factcheck WHERE review_date != ''"
    ):
        if geldige_review_datum(waarde, vandaag=vandaag) != waarde:
            telling[publisher] = telling.get(publisher, 0) + 1
    return sorted(telling.items(), key=lambda paar: -paar[1])


def main() -> None:
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(
        description=(
            "Meet ongeldige review-datums; met --schoonmaak worden ze geleegd"
            " (nooit gerepareerd). Zonder vlag verandert er niets."
        )
    )
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--schoonmaak", action="store_true",
                        help="pas de regel toe op de bestaande rijen")
    args = parser.parse_args()

    conn = connect(args.db)
    vandaag = date.today()
    leeg = conn.execute(
        "SELECT COUNT(*) FROM factcheck WHERE review_date = ''"
    ).fetchone()[0]
    totaal = conn.execute("SELECT COUNT(*) FROM factcheck").fetchone()[0]
    per_uitgever = _meting(conn, vandaag)
    fout = sum(n for _, n in per_uitgever)
    print(f"{totaal} factchecks; {leeg} zonder datum, {fout} met ongeldige datum")
    for publisher, n in per_uitgever[:15]:
        print(f"  {n:>5}  {publisher}")

    if args.schoonmaak:
        verslag = schoonmaak(conn, vandaag=vandaag)
        print(
            f"geleegd: {verslag.geleegd}, ingekort: {verslag.ingekort},"
            f" al leeg: {verslag.al_leeg}"
        )
        for waarde in verslag.geleegde_waarden:
            print(f"  geleegd: {waarde!r}")
    elif fout:
        print("droogloop — draai met --schoonmaak om te legen")
    conn.close()


if __name__ == "__main__":
    main()
