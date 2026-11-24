"""`lezer-v7` op echte screenshots (PLAN #32.33): de sets van §201, de eigen check als bewijs, en de eisen vooraf."""

import pytest

from doublecheck import screenshotlezer as sl


def _rij(id_, set_, kleur, bronnen=(), uitkomst=None, vraag="v"):
    return {"id": id_, "set": set_, "kleur": kleur, "uitkomst": uitkomst or {"rood": "klopt niet", "oranje": "misleidend",
            "groen": "klopt"}.get(kleur, "onzeker"), "route": "zoeken", "bronnen": list(bronnen), "vraag": vraag,
            "kosten": 0.01}


EIGEN = "https://www.boomlive.in/old-flood/"
CHECK = {"soort": "check van een redactie", "url": EIGEN, "redactie": "BOOM", "oordeel": "onwaar"}
ANDER = {"url": "https://www.reuters.com/fact-check/x", "site": "reuters.com", "band": "goed", "rol": "spreekt tegen"}


def _stukken(n_n=3, n_w=2):
    return ([{"id": f"n{i}", "set": "N", "eigen_urls": [EIGEN]} for i in range(n_n)]
            + [{"id": f"w{i}", "set": "W", "eigen_urls": []} for i in range(n_w)])


def test_the_set_takes_the_own_claims_of_201_and_all_urls_of_their_group():
    rijen = [{"id": "n-sn-000", "set": "N", "tekst": "DIFFERENCE IS CLEAR", "datum": "2021-11-10",
              "eigen": ["gfc-1"], "beeld": "/pad/01878.jpg", "geheugen": []},
             {"id": "w-00696", "set": "W", "tekst": "Hezbollah hung a picture", "datum": "2024-01-08", "eigen": None}]
    uit = sl.stukken_uit(rijen, {"g1": {"https://b/2", "https://a/1"}}, {"gfc-1": "g1"})
    assert uit[0] == {"id": "n-sn-000", "set": "N", "tekst": "DIFFERENCE IS CLEAR", "datum": "2021-11-10",
                      "eigen": ["g1"], "eigen_urls": ["https://a/1", "https://b/2"]}
    assert uit[1]["eigen"] == [] and uit[1]["eigen_urls"] == [] and "beeld" not in uit[1]  # nooit het beeld


def test_a_warning_counts_as_evidence_with_the_own_check_even_without_a_label():
    rijen = [_rij("n0", "N", "rood", [CHECK]), _rij("n1", "N", "rood", [ANDER]), _rij("n2", "N", None),
             _rij("w0", "W", "groen"), _rij("w1", "W", None)]
    uit = sl.telling(rijen, _stukken(), {"n1": "bewijst"})
    assert uit["N"]["gewaarschuwd met bewijs"] == 2 and uit["N"]["met de eigen check"] == 1
    assert uit["W"].get("vals alarm", 0) == 0 and uit["W"]["kleur groen"] == 1


def test_counting_refuses_while_a_green_at_n_or_an_alarm_at_w_or_an_unproven_alarm_has_no_label():
    for rij in (_rij("n0", "N", "groen"), _rij("w0", "W", "oranje"), _rij("n1", "N", "rood", [ANDER])):
        with pytest.raises(sl.Weigering):
            sl.telling([rij], _stukken(), {})
    assert sl.telling([_rij("n0", "N", "rood", [CHECK])], _stukken(), {})["N"]["gewaarschuwd met bewijs"] == 1


def test_counting_refuses_unknown_labels_and_answers_from_two_questions():
    with pytest.raises(sl.Weigering):
        sl.telling([_rij("n0", "N", "groen")], _stukken(), {"n0": "misschien"})
    with pytest.raises(sl.Weigering):
        sl.telling([_rij("n0", "N", None), _rij("n1", "N", None, vraag="ander")], _stukken(), {})


def test_the_three_requirements_are_those_fixed_beforehand_and_an_incomplete_run_never_meets_them():
    stukken = _stukken(n_n=58, n_w=60)
    rijen = ([_rij(f"n{i}", "N", "rood", [CHECK]) for i in range(37)] + [_rij(f"n{i}", "N", None) for i in range(37, 57)]
             + [_rij("n57", "N", "groen")] + [_rij(f"w{i}", "W", "rood") for i in range(3)]
             + [_rij(f"w{i}", "W", "groen") for i in range(3, 60)])
    labels = {"n57": "vals groen", "w0": "vals", "w1": "vals", "w2": "vals"}
    eisen = sl.telling(rijen, stukken, labels)["eisen"]
    assert list(eisen.values()) == [True, True, True] and len(eisen) == 3
    eisen = sl.telling(rijen, stukken, {**labels, "w0": "set fout", "n57": "set fout"})["eisen"]
    assert all(eisen.values())
    meer = sl.telling(rijen + [_rij("w60", "W", "oranje")], stukken + [{"id": "w60", "set": "W", "eigen_urls": []}],
                      {**labels, "w60": "vals"})["eisen"]
    assert list(meer.values()) == [True, True, False]
    assert not any(sl.telling(rijen[:10], stukken, labels)["eisen"].values())


def test_the_run_is_the_one_of_3232_with_reader_v7_and_its_own_limit():
    assert sl.RONDE["lezer"] == "lezer-v7" and sl.RONDE["sets"] == ("N", "W") and sl.RONDE["budget"] == 1.60


def test_the_image_round_has_its_own_four_requirements_fixed_beforehand():
    r = sl.RONDES["beeld"]
    assert r["beeld"] and r["lezer"] == "lezer-v7" and r["budget"] == 2.80
    stukken = _stukken(n_n=58, n_w=60)
    rijen = ([_rij(f"n{i}", "N", "rood", [CHECK]) for i in range(39)] + [_rij(f"n{i}", "N", None) for i in range(39, 58)]
             + [_rij(f"w{i}", "W", "groen") for i in range(25)] + [_rij(f"w{i}", "W", None) for i in range(25, 60)])
    eisen = sl.telling(rijen, stukken, {}, ronde="beeld")["eisen"]
    assert len(eisen) == 4 and all(eisen.values())
    minder = [r if r["id"] != "w0" else {**r, "kleur": None} for r in rijen]
    assert list(sl.telling(minder, stukken, {}, ronde="beeld")["eisen"].values()) == [True, True, True, False]
