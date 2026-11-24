"""Cijferschriften in de getalvergelijking (PLAN.md #11.1, E3.S4, DR8).

Aanleiding: `_canoniek_getal` normaliseerde wél scheidingstekens maar niet het
cijferschrift, waardoor `٣٠٠٠٠` en `30000` als verschillende getallen golden.
DR8 zag dan een getalconflict dat er niet is en degradeerde `matched` →
`related` — fail-safe, maar het kost dekking in elke markt die inheemse cijfers
schrijft. Negen benchmarkruns overleefd omdat NL/DE/FR/EN Westers schrijven
(BENCHMARK.md §17c).

Welke schriften ertoe doen is gemeten op echte factchecks, niet aangenomen:
Bengaals 100%, Perzisch 100%, Arabisch 3%, Hindi 0%, Thai 0%.
"""

import pytest

from doublecheck.relation import contradicts, extract_number_contexts, extract_numbers

# (schrift, dezelfde bewering in inheemse cijfers) — allemaal het getal 30000.
SCHRIFTEN = [
    ("Arabisch-Indisch", "٣٠٠٠٠"),
    ("Bengaals", "৩০০০০"),
    ("Perzisch", "۳۰۰۰۰"),
    ("Devanagari", "३००००"),
]


@pytest.mark.parametrize("schrift,getal", SCHRIFTEN)
def test_native_digits_equal_western_digits(schrift, getal):
    assert extract_numbers(getal) == frozenset({"30000"}), schrift


@pytest.mark.parametrize("schrift,getal", SCHRIFTEN)
def test_same_number_in_another_script_is_no_contradiction(schrift, getal):
    """De kern: dezelfde bewering, ander cijferschrift, géén tegenspraak."""
    artefact = f"Het vaccin bevat {getal} chips"
    claim = "Het vaccin bevat 30000 chips"
    assert not contradicts(
        extract_numbers(artefact), frozenset(), claim, artefact
    ), schrift


def test_mixed_scripts_within_one_claim():
    """Echte Arabische factchecks mengen schriften: ['5', '١٤', '19']."""
    assert extract_numbers("منذ ١٤ عاما و 19 شهرا و 5 أيام") == frozenset(
        {"14", "19", "5"}
    )


def test_different_number_stays_a_contradiction_across_scripts():
    """Cijfervouwen mag de detectie niet verzwakken — ٤٠٠٠٠ is niet 30000."""
    artefact = "Het vaccin bevat ٤٠٠٠٠ chips"
    assert contradicts(
        extract_numbers(artefact), frozenset(), "Het vaccin bevat 30000 chips", artefact
    )


def test_separator_heuristic_survives_folding():
    """De groepslengte-heuristiek blijft gelden ná het vouwen (PLAN.md #8.1)."""
    assert extract_numbers("٣٠.٠٠٠ euro") == frozenset({"30000"})
    assert extract_numbers("٣,٥ miljoen") == frozenset({"3.5"})


def test_context_comparison_folds_digits_too():
    """Het tweede getalsignaal (contextconflict) mag niet achterblijven."""
    assert extract_number_contexts("٨ migranten") == {"migranten": "8"}


def test_western_behaviour_is_unchanged():
    """Regressie: de bug kón in NL/DE/FR/EN niet afgaan, dus mag er niets bewegen."""
    assert extract_numbers("bekommt 30.000 Euro") == frozenset({"30000"})
    assert extract_numbers("costs 30,000 euros") == frozenset({"30000"})
    assert extract_numbers("1.234,56 en 40 000") == frozenset({"1234.56", "40000"})
    assert extract_number_contexts("8 migranten") == {"migranten": "8"}
