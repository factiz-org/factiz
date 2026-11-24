"""Kritieke afdwinging: clustering voegt nooit een claim en zijn ontkenning samen.

Dit is het ergst denkbare resultaat van clustering: dan krijgt een bewering het
oordeel van zijn tegendeel opgeplakt — precies het incident uit B5, maar dan
ingebakken in de index in plaats van in één respons (E2.S5 kritiek AC, DR8).
"""

import numpy as np
import pytest

from doublecheck.clustering import build_clusters, cluster_members
from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.seed import load_seed, seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint

PAAR = ("seed-jansen-afgetreden", "seed-jansen-niet-afgetreden")


@pytest.fixture
def conn():
    """Het echte seed-corpus met echte embeddings — geen synthetische vectoren."""
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    for claim in load_seed():
        save_text_fingerprint(
            conn,
            claim["claim_id"],
            fingerprint_text(
                claim["canonical_text"], config.model_versions.text_embedding
            ),
        )
    conn.commit()
    yield conn
    conn.close()


def test_negation_pair_never_shares_a_cluster(conn):
    config = load_config()
    wel, niet = PAAR

    # Ook bij een drempel die ver onder hun similariteit ligt (0,866).
    for drempel in (0.95, 0.90, 0.85, 0.80):
        build_clusters(
            conn, config.model_versions.text_embedding, threshold=drempel
        )
        leden = cluster_members(conn, wel)
        assert niet not in leden, (
            f"ontkenningspaar samengevoegd bij drempel {drempel}: {leden}"
        )


def test_the_pair_is_close_enough_that_this_test_matters(conn):
    """Zonder deze controle zou de test ook slagen als het paar ver uit elkaar lag."""
    config = load_config()
    versie = config.model_versions.text_embedding
    vectoren = {
        rij["claim_id"]: np.frombuffer(rij["payload"], dtype=np.float32)
        for rij in conn.execute(
            "SELECT claim_id, payload FROM fingerprint WHERE model_version = ?",
            (versie,),
        )
    }

    similariteit = float(vectoren[PAAR[0]] @ vectoren[PAAR[1]])
    assert similariteit > 0.80, similariteit
