"""Ontkenning tellen, niet alleen zien (PLAN.md #25.1c, BENCHMARK §65).

Run #42 liet 25 fouten over met één mechanisme: de wachter keek óf er een
ontkenning was, niet hoeveel. Een tweede ontkenning in een al ontkende zin
gleed erdoor. De regel wordt: omslag als de ontkenningen van de ene kant een
strikte deelverzameling (met herhalingen) zijn van die van de andere kant. De
oude regel (de ene kant wel, de andere niet) is daar een speciaal geval van.
"""

import json

import numpy as np

from doublecheck.embedding import TextFingerprint
from doublecheck.relation import contradicts, extract_negation_tokens
from doublecheck.storage import connect, init_schema
from doublecheck.testset import TestPair, load_test_pairs, save_test_pair


def test_tokens_keep_repetitions_and_are_sorted():
    assert extract_negation_tokens("Não é verdade que a vacina não funciona") == ("não", "não")
    assert extract_negation_tokens("Le vaccin n'est pas efficace") == ("n'", "pas")
    assert extract_negation_tokens("Het vaccin werkt") == ()


def test_a_second_negation_in_a_negated_sentence_is_a_flip():
    claim = "O ministro não disse que a vacina é perigosa"
    artefact = "O ministro não disse que a vacina não é perigosa"
    assert contradicts(frozenset(), frozenset({"não"}), claim,
                       artefact_negation_tokens=extract_negation_tokens(artefact))


def test_dropping_one_of_two_negations_is_a_flip():
    claim = "Não é verdade que a vacina não funciona"
    artefact = "Não é verdade que a vacina funciona"
    assert contradicts(frozenset(), frozenset({"não"}), claim,
                       artefact_negation_tokens=extract_negation_tokens(artefact))


def test_the_old_presence_rule_still_holds():
    assert contradicts(frozenset(), frozenset({"not"}), "The vaccine works",
                       artefact_negation_tokens=("not",))
    assert contradicts(frozenset(), frozenset({"not"}), "The vaccine works")  # zonder telling: de verzameling
    assert not contradicts(frozenset(), frozenset(), "The vaccine works",
                           artefact_negation_tokens=())


def test_a_translation_with_a_different_negation_shape_is_not_a_flip():
    """Frans 'ne … pas' is één ontkenning in twee tokens; Engels 'not' één.
    Geen van beide bevat de ander, dus geen omslag: vertalingen blijven matchen."""
    assert not contradicts(frozenset(), frozenset({"n'", "pas"}), "The vaccine is not effective",
                           artefact_negation_tokens=extract_negation_tokens("Le vaccin n'est pas efficace"))


def test_the_benchmark_path_uses_the_stored_counts_without_text():
    """De benchmark heeft geen artefacttekst (DR3) maar wel de opgeslagen telling."""
    claim = "O ministro não disse que a vacina é perigosa"
    assert contradicts(frozenset(), frozenset({"não"}), claim,
                       artefact_negation_tokens=("não", "não"))
    assert not contradicts(frozenset(), frozenset({"não"}), claim,
                           artefact_negation_tokens=("não",))


def test_the_testset_stores_and_loads_the_counts():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c', 'x', 'pt')")
    vector = np.array([1.0, 0.0], dtype=np.float32)
    fp = TextFingerprint(vector=vector, model_version="m", negations=frozenset({"não"}),
                         negation_tokens=("não", "não"))
    save_test_pair(conn, TestPair(claim_id="c", is_same=False, provenance="ontkenning",
                                  language="pt", fingerprint=fp))
    opgeslagen = conn.execute("SELECT negations FROM testpair").fetchone()[0]
    assert json.loads(opgeslagen) == ["não", "não"]
    paar = load_test_pairs(conn)[0]
    assert paar.fingerprint.negation_tokens == ("não", "não")
    assert paar.fingerprint.negations == frozenset({"não"})
