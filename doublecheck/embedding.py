"""Tekst naar vector-fingerprint, altijd mét modelversie (DR6, E1.S1-AC4).

Vectors worden genormaliseerd opgeslagen, zodat cosinusgelijkenis verderop
een kaal inwendig product is. De modelversie komt als parameter binnen
(uiteindelijk uit config); deze module kent zelf geen modelnamen.

De versie beschrijft model **én voorbewerking**, gescheiden door `+`. Wat we vóór
het embedden met de tekst doen bepaalt de vector net zo goed als het model zelf,
dus het hoort in de versie die DR6 bewaakt: `<model>+casefold`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class TextFingerprint:
    vector: np.ndarray
    model_version: str
    # Deterministische signaturen voor de relatiecheck (E3.S4/DR8) — onderdeel
    # van de fingerprint, zodat ook de artefactloze testset (DR3) ze draagt.
    numbers: frozenset[str] = frozenset()
    negations: frozenset[str] = frozenset()
    # Dezelfde ontkenningen mét herhalingen (#25.1c): de negatieflip telt.
    negation_tokens: tuple[str, ...] = ()
    # Herkende taal van de brontekst, of None bij twijfel (#12.4). Onderdeel van
    # de fingerprint om dezelfde reden als `numbers`: de artefacttekst zelf wordt
    # weggegooid (DR3), dus wat we ervan willen weten moet hier in.
    language: str | None = None


# De voorbewerkingsstappen die deze module kent. Een onbekende stap in de
# versie wordt geweigerd, nooit genegeerd: dan zou de resolver stil anders
# rekenen dan de index (DR6).
_STAPPEN = {"casefold"}


def _modelspec(model_version: str) -> tuple[str, str | None, tuple[str, ...]]:
    """Leest `naam[@commit]+stap+stap` (#25.14c).

    De commit zet het model vast: op Hugging Face kan een model onder dezelfde
    naam veranderen, en dan rekent de resolver met andere vectoren dan de
    index. Alleen een volledige commit-hash telt; een tak of een afkorting kan
    verschuiven.
    """
    import re

    kern, *stappen = model_version.split("+")
    naam, _, revisie = kern.partition("@")
    onbekend = [s for s in stappen if s not in _STAPPEN]
    if onbekend:
        raise ValueError(f"onbekende voorbewerking {onbekend} in {model_version!r}")
    if revisie and not re.fullmatch(r"[0-9a-f]{40}", revisie):
        raise ValueError(f"revisie {revisie!r} is geen volledige commit-hash in {model_version!r}")
    return naam, revisie or None, tuple(stappen)


def _model_naam(model_version: str) -> str:
    """De HuggingFace-naam uit de versie, zonder revisie en voorbewerking."""
    return model_version.split("+", 1)[0].partition("@")[0]


def normaliseer_voor_embedding(text: str) -> str:
    """Haalt kapitalisatie uit de tekst voordat het model hem ziet (#12.1).

    Het model codeert hoofdlettergebruik sterk: een artefact in kapitalen landde
    in 45 van de 100 gevallen op een all-caps claim, tegen 0,21% kansniveau
    (BENCHMARK.md §22e). Virale screenshots staan vaak in kapitalen, dus dat is
    een G1-risico in productie.

    `casefold()` en niet `lower()`: het eerste is de Unicode-variant die ook
    Duitse ß en Griekse eindsigma correct afhandelt. Schriften zonder
    hoofdletters blijven ongemoeid.
    """
    return text.casefold()


@lru_cache(maxsize=2)
def _load_model(model_version: str, apparaat: str = "cpu"):
    # Import hier, niet bovenaan: sentence_transformers sleept torch mee en
    # kost seconden — alleen betalen wanneer er echt ge-embed wordt.
    import torch
    from sentence_transformers import SentenceTransformer

    naam, revisie, _ = _modelspec(model_version)
    # Op de CPU en in float32: zo is de index gebouwd en gemeten (BENCHMARK
    # §74), en een server heeft geen GPU. Alleen het bulkembedden mag op de
    # grafische chip ("mps", B37): op 512 claims hoogstens 6,4e-7 verschil per
    # getal (#32.38).
    model = SentenceTransformer(naam, revision=revisie, device=apparaat,
                                model_kwargs={"dtype": torch.float32})
    # Claims zijn kort; een lange OCR-tekst mag een groot model niet minutenlang
    # bezighouden. Een model met een kortere eigen grens houdt die.
    model.max_seq_length = min(model.max_seq_length or 512, 512)
    return model


def fingerprint_text(text: str, model_version: str) -> TextFingerprint:
    from doublecheck.relation import extract_negation_tokens, extract_negations, extract_numbers
    from doublecheck.taal import detecteer_taal

    model = _load_model(model_version)
    vector = np.asarray(
        model.encode(
            normaliseer_voor_embedding(text),
            normalize_embeddings=True,
            show_progress_bar=False,
        ),
        dtype=np.float32,
    )
    vector.setflags(write=False)
    return TextFingerprint(
        vector=vector,
        model_version=model_version,
        # Bewust uit de óórspronkelijke tekst: normaliseren is voor het model,
        # niet voor de deterministische afleidingen (#11.5).
        numbers=extract_numbers(text),
        negations=extract_negations(text),
        negation_tokens=extract_negation_tokens(text),
        language=detecteer_taal(text),
    )


def fingerprint_texts(texts, model_version: str, apparaat: str = "cpu") -> list[TextFingerprint]:
    """Batchvariant van `fingerprint_text`, voor herindexeren (#12.2).

    Levert per constructie dezelfde vectoren als het losse pad — dezelfde
    normalisatie, hetzelfde model — maar in één modelaanroep in plaats van
    duizenden. Op een corpus van tienduizenden claims is dat het verschil tussen
    minuten en uren.
    """
    from doublecheck.relation import extract_negation_tokens, extract_negations, extract_numbers
    from doublecheck.taal import detecteer_taal

    texts = list(texts)
    if not texts:
        return []
    model = _load_model(model_version, apparaat)
    vectoren = np.asarray(
        model.encode(
            [normaliseer_voor_embedding(t) for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        ),
        dtype=np.float32,
    )
    fingerprints = []
    for tekst, vector in zip(texts, vectoren):
        vector = np.ascontiguousarray(vector, dtype=np.float32)
        vector.setflags(write=False)
        fingerprints.append(
            TextFingerprint(
                vector=vector,
                model_version=model_version,
                numbers=extract_numbers(tekst),
                negations=extract_negations(tekst),
                negation_tokens=extract_negation_tokens(tekst),
                language=detecteer_taal(tekst),
            )
        )
    return fingerprints
