"""Een witte lijst van uitgevers (#25.29, B28, SPECS E2.S6-AC2 tot AC4).

Iedereen mag ClaimReview publiceren en niemand controleert het. In een
database die de toelating draagt, is een claim alleen vindbaar met een check
van een host uit het register, en alleen zulke checks staan als bonnetje in
het antwoord. De testdatabases van de suite dragen haar niet: daar zijn de
hosts verzonnen.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from doublecheck import toelating
from doublecheck.embedding import TextFingerprint
from doublecheck.search import search_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint

REGISTER = {"politifact.com": "PolitiFact", "fullfact.org": "Full Fact"}


def _vector(richting):
    v = np.asarray(richting, dtype=np.float32)
    v = v / np.linalg.norm(v)
    v.setflags(write=False)
    return TextFingerprint(vector=v, model_version="testmodel-v1")


def _claim(conn, claim_id, richting, *urls):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
                 (claim_id, f"tekst van {claim_id}"))
    for url in urls:
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'Iemand', 'false', 'False', ?, '2024-01-01', 'en')",
                     (claim_id, url))
    save_text_fingerprint(conn, claim_id, _vector(richting))


@pytest.fixture(params=["geheugen", "bestand"])
def conn(request, tmp_path, monkeypatch):
    monkeypatch.setattr(toelating, "register", lambda: REGISTER)
    conn = connect(":memory:" if request.param == "geheugen" else tmp_path / "index.db")
    init_schema(conn)
    _claim(conn, "winkel", [1.0, 0.0, 0.0], "https://www.webwinkel.example/recensie")
    _claim(conn, "redactie", [0.6, 0.8, 0.0], "https://www.politifact.com/factchecks/1/",
           "https://www.webwinkel.example/kopie")
    conn.commit()
    yield conn
    conn.close()


def test_without_the_admission_every_host_is_found(conn):
    gevonden = [k.claim_id for k in search_text(conn, _vector([1.0, 0.0, 0.0]), limit=5)]
    assert gevonden == ["winkel", "redactie"]


def test_with_the_admission_a_claim_needs_a_check_from_the_register(conn):
    toelating.zet_aan(conn)
    gevonden = [k.claim_id for k in search_text(conn, _vector([1.0, 0.0, 0.0]), limit=5)]
    assert gevonden == ["redactie"]


def test_only_checks_from_the_register_are_receipts(conn):
    """SPECS E2.S6-AC3: ook bij een claim die wel vindbaar is, staat de
    kopie op de webwinkel niet als bonnetje in het antwoord."""
    from doublecheck.evidence import build_evidence

    assert build_evidence(conn, "redactie", register=REGISTER, onbekend="telt-mee").check_count == 2
    toelating.zet_aan(conn)
    bewijs = build_evidence(conn, "redactie", register=REGISTER, onbekend="telt-mee")
    assert [c.url for c in bewijs.factchecks] == ["https://www.politifact.com/factchecks/1/"]
    assert bewijs.publisher_count == 1


def test_outside_the_index_is_still_in_the_database(conn):
    """SPECS E2.S6-AC5."""
    toelating.zet_aan(conn)
    assert conn.execute("SELECT count(*) FROM factcheck WHERE claim_id = 'winkel'").fetchone()[0] == 1
    assert "winkel" in toelating.buiten_index(conn)


def test_switching_the_admission_on_is_recorded_once(conn):
    assert not toelating.staat_aan(conn)
    toelating.zet_aan(conn)
    toelating.zet_aan(conn)
    assert toelating.staat_aan(conn)
    assert conn.execute("SELECT count(*) FROM toelating").fetchone()[0] == 1


def test_a_proposal_never_admits_a_new_host_by_itself():
    """SPECS E2.S6-AC4: vroeger kwam een host met vijf checks en een
    dominante naam vanzelf in het register; zo kwamen er een witgoedwinkel en
    een casinosite in."""
    from doublecheck.uitgevers import voeg_voorstel_samen

    hosts, twijfel = {"slotsup.com": "SlotsUp", "politifact.com": "PolitiFact"}, []
    huidig = {"politifact.com": "PolitiFact"}
    samen, te_beoordelen = voeg_voorstel_samen(hosts, twijfel, huidig, geweerd={"rommel.example"})
    assert samen == huidig
    assert [t["host"] for t in te_beoordelen] == ["slotsup.com"]
    assert voeg_voorstel_samen({"rommel.example": "X"}, [], huidig, geweerd={"rommel.example"})[1] == []


TOEGELATEN = ("redactie", "instelling")


def test_every_host_in_the_register_was_labelled_a_newsroom_or_an_institution():
    """Het register is de witte lijst: wat erin staat heeft iemand gelezen
    en een redactie of een kennisinstelling genoemd
    (docs/steekproeven/25.29-uitgevers.json, B28)."""
    from doublecheck.uitgevers import load_hosts

    labels = json.loads(Path("docs/steekproeven/25.29-uitgevers.json").read_text(encoding="utf-8"))["labels"]
    assert {h for h in load_hosts()} == {h for h, l in labels.items() if l["oordeel"] in TOEGELATEN}
    assert all(load_hosts()[h] == l["naam"] for h, l in labels.items() if l["oordeel"] in TOEGELATEN)


def test_an_institution_is_admitted_only_with_the_four_requirements_written_down():
    """B28 aangevuld (PO 2026-10-13): kern is kennis of bewijs, verkoopt niets
    wat met de claim te maken heeft, toont bronnen, voert geen campagne. Wie
    een instelling toelaat, schrijft op waarom."""
    from doublecheck.uitgevers import load_hosts

    labels = json.loads(Path("docs/steekproeven/25.29-uitgevers.json").read_text(encoding="utf-8"))["labels"]
    instellingen = {h: l for h, l in labels.items() if l["oordeel"] == "instelling"}
    assert {"nationalacademies.org", "sites.nationalacademies.org", "cancer.org",
            "watchlist-internet.at"} <= set(instellingen)
    for host, label in instellingen.items():
        assert set(label["eisen"]) == {"kennis", "verkoopt_niets", "bronnen", "geen_campagne"}, host
        assert all(label["eisen"].values()), host
        assert host in load_hosts()


def test_euvsdisinfo_is_on_the_list_under_its_own_name():
    from doublecheck.uitgevers import load_hosts

    assert load_hosts()["euvsdisinfo.eu"] == "EUvsDisinfo"


def test_junk_from_the_review_is_banned_in_the_register_itself():
    """PO 2026-10-13: "verwijder de rommel". Wat bij het nalopen rommel bleek,
    staat als derde stand in het register: de import weigert het en
    `opruimen` haalt het uit het corpus. Register en labels blijven gelijk."""
    from doublecheck.uitgeverkwaliteit import is_geweerde_host
    from doublecheck.uitgevers import load_geweerd, load_hosts

    labels = json.loads(Path("docs/steekproeven/25.29-uitgevers.json").read_text(encoding="utf-8"))["labels"]
    rommel = {h for h, l in labels.items() if l["oordeel"] == "rommel"}
    assert set(load_geweerd()) == rommel
    assert not set(load_geweerd()) & set(load_hosts())
    for url in ("https://www.slotsup.com/online-casinos/777", "https://beststocks.ru/journal/x",
                "https://www.rorustec.it/instagram-facebook-web/", "https://halfrain.com/"):
        assert is_geweerde_host(url), url
    # Een gewone redactie en een onduidelijke host blijven toegestaan.
    assert not is_geweerde_host("https://www.politifact.com/factchecks/1/")
    assert not is_geweerde_host("https://mexicanadearte.art/2021/07/10/x")


def test_the_discovery_counts_only_what_the_index_can_find():
    """PROTOCOL §3: `languages` zijn de talen die in de index zitten, en
    `claims` maakt een `none` leesbaar. Een claim buiten de index kan nooit
    gevonden worden, dus telt hij niet mee."""
    from fastapi.testclient import TestClient

    import doublecheck.api as api

    conn = connect(":memory:")
    init_schema(conn)
    for claim_id, taal, url in (("redactie", "nl", "https://factly.in/a"),
                                ("winkel", "vi", "https://www.webwinkel.example/r")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
                     (claim_id, f"tekst van {claim_id}", taal))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'X', 'false', 'False', ?, '2024-01-01', ?)",
                     (claim_id, url, taal))
    conn.commit()
    toelating.zet_aan(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    try:
        scope = TestClient(api.app).get("/.well-known/doublecheck").json()["scope"]
    finally:
        api.app.dependency_overrides.clear()
        conn.close()
    assert scope["claims"] == 1
    assert scope["languages"] == ["nl"]


def test_a_new_proposal_keeps_the_reason_a_person_wrote_down():
    """Wie een host onduidelijk noemde, schreef op waarom; een nieuwe meting
    ververst de telling, niet de reden."""
    from doublecheck.uitgevers import voeg_voorstel_samen

    bestaand = [{"host": "boolshat.com", "voorstel": "Boolshat.com", "checks": 5,
                 "reden": "kleine site zonder herkenbare redactie"}]
    twijfel = [{"host": "boolshat.com", "voorstel": "Boolshat.com", "aandeel": 1.0, "checks": 7}]
    _, te_beoordelen = voeg_voorstel_samen({}, twijfel, {}, bestaand=bestaand)
    assert te_beoordelen == [{"host": "boolshat.com", "voorstel": "Boolshat.com", "checks": 7, "aandeel": 1.0,
                              "reden": "kleine site zonder herkenbare redactie"}]


def test_a_newsroom_has_one_spelling_in_the_register():
    """Eén naam per redactie (PLAN #34.2ao): twee hosts van dezelfde redactie dragen precies dezelfde naam. Het lab telt
    redacties al los van schrijfwijze (`evidence._uitgeversleutel`, DR7), maar de uitgave toont en telt de naam zoals hij
    hier staat; *youturn* naast *Youturn* werden op de site twee redacties met elk een deel van hun checks."""
    from doublecheck.evidence import _uitgeversleutel
    from doublecheck.uitgevers import load_hosts

    per_sleutel: dict[str, set[str]] = {}
    for naam in load_hosts().values():
        per_sleutel.setdefault(_uitgeversleutel(naam), set()).add(naam)
    assert [sorted(v) for v in per_sleutel.values() if len(v) > 1] == []
