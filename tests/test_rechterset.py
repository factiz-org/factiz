"""De rechterset (PLAN #30.3): lesstof en meetstof voor de rechter, met het
label vooraf bepaald, en nooit lesstof van de toetshelft van de zeef.
"""

import pytest

from doublecheck import rechterset as rs


def test_each_generated_variant_carries_its_label_by_construction():
    antwoord = {"parafrase": "Russia annexed the Crimean peninsula in 2014.",
                "vertaling": "Rusland annexeerde de Krim in 2014.",
                "rolwissel": "Ukraine annexed Crimea from Russia in 2014.",
                "getal": "Russia annexed Crimea in 2016.",
                "ontkenning": "Russia did not annex Crimea in 2014."}
    paren = rs.paren_uit_varianten({"claim_id": "c1", "tekst": "Russia annexed Crimea in 2014.", "taal": "en"},
                                   antwoord)
    labels = {p["soort"]: p["label"] for p in paren}
    assert labels == {"parafrase": "zelfde", "vertaling": "zelfde", "rolwissel": "verwant",
                      "getal": "verwant", "ontkenning": "tegenspraak"}
    assert all(p["kandidaat"] == "Russia annexed Crimea in 2014." for p in paren if p["richting"] == "heen")
    assert paren[0]["vraag"] == antwoord["parafrase"]


def test_an_empty_or_unchanged_variant_is_dropped():
    antwoord = {"parafrase": "", "vertaling": "x", "rolwissel": "Same claim.", "getal": "Other 2016.",
                "ontkenning": "Not so."}
    paren = rs.paren_uit_varianten({"claim_id": "c1", "tekst": "Same claim.", "taal": "en"}, antwoord)
    assert {p["soort"] for p in paren} == {"vertaling", "getal", "ontkenning"}


def test_claims_on_the_test_half_of_the_zeef_are_never_teaching_material():
    from doublecheck.zeef import helft

    for i in range(200):
        claim = f"gfc-{i:016x}"
        assert rs.rol(claim) == ("meten" if helft(f"zaak:{claim}") == "toets" else "leren")


@pytest.mark.parametrize("label, verwacht", [
    ("stijl", "zelfde"), ("vervalsing", "verwant"), ("standpunt", "verwant"), ("vandalisme", "verwant"),
    ("toevoeging", None),
])
def test_minimal_pairs_become_judge_pairs_by_their_reading_label(label, verwacht):
    assert rs.label_minimaal_paar(label) == verwacht


def test_the_request_asks_for_five_variants_in_a_fixed_schema():
    v = rs.verzoek({"claim_id": "c1", "tekst": "Japan attacked Pearl Harbor in 1941.", "taal": "en"})
    assert v["custom_id"] == "c1"
    assert set(rs.SOORTEN) == {"parafrase", "vertaling", "rolwissel", "getal", "ontkenning"}
    schema = v["params"]["output_config"]["format"]["schema"]
    assert set(schema["required"]) == set(rs.SOORTEN)


@pytest.mark.parametrize("label, verwacht", [("onterecht", "zelfde"), ("terecht", "verwant"), ("twijfel", None)])
def test_veto_labels_become_judge_pairs_and_doubt_stays_out(label, verwacht):
    assert rs.label_veto(label) == verwacht


def test_a_real_pair_is_measurement_as_soon_as_one_claim_is_on_the_test_half():
    from doublecheck.zeef import helft

    claims = [f"gfc-{i:016x}" for i in range(400)]
    toets = next(c for c in claims if helft(f"zaak:{c}") == "toets")
    ontwikkel = [c for c in claims if helft(f"zaak:{c}") == "ontwikkel"][:2]
    assert rs.rol(toets, ontwikkel[0]) == "meten"
    assert rs.rol(*ontwikkel) == "leren"


def test_the_kern_is_never_teaching_material():
    paren = rs.kernparen([{"id": "apollo-11", "formuleringen": [
        {"taal": "en", "tekst": "Neil Armstrong walked on the Moon on 20 July 1969."},
        {"taal": "nl", "tekst": "Neil Armstrong liep op 20 juli 1969 op de maan."}]}],
        [{"feit": "apollo-11", "index": 0, "kandidaat": "gfc-1", "label": "verwant"}],
        {"gfc-1": "Neil Armstrong reached the moon on 17 July 1969."})
    assert len(paren) == 1 and paren[0]["label"] == "verwant" and paren[0]["rol"] == "meten"
    assert paren[0]["vraag"].startswith("Neil Armstrong walked")


def test_the_labels_are_the_four_answers_of_the_preregistered_question():
    assert set(rs.LABEL.values()) <= set(rs.ANTWOORDEN)
    assert rs.ANTWOORDEN == ("zelfde", "verwant", "anders", "tegenspraak")


@pytest.mark.parametrize("claim, variant, blijft", [
    ("Sanctions are hurting the European economy.", "Sanctions are hurting the European economy in 2023.", False),
    ("The BSP will release a P500 banknote.", "The BSP will release a P1000 banknote.", True),
    ("Tamiflu cures the flu.", "Relenza cures the flu.", True),
    ("තේ බොන්න එපා", "තේ බොන්න එපා දැන්", False),
    ("पानी पीने से कैंसर होता है", "दूध पीने से कैंसर होता है", True),
    ("पानी पीने से कैंसर होता है", "पानी पीने से कैंसर नहीं होता है", False),
])
def test_a_role_or_number_variant_that_only_adds_words_is_not_a_different_claim(claim, variant, blijft):
    antwoord = {"parafrase": "", "vertaling": "", "rolwissel": "", "getal": variant, "ontkenning": ""}
    paren = rs.paren_uit_varianten({"claim_id": "c1", "tekst": claim, "taal": "xx"}, antwoord)
    assert bool(paren) is blijft


def test_the_reading_sample_does_not_shift_when_pairs_are_added():
    paren = [{"vraag": f"v{i}", "kandidaat": "k"} for i in range(1000)]
    eerst = rs.leesproef(paren, 20)
    erbij = rs.leesproef(paren + [{"vraag": f"w{i}", "kandidaat": "k"} for i in range(50)], 20)
    assert len(eerst) == 20 and len({rs.paarsleutel(p) for p in eerst} - {rs.paarsleutel(p) for p in erbij}) <= 3


def test_a_reordering_with_the_same_meaning_is_the_same_claim():
    claim = {"claim_id": "c1", "tekst": "In April 2014 Ukraine launched an operation in Donetsk.", "taal": "en"}
    paren = rs.paren_uit_varianten(claim, {"herschikking": "Ukraine launched an operation in Donetsk in April 2014."},
                                   prompt=rs.RONDES["herschikking"]["versie"])
    assert {(p["soort"], p["label"], p["prompt"]) for p in paren} == {
        ("herschikking", "zelfde", "rechterset-v3-herschikking")}


def test_the_reordering_round_asks_only_for_the_reordering():
    v = rs.verzoek({"claim_id": "c1", "tekst": "x y z", "taal": "en"}, ronde="herschikking")
    assert v["params"]["output_config"]["format"]["schema"]["required"] == ["herschikking"]
    assert "rolwissel" not in v["params"]["messages"][0]["content"]


def test_across_languages_a_different_charge_is_related_and_the_negation_contradicts():
    claim = {"claim_id": "c1", "tekst": "Russia annexed Crimea in 2014.", "taal": "en"}
    paren = rs.paren_uit_varianten(claim, {"lading": "En 2014, Crimea decidió unirse a Rusia.",
                                           "ontkenning_vertaald": "Rusia no se anexionó Crimea en 2014."},
                                   prompt=rs.RONDES["taalgrens"]["versie"])
    assert {p["soort"]: p["label"] for p in paren} == {"lading": "verwant", "ontkenning_vertaald": "tegenspraak"}


def test_the_language_border_round_writes_in_another_language():
    v = rs.verzoek({"claim_id": "c1", "tekst": "x y z", "taal": "en"}, ronde="taalgrens")
    assert v["params"]["output_config"]["format"]["schema"]["required"] == ["lading", "ontkenning_vertaald"]
    assert "Spanish" in v["params"]["messages"][0]["content"]


def test_every_pair_is_taught_in_both_directions():
    claim = {"claim_id": "c1", "tekst": "Russia annexed Crimea in 2014.", "taal": "en"}
    paren = rs.paren_uit_varianten(claim, {"parafrase": "In 2014 Russia annexed Crimea.",
                                           "rolwissel": "Ukraine annexed Crimea in 2014.",
                                           "ontkenning": "Russia did not annex Crimea in 2014."})
    richtingen = {(p["soort"], p["richting"]) for p in paren}
    assert richtingen == {(s, r) for s in ("parafrase", "rolwissel", "ontkenning") for r in ("heen", "om")}
    om = next(p for p in paren if p["soort"] == "rolwissel" and p["richting"] == "om")
    assert om["vraag"] == claim["tekst"] and om["kandidaat"] == "Ukraine annexed Crimea in 2014."


def test_an_added_contested_assertion_is_a_different_claim_even_though_it_only_adds():
    claim = {"claim_id": "c1", "tekst": "In March 2014 Crimea was annexed by Russia.", "taal": "en"}
    variant = "In March 2014 Crimea was annexed by Russia after a referendum held in accordance with international law."
    paren = rs.paren_uit_varianten(claim, {"toevoeging": variant}, prompt=rs.RONDES["toevoeging"]["versie"])
    assert [(p["label"], p["vraag"], p["kandidaat"]) for p in paren] == [("verwant", claim["tekst"], variant)]


def test_a_text_that_makes_the_claim_and_more_is_not_taught_as_a_different_claim():
    # Een artikel dat de claim doet plus meer, hoort bij de check van die claim (BENCHMARK §127):
    # de toevoeging gaat alleen in de richting vraag = de claim, kandidaat = de claim plus de toevoeging.
    claim = {"claim_id": "c1", "tekst": "Zelensky banned the church in Ukraine.", "taal": "en"}
    variant = "Zelensky banned the church in Ukraine on orders from foreign intelligence."
    paren = rs.paren_uit_varianten(claim, {"toevoeging": variant}, prompt=rs.RONDES["toevoeging"]["versie"])
    assert not any(p["vraag"] == variant for p in paren)


def test_the_claim_list_only_grows_so_earlier_answers_keep_their_claim(tmp_path):
    eerst = [{"claim_id": "a", "tekst": "x", "taal": "en"}]
    erbij = [{"claim_id": "a", "tekst": "x", "taal": "en"}, {"claim_id": "b", "tekst": "y", "taal": "nl"}]
    assert [c["claim_id"] for c in rs.samen(eerst, erbij)] == ["a", "b"]
