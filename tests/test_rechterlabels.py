"""Haiku-labels op echte paren (PLAN #30.3, de volgende ronde): kandidaten
zoals de rechter ze in het wild ziet, nooit van de toetshelft of de kern.
"""

import json

import pytest

from doublecheck import rechterlabels as rl
from doublecheck.zeef import helft


def _claim(h):
    return next(f"gfc-{i:016x}" for i in range(1000) if helft(f"zaak:gfc-{i:016x}") == h)


def test_a_pair_touching_the_test_half_never_becomes_material():
    ontw, toets = _claim("ontwikkel"), _claim("toets")
    assert rl.mag_mee("ontwikkel", ontw) is True
    assert rl.mag_mee("toets", ontw) is False
    assert rl.mag_mee("ontwikkel", toets) is False


def test_the_question_carries_both_texts_and_the_four_answers():
    v = rl.verzoek({"vraag": "Russia annexed Crimea.", "kandidaat": "Crimea decided to join Russia."})
    tekst = v["params"]["messages"][0]["content"]
    assert "Russia annexed Crimea." in tekst and "Crimea decided to join Russia." in tekst
    schema = v["params"]["output_config"]["format"]["schema"]
    assert schema["properties"]["oordeel"]["enum"] == ["zelfde", "verwant", "tegenspraak", "anders"]
    assert v["custom_id"] == rl.paarsleutel({"vraag": "Russia annexed Crimea.",
                                             "kandidaat": "Crimea decided to join Russia."})


@pytest.mark.parametrize("tekst, verwacht", [
    ('{"oordeel": "zelfde", "zeker": true}', ("zelfde", True)),
    ('{"oordeel": "verwant", "zeker": false}', ("verwant", False)),
    ('{"oordeel": "misschien", "zeker": true}', None),
    ("niet te lezen", None),
])
def test_an_unreadable_or_unknown_answer_is_no_label(tekst, verwacht):
    assert rl.uitkomst(tekst) == verwacht


@pytest.mark.parametrize("mens, verwacht", [
    ("doel", True), ("zelfde", True), ("terecht", True), ("anders", False), ("vals", False), (None, None),
])
def test_human_labels_are_compared_on_same_claim_or_not(mens, verwacht):
    assert rl.mens_zelfde(mens) is verwacht


def test_the_agreement_counts_only_pairs_a_human_labelled():
    rijen = [{"mens": "doel", "label": "zelfde"}, {"mens": "vals", "label": "zelfde"},
             {"mens": "anders", "label": "verwant"}, {"mens": None, "label": "zelfde"}]
    assert rl.overeenstemming(rijen) == {"n": 3, "eens": 2, "haiku_zelfde_mens_niet": 1, "mens_zelfde_haiku_niet": 0}


def test_written_pairs_carry_their_case_and_role(tmp_path):
    paar = rl.lesregel({"vraag": "a", "kandidaat": "b", "zaak": "zaak:x", "soort": "buren", "taal": "en"},
                       ("verwant", True))
    assert paar["label"] == "verwant" and paar["rol"] == "leren" and paar["bron"] == "haiku-echt"
    assert json.loads(json.dumps(paar)) == paar


@pytest.mark.parametrize("haiku, zeker, mens, verwacht", [
    ("zelfde", True, None, "zelfde"),
    ("verwant", False, None, None),
    ("verwant", False, "doel", "zelfde"),
    ("verwant", True, "doel", None),
    ("zelfde", True, "vals", None),
    ("verwant", True, "vals", "verwant"),
    ("tegenspraak", False, "anders", "tegenspraak"),
])
def test_a_human_settles_doubt_and_a_sure_conflict_is_left_out(haiku, zeker, mens, verwacht):
    assert rl.leslabel(haiku, zeker, mens) == verwacht
