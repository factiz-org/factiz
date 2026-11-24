"""Bonnetjes die blijven (PLAN #25.9).

Elke uitslag rust op een link naar de check van een redactie (DR1), en links
sterven: 5,2% van de bonnetjes was dood bij de meting van #25.6, Logically
Facts helemaal (§67). Het oordeel ís het bonnetje: claim, oordeel, uitgever en
datum blijven staan, wat de link ook doet. Deze module houdt per adres bij of
de bron nog bereikbaar is, en zoekt een archiefkopie op waar die bestaat.

Streng in één richting. Alleen wat aantoonbaar weg is telt als dood (zoals
#25.6), en een link heet pas offline na twee dode waarnemingen met minstens
`[bonnetjes] offline_na_uren` ertussen: ten onrechte "offline" is een foute
uitspraak over het werk van een redactie. Onduidelijk (een robotcontrole, een
time-out) telt nooit, niet als dood en niet als levend.

Er gaat niets naar archive.org behalve leesvragen aan de CDX-dienst; een
kopie laten maken (opslagverzoeken) is stap (b) van #25.9 en wacht op een
PO-besluit. De ronde leest per link alleen status en eindadres, nooit de
inhoud, per host één verzoek tegelijk, met robots.txt.

    python -m doublecheck.bonnetjes controleren [--alleen-dood]
    python -m doublecheck.bonnetjes toepassen --ronde data/bonnetjes/ronde-<datum>.jsonl
    python -m doublecheck.bonnetjes archief
    python -m doublecheck.bonnetjes rapport --ronde data/bonnetjes/ronde-<datum>.jsonl
"""

from __future__ import annotations

import collections
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

DOOD = frozenset({"dood", "zacht-dood"})
WAARNEMINGEN = frozenset({"levend", "onduidelijk"}) | DOOD
VELDEN = ("url", "uitkomst", "gecontroleerd_op", "laatst_levend", "dood_sinds", "laatst_dood",
          "archief_url", "archief_datum")
AGENT = "FactizLinkCheck"
CDX = "https://web.archive.org/cdx/search/cdx"
STANDAARDMAP = Path("data/bonnetjes")


def nu() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- de stand van één link ------------------------------------------------------

def neem_waar(rij: dict | None, url: str, uitkomst: str, tijdstip: str) -> dict:
    """De nieuwe stand na één waarneming. Levend beëindigt een dode reeks;
    onduidelijk verandert de reeks niet."""
    if uitkomst not in WAARNEMINGEN:
        raise ValueError(f"geen waarneming: {uitkomst}")
    nieuw = dict.fromkeys(VELDEN) if rij is None else dict(rij)
    nieuw.update(url=url, uitkomst=uitkomst, gecontroleerd_op=tijdstip)
    if uitkomst == "levend":
        nieuw.update(laatst_levend=tijdstip, dood_sinds=None, laatst_dood=None)
    elif uitkomst in DOOD:
        nieuw["dood_sinds"] = nieuw["dood_sinds"] or tijdstip
        nieuw["laatst_dood"] = tijdstip
    return nieuw


def is_offline(rij: dict | None, uren: int) -> bool:
    if not rij or not rij.get("dood_sinds") or not rij.get("laatst_dood"):
        return False
    tussenpoos = datetime.fromisoformat(rij["laatst_dood"]) - datetime.fromisoformat(rij["dood_sinds"])
    return tussenpoos >= timedelta(hours=uren)


def _dag(tijdstip: str | None) -> str | None:
    return tijdstip[:10] if tijdstip else None


def link_status(rij: dict, uren: int) -> dict:
    """Het object `link` bij een check in het antwoord (PROTOCOL §5)."""
    offline = is_offline(rij, uren)
    status = "offline" if offline else ("live" if rij["uitkomst"] == "levend" else "unclear")
    return {
        "status": status,
        "checked_on": _dag(rij["gecontroleerd_op"]),
        # De eerste dode waarneming van de reeks: de link kan eerder gestorven zijn.
        "offline_since": _dag(rij["dood_sinds"]) if offline else None,
        "last_seen_live": _dag(rij.get("laatst_levend")),
        "archive_url": rij.get("archief_url"),
        "archived_on": rij.get("archief_datum"),
    }


# --- opslag ---------------------------------------------------------------------

def sla_op(conn: sqlite3.Connection, rij: dict) -> None:
    """Schrijft één stand; de aanroeper commit (één keer per ronde, zodat een
    draaiende resolver zijn zoekcache niet bij elke link kwijtraakt)."""
    conn.execute(
        f"INSERT OR REPLACE INTO linkstatus ({', '.join(VELDEN)}) VALUES ({', '.join('?' for _ in VELDEN)})",
        [rij.get(veld) for veld in VELDEN],
    )


def lees(conn: sqlite3.Connection, urls) -> dict[str, dict]:
    urls = list(dict.fromkeys(urls))
    gevonden: dict[str, dict] = {}
    for begin in range(0, len(urls), 500):
        deel = urls[begin:begin + 500]
        for rij in conn.execute(
            f"SELECT {', '.join(VELDEN)} FROM linkstatus WHERE url IN ({', '.join('?' for _ in deel)})", deel
        ):
            gevonden[rij[0]] = dict(zip(VELDEN, rij))
    return gevonden


def links_voor(conn: sqlite3.Connection, urls, uren: int) -> dict[str, dict]:
    """Per gecontroleerd adres het object `link`; een nooit gecontroleerd
    adres ontbreekt."""
    return {url: link_status(rij, uren) for url, rij in lees(conn, urls).items()}


# --- archiefkopieën -------------------------------------------------------------

def sleutel(url: str) -> str:
    """Vergelijkingssleutel voor een adres: zonder schema, `www.`, kast,
    afsluitende schuine streep en fragment; de query blijft."""
    deel = urlsplit(url.strip())
    host = (deel.hostname or "").lower().removeprefix("www.")
    pad = deel.path.rstrip("/").lower()
    return host + pad + (f"?{deel.query.lower()}" if deel.query else "")


def _stempel(tijdstip: str) -> str:
    """ISO-tijdstip naar de veertien cijfers van de Wayback Machine."""
    return "".join(teken for teken in tijdstip[:19] if teken.isdigit())


def archief_uit_cdx(regels: list[list[str]], doden: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Per dood adres de laatste opname met status 200 van vóór de eerste dode
    waarneming. `regels` is de JSON-uitvoer van de CDX-dienst met de velden
    `original,timestamp` en eventueel `statuscode` (kop, opnames, en soms een
    vervolgsleutel); `doden` geeft per adres het begin van de dode reeks."""
    per_sleutel: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for url, dood_sinds in doden.items():
        per_sleutel[sleutel(url)].append((url, _stempel(dood_sinds)))
    beste: dict[str, tuple[str, str]] = {}
    for regel in regels:
        if len(regel) < 2:
            continue
        origineel, stempel = regel[0], regel[1]
        if len(stempel) != 14 or not stempel.isdigit() or (len(regel) > 2 and regel[2] != "200"):
            continue
        for url, grens in per_sleutel.get(sleutel(origineel), ()):
            if stempel < grens and (url not in beste or stempel > beste[url][0]):
                beste[url] = (stempel, origineel)
    return {
        url: (f"https://web.archive.org/web/{stempel}/{origineel}", f"{stempel[:4]}-{stempel[4:6]}-{stempel[6:8]}")
        for url, (stempel, origineel) in beste.items()
    }


def archiefgroepen(doden: dict[str, str], drempel: int) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Hosts met minstens `drempel` dode adressen krijgen één lijst per host
    (een hele site die verdween, zoals Logically Facts); de rest één vraag per
    adres. Een lijst voor een grote levende site zou miljoenen opnames tellen."""
    per_host: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for url, dood_sinds in doden.items():
        per_host[(urlsplit(url).hostname or "").lower().removeprefix("www.")][url] = dood_sinds
    groot = {host: adressen for host, adressen in per_host.items() if len(adressen) >= drempel}
    los = {url: d for host, adressen in per_host.items() if host not in groot for url, d in adressen.items()}
    return groot, los


def _cdx_vraag(web, params: dict, *, pogingen: int = 4, wacht: float = 30.0):
    """Eén leesvraag aan de CDX-dienst, met herkansing bij een storing of een
    beperking (429, 5xx, time-out). `None` als het niet lukt."""
    import httpx

    for poging in range(pogingen):
        try:
            antwoord = web.get(CDX, params=params)
        except httpx.HTTPError:
            antwoord = None
        if antwoord is not None and antwoord.status_code == 200:
            return antwoord
        if antwoord is not None and antwoord.status_code not in (429,) and antwoord.status_code < 500:
            return None
        time.sleep(wacht * (poging + 1))
    return None


def _json(antwoord) -> list[list[str]]:
    try:
        return antwoord.json() if antwoord is not None and antwoord.text.strip() else []
    except ValueError:
        return []


def cdx_adres(web, url: str) -> list[list[str]] | None:
    """Alleen lezen: alle opnames van één adres, met status; filteren doen we
    zelf, want een filter op de server maakt de vraag twee keer zo traag."""
    antwoord = _cdx_vraag(web, {"url": url, "output": "json", "fl": "original,timestamp,statuscode"})
    return None if antwoord is None else _json(antwoord)


def cdx_host(web, host: str, tot: str, *, pauze: float, max_paginas: int = 100) -> tuple[list[list[str]], bool]:
    """Alleen lezen: alle opnames met status 200 onder een host tot `tot`, in
    pagina's van 5.000. Geeft de regels en of de lijst volledig is."""
    params = {"url": f"{host}/", "matchType": "prefix", "output": "json", "fl": "original,timestamp",
              "filter": "statuscode:200", "to": _stempel(tot), "limit": "5000", "showResumeKey": "true"}
    regels: list[list[str]] = []
    for _ in range(max_paginas):
        data = _json(_cdx_vraag(web, params))
        if not data:
            return regels, False
        if len(data) >= 2 and data[-2] == []:
            regels += data[:-2]
            params["resumeKey"] = data[-1][0]
            time.sleep(pauze)
            continue
        return regels + data, True
    return regels, False


# --- de ronde -------------------------------------------------------------------

def ronde(urls, controleer, robots_voor, *, proef: int = 10, pauze: float = 2.0, threads: int = 12,
          schrijf, gedaan=frozenset()) -> collections.Counter:
    """Controleert elk adres één keer. Per host één verzoek tegelijk met
    `pauze` ertussen, hosts parallel. robots.txt verbiedt: niet gevraagd.
    Zijn de eerste `proef` gevraagde adressen van een host allemaal
    onduidelijk (een robotcontrole), dan slaat de ronde de rest van die host
    over. `gedaan` maakt de ronde hervatbaar. `schrijf` krijgt per adres een
    regel en wordt nooit door twee draden tegelijk aangeroepen."""
    import concurrent.futures as cf

    per_host: dict[str, list[str]] = collections.defaultdict(list)
    for url in dict.fromkeys(urls):
        if url not in gedaan:
            per_host[urlsplit(url).hostname or ""].append(url)
    slot = threading.Lock()
    teller: collections.Counter = collections.Counter()

    def noteer(regel: dict) -> None:
        with slot:
            schrijf(regel)
            teller[regel["uitkomst"]] += 1

    def host_werk(host: str) -> None:
        robots = robots_voor(host)
        gevraagd = onduidelijk = 0
        for url in per_host[host]:
            if proef and gevraagd >= proef and onduidelijk == gevraagd:
                noteer({"url": url, "uitkomst": "overgeslagen", "reden": "robotcontrole", "tijdstip": nu()})
                continue
            if robots is not None and not robots.can_fetch(AGENT, url):
                noteer({"url": url, "uitkomst": "verboden", "tijdstip": nu()})
                continue
            uitkomst = controleer(url)
            gevraagd += 1
            onduidelijk += uitkomst == "onduidelijk"
            noteer({"url": url, "uitkomst": uitkomst, "tijdstip": nu()})
            if pauze:
                time.sleep(pauze)

    with cf.ThreadPoolExecutor(max(1, threads)) as pool:
        list(pool.map(host_werk, sorted(per_host, key=lambda h: len(per_host[h]), reverse=True)))
    return teller


def _robots_voor(web):
    import urllib.robotparser

    from doublecheck.artikelbeelden import _haal

    def robots(host: str):
        antwoord = _haal(web, f"https://{host}/robots.txt")
        if antwoord is None or antwoord.status_code != 200:
            return None
        lezer = urllib.robotparser.RobotFileParser()
        lezer.parse(antwoord.text.splitlines())
        return lezer

    return robots


def lees_ronde(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    inhoud = inhoud[:inhoud.rfind("\n") + 1]   # een afgebroken laatste regel telt niet
    return [json.loads(r) for r in inhoud.splitlines() if r.strip()]


def pas_toe(conn: sqlite3.Connection, regels: list[dict]) -> collections.Counter:
    """Zet de waarnemingen van een ronde in `linkstatus`, in één transactie."""
    waarnemingen = [r for r in regels if r["uitkomst"] in WAARNEMINGEN]
    standen = lees(conn, (r["url"] for r in waarnemingen))
    teller: collections.Counter = collections.Counter()
    with conn:
        for regel in sorted(waarnemingen, key=lambda r: r["tijdstip"]):
            stand = neem_waar(standen.get(regel["url"]), regel["url"], regel["uitkomst"], regel["tijdstip"])
            standen[regel["url"]] = stand
            sla_op(conn, stand)
            teller[regel["uitkomst"]] += 1
    return teller


# --- het rapport ----------------------------------------------------------------

def rapport(regels: list[dict], *, min_dood: int, aandeel: float) -> dict:
    """Bron-gezondheid per host: gecontroleerd, dood, onduidelijk, en een
    waarschuwing vanaf `min_dood` dode links én `aandeel` dood."""
    from doublecheck.benchmark import upper_bound_95

    per_host: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for regel in regels:
        per_host[(urlsplit(regel["url"]).hostname or "").removeprefix("www.")][regel["uitkomst"]] += 1
    hosts = {}
    for host, tel in per_host.items():
        gezien = sum(tel[k] for k in WAARNEMINGEN)
        dood = sum(tel[k] for k in DOOD)
        hosts[host] = {
            "gezien": gezien, "dood": dood, "onduidelijk": tel["onduidelijk"],
            "overgeslagen": tel["overgeslagen"], "verboden": tel["verboden"],
            "aandeel_dood": dood / gezien if gezien else 0.0,
            "waarschuwing": dood >= min_dood and gezien > 0 and dood / gezien >= aandeel,
        }
    gezien = sum(h["gezien"] for h in hosts.values())
    dood = sum(h["dood"] for h in hosts.values())
    return {
        "gezien": gezien, "dood": dood, "aandeel_dood": dood / gezien if gezien else 0.0,
        "bovengrens95_dood": upper_bound_95(dood, gezien) if gezien else 1.0,
        "onduidelijk": sum(h["onduidelijk"] for h in hosts.values()),
        "overgeslagen": sum(h["overgeslagen"] for h in hosts.values()),
        "verboden": sum(h["verboden"] for h in hosts.values()),
        "hosts": hosts,
    }


# --- opdrachtregel --------------------------------------------------------------

def _check_urls(conn: sqlite3.Connection) -> list[str]:
    """De unieke check-adressen van claims in de index (B28)."""
    from doublecheck.toelating import buiten_index

    buiten = buiten_index(conn)
    return sorted({url for claim_id, url in conn.execute("SELECT claim_id, url FROM factcheck")
                   if claim_id not in buiten and url.startswith("http")})


def main() -> None:
    import argparse
    import os

    import httpx

    from doublecheck.config import load_config
    from doublecheck.linkrot import USER_AGENT, _controleer
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Bonnetjes die blijven (#25.9)")
    parser.add_argument("stap", choices=("controleren", "toepassen", "archief", "rapport"))
    parser.add_argument("--map", default=str(STANDAARDMAP))
    parser.add_argument("--ronde", help="het logbestand van een ronde (toepassen, rapport; bij controleren: hervatten)")
    parser.add_argument("--alleen-dood", action="store_true", help="alleen de adressen met een dode reeks")
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--pauze", type=float, default=2.0)
    parser.add_argument("--proef", type=int, default=10)
    parser.add_argument("--host-drempel", type=int, default=50,
                        help="vanaf zoveel offline adressen één archieflijst per host")
    parser.add_argument("--max", type=int, help="een reproduceerbare steekproef van zoveel adressen (proefronde)")
    args = parser.parse_args()

    config = load_config().bonnetjes
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    init_schema(conn)
    map_ = Path(args.map)

    if args.stap == "controleren":
        if args.alleen_dood:
            urls = sorted(r[0] for r in conn.execute("SELECT url FROM linkstatus WHERE dood_sinds IS NOT NULL"))
        else:
            urls = _check_urls(conn)
        if args.max:
            from doublecheck.linkrot import steekproef

            urls = steekproef(urls, args.max)
        map_.mkdir(parents=True, exist_ok=True)
        soort = "-dood" if args.alleen_dood else (f"-proef{args.max}" if args.max else "")
        # Hervatten na een herstart, ook op een latere dag: `--ronde` wijst
        # naar de log die al loopt; zonder draagt de log de datum van vandaag.
        pad = Path(args.ronde) if args.ronde else map_ / f"ronde-{nu()[:10]}{soort}.jsonl"
        from doublecheck.beeldindex import herstel

        herstel(pad)   # een halve laatste regel van een onderbroken ronde weg
        gedaan = {r["url"] for r in lees_ronde(pad)}
        print(f"{len(urls)} adressen, {len(gedaan)} al gedaan; log: {pad}", flush=True)
        with httpx.Client(follow_redirects=True, timeout=12.0, headers={"User-Agent": USER_AGENT}) as web, \
                pad.open("a", encoding="utf-8") as uit:
            def schrijf(regel: dict) -> None:
                uit.write(json.dumps(regel, ensure_ascii=False) + "\n")
                uit.flush()

            teller = ronde(urls, lambda url: _controleer(web, url)[1], _robots_voor(web), proef=args.proef,
                           pauze=args.pauze, threads=args.threads, schrijf=schrijf, gedaan=gedaan)
        print(dict(teller))
    elif args.stap == "toepassen":
        teller = pas_toe(conn, lees_ronde(Path(args.ronde)))
        offline = sum(is_offline(rij, config.offline_na_uren) for rij in lees(
            conn, (r[0] for r in conn.execute("SELECT url FROM linkstatus WHERE dood_sinds IS NOT NULL"))).values())
        print(f"toegepast: {dict(teller)}; offline volgens de regel: {offline}")
    elif args.stap == "archief":
        # Alleen links die volgens de regel offline zijn: alleen daar toont
        # het antwoord een archiefkopie.
        standen = lees(conn, (r[0] for r in conn.execute("SELECT url FROM linkstatus WHERE dood_sinds IS NOT NULL")))
        doden = {url: rij["dood_sinds"] for url, rij in standen.items()
                 if is_offline(rij, config.offline_na_uren) and not rij.get("archief_url")}
        map_.mkdir(parents=True, exist_ok=True)
        logpad = map_ / "archief.jsonl"
        gedaan = {r["url"] for r in lees_ronde(logpad)}
        doden = {url: d for url, d in doden.items() if url not in gedaan}
        groot, los = archiefgroepen(doden, args.host_drempel)
        print(f"{len(doden)} offline adressen te zoeken: {sum(map(len, groot.values()))} via een lijst per host "
              f"({', '.join(sorted(groot)) or 'geen'}), {len(los)} los; alleen leesvragen", flush=True)
        with httpx.Client(timeout=90.0, headers={"User-Agent": USER_AGENT}) as web, \
                logpad.open("a", encoding="utf-8") as uit:
            def noteer(url: str, kopie, bron: str) -> None:
                uit.write(json.dumps({"url": url, "archief_url": kopie[0] if kopie else None,
                                      "archief_datum": kopie[1] if kopie else None, "via": bron,
                                      "tijdstip": nu()}, ensure_ascii=False) + "\n")
                uit.flush()

            for host, adressen in sorted(groot.items()):
                regels, volledig = cdx_host(web, host, max(adressen.values()), pauze=args.pauze)
                kopieen = archief_uit_cdx(regels, adressen)
                for url in adressen:
                    if url in kopieen or volledig:
                        noteer(url, kopieen.get(url), "host")
                    else:
                        los[url] = adressen[url]   # lijst afgekapt: dan alsnog los
                print(f"  {host}: {len(kopieen)} van {len(adressen)} met kopie"
                      f"{'' if volledig else ' (lijst afgekapt, de rest los)'}", flush=True)
            for i, (url, dood_sinds) in enumerate(sorted(los.items()), 1):
                regels = cdx_adres(web, url)
                if regels is not None:
                    noteer(url, archief_uit_cdx(regels, {url: dood_sinds}).get(url), "adres")
                if i % 50 == 0:
                    print(f"  los {i}/{len(los)}", flush=True)
                time.sleep(args.pauze)
        # In één transactie, zoals een ronde.
        met = 0
        with conn:
            for regel in lees_ronde(logpad):
                if regel["archief_url"]:
                    met += conn.execute("UPDATE linkstatus SET archief_url = ?, archief_datum = ? WHERE url = ?",
                                        (regel["archief_url"], regel["archief_datum"], regel["url"])).rowcount
        print(f"archiefkopieën in de database: {met}")
    else:
        r = rapport(lees_ronde(Path(args.ronde)), min_dood=config.waarschuwing_min_dood,
                    aandeel=config.waarschuwing_aandeel)
        print(f"gezien {r['gezien']} · dood {r['dood']} ({r['aandeel_dood']:.1%}, bovengrens 95% "
              f"{r['bovengrens95_dood']:.1%}) · onduidelijk {r['onduidelijk']} · overgeslagen "
              f"{r['overgeslagen']} · verboden {r['verboden']}")
        for host, h in sorted(r["hosts"].items(), key=lambda kv: -kv[1]["dood"]):
            if h["waarschuwing"]:
                print(f"  waarschuwing {host}: {h['dood']} van {h['gezien']} dood ({h['aandeel_dood']:.0%})")
        for host, h in sorted(r["hosts"].items()):
            if h["overgeslagen"]:
                print(f"  overgeslagen {host}: {h['overgeslagen']} (robotcontrole)")


if __name__ == "__main__":
    main()
