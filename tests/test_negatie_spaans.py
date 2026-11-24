"""Spaanse ontkenningen voor de ES-markt (PLAN.md #11.4, B14).

Zoals bij Frans: het harnas moet de ontkenning kunnen *bouwen* (de is_same=0-klasse
die G1 bewaakt) en het productpad moet haar kunnen *herkennen* (een gemiste
ontkenning laat een ontkend paar alsnog matchen).

Spaans is een gunstig geval: `no` stond al in de gedeelde lijst en vangt 14,7%
van de 14.024 corpusclaims, want de Spaanse zinsontkenning is meestal `no` +
werkwoord. De extra tokens vullen de staart aan (BENCHMARK.md §22b).
"""

import pytest

from doublecheck.relation import extract_negations
from doublecheck.testset import _negation_variant

SPAANSE_ONTKENNINGEN = [
    "La vacuna no contiene microchips para rastrear a las personas",
    "Nunca se ha demostrado que el 5G cause cáncer",
    "Jamás se aprobó esa ley en el Congreso",
    "Ningún estudio confirma ese vínculo entre la vacuna y el autismo",
    "Ninguna autoridad sanitaria respalda esa afirmación",
    "Nadie ha caminado sobre la Luna, según esta publicación viral",
    "Tampoco es cierto que el gobierno haya prohibido esos alimentos",
    "España anuncia la entrada sin visado para ciudadanos de Botsuana",
]


@pytest.mark.parametrize("tekst", SPAANSE_ONTKENNINGEN)
def test_spanish_negation_is_detected(tekst):
    assert extract_negations(tekst), tekst


@pytest.mark.parametrize(
    "tekst",
    [
        "La vacuna es eficaz contra el virus según las autoridades sanitarias",
        "Los drones son de origen extranjero según el Pentágono",
        "Este producto puede curar el cáncer según una publicación viral",
        "El gobierno ha aprobado la nueva ley de vivienda esta semana",
    ],
)
def test_affirmative_spanish_is_not_flagged(tekst):
    assert not extract_negations(tekst), tekst


def test_sin_embargo_means_however_and_is_not_a_negation():
    """Gemeten uitzondering: 5 van de 205 `sin`-claims zijn `sin embargo`."""
    assert not extract_negations(
        "Los presupuestos destinan 248 millones; sin embargo la cifra es menor"
    )
    # De echte betekenis van `sin` blijft wél een ontkenning.
    assert extract_negations("Entrada sin visado para ciudadanos de Namibia")


@pytest.mark.parametrize(
    "tekst",
    [
        "La vacuna es eficaz contra el virus según las autoridades sanitarias",
        "Los drones son de origen extranjero según el Pentágono",
        "Este producto puede curar el cáncer según una publicación viral",
        "El gobierno ha aprobado la nueva ley de vivienda esta semana",
    ],
)
def test_harness_can_build_a_spanish_negation(tekst):
    variant = _negation_variant(tekst, "es")
    assert variant is not None, tekst
    assert variant != tekst
    assert extract_negations(variant), "de gebouwde ontkenning moet herkenbaar zijn"


def test_already_negated_spanish_claim_yields_no_variant():
    assert _negation_variant("La vacuna no es eficaz contra el virus", "es") is None


def test_other_languages_are_unchanged():
    """Regressie: nl/de/fr/en mogen niet verschuiven door de Spaanse tokens."""
    assert extract_negations("Het vaccin bevat geen microchips")
    assert extract_negations("Die Impfung ist nicht wirksam")
    assert extract_negations("Le vaccin n'est pas efficace")
    assert not extract_negations("Het vaccin bevat microchips")
    assert not extract_negations("Die Impfung ist wirksam")
    assert not extract_negations("The report confirms the finding")
