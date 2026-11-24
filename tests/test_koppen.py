"""De koppen van de dichte sites, een voormeting (PLAN #32.3f)."""

import pytest

from doublecheck import koppen as k

SITES = {"rferl.org": [["goed", "Lin e.a. 0.80"]], "news.yahoo.com": [["goed", "Lin e.a. 0.70"]],
         "cnn.com": [["goed", "Lin e.a. 0.75"]], "infowars.com": [["laag", "Lin e.a. 0.10"]]}
KOP = "Poisoned opposition leader held after flying home"


def test_a_title_counts_only_when_it_holds_four_fifths_of_the_headline_words():
    assert k.lijkt_op(KOP, "Russia Navalny: Poisoned opposition leader held after flying home - BBC News")
    assert k.lijkt_op(KOP, "poisoned OPPOSITION leader held after flying back home")
    assert not k.lijkt_op(KOP, "Opposition leader flies home")
    assert not k.lijkt_op("", "anything")


def test_wikipedia_citations_are_read_with_their_link_and_title():
    wiki = ("Text.<ref>{{cite news |title=Poisoned opposition leader held after flying home |url=https://www.bbc.com/"
            "news/world-europe-55693721 |work=BBC News}}</ref> More.<ref>{{Cite web|url=https://www.dw.com/en/x/a-1|"
            "title=Other story}}</ref> And [https://www.theguardian.com/world/2021/jan/17/x A bare link title].")
    assert k.citaten(wiki) == [
        {"url": "https://www.bbc.com/news/world-europe-55693721", "titel": KOP},
        {"url": "https://www.dw.com/en/x/a-1", "titel": "Other story"},
        {"url": "https://www.theguardian.com/world/2021/jan/17/x", "titel": "A bare link title"}]


def test_a_wikipedia_find_needs_the_same_publisher_and_a_matching_title():
    cit = [{"url": "https://www.bbc.co.uk/news/world-europe-55693721", "titel": KOP},
           {"url": "https://www.rferl.org/a/navalny/1.html", "titel": KOP}]
    assert k.wiki_vondst(KOP, "bbc.com", cit)["url"].startswith("https://www.bbc.co.uk")
    assert k.wiki_vondst(KOP, "dw.com", cit) is None
    assert k.wiki_vondst("Navalny sentenced to nine years", "bbc.com", cit) is None


def _pagina(**kw):
    return {"url": "https://news.yahoo.com/x.html", "kop": KOP, "zelfde_verhaal": True, "overname": False,
            "bron": "", "verschillen": [], **kw}


def test_a_copy_counts_for_the_shown_site_only_when_it_names_that_site_as_source():
    assert k.overname_vondst(KOP, "theguardian.com", [_pagina(bron="The Guardian")], SITES)["bij site"]
    assert k.overname_vondst(KOP, "apnews.com", [_pagina(overname=True, bron="AP")], SITES)["bij site"]
    andere = k.overname_vondst(KOP, "theguardian.com", [_pagina(bron="rferl.org")], SITES)
    assert not andere["bij site"] and andere["andere site"] == "rferl.org"
    verzonnen = k.overname_vondst("Kremlin dissolves GRU after parliament vote", "theguardian.com",
                                  [_pagina(bron="theguardian.com")], SITES)
    assert not verzonnen["bij site"] and verzonnen["andere site"] is None


def test_good_outlets_carrying_the_story_are_counted_separately_per_newsroom():
    paginas = [_pagina(url="https://news.yahoo.com/a"), _pagina(url="https://edition.cnn.com/b"),
               _pagina(url="https://www.cnn.com/c"), _pagina(url="https://www.rferl.org/d"),
               _pagina(url="https://www.infowars.com/e"), _pagina(url="https://www.rferl.org/f", zelfde_verhaal=False)]
    assert k.overname_vondst(KOP, "bbc.com", paginas, SITES)["goede sites"] == 3


def test_the_answer_of_route_two_is_read_from_its_last_json_line():
    tekst = ('I found two pages.\n{"paginas": [{"url": "https://news.yahoo.com/x", "kop": "A", "zelfde_verhaal": true, '
             '"overname": true, "bron": "AP", "verschillen": [{"woorden": "Friday", "juist": "Wednesday"}]}, "rommel"]}')
    p = k.lees_overname([{"type": "text", "text": tekst}])
    assert p == [{"url": "https://news.yahoo.com/x", "kop": "A", "zelfde_verhaal": True, "overname": True, "bron": "AP",
                  "verschillen": [{"woorden": "Friday", "juist": "Wednesday"}]}]
    assert k.lees_overname([{"type": "text", "text": "geen JSON"}]) is None


def test_portal_links_and_gdelt_words_come_from_the_link_itself():
    wiki = "* Event. [https://www.bbc.com/news/articles/c4g7 (BBC News)] [https://apnews.com/article/gaza-ceasefire-talks-cairo-0a1b2c3d (AP)]"
    assert k.portal_links(wiki) == ["https://www.bbc.com/news/articles/c4g7",
                                    "https://apnews.com/article/gaza-ceasefire-talks-cairo-0a1b2c3d"]
    assert k.gdelt_woorden("https://apnews.com/article/gaza-ceasefire-talks-cairo-0a1b2c3d") == "gaza ceasefire talks cairo"
    assert k.gdelt_woorden("https://www.bbc.com/news/articles/c4g7") == ""
    assert k.zelfde_link("https://www.apnews.com/article/x?utm=1", "http://apnews.com/article/x/")
    assert not k.zelfde_link("https://apnews.com/article/x", "https://apnews.com/article/y")


def test_the_count_refuses_while_a_find_for_a_forgery_has_no_label():
    stukken = [{"id": "A:1", "sub": "A", "set": "toets"}, {"id": "B-kop:2", "sub": "B-kop", "set": "toets"}]
    vondsten = {"A:1": {"route 1": False, "route 2": True}, "B-kop:2": {"route 1": False, "route 2": True}}
    with pytest.raises(k.Weigering):
        k.telling(stukken, vondsten, {("A:1", "route 2"): "juist"}, {})
    with pytest.raises(k.Weigering):  # ook een vondst van route 2 bij een echt artikel wordt gelezen
        k.telling(stukken, vondsten, {("B-kop:2", "route 2"): "vals"}, {})
    uit = k.telling(stukken, vondsten, {("A:1", "route 2"): "juist", ("B-kop:2", "route 2"): "vals"}, {})
    assert uit["dekking"]["samen"] == {"n": 1, "gevonden": 1} and uit["valse vondst"]["route 2"] == 1
    assert uit["veelbelovend"] is False  # route 2 vindt alles, maar met een valse vondst
    schoon = k.telling(stukken, vondsten, {("A:1", "route 2"): "juist", ("B-kop:2", "route 2"): "set fout"}, {})
    assert schoon["valse vondst"]["route 2"] == 0 and schoon["veelbelovend"] is True
    fout = k.telling(stukken, vondsten, {("A:1", "route 2"): "fout", ("B-kop:2", "route 2"): "set fout"}, {})
    assert fout["dekking"]["route 2"] == {"n": 1, "gevonden": 0}
