"""Vertaalfixture voor cross-linguale meting (E4.S1-AC5, PLAN.md #14.7).

Herbouwd na de omzetting naar het CC BY-corpus: van de oude 44 NL/EN-paren
overleefden er 22, waarna de cross-linguale bovengrens opliep tot 19,8% en dat
cijfer niets meer droeg (BENCHMARK.md §36d).
"""

import collections
from pathlib import Path

import pytest

from doublecheck.storage import connect
from doublecheck.vertalingen import load_translations

CORPUS = Path(__file__).parent.parent / "doublecheck.db"


def test_translation_fixture_is_well_formed():
    paren = load_translations()

    assert len(paren) >= 40
    ids = [paar["claim_id"] for paar in paren]
    assert len(set(ids)) == len(ids), "dubbele claim_id in de fixture"

    for paar in paren:
        assert paar["claim_id"].startswith("gfc-")
        assert paar["bron"].strip() and paar["doel"].strip()
        assert paar["bron_taal"] != paar["doel_taal"], paar["claim_id"]
        # Een vertaling is geen kopie.
        assert paar["doel"] != paar["bron"], paar["claim_id"]
        # En geen fragment: vergelijkbare lengte-orde.
        assert 0.4 < len(paar["doel"]) / len(paar["bron"]) < 2.2, paar["claim_id"]


def test_the_fixture_covers_more_than_one_direction():
    """De oude fixture was alleen nl→en; het corpus maakt nu meer mogelijk."""
    richtingen = {
        f"{paar['bron_taal']}-{paar['doel_taal']}" for paar in load_translations()
    }
    assert len(richtingen) >= 5, richtingen
    # Ook de omgekeerde richting: Engels is nu onze grootste taal, dus een
    # niet-Engels artefact dat een Engelse claim raakt is het realistische geval.
    assert any(r.startswith("en-") for r in richtingen), richtingen


def test_every_direction_stays_within_verifiable_languages():
    """Alleen Germaans en Romaans: buiten die talen kan de opsteller een
    vertaalfout niet zien, en die corrumpeert de meting stil (§32, §34b)."""
    toegestaan = {"nl", "en", "de", "fr", "es", "pt", "it", "ca"}
    for paar in load_translations():
        assert paar["bron_taal"] in toegestaan, paar["claim_id"]
        assert paar["doel_taal"] in toegestaan, paar["claim_id"]


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus niet aanwezig")
def test_translation_fixture_matches_corpus_claims():
    """De bronkant moet létterlijk de corpusclaim zijn, anders meet de
    benchmark iets anders dan hij denkt te meten."""
    conn = connect(str(CORPUS))
    try:
        for paar in load_translations():
            rij = conn.execute(
                "SELECT canonical_text, language FROM claim WHERE claim_id = ?",
                (paar["claim_id"],),
            ).fetchone()
            assert rij is not None, f"{paar['claim_id']} niet in het corpus"
            assert rij["canonical_text"] == paar["bron"], paar["claim_id"]
            assert rij["language"] == paar["bron_taal"], paar["claim_id"]
    finally:
        conn.close()


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus niet aanwezig")
def test_no_direction_dominates_the_fixture():
    """Eén richting die alles overheerst maakt het cijfer een cijfer over die
    richting, niet over cross-linguaal matchen."""
    telling = collections.Counter(
        f"{paar['bron_taal']}-{paar['doel_taal']}" for paar in load_translations()
    )
    grootste = telling.most_common(1)[0][1]
    assert grootste / sum(telling.values()) < 0.35, telling
