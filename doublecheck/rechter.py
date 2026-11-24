"""De rechter in het aanvraagpad (PLAN #30.3, B36).

Tussen breed zoeken en `categorize`: de rechter leest de bovenste
kandidaten waarvan de gelijkenis boven de vloer ligt, geeft elk een score
voor *zelfde bewering*, en zet ze op die volgorde. `categorize` blijft de
enige plek die de categorie zet (DR4); de score is daar de matchdrempel voor
tekst. Een kandidaat die de rechter niet las, kan met de rechter aan nooit
`matched` worden.

Lokaal, nooit een externe dienst (DR3). De gewichten dragen hun versie als
hash (DR6): passen ze niet bij de config, dan weigert hij.
"""

from __future__ import annotations

import dataclasses
import hashlib
from functools import lru_cache
from pathlib import Path

from doublecheck.search import Candidate


class Weigering(RuntimeError):
    pass


# Een meting (de zeef) kan hier meekijken wat de rechter las: per vraag een
# lijst (claim_id, gelijkenis, score, tegenspraak). Nooit tekst (DR3); in de
# dienst staat hij uit.
waarnemer = None


def versie(map_: Path | str) -> str:
    """`rechter-d@<hash>` uit de gewichten zelf: een andere training is een
    andere motor (DR6)."""
    h = hashlib.sha256()
    for pad in sorted(Path(map_).glob("*.safetensors")):
        # In stukken: in één keer lezen zette 2,1 GB extra in het geheugen
        # van de werker, bovenop de gewichten zelf.
        with pad.open("rb") as f:
            while stuk := f.read(1 << 24):
                h.update(stuk)
    return f"rechter-d@{h.hexdigest()[:12]}"


def controleer_versie(map_: str, model: str) -> None:
    gevonden = versie(map_)
    if gevonden != model:
        raise Weigering(f"de gewichten in {map_} zijn {gevonden}, de config verwacht {model} (DR6)")


@lru_cache(maxsize=1)
def _laad(map_: str, model: str):  # pragma: no cover - met het model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    controleer_versie(map_, model)
    tokenizer = AutoTokenizer.from_pretrained(map_)
    return tokenizer, AutoModelForSequenceClassification.from_pretrained(map_).eval()


def scores(vraag: str, teksten: list[str], map_: str, model: str) -> list[float]:  # pragma: no cover - met het model
    import torch

    tokenizer, net = _laad(map_, model)
    with torch.no_grad():
        invoer = tokenizer([vraag] * len(teksten), teksten, return_tensors="pt", truncation=True,
                           max_length=256, padding=True)
        return torch.sigmoid(net(**invoer).logits.view(-1).float()).tolist()


def herorden(conn, config, vraag: str, kandidaten: list[Candidate], scorer=None,
             tegenspraak=None) -> list[Candidate]:
    """De gelezen kandidaten op de volgorde van de rechter, daarna de rest in
    hun eigen volgorde. Met de rechter uit: ongewijzigd. `tegenspraak` (de
    getallen- en ontkenningsregel per kandidaattekst) gaat alleen naar de
    waarnemer, zodat een meting precies kan narekenen wat `categorize` doet."""
    if not config.rechter.aan:
        return kandidaten
    vloer = config.thresholds.rechter_vloer
    te_lezen = [k for k in kandidaten[:config.rechter.diepte] if k.similarity >= vloer]
    if not te_lezen:
        return kandidaten
    plaats = ",".join("?" * len(te_lezen))
    teksten = dict(conn.execute(f"SELECT claim_id, canonical_text FROM claim WHERE claim_id IN ({plaats})",
                                [k.claim_id for k in te_lezen]))
    te_lezen = [k for k in te_lezen if k.claim_id in teksten]
    if scorer is None:
        def scorer(v, t):
            return scores(v, t, config.rechter.pad, config.rechter.model)
    uitslag = scorer(vraag, [teksten[k.claim_id] for k in te_lezen])
    if waarnemer is not None:
        waarnemer([(k.claim_id, round(float(k.similarity), 4), round(float(s), 4),
                    None if tegenspraak is None else bool(tegenspraak(teksten[k.claim_id])))
                   for k, s in zip(te_lezen, uitslag)])
    gelezen = volgorde([dataclasses.replace(k, rechter=s) for k, s in zip(te_lezen, uitslag)], config.thresholds)
    ids = {k.claim_id for k in gelezen}
    return gelezen + [k for k in kandidaten if k.claim_id not in ids]


def volgorde(gelezen: list[Candidate], thresholds) -> list[Candidate]:
    """De gelezen kandidaten op hun marge boven de eigen drempel van de
    rechter (`categorize.rechterdrempel`): wie het verst erboven zit, eerst."""
    from doublecheck.categorize import rechterdrempel

    return sorted(gelezen, key=lambda k: -(k.rechter - rechterdrempel(k.similarity, thresholds)))


def oordeel(kandidaat: Candidate, config) -> float | None:
    """Wat `categorize` als rechterscore krijgt: niets met de rechter uit,
    en nul voor een kandidaat die hij niet las."""
    if not config.rechter.aan:
        return None
    return kandidaat.rechter if kandidaat.rechter is not None else 0.0
