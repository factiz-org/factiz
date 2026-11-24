"""Een taal mag alleen in de index als het model haar aantoonbaar aankan.

Aanscherping van B14 *(PO 2026-08-31)*. B14 zei dat een taal zonder eigen
benchmark in de index mocht "zonder precisiebelofte". Dat bleek niet houdbaar:
in de index zitten betekent kándidaat zijn, en in Tamil, Telugu en Bengaals gaf
71% van de artefacten een zelfverzekerde `matched` op een willekeurige andere
bewering (BENCHMARK.md §39). Die fout valt per constructie buiten elke
benchmark — geen enkel cijfer had hem gevonden.

De regel draait daarmee om: van een zwarte lijst naar een **gemeten witte
lijst**. Ongemeten is niet hetzelfde als goed.
"""

import pytest

from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.taalgeschiktheid import (
    GEMETEN_BRUIKBAAR,
    GEMETEN_MET,
    ONBRUIKBARE_TALEN,
    OngemetenModelError,
    mag_in_de_index,
    taalgrond,
)


def test_a_measured_language_is_admitted():
    assert mag_in_de_index("nl", GEMETEN_MET)
    assert mag_in_de_index("ja", GEMETEN_MET)


def test_a_language_the_model_cannot_represent_stays_out():
    """De negen uit §39, gemeten en gezakt."""
    for taal in sorted(ONBRUIKBARE_TALEN):
        assert not mag_in_de_index(taal, GEMETEN_MET), taal


def test_an_unmeasured_language_stays_out_too():
    """Dit ís de aanscherping. Voorheen kwam een onbekende taal er gewoon in."""
    for taal in ("bg", "cs", "sv", "uk", "xx"):
        assert not mag_in_de_index(taal, GEMETEN_MET), taal
    assert not set(GEMETEN_BRUIKBAAR) & ONBRUIKBARE_TALEN


def test_never_measured_and_measured_badly_get_different_answers(monkeypatch):
    """Voor de beheerder is dat het verschil tussen "meten" en "opgeven".

    Onder bge-m3 klapt geen gemeten taal ineen (#25.18); het mechanisme wordt
    getoetst met een taal die onder een ander model wél zakte.
    """
    import doublecheck.taalgeschiktheid as tg

    monkeypatch.setattr(tg, "GEMETEN_BRUIKBAAR", tg.GEMETEN_BRUIKBAAR - {"ta"})
    monkeypatch.setattr(tg, "ONBRUIKBARE_TALEN", frozenset({"ta"}))
    assert tg.taalgrond("ta", GEMETEN_MET) == "onbruikbare_taal"
    assert tg.taalgrond("sv", GEMETEN_MET) == "ongemeten_taal"
    assert tg.taalgrond("nl", GEMETEN_MET) is None


def test_the_nine_south_asian_languages_are_admitted_under_bge_m3():
    """Onder MiniLM ineengeklapt (§39), onder bge-m3 gemeten bruikbaar
    (0,33–0,39 op de feed) en toegelaten door de PO (#25.18, 2026-10-11)."""
    from doublecheck.config import load_config

    assert GEMETEN_MET == load_config().model_versions.text_embedding
    for taal in ("te", "ta", "si", "ml", "bn", "kn", "km", "as", "pa"):
        assert mag_in_de_index(taal, GEMETEN_MET), taal


def test_the_list_refuses_to_be_used_under_another_model():
    """De maat is modelgebonden; een andere modelversie maakt hem waardeloos.

    Weigeren, niet stil doorrekenen — dezelfde regel als bij de fingerprints
    en de clusters (DR6).
    """
    with pytest.raises(OngemetenModelError):
        mag_in_de_index("nl", "een-ander-model-v9")


def _claim(tekst, taal):
    return RawClaim(
        text=tekst, claimant=None, claim_date=None,
        factchecks=(RawFactcheck(
            publisher="Nieuwscheckers", publisher_site="nieuwscheckers.nl",
            url="https://nieuwscheckers.nl/check/1", review_date="2024-03-14",
            verdict_original="Onjuist", language=taal),))


def test_import_refuses_a_claim_in_an_unmeasured_language():
    from doublecheck.ingest import import_claims
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    rapport = import_claims(
        conn,
        [_claim("Tvrdenie o očkovaní ktoré nikto nekontroloval", "sk")],
        source="datacommons-ccby",
        uitgesteld=True,
    )
    assert rapport.accepted_claims == 0
    assert [r.reason for r in rapport.refusals] == ["ongemeten_taal"]
    conn.close()


def test_import_still_accepts_a_measured_language():
    from doublecheck.ingest import import_claims
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    rapport = import_claims(
        conn, [_claim("De zeespiegel daalt al tien jaar wereldwijd", "nl")],
        source="datacommons-ccby", uitgesteld=True,
    )
    assert rapport.accepted_claims == 1
    conn.close()


def test_a_new_language_can_be_measured_before_it_is_imported():
    """Zonder uitweg is deze regel een muur.

    Een taal komt er niet in vóór ze gemeten is, en ze is niet te meten uit een
    corpus waar ze niet in zit. `meet_teksten` breekt die cirkel: meten op ruwe
    teksten, vóór de import.
    """
    import numpy as np

    from doublecheck.taalgeschiktheid import meet_teksten

    def nep_embedder(teksten, model_version):
        # Onderscheidende vectoren: elk zijn eigen as.
        uit = np.zeros((len(teksten), len(teksten)), dtype=np.float32)
        for nummer in range(len(teksten)):
            uit[nummer, nummer] = 1.0
        return uit

    teksten = [f"Een bewering nummer {n}" for n in range(40)]
    score = meet_teksten(teksten, "welk-model-dan-ook", embedder=nep_embedder)
    assert score is not None and score < 0.45

    assert meet_teksten(["te", "weinig"], "x", embedder=nep_embedder) is None
