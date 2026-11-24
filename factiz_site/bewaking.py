"""Bewaking van factiz.org (PLAN #34.2bv).

    python -m factiz_site.bewaking [--n 12] [--zonder-d1] [--melding]

Vraagt de vaste pagina's en robots.txt op, en een stel willekeurige factchecks met hun deelplaatje (elke keer andere, en het
deelplaatje zonder versie in het adres, dus nooit uit de cache): zo ziet ze ook een verzoek dat Workers afbreekt, dat de
Worker zelf niet meer kan tellen. Daarnaast leest ze de storingen (antwoorden van 500 of hoger) die de Worker telde, uit de D1
`factiz-tellingen`, alleen lezen. robots.txt moet passen bij de stand van `FACTIZ_VINDBAAR` in site/wrangler.jsonc.

Elke keer één regel in `data/bewaking/log.jsonl`: goed, of wat er mis is. Met `--melding` op een Mac een melding bij een
probleem; geen mail en geen dienst van een ander. Als robot (de User-Agent zegt Bot), dus het telt niet als bezoek. Elke
dag: `deploy/org.factiz.bewaking.plist`.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from factiz_site import i18n, tellen

WORTEL = Path(__file__).resolve().parent.parent
CONFIG = WORTEL / "site" / "wrangler.jsonc"
PUBLICATIE = WORTEL / "data" / "publicatie"
LOG = WORTEL / "data" / "bewaking" / "log.jsonl"
SITE = "https://factiz.org"
AFZENDER = "FactizBewakingBot/1.0 (nakijken van factiz.org)"    # Cloudflare weigert die van urllib (1010); Bot telt als robot
TELLINGEN = "factiz-tellingen"
VAST = ("/", "/nl/", "/fact-checks/", "/themes/", "/dossiers/", "/about/")
TRAAG = 20.0                        # seconden: langer is een probleem, ook als het antwoord goed is


def stand_uit(config: str) -> int:
    """De stand van `FACTIZ_VINDBAAR` in `vars` van site/wrangler.jsonc: 1, 2 of 3, anders 0 (dicht)."""
    m = re.search(r'"FACTIZ_VINDBAAR"\s*:\s*"([0-9])"', config or "")
    return int(m.group(1)) if m and m.group(1) in ("1", "2", "3") else 0


def uitgave_uit(config: str) -> str | None:
    """De uitgave die de Worker leest: de naam van de database `factiz-<uitgave>` in de binding DB."""
    m = re.search(r'"binding":\s*"DB",\s*"database_name":\s*"factiz-([0-9a-z-]+)"', config or "")
    return m.group(1) if m else None


def kies(bestand: Path, n: int, rng: random.Random) -> list[str]:
    """`n` willekeurige factchecks uit de uitgave: elke keer andere, zodat ze niet uit de cache komen."""
    with sqlite3.connect(f"file:{bestand}?mode=ro", uri=True) as c:
        nummers = [r[0] for r in c.execute("SELECT nummer FROM pagina")]
    return rng.sample(nummers, min(n, len(nummers)))


def adressen(nummers: list[str], rng: random.Random) -> list[str]:
    """De vaste pagina's, robots.txt, en per factcheck de pagina en het deelplaatje, in een willekeurige sitetaal."""
    uit = [*VAST, "/robots.txt"]
    for nummer in nummers:
        taal = rng.choice(i18n.TALEN)
        uit += [i18n.pad(taal, "fact-checks", nummer), f"/deelbeeld/{taal}/{nummer}.jpg"]
    return uit


def robots_klopt(robots: str, stand: int) -> str | None:
    """Of robots.txt past bij de stand: dicht in stand 0, open met de sitemap in een open stand."""
    regels = robots.splitlines()
    if not stand and "Disallow: /" not in regels:
        return "robots.txt staat open, maar de stand is 0"
    if stand and ("Disallow: /" in regels or f"Sitemap: {SITE}/sitemap.xml" not in regels):
        return f"robots.txt past niet bij stand {stand}"
    return None


def storingen(rijen: list[tuple]) -> dict[str, int]:
    """Per dag het aantal storingen uit de tellingen (dag, wat, taal, n)."""
    uit: dict[str, int] = {}
    for dag, wat, _, n in rijen:
        if wat == "storing":
            uit[dag] = uit.get(dag, 0) + n
    return dict(sorted(uit.items()))


def _haal(pad: str) -> tuple[int, float, str]:  # pragma: no cover - het net
    begin = time.monotonic()
    verzoek = urllib.request.Request(SITE + pad, headers={"User-Agent": AFZENDER})
    try:
        with urllib.request.urlopen(verzoek, timeout=45) as r:
            lijf = r.read()
            return r.status, time.monotonic() - begin, lijf.decode("utf-8", "replace") if pad == "/robots.txt" else ""
    except urllib.error.HTTPError as fout:
        return fout.code, time.monotonic() - begin, ""
    except Exception as fout:                      # een afgebroken verbinding, een time-out
        return 0, time.monotonic() - begin, type(fout).__name__


def nakijken(paden: list[str], stand: int, rijen: list[tuple] | None, vorige: dict | None, haal=_haal) -> dict:
    """Eén ronde: elk adres goed en op tijd, robots.txt bij de stand, en geen nieuwe storing sinds de vorige ronde."""
    with ThreadPoolExecutor(4) as pool:
        antwoorden = dict(zip(paden, pool.map(haal, paden)))
    problemen = []
    for pad, (status, duur, _) in antwoorden.items():
        if status != 200:
            problemen.append(f"{pad} gaf {status or 'geen antwoord'}")
        elif duur > TRAAG:
            problemen.append(f"{pad} duurde {duur:.0f} s")
    robots = antwoorden.get("/robots.txt")
    if robots and robots[0] == 200:
        fout = robots_klopt(robots[2], stand)
        if fout:
            problemen.append(fout)
    per_dag = storingen(rijen) if rijen is not None else None
    if per_dag is not None:
        dag = datetime.now(timezone.utc).date().isoformat()
        eerder = ((vorige or {}).get("storingen") or {}).get(dag, 0)
        if per_dag.get(dag, 0) > eerder:
            problemen.append(f"{per_dag[dag] - eerder} nieuwe storing(en) vandaag, {per_dag[dag]} samen")
    tijden = sorted(d for _, d, _ in antwoorden.values())
    return {"tijd": datetime.now(timezone.utc).isoformat(timespec="seconds"), "goed": not problemen,
            "problemen": problemen, "gevraagd": len(paden), "stand": stand,
            "mediaan_s": round(tijden[len(tijden) // 2], 2) if tijden else None, "storingen": per_dag}


def _vorige() -> dict | None:
    if not LOG.exists():
        return None
    regels = LOG.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(regels[-1]) if regels else None


def _melding(tekst: str) -> None:  # pragma: no cover - alleen op een Mac
    if sys.platform == "darwin":
        script = f"display notification {json.dumps(tekst[:200])} with title \"factiz.org\""
        subprocess.run(["osascript", "-e", script], check=False)


def main() -> None:  # pragma: no cover - CLI
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 12
    config = CONFIG.read_text(encoding="utf-8")
    rng = random.Random()
    release = uitgave_uit(config)
    bestand = PUBLICATIE / release / "publicatie.db" if release else None
    nummers = kies(bestand, n, rng) if bestand and bestand.exists() else []
    rijen, d1_fout = None, None
    if "--zonder-d1" not in sys.argv:
        try:
            rijen = tellen.rijen_d1(TELLINGEN, dagen=2)
        except SystemExit as fout:          # wrangler niet aangemeld of geen net: de pagina's toch nakijken
            d1_fout = str(fout)[:200]
    uit = nakijken(adressen(nummers, rng), stand_uit(config), rijen, _vorige())
    if not nummers:
        uit["opmerking"] = f"geen uitgave {release} op deze Mac: alleen de vaste pagina's nagekeken"
    if d1_fout:
        uit["problemen"].append(f"de storingen in D1 niet gelezen: {d1_fout}")
        uit["goed"] = False
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(uit, ensure_ascii=False) + "\n")
    print(("goed" if uit["goed"] else "PROBLEEM") + f": {uit['gevraagd']} adressen, mediaan {uit['mediaan_s']} s, "
          f"storingen {uit['storingen']}" + "".join(f"\n- {p}" for p in uit["problemen"]))
    if not uit["goed"] and "--melding" in sys.argv:
        _melding("; ".join(uit["problemen"]))
    sys.exit(0 if uit["goed"] else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
