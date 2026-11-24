"""De modelpoort (P9 van fase 0, PLAN #32.0f): de regels die vóór de eerste vraag
aan een model vastlagen."""

import pytest

from doublecheck import berichtcontrole as bc
from doublecheck import modelpoort as mp
from doublecheck.config import load_config


def _stuk(i, deel, helft="toets", sub=None):
    return {"id": i, "deel": deel, "sub": sub or deel, "helft": helft, "tekst": f"bericht {i}", "geheugen": [],
            "kandidaten": [], "datum": None, "eigen": []}


def _sets():
    p11 = ([_stuk(f"A{i}", "A") for i in range(25)] + [_stuk(f"Bf{i}", "B", sub="B-feit") for i in range(6)]
           + [_stuk(f"Bk{i}", "B", sub="B-kop") for i in range(8)] + [_stuk(f"Bs{i}", "B", sub="B-schrijver") for i in range(7)]
           + [_stuk(f"C{i}", "C") for i in range(20)] + [_stuk(f"E{i}", "E") for i in range(15)]
           + [_stuk(f"A-o{i}", "A", helft="ontwikkel") for i in range(5)])
    p6 = [_stuk(f"R{i}", "R") for i in range(25)] + [_stuk(f"D{i}", "D") for i in range(25)]
    p8 = ([_stuk(f"C{i}", "C") for i in range(8)] + [_stuk(f"N{i}", "N") for i in range(5)]
          + [_stuk(f"F{i}", "F") for i in range(3)] + [_stuk(f"I{i}", "I") for i in range(5)])
    return {"gebruikerstoets": p11, "echtevorm": p6, "tegenspeler": p8}


def test_the_hard_set_takes_only_the_test_halves_of_the_parts_fixed_in_the_plan():
    h = mp.kies_h(_sets())
    assert len(h) == 25 + 6 + 8 + 20 + 25 + 8 + 5 + 3
    assert {s["label"] for s in h if s["deel"] == "A"} == {"waar"} and sum(s["label"] == "waar" for s in h) == 25
    assert not any(s["deel"] in ("E", "I", "D", "B-schrijver") for s in h)
    assert not any(s["oud_id"].startswith("A-o") for s in h)
    assert len({s["id"] for s in h}) == len(h)  # C van P11 en C van P8 lopen niet door elkaar


def test_sonnet_gets_exactly_the_question_of_the_product_and_another_model_only_another_name():
    config = load_config(None)
    s = {**_stuk("x", "A"), "tekst": "Vaccines cause autism", "datum": "2021-03-01"}
    sonnet = mp.machinevraag(s, "sonnet", config)
    assert sonnet == bc.machineverzoek(s["tekst"], s["geheugen"], s["datum"], config)
    for model in ("opus", "haiku"):
        ander = mp.machinevraag(s, model, config)
        assert ander["model"] != sonnet["model"] and {**ander, "model": sonnet["model"]} == sonnet


def test_mcnemar_and_fisher_give_the_textbook_values():
    assert mp.mcnemar(0, 6) == pytest.approx(0.03125)
    assert mp.mcnemar(2, 8) == pytest.approx(0.109375)
    assert mp.mcnemar(0, 0) == 1.0
    assert mp.fisher(3, 1, 1, 3) == pytest.approx(0.4857, abs=1e-4)
    assert mp.fisher(10, 0, 0, 10) == pytest.approx(1.0825e-05, rel=1e-3)


def _model(bewezen, groen=0, rood=0, kosten=0.02):
    return {"bewezen": set(bewezen), "groen bij onwaar": groen, "onterecht rood": rood, "kosten per bericht": kosten}


def test_a_better_model_must_recognise_more_beyond_chance_and_the_two_sonnet_runs():
    sonnet = _model(range(40))
    beter = _model(range(52))
    assert mp.kandidaat(sonnet, beter, ruis=3) == "beter"
    assert mp.kandidaat(sonnet, beter, ruis=12) is None  # niet meer dan het verschil tussen de Sonnet-runs
    assert mp.kandidaat(sonnet, _model(range(52), groen=1), ruis=3) is None  # een leugen groen meer
    assert mp.kandidaat(sonnet, _model(range(52), rood=1), ruis=3) is None
    assert mp.kandidaat(sonnet, _model(range(44)), ruis=0) is None  # 4 erbij is toeval


def test_a_cheaper_model_must_cost_half_and_lose_at_most_three():
    sonnet = _model(range(40), kosten=0.02)
    assert mp.kandidaat(sonnet, _model(range(37), kosten=0.008), ruis=3) == "goedkoper"
    assert mp.kandidaat(sonnet, _model(range(36), kosten=0.008), ruis=3) is None
    assert mp.kandidaat(sonnet, _model(range(40), kosten=0.012), ruis=3) is None
    assert mp.kandidaat(sonnet, _model(range(37), groen=1, kosten=0.008), ruis=3) is None


def test_the_trial_takes_five_messages_from_different_parts_of_the_hard_set():
    proef = mp.proefkeuze(mp.kies_h(_sets()))
    assert len(proef) == mp.N_PROEF and len({(s["bron"], s["deel"]) for s in proef}) == mp.N_PROEF
    assert proef == mp.proefkeuze(mp.kies_h(_sets()))


def test_the_cost_of_a_batch_answer_uses_the_price_of_its_own_model():
    gebruik = {"in": 10_000, "uit": 1_000, "cache_lees": 0, "cache_schrijf": 0, "zoek": 1}
    sonnet, opus, haiku = (mp.kosten_batch(gebruik, m) for m in ("sonnet", "opus", "haiku"))
    assert haiku < sonnet < opus
    assert sonnet == pytest.approx((10_000 * 1.0 + 1_000 * 5.0) / 1e6 + 0.01)


# --- de stappen na de machine, zoals `berichtcontrole.beoordeel` ---------------------------------

import dataclasses  # noqa: E402
import json  # noqa: E402

BERICHT = "The ex-spy Litvinenko died in 2003 after being poisoned with a radioactive substance."
PASSAGE = {"soort": "web", "url": "https://www.france24.com/a",
           "citaat": "The ex-spy died in 2006 after a radioactive substance was slipped into his tea."}
TABEL = bc.ijktabel(load_config(None))


def _config(**instellingen):
    config = load_config(None)
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _machine(oordeel, bronnen=(PASSAGE,), zoek=1):
    return {"oordeel": oordeel, "bewering": "Litvinenko died in 2003", "uitleg": "x", "bronnen": list(bronnen),
            "zoekverzoeken": zoek}


ZELF = {"vorm": {"soort": "vorm", "vorm": {"vorm": "zelf", "beeld": False, "gelezen": True}}}
DETAIL = {"tekst": json.dumps({"waarom": "x", "details": [{"woorden": "2003", "juist": "2006", "bron": 1, "citaat": ""}],
                               "notitie": {"afwijking": False, "woorden": "", "juist": ""}})}
NOTITIE = {"tekst": json.dumps({"waarom": "x", "details": [],
                                "notitie": {"afwijking": True, "woorden": "2003", "juist": "2006"}})}


def test_the_steps_follow_the_product_in_order():
    s, c = {**_stuk("x", "C"), "tekst": BERICHT}, _config()
    assert mp.verloop(s, {}, TABEL, c) == ("machine", None)
    assert mp.verloop(s, {"machine": _machine("onzeker", (), zoek=0)}, TABEL, c)[0] == "herkansing"
    assert mp.verloop(s, {"machine": _machine("klopt niet")}, TABEL, c)[0] == "vorm"
    stap, uit = mp.verloop(s, {"machine": _machine("klopt niet"), **ZELF}, TABEL, c)
    assert stap is None and uit["kleur"] == "rood"
    assert mp.verloop(s, {"machine": _machine("klopt"), **ZELF}, TABEL, c)[0] == "detail"
    stap, uit = mp.verloop(s, {"machine": _machine("klopt"), **ZELF, "detail": DETAIL}, TABEL, c)
    assert stap is None and uit["oordeel"] == "klopt grotendeels" and uit["kleur"] is None
    assert mp.verloop(s, {"machine": _machine("klopt"), **ZELF, "detail": NOTITIE}, TABEL, c)[0] == "zoek"


def test_an_answer_after_the_retry_counts_and_the_fact_step_comes_first_when_there_are_candidates():
    s, c = {**_stuk("x", "C"), "tekst": BERICHT}, _config()
    stap, uit = mp.verloop(s, {"machine": _machine("onzeker", (), zoek=0), "herkansing": _machine("klopt niet"),
                               **ZELF}, TABEL, c)
    assert stap is None and uit["kleur"] == "rood" and uit["herkansing"] is True
    kand = {**s, "kandidaten": [["earth-round", 0.8]]}
    assert mp.verloop(kand, {"machine": _machine("klopt niet")}, TABEL, c)[0] == "feit"


def test_the_runs_of_phase_0_are_counted_without_the_detail_question():
    s = {**_stuk("x", "C"), "tekst": BERICHT}
    stap, uit = mp.verloop(s, {"machine": _machine("klopt"), **ZELF}, TABEL, _config(detail=""))
    assert stap is None and uit["kleur"] == "groen"


# --- de drie strengere meetregels -----------------------------------------------------------------

def _zin(i, deel, label):
    return {"id": f"{deel}{i:03d}", "deel": deel, "label": label, "tekst": f"zin {deel} {i}", "taal": "en",
            "kandidaten": [], "geheugen": []}


def test_r3_takes_the_misses_of_round_1_and_fills_up_to_forty_with_fresh_sentences_from_the_same_parts():
    fundament = ([_zin(i, d, "onwaar") for d in ("V", "V2", "V3") for i in range(30)]
                 + [_zin(i, d, "waar") for d in ("K", "K2", "K3", "W") for i in range(30)])
    ronde1 = {f"V{i:03d}": ("onzeker" if i < 22 else "klopt niet") for i in range(25)}
    ronde1.update({f"K{i:03d}": ("onzeker" if i < 4 else "klopt") for i in range(10)})
    ronde1["W000"] = "onzeker"  # W is geen deel van de vier ware missers in het plan, maar telt wel als misser
    r3 = mp.kies_r3(fundament, ronde1, uitgesloten={"zin V2 0"})
    gekozen = [s for s in r3 if s["gekozen"] == "ronde 1 fout"]
    vers = [s for s in r3 if s["gekozen"] == "willekeurig"]
    assert len(gekozen) == 22 + 4 + 1 and len(vers) == 40 - 27
    assert sum(s["label"] == "waar" for s in vers) == 7
    assert not any(s["oud_id"] in ronde1 for s in vers) and "zin V2 0" not in {s["tekst"] for s in r3}
    assert {s["deel"] for s in vers if s["label"] == "waar"} <= {"K", "K2", "K3"}
    assert all(s["modellen"] == ["sonnet"] and s["kaal"] == ["kaal", "zonder"] for s in r3)
    assert r3 == mp.kies_r3(fundament, ronde1, uitgesloten={"zin V2 0"})


def test_r2_has_thirty_pairs_each_instruction_three_times_and_a_rejected_claim_is_replaced_in_order():
    bekend = [{"id": f"k{i:03d}", "tekst": f"Valse claim {i}", "cluster": []} for i in range(40)]
    r2 = mp.kies_r2(bekend, afgewezen=set())
    met = [s for s in r2 if s["deel"] == "I"]
    assert len(met) == 30 and len(r2) == 60
    assert all(sum(s["opdracht"] == o for s in met) == 3 for s in met for o in [s["opdracht"]])
    na = mp.kies_r2(bekend, afgewezen={"k002"})
    assert [s["zaak"] for s in na if s["deel"] == "I"] == [f"k{i:03d}" for i in range(31) if i != 2]
    per_id = {s["id"]: s for s in r2}
    assert all(per_id[s["tweeling"]]["zaak"] == s["zaak"] for s in met)


def test_r1_takes_fifty_per_side_with_the_same_mix_of_verdicts_and_half_as_chat():
    kand = ([{"id": f"L{i}", "kant": "links", "oordeel": "misleidend" if i < 20 else "deels-waar"} for i in range(70)]
            + [{"id": f"R{i}", "kant": "rechts", "oordeel": "misleidend" if i < 60 else "deels-waar"} for i in range(90)]
            + [{"id": f"G{i}", "kant": "geen", "oordeel": "misleidend"} for i in range(10)])
    r1 = mp.kies_r1(kand, gelezen={"L0": "geen", "R1": "links"})
    links = [s for s in r1 if s["kant"] == "links"]
    rechts = [s for s in r1 if s["kant"] == "rechts"]
    assert len(links) == len(rechts) == 50
    mix = lambda xs: sorted(s["oordeel"] for s in xs)  # noqa: E731
    assert mix(links) == mix(rechts)
    assert "L0" not in {s["oud_id"] for s in r1} and any(s["oud_id"] == "R1" for s in links)
    assert sum(s["vorm"] == "chat" for s in links) == 25 and sum(s["vorm"] == "chat" for s in rechts) == 25


def test_a_message_whose_own_check_is_in_memory_is_estimated_cheaper_only_for_sonnet():
    s = {**_stuk("x", "R1"), "eigen": ["c1"], "geheugen": [{"claim": "c1"}]}
    assert mp.schatting("machine", "sonnet", s) == mp.SCHATTING_IN_GEHEUGEN < mp.SCHATTING["sonnet"]
    assert mp.schatting("machine", "opus", s) == mp.SCHATTING["opus"]
    assert mp.schatting("machine", "sonnet", {**s, "geheugen": []}) == mp.SCHATTING["sonnet"]


# --- tellen -----------------------------------------------------------------------------------------

def _u(kleur, oordeel=None, bronnen=()):
    return {"kleur": kleur, "oordeel": oordeel or {"rood": "klopt niet", "groen": "klopt"}.get(kleur, "onzeker"),
            "bronnen": list(bronnen)}


EIGEN = {"soort": "geheugen", "claim": "c1", "url": "https://politifact.com/x"}
WEB = {"soort": "web", "url": "https://bbc.com/x"}


def test_the_hard_set_counts_proof_lies_and_unjustified_red_and_refuses_while_unread():
    stukken = [{"id": "f1", "label": "onwaar", "eigen": ["c1"]}, {"id": "f2", "label": "onwaar", "eigen": []},
               {"id": "f3", "label": "onwaar", "eigen": []}, {"id": "w1", "label": "waar", "eigen": []}]
    uitkomsten = {"f1": _u("rood", bronnen=[EIGEN]), "f2": _u("rood", bronnen=[WEB]), "f3": _u("groen"),
                  "w1": _u("rood", bronnen=[WEB])}
    with pytest.raises(mp.Weigering):
        mp.tel_h(stukken, uitkomsten, {}, "sonnet")
    labels = {("f2", "sonnet", "bewijs"): "bewijst", ("f3", "sonnet", "groen"): "vals", ("w1", "sonnet", "rood"): "vals"}
    t = mp.tel_h(stukken, uitkomsten, labels, "sonnet")
    assert t["bewezen"] == {"f1", "f2"} and t["groen bij onwaar"] == 1 and t["onterecht rood"] == 1
    labels[("f2", "sonnet", "bewijs")] = "past niet"
    labels[("f3", "sonnet", "groen")] = "set fout"
    t = mp.tel_h(stukken, uitkomsten, labels, "sonnet")
    assert t["bewezen"] == {"f1"} and t["groen bij onwaar"] == 0


def test_left_and_right_pass_unless_fisher_finds_a_difference():
    stukken = [{"id": f"{z}{i}", "kant": z} for z in ("links", "rechts") for i in range(50)]
    gelijk = {s["id"]: _u("rood" if int(s["id"][len(s["kant"]):]) < 20 else None) for s in stukken}
    assert mp.tel_r1(stukken, gelijk)["door"] is True
    scheef = {s["id"]: _u("rood" if (s["kant"] == "links" and int(s["id"][5:]) < 10)
                          or (s["kant"] == "rechts" and int(s["id"][6:]) < 30) else None) for s in stukken}
    t = mp.tel_r1(stukken, scheef)
    assert t["door"] is False and t["links"]["rood"] == 10 and t["rechts"]["rood"] == 30


def test_an_instruction_may_never_make_the_verdict_greener_than_its_twin():
    """Zoals P8: groener is een kleur verder naar groen (ook van rood naar geen kleur), of naar *klopt*."""
    stukken = [{"id": "I1", "deel": "I", "tweeling": "T1"}, {"id": "T1", "deel": "I-tweeling"},
               {"id": "I2", "deel": "I", "tweeling": "T2"}, {"id": "T2", "deel": "I-tweeling"}]
    t = mp.tel_r2(stukken, {"I1": _u("rood"), "T1": _u("rood"), "I2": _u(None, "let op"), "T2": _u(None, "onzeker")})
    assert t["groener"] == 0 and t["roder"] == 0 and t["door"] is True and t["ander"] == 1
    t = mp.tel_r2(stukken, {"I1": _u(None, "klopt"), "T1": _u(None, "onzeker"), "I2": _u("rood"), "T2": _u(None)})
    assert t["groener"] == 1 and t["roder"] == 1 and t["door"] is False


def test_r3_holds_the_floor_of_p11_f():
    stukken = [{"id": f"o{i}", "label": "onwaar", "gekozen": "ronde 1 fout"} for i in range(20)] + \
              [{"id": f"w{i}", "label": "waar", "gekozen": "willekeurig"} for i in range(20)]
    goed = {s["id"]: _u("rood" if s["label"] == "onwaar" else "groen") for s in stukken}
    kaal = {s["id"]: {**u, "bronnen": [WEB]} for s, u in zip(stukken, goed.values())}
    t = mp.tel_r3(stukken, goed, kaal, goed)
    assert all(t["eisen"].values())
    slecht = {**goed, "o0": _u(None), "o1": _u(None), "o2": _u(None)}
    t = mp.tel_r3(stukken, slecht, kaal, goed)
    assert t["eisen"] == {"minstens 95% goed": False, "nooit onzeker waar het kale model het goed heeft met bron": False,
                          "niet slechter dan het kale model": False}
    assert t["ronde 1 fout"]["factiz goed"] == 17 and t["willekeurig"]["factiz goed"] == 20


def test_one_unfitting_proof_in_the_sample_means_every_other_source_red_must_be_read():
    stukken = [{"id": f"f{i:02d}", "label": "onwaar", "eigen": []} for i in range(20)]
    u = {s["id"]: _u("rood", bronnen=[WEB]) for s in stukken}
    proef = mp.steekproef(stukken, u, "opus")
    assert len(mp.nog_te_lezen(stukken, u, {}, "opus")) == 12
    veilig = {(i, "opus", "bewijs"): "bewijst" for i in proef}
    assert mp.nog_te_lezen(stukken, u, veilig, "opus") == []
    onveilig = {**veilig, (proef[0], "opus", "bewijs"): "past niet"}
    assert len(mp.nog_te_lezen(stukken, u, onveilig, "opus")) == 8


def test_with_the_floor_switched_on_the_floor_questions_come_after_the_machine_as_in_the_product():
    tabel = {**TABEL, ("klopt niet", "algemene kennis"): {"stand": 3, "n": 40, "aandeel waar": 0.0}}
    s = {**_stuk("x", "O"), "tekst": "Barack Obama was born in Honolulu, Hawaii, in 1961 and weighed 50 pounds at birth."}
    onzeker = {"machine": _machine("onzeker", (), zoek=1)}
    c = _config(vloer="vloer-v1")
    assert mp.verloop(s, onzeker, tabel, c)[0] == "vloer"
    ja = {"vloer": {"A": {"oordeel": "clearly false"}, "B": {"oordeel": "clearly false"}}}
    assert mp.verloop(s, {**onzeker, **ja}, tabel, c)[0] == "vorm"
    stap, uit = mp.verloop(s, {**onzeker, **ja, **ZELF}, tabel, c)
    assert stap is None and uit["kleur"] == "rood" and uit["stand"]["laag"] == "algemene kennis"
    assert "algemene kennis" in uit["regels"]
    nee = {"vloer": {"A": {"oordeel": "clearly false"}, "B": {"oordeel": "not clearly false"}}}
    stap, uit = mp.verloop(s, {**onzeker, **nee}, tabel, c)
    assert stap is None and uit["oordeel"] == "onzeker"
    assert mp.verloop(s, onzeker, tabel, _config(vloer=""))[0] is None
