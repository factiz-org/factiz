"""Het antwoord in twee lagen, gemeten op verse berichten (PLAN #32.13)."""

import pytest

from doublecheck import tweelagen as t


def test_fresh_true_sentences_leave_out_every_sentence_already_used():
    zinnen = [(3, "A ferry sinks off Bali."), (3, "  A ferry sinks off Bali. "), (4, "Floods hit Valencia again.")]
    assert t.nieuwe_zinnen(zinnen, gezien={"A ferry sinks off Bali."}) == [(4, "Floods hit Valencia again.")]


def _a(kleur=None, feit=None, anders=None, over_beeld=False):
    return {"kleur": kleur, "kleur_streng": kleur, "kleur_zonder_beeldregel": kleur, "over_beeld": over_beeld,
            "seconden": 3.0, "kosten": 0.01, "oordeel": "onzeker", "route": "zoeken", "staatsmedia": 0,
            "wat_klopt": feit, "wat_er_gebeurde": anders}


def test_counting_refuses_until_every_shown_sentence_is_read_and_a_false_one_counts_against_the_bar():
    stukken = [{"id": "W2:1-0", "deel": "W"}, {"id": "O2:c1", "deel": "O"}, {"id": "O2:c2", "deel": "O"}]
    antwoorden = {"W2:1-0": _a("groen"), "O2:c1": _a(feit="Floods hit Rasuwa.", over_beeld=True),
                  "O2:c2": _a("oranje", feit="A storm hit Manila.", anders="The photo is from 2019.")}
    with pytest.raises(t.Weigering, match="O2:c1#feit"):
        t.telling(stukken, antwoorden, {})
    labels = {"O2:c1#feit": "juist", "O2:c2#feit": "vals", "O2:c2#anders": "niet in de bronnen"}
    uit = t.telling(stukken, antwoorden, labels)
    assert uit["O"]["wat klopt"] == 2 and uit["O"]["wat klopt met over_beeld"] == 1
    assert uit["O"]["wat er echt gebeurde"] == 1 and uit["O"]["zin vals"] == 1
    assert uit["O"]["zin niet in de bronnen"] == 1 and uit["W"]["groen"] == 1
    assert uit["eisen"]["getoonde zinnen: hoogstens 1 vals op 100"] is False  # 1 van 2 berichten
