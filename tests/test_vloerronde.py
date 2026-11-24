"""De ronde van de vloerstap (PLAN #32.0m, B50): de regels die vóór de eerste vraag
vastlagen."""

import pytest

from doublecheck import vloerronde as vr


def _zin(i, label, deel="V"):
    return {"id": f"{deel}{i:03d}", "deel": deel, "label": label, "tekst": f"zin {label} {i}", "taal": "en"}


def test_o_takes_fifty_true_and_fifty_false_sentences_that_were_never_asked():
    fundament = [_zin(i, "waar", "K") for i in range(80)] + [_zin(i, "onwaar") for i in range(80)]
    gevraagd = {f"K{i:03d}" for i in range(20)} | {f"V{i:03d}" for i in range(10)}
    o = vr.kies_o(fundament, gevraagd, uitgesloten={"zin onwaar 50"})
    assert sum(s["label"] == "waar" for s in o) == 50 and sum(s["label"] == "onwaar" for s in o) == 50
    assert not {s["oud_id"] for s in o} & gevraagd and "zin onwaar 50" not in {s["tekst"] for s in o}
    assert all(s["modellen"] == ["sonnet"] and s["kaal"] == ["kaal"] and s["id"].startswith("O:") for s in o)
    assert o == vr.kies_o(fundament, gevraagd, uitgesloten={"zin onwaar 50"})


def _antw(ids):
    return {(i, k): "clearly false" for i in ids for k in ("A", "B")}


ALLES = [{"id": f"w{i}", "label": "waar"} for i in range(30)] + [{"id": f"o{i}", "label": "onwaar"} for i in range(40)]


def test_every_true_message_flagged_by_both_questions_must_be_read_and_counts_unless_the_set_was_wrong():
    antwoorden = {**_antw(["w0", "w1", "o0"]), ("w2", "A"): "clearly false", ("w2", "B"): "not clearly false"}
    with pytest.raises(vr.Weigering):
        vr.bewaking(ALLES, antwoorden, {}, waar_in_rondes=1375)
    t = vr.bewaking(ALLES, antwoorden, {"w0": "vals", "w1": "set fout"}, waar_in_rondes=1375)
    assert t["vals alarm"] == 1 and t["set fout"] == 1 and t["door"] is True
    t = vr.bewaking(ALLES, _antw([f"w{i}" for i in range(5)]), {f"w{i}": "vals" for i in range(5)}, waar_in_rondes=1375)
    assert t["door"] is False  # hoogstens 4 van de 1.375


def test_the_class_is_every_message_both_questions_flag_and_needs_thirty_for_stand_3():
    weinig = vr.klasse(ALLES, _antw([f"o{i}" for i in range(20)]), {})
    assert weinig["n"] == 20 and weinig["stand"] == 5
    genoeg = vr.klasse(ALLES, _antw([f"o{i}" for i in range(35)] + ["w0"]), {"w0": "vals"})
    assert genoeg["n"] == 36 and genoeg["waar"] == 1 and genoeg["stand"] == 3 and genoeg["interval"][1] <= 0.5
    fout_in_de_set = vr.klasse(ALLES, _antw([f"o{i}" for i in range(35)] + ["w0"]), {"w0": "set fout"})
    assert fout_in_de_set["waar"] == 0  # een waar bericht dat eigenlijk onwaar was, telt als onwaar


def _u(kleur, oordeel=None, bronnen=()):
    return {"kleur": kleur, "oordeel": oordeel or {"rood": "klopt niet", "groen": "klopt"}.get(kleur, "onzeker"),
            "bronnen": list(bronnen)}


def test_o_counts_mostly_true_with_the_right_detail_as_right_and_compares_with_the_bare_model():
    stukken = [{"id": f"o{i}", "label": "onwaar"} for i in range(50)] + [{"id": f"w{i}", "label": "waar"}
                                                                          for i in range(50)]
    factiz = {s["id"]: _u("rood" if s["label"] == "onwaar" else "groen") for s in stukken}
    factiz["o0"] = _u(None, "klopt grotendeels")
    kaal = {s["id"]: {**_u("rood" if s["label"] == "onwaar" else "groen"), "bronnen": [{"url": "https://a.org"}]}
            for s in stukken}
    with pytest.raises(vr.Weigering):
        vr.tel_o(stukken, factiz, kaal, {})
    t = vr.tel_o(stukken, factiz, kaal, {("o0", "markering"): "juist"})
    assert t["factiz goed"] == 100 and all(t["eisen"].values())
    t = vr.tel_o(stukken, factiz, kaal, {("o0", "markering"): "fout"})
    assert t["factiz goed"] == 99 and t["eisen"]["niet aantoonbaar slechter dan het kale model"] is True
    slecht = {**factiz, **{f"o{i}": _u(None, "onzeker") for i in range(1, 6)}}
    t = vr.tel_o(stukken, slecht, kaal, {("o0", "markering"): "juist"})
    assert t["eisen"] == {"minstens 95% goed": True, "niet aantoonbaar slechter dan het kale model": False,
                          "nooit onzeker of let op zonder bron waar het kale model het goed heeft met bron": False}


def test_o2_never_reuses_a_sentence_of_o_and_draws_with_its_own_seed():
    fundament = [_zin(i, "waar", "K") for i in range(120)] + [_zin(i, "onwaar") for i in range(120)]
    o = vr.kies_o(fundament, set(), set())
    o2 = vr.kies_o(fundament, {s["oud_id"] for s in o}, set(), zaad=vr.ZAAD_O2, voorvoegsel="O2")
    assert len(o2) == 100 and not {s["oud_id"] for s in o} & {s["oud_id"] for s in o2}
    assert all(s["id"].startswith("O2:") and s["set"] == "O2" for s in o2)


def test_a_true_sentence_turned_red_by_the_floor_fails_the_round():
    stukken = [{"id": "w1", "label": "waar"}, {"id": "o1", "label": "onwaar"}]
    factiz = {"w1": {**_u("rood"), "regels": ["algemene kennis"]}, "o1": {**_u("rood"), "regels": ["algemene kennis"]}}
    t = vr.vloerrood(stukken, factiz)
    assert t == {"vloerstap rood": 2, "waar rood door de vloerstap": 1, "door": False}
    assert vr.vloerrood(stukken, {"o1": factiz["o1"]})["door"] is True
