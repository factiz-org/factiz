"""De herstelronde (ronde 5 van de koers, B45; PLAN #31.15).

Twee regels ná het oordeel van Sonnet, die zelf niet verandert (vraag v4, dus de
ijking van de schaal blijft gelden). Een korte vormvraag (`berichtcontrole.VORMEN`)
zegt of het bericht de bewering zelf doet en of die over een beeld gaat:
- regel 1: een bericht over een bewering van een ander krijgt geen kleur;
- regel 2: een bewering over wat een beeld toont is zonder het beeld nooit groen.
200 nieuwe Engelse berichten, vooraf vastgelegd:
- W5, 100 betrouwbare nieuwsartikelen (Sheffield, toetshelft), de helft als chatbericht;
- B5, 50 onware beweringen over een beeld (eerst de verse), de helft als chatbericht;
  zonder checks uit de database en met de factchecksites geblokkeerd (§150, b);
- N5, 50 bekend nepnieuws als tekst, zoals in het product.
Omdat de regels ná het oordeel komen, geeft één meting het cijfer met én zonder.

Zoals de toets voor de beta (`betatoets`): dezelfde functies als
`try.factiz.org/check`, de vragen via de Batch API (openbare berichten, B43).
Vooraf de ontwikkelcontrole van de vormvraag op berichten uit ronde 4, live.
De vormvraag (`vorm-v2`) krijgt de bewering die de machine beoordeelde, dus komt
ze ná de machine en de herkansing, en alleen bij een rode of groene uitslag: de
regels halen alleen kleur weg.

    python -m doublecheck.herstel ontwikkel [--vraag vorm-v2]
    python -m doublecheck.hittewacht -- python -m doublecheck.herstel set
    python -m doublecheck.herstel indienen [--proef 3]|herkansing|vorm|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as t
from doublecheck import verificatie as v

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "herstel"
LABELS = WORTEL / "docs" / "steekproeven" / "31.15-herstel.json"
BUDGET = 6.0  # PO 2026-10-27: "grens $6"
ZAAD = 3115
VORM = "vorm-v2"  # gekozen in de ontwikkelcontrole, vóór de keuze van de 200 (PLAN #31.15)
DELEN = ("W5", "B5", "N5")
NR_SCHUIF = 10_000  # andere verzonnen namen en nummers in de chatberichten dan in ronde 4
MAX_ROOD_W5 = 1
MAX_GROEN_B5 = 1
MAX_FOUT_N5 = 2
BEELDWOORD = re.compile(r"\b(video|photo|image|visuals?|footage|clip|picture|pic)s?\b", re.I)
# De omschrijving door een factchecker, geen bericht (PLAN #31.15, uitwerking): 26 van de 435 in de pool voor N5.
OMSCHRIJVING = re.compile(r"^\s*(claim\s*:|says\b|posts?\b|social media|a (viral )?(post|poster|video|photo|clipping|"
                          r"message|tweet|image|claim)\b.*\bclaim|.*\bclaim(s|ing|ed)? (that|to)\b)", re.I)
# Per vraag via de Batch API, uit ronde 4 (§158).
SCHATTING = {"W5": 0.027, "B5": 0.034, "N5": 0.004, "feit": 0.0015, "vorm": 0.0013, "herkansing": 0.035}
VELDEN = ("n", "set fout", "vormvraag gesteld", "vorm: zelf", "vorm: over een bewering", "beeld", "vormvraag onleesbaar",
          "kleur weg door regel 1", "groen weg door regel 2")
VELDEN_WAAR = ("onterecht rood zonder de regels", "onterecht rood met de regels")
VELDEN_ONWAAR = ("rood met bewijs zonder de regels", "rood met bewijs met de regels",
                 "bewezen via een factcheck op het web", "rood zonder bewijs", "groen zonder de regels",
                 "groen met de regels")
VELDEN_N5 = ("over een bewering, doet zelf", "over een bewering, bericht erover", "fout voor eis 3")


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


def omschrijving(tekst: str) -> bool:
    return bool(OMSCHRIJVING.search(tekst))


def kies(pools: dict[str, list[dict]]) -> list[dict]:
    """De 200 berichten van PLAN #31.15, met deel en vorm (tekst of chat)."""
    def deel(rijen: list[dict], naam: str, label: str, bron: str, vormen: list[str]) -> list[dict]:
        return [{**r, "deel": naam, "label": label, "bron": bron, "vorm": vorm} for r, vorm in zip(rijen, vormen)]

    def helften(n: int) -> list[str]:
        return ["tekst"] * (n // 2) + ["chat"] * (n - n // 2)

    vers = [{**r, "beeldpool": "vers"} for r in t._schud(pools["beeld vers"], "beeld vers", ZAAD)[:50]]
    oud = [{**r, "beeldpool": "oud"} for r in t._schud(pools["beeld oud"], "beeld oud", ZAAD)[: 50 - len(vers)]]
    beeld = sorted(vers + oud, key=lambda r: r["id"])
    random.Random(f"{ZAAD}-beeld").shuffle(beeld)
    return (deel(t._schud(pools["artikelen"], "artikelen", ZAAD)[:100], "W5", "waar", "artikel", helften(100))
            + deel(beeld, "B5", "onwaar", "onware check over een beeld", helften(50))
            + deel(t._schud(pools["onwaar oud"], "oud", ZAAD)[:50], "N5", "onwaar", "onware check", ["tekst"] * 50))


# --- tellen ----------------------------------------------------------------------------

def _label(labels: dict, sleutel: tuple | str) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def telling(stukken: list[dict], uitkomsten: dict[str, dict], vormen: dict[str, dict], tabel: dict,
            labels: dict, vormlabels: dict[str, str]) -> dict:
    """Per deel het cijfer zonder en met de regels, en de vier eisen van PLAN #31.15.
    Weigert zolang iets dat telt geen label heeft."""
    from doublecheck.fundament import eis_b45

    uit: dict = {}
    controle = Counter({"door de regels rood of groen": 0, "verkeerde 10": 0})
    for s in stukken:
        u, vorm = uitkomsten.get(s["id"]), vormen.get(s["id"])
        if u is None or vorm is None:
            continue
        o = u["oordeel"]
        zonder = bc.kleur(u["stand"], o)
        na = bc.regels(tabel, o, {"stand": u["stand"], "laag": u["laag"]}, u["feit"], u["bronnen"], vorm)
        met = na["kleur"]
        d = uit.setdefault(s["deel"], Counter({k: 0 for k in VELDEN + (VELDEN_WAAR if s["label"] == "waar" else
                                                                         VELDEN_ONWAAR) + (VELDEN_N5 if s["deel"] == "N5" else ())}))
        d["n"] += 1
        d["vormvraag gesteld"] += vorm.get("gevraagd", True)
        d[f"vorm: {vorm['vorm']}"] += 1
        d["beeld"] += vorm["beeld"]
        d["vormvraag onleesbaar"] += not vorm["gelezen"]
        controle["door de regels rood of groen"] += met not in (zonder, None)
        d["kleur weg door regel 1"] += zonder is not None and "over een bewering" in na["regels"]
        d["groen weg door regel 2"] += zonder == "groen" and "beeld" in na["regels"]
        if u["stand"] == 10:
            controle["verkeerde 10"] += _label(labels, (s["id"], 10, u["feit"])) == "fout"
        if s["label"] == "waar":
            if zonder == "rood":
                label = _label(labels, (s["id"], o))
                d["set fout"] += label == "set fout"
                if label == "vals":
                    d["onterecht rood zonder de regels"] += 1
                    d["onterecht rood met de regels"] += met == "rood"
            continue
        bewijs = None
        if zonder == "rood":
            if t._eigen_bewijs(s, u):
                bewijs = "eigen check"
            elif u["bronnen"]:
                label = _label(labels, (s["id"], o))
                if label in ("bewijst", "bewijst via factcheck"):
                    bewijs = label
                else:
                    d["set fout" if label == "set fout" else "rood zonder bewijs"] += 1
            else:
                d["rood zonder bewijs"] += 1
        if bewijs:
            d["rood met bewijs zonder de regels"] += 1
            d["rood met bewijs met de regels"] += met == "rood"
            d["bewezen via een factcheck op het web"] += met == "rood" and bewijs == "bewijst via factcheck"
        if zonder == "groen":
            label = _label(labels, (s["id"], o))
            d["set fout"] += label == "set fout"
            if label in ("vals", "beeld nodig"):
                d["groen zonder de regels"] += 1
                d["groen met de regels"] += met == "groen"
        if s["deel"] == "N5":
            fout = bool(bewijs) and met != "rood"
            if vorm["vorm"] == "over een bewering":
                label = _label(vormlabels, s["id"])
                d[f"over een bewering, {label}"] += 1
                fout = fout or label == "doet zelf"
            d["fout voor eis 3"] += fout
    for naam in list(uit):
        uit[naam] = dict(uit[naam])
    eisen: dict = {}
    if "W5" in uit:
        w = uit["W5"]
        n = w["n"] - w["set fout"]
        uit["B45"] = {"zonder de regels": eis_b45(w["onterecht rood zonder de regels"], n),
                      "met de regels": eis_b45(w["onterecht rood met de regels"], n), "van": n}
        eisen["1 ware artikelen met de regels hoogstens 1 van de 100 onterecht rood"] = \
            w["onterecht rood met de regels"] <= MAX_ROOD_W5
    if "B5" in uit:
        eisen["2 beweringen over beelden met de regels hoogstens 1 van de 50 groen"] = \
            uit["B5"]["groen met de regels"] <= MAX_GROEN_B5
    if "N5" in uit:
        eisen["3 herkenning blijft: hoogstens 2 van de 50 bekend nepnieuws fout"] = \
            uit["N5"]["fout voor eis 3"] <= MAX_FOUT_N5
    eisen["4 de regels maken nooit iets rood of groen"] = controle["door de regels rood of groen"] == 0
    uit["controle"] = dict(controle)
    uit["eisen"] = eisen
    return uit


# --- de set ------------------------------------------------------------------------------

def pools(config) -> dict[str, list[dict]]:  # pragma: no cover - op de basisset
    from doublecheck import basisset
    from doublecheck.leerstof import taalcode

    ids, sleutels = t._gebruikt()
    ronde4 = t._jsonl(t.UIT / "set.jsonl")
    ids |= {s["id"] for s in ronde4}
    sleutels |= {s["sleutel"] for s in ronde4}
    vrij = [s for s in basisset.lees() if taalcode(s.get("taal")) == "en" and s["id"] not in ids
            and s["sleutel"] not in sleutels]

    def laag(soort: str, naam: str, alleen_toets: bool = True) -> list[dict]:
        return [s for s in vrij if s["soort"] == soort and v.laag_van(s) == naam
                and (not alleen_toets or s["helft"] == "toets")]

    def bericht(s: dict) -> bool:
        return not omschrijving(s["tekst"])

    return {"artikelen": laag("artikel", "betrouwbaar artikel"),
            "beeld vers": [s for s in laag("tekst", "onwaar, vers", False) if BEELDWOORD.search(s["tekst"]) and bericht(s)],
            "beeld oud": [s for s in laag("tekst", "onwaar, oud") if BEELDWOORD.search(s["tekst"]) and bericht(s)],
            "onwaar oud": [s for s in laag("tekst", "onwaar, oud") if not BEELDWOORD.search(s["tekst"]) and bericht(s)]}


def maak_set() -> list[dict]:  # pragma: no cover - met de OCR, het model en de database
    from doublecheck import routemeting as rm
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    uit = []
    for i, s in enumerate(kies(pools(config))):
        tekst, beeld = t.invoer(s, NR_SCHUIF + i)
        begin = time.perf_counter()
        bericht = bc.bericht_uit(tekst, beeld, config.ocr)
        voorbereid = bc.voorbereiden(conn, config, bericht) if bericht.strip() else \
            {"tekst": bericht, "geheugen": [], "kandidaten": []}
        rij = {"id": s["id"], "nr": i, "deel": s["deel"], "vorm": s["vorm"], "label": s["label"], "bron": s["bron"],
               "beeldpool": s.get("beeldpool"),
               "sleutel": s["sleutel"], "zaak": s.get("zaak"), "datum": s.get("datum"), "helft": s.get("helft"),
               "tekst": voorbereid["tekst"], "geheugen": voorbereid["geheugen"], "kandidaten": voorbereid["kandidaten"],
               "eigen": sorted(v.eigen_cluster(conn, s.get("zaak"))), "lokaal": round(time.perf_counter() - begin, 3)}
        if s["vorm"] == "chat":
            rij["lekken"] = rm.lekken(voorbereid["tekst"], rm.nep_pii(t.PII_SCHUIF + NR_SCHUIF + i))
        uit.append(rij)
        print(f"\r{i + 1}", end="", flush=True)
    t._schrijf(UIT / "set.jsonl", uit)
    return uit


# --- de vragen en de antwoorden -----------------------------------------------------------

def machinevraag(s: dict, config, blok: list[str]) -> dict:
    if s["deel"] == "B5":
        return t.machineverzoek_b(s["tekst"], s["datum"], blok, config)
    return bc.machineverzoek(s["tekst"], s["geheugen"], s["datum"], config)


def vraagt_vorm(u: dict) -> bool:
    """Alleen een rode of groene uitslag met een bewering krijgt de vormvraag."""
    return bc.kleur(u["stand"], u["oordeel"]) is not None and bool(u.get("bewering"))


def vormen_van(antwoorden: list[dict], uitkomsten: dict[str, dict]) -> dict[str, dict]:
    """Per bericht het antwoord op de vormvraag; zonder kleur of bewering geen vraag
    en geen regel. Een gevraagde vorm die nog uitstaat, ontbreekt."""
    gevraagd = {r["id"]: {"vorm": r["vorm"], "beeld": r["beeld"], "gelezen": r["gelezen"], "gevraagd": True}
                for r in antwoorden if r["soort"] == "vorm"}
    uit = {}
    for i, u in uitkomsten.items():
        if i in gevraagd:
            uit[i] = gevraagd[i]
        elif not vraagt_vorm(u):
            uit[i] = {"vorm": "zelf", "beeld": False, "gelezen": True, "gevraagd": False}
    return uit


def vormvragen(stukken: list[dict], uitkomsten: dict[str, dict], config, ingediend: set[str]) -> list[dict]:
    """De vormvragen voor de batch: per rode of groene uitslag één, met de bewering."""
    return [{"custom_id": f"v-{t.batch_id(s['id'])}",
             "params": bc.vormverzoek(s["tekst"], VORM, config, uitkomsten[s["id"]]["bewering"])}
            for s in stukken if s["id"] in uitkomsten and vraagt_vorm(uitkomsten[s["id"]])
            and f"v-{t.batch_id(s['id'])}" not in ingediend]


def _waarom(tekst: str) -> str | None:
    try:
        d = json.loads(tekst)
    except json.JSONDecodeError:
        return None
    return d.get("waarom") if isinstance(d, dict) else None


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in t._jsonl(UIT / "batches.jsonl")) \
        + sum(r.get("kosten", 0) for r in t._jsonl(UIT / "ontwikkel.jsonl"))


def lees_labels() -> tuple[dict, dict[str, str]]:
    if not LABELS.exists():
        return {}, {}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {((r["id"], r["oordeel"]) if r["oordeel"] != 10 else (r["id"], 10, r.get("feit"))): r["label"]
              for r in d.get("oordelen", [])}
    return labels, {r["id"]: r["label"] for r in d.get("vorm", [])}


def _proefkeuze(stukken: list[dict], n: int) -> list[dict]:
    uit = []
    for deel in DELEN:
        per_vorm: dict[str, list[dict]] = {}
        for s in stukken:
            if s["deel"] == deel:
                per_vorm.setdefault(s["vorm"], []).append(s)
        rijen, k = list(per_vorm.values()), 0
        while len([s for s in uit if s["deel"] == deel]) < n and any(rijen):
            if rijen[k % len(rijen)]:
                uit.append(rijen[k % len(rijen)].pop(0))
            k += 1
    return uit


# --- de ontwikkelcontrole ----------------------------------------------------------------

def ontwikkelset() -> list[dict]:  # pragma: no cover - op ronde 4
    """De 17 fouten van ronde 4 en 40 andere berichten daaruit (PLAN #31.15, uitwerking)."""
    stukken = t._jsonl(t.UIT / "set.jsonl")
    uitkomsten = {r["id"]: r for r in t._jsonl(t.UIT / "antwoorden.jsonl") if r["soort"] == "machine"}
    labels, _ = t.lees_labels()
    fouten = {sleutel[0]: label for sleutel, label in labels.items() if label in ("vals", "beeld nodig")}
    rng = random.Random(f"{ZAAD}-ontwikkel")
    bron = re.compile(r"\b(says?|said|according to|reports?|reported|claims?|alleg\w*)\b", re.I)

    def neem(groep: str, rijen: list[dict], n: int) -> list[dict]:
        rijen = sorted(rijen, key=lambda s: s["id"])
        return [{**s, "groep": groep} for s in rng.sample(rijen, min(n, len(rijen)))]

    tekst = [s for s in stukken if s["vorm"] in ("tekst", "chat") and s["id"] not in fouten]
    uit = [{**s, "groep": "fout: rood, waar" if s["label"] == "waar" else f"fout: groen, {fouten[s['id']]}"}
           for s in stukken if s["id"] in fouten]
    uit += neem("nepnieuws met een bron in de zin", [s for s in tekst if s["label"] == "onwaar" and bron.search(s["tekst"])], 20)
    uit += neem("waar artikel, niet rood", [s for s in tekst if s["bron"] == "artikel" and s["id"] in uitkomsten
                                            and uitkomsten[s["id"]]["oordeel"] != "klopt niet"], 10)
    uit += neem("ware check", [s for s in tekst if s["bron"] == "ware check"], 10)
    return uit


def ontwikkel(client, config, versie: str) -> None:  # pragma: no cover - live, met het model
    from concurrent.futures import ThreadPoolExecutor

    set_ = ontwikkelset()
    if al_uitgegeven() + len(set_) * 0.003 > BUDGET:
        raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus de ontwikkelcontrole is meer dan ${BUDGET:.2f}")

    stukken = t._jsonl(t.UIT / "set.jsonl")
    beweringen = {i: u["bewering"] for i, u in
                  t.uitkomsten_van(stukken, t._jsonl(t.UIT / "antwoorden.jsonl"), bc.ijktabel(config)).items()}

    def vraag(s: dict) -> dict:
        begin = time.perf_counter()
        msg = client.messages.create(**bc.vormverzoek(s["tekst"], versie, config, beweringen.get(s["id"])))
        tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
        return {"versie": versie, "id": s["id"], "groep": s["groep"], **bc.lees_vorm(tekst), "waarom": _waarom(tekst),
                "bewering": beweringen.get(s["id"]), "tijd": round(time.perf_counter() - begin, 2),
                "kosten": round(bc.kosten(bc.gebruik_uit(msg)), 5)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rijen = list(pool.map(vraag, set_))
    with (UIT / "ontwikkel.jsonl").open("a", encoding="utf-8") as fh:
        for r in rijen:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    per_id = {s["id"]: s for s in set_}
    for r in sorted(rijen, key=lambda r: (r["groep"], r["id"])):
        print(f"[{r['groep']}] {r['id']}: {r['vorm']}{', beeld' if r['beeld'] else ''}"
              f"{'' if r['gelezen'] else ', ONLEESBAAR'}\n  {per_id[r['id']]['tekst'][:160]!r}"
              f"\n  BEWERING: {r['bewering']}\n  {r['waarom']}")
    print(Counter((r["groep"], r["vorm"], r["beeld"]) for r in rijen))
    from doublecheck.routemeting import p95
    print(f"wachttijd vormvraag: p95 {p95([r['tijd'] for r in rijen]):.1f} s (vier tegelijk)")
    print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


# --- de CLI ------------------------------------------------------------------------------

def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="De herstelronde (PLAN #31.15)")
    parser.add_argument("stap", choices=("ontwikkel", "set", "indienen", "herkansing", "vorm", "ophalen", "lezen",
                                         "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="indienen: per deel de eerste N, de vormen om de beurt")
    parser.add_argument("--vraag", default=VORM, help="ontwikkel: de versie van de vormvraag")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "set":
        stukken = maak_set()
        print("\n", Counter((s["deel"], s["vorm"]) for s in stukken))
        return
    from doublecheck.config import load_config

    config = load_config(None)
    tabel = bc.ijktabel(config)
    stukken = t._jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    per_batch_id = {t.batch_id(s["id"]): s for s in stukken}
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    if args.stap in ("lezen", "tellen"):
        labels, vormlabels = lees_labels()
        uitkomsten = t.uitkomsten_van(stukken, antwoorden, tabel)
        vormen = vormen_van(antwoorden, uitkomsten)
        if len(vormen) < len(uitkomsten) or len(uitkomsten) < len(stukken):
            print(f"nog niet klaar: {len(stukken) - len(uitkomsten)} zonder uitslag, "
                  f"{len(uitkomsten) - len(vormen)} zonder vormvraag")
        if args.stap == "tellen":
            uit = telling(stukken, uitkomsten, vormen, tabel, labels, vormlabels)
            lek = Counter(k for s in stukken if "lekken" in s for k, w in s["lekken"].items() if w)
            uit["maskeren"] = {"chatberichten": sum("lekken" in s for s in stukken), **dict(lek)}
            print(json.dumps(uit, ensure_ascii=False, indent=1))
            print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
            return
        _lees(stukken, uitkomsten, vormen, tabel, labels, vormlabels,
              {r["id"]: r.get("waarom") for r in antwoorden if r["soort"] == "vorm"})
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    if args.stap == "ontwikkel":
        ontwikkel(client, config, args.vraag)
        return
    batches = UIT / "batches.jsonl"
    if args.stap in ("indienen", "herkansing", "vorm"):
        blok = v.geblokkeerd()
        ingediend = {i for b in t._jsonl(batches) for i in b["ids"]}
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            nog = [s for s in stukken if f"m-{t.batch_id(s['id'])}" not in ingediend]
            if args.proef:
                nog = _proefkeuze(nog, args.proef)
            zinnen = bc.feitzinnen()
            for s in nog:
                b = t.batch_id(s["id"])
                verzoeken.append({"custom_id": f"m-{b}", "params": machinevraag(s, config, blok)})
                geschat += SCHATTING[s["deel"]]
                for k in ("A", "B") if s["kandidaten"] else ():
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{b}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        elif args.stap == "vorm":
            verzoeken = vormvragen(stukken, t.uitkomsten_van(stukken, antwoorden, tabel), config, ingediend)
            geschat = len(verzoeken) * SCHATTING["vorm"]
        else:
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and f"h-{t.batch_id(r['id'])}" not in ingediend:
                    s = per_id[r["id"]]
                    verzoeken.append({"custom_id": f"h-{t.batch_id(s['id'])}",
                                      "params": bc.met_herkansing(machinevraag(s, config, blok), zin)})
                    geschat += SCHATTING["herkansing"]
        if not verzoeken:
            raise SystemExit("niets in te dienen")
        if al_uitgegeven() + geschat > BUDGET:
            raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        batch = client.messages.batches.create(requests=verzoeken)
        with batches.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": batch.id, "stap": args.stap, "schatting": round(geschat, 3),
                                 "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    # ophalen
    alle = t._jsonl(batches)
    klaar = {(r["soort"], r["id"], r.get("sleutel")) for r in antwoorden}
    with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                soort_kort, rest = r.custom_id.split("-", 1)
                msg = r.result.message
                if soort_kort == "f":
                    stuk, sleutel = rest.rsplit("__", 1)
                    s = per_batch_id[stuk]
                    rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel,
                           **bc.feitantwoord(msg, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel,
                                                                 bc.feitzinnen(), config)[1])}
                elif soort_kort == "v":
                    s = per_batch_id[rest]
                    tekst = "".join(getattr(x, "text", "") or "" for x in msg.content)
                    rij = {"soort": "vorm", "id": s["id"], "sleutel": None, **bc.lees_vorm(tekst),
                           "waarom": _waarom(tekst)}
                else:
                    s = per_batch_id[rest]
                    geheugen = [] if s["deel"] == "B5" else s["geheugen"]
                    rij = {"soort": "machine" if soort_kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                           **bc.machineantwoord(msg, geheugen)}
                rij["kosten"] = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
                werkelijk += rij["kosten"]
                if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    t._schrijf(batches, alle)
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    print(Counter((per_id[r["id"]]["deel"], r["oordeel"]) for r in antwoorden if r["soort"] == "machine"),
          Counter((per_id[r["id"]]["deel"], r["vorm"], r["beeld"]) for r in antwoorden if r["soort"] == "vorm"),
          f"\nherkansing nodig: {sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}",
          f"\nuitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


def _lees(stukken: list[dict], uitkomsten: dict[str, dict], vormen: dict[str, dict], tabel: dict, labels: dict,
          vormlabels: dict, waarom: dict[str, str]) -> None:  # pragma: no cover
    for s in stukken:
        u, vorm = uitkomsten.get(s["id"]), vormen.get(s["id"])
        if u is None or vorm is None:
            continue
        o, st, te_lezen = u["oordeel"], u["stand"], []
        zonder = bc.kleur(st, o)
        met = bc.regels(tabel, o, {"stand": st, "laag": u["laag"]}, u["feit"], u["bronnen"], vorm)["kleur"]
        if st == 10 and (s["id"], 10, u["feit"]) not in labels:
            te_lezen.append(f"STAND 10 bij {u['feit']}")
        if (s["id"], o) not in labels:
            if s["label"] == "waar" and zonder == "rood":
                te_lezen.append(f"ROOD ({o}): vals of set fout?")
            elif s["label"] == "onwaar" and zonder == "rood" and u["bronnen"] and not t._eigen_bewijs(s, u):
                te_lezen.append(f"OORDEEL {o}: bewijst, bewijst via factcheck, bewijst niet, set fout?")
            elif s["label"] == "onwaar" and zonder == "groen":
                te_lezen.append(f"GROEN ({o}): vals, beeld nodig, set fout?")
        if s["deel"] == "N5" and vorm["vorm"] == "over een bewering" and s["id"] not in vormlabels:
            te_lezen.append("VORM over een bewering: doet zelf of bericht erover?")
        if te_lezen:
            print(f"\n[{s['id']} · {s['deel']} · {s['vorm']} · {s['bron']}] {' | '.join(te_lezen)} · stand {st}"
                  f" · kleur {zonder} → {met}\n  VORM: {vorm['vorm']}{', beeld' if vorm['beeld'] else ''}"
                  f" — {waarom.get(s['id'])}\n  BERICHT: {s['tekst'][:500]}\n  BEWERING: {u.get('bewering')}"
                  f"\n  UITLEG: {u.get('uitleg')}")
            for b in u["bronnen"][:4]:
                print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:300]}")


if __name__ == "__main__":
    main()
