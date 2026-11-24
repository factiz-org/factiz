"""De eerste leerling (PLAN #31.4, E8.S4): de regels die vóór het trainen vastlagen."""

from doublecheck import leerling


def _rij(score, label, bron="b"):
    return {"score": score, "label": label, "bron": bron}


def test_the_threshold_is_the_lowest_with_at_most_one_percent_true_flagged_and_no_core_fact():
    rijen = [_rij(s / 100, "waar") for s in range(100)] + [_rij(0.95, "onwaar"), _rij(0.50, "onwaar")]
    # 100 ware stukken: hoogstens 1 mag een vlag krijgen, dus de drempel ligt boven 0,98.
    assert leerling.kies_drempel(rijen) == 0.99
    met_kern = rijen + [_rij(0.995, "waar", bron="n3-kern")]
    assert leerling.kies_drempel(met_kern) > 0.995


def test_with_nothing_true_above_any_score_the_lowest_score_is_the_threshold():
    rijen = [_rij(0.1, "waar"), _rij(0.9, "onwaar"), _rij(0.8, "onwaar")]
    assert leerling.kies_drempel(rijen, max_vals=0.0) == 0.8


def test_the_student_reads_the_text_or_for_an_image_what_haiku_read():
    assert leerling.invoer({"id": "b-1", "soort": "tekst", "tekst": "Een bewering."}, {}) == "Een bewering."
    assert leerling.invoer({"id": "b-2", "soort": "beeld", "sleutel": "P3:00001"}, {"P3:00001": "Photo shows X."}) \
        == "Photo shows X."
    assert leerling.invoer({"id": "b-3", "soort": "beeld", "sleutel": "P3:00002"}, {}) is None


def test_a_core_fact_and_the_test_half_are_never_lessons():
    kern = {"helft": "ontwikkel", "bron": "n3-kern", "sleutel": "N3:1", "vers": False}
    assert leerling.rol(kern) == "keuze"
    assert leerling.rol({**kern, "bron": "claimreview", "helft": "toets"}) == "toets"
    zaken = [{"helft": "ontwikkel", "bron": "claimreview", "zaak": f"z{i}", "sleutel": f"s{i}", "vers": False}
             for i in range(50)]
    assert {leerling.rol(z) for z in zaken} == {"les", "keuze"}


def test_an_image_without_a_read_claim_gets_no_verdict():
    stukken = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert leerling.oordelen_bij({"a": 0.9, "b": 0.2}, 0.5, stukken) == \
        {"a": "onwaar", "b": "geen-oordeel", "c": "geen-oordeel"}


def _echt(i, taal, helft="toets", bron="wikinews"):
    return {"sleutel": f"{bron}:{taal}:{i}", "bron": bron, "taal": taal, "helft": helft, "label": "waar", "tekst": "x"}


def test_real_news_is_tested_only_from_the_test_half_and_at_most_so_many_per_language():
    stukken = [_echt(i, "ru") for i in range(30)] + [_echt(i, "ar") for i in range(5)] + \
              [_echt(i, "nl", helft="ontwikkel") for i in range(30)]
    gekozen = leerling.echt_steekproef(stukken, per_taal=10)
    assert {s["helft"] for s in gekozen} == {"toets"}
    assert sum(s["taal"] == "ru" for s in gekozen) == 10 and sum(s["taal"] == "ar" for s in gekozen) == 5
    assert [s["sleutel"] for s in gekozen] == [s["sleutel"] for s in leerling.echt_steekproef(stukken[::-1], 10)]


def test_real_news_counts_every_flag_as_false_per_source_and_language():
    stukken = [_echt(1, "ru"), _echt(2, "ru"), _echt(3, "ar", bron="wikipedia")]
    telling = leerling.echt_telling(stukken, {"wikinews:ru:1": 0.9, "wikinews:ru:2": 0.1, "wikipedia:ar:3": 0.95}, 0.5)
    assert telling["wikinews"]["n"] == 2 and telling["wikinews"]["vlag"] == 1
    assert telling["wikinews"]["per taal"] == {"ru": [2, 1]}
    assert telling["wikipedia"]["per taal"] == {"ar": [1, 1]}
    assert 0.5 < telling["wikinews"]["bovengrens"] <= 1.0


def test_the_core_margin_is_how_far_the_highest_core_fact_stays_below_the_threshold():
    rijen = [{"score": 0.4, "bron": "n3-kern"}, {"score": 0.7, "bron": "n3-kern"}, {"score": 0.99, "bron": "claimreview"}]
    assert abs(leerling.kernmarge(rijen, 0.9) - 0.2) < 1e-9
    assert leerling.kernmarge(rijen, 0.6) < 0
