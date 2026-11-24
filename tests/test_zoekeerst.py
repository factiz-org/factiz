"""Zoeken eerst: de simpele versie (PLAN #32.9)."""

import json

from doublecheck import zoekeerst as z

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "aljazeera.com": [["goed", "Lin e.a. 0.70"]], "infowars.com": [["laag", "Lin e.a. 0.10"]]}


def test_the_query_is_the_message_itself_cut_to_fifty_words_and_400_characters():
    tekst = "Train  crash\nin Spain " + " ".join(f"w{i}" for i in range(80))
    q = z.zoekvraag(tekst)
    assert q.startswith("Train crash in Spain w0") and len(q.split()) == 50 and len(q) <= 400
    assert z.zoekvraag("   ") == ""


def _brave(*urls):
    return {"web": {"results": [{"url": u, "title": f"titel {i}", "description": f"<strong>fragment</strong> {i}",
                                 "extra_snippets": [f"extra {i}"]} for i, u in enumerate(urls)]}}


def test_each_result_carries_its_site_and_band_from_the_source_list():
    r = z.resultaten_uit(_brave("https://www.nytimes.com/a", "https://www.youtube.com/watch?v=1",
                                "https://www.infowars.com/b"), SITES)
    assert [(x["nr"], x["site"], x["band"]) for x in r] == [(1, "nytimes.com", "goed"), (2, "youtube.com", None),
                                                            (3, "infowars.com", "laag")]
    assert r[0]["fragment"] == "fragment 0 extra 0"


def _r(*paren):
    return [{"nr": i, "url": u, "site": u.split("/")[2], "band": b, "soort": "overig"} for i, (u, b) in enumerate(paren, 1)]


def test_green_needs_two_good_publishers_and_red_one_good_contradiction():
    res = _r(("https://nytimes.com/a", "goed"), ("https://edition.cnn.com/b", "goed"), ("https://cnn.com/c", "goed"),
             ("https://infowars.com/d", "laag"))
    assert z.kleur_van({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": []}, res) == "groen"
    assert z.kleur_van({"oordeel": "klopt", "steunt": [2, 3], "spreekt_tegen": []}, res) is None  # één uitgever
    assert z.kleur_van({"oordeel": "klopt", "steunt": [1, 4], "spreekt_tegen": []}, res) is None  # één goede
    assert z.kleur_van({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [3]}, res) is None  # goede tegenspraak
    assert z.kleur_van({"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [1]}, res) == "rood"
    assert z.kleur_van({"oordeel": "klopt niet", "steunt": [], "spreekt_tegen": [4]}, res) is None  # alleen een slechte
    assert z.kleur_van({"oordeel": "klopt", "steunt": [1, 2, 99], "spreekt_tegen": []}, res) == "groen"  # 99 bestaat niet
    assert z.kleur_van({"oordeel": "onzeker", "steunt": [1, 2], "spreekt_tegen": []}, res) is None


def test_the_reader_answer_is_read_strictly_and_anything_else_is_unsure():
    goed = z.lees_oordeel(json.dumps({"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [], "uitleg": "x"}))
    # v1 kent `over_beeld` (#32.12), de twee lagen (#32.13), de checks uit de database (#32.28) en de vorm en het
    # detail (#32.31) en de verdere zoekvragen van de speurstap (#32.40) niet: ze ontbreken, en zijn dus nee, zelf en leeg
    assert goed == {"oordeel": "klopt", "steunt": [1, 2], "spreekt_tegen": [], "uitleg": "x", "over_beeld": False,
                    "feit": "", "feit_steunt": [], "anders": "", "zelfde": [], "vorm": "zelf",
                    "detail": {"woorden": "", "juist": "", "nr": 0}, "verder": [], "zou_gemeld": False}
    assert z.lees_oordeel("geen JSON")["oordeel"] == "onzeker"
    assert z.lees_oordeel(json.dumps({"oordeel": "misschien"}))["oordeel"] == "onzeker"


def test_the_comparison_counts_right_wrong_and_no_colour_per_part():
    stukken = [{"id": "K:1", "deel": "K"}, {"id": "V:1", "deel": "V"}, {"id": "W:1", "deel": "W"}, {"id": "W:2", "deel": "W"}]
    a = {"K:1": "rood", "V:1": None, "W:1": "groen", "W:2": "rood"}
    uit = z.vergelijk(stukken, a)
    assert uit["K"] == {"n": 1, "juist": 1, "fout": 0, "geen kleur": 0}
    assert uit["W"] == {"n": 2, "juist": 1, "fout": 1, "geen kleur": 0}
    assert uit["samen"] == {"n": 4, "juist": 2, "fout": 1, "geen kleur": 1}
