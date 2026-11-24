"""Gedragstests op het echte embeddingmodel (E1.S1-AC1, AC2, PLAN.md #1.10).

Faalt dit, dan is dat een bevinding over het gekozen model — melden aan de
PO, niet omheen werken.
"""

import pytest

from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.seed import load_seed

NL_CLAIM = "Coronavaccins bevatten microchips om mensen te volgen"
EN_CLAIM = "COVID-19 vaccines contain microchips to track people"

ORIGINEEL = "De zeespiegel daalt al tien jaar wereldwijd"
PARAFRASE = "Wereldwijd zakt het zeeniveau al een decennium"


@pytest.fixture(scope="module")
def versie():
    return load_config().model_versions.text_embedding


def _similariteit(tekst_a, tekst_b, versie):
    vector_a = fingerprint_text(tekst_a, versie).vector
    vector_b = fingerprint_text(tekst_b, versie).vector
    return float(vector_a @ vector_b)


def _andere_seedteksten(*uitgesloten):
    return [
        claim["canonical_text"]
        for claim in load_seed()
        if claim["canonical_text"] not in uitgesloten
    ]


def test_translation_pair_closer_than_random(versie):
    paar = _similariteit(NL_CLAIM, EN_CLAIM, versie)

    for andere in _andere_seedteksten(NL_CLAIM, EN_CLAIM):
        assert paar > _similariteit(NL_CLAIM, andere, versie), (
            f"vertaalpaar ({paar:.3f}) niet dichterbij dan: {andere!r}"
        )
        assert paar > _similariteit(EN_CLAIM, andere, versie), (
            f"vertaalpaar ({paar:.3f}) niet dichterbij dan: {andere!r}"
        )


def test_paraphrase_closer_than_random(versie):
    paar = _similariteit(ORIGINEEL, PARAFRASE, versie)

    for andere in _andere_seedteksten(ORIGINEEL, PARAFRASE):
        assert paar > _similariteit(ORIGINEEL, andere, versie), (
            f"parafrasepaar ({paar:.3f}) niet dichterbij dan: {andere!r}"
        )
