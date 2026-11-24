"""Waarom het nep is (stap 7, de eis van V1: 95% van de zinnen gedekt door een bron; PLAN #32.56, PO 2026-11-07: "doen"):
per zin van de uitleg of die rust op een bron die de lezer noemde."""

import json

import pytest

from doublecheck import uitlegdekking as ud


def test_the_explanation_is_split_into_sentences_over_paragraphs_without_breaking_numbers_or_abbreviations():
    tekst = ("Dit klopt niet: de video komt uit 2019. AFP vond het origineel o.a. op YouTube.\n\n"
             "Op 6 november 2026 meldde de BBC 3,5 miljoen kijkers. Wat er echt gebeurde, is anders!")
    assert ud.zinnen(tekst) == ["Dit klopt niet: de video komt uit 2019.", "AFP vond het origineel o.a. op YouTube.",
                                "Op 6 november 2026 meldde de BBC 3,5 miljoen kijkers.", "Wat er echt gebeurde, is anders!"]
    assert ud.zinnen("") == [] and ud.zinnen("Eén zin zonder punt") == ["Eén zin zonder punt"]


def test_the_checker_sees_each_sentence_and_only_what_the_reader_saw():
    v = ud.verzoek(["Zin een.", "Zin twee."], {"https://bbc.com/a": "Kop — fragment"})
    tekst = v["messages"][0]["content"]
    assert "[1] Zin een." in tekst and "[2] Zin twee." in tekst and "Kop — fragment" in tekst
    assert v["output_config"]["format"]["schema"]["properties"]["zinnen"]["items"]["properties"]["dekking"]["enum"] == [
        "gedekt", "niet gedekt", "geen feit"]


def test_an_unreadable_answer_counts_every_sentence_as_not_covered():
    goed = json.dumps({"zinnen": [{"nr": 1, "dekking": "gedekt"}, {"nr": 2, "dekking": "geen feit"}]})
    assert ud.lees(goed, 2) == ["gedekt", "geen feit"]
    assert ud.lees("kapot", 2) == ["niet gedekt", "niet gedekt"]
    assert ud.lees(json.dumps({"zinnen": [{"nr": 9, "dekking": "gedekt"}]}), 1) == ["niet gedekt"]


def test_the_count_refuses_while_an_uncovered_sentence_is_unread_and_corrects_with_the_labels():
    rijen = [{"id": "a", "zinnen": ["z1", "z2", "z3"], "dekking": ["gedekt", "niet gedekt", "geen feit"]},
             {"id": "b", "zinnen": ["z4"], "dekking": ["gedekt"]}]
    with pytest.raises(ud.Weigering):
        ud.telling(rijen, {})
    t = ud.telling(rijen, {"a#2": "wel gedekt"})
    assert t == {"zinnen": 4, "geen feit": 1, "feitelijk": 3, "gedekt": 3, "niet gedekt": 0, "dekking": 1.0,
                 "eis (95%)": True}
    t2 = ud.telling(rijen, {"a#2": "niet gedekt"})
    assert t2["gedekt"] == 2 and t2["dekking"] == round(2 / 3, 4) and t2["eis (95%)"] is False
