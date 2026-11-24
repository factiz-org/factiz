"""De artikellezer (#30.11b): welke claims hij leest bij een tekst van
meerdere eenheden."""

from doublecheck.artikellezer import beste_claims


def test_each_claim_counts_once_with_its_best_unit():
    per_eenheid = [[("a", 0.62), ("b", 0.58)], [("b", 0.71), ("c", 0.55)], [("a", 0.60)]]
    assert beste_claims(per_eenheid, k=5, vloer=0.5) == [("b", 0.71, 1), ("a", 0.62, 0), ("c", 0.55, 1)]


def test_below_the_floor_nothing_is_read_and_at_most_k_are():
    per_eenheid = [[("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.45)]]
    assert beste_claims(per_eenheid, k=2, vloer=0.5) == [("a", 0.9, 0), ("b", 0.8, 0)]
    assert [c for c, _, _ in beste_claims(per_eenheid, k=5, vloer=0.5)] == ["a", "b", "c"]


def test_a_tie_goes_to_the_earlier_unit():
    assert beste_claims([[("a", 0.7)], [("a", 0.7)]], k=5, vloer=0.5) == [("a", 0.7, 0)]


def test_the_trial_counts_articles_above_the_highest_web_text():
    from doublecheck.artikellezer import uitslag_voorproef

    regels = [
        {"set": "P2", "sleutel": "p1", "verwacht": True, "a_x": 0.9},
        {"set": "P2", "sleutel": "p1", "verwacht": False, "a_x": 0.95},
        {"set": "P2", "sleutel": "p2", "verwacht": True, "a_x": 0.5},
        {"set": "N1", "sleutel": "w1", "verwacht": False, "a_x": 0.6},
        {"set": "N1", "sleutel": "w1", "verwacht": False, "a_x": 0.1},
        {"set": "N1", "sleutel": "w2", "verwacht": False, "a_x": 0.3},
    ]
    uit = uitslag_voorproef(regels, n_p2=3)["a_x"]
    assert uit["verwacht_in_kandidaten"] == 2 and uit["webtekst_n"] == 2
    assert uit["grens"]["0_vals"] == 0.6 and uit["gevonden"]["0_vals"] == 1
    assert uit["gevonden"]["1_vals"] == 2  # boven de op één na hoogste webtekst (0,3): p1 en p2
    assert uit["auc"] == 0.75


def test_a_case_with_a_cluster_member_in_the_test_half_never_becomes_lesson_material():
    from doublecheck.artikellezer import mag_mee

    helft = {"a": "ontwikkel", "b": "ontwikkel", "c": "toets"}.get
    assert mag_mee({"a", "b"}, helft)
    assert not mag_mee({"a", "c"}, helft)


def test_only_a_sure_answer_becomes_a_label_and_refuting_is_not_asserting():
    from doublecheck.artikellezer import label_uit

    assert label_uit('{"oordeel": "beweert", "zeker": true}') == 1
    assert label_uit('{"oordeel": "weerlegt", "zeker": true}') == 0
    assert label_uit('{"oordeel": "niet", "zeker": true}') == 0
    assert label_uit('{"oordeel": "beweert", "zeker": false}') is None
    assert label_uit("geen json") is None


def test_a_pair_key_is_short_stable_and_fit_for_the_batch_api():
    import re

    from doublecheck.artikellezer import paarsleutel

    s = paarsleutel("claim", "tekst")
    assert s == paarsleutel("claim", "tekst") != paarsleutel("tekst", "claim")
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", s)


def test_training_takes_only_labelled_lesson_pairs_and_caps_the_web_text():
    from doublecheck.artikellezer import lesparen

    regels = ([{"deel": "les", "label": 1, "bron": "eu-samenvatting"}] * 3
              + [{"deel": "keuze", "label": 1, "bron": "eu-samenvatting"}]
              + [{"deel": "les", "label": None, "bron": "eu-buur"}]
              + [{"deel": "les", "label": 0, "bron": "webtekst", "n": i} for i in range(10)])
    uit = lesparen(regels, web_n=4)
    assert sum(r["bron"] == "eu-samenvatting" for r in uit) == 3
    assert sum(r["bron"] == "webtekst" for r in uit) == 4
    assert lesparen(regels, web_n=4) == uit


def test_the_choice_takes_per_floor_the_lowest_threshold_without_web_text_then_the_floor_that_finds_most():
    from doublecheck.artikellezer import kies_drempels

    rijen = [
        # artikel 1: verwacht op 0,62 met score 0,96
        {"set": "P2", "sleutel": "a1", "verwacht": True, "gelijkenis": 0.62, "score": 0.96},
        {"set": "P2", "sleutel": "a1", "verwacht": False, "gelijkenis": 0.70, "score": 0.30},
        # artikel 2: verwacht op 0,52 met score 0,99
        {"set": "P2", "sleutel": "a2", "verwacht": True, "gelijkenis": 0.52, "score": 0.99},
        # artikel 3: een andere claim wint
        {"set": "P2", "sleutel": "a3", "verwacht": True, "gelijkenis": 0.66, "score": 0.97},
        {"set": "P2", "sleutel": "a3", "verwacht": False, "gelijkenis": 0.65, "score": 0.98},
        # webtekst: 0,93 op 0,55 en 0,90 op 0,61
        {"set": "N1", "sleutel": "w1", "verwacht": False, "gelijkenis": 0.55, "score": 0.93},
        {"set": "N1", "sleutel": "w2", "verwacht": False, "gelijkenis": 0.61, "score": 0.90},
    ]
    uit = kies_drempels(rijen, vloeren=(0.50, 0.60), drempels=(0.9, 0.95, 0.99))
    assert uit["per_vloer"]["0.5"] == {"drempel": 0.95, "gevonden": 2, "ander": 1, "webtekst": 0}
    assert uit["per_vloer"]["0.6"] == {"drempel": 0.95, "gevonden": 1, "ander": 1, "webtekst": 0}
    assert uit["gekozen"] == {"vloer": 0.5, "drempel": 0.95}


def _config_lezer(diepte=5):
    import dataclasses

    from doublecheck.config import ArtikellezerSettings, load_config

    basis = load_config()
    return dataclasses.replace(basis, thresholds=dataclasses.replace(basis.thresholds, artikel_vloer=0.70,
                                                                     artikel_zelfde=0.80),
                               artikellezer=ArtikellezerSettings(aan=True, model="nep", pad="nep", diepte=diepte))


def test_the_reader_reads_the_best_claims_over_the_units_and_the_highest_score_wins():
    from doublecheck.artikellezer import lees
    from doublecheck.search import Candidate

    lijsten = [[Candidate("a", 0.66), Candidate("b", 0.72)], [Candidate("c", 0.75, via="vertaling"), Candidate("a", 0.71)]]
    gelezen = []

    def scorer(paren):
        gelezen.append(paren)
        return [{"claim a": 0.9, "claim b": 0.3, "claim c": 0.85}[c] for c, _ in paren]

    kandidaat, score, eenheid = lees(_config_lezer(), "het artikel", lijsten, lambda c: f"claim {c}", scorer)
    assert (kandidaat.claim_id, kandidaat.similarity, score, eenheid) == ("a", 0.71, 0.9, 1)
    assert [c for c, _ in gelezen[0]] == ["claim c", "claim b", "claim a"]
    assert all(t == "het artikel" for _, t in gelezen[0])


def test_the_reader_keeps_the_route_of_a_match_through_a_variant():
    from doublecheck.artikellezer import lees
    from doublecheck.search import Candidate

    kandidaat, _, _ = lees(_config_lezer(), "t", [[Candidate("c", 0.75, via="vertaling")]], str, lambda p: [0.9])
    assert kandidaat.via == "vertaling"


def test_below_the_floor_the_reader_reads_nothing():
    from doublecheck.artikellezer import lees
    from doublecheck.search import Candidate

    def nooit(paren):
        raise AssertionError("niets boven de vloer, niets te lezen")

    assert lees(_config_lezer(), "t", [[Candidate("a", 0.6)]], str, nooit) is None


def test_only_web_text_from_the_lesson_part_leaves_the_false_alarm_count(tmp_path):
    import json

    from doublecheck.artikellezer import webtekst_in_lesstof
    from doublecheck.rechtermeting import deel

    sleutels = [f"N1:pool:{i}" for i in range(200)]
    les = next(s for s in sleutels if deel(s) == "les")
    keuze = next(s for s in sleutels if deel(s) == "keuze")
    pad = tmp_path / "voorproef.jsonl"
    pad.write_text("".join(json.dumps(r) + "\n" for r in [
        {"set": "N1", "sleutel": les}, {"set": "N1", "sleutel": keuze}, {"set": "P2", "sleutel": "P2:a#c"}]))
    assert webtekst_in_lesstof(pad) == {les}
    assert webtekst_in_lesstof(tmp_path / "ontbreekt.jsonl") == set()


def test_candidates_from_stored_unit_vectors_are_those_of_one_pass(monkeypatch):
    # De zeef embedt eerst alle eenheden en laadt pas daarna de index, zodat
    # bge-m3 en de index nooit samen in het geheugen staan (2026-10-22, lezer
    # B: de Mac swapte). Dezelfde kandidaten als in één keer.
    import numpy as np

    from doublecheck import artikellezer, search, zeef

    rng = np.random.default_rng(3011)
    claims = rng.normal(size=(40, 8)).astype(np.float32)
    varianten = rng.normal(size=(30, 8)).astype(np.float32)
    claims /= np.linalg.norm(claims, axis=1, keepdims=True)
    varianten /= np.linalg.norm(varianten, axis=1, keepdims=True)
    ids = [f"c{i}" for i in range(40)]
    monkeypatch.setattr(search, "_tekstmatrix", lambda conn, versie: (ids, claims))
    monkeypatch.setattr(search, "_variantenmatrix", lambda conn, versie: ([ids[i % 40] for i in range(30)], None,
                                                                          varianten, None))
    monkeypatch.setattr(artikellezer, "_apparaat", lambda: "cpu")

    def vectoren(teksten, versie):
        uit = np.stack([claims[sum(map(ord, t)) % 40] + 0.05 * varianten[len(t) % 30] for t in teksten])
        return (uit / np.linalg.norm(uit, axis=1, keepdims=True)).astype(np.float32)

    monkeypatch.setattr(zeef, "_vectoren_gpu", vectoren)
    teksten = ["Eerste zin van een artikel hier. Tweede zin die ook meetelt.",
               "Een tekst met maar één zin die lang genoeg is.",
               "Nog een artikel. Met drie zinnen die tellen. En de laatste zin hier."]
    artikellezer._MATRICES.clear()
    ineens = artikellezer._kandidaten(teksten, None, "v", k=3, vloer=0.0)
    artikellezer._MATRICES.clear()
    per_tekst, v = artikellezer._eenheidvectoren(teksten, "v")
    artikellezer._MATRICES.clear()
    assert artikellezer._kandidaten_uit(per_tekst, v, None, "v", k=3, vloer=0.0) == ineens
    assert sum(map(len, per_tekst)) == len(v) and all(ineens)
    artikellezer._MATRICES.clear()
