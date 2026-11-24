"""Waarom het nep is: is elke zin van de uitleg gedekt door een bron die de lezer noemde? (stap 7 van V1, eis 95%; PLAN
#32.56, PO 2026-11-07: "doen").

Op de antwoorden van een meting met `gezien` (wat de lezer per genoemde bron zag, `meting.wat_de_lezer_zag`): per antwoord
de zinnen van de uitleg, Haiku zegt per zin *gedekt*, *niet gedekt* of *geen feit*; elke *niet gedekt* wordt gelezen
(*wel gedekt* of *niet gedekt*) in `docs/steekproeven/<meetplan>-uitleg.json`, en `tellen` weigert zolang er een open is.

    python -m doublecheck.uitlegdekking <meetplan> vragen [--proef N]|lezen|tellen
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MODEL = "haiku"
EIS = 0.95
DEKKING = ("gedekt", "niet gedekt", "geen feit")
_EINDE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÝÄÖÜ0-9\"'„“(])")

SYSTEEM = ("You check whether each sentence of an explanation is supported by the sources the writer had. You do not judge "
           "whether the sentence is true in general, only whether these sources support it.")
VRAAG = """The explanation, sentence by sentence:
{zinnen}

What the writer saw of each source it named:
{bronnen}

For each sentence:
- "gedekt": every fact in it (who, what, when, where, numbers, what a source says) is stated or directly implied by one of
  these sources;
- "niet gedekt": it contains a fact that none of these sources states;
- "geen feit": it contains no factual claim (for example only a verdict like "Dit klopt niet." or "Dit klopt.").
A sentence that names a source ("Reuters meldt dat ...") is "gedekt" only if that source says it."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["zinnen"],
          "properties": {"zinnen": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["nr", "dekking"],
              "properties": {"nr": {"type": "integer"}, "dekking": {"type": "string", "enum": list(DEKKING)}}}}}}


class Weigering(Exception):
    """Tellen kan niet: een zin die *niet gedekt* heet, is nog niet gelezen."""


def zinnen(tekst: str) -> list[str]:
    """De zinnen van de uitleg, zoals de kern ze splitst (`zoekcontrole.zinnen`)."""
    from doublecheck.zoekcontrole import zinnen as kern_zinnen

    return kern_zinnen(tekst)


def verzoek(zinnen_: list[str], gezien: dict[str, str]) -> dict:
    from doublecheck.modellen import MODELLEN

    tekst = VRAAG.format(zinnen="\n".join(f"[{i}] {z}" for i, z in enumerate(zinnen_, 1)),
                         bronnen="\n".join(f"- {url}: {wat}" for url, wat in gezien.items()) or "(none)")
    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 1500, "system": SYSTEEM,
            "messages": [{"role": "user", "content": tekst}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}}


def lees(tekst: str, n: int) -> list[str]:
    """Per zin de dekking; een onleesbaar antwoord of nummer telt als *niet gedekt* (twijfel versoepelt nooit)."""
    uit = ["niet gedekt"] * n
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return uit
    for r in d.get("zinnen", []) if isinstance(d, dict) else []:
        if isinstance(r, dict) and type(r.get("nr")) is int and 1 <= r["nr"] <= n and r.get("dekking") in DEKKING:
            uit[r["nr"] - 1] = r["dekking"]
    return uit


def telling(rijen: list[dict], labels: dict[str, str]) -> dict:
    """De dekking over alle feitelijke zinnen; een *niet gedekt* telt pas na het lezen (sleutel `<id>#<nr>`): *wel
    gedekt* (de nakijker zat ernaast) of *niet gedekt*."""
    open_ = [f"{r['id']}#{i}" for r in rijen for i, d in enumerate(r["dekking"], 1)
             if d == "niet gedekt" and labels.get(f"{r['id']}#{i}") not in ("wel gedekt", "niet gedekt")]
    if open_:
        raise Weigering(f"{len(open_)} zinnen zonder label, bijvoorbeeld {open_[0]}")
    n = sum(len(r["dekking"]) for r in rijen)
    geen = sum(d == "geen feit" for r in rijen for d in r["dekking"])
    gedekt = sum(d == "gedekt" or (d == "niet gedekt" and labels[f"{r['id']}#{i}"] == "wel gedekt")
                 for r in rijen for i, d in enumerate(r["dekking"], 1))
    feitelijk = n - geen
    dekking = round(gedekt / feitelijk, 4) if feitelijk else 0.0
    return {"zinnen": n, "geen feit": geen, "feitelijk": feitelijk, "gedekt": gedekt, "niet gedekt": feitelijk - gedekt,
            "dekking": dekking, "eis (95%)": dekking >= EIS}


# --- de bestanden en het model -----------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _paden(meetplan: str) -> tuple[Path, Path, Path]:
    plan = json.loads((WORTEL / "docs" / "meetplannen" / f"{meetplan}.json").read_text(encoding="utf-8"))
    map_ = WORTEL / plan["map"]
    return map_ / "antwoorden.jsonl", map_ / "uitleg.jsonl", WORTEL / "docs" / "steekproeven" / f"{meetplan}-uitleg.json"


def _vragen(meetplan: str, proef: int | None) -> None:  # pragma: no cover - de Batch API op openbare antwoorden
    import anthropic

    from doublecheck.berichtcontrole import gebruik_uit
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.uitkomsten import batch_met_grens
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    antwoorden, uit, _ = _paden(meetplan)
    klaar = {r["id"] for r in _jsonl(uit)}
    werk = [a for a in _jsonl(antwoorden) if a.get("uitleg") and "gezien" in a and a["id"] not in klaar][:proef or None]
    nummers = {f"u{i:04d}": a for i, a in enumerate(werk)}
    gelezen = {}
    batch_met_grens(anthropic.Anthropic(max_retries=6), {c: verzoek(zinnen(a["uitleg"]), a["gezien"])
                                                         for c, a in nummers.items()},
                    gelezen.update, aangemeld=lambda b, ids: None, afgemeld=lambda b: None)
    nieuw = []
    for c, msg in gelezen.items():
        a = nummers[c]
        z = zinnen(a["uitleg"])
        nieuw.append({"id": a["id"], "set": a["set"], "zinnen": z,
                      "dekking": lees("".join(getattr(b, "text", "") or "" for b in msg.content), len(z)),
                      "kosten": round(kosten_batch(gebruik_uit(msg), MODEL), 6)})
    with uit.open("a", encoding="utf-8") as f:
        for r in nieuw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(nieuw)} uitleggen nagekeken, ${sum(r['kosten'] for r in nieuw):.3f}")


def _labels(pad: Path) -> dict[str, str]:
    d = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}
    return {r["id"]: r["label"] for r in d.get("labels", [])}


def _lezen(meetplan: str) -> None:  # pragma: no cover - op de bestanden
    antwoorden, uit, labels = _paden(meetplan)
    gezien = {a["id"]: a.get("gezien", {}) for a in _jsonl(antwoorden)}
    al = _labels(labels)
    open_ = [{"sleutel": f"{r['id']}#{i}", "zin": z, "bronnen": gezien.get(r["id"], {})}
             for r in _jsonl(uit) for i, (z, d) in enumerate(zip(r["zinnen"], r["dekking"]), 1)
             if d == "niet gedekt" and f"{r['id']}#{i}" not in al]
    doel = uit.with_name("uitleg-te-lezen.jsonl")
    doel.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in open_), encoding="utf-8")
    print(f"{len(open_)} zinnen te lezen in {doel}")


def _tellen(meetplan: str) -> None:  # pragma: no cover - op de bestanden
    _, uit, labels = _paden(meetplan)
    print(json.dumps(telling(_jsonl(uit), _labels(labels)), ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Is elke zin van de uitleg gedekt door een bron? (PLAN #32.56)")
    parser.add_argument("meetplan")
    parser.add_argument("stap", choices=("vragen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    {"vragen": lambda: _vragen(args.meetplan, args.proef), "lezen": lambda: _lezen(args.meetplan),
     "tellen": lambda: _tellen(args.meetplan)}[args.stap]()


if __name__ == "__main__":
    main()
