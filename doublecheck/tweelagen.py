"""Het antwoord in twee lagen, gemeten op verse berichten (PLAN #32.13).

`lezer-v4` door dezelfde functies als `/check`: de bewering met haar kleur, het onderliggende feit dat de resultaten
bevestigen (*wat klopt*), en hoe het echt zit (*wat er echt gebeurde*). Eerst op de 18 gevallen die de PO nakeek
(de ontwikkelcheck, geen toets), daarna op berichten die nooit in een set zaten:
- O'': 100 Engelse claims met een onware of misleidende factcheck sinds 1 april 2026; kring 1 uit en de resultaten
  van IFCN-factcheckers weggelaten, zoals O en O';
- W'': 40 ware berichten uit Portal:Current events van 1 tot en met 19 oktober 2026 die niet in W' zaten; kring 1 aan.
Elk groen bij O'', elk rood of oranje bij W'', en elke getoonde zin wordt gelezen
(`docs/steekproeven/32.13-tweelagen.json`).

    python -m doublecheck.tweelagen set
    python -m doublecheck.hittewacht -- python -m doublecheck.tweelagen ontwikkel|draaien
    python -m doublecheck.tweelagen lezen|tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from doublecheck import controle500 as c5
from doublecheck import versetoets as vt

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "tweelagen"
LABELS = WORTEL / "docs" / "steekproeven" / "32.13-tweelagen.json"
BUDGET = 2.0  # PO 2026-10-29: "meet op verse berichten binnen ~$2"; Sonnet en Brave samen, Brave tegen de lijstprijs
LEZER = "lezer-v4"
ZAAD = 3213
N_ONWAAR, N_WAAR = 100, 40
VANAF = "2026-04-01"  # sinds 1 juli waren er nog maar 3 ongezien (#32.12 nam er 100 van de 103)
ZINNEN = {"feit": "wat_klopt", "anders": "wat_er_gebeurde"}  # het label van een zin heeft de sleutel <id>#<soort>
Weigering = c5.Weigering


def nieuwe_zinnen(zinnen: list[tuple[int, str]], gezien: set[str]) -> list[tuple[int, str]]:
    """De ware zinnen voor W'': elke zin één keer, en geen zin die al in een set zat."""
    uit, al = [], set(gezien)
    for dag, z in zinnen:
        z = z.strip()
        if z not in al:
            uit.append((dag, z))
            al.add(z)
    return uit


def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict[str, str]) -> dict:
    """De telling van #32.11 op W'' en O'', met per deel hoe vaak *wat klopt* en *wat er echt gebeurde* verschenen
    en hoe hun labels uitvielen (juist, vals, niet in de bronnen). Weigert ook zolang een getoonde zin geen label
    heeft; de eis: bij O'' hoogstens 1 bericht met een valse zin op de 100."""
    open_ = [f"{s['id']}#{soort}" for s in stukken for soort, veld in ZINNEN.items()
             if (antwoorden.get(s["id"]) or {}).get(veld) and f"{s['id']}#{soort}" not in labels]
    if open_:
        raise Weigering(f"{len(open_)} zinnen zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    uit = vt.telling(stukken, antwoorden, labels, bestand=LABELS.name)
    vals_o = streng_o = 0
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        d = uit[s["deel"]]
        d["wat klopt"] = d.get("wat klopt", 0) + bool(a.get("wat_klopt"))
        d["wat klopt met over_beeld"] = d.get("wat klopt met over_beeld", 0) + bool(a.get("wat_klopt")
                                                                                    and a.get("over_beeld"))
        d["wat er echt gebeurde"] = d.get("wat er echt gebeurde", 0) + bool(a.get("wat_er_gebeurde"))
        oordelen = [labels[f"{s['id']}#{soort}"] for soort, veld in ZINNEN.items() if a.get(veld)]
        for label in oordelen:
            d[f"zin {label}"] = d.get(f"zin {label}", 0) + 1
        vals_o += s["deel"] == "O" and "vals" in oordelen
        streng_o += s["deel"] == "O" and bool({"vals", "ander onderwerp"} & set(oordelen))
    n_o = uit.get("O", {}).get("n", 0)
    uit["eisen"]["getoonde zinnen: hoogstens 1 vals op 100"] = vals_o <= 0.01 * n_o
    # gemeld, geen eis: een ware zin over een andere gebeurtenis of een ander moment misleidt ook
    uit["eisen"]["streng, met 'ander onderwerp' als vals"] = streng_o <= 0.01 * n_o
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def lees_labels() -> dict[str, str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r["label"] for r in d.get("oordelen", [])}


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
    vrij = vt.ongezien([tuple(r) for r in rijen], vt._gezien())
    onwaar = [{**s, "id": "O2:" + s["claim"]} for s in rng.sample(vrij, min(N_ONWAAR, len(vrij)))]
    gezien_tekst = {r["tekst"] for pad in WORTEL.glob("data/*/set.jsonl") for r in c5._jsonl(pad) if r.get("tekst")}
    zinnen = nieuwe_zinnen([(dag, z) for dag in vt.DAGEN
                            for z in portal_zinnen(_wikitekst(f"Portal:Current events/2026 October {dag}"))
                            if 60 <= len(z) <= 300], gezien_tekst)
    waar = [{"id": f"W2:{dag}-{i}", "deel": "W", "tekst": z, "label": "waar", "datum": f"2026-10-{dag:02d}"}
            for i, (dag, z) in enumerate(rng.sample(zinnen, N_WAAR))]
    uit = waar + onwaar
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "set.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    print(f"{len(vrij)} ongeziene onware claims, {len(onwaar)} gekozen; {len(zinnen)} nieuwe ware zinnen, "
          f"{len(waar)} gekozen")
    return uit


def _ontwikkelstukken() -> list[dict]:  # pragma: no cover - op de sets van #32.11 en #32.12
    oud = c5.lees_labels()
    vers = vt.lees_labels()
    return ([s for s in c5.stukken() if s["id"] in oud]
            + [s for s in c5._jsonl(vt.UIT / "set.jsonl") if s["id"] in vers])


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
            if vt.uitgegeven(UIT) > BUDGET:
                return
        rij = c5._een(s, lokaal.conn, config, client, sleutel, tabel, sites)
        with slot:
            with pad.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            print(f"{s['id']} [{s['deel']}]: {rij['oordeel']} ({rij['kleur']}), feit {bool(rij.get('wat_klopt'))}, "
                  f"anders {bool(rij.get('wat_er_gebeurde'))}, {rij['seconden']} s", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(doe, [s for s in stukken if s["id"] not in gedaan]))


def _toon(r: dict, s: dict, vorig: dict | None = None) -> str:
    bronnen = {x["nr"]: x for x in r.get("resultaten", [])}
    regels = [f"=== {r['id']} [{s['deel']}, {s.get('redactie') or s.get('label')}: {s.get('oordeel', '')}] "
              f"{r['oordeel']} ({r['kleur']}), over_beeld {r.get('over_beeld')}"
              + (f"; eerder {vorig['oordeel']} ({vorig['kleur']})" if vorig else ""),
              f"BERICHT: {s['tekst'][:400]}", f"UITLEG: {r.get('uitleg')}",
              f"FEIT: {r.get('feit')!r} {r.get('feit_steunt')} -> getoond: {r.get('wat_klopt') is not None}",
              f"ANDERS: {r.get('anders')!r} -> getoond: {r.get('wat_er_gebeurde') is not None}"]
    for rol, nummers in (("steunt", r.get("steunt", [])), ("tegen", r.get("spreekt_tegen", [])),
                         ("feit", r.get("feit_steunt", []))):
        for n in nummers:
            if n in bronnen:
                b = bronnen[n]
                regels.append(f"  [{rol} {n}] {b['site']} ({b['band']}) {b['titel'][:90]} | {b.get('fragment', '')[:220]}")
    return "\n".join(regels)


def main() -> None:  # pragma: no cover - CLI, live
    import argparse

    parser = argparse.ArgumentParser(description="Het antwoord in twee lagen op verse berichten (PLAN #32.13)")
    parser.add_argument("stap", choices=("set", "ontwikkel", "draaien", "lezen", "tellen"))
    parser.add_argument("--alleen", default="", help="ontwikkel: alleen deze ids, na de ene bijstelling van de vraag")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "set":
        _maak_set()
        return
    if args.stap == "ontwikkel":
        stukken = _ontwikkelstukken()
        pad = UIT / ("bijgesteld.jsonl" if args.alleen else "ontwikkel.jsonl")
        if args.alleen:
            stukken = [s for s in stukken if s["id"] in set(args.alleen.split(","))]
        _draai(stukken, pad)
        vorig = {r["id"]: r for pad_ in (c5.UIT / "antwoorden.jsonl", vt.UIT / "antwoorden.jsonl")
                 for r in c5._jsonl(pad_)}
        per_id = {s["id"]: s for s in stukken}
        for r in c5._jsonl(pad):
            if r["id"] in per_id:
                print(_toon(r, per_id[r["id"]], vorig.get(r["id"])) + "\n")
        print(f"samen ${vt.uitgegeven(UIT):.2f}")
        return
    # de onware eerst: raakt de grens het einde, dan mist een paar ware, nooit het deel waar de eisen op liggen
    alle = sorted(c5._jsonl(UIT / "set.jsonl"), key=lambda s: s["deel"] != "O")
    pad = UIT / "antwoorden.jsonl"
    if args.stap == "draaien":
        _draai(alle, pad)
        print(f"samen ${vt.uitgegeven(UIT):.2f}")
        return
    antwoorden = {r["id"]: r for r in c5._jsonl(pad)}
    labels = lees_labels()
    if args.stap == "lezen":
        for s in alle:
            a = antwoorden.get(s["id"])
            if a is None:
                continue
            kleur_open = s["id"] not in labels and (
                (s["deel"] == "W" and a["kleur"] in c5.ALARM) or (s["deel"] == "O" and a["kleur"] == "groen"))
            zin_open = any(a.get(veld) and f"{s['id']}#{soort}" not in labels for soort, veld in ZINNEN.items())
            if kleur_open or zin_open:
                print(_toon(a, s) + "\n")
        return
    print(json.dumps(telling(alle, antwoorden, labels), ensure_ascii=False, indent=1))
    print(f"samen met de ontwikkelcheck ${vt.uitgegeven(UIT):.2f}")


if __name__ == "__main__":
    main()
