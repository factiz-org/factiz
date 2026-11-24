"""De zeef: de meetmachine per versie (PLAN #30.1, B33).

Versie 1 gaat de deur uit als Factiz in een grote, gemengde berg minstens 70%
vindt van wat al ontkracht is, bij een bovengrens van hoogstens 1 vals alarm
per 100.000 stukken. De rekenkern hier is vastgelegd vóór de eerste meting:
een vaste helft per stuk, tekst, artikelen en beelden even zwaar, vals alarm
tegen de hele berg, en van de toetshelft alleen totalen.
"""

import pytest

from doublecheck import zeef


def test_every_piece_lands_in_the_same_half_every_round():
    sleutels = [f"P1:https://voorbeeld.example/check/{i}" for i in range(2000)]
    eerste = [zeef.helft(s) for s in sleutels]
    assert eerste == [zeef.helft(s) for s in sleutels]
    assert set(eerste) == {"ontwikkel", "toets"}
    assert 900 < eerste.count("toets") < 1100


@pytest.mark.parametrize("terugkijk, verwacht", [
    ("gevonden", "gevonden"), ("ander record", "ander"), ("verwant", "verwant"),
    ("tegenspraak", "niets"), ("niets", "niets"),
])
def test_on_the_text_set_only_the_expected_check_counts_as_found(terugkijk, verwacht):
    assert zeef.uitkomst_p1(terugkijk) == verwacht


@pytest.mark.parametrize("beoordeeld, verwacht", [
    ("gevonden", "gevonden"), ("fout", "ander"), ("verwant", "verwant"), ("niets", "niets"),
])
def test_on_articles_and_images_a_match_on_another_claim_is_not_found(beoordeeld, verwacht):
    assert zeef.uitkomst_resolver(beoordeeld) == verwacht


def _regels(set_, uitkomsten, helft="ontwikkel"):
    return [{"set": set_, "sleutel": f"{set_}:{i}", "helft": helft, "taal": "en", "uitkomst": u}
            for i, u in enumerate(uitkomsten)]


def test_the_headline_weighs_text_articles_and_images_equally():
    regels = (_regels("P1", ["gevonden"] * 9 + ["niets"])          # 90%
              + _regels("P2", ["gevonden"] + ["niets"] * 99)       # 1%
              + _regels("P3", ["gevonden"] * 5 + ["niets"] * 5))   # 50%
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 1000}, "toets": {"N1": 1000}}, {})
    assert uit["ontwikkel"]["hoofdgetal"] == pytest.approx((0.9 + 0.01 + 0.5) / 3)
    assert uit["ontwikkel"]["sets"]["P2"]["vindkans"] == pytest.approx(0.01)


def test_a_false_alarm_counts_against_the_whole_berg_with_its_bound():
    regels = (_regels("P1", ["gevonden", "ander"])
              + [{"set": "N1", "sleutel": "N1:x", "helft": "ontwikkel", "taal": "en", "uitkomst": "matched"}])
    labels = {"P1:1": "anders", "N1:x": "vals"}
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 99_998}, "toets": {"N1": 0}}, labels)
    vals = uit["ontwikkel"]["vals_alarm"]
    assert vals["vals"] == 2 and vals["berg"] == 100_000
    assert vals["per_100k"] == pytest.approx(2.0)
    assert vals["bovengrens_per_100k"] > 2.0


def test_an_unlabelled_other_claim_or_negative_match_blocks_the_count():
    regels = _regels("P1", ["ander"])
    with pytest.raises(zeef.Weigering):
        zeef.uitslag(regels, {"ontwikkel": {"N1": 10}, "toets": {"N1": 0}}, {})
    negatief = [{"set": "N1", "sleutel": "N1:y", "helft": "toets", "taal": "en", "uitkomst": "matched"}]
    with pytest.raises(zeef.Weigering):
        zeef.uitslag(negatief, {"ontwikkel": {"N1": 0}, "toets": {"N1": 10}}, {})


def test_the_same_claim_under_another_record_is_neither_found_nor_false():
    regels = _regels("P1", ["gevonden", "ander"])
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 100}, "toets": {"N1": 0}}, {"P1:1": "zelfde"})
    assert uit["ontwikkel"]["sets"]["P1"]["gevonden"] == 1
    assert uit["ontwikkel"]["sets"]["P1"]["ander_zelfde"] == 1
    assert uit["ontwikkel"]["vals_alarm"]["vals"] == 0


def test_the_bar_is_seventy_percent_and_one_per_hundred_thousand():
    assert zeef.haalt_de_lat(0.70, 0.9) and not zeef.haalt_de_lat(0.69, 0.9)
    assert not zeef.haalt_de_lat(0.95, 1.2)


def test_of_the_test_half_only_totals_come_out():
    regels = (_regels("P1", ["gevonden", "niets"], helft="toets")
              + _regels("P1", ["gevonden"], helft="ontwikkel"))
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 10}, "toets": {"N1": 10}}, {})
    tekst = zeef.verslag(uit)
    assert "P1:0" not in tekst and "P1:1" not in tekst
    assert "toets" in tekst and "hoofdgetal" in tekst


def test_a_red_verdict_next_to_an_established_fact_counts_against_the_berg():
    feiten = [{"set": "N3", "sleutel": f"N3:feit#{i}", "helft": "toets", "taal": "en", "uitkomst": u}
              for i, u in enumerate(["rood", "omstreden", "deels-waar", "waar", "niets"])]
    uit = zeef.uitslag(feiten, {"ontwikkel": {"N1": 0}, "toets": {"N1": 995}}, {})
    vals = uit["toets"]["vals_alarm"]
    assert vals["vals"] == 2 and vals["berg"] == 1_000
    n3 = uit["toets"]["N3"]
    assert (n3["n"], n3["rood"], n3["omstreden"], n3["twijfel"]) == (5, 1, 1, 1)
    assert uit["kern"] == {"formuleringen": 5, "rood_of_omstreden": 2}


def test_a_red_verdict_on_a_wikipedia_sentence_is_a_false_alarm_but_not_a_core_failure():
    regels = [{"set": "N3", "sleutel": "N3:paar:1", "helft": "toets", "taal": "en", "uitkomst": "rood", "bron": "paar"},
              {"set": "N3", "sleutel": "N3:feit#0", "helft": "toets", "taal": "en", "uitkomst": "niets", "bron": "kern"}]
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 0}, "toets": {"N1": 98}}, {})
    assert uit["toets"]["vals_alarm"]["vals"] == 1
    assert uit["kern"] == {"formuleringen": 1, "rood_of_omstreden": 0}


def test_precision_counts_every_matched_answer_and_its_errors_with_a_bound():
    regels = (_regels("P1", ["gevonden", "ander", "ander", "verwant"])
              + [{"set": "N1", "sleutel": "N1:a", "helft": "ontwikkel", "taal": "en", "uitkomst": "matched"},
                 {"set": "N3", "sleutel": "N3:f#0", "helft": "ontwikkel", "taal": "en", "uitkomst": "rood"},
                 {"set": "N3", "sleutel": "N3:f#1", "helft": "ontwikkel", "taal": "en", "uitkomst": "waar"}])
    labels = {"P1:1": "zelfde", "P1:2": "anders", "N1:a": "vals"}
    p = zeef.uitslag(regels, {"ontwikkel": {"N1": 100}, "toets": {"N1": 0}}, labels)["ontwikkel"]["precisie"]
    assert (p["matched"], p["fout"]) == (6, 3)
    assert p["precisie"] == pytest.approx(0.5)
    assert p["bovengrens_fout"] > 0.5


@pytest.mark.parametrize("aantal, emmer", [(0, "stil"), (2, "stil"), (3, "druk"), (29, "druk"), (30, "heel druk")])
def test_drukte_buckets_are_fixed_before_the_measurement(aantal, emmer):
    assert zeef.emmer(aantal) == emmer


def test_finding_and_precision_are_reported_per_drukte_bucket():
    regels = [
        {"set": "P1", "sleutel": "P1:0", "helft": "toets", "taal": "en", "uitkomst": "gevonden", "drukte": 1},
        {"set": "P1", "sleutel": "P1:1", "helft": "toets", "taal": "en", "uitkomst": "niets", "drukte": 1},
        {"set": "P2", "sleutel": "P2:0", "helft": "toets", "taal": "en", "uitkomst": "ander", "drukte": 50},
        {"set": "P3", "sleutel": "P3:0", "helft": "toets", "taal": "en", "uitkomst": "gevonden", "drukte": 50},
    ]
    uit = zeef.uitslag(regels, {"ontwikkel": {"N1": 0}, "toets": {"N1": 10}}, {"P2:0": "anders"})
    d = uit["toets"]["drukte"]
    assert d["stil"]["n"] == 2 and d["stil"]["vindkans"] == pytest.approx(0.5) and d["stil"]["matched"] == 1
    assert d["heel druk"]["n"] == 2 and d["heel druk"]["fout"] == 1 and d["heel druk"]["precisie"] == pytest.approx(0.5)


# De uitsplitsing van #30.11b, vastgelegd vóór de zeefrun van de lezer: de
# lezer leerde van het lesdeel van de ontwikkelhelft, dus beslist alleen wat
# hij nooit zag.

def _zaken(deel_, n):
    from doublecheck.rechtermeting import deel

    return [c for c in (f"zaak-{i}" for i in range(10_000)) if deel(c) == deel_][:n]


def _ontwikkel_n1(n):
    return [s for s in (f"N1:pool:{i}" for i in range(10_000)) if zeef.helft(s) == "ontwikkel"][:n]


def test_the_reader_decision_counts_articles_only_where_the_reader_never_learned():
    keuze, les = _zaken("keuze", 2), _zaken("les", 3)
    regels = ([{"set": "P2", "sleutel": f"P2:a#{c}", "helft": "ontwikkel", "claim": c, "uitkomst": u}
               for c, u in zip(keuze, ["gevonden", "niets"])]
              + [{"set": "P2", "sleutel": f"P2:b#{c}", "helft": "ontwikkel", "claim": c, "uitkomst": "gevonden"}
                 for c in les]
              + [{"set": "P2", "sleutel": "P2:t#x", "helft": "toets", "claim": keuze[0], "uitkomst": "gevonden"}])
    p2 = zeef.lezerdelen(regels, {}, 0, set())["P2"]
    assert (p2["keuze"]["n"], p2["keuze"]["gevonden"]) == (2, 1)
    assert p2["keuze"]["vindkans"] == pytest.approx(0.5)
    assert (p2["les"]["n"], p2["les"]["gevonden"]) == (3, 3)


def test_web_text_the_reader_learned_from_leaves_the_false_alarm_count():
    geleerd, ander, terecht, nooit_door = _ontwikkel_n1(4)
    regels = [{"set": "N1", "sleutel": s, "helft": "ontwikkel", "uitkomst": "matched"}
              for s in (geleerd, ander, terecht)]
    labels = {geleerd: "vals", ander: "vals", terecht: "terecht"}
    n1 = zeef.lezerdelen(regels, labels, 100, {geleerd, nooit_door})["N1"]
    assert n1 == {"n": 98, "vals": 1, "vals_in_lesstof": 1, "lesstof": 2}
