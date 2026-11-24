"""De woorden zoeken, het beeld bevestigt: een voormeting met drie sleutels (PLAN #32.17).

Vastgelegd vóór het ophalen en vóór de eerste vraag, in PLAN #32.17:

- **per vraag drie sleutels**: de tekst (gelezen en gemaskeerd zoals in `/check`; bij minstens 20 tekens "beweringen
  eerst" en het geheugen, bij N en W het geheugen van §178), een beschrijving van de foto (`beschrijvingvraag`, Haiku
  met het beeld) met hetzelfde geheugen, en het beeld als bevestiging tegen de beelden in de artikelen van de
  kandidaat-checks (de twee lijsten samen, hooguit tien);
- **bevestigd**: PDQ binnen 31 bits (beide hashes met kwaliteit 50), of minstens 50 punten die samen minstens 10% van
  de vraag beslaan (`beeldvraag.bevestigd`); de vraag is het beeldgebied als er een is, anders het hele beeld;
- **telt niet**: een artikelbeeld met het adres van de vraag, of als geheel binnen 31 bits van de vraag als geheel (bij
  N, W en S3, want die beelden komen uit een factcheckartikel), en huisstijl: een beeldadres bij drie of meer
  beweringen;
- **sets**: N, R3, W en S1 tot S4 beslissen; R2 ter vergelijking met §187;
- **lezen**: elke bevestiging die telt, ook in de eigen bewering, in `LABELS`; de eisen in `eisen`.

Beelden alleen in het werkgeheugen (DR3, B35). Op schijf per vraag de beschrijving, de beweringen, de kandidaten, de
hashes en de punten (die wist `opruimen` na `tellen`); per paar de afstand, de punten en de dekking.

    python -m doublecheck.beeldbevestiging set
    python -m doublecheck.beeldbevestiging vision
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldbevestiging vragen [--set N] [--proef 5]
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldbevestiging vergelijken [--max 20]
    python -m doublecheck.beeldbevestiging herbereken      (§189, verkennend: de paren opnieuw zonder ingeklapte vorm)
    python -m doublecheck.beeldbevestiging lezen|tellen|opruimen
"""

from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import random
import re
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from doublecheck import beeldindexmeting as bm
from doublecheck import beeldvraag as bv
from doublecheck import beschrijvingvraag as bs
from doublecheck.beeldstap import beeldkenmerken

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "beeldbevestiging"
LABELS = WORTEL / "docs" / "steekproeven" / "32.17-beeldbevestiging.json"
BEELDRONDE = WORTEL / "data" / "beeldronde" / "set.jsonl"      # N en W, met het geheugen van §178
BUDGET = 3.0                       # PO 2026-10-30: "grens $3"
VISIEPRIJS = 1.50 / 1000           # Google Vision tegen de lijstprijs: zo telt de grens de gratis 1.000 nooit mee
SETS = ("N", "R3", "W", "S1", "S2", "S3", "S4", "R2")
SETS_S = ("S1", "S2", "S3", "S4")
BESLISSEND = ("N", "R3", "W") + SETS_S
MET_UITSLUITING = frozenset({"N", "W", "S3"})
PER_CLAIM = frozenset({"R2", "R3"})
R3_N, R3_ZAAD, R3_TOT = 100, 3217, "2026-10-29"
S3_N, S3_ZAAD = 500, 3218
DREMPEL_PDQ, MIN_PUNTEN, MIN_DEKKING = 31, 50, 0.10     # vooraf, PLAN #32.17; niet bijstellen na de uitslag
STERKSTE = 500
HUISSTIJL_GROEPEN = 3
MIN_TEKENS = 20
MAX_KOPIEEN, MAX_BEELDEN, MIN_ZIJDE = bm.MAX_KOPIEEN, bm.MAX_BEELDEN, bm.MIN_ZIJDE
GEVONDEN, ANDERE, VALS = bm.GEVONDEN, bm.ANDERE, bm.VALS
LABELWAARDEN = bm.LABELWAARDEN
# de regel van de meting en de verkennende varianten: (punten, sleutel voor de punten, sleutel voor de dekking)
VARIANTEN = {"hoofd": (MIN_PUNTEN, "punten", "dekking"), "20 punten": (20, "punten", "dekking"),
             "100 punten": (100, "punten", "dekking"), "500 sterkste": (MIN_PUNTEN, "punten500", "dekking500")}
_WAYBACK = re.compile(r"^https?://web\.archive\.org/web/\d+[a-z_]*/(.+)$", re.IGNORECASE)


class Weigering(Exception):
    """Tellen kan niet: een bevestiging zonder label."""


# --- de sets -------------------------------------------------------------------------------------

def r3_claims(rijen: list[tuple], r2_ids: set[str]) -> list[dict]:
    """100 verse beeldclaims volgens de regel van R2 (#32.15), tot en met 29 oktober 2026, niet in R2, zaad 3217."""
    lijst = [c for c in bm.r2_kandidaten(rijen) if c["datum"] <= R3_TOT and c["claim_id"] not in r2_ids]
    return sorted(random.Random(R3_ZAAD).sample(lijst, min(R3_N, len(lijst))), key=lambda c: c["claim_id"])


def s3_keuze(werk: list[str]) -> list[str]:
    """500 van de beelden uit de rest van M4FC die in #32.15 lukten, zaad 3218."""
    lijst = sorted(set(werk), key=int)
    return sorted(random.Random(S3_ZAAD).sample(lijst, min(S3_N, len(lijst))), key=int)


# --- de kandidaten -------------------------------------------------------------------------------

def kandidaten(tekst: list[dict], beschrijving: list[dict], groep) -> list[dict]:
    """De checks uit het geheugen van de tekst en van de beschrijving samen, elk één keer, met waar ze vandaan komen;
    `groep(claim)` geeft het cluster, anders de claim."""
    uit: dict[str, dict] = {}
    for via, lijst in (("tekst", tekst), ("beschrijving", beschrijving)):
        for k in lijst:
            if k["claim"] not in uit:
                uit[k["claim"]] = {"claim": k["claim"], "url": k["url"], "gelijkenis": k["gelijkenis"],
                                   "redactie": k.get("redactie"), "groep": groep(k["claim"]) or k["claim"], "via": []}
            uit[k["claim"]]["via"].append(via)
    return list(uit.values())


def vraag(meta: dict, beeld: bytes, *, lees, beweer, beschrijf, zoek, groep, slot=None) -> tuple[dict, dict]:
    """Eén vraag met de drie sleutels. De tekst: `lees(beeld)` (gelezen en gemaskeerd), bij minstens 20 tekens
    `beweer(tekst)` en `zoek(tekst, beweringen)`; N en W brengen hun geheugen mee. De beschrijving: `beschrijf(beeld)`
    en `zoek(beschrijving, ...)`. Dan de hashes en de punten van het beeldgebied (anders het hele beeld), onder
    `slot` als dat er is. Geeft de regel en de punten; de tekst en het beeld blijven hier."""
    slot = slot or contextlib.nullcontext()
    tijd, kosten, nu = {}, 0.0, time.perf_counter
    tekens, gehaald, tekstlijst = None, [], []
    if meta.get("geheugen") is not None:
        tekstlijst = list(meta["geheugen"])
    else:
        b = nu()
        tekst = lees(beeld)
        tijd["lezen"] = nu() - b
        tekens = len(tekst.strip())
        if tekens >= MIN_TEKENS:
            b = nu()
            gehaald, k = beweer(tekst)
            kosten += k
            tijd["beweringen"] = nu() - b
            b = nu()
            tekstlijst = zoek(tekst, gehaald)
            tijd["geheugen tekst"] = nu() - b
        del tekst
    b = nu()
    beschrijving, k = beschrijf(beeld)
    kosten += k
    tijd["beschrijving"] = nu() - b
    beeldlijst = []
    if beschrijving:
        b = nu()
        beeldlijst = zoek(beschrijving["beschrijving"], bs.als_beweringen(beschrijving))
        tijd["geheugen beschrijving"] = nu() - b
    b = nu()
    with slot:
        kenmerken, punten = _vraagkenmerken(beeld)
    tijd["kenmerken"] = nu() - b
    regel = {**{k: v for k, v in meta.items() if k not in ("geheugen", "tekst")}, "tekens": tekens,
             "beweringen": gehaald, "beschrijving": beschrijving["beschrijving"] if beschrijving else None,
             "zoekvragen": beschrijving["zoekvragen"] if beschrijving else [],
             "kandidaten": kandidaten(tekstlijst, beeldlijst, groep), **kenmerken, "kosten": round(kosten, 6),
             "seconden": {k: round(v, 3) for k, v in tijd.items()}}
    return regel, punten


def _vraagkenmerken(beeld: bytes) -> tuple[dict, dict]:
    """De PDQ-hashes van het hele beeld en het beeldgebied met hun kwaliteit, en de punten van het beeldgebied (anders
    van het hele beeld), zoals `beeldvraag.vraagkenmerken` het gebied zoekt."""
    from doublecheck.beelduitsnede import beeldgebied
    from doublecheck.image_fingerprint import pdq_met_kwaliteit

    b = bv._open(beeld)
    gebied = beeldgebied(b)
    delen = [b] + ([b.crop(gebied)] if gebied else [])
    hashes = [pdq_met_kwaliteit(d) for d in delen]
    punten = bv.puntkenmerken(delen[-1])
    return ({"pdq": [h for h, _ in hashes], "kwaliteit": [q for _, q in hashes],
             "gebied": list(gebied) if gebied else None, "punten_n": len(punten["des"])}, punten)


# --- vergelijken ---------------------------------------------------------------------------------

def _afstand(een: str, twee: str) -> int:
    return (int(een, 16) ^ int(twee, 16)).bit_count()


def _adres(url: str) -> str:
    """Een beeldadres zonder schema, www, zoekdeel en dubbele schuine strepen; een kopie in de Wayback Machine is het
    adres dat erin staat."""
    m = _WAYBACK.match(url)
    deel = urlsplit(m.group(1) if m else url)
    return (deel.hostname or "").lower().removeprefix("www.") + re.sub(r"/{2,}", "/", unquote(deel.path))


def uitgesloten(vraag_: dict, beeld: dict) -> bool:
    """Bij N, W en S3 komt de vraag zelf uit een factcheckartikel: een artikelbeeld met haar adres, of als geheel binnen
    31 bits van de vraag als geheel, is de vraag en geen vondst."""
    if vraag_["set"] not in MET_UITSLUITING:
        return False
    if _adres(beeld["beeld"]) in {_adres(a) for a in vraag_.get("adressen") or []}:
        return True
    return _afstand(vraag_["pdq"][0], beeld["pdq"][0]) <= DREMPEL_PDQ


def huisstijl(artikelen: list[dict]) -> set[str]:
    """De beeldadressen die in de artikelen van drie of meer beweringen staan: een logo, een auteursfoto, een meter."""
    groepen = collections.defaultdict(set)
    for a in artikelen:
        for b in a.get("beelden") or []:
            groepen[_adres(b)] |= set(a.get("groepen") or [])
    return {b for b, g in groepen.items() if len(g) >= HUISSTIJL_GROEPEN}


# de kenmerken van een artikelbeeld komen uit de kern, zoals de beeldstap van het product ze gebruikt (#32.35)
artikelbeeld = beeldkenmerken


def vergelijk(regel: dict, punten: dict, kandidaat: dict, beeld: dict) -> dict:
    """Eén vraag tegen één beeld uit het artikel van een kandidaat: de kleinste PDQ-afstand tussen hashes met genoeg
    kwaliteit (anders `None`), de afstand van het geheel, de uitsluiting, en de punten met hun dekking, ook met alleen
    de 500 sterkste."""
    begin = time.perf_counter()
    vraaghashes = [h for h, q in zip(regel["pdq"], regel["kwaliteit"]) if q >= bv.MIN_KWALITEIT]
    pdq = min(_afstand(a, b) for a in vraaghashes for b in beeld["pdq"]) \
        if vraaghashes and beeld["kwaliteit"] >= bv.MIN_KWALITEIT else None
    n, dekking = bv.puntvergelijking(punten, beeld["punten"])
    n5, dekking5 = bv.puntvergelijking(bv.sterkste(punten, STERKSTE), bv.sterkste(beeld["punten"], STERKSTE))
    return {"vraag": regel["id"], "set": regel["set"], "artikel": kandidaat["url"], "claim": kandidaat["claim"],
            "groep": kandidaat["groep"], "via": kandidaat["via"], "beeld": beeld["beeld"],
            "breedte": beeld["breedte"], "hoogte": beeld["hoogte"], "kwaliteit": beeld["kwaliteit"], "pdq": pdq,
            "heel": _afstand(regel["pdq"][0], beeld["pdq"][0]), "uitgesloten": uitgesloten(regel, beeld),
            "punten": n, "dekking": round(dekking, 4), "punten500": n5, "dekking500": round(dekking5, 4),
            "seconden": round(time.perf_counter() - begin, 4)}


def bevestigd(paar: dict, variant: str = "hoofd") -> bool:
    n, kp, kd = VARIANTEN[variant]
    return bv.bevestigd(paar["pdq"], paar[kp], paar[kd], drempel_pdq=DREMPEL_PDQ, min_punten=n,
                        min_dekking=MIN_DEKKING)


def telt(paar: dict, huisstijl_: set[str]) -> bool:
    return not paar["uitgesloten"] and _adres(paar["beeld"]) not in huisstijl_


# --- tellen -------------------------------------------------------------------------------------

def labelsleutel(paar: dict) -> str:
    return f"{paar['set']}|{paar['vraag']}|{paar['beeld']}"


def te_lezen(vragen: list[dict], paren: list[dict], labels: dict[str, str], huisstijl_: set[str],
             variant: str = "hoofd") -> list[dict]:
    """Elke bevestiging die telt en nog geen label heeft, elk paar van vraag en beeld één keer."""
    bekend = {(v["set"], v["id"]) for v in vragen}
    uit, gezien = [], set()
    for p in paren:
        sleutel = labelsleutel(p)
        if (p["set"], p["vraag"]) in bekend and telt(p, huisstijl_) and bevestigd(p, variant) \
                and sleutel not in labels and sleutel not in gezien:
            gezien.add(sleutel)
            uit.append(p)
    return uit


def _tel(vragen: list[dict], paren: list[dict], labels: dict[str, str], huisstijl_: set[str], aantallen: dict,
         variant: str) -> dict:
    eigen = {(v["set"], v["id"]): set(v.get("groepen") or []) for v in vragen}
    claim = {(v["set"], v["id"]): v.get("claim_id") for v in vragen}
    tel = collections.defaultdict(collections.Counter)
    gevonden, elders, andere, vals = (collections.defaultdict(set) for _ in range(4))
    via = {"tekst": collections.defaultdict(set), "beschrijving": collections.defaultdict(set)}
    for p in paren:
        sleutel = (p["set"], p["vraag"])
        if sleutel not in eigen or not telt(p, huisstijl_) or not bevestigd(p, variant):
            continue
        s, label = p["set"], labels.get(labelsleutel(p))
        tel[s]["bevestigingen"] += 1
        if label is None:
            tel[s]["ongelezen"] += 1
            continue
        eenheid = claim[sleutel] if s in PER_CLAIM else p["vraag"]
        if label == GEVONDEN and p["groep"] in eigen[sleutel]:
            gevonden[s].add(eenheid)
            for k in p["via"]:
                via[k][s].add(eenheid)
        elif label == GEVONDEN:
            elders[s].add(eenheid)
        elif label == ANDERE:
            andere[s].add(p["vraag"])
            tel[s]["andere paren"] += 1
        else:
            vals[s].add(p["vraag"])
            tel[s]["vals paren"] += 1
    uit = {}
    for s in SETS:
        d = {"vragen": sum(v["set"] == s for v in vragen), "bevestigingen": tel[s]["bevestigingen"],
             "ongelezen": tel[s]["ongelezen"], "gevonden": len(gevonden[s]), "via tekst": len(via["tekst"][s]),
             "via beschrijving": len(via["beschrijving"][s]),
             "beschrijving voegt toe": len(gevonden[s] - via["tekst"][s]),
             "gevonden elders": len(elders[s] - gevonden[s]), "andere bewering": len(andere[s]),
             "andere paren": tel[s]["andere paren"], "vals": len(vals[s]), "vals paren": tel[s]["vals paren"]}
        if s in PER_CLAIM:
            d["claims"] = aantallen.get(s, 0)
        if s == "W":
            d["terecht"] = d["gevonden elders"]
        uit[s] = d
    from doublecheck.cijfers import _bovengrens

    n = sum(uit[s]["vragen"] for s in BESLISSEND)
    k = sum(uit[s]["vals"] for s in BESLISSEND)
    uit["samen"] = {"vragen": n, "vals": k, "per 1.000": round(1000 * k / n, 2) if n else None,
                    "bovengrens": _bovengrens(k, n) if n else None}
    return uit


def eisen(hoofd: dict) -> dict:
    """De drie eisen van PLAN #32.17, vooraf vastgelegd."""
    return {"1. N: bij minstens 20 van de 58 screenshots bevestigt het beeld de eigen check": hoofd["N"]["gevonden"] >= 20,
            "2. R3: bij minstens 30 van de 100 verse claims bevestigt een kopie de eigen check":
                hoofd["R3"]["gevonden"] >= 30,
            "3. vals: bij W geen enkele, over N, R3, W en S samen hoogstens 1 per 1.000 vragen":
                hoofd["W"]["vals paren"] == 0 and hoofd["samen"]["vals"] * 1000 <= hoofd["samen"]["vragen"]}


def herberekend(paren: list[dict], opnieuw: dict[str, dict]) -> list[dict]:
    """De paren met de punten van de herstelde vergelijking (§189) waar die er zijn; de rest zoals hij draaide."""
    return [{**p, **opnieuw[labelsleutel(p)]} if labelsleutel(p) in opnieuw else p for p in paren]


def telling(vragen: list[dict], paren: list[dict], labels: dict[str, str], huisstijl_: set[str],
            aantallen: dict, opnieuw: dict[str, dict] | None = None) -> dict:
    """Per set wat gevonden is (per vraag, bij R2 en R3 per claim), via welke sleutel, wat elders of bij een andere
    bewering bevestigd is en wat vals; de eisen; en de verkennende varianten, die niet weigeren maar tellen wat
    ongelezen is. Met `opnieuw` ook alle varianten na de reparatie van §189, verkennend: de eisen blijven op de regel
    zoals hij draaide. Weigert zolang een bevestiging van de regel geen label heeft."""
    open_ = te_lezen(vragen, paren, labels, huisstijl_)
    if open_:
        raise Weigering(f"{len(open_)} bevestigingen zonder label in {LABELS.name}, bijvoorbeeld {labelsleutel(open_[0])}")
    hoofd = _tel(vragen, paren, labels, huisstijl_, aantallen, "hoofd")
    e = eisen(hoofd)
    uit = {"hoofd": hoofd, "eisen": e, "gehaald": all(e.values()),
           "verkennend": {v: _tel(vragen, paren, labels, huisstijl_, aantallen, v) for v in VARIANTEN if v != "hoofd"}}
    if opnieuw is not None:
        na = herberekend(paren, opnieuw)
        uit["na de reparatie"] = {v: _tel(vragen, na, labels, huisstijl_, aantallen, v) for v in VARIANTEN}
        uit["na de reparatie"]["eisen, ter vergelijking"] = eisen(uit["na de reparatie"]["hoofd"])
    return uit


def gevonden_vragen(vragen: list[dict], paren: list[dict], labels: dict[str, str], huisstijl_: set[str],
                    set_: str) -> set[str]:
    """De vragen van één set waar het beeld de eigen check bevestigt (gelezen als zelfde beeld, zelfde bewering)."""
    eigen = {v["id"]: set(v.get("groepen") or []) for v in vragen if v["set"] == set_}
    return {p["vraag"] for p in paren if p["set"] == set_ and p["vraag"] in eigen and telt(p, huisstijl_)
            and bevestigd(p) and labels.get(labelsleutel(p)) == GEVONDEN and p["groep"] in eigen[p["vraag"]]}


def over_budget(regels: list[dict], vision: int) -> bool:
    """Ruimte voor wat nog loopt: stoppen vóór de grens."""
    return sum(r.get("kosten") or 0 for r in regels) + vision * VISIEPRIJS > BUDGET - 0.05


# --- de bestanden ------------------------------------------------------------------------------

_SCHRIJFSLOT = threading.Lock()


def _jsonl(pad: Path) -> list[dict]:
    return bm._jsonl(pad)


def schrijf(pad: Path, regels: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    bm._schrijf(pad, regels, _SCHRIJFSLOT)


def _puntpad(map_: Path, regel: dict) -> Path:
    return map_ / "punten" / regel["set"] / (hashlib.sha1(regel["id"].encode()).hexdigest()[:20] + ".npz")


def schrijf_vraag(map_: Path, regel: dict, punten: dict) -> None:
    """Eerst de punten, dan de regel: een regel heeft altijd haar punten."""
    pad = _puntpad(map_, regel)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_bytes(bv.punten_naar_bytes(punten))
    schrijf(map_ / "vragen.jsonl", [regel])


def lees_punten(map_: Path, regel: dict) -> dict:
    return bv.punten_uit_bytes(_puntpad(map_, regel).read_bytes())


def opruimen(map_: Path) -> None:
    """De punten van de vragen weg na het tellen: uit veel punten is een ruwe versie van het beeld terug te rekenen."""
    shutil.rmtree(map_ / "punten", ignore_errors=True)


def lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    labels = json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {})
    fout = {k: v for k, v in labels.items() if v not in LABELWAARDEN}
    if fout:
        raise Weigering(f"onbekende labels in {LABELS.name}: {list(fout.items())[:3]}")
    return labels


def _lees_set() -> dict:
    pad = MAP / "set.json"
    if not pad.exists():
        raise Weigering("eerst: python -m doublecheck.beeldbevestiging set")
    return json.loads(pad.read_text(encoding="utf-8"))


def _groep_van() -> dict[str, str]:  # pragma: no cover - op de database
    return {c: (cl or c) for c, cl in bm._db().execute("SELECT claim_id, cluster_id FROM claim")}


# --- set ----------------------------------------------------------------------------------------

def _set() -> dict:  # pragma: no cover - op de database en de bestanden van #32.15
    from doublecheck.beeldstilte import onderschriften

    groep = _groep_van()
    m4fc = json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8"))
    uit: dict[str, list] = {s: [] for s in SETS}
    for s in _jsonl(BEELDRONDE):
        item = m4fc[int(Path(s["beeld"]).stem)]
        uit[s["set"]].append({"id": s["id"], "set": s["set"], "beeld": s["beeld"],
                              "adressen": [a for a in (item.get("image_url"), item.get("wayback_image_url")) if a],
                              "vraag": item.get("image_url") or item.get("wayback_image_url"),
                              "groepen": sorted({groep.get(c, c) for c in s.get("eigen") or []}),
                              "eigen": s.get("eigen") or [], "geheugen": s["geheugen"]})
    oud = bm._lees_set()
    for c in r3_claims(bm._rijen(bm._db()), {c["claim_id"] for c in oud["r2"]}):
        uit["R3"].append({"claim_id": c["claim_id"], "groep": c["groep"], "url": c["url"], "uitgever": c["uitgever"],
                          "datum": c["datum"]})
    for r in _jsonl(bm.MAP / "vragen" / "R2.jsonl"):
        uit["R2"].append({"id": r["werk"], "set": "R2", "vraag": r["vraag"], "adressen": [r["vraag"]],
                          "claim_id": r["claim_id"], "groepen": [r["groep"]], "soort": r["soort"],
                          "pagina": r["pagina"], "rang": r["rang"]})
    lijsten = {s: json.loads((bm.MAP / "vragen" / f"{s}-lijst.json").read_text(encoding="utf-8")) for s in SETS_S}
    gelukt = [r["werk"] for r in _jsonl(bm.MAP / "vragen" / "S3.jsonl") if r["vorm"] == "origineel"]
    s3 = set(s3_keuze(gelukt))
    for s in ("S1", "S2", "S3"):
        for w in lijsten[s]:
            if s != "S3" or w["werk"] in s3:
                uit[s].append({"id": w["werk"], "set": s, "vraag": w["vraag"], "adressen": w["adressen"],
                               **{k: w[k] for k in ("persoon", "titel") if k in w}})
    teksten = onderschriften(bm._jsonl(WORTEL / "data" / "stiltetoets" / "regels.jsonl"),
                             bm.S4_EERDER + bm.S4_SJABLONEN * bm.S4_PER_SJABLOON)[bm.S4_EERDER:]
    for w in lijsten["S4"]:
        for k in range(bm.S4_PER_SJABLOON):
            uit["S4"].append({"id": f"{w['werk']}#{k}", "set": "S4", "vraag": w["vraag"], "adressen": w["adressen"],
                              "sjabloon": w["naam"], "onderschrift": teksten[w["rang"] * bm.S4_PER_SJABLOON + k]})
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / "set.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return {s: len(v) for s, v in uit.items()}


# --- Vision voor R3 ---------------------------------------------------------------------------------

def _pagina(web: bm.Beleefd, url: str):  # pragma: no cover - netwerk
    """(status, beeldadressen) van een artikel, beleefd: robots.txt, één verzoek tegelijk per host."""
    from doublecheck.artikelbeelden import beelden_uit_artikel

    if bm.host(url) in bm.UITGESLOTEN:
        return "uitgesloten", []
    if not web.mag(url):
        return "verboden", []
    antwoord = web._vraag(url)
    if antwoord is None or antwoord.status_code != 200:
        return ("fout" if antwoord is None else antwoord.status_code), []
    try:
        return 200, beelden_uit_artikel(antwoord.text, str(antwoord.url))[:MAX_BEELDEN]
    except Exception:   # een pagina die niet te lezen is
        return "onleesbaar", []


def _groot_genoeg(inhoud: bytes) -> bool:  # pragma: no cover - op echte beelden
    from doublecheck.image_fingerprint import as_image

    try:
        return min(as_image(inhoud).size) >= MIN_ZIJDE
    except Exception:
        return False


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
    pad = MAP / "r3-vision.jsonl"
    klaar = {r["claim_id"] for r in _jsonl(pad)}
    web, teller, slot = bm.Beleefd(), collections.Counter(), threading.Lock()
    per_host = collections.defaultdict(list)
    for c in _lees_set()["R3"]:
        if c["claim_id"] not in klaar:
            per_host[bm.host(c["url"])].append(c)

    def doe(lijst):
        for c in lijst:
            status, adressen = _pagina(web, c["url"])
            antwoorden = []
            for adres in adressen:
                inhoud = web.beeld(adres)
                if inhoud is None or not _groot_genoeg(inhoud):
                    continue
                verzoek = {"requests": [{"image": {"content": base64.b64encode(inhoud).decode()},
                                         "features": [{"type": "WEB_DETECTION", "maxResults": MAX_RESULTATEN}]}]}
                del inhoud
                for poging in range(4):
                    a = httpx.post(VISION, params={"key": sleutel}, json=verzoek, timeout=60)
                    if a.status_code == 200:
                        antwoorden.append({"beeld": adres, **a.json()})
                        break
                    if a.status_code not in (429, 500, 502, 503, 504):
                        raise RuntimeError(f"Vision {a.status_code}")
                    time.sleep(5 * 2 ** poging)
            schrijf(pad, [{"claim_id": c["claim_id"], "url": c["url"], "status": status, "beelden": adressen,
                           "antwoorden": antwoorden}])
            with slot:
                teller["claims"] += 1
                teller["zoekvragen"] += len(antwoorden)
            print(f"{c['claim_id']}: {status}, {len(adressen)} beelden, {len(antwoorden)} zoekvragen", flush=True)

    with cf.ThreadPoolExecutor(6) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {dict(teller)}", flush=True)


def _vision_aantal() -> int:
    return sum(len(r["antwoorden"]) for r in _jsonl(MAP / "r3-vision.jsonl"))


def _kopieen_r3() -> list[dict]:  # pragma: no cover - op de antwoorden van Vision
    sites = bm._factchecksites()
    claims = {c["claim_id"]: c for c in _lees_set()["R3"]}
    werk = []
    for r in _jsonl(MAP / "r3-vision.jsonl"):
        c = claims[r["claim_id"]]
        for i, k in enumerate(bm.kopieen(r["antwoorden"], sites, bm.host(c["url"]))):
            werk.append({"id": f"{c['claim_id']}#{i}", "set": "R3", "vraag": k["beeld"], "adressen": [k["beeld"]],
                         "claim_id": c["claim_id"], "groepen": [c["groep"]], "soort": k["soort"],
                         "pagina": k["pagina"], "rang": i})
    return werk


# --- vragen -------------------------------------------------------------------------------------

def _rekenen():  # pragma: no cover - laadt de modellen
    import cv2
    import torch

    torch.set_num_threads(2)   # hoogstens twee kernen (PO)
    cv2.setNumThreads(2)


def _haiku_kosten(antwoord) -> float:
    from doublecheck.modellen import MODELLEN

    p = MODELLEN["haiku"]
    return 2 * (antwoord.usage.input_tokens * p["in"] + antwoord.usage.output_tokens * p["uit"]) / 1e6   # live: 2x


def _meme(sjabloon: bytes, onderschrift: str) -> bytes:  # pragma: no cover - op een echt sjabloon
    import io

    from doublecheck.beeldstilte import maak_meme, splits
    from doublecheck.image_fingerprint import as_image

    beeld = as_image(sjabloon).convert("RGB")
    beeld.thumbnail((bv.MAX_ZIJDE, bv.MAX_ZIJDE))
    buf = io.BytesIO()
    maak_meme(beeld, *splits(onderschrift)).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _vragen(sets: list[str], proef: int) -> None:  # pragma: no cover - netwerk en modellen
    import concurrent.futures as cf
    import dataclasses

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.modellen import MODELLEN
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    _rekenen()
    laad_sleutel()
    config = load_config(None)
    cfg = dataclasses.replace(config, berichtcontrole=dataclasses.replace(
        config.berichtcontrole, beweringen="beweringen-v1", beweringen_model=MODELLEN["haiku"]["id"]))
    client = anthropic.Anthropic(max_retries=6)
    groep = _groep_van()
    rekenen, lokaal, slot = threading.Lock(), threading.local(), threading.Lock()
    web = bm.Beleefd()
    pad, mislukt = MAP / "vragen.jsonl", MAP / "vragen.mislukt.jsonl"
    vision = _vision_aantal()

    def conn():
        if not hasattr(lokaal, "conn"):
            lokaal.conn = connect(str(WORTEL / "doublecheck.db"))
        return lokaal.conn

    def lees(beeld):
        with rekenen:
            return bc.bericht_uit(None, beeld, config.ocr)

    def beweer(tekst):
        return bc.beweringen_vragen(tekst, client, cfg, screenshot=True)

    def beschrijf(beeld):
        a = client.messages.create(**bs.verzoek(beeld))
        return bs.lees_beschrijving("".join(getattr(b, "text", "") or "" for b in a.content)), _haiku_kosten(a)

    def zoek(tekst, gehaald):
        with rekenen:
            fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
            return bc.geheugen_met(conn(), cfg, tekst, fp, gehaald)

    sjablonen: dict[str, bytes | None] = {}

    def beeld_van(w) -> bytes | None:
        if w["set"] in ("N", "W"):
            return Path(w["beeld"]).read_bytes()
        if w["set"] == "S4":
            sleutel = w["vraag"]
            if sleutel not in sjablonen:
                sjablonen[sleutel] = next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)
            return _meme(sjablonen[sleutel], w["onderschrift"]) if sjablonen[sleutel] else None
        return next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)

    def doe(w) -> None:
        with slot:
            if over_budget(_jsonl(pad), vision):
                return
        beeld = beeld_van(w)
        regel, fout = None, "niet opgehaald"
        if beeld is not None:
            try:
                regel, punten = vraag(w, beeld, lees=lees, beweer=beweer, beschrijf=beschrijf, zoek=zoek,
                                      groep=groep.get, slot=rekenen)
            except anthropic.APIError:
                raise
            except Exception as e:   # kapot of geen beeld: overslaan; alleen de soort fout, nooit de inhoud (DR3)
                regel, fout = None, type(e).__name__
            del beeld
        if regel is None:
            schrijf(mislukt, [{"id": w["id"], "set": w["set"], "fout": fout}])
            return
        schrijf_vraag(MAP, regel, punten)
        with slot:
            print(f"{w['set']} {w['id'][:60]}: {len(regel['kandidaten'])} kandidaten, beschrijving "
                  f"{'ja' if regel['beschrijving'] else 'nee'}, ${regel['kosten']:.4f}", flush=True)

    s = _lees_set()
    for naam in sets:
        werk_alle = _kopieen_r3() if naam == "R3" else s[naam]
        for _ in range(20 if naam in PER_CLAIM else 1):   # R2 en R3: tot elke claim vijf kopieën heeft die lukken
            gedaan = _jsonl(pad)
            geprobeerd = {(r["set"], r["id"]) for r in gedaan + _jsonl(mislukt)}
            gelukt = collections.Counter(r.get("claim_id") for r in gedaan if r["set"] == naam)
            volgende, per_claim = [], collections.Counter()
            for w in werk_alle:
                if (naam, w["id"]) in geprobeerd:
                    continue
                if naam in PER_CLAIM:
                    if gelukt[w["claim_id"]] + per_claim[w["claim_id"]] >= MAX_KOPIEEN:
                        continue
                    per_claim[w["claim_id"]] += 1
                volgende.append(w)
            if proef:
                volgende = volgende[:proef]
            if not volgende:
                break
            print(f"{naam}: {len(volgende)} vragen", flush=True)
            with cf.ThreadPoolExecutor(4) as pool:
                list(pool.map(doe, volgende))
            if proef:
                break
    regels = _jsonl(pad)
    print(f"samen {len(regels)} vragen, ${sum(r['kosten'] for r in regels):.2f} aan Haiku, "
          f"{vision} zoekvragen aan Vision", flush=True)


# --- vergelijken --------------------------------------------------------------------------------

def _vergelijken(max_artikelen: int | None) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf
    import functools

    _rekenen()
    regels = _jsonl(MAP / "vragen.jsonl")
    per_artikel = collections.defaultdict(list)
    for r in regels:
        for k in r["kandidaten"]:
            if k.get("url"):
                per_artikel[k["url"]].append((r, k))
    apad, ppad = MAP / "artikelen.jsonl", MAP / "paren.jsonl"
    klaar = {a["url"] for a in _jsonl(apad)}
    per_host = collections.defaultdict(list)
    for url in sorted(per_artikel):
        if url not in klaar:
            per_host[bm.host(url)].append(url)
    if max_artikelen:
        per_host = {h: lijst[:1] for h, lijst in list(per_host.items())[:max_artikelen]}
    print(f"{sum(len(v) for v in per_host.values())} artikelen op {len(per_host)} hosts "
          f"({len(klaar)} al gedaan)", flush=True)
    web, rekenen, slot, teller = bm.Beleefd(), threading.Lock(), threading.Lock(), collections.Counter()

    @functools.lru_cache(maxsize=512)
    def punten_van(set_: str, id_: str) -> dict:
        return lees_punten(MAP, {"set": set_, "id": id_})

    def doe(lijst):
        for url in lijst:
            begin = time.monotonic()
            status, adressen = _pagina(web, url)
            paren_, beelden = [], []
            for adres in adressen:
                inhoud = web.beeld(adres)
                if inhoud is None:
                    continue
                try:
                    with rekenen:
                        kenm = artikelbeeld(inhoud)
                        if min(kenm["breedte"], kenm["hoogte"]) >= MIN_ZIJDE:
                            beelden.append(adres)
                            for regel, k in per_artikel[url]:
                                paren_.append(vergelijk(regel, punten_van(regel["set"], regel["id"]), k,
                                                        {"beeld": adres, **kenm}))
                        del kenm
                except Exception as e:   # kapot of geen beeld: overslaan; alleen de soort fout tellen (DR3)
                    with slot:
                        teller[f"fout {type(e).__name__}"] += 1
                del inhoud
            schrijf(ppad, paren_)
            schrijf(apad, [{"url": url, "host": bm.host(url), "status": status, "beelden": beelden,
                            "groepen": sorted({k["groep"] for _, k in per_artikel[url]}),
                            "vragen": len(per_artikel[url]), "seconden": round(time.monotonic() - begin, 1)}])
            with slot:
                teller["artikelen"] += 1
                teller["met beeld"] += bool(beelden)
                teller["beelden"] += len(beelden)
                teller["paren"] += len(paren_)
                teller["bevestigd"] += sum(bevestigd(p) and not p["uitgesloten"] for p in paren_)
                if teller["artikelen"] % 100 == 0:
                    print(f"  {dict(teller)}", flush=True)

    with cf.ThreadPoolExecutor(12) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {dict(teller)}", flush=True)


# --- lezen en tellen ----------------------------------------------------------------------------

def _stand() -> tuple[list[dict], list[dict], set[str]]:
    vragen = _jsonl(MAP / "vragen.jsonl")
    paren = _jsonl(MAP / "paren.jsonl")
    return vragen, paren, huisstijl(_jsonl(MAP / "artikelen.jsonl"))


def _lezen() -> None:  # pragma: no cover - schrijft een leespagina naast de bestanden
    import html

    vragen, paren, stijl = _stand()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    lijst = sorted(te_lezen(vragen, paren, lees_labels(), stijl), key=lambda p: (SETS.index(p["set"]), p["vraag"]))
    conn = bm._db()
    tekst = dict(conn.execute("SELECT claim_id, substr(canonical_text, 1, 300) FROM claim"))
    ronde = {s["id"]: s for s in _jsonl(BEELDRONDE)}
    m4fc = json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8"))
    rijen = []
    for nr, p in enumerate(lijst):
        v = per_vraag[(p["set"], p["vraag"])]
        if p["set"] in ("N", "W"):
            uitleg = ronde[v["id"]]["tekst"][:300]
        elif p["set"] in PER_CLAIM:
            uitleg = tekst.get(v["claim_id"], "")
        elif p["set"] == "S3":
            uitleg = "M4FC: " + m4fc[int(v["id"])]["claim"]
        else:
            uitleg = v.get("onderschrift") or v.get("persoon") or v.get("titel") or ""
        eigen = ", ".join(tekst.get(c, "")[:160] for c in v.get("eigen") or [])
        terug = html.escape(v["adressen"][-1]) if v.get("adressen") else ""
        kort = lambda t, n=150: html.escape((t or "")[:n])   # noqa: E731
        rijen.append(
            f"<div class=k id=k{nr}><b>#{nr}</b> {p['set']} · "
            f"<b>{'EIGEN' if p['groep'] in (v.get('groepen') or []) else 'elders'}</b> · pdq {p['pdq']} · heel "
            f"{p['heel']} · punten {p['punten']} · dekking {p['dekking']} · via {'+'.join(p['via'])}"
            f"<div><img referrerpolicy=no-referrer src='{html.escape(v['vraag'])}' onerror=\"this.src='{terug}'\">"
            f"<img referrerpolicy=no-referrer src='{html.escape(p['beeld'])}'></div>"
            f"<b>vraag:</b> {kort(uitleg)}<br><b>eigen:</b> {kort(eigen, 110)}"
            f"<br><b>kandidaat:</b> {kort(tekst.get(p['claim'], ''))}"
            f"<br><a href='{html.escape(p['artikel'])}'>{kort(p['artikel'], 70)}</a></div>")
    kop = ("<!doctype html><meta charset=utf-8><title>Bevestigingen lezen</title><style>body{font:11px sans-serif;"
           "margin:4px;display:flex;flex-wrap:wrap;gap:6px}.k{width:476px;border:1px solid #bbb;padding:3px}"
           "img{width:234px;height:176px;object-fit:contain;background:#eee;margin:1px}</style>")
    (MAP / "lezen.html").write_text(kop + "".join(rijen), encoding="utf-8")
    for oud_blad in MAP.glob("lezen-*.html"):
        oud_blad.unlink()
    for i in range(0, len(rijen), 4):     # bladen van vier kaarten: één schermbeeld per blad
        (MAP / f"lezen-{i // 4}.html").write_text(kop + "".join(rijen[i:i + 4]), encoding="utf-8")
    (MAP / "lezen.json").write_text(json.dumps([labelsleutel(p) for p in lijst], ensure_ascii=False, indent=0),
                                    encoding="utf-8")
    print(f"{len(lijst)} bevestigingen te lezen: {MAP / 'lezen.html'}")


def _percentiel(waarden: list[float], q: float) -> float | None:
    from doublecheck.snelantwoord import percentiel

    return percentiel(waarden, q) if waarden else None


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    from doublecheck import beeldcontrole

    vragen, paren, stijl = _stand()
    labels = lees_labels()
    opnieuw = {r["sleutel"]: {k: r[k] for k in ("punten", "dekking", "punten500", "dekking500")}
               for r in _jsonl(MAP / "paren-v2.jsonl") if "punten" in r} or None
    uit = telling(vragen, paren, labels, stijl, {"R3": R3_N, "R2": bm.R2_N}, opnieuw)
    if opnieuw:
        uit["herberekend"] = {"paren": len(opnieuw), "vergelijking": bv.VERGELIJKING,
                              "niet op te halen": sum("punten" not in r for r in _jsonl(MAP / "paren-v2.jsonl"))}
    # bij N: de screenshots die de controle van §188 niet met bewijs waarschuwde
    antwoorden = [r for r in _jsonl(beeldcontrole.UIT / "antwoorden.jsonl") if r["arm"] == "met"]
    oud = beeldcontrole.lees_labels()
    met_bewijs = {r["id"] for r in antwoorden if r["set"] == "N" and (
        (r["kleur"] in beeldcontrole.ALARM and r["eigen_check"]) or oud.get((r["id"], "met")) == "bewijst")}
    nu = gevonden_vragen(vragen, paren, labels, stijl, "N")
    n_ids = {v["id"] for v in vragen if v["set"] == "N"}
    uit["N naast §188"] = {"met bewijs gewaarschuwd in §188": len(met_bewijs & n_ids),
                           "niet met bewijs in §188": len(n_ids - met_bewijs),
                           "daarvan nu bevestigd": len(nu - met_bewijs), "beide": len(nu & met_bewijs)}
    # de tijd per vraag zonder het ophalen: de vraag zelf en het vergelijken met haar artikelbeelden
    vergelijken = collections.Counter()
    for p in paren:
        vergelijken[(p["set"], p["vraag"])] += p["seconden"]
    totaal = [sum(v["seconden"].values()) + vergelijken[(v["set"], v["id"])] for v in vragen]
    stappen = collections.defaultdict(list)
    for v in vragen:
        for k, s in v["seconden"].items():
            stappen[k].append(s)
    uit["tijd"] = {"per vraag p50": _percentiel(totaal, .5), "per vraag p95": _percentiel(totaal, .95),
                   **{f"{k} p50": _percentiel(s, .5) for k, s in stappen.items()},
                   "vergelijken p50": _percentiel(list(vergelijken.values()), .5),
                   "vergelijken p95": _percentiel(list(vergelijken.values()), .95)}
    artikelen = _jsonl(MAP / "artikelen.jsonl")
    bereikbaar = {a["url"] for a in artikelen if a["beelden"]}
    eigen_bereikbaar = collections.Counter()
    for v in vragen:
        if v["set"] in ("N", "R3") and any(k["groep"] in v["groepen"] and k["url"] in bereikbaar
                                           for k in v["kandidaten"]):
            eigen_bereikbaar[v["set"]] += 1
    uit["artikelen"] = {"opgehaald": len(artikelen), "met beelden": len(bereikbaar),
                        "beelden": sum(len(a["beelden"]) for a in artikelen),
                        "status": dict(collections.Counter(str(a["status"]) for a in artikelen).most_common()),
                        "huisstijl": len(stijl),
                        "vragen met de eigen check als kandidaat in een bereikbaar artikel": dict(eigen_bereikbaar),
                        "vragen met de eigen check als kandidaat": dict(collections.Counter(
                            v["set"] for v in vragen if v["set"] in ("N", "R3")
                            and any(k["groep"] in v["groepen"] for k in v["kandidaten"])))}
    uit["kosten"] = {"Haiku": round(sum(v["kosten"] for v in vragen), 2), "Vision zoekvragen": _vision_aantal()}
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def _herbereken(zonder: frozenset = frozenset()) -> None:  # pragma: no cover - netwerk
    """§189, verkennend: elk paar met minstens 20 punten opnieuw vergeleken met de herstelde vergelijking. Elk
    artikelbeeld één keer beleefd opgehaald, alleen in het geheugen; hervatbaar per beeld."""
    import concurrent.futures as cf

    _rekenen()
    pad = MAP / "paren-v2.jsonl"
    klaar = {r["sleutel"] for r in _jsonl(pad)}
    per_beeld = collections.defaultdict(list)
    for p in _jsonl(MAP / "paren.jsonl"):
        if max(p["punten"], p["punten500"]) >= 20 and labelsleutel(p) not in klaar:
            per_beeld[p["beeld"]].append(p)
    per_host = collections.defaultdict(list)
    for adres in per_beeld:
        if bm.host(adres) not in zonder:   # een host die een ander proces op dat moment al vraagt
            per_host[bm.host(adres)].append(adres)
    print(f"{sum(len(v) for v in per_beeld.values())} paren, {len(per_beeld)} beelden op {len(per_host)} hosts",
          flush=True)
    web, rekenen = bm.Beleefd(), threading.Lock()

    def doe(adressen):
        for adres in adressen:
            inhoud, regels = web.beeld(adres), []
            for p in per_beeld[adres]:
                regels.append({"sleutel": labelsleutel(p), "vergelijking": bv.VERGELIJKING})
            if inhoud is not None:
                try:
                    with rekenen:
                        punten = artikelbeeld(inhoud)["punten"]
                        for r, p in zip(regels, per_beeld[adres]):
                            q = lees_punten(MAP, {"set": p["set"], "id": p["vraag"]})
                            n, d = bv.puntvergelijking(q, punten)
                            n5, d5 = bv.puntvergelijking(bv.sterkste(q, STERKSTE), bv.sterkste(punten, STERKSTE))
                            r.update({"punten": n, "dekking": round(d, 4), "punten500": n5,
                                      "dekking500": round(d5, 4)})
                except Exception:   # kapot of geen beeld: zonder punten, nooit loggen (DR3)
                    pass
                del inhoud
            schrijf(pad, regels)

    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {len(_jsonl(pad))} paren herberekend", flush=True)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De woorden zoeken, het beeld bevestigt (PLAN #32.17)")
    parser.add_argument("stap", choices=("set", "vision", "vragen", "vergelijken", "herbereken", "lezen", "tellen",
                                         "opruimen"))
    parser.add_argument("--set", dest="sets", action="append", choices=SETS,
                        help="vragen: alleen deze set (meer keren mag); anders alle, in volgorde")
    parser.add_argument("--proef", type=int, default=0, help="vragen: zoveel per set")
    parser.add_argument("--max", type=int, help="vergelijken: de proef, één artikel per host, zoveel hosts")
    parser.add_argument("--zonder-host", action="append", default=[],
                        help="herbereken: beelden op deze host laten liggen (een ander proces vraagt die host al)")
    args = parser.parse_args()
    if args.stap == "set":
        print(json.dumps(_set(), ensure_ascii=False, indent=1))
    elif args.stap == "vision":
        _vision()
    elif args.stap == "vragen":
        _vragen(args.sets or list(SETS), args.proef)
    elif args.stap == "vergelijken":
        _vergelijken(args.max)
    elif args.stap == "lezen":
        _lezen()
    elif args.stap == "herbereken":
        _herbereken(frozenset(args.zonder_host))
    elif args.stap == "tellen":
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))
    else:
        opruimen(MAP)
        print(f"de punten van de vragen gewist in {MAP / 'punten'}")


if __name__ == "__main__":
    main()
