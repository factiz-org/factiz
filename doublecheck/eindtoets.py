"""De eindtoets van de hele keten, met labels van de PO (PLAN #32.8).

Het eerste cijfer van de keten zoals die live zou gaan: kring 1, de machine (v4) met herkansing en feitenstap, de
vormvraag, de detailvraag, de vloer en de herkomstcontrole, live door `beoordeel`. Op 60 Engelse berichten die
nooit in een set zaten:
- K: beweringen uit de checks die op 29 oktober uit de feed binnenkwamen; de eigen check staat in de database;
- V: andere beweringen uit dezelfde nieuwe checks, met de eigen check en zijn cluster verborgen;
- W: ware berichten uit Portal:Current events (20 tot 28 oktober 2026).
De PO beoordeelt elk antwoord: *klopt*, *klopt niet* of *te voorzichtig*. Claude zet geen label.

    python -m doublecheck.eindtoets set|lezen
    python -m doublecheck.hittewacht -- python -m doublecheck.eindtoets draaien
    python -m doublecheck.eindtoets uitvoer|tellen
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

from doublecheck.snelantwoord import percentiel

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "eindtoets"
LABELS = WORTEL / "docs" / "steekproeven" / "32.8-eindtoets.json"
BUDGET = 3.5  # PO 2026-10-29: "de eindtoets van de hele keten (~$3)"
N_PER_DEEL = 20
DAGEN = range(20, 29)
ZAAD = 3208
SCHATTING = 0.06  # per bericht live, ruim
OORDELEN_PO = ("klopt", "klopt niet", "te voorzichtig")
_BRON = re.compile(r"\s*\[https?://[^\]]*\]")
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")


class Weigering(Exception):
    """Tellen of draaien kan niet: een bericht zonder label van de PO, of boven het budget."""


def portal_zinnen(wikitekst: str) -> list[str]:
    """De gebeurtenissen van één dag uit Portal:Current events: de regels met een bron, zonder opmaak en bronnen."""
    uit = []
    for regel in wikitekst.splitlines():
        if not regel.startswith("*") or "[http" not in regel:
            continue
        tekst = _LINK.sub(r"\1", _BRON.sub("", regel.lstrip("*").strip()))
        tekst = re.sub(r"'{2,}", "", tekst).strip()
        if tekst:
            uit.append(tekst)
    return uit


def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict[str, str]) -> dict:
    """Per deel en samen, met de labels van de PO. Weigert zolang een beantwoord bericht geen label heeft."""
    open_ = [s["id"] for s in stukken if s["id"] in antwoorden and s["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} zonder label van de PO in {LABELS.name}, bijvoorbeeld {open_[0]}")
    per_deel: dict[str, Counter] = {}
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        label, kleur = labels[s["id"]], a["kleur"]
        for d in (per_deel.setdefault(s["deel"], Counter()), per_deel.setdefault("samen", Counter())):
            d["n"] += 1
            d[label] += 1
            d[kleur or "geen kleur"] += 1
            if s["deel"] == "W" and kleur == "rood" and label == "klopt niet":
                d["onterecht rood"] += 1
            if s["deel"] in ("K", "V") and kleur == "groen" and label == "klopt niet":
                d["onterecht groen"] += 1
            if s["deel"] in ("K", "V") and kleur == "rood" and label == "klopt":
                d["rood en terecht"] += 1
    tijden = [a["seconden"] for a in antwoorden.values()]
    samen = per_deel.pop("samen", Counter())
    return {"per deel": {k: dict(v) for k, v in sorted(per_deel.items())}, "samen": dict(samen),
            "tijd": {"p50": percentiel(tijden, 0.5), "p95": percentiel(tijden, 0.95)} if tijden else {},
            "kosten per bericht": round(sum(a["kosten"] for a in antwoorden.values()) / len(antwoorden), 4)
            if antwoorden else None}


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def lees_labels() -> dict[str, str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r["label"] for r in d.get("oordelen", []) if r.get("label") in OORDELEN_PO}


def _maak_set() -> list[dict]:  # pragma: no cover - netwerk en database
    import sqlite3

    from doublecheck.clustering import cluster_members
    from doublecheck.koppen import _wikitekst

    rng = random.Random(ZAAD)
    zinnen = [(dag, z) for dag in DAGEN for z in portal_zinnen(_wikitekst(f"Portal:Current events/2026 October {dag}"))
              if 60 <= len(z) <= 300]
    w = rng.sample(zinnen, N_PER_DEEL)
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, f.verdict_normalized, max(f.review_date), f.publisher FROM claim c "
        "JOIN factcheck f ON f.claim_id = c.claim_id WHERE f.review_date > '2026-10-03' AND f.language = 'en' "
        "AND f.verdict_normalized IN ('onwaar', 'misleidend', 'waar') GROUP BY c.claim_id ORDER BY c.claim_id").fetchall()
    gekozen = [tuple(r) for r in rng.sample(rijen, 2 * N_PER_DEEL)]
    uit = [{"id": f"K:{c}", "deel": "K", "tekst": t.strip(), "claim": c, "oordeel": o, "datum": d, "redactie": p,
            "verborgen": []} for c, t, o, d, p in gekozen[:N_PER_DEEL]]
    uit += [{"id": f"V:{c}", "deel": "V", "tekst": t.strip(), "claim": c, "oordeel": o, "datum": d, "redactie": p,
             "verborgen": sorted({c} | cluster_members(conn, c))} for c, t, o, d, p in gekozen[N_PER_DEEL:]]
    uit += [{"id": f"W:{dag}-{i}", "deel": "W", "tekst": z, "claim": None, "oordeel": "waar",
             "datum": f"2026-10-{dag:02d}", "redactie": None, "verborgen": []} for i, (dag, z) in enumerate(w)]
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "set.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    return uit


def _config():  # pragma: no cover - op config.toml
    import dataclasses

    from doublecheck.config import load_config

    config = load_config(None)
    alles = dataclasses.replace(config.berichtcontrole, aan=True, kring1=True, herkomst="herkomst-v2",
                                vorm="vorm-v2", detail="detail-v3", vloer="vloer-v2", beweringen="")
    return dataclasses.replace(config, berichtcontrole=alles)


def _draaien() -> None:  # pragma: no cover - live, met het model
    import time

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    config = _config()
    conn = connect(str(WORTEL / "doublecheck.db"))
    kosten = bc.kostenverbinding(config)
    tabel, zinnen = bc.ijktabel(config), bc.feitzinnen()
    pad = UIT / "antwoorden.jsonl"
    gedaan = {r["id"] for r in _jsonl(pad)}
    for s in _jsonl(UIT / "set.jsonl"):
        if s["id"] in gedaan:
            continue
        uitgegeven = sum(r["kosten"] for r in _jsonl(pad))
        if uitgegeven + SCHATTING > BUDGET:
            raise Weigering(f"gestopt: ${uitgegeven:.2f} plus ${SCHATTING:.2f} is meer dan ${BUDGET:.2f}")
        begin = time.perf_counter()
        uit = None
        if s["deel"] != "V":  # bij V doet de eigen check alsof hij er niet is, dus ook geen eerste kring
            uit = bc.snel_antwoord(api.los_op(conn, config, s["tekst"], None, None).model_dump(), tabel, s["tekst"],
                                   config.model_versions.text_embedding)
        if uit is None:
            voorbereid = bc.voorbereiden(conn, config, s["tekst"], verborgen=frozenset(s["verborgen"]))
            uit = bc.beoordeel(kosten, voorbereid, client, config, s["datum"], tabel, zinnen, dag="eindtoets-32.8")
        rij = {"id": s["id"], "seconden": round(time.perf_counter() - begin, 2), "kosten": round(uit["kosten"], 5),
               "kleur": uit["kleur"], "oordeel": uit["oordeel"], "stand": uit["stand"], "regels": uit["regels"],
               "bewering": uit["bewering"], "uitleg": uit["uitleg"], "correcties": uit["correcties"],
               "herkomst": uit["herkomst"], "route": uit["versies"].get("route", "machine"),
               "bronnen": uit["bronnen"]}
        with pad.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
        print(f"{s['id']}: {uit['oordeel']} ({uit['kleur']}), {rij['seconden']} s, ${rij['kosten']:.3f}", flush=True)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De eindtoets van de hele keten (PLAN #32.8)")
    parser.add_argument("stap", choices=("set", "lezen", "draaien", "uitvoer", "tellen"))
    args = parser.parse_args()
    if args.stap == "set":
        uit = _maak_set()
        print(len(uit), Counter(s["deel"] for s in uit))
    elif args.stap == "lezen":
        for s in _jsonl(UIT / "set.jsonl"):
            print(f"{s['id']} [{s['oordeel']}] {s['tekst']}")
    elif args.stap == "draaien":
        _draaien()
    else:
        stukken = _jsonl(UIT / "set.jsonl")
        antwoorden = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
        if args.stap == "uitvoer":
            print(json.dumps([{**s, "antwoord": antwoorden.get(s["id"])} for s in stukken], ensure_ascii=False)[:500])
        else:
            print(json.dumps(telling(stukken, antwoorden, lees_labels()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
