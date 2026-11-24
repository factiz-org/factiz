"""Omgekeerd zoeken op beelden (PLAN #31.8, ronde 3): de regels die vóór de toets vastlagen."""

import pytest

from doublecheck import beeldzoeken, verificatie


def _m4fc(claim, waar, gebruik=True):
    return {"claim": claim, "true_caption": waar, "use_true_caption": gebruik}


def _beeld(i, helft="toets", deel="foto zonder tekst"):
    return ({"id": f"b-{i:06d}", "sleutel": f"P3:{i:05d}", "soort": "beeld", "bron": "m4fc", "label": "onwaar",
             "helft": helft, "datum": "2023-07-01", "zaak": f"gfc-{i}", "beeld": f"/x/{i:05d}.png", "vers": False},
            {"sleutel": f"P3:{i:05d}", "deel": deel})


def _berg():
    beelden, delen, m4fc = [], {}, {}
    for i in range(1, 121):
        helft = "toets" if i <= 60 else "ontwikkel"
        deel = "screenshot met tekst" if i % 10 == 0 else "foto zonder tekst"
        s, item = _beeld(i, helft, deel)
        beelden.append(s)
        delen[s["sleutel"]] = item["deel"]
        m4fc[i] = _m4fc(f"valse claim {i}", "not enough information" if i % 7 == 0 else f"waar verhaal {i}")
    return beelden, delen, m4fc


def test_pairs_take_images_without_a_claim_of_their_own_with_a_true_story_never_used_before_test_half_first():
    # Een schermafdruk van de virale post draagt de valse claim zelf; die past niet bij het ware verhaal.
    beelden, delen, m4fc = _berg()
    zonder_claim = {k for k, deel in delen.items() if deel == "foto zonder tekst"}
    paren = verificatie.beeldparen(beelden, zonder_claim, m4fc, gebruikt={"P3:00001"}, n=50)
    onwaar = [s for s in paren if s["label"] == "onwaar"]
    waar = [s for s in paren if s["label"] == "waar"]
    assert len(onwaar) == len(waar) == 50
    gekozen = {s["sleutel"] for s in onwaar}
    assert "P3:00001" not in gekozen
    assert all(delen[k] == "foto zonder tekst" for k in gekozen)
    assert all(int(k[3:]) % 7 for k in gekozen)  # geen "not enough information"
    assert sum(s["helft"] == "toets" for s in onwaar) == min(50, sum(
        1 for s in beelden if s["helft"] == "toets" and delen[s["sleutel"]] == "foto zonder tekst"
        and int(s["sleutel"][3:]) % 7 and s["sleutel"] != "P3:00001"))
    for o in onwaar:
        w = next(x for x in waar if x["sleutel"] == o["sleutel"])
        assert (o["beeld"], o["datum"], o["zaak"]) == (w["beeld"], w["datum"], w["zaak"])
        assert o["tekst"].startswith("valse claim") and w["tekst"].startswith("waar verhaal")
        assert (o["laag"], w["laag"]) == ("beeld onwaar", "beeld waar")
    assert [s["id"] for s in paren] == [s["id"] for s in verificatie.beeldparen(beelden[::-1], zonder_claim, m4fc,
                                                                                gebruikt={"P3:00001"}, n=50)]


def test_pages_of_fact_checkers_are_left_out_when_the_model_must_prove_it_itself():
    paginas = [{"url": "https://www.factly.in/x", "titel": "a"}, {"url": "https://m.youturn.in/y", "titel": "b"},
               {"url": "https://www.lemonde.fr/2019/protest", "titel": "c"},
               {"url": "https://news.example.com/fact-check/z", "titel": "d"},
               {"url": "https://example.org/hoax-or-not", "titel": "e"}]
    over = beeldzoeken.zonder_factchecks(paginas, {"factly.in", "youturn.in"})
    assert [p["titel"] for p in over] == ["c"]


def test_the_vision_answer_becomes_pages_with_titles_without_markup():
    antwoord = {"responses": [{"webDetection": {
        "pagesWithMatchingImages": [{"url": "https://a.org/p", "pageTitle": "Protest <b>Bouteflika</b> 2019"},
                                    {"url": "https://b.org/q"}],
        "webEntities": [{"description": "Place de la République"}, {"entityId": "x"}],
        "bestGuessLabels": [{"label": "protest paris"}]}}]}
    r = beeldzoeken.lees_vision(antwoord)
    assert r["paginas"] == [{"url": "https://a.org/p", "titel": "Protest Bouteflika 2019"},
                            {"url": "https://b.org/q", "titel": ""}]
    assert r["entiteiten"] == ["Place de la République"] and r["beste_gok"] == ["protest paris"]
    assert beeldzoeken.lees_vision({"responses": [{}]})["paginas"] == []


def test_the_question_lists_the_pages_as_r_numbers_and_says_when_nothing_was_found():
    blok = beeldzoeken.beeldzoek_tekst([{"url": "https://a.org/p", "titel": "Protest 2019"}])
    assert "[R1] Protest 2019 — a.org" in blok
    assert "no pages" in beeldzoeken.beeldzoek_tekst([])


def test_an_answer_that_names_r1_has_that_page_as_its_source():
    blokken = [{"type": "text", "text": "Volgens [R1] is dit 2019."}]
    bronnen = verificatie.bronnen_uit(blokken, [], [{"url": "https://a.org/p", "titel": "Protest 2019"}])
    assert bronnen == [{"soort": "beeld", "url": "https://a.org/p", "titel": "Protest 2019"}]


def test_round_three_runs_differ_only_in_memory_blocking_and_image_search():
    g = {"kandidaten": [{"claim": "a"}], "eigen": []}
    assert verificatie.geheugen_voor("b", g) == verificatie.geheugen_voor("bR", g) == []
    assert verificatie.geheugen_voor("aR", g) == [{"claim": "a"}]
    assert [verificatie.met_beeldzoeken(o) for o in ("b", "bR", "aR")] == [False, True, True]
    assert [verificatie.zonder_factchecks_aan(o) for o in ("b", "bR", "aR")] == [True, True, False]


def test_question_three_shows_the_caption_under_the_image_and_the_reverse_search_rule():
    s = {"soort": "beeld", "tekst": "Protest na de dood van Nahel M.", "datum": "2023-07-01"}
    v3 = verificatie.vraagtekst(s, [], "verificatie-v3", beeldpaginas=[{"url": "https://a.org/p", "titel": "T"}])
    assert "posted with this caption:\nProtest na de dood van Nahel M." in v3
    assert "[R1] T" in v3 and "another context" in v3
    zonder = verificatie.vraagtekst(s, [], "verificatie-v3", beeldpaginas=None)
    assert "[R1]" not in zonder and "Reverse image search" not in zonder


def test_only_an_answer_that_says_plain_photo_counts_as_a_plain_photo():
    assert beeldzoeken.lees_kaal('{"kaal": true}') is True
    assert beeldzoeken.lees_kaal('{"kaal": false}') is False
    assert beeldzoeken.lees_kaal("{") is None


# Ronde 5 (PO 2026-10-26): ware beelden uit M4FC tegenover ongebruikte onware, met dezelfde vorm.

def _item(i, verdict="true"):
    return {"claim": f"claim {i}", "verdict": verdict, "fc_pub_date": "2021-03-15 10:00:00",
            "image_url": f"https://www.snopes.com/i/{i}.jpg", "fc_org": "snopes.com"}


def test_true_candidates_are_images_m4fc_rates_true_that_could_be_fetched_before_always_the_same():
    m4fc = [_item(i, "true" if i % 3 else "false (out-of-context)") for i in range(90)]
    eerder = {i: (f"{i:05d}.jpg" if i % 5 else None) for i in range(90)}
    kandidaten = beeldzoeken.ware_kandidaten(m4fc, eerder, n=20, zaad=7)
    assert len(kandidaten) == 20 and all(i % 3 and i % 5 for i in kandidaten)
    assert kandidaten == beeldzoeken.ware_kandidaten(m4fc, eerder, n=20, zaad=7)


def test_false_candidates_come_from_the_test_half_and_were_never_used():
    beelden = [_beeld(i, "toets" if i <= 80 else "ontwikkel")[0] for i in range(1, 121)]
    gekozen = verificatie.onware_kandidaten(beelden, gebruikt={"P3:00001", "P3:00002"}, n=30)
    assert len(gekozen) == 30 and {s["helft"] for s in gekozen} == {"toets"}
    assert not {"P3:00001", "P3:00002"} & {s["sleutel"] for s in gekozen}
    assert gekozen == verificatie.onware_kandidaten(beelden[::-1], gebruikt={"P3:00001", "P3:00002"}, n=30)


def test_the_form_answer_needs_both_plain_and_stamp_or_it_is_unreadable():
    assert beeldzoeken.lees_vorm('{"kaal": true, "stempel": false}') == (True, False)
    assert beeldzoeken.lees_vorm('{"kaal": true}') is None
    assert beeldzoeken.lees_vorm("x") is None


def _set_berg():
    waar = [{"id": f"w-{i:05d}", "sleutel": f"waar:{i:05d}", "soort": "beeld", "bron": "m4fc", "label": "waar",
             "laag": "beeld waar", "helft": "toets", "tekst": f"ware claim {i}", "datum": "2021-03-15",
             "beeld": f"/w/{i:05d}.jpg"} for i in range(1, 61)]
    onwaar = [{**_beeld(i)[0], "laag": "beeld onwaar", "tekst": f"valse claim {i}"} for i in range(101, 251)]
    vorm = {}
    for s in waar:
        i = int(s["sleutel"][5:])
        vorm[s["sleutel"]] = (i % 4 != 0, i % 10 == 0)  # driekwart kaal, elk tiende met een stempel
    for s in onwaar:
        i = int(s["sleutel"][3:])
        vorm[s["sleutel"]] = (i % 2 == 0, i % 7 == 0)  # de helft kaal
    return waar, onwaar, vorm


def test_stamped_images_never_enter_and_both_halves_have_the_same_number_of_plain_photos():
    waar, onwaar, vorm = _set_berg()
    gekozen = verificatie.beeldset(waar, onwaar, vorm, n=50)
    w = [s for s in gekozen if s["label"] == "waar"]
    o = [s for s in gekozen if s["label"] == "onwaar"]
    assert len(w) == len(o) == 50
    assert not any(vorm[s["sleutel"]][1] for s in gekozen)
    assert sum(vorm[s["sleutel"]][0] for s in w) == sum(vorm[s["sleutel"]][0] for s in o)
    assert [s["id"] for s in gekozen] == [s["id"] for s in verificatie.beeldset(waar[::-1], onwaar[::-1], vorm, n=50)]


def test_the_set_refuses_when_the_form_cannot_be_matched():
    waar, onwaar, vorm = _set_berg()
    alles_kaal = {k: (k.startswith("waar"), False) for k in vorm}  # ware helft alleen kaal, onwaar nooit
    with pytest.raises(verificatie.Weigering):
        verificatie.beeldset(waar, onwaar, alles_kaal, n=50)


def test_question_five_is_question_four_with_the_caption_under_the_image():
    s = {"soort": "beeld", "tekst": "Kinderen op ezelkarren naar school", "datum": "2023-02-15"}
    v5 = verificatie.vraagtekst(s, [], "verificatie-v5", beeldpaginas=[{"url": "https://a.org/p", "titel": "T"}])
    assert "posted with this caption:\nKinderen op ezelkarren naar school" in v5
    assert "circulated around 2023-02-15" in v5 and '"let op"' in v5 and "[R1] T" in v5
    r5 = verificatie.RONDES[5]
    assert r5["omstandigheden"] == ("b", "bR", "aR") and r5["versie"] == "verificatie-v5" and r5["budget"] == 12.0


def test_round_five_also_blocks_the_fact_checkers_of_m4fc_and_the_leaks_of_round_four():
    extra = verificatie.RONDES[5]["extra_blok"]
    assert {"poligrafo.sapo.pt", "dfrac.org", "cyberpeace.org", "indiatoday.in/fact-check"} <= set(extra)
    assert "indiatoday.in" not in verificatie.extra_domeinen(5)  # een nieuwssite: alleen het pad
    assert "poligrafo.sapo.pt" in verificatie.extra_domeinen(5)


def test_without_matching_form_each_half_is_random_but_still_without_stamps():
    # De vorm bleek niet te evenaren (3 kale foto's op 150 onware kandidaten, 2026-10-26).
    waar, onwaar, vorm = _set_berg()
    gekozen = verificatie.beeldset(waar, onwaar, vorm, n=50, gelijk=False)
    assert sum(s["label"] == "waar" for s in gekozen) == sum(s["label"] == "onwaar" for s in gekozen) == 50
    assert not any(vorm[s["sleutel"]][1] for s in gekozen)
    assert gekozen == verificatie.beeldset(waar[::-1], onwaar[::-1], vorm, n=50, gelijk=False)
    with pytest.raises(verificatie.Weigering):
        verificatie.beeldset(waar[:40], onwaar, vorm, n=50, gelijk=False)
