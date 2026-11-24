"""Het proefdossier (PLAN #32.70): wat er ligt ordenen in een dossier (thema), verhaallijnen en cases."""

import json

import numpy as np
import pytest

from doublecheck import dossier as ds

THEMA = "oekraine-rusland"


@pytest.mark.parametrize("tekst", [
    "Zelensky bought a villa in Florida",
    "The US runs secret biolabs in UKRAINE",
    "Украина продала зерно, заявил Путин",
    "В Україні нібито закрили всі церкви",
    "La OTAN prometió no expandirse hacia el este",
    "De Oekraïense president zou een jacht hebben gekocht",
    "A Ucrânia vendeu armas ao Hamas",
    "Das Kreml-Dementi zur Mobilmachung",
])
def test_a_claim_belongs_to_the_theme_by_a_keyword_in_its_own_script(tekst):
    assert ds.hoort_bij(tekst, THEMA)


@pytest.mark.parametrize("tekst", ["Vaccines cause autism", "El aceite de oliva cura el cáncer", "", "Senator voted no"])
def test_a_claim_without_a_keyword_stays_outside_the_theme(tekst):
    assert not ds.hoort_bij(tekst, THEMA)


def test_an_unknown_theme_is_an_error_and_not_an_empty_dossier():
    with pytest.raises(KeyError):
        ds.hoort_bij("Ukraine", "bestaat-niet")


def test_the_question_shows_the_claim_and_the_theme_and_asks_for_fixed_json():
    from doublecheck.modellen import MODELLEN

    p = ds.verhaalverzoek("Украина продала зерно", "ru", THEMA)
    assert p["model"] == MODELLEN["haiku"]["id"]
    tekst = p["messages"][0]["content"][0]["text"]
    assert "Украина продала зерно" in tekst and "(ru)" in tekst
    assert ds.THEMAS[THEMA]["omschrijving"] in p["system"]
    schema = p["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"past", "verhaallijn"} and schema["additionalProperties"] is False
    # Haiku 5.5 denkt eerst, en dat telt mee in de grens van de uitvoer: met een lage grens blijft het antwoord leeg
    assert p["max_tokens"] >= 2000


def test_an_answer_outside_the_schema_is_doubt_and_a_claim_outside_the_theme_has_no_storyline():
    goed = ds.lees_verhaal(json.dumps({"past": True, "verhaallijn": "  The US runs secret\n biolabs in Ukraine. "}))
    assert goed == {"past": True, "verhaallijn": "The US runs secret biolabs in Ukraine."}
    assert ds.lees_verhaal(json.dumps({"past": False, "verhaallijn": "Something else"})) == {"past": False,
                                                                                             "verhaallijn": ""}
    # twijfel versoepelt nooit: een antwoord dat niet te lezen is, zet een bewering nergens bij
    twijfel = {"past": None, "verhaallijn": ""}
    assert ds.lees_verhaal("kapot") == twijfel and ds.lees_verhaal(None) == twijfel
    assert ds.lees_verhaal(json.dumps({"past": "ja", "verhaallijn": "x"})) == twijfel
    assert ds.lees_verhaal(json.dumps({"past": True, "verhaallijn": "  "})) == twijfel
    assert ds.lees_verhaal(json.dumps(["past"])) == twijfel


def test_storylines_are_the_connected_sentences_and_come_largest_first_with_the_most_central_as_name():
    # drie zinnen die op elkaar lijken, twee andere die op elkaar lijken, één losse
    v = np.array([[1, 0, 0], [0.98, 0.2, 0], [0.97, 0, 0.24], [0, 1, 0], [0, 0.99, 0.14], [0, 0, 1]], dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    zinnen = ["biolabs a", "biolabs b", "biolabs c", "nato a", "nato b", "los"]
    lijnen = ds.verhaallijnen(zinnen, v, drempel=0.9)
    assert [l["leden"] for l in lijnen] == [[0, 1, 2], [3, 4], [5]]
    assert lijnen[0]["naam"] == "biolabs a" and lijnen[2]["naam"] == "los"


def test_a_storyline_counts_its_cases_checks_languages_newsrooms_and_years():
    rijen = [{"taal": "en", "checks": [{"redactie": "Snopes", "datum": "2022-03-01", "oordeel": "onwaar"},
                                       {"redactie": "AFP", "datum": "2022-03-04", "oordeel": "onwaar"}]},
             {"taal": "es", "checks": [{"redactie": "Maldita", "datum": "2018-09-11", "oordeel": "onwaar"}]},
             {"taal": "en", "checks": [{"redactie": "Snopes", "datum": "", "oordeel": "misleidend"}]}]
    assert ds.samenvatting(rijen) == {"cases": 3, "checks": 4, "talen": ["en", "es"], "redacties": 3,
                                      "jaren": ["2018", "2022"], "oordelen": {"onwaar": 3, "misleidend": 1}}


def test_a_test_story_reports_how_many_of_its_claims_share_the_largest_storyline():
    rijen = [{"tekst": "US biolabs in Ukraine"}, {"tekst": "A biological laboratory in Tbilisi"},
             {"tekst": "Biolab birds"}, {"tekst": "Zelensky villa"}, {"tekst": "biolabs again"}]
    lijn_van = {0: 7, 1: 7, 2: 9, 3: 7, 4: None}   # 4: hoort volgens het model niet bij het thema
    assert ds.toets_verhaal(rijen, ("biolab", "biological lab"), lijn_van) == {"beweringen": 4, "in grootste": 2,
                                                                                "aandeel": 0.5}
    assert ds.toets_verhaal(rijen, ("bestaat niet",), lijn_van) == {"beweringen": 0, "in grootste": 0, "aandeel": None}


def test_coverage_is_the_share_of_the_fitting_claims_in_the_n_largest_storylines():
    assert ds.dekking([5, 3, 1, 1], n=2) == 0.8
    assert ds.dekking([], n=50) is None


def test_spending_past_the_limit_is_refused_before_anything_is_sent():
    ds.binnen_grens(0.5, 2.0, grens=3.0)
    with pytest.raises(ds.Weigering):
        ds.binnen_grens(1.5, 2.0, grens=3.0)


def test_a_group_that_grew_into_a_chain_is_split_again_at_the_tighter_threshold():
    # vier zinnen op een rij: elke buur lijkt genoeg op de volgende, de uiteinden niet op elkaar
    hoeken = np.radians([0, 30, 60, 90])
    v = np.stack([np.cos(hoeken), np.sin(hoeken)], axis=1).astype(np.float32)
    zinnen = ["a", "b", "c", "d"]
    assert [l["leden"] for l in ds.verhaallijnen(zinnen, v, drempel=0.85)] == [[0, 1, 2, 3]]
    los = ds.verhaallijnen(zinnen, v, drempel=0.85, ketting=3, strakker=0.9)
    assert sorted(l["leden"] for l in los) == [[0], [1], [2], [3]]
    # een groep die klein genoeg is, blijft heel
    assert [l["leden"] for l in ds.verhaallijnen(zinnen, v, drempel=0.85, ketting=4, strakker=0.9)] == [[0, 1, 2, 3]]


def test_a_new_claim_returns_to_a_storyline_only_if_that_line_existed_and_was_large_enough():
    oud = np.array([[1, 0, 0], [0.98, 0.2, 0], [0.97, 0, 0.24], [0, 1, 0]], dtype=np.float32)
    oud /= np.linalg.norm(oud, axis=1, keepdims=True)
    lijn_van_oud, cases = [0, 0, 0, 1], {0: 3, 1: 1}
    nieuw = np.array([[0.99, 0.1, 0.1], [0.05, 1, 0], [0, 0, 1]], dtype=np.float32)
    nieuw /= np.linalg.norm(nieuw, axis=1, keepdims=True)
    # de eerste lijkt op de grote lijn; de tweede op een lijn van één case (te klein); de derde op niets
    assert ds.terugkeer(oud, lijn_van_oud, cases, nieuw, drempel=0.9, minimaal=3) == [0, None, None]
    assert ds.terugkeer(oud, lijn_van_oud, cases, nieuw, drempel=0.9, minimaal=1) == [0, 1, None]
    assert ds.terugkeer(oud[:0], [], {}, nieuw) == [None, None, None]


def test_a_new_claim_counts_only_its_direct_old_neighbours_and_never_a_chain_of_them():
    # vier oude zinnen op een rij (elke buur lijkt op de volgende); de nieuwe zin ligt bij het begin
    hoeken = np.radians([0, 30, 60, 90])
    oud = np.stack([np.cos(hoeken), np.sin(hoeken)], axis=1).astype(np.float32)
    nieuw = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float32)
    # bij 0,85 lijkt de nieuwe zin op de eerste twee; de eerste oude zin stond voor drie beweringen
    assert ds.buren(oud, [3, 1, 1, 1], nieuw, drempel=0.85) == [4, 0]
    assert ds.buren(oud, [1, 1, 1, 1], nieuw, drempel=0.99) == [1, 0]
    assert ds.buren(oud[:0], [], nieuw) == [0, 0]
