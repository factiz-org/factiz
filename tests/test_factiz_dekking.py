"""Wat erin zit en wat nog niet (PLAN #34.2az, SPECS E9.S25): op de pagina met redacties en bij een zoekvraag zonder
resultaat zegt de site hoeveel factchecks er zijn, van hoeveel redacties, wie de meeste leverde, en welke grote redacties
nog bijna ontbreken en waarom. Uit de uitgave geteld, in vijf talen."""

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import i18n
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("dekking")
    lab = _lab(map_)
    for i in range(3):
        _check(lab, _claim(lab, 1 + i, f"Snopes checked claim number {i} about a bridge"), f"https://snopes.com/s{i}")
    for i in range(2):
        _check(lab, _claim(lab, 10 + i, f"Maldita checked claim number {i} about a river"), f"https://maldita.es/m{i}")
    _check(lab, _claim(lab, 20, "AFP checked a claim about a mountain"), "https://factcheck.afp.com/a")
    lab.commit()
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-15")
    return TestClient(fa.maak_app(m["bestand"]))


def test_the_newsrooms_page_says_how_many_from_whom_and_who_is_still_missing(client):
    g = client.get("/api/nl/redacties").json()
    assert g["dekking"][0] == "Factiz bevat nu 6 factchecks van 3 redacties, de meeste van Snopes, Maldita en AFP."
    assert g["dekking"][1].startswith("Van grote redacties als AFP, Reuters, Snopes, Correctiv en Full Fact staan er nog")


def test_a_big_newsroom_with_enough_fact_checks_drops_out_and_without_any_missing_the_sentence_goes(client, monkeypatch):
    monkeypatch.setattr(fa, "BIJNA_GEEN", 3)                # Snopes heeft er 3, AFP 1
    zin = client.get("/api/nl/redacties").json()["dekking"]
    assert "Snopes" not in zin[1] and "AFP" in zin[1]
    monkeypatch.setattr(fa, "BIJNA_GEEN", 0)
    assert len(client.get("/api/nl/redacties").json()["dekking"]) == 1


def test_a_search_without_result_explains_what_is_in_and_a_search_with_results_does_not(client):
    leeg = client.post("/api/nl/zoek", data={"q": "volkomen onbekend woordxyz"}).json()
    assert leeg["totaal"] == 0 and len(leeg["dekking"]) == 2 and "Snopes" in leeg["dekking"][0]
    vol = client.post("/api/nl/zoek", data={"q": "bridge"}).json()
    assert vol["totaal"] > 0 and vol["dekking"] == []


@pytest.mark.parametrize("taal", TALEN)
def test_every_language_has_both_sentences_in_plain_words(client, taal):
    zin = client.get(f"/api/{taal}/redacties").json()["dekking"]
    assert len(zin) == 2 and all(z.endswith(".") for z in zin)
    for z in zin:
        assert "—" not in z and "!" not in z and "{" not in z, z
    assert i18n.getal(taal, 6) in zin[0] and "Snopes" in zin[0] and "Reuters" in zin[1]


def test_the_site_shows_the_sentences_on_the_newsrooms_page_and_under_an_empty_search():
    from pathlib import Path
    site = Path(__file__).resolve().parent.parent / "site" / "src" / "components" / "site"
    redacties = (site / "paginas" / "Redacties.astro").read_text(encoding="utf-8")
    assert "{g.dekking.join(' ')}" in redacties
    bieb = (site / "Bibliotheek.jsx").read_text(encoding="utf-8")
    leeg = bieb[bieb.index("rijen.length === 0 &&"):]
    assert leeg.index("tekst.zoek_niets_klopt") < leeg.index("gegevens.dekking.join(' ')") < leeg.index("tekst.zoek_tip")
