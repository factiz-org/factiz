"""Betrouwbare bronnen (PLAN #32.3b): een soort per website met de herkomst, en de
meting die vooraf vastlag. Geen download: kleine stukjes in de vorm van de echte
bestanden."""

import pytest

from doublecheck import bronnenlijst as bl

LIN = ("domain,pc1\nreuters.com,1\ncnn.com,0.81\nmiddel.com,0.55\nnepnieuws.net,0.12\nnih.gov,0.9\n"
       "facebook.com/iemand,0.25\nnewyorker.com/humor,0.27\n")
WIKI = """{| class="wikitable"
|- class="s-gr" id="Reuters"
| [[Reuters]]
| {{WP:RSPSTATUS|gr}}
| {{WP:RSPUSES|reuters.com}}
|- class="s-gu" id="Fox News (politics)"
| Fox News (politics)
| {{WP:RSPSTATUS|gu}}
| {{WP:RSPUSES|foxnews.com}}
|- class="s-nc" id="Fox News (general)"
| Fox News
| {{WP:RSPSTATUS|nc}}
| {{WP:RSPUSES|foxnews.com}}
|- class="s-gu" id="Forbes contributors"
| Forbes contributors
| {{WP:RSPSTATUS|gu}}
| {{WP:RSPUSES|forbes.com/sites}}
|- class="s-gr" id="Gemengd"
| Gemengd
| {{WP:RSPSTATUS|gr}} {{WP:RSPSTATUS|nc}}
| {{WP:RSPUSES|gemengd.org}}
|- class="s-d" id="Afgeschreven"
| Afgeschreven
| {{WP:RSPSTATUS|d}}
| {{WP:RSPUSES|afgeschreven.com|ook-afgeschreven.com}}
|}"""
RSF = "ISO;Score 2026;Rank\r\nNLD;88,92;4\r\nUSA;62,61;64\r\nGBR;79,45;20\r\n"


def _lijst(**extra):
    return bl.bouw(lin=LIN, wikipedia=[WIKI], ifcn=["https://www.factcheck.org/"],
                   ebu=[("nos.nl", "NLD"), ("pbs-voorbeeld.org", "USA"), ("bbc.com", "GBR")],
                   rsf=bl.rsf_scores(RSF), datum="2026-10-28", **extra)


def test_a_site_is_found_on_the_longest_part_of_its_name():
    sites = _lijst()["sites"]
    assert bl.soort("https://edition.cnn.com/2026/x", sites) == "A"
    assert bl.soort("http://WWW.Reuters.com:443/a", sites) == "A"
    assert bl.soort("https://en.wikipedia.org/wiki/X", sites) == "U"
    assert bl.soort("https://onbekend-blog.example/x", sites) == "B"
    assert bl.host("https://www.bbc.com/news") == "bbc.com" and bl.host("") == ""


def test_lin_gives_a_from_0_70_and_c_up_to_0_40_and_nothing_in_between():
    sites = _lijst()["sites"]
    assert bl.soort("https://middel.com", sites) == "B"
    assert bl.soort("https://nepnieuws.net", sites) == "C"
    assert bl.soort("https://www.facebook.com/x", sites) == "U" and bl.soort("https://newyorker.com", sites) == "B"
    streng = bl.bouw(lin=LIN, wikipedia=[], ifcn=[], ebu=[], rsf={}, datum="2026-10-28", lin_a=0.85)["sites"]
    assert bl.soort("https://cnn.com", streng) == "B" and bl.soort("https://reuters.com", streng) == "A"


def test_wikipedia_is_a_only_when_every_status_is_generally_reliable_and_strictest_wins():
    sites = _lijst()["sites"]
    assert bl.soort("https://www.foxnews.com/politics", sites) == "C"  # ongeschikt én geen consensus
    assert bl.soort("https://gemengd.org", sites) == "B"  # betrouwbaar én geen consensus is geen A
    assert bl.soort("https://ook-afgeschreven.com", sites) == "C"
    assert bl.soort("https://forbes.com/sites/iemand", sites) == "B"  # een oordeel over een deel van een site telt niet


def test_official_domains_are_their_own_kind_and_beat_an_a():
    sites = _lijst()["sites"]
    assert bl.soort("https://pmc.ncbi.nlm.nih.gov/articles/1", sites) == "O"  # Lin zegt A, de overheid is strenger
    for url in ("https://pib.gov.in/x", "https://www.cdc.gov", "https://who.int", "https://mit.edu",
                "https://ox.ac.uk", "https://www.gob.mx", "https://www.interieur.gouv.fr", "https://x.overheid.nl"):
        assert bl.soort(url, sites) == "O", url
    assert bl.soort("https://nos.nl", sites) == "A" and bl.soort("https://news.gov.example.com", sites) == "B"


def test_a_public_broadcaster_counts_only_from_a_country_with_a_free_press():
    sites = _lijst()["sites"]
    assert bl.soort("https://nos.nl/artikel/1", sites) == "A"
    assert bl.soort("https://www.bbc.com/news", sites) == "A"
    assert bl.soort("https://pbs-voorbeeld.org", sites) == "B"  # RSF 62,6: onder de 70


def test_every_kind_carries_where_it_came_from():
    lijst = _lijst()
    assert ["A", "IFCN"] in lijst["sites"]["factcheck.org"]
    assert ["A", "Lin e.a. 0.81"] in lijst["sites"]["cnn.com"]
    assert ["U", "vaste lijst"] in lijst["sites"]["wikipedia.org"]
    assert lijst["_meta"]["datum"] == "2026-10-28" and lijst["_meta"]["grenzen"]["lin_a"] == 0.70


def test_per_answer_the_best_kind_counts():
    sites = _lijst()["sites"]
    assert bl.beste(["https://onbekend.example", "https://cnn.com/x"], sites) == "A"
    assert bl.beste(["https://x.com/a", "https://nepnieuws.net"], sites) == "U"
    assert bl.beste(["https://cdc.gov", "https://blog.example"], sites) == "O"
    assert bl.beste([], sites) is None


def test_the_count_refuses_a_list_that_was_changed_after_it_was_fixed():
    lijst = _lijst()
    assert bl.vastgelegd(lijst)
    lijst["sites"]["nepnieuws.net"] = [["A", "met de hand"]]
    assert not bl.vastgelegd(lijst)
    with pytest.raises(bl.Weigering):
        bl.telling([], [], lijst)


def _rijen(soort, oordeel, waar, onwaar, dekking=True):
    return [{"oordeel": oordeel, "soort": soort, "label": "waar", "dekking": dekking}] * waar + \
        [{"oordeel": oordeel, "soort": soort, "label": "onwaar", "dekking": dekking}] * onwaar


def test_the_three_requirements_are_coverage_a_real_difference_and_thirty_greens_with_an_a():
    lijst = _lijst()
    ontwikkel = _rijen("A", "klopt", 40, 2) + _rijen("B", "klopt", 30, 10)
    toets = _rijen("A", "klopt", 80, 1) + _rijen("U", "klopt", 30, 15, dekking=False) + _rijen("C", "klopt niet", 1, 20)
    t = bl.telling(ontwikkel, toets, lijst)
    assert t["eisen"] == {"dekking minstens de helft": True, "minder onwaar bij groen met een A-bron": True,
                          "minstens 30 keer groen met een A-bron": True}
    assert t["toets"]["klopt"]["A"]["n"] == 81 and t["toets"]["klopt"]["A"]["waar"] == 80
    assert t["vraag"]["toets"]["p"] < 0.05 and t["vraag"]["ontwikkel"]["richting"] is True
    assert t["toets"]["klopt"]["A"]["stand"] == 7 and t["toets"]["klopt"]["A"]["stand zonder grens"] == 9

    weinig = bl.telling(ontwikkel, _rijen("A", "klopt", 20, 0) + _rijen("B", "klopt", 15, 5, dekking=False), lijst)
    assert weinig["eisen"]["minstens 30 keer groen met een A-bron"] is False
    assert weinig["eisen"]["dekking minstens de helft"] is True  # precies de helft telt


def test_the_difference_must_point_the_same_way_in_the_development_set():
    lijst = _lijst()
    toets = _rijen("A", "klopt", 60, 2) + _rijen("B", "klopt", 30, 15)
    omgekeerd = _rijen("A", "klopt", 30, 10) + _rijen("B", "klopt", 40, 2)
    assert bl.telling(omgekeerd, toets, lijst)["eisen"]["minder onwaar bij groen met een A-bron"] is False
