"""Kan het model deze taal überhaupt representeren? (PLAN.md #16.1, DR6, B5)

Ontdekt bij het schaalonderzoek van etappe 16. Het embeddingmodel zet in Tamil,
Telugu en Bengaals **verschillende** claims op mediaan 0,73–0,78 gelijkenis,
tegen 0,08–0,21 in de andere corpustalen. Gevolg: 71% van de artefacten in die
talen krijgt een dichtste buur boven de matchdrempel — een zelfverzekerde
`matched` op een willekeurige andere bewering (BENCHMARK.md §39).

B14 zei dat een taal zónder eigen benchmark in de index mag zitten "zonder
precisiebelofte". Dat bleek niet houdbaar: in de index zitten betekent kandidaat
zijn, en een onbruikbare kandidaat is schadelijker dan een afwezige.

De maat is modelgebonden en hoort dus bij de modelversie (DR6): een ander model
kan deze talen wél aan, en dan moet opnieuw gemeten worden.
"""

import numpy as np
import pytest

from doublecheck.taalgeschiktheid import (
    ONBRUIKBARE_TALEN,
    is_bruikbaar,
    meet_onderscheid,
)


def test_a_language_where_different_claims_look_alike_is_unusable():
    """De kern: kan het model twee ándere beweringen uit elkaar houden?"""
    assert is_bruikbaar(0.09) is True
    assert is_bruikbaar(0.21) is True
    assert is_bruikbaar(0.73) is False
    assert is_bruikbaar(0.78) is False


def test_the_measured_languages_are_recorded_with_their_model():
    """De lijst is een meetuitkomst, geen mening, en hoort bij één modelversie.

    Onder MiniLM klapten negen talen ineen (§39, §41). Onder bge-m3 houdt het
    model ze uit elkaar en zijn ze toegelaten (#25.18); de lijst van
    onbruikbare talen is daarmee leeg, en dat is zelf een meetuitkomst.
    """
    from doublecheck.taalgeschiktheid import GEMETEN_BRUIKBAAR

    assert not ONBRUIKBARE_TALEN
    for taal in ("ta", "te", "bn", "as", "km", "kn", "ml", "pa", "si"):
        assert taal in GEMETEN_BRUIKBAAR


def test_measurement_separates_a_collapsed_language_from_a_healthy_one():
    """Twee kunstmatige talen: één met spreiding, één ineengeklapt."""
    rng = np.random.default_rng(0)

    gezond = rng.normal(size=(60, 32)).astype(np.float32)
    gezond /= np.linalg.norm(gezond, axis=1, keepdims=True)

    # Ineengeklapt: alle vectoren dicht bij één richting.
    kern = rng.normal(size=32).astype(np.float32)
    ineen = kern + 0.08 * rng.normal(size=(60, 32)).astype(np.float32)
    ineen /= np.linalg.norm(ineen, axis=1, keepdims=True)

    assert meet_onderscheid(gezond) < 0.4
    assert meet_onderscheid(ineen) > 0.9


def test_too_little_material_yields_no_verdict():
    """Liever geen oordeel dan een oordeel op vijf claims."""
    rng = np.random.default_rng(1)
    weinig = rng.normal(size=(5, 32)).astype(np.float32)
    weinig /= np.linalg.norm(weinig, axis=1, keepdims=True)

    assert meet_onderscheid(weinig) is None


def test_import_refuses_claims_in_an_unusable_language(monkeypatch):
    """Niet importeren is de enige veilige stand: in de index zitten betekent
    kandidaat zijn, en een onbruikbare kandidaat is schadelijker dan geen.

    Gesimuleerd met Tamil zoals het onder MiniLM was (§39); onder bge-m3 is
    Tamil toegelaten (#25.18)."""
    import doublecheck.taalgeschiktheid as tg

    monkeypatch.setattr(tg, "GEMETEN_BRUIKBAAR", tg.GEMETEN_BRUIKBAAR - {"ta"})
    monkeypatch.setattr(tg, "ONBRUIKBARE_TALEN", frozenset({"ta"}))
    from doublecheck.factchecktools import RawClaim, RawFactcheck
    from doublecheck.feed import HERDISTRIBUEERBAAR
    from doublecheck.ingest import import_claims
    from doublecheck.storage import connect, init_schema

    class _Nep:
        model_version = "testmodel-v1"

        def __call__(self, tekst):
            from doublecheck.embedding import TextFingerprint

            vector = np.ones(3, dtype=np.float32) / np.sqrt(3)
            vector.setflags(write=False)
            return TextFingerprint(vector=vector, model_version="testmodel-v1")

    def _claim(tekst, taal):
        return RawClaim(text=tekst, claimant=None, claim_date=None, factchecks=(
            RawFactcheck(publisher="X", publisher_site="x.nl",
                         url=f"https://x.nl/{taal}", review_date="2024-01-01",
                         verdict_original="Onjuist", language=taal),))

    conn = connect(":memory:")
    init_schema(conn)
    try:
        rapport = import_claims(
            conn,
            [_claim("Een gewone Nederlandse bewering over vaccins", "nl"),
             _claim("ஒரு தமிழ் கூற்று", "ta")],
            fingerprinter=_Nep(), source=HERDISTRIBUEERBAAR,
        )
        assert rapport.accepted_claims == 1
        assert "onbruikbare_taal" in {w.reason for w in rapport.refusals}
        talen = {r[0] for r in conn.execute("SELECT language FROM claim")}
        assert talen == {"nl"}
    finally:
        conn.close()


def test_the_corpus_measurement_uses_only_the_configured_model(tmp_path):
    """Na een modelwissel staan twee versies naast elkaar (DR6 staat dat toe);
    de meting mag ze nooit door elkaar halen (#25.14c)."""
    from doublecheck.storage import connect, init_schema
    from doublecheck.taalgeschiktheid import vectoren_per_taal

    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    for i in range(3):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')", (f"c{i}", f"tekst {i}"))
        conn.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload) VALUES (?, 'text', 'oud', ?)",
                     (f"c{i}", np.ones(4, dtype=np.float32).tobytes()))
        conn.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload) VALUES (?, 'text', 'nieuw', ?)",
                     (f"c{i}", np.full(8, i, dtype=np.float32).tobytes()))
    conn.commit()
    per_taal = vectoren_per_taal(conn, "nieuw")
    assert set(per_taal) == {"nl"}
    assert per_taal["nl"].shape == (3, 8)
