"""De dekking van de bronnenlijst op echte zoekresultaten (PLAN #32.29c).

Per taal (en, es, pt, de) 100 claims uit de database, zoals het product door Brave (`zoekcontrole.zoekvraag`,
`zoekcontrole.brave`, top 10); per vraag hoeveel verschillende goede uitgevers erbij staan, met `bronnen-v2` en
`bronnen-v3` op dezelfde resultaten, met en zonder de factcheckers, en de bovengrens voor groen met de ruime regel.
Bewaard: alleen de adressen van de resultaten; de claimtekst is openbaar. Een beschrijving, geen poort.

    python -m doublecheck.bronnendekking set
    python -m doublecheck.bronnendekking draaien [--proef 5]
    python -m doublecheck.bronnendekking tellen
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from doublecheck import bronnen as br
from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "bronnendekking"
SET, RESULTATEN = UIT / "set.jsonl", UIT / "resultaten.jsonl"
TALEN = ("en", "es", "pt", "de")
N, ZAAD, VANAF, MIN_TEKENS = 100, 32291, "2024-01-01", 30   # vooraf vastgelegd in PLAN #32.29c
BUDGET = 2.50  # PO 2026-11-02: "within $2.50"; Brave tegen de lijstprijs
FACTCHECKERS = ("IFCN", "EFCSN")  # herkomst van een factchecker, ook "IFCN vernieuwing, PO ..."
KOLOMMEN = ("1 goed", "2 goed", "1 goed zonder factcheckers", "2 goed zonder factcheckers", "groen kan",
            "groen kan zonder factcheckers")


def kies(rijen: list[tuple[str, str, str]], n: int, zaad: int) -> list[dict]:
    """Per taal `n` claims (claim, taal, tekst), getrokken met een vast zaad; de volgorde van de invoer telt niet."""
    uit = []
    for taal in sorted({t for _, t, _ in rijen}):
        hier = sorted((c, tekst) for c, t, tekst in rijen if t == taal)
        for i, (c, tekst) in enumerate(random.Random(f"{zaad}-{taal}").sample(hier, min(n, len(hier)))):
            uit.append({"id": f"{taal}-{i:03d}", "claim": c, "taal": taal, "tekst": tekst})
    return uit


def _factchecker(oordelen: list) -> bool:
    return any(str(h).startswith(FACTCHECKERS) for _, h in oordelen)


def tel_vraag(urls: list[str], sites: dict, staat: dict | None = None) -> dict:
    """Voor één top 10: het aantal verschillende goede uitgevers (band goed of officieel, per eigenaar), zonder de
    factcheckers, en of groen met de ruime regel kan als alle resultaten de bewering steunen."""
    res = zc.resultaten_uit({"web": {"results": [{"url": u} for u in urls]}}, sites, staat)
    fc = [_factchecker(br.beoordeel(r["url"], sites)["bronnen"]) for r in res]
    zonder = [r for r, f in zip(res, fc) if not f]
    return {"goed": len({zc.eigenaar(r["site"]) for r in res if zc._goed(r)}),
            "goed_zonder": len({zc.eigenaar(r["site"]) for r in zonder if zc._goed(r)}),
            "groen": zc._gedragen(res, "ruim"), "groen_zonder": zc._gedragen(zonder, "ruim")}


def telling(rijen: list[dict], lijsten: dict[str, dict], staat: dict | None = None) -> dict:
    """Per taal en per lijst: het aantal vragen en hoeveel er elke kolom van `KOLOMMEN` halen."""
    if bad := {r["taal"] for r in rijen} - set(TALEN):
        raise ValueError(f"onbekende taal: {sorted(bad)}")
    uit = {}
    for taal in TALEN:
        hier = [r for r in rijen if r["taal"] == taal]
        if not hier:
            continue
        uit[taal] = {}
        for naam, sites in lijsten.items():
            t = [tel_vraag(r["urls"], sites, staat) for r in hier]
            uit[taal][naam] = {"n": len(hier), "1 goed": sum(x["goed"] >= 1 for x in t),
                               "2 goed": sum(x["goed"] >= 2 for x in t),
                               "1 goed zonder factcheckers": sum(x["goed_zonder"] >= 1 for x in t),
                               "2 goed zonder factcheckers": sum(x["goed_zonder"] >= 2 for x in t),
                               "groen kan": sum(x["groen"] for x in t),
                               "groen kan zonder factcheckers": sum(x["groen_zonder"] for x in t)}
    return uit


def mag_nog(gedaan: int, budget: float = BUDGET) -> bool:
    """Nog een zoekvraag binnen de grens, tegen de lijstprijs."""
    return (gedaan + 1) * zc.ZOEKPRIJS <= budget


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _set() -> None:  # pragma: no cover - op de database
    import sqlite3

    from doublecheck.toelating import buiten_index

    if SET.exists():
        raise SystemExit(f"{SET.name} ligt al vast")
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    buiten = buiten_index(conn)
    rijen = [(c, t, tekst) for c, t, tekst in conn.execute(
        "SELECT DISTINCT c.claim_id, c.language, c.canonical_text FROM claim c JOIN factcheck f USING (claim_id) "
        f"WHERE c.language IN ({','.join('?' * len(TALEN))}) AND f.review_date >= ? AND length(c.canonical_text) >= ?",
        (*TALEN, VANAF, MIN_TEKENS)) if c not in buiten]
    gekozen = kies(rijen, N, ZAAD)
    UIT.mkdir(parents=True, exist_ok=True)
    SET.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in gekozen), encoding="utf-8")
    print(f"{len(gekozen)} claims: " + ", ".join(f"{t} {sum(s['taal'] == t for s in gekozen)}" for t in TALEN))


def _draai(proef: int | None) -> None:  # pragma: no cover - netwerk
    import os
    import time

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = os.environ["BRAVE_API_KEY"]
    gedaan = {r["id"] for r in _jsonl(RESULTATEN)}
    stukken = [s for s in _jsonl(SET) if s["id"] not in gedaan]
    if proef:
        stukken = [s for t in TALEN for s in [x for x in stukken if x["taal"] == t][:proef]]
    n = len(gedaan)
    for s in stukken:
        if not mag_nog(n):
            print(f"gestopt op de grens van ${BUDGET:.2f}", flush=True)
            break
        try:
            antwoord = zc.brave(zc.zoekvraag(s["tekst"]), sleutel)
        except Exception as e:  # noqa: BLE001 - de soort fout, nooit de inhoud
            print(f"{s['id']}: {type(e).__name__}", flush=True)
            time.sleep(2)
            continue
        n += 1
        urls = [r["url"] for r in antwoord.get("web", {}).get("results", [])[:zc.N_RESULTATEN]]
        with RESULTATEN.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": s["id"], "taal": s["taal"], "claim": s["claim"], "urls": urls}) + "\n")
        time.sleep(1.1)  # binnen de grens van de zoekdienst
    print(f"{n} zoekvragen, ${n * zc.ZOEKPRIJS:.2f}", flush=True)


def _tellen() -> None:  # pragma: no cover - op de bestanden
    rijen = _jsonl(RESULTATEN)
    lijsten = {naam: json.loads(pad.read_text(encoding="utf-8"))["sites"]
               for naam, pad in (("v2", br.BESTAND_V2), ("v3", br.BESTAND_V3), ("v4", br.BESTAND_V4),
                                  ("v6", br.BESTAND_V6), ("v7", br.BESTAND_V7)) if pad.exists()}
    tel = telling(rijen, lijsten)
    zonder = sum(not r["urls"] for r in rijen)
    print(f"{len(rijen)} zoekvragen ({zonder} zonder resultaat), ${len(rijen) * zc.ZOEKPRIJS:.2f}")
    for taal, per in tel.items():
        eerste = next(iter(per.values()))
        print(f"{taal} (n={eerste['n']}, {' -> '.join(per)}): "
              + "; ".join(f"{k} " + " -> ".join(str(per[v][k]) for v in per) for k in KOLOMMEN))
    (UIT / "telling.json").write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De dekking van de bronnenlijst op echte zoekresultaten (#32.29c)")
    parser.add_argument("stap", choices=("set", "draaien", "tellen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    {"set": _set, "draaien": lambda: _draai(args.proef), "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
