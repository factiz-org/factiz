"""Materiaal per taal (P10 van fase 0, PLAN #32.0g, B47): wat een taal nodig heeft
om mee te doen, en de omzetting van de Duitse oordelen in zinsvorm."""

import pytest

from doublecheck import talen


def test_a_language_passes_only_with_300_true_100_known_and_100_fresh_false():
    genoeg = {"waar": 300, "onwaar_bekend": 100, "onwaar_vers": 100}
    assert talen.door(genoeg) == []
    assert talen.door({**genoeg, "onwaar_vers": 2}) == ["vers onwaar: 2 van de 100"]
    assert talen.door({"waar": 299, "onwaar_bekend": 99, "onwaar_vers": 0}) == [
        "waar: 299 van de 300", "bekend onwaar: 99 van de 100", "vers onwaar: 0 van de 100"]


def test_a_conversion_outside_the_seven_categories_counts_as_unknown():
    assert talen.lees_omzetting('{"oordeel": "onwaar", "waarom": "Falsch."}') == "onwaar"
    assert talen.lees_omzetting('{"oordeel": "fake", "waarom": "x"}') == "onbekend"
    assert talen.lees_omzetting("geen json") == "onbekend"
    assert talen.lees_omzetting('{"waarom": "x"}') == "onbekend"


def test_the_conversion_question_carries_the_claim_and_the_verdict_sentence():
    verzoek = talen.omzetverzoek("de-1", "Die Erde ist flach.", "Falsch. Die Erde ist rund.")
    vraag = verzoek["params"]["messages"][0]["content"]
    assert "Die Erde ist flach." in vraag and "Falsch. Die Erde ist rund." in vraag
    schema = verzoek["params"]["output_config"]["format"]["schema"]
    assert set(schema["properties"]["oordeel"]["enum"]) == set(talen.CATEGORIEEN)
    assert verzoek["params"]["model"] == "claude-haiku-5-5"


def test_the_sample_to_read_is_fixed_by_seed():
    rijen = [{"id": f"c{i}", "oordeel": "onwaar"} for i in range(500)]
    eerst = talen.steekproef(rijen)
    assert len(eerst) == 50 and eerst == talen.steekproef(list(reversed(rijen)))


def test_the_count_refuses_while_a_sampled_conversion_has_no_label():
    rijen = [{"id": f"c{i}", "oordeel": "onwaar"} for i in range(60)]
    labels = {r["id"]: "onwaar" for r in talen.steekproef(rijen)[:49]}
    with pytest.raises(talen.Weigering):
        talen.overeenstemming(rijen, labels)
    labels.update({r["id"]: "misleidend" for r in talen.steekproef(rijen)[49:]})
    assert talen.overeenstemming(rijen, labels) == {"gelezen": 50, "gelijk": 49, "verschil": 1}


def test_dutch_and_french_verdicts_get_their_own_question_and_file_and_german_keeps_its_own():
    """B63, #32.59: dpa en anderen schrijven ook in het Nederlands en Frans een zin in plaats van een label."""
    nl = talen.omzetverzoek("nl-1", "De aarde is plat.", "Nee, de aarde is rond.", taal="nl")
    tekst = nl["params"]["messages"][0]["content"]
    assert "Dutch" in tekst and "German" not in tekst and "Nee, de aarde is rond." in tekst
    de = talen.omzetverzoek("de-1", "Die Erde ist flach.", "Falsch.")
    assert de["params"]["messages"][0]["content"] == talen.OMZETVRAAG.format(claim="Die Erde ist flach.", oordeel="Falsch.")
    assert talen.omzetting_pad("de").name == "duits.jsonl" and talen.omzetting_pad("fr").name == "oordelen-fr.jsonl"
    assert talen.batches_pad("de").name == "batches.jsonl" and talen.batches_pad("nl").name == "batches-nl.jsonl"
    assert set(talen.OMZET_TALEN) == {"de", "nl", "fr"}
