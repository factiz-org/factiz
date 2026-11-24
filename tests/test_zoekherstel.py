"""Het zoeken voor screenshots herstellen (P4 van fase 0, PLAN #32.0b): de regels
die vóór de eerste vraag aan een model vastlagen."""

from doublecheck import zoekherstel as z


def _k(claim, gelijkenis, oordeel="onwaar"):
    return {"claim": claim, "gelijkenis": gelijkenis, "oordeel": oordeel}


def test_merged_searches_keep_the_highest_similarity_per_check_and_the_best_five():
    lijsten = [[_k("a", 0.70), _k("b", 0.65)], [_k("b", 0.80), _k("c", 0.60)],
               [_k("d", 0.75), _k("e", 0.72), _k("f", 0.71), _k("g", 0.50)]]
    samen = z.voeg_samen(lijsten)
    assert [k["claim"] for k in samen] == ["b", "d", "e", "f", "a"]
    assert samen[0]["gelijkenis"] == 0.80


def test_a_hit_is_the_own_check_or_its_cluster_among_the_best_five():
    kandidaten = [_k(c, 0.9 - i / 100) for i, c in enumerate("abcdefg")]
    assert z.treffer(kandidaten, {"e"})
    assert not z.treffer(kandidaten, {"f"})
    assert not z.treffer([], {"a"})


def test_the_queries_are_the_text_the_claims_and_their_phrasings_without_doubles():
    gehaald = [{"bewering": "Video shows a flood in Delhi.", "zoekvragen": ["Delhi flood video", "Delhi flood video"]},
               {"bewering": "  ", "zoekvragen": ["", "Modi said X"]}]
    assert z.zoekvragen("ocr tekst", gehaald) == ["ocr tekst", "Video shows a flood in Delhi.", "Delhi flood video",
                                                 "Modi said X"]
    assert z.zoekvragen("ocr tekst", []) == ["ocr tekst"]


def test_at_most_three_claims_with_two_phrasings_are_read():
    tekst = ('{"beweringen": [' + ", ".join(
        f'{{"bewering": "c{i}", "zoekvragen": ["q{i}a", "q{i}b", "q{i}c"]}}' for i in range(5)) + "]}")
    gehaald = z.lees_extractie(tekst)
    assert len(gehaald) == 3 and all(len(b["zoekvragen"]) == 2 for b in gehaald)
    assert z.lees_extractie("geen json") == [] and z.lees_extractie('{"x": 1}') == []


def test_the_extraction_question_asks_for_claims_not_for_a_verdict():
    verzoek = z.extractieverzoek("x-1", "Ronaldo watching Argentina vs France", "haiku")
    vraag = verzoek["params"]["messages"][0]["content"]
    assert "Ronaldo watching Argentina vs France" in vraag and "Do not judge" in vraag
    assert verzoek["params"]["model"] == "claude-haiku-5-5"
    assert "tools" not in verzoek["params"]  # alleen lezen, niet zoeken


def test_the_count_reports_the_found_and_the_missed_groups_apart():
    stukken = [{"id": "a", "eigen": ["x"], "helft": "toets"}, {"id": "b", "eigen": ["y"], "helft": "ontwikkel"}]
    v0 = {"a": [_k("x", 0.9)], "b": [_k("z", 0.9)]}
    v2 = {"a": [_k("q", 0.9)], "b": [_k("y", 0.9)]}
    telling = z.telling(stukken, {"V0": v0, "V2-haiku": v2})
    assert telling["V0"] == {"treffers": 1, "n": 2, "van de gevonden kwijt": 0, "van de gemiste gevonden": 0}
    assert telling["V2-haiku"] == {"treffers": 1, "n": 2, "van de gevonden kwijt": 1, "van de gemiste gevonden": 1}


def test_each_variant_reads_its_own_ocr():
    assert z.BRON["V0"] == z.BRON["V2-haiku"] == z.BRON["V2-sonnet"] == "tesseract"
    assert z.BRON["V1"] == z.BRON["V3-sonnet"] == "apple"
    assert z.BRON["V4"] == z.BRON["V5-haiku"] == z.BRON["V5-sonnet"] == "google"
    assert set(z.BRON) == set(z.VARIANTEN)


def test_the_google_request_only_asks_to_read_the_text():
    verzoek = z.vision_verzoek(b"\x89PNG")
    assert verzoek == {"requests": [{"image": {"content": "iVBORw=="},
                                     "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]}


def test_reading_the_google_answer():
    assert z.lees_google({"responses": [{"fullTextAnnotation": {"text": "Ronaldo watching\n"}}]}) == "Ronaldo watching\n"
    assert z.lees_google({"responses": [{}]}) == ""
    assert z.lees_google({"responses": [{"error": {"code": 3}}]}) == ""
