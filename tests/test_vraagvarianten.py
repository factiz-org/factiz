"""De vraag-claims ook als bewering in de index (PLAN #25.37).

Een claim die als vraag is opgeschreven, krijgt één variant: dezelfde tekst
door de regel van #25.36 (`vraagvorm.als_bewering`), zonder taalmodel. Zo
lijkt de variant niet op de posts van de meetset (die komen van een
taalmodel), en kost hij niets. De varianten gaan alleen in een kopie van de
database tot de meting en een release (B22).
"""

import numpy as np
import pytest

from doublecheck import vraagvarianten as vv
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "kopie.db")
    init_schema(conn)
    for claim_id, tekst, taal in [
        ("c1", "Is it true that the harbour of Rotterdam closed in 2020?", "en"),
        ("c2", "The harbour of Rotterdam closed in 2020.", "en"),
        ("c3", "日本は世界一の重税国ですか？", "ja"),
        ("c4", "Why did the harbour close?", "en"),
        ("c5", "?", "und"),
    ]:
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
                     (claim_id, tekst, taal))
    conn.commit()
    return conn


def _vingerafdrukken(teksten, versie):
    return [TextFingerprint(np.ones(4, dtype=np.float32) / 2, versie) for _ in teksten]


def test_only_a_claim_written_as_a_question_gets_a_variant(conn):
    rijen = {claim_id: tekst for claim_id, _, tekst in vv.varianten(conn)}
    assert rijen == {"c1": "the harbour of Rotterdam closed in 2020",
                     "c3": "日本は世界一の重税国です",
                     "c4": "Why did the harbour close"}


def test_the_variant_is_made_by_the_rule_and_says_so(conn):
    aantal = vv.importeer(conn, vv.varianten(conn), _vingerafdrukken, "m@1")
    assert aantal == 3
    herkomst = {tuple(r) for r in conn.execute("SELECT generator, prompt_version, model_version FROM claim_variant")}
    assert herkomst == {(vv.GENERATOR, vv.PROMPTVERSIE, "m@1")}
    assert vv.GENERATOR == "regel", "geen taalmodel: zo lijkt de variant niet op de posts van de meetset"


def test_importing_twice_replaces_instead_of_doubling(conn):
    vv.importeer(conn, vv.varianten(conn), _vingerafdrukken, "m@1")
    vv.importeer(conn, vv.varianten(conn), _vingerafdrukken, "m@1")
    assert conn.execute("SELECT count(*) FROM claim_variant").fetchone()[0] == 3


def test_the_production_database_is_refused(tmp_path, monkeypatch):
    """B22: varianten in de productie-index zijn een release. Zonder die stap
    weigert de import de database van de resolver."""
    monkeypatch.setenv("DOUBLECHECK_DB", str(tmp_path / "productie.db"))
    with pytest.raises(vv.Weigering):
        vv.controleer_doel(tmp_path / "productie.db")
    vv.controleer_doel(tmp_path / "kopie.db")
    # Met een release (PO 2026-10-16) mag het wel, maar alleen expliciet.
    vv.controleer_doel(tmp_path / "productie.db", release=True)


def test_only_web_text_close_to_a_new_variant_goes_through_the_resolver():
    """Een webtekst kan alleen een ander antwoord krijgen als een nieuwe
    variant hem dichter nadert dan de drempel voor `related`; de rest is per
    constructie gelijk."""
    web = np.array([[1, 0, 0], [0, 1, 0], [0.6, 0.8, 0]], dtype=np.float32)
    nieuw = np.array([[0.8, 0.6, 0]], dtype=np.float32)
    hoogste, boven = vv.boven_drempel(web, nieuw, 0.79, blok=2)
    assert list(boven) == [0, 2]
    assert np.allclose(hoogste, [0.8, 0.6, 0.96])


def test_on_the_claim_side_sinhala_also_loses_its_question_particle():
    """Groei op de ontwikkelhelft (#25.37): 356 Singalese vraag-claims eindigen
    op een los ද, en veel meer hebben het aan het laatste woord. Alleen aan de
    claimkant; de uitgebrachte invoerregel van #25.36 blijft zoals hij is."""
    from doublecheck.vraagvorm import als_bewering

    los = "ලොව වෙසෙන කුඩාම පක්ෂියාගේ ඡායාරූපයක් ද?"
    vast = "සජිත් සමග එක්වන බව නාමල් ප්‍රකාශ කළාද?"
    assert vv.als_bewering_claim(los) == "ලොව වෙසෙන කුඩාම පක්ෂියාගේ ඡායාරූපයක්"
    assert vv.als_bewering_claim(vast) == "සජිත් සමග එක්වන බව නාමල් ප්‍රකාශ කළා"
    assert als_bewering(los) == "ලොව වෙසෙන කුඩාම පක්ෂියාගේ ඡායාරූපයක් ද", "de invoerregel verandert niet"
    # Zonder vraagteken blijft een Singalese bewering zoals ze is.
    assert vv.als_bewering_claim("ලොව වෙසෙන කුඩාම පක්ෂියාගේ ඡායාරූපයක් ද") == \
        "ලොව වෙසෙන කුඩාම පක්ෂියාගේ ඡායාරූපයක් ද"
