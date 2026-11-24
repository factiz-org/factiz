"""Echt nieuws en ware zinnen (PLAN #31.6, E8.S6, B42).

De basisset is scheef: tegenover ~100.000 onware stukken staan ~9.000 ware, en
van de Russische en Arabische stukken is 90% onwaar. Een leerling leert dan
"verrassend is onwaar" of "Russisch is nep" (§140). Dit haalt ware stukken in
de talen van de onware, volgens het ophaalplan dat de PO goedkeurde
(2026-10-23):

- **Wikinews** (CC BY 2.5/4.0): de CirrusSearch-inhoudsdump van 2025-12-29, één
  bestand per taal met schone tekst, gestreamd en meteen verwerkt; van de
  Russische (8,6 GB, een bot-archief) alleen de eerste ~100 MB.
- **Wikipedia** (CC BY-SA 3.0 en GFDL): de dump van 2023-11-01 van Hugging
  Face, via hun datasets-API in porties van 100, per taal de eerste 3.000
  artikelen; daaruit de zinnen van de inleiding.

Alleen tekst, met titel en adres voor de naamsvermelding; één verzoek
tegelijk, hervatbaar. Per artikel een vaste helft (de hash van de zeef): de
ontwikkelhelft wordt leerstof, de toetshelft alleen toets voor de poort.

    python -m doublecheck.echtnieuws ophalen --bron wikinews|wikipedia [--talen en,ta]
    python -m doublecheck.echtnieuws tellen
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "echtnieuws"
AGENT = "FactizResearch/1.0 (factiz.org; alleen tekst, voor een meting van vals alarm, PLAN #31.6)"

WIKINEWS_DUMP = "20251229"
WIKINEWS_TALEN = ("en", "pt", "fr", "pl", "ar", "es", "it", "de", "zh", "nl", "cs", "ta", "fa", "ru")
RU_MAX_BYTES = 100 * 1024 ** 2
WIKIPEDIA_DUMP = "20231101"
WIKIPEDIA_TALEN = ("en", "ru", "ar", "es", "pt", "de", "fr", "it", "nl", "pl", "cs", "hu", "uk", "tr", "fa", "hi",
                   "te", "ta", "ml", "bn", "si", "ka", "hy", "az", "id", "zh")
N_ARTIKELEN, PORTIE = 3_000, 100
MAX_TEKENS = 2_000       # openingstekst van een nieuwsartikel
MIN_TEKST = 200          # korter is geen artikel (hoofdpagina, portaal)
MAX_ZINNEN = 10          # per Wikipedia-artikel
# "8 tot 60 woorden" uit het ophaalplan, in elk schrift gelijk: tekens zonder
# spaties, een breed teken (Han, kana, Hangul) voor drie (`zinnen._lengte`).
# De ondergrens op 30: een Arabische zin van negen woorden telt 38 tekens.
MIN_LENGTE, MAX_LENGTE = 30, 360


def cirrus_paren(regels: Iterable[str]) -> Iterator[tuple[str, dict]]:
    """De CirrusSearch-dump wisselt een indexregel en een documentregel af:
    geef per pagina haar id en haar document."""
    id_ = None
    for regel in regels:
        if not regel.strip():
            continue
        r = json.loads(regel)
        if "index" in r:
            id_ = str(r["index"].get("_id"))
        elif id_ is not None:
            yield id_, r
            id_ = None


def nieuwsstuk(taal: str, page_id: str, doc: dict) -> dict | None:
    """Een Wikinews-artikel als waar nieuws: titel en openingstekst (hooguit
    `MAX_TEKENS`), datum, adres. None als er bijna geen tekst is."""
    from doublecheck.zeef import helft

    titel = " ".join(str(doc.get("title") or "").split())
    tekst = " ".join(str(doc.get("opening_text") or doc.get("text") or "").split())
    if len(tekst) < MIN_TEKST:
        return None
    return {"sleutel": f"wikinews:{taal}:{page_id}", "bron": "wikinews", "soort": "nieuws", "label": "waar",
            "taal": taal, "titel": titel, "url": f"https://{taal}.wikinews.org/wiki/{titel.replace(' ', '_')}",
            "datum": (doc.get("create_timestamp") or doc.get("timestamp") or "")[:10] or None,
            "helft": helft(f"wikinews:{taal}:{page_id}"), "tekst": f"{titel}\n{tekst}"[:MAX_TEKENS]}


def _inleiding(tekst: str) -> str:
    """De eerste alinea van een Wikipedia-artikel."""
    return next((a.strip() for a in tekst.split("\n") if a.strip()), "")


def feitzinnen(artikel: dict, taal: str) -> list[dict]:
    """De zinnen uit de inleiding van een Wikipedia-artikel binnen de
    lengtegrenzen, hooguit `MAX_ZINNEN`; alle in de helft van het artikel."""
    from doublecheck.zeef import helft
    from doublecheck.zinnen import _lengte, zinnen

    sleutel = f"wikipedia:{taal}:{artikel['id']}"
    gekozen = [z for z in zinnen(_inleiding(artikel.get("text") or "")) if MIN_LENGTE <= _lengte(z) <= MAX_LENGTE]
    return [{"sleutel": f"{sleutel}#{i}", "bron": "wikipedia", "soort": "feit", "label": "waar", "taal": taal,
             "titel": artikel.get("title"), "url": artikel.get("url"), "datum": None, "helft": helft(sleutel),
             "tekst": z} for i, z in enumerate(gekozen[:MAX_ZINNEN])]


# --- ophalen ----------------------------------------------------------------------

def _schrijf_regels(pad: Path, regels: list[dict]) -> None:
    with pad.open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in regels)


def wikinews_ophalen(taal: str) -> dict:  # pragma: no cover - met het netwerk
    """Eén taal, gestreamd: niets van de dump komt op schijf, alleen de
    stukken. Hervatbaar per taal: een taal met een klaar-bestand slaat over."""
    import zlib

    import httpx

    klaar = UIT / f"wikinews-{taal}.klaar.json"
    if klaar.exists():
        return json.loads(klaar.read_text(encoding="utf-8"))
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / f"wikinews-{taal}.jsonl"
    pad.unlink(missing_ok=True)
    url = (f"https://dumps.wikimedia.org/other/cirrussearch/{WIKINEWS_DUMP}/"
           f"{taal}wikinews-{WIKINEWS_DUMP}-cirrussearch-content.json.gz")
    ontpak = zlib.decompressobj(16 + zlib.MAX_WBITS)
    rest, gelezen, stukken, pagina_s = "", 0, 0, 0
    afgebroken = False
    with httpx.stream("GET", url, headers={"User-Agent": AGENT}, timeout=60, follow_redirects=True) as antwoord:
        antwoord.raise_for_status()
        for blok in antwoord.iter_bytes(1 << 20):
            gelezen += len(blok)
            rest += ontpak.decompress(blok).decode("utf-8", errors="replace")
            regels = rest.split("\n")
            rest = regels.pop()
            nieuw = [s for i, d in cirrus_paren(regels) if (s := nieuwsstuk(taal, i, d))]
            pagina_s += sum(1 for r in regels if r.startswith('{"index"'))
            stukken += len(nieuw)
            _schrijf_regels(pad, nieuw)
            if taal == "ru" and gelezen >= RU_MAX_BYTES:
                afgebroken = True
                break
    uitslag = {"taal": taal, "dump": WIKINEWS_DUMP, "bytes": gelezen, "paginas": pagina_s, "stukken": stukken,
               "afgebroken_na_bytes": RU_MAX_BYTES if afgebroken else None}
    klaar.write_text(json.dumps(uitslag), encoding="utf-8")
    return uitslag


def wikipedia_ophalen(taal: str) -> dict:  # pragma: no cover - met het netwerk
    """Per portie van 100 artikelen via de datasets-API, één verzoek per
    seconde; hervatbaar per portie."""
    import httpx

    UIT.mkdir(parents=True, exist_ok=True)
    pad, voortgang = UIT / f"wikipedia-{taal}.jsonl", UIT / f"wikipedia-{taal}.voortgang.json"
    gedaan = set(json.loads(voortgang.read_text())) if voortgang.exists() else set()
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=60) as web:
        for offset in range(0, N_ARTIKELEN, PORTIE):
            if offset in gedaan:
                continue
            for poging in range(6):
                antwoord = web.get("https://datasets-server.huggingface.co/rows",
                                   params={"dataset": "wikimedia/wikipedia", "config": f"{WIKIPEDIA_DUMP}.{taal}",
                                           "split": "train", "offset": offset, "length": PORTIE})
                if antwoord.status_code == 200:
                    break
                if antwoord.status_code not in (429, 500, 502, 503, 504):
                    antwoord.raise_for_status()
                time.sleep(min(120, 10 * 2 ** poging))
            else:
                raise RuntimeError(f"wikipedia {taal} offset {offset}: blijft {antwoord.status_code} geven; later hervatten")
            rijen = [r["row"] for r in antwoord.json().get("rows", [])]
            _schrijf_regels(pad, [z for rij in rijen for z in feitzinnen(rij, taal)])
            gedaan.add(offset)
            voortgang.write_text(json.dumps(sorted(gedaan)))
            time.sleep(1)
    return {"taal": taal, "porties": len(gedaan)}


def lees(bron: str) -> list[dict]:
    from doublecheck.sheffield import regels

    uit = []
    for pad in sorted(UIT.glob(f"{bron}-*.jsonl")):
        uit += regels(pad)
    return uit


def telling() -> dict:
    uit = {}
    for bron in ("wikinews", "wikipedia"):
        stukken = lees(bron)
        uit[bron] = {"stukken": len(stukken), "per taal": dict(Counter(s["taal"] for s in stukken)),
                     "per helft": dict(Counter(s["helft"] for s in stukken))}
    return uit


def main() -> None:  # pragma: no cover - CLI, met het netwerk
    import argparse

    parser = argparse.ArgumentParser(description="Echt nieuws en ware zinnen (#31.6)")
    parser.add_argument("stap", choices=("ophalen", "tellen"))
    parser.add_argument("--bron", choices=("wikinews", "wikipedia"))
    parser.add_argument("--talen", help="komma-gescheiden; standaard alle talen van het plan")
    args = parser.parse_args()
    if args.stap == "tellen":
        print(json.dumps(telling(), ensure_ascii=False, indent=1))
        return
    talen = args.talen.split(",") if args.talen else (WIKINEWS_TALEN if args.bron == "wikinews" else WIKIPEDIA_TALEN)
    for taal in talen:
        t0 = time.time()
        uitslag = wikinews_ophalen(taal) if args.bron == "wikinews" else wikipedia_ophalen(taal)
        print(f"{args.bron} {taal}: {uitslag} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
