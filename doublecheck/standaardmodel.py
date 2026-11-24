"""Een standaardmodel door dezelfde zeef (PLAN #30.1c, B33).

Is Factiz beter dan wat een gewoon taalmodel antwoordt? Dat is pas een meting
als het model door precies dezelfde berg gaat, met dezelfde telling. Per stuk
één vaste vraag, vastgelegd vóór de meting (`PROMPTVERSIE`): is deze bewering
door factcheckers als onwaar of misleidend ontkracht, als deels waar
beoordeeld, als waar bevestigd, of weet het model het niet?

- Bij P1 tot P3 telt als gevonden: dezelfde kant als het oordeel van de
  redactie (rood, midden, groen). Het model geeft geen bonnetje.
- Op gewone webtekst (N1) en naast een vastgesteld feit (N3) is "onwaar"
  vals alarm.

Alleen openbare data, offline (B26): de claimteksten uit de index, de
artikelen van de netwerktoets, de M4FC-beelden, een steekproef van de
stiltepools en de kern. Nooit iets van een gebruiker (DR3). Eerst het
kostenplan; er gaat niets naar de API zonder `--akkoord <bedrag>` van de PO.

    python -m doublecheck.standaardmodel plan
    python -m doublecheck.standaardmodel indienen --model haiku --akkoord 1.00 [--proef 100]
    python -m doublecheck.standaardmodel ophalen --model haiku
    python -m doublecheck.standaardmodel tellen --model haiku
"""

from __future__ import annotations

import base64
import json
import random
from collections import Counter
from pathlib import Path

# Batchprijzen in dollar per miljoen tokens (platform.claude.com, 2026-10-17).
MODELLEN = {
    "haiku": {"id": "claude-haiku-5-5", "in": 0.05, "uit": 0.25},
    "opus": {"id": "claude-opus-5-5", "in": 2.00, "uit": 10.00},
}
PROMPTVERSIE = "standaardmodel-v1"
ANTWOORDEN = ("onwaar", "deels-waar", "waar", "onbekend")
SYSTEEM = ("You help measure how well language models recognise claims that fact-checkers have already "
           "assessed. Answer from your own knowledge only.")
VRAAG = ("Has the claim in this text been assessed by fact-checkers? Answer \"onwaar\" if it was debunked as "
         "false or misleading, \"deels-waar\" if it was rated partly true, \"waar\" if it was confirmed as true, "
         "and \"onbekend\" if you do not know or if the text makes no checkable claim.")
_SCHEMA = {"type": "object", "properties": {"oordeel": {"type": "string", "enum": list(ANTWOORDEN)}},
           "required": ["oordeel"], "additionalProperties": False}
_KANT = {"onwaar": "rood", "deels-waar": "midden", "waar": "groen"}
N1_STEEKPROEF = 5_000
ZAAD = 3003
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "standaardmodel"


def verzoek(item: dict, model: str, max_tokens: int = 300) -> dict:
    if item.get("beeld"):
        pad = Path(item["beeld"])
        soort = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(pad.suffix.lower(), "image/jpeg")
        inhoud = [{"type": "image", "source": {"type": "base64", "media_type": soort,
                                               "data": base64.b64encode(pad.read_bytes()).decode()}},
                  {"type": "text", "text": VRAAG}]
    else:
        inhoud = [{"type": "text", "text": f"Text:\n{item['tekst']}\n\n{VRAAG}"}]
    return {"custom_id": item["id"],
            "params": {"model": MODELLEN[model]["id"], "max_tokens": max_tokens, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": inhoud}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def uitkomst(set_: str, verwacht: str | None, antwoord: str) -> str:
    """Hoe een antwoord telt, zoals bij Factiz."""
    if set_ in ("P1", "P2", "P3"):
        if antwoord not in _KANT:
            return "niets"
        return "gevonden" if _KANT[antwoord] == verwacht else "fout"
    if antwoord == "onwaar":
        return "vals"
    if set_ == "N3" and antwoord == "waar":
        return "goed"
    return "niets"


def _tokens(item: dict) -> int:
    vast = (len(SYSTEEM) + len(VRAAG)) // 4 + 20
    return vast + (1_600 if item.get("beeld") else len(item.get("tekst", "")) // 4 + 5)


def kosten(items: list[dict], model: str, *, uit_per_stuk: int = 80) -> float:
    m = MODELLEN[model]
    return (sum(_tokens(i) for i in items) * m["in"] + len(items) * uit_per_stuk * m["uit"]) / 1e6


def _kant(conn, claim_id: str) -> str | None:
    from doublecheck.verdicts import _POSITIE, labelklasse_in_tijd

    checks = conn.execute("SELECT verdict_normalized, review_date FROM factcheck WHERE claim_id = ?", (claim_id,))
    klasse, _ = labelklasse_in_tijd((v, d) for v, d in checks)
    return _POSITIE.get(klasse)


def items(versie: str, db: str) -> list[dict]:  # pragma: no cover - op de productiedatabase
    """De berg van de zeef voor het model: P1 tot P3 met de verwachte kant, een
    steekproef van N1, en N3."""
    import sqlite3

    from doublecheck import zeef
    from doublecheck.feitenbasis import lees_kern, lees_paren, n3_items
    from doublecheck.netwerktoets import items as artikel_items
    from doublecheck.ruwetest import m4fc_items
    from doublecheck.variantenbatch import lees_regels

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    map_ = zeef.UIT / versie
    tekst_van = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    claim_van_check = dict(conn.execute("SELECT url, claim_id FROM factcheck"))
    dag = {f"P1:{r['vraag']}": r["dag"] for r in zeef._lees(map_ / "terugkijk" / "uitkomsten.jsonl") if r["bron"] == "post"}
    uit = []
    for i, r in enumerate(zeef._lees(map_ / "P1.jsonl")):
        claim = claim_van_check.get(r["sleutel"][3:])
        if claim and claim in tekst_van:
            uit.append({"id": f"P1-{i:05d}", "set": "P1", "sleutel": r["sleutel"], "helft": r["helft"],
                        "taal": r["taal"], "tekst": tekst_van[claim], "verwacht": _kant(conn, min(r["doelen"])),
                        "datum": dag.get(r["sleutel"])})
    artikelen = [json.loads(x) for x in (zeef.P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    p2 = {r["sleutel"]: r for r in zeef._lees(map_ / "P2.jsonl")}
    for i, a in enumerate(artikel_items(artikelen)):
        sleutel = f"P2:{a.artikel}#{a.claim_id}"
        if sleutel in p2:
            uit.append({"id": f"P2-{i:05d}", "set": "P2", "sleutel": sleutel, "helft": p2[sleutel]["helft"],
                        "taal": a.taal, "tekst": a.kop_inleiding, "verwacht": _kant(conn, a.claim_id)})
    p3 = {r["sleutel"]: r for r in zeef._lees(map_ / "P3.jsonl")}
    for i, b in enumerate(m4fc_items(zeef.P3_MAP)):
        sleutel = f"P3:{b.pad.stem}"
        if sleutel in p3:
            uit.append({"id": f"P3-{i:05d}", "set": "P3", "sleutel": sleutel, "helft": p3[sleutel]["helft"],
                        "taal": b.taal, "beeld": str(b.pad), "verwacht": _kant(conn, b.claim_id)})
    stukken = [(pool.name, r) for pool in zeef.POOLS for r in lees_regels(pool)]
    random.Random(ZAAD).shuffle(stukken)
    for i, (pool, r) in enumerate(stukken[:N1_STEEKPROEF]):
        sleutel = f"N1:{pool}:{r['claim_id']}"
        uit.append({"id": f"N1-{i:05d}", "set": "N1", "sleutel": sleutel, "helft": zeef.helft(sleutel),
                    "taal": r["taal"], "tekst": r["varianten"][0]["tekst"]})
    for i, n in enumerate(n3_items(lees_kern(), lees_paren())):
        uit.append({"id": f"N3-{i:05d}", "set": "N3", "sleutel": n["sleutel"], "helft": n["helft"],
                    "taal": n["taal"], "tekst": n["tekst"], "bron": n["bron"]})
    return uit


RECENT_VANAF = "2026-07-01"  # na de trainingsgrens van Haiku 5.5 (juni 2026)


def vergelijking(items: list[dict], antwoorden: dict[str, str], labels: dict[str, str] | None = None) -> dict:
    """Per helft, naast Factiz te leggen: per positieve set de vindkans op de
    stukken met een oordeel met kant, P1 apart voor checks na de
    trainingsgrens, vals alarm op N1 en N3, en de precisie van de stellige
    antwoorden (alles behalve "onbekend")."""
    uit: dict = {}
    for i in items:
        if i["id"] not in antwoorden:
            continue
        h = uit.setdefault(i["helft"], {"precisie": {"stellig": 0, "fout": 0}})
        u = uitkomst(i["set"], i.get("verwacht"), antwoorden[i["id"]])
        if u == "vals" and i["set"] == "N1" and (labels or {}).get(i.get("sleutel")) == "terecht":
            u = "terecht"  # de webtekst doet zelf een ontkrachte bewering
        if i["set"] in ("P1", "P2", "P3"):
            d = h.setdefault(i["set"], {"n": 0, "gevonden": 0, "fout": 0, "zonder_kant": 0})
            if i.get("verwacht") not in ("rood", "midden", "groen"):
                d["zonder_kant"] += 1
                continue
            d["n"] += 1
            d[u] = d.get(u, 0) + 1
            if i["set"] == "P1" and (i.get("datum") or "") >= RECENT_VANAF:
                r = h.setdefault("P1_recent", {"n": 0, "gevonden": 0})
                r["n"] += 1
                r["gevonden"] += u == "gevonden"
        else:
            d = h.setdefault(i["set"], {"n": 0, "vals": 0, "goed": 0})
            d["n"] += 1
            d[u] = d.get(u, 0) + 1
        if u in ("gevonden", "fout", "vals", "goed", "terecht"):
            h["precisie"]["stellig"] += 1
            h["precisie"]["fout"] += u in ("fout", "vals")
    return uit


def main() -> None:  # pragma: no cover
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Een standaardmodel door dezelfde zeef (#30.1c)")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "tellen"))
    parser.add_argument("--versie", default="factiz-1")
    parser.add_argument("--model", choices=tuple(MODELLEN), default="haiku")
    parser.add_argument("--proef", type=int, default=0, help="alleen de eerste N stukken (een proefbatch)")
    parser.add_argument("--akkoord", type=float, help="het bedrag in dollar dat de PO goedkeurde")
    parser.add_argument("--opnieuw", action="store_true", help="bij indienen: alleen de afgekapte antwoorden, met meer ruimte")
    args = parser.parse_args()
    db = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    alle = items(args.versie, db)
    if args.stap == "plan":
        print(f"{len(alle)} stukken: {dict(Counter(i['set'] for i in alle))}")
        for m in MODELLEN:
            print(f"  {m}: proef van 100 ${kosten(alle[:100], m):.2f}; alles ${kosten(alle, m):.2f}")
        return
    map_ = UIT / args.model
    map_.mkdir(parents=True, exist_ok=True)
    ingediend = set()
    for pad in map_.glob("batch-*.json"):
        ingediend |= set(json.loads(pad.read_text(encoding="utf-8")))
    nog = [i for i in alle if i["id"] not in ingediend]
    antwoorden_pad = map_ / "antwoorden.jsonl"
    if args.stap == "indienen" and args.opnieuw:
        laatste = {}
        for r in antwoorden_pad.read_text(encoding="utf-8").splitlines():
            laatste[json.loads(r)["id"]] = json.loads(r)["oordeel"]
        nog = [i for i in alle if laatste.get(i["id"]) == "onleesbaar"]
    gekozen = nog[: args.proef] if args.proef else nog
    if args.stap == "indienen" and not gekozen:
        raise SystemExit("alle stukken zijn al ingediend")
    if args.stap == "indienen":
        bedrag = kosten(gekozen, args.model)
        if args.akkoord is None or bedrag > args.akkoord:
            raise SystemExit(f"geweigerd: deze batch kost naar schatting ${bedrag:.2f}; geef het bedrag dat de PO "
                             "goedkeurde met --akkoord")
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        ruimte = 2_000 if args.opnieuw else 300
        batch = anthropic.Anthropic().messages.batches.create(
            requests=[verzoek(i, args.model, ruimte) for i in gekozen])
        (map_ / f"batch-{batch.id}.json").write_text(json.dumps([i["id"] for i in gekozen]), encoding="utf-8")
        (map_ / "batches.jsonl").open("a", encoding="utf-8").write(
            json.dumps({"id": batch.id, "stukken": len(gekozen), "schatting": round(bedrag, 2),
                        "prompt": PROMPTVERSIE}) + "\n")
        print(f"batch {batch.id}: {len(gekozen)} stukken, naar schatting ${bedrag:.2f}")
    elif args.stap == "ophalen":
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        pad = map_ / "antwoorden.jsonl"
        klaar = {json.loads(r)["id"] for r in pad.read_text(encoding="utf-8").splitlines()
                 if json.loads(r)["oordeel"] != "onleesbaar"} if pad.exists() else set()
        with pad.open("a", encoding="utf-8") as uit:
            # De nieuwste batch eerst: een opnieuw ingediend stuk wint van zijn afgekapte versie.
            batches = [json.loads(r) for r in (map_ / "batches.jsonl").read_text(encoding="utf-8").splitlines()]
            for b in reversed(batches):
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    continue
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded" or r.custom_id in klaar:
                        continue
                    tekst = next((c.text for c in r.result.message.content if c.type == "text"), "{}")
                    try:
                        oordeel = json.loads(tekst).get("oordeel", "onbekend")
                    except json.JSONDecodeError:
                        oordeel = "onleesbaar"  # afgekapt; opnieuw indienen met meer ruimte
                    uit.write(json.dumps({"id": r.custom_id, "oordeel": oordeel, "model": MODELLEN[args.model]["id"],
                                          "prompt": PROMPTVERSIE, "stop": r.result.message.stop_reason}) + "\n")
                    klaar.add(r.custom_id)
        print(f"{len(klaar)} antwoorden")
    else:
        antwoorden = {json.loads(r)["id"]: json.loads(r)["oordeel"]
                      for r in (map_ / "antwoorden.jsonl").read_text(encoding="utf-8").splitlines()}
        lp = WORTEL / "docs" / "steekproeven" / "30.1c-standaardmodel-n1.json"
        labels = {r["sleutel"]: r["label"] for r in json.loads(lp.read_text(encoding="utf-8"))["labels"]} if lp.exists() else {}
        uitslag = vergelijking(alle, antwoorden, labels)
        (map_ / "vergelijking.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(uitslag, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
