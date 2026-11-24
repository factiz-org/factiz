"""Wat de index toelaat (B28, SPECS E2.S6).

Buiten de index is niet weg: de claim en zijn checks blijven in de database,
maar het zoeken slaat ze over. Eerst de vage claims (#25.28): een tekst die
niets toetsbaars zegt, trekt elke gewone zin aan die erop lijkt (BENCHMARK
§99).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from doublecheck import toelating
from doublecheck.embedding import TextFingerprint
from doublecheck.image_fingerprint import ImageFingerprint
from doublecheck.ingest import claim_id_for_text
from doublecheck.search import search_image, search_text
from doublecheck.storage import connect, init_schema, save_image_fingerprint, save_text_fingerprint, save_variant

VAAG = "Something to think about."
ECHT = "5G masts spread the coronavirus."
VERSIE = "testmodel-v1"


def _vector(richting):
    v = np.asarray(richting, dtype=np.float32)
    v = v / np.linalg.norm(v)
    v.setflags(write=False)
    return TextFingerprint(vector=v, model_version=VERSIE)


def _claim(conn, tekst, richting, *, cluster=None, url=None):
    claim_id = claim_id_for_text(tekst)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, 'en', ?)",
                 (claim_id, tekst, cluster))
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES (?, 'Redactie', 'false', 'False', ?, '2024-01-01', 'en')",
                 (claim_id, url or f"https://redactie.example/{claim_id}"))
    save_text_fingerprint(conn, claim_id, _vector(richting))
    return claim_id


@pytest.fixture(params=["geheugen", "bestand"])
def conn(request, tmp_path):
    """In het geheugen zoekt het brute force, op een bestand via de
    gedeelde matrixcache; allebei moeten de vage claim overslaan."""
    conn = connect(":memory:" if request.param == "geheugen" else tmp_path / "index.db")
    init_schema(conn)
    yield conn
    conn.close()


def test_the_vague_text_is_on_the_list_under_its_own_hash():
    """Een claim-id is de hash van de tekst, dus de lijst geldt ook in een
    schone kloon die het corpus opnieuw opbouwt."""
    assert claim_id_for_text(VAAG) in toelating.vage_claims()


def test_a_vague_claim_is_never_found_even_as_the_exact_text(conn):
    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    echt = _claim(conn, ECHT, [0.6, 0.8, 0.0])
    conn.commit()
    gevonden = [k.claim_id for k in search_text(conn, _vector([1.0, 0.0, 0.0]), limit=5)]
    assert vaag not in gevonden
    assert gevonden == [echt]


def test_a_vague_claim_is_not_found_through_its_variants(conn):
    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    echt = _claim(conn, ECHT, [0.0, 1.0, 0.0])
    save_variant(conn, vaag, "nl", "Iets om over na te denken.", "proef", "v1", _vector([0.0, 0.0, 1.0]))
    conn.commit()
    gevonden = [k.claim_id for k in search_text(conn, _vector([0.0, 0.0, 1.0]), limit=5, varianten=True)]
    assert gevonden == [echt]


def test_a_vague_claim_is_not_found_through_an_image(conn):
    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    echt = _claim(conn, ECHT, [0.0, 1.0, 0.0])
    save_image_fingerprint(conn, vaag, ImageFingerprint(hash_hex="00" * 32, model_version="pdq-test", bits=256))
    save_image_fingerprint(conn, echt, ImageFingerprint(hash_hex="ff" * 32, model_version="pdq-test", bits=256))
    conn.commit()
    gevonden = search_image(conn, ImageFingerprint(hash_hex="00" * 32, model_version="pdq-test", bits=256), limit=5)
    assert [k.claim_id for k in gevonden] == [echt]


def test_a_vague_member_does_not_add_its_checks_to_the_cluster(conn):
    """Een vage tekst trekt ook bij het clusteren aan; zijn check telt dus
    niet mee in het bewijs van de bewering waar hij naast staat."""
    from doublecheck.evidence import build_evidence

    echt = _claim(conn, ECHT, [1.0, 0.0, 0.0], cluster="k1", url="https://een.example/1")
    _claim(conn, VAAG, [0.9, 0.1, 0.0], cluster="k1", url="https://twee.example/2")
    conn.commit()
    bewijs = build_evidence(conn, echt, register={}, onbekend="telt-mee")
    assert bewijs.check_count == 1 and bewijs.cluster_size == 1
    assert [c.url for c in bewijs.factchecks] == ["https://een.example/1"]


def test_outside_the_index_is_not_gone():
    """De check blijft een bonnetje: wie de vage claim zelf opvraagt, ziet
    hem nog (SPECS E2.S6-AC5)."""
    from doublecheck.evidence import build_evidence

    conn = connect(":memory:")
    init_schema(conn)
    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    assert build_evidence(conn, vaag, register={}, onbekend="telt-mee").check_count == 1


def test_the_list_is_exactly_the_hand_labels():
    """Wat het zoeken overslaat, is wat iemand met de hand vaag noemde, niet
    meer en niet minder (§99)."""
    labels = json.loads(Path("docs/steekproeven/25.26-vage-claims.json").read_text(encoding="utf-8"))["labels"]
    assert toelating.vage_claims() == {c for c, l in labels.items() if l == "vaag"}


def test_the_benchmark_refuses_a_test_pair_on_a_claim_outside_the_index(conn):
    """Anders wordt een testpaar stil een misser, en verschuift het cijfer
    zonder dat iemand het besloot."""
    from doublecheck.benchmark import ensure_testset_inside_index
    from doublecheck.testset import TestPair, save_test_pair

    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    echt = _claim(conn, ECHT, [0.0, 1.0, 0.0])
    save_test_pair(conn, TestPair(claim_id=echt, is_same=True, provenance="origineel",
                                  language="en", fingerprint=_vector([0.0, 1.0, 0.0])))
    ensure_testset_inside_index(conn)
    save_test_pair(conn, TestPair(claim_id=echt, is_same=False, provenance=f"hardste-buur:{vaag}",
                                  language="en", fingerprint=_vector([1.0, 0.0, 0.0])))
    with pytest.raises(ValueError, match="buiten de index"):
        ensure_testset_inside_index(conn)


def test_test_pairs_on_a_vague_claim_leave_on_purpose_and_on_record(conn, tmp_path):
    """Ook een hardste buur die vaag is; de andere paren op dezelfde gewone
    claim blijven staan."""
    from doublecheck.testset import TestPair, save_test_pair

    vaag = _claim(conn, VAAG, [1.0, 0.0, 0.0])
    echt = _claim(conn, ECHT, [0.0, 1.0, 0.0])
    for claim_id, herkomst in ((vaag, "origineel"), (echt, "origineel"), (echt, f"hardste-buur:{vaag}")):
        save_test_pair(conn, TestPair(claim_id=claim_id, is_same=herkomst == "origineel", provenance=herkomst,
                                      language="en", fingerprint=_vector([1.0, 0.0, 0.0])))
    rapport = tmp_path / "testparen.json"
    assert toelating.haal_testparen_weg(conn, rapportpad=rapport) == 2
    weg = json.loads(rapport.read_text(encoding="utf-8"))["verwijderd"]
    assert sorted(p["provenance"] for p in weg) == ["hardste-buur:" + vaag, "origineel"]
    assert [tuple(r) for r in conn.execute("SELECT claim_id, provenance FROM testpair")] == [(echt, "origineel")]


def test_applying_the_labels_writes_only_the_vague_ones_with_their_text():
    from doublecheck.vaagmeting import lijst

    labels = {"a": "vaag", "b": "bewering", "c": "vaag"}
    assert lijst(labels, {"a": "Good initiative", "b": "Mortgage rates are coming down", "c": "Be careful.."}) == {
        "a": "Good initiative", "c": "Be careful.."}
    with pytest.raises(Exception):
        lijst({"d": "vaag"}, {})
