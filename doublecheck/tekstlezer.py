"""De lezer met de database op tekst (PLAN #32.30, stap 2).

`lezer-v5` is gemeten op screenshots (§201), niet op tekst. Hier twee armen op dezelfde zoekresultaten, door dezelfde
functies als `/check`: `lezer-v3` (het product nu) en `lezer-v5` met de 5 checks uit de database. Per bericht één
zoekvraag bij Brave en één keer kring 1.
- W: de 300 ware berichten van ronde 4 (kring 1 aan), zoals §181;
- W': de 50 verse ware berichten van §182 (kring 1 aan);
- O': de 100 verse onware berichten van §182: kring 1 uit, de resultaten van IFCN-factcheckers (actief of in
  vernieuwing) weggelaten, en bij het opzoeken voor `lezer-v5` de eigen claim en haar groep verborgen, zodat het
  onbekend nepnieuws blijft.
Elk rood of oranje bij W en W' en elk groen bij O' wordt gelezen (`docs/steekproeven/32.30-tekst.json`).

    python -m doublecheck.hittewacht -- python -m doublecheck.tekstlezer draaien [--proef 5]
    python -m doublecheck.tekstlezer lezen|tellen
    python -m doublecheck.tekstlezer wachttijd [--lezer lezer-v7]
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "tekstlezer"
LABELS = WORTEL / "docs" / "steekproeven" / "32.30-tekst.json"
BUDGET = 12.0  # PLAN #32.30: ~$10,40 en ~$0,30 voor de wachttijd, grens $12
PROEF, N_WACHTTIJD = 5, 20
ARMEN = ("3", "5")
LEZERS = {"3": "lezer-v3", "5": "lezer-v5"}
SETS = ("W", "W'", "O'")
ALARM = ("rood", "oranje")
LABELWAARDEN = ("vals", "terecht", "set fout")


class Weigering(Exception):
    """Tellen kan niet: een alarm bij een waar bericht of een groen bij nepnieuws zonder label."""


def _factchecker(url: str, sites: dict) -> bool:
    from doublecheck import bronnen as br

    return any(br.reden(h).startswith("IFCN") for _, h in br.beoordeel(url, sites)["bronnen"])


def zonder_factcheckers(antwoord: dict, sites: dict) -> dict:
    """De resultaten van de zoekdienst zonder IFCN-factcheckers (actief of in vernieuwing), voor O'."""
    web = antwoord.get("web", {})
    return {**antwoord, "web": {**web, "results": [r for r in web.get("results", [])
                                                   if not _factchecker(r["url"], sites)]}}


def twee(s: dict, configs: dict, client, zoek, snel, sites: dict, checks_voor) -> dict[str, dict]:
    """Beide armen voor één bericht: één zoekvraag (betaald bij arm 3), één keer kring 1 (niet bij O'), en de checks
    uit de database alleen voor arm 5, met de verborgen claims van het bericht."""
    gezocht, gevonden, gehaald = {}, {}, {}
    onbekend = s["set"] == "O'"

    def zoek1(q: str) -> dict:
        if q not in gezocht:
            gezocht[q] = zonder_factcheckers(zoek(q), sites) if onbekend else zoek(q)
        return gezocht[q]

    def snel1(tekst: str) -> dict | None:
        if onbekend:
            return None
        if tekst not in gevonden:
            gevonden[tekst] = snel(tekst)
        return gevonden[tekst]

    def checks1(tekst: str) -> list[dict]:
        if tekst not in gehaald:
            gehaald[tekst] = checks_voor(tekst, s.get("verborgen") or frozenset())
        return gehaald[tekst]

    uit = {}
    for arm in ARMEN:
        begin = time.perf_counter()
        r = zc.controleer(sqlite3.connect(":memory:"), s["tekst"], configs[arm], client, zoek1, snel1, sites, "meting",
                          datum=s.get("datum"), zoek_checks=checks1 if arm == "5" else None)
        betaald = r["kosten"] - (zc.ZOEKPRIJS if arm == "5" and r["route"] == "zoeken" else 0)
        gekozen = [b for b in r["bronnen"] if b.get("soort") == "check van een redactie"]
        uit[arm] = {"id": s["id"], "set": s["set"], "arm": arm, "route": r["route"], "oordeel": r["oordeel"],
                    "kleur": r["kleur"], "uitleg": r["uitleg"], "over_beeld": r["over_beeld"], "bronnen": r["bronnen"],
                    "checks": len(gehaald.get(s["tekst"]) or []) if arm == "5" else 0,
                    "gekozen": [{k: b.get(k) for k in ("url", "redactie", "oordeel", "rol")} for b in gekozen],
                    "kosten": round(betaald, 5), "seconden": round(time.perf_counter() - begin, 2)}
    return uit


def _moet_lezen(r: dict) -> bool:
    return (r["set"] in ("W", "W'") and r["kleur"] in ALARM) or (r["set"] == "O'" and r["kleur"] == "groen")


def telling(rijen: list[dict], labels: dict[tuple[str, str], str]) -> dict:
    """Per set en arm de kleuren, het valse alarm bij W en W' en het onterechte groen bij O', met de eisen van PLAN
    #32.30. Weigert zolang iets dat telt geen label heeft."""
    open_ = sorted((r["id"], r["arm"]) for r in rijen if _moet_lezen(r) and (r["id"], r["arm"]) not in labels)
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    uit: dict = {}
    for r in rijen:
        d = uit.setdefault(r["set"], {}).setdefault(r["arm"], Counter())
        sleutel = "vals alarm" if r["set"] != "O'" else "vals groen"
        d[sleutel] = d.get(sleutel, 0)  # ook als het nul blijft
        d["n"] += 1
        d[r["kleur"] or "geen kleur"] += 1
        d["kosten"] += r["kosten"]
        if _moet_lezen(r) and labels[(r["id"], r["arm"])] == "vals":
            d[sleutel] += 1
    uit = {s: {a: dict(c) for a, c in per.items()} for s, per in uit.items()}

    def n(set_: str, arm: str, k: str) -> int:
        return uit.get(set_, {}).get(arm, {}).get(k, 0)

    uit["eisen"] = {"W: hoogstens 3 van 300 vals alarm": n("W", "5", "vals alarm") <= 3,
                    "W: niet meer vals alarm dan lezer-v3": n("W", "5", "vals alarm") <= n("W", "3", "vals alarm"),
                    "W': niet meer vals alarm dan lezer-v3": n("W'", "5", "vals alarm") <= n("W'", "3", "vals alarm"),
                    "O': niet meer onterecht groen dan lezer-v3": n("O'", "5", "vals groen") <= n("O'", "3",
                                                                                                    "vals groen")}
    return uit


def lees_labels(d: dict) -> dict[tuple[str, str], str]:
    labels = {(r["id"], r["arm"]): r["label"] for r in d.get("oordelen", [])}
    fout = [k for k, v in labels.items() if v not in LABELWAARDEN]
    if fout:
        raise Weigering(f"onbekende labels in {LABELS.name}: {fout[:3]}")
    return labels


# --- de bestanden en de CLI ----------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _labels() -> dict[tuple[str, str], str]:  # pragma: no cover - een bestand
    return lees_labels(json.loads(LABELS.read_text(encoding="utf-8"))) if LABELS.exists() else {}


def stukken(conn=None) -> list[dict]:  # pragma: no cover - op de sets van ronde 4 en §182
    from doublecheck import controle500 as c5
    from doublecheck import versetoets as vt

    w = [{**x, "set": "W"} for x in c5.stukken() if x["deel"] == "W"]
    vers = _jsonl(vt.UIT / "set.jsonl")
    ww = [{**x, "set": "W'"} for x in vers if x["deel"] == "W"]
    o = [{**x, "set": "O'", "claim": x["id"].split(":", 1)[1]} for x in vers if x["deel"] == "O"]
    if conn is not None:
        groep = {c: g for c, g in conn.execute("SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
        leden: dict[str, set[str]] = {}
        for c, g in groep.items():
            leden.setdefault(g, set()).add(c)
        o = [{**x, "verborgen": frozenset(leden.get(groep.get(x["claim"], x["claim"]), {x["claim"]}))} for x in o]
    return w + ww + o


def _draai(proef: int | None) -> None:  # pragma: no cover - live
    import dataclasses
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    configs = {arm: dataclasses.replace(config, berichtcontrole=dataclasses.replace(
        config.berichtcontrole, lezer=LEZERS[arm], beeld=False)) for arm in ARMEN}
    client, sleutel = anthropic.Anthropic(max_retries=6), os.environ["BRAVE_API_KEY"]
    tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
    alle = stukken(connect(str(WORTEL / "doublecheck.db")))
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "antwoorden.jsonl"
    gedaan = {r["id"] for r in _jsonl(pad)}
    werk = [s for s in alle if s["id"] not in gedaan]
    if proef:
        werk = [s for set_ in SETS for s in [x for x in werk if x["set"] == set_][:proef]]
    print(f"{len(werk)} berichten ({len(gedaan)} al gedaan)", flush=True)
    slot, lokaal = threading.Lock(), threading.local()
    api.los_op(connect(str(WORTEL / "doublecheck.db")), config, "warm", None, None)

    def doe(s: dict) -> None:
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        conn = lokaal.conn
        with slot:
            if sum(r["kosten"] for r in _jsonl(pad)) > BUDGET - 0.5:  # ruimte voor de wachttijd
                return

        def snel(tekst: str) -> dict | None:
            return bc.snel_antwoord(api.los_op(conn, config, tekst, None, None).model_dump(), tabel, tekst,
                                    config.model_versions.text_embedding)

        def checks_voor(tekst: str, verborgen: frozenset) -> list[dict]:
            fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
            return zc.checks_uit(bc.geheugen_met(conn, config, tekst, fp, [], verborgen))

        uit = twee(s, configs, client, lambda q: zc.brave(q, sleutel), snel, sites, checks_voor)
        with slot:
            with pad.open("a", encoding="utf-8") as fh:
                for arm in ARMEN:
                    fh.write(json.dumps(uit[arm], ensure_ascii=False) + "\n")
            print(f"{s['id']} [{s['set']}]: " + ", ".join(f"v{a} {uit[a]['oordeel']} ({uit[a]['kleur']})" for a in ARMEN)
                  + f", {uit['3']['route']}, ${sum(uit[a]['kosten'] for a in ARMEN):.3f}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(doe, werk))
    print(f"samen ${sum(r['kosten'] for r in _jsonl(pad)):.2f} van ${BUDGET:.2f}", flush=True)


def _lezen() -> None:  # pragma: no cover - op de bestanden
    labels, per_id = _labels(), {s["id"]: s for s in stukken()}
    for r in sorted(_jsonl(UIT / "antwoorden.jsonl"), key=lambda r: (r["set"], r["id"], r["arm"])):
        if not _moet_lezen(r) or (r["id"], r["arm"]) in labels:
            continue
        s = per_id[r["id"]]
        print(f"\n== {r['id']} [{r['set']}] arm {r['arm']}: {r['oordeel']} ({r['kleur']})\n{s['tekst'][:600]}\n"
              f"uitleg: {r['uitleg']}")
        for b in r["bronnen"]:
            print(f"  - {b.get('rol')}: {b.get('site') or b.get('redactie')} {b.get('band') or b.get('oordeel') or ''} "
                  f"{b.get('url')}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    rijen = _jsonl(UIT / "antwoorden.jsonl")
    tel = telling(rijen, _labels())
    (UIT / "telling.json").write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")
    for set_ in SETS:
        for arm in ARMEN:
            print(set_, f"lezer-v{arm}", tel.get(set_, {}).get(arm))
    print("eisen:", tel["eisen"])


def _wachttijd(lezer: str = "lezer-v5") -> None:  # pragma: no cover - live
    """20 berichten uit W door het echte `POST /check`, lokaal, met `lezer` (#32.30: `lezer-v5`; #32.33: `lezer-v7`) en de
    controle aan in een kopie van de config; de config op schijf verandert niet."""
    import dataclasses

    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.config import load_config
    from doublecheck.snelantwoord import percentiel
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, aan=True,
                                                                             lezer=lezer))
    api.app.dependency_overrides[api.get_config] = lambda: config
    tijden, routes = [], Counter()
    try:
        klant = TestClient(api.app)
        for s in [x for x in stukken() if x["set"] == "W"][-N_WACHTTIJD:]:
            begin = time.perf_counter()
            a = klant.post("/check", json={"text": s["tekst"]})
            tijden.append(round(time.perf_counter() - begin, 2))
            routes[a.json().get("route") if a.status_code == 200 else f"fout {a.status_code}"] += 1
    finally:
        api.app.dependency_overrides.clear()
    uit = {"n": len(tijden), "p50": percentiel(tijden, .5), "p95": percentiel(tijden, .95), "routes": dict(routes),
           "tijden": tijden}
    naam = "wachttijd.json" if lezer == "lezer-v5" else f"wachttijd-{lezer}.json"
    (UIT / naam).write_text(json.dumps({"lezer": lezer, **uit}, indent=1), encoding="utf-8")
    print(uit)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De lezer met de database op tekst (PLAN #32.30)")
    parser.add_argument("stap", choices=("draaien", "lezen", "tellen", "wachttijd"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--lezer", default="lezer-v5", help="wachttijd: de lezer in de kopie van de config (#32.33)")
    args = parser.parse_args()
    {"draaien": lambda: _draai(args.proef), "lezen": _lezen, "tellen": _tellen,
     "wachttijd": lambda: _wachttijd(args.lezer)}[args.stap]()


if __name__ == "__main__":
    main()
