"""Een nieuwe lezer met vier punten, gemeten op verse berichten (PLAN #32.12)."""

import pytest

from doublecheck import versetoets as v


def test_only_unseen_claims_with_nothing_but_false_or_misleading_checks_enter_the_fresh_set():
    rijen = [("c1", "Video shows a flood.", "onwaar", "2026-08-02", "FACTLY"),
             ("c2", "A claim with two checks.", "onwaar,waar", "2026-08-03", "VERA Files"),
             ("c3", "Seen in round 4.", "misleidend", "2026-08-04", "FACTLY"),
             ("c4", "  Fresh and misleading. ", "misleidend", "2026-09-30", "Fact Crescendo Sri Lanka")]
    uit = v.ongezien(rijen, gezien={"c3"})
    assert [s["claim"] for s in uit] == ["c1", "c4"]
    assert uit[1] == {"id": "O:c4", "deel": "O", "tekst": "Fresh and misleading.", "claim": "c4", "label": "onwaar",
                      "oordeel": "misleidend", "datum": "2026-09-30", "redactie": "Fact Crescendo Sri Lanka"}


def _a(kleur, zonder=None, over_beeld=False, kosten=0.01):
    return {"kleur": kleur, "kleur_streng": kleur, "kleur_zonder_beeldregel": zonder if zonder is not None else kleur,
            "over_beeld": over_beeld, "seconden": 3.0, "kosten": kosten, "oordeel": "klopt", "route": "zoeken",
            "staatsmedia": 0}


def test_counting_refuses_until_read_and_reports_what_the_image_rule_took_away():
    stukken = [{"id": "W:1-0", "deel": "W"}, {"id": "W:1-1", "deel": "W"}, {"id": "O:c1", "deel": "O"},
               {"id": "O:c2", "deel": "O"}]
    antwoorden = {"W:1-0": _a("groen"), "W:1-1": _a(None, zonder="groen", over_beeld=True),
                  "O:c1": _a(None, zonder="groen", over_beeld=True), "O:c2": _a("groen")}
    with pytest.raises(v.Weigering, match=v.LABELS.name):
        v.telling(stukken, antwoorden, {})
    uit = v.telling(stukken, antwoorden, {"O:c2": "vals"})
    assert uit["O"]["vals groen"] == 1 and uit["O"]["over_beeld"] == 1 and uit["O"]["groen zonder beeldregel"] == 2
    assert uit["W"]["groen"] == 1 and uit["W"]["groen zonder beeldregel"] == 2
    assert uit["eisen"]["nepberichten: hoogstens 1 op 100 onterecht groen"] is False  # 1 van 2


def test_the_budget_counts_the_development_check_and_the_test_together(tmp_path):
    (tmp_path / "ontwikkel.jsonl").write_text('{"id": "a", "kosten": 0.5}\n')
    (tmp_path / "antwoorden.jsonl").write_text('{"id": "b", "kosten": 1.2}\n{"id": "c", "kosten": 0.1}\n')
    assert v.uitgegeven(tmp_path) == pytest.approx(1.8)
    assert v.uitgegeven(tmp_path / "leeg") == 0
