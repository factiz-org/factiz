"""Ontkenningstest — de risicovolste taak van het project (E1.S1-AC3, PLAN.md #1.11).

Bevinding 2026-08-27: het huidige model plaatst het ontkenningspaar DICHTERBIJ
elkaar (0.866) dan parafrases (0.843 / 0.858). Het AC wordt dus niet gehaald.
Conform het plan is dit een bevinding voor de PO, geen bug om omheen te werken:
de test staat op xfail(strict) zodat de suite bruikbaar blijft, de bevinding
elke run zichtbaar is, én de marker luid breekt zodra een modelwissel dit ooit
oplost.
"""

from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.seed import load_seed

PARAFRASE_JANSEN = "Minister Jansen is opgestapt vanwege het datalek"
ZEESPIEGEL = "De zeespiegel daalt al tien jaar wereldwijd"
ZEESPIEGEL_PARAFRASE = "Wereldwijd zakt het zeeniveau al een decennium"


def _seedtekst(claim_id):
    for claim in load_seed():
        if claim["claim_id"] == claim_id:
            return claim["canonical_text"]
    raise LookupError(claim_id)


def _similariteit(tekst_a, tekst_b, versie):
    vector_a = fingerprint_text(tekst_a, versie).vector
    vector_b = fingerprint_text(tekst_b, versie).vector
    return float(vector_a @ vector_b)


def test_negation_pair_further_than_paraphrase():
    """Onder MiniLM een bekende beperking (PLAN.md #1.11, 2026-08-27): de
    ontkenning lag dichterbij (0,827) dan een parafrase (0,756). Onder bge-m3
    opgelost (#25.14c): ontkenning 0,828 tegen parafrasen 0,983 en 0,901.
    Nu een bewaking: een volgend model mag hier niet terugvallen."""
    versie = load_config().model_versions.text_embedding
    afgetreden = _seedtekst("seed-jansen-afgetreden")
    niet_afgetreden = _seedtekst("seed-jansen-niet-afgetreden")

    ontkenning = _similariteit(afgetreden, niet_afgetreden, versie)

    assert ontkenning < _similariteit(afgetreden, PARAFRASE_JANSEN, versie)
    assert ontkenning < _similariteit(ZEESPIEGEL, ZEESPIEGEL_PARAFRASE, versie)
