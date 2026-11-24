"""Cross-linguale matchdrempel (PLAN.md #12.4, DR4, DR6).

Cross-linguale gelijkenis ligt structureel lager, dus één drempel kiest altijd
verkeerd. Gemeten op de 44 vertaalparen tegenover de dichtstbijzijnde buur in
een ándere taal (BENCHMARK.md §26b).

De categorie blijft uit één plek komen (DR4): `categorize` krijgt er een
parameter bij, er komt géén tweede codepad.
"""

import pytest

from doublecheck.categorize import Category, categorize
from doublecheck.config import ConfigError, Thresholds, load_config

DREMPELS = Thresholds(
    text_match=0.90,
    text_related=0.80,
    image_same=10,
    text_match_crosslingual=0.85,
)


def test_same_language_pair_uses_the_strict_threshold():
    assert categorize(0.87, DREMPELS).category is Category.RELATED


def test_cross_lingual_pair_uses_the_lower_threshold():
    uitkomst = categorize(0.87, DREMPELS, crosslinguaal=True)
    assert uitkomst.category is Category.MATCHED


def test_cross_lingual_threshold_still_has_a_floor():
    """Lager is niet vrijblijvend: onder de cross-linguale drempel geen match."""
    assert categorize(0.84, DREMPELS, crosslinguaal=True).category is Category.RELATED


def test_uncertainty_never_loosens_anything():
    """`crosslinguaal` is alleen True als béíde talen bekend zijn én verschillen."""
    from doublecheck.taal import zijn_verschillende_talen

    assert zijn_verschillende_talen("nl", "en") is True
    assert zijn_verschillende_talen("nl", "nl") is False
    assert zijn_verschillende_talen(None, "en") is False
    assert zijn_verschillende_talen("nl", None) is False
    assert zijn_verschillende_talen(None, None) is False


def test_contradiction_still_wins_over_a_cross_lingual_match():
    """DR8 blijft boven alles: tegenspraak degradeert, ook cross-linguaal."""
    uitkomst = categorize(0.97, DREMPELS, contradiction=True, crosslinguaal=True)
    assert uitkomst.category is Category.RELATED


def test_thresholds_travel_with_the_result():
    """De gebruikte waarden reizen mee (E3.S2-AC4, DR6)."""
    uitkomst = categorize(0.87, DREMPELS, crosslinguaal=True)
    assert uitkomst.thresholds.text_match_crosslingual == 0.85


def test_config_refuses_a_cross_lingual_threshold_above_the_strict_one(tmp_path):
    """Een lósser cross-lingueel pad is het doel; strenger zou onzin zijn."""
    pad = tmp_path / "config.toml"
    pad.write_text(
        "[thresholds]\ntext_match = 0.90\ntext_related = 0.80\n"
        "text_match_crosslingual = 0.95\nimage_same = 10\ncluster_same = 0.93\n"
        "nli_contradiction = 0.5\n"
        '[model_versions]\ntext_embedding = "m"\nimage_hash = "p"\nnli = "n"\n'
        '[ocr]\nlanguages = "nld"\nmin_chars = 12\n'
        "[retention]\nartifact_days = 90\nsweep_interval_hours = 24\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(pad)


def test_config_refuses_a_cross_lingual_threshold_below_related(tmp_path):
    """Onder de related-drempel zou de categorie zichzelf tegenspreken."""
    pad = tmp_path / "config.toml"
    pad.write_text(
        "[thresholds]\ntext_match = 0.90\ntext_related = 0.80\n"
        "text_match_crosslingual = 0.75\nimage_same = 10\ncluster_same = 0.93\n"
        "nli_contradiction = 0.5\n"
        '[model_versions]\ntext_embedding = "m"\nimage_hash = "p"\nnli = "n"\n'
        '[ocr]\nlanguages = "nld"\nmin_chars = 12\n'
        "[retention]\nartifact_days = 90\nsweep_interval_hours = 24\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(pad)


def test_real_config_is_consistent():
    drempels = load_config().thresholds
    assert (
        drempels.text_related
        <= drempels.text_match_crosslingual
        <= drempels.text_match
    )


def test_image_signal_is_not_claimed_when_it_points_elsewhere():
    """Een signaal in `matched_on` moet over de teruggegeven claim gaan (#13.2).

    Gemeten na B15: in de klasse waar beeld en tekst verschillende claims
    aanwijzen kwam 15 van de 15 keer `beeld` in `matched_on` te staan, terwijl
    dat beeld ergens anders op sloeg (BENCHMARK.md §30). De categorie was goed,
    het bijschrift onwaar.
    """
    drempels = Thresholds(
        text_match=0.90, text_related=0.80, image_same=31, text_match_crosslingual=0.85
    )
    # Tekst matcht vol; het beeld ligt binnen de drempel maar bij een ándere claim.
    uitkomst = categorize(
        0.95, drempels, image_distance=5, image_claim_differs=True
    )
    assert uitkomst.category is Category.MATCHED
    assert "beeld" not in uitkomst.matched_on


def test_image_signal_is_kept_when_it_agrees():
    drempels = Thresholds(
        text_match=0.90, text_related=0.80, image_same=31, text_match_crosslingual=0.85
    )
    uitkomst = categorize(
        0.95, drempels, image_distance=5, image_claim_differs=False
    )
    assert "beeld" in uitkomst.matched_on


def test_image_only_match_is_unaffected():
    """Zonder tekstsignaal is het beeld de enige bron en dus nooit misleidend."""
    drempels = Thresholds(
        text_match=0.90, text_related=0.80, image_same=31, text_match_crosslingual=0.85
    )
    uitkomst = categorize(None, drempels, image_distance=5, image_claim_differs=False)
    assert uitkomst.category is Category.RELATED
    assert "beeld" in uitkomst.matched_on
