"""Een sterker stance-model, gemeten (PLAN.md #25.32).

Vastgelegd vóór het meten (PLAN #25.32): twee kandidaten tegen het huidige
model, met dezelfde drempel, dezelfde vensters en dezelfde poort; alleen het
model wisselt. Vier metingen: de proefset van §56, de 60 modeluitvoeren van
§59, de mC4-stukken van §97 met een zin boven de poort, en een verse
steekproef uit mC4 langs dezelfde weg. Elke vlag op mC4 wordt gelabeld zonder
te weten welk model hem gaf.

De kandidaten leveren geen `tokenizer.json`, en `sentencepiece` staat niet in
de omgeving. Hun SentencePiece-bestand is byte voor byte gelijk aan dat van
bge-m3, dus de meting gebruikt die snelle tokenizer; `zelfde_bestand`
controleert dat bij elke lading.

    python -m doublecheck.stancemeting kandidaten --map data/stiltetoets
    python -m doublecheck.stancemeting kandidaten --map data/stiltetoets-vers
    python -m doublecheck.stancemeting meten|tellen
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODELLEN = {
    "mdeberta": "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7@b5113eb38ab63efdd7f280f8c144ea8b13f978ce",
    "joeddav": "joeddav/xlm-roberta-large-xnli@b227ee8435ceadfa86dc1368a34254e2838bf242",
    "vicgalle": "vicgalle/xlm-roberta-large-xnli-anli@85981da85b85045fecd6e81e501767de7da370eb",
}
HUIDIG = "mdeberta"
VOORKEUR = ["joeddav", "vicgalle"]          # bij gelijkspel: joeddav, breder gebruikt
UIT = Path("data/stance")
LABELS = Path("docs/steekproeven/25.32-stance-vlaggen.json")
KAARTEN = (Path("data/stiltetoets"), Path("data/stiltetoets-vers"))


class Weigering(Exception):
    pass


def label(entailment: float, contradiction: float, drempel: float) -> str:
    """Dezelfde regel als de batchcontrole (controle.py)."""
    if entailment >= drempel:
        return "beweert"
    if contradiction >= drempel:
        return "weerlegt"
    return "overig"


def proefset_uitslag(paren: list[tuple[str, str]]) -> dict:
    """(verwacht, gekregen) per proefsetversie."""
    return {
        "beweert_goed": sum(v == "beweert" and g == "beweert" for v, g in paren),
        "missers": sum(v == "beweert" and g != "beweert" for v, g in paren),
        "fouten": sum(v != "beweert" and g == "beweert" for v, g in paren),
        "n": len(paren),
    }


def kies(uitslagen: dict[str, dict], *, huidig: str, voorkeur: list[str]) -> dict:
    """Het criterium van PLAN #25.32."""
    h = uitslagen[huidig]
    gehaald = []
    for naam in voorkeur:
        u = uitslagen[naam]
        geen_verlies = (u["beweert_terecht"]["proefset"] >= h["beweert_terecht"]["proefset"]
                        and u["beweert_terecht"]["modeluitvoer"] >= h["beweert_terecht"]["modeluitvoer"])
        proef = u["proefset"]["fouten"] <= h["proefset"]["fouten"]
        minder_vals = u["mc4"]["vals"] < h["mc4"]["vals"] and u["mc4"]["terecht"] >= h["mc4"]["terecht"]
        if geen_verlies and proef and minder_vals:
            gehaald.append(naam)
    volgorde = sorted(gehaald, key=lambda n: (uitslagen[n]["vers"]["vals"], -uitslagen[n]["mc4"]["terecht"],
                                              voorkeur.index(n)))
    return {"gehaald": gehaald, "winnaar": volgorde[0] if volgorde else None}


def zelfde_bestand(a: Path, b: Path) -> bool:
    def digest(p: Path) -> str:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    return digest(a) == digest(b)


def _snapshot(model: str) -> Path:
    """De lokale map van precies deze revisie. Gedownload zijn alleen de
    safetensors, de config en de tokenizerbestanden; `snapshot_download`
    offline noemt dat onvolledig, dus zoeken we de map via de config."""
    from huggingface_hub import try_to_load_from_cache

    naam, _, revisie = model.partition("@")
    pad = try_to_load_from_cache(naam, "config.json", revision=revisie or None)
    if not isinstance(pad, str):
        raise Weigering(f"{model} staat niet lokaal; download het eerst (PO-besluit)")
    return Path(pad).parent


def scorer(model: str):
    """(premise, hypothese) -> (entailment, contradiction), zoals
    `nli.stance_scores`, met de tokenizer van bge-m3 als het model er zelf
    geen snelle levert en het SentencePiece-bestand gelijk is."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, XLMRobertaTokenizerFast

    from doublecheck.config import load_config

    pad = _snapshot(model)
    if (pad / "tokenizer.json").exists():
        tokenizer = AutoTokenizer.from_pretrained(pad)
    else:
        m3 = _snapshot(load_config().model_versions.text_embedding.split("+")[0])
        if not zelfde_bestand(pad / "sentencepiece.bpe.model", m3 / "sentencepiece.bpe.model"):
            raise Weigering(f"{model}: geen tokenizer.json, en het SentencePiece-bestand wijkt af van bge-m3")
        tokenizer = XLMRobertaTokenizerFast(tokenizer_file=str(m3 / "tokenizer.json"))
    netwerk = AutoModelForSequenceClassification.from_pretrained(pad)
    netwerk.eval()
    labels = {l.lower(): int(i) for i, l in netwerk.config.id2label.items()}

    def stance(premise: str, hypothese: str) -> tuple[float, float]:
        with torch.no_grad():
            invoer = tokenizer([premise], [hypothese], return_tensors="pt", truncation=True,
                               padding=True, max_length=384)
            kansen = torch.softmax(netwerk(**invoer).logits, dim=-1)[0]
        return float(kansen[labels["entailment"]]), float(kansen[labels["contradiction"]])

    return stance


def _vlaggen(rapport) -> list[dict]:
    return [{"doc": d.document_id, "claim_id": t.claim_id, "zin": t.zin, "claim_tekst": t.claim_tekst,
             "entailment": t.entailment} for d in rapport.documenten for t in d.beweert]


def main() -> None:
    import argparse
    import os

    import numpy as np
    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.controle import controleer_teksten
    from doublecheck.storage import connect
    from doublecheck.variantenbatch import lees_regels, lees_vectoren
    from doublecheck.vlaggenmeting import MARGE

    parser = argparse.ArgumentParser(description="Een sterker stance-model (PLAN #25.32)")
    parser.add_argument("stap", choices=("kandidaten", "meten", "tellen"))
    parser.add_argument("--map", default=str(KAARTEN[0]))
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)
    config = load_config()
    UIT.mkdir(parents=True, exist_ok=True)
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))

    if args.stap == "kandidaten":
        from doublecheck.stiltetoets import ondergrens, voorselectie

        map_ = Path(args.map)
        rijen = lees_regels(map_)
        if not (map_ / "hoogste.npy").exists():
            versie = config.model_versions.text_embedding
            _, matrix = lees_vectoren(map_, versie)
            if len(matrix) < len(rijen):
                raise Weigering(f"{len(matrix)} van {len(rijen)} stukken embed; eerst `stiltetoets embedden`")
            hoogste, _ = voorselectie(conn, matrix, versie, ondergrens(config.thresholds))
            np.save(map_ / "hoogste.npy", hoogste)
        hoogste = np.load(map_ / "hoogste.npy")
        boven = np.nonzero(hoogste >= config.thresholds.screening_poort - MARGE)[0]
        documenten = [(rijen[i]["claim_id"], rijen[i]["varianten"][0]["tekst"]) for i in boven]
        print(f"{len(rijen)} stukken; {len(documenten)} door de batchcontrole zonder stance", flush=True)
        rapport = controleer_teksten(conn, documenten, config=config, stance=lambda p, h: (0.0, 0.0))
        met = [{"stuk_id": d.document_id, "tekst": dict(documenten)[d.document_id]}
               for d in rapport.documenten if d.treffers]
        (map_ / "stance-kandidaten.json").write_text(json.dumps(met, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"stukken met een zin boven de poort: {len(met)}", flush=True)
        return

    if args.stap == "meten":
        proef = json.loads(Path("docs/steekproeven/21.1-stance-proefset.json").read_text(encoding="utf-8"))["proefset"]
        uitvoer = json.loads(Path("docs/steekproeven/21.3-echte-data.json").read_text(encoding="utf-8"))["modeluitvoer"]
        kaarten = {m.name: json.loads((m / "stance-kandidaten.json").read_text(encoding="utf-8")) for m in KAARTEN}
        for naam, model in MODELLEN.items():
            stance = scorer(model)
            drempel = config.thresholds.stance_entailment
            proefparen = [(versie, label(*stance(item[versie], item["claim"]), drempel), item["taal"], item["claim"])
                          for item in proef for versie in ("beweert", "weerlegt", "bespreekt")]
            uit = {"model": model, "proefset": proefparen}
            rapport = controleer_teksten(conn, [(m["id"], m["tekst"]) for m in uitvoer], config=config, stance=stance)
            uit["modeluitvoer"] = _vlaggen(rapport)
            for kaart, stukken in kaarten.items():
                rapport = controleer_teksten(conn, [(s["stuk_id"], s["tekst"]) for s in stukken],
                                             config=config, stance=stance)
                uit[kaart] = _vlaggen(rapport)
            (UIT / f"{naam}.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(naam, {k: len(v) for k, v in uit.items() if isinstance(v, list)}, flush=True)
        # Blind te labelen: elke vlag op mC4 van elk model, zonder model erbij.
        alle = {}
        for naam in MODELLEN:
            uit = json.loads((UIT / f"{naam}.json").read_text(encoding="utf-8"))
            for kaart in kaarten:
                for v in uit[kaart]:
                    alle[f"{v['doc']}|{v['claim_id']}"] = {"zin": v["zin"], "claim": v["claim_tekst"]}
        (UIT / "te-labelen.json").write_text(json.dumps(dict(sorted(alle.items())), ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print(f"te labelen: {len(alle)} vlaggen in {UIT / 'te-labelen.json'}")
        return

    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}
    uitvoer = json.loads(Path("docs/steekproeven/21.3-echte-data.json").read_text(encoding="utf-8"))["modeluitvoer"]
    bedoeld = {m["id"]: m["claim_id"] for m in uitvoer if m["groep"] == "beweert"}
    uitslagen = {}
    for naam in MODELLEN:
        uit = json.loads((UIT / f"{naam}.json").read_text(encoding="utf-8"))
        ontbreekt = [f"{v['doc']}|{v['claim_id']}" for k in ("stiltetoets", "stiltetoets-vers") for v in uit[k]
                     if labels.get(f"{v['doc']}|{v['claim_id']}") not in ("terecht", "vals")]
        if ontbreekt:
            raise Weigering(f"{len(ontbreekt)} vlaggen zonder label (bijvoorbeeld {ontbreekt[:3]}); label in {LABELS}")
        proefset = proefset_uitslag([(v, g) for v, g, *_ in uit["proefset"]])
        model_terecht = sum(bedoeld.get(v["doc"]) == v["claim_id"] for v in uit["modeluitvoer"])

        def telling(kaarten):
            vlag = [labels[f"{v['doc']}|{v['claim_id']}"] for k in kaarten for v in uit[k]]
            return {"terecht": vlag.count("terecht"), "vals": vlag.count("vals")}

        uitslagen[naam] = {
            "proefset": proefset,
            "beweert_terecht": {"proefset": proefset["beweert_goed"], "modeluitvoer": model_terecht},
            "modeluitvoer": {"terecht": model_terecht, "vals": len(uit["modeluitvoer"]) - model_terecht},
            "oud": telling(["stiltetoets"]), "vers": telling(["stiltetoets-vers"]),
            "mc4": telling(["stiltetoets", "stiltetoets-vers"]),
        }
    keuze = kies(uitslagen, huidig=HUIDIG, voorkeur=VOORKEUR)
    (UIT / "uitslag.json").write_text(json.dumps({"uitslagen": uitslagen, "keuze": keuze}, ensure_ascii=False,
                                                 indent=1), encoding="utf-8")
    for naam, u in uitslagen.items():
        print(naam, json.dumps(u, ensure_ascii=False))
    print("keuze:", keuze)


if __name__ == "__main__":
    main()
