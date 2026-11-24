"""De voormeting voor de vloer (PLAN #32.0f, na P9): een vraag zonder zoeken op de
berichten waar de machine zonder bron *onzeker* of *let op* zei."""

import pytest

from doublecheck import vloer as vl


def _a(oordeel, bronnen=()):
    return {"oordeel": oordeel, "bronnen": list(bronnen)}


def test_only_unsure_or_watch_out_without_any_source_enters_the_pool():
    assert vl.zonder_bron(_a("onzeker")) and vl.zonder_bron(_a("let op"))
    assert not vl.zonder_bron(_a("let op", [{"soort": "web", "url": "https://a.org"}]))
    assert not vl.zonder_bron(_a("klopt niet")) and not vl.zonder_bron(_a("klopt"))


def test_the_pool_keeps_one_copy_of_each_message_and_only_true_false_or_misleading():
    rijen = [{"bron": "x", "id": "1", "tekst": "The Moon is  made of cheese.", "label": "onwaar", "helft": "toets"},
             {"bron": "y", "id": "2", "tekst": "the moon is made of cheese.", "label": "onwaar", "helft": "toets"},
             {"bron": "x", "id": "3", "tekst": "Paris is in France.", "label": "waar", "helft": "ontwikkel"},
             {"bron": "x", "id": "4", "tekst": "Hello there", "label": "geen bewering", "helft": "toets"}]
    pool = vl.ontdubbel(rijen)
    assert [r["id"] for r in pool] == ["x:1", "x:3"]


def test_the_answer_is_read_strictly_and_anything_unclear_counts_as_not_clearly_false():
    assert vl.lees_oordeel('{"waarom": "x", "oordeel": "clearly false"}') == "clearly false"
    assert vl.lees_oordeel('{"waarom": "x", "oordeel": "not clearly false"}') == "not clearly false"
    for tekst in ("geen json", '{"oordeel": "maybe"}', "[]"):
        assert vl.lees_oordeel(tekst) == "not clearly false"


def test_both_keys_ask_the_same_message_without_search_and_with_haiku():
    from doublecheck.config import load_config

    for sleutel in ("A", "B"):
        params = vl.verzoek("The Moon is made of cheese.", sleutel, load_config(None))
        assert "tools" not in params and params["model"] == "claude-haiku-5-5"
        assert "The Moon is made of cheese." in params["messages"][0]["content"]
    assert vl.verzoek("x", "A", load_config(None))["messages"] != vl.verzoek("x", "B", load_config(None))["messages"]


def _pool():
    return ([{"id": f"w{i}", "label": "waar"} for i in range(10)] + [{"id": f"o{i}", "label": "onwaar"} for i in range(10)]
            + [{"id": f"m{i}", "label": "misleidend"} for i in range(2)]
            + [{"id": f"r3-{i}", "label": "onwaar", "r3": True} for i in range(3)])


def _antw(vals):
    return {(i, k): "clearly false" for i in vals for k in ("A", "B")}


def test_a_false_alarm_on_a_true_message_must_be_read_and_only_a_wrong_set_is_excused():
    antwoorden = _antw(["w0", "o0", "o1", "r3-0", "r3-1"])
    antwoorden[("o2", "A")], antwoorden[("o2", "B")] = "clearly false", "not clearly false"  # één sleutel is niet genoeg
    with pytest.raises(vl.Weigering):
        vl.telling(_pool(), antwoorden, {}, waar_in_rondes=600)
    t = vl.telling(_pool(), antwoorden, {"w0": "vals"}, waar_in_rondes=600)
    assert t["waar"]["beide"] == 1 and t["onwaar"]["beide"] == 2 and t["onwaar"]["A"] == 3
    assert t["eisen"] == {"hoogstens 1 vals alarm per 300 ware berichten in de rondes": True,
                          "minstens 2 van de 3 missers van R3 gevangen": True}
    t = vl.telling(_pool(), {**antwoorden, **_antw(["w1", "w2"])}, {"w0": "vals", "w1": "vals", "w2": "vals"},
                   waar_in_rondes=600)
    assert t["eisen"]["hoogstens 1 vals alarm per 300 ware berichten in de rondes"] is False
    t = vl.telling(_pool(), antwoorden, {"w0": "set fout"}, waar_in_rondes=600)
    assert t["waar"]["vals alarm"] == 0 and t["waar"]["set fout"] == 1
