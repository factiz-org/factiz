"""Privépersonen in een bewering: hoeveel factchecks noemen er een (PLAN #34.2bw, maatregel 2).

Stand 2 zet elke factcheck één keer open voor zoekmachines. Een bewering kan een privépersoon bij naam noemen: een
slachtoffer, een verdachte, een buurman in een filmpje. De juridische verkenning raadt daar initialen of een rol aan, en
`noindex` bij misdaad, ziekte of seksualiteit. De PO verwacht dat het er weinig zijn (2026-11-22: "echte privépersonen
niet, maar ik verwacht dat die bij factchecks er weinig zijn"). Deze meting telt het: Haiku leest een steekproef van de
uitgave en noemt per bewering een privépersoon met de naam zoals die er staat en de context (`privepersoon-v1`, tien per
vraag, direct); ik lees elke *ja* en *twijfel* na, en een vaste greep uit de *nee* om te zien wat Haiku mist.

    python -m doublecheck.privepersonen vragen [--proef N]|lezen|tellen|indienen|ophalen [--wacht M]|tweede

`vragen`, `lezen` en `tellen` zijn de meting op de steekproef; `indienen` en `ophalen` de volle ronde over de hele uitgave
via de Batch API (openbare beweringen), voor de afscherming in de uitgave; `tweede` laat Sonnet elke minderjarige in een
gevoelige context nog eens lezen, want alleen dan staat op de plek van de naam de sticker *naam weggelaten* (`uitgave_invoer`).

Leest de nieuwste publicatiedatabase (openbare beweringen), alleen-lezen. Uitvoer in `data/privepersonen/`; mijn lezing in
`docs/steekproeven/34.2bw-privepersonen.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "privepersonen"
ANTWOORDEN = MAP / "antwoorden.jsonl"   # de meting op de steekproef
VOL = MAP / "vol.jsonl"                 # de volle ronde over de hele uitgave, voor de afscherming
BATCHES = MAP / "batches.jsonl"
TWEEDE_ANTWOORDEN = MAP / "tweede.jsonl"   # de tweede lezing van een minderjarige, door Sonnet
LABELS = WORTEL / "docs" / "steekproeven" / "34.2bw-privepersonen.json"
VERSIE = "privepersoon-v1"
ZAAD = 2214
PROEF_N = 500
NEE_LEZEN = 100        # zoveel *nee* lees ik na, om te zien wat Haiku mist
PER_VRAAG = 10
DRADEN = 8
GRENS = 5.00           # dollar, alles samen: de meting kostte $0,02, de volle ronde via de Batch API ~$2,30
SCHATTING = 0.00015    # per bewering, direct, tien per vraag (gemeten: $0,000042)
SCHATTING_BATCH = 0.00003
OORDELEN = ("ja", "nee", "twijfel")
CONTEXTEN = ("misdaad", "ziekte", "dood", "seksualiteit", "anders", "geen")
LEESLABELS = ("prive", "publiek", "geen", "twijfel")
GEVOELIG = ("misdaad", "ziekte", "dood", "seksualiteit")    # B73 en de verkenning: hier gaat een pagina buiten zoekmachines
TWEEDE = "minderjarig-v1"
TWEEDE_GRENS = 2.00


class Weigering(Exception):
    pass


def verzoek(teksten: list[str]) -> dict:
    """Eén vraag over een rijtje beweringen, in welke taal ook."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You read claims from a public archive of fact-checks, in many languages. For each numbered claim, decide whether "
        "it names a private individual.\n"
        "\n"
        "prive:\n"
        "- \"ja\": the claim names a specific private individual, a person who is not a public figure, identified by name: "
        "a full name, a first name with a surname or a place, or the social media handle of a private person. For "
        "example a victim, a suspect, a patient, a nurse, a teacher, a neighbour, a relative of a public figure without a "
        "public role of their own, or an ordinary person in a viral photo or video.\n"
        "- \"nee\": the claim names no person, or only public figures: politicians and officials at any level, members of "
        "royal families, heads of companies and organisations, celebrities, artists, athletes, journalists and "
        "presenters, scientists and doctors who speak publicly in that role, religious leaders, well-known influencers, "
        "and people named because of their public office. A description without a name (\"a woman in Rotterdam\", "
        "\"this man\") is \"nee\".\n"
        "- \"twijfel\": the claim names a person and you cannot tell whether they are a public figure.\n"
        "\n"
        "naam: for ja or twijfel, the name exactly as written in the claim, in the same script and spelling; otherwise "
        "empty.\n"
        "context: what the claim says about that private individual: \"misdaad\" (a crime, an accusation, an arrest, a "
        "trial), \"ziekte\" (an illness, an injury, a vaccine reaction, a disability), \"dood\" (a death or an accident), "
        "\"seksualiteit\" (sexual orientation or sexual acts), \"anders\" (anything else); \"geen\" when prive is nee.\n"
        "minderjarig: true if that private individual is presented as a minor, a child or a teenager.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["nr", "prive", "naam", "context", "minderjarig"],
            "properties": {"nr": {"type": "integer"}, "prive": {"type": "string", "enum": list(OORDELEN)},
                           "naam": {"type": "string"}, "context": {"type": "string", "enum": list(CONTEXTEN)},
                           "minderjarig": {"type": "boolean"}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 3000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_oordelen(tekst: str | None, teksten: list[str]) -> list[dict | None]:
    """De antwoorden op nummer. Een *ja* of *twijfel* telt alleen met een naam die letterlijk in de bewering staat
    (hoofdletters en witruimte tellen niet); een nummer dat ontbreekt of twee keer voorkomt, of een onbekende waarde,
    telt niet."""
    uit: list[dict | None] = [None] * len(teksten)
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        nummers = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        try:
            nr, prive, naam, context = a["nr"], a["prive"], " ".join(str(a["naam"]).split()), a["context"]
        except (KeyError, TypeError):
            continue
        if not isinstance(nr, int) or not 1 <= nr <= len(teksten) or nummers[nr] != 1:
            continue
        if prive not in OORDELEN or context not in CONTEXTEN:
            continue
        if prive != "nee" and (not naam or naam.casefold() not in " ".join((teksten[nr - 1] or "").split()).casefold()):
            continue
        uit[nr - 1] = {"prive": prive, "naam": naam if prive != "nee" else "", "context": context,
                       "minderjarig": bool(a.get("minderjarig"))}
    return uit


def steekproef(paginas: list[str], n: int = PROEF_N) -> list[str]:
    """De pagina's van de meting: willekeurig, bij dezelfde pagina's altijd dezelfde, en een kleinere proef is het begin."""
    return random.Random(ZAAD).sample(sorted(paginas), min(PROEF_N, len(paginas)))[:n]


def _laatste(antwoorden: list[dict]) -> dict[str, dict]:
    return {a["pagina"]: a for a in antwoorden if a.get("prive") and a.get("versie") == VERSIE}


def te_lezen(antwoorden: list[dict]) -> list[str]:
    """Wat ik nalees: elke *ja* en *twijfel*, en een vaste greep van `NEE_LEZEN` uit de *nee*."""
    laatste = _laatste(antwoorden)
    ja = sorted(p for p, a in laatste.items() if a["prive"] != "nee")
    nee = sorted(p for p, a in laatste.items() if a["prive"] == "nee")
    return ja + random.Random(ZAAD).sample(nee, min(NEE_LEZEN, len(nee)))


def _wilson_boven(k: float, n: int, z: float = 1.96) -> float:
    if not n:
        return 1.0
    p = k / n
    return (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def telling(antwoorden: list[dict], pad: str | Path = LABELS) -> dict:
    """Het aandeel beweringen met een privépersoon: wat ik bij een *ja* of *twijfel* als privépersoon las, plus wat ik in
    de greep uit de *nee* vond, opgeschaald naar de hele groep *nee*; met de bovengrens van 95% (Wilson). Weigert zolang
    iets dat ik moet nalezen geen label heeft."""
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        labels = {}
    open_ = [p for p in te_lezen(antwoorden) if labels.get(p, {}).get("label") not in LEESLABELS]
    if open_:
        raise Weigering(f"{len(open_)} nog te lezen in {pad}")
    laatste = _laatste(antwoorden)
    nee = [p for p, a in laatste.items() if a["prive"] == "nee"]
    greep = [p for p in te_lezen(antwoorden) if laatste[p]["prive"] == "nee"]
    prive = [p for p, a in laatste.items() if a["prive"] != "nee" and labels[p]["label"] == "prive"]
    gemist = [p for p in greep if labels[p]["label"] == "prive"]
    n = len(laatste)
    schatting = len(prive) + (len(gemist) * len(nee) / len(greep) if greep else 0.0)
    gevoelig = Counter(labels[p].get("gevoelig", "geen") for p in prive + gemist)
    gevoelig.pop("geen", None)
    return {"n": n, "prive": len(prive), "gemist": len(gemist), "greep": len(greep),
            "twijfel": sum(labels[p]["label"] == "twijfel" for p in te_lezen(antwoorden)),
            "aandeel": schatting / n if n else 0.0, "boven": _wilson_boven(schatting, n), "gevoelig": dict(gevoelig),
            "minderjarig": sum(bool(labels[p].get("minderjarig")) for p in prive + gemist)}


# --- de afscherming in de uitgave (maatregel 2) -----------------------------------------------------------------------

def afschermen(lezing: dict) -> bool:
    """Of een pagina buiten zoekmachines blijft: een privépersoon bij naam (of twijfel) bij een misdaad, ziekte, dood of
    seksualiteit, of een minderjarige. Een privépersoon in een onschuldig verhaal blijft vindbaar."""
    return lezing.get("prive") in ("ja", "twijfel") and (lezing.get("context") in GEVOELIG or bool(lezing.get("minderjarig")))


def tweede_verzoek(items: list[tuple[str, str]]) -> dict:
    """De tweede lezing bij een minderjarige (Sonnet): gaat het om de genoemde persoon zelf? In de steekproef noemde Haiku
    een raadslid minderjarig omdat het slachtoffer een kind was."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "Each numbered item is a claim from a public archive of fact-checks and a name that appears in it. Answer about "
        "the named person themself, never about anyone else in the claim.\n"
        "prive: true if the named person is a private individual, not a public figure. Public figures are politicians and "
        "officials at any level, members of royal families, heads of companies and organisations, celebrities, artists, "
        "athletes, journalists, presenters, religious leaders and well-known influencers.\n"
        "minderjarig: true if the named person themself is presented as under 18, a child or a teenager.\n"
        "gevoelig: true if the claim presents the named person as a victim or suspect of a crime, as ill or injured, as "
        "dead, or in a sexual context.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "prive", "minderjarig", "gevoelig"],
            "properties": {"nr": {"type": "integer"}, "prive": {"type": "boolean"}, "minderjarig": {"type": "boolean"},
                           "gevoelig": {"type": "boolean"}}}}}}
    vraag = "\n\n".join(f"{i}. Claim: {' '.join(t.split())}\nName: {n}" for i, (t, n) in enumerate(items, 1))
    return {"model": MODELLEN["sonnet"]["id"], "max_tokens": 2000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_tweede(tekst: str | None, n: int) -> list[dict | None]:
    """De tweede lezing op nummer; een nummer dat ontbreekt, twee keer voorkomt of geen ja of nee is, telt niet."""
    uit: list[dict | None] = [None] * n
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        nummers = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr = a.get("nr") if isinstance(a, dict) else None
        if not isinstance(nr, int) or not 1 <= nr <= n or nummers[nr] != 1:
            continue
        if all(isinstance(a.get(k), bool) for k in ("prive", "minderjarig", "gevoelig")):
            uit[nr - 1] = {k: a[k] for k in ("prive", "minderjarig", "gevoelig")}
    return uit


def _per_pagina(rijen: list[dict], versie: str, sleutel: str) -> dict[str, dict]:
    return {r["pagina"]: r for r in rijen if r.get("versie") == versie and r.get(sleutel) is not None}


def uitgave_invoer(vol: list[dict], tweede: list[dict]) -> dict[str, dict]:
    """Wat de uitgave van de lezing krijgt, per pagina: de tekst die gelezen is (`bron`; de uitgave neemt het alleen over
    bij precies die tekst) en of de pagina buiten zoekmachines blijft. De naam gaat alleen mee om haar te vervangen door
    de sticker *naam weggelaten*, bij een minderjarige in een gevoelige context die de tweede lezing bij precies deze
    tekst en naam bevestigde. Een pagina zonder geldige lezing staat er niet in; de uitgave noemt haar *niet gelezen*."""
    bevestigd = _per_pagina(tweede, TWEEDE, "prive")
    uit: dict[str, dict] = {}
    for pagina, l in _per_pagina(vol, VERSIE, "prive").items():
        rij = {"bron": l["bewering"], "afschermen": afschermen(l)}
        t = bevestigd.get(pagina)
        if (rij["afschermen"] and t and t["bewering"] == l["bewering"] and t["naam"] == l["naam"]
                and t["prive"] and t["minderjarig"] and t["gevoelig"]):
            rij["naam"] = l["naam"]
        uit[pagina] = rij
    return uit


def voor_de_uitgave() -> dict[str, dict]:  # pragma: no cover - bestanden
    return uitgave_invoer(_jsonl(VOL), _jsonl(TWEEDE_ANTWOORDEN))


def tweede_kandidaten(vol: list[dict]) -> list[dict]:
    """Wat de tweede lezing krijgt: elke lezing met een minderjarige in een gevoelige context."""
    return [l for l in _per_pagina(vol, VERSIE, "prive").values()
            if l["prive"] != "nee" and l.get("minderjarig") and l.get("context") in GEVOELIG]


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _paginas() -> dict[str, str]:  # pragma: no cover - een bestand
    """Elke bewering van de nieuwste uitgave, op nummer."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    return dict(pub.execute("SELECT nummer, bewering FROM pagina"))


def _vragen(proef: int | None) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(ANTWOORDEN)
    klaar = set(_laatste(eerder))
    paginas = _paginas()
    werk = [p for p in steekproef(list(paginas), proef or PROEF_N) if p not in klaar]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(a.get("kosten", 0.0) for a in eerder)
    if uitgegeven + SCHATTING * len(werk) > GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} uitgegeven plus ${SCHATTING * len(werk):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[str]) -> None:
        teksten = [paginas[p] for p in groep]
        try:
            msg = client.messages.create(**verzoek(teksten))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for p, t, a in zip(groep, teksten, lees_oordelen(tekst, teksten)):
                f.write(json.dumps({"pagina": p, "bewering": t, **(a or {"prive": None}), "versie": VERSIE,
                                    "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]))
    nu = _jsonl(ANTWOORDEN)
    laatste = _laatste(nu)
    print(f"{len(laatste)} gelezen, {sum(not a.get('prive') for a in nu)} zonder geldig antwoord;",
          Counter(a["prive"] for a in laatste.values()), f"${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    return (sum(a.get("kosten", 0.0) for a in _jsonl(ANTWOORDEN) + _jsonl(VOL))
            + sum(b["schatting"] for b in _jsonl(BATCHES) if b.get("werkelijk") is None))


def _indienen() -> None:  # pragma: no cover - de Batch API, op openbare beweringen
    """De volle ronde: elke bewering van de uitgave die nog geen antwoord van deze versie heeft, met haar tekst."""
    from datetime import date

    import anthropic

    from doublecheck.varianten import laad_sleutel

    klaar = {(a["pagina"], a["bewering"]) for a in _jsonl(VOL) if a.get("prive") and a.get("versie") == VERSIE}
    lopend = {p for b in _jsonl(BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    werk = [(p, t) for p, t in sorted(_paginas().items()) if (p, t) not in klaar and p not in lopend]
    if not werk:
        print("niets te vragen")
        return
    from doublecheck import routinegrens as rg

    schatting = SCHATTING_BATCH * len(werk)
    if rg.uitgave():            # onder de routine per week telt haar ruimte, niet de grens voor altijd (PLAN #35.2)
        if not rg.past(schatting):
            raise Weigering(f"geschat ${schatting:.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
    elif _uitgegeven() + schatting > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${schatting:.2f} is meer dan ${GRENS:.2f}")
    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
    laad_sleutel()
    client = anthropic.Anthropic(max_retries=6)
    batch = client.messages.batches.create(requests=[{"custom_id": f"g{i}", "params": verzoek([t for _, t in g])}
                                                     for i, g in enumerate(groepen)])
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / f"batch-{batch.id}.json").write_text(json.dumps({f"g{i}": g for i, g in enumerate(groepen)}, ensure_ascii=False),
                                                encoding="utf-8")
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rg.merk({"id": batch.id, "paginas": [p for p, _ in werk], "schatting": round(schatting, 4),
                                    "versie": VERSIE, "dag": date.today().isoformat(), "werkelijk": None})) + "\n")
    print(f"batch {batch.id}: {len(werk)} beweringen in {len(groepen)} vragen, schatting ${schatting:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        batches, open_ = _jsonl(BATCHES), 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            groepen = json.loads((MAP / f"batch-{b['id']}.json").read_text(encoding="utf-8"))
            werkelijk, uitslag = 0.0, Counter()
            with VOL.open("a", encoding="utf-8") as f:
                for r in client.messages.batches.results(b["id"]):
                    groep = groepen.get(r.custom_id) or []
                    if not groep or r.result.type != "succeeded":
                        uitslag["zonder"] += len(groep)
                        continue
                    msg = r.result.message
                    kosten = kosten_batch(bc.gebruik_uit(msg), "haiku")
                    werkelijk += kosten
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(x, "text", "") or "" for x in msg.content)
                    for (p, t), a in zip(groep, lees_oordelen(tekst, [t for _, t in groep])):
                        uitslag[a["prive"] if a else "zonder"] += 1
                        f.write(json.dumps({"pagina": p, "bewering": t, **(a or {"prive": None}), "versie": b["versie"],
                                            "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
            BATCHES.write_text("".join(json.dumps(x) + "\n" for x in batches), encoding="utf-8")
            print(f"batch {b['id']}: {dict(uitslag)}, ${werkelijk:.2f}")
        if not open_ or time.time() > einde:
            print(f"{open_} batches nog open; samen ${_uitgegeven():.2f} van ${GRENS:.2f}")
            return
        time.sleep(60)


def _tweede() -> None:  # pragma: no cover - een model, op openbare beweringen
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(TWEEDE_ANTWOORDEN)
    klaar = {(r["pagina"], r["bewering"], r["naam"]) for r in eerder if r.get("versie") == TWEEDE and r.get("prive") is not None}
    werk = [l for l in tweede_kandidaten(_jsonl(VOL)) if (l["pagina"], l["bewering"], l["naam"]) not in klaar]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(r.get("kosten", 0.0) for r in eerder)
    if uitgegeven + 0.002 * len(werk) > TWEEDE_GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} plus ${0.002 * len(werk):.2f} is meer dan ${TWEEDE_GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["sonnet"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[dict]) -> None:
        try:
            msg = client.messages.create(**tweede_verzoek([(l["bewering"], l["naam"]) for l in groep]))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, TWEEDE_ANTWOORDEN.open("a", encoding="utf-8") as f:
            for l, a in zip(groep, lees_tweede(tekst, len(groep))):
                f.write(json.dumps({"pagina": l["pagina"], "bewering": l["bewering"], "naam": l["naam"],
                                    **(a or {"prive": None}), "versie": TWEEDE, "kosten": round(kosten / len(groep), 7)},
                                   ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]))
    nu = _per_pagina(_jsonl(TWEEDE_ANTWOORDEN), TWEEDE, "prive")
    bevestigd = sum(r["prive"] and r["minderjarig"] and r["gevoelig"] for r in nu.values())
    print(f"{len(nu)} gelezen, {bevestigd} bevestigd; ${sum(r.get('kosten', 0.0) for r in _jsonl(TWEEDE_ANTWOORDEN)):.3f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["vragen", "lezen", "tellen", "indienen", "ophalen", "tweede"])
    p.add_argument("--proef", type=int)
    p.add_argument("--wacht", type=int, default=0, help="minuten wachten tot de batch klaar is")
    a = p.parse_args()
    try:
        if a.stap == "vragen":
            return _vragen(a.proef)
        if a.stap == "indienen":
            return _indienen()
        if a.stap == "ophalen":
            return _ophalen(a.wacht)
        if a.stap == "tweede":
            return _tweede()
        antwoorden = _jsonl(ANTWOORDEN)
        if a.stap == "lezen":
            laatste = _laatste(antwoorden)
            uit = [{"pagina": p, **{k: laatste[p][k] for k in ("bewering", "prive", "naam", "context", "minderjarig")
                                    if k in laatste[p]}} for p in te_lezen(antwoorden)]
            MAP.mkdir(parents=True, exist_ok=True)
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", len(uit), Counter(x["prive"] for x in uit))
            return
        t = telling(antwoorden)
        print(f"{t['n']} beweringen gelezen; {t['prive']} met een privépersoon bij Haiku's ja, {t['gemist']} gemist in "
              f"{t['greep']} nee; geschat {t['aandeel']:.1%} (hoogstens {t['boven']:.1%}); gevoelig {t['gevoelig']}, "
              f"minderjarig {t['minderjarig']}, twijfel {t['twijfel']}")
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
