"""Het proefdossier (PLAN #32.70): wat er ligt ordenen in een dossier (thema), verhaallijnen en cases.

Een **dossier** is een thema, een **verhaallijn** een verhaal dat terugkomt in steeds andere woorden, een **case** één
bewering die rondging, met de checks van de redacties erbij. De cases liggen er (de claims in de database); de
verhaallijn ontbreekt: groeperen op gelijkenis ving bij de biolabs 17 van de 96 beweringen (BENCHMARK §111). Hier zegt
Haiku per bewering de verhaallijn in één Engelse zin, en groeperen we die zinnen.

    python -m doublecheck.dossier kiezen|benoemen [--proef N | --toets] [--direct]|ophalen [--wacht M]|groeperen|terug [--grens 2025]

Offline, op openbare beweringen uit factchecks; de database wordt alleen gelezen. Uitvoer in `data/dossier/<thema>/`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "dossier"
VERSIE = "verhaallijn-v1"
GRENS = 3.00            # dollar voor het hele proefdossier (PLAN #32.70)
SCHATTING = 0.00006     # per bewering in de batch; in de proef direct $0,00010 (~740 tokens in, ~51 uit)
ZAAD = 3270
DRADEN = 8
KETTING = 1000          # een groep met meer beweringen is een ketting en gaat opnieuw, bij STRAKKER
STRAKKER = 0.85
MIN_CASES = 3           # een verhaallijn van vóór de grens telt pas vanaf zoveel cases
DREMPEL = 0.80          # gekozen op de proef van 214 en vast vóór de volle ronde: bij 0,75 kleven de twee
                        # toetsverhalen aan elkaar, bij 0,85 vallen ze uiteen (PLAN #32.70)

THEMAS = {
    "oekraine-rusland": {
        "naam": "Oekraïne en Rusland",
        "omschrijving": ("Russia's war against Ukraine, and stories about Ukraine, Russia, their leaders, NATO and "
                         "Western support for Ukraine"),
        # Een ondergrens: trefwoorden in een tiental talen en drie schriften.
        "trefwoorden": (r"ukrain|ucrania|ucr[aâ]nia|oekra[iï]|ukrayna|украин|україн|أوكراني|यूक्रेन|"
                        r"russia|\brusia|r[uú]ssia|russie|rusland|russland|ryssland|\brosj|\brusya|росси|росі|روسيا|रूस|"
                        r"zelensk|selensk|зеленск|зеленськ|putin|poutine|путин|путін|kreml|кремл|"
                        r"\bnato\b|\botan\b|\bnavo\b|\bнато\b|crimea|\bkrim\b|crimée|крым|крим|donbas|донбас|"
                        r"\bbucha\b|буча|mariupol|мариупол|маріупол|wagner"),
    },
}
_RX = {naam: re.compile(t["trefwoorden"], re.IGNORECASE) for naam, t in THEMAS.items()}

# De verhalen van §111, met dezelfde trefwoorden: daar ving groeperen op gelijkenis 17 van 96 en 8 van 40.
TOETSVERHALEN = {
    "biolabs": ("biolab", "biological lab", "biological laborator", "biolaborator"),
    "NAVO-uitbreiding": ("nato expansion", "nato enlargement", "expand eastward", "eastward expansion", "not one inch"),
}


class Weigering(Exception):
    """De grens in dollars is bereikt."""


def hoort_bij(tekst: str, thema: str) -> bool:
    """Of een bewering op een trefwoord bij het thema hoort. Een onbekend thema is een fout, geen leeg dossier."""
    return bool(_RX[thema].search(tekst or ""))


# --- de vraag aan het model ---------------------------------------------------------------------------------------

_SYSTEEM = """You help organise a public archive of fact-checked claims into storylines. The dossier is: {omschrijving}.

A storyline is a story that keeps coming back in different words, years and languages, for example "Mobile phone \
masts spread the coronavirus" in a dossier about health. One claim is one instance of a storyline. The claim may be \
false; do not judge it and do not describe how it is false or how a photo or video was misused: name the story the \
claim itself tells.

For the claim you are given:
1. "past": true if the claim is about the subject of the dossier; false if it only mentions it in passing or is \
about something else.
2. "verhaallijn": the storyline, as ONE plain English sentence of at most 12 words with one single idea, stated the \
way its tellers state it. If the claim tells two stories, take the main one. Make it general enough that other claims \
telling the same story in other words, places or years get the same sentence: no dates, no numbers, no names of \
private persons, no details of this one incident. Keep the names of countries, public institutions and heads of \
state. If "past" is false, give an empty string."""

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["past", "verhaallijn"],
           "properties": {"past": {"type": "boolean"}, "verhaallijn": {"type": "string"}}}


def verhaalverzoek(bewering: str, taal: str, thema: str) -> dict:
    """De vraag aan Haiku over één bewering: hoort ze bij het thema, en welke verhaallijn vertelt ze."""
    from doublecheck.modellen import MODELLEN

    # Haiku 5.5 denkt eerst, en dat denken telt mee in `max_tokens`: met een lage grens blijft het antwoord leeg
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 2000,
            "system": _SYSTEEM.format(omschrijving=THEMAS[thema]["omschrijving"]),
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": f"Claim ({taal or 'und'}): {' '.join(bewering.split())[:1500]}"}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees_verhaal(tekst: str | None) -> dict:
    """Het antwoord in vaste vorm. Twijfel versoepelt nooit: een antwoord dat niet te lezen is, of zonder zin, zet een
    bewering nergens bij (`past` is None); een bewering buiten het thema heeft geen verhaallijn."""
    twijfel = {"past": None, "verhaallijn": ""}
    try:
        d = json.loads(tekst)  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError):
        return twijfel
    if not isinstance(d, dict) or not isinstance(d.get("past"), bool):
        return twijfel
    if d["past"] is False:
        return {"past": False, "verhaallijn": ""}
    zin = " ".join(str(d.get("verhaallijn") or "").split())
    return {"past": True, "verhaallijn": zin} if zin else twijfel


def binnen_grens(geschat: float, uitgegeven: float, grens: float = GRENS) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} al uitgegeven plus ${geschat:.2f} is meer dan ${grens:.2f}")


# --- groeperen en tellen ------------------------------------------------------------------------------------------

def verhaallijnen(zinnen: list[str], vectoren: np.ndarray, drempel: float = DREMPEL,
                  gewicht: list[int] | None = None, ketting: int | None = None,
                  strakker: float = STRAKKER) -> list[dict]:
    """De zinnen die vanaf `drempel` op elkaar lijken, samen als één verhaallijn; de grootste eerst (naar `gewicht`,
    het aantal beweringen per zin). De naam is de zin die het dichtst bij het midden ligt. Een groep met meer dan
    `ketting` beweringen is een ketting (BENCHMARK §111) en wordt binnen die groep opnieuw gegroepeerd bij `strakker`."""
    from doublecheck.evergreen import verhaalgroepen

    if not zinnen:
        return []
    gewicht = gewicht or [1] * len(zinnen)
    leden: dict[int, list[int]] = {}
    for i, label in enumerate(verhaalgroepen(vectoren, drempel)):
        leden.setdefault(int(label), []).append(i)
    groepen = []
    for groep in leden.values():
        if ketting is not None and sum(gewicht[i] for i in groep) > ketting:
            binnen: dict[int, list[int]] = {}
            for i, label in zip(groep, verhaalgroepen(vectoren[groep], strakker)):
                binnen.setdefault(int(label), []).append(i)
            groepen.extend(binnen.values())
        else:
            groepen.append(groep)
    lijnen = []
    for groep in groepen:
        w = np.array([gewicht[i] for i in groep], dtype=np.float32)
        midden = (vectoren[groep] * w[:, None]).sum(axis=0)
        beste = groep[int(np.argmax(vectoren[groep] @ midden))]
        lijnen.append({"naam": zinnen[beste], "leden": groep, "beweringen": int(w.sum())})
    lijnen.sort(key=lambda l: (-l["beweringen"], l["leden"][0]))
    return lijnen


def samenvatting(rijen: list[dict]) -> dict:
    """Wat een verhaallijn omvat: de cases, hun checks, de talen, de redacties, de jaren en de oordelen."""
    checks = [c for r in rijen for c in r.get("checks", [])]
    return {"cases": len(rijen), "checks": len(checks), "talen": sorted({r["taal"] for r in rijen if r.get("taal")}),
            "redacties": len({c["redactie"] for c in checks}),
            "jaren": sorted({c["datum"][:4] for c in checks if c.get("datum", "")[:4].isdigit()}),
            "oordelen": dict(Counter(c["oordeel"] for c in checks).most_common())}


def toets_verhaal(rijen: list[dict], trefwoorden: tuple[str, ...], lijn_van: dict[int, int | None]) -> dict:
    """Van de beweringen met een trefwoord van een bekend verhaal: hoeveel er samen in de grootste verhaallijn staan.
    Een bewering die het model buiten het thema zette, telt mee in de noemer."""
    raak = [i for i, r in enumerate(rijen) if any(t in r["tekst"].lower() for t in trefwoorden)]
    if not raak:
        return {"beweringen": 0, "in grootste": 0, "aandeel": None}
    telling = Counter(lijn_van.get(i) for i in raak if lijn_van.get(i) is not None)
    grootste = telling.most_common(1)[0][1] if telling else 0
    return {"beweringen": len(raak), "in grootste": grootste, "aandeel": round(grootste / len(raak), 3)}


def terugkeer(oud: np.ndarray, lijn_van_oud: list[int], cases: dict[int, int], nieuw: np.ndarray,
              drempel: float = DREMPEL, minimaal: int = MIN_CASES) -> list[int | None]:
    """Per nieuwe zin de verhaallijn van vóór de grens waar ze bij hoort: de lijn van de oude zin die er het meest op
    lijkt, als die gelijkenis `drempel` haalt en de lijn toen al `minimaal` cases had. Anders None: een nieuw verhaal,
    of een verhaal dat te klein was om een verhaallijn te heten."""
    if len(oud) == 0 or len(nieuw) == 0:
        return [None] * len(nieuw)
    uit: list[int | None] = []
    for begin in range(0, len(nieuw), 512):
        gelijkenis = nieuw[begin:begin + 512] @ oud.T
        # alleen oude zinnen uit een lijn die groot genoeg was mogen een nieuwe zin opnemen
        groot = np.array([cases.get(l, 0) >= minimaal for l in lijn_van_oud])
        gelijkenis[:, ~groot] = -1.0
        beste = gelijkenis.argmax(axis=1)
        for rij, k in enumerate(beste):
            uit.append(lijn_van_oud[int(k)] if gelijkenis[rij, int(k)] >= drempel else None)
    return uit


def buren(oud: np.ndarray, gewicht: list[int], nieuw: np.ndarray, drempel: float = DREMPEL) -> list[int]:
    """Per nieuwe zin het aantal oude beweringen waarvan de zin er vanaf `drempel` op lijkt: alleen directe buren,
    geen ketting van buren van buren. `gewicht` is het aantal beweringen per oude zin."""
    if len(oud) == 0 or len(nieuw) == 0:
        return [0] * len(nieuw)
    w = np.asarray(gewicht, dtype=np.int64)
    uit: list[int] = []
    for begin in range(0, len(nieuw), 512):
        uit.extend(int(x) for x in ((nieuw[begin:begin + 512] @ oud.T >= drempel) * w).sum(axis=1))
    return uit


def dekking(groottes: list[int], n: int = 50) -> float | None:
    """Het aandeel van de beweringen die bij het thema horen dat in de `n` grootste verhaallijnen valt."""
    if not groottes:
        return None
    return round(sum(sorted(groottes, reverse=True)[:n]) / sum(groottes), 3)


# --- bestanden, de database en het model --------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict], toevoegen: bool = True) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a" if toevoegen else "w", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _kiezen(thema: str) -> None:  # pragma: no cover - op de database
    import sqlite3

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    checks: dict[str, list[dict]] = {}
    for cid, redactie, oordeel, datum, url, bron in conn.execute(
            "SELECT claim_id, publisher, verdict_normalized, review_date, url, source FROM factcheck"):
        checks.setdefault(cid, []).append({"redactie": redactie, "oordeel": oordeel, "datum": datum, "url": url,
                                           "bron": bron})
    rijen = [{"id": cid, "tekst": tekst, "taal": taal, "cluster": cluster, "checks": checks.get(cid, [])}
             for cid, tekst, taal, cluster in conn.execute(
                 "SELECT claim_id, canonical_text, language, cluster_id FROM claim ORDER BY claim_id")
             if hoort_bij(tekst, thema)]
    _schrijf(MAP / thema / "set.jsonl", rijen, toevoegen=False)
    s = samenvatting(rijen)
    print(f"{thema}: {s['cases']} beweringen, {s['checks']} checks, {len(s['talen'])} talen, {s['redacties']} "
          f"redacties, {s['jaren'][0]}–{s['jaren'][-1]}")
    for naam, woorden in TOETSVERHALEN.items():
        print(f"  toetsverhaal {naam}: {sum(any(w in r['tekst'].lower() for w in woorden) for r in rijen)} beweringen")
    print(f"  schatting voor benoemen via de batch: ${SCHATTING * len(rijen):.2f}")


def _uitgegeven(thema: str) -> float:  # pragma: no cover - bestanden
    batches = sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"]
                  for b in _jsonl(MAP / thema / "batches.jsonl"))
    return batches + sum(r.get("kosten", 0.0) for r in _jsonl(MAP / thema / "antwoorden.jsonl"))


def _werk(thema: str, proef: int | None, toets: bool) -> list[dict]:  # pragma: no cover - bestanden
    import random

    klaar = {r["id"] for r in _jsonl(MAP / thema / "antwoorden.jsonl")} | {
        r["id"] for r in _jsonl(MAP / thema / "kaart.jsonl")}
    rijen = [r for r in _jsonl(MAP / thema / "set.jsonl") if r["id"] not in klaar]
    if toets:
        rijen = [r for r in rijen if any(w in r["tekst"].lower() for ws in TOETSVERHALEN.values() for w in ws)]
    if proef:
        rijen = random.Random(ZAAD).sample(rijen, min(proef, len(rijen)))
    return rijen


def _benoemen(thema: str, proef: int | None, toets: bool, direct: bool) -> None:  # pragma: no cover - een model
    import anthropic

    from doublecheck.varianten import laad_sleutel

    werk = _werk(thema, proef, toets)
    if not werk:
        print("niets te vragen")
        return
    binnen_grens(SCHATTING * len(werk) * (2 if direct else 1), _uitgegeven(thema))
    laad_sleutel()
    if not direct:
        client = anthropic.Anthropic()
        begin = len(_jsonl(MAP / thema / "kaart.jsonl"))
        batch = client.messages.batches.create(requests=[
            {"custom_id": f"vl-{begin + i}", "params": verhaalverzoek(r["tekst"], r["taal"], thema)}
            for i, r in enumerate(werk)])
        _schrijf(MAP / thema / "kaart.jsonl",
                 [{"custom_id": f"vl-{begin + i}", "id": r["id"], "batch": batch.id} for i, r in enumerate(werk)])
        _schrijf(MAP / thema / "batches.jsonl", [{"id": batch.id, "aantal": len(werk),
                                                  "schatting": round(SCHATTING * len(werk), 4)}])
        print(f"batch {batch.id}: {len(werk)} beweringen, schatting ${SCHATTING * len(werk):.2f}; samen "
              f"${_uitgegeven(thema):.2f} van ${GRENS:.2f}")
        return
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from doublecheck.modellen import MODELLEN

    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]

    def een(r: dict) -> None:
        if _uitgegeven(thema) > GRENS:
            return
        try:
            msg = client.messages.create(**verhaalverzoek(r["tekst"], r["taal"], thema))
            # direct, dus zonder batchkorting: twee keer de batchprijs
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            rij = {"id": r["id"], "versie": VERSIE, "kosten": round(kosten, 6),
                   "tokens": [msg.usage.input_tokens, msg.usage.output_tokens],
                   "antwoord": None if msg.stop_reason == "max_tokens" else
                   "".join(getattr(b, "text", "") or "" for b in msg.content)}
        except Exception as e:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(e).__name__, flush=True)
            return
        with slot:
            _schrijf(MAP / thema / "antwoorden.jsonl", [rij])

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, werk))
    nu = [r for r in _jsonl(MAP / thema / "antwoorden.jsonl") if "tokens" in r]
    if nu:
        print(f"{len(nu)} direct beantwoord; gemiddeld {sum(r['tokens'][0] for r in nu) / len(nu):.0f} tokens in, "
              f"{sum(r['tokens'][1] for r in nu) / len(nu):.0f} uit, ${sum(r['kosten'] for r in nu) / len(nu):.5f} "
              f"per bewering; samen ${_uitgegeven(thema):.2f} van ${GRENS:.2f}")


def _ophalen(thema: str, wacht: int) -> None:  # pragma: no cover - netwerk
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart = {r["custom_id"]: r for r in _jsonl(MAP / thema / "kaart.jsonl")}
    einde = time.time() + 60 * wacht
    while True:
        alle, open_ = _jsonl(MAP / thema / "batches.jsonl"), 0
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, mis, regels = 0.0, 0, []
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded" or r.custom_id not in kaart:
                    mis += 1
                    continue
                msg = r.result.message
                werkelijk += kosten_batch(bc.gebruik_uit(msg), "haiku")
                regels.append({"id": kaart[r.custom_id]["id"], "versie": VERSIE,
                               "antwoord": None if msg.stop_reason == "max_tokens" else
                               "".join(getattr(x, "text", "") or "" for x in msg.content)})
            _schrijf(MAP / thema / "antwoorden.jsonl", regels)
            b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
            print(f"batch {b['id']}: {len(regels)} antwoorden, ${werkelijk:.3f}, {mis} mislukt", flush=True)
        _schrijf(MAP / thema / "batches.jsonl", alle, toevoegen=False)
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; samen ${_uitgegeven(thema):.2f} van ${GRENS:.2f}")


APPARAAT = "cpu"  # `--grafische-chip` zet dit op mps: dezelfde vectoren, sneller (B37)


def _zinvectoren(thema: str, zinnen: list[str]) -> np.ndarray:  # pragma: no cover - rekenen op de bestanden
    """De vectoren van de zinnen van Haiku, genormaliseerd; bewaard per modelversie, zodat een zin één keer rekent."""
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts

    model = load_config(None).model_versions.text_embedding
    pad = MAP / thema / f"zinvectoren-{re.sub(r'[^a-zA-Z0-9.-]+', '_', model)}.npz"
    bekend: dict[str, np.ndarray] = {}
    if pad.exists():
        with np.load(pad, allow_pickle=False) as f:
            bekend = dict(zip(f["zinnen"].tolist(), f["vectoren"]))
    nieuw = [z for z in dict.fromkeys(zinnen) if z not in bekend]
    for begin in range(0, len(nieuw), 2000):
        deel = nieuw[begin:begin + 2000]
        v = np.array([f.vector for f in fingerprint_texts(deel, model, apparaat=APPARAAT)], dtype=np.float32)
        bekend.update(zip(deel, v / np.linalg.norm(v, axis=1, keepdims=True)))
        np.savez(pad, zinnen=np.array(list(bekend)), vectoren=np.stack(list(bekend.values())))
        print(f"  {min(begin + 2000, len(nieuw))} van {len(nieuw)} zinnen gerekend", flush=True)
    return np.stack([bekend[z] for z in zinnen]) if zinnen else np.empty((0, 0), dtype=np.float32)


def _groepen(thema: str, drempel: float):  # pragma: no cover - rekenen op de bestanden
    rijen = _jsonl(MAP / thema / "set.jsonl")
    plek = {r["id"]: i for i, r in enumerate(rijen)}
    gelezen = {a["id"]: lees_verhaal(a["antwoord"]) for a in _jsonl(MAP / thema / "antwoorden.jsonl")}
    zin_van = {plek[i]: g["verhaallijn"] for i, g in gelezen.items() if g["past"] and i in plek}
    tel = Counter(zin_van.values())
    zinnen = sorted(tel)
    vectoren = _zinvectoren(thema, zinnen)
    lijnen = verhaallijnen(zinnen, vectoren, drempel, [tel[z] for z in zinnen], ketting=KETTING)
    lijn_van_zin = {zinnen[i]: n for n, l in enumerate(lijnen) for i in l["leden"]}
    lijn_van = {i: lijn_van_zin[z] for i, z in zin_van.items()}
    return rijen, gelezen, lijnen, lijn_van


def _groeperen(thema: str, drempel: float, top: int) -> None:  # pragma: no cover - rekenen op de bestanden
    rijen, gelezen, lijnen, lijn_van = _groepen(thema, drempel)
    past = Counter(g["past"] for g in gelezen.values())
    print(f"{len(gelezen)} gelezen: {past[True]} bij het thema, {past[False]} niet, {past[None]} twijfel; "
          f"{len(lijnen)} verhaallijnen bij drempel {drempel}")
    print(f"dekking van de {min(50, len(lijnen))} grootste: {dekking([l['beweringen'] for l in lijnen])}")
    for naam, woorden in TOETSVERHALEN.items():
        gevraagd = [i for i, r in enumerate(rijen) if r["id"] in gelezen]
        deel = [rijen[i] for i in gevraagd]
        print(f"toetsverhaal {naam}:", toets_verhaal(deel, woorden, {n: lijn_van.get(i) for n, i in enumerate(gevraagd)}))
    leden: dict[int, list[dict]] = {}
    for i, n in lijn_van.items():
        leden.setdefault(n, []).append(rijen[i])
    uit = []
    for n, l in enumerate(lijnen[:top]):
        s = samenvatting(leden[n])
        uit.append({"nr": n, "naam": l["naam"], "zinnen": len(l["leden"]), **s,
                    "voorbeelden": [r["tekst"][:160] for r in leden[n][:5]]})
        print(f"{n:3} {s['cases']:5} cases, {len(s['talen']):2} talen, {s['redacties']:3} redacties, "
              f"{s['jaren'][0] if s['jaren'] else '-'}–{s['jaren'][-1] if s['jaren'] else '-'} | {l['naam'][:110]}")
    (MAP / thema / "lijnen.json").write_text(json.dumps({"drempel": drempel, "versie": VERSIE, "lijnen": uit},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")


def _eerste_jaar(r: dict) -> int | None:  # pragma: no cover - een rij
    jaren = sorted(int(c["datum"][:4]) for c in r["checks"] if c.get("datum", "")[:4].isdigit())
    return jaren[0] if jaren else None


def _terug(thema: str, grens: int, drempel: float) -> None:  # pragma: no cover - rekenen op de bestanden
    """De beslissende telling van PLAN #32.70: van de beweringen die voor het eerst gecheckt zijn in of na `grens`,
    hoeveel horen bij een verhaallijn die er vóór `grens` al was. De verhaallijnen komen alleen uit de oude zinnen.
    Ernaast dezelfde telling op de ruwe beweringen (de vingerafdrukken uit de database), zonder de zin van Haiku."""
    import random
    import sqlite3

    from doublecheck.config import load_config

    rijen = _jsonl(MAP / thema / "set.jsonl")
    gelezen = {a["id"]: lees_verhaal(a["antwoord"]) for a in _jsonl(MAP / thema / "antwoorden.jsonl")}
    jaar = [_eerste_jaar(r) for r in rijen]
    oud_i = [i for i, r in enumerate(rijen) if jaar[i] is not None and jaar[i] < grens and r["id"] in gelezen]
    nieuw_i = [i for i, r in enumerate(rijen) if jaar[i] is not None and jaar[i] >= grens and r["id"] in gelezen]
    past = Counter(gelezen[rijen[i]["id"]]["past"] for i in nieuw_i)
    print(f"oud (eerste check vóór {grens}): {len(oud_i)}; nieuw: {len(nieuw_i)} "
          f"(bij het thema {past[True]}, niet {past[False]}, twijfel {past[None]})")
    model = load_config(None).model_versions.text_embedding

    def vec(teksten: list[str]) -> np.ndarray:
        return _zinvectoren(thema, teksten)

    # met de zin van Haiku
    zin = {i: gelezen[rijen[i]["id"]]["verhaallijn"] for i in oud_i + nieuw_i if gelezen[rijen[i]["id"]]["past"]}
    tel = Counter(zin[i] for i in oud_i if i in zin)
    oude_zinnen = sorted(tel)
    ov = vec(oude_zinnen)
    lijnen = verhaallijnen(oude_zinnen, ov, drempel, [tel[z] for z in oude_zinnen], ketting=KETTING)
    lijn_van_oud = [0] * len(oude_zinnen)
    for n, l in enumerate(lijnen):
        for k in l["leden"]:
            lijn_van_oud[k] = n
    cases = {n: l["beweringen"] for n, l in enumerate(lijnen)}
    nieuw_met = [i for i in nieuw_i if i in zin]
    terug = terugkeer(ov, lijn_van_oud, cases, vec([zin[i] for i in nieuw_met]), drempel)
    noemer = past[True] + past[None]
    raak = sum(t is not None for t in terug)
    print(f"verhaallijnen van vóór {grens}: {len(lijnen)}, waarvan {sum(c >= MIN_CASES for c in cases.values())} met "
          f"minstens {MIN_CASES} cases")
    print(f"A, zoals eerst vastgelegd (verhaallijnen als ketens): {raak} van {noemer} = {raak / noemer:.1%}; de "
          f"grootste oude lijn heeft {max(cases.values())} cases" if noemer else "geen nieuwe")
    # B, de telling die geldt (PLAN #32.70, vastgelegd vóór deze telling draaide): alleen directe buren
    nv = vec([zin[i] for i in nieuw_met])
    gew = [tel[z] for z in oude_zinnen]
    for d in (drempel, 0.85, 0.90):
        n_buren = buren(ov, gew, nv, d)
        b = sum(n >= MIN_CASES for n in n_buren)
        print(f"B bij {d:.2f}: {b} van {noemer} = {b / noemer:.1%} heeft minstens {MIN_CASES} oude beweringen met "
              f"hetzelfde verhaal; minstens 1: {sum(n >= 1 for n in n_buren)}")
        if d == drempel:
            terug_b = n_buren
            per_jaar = Counter((jaar[i], n >= MIN_CASES) for i, n in zip(nieuw_met, n_buren))
            print("  per jaar:", {j: f"{per_jaar[(j, True)]} van {per_jaar[(j, True)] + per_jaar[(j, False)]}"
                                 for j in sorted({j for j, _ in per_jaar})})

    # ernaast: de ruwe bewering, met de vingerafdruk uit de database
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    ids = [rijen[i]["id"] for i in oud_i + nieuw_met]
    v: dict[str, np.ndarray] = {}
    for begin in range(0, len(ids), 800):
        deel = ids[begin:begin + 800]
        v.update((c, np.frombuffer(b, dtype=np.float32)) for c, b in conn.execute(
            "SELECT claim_id, payload FROM fingerprint WHERE kind = 'text' AND model_version = ? AND claim_id IN "
            f"({','.join('?' * len(deel))})", (model, *deel)))
    oud_r = [i for i in oud_i if rijen[i]["id"] in v and gelezen[rijen[i]["id"]]["past"]]
    nieuw_r = [i for i in nieuw_met if rijen[i]["id"] in v]
    if oud_r and nieuw_r:
        om = np.stack([v[rijen[i]["id"]] for i in oud_r])
        om = om / np.linalg.norm(om, axis=1, keepdims=True)
        nm = np.stack([v[rijen[i]["id"]] for i in nieuw_r])
        nm = nm / np.linalg.norm(nm, axis=1, keepdims=True)
        for d in (drempel, 0.85, 0.90):
            b2 = buren(om, [1] * len(oud_r), nm, d)
            print(f"ernaast, op de ruwe bewering bij {d:.2f}: {sum(n >= MIN_CASES for n in b2)} van {len(nieuw_r)} = "
                  f"{sum(n >= MIN_CASES for n in b2) / len(nieuw_r):.1%}; minstens 1: {sum(n >= 1 for n in b2)}")

    # een steekproef om te lezen: 50 koppelingen (B) en 25 die nergens bij kwamen, met de drie oude beweringen
    # waarvan de zin er het meest op lijkt
    oud_van_zin: dict[str, list[int]] = {}
    for i in oud_i:
        if i in zin:
            oud_van_zin.setdefault(zin[i], []).append(i)
    rng = random.Random(ZAAD)
    wel = [k for k, n in enumerate(terug_b) if n >= MIN_CASES]
    niet = [k for k, n in enumerate(terug_b) if n < MIN_CASES]
    uit = []
    for soort, kies in (("terug", rng.sample(wel, min(50, len(wel)))), ("los", rng.sample(niet, min(25, len(niet))))):
        for k in kies:
            i = nieuw_met[k]
            top = np.argsort(-(ov @ nv[k]))[:3]
            uit.append({"id": rijen[i]["id"], "soort": soort, "jaar": jaar[i], "buren": terug_b[k],
                        "bewering": rijen[i]["tekst"][:400], "zin": zin[i],
                        "eerder": [{"gelijkenis": round(float(ov[t] @ nv[k]), 2), "zin": oude_zinnen[t],
                                    "bewering": f"{jaar[oud_van_zin[oude_zinnen[t]][0]]}: "
                                                f"{rijen[oud_van_zin[oude_zinnen[t]][0]]['tekst'][:220]}"}
                                   for t in top]})
    _schrijf(MAP / thema / "terugkeer-te-lezen.jsonl", uit, toevoegen=False)
    print(f"{len(uit)} om te lezen in {MAP / thema / 'terugkeer-te-lezen.jsonl'}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["kiezen", "benoemen", "ophalen", "groeperen", "terug"])
    p.add_argument("--grens", type=int, default=2025, help="terug: nieuw is een eerste check in of na dit jaar")
    p.add_argument("--thema", default="oekraine-rusland", choices=sorted(THEMAS))
    p.add_argument("--proef", type=int)
    p.add_argument("--toets", action="store_true", help="alleen de beweringen van de toetsverhalen van §111")
    p.add_argument("--direct", action="store_true", help="los en tegelijk in plaats van via de Batch API")
    p.add_argument("--wacht", type=int, default=0, help="minuten wachten op de batch")
    p.add_argument("--drempel", type=float, default=DREMPEL)
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--grafische-chip", action="store_true", help="embedden op mps: dezelfde vectoren (B37)")
    a = p.parse_args()
    if a.grafische_chip:
        global APPARAAT
        APPARAAT = "mps"
    try:
        if a.stap == "kiezen":
            _kiezen(a.thema)
        elif a.stap == "benoemen":
            _benoemen(a.thema, a.proef, a.toets, a.direct)
        elif a.stap == "ophalen":
            _ophalen(a.thema, a.wacht)
        elif a.stap == "groeperen":
            _groeperen(a.thema, a.drempel, a.top)
        else:
            _terug(a.thema, a.grens, a.drempel)
    except Weigering as e:
        raise SystemExit(str(e)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
