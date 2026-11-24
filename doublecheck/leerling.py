"""De eerste leerling (PLAN #31.4, E8.S4, B42).

Een classificeerder van één tekst: hoe zeker is het dat deze tekst onwaar of
misleidend is? Getraind op leerstof v2 (#31.3: labels alleen van redacties of
de bron, stijl tegen stijl), vanaf de herordenaar op de vastgezette revisie,
met de instellingen van lezer B. Een beeld leest de leerling als de bewering
die Haiku eruit haalde (#30.12); zonder bewering geen oordeel. In de dienst
doet een lokaal model dat lezen.

De drempel kiest de keuzerol van de basisset (alles uit de ontwikkelhelft dat
de leerling nooit zag): de laagste score waarbij hoogstens 1% van de ware
stukken en geen enkel kernfeit een vlag krijgt. Met die drempel de
toetshelft, alleen totalen, en de leraren op dezelfde stukken. Daarnaast echt
nieuws uit de toetshelft van #31.6, per taal: daar is elke vlag vals. Offline, op
openbare data; in de dienst pas per klasse achter de poort van B30.

    python -m doublecheck.leerling trainen [--naam leerling-2 --leerstof v3]
    python -m doublecheck.leerling scoren|lezen|meten [--naam leerling-2]
"""

from __future__ import annotations

import json
import time
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "leerling"
NAAM = "leerling-1"
ZAAD = 3011
MAX_VALS = 0.01  # hoogstens 1% van de ware stukken op de keuzerol
ECHT_PER_TAAL = 200  # echt nieuws uit de toetshelft, per bron en taal


def kies_drempel(rijen: list[dict], max_vals: float = MAX_VALS) -> float:
    """De laagste score als drempel waarbij hoogstens `max_vals` van de ware
    stukken en geen enkel kernfeit erop of erboven ligt."""
    waar = sorted((r["score"] for r in rijen if r["label"] == "waar"), reverse=True)
    kern = max((r["score"] for r in rijen if r["label"] == "waar" and r["bron"] == "n3-kern"), default=-1.0)
    toegestaan = int(max_vals * len(waar))
    # Strikt boven de (toegestaan+1)-ste hoogste ware score, en boven de hoogste kernscore.
    ondergrens = max(waar[toegestaan] if toegestaan < len(waar) else -1.0, kern)
    kandidaten = sorted({r["score"] for r in rijen if r["score"] > ondergrens})
    return kandidaten[0] if kandidaten else 1.0


def kernmarge(rijen: list[dict], drempel: float) -> float:
    """Hoe ver het hoogste kernfeit onder de drempel blijft (negatief: erboven)."""
    return drempel - max((r["score"] for r in rijen if r["bron"] == "n3-kern"), default=0.0)


def invoer(stuk: dict, beeldzinnen: dict[str, str]) -> str | None:
    """Wat de leerling leest: de tekst, of bij een beeld de bewering die Haiku
    eruit haalde (None als er geen is)."""
    if stuk["soort"] == "beeld":
        return beeldzinnen.get(stuk["sleutel"])
    return stuk.get("tekst")


def rol(stuk: dict) -> str:
    """Toets, les (de leerling zag het) of keuze (ontwikkelhelft, nooit gezien)."""
    from doublecheck.leerstof import mag_leren

    if stuk["helft"] == "toets":
        return "toets"
    return "les" if mag_leren(stuk) else "keuze"


def oordelen_bij(scores: dict[str, float], drempel: float, stukken: list[dict]) -> dict[str, str]:
    """Het oordeel van de leerling per stuk: onwaar vanaf de drempel; een stuk
    zonder score (een beeld zonder bewering) krijgt geen oordeel."""
    return {s["id"]: "onwaar" if scores.get(s["id"], -1.0) >= drempel else "geen-oordeel" for s in stukken}


def echt_steekproef(stukken: list[dict], per_taal: int = ECHT_PER_TAAL, zaad: int = ZAAD) -> list[dict]:
    """Echt nieuws (#31.6) uit de toetshelft: per bron en taal hooguit
    `per_taal`, willekeurig en telkens dezelfde. De ontwikkelhelft was leerstof."""
    import random
    from collections import defaultdict

    groepen: dict[tuple, list] = defaultdict(list)
    for s in stukken:
        if s["helft"] == "toets":
            groepen[(s["bron"], s["taal"])].append(s)
    rng = random.Random(zaad)
    uit = []
    for sleutel in sorted(groepen):
        groep = sorted(groepen[sleutel], key=lambda s: s["sleutel"])
        uit += rng.sample(groep, min(per_taal, len(groep)))
    return uit


def echt_telling(stukken: list[dict], scores: dict[str, float], drempel: float) -> dict:
    """Elke vlag op echt nieuws is vals: per bron het totaal met bovengrens,
    en per taal [n, vlag]."""
    from doublecheck.benchmark import upper_bound_95

    uit: dict = {}
    for s in stukken:
        if s["sleutel"] not in scores:
            continue
        b = uit.setdefault(s["bron"], {"n": 0, "vlag": 0, "per taal": {}})
        vlag = scores[s["sleutel"]] >= drempel
        b["n"] += 1
        b["vlag"] += vlag
        t = b["per taal"].setdefault(s["taal"], [0, 0])
        t[0] += 1
        t[1] += vlag
    for b in uit.values():
        b["bovengrens"] = round(upper_bound_95(b["vlag"], b["n"]), 4)
    return uit


def _echt() -> list[dict]:  # pragma: no cover - op de data van #31.6 en #31.5
    """Echt nieuws van #31.6 en, zodra opgehaald, Wikipedia over de onderwerpen
    van het nepnieuws (#31.5)."""
    from doublecheck import echtnieuws, onderwerp

    return echt_steekproef(echtnieuws.lees("wikinews") + echtnieuws.lees("wikipedia") + onderwerp.lees_stukken())


# --- met het model ----------------------------------------------------------------

def trainen(naam: str = NAAM, leerstof: Path | None = None, lagen: int = 6, rondes: int = 1, batch: int = 8,
            lr: float = 2e-5, lengte: int = 384, zaad: int = ZAAD) -> dict:  # pragma: no cover - met het model
    """Zoals `artikellezer.trainen` (lezer B), maar met één tekst per voorbeeld.
    Na elke 100 stappen het tempo en de verwachte totale duur in de log (PO:
    "Meet de eerste 100 stappen en stop als het tempo niet klopt")."""
    import collections
    import random

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck.artikellezer import _apparaat, lezerversie
    from doublecheck.herordenaar import HERORDENAAR
    from doublecheck.leerstof import BESTAND_V2, _jsonl

    torch.manual_seed(zaad)
    basis, _, revisie = HERORDENAAR.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(basis, revision=revisie)
    model = AutoModelForSequenceClassification.from_pretrained(basis, revision=revisie, attn_implementation="sdpa",
                                                               hidden_dropout_prob=0.0,
                                                               attention_probs_dropout_prob=0.0)
    for n, param in model.named_parameters():
        bovenin = any(f"encoder.layer.{i}." in n for i in range(model.config.num_hidden_layers - lagen,
                                                                  model.config.num_hidden_layers))
        param.requires_grad = bovenin or n.startswith("classifier")
    apparaat = _apparaat()
    model.to(apparaat).train()
    leerstof = leerstof or BESTAND_V2
    les = _jsonl(leerstof)
    optim = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    verlies_fn = torch.nn.BCEWithLogitsLoss()
    rnd = random.Random(zaad)  # de volgorde van de voorbeelden; de kop van de herordenaar is al getraind
    totaal_stappen = rondes * ((len(les) + batch - 1) // batch)
    print(f"leerstof {leerstof.name}: {len(les)} voorbeelden, {totaal_stappen} stappen op {apparaat}", flush=True)
    stappen, t0, t_blok = 0, time.time(), time.time()
    for ronde in range(rondes):
        rnd.shuffle(les)
        for start in range(0, len(les), batch):
            deel = les[start:start + batch]
            invoer_ = tokenizer([r["tekst"] for r in deel], return_tensors="pt", truncation=True, max_length=lengte,
                                padding=True).to(apparaat)
            doelen = torch.tensor([float(r["label"]) for r in deel], device=apparaat)
            verlies = verlies_fn(model(**invoer_).logits.view(-1).float(), doelen)
            optim.zero_grad()
            verlies.backward()
            optim.step()
            stappen += 1
            if stappen % 100 == 0:
                blok = time.time() - t_blok
                verwacht = (time.time() - t0) / stappen * totaal_stappen / 60
                print(f"  ronde {ronde + 1}, stap {stappen} van {totaal_stappen}: verlies {float(verlies.detach()):.4f},"
                      f" 100 stappen in {blok:.0f} s, verwacht totaal {verwacht:.0f} min", flush=True)
                t_blok = time.time()
                if apparaat == "mps":
                    torch.mps.empty_cache()
    model.train(False).to("cpu")
    UIT.mkdir(parents=True, exist_ok=True)
    nieuw = UIT / f"{naam}-nieuw"
    model.save_pretrained(nieuw)
    tokenizer.save_pretrained(nieuw)
    versie = lezerversie(nieuw, naam)
    meta = {"basis": HERORDENAAR, "lagen": lagen, "rondes": rondes, "batch": batch, "lr": lr, "lengte": lengte,
            "aandacht": "sdpa, zonder dropout", "zaad": zaad, "leerstof": leerstof.name, "voorbeelden": len(les),
            "onwaar": sum(r["label"] for r in les),
            "bronnen": {f"{b}/{lb}": n for (b, lb), n in collections.Counter((r["bron"], r["label"]) for r in les).items()},
            "minuten": round((time.time() - t0) / 60, 1), "versie": versie}
    (nieuw / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    nieuw.rename(UIT / versie)
    koppeling = UIT / naam
    koppeling.unlink(missing_ok=True)
    koppeling.symlink_to(versie)
    return meta


def _beeldzinnen() -> dict[str, str]:  # pragma: no cover - op de data van #30.12
    """Per beeld (sleutel) de bewering die Haiku eruit haalde; de tweede vraag
    gaat voor als die er is."""
    from doublecheck import bewering

    id_van = {i["sleutel"]: i["id"] for i in bewering.items()}
    zin = {**bewering._zinnen("v1"), **bewering._zinnen("v2")}
    return {s: zin[i] for s, i in id_van.items() if i in zin}


def scoren(naam: str = NAAM, batch: int = 32, lengte: int = 384) -> Path:  # pragma: no cover - met het model
    """De score van de leerling op elk stuk van de basisset dat hij kan lezen
    en niet als les zag, en op de steekproef van echt nieuws. Hervatbaar:
    wat al een score heeft, blijft staan."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck import basisset
    from doublecheck.artikellezer import _apparaat

    map_ = (UIT / naam).resolve()
    pad = map_ / "scores.jsonl"
    al = set(_scores(naam)) if pad.exists() else set()
    tokenizer = AutoTokenizer.from_pretrained(map_)
    model = AutoModelForSequenceClassification.from_pretrained(map_).to(_apparaat()).train(False)
    beeldzinnen = _beeldzinnen()
    te_lezen = [(s["id"], t) for s in basisset.lees() if rol(s) != "les" and (t := invoer(s, beeldzinnen))]
    te_lezen += [(s["sleutel"], s["tekst"]) for s in _echt()]
    te_lezen = [x for x in te_lezen if x[0] not in al]
    te_lezen.sort(key=lambda x: len(x[1]))  # minder opvulling per portie, dezelfde scores
    print(f"{naam}: {len(te_lezen)} te scoren, {len(al)} al gedaan", flush=True)
    with torch.no_grad(), pad.open("a", encoding="utf-8") as uit:
        for start in range(0, len(te_lezen), batch):
            deel = te_lezen[start:start + batch]
            invoer_ = tokenizer([t for _, t in deel], return_tensors="pt", truncation=True, max_length=lengte,
                                padding=True).to(model.device)
            scores = torch.sigmoid(model(**invoer_).logits.view(-1).float()).cpu().tolist()
            uit.writelines(json.dumps({"id": i, "score": round(s, 6)}) + "\n" for (i, _), s in zip(deel, scores))
            if model.device.type == "mps" and start % (batch * 50) == 0:
                torch.mps.empty_cache()
    return pad


# --- meten ------------------------------------------------------------------------

def _scores(naam: str = NAAM) -> dict[str, float]:  # pragma: no cover - leest de scores
    from doublecheck.leerstof import _jsonl

    return {r["id"]: r["score"] for r in _jsonl((UIT / naam).resolve() / "scores.jsonl")}


def _gemeten(naam: str = NAAM) -> tuple[list[dict], dict[str, str], float]:  # pragma: no cover - op de data
    from doublecheck import basisset

    stukken = [s for s in basisset.lees() if rol(s) != "les"]
    scores = _scores(naam)
    keuze = [{"score": scores[s["id"]], "label": s["label"], "bron": s["bron"]}
             for s in stukken if rol(s) == "keuze" and s["id"] in scores]
    drempel = kies_drempel(keuze)
    return stukken, oordelen_bij(scores, drempel, stukken), drempel


def lezen(naam: str = NAAM) -> None:  # pragma: no cover - CLI
    """De gevlagde webtekst zonder label, om te lezen vóór de telling."""
    from doublecheck.leraar import _lees_labels

    stukken, oordelen, drempel = _gemeten(naam)
    labels = _lees_labels()
    open_ = [s for s in stukken if s["soort"] == "webtekst" and oordelen[s["id"]] == "onwaar"
             and s["sleutel"] not in labels]
    print(f"drempel {drempel}; {len(open_)} gevlagde webteksten zonder label")
    for s in open_:
        print(json.dumps({"sleutel": s["sleutel"], "helft": s["helft"], "tekst": s["tekst"][:400]}, ensure_ascii=False))


def meten(naam: str = NAAM) -> dict:  # pragma: no cover - op de data
    """De telling van de leerling en, op dezelfde stukken, van de leraren."""
    from doublecheck import basisset, leraar

    stukken, oordelen, drempel = _gemeten(naam)
    labels = leraar._lees_labels()
    scores = _scores(naam)
    uit = {"versie": (UIT / naam).resolve().name, "drempel": drempel,
           "kernmarge": round(kernmarge([{"score": scores[s["id"]], "bron": s["bron"]} for s in stukken
                                         if s["id"] in scores], drempel), 6),
           "leerling, alles buiten de les": leraar.telling(stukken, oordelen, labels),
           "echt nieuws, toetshelft": echt_telling(_echt(), scores, drempel)}
    alle = basisset.lees()
    for model in leraar.MODELLEN:
        ids = {s["id"] for s in leraar.set_van(model, alle)}
        zelfde = [s for s in stukken if s["id"] in ids]
        uit[f"op de set van {model}"] = {"n": len(zelfde),
                                          "leerling": leraar.telling(zelfde, oordelen, labels),
                                          model: leraar.telling(zelfde, leraar.oordelen(model), labels)}
    pad = (UIT / naam).resolve() / "meting.json"
    pad.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De eerste leerling (#31.4)")
    parser.add_argument("stap", choices=("trainen", "scoren", "lezen", "meten"))
    parser.add_argument("--naam", default=NAAM)
    parser.add_argument("--zaad", type=int, default=ZAAD, help="trainen: een ander zaad meet de ruisvloer (#31.5)")
    parser.add_argument("--leerstof", choices=("v2", "v3", "v4"), default="v2")
    args = parser.parse_args()
    if args.stap == "trainen":
        from doublecheck.leerstof import BESTAND_V2, BESTAND_V3, BESTAND_V4

        pad = {"v3": BESTAND_V3, "v4": BESTAND_V4}.get(args.leerstof, BESTAND_V2)
        print(json.dumps(trainen(args.naam, pad, zaad=args.zaad), indent=1), flush=True)
    elif args.stap == "scoren":
        print(scoren(args.naam))
    elif args.stap == "lezen":
        lezen(args.naam)
    else:
        print(json.dumps(meten(args.naam), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
