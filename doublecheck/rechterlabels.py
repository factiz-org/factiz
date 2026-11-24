"""Haiku-labels op echte paren (PLAN #30.3, de volgende ronde, BENCHMARK §125).

De rechter leerde op varianten die Haiku schreef, en faalde op wat hij in het
wild ziet: echte, lange teksten, een andere lading over de taalgrens, en
gewone parafrasen die hij te streng afwees. Hier krijgt hij echte paren: per
vraag de bovenste vijf kandidaten uit het geheugen vanaf 0,75, zoals de
resolver ze vindt, met een label van Claude Haiku 5.5 (batch, offline,
openbare claims en openbare webtekst, B26).

Drie bronnen, alle van de ontwikkelhelft van de zeef:

- **zeef-p1**: de latere check van een post als vraag (P1);
- **zeef-n1**: gewone webtekst die dicht bij een claim ligt (N1, vanaf 0,75);
- **buren**: de lesclaims van de rechterset met hun buren in de index.

Nooit een vraag van de toetshelft, nooit de kern (N3), en geen kandidaat
waarvan de zaak op de toetshelft ligt. Waar mensen hetzelfde paar al
labelden (dezelfde post, `30.1-zeef.json`, `28.6c`), wordt Haiku daaraan
gemeten.

    python -m doublecheck.rechterlabels verzamelen|plan|indienen|ophalen|uitschrijven|vergelijken|lezen
"""

from __future__ import annotations

import json
import random
from collections import Counter

from doublecheck.rechterset import UIT, paarsleutel

MODEL = "claude-haiku-5-5"
PROMPTVERSIE = "rechterlabel-v1"
PRIJS_IN, PRIJS_UIT = 0.05, 0.25  # batch, dollar per miljoen tokens (2026-10-17)
VANAF = 0.75
DIEPTE = 5
OORDELEN = ["zelfde", "verwant", "tegenspraak", "anders"]
KANDIDATEN = UIT / "echte-kandidaten.jsonl"
UITVOER = UIT / "haiku-echt.jsonl"

SYSTEEM = ("You label pairs of texts for a system that matches what people share to fact-checks that already "
           "exist. Never judge whether a claim is true; only compare what the two texts claim.")
_VRAAG = """Text A (what someone wants to check):
{vraag}

Text B (a claim that fact-checkers have checked):
{kandidaat}

Which one is right?
- zelfde: a fact-check of B answers A. Same claim; wording, language, length and detail may differ. A text that reports or refutes the claim of B also counts as zelfde.
- verwant: same subject or event, but a different claim: another actor, target, number, date, place, image or framing (for example "annexed" against "decided to join"), or one claims clearly more than the other.
- tegenspraak: A asserts the opposite of B.
- anders: a different subject.
Set zeker to false if you are unsure."""
_SCHEMA = {"type": "object",
           "properties": {"oordeel": {"type": "string", "enum": OORDELEN}, "zeker": {"type": "boolean"}},
           "required": ["oordeel", "zeker"], "additionalProperties": False}


def mag_mee(vraag_helft: str, kandidaat_id: str) -> bool:
    """Alleen de ontwikkelhelft, en geen kandidaat die zelf op de toetshelft ligt."""
    from doublecheck.zeef import helft

    return vraag_helft == "ontwikkel" and helft(f"zaak:{kandidaat_id}") != "toets"


def verzoek(paar: dict) -> dict:
    return {"custom_id": paarsleutel(paar),
            "params": {"model": MODEL, "max_tokens": 1_500, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": _VRAAG.format(**paar)}],
                       "output_config": {"effort": "medium",
                                         "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def uitkomst(tekst: str) -> tuple[str, bool] | None:
    try:
        antwoord = json.loads(tekst)
    except json.JSONDecodeError:
        return None
    if antwoord.get("oordeel") not in OORDELEN:
        return None
    return antwoord["oordeel"], bool(antwoord.get("zeker"))


def mens_zelfde(mens: str | None) -> bool | None:
    """Wat mensen over hetzelfde paar zeiden: dezelfde bewering of niet."""
    if mens is None:
        return None
    return mens in ("doel", "zelfde", "terecht")


def overeenstemming(rijen: list[dict]) -> dict:
    gelabeld = [r for r in rijen if mens_zelfde(r["mens"]) is not None]
    haiku = [(mens_zelfde(r["mens"]), r["label"] == "zelfde") for r in gelabeld]
    return {"n": len(haiku), "eens": sum(m == h for m, h in haiku),
            "haiku_zelfde_mens_niet": sum(h and not m for m, h in haiku),
            "mens_zelfde_haiku_niet": sum(m and not h for m, h in haiku)}


def leslabel(haiku: str, zeker: bool, mens: str | None) -> str | None:
    """Wat de rechter leert: een mens beslist waar Haiku twijfelt, een zeker
    conflict tussen mens en Haiku valt weg, en zonder mens alleen een zeker
    label van Haiku. Haiku is voorzichtig (BENCHMARK §126); zonder deze regel
    leert de rechter die voorzichtigheid na."""
    m = mens_zelfde(mens)
    if m is None:
        return haiku if zeker else None
    if m:
        return "zelfde" if haiku == "zelfde" or not zeker else None
    return None if haiku == "zelfde" else haiku


def lesregel(item: dict, oordeel: tuple[str, bool]) -> dict:
    return {"vraag": item["vraag"], "kandidaat": item["kandidaat"], "label": oordeel[0], "zeker": oordeel[1],
            "soort": item["soort"], "zaak": item["zaak"], "taal": item.get("taal", ""), "rol": "leren",
            "bron": "haiku-echt", "prompt": PROMPTVERSIE}


def verzamelen(db: str) -> list[dict]:  # pragma: no cover - op de productiedatabase, met het model
    import numpy as np

    from doublecheck import vraagvorm
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.stiltetoets import lees_db
    from doublecheck.variantenbatch import lees_regels
    from doublecheck.zeef import POOLS, UIT as ZEEF, _alle_regels, _claim_van_check, helft, lees_labels

    config = load_config()
    conn = lees_db(db)
    tekst = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    regels = _alle_regels(ZEEF / "factiz-rechter-d2")
    labels = lees_labels(regels)
    vragen = []
    for r in regels:
        if r["set"] == "P1" and r["helft"] == "ontwikkel" and r.get("doelen"):
            eigen = _claim_van_check(conn, r["sleutel"][3:])
            if eigen in tekst:
                mens = {d: "doel" for d in r["doelen"]}
                if r.get("kandidaat") and r["sleutel"] in labels:
                    mens[r["kandidaat"]] = labels[r["sleutel"]]
                vragen.append({"vraag": tekst[eigen], "zaak": min(r["doelen"]), "soort": "zeef-p1",
                               "helft": "ontwikkel", "taal": r.get("taal", ""), "zelf": eigen, "mens": mens})
    n1 = {r["sleutel"]: r for r in regels if r["set"] == "N1"}
    for pool in POOLS:
        rijen = lees_regels(pool)
        hoogste = np.load(ZEEF / "factiz-1" / f"N1-{pool.name}-hoogste.npy")
        for i, rij in enumerate(rijen):
            sleutel = f"N1:{pool.name}:{rij['claim_id']}"
            if hoogste[i] >= VANAF and helft(sleutel) == "ontwikkel":
                mens = {}
                if sleutel in n1 and n1[sleutel].get("kandidaat") and sleutel in labels:
                    mens[n1[sleutel]["kandidaat"]] = labels[sleutel]
                vragen.append({"vraag": rij["varianten"][0]["tekst"], "zaak": sleutel, "soort": "zeef-n1",
                               "helft": "ontwikkel", "taal": rij.get("taal", ""), "zelf": None, "mens": mens})
    for r in (json.loads(x) for x in (UIT / "claims.jsonl").read_text(encoding="utf-8").splitlines()):
        if helft(f"zaak:{r['claim_id']}") == "ontwikkel":
            vragen.append({"vraag": r["tekst"], "zaak": r["claim_id"], "soort": "buren", "helft": "ontwikkel",
                           "taal": r["taal"], "zelf": r["claim_id"], "mens": {}})
    vingers = fingerprint_texts([v["vraag"] for v in vragen], config.model_versions.text_embedding)
    paren = []
    for v, fp in zip(vragen, vingers):
        gevonden = vraagvorm.zoek(conn, config, v["vraag"], fp, DIEPTE + 3)
        genomen = 0
        for k in gevonden:
            if k.claim_id == v["zelf"] or k.similarity < VANAF or not mag_mee(v["helft"], k.claim_id):
                continue
            paren.append({"vraag": v["vraag"], "kandidaat": tekst[k.claim_id], "kandidaat_id": k.claim_id,
                          "zaak": v["zaak"], "soort": v["soort"], "taal": v["taal"],
                          "gelijkenis": round(float(k.similarity), 4), "mens": v["mens"].get(k.claim_id)})
            genomen += 1
            if genomen == DIEPTE:
                break
    gezien, uniek = set(), []
    for p in paren:
        if paarsleutel(p) not in gezien:
            gezien.add(paarsleutel(p))
            uniek.append(p)
    return uniek


def _lees(pad) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def main() -> None:  # pragma: no cover
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Haiku-labels op echte paren (PLAN #30.3)")
    parser.add_argument("stap", choices=("verzamelen", "plan", "indienen", "ophalen", "uitschrijven", "vergelijken",
                                         "lezen"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    logboek, antwoorden = UIT / "batches-echt.jsonl", UIT / "antwoorden-echt.jsonl"
    if args.stap == "verzamelen":
        import torch
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        paren = verzamelen(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
        KANDIDATEN.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in paren), encoding="utf-8")
        print(f"{len(paren)} paren; {dict(Counter(p['soort'] for p in paren))}; "
              f"met een label van mensen {sum(p['mens'] is not None for p in paren)}")
        return
    paren = _lees(KANDIDATEN)
    if args.stap == "plan":
        tokens_in = sum((len(p["vraag"]) + len(p["kandidaat"])) // 3 + 350 for p in paren)
        kosten = (tokens_in * PRIJS_IN + len(paren) * 300 * PRIJS_UIT) / 1e6
        print(f"{len(paren)} paren, naar schatting ${kosten:.2f}")
    elif args.stap == "indienen":
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        ingediend = {i for r in _lees(logboek) for i in r["ids"]}
        verzoeken = [verzoek(p) for p in paren if paarsleutel(p) not in ingediend][:args.proef]
        if not verzoeken:
            print("alles is al ingediend")
            return
        batch = anthropic.Anthropic().messages.batches.create(requests=verzoeken)
        with logboek.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE, "ids": [v["custom_id"] for v in verzoeken]})
                    + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} paren")
    elif args.stap == "ophalen":
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
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
                    if uitkomst(tekst) is None:
                        continue
                    uit.write(json.dumps({"id": r.custom_id, "tekst": tekst}) + "\n")
                    klaar.add(r.custom_id)
        print(f"{len(klaar)} antwoorden")
    elif args.stap == "uitschrijven":
        oordeel = {r["id"]: uitkomst(r["tekst"]) for r in _lees(antwoorden)}
        rijen = [lesregel(p, oordeel[paarsleutel(p)]) | {"mens": p["mens"], "gelijkenis": p["gelijkenis"],
                                                          "haiku": oordeel[paarsleutel(p)][0]}
                 for p in paren if oordeel.get(paarsleutel(p))]
        for r in rijen:
            r["label"] = leslabel(r["haiku"], r["zeker"], r["mens"])
        UITVOER.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")
        print(f"{len(rijen)} paren, waarvan lesstof {sum(r['label'] is not None for r in rijen)}; "
              f"{dict(Counter((r['soort'], r['label']) for r in rijen))}")
    elif args.stap == "vergelijken":
        rijen = [r | {"label": r["haiku"]} for r in _lees(UITVOER)]
        print(overeenstemming(rijen))
        for r in rijen:
            m = mens_zelfde(r["mens"])
            if m is not None and m != (r["label"] == "zelfde"):
                print(f"  mens {r['mens']}, Haiku {r['label']}: {r['vraag'][:90]!r} | {r['kandidaat'][:90]!r}")
    else:
        rijen = _lees(UITVOER)
        for r in random.Random(3009).sample(rijen, min(100, len(rijen))):
            print(f"{paarsleutel(r)} [{r['soort']} → {r['label']}{'' if r['zeker'] else '?'}] ({r['gelijkenis']})\n"
                  f"  V: {r['vraag'][:220]}\n  K: {r['kandidaat'][:220]}")


if __name__ == "__main__":
    main()
