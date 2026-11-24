"""De voormeting voor kruiscontrole per detail (PLAN #32.3d): onafhankelijke goede
bronnen, en of de getallen uit het bericht in de geciteerde passages staan. De
regels die vóór de meting vastlagen."""

from doublecheck import kruiscontrole as kc

SITES = {"bbc.com": [["goed", "x"]], "bbc.co.uk": [["goed", "x"]], "reuters.com": [["goed", "x"]],
         "apnews.com": [["goed", "x"]], "dailymail.co.uk": [["laag", "x"]], "wikipedia.org": [["goed", "x"]]}


def _bron(url, citaat):
    return {"soort": "web", "url": url, "citaat": citaat, "titel": ""}


def test_the_owner_is_the_name_without_its_suffix():
    assert kc.eigenaar("bbc.com") == kc.eigenaar("bbc.co.uk") == "bbc"
    assert kc.eigenaar("edition.cnn.com") == "cnn" and kc.eigenaar("pib.gov.in") == "pib"
    assert kc.eigenaar("pmc.ncbi.nlm.nih.gov") == "nih" and kc.eigenaar("localhost") == "localhost"


def test_one_owner_one_wire_story_and_one_wikipedia_count_once():
    bronnen = [_bron("https://www.bbc.com/a", "The minister resigned on Tuesday after the vote."),
               _bron("https://www.bbc.co.uk/b", "A second passage from the same broadcaster."),
               _bron("https://www.reuters.com/x", "Officials said the bridge will reopen in May after repairs."),
               _bron("https://apnews.com/y", "Officials said the bridge will reopen in May after the repairs."),
               _bron("https://en.wikipedia.org/wiki/X", "Wikipedia passage about something else entirely here."),
               _bron("https://www.wikiwand.com/en/X", "A copy of the same article on another site.")]
    groepen = kc.groepen(bronnen, SITES)
    assert sum(g["goed"] for g in groepen) == 3  # bbc, het persbureaubericht, wikipedia


def test_a_low_band_a_platform_or_an_unknown_site_is_never_a_good_source():
    bronnen = [_bron("https://www.dailymail.co.uk/a", "x y z"), _bron("https://www.youtube.com/watch", "a b c"),
               _bron("https://blog.example/post", "d e f")]
    groepen = kc.groepen(bronnen, SITES)
    assert len(groepen) == 3 and not any(g["goed"] for g in groepen)


def test_a_number_is_found_or_contradicted_by_the_same_word_in_a_good_passage():
    uit = kc.getallen("Four people were detained on 12 March and fined 300 euros.",
                      ["Police detained four people on 21 March.", "Each was fined 300 euros."])
    assert uit["in bericht"] == {"12", "300"} and uit["gevonden"] == {"300"}
    assert uit["tegengesproken"] == {"12"}
    assert kc.getallen("In 2024 the vote passed.", ["In 2023 the budget fell."])["tegengesproken"] == set()  # "the"


def _rij(label, groepen, bericht="Het gebeurde op 12 maart.", ronde="r", deel=""):
    return {"label": label, "tekst": bericht, "ronde": ronde, "deel": deel, "groepen": groepen}


def _g(goed, *passages):
    return {"goed": goed, "passages": list(passages)}


def test_the_five_rules_on_one_green():
    twee_goed_met_getal = [_g(True, "Op 12 maart gebeurde het."), _g(True, "Iets anders.")]
    r = kc.regels(_rij("waar", twee_goed_met_getal))
    assert r == {"R-a": True, "R-b": True, "R-c": True, "R-d": True, "R-e": False}
    r = kc.regels(_rij("waar", [_g(True, "Op 12 maart gebeurde het."), _g(False, "Ook 12 maart, elders.")]))
    assert r["R-a"] is False and r["R-e"] is True
    r = kc.regels(_rij("onwaar", [_g(True, "Het gebeurde op 21 maart.")]))
    assert r["R-b"] is False and r["R-c"] is False
    zonder_getal = kc.regels(_rij("waar", [_g(False, "x")], bericht="De minister trad af."))
    assert zonder_getal["R-b"] and zonder_getal["R-e"] and not zonder_getal["R-a"]


def test_a_rule_is_promising_with_half_the_wrong_greens_stopped_and_at_most_a_fifth_of_the_right_ones_lost():
    goed = [_g(True, "Op 12 maart."), _g(True, "Op 12 maart, ook.")]
    fout = [_g(True, "Op 21 maart."), _g(True, "Elders.")]
    ontwikkel = [_rij("waar", goed)] * 8 + [_rij("waar", fout)] + [_rij("onwaar", fout)] * 2
    toets = [_rij("waar", goed)] * 9 + [_rij("waar", fout)] + [_rij("onwaar", fout)] * 3 + [_rij("onwaar", goed)]
    t = kc.telling(ontwikkel, toets)
    rc = t["regels"]["R-c"]
    assert rc["samen"] == {"onterecht groen": 6, "tegengehouden": 5, "juist groen": 19, "kleur kwijt": 2}
    assert rc["veelbelovend"] is True
    assert t["regels"]["R-a"]["samen"]["tegengehouden"] == 0 and t["regels"]["R-a"]["veelbelovend"] is False
