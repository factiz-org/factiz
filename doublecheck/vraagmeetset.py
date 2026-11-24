"""De meetset van #25.36: vraag en bewering, beide kanten op (PLAN #25.36, stap a).

Vooraf vastgelegd: per taal en per richting 50 claims met een toegelaten
check (seed 2536). Een claim die een bewering is, krijgt een vraag als
tegenvorm ("vraag zoekt bewering"); een claim die een vraag is, krijgt een
bewering ("bewering zoekt vraag"). De tegenvorm is een post, geschreven met een
eigen opdracht, los van die van de claimvarianten, zodat meetset en ingreep
niet op elkaar lijken. Elke richting en taal gaat in twee helften: op de
ontwikkelhelft mag de regel van stap c groeien, op de toetshelft wordt de poort
gemeten en kijkt niemand vóór de uitslag.

De harde regels van de Batch API zijn die van `variantenbatch`: eerst een
proefbatch, binnen het budget (PO 2026-10-16: $2 voor meetset en varianten
samen), en nooit blind opnieuw. Er gaat alleen openbare claimtekst naar buiten
(DR3, B26).

    python -m doublecheck.vraagmeetset plan
    python -m doublecheck.vraagmeetset indienen [--budget 1]
    python -m doublecheck.vraagmeetset ophalen
    python -m doublecheck.vraagmeetset uitschrijven
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from doublecheck.toelating import buiten_index, register, staat_aan
from doublecheck.variantenbatch import Weigering, kosten, lees_regels, lees_stand, schrijf_stand
from doublecheck.varianten import MODEL
from doublecheck.vraagvorm import is_vraag

TALEN = ("si", "ja", "zh", "ar", "en", "nl", "es", "pt", "hi")
RICHTINGEN = ("vraag", "bewering")
PER_TAAL = 50
SEED = 2536
# v2 (2026-10-16, na de proef van v1): bij een claim die zelf een vraag is, gaf v1
# één keer antwoord ("er is geen wetsvoorstel nodig") in plaats van de bewering.
PROMPTVERSIE = "vraagvorm-meetset-v2"
PROEFGROOTTE = 20
BUDGET = 1.0
MAP = Path("data/vraagvorm/meetset")
UIT = Path("docs/steekproeven/25.36-meetset.json")

_SYSTEEM = (
    "You write test material for a search engine that finds claims fact-checkers have already checked. "
    "Given one checked claim, you write one short social media post in the same language as the claim, "
    "the way a person would post it. You never judge whether the claim is true and you add no facts: "
    "keep every name, number, date and negation of the claim."
)
_OPDRACHT = {
    "vraag": ("Write one short social media post, in the same language as the claim, in which someone asks "
              "whether this is true, as a yes-no question. Do not copy the claim word for word."),
    "bewering": ("Write one short social media post, in the same language as the claim, in which someone states "
                 "this as a fact: a plain statement, not a question. If the claim is phrased as a question, state "
                 "as a fact what it asks about; never answer it and never deny it. Do not copy the claim word for "
                 "word."),
}
_SCHEMA = {"type": "object", "properties": {"post": {"type": "string"}}, "required": ["post"],
           "additionalProperties": False}


def kies(conn, *, talen=TALEN, per_taal: int = PER_TAAL, seed: int = SEED) -> list[dict]:
    """De claims van de meetset, per taal en richting, met hun helft en hun
    bron (CC BY: de naamsvermelding reist mee)."""
    from doublecheck.evidence import _host

    hosts = register() if staat_aan(conn) else None
    bron: dict[str, tuple[str, str]] = {}
    for claim_id, uitgever, url in conn.execute(
            "SELECT claim_id, publisher, url FROM factcheck ORDER BY claim_id, url"):
        if claim_id not in bron and url and (hosts is None or (_host(url) or "") in hosts):
            bron[claim_id] = (uitgever, url)
    buiten = buiten_index(conn)
    groepen: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for claim_id, tekst, taal in conn.execute(
            "SELECT claim_id, canonical_text, language FROM claim ORDER BY claim_id"):
        if taal in talen and claim_id not in buiten and claim_id in bron and tekst and tekst.strip():
            groepen[(taal, "bewering" if is_vraag(tekst) else "vraag")].append((claim_id, tekst.strip()))
    uit = []
    for taal in talen:
        for richting in RICHTINGEN:
            kandidaten = groepen[(taal, richting)]
            gekozen = random.Random(f"{seed}-{taal}-{richting}").sample(kandidaten, min(per_taal, len(kandidaten)))
            for n, (claim_id, tekst) in enumerate(gekozen):
                uitgever, url = bron[claim_id]
                uit.append({"id": f"{richting}-{claim_id}", "claim_id": claim_id, "taal": taal,
                            "richting": richting, "claim": tekst, "helft": "ontwikkel" if n % 2 == 0 else "toets",
                            "publisher": uitgever, "url": url})
    return uit


def verzoek(item: dict) -> dict:
    prompt = f"Claim (language: {item['taal']}):\n{item['claim']}\n\n{_OPDRACHT[item['richting']]}"
    return {
        "custom_id": item["id"],
        "params": {
            "model": MODEL,
            "max_tokens": 600,
            "system": _SYSTEEM,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
        },
    }


# --- indienen en ophalen -------------------------------------------------------

def _onderweg(map_: Path, stand: dict) -> set[str]:
    return {i for b in stand["batches"] if not b["opgehaald"]
            for i in json.loads((map_ / f"batch-{b['id']}.json").read_text(encoding="utf-8"))}


def dien_volgende_in(client, map_: Path, items: list[dict], *, budget: float = BUDGET,
                     proefgrootte: int = PROEFGROOTTE) -> str | None:
    """Dient de proefbatch in, of na de proef de rest binnen het budget. Geeft
    het batch-id terug, of `None` als er niets meer te doen is."""
    map_ = Path(map_)
    stand = lees_stand(map_)
    if stand["bezig"]:
        raise Weigering(
            f"een vorige indiening werd onderbroken vóór het batch-id bewaard was ({stand['bezig']}). "
            "Kijk met client.messages.batches.list() of die batch bestaat; zet daarna 'bezig' op null.")
    klaar = {r["id"] for r in lees_regels(map_)}
    onderweg = _onderweg(map_, stand)
    open_ = [i for i in items if i["id"] not in klaar and i["id"] not in onderweg]
    if not open_:
        return None
    if not stand["batches"]:
        return _dien_in(client, map_, stand, _gespreid(open_)[:proefgrootte], proef=True)
    if any(b["proef"] and not b["opgehaald"] for b in stand["batches"]):
        raise Weigering("de proefbatch is nog niet opgehaald; die meet eerst de echte kosten per verzoek")
    regels = lees_regels(map_)
    if not regels:
        raise Weigering("de proefbatch leverde geen enkele regel op; geen kosten per verzoek te meten")
    uitgegeven = kosten(regels)
    verwacht = uitgegeven + uitgegeven / len(regels) * (len(items) - len({r["id"] for r in regels}))
    if verwacht > budget:
        raise Weigering(f"verwachte kosten ${verwacht:.4f} (uitgegeven ${uitgegeven:.4f}) gaan over het budget"
                        f" van ${budget:.2f}")
    return _dien_in(client, map_, stand, open_, proef=False)


def _gespreid(items: list[dict]) -> list[dict]:
    """Om en om per taal en richting, zodat de proefbatch de opdracht in elke
    taal en beide richtingen ziet, niet twintig keer dezelfde."""
    rang: dict[tuple[str, str], int] = defaultdict(int)
    geordend = []
    for volgorde, item in enumerate(items):
        sleutel = (item["taal"], item["richting"])
        geordend.append((rang[sleutel], volgorde, item))
        rang[sleutel] += 1
    return [item for _, _, item in sorted(geordend, key=lambda t: (t[0], t[1]))]


def _dien_in(client, map_: Path, stand: dict, portie: list[dict], *, proef: bool) -> str:
    nu = dt.datetime.now().isoformat(timespec="seconds")
    stand["bezig"] = {"verzoeken": len(portie), "proef": proef, "sinds": nu}
    schrijf_stand(map_, stand)
    try:
        batch = client.messages.batches.create(requests=[verzoek(i) for i in portie])
    except Exception as fout:
        if getattr(fout, "status_code", None) is not None:
            stand["bezig"] = None
            schrijf_stand(map_, stand)
        raise
    (map_ / f"batch-{batch.id}.json").write_text(json.dumps([i["id"] for i in portie]), encoding="utf-8")
    stand["batches"].append({"id": batch.id, "aantal": len(portie), "proef": proef, "opgehaald": False,
                             "ingediend": nu})
    stand["bezig"] = None
    schrijf_stand(map_, stand)
    return batch.id


def _regel(uitslag, batch_id: str) -> dict:
    bericht = uitslag.result.message
    regel = {"id": uitslag.custom_id, "batch": batch_id, "model": MODEL, "prompt": PROMPTVERSIE,
             "tokens": [bericht.usage.input_tokens, bericht.usage.output_tokens],
             "geweigerd": bericht.stop_reason == "refusal", "onleesbaar": False, "post": None}
    if regel["geweigerd"]:
        return regel
    teksten = [b.text for b in bericht.content if getattr(b, "type", "") == "text"]
    try:
        post = json.loads(teksten[0])["post"].strip() if teksten else ""
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        post = ""
    if post:
        regel["post"] = post
    else:
        regel["onleesbaar"] = True
    return regel


def haal_op(client, map_: Path) -> dict:
    """Elke afgeronde batch binnen; een fout of verlopen verzoek krijgt geen
    regel en gaat bij de volgende indiening opnieuw mee."""
    map_ = Path(map_)
    stand = lees_stand(map_)
    klaar = {r["id"] for r in lees_regels(map_)}
    telling = {"regels": 0, "zonder regel": 0, "lopend": 0}
    for batch in stand["batches"]:
        if batch["opgehaald"]:
            continue
        if client.messages.batches.retrieve(batch["id"]).processing_status != "ended":
            telling["lopend"] += 1
            continue
        with (map_ / "regels.jsonl").open("a", encoding="utf-8") as uit:
            for uitslag in client.messages.batches.results(batch["id"]):
                if uitslag.result.type != "succeeded" or uitslag.custom_id in klaar:
                    telling["zonder regel"] += uitslag.result.type != "succeeded"
                    continue
                uit.write(json.dumps(_regel(uitslag, batch["id"]), ensure_ascii=False) + "\n")
                klaar.add(uitslag.custom_id)
                telling["regels"] += 1
        batch["opgehaald"] = True
        schrijf_stand(map_, stand)
    return telling


# --- de meetset ----------------------------------------------------------------

def meetset(items: list[dict], regels: list[dict]) -> dict:
    per_id = {r["id"]: r for r in regels}
    paren = [{**i, "post": per_id[i["id"]]["post"], "lezing": None}
             for i in items if per_id.get(i["id"], {}).get("post")]
    return {
        "_meta": ("De meetset van PLAN #25.36, vastgelegd vóór het meten. Elk paar is een claim uit het corpus, "
                  "letterlijk, uit de Data Commons ClaimReview-feed of de EUvsDisinfo-snapshot (beide CC BY; "
                  "uitgever en url bij elk paar), en een post die " + MODEL + " er met de opdracht "
                  + PROMPTVERSIE + " van maakte: een bewerking van die claim, als vraag of als bewering. De "
                  "leesproef vult `lezing` (goed, betekenisfout, verkeerde vorm of verkeerde taal); de helft "
                  "`toets` blijft dicht tot de uitslag."),
        "seed": SEED,
        "prompt": PROMPTVERSIE,
        "model": MODEL,
        "gemaakt": dt.date.today().isoformat(),
        "paren": paren,
    }


def _plan(items: list[dict], map_: Path, budget: float) -> None:
    telling = defaultdict(int)
    for i in items:
        telling[(i["taal"], i["richting"])] += 1
    for taal in TALEN:
        print(f"  {taal}: vraag {telling[(taal, 'vraag')]}, bewering {telling[(taal, 'bewering')]}")
    regels = lees_regels(map_)
    if regels:
        uitgegeven = kosten(regels)
        print(f"{len(items)} verzoeken; {len(regels)} binnen voor ${uitgegeven:.4f}; verwacht totaal "
              f"${uitgegeven / len(regels) * len(items):.4f} (budget ${budget:.2f})")
    else:
        # Een schatting tot de proefbatch de echte kosten meet: 300 tokens in, 100 uit.
        from doublecheck.variantenbatch import PRIJS_IN, PRIJS_UIT

        schatting = len(items) * (300 * PRIJS_IN + 100 * PRIJS_UIT) / 1e6
        print(f"{len(items)} verzoeken; geschat ${schatting:.4f} (budget ${budget:.2f}); eerst een proefbatch van "
              f"{PROEFGROOTTE}")


def main() -> None:
    import argparse
    import os
    import sqlite3

    parser = argparse.ArgumentParser(description="De meetset van #25.36: vraag en bewering, beide kanten op")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "uitschrijven"))
    parser.add_argument("--map", default=str(MAP))
    parser.add_argument("--budget", type=float, default=BUDGET)
    args = parser.parse_args()

    map_ = Path(args.map)
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    items = kies(conn)
    if args.stap == "plan":
        _plan(items, map_, args.budget)
    elif args.stap in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        if args.stap == "indienen":
            try:
                batch_id = dien_volgende_in(client, map_, items, budget=args.budget)
            except Weigering as reden:
                raise SystemExit(f"geweigerd: {reden}")
            print(f"ingediend: {batch_id}" if batch_id else "niets meer in te dienen")
        else:
            print(haal_op(client, map_))
        _plan(items, map_, args.budget)
    else:
        uit = meetset(items, lees_regels(map_))
        UIT.write_text(json.dumps(uit, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(uit['paren'])} paren naar {UIT}")


if __name__ == "__main__":
    main()
