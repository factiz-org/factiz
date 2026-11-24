"""Dossiers in de publicatiedatabase (PLAN #33.6, SPECS E9.S7): alleen wat een mens goedkeurde, en niets zonder akkoord."""

import json
import shutil
import sqlite3

import pytest

from doublecheck.sitetalen import SITETALEN

from doublecheck import dossiers as ds
from doublecheck import publiceren as pb
from tests.test_publiceren import LANDEN, THEMAS, _bouw, _check, _claim, _lab, _pub

AKKOORD = '2026-11-12, PO: "ja, zo mag het"'


def _vijf(tekst):
    return {taal: f"{tekst} ({taal})" for taal in ds.SITETALEN}


def _dossier(sleutel, nummers=(), *, soort="verhaal", status="akkoord", items=(), verwant=(), thema="war",
             onderdeel="ukraine", bron=None):
    ruw = {"soort": soort, "status": status, "thema": thema, "onderdeel": onderdeel, "verwant": list(verwant),
           "naam": _vijf(sleutel), "inleiding": _vijf("Een alinea over " + sleutel),
           "nagelezen": {taal: False for taal in ds.SITETALEN}, "item": [dict(i) for i in items]}
    if status == "akkoord":
        ruw["akkoord"] = AKKOORD
    if soort == "netwerk":
        ruw["vastgesteld"] = {"door": "EU DisinfoLab", "url": "https://www.disinfo.eu/doppelganger", "datum": "2022-09-27"}
    goed = {"goedgekeurd_door": "PO", "datum": "2026-11-12",
            "factchecks": [{"nummer": n, **(bron or {})} for n in nummers]}
    return ds.keur(sleutel, ruw, goed)


def _item(soort="onderzoek", datum="2023-12-20", bron="BBC Verify", url="https://www.bbc.com/news/x", titel="Hoe het reisde"):
    return {"soort": soort, "datum": datum, "bron": bron, "url": url, "titel": _vijf(titel)}


def _basis(tmp_path):
    lab = _lab(tmp_path)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida", cluster="cl-1"),
         "villa_es": _claim(lab, 2, "Zelenski compró una villa en Florida", taal="es", cluster="cl-1"),
         "jacht": _claim(lab, 3, "Zelensky bought two yachts"),
         "zonder_datum": _claim(lab, 4, "Zelenska bought a Bugatti"),
         "eigen": _claim(lab, 5, "Zelensky bought a casino in Cyprus")}
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2024-03-05")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr")
    _check(lab, n["villa_es"], "https://maldita.es/villa", datum="2023-12-31", taal="es")
    _check(lab, n["jacht"], "https://snopes.com/jacht", datum="2023-12-01")
    _check(lab, n["zonder_datum"], "https://snopes.com/bugatti", datum="")
    _check(lab, n["eigen"], "https://maldita.es/casino", bron="route-a")      # zelf opgehaald: niet in de uitgave
    return lab, {k: pb.nummer(v) for k, v in n.items()}


def _items(pub, sleutel):
    return [dict(r) for r in pub.execute("SELECT * FROM dossier_item WHERE dossier = ? ORDER BY volg", (sleutel,))]


def test_only_an_approved_dossier_goes_into_a_release_and_a_draft_only_into_a_preview(tmp_path):
    lab, n = _basis(tmp_path)
    dossiers = [_dossier("zelensky-luxury", [n["villa"]]), _dossier("biolabs", [n["jacht"]], status="concept")]
    m = _bouw(lab, tmp_path, dossiers=dossiers)
    pub = _pub(m)
    assert [r["sleutel"] for r in pub.execute("SELECT sleutel FROM dossier")] == ["zelensky-luxury"]
    assert "concepten" not in dict(pub.execute("SELECT sleutel, waarde FROM meta"))
    assert set(m["dossiers"]) == {"zelensky-luxury"} and m["concepten"] == 0
    pb.controleer(m["bestand"])
    # het voorbeeld voor de eigen computer: het concept gaat mee, het bestand zegt dat, en de keuring weigert het
    voorbeeld = _bouw(lab, tmp_path, naam="voorbeeld", dossiers=dossiers, concepten=True)
    pub = _pub(voorbeeld)
    assert {r["sleutel"]: r["concept"] for r in pub.execute("SELECT sleutel, concept FROM dossier")} == {
        "biolabs": 1, "zelensky-luxury": 0}
    assert dict(pub.execute("SELECT sleutel, waarde FROM meta"))["concepten"] == "1" and voorbeeld["concepten"] == 1
    with pytest.raises(pb.Weigering, match="akkoord"):
        pb.controleer(voorbeeld["bestand"])
    assert pb.controleer(voorbeeld["bestand"], concepten=True)["dossiers"] == 2


def test_a_fact_check_sits_on_the_timeline_at_its_first_check_and_the_newest_item_comes_first(tmp_path):
    lab, n = _basis(tmp_path)
    d = _dossier("zelensky-luxury", [n["zonder_datum"], n["jacht"], n["villa"]],
                 items=[_item(datum="2024-01-15"), _item("besluit", "2023-12-01", "EU", "https://europa.eu/x", "Sancties")])
    pub = _pub(_bouw(lab, tmp_path, dossiers=[d], indeling={n["villa"]: {"thema": "war", "onderdeel": "ukraine",
                                                                         "tweede": "", "land": "UA"}},
                     themas=THEMAS, landen=LANDEN))
    rij = dict(pub.execute("SELECT * FROM dossier").fetchone())
    assert rij["soort"] == "verhaal" and rij["concept"] == 0 and rij["thema"] == "war" and rij["onderdeel"] == "ukraine"
    assert rij["naam_nl"] == "zelensky-luxury (nl)" and rij["inleiding_fr"] == "Een alinea over zelensky-luxury (fr)"
    assert rij["vastgesteld_door"] == "" and rij["vastgesteld_url"] == ""
    items = _items(pub, "zelensky-luxury")
    # de villa is drie keer gecheckt (2022, 2023, 2024): ze staat op 2022, de dag van de eerste check
    assert [(i["soort"], i["datum"], i["pagina"]) for i in items] == [
        ("onderzoek", "2024-01-15", None), ("besluit", "2023-12-01", None), ("factcheck", "2023-12-01", n["jacht"]),
        ("factcheck", "2022-04-01", n["villa"]), ("factcheck", "", n["zonder_datum"])]
    assert [i["volg"] for i in items] == [0, 1, 2, 3, 4]
    assert items[0]["titel_de"] == "Hoe het reisde (de)" and items[0]["bron"] == "BBC Verify"
    assert items[0]["url"] == "https://www.bbc.com/news/x" and items[2]["titel_en"] == "" and items[2]["url"] == ""


def test_a_dossier_keeps_its_theme_only_if_the_release_carries_that_theme(tmp_path):
    lab, n = _basis(tmp_path)
    pub = _pub(_bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"]])]))      # een uitgave zonder thema's
    assert tuple(pub.execute("SELECT thema, onderdeel FROM dossier").fetchone()) == (None, "")


def test_a_number_that_is_not_in_the_release_drops_out_and_is_named_in_the_manifest(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"], n["eigen"], "00000000000000ff"])])
    assert [i["pagina"] for i in _items(_pub(m), "zelensky-luxury")] == [n["villa"]]
    assert m["dossiers"]["zelensky-luxury"] == {"soort": "verhaal", "concept": False, "factchecks": 1, "items": 0,
                                                "weggevallen": sorted([n["eigen"], "00000000000000ff"]), "versies": 0}
    pb.controleer(m["bestand"])


def test_the_number_of_a_merged_wording_follows_to_its_page_and_counts_once(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa_es"], n["villa"]])])
    assert [i["pagina"] for i in _items(_pub(m), "zelensky-luxury")] == [n["villa"]]
    assert m["dossiers"]["zelensky-luxury"]["weggevallen"] == []


def test_one_fact_check_in_two_story_dossiers_refuses_the_build_also_through_a_merged_wording(tmp_path):
    lab, n = _basis(tmp_path)
    with pytest.raises(pb.Weigering, match="twee verhaaldossiers"):
        _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"]]), _dossier("biolabs", [n["villa_es"]])])
    # een concept dat niet meegaat, telt niet mee
    _bouw(lab, tmp_path, naam="b", dossiers=[_dossier("zelensky-luxury", [n["villa"]]),
                                             _dossier("biolabs", [n["villa_es"]], status="concept")])


def test_a_network_dossier_carries_who_identified_it_and_per_fact_check_the_source_and_the_level(tmp_path):
    lab, n = _basis(tmp_path)
    bron = {"niveau": "toegeschreven", "bron": "EUvsDisinfo", "url": "https://euvsdisinfo.eu/report/x"}
    dossiers = [_dossier("zelensky-luxury", [n["villa"]], verwant=["doppelganger"]),
                _dossier("doppelganger", [n["villa"], n["jacht"]], soort="netwerk", bron=bron, verwant=["zelensky-luxury"])]
    m = _bouw(lab, tmp_path, dossiers=dossiers)
    pub = _pub(m)
    rij = dict(pub.execute("SELECT * FROM dossier WHERE sleutel = 'doppelganger'").fetchone())
    assert (rij["soort"], rij["vastgesteld_door"], rij["vastgesteld_url"], rij["vastgesteld_datum"]) == (
        "netwerk", "EU DisinfoLab", "https://www.disinfo.eu/doppelganger", "2022-09-27")
    assert all((i["niveau"], i["bron"], i["url"]) == ("toegeschreven", "EUvsDisinfo", "https://euvsdisinfo.eu/report/x")
               for i in _items(pub, "doppelganger"))
    # dezelfde factcheck mag in een verhaal én in een netwerk staan: ze verwijzen naar elkaar, ze zitten niet in elkaar
    assert sorted(tuple(r) for r in pub.execute("SELECT dossier, verwant FROM dossier_verwant")) == [
        ("doppelganger", "zelensky-luxury"), ("zelensky-luxury", "doppelganger")]
    pb.controleer(m["bestand"])


def test_a_related_dossier_that_stays_out_of_the_release_is_not_referred_to(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"]], verwant=["biolabs"]),
                                       _dossier("biolabs", [n["jacht"]], status="concept", verwant=["zelensky-luxury"])])
    assert _pub(m).execute("SELECT COUNT(*) FROM dossier_verwant").fetchone()[0] == 0


def test_building_twice_gives_the_same_content_and_a_changed_dossier_another(tmp_path):
    lab, n = _basis(tmp_path)
    een = _bouw(lab, tmp_path, naam="een", dossiers=[_dossier("zelensky-luxury", [n["villa"], n["jacht"]], items=[_item()])])
    twee = _bouw(lab, tmp_path, naam="twee", dossiers=[_dossier("zelensky-luxury", [n["jacht"], n["villa"]], items=[_item()])])
    drie = _bouw(lab, tmp_path, naam="drie", dossiers=[_dossier("zelensky-luxury", [n["villa"]], items=[_item()])])
    assert een["controlegetal"] == twee["controlegetal"] != drie["controlegetal"]
    assert een["controlegetal"] != _bouw(lab, tmp_path, naam="geen")["controlegetal"]


@pytest.mark.parametrize("breek, waarom", [
    ("UPDATE dossier_item SET pagina = '00000000000000ff' WHERE soort = 'factcheck'", "zonder pagina"),
    ("UPDATE dossier_item SET url = '' WHERE soort = 'onderzoek'", "zonder bron, link of titel"),
    ("UPDATE dossier_item SET titel_fr = '' WHERE soort = 'onderzoek'", "zonder bron, link of titel"),
    ("UPDATE dossier SET naam_de = ''", "zonder naam of inleiding"),
    ("UPDATE dossier SET soort = 'netwerk'", "netwerk"),
    ("UPDATE dossier SET thema = 'astrology'", "thema"),
    ("INSERT INTO dossier_item SELECT 'spook', volg, soort, datum, pagina, " + ", ".join(f"titel_{t}" for t in SITETALEN)
     + ", bron, url, niveau, versie FROM dossier_item", "zonder dossier"),
    ("INSERT INTO dossier_verwant VALUES ('zelensky-luxury', 'spook')", "verwijzingen"),
])
def test_the_checker_refuses_a_file_in_which_a_dossier_was_changed_by_hand(tmp_path, breek, waarom):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"]], items=[_item()])])
    kopie = tmp_path / "kopie.db"
    shutil.copy(m["bestand"], kopie)
    conn = sqlite3.connect(kopie)
    conn.execute(breek)
    # het controlegetal opnieuw, zodat de keuring op de inhoud zelf moet weigeren en niet op het getal
    conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match=waarom):
        pb.controleer(kopie)


def test_the_checker_refuses_one_fact_check_in_two_story_dossiers(tmp_path):
    lab, n = _basis(tmp_path)
    m = _bouw(lab, tmp_path, dossiers=[_dossier("zelensky-luxury", [n["villa"]]), _dossier("biolabs", [n["jacht"]])])
    kopie = tmp_path / "kopie.db"
    shutil.copy(m["bestand"], kopie)
    conn = sqlite3.connect(kopie)
    conn.execute("UPDATE dossier_item SET pagina = ? WHERE dossier = 'biolabs'", (n["villa"],))
    conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match="twee verhaaldossiers"):
        pb.controleer(kopie)


def test_a_release_without_dossiers_is_still_a_complete_file(tmp_path):
    lab, _ = _basis(tmp_path)
    m = _bouw(lab, tmp_path)
    assert m["dossiers"] == {} and m["concepten"] == 0
    assert _pub(m).execute("SELECT COUNT(*) FROM dossier").fetchone()[0] == 0
    assert pb.controleer(m["bestand"])["dossiers"] == 0
    assert json.loads((tmp_path / "uit" / "manifest.json").read_text(encoding="utf-8"))["dossiers"] == {}


# --- versies (E9.S7 AC8) ---------------------------------------------------------------------------------------------

def _met_versies(sleutel, paren, **meer):
    d = _dossier(sleutel, [n for n, _ in paren], **meer)
    d["factchecks"] = [{"nummer": n, **({"versie": v} if v else {})} for n, v in paren]
    return d


def test_a_version_goes_into_the_release_and_a_version_that_keeps_one_fact_check_does_not(tmp_path):
    lab, n = _basis(tmp_path)
    d = _met_versies("zelensky-luxury", [(n["villa"], "villa-florida"), (n["jacht"], "villa-florida"),
                                         (n["zonder_datum"], "bugatti"), (n["eigen"], "bugatti")])
    m = _bouw(lab, tmp_path, dossiers=[d])
    versie = {i["pagina"]: i["versie"] for i in _items(_pub(m), "zelensky-luxury")}
    # de tweede Bugatti-factcheck staat niet in deze uitgave: de versie houdt er één over en vervalt
    assert versie == {n["villa"]: "villa-florida", n["jacht"]: "villa-florida", n["zonder_datum"]: ""}
    assert m["dossiers"]["zelensky-luxury"]["versies"] == 1
    pb.controleer(m["bestand"])


def test_two_numbers_of_one_page_keep_one_version(tmp_path):
    lab, n = _basis(tmp_path)
    d = _met_versies("zelensky-luxury", [(n["villa"], "villa-florida"), (n["villa_es"], "villa-florida"),
                                         (n["jacht"], "villa-florida")])
    items = _items(_pub(_bouw(lab, tmp_path, dossiers=[d])), "zelensky-luxury")
    assert sorted((i["pagina"], i["versie"]) for i in items) == sorted([(n["villa"], "villa-florida"), (n["jacht"], "villa-florida")])


@pytest.mark.parametrize("breek, waarom", [
    ("UPDATE dossier_item SET versie = 'x-y' WHERE soort = 'onderzoek'", "versie"),
    ("UPDATE dossier_item SET versie = 'alleen' WHERE pagina = (SELECT MIN(pagina) FROM dossier_item WHERE soort = 'factcheck')",
     "versies met één factcheck"),
    # een netwerk dat verder klopt (vaststeller, en bron en niveau per factcheck), maar nog een versie draagt
    ("UPDATE dossier SET soort = 'netwerk', vastgesteld_door = 'x', vastgesteld_url = 'https://x.org/y', "
     "vastgesteld_datum = '2022-09-27'; UPDATE dossier_item SET bron = 'EUvsDisinfo', url = 'https://euvsdisinfo.eu/x', "
     "niveau = 'toegeschreven' WHERE soort = 'factcheck'", "versie"),
])
def test_the_checker_refuses_a_version_where_it_does_not_belong(tmp_path, breek, waarom):
    lab, n = _basis(tmp_path)
    d = _met_versies("zelensky-luxury", [(n["villa"], "villa-florida"), (n["jacht"], "villa-florida"), (n["zonder_datum"], "")],
                     items=[_item()])
    m = _bouw(lab, tmp_path, dossiers=[d])
    kopie = tmp_path / "kopie.db"
    shutil.copy(m["bestand"], kopie)
    conn = sqlite3.connect(kopie)
    conn.executescript(breek)
    conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match=waarom):
        pb.controleer(kopie)
