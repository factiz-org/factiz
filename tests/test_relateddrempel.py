"""Herijking van `text_related` (PLAN.md #12.5).

Bij de fingerprintwissel van etappe 12 bewogen alleen `text_match` en
`cluster_same` mee. `text_related` bleef op 0,70 uit de oude verdeling staan en
werd daarmee feitelijk lósser — dezelfde val als bij `text_match`, alleen
ongemerkt omdat de bestaande sweep die drempel niet varieert.

De maat is tweezijdig, want een drempel die alleen naar één kant kijkt is geen
afweging:
- *valse related* — een artefact zónder tegenhanger in de index krijgt tóch een
  factcheck voorgeschoteld. Gemeten door de eigen cluster uit te sluiten en te
  kijken hoe hoog de dichtstbijzijnde overgebleven buur nog komt;
- *teruggewonnen paren* — zelfde-paren die de matchdrempel niet haalden en die
  `related` alsnog zichtbaar maakt.
"""

import numpy as np
import pytest

from doublecheck.benchmark import sweep_related
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, save_test_pair

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
    # Drie claims: a en b liggen dicht bijeen (0,98), c ligt ver weg.
    richtingen = {
        "claim-a": [1.0, 0.0, 0.0],
        "claim-b": [0.98, 0.199, 0.0],
        "claim-c": [0.0, 0.0, 1.0],
    }
    for claim_id, richting in richtingen.items():
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (claim_id, f"tekst van {claim_id}"),
        )
        save_text_fingerprint(conn, claim_id, _fp(richting))
    # Een zelfde-paar dat de matchdrempel net niet haalt.
    save_test_pair(
        conn, TestPair("claim-c", True, "inkorting", "nl", _fp([0.1, 0.0, 0.86]))
    )
    yield conn
    conn.close()


def test_sweep_reports_both_sides_of_the_tradeoff(conn):
    rijen = sweep_related(conn, VERSIE, match=0.90, kandidaten=(0.70, 0.85))

    assert [r.related for r in rijen] == [0.70, 0.85]
    for rij in rijen:
        assert 0.0 <= rij.valse_related_aandeel <= 1.0
        assert 0 <= rij.teruggewonnen <= rij.gemiste_paren


def test_raising_the_threshold_never_increases_false_related(conn):
    rijen = sweep_related(conn, VERSIE, match=0.90, kandidaten=(0.60, 0.75, 0.90))
    aandelen = [r.valse_related_aandeel for r in rijen]
    assert aandelen == sorted(aandelen, reverse=True)


def test_raising_the_threshold_never_recovers_more_pairs(conn):
    rijen = sweep_related(conn, VERSIE, match=0.90, kandidaten=(0.60, 0.75, 0.90))
    teruggewonnen = [r.teruggewonnen for r in rijen]
    assert teruggewonnen == sorted(teruggewonnen, reverse=True)


def test_a_claim_is_never_its_own_neighbour(conn):
    """De eigen claim uitsluiten is de kern: anders meet je gelijkenis met jezelf."""
    rijen = sweep_related(conn, VERSIE, match=0.90, kandidaten=(0.999,))
    assert rijen[0].valse_related_aandeel < 1.0


def test_sweep_changes_no_configuration(conn):
    """Een sweep is een experiment, geen configwijziging (DR6)."""
    from doublecheck.config import load_config

    voor = load_config().thresholds.text_related
    sweep_related(conn, VERSIE, match=0.90, kandidaten=(0.70, 0.85))
    assert load_config().thresholds.text_related == voor
