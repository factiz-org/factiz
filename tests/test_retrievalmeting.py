"""Waar zit het retrievalplafond van de batchcontrole (PLAN #21.7, stap 1)?

De meting telt per document de beste rang van de doelclaim over vier soorten
eenheden, met zoeken op betekenis en zoeken op woorden. Deze tests houden de
stukken zonder model vast: de eenheden, BM25 en de telling.
"""

from doublecheck.retrievalmeting import Bm25, eenheden, rang, telling

TEKST = ("Eerste zin over de zeespiegel. Tweede zin over het ijs! "
         "Derde zin over de oceaan? Vierde zin, de laatste.")


def test_sentences_are_the_units_the_batch_check_uses_now():
    assert eenheden(TEKST, "zin") == [
        "Eerste zin over de zeespiegel", "Tweede zin over het ijs",
        "Derde zin over de oceaan", "Vierde zin, de laatste",
    ]


def test_windows_slide_one_sentence_at_a_time():
    vensters = eenheden(TEKST, "venster2")
    assert vensters[0] == "Eerste zin over de zeespiegel Tweede zin over het ijs"
    assert len(vensters) == 3
    assert len(eenheden(TEKST, "venster3")) == 2


def test_a_document_shorter_than_its_window_is_one_unit():
    assert eenheden("Alleen deze zin hier.", "venster3") == ["Alleen deze zin hier"]


def test_the_whole_document_is_one_unit():
    assert eenheden(TEKST, "document") == [TEKST.strip()]


def test_bm25_puts_the_claim_with_the_shared_rare_words_first():
    claims = [[1, 2, 3], [1, 4, 5], [1, 6, 7, 8, 9], [10, 11]]
    index = Bm25(claims)
    assert index.top([1, 6, 7], 1)[0][0] == 2
    # Een woord dat in geen enkele claim staat, vindt niets.
    assert index.top([99], 3) == []


def test_bm25_counts_a_repeated_query_word_once():
    index = Bm25([[1, 2], [3, 4]])
    assert index.top([1, 1, 1], 1) == index.top([1], 1)


def test_a_member_of_the_target_cluster_counts_as_the_target():
    cluster_van = {"a": "k1", "b": "k1", "c": "k2"}
    assert rang(["c", "b", "a"], "a", cluster_van) == 2
    assert rang(["c"], "a", cluster_van) is None
    assert rang(["x", "a"], "a", {}) == 2


def test_the_count_says_how_many_documents_reach_each_rank():
    assert telling({"d1": 1, "d2": 4, "d3": 12, "d4": None}) == {1: 1, 5: 2, 20: 3}
