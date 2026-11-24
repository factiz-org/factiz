"""Het beeld in de nieuwe controle (PLAN #32.16).

`zoekcontrole.controleer`, dezelfde functie als `POST /check`, met en zonder het beeld, op de sets van §178: N, 58
echte screenshots van bekend nepnieuws, en W, 60 echte foto's die M4FC *waar* noemt. Per bericht één zoekvraag en één
keer de database voor beide armen: het enige verschil is het beeld. Live vragen op openbare beelden uit M4FC; het
beeld alleen in het werkgeheugen. Elk rood of oranje bij N zonder de eigen check, elk groen bij N en elk rood of
oranje bij W wordt gelezen (`docs/steekproeven/32.16-beeldcontrole.json`).

    python -m doublecheck.hittewacht -- python -m doublecheck.beeldcontrole draaien [--proef N]
    python -m doublecheck.beeldcontrole lezen|tellen
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
SET = WORTEL / "data" / "beeldronde" / "set.jsonl"
UIT = WORTEL / "data" / "beeldcontrole"
LABELS = WORTEL / "docs" / "steekproeven" / "32.16-beeldcontrole.json"
BUDGET = 3.0  # PO 2026-10-30: "grens $3"; Sonnet en Brave samen, Brave tegen de lijstprijs
ARMEN = ("zonder", "met")
ALARM = ("rood", "oranje")


class Weigering(Exception):
    """Tellen kan niet: iets dat telt zonder label."""


LEZER = "lezer-v3"  # #32.16 mat met de lezer van toen; sinds 2026-11-03 staat lezer-v5 in de config


def armen(config) -> dict:
    """De config per arm: het beeld alleen aan in een kopie voor de arm *met*, en de lezer van #32.16; verder verandert
    er niets."""
    c = config.berichtcontrole
    return {arm: dataclasses.replace(config, berichtcontrole=dataclasses.replace(c, beeld=arm == "met", lezer=LEZER))
            for arm in ARMEN}


def _adres(url: str) -> str:
    deel = urlsplit(url)
    return (deel.hostname or "").removeprefix("www.") + deel.path.rstrip("/")


def met_eigen_check(uit: dict, eigen_urls: set[str]) -> bool:
    """De eigen check staat als bron: uit de database, of als resultaat dat de bewering tegenspreekt."""
    eigen = {_adres(u) for u in eigen_urls}
    return any(_adres(b.get("url") or "") in eigen for b in uit["bronnen"]
               if b.get("soort") == "check van een redactie" or b.get("rol") == "spreekt tegen")


def beide(s: dict, beeld: bytes, configs: dict, client, zoek, snel, sites: dict, eigen_urls: set[str]) -> dict:
    """Beide armen voor één bericht, met één zoekvraag en één keer de database; het beeld alleen in de arm *met*.
    De zoekvraag wordt één keer betaald, bij de arm *zonder*."""
    gezocht, gevonden = {}, {}

    def zoek1(q: str) -> dict:
        if q not in gezocht:
            gezocht[q] = zoek(q)
        return gezocht[q]

    def snel1(tekst: str) -> dict | None:
        if tekst not in gevonden:
            gevonden[tekst] = snel(tekst)
        return gevonden[tekst]

    kosten = sqlite3.connect(":memory:")
    uit = {}
    for arm in ARMEN:
        begin = time.perf_counter()
        r = zc.controleer(kosten, s["tekst"], configs[arm], client, zoek1, snel1, sites, "meting",
                          datum=s.get("datum"), beeld=beeld if arm == "met" else None)
        betaald = r["kosten"] - (zc.ZOEKPRIJS if arm == "met" and r["route"] == "zoeken" else 0)
        uit[arm] = {"id": s["id"], "set": s["set"], "arm": arm, "route": r["route"], "oordeel": r["oordeel"],
                    "kleur": r["kleur"], "over_beeld": r["over_beeld"], "uitleg": r["uitleg"],
                    "bronnen": r["bronnen"], "eigen_check": met_eigen_check(r, eigen_urls),
                    "kosten": round(betaald, 5), "seconden": round(time.perf_counter() - begin, 2)}
    return uit


def telling(stukken: list[dict], per_arm: dict[str, dict[str, dict]], labels: dict[tuple[str, str], str]) -> dict:
    """Per arm, alleen op berichten met een antwoord in beide armen: bij N gewaarschuwd met bewijs (de eigen check
    als bron, of een andere bron gelezen als *bewijst*) en onterecht groen, bij W vals alarm; met de drie eisen van
    PLAN #32.16. Weigert zolang iets dat telt geen label heeft. Een onvolledige run haalt de eisen nooit."""
    paren = [s for s in stukken if all(s["id"] in per_arm.get(arm, {}) for arm in ARMEN)]
    uit, open_ = {}, []
    for arm in ARMEN:
        per_set = {"N": Counter(), "W": Counter()}
        for s in paren:
            r, label, d = per_arm[arm][s["id"]], labels.get((s["id"], arm)), per_set[s["set"]]
            d["n"] += 1
            d[r["kleur"] or "geen kleur"] += 1
            d["over_beeld"] += bool(r.get("over_beeld"))
            d["via de database"] += r["route"] == "database"
            if s["set"] == "N" and r["kleur"] in ALARM and r["eigen_check"]:
                d["gewaarschuwd met bewijs"] += 1
                d["met de eigen check"] += 1
            elif (s["set"] == "N" and r["kleur"] in (*ALARM, "groen")) or (s["set"] == "W" and r["kleur"] in ALARM):
                if label is None:
                    open_.append(f"{s['id']} {arm} {r['kleur']}")
                elif s["set"] == "W":
                    d["vals alarm"] += label == "vals"
                elif r["kleur"] == "groen":
                    d["onterecht groen"] += label == "vals groen"
                else:
                    d["gewaarschuwd met bewijs"] += label == "bewijst"
        uit[arm] = {k: dict(v) for k, v in per_set.items()}
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    zonder, met = uit["zonder"], uit["met"]
    uit["eisen"] = {
        "1. N: met beeld minstens zoveel gewaarschuwd met bewijs als zonder":
            met["N"].get("gewaarschuwd met bewijs", 0) >= zonder["N"].get("gewaarschuwd met bewijs", 0),
        "2. W: met beeld niet meer vals alarm dan zonder":
            met["W"].get("vals alarm", 0) <= zonder["W"].get("vals alarm", 0),
        "3. N: met beeld geen onterecht groen": met["N"].get("onterecht groen", 0) == 0}
    uit["volledig"] = f"{len(paren)} van {len(stukken)}"
    uit["gehaald"] = all(uit["eisen"].values()) and len(paren) == len(stukken)
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def lees_labels() -> dict[tuple[str, str], str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {(r["id"], r["arm"]): r["label"] for r in d.get("oordelen", [])}


def _eigen_urls(conn, s: dict) -> set[str]:  # pragma: no cover - op de database
    """De adressen van de eigen check: alle checks van de eigen claims in de database, en die uit het geheugen."""
    ids = s.get("eigen") or []
    urls = {g["url"] for g in s.get("geheugen") or [] if g.get("claim") in ids and g.get("url")}
    for i in ids:
        urls |= {u for (u,) in conn.execute("SELECT url FROM factcheck WHERE claim_id = ?", (i,))}
    return urls


def _draai(stukken: list[dict], pad: Path) -> None:  # pragma: no cover - live
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.plafond import _beeld
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    configs = armen(config)
    client, sleutel = anthropic.Anthropic(), os.environ["BRAVE_API_KEY"]
    tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
    slot, lokaal = threading.Lock(), threading.local()
    api.los_op(connect(str(WORTEL / "doublecheck.db")), config, "warm", None, None)  # het tekstmodel één keer laden

    def doe(s: dict) -> None:
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        conn = lokaal.conn
        with slot:
            if sum(r["kosten"] for r in _jsonl(pad)) > BUDGET - 0.05:  # ruimte voor de berichten die nog lopen
                return

        def snel(tekst: str) -> dict | None:
            return bc.snel_antwoord(api.los_op(conn, config, tekst, None, None).model_dump(), tabel, tekst,
                                    config.model_versions.text_embedding)

        uit = beide(s, _beeld(s["beeld"]), configs, client, lambda q: zc.brave(q, sleutel), snel, sites,
                    _eigen_urls(conn, s))
        with slot:
            with pad.open("a", encoding="utf-8") as fh:
                for arm in ARMEN:
                    fh.write(json.dumps(uit[arm], ensure_ascii=False) + "\n")
            print(f"{s['id']} [{s['set']}]: zonder {uit['zonder']['oordeel']} ({uit['zonder']['kleur']}), "
                  f"met {uit['met']['oordeel']} ({uit['met']['kleur']}), {uit['met']['route']}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(doe, stukken))


def main() -> None:  # pragma: no cover - CLI, live
    import argparse

    from doublecheck.snelantwoord import percentiel

    parser = argparse.ArgumentParser(description="Het beeld in de nieuwe controle (PLAN #32.16)")
    parser.add_argument("stap", choices=("draaien", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="draaien: alleen zoveel uit N en zoveel uit W")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "antwoorden.jsonl"
    stukken = _jsonl(SET)
    rijen = _jsonl(pad)
    per_arm = {arm: {r["id"]: r for r in rijen if r["arm"] == arm} for arm in ARMEN}
    if args.stap == "draaien":
        # N eerst: raakt de grens het einde, dan is de run onvolledig en haalt hij de eisen niet
        nog = [s for s in sorted(stukken, key=lambda s: s["set"] != "N") if s["id"] not in per_arm["met"]]
        if args.proef:
            nog = [s for deel in ("N", "W") for s in [x for x in nog if x["set"] == deel][: args.proef]]
        _draai(nog, pad)
        print(f"samen ${sum(r['kosten'] for r in _jsonl(pad)):.2f} van ${BUDGET:.2f}")
        return
    labels = lees_labels()
    if args.stap == "lezen":
        per_id = {s["id"]: s for s in stukken}
        for (i, arm), r in sorted(((r["id"], r["arm"]), r) for r in rijen):
            s = per_id[i]
            lezen = (s["set"] == "N" and r["kleur"] in ALARM and not r["eigen_check"]) or \
                    (s["set"] == "N" and r["kleur"] == "groen") or (s["set"] == "W" and r["kleur"] in ALARM)
            if not lezen or (i, arm) in labels:
                continue
            eigen = [(g["redactie"], g["tekst"][:200], g["url"]) for g in s.get("geheugen") or []
                     if g.get("claim") in (s.get("eigen") or [])]
            print(f"\n=== {i} [{s['set']}] {arm}: {r['oordeel']} ({r['kleur']}), {r['route']}, over_beeld "
                  f"{r['over_beeld']}\nTEKST: {s['tekst'][:400]}\nUITLEG: {r['uitleg']}\n"
                  f"BRONNEN: {[(b.get('site') or b.get('redactie'), b.get('band'), b.get('rol'), b.get('url')) for b in r['bronnen']]}"
                  f"\nEIGEN CHECK: {eigen}")
        return
    uit = telling(stukken, per_arm, labels)
    tijden = [r["seconden"] for r in rijen if r["route"] == "zoeken"]
    uit["tijd per arm"] = {"p50": percentiel(tijden, .5), "p95": percentiel(tijden, .95)} if tijden else {}
    uit["kosten"] = round(sum(r["kosten"] for r in rijen), 2)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
