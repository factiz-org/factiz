"""De lezer leest ook de checks uit de database, en het beeld helpt kiezen (PLAN #32.28).

Drie armen op dezelfde zoekresultaten: per bericht één zoekvraag bij Brave (`brave-v1`, top 10) en één keer kring 1,
voor alle armen dezelfde, met de datum waarop het bericht rondging, zoals §188. Dezelfde gemaskeerde tekst, zonder beeld
naar het model.
- Arm 0, het product nu: `lezer-v3`.
- Arm 1: `lezer-v5` met de beste 5 checks uit de database, de kandidaten van de woorden (sleutel 1 van de vindronde,
  `berichtcontrole.geheugen_met`), zoals ze in #32.21 per bericht bewaard zijn.
- Arm 2: als arm 1, en bij een check waarvan het beeld de screenshot bevestigt (de vergelijking van #32.21 op een beeld
  dat `rol-v3` viraal noemt) staat `zoekcontrole.BEELDZIN`; een bevestiging buiten de beste 5 komt erbij. Voegt het beeld
  niets toe, dan is de vraag die van arm 1: één keer gesteld, het antwoord geldt in beide armen.
Sets N (58 echte screenshots van bekend nepnieuws) en W (60 echte foto's met hun ware bewering), live vragen aan Sonnet
op openbare beelden uit M4FC; de tekst alleen in het werkgeheugen. Elk rood of oranje bij N zonder de eigen check als
bron, elk groen bij N en elk rood of oranje bij W wordt gelezen (`docs/steekproeven/32.28-database-lezer.json`).

    python -m doublecheck.hittewacht -- python -m doublecheck.databaselezer draaien [--proef 5]
    python -m doublecheck.databaselezer lezen|tellen
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

from doublecheck import beeldcontrole as bk
from doublecheck import vindronde as vr
from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
SET = WORTEL / "data" / "beeldronde" / "set.jsonl"
VRAGEN = vr.MAP / "vragen.jsonl"
PAREN = vr.MAP / "paren.jsonl"
UIT = WORTEL / "data" / "databaselezer"
LABELS = WORTEL / "docs" / "steekproeven" / "32.28-database-lezer.json"
BUDGET = 6.0  # PO 2026-11-02: "run it within the $6 limit"; Sonnet en Brave samen, Brave tegen de lijstprijs
PROEF = 5
ARMEN = ("0", "1", "2")
LEZERS = {"0": "lezer-v3", "1": "lezer-v5", "2": "lezer-v5"}
MODUS = "productie"
ALARM = ("rood", "oranje")
LABELWAARDEN = ("bewijst", "bewijst niet", "vals groen", "vals", "set fout")


class Weigering(Exception):
    """Tellen kan niet: iets dat telt zonder label, of een label dat niet bestaat."""


def armen(config) -> dict:
    """De config per arm, in een kopie: arm 0 de lezer van het product nu, arm 1 en 2 de lezer met de database; geen
    arm ziet het beeld."""
    c = config.berichtcontrole
    return {arm: dataclasses.replace(config, berichtcontrole=dataclasses.replace(c, lezer=LEZERS[arm], beeld=False))
            for arm in ARMEN}


def checks_uit(k1: list[dict], info: dict[tuple[str, str], dict]) -> tuple[list[dict], int]:
    """De checks voor de lezer uit de beste 5 van de woorden, met wat de database over elk zegt (`info` per claim en
    adres); een claim die niet meer in de database staat, valt weg en wordt geteld."""
    uit, weg = [], 0
    for k in k1:
        i = info.get((k["claim"], k["url"]))
        if i is None:
            weg += 1
            continue
        uit.append({"claim": k["claim"], "groep": k.get("groep") or k["claim"], "tekst": i["tekst"],
                    "redactie": i["redactie"], "oordeel": i["oordeel"], "datum": i["datum"], "url": k["url"],
                    "beeld": False})
    return uit, weg


def met_beeld(checks: list[dict], bevestigd: list[dict]) -> list[dict]:
    """De checks van arm 2: die van arm 1, met de zin over het beeld bij een check waarvan het beeld de screenshot
    bevestigt (dezelfde claim of hetzelfde adres), en een bevestigde check die er nog niet stond, erachter."""
    claims, adressen = {b["claim"] for b in bevestigd}, {vr.adres(b["url"]) for b in bevestigd}
    uit = [{**k, "beeld": k["claim"] in claims or vr.adres(k["url"]) in adressen} for k in checks]
    hier, hier_adres = {k["claim"] for k in checks}, {vr.adres(k["url"]) for k in checks}
    for b in bevestigd:
        if b["claim"] not in hier and vr.adres(b["url"]) not in hier_adres:
            uit.append({**b, "beeld": True})
            hier.add(b["claim"])
            hier_adres.add(vr.adres(b["url"]))
    return uit


def bevestigde_artikelen(paren: list[dict], rollen: dict, set_: str, vraag: str) -> list[str]:
    """De artikelen waarvan een beeld de screenshot bevestigt zoals in #32.21 telt (`vindronde._telt`: gevonden in de
    productie, niet de screenshot zelf, bevestigd, en een beeld dat de rolvraag viraal noemt); de sterkste eerst."""
    beste: dict[str, int] = {}
    for p in paren:
        if p["set"] == set_ and p["vraag"] == vraag and vr._telt(p, rollen, MODUS):
            beste[p["artikel"]] = max(beste.get(p["artikel"], 0), p["punten"])
    return sorted(beste, key=lambda a: (-beste[a], a))


def drie(s: dict, checks1: list[dict], checks2: list[dict], configs: dict, client, zoek, snel, sites: dict,
         eigen_urls: set[str], eigen_groepen: set[str]) -> dict[str, dict]:
    """De drie armen voor één bericht, met één zoekvraag en één keer kring 1; de zoekvraag is één keer betaald, bij
    arm 0. Arm 2 met dezelfde checks als arm 1 is dezelfde vraag: niet opnieuw gesteld."""
    gezocht, gevonden = {}, {}

    def zoek1(q: str) -> dict:
        if q not in gezocht:
            gezocht[q] = zoek(q)
        return gezocht[q]

    def snel1(tekst: str) -> dict | None:
        if tekst not in gevonden:
            gevonden[tekst] = snel(tekst)
        return gevonden[tekst]

    kosten, uit = sqlite3.connect(":memory:"), {}
    for arm, checks in zip(ARMEN, (None, checks1, checks2)):
        if arm == "2" and checks2 == checks1:
            uit[arm] = {**uit["1"], "arm": arm, "kopie_van": "1", "kosten": 0.0, "seconden": 0.0}
            continue
        begin = time.perf_counter()
        r = zc.controleer(kosten, s["tekst"], configs[arm], client, zoek1, snel1, sites, "meting",
                          datum=s.get("datum"), checks=checks)
        betaald = r["kosten"] - (zc.ZOEKPRIJS if arm != "0" and r["route"] == "zoeken" else 0)
        groep = {vr.adres(k["url"]): k["groep"] for k in checks or []}
        gekozen = [groep[vr.adres(b["url"])] for b in r["bronnen"] if r["route"] == "zoeken"
                   and b.get("soort") == "check van een redactie" and vr.adres(b["url"]) in groep]
        uit[arm] = {"id": s["id"], "set": s["set"], "arm": arm, "route": r["route"], "oordeel": r["oordeel"],
                    "kleur": r["kleur"], "over_beeld": r["over_beeld"], "uitleg": r["uitleg"], "bronnen": r["bronnen"],
                    "eigen_check": bk.met_eigen_check(r, eigen_urls), "checks": len(checks or []),
                    "beeldchecks": sum(bool(k.get("beeld")) for k in checks or []), "gekozen": gekozen,
                    "eigen_gekozen": any(g in eigen_groepen for g in gekozen),
                    "andere_gekozen": sum(g not in eigen_groepen for g in gekozen), "kopie_van": None,
                    "kosten": round(betaald, 5), "seconden": round(time.perf_counter() - begin, 2)}
    return uit


def _label(labels: dict, r: dict) -> str | None:
    """Het label van een antwoord; een kopie van arm 1 draagt het label van arm 1."""
    return labels.get((r["id"], r["arm"])) or (labels.get((r["id"], r["kopie_van"])) if r.get("kopie_van") else None)


def telt_als_lezen(s: dict, r: dict) -> bool:
    return (s["set"] == "N" and r["kleur"] in (*ALARM, "groen") and not (r["kleur"] in ALARM and r["eigen_check"])) \
        or (s["set"] == "W" and r["kleur"] in ALARM)


def telling(stukken: list[dict], per_arm: dict[str, dict[str, dict]], labels: dict[tuple[str, str], str]) -> dict:
    """Per arm, alleen op berichten met een antwoord in alle drie: bij N gewaarschuwd met bewijs (de eigen check als
    bron, of een andere bron gelezen als *bewijst*) en onterecht groen, bij W vals alarm; hoe vaak de lezer de eigen
    check koos en hoe vaak een andere; met de vier eisen van PLAN #32.28, vooraf. Weigert zolang iets dat telt geen
    label heeft. Een onvolledige run haalt de eisen nooit."""
    fout = sorted({v for v in labels.values() if v not in LABELWAARDEN})
    if fout:
        raise Weigering(f"onbekende labels in {LABELS.name}: {fout}")
    paren = [s for s in stukken if all(s["id"] in per_arm.get(arm, {}) for arm in ARMEN)]
    uit, open_ = {}, []
    for arm in ARMEN:
        per_set = {"N": Counter(), "W": Counter()}
        for s in paren:
            r, d = per_arm[arm][s["id"]], per_set[s["set"]]
            label = _label(labels, {"id": s["id"], "arm": arm, **r})
            d["n"] += 1
            d[r["kleur"] or "geen kleur"] += 1
            d["via de database"] += r["route"] == "database"
            d["eigen check gekozen"] += bool(r.get("eigen_gekozen"))
            d["andere check gekozen"] += bool(r.get("andere_gekozen"))
            if s["set"] == "N" and r["kleur"] in ALARM and r["eigen_check"]:
                d["gewaarschuwd met bewijs"] += 1
                d["met de eigen check"] += 1
            elif telt_als_lezen(s, r):
                if label is None:
                    open_.append(f"{s['id']} arm {arm} {r['kleur']}")
                elif s["set"] == "W":
                    d["vals alarm"] += label == "vals"
                elif r["kleur"] == "groen":
                    d["onterecht groen"] += label == "vals groen"
                else:
                    d["gewaarschuwd met bewijs"] += label == "bewijst"
        uit[arm] = {k: dict(v) for k, v in per_set.items()}
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")

    def n(arm: str, set_: str, k: str) -> int:
        return uit[arm][set_].get(k, 0)

    gw = "gewaarschuwd met bewijs"
    eisen = {"1. N: arm 1 minstens 10 meer gewaarschuwd met bewijs dan arm 0": n("1", "N", gw) >= n("0", "N", gw) + 10,
             "2. N: arm 2 minstens 4 meer gewaarschuwd met bewijs dan arm 1": n("2", "N", gw) >= n("1", "N", gw) + 4,
             "3. W: in arm 1 en arm 2 niet meer vals alarm dan in arm 0":
                 all(n(a, "W", "vals alarm") <= n("0", "W", "vals alarm") for a in ("1", "2")),
             "4. N: in arm 1 en arm 2 niet meer onterecht groen dan in arm 0":
                 all(n(a, "N", "onterecht groen") <= n("0", "N", "onterecht groen") for a in ("1", "2"))}
    e = list(eisen.values())
    uit["eisen"] = eisen
    uit["volledig"] = f"{len(paren)} van {len(stukken)}"
    uit["database kandidaat"] = len(paren) == len(stukken) and e[0] and e[2] and e[3]
    uit["beeld kandidaat"] = uit["database kandidaat"] and e[1]
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def lees_labels() -> dict[tuple[str, str], str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {(r["id"], r["arm"]): r["label"] for r in d.get("oordelen", [])}


def _per_arm(rijen: list[dict]) -> dict[str, dict[str, dict]]:
    return {arm: {r["id"]: r for r in rijen if r["arm"] == arm} for arm in ARMEN}


def _database(conn, vragen: dict[str, dict], paren: list[dict], rollen: dict) -> dict[str, dict]:  # pragma: no cover
    """Per bericht de checks van arm 1 en 2, de eigen groepen en de adressen van de eigen check, uit de productie."""
    groep = {c: g for c, g in conn.execute("SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
    per_adres: dict[str, list[tuple]] = {}
    for rij in conn.execute("SELECT f.claim_id, f.url, c.canonical_text, f.publisher, f.verdict_normalized, "
                            "f.review_date FROM factcheck f JOIN claim c USING (claim_id)"):
        per_adres.setdefault(vr.adres(rij[1]), []).append(rij)
    info = {(c, u): {"tekst": t, "redactie": p, "oordeel": o, "datum": str(d)[:10]}
            for rijen in per_adres.values() for c, u, t, p, o, d in rijen}
    urls_per_groep: dict[str, set[str]] = {}
    for (c, u) in info:
        urls_per_groep.setdefault(groep.get(c, c), set()).add(u)
    uit = {}
    for i, v in vragen.items():
        checks1, weg = checks_uit(v["k1"][MODUS], info)
        bevestigd = [{"claim": c, "groep": groep.get(c, c), "tekst": t, "redactie": p, "oordeel": o,
                      "datum": str(d)[:10], "url": u, "beeld": True}
                     for a in bevestigde_artikelen(paren, rollen, v["set"], i) for c, u, t, p, o, d in
                     per_adres.get(vr.adres(a), [])]
        eigen = set(v["eigen"][MODUS])
        uit[i] = {"checks1": checks1, "checks2": met_beeld(checks1, bevestigd), "weg": weg, "eigen": eigen,
                  "eigen_urls": set().union(*(urls_per_groep.get(g, set()) for g in eigen))}
    return uit


def _draai(stukken: list[dict], pad: Path) -> None:  # pragma: no cover - live
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    configs = armen(config)
    client, sleutel = anthropic.Anthropic(max_retries=6), os.environ["BRAVE_API_KEY"]
    tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
    vragen = {v["id"]: v for v in _jsonl(VRAGEN) if v["set"] in ("N", "W")}
    paren = [p for p in _jsonl(PAREN) if p["set"] in ("N", "W")]
    db = _database(vr._conn(vr.PRODUCTIE), vragen, paren, vr._rolronde_rollen())
    weg = sum(d["weg"] for d in db.values())
    print(f"{len(db)} berichten met checks; {weg} checks niet meer in de database; arm 2 anders dan arm 1 bij "
          f"{sum(d['checks1'] != d['checks2'] for d in db.values())}", flush=True)
    slot, lokaal = threading.Lock(), threading.local()
    api.los_op(connect(str(WORTEL / "doublecheck.db")), config, "warm", None, None)  # het tekstmodel één keer laden

    def doe(s: dict) -> None:
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        conn = lokaal.conn
        with slot:
            if sum(r["kosten"] for r in _jsonl(pad)) > BUDGET - 0.15:  # ruimte voor de berichten die nog lopen
                return

        def snel(tekst: str) -> dict | None:
            return bc.snel_antwoord(api.los_op(conn, config, tekst, None, None).model_dump(), tabel, tekst,
                                    config.model_versions.text_embedding)

        d = db[s["id"]]
        uit = drie(s, d["checks1"], d["checks2"], configs, client, lambda q: zc.brave(q, sleutel), snel, sites,
                   d["eigen_urls"], d["eigen"])
        with slot:
            with pad.open("a", encoding="utf-8") as fh:
                for arm in ARMEN:
                    fh.write(json.dumps(uit[arm], ensure_ascii=False) + "\n")
            print(f"{s['id']} [{s['set']}]: " + ", ".join(
                f"arm {a} {uit[a]['oordeel']} ({uit[a]['kleur']})" for a in ARMEN)
                + f", {uit['0']['route']}, ${sum(uit[a]['kosten'] for a in ARMEN):.3f}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(doe, stukken))


def _lezen(stukken: list[dict], rijen: list[dict], labels: dict) -> None:  # pragma: no cover - op de bestanden
    per_id = {s["id"]: s for s in stukken}
    vragen = {v["id"]: v for v in _jsonl(VRAGEN) if v["set"] in ("N", "W")}
    for r in sorted(rijen, key=lambda r: (r["id"], r["arm"])):
        s = per_id[r["id"]]
        if r.get("kopie_van") or not telt_als_lezen(s, r) or _label(labels, r) is not None:
            continue
        eigen = [(g["redactie"], g["tekst"][:200], g["url"]) for g in s.get("geheugen") or []
                 if g.get("claim") in (s.get("eigen") or [])]
        print(f"\n=== {r['id']} [{s['set']}] arm {r['arm']}: {r['oordeel']} ({r['kleur']}), {r['route']}, gekozen "
              f"{r['gekozen']} (eigen {sorted(vragen[r['id']]['eigen'][MODUS])})\nTEKST: {s['tekst'][:400]}\n"
              f"UITLEG: {r['uitleg']}\nBRONNEN: "
              f"{[(b.get('site') or b.get('redactie'), b.get('band') or b.get('oordeel'), b.get('rol'), b.get('url')) for b in r['bronnen']]}"
              f"\nEIGEN CHECK: {eigen}")


def main() -> None:  # pragma: no cover - CLI, live
    import argparse

    from doublecheck.snelantwoord import percentiel

    parser = argparse.ArgumentParser(description="De lezer leest ook de checks uit de database (PLAN #32.28)")
    parser.add_argument("stap", choices=("draaien", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="draaien: alleen zoveel uit N en zoveel uit W")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "antwoorden.jsonl"
    stukken = _jsonl(SET)
    rijen = _jsonl(pad)
    per_arm = _per_arm(rijen)
    if args.stap == "draaien":
        # N eerst: raakt de grens het einde, dan is de run onvolledig en haalt hij de eisen niet
        nog = [s for s in sorted(stukken, key=lambda s: s["set"] != "N") if s["id"] not in per_arm["2"]]
        if args.proef:
            nog = [s for deel in ("N", "W") for s in [x for x in nog if x["set"] == deel][: args.proef]]
        _draai(nog, pad)
        print(f"samen ${sum(r['kosten'] for r in _jsonl(pad)):.2f} van ${BUDGET:.2f}")
        return
    labels = lees_labels()
    if args.stap == "lezen":
        _lezen(stukken, rijen, labels)
        return
    uit = telling(stukken, per_arm, labels)
    for arm in ARMEN:
        tijden = [r["seconden"] for r in rijen if r["arm"] == arm and r["route"] == "zoeken" and not r.get("kopie_van")]
        uit[arm]["tijd"] = {"p50": percentiel(tijden, .5), "p95": percentiel(tijden, .95)} if tijden else {}
        uit[arm]["kosten"] = round(sum(r["kosten"] for r in rijen if r["arm"] == arm), 2)
    uit["kosten"] = round(sum(r["kosten"] for r in rijen), 2)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
