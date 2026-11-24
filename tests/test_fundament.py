"""Ronde 1 van de koers (B45, PLAN #31.11 stap 2): de controle op de Engelse
zinnen over de vastgestelde feiten. De regels die vóór de eerste vraag vastlagen."""

import pytest

from doublecheck import fundament as f


def test_the_set_takes_only_the_reviewed_english_sentences_true_and_false():
    rijen = [{"id": "K0000", "deel": "K", "taal": "en", "feit": "apollo-11", "tekst": "a"},
             {"id": "K0002", "deel": "K", "taal": "es", "feit": "apollo-11", "tekst": "b"},
             {"id": "W000", "deel": "W", "taal": "en", "feit": "apollo-11", "tekst": "c"},
             {"id": "V3-000", "deel": "V3", "taal": "en", "feit": "apollo-11", "tekst": "d"},
             {"id": "O000", "deel": "O", "taal": "en", "feit": None, "tekst": "e"},
             {"id": "Dn-000", "deel": "Dn", "taal": "en", "feit": "apollo-11", "tekst": "f"}]
    gekozen = f.kies(rijen)
    assert [(s["id"], s["label"]) for s in gekozen] == [("K0000", "waar"), ("W000", "waar"), ("V3-000", "onwaar")]
    assert all(s["soort"] == "tekst" and s["eigen"] == [] for s in gekozen)


def _stuk(i, deel, label, feit="apollo-11"):
    return {"id": i, "deel": deel, "label": label, "feit": feit}


def test_a_false_sentence_counts_as_recognised_with_any_source_and_anything_else_is_read():
    stukken = [_stuk("V000", "V", "onwaar"), _stuk("V001", "V", "onwaar"), _stuk("V002", "V", "onwaar")]
    antwoorden = {"V000": {"oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "x"}]},
                  "V001": {"oordeel": "let op", "bronnen": []},
                  "V002": {"oordeel": "klopt", "bronnen": []}}
    with pytest.raises(f.Weigering):
        f.telling(stukken, antwoorden, {}, {("V001", "let op"): "terecht"}, {})
    t = f.telling(stukken, antwoorden, {}, {("V001", "let op"): "terecht", ("V002", "klopt"): "vals"},
                  {"V000": "past"})
    assert t["onwaar"]["herkend"] == 2 and t["onwaar"]["klopt vals"] == 1


def test_a_true_sentence_made_red_needs_a_label_and_counts_against_the_bar():
    stukken = [_stuk("K0000", "K", "waar"), _stuk("W000", "W", "waar")]
    antwoorden = {"K0000": {"oordeel": "klopt", "bronnen": []},
                  "W000": {"oordeel": "let op", "bronnen": []}}
    with pytest.raises(f.Weigering):
        f.telling(stukken, antwoorden, {}, {}, {})
    t = f.telling(stukken, antwoorden, {}, {("W000", "let op"): "vals"}, {})
    assert t["waar"]["onterecht rood"] == 1 and t["waar"]["klopt niet vals"] == 0
    assert t["latten"]["ware zinnen nooit klopt niet"] is True
    assert t["eis B45"]["gehaald"] == "onder 97%"  # 1 van 2


def test_the_bar_of_b45_is_at_most_3_6_or_9_red_of_300_true_messages():
    assert f.eis_b45(3, 300) == "99%"
    assert f.eis_b45(4, 300) == "98%" and f.eis_b45(6, 300) == "98%"
    assert f.eis_b45(7, 300) == "97%" and f.eis_b45(9, 300) == "97%"
    assert f.eis_b45(10, 300) == "onder 97%"
    assert f.eis_b45(3, 350) == "99%" and f.eis_b45(4, 350) == "98%"


def test_a_10_on_the_own_fact_of_a_core_sentence_is_good_and_any_other_10_is_read():
    stukken = [_stuk("K0000", "K", "waar"), _stuk("W000", "W", "waar")]
    antwoorden = {i: {"oordeel": "klopt", "bronnen": []} for i in ("K0000", "W000")}
    standen = {"K0000": {"stand": 10, "feit": "apollo-11"}, "W000": {"stand": 10, "feit": "apollo-11"}}
    with pytest.raises(f.Weigering):
        f.telling(stukken, antwoorden, standen, {}, {})
    t = f.telling(stukken, antwoorden, standen, {("W000", 10, "apollo-11"): "fout"}, {})
    assert t["waar"]["op 10"] == 2
    assert t["latten"]["geen verkeerde 10"] is False


def test_a_source_that_does_not_fit_in_the_sample_makes_every_recognised_sentence_need_a_label():
    stukken = [_stuk(f"V{i:03d}", "V", "onwaar") for i in range(3)]
    antwoorden = {s["id"]: {"oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "x"}]} for s in stukken}
    with pytest.raises(f.Weigering):
        f.telling(stukken, antwoorden, {}, {}, {"V000": "past niet"})
    t = f.telling(stukken, antwoorden, {}, {("V000", "klopt niet"): "bewijst niet", ("V001", "klopt niet"): "bewijst",
                                            ("V002", "klopt niet"): "bewijst"}, {"V000": "past niet"})
    assert t["onwaar"]["herkend"] == 2


def test_the_sample_of_sources_is_fixed_by_seed_and_waits_for_its_labels():
    stukken = [_stuk(f"V{i:03d}", "V", "onwaar") for i in range(30)]
    antwoorden = {s["id"]: {"oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "x"}]} for s in stukken}
    proef = f.steekproef(stukken, antwoorden)
    assert proef == f.steekproef(stukken, antwoorden) and len(proef) == f.N_STEEKPROEF
    with pytest.raises(f.Weigering):
        f.telling(stukken, antwoorden, {}, {}, {})


def test_red_on_the_scale_is_counted_from_the_stand_not_from_the_verdict():
    stukken = [_stuk("V000", "V", "onwaar"), _stuk("V001", "V", "onwaar")]
    antwoorden = {"V000": {"oordeel": "let op", "bronnen": []}, "V001": {"oordeel": "let op", "bronnen": []}}
    standen = {"V000": {"stand": 5}, "V001": {"stand": 3}}
    t = f.telling(stukken, antwoorden, standen, {("V000", "let op"): "terecht", ("V001", "let op"): "terecht"}, {})
    assert t["onwaar"]["herkend"] == 2 and t["onwaar"]["rood op de schaal"] == 1


def test_the_random_choice_is_fixed_by_seed_and_skips_what_was_already_asked():
    stukken = [_stuk(f"K{i:04d}", "K", "waar") for i in range(20)] + [_stuk(f"V{i:03d}", "V", "onwaar") for i in range(20)]
    gekozen = f.kies_willekeurig(stukken, {"K0000", "V000"}, 5, 6)
    assert gekozen == f.kies_willekeurig(stukken, {"K0000", "V000"}, 5, 6)
    assert sum(s["label"] == "waar" for s in gekozen) == 5 and sum(s["label"] == "onwaar" for s in gekozen) == 6
    assert not {"K0000", "V000"} & {s["id"] for s in gekozen}


def test_the_random_part_is_also_counted_apart_from_the_trial():
    stukken = [{**_stuk("K0000", "K", "waar"), "groep": "proef"}, {**_stuk("K0001", "K", "waar"), "groep": "willekeurig"}]
    antwoorden = {i: {"oordeel": "klopt", "bronnen": []} for i in ("K0000", "K0001")}
    t = f.telling(stukken, antwoorden, {}, {}, {})
    assert t["waar"]["n"] == 2 and t["waar willekeurig"]["n"] == 1


def test_a_source_that_proves_it_only_indirectly_counts_as_recognised_but_apart():
    stukken = [_stuk("V000", "V", "onwaar"), _stuk("V001", "V", "onwaar")]
    antwoorden = {s["id"]: {"oordeel": "klopt niet", "bronnen": [{"soort": "geheugen", "claim": "c"}]} for s in stukken}
    labels = {("V000", "klopt niet"): "bewijst indirect", ("V001", "klopt niet"): "bewijst"}
    t = f.telling(stukken, antwoorden, {}, labels, {"V000": "past niet"})
    assert t["onwaar"]["herkend"] == 2 and t["onwaar"]["bron indirect"] == 1
