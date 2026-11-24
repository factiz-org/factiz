"""De zeef: de meetmachine per versie (PLAN #30.1, B33).

Versie 1 gaat de deur uit als Factiz in een grote, gemengde berg minstens 70%
vindt van wat al ontkracht is, bij een eenzijdige bovengrens (95%) van
hoogstens 1 vals alarm per 100.000 stukken. De opzet ligt vast in PLAN #30.1,
vóór de eerste meting:

- **P1 tekst**: de latere checks van een post die al gecheckt was, met het
  geheugen van die dag (de bron `post` van de terugkijktoets, zonder de
  checks met letterlijk dezelfde claimtekst). Via het zoekpad van
  `terugkijk`, anders vindt de latere check zichzelf.
- **P2 artikelen**: artikelen van desinformatiesites met hun ontkrachting
  (EUvsDisinfo, Sheffield, CC BY). Telt als kop met inleiding; de kop alleen
  wordt apart gemeld.
- **P3 beelden**: de beelden die rondgingen (M4FC, CC BY-SA), als upload.
- **N3 ware feiten**: de kern van de feitenbasis (B34), elk feit in meerdere
  formuleringen en talen. Een `matched` met een rood oordeel of *omstreden*
  naast een vastgesteld feit is vals alarm; *deels waar* en *onbewezen* staan
  apart (PLAN #30.1b). Geen labels nodig: het oordeel is wat een lezer ziet.
- **N1 webtekst**: de twee stiltepools; de stukken die zelf, of als
  bewering omgezet door de vraagvorm (#25.36), op of boven de laagste
  drempel komen, gaan door `/resolve`. Wat daaronder blijft, kan per
  constructie geen `matched` geven.

*Gevonden* is `matched` op de verwachte claim of een clustergenoot (bij P2
en P3 ook het bonnetje). Een `matched` op een andere claim leest een mens:
dezelfde bewering telt niet als gevonden en niet als vals, iets anders telt
als vals alarm. Het hoofdgetal is het ongewogen gemiddelde over P1, P2 en P3.

Elk stuk krijgt met een vaste hash een helft. Bij P1 tot P3 is dat de hash
van de verwachte claim, zodat twee stukken van dezelfde zaak nooit over de
helften verdeeld raken, ook niet tussen de sets; bij N1 die van het stuk. Van de toetshelft drukt de
machine alleen totalen af.

    python -m doublecheck.zeef meten --versie factiz-1 [--sets P1,P2,P3,N1]
    python -m doublecheck.zeef lezen --versie factiz-1
    python -m doublecheck.zeef tellen --versie factiz-1

Alles komt in `data/zeef/<versie>/`: per set de uitkomsten (geen
artikeltekst, geen beeld), en bij `tellen` `uitslag.json`. Labels staan in
`docs/steekproeven/30.1-zeef.json`.
"""

from __future__ import annotations

import collections
import hashlib
import json
import time
from pathlib import Path

from doublecheck.feitenbasis import TWIJFEL_N3, VALS_N3

SEED = 3001
LAT_VINDKANS = 0.70
LAT_VALS_PER_100K = 1.0
LAT_FOUT = 0.005  # precisie minstens 99,5% (B33, aangevuld 2026-10-17)
# Drukte: andere claims in de index met een gelijkenis van minstens 0,80 tot de
# verwachte claim; de emmers liggen vast vóór de meting (PLAN #30.1c).
DRUKTE_GELIJKENIS = 0.80
EMMERS = (("stil", 0, 2), ("druk", 3, 29), ("heel druk", 30, None))
P_SETS = ("P1", "P2", "P3")
SETS = (*P_SETS, "N1", "N3")
HELFTEN = ("ontwikkel", "toets")

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "zeef"
LABELS = WORTEL / "docs" / "steekproeven" / "30.1-zeef.json"
# Labels van #28.6 c op precies hetzelfde paar (vraag en treffer) gelden ook hier.
LABELS_TERUGKIJK = WORTEL / "docs" / "steekproeven" / "28.6c-ander-record.json"
FEED = WORTEL / "data" / "datacommons-claimreview.json"
NOTES = WORTEL / "data" / "communitynotes"
P2_MAP = WORTEL / "data" / "extern" / "euvsdisinfo-sheffield"
P3_MAP = WORTEL / "data" / "extern" / "m4fc"
POOLS = (WORTEL / "data" / "stiltetoets", WORTEL / "data" / "stiltetoets-vers")

_P1 = {"gevonden": "gevonden", "ander record": "ander", "verwant": "verwant",
       "tegenspraak": "niets", "niets": "niets"}
_RESOLVER = {"gevonden": "gevonden", "fout": "ander", "verwant": "verwant", "niets": "niets"}
_P_LABELS = ("zelfde", "anders")
_N_LABELS = ("terecht", "vals")


class Weigering(Exception):
    """De zeef telt niet, met de reden erbij."""


def helft(sleutel: str) -> str:
    """De vaste helft van een stuk: dezelfde in elke ronde en elke versie."""
    return "toets" if hashlib.sha256(f"{SEED}:{sleutel}".encode()).digest()[0] & 1 else "ontwikkel"


def uitkomst_p1(terugkijk: str) -> str:
    """De uitkomst van de terugkijktoets in de woorden van de zeef;
    `tegenspraak` telt als niets (PLAN #30.1)."""
    return _P1[terugkijk]


def uitkomst_resolver(beoordeeld: str) -> str:
    """De uitkomst van `ruwetest.beoordeel` in de woorden van de zeef."""
    return _RESOLVER[beoordeeld]


def emmer(aantal: int) -> str:
    for naam, laag, hoog in EMMERS:
        if aantal >= laag and (hoog is None or aantal <= hoog):
            return naam
    raise ValueError(aantal)


_GOED_N3 = {"waar", "deels-waar", "onbewezen", "zonder-oordeel"}


def _matched_en_fout(r: dict, labels: dict[str, str]) -> tuple[int, int]:
    """(1, 0) voor een juiste `matched`, (1, 1) voor een foute, (0, 0) als er
    geen `matched` was. Twijfel naast een feit telt niet als fout (#30.1b)."""
    u = r["uitkomst"]
    if r["set"] in P_SETS:
        if u == "gevonden":
            return 1, 0
        if u == "ander":
            return 1, int(labels[r["sleutel"]] == "anders")
        return 0, 0
    if r["set"] == "N1":
        return (1, int(labels[r["sleutel"]] == "vals")) if u == "matched" else (0, 0)
    if r["set"] == "N3":
        if u in VALS_N3:
            return 1, 1
        return (1, 0) if u in _GOED_N3 else (0, 0)
    return 0, 0


def _precisie(rijen: list[dict], labels: dict[str, str]) -> dict:
    from doublecheck.cijfers import _bovengrens

    paren = [_matched_en_fout(r, labels) for r in rijen]
    matched, fout = sum(m for m, _ in paren), sum(f for _, f in paren)
    return {"matched": matched, "fout": fout, "precisie": (matched - fout) / matched if matched else None,
            "bovengrens_fout": _bovengrens(fout, matched) if matched else None}


def haalt_de_lat(hoofdgetal: float, bovengrens_per_100k: float) -> bool:
    return hoofdgetal >= LAT_VINDKANS and bovengrens_per_100k <= LAT_VALS_PER_100K


def uitslag(regels: list[dict], n_per_set: dict[str, dict[str, int]], labels: dict[str, str]) -> dict:
    """Per helft de vindkans per set, het hoofdgetal en het vals alarm.

    `regels` zijn de uitkomsten van P1 tot P3 en van de N1-stukken die door
    `/resolve` gingen; `n_per_set[helft]["N1"]` is de hele webtekst van die
    helft. Weigert zolang een andere claim of een `matched` op webtekst geen
    label heeft."""
    from doublecheck.cijfers import _bovengrens

    ontbreekt = [r["sleutel"] for r in regels
                 if (r["set"] in P_SETS and r["uitkomst"] == "ander" and labels.get(r["sleutel"]) not in _P_LABELS)
                 or (r["set"] == "N1" and r["uitkomst"] == "matched" and labels.get(r["sleutel"]) not in _N_LABELS)]
    if ontbreekt:
        raise Weigering(f"{len(ontbreekt)} treffer(s) zonder label; label eerst in {LABELS.name}"
                        f" (`python -m doublecheck.zeef lezen`)")

    uit = {}
    for h in HELFTEN:
        eigen = [r for r in regels if r["helft"] == h]
        sets = {}
        for s in P_SETS:
            rijen = [r for r in eigen if r["set"] == s]
            if not rijen:
                continue
            c = collections.Counter(r["uitkomst"] for r in rijen)
            ander = [labels[r["sleutel"]] for r in rijen if r["uitkomst"] == "ander"]
            per_taal = collections.defaultdict(lambda: {"n": 0, "gevonden": 0})
            for r in rijen:
                per_taal[r.get("taal") or "?"]["n"] += 1
                per_taal[r.get("taal") or "?"]["gevonden"] += r["uitkomst"] == "gevonden"
            sets[s] = {"n": len(rijen), "gevonden": c["gevonden"], "verwant": c["verwant"], "niets": c["niets"],
                       "ander_zelfde": ander.count("zelfde"), "ander_anders": ander.count("anders"),
                       "vindkans": c["gevonden"] / len(rijen),
                       "per_taal": dict(sorted(per_taal.items(), key=lambda kv: -kv[1]["n"]))}
        compleet = all(s in sets for s in P_SETS)
        hoofdgetal = sum(sets[s]["vindkans"] for s in P_SETS) / len(P_SETS) if compleet else None

        n1 = [r for r in eigen if r["set"] == "N1"]
        n1_matched = [r for r in n1 if r["uitkomst"] == "matched"]
        n1_vals = sum(labels[r["sleutel"]] == "vals" for r in n1_matched)
        n3 = collections.Counter(r["uitkomst"] for r in eigen if r["set"] == "N3")
        n3_vals = sum(n for u, n in n3.items() if u in VALS_N3)
        vals = sum(d["ander_anders"] for d in sets.values()) + n1_vals + n3_vals
        berg = sum(d["n"] for d in sets.values()) + n_per_set.get(h, {}).get("N1", 0) + sum(n3.values())
        bovengrens = _bovengrens(vals, berg) * 100_000
        uit[h] = {
            "hoofdgetal": hoofdgetal,
            "sets": sets,
            "N1": {"n": n_per_set.get(h, {}).get("N1", 0), "door_resolve": len(n1), "matched": len(n1_matched),
                   "vals": n1_vals, "related": sum(r["uitkomst"] == "related" for r in n1)},
            "N3": {"n": sum(n3.values()), "rood": n3["rood"], "omstreden": n3["omstreden"],
                   "twijfel": sum(n for u, n in n3.items() if u in TWIJFEL_N3), "waar": n3["waar"],
                   "verwant": n3["verwant"], "niets": n3["niets"]},
            "vals_alarm": {"vals": vals, "berg": berg, "per_100k": vals / berg * 100_000 if berg else 0.0,
                           "bovengrens_per_100k": bovengrens},
            "lat": compleet and haalt_de_lat(hoofdgetal, bovengrens),
            "precisie": _precisie(eigen, labels),
        }
        positief = [r for r in eigen if r["set"] in P_SETS and "drukte" in r]
        if positief:
            per = {}
            for naam, _, _ in EMMERS:
                rijen = [r for r in positief if emmer(r["drukte"]) == naam]
                n = len(rijen)
                gevonden = sum(r["uitkomst"] == "gevonden" for r in rijen)
                per[naam] = {"n": n, "gevonden": gevonden, "vindkans": gevonden / n if n else None,
                             **_precisie(rijen, labels)}
            uit[h]["drukte"] = per
    # Nultolerantie op de kern (B33): over beide helften, alleen het totaal.
    kern = [r for r in regels if r["set"] == "N3" and r.get("bron", "kern") == "kern"]
    uit["kern"] = {"formuleringen": len(kern), "rood_of_omstreden": sum(r["uitkomst"] in VALS_N3 for r in kern)}
    return uit


def lezerdelen(regels: list[dict], labels: dict[str, str], n_n1: int, les_web: set[str]) -> dict:
    """De uitsplitsing van #30.11b, vastgelegd vóór de zeefrun van de lezer.

    De lezer leerde van het lesdeel van de ontwikkelhelft. Voor de
    beslisregel telt P2 daarom op het keuzedeel (`rechtermeting.deel` van de
    claim) en N1 zonder de webteksten uit de lesstof (`les_web`), uit teller
    én noemer; wat daar toch vals alarm geeft, staat apart. `n_n1` is de hele
    webtekst van de ontwikkelhelft. Alleen de ontwikkelhelft: de toetshelft
    blijft de controle, in totalen."""
    from doublecheck.rechtermeting import deel

    eigen = [r for r in regels if r["helft"] == "ontwikkel"]
    p2 = {}
    for d in ("keuze", "les"):
        rijen = [r for r in eigen if r["set"] == "P2" and deel(r["claim"]) == d]
        gevonden = sum(r["uitkomst"] == "gevonden" for r in rijen)
        p2[d] = {"n": len(rijen), "gevonden": gevonden, "vindkans": gevonden / len(rijen) if rijen else None,
                 "ander_anders": sum(r["uitkomst"] == "ander" and labels[r["sleutel"]] == "anders" for r in rijen)}
    vals = [r["sleutel"] for r in eigen
            if r["set"] == "N1" and r["uitkomst"] == "matched" and labels[r["sleutel"]] == "vals"]
    les_eigen = {s for s in les_web if helft(s) == "ontwikkel"}
    return {"P2": p2, "N1": {"n": n_n1 - len(les_eigen), "vals": sum(s not in les_web for s in vals),
                             "vals_in_lesstof": sum(s in les_web for s in vals), "lesstof": len(les_eigen)}}


def verslag(uit: dict) -> str:
    """Wat de machine afdrukt: per helft alleen totalen, nooit een stuk."""
    regels = []
    for h in HELFTEN:
        d = uit[h]
        sets = d["sets"]
        hoofd = (f"{d['hoofdgetal']:.1%}" if d["hoofdgetal"] is not None
                 else f"- (ontbreekt {', '.join(s for s in P_SETS if s not in sets)})")
        v = d["vals_alarm"]
        regels.append(f"{h}: hoofdgetal {hoofd}; vals alarm {v['vals']} op {v['berg']:,},"
                      f" {v['per_100k']:.2f} per 100.000, bovengrens {v['bovengrens_per_100k']:.2f};"
                      f" lat {'gehaald' if d['lat'] else 'niet gehaald'}")
        for s, t in sets.items():
            regels.append(f"  {s}: n {t['n']:,} · gevonden {t['gevonden']:,} ({t['vindkans']:.1%}) · verwant"
                          f" {t['verwant']:,} · andere claim {t['ander_zelfde']} zelfde, {t['ander_anders']} anders"
                          f" · niets {t['niets']:,}")
        p = d.get("precisie") or {}
        if p.get("matched"):
            regels.append(f"  precisie: {p['matched'] - p['fout']} van {p['matched']} keer matched juist"
                          f" ({p['precisie']:.1%}), bovengrens fout {p['bovengrens_fout']:.1%};"
                          f" lat hoogstens {LAT_FOUT:.1%}: {'gehaald' if p['bovengrens_fout'] <= LAT_FOUT else 'niet gehaald'}")
        for naam, e in (d.get("drukte") or {}).items():
            vind = f"{e['vindkans']:.1%}" if e["vindkans"] is not None else "-"
            prec = f"{e['precisie']:.1%}" if e["precisie"] is not None else "-"
            regels.append(f"  drukte {naam}: n {e['n']:,} · gevonden {e['gevonden']} ({vind}) · matched {e['matched']},"
                          f" fout {e['fout']} (precisie {prec})")
        n1 = d["N1"]
        regels.append(f"  N1: n {n1['n']:,} · door /resolve {n1['door_resolve']:,} · matched {n1['matched']}"
                      f" (vals {n1['vals']}) · related {n1['related']}")
        n3 = d["N3"]
        if n3["n"]:
            regels.append(f"  N3: n {n3['n']:,} · rood {n3['rood']} · omstreden {n3['omstreden']} · twijfel"
                          f" {n3['twijfel']} · waar {n3['waar']} · verwant {n3['verwant']} · niets {n3['niets']}")
    if uit.get("kern", {}).get("formuleringen"):
        k = uit["kern"]
        regels.append(f"kern: {k['rood_of_omstreden']} keer rood of omstreden op {k['formuleringen']} formuleringen"
                      f" ({'gehaald' if not k['rood_of_omstreden'] else 'niet gehaald'}: nultolerantie, B33)")
    return "\n".join(regels)


# --- de meting --------------------------------------------------------------

def lees_labels(regels: list[dict]) -> dict[str, str]:
    """De labels van #30.1, aangevuld met die van #28.6 c op hetzelfde paar."""
    labels = {}
    if LABELS_TERUGKIJK.exists():
        oud = {(r["vraag"], r["claim"]): r["label"]
               for r in json.loads(LABELS_TERUGKIJK.read_text(encoding="utf-8"))["labels"] if r["bron"] == "post"}
        for r in regels:
            paar = (r["sleutel"].removeprefix("P1:"), r.get("kandidaat"))
            if r["set"] == "P1" and paar in oud:
                labels[r["sleutel"]] = oud[paar]
    if LABELS.exists():
        labels.update({r["sleutel"]: r["label"] for r in json.loads(LABELS.read_text(encoding="utf-8"))["labels"]})
    return labels


def _lees(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def _antwoord(antwoord) -> dict:
    return {"kandidaat": (antwoord.get("claim") or {}).get("id"), "gelijkenis": antwoord.get("similarity")}


def _met_rechter(doe) -> tuple:  # pragma: no cover - met het echte pad
    """Een verzoek aan /resolve, met wat de rechter las (#30.3): claim-id's,
    gelijkenis en score, nooit tekst. Leeg met de rechter uit."""
    from doublecheck import rechter

    gezien = []
    rechter.waarnemer = gezien.append
    try:
        antwoord = doe()
    finally:
        rechter.waarnemer = None
    return antwoord, ({"gelezen": [list(g) for g in gezien[-1]]} if gezien else {})


def _p1(conn, config, map_: Path) -> None:  # pragma: no cover - op de productiedatabase
    from doublecheck import terugkijk

    terugkijk.UIT = map_ / "terugkijk"
    terugkijk._meten(conn, config, FEED, NOTES)
    regels = []
    for r in _lees(terugkijk.UIT / "uitkomsten.jsonl"):
        if r["bron"] != "post" or r["zelfde_tekst"]:
            continue
        regels.append({"set": "P1", "sleutel": f"P1:{r['vraag']}", "helft": helft(f"zaak:{min(r['doelen'])}"),
                       "taal": r["taal"], "uitkomst": uitkomst_p1(r["uitkomst"]), "kandidaat": r["kandidaat"],
                       "gelijkenis": r["gelijkenis"], "doelen": r["doelen"],
                       **({"gelezen": r["gelezen"]} if "gelezen" in r else {})})
    (map_ / "P1.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels),
                                   encoding="utf-8")


def _p2(conn, client, map_: Path) -> None:  # pragma: no cover
    from doublecheck.clustering import cluster_members
    from doublecheck.netwerktoets import items
    from doublecheck.ruwetest import antwoord_of_fout, beoordeel

    artikelen = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines()
                 if r.strip()]
    pad = map_ / "P2.jsonl"
    gedaan = {r["sleutel"] for r in _lees(pad)}
    toets = items(artikelen)
    with pad.open("a", encoding="utf-8") as uit:
        for n, item in enumerate(toets, 1):
            sleutel = f"P2:{item.artikel}#{item.claim_id}"
            if sleutel in gedaan:
                continue
            verwacht = cluster_members(conn, item.claim_id) | {item.claim_id}
            antwoord, gelezen = _met_rechter(lambda: client.post("/resolve", json={"text": item.kop_inleiding}))
            met = antwoord_of_fout(antwoord)
            kop = antwoord_of_fout(client.post("/resolve", json={"text": item.kop}))
            uit.write(json.dumps({
                "set": "P2", "sleutel": sleutel, "helft": helft(f"zaak:{item.claim_id}"), "taal": item.taal,
                "uitkomst": uitkomst_resolver(beoordeel(met, item.bonnetje, verwacht)),
                "kop": uitkomst_resolver(beoordeel(kop, item.bonnetje, verwacht)),
                "claim": item.claim_id, **_antwoord(met), **gelezen}, ensure_ascii=False) + "\n")
            if n % 100 == 0:
                uit.flush()
                print(f"  P2 {n}/{len(toets)}", flush=True)


def _p3(conn, client, map_: Path) -> dict:  # pragma: no cover
    from doublecheck.api import MAX_IMAGE_BYTES
    from doublecheck.clustering import cluster_members
    from doublecheck.ruwetest import antwoord_of_fout, beoordeel, m4fc_items

    pad = map_ / "P3.jsonl"
    gedaan = {r["sleutel"] for r in _lees(pad)}
    beelden = m4fc_items(P3_MAP)
    te_groot = 0
    with pad.open("a", encoding="utf-8") as uit:
        for n, item in enumerate(beelden, 1):
            sleutel = f"P3:{item.pad.stem}"
            if sleutel in gedaan:
                continue
            inhoud = item.pad.read_bytes()
            if len(inhoud) > MAX_IMAGE_BYTES:
                te_groot += 1
                continue
            ruw, gelezen = _met_rechter(
                lambda: client.post("/resolve", files={"image": ("beeld", inhoud, "application/octet-stream")}))
            antwoord = antwoord_of_fout(ruw)
            del inhoud
            verwacht = cluster_members(conn, item.claim_id) | {item.claim_id}
            uit.write(json.dumps({
                "set": "P3", "sleutel": sleutel, "helft": helft(f"zaak:{item.claim_id}"), "taal": item.taal,
                "uitkomst": uitkomst_resolver(beoordeel(antwoord, item.url, verwacht)), "claim": item.claim_id,
                **_antwoord(antwoord), **gelezen}, ensure_ascii=False) + "\n")
            if n % 100 == 0:
                uit.flush()
                print(f"  P3 {n}/{len(beelden)}", flush=True)
    return {"beelden": len(beelden), "te_groot": te_groot}


def _n1(config, client, map_: Path) -> dict:  # pragma: no cover
    import os

    import numpy as np

    from doublecheck.embedding import fingerprint_texts
    from doublecheck.stiltetoets import lees_db, ondergrens, voorselectie
    from doublecheck.variantenbatch import lees_regels, lees_vectoren
    from doublecheck.vraagvorm import als_bewering

    versie = config.model_versions.text_embedding
    grens = ondergrens(config.thresholds)
    pad = map_ / "N1.jsonl"
    gedaan = {r["sleutel"] for r in _lees(pad)}
    n_per_helft = collections.Counter()
    for pool in POOLS:
        rijen = lees_regels(pool)
        _, matrix = lees_vectoren(pool, versie)
        if len(matrix) < len(rijen):
            raise Weigering(f"{pool}: {len(matrix)} van {len(rijen)} stukken embed met {versie}")
        n_per_helft.update(helft(f"N1:{pool.name}:{r['claim_id']}") for r in rijen)
        hoogste_pad = map_ / f"N1-{pool.name}-hoogste.npy"
        if hoogste_pad.exists():
            hoogste = np.load(hoogste_pad)
        else:
            hoogste, _ = voorselectie(lees_db(os.environ.get("DOUBLECHECK_DB", "doublecheck.db")), matrix, versie,
                                      grens)
            np.save(hoogste_pad, hoogste)
        del matrix
        boven = set(np.nonzero(hoogste >= grens)[0].tolist())
        # Een vraag zoekt ook als bewering (#25.36), per claim de hoogste van de
        # twee: dezelfde voorselectie op de omgezette tekst. Blijven beide
        # onder de grens, dan kan het antwoord per constructie alleen `none` zijn.
        omgezet = {i: als_bewering(r["varianten"][0]["tekst"]) for i, r in enumerate(rijen)}
        vraag = sorted(i for i, t in omgezet.items() if t != rijen[i]["varianten"][0]["tekst"])
        vraag_pad = map_ / f"N1-{pool.name}-hoogste-vraag.npy"
        if vraag_pad.exists():
            hoogste_vraag = np.load(vraag_pad)
        else:
            vectoren = np.vstack([f.vector for start in range(0, len(vraag), 256)
                                  for f in fingerprint_texts([omgezet[i] for i in vraag[start:start + 256]], versie)])
            hoogste_vraag, _ = voorselectie(lees_db(os.environ.get("DOUBLECHECK_DB", "doublecheck.db")), vectoren,
                                            versie, grens)
            np.save(vraag_pad, hoogste_vraag)
        vraag_boven = {vraag[j] for j in np.nonzero(hoogste_vraag >= grens)[0].tolist()}
        # Een artikel per zin (#30.11): dan zoekt ook elke zin, en elke vraag
        # onder de zinnen als bewering. Dezelfde voorselectie per zin, de
        # hoogste per stuk; ook dit is per constructie alles wat iets kan geven.
        zin_boven: set[int] = set()
        if config.artikel.per_zin:
            zinnen_pad = map_ / f"N1-{pool.name}-hoogste-zinnen.npy"
            if zinnen_pad.exists():
                hoogste_zinnen = np.load(zinnen_pad)
            else:
                hoogste_zinnen = _hoogste_per_zin(rijen, versie, grens, map_ / f"N1-{pool.name}-zinnen")
                np.save(zinnen_pad, hoogste_zinnen)
            zin_boven = set(np.nonzero(hoogste_zinnen >= grens)[0].tolist())
        # De artikellezer (#30.11b) leest webtekst van meerdere eenheden vanaf
        # `artikel_vloer`. In batch op de grafische chip voorgelezen; wat tot
        # op een marge de lezerdrempel haalt, gaat door het echte /resolve.
        lezer_boven: set[int] = set()
        if config.artikellezer.aan:
            lezer_boven = _lezer_boven(rijen, pool.name, config, map_)
        kandidaten = sorted(boven | vraag_boven | zin_boven | lezer_boven)
        print(f"N1 {pool.name}: {len(rijen):,} stukken; {len(boven):,} op of boven {grens:.2f}; van de"
              f" {len(vraag):,} waar de vraagvorm iets doet {len(vraag_boven):,} als bewering;"
              + (f" per zin {len(zin_boven):,};" if config.artikel.per_zin else "")
              + (f" door de lezer {len(lezer_boven):,};" if config.artikellezer.aan else "")
              + f" {len(kandidaten):,} door /resolve", flush=True)
        with pad.open("a", encoding="utf-8") as uit:
            for n, i in enumerate(kandidaten, 1):
                sleutel = f"N1:{pool.name}:{rijen[i]['claim_id']}"
                if sleutel in gedaan:
                    continue
                antwoord, gelezen = _met_rechter(
                    lambda: client.post("/resolve", json={"text": rijen[i]["varianten"][0]["tekst"]}))
                if antwoord.status_code != 200:
                    raise RuntimeError(f"{sleutel}: resolve {antwoord.status_code}; de run stopt")
                d = antwoord.json()
                uit.write(json.dumps({"set": "N1", "sleutel": sleutel, "helft": helft(sleutel),
                                      "taal": rijen[i]["taal"], "uitkomst": d["category"],
                                      "hoogste": round(float(hoogste[i]), 4), **_antwoord(d), **gelezen},
                                     ensure_ascii=False) + "\n")
                if n % 500 == 0:
                    uit.flush()
                    print(f"  N1 {pool.name} {n}/{len(kandidaten)}", flush=True)
    return {"N1": dict(n_per_helft)}


def _vectoren_gpu(teksten: list[str], versie: str):  # pragma: no cover - met het model
    """Vectoren voor een meting, op de grafische chip als die er is (B37):
    zelfde model, normalisatie en lengtegrens als `fingerprint_texts`. Op
    1.000 zinnen uit de stiltepool hoogstens 7e-7 verschil per getal en
    cosinus 1,000000 met de processor, bij twee keer de snelheid (#30.11).
    Alleen voor de voorselectie, die een marge onder de laagste drempel
    houdt; de resolver zelf rekent op de processor."""
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    from doublecheck.embedding import _modelspec, normaliseer_voor_embedding

    global _GPU_MODEL
    if _GPU_MODEL is None:
        naam, revisie, _ = _modelspec(versie)
        apparaat = "mps" if torch.backends.mps.is_available() else "cpu"
        _GPU_MODEL = SentenceTransformer(naam, revision=revisie, device=apparaat,
                                         model_kwargs={"dtype": torch.float32})
        _GPU_MODEL.max_seq_length = min(_GPU_MODEL.max_seq_length or 512, 512)
    return np.asarray(_GPU_MODEL.encode([normaliseer_voor_embedding(t) for t in teksten], batch_size=64,
                                        normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)


_GPU_MODEL = None
_PORTIE_ZINNEN = 20_000
# Na elke portie op de grafische chip even niets, zodat die afkoelt; de
# hittewacht pauzeert de hele run als de Mac toch warm wordt (PO 2026-10-21).
GPU_PAUZE = 3


def _hoogste_per_zin(rijen: list[dict], versie: str, grens: float, deelmap: Path):  # pragma: no cover
    """Per stuk de hoogste gelijkenis van zijn zinnen (en van de vragen onder
    hen als bewering) met alle claims en varianten; -1 voor een stuk van één
    eenheid. Hervatbaar: per portie van 20.000 zinnen een bestand in
    `deelmap`, een afgebroken run gaat verder bij de eerste die ontbreekt."""
    import os

    import numpy as np

    from doublecheck.stiltetoets import lees_db, voorselectie
    from doublecheck.vraagvorm import als_bewering
    from doublecheck.zinnen import eenheden

    eigenaar, teksten = [], []
    for i, rij in enumerate(rijen):
        for zin in eenheden(rij["varianten"][0]["tekst"])[1:]:
            for vorm in dict.fromkeys((zin, als_bewering(zin))):
                eigenaar.append(i)
                teksten.append(vorm)
    deelmap.mkdir(parents=True, exist_ok=True)
    conn = lees_db(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    delen = []
    for k, start in enumerate(range(0, len(teksten), _PORTIE_ZINNEN)):
        deel = deelmap / f"deel-{k:03d}.npy"
        if not deel.exists():
            h, _ = voorselectie(conn, _vectoren_gpu(teksten[start:start + _PORTIE_ZINNEN], versie), versie, grens)
            np.save(deel, h)
            print(f"  per zin {deelmap.name}: {min(start + _PORTIE_ZINNEN, len(teksten)):,} van {len(teksten):,}",
                  flush=True)
            time.sleep(GPU_PAUZE)
        delen.append(np.load(deel))
    per_zin = np.concatenate(delen) if delen else np.empty(0, dtype=np.float32)
    hoogste = np.full(len(rijen), -1.0, dtype=np.float32)
    np.maximum.at(hoogste, np.asarray(eigenaar, dtype=np.int64), per_zin)
    return hoogste


LEZER_MARGE = 0.05


def _chipgeheugen() -> str:  # pragma: no cover - met de grafische chip
    """Wat het proces op de grafische chip vasthoudt, voor de logregel: de
    bewaker stopt de run als dit groeit (2026-10-22, lezer B: 17 GB)."""
    import torch

    if not torch.backends.mps.is_available():
        return ""
    return f", grafische chip {torch.mps.driver_allocated_memory() / 2**30:.1f} GB"


def _vrij() -> None:  # pragma: no cover - met de modellen
    """De zoekindex en de modellen op de grafische chip loslaten."""
    import gc

    import torch

    from doublecheck import artikellezer

    global _GPU_MODEL, _LEZER_MPS
    artikellezer._MATRICES.clear()
    _GPU_MODEL, _LEZER_MPS = None, None
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


_LEZER_MPS = None


def _lezer_scores(paren: list[tuple[str, str]], pad: str) -> list[float]:  # pragma: no cover - met het model
    """Scores van de artikellezer op de grafische chip, het model één keer
    geladen (claim eerst, 384 tokens), zoals bij de keuze (#30.11c)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck.artikellezer import _apparaat

    global _LEZER_MPS
    if _LEZER_MPS is None:
        _LEZER_MPS = (AutoTokenizer.from_pretrained(pad),
                      AutoModelForSequenceClassification.from_pretrained(pad).to(_apparaat()).eval())
    tokenizer, model = _LEZER_MPS
    # Op lengte gesorteerd: minder opvulling per batch, dezelfde scores.
    volgorde = sorted(range(len(paren)), key=lambda j: len(paren[j][0]) + len(paren[j][1]))
    uit = [0.0] * len(paren)
    with torch.no_grad():
        for start in range(0, len(volgorde), 16):
            deel = volgorde[start:start + 16]
            invoer = tokenizer([paren[j][0] for j in deel], [paren[j][1] for j in deel], return_tensors="pt",
                               truncation=True, max_length=384, padding=True).to(model.device)
            for j, s in zip(deel, torch.sigmoid(model(**invoer).logits.view(-1).float()).cpu().tolist()):
                uit[j] = s
    # Elke batch heeft een andere lengte; zonder vrijgeven groeit de cache (zie `_kandidaten`).
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    return uit


def _lezer_boven(rijen: list[dict], pool: str, config, map_: Path) -> set[int]:  # pragma: no cover
    """De stukken die de artikellezer `matched` zou kunnen geven: twee of meer
    eenheden, een kandidaat vanaf `artikel_vloer`, en een voorgelezen score
    vanaf `artikel_zelfde` min `LEZER_MARGE`. Welke stukken een kandidaat
    hebben, komt uit de voorfilter per eenheid van `factiz-artikel` (gemaakt
    vóór de vage claims de index uit gingen, dus een ruime bovengrens).

    In drie stappen, zodat er steeds maar één model of de index in het
    geheugen staat (PO 2026-10-22: eerst de zuinigste aanpak): eerst de
    vectoren van de eenheden met bge-m3 (per blok op schijf, daarna weg), dan
    de kandidaten uit de index (`N1-<pool>-kandidaten.jsonl`), dan de lezer
    (`N1-<pool>-lezer.jsonl`). Alles per blok of stuk op schijf, dus hervatbaar."""
    import os
    import shutil

    import numpy as np

    from doublecheck.artikellezer import _eenheidvectoren, _kandidaten_uit
    from doublecheck.stiltetoets import lees_db
    from doublecheck.zinnen import eenheden

    bron = WORTEL / "data" / "zeef" / "factiz-artikel"
    best = np.maximum(np.load(bron / f"N1-{pool}-hoogste.npy"), np.load(bron / f"N1-{pool}-hoogste-zinnen.npy"))
    meer = np.load(bron / f"N1-{pool}-hoogste-zinnen.npy") > -1
    te_lezen = np.nonzero(meer & (best >= config.thresholds.artikel_vloer))[0].tolist()
    score_pad, kand_pad = map_ / f"N1-{pool}-lezer.jsonl", map_ / f"N1-{pool}-kandidaten.jsonl"
    klaar = {r["i"]: r["score"] for r in _lees(score_pad)}
    kandidaten = {r["i"]: r["kandidaten"] for r in _lees(kand_pad)}
    rest = [i for i in te_lezen if i not in klaar]
    nodig = [i for i in rest if i not in kandidaten]
    print(f"  lezer {pool}: {len(te_lezen):,} stukken vanaf {config.thresholds.artikel_vloer}, nog {len(rest):,}"
          f" te lezen, waarvan {len(nodig):,} zonder kandidaten", flush=True)
    conn = lees_db(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    versie = config.model_versions.text_embedding
    blokken = [nodig[start:start + 1000] for start in range(0, len(nodig), 1000)]
    # Stap 1a: de eenheden embedden, alleen bge-m3. Met de index erbij hield
    # het proces ~10 GB vast en swapte de Mac (2026-10-22, lezer B).
    vecmap = map_ / f"N1-{pool}-vectoren"
    vecmap.mkdir(exist_ok=True)
    for b, deel in enumerate(blokken):
        pad_v = vecmap / f"{deel[0]}-{len(deel)}.npy"
        if pad_v.exists():
            continue
        t0 = time.time()
        _, vectoren = _eenheidvectoren([rijen[i]["varianten"][0]["tekst"] for i in deel], versie)
        np.save(vecmap / "deel.npy", vectoren)
        (vecmap / "deel.npy").rename(pad_v)
        print(f"  vectoren {pool}: {min((b + 1) * 1000, len(nodig)):,} van {len(nodig):,}"
              f" in {time.time() - t0:.0f} s{_chipgeheugen()}", flush=True)
        time.sleep(GPU_PAUZE)
    _vrij()
    # Stap 1b: de kandidaten, alleen de index.
    with kand_pad.open("a", encoding="utf-8") as uit:
        for b, deel in enumerate(blokken):
            t0 = time.time()
            per_tekst = [eenheden(rijen[i]["varianten"][0]["tekst"]) for i in deel]
            lijsten = _kandidaten_uit(per_tekst, np.load(vecmap / f"{deel[0]}-{len(deel)}.npy"), conn, versie,
                                      k=config.artikellezer.diepte, vloer=config.thresholds.artikel_vloer)
            for i, lijst in zip(deel, lijsten):
                kandidaten[i] = [[c, round(g, 4)] for c, g, _, _ in lijst]
                uit.write(json.dumps({"i": i, "kandidaten": kandidaten[i]}) + "\n")
            uit.flush()
            print(f"  kandidaten {pool}: {min((b + 1) * 1000, len(nodig)):,} van {len(nodig):,}"
                  f" in {time.time() - t0:.0f} s{_chipgeheugen()}", flush=True)
            time.sleep(GPU_PAUZE)
    _vrij()
    shutil.rmtree(vecmap)
    # Stap 2: de lezer, alleen.
    tekst = {r[0]: r[1] for r in conn.execute("SELECT claim_id, canonical_text FROM claim")}
    pad = str(Path(config.artikellezer.pad).resolve())
    with score_pad.open("a", encoding="utf-8") as uit:
        for start in range(0, len(rest), 1000):
            t0 = time.time()
            deel = rest[start:start + 1000]
            paren = [(i, c) for i in deel for c, _ in kandidaten[i]]
            scores = _lezer_scores([(tekst[c], rijen[i]["varianten"][0]["tekst"]) for i, c in paren], pad) if paren else []
            hoogste: dict[int, float] = {}
            for (i, _), s in zip(paren, scores):
                hoogste[i] = max(s, hoogste.get(i, 0.0))
            for i in deel:
                klaar[i] = round(hoogste.get(i, 0.0), 5)
                uit.write(json.dumps({"i": i, "score": klaar[i]}) + "\n")
            uit.flush()
            print(f"  lezer {pool}: {min(start + 1000, len(rest)):,} van {len(rest):,} in {time.time() - t0:.0f} s"
                  f"{_chipgeheugen()}", flush=True)
            time.sleep(GPU_PAUZE)
    _vrij()
    return {i for i in te_lezen if klaar[i] >= config.thresholds.artikel_zelfde - LEZER_MARGE}


def _n3(map_: Path) -> dict:  # pragma: no cover
    from doublecheck.feitenbasis import door_resolver, lees_kern, lees_paren, lees_register, n3_items, problemen_kern

    kern = lees_kern()
    problemen = problemen_kern(kern, lees_register())
    if problemen:
        raise Weigering(f"de kern volgt de regel van B34 niet ({len(problemen)} problemen)")
    regels = door_resolver(n3_items(kern, lees_paren()))
    (map_ / "N3.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels),
                                   encoding="utf-8")
    return {"feiten": len(kern), "stukken": len(regels), "kern": sum(r["bron"] == "kern" for r in regels)}


def meten(versie: str, sets: list[str], db: str, config_pad: str | None = None) -> None:  # pragma: no cover
    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.config import load_config
    from doublecheck.feitenbasis import motor_van
    from doublecheck.storage import connect

    # Een andere config (de rechter aan, #30.3) zonder config.toml te raken:
    # dezelfde config voor de terugkijkstap en voor het echte /resolve.
    config = load_config(config_pad)
    api.app.dependency_overrides[api.get_config] = lambda: config
    map_ = UIT / versie
    map_.mkdir(parents=True, exist_ok=True)
    # Per set een eigen klaar-bestand, zodat twee processen naast elkaar kunnen meten.
    motor = motor_van(config)
    motor_pad = map_ / "motor.json"
    if motor_pad.exists() and json.loads(motor_pad.read_text(encoding="utf-8")) != motor:
        raise Weigering(f"{map_} is gemeten met een andere motor; kies een andere --versie")
    motor_pad.write_text(json.dumps(motor, ensure_ascii=False, indent=1), encoding="utf-8")
    conn = connect(db)
    # Het echte pad zonder de opstartstap (die ruimt op) en zonder de per-IP-grens.
    api.limiter.enabled = False
    client = TestClient(api.app)
    for s in sets:
        klaar = map_ / f"{s}.klaar.json"
        if klaar.exists():
            print(f"{s}: al klaar", flush=True)
            continue
        print(f"{s}: meten", flush=True)
        if s == "P1":
            _p1(conn, config, map_)
            info = {}
        elif s == "P2":
            _p2(conn, client, map_)
            info = {}
        elif s == "P3":
            info = _p3(conn, client, map_)
        elif s == "N3":
            info = _n3(map_)
        else:
            info = _n1(config, client, map_)
        klaar.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")


def verwachte_claim(regel: dict) -> str | None:
    """De claim waar een positief stuk om draait: bij P1 de laagste van de
    doelen, bij P2 en P3 de claim van de zaak."""
    if regel["set"] == "P1":
        return min(regel["doelen"]) if regel.get("doelen") else None
    return regel.get("claim")


def drukte_meten(versie: str, db: str) -> dict[str, int]:  # pragma: no cover - op de productiedatabase
    """Per verwachte claim het aantal andere claims in de index (dezelfde
    matrix als de resolver) met een gelijkenis vanaf DRUKTE_GELIJKENIS."""
    import numpy as np

    from doublecheck.config import load_config
    from doublecheck.search import _tekstmatrix
    from doublecheck.stiltetoets import lees_db

    map_ = UIT / versie
    claims = sorted({c for r in _alle_regels(map_) if r["set"] in P_SETS for c in [verwachte_claim(r)] if c})
    ids, matrix = _tekstmatrix(lees_db(db), load_config().model_versions.text_embedding)
    plek = {c: i for i, c in enumerate(ids)}
    uit = {}
    for c in claims:
        if c not in plek:
            continue
        gelijkenis = matrix @ matrix[plek[c]]
        uit[c] = int((gelijkenis >= DRUKTE_GELIJKENIS).sum()) - 1
    (map_ / "drukte.json").write_text(json.dumps(uit, ensure_ascii=False), encoding="utf-8")
    return uit


def _alle_regels(map_: Path) -> list[dict]:
    regels = [r for s in SETS for r in _lees(map_ / f"{s}.jsonl")]
    pad = map_ / "drukte.json"
    if pad.exists():
        drukte = json.loads(pad.read_text(encoding="utf-8"))
        for r in regels:
            if r["set"] in P_SETS and verwachte_claim(r) in drukte:
                r["drukte"] = drukte[verwachte_claim(r)]
    return regels


def _te_labelen(regels: list[dict], labels: dict[str, str]) -> list[dict]:
    return [r for r in regels
            if ((r["set"] in P_SETS and r["uitkomst"] == "ander") or (r["set"] == "N1" and r["uitkomst"] == "matched"))
            and r["sleutel"] not in labels]


def lezen(versie: str, db: str) -> None:  # pragma: no cover - drukt teksten af om te labelen, schrijft niets
    import sqlite3

    regels = _alle_regels(UIT / versie)
    open_ = _te_labelen(regels, lees_labels(regels))
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tekst = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    kop = {}
    if any(r["set"] == "P2" for r in open_):
        from doublecheck.netwerktoets import items

        artikelen = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines()
                     if r.strip()]
        kop = {f"P2:{i.artikel}#{i.claim_id}": i.kop_inleiding for i in items(artikelen)}
    stukken = {}
    if any(r["set"] == "N1" for r in open_):
        from doublecheck.variantenbatch import lees_regels

        for pool in POOLS:
            stukken.update({f"N1:{pool.name}:{r['claim_id']}": r["varianten"][0]["tekst"] for r in lees_regels(pool)})
    for r in open_:
        print(f"\n[{r['set']} · {r['helft']}] {r['sleutel']} -> {r['kandidaat']} ({r['gelijkenis']})")
        if r["set"] == "P1":
            print(f"  VRAAG: {tekst.get(_claim_van_check(conn, r['sleutel'][3:]), '?')[:400]}")
            for d in r["doelen"][:2]:
                print(f"  DOEL: {tekst.get(d, '?')[:300]}")
        elif r["set"] == "P2":
            print(f"  ARTIKEL: {kop.get(r['sleutel'], '?')[:500]}")
            print(f"  DOEL: {tekst.get(r['claim'], '?')[:300]}")
        elif r["set"] == "P3":
            print(f"  BEELD: {P3_MAP / 'beelden'}/{r['sleutel'][3:]}.*")
            print(f"  DOEL: {tekst.get(r['claim'], '?')[:300]}")
        else:
            print(f"  STUK: {stukken.get(r['sleutel'], '?')[:500]}")
        print(f"  GEVONDEN: {tekst.get(r['kandidaat'], '?')[:300]}")
    print(f"\n{len(open_)} te labelen in {LABELS}")


def _claim_van_check(conn, url: str) -> str | None:  # pragma: no cover
    rij = conn.execute("SELECT claim_id FROM factcheck WHERE url = ?", (url,)).fetchone()
    return rij[0] if rij else None


def tellen(versie: str) -> dict:  # pragma: no cover - leest de uitvoer van meten
    map_ = UIT / versie
    ontbreekt = [s for s in SETS if not (map_ / f"{s}.klaar.json").exists()]
    if ontbreekt:
        raise Weigering(f"nog niet gemeten: {', '.join(ontbreekt)}")
    klaar = {s: json.loads((map_ / f"{s}.klaar.json").read_text(encoding="utf-8")) for s in SETS}
    regels = _alle_regels(map_)
    n_per_set = {h: {"N1": klaar["N1"]["N1"].get(h, 0)} for h in HELFTEN}
    uit = uitslag(regels, n_per_set, lees_labels(regels))
    uit["motor"] = json.loads((map_ / "motor.json").read_text(encoding="utf-8"))
    uit["overgeslagen"] = {"P3_te_groot": klaar["P3"].get("te_groot", 0), "P3_beelden": klaar["P3"].get("beelden")}
    uit["P2_kop_alleen"] = {h: collections.Counter(r["kop"] for r in regels if r["set"] == "P2" and r["helft"] == h)
                            for h in HELFTEN}
    from doublecheck.artikellezer import webtekst_in_lesstof

    les_web = webtekst_in_lesstof()
    if uit["motor"].get("artikellezer", {}).get("model", "").startswith("lezer-b"):
        from doublecheck.lezerb import webtekst_hard

        les_web |= webtekst_hard()
    if les_web:
        uit["lezerdelen"] = lezerdelen(regels, lees_labels(regels), n_per_set["ontwikkel"]["N1"], les_web)
    (map_ / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(verslag(uit))
    for h in HELFTEN:
        print(f"P2 kop alleen, {h}: {dict(uit['P2_kop_alleen'][h])}")
    if "lezerdelen" in uit:
        d = uit["lezerdelen"]
        print("ontwikkel, de lezing van #30.11b (de lezer leerde van het lesdeel):")
        for deel_ in ("keuze", "les"):
            p = d["P2"][deel_]
            vind = f"{p['vindkans']:.1%}" if p["vindkans"] is not None else "-"
            print(f"  P2 {deel_}deel: n {p['n']} · gevonden {p['gevonden']} ({vind}) · andere claim anders"
                  f" {p['ander_anders']}")
        n1 = d["N1"]
        print(f"  N1 zonder lesstof: n {n1['n']:,} · vals {n1['vals']}; in de lesstof {n1['lesstof']:,}"
              f" stukken, vals {n1['vals_in_lesstof']}")
    return uit


def main() -> None:  # pragma: no cover
    import argparse
    import os

    parser = argparse.ArgumentParser(description="De zeef: de meetmachine per versie (PLAN #30.1, B33)")
    parser.add_argument("stap", choices=("meten", "drukte", "lezen", "tellen"))
    parser.add_argument("--versie", required=True, help="de naam van de versie, bijvoorbeeld factiz-1")
    parser.add_argument("--sets", default=",".join(SETS))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--config", help="een andere config dan config.toml, bijvoorbeeld met de rechter aan")
    args = parser.parse_args()
    db = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    try:
        if args.stap == "meten":
            # Tesseract neemt anders zelf alle kernen; twee per proces is de afspraak.
            os.environ.setdefault("OMP_THREAD_LIMIT", str(args.threads))
            import torch
            from threadpoolctl import threadpool_limits

            threadpool_limits(limits=args.threads)
            torch.set_num_threads(args.threads)
            sets = [s.strip() for s in args.sets.split(",") if s.strip()]
            onbekend = [s for s in sets if s not in SETS]
            if onbekend:
                raise Weigering(f"onbekende set(s): {onbekend}")
            meten(args.versie, sets, db, args.config)
        elif args.stap == "drukte":
            from collections import Counter

            telling = drukte_meten(args.versie, db)
            print(f"{len(telling)} verwachte claims; per emmer: {dict(Counter(emmer(n) for n in telling.values()))}")
        elif args.stap == "lezen":
            lezen(args.versie, db)
        else:
            tellen(args.versie)
    except Weigering as reden:
        raise SystemExit(f"geweigerd: {reden}")


if __name__ == "__main__":
    main()
