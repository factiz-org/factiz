"""De proef van ronde 2 (PLAN #31.12): 20 vragen rechtstreeks, zonder
batchkorting, door de echte functies van de controle per bericht
(`berichtcontrole.voorbereiden` en `berichtcontrole.beoordeel`), op openbare
zinnen uit ronde 1, de helft waar en de helft vals.

Gemeten wordt of het vaste deel onthouden wordt (de tokens die uit de cache
gelezen worden), wat een bericht kost, hoe lang het duurt, en of het oordeel
gelijk is aan dat van ronde 1. De vragen gaan na elkaar, zodat de cache warm
blijft zoals bij doorlopend verkeer. Geen gebruikersberichten: de schakelaar
blijft uit, en alleen het id van de zin wordt bewaard.

    python -m doublecheck.hittewacht -- python -m doublecheck.controleproef [--n 20]
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "berichtcontrole"
BUDGET = 1.5  # PLAN Koers: ronde 2 ~$1,50
ZAAD = 3112
SCHATTING = 0.06  # per bericht zonder batchkorting, ruim (§156: ~$0,048 met zoeken)


def kies(stukken: list[dict], n: int) -> list[dict]:
    """De helft ware en de helft valse zinnen, willekeurig met een vast zaad."""
    uit = []
    for label in ("waar", "onwaar"):
        groep = sorted((s for s in stukken if s["label"] == label), key=lambda s: s["id"])
        uit += random.Random(f"{ZAAD}-{label}").sample(groep, n // 2)
    return uit


def samenvatting(rijen: list[dict]) -> dict:
    from doublecheck.routemeting import p95

    n = len(rijen)
    return {"n": n, "uit de cache gelezen": sum(r["gebruik"]["cache_lees"] > 0 for r in rijen),
            "in de cache gezet": sum(r["gebruik"]["cache_schrijf"] > 0 for r in rijen),
            "kosten samen": round(sum(r["kosten"] for r in rijen), 4),
            "kosten per bericht": round(sum(r["kosten"] for r in rijen) / n, 4) if n else None,
            "p95 route (s)": round(p95([r["lokaal"] + r["model"] for r in rijen]), 2) if n else None,
            "gelijk aan ronde 1": sum(r["oordeel"] == r["ronde1"] for r in rijen),
            "herkansingen": sum(bool(r.get("herkansing")) for r in rijen)}


def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in pad.read_text(encoding="utf-8").splitlines() if x.strip()] if pad.exists() else []


def main() -> None:  # pragma: no cover - met het model en de database
    import argparse

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck import fundament
    from doublecheck.config import load_config
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="De proef van de controle per bericht (PLAN #31.12)")
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()
    laad_sleutel()
    client = anthropic.Anthropic()
    config = load_config()
    conn = connect("doublecheck.db")
    kosten = bc.kostenverbinding(config)
    stukken = fundament._jsonl(fundament.UIT / "set.jsonl")
    ronde1 = {r["id"]: r["oordeel"] for r in fundament._jsonl(fundament.UIT / "antwoorden.jsonl")}
    tabel, zinnen = bc.ijktabel(config), bc.feitzinnen()
    pad = UIT / "proef.jsonl"
    pad.parent.mkdir(parents=True, exist_ok=True)
    gedaan = {r["id"] for r in _jsonl(pad)}
    for s in kies([x for x in stukken if x["id"] in ronde1], args.n):
        if s["id"] in gedaan:
            continue
        uitgegeven = sum(r["kosten"] for r in _jsonl(pad))
        if uitgegeven + SCHATTING > BUDGET:
            print(f"gestopt: ${uitgegeven:.2f} plus ${SCHATTING:.2f} is meer dan ${BUDGET:.2f}")
            break
        begin = time.perf_counter()
        voorbereid = bc.voorbereiden(conn, config, s["tekst"])
        lokaal = time.perf_counter() - begin
        begin = time.perf_counter()
        uit = bc.beoordeel(kosten, voorbereid, client, config, None, tabel, zinnen, dag="proef-31.12")
        model = time.perf_counter() - begin
        rij = {"id": s["id"], "label": s["label"], "oordeel": uit["oordeel"], "ronde1": ronde1[s["id"]],
               "stand": uit["stand"]["stand"], "herkansing": uit["herkansing"], "kosten": round(uit["kosten"], 5),
               "gebruik": uit["gebruik"], "lokaal": round(lokaal, 3), "model": round(model, 3)}
        with pad.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
        print(f"{s['id']}: {uit['oordeel']} (ronde 1: {rij['ronde1']}), cache {uit['gebruik']['cache_lees']}, "
              f"${uit['kosten']:.4f}, {lokaal + model:.1f} s", flush=True)
    print(json.dumps(samenvatting(_jsonl(pad)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
