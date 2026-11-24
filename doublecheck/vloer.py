"""De voormeting voor de vloer (PLAN #32.0f, na P9; BENCHMARK §168).

In P9 (R3) bleef Factiz bij duidelijke onzin onder het kale model: zonder bron zegt
de machine *onzeker* of *let op* ("Barack Obama … weighed 50 pounds at birth"),
want vraag v4 laat *klopt niet* alleen toe met een check of een geciteerde bron.
Een model zonder zoeken had die zinnen wel goed.

Deze voormeting stelt een korte vraag zonder zoeken (`vloer-v1`, twee sleutels met
een andere formulering) aan Haiku 5.5, op alle eerdere berichten waar de vastgezette
machine (vraag v4) zonder bron *onzeker* of *let op* zei, ware en onware. Hoe vaak
noemt hij een waar bericht "duidelijk onwaar" (vals alarm), en hoeveel onware vangt
hij? Daarnaast de drie missers van R3. Offline, op openbare data, via de Batch API;
het product verandert niet.

    python -m doublecheck.vloer pool
    python -m doublecheck.vloer indienen [--proef 10]|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
from pathlib import Path

from doublecheck import betatoets as bt
from doublecheck.vloervraag import (  # noqa: F401 - verhuisd naar de kern (PLAN #32.7c)
    DUIDELIJK,
    MODEL,
    NIET,
    SLEUTELS,
    VRAGEN,
    _SCHEMA,
    lees_oordeel,
    verzoek,
)

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "vloer"
LABELS = WORTEL / "docs" / "steekproeven" / "32.0f-vloer.json"
BUDGET = 2.0  # PO 2026-10-28: "grens $2"
VERSIE = "vloer-v1"
SCHATTING = 0.0003  # per vraag via de Batch API, ruim
LABELS_POOL = ("waar", "onwaar", "misleidend")
# Hoogstens een derde van wat B45 toestaat (1 op 100): de rondes gebruiken er al een deel van.
PER_VALS_ALARM = 300
R3_MISSERS = ("weighed 50 pounds at birth", "protect about 97 to 99 percent of vaccinated people against measles",
              "on the planet Mars")


class Weigering(RuntimeError):
    pass


def zonder_bron(antwoord: dict) -> bool:
    """De machine twijfelt en heeft niets om naar te wijzen: het geval van de vloer."""
    return antwoord["oordeel"] in ("onzeker", "let op") and not antwoord["bronnen"]


def _gewoon(tekst: str) -> str:
    return " ".join(tekst.lower().split())


def ontdubbel(rijen: list[dict]) -> list[dict]:
    """Eén keer per bericht (op tekst), alleen waar, onwaar of misleidend; het id draagt de ronde."""
    gezien, uit = set(), []
    for r in rijen:
        sleutel = _gewoon(r["tekst"])
        if r["label"] not in LABELS_POOL or not sleutel or sleutel in gezien:
            continue
        gezien.add(sleutel)
        uit.append({**r, "id": f"{r['bron']}:{r['id']}"})
    return uit


def telling(pool: list[dict], antwoorden: dict[tuple[str, str], str], labels: dict[str, str],
            waar_in_rondes: int) -> dict:
    """Per label hoe vaak A, B en beide sleutels "clearly false" zeiden; elk vals alarm (beide sleutels bij een waar
    bericht) moet gelezen zijn: alleen een fout in de set telt niet. Weigert zolang er een open is."""
    uit: dict = {}
    for s in pool:
        if not all((s["id"], k) in antwoorden for k in SLEUTELS):
            continue
        groep = "missers van R3" if s.get("r3") else s["label"]
        d = uit.setdefault(groep, {"n": 0, "A": 0, "B": 0, "beide": 0})
        d["n"] += 1
        ja = [antwoorden[(s["id"], k)] == DUIDELIJK for k in SLEUTELS]
        d["A"] += ja[0]
        d["B"] += ja[1]
        d["beide"] += all(ja)
        if all(ja) and groep == "waar":
            if s["id"] not in labels:
                raise Weigering(f"{s['id']} is een vals alarm zonder label in {LABELS.name}; eerst lezen")
            d["vals alarm"] = d.get("vals alarm", 0) + (labels[s["id"]] == "vals")
            d["set fout"] = d.get("set fout", 0) + (labels[s["id"]] == "set fout")
    w = uit.setdefault("waar", {"n": 0, "A": 0, "B": 0, "beide": 0})
    w.setdefault("vals alarm", 0)
    w.setdefault("set fout", 0)
    r3 = uit.get("missers van R3", {"beide": 0})
    uit["ware berichten in de rondes"] = waar_in_rondes
    uit["eisen"] = {"hoogstens 1 vals alarm per 300 ware berichten in de rondes":
                        w["vals alarm"] <= waar_in_rondes / PER_VALS_ALARM,
                    "minstens 2 van de 3 missers van R3 gevangen": r3["beide"] >= 2}
    return uit


# --- de rondes, de batch en de CLI ----------------------------------------------------------------

def _laatste(antwoorden: list[dict], model: str | None = None) -> dict[str, dict]:
    """Per bericht het laatste oordeel van de machine: na een herkansing dat van de herkansing."""
    uit: dict[str, dict] = {}
    for r in antwoorden:
        if model and r.get("model") not in (model, None):
            continue
        if r.get("soort") in (None, "machine") and r["id"] not in uit:
            uit[r["id"]] = r
    for r in antwoorden:
        if r.get("soort") == "herkansing" and (not model or r.get("model") == model):
            uit[r["id"]] = r
    return uit


def rondes(alle: bool = False) -> tuple[list[dict], int]:  # pragma: no cover - op de bestanden van de rondes
    """De berichten van de rondes met vraag v4 waar de machine zonder bron twijfelde (met `alle`: elk bericht met
    een oordeel van de machine), en hoeveel ware berichten die rondes samen hadden (één keer per tekst)."""
    from doublecheck import verificatie as v

    def data(naam: str) -> tuple[list[dict], list[dict]]:
        return bt._jsonl(WORTEL / "data" / naam / "set.jsonl"), bt._jsonl(WORTEL / "data" / naam / "antwoorden.jsonl")

    bronnen: list[tuple[str, list[dict], dict[str, dict], object]] = []
    for naam in ("route", "fundament", "betatoets", "herstel"):
        stukken, antw = data(naam)
        bronnen.append((naam, stukken, _laatste(antw), lambda s: s.get("label")))
    stukken, antw = data("gebruikerstoets")
    bronnen.append(("gebruikerstoets", stukken, _laatste([r for r in antw if r.get("soort") in ("machine", "herkansing")]),
                    lambda s: (s.get("verwacht") or {}).get("inhoud")))
    stukken, antw = data("echtevorm")
    bronnen.append(("echtevorm", stukken, _laatste(antw), lambda s: "onwaar"))
    stukken, antw = data("tegenspeler")
    bronnen.append(("tegenspeler", stukken, _laatste(antw), lambda s: "satire" if s["deel"] == "S" else "onwaar"))
    mp = bt._jsonl(WORTEL / "data" / "modelpoort" / "set.jsonl") + bt._jsonl(WORTEL / "data" / "modelpoort" / "r.jsonl")
    bronnen.append(("modelpoort", mp, _laatste(bt._jsonl(WORTEL / "data" / "modelpoort" / "antwoorden.jsonl"), "sonnet"),
                    lambda s: s.get("label")))
    for ronde in (4, 7):
        stukken = [s for s in v.gekozen_stukken(ronde) if s.get("tekst") and s.get("soort") != "beeld"]
        antw = bt._jsonl(v.RONDES[ronde]["map"] / "sonnet" / "antwoorden.jsonl")
        for omst in sorted({r["omstandigheid"] for r in antw} - {"k"}):
            per = {r["id"]: r for r in antw if r["omstandigheid"] == omst}
            bronnen.append((f"verificatie-{ronde}{omst}", stukken, per, lambda s: s.get("label")))
    rijen, ware = [], set()
    for naam, stukken, per, label_van in bronnen:
        for s in stukken:
            a = per.get(s["id"])
            label = label_van(s)
            if a is None or not s.get("tekst"):
                continue
            if label == "waar":
                ware.add(_gewoon(s["tekst"]))
            if alle or zonder_bron(a):
                rijen.append({"bron": naam, "id": s["id"], "tekst": s["tekst"], "label": label, "helft": s.get("helft"),
                              "oordeel": a["oordeel"]})
    if alle:
        return ontdubbel(rijen), len(ware)
    r3 = [s for s in mp if s.get("set") == "R3" and any(m in s["tekst"] for m in R3_MISSERS)]
    pool = ontdubbel(rijen) + [{"bron": "R3", "id": f"r3vloer:{s['id']}", "tekst": s["tekst"], "label": "onwaar",
                                "helft": "toets", "r3": True} for s in r3]
    return pool, len(ware)


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in bt._jsonl(UIT / "batches.jsonl"))


def _labels() -> dict[str, str]:
    return json.loads(LABELS.read_text(encoding="utf-8")).get("valse alarmen", {}) if LABELS.exists() else {}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(description="De voormeting voor de vloer (PLAN #32.0f)")
    parser.add_argument("stap", choices=("pool", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "pool":
        pool, ware = rondes()
        bt._schrijf(UIT / "pool.jsonl", pool)
        (UIT / "meta.json").write_text(json.dumps({"ware berichten in de rondes": ware}), encoding="utf-8")
        print(f"{len(pool)} berichten, {ware} ware berichten in de rondes;",
              dict(Counter(s["label"] if not s.get("r3") else "R3" for s in pool)),
              dict(Counter(s["bron"].split("-")[0] for s in pool)))
        return
    pool = bt._jsonl(UIT / "pool.jsonl")
    antwoorden = {(r["id"], r["sleutel"]): r for r in bt._jsonl(UIT / "antwoorden.jsonl")}
    if args.stap in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.config import load_config
        from doublecheck.leraar import MODELLEN
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        batches = bt._jsonl(UIT / "batches.jsonl")
        per_bid = {f"{k}-{bt.batch_id(s['id'])}": (s, k) for s in pool for k in SLEUTELS}
        if args.stap == "indienen":
            al = {i for b in batches for i in b["ids"]}
            keuze = pool[: args.proef] if args.proef else pool
            verzoeken = [{"custom_id": f"{k}-{bt.batch_id(s['id'])}", "params": verzoek(s["tekst"], k, load_config(None))}
                         for s in keuze for k in SLEUTELS if f"{k}-{bt.batch_id(s['id'])}" not in al]
            geschat = len(verzoeken) * SCHATTING
            if not verzoeken or al_uitgegeven() + geschat > BUDGET:
                raise Weigering(f"{len(verzoeken)} vragen: ${al_uitgegeven():.2f} plus ${geschat:.2f} tegen ${BUDGET:.2f}")
            batch = client.messages.batches.create(requests=verzoeken)
            batches.append({"id": batch.id, "schatting": round(geschat, 4), "ids": [r["custom_id"] for r in verzoeken]})
            bt._schrijf(UIT / "batches.jsonl", batches)
            print(f"batch {batch.id}: {len(verzoeken)} vragen, geschat ${geschat:.3f}; samen ${al_uitgegeven():.3f}")
            return
        rijen = list(antwoorden.values())
        prijs = MODELLEN[MODEL]
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"{b['id']} loopt nog")
                continue
            kosten = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                msg = r.result.message
                kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
                s, k = per_bid[r.custom_id]
                tekst = "".join(getattr(x, "text", "") or "" for x in msg.content)
                rijen.append({"id": s["id"], "sleutel": k, "oordeel": lees_oordeel(tekst), "tekst": tekst})
            b["werkelijk"] = round(kosten, 4)
        bt._schrijf(UIT / "antwoorden.jsonl", rijen)
        bt._schrijf(UIT / "batches.jsonl", batches)
        print(f"{len(rijen)} antwoorden; samen ${al_uitgegeven():.3f}")
        return
    oordelen = {sleutel: r["oordeel"] for sleutel, r in antwoorden.items()}
    labels = _labels()
    if args.stap == "lezen":
        for s in pool:
            if (s["label"] == "waar" and not s.get("r3") and s["id"] not in labels
                    and all(oordelen.get((s["id"], k)) == DUIDELIJK for k in SLEUTELS)):
                print(f"=== {s['id']} [{s['label']}, {s.get('helft')}]\n{s['tekst'][:600]}")
                for k in SLEUTELS:
                    print(f"  {k}: {antwoorden[(s['id'], k)]['tekst'][:300]}")
        return
    meta = json.loads((UIT / "meta.json").read_text(encoding="utf-8"))
    uit = telling(pool, oordelen, labels, meta["ware berichten in de rondes"])
    uit["uitgegeven"] = round(al_uitgegeven(), 4)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
