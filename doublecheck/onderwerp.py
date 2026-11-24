"""Wikipedia per onderwerp (PLAN #31.5, E8.S5, B42).

leerling-1 scheidt op stijl en onderwerp (§141): Oekraïne, de NAVO en 11
september zijn voor hem verdacht, omdat de ware kant van de leerstof over
andere dingen ging. Dit haalt per onwaar stuk van leerstof v2 ware stukken
over hetzelfde onderwerp, in dezelfde taal: de inleiding van de Wikipedia-
artikelen erover.

Een zin als zoekvraag vindt op Wikipedia bijna niets (alle woorden moeten
erin staan), en losse zeldzame woorden geven ruis (tikfouten, verbogen
vormen). Daarom leest Haiku per stuk de taal en 2 à 4 zoekwoorden (namen,
plaatsen, de gebeurtenis), zonder oordeel (B42: de leraar leest, oordeelt
niet). Dan Wikipedia: eerst alle zoekwoorden samen, anders één ervan; de
eerste drie treffers, alleen de inleiding als platte tekst. Eén verzoek
tegelijk, hooguit één per seconde, hervatbaar. Alleen openbare tekst van
ClaimReview en Sheffield gaat de deur uit, nooit een artefact van een
gebruiker.

Per pagina dezelfde helft als de Wikipedia-zinnen van #31.6: de
ontwikkelhelft wordt leerstof, de toetshelft een toets met ware stukken over
de onderwerpen van nepnieuws.

    python -m doublecheck.onderwerp plan|indienen [--proef N]|ophalen|zoeken|bewaken|tellen
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "echtnieuws" / "onderwerp"
AGENT = "FactizResearch/1.0 (https://factiz.org; alleen tekst, PLAN #31.5)"
PROMPTVERSIE = "onderwerp-v1"
INVOER_TEKENS = 600
MAX_WOORDEN = 4
TREFFERS = 3
BRON_ZIN = "wikipedia-onderwerp"
BRON_INLEIDING = "wikipedia-onderwerp-inleiding"

SYSTEEM = "You help find encyclopedia articles about the subject of a text. You never judge whether a text is true."
VRAAG = ("Give (1) the language of the text above as an ISO 639-1 code, and (2) two to four search keywords in that "
         "same language that would find the Wikipedia article about its subject: names of people, places or "
         "organisations, or the event or thing it is about. No opinions, and no words such as 'fake', 'hoax' or "
         "'claim'.")
_SCHEMA = {"type": "object", "properties": {"taal": {"type": "string"},
                                            "zoekwoorden": {"type": "array", "items": {"type": "string"}}},
           "required": ["taal", "zoekwoorden"], "additionalProperties": False}


def invoer(stuk: dict) -> str:
    """Wat Haiku leest: de claim, of het begin van een artikel (kop en
    opening)."""
    return stuk["tekst"][:INVOER_TEKENS]


def lees_antwoord(tekst: str) -> tuple[str, list[str]] | None:
    """(taal, zoekwoorden), of None bij een onleesbaar of leeg antwoord."""
    try:
        a = json.loads(tekst)
    except json.JSONDecodeError:
        return None
    taal = str(a.get("taal") or "").strip().lower()
    woorden = [w for w in (" ".join(str(x).replace('"', " ").split()) for x in a.get("zoekwoorden") or []) if w]
    if not taal or not woorden:
        return None
    return taal, woorden[:MAX_WOORDEN]


def zoekvragen(woorden: list[str]) -> tuple[str, str]:
    """Streng: alle woorden moeten erin staan. Ruim: één van de zoekwoorden is
    genoeg, een zoekwoord van meer woorden als vaste reeks."""
    return " ".join(woorden), " OR ".join(f'"{w}"' if " " in w else w for w in woorden)


def stukken_van(pagina: dict) -> list[dict]:
    """De ware zinnen uit de inleiding (zoals `echtnieuws.feitzinnen`) en de
    inleiding zelf als waar artikel, als die lang genoeg is. Eén zaak en één
    helft per pagina, dezelfde als de Wikipedia-zinnen van #31.6."""
    from doublecheck.echtnieuws import MAX_TEKENS, MIN_TEKST, feitzinnen

    taal, pageid = pagina["taal"], pagina["pageid"]
    zaak = f"wikipedia:{taal}:{pageid}"
    zinnen = feitzinnen({"id": pageid, "title": pagina["titel"], "url": pagina["url"], "text": pagina["inleiding"]},
                        taal)
    uit = [{**z, "sleutel": f"{BRON_ZIN}:{taal}:{pageid}#{i}", "bron": BRON_ZIN, "zaak": zaak}
           for i, z in enumerate(zinnen)]
    inleiding = " ".join(pagina["inleiding"].split())
    if len(inleiding) >= MIN_TEKST:
        uit.append({"sleutel": f"{BRON_INLEIDING}:{taal}:{pageid}", "bron": BRON_INLEIDING, "soort": "artikel",
                    "label": "waar", "taal": taal, "titel": pagina["titel"], "url": pagina["url"], "datum": None,
                    "helft": zinnen[0]["helft"] if zinnen else _helft(zaak), "zaak": zaak,
                    "tekst": f"{pagina['titel']}\n{inleiding}"[:MAX_TEKENS]})
    return uit


def _helft(zaak: str) -> str:
    from doublecheck.zeef import helft

    return helft(zaak)


# --- de vragen en de batch ---------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad) if pad.exists() else []


def vragen() -> list[dict]:  # pragma: no cover - op leerstof v2
    """Elk onwaar stuk van leerstof v2, met een vast id."""
    from doublecheck.leerstof import BESTAND_V2

    een = [r for r in _jsonl(BESTAND_V2) if r["label"] == 1]
    return [{"id": f"o-{i:05d}", "herkomst": r["herkomst"], "taal": r["taal"], "soort": r["soort"],
             "tekst": invoer(r)} for i, r in enumerate(sorted(een, key=lambda r: r["herkomst"]))]


def verzoek(vraag: dict) -> dict:  # pragma: no cover - vorm van de Batch API
    from doublecheck.leraar import MODELLEN

    return {"custom_id": vraag["id"],
            "params": {"model": MODELLEN["haiku"]["id"], "max_tokens": 1_000, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": [
                           {"type": "text", "text": f"Text:\n{vraag['tekst']}\n\n{VRAAG}"}]}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def kosten(n_tekens: int, n: int, uit_per_stuk: int = 300) -> float:
    from doublecheck.leraar import MODELLEN

    m = MODELLEN["haiku"]
    tokens = n_tekens // 3 + n * ((len(SYSTEEM) + len(VRAAG)) // 4 + 20)
    return (tokens * m["in"] + n * uit_per_stuk * m["uit"]) / 1e6


def antwoorden() -> dict[str, tuple[str, list[str]]]:
    uit = {}
    for r in _jsonl(UIT / "antwoorden.jsonl"):
        if r.get("taal"):
            uit[r["id"]] = (r["taal"], r["zoekwoorden"])
    return uit


# --- Wikipedia ----------------------------------------------------------------------

def _vraag_wikipedia(web, taal: str, zoek: str) -> list[dict]:  # pragma: no cover - met het netwerk
    """Eén zoekvraag met de inleiding van de eerste treffers; wacht bij maxlag,
    429 of 5xx en probeert opnieuw."""
    import httpx

    params = {"action": "query", "format": "json", "formatversion": 2, "generator": "search", "gsrsearch": zoek,
              "gsrlimit": TREFFERS, "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": TREFFERS,
              "maxlag": 5}
    for poging in range(6):
        try:
            antwoord = web.get(f"https://{taal}.wikipedia.org/w/api.php", params=params)
        except httpx.ConnectError:
            return []  # geen Wikipedia in deze taal
        if antwoord.status_code == 404:
            return []
        if antwoord.status_code == 200:
            data = antwoord.json()
            if data.get("error", {}).get("code") != "maxlag":
                return sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
        elif antwoord.status_code not in (429, 500, 502, 503, 504):
            antwoord.raise_for_status()
        time.sleep(min(120, max(int(antwoord.headers.get("Retry-After", "0") or 0), 5 * 2 ** poging)))
    raise RuntimeError(f"wikipedia {taal}: blijft weigeren; later hervatten")


def zoeken() -> dict:  # pragma: no cover - met het netwerk
    """Per vraag met zoekwoorden: eerst streng, anders ruim. Hervatbaar per
    vraag; elke pagina één keer."""
    import httpx

    UIT.mkdir(parents=True, exist_ok=True)
    uitslagen, paginas = UIT / "zoekuitslagen.jsonl", UIT / "paginas.jsonl"
    gedaan = {r["id"] for r in _jsonl(uitslagen)}
    bekend = {(p["taal"], p["pageid"]) for p in _jsonl(paginas)}
    woorden = antwoorden()
    teller: Counter = Counter()
    vorige = 0.0
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=60) as web:
        for v in vragen():
            if v["id"] in gedaan or v["id"] not in woorden:
                continue
            taal, zw = woorden[v["id"]]
            gevonden, vorm = [], None
            for vorm, zoek in zip(("streng", "ruim"), zoekvragen(zw)):
                time.sleep(max(0.0, 1.0 - (time.time() - vorige)))
                vorige = time.time()
                gevonden = _vraag_wikipedia(web, taal, zoek)
                if gevonden or len(zw) == 1:
                    break
            nieuw = []
            for p in gevonden:
                if (taal, p["pageid"]) not in bekend and p.get("extract"):
                    bekend.add((taal, p["pageid"]))
                    nieuw.append({"taal": taal, "pageid": p["pageid"], "titel": p["title"],
                                  "url": f"https://{taal}.wikipedia.org/?curid={p['pageid']}",
                                  "inleiding": p["extract"]})
            with paginas.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in nieuw)
            with uitslagen.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": v["id"], "taal": taal, "vorm": vorm if gevonden else None,
                                    "paginas": [p["pageid"] for p in gevonden]}, ensure_ascii=False) + "\n")
            teller[vorm if gevonden else "niets"] += 1
            if sum(teller.values()) % 250 == 0:
                print(f"  {len(gedaan) + sum(teller.values())} vragen: {dict(teller)}, {len(bekend)} pagina's", flush=True)
    return {"vragen": dict(teller), "paginas": len(bekend)}


def lees_stukken() -> list[dict]:
    return [s for p in _jsonl(UIT / "paginas.jsonl") for s in stukken_van(p)]


# --- bewaking: niets de leerstof in dat op een bewaakt stuk lijkt ------------------------

GRENS_BEWAKING = 0.85
BEWAKING_TEKENS = 500
BEWAKING = UIT / "bewaking.json"


def uit_te_sluiten(hoogste: dict[str, float], grens: float = GRENS_BEWAKING) -> list[str]:
    """De sleutels waarvan de hoogste gelijkenis met een bewaakt stuk de grens
    haalt."""
    return sorted(k for k, v in hoogste.items() if v >= grens)


def uitgesloten() -> list[str]:
    if not BEWAKING.exists():
        raise SystemExit("eerst `python -m doublecheck.onderwerp bewaken`")
    return json.loads(BEWAKING.read_text(encoding="utf-8"))["uitgesloten"]


def bewaken(grens: float = GRENS_BEWAKING) -> dict:  # pragma: no cover - met bge-m3
    """Per ware kandidaat voor de leerstof de hoogste gelijkenis (bge-m3) met
    alles wat meet: de basisset buiten de les (kern, minimale paren, keuzerol,
    toetshelft; beelden via de bewering van Haiku) en de steekproef echt
    nieuws van `leerling._echt`, met de toetshelft van deze pagina's. Eerst alles embedden, dan vergelijken (lessen van 2026-10-22)."""
    import numpy as np

    from doublecheck import basisset, leerling
    from doublecheck.config import load_config
    from doublecheck.leerstof import mag_leren, taalcode
    from doublecheck.zeef import GPU_PAUZE, _vectoren_gpu

    versie = load_config().model_versions.text_embedding
    stukken = [{**s, "taal": taalcode(s["taal"])} for s in lees_stukken()]
    kandidaten = [s for s in stukken if mag_leren(s)]
    beeldzinnen = leerling._beeldzinnen()
    bewaakt = [(s["sleutel"], t) for s in basisset.lees() if leerling.rol(s) != "les"
               and (t := leerling.invoer(s, beeldzinnen))]
    bewaakt += [(s["sleutel"], s["tekst"]) for s in leerling._echt()]

    def vectoren(naam: str, teksten: list[str]):
        """Op de eerste `BEWAKING_TEKENS` tekens (een bijna-dubbel zie je aan
        het begin), op lengte gesorteerd voor minder opvulling; de volgorde
        terug zoals gegeven. Na elke portie de cache van de grafische chip
        leeg (anders 15 GB, 2026-10-23); per set bewaard, dus hervatbaar."""
        pad = UIT / f"bewaking-{naam}.npy"
        if pad.exists():
            klaar = np.load(pad)
            if len(klaar) == len(teksten):
                return klaar
        teksten = [t[:BEWAKING_TEKENS] for t in teksten]
        orde = sorted(range(len(teksten)), key=lambda i: len(teksten[i]))
        delen = []
        for start in range(0, len(orde), 256):
            delen.append(_vectoren_gpu([teksten[i] for i in orde[start:start + 256]], versie))
            _leeg_chip()
            if start and start % 5_120 == 0:
                print(f"    {naam}: {start:,} van {len(teksten):,}", flush=True)
                time.sleep(GPU_PAUZE)
        uit = np.empty((len(teksten), delen[0].shape[1]), dtype=np.float32)
        uit[np.asarray(orde)] = np.concatenate(delen)
        np.save(pad, uit)
        return uit

    print(f"  bewaakt: {len(bewaakt):,} stukken; kandidaten: {len(kandidaten):,}", flush=True)
    b = vectoren("bewaakt", [t for _, t in bewaakt])
    k = vectoren("kandidaten", [s["tekst"] for s in kandidaten])
    hoogste, naast = {}, {}
    for start in range(0, len(k), 2_048):
        sim = k[start:start + 2_048] @ b.T
        for i, j in enumerate(sim.argmax(axis=1)):
            s = kandidaten[start + i]
            hoogste[s["sleutel"]] = float(sim[i, j])
            naast[s["sleutel"]] = bewaakt[int(j)][0]
    weg = uit_te_sluiten(hoogste, grens)
    per_tekst = {s["sleutel"]: s for s in kandidaten}
    uitslag = {"grens": grens, "model": versie, "bewaakt": len(bewaakt), "kandidaten": len(kandidaten),
               "uitgesloten": weg, "per bron": dict(Counter(per_tekst[x]["bron"] for x in weg)),
               "voorbeelden": [{"kandidaat": per_tekst[x]["tekst"][:200], "lijkt op": naast[x],
                                "gelijkenis": round(hoogste[x], 3)} for x in weg[:: max(1, len(weg) // 20)][:20]]}
    BEWAKING.write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
    return {k_: v for k_, v in uitslag.items() if k_ not in ("uitgesloten", "voorbeelden")} | {"weg": len(weg)}


def _leeg_chip() -> None:  # pragma: no cover - met de grafische chip
    import torch

    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def telling() -> dict:
    stukken = lees_stukken()
    uitslagen = _jsonl(UIT / "zoekuitslagen.jsonl")
    return {"vragen": len(uitslagen), "per vorm": dict(Counter(r["vorm"] for r in uitslagen)),
            "paginas": len(_jsonl(UIT / "paginas.jsonl")),
            "stukken per bron en helft": dict(Counter(f"{s['bron']} {s['helft']}" for s in stukken)),
            "per taal": dict(Counter(s["taal"] for s in stukken).most_common())}


def main() -> None:  # pragma: no cover - CLI, met de Batch API en het netwerk
    import argparse

    from doublecheck.leraar import MODELLEN

    parser = argparse.ArgumentParser(description="Wikipedia per onderwerp (#31.5)")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "zoeken", "bewaken", "tellen"))
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    if args.stap == "tellen":
        print(json.dumps(telling(), ensure_ascii=False, indent=1))
        return
    if args.stap == "zoeken":
        print(json.dumps(zoeken(), ensure_ascii=False))
        return
    if args.stap == "bewaken":
        print(json.dumps(bewaken(), ensure_ascii=False, indent=1))
        return
    alle = vragen()
    if args.stap == "plan":
        print(f"{len(alle)} vragen {dict(Counter(v['soort'] for v in alle))}, Haiku naar schatting "
              f"${kosten(sum(len(v['tekst']) for v in alle), len(alle)):.2f}")
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    UIT.mkdir(parents=True, exist_ok=True)
    batches = UIT / "batches.jsonl"
    if args.stap == "indienen":
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        nog = [v for v in alle if v["id"] not in ingediend]
        kies = nog[:: max(1, len(nog) // args.proef)][: args.proef] if args.proef else nog
        geschat = kosten(sum(len(v["tekst"]) for v in kies), len(kies))
        batch = client.messages.batches.create(requests=[verzoek(v) for v in kies])
        with batches.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE, "schatting": round(geschat, 3),
                                "ids": [v["id"] for v in kies]}) + "\n")
        print(f"batch {batch.id}: {len(kies)} vragen, naar schatting ${geschat:.2f}")
        return
    m = MODELLEN["haiku"]
    alle_b = _jsonl(batches)
    klaar = set(antwoorden())
    with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as uit:
        for b in alle_b:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                gelezen = None
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += (msg.usage.input_tokens * m["in"] + msg.usage.output_tokens * m["uit"]) / 1e6
                    gelezen = lees_antwoord(next((c.text for c in msg.content if c.type == "text"), "{"))
                if r.custom_id in klaar:
                    continue
                taal, zw = gelezen or (None, [])
                uit.write(json.dumps({"id": r.custom_id, "taal": taal, "zoekwoorden": zw, "model": m["id"],
                                      "prompt": PROMPTVERSIE}, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    batches.write_text("".join(json.dumps(b) + "\n" for b in alle_b), encoding="utf-8")
    print(f"{len(antwoorden())} van {len(alle)} vragen met zoekwoorden; werkelijk "
          f"${sum(b.get('werkelijk') or 0 for b in alle_b):.2f}")


if __name__ == "__main__":
    main()
