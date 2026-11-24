"""Community Notes als signaal en brug (#25.15, B25 laag 2).

De dagelijkse export van X (x.com/i/communitynotes/download-data) is geen
corpus voor ons: de ruwe data valt onder de X Developer Agreement and Policy
en wordt niet doorgegeven, en de posttekst zit er niet in (alleen het
post-ID). Wel een signaal: een note wordt pas "behulpzaam" als deelnemers die
het normaal oneens zijn het er samen over eens zijn. En een brug: een
behulpzame note die naar een check in ons corpus linkt, verbindt een echte
virale post met onze claim.

Gelezen rechtstreeks uit de zips; niets wordt uitgepakt of bewaard.

Sinds #25.16 wordt elke brug een regel in de geschiedenis van de bewering
(PO 2026-10-12): een attributie van niveau `waargenomen` op platform X, met
de datum van de note en een link naar de note. Nooit de notetekst; de bron
staat als niet herverdeelbaar in het register, dus `--herkomst` meldt een
database met deze regels als niet uitgeefbaar (E7.S6).
"""

from __future__ import annotations

import collections
import csv
import io
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_URL = re.compile(r"https?://[^\s\"'<>]+")


def host_en_pad(url: str) -> tuple[str, str]:
    try:
        s = urlsplit(url.strip().rstrip(".,);]"))
    except ValueError:
        return "", ""
    return re.sub(r"^www\.", "", (s.hostname or "").lower()), s.path.rstrip("/").lower()


def _rijen(map_: Path, naam: str):
    csv.field_size_limit(sys.maxsize)
    with zipfile.ZipFile(Path(map_) / f"{naam}.zip") as z, z.open(f"{naam}.tsv") as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")


def meet(conn, map_: Path, *, factcheck_hosts: set[str]) -> dict:
    behulpzaam: dict[str, int] = {}
    for r in _rijen(map_, "noteStatusHistory-00000"):
        if r.get("currentStatus") == "CURRENTLY_RATED_HELPFUL":
            behulpzaam[r["noteId"]] = int(r.get("timestampMillisOfCurrentStatus") or 0)

    checks = {}
    for url, claim_id in conn.execute("SELECT url, claim_id FROM factcheck"):
        h, p = host_en_pad(url)
        checks[h + p] = claim_id

    gelezen = met_domein = 0
    per_week: collections.Counter = collections.Counter()
    soort: collections.Counter = collections.Counter()
    bruggen: list[tuple[str, str, str]] = []
    brugdatum: dict[str, int] = {}
    for pad in sorted(Path(map_).glob("notes-*.zip")):
        for r in _rijen(map_, pad.stem):
            moment = behulpzaam.get(r["noteId"])
            if moment is None:
                continue
            gelezen += 1
            soort[r.get("classification", "")] += 1
            per_week[datetime.fromtimestamp(moment / 1000, tz=timezone.utc).strftime("%G-W%V")] += 1
            paren = [host_en_pad(u) for u in _URL.findall(r.get("summary", ""))]
            if {h for h, _ in paren} & factcheck_hosts:
                met_domein += 1
            for h, p in paren:
                if h + p in checks:
                    bruggen.append((r["noteId"], r["tweetId"], checks[h + p]))
                    # Wanneer de note geschreven werd: zo dicht als de export
                    # komt bij wanneer de post rondging.
                    brugdatum[r["noteId"]] = int(r.get("createdAtMillis") or 0) or moment
                    break
    return {
        "behulpzaam": len(behulpzaam),
        "gelezen": gelezen,
        "soort": dict(soort),
        "met_factcheckdomein": met_domein,
        "bruggen": bruggen,
        "brugdatum": brugdatum,
        "per_week": dict(per_week),
    }


BRON = dict(
    bron_id="communitynotes",
    naam="Community Notes (X)",
    soort="platform",
    licentie="X Developer Agreement and Policy; niet herverdeelbaar",
    attributietekst="Community Notes, behulpzaam bevonden door deelnemers met verschillende standpunten",
    url="https://communitynotes.x.com",
    herverdeelbaar=False,
)


def importeer(conn, map_: Path, *, factcheck_hosts: set[str]) -> int:
    """Elke brug als attributie (E7.S6): actor X, bron Community Notes, de
    datum van de note en een link naar de note. Herhaalbaar; geeft het
    aantal nieuwe regels."""
    from doublecheck import attributie as at

    r = meet(conn, map_, factcheck_hosts=factcheck_hosts)
    at.registreer_bron(conn, **BRON)
    x = at.registreer_actor(conn, naam="X", soort="platform")
    nieuw = 0
    for note, post, claim_id in r["bruggen"]:
        moment = r["brugdatum"].get(note)
        if not moment:
            continue
        nieuw += at.voeg_attributie(
            conn, claim_id=claim_id, actor_id=x, bron_id=BRON["bron_id"],
            datum=datetime.fromtimestamp(moment / 1000, tz=timezone.utc).date().isoformat(),
            url=f"https://x.com/i/birdwatch/n/{note}", niveau="waargenomen",
            grond=f"behulpzame Community Note bij https://x.com/i/status/{post}",
        )
    return nieuw


def main() -> None:
    import argparse
    import json
    import os

    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Community Notes meten als signaal en brug (#25.15)")
    parser.add_argument("--map", default="data/communitynotes")
    parser.add_argument("--importeer", action="store_true",
                        help="de bruggen als attributies in de database zetten (#25.16)")
    args = parser.parse_args()
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    hosts = {h.lower() for h in json.load(open("doublecheck/uitgevers.json", encoding="utf-8"))["hosts"]}
    if args.importeer:
        from doublecheck.storage import init_schema

        init_schema(conn)   # de actorsoort `platform` in een oudere database (#25.16)
        print(f"nieuwe regels in de geschiedenis: {importeer(conn, Path(args.map), factcheck_hosts=hosts):,}")
        return
    r = meet(conn, Path(args.map), factcheck_hosts=hosts)
    n = r["gelezen"] or 1
    print(f"behulpzaam nu: {r['behulpzaam']:,} · gelezen in de notesbestanden: {r['gelezen']:,} · {r['soort']}")
    print(f"linkt naar een factcheckdomein uit het register: {r['met_factcheckdomein']:,} ({r['met_factcheckdomein'] / n:.1%})")
    print(f"brug naar een check in ons corpus: {len(r['bruggen']):,} notes · "
          f"{len({c for *_, c in r['bruggen']}):,} claims · {len({t for _, t, _ in r['bruggen']}):,} posts")
    print("behulpzaam geworden per week (laatste 12):",
          ", ".join(f"{w[-3:]}:{c}" for w, c in sorted(r["per_week"].items())[-12:]))


if __name__ == "__main__":
    main()
