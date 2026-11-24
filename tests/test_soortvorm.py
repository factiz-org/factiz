"""Soort en vorm, alleen waar het zeker is (PLAN #34.2ak, SPECS E9.S19): de nagelezen woorden van de redacties, de
vorm uit de Engelse tekst van de bewering, de tabel in de uitgave en de filters en kaarten op het platform."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from doublecheck import soortvorm as sv
from factiz_site import app as fa
from factiz_site import db
from tests.test_publiceren import _bouw, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")


def test_the_reviewed_list_names_only_known_kinds_and_leaves_out_what_is_not_a_kind():
    woorden = sv.lees_woorden()
    assert set(woorden.values()) <= set(sv.SOORTEN)
    assert woorden["Altered"] == "bewerkt" and woorden["Missing Context"] == "context" and woorden["Satire"] == "satire"
    # feiten misleidend gebracht is geen bewerkt beeld, en een redactie die twijfelt, zegt het niet (34.2ak-soortwoorden)
    assert "Manipulacja" not in woorden and "Netočno, Manipulacija činjenicama" not in woorden
    assert "False, likely AI-generated" not in woorden and "Newspaper didn't alter stories" not in woorden
    ruw = json.loads(sv.WOORDEN.read_text(encoding="utf-8"))
    assert ruw["versie"] == sv.VERSIE and ruw["toelichting"]


def test_a_kind_comes_only_from_a_reviewed_word_and_the_most_specific_one_wins():
    woorden = {"Altered": "bewerkt", "Missing context": "context", "AI generated": "ai", "Satire": "satire"}
    assert sv.soort_van(["False"], woorden) == ""
    assert sv.soort_van(["False", "Missing context"], woorden) == "context"
    assert sv.soort_van(["Missing context", "AI generated"], woorden) == "ai"
    assert sv.soort_van(["Satire", "Altered"], woorden) == "bewerkt"
    assert sv.soort_van(["  Missing   context "], woorden) == "context"          # witruimte telt niet
    assert sv.soort_van(["missing context but altered somewhere"], woorden) == ""  # nooit een deel van een zin
    assert sv.soort_van([], woorden) == "" and sv.soort_van([""], woorden) == ""


@pytest.mark.parametrize("tekst, vorm", [
    ("A video shows floods in Valencia", "video"), ("Viral clip of a protest", "video"), ("FOOTAGE of the attack", "video"),
    ("Photos of a police officer arresting a woman", "beeld"), ("This image shows Zelensky", "beeld"),
    ("Screenshot of a tweet by Musk", "beeld"), ("Images and videos of the earthquake", "video"),
    ("The minister said taxes will rise", ""), ("Videographer arrested in Paris", ""), ("photographer wins prize", ""),
    ("वीडियो में दिखाया गया", ""), ("", ""),
])
def test_the_form_comes_from_the_english_words_of_the_claim(tekst, vorm):
    assert sv.vorm_van(tekst) == vorm


# --- de uitgave en het platform --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def uitgave(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("soortvorm")
    lab = _lab(tmp)
    n = {"bewerkt": _claim(lab, 1, "Photo shows Zelensky in a casino"),
         "context": _claim(lab, 2, "A video shows floods in Valencia last week"),
         "gewoon": _claim(lab, 3, "The minister said taxes will rise"),
         "spaans": _claim(lab, 4, "Un vídeo muestra a Zelenski en un casino", taal="es")}
    _check(lab, n["bewerkt"], "https://snopes.com/1", eigen="Altered")
    _check(lab, n["context"], "https://snopes.com/2", eigen="Missing context")
    _check(lab, n["context"], "https://factcheck.afp.com/2", eigen="False")
    _check(lab, n["gewoon"], "https://snopes.com/3", eigen="False")
    _check(lab, n["spaans"], "https://maldita.es/4", eigen="Falso", taal="es")
    m = _bouw(lab, tmp, soortwoorden={"Altered": "bewerkt", "Missing context": "context"})
    return m, {k: pb.nummer(v) for k, v in n.items()}


def test_the_release_holds_a_kind_and_a_form_only_where_they_are_certain(uitgave):
    m, nr = uitgave
    pub = sqlite3.connect(m["bestand"])
    rijen = {p: (s, v) for p, s, v in pub.execute("SELECT pagina, soort, vorm FROM kenmerk")}
    assert rijen == {nr["bewerkt"]: ("bewerkt", "beeld"), nr["context"]: ("context", "video")}
    # een Spaanse bewering zonder Engelse versie krijgt geen vorm: de regel kent alleen de Engelse woorden
    assert nr["spaans"] not in rijen and nr["gewoon"] not in rijen
    assert m["schema"] == pb.SCHEMA_VERSIE and m["kenmerk"] == {"versie": sv.VERSIE, "soort": 2, "vorm": 2}
    pb.controleer(m["bestand"])


def test_a_release_without_the_reviewed_words_has_forms_but_no_kinds(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "Photo shows Zelensky in a casino"), "https://snopes.com/1", eigen="Altered")
    m = _bouw(lab, tmp_path)
    assert [tuple(r) for r in sqlite3.connect(m["bestand"]).execute("SELECT soort, vorm FROM kenmerk")] == [("", "beeld")]
    assert m["kenmerk"]["versie"] == ""


@pytest.fixture(scope="module")
def platform(uitgave):
    m, nr = uitgave
    return TestClient(fa.maak_app(m["bestand"]), follow_redirects=False), nr


def test_kind_and_form_are_filters_with_their_counts_and_say_what_they_count(platform):
    client, nr = platform
    g = client.get("/api/nl/archief").json()
    groepen = {gr["soort"]: gr for gr in g["filters"]["groepen"]}
    assert [(k["waarde"], k["naam"], k["aantal"]) for k in groepen["soort"]["boven"]] == [
        ("bewerkt", "Bewerkt of nagemaakt", "1"), ("context", "Zonder of uit zijn context", "1")]
    assert [(k["waarde"], k["naam"]) for k in groepen["vorm"]["boven"]] == [("video", "Video"), ("beeld", "Beeld")]
    assert groepen["soort"]["uitleg"] == "Alleen waar de redactie het zelf zegt." and groepen["vorm"]["uitleg"]
    assert groepen["oordeel"]["uitleg"] == ""
    lijst = client.get("/api/nl/archief?soort=bewerkt").json()
    assert lijst["totaal"] == 1 and lijst["rijen"][0]["nummer"] == nr["bewerkt"]
    assert client.get("/api/nl/archief?vorm=video&vorm=beeld").json()["totaal"] == 2
    assert client.get("/api/nl/archief?soort=context&vorm=beeld").json()["totaal"] == 0


def test_a_card_and_a_fact_check_page_name_the_kind_as_the_newsrooms_word_and_the_form(platform):
    client, nr = platform
    rijen = {r["nummer"]: r for r in client.get("/api/nl/archief").json()["rijen"]}
    assert [(k["wat"], k["waarde"], k["naam"], k["regel"]) for k in rijen[nr["bewerkt"]]["kenmerken"]] == [
        ("soort", "bewerkt", "Bewerkt of nagemaakt", "volgens de redactie"), ("vorm", "beeld", "Beeld", "")]
    assert rijen[nr["bewerkt"]]["kenmerken"][0]["href"] == "/nl/fact-checks/?soort=bewerkt"
    assert rijen[nr["gewoon"]]["kenmerken"] == []
    p = client.get(f"/api/en/factcheck/{nr['context']}").json()
    assert [(k["naam"], k["regel"]) for k in p["kenmerken"]] == [("Missing or out of context", "according to the newsroom"),
                                                                 ("Video", "")]


@pytest.mark.parametrize("adres", ["/api/nl/archief?soort=onbekend", "/api/nl/archief?vorm=audio",
                                   "/api/nl/archief?soort=satire"])
def test_a_kind_or_form_that_no_fact_check_has_does_not_exist(platform, adres):
    client, _ = platform
    assert client.get(adres).status_code == 404


def test_the_site_and_the_lab_know_the_same_kinds_and_forms():
    assert set(db.SOORTEN) == set(sv.SOORTEN) and set(db.VORMEN) == set(sv.VORMEN)
    for taal in TALEN:
        assert all(json.loads((fa.PAKKET / "teksten" / f"{taal}.json").read_text(encoding="utf-8"))["teksten"].get(f"soort_{s}")
                   for s in db.SOORTEN)
