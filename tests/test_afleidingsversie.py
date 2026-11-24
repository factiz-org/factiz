"""Versiebewaking op afgeleide testsetdata (PLAN.md #11.5, DR6-analoog).

Aanleiding: de testset draagt `numbers` en `negations`, afgeleid van de
extractiecode. Die veroudert zodra die code verandert, en niets dwong een
herbouw af. De spatie-duizendtalregex uit etappe 8 zat nooit in de opgeslagen
testset, waardoor de runs #9 en #10 op verouderde afleidingen zijn gemeten
(BENCHMARK.md §19c).

De versie wordt uit het *gedrag* afgeleid, niet uit een handmatig nummer. De
bug ontstond juist doordat een mens eraan moest denken.
"""

import re

import numpy as np
import pytest

import doublecheck.relation as relation
from doublecheck.benchmark import run_benchmark
from doublecheck.config import Thresholds
from doublecheck.embedding import TextFingerprint
from doublecheck.relation import derivation_version
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import (
    DerivationVersionMismatchError,
    TestPair,
    ensure_testset_matches_derivation,
    save_test_pair,
)

VERSIE = "testmodel-v1"


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES"
        " ('claim-a', 'een corpusclaim over 30.000 euro', 'nl')"
    )
    save_text_fingerprint(conn, "claim-a", _fp([1.0, 0.0, 0.0]))
    yield conn
    conn.close()


@pytest.fixture
def testpaar(conn):
    save_test_pair(
        conn, TestPair("claim-a", True, "origineel", "nl", _fp([1.0, 0.0, 0.0]))
    )
    return conn


def test_version_is_stable_across_calls():
    assert derivation_version() == derivation_version()
    assert derivation_version().startswith("afleiding-")


def test_version_changes_when_negation_behaviour_changes(monkeypatch):
    voor = derivation_version()
    monkeypatch.setattr(
        relation, "_NEGATIE", re.compile(r"\b(niet|geen)\b", re.IGNORECASE)
    )
    assert derivation_version() != voor


def test_version_changes_when_number_behaviour_changes(monkeypatch):
    """11.1 wijzigde géén regex maar wel het gedrag — een patroon-hash zou dat missen."""
    voor = derivation_version()
    monkeypatch.setattr(relation, "_vouw_cijfers", lambda ruw: ruw)
    assert derivation_version() != voor


def test_new_lexicon_entry_changes_the_version_even_without_a_probe(monkeypatch):
    """Het gat dat 11.4 blootlegde.

    Bij 11.4 werden Spaanse tokens aan `_NEGATIE` toegevoegd en de versie bewóóg
    niet: geen enkele proeftekst was Spaans, dus geen enkele uitkomst veranderde.
    Een guard die erop rekent dat iemand een proef bijzet, is geen guard. De
    patronen zitten daarom óók in de hash — die twee dekken elkaars blinde vlek:
    patronen vangen een nieuw lexicon, gedrag vangt een wijziging die geen patroon
    aanraakt (#11.1).
    """
    voor = derivation_version()
    monkeypatch.setattr(
        relation,
        "_NEGATIE",
        re.compile(relation._NEGATIE.pattern + r"|\bzzzonbestaand\b", re.IGNORECASE),
    )
    assert derivation_version() != voor


def test_empty_testset_is_not_a_mismatch(conn):
    """De legitieme beginstand, net als bij een lege index (E3.S1-AC2)."""
    ensure_testset_matches_derivation(conn)


def test_current_testset_passes_the_guard(conn, testpaar):
    ensure_testset_matches_derivation(conn)


def test_stale_derivation_is_refused(conn, testpaar):
    conn.execute("UPDATE testpair SET derivation_version = 'afleiding-verouderd'")
    with pytest.raises(DerivationVersionMismatchError) as fout:
        ensure_testset_matches_derivation(conn)
    assert "herbouw" in str(fout.value)


def test_unrecorded_derivation_is_refused(conn, testpaar):
    """Een rij zonder vastgelegde versie is onbekende herkomst — juist het geval
    dat de runs #9 en #10 heeft aangetast."""
    conn.execute("UPDATE testpair SET derivation_version = ''")
    with pytest.raises(DerivationVersionMismatchError):
        ensure_testset_matches_derivation(conn)


def test_benchmark_refuses_instead_of_reporting_numbers(conn, testpaar):
    """Weigeren moet luid: nooit stil een cijfer over verouderde data."""
    conn.execute("UPDATE testpair SET derivation_version = 'afleiding-verouderd'")
    drempels = Thresholds(text_match=0.85, text_related=0.70, image_same=10)
    with pytest.raises(DerivationVersionMismatchError):
        run_benchmark(conn, drempels, VERSIE)
