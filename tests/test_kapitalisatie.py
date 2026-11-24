"""Kapitalisatie uit de fingerprint (PLAN.md #12.1, E1.S1, DR6).

Aanleiding: gemeten bij de ES-uitrol. Het embeddingmodel zet hoofdlettertekst bij
hoofdlettertekst, vrijwel los van de inhoud — een artefact in kapitalen landde in
45 van de 100 gevallen op een all-caps claim, tegen 0,21% kansniveau
(BENCHMARK.md §22e). Virale screenshots staan vaak in kapitalen, dus dit is een
G1-risico in productie en niet alleen in het harnas.

De oplossing normaliseert vóór het embedden. Dat verandert wat het model ziet,
dus de fingerprintversie gaat omhoog: DR6 verbiedt vergelijken over versies heen.
"""

import numpy as np
import pytest

from doublecheck.embedding import (
    _model_naam,
    fingerprint_text,
    normaliseer_voor_embedding,
)

VERSIE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2+casefold"


def test_model_name_strips_the_preprocessing_suffix():
    """De versie beschrijft model én voorbewerking; het laden wil alleen het model."""
    assert _model_naam(VERSIE) == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    assert _model_naam("kaal-model-v1") == "kaal-model-v1"


@pytest.mark.parametrize(
    "tekst",
    [
        "HET VACCIN BEVAT MICROCHIPS",
        "Het vaccin bevat microchips",
        "het vaccin bevat microchips",
        "Het Vaccin Bevat Microchips",
    ],
)
def test_casing_does_not_survive_normalisation(tekst):
    assert normaliseer_voor_embedding(tekst) == "het vaccin bevat microchips"


def test_normalisation_leaves_other_scripts_alone():
    """Schriften zonder hoofdletters mogen niet stilletjes veranderen."""
    for tekst in ("لقاح كورونا يحتوي على شريحة", "新冠疫苗含有微芯片", "टीके में माइक्रोचिप है"):
        assert normaliseer_voor_embedding(tekst) == tekst


def test_uppercase_artifact_matches_its_own_source(model_versie):
    """De kern: HOOFDLETTERS mag de gelijkenis niet meer sturen."""
    claim = "El Gobierno aprueba una nueva ley de vivienda esta semana"
    ruis = "ABELARDO DE LA ESPRIELLA PODRÍA IR PRESO POR FALSIFICACIÓN DE FIRMAS"

    bron = fingerprint_text(claim, model_versie).vector
    stoorzender = fingerprint_text(ruis, model_versie).vector
    artefact = fingerprint_text(claim.upper(), model_versie).vector

    assert float(artefact @ bron) > float(artefact @ stoorzender)


def test_fingerprint_is_identical_regardless_of_casing(model_versie):
    a = fingerprint_text("Het vaccin bevat microchips", model_versie).vector
    b = fingerprint_text("HET VACCIN BEVAT MICROCHIPS", model_versie).vector
    assert np.allclose(a, b)


def test_numbers_and_negations_still_come_from_the_original(model_versie):
    """Normaliseren is voor het model; de afleidingen blijven ongemoeid (#11.5)."""
    fp = fingerprint_text("Het bevat GEEN 30.000 chips", model_versie)
    assert fp.numbers == frozenset({"30000"})
    assert fp.negations == frozenset({"geen"})


@pytest.fixture
def model_versie():
    from doublecheck.config import load_config

    return load_config().model_versions.text_embedding
