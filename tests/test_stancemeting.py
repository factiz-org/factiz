"""Een sterker stance-model, gemeten (PLAN.md #25.32)."""

import pytest

from doublecheck import stancemeting as sm


def test_the_label_follows_the_same_threshold_for_every_model():
    assert sm.label(0.91, 0.02, 0.7) == "beweert"
    assert sm.label(0.10, 0.85, 0.7) == "weerlegt"
    assert sm.label(0.50, 0.40, 0.7) == "overig"


def test_on_the_test_set_a_discussion_or_debunk_marked_as_assertion_is_an_error():
    """§56: een *bespreekt* of *weerlegt* die "beweert" krijgt is fout; een
    *beweert* die het niet krijgt is een misser."""
    uit = sm.proefset_uitslag([("beweert", "beweert"), ("beweert", "overig"),
                               ("bespreekt", "beweert"), ("weerlegt", "weerlegt"), ("bespreekt", "overig")])
    assert uit == {"beweert_goed": 1, "missers": 1, "fouten": 1, "n": 5}


def _model(proef_goed, proef_fout, model_terecht, mc4_terecht, mc4_vals, vers_vals):
    return {"proefset": {"beweert_goed": proef_goed, "fouten": proef_fout},
            "beweert_terecht": {"proefset": proef_goed, "modeluitvoer": model_terecht},
            "mc4": {"terecht": mc4_terecht, "vals": mc4_vals}, "vers": {"vals": vers_vals}}


def test_a_candidate_wins_only_without_losing_a_rightful_assertion_and_with_fewer_false_flags():
    """Vastgelegd vóór het meten (PLAN #25.32)."""
    huidig = _model(10, 2, 2, 2, 6, 3)
    beter = _model(10, 1, 2, 2, 3, 1)
    verliest = _model(9, 0, 2, 2, 1, 0)           # een terechte "beweert" kwijt
    meer_fout = _model(10, 3, 2, 2, 1, 0)         # meer fouten op de proefset
    niet_minder = _model(10, 2, 2, 2, 6, 3)       # niet strikt minder vals
    keuze = sm.kies({"huidig": huidig, "beter": beter, "verliest": verliest,
                     "meer_fout": meer_fout, "niet_minder": niet_minder}, huidig="huidig",
                    voorkeur=["beter", "verliest", "meer_fout", "niet_minder"])
    assert keuze["gehaald"] == ["beter"] and keuze["winnaar"] == "beter"


def test_without_a_passing_candidate_the_current_model_stays():
    huidig = _model(10, 2, 2, 2, 6, 3)
    assert sm.kies({"huidig": huidig, "x": _model(9, 0, 2, 2, 0, 0)}, huidig="huidig", voorkeur=["x"])["winnaar"] is None


def test_a_borrowed_tokenizer_must_have_the_identical_sentencepiece_file(tmp_path):
    """De kandidaten leveren geen tokenizer.json; die van bge-m3 mag alleen
    als het SentencePiece-bestand byte voor byte gelijk is."""
    a, b, c = tmp_path / "a.model", tmp_path / "b.model", tmp_path / "c.model"
    a.write_bytes(b"spm-1"); b.write_bytes(b"spm-1"); c.write_bytes(b"spm-2")
    assert sm.zelfde_bestand(a, b)
    assert not sm.zelfde_bestand(a, c)
