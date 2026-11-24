"""Screenshots beter lezen, lokaal: een voormeting op de 19 gemiste van §209 (PLAN #32.34).

Drie varianten van de tekstherkenning op de 58 screenshots van N, alle lokaal:
- V0: het product nu (`ocr.extract_text`, Tesseract per schrift);
- V1: Tesseract met elk niet-Latijns pakket uit `TESS_SCHRIFTEN` en met `languages`; de zekerste lezing wint, maar alleen
  als die grotendeels in haar eigen schrift staat (`ocr.aandeel_in_schrift`);
- V2: EasyOCR (Apache 2.0) met dezelfde keuze over `LEZERS_EASY`.
Daarna opknippen en maskeren zoals het product, en de 5 checks die `/check` uit de database haalt: staat de eigen check
erbij? De beelden zijn de openbare M4FC-beelden die al lokaal staan; ze gaan nergens heen. Bewaard wordt alleen de
gemaskeerde tekst, in `data/ocrvoormeting/`. De leesbaarheid van elke tekst van G19 krijgt een label in
`docs/steekproeven/32.34-ocr-leesbaar.json`, gelezen zonder de top 5 ernaast.

    pip install easyocr "torch==2.13.0" "torchvision<0.29"   # alleen voor V2; torch blijft 2.13.0 (DR6)
    python -m doublecheck.hittewacht -- python -m doublecheck.ocrvoormeting lezen
    python -m doublecheck.ocrvoormeting teksten|tellen

Na de meting (BENCHMARK §210) is EasyOCR weer verwijderd: geen kandidaat, en 750 MB gewichten.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from doublecheck.ocr import aandeel_in_schrift

WORTEL = Path(__file__).resolve().parent.parent
SET = WORTEL / "data" / "screenshotlezer" / "lezer-v7" / "set.jsonl"
BEELDEN = WORTEL / "data" / "beeldronde" / "set.jsonl"
UIT = WORTEL / "data" / "ocrvoormeting"
LABELS = WORTEL / "docs" / "steekproeven" / "32.34-ocr-leesbaar.json"
# de 19 die `lezer-v7` in §209 niet met bewijs waarschuwde, vooraf vastgelegd in PLAN #32.34
G19 = ("n-sn-002", "n-sn-008", "n-sn-014", "n-sn-017", "n-sn-018", "n-sn-019", "n-sn-024", "n-sn-031", "n-sn-032",
       "n-sn-034", "n-sn-035", "n-sn-037", "n-sn-040", "n-sn-041", "n-sn-043", "n-sn-044", "n-sn-050", "n-sn-054",
       "n-sn-057")
VARIANTEN = ("V0", "V1", "V2")
TESS_SCHRIFTEN = ("Devanagari", "Bengali", "Telugu", "Tamil", "Kannada", "Gujarati", "Gurmukhi", "Malayalam", "Arabic")
# zonder Tamil: het Tamil-model van EasyOCR 1.7.2 laadt niet (143 tegen 127 tekens); Tamil leest V1 (PLAN #32.34)
LEZERS_EASY = {"Latin": ["en"], "Devanagari": ["hi", "mr", "ne", "en"], "Bengali": ["bn", "as", "en"],
               "Telugu": ["te", "en"], "Kannada": ["kn", "en"]}
LEESBAAR = ("ja", "deels", "nee")
TOP = 5


class Weigering(Exception):
    """Tellen kan niet: een tekst van G19 zonder label, of een label dat niet bestaat."""


def kies_lezing(lezingen: list[tuple[str, str, float]], min_aandeel: float) -> tuple[str, str]:
    """De zekerste lezing (schrift, tekst, zekerheid), maar een niet-Latijnse telt alleen als ze grotendeels in haar
    eigen schrift staat, zoals de tweede lezing van het product (#25.22); de Latijnse telt altijd."""
    geldig = [(z, s, t) for s, t, z in lezingen if s == "Latin" or aandeel_in_schrift(t, s) >= min_aandeel]
    _, schrift, tekst = max(geldig, key=lambda x: x[0])
    return schrift, tekst


def easy_tekst(vondsten: list, hoogte: int) -> tuple[str, float]:
    """De vondsten van EasyOCR (kader, tekst, zekerheid) als regels van boven naar onder, zoals `appletekst.swift`:
    banden van 2% van de hoogte gelden als één regel; met de gemiddelde zekerheid, of -1 zonder tekst."""
    if not vondsten:
        return "", -1.0
    band = max(hoogte * 0.02, 1)
    regels: dict[int, list[tuple[float, str]]] = {}
    for kader, tekst, _ in vondsten:
        midden = sum(p[1] for p in kader) / len(kader)
        regels.setdefault(int(midden // band), []).append((min(p[0] for p in kader), tekst))
    tekst = "\n".join(" ".join(t for _, t in sorted(regels[r])) for r in sorted(regels))
    return tekst, sum(z for _, _, z in vondsten) / len(vondsten)


def eigen_in_top5(kandidaten: list[dict], eigen_groepen: list[str], groep_van: dict[str, str]) -> bool:
    return any(groep_van.get(k["claim"], k["claim"]) in eigen_groepen for k in kandidaten[:TOP])


def telling(rijen: list[dict], labels: dict[tuple[str, str], str]) -> dict:
    """Per variant de eigen check in de top 5 bij G19 en B39, de leesbaarheid bij G19 en de tijd, en of de variant
    kandidaat is volgens de vier eisen van PLAN #32.34. Weigert zolang een tekst van G19 geen label heeft."""
    fout = sorted({v for v in labels.values() if v not in LEESBAAR})
    if fout:
        raise Weigering(f"onbekende labels: {fout}")
    open_ = sorted(f"{r['id']} {r['variant']}" for r in rijen if r["groep"] == "G19" and (r["id"], r["variant"]) not in labels)
    if open_:
        raise Weigering(f"{len(open_)} teksten zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    uit: dict[str, dict] = {}
    for v in sorted({r["variant"] for r in rijen}):
        eigen = [r for r in rijen if r["variant"] == v]
        leesbaar = Counter(labels[(r["id"], v)] for r in eigen if r["groep"] == "G19")
        tijden = sorted(r["een_lezer"] for r in eigen)
        uit[v] = {"G19 top 5": sum(r["top5"] for r in eigen if r["groep"] == "G19"),
                  "B39 top 5": sum(r["top5"] for r in eigen if r["groep"] == "B39"),
                  **{f"G19 leesbaar {k}": leesbaar.get(k, 0) for k in LEESBAAR},
                  "een lezer, mediaan s": tijden[len(tijden) // 2] if tijden else None,
                  "alle lezers, s": round(sum(r["seconden"] for r in eigen), 1)}
    if "V0" in uit:
        nul = uit["V0"]
        for v, d in uit.items():
            d["kandidaat"] = v != "V0" and (d["G19 top 5"] >= nul["G19 top 5"] + 5 and d["B39 top 5"] >= nul["B39 top 5"] - 1
                                            and d["G19 leesbaar ja"] >= nul["G19 leesbaar ja"] + 5
                                            and d["een lezer, mediaan s"] is not None and d["een lezer, mediaan s"] <= 5)
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _labels() -> dict[tuple[str, str], str]:  # pragma: no cover - een bestand
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {(r["id"], r["variant"]): r["label"] for r in d.get("oordelen", [])}


def _lezen() -> None:  # pragma: no cover - live, lokaal: Tesseract, EasyOCR, het tekstmodel en de database
    import sqlite3

    import pytesseract
    import torch
    from PIL import Image

    from doublecheck import berichtcontrole as bc
    from doublecheck import ocr
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.storage import connect

    torch.set_num_threads(2)  # hoogstens twee kernen
    config = load_config(None)
    o = config.ocr
    conn = connect(str(WORTEL / "doublecheck.db"))
    groep_van = {c: g for c, g in sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True).execute(
        "SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
    paden = {s["id"]: s["beeld"] for s in _jsonl(BEELDEN)}
    stukken = [s for s in _jsonl(SET) if s["set"] == "N"]
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / "lezingen.jsonl"
    gedaan = {(r["id"], r["variant"]) for r in _jsonl(pad)}
    lezers: dict[str, object] = {}

    def tesseract(beeld, pakketten: str) -> tuple[str, float, float]:
        begin = time.perf_counter()
        try:
            tekst, zekerheid = ocr._lees_met_zekerheid(beeld, pakketten, o.timeout_seconds)
        except (RuntimeError, pytesseract.TesseractError):
            tekst, zekerheid = "", -1.0
        return tekst, zekerheid, time.perf_counter() - begin

    def easy(beeldpad: str, schrift: str, hoogte: int) -> tuple[str, float, float]:
        import easyocr

        if schrift not in lezers:
            lezers[schrift] = easyocr.Reader(LEZERS_EASY[schrift], gpu=False, verbose=False)
        begin = time.perf_counter()
        tekst, zekerheid = easy_tekst(lezers[schrift].readtext(beeldpad), hoogte)
        return tekst, zekerheid, time.perf_counter() - begin

    for n, s in enumerate(stukken):
        beeldpad = paden[s["id"]]
        beeld = Image.open(beeldpad).convert("RGB")
        for v in VARIANTEN:
            if (s["id"], v) in gedaan:
                continue
            if v == "V0":
                begin = time.perf_counter()
                tekst, schrift = ocr.extract_text(beeld, o).text, "product"
                seconden = een = time.perf_counter() - begin
            else:
                namen = ("Latin",) + (TESS_SCHRIFTEN if v == "V1" else tuple(k for k in LEZERS_EASY if k != "Latin"))
                lezingen, tijd = [], {}
                for schrift in namen:
                    if v == "V1":
                        t, z, sec = tesseract(beeld, o.languages if schrift == "Latin" else o.schriften[schrift])
                    else:
                        t, z, sec = easy(beeldpad, schrift, beeld.height)
                    lezingen.append((schrift, t, z))
                    tijd[schrift] = sec
                schrift, tekst = kies_lezing(lezingen, o.schrift_min_aandeel)
                seconden, een = sum(tijd.values()), tijd[schrift]
            bericht = bc.samenstellen(None, bc.opknippen(tekst))
            kandidaten = []
            if bericht.strip():
                fp = fingerprint_texts([bericht[:600]], config.model_versions.text_embedding)[0]
                kandidaten = bc.geheugen_met(conn, config, bericht, fp, [])
            rij = {"id": s["id"], "groep": "G19" if s["id"] in G19 else "B39", "variant": v, "schrift": schrift,
                   "tekst": bericht, "top5": eigen_in_top5(kandidaten, s["eigen"], groep_van),
                   "seconden": round(seconden, 2), "een_lezer": round(een, 2)}
            with pad.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
        print(f"{n + 1}/{len(stukken)} {s['id']}", flush=True)


def _teksten() -> None:  # pragma: no cover - op de bestanden
    """De teksten van G19 per variant, zonder de top 5 ernaast (PLAN #32.34), voor de labels."""
    labels = _labels()
    for r in sorted(_jsonl(UIT / "lezingen.jsonl"), key=lambda r: (r["id"], r["variant"])):
        if r["groep"] == "G19" and (r["id"], r["variant"]) not in labels:
            print(f"\n== {r['id']} {r['variant']} ({r['schrift']})\n{r['tekst'][:700]}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    uit = telling(_jsonl(UIT / "lezingen.jsonl"), _labels())
    (UIT / "telling.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    for v, d in uit.items():
        print(v, d)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Screenshots beter lezen, lokaal (PLAN #32.34)")
    parser.add_argument("stap", choices=("lezen", "teksten", "tellen"))
    args = parser.parse_args()
    {"lezen": _lezen, "teksten": _teksten, "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
