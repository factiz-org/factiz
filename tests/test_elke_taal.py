"""Elke taal een eigen cijfer (PLAN #25.1, B14 aangescherpt).

Het foutcijfer gold voor vijf talen terwijl 29% van het corpus in talen
zonder testpaar stond. Voortaan: elke taal vanaf een drempel uit config heeft
testparen, of de benchmark weigert. De uitbreiding is additief, zodat eerdere
runs vergelijkbaar blijven.
"""

import pytest

from doublecheck.benchmark import MarktZonderCijferError, ensure_every_language_is_measured
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import (
    _negation_variant,
    load_test_pairs,
    ontbrekende_talen,
    voeg_talen_toe,
    build_testset,
)
from tests.test_ingest import NEP


def _claims(conn, taal, aantal, sjabloon, uitgevers=2):
    for i in range(aantal):
        claim_id = f"{taal}-{i}"
        tekst = sjabloon.format(i=i, j=10 + i)
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
            (claim_id, tekst, taal),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language)"
            " VALUES (?, ?, 'onwaar', 'Falso', ?, '2024-01-01', ?)",
            (claim_id, f"Uitgever-{taal}-{i % uitgevers}", f"https://x.org/{claim_id}", taal),
        )
        save_text_fingerprint(conn, claim_id, NEP(tekst))
    conn.commit()


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    _claims(c, "nl", 20, "De heffing is {j} procent gestegen in het jaar 20{i:02d} volgens het rapport")
    _claims(c, "pt", 30, "O governo é responsável por {j} mortes em 20{i:02d} segundo o relatório oficial")
    _claims(c, "zh", 30, "政府在20{i:02d}年导致{j}人死亡，这是官方报告说的内容和数据")
    _claims(c, "und", 40, "Claim {i}")
    yield c
    c.close()


def test_the_threshold_comes_from_config():
    assert load_config().benchmark.min_claims_voor_cijfer >= 1


def test_a_language_above_the_threshold_without_pairs_blocks_the_benchmark(conn):
    build_testset(conn, NEP, total=20, language_shares={"nl": 1.0})
    assert ontbrekende_talen(conn, min_claims=25) == ["pt", "zh"]  # und is geen taal
    with pytest.raises(MarktZonderCijferError) as fout:
        ensure_every_language_is_measured(conn, min_claims=25)
    assert "pt" in str(fout.value) and "zh" in str(fout.value)
    # Onder de drempel geen eis: dan staat de taal zonder precisiebelofte in de index.
    ensure_every_language_is_measured(conn, min_claims=31)


def test_adding_languages_leaves_existing_pairs_untouched(conn):
    build_testset(conn, NEP, total=20, language_shares={"nl": 1.0})
    voor = [(p.claim_id, p.provenance, p.language) for p in load_test_pairs(conn)]
    rapport = voeg_talen_toe(conn, NEP, ["pt", "zh"], per_taal=20)
    na = [(p.claim_id, p.provenance, p.language) for p in load_test_pairs(conn)]
    assert na[: len(voor)] == voor
    assert rapport.per_language == {"pt": 20, "zh": 20}
    ensure_every_language_is_measured(conn, min_claims=25)


def test_a_language_that_already_has_pairs_is_refused(conn):
    build_testset(conn, NEP, total=20, language_shares={"nl": 1.0})
    with pytest.raises(ValueError):
        voeg_talen_toe(conn, NEP, ["nl"], per_taal=10)


def test_languages_without_negation_rules_get_harder_pairs_not_easier(conn):
    """Zonder ontkenningsregel gaat dat aandeel naar de hardste buur, niet
    naar de makkelijke aankleding."""
    rapport = voeg_talen_toe(conn, NEP, ["zh"], per_taal=20)
    soorten = rapport.per_provenance
    assert "ontkenning" not in soorten
    assert soorten.get("hardste-buur", 0) >= 5


@pytest.mark.parametrize("taal, tekst, ontkenning", [
    ("pt", "O presidente é responsável pela crise", "não é"),
    ("it", "Il governo è responsabile della crisi", "non è"),
    ("ru", "Президент является виновником кризиса", "не является"),
    ("id", "Vaksin itu adalah penyebab autisme", "bukan"),
    ("hi", "यह वीडियो असली है", "नहीं है"),
])
def test_new_negation_patterns_produce_a_different_claim(taal, tekst, ontkenning):
    variant = _negation_variant(tekst, taal)
    assert variant is not None and variant != tekst and ontkenning in variant


def test_derivations_are_recomputed_without_changing_the_pairs(conn):
    """Na een wijziging van de extractiecode worden de opgeslagen afleidingen
    herberekend uit herleide artefacten (§63); de paren zelf blijven gelijk."""
    import json

    from doublecheck.relation import derivation_version
    from doublecheck.testset import herbereken_afleidingen

    voeg_talen_toe(conn, NEP, ["pt"], per_taal=20)
    voor = conn.execute(
        "SELECT testpair_id, claim_id, provenance, payload, negations FROM testpair ORDER BY 1"
    ).fetchall()
    conn.execute("UPDATE testpair SET derivation_version = 'oud', negations = '[]'")
    rapport = herbereken_afleidingen(conn, NEP)
    na = conn.execute(
        "SELECT testpair_id, claim_id, provenance, payload, negations, derivation_version"
        " FROM testpair ORDER BY 1"
    ).fetchall()
    assert rapport.niet_herleid == 0 and rapport.herberekend == len(voor)
    assert {r["derivation_version"] for r in na} == {derivation_version()}
    for oud, nieuw in zip(voor, na):
        assert (oud["testpair_id"], oud["claim_id"], oud["provenance"], oud["payload"]) == (
            nieuw["testpair_id"], nieuw["claim_id"], nieuw["provenance"], nieuw["payload"]
        )
        # De nep-fingerprinter slaat lege afleidingen op; de herberekening
        # leidt ze af uit de herleide tekst, dus elke ontkenningsvariant
        # draagt daarna de ingevoegde ontkenning.
        if nieuw["provenance"] == "ontkenning":
            assert "não" in json.loads(nieuw["negations"])


def test_an_unrecoverable_pair_keeps_its_old_version_so_the_benchmark_refuses(conn):
    from doublecheck.testset import herbereken_afleidingen

    voeg_talen_toe(conn, NEP, ["pt"], per_taal=10)
    conn.execute("UPDATE testpair SET derivation_version = 'oud'")
    conn.execute(
        "UPDATE testpair SET payload = ? WHERE testpair_id = (SELECT min(testpair_id) FROM testpair"
        " WHERE provenance NOT LIKE 'hardste-buur:%')",
        (bytes(32),),
    )
    rapport = herbereken_afleidingen(conn, NEP)
    assert rapport.niet_herleid == 1
    assert conn.execute(
        "SELECT count(*) FROM testpair WHERE derivation_version = 'oud'"
    ).fetchone()[0] == 1


def test_a_truncation_of_a_negated_claim_is_removed_not_kept(conn):
    """Gebouwd met een detector die de ontkenning niet zag: de inkorting kan
    de ontkenning hebben afgeknipt terwijl het label 'zelfde' zegt."""
    from doublecheck.testset import (
        TestPair, _truncation_variant, herbereken_afleidingen, save_test_pair,
    )

    tekst = "O ministro disse ontem na televisão que a vacina contra a gripe não funciona"
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('pt-neg', ?, 'pt')", (tekst,))
    save_text_fingerprint(conn, "pt-neg", NEP(tekst))
    ingekort = _truncation_variant(tekst, controleer=False)
    save_test_pair(conn, TestPair(claim_id="pt-neg", is_same=True, provenance="inkorting",
                                  language="pt", fingerprint=NEP(ingekort)))
    rapport = herbereken_afleidingen(conn, NEP)
    assert rapport.verwijderd_label_twijfel == 1
    assert conn.execute("SELECT count(*) FROM testpair WHERE claim_id = 'pt-neg'").fetchone()[0] == 0
