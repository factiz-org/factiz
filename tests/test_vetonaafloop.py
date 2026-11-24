"""Het veto ná het clusteren in plaats van ervóór (PLAN.md #16.2).

Het NLI-veto draaide binnen de samenvoeglus, dus op elke *poging* — ook op paren
die uiteindelijk toch niet bij elkaar kwamen. Op het huidige corpus zijn dat
394.221 kandidaatparen, oftewel ~22 uur modelwerk (BENCHMARK.md §39e).

Maar het veto kan alleen **blokkeren**, en blokkeren heeft alleen zin voor paren
die daadwerkelijk samen in een cluster zijn beland. Alle overige aanroepen zijn
verspilling: die paren zitten al niet bij elkaar.

Ná afloop toetsen is dus niet alleen goedkoper maar raakt precies de juiste
verzameling. Het is niet bit-identiek aan de oude volgorde — een pre-merge
blokkade kon een ánder cluster laten ontstaan — maar het verschil is
tweede-orde, en de uitkomst is even conservatief: er wordt nooit méér
samengevoegd dan zonder veto.
"""

import numpy as np
import pytest

from doublecheck.clustering import build_clusters, splits_op_veto
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

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
    # Drie claims die dicht genoeg liggen om één cluster te vormen.
    for naam, richting, tekst in (
        ("claim-a", [1.0, 0.00, 0.0], "brandende bus in Italië"),
        ("claim-b", [1.0, 0.05, 0.0], "brandende bus in Italie gefilmd"),
        ("claim-c", [1.0, 0.09, 0.0], "brandende bus in Londen"),
    ):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (naam, tekst),
        )
        save_text_fingerprint(conn, naam, _fp(richting))
    conn.commit()
    yield conn
    conn.close()


def _leden(conn):
    groepen: dict = {}
    for claim_id, cluster_id in conn.execute(
        "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL"
    ):
        groepen.setdefault(cluster_id, set()).add(claim_id)
    return sorted(groepen.values(), key=len, reverse=True)


def test_without_a_veto_the_three_stay_together(conn):
    build_clusters(conn, VERSIE, 0.99)
    assert _leden(conn) == [{"claim-a", "claim-b", "claim-c"}]


def test_the_veto_splits_a_cluster_afterwards(conn):
    """Italië en Londen horen niet in één cluster; de mechanische regels zien
    dat niet — geen getal, geen ontkenning (BENCHMARK.md §16)."""
    build_clusters(conn, VERSIE, 0.99)

    def veto(a, b, taal_a, taal_b):
        # Precies één van beide noemt Londen: dan gaat het over een andere bus.
        return ("Londen" in a) != ("Londen" in b)

    rapport = splits_op_veto(conn, veto)

    assert rapport.geblokkeerde_paren == 2
    groepen = _leden(conn)
    assert {"claim-a", "claim-b"} in groepen
    assert {"claim-c"} not in groepen, "een eenling hoort geen cluster te zijn"
    assert all("claim-c" not in g for g in groepen if "claim-a" in g)


def test_a_veto_that_blocks_nothing_changes_nothing(conn):
    build_clusters(conn, VERSIE, 0.99)
    voor = _leden(conn)

    rapport = splits_op_veto(conn, lambda *a: False)

    assert rapport.geblokkeerde_paren == 0
    assert _leden(conn) == voor


def test_only_pairs_that_ended_up_together_are_judged(conn):
    """De hele besparing: paren die niet samen in een cluster zitten worden
    niet aan het model voorgelegd."""
    build_clusters(conn, VERSIE, 0.99)
    gezien = []

    def veto(a, b, taal_a, taal_b):
        gezien.append((a, b))
        return False

    splits_op_veto(conn, veto)

    # Drie leden in één cluster = drie paren, en geen enkele daarbuiten.
    assert len(gezien) == 3


def test_the_cluster_state_records_the_veto_that_ran(conn):
    """Anders zegt het clusterbewuste cijfer niet waarop het slaat (#12.3)."""
    build_clusters(conn, VERSIE, 0.99)

    veto = lambda *a: False
    veto.model_version = "nli-testmodel-v1"
    splits_op_veto(conn, veto)

    rij = conn.execute("SELECT veto_version FROM cluster_state").fetchone()
    assert rij["veto_version"] == "nli-testmodel-v1"


def test_blocked_pairs_are_inspectable(conn):
    """Een telling zonder de paren is niet na te rekenen.

    De benchmark laat zijn fouten inspecteren (`--failures`); het veto deed dat
    niet, en toen de vraag kwam wát die 227 blokkades waren, was het antwoord
    niet meer te geven zonder alles opnieuw te draaien (#16.3).
    """
    build_clusters(conn, VERSIE, 0.99)

    def veto(a, b, taal_a, taal_b):
        return ("Londen" in a) != ("Londen" in b)

    rapport = splits_op_veto(conn, veto)

    assert len(rapport.geblokkeerd) == rapport.geblokkeerde_paren
    for tekst_a, tekst_b in rapport.geblokkeerd:
        assert ("Londen" in tekst_a) != ("Londen" in tekst_b)
