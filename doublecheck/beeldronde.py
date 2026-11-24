"""Het beeld bij screenshots, één ronde (PLAN #32.6b).

Mag het beeld, met toestemming, naar het model (B43)? Dezelfde vraag v4 met het geheugen, het web, de herkansing
en de feitenstap, in twee armen: *zonder* beeld (de gelezen tekst, zoals nu) en *met* het beeld vóór dezelfde
vraag. Op N, de 58 nieuwe echte screenshots van bekend nepnieuws uit P4 (geheugen uit "beweringen eerst"), en W,
de 61 echte foto's die M4FC *waar* noemt, met hun ware bewering als bijschrift. Via de Batch API op openbare
beelden; het beeld alleen in het geheugen (B35).

    python -m doublecheck.beeldronde set --deel N
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldronde set --deel W
    python -m doublecheck.beeldronde indienen [--proef N]|herkansing|ophalen|lezen|tellen
"""

from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck.plafond import media_soort

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "beeldronde"
LABELS = WORTEL / "docs" / "steekproeven" / "32.6b-beeld.json"
BUDGET = 7.0  # PO 2026-10-28: "het beeld bij screenshots (~$7)"
ARMEN = ("zonder", "met")
SCHATTING = {"machine": 0.022, "feit": 0.0015, "herkansing": 0.025}
BEWEZEN = ("bewijst", "bewijst via factcheck")
WINST, HOOGSTENS_W = 0.10, 1


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


def met_beeld(params: dict, data: bytes) -> dict:
    """Dezelfde vraag, met het beeld ervoor; verder verandert er niets."""
    tekst = params["messages"][0]["content"]
    blokken = tekst if isinstance(tekst, list) else [{"type": "text", "text": tekst}]
    beeld = {"type": "image", "source": {"type": "base64", "media_type": media_soort(data),
                                         "data": base64.b64encode(data).decode()}}
    return {**params, "messages": [{"role": "user", "content": [beeld, *blokken]}]}


def _aandeel(d: dict, veld: str) -> float:
    return d.get(veld, 0) / d["n"] if d.get("n") else 0.0


def telling(stukken: list[dict], per_arm: dict[str, dict[str, dict]], labels: dict[tuple[str, str], str]) -> dict:
    """Per arm: bij N rood met bewijs (de eigen check, of een andere bron die gelezen is als bewijs) en groen;
    bij W onterecht rood. Weigert zolang een rood met een andere bron, een groen bij N of een rood bij W geen
    label heeft."""
    uit, open_ = {}, []
    for arm, uitkomsten in per_arm.items():
        n, w = Counter(), Counter()
        for s in stukken:
            u = uitkomsten.get(s["id"])
            if u is None:
                continue
            kleur = bc.kleur(u["stand"], u["oordeel"])
            label = labels.get((s["id"], arm))
            d = n if s["set"] == "N" else w
            d["n"] += 1
            d[kleur or "geen kleur"] += 1
            if s["set"] == "N" and kleur == "rood":
                if u["eigen_bewijs"]:
                    d["rood met bewijs"] += 1
                    d["met de eigen check"] += 1
                elif u["bronnen"]:
                    if label is None:
                        open_.append(f"{s['id']} {arm} rood")
                    d["rood met bewijs"] += label in BEWEZEN
                else:
                    d["rood zonder bron"] += 1
            elif s["set"] == "N" and kleur == "groen" and label is None:
                open_.append(f"{s['id']} {arm} groen")
            elif s["set"] == "W" and kleur == "rood":
                if label is None:
                    open_.append(f"{s['id']} {arm} rood")
                d["onterecht rood"] += label == "vals"
        uit[arm] = {"N": dict(n), "W": dict(w)}
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    zonder, met = uit.get("zonder", {"N": {}, "W": {}}), uit.get("met", {"N": {}, "W": {}})
    uit["eisen"] = {
        "N: met beeld minstens 10 punten meer rood met bewijs":
            _aandeel(met["N"], "rood met bewijs") - _aandeel(zonder["N"], "rood met bewijs") >= WINST,
        "W: met beeld niet meer onterecht rood dan zonder":
            met["W"].get("onterecht rood", 0) <= zonder["W"].get("onterecht rood", 0),
        "W: hoogstens 1 onterecht rood met beeld": met["W"].get("onterecht rood", 0) <= HOOGSTENS_W}
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def lees_labels() -> dict[tuple[str, str], str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {(r["id"], r["arm"]): r["label"] for r in d.get("oordelen", [])}


def _maak_set(config, deel: str) -> list[dict]:  # pragma: no cover - met de OCR, het model en de database
    """N kan meteen (het geheugen van "beweringen eerst" is er al); W leest de database."""
    from doublecheck import beeldzoeken as bz
    from doublecheck import betatoets as t
    from doublecheck.plafond import _beeld
    from doublecheck.storage import connect

    uit = [s for s in t._jsonl(UIT / "set.jsonl") if s["set"] != deel]
    if deel == "N":
        geheugen = {r["id"]: r["nieuw"] for r in t._jsonl(WORTEL / "data" / "beweringen" / "geheugen.jsonl")}
        uit += [{"id": s["id"], "set": "N", "tekst": s["tekst"], "beeld": s["beeld"], "datum": s.get("datum"),
                 "eigen": s.get("eigen"), "kandidaten": s["kandidaten"], "geheugen": geheugen[s["id"]]}
                for s in t._jsonl(WORTEL / "data" / "beweringen" / "set.jsonl") if s["set"] == "N"]
        t._schrijf(UIT / "set.jsonl", uit)
        return uit
    conn = connect(str(WORTEL / "doublecheck.db"))
    m4fc = json.loads(bz.M4FC_JSON.read_text(encoding="utf-8"))
    for i, s in enumerate(bz.ware_stukken(m4fc)):
        bericht = bc.bericht_uit(s["tekst"], _beeld(s["beeld"]), config.ocr)
        v = bc.voorbereiden(conn, config, bericht, client=None, screenshot=False)
        uit.append({"id": s["id"], "set": "W", "tekst": v["tekst"], "beeld": s["beeld"], "datum": s.get("datum"),
                    "eigen": None, "kandidaten": v["kandidaten"], "geheugen": v["geheugen"]})
        print(f"\rW {i + 1}", end="", flush=True)
    print()
    t._schrijf(UIT / "set.jsonl", uit)
    return uit


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    import anthropic

    from doublecheck import betatoets as t
    from doublecheck import machinevraag as v
    from doublecheck.config import load_config
    from doublecheck.plafond import _beeld
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="Het beeld bij screenshots, één ronde (PLAN #32.6b)")
    parser.add_argument("stap", choices=("set", "indienen", "herkansing", "ophalen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0)
    parser.add_argument("--deel", choices=("N", "W"), default="N")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    config = load_config(None)
    if args.stap == "set":
        uit = _maak_set(config, args.deel)
        print(Counter(s["set"] for s in uit))
        return
    stukken = t._jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    per_bid = {t.batch_id(s["id"]): s for s in stukken}
    batches = t._jsonl(UIT / "batches.jsonl")
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    tabel = bc.ijktabel(config)
    ingediend = {i for b in batches for i in b["ids"]}

    def vraag(s: dict, arm: str) -> dict:
        stuk = {"id": s["id"], "soort": "tekst", "tekst": s["tekst"], "datum": s.get("datum")}
        params = v.verzoek(stuk, s["geheugen"], "a", [], "sonnet", config.berichtcontrole.vraag)["params"]
        return met_beeld(params, _beeld(s["beeld"])) if arm == "met" else params

    def uitgegeven() -> float:
        return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in batches)

    if args.stap in ("indienen", "herkansing"):
        laad_sleutel()
        client = anthropic.Anthropic()
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            zinnen = bc.feitzinnen()
            nog = [s for s in stukken if f"m-zonder-{t.batch_id(s['id'])}" not in ingediend][: args.proef or None]
            for s in nog:
                b = t.batch_id(s["id"])
                for arm in ARMEN:
                    verzoeken.append({"custom_id": f"m-{arm}-{b}", "params": vraag(s, arm)})
                    geschat += SCHATTING["machine"]
                for k in ("A", "B") if s["kandidaten"] else ():  # de feitenstap leest alleen de tekst: één keer
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{b}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        else:
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                cid = f"h-{r.get('arm')}-{t.batch_id(r['id'])}"
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and cid not in ingediend:
                    verzoeken.append({"custom_id": cid, "params": bc.met_herkansing(vraag(per_id[r["id"]], r["arm"]), zin)})
                    geschat += SCHATTING["herkansing"]
        if not verzoeken:
            raise SystemExit("niets in te dienen")
        if uitgegeven() + geschat > BUDGET:
            raise Weigering(f"${uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        batch = client.messages.batches.create(requests=verzoeken)
        batches.append({"id": batch.id, "stap": args.stap, "schatting": round(geschat, 3),
                        "ids": [r["custom_id"] for r in verzoeken]})
        t._schrijf(UIT / "batches.jsonl", batches)
        print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    if args.stap == "ophalen":
        laad_sleutel()
        client = anthropic.Anthropic()
        zinnen = bc.feitzinnen()
        for b in batches:
            if b.get("werkelijk") is not None or client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                msg = r.result.message
                if r.custom_id.startswith("f-"):
                    stuk, sleutel = r.custom_id[2:].rsplit("__", 1)
                    s = per_bid[stuk]
                    rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel, "arm": None, **bc.feitantwoord(
                        msg, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel, zinnen, config)[1])}
                else:
                    kort, arm, rest = r.custom_id.split("-", 2)
                    s = per_bid[rest]
                    rij = {"soort": "machine" if kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                           "arm": arm, **bc.machineantwoord(msg, s["geheugen"])}
                rij["kosten"] = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
                werkelijk += rij["kosten"]
                antwoorden.append(rij)
            b["werkelijk"] = round(werkelijk, 4)
        t._schrijf(UIT / "antwoorden.jsonl", antwoorden)
        t._schrijf(UIT / "batches.jsonl", batches)
        print(Counter((r["soort"], r.get("arm")) for r in antwoorden), f"\nherkansing nodig: "
              f"{sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}; "
              f"uitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    feiten = [r for r in antwoorden if r["soort"] == "feit"]
    per_arm = {}
    for arm in ARMEN:
        eigen = [r for r in antwoorden if r.get("arm") == arm] + feiten
        u = t.uitkomsten_van(stukken, eigen, tabel)
        per_arm[arm] = {i: {**x, "eigen_bewijs": t._eigen_bewijs(per_id[i], x)} for i, x in u.items()}
    labels = lees_labels()
    if args.stap == "lezen":
        for arm in ARMEN:
            for s in stukken:
                u = per_arm[arm].get(s["id"])
                if u is None or (s["id"], arm) in labels:
                    continue
                kleur = bc.kleur(u["stand"], u["oordeel"])
                lezen = (s["set"] == "N" and kleur == "rood" and not u["eigen_bewijs"] and u["bronnen"]) or \
                        (s["set"] == "N" and kleur == "groen") or (s["set"] == "W" and kleur == "rood")
                if lezen:
                    print(f"\n=== {s['id']} [{s['set']}] {arm}: {u['oordeel']} ({kleur})\nTEKST: {s['tekst'][:300]}\n"
                          f"BEWERING: {u.get('bewering')}\nUITLEG: {(u.get('uitleg') or '')[:500]}\n"
                          f"BRONNEN: {[(b.get('soort'), b.get('url'), (b.get('citaat') or '')[:150]) for b in u['bronnen'][:4]]}")
        return
    uit = telling(stukken, per_arm, labels)
    uit["kosten"] = round(uitgegeven(), 2)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
