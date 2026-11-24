"""De herordenaar: gaat deze tekst over dezelfde bewering als de vraag? (#25.23)

Een embedding zegt hoe dicht twee teksten bij elkaar liggen, en dat is te
weinig: een algemene note als "This photo is fake" ligt dicht bij elke
bewering over iets nieps (BENCHMARK §87). Een herordenaar krijgt vraag en
kandidaat tegelijk en beoordeelt of de kandidaat erover gaat. Ons NLI-model
kan dat niet: het vraagt of twee zinnen elkaar tegenspreken, en een goede note
spreekt haar bewering juist tegen (§44, §86).

Uitsluitend offline, als meetgereedschap, op een vastgezette revisie (DR6).
In het aanvraagpad pas met een release (B22), en dan uit de config.
"""

from __future__ import annotations

from functools import lru_cache

HERORDENAAR = "BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


@lru_cache(maxsize=1)
def _laad(versie: str):
    # Import hier: transformers en torch kosten seconden, en de gewone suite
    # raakt dit pad alleen als het model er al staat.
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    naam, _, revisie = versie.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(naam, revision=revisie or None)
    model = AutoModelForSequenceClassification.from_pretrained(naam, revision=revisie or None)
    model.eval()
    return tokenizer, model


def scores(paren: list[tuple[str, str]], versie: str = HERORDENAAR, batch: int = 16) -> list[float]:
    """Per paar (vraag, kandidaat) een getal tussen 0 en 1: hoe zeker de
    herordenaar is dat de kandidaat over de vraag gaat."""
    import torch

    tokenizer, model = _laad(versie)
    uit: list[float] = []
    with torch.no_grad():
        for start in range(0, len(paren), batch):
            deel = paren[start:start + batch]
            invoer = tokenizer([v for v, _ in deel], [k for _, k in deel], return_tensors="pt",
                               truncation=True, max_length=512, padding=True)
            uit += torch.sigmoid(model(**invoer).logits.view(-1).float()).tolist()
    return uit
