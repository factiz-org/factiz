"""De feed van Data Commons stopt (B91, PLAN #37.12, SPECS E10.S6 AC7; PO 2026-11-23: "Ja, feed stoppen").

    python -m doublecheck.feedstop vastleggen --uitgave 2026-11-23
    python -m doublecheck.feedstop tellen

Nieuwe factchecks komen uit de wereldlijst (B90). Een check van Data Commons gaat alleen nog in een uitgave als hij in de
uitgave van 2026-11-23 stond: het paar van bewering en link, als vingerafdruk in `feed_bevroren.txt.gz`. Wat de feed daarna
brengt, blijft in het lab (de radar en de wereldlijst zien zo wat al gecheckt is) en gaat nergens heen. Het archief blijft
zoals het was, met zijn correcties en filters; `publiceren bouwen` weigert zonder dit bestand, want twijfel versoepelt nooit.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import sqlite3
from pathlib import Path

from doublecheck.feed import HERDISTRIBUEERBAAR

WORTEL = Path(__file__).resolve().parent.parent
BESTAND = Path(__file__).resolve().parent / "feed_bevroren.txt.gz"
KOP = "# feed van Data Commons, bevroren op uitgave {uitgave}: {n} checks"


class Weigering(Exception):
    pass


def sleutel(claim_id: str, url: str) -> str:
    """De vingerafdruk van één check: de bewering (haar vaste id, ook na een nieuwe import) en de link van de redactie."""
    return hashlib.sha256(f"{claim_id}\n{url}".encode("utf-8")).hexdigest()[:16]


def uit_uitgave(lab: sqlite3.Connection, uitgave: sqlite3.Connection) -> list[str]:
    """De checks van Data Commons die in een uitgave stonden: van het lab elke check van de feed waarvan de bewering een
    pagina of een formulering van een pagina is en de link bij die pagina als check van Data Commons stond."""
    from doublecheck.publiceren import nummer

    # de hoofdformulering is het nummer van de pagina zelf, de andere staan in `formulering`
    pagina_van = {**dict(uitgave.execute("SELECT nummer, pagina FROM formulering")),
                  **{nr: nr for (nr,) in uitgave.execute("SELECT nummer FROM pagina")}}
    links: dict[str, set[str]] = {}
    for pagina, url in uitgave.execute("SELECT pagina, url FROM check_ WHERE bron = ?", (HERDISTRIBUEERBAAR,)):
        links.setdefault(pagina, set()).add(url)
    uit = set()
    for claim_id, url in lab.execute("SELECT claim_id, url FROM factcheck WHERE source = ?", (HERDISTRIBUEERBAAR,)):
        pagina = pagina_van.get(nummer(claim_id))
        if pagina is not None and url in links.get(pagina, ()):
            uit.add(sleutel(claim_id, url))
    return sorted(uit)


def schrijf(sleutels: list[str], pad: Path = BESTAND, *, uitgave: str) -> None:
    regels = [KOP.format(uitgave=uitgave, n=len(set(sleutels))), *sorted(set(sleutels))]
    # mtime=0: hetzelfde bestand bij dezelfde inhoud
    pad.write_bytes(gzip.compress(("\n".join(regels) + "\n").encode("utf-8"), mtime=0))


def lees(pad: Path = BESTAND) -> frozenset[str]:
    try:
        regels = gzip.decompress(Path(pad).read_bytes()).decode("utf-8").splitlines()
    except (OSError, EOFError) as fout:
        raise Weigering(f"de feed is gestopt (B91), maar {pad} ontbreekt of is kapot: geen uitgave zonder ({fout})") from None
    if not regels or not regels[0].startswith("# feed van Data Commons, bevroren op uitgave "):
        raise Weigering(f"{pad} is geen bevroren feed")
    sleutels = frozenset(r for r in regels[1:] if r)
    if len(sleutels) != int(regels[0].rsplit(": ", 1)[1].split()[0]):
        raise Weigering(f"{pad}: het aantal checks klopt niet met de kop")
    return sleutels


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stap", choices=["vastleggen", "tellen"])
    p.add_argument("--uitgave", default="2026-11-23")
    p.add_argument("--lab", default=str(WORTEL / "doublecheck.db"))
    a = p.parse_args()
    try:
        if a.stap == "tellen":
            print(f"{len(lees())} checks van Data Commons mogen nog in een uitgave ({BESTAND.name})")
            return
        if BESTAND.exists():
            raise Weigering(f"{BESTAND} ligt al vast: de feed is één keer bevroren, niet opnieuw")
        bestand = WORTEL / "data" / "publicatie" / a.uitgave / "publicatie.db"
        lab = sqlite3.connect(f"file:{a.lab}?mode=ro", uri=True)
        uitgave = sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)
        live = uitgave.execute("SELECT COUNT(*) FROM check_ WHERE bron = ?", (HERDISTRIBUEERBAAR,)).fetchone()[0]
        sleutels = uit_uitgave(lab, uitgave)
        schrijf(sleutels, uitgave=a.uitgave)
        print(f"{len(sleutels)} checks van Data Commons vastgelegd uit {a.uitgave} (in de uitgave: {live} rijen) -> {BESTAND}")
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
