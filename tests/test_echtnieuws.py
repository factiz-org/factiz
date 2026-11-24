"""Echt nieuws en ware zinnen (PLAN #31.6, E8.S6): de regels van het ophaalplan."""

import json

from doublecheck import echtnieuws


def test_a_cirrus_dump_gives_each_page_id_with_its_document():
    regels = [json.dumps({"index": {"_type": "_doc", "_id": "12"}}), json.dumps({"title": "A", "text": "x"}),
              "", json.dumps({"index": {"_id": "13"}}), json.dumps({"title": "B", "text": "y"})]
    assert [(i, d["title"]) for i, d in echtnieuws.cirrus_paren(regels)] == [("12", "A"), ("13", "B")]


def test_a_news_article_keeps_title_opening_text_and_date_and_is_true_news():
    doc = {"title": "Floods in Chennai", "text": "Chennai, India — " + "Heavy rain fell. " * 200,
           "create_timestamp": "2015-12-03T10:00:00Z"}
    stuk = echtnieuws.nieuwsstuk("en", "12", doc)
    assert stuk["soort"] == "nieuws" and stuk["label"] == "waar" and stuk["bron"] == "wikinews"
    assert stuk["url"] == "https://en.wikinews.org/wiki/Floods_in_Chennai"
    assert stuk["datum"] == "2015-12-03" and len(stuk["tekst"]) == echtnieuws.MAX_TEKENS
    assert stuk["tekst"].startswith("Floods in Chennai\n")
    assert stuk["helft"] == echtnieuws.nieuwsstuk("en", "12", doc)["helft"]


def test_a_page_with_almost_no_text_is_not_news():
    assert echtnieuws.nieuwsstuk("en", "1", {"title": "Main Page", "text": "Welcome."}) is None


def _artikel(tekst, id_="7"):
    return {"id": id_, "url": f"https://x.wikipedia.org/wiki?curid={id_}", "title": "T", "text": tekst}


def test_true_sentences_come_only_from_the_introduction_within_the_length_bounds():
    inleiding = ("Amsterdam is the capital and most populous city of the Netherlands. "
                 "It has about 900,000 inhabitants in the city proper. Short one. ")
    tekst = inleiding + "\n\nHistory\n\nThe city was founded as a fishing village in the late 12th century."
    zinnen = echtnieuws.feitzinnen(_artikel(tekst), "en")
    assert [z["tekst"] for z in zinnen] == ["Amsterdam is the capital and most populous city of the Netherlands.",
                                          "It has about 900,000 inhabitants in the city proper."]
    assert {z["helft"] for z in zinnen} == {zinnen[0]["helft"]}
    assert all(z["soort"] == "feit" and z["label"] == "waar" and z["bron"] == "wikipedia" for z in zinnen)


def test_true_sentences_are_found_in_every_script():
    teksten = {
        "ru": "Москва — столица России и крупнейший по численности населения город страны. "
              "Город расположен на реке Москве в центре Восточно-Европейской равнины.",
        "ar": "القاهرة هي عاصمة جمهورية مصر العربية وأكبر مدنها من حيث عدد السكان. "
              "تقع المدينة على ضفاف نهر النيل في شمال البلاد.",
        "hi": "नई दिल्ली भारत की राजधानी है और यह दिल्ली राज्य के अंतर्गत आती है। "
              "यह शहर यमुना नदी के किनारे बसा हुआ एक प्रमुख प्रशासनिक केंद्र है।",
        "zh": "北京市是中华人民共和国的首都，也是全国的政治和文化中心。北京位于华北平原的北部，历史悠久。",
    }
    for taal, tekst in teksten.items():
        assert len(echtnieuws.feitzinnen(_artikel(tekst), taal)) == 2, taal


def test_at_most_ten_sentences_per_article():
    tekst = " ".join(f"Sentence number {i} is a perfectly ordinary statement of fact here." for i in range(20))
    assert len(echtnieuws.feitzinnen(_artikel(tekst), "en")) == echtnieuws.MAX_ZINNEN
