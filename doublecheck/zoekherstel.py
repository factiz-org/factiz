"""Het zoeken voor screenshots herstellen (P4 van fase 0, PLAN #32.0b, B47).

In §155 stond de eigen check van een echt screenshot met tekst maar bij 71 van
de 150 bij de vijf beste uit het geheugen: de virale tekst staat ver af van de
samenvatting van de redactie, en de OCR maakt hem rommeliger. Vier varianten,
vooraf vastgelegd in PLAN #32.0b:

- V0 zoals §155: de tekst van Tesseract, één zoekvraag;
- V1 de tekst van Apple Vision (`appletekst.swift`, de OCR van macOS zelf);
- V2 Tesseract, plus hoogstens drie beweringen met elk twee zoekvragen, door
  een model uit de tekst gehaald; per check telt de hoogste gelijkenis;
- V3 als V2, op de tekst van Apple Vision.

V2 en V3 elk met Haiku 5.5 en Sonnet 5.5. Achteraf toegevoegd (PO 2026-10-27): V4 de
tekst van Google Cloud Vision, en V5 als V2 op die tekst. In het product blijft het
beeld lokaal (B43); hier gaan alleen openbare M4FC-beelden naar Google, zoals in §148. Het model leest alleen; het zoekt
niet en oordeelt niet. De beelden zijn openbare M4FC-beelden die al op schijf
staan; er wordt geen beeld bijgeschreven (B35).
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

from doublecheck.beweringvraag import (  # noqa: F401 - verhuisd naar de kern (PLAN #32.7c)
    EXTRACTIEVRAAG,
    MAX_BEWERINGEN,
    MAX_ZOEKVRAGEN,
    TOP,
    _SCHEMA,
    lees_extractie,
    voeg_samen,
    zoekvragen,
)

UIT = Path("data/zoekherstel")
ROUTE = Path("data/route/set.jsonl")
APPLETEKST = UIT / "appletekst"
BUDGET = 2.5  # PLAN #32.0b
N_NIEUW = 100
ZAAD = 3110  # de volgorde van §155 (routemeting.ZAAD)
SCHATTING = {"haiku": 0.0003, "sonnet": 0.003}  # per verzoek via de Batch API, ruim
VARIANTEN = ("V0", "V1", "V2-haiku", "V2-sonnet", "V3-haiku", "V3-sonnet", "V4", "V5-haiku", "V5-sonnet")
BRON = {v: {"0": "tesseract", "2": "tesseract", "1": "apple", "3": "apple", "4": "google", "5": "google"}[v[1]]
        for v in VARIANTEN}
OCR_KORT = {"t": "tesseract", "a": "apple", "g": "google"}
VISION = "https://vision.googleapis.com/v1/images:annotate"
VISION_PRIJS = 0.0015  # per beeld, $1,50 per 1.000 (de eerste 1.000 per maand gratis)
ONWAAR = ("onwaar", "misleidend")


class Weigering(RuntimeError):
    pass


def treffer(kandidaten: list[dict], eigen, n: int = TOP) -> bool:
    eigen = set(eigen)
    return any(k["claim"] in eigen for k in kandidaten[:n])


def extractieverzoek(custom_id: str, tekst: str, model: str) -> dict:
    from doublecheck.leraar import MODELLEN

    vraag = EXTRACTIEVRAAG.format(n=MAX_BEWERINGEN, m=MAX_ZOEKVRAGEN, tekst=tekst)
    return {"custom_id": custom_id, "params": {
        "model": MODELLEN[model]["id"], "max_tokens": 1_500, "messages": [{"role": "user", "content": vraag}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def vision_verzoek(data: bytes) -> dict:
    """Alleen de tekst lezen; geen omgekeerd zoeken, geen labels."""
    return {"requests": [{"image": {"content": base64.b64encode(data).decode()},
                          "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]}


def lees_google(antwoord: dict) -> str:
    eerste = (antwoord.get("responses") or [{}])[0]
    return "" if "error" in eerste else (eerste.get("fullTextAnnotation") or {}).get("text", "")


def telling(stukken: list[dict], uitslagen: dict[str, dict[str, list[dict]]]) -> dict:
    """Per variant de treffers bij de vijf beste, en tegen V0: wat er van de gevonden kwijtraakte en wat er van
    de gemiste bij kwam."""
    v0 = {s["id"] for s in stukken if treffer(uitslagen["V0"].get(s["id"], []), s["eigen"])}
    uit = {}
    for variant, per_id in uitslagen.items():
        raak = {s["id"] for s in stukken if treffer(per_id.get(s["id"], []), s["eigen"])}
        uit[variant] = {"treffers": len(raak), "n": len(stukken), "van de gevonden kwijt": len(v0 - raak),
                        "van de gemiste gevonden": len(raak - v0)}
    return uit


# --- het lezen, het zoeken en de CLI --------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")


def apple_lees(paden: list[str]) -> dict[str, str]:  # pragma: no cover - met Swift en Vision
    """De tekst per beeld, met de OCR van macOS; het programma wordt één keer gebouwd."""
    if not APPLETEKST.exists():
        bron = Path(__file__).with_name("appletekst.swift")
        subprocess.run(["swiftc", "-O", str(bron), "-o", str(APPLETEKST)], check=True)
    uit = subprocess.run([str(APPLETEKST)], input="\n".join(paden) + "\n", capture_output=True, text=True,
                         check=True).stdout
    return {r["pad"]: r["tekst"] for r in map(json.loads, uit.splitlines())}


def google_lees(pad: str, sleutel: str) -> str:  # pragma: no cover - met Google Cloud Vision
    import httpx

    verzoek = vision_verzoek(Path(pad).read_bytes())
    for poging in range(4):
        antwoord = httpx.post(VISION, params={"key": sleutel}, json=verzoek, timeout=60)
        if antwoord.status_code == 200:
            return lees_google(antwoord.json())
        if antwoord.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"Vision {antwoord.status_code}: {antwoord.text[:300]}")
        time.sleep(5 * 2 ** poging)
    raise RuntimeError("Vision blijft weigeren; later hervatten")


def _sets() -> dict[str, list[dict]]:  # pragma: no cover - op de bestanden
    route = _jsonl(ROUTE)
    return {"route": [s for s in route if s["deel"] == "S-onwaar"], "waar": [s for s in route if s["deel"] == "S-waar"],
            "nieuw": _jsonl(UIT / "nieuw.jsonl")}


def kies_nieuw() -> list[dict]:  # pragma: no cover - met de OCR, de database en M4FC
    """De volgende 100 Engelse M4FC-screenshots met tekst, in de volgorde van §155, nooit gebruikt."""
    import sqlite3

    from doublecheck import routemeting as rm
    from doublecheck import verificatie as v
    from doublecheck.config import load_config
    from doublecheck.ocr import extract_text
    from doublecheck.opknippen import knip, maskeer

    config = load_config(None)
    lees = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    lees.row_factory = sqlite3.Row
    gebruikt = {s.get("sleutel") for pad in Path("data").glob("*/set.jsonl") for s in _jsonl(pad)}
    uit = []
    for k in rm.beeldkandidaten():
        if len(uit) >= N_NIEUW:
            break
        if k["sleutel"] in gebruikt:
            continue
        ruw = extract_text(Path(k["beeld"]).read_bytes(), config.ocr).text
        if rm.soort_van(ruw) != "S" or rm.verraadt(ruw):
            continue
        uit.append({"id": f"sn-{len(uit):03d}", "sleutel": k["sleutel"], "zaak": k.get("zaak"), "helft": k["helft"],
                    "beeld": k["beeld"], "tekst": maskeer(knip(ruw)), "eigen": sorted(v.eigen_cluster(lees, k.get("zaak")))})
        print(f"\r{len(uit)}", end="", flush=True)
    _schrijf(UIT / "nieuw.jsonl", uit)
    return uit


def _beeldpad(s: dict) -> str:  # pragma: no cover - op de basisset
    if s.get("beeld"):
        return s["beeld"]
    from doublecheck import basisset

    return next(b["beeld"] for b in basisset.lees() if b["sleutel"] == s["sleutel"])


def main() -> None:  # pragma: no cover - CLI, met de database en de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="Het zoeken voor screenshots herstellen (PLAN #32.0b)")
    parser.add_argument("stap", choices=("nieuw", "apple", "google", "indienen", "ophalen", "zoeken", "tellen"))
    parser.add_argument("--set", default="route", choices=("route", "nieuw", "waar"))
    parser.add_argument("--modellen", default="haiku,sonnet")
    parser.add_argument("--ocr", default="tesseract,apple")
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "nieuw":
        kies_nieuw()
        return
    stukken = _sets()[args.set]
    apple = {r["id"]: r["tekst"] for r in _jsonl(UIT / "apple.jsonl")}
    google = {r["id"]: r["tekst"] for r in _jsonl(UIT / "google.jsonl")}
    if args.stap == "google":
        import os

        from doublecheck import basisset
        from doublecheck.opknippen import knip, maskeer
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        sleutel = os.environ["GOOGLE_VISION_API_KEY"]
        paden = {b["sleutel"]: b["beeld"] for b in basisset.lees() if b.get("beeld")}
        nodig = [s for s in stukken if s["id"] not in google]
        batches = _jsonl(UIT / "batches.jsonl")
        uitgegeven = sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"] for b in batches)
        if uitgegeven + len(nodig) * VISION_PRIJS > BUDGET:
            raise Weigering(f"${uitgegeven:.2f} plus {len(nodig)} beelden tegen ${BUDGET:.2f}")
        with (UIT / "google.jsonl").open("a", encoding="utf-8") as fh:
            for i, s in enumerate(nodig):
                tekst = google_lees(s.get("beeld") or paden[s["sleutel"]], sleutel)
                fh.write(json.dumps({"id": s["id"], "tekst": maskeer(knip(tekst))}, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"\r{i + 1}/{len(nodig)}", end="", flush=True)
        batches.append({"id": f"google-{args.set}-{len(batches)}", "schatting": round(len(nodig) * VISION_PRIJS, 4),
                        "werkelijk": round(len(nodig) * VISION_PRIJS, 4), "ids": []})
        _schrijf(UIT / "batches.jsonl", batches)
        print(f"\n{len(nodig)} gelezen, hoogstens ${len(nodig) * VISION_PRIJS:.2f}")
        return
    if args.stap == "apple":
        from doublecheck.opknippen import knip, maskeer

        from doublecheck import basisset

        paden = {b["sleutel"]: b["beeld"] for b in basisset.lees() if b.get("beeld")}
        nodig = [s for s in stukken if s["id"] not in apple]
        gelezen = apple_lees([s.get("beeld") or paden[s["sleutel"]] for s in nodig])
        rijen = _jsonl(UIT / "apple.jsonl") + [
            {"id": s["id"], "tekst": maskeer(knip(gelezen.get(s.get("beeld") or paden[s["sleutel"]], "")))} for s in nodig]
        _schrijf(UIT / "apple.jsonl", rijen)
        print(f"{len(nodig)} gelezen; leeg: {sum(not r['tekst'].strip() for r in rijen)}")
        return
    if args.stap in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.leraar import MODELLEN
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        batches = _jsonl(UIT / "batches.jsonl")
        if args.stap == "indienen":
            al = {i for b in batches for i in b["ids"]}
            verzoeken, geschat = [], 0.0
            for model in args.modellen.split(","):
                for ocr in args.ocr.split(","):
                    for s in stukken[: args.proef or None]:
                        cid = f"{model[0]}{ocr[0]}-{s['id']}"
                        tekst = {"tesseract": s["tekst"], "apple": apple.get(s["id"]), "google": google.get(s["id"])}[ocr]
                        if cid in al or tekst is None:
                            continue
                        verzoeken.append(extractieverzoek(cid, tekst[:3000], model))
                        geschat += SCHATTING[model]
            uitgegeven = sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"] for b in batches)
            if not verzoeken or uitgegeven + geschat > BUDGET:
                raise Weigering(f"{len(verzoeken)} verzoeken: ${uitgegeven:.2f} plus ${geschat:.2f} tegen ${BUDGET:.2f}")
            batch = client.messages.batches.create(requests=verzoeken)
            batches.append({"id": batch.id, "schatting": round(geschat, 3), "ids": [v["custom_id"] for v in verzoeken]})
            print(f"batch {batch.id}: {len(verzoeken)} verzoeken, geschat ${geschat:.2f}; samen ${uitgegeven + geschat:.2f}")
        else:
            rijen = _jsonl(UIT / "extracties.jsonl")
            for b in batches:
                if b.get("werkelijk") is not None or client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    continue
                kosten = 0.0
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded":
                        print(f"{r.custom_id}: {r.result.type}")
                        continue
                    msg = r.result.message
                    soort, sid = r.custom_id.split("-", 1)
                    model = "haiku" if soort[0] == "h" else "sonnet"
                    prijs = MODELLEN[model]
                    kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
                    tekst = "".join(getattr(blok, "text", "") or "" for blok in msg.content)
                    rijen.append({"id": sid, "model": model, "ocr": OCR_KORT[soort[1]],
                                  "beweringen": lees_extractie(tekst)})
                b["werkelijk"] = round(kosten, 4)
            _schrijf(UIT / "extracties.jsonl", rijen)
            print(Counter((r["model"], r["ocr"]) for r in rijen), f"${sum(b.get('werkelijk') or 0 for b in batches):.3f}")
        _schrijf(UIT / "batches.jsonl", batches)
        return
    if args.stap == "zoeken":
        zoek(args.set, stukken, {"apple": apple, "google": google})
        return
    uitslagen: dict[str, dict] = {}
    for r in _jsonl(UIT / f"uitslag-{args.set}.jsonl"):
        uitslagen.setdefault(r["variant"], {})[r["id"]] = r["kandidaten"]
    uit = {"alles": telling(stukken, uitslagen)}
    for helft in ("ontwikkel", "toets"):
        deel = [s for s in stukken if s.get("helft") == helft]
        if deel:
            uit[helft] = {k: v["treffers"] for k, v in telling(deel, uitslagen).items()}
    if args.set == "waar":
        v0 = uitslagen["V0"]
        uit["onwaar bovenaan, nieuw"] = {
            variant: sum(1 for s in stukken if per_id.get(s["id"]) and per_id[s["id"]][0]["oordeel"] in ONWAAR
                         and not (v0.get(s["id"]) and v0[s["id"]][0]["oordeel"] in ONWAAR))
            for variant, per_id in uitslagen.items()}
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def zoek(naam: str, stukken: list[dict], lezingen: dict[str, dict[str, str]]) -> None:  # pragma: no cover - model en database
    """Elke variant door het geheugen: dezelfde vingerafdruk, dezelfde zoekfunctie en dezelfde vloer als §155."""
    import sqlite3

    from doublecheck import verificatie as v
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    versie = load_config(None).model_versions.text_embedding
    conn = connect("doublecheck.db")
    lees = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    lees.row_factory = sqlite3.Row
    extracties = {(r["id"], r["model"], r["ocr"]): r["beweringen"] for r in _jsonl(UIT / "extracties.jsonl")}
    pad = UIT / f"uitslag-{naam}.jsonl"
    klaar = {(r["variant"], r["id"]) for r in _jsonl(pad)}

    def lijsten(teksten: list[str]) -> list[list[dict]]:
        fps = fingerprint_texts([t[:600] for t in teksten], versie)
        return [v.kandidaten_uit(lees, lijst) for lijst in search_texts(conn, fps, 8, varianten=True)]

    with pad.open("a", encoding="utf-8") as fh:
        for i, s in enumerate(stukken):
            ocr = {"tesseract": s["tekst"], **{k: v.get(s["id"]) for k, v in lezingen.items()}}
            for variant in VARIANTEN:
                if (variant, s["id"]) in klaar:
                    continue
                bron = BRON[variant]
                tekst = ocr[bron]
                if tekst is None:
                    continue
                gehaald = [] if "-" not in variant else extracties.get((s["id"], variant[3:], bron))
                if gehaald is None:
                    continue
                vragen = zoekvragen(tekst, gehaald)
                kand = voeg_samen(lijsten(vragen))
                fh.write(json.dumps({"variant": variant, "id": s["id"], "vragen": len(vragen),
                                     "kandidaten": [{k: c[k] for k in ("claim", "gelijkenis", "oordeel")} for c in kand]},
                                    ensure_ascii=False) + "\n")
                fh.flush()
            print(f"\r{i + 1}/{len(stukken)}", end="", flush=True)
    print()


if __name__ == "__main__":
    main()
