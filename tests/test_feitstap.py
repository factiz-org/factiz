"""De feitenstap vóór de waarheidsmeter (B44, PLAN #31.9): de regels die vóór de meting vastlagen."""

import numpy as np
import pytest

from doublecheck import feitstap


def _index():
    zinnen = [("a", "fact a"), ("a", "fact a again"), ("b", "fact b"), ("c", "fact c")]
    m = np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    return zinnen, m / np.linalg.norm(m, axis=1, keepdims=True)


def test_retrieval_gives_each_fact_once_above_the_floor_best_first():
    v = np.array([0.95, 0.3, 0.05])
    kandidaten = feitstap.kandidaten(v / np.linalg.norm(v), _index(), vloer=0.2, n=3)
    assert [f for f, _ in kandidaten] == ["a", "b"]
    assert kandidaten[0][1] > kandidaten[1][1]


def test_nothing_above_the_floor_means_no_question_to_the_model():
    v = np.array([0.0, 0.0, 1.0])
    assert feitstap.kandidaten(v, _index(), vloer=0.99, n=3) == [("c", pytest.approx(1.0))]
    assert feitstap.kandidaten(np.array([0.577, 0.577, 0.577]), _index(), vloer=0.99, n=3) == []


def test_the_answer_is_read_strictly_and_anything_else_is_no_link():
    assert feitstap.lees_feitoordeel('{"richting": "bevestigt", "feit": "V2"}', 3) == ("bevestigt", 2)
    assert feitstap.lees_feitoordeel('{"richting": "spreekt tegen", "feit": "V1"}', 3) == ("spreekt tegen", 1)
    assert feitstap.lees_feitoordeel('{"richting": "bevestigt", "feit": "V4"}', 3) == ("geen", None)
    assert feitstap.lees_feitoordeel('{"richting": "misschien", "feit": "V1"}', 3) == ("geen", None)
    assert feitstap.lees_feitoordeel('{"richting": "geen", "feit": ""}', 3) == ("geen", None)
    assert feitstap.lees_feitoordeel("x", 3) == ("geen", None)
    assert [feitstap.stand_van(r) for r in ("bevestigt", "spreekt tegen", "geen")] == [10, 0, None]


def test_the_question_names_the_facts_as_v_numbers_and_never_counts_a_lead_in_as_the_claim():
    vraag = feitstap.vraag("The Earth is flat.", [("earth-round", "The Earth is round.")])
    assert "[V1] The Earth is round." in vraag and "Message:\nThe Earth is flat." in vraag
    assert "lead-in" in vraag and "date, place, actor or number" in vraag


def _set():
    return [{"id": "K1", "deel": "K", "feit": "a"}, {"id": "K2", "deel": "K", "feit": "a"},
            {"id": "V1", "deel": "V", "feit": "a"}, {"id": "O1", "deel": "O", "feit": None},
            {"id": "W1", "deel": "W", "feit": "a"}]


def test_the_count_refuses_while_a_0_or_10_or_a_missed_core_formulation_is_unread():
    antwoorden = {"K1": {"richting": "bevestigt", "feit": "a"}, "K2": {"richting": "geen", "feit": None},
                  "V1": {"richting": "spreekt tegen", "feit": "a"}, "O1": {"richting": "geen", "feit": None},
                  "W1": {"richting": "bevestigt", "feit": "a"}}
    with pytest.raises(feitstap.Weigering):
        feitstap.telling(_set(), antwoorden, {"V1": "terecht", "W1": "fout"})
    t = feitstap.telling(_set(), antwoorden, {"K2": "fout", "V1": "terecht", "W1": "fout"})
    assert t["totaal"]["fouten"] == 2
    assert t["K"] == {"n": 2, "op 10": 1, "op 0": 0, "fouten": 1, "set fout": 0}
    assert t["V"]["op 0"] == 1 and t["V"]["fouten"] == 0


def test_a_core_formulation_on_10_counts_only_at_its_own_fact():
    antwoorden = {"K1": {"richting": "bevestigt", "feit": "b"}}
    t = feitstap.telling(_set()[:1], antwoorden, {"K1": "fout"})
    assert t["K"]["fouten"] == 1
    with pytest.raises(feitstap.Weigering):
        feitstap.telling(_set()[:1], antwoorden, {})


def test_an_item_the_set_got_wrong_is_reported_apart_not_counted():
    antwoorden = {"V1": {"richting": "bevestigt", "feit": "a"}}
    t = feitstap.telling([_set()[2]], antwoorden, {"V1": "set fout"})
    assert t["V"]["fouten"] == 0 and t["V"]["set fout"] == 1 and t["V"]["n"] == 0


# --- feitstap-v2 (PLAN #31.9, akkoord PO 2026-10-26) -------------------------------------

def test_v2_has_the_lower_floor_its_own_budget_and_its_own_files():
    v1, v2 = feitstap.VERSIES["v1"], feitstap.VERSIES["v2"]
    assert (v1["vloer"], v2["vloer"]) == (0.60, 0.55)
    assert v2["budget"] == 3.0
    assert len({v1["uit"], v2["uit"]}) == 2 and len({v1["labels"], v2["labels"]}) == 2


def test_v2_never_confirms_a_message_that_adds_its_own_detail():
    vraag = feitstap.vraag("Apollo 11 landed on 20 July 1969; the first step was at 20:56 UTC.",
                           [("apollo-11", "On 20 July 1969 Apollo 11 landed on the Moon.")],
                           feitstap.VERSIES["v2"]["vraag"])
    assert "concrete detail that the fact does not state" in vraag
    assert "lead-in" in vraag and "date, place, actor or number" in vraag
    assert "not on your own knowledge" in vraag  # na de proef: 0 alleen op wat het feit zelf zegt
    assert "concrete detail that the fact does not state" not in feitstap.vraag("x", [("a", "y")])


def test_the_new_sentences_get_their_part_and_language_by_position():
    rij = {"feit": "a", "kern": [f"k{i}" for i in range(8)], "vals_en": ["v1", "v2", "v3", "v4"],
           "vals_anders": ["x1", "x2"], "detail_waar": ["dw1", "dw2"], "detail_vals": ["dn1", "dn2"]}
    zinnen = feitstap.zinnen_v2([rij], {"a": 0})
    per_deel = {d: [z for z in zinnen if z["deel"] == d] for d in ("K2", "V2", "Dw", "Dn")}
    assert [len(per_deel[d]) for d in ("K2", "V2", "Dw", "Dn")] == [8, 6, 2, 2]
    assert [z["taal"] for z in per_deel["K2"]] == ["en", "en", "es", "pt", "it", "tr", "id", "ar"]
    assert [z["taal"] for z in per_deel["V2"]][4:] == list(feitstap.taal_voor(1))
    assert len({z["id"] for z in zinnen}) == len(zinnen) and all(z["feit"] == "a" for z in zinnen)


def test_a_true_detail_on_10_is_reported_but_on_0_needs_a_label():
    stukken = [{"id": "Dw1", "deel": "Dw", "feit": "a"}, {"id": "Dw2", "deel": "Dw", "feit": "a"},
               {"id": "K2-1", "deel": "K2", "feit": "a"}]
    antwoorden = {"Dw1": {"richting": "bevestigt", "feit": "a"}, "Dw2": {"richting": "spreekt tegen", "feit": "a"},
                  "K2-1": {"richting": "geen", "feit": None}}
    with pytest.raises(feitstap.Weigering):
        feitstap.telling(stukken, antwoorden, {"K2-1": "fout"})
    t = feitstap.telling(stukken, antwoorden, {"Dw2": "fout", "K2-1": "fout"})
    assert t["Dw"] == {"n": 2, "op 10": 1, "op 0": 1, "fouten": 1, "set fout": 0}
    assert t["K2"]["fouten"] == 1


def test_an_outcome_equal_to_v1_keeps_its_v1_label_and_a_new_outcome_does_not(tmp_path):
    import json

    v2, v1 = tmp_path / "v2.json", tmp_path / "v1.json"
    v1.write_text(json.dumps({"labels": [{"id": "V1", "stand": 0, "feit": "a", "label": "terecht"},
                                         {"id": "W1", "stand": 10, "feit": "a", "label": "fout"}]}))
    v2.write_text(json.dumps({"labels": [{"id": "V1", "stand": 0, "feit": "a", "label": "set fout"}]}))
    antwoorden = {"V1": {"richting": "spreekt tegen", "feit": "a"}, "W1": {"richting": "spreekt tegen", "feit": "a"}}
    assert feitstap.labels_voor(antwoorden, (v2, v1)) == {"V1": "set fout"}


def test_spending_is_counted_per_version(tmp_path):
    (tmp_path / "batches.jsonl").write_text('{"schatting": 0.5, "werkelijk": 0.3}\n{"schatting": 0.2}\n')
    assert feitstap.al_uitgegeven(tmp_path) == pytest.approx(0.5)
    assert feitstap.al_uitgegeven(tmp_path / "leeg") == 0


# --- feitstap-v3: twee sleutels (PLAN #31.9, akkoord PO 2026-10-26) ----------------------

def test_two_keys_give_0_or_10_only_when_both_agree_on_direction_and_fact():
    a = {"x": {"richting": "bevestigt", "feit": "f"}, "y": {"richting": "spreekt tegen", "feit": "f"},
         "z": {"richting": "spreekt tegen", "feit": "f"}, "w": {"richting": "bevestigt", "feit": "f"}}
    b = {"x": {"richting": "bevestigt", "feit": "f"}, "y": {"richting": "geen", "feit": None},
         "z": {"richting": "spreekt tegen", "feit": "g"}}
    twee = feitstap.twee_sleutels(a, b)
    assert twee["x"]["richting"] == "bevestigt" and twee["x"]["feit"] == "f"
    assert all(twee[i] == {"richting": "geen", "feit": None} for i in ("y", "z", "w"))


def test_key_b_turns_the_facts_around_and_asks_the_reason_in_english():
    v3 = feitstap.VERSIES["v3"]
    assert v3["vraag"] == feitstap.VERSIES["v2"]["vraag"]
    assert "one short English sentence" in v3["vraag_b"] and "Dutch" not in v3["vraag_b"]
    kandidaten = [["a", 0.9], ["b", 0.7], ["c", 0.6]]
    assert feitstap.volgorde(kandidaten, "A") == ["a", "b", "c"]
    assert feitstap.volgorde(kandidaten, "B") == ["c", "b", "a"]


def test_a_request_id_carries_its_key_and_comes_back_whole():
    assert feitstap.verzoek_id("K2-001", "B") == "K2-001__B"
    assert feitstap.uit_verzoek_id("K2-001__B") == ("K2-001", "B")
    assert feitstap.uit_verzoek_id("Pw016__A") == ("Pw016", "A")


def test_a_missed_ten_counts_apart_without_a_label_and_a_wrong_0_still_needs_one():
    stukken = [{"id": "K3-1", "deel": "K3", "feit": "a"}, {"id": "K3-2", "deel": "K3", "feit": "a"},
               {"id": "K3-3", "deel": "K3", "feit": "a"}, {"id": "W3-1", "deel": "W3", "feit": "a"}]
    antwoorden = {"K3-1": {"richting": "bevestigt", "feit": "a"}, "K3-2": {"richting": "geen", "feit": None},
                  "K3-3": {"richting": "spreekt tegen", "feit": "a"}, "W3-1": {"richting": "geen", "feit": None}}
    with pytest.raises(feitstap.Weigering):
        feitstap.telling(stukken, antwoorden, {}, missers_apart=True)
    t = feitstap.telling(stukken, antwoorden, {"K3-3": "fout"}, missers_apart=True)
    assert t["K3"] == {"n": 3, "op 10": 1, "op 0": 1, "fouten": 1, "set fout": 0, "gemist": 1}
    assert t["W3"]["fouten"] == 0 and t["totaal"]["gemist"] == 1


def test_the_new_v3_sentences_get_their_part_and_language_by_position():
    rij = {"feit": "a", "kern": [f"k{i}" for i in range(8)], "vals_en": ["v1", "v2", "v3", "v4"],
           "vals_anders": ["x1", "x2"], "waar": ["w1", "w2", "w3"], "detail_waar": ["dw1", "dw2"],
           "detail_vals": ["dn1", "dn2"]}
    zinnen = feitstap.nieuwe_zinnen([rij], {"a": 0}, "v3")
    per_deel = {d: [z for z in zinnen if z["deel"] == d] for d in ("K3", "V3", "W3", "Dw3", "Dn3")}
    assert [len(per_deel[d]) for d in per_deel] == [8, 6, 3, 2, 2]
    assert [z["taal"] for z in per_deel["W3"]] == ["en", "en", feitstap.taal_voor(2)[0]]
    assert [z["taal"] for z in per_deel["V3"]][4:] == list(feitstap.taal_voor(2))
    assert feitstap.nieuwe_zinnen([rij], {"a": 0}, "v2")[0]["deel"] == "K2"
