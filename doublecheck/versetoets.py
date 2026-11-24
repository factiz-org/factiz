"""Een nieuwe lezer met vier punten, gemeten op verse berichten (PLAN #32.12).

`lezer-v3` door dezelfde functies als `/check`, eerst op de 15 gelezen gevallen van §181 (de ontwikkelcheck, geen
toets), daarna op berichten die nooit in een set zaten:
- O': 100 Engelse claims met een onware of misleidende factcheck sinds 1 juli 2026; kring 1 uit en de resultaten van
  IFCN-factcheckers weggelaten, zoals O in #32.11;
- W': 50 ware berichten uit Portal:Current events van 1 tot en met 19 oktober 2026; kring 1 aan, zoals W.
Elk groen bij O' en elk rood of oranje bij W' wordt gelezen (`docs/steekproeven/32.12-versetoets.json`).

    python -m doublecheck.versetoets set
    python -m doublecheck.hittewacht -- python -m doublecheck.versetoets ontwikkel|draaien
    python -m doublecheck.versetoets lezen|tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from doublecheck import controle500 as c5

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "versetoets"
LABELS = WORTEL / "docs" / "steekproeven" / "32.12-versetoets.json"
BUDGET = 2.0  # PO 2026-10-29: "binnen ~$2"; Sonnet en Brave samen, Brave tegen de lijstprijs
LEZER = "lezer-v3"
ZAAD = 3212
N_ONWAAR, N_WAAR = 100, 50
VANAF = "2026-07-01"
DAGEN = range(1, 20)  # de eindtoets nam 20 tot 28 oktober
Weigering = c5.Weigering


def ongezien(rijen: list[tuple], gezien: set[str]) -> list[dict]:
    """De claims voor O': nooit in een set, en alleen onware of misleidende checks (een claim met ook een ware check
    is geen nepbericht). `rijen`: (claim, tekst, oordelen met komma's, laatste datum, redactie)."""
    return [{"id": f"O:{c}", "deel": "O", "tekst": t.strip(), "claim": c, "label": "onwaar", "oordeel": o,
             "datum": d, "redactie": p}
            for c, t, o, d, p in rijen if c not in gezien and set(o.split(",")) <= {"onwaar", "misleidend"}]


def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict[str, str],
            bestand: str = LABELS.name) -> dict:
    """De telling van #32.11 op W' en O', met per deel hoe vaak de lezer `over_beeld` zei en hoeveel groen er zonder
    de beeldregel was geweest, op dezelfde lezing."""
    uit = c5.telling(stukken, antwoorden, labels, bestand=bestand)
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        d = uit[s["deel"]]
        d["over_beeld"] = d.get("over_beeld", 0) + bool(a.get("over_beeld"))
        d["groen zonder beeldregel"] = d.get("groen zonder beeldregel", 0) + (a.get("kleur_zonder_beeldregel") == "groen")
    return uit


def uitgegeven(map_: Path) -> float:
    """Wat alles in de map samen kostte (de ontwikkelcheck, de bijstelling en de toets); de grens geldt voor alles."""
    return sum(r.get("kosten", 0) for pad in sorted(map_.glob("*.jsonl")) for r in c5._jsonl(pad))


# --- de bestanden en de CLI ------------------------------------------------------------------------

def lees_labels() -> dict[str, str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r["label"] for r in d.get("oordelen", [])}


def _gezien() -> set[str]:  # pragma: no cover - op de sets van de eerdere rondes
    gezien: set[str] = set()
    for pad in WORTEL.glob("data/*/set.jsonl"):
        for r in c5._jsonl(pad):
            gezien |= {str(r[k]) for k in ("zaak", "claim", "claim_id") if r.get(k)}
            gezien |= set(r.get("verborgen") or [])
            if str(r.get("sleutel", "")).startswith("C:"):
                gezien.add(r["sleutel"][2:])
    return gezien


def _maak_set() -> list[dict]:  # pragma: no cover - netwerk en database
    import sqlite3

    from doublecheck.eindtoets import portal_zinnen
    from doublecheck.koppen import _wikitekst

    rng = random.Random(ZAAD)
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, group_concat(DISTINCT f.verdict_normalized), max(f.review_date), "
        "f.publisher FROM claim c JOIN factcheck f ON f.claim_id = c.claim_id WHERE f.language = 'en' "
        "AND f.review_date >= ? GROUP BY c.claim_id ORDER BY c.claim_id", (VANAF,)).fetchall()
    vrij = ongezien([tuple(r) for r in rijen], _gezien())
    onwaar = rng.sample(vrij, min(N_ONWAAR, len(vrij)))
    zinnen = [(dag, z) for dag in DAGEN for z in portal_zinnen(_wikitekst(f"Portal:Current events/2026 October {dag}"))
              if 60 <= len(z) <= 300]
    waar = [{"id": f"W:{dag}-{i}", "deel": "W", "tekst": z, "label": "waar", "datum": f"2026-10-{dag:02d}"}
            for i, (dag, z) in enumerate(rng.sample(zinnen, N_WAAR))]
    uit = waar + onwaar
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "set.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    print(f"{len(vrij)} ongeziene onware claims, {len(onwaar)} gekozen; {len(zinnen)} ware zinnen, {len(waar)} gekozen")
    return uit


def _ontwikkelstukken() -> list[dict]:  # pragma: no cover - op de set van ronde 4
    labels = c5.lees_labels()
    return [s for s in c5.stukken() if s["id"] in labels]


def _draai(stukken: list[dict], pad: Path) -> None:  # pragma: no cover - live
    import dataclasses
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, lezer=LEZER))
    client, sleutel = anthropic.Anthropic(), os.environ["BRAVE_API_KEY"]
    tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
    gedaan = {r["id"] for r in c5._jsonl(pad)}
    slot, lokaal = threading.Lock(), threading.local()

    def doe(s: dict) -> None:
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        with slot:
            if uitgegeven(UIT) > BUDGET:
                return
        rij = c5._een(s, lokaal.conn, config, client, sleutel, tabel, sites)
        with slot:
            with pad.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            print(f"{s['id']} [{s['deel']}]: {rij['oordeel']} ({rij['kleur']}), {rij['seconden']} s", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(doe, [s for s in stukken if s["id"] not in gedaan]))


def _toon_ontwikkel() -> None:  # pragma: no cover - CLI
    oud = {r["id"]: r for r in c5._jsonl(c5.UIT / "antwoorden.jsonl")}
    labels = c5.lees_labels()
    tel = Counter()
    for r in c5._jsonl(UIT / "ontwikkel.jsonl"):
        o = oud[r["id"]]
        tel[(labels[r["id"]], o["kleur"], r["kleur"])] += 1
        print(f"{r['id']} [{labels[r['id']]}] v2: {o['oordeel']} ({o['kleur']}) -> v3: {r['oordeel']} ({r['kleur']}), "
              f"over_beeld {r.get('over_beeld')}\n    {r.get('uitleg')}")
    print(dict(tel))


def main() -> None:  # pragma: no cover - CLI, live
    import argparse

    parser = argparse.ArgumentParser(description="Een nieuwe lezer op verse berichten (PLAN #32.12)")
    parser.add_argument("stap", choices=("set", "ontwikkel", "draaien", "lezen", "tellen"))
    parser.add_argument("--alleen", default="", help="ontwikkel: alleen deze ids, na de ene bijstelling van de vraag")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "set":
        _maak_set()
        return
    if args.stap == "ontwikkel" and args.alleen:
        ids = set(args.alleen.split(","))
        _draai([s for s in _ontwikkelstukken() if s["id"] in ids], UIT / "bijgesteld.jsonl")
        for r in c5._jsonl(UIT / "bijgesteld.jsonl"):
            print(f"{r['id']}: {r['oordeel']} ({r['kleur']}), over_beeld {r.get('over_beeld')}\n    {r.get('uitleg')}")
        return
    if args.stap == "ontwikkel":
        _draai(_ontwikkelstukken(), UIT / "ontwikkel.jsonl")
        _toon_ontwikkel()
        return
    # de onware eerst: raakt de grens het einde, dan mist een paar ware, nooit het deel waar de eis op ligt
    alle = sorted(c5._jsonl(UIT / "set.jsonl"), key=lambda s: s["deel"] != "O")
    pad = UIT / "antwoorden.jsonl"
    if args.stap == "draaien":
        _draai(alle, pad)
        print(f"samen ${uitgegeven(UIT):.2f}")
        return
    antwoorden = {r["id"]: r for r in c5._jsonl(pad)}
    labels = lees_labels()
    if args.stap == "lezen":
        for s in alle:
            a = antwoorden.get(s["id"])
            if a is None or s["id"] in labels:
                continue
            if (s["deel"] == "W" and a["kleur"] in c5.ALARM) or (s["deel"] == "O" and a["kleur"] == "groen"):
                bronnen = [(r["site"], r["band"]) for r in a.get("resultaten", [])
                           if r["nr"] in a.get("steunt", []) + a.get("spreekt_tegen", [])]
                print(f"\n=== {s['id']} [{s['deel']}, {s.get('redactie')}: {s.get('oordeel')}] {a['oordeel']} "
                      f"({a['kleur']}), over_beeld {a.get('over_beeld')}\nBERICHT: {s['tekst'][:400]}\n"
                      f"UITLEG: {a.get('uitleg')}\nBRONNEN: {bronnen}")
        return
    print(json.dumps(telling(alle, antwoorden, labels), ensure_ascii=False, indent=1))
    print(f"samen met de ontwikkelcheck ${uitgegeven(UIT):.2f}")


if __name__ == "__main__":
    main()
