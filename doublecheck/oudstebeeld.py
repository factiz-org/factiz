"""De voormeting voor het beeld (PLAN #32.40, PO 2026-11-04: "kijken of ze hetzelfde plaatje tegenkomen").

Een factchecker zoekt de oudste plek waar een beeld stond. Google Vision gaf eerder alleen een lijst met titels, en die
zegt niet wanneer een beeld eerst verscheen (§148). Hier: bij 100 beelden uit M4FC waarvan de factchecker zegt dat
omgekeerd zoeken het vond (de ijkset op schijf, B35), de pagina's met hetzelfde beeld zonder factchecksites (als op de
eerste dag, `speuren.van_factchecker`), van elke pagina beleefd de datum uit de pagina zelf (per host één verzoek,
robots.txt, nooit het beeld of de tekst bewaard), en de oudste vooraan. Gemeten wordt of de oudste pagina van ruim
vóór de factcheck is, en of ze het echte verhaal geeft (gelezen tegen wat M4FC over het beeld zegt).

    python -m doublecheck.oudstebeeld set|vision|paginas|lezen|tellen
"""

from __future__ import annotations

import datetime
import json
import random
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "oudstebeeld"
M4FC = WORTEL / "data" / "extern" / "m4fc"
LABELS = WORTEL / "docs" / "steekproeven" / "32.40-oudstebeeld.json"
N, N_PAGINAS, ZAAD = 100, 10, 3245
EERDER_DAGEN = 7
MAX_TEKENS = 4_000_000  # een videopagina is ruim 1 MB, de datum staat achteraan
VISIEPRIJS = 3.50 / 1000  # de lijstprijs van Web Detection na de gratis 1.000; de grens telt nooit gratis
BUDGET = 0.50
LABELWAARDEN = ("echt verhaal", "niet", "onduidelijk")

_META = re.compile(r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:published_time|'
                   r'datePublished|uploadDate|date|pubdate|publishdate|publish-date|dc\.date\.issued|'
                   r'sailthru\.date|parsely-pub-date)["\'][^>]*content=["\']([^"\']+)', re.I)
_META2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\'](?:'
                    r'article:published_time|og:published_time|datePublished|date|pubdate|publishdate)["\']', re.I)
_LD = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_TIJD = re.compile(r'<time[^>]+datetime=["\']([^"\']+)', re.I)
_ADRES = re.compile(r"/((?:19|20)\d\d)[/-](\d\d)[/-](\d\d)(?:[/-]|$)")
_ISO = re.compile(r"((?:19|20)\d\d)-(\d\d)-(\d\d)")


class Weigering(Exception):
    """Tellen kan niet: een oudste pagina zonder label, of boven de grens."""


def _geldig(j: str, m: str, d: str) -> str | None:
    try:
        datum = datetime.date(int(j), int(m), int(d))
    except ValueError:
        return None
    return datum.isoformat() if datetime.date(1995, 1, 1) <= datum <= datetime.date.today() else None


def paginadatum(html: str, url: str) -> str | None:
    """De datum van een pagina: eerst haar eigen publicatiedatum (meta), dan de gestructureerde data, dan een
    `<time>`, en pas dan een datum in het adres. Een onmogelijke datum telt nooit."""
    for patroon in (_META, _META2, _LD, _TIJD):
        m = patroon.search(html or "")
        if m:
            iso = _ISO.search(m.group(1))
            if iso and (datum := _geldig(*iso.groups())):
                return datum
    m = _ADRES.search(url or "")
    return _geldig(*m.groups()) if m else None


def oudste(paginas: list[dict]) -> dict | None:
    """De pagina met de vroegste datum; een pagina zonder datum wint nooit."""
    met = [p for p in paginas if p.get("datum")]
    return min(met, key=lambda p: p["datum"]) if met else None


def eerder(datum: str | None, factcheck: str | None, dagen: int = EERDER_DAGEN) -> bool:
    """De pagina is minstens `dagen` ouder dan de factcheck: het beeld stond er al vóór het rondging."""
    if not datum or not factcheck:
        return False
    return datetime.date.fromisoformat(datum) <= datetime.date.fromisoformat(factcheck[:10]) - datetime.timedelta(dagen)


def kies(rijen: list[dict], op_schijf: set[int], n: int = N, zaad: int = ZAAD) -> list[dict]:
    """De beelden waarbij de factchecker omgekeerd zocht en die op schijf staan, een vaste steekproef."""
    kandidaten = [{**r, "index": i} for i, r in enumerate(rijen)
                  if i in op_schijf and "reverse image search" in (r.get("verification_strategy") or "")]
    return sorted(random.Random(zaad).sample(kandidaten, min(n, len(kandidaten))), key=lambda r: r["index"])


# --- de bestanden en het netwerk ---------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad)


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _bestanden() -> dict[int, Path]:  # pragma: no cover - een map
    return {int(p.stem): p for p in (M4FC / "beelden").iterdir() if p.stem.isdigit()}


def _set() -> None:  # pragma: no cover - op de bestanden
    if (UIT / "set.jsonl").exists():
        raise Weigering("de set ligt al vast")
    rijen = json.loads((M4FC / "M4FC.json").read_text(encoding="utf-8"))
    velden = ("claim", "verdict", "fc_pub_date", "article_url", "verification_strategy", "date", "location", "event",
              "true_caption", "provenance", "source")
    gekozen = [{"index": r["index"], **{k: r.get(k) for k in velden}} for r in kies(rijen, set(_bestanden()))]
    _schrijf(UIT / "set.jsonl", gekozen)
    print(f"{len(gekozen)} beelden")


def _vision() -> None:  # pragma: no cover - met Google Cloud Vision
    import os

    from doublecheck.beeldzoeken import zoek
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = os.environ["GOOGLE_VISION_API_KEY"]
    klaar = {r["index"] for r in _jsonl(UIT / "vision.jsonl")}
    werk = [r for r in _jsonl(UIT / "set.jsonl") if r["index"] not in klaar]
    if (len(klaar) + len(werk)) * VISIEPRIJS > BUDGET:
        raise Weigering(f"{len(klaar) + len(werk)} vragen aan Vision komen boven ${BUDGET:.2f}")
    bestanden = _bestanden()
    for r in werk:
        uit = zoek(bestanden[r["index"]], sleutel)
        _schrijf(UIT / "vision.jsonl", [{"index": r["index"], "paginas": uit["paginas"], "kosten": VISIEPRIJS}])
    print(f"{len(werk)} beelden gezocht, samen ${(len(klaar) + len(werk)) * VISIEPRIJS:.2f}")


def _paginas() -> None:  # pragma: no cover - netwerk
    """Van elke pagina met hetzelfde beeld (zonder factchecksites, de eerste tien) de datum, beleefd; hervatbaar."""
    from concurrent.futures import ThreadPoolExecutor

    import httpx

    from doublecheck import berichtcontrole as bc
    from doublecheck.beeldindexmeting import Beleefd
    from doublecheck.speuren import eerste_dag_domeinen, van_factchecker
    from doublecheck.werkwijze import KOP

    domeinen = eerste_dag_domeinen(bc.herkomstlijst()["sites"])
    klaar = {(r["index"], r["url"]) for r in _jsonl(UIT / "paginas.jsonl")}
    werk = []
    for v in _jsonl(UIT / "vision.jsonl"):
        paginas = [p for p in v["paginas"] if not van_factchecker(p["url"], domeinen)][:N_PAGINAS]
        werk += [(v["index"], p) for p in paginas if (v["index"], p["url"]) not in klaar]
    beleefd = Beleefd()
    beleefd.web = httpx.Client(headers=KOP, follow_redirects=True, timeout=30)

    def een(taak):
        index, p = taak
        datum, status = None, "robots"
        if beleefd.mag(p["url"]):
            a = beleefd._vraag(p["url"])
            status = a.status_code if a is not None else "fout"
            if status == 200 and "html" in a.headers.get("content-type", ""):
                datum = paginadatum(a.text[:MAX_TEKENS], p["url"])
        if datum is None and status != 200:
            datum = paginadatum("", p["url"])
        return {"index": index, "url": p["url"], "titel": p["titel"], "status": status, "datum": datum}

    with ThreadPoolExecutor(12) as pool:
        for i, rij in enumerate(pool.map(een, werk), 1):
            _schrijf(UIT / "paginas.jsonl", [rij])
            if i % 100 == 0:
                print(f"{i} van {len(werk)} pagina's", flush=True)
    print(f"klaar: {len(werk)} pagina's")


def _per_beeld() -> list[dict]:  # pragma: no cover - op de bestanden
    per = {}
    for p in _jsonl(UIT / "paginas.jsonl"):
        per.setdefault(p["index"], []).append(p)
    vision = {v["index"]: v for v in _jsonl(UIT / "vision.jsonl")}
    uit = []
    for s in _jsonl(UIT / "set.jsonl"):
        paginas = per.get(s["index"], [])
        o = oudste(paginas)
        uit.append({**s, "gevonden": len((vision.get(s["index"]) or {}).get("paginas", [])), "zonder fc": len(paginas),
                    "met datum": sum(bool(p["datum"]) for p in paginas), "oudste": o,
                    "eerder": eerder(o["datum"] if o else None, s.get("fc_pub_date"))})
    return uit


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    if not LABELS.exists():
        return {}
    labels = {k: v["label"] for k, v in json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {}).items()}
    fout = [k for k, v in labels.items() if v not in LABELWAARDEN]
    if fout:
        raise Weigering(f"onbekende labels: {fout[:3]}")
    return labels


def _lezen() -> None:  # pragma: no cover - op de bestanden
    labels = _labels()
    for b in _per_beeld():
        if not b["eerder"] or str(b["index"]) in labels:
            continue
        o = b["oudste"]
        print(f"\n== {b['index']} ({b['fc_pub_date'][:10]}) {b['verdict']}: {b['claim'][:160]}\n"
              f"   M4FC: datum {b['date']} | plek {b['location']} | gebeurtenis {b['event']} | echt {b['true_caption']}"
              f"\n   oudste: {o['datum']} {o['url']}\n   titel: {o['titel'][:200]}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    beelden, labels = _per_beeld(), _labels()
    open_ = [b["index"] for b in beelden if b["eerder"] and str(b["index"]) not in labels]
    if open_:
        raise Weigering(f"{len(open_)} oudste pagina's zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    n = len(beelden)
    uit = {"beelden": n, "Vision vond pagina's": sum(b["gevonden"] > 0 for b in beelden),
           "pagina's zonder factchecksites": sum(b["zonder fc"] > 0 for b in beelden),
           "een pagina met datum": sum(b["met datum"] > 0 for b in beelden),
           "oudste ruim vóór de factcheck": sum(b["eerder"] for b in beelden),
           "en geeft het echte verhaal": sum(b["eerder"] and labels.get(str(b["index"])) == "echt verhaal"
                                              for b in beelden),
           "kosten": round(sum(r["kosten"] for r in _jsonl(UIT / "vision.jsonl")), 4)}
    (UIT / "telling.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De voormeting voor het beeld (PLAN #32.40)")
    parser.add_argument("stap", choices=("set", "vision", "paginas", "lezen", "tellen"))
    args = parser.parse_args()
    {"set": _set, "vision": _vision, "paginas": _paginas, "lezen": _lezen, "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
