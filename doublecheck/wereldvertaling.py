"""De wereldlijst vertaald (PLAN #37.12 punt 5, SPECS E10.S6 AC9; PO 2026-11-23: "Ja, werk het uit", na "Ik wil me wel
nadrukkelijk positioneren als een wereldwijd systeem"): elk gepubliceerd overzicht in alle andere talen van de site, zoals
de eigen checks (`eigenvertaling`).

    python -m doublecheck.wereldvertaling plan                     # wat nog vertaald moet worden, en de schatting
    python -m doublecheck.wereldvertaling indienen [--proef N]     # Sonnet via de Batch API, binnen de grens van de week
    python -m doublecheck.wereldvertaling ophalen [--wacht M]      # de antwoorden nakijken en wegschrijven

Per overzicht en taal één bestand `content/wereldlijst/vertalingen/<sleutel>/<taal>.json`: de bewering, wat de redacties
vonden en waar het rondging, de maker en de vingerafdruk van de tekst die vertaald werd. Een antwoord telt alleen met
dezelfde velden, lijsten en bronnummers en zonder lang streepje (`eigenvertaling.lees_antwoord`). Eén grens met de eigen
checks: samen hoogstens `eigenvertaling.GRENS` per week; wat niet past, schuift naar de week erna. De overzichten zijn
openbaar werk van Factiz over openbare factchecks (B54: de Batch API voor offline werk op openbare data).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from doublecheck import eigenvertaling as ev

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "content" / "wereldlijst" / "vertalingen"
BATCHES = WORTEL / "data" / "wereldvertaling" / "batches.jsonl"
VERSIE = "wereldvertaling-v1"
MODEL = ev.MODEL

_SYSTEEM = """You translate a short overview by Factiz into another language, for readers in that language. The overview
says what a false or misleading claim says (in Factiz's own words, not a quote), what professional fact-checkers found, and
where the claim circulated.

Rules:
- Translate faithfully and completely. Do not add, explain, soften, sharpen or leave out anything.
- Keep every source number such as [2] exactly as it is, attached to the same statement.
- Keep names of people, newsrooms, platforms and organisations, and numbers, dates and amounts as they are; write dates and
  numbers the way the target language writes them.
- No em dashes and no exclamation marks.
- Answer with one JSON object only: the same keys as the input "velden", lists with the same number of items, nothing else.
"""


def bron(o: dict) -> dict:
    """Wat een lezer van een overzicht leest: de bewering, wat de redacties vonden en waar het rondging."""
    uit = {"bewering": o["bewering"], "kern": list(o["kern"])}
    if o.get("rondgang"):
        uit["rondgang"] = o["rondgang"]
    return uit


def vingerafdruk(o: dict) -> str:
    return hashlib.sha256(json.dumps(bron(o), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def doeltalen(o: dict) -> list[str]:
    return [t for t in ev.TALEN if t != (o.get("taal") or "en")]


def pad(sleutel: str, taal: str, map_: Path = MAP) -> Path:
    return Path(map_) / sleutel / f"{taal}.json"


def bestand(o: dict, taal: str, velden: dict, maker: str) -> dict:
    return {"_meta": (f"Machinevertaling ({o.get('taal') or 'en'} naar {taal}) van het overzicht {o['sleutel']} van de "
                      f"wereldlijst van Factiz, door {maker}; doublecheck/wereldvertaling.py, PLAN #37.12."),
            "taal": taal, "brontaal": o.get("taal") or "en", "vingerafdruk": vingerafdruk(o), "maker": maker, "velden": velden}


def schrijf(p: Path, v: dict) -> None:
    ev.schrijf(p, v)


def geldig(o: dict, v: dict | None) -> bool:
    """Zolang de tekst die vertaald werd niet veranderde, en elke tekst echt vertaald is (`eigenvertaling.onvertaald`)."""
    return (bool(v) and v.get("vingerafdruk") == vingerafdruk(o) and isinstance(v.get("velden"), dict)
            and not ev.onvertaald(bron(o), v["velden"]))


def geldige(o: dict, map_: Path = MAP) -> dict[str, dict]:
    """De geldige vertalingen van een overzicht per taal, als `{taal: {"velden": ..., "maker": ...}}`."""
    uit = {}
    for taal in doeltalen(o):
        p = pad(o["sleutel"], taal, map_)
        if p.exists():
            v = json.loads(p.read_text(encoding="utf-8"))
            if geldig(o, v):
                uit[taal] = {"velden": v["velden"], "maker": v["maker"]}
    return uit


def nog_te_doen(overzichten: list[dict], map_: Path = MAP) -> list[tuple[str, str]]:
    """Per gepubliceerd overzicht de talen zonder geldige vertaling; een concept wordt niet vertaald."""
    uit = []
    for o in overzichten:
        if o.get("status") == "gepubliceerd":
            klaar = geldige(o, map_)
            uit += [(o["sleutel"], t) for t in doeltalen(o) if t not in klaar]
    return uit


def verzoek(o: dict, taal: str) -> dict:
    from doublecheck.modellen import MODELLEN

    vraag = {"doeltaal": ev.TALEN[taal], "brontaal": ev.TALEN[o.get("taal") or "en"], "velden": bron(o)}
    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 8000, "system": _SYSTEEM,
            "messages": [{"role": "user", "content": json.dumps(vraag, ensure_ascii=False)}]}


def schatting(overzichten: list[dict], te_doen: list[tuple[str, str]]) -> float:
    """Zoals `eigenvertaling.schatting`, met dezelfde ijking."""
    from doublecheck.modellen import MODELLEN

    lengte = {o["sleutel"]: len(json.dumps(bron(o), ensure_ascii=False)) for o in overzichten}
    tok_in = sum(lengte[s] / 3 + 500 for s, _ in te_doen)
    tok_uit = sum(lengte[s] / 2.5 for s, _ in te_doen)
    return ev.KALIBRATIE * (tok_in * MODELLEN[MODEL]["in"] + tok_uit * MODELLEN[MODEL]["uit"]) / 1e6


def uitgegeven(dag: str, eigen: list[dict], wereld: list[dict]) -> float:
    """Wat de vertalingen in de week van `dag` kostten: de eigen checks en de wereldlijst samen, onder één grens."""
    return ev.weekbedrag(eigen, dag) + ev.weekbedrag(wereld, dag)


def binnen_grens(overzichten: list[dict], te_doen: list[tuple[str, str]], ruimte: float) -> list[tuple[str, str]]:
    """Wat er deze week nog in past, per overzicht alle talen samen voor het volgende overzicht begint."""
    gekozen: list[tuple[str, str]] = []
    for vraag in te_doen:
        if schatting(overzichten, gekozen + [vraag]) <= ruimte:
            gekozen.append(vraag)
    return gekozen


def _ruimte() -> float:
    from datetime import date

    return ev.GRENS - uitgegeven(date.today().isoformat(), ev._jsonl(ev.BATCHES), ev._jsonl(BATCHES))


def _indienen(proef: int | None) -> None:  # pragma: no cover - de Batch API
    from datetime import date

    import anthropic

    from doublecheck import wereldlijst as wl
    from doublecheck.varianten import laad_sleutel

    alle = {o["sleutel"]: o for o in wl.lees_alle()}
    open_ = {(s, t) for b in ev._jsonl(BATCHES) if b.get("werkelijk") is None for s, t in b["vragen"]}
    te_doen = [x for x in nog_te_doen(list(alle.values())) if x not in open_]
    if proef:
        te_doen = te_doen[:proef]
    if not te_doen:
        print("niets te vertalen")
        return
    n = len(te_doen)
    te_doen = binnen_grens(list(alle.values()), te_doen, _ruimte())
    if not te_doen:
        raise SystemExit(f"de grens van deze week is bereikt (${ev.GRENS:.2f} voor de eigen checks en de wereldlijst samen); "
                         f"{n} wachten")
    if len(te_doen) < n:
        print(f"{n - len(te_doen)} vertalingen wachten op volgende week (grens ${ev.GRENS:.2f} per week, samen)")
    kost = schatting(list(alle.values()), te_doen)
    laad_sleutel()
    batch = anthropic.Anthropic(max_retries=6).messages.batches.create(requests=[
        {"custom_id": f"{s}__{t}", "params": verzoek(alle[s], t)} for s, t in te_doen])
    BATCHES.parent.mkdir(parents=True, exist_ok=True)
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": batch.id, "vragen": te_doen, "schatting": round(kost, 4), "versie": VERSIE,
                            "dag": date.today().isoformat(), "werkelijk": None}) + "\n")
    print(f"batch {batch.id}: {len(te_doen)} vertalingen, schatting ${kost:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck import wereldlijst as wl
    from doublecheck.modellen import MODELLEN
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    alle = {o["sleutel"]: o for o in wl.lees_alle()}
    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        batches = ev._jsonl(BATCHES)
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, goed, fout = 0.0, 0, []
            for r in client.messages.batches.results(b["id"]):
                sleutel, taal = r.custom_id.split("__")
                o = alle.get(sleutel)
                if o is None or r.result.type != "succeeded":
                    fout.append(r.custom_id)
                    continue
                msg = r.result.message
                werkelijk += kosten_batch(bc.gebruik_uit(msg), MODEL)
                tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(x, "text", "") or "" for x in msg.content)
                velden = ev.lees_antwoord(tekst, bron(o))
                if velden is None:
                    fout.append(r.custom_id)
                    continue
                schrijf(pad(sleutel, taal), bestand(o, taal, velden, f"{MODELLEN[MODEL]['id']}, {b.get('versie', VERSIE)}"))
                goed += 1
            b["werkelijk"] = round(werkelijk, 4)
            b["fout"] = fout
            BATCHES.write_text("".join(json.dumps(x) + "\n" for x in batches), encoding="utf-8")
            print(f"batch {b['id']}: {goed} goed, {len(fout)} niet bruikbaar {fout[:5]}, ${werkelijk:.2f}")
        if not open_ or time.time() > einde:
            print(f"{open_} batches nog open; ruimte deze week ${_ruimte():.2f} van ${ev.GRENS:.2f}")
            return
        time.sleep(30)


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="De wereldlijst vertaald (PLAN #37.12)")
    p.add_argument("stap", choices=["plan", "indienen", "ophalen"])
    p.add_argument("--proef", type=int)
    p.add_argument("--wacht", type=int, default=0)
    a = p.parse_args()
    if a.stap == "plan":
        from doublecheck import wereldlijst as wl

        alle = wl.lees_alle()
        te_doen = nog_te_doen(alle)
        print(f"{len(te_doen)} vertalingen te doen, schatting ${schatting(alle, te_doen):.2f}; "
              f"ruimte deze week ${_ruimte():.2f} van ${ev.GRENS:.2f} (samen met de eigen checks)")
    elif a.stap == "indienen":
        _indienen(a.proef)
    else:
        _ophalen(a.wacht)


if __name__ == "__main__":  # pragma: no cover
    main()
