"""De wereldlijst (B90, B91, PLAN #37.12, SPECS E10.S6): wat wereldwijd rondgaat, als gewone factcheckpagina met de
oordelen van de redacties, wat ze vonden in de woorden van Factiz, en waar het rondging. Geen eigen oordeel (DR2)."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from doublecheck import wereldlijst as wl
from factiz_site import app as fa
from factiz_site import gelijk, i18n
from tests.test_publiceren import REGISTER, _check, _claim, _lab

REG = {**REGISTER, "dpa-factchecking.com": "dpa", "verifica.efe.com": "EFE Verifica"}


def _overzicht(**anders):
    o = {
        "sleutel": "crimea-bridge-ai-visuals", "status": "gepubliceerd", "regio": "europa", "landen": ["UA", "RU"],
        "talen": ["en", "pl"], "soort": "image", "taal": "en",
        "bewering": "Pictures show the Crimea bridge broken apart after Ukraine's strike on it.",
        "rondgang": "The visuals spread on Facebook and X from 18 November 2026 [1] [2].",
        "kern": ["Ukraine did strike the bridge, but the pictures do not show that damage [1] [2].",
                 "A detection tool found an AI watermark in one image [1]."],
        "checks": [
            {"nr": 1, "redactie": "AFP Fact Check", "land": "FR", "taal": "en", "oordeel": "False", "oordeel_en": "False",
             "schaal": "onwaar", "datum": "2026-11-20", "titel": "AI-generated image", "url": "https://factcheck.afp.com/a"},
            {"nr": 2, "redactie": "dpa-Faktencheck", "land": "DE", "taal": "de", "oordeel": "Fälschung",
             "oordeel_en": "Fake", "schaal": "onwaar", "datum": "2026-11-18", "titel": "Video ist KI-generiert",
             "url": "https://dpa-factchecking.com/germany/b/"}],
        "post": None, "waarom": "A major moment in the war."}
    o.update(anders)
    return o


def _bouw(map_, overzichten, concepten=False):
    map_.mkdir(parents=True, exist_ok=True)
    lab = _lab(map_)
    _check(lab, _claim(lab, 1, "Garlic water cures covid"), "https://snopes.com/garlic", datum="2021-01-01")
    lab.commit()
    return pb.bouw(lab, map_ / "uit", register=REG, vaag=frozenset(), datum="2026-11-23",
                   wereldlijst=overzichten, concepten=concepten)


def test_an_overview_needs_a_source_for_every_sentence_and_gives_no_verdict_of_its_own():
    assert wl.controleer(_overzicht(), REG) == []
    fouten = lambda **a: " | ".join(wl.controleer(_overzicht(**a), REG))
    assert "zonder bron" in fouten(kern=["Ukraine did strike the bridge."])
    assert "[3]" in fouten(kern=["The pictures are fake [3]."] + _overzicht()["kern"])
    assert "niet genoemd" in fouten(kern=["The pictures are fake [1]."], rondgang="It spread on X [1].")
    assert "streep" in fouten(bewering="Pictures show the bridge — broken apart.")
    assert "schaal" in fouten(checks=[{**_overzicht()["checks"][0], "schaal": "klopt-wel"}, _overzicht()["checks"][1]])
    # minstens één check van een erkende redactie of een persbureau
    vreemd = [{**k, "url": f"https://blog.invalid/{k['nr']}"} for k in _overzicht()["checks"]]
    assert "erkende" in fouten(checks=vreemd)
    # een post van een privépersoon alleen als archiefkopie (zoals bij de eigen checks)
    assert "privépersoon" in fouten(post={"platform": "X", "url": "https://x.com/iemand/status/1", "prive": True})


def test_an_overview_becomes_an_ordinary_fact_check_page_with_the_verdicts_of_the_newsrooms(tmp_path):
    m = _bouw(tmp_path, [_overzicht()])
    conn = sqlite3.connect(m["bestand"])
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    assert conn.execute("SELECT bewering, taal, label, checks, redacties FROM pagina WHERE nummer = ?", (nr,)).fetchone() == (
        "Pictures show the Crimea bridge broken apart after Ukraine's strike on it.", "en", "onwaar", 2, 2)
    # de nieuwste check eerst, zoals in het archief; de naam van de redactie uit het register waar het die kent
    assert conn.execute("SELECT volg, redactie, oordeel, oordeel_eigen, datum, url, bron FROM check_ WHERE pagina = ? "
                        "ORDER BY volg", (nr,)).fetchall() == [
        (0, "AFP", "onwaar", "False", "2026-11-20", "https://factcheck.afp.com/a", wl.BRON["bron"]),
        (1, "dpa", "onwaar", "Fälschung", "2026-11-18", "https://dpa-factchecking.com/germany/b/", wl.BRON["bron"])]
    assert conn.execute("SELECT naam FROM bron WHERE bron = ?", (wl.BRON["bron"],)).fetchone() == ("Factiz",)
    assert conn.execute("SELECT volg, soort, zin, bronnen FROM samenvatting WHERE pagina = ? ORDER BY volg", (nr,)).fetchall() == [
        (0, "vond", "Ukraine did strike the bridge, but the pictures do not show that damage.",
         json.dumps(["https://factcheck.afp.com/a", "https://dpa-factchecking.com/germany/b/"])),
        (1, "vond", "A detection tool found an AI watermark in one image.", json.dumps(["https://factcheck.afp.com/a"])),
        (2, "rondgang", "The visuals spread on Facebook and X from 18 November 2026.",
         json.dumps(["https://factcheck.afp.com/a", "https://dpa-factchecking.com/germany/b/"]))]
    assert m["wereldlijst"] == {"gepubliceerd": 1, "concept": 0}
    assert pb.controleer(m["bestand"])["paginas"] == 2


def test_an_overview_gets_the_translations_that_passed_their_reading_test_like_any_page(tmp_path):
    """2026-11-23: de eerste bouw koppelde de vertalingen voordat de overzichten erbij kwamen, zodat ze er geen kregen."""
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "Garlic water cures covid"), "https://snopes.com/garlic", datum="2021-01-01")
    lab.commit()
    m = pb.bouw(lab, tmp_path / "uit", register=REG, vaag=frozenset(), datum="2026-11-23", wereldlijst=[_overzicht()],
                vertalingen={"es": {nr: "Imágenes muestran el puente de Crimea partido."},
                             "fr": {nr: "Pictures show the Crimea bridge broken apart after Ukraine's strike on it."}},
                vertaalmaker="proef")
    conn = sqlite3.connect(m["bestand"])
    # een "vertaling" met dezelfde woorden als het origineel is er geen, zoals bij elke pagina
    assert conn.execute("SELECT taal, tekst FROM vertaling WHERE pagina = ?", (nr,)).fetchall() == [
        ("es", "Imágenes muestran el puente de Crimea partido.")]


def test_a_draft_overview_only_goes_into_a_preview(tmp_path):
    concept = _overzicht(sleutel="concept-overzicht", status="concept")
    m = _bouw(tmp_path / "a", [_overzicht(), concept])
    assert m["wereldlijst"] == {"gepubliceerd": 1, "concept": 0}
    m = _bouw(tmp_path / "b", [_overzicht(), concept], concepten=True)
    assert m["wereldlijst"] == {"gepubliceerd": 1, "concept": 1}


def test_an_overview_that_breaks_the_rules_stops_the_build(tmp_path):
    with pytest.raises(pb.Weigering, match="crimea-bridge-ai-visuals"):
        _bouw(tmp_path, [_overzicht(kern=["No source here."])])


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    m = _bouw(tmp_path_factory.mktemp("wereld"), [_overzicht()])
    client = TestClient(fa.maak_app(m["bestand"]), follow_redirects=False)
    client.bestand = m["bestand"]
    return client


def test_the_fact_check_page_shows_what_the_fact_checkers_found_with_the_newsroom_behind_each_sentence(site):
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    g = site.get(f"/api/en/factcheck/{nr}").json()
    s = g["samenvatting"]
    assert s["kop"] == i18n.tekst("en", "samenvatting_kop") and s["taal"] == "en" and s["engels"] == ""
    assert s["vond"][0] == {"zin": "Ukraine did strike the bridge, but the pictures do not show that damage.",
                            "bronnen": [{"naam": "AFP", "anker": "check-0"}, {"naam": "dpa", "anker": "check-1"}]}
    assert s["rondgang"][0]["bronnen"][1] == {"naam": "dpa", "anker": "check-1"}
    assert [k["redactie"] for k in g["checks"]] == ["AFP", "dpa"]          # dezelfde volgorde als de ankers
    nl = site.get(f"/api/nl/factcheck/{nr}").json()["samenvatting"]
    assert nl["kop"] == i18n.tekst("nl", "samenvatting_kop") and nl["engels"] == i18n.tekst("nl", "samenvatting_engels")
    # een gewone pagina uit het archief heeft geen samenvatting
    gewoon = pb.nummer("gfc-" + f"{1:016x}")
    assert site.get(f"/api/en/factcheck/{gewoon}").json()["samenvatting"] is None


def test_typescript_answers_the_same_for_an_overview_in_every_language(site):
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    adressen = [f"/api/{taal}/factcheck/{nr}" for taal in i18n.TALEN] + ["/api/en/archief", "/api/nl/redacties"]
    assert gelijk.verschillen(site, site.bestand, adressen) == []


def test_every_published_overview_in_the_repository_keeps_the_rules():
    from doublecheck import toelating

    alle = wl.lees_alle()
    assert alle, "geen wereldlijst in content/wereldlijst/"
    register = toelating.register()
    for o in alle:
        assert wl.controleer(o, register) == [], o["sleutel"]
    assert len({o["sleutel"] for o in alle}) == len(alle)
