"""De rechterset: lesstof en meetstof voor de rechter (PLAN #30.3, B36).

De rechter krijgt een paar (vraag, kandidaat) en zegt: *zelfde bewering*,
*verwant* (zelfde onderwerp, andere bewering), *iets anders*, of *spreekt
tegen*. Om dat te leren en te meten, zijn paren
nodig met het label vooraf bepaald. Twee bronnen:

- **Gemaakt**: een gelaagde steekproef van claims uit de index; per claim
  schrijft Claude Haiku 5.5 (batch, offline, openbare claimtekst, B26) vijf
  varianten waarvan het label vastligt vóór het schrijven: een parafrase en
  een vertaling (zelfde), een rolwissel en een ander getal, datum of plaats
  (verwant), en de ontkenning (spreekt tegen). Precies de fouten uit onze
  metingen: de omgedraaide rol, de andere lading, de datum.
- **Echt**: de paren die al gelabeld zijn: de vetolabels van #25.14d, de
  ander-records van #28.6 c, de minimale paren, de stance-proefset van #21.1
  en de rode uitslagen van de kerncheck. Niet de vetolabels van #17.2 (hun
  sleutel is een hash van teksten onder een ouder model) en niet de labels
  van de zeef (die gaan over beelden).

De rol per claim volgt de helft van de zeef (seed 3001): een claim op de
toetshelft wordt nooit lesstof, alleen meetstof.

    python -m doublecheck.rechterset plan|indienen|ophalen|uitschrijven|echt|lezen [--ronde herschikking|taalgrens|toevoeging] [--extra N]
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

MODEL = "claude-haiku-5-5"
PROMPTVERSIE = "rechterset-v2"
PRIJS_IN, PRIJS_UIT = 0.05, 0.25  # batch, dollar per miljoen tokens (2026-10-17)
SOORTEN = ("parafrase", "vertaling", "rolwissel", "getal", "ontkenning")
# De vier antwoorden van de rechter (PLAN #30.3): dezelfde bewering, verwant
# (zelfde onderwerp, andere bewering), iets anders, of de ontkenning ervan.
ANTWOORDEN = ("zelfde", "verwant", "anders", "tegenspraak")
LABEL = {"parafrase": "zelfde", "vertaling": "zelfde", "rolwissel": "verwant", "getal": "verwant",
         "ontkenning": "tegenspraak", "herschikking": "zelfde", "lading": "verwant",
         "ontkenning_vertaald": "tegenspraak", "toevoeging": "verwant"}
STEEKPROEF = 3_000
ZAAD = 3005
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "rechterset"
STEEKPROEVEN = WORTEL / "docs" / "steekproeven"

SYSTEEM = ("You create test pairs for a system that decides whether two texts make the same claim. Never answer, "
           "judge or correct the claim; only rewrite it as asked.")
_OPDRACHT = """Write five variants of this claim, each one sentence, in the language the claim is actually written in (the label above can be wrong), except the translation.
- parafrase: the same claim in other words, with exactly the same meaning. A question stays a question.
- vertaling: the same claim translated into {doeltaal}, with exactly the same meaning.
- rolwissel: swap who did what to whom, or replace the main actor or target with another plausible one, so that it becomes a different claim. Change nothing else and add nothing.
- getal: change exactly one number, date or place; if there is none, one named person or organisation. Change nothing else and add nothing.
- ontkenning: one plain sentence saying that the core of the claim is not so: what a fact-checker would rate as true or false, not a side detail. If the claim is a question or a description (such as "Video of ..."), negate the assertion it implies."""
# De herschikking kwam na de eerste training (BENCHMARK §125): de rolwissels
# leerden de rechter dat omgezette woorden een andere bewering zijn, en hij
# had geen tegenvoorbeeld met dezelfde betekenis.
_HERSCHIKKING = """Rewrite this claim once, keeping the same words as far as possible but in a different order: move a phrase or clause to another place, or split or join sentences. The meaning must stay exactly the same; do not change who did what to whom, and add or drop nothing. Use the language the claim is actually written in (the label above can be wrong)."""


# De taalgrens kwam na de zeef (BENCHMARK §125): over de taalgrens ziet de
# getallen- en ontkenningsregel niets, en de rechter zag "se anexionó" als
# "decided to join" en "bespotte" als "prees".
_TAALGRENS = """Write two variants of this claim, each one sentence, both in {doeltaal}:
- lading: the same event with the same people, place and time, but change the charge or framing of the core of the claim (what a fact-checker would rate), so that it becomes a different claim: for example "annexed" against "decided to join", "mocked" against "praised", "invaded" against "liberated", "protest" against "riot". Do not change a side detail and do not add a clause.
- ontkenning_vertaald: the negation of the core of the claim, saying that it is not so."""


# De toevoeging kwam na de tweede ronde (BENCHMARK §126): "annexed by Russia
# after a referendum in accordance with the rules" bevat het ware feit plus een
# valse lading, en de rechter zag alleen het ware deel.
_TOEVOEGING = """Rewrite this claim once, keeping every word, but add one clause with a contested or false assertion about this specific claim, so that a fact-checker would rate it differently: about its cause, its legality, someone's intent, its scale, its consequence, or who is behind it. Make the addition specific to this claim and plausible to someone who shares it; avoid stock phrases. Do not change anything else. Use the language the claim is actually written in (the label above can be wrong)."""


def _schema(soorten: tuple[str, ...]) -> dict:
    return {"type": "object", "properties": {s: {"type": "string"} for s in soorten},
            "required": list(soorten), "additionalProperties": False}


RONDES = {
    "varianten": {"versie": PROMPTVERSIE, "soorten": SOORTEN, "opdracht": _OPDRACHT, "achtervoegsel": ""},
    "herschikking": {"versie": "rechterset-v3-herschikking", "soorten": ("herschikking",),
                     "opdracht": _HERSCHIKKING, "achtervoegsel": "-herschikking"},
    "taalgrens": {"versie": "rechterset-v5-taalgrens", "soorten": ("lading", "ontkenning_vertaald"),
                  "opdracht": _TAALGRENS, "achtervoegsel": "-taalgrens"},
    "toevoeging": {"versie": "rechterset-v7-toevoeging", "soorten": ("toevoeging",),
                   "opdracht": _TOEVOEGING, "achtervoegsel": "-toevoeging"},
}
_ID = re.compile(r"[^A-Za-z0-9_-]")


def rol(*claim_ids: str) -> str:
    """Leren of meten: de toetshelft van de zeef is nooit lesstof, en een
    paar is meetstof zodra één van zijn claims op de toetshelft staat."""
    from doublecheck.zeef import helft

    return "meten" if any(helft(f"zaak:{c}") == "toets" for c in claim_ids) else "leren"


def verzoek(claim: dict, max_tokens: int = 2_000, ronde: str = "varianten") -> dict:
    r = RONDES[ronde]
    doeltaal = "Spanish" if claim["taal"] == "en" else "English"
    tekst = f"Claim (language: {claim['taal']}):\n{claim['tekst']}\n\n" + r["opdracht"].format(doeltaal=doeltaal)
    return {"custom_id": _ID.sub("_", claim["claim_id"])[:64],
            "params": {"model": MODEL, "max_tokens": max_tokens, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": tekst}],
                       "output_config": {"effort": "low",
                                         "format": {"type": "json_schema", "schema": _schema(r["soorten"])}}}}


def _woorden(tekst: str) -> list[str]:
    """Woorden op spaties, zonder leestekens; combinerende tekens blijven
    staan. In een schrift zonder spaties is de hele zin één woord."""
    return ["".join(t for t in w if not unicodedata.category(t).startswith("P")) or w for w in tekst.casefold().split()]


def _alleen_toegevoegd(claim: str, variant: str) -> bool:
    """Staat de claim woord voor woord en in volgorde in de variant? Dan is er
    alleen iets bijgekomen; een rolwissel zet woorden juist om."""
    rest = iter(_woorden(variant))
    return all(woord in rest for woord in _woorden(claim))


def paren_uit_varianten(claim: dict, antwoord: dict, prompt: str = PROMPTVERSIE) -> list[dict]:
    """De paren met hun label: de variant is de vraag, de claim uit de index
    de kandidaat, zoals in het echt. Lege of onveranderde varianten vallen weg,
    en een rolwissel of ander getal dat alleen iets toevoegt ook: dat is een
    preciezere versie van dezelfde bewering, geen andere."""
    uit = []
    for soort in (s for s in LABEL if s in antwoord):
        variant = " ".join((antwoord.get(soort) or "").split())
        if not variant or variant.casefold() == claim["tekst"].strip().casefold():
            continue
        if LABEL[soort] == "verwant" and soort != "toevoeging" and _alleen_toegevoegd(claim["tekst"], variant):
            continue
        paar = {"vraag": variant, "kandidaat": claim["tekst"], "label": LABEL[soort], "soort": soort,
                "claim_id": claim["claim_id"], "zaak": claim["claim_id"], "taal": claim["taal"],
                "rol": rol(claim["claim_id"]), "bron": "gemaakt", "prompt": prompt, "richting": "heen"}
        om = paar | {"vraag": claim["tekst"], "kandidaat": variant, "richting": "om"}
        if soort == "toevoeging":
            # Insluiten is niet symmetrisch (BENCHMARK §127): een gecheckte claim
            # die meer beweert dan de vraag, is iets anders; een vraag die de
            # claim doet plus meer (een artikel), hoort wel bij die check.
            uit.append(om)
            continue
        # Elk ander paar ook omgedraaid (BENCHMARK §126): vervangen is
        # symmetrisch, en alle soorten, anders raakt de lesstof scheef naar
        # *niet hetzelfde*.
        uit += [paar, om]
    return uit


def samen(eerder: list[dict], nieuw: list[dict]) -> list[dict]:
    """De claimlijst groeit alleen: een eerdere claim blijft staan, zodat zijn
    antwoorden hun claim houden."""
    gezien = {c["claim_id"] for c in eerder}
    return eerder + [c for c in nieuw if c["claim_id"] not in gezien]


def label_minimaal_paar(leeslabel: str) -> str | None:
    """De leesproef van #30.1b als rechterlabel: stijl blijft dezelfde
    bewering, vervalsing, standpunt en vandalisme maken er een andere bewering
    over hetzelfde van; een toevoeging is geen van beide."""
    return {"stijl": "zelfde", "vervalsing": "verwant", "standpunt": "verwant", "vandalisme": "verwant"}.get(leeslabel)


def label_veto(leeslabel: str) -> str | None:
    """De vetolabels van #25.14d: onterecht uit elkaar getrokken is dezelfde
    bewering, terecht is een andere bewering over hetzelfde (de paren lagen
    boven 0,91), twijfel doet niet mee."""
    return {"onterecht": "zelfde", "terecht": "verwant"}.get(leeslabel)


def kernparen(kern: list[dict], rood: list[dict], teksten: dict[str, str]) -> list[dict]:
    """De rode uitslagen van de kerncheck als paren: per formulering van het
    feit de claim waarop hij rood kreeg, met het label uit de leesproef.
    Altijd meetstof: op de kern ligt de releasepoort (B33)."""
    per_feit = {f["id"]: f["formuleringen"] for f in kern}
    return [{"vraag": per_feit[r["feit"]][r["index"]]["tekst"], "kandidaat": teksten[r["kandidaat"]], "label": r["label"],
             "soort": "kern", "taal": per_feit[r["feit"]][r["index"]]["taal"], "zaak": f"feit:{r['feit']}",
             "rol": "meten", "bron": "kerncheck"}
            for r in rood if r["kandidaat"] in teksten]


def echte_paren(conn) -> list[dict]:  # pragma: no cover - op de productiedatabase
    """Wat al gelabeld is, als paren voor de rechter."""
    from doublecheck.feitenbasis import PAREN, lees_kern

    teksten = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    taal = dict(conn.execute("SELECT claim_id, language FROM claim"))
    lees = lambda naam: json.loads((STEEKPROEVEN / naam).read_text(encoding="utf-8"))  # noqa: E731
    uit = []
    for sleutel, v in lees("25.14d-vetolabels.json")["paren"].items():
        a, b = sleutel.split("|")
        if label_veto(v["label"]) and a in teksten and b in teksten:
            uit.append({"vraag": teksten[a], "kandidaat": teksten[b], "label": label_veto(v["label"]), "soort": v.get("soort"),
                        "taal": taal[a], "zaak": min(a, b), "rol": rol(a, b), "bron": "25.14d"})
    vraag_claim = dict(conn.execute("SELECT url, claim_id FROM factcheck"))
    for r in lees("28.6c-ander-record.json")["labels"]:
        if r["bron"] == "post" and vraag_claim.get(r["vraag"]) in teksten and r["claim"] in teksten:
            # de notetekst nooit (X Developer Agreement)
            a = vraag_claim[r["vraag"]]
            # anders in #28.6 c is een ander land, moment of beeld bij dezelfde zaak: verwant
            label = {"zelfde": "zelfde", "anders": "verwant"}[r["label"]]
            uit.append({"vraag": teksten[a], "kandidaat": teksten[r["claim"]], "label": label, "soort": "terugkijk",
                        "taal": taal[a], "zaak": min(a, r["claim"]), "rol": rol(a, r["claim"]), "bron": "28.6c"})
    from doublecheck.zeef import helft

    for p in json.loads(PAREN.read_text(encoding="utf-8"))["paren"]:
        if label_minimaal_paar(p.get("label")):
            uit.append({"vraag": p["waar"], "kandidaat": p["nep"], "label": label_minimaal_paar(p["label"]), "soort": p["label"],
                        "taal": "en", "zaak": f"feit:{p['feit']}",
                        "rol": "meten" if helft(f"feit:{p['feit']}") == "toets" else "leren",
                        "bron": "30.1b"})
    for p in lees("21.1-stance-proefset.json")["proefset"]:
        uit.append({"vraag": p["beweert"], "kandidaat": p["claim"], "label": "zelfde", "soort": "beweert", "taal": p["taal"],
                    "zaak": f"stance:{p['claim']}", "rol": "meten", "bron": "21.1"})
        uit.append({"vraag": p["weerlegt"], "kandidaat": p["claim"], "label": "tegenspraak", "soort": "weerlegt",
                    "taal": p["taal"], "zaak": f"stance:{p['claim']}", "rol": "meten", "bron": "21.1"})
    uit += kernparen(lees_kern(), lees("30.3-kernrood.json")["rood"], teksten)
    return uit


def paarsleutel(paar: dict) -> str:
    import hashlib

    return hashlib.sha1(f"{paar['vraag']}\0{paar['kandidaat']}".encode("utf-8")).hexdigest()[:16]


def leesproef(paren: list[dict], n: int = 200) -> list[dict]:
    """De leesproef van de opzet: de n paren met de laagste hash, zodat er
    alleen een paar bijkomt als er nieuwe paren bijkomen."""
    import hashlib

    return sorted(paren, key=lambda p: hashlib.sha256(f"3006:{paarsleutel(p)}".encode()).hexdigest())[:n]


def kies(conn, n: int = STEEKPROEF, zaad: int = ZAAD) -> list[dict]:  # pragma: no cover - op de productiedatabase
    """Een steekproef van claims in de index, gelaagd naar taal: per taal naar
    rato, met een vloer van 20, teksten van 30 tot 300 tekens."""
    from doublecheck.search import _buiten_index

    buiten = _buiten_index(conn)
    per_taal: dict[str, list] = {}
    for claim_id, tekst, taal in conn.execute("SELECT claim_id, canonical_text, language FROM claim"):
        if claim_id in buiten or not tekst or not 30 <= len(tekst) <= 300:
            continue
        per_taal.setdefault(taal or "und", []).append({"claim_id": claim_id, "tekst": tekst, "taal": taal or "und"})
    totaal = sum(len(v) for v in per_taal.values())
    rnd = random.Random(zaad)
    uit = []
    for taal, claims in sorted(per_taal.items()):
        k = min(len(claims), max(20, round(n * len(claims) / totaal)))
        uit += rnd.sample(claims, k)
    rnd.shuffle(uit)
    return uit


def main() -> None:  # pragma: no cover
    import argparse
    import os
    import sqlite3

    parser = argparse.ArgumentParser(description="De rechterset (PLAN #30.3)")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "uitschrijven", "echt", "lezen"))
    parser.add_argument("--n", type=int, default=STEEKPROEF)
    parser.add_argument("--ronde", choices=tuple(RONDES), default="varianten")
    parser.add_argument("--lees", type=int, default=200, help="lezen: hoeveel paren")
    parser.add_argument("--extra", type=int, default=0,
                        help="een tweede steekproef van N claims erbij (ander zaad); de lijst groeit alleen")
    parser.add_argument("--proef", type=int, help="alleen de eerste N claims indienen")
    parser.add_argument("--opnieuw", action="store_true",
                        help="ingediende claims zonder bruikbaar antwoord opnieuw, met 6.000 tokens: Indische"
                             " schriften kosten veel tokens per woord")
    args = parser.parse_args()
    db = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "echt":
        paren = echte_paren(conn)
        (UIT / "echt.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in paren),
                                        encoding="utf-8")
        print(f"{len(paren)} echte paren; {dict(Counter((p['bron'], p['rol'], p['label']) for p in paren))}")
        return
    lijst = UIT / "claims.jsonl"
    claims = ([json.loads(r) for r in lijst.read_text(encoding="utf-8").splitlines()] if lijst.exists()
              else kies(conn, args.n))
    if args.extra:
        claims = samen(claims, kies(conn, args.extra, zaad=ZAAD + 1))
        lijst.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
        print(f"{len(claims)} claims in de lijst")
    ronde = RONDES[args.ronde]
    logboek = UIT / f"batches{ronde['achtervoegsel']}.jsonl"
    antwoorden = UIT / f"antwoorden{ronde['achtervoegsel']}.jsonl"
    if args.stap == "plan":
        tokens_in = sum(len(c["tekst"]) // 4 + 260 for c in claims)
        kosten = (tokens_in * PRIJS_IN + len(claims) * 450 * PRIJS_UIT) / 1e6
        print(f"{len(claims)} claims in {len({c['taal'] for c in claims})} talen; "
              f"rol {dict(Counter(rol(c['claim_id']) for c in claims))}; naar schatting ${kosten:.2f}")
        return
    if args.stap == "indienen":
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        lijst.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
        ingediend = {i for r in (logboek.read_text(encoding="utf-8").splitlines() if logboek.exists() else [])
                     for i in json.loads(r)["ids"]}
        if args.opnieuw:
            beantwoord = {json.loads(r)["id"] for r in antwoorden.read_text(encoding="utf-8").splitlines()}
            verzoeken = [verzoek(c, 6_000, args.ronde) for c in claims if c["claim_id"] in ingediend - beantwoord]
        else:
            verzoeken = [verzoek(c, ronde=args.ronde) for c in claims if c["claim_id"] not in ingediend][:args.proef]
        if not verzoeken:
            print("alles is al ingediend")
            return
        batch = anthropic.Anthropic().messages.batches.create(requests=verzoeken)
        with logboek.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": ronde["versie"],
                                "ids": [v["custom_id"] for v in verzoeken]}) + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} claims")
    elif args.stap == "ophalen":
        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        pad = antwoorden
        klaar = {json.loads(r)["id"] for r in pad.read_text(encoding="utf-8").splitlines()} if pad.exists() else set()
        batches = [json.loads(r) for r in logboek.read_text(encoding="utf-8").splitlines()]
        with pad.open("a", encoding="utf-8") as uit:
            for b in reversed(batches):
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    continue
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded" or r.custom_id in klaar:
                        continue
                    tekst = next((c.text for c in r.result.message.content if c.type == "text"), "{}")
                    try:
                        antwoord = json.loads(tekst)
                    except json.JSONDecodeError:
                        continue
                    uit.write(json.dumps({"id": r.custom_id, "antwoord": antwoord}, ensure_ascii=False) + "\n")
                    klaar.add(r.custom_id)
        print(f"{len(klaar)} antwoorden")
    elif args.stap == "uitschrijven":
        bij_id = {_ID.sub("_", c["claim_id"])[:64]: c for c in
                  (json.loads(r) for r in (UIT / "claims.jsonl").read_text(encoding="utf-8").splitlines())}
        paren = []
        for r_ in RONDES.values():
            pad = UIT / f"antwoorden{r_['achtervoegsel']}.jsonl"
            for r in (json.loads(x) for x in (pad.read_text(encoding="utf-8").splitlines() if pad.exists() else [])):
                if r["id"] in bij_id:
                    paren += paren_uit_varianten(bij_id[r["id"]], r["antwoord"], r_["versie"])
        (UIT / "paren.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in paren),
                                         encoding="utf-8")
        print(f"{len(paren)} paren; {dict(Counter((p['soort'], p['rol']) for p in paren))}")
    else:
        paren = [json.loads(r) for r in (UIT / "paren.jsonl").read_text(encoding="utf-8").splitlines()]
        for p in leesproef([p for p in paren if p["prompt"] == ronde["versie"]], args.lees):
            print(f"{paarsleutel(p)} [{p['soort']} → {p['label']}] ({p['taal']})\n  K: {p['kandidaat']}\n"
                  f"  V: {p['vraag']}")


if __name__ == "__main__":
    main()
