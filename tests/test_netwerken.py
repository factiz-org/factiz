"""Patronen in herkomst: bekende netwerkdomeinen en hun klonen als signaal (PLAN #32.58, B62; PO 2026-11-07: "Ze quoten
mekaar, dan hoeven we het bericht niet eens door te lezen om toch al te weten dat het nep nieuws is")."""

from doublecheck import netwerken as nw

LIJST = {"achtervoegsels": {"news-pravda.com": {"netwerk": "Pravda", "bron": "CheckFirst"}},
         "domeinen": {"sputnik.by": {"netwerk": "EUvsDisinfo", "bron": "EUvsDisinfo", "gevallen": 326},
                      "abkhazia-news.com": {"netwerk": "Pravda", "bron": "CheckFirst"}},
         "kloon_extensies": ["ltd", "online", "foo"]}
BANDEN = {"spiegel.de": [["goed", "Lin"]], "lemonde.fr": [["goed", "Lin"]], "theguardian.com": [["goed", "Lin"]],
          "bbc.co.uk": [["goed", "EBU"]], "bbc.com": [["goed", "EBU"]], "nieuws.example": [["laag", "Lin"]]}


def test_a_host_is_read_from_a_url_or_a_bare_domain_without_www_or_path():
    assert nw.host_van("https://www.Spiegel.LTD/politik/a?b=1") == "spiegel.ltd"
    assert nw.host_van("france.news-pravda.com") == "france.news-pravda.com"
    assert nw.host_van("geen domein hier") is None


def test_domains_in_a_message_are_found_also_without_https():
    tekst = "Lees dit: https://france.news-pravda.com/x en ook sputnik.by/nieuws, of mail me op a@b.nl. Klaar."
    assert nw.hosts_in(tekst) == ["france.news-pravda.com", "sputnik.by"]


def test_a_known_network_domain_or_any_subdomain_of_a_network_suffix_is_recognised_with_its_source():
    assert nw.netwerk_van("japan.news-pravda.com", LIJST)["netwerk"] == "Pravda"
    assert nw.netwerk_van("news-pravda.com", LIJST)["netwerk"] == "Pravda"
    assert nw.netwerk_van("sputnik.by", LIJST)["gevallen"] == 326
    assert nw.netwerk_van("abkhazia-news.com", LIJST)["bron"] == "CheckFirst"
    assert nw.netwerk_van("bbc.com", LIJST) is None and nw.netwerk_van("notnews-pravda.com", LIJST) is None


def test_a_clone_takes_the_name_of_a_good_outlet_on_an_extension_the_network_used():
    assert nw.kloon_van("spiegel.ltd", BANDEN, LIJST) == "spiegel.de"
    assert nw.kloon_van("lemonde.online", BANDEN, LIJST) == "lemonde.fr"
    assert nw.kloon_van("spiegel.de", BANDEN, LIJST) is None          # het echte medium
    assert nw.kloon_van("bbc.co.uk", BANDEN, LIJST) is None           # een eigen domein met een band
    assert nw.kloon_van("spiegel.com", BANDEN, LIJST) is None         # geen extensie van het netwerk: niet zeker
    assert nw.kloon_van("nieuws.ltd", BANDEN, LIJST) is None          # lijkt op een site zonder band goed


def test_the_signals_name_what_was_found_and_where_and_never_judge():
    s = nw.signalen("Zie spiegel.ltd/artikel", ["https://japan.news-pravda.com/a", "https://www.bbc.com/b"], BANDEN, LIJST)
    assert {(x["soort"], x["host"]) for x in s} == {("kloon", "spiegel.ltd"), ("netwerk", "japan.news-pravda.com")}
    assert all(x["bron"] for x in s) and all("oordeel" not in x for x in s)
    assert nw.signalen("Gewoon nieuws op bbc.com", [], BANDEN, LIJST) == []
