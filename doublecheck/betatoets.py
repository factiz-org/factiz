"""De toets voor de beta (ronde 4 van de koers, B45; PLAN #31.14).

Eén beslissende meting, vooraf vastgelegd: is de controle betrouwbaar genoeg
voor de beta (99%, 98% of 97%), hoeveel nepnieuws herkent ze, en hoe snel is
ze? 800 Engelse berichten die Sonnet nooit zag:
- waar, 300: de 92 vrije ware checks en 208 betrouwbare nieuwsartikelen
  (Sheffield, de kop en het begin), de helft als chatbericht getekend;
- bekend nepnieuws, 200: 100 onware checks als tekst, 100 echte screenshots uit
  M4FC met tekst erin;
- onbekend nepnieuws, 200: verse onware checks, de helft getekend; zonder
  checks uit de database en met de factchecksites geblokkeerd (§150, b);
- zonder bewering, 100: tiplineberichten zonder bewering, de helft getekend.

Zoals op `try.factiz.org/check`: het lokale deel door `berichtcontrole.bericht_uit`
en `voorbereiden`, de vragen uit `machineverzoek` en `feitverzoek`, de
herkansing uit `met_herkansing`, de stand uit `stand_van`. De vragen gaan via de
Batch API: openbare berichten, geen gebruikers (B43). De wachttijd wordt live
gemeten door `beoordeel` zelf. Getekende berichten bestaan alleen in het
geheugen; de M4FC-beelden staan al op schijf (B35).

    python -m doublecheck.hittewacht -- python -m doublecheck.betatoets set
    python -m doublecheck.betatoets indienen [--proef 5]|herkansing|ophalen|live|lezen|tellen
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import verificatie as v

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "betatoets"
LABELS = WORTEL / "docs" / "steekproeven" / "31.14-betatoets.json"
BUDGET = 20.0  # PO 2026-10-27: "grens $20"
ZAAD = 3114
DELEN = ("waar", "bekend", "onbekend", "zonder bewering")
LABEL = {"waar": "waar", "bekend": "onwaar", "onbekend": "onwaar", "zonder bewering": "geen bewering"}
MAX_ARTIKEL = 500
N_STEEKPROEF = 12
N_LIVE = 5  # per soort
MAX_GROEN = 4
LAT_BEWEZEN = 0.90
LAT_ROUTE = 20.0
PII_SCHUIF = 20_000  # andere verzonnen namen en nummers dan in de route (#31.10)
DATUM_STILTE = "2019–2021 (exact date unknown)"  # zoals ronde 6 en de route
# Per vraag via de Batch API, ruim (ronde 1, de route, §150).
SCHATTING = {"waar": 0.023, "bekend": 0.010, "onbekend": 0.036, "zonder bewering": 0.007, "feit": 0.0015,
             "herkansing": 0.035}


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


# --- de regels die vóór de meting vastlagen -------------------------------------------

def artikelbericht(tekst: str) -> str:
    """Een nieuwsartikel zoals iemand het deelt: de kop zonder rubriek en krant, en
    de eerste zinnen, afgebroken op een zin."""
    kop, _, romp = tekst.partition("\n")
    kop = kop.split(" | ")[0].strip()
    lichaam = ""
    for zin in re.split(r"(?<=[.!?])\s+", " ".join(romp.split())):
        if not zin or len(kop) + 1 + len(lichaam) + 1 + len(zin) > MAX_ARTIKEL:
            break
        lichaam = f"{lichaam} {zin}".strip()
    return f"{kop}\n{lichaam}" if lichaam else kop


def _schud(rijen: list[dict], naam: str, zaad: int = ZAAD) -> list[dict]:
    """De toetshelft eerst, elke helft willekeurig met een vast zaad."""
    uit = []
    for toets in (True, False):
        groep = sorted((r for r in rijen if (r.get("helft", "toets") == "toets") == toets), key=lambda r: r["id"])
        random.Random(f"{zaad}-{naam}-{toets}").shuffle(groep)
        uit += groep
    return uit


def kies(pools: dict[str, list[dict]]) -> list[dict]:
    """De 800 berichten van PLAN #31.14, met soort en vorm (tekst, chat of echt screenshot)."""
    def deel(rijen: list[dict], soort: str, bron: str, vormen: list[str]) -> list[dict]:
        return [{**r, "deel": soort, "label": LABEL[soort], "bron": bron, "vorm": vorm} for r, vorm in zip(rijen, vormen)]

    def helften(n: int) -> list[str]:
        return ["tekst"] * (n // 2) + ["chat"] * (n - n // 2)

    checks = _schud(pools["ware checks"], "checks")
    artikelen = _schud(pools["artikelen"], "artikelen")[: 300 - len(checks)]
    return (deel(checks, "waar", "ware check", helften(len(checks)))
            + deel(artikelen, "waar", "artikel", helften(len(artikelen)))
            + deel(_schud(pools["onwaar oud"], "oud")[:100], "bekend", "onware check", ["tekst"] * 100)
            + deel(_schud(pools["screenshots"], "screenshots")[:100], "bekend", "M4FC", ["screenshot"] * 100)
            + deel(_schud(pools["onwaar vers"], "vers")[:200], "onbekend", "onware check, vers", helften(200))
            + deel(_schud(pools["zonder"], "zonder")[:100], "zonder bewering", "tipline", helften(100)))


def rood(stand: int, oordeel: str) -> bool:
    """Rood voor de gebruiker (B45): 1 tot 3 op de schaal, of het oordeel *klopt niet*."""
    return stand <= 3 or oordeel == "klopt niet"


def groen(stand: int) -> bool:
    return stand >= 7


def machineverzoek_b(tekst: str, datum: str | None, blok: list[str], config) -> dict:
    """De enige afwijking van het product, voor onbekend nepnieuws (§150, b): geen
    checks uit de database, en de factchecksites geblokkeerd bij het zoeken."""
    c = config.berichtcontrole
    s = {"id": "toets", "soort": "tekst", "tekst": tekst, "datum": datum}
    params = v.verzoek(s, [], "b", blok, "sonnet", c.vraag)["params"]
    if params["model"] != c.model_id:
        raise bc.VersieFout(f"de code vraagt {params['model']}, config zegt {c.model_id}")
    return bc.met_cache(params) if c.cache else params


def kosten_batch(gebruik: dict) -> float:
    """De Batch API halveert de tokens, niet de zoekopdrachten."""
    tokens = sum(gebruik.get(k, 0) * bc.PRIJS[k] for k in bc.PRIJS)
    return tokens / 2 / 1e6 + gebruik.get("zoek", 0) * v.ZOEKEN_PER_1000 / 1000


def batch_id(stuk_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", stuk_id)


# --- tellen ----------------------------------------------------------------------------

def _eigen_bewijs(stuk: dict, uitkomst: dict) -> bool:
    eigen = set(stuk.get("eigen") or ())
    return any(b.get("soort") == "geheugen" and b.get("claim") in eigen for b in uitkomst["bronnen"])


def steekproef(stukken: list[dict], uitkomsten: dict[str, dict]) -> list[str]:
    """Rood bij bekend nepnieuws met een andere bron dan de eigen check: een mens leest
    of de bron past. Bij onbekend nepnieuws wordt elk rood met bron gelezen."""
    ids = sorted(s["id"] for s in stukken if s["deel"] == "bekend" and s["id"] in uitkomsten
                 and rood(uitkomsten[s["id"]]["stand"], uitkomsten[s["id"]]["oordeel"])
                 and uitkomsten[s["id"]]["bronnen"] and not _eigen_bewijs(s, uitkomsten[s["id"]]))
    return sorted(random.Random(ZAAD).sample(ids, min(N_STEEKPROEF, len(ids))))


def _label(labels: dict, sleutel: tuple) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def telling(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict, proeflabels: dict[str, str],
            lekdata: dict[str, dict] | None = None, tijden: list[dict] | None = None) -> dict:
    """Per soort en vorm wat de oordelen waard zijn, en de zeven eisen van PLAN #31.14.
    Weigert zolang iets dat telt geen label heeft."""
    from doublecheck.fundament import eis_b45
    from doublecheck.meter import wilson
    from doublecheck.routemeting import p95

    proef = steekproef(stukken, uitkomsten)
    onveilig = any(proeflabels.get(i) == "past niet" for i in proef)
    if not onveilig:
        for i in proef:
            if i not in proeflabels:
                raise Weigering(f"{i} uit de steekproef van de bronnen heeft geen label in {LABELS.name}")
    uit: dict = {}
    verkeerde_10 = 0
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if u is None:
            continue
        o, st = u["oordeel"], u["stand"]
        groepen = (s["deel"], f"{s['deel']} · {s['vorm']}")
        for g in groepen:
            d = uit.setdefault(g, {"n": 0, "oordelen": Counter(), "standen": Counter()})
            d["n"] += 1
            d["oordelen"][o] += 1
            d["standen"][st] += 1
        uitkomst = []
        if st == 10:
            uitkomst.append("op 10")
            verkeerde_10 += _label(labels, (s["id"], 10, u.get("feit"))) == "fout"
        if s["label"] == "onwaar":
            if rood(st, o):
                if _eigen_bewijs(s, u):
                    uitkomst.append("bewezen met de eigen check")
                elif u["bronnen"]:
                    eigen = labels.get((s["id"], o))
                    if eigen is None and (onveilig or s["deel"] == "onbekend"):
                        eigen = _label(labels, (s["id"], o))  # zelf herkend of via een overgenomen check?
                    if eigen in (None, "bewijst", "bewijst via factcheck"):
                        uitkomst.append("bewezen met een andere bron")
                        if eigen == "bewijst via factcheck":
                            uitkomst.append("bewezen via een factcheck op het web")
                    else:
                        uitkomst.append("set fout" if eigen == "set fout" else "rood zonder bewijs")
                else:
                    uitkomst.append("rood zonder bron")
            if groen(st):
                label = _label(labels, (s["id"], o))
                uitkomst.append({"vals": "groen vals", "beeld nodig": "groen, beeld nodig"}.get(label, "set fout"))
        elif rood(st, o):
            label = _label(labels, (s["id"], o))
            uitkomst.append({"vals": "onterecht rood", "set fout": "set fout"}.get(label, "rood, label onbekend"))
        for g in groepen:
            for k in uitkomst:
                uit[g][k] = uit[g].get(k, 0) + 1
    for d in uit.values():
        d["bewezen"] = d.get("bewezen met de eigen check", 0) + d.get("bewezen met een andere bron", 0)
        d["oordelen"], d["standen"] = dict(d["oordelen"]), dict(sorted(d["standen"].items()))
    eisen: dict = {}
    if "waar" in uit:
        w = uit["waar"]
        n, fout = w["n"] - w.get("set fout", 0), w.get("onterecht rood", 0)
        uit["eis B45"] = {"onterecht rood": fout, "van": n, "gehaald": eis_b45(fout, n),
                          "bovengrens (95%)": round(wilson(fout, n)[1], 4)}
        eisen["1 betrouwbaarheid minstens 97%"] = uit["eis B45"]["gehaald"] != "onder 97%"
    if "bekend" in uit:
        b = uit["bekend"]
        n = b["n"] - b.get("set fout", 0)
        b["aandeel bewezen"] = round(b["bewezen"] / n, 4) if n else None
        eisen["2 bekend nepnieuws minstens 90% rood met bewijs"] = bool(n) and b["bewezen"] / n >= LAT_BEWEZEN
    if "onbekend" in uit:
        o = uit["onbekend"]
        n = o["n"] - o.get("set fout", 0)
        o["aandeel bewezen"] = round(o["bewezen"] / n, 4) if n else None
    vals_groen = sum(uit[g].get("groen vals", 0) + uit[g].get("groen, beeld nodig", 0)
                     for g in ("bekend", "onbekend") if g in uit)
    if "bekend" in uit or "onbekend" in uit:
        eisen["3 nepnieuws hoogstens 4 keer groen"] = vals_groen <= MAX_GROEN
    if "zonder bewering" in uit:
        eisen["4 zonder bewering nooit rood"] = uit["zonder bewering"].get("onterecht rood", 0) == 0
    eisen["5 geen verkeerde 10"] = verkeerde_10 == 0
    if lekdata:
        tel = Counter(k for lek in lekdata.values() for k, w in lek.items() if w)
        namen_weg = 1 - (tel["naam"] + tel["groep"]) / (2 * len(lekdata))
        uit["maskeren"] = {"n": len(lekdata), **dict(tel), "namen weg": round(namen_weg, 4)}
        eisen["6 geen nummer, adres of handle gelekt"] = tel["telefoon"] + tel["e-mail"] + tel["handle"] == 0
        eisen["6b minstens 95% van de namen uit de chatomgeving weg"] = namen_weg >= 0.95
    if tijden:
        uit["wachttijd"] = {"n": len(tijden), "p95 route": round(p95([t["route"] for t in tijden]), 2)}
        eisen["7 95% binnen 20 seconden"] = uit["wachttijd"]["p95 route"] <= LAT_ROUTE
    uit["eisen"] = eisen
    return uit


# --- de set ------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in Path(pad).read_text(encoding="utf-8").splitlines() if x.strip()] \
        if Path(pad).exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")


def _gebruikt() -> tuple[set[str], set[str]]:  # pragma: no cover - op de rondes
    from doublecheck import routemeting as rm

    ids, sleutels = set(), set(rm._gebruikte_sleutels())
    for r in range(1, 8):
        for s in v.gekozen_stukken(r):
            ids.add(s.get("id"))
            sleutels.add(s.get("sleutel"))
    sleutels |= {s.get("sleutel") for s in _jsonl(rm.UIT / "set.jsonl")}
    return ids, sleutels


def pools(config) -> dict[str, list[dict]]:  # pragma: no cover - op de basisset, M4FC en de tiplines
    import csv

    from doublecheck import basisset
    from doublecheck import routemeting as rm
    from doublecheck.leerstof import taalcode
    from doublecheck.ocr import extract_text

    ids, sleutels = _gebruikt()
    vrij = [s for s in basisset.lees() if taalcode(s.get("taal")) == "en" and s["id"] not in ids
            and s["sleutel"] not in sleutels]

    def laag(soort: str, naam: str, alleen_toets: bool = False) -> list[dict]:
        return [s for s in vrij if s["soort"] == soort and v.laag_van(s) == naam
                and (not alleen_toets or s["helft"] == "toets")]

    screenshots = []
    for k in rm.beeldkandidaten():
        if len(screenshots) >= 150:
            break
        if k["sleutel"] in sleutels:
            continue
        gelezen = extract_text(Path(k["beeld"]).read_bytes(), config.ocr).text
        if rm.soort_van(gelezen) == "S" and not rm.verraadt(gelezen):
            screenshots.append(k)
    with v.TIPLINES.open(encoding="utf-8") as fh:
        rijen = list(csv.DictReader(fh))
    zonder = [{"id": f"tipline:{i:05d}", "sleutel": f"tipline:{i:05d}", "tekst": r["text"], "datum": DATUM_STILTE}
              for i, r in enumerate(rijen) if r["language"] == "en" and r["source"] == "social media"
              and r["majority_label"] == "No" and r["text"].strip() and f"tipline:{i:05d}" not in sleutels]
    return {"ware checks": laag("tekst", "ware check"), "artikelen": laag("artikel", "betrouwbaar artikel", True),
            "onwaar oud": laag("tekst", "onwaar, oud", True), "screenshots": screenshots,
            "onwaar vers": laag("tekst", "onwaar, vers"), "zonder": zonder}


def bron_tekst(s: dict) -> str:
    return artikelbericht(s["tekst"]) if s["bron"] == "artikel" else s["tekst"]


def invoer(s: dict, i: int):  # pragma: no cover - met Pillow
    """(tekst, beeld) zoals een gebruiker het stuurt; een chatbericht bestaat alleen in het geheugen."""
    import io

    from doublecheck import routemeting as rm

    if s["vorm"] == "screenshot":
        return None, Path(s["beeld"]).read_bytes()
    if s["vorm"] == "chat":
        buf = io.BytesIO()
        rm.teken_chat(bron_tekst(s), rm.nep_pii(PII_SCHUIF + i)).save(buf, format="PNG")
        return None, buf.getvalue()
    return bron_tekst(s), None


def maak_set() -> list[dict]:  # pragma: no cover - met de OCR, het model en de database
    from doublecheck import routemeting as rm
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    uit = []
    for i, s in enumerate(kies(pools(config))):
        tekst, beeld = invoer(s, i)
        begin = time.perf_counter()
        bericht = bc.bericht_uit(tekst, beeld, config.ocr)
        voorbereid = bc.voorbereiden(conn, config, bericht) if bericht.strip() else \
            {"tekst": bericht, "geheugen": [], "kandidaten": []}
        rij = {"id": s["id"], "nr": i, "deel": s["deel"], "vorm": s["vorm"], "label": s["label"], "bron": s["bron"],
               "sleutel": s["sleutel"], "zaak": s.get("zaak"), "datum": s.get("datum"), "beeld": s.get("beeld"),
               "helft": s.get("helft"), "tekst": voorbereid["tekst"], "geheugen": voorbereid["geheugen"],
               "kandidaten": voorbereid["kandidaten"], "eigen": sorted(v.eigen_cluster(conn, s.get("zaak"))),
               "lokaal": round(time.perf_counter() - begin, 3)}
        if s["vorm"] == "chat":
            rij["lekken"] = rm.lekken(voorbereid["tekst"], rm.nep_pii(PII_SCHUIF + i))
        uit.append(rij)
        print(f"\r{i + 1}", end="", flush=True)
    _schrijf(UIT / "set.jsonl", uit)
    return uit


# --- de vragen en de antwoorden -----------------------------------------------------------

def machinevraag(s: dict, config, blok: list[str]) -> dict:
    if s["deel"] == "onbekend":
        return machineverzoek_b(s["tekst"], s["datum"], blok, config)
    return bc.machineverzoek(s["tekst"], s["geheugen"], s["datum"], config)


def uitkomsten_van(stukken: list[dict], antwoorden: list[dict], tabel: dict) -> dict[str, dict]:
    """Per bericht het laatste antwoord van de machine (na een herkansing dat van de
    herkansing) en de stand met de twee sleutels, zoals `beoordeel` het doet."""
    machine = {r["id"]: r for r in antwoorden if r["soort"] == "machine"}
    tweede = {r["id"]: r for r in antwoorden if r["soort"] == "herkansing"}
    feit = {(r["id"], r["sleutel"]): r for r in antwoorden if r["soort"] == "feit"}
    geen = {"richting": "geen", "feit": None}
    uit = {}
    for s in stukken:
        a = tweede.get(s["id"]) or machine.get(s["id"])
        if a is None or (bc.herkansing_nodig(a) and s["id"] not in tweede and s["id"] in machine
                         and a is machine[s["id"]]):
            continue  # de herkansing staat nog uit
        if s["kandidaten"] and not all((s["id"], k) in feit for k in ("A", "B")):
            continue
        stand, f, _ = bc.stand_van(tabel, a, feit.get((s["id"], "A"), geen), feit.get((s["id"], "B"), geen))
        uit[s["id"]] = {"oordeel": a["oordeel"], "stand": stand["stand"], "laag": stand["laag"], "feit": f,
                        "bronnen": a["bronnen"], "bewering": a.get("bewering"), "uitleg": a.get("uitleg"),
                        "herkansing": s["id"] in tweede}
    return uit


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in _jsonl(UIT / "batches.jsonl")) \
        + sum(r.get("kosten", 0) for r in _jsonl(UIT / "live.jsonl"))


def lees_labels() -> tuple[dict, dict[str, str]]:
    if not LABELS.exists():
        return {}, {}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {((r["id"], r["oordeel"]) if r["oordeel"] != 10 else (r["id"], 10, r.get("feit"))): r["label"]
              for r in d.get("oordelen", [])}
    return labels, {r["id"]: r["label"] for r in d.get("steekproef", [])}


def _proefkeuze(stukken: list[dict], n: int) -> list[dict]:
    """Per soort n berichten, de vormen om de beurt."""
    uit = []
    for deel in DELEN:
        per_vorm: dict[str, list[dict]] = {}
        for s in stukken:
            if s["deel"] == deel:
                per_vorm.setdefault(s["vorm"], []).append(s)
        rijen = list(per_vorm.values())
        k = 0
        while len([s for s in uit if s["deel"] == deel]) < n and any(rijen):
            rij = rijen[k % len(rijen)]
            if rij:
                uit.append(rij.pop(0))
            k += 1
    return uit


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="De toets voor de beta (PLAN #31.14)")
    parser.add_argument("stap", choices=("set", "indienen", "herkansing", "ophalen", "live", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="indienen: per soort de eerste N, de vormen om de beurt")
    args = parser.parse_args()
    if args.stap == "set":
        stukken = maak_set()
        print("\n", Counter((s["deel"], s["vorm"]) for s in stukken))
        return
    from doublecheck.config import load_config

    config = load_config(None)
    stukken = _jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    per_batch_id = {batch_id(s["id"]): s for s in stukken}
    antwoorden = _jsonl(UIT / "antwoorden.jsonl")
    tabel = bc.ijktabel(config)
    if args.stap in ("lezen", "tellen"):
        labels, proeflabels = lees_labels()
        uitkomsten = uitkomsten_van(stukken, antwoorden, tabel)
        if args.stap == "tellen":
            lekdata = {s["id"]: s["lekken"] for s in stukken if "lekken" in s and s["id"] in uitkomsten}
            tijden = _jsonl(UIT / "live.jsonl")
            print(json.dumps(telling(stukken, uitkomsten, labels, proeflabels, lekdata, tijden or None),
                             ensure_ascii=False, indent=1))
            print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
            return
        _lees(stukken, uitkomsten, labels, proeflabels)
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    batches = UIT / "batches.jsonl"
    if args.stap == "live":
        _live(stukken, client, config, tabel)
        return
    if args.stap in ("indienen", "herkansing"):
        blok = v.geblokkeerd()
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            nog = [s for s in stukken if f"m-{batch_id(s['id'])}" not in ingediend]
            if args.proef:
                nog = _proefkeuze(nog, args.proef)
            zinnen = bc.feitzinnen()
            for s in nog:
                verzoeken.append({"custom_id": f"m-{batch_id(s['id'])}", "params": machinevraag(s, config, blok)})
                geschat += SCHATTING[s["deel"]]
                for k in ("A", "B") if s["kandidaten"] else ():
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{batch_id(s['id'])}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        else:
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and f"h-{batch_id(r['id'])}" not in ingediend:
                    s = per_id[r["id"]]
                    verzoeken.append({"custom_id": f"h-{batch_id(s['id'])}",
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
    alle = _jsonl(batches)
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
                    continue
                soort_kort, rest = r.custom_id.split("-", 1)
                if soort_kort == "f":
                    stuk, sleutel = rest.rsplit("__", 1)
                    s = per_batch_id[stuk]
                    rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel,
                           **bc.feitantwoord(r.result.message, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel,
                                                                             bc.feitzinnen(), config)[1])}
                else:
                    s = per_batch_id[rest]
                    geheugen = [] if s["deel"] == "onbekend" else s["geheugen"]
                    rij = {"soort": "machine" if soort_kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                           **bc.machineantwoord(r.result.message, geheugen)}
                rij["kosten"] = round(kosten_batch(bc.gebruik_uit(r.result.message)), 5)
                werkelijk += rij["kosten"]
                if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    _schrijf(batches, alle)
    antwoorden = _jsonl(UIT / "antwoorden.jsonl")
    print(Counter((per_id[r["id"]]["deel"], r["oordeel"]) for r in antwoorden if r["soort"] == "machine"),
          f"\nherkansing nodig: {sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}",
          f"\nuitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


def _lees(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict, proeflabels: dict) -> None:  # pragma: no cover
    proef = set(steekproef(stukken, uitkomsten))
    onveilig = "past niet" in proeflabels.values()
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if u is None:
            continue
        o, st, te_lezen = u["oordeel"], u["stand"], []
        if st == 10 and (s["id"], 10, u["feit"]) not in labels:
            te_lezen.append(f"STAND 10 bij {u['feit']}")
        if s["label"] == "onwaar":
            if rood(st, o) and u["bronnen"] and not _eigen_bewijs(s, u) and (s["id"], o) not in labels:
                if s["deel"] == "onbekend" or onveilig:
                    te_lezen.append(f"OORDEEL {o}: bewijst, bewijst via factcheck, bewijst niet?")
                elif s["id"] in proef and s["id"] not in proeflabels:
                    te_lezen.append("STEEKPROEF: past de bron?")
            if groen(st) and (s["id"], o) not in labels:
                te_lezen.append(f"GROEN ({o})")
        elif rood(st, o) and (s["id"], o) not in labels:
            te_lezen.append(f"ROOD ({o})")
        if te_lezen:
            print(f"\n[{s['id']} · {s['deel']} · {s['vorm']} · {s['bron']}] {' | '.join(te_lezen)} · stand {st}\n"
                  f"  BERICHT: {s['tekst'][:500]}\n  BEWERING: {u.get('bewering')}\n  UITLEG: {u.get('uitleg')}")
            for b in u["bronnen"][:4]:
                print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:300]}")


def _live(stukken: list[dict], client, config, tabel: dict) -> None:  # pragma: no cover - met het model
    """De wachttijd: N_LIVE per soort door `beoordeel` zelf, na een warme start."""
    from doublecheck.storage import connect

    conn = connect("doublecheck.db")
    kosten = bc.kostenverbinding(config)
    zinnen = bc.feitzinnen()
    bc.voorbereiden(conn, config, "warm")  # het model en de lijst met feiten laden, zoals bij het opstarten
    gedaan = {r["id"] for r in _jsonl(UIT / "live.jsonl")}
    rng = random.Random(ZAAD + 1)
    kies_live = [s for d in DELEN for s in sorted(rng.sample([x for x in stukken if x["deel"] == d], N_LIVE),
                                                  key=lambda x: x["nr"])]
    for s in kies_live:
        if s["id"] in gedaan:
            continue
        if al_uitgegeven() + 0.06 > BUDGET:
            print("gestopt: het budget")
            break
        tekst, beeld = invoer(s, s["nr"])
        begin = time.perf_counter()
        voorbereid = bc.voorbereiden(conn, config, bc.bericht_uit(tekst, beeld, config.ocr))
        lokaal = time.perf_counter() - begin
        begin = time.perf_counter()
        uit = bc.beoordeel(kosten, voorbereid, client, config, s["datum"], tabel, zinnen, dag="betatoets")
        model = time.perf_counter() - begin
        rij = {"id": s["id"], "deel": s["deel"], "vorm": s["vorm"], "lokaal": round(lokaal, 3),
               "model": round(model, 3), "route": round(lokaal + model, 3), "oordeel": uit["oordeel"],
               "kosten": round(uit["kosten"], 5)}
        with (UIT / "live.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
        print(f"{s['id']}: {rij['route']:.1f} s ({uit['oordeel']}); ${al_uitgegeven():.2f}", flush=True)


if __name__ == "__main__":
    main()
