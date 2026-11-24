"""De uitgave naar D1 (PLAN #34.2bo, stap 2; B80): dezelfde gegevens, in opdrachten die D1 aanneemt, nagekeken tot op de rij."""

import json
import sqlite3

import pytest

from doublecheck import d1uitgave as d1
from doublecheck import publiceren as pb
from tests.test_publiceren import EU, _bouw, _check, _claim, _lab

LANG = "Vaccines " + "contain microchips and the government knows it. " * 70


def _uitgave(tmp_path):
    lab = _lab(tmp_path)
    teksten = [("en", "The moon is made of 'cheese'"), ("hi", "टीका सुरक्षित नहीं है"), ("ar", "اللقاح غير آمن"),
               ("zh", "疫苗接种不安全"), ("en", LANG), ("de", "München verbietet das Impfen")]
    for i, (taal, tekst) in enumerate(teksten, 1):
        _check(lab, _claim(lab, i, tekst, taal=taal), f"https://euvsdisinfo.eu/report/{i}", bron=EU, taal=taal)
    return _bouw(lab, tmp_path)


def _laad(map_, tmp_path, naam="kopie.db"):
    """Doet wat D1 doet bij een import: elk deel in één transactie, met de verwijzingen aan."""
    kopie = sqlite3.connect(tmp_path / naam, isolation_level=None)
    kopie.execute("PRAGMA foreign_keys = ON")
    for deel in json.loads((map_ / "klaar.json").read_text(encoding="utf-8"))["delen"]:
        kopie.executescript("BEGIN;\n" + (map_ / deel["bestand"]).read_text(encoding="utf-8") + "\nCOMMIT;")
    return kopie


def _zoals_d1(conn):
    """Een vraag aan een SQLite zoals D1 haar beantwoordt: via JSON, 2.0 wordt 2, bytes een lijst getallen."""
    def vorm(v):
        if isinstance(v, bytes):
            return list(v)
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    def vraag(sql):
        cur = conn.execute(sql)
        namen = [k[0] for k in cur.description] if cur.description else []
        return json.loads(json.dumps([{n: vorm(v) for n, v in zip(namen, r)} for r in cur.fetchall()]))
    return vraag


def test_every_statement_fits_d1_and_the_copy_has_the_same_checksum_rowids_and_search_hits(tmp_path):
    m = _uitgave(tmp_path)
    klaar = d1.schrijf(m["bestand"], tmp_path / "d1", grens=8_000)
    opdrachten = [o for deel in klaar["delen"] for o in (tmp_path / "d1" / deel["bestand"]).read_text(
        encoding="utf-8").split(";\n") if o.strip()]
    assert len(opdrachten) > 10
    assert max(len((o + ";").encode()) for o in opdrachten) <= 8_000
    kopie = _laad(tmp_path / "d1", tmp_path)
    assert pb.controlegetal(kopie) == m["controlegetal"]
    origineel = sqlite3.connect(f"file:{m['bestand']}?mode=ro", uri=True)
    for tabel in ("pagina", "check_", "zoek", "zoek3"):
        vraag = f"SELECT rowid, * FROM {tabel} ORDER BY rowid"
        assert kopie.execute(vraag).fetchall() == origineel.execute(vraag).fetchall()
    for tabel, zoekvraag in (("zoek", '"cheese"'), ("zoek", '"münchen"'), ("zoek", '"munchen"'), ("zoek3", '"疫苗接"'),
                             ("zoek", '"सुरक्षित"')):
        vraag = f"SELECT nummer FROM {tabel} WHERE {tabel} MATCH '{zoekvraag}' ORDER BY rank"
        assert kopie.execute(vraag).fetchall() == origineel.execute(vraag).fetchall() != []
    kopie.execute("INSERT INTO zoek(zoek) VALUES('integrity-check')")   # het register past bij zijn tekst


def test_a_row_larger_than_one_statement_goes_in_parts_and_comes_back_exactly(tmp_path):
    # een eigen check met veertien vertalingen is groter dan één opdracht (#37.8, 2026-11-19): de rij gaat in met een lege
    # tekst en de tekst komt er in stukken bij, elk stuk onder de grens; niets wordt afgekapt
    m = _uitgave(tmp_path)
    klaar = d1.schrijf(m["bestand"], tmp_path / "d1", grens=3_000)
    opdrachten = [o for deel in klaar["delen"] for o in (tmp_path / "d1" / deel["bestand"]).read_text(
        encoding="utf-8").split(";\n") if o.strip()]
    assert max(len((o + ";").encode()) for o in opdrachten) <= 3_000
    assert any(o.startswith("UPDATE ") and " || " in o for o in opdrachten)
    kopie = _laad(tmp_path / "d1", tmp_path)
    assert pb.controlegetal(kopie) == m["controlegetal"]
    origineel = sqlite3.connect(f"file:{m['bestand']}?mode=ro", uri=True)
    for tabel in ("pagina", "check_", "zoek"):
        vraag = f"SELECT rowid, * FROM {tabel} ORDER BY rowid"
        assert kopie.execute(vraag).fetchall() == origineel.execute(vraag).fetchall()
    kopie.execute("INSERT INTO zoek(zoek) VALUES('integrity-check')")


def test_a_row_that_does_not_fit_even_without_its_texts_is_refused_not_cut(tmp_path):
    m = _uitgave(tmp_path)
    with pytest.raises(d1.Weigering, match="past niet"):
        d1.schrijf(m["bestand"], tmp_path / "d1", grens=120)
    assert not (tmp_path / "d1" / "klaar.json").exists()


def test_a_release_the_check_refuses_is_never_written(tmp_path):
    m = _uitgave(tmp_path)
    conn = sqlite3.connect(m["bestand"])
    conn.execute("UPDATE pagina SET bewering = bewering || '.' WHERE rowid = 1")
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match="controlegetal"):
        d1.schrijf(m["bestand"], tmp_path / "d1")
    assert not (tmp_path / "d1").exists() or not any((tmp_path / "d1").iterdir())


def test_values_come_back_exactly_with_their_type():
    conn = sqlite3.connect(":memory:")
    for waarde in (None, 0, -7, 2**62, 0.1, 2.0, -2.5e-10, 1e300, "", "l'eau", "regel\nregel", "a\x00b", "🙂 क़ ب",
                   b"", b"\x00\xff"):
        terug = conn.execute(f"SELECT {d1.literaal(waarde)}").fetchone()[0]
        assert terug == waarde and type(terug) is type(waarde)
    with pytest.raises(d1.Weigering):
        d1.literaal(float("nan"))


def test_tables_come_after_the_tables_they_point_to_and_shadow_tables_of_the_search_stay_out():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE kind (id TEXT PRIMARY KEY, ouder TEXT REFERENCES ouder(id));
        CREATE TABLE ouder (id TEXT PRIMARY KEY, boven TEXT REFERENCES ouder(id));
        CREATE VIRTUAL TABLE zoek USING fts5(nummer UNINDEXED, tekst);
        CREATE TABLE los (id TEXT);""")
    assert d1.volgorde(conn) == ["ouder", "kind", "zoek", "los"]


def test_the_import_refuses_a_database_that_already_has_tables(tmp_path):
    m = _uitgave(tmp_path)
    d1.schrijf(m["bestand"], tmp_path / "d1")
    uitgevoerd = []
    with pytest.raises(d1.Weigering, match="al tabellen"):
        d1.importeren(tmp_path / "d1", "factiz-2026-11-10", vraag=lambda sql: [{"name": "pagina"}],
                      voer_uit=uitgevoerd.append)
    assert uitgevoerd == []
    d1.importeren(tmp_path / "d1", "factiz-2026-11-10", vraag=lambda sql: [], voer_uit=uitgevoerd.append)
    assert [a[:3] for a in uitgevoerd] == [["d1", "execute", "factiz-2026-11-10"]] * len(uitgevoerd) != []
    assert all("--remote" in a and "--file" in a for a in uitgevoerd)


def test_the_import_refuses_a_half_written_folder(tmp_path):
    (tmp_path / "d1").mkdir()
    (tmp_path / "d1" / "deel-001.sql").write_text("CREATE TABLE x (a);", encoding="utf-8")
    with pytest.raises(d1.Weigering, match="klaar"):
        d1.importeren(tmp_path / "d1", "factiz-x", vraag=lambda sql: [], voer_uit=lambda a: None)


def test_checking_passes_on_a_true_copy_and_names_the_table_with_one_changed_character_or_a_missing_row(tmp_path):
    m = _uitgave(tmp_path)
    d1.schrijf(m["bestand"], tmp_path / "d1", grens=8_000)
    kopie = _laad(tmp_path / "d1", tmp_path)
    vragen = [("zoek", '"cheese"'), ("zoek3", '"疫苗接"')]
    verslag = d1.nakijken(m["bestand"], _zoals_d1(kopie), zoekvragen=vragen, blad=500)
    assert verslag["tabellen"]["pagina"]["rijen"] == 6 and verslag["zoekvragen"] == 2
    kopie.execute("UPDATE pagina SET bewering = 'X' || substr(bewering, 2) WHERE rowid = 2")
    with pytest.raises(d1.Weigering, match="pagina"):
        d1.nakijken(m["bestand"], _zoals_d1(kopie), zoekvragen=vragen, blad=500)
    kopie2 = _laad(tmp_path / "d1", tmp_path, "kopie2.db")
    kopie2.execute("PRAGMA foreign_keys = OFF")
    kopie2.execute("DELETE FROM check_ WHERE rowid = (SELECT max(rowid) FROM check_)")
    with pytest.raises(d1.Weigering, match="check_"):
        d1.nakijken(m["bestand"], _zoals_d1(kopie2), zoekvragen=vragen, blad=500)


def test_creating_a_database_names_it_after_the_release_and_puts_it_in_western_europe():
    gezien = []

    def voer_uit(args):
        gezien.append(args)
        return '{\n "d1_databases": [{"binding": "x", "database_name": "factiz-2026-11-16",\n' \
               ' "database_id": "f1cfa88e-7941-4b44-bb45-ac0bc1c17a4d"}]}'
    assert d1.aanmaken("2026-11-16", voer_uit) == {"naam": "factiz-2026-11-16",
                                                    "id": "f1cfa88e-7941-4b44-bb45-ac0bc1c17a4d"}
    assert gezien == [["d1", "create", "factiz-2026-11-16", "--location", "weur"]]


def test_the_default_limit_stays_below_what_d1_refused():
    # D1 noemt 100 KB, maar weigerde een opdracht van 99.999 bytes met SQLITE_TOOBIG; 90.000 ging goed (34.2bo, stap 2)
    assert d1.GRENS <= 90_000


def test_a_question_to_d1_waits_and_tries_again_when_d1_is_overloaded_and_not_on_other_errors():
    """2026-11-17: het nakijken van een uitgave stopte op "D1 DB is overloaded" (code 7429); een pauze en opnieuw."""
    from doublecheck import d1uitgave as d1

    keer, pauzes = {"n": 0}, []

    def overbelast():
        keer["n"] += 1
        if keer["n"] < 3:
            raise d1.Weigering('wrangler d1 execute mislukte: {"text": "D1 DB is overloaded. [code: 7429]"}')
        return "[]"

    assert d1.met_geduld(overbelast, slaap=pauzes.append) == "[]" and keer["n"] == 3 and pauzes == [10.0, 20.0]

    def kapot():
        raise d1.Weigering("wrangler d1 execute mislukte: no such table")

    import pytest
    with pytest.raises(d1.Weigering, match="no such table"):
        d1.met_geduld(kapot, slaap=pauzes.append)
    with pytest.raises(d1.Weigering, match="7429"):
        d1.met_geduld(lambda: (_ for _ in ()).throw(d1.Weigering("code 7429")), pogingen=2, slaap=lambda s: None)
