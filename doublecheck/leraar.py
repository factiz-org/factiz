"""De leraarladder (PLAN #31.2, E8.S2, B42).

Haiku, Sonnet en Opus krijgen dezelfde vaste vraag op de basisset (#31.1): is
dit nepnieuws of desinformatie? Antwoord `onwaar` of `geen-oordeel`, met één
zin reden. Nooit "waar": de machine zegt niet "waarschijnlijk waar" omdat ze
niets fouts vindt (B30). Wat telt, is naast de herkenning vooral hoe vaak een
model "onwaar" zegt bij iets waars (de basislijnval van §70): bij betrouwbaar
nieuws, ware checks en de kern, en bij gewone webtekst (die wordt gelezen).

Offline, op openbare data (B26); de leraar komt nooit in de dienst. Eerst een
proef van 50 per model; het budget (PO: tot $50) is een harde grens.

    python -m doublecheck.leraar plan
    python -m doublecheck.leraar indienen --model haiku|sonnet|opus [--proef 50]
    python -m doublecheck.leraar ophalen --model haiku|sonnet|opus
    python -m doublecheck.leraar lezen
    python -m doublecheck.leraar tellen --model haiku|sonnet|opus
"""

from __future__ import annotations

import base64
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from doublecheck.modellen import (  # noqa: F401 - verhuisd naar de kern (PLAN #32.7c)
    MODELLEN,
)

PROMPTVERSIE = "oordeel-v1"
BUDGET = 50.0  # PO 2026-10-23, voor de hele ladder
N_SONNET, N_OPUS = 6_000, 500
ZAAD = 3001
SYSTEEM = ("You help measure how well language models recognise false or misleading content, such as "
           "disinformation, hoaxes and debunked claims. Judge the content itself.")
VRAAG = ("Is this false or misleading news or misinformation? Answer \"onwaar\" if the main claim it makes is false "
         "or misleading, and \"geen-oordeel\" if it is accurate, if you cannot tell, or if it makes no checkable "
         "claim. Add one short sentence with your reason.")
_SCHEMA = {"type": "object",
           "properties": {"oordeel": {"type": "string", "enum": ["onwaar", "geen-oordeel"]},
                          "reden": {"type": "string"}},
           "required": ["oordeel", "reden"], "additionalProperties": False}
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "leraar"
LABELS = WORTEL / "docs" / "steekproeven" / "31.2-leraar.json"


class Weigering(Exception):
    """Tellen of indienen kan niet: een vlag zonder label, of boven het budget."""


def lees_oordeel(tekst: str) -> tuple[str, str | None]:
    """("onwaar" of "geen-oordeel", reden), of ("onleesbaar", None) bij een
    afgekapt antwoord of een antwoord buiten de twee."""
    try:
        antwoord = json.loads(tekst)
    except json.JSONDecodeError:
        return "onleesbaar", None
    oordeel = antwoord.get("oordeel")
    if oordeel not in ("onwaar", "geen-oordeel"):
        return "onleesbaar", None
    return oordeel, " ".join(str(antwoord.get("reden") or "").split())


def verzoek(stuk: dict, model: str, max_tokens: int = 1_000) -> dict:
    """Ruim `max_tokens`: het model denkt eerst, en dat telt mee (#30.12)."""
    if stuk.get("beeld"):
        pad = Path(stuk["beeld"])
        soort = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(pad.suffix.lower(), "image/jpeg")
        inhoud = [{"type": "image", "source": {"type": "base64", "media_type": soort,
                                               "data": base64.b64encode(pad.read_bytes()).decode()}},
                  {"type": "text", "text": VRAAG}]
    else:
        inhoud = [{"type": "text", "text": f"Content:\n{stuk['tekst']}\n\n{VRAAG}"}]
    return {"custom_id": stuk["id"],
            "params": {"model": MODELLEN[model]["id"], "max_tokens": max_tokens, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": inhoud}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def kosten(stukken: list[dict], model: str, uit_per_stuk: int = 250) -> float:
    """Een ruime schatting: tekst op vier tekens per token, een beeld 1.600."""
    vast = (len(SYSTEEM) + len(VRAAG)) // 4 + 20
    tokens = sum(vast + (1_600 if s.get("beeld") else len(s.get("tekst", "")) // 4 + 5) for s in stukken)
    m = MODELLEN[model]
    return (tokens * m["in"] + len(stukken) * uit_per_stuk * m["uit"]) / 1e6


def binnen_budget(geschat: float, al_uitgegeven: float, budget: float = BUDGET) -> None:
    if al_uitgegeven + geschat > budget:
        raise Weigering(f"geweigerd: ${al_uitgegeven:.2f} al ingediend plus ${geschat:.2f} is meer dan ${budget:.2f}")


def uitkomst(label: str, oordeel: str) -> str:
    if label == "onwaar":
        return "herkend" if oordeel == "onwaar" else "gemist"
    if label == "waar":
        return "valse vlag" if oordeel == "onwaar" else "goed"
    return "te lezen" if oordeel == "onwaar" else "goed"


def steekproef(stukken: list[dict], n: int, zaad: int = ZAAD) -> list[dict]:
    """Per laag (soort, label, helft) naar verhouding, binnen een laag
    willekeurig en telkens dezelfde; alle feiten en alle verse stukken
    altijd erbij (de kern en de verse toets moeten volledig zijn)."""
    altijd = [s for s in stukken if s["soort"] == "feit" or s["vers"]]
    gewoon = [s for s in stukken if not (s["soort"] == "feit" or s["vers"])]
    lagen: dict[tuple, list] = defaultdict(list)
    for s in gewoon:
        lagen[(s["soort"], s["label"], s["helft"])].append(s)
    rng = random.Random(zaad)
    gekozen = []
    for laag in sorted(lagen):
        groep = lagen[laag]
        gekozen += rng.sample(groep, min(len(groep), round(n * len(groep) / len(gewoon))))
    ids = {s["id"] for s in gekozen + altijd}
    return [s for s in stukken if s["id"] in ids]


def telling(stukken: list[dict], oordelen: dict[str, str], labels: dict[str, str]) -> dict:
    """Per helft: per soort en label herkend of vals gevlagd, de verse stukken,
    de valse vlaggen op alles wat waar is, de kern apart, en de webtekst
    (gelezen: terecht als de tekst zelf een ontkrachte bewering doet). Alleen
    stukken met een leesbaar oordeel tellen mee."""
    uit: dict = {}
    for s in stukken:
        oordeel = oordelen.get(s["id"])
        if oordeel not in ("onwaar", "geen-oordeel"):
            continue
        h = uit.setdefault(s["helft"], {"per soort en label": {}, "vers": {"n": 0, "herkend": 0},
                                        "valse vlag op waar": {"n": 0, "vlag": 0}, "kern": {"n": 0, "vlag": 0},
                                        "webtekst": {"n": 0, "vlag": 0, "terecht": 0}})
        u = uitkomst(s["label"], oordeel)
        if s["soort"] == "webtekst":
            h["webtekst"]["n"] += 1
            if u == "te lezen":
                label = labels.get(s["sleutel"])
                if label is None:
                    raise Weigering(f"geen label voor {s['sleutel']} in {LABELS.name}; eerst lezen")
                h["webtekst"]["vlag" if label == "vals" else "terecht"] += 1
            continue
        if s["label"] == "onwaar" and s["vers"]:
            h["vers"]["n"] += 1
            h["vers"]["herkend"] += u == "herkend"
            continue
        sleutel = f"{s['soort']} {s['label']}"
        if s["label"] == "onwaar":
            d = h["per soort en label"].setdefault(sleutel, {"n": 0, "herkend": 0})
            d["n"] += 1
            d["herkend"] += u == "herkend"
        else:
            d = h["per soort en label"].setdefault(sleutel, {"n": 0, "vlag": 0})
            d["n"] += 1
            d["vlag"] += u == "valse vlag"
            h["valse vlag op waar"]["n"] += 1
            h["valse vlag op waar"]["vlag"] += u == "valse vlag"
            if s["bron"] == "n3-kern":
                h["kern"]["n"] += 1
                h["kern"]["vlag"] += u == "valse vlag"
    return uit


# --- de batches ---------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    return [json.loads(r) for r in inhoud[:inhoud.rfind("\n") + 1].split("\n") if r]


def set_van(model: str, stukken: list[dict]) -> list[dict]:
    """Haiku de hele basisset, Sonnet een gelaagde steekproef, Opus een
    gelaagde steekproef uit die van Sonnet (PLAN #31.2)."""
    if model == "haiku":
        return stukken
    sonnet = steekproef(stukken, N_SONNET)
    return sonnet if model == "sonnet" else steekproef(sonnet, N_OPUS)


def oordelen(model: str) -> dict[str, str]:
    """Per stuk het laatste leesbare oordeel van dit model."""
    uit: dict[str, str] = {}
    for r in _jsonl(UIT / model / "antwoorden.jsonl"):
        if r["oordeel"] != "onleesbaar" or r["id"] not in uit:
            uit[r["id"]] = r["oordeel"]
    return uit


def al_ingediend() -> float:
    """Wat de hele ladder al kost: per batch de werkelijke kosten als die
    bekend zijn, anders de schatting."""
    return sum(max(b["schatting"], b.get("werkelijk", 0.0)) for m in MODELLEN for b in _jsonl(UIT / m / "batches.jsonl"))


def _lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    return {r["sleutel"]: r["label"] for r in json.loads(LABELS.read_text(encoding="utf-8"))["labels"]}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    from doublecheck import basisset
    from doublecheck.benchmark import upper_bound_95

    parser = argparse.ArgumentParser(description="De leraarladder (#31.2)")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("--model", choices=tuple(MODELLEN), default="haiku")
    parser.add_argument("--proef", type=int, default=0, help="indienen: alleen een proef van N, verspreid over de soorten")
    parser.add_argument("--opnieuw", action="store_true", help="indienen: alleen de onleesbare antwoorden")
    args = parser.parse_args()
    stukken = basisset.lees()
    if args.stap == "plan":
        for m in MODELLEN:
            s = set_van(m, stukken)
            print(f"{m}: {len(s)} stukken {dict(Counter(x['soort'] for x in s))}, naar schatting ${kosten(s, m):.2f}")
        print(f"al ingediend: ${al_ingediend():.2f} van ${BUDGET:.2f}")
        return
    if args.stap == "lezen":
        labels = _lees_labels()
        per_id = {s["id"]: s for s in stukken}
        open_ = {}
        for m in MODELLEN:
            redenen = {r["id"]: r.get("reden") for r in _jsonl(UIT / m / "antwoorden.jsonl")}
            for id_, o in oordelen(m).items():
                s = per_id[id_]
                if s["soort"] == "webtekst" and o == "onwaar" and s["sleutel"] not in labels:
                    open_.setdefault(s["sleutel"], (s, []))[1].append(f"{m}: {redenen.get(id_)}")
        for sleutel, (s, waarom) in open_.items():
            print(f"\n[{s['helft']} · {s['taal']}] {sleutel}\n  TEKST: {s['tekst'][:600]}")
            for w in waarom:
                print(f"  {w}")
        print(f"\n{len(open_)} te labelen in {LABELS}")
        return
    if args.stap == "tellen":
        uitslag = telling(set_van(args.model, stukken), oordelen(args.model), _lees_labels())
        for helft in ("ontwikkel", "toets"):
            h = uitslag.get(helft)
            if not h:
                continue
            print(f"\n{helft}:")
            for k, d in sorted(h["per soort en label"].items()):
                if "herkend" in d:
                    print(f"  {k:18} herkend {d['herkend']} van {d['n']} ({d['herkend'] / d['n']:.1%})")
                else:
                    print(f"  {k:18} valse vlag {d['vlag']} van {d['n']} (bovengrens {upper_bound_95(d['vlag'], d['n']):.2%})")
            for k in ("valse vlag op waar", "kern"):
                d = h[k]
                if d["n"]:
                    print(f"  {k:18} {d['vlag']} van {d['n']} (bovengrens {upper_bound_95(d['vlag'], d['n']):.2%})")
            w, v = h["webtekst"], h["vers"]
            if w["n"]:
                print(f"  webtekst           vals {w['vlag']} van {w['n']} (bovengrens {upper_bound_95(w['vlag'], w['n']):.2%}),"
                      f" terecht {w['terecht']}")
            if v["n"]:
                print(f"  vers (onwaar)      herkend {v['herkend']} van {v['n']} ({v['herkend'] / v['n']:.1%})")
        (UIT / args.model / "uitslag.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    map_ = UIT / args.model
    map_.mkdir(parents=True, exist_ok=True)
    batches, antwoorden = map_ / "batches.jsonl", map_ / "antwoorden.jsonl"
    if args.stap == "indienen":
        eigen = set_van(args.model, stukken)
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        if args.opnieuw:
            laatste = oordelen(args.model)
            kies = [s for s in eigen if laatste.get(s["id"]) == "onleesbaar"]
        else:
            nog = [s for s in eigen if s["id"] not in ingediend]
            if args.proef:
                per_soort: dict[str, list] = defaultdict(list)
                for s in nog:
                    per_soort[s["soort"]].append(s)
                kies = [s for groep in per_soort.values() for s in groep[: max(1, args.proef // len(per_soort))]]
            else:
                kies = nog
        if not kies:
            raise SystemExit("niets in te dienen")
        geschat = kosten(kies, args.model)
        binnen_budget(geschat, al_ingediend())
        batch = client.messages.batches.create(requests=[verzoek(s, args.model) for s in kies])
        with batches.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE, "schatting": round(geschat, 3),
                                "ids": [s["id"] for s in kies]}) + "\n")
        print(f"batch {batch.id}: {len(kies)} stukken, naar schatting ${geschat:.2f}; ladder samen ${al_ingediend():.2f}")
        return
    # ophalen, met de werkelijke kosten uit het tokengebruik
    klaar = {k for k, o in oordelen(args.model).items() if o != "onleesbaar"}
    m = MODELLEN[args.model]
    alle = _jsonl(batches)
    with antwoorden.open("a", encoding="utf-8") as uit:
        for b in alle:
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    oordeel, reden = "onleesbaar", None
                else:
                    msg = r.result.message
                    werkelijk += (msg.usage.input_tokens * m["in"] + msg.usage.output_tokens * m["uit"]) / 1e6
                    oordeel, reden = lees_oordeel(next((c.text for c in msg.content if c.type == "text"), "{}"))
                if r.custom_id in klaar:
                    continue
                uit.write(json.dumps({"id": r.custom_id, "oordeel": oordeel, "reden": reden, "model": m["id"],
                                      "prompt": PROMPTVERSIE}, ensure_ascii=False) + "\n")
                if oordeel != "onleesbaar":
                    klaar.add(r.custom_id)
            b["werkelijk"] = round(werkelijk, 4)
    batches.write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(f"{args.model}: {Counter(oordelen(args.model).values())}; werkelijk ${sum(b.get('werkelijk', 0) for b in alle):.2f};"
          f" ladder samen ${al_ingediend():.2f}")


if __name__ == "__main__":
    main()
