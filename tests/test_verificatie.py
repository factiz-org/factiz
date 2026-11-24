"""Controleren met bronnen (PLAN #31.8): de regels die vóór de toets vastlagen."""

import pytest

from doublecheck import verificatie


def _stuk(i, soort, bron, label, helft="toets", vers=False, **extra):
    return {"id": f"b-{i:06d}", "sleutel": f"s{i}", "soort": soort, "bron": bron, "label": label, "helft": helft,
            "vers": vers, "zaak": f"gfc-{i}", "tekst": f"tekst {i}", **extra}


def _berg():
    stukken, i = [], 0
    for soort, bron, label, vers, n in (("tekst", "claimreview", "onwaar", False, 40),
                                        ("tekst", "claimreview", "onwaar", True, 40),
                                        ("beeld", "m4fc", "onwaar", False, 40),
                                        ("tekst", "claimreview", "waar", False, 40),
                                        ("artikel", "sheffield-trustworthy", "waar", False, 40),
                                        ("webtekst", "stiltepool", "neutraal", False, 40)):
        n = 60 if label == "waar" or not vers and label == "onwaar" else n
        for _ in range(n):
            i += 1
            stukken.append(_stuk(i, soort, bron, label, vers=vers))
            stukken.append(_stuk(i + 10_000, soort, bron, label, helft="ontwikkel", vers=vers))
    for f in range(30):
        for variant in range(3):
            i += 1
            stukken.append(_stuk(i, "feit", "n3-kern", "waar", feit=f"feit-{f}"))
    return stukken


def test_the_sample_takes_each_layer_from_the_test_half_only_and_always_the_same():
    stukken = _berg()
    gekozen = verificatie.steekproef(stukken)
    assert len(gekozen) == sum(verificatie.LAGEN.values()) == 100
    assert {s["helft"] for s in gekozen} == {"toets"}
    assert [s["id"] for s in gekozen] == [s["id"] for s in verificatie.steekproef(list(reversed(stukken)))]
    laag = verificatie.laag_van
    assert sum(laag(s) == "onwaar, vers" for s in gekozen) == verificatie.LAGEN["onwaar, vers"]


def test_core_facts_in_the_sample_are_all_different_facts():
    kern = [s for s in verificatie.steekproef(_berg()) if s["bron"] == "n3-kern"]
    assert len({s["feit"] for s in kern}) == len(kern) == verificatie.LAGEN["kernfeit"]


def test_the_verdict_is_read_from_the_last_verdict_line():
    tekst = "Ik zoek eerst.\nOORDEEL: onzeker\n...\nBEWERING: De Krim werd ingenomen.\nOORDEEL: Klopt niet\nUITLEG: x"
    assert verificatie.lees_antwoord(tekst) == ("klopt niet", "De Krim werd ingenomen.", "x")
    assert verificatie.lees_antwoord("geen regel")[0] == "onleesbaar"
    assert verificatie.lees_antwoord("OORDEEL: misschien")[0] == "onleesbaar"


def test_sources_are_the_cited_passages_and_the_memory_checks_the_answer_names():
    blokken = [{"type": "server_tool_use", "input": {"query": "krim 2014"}},
               {"type": "text", "text": "Volgens [F2] en Reuters ", "citations": [
                   {"type": "web_search_result_location", "url": "https://reuters.com/a", "title": "A",
                    "cited_text": "Russia annexed Crimea in March 2014"}]},
               {"type": "text", "text": "OORDEEL: klopt"}]
    geheugen = [{"claim": "c1"}, {"claim": "c2", "url": "https://factly.in/x"}]
    bronnen = verificatie.bronnen_uit(blokken, geheugen)
    assert bronnen == [{"soort": "web", "url": "https://reuters.com/a", "titel": "A",
                        "citaat": "Russia annexed Crimea in March 2014"},
                       {"soort": "geheugen", "url": "https://factly.in/x", "claim": "c2"}]
    assert verificatie.zoekopdrachten(blokken) == ["krim 2014"]


def test_the_new_claim_condition_hides_the_own_check_from_memory():
    kandidaten = [{"claim": "a"}, {"claim": "b"}, {"claim": "c"}]
    assert verificatie.verberg(kandidaten, {"b"}) == [{"claim": "a"}, {"claim": "c"}]
    assert len(verificatie.verberg([{"claim": str(i)} for i in range(9)], set())) == verificatie.N_GEHEUGEN


def test_what_needs_reading_before_counting():
    assert verificatie.uitkomst("waar", "klopt niet") == "te lezen"
    assert verificatie.uitkomst("onwaar", "klopt") == "te lezen"
    assert verificatie.uitkomst("onwaar", "klopt niet") == "te lezen"  # bewijst de bron het?
    assert verificatie.uitkomst("neutraal", "klopt niet") == "te lezen"
    assert verificatie.uitkomst("onwaar", "onzeker") == "gemist"
    assert verificatie.uitkomst("waar", "klopt") == "bevestigd"
    assert verificatie.uitkomst("neutraal", "geen bewering") == "goed"


def test_the_count_refuses_while_a_verdict_that_matters_is_unread():
    stukken = [_stuk(1, "tekst", "claimreview", "waar")]
    antwoorden = {("a", "b-000001"): {"oordeel": "klopt niet", "bronnen": []}}
    with pytest.raises(verificatie.Weigering):
        verificatie.telling(stukken, antwoorden, {})
    telling = verificatie.telling(stukken, antwoorden, {"a:b-000001": "vals"})
    assert telling["a"]["ware stukken klopt niet"] == {"n": 1, "vals": 1, "terecht": 0}


def test_a_false_piece_counts_as_proven_only_with_a_source_that_proves_it():
    stukken = [_stuk(1, "tekst", "claimreview", "onwaar"), _stuk(2, "tekst", "claimreview", "onwaar")]
    antwoorden = {("b", "b-000001"): {"oordeel": "klopt niet", "bronnen": [{"soort": "web"}]},
                  ("b", "b-000002"): {"oordeel": "klopt niet", "bronnen": [{"soort": "web"}]}}
    telling = verificatie.telling(stukken, antwoorden, {"b:b-000001": "bewijst", "b:b-000002": "bewijst niet"})
    assert telling["b"]["onwaar"]["onwaar, oud"] == {"n": 2, "bewezen": 1, "klopt niet zonder bewijs": 1,
                                                     "klopt": 0, "onzeker": 0}


def test_a_new_claim_gets_no_memory_at_all_because_other_editors_checked_the_same_claim():
    # Proef 2026-10-25: met alleen het eigen cluster verborgen vond het model de
    # check van een andere redactie over dezelfde claim (Kuwait, 73 graden).
    g = {"kandidaten": [{"claim": "a"}, {"claim": "b"}], "eigen": ["a"]}
    assert verificatie.geheugen_voor("b", g) == []
    assert verificatie.geheugen_voor("a", g) == [{"claim": "a"}, {"claim": "b"}]



# Ronde 2 (PO 2026-10-25): vraag v2 op 100 nieuwe stukken, Haiku en Sonnet.

def test_round_two_takes_new_pieces_and_never_a_core_fact_of_round_one():
    stukken = _berg()
    eerste = verificatie.steekproef(stukken)
    tweede = verificatie.steekproef(stukken, zaad=verificatie.ZAAD + 1, uitsluiten=eerste)
    assert len(tweede) == 100
    assert not {s["id"] for s in eerste} & {s["id"] for s in tweede}
    feiten = lambda groep: {s["feit"] for s in groep if s["bron"] == "n3-kern"}
    assert not feiten(eerste) & feiten(tweede)


def test_question_two_gives_the_date_and_the_rule_on_small_deviations():
    s = _stuk(1, "tekst", "claimreview", "waar", datum="2024-05-01")
    v2 = verificatie.vraagtekst(s, [], "verificatie-v2")
    assert "circulated around 2024-05-01" in v2 and "not as of today" in v2 and "small deviation" in v2
    zonder = verificatie.vraagtekst({**s, "datum": None}, [], "verificatie-v2")
    assert "date of this message is unknown" in zonder
    v1 = verificatie.vraagtekst(s, [], "verificatie-v1")
    assert "2024-05-01" not in v1 and "small deviation" not in v1
    assert v1.startswith("Message:\ntekst 1")


# Ronde 4 (PO 2026-10-26): vier uitkomsten, met "let op" als signaal, en een kaal model als nulmeting.

def test_round_four_explores_on_the_pieces_of_round_two_without_memory():
    r4 = verificatie.RONDES[4]
    assert r4["stukken"] == 2 and r4["versie"] == "verificatie-v4" and r4["omstandigheden"] == ("b", "k")
    g = {"kandidaten": [{"claim": "a"}], "eigen": []}
    assert verificatie.geheugen_voor("k", g) == [] and verificatie.geheugen_voor("b", g) == []


def test_question_four_knows_let_op_and_counts_what_really_happened_as_proof():
    s = _stuk(1, "tekst", "claimreview", "onwaar", datum="2026-08-14")
    v4 = verificatie.vraagtekst(s, [], "verificatie-v4")
    assert '"let op"' in v4 and "what actually happened" in v4 and "circulated around 2026-08-14" in v4
    assert "small local event" in v4  # niets gevonden over iets kleins is onzeker, geen let op
    assert "let op |" in v4.splitlines()[-2]


def test_the_bare_model_gets_no_memory_block_and_no_search():
    s = _stuk(1, "tekst", "claimreview", "onwaar", datum="2026-08-14")
    kaal = verificatie.vraagtekst(s, [], "verificatie-v4", kaal=True)
    assert "Factiz memory" not in kaal and "search the web" not in kaal and "own knowledge" in kaal
    verzoek = verificatie.verzoek(s, [], "k", ["snopes.com"], "sonnet", "verificatie-v4")
    assert "tools" not in verzoek["params"] and verzoek["params"]["system"] == verificatie.SYSTEEM_KAAL
    assert verzoek["custom_id"] == "k-b-000001"
    assert verificatie.verzoek(s, [], "b", ["snopes.com"], "sonnet", "verificatie-v4")["params"]["tools"]


def test_let_op_is_read_as_a_verdict_and_always_read_before_counting():
    assert verificatie.lees_antwoord("OORDEEL: Let op\nUITLEG: x")[0] == "let op"
    for label in ("waar", "onwaar", "neutraal"):
        assert verificatie.uitkomst(label, "let op") == "te lezen"


def test_let_op_on_a_true_piece_is_a_false_warning_and_on_a_false_piece_counts_only_with_a_sound_reason():
    stukken = [_stuk(1, "tekst", "claimreview", "waar"), _stuk(2, "tekst", "claimreview", "onwaar"),
               _stuk(3, "tekst", "claimreview", "onwaar")]
    antwoorden = {("b", "b-000001"): {"oordeel": "let op", "bronnen": []},
                  ("b", "b-000002"): {"oordeel": "let op", "bronnen": []},
                  ("b", "b-000003"): {"oordeel": "let op", "bronnen": []}}
    with pytest.raises(verificatie.Weigering):
        verificatie.telling(stukken, antwoorden, {"b:b-000001": "vals"})
    t = verificatie.telling(stukken, antwoorden, {"b:b-000001": "vals", "b:b-000002": "terecht",
                                                  "b:b-000003": "toevallig"})["b"]
    assert t["ware stukken let op"] == {"vals": 1, "terecht": 0}
    assert t["waar"]["ware check"]["let op"] == 1
    assert t["onwaar"]["onwaar, oud"]["let op"] == 1 and t["onwaar"]["onwaar, oud"]["let op toevallig"] == 1


def test_counts_of_earlier_rounds_keep_their_shape_without_let_op():
    stukken = [_stuk(1, "tekst", "claimreview", "onwaar")]
    t = verificatie.telling(stukken, {("b", "b-000001"): {"oordeel": "onzeker", "bronnen": []}}, {})["b"]
    assert "let op" not in t["onwaar"]["onwaar, oud"] and "ware stukken let op" not in t


def test_the_budget_counts_what_a_finished_batch_really_cost_and_the_estimate_for_one_still_running(tmp_path, monkeypatch):
    # Ronde 5: de schatting ($0,053 per bericht) lag ver boven het werkelijke bedrag (~$0,03).
    monkeypatch.setitem(verificatie.RONDES, 99, {"map": tmp_path, "modellen": ("sonnet",)})
    (tmp_path / "sonnet").mkdir()
    (tmp_path / "sonnet" / "batches.jsonl").write_text(
        '{"id": "a", "schatting": 2.0, "werkelijk": 0.5, "ids": []}\n{"id": "b", "schatting": 1.0, "ids": []}\n',
        encoding="utf-8")
    assert verificatie.al_ingediend(99) == pytest.approx(1.5)


def test_klopt_on_a_false_piece_whose_caption_is_true_after_all_counts_apart_as_an_error_in_the_set():
    # Ronde 5: "Prabha Munni staat op een oude foto met Kejriwal" klopt letterlijk; het
    # misleidende deel van de post viel weg toen M4FC de claim opschreef.
    stukken = [_stuk(1, "tekst", "claimreview", "onwaar"), _stuk(2, "tekst", "claimreview", "onwaar")]
    antwoorden = {("bR", "b-000001"): {"oordeel": "klopt", "bronnen": []},
                  ("bR", "b-000002"): {"oordeel": "klopt", "bronnen": []}}
    d = verificatie.telling(stukken, antwoorden, {"bR:b-000001": "vals", "bR:b-000002": "bijschrift waar"})
    assert d["bR"]["onwaar"]["onwaar, oud"]["klopt"] == 1
    assert d["bR"]["onwaar"]["onwaar, oud"]["klopt, bijschrift waar"] == 1


# Ronde 6, in het wild (PO 2026-10-26): echte tiplineberichten, met of zonder bewering.

def _rij(i, taal="hi", label="Yes", bron="social media"):
    return {"text": f"bericht {i}", "language": taal, "majority_label": label, "source": bron}


def test_the_wild_sample_takes_only_messages_from_social_media_with_a_clear_majority_per_language():
    rijen = [_rij(i, taal, label, bron) for i, (taal, label, bron) in enumerate(
        (t, l, b) for t in ("hi", "ta") for l in ("Yes", "No", "No Majority", "Probably")
        for b in ("social media", "fact-check") for _ in range(5))]
    gekozen = verificatie.wilde_steekproef(rijen, n_per_taal=6)
    assert len(gekozen) == 12 and {s["laag"] for s in gekozen} == {"hi", "ta"}
    assert all(rijen[int(s["id"][2:])]["source"] == "social media" for s in gekozen)
    assert {s["label"] for s in gekozen} <= {"bewering", "geen bewering"}
    assert [s["id"] for s in gekozen] == [s["id"] for s in verificatie.wilde_steekproef(rijen, n_per_taal=6)]
    assert gekozen[0]["datum"] == verificatie.DATUM_WILD and gekozen[0]["soort"] == "tekst"


def test_a_wild_message_says_its_date_is_a_range_and_every_verdict_with_a_claim_is_read():
    s = {"soort": "tekst", "tekst": "x", "datum": verificatie.DATUM_WILD}
    assert "circulated around 2019–2021 (exact date unknown)" in verificatie.vraagtekst(s, [], "verificatie-v4")
    assert verificatie.uitkomst("bewering", "klopt") == "te lezen"
    assert verificatie.uitkomst("geen bewering", "geen bewering") == "goed"


def test_the_wild_count_measures_agreement_on_claims_and_what_holds_when_read():
    stukken = [{"id": "t-00001", "label": "bewering", "laag": "hi"}, {"id": "t-00002", "label": "geen bewering", "laag": "hi"},
               {"id": "t-00003", "label": "bewering", "laag": "ta"}, {"id": "t-00004", "label": "bewering", "laag": "ta"}]
    antwoorden = {("a", "t-00001"): {"oordeel": "klopt niet", "bronnen": [{"soort": "geheugen"}], "kosten": 0.02},
                  ("a", "t-00002"): {"oordeel": "geen bewering", "bronnen": [], "kosten": 0.004},
                  ("a", "t-00003"): {"oordeel": "let op", "bronnen": [], "kosten": 0.03},
                  ("a", "t-00004"): {"oordeel": "geen bewering", "bronnen": [], "kosten": 0.006}}
    with pytest.raises(verificatie.Weigering):
        verificatie.telling_wild(stukken, antwoorden, {"a:t-00001": "houdt stand"})
    t = verificatie.telling_wild(stukken, antwoorden, {"a:t-00001": "houdt stand", "a:t-00003": "terecht"})
    assert t["totaal"]["n"] == 4 and t["totaal"]["eens"] == 3
    assert t["totaal"]["met bron"] == {"n": 1, "houdt stand": 1, "houdt geen stand": 0}
    assert t["totaal"]["let op"] == {"n": 1, "terecht": 1, "toevallig": 0}
    assert t["totaal"]["met check uit het geheugen"] == 1 and t["totaal"]["kosten per bericht"] == pytest.approx(0.015)
    assert t["ta"]["eens"] == 1 and t["hi"]["model: bewering"] == 1


# Ronde 7, de bewijsronde (PO 2026-10-26): de vastgezette machine op Engelse checks en de Verifyr-vloer.

def test_the_proof_set_takes_unused_english_checks_from_the_test_half_always_the_same():
    stukken = [_stuk(i, "tekst", "claimreview", "waar" if i % 2 else "onwaar", helft="toets" if i <= 360 else "ontwikkel",
                     vers=i % 10 == 0, taal="English" if i % 4 else "hindi") for i in range(1, 401)]
    gekozen = verificatie.bewijsset(stukken, {"b-000001", "b-000003"}, n_waar=60, n_onwaar=40)
    waar = [s for s in gekozen if s["label"] == "waar"]
    onwaar = [s for s in gekozen if s["label"] == "onwaar"]
    assert len(waar) == 60 and len(onwaar) == 40
    assert all(s["helft"] == "toets" and s["taal"] == "English" for s in gekozen)
    assert not {"b-000001", "b-000003"} & {s["id"] for s in gekozen}
    assert {verificatie.laag_van(s) for s in waar} == {"ware check"}
    assert [s["id"] for s in gekozen] == [s["id"] for s in verificatie.bewijsset(stukken[::-1], {"b-000001", "b-000003"},
                                                                                 n_waar=60, n_onwaar=40)]


def test_the_verifyr_floor_is_the_fixed_list_of_fifty_and_runs_only_on_the_web_without_memory():
    lijst = verificatie.evergreen_stukken()
    assert len(lijst) == 50 and len({s["sleutel"] for s in lijst}) == 50
    assert {s["laag"] for s in lijst} == {"evergreen"} and all(s["label"] == "onwaar" and s["tekst"] for s in lijst)
    check = {"laag": "ware check"}
    assert verificatie.doet_mee(7, "w", lijst[0]) and not verificatie.doet_mee(7, "a", lijst[0])
    assert verificatie.doet_mee(7, "a", check) and verificatie.doet_mee(7, "b", check)
    assert not verificatie.doet_mee(7, "w", check) and verificatie.doet_mee(5, "bR", check)
    g = {"kandidaten": [{"claim": "a"}], "eigen": []}
    assert verificatie.geheugen_voor("w", g) == [] and not verificatie.zonder_factchecks_aan("w")
    r7 = verificatie.RONDES[7]
    assert r7["omstandigheden"] == ("a", "b", "w") and r7["versie"] == "verificatie-v4" and r7["budget"] == 30.0
