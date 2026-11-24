"""Eén bewering, meer redacties (PLAN #34.2bp, SPECS E9.S31): welke pagina's dezelfde bewering checkten bij een andere
redactie, met een poort op mijn lezing voordat het in een uitgave gaat."""

import json

import pytest

from doublecheck import zelfdebewering as zb


def test_candidates_are_pairs_of_pages_that_share_no_newsroom_once_with_their_best_score():
    paren = [{"pagina": "b", "ander": "a", "score": 0.81}, {"pagina": "a", "ander": "b", "score": 0.86},
             {"pagina": "a", "ander": "c", "score": 0.9},          # deelt Snopes
             {"pagina": "a", "ander": "weg", "score": 0.99},       # niet meer in de uitgave
             {"pagina": "d", "ander": "d", "score": 1.0}]
    redacties = {"a": {"Snopes"}, "b": {"AFP"}, "c": {"Snopes", "Maldita"}, "d": {"AFP"}}
    assert zb.kandidaten(paren, redacties) == [{"paar": "a|b", "score": 0.86}]


def test_the_model_sees_the_text_as_the_site_shows_it_and_the_original_but_never_a_verdict():
    a = zb.tekst_van("es", "Bill Gates compró   la isla", {"en": "Bill Gates bought the island"}, "2021-03-04")
    b = zb.tekst_van("en", "Bill Gates bought an island", {})
    assert a == {"taal": "es", "datum": "2021-03-04", "getoond": "Bill Gates bought the island",
                 "origineel": "Bill Gates compró la isla"}
    assert b == {"taal": "en", "datum": "", "getoond": "Bill Gates bought an island"}
    vraag = zb.verzoek([(a, b)])
    tekst = vraag["messages"][0]["content"][0]["text"]
    assert "A (es, first checked 2021-03-04): Bill Gates bought the island\n   original: Bill Gates compró la isla" in tekst
    assert "B (en): Bill Gates bought an island" in tekst
    assert "false" not in tekst.lower() and vraag["model"].startswith("claude-haiku")
    assert vraag["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]["oordeel"][
        "enum"] == ["ja", "nee", "twijfel"]
    with pytest.raises(zb.Weigering):
        zb.verzoek([(a, b)] * 11)


def test_a_long_text_is_cut_and_control_characters_go():
    t = zb.tekst_van("en", "x‮" + "y" * 900, {})
    assert len(t["getoond"]) == zb.MAX_TEKST and "‮" not in t["getoond"]


def test_only_a_known_answer_for_a_number_in_the_list_that_appears_once_counts():
    tekst = json.dumps({"antwoorden": [{"nr": 1, "oordeel": "ja", "reden": "same claim"},
                                       {"nr": 2, "oordeel": "misschien", "reden": ""},
                                       {"nr": 3, "oordeel": "nee", "reden": "a"}, {"nr": 3, "oordeel": "ja", "reden": "b"},
                                       {"nr": 9, "oordeel": "ja", "reden": ""}]})
    assert zb.lees(tekst, 4) == [{"oordeel": "ja", "reden": "same claim"}, None, None, None]
    assert zb.lees("geen json", 2) == [None, None] and zb.lees(None, 1) == [None]


def test_the_reading_sample_only_takes_yes_and_never_a_pair_from_the_trial():
    antwoorden = {f"{i:02d}|x": {"oordeel": "ja" if i % 2 else "nee"} for i in range(300)}
    proef = {"01|x", "03|x"}
    gekozen = zb.leesproef(antwoorden, proef)
    assert len(gekozen) == zb.LEES and not set(gekozen) & proef
    assert all(antwoorden[k]["oordeel"] == "ja" for k in gekozen)
    assert gekozen == zb.leesproef(antwoorden, proef)                      # vast zaad


def test_the_gate_opens_only_when_every_chosen_pair_is_read_and_98_are_the_same_claim():
    gekozen = [f"{i:03d}|x" for i in range(100)]
    assert zb.poort({}, gekozen)[0] is False
    assert zb.poort({k: "zelfde" for k in gekozen[:99]}, gekozen)[0] is False
    labels = {k: "zelfde" for k in gekozen}
    labels[gekozen[0]], labels[gekozen[1]] = "ander", "twijfel"
    assert zb.poort(labels, gekozen) == (True, "98 van 100 dezelfde bewering (eis 98)")
    labels[gekozen[2]] = "twijfel"                                         # twijfel telt als niet
    assert zb.poort(labels, gekozen)[0] is False
    assert zb.poort({}, gekozen[:50])[0] is False


def test_for_the_release_only_yes_counts_both_ways_and_nothing_while_the_gate_is_closed():
    antwoorden = {"a|b": {"oordeel": "ja"}, "a|c": {"oordeel": "twijfel"}, "b|d": {"oordeel": "ja"},
                  "c|d": {"oordeel": "nee"}}
    assert zb.voor_uitgave(antwoorden, True) == {"a": ["b"], "b": ["a", "d"], "d": ["b"]}
    assert zb.voor_uitgave(antwoorden, False) == {}


def test_below_the_floor_even_a_yes_does_not_count():
    antwoorden = {"a|b": {"oordeel": "ja"}, "a|c": {"oordeel": "ja"}, "b|c": {"oordeel": "nee"}}
    scores = {"a|b": 0.8399, "a|c": 0.84, "b|c": 0.95}
    assert zb.boven_vloer(antwoorden, scores) == {"a|c": {"oordeel": "ja"}, "b|c": {"oordeel": "nee"}}
    assert zb.voor_uitgave(zb.boven_vloer(antwoorden, scores), True) == {"a": ["c"], "c": ["a"]}


def test_a_pair_counts_only_when_both_readers_say_yes():
    eerste = {"a|b": {"oordeel": "ja"}, "a|c": {"oordeel": "ja"}, "b|c": {"oordeel": "nee"}, "c|d": {"oordeel": "ja"}}
    tweede = {"a|b": {"oordeel": "ja"}, "a|c": {"oordeel": "twijfel"}, "b|c": {"oordeel": "ja"}}
    samen = zb.beide_ja(eerste, tweede)
    assert {k: v["oordeel"] for k, v in samen.items()} == {"a|b": "ja", "a|c": "twijfel", "b|c": "nee", "c|d": "twijfel"}
    assert zb.voor_uitgave(samen, True) == {"a": ["b"], "b": ["a"]}
    assert zb.versie_van("haiku") == zb.VERSIE and zb.versie_van("sonnet") == f"{zb.VERSIE}/sonnet"
    assert zb.verzoek([(zb.tekst_van("en", "x", {}), zb.tekst_van("en", "y", {}))], "sonnet")["model"].startswith(
        "claude-sonnet")


def test_a_claim_about_a_photo_or_video_counts_only_with_the_same_person_on_both_pages():
    libie = zb.tekst_van("en", "Visuals from recent Libya flood", {})
    libie2 = zb.tekst_van("bn", "x", {"en": "The scenes in this video are from the storm and flooding in Libya."})
    poetin = zb.tekst_van("en", "This photo shows Putin in the attire of a Buddhist monk", {})
    poetin2 = zb.tekst_van("hi", "x", {"en": "Photos of Vladimir Putin dressed as a Buddhist monk"})
    graan = zb.tekst_van("en", "Fasting can cure cancer", {})
    assert zb.over_een_beeld(libie["getoond"]) and zb.over_een_beeld("Dit filmpje toont") and not zb.over_een_beeld(
        graan["getoond"])
    assert zb.beeldregel(libie, libie2, set(), set()) is False
    assert zb.beeldregel(libie, libie2, {"Q1016"}, {"Q1016"}) is True        # de aanroeper geeft alleen personen
    assert zb.beeldregel(poetin, poetin2, {"Q7747"}, {"Q7747"}) is True
    assert zb.beeldregel(graan, graan, set(), set()) is True                 # geen beeld: de regel speelt niet
    antwoorden = {"a|b": {"oordeel": "ja"}, "a|c": {"oordeel": "ja"}, "b|c": {"oordeel": "nee"}}
    uit = zb.met_beeldregel(antwoorden, {"a|b": True, "a|c": False})
    assert [uit[k]["oordeel"] for k in ("a|b", "a|c", "b|c")] == ["ja", "twijfel", "nee"]
