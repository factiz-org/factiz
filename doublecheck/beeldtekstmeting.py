"""De tekstregel voor beeldtreffers gemeten (PLAN.md #26.3).

Vastgelegd vóór het meten (PLAN #26.3):

- **valse treffers op verse memes**: de sjablonen 51 tot 100 van de
  imgflip-API, die §93 niet zag, met per sjabloon 10 memes; onderschriften
  uit de Engelse stukken van de tekst-stiltetoets ná de 500 die §93 gebruikte.
  Index: de 551 beelden van §90 plus per sjabloon de eerste meme. Vragen: de
  andere 9, als origineel en in kader B. Elke treffer is vals, want het is
  een andere meme;
- **wat de regel kost**: de 14 kopieën van §92 van elk indexbeeld, met en
  zonder de regel;
- de vier varianten van §92 met haar drempels, niet opnieuw geijkt; de
  tekstdrempel is `text_related` uit config.

Alleen een vraag met een beeldtreffer wordt gelezen: zonder treffer kan de
regel niets veranderen. Van elk beeld blijft alleen de gelezen tekst over.

    python -m doublecheck.beeldtekstmeting ophalen|meten
"""

from __future__ import annotations

import collections
import json
import time
from pathlib import Path
from typing import Callable

from doublecheck.beeldtekst import beeldtreffer_telt
from doublecheck.kadermeting import VARIANTEN, beslis, routes
from doublecheck.ocr import OcrResult

MAP = Path("data/extern/stilte-beelden")
SJABLONEN = range(50, 100)      # de rangen 51 tot 100
PER_SJABLOON = 10
EERDER_GEBRUIKT = 500           # onderschriften van §93
UITSLAG = Path("data/kadermeting/uitslag-beeldtekst.json")


def lees_alles(beelden: list, lees: Callable) -> list[OcrResult]:
    return [lees(b) for b in beelden]


def _leeg() -> collections.Counter:
    return collections.Counter(goed=0, fout=0, vals=0, niets=0)


def tel(uitkomsten: list[tuple[str, int | None, tuple]], ocr_vraag: dict[str, OcrResult],
        index_ocr: list[OcrResult], vergelijk: Callable[[str, str], float], *,
        drempel_pdq: int, drempels_dino: dict[str, float | None], drempel_tekst: float) -> dict:
    """Per variant de uitkomsten zonder en met de regel. `doel` is het
    indexbeeld dat een kopie hoort te vinden, of `None` als elke treffer vals
    is (een andere meme)."""
    uit = {v: {"zonder": _leeg(), "met": _leeg()} for v in VARIANTEN}
    for vraag, doel, x in uitkomsten:
        for variant in VARIANTEN:
            d = drempels_dino.get(variant)
            gekozen = beslis(*routes(variant, x), drempel_pdq=drempel_pdq,
                             drempel_dino=d if d is not None else float("inf"))
            met = gekozen
            if gekozen is not None and not beeldtreffer_telt(ocr_vraag[vraag], index_ocr[gekozen],
                                                             vergelijk, drempel_tekst):
                met = None
            for soort, keuze in (("zonder", gekozen), ("met", met)):
                if keuze is None:
                    uit[variant][soort]["niets"] += 1
                elif doel is None:
                    uit[variant][soort]["vals"] += 1
                else:
                    uit[variant][soort]["goed" if keuze == doel else "fout"] += 1
    return uit


def ophalen() -> int:
    import httpx

    from doublecheck.beeldstilte import KOP, _haal

    doel = MAP / "sjablonen-2"
    doel.mkdir(parents=True, exist_ok=True)
    meta = []
    with httpx.Client(headers=KOP) as client:
        memes = client.get("https://api.imgflip.com/get_memes", timeout=30).json()["data"]["memes"]
        for rang in SJABLONEN:
            m = memes[rang]
            data, ext = _haal(client, m["url"])
            if data is not None:
                naam = f"{rang:02d}.{ext}"
                (doel / naam).write_bytes(data)
                meta.append({"rang": rang, "bestand": naam, "naam": m["name"], "url": m["url"]})
            time.sleep(1)
    (MAP / "sjablonen-2.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(meta)


def meten() -> dict:
    from doublecheck.beeldembedding import alle_vectoren
    from doublecheck.beeldstilte import lui, maak_meme, onderschriften, splits
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_text
    from doublecheck.kadermeting import KOPIEEN, SNEDEN, Routes, _kader_b, m4fc_helften
    from doublecheck.ocr import extract_text

    config = load_config()
    combinatie = json.loads(Path("data/kadermeting/uitslag-combinatie.json").read_text(encoding="utf-8"))
    drempels_dino = {v: d["drempel_dino"] for v, d in combinatie.items()}
    drempel_pdq = config.thresholds.image_same
    drempel_tekst = config.thresholds.text_related
    versie = config.model_versions.text_embedding

    vectoren: dict[str, object] = {}

    def vergelijk(a: str, b: str) -> float:
        for t in (a, b):
            if t not in vectoren:
                vectoren[t] = fingerprint_text(t, versie).vector
        return float(vectoren[a] @ vectoren[b])

    def lees(beeld) -> OcrResult:
        return extract_text(beeld, config.ocr)

    index = [b for _, b in m4fc_helften()[0]]
    aantal_m4fc = len(index)
    rijen = [json.loads(r) for r in Path("data/stiltetoets/regels.jsonl").read_text(encoding="utf-8").splitlines() if r]
    teksten = onderschriften(rijen, EERDER_GEBRUIKT + len(SJABLONEN) * PER_SJABLOON)[EERDER_GEBRUIKT:]
    memevragen = []
    for t, (naam, laad) in enumerate(lui(MAP / "sjablonen-2")):
        sjabloon = laad()
        if sjabloon is None:
            continue
        onder = [splits(teksten[t * PER_SJABLOON + k]) for k in range(PER_SJABLOON)]
        index.append(maak_meme(sjabloon, *onder[0]))
        rang = naam.split(".")[0]
        memevragen += [(f"meme:{rang}-{k}", sjabloon, tekst) for k, tekst in enumerate(onder) if k]
    print(f"index {len(index)} beelden; {len(memevragen)} memes als vraag", flush=True)

    r = Routes(index, alle_vectoren)
    index_ocr = lees_alles(index, lees)
    print(f"indexbeelden gelezen: {sum(o.readable for o in index_ocr)} van {len(index)} met tekst", flush=True)

    uitkomsten: dict[str, list] = collections.defaultdict(list)
    ocr_vraag: dict[str, OcrResult] = {}

    def verwerk(groep_van: Callable[[str], str], blok: list[tuple[str, int | None, object]]) -> None:
        for (vraag, doel, beeld), x in zip(blok, r.vraag([b for _, _, b in blok])):
            if any(beslis(*routes(v, x), drempel_pdq=drempel_pdq,
                          drempel_dino=drempels_dino[v] if drempels_dino[v] is not None else float("inf"))
                   is not None for v in VARIANTEN):
                ocr_vraag[vraag] = lees(beeld)
            uitkomsten[groep_van(vraag)].append((vraag, doel, x))

    soorten = {**KOPIEEN, **SNEDEN}
    for i, beeld in enumerate(index[:aantal_m4fc]):
        verwerk(lambda v: v.split(":")[2], [(f"kopie:{i}:{s}", i, maak(beeld)) for s, maak in soorten.items()])
        if i % 50 == 0:
            print(f"  kopieën: {i} van {aantal_m4fc}", flush=True)
    for start in range(0, len(memevragen), 16):
        blok = []
        for vraag, sjabloon, tekst in memevragen[start:start + 16]:
            meme = maak_meme(sjabloon, *tekst)
            blok += [(f"{vraag}|origineel", None, meme), (f"{vraag}|kader_b", None, _kader_b(meme))]
        verwerk(lambda v: "memes", blok)
    print(f"gelezen vragen: {len(ocr_vraag)}", flush=True)

    uit = {groep: tel(lijst, ocr_vraag, index_ocr, vergelijk, drempel_pdq=drempel_pdq,
                      drempels_dino=drempels_dino, drempel_tekst=drempel_tekst)
           for groep, lijst in uitkomsten.items()}
    meme_treffers = sorted(v for v, d, x in uitkomsten["memes"] if v in ocr_vraag)
    return {"groepen": uit, "drempel_tekst": drempel_tekst, "meme_treffers": meme_treffers}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="De tekstregel voor beeldtreffers (PLAN #26.3)")
    parser.add_argument("stap", choices=("ophalen", "meten"))
    args = parser.parse_args()
    if args.stap == "ophalen":
        print(f"sjablonen 51-100: {ophalen()}")
        return
    uit = meten()
    UITSLAG.write_text(json.dumps(uit, indent=1), encoding="utf-8")
    for groep, varianten in uit["groepen"].items():
        for variant, d in varianten.items():
            z, m = d["zonder"], d["met"]
            print(f"{groep:<22} {variant:<20} zonder: goed {z['goed']:>4} vals {z['vals']:>4}"
                  f"  | met: goed {m['goed']:>4} vals {m['vals']:>4}", flush=True)


if __name__ == "__main__":
    main()
