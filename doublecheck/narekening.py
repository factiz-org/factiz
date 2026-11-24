"""Herrekening van *niet bevestigd* op de bewaarde antwoorden van een meting, zonder nieuwe vragen (PLAN #32.42, PO
2026-11-06): wat de uitkomst doet als ze niet geldt voor oud nieuws, en niet als een onafhankelijke bron zonder band het
bericht bevestigt. Een meting, geen productcode: de regels staan niet in `zoekcontrole`.

Vastgelegd vóór het rekenen (meetdatum 2026-11-05):
- oud is van vóór 2024-11-05, twee jaar; als gevoeligheid één jaar;
- (a1) oud volgens de datum van het item, het plafond: wat Factiz zou doen als het de leeftijd altijd wist;
- (a2) oud volgens wat Factiz zelf ziet: het nieuwste jaartal in het bericht is 2023 of eerder. 2024 telt niet als oud,
  want twijfel versoepelt nooit: bij twijfel blijft de waarschuwing staan. Gewone tekst heeft geen gebeurtenis;
- (b) een geciteerde bron met rol *bevestigt*, zonder band, geen platform en geen staatsmedia; als gevoeligheid twee
  verschillende sites, en *wisselend* erbij.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

from doublecheck import meting as mt
from doublecheck import staatsmedia
from doublecheck import zoekcontrole as zc

GRENS = {2: "2024-11-05", 1: "2025-11-05"}
JAAR_OUD = {2: 2023, 1: 2024}
GEWOON = {"G", "G2"}
JAARTAL = re.compile(r"(?<![0-9])(199[0-9]|20[0-2][0-9])(?![0-9])")
PLANNEN = ("docs/meetplannen/32.41.json", "docs/meetplannen/32.42-es.json", "docs/meetplannen/32.42-pt.json",
           "docs/meetplannen/32.42-de.json", "docs/meetplannen/32.42-pt-w.json")


def oud_volgens_datum(item: dict, jaren: int = 2) -> bool:
    d = item.get("datum") or ""
    return item["set"] not in GEWOON and bool(d) and d < GRENS[jaren]


def oud_volgens_tekst(item: dict, jaren: int = 2) -> bool:
    """Alleen jaartallen in Arabische cijfers; een ander schrift geeft geen jaartal, dus blijft de waarschuwing."""
    jaartallen = [int(j) for j in JAARTAL.findall(item["tekst"])]
    return bool(jaartallen) and max(jaartallen) <= JAAR_OUD[jaren]


def bevestigd_zonder_band(rij: dict, staat: dict, banden: tuple = (None,), minimum: int = 1) -> bool:
    sites = {b.get("site") for b in rij["bronnen"]
             if b.get("rol") == "bevestigt" and b.get("band") in banden and b.get("soort") != "platform"
             and not staatsmedia.label(b.get("url", ""), staat)}
    return len(sites) >= minimum


def met_kopjesbalk(item: dict) -> bool:
    """Een artikel van Wikinews van vóór 2024 met twee of meer jaartallen vanaf 2025: de balk met de laatste koppen
    van de site kwam mee in plaats van het begin van het artikel."""
    return (item.get("datum") or "9999") < "2024" and sum(int(j) >= 2025 for j in JAARTAL.findall(item["tekst"])) >= 2


def regels(staat: dict) -> dict:
    return {
        "a1 datum": lambda r, i: oud_volgens_datum(i),
        "a2 jaartal": lambda r, i: oud_volgens_tekst(i),
        "b zonder band": lambda r, i: bevestigd_zonder_band(r, staat),
        "a2 + b": lambda r, i: oud_volgens_tekst(i) or bevestigd_zonder_band(r, staat),
        "a1 + b": lambda r, i: oud_volgens_datum(i) or bevestigd_zonder_band(r, staat),
        "gevoeligheid a1, 1 jaar": lambda r, i: oud_volgens_datum(i, 1),
        "gevoeligheid a2, 1 jaar": lambda r, i: oud_volgens_tekst(i, 1),
        "gevoeligheid b, 2 sites": lambda r, i: bevestigd_zonder_band(r, staat, minimum=2),
        "gevoeligheid b, met wisselend": lambda r, i: bevestigd_zonder_band(r, staat, banden=(None, "wisselend")),
        "gevoeligheid a2 + b, 2 sites": lambda r, i: oud_volgens_tekst(i) or bevestigd_zonder_band(r, staat,
                                                                                                    minimum=2),
    }


def toepassen(rijen: list[dict], items: dict[str, dict], regel) -> list[dict]:
    """Elke *niet bevestigd* waar de regel op slaat, wordt weer *onzeker*; de rest blijft zoals hij was."""
    return [{**r, "uitkomst": "onzeker"} if r["uitkomst"] == "niet bevestigd" and regel(r, items[r["id"]]) else r
            for r in rijen]


def zonder_lek(rijen: list[dict], labels: dict[str, str], weg) -> dict:
    """Wat er over is als de pagina's waar `weg(url)` ja op zegt (factcheckers en hun rubrieken, het dichte filter van
    #32.43) niet in de resultaten hadden gestaan, zonder nieuwe vragen. Een waarschuwing houdt haar tegenspraak alleen
    met een tegensprekende bron die blijft. Een groen blijft alleen gedragen door de bevestigende bronnen die blijven,
    met de ruime regel (`zoekcontrole._gedragen`). Het is een schatting: wat de lezer zonder die pagina's gezegd had,
    weet niemand."""
    from doublecheck import zoekcontrole as zc

    tel = dict.fromkeys(("alarm", "alarm zonder tegenspraak", "bewijst", "bewijst zonder tegenspraak",
                         "bewijst met tegenspraak", "niet bevestigd", "groen", "groen niet meer gedragen",
                         "groen vals niet meer gedragen"), 0)
    for r in rijen:
        label = labels.get(f"{r['id']}#{r['arm']}")
        blijft = [b for b in r["bronnen"] if not weg(b.get("url") or "")]
        if r["kleur"] in ("rood", "oranje"):
            tegen = any(b.get("rol") == "spreekt tegen" for b in blijft)
            tel["alarm"] += 1
            tel["alarm zonder tegenspraak"] += not tegen
            if label == "bewijst":
                tel["bewijst"] += 1
                tel["bewijst met tegenspraak" if tegen else "bewijst zonder tegenspraak"] += 1
        elif r["kleur"] == "groen":
            gedragen = zc._gedragen([b for b in blijft if b.get("rol") == "bevestigt"], "ruim")
            tel["groen"] += 1
            tel["groen niet meer gedragen"] += not gedragen
            tel["groen vals niet meer gedragen"] += not gedragen and label == "vals"
        tel["niet bevestigd"] += r["uitkomst"] == "niet bevestigd"
    return tel


# De media van de koppen en hun sites: die van het product (`zoekcontrole.MEDIA`, v11)
MEDIUMSITES = zc.MEDIA


def eigen_kop(rij: dict, bericht: str) -> bool:
    """Een echte kop op de eigen site (#32.45, §232, vastgelegd vóór het tellen) op een bewaard antwoord: de lezer zei
    zelf *klopt*, niets spreekt het tegen, en `zoekcontrole.eigen_kop` op de bevestigende bronnen. Dan mag *onzeker* of
    *niet bevestigd* groen worden."""
    if rij.get("oordeel") != "klopt" or any(b.get("rol") == "spreekt tegen" for b in rij["bronnen"]):
        return False
    return zc.eigen_kop(bericht, [b for b in rij["bronnen"] if b.get("rol") == "bevestigt"])


KOPPLANNEN = (*PLANNEN[:4], "docs/meetplannen/32.43-en.json", "docs/meetplannen/32.43-pt.json",
              "docs/meetplannen/32.43-es.json", "docs/meetplannen/32.43-de.json",
              "docs/meetplannen/poproef-2026-11-07-2.json")


def koppen() -> None:  # pragma: no cover - op de bestanden
    """`eigen_kop` op de bewaarde antwoorden: welke echte koppen (W-merk) groen worden, en of een nagemaakte kop onder een
    echte naam (set M) ooit groen wordt (BENCHMARK §232)."""
    uit = {}
    for pad in KOPPLANNEN:
        plan = mt.lees_plan(pad)
        rijen = mt._jsonl(plan["_map"] / "antwoorden.jsonl")
        items = {s["id"]: s for s in mt._jsonl(plan["_map"] / "set.jsonl")}
        for naam in ("W-merk", "M"):
            deel = [r for r in rijen if r["set"] == naam]
            if not deel:
                continue
            nu = collections.Counter(r["uitkomst"] for r in deel)
            groen = [r for r in deel if r["kleur"] is None and r["uitkomst"] in ("onzeker", "niet bevestigd")
                     and eigen_kop(r, items[r["id"]]["tekst"])]
            sleutel = f"{plan['taak']} {naam}"
            uit[sleutel] = {"n": len(deel), "nu": dict(nu), "wordt groen": len(groen),
                            "welke": [items[r["id"]]["tekst"].replace("\n", " / ")[:120] for r in groen]}
            print(f"{sleutel:30} {uit[sleutel]}")
    Path("data/meting/koppen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")


LEKPLANNEN = (*PLANNEN, "docs/meetplannen/32.43-en.json", "docs/meetplannen/32.43-pt.json")


def lek() -> None:  # pragma: no cover - op de bestanden en de database
    """`zonder_lek` op de sets als op de eerste dag van #32.41 tot en met #32.43, per set (BENCHMARK §227)."""
    from doublecheck import berichtcontrole as bc
    from doublecheck import speuren as sp

    hosts = sp.eerste_dag_domeinen(bc.herkomstlijst()["sites"])
    uit = {}
    for pad in LEKPLANNEN:
        plan = mt.lees_plan(pad)
        rijen = mt._jsonl(plan["_map"] / "antwoorden.jsonl")
        items = {s["id"]: s for s in mt._jsonl(plan["_map"] / "set.jsonl")}
        labels = {**{f"{r['id']}#{r['arm']}": mt.auto_label(r, items[r["id"]]) for r in rijen}, **mt._labels(plan)}
        for naam, s in plan["sets"].items():
            if s.get("eerste_dag"):
                deel = [r for r in rijen if r["set"] == naam]
                sleutel = f"{plan['taak']} {naam}"
                uit[sleutel] = zonder_lek(deel, labels, lambda u: sp.van_factchecker(u, hosts))
                print(f"{sleutel:20} {uit[sleutel]}")
    doel = Path("data/meting/lek.json")
    doel.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{doel} ({len(hosts)} factchecksites)")


def narekenen(plan: dict, staat: dict) -> dict:  # pragma: no cover - op de bestanden
    rijen = mt._jsonl(plan["_map"] / "antwoorden.jsonl")
    items = {s["id"]: s for s in mt._jsonl(plan["_map"] / "set.jsonl")}
    labels = mt._labels(plan)
    voor = mt.telling(rijen, labels, plan, items)["eisen"]
    nb = [r for r in rijen if r["uitkomst"] == "niet bevestigd"]

    def soort(r):
        return f"{r['set']} " + ("onwaar" if r["set"] in plan["onwaar"] else labels.get(f"{r['id']}#{r['arm']}", "?"))

    uit = {"niet bevestigd": dict(collections.Counter(soort(r) for r in nb)),
           "eisen": {k: v["waarde"] for k, v in voor.items()},
           "kopjesbalk": dict(collections.Counter(r["uitkomst"] for r in rijen if met_kopjesbalk(items[r["id"]]))),
           "regels": {}}
    for naam, regel in regels(staat).items():
        na = mt.telling(toepassen(rijen, items, regel), labels, plan, items)["eisen"]
        uit["regels"][naam] = {
            "weg": dict(collections.Counter(soort(r) for r in nb if regel(r, items[r["id"]]))),
            "eisen": {k: [voor[k]["waarde"], v["waarde"], v["gehaald"]] for k, v in na.items()
                      if v["waarde"] != voor[k]["waarde"] or v["gehaald"] != voor[k]["gehaald"]}}
    return uit


def main() -> None:  # pragma: no cover - CLI
    if sys.argv[1:] == ["lek"]:
        lek()
        return
    if sys.argv[1:] == ["koppen"]:
        koppen()
        return
    staat = staatsmedia.lees()
    alles = {}
    for pad in sys.argv[1:] or PLANNEN:
        plan = mt.lees_plan(pad)
        alles[plan["taak"]] = uit = narekenen(plan, staat)
        print(f"\n== {plan['taak']}  niet bevestigd: {uit['niet bevestigd']}  kopjesbalk: {uit['kopjesbalk']}")
        for naam, r in uit["regels"].items():
            eisen = "; ".join(f"{k.split('.')[0]}: {a} → {b}{'' if g else ' (niet gehaald)'}"
                              for k, (a, b, g) in r["eisen"].items())
            print(f"  {naam:30} weg {r['weg']} | {eisen}")
    doel = Path("data/meting/narekening.json")
    doel.write_text(json.dumps(alles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{doel}")


if __name__ == "__main__":
    main()
