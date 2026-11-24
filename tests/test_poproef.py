"""Een steekproef voor de PO om op het oog na te kijken (PO 2026-11-07): willekeurig uit de antwoorden van een meting,
alleen Engelse berichten uit westerse media, met wat Factiz zei en daarna pas wat de redactie zei."""

from doublecheck import poproef as pp


def _rij(i, set_, kleur="rood", uitkomst="klopt niet"):
    return {"id": i, "set": set_, "arm": "C", "kleur": kleur, "uitkomst": uitkomst, "uitleg": "Uitleg.",
            "bronnen": [{"site": "bbc.com", "titel": "t", "url": "https://bbc.com/a", "rol": "spreekt tegen",
                         "band": "goed"}]}


ITEMS = {"o1": {"id": "o1", "set": "O", "tekst": "Nep 1", "publisher": "Snopes", "oordeel": "onwaar",
                "datum": "2026-02-01"},
         "o2": {"id": "o2", "set": "O", "tekst": "Nep 2", "publisher": "FACTLY", "oordeel": "onwaar",
                "datum": "2026-02-01"},
         "o3": {"id": "o3", "set": "O", "tekst": "Nep 3", "publisher": "Full Fact", "oordeel": "misleidend",
                "datum": "2026-03-01"},
         "m1": {"id": "m1", "set": "W-merk", "tekst": "BBC News\nKop", "merk": "BBC News", "datum": "2026-11-06"},
         "m2": {"id": "m2", "set": "W-merk", "tekst": "Al Jazeera\nKop", "merk": "Al Jazeera", "datum": "2026-11-06"},
         "w1": {"id": "w1", "set": "W", "tekst": "Oud artikel", "datum": "2007-01-01"}}
RIJEN = [_rij("o1", "O"), _rij("o2", "O"), _rij("o3", "O", "oranje", "misleidend"),
         _rij("m1", "W-merk", "groen", "klopt"), _rij("m2", "W-merk", "groen", "klopt"), _rij("w1", "W", "groen", "klopt")]


def test_only_english_messages_from_western_media_go_in_the_card_box():
    assert sorted(r["id"] for r in pp.voorraad(RIJEN, ITEMS)) == ["m1", "o1", "o3"]


def test_the_draw_is_random_but_fixed_by_its_seed_and_never_larger_than_the_box():
    a = pp.trek(RIJEN, ITEMS, n=2, zaad="2026-11-07")
    assert [r["id"] for r in a] == [r["id"] for r in pp.trek(list(reversed(RIJEN)), ITEMS, n=2, zaad="2026-11-07")]
    assert len(a) == 2 and len(pp.trek(RIJEN, ITEMS, n=25, zaad="x")) == 3


def test_each_card_shows_what_factiz_said_and_keeps_the_answer_of_the_newsroom_apart():
    kaart = next(r for r in pp.trek(RIJEN, ITEMS, n=3, zaad="x") if r["id"] == "o3")
    assert (kaart["bericht"], kaart["kleur"], kaart["uitkomst"]) == ("Nep 3", "oranje", "misleidend")
    assert kaart["bronnen"][0]["site"] == "bbc.com"
    assert kaart["onthulling"] == {"soort": "factcheck", "door": "Full Fact", "oordeel": "misleidend",
                                   "datum": "2026-03-01", "url": None}
    kop = next(r for r in pp.trek(RIJEN, ITEMS, n=3, zaad="x") if r["id"] == "m1")
    assert kop["onthulling"]["soort"] == "echte kop" and kop["onthulling"]["door"] == "BBC News"


def test_a_message_can_never_close_the_script_tag_of_the_page():
    pagina = pp.vul('<script type="application/json">/*KAARTEN*/</script>', {"kaarten": [{"bericht": "a</script><b>"}]})
    assert pagina.count("</script>") == 1 and "<\\/script><b>" in pagina


def test_a_product_round_takes_only_western_messages_the_po_has_not_seen_yet():
    items = list(ITEMS.values())
    uit = pp.nieuwe_berichten(items, gezien={"o1"}, n=5, zaad="r2")
    assert sorted(i["id"] for i in uit) == ["m1", "o3"]
    assert [i["id"] for i in pp.nieuwe_berichten(list(reversed(items)), {"o1"}, 1, "r2")] == \
        [i["id"] for i in pp.nieuwe_berichten(items, {"o1"}, 1, "r2")]


def test_a_card_answered_from_the_database_names_the_newsroom_and_its_verdict():
    rij = {**_rij("o1", "O"), "route": "database",
           "bronnen": [{"url": "https://www.snopes.com/x", "soort": "check van een redactie", "redactie": "Snopes",
                        "oordeel": "onwaar"}]}
    kaart = pp.trek([rij], ITEMS, n=1, zaad="x")[0]
    assert kaart["route"] == "database"
    assert kaart["bronnen"] == [{"site": "Snopes", "titel": "Check van Snopes: onwaar", "url": "https://www.snopes.com/x",
                                 "rol": "check in de database", "band": None}]


# --- een ronde uit het nieuws zelf (PO 2026-11-07: "echt random nieuwsfeiten, foto's en berichten") ---------------

RSS = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>  Storm hits   coast </title><link>https://news.example/storm</link><pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate>
<media:content url="https://img.example/storm.jpg" medium="image"/></item>
<item><title>Vote delayed</title><link>https://news.example/vote</link><pubDate>Fri, 06 Nov 2026 11:00:00 GMT</pubDate>
<enclosure url="https://img.example/vote.png" type="image/png"/></item>
<item><title>No picture here</title><link>https://news.example/plain</link><pubDate>Thu, 05 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_a_feed_gives_headline_link_date_and_the_photo_when_there_is_one():
    uit = pp.uit_feed(RSS, "Example News")
    assert [(i["titel"], i["url"], i["datum"], i["foto"]) for i in uit] == [
        ("Storm hits coast", "https://news.example/storm", "2026-11-06", "https://img.example/storm.jpg"),
        ("Vote delayed", "https://news.example/vote", "2026-11-06", "https://img.example/vote.png"),
        ("No picture here", "https://news.example/plain", "2026-11-05", None)]
    assert all(i["merk"] == "Example News" for i in uit)


def _nieuws(merk, n, foto=True):
    return [{"merk": merk, "titel": f"{merk} headline number {i} about something", "url": f"https://{merk}.example/{i}",
             "datum": "2026-11-06", "foto": f"https://img.example/{merk}{i}.jpg" if foto else None} for i in range(n)]


def test_a_news_round_draws_headlines_and_photos_evenly_over_outlets_and_is_fixed_by_its_seed():
    items = _nieuws("a", 30) + _nieuws("b", 3, foto=False) + _nieuws("c", 5)
    ronde = pp.nieuwsronde(items, n_koppen=8, n_fotos=3, zaad="r3")
    assert ronde == pp.nieuwsronde(list(reversed(items)), n_koppen=8, n_fotos=3, zaad="r3")
    koppen, fotos = [i for i in ronde if i["set"] == "K"], [i for i in ronde if i["set"] == "F"]
    assert len(koppen) == 8 and len(fotos) == 3 and all(i["beeld"] for i in fotos)
    assert len({i["id"] for i in ronde}) == 11
    assert {i["merk"] for i in koppen} == {"a", "b", "c"}            # elk medium even zwaar, niet naar aantal koppen
    assert sum(i["tekst"].startswith(i["merk"] + "\n") for i in koppen) == 4   # de helft met de naam van het medium
    assert all(i["tekst"].endswith(i["titel"]) for i in ronde)


def test_a_news_card_shows_the_photo_link_and_afterwards_the_source_and_whether_a_fact_check_existed():
    item = {"id": "F:1", "set": "F", "tekst": "a headline", "merk": "BBC News", "datum": "2026-11-06",
            "url": "https://www.bbc.com/news/1", "beeld": "https://img.example/1.jpg"}
    rij = {**_rij("F:1", "F", None, "onzeker"), "route": "zoeken",
           "bronnen": [{"url": "https://www.snopes.com/fact-check/x", "site": "snopes.com", "rol": "spreekt tegen"}]}
    kaart = pp.trek([rij], {"F:1": item}, n=1, zaad="x", is_factcheck=lambda u: "snopes" in u)[0]
    assert kaart["foto"] == "https://img.example/1.jpg"
    assert kaart["onthulling"] == {"soort": "nieuws", "door": "BBC News", "oordeel": None, "datum": "2026-11-06",
                                   "url": "https://www.bbc.com/news/1", "factcheck": True}
