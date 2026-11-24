"""Drie voormetingen voor de volgende beeldronde (PLAN #32.20), $0 en zonder vraag aan een taalmodel.

- V1: §187 opnieuw met de herstelde vergelijking (`sift-ransac-v2`): elke kopie van R2 tegen elk beeld uit de artikelen
  van R2. Kan het beeld zelf zoeken?
- V2: per sleutel (tekst, beschrijving) de beste 5, 10 en 20 checks. Vinden de woorden de eigen check vaker?
- V3: de matcher van CopyNCE (`copynce.py`) naast SIFT: op de gelabelde paren van #32.17, op R2 zoals V1, en op een
  steekproef van paren die SIFT niet bevestigde.

Beelden alleen in het werkgeheugen (B35); op schijf per paar alleen getallen. `tellen` weigert zolang een paar dat telt
geen label heeft in `docs/steekproeven/32.20-voormetingen.json`; een label uit #32.15 of #32.17 voor hetzelfde paar telt
mee.

    python -m doublecheck.hittewacht -- python -m doublecheck.beeldvoormeting r2|paren|kandidaten
    python -m doublecheck.beeldvoormeting lezen|tellen
"""

from __future__ import annotations

import collections
import json
import random
import threading
import time
from pathlib import Path

from doublecheck import beeldbevestiging as bb
from doublecheck import beeldindexmeting as bm
from doublecheck import beeldvraag as bv

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "beeldvoormeting"
LABELS = WORTEL / "docs" / "steekproeven" / "32.20-voormetingen.json"
GEVONDEN, ANDERE, VALS = bm.GEVONDEN, bm.ANDERE, bm.VALS
LABELWAARDEN = bm.LABELWAARDEN

# vooraf vastgelegd in PLAN #32.20; niet bijstellen na de uitslag
HOOFDREGEL, REGEL_187, MIN_DEKKING = 50, 20, bb.MIN_DEKKING
DREMPEL = 0.5                      # CopyNCE: het midden van de score; de makers geven geen werkpunt
KANDIDATEN = (5, 10, 20)
MIN_CLAIMS_V1 = 30                 # eis 2 van #32.17
MIN_EXTRA_V2 = 5
ZAAD_C, N_C = 3220, 300
SETS_C = ("N", "R3", "W", "S1", "S2", "S3", "S4")
SETS_V2 = ("N", "R2", "R3")
INDEX_GROOT = 200_000              # de doorrekening: zoveel artikelbeelden heeft de database ongeveer
BEWAAR_COPYNCE = 5                 # per kopie de beste scores, plus alles vanaf de drempel


class Weigering(Exception):
    """Tellen kan niet: een paar dat telt heeft geen label."""


# --- labels ------------------------------------------------------------------------------------------------

def labelsleutel(set_: str, vraag: str, beeld: str) -> str:
    return f"{set_}|{vraag}|{beeld}"


def samengevoegd(eigen: dict[str, str], van_3217: dict[str, str], van_3215: dict[str, str]) -> dict[str, str]:
    """Eén woordenboek: de eigen labels eerst, dan die van #32.17 (zelfde sleutel), dan die van #32.15. Die laatste
    hebben de sleutel `R2|kopie|origineel|beeld`; ze staan erin als `R2|kopie|beeld`, zodat `label` ze vindt."""
    uit = {}
    for k, v in van_3215.items():
        delen = k.split("|")
        if len(delen) == 4 and delen[2] == "origineel":
            uit[labelsleutel(delen[0], delen[1], delen[3])] = v
    uit.update(van_3217)
    uit.update(eigen)
    return uit


def label(labels: dict[str, str], regel: dict, beeld: str) -> str | None:
    """Het label van een kopie van R2 tegen een beeld: op haar werk-id (#32.17, #32.20) of op haar adres (#32.15)."""
    return labels.get(labelsleutel(regel["set"], regel["id"], beeld)) or \
        labels.get(labelsleutel(regel["set"], regel["vraag"], beeld))


def lees_labels() -> dict[str, str]:
    def lees(pad: Path) -> dict[str, str]:
        if not pad.exists():
            return {}
        labels = json.loads(pad.read_text(encoding="utf-8")).get("labels", {})
        fout = {k: v for k, v in labels.items() if v not in LABELWAARDEN}
        if fout:
            raise Weigering(f"onbekende labels in {pad.name}: {list(fout.items())[:3]}")
        return labels

    return samengevoegd(lees(LABELS), lees(bb.LABELS), lees(bm.LABELS))


# --- V1 en V3 (b): R2, elke kopie tegen elk indexbeeld -------------------------------------------------------

def beste_sift(treffers: list[list], min_punten: int) -> list | None:
    """De treffer met de meeste punten die de regel haalt; `treffers` is [beeld, groep, artikel, punten, dekking]."""
    goed = [t for t in treffers if t[3] >= min_punten and t[4] >= MIN_DEKKING]
    return max(goed, key=lambda t: t[3]) if goed else None


def beste_copynce(treffers: list[list], drempel: float) -> list | None:
    """De hoogste score vanaf de drempel; `treffers` is [beeld, groep, artikel, score]."""
    goed = [t for t in treffers if t[3] >= drempel]
    return max(goed, key=lambda t: t[3]) if goed else None


def _beste(regel: dict, methode: str, grens: float) -> list | None:
    return beste_sift(regel["sift"], grens) if methode == "sift" else beste_copynce(regel["copynce"], grens)


def _label_nodig(regel: dict, beste: list, methode: str, grens: float) -> bool:
    """Bij de regel van §187 telt een treffer in het eigen artikel zonder label, zoals toen; anders elke beste."""
    return not (methode == "sift" and grens == REGEL_187 and beste[1] == regel["groep"])


def te_lezen_r2(regels: list[dict], labels: dict[str, str], methode: str, grens: float) -> list[tuple[dict, list]]:
    uit = []
    for r in regels:
        b = _beste(r, methode, grens)
        if b is not None and _label_nodig(r, b, methode, grens) and label(labels, r, b[0]) is None:
            uit.append((r, b))
    return uit


def r2_telling(regels: list[dict], labels: dict[str, str], methode: str, grens: float) -> dict:
    """Per claim gevonden als een kopie haar beste treffer in het eigen artikel heeft en die zelfde beeld, zelfde
    bewering is; elders telt per kopie. Weigert zolang een beste treffer die telt geen label heeft."""
    open_ = te_lezen_r2(regels, labels, methode, grens)
    if open_:
        r, b = open_[0]
        raise Weigering(f"{len(open_)} beste treffers zonder label ({methode}, {grens}), bijvoorbeeld "
                        f"{labelsleutel(r['set'], r['id'], b[0])}")
    gevonden, elders_zelfde = set(), set()
    teller = collections.Counter()
    for r in regels:
        b = _beste(r, methode, grens)
        if b is None:
            teller["kopieën zonder treffer"] += 1
            continue
        oordeel = label(labels, r, b[0]) if _label_nodig(r, b, methode, grens) else GEVONDEN
        eigen = b[1] == r["groep"]
        if oordeel == GEVONDEN:
            (gevonden if eigen else elders_zelfde).add(r["claim_id"])
            teller["beste in het eigen artikel" if eigen else "beste elders, zelfde beeld en bewering"] += 1
        elif oordeel == ANDERE:
            teller["zelfde beeld, andere bewering"] += 1
        else:
            teller["vals"] += 1
            teller["vals in het eigen artikel" if eigen else "vals elders"] += 1
    return {"kopieën": len(regels), "claims": len({r["claim_id"] for r in regels}), "gevonden": len(gevonden),
            "gevonden elders": len(elders_zelfde - gevonden), "vals": teller["vals"], **dict(teller)}


def v1_beslissing(hoofd: dict) -> dict:
    regels = {"geen kopie met een ander beeld als beste treffer": hoofd["vals"] == 0,
              f"minstens {MIN_CLAIMS_V1} claims met een echte treffer in het eigen artikel":
                  hoofd["gevonden"] >= MIN_CLAIMS_V1}
    return {**regels, "gehaald": all(regels.values())}


def kans_per_paar(regels: list[dict], min_punten: int = HOOFDREGEL) -> dict:
    """Alle paren buiten het eigen artikel die de regel halen, gedeeld door alle vergelijkingen buiten het eigen
    artikel: een bovengrens voor de kans op een vals paar (ongelezen; er zit ook zelfde beeld elders tussen)."""
    boven = sum(1 for r in regels for t in r["sift"] if t[1] != r["groep"] and t[3] >= min_punten
                and t[4] >= MIN_DEKKING)
    vergelijkingen = sum(r["index"] - r["eigen_beelden"] for r in regels)
    kans = boven / vergelijkingen if vergelijkingen else 0.0
    return {"paren elders boven de regel": boven, "vergelijkingen elders": vergelijkingen, "kans per paar": kans,
            f"per vraag bij {INDEX_GROOT:,} beelden".replace(",", "."): round(kans * INDEX_GROOT, 2)}


# --- V2: meer kandidaten per sleutel ----------------------------------------------------------------------

def _bij(v: dict, n: int) -> list[dict]:
    return bb.kandidaten(v["tekst"][:n], v["beschrijving"][:n], lambda c: None)


def eigen_bij(v: dict, n: int) -> set[str]:
    """Via welke sleutels de eigen check bij de beste n van elke sleutel staat (leeg: niet)."""
    eigen = set(v["eigen"])
    groep = {k["claim"]: k["groep"] for k in v["tekst"] + v["beschrijving"]}
    return {via for k in _bij(v, n) if groep.get(k["claim"], k["claim"]) in eigen for via in k["via"]}


def nieuwe_eigen(v: dict) -> list[tuple[int, dict]]:
    """De eigen checks die er pas bij 10 of 20 bij komen, met het kleinste n waarbij ze er staan."""
    eigen, gezien, uit = set(v["eigen"]), set(), []
    for n in KANDIDATEN:
        for k in v["tekst"][:n] + v["beschrijving"][:n]:
            if k["groep"] in eigen and k["url"] not in gezien:
                gezien.add(k["url"])
                if n > KANDIDATEN[0]:
                    uit.append((n, k))
    return uit


def v2_telling(regels: list[dict]) -> dict:
    """Per set en per n: bij hoeveel claims (N: screenshots) de eigen check bij de kandidaten staat, via welke
    sleutel, en hoeveel artikelen er per vraag te vergelijken zijn."""
    uit = {}
    for set_ in SETS_V2:
        vragen = [v for v in regels if v["set"] == set_]
        if not vragen:
            continue
        uit[set_] = {}
        for n in KANDIDATEN:
            per = collections.defaultdict(set)
            for v in vragen:
                via = eigen_bij(v, n)
                if via:
                    per["gevonden"].add(v["claim_id"] or v["id"])
                    for s in via:
                        per[f"via {s}"].add(v["claim_id"] or v["id"])
            artikelen = [len({k["url"] for k in _bij(v, n) if k.get("url")}) for v in vragen]
            uit[set_][str(n)] = {"vragen": len(vragen), **{k: len(s) for k, s in per.items()},
                                 "artikelen per vraag": round(sum(artikelen) / len(artikelen), 2)}
    return uit


def verwacht_vals(kans_per_paar_: float, artikelen_per_vraag: float, beelden_per_artikel: float) -> float:
    """Het verwachte aantal valse bevestigingen per 1.000 vragen bij zoveel artikelen per vraag."""
    return 1000 * artikelen_per_vraag * beelden_per_artikel * kans_per_paar_


def v2_beslissing(extra_r3: int, verwacht_per_1000: float) -> dict:
    regels = {f"minstens {MIN_EXTRA_V2} claims extra bevestigd bij R3": extra_r3 >= MIN_EXTRA_V2,
              "verwacht vals onder 1 per 1.000 vragen": verwacht_per_1000 < 1}
    return {**regels, "gehaald": all(regels.values())}


# --- V3: CopyNCE naast SIFT ---------------------------------------------------------------------------------

def steekproef_c(paren: list[dict], huisstijl_: set[str], n: int = N_C, zaad: int = ZAAD_C) -> list[dict]:
    """n paren van #32.17 die tellen (niet de vraag zelf, geen huisstijl) en die SIFT niet bevestigde, uit de sets
    met een eigen beslissing; elk paar één keer; altijd dezelfde."""
    gezien, lijst = set(), []
    for p in paren:
        k = bb.labelsleutel(p)
        if p["set"] in SETS_C and k not in gezien and bb.telt(p, huisstijl_) and not bb.bevestigd(p):
            gezien.add(k)
            lijst.append(p)
    lijst.sort(key=bb.labelsleutel)
    return random.Random(zaad).sample(lijst, min(n, len(lijst)))


def v3a_telling(scores: dict[str, float], labels: dict[str, str], drempel: float = DREMPEL) -> dict:
    uit = {w: {"paren": 0, "boven": 0} for w in LABELWAARDEN}
    for k, s in scores.items():
        if k in labels:
            uit[labels[k]]["paren"] += 1
            uit[labels[k]]["boven"] += s >= drempel
    return uit


def v3c_telling(scores: dict[str, float], labels: dict[str, str], drempel: float = DREMPEL) -> dict:
    boven = [k for k, s in scores.items() if s >= drempel]
    open_ = [k for k in boven if k not in labels]
    if open_:
        raise Weigering(f"{len(open_)} paren van CopyNCE zonder label, bijvoorbeeld {open_[0]}")
    c = collections.Counter(labels[k] for k in boven)
    return {"paren": len(scores), "boven": len(boven), "zelfde beeld": c[GEVONDEN] + c[ANDERE],
            "zelfde beeld, zelfde bewering": c[GEVONDEN], "zelfde beeld, andere bewering": c[ANDERE],
            "vals": c[VALS]}


def v3_beslissing(a: dict, b: dict, c: dict, sift_vals: int) -> dict:
    """Als tweede bevestiger: minstens 10 echte paren die SIFT miste, en niet meer vals dan SIFT in V1. Als filter:
    minstens 95% van de echte paren gehouden en minstens de helft van de andere beelden geweerd."""
    echt, ander = a[GEVONDEN], a[VALS]
    return {"als tweede bevestiger": c["zelfde beeld"] >= 10 and b["vals"] + c["vals"] <= sift_vals,
            "als filter": echt["paren"] > 0 and echt["boven"] >= 0.95 * echt["paren"]
            and ander["paren"] > 0 and ander["paren"] - ander["boven"] >= 0.5 * ander["paren"]}


# --- de bestanden -------------------------------------------------------------------------------------------

_SCHRIJFSLOT = threading.Lock()


def _jsonl(pad: Path) -> list[dict]:
    return bm._jsonl(pad)


def _geen_bytes(x) -> None:
    if isinstance(x, (bytes, bytearray, memoryview)):
        raise ValueError("een beeld gaat nooit naar schijf (B35)")
    if isinstance(x, dict):
        for w in x.values():
            _geen_bytes(w)
    elif isinstance(x, (list, tuple)):
        for w in x:
            _geen_bytes(w)


def schrijf(pad: Path, regels: list[dict]) -> None:
    for r in regels:
        _geen_bytes(r)
    pad.parent.mkdir(parents=True, exist_ok=True)
    bm._schrijf(pad, regels, _SCHRIJFSLOT)


# --- rekenen (netwerk en modellen) -----------------------------------------------------------------------

def _rekenen():  # pragma: no cover - laadt de modellen
    import cv2
    import torch

    cv2.setNumThreads(2)     # hoogstens twee kernen (PO)
    torch.set_num_threads(2)
    from doublecheck import copynce

    return copynce.laad(apparaat="mps" if torch.backends.mps.is_available() else "cpu")


def _tokens(model, invoer: list) -> "torch.Tensor":  # pragma: no cover - met het model
    import torch

    apparaat = next(model.parameters()).device
    delen = [model.tokens(torch.stack(invoer[i:i + 32]).to(apparaat)) for i in range(0, len(invoer), 32)]
    return torch.cat(delen) if delen else torch.zeros(0)


def _per_host(web, werk: list[dict], haal) -> list:  # pragma: no cover - netwerk
    """`haal(web, w)` voor elk werk, per host na elkaar en hosts naast elkaar."""
    import concurrent.futures as cf

    groepen = collections.defaultdict(list)
    for w in werk:
        groepen[bm.host(w["adres"])].append(w)

    def doe(lijst):
        return [x for w in lijst if (x := haal(web, w)) is not None]

    with cf.ThreadPoolExecutor(8) as pool:
        return [x for lijst in pool.map(doe, sorted(groepen.values(), key=len, reverse=True)) for x in lijst]


def _r2(proef: int = 0) -> None:  # pragma: no cover - netwerk en modellen
    """V1 en V3 (b): de beelden van de artikelen van R2 en de 275 kopieën opnieuw opgehaald, alleen in het geheugen;
    elke kopie tegen elk indexbeeld, met SIFT (hele beeld, zoals §187) en met CopyNCE."""
    from doublecheck import copynce
    from doublecheck.beeldindex import _lees, laatste

    model = _rekenen()
    groep_van = {c["url"]: c["groep"] for c in bm._lees_set()["r2"]}
    web, rekenen = bm.Beleefd(), threading.Lock()

    def haal(web_, w):
        inhoud = web_.beeld(w["adres"])
        if inhoud is None:
            return None
        try:
            with rekenen:
                return {**w, "punten": bv.puntkenmerken(inhoud), "invoer": copynce.invoer(inhoud)}
        except Exception:   # kapot of geen beeld: overslaan, nooit loggen (DR3)
            return None
        finally:
            del inhoud

    begin = time.monotonic()
    werk = [{"adres": b["beeld"], "groep": groep_van[r["url"]], "artikel": r["url"]}
            for r in laatste(_lees(bm.PANEELMAP)) if r["status"] == 200 and r["url"] in groep_van
            for b in r["beelden"] if min(b["breedte"], b["hoogte"]) >= bm.MIN_ZIJDE]
    vragen = _jsonl(bm.MAP / "vragen" / "R2.jsonl")
    if proef:
        werk, vragen = werk[:3 * proef], vragen[:proef]
    index = _per_host(web, werk, haal)
    print(f"index: {len(index)} beelden in {time.monotonic() - begin:.0f} s", flush=True)
    kopieen = _per_host(web, [{"adres": v["vraag"], "id": v["werk"], "vraag": v["vraag"], "claim_id": v["claim_id"],
                               "groep": v["groep"], "soort": v["soort"]} for v in vragen], haal)
    print(f"kopieën: {len(kopieen)} van {len(vragen)} opgehaald", flush=True)
    index_tokens = _tokens(model, [i.pop("invoer") for i in index])
    kopie_tokens = _tokens(model, [k.pop("invoer") for k in kopieen])
    regels = []
    for k, tk in zip(kopieen, kopie_tokens):
        t0 = time.monotonic()
        sift = []
        for i in index:
            n, d = bv.puntvergelijking(k["punten"], i["punten"])
            if n >= REGEL_187:
                sift.append([i["adres"], i["groep"], i["artikel"], n, round(d, 3)])
        t1 = time.monotonic()
        s = copynce.scores(model, tk, index_tokens)
        t2 = time.monotonic()
        volgorde = sorted(range(len(index)), key=lambda j: -s[j])
        bewaard = [j for n_, j in enumerate(volgorde) if n_ < BEWAAR_COPYNCE or s[j] >= DREMPEL]
        regels.append({"set": "R2", "id": k["id"], "vraag": k["vraag"], "claim_id": k["claim_id"], "groep": k["groep"],
                       "soort": k["soort"], "vergelijking": bv.VERGELIJKING, "copynce_versie": copynce.VERSIE,
                       "sift": sorted(sift, key=lambda t: -t[3]),
                       "copynce": [[index[j]["adres"], index[j]["groep"], index[j]["artikel"], round(float(s[j]), 4)]
                                   for j in bewaard],
                       "index": len(index), "eigen_beelden": sum(i["groep"] == k["groep"] for i in index),
                       "seconden_sift": round(t1 - t0, 3), "seconden_copynce": round(t2 - t1, 3)})
    pad = MAP / ("r2-proef.jsonl" if proef else "r2.jsonl")
    pad.unlink(missing_ok=True)
    schrijf(pad, regels)
    print(f"klaar: {len(regels)} kopieën in {time.monotonic() - begin:.0f} s", flush=True)


def _vraagbeeld(web, v: dict) -> bytes | None:  # pragma: no cover - netwerk
    """De vraag van #32.17 opnieuw: N en W uit M4FC op schijf, S4 opnieuw getekend, de rest beleefd opgehaald."""
    if v["set"] in ("N", "W"):
        return Path(v["beeld"]).read_bytes()
    sjabloon = next((b for a in v["adressen"] if (b := web.beeld(a)) is not None), None)
    if v["set"] == "S4":
        return bb._meme(sjabloon, v["onderschrift"]) if sjabloon else None
    return sjabloon


def _gebied(beeld: bytes):  # pragma: no cover - op echte beelden
    """Het deel van de vraag waar #32.17 de punten van nam: het beeldgebied, anders het hele beeld."""
    from doublecheck.beelduitsnede import beeldgebied

    b = bv._open(beeld)
    gebied = beeldgebied(b)
    return b.crop(gebied) if gebied else b


def _paren(proef: int = 0) -> None:  # pragma: no cover - netwerk en modellen
    """V3 (a) en (c): de gelabelde paren van #32.17 en de steekproef van onbevestigde paren, met CopyNCE. De vraag
    zoals #32.17 haar punten nam (het beeldgebied), het artikelbeeld heel."""
    from doublecheck import copynce

    model = _rekenen()
    vragen_, paren_, stijl = bb._stand()
    opnieuw = {r["sleutel"]: {k: r[k] for k in ("punten", "dekking", "punten500", "dekking500")}
               for r in _jsonl(bb.MAP / "paren-v2.jsonl") if "punten" in r}
    paren_ = bb.herberekend(paren_, opnieuw)
    per_sleutel = {bb.labelsleutel(p): p for p in paren_}
    gelabeld = json.loads(bb.LABELS.read_text(encoding="utf-8"))["labels"]
    werk = [("a", per_sleutel[k]) for k in sorted(gelabeld) if k in per_sleutel]
    werk += [("c", p) for p in steekproef_c(paren_, stijl)]
    if proef:
        werk = [w for w in werk if w[0] == "a"][:proef] + [w for w in werk if w[0] == "c"][:proef]
    print(f"{sum(d == 'a' for d, _ in werk)} gelabelde paren, {sum(d == 'c' for d, _ in werk)} uit de steekproef",
          flush=True)
    vraag_van = {(v["set"], v["id"]): v for v in vragen_}
    web, rekenen = bm.Beleefd(), threading.Lock()
    begin = time.monotonic()

    def haal_vraag(web_, w):
        inhoud = _vraagbeeld(web_, vraag_van[w["sleutel"]])
        if inhoud is None:
            return None
        try:
            with rekenen:
                return {**w, "invoer": copynce.invoer(_gebied(inhoud))}
        except Exception:
            return None
        finally:
            del inhoud

    def haal_beeld(web_, w):
        inhoud = web_.beeld(w["adres"])
        if inhoud is None:
            return None
        try:
            with rekenen:
                return {**w, "invoer": copynce.invoer(inhoud)}
        except Exception:
            return None
        finally:
            del inhoud

    sleutels = sorted({(p["set"], p["vraag"]) for _, p in werk})
    vragen = _per_host(web, [{"sleutel": k, "adres": (vraag_van[k].get("adressen") or [vraag_van[k].get("beeld", "")])[0]}
                             for k in sleutels], haal_vraag)
    vt = dict(zip([v["sleutel"] for v in vragen], _tokens(model, [v.pop("invoer") for v in vragen])))
    print(f"vragen: {len(vt)} van {len(sleutels)} in {time.monotonic() - begin:.0f} s", flush=True)
    beelden = _per_host(web, [{"adres": a} for a in sorted({p["beeld"] for _, p in werk})], haal_beeld)
    bt = dict(zip([b["adres"] for b in beelden], _tokens(model, [b.pop("invoer") for b in beelden])))
    print(f"artikelbeelden: {len(bt)} in {time.monotonic() - begin:.0f} s", flush=True)
    regels, tijden = [], []
    for deel, p in werk:
        k = (p["set"], p["vraag"])
        regel = {"deel": deel, "sleutel": bb.labelsleutel(p), "set": p["set"], "groep": p["groep"],
                 "copynce_versie": copynce.VERSIE, "punten": p["punten"], "dekking": p["dekking"]}
        if k in vt and p["beeld"] in bt:
            t0 = time.monotonic()
            regel["score"] = round(float(copynce.scores(model, vt[k], bt[p["beeld"]][None])[0]), 4)
            tijden.append(time.monotonic() - t0)
        regels.append(regel)
    pad = MAP / ("paren-proef.jsonl" if proef else "paren.jsonl")
    pad.unlink(missing_ok=True)
    schrijf(pad, regels)
    print(f"klaar: {sum('score' in r for r in regels)} van {len(regels)} paren gescoord, "
          f"{1000 * sum(tijden) / max(len(tijden), 1):.1f} ms per paar", flush=True)


def _kandidaten(sets: list[str], proef: int = 0) -> None:  # pragma: no cover - netwerk en de database
    """V2: per vraag van N, R2 en R3 de beste 20 checks per sleutel; de kopie opnieuw gelezen (OCR, gemaskeerd) met de
    beweringen van #32.17; de beschrijving uit #32.17. Een eigen check die er pas bij 10 of 20 bij komt: het artikel
    beleefd ophalen en de vraag ertegen zetten. De tekst blijft in het geheugen."""
    import concurrent.futures as cf

    from doublecheck import beschrijvingvraag as bs
    from doublecheck import berichtcontrole as bc
    from doublecheck import beweringvraag as zh
    from doublecheck import machinevraag as mv
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    bb._rekenen()
    import cv2
    cv2.setNumThreads(2)
    config = load_config(None)
    groep_van = bb._groep_van()
    ronde = {s["id"]: s for s in _jsonl(bb.BEELDRONDE)}
    rekenen, lokaal = threading.Lock(), threading.local()
    web = bm.Beleefd()
    staart = "-proef" if proef else ""
    pad, ppad = MAP / f"kandidaten{staart}.jsonl", MAP / f"kandidaten-paren{staart}.jsonl"
    klaar = {(r["set"], r["id"]) for r in _jsonl(pad)}
    vragen = [v for v in _jsonl(bb.MAP / "vragen.jsonl") if v["set"] in sets and (v["set"], v["id"]) not in klaar]
    if proef:
        vragen = [v for s in sets for v in [w for w in vragen if w["set"] == s][:proef]]
    print(f"{len(vragen)} vragen", flush=True)

    def conn():
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        return lokaal.conn

    def zoek(tekst: str, gehaald: list[dict], n: int) -> list[dict]:
        with rekenen:
            vragen_ = [tekst] + (zh.zoekvragen(tekst, gehaald)[1:] if gehaald else [])
            fps = fingerprint_texts([q[:600] for q in vragen_], config.model_versions.text_embedding)
            lijsten = search_texts(conn(), fps, n + 3, varianten=True)
            uit = zh.voeg_samen([mv.kandidaten_uit(conn(), lijst) for lijst in lijsten], n)
        return [{"claim": k["claim"], "groep": groep_van.get(k["claim"], k["claim"]), "url": k["url"],
                 "gelijkenis": k["gelijkenis"]} for k in uit]

    def doe(v: dict) -> None:
        if v["set"] == "N":     # de tekst van het bericht uit §178, zoals #32.17 hem gebruikte
            beeld = Path(v["beeld"]).read_bytes()
            tekst, gehaald = ronde[v["id"]]["tekst"], []
        else:
            beeld = next((b for a in v["adressen"] if (b := web.beeld(a)) is not None), None)
            if beeld is None:
                schrijf(pad, [{"set": v["set"], "id": v["id"], "fout": "niet opgehaald"}])
                return
            with rekenen:
                tekst = bc.bericht_uit(None, beeld, config.ocr)
            gehaald = v["beweringen"]
        tekstlijst = zoek(tekst, gehaald, KANDIDATEN[-1]) if len(tekst.strip()) >= bb.MIN_TEKENS else []
        del tekst
        beschrijving = {"beschrijving": v["beschrijving"], "zoekvragen": v["zoekvragen"]} if v["beschrijving"] else None
        beeldlijst = zoek(v["beschrijving"], bs.als_beweringen(beschrijving), KANDIDATEN[-1]) if beschrijving else []
        regel = {"set": v["set"], "id": v["id"], "claim_id": v.get("claim_id"), "eigen": v["groepen"],
                 "tekst": tekstlijst, "beschrijving": beeldlijst,
                 "eerder bij 5": sorted({k["groep"] for k in v["kandidaten"]} & set(v["groepen"]))}
        nieuw = nieuwe_eigen(regel)
        paren = []
        if nieuw:
            with rekenen:
                kenmerken, punten = bb._vraagkenmerken(beeld)
            vraagregel = {**v, **kenmerken}
            for n, k in nieuw:
                status, adressen = bb._pagina(web, k["url"])
                for adres in adressen:
                    inhoud = web.beeld(adres)
                    if inhoud is None:
                        continue
                    try:
                        with rekenen:
                            kenm = bb.artikelbeeld(inhoud)
                            if min(kenm["breedte"], kenm["hoogte"]) >= bm.MIN_ZIJDE:
                                p = bb.vergelijk(vraagregel, punten, {**k, "via": ["n" + str(n)],
                                                                      "redactie": None}, {"beeld": adres, **kenm})
                                paren.append({**p, "n": n})
                    except Exception:   # kapot of geen beeld: overslaan (DR3)
                        pass
                    del inhoud
            regel["nieuw"] = [{"n": n, "url": k["url"], "groep": k["groep"]} for n, k in nieuw]
        del beeld
        schrijf(ppad, paren)
        schrijf(pad, [regel])
        print(f"{v['set']} {v['id'][:50]}: tekst {len(tekstlijst)}, beschrijving {len(beeldlijst)}, "
              f"nieuw {len(nieuw)}, paren {len(paren)}", flush=True)

    with cf.ThreadPoolExecutor(4) as pool:
        list(pool.map(doe, vragen))


# --- lezen en tellen ------------------------------------------------------------------------------------------

def _stand() -> dict:
    return {"r2": _jsonl(MAP / "r2.jsonl"), "paren": _jsonl(MAP / "paren.jsonl"),
            "kandidaten": [r for r in _jsonl(MAP / "kandidaten.jsonl") if "fout" not in r],
            "kandidaten-paren": _jsonl(MAP / "kandidaten-paren.jsonl")}


def _bevestigd_v2(p: dict) -> bool:
    return not p["uitgesloten"] and p["punten"] >= HOOFDREGEL and p["dekking"] >= MIN_DEKKING


def te_lezen(stand: dict, labels: dict[str, str]) -> list[dict]:
    """Alles wat een label nodig heeft en er nog geen heeft, elk paar één keer: V1 (beide regels), V3 (b) en (c), en
    de bevestigingen van V2."""
    uit, gezien = [], set()

    def voeg(set_, vraag, beeld, rest):
        k = labelsleutel(set_, vraag, beeld)
        if k not in gezien:
            gezien.add(k)
            uit.append({"sleutel": k, "set": set_, "vraag": vraag, "beeld": beeld, **rest})

    for methode, grens in (("sift", HOOFDREGEL), ("sift", REGEL_187), ("copynce", DREMPEL)):
        for r, b in te_lezen_r2(stand["r2"], labels, methode, grens):
            voeg("R2", r["id"], b[0], {"waar": f"R2 {methode} {grens}", "adres": r["vraag"], "artikel": b[2],
                                       "eigen": b[1] == r["groep"], "maat": b[3:]})
    for r in stand["paren"]:
        if r["deel"] == "c" and r.get("score", 0) >= DREMPEL and r["sleutel"] not in labels:
            set_, vraag, beeld = r["sleutel"].split("|", 2)
            voeg(set_, vraag, beeld, {"waar": "V3 (c)", "maat": [r["score"], r["punten"]]})
    for p in stand["kandidaten-paren"]:
        if _bevestigd_v2(p) and bb.labelsleutel(p) not in labels:
            voeg(p["set"], p["vraag"], p["beeld"], {"waar": f"V2 bij {p['n']}", "artikel": p["artikel"],
                                                    "eigen": True, "maat": [p["punten"], p["dekking"]]})
    return uit


def _lezen() -> None:  # pragma: no cover - schrijft leesbladen naast de bestanden
    import html

    lijst = te_lezen(_stand(), lees_labels())
    vraag_van = {(v["set"], v["id"]): v for v in _jsonl(bb.MAP / "vragen.jsonl")}
    conn = bm._db()
    tekst = dict(conn.execute("SELECT claim_id, substr(canonical_text, 1, 220) FROM claim"))
    kort = lambda t, n=160: html.escape((t or "")[:n])   # noqa: E731
    rijen = []
    for nr, p in enumerate(lijst):
        v = vraag_van.get((p["set"], p["vraag"]), {})
        adres = p.get("adres") or v.get("vraag") or ""
        terug = html.escape((v.get("adressen") or [adres])[-1])
        uitleg = v.get("onderschrift") or tekst.get(v.get("claim_id", ""), "") or v.get("titel") or ""
        rijen.append(f"<div class=k><b>#{nr}</b> {html.escape(p['waar'])} · "
                     f"<b>{'EIGEN' if p.get('eigen') else 'elders'}</b> · {html.escape(str(p['maat']))}"
                     f"<div><img referrerpolicy=no-referrer src='{html.escape(adres)}' onerror=\"this.src='{terug}'\">"
                     f"<img referrerpolicy=no-referrer src='{html.escape(p['beeld'])}'></div>"
                     f"<b>vraag:</b> {kort(uitleg)}<br><a href='{html.escape(p.get('artikel') or '')}'>"
                     f"{kort(p.get('artikel'), 80)}</a></div>")
    kop = ("<!doctype html><meta charset=utf-8><title>Voormetingen lezen</title><style>body{font:11px sans-serif;"
           "margin:2px;display:flex;flex-wrap:wrap;gap:4px}.k{width:388px;border:1px solid #bbb;padding:2px}"
           "img{width:191px;height:150px;object-fit:contain;background:#eee;margin:1px}</style>")
    for oud in MAP.glob("lezen-*.html"):
        oud.unlink()
    for i in range(0, len(rijen), 8):     # bladen van acht kaarten: één schermbeeld per blad
        (MAP / f"lezen-{i // 8}.html").write_text(kop + "".join(rijen[i:i + 8]), encoding="utf-8")
    (MAP / "lezen.json").write_text(json.dumps([p["sleutel"] for p in lijst], ensure_ascii=False, indent=0),
                                    encoding="utf-8")
    print(f"{len(lijst)} paren te lezen, {(len(rijen) + 7) // 8} bladen in {MAP}")


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    stand, labels = _stand(), lees_labels()
    uit: dict = {}
    if stand["r2"]:
        r2 = stand["r2"]
        uit["V1"] = {"hoofdregel (50 punten)": r2_telling(r2, labels, "sift", HOOFDREGEL),
                     "regel van §187 (20 punten)": r2_telling(r2, labels, "sift", REGEL_187),
                     "kans op een vals paar": kans_per_paar(r2, HOOFDREGEL),
                     "seconden per kopie (SIFT, p50)": sorted(r["seconden_sift"] for r in r2)[len(r2) // 2]}
        uit["V1"]["beslissing"] = v1_beslissing(uit["V1"]["hoofdregel (50 punten)"])
        uit["V3 (b)"] = r2_telling(r2, labels, "copynce", DREMPEL)
        uit["V3 (b)"]["seconden per kopie (CopyNCE, p50)"] = sorted(r["seconden_copynce"] for r in r2)[len(r2) // 2]
    if stand["paren"]:
        scores = {r["sleutel"]: r["score"] for r in stand["paren"] if "score" in r}
        a = {k: s for k, s in scores.items() if any(r["sleutel"] == k and r["deel"] == "a" for r in stand["paren"])}
        c = {r["sleutel"]: r["score"] for r in stand["paren"] if r["deel"] == "c" and "score" in r}
        uit["V3 (a)"] = v3a_telling(a, labels)
        uit["V3 (a)"]["niet op te halen"] = sum(r["deel"] == "a" and "score" not in r for r in stand["paren"])
        uit["V3 (c)"] = v3c_telling(c, labels)
        uit["V3 (c)"]["niet op te halen"] = sum(r["deel"] == "c" and "score" not in r for r in stand["paren"])
        if "V1" in uit:
            uit["V3"] = v3_beslissing(uit["V3 (a)"], uit["V3 (b)"], uit["V3 (c)"],
                                      uit["V1"]["hoofdregel (50 punten)"]["vals"])
    if stand["kandidaten"]:
        uit["V2"] = v2_telling(stand["kandidaten"])
        open_ = [p for p in stand["kandidaten-paren"] if _bevestigd_v2(p) and bb.labelsleutel(p) not in labels]
        if open_:
            raise Weigering(f"{len(open_)} bevestigingen van V2 zonder label, bijvoorbeeld {bb.labelsleutel(open_[0])}")
        extra = collections.defaultdict(set)
        regels = {(r["set"], r["id"]): r for r in stand["kandidaten"]}
        for p in stand["kandidaten-paren"]:
            r = regels.get((p["set"], p["vraag"]))
            if r and _bevestigd_v2(p) and labels.get(bb.labelsleutel(p)) == GEVONDEN:
                for n in KANDIDATEN[1:]:
                    if p["n"] <= n:
                        extra[(p["set"], n)].add(r["claim_id"] or r["id"])
        eerder = _eerder_bevestigd(labels)   # extra is alleen wat #32.17 bij 5 nog niet bevestigde
        extra = {(s, n): c - eerder[s] for (s, n), c in extra.items()}
        uit["V2 bevestigd in #32.17"] = {s: len(eerder[s]) for s in SETS_V2}
        uit["V2 extra bevestigd"] = {f"{s} bij {n}": len(extra.get((s, n), set())) for s in SETS_V2
                                     for n in KANDIDATEN[1:]}
        extra = collections.defaultdict(set, extra)
        uit["V2 verwacht vals"] = _verwacht(uit["V2"])
        n_beste = max(KANDIDATEN[1:], key=lambda n: (len(extra[("R3", n)]), -n))
        uit["V2 beslissing"] = {"n": n_beste, **v2_beslissing(len(extra[("R3", n_beste)]),
                                                               uit["V2 verwacht vals"][str(n_beste)])}
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def _eerder_bevestigd(labels: dict[str, str]) -> dict[str, set]:  # pragma: no cover - op de bestanden van #32.17
    """Per set de claims (N: screenshots) die #32.17 na de reparatie al bevestigde in de eigen check."""
    vragen, paren, stijl = bb._stand()
    opnieuw = {r["sleutel"]: {k: r[k] for k in ("punten", "dekking", "punten500", "dekking500")}
               for r in _jsonl(bb.MAP / "paren-v2.jsonl") if "punten" in r}
    per_id = {(v["set"], v["id"]): v for v in vragen}
    uit = collections.defaultdict(set)
    for p in bb.herberekend(paren, opnieuw):
        v = per_id.get((p["set"], p["vraag"]))
        if v and p["set"] in SETS_V2 and bb.telt(p, stijl) and bb.bevestigd(p) \
                and labels.get(bb.labelsleutel(p)) == GEVONDEN and p["groep"] in v["groepen"]:
            uit[p["set"]].add(v.get("claim_id") or v["id"])
    return uit


def _verwacht(v2: dict) -> dict:  # pragma: no cover - op de bestanden van #32.17
    """De kans per paar uit #32.17 na de reparatie (valse bevestigingen in de beslissende sets gedeeld door de paren
    die tellen), maal de artikelen per vraag en de beelden per artikel."""
    vragen, paren, stijl = bb._stand()
    na = json.loads((bb.MAP / "uitslag.json").read_text(encoding="utf-8"))["na de reparatie"]["hoofd"]
    vals = sum(na[s]["vals paren"] for s in bb.BESLISSEND)
    tellend = sum(1 for p in paren if p["set"] in bb.BESLISSEND and bb.telt(p, stijl))
    artikelen = [a for a in _jsonl(bb.MAP / "artikelen.jsonl") if a["beelden"]]
    per_artikel = sum(len(a["beelden"]) for a in artikelen) / len(artikelen)
    kans = vals / tellend
    alle = list(v2.values())
    uit = {"kans per paar (#32.17 na de reparatie)": kans, "vals": vals, "paren die tellen": tellend,
           "beelden per artikel": round(per_artikel, 2)}
    for n in KANDIDATEN:
        per_vraag = sum(s[str(n)]["artikelen per vraag"] * s[str(n)]["vragen"] for s in alle) / \
            sum(s[str(n)]["vragen"] for s in alle)
        uit[str(n)] = round(verwacht_vals(kans, per_vraag, per_artikel), 3)
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Drie voormetingen voor de volgende beeldronde (PLAN #32.20)")
    parser.add_argument("stap", choices=("r2", "paren", "kandidaten", "lezen", "tellen"))
    parser.add_argument("--set", dest="sets", action="append", choices=SETS_V2,
                        help="kandidaten: alleen deze set(s)")
    parser.add_argument("--proef", type=int, default=0, help="een kleine proef, naar een eigen bestand")
    args = parser.parse_args()
    if args.stap == "r2":
        _r2(args.proef)
    elif args.stap == "paren":
        _paren(args.proef)
    elif args.stap == "kandidaten":
        _kandidaten(args.sets or list(SETS_V2), args.proef)
    elif args.stap == "lezen":
        _lezen()
    else:
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
