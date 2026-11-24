"""Kandidaat D: de herordenaar bijgetraind als rechter (PLAN #30.3, B36, B37).

`bge-reranker-v2-m3` weet of een tekst over de vraag gaat, niet of hij
hetzelfde beweert; een rolwissel scoort bij hem even hoog als een parafrase.
Hier leert hij het verschil, op het lesdeel van de rechterset: *zelfde* is
1, al het andere 0. Licht, volgens B37: alleen de bovenste lagen en de kop
bewegen, op de Mac (MPS). Het resultaat krijgt een versie uit de hash van
zijn gewichten (DR6) en blijft buiten git, in `data/rechterset/`.

    python -m doublecheck.rechtertraining [--lagen 6] [--rondes 2] [--echt-gewicht 3]
"""

from __future__ import annotations

import json
import random
from collections import Counter

from doublecheck.rechtermeting import lees_paren, lesstof
from doublecheck.rechterset import UIT

MAP = UIT / "rechter-d"
ZAAD = 3008


def doel(label: str) -> float:
    return 1.0 if label == "zelfde" else 0.0


def trainingsparen(paren: list[dict], echt_gewicht: int = 1) -> list[tuple[dict, float]]:
    """Het lesdeel; een echt paar (niet door Haiku geschreven) telt `echt_gewicht` keer."""
    return [(p, doel(p["label"])) for p in lesstof(paren)
            for _ in range(1 if p.get("bron") == "gemaakt" else echt_gewicht)]


def versie(map_=MAP) -> str:  # pragma: no cover - leest de gewichten
    from doublecheck.rechter import versie as _versie

    return _versie(map_)


def trainen(lagen: int = 6, rondes: int = 2, batch: int = 16, lr: float = 2e-5, echt_gewicht: int = 1) -> dict:  # pragma: no cover - met het model
    import torch

    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck.herordenaar import HERORDENAAR
    from doublecheck.rechtermeting import _apparaat

    torch.manual_seed(ZAAD)
    naam, _, revisie = HERORDENAAR.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(naam, revision=revisie)
    # "eager": de snelle aandacht op MPS kent geen dropout, en zonder dropout
    # leert hij niet zoals bedoeld; de gewichten zijn dezelfde.
    model = AutoModelForSequenceClassification.from_pretrained(naam, revision=revisie, attn_implementation="eager")
    for naam, param in model.named_parameters():
        bovenin = any(f"encoder.layer.{i}." in naam for i in range(model.config.num_hidden_layers - lagen,
                                                                     model.config.num_hidden_layers))
        param.requires_grad = bovenin or naam.startswith("classifier")
    apparaat = _apparaat()
    model.to(apparaat).train()
    les = trainingsparen(lees_paren(), echt_gewicht)
    optim = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    verlies_fn = torch.nn.BCEWithLogitsLoss()
    rnd = random.Random(ZAAD)
    stappen = 0
    for ronde in range(rondes):
        rnd.shuffle(les)
        totaal = 0.0
        for start in range(0, len(les), batch):
            deel = les[start:start + batch]
            invoer = tokenizer([p["vraag"] for p, _ in deel], [p["kandidaat"] for p, _ in deel], return_tensors="pt",
                               truncation=True, max_length=192, padding=True).to(apparaat)
            doelen = torch.tensor([d for _, d in deel], device=apparaat)
            verlies = verlies_fn(model(**invoer).logits.view(-1).float(), doelen)
            optim.zero_grad()
            verlies.backward()
            optim.step()
            totaal += float(verlies) * len(deel)
            stappen += 1
            if stappen % 50 == 0:
                print(f"  ronde {ronde + 1}, stap {stappen}: verlies {float(verlies):.4f}", flush=True)
        print(f"ronde {ronde + 1}: gemiddeld verlies {totaal / len(les):.4f}", flush=True)
    model.eval().to("cpu")
    # Elke training in een eigen map met haar versie; `rechter-d` wijst naar
    # de nieuwste. Een volgende training overschrijft nooit een vorige.
    nieuw = UIT / "rechter-d-nieuw"
    model.save_pretrained(nieuw)
    tokenizer.save_pretrained(nieuw)
    v = versie(nieuw)
    meta = {"basis": HERORDENAAR, "lagen": lagen, "rondes": rondes, "batch": batch, "lr": lr, "zaad": ZAAD,
            "echt_gewicht": echt_gewicht, "bronnen": dict(Counter(p.get("bron") for p, _ in les)),
            "paren": len(les), "positief": sum(d for _, d in les), "versie": v}
    (nieuw / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    nieuw.rename(UIT / v)
    if MAP.is_symlink() or MAP.exists():
        MAP.unlink()
    MAP.symlink_to(v)
    return meta


def main() -> None:  # pragma: no cover
    import argparse

    import torch
    from threadpoolctl import threadpool_limits

    parser = argparse.ArgumentParser(description="De herordenaar bijgetraind als rechter (PLAN #30.3, D)")
    parser.add_argument("--lagen", type=int, default=6)
    parser.add_argument("--rondes", type=int, default=2)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--echt-gewicht", type=int, default=1, help="hoe vaak een echt paar telt")
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)
    print(trainen(args.lagen, args.rondes, echt_gewicht=args.echt_gewicht))


if __name__ == "__main__":
    main()
