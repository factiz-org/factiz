"""De drie voormetingen voor de volgende beeldronde (PLAN #32.20): tellen zoals vooraf vastgelegd."""

import pytest

from doublecheck import beeldvoormeting as bvm

G, A, V = bvm.GEVONDEN, bvm.ANDERE, bvm.VALS


def _kopie(id_, claim, groep, sift=(), copynce=(), url=None):
    return {"set": "R2", "id": id_, "vraag": url or f"https://x.test/{id_}.jpg", "claim_id": claim, "groep": groep,
            "sift": [list(s) for s in sift], "copynce": [list(c) for c in copynce], "index": 10, "eigen_beelden": 2}


# --- V1 en V3 (b): R2 -------------------------------------------------------------------------------

def test_a_match_below_50_points_is_never_a_main_rule_match():
    assert bvm.beste_sift([["b1", "g", "a", 49, 0.9]], 50) is None
    assert bvm.beste_sift([["b1", "g", "a", 60, 0.05]], 50) is None
    assert bvm.beste_sift([["b1", "g", "a", 49, 0.9]], 20)[0] == "b1"


def test_the_best_sift_match_is_the_one_with_most_points():
    assert bvm.beste_sift([["b1", "g", "a", 60, 0.2], ["b2", "h", "a", 300, 0.3], ["b3", "g", "a", 80, 0.9]],
                          50)[0] == "b2"


def test_copynce_below_the_threshold_is_never_a_match():
    assert bvm.beste_copynce([["b1", "g", "a", 0.49]], 0.5) is None
    assert bvm.beste_copynce([["b1", "g", "a", 0.6], ["b2", "h", "a", 0.97]], 0.5)[0] == "b2"


def test_with_the_main_rule_every_best_match_needs_a_label():
    regels = [_kopie("c#0", "c", "c", sift=[["b1", "c", "a", 70, 0.4]])]
    with pytest.raises(bvm.Weigering):
        bvm.r2_telling(regels, {}, "sift", 50)
    uit = bvm.r2_telling(regels, {"R2|c#0|b1": G}, "sift", 50)
    assert uit["gevonden"] == 1 and uit["vals"] == 0


def test_with_the_old_rule_an_own_article_match_counts_without_label_as_in_187():
    regels = [_kopie("c#0", "c", "c", sift=[["b1", "c", "a", 25, 0.4]])]
    assert bvm.r2_telling(regels, {}, "sift", 20)["gevonden"] == 1


def test_a_best_match_elsewhere_without_label_blocks_the_count():
    regels = [_kopie("c#0", "c", "c", sift=[["b9", "z", "a", 25, 0.4]])]
    with pytest.raises(bvm.Weigering):
        bvm.r2_telling(regels, {}, "sift", 20)
    assert bvm.r2_telling(regels, {"R2|c#0|b9": V}, "sift", 20)["vals"] == 1


def test_an_own_article_match_that_is_another_image_is_not_found():
    regels = [_kopie("c#0", "c", "c", sift=[["b1", "c", "a", 70, 0.4]])]
    uit = bvm.r2_telling(regels, {"R2|c#0|b1": V}, "sift", 50)
    assert uit["gevonden"] == 0 and uit["vals"] == 1


def test_a_claim_counts_once_however_many_copies_find_it():
    regels = [_kopie(f"c#{i}", "c", "c", copynce=[["b1", "c", "a", 0.9]]) for i in range(3)]
    labels = {f"R2|c#{i}|b1": G for i in range(3)}
    assert bvm.r2_telling(regels, labels, "copynce", 0.5)["gevonden"] == 1


def test_labels_from_32_15_carry_over_for_the_same_pair():
    regel = _kopie("c#0", "c", "c", sift=[["b9", "z", "a", 25, 0.4]], url="https://x.test/kopie.jpg")
    labels = bvm.samengevoegd({}, {}, {"R2|https://x.test/kopie.jpg|origineel|b9": V})
    assert bvm.r2_telling([regel], labels, "sift", 20)["vals"] == 1


def test_v1_passes_only_with_no_false_best_match_and_30_claims():
    assert bvm.v1_beslissing({"gevonden": 30, "vals": 0})["gehaald"]
    assert not bvm.v1_beslissing({"gevonden": 29, "vals": 0})["gehaald"]
    assert not bvm.v1_beslissing({"gevonden": 80, "vals": 1})["gehaald"]


def test_the_chance_of_a_false_pair_counts_only_comparisons_elsewhere():
    regels = [_kopie("c#0", "c", "c", sift=[["b1", "c", "a", 70, 0.4], ["b9", "z", "a", 60, 0.2],
                                            ["b8", "y", "a", 30, 0.2]])]
    k = bvm.kans_per_paar(regels, 50)
    assert k["paren elders boven de regel"] == 1 and k["vergelijkingen elders"] == 8


# --- V2: meer kandidaten ----------------------------------------------------------------------------

def _vraag(eigen, tekst, beschrijving, set_="R3", id_="q", claim="c"):
    def lijst(groepen):
        return [{"claim": g, "groep": g, "url": f"https://f.test/{g}", "gelijkenis": 0.9 - i / 100}
                for i, g in enumerate(groepen)]

    return {"set": set_, "id": id_, "claim_id": claim, "eigen": eigen, "tekst": lijst(tekst),
            "beschrijving": lijst(beschrijving)}


def test_own_check_found_at_10_but_not_at_5_is_new():
    v = _vraag(["e"], [f"x{i}" for i in range(7)] + ["e"], [])
    assert bvm.eigen_bij(v, 5) == set() and bvm.eigen_bij(v, 10) == {"tekst"}
    assert [(n, k["groep"]) for n, k in bvm.nieuwe_eigen(v)] == [(10, "e")]


def test_more_candidates_never_find_less():
    v = _vraag(["e"], ["e"] + [f"x{i}" for i in range(20)], [f"y{i}" for i in range(12)] + ["e"])
    gevonden = [bool(bvm.eigen_bij(v, n)) for n in bvm.KANDIDATEN]
    assert gevonden == sorted(gevonden)
    assert bvm.eigen_bij(v, 20) == {"tekst", "beschrijving"}


def test_v2_counts_a_claim_once_and_screenshots_of_n_each():
    regels = [_vraag(["e"], ["e"], [], id_="q1"), _vraag(["e"], ["e"], [], id_="q2"),
              _vraag(["e"], ["e"], [], set_="N", id_="n1", claim=None), _vraag(["f"], ["e"], [], set_="N", id_="n2",
                                                                               claim=None)]
    uit = bvm.v2_telling(regels)
    assert uit["R3"]["5"]["gevonden"] == 1 and uit["N"]["5"]["gevonden"] == 1 and uit["N"]["5"]["vragen"] == 2


def test_expected_false_scales_with_the_articles_to_compare():
    laag = bvm.verwacht_vals(1e-5, 10, 5)
    assert bvm.verwacht_vals(1e-5, 20, 5) == pytest.approx(2 * laag)
    assert laag == pytest.approx(0.5)


def test_v2_takes_more_candidates_only_with_5_extra_and_under_1_false_per_1000():
    assert bvm.v2_beslissing(5, 0.9)["gehaald"]
    assert not bvm.v2_beslissing(4, 0.1)["gehaald"]
    assert not bvm.v2_beslissing(9, 1.0)["gehaald"]


# --- V3: CopyNCE naast SIFT -------------------------------------------------------------------------

def _paar(set_, vraag, beeld, punten, uitgesloten=False, pdq=None):
    return {"set": set_, "vraag": vraag, "beeld": beeld, "punten": punten, "dekking": 0.5, "punten500": punten,
            "dekking500": 0.5, "pdq": pdq, "uitgesloten": uitgesloten}


def test_sample_c_takes_only_unconfirmed_pairs_that_count_and_is_the_same_each_time():
    paren = [_paar("N", f"q{i}", f"b{i}", 10) for i in range(50)] + [_paar("N", "q", "bevestigd", 80),
                                                                      _paar("N", "q", "zelf", 5, uitgesloten=True),
                                                                      _paar("R2", "q", "r2", 5),
                                                                      _paar("W", "q", "https://huis.test/logo", 5)]
    a = bvm.steekproef_c(paren, {"huis.test/logo"}, n=20)
    assert len(a) == 20 and a == bvm.steekproef_c(paren, {"huis.test/logo"}, n=20)
    assert {p["beeld"] for p in a}.isdisjoint({"bevestigd", "zelf", "r2", "https://huis.test/logo"})


def test_copynce_on_the_labelled_pairs_counts_per_label():
    scores = {"N|q|b1": 0.9, "N|q|b2": 0.2, "N|q|b3": 0.7}
    uit = bvm.v3a_telling(scores, {"N|q|b1": G, "N|q|b2": G, "N|q|b3": V}, 0.5)
    assert uit[G] == {"paren": 2, "boven": 1} and uit[V] == {"paren": 1, "boven": 1}


def test_a_new_copynce_match_without_label_blocks_the_count():
    with pytest.raises(bvm.Weigering):
        bvm.v3c_telling({"N|q|b1": 0.8}, {}, 0.5)
    uit = bvm.v3c_telling({"N|q|b1": 0.8, "N|q|b2": 0.6, "N|q|b3": 0.1}, {"N|q|b1": A, "N|q|b2": V}, 0.5)
    assert uit["zelfde beeld"] == 1 and uit["vals"] == 1 and uit["boven"] == 2


def test_v3_rules_as_second_confirmer_and_as_filter():
    a = {G: {"paren": 100, "boven": 95}, A: {"paren": 2, "boven": 2}, V: {"paren": 10, "boven": 5}}
    uit = bvm.v3_beslissing(a, {"vals": 1}, {"zelfde beeld": 10, "vals": 1}, sift_vals=2)
    assert uit["als tweede bevestiger"] and uit["als filter"]
    a[V]["boven"] = 6
    uit = bvm.v3_beslissing(a, {"vals": 2}, {"zelfde beeld": 12, "vals": 1}, sift_vals=2)
    assert not uit["als tweede bevestiger"] and not uit["als filter"]


def test_a_row_with_image_bytes_is_never_written(tmp_path):
    with pytest.raises(ValueError):
        bvm.schrijf(tmp_path / "x.jsonl", [{"vraag": "q", "inhoud": b"\x89PNG"}])
    bvm.schrijf(tmp_path / "x.jsonl", [{"vraag": "q", "sift": [["b", "g", "a", 3, 0.1]]}])
    assert (tmp_path / "x.jsonl").read_text().count("\n") == 1
