"""Namen in de publicatiedatabase (PLAN #33.7, SPECS E9.S11): alleen wat de regels haalt in déze uitgave, niets wat
een mens weghaalde, en zonder de lezing van de PO alleen in een voorbeeld."""

import shutil
import sqlite3

import pytest

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from tests.test_publiceren import _bouw, _check, _claim, _lab, _pub


@pytest.fixture(autouse=True)
def _kleine_regels(monkeypatch):
    monkeypatch.setattr(nm, "MIN_PAGINAS", 2)          # in de tests twee pagina's in plaats van vijf


def _vijf(en, nl=None):
    return {"en": en, "nl": nl or en, "de": en, "es": en, "fr": en}


def _basis(tmp_path):
    lab = _lab(tmp_path)
    c = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida", cluster="cl-1"),
         "villa_es": _claim(lab, 2, "Zelenski compró una villa en Florida", taal="es", cluster="cl-1"),
         "jacht": _claim(lab, 3, "Zelensky bought two yachts"),
         "who": _claim(lab, 4, "WHO says masks do not work in Georgia"),
         "eigen": _claim(lab, 5, "Zelensky bought a casino")}
    _check(lab, c["villa"], "https://snopes.com/villa")
    _check(lab, c["villa_es"], "https://maldita.es/villa", taal="es")
    _check(lab, c["jacht"], "https://snopes.com/jacht")
    _check(lab, c["who"], "https://snopes.com/who")
    _check(lab, c["eigen"], "https://maldita.es/casino", bron="route-a")       # zelf opgehaald: niet in de uitgave
    return lab, {k: pb.nummer(v) for k, v in c.items()}


def _namen(n, **extra):
    namen = {"Q3874799": {"soort": "persoon", "namen": _vijf("Volodymyr Zelensky", "Volodymyr Zelensky"), "wikis": 150,
                          "paginas": [n["villa"], n["jacht"]]},
             "Q812": {"soort": "plaats", "namen": _vijf("Florida"), "wikis": 250, "paginas": [n["villa"], n["who"]]}}
    namen.update(extra)
    return {"namen": namen, "per_pagina": {n["villa"]: ["Q812", "Q3874799"], n["jacht"]: ["Q3874799"], n["who"]: ["Q812"]}}


def _rijen(pub, tabel, orde):
    return [dict(r) for r in pub.execute(f"SELECT * FROM {tabel} ORDER BY {orde}")]


def _kolommen(namen: dict) -> dict:
    """Een naam per sitetaal: in een nieuwe taal (B79) zonder label het Engels."""
    from doublecheck.sitetalen import SITETALEN
    return {f"naam_{t}": namen.get(t) or namen["en"] for t in SITETALEN}


def test_names_go_into_a_release_with_their_number_kind_and_a_name_in_every_site_language(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, namen=_namen(n))
    pub = _pub(m)
    assert _rijen(pub, "naam", "nummer") == [
        {"nummer": "Q3874799", "soort": "persoon", **_kolommen(_vijf("Volodymyr Zelensky")), "wikis": 150, "paginas": 2},
        {"nummer": "Q812", "soort": "plaats", **_kolommen(_vijf("Florida")), "wikis": 250, "paginas": 2}]
    # op de pagina in de volgorde waarin het model de namen noemde
    assert [(r["naam"], r["volg"]) for r in pub.execute("SELECT * FROM pagina_naam WHERE pagina = ? ORDER BY volg",
                                                         (n["villa"],))] == [("Q812", 0), ("Q3874799", 1)]
    assert m["namen"] == {"mee": 2, "per_soort": {"persoon": 1, "plaats": 1}, "paren": 4, "weggevallen": [], "concept": False}
    assert pb.controleer(m["bestand"])["namen"] == 2


def test_a_release_without_names_is_still_a_complete_file(tmp_path):
    lab, _ = _basis(tmp_path)
    m = _bouw(lab, tmp_path)
    pub = _pub(m)
    assert _rijen(pub, "naam", "nummer") == [] and _rijen(pub, "pagina_naam", "pagina") == []
    assert m["namen"]["mee"] == 0 and pb.controleer(m["bestand"])["namen"] == 0


def test_names_the_po_has_not_read_only_go_into_a_preview(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, namen=_namen(n), namen_concept=True)
    assert dict(_pub(m).execute("SELECT sleutel, waarde FROM meta"))["concepten"] == "1" and m["namen"]["concept"] is True
    with pytest.raises(pb.Weigering, match="namen"):
        pb.controleer(m["bestand"])
    assert pb.controleer(m["bestand"], concepten=True)["namen"] == 2


def test_a_page_that_is_not_in_the_release_drops_out_and_a_name_that_then_fails_the_rule_too(tmp_path):
    lab, n = _basis(tmp_path)
    namen = _namen(n, Q30={"soort": "plaats", "namen": _vijf("United States", "Verenigde Staten"), "wikis": 300,
                           "paginas": [n["who"], n["eigen"], "00000000000000ff"]})     # twee ervan bestaan niet
    m = _bouw(lab, tmp_path, namen=namen)
    assert [r["nummer"] for r in _pub(m).execute("SELECT nummer FROM naam ORDER BY nummer")] == ["Q3874799", "Q812"]
    assert m["namen"]["weggevallen"] == ["Q30"]


def test_the_number_of_a_merged_wording_follows_to_its_page_and_counts_once(tmp_path):
    lab, n = _basis(tmp_path)
    namen = _namen(n)
    namen["namen"]["Q812"]["paginas"] = [n["villa"], n["villa_es"], n["who"]]          # twee nummers van één pagina
    namen["per_pagina"][n["villa_es"]] = ["Q812"]
    pub = _pub(_bouw(lab, tmp_path, namen=namen))
    assert pub.execute("SELECT paginas FROM naam WHERE nummer = 'Q812'").fetchone()[0] == 2
    assert pub.execute("SELECT COUNT(*) FROM pagina_naam WHERE naam = 'Q812'").fetchone()[0] == 2


def test_a_person_whose_pages_come_from_one_newsroom_stays_out(tmp_path):
    lab, n = _basis(tmp_path)
    # Zelensky staat op de villa (Snopes en Maldita) en het jacht (Snopes): twee redacties. Iemand die alleen op de
    # twee pagina's van Snopes staat, valt af; een plaats met dezelfde pagina's niet.
    namen = _namen(n, Q1={"soort": "persoon", "namen": _vijf("Iemand"), "wikis": 9, "paginas": [n["jacht"], n["who"]]},
                   Q2={"soort": "plaats", "namen": _vijf("Ergens"), "wikis": 9, "paginas": [n["jacht"], n["who"]]})
    m = _bouw(lab, tmp_path, namen=namen)
    assert m["namen"]["weggevallen"] == ["Q1"] and m["namen"]["mee"] == 3


@pytest.mark.parametrize("naam", [
    {"soort": "ding", "namen": _vijf("Iets"), "wikis": 9},                    # een soort die niet bestaat
    {"soort": "plaats", "namen": {"en": "Alleen Engels"}, "wikis": 9},        # niet in alle vijf talen
    {"soort": "plaats", "namen": _vijf("Dorp"), "wikis": 2},                  # te weinig Wikipedia's
])
def test_a_name_that_does_not_meet_the_rules_never_gets_in(tmp_path, naam):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, namen=_namen(n, Q9={**naam, "paginas": [n["villa"], n["jacht"], n["who"]]}))
    assert m["namen"]["weggevallen"] == ["Q9"]


def test_a_number_that_is_no_number_never_gets_in(tmp_path):
    lab, n = _basis(tmp_path)
    slecht = {"soort": "plaats", "namen": _vijf("Dorp"), "wikis": 9, "paginas": [n["villa"], n["who"]]}
    m = _bouw(lab, tmp_path, namen=_namen(n, **{"Q9x": slecht, "P31": slecht}))
    assert m["namen"]["weggevallen"] == ["P31", "Q9x"]


def test_a_name_a_person_removed_is_in_no_release(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, namen=_namen(n), namen_niet=frozenset({"Q3874799"}))
    assert [r["nummer"] for r in _pub(m).execute("SELECT nummer FROM naam")] == ["Q812"]
    assert m["namen"]["weggevallen"] == ["Q3874799"]


def test_building_twice_gives_the_same_content_and_other_names_another(tmp_path):
    lab, n = _basis(tmp_path)
    een, twee = _bouw(lab, tmp_path, naam="een", namen=_namen(n)), _bouw(lab, tmp_path, naam="twee", namen=_namen(n))
    drie = _bouw(lab, tmp_path, naam="drie", namen=_namen(n), namen_niet=frozenset({"Q812"}))
    assert een["controlegetal"] == twee["controlegetal"] != drie["controlegetal"]


def test_the_other_spellings_wikidata_knows_go_in_for_search_without_the_names_themselves_or_signs(tmp_path):
    """PLAN #34.2z, SPECS E9.S11 AC8: de bijnamen van een naam die in de uitgave staat; niet de vijf namen zelf, niet een
    vorm zonder letter, en niets van een naam die er niet in staat."""
    lab, n = _basis(tmp_path)
    vormen = {"Q3874799": ["Volodymyr Zelensky", "Zelenskiy", "  Volodymyr   Zelenskiy ", "Зеленский", "🇺🇦", "♁", ""],
              "Q812": ["Florida", "Sunshine State", "FL", "Floride"],
              "Q999": ["Niet in de uitgave"]}
    m = _bouw(lab, tmp_path, namen=_namen(n), naamvormen=vormen)
    pub = _pub(m)
    assert _rijen(pub, "naam_vorm", "naam, vorm") == [
        {"naam": "Q3874799", "vorm": "Volodymyr Zelenskiy"}, {"naam": "Q3874799", "vorm": "Zelenskiy"},
        {"naam": "Q3874799", "vorm": "Зеленский"},
        {"naam": "Q812", "vorm": "FL"}, {"naam": "Q812", "vorm": "Floride"}, {"naam": "Q812", "vorm": "Sunshine State"}]
    pb.controleer(m["bestand"])
    # zonder bijnamen: een lege tabel, en het bestand blijft compleet
    assert _rijen(_pub(_bouw(lab, tmp_path, naam="kaal", namen=_namen(n))), "naam_vorm", "naam") == []


@pytest.mark.parametrize("breek, waarom", [
    ("INSERT INTO naam_vorm VALUES ('Q5', 'Iemand anders')", "bijnamen"),
    ("UPDATE pagina_naam SET pagina = '00000000000000ff' WHERE naam = 'Q812' AND volg = 0", "bij een pagina of een naam"),
    ("INSERT INTO pagina_naam SELECT pagina, 'Q5', 9 FROM pagina_naam WHERE naam = 'Q812'", "bij een pagina of een naam"),
    ("UPDATE naam SET naam_de = '' WHERE nummer = 'Q812'", "zonder nummer of zonder naam"),
    ("UPDATE naam SET paginas = 7 WHERE nummer = 'Q812'", "te weinig pagina"),
    ("DELETE FROM pagina_naam WHERE naam = 'Q812' AND volg = 0", "te weinig pagina"),
    ("UPDATE naam SET wikis = 1 WHERE nummer = 'Q812'", "Wikipedia"),
    ("UPDATE naam SET soort = 'persoon' WHERE nummer = 'Q812'", "redacties"),
])
def test_the_checker_refuses_a_file_in_which_a_name_was_changed_by_hand(tmp_path, breek, waarom):
    lab, n = _basis(tmp_path)
    namen = _namen(n)
    namen["namen"]["Q812"]["paginas"] = [n["jacht"], n["who"]]                 # Florida alleen bij Snopes
    namen["per_pagina"] = {n["jacht"]: ["Q3874799", "Q812"], n["who"]: ["Q812"], n["villa"]: ["Q3874799"]}
    m = _bouw(lab, tmp_path, namen=namen)
    kopie = tmp_path / "kopie.db"
    shutil.copy(m["bestand"], kopie)
    conn = sqlite3.connect(kopie)
    conn.execute(breek)
    conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match=waarom):
        pb.controleer(kopie)


def test_the_checker_refuses_a_file_with_a_name_that_was_removed_since(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, namen=_namen(n))
    pb.controleer(m["bestand"])
    with pytest.raises(pb.Weigering, match="weggehaald"):
        pb.controleer(m["bestand"], namen_niet=frozenset({"Q812"}))
