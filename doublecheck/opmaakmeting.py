"""De opmaak eruit (PLAN #32.22): de 875 bevestigingen die in de vindronde tellen opnieuw vergelijken zonder de
opmaakpunten van de redactie (stempel, balk, logo; `beeldvraag.opmaakmasker`), en 500 paren zonder bevestiging ter
controle. Dezelfde labels, rollen, zoekresultaten en sets als #32.21.

    python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting referentie
    python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting ophalen
    python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting vergelijken
    python -m doublecheck.opmaakmeting lezen|tellen|opruimen
    python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting voormeting ophalen|vergelijken
    python -m doublecheck.opmaakmeting voormeting tellen|opruimen      (#32.23, `opmaak-v2`, de plek)
    python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting rest ophalen|vergelijken
    python -m doublecheck.opmaakmeting rest lezen|tellen|opruimen      (#32.24, `rest-v1`, de rest van de foto)

Beelden alleen in het geheugen (B35); de punten tijdelijk op schijf in `data/opmaak/`, na de telling gewist. Een beeld
dat niet meer te halen is, of op hetzelfde adres een ander beeld geworden is: dat paar is *niet te meten* en telt zoals
in #32.21, apart gemeld.
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from doublecheck import beeldbevestiging as bb
from doublecheck import beeldindexmeting as bm
from doublecheck import beeldvraag as bv
from doublecheck import vindronde as vr
from doublecheck.eigenaanvoer import adres

WORTEL = Path(__file__).resolve().parent.parent
MAP_V1 = WORTEL / "data" / "opmaak"
MAP = MAP_V1                  # de voormeting van #32.23 schrijft naar `MAP_V2`
MAP_V2 = WORTEL / "data" / "opmaakplek"
MAP_REST = WORTEL / "data" / "opmaakrest"     # #32.24, de rest van de foto
LABELS = WORTEL / "docs" / "steekproeven" / "32.22-opmaak.json"
LABELS_V2 = WORTEL / "docs" / "steekproeven" / "32.23-opmaakplek.json"
CONTROLE_N, CONTROLE_ZAAD, CONTROLE_PUNTEN = 500, 3226, 30
BEHOUD_TIENDEN = 9            # per set blijft minstens 90% van de vondsten (eis 2)
MAX_VALS_PER_DUIZEND = 1      # eis 1, zoals eis 4 van #32.21
LEZEN_N = 30
VOOR_LS, VOOR_TERUG, VOOR_N = 90, 39, 25     # de voormeting van #32.23: V1 en V2, vooraf


def site(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _sha(tekst: str) -> str:
    return hashlib.sha1(tekst.encode()).hexdigest()


# --- de referentie ---------------------------------------------------------------------------------------------------

def referentie(pool: list[dict], n: int = bv.OPMAAK_ARTIKELEN, per: int = bv.OPMAAK_BEELDEN) -> dict[str, dict]:
    """Per site de beelden van hoogstens `n` artikelen (op volgorde van de hash van hun adres), per artikel hoogstens
    `per` (het deelbeeld eerst, dan op volgorde van de hash van het beeldadres). Vast, niet gekozen op de labels."""
    per_artikel: dict[str, dict[str, bool]] = collections.defaultdict(dict)
    for b in pool:
        a = adres(b["artikel"])
        per_artikel[a][b["beeld"]] = per_artikel[a].get(b["beeld"], False) or bool(b.get("deel"))
    per_site: dict[str, list[str]] = collections.defaultdict(list)
    for a in per_artikel:
        per_site[site("https://" + a)].append(a)
    uit = {}
    for s, artikelen in per_site.items():
        gekozen = sorted(artikelen, key=_sha)[:n]
        uit[s] = {a: sorted(per_artikel[a], key=lambda b: (not per_artikel[a][b], _sha(b)))[:per] for a in gekozen}
    return uit


def andere_artikelen(artikel: str, ref: dict[str, dict]) -> list[str]:
    """De artikelen van dezelfde site in de referentie, nooit het eigen artikel."""
    eigen = adres(artikel)
    return sorted(a for a in ref.get(site(artikel), {}) if a != eigen)


# --- de telling ------------------------------------------------------------------------------------------------------

def na_regel(paren: list[dict], uitkomst: dict[str, dict]) -> list[dict]:
    """De paren met de punten en dekking zonder opmaak, waar gemeten; een paar dat niet te meten was, blijft zoals het
    was (niet verloren, niet gewonnen)."""
    uit = []
    for p in paren:
        u = uitkomst.get(vr.labelsleutel(p))
        if u and u.get("status") == "gemeten":
            p = {**p, "punten": u["punten"], "dekking": u["dekking"]}
        uit.append(p)
    return uit


def controle(paren: list[dict], n: int = CONTROLE_N, zaad: int = CONTROLE_ZAAD) -> list[dict]:
    """Paren zonder bevestiging met minstens 30 punten: de regel haalt alleen punten weg, dus die horen onbevestigd te
    blijven. Altijd dezelfde, welke volgorde de paren ook hebben."""
    kandidaten = sorted((p for p in paren if not p["uitgesloten"] and p["punten"] >= CONTROLE_PUNTEN
                         and not bb.bevestigd(p)), key=vr.labelsleutel)
    return random.Random(zaad).sample(kandidaten, n) if len(kandidaten) > n else kandidaten


def behoud(n: int) -> int:
    """90% van `n` vondsten, naar boven afgerond op hele claims (in gehele getallen: 0,9 x 40 is geen 36,0000001)."""
    return (BEHOUD_TIENDEN * n + 9) // 10


def _vals_binnen(t: dict, vragen: int) -> bool:
    """Hoogstens 1 vraag met een valse bevestiging per 1.000 vragen, en geen bij W."""
    vals = sum(v.get("vals", 0) for v in t.values() if isinstance(v, dict))
    return vals * 1000 <= MAX_VALS_PER_DUIZEND * vragen and t.get("W", {}).get("vals", 0) == 0


def eisen(voor_p: dict, voor_k: dict, na_p: dict, na_k: dict, vragen: int) -> dict:
    """De eisen zoals vooraf vastgelegd in PLAN #32.22."""
    een = all(_vals_binnen(t, vragen) for t in (na_p, na_k))
    paren = [(voor_p, na_p, "N"), (voor_k, na_k, "N"), (voor_p, na_p, "R3"), (voor_k, na_k, "R3"),
             (voor_k, na_k, "R4"), (voor_k, na_k, "F")]
    twee = all(na.get(s, {}).get("gevonden", 0) >= behoud(voor.get(s, {}).get("gevonden", 0)) for voor, na, s in paren)
    return {"1. vals": een, "2. behoud": twee, "gehaald": een and twee}


def voormeting_paren(paren: list[dict], labels: dict[str, str], rollen: dict, uitkomst_v1: dict[str, dict]) -> list[dict]:
    """De paren die in #32.22 veranderden of vals waren (#32.23): elke valse bevestiging die in #32.21 telt, elke goede
    die `opmaak-v1` kwijtraakte en elke die het erbij gaf."""
    na = {vr.labelsleutel(p): p for p in na_regel(paren, uitkomst_v1)}
    uit = []
    for p in paren:
        k = vr.labelsleutel(p)
        voor, nu = (any(vr._telt(x, rollen, m) for m in vr.MODI) for x in (p, na[k]))
        if (voor and labels.get(k) == vr.VALS) or (voor and not nu and labels.get(k) == vr.GEVONDEN) or (nu and not voor):
            uit.append(p)
    return sorted(uit, key=vr.labelsleutel)


def poorten(ls_weg: int, terug: int, na_p: dict, na_k: dict, vragen: int) -> dict:
    """Wanneer de volle ronde van `opmaak-v2` volgt, zoals vooraf vastgelegd in PLAN #32.23: de valse paren op Lead
    Stories blijven weg, de goede die `opmaak-v1` kwijtraakte komen terug en N haalt 25, en in de verwachting
    hoogstens 1 valse vraag per 1.000."""
    een = ls_weg >= VOOR_LS
    twee = terug >= VOOR_TERUG and all(t.get("N", {}).get("gevonden", 0) >= VOOR_N for t in (na_p, na_k))
    drie = all(_vals_binnen(t, vragen) for t in (na_p, na_k))
    return {"V1. Lead Stories": een, "V2. behoud": twee, "V3. vals": drie, "volle ronde": een and twee and drie}


def rest_paren(paren: list[dict], labels: dict[str, str], rollen: dict, uitkomst_v1: dict[str, dict]) -> list[dict]:
    """De voormeting van #32.24: de 163 paren van #32.23 en alle andere goede bevestigingen die in #32.21 tellen, want
    de restcontrole kan elke bevestiging afkeuren."""
    gekozen = {vr.labelsleutel(p): p for p in voormeting_paren(paren, labels, rollen, uitkomst_v1)}
    for p in paren:
        if labels.get(vr.labelsleutel(p)) == vr.GEVONDEN and any(vr._telt(p, rollen, m) for m in vr.MODI):
            gekozen.setdefault(vr.labelsleutel(p), p)
    return [gekozen[k] for k in sorted(gekozen)]


def na_rest(paren: list[dict], uitkomst: dict[str, dict]) -> list[dict]:
    """De paren na `opmaak-v2` en de restcontrole: een bevestiging op punten waarvan de rest niet past, valt weg; een
    bevestiging op PDQ wordt niet gecontroleerd; niet te meten blijft zoals het was."""
    uit = []
    for p in na_regel(paren, uitkomst):
        u = uitkomst.get(vr.labelsleutel(p))
        if u and u.get("status") == "gemeten" and u.get("rest") is False:
            p = {**p, "punten": 0, "dekking": 0.0}
        uit.append(p)
    return uit


def restpoorten(voor_p: dict, voor_k: dict, na_p: dict, na_k: dict, vragen: int) -> dict:
    """Wanneer de volle ronde van de restcontrole volgt, zoals vooraf vastgelegd in PLAN #32.24: R1 hoogstens 1 valse
    vraag per 1.000 en W 0, R2 per set 90% van de vondsten van #32.21."""
    e = eisen(voor_p, voor_k, na_p, na_k, vragen)
    return {"R1. vals": e["1. vals"], "R2. behoud": e["2. behoud"], "volle ronde": e["gehaald"]}


def schrijf(pad: Path, rijen: list[dict]) -> None:
    """Regels erbij in een jsonl-bestand; nooit een beeld en nooit de gelezen tekst van een kopie (B35, DR3)."""
    for r in rijen:
        if "tekst" in r or any(isinstance(v, (bytes, bytearray)) for v in r.values()):
            raise ValueError("een beeld of gelezen tekst hoort niet op schijf")
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as fh:
        for r in rijen:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def lees_labels() -> dict[str, str]:
    """De labels van #32.21 (en eerder) voor hetzelfde paar, met die van #32.22 en #32.23 voor wat een regel erbij
    geeft."""
    uit = vr._paarlabels(vr.lees_labels())
    for pad in (LABELS, LABELS_V2):
        eigen = json.loads(pad.read_text(encoding="utf-8")).get("labels", {}) if pad.exists() else {}
        fout = {k: v for k, v in eigen.items() if v not in vr.LABELWAARDEN}
        if fout:
            raise vr.Weigering(f"onbekende labels in {pad.name}: {list(fout.items())[:3]}")
        uit.update(eigen)
    return uit


# --- op de bestanden en het net ----------------------------------------------------------------------------------------

def _beeldpad(url: str) -> Path:
    return MAP / "punten" / "beelden" / (_sha(url)[:24] + ".npz")


def _vraagpad(set_: str, id_: str) -> Path:
    return MAP / "punten" / "vragen" / set_ / (_sha(id_)[:24] + ".npz")


def _maskerpad(url: str) -> Path:
    return MAP / "maskers" / (_sha(url)[:24] + ".npy")


def _doelen():  # pragma: no cover - op de bestanden van #32.21
    vragen, paren, rollen, _ = vr._stand()
    telt = [p for p in paren if any(vr._telt(p, rollen, m) for m in vr.MODI)]
    gezien = {vr.labelsleutel(p) for p in telt}
    doelen = telt + [p for p in controle(paren) if vr.labelsleutel(p) not in gezien]
    return vragen, paren, rollen, doelen


def _voordoelen():  # pragma: no cover - op de bestanden van #32.21 en #32.22
    vragen, paren, rollen, _ = vr._stand()
    v1 = {r["sleutel"]: r for r in vr._jsonl(MAP_V1 / "uitkomst.jsonl")}
    return vragen, paren, rollen, voormeting_paren(paren, lees_labels(), rollen, v1)


def _restdoelen():  # pragma: no cover - op de bestanden van #32.21 en #32.22
    vragen, paren, rollen, _ = vr._stand()
    v1 = {r["sleutel"]: r for r in vr._jsonl(MAP_V1 / "uitkomst.jsonl")}
    return vragen, paren, rollen, rest_paren(paren, lees_labels(), rollen, v1)


def _kies(soort: str):  # pragma: no cover
    return {"vol": _doelen, "voormeting": _voordoelen, "rest": _restdoelen}[soort]()


def _referentie(doelen=None) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    import cv2

    cv2.setNumThreads(2)    # hoogstens twee kernen (PO)
    if doelen is None:
        _, _, _, doelen = _doelen()
    pool = vr._jsonl(vr.MAP / "pool-beelden.jsonl")
    pdq = {b["beeld"]: b["pdq"][0] for b in pool}
    sites = {site(p["artikel"]) for p in doelen}
    ref = {s: a for s, a in referentie(pool).items() if s in sites}
    nodig = {b for artikelen in ref.values() for beelden in artikelen.values() for b in beelden}
    nodig |= {p["beeld"] for p in doelen}
    _haal_beelden(sorted(nodig), pdq, cf, "referentie en artikelbeelden")
    (MAP / "referentie.json").write_text(json.dumps(ref, ensure_ascii=False, indent=0), encoding="utf-8")


def _haal_beelden(urls, pdq, cf, wat) -> None:  # pragma: no cover - netwerk
    log = MAP / "beelden.jsonl"
    klaar = {r["beeld"] for r in vr._jsonl(log)} if log.exists() else set()
    per_host = collections.defaultdict(list)
    for u in urls:
        if u not in klaar:
            per_host[bm.host(u)].append(u)
    print(f"{wat}: {sum(map(len, per_host.values()))} beelden op {len(per_host)} hosts ({len(klaar)} al gedaan)",
          flush=True)
    web, rekenen, slot, teller = bm.Beleefd(), threading.Lock(), threading.Lock(), collections.Counter()

    def doe(lijst):
        for u in lijst:
            inhoud, status = web.beeld(u), "gemeten"
            if inhoud is None:
                status = "niet opgehaald"
            else:
                try:
                    with rekenen:
                        kenm = bb.artikelbeeld(inhoud)
                    if u in pdq and bb._afstand(kenm["pdq"][0], pdq[u]) > bb.DREMPEL_PDQ:
                        status = "ander beeld"
                    else:
                        _beeldpad(u).parent.mkdir(parents=True, exist_ok=True)
                        _beeldpad(u).write_bytes(bv.punten_naar_bytes(kenm["punten"]))
                except Exception as e:   # kapot of geen beeld; alleen de soort fout (DR3)
                    status = f"fout {type(e).__name__}"
            del inhoud
            schrijf(log, [{"beeld": u, "status": status}])
            with slot:
                teller[status] += 1
                if sum(teller.values()) % 250 == 0:
                    print(f"  {dict(teller)}", flush=True)

    with cf.ThreadPoolExecutor(12) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {dict(teller)}", flush=True)


def _ophalen(soort: str = "vol") -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    import cv2

    cv2.setNumThreads(2)
    vragen, _, _, doelen = _kies(soort)
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    nodig = sorted({(p["set"], p["vraag"]) for p in doelen})
    log = MAP / "vragen.jsonl"
    klaar = {(r["set"], r["id"]) for r in vr._jsonl(log)} if log.exists() else set()
    werk = [per_vraag[k] for k in nodig if k not in klaar]
    print(f"{len(werk)} vraagbeelden ({len(klaar)} al gedaan)", flush=True)
    web, rekenen, sjablonen = bm.Beleefd(), threading.Lock(), {}

    def beeld_van(w) -> bytes | None:
        return _vraagbeeld(w, web, sjablonen)

    def doe(lijst):
        for w in lijst:
            beeld, status = beeld_van(w), "gemeten"
            if beeld is None:
                status = "niet opgehaald"
            else:
                try:
                    with rekenen:
                        kenm, punten = bb._vraagkenmerken(beeld)
                    if bb._afstand(kenm["pdq"][0], w["pdq"][0]) > bb.DREMPEL_PDQ:
                        status = "ander beeld"
                    else:
                        _vraagpad(w["set"], w["id"]).parent.mkdir(parents=True, exist_ok=True)
                        _vraagpad(w["set"], w["id"]).write_bytes(bv.punten_naar_bytes(punten))
                except Exception as e:   # kapot of geen beeld; alleen de soort fout (DR3)
                    status = f"fout {type(e).__name__}"
            del beeld
            schrijf(log, [{"set": w["set"], "id": w["id"], "status": status}])

    per_host = collections.defaultdict(list)
    for w in werk:
        per_host["lokaal" if w["set"] in ("N", "W") else bm.host((w.get("adressen") or [""])[0] or "x")].append(w)
    with cf.ThreadPoolExecutor(12) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {collections.Counter(r['status'] for r in vr._jsonl(log))}", flush=True)


def _vraagbeeld(w, web, sjablonen) -> bytes | None:  # pragma: no cover - netwerk; zoals `vindronde._vragen`
    if w["set"] in ("N", "W"):
        pad = Path(w["beeld"])
        return pad.read_bytes() if pad.exists() else None
    if w["set"] == "S4":
        if w["vraag"] not in sjablonen:
            sjablonen[w["vraag"]] = next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)
        return bb._meme(sjablonen[w["vraag"]], w["onderschrift"]) if sjablonen[w["vraag"]] else None
    return next((b for a in w["adressen"] if (b := web.beeld(a)) is not None), None)


def _vraaggrijs(beeld: bytes) -> tuple[np.ndarray, list | None]:  # pragma: no cover - zoals `bb._vraagkenmerken`
    from doublecheck.beelduitsnede import beeldgebied

    b = bv._open(beeld)
    gebied = beeldgebied(b)
    deel = b.crop(gebied) if gebied else b
    vak = [round(gebied[0] / b.width, 4), round(gebied[1] / b.height, 4), round(gebied[2] / b.width, 4),
           round(gebied[3] / b.height, 4)] if gebied else None
    return bv.grijs_voor_punten(deel), vak


def _restvergelijken() -> None:  # pragma: no cover - op de bestanden en het net
    """`opmaak-v2` en daarna de restcontrole (#32.24). De beelden alleen in het geheugen: per paar opnieuw beleefd
    opgehaald (per host één verzoek), na het paar weg; op schijf alleen de getallen."""
    import concurrent.futures as cf
    import functools

    import cv2

    cv2.setNumThreads(2)
    vragen, _, _, doelen = _restdoelen()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    ref = json.loads((MAP / "referentie.json").read_text(encoding="utf-8"))
    beeldstatus = {r["beeld"]: r["status"] for r in vr._jsonl(MAP / "beelden.jsonl")}
    vraagstatus = {(r["set"], r["id"]): r["status"] for r in vr._jsonl(MAP / "vragen.jsonl")}
    rekenen, slot = threading.Lock(), threading.Lock()

    @functools.lru_cache(maxsize=8192)
    def punten(url):
        return bv.punten_uit_bytes(_beeldpad(url).read_bytes()) if beeldstatus.get(url) == "gemeten" else None

    @functools.lru_cache(maxsize=4096)
    def masker(artikel, url):
        andere = [[k for b in ref[site(artikel)][a] if (k := punten(b)) is not None]
                  for a in andere_artikelen(artikel, ref)]
        return bv.opmaakmasker(punten(url), [a for a in andere if a], plek=bv.OPMAAK_PLEK)

    pad = MAP / "uitkomst.jsonl"
    pad.unlink(missing_ok=True)
    begin, nodig = time.monotonic(), []
    for p in doelen:
        regel = {"sleutel": vr.labelsleutel(p), "site": site(p["artikel"]), "voor": [p["punten"], p["dekking"]]}
        vraag = (p["set"], p["vraag"])
        if vraagstatus.get(vraag) != "gemeten" or punten(p["beeld"]) is None:
            schrijf(pad, [{**regel, "status": "niet te meten", "waarom": "punten"}])
            continue
        m = masker(p["artikel"], p["beeld"])
        artikelpunten = punten(p["beeld"])
        vp = bv.punten_uit_bytes(_vraagpad(*vraag).read_bytes())
        n, dekking, vorm = bv.puntvorm(vp, bv.zonder_punten(artikelpunten, m))
        regel.update({"status": "gemeten", "punten": n, "dekking": round(dekking, 4), "opmaak": int(m.sum())})
        if p["pdq"] is not None and p["pdq"] <= bb.DREMPEL_PDQ:
            schrijf(pad, [{**regel, "rest": "pdq"}])
        elif n >= bb.MIN_PUNTEN and dekking >= bb.MIN_DEKKING and vorm is not None:
            nodig.append((p, regel, vorm, artikelpunten["xy"][m], tuple(artikelpunten["maat"]), tuple(vp["maat"])))
        else:
            schrijf(pad, [{**regel, "rest": None}])
    print(f"vergeleken in {time.monotonic() - begin:.0f} s; restcontrole bij {len(nodig)} paren", flush=True)

    web, sjablonen, vraaggrijs = bm.Beleefd(), {}, {}

    def grijs_vraag(p):
        k = (p["set"], p["vraag"])
        with slot:
            if k in vraaggrijs:
                return vraaggrijs[k]
        beeld = _vraagbeeld(per_vraag[k], web, sjablonen)
        uit = None
        if beeld is not None:
            with rekenen:
                uit = _vraaggrijs(beeld)
        del beeld
        with slot:
            vraaggrijs[k] = uit
        return uit

    def doe(lijst):
        artikelgrijs = {}
        for p, regel, vorm, opmaak_xy, amaat, vmaat in lijst:
            t0 = time.perf_counter()
            if p["beeld"] not in artikelgrijs:
                inhoud = web.beeld(p["beeld"])
                with rekenen:
                    artikelgrijs[p["beeld"]] = None if inhoud is None else bv.grijs_voor_punten(bv._open(inhoud))
                del inhoud
            a, v = artikelgrijs[p["beeld"]], grijs_vraag(p)
            if a is None or v is None or a.shape[::-1] != amaat or v[0].shape[::-1] != vmaat:
                uit = {**regel, "status": "niet te meten", "waarom": "rest: beeld niet opgehaald of andere maat"}
            else:
                with rekenen:
                    r = bv.restcontrole(v[0], a, vorm, opmaak_xy=opmaak_xy)
                uit = {**regel, "rest": bool(r["goed"]), "vakken": r["vakken"], "kloppen": r["kloppen"],
                       "kaart": r["kaart"], "gebied": v[1], "seconden_rest": round(time.perf_counter() - t0, 3)}
            with slot:
                schrijf(pad, [uit])

    per_host = collections.defaultdict(list)
    for x in nodig:
        per_host[bm.host(x[0]["beeld"])].append(x)
    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    print(f"klaar: {len(doelen)} paren in {time.monotonic() - begin:.0f} s", flush=True)


def _resttellen() -> dict:  # pragma: no cover - op de bestanden
    """De voormeting van #32.24: `opmaak-v2` en de restcontrole op de 863 paren; de rest zoals in #32.21."""
    vragen, paren, rollen, doelen = _restdoelen()
    labels, uitkomst = lees_labels(), _uitkomst()
    ontbreekt = [vr.labelsleutel(p) for p in doelen if vr.labelsleutel(p) not in uitkomst]
    if ontbreekt:
        raise vr.Weigering(f"{len(ontbreekt)} paren nog niet vergeleken")
    na_lijst = na_rest(paren, uitkomst)
    na = {vr.labelsleutel(p): p for p in na_lijst}
    voor_t = {m: vr.telling(vragen, paren, labels, rollen, m) for m in vr.MODI}
    na_t = {m: vr.telling(vragen, na_lijst, labels, rollen, m) for m in vr.MODI}

    def telt(p):
        return any(vr._telt(p, rollen, m) for m in vr.MODI)

    groepen, verhouding = collections.Counter(), collections.defaultdict(list)
    for p in doelen:
        k, lab, u = vr.labelsleutel(p), labels.get(vr.labelsleutel(p)), uitkomst[vr.labelsleutel(p)]
        voor, nu = telt(p), telt(na[k])
        soort = {vr.VALS: "vals", vr.GEVONDEN: "goed", vr.ANDERE: "andere bewering"}.get(lab, "zonder label")
        if voor:
            groepen[f"{soort} {p['set'] if soort == 'goed' else site(p['artikel'])}: {'blijft' if nu else 'weg'}"] += 1
        elif nu:
            groepen[f"erbij ({soort})"] += 1
        if u.get("vakken"):
            verhouding[soort].append(round(u["kloppen"] / u["vakken"], 2))
        groepen[f"rest {u.get('rest')}"] += 1
    tijden = sorted(u["seconden_rest"] for u in uitkomst.values() if u.get("seconden_rest") is not None)
    uit = {
        "groepen": dict(sorted(groepen.items())),
        "na": na_t,
        "poorten": restpoorten(voor_t["productie"], voor_t["kopie"], na_t["productie"], na_t["kopie"], len(vragen)),
        "kloppend deel van de vakken (p10, p50, p90)": {
            s: [float(np.percentile(v, q)) for q in (10, 50, 90)] for s, v in verhouding.items() if v},
        "seconden per restcontrole": {"p50": tijden[len(tijden) // 2], "p95": tijden[int(len(tijden) * 0.95)]}
        if tijden else {},
        "niet te meten": dict(collections.Counter(u.get("waarom") for u in uitkomst.values()
                                                  if u["status"] == "niet te meten")),
        "doelen": len(doelen), "vragen": len(vragen), "versie": [bv.REST, bv.OPMAAK_V2, bv.VERGELIJKING, bv.PUNTVERSIE],
    }
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


RESTPAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Rest lezen</title><style>body{font:13px system-ui,sans-serif;margin:8px;background:#f4f6f8;color:#15202b}
.k{background:#fff;border:1px solid #ccd;border-radius:8px;padding:8px;margin:8px 0}.r{display:flex;gap:8px;flex-wrap:wrap;
align-items:flex-start}.f{position:relative;width:420px}.f img{width:100%;display:block}.f .g{position:absolute;display:grid;
grid-template-columns:repeat(8,1fr);grid-template-rows:repeat(8,1fr)}.g div{border:1px solid rgba(0,0,0,.15)}
.p{background:rgba(0,170,0,.35)}.m{background:rgba(220,0,0,.35)}</style><h1>Rest lezen</h1><div id=k></div><script>
const DATA = __DATA__;
function el(t, a, ...k) { const e = document.createElement(t); for (const [x, y] of Object.entries(a || {})) e.setAttribute(x, y);
  for (const c of k) e.append(c); return e; }
DATA.forEach((d, i) => {
  const f = el("div", {class: "f"}, el("img", {src: d.vraag, referrerpolicy: "no-referrer"}));
  const [l, t, r, o] = d.gebied || [0, 0, 1, 1];
  const g = el("div", {class: "g", style: `left:${l * 100}%;top:${t * 100}%;width:${(r - l) * 100}%;height:${(o - t) * 100}%`});
  for (const c of d.kaart) g.append(el("div", {class: c === "+" ? "p" : c === "-" ? "m" : ""}));
  f.append(g);
  document.getElementById("k").append(el("div", {class: "k"}, el("b", {}, `#${i} ${d.soort} · ${d.sleutel}`),
    el("div", {}, `punten ${d.punten} (${d.dekking}); vakken ${d.kloppen} van ${d.vakken} kloppen`),
    el("div", {class: "r"}, f, el("div", {class: "f"}, el("img", {src: d.beeld, referrerpolicy: "no-referrer"})))));
});
</script>"""


def _restlezen() -> None:  # pragma: no cover - op de bestanden
    vragen, paren, rollen, doelen = _restdoelen()
    labels, uitkomst = lees_labels(), _uitkomst()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    na = {vr.labelsleutel(p): p for p in na_rest(paren, uitkomst)}
    kaarten = collections.defaultdict(list)
    for p in doelen:
        k, lab, u = vr.labelsleutel(p), labels.get(vr.labelsleutel(p)), uitkomst[vr.labelsleutel(p)]
        voor, nu = (any(vr._telt(x, rollen, m) for m in vr.MODI) for x in (p, na[k]))
        if not u.get("kaart") or not voor:
            continue
        soort = ("vals blijft" if nu else "vals weg") if lab == vr.VALS else ("goed weg" if lab == vr.GEVONDEN and not nu
                                                                              else None)
        if soort:
            v = per_vraag[(p["set"], p["vraag"])]
            kaarten[soort].append({"soort": soort, "sleutel": k, "vraag": v.get("vraag") or (v.get("adressen") or [""])[0],
                                   "beeld": p["beeld"], "punten": u["punten"], "dekking": u["dekking"],
                                   "vakken": u["vakken"], "kloppen": u["kloppen"], "kaart": u["kaart"],
                                   "gebied": u.get("gebied")})
    lijst = kaarten["vals blijft"] + kaarten["vals weg"][:10] + kaarten["goed weg"][:LEZEN_N]
    data = json.dumps(lijst, ensure_ascii=False).replace("</", "<\\/")
    (MAP / "lezen.html").write_text(RESTPAGINA.replace("__DATA__", data), encoding="utf-8")
    print({s: len(v) for s, v in kaarten.items()}, f"{len(lijst)} kaarten op {MAP / 'lezen.html'}")


def _vergelijken(voormeting: bool = False) -> None:  # pragma: no cover - op de bestanden
    """Zonder de opmaak vergelijken; in de voormeting van #32.23 met `opmaak-v2` (de plek) en ter controle opnieuw met
    `opmaak-v1`, die dezelfde uitkomst moet geven als in #32.22."""
    import functools

    import cv2

    cv2.setNumThreads(2)
    _, _, _, doelen = _voordoelen() if voormeting else _doelen()
    plek = bv.OPMAAK_PLEK if voormeting else None
    ref = json.loads((MAP / "referentie.json").read_text(encoding="utf-8"))
    beeldstatus = {r["beeld"]: r["status"] for r in vr._jsonl(MAP / "beelden.jsonl")}
    vraagstatus = {(r["set"], r["id"]): r["status"] for r in vr._jsonl(MAP / "vragen.jsonl")}

    @functools.lru_cache(maxsize=8192)
    def punten(url):
        return bv.punten_uit_bytes(_beeldpad(url).read_bytes()) if beeldstatus.get(url) == "gemeten" else None

    maskers: dict[tuple, tuple[np.ndarray, int, float]] = {}

    def masker(artikel, url, plek_=plek):
        sleutel = (adres(artikel), url, plek_)
        if sleutel not in maskers:
            begin = time.perf_counter()
            andere = [[k for b in ref[site(artikel)][a] if (k := punten(b)) is not None]
                      for a in andere_artikelen(artikel, ref)]
            andere = [a for a in andere if a]
            m = bv.opmaakmasker(punten(url), andere, plek=plek_)
            if plek_ == plek:
                np.save(_maak(_maskerpad(url)), m)
            maskers[sleutel] = (m, len(andere), time.perf_counter() - begin)
        return maskers[sleutel]

    pad = MAP / "uitkomst.jsonl"
    pad.unlink(missing_ok=True)
    begin = time.monotonic()
    for i, p in enumerate(doelen, 1):
        regel = {"sleutel": vr.labelsleutel(p), "site": site(p["artikel"]), "voor": [p["punten"], p["dekking"]]}
        vraag = (p["set"], p["vraag"])
        if vraagstatus.get(vraag) != "gemeten" or punten(p["beeld"]) is None:
            regel["status"] = "niet te meten"
            regel["waarom"] = vraagstatus.get(vraag, "-") if vraagstatus.get(vraag) != "gemeten" \
                else beeldstatus.get(p["beeld"], "-")
        else:
            m, n_andere, sec = masker(p["artikel"], p["beeld"])
            vp = bv.punten_uit_bytes(_vraagpad(*vraag).read_bytes())
            n, dekking = bv.puntvergelijking(vp, bv.zonder_punten(punten(p["beeld"]), m))
            regel.update({"status": "gemeten", "punten": n, "dekking": round(dekking, 4), "opmaak": int(m.sum()),
                          "totaal": len(m), "andere": n_andere, "seconden_masker": round(sec, 3)})
            if voormeting:   # de controle: opmaak-v1 op dezelfde beelden
                m1 = masker(p["artikel"], p["beeld"], None)[0]
                n1, d1 = bv.puntvergelijking(vp, bv.zonder_punten(punten(p["beeld"]), m1))
                regel["v1"] = [n1, round(d1, 4), int(m1.sum())]
        schrijf(pad, [regel])
        if i % 100 == 0:
            print(f"  {i}/{len(doelen)} in {time.monotonic() - begin:.0f} s", flush=True)
    print(f"klaar: {len(doelen)} paren in {time.monotonic() - begin:.0f} s", flush=True)


def _maak(pad: Path) -> Path:  # pragma: no cover
    pad.parent.mkdir(parents=True, exist_ok=True)
    return pad


def _uitkomst() -> dict[str, dict]:  # pragma: no cover - op de bestanden
    return {r["sleutel"]: r for r in vr._jsonl(MAP / "uitkomst.jsonl")}


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    vragen, paren, rollen, doelen = _doelen()
    labels, uitkomst = lees_labels(), _uitkomst()
    ontbreekt = [vr.labelsleutel(p) for p in doelen if vr.labelsleutel(p) not in uitkomst]
    if ontbreekt:
        raise vr.Weigering(f"{len(ontbreekt)} paren nog niet vergeleken")
    na = na_regel(paren, uitkomst)
    voor_t = {m: vr.telling(vragen, paren, labels, rollen, m) for m in vr.MODI}
    na_t = {m: vr.telling(vragen, na, labels, rollen, m) for m in vr.MODI}
    voor_telt = {vr.labelsleutel(p) for p in paren if any(vr._telt(p, rollen, m) for m in vr.MODI)}
    na_telt = {vr.labelsleutel(p) for p in na if any(vr._telt(p, rollen, m) for m in vr.MODI)}
    soort = collections.Counter()
    for k in voor_telt - na_telt:
        soort[f"weg: {labels.get(k)}"] += 1
    for k in na_telt - voor_telt:
        soort[f"erbij: {labels.get(k)}"] += 1
    gemeten = [u for u in uitkomst.values() if u["status"] == "gemeten"]
    per_site = collections.defaultdict(lambda: [0, 0])
    seen = set()
    for u in gemeten:
        beeld = u["sleutel"].split("|", 2)[2]
        if beeld in seen:
            continue
        seen.add(beeld)
        per_site[u["site"]][0] += u["opmaak"]
        per_site[u["site"]][1] += u["totaal"]
    tijden = sorted(u["seconden_masker"] for u in gemeten)
    uit = {
        "voor": voor_t, "na": na_t,
        "eisen": eisen(voor_t["productie"], voor_t["kopie"], na_t["productie"], na_t["kopie"], len(vragen)),
        "veranderd": dict(soort),
        "niet te meten": dict(collections.Counter(u.get("waarom") for u in uitkomst.values()
                                                  if u["status"] == "niet te meten")),
        "opmaak per site": {s: round(a / t, 3) for s, (a, t) in sorted(per_site.items(), key=lambda x: -x[1][1]) if t},
        "seconden per artikelbeeld": {"p50": tijden[len(tijden) // 2], "p95": tijden[int(len(tijden) * 0.95)]}
        if tijden else {},
        "vragen": len(vragen), "doelen": len(doelen), "versie": [bv.OPMAAK, bv.VERGELIJKING, bv.PUNTVERSIE],
    }
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


LEESPAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Opmaak lezen</title><style>body{font:13px system-ui,sans-serif;margin:8px;background:#f4f6f8;color:#15202b}
.k{background:#fff;border:1px solid #ccd;border-radius:8px;padding:8px;margin:8px 0}.r{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start}
.f{position:relative;width:440px}.f img{width:100%;display:block}.f svg{position:absolute;inset:0;width:100%;height:100%}
</style><h1>Opmaak lezen</h1><div id=k></div><script>
const DATA = __DATA__;
function el(t, a, ...k) { const e = document.createElement(t); for (const [x, y] of Object.entries(a || {})) e.setAttribute(x, y);
  for (const c of k) e.append(c); return e; }
const NS = "http://www.w3.org/2000/svg";
DATA.forEach((d, i) => {
  const f = el("div", {class: "f"}, el("img", {src: d.beeld, referrerpolicy: "no-referrer"}));
  const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "0 0 1 1"); svg.setAttribute("preserveAspectRatio", "none");
  for (const [x, y, weg] of d.punten) { const c = document.createElementNS(NS, "circle"); c.setAttribute("cx", x); c.setAttribute("cy", y);
    c.setAttribute("r", 0.006); c.setAttribute("fill", weg ? "#d00" : "#0a0"); c.setAttribute("opacity", 0.7); svg.append(c); }
  f.append(svg);
  const v = el("div", {class: "f"}, el("img", {src: d.vraag, referrerpolicy: "no-referrer"}));
  document.getElementById("k").append(el("div", {class: "k"}, el("b", {}, `#${i} ${d.soort} · ${d.sleutel}`),
    el("div", {}, `voor ${d.voor[0]} punten (${d.voor[1]}), na ${d.na[0]} (${d.na[1]}); opmaak ${d.opmaak} van ${d.totaal}`),
    el("div", {class: "r"}, v, f)));
});
</script>"""


def _lezen() -> None:  # pragma: no cover - op de bestanden
    vragen, paren, rollen, doelen = _doelen()
    labels, uitkomst = lees_labels(), _uitkomst()
    per_vraag = {(v["set"], v["id"]): v for v in vragen}
    na = {vr.labelsleutel(p): p for p in na_regel(paren, uitkomst)}
    kaarten, open_ = [], []
    for p in doelen:
        k = vr.labelsleutel(p)
        voor, nu = any(vr._telt(p, rollen, m) for m in vr.MODI), any(vr._telt(na[k], rollen, m) for m in vr.MODI)
        if nu and not voor and k not in labels:
            open_.append(k)
            soort = "nieuw, zonder label"
        elif voor and not nu and labels.get(k) == vr.GEVONDEN:
            soort = "verloren goed"
        else:
            continue
        u = uitkomst[k]
        pt = bv.punten_uit_bytes(_beeldpad(p["beeld"]).read_bytes())
        m = np.load(_maskerpad(p["beeld"]))
        b, h = pt["maat"]
        v = per_vraag[(p["set"], p["vraag"])]
        kaarten.append({"soort": soort, "sleutel": k, "beeld": p["beeld"], "vraag": v.get("vraag") or
                        (v.get("adressen") or [""])[0], "voor": u["voor"], "na": [u["punten"], u["dekking"]],
                        "opmaak": u["opmaak"], "totaal": u["totaal"],
                        "punten": [[round(float(x) / b, 4), round(float(y) / h, 4), bool(w)]
                                   for (x, y), w in zip(pt["xy"], m)]})
    kaarten = [k for k in kaarten if k["soort"] != "verloren goed"] + \
        [k for k in kaarten if k["soort"] == "verloren goed"][:LEZEN_N]
    data = json.dumps(kaarten, ensure_ascii=False).replace("</", "<\\/")
    (MAP / "lezen.html").write_text(LEESPAGINA.replace("__DATA__", data), encoding="utf-8")
    print(f"{len(open_)} nieuwe bevestigingen zonder label; {len(kaarten)} kaarten op {MAP / 'lezen.html'}")


def _voortellen() -> dict:  # pragma: no cover - op de bestanden
    """De voormeting van #32.23: `opmaak-v2` op de 163 paren, de rest zoals in #32.21 (een verwachting)."""
    vragen, paren, rollen, doelen = _voordoelen()
    labels, v2 = lees_labels(), _uitkomst()
    v1 = {r["sleutel"]: r for r in vr._jsonl(MAP_V1 / "uitkomst.jsonl")}
    ontbreekt = [vr.labelsleutel(p) for p in doelen if vr.labelsleutel(p) not in v2]
    if ontbreekt:
        raise vr.Weigering(f"{len(ontbreekt)} paren nog niet vergeleken")
    na1 = {vr.labelsleutel(p): p for p in na_regel(paren, v1)}
    na2_lijst = na_regel(paren, v2)
    na2 = {vr.labelsleutel(p): p for p in na2_lijst}
    na_t = {m: vr.telling(vragen, na2_lijst, labels, rollen, m) for m in vr.MODI}

    def telt(p):
        return any(vr._telt(p, rollen, m) for m in vr.MODI)

    groepen = collections.Counter()
    for p in doelen:
        k, lab = vr.labelsleutel(p), labels.get(vr.labelsleutel(p))
        voor, met1, met2 = telt(p), telt(na1[k]), telt(na2[k])
        if voor and lab == vr.VALS:
            groepen[f"vals {site(p['artikel'])}: {'blijft' if met2 else 'weg'}"] += 1
        elif voor and not met1 and lab == vr.GEVONDEN:
            groepen[f"verloren met v1: {'terug' if met2 else 'nog weg'}"] += 1
        elif met1 and not voor:
            groepen[f"erbij met v1 ({lab}): {'blijft erbij' if met2 else 'niet meer'}"] += 1
        if met2 and not voor and not met1:
            groepen[f"nieuw met v2 ({lab})"] += 1
    gemeten = [u for u in v2.values() if u["status"] == "gemeten"]
    gelijk = sum(u["v1"][:2] == [v1[u["sleutel"]]["punten"], v1[u["sleutel"]]["dekking"]]
                 for u in gemeten if u.get("v1") and v1.get(u["sleutel"], {}).get("status") == "gemeten")
    uit = {
        "groepen": dict(sorted(groepen.items())),
        "na (verwachting)": na_t,
        "poorten": poorten(groepen["vals leadstories.com: weg"], groepen["verloren met v1: terug"], na_t["productie"],
                           na_t["kopie"], len(vragen)),
        "opmaak-v1 opnieuw gelijk aan #32.22": f"{gelijk} van {len(gemeten)}",
        "opmaakpunten per paar (v2 tegen v1, mediaan)": [
            float(np.median([u["opmaak"] for u in gemeten])), float(np.median([u["v1"][2] for u in gemeten]))]
        if gemeten else None,
        "niet te meten": dict(collections.Counter(u.get("waarom") for u in v2.values() if u["status"] == "niet te meten")),
        "doelen": len(doelen), "vragen": len(vragen), "versie": [bv.OPMAAK_V2, bv.VERGELIJKING, bv.PUNTVERSIE],
    }
    (MAP / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def _opruimen() -> None:  # pragma: no cover - op de bestanden
    for d in (MAP / "punten", MAP / "maskers"):
        shutil.rmtree(d, ignore_errors=True)
    print("punten en maskers gewist")


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    import argparse

    global MAP
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stap", choices=["referentie", "ophalen", "vergelijken", "lezen", "tellen", "opruimen",
                                    "voormeting", "rest"])
    p.add_argument("deel", nargs="?", choices=["ophalen", "vergelijken", "lezen", "tellen", "opruimen"],
                   help="bij `voormeting` (#32.23) en `rest` (#32.24)")
    a = p.parse_args(argv)
    if a.stap == "rest":
        MAP = MAP_REST
        MAP.mkdir(parents=True, exist_ok=True)
        if a.deel == "ophalen":
            _referentie(_restdoelen()[3])
            _ophalen("rest")
        elif a.deel == "vergelijken":
            _restvergelijken()
        elif a.deel == "lezen":
            _restlezen()
        elif a.deel == "tellen":
            print(json.dumps(_resttellen(), ensure_ascii=False, indent=1))
        elif a.deel == "opruimen":
            _opruimen()
        else:
            p.error("rest ophalen|vergelijken|lezen|tellen|opruimen")
        return
    if a.stap == "voormeting":
        MAP = MAP_V2
        MAP.mkdir(parents=True, exist_ok=True)
        if a.deel == "ophalen":
            _referentie(_voordoelen()[3])
            _ophalen("voormeting")
        elif a.deel == "vergelijken":
            _vergelijken(voormeting=True)
        elif a.deel == "tellen":
            print(json.dumps(_voortellen(), ensure_ascii=False, indent=1))
        elif a.deel == "opruimen":
            _opruimen()
        else:
            p.error("voormeting ophalen|vergelijken|tellen|opruimen")
        return
    MAP.mkdir(parents=True, exist_ok=True)
    if a.stap == "referentie":
        _referentie()
    elif a.stap == "ophalen":
        _ophalen()
    elif a.stap == "vergelijken":
        _vergelijken()
    elif a.stap == "lezen":
        _lezen()
    elif a.stap == "tellen":
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))
    else:
        _opruimen()


if __name__ == "__main__":  # pragma: no cover
    main()
