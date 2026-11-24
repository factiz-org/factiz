"""Voorlopige vertalingen (B93; PO 2026-11-23: "de vertalingen alvast live zetten, met 1 banner erboven"): de Haiku-
vertalingen die hun leesproef niet haalden, op de site met de banner *Machinevertaling, wacht op een nieuwe vertaling*, tot
de ronde van 3 december; nooit voor zoekmachines, nooit een vertaling die ik fout las."""

import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from doublecheck import weergave as wg
from factiz_site import app as fa
from factiz_site import gelijk, i18n
from tests.test_publiceren import REGISTER, _check, _claim, _lab


def _a(nummer, taal, tekst, versie, model="haiku", bron="en"):
    return {"nummer": nummer, "bron": bron, "vertalingen": {taal: tekst}, "versie": versie, "model": model, "ronde": 10}


def test_only_translations_kept_out_by_their_reading_test_become_provisional():
    pt_m, nl_m = wg.METHODE["pt"].split("/")[0], wg.METHODE["nl"].split("/")[0]
    antwoorden = [_a("a", "pt", "Uma vacina altera o DNA.", pt_m), _a("b", "pt", "Texto lido como errado.", pt_m),
                  _a("c", "pt", "Fora da varredura.", pt_m), _a("d", "nl", "Een vaccin verandert het DNA.", nl_m),
                  _a("e", "pt", "Método antigo.", "weergave-v2"),               # niet de methode van het Portugees nu
                  _a("f", "pt", "Een vertaling in het Portugees.", pt_m, bron="pt")]   # de taal van de bewering zelf
    geldig = {"nl": {"d": "Een vaccin verandert het DNA."}}                      # haalde haar leesproef: geen voorlopige
    originelen = {k: "A vaccine changes DNA." for k in "abcdef"}
    uit = wg.voorlopige_vertalingen(antwoorden, geldig, frozenset({("pt", "b")}), originelen, houden={"a", "b", "d", "e", "f"})
    assert uit == {"pt": {"a": "Uma vacina altera o DNA."}}


def _bouw(map_):
    map_.mkdir(parents=True, exist_ok=True)
    lab = _lab(map_)
    a = _claim(lab, 1, "A vaccine changes your DNA.")
    _check(lab, a, "https://snopes.com/dna", datum="2025-01-01")
    lab.commit()
    nr = pb.nummer(a)
    return pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-23",
                   vertalingen={"es": {nr: "Una vacuna cambia tu ADN."}}, vertaalmaker="weergave",
                   voorlopig={"pt": {nr: "Uma vacina altera o seu DNA."}, "es": {nr: "Niet over een geldige heen."}},
                   voorlopig_maker={"pt": "claude-haiku-5-5, weergave-v6"}), nr


def test_the_edition_marks_a_provisional_translation_and_never_puts_it_over_a_valid_one(tmp_path):
    m, nr = _bouw(tmp_path)
    conn = sqlite3.connect(m["bestand"])
    assert conn.execute("SELECT taal, tekst, maker, voorlopig FROM vertaling WHERE pagina = ? ORDER BY taal", (nr,)).fetchall() == [
        ("es", "Una vacuna cambia tu ADN.", "weergave", 0), ("pt", "Uma vacina altera o seu DNA.", "claude-haiku-5-5, weergave-v6", 1)]
    assert m["voorlopig"] == {"pt": 1}
    assert pb.controleer(m["bestand"])["paginas"] == 1
    # zoeken op de site vindt ook de voorlopige vertaling (#37.16): de woordenlijst staat in de uitgave, niet in de Worker
    zoek = lambda woord: conn.execute("SELECT count(*) FROM zoek WHERE zoek MATCH ?", (woord,)).fetchone()[0]
    assert zoek("vacuna") == 1 and zoek("vacina") == 1


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    m, nr = _bouw(tmp_path_factory.mktemp("voorlopig"))
    client = TestClient(fa.maak_app(m["bestand"]), follow_redirects=False)
    client.bestand, client.nr = m["bestand"], nr
    return client


def test_the_page_shows_the_banner_above_a_provisional_translation_and_keeps_it_from_search_engines(site):
    pt = site.get(f"/api/pt/factcheck/{site.nr}").json()
    assert pt["vertaling"]["tekst"] == "Uma vacina altera o seu DNA."
    assert pt["voorlopig"] == i18n.tekst("pt", "vertaling_voorlopig")
    assert "pt" not in pt["vindbaar"]["talen"] and pt["vindbaar"]["index"] is False
    es = site.get(f"/api/es/factcheck/{site.nr}").json()
    assert es["voorlopig"] == "" and "es" in es["vindbaar"]["talen"]
    # de sitemap van het Portugees noemt de pagina niet, die van het Spaans wel (stand 3: elke vindbare taal)
    assert site.get("/api/pt/sitemap?stand=3").json()["totaal"] == 0
    assert site.nr in str(site.get("/api/es/sitemap?stand=3&deel=0").json())


def test_typescript_answers_the_same_for_a_provisional_translation(site):
    adressen = [f"/api/{taal}/factcheck/{site.nr}" for taal in i18n.TALEN] + ["/api/pt/sitemap?stand=3", "/api/pt/sitemap?stand=2",
                                                                               "/api/es/sitemap?stand=3&deel=0"]
    assert gelijk.verschillen(site, site.bestand, adressen) == []
