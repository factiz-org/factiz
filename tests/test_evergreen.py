"""De evergreen-meting (PLAN #27.2a): welke verhalen komen over de jaren terug?

Per claimcluster komt bijna niets terug; een verhaal (biolabs in Oekraïne, en
dan in Georgië) leeft een niveau hoger. De meting verbindt claims die sterk op
elkaar lijken tot verhaalgroepen, telt de jaren waarin een groep gecheckt is,
en kijkt of het oordeel binnen een groep over de jaren verschuift.
"""

import numpy as np

from doublecheck.evergreen import is_evergreen, jaren, kant_per_jaar, verhaalgroepen, verschuift


def _eenheden(*richtingen):
    m = np.asarray(richtingen, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def test_claims_that_resemble_each_other_form_one_story_group():
    matrix = _eenheden([1, 0, 0], [0.95, 0.31, 0], [0, 1, 0], [0, 0, 1])
    groepen = verhaalgroepen(matrix, 0.9, blok=2)
    assert groepen[0] == groepen[1]
    assert len({groepen[1], groepen[2], groepen[3]}) == 3


def test_a_chain_of_resemblance_joins_one_group():
    """Verbonden is samenhangend: a lijkt op b, b op c, dan zijn a en c één
    groep, ook als ze zelf niet op elkaar lijken. Daarom meldt het verslag
    groepen die door zo'n ketting te groot worden."""
    hoek = np.radians([0, 20, 40])
    matrix = _eenheden(*[[np.cos(h), np.sin(h), 0] for h in hoek])
    groepen = verhaalgroepen(matrix, 0.9, blok=1)
    assert groepen[0] == groepen[2]


def test_only_valid_dates_count_as_years():
    assert jaren(["2020-01-25", "2024-10-25", "", "2924-01-02", "2020-07-01"]) == {"2020", "2024"}


def test_an_evergreen_is_checked_in_at_least_three_years():
    assert is_evergreen({"2016", "2019", "2025"})
    assert not is_evergreen({"2020", "2021"})


def test_the_side_per_year_follows_the_label_class():
    kanten = kant_per_jaar([("2020", "onwaar"), ("2020", "misleidend"), ("2024", "onbewezen"),
                            ("2025", "onbewezen"), ("2025", "onbekend"), ("2021", "satire")])
    assert kanten == {"2020": "rood", "2024": "onbewezen", "2025": "onbewezen"}


def test_a_verdict_that_changes_side_over_the_years_is_flagged():
    """Zoals het lab in Wuhan: 2020 onwaar, 2024 en 2025 onbewezen."""
    assert verschuift({"2020": "rood", "2024": "onbewezen"})
    assert not verschuift({"2016": "rood", "2022": "rood"})
