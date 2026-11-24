"""Semantische clustering (E2.S5, DR7 — PLAN.md #9.2)."""

import numpy as np
import pytest

from doublecheck.clustering import build_clusters, cluster_members
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

VERSIE = "testmodel-v1"


def _fp(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=VERSIE)


def _claim(conn, claim_id, tekst, richting, taal="nl"):
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
        (claim_id, tekst, taal),
    )
    save_text_fingerprint(conn, claim_id, _fp(richting))


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def test_same_claim_different_wording_shares_a_cluster(conn):
    _claim(conn, "a", "Dit zijn beelden van de aardbeving in Turkije", [1.0, 0.0, 0.0])
    _claim(conn, "b", "Dit zijn beelden van de recente aardbeving in Turkije",
           [0.999, 0.045, 0.0])
    _claim(conn, "c", "Vrouwen genieten meer van wijn dan mannen", [0.0, 0.0, 1.0])
    conn.commit()

    rapport = build_clusters(conn, VERSIE, threshold=0.90)

    assert cluster_members(conn, "a") == {"a", "b"}
    assert cluster_members(conn, "c") == {"c"}
    assert rapport.clusters_with_multiple_members == 1


def test_contradiction_blocks_a_merge(conn):
    """DR8: dicht bij elkaar, maar het tegendeel — nooit samenvoegen."""
    _claim(conn, "wel", "Minister Jansen is afgetreden", [1.0, 0.0, 0.0])
    _claim(conn, "niet", "Minister Jansen is niet afgetreden", [0.999, 0.045, 0.0])
    conn.commit()

    build_clusters(conn, VERSIE, threshold=0.90)

    assert cluster_members(conn, "wel") == {"wel"}
    assert cluster_members(conn, "niet") == {"niet"}


def test_complete_linkage_prevents_chaining(conn):
    """A~B en B~C, maar A niet met C: dan geen cluster van drie."""
    _claim(conn, "a", "eerste bewering over treinen", [1.0, 0.0, 0.0])
    _claim(conn, "b", "tweede bewering over treinen", [0.96, 0.28, 0.0])
    _claim(conn, "c", "derde bewering over treinen", [0.85, 0.53, 0.0])
    conn.commit()

    build_clusters(conn, VERSIE, threshold=0.93)

    leden = cluster_members(conn, "a")
    assert "c" not in leden, "keten A~B~C mag niet één cluster worden"
    assert len(leden) <= 2


def test_clustering_only_uses_one_model_version(conn):
    _claim(conn, "a", "een bewering", [1.0, 0.0, 0.0])
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('b', 'een bewering', 'nl')"
    )
    save_text_fingerprint(
        conn, "b",
        TextFingerprint(vector=_fp([1.0, 0.0, 0.0]).vector, model_version="ander-model"),
    )
    conn.commit()

    build_clusters(conn, VERSIE, threshold=0.90)

    assert cluster_members(conn, "a") == {"a"}


def test_threshold_comes_from_config():
    config = load_config()

    assert 0.0 < config.thresholds.cluster_same <= 1.0
    # Clusteren hoort strenger te zijn dan matchen: samenvoegen is ingrijpender.
    assert config.thresholds.cluster_same >= config.thresholds.text_match


def test_clustering_is_idempotent(conn):
    _claim(conn, "a", "Dit zijn beelden van de aardbeving in Turkije", [1.0, 0.0, 0.0])
    _claim(conn, "b", "Dit zijn beelden van de recente aardbeving in Turkije",
           [0.999, 0.045, 0.0])
    conn.commit()

    eerste = build_clusters(conn, VERSIE, threshold=0.90)
    tweede = build_clusters(conn, VERSIE, threshold=0.90)

    assert eerste.clusters_with_multiple_members == tweede.clusters_with_multiple_members
    assert cluster_members(conn, "a") == {"a", "b"}


def test_nli_veto_blocks_a_merge(conn):
    """Het veto houdt een samenvoeging tegen die de mechanische regels doorlieten."""
    _claim(conn, "a", "Studenten voeren actie voor de boeren", [1.0, 0.0, 0.0])
    _claim(conn, "b", "Studenten protesteren tegen de boeren", [0.999, 0.045, 0.0])
    conn.commit()

    # Zonder veto: samengevoegd (geen negatiewoord, geen getalconflict).
    build_clusters(conn, VERSIE, threshold=0.90)
    assert cluster_members(conn, "a") == {"a", "b"}

    # Mét veto: tegengehouden.
    rapport = build_clusters(
        conn, VERSIE, threshold=0.90,
        veto=lambda x, y, la, lb: "voor de boeren" in x and "tegen de boeren" in y,
    )

    assert cluster_members(conn, "a") == {"a"}
    assert rapport.blocked_by_veto == 1


def test_nli_veto_never_creates_a_merge(conn):
    """Cruciaal: het veto mag alleen tegenhouden, nooit toestaan.

    Een veto dat altijd 'nee, geen tegenspraak' zegt, mag geen enkele claim
    samenvoegen die zonder veto apart was gebleven.
    """
    _claim(conn, "a", "Een bewering over treinen", [1.0, 0.0, 0.0])
    _claim(conn, "b", "Iets totaal anders over wijn", [0.0, 0.0, 1.0])
    _claim(conn, "wel", "Minister Jansen is afgetreden", [0.5, 0.86, 0.0])
    _claim(conn, "niet", "Minister Jansen is niet afgetreden", [0.5, 0.859, 0.02])
    conn.commit()

    zonder = build_clusters(conn, VERSIE, threshold=0.90)
    leden_zonder = {c: cluster_members(conn, c) for c in ("a", "b", "wel", "niet")}

    # Een veto dat nooit blokkeert mag exact hetzelfde resultaat geven.
    met = build_clusters(conn, VERSIE, threshold=0.90, veto=lambda x, y, la, lb: False)
    leden_met = {c: cluster_members(conn, c) for c in ("a", "b", "wel", "niet")}

    assert leden_met == leden_zonder
    assert met.clusters_with_multiple_members == zonder.clusters_with_multiple_members


def test_veto_runs_after_the_mechanical_rules(conn):
    """Het veto is een extra slot, geen vervanging: DR8 blijft eerst blokkeren."""
    _claim(conn, "wel", "Minister Jansen is afgetreden", [1.0, 0.0, 0.0])
    _claim(conn, "niet", "Minister Jansen is niet afgetreden", [0.999, 0.045, 0.0])
    conn.commit()

    geraadpleegd = []

    def veto(x, y, la, lb):
        geraadpleegd.append((x, y))
        return False

    build_clusters(conn, VERSIE, threshold=0.90, veto=veto)

    # DR8 hield het al tegen, dus het dure model is niet eens geraadpleegd.
    assert geraadpleegd == []
    assert cluster_members(conn, "wel") == {"wel"}



def test_veto_can_restrict_itself_to_one_language(conn):
    """De taalbeperking hoort in het veto, niet in de clusteringlogica."""
    _claim(conn, "nl", "Het WEF roept op de Bijbel te herschrijven met AI", [1.0, 0.0, 0.0])
    _claim(conn, "de", "WEF fordert, dass KI die Bibel umschreibt", [0.999, 0.045, 0.0],
           taal="de")
    conn.commit()

    gezien = []

    def veto(a, b, taal_a, taal_b):
        gezien.append((taal_a, taal_b))
        return taal_a == taal_b

    build_clusters(conn, VERSIE, threshold=0.90, veto=veto)

    assert gezien == [("de", "nl")] or gezien == [("nl", "de")]
    # Verschillende talen: het veto liet het door, dus samengevoegd.
    assert cluster_members(conn, "nl") == {"nl", "de"}


def test_block_size_does_not_change_the_outcome(monkeypatch):
    """Regressie: `matrix @ matrix.T` was 28,9 GB bij 85.099 claims (#16.3).

    De volle matrix is niet nodig — de koppelingscontrole vraagt alleen óf een
    paar boven de drempel ligt, en dat is precies de kandidatenlijst. Blokgewijs
    rekenen mag de uitkomst dan niet veranderen, en dát is hier de test: de
    blokgrootte is een geheugenknop, geen gedragsknop.
    """
    import numpy as np

    import doublecheck.clustering as clustering

    def _vul(conn):
        init_schema(conn)
        for nummer in range(60):
            naam = f"claim-{nummer:02d}"
            conn.execute(
                "INSERT INTO claim (claim_id, canonical_text, language)"
                " VALUES (?, ?, 'nl')",
                (naam, f"bewering nummer {nummer} over vaccins en microchips"),
            )
            richting = np.zeros(8, dtype=np.float32)
            richting[nummer % 8] = 1.0
            richting[(nummer + 1) % 8] = 0.4
            richting /= np.linalg.norm(richting)
            richting.setflags(write=False)
            save_text_fingerprint(
                conn, naam, TextFingerprint(vector=richting, model_version=VERSIE)
            )
        conn.commit()

    def _clusters(blok):
        monkeypatch.setattr(clustering, "_BLOK", blok)
        conn = connect(":memory:")
        _vul(conn)
        build_clusters(conn, VERSIE, 0.9)
        groepen = {}
        for claim_id, cluster_id in conn.execute(
            "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL"
        ):
            groepen.setdefault(cluster_id, set()).add(claim_id)
        conn.close()
        return sorted((sorted(g) for g in groepen.values()))

    # Eén blok dat alles omvat, tegenover blokjes van zeven rijen.
    assert _clusters(1000) == _clusters(7)
