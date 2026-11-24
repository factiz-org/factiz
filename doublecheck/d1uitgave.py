"""De uitgave naar D1 (PLAN #34.2bo, stap 2; B80).

De site van V1 leest de uitgave uit D1, de SQLite van Cloudflare. Dit script zet een uitgave die `publiceren controleer`
doorliet om in SQL die D1 aanneemt, maakt per release een eigen database, importeert en kijkt na of D1 tot op de rij
hetzelfde bevat. Het lab blijft de bron; D1 is een kopie die je opnieuw kunt maken.

    python -m doublecheck.d1uitgave sql [<publicatie.db>]       schrijft data/d1/<release>/
    python -m doublecheck.d1uitgave aanmaken <release>          een database factiz-<release> in West-Europa
    python -m doublecheck.d1uitgave importeren <release>        alleen in een lege database
    python -m doublecheck.d1uitgave nakijken <release>          per tabel elke rij, de zoekregisters, de zoekvragen

Wat D1 vraagt en wat dit script daarom doet:
- elke opdracht hoogstens 90.000 bytes (D1 noemt 100 KB, maar weigerde 99.999); een rij die er niet in past laat het
  weigeren, nooit afkappen;
- de verwijzingen staan aan, dus de tabellen in de volgorde van hun verwijzingen, met `defer_foreign_keys`;
- geen BEGIN in een bestand: D1 doet elke import in één transactie;
- de zoekregisters (FTS5) worden uit hun tekst opnieuw opgebouwd, met dezelfde `rowid`; de interne tabellen niet;
- D1 geeft via JSON 2.0 terug als 2 en bytes als een lijst getallen, dus het nakijken vergelijkt in één vaste vorm.

Elke handeling op het Cloudflare-account (`aanmaken`, `importeren`) vraagt een ja van de PO (B80).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from doublecheck import publiceren as pb

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "d1"
WRANGLER = WORTEL / "site" / "node_modules" / ".bin" / "wrangler"
GRENS = 90_000                  # bytes per opdracht: D1 weigerde 99.999 (SQLITE_TOOBIG), 90.000 ging goed (34.2bo)
DEEL = 200_000_000              # bytes per bestand dat in één keer geïmporteerd wordt
BLAD = 4_000_000                # ongeveer zoveel bytes per vraag bij het nakijken
LOCATIE = "weur"                # West-Europa
SCHADUW = ("data", "idx", "content", "docsize", "config")    # de interne tabellen van FTS5

# De zoekvragen van stap 1, in veertien schriften (PLAN 34.2bo): dezelfde aantallen als in Python.
ZOEKVRAGEN = [
    ("zoek", '"vaccine"'), ("zoek", '"zelensky" "villa"'), ("zoek", '"vaccin"'), ("zoek", '"impfung"'),
    ("zoek", '"vacuna"'), ("zoek", '"вакцина"'), ("zoek", '"वैक्सीन"'), ("zoek", '"لقاح"'), ("zoek", '"واکسن"'),
    ("zoek", '"aşı"'), ("zoek", '"münchen"'), ("zoek", '"munchen"'),
    ("zoek3", '"ワクチン"'), ("zoek3", '"วัคซีน"'), ("zoek3", '"백신을"'), ("zoek3", '"疫苗接"'), ("zoek3", '"ಲಸಿಕೆ"'),
    ("zoek3", '"தடுப்பூசி"'),
]

Vraag = Callable[[str], list[dict]]


class Weigering(Exception):
    """Het script weigert: liever niets in D1 dan iets dat niet klopt."""


def literaal(waarde: object) -> str:
    """Een waarde als SQL, zo dat SQLite precies dezelfde waarde met hetzelfde type teruggeeft."""
    if waarde is None:
        return "NULL"
    if isinstance(waarde, bool):
        raise Weigering("een waarheidswaarde komt niet uit SQLite")
    if isinstance(waarde, int):
        return str(waarde)
    if isinstance(waarde, float):
        if not math.isfinite(waarde):
            raise Weigering(f"een getal dat SQL niet kan schrijven: {waarde!r}")
        return repr(waarde)
    if isinstance(waarde, (bytes, bytearray)):
        return f"X'{bytes(waarde).hex()}'"
    if isinstance(waarde, str):
        if "\x00" in waarde:        # een nul kan niet in een tekst tussen aanhalingstekens
            return f"CAST(X'{waarde.encode('utf-8').hex()}' AS TEXT)"
        return "'" + waarde.replace("'", "''") + "'"
    raise Weigering(f"een waarde van een onbekend soort: {type(waarde).__name__}")


def _naam(tabel: str) -> str:
    return '"' + tabel.replace('"', '""') + '"'


def _virtueel(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%' ORDER BY rowid")]


def volgorde(conn: sqlite3.Connection) -> list[str]:
    """De tabellen die mee moeten, elke tabel na de tabellen waarnaar ze verwijst; verder in de volgorde van het
    schema. Zonder de interne tabellen van de zoekregisters, die D1 zelf opbouwt."""
    virtueel = _virtueel(conn)
    schaduw = {f"{v}_{s}" for v in virtueel for s in SCHADUW}
    alle = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid")
            if not r[0].startswith("sqlite_") and r[0] not in schaduw]
    zonder_rowid = {r[0] for r in conn.execute("SELECT name FROM pragma_table_list WHERE wr = 1")}
    if set(alle) & zonder_rowid:
        raise Weigering(f"een tabel zonder rowid wordt niet ondersteund: {sorted(set(alle) & zonder_rowid)}")
    if conn.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('view', 'trigger')").fetchone()[0]:
        raise Weigering("een view of trigger wordt niet ondersteund")
    nodig = {t: {r[2] for r in conn.execute(f"PRAGMA foreign_key_list({_naam(t)})")} - {t}
             for t in alle if t not in virtueel}
    uit: list[str] = []
    while len(uit) < len(alle):
        for t in alle:
            if t not in uit and nodig.get(t, set()) <= set(uit):
                uit.append(t)
                break
        else:
            raise Weigering(f"verwijzingen in een kring: {sorted(set(alle) - set(uit))}")
    return uit


def _kolommen(conn: sqlite3.Connection, tabel: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({_naam(tabel)})")]


def _stukken(tekst: str, ruimte: int) -> Iterator[str]:
    """`tekst` in opeenvolgende stukken waarvan elk als literaal hoogstens `ruimte` bytes is."""
    begin, omvang = 0, 2                       # de twee aanhalingstekens
    for i, teken in enumerate(tekst):
        n = len(teken.encode("utf-8")) + (1 if teken == "'" else 0)
        if omvang + n > ruimte:
            yield tekst[begin:i]
            begin, omvang = i, 2
        omvang += n
    yield tekst[begin:]


def _in_stukken(tabel: str, kolommen: list[str], rij: tuple, kop: str, grens: int) -> Iterator[str]:
    """Een rij die niet in één opdracht past (een eigen check met veertien vertalingen, #37.8): eerst de rij met de
    grootste teksten leeg, dan elke tekst in stukken erachter (`kolom || '...'`), zodat de waarde precies terugkomt.
    Weigert een rij die ook zonder haar teksten niet past, en een tekst met een nul (die kan niet tussen aanhalingstekens)."""
    rowid, waarden = rij[0], list(rij[1:])
    later: dict[int, str] = {}
    while True:
        stuk = "(" + ",".join(literaal(v) for v in [rowid, *waarden]) + ")"
        if len((kop + stuk).encode("utf-8")) + 1 <= grens:
            break
        teksten = [j for j, v in enumerate(waarden) if isinstance(v, str) and v and j not in later and "\x00" not in v]
        if not teksten:
            raise Weigering(f"rij {rowid} van {tabel} past niet in één opdracht van {grens} bytes")
        j = max(teksten, key=lambda k: len(waarden[k].encode("utf-8")))
        later[j], waarden[j] = waarden[j], ""
    yield kop + stuk
    for j, tekst in later.items():
        kolom = _naam(kolommen[j])
        voor, achter = f"UPDATE {_naam(tabel)} SET {kolom} = {kolom} || ", f" WHERE rowid = {rowid}"
        ruimte = grens - len((voor + achter).encode("utf-8")) - 1
        if ruimte < 8:
            raise Weigering(f"rij {rowid} van {tabel} past niet in één opdracht van {grens} bytes")
        for deel in _stukken(tekst, ruimte):
            yield voor + literaal(deel) + achter


def opdrachten(conn: sqlite3.Connection, grens: int = GRENS) -> Iterator[str]:
    """Alle opdrachten, elk hoogstens `grens` bytes met de puntkomma erbij: de tabellen, de rijen met hun eigen rowid,
    en daarna de indexen."""
    yield "PRAGMA defer_foreign_keys = true"
    tabellen = volgorde(conn)
    for t in tabellen:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (t,)).fetchone()[0]
        yield sql
    for t in tabellen:
        kolommen = _kolommen(conn, t)
        kop = f"INSERT INTO {_naam(t)} (rowid, {', '.join(_naam(k) for k in kolommen)}) VALUES "
        kop_bytes = len(kop.encode("utf-8"))
        rijen: list[str] = []
        omvang = kop_bytes + 1                    # de puntkomma
        for rij in conn.execute(f"SELECT rowid, * FROM {_naam(t)} ORDER BY rowid"):
            stuk = "(" + ",".join(literaal(v) for v in rij) + ")"
            n = len(stuk.encode("utf-8")) + (1 if rijen else 0)
            if kop_bytes + len(stuk.encode("utf-8")) + 1 > grens:
                if rijen:
                    yield kop + ",".join(rijen)
                    rijen, omvang = [], kop_bytes + 1
                yield from _in_stukken(t, kolommen, rij, kop, grens)
                continue
            if omvang + n > grens:
                yield kop + ",".join(rijen)
                rijen, omvang = [], kop_bytes + 1
                n = len(stuk.encode("utf-8"))
            rijen.append(stuk)
            omvang += n
        if rijen:
            yield kop + ",".join(rijen)
    for (sql,) in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL ORDER BY rowid"):
        yield sql


def schrijf(bestand: str | Path, uit: str | Path, *, grens: int = GRENS, deel: int = DEEL,
            controleer: Callable[..., dict] = pb.controleer) -> dict:
    """Schrijft de uitgave als SQL in `uit`, in delen van hoogstens `deel` bytes, alleen als `controleer` haar doorliet.
    `klaar.json` komt als laatste: een map zonder dat bestand is niet af."""
    controleer(bestand)
    uit = Path(uit)
    conn = sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)
    try:
        meta = dict(conn.execute("SELECT sleutel, waarde FROM meta"))
        tijdelijk = uit.with_name(uit.name + ".bezig")
        shutil.rmtree(tijdelijk, ignore_errors=True)
        tijdelijk.mkdir(parents=True)
        delen: list[dict] = []
        f = None
        try:
            for opdracht in opdrachten(conn, grens):
                regel = opdracht + ";\n"
                n = len(regel.encode("utf-8"))
                if f is None or (delen[-1]["bytes"] + n > deel and delen[-1]["opdrachten"]):
                    if f:
                        f.close()
                    naam = f"deel-{len(delen) + 1:03d}.sql"
                    f = open(tijdelijk / naam, "w", encoding="utf-8")
                    delen.append({"bestand": naam, "bytes": 0, "opdrachten": 0})
                    if len(delen) > 1:        # elk deel is een eigen import, dus een eigen transactie
                        kop = "PRAGMA defer_foreign_keys = true;\n"
                        f.write(kop)
                        delen[-1]["bytes"] += len(kop.encode("utf-8"))
                f.write(regel)
                delen[-1]["bytes"] += n
                delen[-1]["opdrachten"] += 1
        finally:
            if f:
                f.close()
        tabellen = {t: conn.execute(f"SELECT count(*) FROM {_naam(t)}").fetchone()[0] for t in volgorde(conn)}
        klaar = {"release": meta.get("release"), "controlegetal": meta.get("controlegetal"), "schema": meta.get("schema"),
                 "bron": str(bestand), "grens": grens, "delen": delen, "tabellen": tabellen}
        (tijdelijk / "klaar.json").write_text(json.dumps(klaar, ensure_ascii=False, indent=1), encoding="utf-8")
    except BaseException:
        shutil.rmtree(uit.with_name(uit.name + ".bezig"), ignore_errors=True)
        raise
    finally:
        conn.close()
    shutil.rmtree(uit, ignore_errors=True)
    tijdelijk.rename(uit)
    return klaar


# --- de handelingen op het account, via wrangler -------------------------------------------------------------------

def wrangler(args: list[str]) -> str:  # pragma: no cover - roept wrangler aan
    if not WRANGLER.exists():
        raise SystemExit("wrangler ontbreekt: eerst npm ci --prefix site")
    uit = subprocess.run([str(WRANGLER), *args], capture_output=True, text=True, cwd=WORTEL)
    if uit.returncode:
        raise Weigering(f"wrangler {' '.join(args[:3])} mislukte:\n{uit.stdout[-2000:]}\n{uit.stderr[-2000:]}")
    return uit.stdout


def met_geduld(stap: Callable[[], object], *, pogingen: int = 6, wacht: float = 10.0,
               slaap: Callable[[float], None] | None = None) -> object:
    """Een stap opnieuw na een pauze als D1 zegt dat hij overbelast is (code 7429: te veel in tien seconden, 2026-11-17
    bij het nakijken van 2026-11-17); elke keer langer wachten. Een andere fout gaat meteen door."""
    import time

    for poging in range(1, pogingen + 1):
        try:
            return stap()
        except Weigering as fout:
            if poging == pogingen or not ("7429" in str(fout) or "overloaded" in str(fout)):
                raise
            (slaap or time.sleep)(wacht * poging)
    raise AssertionError("onbereikbaar")


def d1_vraag(database: str) -> Vraag:  # pragma: no cover - roept wrangler aan
    """Eén leesvraag aan D1 in de cloud; de rijen als woordenboeken, zoals D1 ze via JSON teruggeeft."""
    def vraag(sql: str) -> list[dict]:
        antwoord = json.loads(met_geduld(
            lambda: wrangler(["d1", "execute", database, "--remote", "--json", "--command", sql])))
        if not antwoord or not antwoord[-1].get("success", False):
            raise Weigering(f"D1 gaf geen antwoord op: {sql[:200]}")
        return antwoord[-1]["results"]
    return vraag


def aanmaken(release: str, voer_uit: Callable[[list[str]], str]) -> dict:
    """Een nieuwe database voor deze release, in West-Europa. De draaiende blijft staan tot de nieuwe klopt."""
    naam = f"factiz-{release}"
    uit = voer_uit(["d1", "create", naam, "--location", LOCATIE])
    gevonden = re.search(r'"database_id":\s*"([0-9a-f-]{36})"', uit or "")
    if not gevonden:
        raise Weigering(f"geen database-id in het antwoord van wrangler voor {naam}")
    return {"naam": naam, "id": gevonden.group(1)}


def importeren(map_: str | Path, database: str, *, vraag: Vraag, voer_uit: Callable[[list[str]], object]) -> dict:
    """Zet de delen in `database`, maar alleen als daar nog geen tabel in staat: nooit over de draaiende heen."""
    map_ = Path(map_)
    if not (map_ / "klaar.json").exists():
        raise Weigering(f"{map_} is niet klaar: eerst `sql`")
    klaar = json.loads((map_ / "klaar.json").read_text(encoding="utf-8"))
    er = [r.get("name") for r in vraag("SELECT name FROM sqlite_master WHERE type = 'table' "
                                       "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%'")]
    if er:
        raise Weigering(f"in {database} staan al tabellen ({', '.join(map(str, er[:5]))}): kies een lege database")
    for deel in klaar["delen"]:
        voer_uit(["d1", "execute", database, "--remote", "--file", str(map_ / deel["bestand"]), "--yes"])
    return {"database": database, "delen": len(klaar["delen"]), "release": klaar["release"]}


# --- nakijken ---------------------------------------------------------------------------------------------------------

def _vorm(waarde: object) -> object:
    """Eén vorm voor een waarde uit SQLite en dezelfde waarde uit D1 (JSON): 2.0 en 2 gelijk, bytes als lijst, en een
    geheel getal buiten wat JSON precies draagt zoals JSON het teruggeeft."""
    if isinstance(waarde, (bytes, bytearray)):
        return list(waarde)
    if isinstance(waarde, float) and waarde.is_integer() and abs(waarde) < 2**53:
        return int(waarde)
    if isinstance(waarde, int) and abs(waarde) >= 2**53:
        return float(waarde)
    return waarde


def _lokaal(conn: sqlite3.Connection) -> Vraag:
    def vraag(sql: str) -> list[dict]:
        cur = conn.execute(sql)
        namen = [k[0] for k in cur.description] if cur.description else []
        return [dict(zip(namen, r)) for r in cur.fetchall()]
    return vraag


def _afdruk(vraag: Vraag, tabel: str, kolommen: list[str], blad: int) -> tuple[int, str]:
    """Het aantal rijen en een vingerafdruk over elke rij (rowid en alle kolommen), blad voor blad op rowid."""
    h = hashlib.sha256(tabel.encode())
    lijst = ", ".join(f"{_naam(k)} AS k{i}" for i, k in enumerate(kolommen))
    laatste, n = None, 0
    while True:
        voorwaarde = "" if laatste is None else f"WHERE rowid > {int(laatste)} "
        rijen = vraag(f"SELECT rowid AS r, {lijst} FROM {_naam(tabel)} {voorwaarde}ORDER BY rowid LIMIT {blad}")
        for rij in rijen:
            waarden = [_vorm(rij["r"])] + [_vorm(rij[f"k{i}"]) for i in range(len(kolommen))]
            h.update(json.dumps(waarden, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        n += len(rijen)
        if len(rijen) < blad:
            return n, h.hexdigest()
        laatste = rijen[-1]["r"]


def _blad(conn: sqlite3.Connection, tabel: str, kolommen: list[str]) -> int:
    som = " + ".join(f"coalesce(length(CAST({_naam(k)} AS BLOB)), 0)" for k in kolommen) or "0"
    gemiddeld = conn.execute(f"SELECT avg({som}) FROM {_naam(tabel)}").fetchone()[0] or 1
    return max(100, min(50_000, int(BLAD // max(gemiddeld, 1))))


def nakijken(bestand: str | Path, vraag: Vraag, *, zoekvragen: list[tuple[str, str]] = ZOEKVRAGEN,
             blad: int | None = None, melden: Callable[[str], None] = lambda s: None) -> dict:
    """Legt D1 naast de uitgave: per tabel het aantal rijen en een vingerafdruk over elke rij, de controle van de
    zoekregisters zelf, en de aantallen van de zoekvragen. Eén verschil en het weigert, met de tabel erbij."""
    conn = sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)
    lokaal = _lokaal(conn)
    try:
        verslag: dict = {"tabellen": {}, "verschillen": []}
        for t in volgorde(conn):
            kolommen = _kolommen(conn, t)
            b = blad or _blad(conn, t, kolommen)
            hier, daar = _afdruk(lokaal, t, kolommen, b), _afdruk(vraag, t, kolommen, b)
            verslag["tabellen"][t] = {"rijen": hier[0], "afdruk": hier[1]}
            if hier != daar:
                verslag["verschillen"].append(f"{t}: {hier[0]} rijen in de uitgave, {daar[0]} in D1"
                                              + ("" if hier[0] != daar[0] else ", maar niet dezelfde inhoud"))
            melden(f"{t}: {hier[0]} rijen {'gelijk' if hier == daar else 'ANDERS'}")
        for vt in _virtueel(conn):
            try:
                vraag(f"INSERT INTO {_naam(vt)}({_naam(vt)}) VALUES('integrity-check')")
            except Exception as fout:        # D1 meldt een register dat niet bij zijn tekst past als fout
                verslag["verschillen"].append(f"{vt}: de controle van het zoekregister faalde ({fout})")
        for tabel, zoekvraag in zoekvragen:
            sql = f"SELECT count(*) AS n FROM {_naam(tabel)} WHERE {_naam(tabel)} MATCH {literaal(zoekvraag)}"
            hier_n, daar_n = lokaal(sql)[0]["n"], vraag(sql)[0]["n"]
            if hier_n != daar_n:
                verslag["verschillen"].append(f"{tabel} {zoekvraag}: {hier_n} in de uitgave, {daar_n} in D1")
        verslag["zoekvragen"] = len(zoekvragen)
        meta = dict(conn.execute("SELECT sleutel, waarde FROM meta"))
        verslag["release"], verslag["controlegetal"] = meta.get("release"), meta.get("controlegetal")
    finally:
        conn.close()
    if verslag["verschillen"]:
        raise Weigering("D1 wijkt af van de uitgave: " + "; ".join(verslag["verschillen"]))
    return verslag


# --- de opdrachtregel -------------------------------------------------------------------------------------------------

def _nieuwste() -> Path:  # pragma: no cover - CLI
    kandidaten = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not kandidaten:
        raise SystemExit("geen uitgave in data/publicatie/")
    return kandidaten[-1]


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["sql", "aanmaken", "importeren", "nakijken"])
    p.add_argument("doel", nargs="?", help="sql: de uitgave (standaard de nieuwste); anders de release")
    p.add_argument("--database", help="importeren en nakijken: de naam in D1 (standaard factiz-<release>)")
    a = p.parse_args()
    try:
        if a.stap == "sql":
            bestand = Path(a.doel) if a.doel else _nieuwste()
            conn = sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)
            release = conn.execute("SELECT waarde FROM meta WHERE sleutel = 'release'").fetchone()[0]
            conn.close()
            klaar = schrijf(bestand, MAP / release)
            print(f"{MAP / release}: {len(klaar['delen'])} delen, "
                  f"{sum(d['opdrachten'] for d in klaar['delen'])} opdrachten, "
                  f"{sum(d['bytes'] for d in klaar['delen']) / 1e6:.1f} MB")
            return
        if not a.doel:
            raise SystemExit(f"{a.stap} vraagt de release, bijvoorbeeld 2026-11-16")
        database = a.database or f"factiz-{a.doel}"
        if a.stap == "aanmaken":
            print(aanmaken(a.doel, wrangler))
        elif a.stap == "importeren":
            print(importeren(MAP / a.doel, database, vraag=d1_vraag(database), voer_uit=wrangler))
        else:
            klaar = json.loads((MAP / a.doel / "klaar.json").read_text(encoding="utf-8"))
            verslag = nakijken(klaar["bron"], d1_vraag(database), melden=lambda s: print(s, flush=True))
            print(f"in orde: {len(verslag['tabellen'])} tabellen en {verslag['zoekvragen']} zoekvragen gelijk, "
                  f"release {verslag['release']}")
    except (Weigering, pb.Weigering) as fout:
        print(f"geweigerd: {fout}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
