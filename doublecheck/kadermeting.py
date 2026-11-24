"""De meting van #26.3: vindt een kopie in een kader, met een stempel of
bijgesneden haar origineel terug?

Op de 1.103 M4FC-beelden op schijf (echte virale beelden uit
factcheckartikelen): de helft in de index, de andere helft als beelden die
er niet in staan, voor de valse treffers. De knipregel is gebouwd op het
kader uit #25.11 (`kader_a`); `kader_b` (een donkere post) en `kader_c` (een
chatbericht) zag hij nooit, en die zijn vastgelegd vóór de eerste meting.
Wie ze na de uitslag bijstelt, meet niet meer wat hier staat.

    python -m doublecheck.kadermeting
"""

from __future__ import annotations

import collections
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from doublecheck.beeldindex import _POPCOUNT, _bijgesneden, _jpeg, _kader, _stempel
from doublecheck.beelduitsnede import indexhashes, vraaghashes
from doublecheck.beeldvraag import beslis  # het beslispad staat sinds #32.15 in de kern (DR4)

VERSIE = "pdq-256-v1"
M4FC = Path("data/extern/m4fc/beelden")


# --- de kopieën ----------------------------------------------------------------

def _kader_b(beeld: Image.Image) -> Image.Image:
    """Een post in donkere modus: avatar, naam en handle, twee regels tekst,
    het beeld met ronde hoeken en wat marge, een knoppenbalk eronder."""
    b, h = beeld.size
    marge = max(8, b // 25)
    kop, voet = int(h * 0.38), int(h * 0.16)
    uit = Image.new("RGB", (b + 2 * marge, h + kop + voet), (21, 32, 43))
    teken = ImageDraw.Draw(uit)
    r = max(10, kop // 7)
    teken.ellipse([marge, marge, marge + 2 * r, marge + 2 * r], fill=(140, 150, 160))
    teken.rectangle([marge + 3 * r, marge + r // 2, marge + 3 * r + b // 3, marge + r], fill=(231, 233, 234))
    teken.rectangle([marge + 3 * r, marge + int(1.4 * r), marge + 3 * r + b // 4, marge + int(1.8 * r)],
                    fill=(113, 118, 123))
    for i, breedte in enumerate((0.92, 0.6)):
        y = marge + 3 * r + i * (r + 4)
        teken.rectangle([marge, y, marge + int(b * breedte), y + max(4, r // 2)], fill=(231, 233, 234))
    masker = Image.new("L", beeld.size, 0)
    ImageDraw.Draw(masker).rounded_rectangle([0, 0, b - 1, h - 1], radius=max(6, b // 30), fill=255)
    uit.paste(beeld, (marge, kop), masker)
    y = kop + h + voet // 3
    for i in range(4):
        x = marge + i * (b // 4)
        teken.ellipse([x, y, x + voet // 4, y + voet // 4], fill=(113, 118, 123))
    return uit


def _kader_c(beeld: Image.Image) -> Image.Image:
    """Een chatbericht: een lichte achtergrond, een witte ballon met een
    label "doorgestuurd", het beeld, en twee regels tekst en een tijd eronder."""
    b, h = beeld.size
    rand, binnen = max(10, b // 12), max(6, b // 40)
    label, onder = max(14, h // 14), int(h * 0.22)
    breed, hoog = b + 2 * binnen, h + label + onder + 2 * binnen
    uit = Image.new("RGB", (breed + 2 * rand, hoog + 2 * rand), (230, 221, 212))
    teken = ImageDraw.Draw(uit)
    teken.rounded_rectangle([rand, rand, rand + breed, rand + hoog], radius=binnen * 2, fill=(255, 255, 255))
    teken.rectangle([rand + binnen, rand + binnen, rand + binnen + b // 3, rand + binnen + label // 2],
                    fill=(150, 150, 150))
    uit.paste(beeld, (rand + binnen, rand + binnen + label))
    y = rand + binnen + label + h + binnen
    for breedte in (0.85, 0.55):
        teken.rectangle([rand + binnen, y, rand + binnen + int(b * breedte), y + max(4, onder // 6)], fill=(40, 40, 40))
        y += onder // 3
    teken.rectangle([rand + breed - b // 6, y, rand + breed - binnen, y + max(3, onder // 10)], fill=(150, 150, 150))
    return uit


def _hoekstempel(beeld: Image.Image) -> Image.Image:
    uit = beeld.copy()
    b, h = uit.size
    teken = ImageDraw.Draw(uit)
    teken.rectangle([b // 30, h // 30, b // 30 + b // 4, h // 30 + h // 8], fill=(200, 20, 20))
    lettertype = ImageFont.load_default(size=max(10, h // 14))
    teken.text((b // 30 + b // 8, h // 30 + h // 16), "FALSE", fill="white", font=lettertype, anchor="mm")
    return uit


def _zonder_boven(beeld: Image.Image) -> Image.Image:
    b, h = beeld.size
    return beeld.crop((0, int(h * 0.15), b, h))


KOPIEEN = {
    "jpeg60": lambda x: _jpeg(x, 60),
    "kader_a": _kader,
    "kader_b": _kader_b,
    "kader_c": _kader_c,
    "stempel_band": _stempel,
    "stempel_hoek": _hoekstempel,
    "bijgesneden_10": _bijgesneden,
    "zonder_boven_15": _zonder_boven,
    "kader_b_met_stempel": lambda x: _kader_b(_hoekstempel(x)),
}

# Welke hashes de vraag en de index meebrengen.
METHODEN = ("basis", "gebied", "uitsneden", "beide")


def _snede(links: float, boven: float, rechts: float, onder: float):
    def maak(beeld: Image.Image) -> Image.Image:
        b, h = beeld.size
        return beeld.crop((int(b * links), int(h * boven), int(b * (1 - rechts)), int(h * (1 - onder))))
    return maak


# Bijsnijdingen die niet op de uitsneden in de index vallen (§89: de eerste
# meting sneed op precies die maten en mat zichzelf).
SNEDEN = {
    "bijgesneden_5_rondom": _snede(0.05, 0.05, 0.05, 0.05),
    "bijgesneden_7_rondom": _snede(0.07, 0.07, 0.07, 0.07),
    "bijgesneden_12_boven": _snede(0, 0.12, 0, 0),
    "bijgesneden_20_onder": _snede(0, 0, 0, 0.20),
    "bijgesneden_10_links": _snede(0.10, 0, 0, 0),
}


# --- meten ---------------------------------------------------------------------

def _rijen(hexen: list[str]) -> np.ndarray:
    return np.vstack([np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in hexen])


def _dichtste(vraag: np.ndarray, index: np.ndarray, eigenaar: np.ndarray) -> tuple[int, int]:
    """Kleinste afstand over alle vraaghashes en alle indexhashes."""
    d = _POPCOUNT[index[None, :, :] ^ vraag[:, None, :]].sum(axis=2)
    i, j = np.unravel_index(int(np.argmin(d)), d.shape)
    return int(eigenaar[j]), int(d[i, j])


def meet(index: list[Image.Image], buiten: list[Image.Image], *, drempel: int) -> dict:
    """Per methode en soort kopie: eigen beeld gevonden (goed), een ander
    beeld (fout) of niets; en per methode de valse treffers op de beelden
    buiten de index, met elke kopie erbij."""
    ih = [indexhashes(x, VERSIE) for x in index]
    indexsets = {
        "zonder": (_rijen([h[0] for h in ih]), np.arange(len(ih))),
        "met": (_rijen([x for h in ih for x in h]), np.repeat(np.arange(len(ih)), [len(h) for h in ih])),
    }
    welke = {"basis": (False, "zonder"), "gebied": (True, "zonder"), "uitsneden": (False, "met"), "beide": (True, "met")}
    gevonden = {m: {s: collections.Counter(goed=0, fout=0, niets=0) for s in KOPIEEN} for m in METHODEN}
    vals = {m: collections.Counter(vragen=0, treffers=0) for m in METHODEN}

    def vraag(beeld):
        h = vraaghashes(beeld, VERSIE)
        return _rijen(h[:1]), _rijen(h)

    for nummer, beeld in enumerate(index):
        for soort, maak in KOPIEEN.items():
            alleen_heel, met_gebied = vraag(maak(beeld))
            for methode in METHODEN:
                gebied, indexset = welke[methode]
                eigenaar, d = _dichtste(met_gebied if gebied else alleen_heel, *indexsets[indexset])
                gevonden[methode][soort]["niets" if d > drempel else "goed" if eigenaar == nummer else "fout"] += 1
    for beeld in buiten:
        for maak in (lambda x: x, *KOPIEEN.values()):
            alleen_heel, met_gebied = vraag(maak(beeld))
            for methode in METHODEN:
                gebied, indexset = welke[methode]
                _, d = _dichtste(met_gebied if gebied else alleen_heel, *indexsets[indexset])
                vals[methode]["vragen"] += 1
                vals[methode]["treffers"] += d <= drempel
    return {"gevonden": gevonden, "vals": vals}


def meet_embedding(index: list[Image.Image], buiten: list[Image.Image], vectoren) -> dict:
    """Dezelfde kopieën met een beeldembedding. `vectoren(beelden)` geeft per
    soort vector genormaliseerde rijen; elke soort krijgt haar eigen uitslag.
    De drempel is de hoogste gelijkenis die een beeld uit de eerste helft van
    `buiten` (of een kopie ervan) met de index haalt: daar valt dan geen
    enkele valse treffer. Geteld wordt op de tweede helft."""
    soorten = {**KOPIEEN, **SNEDEN}
    v_index = vectoren(index)
    helft = len(buiten) // 2

    def vragen(beelden):
        return vectoren([maak(b) for b in beelden for maak in (lambda x: x, *soorten.values())])

    ijk, test = vragen(buiten[:helft]), vragen(buiten[helft:])
    kopie = {soort: vectoren([maak(b) for b in index]) for soort, maak in soorten.items()}
    uit = {}
    for naam, vi in v_index.items():
        drempel = float((ijk[naam] @ vi.T).max()) + 1e-6
        hoog = (test[naam] @ vi.T).max(axis=1)
        gevonden = {s: collections.Counter(goed=0, fout=0, niets=0) for s in soorten}
        for soort in soorten:
            for nummer, rij in enumerate(kopie[soort][naam] @ vi.T):
                j = int(np.argmax(rij))
                gevonden[soort]["niets" if rij[j] < drempel else "goed" if j == nummer else "fout"] += 1
        uit[naam] = {"drempel": drempel, "gevonden": gevonden,
                     "vals": {"vragen": int(len(hoog)), "treffers": int((hoog >= drempel).sum())}}
    return uit


# De combinatie (PLAN #26.3, vastgelegd vóór de meting): PDQ met beeldgebied
# en uitsneden, DINOv2 CLS op het hele beeld, en twee verenigingen.
VARIANTEN = ("pdq", "dino", "pdq_of_dino", "pdq_of_dino_gebied")


class Routes:
    """De index voor de combinatie: PDQ met uitsneden en DINOv2 CLS."""

    def __init__(self, index: list[Image.Image], vectoren):
        ih = [indexhashes(x, VERSIE) for x in index]
        self.rijen = _rijen([x for h in ih for x in h])
        self.eigenaar = np.repeat(np.arange(len(ih)), [len(h) for h in ih])
        self.v_index = vectoren(index)["cls"]
        self.vectoren = vectoren

    def vraag(self, beelden: list[Image.Image]) -> list[tuple]:
        """Per beeld (pdq, dino, beste): PDQ als (beeld, afstand) over het hele
        beeld en het beeldgebied; DINOv2 als (beeld, gelijkenis) over het hele
        beeld, en `beste` ook over de uitsnede van het beeldgebied."""
        from doublecheck.beelduitsnede import beeldgebied

        gebieden = [beeldgebied(b) for b in beelden]
        uitsneden = [b.crop(g) for b, g in zip(beelden, gebieden) if g is not None]
        v = self.vectoren(list(beelden) + uitsneden)["cls"]
        heel = v[:len(beelden)] @ self.v_index.T
        van_gebied = iter(v[len(beelden):] @ self.v_index.T)
        uit = []
        for b, g, rij in zip(beelden, gebieden, heel):
            pdq = _dichtste(_rijen(vraaghashes(b, VERSIE)), self.rijen, self.eigenaar)
            j = int(np.argmax(rij))
            dino = beste = (j, float(rij[j]))
            if g is not None:
                rg = next(van_gebied)
                k = int(np.argmax(rg))
                if rg[k] > beste[1]:
                    beste = (k, float(rg[k]))
            uit.append((pdq, dino, beste))
        return uit


def routes(variant: str, r: tuple) -> tuple:
    """De (pdq, dino) die een variant gebruikt; `None` waar ze die route mist."""
    pdq, dino, beste = r
    return {"pdq": (pdq, None), "dino": (None, dino),
            "pdq_of_dino": (pdq, dino), "pdq_of_dino_gebied": (pdq, beste)}[variant]


def meet_combinatie(index: list[Image.Image], buiten: list[Image.Image], vectoren, *,
                    drempel_pdq: int) -> dict:
    """De vier varianten op dezelfde vragen. De DINOv2-drempels komen, als in
    §90, uit de eerste helft van `buiten`; de valse treffers uit de tweede."""
    soorten = {**KOPIEEN, **SNEDEN}
    r = Routes(index, vectoren)
    helft = len(buiten) // 2
    ijk = [x for b in buiten[:helft] for x in r.vraag([b] + [maak(b) for maak in soorten.values()])]
    test = [x for b in buiten[helft:] for x in r.vraag([b] + [maak(b) for maak in soorten.values()])]
    kopieen = [r.vraag([maak(b) for maak in soorten.values()]) for b in index]

    uit = {}
    for variant in VARIANTEN:
        scores = [routes(variant, x)[1][1] for x in ijk if routes(variant, x)[1] is not None]
        drempel_dino = (max(scores) + 1e-6) if scores else float("inf")

        def kies(x, variant=variant, drempel_dino=drempel_dino):
            return beslis(*routes(variant, x), drempel_pdq=drempel_pdq, drempel_dino=drempel_dino)

        gevonden = {s: collections.Counter(goed=0, fout=0, niets=0) for s in soorten}
        for nummer, rij in enumerate(kopieen):
            for soort, x in zip(soorten, rij):
                gekozen = kies(x)
                gevonden[soort]["niets" if gekozen is None else "goed" if gekozen == nummer else "fout"] += 1
        uit[variant] = {"drempel_dino": None if drempel_dino == float("inf") else drempel_dino,
                        "gevonden": gevonden,
                        "vals": {"vragen": len(test), "treffers": sum(kies(x) is not None for x in test)}}
    return uit


def _laad(pad: Path, max_zijde: int = 1024) -> Image.Image | None:
    try:
        beeld = Image.open(pad).convert("RGB")
    except Exception:
        return None
    beeld.thumbnail((max_zijde, max_zijde))
    return beeld if min(beeld.size) >= 64 else None


def m4fc_helften(max_aantal: int | None = None) -> tuple[list[tuple[str, Image.Image]], list[tuple[str, Image.Image]]]:
    """De beelden met hun bestandsnaam, in de vaste volgorde van §89 en §90:
    de eerste helft gaat de index in, de tweede blijft erbuiten."""
    paden = sorted(M4FC.glob("*.*"))
    random.Random(2603).shuffle(paden)
    paren = [(p.name, b) for p in paden if (b := _laad(p)) is not None][:max_aantal]
    helft = len(paren) // 2
    return paren[:helft], paren[helft:]


def main() -> None:
    import argparse
    import json

    from doublecheck.benchmark import upper_bound_95
    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="Kaders, stempels en uitsneden (#26.3)")
    parser.add_argument("--embedding", action="store_true", help="meet DINOv2-small in plaats van PDQ")
    parser.add_argument("--combinatie", action="store_true",
                        help="PDQ met beeldgebied, DINOv2 en hun vereniging op dezelfde vragen")
    parser.add_argument("--max", type=int, help="hooguit zoveel beelden (proef)")
    args = parser.parse_args()

    drempel = load_config().thresholds.image_same
    index_paren, buiten_paren = m4fc_helften(args.max)
    beelden = [b for _, b in index_paren + buiten_paren]
    helft = len(index_paren)
    if args.combinatie:
        from doublecheck.beeldembedding import BEELDMODEL, alle_vectoren

        print(f"{len(beelden)} M4FC-beelden: {helft} in de index, {len(beelden) - helft} erbuiten;"
              f" PDQ-drempel {drempel}; {BEELDMODEL}", flush=True)
        alles = meet_combinatie(beelden[:helft], beelden[helft:], alle_vectoren, drempel_pdq=drempel)
        print(f"\n{'kopie':<22}" + "".join(f"{v:>20}" for v in VARIANTEN))
        for soort in alles[VARIANTEN[0]]["gevonden"]:
            print(f"{soort:<22}" + "".join(
                f"{alles[v]['gevonden'][soort]['goed']:>14} (f{alles[v]['gevonden'][soort]['fout']})"
                for v in VARIANTEN), flush=True)
        for v in VARIANTEN:
            vals = alles[v]["vals"]
            d = alles[v]["drempel_dino"]
            print(f"{v}: DINOv2-drempel {'-' if d is None else f'{d:.4f}'}; valse treffers {vals['treffers']}"
                  f" op {vals['vragen']} (bovengrens {upper_bound_95(vals['treffers'], vals['vragen']):.2%})",
                  flush=True)
        Path("data/kadermeting").mkdir(parents=True, exist_ok=True)
        Path("data/kadermeting/uitslag-combinatie.json").write_text(json.dumps(alles, indent=1), encoding="utf-8")
        return
    if args.embedding:
        from doublecheck.beeldembedding import BEELDMODEL, alle_vectoren

        print(f"{len(beelden)} M4FC-beelden: {helft} in de index, {len(beelden) - helft} erbuiten; {BEELDMODEL}",
              flush=True)
        alles = meet_embedding(beelden[:helft], beelden[helft:], alle_vectoren)
        for pooling, uit in alles.items():
            v = uit["vals"]
            print(f"\n{pooling}: drempel {uit['drempel']:.4f} (hoogste gelijkenis op de eerste helft buiten de"
                  f" index); valse treffers op de tweede helft {v['treffers']} op {v['vragen']}"
                  f" (bovengrens {upper_bound_95(v['treffers'], v['vragen']):.2%})", flush=True)
            for soort, t in uit["gevonden"].items():
                print(f"  {soort:<22} goed {t['goed']:>4}  fout {t['fout']:>3}  niets {t['niets']:>4}", flush=True)
        Path("data/kadermeting").mkdir(parents=True, exist_ok=True)
        Path("data/kadermeting/uitslag-dinov2.json").write_text(json.dumps(alles, indent=1), encoding="utf-8")
        return
    print(f"{len(beelden)} M4FC-beelden: {helft} in de index, {len(beelden) - helft} erbuiten; drempel {drempel}",
          flush=True)
    uit = meet(beelden[:helft], beelden[helft:], drempel=drempel)
    for methode in METHODEN:
        v = uit["vals"][methode]
        print(f"\n{methode}: valse treffers {v['treffers']} op {v['vragen']}"
              f" (bovengrens {upper_bound_95(v['treffers'], v['vragen']):.2%})")
        for soort in KOPIEEN:
            t = uit["gevonden"][methode][soort]
            print(f"  {soort:<22} goed {t['goed']:>4}  fout {t['fout']:>3}  niets {t['niets']:>4}")
    Path("data/kadermeting").mkdir(parents=True, exist_ok=True)
    Path("data/kadermeting/uitslag.json").write_text(
        json.dumps({"drempel": drempel, "index": helft, "buiten": len(beelden) - helft,
                    "gevonden": uit["gevonden"], "vals": uit["vals"]}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
