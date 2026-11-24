"""Een standaardmodel door dezelfde zeef (PLAN #30.1c, B33): dezelfde berg,
dezelfde telling, een vaste vraag per stuk, en geen geld voordat de PO het
bedrag goedkeurde.
"""

import pytest

from doublecheck import standaardmodel as sm


def test_the_question_is_fixed_versioned_and_offers_four_answers():
    v = sm.verzoek({"id": "P1-1", "tekst": "Vaccines cause autism."}, "haiku")
    tekst = v["params"]["messages"][0]["content"][-1]["text"]
    assert "Vaccines cause autism." in tekst
    assert v["params"]["model"] == sm.MODELLEN["haiku"]["id"]
    assert set(sm.ANTWOORDEN) == {"onwaar", "deels-waar", "waar", "onbekend"}
    assert sm.VRAAG in tekst and sm.PROMPTVERSIE


def test_an_image_is_sent_as_an_image_block_and_never_written_elsewhere(tmp_path):
    beeld = tmp_path / "00001.jpg"
    beeld.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
    v = sm.verzoek({"id": "P3-1", "beeld": str(beeld)}, "opus")
    blokken = v["params"]["messages"][0]["content"]
    assert blokken[0]["type"] == "image" and blokken[0]["source"]["type"] == "base64"


@pytest.mark.parametrize("set_, verwacht, antwoord, uitkomst", [
    ("P1", "rood", "onwaar", "gevonden"),
    ("P1", "groen", "waar", "gevonden"),
    ("P1", "rood", "waar", "fout"),
    ("P2", "rood", "onbekend", "niets"),
    ("N1", None, "onwaar", "vals"),
    ("N1", None, "onbekend", "niets"),
    ("N3", None, "onwaar", "vals"),
    ("N3", None, "waar", "goed"),
])
def test_the_model_is_scored_like_factiz(set_, verwacht, antwoord, uitkomst):
    assert sm.uitkomst(set_, verwacht, antwoord) == uitkomst


def test_the_cost_plan_counts_tokens_per_model():
    items = [{"id": "a", "tekst": "x" * 400}, {"id": "b", "beeld": "y.jpg"}]
    haiku, opus = sm.kosten(items, "haiku"), sm.kosten(items, "opus")
    assert 0 < haiku < opus


def test_the_comparison_counts_recall_false_alarms_precision_and_recent_checks():
    items = [
        {"id": "a", "set": "P1", "helft": "toets", "verwacht": "rood", "datum": "2026-08-01"},
        {"id": "b", "set": "P1", "helft": "toets", "verwacht": "rood", "datum": "2025-01-01"},
        {"id": "c", "set": "P1", "helft": "toets", "verwacht": None},
        {"id": "d", "set": "N1", "helft": "toets"},
        {"id": "e", "set": "N3", "helft": "toets"},
    ]
    antwoorden = {"a": "onbekend", "b": "onwaar", "c": "onwaar", "d": "onwaar", "e": "waar"}
    v = sm.vergelijking(items, antwoorden)["toets"]
    assert v["P1"]["n"] == 2 and v["P1"]["gevonden"] == 1 and v["P1"]["zonder_kant"] == 1
    assert v["P1_recent"]["n"] == 1 and v["P1_recent"]["gevonden"] == 0
    assert v["N1"]["vals"] == 1 and v["N3"]["goed"] == 1
    assert v["precisie"]["stellig"] == 3 and v["precisie"]["fout"] == 1
