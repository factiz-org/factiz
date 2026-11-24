"""Eén commando voor een uitgave (PLAN #34.2bo stap 9, B80).

    python -m doublecheck.uitrol voorbereiden [--release <naam>]
    python -m doublecheck.uitrol live <release> --akkoord '<datum>, PO: "…"'

`voorbereiden` doet wat op de Mac gebeurt en raakt het account niet: de uitgave bouwen (`publiceren bouwen`), de SQL voor
D1 (`d1uitgave sql`) en het geheugen van de Worker (`site/scripts/geheugen.ts`). Wat al klaar is, slaat het over. Zonder
naam neemt het de eerste vrije: vandaag, anders vandaag met een letter (2026-11-16b).

`live` doet de rest, alleen met het akkoord van de PO (elke uitrol vraagt een ja): de database aanmaken, importeren en
nakijken, de binding `DB` in `site/wrangler.jsonc` naar de nieuwe database, de Worker bouwen, uitrollen, factiz.org
nakijken en, alleen in een open stand van `FACTIZ_VINDBAAR`, de nieuwe adressen aan IndexNow melden (PLAN #34.2bt). De stand staat na elke stap in `data/d1/<release>/uitrol.json`; na een fout begint een nieuwe aanroep bij de stap
die misging, zodat nooit twee keer in dezelfde database geïmporteerd wordt. De vorige database blijft staan.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "d1"
PUBLICATIE = WORTEL / "data" / "publicatie"
CONFIG = WORTEL / "site" / "wrangler.jsonc"
WRANGLER = WORTEL / "site" / "node_modules" / ".bin" / "wrangler"
SITE = "https://factiz.org"
AFZENDER = "FactizUitrolBot/1.0 (nakijken na een uitrol)"  # Cloudflare weigert die van urllib (1010); "Bot" telt als robot
LIVE = ("aanmaken", "importeren", "nakijken", "binding", "worker", "uitrollen", "controle", "melden")

_AKKOORD = re.compile(r'\d{4}-\d{2}-\d{2}, PO: "[^"\n]{2,}"')
_DATABASE = re.compile(r'factiz-\d{4}-\d{2}-\d{2}[a-z]?')
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_BINDING = re.compile(r'(\{\s*"binding":\s*"DB",\s*"database_name":\s*")([^"]+)(",\s*"database_id":\s*")([^"]+)(")')
_VERSIE = re.compile(r"Current Version ID:\s*([0-9a-f-]{36})")


class Weigering(Exception):
    """De stap mag zo niet, of het nakijken vond iets."""


# --- wat zonder het account te toetsen is ----------------------------------------------------------------------------

def lees_database(tekst: str) -> tuple[str, str]:
    """De database achter de binding `DB` in `wrangler.jsonc`: haar naam en id."""
    gevonden = _BINDING.findall(tekst)
    if len(gevonden) != 1:
        raise Weigering(f"wrangler.jsonc heeft {len(gevonden)} bindingen DB, verwacht 1")
    return gevonden[0][1], gevonden[0][3]


def zet_database(tekst: str, naam: str, id_: str) -> str:
    """`wrangler.jsonc` met de binding `DB` naar een andere database; de rest blijft letterlijk zoals het was."""
    lees_database(tekst)
    if not _DATABASE.fullmatch(naam) or not _ID.fullmatch(id_):
        raise Weigering(f"geen geldige database: {naam!r}, {id_!r}")
    return _BINDING.sub(lambda m: f"{m.group(1)}{naam}{m.group(3)}{id_}{m.group(5)}", tekst)


def volgende_naam(bestaande: set[str], vandaag: str) -> str:
    """De eerste vrije naam: vandaag, anders vandaag met de volgende letter."""
    if vandaag not in bestaande:
        return vandaag
    for letter in "bcdefghijklmnopqrstuvwxyz":
        if vandaag + letter not in bestaande:
            return vandaag + letter
    raise Weigering(f"geen vrije naam meer op {vandaag}")


def akkoord(tekst: str) -> str:
    """Het akkoord van de PO zoals het bewaard wordt: de dag en haar woorden."""
    if not _AKKOORD.fullmatch(tekst or ""):
        raise Weigering("een uitrol vraagt het akkoord van de PO als '<datum>, PO: \"<haar woorden>\"'")
    return tekst


def niet_klaar(map_: Path, release: str) -> list[str]:
    """Wat van `voorbereiden` nog ontbreekt voor deze uitgave; leeg als `live` mag beginnen."""
    uit = []
    klaar = map_ / "klaar.json"
    if not klaar.exists():
        uit.append("de SQL voor D1 ontbreekt (voorbereiden)")
    elif (van := json.loads(klaar.read_text(encoding="utf-8")).get("release")) != release:
        uit.append(f"de SQL is van {van}, niet van {release}")
    index = map_ / "geheugen" / "index.json"
    if not index.exists():
        uit.append("het geheugen ontbreekt (voorbereiden)")
    elif (van := json.loads(index.read_text(encoding="utf-8")).get("release")) != release:
        uit.append(f"het geheugen is van {van}, niet van {release}")
    return uit


def al_live(config: str, release: str, stand: dict | None) -> bool:
    """Of deze uitgave al live staat: de Worker leest haar database al, of de stand zegt dat ze uitgerold is."""
    return lees_database(config)[0] == f"factiz-{release}" or "uitrollen" in ((stand or {}).get("stappen") or {})


def voer_uit(stappen: dict[str, Callable[[dict], dict]], stand_pad: Path, *, akkoord_: str, release: str) -> dict:
    """De stappen van `live` in de vaste volgorde; na elke stap de stand op schijf, en wat al klaar is gaat niet nog eens.
    Een stap krijgt de stand, met wat de stappen ervoor vonden. Een fout stopt alles, de stand blijft."""
    stand = json.loads(stand_pad.read_text(encoding="utf-8")) if stand_pad.exists() else {"release": release, "stappen": {}}
    if stand.get("release") != release:
        raise Weigering(f"{stand_pad} hoort bij {stand.get('release')}, niet bij {release}")
    stand["akkoord"] = akkoord_
    stand_pad.parent.mkdir(parents=True, exist_ok=True)
    for naam in LIVE:
        if naam in stand["stappen"]:
            continue
        stand["stappen"][naam] = stappen[naam](stand)
        stand_pad.write_text(json.dumps(stand, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return stand


def live_klopt(status: int, html: str, robots: str, release: str, stand: int = 0) -> list[str]:
    """Wat er op factiz.org nog niet klopt: de pagina, de uitgave (in het adres van het deelplaatje) en robots.txt, dicht
    in stand 0 en open met de sitemap in een open stand (PLAN #34.2bt)."""
    uit = []
    if status != 200:
        uit.append(f"de factcheckpagina gaf {status}")
    elif not re.search(r"\?v=" + re.escape(release) + r"(?![0-9a-z])", html):
        uit.append(f"factiz.org toont nog niet de uitgave {release}")
    regels = robots.splitlines()
    if not stand and "Disallow: /" not in regels:
        uit.append("robots.txt zet de site niet dicht")
    if stand and ("Disallow: /" in regels or f"Sitemap: {SITE}/sitemap.xml" not in regels):
        uit.append(f"robots.txt staat niet open zoals stand {stand} zegt")
    return uit


def versie_uit(uit: str) -> str:
    """De versie die wrangler na het uitrollen noemt; een fout of geen versie is een weigering."""
    fout = next((r for r in uit.splitlines() if "[ERROR]" in r), None)
    gevonden = _VERSIE.search(uit)
    if fout or not gevonden:
        raise Weigering(f"het uitrollen gaf geen versie{': ' + fout.strip() if fout else ''}")
    return gevonden.group(1)


# --- de stappen zelf -------------------------------------------------------------------------------------------------

def _druk(uit: str) -> None:  # pragma: no cover - uitvoer
    """Uitvoer van wrangler, zonder regels met het account of een adres."""
    for r in uit.splitlines():
        if r.strip() and not re.search(r"account|@", r, re.IGNORECASE):
            print("   ", r.rstrip())


def _draai(args: list[str], cwd: Path = WORTEL) -> str:  # pragma: no cover - roept een programma aan
    uit = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if uit.returncode:
        _druk(uit.stdout[-3000:] + uit.stderr[-3000:])
        raise Weigering(f"{' '.join(Path(a).name if i == 0 else a for i, a in enumerate(args[:4]))} mislukte")
    return uit.stdout + uit.stderr


def _bestaande() -> set[str]:  # pragma: no cover - bestanden
    return {p.name for m in (PUBLICATIE, MAP) if m.exists() for p in m.iterdir() if p.is_dir()}


def voorbereiden(release: str | None) -> str:  # pragma: no cover - bouwt op de Mac
    from doublecheck import d1uitgave as d1
    from doublecheck import publiceren as pb

    naam = pb.releasenaam(release) if release else volgende_naam(_bestaande(), date.today().isoformat())
    stand_pad = MAP / naam / "uitrol.json"
    stand = json.loads(stand_pad.read_text(encoding="utf-8")) if stand_pad.exists() else None
    if al_live(CONFIG.read_text(encoding="utf-8"), naam, stand):
        raise Weigering(f"de uitgave {naam} staat al live; kies een nieuwe naam")
    bestand = PUBLICATIE / naam / "publicatie.db"
    print(f"uitgave {naam}")
    if bestand.exists():
        print("1. bouwen: er is al een uitgave, die blijft")
    else:
        print("1. bouwen ...", flush=True)
        _draai([sys.executable, "-m", "doublecheck.publiceren", "bouwen", "--release", naam])
    print("   nakijken:", pb.controleer(bestand))
    klaar = MAP / naam / "klaar.json"
    with sqlite3.connect(f"file:{bestand}?mode=ro", uri=True) as c:
        getal = c.execute("SELECT waarde FROM meta WHERE sleutel = 'controlegetal'").fetchone()[0]
    if klaar.exists() and json.loads(klaar.read_text(encoding="utf-8")).get("controlegetal") == getal:
        print("2. de SQL voor D1: er al, voor deze uitgave")
    else:
        print("2. de SQL voor D1 ...", flush=True)
        k = d1.schrijf(bestand, MAP / naam)
        print(f"   {len(k['delen'])} delen, {sum(d['bytes'] for d in k['delen']) / 1e6:.1f} MB")
    index = MAP / naam / "geheugen" / "index.json"
    if index.exists() and json.loads(index.read_text(encoding="utf-8")).get("release") == naam:
        print("3. het geheugen: er al, voor deze uitgave")
    else:
        print("3. het geheugen ...", flush=True)
        _draai(["node", "site/scripts/geheugen.ts", str(bestand), str(MAP / naam / "geheugen")])
    ontbreekt = niet_klaar(MAP / naam, naam)
    if ontbreekt:
        raise Weigering("; ".join(ontbreekt))
    print(f"klaar op de Mac. Naar factiz.org, met een ja van de PO:\n"
          f"    python -m doublecheck.uitrol live {naam} --akkoord '<datum>, PO: \"<haar woorden>\"'")
    return naam


def _haal(adres: str) -> tuple[int, str]:  # pragma: no cover - het net
    verzoek = urllib.request.Request(adres, headers={"User-Agent": AFZENDER})
    try:
        with urllib.request.urlopen(verzoek, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as fout:
        return fout.code, ""


def live(release: str, akkoord_tekst: str) -> dict:  # pragma: no cover - het account
    from doublecheck import d1uitgave as d1
    from doublecheck import indexnow
    from doublecheck import publiceren as pb

    akkoord_ = akkoord(akkoord_tekst)
    map_ = MAP / release
    ontbreekt = niet_klaar(map_, release)
    if ontbreekt:
        raise Weigering("eerst voorbereiden: " + "; ".join(ontbreekt))
    stand = json.loads((map_ / "uitrol.json").read_text(encoding="utf-8")) if (map_ / "uitrol.json").exists() else None
    # pas klaar na de laatste stap: mislukt het melden (2026-11-23, IndexNow op een ouder schema), dan gaat `live` daar verder
    if al_live(CONFIG.read_text(encoding="utf-8"), release, stand) and "melden" in ((stand or {}).get("stappen") or {}):
        raise Weigering(f"de uitgave {release} staat al live, is nagekeken en gemeld")
    if lees_database(CONFIG.read_text(encoding="utf-8"))[0] == f"factiz-{release}" and not stand:
        raise Weigering(f"de Worker leest factiz-{release} al, maar zonder stand van deze uitrol: niets aangeraakt")
    klaar = json.loads((map_ / "klaar.json").read_text(encoding="utf-8"))
    pb.controleer(klaar["bron"])

    def aanmaken(s):
        print("1. de database aanmaken ...", flush=True)
        return d1.aanmaken(release, d1.wrangler)

    def importeren(s):
        naam = s["stappen"]["aanmaken"]["naam"]
        print(f"2. importeren in {naam} ...", flush=True)
        return d1.importeren(map_, naam, vraag=d1.d1_vraag(naam), voer_uit=d1.wrangler)

    def nakijken(s):
        naam = s["stappen"]["aanmaken"]["naam"]
        print(f"3. {naam} naast de uitgave leggen ...", flush=True)
        v = d1.nakijken(klaar["bron"], d1.d1_vraag(naam))
        return {"tabellen": len(v["tabellen"]), "zoekvragen": v["zoekvragen"], "release": v["release"]}

    def binding(s):
        nieuw = s["stappen"]["aanmaken"]
        tekst = CONFIG.read_text(encoding="utf-8")
        vorige = lees_database(tekst)
        CONFIG.write_text(zet_database(tekst, nieuw["naam"], nieuw["id"]), encoding="utf-8")
        print(f"4. de Worker leest voortaan {nieuw['naam']} (was {vorige[0]})")
        return {"vorige": {"naam": vorige[0], "id": vorige[1]}, "nieuw": nieuw}

    def worker(s):
        print("5. de Worker bouwen ...", flush=True)
        _draai(["npm", "--prefix", "site", "run", "build:worker"])
        return {"gebouwd": True}

    def uitrollen(s):
        print("6. uitrollen naar factiz.org ...", flush=True)
        uit = _draai([str(WRANGLER), "deploy", "--config", "dist-worker/server/wrangler.json"], cwd=WORTEL / "site")
        _druk("\n".join(r for r in uit.splitlines() if re.search(r"custom domain|Version ID|env\.DB", r)))
        return {"versie": versie_uit(uit)}

    def controle(s):
        with sqlite3.connect(f"file:{klaar['bron']}?mode=ro", uri=True) as c:
            nummer = c.execute("SELECT nummer FROM pagina ORDER BY nummer LIMIT 1").fetchone()[0]
        print(f"7. factiz.org nakijken (/fact-checks/{nummer}/) ...", flush=True)
        problemen: list[str] = []
        for _ in range(12):
            status, html = _haal(f"{SITE}/fact-checks/{nummer}/")
            problemen = live_klopt(status, html, _haal(f"{SITE}/robots.txt")[1], release, indexnow.stand_uit(
                CONFIG.read_text(encoding="utf-8")))
            if not problemen:
                return {"pagina": nummer}
            time.sleep(10)
        raise Weigering("factiz.org: " + "; ".join(problemen))

    def melden(s):
        # IndexNow (PLAN #34.2bt): alleen in een open stand, en alleen wat sinds de vorige uitgave nieuw of anders is
        st = indexnow.stand_uit(CONFIG.read_text(encoding="utf-8"))
        vorige = PUBLICATIE / s["stappen"]["binding"]["vorige"]["naam"].removeprefix("factiz-") / "publicatie.db"
        print(f"8. IndexNow ({f'stand {st}' if st else 'dicht, niets gemeld'}) ...", flush=True)
        return indexnow.melden(st, vorige if vorige.exists() else None, klaar["bron"])

    stand = voer_uit({"aanmaken": aanmaken, "importeren": importeren, "nakijken": nakijken, "binding": binding,
                      "worker": worker, "uitrollen": uitrollen, "controle": controle, "melden": melden},
                     map_ / "uitrol.json", akkoord_=akkoord_, release=release)
    b = stand["stappen"]["binding"]
    print(f"live: uitgave {release} op {b['nieuw']['naam']}, versie {stand['stappen']['uitrollen']['versie']}.\n"
          f"De vorige database {b['vorige']['naam']} blijft staan. Terug: `npx wrangler rollback` vanuit site/ (de vorige "
          f"versie met haar eigen database) en `git checkout site/wrangler.jsonc`.\n"
          f"Nog te doen: site/wrangler.jsonc committen.")
    return stand


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["voorbereiden", "live"])
    p.add_argument("release", nargs="?", help="live: de uitgave die voorbereid is")
    p.add_argument("--release", dest="naam", help="voorbereiden: de naam (standaard de eerste vrije)")
    p.add_argument("--akkoord", help="live: '<datum>, PO: \"<haar woorden>\"'")
    a = p.parse_args()
    from doublecheck import d1uitgave as d1
    from doublecheck import publiceren as pb
    try:
        if a.stap == "voorbereiden":
            voorbereiden(a.naam or a.release)
        else:
            if not a.release:
                raise Weigering("live vraagt de uitgave, bijvoorbeeld 2026-11-17")
            live(pb.releasenaam(a.release), a.akkoord or "")
    except (Weigering, d1.Weigering, pb.Weigering) as fout:
        print(f"geweigerd: {fout}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
