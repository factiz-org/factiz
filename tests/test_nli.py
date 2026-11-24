"""NLI-relatiemodule (E3.S4-AC3, PLAN.md #10.3).

Draait lokaal (DR3), modelversie uit config (DR6). De zware tests laden het
echte model en zijn gemarkeerd, zodat de gewone suite snel blijft.
"""

import pytest

from doublecheck.config import load_config
from doublecheck.nli import contradiction_score, is_contradiction


def test_config_exposes_nli_model_and_threshold():
    config = load_config()

    assert config.model_versions.nli
    assert 0.0 < config.thresholds.nli_contradiction < 1.0


@pytest.mark.nli
def test_nli_scores_contradiction_for_the_negation_pair():
    config = load_config()
    versie = config.model_versions.nli

    score = contradiction_score(
        "Minister Jansen is afgetreden vanwege het datalek",
        "Minister Jansen is niet afgetreden vanwege het datalek",
        versie,
    )

    assert score > 0.9, score


@pytest.mark.nli
def test_nli_does_not_flag_a_paraphrase():
    config = load_config()

    score = contradiction_score(
        "De zeespiegel daalt al tien jaar wereldwijd",
        "Wereldwijd zakt het zeeniveau al een decennium",
        config.model_versions.nli,
    )

    assert score < 0.2, score


@pytest.mark.nli
def test_nli_does_not_flag_a_translation():
    config = load_config()

    score = contradiction_score(
        "Hongarije kondigt officieel zijn terugtrekking aan uit de EU.",
        "Ungarn hat offiziell den Austritt aus der EU angekuendigt.",
        config.model_versions.nli,
    )

    assert score < 0.2, score


@pytest.mark.nli
def test_is_contradiction_uses_the_configured_threshold():
    config = load_config()
    paar = ("Minister Jansen is afgetreden", "Minister Jansen is niet afgetreden")

    assert is_contradiction(*paar, config.model_versions.nli, threshold=0.9) is True
    assert is_contradiction(*paar, config.model_versions.nli, threshold=0.999) is False
