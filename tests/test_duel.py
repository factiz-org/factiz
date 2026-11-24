"""Factiz tegen gewoon zoeken: een blind duel met Gemini in de kaartenbak (PLAN #32.47, PO 2026-11-07: "Alleen Gemini")."""

import json

from doublecheck import duel


def _check(i, uitgever="Snopes", oordeel="onwaar", datum="2026-10-20", taal="en", claim=None):
    return {"claim_id": claim or f"gfc-{i:04d}", "tekst": f"A claim that went around number {i} about something",
            "publisher": uitgever, "oordeel": oordeel, "datum": datum, "taal": taal, "url": f"https://check.example/{i}"}


def test_fresh_fakes_are_recent_english_checks_of_western_newsrooms_never_seen_before():
    checks = ([_check(i) for i in range(10)] + [_check(10, uitgever="FACTLY"), _check(11, oordeel="waar"),
                                                _check(12, datum="2025-01-01"), _check(13, taal="es")])
    uit = duel.verse_nep(checks, gezien={"gfc-0001"}, n=20, zaad="r1", sinds="2026-08-01")
    assert sorted(i["id"] for i in uit) == [f"O:gfc-{i:04d}" for i in range(10) if i != 1]
    assert all(i["set"] == "O" and i["eigen_urls"][0].startswith("https://check.example/") for i in uit)
    assert duel.verse_nep(checks, set(), 3, "r1", "2026-08-01") == duel.verse_nep(list(reversed(checks)), set(), 3, "r1",
                                                                                   "2026-08-01")


def test_gemini_gets_the_plain_question_of_a_dutch_user_with_google_search_and_the_photo():
    v = duel.gemini_verzoek("Paus Leo bezoekt Brazilië", beeld=b"\x89PNG", mime="image/png")
    tekst = v["contents"][0]["parts"][-1]["text"]
    assert "Paus Leo bezoekt Brazilië" in tekst and "OORDEEL" in tekst and "Nederlands" in tekst
    assert v["tools"] == [{"google_search": {}}]
    assert v["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"
    assert "inline_data" not in json.dumps(duel.gemini_verzoek("tekst"))


ANTWOORD = {"candidates": [{"content": {"parts": [{"text": "OORDEEL: klopt niet\nDe foto is oud en komt uit 2019."}]},
                            "groundingMetadata": {"webSearchQueries": ["paus leo brazilië"],
                                                  "groundingChunks": [{"web": {"uri": "https://vertexaisearch.example/1",
                                                                               "title": "reuters.com"}}]}}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200, "thoughtsTokenCount": 300}}


def test_geminis_answer_is_read_into_a_verdict_an_explanation_and_its_sources():
    uit = duel.lees_gemini(ANTWOORD)
    assert uit["oordeel"] == "klopt niet" and uit["uitleg"].startswith("De foto is oud")
    assert uit["bronnen"] == [{"site": "reuters.com", "url": "https://vertexaisearch.example/1"}]
    assert uit["zoekvragen"] == 1 and uit["tokens"] == {"in": 1000, "uit": 500}
    vaag = {"candidates": [{"content": {"parts": [{"text": "Dat is lastig te zeggen."}]}}]}
    assert duel.lees_gemini(vaag)["oordeel"] == "weet ik niet"
    assert duel.lees_gemini({"candidates": []})["oordeel"] == "geen antwoord"


def test_the_cost_of_a_gemini_answer_counts_tokens_and_searches_beyond_the_free_allowance():
    uit = duel.lees_gemini(ANTWOORD)
    assert duel.kosten(uit, gratis_over=0) == round(1000 * 2 / 1e6 + 500 * 10 / 1e6 + 1 * 14 / 1000, 6)
    assert duel.kosten(uit, gratis_over=10) == round(1000 * 2 / 1e6 + 500 * 10 / 1e6, 6)


def test_each_card_shows_both_answers_blind_in_a_fixed_random_order():
    factiz = {"id": "K:1", "kleur": "groen", "uitkomst": "klopt", "uitleg": "Uitleg.", "bronnen": []}
    gemini = {"id": "K:1", "oordeel": "klopt", "uitleg": "Ander antwoord.", "bronnen": [{"site": "bbc.com", "url": "u"}]}
    a = duel.duelkaart(factiz, gemini, zaad="r1")
    assert {a["antwoorden"][0]["wie"], a["antwoorden"][1]["wie"]} == {"Factiz", "Gemini"}
    assert [x["wie"] for x in a["antwoorden"]] == [x["wie"] for x in duel.duelkaart(factiz, gemini, zaad="r1")["antwoorden"]]
    volgorden = {tuple(x["wie"] for x in duel.duelkaart({**factiz, "id": f"K:{i}"}, {**gemini, "id": f"K:{i}"},
                                                         zaad="r1")["antwoorden"]) for i in range(20)}
    assert len(volgorden) == 2


def test_neither_answer_gives_away_who_wrote_it():
    factiz = {"id": "O:1", "kleur": "rood", "uitkomst": "klopt niet", "uitleg": None, "route": "database",
              "bronnen": [{"redactie": "Snopes", "oordeel": "onwaar", "url": "https://www.snopes.com/x"}]}
    gemini = {"id": "O:1", "oordeel": "weet ik niet", "uitleg": "**Lastig.** Ik vond niets.", "bronnen": []}
    kaart = duel.duelkaart(factiz, gemini, zaad="r1")
    van = {a["wie"]: a for a in kaart["antwoorden"]}
    assert "Factiz" not in van["Factiz"]["uitleg"] and "database" not in van["Factiz"]["uitleg"]
    assert "Snopes" in van["Factiz"]["uitleg"] and "onwaar" in van["Factiz"]["uitleg"]
    assert van["Factiz"]["bronnen"] == [{"site": "snopes.com", "url": "https://www.snopes.com/x"}]
    assert van["Gemini"]["oordeel"] == "onzeker" and van["Gemini"]["uitleg"] == "Lastig. Ik vond niets."
    schuin = duel.duelkaart(factiz, {**gemini, "uitleg": "Een artikel van *The Guardian* over 5 * 3 = 15."}, zaad="r1")
    assert {a["wie"]: a for a in schuin["antwoorden"]}["Gemini"]["uitleg"] == "Een artikel van The Guardian over 5 * 3 = 15."


def test_the_google_key_of_the_project_serves_when_there_is_no_separate_gemini_key():
    assert duel.gemini_sleutel({"GEMINI_API_KEY": "a", "GOOGLE_VISION_API_KEY": "b"}) == "a"
    assert duel.gemini_sleutel({"GOOGLE_VISION_API_KEY": "b"}) == "b"
    assert duel.gemini_sleutel({}) is None


def test_geminis_own_headings_and_source_list_leave_the_explanation_its_sources_stay_below():
    tekst = ("**OORDEEL: klopt**\n\n**Uitleg:**\nHet bericht komt van The Guardian.\n\nDe koers viel 5 procent.\n\n"
             "**Bronnen:**\n* *The Guardian* – kop\n* CNN – kop")
    uit = duel.lees_gemini({"candidates": [{"content": {"parts": [{"text": tekst}]}}]})
    assert uit["oordeel"] == "klopt"
    assert uit["uitleg"] == "Het bericht komt van The Guardian.\n\nDe koers viel 5 procent."
