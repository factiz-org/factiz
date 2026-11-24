"""Kruiscontrole per detail, een voormeting (PLAN #32.3d).

Een goede bron alleen maakt een groen niet juister (BENCHMARK §173): bij een
vervalst echt artikel bevestigen de goede bronnen het verhaal, maar niet het
veranderde detail. Deze voormeting telt per groen hoeveel onafhankelijke goede
bronnen het antwoord citeert, en of de getallen uit het bericht in die passages
staan of erdoor worden tegengesproken. Alleen de geciteerde passages, geen
taalmodel en geen netwerk; verkennend, want de onterechte groenen van de toets
zijn al bekeken.

    python -m doublecheck.kruiscontrole voormeting
"""

from __future__ import annotations

import json
import re

from doublecheck import bronnen as br
from doublecheck import bronnenlijst as bl
from doublecheck import relation

UITSLAG = bl.MAP / "kruiscontrole-voormeting.json"
REGELS = ("R-a", "R-b", "R-c", "R-d", "R-e")
GELIJK = 0.8          # passages met minstens 80% dezelfde woorden tellen als één bron
TEGENGEHOUDEN, KWIJT = 0.5, 0.2
# Bij het bouwen vastgelegd, vóór de uitslag: een getal vóór een lidwoord of voorzetsel ("in 2024 the vote")
# zegt niets over de grootheid; zo'n woord telt niet voor een tegenspraak.
GEEN_GROOTHEID = frozenset({
    "the", "and", "for", "but", "was", "are", "has", "had", "not", "its", "per", "that", "this", "with", "from",
    "van", "het", "een", "der", "die", "das", "und", "les", "des", "los", "las", "met", "aan", "von", "dat"})
_ACHTERVOEGSEL = frozenset({"co", "com", "org", "net", "gov", "ac", "edu", "gob", "or", "ne", "go", "nic", "gv"})


def eigenaar(site: str) -> str:
    """De naam zonder het achtervoegsel: bbc.com en bbc.co.uk zijn allebei bbc."""
    delen = site.split(".")
    if len(delen) >= 3 and len(delen[-1]) == 2 and delen[-2] in _ACHTERVOEGSEL:
        return delen[-3]
    return delen[-2] if len(delen) >= 2 else site


def _woorden(tekst: str) -> set[str]:
    return set(re.findall(r"\w+", tekst.casefold()))


def _bijna_gelijk(a: str, b: str) -> bool:
    wa, wb = _woorden(a), _woorden(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= GELIJK


def groepen(bronnen: list[dict], sites: dict[str, list]) -> list[dict]:
    """De onafhankelijke bronnen van een antwoord: één groep per eigenaar, en groepen met een bijna gelijke passage
    (hetzelfde persbureaubericht op twee sites) samen. Een groep is goed als er een website met band goed in zit."""
    per: dict[str, dict] = {}
    for b in bronnen:
        if b.get("soort") not in ("web", "beeld") or not b.get("url"):
            continue
        oordeel = br.beoordeel(b["url"], sites)
        g = per.setdefault(eigenaar(oordeel["site"]), {"goed": False, "passages": []})
        g["goed"] = g["goed"] or oordeel["band"] == "goed"
        if b.get("citaat"):
            g["passages"].append(b["citaat"])
    uit: list[dict] = []
    for g in per.values():
        doel = next((u for u in uit if any(_bijna_gelijk(p, q) for p in g["passages"] for q in u["passages"])), None)
        if doel is None:
            uit.append({"goed": g["goed"], "passages": list(g["passages"])})
        else:
            doel["goed"] = doel["goed"] or g["goed"]
            doel["passages"] += g["passages"]
    return uit


def _contexten(tekst: str) -> dict[str, str]:
    return {w: n for w, n in relation.extract_number_contexts(tekst).items() if len(w) >= 3 and w not in GEEN_GROOTHEID}


def getallen(bericht: str, passages: list[str]) -> dict[str, set[str]]:
    """Welke getallen uit het bericht in de passages staan, en welke een passage bij hetzelfde woord tegenspreekt
    ("12 March" tegen "21 March")."""
    in_bericht = set(relation.extract_numbers(bericht))
    gevonden = in_bericht & set().union(*(relation.extract_numbers(p) for p in passages))
    eigen = _contexten(bericht)
    tegen = {n for p in passages for w, m in _contexten(p).items() if w in eigen and m != (n := eigen[w])}
    return {"in bericht": in_bericht, "gevonden": gevonden, "tegengesproken": tegen & in_bericht}


def regels(rij: dict) -> dict[str, bool]:
    """De vijf regels van PLAN #32.3d voor één groen; een groen die een regel niet haalt, verliest zijn kleur."""
    goed = [g for g in rij["groepen"] if g["goed"]]
    uit = getallen(rij["tekst"], [p for g in goed for p in g["passages"]])
    per_getal = {n: [g for g in rij["groepen"] if any(n in relation.extract_numbers(p) for p in g["passages"])]
                 for n in uit["in bericht"]}
    r = {"R-a": len(goed) >= 2, "R-b": uit["gevonden"] == uit["in bericht"], "R-c": not uit["tegengesproken"],
         "R-e": all(len(gs) >= 2 and any(g["goed"] for g in gs) for gs in per_getal.values())}
    return {"R-a": r["R-a"], "R-b": r["R-b"], "R-c": r["R-c"], "R-d": r["R-a"] and r["R-b"], "R-e": r["R-e"]}


def _tel(rijen: list[dict], regel: str) -> dict:
    fout = [r for r in rijen if r["label"] != "waar"]
    juist = [r for r in rijen if r["label"] == "waar"]
    return {"onterecht groen": len(fout), "tegengehouden": sum(not regels(r)[regel] for r in fout),
            "juist groen": len(juist), "kleur kwijt": sum(not regels(r)[regel] for r in juist)}


def _aandeel(t: dict, teller: str, noemer: str) -> float:
    return t[teller] / t[noemer] if t[noemer] else 0.0


def telling(ontwikkel: list[dict], toets: list[dict]) -> dict:
    """Per regel: hoeveel onterechte groenen hij tegenhoudt en hoeveel juiste groenen hun kleur verliezen, per set
    en samen; veelbelovend bij de helft tegengehouden, hoogstens een vijfde kwijt, en in beide sets dezelfde
    richting."""
    uit: dict = {"regels": {}}
    for regel in REGELS:
        per = {"ontwikkel": _tel(ontwikkel, regel), "toets": _tel(toets, regel)}
        samen = {k: per["ontwikkel"][k] + per["toets"][k] for k in per["toets"]}
        richting = all(_aandeel(t, "tegengehouden", "onterecht groen") > _aandeel(t, "kleur kwijt", "juist groen")
                       for t in per.values())
        uit["regels"][regel] = {**per, "samen": samen, "veelbelovend":
                                _aandeel(samen, "tegengehouden", "onterecht groen") >= TEGENGEHOUDEN
                                and _aandeel(samen, "kleur kwijt", "juist groen") <= KWIJT and richting}
    return uit


def _beschrijf(rijen: list[dict]) -> dict:
    """Ter informatie: het aantal onafhankelijke goede bronnen en het deel gevonden getallen, juist tegen onterecht."""
    uit = {}
    for naam, deel in (("juist", [r for r in rijen if r["label"] == "waar"]),
                       ("onterecht", [r for r in rijen if r["label"] != "waar"])):
        goed = [sum(g["goed"] for g in r["groepen"]) for r in deel]
        met = [getallen(r["tekst"], [p for g in r["groepen"] if g["goed"] for p in g["passages"]]) for r in deel]
        met = [m for m in met if m["in bericht"]]
        uit[naam] = {"n": len(deel), "goede bronnen": {str(k): sum(min(x, 3) == k for x in goed) for k in range(4)},
                     "met getallen": len(met),
                     "getallen gevonden": round(sum(len(m["gevonden"]) for m in met)
                                                / max(1, sum(len(m["in bericht"]) for m in met)), 3)}
    return uit


def _namen(tekst: str) -> set[str]:
    """Ter informatie: woorden van minstens drie letters met een hoofdletter, niet aan het begin van een zin."""
    namen = set()
    for zin in re.split(r"(?<=[.!?])\s+|\n", tekst):
        for woord in re.findall(r"\w+", zin)[1:]:
            if len(woord) >= 3 and woord[0].isupper():
                namen.add(woord.casefold())
    return namen


def main() -> None:  # pragma: no cover - CLI, op de antwoorden van de rondes
    import argparse

    parser = argparse.ArgumentParser(description="Kruiscontrole per detail, een voormeting (PLAN #32.3d)")
    parser.add_argument("stap", choices=("voormeting",))
    parser.parse_args()
    lijst = json.loads(br.BESTAND.read_text(encoding="utf-8"))
    if not bl.vastgelegd(lijst) or lijst["_meta"]["versie"] != br.VERSIE:
        raise SystemExit("de lijst van #32.3c ligt niet vast")
    ontwikkel, toets = bl.berichten()

    def groenen(set_: list[dict]) -> list[dict]:
        return [{**r, "groepen": groepen(r["bronnen"], lijst["sites"])} for r in set_
                if r["oordeel"] == "klopt" and bl.meter.laag_van_antwoord(r["bronnen"]) == "web"]

    o, t = groenen(ontwikkel), groenen(toets)
    uit = {"lijst": lijst["_meta"]["vingerafdruk"], **telling(o, t),
           "ter informatie": {"samen": _beschrijf(o + t),
                              "vervalste artikelen": _beschrijf([r for r in t if r["ronde"] == "gebruikerstoets"
                                                                 and r["deel"] == "B"]),
                              "namen gevonden": {naam: round(sum(len(_namen(r["tekst"]) & _woorden(" ".join(
                                  p for g in r["groepen"] if g["goed"] for p in g["passages"]))) for r in d)
                                  / max(1, sum(len(_namen(r["tekst"])) for r in d)), 3)
                                  for naam, d in (("juist", [r for r in o + t if r["label"] == "waar"]),
                                                  ("onterecht", [r for r in o + t if r["label"] != "waar"]))}},
           "vervalste artikelen per regel": {regel: _tel([r for r in t if r["ronde"] == "gebruikerstoets"
                                                          and r["deel"] == "B"], regel) for regel in REGELS}}
    UITSLAG.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
