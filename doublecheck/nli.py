"""Relatie-oordeel met een lokaal NLI-model (E3.S4-AC3).

**Uitsluitend offline.** Dit model hoort niet in het aanvraagpad: het kost
~525 ms per paar tegenover een budget van 500 ms, en het is bovendien te grof
voor het onderscheid dat daar nodig is — één richting wijst 100% van de
legitieme inkortingen af (BENCHMARK.md §15d). Waar het wél thuishoort is
clustering, dat offline draait en waar het alleen als *veto* wordt gebruikt.

Het model draait lokaal (DR3); zijn versie komt uit config (DR6).
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=2)
def _laad(model_version: str):
    # Import hier: transformers en torch kosten seconden om te laden, en de
    # gewone suite raakt dit pad nooit.
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # `model@revisie` pint de gewichten vast (#25.32, DR6); een kale naam
    # laadt zoals altijd.
    naam, _, revisie = model_version.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(naam, revision=revisie or None)
    model = AutoModelForSequenceClassification.from_pretrained(naam, revision=revisie or None)
    model.eval()
    labels = {label.lower(): index for index, label in model.config.id2label.items()}
    if "contradiction" not in labels:
        raise ValueError(
            f"model {model_version!r} kent geen 'contradiction'-label:"
            f" {model.config.id2label}"
        )
    return tokenizer, model, labels["contradiction"]


def contradiction_score(a: str, b: str, model_version: str) -> float:
    """Hoogste tegenspraak-score over beide richtingen.

    Tegenspraak is symmetrisch bedoeld — als A het tegendeel van B beweert,
    doet B dat ook van A — maar het model is dat niet, dus beide richtingen
    worden gemeten en de sterkste telt.
    """
    import torch

    tokenizer, model, index = _laad(model_version)
    with torch.no_grad():
        invoer = tokenizer(
            [a, b], [b, a], return_tensors="pt", truncation=True,
            padding=True, max_length=128,
        )
        kansen = torch.softmax(model(**invoer).logits, dim=-1)
    return float(kansen[:, index].max())


def stance_scores(premise: str, hypothese: str, model_version: str) -> tuple[float, float]:
    """Entailment- en contradiction-score in één richting: premise → hypothese.

    Anders dan `contradiction_score` bewust níét symmetrisch: stance is een
    gerichte vraag — *brengt dit document deze claim als waar?* — en precies zo
    is hij gemeten (BENCHMARK.md §56, document als premise, claim als
    hypothese). Weerleggers die de claim citeren scoren entailment 0,00; de
    omgekeerde richting is nooit gemeten en heeft hier geen betekenis.
    Uitsluitend offline/batch, net als de rest van deze module (§15).
    """
    import torch

    tokenizer, model, contradiction_index = _laad(model_version)
    labels = {label.lower(): i for i, label in model.config.id2label.items()}
    if "entailment" not in labels:
        raise ValueError(
            f"model {model_version!r} kent geen 'entailment'-label:"
            f" {model.config.id2label}"
        )
    with torch.no_grad():
        invoer = tokenizer(
            [premise], [hypothese], return_tensors="pt", truncation=True,
            # 384 sinds de venster-premise (#21.5): een zin plus vier
            # buurzinnen moet erin passen, anders snijdt de truncatie juist
            # het oordeel aan het eind af. Ruimer toelaten verandert korte
            # premises niet, dus de §56-meting blijft geldig.
            padding=True, max_length=384,
        )
        kansen = torch.softmax(model(**invoer).logits, dim=-1)[0]
    return float(kansen[labels["entailment"]]), float(kansen[contradiction_index])


def is_contradiction(a: str, b: str, model_version: str, threshold: float) -> bool:
    return contradiction_score(a, b, model_version) >= threshold


def same_language_veto(model_version: str, threshold: float):
    """Bouwt een clustering-veto dat alleen bínnen één taal oordeelt.

    Gemeten op het corpus (2026-08-29): zonder deze beperking blokkeerde het
    model 19 samenvoegingen, waarvan 11 cross-linguaal — en díé waren
    grotendeels vals: Baerbock NL/DE, astronauten FR/NL, WEF NL/DE zijn
    dezelfde claim in twee talen. Het model leest een vertaling te vaak als
    tegenspraak, en juist meertalige clusters zijn de kern van DR7.

    Binnen één taal is het oordeel wél bruikbaar: 8 blokkades, waaronder
    gevallen die de mechanische regels per constructie missen — "één miljoen"
    tegenover "2,4 miljoen" bijwerkingen (uitgeschreven getallen), en
    "brandende bus in Italië" tegenover "in Londen".
    """

    def veto(tekst_a: str, tekst_b: str, taal_a: str, taal_b: str) -> bool:
        if taal_a != taal_b:
            return False
        return is_contradiction(tekst_a, tekst_b, model_version, threshold)

    # Zodat de clustertoestand kan vastleggen mét welk relatiemodel gebouwd is
    # (#12.3); anders is een vetowissel onzichtbaar voor de guard.
    veto.model_version = model_version

    return veto
