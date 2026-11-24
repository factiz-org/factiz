"""De nieuwe controle op 500 berichten uit ronde 4 (PLAN #32.11).

De controle van B51 met `lezer-v2` (misleidend, de ruimere regel voor groen) en het label voor staatsmedia, door
dezelfde functies als `/check`, op:
- W: de 300 ware berichten van ronde 4 (tekst en chat, als tekst);
- B: 100 bekend nepnieuws als tekst, met de check in de database (kring 1);
- O: 100 onbekend nepnieuws als tekst: kring 1 uit, en de resultaten van IFCN-factcheckers weggelaten, zoals
  ronde 4 de factchecksites blokkeerde.
Elk rood of oranje bij W en elk groen bij B of O wordt gelezen (`docs/steekproeven/32.11-controle500.json`).

    python -m doublecheck.hittewacht -- python -m doublecheck.controle500 draaien
    python -m doublecheck.controle500 lezen|tellen
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from doublecheck.snelantwoord import percentiel

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "controle500"
LABELS = WORTEL / "docs" / "steekproeven" / "32.11-controle500.json"
BUDGET = 4.0  # PLAN #32.11
LEZER = "lezer-v2"
ALARM = ("rood", "oranje")
NIVEAUS = (("99%", 0.01), ("98%", 0.02), ("97%", 0.03))  # B45: hoogstens 3, 6 of 9 op 300


class Weigering(Exception):
    """Tellen kan niet: een alarm bij een waar bericht of een groen bij nepnieuws zonder label."""


def zonder_factcheckers(resultaten: list[dict]) -> list[dict]:
    """Deel O: de resultaten zonder IFCN-factcheckers, opnieuw genummerd, zoals ronde 4 de factchecksites blokkeerde."""
    return [{**r, "nr": i} for i, r in enumerate((r for r in resultaten if not r.get("factcheck")), 1)]


def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict[str, str],
            bestand: str = LABELS.name) -> dict:
    """Per deel de kleuren, de valse alarmen bij W en de valse groenen bij B en O, met de eisen van PLAN #32.11.
    Weigert zolang een alarm bij W of een groen bij B of O geen label heeft ('vals' of 'set fout')."""
    open_ = [s["id"] for s in stukken if s["id"] in antwoorden and s["id"] not in labels and (
        (s["deel"] == "W" and antwoorden[s["id"]]["kleur"] in ALARM)
        or (s["deel"] != "W" and antwoorden[s["id"]]["kleur"] == "groen"))]
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {bestand}, bijvoorbeeld {open_[0]}")
    uit: dict[str, Counter] = {}
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        d = uit.setdefault(s["deel"], Counter())
        d["n"] += 1
        d[a["kleur"] or "geen kleur"] += 1
        d["streng: " + (a["kleur_streng"] or "geen kleur")] += 1
        d["misleidend"] += a["oordeel"] == "misleidend"
        d["met staatsmedia"] += bool(a.get("staatsmedia"))
        if s["deel"] == "W" and a["kleur"] in ALARM:
            d["vals alarm"] += labels[s["id"]] == "vals"
        if s["deel"] != "W" and a["kleur"] == "groen":
            d["vals groen"] += labels[s["id"]] == "vals"
    w, nep = uit.get("W", Counter()), uit.get("B", Counter()) + uit.get("O", Counter())
    niveau = next((naam for naam, deel in NIVEAUS if w["vals alarm"] <= deel * w["n"]), "niet gehaald")
    tijden = [a["seconden"] for a in antwoorden.values()]
    return {**{k: dict(v) for k, v in sorted(uit.items())},
            "eisen": {"ware berichten": niveau,
                      "nepberichten: hoogstens 1 op 100 onterecht groen": nep["vals groen"] <= 0.01 * nep["n"]},
            "tijd": {"p50": percentiel(tijden, .5), "p95": percentiel(tijden, .95)} if tijden else {},
            "kosten": round(sum(a["kosten"] for a in antwoorden.values()), 2)}


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def stukken() -> list[dict]:  # pragma: no cover - op de set van ronde 4
    from doublecheck import betatoets as t

    s = t._jsonl(t.UIT / "set.jsonl")
    w = [x for x in s if x["deel"] == "waar"]
    b = [x for x in s if x["deel"] == "bekend" and x["vorm"] == "tekst"]
    o = [x for x in s if x["deel"] == "onbekend" and x["vorm"] == "tekst"]
    return ([{**x, "deel": "W"} for x in w] + [{**x, "deel": "B"} for x in b] + [{**x, "deel": "O"} for x in o])


def lees_labels() -> dict[str, str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r["label"] for r in d.get("oordelen", [])}


def _een(s: dict, conn, config, client, sleutel: str, tabel: dict, sites: dict) -> dict:  # pragma: no cover - live
    import time

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck import zoekcontrole as zc

    begin = time.perf_counter()
    if s["deel"] != "O":
        snel = bc.snel_antwoord(api.los_op(conn, config, s["tekst"], None, None).model_dump(), tabel, s["tekst"],
                                config.model_versions.text_embedding)
        if snel is not None:
            return {"id": s["id"], "route": "database", "kleur": snel["kleur"], "kleur_streng": snel["kleur"],
                    "kleur_zonder_beeldregel": snel["kleur"], "oordeel": snel["oordeel"], "over_beeld": False,
                    "wat_klopt": None, "wat_er_gebeurde": None,
                    "kosten": 0.0, "staatsmedia": 0, "seconden": round(time.perf_counter() - begin, 2)}
    resultaten = zc.resultaten_uit(zc.brave(zc.zoekvraag(s["tekst"]), sleutel), sites)
    if s["deel"] == "O":
        resultaten = zonder_factcheckers(resultaten)
    msg = client.messages.create(**zc.leesverzoek(s["tekst"], resultaten, s.get("datum"), config))
    antwoord = zc.lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
    # de beeldregel van #32.12 werkt alleen bij lezer-v3 en later; v1 en v2 geven geen `over_beeld`, en de twee
    # lagen van #32.13 alleen bij lezer-v4
    kleur = zc.kleur_van(antwoord, resultaten, "ruim")
    return {"id": s["id"], "route": "zoeken", "kleur": kleur,
            "kleur_streng": zc.kleur_van(antwoord, resultaten, "streng"),
            "kleur_zonder_beeldregel": zc.kleur_van(antwoord, resultaten, "ruim", beeld_gezien=True), **antwoord,
            "wat_klopt": zc.feit_van(antwoord, resultaten, kleur), "wat_er_gebeurde": zc.anders_van(antwoord, kleur),
            "staatsmedia": sum(bool(r["staatsmedia"]) for r in resultaten),
            "resultaten": [{**{k: r[k] for k in ("nr", "url", "site", "band", "factcheck", "staatsmedia", "titel")},
                            "fragment": r["fragment"][:400]} for r in resultaten],
            "kosten": round(bc.kosten(bc.gebruik_uit(msg)) + zc.ZOEKPRIJS, 5),
            "seconden": round(time.perf_counter() - begin, 2)}


def main() -> None:  # pragma: no cover - CLI, live
    import argparse
    import dataclasses
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="De nieuwe controle op 500 berichten (PLAN #32.11)")
    parser.add_argument("stap", choices=("draaien", "lezen", "tellen"))
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "antwoorden.jsonl"
    alle = stukken()
    if args.stap == "draaien":
        laad_sleutel()
        config = load_config(None)
        config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, lezer=LEZER))
        client, sleutel = anthropic.Anthropic(), os.environ["BRAVE_API_KEY"]
        tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
        gedaan = {r["id"] for r in _jsonl(pad)}
        slot, lokaal = threading.Lock(), threading.local()

        def doe(s: dict) -> None:
            if not hasattr(lokaal, "conn"):
                lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
            with slot:
                if sum(r["kosten"] for r in _jsonl(pad)) > BUDGET:
                    return
            rij = _een(s, lokaal.conn, config, client, sleutel, tabel, sites)
            with slot:
                with pad.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
                print(f"{s['id']} [{s['deel']}]: {rij['oordeel']} ({rij['kleur']}), {rij['seconden']} s", flush=True)

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(doe, [s for s in alle if s["id"] not in gedaan]))
        return
    antwoorden = {r["id"]: r for r in _jsonl(pad)}
    labels = lees_labels()
    if args.stap == "lezen":
        for s in alle:
            a = antwoorden.get(s["id"])
            if a is None or s["id"] in labels:
                continue
            if (s["deel"] == "W" and a["kleur"] in ALARM) or (s["deel"] != "W" and a["kleur"] == "groen"):
                bronnen = [(r["site"], r["band"]) for r in a.get("resultaten", [])
                           if r["nr"] in a.get("steunt", []) + a.get("spreekt_tegen", [])]
                print(f"\n=== {s['id']} [{s['deel']}, set: {s['label']}] {a['oordeel']} ({a['kleur']}), {a['route']}\n"
                      f"BERICHT: {s['tekst'][:400]}\nUITLEG: {a.get('uitleg')}\nBRONNEN: {bronnen}")
        return
    print(json.dumps(telling(alle, antwoorden, labels), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
