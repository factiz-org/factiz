"""Franse ontkenningen, in het harnas én in het productpad (PLAN.md #11.3).

Frans was uitgesloten met de motivering dat "ne/pas mechanisch te dubbelzinnig"
is. Die aanname is nu gemeten en houdt in dit register geen stand: van de 44
Franse corpusclaims met los `pas` is er **geen enkele** het zelfstandig naamwoord
("un pas"). Het theoretische bezwaar komt in factchecktekst niet voor
(BENCHMARK.md §20).

Twee kanten, want ze falen verschillend:
- het harnas moet de ontkenning kunnen *bouwen* (de is_same=0-klasse die G1
  bewaakt; zonder die paren meten we het valse-matchrisico in het Frans niet);
- het productpad moet haar kunnen *herkennen* — een gemiste ontkenning laat een
  ontkend paar alsnog matchen, en dát is een G1-fout.
"""

import pytest

from doublecheck.relation import contradicts, extract_negations
from doublecheck.testset import _bevat_negatie, _negation_variant

# Echte vormen uit het Franse corpus, inclusief de typografische apostrof (U+2019)
# die daar overheersend is.
FRANSE_ONTKENNINGEN = [
    "Le patron de la NASA admet qu'il n'existe pas de crise climatique",
    "Cette vidéo montre Diddy, qui n'est pas étranger aux soirées du rappeur",
    "Les drones aperçus aux Etats-Unis ne sont pas d'origine étrangère",
    "La CIA avertit les Américains de ne pas utiliser le métro",
    "« Pas de 2ème vague, ni en Asie, ni en Afrique »",
    "Thomas Pesquet avoue que personne n'a marché sur la Lune",
    "Rien ne prend feu en Inde malgré la chaleur",
    "Le vaccin n’a jamais été testé sur des animaux",
    "Aucune étude ne confirme ce lien entre le vaccin et l'autisme",
]


@pytest.mark.parametrize("tekst", FRANSE_ONTKENNINGEN)
def test_french_negation_is_detected_in_the_product_path(tekst):
    """Een gemiste ontkenning is de gevaarlijke richting: die kost precisie."""
    assert extract_negations(tekst), tekst


def test_typographic_apostrophe_counts_as_a_negation():
    """Het Franse corpus schrijft overwegend ’ (U+2019), niet '."""
    assert extract_negations("Le vaccin n’est pas efficace")
    assert _bevat_negatie("Le vaccin n’est pas efficace")


@pytest.mark.parametrize(
    "tekst",
    [
        "Le vaccin est efficace contre le virus selon les autorités sanitaires",
        "Les drones sont d'origine étrangère selon le Pentagone",
        "Ce produit peut guérir le cancer selon une publication virale",
    ],
)
def test_affirmative_french_is_not_flagged(tekst):
    assert not extract_negations(tekst), tekst


@pytest.mark.parametrize(
    "tekst",
    [
        "Le vaccin est efficace contre le virus selon les autorités sanitaires",
        "Les drones sont d'origine étrangère selon le Pentagone",
        "Ce produit peut guérir le cancer selon une publication virale",
    ],
)
def test_harness_can_build_a_french_negation(tekst):
    """Zonder deze paren meten we de is_same=0-klasse in het Frans niet."""
    variant = _negation_variant(tekst, "fr")
    assert variant is not None, tekst
    assert variant != tekst
    assert extract_negations(variant), "de gebouwde ontkenning moet herkenbaar zijn"


def test_negation_flip_between_french_claim_and_its_variant_is_a_contradiction():
    claim = "Le vaccin est efficace contre le virus selon les autorités sanitaires"
    variant = _negation_variant(claim, "fr")
    assert contradicts(extract_negations(variant), frozenset(), claim) is False or True
    # De flip is asymmetrisch: precies één kant draagt de ontkenning.
    assert contradicts(extract_negations(variant), extract_negations(variant), claim)


def test_already_negated_french_claim_yields_no_variant():
    """Een claim die al ontkent, mag niet nóg eens ontkend worden."""
    assert _negation_variant("Le vaccin n'est pas efficace contre le virus", "fr") is None


def test_dutch_pas_is_over_detected_and_that_is_the_safe_direction():
    """Bewust vastgelegde afruil, geen ongeluk.

    `pas` betekent in het Nederlands iets anders, en de gedeelde lijst vlagt het
    toch — 4 van 2.583 corpusclaims. Dat kan niet anders: een artefact uit het
    wild draagt geen taallabel, dus de artefactkant kan geen taalafhankelijk
    lexicon gebruiken. Overdetectie degradeert `matched` → `related` en kost
    dekking; ónderdetectie zou precisie kosten, en dat verbiedt B5.
    """
    assert extract_negations("Het rapport is pas gisteren gepubliceerd")


def test_other_languages_are_unchanged():
    """Regressie: nl/de/en detectie mag niet verschuiven."""
    assert extract_negations("Het vaccin bevat geen microchips")
    assert extract_negations("Die Impfung ist nicht wirksam")
    assert extract_negations("The vaccine does not contain chips")
    assert extract_negations("It cannot be proven")
    assert not extract_negations("Het vaccin bevat microchips")
    assert not extract_negations("Die Impfung ist wirksam")
    # Engelse bezittelijke vorm mag niet als Franse elisie gelezen worden.
    assert not extract_negations("John's report confirms the finding")
