"""De formuleringen van de poort (PLAN #30.3b, B33, B34).

De kern wordt gesplitst op formuleringen: de bestaande voeden de feitenlaag
(`rol: laag`), en per feit komen er acht nieuwe bij die de poort zijn
(`rol: poort`): woorden en talen die de laag nooit zag. Claude Haiku 5.5
schrijft ze in batch (openbare feiten, B26); elk wordt gelezen vóór opname,
en wat niet precies het feit zegt, wordt afgewezen.

    python -m doublecheck.poortformuleringen indienen|ophalen|lezen|opnemen
"""

from __future__ import annotations

import json
from pathlib import Path

MODEL = "claude-haiku-5-5"
PROMPTVERSIE = "kernpoort-v1"
VAKKEN = (("en_1", "en"), ("en_2", "en"), ("es", "es"), ("pt", "pt"), ("it", "it"), ("tr", "tr"), ("id", "id"),
          ("ar", "ar"))
_TAALNAAM = {"en": "English", "es": "Spanish", "pt": "Portuguese", "it": "Italian", "tr": "Turkish",
             "id": "Indonesian", "ar": "Arabic"}
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "feitenbasis"
LEESLIJST = WORTEL / "docs" / "steekproeven" / "30.3b-poortformuleringen.json"

SYSTEEM = ("You write plain statements of established facts, for a test of whether a system recognises a fact in "
           "new wording. Never add, drop or soften anything; keep names, numbers and dates exact.")
_VRAAG = """The established fact:
{zin}

Existing wordings (do not reuse their wording):
{bestaand}

Write eight new plain declarative sentences that state exactly this fact, each in different words from the existing ones:
{vakken}"""
_SCHEMA = {"type": "object", "properties": {s: {"type": "string"} for s, _ in VAKKEN},
           "required": [s for s, _ in VAKKEN], "additionalProperties": False}


def verzoek(feit: dict) -> dict:
    bestaand = "\n".join(f"- ({f['taal']}) {f['tekst']}" for f in feit["formuleringen"])
    vakken = "\n".join(f"- {s}: in {_TAALNAAM[t]}" for s, t in VAKKEN)
    return {"custom_id": feit["id"],
            "params": {"model": MODEL, "max_tokens": 3_000, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": _VRAAG.format(zin=feit["zin"], bestaand=bestaand,
                                                                              vakken=vakken)}],
                       "output_config": {"effort": "medium",
                                         "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def opnemen(kern: list[dict], antwoorden: dict[str, dict], afgewezen: set[str]) -> list[dict]:
    """De gelezen poortformuleringen in de kern, met `rol: poort`; afgewezen
    (`feit#vak`) en al aanwezige teksten niet."""
    uit = []
    for feit in kern:
        feit = dict(feit, formuleringen=list(feit["formuleringen"]))
        al = {f["tekst"] for f in feit["formuleringen"]}
        for vak, taal in VAKKEN:
            tekst = " ".join((antwoorden.get(feit["id"], {}).get(vak) or "").split())
            if tekst and tekst not in al and f"{feit['id']}#{vak}" not in afgewezen:
                feit["formuleringen"].append({"taal": taal, "tekst": tekst, "rol": "poort", "prompt": PROMPTVERSIE})
                al.add(tekst)
        uit.append(feit)
    return uit


def _lees(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def main() -> None:  # pragma: no cover
    import argparse

    from doublecheck.feitenbasis import KERN, lees_kern

    parser = argparse.ArgumentParser(description="De formuleringen van de poort (PLAN #30.3b)")
    parser.add_argument("stap", choices=("indienen", "ophalen", "lezen", "opnemen"))
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    logboek, antwoorden = UIT / "poort-batches.jsonl", UIT / "poort-antwoorden.jsonl"
    kern = lees_kern()
    if args.stap in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        if args.stap == "indienen":
            batch = client.messages.batches.create(requests=[verzoek(f) for f in kern])
            with logboek.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE}) + "\n")
            print(f"batch {batch.id}: {len(kern)} feiten")
            return
        klaar = {r["id"] for r in _lees(antwoorden)}
        with antwoorden.open("a", encoding="utf-8") as uit:
            for b in reversed(_lees(logboek)):
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    continue
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded" or r.custom_id in klaar:
                        continue
                    tekst = next((c.text for c in r.result.message.content if c.type == "text"), "")
                    try:
                        uit.write(json.dumps({"id": r.custom_id, "antwoord": json.loads(tekst)},
                                             ensure_ascii=False) + "\n")
                        klaar.add(r.custom_id)
                    except json.JSONDecodeError:
                        continue
        print(f"{len(klaar)} van {len(kern)} feiten")
        return
    per_feit = {r["id"]: r["antwoord"] for r in _lees(antwoorden)}
    if args.stap == "lezen":
        for feit in kern:
            print(f"\n{feit['id']}: {feit['zin']}")
            for vak, _ in VAKKEN:
                print(f"  {feit['id']}#{vak}: {per_feit.get(feit['id'], {}).get(vak, '')}")
        return
    afgewezen = set(json.loads(LEESLIJST.read_text(encoding="utf-8"))["afgewezen"])
    doc = json.loads(KERN.read_text(encoding="utf-8"))
    doc["feiten"] = opnemen(doc["feiten"], per_feit, afgewezen)
    KERN.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sum(f.get('rol') == 'poort' for x in doc['feiten'] for f in x['formuleringen'])} poortformuleringen")


if __name__ == "__main__":
    main()
