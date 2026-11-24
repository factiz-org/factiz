"""De tweede artikellezer (PLAN #30.11c; PO 2026-10-22: "Akkoord met het
voorstel voor lezer B").

Lezer A (#30.11b) vond artikelen, maar gaf op webtekst 30 valse treffers, ook
bij een drempel van 0,99 (BENCHMARK §136): hij leerde het onderwerp, niet
*deze bewering, op dit moment*. Lezer B leert dat verschil, met wat vóór het
bouwen vastlag:

- **Lesstof:** alles van A, plus (a) elk Sheffield-artikel uit het lesdeel
  naast de claim van zijn ontkrachting, met een Haiku-label: desinformatie die
  de bewering zeker doet is positief, een betrouwbaar artikel dat haar zeker
  niet doet (of weerlegt) is negatief, de rest valt af; (b) de webtekst van
  de ontwikkelhelft van N1 waar A `HARD_VANAF` of hoger gaf, uit het lesdeel
  per stuk, naast haar kandidaten, met een Haiku-label.
- **Scheiding, zoals A:** alleen zaken van de ontwikkelhelft zonder
  clustergenoot in de toetshelft; les en keuze per zaak, webtekst per stuk.
- **Training:** opnieuw vanaf de herordenaar, met de instellingen van A.
- **Drempels, op het keuzedeel:** per vloer de laagste `artikel_zelfde` waarbij
  geen enkel negatief van het keuzedeel erboven komt (webtekst van N1 die de
  lezer leest, betrouwbare Sheffield-artikelen naast hun kandidaten,
  ontkrachtingen naast hun titel); dan de vloer met de meeste positieven (de
  P2-artikelen en de Sheffield-desinformatie van het keuzedeel).

    python -m doublecheck.lezerb lesstof
    python -m doublecheck.lezerb plan|indienen [--proef N]|ophalen|uitschrijven
    python -m doublecheck.lezerb trainen
    python -m doublecheck.lezerb kiezen
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

from doublecheck.artikellezer import DREMPELS, VLOEREN, mag_mee

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "artikellezer" / "b"
LEZER = WORTEL / "data" / "artikellezer" / "lezer-b"
LEZER_A_N1 = WORTEL / "data" / "zeef" / "factiz-lezer"  # de scores van A op N1, per pool
HARD_VANAF = 0.50
K = 5
MIN_TEKST = 200
BLOK = 1000  # stukken per blok kandidaten; elk blok op schijf, dus hervatbaar

# Welke Haiku-labels per bron lesstof worden (vastgelegd vóór het bouwen).
_HOUDT = {"sheffield-desinformatie": {1}, "sheffield-betrouwbaar": {0}, "webtekst-hard": {0, 1}}


def deel_van(claim: str, helft_van, leden_van, deel) -> str | None:
    """`les` of `keuze` voor een zaak van de ontwikkelhelft zonder clustergenoot
    in de toetshelft; anders `None`: nooit lesstof en nooit keuzestof."""
    if helft_van(claim) != "ontwikkel" or not mag_mee(leden_van(claim), helft_van):
        return None
    return deel(claim)


def na_label(paren: list[dict]) -> list[dict]:
    """De gelabelde paren die lesstof worden, volgens `_HOUDT` per bron."""
    return [p for p in paren if p.get("label") is not None and p["label"] in _HOUDT.get(p["bron"], {0, 1})]


def _per_stuk(rijen: list[dict]) -> dict:
    per_stuk = collections.defaultdict(list)
    for r in rijen:
        per_stuk[(r["soort"], r["sleutel"])].append(r)
    return per_stuk


def _tel(per_stuk: dict, vloer: float, drempel: float) -> dict:
    gevonden = ander = negatief = 0
    for (soort, _), kandidaten in per_stuk.items():
        boven = [k for k in kandidaten if k["gelijkenis"] >= vloer and k["score"] >= drempel]
        if not boven:
            continue
        if soort != "positief":
            negatief += 1
        elif max(boven, key=lambda k: k["score"])["verwacht"]:
            gevonden += 1
        else:
            ander += 1
    return {"gevonden": gevonden, "ander": ander, "negatief": negatief}


def _schoon(per_stuk: dict, vloer: float, drempels) -> float | None:
    return next((d for d in drempels if _tel(per_stuk, vloer, d)["negatief"] == 0), None)


def kies_drempels(rijen: list[dict], vloeren=VLOEREN, drempels=DREMPELS) -> dict:
    """De regel van #30.11c: per vloer de laagste drempel waarbij geen negatief
    stuk (elke `soort` behalve `positief`) een kandidaat vanaf de vloer met een
    score vanaf de drempel heeft; dan de vloer met de meeste positieven waarvan
    de best scorende kandidaat boven de drempel de verwachte is (bij
    gelijkstand de hoogste vloer). `rijen`: per kandidaat soort, sleutel,
    verwacht, gelijkenis, score."""
    per_stuk = _per_stuk(rijen)
    per_vloer = {}
    for vloer in vloeren:
        drempel = _schoon(per_stuk, vloer, drempels)
        if drempel is not None:
            per_vloer[str(vloer)] = {"drempel": drempel, **_tel(per_stuk, vloer, drempel)}
    beste = max(per_vloer.items(), key=lambda kv: (kv[1]["gevonden"], float(kv[0])), default=None)
    return {"per_vloer": per_vloer,
            "gekozen": {"vloer": float(beste[0]), "drempel": beste[1]["drempel"]} if beste else None}


def zonder_terecht(rijen: list[dict], terecht: set[tuple[str, str]]) -> list[dict]:
    """De aanvulling van de keuzeregel (PO 2026-10-22): een negatief paar
    (sleutel, claim) waarvan Haiku zeker zegt dat de tekst de bewering doet,
    is geen tegenvoorbeeld; een positief blijft altijd staan."""
    return [r for r in rijen if r["soort"] == "positief" or (r["sleutel"], r["claim"]) not in terecht]


def beslist(rijen: list[dict], onbepaald_onder: float, vloeren=VLOEREN, drempels=DREMPELS) -> dict | None:
    """Dezelfde keuze als `kies_drempels`, zonder alle webtekst te lezen.

    `rijen` bevat alle positieven en alle negatieven behalve webtekst waarvan
    de hoogste gelijkenis niet boven `onbepaald_onder` komt; een vloer daarboven
    is dus volledig. Een lagere vloer heeft minstens dezelfde negatieven, dus
    een minstens even hoge drempel, en bij die drempel vindt hij hooguit wat
    de positieven (die compleet zijn) laten zien. Kan geen lagere vloer meer
    winnen, dan staat de keuze vast: `{"vloer", "drempel"}`, of `{}` als geen
    vloer een schone drempel heeft. Anders `None`: eerst meer webtekst."""
    per_stuk = _per_stuk(rijen)
    bepaald = sorted((v for v in vloeren if v > onbepaald_onder), reverse=True)
    open_ = [v for v in vloeren if v <= onbepaald_onder]
    if not bepaald:
        return None
    gekozen: dict[float, tuple[float, int]] = {}
    for vloer in bepaald:
        drempel = _schoon(per_stuk, vloer, drempels)
        if drempel is None:
            open_ = []  # elke lagere vloer heeft minstens deze negatieven
            break
        gekozen[vloer] = (drempel, _tel(per_stuk, vloer, drempel)["gevonden"])
    if not gekozen:
        return {}
    vloer, (drempel, gevonden) = max(gekozen.items(), key=lambda kv: (kv[1][1], kv[0]))
    ondergrens = max(d for d, _ in gekozen.values())
    for v in open_:
        # Wat al gelezen is, is een deel van de negatieven van deze vloer: haar
        # drempel is minstens de schone drempel daarvan (en die van hogere vloeren).
        deel_drempel = _schoon(per_stuk, v, drempels)
        if deel_drempel is None:
            continue  # zelfs zonder de rest is deze vloer niet schoon te krijgen
        if _tel(per_stuk, v, max(ondergrens, deel_drempel))["gevonden"] > gevonden:
            return None
    return {"vloer": vloer, "drempel": drempel}


def webtekst_hard(pad: Path = UIT / "te-labelen.jsonl") -> set[str]:
    """De webteksten (N1-sleutels) die als harde negatieven lesstof van B
    werden; de zeef telt ze niet mee in het vals alarm, zoals bij A."""
    from doublecheck.artikellezer import _lees_jsonl

    return {r["zaak"] for r in _lees_jsonl(pad) if r["bron"] == "webtekst-hard"}


def kies_korte(teksten: list[str], n: int, zaad: int = 3011) -> list[str]:
    """Voor de tijdmeting (B41): een vaste trekking van teksten met precies
    twee zinnen die meetellen (de kortste tekst waarop de lezer leest)."""
    import random

    from doublecheck.zinnen import eenheden

    twee = [t for t in teksten if len(eenheden(t)) == 3]
    return random.Random(zaad).sample(twee, min(n, len(twee)))


def sheffield_uitslag(regels: list[dict]) -> dict:
    """De controle op de Sheffield-artikelen uit de toetshelft, alleen totalen:
    bij desinformatie wat gevonden werd, bij een betrouwbaar artikel hoe vaak
    het `matched` gaf op zijn eigen claim (lezen om te tellen) of een andere."""
    des = collections.Counter(r["uitkomst"] for r in regels if r["klasse"] == "disinformation")
    bet = collections.Counter(r["uitkomst"] for r in regels if r["klasse"] == "trustworthy")
    return {"desinformatie": {"n": sum(des.values()), "gevonden": des["gevonden"], "ander": des["ander"],
                              "verwant": des["verwant"], "niets": des["niets"]},
            "betrouwbaar": {"n": sum(bet.values()), "matched_eigen_claim": bet["gevonden"],
                            "matched_andere_claim": bet["ander"], "verwant": bet["verwant"], "niets": bet["niets"]}}


# --- op de productiedatabase en met de modellen ------------------------------

def _context():  # pragma: no cover - op de productiedatabase
    import sqlite3

    from doublecheck.clustering import cluster_members
    from doublecheck.rechtermeting import deel
    from doublecheck.zeef import helft

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tekst = {r[0]: r[1] for r in conn.execute("SELECT claim_id, canonical_text FROM claim")}
    cluster: dict[str, set[str]] = {}

    def leden(c):
        if c not in cluster:
            cluster[c] = cluster_members(conn, c) | {c}
        return cluster[c]

    def helft_van(c):
        return helft(f"zaak:{c}")

    return conn, tekst, lambda c: deel_van(c, helft_van, leden, deel), leden


def _sheffield_items():  # pragma: no cover - leest de opgehaalde artikelen
    """De Sheffield-artikelen met een claim en alineatekst, als kop met
    inleiding (zoals P2, met de boilerplate per site eruit), met hun klasse."""
    from doublecheck import sheffield
    from doublecheck.netwerktoets import items

    regels = [r | {"report": ""} for r in sheffield.regels(sheffield.UIT)
              if r["claim_id"] and r["bron"] and len(r["tekst"]) >= MIN_TEKST]
    klasse = {r["article_url"]: r["klasse"] for r in regels}
    return [(i, klasse[i.artikel]) for i in items(regels)]


def _n1_stukken(deel_wens: str, score_vanaf: float | None = None):  # pragma: no cover
    """Webtekst van de ontwikkelhelft van N1 met twee of meer eenheden, uit
    `deel_wens` per stuk; met `score_vanaf` alleen wat lezer A zo hoog gaf,
    anders alles met een kandidaat vanaf de laagste vloer (de voorfilter per
    eenheid van `factiz-artikel`). Per stuk sleutel, tekst en die hoogste
    gelijkenis, een bovengrens voor wat `_kandidaten` nu vindt."""
    import numpy as np

    from doublecheck.rechtermeting import deel
    from doublecheck.variantenbatch import lees_regels
    from doublecheck.zeef import POOLS, helft

    bron = WORTEL / "data" / "zeef" / "factiz-artikel"
    uit = []
    for p in POOLS:
        rijen = lees_regels(p)
        zinnen = np.load(bron / f"N1-{p.name}-hoogste-zinnen.npy")
        best = np.maximum(np.load(bron / f"N1-{p.name}-hoogste.npy"), zinnen)
        if score_vanaf is not None:
            scores = {r["i"]: r["score"] for r in map(json.loads, (LEZER_A_N1 / f"N1-{p.name}-lezer.jsonl")
                                                       .read_text(encoding="utf-8").split("\n")[:-1])}
            kies = [i for i, s in scores.items() if s >= score_vanaf]
        else:
            kies = np.nonzero((zinnen > -1) & (best >= min(VLOEREN)))[0].tolist()
        for i in kies:
            sleutel = f"N1:{p.name}:{rijen[i]['claim_id']}"
            if helft(sleutel) == "ontwikkel" and deel(sleutel) == deel_wens:
                uit.append((sleutel, rijen[i]["varianten"][0]["tekst"], float(best[i])))
    return uit


def lesstof() -> dict:  # pragma: no cover - op de productiedatabase
    """De paren die Haiku labelt, naar `UIT/te-labelen.jsonl`."""
    from doublecheck.artikellezer import TE_LABELEN, _kandidaten, load_config_versie

    conn, tekst, deel_van_, _ = _context()
    paren = []
    for item, klasse in _sheffield_items():
        if deel_van_(item.claim_id) == "les" and item.claim_id in tekst:
            paren.append({"claim": tekst[item.claim_id], "tekst": item.kop_inleiding, "label": None,
                          "bron": f"sheffield-{'desinformatie' if klasse == 'disinformation' else 'betrouwbaar'}",
                          "zaak": item.claim_id, "deel": "les"})
    hard = _n1_stukken("les", HARD_VANAF)
    for (sleutel, t, _), lijst in zip(hard, _kandidaten([t for _, t, _ in hard], conn, load_config_versie(), k=K,
                                                     vloer=min(VLOEREN))):
        for c, _, _, _ in lijst:
            paren.append({"claim": tekst[c], "tekst": t, "label": None, "bron": "webtekst-hard", "zaak": sleutel,
                          "deel": "les"})
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / TE_LABELEN.name).write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in paren),
                                       encoding="utf-8")
    return {"paren": dict(collections.Counter(p["bron"] for p in paren)), "webtekst_stukken": len(hard)}


def trainen() -> dict:  # pragma: no cover - met het model
    from doublecheck.artikellezer import _lees_jsonl
    from doublecheck.artikellezer import trainen as trainen_a

    return trainen_a(extra=na_label(_lees_jsonl(UIT / "lesstof-haiku.jsonl")), naam="lezer-b")


_LEZER = None


def _scores(paren: list[tuple[str, str]]) -> list[float]:  # pragma: no cover - met het model
    """Scores van lezer B, met het model één keer geladen (claim eerst, 384 tokens)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck.artikellezer import _apparaat

    global _LEZER
    if _LEZER is None:
        pad = str(LEZER.resolve())
        _LEZER = (AutoTokenizer.from_pretrained(pad),
                  AutoModelForSequenceClassification.from_pretrained(pad).to(_apparaat()).eval())
    tokenizer, model = _LEZER
    uit: list[float] = []
    with torch.no_grad():
        for start in range(0, len(paren), 16):
            deel_ = paren[start:start + 16]
            invoer = tokenizer([a for a, _ in deel_], [b for _, b in deel_], return_tensors="pt", truncation=True,
                               max_length=384, padding=True).to(model.device)
            uit += torch.sigmoid(model(**invoer).logits.view(-1).float()).cpu().tolist()
    return uit


def _keuzestof():  # pragma: no cover - op de productiedatabase
    """De vaste keuzestof (positieven en betrouwbare artikelen) en de webtekst
    van het keuzedeel, met de context."""
    from doublecheck.netwerktoets import items
    from doublecheck.zeef import P2_MAP

    conn, tekst, deel_van_, leden = _context()
    vast = []  # (soort, sleutel, tekst, verwachte claim of None)
    p2 = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").split("\n") if r.strip()]
    for i in items(p2):
        if deel_van_(i.claim_id) == "keuze":
            vast.append(("positief", f"P2:{i.artikel}#{i.claim_id}", i.kop_inleiding, i.claim_id))
    for i, klasse in _sheffield_items():
        if deel_van_(i.claim_id) == "keuze":
            soort = "positief" if klasse == "disinformation" else "betrouwbaar"
            vast.append((soort, f"S:{i.artikel}", i.kop_inleiding, i.claim_id if soort == "positief" else None))
    return conn, tekst, leden, vast, _n1_stukken("keuze")


KANDIDATEN = UIT / "keuze-kandidaten.jsonl"
KEUZE_HAIKU = UIT / "keuze-haiku"  # de labels van de aanvulling op de keuzeregel
SCORES = UIT / "keuze-scores.jsonl"


def _kandidaten_op_schijf(vast, web) -> dict[str, list]:  # pragma: no cover
    from doublecheck.artikellezer import _lees_jsonl

    kandidaten = {r["sleutel"]: r["kandidaten"] for r in _lees_jsonl(KANDIDATEN)}
    # De blokken van de eerste poging (volgorde: vast, dan webtekst per pool).
    oude_volgorde = [s for _, s, _, _ in vast] + [s for s, _, _ in web]
    for n, blok in enumerate(sorted((UIT / "keuze-kandidaten").glob("blok-*.json"))):
        for sleutel, lijst in zip(oude_volgorde[n * 1000:(n + 1) * 1000], json.loads(blok.read_text())):
            kandidaten.setdefault(sleutel, lijst)
    return kandidaten


def kandidaten_maken(vanaf: float, hoogstens: int | None = None) -> dict:  # pragma: no cover - met bge-m3 en de index
    """Stap 1 van de keuze, zonder lezer in het geheugen: de kandidaten van de
    vaste keuzestof en van de webtekst met een hoogste gelijkenis vanaf
    `vanaf`, per 1.000 op schijf (hervatbaar)."""
    import time

    from doublecheck.artikellezer import _kandidaten, load_config_versie

    conn, _, _, vast, web = _keuzestof()
    kandidaten = _kandidaten_op_schijf(vast, web)
    nodig = [(s, t) for _, s, t, _ in vast if s not in kandidaten]
    nodig += [(s, t) for s, t, best in sorted(web, key=lambda w: -w[2]) if best >= vanaf and s not in kandidaten]
    nodig = nodig[:hoogstens] if hoogstens else nodig
    print(f"kandidaten nodig: {len(nodig):,}", flush=True)
    versie = load_config_versie()
    for start in range(0, len(nodig), 1000):
        t0 = time.time()
        deel_ = nodig[start:start + 1000]
        lijsten = _kandidaten([t for _, t in deel_], conn, versie, k=K, vloer=min(VLOEREN))
        with KANDIDATEN.open("a", encoding="utf-8") as f:
            for (sleutel, _), lijst in zip(deel_, lijsten):
                f.write(json.dumps({"sleutel": sleutel, "kandidaten": [[c, round(g, 4)] for c, g, _, _ in lijst]})
                        + "\n")
        print(f"  {min(start + 1000, len(nodig)):,} van {len(nodig):,} in {time.time() - t0:.0f} s", flush=True)
    return {"gemaakt": len(nodig), "vanaf": vanaf}


def kiezen() -> dict:  # pragma: no cover - met het model
    """Stap 2 van de keuze, zonder zoekindex in het geheugen: lezer B leest de
    kandidaten die op schijf staan, eerst de vaste keuzestof en de
    ontkrachtingen, dan de webtekst van hoog naar laag; na elk blok van 1.000
    `beslist`. Ontbreken de kandidaten voor het volgende blok, dan stopt hij
    en noemt hij de gelijkenis vanaf waar `kandidaten` verder moet."""
    import time

    from doublecheck.artikellezer import LESSTOF, _lees_jsonl

    _, tekst, leden, vast, web = _keuzestof()
    kandidaten = _kandidaten_op_schijf(vast, web)
    ontbreekt = [s for _, s, _, _ in vast if s not in kandidaten]
    if ontbreekt:
        raise SystemExit(f"{len(ontbreekt)} vaste stukken zonder kandidaten; eerst `lezerb kandidaten`")
    scores = {(r["sleutel"], r["claim"]): r["score"] for r in _lees_jsonl(SCORES)}

    def lees(paren: list[tuple[str, str, str, str]]) -> None:
        """(sleutel, claim, claimtekst, tekst) die nog geen score hebben."""
        nieuw = [p for p in paren if (p[0], p[1]) not in scores]
        with SCORES.open("a", encoding="utf-8") as f:
            for start in range(0, len(nieuw), 2000):
                deel_ = nieuw[start:start + 2000]
                for (sleutel, c, _, _), s in zip(deel_, _scores([(ct, t) for _, _, ct, t in deel_])):
                    scores[(sleutel, c)] = round(s, 5)
                    f.write(json.dumps({"sleutel": sleutel, "claim": c, "score": round(s, 5)}) + "\n")

    def rijen_van(stukken) -> list[dict]:
        lees([(sleutel, c, tekst[c], t) for _, sleutel, t, _ in stukken for c, _ in kandidaten[sleutel]])
        return [{"soort": soort, "sleutel": sleutel, "claim": c, "gelijkenis": g,
                 "verwacht": bool(verwacht) and c in leden(verwacht), "score": scores[(sleutel, c)]}
                for soort, sleutel, _, verwacht in stukken for c, g in kandidaten[sleutel]]

    t0 = time.time()
    rijen = rijen_van(vast)
    # De ontkrachtingen van het keuzedeel naast hun titel: altijd gelezen (gelijkenis 1).
    ontkrachtingen = [r for r in _lees_jsonl(LESSTOF) if r["bron"] == "eu-ontkrachting" and r["deel"] == "keuze"]
    lees([(f"O:{r['zaak']}", r["zaak"], r["claim"], r["tekst"]) for r in ontkrachtingen])
    rijen += [{"soort": "ontkrachting", "sleutel": f"O:{r['zaak']}", "claim": r["zaak"], "gelijkenis": 1.0,
               "verwacht": False, "score": scores[(f"O:{r['zaak']}", r["zaak"])]} for r in ontkrachtingen]
    print(f"vast: {len(vast)} stukken en {len(ontkrachtingen)} ontkrachtingen in {time.time() - t0:.0f} s", flush=True)

    from doublecheck.artikellezer import label_uit, paarsleutel

    gevraagd = {(r["zaak"], r["claim_id"]): r for r in _lees_jsonl(KEUZE_HAIKU / "te-labelen.jsonl")}
    antwoord = {r["id"]: label_uit(r["tekst"]) for r in _lees_jsonl(KEUZE_HAIKU / "antwoorden.jsonl")}
    claimtekst = {f"O:{r['zaak']}": r["claim"] for r in ontkrachtingen}
    teksten = {s: t for _, s, t, _ in vast} | {f"O:{r['zaak']}": r["tekst"] for r in ontkrachtingen}

    def labels_klaar(rijen_: list[dict], vanaf: float = min(DREMPELS)) -> tuple[set[tuple[str, str]], int]:
        """De paren die zeker de bewering doen, en hoeveel negatieven vanaf
        `vanaf` nog op een label wachten (die worden aangevraagd). Een negatief
        onder de drempel van de laagste volledig gelezen vloer verandert niets
        meer: elke lagere vloer heeft minstens die drempel."""
        nodig = [r for r in rijen_ if r["soort"] != "positief" and r["score"] >= vanaf]
        nieuw = [r for r in nodig if (r["sleutel"], r["claim"]) not in gevraagd]
        if nieuw:
            KEUZE_HAIKU.mkdir(parents=True, exist_ok=True)
            with (KEUZE_HAIKU / "te-labelen.jsonl").open("a", encoding="utf-8") as f:
                for r in nieuw:
                    regel = {"claim": claimtekst.get(r["sleutel"]) or tekst[r["claim"]], "tekst": teksten[r["sleutel"]],
                             "label": None, "bron": r["soort"], "zaak": r["sleutel"], "claim_id": r["claim"]}
                    gevraagd[(r["sleutel"], r["claim"])] = regel
                    f.write(json.dumps(regel, ensure_ascii=False) + "\n")
        wacht = sum(paarsleutel(gevraagd[(r["sleutel"], r["claim"])]["claim"],
                                gevraagd[(r["sleutel"], r["claim"])]["tekst"]) not in antwoord for r in nodig)
        terecht = {(r["sleutel"], r["claim"]) for r in nodig
                   if antwoord.get(paarsleutel(gevraagd[(r["sleutel"], r["claim"])]["claim"],
                                               gevraagd[(r["sleutel"], r["claim"])]["tekst"])) == 1}
        return terecht, wacht

    web.sort(key=lambda s: -s[2])
    teksten |= {s: t for s, t, _ in web}
    gelezen, keuze, nodig_vanaf, wachtend = 0, None, None, 0
    # Eén Haiku-ronde voor alles wat al gescoord is, in plaats van één per blok.
    al_gescoord = [("webtekst", s, t, None) for s, t, _ in web
                   if s in kandidaten and all((s, c) in scores for c, _ in kandidaten[s])]
    labels_klaar(rijen + rijen_van(al_gescoord))
    terecht, wachtend = labels_klaar(rijen)
    while keuze is None and gelezen < len(web) and not wachtend:
        blok = web[gelezen:gelezen + 1000]
        zonder = [best for s, _, best in blok if s not in kandidaten]
        if zonder:
            nodig_vanaf = round(min(best for _, _, best in blok), 4)
            break
        t0 = time.time()
        rijen += rijen_van([("webtekst", s, t, None) for s, t, _ in blok])
        gelezen += len(blok)
        onder = web[gelezen][2] if gelezen < len(web) else -1.0
        per = _per_stuk(zonder_terecht(rijen, terecht))
        drempels_bepaald = [_schoon(per, v, DREMPELS) for v in VLOEREN if v > web[gelezen - len(blok)][2]]
        vanaf = max([d for d in drempels_bepaald if d is not None], default=min(DREMPELS))
        terecht, wachtend = labels_klaar(rijen, vanaf)
        if wachtend:
            break
        keuze = beslist(zonder_terecht(rijen, terecht), onder)
        print(f"  webtekst {gelezen:,} van {len(web):,} (volledig boven {onder:.3f}) in {time.time() - t0:.0f} s;"
              f" keuze {keuze}", flush=True)
    onder = web[gelezen][2] if gelezen < len(web) else -1.0
    bepaald = [v for v in VLOEREN if v > onder]
    uit = {"gekozen": keuze if keuze is not None else None, "beslist": keuze is not None,
           "nodig_vanaf": nodig_vanaf, "wacht_op_haiku": wachtend, "terecht_uit_de_negatieven": len(terecht),
           "lezer": LEZER.resolve().name,
           "per_vloer_bepaald": {k: v for k, v in kies_drempels(zonder_terecht(rijen, terecht))["per_vloer"].items()
                                 if float(k) in bepaald},
           "webtekst_gelezen": gelezen, "webtekst_totaal": len(web), "volledig_boven": onder,
           "stukken": dict(collections.Counter(s for s, _, _, _ in vast)), "ontkrachtingen": len(ontkrachtingen)}
    (UIT / "keuze.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
    return uit


MOTOREN = {"zonder lezer": "config.toml", "lezer A": "data/zeef/config-lezer.toml",
           "lezer B": "data/zeef/config-lezer-b.toml"}


def _client(config_pad: str):  # pragma: no cover - het echte pad
    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.config import load_config

    config = load_config(config_pad)
    api.app.dependency_overrides[api.get_config] = lambda: config
    api.limiter.enabled = False
    return TestClient(api.app)


def tijd(n: int = 150) -> dict:  # pragma: no cover - meet het echte /resolve
    """De tijd per vraag (B41) op een vaste steekproef uit de ontwikkelhelft:
    `n` P2-artikelen (kop met inleiding) en `n` korte P1-teksten van twee
    zinnen, door drie motoren. Na de zeef draaien, nooit ernaast."""
    import random
    import sqlite3
    import time

    import numpy as np

    from doublecheck.netwerktoets import items
    from doublecheck.zeef import P2_MAP, UIT as ZEEF, helft

    p2 = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").split("\n") if r.strip()]
    artikelen = sorted({i.kop_inleiding for i in items(p2) if helft(f"zaak:{i.claim_id}") == "ontwikkel"})
    artikelen = random.Random(3011).sample(artikelen, min(n, len(artikelen)))
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    claim_van = dict(conn.execute("SELECT f.url, c.canonical_text FROM factcheck f JOIN claim c USING (claim_id)"))
    p1 = [json.loads(r) for r in (ZEEF / "factiz-lezer" / "P1.jsonl").read_text(encoding="utf-8").split("\n") if r.strip()]
    korte = kies_korte(sorted({claim_van[r["sleutel"][3:]] for r in p1
                               if r["helft"] == "ontwikkel" and r["sleutel"][3:] in claim_van}), n)
    uit = {"steekproef": {"artikelen": len(artikelen), "korte_teksten": len(korte), "zaad": 3011}}
    for naam, pad in MOTOREN.items():
        client = _client(pad)
        for t in artikelen[:3]:
            client.post("/resolve", json={"text": t})  # opwarmen: modellen laden
        uit[naam] = {}
        for soort, teksten in (("artikelen", artikelen), ("korte_teksten", korte)):
            duur = []
            for t in teksten:
                t0 = time.perf_counter()
                if client.post("/resolve", json={"text": t}).status_code != 200:
                    raise SystemExit(f"{naam}: /resolve gaf een fout; de meting stopt")
                duur.append(time.perf_counter() - t0)
            uit[naam][soort] = {"p50": round(float(np.percentile(duur, 50)), 3),
                                "p95": round(float(np.percentile(duur, 95)), 3)}
            print(f"{naam}, {soort}: {uit[naam][soort]}", flush=True)
    (UIT / "tijd.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
    return uit


def sheffield_toets(config_pad: str, naam: str) -> dict:  # pragma: no cover - het echte /resolve
    """De Sheffield-artikelen uit de toetshelft door `/resolve`, met de motor
    van `config_pad`; per artikel alleen sleutels en uitkomst op schijf
    (hervatbaar), en alleen totalen naar buiten."""
    from doublecheck.clustering import cluster_members
    from doublecheck.zeef import helft

    conn, _, _, _ = _context()
    pad = UIT / f"sheffield-toets-{naam}.jsonl"
    from doublecheck.artikellezer import _lees_jsonl

    klaar = {r["sleutel"] for r in _lees_jsonl(pad)}
    werk = [(i, k) for i, k in _sheffield_items() if helft(f"zaak:{i.claim_id}") == "toets"
            and f"S:{i.artikel}" not in klaar]
    print(f"{naam}: {len(werk):,} artikelen te doen", flush=True)
    client = _client(config_pad)
    with pad.open("a", encoding="utf-8") as f:
        for n, (item, klasse) in enumerate(werk, 1):
            antwoord = client.post("/resolve", json={"text": item.kop_inleiding})
            if antwoord.status_code != 200:
                raise SystemExit(f"{item.artikel}: /resolve {antwoord.status_code}; de controle stopt")
            d = antwoord.json()
            kandidaat = (d.get("claim") or {}).get("id")
            verwacht = cluster_members(conn, item.claim_id) | {item.claim_id}
            uitkomst = ("gevonden" if kandidaat in verwacht else "ander") if d["category"] == "matched" else \
                "verwant" if d["category"] == "related" else "niets"
            f.write(json.dumps({"sleutel": f"S:{item.artikel}", "klasse": klasse, "claim": item.claim_id,
                                "uitkomst": uitkomst, "kandidaat": kandidaat}) + "\n")
            if n % 200 == 0:
                f.flush()
                print(f"  {n:,} van {len(werk):,}", flush=True)
    uit = sheffield_uitslag(_lees_jsonl(pad))
    print(json.dumps(uit, indent=1), flush=True)
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse

    from doublecheck.artikellezer import _haiku

    parser = argparse.ArgumentParser(description="De tweede artikellezer (#30.11c)")
    parser.add_argument("stap", choices=("lesstof", "plan", "indienen", "ophalen", "uitschrijven", "trainen",
                                         "kandidaten", "kiezen", "keuze-plan", "keuze-indienen", "keuze-ophalen",
                                         "tijd", "sheffield-toets"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--vanaf", type=float, default=0.70, help="kandidaten: webtekst vanaf deze gelijkenis")
    parser.add_argument("--max", type=int, help="kandidaten: hoogstens zoveel stukken, de hoogste eerst")
    parser.add_argument("--config", default="data/zeef/config-lezer-b.toml", help="sheffield-toets: de motor")
    parser.add_argument("--naam", default="lezer-b", help="sheffield-toets: naam van de uitvoer")
    args = parser.parse_args()
    if args.stap == "lesstof":
        print(json.dumps(lesstof(), ensure_ascii=False, indent=1))
    elif args.stap == "trainen":
        print(json.dumps(trainen(), ensure_ascii=False, indent=1))
    elif args.stap == "kandidaten":
        print(json.dumps(kandidaten_maken(args.vanaf, args.max), ensure_ascii=False, indent=1))
    elif args.stap == "kiezen":
        print(json.dumps(kiezen(), ensure_ascii=False, indent=1))
    elif args.stap == "tijd":
        print(json.dumps(tijd(), ensure_ascii=False, indent=1))
    elif args.stap == "sheffield-toets":
        sheffield_toets(args.config, args.naam)
    elif args.stap.startswith("keuze-"):
        _haiku(args.stap.removeprefix("keuze-"), args.proef, KEUZE_HAIKU)
    else:
        _haiku(args.stap, args.proef, UIT)


if __name__ == "__main__":
    main()
