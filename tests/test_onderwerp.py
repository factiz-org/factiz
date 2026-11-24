"""Wikipedia per onderwerp (PLAN #31.5, E8.S5): ware stukken over hetzelfde onderwerp als de onware."""

import json

from doublecheck import echtnieuws, onderwerp, zeef


def test_haiku_gives_a_language_and_at_most_four_search_words_without_quotes():
    tekst = json.dumps({"taal": "RU", "zoekwoorden": ["Буча", '"Киевская область"', " ", "2022", "война", "ещё"]})
    assert onderwerp.lees_antwoord(tekst) == ("ru", ["Буча", "Киевская область", "2022", "война"])


def test_an_unreadable_or_empty_answer_gives_nothing_to_search():
    assert onderwerp.lees_antwoord("{") is None
    assert onderwerp.lees_antwoord(json.dumps({"taal": "en", "zoekwoorden": []})) is None
    assert onderwerp.lees_antwoord(json.dumps({"taal": "", "zoekwoorden": ["Biden"]})) is None


def test_the_strict_query_needs_every_word_and_the_wide_one_any_phrase():
    streng, ruim = onderwerp.zoekvragen(["Hunter Biden", "Burisma"])
    assert streng == "Hunter Biden Burisma"
    assert ruim == '"Hunter Biden" OR Burisma'


def test_haiku_reads_the_claim_or_the_opening_of_an_article():
    assert onderwerp.invoer({"soort": "tekst", "tekst": "Kort."}) == "Kort."
    lang = "Kop\n" + "x" * 2_000
    assert onderwerp.invoer({"soort": "artikel", "tekst": lang}) == lang[:onderwerp.INVOER_TEKENS]


def _pagina(inleiding, pageid=42, taal="en"):
    return {"taal": taal, "pageid": pageid, "titel": "Bucha massacre", "url": "u", "inleiding": inleiding}


def test_a_page_gives_true_sentences_and_its_introduction_in_the_half_of_the_page():
    inleiding = ("The Bucha massacre was the mass killing of Ukrainian civilians by Russian troops in 2022. "
                 "It took place in the city of Bucha during the Russian occupation in March. ") * 3
    stukken = onderwerp.stukken_van(_pagina(inleiding))
    zinnen = [s for s in stukken if s["bron"] == onderwerp.BRON_ZIN]
    inleidingen = [s for s in stukken if s["bron"] == onderwerp.BRON_INLEIDING]
    assert zinnen and len(inleidingen) == 1
    assert all(s["label"] == "waar" and s["soort"] == "feit" for s in zinnen)
    assert inleidingen[0]["soort"] == "artikel" and inleidingen[0]["tekst"].startswith("Bucha massacre\n")
    # Dezelfde helft als de Wikipedia-zinnen van #31.6 voor deze pagina, en één zaak per pagina.
    assert {s["helft"] for s in stukken} == {zeef.helft("wikipedia:en:42")}
    assert {s["zaak"] for s in stukken} == {"wikipedia:en:42"}
    assert len({s["sleutel"] for s in stukken}) == len(stukken)


def test_a_short_introduction_gives_sentences_but_no_article():
    stukken = onderwerp.stukken_van(_pagina("Bucha is a city in Kyiv Oblast in northern Ukraine."))
    assert [s["bron"] for s in stukken] == [onderwerp.BRON_ZIN]
    assert len(stukken[0]["tekst"]) <= echtnieuws.MAX_LENGTE * 3


def test_a_true_piece_that_resembles_a_guarded_one_stays_out_of_the_lessons():
    hoogste = {"a": 0.84999, "b": 0.85, "c": 0.97}
    assert onderwerp.uit_te_sluiten(hoogste) == ["b", "c"]
