"""De volle beeldindex: de oogst (PLAN #32.35).

De factcheckartikelen die nog niet in de pool van #32.21 staan, beleefd opgehaald zoals die pool: per site één verzoek
tegelijk, robots.txt, als FactizResearch, en de sites in `beeldindexmeting.UITGESLOTEN` niet. Per artikel de pagina en
de beelden in één keer: van elk beeld PDQ en de punten (`beeldbevestiging.artikelbeeld`), en in hetzelfde geheugen de
vraag `rol-v3` (`beeldrolvraag`) voor de Batch API, op openbare artikelen. Geen beeld gaat naar schijf (B35); daarna
blijven alleen van de virale beelden de punten over. Een batch die na 20 minuten niet dicht is, wordt geannuleerd; een
beeld zonder antwoord is *onbekend*, nooit viraal. Eerst de proef van 1.000 artikelen; `tellen` schat de rest met de
regels die vooraf in PLAN staan.

    python -m doublecheck.hittewacht -- python -m doublecheck.beeldoogst oogsten --proef 1000
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldoogst oogsten --alles
    python -m doublecheck.beeldoogst ophalen|tellen
"""

from __future__ import annotations

import json
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from doublecheck import beeldindexmeting as bm

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "beeldoogst"
POOL = WORTEL / "data" / "vindronde" / "pool-artikelen.jsonl"
ZAAD = 3235
GRENS_PROEF = 0.50          # PLAN #32.35: de proef, de code stopt ervoor
# de volle oogst, met de proef erbij: §211 schat de rest op ~$10,70 voor de rolvraag (PO 2026-11-03: "start de volle oogst")
GRENZEN = {"proef": GRENS_PROEF, "alles": 12.50}
# zoals #32.32 een batch die niet dicht komt annuleren, maar later: hier 400 vragen met beelden per batch, in #32.32 100
GRENS_BATCH = 60 * 60
DRADEN = 12                 # zoals de pool van #32.21
VERWACHT_PER_ARTIKEL = 0.0002   # rol-v3 per artikel met beelden, §199 ($0,105 voor 539)
SCHATTING_ROL3 = 2 * VERWACHT_PER_ARTIKEL   # voor de grens, ruim; de werkelijke kosten komen bij het ophalen
# PO 2026-11-03: FACTLY trekt het corpus naar India, en de eigen artikelen van N staan al in de pool; daarom niet in de
# rest van de oogst, naast de sites die de oogst al overslaat
OVERGESLAGEN = bm.UITGESLOTEN | frozenset({"factly.in"})
# de regels van PLAN #32.35: wanneer het plan eerst moet veranderen
MAX_NIET_200, MAX_DAGEN, MAX_GB = 0.25, 3, 10


def te_oogsten(urls: dict[str, str], klaar: set[str], uitgesloten: frozenset[str]) -> list[str]:
    """De adressen die nog niet in de pool staan (`urls`: adres → url), zonder de uitgesloten sites, gesorteerd."""
    return sorted(u for a, u in urls.items() if a not in klaar and bm.host(u) not in uitgesloten)


def proef_keuze(urls: list[str], n: int, zaad: int = ZAAD) -> list[str]:
    """Een vaste, willekeurige keuze van `n`, dus per site naar verhouding; de volgorde van de invoer telt niet."""
    alle = sorted(set(urls))
    return sorted(random.Random(zaad).sample(alle, min(n, len(alle))))


def al_klaar(artikelen: list[dict], kaart: list[dict]) -> set[str]:
    """Wat een herstart niet opnieuw ophaalt: een artikel zonder beelden, of met een regel in de kaart (de rolvraag is
    gesteld, of de grens hield haar tegen). Een artikel met beelden dat nog in de wachtrij zat, gaat opnieuw: anders
    raakt het zijn virale beelden kwijt."""
    gevraagd = {k["artikel"] for k in kaart}
    return {a["url"] for a in artikelen if not a["beelden"] or a["url"] in gevraagd}


def werk_voor(urls: list[str], proef: int, alles: bool, zaad: int = ZAAD) -> list[str]:
    """Wat de oogst ophaalt: bij `alles` elk te oogsten artikel, anders de vaste proefkeuze."""
    return sorted(set(urls)) if alles else proef_keuze(urls, proef, zaad)


def te_wissen_voor_batch(kaart: list[dict], batch_id: str, beelden: dict[str, list[str]],
                         rollen: list[dict]) -> list[tuple[str, str]]:
    """Zodra een batch dicht is: van de artikelen in die batch de beelden die geen *viraal* kregen (ook zonder
    antwoord), zodat de punten niet tot het einde van de oogst blijven staan."""
    artikelen = {k["artikel"] for k in kaart if k.get("batch") == batch_id}
    return te_wissen({a: b for a, b in beelden.items() if a in artikelen}, rollen)


def te_wissen(beelden: dict[str, list[str]], rollen: list[dict]) -> list[tuple[str, str]]:
    """Van welke beelden de punten weg mogen: alles wat geen *viraal* kreeg, ook zonder antwoord (onbekend)."""
    rol = {(r["artikel"], b): x for r in rollen for b, x in zip(r["beelden"], r["rollen"])}
    return [(a, b) for a in sorted(beelden) for b in beelden[a] if rol.get((a, b)) != "viraal"]


def schatting(artikelen: list[dict], rollen: list[dict], kosten: float, rest_per_host: dict[str, int],
              bytes_per_viraal: float, draden: int = DRADEN) -> dict:
    """Wat de proef zegt over de rest: per site de mediane tijd per artikel (een site die de proef niet zag, krijgt de
    mediaan van alle artikelen), de duur als de langste site of al het werk over de draden, de beelden per artikel, het
    aandeel viraal, de kosten per artikel met beelden en de opslag; met de regels van PLAN #32.35. Een artikel dat na
    een herstart twee keer staat, telt één keer (de laatste)."""
    artikelen = list({a["url"]: a for a in artikelen}.values())
    per_host: dict[str, list[float]] = defaultdict(list)
    for a in artikelen:
        per_host[a["host"]].append(a["seconden"])
    alle = statistics.median(a["seconden"] for a in artikelen)
    sec = {h: n * (statistics.median(per_host[h]) if h in per_host else alle) for h, n in rest_per_host.items()}
    duur = max(max(sec.values(), default=0), sum(sec.values()) / draden) / 3600
    rollen_alle = [x for r in rollen for x in r["rollen"]]
    viraal = rollen_alle.count("viraal") / len(rollen_alle) if rollen_alle else 0.0
    beelden_per_artikel = sum(len(a["beelden"]) for a in artikelen) / len(artikelen)
    per_artikel = kosten / len(rollen) if rollen else 0.0
    rest = sum(rest_per_host.values())
    opslag = rest * beelden_per_artikel * viraal * bytes_per_viraal / 1e9
    niet_200 = sum(a["status"] != 200 for a in artikelen) / len(artikelen)
    return {"artikelen": len(artikelen), "antwoorden": dict(Counter(str(a["status"]) for a in artikelen)),
            "aandeel geen 200": round(niet_200, 3), "beelden per artikel": round(beelden_per_artikel, 2),
            "aandeel viraal": round(viraal, 3), "kosten per artikel met beelden": round(per_artikel, 6),
            "rest": rest, "duur rest, uur": round(duur, 1),
            "kosten rest": round(rest * (1 - niet_200) * per_artikel, 2), "opslag rest, GB": round(opslag, 2),
            "plan moet veranderen": {
                "meer dan 25% geen 200": niet_200 > MAX_NIET_200,
                "kosten per artikel meer dan twee keer $0,0002": per_artikel > 2 * VERWACHT_PER_ARTIKEL,
                "duur rest meer dan 3 dagen": duur > MAX_DAGEN * 24,
                "opslag rest meer dan 10 GB": opslag > MAX_GB}}


# --- de bestanden en de CLI ------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, regels: list[dict]) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as fh:
        for r in regels:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _puntpad(artikel: str, beeld: str) -> Path:
    from doublecheck.vindronde import _sha

    return MAP / "punten" / (_sha(artikel, beeld) + ".npz")


def _alle() -> tuple[list[str], dict[str, str]]:  # pragma: no cover - op de databases
    """De te oogsten adressen, en per adres de claimtekst voor de rolvraag."""
    import sqlite3

    from doublecheck.vindronde import adres

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    urls, claims = {}, {}
    for url, tekst in conn.execute("SELECT f.url, c.canonical_text FROM factcheck f JOIN claim c USING (claim_id) "
                                   "WHERE f.url LIKE 'http%'"):
        urls.setdefault(adres(url), url)
        claims.setdefault(adres(url), tekst)
    klaar = {adres(r["url"]) for r in _jsonl(POOL)}
    return te_oogsten(urls, klaar, OVERGESLAGEN), claims


def _uitgegeven() -> float:  # pragma: no cover - een bestand
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in _jsonl(MAP / "batches.jsonl"))


def _oogsten(proef: int, alles: bool = False) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf
    import threading

    import anthropic
    import cv2

    from doublecheck import beeldbevestiging as bb
    from doublecheck import beeldrolvraag as br
    from doublecheck import beeldvraag as bv
    from doublecheck import vindronde as vr
    from doublecheck.varianten import laad_sleutel

    cv2.setNumThreads(2)    # hoogstens twee kernen (PO)
    laad_sleutel()
    client = anthropic.Anthropic()
    alle, claims = _alle()
    grens = GRENZEN["alles" if alles else "proef"]
    setpad = MAP / "proef.json"
    if alles:
        werk = werk_voor(alle, proef, alles=True)
    else:
        if not setpad.exists():
            MAP.mkdir(parents=True, exist_ok=True)
            setpad.write_text(json.dumps(werk_voor(alle, proef, alles=False), indent=0), encoding="utf-8")
        werk = json.loads(setpad.read_text(encoding="utf-8"))
    apad, bpad, kaart = MAP / "artikelen.jsonl", MAP / "beelden.jsonl", MAP / "kaart.jsonl"
    klaar = al_klaar(_jsonl(apad), _jsonl(kaart))
    per_host = defaultdict(list)
    for u in werk:
        if u not in klaar:
            per_host[bm.host(u)].append(u)
    print(f"{sum(map(len, per_host.values()))} artikelen op {len(per_host)} sites ({len(klaar)} al gedaan); "
          f"${_uitgegeven():.2f} van ${grens:.2f}", flush=True)
    web, rekenen, slot, wachtrij, teller = bm.Beleefd(), threading.Lock(), threading.Lock(), [], Counter()

    def dien_in(alles: bool = False):
        while wachtrij and (alles or len(wachtrij) >= 400 or sum(d["grootte"] for d in wachtrij) >= vr.MAX_BATCH_BYTES):
            deel, grootte = [], 0
            while wachtrij and len(deel) < 400 and grootte < vr.MAX_BATCH_BYTES:
                deel.append(wachtrij.pop(0))
                grootte += deel[-1]["grootte"]
            schatting_ = SCHATTING_ROL3 * len(deel)
            if _uitgegeven() + schatting_ > grens:
                _schrijf(kaart, [{**{k: d[k] for k in ("custom_id", "artikel", "beelden")}, "status": "grens"}
                                 for d in deel])
                print(f"de grens: ${_uitgegeven():.2f} plus ${schatting_:.2f}; {len(deel)} zonder rol", flush=True)
                continue
            batch = client.messages.batches.create(requests=[{"custom_id": d["custom_id"], "params": d["params"]}
                                                              for d in deel])
            _schrijf(kaart, [{**{k: d[k] for k in ("custom_id", "artikel", "beelden")}, "status": "gevraagd",
                              "batch": batch.id} for d in deel])
            _schrijf(MAP / "batches.jsonl", [{"id": batch.id, "schatting": round(schatting_, 4), "aantal": len(deel),
                                              "moment": time.time()}])
            print(f"batch {batch.id}: {len(deel)} artikelen, schatting ${schatting_:.3f}", flush=True)

    def pagina(url):
        if not web.mag(url):
            return "verboden", "", []
        antwoord = web._vraag(url)
        if antwoord is None or antwoord.status_code != 200:
            return ("fout" if antwoord is None else antwoord.status_code), "", []
        try:
            titel, beelden = vr.beelden_met_context(antwoord.text, str(antwoord.url))
            return 200, titel, beelden
        except Exception:   # een pagina die niet te lezen is
            return "onleesbaar", "", []

    def doe(lijst):
        for url in lijst:
            begin = time.monotonic()
            status, titel, beelden = pagina(url)
            rijen, inhoud = [], []
            for b in beelden[:br.MAX_BEELDEN]:
                bytes_ = web.beeld(b["beeld"])
                if bytes_ is None:
                    continue
                try:
                    with rekenen:
                        kenm = bb.artikelbeeld(bytes_)
                    if min(kenm["breedte"], kenm["hoogte"]) >= bm.MIN_ZIJDE:
                        p = _puntpad(url, b["beeld"])
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(bv.punten_naar_bytes(kenm.pop("punten")))
                        rijen.append({"artikel": url, **b, **{k: v for k, v in kenm.items() if k != "punten"}})
                        inhoud.append(bytes_)
                except Exception as e:   # kapot of geen beeld: overslaan; alleen de soort fout (DR3)
                    with slot:
                        teller[f"fout {type(e).__name__}"] += 1
            params = None
            if rijen:
                try:
                    params = br.verzoek(claims.get(vr.adres(url), ""), titel, rijen, versie="rol-v3",
                                        beelden_bytes=inhoud)
                except Exception as e:   # alleen de soort fout (DR3)
                    with slot:
                        teller[f"rol {type(e).__name__}"] += 1
            del inhoud
            _schrijf(bpad, rijen)
            _schrijf(apad, [{"url": url, "host": bm.host(url), "status": status, "titel": titel,
                             "beelden": [r["beeld"] for r in rijen], "seconden": round(time.monotonic() - begin, 1)}])
            with slot:
                teller["artikelen"] += 1
                teller["met beeld"] += bool(rijen)
                teller["beelden"] += len(rijen)
                if params is not None:
                    wachtrij.append({"custom_id": "oogst-" + vr._sha(url), "artikel": url,
                                     "beelden": [r["beeld"] for r in rijen], "params": params,
                                     "grootte": len(json.dumps(params))})
                    dien_in()
                if teller["artikelen"] % 100 == 0:
                    print(f"  {dict(teller)}", flush=True)

    with cf.ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(doe, sorted(per_host.values(), key=len, reverse=True)))
    with slot:
        dien_in(alles=True)
    print(f"klaar: {dict(teller)}; ${_uitgegeven():.2f} van ${grens:.2f}", flush=True)


def _ophalen() -> None:  # pragma: no cover - netwerk
    """De antwoorden van de rolvraag; een batch die na `GRENS_BATCH` niet dicht is, wordt geannuleerd. Per dichte batch
    gaan de punten weg van elk beeld in die batch dat geen *viraal* kreeg; na de oogst nog één keer voor de rest."""
    import anthropic

    from doublecheck import beeldrolvraag as br
    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    kaartrijen = [r for r in _jsonl(MAP / "kaart.jsonl") if r["status"] == "gevraagd"]
    kaart = {r["custom_id"]: r for r in kaartrijen}
    klaar = {r["artikel"] for r in _jsonl(MAP / "rollen.jsonl")}
    alle = _jsonl(MAP / "batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        status = client.messages.batches.retrieve(b["id"]).processing_status
        if status != "ended" and time.time() - b["moment"] >= GRENS_BATCH:
            client.messages.batches.cancel(b["id"])
            print(f"batch {b['id']} na {GRENS_BATCH // 60} minuten niet dicht: geannuleerd", flush=True)
            while client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                time.sleep(5)
            status = "ended"
        if status != "ended":
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
        _schrijf(MAP / "rollen.jsonl", regels)
        b["werkelijk"], b["mislukt"] = round(werkelijk, 4), mis
        weg = _wis(te_wissen_voor_batch(kaartrijen, b["id"], _beelden_per_artikel(), _jsonl(MAP / "rollen.jsonl")))
        print(f"batch {b['id']}: ${werkelijk:.3f}, {mis} zonder antwoord; de punten van {weg} beelden weg", flush=True)
    (MAP / "batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    if all(b.get("werkelijk") is not None for b in alle) and not _oogst_loopt():
        weg = _wis(te_wissen(_beelden_per_artikel(), _jsonl(MAP / "rollen.jsonl")))
        print(f"de punten van {weg} beelden zonder *viraal* weggegooid", flush=True)
    print(f"samen ${_uitgegeven():.2f} van ${GRENZEN['alles']:.2f}", flush=True)


def _beelden_per_artikel() -> dict[str, list[str]]:  # pragma: no cover - een bestand
    beelden = defaultdict(list)
    for r in _jsonl(MAP / "beelden.jsonl"):
        beelden[r["artikel"]].append(r["beeld"])
    return beelden


def _wis(paren: list[tuple[str, str]]) -> int:  # pragma: no cover - bestanden
    weg = 0
    for a, b in paren:
        p = _puntpad(a, b)
        if p.exists():
            p.unlink()
            weg += 1
    return weg


def _oogst_loopt() -> bool:  # pragma: no cover - het proces
    """Loopt de oogst nog? Dan kan een artikel zonder batch nog een vraag krijgen; de laatste schoonmaak wacht."""
    import subprocess

    return subprocess.run(["pgrep", "-f", "doublecheck.beeldoogst oogsten"], capture_output=True).returncode == 0


def _tellen() -> None:  # pragma: no cover - op de bestanden
    alle, _ = _alle()
    proef = set(json.loads((MAP / "proef.json").read_text(encoding="utf-8")))
    rest = Counter(bm.host(u) for u in alle if u not in proef)
    punten = list((MAP / "punten").glob("*.npz"))
    per_viraal = sum(p.stat().st_size for p in punten) / len(punten) if punten else 0.0
    kosten = sum(b.get("werkelijk") or 0.0 for b in _jsonl(MAP / "batches.jsonl"))
    uit = schatting(_jsonl(MAP / "artikelen.jsonl"), _jsonl(MAP / "rollen.jsonl"), kosten, dict(rest), per_viraal)
    uit["per site, de langste"] = sorted(
        ((h, n) for h, n in rest.items()), key=lambda x: -x[1])[:5]
    uit["opslag per viraal beeld, kB"] = round(per_viraal / 1000, 1)
    uit["kosten proef"] = round(kosten, 3)
    (MAP / "telling.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De volle beeldindex, de oogst (PLAN #32.35)")
    parser.add_argument("stap", choices=("oogsten", "ophalen", "tellen"))
    parser.add_argument("--proef", type=int, default=1000)
    parser.add_argument("--alles", action="store_true", help="oogsten: alle te oogsten artikelen, niet de proef")
    args = parser.parse_args()
    {"oogsten": lambda: _oogsten(args.proef, args.alles), "ophalen": _ophalen, "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
