"""De vooruitblik (PLAN #28.6 d): een release bevroren, gescoord op checks
die er nog niet waren toen hij uitkwam.

Wat na de bevriezing in de feed verschijnt, kon niemand gebruiken om af te
stellen. `bevriezen` legt per release vast wat er die dag was: het moment,
de commit, de motor (`feitenbasis.motor_van`) en de index (aantal claims en
een hash over hun id's), in `docs/releases/bevroren.json`, in git, zodat
niemand de dag achteraf verschuift. `ophalen` haalt de ClaimReview-feed
binnen (wekelijks via launchd, RUNBOOK) en bewaart alleen een nieuwe stand,
de twee jongste (de stand is het jongste element, niet `dateModified`). `tellen` zegt per bevroren release hoeveel checks van na
die dag de feed al heeft, en hoeveel daarvan een post opnieuw checken die
toen al gecheckt was: de verse positieven, gekoppeld door redacties zelf
(#25.13). Alleen tellingen: de set blijft dicht tot hij gemeten wordt.

    python -m doublecheck.vooruitblik bevriezen --release <naam>
    python -m doublecheck.vooruitblik ophalen [--bijwerken]
    python -m doublecheck.vooruitblik tellen
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
BEVROREN = WORTEL / "docs" / "releases" / "bevroren.json"
FEEDMAP = WORTEL / "data" / "vooruitblik" / "feed"
LOG = WORTEL / "data" / "vooruitblik" / "ophalen.log"
HOUD = 2


TOELICHTING = ("Bevroren releases (PLAN #28.6 d): per release het moment, de commit, de motor en de index "
               "(aantal claims en een hash over hun id's), geschreven door `python -m doublecheck.vooruitblik "
               "bevriezen`. Eigen meetgegevens, geen corpustekst. Een release wordt één keer bevroren.")


class AlBevroren(Exception):
    """Een release is één keer bevroren; een tweede moment zou de dag verschuiven."""


def index_vingerafdruk(claim_ids) -> str:
    return hashlib.sha256("\n".join(sorted(claim_ids)).encode("utf-8")).hexdigest()[:16]


def bevries(pad: Path, record: dict) -> None:
    data = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {"toelichting": TOELICHTING,
                                                                             "bevroren": []}
    if any(r["release"] == record["release"] for r in data["bevroren"]):
        raise AlBevroren(f"{record['release']} is al bevroren")
    data["bevroren"].append(record)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def feedstand(pad: Path) -> str:
    """De stand van een feed: het jongste `dateCreated` van zijn elementen,
    als `YYYY-MM-DDTHHMMSS`. `dateModified` zegt niets, want de feed zet daar
    het moment van ophalen in."""
    data = json.loads(Path(pad).read_text(encoding="utf-8"))
    jongste = max((str(e.get("dateCreated") or "") for e in data.get("dataFeedElement", []) if isinstance(e, dict)),
                  default="")
    if not jongste:
        raise ValueError(f"{pad}: geen element met dateCreated")
    return jongste[:10] + "T" + jongste[11:19].replace(":", "")


def bewaar(nieuw: Path, map_: Path, houd: int = HOUD) -> Path | None:
    """Zet een download op zijn plek als zijn stand nieuw is, anders weg ermee.
    Van de standen blijven de jongste `houd`."""
    doel = map_ / f"feed-{feedstand(nieuw)}.json"
    if doel.exists():
        nieuw.unlink()
        return None
    map_.mkdir(parents=True, exist_ok=True)
    nieuw.replace(doel)
    for oud in sorted(map_.glob("feed-*.json"))[:-houd]:
        oud.unlink()
    return doel


def _checks(elementen):
    """(url, datum, claimtekst, posts) per check in de feed; datum alleen als
    hij te vertrouwen is."""
    from doublecheck.datums import geldige_review_datum
    from doublecheck.natuurlijk import post_sleutel

    for rec in elementen:
        item = (rec or {}).get("item") if isinstance(rec, dict) else None
        if isinstance(item, list):
            item = item[0] if item and isinstance(item[0], dict) else None
        if not isinstance(item, dict) or not item.get("url"):
            continue
        verschijningen = (item.get("itemReviewed") or {}).get("appearance") or []
        if isinstance(verschijningen, dict):
            verschijningen = [verschijningen]
        posts = set()
        for v in verschijningen if isinstance(verschijningen, list) else []:
            u = v.get("url") if isinstance(v, dict) else (v if isinstance(v, str) else None)
            if u and (p := post_sleutel(u)):
                posts.add(p)
        yield item["url"], geldige_review_datum(item.get("datePublished") or ""), item.get("claimReviewed"), posts


def nieuwe_checks(elementen, sinds: str) -> int:
    return sum(1 for _, dag, _, _ in _checks(elementen) if dag and dag > sinds)


def verse_positieven(elementen, geheugen: dict[str, str], sinds: str) -> list[dict]:
    """De checks van na `sinds` van een post die een check uit het geheugen
    van die dag al had (`geheugen`: check-url naar claim). De doelen zijn de
    claims van die eerdere checks."""
    lijst = list(_checks(elementen))
    per_post: dict[str, set[str]] = {}
    for url, _, _, posts in lijst:
        if url in geheugen:
            for post in posts:
                per_post.setdefault(post, set()).add(geheugen[url])
    uit = []
    for url, dag, claim, posts in lijst:
        if not dag or dag <= sinds or url in geheugen:
            continue
        doelen = set().union(*(per_post.get(p, set()) for p in posts)) if posts else set()
        if doelen:
            uit.append({"url": url, "dag": dag, "claim": claim, "doelen": doelen})
    return sorted(uit, key=lambda v: v["url"])


def _geheugen(conn, dag: str) -> dict[str, str]:  # pragma: no cover - op de productiedatabase
    """Check-url naar claim, voor de toegelaten checks met een datum strikt
    vóór `dag` en een claim in de index: het geheugen van die dag."""
    from doublecheck.datums import geldige_review_datum
    from doublecheck.evidence import _host
    from doublecheck.toelating import buiten_index, register, staat_aan

    buiten, aan, hosts = buiten_index(conn), staat_aan(conn), register()
    uit = {}
    for url, claim, datum in conn.execute("SELECT url, claim_id, review_date FROM factcheck"):
        geldig = geldige_review_datum(datum or "")
        if geldig and geldig < dag and claim not in buiten and (not aan or (_host(url) or "") in hosts):
            uit[url] = claim
    return uit


ETAG = WORTEL / "data" / "vooruitblik" / "etag.json"


def nieuwe_versie(etag: str | None, pad: Path = ETAG) -> bool:
    """Is de feed veranderd sinds de vorige keer? Zonder kenmerk toch ophalen (twijfel versoepelt nooit)."""
    if not etag or not pad.exists():
        return True
    return json.loads(pad.read_text(encoding="utf-8")).get("etag") != etag


def onthoud_versie(etag: str | None, pad: Path = ETAG) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps({"etag": etag, "gezien": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                   encoding="utf-8")


def bijwerkopdracht(feed: Path, log: Path) -> tuple[list[str], dict[str, str]]:
    """De database bijwerken uit een nieuwe stand (de versheidscadans, PLAN #32.7b): de bouwer met het NLI-veto,
    achter de hittewacht en op hoogstens twee kernen."""
    import os
    import sys

    opdracht = [sys.executable, "-m", "doublecheck.hittewacht", "--log", str(log), "--",
                sys.executable, "-m", "doublecheck.bootstrap", "--cache", str(feed), "--met-veto"]
    return opdracht, {**os.environ, "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"}


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import os
    import sqlite3
    import subprocess

    parser = argparse.ArgumentParser(description="De vooruitblik (#28.6 d)")
    sub = parser.add_subparsers(dest="stap", required=True)
    b = sub.add_parser("bevriezen", help="leg vast wat er vandaag is, voor één release")
    b.add_argument("--release", required=True)
    o = sub.add_parser("ophalen", help="haal de ClaimReview-feed binnen als hij een nieuwe stand heeft")
    o.add_argument("--bijwerken", action="store_true", help="werk daarna de database bij uit een nieuwe stand (#32.7b)")
    sub.add_parser("tellen", help="hoeveel verse positieven er per bevroren release zijn")
    args = parser.parse_args()
    bron = os.environ.get("DOUBLECHECK_DB", str(WORTEL / "doublecheck.db"))

    if args.stap == "bevriezen":
        from doublecheck.api import _in_index
        from doublecheck.config import load_config
        from doublecheck.feitenbasis import motor_van

        conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
        ids = [c for c, _ in _in_index(conn)]
        laatste = conn.execute("SELECT max(review_date) FROM factcheck WHERE review_date <= date('now')").fetchone()[0]
        commit = subprocess.run(["git", "-C", str(WORTEL), "rev-parse", "HEAD"], capture_output=True,
                                text=True).stdout.strip()
        record = {"release": args.release, "moment": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "commit": commit, "motor": motor_van(load_config()), "claims_in_index": len(ids),
                  "index": index_vingerafdruk(ids), "jongste_check": laatste}
        bevries(BEVROREN, record)
        print(f"bevroren: {args.release} op {record['moment']}, {len(ids):,} claims, index {record['index']}")
    elif args.stap == "ophalen":
        from doublecheck.bootstrap import FEED_URL, download_bestand

        import urllib.request

        FEEDMAP.mkdir(parents=True, exist_ok=True)
        nu = datetime.now(timezone.utc).isoformat(timespec="seconds")
        etag = urllib.request.urlopen(urllib.request.Request(FEED_URL, method="HEAD"), timeout=60).headers.get("ETag")
        if not nieuwe_versie(etag):
            regel, doel = f"{nu} geen nieuwe versie (etag)", None
        else:
            tijdelijk = download_bestand(FEED_URL, FEEDMAP / "download.json")
            doel = bewaar(tijdelijk, FEEDMAP)
            onthoud_versie(etag)
            regel = f"{nu} " + (f"nieuwe stand {doel.name}" if doel else "geen nieuwe stand")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(regel + "\n")
        print(regel)
        if doel and args.bijwerken:
            opdracht, omgeving = bijwerkopdracht(doel, LOG.parent / "hittewacht.log")
            with (LOG.parent / "bijwerken.log").open("a", encoding="utf-8") as uit:
                code = subprocess.run(opdracht, cwd=WORTEL, env=omgeving, stdout=uit, stderr=subprocess.STDOUT).returncode
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} database bijgewerkt uit "
                        f"{doel.name}: uitgang {code}\n")
    else:
        standen = sorted(FEEDMAP.glob("feed-*.json"))
        if not standen:
            raise SystemExit("nog geen feed opgehaald: python -m doublecheck.vooruitblik ophalen")
        data = json.loads(standen[-1].read_text(encoding="utf-8"))
        elementen = data.get("dataFeedElement", [])
        conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
        for record in json.loads(BEVROREN.read_text(encoding="utf-8"))["bevroren"]:
            dag = record["moment"][:10]
            vers = verse_positieven(elementen, _geheugen(conn, dag), dag)
            print(f"{record['release']} (bevroren {dag}), feed van {standen[-1].stem[5:]}: "
                  f"{nieuwe_checks(elementen, dag)} checks van na die dag, {len(vers)} verse positieven")


if __name__ == "__main__":
    main()
