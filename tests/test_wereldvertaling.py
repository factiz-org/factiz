"""De wereldlijst vertaald (PLAN #37.12 punt 5, SPECS E10.S6 AC9; PO 2026-11-23: "Ja, werk het uit"): elk gepubliceerd
overzicht in alle talen van de site, zoals de eigen checks, binnen één grens van $5 per week samen met die checks."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import eigenvertaling as ev
from doublecheck import publiceren as pb
from doublecheck import wereldvertaling as wv
from factiz_site import app as fa
from factiz_site import gelijk, i18n
from tests.test_publiceren import _check, _claim, _lab
from tests.test_wereldlijst import REG, _overzicht


def _nl():
    return {"bewering": "Beelden tonen de Krimbrug in stukken na de Oekraïense aanval.",
            "kern": ["Oekraïne trof de brug, maar de beelden tonen die schade niet [1] [2].",
                     "Een detectiemiddel vond een AI-watermerk in één beeld [1]."],
            "rondgang": "De beelden gingen vanaf 18 november 2026 rond op Facebook en X [1] [2]."}


def test_an_overview_is_translated_in_every_other_language_of_the_site_and_only_when_published(tmp_path):
    o = _overzicht()
    assert wv.bron(o) == {"bewering": o["bewering"], "kern": o["kern"], "rondgang": o["rondgang"]}
    assert wv.doeltalen(o) == [t for t in ev.TALEN if t != "en"] and len(wv.doeltalen(o)) == 14
    concept = _overzicht(sleutel="concept-overzicht", status="concept")
    te_doen = wv.nog_te_doen([o, concept], tmp_path)
    assert {s for s, _ in te_doen} == {o["sleutel"]} and len(te_doen) == 14
    wv.schrijf(wv.pad(o["sleutel"], "nl", tmp_path), wv.bestand(o, "nl", _nl(), "proef"))
    assert ("crimea-bridge-ai-visuals", "nl") not in wv.nog_te_doen([o], tmp_path)
    assert wv.geldige(o, tmp_path) == {"nl": {"velden": _nl(), "maker": "proef"}}
    # verandert het overzicht, dan geldt de vertaling niet meer
    anders = _overzicht(bewering="Pictures show the Crimea bridge broken in two.")
    assert wv.geldige(anders, tmp_path) == {}


def test_an_answer_counts_only_with_the_same_fields_lists_and_source_numbers():
    velden = wv.bron(_overzicht())
    assert ev.lees_antwoord(json.dumps(_nl()), velden) == _nl()
    zonder_nummer = {**_nl(), "kern": [_nl()["kern"][0], "Een detectiemiddel vond een AI-watermerk in één beeld."]}
    assert ev.lees_antwoord(json.dumps(zonder_nummer), velden) is None
    assert ev.lees_antwoord(json.dumps({**_nl(), "kern": _nl()["kern"][:1]}), velden) is None


def test_the_overviews_and_the_own_checks_share_one_limit_of_five_dollars_a_week():
    dag = "2026-11-23"
    eigen = [{"dag": dag, "werkelijk": 2.33}]
    wereld = [{"dag": dag, "werkelijk": None, "schatting": 1.5}, {"dag": "2026-11-16", "werkelijk": 4.0}]
    assert wv.uitgegeven(dag, eigen, wereld) == pytest.approx(3.83)
    o = _overzicht()
    te_doen = [(o["sleutel"], t) for t in wv.doeltalen(o)]
    gekozen = wv.binnen_grens([o], te_doen, ruimte=0.0)
    assert gekozen == []
    assert wv.binnen_grens([o], te_doen, ruimte=100.0) == te_doen


def _bouw(map_, vertalingen):
    map_.mkdir(parents=True, exist_ok=True)
    lab = _lab(map_)
    _check(lab, _claim(lab, 1, "Garlic water cures covid"), "https://snopes.com/garlic", datum="2021-01-01")
    lab.commit()
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    return pb.bouw(lab, map_ / "uit", register=REG, vaag=frozenset(), datum="2026-11-23",
                   wereldlijst=[{**_overzicht(), "vertalingen": vertalingen}],
                   vertalingen={"nl": {nr: "Een slechtere vertaling van weergave."},
                                "es": {nr: "Imágenes muestran el puente de Crimea partido."}}, vertaalmaker="weergave")


def test_the_edition_takes_the_translation_of_the_overview_before_the_one_for_display(tmp_path):
    m = _bouw(tmp_path, {"nl": {"velden": _nl(), "maker": "claude-sonnet-5-5, wereldvertaling-v1"}})
    conn = sqlite3.connect(m["bestand"])
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    assert dict(conn.execute("SELECT taal, tekst FROM vertaling WHERE pagina = ?", (nr,))) == {
        "nl": _nl()["bewering"], "es": "Imágenes muestran el puente de Crimea partido."}
    rijen = conn.execute("SELECT taal, volg, soort, zin, bronnen FROM samenvatting WHERE pagina = ? AND taal = 'nl' "
                         "ORDER BY volg", (nr,)).fetchall()
    assert rijen[0] == ("nl", 0, "vond", "Oekraïne trof de brug, maar de beelden tonen die schade niet.",
                        json.dumps(["https://factcheck.afp.com/a", "https://dpa-factchecking.com/germany/b/"]))
    assert rijen[2][2] == "rondgang" and len(rijen) == 3
    assert conn.execute("SELECT count(*) FROM samenvatting WHERE pagina = ? AND taal = 'en'", (nr,)).fetchone()[0] == 3
    assert pb.controleer(m["bestand"])["paginas"] == 2


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    m = _bouw(tmp_path_factory.mktemp("wereldvertaald"), {"nl": {"velden": _nl(), "maker": "proef"}})
    client = TestClient(fa.maak_app(m["bestand"]), follow_redirects=False)
    client.bestand = m["bestand"]
    return client


def test_the_page_shows_the_translated_sentences_with_their_label_and_english_where_there_is_none(site):
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    nl = site.get(f"/api/nl/factcheck/{nr}").json()["samenvatting"]
    assert nl["taal"] == "nl" and nl["engels"] == ""
    assert nl["vertaald"] == i18n.tekst("nl", "eigen_vertaling", bron=i18n.taalnaam_in("nl", "en"))
    assert nl["vond"][0]["zin"] == "Oekraïne trof de brug, maar de beelden tonen die schade niet."
    assert [b["anker"] for b in nl["vond"][0]["bronnen"]] == ["check-0", "check-1"]
    de = site.get(f"/api/de/factcheck/{nr}").json()["samenvatting"]
    assert de["taal"] == "en" and de["engels"] == i18n.tekst("de", "samenvatting_engels") and de["vertaald"] == ""
    en = site.get(f"/api/en/factcheck/{nr}").json()["samenvatting"]
    assert en["taal"] == "en" and en["engels"] == "" and en["vertaald"] == ""


def test_typescript_answers_the_same_for_a_translated_overview_in_every_language(site):
    nr = pb.nummer("wereldlijst-crimea-bridge-ai-visuals")
    assert gelijk.verschillen(site, site.bestand, [f"/api/{taal}/factcheck/{nr}" for taal in i18n.TALEN]) == []
