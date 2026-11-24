"""Zoeken op een geplakt bericht (PLAN #34.2au, SPECS E9.S6 AC5): een doorgestuurde tekst zoekt op haar opvallendste
woorden, een gewoon woord telt niet, een treffer moet genoeg van die woorden hebben, en de site zegt eerlijk dat het om
gelijkenis in woorden gaat."""

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db
from tests.test_publiceren import REGISTER, _check, _claim, _lab

GATES = "Bill Gates admitted that vaccines contain a microchip to track people"
BERICHT = ("Forwarded as received. PLEASE READ AND SHARE. Bill Gates finally admitted that the new vaccines contain a "
           "microchip to track people everywhere. Share this before they delete it.")
GEWOON = "Hi everyone, dinner is at seven tonight, can someone pick up bread and a bottle of wine on the way"


@pytest.fixture(scope="module")
def pub_en_app(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("bericht")
    lab = _lab(map_)
    n = {"gates": _claim(lab, 1, GATES), "veilig": _claim(lab, 2, "The WHO says vaccines are safe for children"),
         "chip": _claim(lab, 3, "A microchip was found in a bottle of wine")}
    _check(lab, n["gates"], "https://snopes.com/gates")
    _check(lab, n["veilig"], "https://snopes.com/veilig")
    _check(lab, n["chip"], "https://snopes.com/chip")
    for i in range(60):       # gewone woorden: in meer dan 2% van de pagina's
        vulsel = _claim(lab, 100 + i, f"This is a claim about the moon that people share on the day number {i}")
        _check(lab, vulsel, f"https://snopes.com/maan-{i}")
    lab.commit()
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-15")
    nr = {k: pb.nummer(v) for k, v in n.items()}
    return db.Publicatie(m["bestand"]), TestClient(fa.maak_app(m["bestand"])), nr


def test_a_pasted_message_finds_the_fact_check_on_its_rare_words_and_counts_honestly(pub_en_app):
    pub, _, nr = pub_en_app
    uit = pub.zoek_ruim(BERICHT, 1, "en", bericht=True)
    assert uit["bericht"] and not uit["deels"] and uit["rijen"][0]["nummer"] == nr["gates"]
    assert 0 < uit["totaal"] <= 3                      # niet elke pagina met "the" of "this"
    assert {"microchip", "gates"} <= {t.casefold() for t in uit["termen"]}
    assert not {"the", "this", "people", "share"} & {t.casefold() for t in uit["termen"]}


def test_without_the_new_way_the_message_falls_back_on_every_word(pub_en_app):
    pub, _, _ = pub_en_app
    uit = pub.zoek_ruim(BERICHT, 1, "en")
    assert uit["deels"] and not uit.get("bericht") and uit["totaal"] > 50


def test_an_ordinary_message_gets_no_hit_and_at_most_ten_marked_as_weak(pub_en_app):
    """Zonder treffer de tien met de meeste van dezelfde woorden, gemarkeerd als geen treffer (`deels`, E9.S6 AC4); een
    bericht met minder dan twee opvallende woorden krijgt niets."""
    pub, _, _ = pub_en_app
    uit = pub.zoek_ruim(GEWOON, 1, "en", bericht=True)
    assert uit["bericht"] and uit["deels"] and uit["totaal"] <= db.BERICHT_ZWAK
    alleen_gewoon = "This is a claim about the moon that people share on the day, please share it with people"
    uit = pub.zoek_ruim(alleen_gewoon, 1, "en", bericht=True)
    assert uit["totaal"] == 0 and uit["rijen"] == []


def test_a_short_query_searches_as_before(pub_en_app):
    pub, _, nr = pub_en_app
    for vraag in ("microchip", "Gates microchip", "vaccines safe"):
        nieuw, oud = pub.zoek_ruim(vraag, 1, "en", bericht=True), pub.zoek_ruim(vraag, 1, "en")
        assert not nieuw.get("bericht") and [r["nummer"] for r in nieuw["rijen"]] == [r["nummer"] for r in oud["rijen"]]


def test_the_words_after_the_first_200_characters_still_count(pub_en_app):
    pub, _, nr = pub_en_app
    lang = "Forwarded as received. " * 12 + "Bill Gates admitted vaccines contain a microchip"
    assert len(lang) > 250
    uit = pub.zoek_ruim(lang, 1, "en", bericht=True)
    assert uit["rijen"] and uit["rijen"][0]["nummer"] == nr["gates"]


def test_never_more_than_the_maximum(pub_en_app, monkeypatch):
    pub, _, _ = pub_en_app
    monkeypatch.setattr(db, "BERICHT_MAX", 1)
    assert pub.zoek_ruim(BERICHT, 1, "en", bericht=True)["totaal"] <= 1


def test_the_search_answer_says_the_results_look_like_your_message(pub_en_app):
    _, client, nr = pub_en_app
    r = client.post("/api/nl/zoek", data={"q": BERICHT}).json()
    assert r["bericht"] is True and r["rijen"][0]["nummer"] == nr["gates"] and r["totaal"] <= 3
    assert r["bericht_kop"] == "1 factcheck lijkt op je bericht" and "microchip" in r["bericht_uitleg"].casefold()
    gewoon = client.post("/api/nl/zoek", data={"q": "microchip"}).json()
    assert gewoon["bericht"] is False
