"""Betrouwbare bronnen: een soort per website, met de herkomst (PLAN #32.3b).

Nooit op eigen gezag, net als de feitenbasis (B34). Elke soort komt uit een
beoordeling van buiten of uit een vaste regel op de naam van het domein:

- A, betrouwbaar: Lin e.a. (PNAS Nexus 2023) 0,70 of hoger, *generally reliable*
  bij Wikipedia, een actieve factchecker van het IFCN, of een lid van de EBU uit
  een land met 70 of meer in de index van RSF;
- O, officieel of wetenschappelijk: overheid, internationale organisatie,
  universiteit, naar de naam van het domein;
- U, geschreven door gebruikers of een taalmodel: een vaste lijst;
- C, onbetrouwbaar: Lin e.a. 0,40 of lager, of *generally unreliable* of
  *deprecated* bij Wikipedia;
- B, de rest: niet beoordeeld.

Zeggen twee bronnen iets anders, dan telt het strengste. De autoriteit van
links telt hier niet mee (geen sleutel voor Open PageRank, PO 2026-10-28).

    python -m doublecheck.bronnenlijst bouwen|tellen
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from doublecheck import meter

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "bronnen"
EXTERN = MAP / "extern"
BESTAND = MAP / "bronnen.json"
UITSLAG = MAP / "uitslag.json"

STRENG = "CUBOA"  # strengste eerst: zeggen twee bronnen iets anders, dan telt het strengste
BESTE = "AOBUC"   # per antwoord de beste soort onder de websites die het noemt
LIN_A, LIN_C = 0.70, 0.40
RSF_GRENS = 70.0  # de bovenste twee klassen van RSF: goed (85 en meer) en redelijk (70 tot 85)
DOOR_GEBRUIKERS = frozenset({
    "wikipedia.org", "wikiwand.com", "wiki2.org", "grokipedia.com", "x.com", "twitter.com", "facebook.com",
    "instagram.com", "tiktok.com", "youtube.com", "reddit.com", "quora.com", "medium.com", "substack.com",
    "blogspot.com", "wordpress.com", "linkedin.com", "t.me"})
WIKI_A, WIKI_C = {"gr"}, {"gu", "d", "b"}
DEKKING, MIN_GROEN_A, P_GRENS = 0.5, 30, 0.05


class Weigering(RuntimeError):
    pass


def host(url: str) -> str:
    """De naam van de website, klein, zonder poort en zonder www."""
    naam = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower().rstrip(".")
    return naam[4:] if naam.startswith("www.") else naam


def officieel(naam: str) -> bool:
    """Overheid (.gov, .gov.xx, .gob.xx, .gouv.fr, .overheid.nl), .int, .edu en .ac.xx."""
    delen = naam.split(".")
    if delen[-1] in ("gov", "int", "edu"):
        return True
    if len(delen) >= 2 and delen[-2] in ("gov", "gob", "ac") and len(delen[-1]) == 2:
        return True
    return naam.endswith((".gouv.fr", ".overheid.nl")) or naam in ("gouv.fr", "overheid.nl")


def soort(url: str, sites: dict[str, list]) -> str:
    """De soort van een website: de oordelen op het langste deel van de naam dat in de lijst staat, plus de regel
    voor officiële domeinen; het strengste telt; zonder oordeel B."""
    naam = host(url)
    delen = naam.split(".")
    oordelen = []
    for i in range(len(delen) - 1):
        if (deel := ".".join(delen[i:])) in sites:
            oordelen = [s for s, _ in sites[deel]]
            break
    if naam and officieel(naam):
        oordelen.append("O")
    return min(oordelen, key=STRENG.index) if oordelen else "B"


def beste(urls: list[str], sites: dict[str, list]) -> str | None:
    """De beste soort onder de websites die een antwoord noemt."""
    soorten = [soort(u, sites) for u in urls]
    return min(soorten, key=BESTE.index) if soorten else None


# --- de oordelen van buiten ----------------------------------------------------------------------

def lin_cijfers(tekst: str) -> dict[str, float]:
    """Het cijfer van Lin e.a. (`domain_pc1.csv`) per website; een oordeel over een deel van een site
    (facebook.com/iemand) telt niet, net als bij Wikipedia."""
    return {host(r["domain"]): float(r["pc1"]) for r in csv.DictReader(io.StringIO(tekst))
            if "/" not in r["domain"].rstrip("/")}


def lin_oordelen(tekst: str, a: float = LIN_A, c: float = LIN_C) -> dict[str, tuple[str, str]]:
    """De samengevoegde beoordeling van Lin e.a.: A vanaf `a`, C tot en met `c`."""
    return {naam: ("A" if pc1 >= a else "C", f"Lin e.a. {pc1:.2f}") for naam, pc1 in lin_cijfers(tekst).items()
            if pc1 >= a or pc1 <= c}


def wikipedia_oordelen(wikitekst: str) -> list[tuple[str, str]]:
    """Per rij van *Reliable sources/Perennial sources*: A alleen als elke status *generally reliable* is, C bij
    *generally unreliable*, *deprecated* of *blacklisted*; een oordeel over een deel van een site telt niet."""
    uit = []
    for rij in re.split(r"\n\|-", wikitekst):
        statussen = set(re.findall(r"\{\{WP:RSPSTATUS\|([^}|]+)", rij))
        oordeel = "C" if statussen & WIKI_C else "A" if statussen and statussen <= WIKI_A else None
        if not oordeel:
            continue
        for gebruik in re.findall(r"\{\{WP:RSPUSES\|([^}]+)\}\}", rij):
            for domein in gebruik.split("|"):
                domein = domein.strip()
                if domein and "=" not in domein and "/" not in domein.rstrip("/"):
                    uit.append((host(domein), oordeel))
    return uit


def rsf_scores(tekst: str) -> dict[str, float]:
    """De score per land (ISO3) uit de index van RSF."""
    rijen = csv.reader(io.StringIO(tekst), delimiter=";")
    kop = next(rijen)
    kolom = next(i for i, k in enumerate(kop) if k.startswith("Score"))
    return {r[0]: float(r[kolom].replace(",", ".")) for r in rijen if r and r[kolom]}


def vingerafdruk(sites: dict[str, list]) -> str:
    return hashlib.sha256(json.dumps(sites, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def bouw(lin: str, wikipedia: list[str], ifcn: list[str], ebu: list[tuple[str, str]], rsf: dict[str, float],
         datum: str, lin_a: float = LIN_A, lin_c: float = LIN_C) -> dict:
    """De lijst: per website de soorten met hun herkomst, en de vingerafdruk waarmee ze vastligt."""
    sites: dict[str, set[tuple[str, str]]] = {}

    def zet(naam: str, s: str, bron: str) -> None:
        if naam:
            sites.setdefault(naam, set()).add((s, bron))

    for naam, (s, bron) in lin_oordelen(lin, lin_a, lin_c).items():
        zet(naam, s, bron)
    for tekst in wikipedia:
        for naam, s in wikipedia_oordelen(tekst):
            zet(naam, s, "Wikipedia")
    for url in ifcn:
        zet(host(url), "A", "IFCN")
    for naam, land in ebu:
        if rsf.get(land, 0.0) >= RSF_GRENS:
            zet(host(naam), "A", f"EBU, RSF {land} {rsf[land]:.1f}")
    for naam in DOOR_GEBRUIKERS:
        zet(naam, "U", "vaste lijst")
    vast = {naam: sorted([list(o) for o in oordelen]) for naam, oordelen in sorted(sites.items())}
    return {"_meta": {"datum": datum, "grenzen": {"lin_a": lin_a, "lin_c": lin_c, "rsf": RSF_GRENS},
                      "plan": "PLAN #32.3b", "vingerafdruk": vingerafdruk(vast)}, "sites": vast}


def vastgelegd(lijst: dict) -> bool:
    return lijst.get("_meta", {}).get("vingerafdruk") == vingerafdruk(lijst.get("sites", {}))


# --- de meting -----------------------------------------------------------------------------------

def _klasse(rijen: list[dict]) -> dict:
    n, waar = len(rijen), sum(r["label"] == "waar" for r in rijen)
    oordeel = rijen[0]["oordeel"] if rijen else ""
    return {"n": n, "waar": waar, "aandeel waar": round(waar / n, 4) if n else None,
            "interval": [round(x, 4) for x in meter.wilson(waar, n)],
            "stand": meter.stand(waar, n, "web", oordeel), "stand zonder grens": meter.stand(waar, n, "redactie", oordeel)}


def _vraag(rijen: list[dict]) -> dict:
    """Bij *klopt*: minder onwaar als de beste bron A is dan als die B, U of C is? Fisher exact, tweezijdig."""
    groen = [r for r in rijen if r["oordeel"] == "klopt"]
    a = [r for r in groen if r["soort"] == "A"]
    rest = [r for r in groen if r["soort"] in ("B", "U", "C")]
    a_fout, rest_fout = sum(r["label"] != "waar" for r in a), sum(r["label"] != "waar" for r in rest)
    from doublecheck.modelpoort import fisher

    richting = bool(a and rest) and a_fout / len(a) < rest_fout / len(rest)
    return {"A": [a_fout, len(a)], "B, U of C": [rest_fout, len(rest)], "richting": richting,
            "p": fisher(a_fout, len(a) - a_fout, rest_fout, len(rest) - rest_fout) if a and rest else 1.0}


def telling(ontwikkel: list[dict], toets: list[dict], lijst: dict) -> dict:
    """Per oordeel en soort het aandeel ware berichten, de dekking, de vraag en de drie eisen van PLAN #32.3b. Elke
    rij: oordeel, soort (de beste), label, dekking (noemt het antwoord een website van soort A of C)."""
    if not vastgelegd(lijst):
        raise Weigering("de lijst ligt niet vast: de vingerafdruk ontbreekt of klopt niet meer")
    uit: dict = {"vingerafdruk": lijst["_meta"]["vingerafdruk"]}
    for naam, rijen in (("ontwikkel", ontwikkel), ("toets", toets)):
        per: dict = {}
        for r in rijen:
            per.setdefault(r["oordeel"], {}).setdefault(r["soort"], []).append(r)
        uit[naam] = {o: {s: _klasse(rs) for s, rs in sorted(d.items(), key=lambda x: BESTE.index(x[0]))}
                     for o, d in sorted(per.items())}
        uit[naam]["dekking"] = round(sum(r["dekking"] for r in rijen) / len(rijen), 4) if rijen else 0.0
    uit["vraag"] = {"ontwikkel": _vraag(ontwikkel), "toets": _vraag(toets)}
    groen_a = uit["toets"].get("klopt", {}).get("A", {}).get("n", 0)
    uit["eisen"] = {
        "dekking minstens de helft": uit["toets"]["dekking"] >= DEKKING,
        "minder onwaar bij groen met een A-bron": uit["vraag"]["toets"]["richting"]
        and uit["vraag"]["toets"]["p"] < P_GRENS and uit["vraag"]["ontwikkel"]["richting"],
        "minstens 30 keer groen met een A-bron": groen_a >= MIN_GROEN_A}
    return uit


# --- de bestanden en de CLI ----------------------------------------------------------------------

def _webadressen(bronnen: list[dict]) -> list[str]:
    return [b["url"] for b in bronnen if b.get("soort") in ("web", "beeld") and b.get("url")]


def _rij(oordeel: str, bronnen: list[dict], label: str, sites: dict) -> dict | None:
    """Alleen antwoorden met een webbron en zonder check van een redactie (de laag *web*)."""
    if meter.laag_van_antwoord(bronnen) != "web":
        return None
    urls = _webadressen(bronnen)
    return {"oordeel": oordeel, "soort": beste(urls, sites), "label": label,
            "dekking": any(soort(u, sites) in ("A", "C") for u in urls)}


def berichten() -> tuple[list[dict], list[dict]]:  # pragma: no cover - op de bestanden van de rondes
    """De ontwikkelset (ronde 4, 5 en 7 van #31.8, de ijking van de schaal) en de toets (de andere rondes met vraag
    v4, één keer per tekst en zonder teksten uit de ontwikkelset): per antwoord het oordeel, de bronnen, het label,
    de tekst van het bericht, de ronde en het deel."""
    from doublecheck import betatoets as bt
    from doublecheck import verificatie as v
    from doublecheck import vloer as vl

    ontwikkel, ijk = [], set()
    for ronde, omstandigheden in meter.IJKRONDES:
        stukken = {s["id"]: s for s in v.gekozen_stukken(ronde)}
        ijk |= {vl._gewoon(s["tekst"]) for s in stukken.values() if s.get("tekst")}
        for (om, id_), a in v.antwoorden(ronde, "sonnet").items():
            s = stukken.get(id_)
            if om in omstandigheden and s and s["label"] in ("waar", "onwaar"):
                ontwikkel.append({"oordeel": a["oordeel"], "bronnen": a["bronnen"], "label": s["label"],
                                  "tekst": s.get("tekst") or "", "ronde": f"verificatie-{ronde}", "deel": ""})

    def data(naam: str) -> tuple[list[dict], list[dict]]:
        return bt._jsonl(WORTEL / "data" / naam / "set.jsonl"), bt._jsonl(WORTEL / "data" / naam / "antwoorden.jsonl")

    rondes = []
    for naam in ("route", "fundament", "betatoets", "herstel"):
        stukken, antw = data(naam)
        rondes.append((naam, stukken, vl._laatste(antw), lambda s: s.get("label")))
    stukken, antw = data("gebruikerstoets")
    rondes.append(("gebruikerstoets", stukken,
                   vl._laatste([r for r in antw if r.get("soort") in ("machine", "herkansing")]),
                   lambda s: (s.get("verwacht") or {}).get("inhoud")))
    stukken, antw = data("echtevorm")
    rondes.append(("echtevorm", stukken, vl._laatste(antw), lambda s: "onwaar"))
    stukken, antw = data("tegenspeler")
    rondes.append(("tegenspeler", stukken, vl._laatste(antw), lambda s: "satire" if s["deel"] == "S" else "onwaar"))
    mp = bt._jsonl(WORTEL / "data" / "modelpoort" / "set.jsonl") + bt._jsonl(WORTEL / "data" / "modelpoort" / "r.jsonl")
    rondes.append(("modelpoort", mp, vl._laatste(bt._jsonl(WORTEL / "data" / "modelpoort" / "antwoorden.jsonl"),
                                                 "sonnet"), lambda s: s.get("label")))
    toets, gezien = [], set()
    for naam, stukken, per, label_van in rondes:
        for s in stukken:
            a, label = per.get(s["id"]), label_van(s)
            if a is None or not s.get("tekst") or label not in ("waar", "onwaar"):
                continue
            sleutel = vl._gewoon(s["tekst"])
            if sleutel in gezien or sleutel in ijk:
                continue
            gezien.add(sleutel)
            toets.append({"oordeel": a["oordeel"], "bronnen": a.get("bronnen") or [], "label": label,
                          "tekst": s["tekst"], "ronde": naam, "deel": str(s.get("deel") or s.get("set") or "")})
    return ontwikkel, toets


def antwoorden() -> tuple[list[tuple], list[tuple]]:  # pragma: no cover - op de bestanden van de rondes
    """Zoals `berichten`, als (oordeel, bronnen, label): de vorm van de meting van #32.3b."""
    ontwikkel, toets = berichten()
    return ([(r["oordeel"], r["bronnen"], r["label"]) for r in ontwikkel],
            [(r["oordeel"], r["bronnen"], r["label"]) for r in toets])


def invoer() -> dict:  # pragma: no cover - op de gedownloade bestanden
    """De gedownloade en gelezen lijsten uit `data/bronnen/extern/`, in de vorm die `bouw` verwacht."""
    return {
        "lin": (EXTERN / "lin" / "domain_pc1.csv").read_text(encoding="utf-8"),
        "wikipedia": [json.loads(p.read_text(encoding="utf-8"))["parse"]["wikitext"]
                      for p in sorted((EXTERN / "wikipedia").glob("rsp-[0-9].json"))],
        "ifcn": [r["site"] for r in csv.DictReader((EXTERN / "ifcn" / "actief.tsv").open(encoding="utf-8"),
                                                   delimiter="\t") if r["site"]],
        "ebu": [tuple(regel.rstrip("\n").split("\t")) for regel in (EXTERN / "ebu" / "leden.tsv").open(encoding="utf-8")
                if regel.strip() and not regel.startswith("#")],
        "rsf": rsf_scores((EXTERN / "rsf" / "2026.csv").read_text(encoding="cp1252"))}


def _bouw_uit_extern(datum: str, lin_a: float = LIN_A) -> dict:  # pragma: no cover - op de gedownloade bestanden
    return bouw(**invoer(), datum=datum, lin_a=lin_a)


def main() -> None:  # pragma: no cover - CLI
    import argparse
    from collections import Counter
    from datetime import date

    parser = argparse.ArgumentParser(description="Betrouwbare bronnen (PLAN #32.3b)")
    parser.add_argument("stap", choices=("bouwen", "tellen"))
    args = parser.parse_args()
    if args.stap == "bouwen":
        if BESTAND.exists():
            raise SystemExit(f"{BESTAND} ligt al vast; na de uitslag verandert de lijst niet (PLAN #32.3b)")
        lijst = _bouw_uit_extern(date.today().isoformat())
        BESTAND.write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
        tel = Counter(min((s for s, _ in o), key=STRENG.index) for o in lijst["sites"].values())
        print(f"{len(lijst['sites'])} websites; per soort {dict(tel)}; vingerafdruk {lijst['_meta']['vingerafdruk'][:12]}")
        return
    lijst = json.loads(BESTAND.read_text(encoding="utf-8"))
    ontwikkel, toets = antwoorden()

    def rijen(set_: list[tuple], sites: dict) -> list[dict]:
        return [r for o, b, label in set_ if (r := _rij(o, b, label, sites))]

    uit = telling(rijen(ontwikkel, lijst["sites"]), rijen(toets, lijst["sites"]), lijst)
    uit["ter informatie"] = {}
    for grens in (0.60, 0.80):
        ander = _bouw_uit_extern(lijst["_meta"]["datum"], lin_a=grens)
        t = telling(rijen(ontwikkel, ander["sites"]), rijen(toets, ander["sites"]), ander)
        uit["ter informatie"][f"Lin A vanaf {grens:.2f}"] = {"vraag": t["vraag"], "eisen": t["eisen"],
                                                             "groen met A": t["toets"].get("klopt", {}).get("A")}
    UITSLAG.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
