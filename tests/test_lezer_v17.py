"""`lezer-v17` (PLAN #32.64; PO 2026-11-08: "slimme tweaks ... om kosten te besparen"): de inhoud van v16, met de vaste
instructies vooraan in het systeembericht zodat ze bewaard worden tussen vragen, en zinnen die niet breken na een
initiaal; en een meting waarin een arm zijn eigen model kiest."""

import json
from types import SimpleNamespace

from doublecheck import meting as mt
from doublecheck import zoekcontrole as zc


def _config(lezer="lezer-v17", model="claude-sonnet-5-5"):
    return SimpleNamespace(berichtcontrole=SimpleNamespace(lezer=lezer, model_id=model, beeld=True))


RES = [{"nr": 1, "url": "https://www.bbc.com/a", "titel": "Joseph M. Juran dies at 103", "site": "bbc.com", "soort": "overig",
        "band": "goed", "fragment": "Juran died on 28 February 2008 aged 103.", "factcheck": False, "staatsmedia": None}]


def test_v17_has_the_same_words_as_v16_only_the_fixed_part_moves_to_the_system_message():
    v16, v17 = zc.LEZERS["lezer-v16"], zc.LEZERS["lezer-v17"]
    assert v17["vraag"] + v17["regels"] == v16["vraag"] and "{checks}" in v17["vraag"] and "{" not in v17["regels"]
    assert {k: v for k, v in v17.items() if k not in ("vraag", "regels", "initialen")} == {
        k: v for k, v in v16.items() if k != "vraag"}
    arm = {"speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk({**arm, "lezer": "lezer-v17"}) != mt.vingerafdruk({**arm, "lezer": "lezer-v16"})


def test_the_fixed_instructions_go_first_and_are_marked_to_be_kept_between_questions():
    verzoek = zc.leesverzoek("Train derails in Germany", RES, "2026-11-08", _config(), None, [], [])
    systeem = verzoek["system"]
    assert isinstance(systeem, list) and systeem[-1]["cache_control"] == {"type": "ephemeral"}
    assert zc.LEZERS["lezer-v17"]["regels"].strip() in systeem[-1]["text"]
    tekst = verzoek["messages"][0]["content"]
    assert "Train derails in Germany" in tekst and "Decide what the message is" not in tekst
    v16 = zc.leesverzoek("Train derails in Germany", RES, "2026-11-08", _config("lezer-v16"), None, [], [])
    assert isinstance(v16["system"], str) and "Decide what the message is" in v16["messages"][0]["content"]


def test_a_sentence_does_not_break_after_an_initial_in_v17_only():
    uitleg = "Dit klopt: Joseph M. Juran overleed op 28 februari 2008 [1]. Hij werd 103 [1]."
    assert zc.met_bronnen(uitleg, RES, [], initialen=True) == uitleg
    assert zc.met_bronnen(uitleg, RES, []) == "Juran overleed op 28 februari 2008 [1]. Hij werd 103 [1]."


def _oordeel(uitleg):
    return {"oordeel": "klopt", "steunt": [1], "spreekt_tegen": [], "uitleg": uitleg, "over_beeld": False, "checks": [],
            "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0}, "zou_gemeld": True}


def test_na_lezen_keeps_the_initial_for_v17():
    uitleg = "Dit klopt: Joseph M. Juran overleed op 28 februari 2008 [1]."
    uit = zc.na_lezen(zc.lees_oordeel(json.dumps(_oordeel(uitleg))), "Juran dies", RES, [], "lezer-v17", False,
                      gezocht=True, jaar=2026)
    assert uit["uitleg"] == uitleg


def test_an_arm_may_choose_its_own_model_and_its_fingerprint_and_price_follow():
    arm = {"lezer": "lezer-v17", "speurvraag_model": "claude-haiku-5-5"}
    assert mt.vingerafdruk(arm) != mt.vingerafdruk({**arm, "model_id": "claude-haiku-5-5"})
    assert mt.vingerafdruk({"lezer": "lezer-v16", "speurvraag_model": "claude-haiku-5-5"}) == mt.vingerafdruk(
        {"lezer": "lezer-v16", "speurvraag_model": "claude-haiku-5-5", "model_id": None})
    assert mt.model_naam("claude-haiku-5-5") == "haiku" and mt.model_naam("claude-sonnet-5-5") == "sonnet"
    assert mt.zoekkosten([True, False, True]) == 2 * zc.ZOEKPRIJS


def test_the_product_reads_with_v17_or_later_and_keeps_the_fixed_part_between_questions():
    """De release van 2026-11-08 (PO: "dat mag"): het product leest met `lezer-v17` of later (v18 sinds 2026-11-09, met
    hetzelfde vaste deel), met bronnenlijst `bronnen-v6` of later (v7 sinds 2026-11-09, B69), en het verzoek van `/check`
    bewaart het vaste deel tussen vragen."""
    from doublecheck import bronnen
    from doublecheck.config import load_config

    config = load_config("config.toml")
    assert config.berichtcontrole.lezer in ("lezer-v17", "lezer-v18") and config.berichtcontrole.speurvraag_model
    assert bronnen.VERSIE in ("bronnen-v6", "bronnen-v7")
    verzoek = zc.leesverzoek("Train derails in Germany", RES, "2026-11-08", config, None, [], [])
    assert verzoek["system"][-1]["cache_control"] == {"type": "ephemeral"}
