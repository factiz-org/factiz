"""De kandidaat-rechters op de rechterset (PLAN #30.3, B36).

Per paar (vraag, kandidaat) een score van elke kandidaat, en per kandidaat
één werkpunt: de laagste drempel waarboven *zelfde bewering* nog minstens
99,5% klopt (de lat van B33), met de vindkans die daarbij hoort. Vergeleken
wordt op een vijfde van de ontwikkelhelft (rol *leren*, per zaak), want een
bijgetrainde kandidaat leert van de rest; de meethelft pas na de keuze, en
alleen met `--toets`.

De kandidaten:

- **nu**: Factiz zoals het nu beslist, per paar los: de cosinus van het
  geconfigureerde model, en nul bij een vastgestelde tegenspraak (DR8).
- **herordenaar**: `bge-reranker-v2-m3` zonder bijtrainen (#25.23).
- **nli**: het NLI-model in twee richtingen; de score is de zwakste van de
  twee entailments, want dezelfde bewering volgt uit elkaar, heen en terug
  (§15).
- **rechter-d**: de herordenaar bijgetraind op het lesdeel
  (`rechtertraining.py`); elke score draagt de versie van de gewichten, en
  alleen die van de huidige gewichten tellen.

Een percentage hier is precisie *op de rechterset*, niet de precisie van het
systeem: de mengverhouding van de set is gekozen, niet gemeten. En de set
heeft zelf labelruis (de leesproef: 2 van 200 fout, 6 met twijfel), dus 99,5%
ligt dicht tegen zijn plafond; daarom ook de vindkans bij 99% en 98%.

    python -m doublecheck.rechtermeting scoren --kandidaat nu|herordenaar|nli|rechter-d
    python -m doublecheck.rechtermeting tellen [--toets]
    python -m doublecheck.rechtermeting kiezen --versie <zeefversie met de rechter aan>
    python -m doublecheck.rechtermeting evalueren --versie <naam> --drempels 0.80,0.97,0.1
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from doublecheck.rechterset import UIT
from doublecheck.rechterset import paarsleutel as sleutel

KANDIDATEN = ("nu", "herordenaar", "nli", "rechter-d")
SIMLABELS = UIT.parent.parent / "docs" / "steekproeven" / "30.3-zeef-simulatie.json"
# Het rooster van de keuzeregel, vastgelegd vóór de derde ronde (PLAN #30.3).
VLOEREN = (0.79, 0.80, 0.81, 0.82, 0.83, 0.84, 0.85)
ZELFDES = (0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995)
VETOS = (0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
DOEL = 0.995
KEUZE, ZAAD_KEUZE = 0.2, 3007


def deel(zaak: str) -> str:
    """Binnen de ontwikkelhelft: een vijfde om te kiezen, de rest om van te
    leren, per zaak, zodat varianten van één claim nooit aan beide kanten
    staan."""
    return "keuze" if int(hashlib.sha256(f"{ZAAD_KEUZE}:{zaak}".encode()).hexdigest()[:8], 16) < KEUZE * 16**8 else "les"


def deelname(rijen: list[dict], toets: bool) -> list[dict]:
    """Het keuzedeel van de ontwikkelhelft, of na de keuze de meethelft;
    nooit beide door elkaar, en nooit wat een kandidaat als lesstof zag."""
    if toets:
        return [r for r in rijen if r["rol"] == "meten"]
    return [r for r in rijen if r["rol"] == "leren" and deel(r["zaak"]) == "keuze"]


def lesstof(rijen: list[dict]) -> list[dict]:
    return [r for r in rijen if r["rol"] == "leren" and deel(r["zaak"]) == "les"]


def werkpunt(rijen: list[dict], doel: float = DOEL) -> dict:
    """De laagste drempel waarboven *zelfde* nog minstens `doel` klopt.
    Gelijke scores gaan samen boven of onder de drempel."""
    geordend = sorted(rijen, key=lambda r: -r["score"])
    positief = sum(r["label"] == "zelfde" for r in rijen)
    beste = {"drempel": None, "vindkans": 0.0, "fout": 0, "boven": 0}
    goed = fout = 0
    for i, r in enumerate(geordend):
        goed += r["label"] == "zelfde"
        fout += r["label"] != "zelfde"
        if i + 1 < len(geordend) and geordend[i + 1]["score"] == r["score"]:
            continue
        if goed and goed / (goed + fout) >= doel:
            beste = {"drempel": r["score"], "vindkans": goed / positief if positief else 0.0, "fout": fout,
                     "boven": goed + fout}
    return beste


def auc(rijen: list[dict]) -> float:
    """De kans dat een willekeurig *zelfde*-paar hoger scoort dan een
    willekeurig ander paar; gelijkspel telt half."""
    pos = [r["score"] for r in rijen if r["label"] == "zelfde"]
    neg = [r["score"] for r in rijen if r["label"] != "zelfde"]
    if not pos or not neg:
        return float("nan")
    rang = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg])
    som, i = 0.0, 0
    while i < len(rang):
        j = i
        while j < len(rang) and rang[j][0] == rang[i][0]:
            j += 1
        gemiddeld = (i + j + 1) / 2  # rangen i+1 .. j
        som += gemiddeld * sum(t for _, t in rang[i:j])
        i = j
    return (som - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def simuleer(gelezen: list, thresholds) -> str | None:
    """Welke claim `matched` zou zijn met deze drempels, uit wat de rechter in
    de zeef las ([claim_id, gelijkenis, score]): met `rechter.volgorde` en
    `categorize` zelf, geen tweede beslisregel (DR4), met de getallen- en
    ontkenningsregel zoals de zeef hem per kandidaat vastlegde (DR8)."""
    from doublecheck.categorize import Category, categorize
    from doublecheck.rechter import volgorde
    from doublecheck.search import Candidate

    tegen = {g[0]: bool(g[3]) for g in gelezen if len(g) > 3 and g[3] is not None}
    kandidaten = [Candidate(g[0], g[1], rechter=g[2]) for g in gelezen if g[1] >= thresholds.rechter_vloer]
    if not kandidaten:
        return None
    beste = volgorde(kandidaten, thresholds)[0]
    uitslag = categorize(beste.similarity, thresholds, rechter=beste.rechter,
                         contradiction=tegen.get(beste.claim_id, False))
    return beste.claim_id if uitslag.category is Category.MATCHED else None


def lees_paren() -> list[dict]:
    paren = []
    for naam in ("paren.jsonl", "echt.jsonl", "haiku-echt.jsonl"):
        pad = UIT / naam
        if pad.exists():
            paren += [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]
    # Een echt paar zonder lesstoflabel (Haiku twijfelde, of een zeker conflict met een mens) doet nergens mee.
    return [p for p in paren if p.get("label") is not None]


def _apparaat():  # pragma: no cover - hardware
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def _scoor_nu(paren: list[dict]) -> list[dict]:  # pragma: no cover - met het model
    import numpy as np

    from doublecheck.categorize import Category, categorize
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.relation import contradicts

    cfg = load_config()
    model = cfg.model_versions.text_embedding
    teksten = sorted({p["vraag"] for p in paren} | {p["kandidaat"] for p in paren})
    fp = dict(zip(teksten, fingerprint_texts(teksten, model)))
    uit = []
    for p in paren:
        v, k = fp[p["vraag"]], fp[p["kandidaat"]]
        gelijkenis = float(np.dot(v.vector, k.vector))
        tegen = contradicts(v.numbers, v.negations, p["kandidaat"], p["vraag"], v.negation_tokens)
        cross = bool(v.language and k.language and v.language != k.language)
        oordeel = categorize(gelijkenis, cfg.thresholds, contradiction=tegen, crosslinguaal=cross)
        uit.append({"sleutel": sleutel(p), "score": 0.0 if tegen else gelijkenis, "gelijkenis": gelijkenis,
                    "tegenspraak": tegen, "matched": oordeel.category is Category.MATCHED, "motor": model})
    return uit


def _scoor_herordenaar(paren: list[dict], batch: int = 16, versie: str | None = None) -> list[dict]:  # pragma: no cover
    import torch

    from doublecheck.herordenaar import HERORDENAAR, _laad

    if versie is None:
        versie = HERORDENAAR
        tokenizer, model = _laad(HERORDENAAR)
    else:
        from doublecheck.rechter import _laad as _laad_rechter
        from doublecheck.rechtertraining import MAP

        tokenizer, model = _laad_rechter(str(MAP), versie)  # één keer, met de versiecontrole (DR6)
    apparaat = _apparaat()
    model.to(apparaat)
    uit = []
    with torch.no_grad():
        for start in range(0, len(paren), batch):
            deel = paren[start:start + batch]
            invoer = tokenizer([p["vraag"] for p in deel], [p["kandidaat"] for p in deel], return_tensors="pt",
                               truncation=True, max_length=512, padding=True).to(apparaat)
            scores = torch.sigmoid(model(**invoer).logits.view(-1).float()).tolist()
            uit += [{"sleutel": sleutel(p), "score": s, "motor": versie} for p, s in zip(deel, scores)]
    return uit


def _scoor_nli(paren: list[dict], batch: int = 16) -> list[dict]:  # pragma: no cover - met het model
    import torch

    from doublecheck.config import load_config
    from doublecheck.nli import _laad

    versie = load_config().model_versions.nli
    tokenizer, model, _ = _laad(versie)
    entail = {label.lower(): i for i, label in model.config.id2label.items()}["entailment"]
    apparaat = _apparaat()
    model.to(apparaat)
    uit = []
    with torch.no_grad():
        for start in range(0, len(paren), batch):
            deel = paren[start:start + batch]
            v, k = [p["vraag"] for p in deel], [p["kandidaat"] for p in deel]
            invoer = tokenizer(v + k, k + v, return_tensors="pt", truncation=True, max_length=256,
                               padding=True).to(apparaat)
            kansen = torch.softmax(model(**invoer).logits.float(), dim=-1)[:, entail].tolist()
            heen, terug = kansen[:len(deel)], kansen[len(deel):]
            uit += [{"sleutel": sleutel(p), "score": min(a, b), "heen": a, "terug": b, "motor": versie}
                    for p, a, b in zip(deel, heen, terug)]
    return uit


def _scoor_rechter_d(paren: list[dict]) -> list[dict]:  # pragma: no cover - met het model
    from doublecheck.rechtertraining import versie

    return _scoor_herordenaar(paren, versie=versie())


SCOORDERS = {"nu": _scoor_nu, "herordenaar": _scoor_herordenaar, "nli": _scoor_nli, "rechter-d": _scoor_rechter_d}


def _motor(kandidaat: str) -> str | None:  # pragma: no cover - leest de gewichten
    """Voor een bijgetrainde kandidaat tellen alleen de scores van de huidige
    gewichten (DR6); de andere kandidaten liggen vast."""
    if kandidaat != "rechter-d":
        return None
    from doublecheck.rechtertraining import MAP, versie

    return versie() if MAP.exists() else ""


def _lees_scores(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines()] if pad.exists() else []


def scoren(kandidaat: str, portie: int = 256) -> int:  # pragma: no cover - met het model
    """Hervatbaar: wat al gescoord is, blijft staan."""
    pad = UIT / f"scores-{kandidaat}.jsonl"
    motor = _motor(kandidaat)
    klaar = {r["sleutel"] for r in _lees_scores(pad) if motor is None or r.get("motor") == motor}
    todo, gezien = [], set(klaar)
    paren = lees_paren()
    if kandidaat == "rechter-d":
        # wat hij leerde, zegt niets over hem; het keuzedeel eerst
        les = {sleutel(p) for p in lesstof(paren)}
        paren = deelname(paren, False) + [p for p in deelname(paren, True) if sleutel(p) not in les]
    for p in paren:
        if sleutel(p) not in gezien:
            gezien.add(sleutel(p))
            todo.append(p)
    with pad.open("a", encoding="utf-8") as uit:
        for start in range(0, len(todo), portie):
            for r in SCOORDERS[kandidaat](todo[start:start + portie]):
                uit.write(json.dumps(r) + "\n")
            uit.flush()
            print(f"  {kandidaat}: {min(start + portie, len(todo))}/{len(todo)}", flush=True)
    return len(todo)


def tellen(toets: bool = False) -> dict:  # pragma: no cover - leest de uitvoer
    paren = lees_paren()
    uitslag = {"helft": "meten" if toets else "keuze", "doel": DOEL, "kandidaten": {}}
    for kandidaat in KANDIDATEN:
        pad = UIT / f"scores-{kandidaat}.jsonl"
        if not pad.exists():
            continue
        motor = _motor(kandidaat)
        scores = {r["sleutel"]: r for r in _lees_scores(pad) if motor is None or r.get("motor") == motor}
        rijen = [{**p, **scores[sleutel(p)]} for p in deelname(paren, toets) if sleutel(p) in scores]
        punt = werkpunt(rijen)
        per_soort = defaultdict(Counter)
        for r in rijen:
            soort = r["soort"] if r["bron"] == "gemaakt" else f"{r['bron']}:{r['soort'] or r['label']}"
            per_soort[soort]["n"] += 1
            per_soort[soort]["zelfde"] += punt["drempel"] is not None and r["score"] >= punt["drempel"]
            per_soort[soort]["matched"] += bool(r.get("matched"))
        uitslag["kandidaten"][kandidaat] = {"n": len(rijen), "auc": auc(rijen), **punt,
                                            "ook": {str(d): werkpunt(rijen, d)["vindkans"] for d in (0.99, 0.98)},
                                            "per_soort": {k: dict(v) for k, v in sorted(per_soort.items())}}
        if kandidaat == "nu":  # de echte beslissing, met de drempel uit config
            matched = [r for r in rijen if r.get("matched")]
            goed = sum(r["label"] == "zelfde" for r in matched)
            uitslag["kandidaten"][kandidaat]["beslissing"] = {
                "matched": len(matched), "precisie": goed / len(matched) if matched else None,
                "vindkans": goed / max(1, sum(r["label"] == "zelfde" for r in rijen))}
    return uitslag


def _zeefzaak(r: dict) -> str:
    return min(r["doelen"]) if r["set"] == "P1" else (r["sleutel"] if r["set"] == "N1" else r["claim"])




def treffer(r: dict, cid: str | None, labels: dict, simlabels: dict, haiku: dict) -> str | None:
    """Wat een gesimuleerde `matched` op stuk `r` is: gevonden, goed (dezelfde
    bewering bij een andere claim), fout (iets anders of vals, volgens een
    mens of anders Haiku) of onbekend. Een label voor precies dit stuk en deze
    claim gaat voor; dan dat van de zeefrun; dan Haiku."""
    if cid is None:
        return None
    verwacht = set(r.get("doelen") or [r.get("claim")])
    if r["set"] != "N1" and (cid in verwacht or (cid == r["kandidaat"] and r["uitkomst"] == "gevonden")):
        return "gevonden"
    mens = simlabels.get((r["sleutel"], cid)) or (labels.get(r["sleutel"]) if cid == r["kandidaat"] else None)
    if mens is not None:
        return "fout_mens" if mens in ("anders", "vals") else "goed_ander"
    h = haiku.get((_zeefzaak(r), cid))
    if h is not None:
        return "goed_ander" if h == "zelfde" else "fout_haiku"
    return "onbekend"


def _bronnen(regels: list[dict]):  # pragma: no cover - leest de labelbestanden
    import json as _json

    from doublecheck.rechterlabels import KANDIDATEN as ECHT, UITVOER as HAIKU
    from doublecheck.zeef import lees_labels

    labels = lees_labels(regels)
    sim = {}
    if SIMLABELS.exists():
        sim = {(x["sleutel"], x["kandidaat"]): x["label"]
               for x in _json.loads(SIMLABELS.read_text(encoding="utf-8"))["labels"]}
    per_paar = {sleutel(r): r["haiku"] for r in _lees_scores(HAIKU)}
    haiku = {(p["zaak"], p["kandidaat_id"]): per_paar.get(sleutel(p)) for p in _lees_scores(ECHT)}
    return labels, sim, haiku


# Hoogstens 2% echte fouten op de gemaakte valkuilen (PO 2026-10-17, na §129):
# de valkuilen die doorglippen zijn gelezen, ruis in de set telt niet mee.
HARD_LAT = 0.02
VALKUILEN = SIMLABELS.parent / "30.3-valkuilen.json"


def _schoon(r: dict) -> bool:
    """Geen fout en geen onbekende treffer op het kiesdeel; geen ware zin van
    een minimaal paar naast een rood oordeel; en op de gemaakte harde
    tegenvoorbeelden (verwant en tegenspraak uit het keuzedeel van de
    rechterset) hoogstens `HARD_LAT` echte fouten."""
    if r.get("fout_mens") or r.get("fout_haiku") or r.get("onbekend") or r.get("paar_fout"):
        return False
    return not r.get("hard_n") or r.get("hard_fout", 0) <= HARD_LAT * r["hard_n"]


def paar_fout(gelezen: list, thresholds, klasse: dict) -> bool:
    """Komt een ware zin (minimaal paar, #30.1b) met deze drempels `matched`
    uit op een claim met een rood of omstreden oordeel?"""
    from doublecheck.feitenbasis import VALS_N3

    cid = simuleer(gelezen, thresholds)
    return cid is not None and klasse.get(cid) in VALS_N3


def kies_volgens_regel(rooster: list[dict], marge: int = 2) -> dict | None:
    """De keuzeregel (PLAN #30.3; vastgelegd vóór de derde ronde, veralgemeend
    na §127, PO 2026-10-17): (1) per vloer de laagste `rechter_zelfde` waarvoor
    een veto in het rooster schoon is (geen fout, geen onbekende treffer), plus
    `marge` stappen; (2) de vloer die daarmee het meest vindt bij zijn mildste
    schone veto, bij gelijkspel de hoogste; (3) het strengste veto dat niets
    kost ten opzichte van dat mildste schone veto. Geen schone instelling:
    None."""
    vetos = sorted({r["veto"] for r in rooster if r["veto"] is not None})
    zelfdes = sorted({r["zelfde"] for r in rooster})
    cel = {(r["vloer"], r["zelfde"], r["veto"]): r for r in rooster}

    def mildste_schone(v, z):
        return next((w for w in vetos if (v, z, w) in cel and _schoon(cel[(v, z, w)])), None)

    kandidaten = []
    for v in sorted({r["vloer"] for r in rooster}):
        schone = [z for z in zelfdes if mildste_schone(v, z) is not None]
        if not schone:
            continue
        z = zelfdes[min(zelfdes.index(schone[0]) + marge, len(zelfdes) - 1)]
        w0 = mildste_schone(v, z)
        if w0 is not None:
            kandidaten.append((cel[(v, z, w0)].get("gevonden", 0), v, z, w0))
    if not kandidaten:
        return None
    basis, v, z, w0 = max(kandidaten)
    w = max(w for w in vetos if w >= w0 and (v, z, w) in cel and _schoon(cel[(v, z, w)])
            and cel[(v, z, w)].get("gevonden", 0) == basis)
    return cel[(v, z, w)]


def _motor_van_zeef(versie: str) -> str:  # pragma: no cover - leest de uitvoer van de zeef
    from doublecheck.zeef import UIT as ZEEF

    return json.loads((ZEEF / versie / "motor.json").read_text(encoding="utf-8"))["rechter"]["model"]


def kernachtig(versie: str, config_pad: str) -> dict:  # pragma: no cover - met het model, op de productiedatabase
    """De kernachtige gevallen voor het kiesdeel (PLAN #30.3, na §128), met de
    rechter van zeefrun `versie`: (1) de gemaakte harde tegenvoorbeelden uit
    het keuzedeel van de rechterset, met gelijkenis, rechterscore en de
    getallen- en ontkenningsregel; (2) de ware zinnen van de minimale paren op
    de ontwikkelhelft door het echte /resolve, met wat de rechter las. Nooit de
    kern, nooit de toetshelft."""
    from fastapi.testclient import TestClient

    from doublecheck import api, rechter
    from doublecheck.config import load_config
    from doublecheck.feitenbasis import lees_kern, lees_paren as minimale_paren, n3_items
    from doublecheck.rechter import scores

    motor = _motor_van_zeef(versie)
    config = load_config(config_pad)
    if config.rechter.model != motor:
        raise SystemExit(f"de config draait {config.rechter.model}, de zeefrun {motor}")
    hard = [p for p in deelname(lees_paren(), False) if p["bron"] == "gemaakt" and p["label"] in ("verwant", "tegenspraak")]
    nu = {r["sleutel"]: r for r in _lees_scores(UIT / "scores-nu.jsonl")}
    ontbreekt = [p for p in hard if sleutel(p) not in nu]
    if ontbreekt:
        with (UIT / "scores-nu.jsonl").open("a", encoding="utf-8") as uit:
            for i in range(0, len(ontbreekt), 256):
                for r in _scoor_nu(ontbreekt[i:i + 256]):
                    uit.write(json.dumps(r) + "\n")
                    nu[r["sleutel"]] = r
    pad = UIT / f"hard-{motor}.jsonl"
    with pad.open("w", encoding="utf-8") as uit:
        for i in range(0, len(hard), 64):
            deel = hard[i:i + 64]
            for p in deel:
                r = nu[sleutel(p)]
                if r["gelijkenis"] < 0.75:
                    continue
                score = scores(p["vraag"], [p["kandidaat"]], config.rechter.pad, motor)[0]
                uit.write(json.dumps({"sleutel": sleutel(p), "soort": p["soort"], "gelijkenis": r["gelijkenis"],
                                      "score": score, "tegen": r["tegenspraak"]}) + "\n")
    api.limiter.enabled = False
    api.app.dependency_overrides[api.get_config] = lambda: config
    client = TestClient(api.app)
    ware = [i for i in n3_items(lees_kern(), minimale_paren()) if i["bron"] == "paar" and i["helft"] == "ontwikkel"]
    with (UIT / f"paren-n3-{motor}.jsonl").open("w", encoding="utf-8") as uit:
        for item in ware:
            gezien = []
            rechter.waarnemer = gezien.append
            try:
                client.post("/resolve", json={"text": item["tekst"]})
            finally:
                rechter.waarnemer = None
            uit.write(json.dumps({"sleutel": item["sleutel"], "gelezen": [list(g) for g in gezien[-1]] if gezien else []})
                      + "\n")
    return {"hard": sum(1 for _ in pad.open()), "paren": len(ware)}


def _kernachtig_lezen(versie: str) -> tuple[list, list, dict]:  # pragma: no cover - leest de uitvoer
    import sqlite3

    from doublecheck.verdicts import labelklasse_in_tijd

    motor = _motor_van_zeef(versie)
    hard = _lees_scores(UIT / f"hard-{motor}.jsonl")
    if VALKUILEN.exists():  # ruis in de gemaakte set is geen fout van de rechter; ongelezen telt als fout
        ruis = {k for k, v in json.loads(VALKUILEN.read_text(encoding="utf-8"))["labels"].items() if v == "ruis"}
        hard = [h | {"ruis": h["sleutel"] in ruis} for h in hard]
    paren = _lees_scores(UIT / f"paren-n3-{motor}.jsonl")
    klasse = {}
    if paren:
        conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
        for cid in {g[0] for p in paren for g in p["gelezen"]}:
            rijen = conn.execute("SELECT verdict_normalized, review_date FROM factcheck WHERE claim_id = ?", (cid,))
            klasse[cid] = labelklasse_in_tijd(rijen)[0]
    return hard, paren, klasse


def zeef_kiezen(versie: str, vloeren, zelfdes, vetos) -> dict:  # pragma: no cover - leest de uitvoer van de zeef
    """De drempels van de rechter, gekozen op de ontwikkelhelft van de zeef:
    van P1 en N1 alleen het kiesdeel (de rest was lesstof), P2 en P3 heel."""
    import dataclasses

    from doublecheck.config import load_config
    from doublecheck.zeef import UIT as ZEEF, _alle_regels

    regels = [r for r in _alle_regels(ZEEF / versie) if r["helft"] == "ontwikkel" and "gelezen" in r
              and r["set"] in ("P1", "P2", "P3", "N1")
              and (r["set"] not in ("P1", "N1") or deel(_zeefzaak(r)) == "keuze")]
    labels, sim, haiku = _bronnen(regels)
    hard, paren, klasse = _kernachtig_lezen(versie)
    basis = {r["sleutel"]: r for r in _alle_regels(ZEEF / "factiz-1")}
    uit = {"regels": dict(Counter(r["set"] for r in regels)), "hard": len(hard), "minimale_paren": len(paren),
           "factiz_1": sum(basis.get(r["sleutel"], {}).get("uitkomst") == "gevonden" for r in regels), "rooster": []}
    t0 = load_config().thresholds
    for v in vloeren:
        for z in zelfdes:
            for w in vetos:
                t = dataclasses.replace(t0, rechter_vloer=v, rechter_zelfde=z, rechter_veto=w)
                tel = Counter(treffer(r, simuleer(r["gelezen"], t), labels, sim, haiku) for r in regels)
                tel.pop(None, None)
                if hard:
                    tel["hard_n"] = sum(h["gelijkenis"] >= v for h in hard)
                    tel["hard_fout"] = sum(not h.get("ruis") and
                                           simuleer([["x", h["gelijkenis"], h["score"], h["tegen"]]], t) is not None
                                           for h in hard)
                tel["paar_fout"] = sum(paar_fout(p["gelezen"], t, klasse) for p in paren)
                uit["rooster"].append({"vloer": v, "zelfde": z, "veto": w, **tel})
    return uit


def zeef_evalueren(versie: str, vloer: float, zelfde: float, veto: float | None) -> dict:  # pragma: no cover
    """Eén keuze van drempels over beide helften, naast Factiz 1. De
    ontwikkelhelft bevat lesstof (vertekend); de toetshelft is hier al eens
    gezien (B33): beide zijn een controle, geen poort."""
    import dataclasses

    from doublecheck.config import load_config
    from doublecheck.zeef import UIT as ZEEF, _alle_regels

    alle = [r for r in _alle_regels(ZEEF / versie) if r["set"] in ("P1", "P2", "P3", "N1")]
    labels, sim, haiku = _bronnen(alle)
    basis = {r["sleutel"]: r for r in _alle_regels(ZEEF / "factiz-1")}
    t = dataclasses.replace(load_config().thresholds, rechter_vloer=vloer, rechter_zelfde=zelfde, rechter_veto=veto)
    uit = {}
    for helft in ("ontwikkel", "toets"):
        tel, f1 = Counter(), Counter()
        for r in (x for x in alle if x["helft"] == helft):
            tel[f"{r['set']} n"] += r["set"] != "N1"
            f1[f"{r['set']} n"] += r["set"] != "N1"
            f1[f"{r['set']} gevonden"] += r["set"] != "N1" and basis.get(r["sleutel"], {}).get("uitkomst") == "gevonden"
            soort = treffer(r, simuleer(r.get("gelezen") or [], t), labels, sim, haiku)
            if soort:
                tel[f"{r['set']} {soort}"] += 1
        uit[helft] = {"rechter": dict(sorted(tel.items())), "factiz_1": dict(sorted(f1.items()))}
    return uit


def verslag(uitslag: dict) -> str:  # pragma: no cover - opmaak
    regels = [f"Rechterset, helft {uitslag['helft']}; werkpunt: precisie op de set ≥ {uitslag['doel']:.1%}"]
    for naam, k in uitslag["kandidaten"].items():
        drempel = "geen" if k["drempel"] is None else f"{k['drempel']:.3f}"
        regels.append(f"\n{naam}: {k['n']} paren, AUC {k['auc']:.3f}, drempel {drempel}, "
                      f"vindkans {k['vindkans']:.1%}, fout boven de drempel {k['fout']}")
        regels.append("  vindkans bij lagere precisie (de set heeft ongeveer 1% labelruis): "
                      + ", ".join(f"{float(d):.0%}: {v:.1%}" for d, v in k["ook"].items()))
        if "beslissing" in k:
            b = k["beslissing"]
            regels.append(f"  beslissing nu: {b['matched']} matched, precisie {b['precisie']:.1%}, "
                          f"vindkans {b['vindkans']:.1%}")
        for soort, c in k["per_soort"].items():
            extra = f", matched nu {c.get('matched', 0)}" if naam == "nu" else ""
            regels.append(f"  {soort:<28} {c['n']:>5}  zelfde {c.get('zelfde', 0):>5}{extra}")
    return "\n".join(regels)


def main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="De kandidaat-rechters op de rechterset (PLAN #30.3)")
    parser.add_argument("stap", choices=("scoren", "tellen", "kiezen", "evalueren", "kernachtig"))
    parser.add_argument("--config", help="kernachtig: de proefconfig van de zeefrun")
    parser.add_argument("--versie", help="kiezen, evalueren: de zeefversie met de rechter aan")
    parser.add_argument("--drempels", help="evalueren: vloer,zelfde,veto (bijvoorbeeld 0.80,0.97,0.1)")
    parser.add_argument("--kandidaat", choices=KANDIDATEN)
    parser.add_argument("--toets", action="store_true", help="de meethelft, pas na de keuze op de ontwikkelhelft")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.stap == "scoren":
        import torch
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        print(f"{scoren(args.kandidaat)} paren gescoord")
        return
    if args.stap == "kernachtig":
        import torch
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        print(kernachtig(args.versie, args.config))
        return
    if args.stap == "evalueren":
        v, z, w = (float(x) if x not in ("", "none") else None for x in args.drempels.split(","))
        uit = zeef_evalueren(args.versie, v, z, w)
        (UIT / f"evalueren-{args.versie}.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
        for helft, d in uit.items():
            print(f"{helft}\n  rechter:   {d['rechter']}\n  Factiz 1:  {d['factiz_1']}")
        return
    if args.stap == "kiezen":
        uit = zeef_kiezen(args.versie, VLOEREN, ZELFDES, VETOS)
        uit["keuze"] = kies_volgens_regel(uit["rooster"])
        (UIT / f"kiezen-{args.versie}.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
        print(f"kiesdeel: {uit['regels']}; Factiz 1 vindt er {uit['factiz_1']}")
        print(f"KEUZE VOLGENS DE REGEL: {uit['keuze']}")
        schoon = sorted((r for r in uit["rooster"] if not r.get("fout_mens") and not r.get("fout_haiku")),
                        key=lambda r: (-r.get("gevonden", 0), r.get("onbekend", 0)))
        for r in schoon[:15]:
            print(r)
        print("beste met fouten:", sorted(uit["rooster"], key=lambda r: -r.get("gevonden", 0))[:5])
        return
    uitslag = tellen(args.toets)
    (UIT / f"uitslag-{uitslag['helft']}.json").write_text(json.dumps(uitslag, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
    print(verslag(uitslag))


if __name__ == "__main__":
    main()
