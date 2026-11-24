"""`lezer-v7` op echte screenshots (PLAN #32.33).

De sets van §201: N, 58 echte screenshots van bekend nepnieuws, en W, 60 echte foto's met hun ware bewering, met de
gelezen en gemaskeerde tekst van §188 en de datum; nooit het beeld. Zoals het product, met de batchronde van #32.32
(`uitkomsten._draai`): kring 1, één zoekvraag bij Brave, de 5 checks uit de database zoals `/check` ze opzoekt,
`zoekcontrole.leesverzoek` en `zoekcontrole.na_lezen`; Sonnet via de Batch API op openbare beelden uit M4FC, de
zoekresultaten alleen in het geheugen. Gewaarschuwd met bewijs: rood of oranje met de eigen check als bron, of gelezen
als *bewijst*. Labels in `docs/steekproeven/32.33-screenshots-v7.json`, met de waarden van §201.

    python -m doublecheck.screenshotlezer set
    python -m doublecheck.hittewacht -- python -m doublecheck.screenshotlezer draaien [--proef 5]
    python -m doublecheck.screenshotlezer lezen|tellen

Met `--ronde beeld` (PLAN #32.36, B55) gaat het beeld mee, zwartgemaakt zoals in het product (`opknippen.zwart_beeld`),
via de Batch API op de openbare beelden; labels in `docs/steekproeven/32.36-screenshots-beeld.json`.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from doublecheck import beeldcontrole as bk

WORTEL = Path(__file__).resolve().parent.parent
BRON = WORTEL / "data" / "beeldronde" / "set.jsonl"
RONDE = {"lezer": "lezer-v7", "map": WORTEL / "data" / "screenshotlezer" / "lezer-v7",
         "labels": WORTEL / "docs" / "steekproeven" / "32.33-screenshots-v7.json", "sets": ("N", "W"),
         "ontwikkel": None, "budget": 1.60}  # PO 2026-11-03: "grens $2", met ~$0,35 voor de wachttijd
RONDES = {"tekst": RONDE,
          "beeld": {"lezer": "lezer-v7", "map": WORTEL / "data" / "screenshotlezer" / "lezer-v7-beeld",
                    "labels": WORTEL / "docs" / "steekproeven" / "32.36-screenshots-beeld.json", "sets": ("N", "W"),
                    "ontwikkel": None, "budget": 2.80, "beeld": True, "stuk": 40}}  # PO: "draai binnen $3"
ALARM = ("rood", "oranje")
LABELWAARDEN = ("bewijst", "bewijst niet", "vals groen", "vals", "set fout")  # zoals §201
EIS_BEWIJS, EIS_GROEN, EIS_VALS = 37, 1, 3  # `lezer-v5` in §201, vooraf vastgelegd in PLAN #32.33
# per ronde: bij N minstens zoveel met bewijs en hoogstens zoveel onterecht groen, bij W hoogstens zoveel vals alarm en
# minstens zoveel groen (of geen eis); vooraf vastgelegd in PLAN #32.33 en #32.36
EISEN = {"tekst": (EIS_BEWIJS, EIS_GROEN, EIS_VALS, None), "beeld": (39, 1, 2, 25)}


class Weigering(Exception):
    """Tellen kan niet: iets dat telt zonder label, een label dat niet bestaat, of antwoorden op twee vragen."""


def stukken_uit(rijen: list[dict], urls_per_groep: dict[str, set[str]], groep_van: dict[str, str],
                met_beeld: bool = False) -> list[dict]:
    """De sets van §201: per screenshot de tekst en de datum, de groepen van de eigen claims en alle adressen van hun
    checks; het pad naar het openbare beeld alleen met `met_beeld` (#32.36), nooit het beeld zelf."""
    uit = []
    for r in rijen:
        groepen = sorted({groep_van.get(c, c) for c in r.get("eigen") or []})
        uit.append({"id": r["id"], "set": r["set"], "tekst": r["tekst"], "datum": r.get("datum"), "eigen": groepen,
                    "eigen_urls": sorted(set().union(*(urls_per_groep.get(g, set()) for g in groepen))),
                    **({"beeld": r["beeld"]} if met_beeld else {})})
    return uit


def met_eigen_check(r: dict, s: dict) -> bool:
    return r["kleur"] in ALARM and bk.met_eigen_check(r, set(s.get("eigen_urls") or ()))


def moet_lezen(r: dict, s: dict) -> bool:
    """Bij N elk groen en elk rood of oranje zonder de eigen check als bron; bij W elk rood of oranje."""
    if s["set"] == "N":
        return r["kleur"] == "groen" or (r["kleur"] in ALARM and not met_eigen_check(r, s))
    return r["kleur"] in ALARM


def telling(rijen: list[dict], stukken: list[dict], labels: dict[str, str], ronde: str = "tekst") -> dict:
    """Per set de kleuren en de uitkomsten, bij N gewaarschuwd met bewijs en onterecht groen, bij W vals alarm; met de
    eisen van de ronde (`EISEN`: PLAN #32.33, en #32.36 met het beeld). Weigert zolang iets dat telt geen label heeft;
    een onvolledige run haalt geen eis."""
    fout = sorted({v for v in labels.values() if v not in LABELWAARDEN})
    if fout:
        raise Weigering(f"onbekende labels: {fout}")
    if len({r["vraag"] for r in rijen}) > 1:
        raise Weigering("de antwoorden rusten op meer dan één vraag")
    per_id = {s["id"]: s for s in stukken}
    open_ = sorted(r["id"] for r in rijen if moet_lezen(r, per_id[r["id"]]) and r["id"] not in labels)
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {RONDE['labels'].name}, bijvoorbeeld {open_[0]}")
    uit = {"N": Counter(), "W": Counter()}
    for r in rijen:
        s, label = per_id[r["id"]], labels.get(r["id"])
        d = uit[s["set"]]
        d["n"] += 1
        d["kleur " + (r["kleur"] or "geen")] += 1
        d[r["uitkomst"]] += 1
        d["uit kring 1"] += r["route"] == "database"
        d["kosten"] += r["kosten"]
        if s["set"] == "N" and met_eigen_check(r, s):
            d["gewaarschuwd met bewijs"] += 1
            d["met de eigen check"] += 1
        elif s["set"] == "N" and r["kleur"] in ALARM:
            d["gewaarschuwd met bewijs"] += label == "bewijst"
        elif s["set"] == "N" and r["kleur"] == "groen":
            d["onterecht groen"] += label == "vals groen"
        elif s["set"] == "W" and r["kleur"] in ALARM:
            d["vals alarm"] += label == "vals"
    uit = {k: {**dict(v), "kosten": round(v["kosten"], 3)} for k, v in uit.items()}
    volledig = {r["id"] for r in rijen} >= set(per_id)
    n = lambda set_, k: uit[set_].get(k, 0)  # noqa: E731
    bewijs, groen, vals, w_groen = EISEN[ronde]
    uit["eisen"] = {f"1. N: minstens {bewijs} gewaarschuwd met bewijs": volledig and n("N", "gewaarschuwd met bewijs")
                    >= bewijs,
                    f"2. N: hoogstens {groen} onterecht groen": volledig and n("N", "onterecht groen") <= groen,
                    f"3. W: hoogstens {vals} vals alarm": volledig and n("W", "vals alarm") <= vals}
    if w_groen is not None:
        uit["eisen"][f"4. W: minstens {w_groen} groen"] = volledig and n("W", "kleur groen") >= w_groen
    uit["volledig"] = f"{len({r['id'] for r in rijen})} van {len(per_id)}"
    return uit


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _labels(ronde: dict) -> dict[str, str]:  # pragma: no cover - een bestand; `telling` kijkt de waarden na
    pad = ronde["labels"]
    d = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}
    return {r["id"]: r["label"] for r in d.get("oordelen", [])}


def _set(ronde: dict) -> None:  # pragma: no cover - op de bestanden en de database
    import sqlite3

    from doublecheck import uitkomsten as uk

    pad = uk._paden(ronde)[0]
    if pad.exists():
        raise SystemExit(f"{pad} ligt al vast")
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    groep_van = {c: g for c, g in conn.execute("SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
    urls: dict[str, set[str]] = {}
    for c, u in conn.execute("SELECT claim_id, url FROM factcheck"):
        urls.setdefault(groep_van.get(c, c), set()).add(u)
    stukken = stukken_uit(uk._jsonl(BRON), urls, groep_van, met_beeld=bool(ronde.get("beeld")))
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in stukken), encoding="utf-8")
    print(Counter(s["set"] for s in stukken), sum(bool(s["eigen_urls"]) for s in stukken), "met de eigen check")


def _lezen(ronde: dict) -> None:  # pragma: no cover - op de bestanden
    from doublecheck import uitkomsten as uk

    set_, _, antwoorden, _ = uk._paden(ronde)
    labels, per_id = _labels(ronde), {s["id"]: s for s in uk._jsonl(set_)}
    for r in sorted(uk._jsonl(antwoorden), key=lambda r: (r["set"], r["id"])):
        s = per_id[r["id"]]
        te_labelen = moet_lezen(r, s) and r["id"] not in labels
        bekijken = ronde.get("beeld") and s["set"] == "W" and r["kleur"] == "groen"
        if not te_labelen and not bekijken and r["uitkomst"] in ("onzeker", "klopt niet", "misleidend", "klopt"):
            continue
        print(f"\n== {r['id']} [{r['set']}]{' LABEL' if te_labelen else ''}: {r['uitkomst']} ({r['oordeel']}, "
              f"{r['vorm']}, {r['kleur']}{', eigen check' if met_eigen_check(r, s) else ''}"
              f"{', zwart ' + str(r['zwart']) if r.get('zwart') else ''})\n{s['tekst'][:500]}\nuitleg: {r['uitleg']}")
        for b in r["bronnen"]:
            print(f"  - {b.get('rol')}: {b.get('site') or b.get('redactie')} {b.get('band') or b.get('oordeel') or ''} "
                  f"{b.get('url')}")
        print(f"  eigen: {s['eigen_urls'][:3]}")


def _tellen(ronde: dict, naam: str) -> None:  # pragma: no cover - op de bestanden
    from doublecheck import uitkomsten as uk

    set_, _, antwoorden, _ = uk._paden(ronde)
    rijen = uk._jsonl(antwoorden)
    if {r["vraag"] for r in rijen} - {uk.vingerafdruk(ronde["lezer"])}:
        raise Weigering("de antwoorden rusten op een andere vraag dan de code nu stelt")
    tel = telling(rijen, uk._jsonl(set_), _labels(ronde), naam)
    zwart = [r["zwart"] for r in rijen if "zwart" in r]
    if zwart:
        tijden = sorted(r["zwart_s"] for r in rijen if "zwart_s" in r)
        tel["zwartmaken"] = {"met zwart": sum(n > 0 for n in zwart), "van": len(zwart), "vakken": sum(zwart),
                             "mediaan s": tijden[len(tijden) // 2]}
    (ronde["map"] / "telling.json").write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, c in tel.items():
        print(k, c)
    print(f"samen ${uk._uitgegeven(ronde):.2f} van ${ronde['budget']:.2f}")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    from doublecheck import uitkomsten as uk

    parser = argparse.ArgumentParser(description="lezer-v7 op echte screenshots (PLAN #32.33, #32.36)")
    parser.add_argument("stap", choices=("set", "draaien", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--ronde", choices=tuple(RONDES), default="tekst")
    args = parser.parse_args()
    ronde = RONDES[args.ronde]
    {"set": lambda: _set(ronde), "draaien": lambda: uk._draai(ronde, args.proef), "lezen": lambda: _lezen(ronde),
     "tellen": lambda: _tellen(ronde, args.ronde)}[args.stap]()


if __name__ == "__main__":
    main()
