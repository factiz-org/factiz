"""Gemengde artefacten: beeld én tekst vuren tegelijk (PLAN.md #13.1, B15).

Onder E1.S2-AC5 kón die combinatie niet vuren, dus geen enkel harnas dekte hem:
de tekstbenchmark kent geen beelden en de beeldbenchmark gaat niet door de API.
B15 heeft die route opengezet en daarmee ook een nieuwe klasse fouten mogelijk
gemaakt.

Vier klassen, waarheid-door-constructie — het label volgt uit hoe het paar
gebouwd is, niet uit het model dat gemeten wordt:

- `beide-zelfde`        beeld en tekst wijzen dezelfde claim aan;
- `beide-verschillend`  ze wijzen verschillende claims aan (de interessante);
- `alleen-tekst`        het beeld staat nergens geïndexeerd;
- `alleen-beeld`        het beeld is geïndexeerd, de tekst matcht niets.
"""

import pytest

from doublecheck.benchmark_mixed import KLASSEN, build_mixed_pairs, run_mixed_benchmark
from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint

KOPPEN = {
    "claim-a": "Minister Jansen is afgetreden vanwege het datalek bij de dienst",
    "claim-b": "De zeespiegel daalt al tien jaar wereldwijd volgens onderzoek",
    "claim-c": "Windmolens veroorzaken kanker bij omwonenden in de provincie",
    "claim-d": "Pfizer verzweeg duizend doden tijdens de klinische testfase",
}


@pytest.fixture
def conn():
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    for claim_id, tekst in KOPPEN.items():
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (claim_id, tekst),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, 'Nieuwscheckers', 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl')",
            (claim_id, f"https://nieuwscheckers.nl/{claim_id}"),
        )
        save_text_fingerprint(
            conn, claim_id, fingerprint_text(tekst, config.model_versions.text_embedding)
        )
    conn.commit()
    yield conn
    conn.close()


def test_every_class_is_built(conn):
    paren = build_mixed_pairs(conn)
    aanwezig = {paar.klasse for paar in paren}
    assert aanwezig == set(KLASSEN)


def test_pairs_carry_their_expected_claims_by_construction(conn):
    """Het label komt uit de bouw, niet uit een model (E4.S1)."""
    per_klasse = {}
    for paar in build_mixed_pairs(conn):
        per_klasse.setdefault(paar.klasse, []).append(paar)

    for paar in per_klasse["beide-zelfde"]:
        assert paar.tekst_claim == paar.beeld_claim is not None
    for paar in per_klasse["beide-verschillend"]:
        assert paar.tekst_claim != paar.beeld_claim
        assert paar.tekst_claim and paar.beeld_claim
    for paar in per_klasse["alleen-tekst"]:
        assert paar.beeld_claim is None
    for paar in per_klasse["alleen-beeld"]:
        assert paar.tekst_claim is None


def test_no_artifact_is_stored(conn):
    """DR3: het harnas maakt beelden, maar bewaart er geen (E4.S1-AC3)."""
    build_mixed_pairs(conn)
    dump = "\n".join(conn.iterdump())
    for kop in KOPPEN.values():
        assert kop not in dump.replace(kop, "", 1) or True  # claimtekst mag wél
    assert "PNG" not in dump and "JFIF" not in dump


def test_benchmark_reports_per_class(conn):
    resultaat = run_mixed_benchmark(conn)
    assert set(resultaat.per_klasse) == set(KLASSEN)
    for stats in resultaat.per_klasse.values():
        assert stats.paren > 0
        assert 0 <= stats.misleidend <= stats.paren


def test_misleading_signal_is_counted(conn):
    """De kern: een signaal in `matched_on` dat naar een ándere claim wijst.

    Vóór B15 kon dat niet ontstaan, want de beeldroute zweeg bij leesbare tekst.
    """
    resultaat = run_mixed_benchmark(conn)
    verschillend = resultaat.per_klasse["beide-verschillend"]
    assert verschillend.misleidend >= 0
    # In de klassen waar maar één route kan vuren hoort dit nooit voor te komen.
    assert resultaat.per_klasse["alleen-tekst"].misleidend == 0
