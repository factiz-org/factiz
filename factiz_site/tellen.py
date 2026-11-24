"""Anoniem tellen (PLAN #34.2ba, SPECS E9.S26, B78).

    python -m factiz_site.tellen [<bestand>] [--dagen 14]
    python -m factiz_site.tellen --d1 factiz-tellingen [--dagen 14]
    python -m factiz_site.tellen [<bestand> | --d1 factiz-tellingen] --zoekvragen [--dagen 7]

De site op factiz.org (de Worker, PLAN #34.2bo stap 8) telt in een eigen D1-database met dezelfde tabel; `--d1` leest die
met wrangler, alleen lezen.

Per dag (UTC), per wat (een soort pagina, `robot`, `zoek`, `zoek-zonder`, `zoek-bericht`) en per taal één getal. Meer
niet: geen IP-adres, geen cookie, geen zoektekst, geen adres of nummer van een pagina, geen user-agent, geen tijd fijner
dan een dag. Het geheugen telt; elke minuut en bij het stoppen gaat het opgetelde naar SQLite, met een upsert, zodat
meerdere serverprocessen in hetzelfde bestand optellen. Zonder bestand telt niets.

Sinds B94 (PLAN #37.17) telt de site ook wat mensen zoeken, in de tabel `zoekvraag` van dezelfde database: per dag en taal
de getypte vraag met haar aantal (`site/src/lib/zoekvragen.js`). `--zoekvragen` leest daaruit per taal alleen wat in de
laatste dagen minstens drie keer kwam; wat zeldzaam bleef, ruimt de site zelf na zeven dagen op. Alleen voor intern gebruik.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from factiz_site.i18n import TALEN

# de soorten pagina van de site (de router in `site/src/pages/[...pad].astro`)
SOORTEN = frozenset({"start", "lijst", "factcheck", "dossiers", "dossier", "namen", "naam", "redacties", "bronnen", "over",
                     "platform", "themas", "thema", "verkennen", "netwerk", "fout", "eigens", "eigen"})
ZOEK = ("zoek", "zoek-zonder", "zoek-bericht")
WAT = SOORTEN | {"robot", *ZOEK, "storing"}     # storing: een antwoord van 500 of hoger (PLAN #34.2bv)
WRANGLER = Path(__file__).resolve().parent.parent / "site" / "node_modules" / ".bin" / "wrangler"
LEES = ("SELECT dag, wat, taal, n FROM telling WHERE dag IN "
        "(SELECT DISTINCT dag FROM telling ORDER BY dag DESC LIMIT {dagen}) ORDER BY dag")
SCHEMA = ("CREATE TABLE IF NOT EXISTS telling (dag TEXT NOT NULL, wat TEXT NOT NULL, taal TEXT NOT NULL, "
          "n INTEGER NOT NULL, PRIMARY KEY (dag, wat, taal)) WITHOUT ROWID")


def vandaag() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Teller:
    """Telt in het geheugen en schrijft het opgetelde weg. `tel` weigert wat het niet kent (ValueError)."""

    def __init__(self, bestand: str | Path | None, interval: float = 60.0):
        self.bestand = Path(bestand) if bestand else None
        self._open: Counter = Counter()
        self._slot = threading.Lock()
        self._stop = threading.Event()
        if not self.bestand:
            return
        self.bestand.parent.mkdir(parents=True, exist_ok=True)
        with self._verbind() as c:
            c.execute(SCHEMA)
        if interval:
            threading.Thread(target=self._lus, args=(interval,), daemon=True, name="factiz-teller").start()

    def _verbind(self) -> sqlite3.Connection:
        return sqlite3.connect(self.bestand, timeout=10)

    def _lus(self, interval: float) -> None:
        while not self._stop.wait(interval):
            self.wegschrijven()

    def tel(self, wat: str, taal: str, n: int = 1) -> None:
        if wat not in WAT or taal not in TALEN:
            raise ValueError("onbekend")
        if self.bestand:
            with self._slot:
                self._open[(vandaag(), wat, taal)] += n

    def wegschrijven(self) -> None:
        if not self.bestand:
            return
        with self._slot:
            open_, self._open = self._open, Counter()
        if not open_:
            return
        try:
            with self._verbind() as c:
                c.executemany("INSERT INTO telling (dag, wat, taal, n) VALUES (?, ?, ?, ?) "
                              "ON CONFLICT (dag, wat, taal) DO UPDATE SET n = n + excluded.n",
                              [(dag, wat, taal, n) for (dag, wat, taal), n in open_.items()])
        except sqlite3.Error:
            # het bestand is even niet te schrijven: niets kwijt, de volgende keer opnieuw
            with self._slot:
                self._open.update(open_)

    def stop(self) -> None:
        self._stop.set()
        self.wegschrijven()


def overzicht(bestand: str | Path, dagen: int = 14) -> str:
    """De getallen per dag uit een bestand, alle talen samen (`_regels`)."""
    with sqlite3.connect(f"{Path(bestand).resolve().as_uri()}?mode=ro", uri=True) as c:
        return _regels(list(c.execute(LEES.format(dagen=int(dagen)))))


def rijen_d1(database: str, dagen: int = 14, voer_uit=None) -> list[tuple]:
    """(dag, wat, taal, n) uit de D1-database van de Worker: één leesvraag via wrangler."""
    uit = json.loads((voer_uit or _wrangler)(["d1", "execute", database, "--remote", "--json", "--command",
                                              LEES.format(dagen=int(dagen))]))
    if not uit or not uit[-1].get("success"):
        raise SystemExit(f"D1 ({database}) gaf geen tellingen")
    return [(r["dag"], r["wat"], r["taal"], r["n"]) for r in uit[-1]["results"]]


def overzicht_d1(database: str, dagen: int = 14, voer_uit=None) -> str:
    """Hetzelfde overzicht uit de D1-database van de Worker."""
    return _regels(rijen_d1(database, dagen, voer_uit))


MINSTENS = 3        # B94: wat minder vaak gezocht is, laat het overzicht nooit zien


def _lees_vragen(vandaag_: str, dagen: int) -> str:
    """De vraag voor het overzicht van zoekvragen; de dag staat erin als tekst, zodat wrangler haar zonder waarden kan
    uitvoeren (alleen cijfers en streepjes, gecontroleerd)."""
    if not (len(vandaag_) == 10 and vandaag_.replace("-", "").isdigit()):
        raise ValueError("geen dag")
    return (f"SELECT taal, vraag, SUM(n) AS n FROM zoekvraag WHERE dag > date('{vandaag_}', '-{int(dagen)} days') "
            f"GROUP BY taal, vraag HAVING SUM(n) >= {MINSTENS} ORDER BY taal, n DESC, vraag")


def _vraagregels(rijen: list[tuple]) -> str:
    """Per taal de zoekvragen met hun aantal, de vaakste eerst."""
    regels = []
    for taal in sorted({r[0] for r in rijen}):
        regels.append(taal)
        regels += [f"{n:>6}  {vraag}" for t, vraag, n in rijen if t == taal]
    return "\n".join(regels) or "nog geen zoekvragen die minstens drie keer kwamen"


def zoekvragen(bestand: str | Path, dagen: int = 7) -> str:
    """Wat mensen zochten (B94), per taal, uit een bestand: alleen wat in de laatste `dagen` minstens drie keer kwam."""
    with sqlite3.connect(f"{Path(bestand).resolve().as_uri()}?mode=ro", uri=True) as c:
        return _vraagregels(list(c.execute(_lees_vragen(vandaag(), dagen))))


def zoekvragen_d1(database: str, dagen: int = 7, voer_uit=None) -> str:
    """Hetzelfde uit de D1-database van de Worker: één leesvraag via wrangler."""
    uit = json.loads((voer_uit or _wrangler)(["d1", "execute", database, "--remote", "--json", "--command",
                                              _lees_vragen(vandaag(), dagen)]))
    if not uit or not uit[-1].get("success"):
        raise SystemExit(f"D1 ({database}) gaf geen zoekvragen")
    return _vraagregels([(r["taal"], r["vraag"], r["n"]) for r in uit[-1]["results"]])


def _wrangler(args: list[str]) -> str:  # pragma: no cover - roept wrangler aan
    if not WRANGLER.exists():
        raise SystemExit("wrangler ontbreekt: eerst npm ci --prefix site")
    uit = subprocess.run([str(WRANGLER), *args], capture_output=True, text=True, cwd=WRANGLER.parents[3])
    if uit.returncode:
        raise SystemExit(f"wrangler mislukte:\n{uit.stderr[-1500:]}")
    return uit.stdout


def _regels(rijen: list[tuple]) -> str:
    """Per dag de bezoeken per soort pagina, de zoekvragen met het aandeel zonder resultaat in procenten, en de robots."""
    regels = []
    for dag in sorted({r[0] for r in rijen}):
        per = Counter()
        for _, wat, _, n in (r for r in rijen if r[0] == dag):
            per[wat] += n
        paginas = sorted(((w, n) for w, n in per.items() if w in SOORTEN), key=lambda x: (-x[1], x[0]))
        zoek, zonder = per["zoek"], per["zoek-zonder"]
        aandeel = f" ({round(100 * zonder / zoek)}%)" if zoek else ""
        regels.append(f"{dag}  bezoeken {sum(n for _, n in paginas)}: " + ", ".join(f"{w} {n}" for w, n in paginas))
        regels.append(f"{'':10}  zoekvragen {zoek}, zonder resultaat {zonder}{aandeel}, geplakte berichten "
                      f"{per['zoek-bericht']}; robots {per['robot']}; storingen {per['storing']}")
    return "\n".join(regels) or "nog geen tellingen"


def main() -> None:  # pragma: no cover - CLI
    import os

    argumenten = [a for a in sys.argv[1:] if not a.startswith("--")]
    vragen = "--zoekvragen" in sys.argv
    dagen = int(sys.argv[sys.argv.index("--dagen") + 1]) if "--dagen" in sys.argv else (7 if vragen else 14)
    argumenten = [a for a in argumenten if a != str(dagen)]
    if "--d1" in sys.argv:
        database = sys.argv[sys.argv.index("--d1") + 1]
        argumenten = [a for a in argumenten if a != database]
        print(zoekvragen_d1(database, dagen) if vragen else overzicht_d1(database, dagen))
        return
    bestand = argumenten[0] if argumenten else os.environ.get("FACTIZ_TELLINGEN")
    if not bestand or not Path(bestand).exists():
        raise SystemExit("geen tellingen: geef het bestand, of zet FACTIZ_TELLINGEN")
    print(zoekvragen(bestand, dagen) if vragen else overzicht(bestand, dagen))


if __name__ == "__main__":  # pragma: no cover
    main()
