"""Het snelle antwoord, gemeten (PLAN #32.0o).

Wat kan Factiz zeggen zonder taalmodel, binnen een seconde of twee? Het echte
`POST /resolve` zoekt in de checks van de database (en in de vastgestelde feiten
waar die laag aan staat). Is de categorie *matched* en wijzen de checks één kant op,
dan is dat het snelle antwoord; anders gaat het bericht door naar de verdieping,
de controle met het taalmodel.

Op de 3.005 berichten van de rondes met vraag v4 (met label) en de 250 echte
tiplineberichten van ronde 6 (zonder label). Lokaal, zonder kosten.

    python -m doublecheck.hittewacht -- python -m doublecheck.snelantwoord meten|tipline|ocr
    python -m doublecheck.snelantwoord lezen|tellen
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from doublecheck import betatoets as bt
from doublecheck.berichtcontrole import ONWAAR, snel_oordeel  # noqa: F401 - verhuisd naar de controle (#32.7a)

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "snelantwoord"
LABELS = WORTEL / "docs" / "steekproeven" / "32.0o-snelantwoord.json"


class Weigering(RuntimeError):
    pass


def uitkomst(label: str, snel: str | None) -> str:
    if snel is None:
        return "verder"
    return "goed" if (snel == "onwaar") == (label in ONWAAR) else "fout"


def percentiel(waarden: list[float], q: float) -> float:
    """Het kleinste getal met minstens een aandeel q van de waarden op of eronder."""
    rij = sorted(waarden)
    return rij[max(0, math.ceil(q * len(rij)) - 1)]


def telling(rijen: list[dict], labels: dict[str, str]) -> dict:
    """Per groep hoeveel er snel beantwoord werd, en goed of fout; elke snelle fout bij een waar bericht moet
    gelezen zijn (`vals`, of `set fout` als het label van de set niet klopte)."""
    groepen: dict[str, dict] = {}
    fout_waar = 0
    for r in rijen:
        u = uitkomst(r["label"], r["snel"])
        for g in (r["groep"], "alles"):
            d = groepen.setdefault(g, {"n": 0, "snel": 0, "goed": 0, "fout": 0, "verder": 0})
            d["n"] += 1
            d["snel"] += r["snel"] is not None
            d[u] += 1
        if u == "fout" and r["label"] == "waar":
            if r["id"] not in labels:
                raise Weigering(f"{r['id']}: snel onwaar bij een waar bericht, zonder label in {LABELS.name}")
            fout_waar += labels[r["id"]] == "vals"
    tijden = [r["seconden"] for r in rijen]
    alles = groepen.pop("alles", {})
    return {"alles": alles, "groepen": groepen, "fout bij een waar bericht": fout_waar,
            "tijd": {"p50": percentiel(tijden, 0.5), "p95": percentiel(tijden, 0.95)} if tijden else {}}


# --- meten en de CLI -----------------------------------------------------------------------------

def _resolver():  # pragma: no cover - met het model en de database
    from fastapi.testclient import TestClient

    from doublecheck import api

    api.limiter.enabled = False
    client = TestClient(api.app)
    client.post("/resolve", json={"text": "warm up the model"}).raise_for_status()  # het model laden telt niet mee
    return client


def _vraag(client, tekst: str) -> tuple[dict, float]:  # pragma: no cover - met de resolver
    begin = time.perf_counter()
    antwoord = client.post("/resolve", json={"text": tekst})
    antwoord.raise_for_status()
    return antwoord.json(), time.perf_counter() - begin


def _rij(r: dict, d: dict, sec: float) -> dict:
    return {**r, "categorie": d["category"], "snel": snel_oordeel(d), "seconden": round(sec, 4),
            "checks": [c["verdict_normalized"] for c in (d.get("evidence") or {}).get("checks", [])],
            "claim": (d.get("claim") or {}).get("id")}


def main() -> None:  # pragma: no cover - CLI
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(description="Het snelle antwoord, gemeten (PLAN #32.0o)")
    parser.add_argument("stap", choices=("meten", "tipline", "ocr", "lezen", "tellen"))
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "meten":
        from doublecheck import vloer as vl

        rijen, _ = vl.rondes(alle=True)
        pad = UIT / "rondes.jsonl"
        klaar = {r["id"] for r in bt._jsonl(pad)}
        client = _resolver()
        with pad.open("a", encoding="utf-8") as fh:
            for i, r in enumerate(rijen):
                if r["id"] in klaar:
                    continue
                d, sec = _vraag(client, r["tekst"])
                groep = f"{r['bron'].split(':')[0]} · {r['label']}"
                fh.write(json.dumps(_rij({"id": r["id"], "groep": groep, "label": r["label"]}, d, sec),
                                    ensure_ascii=False) + "\n")
                if i % 100 == 0:
                    fh.flush()
                    print(f"\r{i + 1}/{len(rijen)}", end="", flush=True)
        print()
        return
    if args.stap == "tipline":
        from doublecheck import verificatie as v

        client = _resolver()
        uit = []
        for s in v.gekozen_stukken(6):
            d, sec = _vraag(client, s["tekst"])
            uit.append(_rij({"id": s["id"], "groep": f"tipline · {s['label']}", "label": s["label"]}, d, sec))
        bt._schrijf(UIT / "tipline.jsonl", uit)
        print(Counter((r["groep"], r["categorie"]) for r in uit))
        return
    if args.stap == "ocr":
        from doublecheck import berichtcontrole as bc
        from doublecheck.config import load_config

        config = load_config(None)
        client = _resolver()
        uit = []
        for s in bt._jsonl(WORTEL / "data" / "betatoets" / "set.jsonl"):
            if s["vorm"] != "screenshot" or not s.get("beeld"):
                continue
            data = Path(s["beeld"]).read_bytes()
            begin = time.perf_counter()
            tekst = bc.bericht_uit(None, data, config.ocr)
            ocr = time.perf_counter() - begin
            d, sec = _vraag(client, tekst) if tekst.strip() else ({"category": "none"}, 0.0)
            uit.append({**_rij({"id": s["id"], "groep": "screenshot · onwaar", "label": "onwaar"}, d, sec),
                        "ocr": round(ocr, 4), "samen": round(ocr + sec, 4)})
        bt._schrijf(UIT / "ocr.jsonl", uit)
        print(f"{len(uit)} screenshots; tekstherkenning en zoeken samen p50 {percentiel([r['samen'] for r in uit], .5):.2f} s, "
              f"p95 {percentiel([r['samen'] for r in uit], .95):.2f} s")
        return
    rijen = bt._jsonl(UIT / "rondes.jsonl")
    labels = json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {}) if LABELS.exists() else {}
    if args.stap == "lezen":
        tekst = {r["id"]: r["tekst"] for r in __import__("doublecheck.vloer", fromlist=["x"]).rondes(alle=True)[0]}
        for r in rijen:
            if uitkomst(r["label"], r["snel"]) == "fout" and r["id"] not in labels:
                print(f"=== {r['id']} [{r['label']}] snel {r['snel']} ({r['checks']}), claim {r['claim']}\n{tekst[r['id']][:400]}")
        return
    uit = {"rondes": telling(rijen, labels)}
    tip = bt._jsonl(UIT / "tipline.jsonl")
    if tip:
        uit["tipline"] = {g: {"n": sum(r["groep"] == g for r in tip), "snel": sum(r["groep"] == g and r["snel"] is not None
                                                                                 for r in tip),
                              "matched": sum(r["groep"] == g and r["categorie"] == "matched" for r in tip)}
                          for g in sorted({r["groep"] for r in tip})}
        uit["tipline"]["tijd"] = {"p50": percentiel([r["seconden"] for r in tip], .5),
                                  "p95": percentiel([r["seconden"] for r in tip], .95)}
    ocr = bt._jsonl(UIT / "ocr.jsonl")
    if ocr:
        uit["screenshots"] = {"n": len(ocr), "snel goed": sum(r["snel"] == "onwaar" for r in ocr),
                              "ocr p50": percentiel([r["ocr"] for r in ocr], .5),
                              "samen p50": percentiel([r["samen"] for r in ocr], .5),
                              "samen p95": percentiel([r["samen"] for r in ocr], .95)}
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
