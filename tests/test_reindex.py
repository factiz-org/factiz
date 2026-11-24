"""Herindexeren na een fingerprintversiewissel (PLAN.md #12.2, DR6).

Etappe 12 verandert wat het model te zien krijgt, dus de fingerprintversie gaat
omhoog en de bestaande index is onbruikbaar — de resolver weigert dan luid
(E2.S3-AC2). Tot nu toe was herimporteren via de API de enige weg terug; dat is
traag, verbruikt quota en hangt af van wat de bron nú nog teruggeeft.

Herindexeren werkt op de claimtekst die we al hebben. Additief: oude
fingerprints blijven staan, zodat een halve run niets sloopt.
"""

import numpy as np
import pytest

from doublecheck.embedding import TextFingerprint, fingerprint_texts
from doublecheck.reindex import reindex_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint

OUD = "oud-model-v1"
NIEUW = "nieuw-model-v2"


def _fp(richting, versie):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return TextFingerprint(vector=vector, model_version=versie)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    for i, tekst in enumerate(["eerste claim", "tweede claim", "derde claim"]):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (f"claim-{i}", tekst),
        )
        save_text_fingerprint(conn, f"claim-{i}", _fp([1.0, i + 1.0, 0.0], OUD))
    yield conn
    conn.close()


def _nep_fingerprinter(teksten, model_version):
    return [_fp([len(t), 1.0, 0.0], model_version) for t in teksten]


def test_reindex_adds_a_fingerprint_for_every_claim(conn):
    rapport = reindex_text(conn, NIEUW, fingerprinter=_nep_fingerprinter)

    assert rapport.nieuwe_fingerprints == 3
    aantal = conn.execute(
        "SELECT count(*) FROM fingerprint WHERE model_version = ?", (NIEUW,)
    ).fetchone()[0]
    assert aantal == 3


def test_reindex_keeps_the_old_version(conn):
    """Additief: een halve run mag de werkende index niet slopen."""
    reindex_text(conn, NIEUW, fingerprinter=_nep_fingerprinter)

    oud = conn.execute(
        "SELECT count(*) FROM fingerprint WHERE model_version = ?", (OUD,)
    ).fetchone()[0]
    assert oud == 3


def test_reindex_is_resumable(conn):
    """Twee keer draaien levert geen dubbele fingerprints."""
    reindex_text(conn, NIEUW, fingerprinter=_nep_fingerprinter)
    tweede = reindex_text(conn, NIEUW, fingerprinter=_nep_fingerprinter)

    assert tweede.nieuwe_fingerprints == 0
    assert tweede.al_aanwezig == 3
    aantal = conn.execute(
        "SELECT count(*) FROM fingerprint WHERE model_version = ?", (NIEUW,)
    ).fetchone()[0]
    assert aantal == 3


def test_reindex_writes_no_artifact_text(conn):
    """DR3 blijft gelden: de index draagt vectoren, geen tekst uit het wild."""
    reindex_text(conn, NIEUW, fingerprinter=_nep_fingerprinter)
    kolommen = {rij["name"] for rij in conn.execute("PRAGMA table_info(fingerprint)")}
    assert kolommen == {"fingerprint_id", "claim_id", "kind", "model_version", "payload"}


def test_batch_fingerprinting_matches_one_by_one():
    """Het batchpad mag geen ándere vectoren opleveren dan het losse pad."""
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_text

    versie = load_config().model_versions.text_embedding
    teksten = ["Het vaccin bevat microchips", "HET VACCIN BEVAT MICROCHIPS"]

    los = [fingerprint_text(t, versie) for t in teksten]
    gebatcht = fingerprint_texts(teksten, versie)

    for a, b in zip(los, gebatcht):
        assert np.allclose(a.vector, b.vector, atol=1e-6)
        assert a.numbers == b.numbers and a.negations == b.negations
        assert b.model_version == versie


# --- Oordelen opnieuw afleiden (PLAN.md #18.1) ------------------------------


def _corpus_met_oordelen(paren):
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    for nummer, (origineel, opgeslagen, taal) in enumerate(paren):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (f"c{nummer}", f"Bewering {nummer}", taal),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source)"
            " VALUES (?, 'Uitgever', ?, ?, ?, '2024-01-01', ?, 'datacommons-ccby')",
            (f"c{nummer}", opgeslagen, origineel, f"https://example.org/{nummer}", taal),
        )
    conn.commit()
    return conn


def test_verdicts_are_rederived_when_the_table_learns_a_language():
    """De tabel groeide van twee talen naar zestien (#18.1); een corpus dat
    daarvóór is geïmporteerd draagt nog de oude `onbekend`-waarden, en juist
    daar leunt DR7 op."""
    from doublecheck.reindex import reindex_verdicts

    conn = _corpus_met_oordelen([
        ("Falso", "onbekend", "pt"),
        ("誤り", "onbekend", "ja"),
        ("False", "onwaar", "en"),        # stond al goed
        ("5", "onbekend", "en"),          # blijft onbekend: geen legenda
    ])
    rapport = reindex_verdicts(conn)

    assert rapport.herzien == 2
    assert rapport.ongewijzigd == 2
    uitkomst = dict(conn.execute(
        "SELECT verdict_original, verdict_normalized FROM factcheck"))
    assert uitkomst == {
        "Falso": "onwaar",
        "誤り": "onwaar",
        "False": "onwaar",
        "5": "onbekend",
    }
    conn.close()


def test_rederiving_verdicts_never_touches_what_the_publisher_wrote():
    """`verdict_original` is van de uitgever. Wij leiden er alleen uit af (DR1)."""
    from doublecheck.reindex import reindex_verdicts

    origineel = ["Falso", "Yanlış ", "Das angebliche Gewinnspiel"]
    conn = _corpus_met_oordelen([(o, "onbekend", "xx") for o in origineel])
    reindex_verdicts(conn)
    bewaard = [rij[0] for rij in conn.execute(
        "SELECT verdict_original FROM factcheck ORDER BY factcheck_id")]
    assert bewaard == origineel
    conn.close()


def test_rederiving_reads_a_scale_label_with_the_legend_of_its_host():
    """#25.3b: "Three Pinocchios" is pas iets op washingtonpost.com."""
    from doublecheck.reindex import reindex_verdicts

    conn = _corpus_met_oordelen([("Three Pinocchios", "onbekend", "en"), ("Exagerado", "onbekend", "pt")])
    conn.execute("UPDATE factcheck SET url = 'https://www.washingtonpost.com/politics/x/'"
                 " WHERE verdict_original = 'Three Pinocchios'")
    conn.commit()
    reindex_verdicts(conn)
    uitkomst = dict(conn.execute("SELECT verdict_original, verdict_normalized FROM factcheck"))
    assert uitkomst == {"Three Pinocchios": "deels-waar", "Exagerado": "onbekend"}   # Exagerado: niet op lupa
    conn.close()
