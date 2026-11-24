"""Rommel uit de index (PLAN #25.2).

Een claim van één woord is geen bewering: "google" (55 checks), "Claim:",
"Disinfo", "Yes", toetsenbordgeklop. Wie "google" in de demo typte kreeg
"checked by 55 fact-checkers". Twee woorden is al te streng: "Fauci
arrested." en "Shakira R.I.P." zijn echte claims. Schriften zonder spaties
(Chinees, Japans, Thai) hebben één "woord" per zin en vallen erbuiten.
Opruimen is nooit stil: eerst een rapport, dan pas uitvoeren, met een
rapportbestand van alles wat wegging.
"""

import json

import pytest

from doublecheck import opruimen
from doublecheck.factchecktools import RawClaim, RawFactcheck
from doublecheck.ingest import import_claims, is_geen_bewering
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from tests.test_ingest import NEP


@pytest.mark.parametrize("tekst", ["google", "Claim:", "  Disinfo  ", "Yes", "asdfasdflkajklagi99wg",
                                   "Fact check", "Claim Reviewed", "#SinERTEsinParo", "谷歌", "グーグル"])
def test_one_word_and_label_texts_are_not_claims(tekst):
    assert is_geen_bewering(tekst)


@pytest.mark.parametrize("tekst", ["Fauci arrested.", "Shakira R.I.P.", "5G causes cancer",
                                   "疫苗会导致自闭症", "地球是平的", "บิลเกตส์สร้างไวรัส"])
def test_short_real_claims_and_unspaced_scripts_stay(tekst):
    assert not is_geen_bewering(tekst)


def _raw(tekst):
    return RawClaim(text=tekst, claimant=None, claim_date=None, factchecks=(
        RawFactcheck(publisher="X", publisher_site="x.org", url=f"https://x.org/{abs(hash(tekst))}",
                     review_date="2024-01-01", verdict_original="False", language="en"),
    ))


def test_the_import_refuses_non_claims_with_a_reason():
    conn = connect(":memory:")
    init_schema(conn)
    rapport = import_claims(conn, [_raw("google"), _raw("Fauci arrested.")], source="test",
                            fingerprinter=NEP)
    assert rapport.accepted_claims == 1
    assert [r.reason for r in rapport.refusals] == ["geen_bewering"]


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    for cid, tekst in (("c1", "google"), ("c2", "Claim:"), ("c3", "Fauci arrested."),
                       ("c4", "The vaccine contains a microchip for tracking people")):
        c.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')", (cid, tekst))
        c.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                  " url, review_date, language) VALUES (?, 'X', 'onwaar', 'False', ?, '2024-01-01', 'en')",
                  (cid, f"https://x.org/{cid}"))
        save_text_fingerprint(c, cid, NEP(tekst))
    c.commit()
    yield c
    c.close()


def test_a_dry_run_reports_and_removes_nothing(conn):
    rommel = opruimen.vind_rommel(conn)
    assert sorted(r.claim_id for r in rommel) == ["c1", "c2"]
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 4


def test_executing_removes_claims_with_their_checks_and_writes_a_report(conn, tmp_path):
    rapportpad = tmp_path / "opruim.json"
    verwijderd = opruimen.ruim_op(conn, opruimen.vind_rommel(conn), rapportpad=rapportpad)
    assert verwijderd == 2
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM factcheck WHERE claim_id IN ('c1','c2')").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM fingerprint WHERE claim_id IN ('c1','c2')").fetchone()[0] == 0
    rapport = json.loads(rapportpad.read_text(encoding="utf-8"))
    assert {r["tekst"] for r in rapport["verwijderd"]} == {"google", "Claim:"}
    assert all(r["checks"] for r in rapport["verwijderd"])  # de bonnetjes staan in het rapport


def test_a_claim_in_the_testset_is_never_removed_silently(conn, tmp_path):
    from doublecheck.testset import TestPair, save_test_pair

    save_test_pair(conn, TestPair(claim_id="c1", is_same=True, provenance="origineel",
                                  language="en", fingerprint=NEP("google")))
    with pytest.raises(ValueError):
        opruimen.ruim_op(conn, opruimen.vind_rommel(conn), rapportpad=tmp_path / "r.json")
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 4


def test_an_existing_report_is_never_overwritten(conn, tmp_path):
    """Het rapport is het enige spoor van wat wegging; een tweede ronde mag
    het eerste nooit overschrijven."""
    pad = tmp_path / "opruim.json"
    pad.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        opruimen.ruim_op(conn, opruimen.vind_rommel(conn), rapportpad=pad)
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 4


def test_a_claim_checked_only_by_a_banned_publisher_is_junk_too(conn, monkeypatch):
    """#25.19: productrecensies van een webwinkel, opgemaakt als ClaimReview.
    Zolang ook één echte redactie de claim checkte, blijft hij staan."""
    import doublecheck.uitgeverkwaliteit as uk

    monkeypatch.setattr(uk, "GEWEERDE_UITGEVERS", uk.GEWEERDE_UITGEVERS | {"Webwinkel"})
    for cid, uitgevers in (("c5", ["Webwinkel"]), ("c6", ["Webwinkel", "Echte redactie"])):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
                     (cid, f"Best store for licenses, happy with their service and support {cid}"))
        for i, uitgever in enumerate(uitgevers):
            conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                         " url, review_date, language) VALUES (?, ?, 'onwaar', 'False', ?, '2024-01-01', 'en')",
                         (cid, uitgever, f"https://x.org/{cid}/{i}"))
    rommel = {r.claim_id: r for r in opruimen.vind_rommel(conn)}
    assert set(rommel) == {"c1", "c2", "c5"}
    assert rommel["c5"].reden == "geweerde_uitgever"
    assert rommel["c1"].reden == "geen_bewering"


def _check(conn, cid, uitgever, url):
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                 " url, review_date, language) VALUES (?, ?, 'onwaar', 'False', ?, '2019-05-09', 'en')",
                 (cid, uitgever, url))


def test_a_banned_host_is_junk_whatever_name_it_wears(conn):
    """#25.19 b: factstream.co was het speelterrein van een app. Weren op naam
    ("FactStream") lekte: dezelfde proefinvoer staat er onder "Someone",
    "SDomeone" en "FactStream test", ook op een ontwikkelsubdomein."""
    for cid, uitgever, url in (("f1", "Someone", "https://www.factstream.co/123456"),
                               ("f2", "SDomeone", "https://www.factstream.co/19292910"),
                               ("f3", "PolitiFact", "https://biffud-dev.factstream.co/trump3")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
                     (cid, f"This is a test of the push notifications number {cid}"))
        _check(conn, cid, uitgever, url)
    rommel = {r.claim_id: r for r in opruimen.vind_rommel(conn)}
    assert {"f1", "f2", "f3"} <= set(rommel)
    assert {rommel[c].reden for c in ("f1", "f2", "f3")} == {"geweerde_host"}


def test_a_banned_copy_beside_a_real_check_goes_but_the_claim_stays(conn, tmp_path):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('p1', ?, 'en')",
                 ("I have a 94% approval rating in the Republican Party",))
    _check(conn, "p1", "Donald Trump", "https://www.factstream.co/truth-o-meter/statements/2019/jun/06/x/")
    _check(conn, "p1", "PolitiFact", "https://www.politifact.com/factchecks/2019/jun/06/x/")
    losse = opruimen.vind_geweerde_checks(conn)
    assert [(c.claim_id, c.url) for c in losse] == [
        ("p1", "https://www.factstream.co/truth-o-meter/statements/2019/jun/06/x/")]
    rapportpad = tmp_path / "opruim.json"
    opruimen.ruim_op(conn, opruimen.vind_rommel(conn), rapportpad=rapportpad, losse_checks=losse)
    assert [u for (u,) in conn.execute("SELECT url FROM factcheck WHERE claim_id = 'p1'")] == [
        "https://www.politifact.com/factchecks/2019/jun/06/x/"]
    rapport = json.loads(rapportpad.read_text(encoding="utf-8"))
    assert [c["url"] for c in rapport["losse_checks"]] == [
        "https://www.factstream.co/truth-o-meter/statements/2019/jun/06/x/"]


def test_the_import_refuses_a_check_from_a_banned_host():
    conn = connect(":memory:")
    init_schema(conn)
    proef = RawClaim(text="This is a test of the push notifications", claimant=None, claim_date=None,
                     factchecks=(RawFactcheck(publisher="Someone", publisher_site="factstream.co",
                                              url="https://www.factstream.co/123456", review_date="2019-05-14",
                                              verdict_original="True", language="en"),))
    rapport = import_claims(conn, [proef], source="test", fingerprinter=NEP)
    assert rapport.accepted_claims == 0
    assert "geweerde_host" in [r.reason for r in rapport.refusals]


def test_test_pairs_on_junk_leave_only_on_purpose_and_on_record(conn, tmp_path):
    """PO 2026-10-13: twee testparen wezen naar een SEO-blog. Weghalen kan,
    maar alleen als eigen stap, met een rapport van elk paar (ook een
    hardste-buur dat naar de rommel verwijst), want het verandert de
    benchmark."""
    from doublecheck.testset import TestPair, save_test_pair

    save_test_pair(conn, TestPair(claim_id="c1", is_same=True, provenance="origineel",
                                  language="en", fingerprint=NEP("google")))
    save_test_pair(conn, TestPair(claim_id="c4", is_same=False, provenance="hardste-buur:c2",
                                  language="en", fingerprint=NEP("iets")))
    save_test_pair(conn, TestPair(claim_id="c3", is_same=True, provenance="origineel",
                                  language="en", fingerprint=NEP("Fauci arrested.")))
    rommel = opruimen.vind_rommel(conn)
    rapport = tmp_path / "testparen.json"
    assert opruimen.haal_uit_testset(conn, [r.claim_id for r in rommel], rapportpad=rapport) == 2
    weg = json.loads(rapport.read_text(encoding="utf-8"))["verwijderd"]
    assert sorted(p["claim_id"] for p in weg) == ["c1", "c4"]
    assert conn.execute("SELECT count(*) FROM testpair").fetchone()[0] == 1   # het echte paar blijft
    assert opruimen.ruim_op(conn, rommel, rapportpad=tmp_path / "r.json") == 2
