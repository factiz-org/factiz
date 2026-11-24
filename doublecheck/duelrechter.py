"""Een automatische beoordelaar voor het duel, geijkt op de keuzes van de PO (PLAN #32.48a).

PO 2026-11-09: "Kunnen we ook nog een geautomatiseerde check schrijven met een blinde test tegen gemini, vooraf aan ons
duel? ... om te zien of we het eens zijn, als dat zo is, kan het voortaan automatisch."

De beoordelaar krijgt wat de PO kreeg: het bericht en antwoord A en B (oordeel, kleur, uitleg, bronnen), zonder de
onthulling, en de twee vragen van de kaartenbak. Elk paar gaat twee keer, met A en B omgedraaid, naar twee beoordelaars
van verschillende makers (Claude Opus 5.5 en Gemini), live en zonder zoeken. Een keuze telt alleen als beide volgordes
en beide beoordelaars hetzelfde zeggen; anders krijgt de kaart een vlag en gaat ze naar de PO.

    python -m doublecheck.duelrechter ijken [--proef N]|tellen
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "duelrechter"
VERSIE = "duelrechter-v1"
OPUS = "claude-opus-5-5"
BEOORDELAARS = ("claude", "gemini")
NAMEN = ("Factiz", "Gemini")
DUELS = {"1": ("data/poproef/duel-2026-11-07.json", "docs/steekproeven/duel-2026-11-07.json"),
         "2": ("data/poproef/duel-2026-11-07-v12.json", "docs/steekproeven/duel-2026-11-07-v12.json")}
LAT = {"klopt": 0.90, "helpt": 0.75, "per_duel": 5, "vlaggen": 0.20}
BUDGET = 4.0
KLOPT = ("A", "B", "beide", "geen", "weet niet")
HELPT = ("A", "B", "gelijk")
VRAAG = ("Je beoordeelt twee antwoorden op de vraag of een bericht klopt, zoals een lezer die wil weten of hij het "
         "bericht kan geloven en doorsturen. Je ziet het bericht en antwoord A en antwoord B, elk met een oordeel, een "
         "kleur, een uitleg en de bronnen. Zoek niet zelf; gebruik wat je weet en wat in de antwoorden staat. Je hoeft "
         "niet zeker te weten wat er echt gebeurde: oordeel zoals een oplettende lezer op grond van de antwoorden en hun "
         "bronnen. Kies *weet niet* alleen als je echt geen kant kunt kiezen.\n\n"
         "1. Welk antwoord klopt? Kies A, B, beide, geen of weet niet.\n"
         "2. Welk antwoord helpt je het meest om het te beoordelen? Kies A, B of gelijk.\n\n"
         "Antwoord alleen met JSON: {\"klopt\": \"...\", \"helpt\": \"...\", \"waarom\": \"één zin\"}\n\n")


def _antwoord(a: dict) -> str:
    bronnen = "; ".join(" — ".join(x for x in (b.get("site"), b.get("titel")) if x) for b in a.get("bronnen") or [])
    return (f"Oordeel: {a.get('oordeel') or '-'} (kleur: {a.get('kleur') or 'geen'})\nUitleg: {a.get('uitleg') or ''}\n"
            f"Bronnen: {bronnen or '-'}")


def paar(kaart: dict, eerst: str) -> tuple[str, dict[str, str]]:
    """De vraag voor één volgorde: `eerst` is A. Geeft de tekst en wie A en B zijn; de onthulling gaat nooit mee."""
    per_wie = {a["wie"]: a for a in kaart["antwoorden"]}
    tweede = next(n for n in NAMEN if n != eerst)
    tekst = (VRAAG + f"Het bericht:\n{kaart['bericht']}\n\nAntwoord A:\n{_antwoord(per_wie[eerst])}\n\n"
             f"Antwoord B:\n{_antwoord(per_wie[tweede])}")
    return tekst, {"A": eerst, "B": tweede}


def lees(tekst: str) -> dict:
    """Het antwoord van een beoordelaar, streng: geen geldige JSON of een keuze buiten de lijst is *weet niet* en
    *gelijk*."""
    leeg = {"klopt": "weet niet", "helpt": "gelijk", "waarom": ""}
    m = re.search(r"\{.*\}", tekst or "", re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or d.get("klopt") not in KLOPT or d.get("helpt") not in HELPT:
        return leeg
    return {"klopt": d["klopt"], "helpt": d["helpt"], "waarom": str(d.get("waarom") or "")}


def namen(oordeel: dict, wie: dict[str, str]) -> tuple[frozenset | None, str]:
    """Van A en B naar Factiz en Gemini: wie klopt (een verzameling, of None bij *weet niet*) en wie het meest helpt."""
    k = oordeel["klopt"]
    klopt = (None if k == "weet niet" else frozenset(NAMEN) if k == "beide" else frozenset() if k == "geen"
             else frozenset({wie[k]}))
    h = oordeel["helpt"]
    return klopt, ("gelijk" if h == "gelijk" else wie[h])


def samen(oordelen: dict[tuple[str, str], tuple]) -> dict:
    """Per beoordelaar telt een keuze alleen als ze in beide volgordes gelijk is; daarna alleen als beide
    beoordelaars hetzelfde zeggen. Anders een vlag."""
    per = {}
    for b in BEOORDELAARS:
        (k1, h1), (k2, h2) = oordelen[(b, NAMEN[0])], oordelen[(b, NAMEN[1])]
        per[b] = (k1 if k1 == k2 else None, h1 if h1 == h2 else None)
    k = per["claude"][0] if per["claude"][0] == per["gemini"][0] and per["claude"][0] is not None else None
    h = per["claude"][1] if per["claude"][1] == per["gemini"][1] and per["claude"][1] is not None else None
    return {"klopt": k, "helpt": h, "vlag": k is None or h is None}


def po(label: dict) -> tuple[frozenset | None, str]:
    """De keuze van de PO in namen; `a` zegt wie A was."""
    wie = {"A": label["a"], "B": next(n for n in NAMEN if n != label["a"])}
    return namen({"klopt": label["klopt"], "helpt": "gelijk"}, wie)[0], label["helpt"]


def ijking(rijen: list[dict], verwacht: dict | None = None) -> dict:
    """De beoordelaar tegen de PO: klopt op de kaarten waar de PO het wist, helpt op de kaarten zonder vlag, per duel
    de aantallen voor Factiz en Gemini, en het aantal vlaggen; elk met de lat van PLAN #32.48a."""
    k = [r for r in rijen if r["po"][0] is not None]
    k_gelijk = sum(r["rechter"]["klopt"] == r["po"][0] for r in k)
    h = [r for r in rijen if not r["rechter"]["vlag"]]
    h_gelijk = sum(r["rechter"]["helpt"] == r["po"][1] for r in h)
    per_duel = {}
    for d in sorted({r["duel"] for r in rijen}):
        eigen = [r for r in rijen if r["duel"] == d]
        po_tel = (verwacht or {}).get(d) or {n: sum(r["po"][1] == n for r in eigen) for n in NAMEN}
        rechter = {n: sum(r["rechter"]["helpt"] == n for r in eigen) for n in NAMEN}
        per_duel[d] = {"po": po_tel, "rechter": rechter,
                       "gehaald": all(abs(po_tel[n] - rechter[n]) <= LAT["per_duel"] for n in NAMEN)}
    vlaggen = sum(r["rechter"]["vlag"] for r in rijen)

    def maat(gelijk, van, lat):
        aandeel = round(gelijk / van, 3) if van else 0.0
        return {"gelijk": gelijk, "van": van, "aandeel": aandeel, "gehaald": van > 0 and aandeel >= lat}

    return {"versie": VERSIE, "klopt": maat(k_gelijk, len(k), LAT["klopt"]),
            "helpt": maat(h_gelijk, len(h), LAT["helpt"]), "per duel": per_duel,
            "vlaggen": {"aantal": vlaggen, "gehaald": vlaggen <= LAT["vlaggen"] * len(rijen)}}


# --- de bestanden en het netwerk -----------------------------------------------------------------------------------

def _kaarten() -> list[tuple[str, dict, dict]]:  # pragma: no cover - op de bestanden
    uit = []
    for d, (kaarten, labels) in DUELS.items():
        k = {x["id"]: x for x in json.loads((WORTEL / kaarten).read_text(encoding="utf-8"))["kaarten"]}
        for label in json.loads((WORTEL / labels).read_text(encoding="utf-8"))["labels"]:
            uit.append((d, k[label["id"]], label))
    return uit


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _claude(client, tekst: str) -> tuple[str, float]:  # pragma: no cover - het netwerk
    from doublecheck.leraar import MODELLEN

    msg = client.messages.create(model=OPUS, max_tokens=3000, messages=[{"role": "user", "content": tekst}])
    p = MODELLEN["opus"]  # de prijzen van de Batch API; live het dubbele
    kosten = 2 * (msg.usage.input_tokens * p["in"] + msg.usage.output_tokens * p["uit"]) / 1e6
    return "".join(getattr(b, "text", "") for b in msg.content), kosten


def _gemini(web, sleutel: str, tekst: str) -> tuple[str, float]:  # pragma: no cover - het netwerk
    from doublecheck import duel

    r = web.post(duel.GEMINI_ADRES.format(model=duel.GEMINI_MODEL), headers={"x-goog-api-key": sleutel},
                 json={"contents": [{"role": "user", "parts": [{"text": tekst}]}],
                       "generationConfig": {"responseMimeType": "application/json"}})
    r.raise_for_status()
    d = r.json()
    gebruik = d.get("usageMetadata", {})
    kosten = (gebruik.get("promptTokenCount", 0) * duel.PRIJS_IN
              + (gebruik.get("candidatesTokenCount", 0) + gebruik.get("thoughtsTokenCount", 0)) * duel.PRIJS_UIT) / 1e6
    tekst_uit = "".join(p.get("text", "") for c in d.get("candidates", []) for p in c.get("content", {}).get("parts", []))
    return tekst_uit, kosten


def _ijken(proef: int | None) -> None:  # pragma: no cover - het netwerk
    """Elke kaart in beide volgordes naar beide beoordelaars; hervatbaar per vraag, binnen `BUDGET`."""
    import os
    from concurrent.futures import ThreadPoolExecutor

    import anthropic
    import httpx

    from doublecheck import duel
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = duel.gemini_sleutel(os.environ)
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "ijking.jsonl"
    klaar = _jsonl(pad)
    gedaan = {(r["duel"], r["id"], r["beoordelaar"], r["eerst"]) for r in klaar}
    uitgegeven = sum(r["kosten"] for r in klaar)
    kaarten = _kaarten()[:proef or None]
    werk = [(d, k, b, e) for d, k, _ in kaarten for b in BEOORDELAARS for e in NAMEN if (d, k["id"], b, e) not in gedaan]
    print(f"{len(werk)} vragen; al uitgegeven ${uitgegeven:.2f}", flush=True)
    client, web = anthropic.Anthropic(max_retries=6), httpx.Client(timeout=120)

    def een(taak):
        d, k, b, e = taak
        tekst, _ = paar(k, eerst=e)
        try:
            ruw, kosten = _claude(client, tekst) if b == "claude" else _gemini(web, sleutel, tekst)
        except Exception as fout:  # noqa: BLE001 - een vraag zonder antwoord gaat de volgende keer opnieuw
            print(f"{k['id']} {b} {e}: {type(fout).__name__}", flush=True)
            return None
        return {"duel": d, "id": k["id"], "beoordelaar": b, "eerst": e, **lees(ruw), "kosten": round(kosten, 5),
                "versie": VERSIE}

    with ThreadPoolExecutor(6) as pool, pad.open("a", encoding="utf-8") as uit:
        for i, rij in enumerate(pool.map(een, werk), 1):
            if rij is None:
                continue
            uit.write(json.dumps(rij, ensure_ascii=False) + "\n")
            uit.flush()
            uitgegeven += rij["kosten"]
            if i % 25 == 0:
                print(f"{i} van {len(werk)}: ${uitgegeven:.2f}", flush=True)
            if uitgegeven >= BUDGET:
                print(f"gestopt bij de grens: ${uitgegeven:.2f}", flush=True)
                break
    print(f"klaar: ${uitgegeven:.2f}", flush=True)


def _tellen() -> None:  # pragma: no cover - op de bestanden
    antwoorden = {(r["duel"], r["id"], r["beoordelaar"], r["eerst"]): r for r in _jsonl(UIT / "ijking.jsonl")}
    rijen = []
    for d, k, label in _kaarten():
        sleutels = [(d, k["id"], b, e) for b in BEOORDELAARS for e in NAMEN]
        if not all(s in antwoorden for s in sleutels):
            continue
        oordelen = {(b, e): namen(antwoorden[(d, k["id"], b, e)], paar(k, eerst=e)[1]) for (_, _, b, e) in sleutels}
        rijen.append({"duel": d, "id": k["id"], "po": po(label), "rechter": samen(oordelen)})
    uit = {**ijking(rijen), "kaarten": len(rijen), "kosten": round(sum(r["kosten"] for r in antwoorden.values()), 4)}
    (UIT / "telling.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De automatische beoordelaar voor het duel (PLAN #32.48a)")
    parser.add_argument("stap", choices=("ijken", "tellen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    _ijken(args.proef) if args.stap == "ijken" else _tellen()


if __name__ == "__main__":
    main()
