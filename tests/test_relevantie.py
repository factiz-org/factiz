"""Alleen wat publiek is: een check over het privéleven van één gewoon persoon gaat uit de uitgave (PLAN #34.2ch)."""

from __future__ import annotations

import json

from doublecheck import relevantie as rv


def _antwoord(*rijen):
    return json.dumps({"antwoorden": [{"nr": n, "oordeel": o} for n, o in rijen]})


def test_each_claim_is_read_as_public_private_or_doubt_and_nothing_else_counts():
    teksten = ["Bill Gates puts chips in vaccines", "Help little Ana, 5, who has cancer", "Een raadsel"]
    uit = rv.lees_oordelen(_antwoord((1, "publiek"), (2, "particulier"), (3, "twijfel")), teksten)
    assert uit == ["publiek", "particulier", "twijfel"]
    assert rv.lees_oordelen(_antwoord((1, "prive")), teksten[:1]) == [None]
    assert rv.lees_oordelen(_antwoord((1, "publiek"), (1, "publiek"), (5, "publiek")), teksten[:2]) == [None, None]
    assert rv.lees_oordelen("geen json", teksten[:2]) == [None, None]


def test_the_question_keeps_crimes_told_about_a_group_and_public_figures_public():
    v = rv.verzoek(["Help little Ana", "Bill Gates"])
    tekst = v["messages"][0]["content"][0]["text"]
    assert "1. Help little Ana" in tekst and "2. Bill Gates" in tekst
    for regel in ("private life of one ordinary person", "about a religious, ethnic, political or national group",
                  "A claim about a public figure is always", "donation or prayer chain",
                  "also when you do not know the name",        # in de proef: de dood van actrice Mariana Rios
                  "nothing in it concerns anyone else", "could affect anyone", "several victims"):   # zeep, een boot
        assert regel in v["system"], regel
    assert v["model"].startswith("claude-haiku")


def _vol(n_particulier, n_publiek):
    rijen = [{"pagina": f"a{i:04}", "bewering": f"Help {i}", "oordeel": "particulier", "versie": rv.VERSIE}
             for i in range(n_particulier)]
    return rijen + [{"pagina": f"b{i:04}", "bewering": f"Gates {i}", "oordeel": "publiek", "versie": rv.VERSIE}
                    for i in range(n_publiek)]


def _tweede(n_particulier, publiek_ook=()):
    """Sonnet noemt alles wat Haiku particulier noemde ook particulier, behalve de nummers in `publiek_ook`."""
    return [{"pagina": f"a{i:04}", "bewering": f"Help {i}", "oordeel": "publiek" if i in publiek_ook else "particulier",
             "versie": rv.TWEEDE} for i in range(n_particulier)]


def test_only_what_haiku_and_then_sonnet_call_private_for_the_same_text_can_go():
    """In de ontwikkelset van v2 waren 38 van de 100 toch publiek; daarom leest Sonnet ze opnieuw met zes voorwaarden."""
    vol = _vol(5, 3)
    tweede = _tweede(5, publiek_ook={1}) + [{"pagina": "a0002", "bewering": "Help 2, changed", "oordeel": "particulier",
                                             "versie": rv.TWEEDE}]
    tweede = [t for t in tweede if not (t["pagina"] == "a0002" and t["bewering"] == "Help 2")]
    assert rv.particulier_volgens_beide(vol, tweede) == {"a0000": "Help 0", "a0003": "Help 3", "a0004": "Help 4"}
    v = rv.tweede_verzoek(["Help little Ana"])
    assert v["model"].startswith("claude-sonnet") and "only if all of these hold" in v["system"]
    for regel in ("could be a public figure in any country", "commercial offer, prize, giveaway", "could apply to anyone"):
        assert regel in v["system"], regel


def test_the_reading_draws_private_and_public_claims_the_same_way_every_time():
    vol, tweede = _vol(500, 2000), _tweede(500)
    part, publ = rv.te_lezen(vol, tweede)
    assert len(part) == rv.PARTICULIER_N and len(publ) == rv.PUBLIEK_N
    assert all(p.startswith("a") for p in part) and all(p.startswith("b") for p in publ)
    assert (part, publ) == rv.te_lezen(list(reversed(vol)), list(reversed(tweede)))


def _labels(tmp_path, part, publ, fout=0, twijfel=0, publiek_part=0):
    labels = {p: {"label": "particulier"} for p in part}
    for p in part[:fout]:
        labels[p] = {"label": "publiek"}
    for p in part[fout:fout + twijfel]:
        labels[p] = {"label": "twijfel"}
    for i, p in enumerate(publ):
        labels[p] = {"label": "particulier" if i < publiek_part else "publiek"}
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": labels}), encoding="utf-8")
    return pad


def test_the_gate_opens_only_with_every_drawn_claim_read_and_at_most_two_public_claims_lost(tmp_path):
    """De regel vooraf (PLAN #34.2ch): van de 200 die beide particulier noemden, hoogstens 2 die toch publiek zijn, en
    hoogstens 5 twijfel; alles wat getrokken is, gelezen."""
    vol, tweede = _vol(500, 2000), _tweede(500)
    part, publ = rv.te_lezen(vol, tweede)
    assert rv.poort(vol, tweede, tmp_path / "geen.json")[0] is False
    assert rv.poort(vol, tweede, _labels(tmp_path, part, publ, fout=2, twijfel=5))[0] is True
    assert rv.poort(vol, tweede, _labels(tmp_path, part, publ, fout=3))[0] is False
    assert rv.poort(vol, tweede, _labels(tmp_path, part, publ, twijfel=6))[0] is False
    pad = _labels(tmp_path, part, publ)
    labels = json.loads(pad.read_text(encoding="utf-8"))
    del labels["labels"][publ[0]]
    pad.write_text(json.dumps(labels), encoding="utf-8")
    assert rv.poort(vol, tweede, pad) == (False, "1 nog te lezen")


def test_new_answers_after_the_reading_keep_the_drawn_claims_and_go_through_the_same_filter(tmp_path):
    """2026-11-23: de routine las nieuwe beweringen, de trekking verschoof, de poort ging dicht en ruim 400 particuliere
    checks kwamen terug in de uitgave. De gelezen greep ligt vast in het labelbestand; wat erna komt, gaat door hetzelfde
    filter (weglaten is de strenge kant, B78)."""
    vol, tweede = _vol(500, 2000), _tweede(500)
    part, publ = rv.te_lezen(vol, tweede)
    pad = _labels(tmp_path, part, publ)
    gelezen = json.loads(pad.read_text(encoding="utf-8"))
    pad.write_text(json.dumps({**gelezen, "greep": {"particulier": part, "publiek": publ}}), encoding="utf-8")
    vol2 = vol + [{"pagina": f"a{i:04}", "bewering": f"Help {i}", "oordeel": "particulier", "versie": rv.VERSIE}
                  for i in range(500, 540)]
    tweede2 = _tweede(540)
    assert rv.te_lezen(vol2, tweede2) != (part, publ)          # een nieuwe trekking zou andere beweringen vragen
    assert rv.poort(vol2, tweede2, pad)[0] is True
    uit = rv.voor_uitgave(vol2, tweede2, pad)
    assert len(uit) == 540 and "a0520" in uit
    # wat in de greep staat en geen label heeft, blijft open
    rv_greep = {"particulier": part[:-1] + ["zz"], "publiek": publ}
    pad.write_text(json.dumps({**gelezen, "greep": rv_greep}), encoding="utf-8")
    assert rv.poort(vol2, tweede2, pad) == (False, "1 nog te lezen")


def test_the_edition_gets_only_private_claims_and_only_with_the_gate_open(tmp_path):
    vol = _vol(500, 2000) + [{"pagina": "c", "bewering": "x", "oordeel": None, "versie": rv.VERSIE}]
    tweede = _tweede(500, publiek_ook={7})
    part, publ = rv.te_lezen(vol, tweede)
    uit = rv.voor_uitgave(vol, tweede, _labels(tmp_path, part, publ))
    assert len(uit) == 499 and uit["a0001"] == {"bron": "Help 1"} and "a0007" not in uit and "b0001" not in uit
    # wat ik als publiek of twijfel las, blijft
    uit = rv.voor_uitgave(vol, tweede, _labels(tmp_path, part, publ, fout=2, twijfel=3))
    assert len(uit) == 494 and not set(part[:5]) & set(uit)
    assert rv.voor_uitgave(vol, tweede, tmp_path / "geen.json") == {}
