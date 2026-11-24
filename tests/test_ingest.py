import hashlib

import numpy as np
import pytest

from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.feed import API_GEBONDEN
from doublecheck.ingest import import_claims
from doublecheck.storage import connect, init_schema


class NepFingerprinter:
    """Deterministische nep-embedder zodat de importtests snel blijven."""

    def __init__(self, model_version="testmodel-v1"):
        self.model_version = model_version

    def __call__(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()[:8]
        vector = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
        vector = vector / np.linalg.norm(vector)
        return TextFingerprint(vector=vector, model_version=self.model_version)


NEP = NepFingerprinter()


def _importeer(conn, claims, fingerprinter=NEP):
    return import_claims(conn, claims, fingerprinter=fingerprinter, source=API_GEBONDEN)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


def _check(publisher="Nieuwscheckers", url="https://nieuwscheckers.nl/factcheck/x",
           review_date="2021-05-04T00:00:00Z", verdict="Onjuist", language="nl"):
    return RawFactcheck(
        publisher=publisher,
        publisher_site=None,
        url=url,
        review_date=review_date,
        verdict_original=verdict,
        language=language,
    )


def _claim(text="Coronavaccins veranderen je DNA", factchecks=None):
    return RawClaim(
        text=text,
        claimant=None,
        claim_date=None,
        factchecks=tuple(factchecks if factchecks is not None else [_check()]),
    )


def test_import_stores_complete_claims(conn):
    rapport = _importeer(conn, [_claim()])

    assert rapport.accepted_claims == 1
    assert rapport.accepted_factchecks == 1
    assert rapport.refusals == ()

    rij = conn.execute(
        "SELECT claim.canonical_text, claim.language, factcheck.publisher,"
        " factcheck.url, factcheck.review_date, factcheck.verdict_original"
        " FROM claim JOIN factcheck ON factcheck.claim_id = claim.claim_id"
    ).fetchone()
    assert rij["canonical_text"] == "Coronavaccins veranderen je DNA"
    assert rij["language"] == "nl"
    assert rij["publisher"] == "Nieuwscheckers"
    assert rij["url"] == "https://nieuwscheckers.nl/factcheck/x"
    assert rij["review_date"] == "2021-05-04"
    assert rij["verdict_original"] == "Onjuist"


def test_import_rejects_claim_without_publisher(conn):
    rapport = _importeer(conn, [_claim(factchecks=[_check(publisher=None)])])

    assert rapport.accepted_claims == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 0

    redenen = [weigering.reason for weigering in rapport.refusals]
    assert "geen_uitgever" in redenen
    assert "geen_geldige_factchecks" in redenen


def test_import_rejects_factcheck_without_url(conn):
    """Een bron zonder URL is niet aanwijsbaar en gaat er dus uit (DR1).

    De datum-eis is hier vervallen: 10,3% van de CC BY-feed draagt geen
    `datePublished`, en een factcheck zonder datum is nog steeds een factcheck
    (BENCHMARK.md §36a, PO 2026-08-30).
    """
    rapport = _importeer(conn, [
        _claim(text="claim zonder url", factchecks=[_check(url=None)]),
        _claim(text="claim zonder datum", factchecks=[_check(review_date=None)]),
    ])

    assert rapport.accepted_claims == 1, "de datumloze claim hoort erin te komen"
    assert {weigering.reason for weigering in rapport.refusals} == {
        "geen_url",
        "geen_geldige_factchecks",
    }
    bewaard = conn.execute(
        "SELECT canonical_text, review_date FROM claim"
        " JOIN factcheck USING (claim_id)").fetchone()
    assert bewaard["canonical_text"] == "claim zonder datum"
    assert bewaard["review_date"] == ""


def test_partial_claim_keeps_valid_checks_and_logs_rest(conn):
    rapport = _importeer(conn, [
        _claim(factchecks=[
            _check(),
            _check(publisher="AFP Factcheck Nederland", url=None),
        ])
    ])

    assert rapport.accepted_claims == 1
    assert rapport.accepted_factchecks == 1
    assert len(rapport.refusals) == 1
    weigering = rapport.refusals[0]
    assert weigering.reason == "geen_url"
    assert weigering.publisher == "AFP Factcheck Nederland"
    assert weigering.claim_text == "Coronavaccins veranderen je DNA"

    aantal = conn.execute("SELECT COUNT(*) AS n FROM factcheck").fetchone()["n"]
    assert aantal == 1


def test_reimport_creates_no_duplicate(conn):
    _importeer(conn, [_claim()])
    rapport = _importeer(conn, [_claim()])

    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM factcheck").fetchone()["n"] == 1
    assert rapport.accepted_claims == 0
    assert rapport.accepted_factchecks == 0
    assert rapport.existing_claims == 1
    assert rapport.duplicate_factchecks == 1


def test_reimport_adds_new_factcheck_to_existing_claim(conn):
    _importeer(conn, [_claim()])
    rapport = _importeer(conn, [
        _claim(factchecks=[
            _check(),
            _check(publisher="AFP Factcheck Nederland",
                   url="https://factchecknederland.afp.com/vaccin-dna"),
        ])
    ])

    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM factcheck").fetchone()["n"] == 2
    assert rapport.accepted_claims == 0
    assert rapport.accepted_factchecks == 1
    assert rapport.duplicate_factchecks == 1


def test_same_text_in_other_casing_or_whitespace_is_same_claim(conn):
    _importeer(conn, [_claim(text="Coronavaccins veranderen je DNA")])
    _importeer(conn, [
        _claim(text="  coronavaccins   veranderen je dna ",
               factchecks=[_check(url="https://nieuwscheckers.nl/factcheck/y")])
    ])

    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 1
    tekst = conn.execute("SELECT canonical_text FROM claim").fetchone()["canonical_text"]
    assert tekst == "Coronavaccins veranderen je DNA"


def test_imported_claim_has_fingerprint(conn):
    # Bewust mét de echte standaard-fingerprinter: de vastgelegde modelversie
    # moet exact die zijn die de resolver gebruikt (config, DR6).
    import_claims(conn, [_claim()], source=API_GEBONDEN)

    rij = conn.execute(
        "SELECT kind, model_version, payload FROM fingerprint"
    ).fetchone()
    assert rij["kind"] == "text"
    assert rij["model_version"] == load_config().model_versions.text_embedding
    assert len(rij["payload"]) > 0


def test_reimport_does_not_duplicate_fingerprint(conn):
    eerste = _importeer(conn, [_claim()])
    tweede = _importeer(conn, [_claim()])

    aantal = conn.execute("SELECT COUNT(*) AS n FROM fingerprint").fetchone()["n"]
    assert aantal == 1
    assert eerste.new_fingerprints == 1
    assert tweede.new_fingerprints == 0


def test_reimport_after_model_switch_adds_new_version_fingerprint(conn):
    _importeer(conn, [_claim()], fingerprinter=NepFingerprinter("model-v1"))
    _importeer(conn, [_claim()], fingerprinter=NepFingerprinter("model-v2"))

    versies = {
        rij["model_version"]
        for rij in conn.execute("SELECT model_version FROM fingerprint")
    }
    assert versies == {"model-v1", "model-v2"}


def test_claim_id_is_stable_for_same_text():
    een = connect(":memory:")
    twee = connect(":memory:")
    init_schema(een)
    init_schema(twee)

    _importeer(een, [_claim()])
    _importeer(twee, [_claim()])

    id_een = een.execute("SELECT claim_id FROM claim").fetchone()["claim_id"]
    id_twee = twee.execute("SELECT claim_id FROM claim").fetchone()["claim_id"]
    assert id_een == id_twee
    een.close()
    twee.close()


def test_url_only_claim_is_refused(conn):
    """Een claimtekst die alleen een URL is, bevat geen bewering (PLAN.md #8.2)."""
    rapport = _importeer(conn, [
        _claim(text="https://www.facebook.com/permalink.php?story_fbid=pfbid02NCKp&id=1"),
        _claim(text="https://x.com/gewoonmerels/status/2041919015824846908"),
    ])

    assert rapport.accepted_claims == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM claim").fetchone()["n"] == 0
    assert {w.reason for w in rapport.refusals} == {"geen_bewering"}


def test_claim_with_a_url_inside_is_still_accepted(conn):
    """Alleen een kále URL is geen bewering; een bewering mét bronlink wel."""
    rapport = _importeer(conn, [
        _claim(text="Volgens https://example.org/bron daalt de zeespiegel al tien jaar"),
    ])

    assert rapport.accepted_claims == 1
