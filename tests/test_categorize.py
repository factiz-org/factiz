from doublecheck.categorize import Category, categorize
from doublecheck.config import Thresholds, load_config


def _drempels(match=0.85, related=0.70):
    return Thresholds(text_match=match, text_related=related, image_same=10)


def test_categorize_uses_config_thresholds():
    config = load_config()
    drempels = config.thresholds

    net_erboven = categorize(drempels.text_match + 0.001, drempels)
    net_eronder = categorize(drempels.text_match - 0.001, drempels)

    assert net_erboven.category == Category.MATCHED
    assert net_eronder.category != Category.MATCHED

    # Dezelfde similariteit valt anders uit onder andere drempels: het oordeel
    # volgt de meegegeven config, er is geen ingebakken waarde.
    zelfde_similariteit = 0.75
    assert categorize(zelfde_similariteit, _drempels(match=0.70, related=0.50)).category == Category.MATCHED
    assert categorize(zelfde_similariteit, _drempels(match=0.85, related=0.70)).category == Category.RELATED
    assert categorize(zelfde_similariteit, _drempels(match=0.95, related=0.80)).category == Category.NONE


def test_at_or_above_match_threshold_is_matched():
    assert categorize(0.85, _drempels()).category == Category.MATCHED
    assert categorize(0.99, _drempels()).category == Category.MATCHED


def test_between_thresholds_is_related():
    assert categorize(0.70, _drempels()).category == Category.RELATED
    assert categorize(0.84, _drempels()).category == Category.RELATED


def test_below_all_thresholds_is_none():
    assert categorize(0.69, _drempels()).category == Category.NONE
    assert categorize(0.0, _drempels()).category == Category.NONE
    assert categorize(-0.3, _drempels()).category == Category.NONE


def test_without_candidate_is_none():
    uitkomst = categorize(None, _drempels())

    assert uitkomst.category == Category.NONE
    assert uitkomst.similarity is None


def test_result_carries_thresholds_used():
    drempels = _drempels(match=0.9, related=0.6)

    uitkomst = categorize(0.95, drempels)

    assert uitkomst.thresholds == drempels
    assert uitkomst.similarity == 0.95


# --- de rechter (PLAN #30.3, B36) ---------------------------------------------

def _met_rechter(zelfde=0.99, vloer=0.79):
    import dataclasses

    return dataclasses.replace(_drempels(match=0.87, related=0.79), rechter_zelfde=zelfde, rechter_vloer=vloer)


def test_with_the_judge_on_a_yes_above_the_floor_is_matched():
    assert categorize(0.80, _met_rechter(), rechter=0.995).category is Category.MATCHED


def test_with_the_judge_on_a_no_keeps_even_a_close_vector_out_of_matched():
    uitslag = categorize(0.97, _met_rechter(), rechter=0.20)
    assert uitslag.category is Category.RELATED and "tekst" not in uitslag.matched_on


def test_the_judge_never_lifts_a_candidate_below_the_floor():
    assert categorize(0.70, _met_rechter(), rechter=0.999).category is Category.NONE


def test_a_contradiction_still_demotes_a_judged_match():
    assert categorize(0.95, _met_rechter(), rechter=0.999, contradiction=True).category is Category.RELATED


def test_a_judge_score_without_judge_thresholds_is_refused():
    import pytest

    with pytest.raises(ValueError):
        categorize(0.95, _drempels(), rechter=0.999)


def test_without_a_judge_score_nothing_changes():
    assert categorize(0.90, _met_rechter()).category is Category.MATCHED


def _twee_standen():
    import dataclasses

    return dataclasses.replace(_met_rechter(zelfde=0.98), rechter_veto=0.30)


def test_above_the_match_threshold_the_judge_only_vetoes():
    assert categorize(0.92, _twee_standen(), rechter=0.50).category is Category.MATCHED
    assert categorize(0.92, _twee_standen(), rechter=0.10).category is Category.RELATED


def test_below_the_match_threshold_the_judge_lifts_only_when_it_is_sure():
    assert categorize(0.82, _twee_standen(), rechter=0.50).category is Category.RELATED
    assert categorize(0.82, _twee_standen(), rechter=0.99).category is Category.MATCHED


def test_without_a_veto_threshold_one_threshold_holds_everywhere():
    assert categorize(0.92, _met_rechter(zelfde=0.98), rechter=0.50).category is Category.RELATED


def test_a_red_check_next_to_an_established_fact_is_never_matched():
    # zoals een vastgestelde tegenspraak (DR8): hoogstens related, de claim blijft als verwant zichtbaar
    assert categorize(0.95, _drempels(), feit_rood=True).category is Category.RELATED


def test_an_established_fact_does_not_change_a_non_red_answer():
    assert categorize(0.95, _drempels()).category is Category.MATCHED


# --- de artikellezer (PLAN #30.11b) ------------------------------------------

def _met_lezer(vloer=0.70, zelfde=0.80):
    import dataclasses

    return dataclasses.replace(_drempels(match=0.87, related=0.79), artikel_vloer=vloer, artikel_zelfde=zelfde)


def test_the_article_reader_lifts_a_candidate_from_its_own_floor_only_when_sure():
    assert categorize(0.72, _met_lezer(), lezer=0.85).category is Category.MATCHED
    assert categorize(0.72, _met_lezer(), lezer=0.79).category is Category.NONE
    assert categorize(0.69, _met_lezer(), lezer=0.99).category is Category.NONE


def test_below_the_reader_threshold_a_close_vector_stays_related():
    assert categorize(0.83, _met_lezer(), lezer=0.40).category is Category.RELATED


def test_a_contradiction_or_a_red_verdict_next_to_a_fact_still_blocks_the_reader():
    assert categorize(0.75, _met_lezer(), lezer=0.95, contradiction=True).category is not Category.MATCHED
    assert categorize(0.75, _met_lezer(), lezer=0.95, feit_rood=True).category is not Category.MATCHED


def test_a_reader_score_without_reader_thresholds_is_refused():
    import pytest

    with pytest.raises(ValueError):
        categorize(0.75, _drempels(), lezer=0.9)
