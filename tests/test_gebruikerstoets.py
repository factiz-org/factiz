"""De gebruikerstoets (P11 van fase 0, PLAN #32.0k, B47): de regels die vóór de
eerste vraag aan het model vastlagen."""

import pytest

from doublecheck import gebruikerstoets as g
from doublecheck.config import load_config


def _rijen(voorvoegsel, n, **extra):
    return [{"id": f"{voorvoegsel}{i:04d}", "sleutel": f"S:https://www.{voorvoegsel}{i % 7}.com/a/{i}",
             "tekst": f"Kop {i}\nHet begin van artikel {i}.", **extra} for i in range(n)]


def _pools():
    politiek = [{**r, "kant": "links" if i % 2 else "rechts"} for i, r in enumerate(_rijen("p", 80))]
    return {"artikelen": _rijen("a", 300), "gezondheid": _rijen("d", 90), "politiek": politiek,
            "feit_onwaar": _rijen("v", 60), "feit_waar": _rijen("k", 60)}


def test_the_set_has_the_six_parts_of_the_plan_fixed_by_seed():
    keuze = g.kies(_pools())
    assert keuze == g.kies(_pools())
    tel = {}
    for s in keuze:
        tel[s["sub"]] = tel.get(s["sub"], 0) + 1
    assert tel == {"A": 50, "B-krant": 10, "B-schrijver": 10, "B-feit": 20, "B-kop": 10, "C": 40, "D": 40,
                   "E": 30, "F-onwaar": 20, "F-waar": 20}
    assert len({s["id"] for s in keuze}) == 250
    assert len({s["bron_id"] for s in keuze if s["deel"] in "ABC"}) == 140  # elk artikel één keer
    kanten = [s["kant"] for s in keuze if s["deel"] == "E"]
    assert kanten.count("links") == kanten.count("rechts") == 15  # 13 uit de checks en 2 eigen per kant
    for deel in "ABCDEF":
        helften = [s["helft"] for s in keuze if s["deel"] == deel]
        assert abs(helften.count("ontwikkel") - helften.count("toets")) <= 1


def test_every_message_carries_its_right_answer_from_how_it_was_made():
    per_sub = {s["sub"]: s["verwacht"] for s in g.kies(_pools())}
    assert per_sub["A"] == {"inhoud": "waar", "herkomst": "echt"}
    assert per_sub["B-krant"] == {"inhoud": "waar", "herkomst": "vals"}
    assert per_sub["B-feit"] == {"inhoud": "onwaar", "herkomst": "vals"}
    assert per_sub["C"]["inhoud"] == "onwaar" and per_sub["E"]["inhoud"] == "misleidend"
    assert per_sub["F-waar"]["inhoud"] == "waar" and per_sub["F-onwaar"]["inhoud"] == "onwaar"


def test_a_forged_article_shows_another_outlet_or_a_writer_who_does_not_exist():
    keuze = g.kies(_pools())
    krant = next(s for s in keuze if s["sub"] == "B-krant")
    assert krant["toon_domein"] != g.domein(krant["sleutel"][2:])
    schrijver = next(s for s in keuze if s["sub"] == "B-schrijver")
    assert schrijver["schrijver"] and schrijver["toon_domein"] == g.domein(schrijver["sleutel"][2:])
    echt = next(s for s in keuze if s["sub"] == "A")
    assert echt["toon_domein"] == g.domein(echt["sleutel"][2:]) and echt["schrijver"] is None


def test_the_bare_question_is_the_same_text_with_or_without_search():
    config = load_config()
    met = g.kaal_verzoek("The moon landing was faked.", True, config)
    zonder = g.kaal_verzoek("The moon landing was faked.", False, config)
    assert met["tools"][0]["type"] == "web_search_20250305" and "tools" not in zonder
    assert met["messages"] == zonder["messages"] and "The moon landing was faked." in met["messages"][0]["content"]
    assert met["model"] == config.berichtcontrole.model_id
    assert "Factiz memory" not in met["messages"][0]["content"]  # het kale model krijgt onze lagen niet


def test_reading_the_bare_answer():
    assert g.lees_kaal("It was not faked.\nVERDICT: false") == "rood"
    assert g.lees_kaal("Yes.\n**VERDICT: True**") == "groen"
    assert g.lees_kaal("VERDICT: uncertain") is None
    assert g.lees_kaal("no verdict line") is None


def test_two_independent_sources_means_two_different_domains():
    bronnen = [{"soort": "web", "url": "https://www.bbc.com/news/1"}, {"soort": "web", "url": "https://bbc.com/x"},
               {"soort": "geheugen", "url": "https://www.politifact.com/f/1"}]
    assert g.domeinen(bronnen) == {"bbc.com", "politifact.com"}


def _stuk(i, sub, kant=None):
    s = next(x for x in g.kies(_pools()) if x["sub"] == sub)
    return {**s, "id": i, "kant": kant or s.get("kant")}


def _uit(kleur, bronnen=(), eigen=False):
    return {"kleur": kleur, "bronnen": list(bronnen), "eigen_bewijs": eigen}


WEB = {"soort": "web", "url": "https://www.reuters.com/a"}
WEB2 = {"soort": "web", "url": "https://apnews.com/b"}


def test_the_count_refuses_while_a_red_on_a_real_article_has_no_label():
    stukken = [_stuk("a1", "A")]
    with pytest.raises(g.Weigering):
        g.telling(stukken, {"a1": _uit("rood", [WEB])}, {"a1": _uit(None)}, {"a1": _uit(None)}, {})
    with pytest.raises(g.Weigering):  # ook een rood van het kale model, voor de vergelijking
        g.telling(stukken, {"a1": _uit(None)}, {"a1": _uit("rood", [WEB])}, {"a1": _uit(None)}, {})
    telling = g.telling(stukken, {"a1": _uit("rood", [WEB])}, {"a1": _uit(None)}, {"a1": _uit(None)},
                        {("a1", "factiz", "rood"): "vals"})
    assert telling["A"]["factiz onterecht rood"] == 1
    assert telling["eisen"]["A hoogstens 1 van de 50 rood"] is True


def test_the_floor_counts_factiz_unsure_where_the_bare_model_is_right_with_a_source():
    stukken = [_stuk("f1", "F-onwaar"), _stuk("f2", "F-waar")]
    factiz = {"f1": _uit(None), "f2": _uit("groen", [WEB])}
    kaal = {"f1": _uit("rood", [WEB]), "f2": _uit("groen", [WEB])}
    telling = g.telling(stukken, factiz, kaal, {"f1": _uit("rood"), "f2": _uit("groen")}, {})
    assert telling["F"]["factiz goed"] == 1 and telling["F"]["kaal goed"] == 2
    assert telling["F"]["factiz onzeker waar kaal goed is met bron"] == 1
    assert telling["eisen"]["F vloer: nooit onzeker waar het kale model het goed heeft"] is False


def test_a_forged_article_that_comes_back_green_is_the_baseline_not_a_failure():
    stukken = [_stuk("b1", "B-krant"), _stuk("b2", "B-schrijver")]
    groen = {"b1": _uit("groen", [WEB]), "b2": _uit("groen", [WEB])}
    telling = g.telling(stukken, groen, groen, {"b1": _uit(None), "b2": _uit(None)}, {})
    assert telling["B"]["factiz groen bij een vervalsing"] == 2
    assert telling["B"]["kaal groen bij een vervalsing"] == 2
    assert not any(k.startswith("B") for k in telling["eisen"])


def test_a_green_on_an_invented_detail_is_read():
    stukken = [_stuk("c1", "C")]
    with pytest.raises(g.Weigering):
        g.telling(stukken, {"c1": _uit("groen", [WEB])}, {"c1": _uit(None)}, {"c1": _uit(None)}, {})
    telling = g.telling(stukken, {"c1": _uit("groen", [WEB])}, {"c1": _uit(None)}, {"c1": _uit(None)},
                        {("c1", "factiz", "groen"): "vals"})
    assert telling["C"]["factiz groen"] == 1


def test_health_myths_count_red_with_proof():
    stukken = [_stuk("d1", "D"), _stuk("d2", "D")]
    factiz = {"d1": _uit("rood", eigen=True), "d2": _uit("rood", [WEB])}
    with pytest.raises(g.Weigering):  # rood met een andere bron dan de eigen check wordt gelezen
        g.telling(stukken, factiz, {"d1": _uit("rood"), "d2": _uit(None)}, {"d1": _uit(None), "d2": _uit(None)}, {})
    telling = g.telling(stukken, factiz, {"d1": _uit("rood"), "d2": _uit(None)}, {"d1": _uit(None), "d2": _uit(None)},
                        {("d2", "factiz", "bewijs"): "bewijst"})
    assert telling["D"]["factiz rood met bewijs"] == 2


def test_left_and_right_reds_are_compared_and_context_needs_two_domains():
    stukken = [_stuk("e1", "E", "links"), _stuk("e2", "E", "rechts")]
    factiz = {"e1": _uit("rood", [WEB, WEB2]), "e2": _uit(None, [WEB])}
    telling = g.telling(stukken, factiz, {"e1": _uit(None), "e2": _uit(None)}, {"e1": _uit(None), "e2": _uit(None)}, {})
    assert telling["E"]["factiz rood links"] == 1 and telling["E"]["factiz rood rechts"] == 0
    assert telling["E"]["factiz context met twee bronnen"] == 1
    assert telling["eisen"]["E elk antwoord context met minstens twee onafhankelijke bronnen"] is False


def test_the_test_half_is_reported_apart():
    stukken = [{**_stuk("f1", "F-onwaar"), "helft": "ontwikkel"}, {**_stuk("f2", "F-onwaar"), "helft": "toets"}]
    rood = {"f1": _uit("rood", [WEB]), "f2": _uit("rood", [WEB])}
    telling = g.telling(stukken, rood, rood, rood, {})
    assert telling["toetshelft"]["F"]["factiz goed"] == 1


def test_a_message_rejected_on_reading_is_replaced_by_the_next_in_the_same_order():
    keuze = g.kies(_pools())
    weg = next(s for s in keuze if s["sub"] == "D")["bron_id"]
    zonder = g.kies(_pools(), afgewezen={weg})
    d_voor = [s["bron_id"] for s in keuze if s["sub"] == "D"]
    d_na = [s["bron_id"] for s in zonder if s["sub"] == "D"]
    assert weg not in d_na and len(d_na) == 40 and d_na[:39] == [x for x in d_voor if x != weg]
    assert [s["bron_id"] for s in zonder if s["sub"] == "A"] == [s["bron_id"] for s in keuze if s["sub"] == "A"]


def test_a_made_up_detail_must_really_replace_a_phrase_from_the_article():
    bron = "Russia expels 23 British diplomats\nMoscow said on Saturday it would expel 23 British diplomats."
    assert g.vervanging_klopt(bron, {"bericht": "Moscow expels 32 British diplomats.", "origineel": "23", "nieuw": "32"})
    assert not g.vervanging_klopt(bron, {"bericht": "Moscow expels 23 British diplomats.", "origineel": "23", "nieuw": "23"})
    assert not g.vervanging_klopt(bron, {"bericht": "Moscow expels 32 diplomats.", "origineel": "Paris", "nieuw": "32"})
