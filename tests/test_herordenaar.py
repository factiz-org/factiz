"""De herordenaar als meetgereedschap (PLAN #25.23)."""

import pytest

from doublecheck import herordenaar


def _in_cache() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        naam, _, revisie = herordenaar.HERORDENAAR.partition("@")
        return isinstance(try_to_load_from_cache(naam, "config.json", revision=revisie), str)
    except Exception:
        return False


def test_the_reranker_version_is_pinned_to_a_commit():
    """DR6: een meting die met een ander model draaide, is niet dezelfde meting."""
    naam, _, revisie = herordenaar.HERORDENAAR.partition("@")
    assert naam == "BAAI/bge-reranker-v2-m3" and len(revisie) == 40


@pytest.mark.skipif(not _in_cache(), reason="herordenaar niet gedownload op deze machine")
def test_a_note_about_the_claim_scores_high_and_a_generic_note_low():
    angola, algemeen = herordenaar.scores([
        ("Angola has banned Islam",
         "This claim has been in circulation since 2013. The government of Angola clarified there is no ban on Islam."),
        ("Angola has banned Islam", "This statement is fake."),
    ])
    assert angola > 0.5 > 0.1 > algemeen
