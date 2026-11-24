"""Een NLI-model op een vaste revisie (#25.32, DR6).

Een modelnaam zonder revisie laadt wat de hub vandaag heeft; een vergelijking
tussen modellen moet weten welke gewichten ze mat. `model@revisie` pint de
gewichten vast; een kale naam werkt zoals altijd.
"""

import sys
import types


def _nep_transformers(geladen):
    class _Model:
        config = types.SimpleNamespace(id2label={0: "contradiction", 1: "neutral", 2: "entailment"})

        def eval(self):
            return self

    class _Lader:
        def __init__(self, soort):
            self.soort = soort

        def from_pretrained(self, naam, **kw):
            geladen.append((self.soort, naam, kw.get("revision")))
            return _Model() if self.soort == "model" else object()

    return types.SimpleNamespace(AutoTokenizer=_Lader("tokenizer"),
                                 AutoModelForSequenceClassification=_Lader("model"))


def test_a_pinned_model_loads_exactly_that_revision(monkeypatch):
    from doublecheck import nli

    geladen = []
    monkeypatch.setitem(sys.modules, "transformers", _nep_transformers(geladen))
    nli._laad.cache_clear()
    try:
        _, _, tegenspraak = nli._laad("joeddav/xlm-roberta-large-xnli@b227ee8435ceadfa86dc1368a34254e2838bf242")
        nli._laad("MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
    finally:
        nli._laad.cache_clear()
    assert geladen == [
        ("tokenizer", "joeddav/xlm-roberta-large-xnli", "b227ee8435ceadfa86dc1368a34254e2838bf242"),
        ("model", "joeddav/xlm-roberta-large-xnli", "b227ee8435ceadfa86dc1368a34254e2838bf242"),
        ("tokenizer", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7", None),
        ("model", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7", None),
    ]
    assert tegenspraak == 0          # het label op naam, niet op plek
