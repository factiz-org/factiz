"""Valse vlaggen op een echt trainingscorpus (PLAN.md #21.9)."""

import numpy as np
import pytest

from doublecheck import vlaggenmeting as vm
from doublecheck.controle import DocumentUitslag, Treffer


def _treffer(claim_id="c1", stance="beweert", vlagbaar=True):
    return Treffer(zin="een zin", claim_id=claim_id, claim_tekst="een claim", similarity=0.9,
                   crosslinguaal=False, stance=stance, entailment=0.95, contradiction=0.01,
                   grond="nli", vlagbaar=vlagbaar, bronnen=())


def test_the_prefilter_keeps_everything_near_the_gate_and_samples_the_rest():
    hoogste = np.array([0.90, 0.70, 0.66, 0.10, 0.50, 0.68])
    boven, steekproef = vm.verdeel(hoogste, poort=0.82, n_steekproef=2)
    assert list(boven) == [0, 1, 5]                     # op of boven 0,82 - 0,15
    assert len(steekproef) == 2 and set(steekproef) <= {2, 3, 4}


def test_a_flag_is_only_what_the_document_asserts():
    uitslagen = [
        DocumentUitslag("en-1", 1, (_treffer(),)),
        DocumentUitslag("en-2", 1, (_treffer(stance="weerlegt"),)),
        DocumentUitslag("en-3", 1, (_treffer(vlagbaar=False),)),
    ]
    assert [v["stuk_id"] for v in vm.vlaggen(uitslagen)] == ["en-1"]


def test_counting_refuses_a_flag_without_a_label():
    with pytest.raises(vm.Weigering):
        vm.uitslag([{"stuk_id": "en-1", "claim_id": "c1", "taal": "en"}], {}, {"en": 10})


def test_a_rightful_flag_is_not_a_false_one():
    vlag = [{"stuk_id": "en-1", "claim_id": "c1", "taal": "en"}, {"stuk_id": "nl-1", "claim_id": "c2", "taal": "nl"}]
    uit = vm.uitslag(vlag, {"en-1|c1": "terecht", "nl-1|c2": "vals"}, {"en": 100, "nl": 50})
    assert (uit["totaal"]["vlaggen"], uit["totaal"]["terecht"], uit["totaal"]["vals"]) == (2, 1, 1)
    assert uit["per_taal"]["en"]["vals"] == 0
