"""De kandidaat-rechters op de rechterset (PLAN #30.3): één keuze op de
ontwikkelhelft, de meethelft pas daarna en alleen op verzoek.
"""

import pytest

from doublecheck import rechtermeting as rm


def _paar(label, score, rol="leren", soort="parafrase", zaak="c"):
    return {"label": label, "score": score, "rol": rol, "soort": soort, "zaak": zaak}


def test_the_working_point_is_the_lowest_threshold_that_keeps_precision():
    rijen = [_paar("zelfde", 0.95), _paar("zelfde", 0.90), _paar("verwant", 0.85), _paar("zelfde", 0.80),
             _paar("tegenspraak", 0.10)]
    punt = rm.werkpunt(rijen, doel=0.995)
    assert punt["drempel"] == pytest.approx(0.90)
    assert punt["vindkans"] == pytest.approx(2 / 3)
    assert punt["fout"] == 0


def test_a_perfect_judge_finds_everything_at_full_precision():
    rijen = [_paar("zelfde", 0.9), _paar("zelfde", 0.8), _paar("verwant", 0.3), _paar("tegenspraak", 0.1)]
    assert rm.werkpunt(rijen)["vindkans"] == 1.0
    assert rm.auc(rijen) == 1.0


def test_a_judge_that_ranks_a_wrong_pair_on_top_finds_nothing():
    rijen = [_paar("verwant", 0.99), _paar("zelfde", 0.9), _paar("zelfde", 0.8)]
    assert rm.werkpunt(rijen)["vindkans"] == 0.0


def test_the_measurement_half_stays_out_unless_asked():
    keuze = next(z for z in (f"gfc-{i}" for i in range(100)) if rm.deel(z) == "keuze")
    rijen = [_paar("zelfde", 0.9, "leren", zaak=keuze), _paar("zelfde", 0.9, "meten", zaak=keuze)]
    assert [r["rol"] for r in rm.deelname(rijen, toets=False)] == ["leren"]
    assert [r["rol"] for r in rm.deelname(rijen, toets=True)] == ["meten"]


def test_no_candidate_is_chosen_on_what_it_learned_from():
    rijen = [_paar("zelfde", 0.5, rol, soort=soort, zaak=f"gfc-{i}") for i in range(500)
             for rol in ("leren", "meten") for soort in ("parafrase", "rolwissel")]
    les, keuze, meten = rm.lesstof(rijen), rm.deelname(rijen, False), rm.deelname(rijen, True)
    assert {r["zaak"] for r in les}.isdisjoint({r["zaak"] for r in keuze})
    assert all(r["rol"] == "leren" for r in les + keuze)
    assert 0.15 < len({r["zaak"] for r in keuze}) / 500 < 0.25
    assert not any(r in les or r in keuze for r in meten)


def test_the_pair_key_does_not_depend_on_other_fields():
    a = {"vraag": "x", "kandidaat": "y", "label": "zelfde"}
    b = {"vraag": "x", "kandidaat": "y", "label": "verwant", "bron": "28.6c"}
    assert rm.sleutel(a) == rm.sleutel(b) != rm.sleutel({"vraag": "y", "kandidaat": "x"})


def test_the_simulation_decides_with_the_same_rule_as_categorize():
    import dataclasses

    from doublecheck.config import load_config

    t = dataclasses.replace(load_config().thresholds, text_match=0.87, text_match_crosslingual=0.87,
                            rechter_vloer=0.80, rechter_zelfde=0.98, rechter_veto=0.30)
    gelezen = [["c0", 0.92, 0.50], ["c1", 0.83, 0.99], ["c2", 0.79, 0.999]]
    assert rm.simuleer(gelezen, t) in ("c0", "c1")
    assert rm.simuleer([["c2", 0.79, 0.999]], t) is None  # onder de vloer
    assert rm.simuleer([["c0", 0.92, 0.10]], t) is None  # veto
    assert rm.simuleer([["c1", 0.83, 0.97]], t) is None  # niet zeker genoeg om op te tillen
    assert rm.simuleer([], t) is None
    assert rm.simuleer([["c0", 0.92, 0.50, True]], t) is None  # de getallen- en ontkenningsregel (DR8)
    assert rm.simuleer([["c0", 0.92, 0.50, False]], t) == "c0"


@pytest.mark.parametrize("cid, sim, mens, haiku, verwacht", [
    ("doel", {}, None, None, "gevonden"),
    ("x", {("P1:a", "x"): "zelfde"}, "anders", None, "goed_ander"),
    ("x", {}, None, "zelfde", "goed_ander"),
    ("x", {}, None, "verwant", "fout_haiku"),
    ("k", {}, "anders", "zelfde", "fout_mens"),
    ("y", {}, None, None, "onbekend"),
    (None, {}, None, None, None),
])
def test_a_simulated_hit_is_judged_by_the_most_specific_label(cid, sim, mens, haiku, verwacht):
    r = {"set": "P1", "sleutel": "P1:a", "doelen": ["doel"], "kandidaat": "k", "uitkomst": "ander"}
    labels = {"P1:a": mens} if mens else {}
    hk = {("doel", cid): haiku} if haiku else {}
    assert rm.treffer(r, cid, labels, sim, hk) == verwacht


def _rooster():
    rooster = []
    for v in (0.80, 0.81):
        for z in (0.90, 0.93, 0.95, 0.96, 0.97, 0.98):
            for w in (0.01, 0.1, 0.2, 0.3):
                gevonden = int(100 - (z - 0.9) * 200 - (v - 0.8) * 500 - (w >= 0.3) * 3)
                fout = 1 if z < 0.95 else 0
                rooster.append({"vloer": v, "zelfde": z, "veto": w, "gevonden": gevonden, "fout_mens": fout})
    return rooster


def test_the_rule_takes_the_first_clean_threshold_plus_two_steps():
    keuze = rm.kies_volgens_regel(_rooster())
    assert keuze["zelfde"] == 0.97


def test_the_rule_takes_the_floor_that_finds_most():
    assert rm.kies_volgens_regel(_rooster())["vloer"] == 0.80


def test_the_rule_takes_the_strictest_veto_that_costs_nothing():
    assert rm.kies_volgens_regel(_rooster())["veto"] == 0.2


def test_the_rule_never_returns_a_setting_with_an_error_or_an_unknown():
    rooster = [{"vloer": 0.8, "zelfde": 0.95, "veto": 0.1, "gevonden": 50, "onbekend": 1}]
    assert rm.kies_volgens_regel(rooster) is None


def test_the_rule_still_chooses_when_the_mildest_veto_is_never_clean():
    rooster = []
    for z in (0.90, 0.93, 0.95, 0.96, 0.97):
        for w in (0.01, 0.1, 0.4, 0.5):
            fout = 1 if w < 0.4 or z < 0.93 else 0
            rooster.append({"vloer": 0.8, "zelfde": z, "veto": w, "gevonden": int(100 - z * 50 - w * 10),
                            "fout_mens": fout})
    keuze = rm.kies_volgens_regel(rooster)
    assert keuze["zelfde"] == 0.96 and keuze["veto"] == 0.4


@pytest.mark.parametrize("cel, schoon", [
    ({"gevonden": 5}, True),
    ({"gevonden": 5, "hard_n": 1000, "hard_fout": 20}, True),
    ({"gevonden": 5, "hard_n": 1000, "hard_fout": 21}, False),
    ({"gevonden": 5, "paar_fout": 1}, False),
    ({"gevonden": 5, "onbekend": 1}, False),
])
def test_a_setting_is_clean_only_within_the_bar_on_hard_negatives_and_without_any_real_error(cel, schoon):
    assert rm._schoon(cel) is schoon


def test_a_true_sentence_matched_to_a_debunked_claim_is_an_error():
    import dataclasses

    from doublecheck.config import load_config

    t = dataclasses.replace(load_config().thresholds, rechter_vloer=0.80, rechter_zelfde=0.9, rechter_veto=0.3)
    klasse = {"c-rood": "rood", "c-groen": "groen"}
    assert rm.paar_fout([["c-rood", 0.9, 0.5, False]], t, klasse) is True
    assert rm.paar_fout([["c-groen", 0.9, 0.5, False]], t, klasse) is False
    assert rm.paar_fout([["c-rood", 0.9, 0.1, False]], t, klasse) is False  # het veto houdt hem tegen
