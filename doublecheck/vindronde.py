"""De vindronde (PLAN #32.21): de eigen check vinden met vier sleutels, de rol van elk beeld en een meetkopie van de
database met FACTors en route A.

Per vraag vier sleutels, elk de beste 5: (1) de tekst en (2) de beschrijving van de foto tegen de claims, zoals #32.17,
in de productie en in de meetkopie; (3) de tekst en (4) de beschrijving tegen wat op de virale beelden in de
factcheckartikelen van de pool staat. Het beeld zoekt niet zelf (#32.20 V1); het bevestigt alleen op een beeld dat in
zijn artikel het virale beeld is (`beeldrolvraag`).

Op schijf nooit een beeld (B35) en nooit de gelezen tekst van een kopie (DR3); wel de vingerafdruk van die tekst, en de
tekst op een viraal beeld uit een openbaar factcheckartikel. De punten van vragen en pool gaan weg na `tellen`.

    python -m doublecheck.vindronde set|kopie|vision
    python -m doublecheck.hittewacht -- python -m doublecheck.vindronde vragen|pool
    python -m doublecheck.vindronde rollen indienen|ophalen
    python -m doublecheck.hittewacht -- python -m doublecheck.vindronde viraal indienen
    python -m doublecheck.vindronde viraal ophalen
    python -m doublecheck.hittewacht -- python -m doublecheck.vindronde zoeken|vergelijken
    python -m doublecheck.vindronde lezen|tellen|opruimen
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import shutil
import sqlite3
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import numpy as np

from doublecheck import beeldbevestiging as bb
from doublecheck import beeldindexmeting as bm
from doublecheck import beeldvoormeting as bvm
from doublecheck import beeldvraag as bv
from doublecheck.eigenaanvoer import adres

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "vindronde"
KOPIE = MAP / "kopie.db"
PRODUCTIE = WORTEL / "doublecheck.db"
LABELS = WORTEL / "docs" / "steekproeven" / "32.21-vindronde.json"
ROUTE_A = WORTEL / "data" / "aanvoer" / "proef" / "checks.jsonl"
FACTORS = WORTEL / "data" / "extern" / "factors" / "FACTors.csv"
M4FC = WORTEL / "data" / "extern" / "m4fc" / "M4FC.json"
BUDGET = 5.0                       # PO 2026-11-01: "the $5 limit"
GEVONDEN, ANDERE, VALS = bm.GEVONDEN, bm.ANDERE, bm.VALS
LABELWAARDEN = bm.LABELWAARDEN

# vooraf vastgelegd in PLAN #32.21; niet bijstellen na de uitslag
R4_N, R4_ZAAD = 100, 3221
F_N, F_ZAAD = 100, 3222
POOL_N, POOL_ZAAD = 5000, 3223
ROL_N, ROL_ZAAD, ROL_193 = 100, 3224, 50
PO_N, PO_ZAAD = 30, 3225
# #32.25: de beelden die bij N en R3 de eigen check bevestigen maar geen viraal heten, en wanneer de rolronde volgt
ROL_SETS, ROL_VIRAAL_DEEL, ROL_N, ROL_R3 = ("N", "R3"), 0.5, 31, 22
ROLLABELS = WORTEL / "docs" / "steekproeven" / "32.25-rol.json"
# #32.26: de rolronde met rol-v3 (elk beeld aan Haiku); vooraf vastgelegd, niet bijstellen na de uitslag
ROLRONDE_BUDGET, ROLRONDE_PROEF = 2.0, 10
ROLRONDE_PRECISIE, ROLRONDE_RECALL, ROLRONDE_42_VIRAAL, ROLRONDE_42_VALS = 0.95, 0.85, 17, 1
ROLRONDE_N, ROLRONDE_R3 = 31, 22
ROLRONDELABELS = WORTEL / "docs" / "steekproeven" / "32.26-rolronde.json"
WAAROM_N, WAAROM_ZAAD = 30, 3226
TOP, TOP_RANG = 5, 20
SLEUTELS = ("tekst", "beschrijving", "beeldtekst", "beeldbeschrijving")
MODI = ("productie", "kopie")
SETS = ("N", "R3", "R4", "F", "W", "S1", "S2", "S3", "S4")
PER_CLAIM = frozenset({"R3", "R4", "F"})
EIS_CLAIMS, EIS_N = 30, 29
ROL_PRECISIE, ROL_RECALL = 0.95, 0.85
MIN_TEKENS = bb.MIN_TEKENS
SCHATTING_ROL, SCHATTING_BESCHRIJVING = 0.00015, 0.00015   # per vraag in de batch, ruim (#32.17)
SCHATTING_ROL_BEELD = 0.0003       # rol-v2: met het deelbeeld, ~1.000 à 1.400 beeldtokens erbij, ruim
MAX_BATCH_BYTES = 100_000_000      # ruim onder de grens van de Batch API (256 MB)


class Weigering(Exception):
    """Doorgaan kan niet: de productie als kopie, een paar zonder label, of de grens."""


# --- de sets ----------------------------------------------------------------------------------------------

def r4_keuze(checks: list[dict], n: int = R4_N, zaad: int = R4_ZAAD) -> list[dict]:
    """Uit de proef van route A: Engels, een beeldwoord in de bewering (de regel van R2), een host die we mogen
    ophalen; elk artikel één keer; altijd dezelfde."""
    gezien, lijst = set(), []
    for c in sorted(checks, key=lambda c: (c["adres"], c.get("bewering") or "")):
        a = adres(c["adres"])
        if c.get("taal") == "en" and bm.BEELDWOORDEN.search(c.get("bewering") or "") \
                and bm.host(c["adres"]) not in bm.UITGESLOTEN and a not in gezien:
            gezien.add(a)
            lijst.append(c)
    return sorted(random.Random(zaad).sample(lijst, min(n, len(lijst))), key=lambda c: c["adres"])


def f_keuze(m4fc: list[dict], bekend: set[str], factors: dict[str, str], gebruikt: set[int], n: int = F_N,
            zaad: int = F_ZAAD) -> list[int]:
    """De beelden uit M4FC waarvan de check in FACTors staat en niet in de database, Engels, nog niet gebruikt in N, W
    of S3; altijd dezelfde."""
    lijst = [i for i, x in enumerate(m4fc) if (x.get("fc_language") or "english") == "english" and i not in gebruikt
             and (a := adres(x.get("article_url") or "")) in factors and a not in bekend]
    return sorted(random.Random(zaad).sample(lijst, min(n, len(lijst))))


# --- de meetkopie ---------------------------------------------------------------------------------------------

def controleer_kopie(pad: Path, productie: Path = PRODUCTIE) -> None:
    """De meetkopie is nooit de database van de resolver: daar komt iets pas met een release (B22)."""
    if Path(pad).resolve() == Path(productie).resolve():
        raise Weigering(f"{pad} is de database van de resolver; de checks van #32.21 komen alleen in een meetkopie")


def _claim_id(voorvoegsel: str, url: str, tekst: str) -> str:
    return voorvoegsel + hashlib.sha1(f"{adres(url)}|{tekst}".encode()).hexdigest()[:16]


def nieuwe_checks(factors: list[dict], route_a: list[dict], bekend: set[str]) -> list[dict]:
    """De checks van FACTors en route A die de database nog niet heeft (op adres), elk met een vaste id."""
    from doublecheck.verdicts import normalize_verdict

    uit, gezien = [], set()
    for bron, rijen, velden in (("FACTors", factors, ("url", "claim", "organisation", "original_verdict",
                                                       "date_published")),
                                ("route A", route_a, ("adres", "bewering", "uitgever", "oordeel", "datum"))):
        voor = "fac-" if bron == "FACTors" else "ra-"
        for r in rijen:
            url, tekst, uitgever, oordeel, datum = (r.get(v) or "" for v in velden)
            tekst = " ".join(tekst.split())
            if not url or not tekst or adres(url) in bekend:
                continue
            cid = _claim_id(voor, url, tekst)
            if cid in gezien:
                continue
            gezien.add(cid)
            uit.append({"claim_id": cid, "tekst": tekst, "taal": "en" if bron == "FACTors" else (r.get("taal") or ""),
                        "uitgever": uitgever, "oordeel": normalize_verdict(oordeel, bm.host(url)),
                        "oordeel_origineel": oordeel, "url": url, "datum": datum[:10], "bron": bron})
    return uit


# --- sleutel 3 en 4 ------------------------------------------------------------------------------------------

def virale(items: list[dict], rollen: dict[tuple[str, str], str]) -> list[dict]:
    """Alleen de beelden die in hun artikel het virale beeld zijn."""
    return [i for i in items if rollen.get((i["artikel"], i["beeld"])) == "viraal"]


def extra_zoekvragen(gehaald: list[dict]) -> list[str]:
    """De beweringen en hun zoekvragen, naast de tekst zelf (zoals `geheugen_met`, zonder de tekst)."""
    from doublecheck.beweringvraag import zoekvragen

    return zoekvragen("", gehaald)


def beste_artikelen(scores: np.ndarray, artikelen: list[str], n: int = TOP,
                    toegestaan: set[str] | None = None) -> list[tuple[str, float]]:
    """Per artikel de hoogste score van zijn beelden, de n beste artikelen (alleen de toegestane)."""
    beste: dict[str, float] = {}
    for s, a in zip(scores.tolist(), artikelen):
        if (toegestaan is None or a in toegestaan) and s > beste.get(a, -2.0):
            beste[a] = s
    return [(a, round(s, 4)) for a, s in sorted(beste.items(), key=lambda x: (-x[1], x[0]))[:n]]


# --- tellen ----------------------------------------------------------------------------------------------------

def labelsleutel(p: dict) -> str:
    return f"{p['set']}|{p['vraag']}|{p['beeld']}"


def _telt(p: dict, rollen: dict, modus: str) -> bool:
    return bool(p["via"].get(modus)) and not p["uitgesloten"] and bb.bevestigd(p) \
        and rollen.get((p["artikel"], p["beeld"])) == "viraal"


def te_lezen(paren: list[dict], labels: dict[str, str], rollen: dict) -> list[dict]:
    """Elke bevestiging die telt (in een van beide modi) en nog geen label heeft, elk paar één keer."""
    uit, gezien = [], set()
    for p in paren:
        k = labelsleutel(p)
        if k not in labels and k not in gezien and any(_telt(p, rollen, m) for m in MODI):
            gezien.add(k)
            uit.append(p)
    return uit


def telling(vragen: list[dict], paren: list[dict], labels: dict[str, str], rollen: dict, modus: str) -> dict:
    """Per set: gevonden (per claim bij R3, R4 en F, anders per vraag) als een viraal beeld de eigen check bevestigt en
    gelezen is als zelfde beeld, zelfde bewering; via welke sleutel; elders; andere bewering; vals per vraag en per
    paar. Weigert zolang een bevestiging die telt geen label heeft."""
    open_ = sorted({labelsleutel(p) for p in paren if _telt(p, rollen, modus) and labelsleutel(p) not in labels})
    if open_:
        raise Weigering(f"{len(open_)} bevestigingen zonder label in {LABELS.name} ({modus}), bijvoorbeeld {open_[0]}")
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    uit = {}
    for set_ in SETS:
        vs = [v for v in vragen if v["set"] == set_]
        if not vs:
            continue
        gevonden, elders, via = set(), set(), collections.defaultdict(set)
        vals_vragen, vals_paren, andere = set(), 0, 0
        for p in paren:
            v = per_vraag.get((p["set"], p["vraag"]))
            if p["set"] != set_ or v is None or not _telt(p, rollen, modus):
                continue
            eenheid = v.get("claim_id") if set_ in PER_CLAIM else v["id"]
            oordeel = labels[labelsleutel(p)]
            if oordeel == GEVONDEN:
                if set(p["groepen"].get(modus) or []) & set(v["eigen"][modus]):
                    gevonden.add(eenheid)
                    for s in p["via"][modus]:
                        via[s].add(eenheid)
                else:
                    elders.add(eenheid)
            elif oordeel == ANDERE:
                andere += 1
            else:
                vals_vragen.add(v["id"])
                vals_paren += 1
        uit[set_] = {"vragen": len(vs), "claims": len({v["claim_id"] for v in vs}) if set_ in PER_CLAIM else None,
                     "gevonden": len(gevonden), **{f"via {s}": len(via[s]) for s in SLEUTELS},
                     "gevonden elders": len(elders - gevonden), "andere bewering": andere, "vals": len(vals_vragen),
                     "vals paren": vals_paren}
    return uit


def _vals_goed(t: dict) -> bool:
    vragen = sum(s["vragen"] for s in t.values())
    vals = sum(s["vals"] for s in t.values())
    return t.get("W", {}).get("vals", 0) == 0 and vals * 1000 <= vragen \
        and t.get("N", {}).get("gevonden", EIS_N) >= EIS_N


def eisen(productie: dict, kopie: dict, rol: dict, po_verschillen: int | None) -> dict:
    e = {"1. R3": productie["R3"]["gevonden"] >= EIS_CLAIMS,
         "2. R4": kopie["R4"]["gevonden"] >= EIS_CLAIMS,
         "3. F": kopie["F"]["gevonden"] >= EIS_CLAIMS,
         "4. vals": _vals_goed(productie) and _vals_goed(kopie),
         "5. de rol": rol["viraal precisie"] >= ROL_PRECISIE and rol["viraal recall"] >= ROL_RECALL,
         "6. de PO": po_verschillen is not None and po_verschillen <= 1}
    return {**e, "gehaald": all(e.values())}


def rol_voormeting_beelden(vragen: list[dict], paren: list[dict], rollen: dict, sets=ROL_SETS,
                           modus: str = "productie") -> list[dict]:
    """De beelden die bij een vraag van N of R3 zonder vondst de eigen check bevestigen maar geen viraal heten (#32.25),
    met alle bevestigingen van N en R3 op die beelden: die tellen mee zodra de rol viraal wordt, dus die krijgen een
    label."""
    per_vraag = collections.defaultdict(list)
    for p in paren:
        per_vraag[(p["set"], p["vraag"])].append(p)
    gekozen = set()
    for v in vragen:
        if v["set"] not in sets:
            continue
        eigen = set(v["eigen"][modus])
        ep = [p for p in per_vraag[(v["set"], v["id"])] if set(p["groepen"].get(modus) or []) & eigen
              and p["via"].get(modus)]
        if any(_telt(p, rollen, modus) for p in ep):
            continue
        gekozen |= {(p["artikel"], p["beeld"]) for p in ep if bb.bevestigd(p) and not p["uitgesloten"]}
    uit = {k: {"artikel": k[0], "beeld": k[1], "paren": []} for k in sorted(gekozen)}
    for p in paren:
        k = (p["artikel"], p["beeld"])
        if k in uit and p["set"] in sets and p["via"].get(modus) and bb.bevestigd(p) and not p["uitgesloten"]:
            if labelsleutel(p) not in uit[k]["paren"]:
                uit[k]["paren"].append(labelsleutel(p))
    return list(uit.values())


def met_gelezen_rollen(rollen: dict, gelezen: dict[str, str]) -> dict:
    """De rollen van Haiku, met de gelezen rol waar die er is (sleutel artikel|beeld)."""
    uit = dict(rollen)
    for k, rol in gelezen.items():
        artikel, beeld = k.split("|", 1)
        uit[(artikel, beeld)] = rol
    return uit


def rol_voorwaarden(gelezen_rollen: list[str], n_gevonden: int, r3_gevonden: int) -> dict:
    """Wanneer de rolronde volgt, zoals vooraf vastgelegd in PLAN #32.25: minstens de helft van de gelezen beelden is
    echt viraal, en met die rollen haalt N 31 of R3 22."""
    een = sum(r == "viraal" for r in gelezen_rollen) >= ROL_VIRAAL_DEEL * len(gelezen_rollen) > 0
    twee = n_gevonden >= ROL_N or r3_gevonden >= ROL_R3
    return {"1. de helft viraal": een, "2. N 31 of R3 22": twee, "ronde": een and twee}


def rolronde_artikelen(paren: list[dict], gelezen: list[str]) -> list[str]:
    """De artikelen die `rol-v3` ziet (#32.26): elk artikel met een beeld waarop een bevestiging ligt, en elk artikel van
    een gelezen beeld (sleutel artikel|beeld). Zo hangt elke telling alleen van `rol-v3` af."""
    uit = {p["artikel"] for p in paren if bb.bevestigd(p) and not p["uitgesloten"] and any(p["via"].get(m) for m in MODI)}
    uit |= {k.split("|", 1)[0] for k in gelezen}
    return sorted(uit)


def rolronde_eisen(lees125: dict[str, str], v3_125: dict[str, str], lees42: dict[str, str], v3_42: dict[str, str],
                   voor_p: dict, voor_k: dict, na_p: dict, na_k: dict) -> dict:
    """De eisen van de rolronde zoals vooraf vastgelegd in PLAN #32.26."""
    r = rol_telling(lees125, v3_125)
    een = r["viraal precisie"] >= ROLRONDE_PRECISIE and r["viraal recall"] >= ROLRONDE_RECALL
    viraal = [k for k, rol in lees42.items() if rol == "viraal"]
    anders = [k for k, rol in lees42.items() if rol != "viraal"]
    twee = sum(v3_42.get(k) == "viraal" for k in viraal) >= ROLRONDE_42_VIRAAL \
        and sum(v3_42.get(k) == "viraal" for k in anders) <= ROLRONDE_42_VALS

    def gevonden(t, s):
        return t.get(s, {}).get("gevonden", 0)

    def behoud(n):
        return (9 * n + 9) // 10

    drie = gevonden(na_p, "N") >= ROLRONDE_N and gevonden(na_p, "R3") >= ROLRONDE_R3 \
        and gevonden(na_k, "R4") >= behoud(gevonden(voor_k, "R4")) and gevonden(na_k, "F") >= behoud(gevonden(voor_k, "F"))

    def vals(t):
        return sum(v.get("vals", 0) for v in t.values() if isinstance(v, dict))

    vier = all(na.get("W", {}).get("vals", 0) == 0 and vals(na) <= vals(voor) for voor, na in ((voor_p, na_p),
                                                                                                (voor_k, na_k)))
    return {"1. de 125": een, "2. de 42": twee, "3. gevonden": drie, "4. vals": vier,
            "gehaald": een and twee and drie and vier}


def rol_per_soort(gelezen: dict[str, str], voorspeld: dict[str, str], deelbeelden: set[str]) -> dict:
    """De rol apart voor de deelbeelden (die `rol-v2` zelf ziet) en voor de andere beelden (alleen hun tekst)."""
    return {"deelbeelden": rol_telling({k: r for k, r in gelezen.items() if k in deelbeelden}, voorspeld),
            "andere beelden": rol_telling({k: r for k, r in gelezen.items() if k not in deelbeelden}, voorspeld)}


def rol_telling(gelezen: dict[str, str], voorspeld: dict[str, str]) -> dict:
    """Hoe vaak *viraal* juist is (precisie) en hoeveel virale beelden Haiku vindt (recall), op de gelezen beelden."""
    tp = sum(r == "viraal" and voorspeld.get(k) == "viraal" for k, r in gelezen.items())
    pv = sum(voorspeld.get(k) == "viraal" for k in gelezen)
    gv = sum(r == "viraal" for r in gelezen.values())
    verwarring = collections.Counter(f"{r} -> {voorspeld.get(k, '?')}" for k, r in gelezen.items())
    return {"gelezen": len(gelezen), "viraal precisie": tp / pv if pv else 0.0, "viraal recall": tp / gv if gv else 0.0,
            "verwarring": dict(verwarring.most_common())}


def po_keuze(sleutels: list[str], n: int = PO_N, zaad: int = PO_ZAAD) -> list[str]:
    """De steekproef die de PO nakijkt: altijd dezelfde, welke volgorde de sleutels ook hebben (eis 6)."""
    alle = sorted(set(sleutels))
    return sorted(random.Random(zaad).sample(alle, n)) if len(alle) > n else alle


def po_verschillen(mijn: dict[str, str], po: dict[str, str], sleutels: list[str]) -> int:
    """Hoe vaak het label van de PO anders is dan dat van Claude; weigert zolang de PO er een niet gelezen heeft."""
    open_ = [k for k in sleutels if k not in po]
    if open_:
        raise Weigering(f"de PO heeft {len(open_)} van de {len(sleutels)} nog niet gelezen")
    return sum(po[k] != mijn.get(k) for k in sleutels)


# --- de bestanden ------------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return bm._jsonl(pad)


def schrijf(pad: Path, regels: list[dict]) -> None:
    bvm.schrijf(pad, regels)


def schrijf_vraag(pad: Path, regel: dict) -> None:
    """Een vraag op schijf: nooit haar tekst (DR3), nooit een beeld (B35)."""
    if "tekst" in regel:
        raise ValueError("de gelezen tekst van een kopie gaat nooit naar schijf (DR3)")
    schrijf(pad, [regel])


def _sha(*delen: str) -> str:
    return hashlib.sha1("|".join(delen).encode()).hexdigest()[:24]


def _puntpad(soort: str, *delen: str) -> Path:
    return MAP / "punten" / soort / (_sha(*delen) + ".npz")


def lees_labels() -> dict:
    if not LABELS.exists():
        return {"labels": {}, "rollen": {}, "waarom": {}}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    fout = {k: v for k, v in d.get("labels", {}).items() if v not in LABELWAARDEN}
    if fout:
        raise Weigering(f"onbekende labels in {LABELS.name}: {list(fout.items())[:3]}")
    return d


def _paarlabels(d: dict) -> dict[str, str]:
    """De eigen labels, en die van #32.15, #32.17 en #32.20 voor hetzelfde paar."""
    oud = bvm.lees_labels()
    return {**oud, **d.get("labels", {})}


def _rollen() -> dict[tuple[str, str], str]:
    uit = {}
    for r in _jsonl(MAP / "rollen.jsonl"):
        for b, rol in zip(r["beelden"], r["rollen"]):
            uit[(r["artikel"], b)] = rol
    return uit


def _factors_rijen() -> list[dict]:
    import csv

    csv.field_size_limit(10_000_000)
    with FACTORS.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _conn(pad: Path, lezen: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{pad}?mode=ro", uri=True, check_same_thread=False) if lezen else sqlite3.connect(pad)
    conn.row_factory = sqlite3.Row
    return conn


def _groepen_per_adres(conn: sqlite3.Connection) -> dict[str, set[str]]:
    groep = {r[0]: r[1] for r in conn.execute("SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
    uit = collections.defaultdict(set)
    for cid, url in conn.execute("SELECT claim_id, url FROM factcheck"):
        if cid in groep:
            uit[adres(url)].add(groep[cid])
    return uit


def al_uitgegeven() -> float:
    """Haiku live (in de vragen), de batches (werkelijk, anders de schatting) en Google Vision tegen de lijstprijs."""
    live = sum(r.get("kosten") or 0 for r in _jsonl(MAP / "vragen.jsonl"))
    batches = sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
                  for naam in ("rollen-batches.jsonl", "viraal-batches.jsonl") for b in _jsonl(MAP / naam))
    vision = sum(len(r.get("antwoorden") or []) for r in _jsonl(MAP / "vision.jsonl"))
    return live + batches + vision * bb.VISIEPRIJS


def _grens(erbij: float = 0.0) -> None:
    if al_uitgegeven() + erbij > BUDGET - 0.05:
        raise Weigering(f"de grens: ${al_uitgegeven():.2f} plus ${erbij:.2f} komt boven ${BUDGET:.2f}")


# --- de beelden in een artikel, met de tekst eromheen --------------------------------------------------------

class _Context(HTMLParser):
    """Een doorlopende stroom van tekst en beelden, met per beeld zijn alt-tekst en het onderschrift van zijn figuur."""

    _OVERSLAAN = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form"}

    def __init__(self, basis: str):
        super().__init__(convert_charrefs=True)
        self.basis, self.stroom, self.titel = basis, [], ""
        self._weg = 0
        self._figuren: list[list[dict]] = []
        self._onderschrift: list[str] | None = None
        self._in_titel = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in self._OVERSLAAN:
            self._weg += 1
        elif tag == "title":
            self._in_titel = True
        elif tag == "figure":
            self._figuren.append([])
        elif tag == "figcaption":
            self._onderschrift = []
        elif tag == "img" and not self._weg:
            bronnen = [a.get(k) for k in ("src", "data-src", "data-lazy-src") if a.get(k)]
            if a.get("srcset"):
                bronnen += [d.strip().split()[0] for d in a["srcset"].split(",") if d.strip()]
            beeld = {"bronnen": {urljoin(self.basis, b.strip()) for b in bronnen}, "alt": a.get("alt", ""),
                     "titel": a.get("title", ""), "plek": len(self.stroom), "onderschrift": ""}
            self.stroom.append(beeld)
            if self._figuren:
                self._figuren[-1].append(beeld)

    def handle_endtag(self, tag):
        if tag in self._OVERSLAAN and self._weg:
            self._weg -= 1
        elif tag == "title":
            self._in_titel = False
        elif tag == "figcaption" and self._onderschrift is not None:
            tekst = " ".join(" ".join(self._onderschrift).split())
            for b in (self._figuren[-1] if self._figuren else []):
                b["onderschrift"] = tekst
            self._onderschrift = None
        elif tag == "figure" and self._figuren:
            self._figuren.pop()

    def handle_data(self, data):
        if self._in_titel:
            self.titel += data
        if self._weg:
            return
        if self._onderschrift is not None:
            self._onderschrift.append(data)
        elif data.strip():
            self.stroom.append(data)


def beelden_met_context(html: str, basis: str) -> tuple[str, list[dict]]:
    """De titel en de beelden van een artikel zoals `artikelbeelden.beelden_uit_artikel` ze kiest (het deelbeeld
    eerst, hoogstens `MAX_BEELDEN`), elk met zijn alt-tekst, onderschrift en de tekst ervoor en erna."""
    from doublecheck.artikelbeelden import beelden_uit_artikel
    from doublecheck.beeldrolvraag import MAX_CONTEXT

    lezer = _Context(basis)
    lezer.feed(html)
    teksten = [(i, x) for i, x in enumerate(lezer.stroom) if isinstance(x, str)]
    uit = []
    for nr, b_adres in enumerate(beelden_uit_artikel(html, basis)[:bm.MAX_BEELDEN]):
        b = next((x for x in lezer.stroom if isinstance(x, dict) and b_adres in x["bronnen"]), None)
        if b is None:
            uit.append({"beeld": b_adres, "alt": "", "onderschrift": "", "voor": "", "na": "", "deel": nr == 0})
            continue
        voor = " ".join(t for i, t in teksten if i < b["plek"])[-MAX_CONTEXT:]
        na = " ".join(t for i, t in teksten if i > b["plek"])[:MAX_CONTEXT]
        uit.append({"beeld": b_adres, "alt": b["alt"] or b["titel"], "onderschrift": b["onderschrift"],
                    "voor": " ".join(voor.split()), "na": " ".join(na.split()), "deel": False})
    return " ".join(lezer.titel.split()), uit


# --- set, kopie en Vision (netwerk) --------------------------------------------------------------------------

def _lees_set() -> dict:
    pad = MAP / "set.json"
    if not pad.exists():
        raise Weigering("eerst: python -m doublecheck.vindronde set")
    return json.loads(pad.read_text(encoding="utf-8"))


def _set() -> dict:  # pragma: no cover - op de bestanden
    ra = _jsonl(ROUTE_A)
    m4fc = json.loads(M4FC.read_text(encoding="utf-8"))
    prod = _conn(PRODUCTIE)
    bekend = {adres(u) for (u,) in prod.execute("SELECT url FROM factcheck")}
    rijen = _factors_rijen()
    factors: dict[str, str] = {}
    for r in rijen:
        factors.setdefault(adres(r["url"]), r["organisation"])
    s17 = bb._lees_set()
    gebruikt = {int(Path(x["beeld"]).stem) for k in ("N", "W") for x in s17[k]} \
        | {int(x["id"]) for x in s17["S3"] if str(x["id"]).isdigit()}
    per_adres = collections.defaultdict(list)
    for c in nieuwe_checks(rijen, ra, bekend):
        per_adres[adres(c["url"])].append(c["claim_id"])
    uit = {"R4": [{"id": adres(c["adres"]), "claim_id": adres(c["adres"]), "url": c["adres"], "bewering": c["bewering"],
                   "uitgever": c.get("uitgever"), "datum": c.get("datum"), "eigen_kopie": per_adres[adres(c["adres"])]}
                  for c in r4_keuze(ra)],
           "F": [{"id": str(i), "claim_id": str(i), "url": m4fc[i]["article_url"], "claim": m4fc[i]["claim"],
                  "adressen": [a for a in (m4fc[i].get("image_url"), m4fc[i].get("wayback_image_url")) if a],
                  "uitgever": factors[adres(m4fc[i]["article_url"])],
                  "eigen_kopie": per_adres[adres(m4fc[i]["article_url"])]}
                 for i in f_keuze(m4fc, bekend, factors, gebruikt)]}
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / "set.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return {s: len(v) for s, v in uit.items()} | {"R4 zonder eigen check in de kopie": sum(
        not c["eigen_kopie"] for c in uit["R4"]), "F zonder eigen check in de kopie": sum(
        not c["eigen_kopie"] for c in uit["F"])}


def _kopie() -> None:  # pragma: no cover - op de database, met het model
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.storage import save_text_fingerprint
    from doublecheck.toelating import per_reden, staat_aan

    controleer_kopie(KOPIE)
    MAP.mkdir(parents=True, exist_ok=True)
    if not KOPIE.exists():
        with _conn(PRODUCTIE) as van, sqlite3.connect(KOPIE) as naar:
            van.backup(naar)
        print(f"kopie van {PRODUCTIE.name} gemaakt", flush=True)
    conn = _conn(KOPIE, lezen=False)
    if staat_aan(conn):
        # de kopie doorzoekt wat de productie doorzoekt, plus de nieuwe checks: wat de toelating weert, gaat eruit,
        # en dan gaat de toelating uit (een echte import laat een nieuwe uitgever eerst toe, B28)
        weg = sorted(per_reden(conn)["onbekende_uitgever"])
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executemany("DELETE FROM claim WHERE claim_id = ?", [(c,) for c in weg])
        conn.execute("DELETE FROM toelating")
        conn.commit()
        print(f"{len(weg)} claims die de productie niet doorzoekt, uit de kopie; toelating uit", flush=True)
    bekend = {adres(u) for (u,) in _conn(PRODUCTIE).execute("SELECT url FROM factcheck")}
    nieuw = nieuwe_checks(_factors_rijen(), _jsonl(ROUTE_A), bekend)
    al = {r[0] for r in conn.execute("SELECT claim_id FROM claim WHERE claim_id LIKE 'fac-%' OR claim_id LIKE 'ra-%'")}
    todo = [c for c in nieuw if c["claim_id"] not in al]
    versie = load_config(None).model_versions.text_embedding
    print(f"{len(nieuw)} nieuwe checks, {len(todo)} nog in te bedden", flush=True)
    begin = time.monotonic()
    for i in range(0, len(todo), 512):
        deel = todo[i:i + 512]
        for c, fp in zip(deel, fingerprint_texts([c["tekst"] for c in deel], versie)):
            conn.execute("INSERT INTO claim (claim_id, canonical_text, language, language_reported) VALUES (?, ?, ?, ?)",
                         (c["claim_id"], c["tekst"], c["taal"] or "und", c["taal"] or ""))
            conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                         " review_date, language, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (c["claim_id"], c["uitgever"] or "", c["oordeel"], c["oordeel_origineel"], c["url"],
                          c["datum"], c["taal"] or "und", c["bron"]))
            save_text_fingerprint(conn, c["claim_id"], fp)
        conn.commit()
        if (i // 512) % 20 == 0:
            print(f"  {i + len(deel)} van {len(todo)} in {time.monotonic() - begin:.0f} s", flush=True)
    print(f"klaar: {conn.execute('SELECT count(*) FROM claim').fetchone()[0]} claims in de kopie", flush=True)


def _vision() -> None:  # pragma: no cover - met Google Cloud Vision
    import base64
    import concurrent.futures as cf
    import os

    import httpx

    from doublecheck.beeldzoeken import MAX_RESULTATEN, VISION
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = os.environ.get("GOOGLE_VISION_API_KEY")
    if not sleutel:
        raise SystemExit("GOOGLE_VISION_API_KEY ontbreekt in .env")
    pad = MAP / "vision.jsonl"
    klaar = {(r["set"], r["id"]) for r in _jsonl(pad)}
    s = _lees_set()
    web, slot = bm.Beleefd(), threading.Lock()

    def zoek(inhoud: bytes) -> dict | None:
        verzoek = {"requests": [{"image": {"content": base64.b64encode(inhoud).decode()},
                                 "features": [{"type": "WEB_DETECTION", "maxResults": MAX_RESULTATEN}]}]}
        for poging in range(4):
            a = httpx.post(VISION, params={"key": sleutel}, json=verzoek, timeout=60)
            if a.status_code == 200:
                return a.json()
            if a.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"Vision {a.status_code}")
            time.sleep(5 * 2 ** poging)
        return None

    def doe(werk):
        for set_, c in werk:
            with slot:
                _grens(0.01)
            if set_ == "R4":
                status, adressen = bb._pagina(web, c["url"])
            else:
                status, adressen = "m4fc", list(c["adressen"])
            antwoorden = []
            for a in adressen:
                inhoud = web.beeld(a)
                if inhoud is None or not bb._groot_genoeg(inhoud):
                    continue
                antwoord = zoek(inhoud)
                del inhoud
                if antwoord is not None:
                    antwoorden.append({"beeld": a, **antwoord})
                if set_ == "F":   # één beeld per vraag: het beeld zelf, of anders zijn kopie in de Wayback Machine
                    break
            schrijf(pad, [{"set": set_, "id": c["id"], "status": status, "beelden": adressen,
                           "antwoorden": antwoorden}])
            print(f"{set_} {c['id'][:60]}: {status}, {len(antwoorden)} zoekvragen", flush=True)

    per_host = collections.defaultdict(list)
    for set_ in ("R4", "F"):
        for c in s[set_]:
            if (set_, c["id"]) not in klaar:
                per_host[bm.host(c["url"] if set_ == "R4" else c["adressen"][0])].append((set_, c))
    with cf.ThreadPoolExecutor(6) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"Vision: {sum(len(r['antwoorden']) for r in _jsonl(pad))} zoekvragen; ${al_uitgegeven():.2f}", flush=True)


def _kopieen() -> dict[str, list[dict]]:  # pragma: no cover - op de antwoorden van Vision
    """Per claim van R4 en F de kopieën van het open web, in volgorde, zonder factchecksites (zoals R3)."""
    sites = bm._factchecksites()
    s = _lees_set()
    per = {(set_, c["id"]): c for set_ in ("R4", "F") for c in s[set_]}
    uit = {"R4": [], "F": []}
    for r in _jsonl(MAP / "vision.jsonl"):
        c = per[(r["set"], r["id"])]
        for i, k in enumerate(bm.kopieen(r["antwoorden"], sites, bm.host(c["url"]))):
            uit[r["set"]].append({"id": f"{c['id']}#{i}", "set": r["set"], "vraag": k["beeld"],
                                  "adressen": [k["beeld"]], "claim_id": c["claim_id"], "soort": k["soort"],
                                  "pagina": k["pagina"], "rang": i, "eigen_kopie": c["eigen_kopie"]})
    return uit


# --- de vragen ---------------------------------------------------------------------------------------------------

def _vragen(sets: list[str], proef: int) -> None:  # pragma: no cover - netwerk en modellen
    import concurrent.futures as cf
    import dataclasses

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck import beschrijvingvraag as bs
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.modellen import MODELLEN
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    bb._rekenen()
    laad_sleutel()
    config = load_config(None)
    cfg = dataclasses.replace(config, berichtcontrole=dataclasses.replace(
        config.berichtcontrole, beweringen="beweringen-v1", beweringen_model=MODELLEN["haiku"]["id"]))
    versie = config.model_versions.text_embedding
    client = anthropic.Anthropic(max_retries=6)
    groep_prod = bb._groep_van()
    ronde = {s["id"]: s for s in _jsonl(bb.BEELDRONDE)}
    oud = [v for v in _jsonl(bb.MAP / "vragen.jsonl")]
    rekenen, lokaal, slot = threading.Lock(), threading.local(), threading.Lock()
    web = bm.Beleefd()
    pad, mislukt = MAP / "vragen.jsonl", MAP / "vragen.mislukt.jsonl"
    geprobeerd = {(r["set"], r["id"]) for r in _jsonl(pad) + _jsonl(mislukt)}

    def conn(modus):
        if not hasattr(lokaal, modus):
            setattr(lokaal, modus, connect(str(PRODUCTIE if modus == "productie" else KOPIE)))
        return getattr(lokaal, modus)

    def zoek(tekst, gehaald):
        with rekenen:
            fp = fingerprint_texts([tekst[:600]], versie)[0]
            lijsten = {m: bc.geheugen_met(conn(m), cfg, tekst, fp, gehaald) for m in MODI}
        return fp, {m: [{"claim": k["claim"], "url": k["url"], "gelijkenis": k["gelijkenis"],
                         "groep": groep_prod.get(k["claim"], k["claim"])} for k in lijst] for m, lijst in lijsten.items()}

    sjablonen: dict[str, bytes | None] = {}

    def beeld_van(w) -> bytes | None:
        if w["set"] in ("N", "W"):
            return Path(w["beeld"]).read_bytes()
        if w["set"] == "S4":
            sleutel = w["vraag"]
            if sleutel not in sjablonen:
                sjablonen[sleutel] = next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)
            return bb._meme(sjablonen[sleutel], w["onderschrift"]) if sjablonen[sleutel] else None
        return next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)

    def doe(w) -> None:
        nieuw = w["set"] in ("R4", "F")
        if nieuw:
            with slot:
                _grens(0.002)
        beeld = beeld_van(w)
        if beeld is None:
            schrijf(mislukt, [{"set": w["set"], "id": w["id"], "fout": "niet opgehaald"}])
            return
        try:
            begin, kosten = time.perf_counter(), 0.0
            if w["set"] in ("N", "W"):
                tekst = ronde[w["id"]]["tekst"]
            else:
                with rekenen:
                    tekst = bc.bericht_uit(None, beeld, config.ocr)
            tekens = len(tekst.strip())
            if nieuw:
                gehaald = []
                if tekens >= MIN_TEKENS:
                    gehaald, k = bc.beweringen_vragen(tekst, client, cfg, screenshot=True)
                    kosten += k
                a = client.messages.create(**bs.verzoek(beeld))
                kosten += bb._haiku_kosten(a)
                beschrijving = bs.lees_beschrijving("".join(getattr(b, "text", "") or "" for b in a.content))
            else:
                gehaald = w.get("beweringen") or []
                beschrijving = {"beschrijving": w["beschrijving"], "zoekvragen": w.get("zoekvragen") or []} \
                    if w.get("beschrijving") else None
            k1, fp = {m: [] for m in MODI}, None
            if tekens >= MIN_TEKENS:
                fp, k1 = zoek(tekst, gehaald)
            del tekst
            k2 = {m: [] for m in MODI}
            if beschrijving:
                _, k2 = zoek(beschrijving["beschrijving"], bs.als_beweringen(beschrijving))
            with rekenen:
                kenmerken, punten = bb._vraagkenmerken(beeld)
        except anthropic.APIError:
            raise
        except Exception as e:   # kapot of geen beeld: overslaan; alleen de soort fout, nooit de inhoud (DR3)
            schrijf(mislukt, [{"set": w["set"], "id": w["id"], "fout": type(e).__name__}])
            return
        finally:
            del beeld
        vpad = _puntpad(w["set"], w["id"])
        vpad.parent.mkdir(parents=True, exist_ok=True)
        vpad.write_bytes(bv.punten_naar_bytes(punten))
        if fp is not None:
            tpad = MAP / "vectoren" / w["set"] / (_sha(w["id"]) + ".npy")
            tpad.parent.mkdir(parents=True, exist_ok=True)
            np.save(tpad, np.asarray(fp.vector, dtype=np.float32))
        eigen_prod = list(w.get("groepen") or []) if w["set"] in ("N", "R3") else []
        regel = {"set": w["set"], "id": w["id"], "claim_id": w.get("claim_id"), "adressen": w.get("adressen") or [],
                 "beeld": w.get("beeld"), "vraag": w.get("vraag"), "onderschrift": w.get("onderschrift"),
                 "eigen": {"productie": eigen_prod, "kopie": eigen_prod or list(w.get("eigen_kopie") or [])},
                 "tekens": tekens, "beweringen": gehaald,
                 "beschrijving": beschrijving["beschrijving"] if beschrijving else None,
                 "zoekvragen": beschrijving["zoekvragen"] if beschrijving else [],
                 "tekstvector": fp.model_version if fp is not None else None,
                 "k1": k1, "k2": k2, **kenmerken, "kosten": round(kosten, 6),
                 "seconden": round(time.perf_counter() - begin, 3)}
        schrijf_vraag(pad, regel)
        with slot:
            print(f"{w['set']} {w['id'][:50]}: k1 {len(k1['productie'])}/{len(k1['kopie'])}, k2 "
                  f"{len(k2['productie'])}/{len(k2['kopie'])}, ${kosten:.4f}", flush=True)

    werk = [{**v, "groepen": v.get("groepen")} for v in oud if v["set"] in sets and v["set"] in SETS
            and v["set"] not in ("R4", "F")]
    nieuw = _kopieen()
    for set_ in ("R4", "F"):
        if set_ not in sets:
            continue
        gelukt = collections.Counter(r["claim_id"] for r in _jsonl(pad) if r["set"] == set_)
        per_claim = collections.Counter()
        for w in nieuw[set_]:   # tot elke claim vijf kopieën heeft die lukken, zoals R3
            if (set_, w["id"]) in geprobeerd or gelukt[w["claim_id"]] + per_claim[w["claim_id"]] >= bm.MAX_KOPIEEN:
                continue
            per_claim[w["claim_id"]] += 1
            werk.append(w)
    werk = [w for w in werk if (w["set"], w["id"]) not in geprobeerd]
    if proef:
        werk = [w for s in sets for w in [x for x in werk if x["set"] == s][:proef]]
    print(f"{len(werk)} vragen", flush=True)
    with cf.ThreadPoolExecutor(4) as pool:
        list(pool.map(doe, werk))
    print(f"klaar; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}", flush=True)


# --- de pool -----------------------------------------------------------------------------------------------------

def _pool_artikelen() -> dict[str, dict]:  # pragma: no cover - op de bestanden en de databases
    """Elk artikel van de pool één keer (op adres), met waarom het erin zit."""
    prod, kopie = _conn(PRODUCTIE), _conn(KOPIE)
    uit: dict[str, dict] = {}

    def voeg(url, reden):
        if url:
            uit.setdefault(adres(url), {"url": url, "redenen": set()})["redenen"].add(reden)

    vragen = _jsonl(MAP / "vragen.jsonl")
    eigen_n = {c for v in _jsonl(bb.MAP / "vragen.jsonl") if v["set"] == "N" for c in (v.get("eigen") or [])}
    for (url,) in prod.execute(f"SELECT url FROM factcheck WHERE claim_id IN ({','.join('?' * len(eigen_n))})",
                               sorted(eigen_n)):
        voeg(url, "eigen")
    for c in bb._lees_set()["R3"]:
        voeg(c["url"], "eigen")
    s = _lees_set()
    for c in s["R4"] + s["F"]:
        voeg(c["url"], "eigen")
    for v in vragen:
        for sleutel in ("k1", "k2"):
            for m in MODI:
                for k in v[sleutel][m]:
                    voeg(k["url"], "kandidaat")
    alle = sorted({adres(u): u for (u,) in kopie.execute("SELECT url FROM factcheck") if u}.items())
    eigen = {a for a, d in uit.items() if "eigen" in d["redenen"]}
    for a, u in random.Random(POOL_ZAAD).sample([x for x in alle if x[0] not in eigen], POOL_N):
        voeg(u, "willekeurig")
    for artikel, _ in _rol193():
        voeg(artikel, "§193")
    return uit


def _rol193() -> list[tuple[str, str]]:  # pragma: no cover - op de bestanden van #32.20
    """De artikelbeelden uit de paren van §193 die gelezen zijn als zelfde beeld met een andere bewering of als ander
    beeld: voor de toets van de rol."""
    labels = bvm.lees_labels()
    uit = set()
    for r in bvm._jsonl(bvm.MAP / "r2.jsonl"):
        for t in r["sift"] + r["copynce"]:
            if bvm.label(labels, r, t[0]) in (ANDERE, VALS):
                uit.add((t[2], t[0]))
    lijst = sorted(uit)
    return sorted(random.Random(ROL_ZAAD).sample(lijst, min(ROL_193, len(lijst))))


def _pool(max_artikelen: int | None) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    import cv2

    cv2.setNumThreads(2)    # hoogstens twee kernen (PO)
    apad, bpad = MAP / "pool-artikelen.jsonl", MAP / "pool-beelden.jsonl"
    klaar = {adres(a["url"]) for a in _jsonl(apad)}
    artikelen = _pool_artikelen()
    per_host = collections.defaultdict(list)
    for a, d in sorted(artikelen.items()):
        if a not in klaar:
            per_host[bm.host(d["url"])].append(d)
    if max_artikelen:
        per_host = {h: lijst[:1] for h, lijst in list(per_host.items())[:max_artikelen]}
    print(f"{sum(len(v) for v in per_host.values())} artikelen op {len(per_host)} hosts ({len(klaar)} al gedaan)",
          flush=True)
    web, rekenen, slot, teller = bm.Beleefd(), threading.Lock(), threading.Lock(), collections.Counter()

    def pagina(url):
        if bm.host(url) in bm.UITGESLOTEN:
            return "uitgesloten", "", []
        if not web.mag(url):
            return "verboden", "", []
        antwoord = web._vraag(url)
        if antwoord is None or antwoord.status_code != 200:
            return ("fout" if antwoord is None else antwoord.status_code), "", []
        try:
            titel, beelden = beelden_met_context(antwoord.text, str(antwoord.url))
            return 200, titel, beelden
        except Exception:   # een pagina die niet te lezen is
            return "onleesbaar", "", []

    def doe(lijst):
        for d in lijst:
            begin = time.monotonic()
            status, titel, beelden = pagina(d["url"])
            rijen = []
            for b in beelden:
                inhoud = web.beeld(b["beeld"])
                if inhoud is None:
                    continue
                try:
                    with rekenen:
                        kenm = bb.artikelbeeld(inhoud)
                    if min(kenm["breedte"], kenm["hoogte"]) >= bm.MIN_ZIJDE:
                        p = _puntpad("pool", d["url"], b["beeld"])
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(bv.punten_naar_bytes(kenm.pop("punten")))
                        rijen.append({"artikel": d["url"], **b, **{k: v for k, v in kenm.items() if k != "punten"}})
                except Exception as e:   # kapot of geen beeld: overslaan; alleen de soort fout (DR3)
                    with slot:
                        teller[f"fout {type(e).__name__}"] += 1
                del inhoud
            schrijf(bpad, rijen)
            schrijf(apad, [{"url": d["url"], "host": bm.host(d["url"]), "status": status, "titel": titel,
                            "beelden": [r["beeld"] for r in rijen], "redenen": sorted(d["redenen"]),
                            "seconden": round(time.monotonic() - begin, 1)}])
            with slot:
                teller["artikelen"] += 1
                teller["met beeld"] += bool(rijen)
                teller["beelden"] += len(rijen)
                if teller["artikelen"] % 200 == 0:
                    print(f"  {dict(teller)}", flush=True)

    with cf.ThreadPoolExecutor(12) as pool:
        # eerst de eigen artikelen: dan is vroeg bekend bij hoeveel claims het beeld ooit kan bevestigen
        for eigen in (True, False):
            lijsten = [[d for d in v if ("eigen" in d["redenen"]) == eigen] for v in per_host.values()]
            list(pool.map(doe, sorted((x for x in lijsten if x), key=len, reverse=True)))
            print(f"  {'eigen artikelen' if eigen else 'de rest'} klaar: {dict(teller)}", flush=True)
    print(f"klaar: {dict(teller)}", flush=True)


# --- de rol en de virale beelden (Batch API, openbare artikelen) ------------------------------------------------

def _batch_ophalen(naam: str, verwerk) -> None:  # pragma: no cover - netwerk
    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    alle = _jsonl(MAP / naam)
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog", flush=True)
            continue
        werkelijk, mis = 0.0, 0
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                mis += 1
                continue
            werkelijk += kosten_batch(bc.gebruik_uit(r.result.message), "haiku")
            verwerk(r.custom_id, "".join(getattr(x, "text", "") or "" for x in r.result.message.content))
        b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
        print(f"batch {b['id']}: ${werkelijk:.3f}, {mis} mislukt", flush=True)
    (MAP / naam).write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(f"samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}", flush=True)


def _claimtekst_per_adres() -> dict[str, str]:  # pragma: no cover - op de meetkopie
    uit: dict[str, str] = {}
    for url, tekst in _conn(KOPIE).execute(
            "SELECT f.url, c.canonical_text FROM factcheck f JOIN claim c USING (claim_id)"):
        uit.setdefault(adres(url), tekst)
    return uit


def _rollen_stap(stap: str, proef: int) -> None:  # pragma: no cover - netwerk
    from doublecheck import beeldrolvraag as br

    kaart = MAP / "rollen-kaart.jsonl"
    if stap == "indienen":
        import concurrent.futures as cf

        import anthropic

        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        ingediend = {r["custom_id"] for r in _jsonl(kaart)}
        per_artikel = collections.defaultdict(list)
        for b in _jsonl(MAP / "pool-beelden.jsonl"):
            per_artikel[b["artikel"]].append(b)
        titels = {a["url"]: a.get("titel") or "" for a in _jsonl(MAP / "pool-artikelen.jsonl")}
        claims = _claimtekst_per_adres()
        werk = [(a, beelden) for a, beelden in sorted(per_artikel.items()) if "rol-" + _sha(a) not in ingediend]
        werk = werk[:proef] if proef else werk
        print(f"{len(werk)} artikelen, waarvan {sum(any(b.get('deel') for b in x) for _, x in werk)} met een deelbeeld",
              flush=True)
        web, slot = bm.Beleefd(), threading.Lock()
        wachtrij: list[dict] = []
        status_teller: collections.Counter = collections.Counter()

        def dien_in(alles: bool = False):
            # hoogstens 800 vragen of ~100 MB per batch: met een beeld erin is een vraag ~150 kB
            while wachtrij and (alles or len(wachtrij) >= 800
                                or sum(d["grootte"] for d in wachtrij) >= MAX_BATCH_BYTES):
                deel, grootte = [], 0
                while wachtrij and len(deel) < 800 and grootte < MAX_BATCH_BYTES:
                    deel.append(wachtrij.pop(0))
                    grootte += deel[-1]["grootte"]
                schatting = sum(SCHATTING_ROL_BEELD if d["versie"] == "rol-v2" else SCHATTING_ROL for d in deel)
                _grens(schatting)
                batch = client.messages.batches.create(requests=[{"custom_id": d["custom_id"], "params": d["params"]}
                                                                  for d in deel])
                schrijf(kaart, [{k: d[k] for k in ("custom_id", "artikel", "beelden", "versie", "deelbeeld")}
                                for d in deel])
                schrijf(MAP / "rollen-batches.jsonl", [{"id": batch.id, "schatting": round(schatting, 3),
                                                        "aantal": len(deel)}])
                print(f"batch {batch.id}: {len(deel)} artikelen; deelbeelden {dict(status_teller)}", flush=True)

        def doe(lijst):
            for artikel, beelden in lijst:
                deel = next((b for b in beelden if b.get("deel")), None)
                inhoud = web.beeld(deel["beeld"]) if deel is not None else None
                status = "geen" if deel is None else "getoond" if inhoud is not None else "niet opgehaald"
                claim, titel = claims.get(adres(artikel), ""), titels.get(artikel, "")
                try:
                    params = br.verzoek(claim, titel, beelden, versie="rol-v2", deelbeeld=inhoud) \
                        if inhoud is not None else br.verzoek(claim, titel, beelden)
                except Exception as e:   # kapot beeld: dan de tekst zoals rol-v1 (DR3: alleen de soort fout)
                    params, status = br.verzoek(claim, titel, beelden), "fout " + type(e).__name__
                finally:
                    del inhoud
                with slot:
                    status_teller[status] += 1
                    wachtrij.append({"custom_id": "rol-" + _sha(artikel), "params": params, "artikel": artikel,
                                     "beelden": [b["beeld"] for b in beelden], "deelbeeld": status,
                                     "versie": "rol-v2" if status == "getoond" else "rol-v1",
                                     "grootte": len(json.dumps(params))})
                    dien_in()

        per_host = collections.defaultdict(list)
        for artikel, beelden in werk:
            deel = next((b for b in beelden if b.get("deel")), None)
            per_host[bm.host(deel["beeld"]) if deel else ""].append((artikel, beelden))
        with cf.ThreadPoolExecutor(8) as pool:
            list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
        with slot:
            dien_in(alles=True)
        print(f"klaar; deelbeelden {dict(status_teller)}; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}", flush=True)
        return
    per_cid = {r["custom_id"]: r for r in _jsonl(kaart)}
    al = {r["artikel"] for r in _jsonl(MAP / "rollen.jsonl")}

    def verwerk(cid, tekst):
        k = per_cid[cid]
        if k["artikel"] not in al:
            schrijf(MAP / "rollen.jsonl", [{"artikel": k["artikel"], "beelden": k["beelden"],
                                            "versie": k.get("versie", "rol-v1"),
                                            "rollen": br.lees_rollen(tekst, len(k["beelden"]))}])

    _batch_ophalen("rollen-batches.jsonl", verwerk)


def _viraal_stap(stap: str, proef: int) -> None:  # pragma: no cover - netwerk en modellen
    from doublecheck import beschrijvingvraag as bs

    kaart = MAP / "viraal-kaart.jsonl"
    if stap == "indienen":
        import concurrent.futures as cf

        import anthropic

        from doublecheck import berichtcontrole as bc
        from doublecheck.config import load_config
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        config = load_config(None)
        rollen = _rollen()
        klaar = {(r["artikel"], r["beeld"]) for r in _jsonl(MAP / "viraal-tekst.jsonl")}
        zoeker = {a["url"] for a in _jsonl(MAP / "pool-artikelen.jsonl") if set(a["redenen"]) - {"§193"}}
        werk = [b for b in virale(_jsonl(MAP / "pool-beelden.jsonl"), rollen)
                if b["artikel"] in zoeker and (b["artikel"], b["beeld"]) not in klaar]
        werk = werk[:proef] if proef else werk
        print(f"{len(werk)} virale beelden", flush=True)
        web, rekenen, slot = bm.Beleefd(), threading.Lock(), threading.Lock()
        wachtrij: list[dict] = []

        def dien_in(alles: bool = False):
            while len(wachtrij) >= 800 or (alles and wachtrij):
                deel = [wachtrij.pop(0) for _ in range(min(800, len(wachtrij)))]
                _grens(len(deel) * SCHATTING_BESCHRIJVING)
                batch = client.messages.batches.create(requests=[{"custom_id": d["custom_id"], "params": d["params"]}
                                                                  for d in deel])
                schrijf(kaart, [{"custom_id": d["custom_id"], "artikel": d["artikel"], "beeld": d["beeld"]}
                                for d in deel])
                schrijf(MAP / "viraal-batches.jsonl", [{"id": batch.id, "aantal": len(deel), "schatting": round(
                    len(deel) * SCHATTING_BESCHRIJVING, 3)}])
                print(f"batch {batch.id}: {len(deel)} beelden", flush=True)

        def doe(lijst):
            for b in lijst:
                inhoud = web.beeld(b["beeld"])
                if inhoud is None:
                    schrijf(MAP / "viraal-tekst.jsonl", [{"artikel": b["artikel"], "beeld": b["beeld"],
                                                          "fout": "niet opgehaald"}])
                    continue
                try:
                    with rekenen:
                        tekst = bc.bericht_uit(None, inhoud, config.ocr)
                    params = bs.verzoek(inhoud)
                except Exception as e:   # kapot of geen beeld (DR3: alleen de soort fout)
                    schrijf(MAP / "viraal-tekst.jsonl", [{"artikel": b["artikel"], "beeld": b["beeld"],
                                                          "fout": type(e).__name__}])
                    continue
                finally:
                    del inhoud
                tekens = len(tekst.strip())
                schrijf(MAP / "viraal-tekst.jsonl", [{"artikel": b["artikel"], "beeld": b["beeld"], "tekens": tekens,
                                                      **({"tekst": tekst} if tekens >= MIN_TEKENS else {})}])
                with slot:
                    wachtrij.append({"custom_id": "vb-" + _sha(b["artikel"], b["beeld"]), "params": params,
                                     "artikel": b["artikel"], "beeld": b["beeld"]})
                    dien_in()

        per_host = collections.defaultdict(list)
        for b in werk:
            per_host[bm.host(b["beeld"])].append(b)
        with cf.ThreadPoolExecutor(8) as pool:
            list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
        with slot:
            dien_in(alles=True)
        return
    per_cid = {r["custom_id"]: r for r in _jsonl(kaart)}
    al = {(r["artikel"], r["beeld"]) for r in _jsonl(MAP / "beschrijvingen.jsonl")}

    def verwerk(cid, tekst):
        k = per_cid[cid]
        b = bs.lees_beschrijving(tekst)
        if b and (k["artikel"], k["beeld"]) not in al:
            schrijf(MAP / "beschrijvingen.jsonl", [{"artikel": k["artikel"], "beeld": k["beeld"], **b}])

    _batch_ophalen("viraal-batches.jsonl", verwerk)


# --- sleutel 3 en 4: zoeken ----------------------------------------------------------------------------------------

def _zoeken() -> None:  # pragma: no cover - met het model
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts

    bb._rekenen()
    versie = load_config(None).model_versions.text_embedding
    rollen = _rollen()
    zoeker = {a["url"] for a in _jsonl(MAP / "pool-artikelen.jsonl") if set(a["redenen"]) - {"§193"}}
    prod_adressen = {adres(u) for (u,) in _conn(PRODUCTIE).execute("SELECT url FROM factcheck")}
    toegestaan = {"productie": {a for a in zoeker if adres(a) in prod_adressen}, "kopie": zoeker}

    def matrix(teksten):
        vecs = []
        for i in range(0, len(teksten), 256):
            vecs += [fp.vector for fp in fingerprint_texts([t[:600] for t in teksten[i:i + 256]], versie)]
        return np.vstack(vecs).astype(np.float32) if vecs else np.zeros((0, 1), np.float32)

    k3 = [i for i in virale(_jsonl(MAP / "viraal-tekst.jsonl"), rollen) if i.get("tekst") and i["artikel"] in zoeker]
    k4 = []
    for i in virale(_jsonl(MAP / "beschrijvingen.jsonl"), rollen):
        if i["artikel"] in zoeker:
            k4 += [{"artikel": i["artikel"], "tekst": t} for t in [i["beschrijving"], *i["zoekvragen"]]]
    m3, m4 = matrix([i["tekst"] for i in k3]), matrix([i["tekst"] for i in k4])
    a3, a4 = [i["artikel"] for i in k3], [i["artikel"] for i in k4]
    print(f"index: {len(k3)} beeldteksten, {len(k4)} beschrijvingen en zoekvragen", flush=True)
    uit = []
    for v in _jsonl(MAP / "vragen.jsonl"):
        regel = {"set": v["set"], "id": v["id"], "k3": {m: [] for m in MODI}, "k4": {m: [] for m in MODI}}
        tpad = MAP / "vectoren" / v["set"] / (_sha(v["id"]) + ".npy")
        if tpad.exists() and len(m3):
            q = [np.load(tpad)]
            extra = extra_zoekvragen(v["beweringen"])
            q = np.vstack(q + ([matrix(extra)] if extra else []))
            s = (m3 @ q.T).max(axis=1)
            regel["k3"] = {m: beste_artikelen(s, a3, TOP_RANG, toegestaan[m]) for m in MODI}
        if v.get("beschrijving") and len(m4):
            q = matrix([v["beschrijving"], *v["zoekvragen"]])
            s = (m4 @ q.T).max(axis=1)
            regel["k4"] = {m: beste_artikelen(s, a4, TOP_RANG, toegestaan[m]) for m in MODI}
        uit.append(regel)
    pad = MAP / "zoeken.jsonl"
    pad.unlink(missing_ok=True)
    schrijf(pad, uit)
    print(f"klaar: {len(uit)} vragen", flush=True)


# --- vergelijken ------------------------------------------------------------------------------------------------

def _vergelijken() -> None:  # pragma: no cover - op de bestanden
    import functools

    import cv2

    cv2.setNumThreads(2)
    vragen = _jsonl(MAP / "vragen.jsonl")
    zoeken = {(z["set"], z["id"]): z for z in _jsonl(MAP / "zoeken.jsonl")}
    per_artikel = collections.defaultdict(list)
    for b in _jsonl(MAP / "pool-beelden.jsonl"):
        per_artikel[adres(b["artikel"])].append(b)
    groepen = {"productie": _groepen_per_adres(_conn(PRODUCTIE)), "kopie": _groepen_per_adres(_conn(KOPIE))}

    @functools.lru_cache(maxsize=4096)
    def poolpunten(artikel, beeld):
        return bv.punten_uit_bytes(_puntpad("pool", artikel, beeld).read_bytes())

    pad = MAP / "paren.jsonl"
    pad.unlink(missing_ok=True)
    begin, n = time.monotonic(), 0
    for v in vragen:
        kandidaten: dict[str, dict] = collections.defaultdict(lambda: {m: set() for m in MODI})
        z = zoeken.get((v["set"], v["id"]), {})
        for m in MODI:
            for sleutel, lijst in (("tekst", v["k1"][m]), ("beschrijving", v["k2"][m])):
                for k in lijst:
                    kandidaten[adres(k["url"])][m].add(sleutel)
            for sleutel, naam in (("beeldtekst", "k3"), ("beeldbeschrijving", "k4")):
                for artikel, _ in (z.get(naam) or {}).get(m, [])[:TOP]:
                    kandidaten[adres(artikel)][m].add(sleutel)
        vraagpunten = bv.punten_uit_bytes(_puntpad(v["set"], v["id"]).read_bytes())
        hashes = [h for h, q in zip(v["pdq"], v["kwaliteit"]) if q >= bv.MIN_KWALITEIT]
        rijen = []
        for a, via in kandidaten.items():
            for b in per_artikel.get(a, []):
                pdq = min(bb._afstand(x, y) for x in hashes for y in b["pdq"]) \
                    if hashes and b["kwaliteit"] >= bv.MIN_KWALITEIT else None
                pn, dekking = bv.puntvergelijking(vraagpunten, poolpunten(b["artikel"], b["beeld"]))
                rijen.append({"set": v["set"], "vraag": v["id"], "artikel": b["artikel"], "beeld": b["beeld"],
                              "pdq": pdq, "heel": bb._afstand(v["pdq"][0], b["pdq"][0]),
                              "uitgesloten": bb.uitgesloten(v, b), "punten": pn, "dekking": round(dekking, 4),
                              "groepen": {m: sorted(groepen[m].get(a, ())) for m in MODI},
                              "via": {m: sorted(s) for m, s in via.items() if s}})
        schrijf(pad, rijen)
        n += len(rijen)
    print(f"klaar: {n} paren voor {len(vragen)} vragen in {time.monotonic() - begin:.0f} s", flush=True)


# --- lezen en tellen ------------------------------------------------------------------------------------------------

def _stand():
    return (_jsonl(MAP / "vragen.jsonl"), _jsonl(MAP / "paren.jsonl"), _rollen(), lees_labels())


def _rol_steekproef() -> list[dict]:  # pragma: no cover - op de bestanden
    """De 150 beelden voor de toets van de rol: 100 willekeurig uit de pool, en die van §193."""
    beelden = {(b["artikel"], b["beeld"]): b for b in _jsonl(MAP / "pool-beelden.jsonl")}
    rollen = _rollen()
    pool = sorted(k for k in beelden if k in rollen)
    keuze = random.Random(ROL_ZAAD).sample(pool, min(ROL_N, len(pool)))
    extra = [k for k in _rol193() if k in beelden and k in rollen and k not in keuze]
    return [beelden[k] for k in keuze + extra]


def _lezen() -> None:  # pragma: no cover - schrijft leesbladen naast de bestanden
    import html

    vragen, paren, rollen, d = _stand()
    labels = _paarlabels(d)
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    claims = _claimtekst_per_adres()
    kort = lambda t, n=160: html.escape((t or "")[:n])   # noqa: E731
    kaarten, sleutels = [], []

    def vraagbeeld(v):
        a = v.get("vraag") or (v.get("adressen") or [""])[0]
        return a, (v.get("adressen") or [a])[-1]

    open_ = te_lezen(paren, labels, rollen)
    originelen = [p for p in paren if rollen.get((p["artikel"], p["beeld"])) == "origineel" and bb.bevestigd(p)
                  and not p["uitgesloten"] and labelsleutel(p) not in labels and any(p["via"].get(m) for m in MODI)]
    for soort, lijst in (("bevestiging", open_), ("origineel", originelen)):
        for p in lijst:
            v = per_vraag[(p["set"], p["vraag"])]
            a, terug = vraagbeeld(v)
            eigen = any(set(p["groepen"].get(m) or []) & set(v["eigen"][m]) for m in MODI)
            kaarten.append(f"<div class=k><b>#{len(kaarten)}</b> {soort} · {p['set']} · <b>{'EIGEN' if eigen else 'elders'}"
                           f"</b> · {html.escape(json.dumps(p['via']))} · punten {p['punten']} · pdq {p['pdq']}"
                           f"<div><img referrerpolicy=no-referrer src='{html.escape(a)}' onerror=\"this.src='"
                           f"{html.escape(terug)}'\"><img referrerpolicy=no-referrer src='{html.escape(p['beeld'])}'>"
                           f"</div><b>check:</b> {kort(claims.get(adres(p['artikel'])))}<br><a href='"
                           f"{html.escape(p['artikel'])}'>{kort(p['artikel'], 80)}</a></div>")
            sleutels.append({"soort": "paar", "sleutel": labelsleutel(p)})
    gelezen = d.get("rollen", {})
    for b in _rol_steekproef():
        k = f"{b['artikel']}|{b['beeld']}"
        if k in gelezen:
            continue
        kaarten.append(f"<div class=k><b>#{len(kaarten)}</b> rol<div><img referrerpolicy=no-referrer "
                       f"src='{html.escape(b['beeld'])}' style='width:380px'></div><b>check:</b> "
                       f"{kort(claims.get(adres(b['artikel'])))}<br><b>alt:</b> {kort(b.get('alt'))} <b>onder:</b> "
                       f"{kort(b.get('onderschrift'))}<br><b>voor:</b> {kort(b.get('voor'), 220)}<br><b>na:</b> "
                       f"{kort(b.get('na'), 220)}<br>{'DEELBEELD · ' if b.get('deel') else ''}<a href='"
                       f"{html.escape(b['artikel'])}'>{kort(b['artikel'], 80)}</a></div>")
        sleutels.append({"soort": "rol", "sleutel": k})
    kop = ("<!doctype html><meta charset=utf-8><title>Vindronde lezen</title><style>body{font:11px sans-serif;"
           "margin:2px;display:flex;flex-wrap:wrap;gap:4px}.k{width:388px;border:1px solid #bbb;padding:2px}"
           "img{width:191px;height:150px;object-fit:contain;background:#eee;margin:1px}</style>")
    for oud in MAP.glob("lezen-*.html"):
        oud.unlink()
    for i in range(0, len(kaarten), 8):
        (MAP / f"lezen-{i // 8}.html").write_text(kop + "".join(kaarten[i:i + 8]), encoding="utf-8")
    (MAP / "lezen.json").write_text(json.dumps(sleutels, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(open_)} bevestigingen, {len(originelen)} originelen en "
          f"{sum(s['soort'] == 'rol' for s in sleutels)} rollen te lezen; {(len(kaarten) + 7) // 8} bladen in {MAP}")


def _po() -> None:  # pragma: no cover - schrijft de nakijkpagina naast de bestanden
    """De pagina waarop de PO 30 bevestigingen en 30 rollen nakijkt (eis 6), zonder de labels van Claude te zien.
    De beelden komen rechtstreeks van hun site, niets op schijf; de keuzes blijven in de browser (localStorage)."""
    vragen, paren, rollen, d = _stand()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    claims, kopie = _claimtekst_per_adres(), _conn(KOPIE)

    def eigen_tekst(v):
        for g in v["eigen"]["kopie"] or v["eigen"]["productie"]:
            r = kopie.execute("SELECT canonical_text FROM claim WHERE claim_id = ? OR cluster_id = ? LIMIT 1",
                              (g, g)).fetchone()
            if r:
                return r[0]
        return ""

    per_sleutel = {labelsleutel(p): p for p in paren if any(_telt(p, rollen, m) for m in MODI)}
    paar_items = []
    for k in po_keuze(list(per_sleutel)):
        p, v = per_sleutel[k], per_vraag[(per_sleutel[k]["set"], per_sleutel[k]["vraag"])]
        vraag = v.get("vraag") or (v.get("adressen") or [""])[0]
        paar_items.append({"sleutel": k, "set": p["set"], "vraag": vraag, "terug": (v.get("adressen") or [vraag])[-1],
                           "beeld": p["beeld"], "eigen": eigen_tekst(v), "check": claims.get(adres(p["artikel"]), ""),
                           "artikel": p["artikel"]})
    beelden = {f"{b['artikel']}|{b['beeld']}": b for b in _jsonl(MAP / "pool-beelden.jsonl")}
    rol_items = []
    for k in po_keuze(list(d.get("rollen", {}))):
        b = beelden[k]
        rol_items.append({"sleutel": k, "beeld": b["beeld"], "check": claims.get(adres(b["artikel"]), ""),
                          **{veld: (b.get(veld) or "")[:300] for veld in ("alt", "onderschrift", "voor", "na")},
                          "deel": bool(b.get("deel")), "artikel": b["artikel"]})
    data = json.dumps({"paren": paar_items, "rollen": rol_items}, ensure_ascii=False).replace("</", "<\\/")
    (MAP / "po.html").write_text(PO_PAGINA.replace("__DATA__", data), encoding="utf-8")
    print(f"{len(paar_items)} bevestigingen en {len(rol_items)} rollen op {MAP / 'po.html'}")


PO_PAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Vindronde nakijken</title>
<style>
:root{--bg:#f4f6f8;--vlak:#fff;--inkt:#15202b;--zacht:#5b6875;--lijn:#d5dce3;--accent:#1f5f8b;--keus:#e3eef7}
@media (prefers-color-scheme:dark){:root{--bg:#10151b;--vlak:#18202a;--inkt:#e5eaf0;--zacht:#98a4b1;--lijn:#2b3542;
--accent:#6fb0dd;--keus:#1d3346;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--inkt);font:15px/1.45 system-ui,-apple-system,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:20px 16px 60px}ol.uitleg,ul.uitleg{padding-left:1.4em}.uitleg li{margin:4px 0}h1{margin:0 0 4px;font-size:1.5rem}
h2{margin:28px 0 8px;font-size:1.15rem}.uitleg{color:var(--zacht);max-width:70ch;margin:4px 0}
.balk{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--lijn);display:flex;
flex-wrap:wrap;gap:8px 16px;align-items:center;z-index:2}.balk b{font-variant-numeric:tabular-nums}
.k{background:var(--vlak);border:1px solid var(--lijn);border-radius:10px;padding:12px;margin:12px 0;display:grid;gap:8px}
.kop{color:var(--zacht);font-size:.85rem}.beelden{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.beelden figure{margin:0;display:grid;gap:4px}.beelden figcaption{font-size:.8rem;color:var(--zacht)}
img{width:100%;max-height:320px;object-fit:contain;background:var(--bg);border-radius:6px}
.een img{max-width:460px}.tekst{font-size:.9rem;overflow-wrap:anywhere}.tekst i{color:var(--zacht);font-style:normal}
.keuze{display:flex;flex-wrap:wrap;gap:6px}.keuze button{font:inherit;padding:6px 12px;border-radius:8px;cursor:pointer;
border:1.5px solid var(--lijn);background:var(--vlak);color:var(--inkt)}
.keuze button[aria-pressed=true]{border-color:var(--accent);background:var(--keus);font-weight:700}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}a{color:var(--accent)}
@media (max-width:560px){.beelden{grid-template-columns:1fr}}
</style>
<div class=wrap>
<h1>Vindronde nakijken</h1>
<p class=uitleg><b>Deel 1, 30 vondsten.</b> Links staat wat iemand zou insturen. De machine zocht daarbij een
factcheck en vond rechts een beeld in dat artikel. Jij kijkt of dat een goede vondst is, met twee vragen:</p>
<ol class=uitleg><li><b>Is het dezelfde foto?</b> Kijk naar de foto zelf. Wat eromheen zit telt niet: een andere
Facebookpost, een uitsnede, een kader, een stempel als <i>misleading</i> of <i>fake</i>, een bewerking van dezelfde foto.
Alleen hetzelfde logo, dezelfde balk of hetzelfde sjabloon met een andere foto erin is <b>een andere foto</b>.</li>
<li><b>Gaat de factcheck over wat er bij de linkerfoto beweerd wordt?</b> Vergelijk de twee zinnen onder de beelden.
Andere woorden zijn goed, zolang het om dezelfde bewering gaat. Staat er links geen bewering, kijk dan alleen naar
de foto: dezelfde foto is dan de eerste knop.</li></ol>
<p class=uitleg><b>Deel 2, 30 rollen.</b> Hier staat telkens één beeld uit een factcheckartikel; er valt niets te
vergelijken. De vraag is: wat doet deze foto in het artikel? Meestal zie je dat aan het beeld zelf. Het artikel openen
hoeft alleen als je twijfelt, en tekst in een taal die je niet leest mag je overslaan.</p>
<ul class=uitleg><li><b>Viraal</b>: wat mensen deelden en wat de factcheck controleert. Vaak een screenshot van een post
op Facebook, X of WhatsApp, of de gedeelde foto zelf, soms met een stempel of watermerk van de factchecker erop. Ook het
beeld bovenaan het artikel kan viraal zijn, als het gedeelde beeld erin staat.</li>
<li><b>Origineel</b>: de echte foto die de factchecker vond, waar het virale beeld van gemaakt of uit gehaald is,
bijvoorbeeld een oudere foto van een persbureau.</li>
<li><b>Bewijs</b>: ander materiaal waarmee de factchecker iets aantoont: een kaart, een nieuwsbericht, zoekresultaten,
een verklaring, de uitslag van een detector, een logo ter vergelijking.</li>
<li><b>Huisstijl</b>: van de factchecker zelf: het logo, het oordeel als plaatje (<i>FAKE</i>, <i>MISLEADING</i>) zonder
het gedeelde beeld, een banner, een illustratie, een verwijzing naar een ander artikel.</li>
<li><b>Onbekend</b>: als je het echt niet kunt zeggen.</li></ul>
<p class=uitleg>Je keuzes blijven in deze browser bewaard. Claude leest ze uit als je klaar bent.</p>
<div class=balk><span>Vondsten <b id=np>0</b>/30</span><span>Rollen <b id=nr>0</b>/30</span>
<button id=kopie type=button>Kopieer de uitslag</button><span id=status class=kop></span></div>
<h2>Deel 1 · vondsten</h2><div id=paren></div>
<h2>Deel 2 · rollen</h2><div id=rollen></div>
</div>
<script>
const DATA = __DATA__;
const OPSLAG = "po-32.21";
let stand = {paren: {}, rollen: {}};
try { stand = Object.assign(stand, JSON.parse(localStorage.getItem(OPSLAG) || "{}")); } catch (e) {}
const PAAR = [["zelfde beeld, zelfde bewering", "Goed: dezelfde foto, dezelfde bewering"],
  ["zelfde beeld, andere bewering", "Dezelfde foto, maar de check gaat over iets anders"],
  ["ander beeld", "Fout: een andere foto"]];
const ROL = [["viraal", "Viraal: het beeld dat rondging, of de post die het deelde"],
  ["origineel", "Origineel: de echte foto waar het virale van gemaakt is"],
  ["bewijs", "Bewijs: kaart, nieuwsbericht, zoekresultaat, detector"],
  ["huisstijl", "Huisstijl: logo, oordeel, banner, illustratie, ander artikel"], ["onbekend", "Onbekend"]];
function bewaar() { try { localStorage.setItem(OPSLAG, JSON.stringify(stand)); } catch (e) {} tel(); }
function tel() {
  document.getElementById("np").textContent = DATA.paren.filter(p => stand.paren[p.sleutel]).length;
  document.getElementById("nr").textContent = DATA.rollen.filter(r => stand.rollen[r.sleutel]).length;
}
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const k of kids) e.append(k);
  return e;
}
function beeld(src, terug, onder) {
  const img = el("img", {src, referrerpolicy: "no-referrer", alt: onder});
  if (terug && terug !== src) img.onerror = () => { img.onerror = null; img.src = terug; };
  return el("figure", {}, img, el("figcaption", {}, onder));
}
function knoppen(soort, sleutel, opties) {
  const rij = el("div", {class: "keuze", role: "group"});
  for (const [waarde, tekst] of opties) {
    const b = el("button", {type: "button", "aria-pressed": String(stand[soort][sleutel] === waarde)}, tekst);
    b.onclick = () => {
      stand[soort][sleutel] = waarde;
      for (const x of rij.children) x.setAttribute("aria-pressed", String(x === b));
      bewaar();
    };
    rij.append(b);
  }
  return rij;
}
DATA.paren.forEach((p, i) => {
  const t = el("div", {class: "tekst"},
    el("div", {}, el("i", {}, "Bewering links: "), p.eigen || "(geen; kijk alleen naar de foto)"),
    el("div", {}, el("i", {}, "Bewering in de factcheck: "), p.check),
    el("a", {href: p.artikel, target: "_blank", rel: "noopener"}, "Open het factcheckartikel"));
  document.getElementById("paren").append(el("div", {class: "k"},
    el("div", {class: "kop"}, `#${i + 1}`),
    el("div", {class: "beelden"}, beeld(p.vraag, p.terug, "Wat iemand instuurt"),
       beeld(p.beeld, "", "Gevonden in de factcheck")),
    t, el("div", {class: "kop"}, "Dezelfde foto? En gaat de factcheck over dezelfde bewering?"),
    knoppen("paren", p.sleutel, PAAR)));
});
DATA.rollen.forEach((r, i) => {
  const t = el("div", {class: "tekst"});
  for (const [veld, naam] of [["check", "Bewering in de check"], ["alt", "Alt-tekst"], ["onderschrift", "Onderschrift"],
                             ["voor", "Tekst ervoor"], ["na", "Tekst erna"]])
    if (r[veld]) t.append(el("div", {}, el("i", {}, naam + ": "), r[veld]));
  t.append(el("a", {href: r.artikel, target: "_blank", rel: "noopener"}, "Open het factcheckartikel"));
  document.getElementById("rollen").append(el("div", {class: "k"},
    el("div", {class: "kop"}, `#${i + 1}` + (r.deel ? " · deelbeeld (het beeld bovenaan, bij delen)" : "")),
    el("div", {class: "een"}, beeld(r.beeld, "", "Uit het factcheckartikel")), t,
    el("div", {class: "kop"}, "Wat doet deze foto in het artikel?"), knoppen("rollen", r.sleutel, ROL)));
});
document.getElementById("kopie").onclick = async () => {
  const tekst = JSON.stringify(stand);
  try { await navigator.clipboard.writeText(tekst); document.getElementById("status").textContent = "Gekopieerd."; }
  catch (e) { document.getElementById("status").textContent = "Kopiëren lukte niet; Claude kan het ook zelf uitlezen."; }
};
tel();
</script>
"""


def _waarom(vragen, paren, rollen) -> dict:  # pragma: no cover - op de bestanden
    """Vragen waar sleutel 3 of 4 het eigen artikel vond maar geen viraal beeld de check bevestigt, en waarom."""
    zoeken = {(z["set"], z["id"]): z for z in _jsonl(MAP / "zoeken.jsonl")}
    uit = collections.Counter()
    for v in vragen:
        z = zoeken.get((v["set"], v["id"]))
        if not z or not v["eigen"]["kopie"]:
            continue
        for m in MODI:
            eigen = set(v["eigen"][m])
            gevonden = [p for p in paren if p["set"] == v["set"] and p["vraag"] == v["id"]
                        and set(p["groepen"].get(m) or []) & eigen and set(p["via"].get(m) or []) & {"beeldtekst",
                                                                                                    "beeldbeschrijving"}]
            if not gevonden:
                continue
            if any(_telt(p, rollen, m) for p in gevonden):
                uit[f"{m}: bevestigd"] += 1
            elif any(bb.bevestigd(p) and not p["uitgesloten"] for p in gevonden):
                uit[f"{m}: bevestigd, maar niet op een viraal beeld"] += 1
            else:
                uit[f"{m}: gevonden, het beeld bevestigt niet"] += 1
    return dict(uit)


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    vragen, paren, rollen, d = _stand()
    labels = _paarlabels(d)
    uit = {m: telling(vragen, paren, labels, rollen, m) for m in MODI}
    voorspeld = {f"{a}|{b}": r for (a, b), r in rollen.items()}
    uit["rol"] = rol_telling(d.get("rollen", {}), voorspeld)
    deelbeelden = {f"{b['artikel']}|{b['beeld']}" for b in _jsonl(MAP / "pool-beelden.jsonl") if b.get("deel")}
    uit["rol apart"] = rol_per_soort(d.get("rollen", {}), voorspeld, deelbeelden)
    uit["rolvraag per artikel"] = dict(collections.Counter(r.get("versie", "rol-v1")
                                                          for r in _jsonl(MAP / "rollen.jsonl")))
    po, verschillen = d.get("po"), None
    if po:
        telt = [labelsleutel(p) for p in paren if any(_telt(p, rollen, m) for m in MODI)]
        verschillen = po_verschillen(labels, po.get("paren", {}), po_keuze(telt))
        uit["po"] = {"paren": verschillen,
                     "rollen": po_verschillen(d.get("rollen", {}), po.get("rollen", {}), po_keuze(list(d["rollen"])))}
        herzien = d.get("po_herzien")
        if herzien:  # na de uitleg van Claude; eis 6 blijft de eerste ronde
            uit["po"]["na overleg"] = {
                "paren": po_verschillen(labels, {**po.get("paren", {}), **herzien.get("paren", {})}, po_keuze(telt)),
                "rollen": po_verschillen(d.get("rollen", {}), {**po.get("rollen", {}), **herzien.get("rollen", {})},
                                         po_keuze(list(d["rollen"])))}
    uit["eisen"] = eisen(uit["productie"], uit["kopie"], uit["rol"], verschillen)
    uit["waarom"] = _waarom(vragen, paren, rollen)
    rolverdeling = collections.Counter(rollen.values())
    bevestigd_per_rol = collections.Counter(rollen.get((p["artikel"], p["beeld"]), "geen rol") for p in paren
                                            if bb.bevestigd(p) and not p["uitgesloten"]
                                            and any(p["via"].get(m) for m in MODI))
    uit["rollen"] = {"verdeling": dict(rolverdeling.most_common()), "bevestigingen per rol": dict(
        bevestigd_per_rol.most_common())}
    zoeken = {(z["set"], z["id"]): z for z in _jsonl(MAP / "zoeken.jsonl")}
    rang = collections.defaultdict(collections.Counter)
    for v in vragen:
        z = zoeken.get((v["set"], v["id"]))
        if not z or not v["eigen"]["kopie"]:
            continue
        groepen = _groepen_per_adres_cache()
        for naam in ("k3", "k4"):
            lijst = [adres(a) for a, _ in z[naam]["kopie"]]
            plek = next((i for i, a in enumerate(lijst) if groepen.get(a, set()) & set(v["eigen"]["kopie"])), None)
            for grens in (1, 5, 20):
                rang[f"{v['set']} {naam}"][f"top {grens}"] += plek is not None and plek < grens
    uit["rang van de eigen check (kopie, per vraag)"] = {k: dict(c) for k, c in rang.items()}
    seconden = sorted(v["seconden"] for v in vragen)
    uit["tijd per vraag"] = {"p50": seconden[len(seconden) // 2], "p95": seconden[int(len(seconden) * 0.95)]}
    uit["kosten"] = round(al_uitgegeven(), 2)
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


_GROEPEN_KOPIE: dict | None = None


def _groepen_per_adres_cache() -> dict:  # pragma: no cover
    global _GROEPEN_KOPIE
    if _GROEPEN_KOPIE is None:
        _GROEPEN_KOPIE = _groepen_per_adres(_conn(KOPIE))
    return _GROEPEN_KOPIE


def opruimen() -> None:
    """De punten van vragen en pool weg na het tellen, en de vingerafdrukken van de vragen."""
    shutil.rmtree(MAP / "punten", ignore_errors=True)
    shutil.rmtree(MAP / "vectoren", ignore_errors=True)


ROLPAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Rol lezen</title><style>body{font:13px system-ui,sans-serif;margin:8px;background:#f4f6f8;color:#15202b}
.k{background:#fff;border:1px solid #ccd;border-radius:8px;padding:8px;margin:8px 0;display:grid;gap:6px}
.r{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}figure{margin:0;width:360px}figure img{width:100%;
max-height:360px;object-fit:contain;background:#eee}figcaption{font-size:11px;color:#556}.t{overflow-wrap:anywhere}
.t i{color:#667;font-style:normal}</style><h1>Rol lezen</h1><div id=k></div><script>
const DATA = __DATA__;
function el(t, a, ...k) { const e = document.createElement(t); for (const [x, y] of Object.entries(a || {})) e.setAttribute(x, y);
  for (const c of k) e.append(c); return e; }
function fig(src, onder) { return el("figure", {}, el("img", {src, referrerpolicy: "no-referrer"}), el("figcaption", {}, onder)); }
const ALLEEN = location.hash.slice(1);   // #B26 toont alleen die kaart
window.onhashchange = () => location.reload();
DATA.filter(d => !ALLEEN || `B${d.nr}` === ALLEEN).forEach(d => {
  const t = el("div", {class: "t"});
  for (const [n, w] of [["Bewering in de check", d.check], ["Alt", d.alt], ["Onderschrift", d.onderschrift],
                        ["Ervoor", d.voor], ["Erna", d.na]]) if (w) t.append(el("div", {}, el("i", {}, n + ": "), w));
  t.append(el("a", {href: d.artikel, target: "_blank", rel: "noopener"}, "Open het artikel"));
  const r = el("div", {class: "r"}, fig(d.beeld, `B${d.nr} · Haiku: ${d.haiku}` + (d.deel ? " · deelbeeld" : "")));
  d.paren.forEach((q, j) => r.append(fig(q.vraag, `P${d.nr}.${j} · ${q.sleutel.slice(0, 60)} · ${q.punten} pt, ${q.dekking}`)));
  document.getElementById("k").append(el("div", {class: "k"}, el("b", {}, `B${d.nr}`), r, t));
});
</script>"""


def _rolvoormeting_lezen() -> None:  # pragma: no cover - op de bestanden
    """De leespagina van #32.25: per beeld het beeld van zijn site, de tekst eromheen en de vragen die het bevestigt.
    Niets op schijf behalve de pagina met de adressen en de sleutels."""
    vragen, paren, rollen, _ = _stand()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    per_sleutel = {labelsleutel(p): p for p in paren}
    pool = {(b["artikel"], b["beeld"]): b for b in _jsonl(MAP / "pool-beelden.jsonl")}
    claims = _claimtekst_per_adres()
    items, sleutels = [], []
    for nr, b in enumerate(rol_voormeting_beelden(vragen, paren, rollen)):
        pb = pool.get((b["artikel"], b["beeld"]), {})
        paren_ = []
        for k in b["paren"]:
            p, v = per_sleutel[k], per_vraag[(per_sleutel[k]["set"], per_sleutel[k]["vraag"])]
            paren_.append({"sleutel": k, "vraag": v.get("vraag") or (v.get("adressen") or [""])[0],
                           "punten": p["punten"], "dekking": p["dekking"]})
            sleutels.append({"soort": "paar", "kaart": f"P{nr}.{len(paren_) - 1}", "sleutel": k})
        sleutels.append({"soort": "rol", "kaart": f"B{nr}", "sleutel": f"{b['artikel']}|{b['beeld']}"})
        items.append({"nr": nr, "artikel": b["artikel"], "beeld": b["beeld"], "deel": bool(pb.get("deel")),
                      "haiku": rollen.get((b["artikel"], b["beeld"]), "geen"), "check": claims.get(adres(b["artikel"]), ""),
                      **{veld: (pb.get(veld) or "")[:300] for veld in ("alt", "onderschrift", "voor", "na")},
                      "paren": paren_})
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    (MAP / "rolvoormeting.html").write_text(ROLPAGINA.replace("__DATA__", data), encoding="utf-8")
    (MAP / "rolvoormeting.json").write_text(json.dumps(sleutels, ensure_ascii=False), encoding="utf-8")
    print(f"{len(items)} beelden en {sum(len(i['paren']) for i in items)} paren op {MAP / 'rolvoormeting.html'}")


def _rolvoormeting_tellen() -> dict:  # pragma: no cover - op de bestanden
    """De twee voorwaarden van #32.25: de gelezen rollen van de beelden, en wat N en R3 ermee vinden (productie)."""
    vragen, paren, rollen, d = _stand()
    gekozen = rol_voormeting_beelden(vragen, paren, rollen)
    gelezen = json.loads(ROLLABELS.read_text(encoding="utf-8")) if ROLLABELS.exists() else {}
    rol, lab = gelezen.get("rollen", {}), gelezen.get("labels", {})
    open_ = [f"{b['artikel']}|{b['beeld']}" for b in gekozen if f"{b['artikel']}|{b['beeld']}" not in rol]
    if open_:
        raise Weigering(f"{len(open_)} van de {len(gekozen)} beelden hebben nog geen gelezen rol in {ROLLABELS.name}")
    fout = {k: v for k, v in lab.items() if v not in LABELWAARDEN}
    if fout:
        raise Weigering(f"onbekende labels in {ROLLABELS.name}: {list(fout.items())[:3]}")
    labels = {**_paarlabels(d), **lab}
    nieuw = met_gelezen_rollen(rollen, rol)
    vr_ = [v for v in vragen if v["set"] in ROL_SETS]
    pa = [p for p in paren if p["set"] in ROL_SETS]
    voor = telling(vr_, pa, labels, rollen, "productie")
    na = telling(vr_, pa, labels, nieuw, "productie")
    sleutels = [f"{b['artikel']}|{b['beeld']}" for b in gekozen]
    rollen_gelezen = [rol[k] for k in sleutels]
    haiku = [rollen.get((b["artikel"], b["beeld"])) for b in gekozen]
    uit = {"beelden": len(gekozen), "gelezen rollen": dict(collections.Counter(rollen_gelezen)),
           "rol van Haiku tegen gelezen": dict(collections.Counter(f"{h} -> {g}" for h, g in zip(haiku, rollen_gelezen))),
           "paarlabels": dict(collections.Counter(lab.get(k, "geen") for b in gekozen for k in b["paren"])),
           "voor": {s: voor[s] for s in ROL_SETS}, "met de gelezen rollen": {s: na[s] for s in ROL_SETS},
           "voorwaarden": rol_voorwaarden(rollen_gelezen, na["N"]["gevonden"], na["R3"]["gevonden"])}
    return uit


# --- de rolronde, rol-v3 (#32.26) -----------------------------------------------------------------------------------

def _rolronde_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
               for b in _jsonl(MAP / "rolronde-batches.jsonl"))


def _rolronde_set() -> list[str]:  # pragma: no cover - op de bestanden
    _, paren, _, d = _stand()
    gelezen = list(d.get("rollen", {}))
    if ROLLABELS.exists():
        gelezen += list(json.loads(ROLLABELS.read_text(encoding="utf-8")).get("rollen", {}))
    artikelen = rolronde_artikelen(paren, gelezen)
    (MAP / "rolronde-set.json").write_text(json.dumps(artikelen, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(artikelen)} artikelen in de rolronde")
    return artikelen


def _rolronde_indienen(proef: int) -> None:  # pragma: no cover - netwerk
    """Per artikel alle beelden beleefd opgehaald, alleen in het geheugen, en één vraag `rol-v3` in de Batch API (openbare
    artikelen). Een artikel waarvan een beeld niet te halen is, krijgt geen vraag: zijn beelden blijven *onbekend*."""
    import concurrent.futures as cf

    import anthropic

    from doublecheck import beeldrolvraag as br
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart = MAP / "rolronde-kaart.jsonl"
    gedaan = {r["artikel"] for r in _jsonl(kaart)}
    artikelen = json.loads((MAP / "rolronde-set.json").read_text(encoding="utf-8"))
    per_artikel = collections.defaultdict(list)
    for b in _jsonl(MAP / "pool-beelden.jsonl"):
        per_artikel[b["artikel"]].append(b)
    titels = {a["url"]: a.get("titel") or "" for a in _jsonl(MAP / "pool-artikelen.jsonl")}
    claims = _claimtekst_per_adres()
    werk = [a for a in artikelen if a not in gedaan and per_artikel.get(a)]
    werk = werk[:proef] if proef else werk
    print(f"{len(werk)} artikelen ({len(gedaan)} al gedaan); samen ${_rolronde_uitgegeven():.2f} van "
          f"${ROLRONDE_BUDGET:.2f}", flush=True)
    web, slot, wachtrij, teller = bm.Beleefd(), threading.Lock(), [], collections.Counter()

    def dien_in(alles: bool = False):
        while wachtrij and (alles or len(wachtrij) >= 400 or sum(d["grootte"] for d in wachtrij) >= MAX_BATCH_BYTES):
            deel, grootte = [], 0
            while wachtrij and len(deel) < 400 and grootte < MAX_BATCH_BYTES:
                deel.append(wachtrij.pop(0))
                grootte += deel[-1]["grootte"]
            schatting = sum(SCHATTING_ROL + SCHATTING_ROL_BEELD * len(d["beelden"]) for d in deel)
            if _rolronde_uitgegeven() + schatting > ROLRONDE_BUDGET - 0.05:
                raise Weigering(f"de grens: ${_rolronde_uitgegeven():.2f} plus ${schatting:.2f} komt boven "
                                f"${ROLRONDE_BUDGET:.2f}")
            batch = client.messages.batches.create(requests=[{"custom_id": d["custom_id"], "params": d["params"]}
                                                              for d in deel])
            schrijf(kaart, [{k: d[k] for k in ("custom_id", "artikel", "beelden", "status")} for d in deel])
            schrijf(MAP / "rolronde-batches.jsonl", [{"id": batch.id, "schatting": round(schatting, 4),
                                                      "aantal": len(deel)}])
            print(f"batch {batch.id}: {len(deel)} artikelen, schatting ${schatting:.3f}", flush=True)

    def doe(lijst):
        for artikel in lijst:
            beelden = per_artikel[artikel][:br.MAX_BEELDEN]
            inhoud = [web.beeld(b["beeld"]) for b in beelden]
            regel = {"custom_id": "rol3-" + _sha(artikel), "artikel": artikel, "beelden": [b["beeld"] for b in beelden]}
            if any(x is None for x in inhoud):
                with slot:
                    teller["niet opgehaald"] += 1
                    schrijf(kaart, [{**regel, "status": "niet opgehaald"}])
                continue
            try:
                params = br.verzoek(claims.get(adres(artikel), ""), titels.get(artikel, ""), beelden, versie="rol-v3",
                                    beelden_bytes=inhoud)
            except Exception as e:   # kapot beeld; alleen de soort fout (DR3)
                with slot:
                    teller[f"fout {type(e).__name__}"] += 1
                    schrijf(kaart, [{**regel, "status": f"fout {type(e).__name__}"}])
                continue
            finally:
                del inhoud
            with slot:
                teller["gevraagd"] += 1
                wachtrij.append({**regel, "params": params, "status": "gevraagd", "grootte": len(json.dumps(params))})
                dien_in()

    per_host = collections.defaultdict(list)
    for a in werk:
        per_host[bm.host(per_artikel[a][0]["beeld"])].append(a)
    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    with slot:
        dien_in(alles=True)
    print(f"klaar: {dict(teller)}; samen ${_rolronde_uitgegeven():.2f} van ${ROLRONDE_BUDGET:.2f}", flush=True)


def _rolronde_ophalen() -> None:  # pragma: no cover - netwerk
    import anthropic

    from doublecheck import beeldrolvraag as br
    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaart = {r["custom_id"]: r for r in _jsonl(MAP / "rolronde-kaart.jsonl") if r["status"] == "gevraagd"}
    klaar = {r["artikel"] for r in _jsonl(MAP / "rolronde.jsonl")}
    alle = _jsonl(MAP / "rolronde-batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog", flush=True)
            continue
        werkelijk, mis, regels = 0.0, 0, []
        for r in client.messages.batches.results(b["id"]):
            k = kaart.get(r.custom_id)
            if r.result.type != "succeeded" or k is None:
                mis += 1
                continue
            werkelijk += kosten_batch(bc.gebruik_uit(r.result.message), "haiku")
            if k["artikel"] not in klaar:
                tekst = "".join(getattr(x, "text", "") or "" for x in r.result.message.content)
                regels.append({"artikel": k["artikel"], "beelden": k["beelden"],
                               "rollen": br.lees_rollen(tekst, len(k["beelden"])), "versie": "rol-v3"})
        schrijf(MAP / "rolronde.jsonl", regels)
        b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
        print(f"batch {b['id']}: ${werkelijk:.3f}, {mis} mislukt", flush=True)
    (MAP / "rolronde-batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(f"samen ${_rolronde_uitgegeven():.2f} van ${ROLRONDE_BUDGET:.2f}", flush=True)


def _rolronde_rollen() -> dict[tuple[str, str], str]:  # pragma: no cover - op de bestanden
    """De rollen van `rol-v3`; een beeld uit de set zonder antwoord is *onbekend* (nooit viraal), de rest blijft van
    `rol-v2`."""
    uit = _rollen()
    for r in _jsonl(MAP / "rolronde-kaart.jsonl"):
        for b in r["beelden"]:
            uit[(r["artikel"], b)] = "onbekend"
    for r in _jsonl(MAP / "rolronde.jsonl"):
        for b, rol in zip(r["beelden"], r["rollen"]):
            uit[(r["artikel"], b)] = rol
    return uit


def _rolronde_labels(d: dict) -> dict[str, str]:  # pragma: no cover - op de bestanden
    uit = _paarlabels(d)
    for pad in (ROLLABELS, ROLRONDELABELS):
        if pad.exists():
            eigen = json.loads(pad.read_text(encoding="utf-8")).get("labels", {})
            fout = {k: v for k, v in eigen.items() if v not in LABELWAARDEN}
            if fout:
                raise Weigering(f"onbekende labels in {pad.name}: {list(fout.items())[:3]}")
            uit.update(eigen)
    return uit


def _rolronde_lezen() -> None:  # pragma: no cover - op de bestanden
    """De leespagina: elk beantwoord artikel met zijn beelden en de rol van rol-v2 en rol-v3 (de proef helemaal), en de
    bevestigingen die door rol-v3 gaan tellen en nog geen label hebben."""
    vragen, paren, rollen2, d = _stand()
    rollen3, labels = _rolronde_rollen(), _rolronde_labels(d)
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    gelezen = dict(d.get("rollen", {}))
    if ROLLABELS.exists():
        gelezen |= json.loads(ROLLABELS.read_text(encoding="utf-8")).get("rollen", {})
    antwoorden = _jsonl(MAP / "rolronde.jsonl")
    artikelkaarten = [{"artikel": r["artikel"], "beelden": [
        {"beeld": b, "v2": rollen2.get((r["artikel"], b), "-"), "v3": rol, "gelezen": gelezen.get(f"{r['artikel']}|{b}", "")}
        for b, rol in zip(r["beelden"], r["rollen"])]} for r in antwoorden[:40]]
    open_, sleutels = [], []
    for p in paren:
        k = labelsleutel(p)
        if k in labels or not any(_telt(p, rollen3, m) for m in MODI):
            continue
        v = per_vraag[(p["set"], p["vraag"])]
        open_.append({"nr": len(open_), "sleutel": k, "set": p["set"], "vraag": v.get("vraag") or (v.get("adressen") or
                      [""])[0], "beeld": p["beeld"], "artikel": p["artikel"], "punten": p["punten"],
                      "dekking": p["dekking"]})
        sleutels.append({"soort": "paar", "kaart": f"P{len(open_) - 1}", "sleutel": k})
    data = json.dumps({"artikelen": artikelkaarten, "paren": open_}, ensure_ascii=False).replace("</", "<\\/")
    (MAP / "rolronde-lezen.html").write_text(ROLRONDEPAGINA.replace("__DATA__", data), encoding="utf-8")
    (MAP / "rolronde-lezen.json").write_text(json.dumps(sleutels, ensure_ascii=False), encoding="utf-8")
    print(f"{len(antwoorden)} artikelen beantwoord ({len(artikelkaarten)} op de pagina); {len(open_)} bevestigingen "
          f"zonder label op {MAP / 'rolronde-lezen.html'}")


ROLRONDEPAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Rolronde lezen</title><style>body{font:13px system-ui,sans-serif;margin:8px;background:#f4f6f8;color:#15202b}
.k{background:#fff;border:1px solid #ccd;border-radius:8px;padding:8px;margin:8px 0}.r{display:flex;gap:8px;flex-wrap:wrap;
align-items:flex-start}figure{margin:0;width:230px}figure img{width:100%;max-height:230px;object-fit:contain;background:#eee}
figcaption{font-size:11px;color:#445}.anders{color:#b00;font-weight:700}</style><h1>Rolronde lezen</h1>
<h2>Antwoorden van rol-v3</h2><div id=a></div><h2>Bevestigingen zonder label</h2><div id=p></div><script>
const DATA = __DATA__;
const ALLEEN = location.hash.slice(1);
function el(t, a, ...k) { const e = document.createElement(t); for (const [x, y] of Object.entries(a || {})) e.setAttribute(x, y);
  for (const c of k) e.append(c); return e; }
function fig(src, onder, cls) { return el("figure", {}, el("img", {src, referrerpolicy: "no-referrer"}), el("figcaption", {class: cls || ""}, onder)); }
DATA.artikelen.forEach((a, i) => {
  if (ALLEEN && ALLEEN !== `A${i}`) return;
  const r = el("div", {class: "r"});
  a.beelden.forEach((b, j) => r.append(fig(b.beeld, `B${j + 1}: v2 ${b.v2} → v3 ${b.v3}` + (b.gelezen ? ` · gelezen ${b.gelezen}` : ""),
    b.gelezen && b.gelezen !== b.v3 ? "anders" : "")));
  document.getElementById("a").append(el("div", {class: "k"}, el("b", {}, `A${i} `), el("a", {href: a.artikel, target: "_blank"}, a.artikel), r));
});
DATA.paren.forEach(p => {
  if (ALLEEN && ALLEEN !== `P${p.nr}`) return;
  document.getElementById("p").append(el("div", {class: "k"}, el("b", {}, `P${p.nr} · ${p.sleutel.slice(0, 90)}`),
    el("div", {class: "r"}, fig(p.vraag, "vraag"), fig(p.beeld, `artikel · ${p.punten} pt, ${p.dekking}`)),
    el("a", {href: p.artikel, target: "_blank"}, p.artikel)));
});
</script>"""


def _rolronde_tellen() -> dict:  # pragma: no cover - op de bestanden
    vragen, paren, rollen2, d = _stand()
    rollen3, labels = _rolronde_rollen(), _rolronde_labels(d)
    voorspeld = {f"{a}|{b}": r for (a, b), r in rollen3.items()}
    lees125 = d.get("rollen", {})
    lees42 = json.loads(ROLLABELS.read_text(encoding="utf-8")).get("rollen", {})
    voor = {m: telling(vragen, paren, labels, rollen2, m) for m in MODI}
    na = {m: telling(vragen, paren, labels, rollen3, m) for m in MODI}
    kaart = _jsonl(MAP / "rolronde-kaart.jsonl")
    uit = {
        "artikelen": {"in de set": len(json.loads((MAP / "rolronde-set.json").read_text(encoding="utf-8"))),
                      "status": dict(collections.Counter(r["status"] for r in kaart)),
                      "beantwoord": len(_jsonl(MAP / "rolronde.jsonl"))},
        "de 125": rol_telling(lees125, voorspeld),
        "de 42": {"viraal gevonden": sum(voorspeld.get(k) == "viraal" for k, r in lees42.items() if r == "viraal"),
                  "vals viraal": sum(voorspeld.get(k) == "viraal" for k, r in lees42.items() if r != "viraal"),
                  "verwarring": dict(collections.Counter(f"{r} -> {voorspeld.get(k, '?')}" for k, r in lees42.items()))},
        "rollen v2 -> v3": dict(collections.Counter(
            f"{rollen2.get(k, '-')} -> {r}" for k, r in rollen3.items() if rollen2.get(k) != r).most_common(12)),
        "voor": {m: {s: {x: v[x] for x in ("gevonden", "vals")} for s, v in voor[m].items() if isinstance(v, dict)}
                 for m in MODI},
        "na": {m: {s: {x: v[x] for x in ("gevonden", "vals")} for s, v in na[m].items() if isinstance(v, dict)}
               for m in MODI},
        "eisen": rolronde_eisen(lees125, voorspeld, lees42, voorspeld, voor["productie"], voor["kopie"],
                                na["productie"], na["kopie"]),
        "kosten": round(_rolronde_uitgegeven(), 3),
    }
    (MAP / "rolronde-uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De vindronde (PLAN #32.21)")
    parser.add_argument("stap", choices=("set", "kopie", "vision", "vragen", "pool", "rollen", "viraal", "zoeken",
                                         "vergelijken", "lezen", "po", "tellen", "opruimen", "rolvoormeting",
                                         "rolronde"))
    parser.add_argument("deel", nargs="?", choices=("indienen", "ophalen", "lezen", "tellen", "set"))
    parser.add_argument("--set", dest="sets", action="append", choices=SETS)
    parser.add_argument("--proef", type=int, default=0)
    parser.add_argument("--max", type=int, help="pool: de proef, één artikel per host")
    args = parser.parse_args()
    if args.stap == "set":
        print(json.dumps(_set(), ensure_ascii=False, indent=1))
    elif args.stap == "kopie":
        _kopie()
    elif args.stap == "vision":
        _vision()
    elif args.stap == "vragen":
        _vragen(args.sets or list(SETS), args.proef)
    elif args.stap == "pool":
        _pool(args.max)
    elif args.stap == "rollen":
        _rollen_stap(args.deel or "ophalen", args.proef)
    elif args.stap == "viraal":
        _viraal_stap(args.deel or "ophalen", args.proef)
    elif args.stap == "zoeken":
        _zoeken()
    elif args.stap == "vergelijken":
        _vergelijken()
    elif args.stap == "lezen":
        _lezen()
    elif args.stap == "po":
        _po()
    elif args.stap == "rolronde":   # #32.26
        if args.deel == "set":
            _rolronde_set()
        elif args.deel == "indienen":
            _rolronde_indienen(args.proef)
        elif args.deel == "ophalen":
            _rolronde_ophalen()
        elif args.deel == "lezen":
            _rolronde_lezen()
        elif args.deel == "tellen":
            print(json.dumps(_rolronde_tellen(), ensure_ascii=False, indent=1))
        else:
            parser.error("rolronde set|indienen [--proef N]|ophalen|lezen|tellen")
    elif args.stap == "rolvoormeting":   # #32.25
        if args.deel == "tellen":
            print(json.dumps(_rolvoormeting_tellen(), ensure_ascii=False, indent=1))
        else:
            _rolvoormeting_lezen()
    elif args.stap == "tellen":
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))
    else:
        opruimen()


if __name__ == "__main__":
    main()
