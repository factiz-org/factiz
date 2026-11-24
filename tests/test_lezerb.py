"""De tweede artikellezer (PLAN #30.11c): de regels die vóór het bouwen
vastlagen (PO 2026-10-22)."""

from doublecheck import lezerb


def _gelabeld(bron, label):
    return {"claim": "c", "tekst": "t", "bron": bron, "label": label}


def test_a_disinformation_article_is_positive_only_when_haiku_is_sure_it_makes_the_claim():
    paren = [_gelabeld("sheffield-desinformatie", 1), _gelabeld("sheffield-desinformatie", 0),
             _gelabeld("sheffield-desinformatie", None)]
    assert [p["label"] for p in lezerb.na_label(paren)] == [1]


def test_a_trustworthy_article_is_negative_only_when_haiku_is_sure_it_does_not_make_the_claim():
    paren = [_gelabeld("sheffield-betrouwbaar", 0), _gelabeld("sheffield-betrouwbaar", 1),
             _gelabeld("sheffield-betrouwbaar", None)]
    assert [p["label"] for p in lezerb.na_label(paren)] == [0]


def test_hard_web_text_keeps_whatever_haiku_is_sure_of():
    paren = [_gelabeld("webtekst-hard", 0), _gelabeld("webtekst-hard", 1), _gelabeld("webtekst-hard", None)]
    assert [p["label"] for p in lezerb.na_label(paren)] == [0, 1]


def test_nothing_from_the_test_half_or_with_a_cluster_member_there_becomes_lesson_or_choice_material():
    helft = {"a": "ontwikkel", "b": "ontwikkel", "c": "toets", "d": "ontwikkel"}.get
    leden = {"a": {"a"}, "b": {"b", "c"}, "c": {"c"}, "d": {"d"}}.get
    deel = {"a": "les", "b": "les", "c": "les", "d": "keuze"}.get
    assert [lezerb.deel_van(c, helft, leden, deel) for c in "abcd"] == ["les", None, None, "keuze"]


def _rij(soort, sleutel, gelijkenis, score, verwacht=False):
    return {"soort": soort, "sleutel": sleutel, "gelijkenis": gelijkenis, "score": score, "verwacht": verwacht}


def test_the_threshold_is_the_lowest_with_no_negative_of_any_kind_above_it():
    rijen = [_rij("positief", "p1", 0.72, 0.85, True), _rij("positief", "p2", 0.72, 0.96, True),
             _rij("webtekst", "w1", 0.71, 0.82), _rij("betrouwbaar", "b1", 0.75, 0.91),
             _rij("ontkrachting", "o1", 1.0, 0.94)]
    uit = lezerb.kies_drempels(rijen, vloeren=(0.70,), drempels=(0.8, 0.9, 0.95, 0.99))
    assert uit["per_vloer"]["0.7"] == {"drempel": 0.95, "gevonden": 1, "ander": 0, "negatief": 0}
    assert uit["gekozen"] == {"vloer": 0.70, "drempel": 0.95}


def test_a_negative_below_the_floor_does_not_count_and_the_floor_with_most_positives_wins():
    rijen = [_rij("positief", "p1", 0.62, 0.99, True), _rij("positief", "p2", 0.72, 0.99, True),
             _rij("webtekst", "w1", 0.61, 0.99)]
    uit = lezerb.kies_drempels(rijen, vloeren=(0.60, 0.70), drempels=(0.9, 0.995))
    assert uit["per_vloer"]["0.6"]["drempel"] == 0.995 and uit["per_vloer"]["0.6"]["gevonden"] == 0
    assert uit["per_vloer"]["0.7"] == {"drempel": 0.9, "gevonden": 1, "ander": 0, "negatief": 0}
    assert uit["gekozen"] == {"vloer": 0.70, "drempel": 0.9}


def test_a_positive_whose_best_candidate_is_another_claim_is_not_found():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True), _rij("positief", "p1", 0.80, 0.97, False)]
    uit = lezerb.kies_drempels(rijen, vloeren=(0.70,), drempels=(0.9,))
    assert uit["per_vloer"]["0.7"] == {"drempel": 0.9, "gevonden": 0, "ander": 1, "negatief": 0}


def test_the_hard_web_text_of_reader_b_is_known_by_its_key(tmp_path):
    import json

    pad = tmp_path / "te-labelen.jsonl"
    pad.write_text("".join(json.dumps(r) + "\n" for r in [
        {"bron": "webtekst-hard", "zaak": "N1:stiltetoets:en-1"}, {"bron": "webtekst-hard", "zaak": "N1:stiltetoets:en-1"},
        {"bron": "sheffield-betrouwbaar", "zaak": "gfc-1"}]))
    assert lezerb.webtekst_hard(pad) == {"N1:stiltetoets:en-1"}
    assert lezerb.webtekst_hard(tmp_path / "ontbreekt.jsonl") == set()


# Van boven naar beneden kiezen (2026-10-22, PO: "eerst de meest economische
# aanpak"): een lagere vloer heeft minstens dezelfde negatieven en dus een
# minstens even hoge drempel; zodra geen lagere vloer meer kan winnen, staat
# de keuze vast, en is ze dezelfde als die van `kies_drempels` op alles.

def test_the_choice_is_final_when_no_lower_floor_can_find_more():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True), _rij("webtekst", "w1", 0.71, 0.82)]
    uit = lezerb.beslist(rijen, onbepaald_onder=0.65, vloeren=(0.60, 0.70), drempels=(0.8, 0.9, 0.99))
    assert uit == {"vloer": 0.70, "drempel": 0.9}


def test_the_choice_waits_while_a_lower_floor_could_still_find_more():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True), _rij("positief", "p2", 0.62, 0.97, True),
             _rij("webtekst", "w1", 0.71, 0.82)]
    assert lezerb.beslist(rijen, onbepaald_onder=0.65, vloeren=(0.60, 0.70), drempels=(0.8, 0.9, 0.99)) is None


def test_with_everything_read_the_choice_is_that_of_the_full_rule():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True), _rij("positief", "p2", 0.62, 0.97, True),
             _rij("webtekst", "w1", 0.71, 0.82), _rij("webtekst", "w2", 0.61, 0.98)]
    volledig = lezerb.kies_drempels(rijen, vloeren=(0.60, 0.70), drempels=(0.8, 0.9, 0.99))["gekozen"]
    assert lezerb.beslist(rijen, onbepaald_onder=-1.0, vloeren=(0.60, 0.70), drempels=(0.8, 0.9, 0.99)) == volledig


def test_a_floor_without_any_clean_threshold_rules_out_every_lower_floor():
    rijen = [_rij("positief", "p1", 0.62, 0.95, True), _rij("webtekst", "w1", 0.71, 0.999)]
    assert lezerb.beslist(rijen, onbepaald_onder=0.65, vloeren=(0.60, 0.70), drempels=(0.9, 0.99)) == {}


# De aanvulling van de keuzeregel (PO 2026-10-22): een negatief paar waarvan
# Haiku zeker zegt dat de tekst de bewering doet, is geen tegenvoorbeeld.

def test_a_negative_pair_that_surely_makes_the_claim_is_no_counterexample():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True), _rij("betrouwbaar", "b1", 0.95, 0.9994),
             _rij("webtekst", "w1", 0.77, 0.965)]
    rijen[1]["claim"], rijen[2]["claim"] = "c1", "c2"
    over = lezerb.zonder_terecht(rijen, terecht={("b1", "c1")})
    assert [r["sleutel"] for r in over] == ["p1", "w1"]
    assert lezerb.kies_drempels(over, vloeren=(0.70,), drempels=(0.95, 0.97, 0.99))["gekozen"] == \
        {"vloer": 0.70, "drempel": 0.97}


def test_a_positive_pair_is_never_dropped_by_the_amendment():
    rijen = [_rij("positief", "p1", 0.72, 0.95, True)]
    rijen[0]["claim"] = "c1"
    assert lezerb.zonder_terecht(rijen, terecht={("p1", "c1")}) == rijen


def test_negatives_already_read_at_a_lower_floor_can_rule_it_out_early():
    # Vloer 0,60 is nog niet volledig gelezen, maar heeft al een negatief van
    # 0,985: haar drempel wordt minstens 0,99, en daar vindt ze niets meer.
    rijen = [_rij("positief", "p1", 0.72, 0.975, True), _rij("positief", "p2", 0.62, 0.98, True),
             _rij("webtekst", "w1", 0.71, 0.96), _rij("webtekst", "w2", 0.61, 0.985)]
    assert lezerb.beslist(rijen, onbepaald_onder=0.65, vloeren=(0.60, 0.70), drempels=(0.97, 0.98, 0.99)) == \
        {"vloer": 0.70, "drempel": 0.97}


# Na de zeef (PLAN #30.11c): de tijd per vraag (B41) en de controle op de
# Sheffield-artikelen uit de toetshelft, alleen totalen.

def test_the_short_texts_for_the_time_have_exactly_two_sentences_and_a_fixed_draw():
    teksten = ["Een zin die lang genoeg is om te tellen. En nog een zin die meetelt.",
               "Maar één zin die lang genoeg is om te tellen.",
               "Eerste zin die meetelt hier. Tweede zin die meetelt hier. Derde zin die meetelt hier.",
               "Nog een tekst van twee zinnen die tellen. De tweede zin telt ook mee."]
    gekozen = lezerb.kies_korte(teksten, n=5, zaad=3011)
    assert sorted(gekozen) == sorted([teksten[0], teksten[3]])
    assert gekozen == lezerb.kies_korte(teksten, n=5, zaad=3011)


def test_the_sheffield_control_counts_found_and_matches_on_trustworthy_articles_apart():
    regels = [{"klasse": "disinformation", "uitkomst": "gevonden"}, {"klasse": "disinformation", "uitkomst": "ander"},
              {"klasse": "disinformation", "uitkomst": "niets"}, {"klasse": "trustworthy", "uitkomst": "gevonden"},
              {"klasse": "trustworthy", "uitkomst": "niets"}]
    uit = lezerb.sheffield_uitslag(regels)
    assert uit["desinformatie"] == {"n": 3, "gevonden": 1, "ander": 1, "verwant": 0, "niets": 1}
    assert uit["betrouwbaar"] == {"n": 2, "matched_eigen_claim": 1, "matched_andere_claim": 0, "verwant": 0, "niets": 1}
