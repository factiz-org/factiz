"""Ontkenningen in pt, it, ru, id en hi (PLAN.md #25.1b, BENCHMARK §64).

Run #41 vond 100 fouten die allemaal dezelfde vorm hadden: een ontkende claim
in een taal die de productiewachter niet kende, matchte op het origineel. Het
harnas kon de ontkenning al bouwen (#25.1); hier leert het productpad haar
herkennen. Overdetectie kost dekking, nooit precisie, maar lijkt-erop-woorden
horen er niet in te vallen.
"""

import pytest

from doublecheck.relation import extract_negations
from doublecheck.testset import _negation_variant

ONTKENNINGEN = [
    ("pt", "A vacina não contém microchips"),
    ("pt", "Nem o governo nem a oposição aprovaram a lei"),
    ("pt", "Nenhum estudo confirma essa ligação"),
    ("it", "Il vaccino non contiene microchip"),
    ("it", "Nessuno studio conferma questo legame"),
    ("ru", "Вакцина не содержит микрочипов"),
    ("ru", "Никто не видел этого видео, его нет"),
    ("id", "Vaksin tidak mengandung mikrocip"),
    ("id", "Video itu bukan dari Indonesia"),
    ("hi", "यह वीडियो असली नहीं है"),
    ("hi", "सरकार ने ऐसा कोई आदेश नही दिया"),
]

GEEN_ONTKENNING = [
    "Saya takut dengan vaksin itu",           # id: 'tak' zit in 'takut'
    "Немец сказал это в интервью",            # ru: 'не' zit in 'немец'
    "Nonostante tutto, il piano è approvato",  # it: 'non' zit in 'nonostante'
    "O nemátodo foi encontrado em Lisboa",     # pt: 'nem' zit in 'nemátodo'
    "यहनहींहै",                               # hi: aaneengeschreven, geen los woord
]


@pytest.mark.parametrize("taal, tekst", ONTKENNINGEN)
def test_negation_is_detected_in_the_five_new_languages(taal, tekst):
    assert extract_negations(tekst), (taal, tekst)


@pytest.mark.parametrize("tekst", GEEN_ONTKENNING)
def test_lookalike_words_are_not_negations(tekst):
    assert not extract_negations(tekst), tekst


@pytest.mark.parametrize("taal, tekst", [
    ("pt", "O presidente é responsável pela crise"),
    ("it", "Il governo è responsabile della crisi"),
    ("ru", "Президент является виновником кризиса"),
    ("id", "Vaksin itu adalah penyebab autisme"),
    ("hi", "यह वीडियो असली है"),
])
def test_every_testset_negation_is_recognised_by_the_product(taal, tekst):
    """De kern van #25.1b: wat het harnas als ontkenning bouwt, herkent het
    productpad als ontkenning. Anders meet de benchmark een gat dat de code
    nooit kan dichten."""
    variant = _negation_variant(tekst, taal)
    assert variant is not None
    assert extract_negations(variant) != extract_negations(tekst)
