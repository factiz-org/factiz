"""Attributie als bonnetje (DR10, E7, #24.6)."""

import csv
import pathlib
import sqlite3

import pytest

from doublecheck import attributie as at
from doublecheck import euvsdisinfo
from doublecheck.storage import connect, init_schema

WORTEL = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def _claim(conn, claim_id="c1", tekst="een bewering"):
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
        (claim_id, tekst),
    )


def _bron(conn, **over):
    velden = dict(
        bron_id="b1", naam="Bron", soort="tracker", licentie="CC BY 4.0",
        attributietekst="Bron", url="https://example.org", herverdeelbaar=True,
    )
    velden.update(over)
    at.registreer_bron(conn, **velden)


def test_a_source_without_licence_or_credit_line_cannot_exist(conn):
    """E7.S1-AC1: het schema weigert, niet de applicatiecode."""
    with pytest.raises(sqlite3.IntegrityError):
        _bron(conn, licentie="")
    with pytest.raises(sqlite3.IntegrityError):
        _bron(conn, attributietekst="")
    with pytest.raises(sqlite3.IntegrityError):
        _bron(conn, soort="vriend")


def test_an_attribution_without_source_date_link_or_level_is_refused(conn):
    """DR10 op opslagniveau: een bonnetje zonder bon bestaat niet."""
    _claim(conn)
    _bron(conn)
    actor = at.registreer_actor(conn, naam="RT", soort="outlet")
    goed = dict(claim_id="c1", actor_id=actor, bron_id="b1", datum="2024-01-02",
                url="https://example.org/geval", niveau="waargenomen")
    assert at.voeg_attributie(conn, **goed)
    for kapot in (
        dict(goed, bron_id="onbekend"),
        dict(goed, datum=""),
        dict(goed, url=""),
        dict(goed, niveau="vermoed"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            at.voeg_attributie(conn, **kapot)


def test_aliases_resolve_to_one_actor_and_unknown_stays_unknown(conn):
    """E7.S3: Matryoshka = Operation Overload = Storm-1679; Doppelganger niet."""
    actor = at.registreer_actor(
        conn, naam="Matryoshka", soort="operatie",
        aliassen=("Operation Overload", "Storm-1679"),
    )
    assert at.vind_actor(conn, "operation  overload") == actor
    assert at.vind_actor(conn, "STORM-1679") == actor
    assert at.vind_actor(conn, "Doppelganger") is None
    # Een tweede registratie van dezelfde naam maakt geen tweede actor.
    assert at.registreer_actor(conn, naam="matryoshka", soort="operatie") == actor


def test_non_latin_actor_names_keep_distinct_ids():
    """Een Cyrillische outlet mag nooit tot een lege slug verschralen."""
    a = at.actor_id_voor("РИА Новости", "outlet")
    b = at.actor_id_voor("Sputnik", "outlet")
    c = at.actor_id_voor("ТАСС", "outlet")
    assert len({a, b, c}) == 3 and all(x.startswith("outlet:") for x in (a, b, c))


def test_category_and_consensus_code_never_read_attributions():
    """E7.S2-AC2: de categorisering en de DR7-telling kennen de tabel niet."""
    for naam in ("evidence.py", "search.py", "categorize.py", "categorise.py"):
        pad = WORTEL / "doublecheck" / naam
        if pad.exists():
            assert "attributie" not in pad.read_text(encoding="utf-8"), naam


def test_euvsdisinfo_snapshot_becomes_claims_checks_and_observed_attributions(conn, tmp_path):
    """E7.S4: elk geval één claim, één check (EUvsDisinfo, disinformation →
    onwaar) en per outlet een `waargenomen`-bonnetje; de bron staat
    geregistreerd als overheid, mét licentie."""
    pad = tmp_path / "snapshot.csv"
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Links", "Title", "Outlets", "Country",
                    "Disinformation", "Information"])
        w.writerow(["01.03.2022", "/report/a", "Titel A",
                    "RT; Sputnik", "Germany, France",
                    "The EU plans to ban all Russian literature from its schools.",
                    "No such plan exists."])
        w.writerow(["2021-11-15", "https://euvsdisinfo.eu/report/b", "Titel B",
                    "Sputnik", "Ukraine",
                    "NATO has promised to deploy nuclear weapons in Kyiv by summer.",
                    "NATO made no such promise."])
        w.writerow(["", "https://euvsdisinfo.eu/report/c", "Zonder datum", "RT", "",
                    "A case without a date is not a receipt.", "n/a"])
    gevallen = euvsdisinfo.lees_csv(pad)
    assert len(gevallen) == 3
    assert gevallen[0].outlets == ("RT", "Sputnik")
    # De echte snapshot schrijft dd.mm.yyyy en relatieve links; beide worden
    # een bonnetje dat je kunt volgen.
    assert gevallen[0].datum == "2022-03-01"
    assert gevallen[0].url == "https://euvsdisinfo.eu/report/a"
    assert gevallen[0].weerlegging == "No such plan exists."

    rapport, attr = euvsdisinfo.importeer(conn, gevallen, uitgesteld=True)
    assert attr.gevallen == 3
    # Het geval zonder datum is geen bonnetje (DR1) en dus geen claim.
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 2
    rij = conn.execute(
        "SELECT publisher, verdict_normalized, verdict_original, source FROM factcheck LIMIT 1"
    ).fetchone()
    assert tuple(rij) == ("EUvsDisinfo", "onwaar", "disinformation", euvsdisinfo.HERKOMST)
    bron = conn.execute("SELECT soort, herverdeelbaar FROM bron WHERE bron_id = 'euvsdisinfo'").fetchone()
    assert tuple(bron) == ("overheid", 1)

    ids = [r[0] for r in conn.execute("SELECT claim_id FROM claim")]
    bonnetjes = at.attributies_voor(conn, ids)
    assert len(bonnetjes) == 3  # RT+Sputnik bij A, Sputnik bij B
    assert {b.niveau for b in bonnetjes} == {"waargenomen"}
    assert {b.actor for b in bonnetjes} == {"RT", "Sputnik"}
    assert all(b.bron_soort == "overheid" and b.url.startswith("https://euvsdisinfo.eu") for b in bonnetjes)
    assert at.aandeel_met_attributie(conn) == (2, 2, 1.0)
    # Sputnik is één actor, niet twee.
    assert conn.execute("SELECT count(*) FROM actor").fetchone()[0] == 2


def test_the_importer_refuses_a_file_without_the_essential_columns(tmp_path):
    pad = tmp_path / "raar.csv"
    pad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError) as fout:
        euvsdisinfo.lees_csv(pad)
    assert "koppen in het bestand" in str(fout.value)


_OUD_SCHEMA = """
CREATE TABLE bron (
    bron_id TEXT PRIMARY KEY, naam TEXT NOT NULL, soort TEXT NOT NULL, licentie TEXT NOT NULL,
    attributietekst TEXT NOT NULL, url TEXT NOT NULL, herverdeelbaar INTEGER NOT NULL) STRICT;
CREATE TABLE actor (
    actor_id TEXT PRIMARY KEY,
    naam     TEXT NOT NULL CHECK (naam <> ''),
    soort    TEXT NOT NULL CHECK (soort IN ('operatie', 'outlet', 'netwerk'))
) STRICT;
CREATE TABLE actor_alias (
    sleutel  TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES actor(actor_id) ON DELETE CASCADE) STRICT;
"""


def test_a_platform_is_an_actor_kind_also_in_an_existing_database(tmp_path):
    """Een post op X verscheen niet bij een outlet maar op een platform
    (#25.16). Een database van vóór die soort krijgt hem erbij zonder dat er
    een actor, alias of attributie verloren gaat."""
    pad = tmp_path / "oud.db"
    oud = sqlite3.connect(pad)
    oud.executescript(_OUD_SCHEMA)
    oud.execute("INSERT INTO actor VALUES ('outlet:1', 'Een kanaal', 'outlet')")
    oud.execute("INSERT INTO actor_alias VALUES ('een kanaal', 'outlet:1')")
    oud.commit()
    oud.close()

    conn = connect(str(pad))
    init_schema(conn)
    _claim(conn)
    _bron(conn)
    x = at.registreer_actor(conn, naam="X", soort="platform")
    assert at.voeg_attributie(conn, claim_id="c1", actor_id="outlet:1", bron_id="b1",
                              datum="2016-02-04", url="https://example.org/1", niveau="waargenomen")
    assert at.voeg_attributie(conn, claim_id="c1", actor_id=x, bron_id="b1",
                              datum="2025-03-15", url="https://example.org/2", niveau="waargenomen")
    assert at.vind_actor(conn, "een kanaal") == "outlet:1"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        at.registreer_actor(conn, naam="Iets", soort="verzonnen")
    init_schema(conn)                                   # nog eens: niets dubbel, niets weg
    assert conn.execute("SELECT count(*) FROM actor").fetchone()[0] == 2


def test_the_show_more_button_never_becomes_part_of_an_outlet_name():
    """De snapshot is een scrape: waar de site een lange outletlijst afkapte,
    plakte de knoptekst aan de laatste outlet vast ("rayalauma.comShow more")
    of stond hij er los achter (#25.25)."""
    assert euvsdisinfo._splits_outlets("youm7.com, rayalauma.comShow more") == ["youm7.com", "rayalauma.com"]
    assert euvsdisinfo._splits_outlets("RT, Show more") == ["RT"]


def test_a_platform_named_in_the_outlet_column_is_registered_as_a_platform(conn, tmp_path):
    """"Twitter" en "t.me" zijn geen outlets maar de plek waar een outlet
    publiceert; een bonnetje "verscheen bij outlet Twitter" zegt niets (#25.25)."""
    pad = tmp_path / "snapshot.csv"
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Links", "Title", "Outlets", "Country", "Disinformation", "Information"])
        w.writerow(["01.03.2022", "/report/a", "Titel A", "Twitter, RT, t.me", "Germany",
                    "The EU plans to ban all Russian literature from its schools.", "No such plan."])
    euvsdisinfo.importeer(conn, euvsdisinfo.lees_csv(pad), uitgesteld=True)
    soorten = dict(conn.execute("SELECT naam, soort FROM actor").fetchall())
    assert soorten == {"Twitter": "platform", "RT": "outlet", "t.me": "platform"}


def test_repair_merges_truncated_outlets_and_moves_platforms_without_losing_a_receipt(conn):
    """Een bestaande database met de oude namen (#25.25): elke attributie van
    "youm7.comShow more" komt bij youm7.com, een dubbel bonnetje vervalt, een
    outlet zonder schone tweeling krijgt zijn schone naam, de losse knop is
    geen outlet, en Twitter wordt een platform. Een tweede keer doet niets."""
    at.registreer_bron(conn, **euvsdisinfo.BRON)
    for c in ("c1", "c2", "c3"):
        _claim(conn, c, f"bewering {c}")

    def bonnetje(claim_id, naam, url):
        actor_id = at.vind_actor(conn, naam) or at.registreer_actor(conn, naam=naam, soort="outlet")
        at.voeg_attributie(conn, claim_id=claim_id, actor_id=actor_id, bron_id=euvsdisinfo.BRON_ID,
                           datum="2020-01-01", url=url, niveau="waargenomen")

    bonnetje("c1", "youm7.com", "https://euvsdisinfo.eu/report/1")
    bonnetje("c1", "youm7.comShow more", "https://euvsdisinfo.eu/report/1")   # wordt een dubbel
    bonnetje("c2", "youm7.comShow more", "https://euvsdisinfo.eu/report/2")
    bonnetje("c3", "rayalauma.comShow more", "https://euvsdisinfo.eu/report/3")
    bonnetje("c3", "Show more", "https://euvsdisinfo.eu/report/3")
    bonnetje("c2", "Twitter", "https://euvsdisinfo.eu/report/2")

    rapport = euvsdisinfo.herstel(conn)

    assert rapport == euvsdisinfo.HerstelRapport(afgekapt=2, samengevoegd=1, knoppen=1, platforms=1,
                                                 bonnetjes_weg=2)
    namen = dict(conn.execute("SELECT naam, soort FROM actor").fetchall())
    assert namen == {"youm7.com": "outlet", "rayalauma.com": "outlet", "Twitter": "platform"}
    per_actor = dict(conn.execute(
        "SELECT ac.naam, group_concat(a.claim_id, ',') FROM attributie a JOIN actor ac USING(actor_id)"
        " GROUP BY ac.naam ORDER BY ac.naam").fetchall())
    assert sorted(per_actor.pop("youm7.com").split(",")) == ["c1", "c2"]
    assert per_actor == {"Twitter": "c2", "rayalauma.com": "c3"}
    assert at.vind_actor(conn, "youm7.comShow more") is None
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert euvsdisinfo.herstel(conn) == euvsdisinfo.HerstelRapport(0, 0, 0, 0, 0)
