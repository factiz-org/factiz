"""Wat de factchecks ons leren (PLAN #32.39): de vorm van het bericht, de truc en hoe de factchecker het ontdekte,
uit een gespreide steekproef van artikelen, met een methode alleen bij een letterlijk citaat."""

import json

import pytest

from doublecheck import werkwijze as ww


def _rij(i, taal="en", jaar=2024, uitgever="A", oordeel="onwaar"):
    return {"url": f"https://{uitgever.lower()}.org/{taal}/{i}", "publisher": uitgever, "language": taal,
            "jaar": jaar, "oordeel": oordeel, "claim": f"claim {i}"}


def test_the_sample_takes_only_false_or_misleading_checks_and_at_most_forty_per_outlet():
    rijen = [_rij(i, uitgever="A") for i in range(100)] + [_rij(i, uitgever="B", oordeel="waar") for i in range(100)]
    uit = ww.steekproef(rijen, dood=set(), per_taal={"en": 100}, rest=0, reserve=1.0)
    assert len(uit) == 40
    assert {r["publisher"] for r in uit} == {"A"}
    assert all(r["oordeel"] in ww.ONWAAR for r in uit)


def test_the_sample_skips_dead_links_and_counts_a_link_once():
    rijen = [_rij(1), _rij(1), _rij(2), _rij(3)]
    uit = ww.steekproef(rijen, dood={_rij(2)["url"]}, per_taal={"en": 10}, rest=0, reserve=1.0)
    assert sorted(r["url"] for r in uit) == [_rij(1)["url"], _rij(3)["url"]]


def test_half_of_each_language_comes_from_the_last_years():
    rijen = ([_rij(i, jaar=2019, uitgever=f"O{i % 9}") for i in range(200)]
             + [_rij(i, jaar=2025, uitgever=f"N{i % 9}") for i in range(200, 400)])
    uit = ww.steekproef(rijen, dood=set(), per_taal={"en": 20}, rest=0, reserve=1.0)
    assert sum(r["jaar"] >= ww.RECENT for r in uit) == 10
    assert sum(r["jaar"] < ww.RECENT for r in uit) == 10


def test_languages_outside_the_list_share_the_rest():
    rijen = [_rij(i, taal="fa", uitgever=f"F{i % 5}") for i in range(50)] + [_rij(i, taal="ar") for i in range(50)]
    uit = ww.steekproef(rijen, dood=set(), per_taal={"en": 0}, rest=10, reserve=1.0)
    assert len(uit) == 10
    assert {r["laag"][0] for r in uit} == {"rest"}


def test_the_sample_is_the_same_every_time():
    rijen = [_rij(i, uitgever=f"U{i % 7}") for i in range(300)]
    a = ww.steekproef(rijen, dood=set(), per_taal={"en": 30}, rest=0)
    b = ww.steekproef(list(reversed(rijen)), dood=set(), per_taal={"en": 30}, rest=0)
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_per_layer_the_first_readable_articles_are_asked_never_more_than_the_quota():
    rijen = [{"id": f"x{i}", "laag": ["en", "recent"], "quotum": 2} for i in range(5)]
    assert [r["id"] for r in ww.kies_leesbaar(rijen, leesbaar={"x0", "x2", "x3", "x4"})] == ["x0", "x2"]


def test_m4fc_strategies_become_our_methods():
    assert ww.m4fc_methoden("reverse image search; keyword search") == {"reverse image search", "keyword search"}
    assert ww.m4fc_methoden("profiling; other") == {"the account behind the post"}
    assert ww.m4fc_methoden("not enough information") == set()


ARTIKEL = ("The video was first posted in 2019 in Brazil. Using a reverse image search we found the original clip "
           "on YouTube. Euronews told us it never published this report.")


def _antwoord(**over):
    d = {"fact_check": True, "vorm": "video", "truc": "imposter", "nagedaan": "news outlet", "wie": "Euronews",
         "verhaal": "A fake Euronews video about secret prisons.", "onderwerp": "war and conflict",
         "methoden": [{"methode": "reverse image search", "citaat": "Using a reverse image search we found the original"},
                      {"methode": "checked with the source", "citaat": "Euronews told us it never published"},
                      {"methode": "geolocation", "citaat": "we located the street with satellite images"}]}
    d.update(over)
    return json.dumps(d)


def test_a_method_counts_only_with_a_quote_that_is_literally_in_the_article():
    uit = ww.lees_antwoord(_antwoord(), ARTIKEL)
    assert uit["methoden"] == ["omgekeerd zoeken op het beeld", "bij de bron zelf nagegaan"]
    assert uit["niet gevonden"] == ["de plek bepaald"]
    assert uit["vorm"] == "video" and uit["truc"] == "nagemaakt" and uit["nagedaan"] == "medium"


def test_a_quote_counts_whatever_the_case_and_spacing_but_not_when_too_short():
    lang = {"methode": "reverse image search", "citaat": "using a  REVERSE image search"}
    kort = {"methode": "checked with the source", "citaat": "Euronews"}
    uit = ww.lees_antwoord(_antwoord(methoden=[lang, kort]), ARTIKEL)
    assert uit["methoden"] == ["omgekeerd zoeken op het beeld"]
    assert uit["niet gevonden"] == ["bij de bron zelf nagegaan"]


@pytest.mark.parametrize("tekst", [None, "", "{niet json", json.dumps({"vorm": "video"}),
                                   _antwoord(truc="verzonnen door mij"), _antwoord(methoden="geen lijst")])
def test_an_unreadable_or_invalid_answer_never_counts(tekst):
    assert ww.lees_antwoord(tekst, ARTIKEL) == {"leesbaar": False}


def test_a_page_that_is_no_fact_check_is_kept_apart():
    uit = ww.lees_antwoord(_antwoord(fact_check=False), ARTIKEL)
    assert uit["leesbaar"] and not uit["factcheck"]


def test_submitting_is_refused_above_the_cap():
    ww.binnen_grens(0.30, 0.60)
    with pytest.raises(ww.Weigering):
        ww.binnen_grens(0.50, 0.60)


def _gelezen(n):
    return [{"id": f"a{i}", "leesbaar": True, "factcheck": True, "vorm": "video", "truc": "nagemaakt",
             "methoden": ["omgekeerd zoeken op het beeld"], "laag": ["en", "recent"]} for i in range(n)]


def test_counting_is_refused_while_a_checked_article_has_no_label():
    gelezen = _gelezen(5)
    labels = {f"a{i}": {"vorm": "goed", "truc": "goed", "methode": "goed"} for i in range(4)}
    with pytest.raises(ww.Weigering):
        ww.telling_nakijken(gelezen, labels, nakijken=[r["id"] for r in gelezen])


def test_the_bar_is_ninety_of_a_hundred_per_field():
    gelezen = _gelezen(100)
    labels = {r["id"]: {"vorm": "goed", "truc": "goed", "methode": "goed"} for r in gelezen}
    for i in range(10):
        labels[f"a{i}"]["truc"] = "fout"
    for i in range(11):
        labels[f"a{i}"]["methode"] = "fout"
    uit = ww.telling_nakijken(gelezen, labels, nakijken=[r["id"] for r in gelezen])
    assert uit["vorm"] == {"goed": 100, "van": 100, "gehaald": True}
    assert uit["truc"]["gehaald"] is True
    assert uit["methode"] == {"goed": 89, "van": 100, "gehaald": False}


def test_m4fc_agreement_counts_per_strategy_what_haiku_also_names():
    gelezen = [{"id": "m1", "leesbaar": True, "factcheck": True, "methoden": ["omgekeerd zoeken op het beeld"],
                "m4fc": "reverse image search; keyword search"},
               {"id": "m2", "leesbaar": True, "factcheck": True, "methoden": [], "m4fc": "keyword search"}]
    uit = ww.m4fc_overeenkomst(gelezen)
    assert uit["omgekeerd zoeken op het beeld"] == {"mensen": 1, "haiku ook": 1}
    assert uit["zoeken op woorden"] == {"mensen": 2, "haiku ook": 0}


def test_the_map_counts_form_trick_and_method_per_layer():
    gelezen = _gelezen(3) + [{"id": "z", "leesbaar": True, "factcheck": False}]
    kaart = ww.kaart(gelezen)
    assert kaart["artikelen"] == 3
    assert kaart["truc"]["nagemaakt"] == 3
    assert kaart["methode"]["omgekeerd zoeken op het beeld"] == 3
    assert kaart["per laag"]["en/recent"]["truc"]["nagemaakt"] == 3
