"""Privépersonen in een bewering: hoeveel factchecks noemen er een (PLAN #34.2bw, maatregel 2)."""

from __future__ import annotations

import json

import pytest

from doublecheck import privepersonen as pp


def _antwoord(*rijen):
    return json.dumps({"antwoorden": [{"nr": n, "prive": p, "naam": naam, "context": c, "minderjarig": m}
                                      for n, p, naam, c, m in rijen]})


TEKSTEN = ["Jan de Vries uit Almere stak een agent neer.", "Mark Rutte zei dat de grens dicht gaat.", "De zon is groen."]


def test_a_named_private_person_is_read_with_the_context_of_the_claim():
    uit = pp.lees_oordelen(_antwoord((1, "ja", "Jan de Vries", "misdaad", False),
                                     (2, "nee", "", "geen", False),
                                     (3, "nee", "", "geen", False)), TEKSTEN)
    assert uit[0] == {"prive": "ja", "naam": "Jan de Vries", "context": "misdaad", "minderjarig": False}
    assert uit[1]["prive"] == "nee" and uit[2]["prive"] == "nee"


def test_a_name_that_is_not_in_the_claim_never_counts():
    """Een naam die het model erbij bedenkt, is geen lezing van de bewering."""
    uit = pp.lees_oordelen(_antwoord((1, "ja", "Piet Jansen", "misdaad", False), (2, "nee", "", "geen", False),
                                     (3, "nee", "", "geen", False)), TEKSTEN)
    assert uit[0] is None
    # zonder naam bij een ja ook niet; hoofdletters en witruimte maken niet uit
    assert pp.lees_oordelen(_antwoord((1, "ja", "", "misdaad", False)), TEKSTEN[:1]) == [None]
    assert pp.lees_oordelen(_antwoord((1, "twijfel", "jan  de vries", "misdaad", False)), TEKSTEN[:1])[0]["prive"] == "twijfel"


def test_an_unknown_value_or_a_number_given_twice_never_counts():
    assert pp.lees_oordelen(_antwoord((1, "misschien", "", "geen", False)), TEKSTEN[:1]) == [None]
    assert pp.lees_oordelen(_antwoord((1, "nee", "", "oorlog", False)), TEKSTEN[:1]) == [None]
    dubbel = _antwoord((1, "nee", "", "geen", False), (1, "nee", "", "geen", False), (4, "nee", "", "geen", False))
    assert pp.lees_oordelen(dubbel, TEKSTEN[:2]) == [None, None]
    assert pp.lees_oordelen("geen json", TEKSTEN[:2]) == [None, None]


def test_the_sample_is_the_same_for_the_same_pages():
    paginas = [f"p{i}" for i in range(2000)]
    assert pp.steekproef(paginas) == pp.steekproef(list(reversed(paginas))) and len(pp.steekproef(paginas)) == pp.PROEF_N
    assert pp.steekproef(paginas, 50) == pp.steekproef(paginas)[:50]


def test_one_question_asks_for_named_private_people_and_the_sensitive_context():
    v = pp.verzoek(["Jan de Vries stak een agent neer.", "Rutte zei X."])
    tekst = v["messages"][0]["content"][0]["text"]
    assert "1. Jan de Vries stak een agent neer." in tekst and "2. Rutte zei X." in tekst
    for regel in ("private individual", "public figure", "exactly as written", "minor"):
        assert regel in v["system"], regel
    assert v["model"].startswith("claude-haiku")
    assert set(v["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]["context"]["enum"]) \
        == set(pp.CONTEXTEN)


def _antwoorden(oordelen):
    return [{"pagina": f"p{i:03}", "bewering": f"Bewering {i}", "prive": o, "naam": "X" if o != "nee" else "",
             "context": "misdaad" if o != "nee" else "geen", "minderjarig": False, "versie": pp.VERSIE}
            for i, o in enumerate(oordelen)]


def test_the_count_refuses_while_a_yes_or_a_drawn_no_has_no_label(tmp_path):
    antwoorden = _antwoorden(["ja"] * 3 + ["twijfel"] + ["nee"] * 196)
    pad = tmp_path / "labels.json"
    with pytest.raises(pp.Weigering, match="nog te lezen"):
        pp.telling(antwoorden, pad)
    te_lezen = pp.te_lezen(antwoorden)
    # elke ja en twijfel, en een vaste greep uit de nee
    assert {"p000", "p001", "p002", "p003"} <= set(te_lezen)
    assert len(te_lezen) == 4 + min(pp.NEE_LEZEN, 196) and te_lezen == pp.te_lezen(list(reversed(antwoorden)))
    labels = {p: {"label": "geen"} for p in te_lezen}
    labels["p000"] = {"label": "prive", "gevoelig": "misdaad"}
    labels["p001"] = {"label": "publiek"}
    pad.write_text(json.dumps({"labels": labels}), encoding="utf-8")
    t = pp.telling(antwoorden, pad)
    assert t["n"] == 200 and t["prive"] == 1 and t["gevoelig"] == {"misdaad": 1}
    assert t["gemist"] == 0 and 0 < t["aandeel"] < 0.01 and t["boven"] > t["aandeel"]


def test_a_private_person_haiku_missed_counts_against_the_no_group(tmp_path):
    """Wat Haiku *nee* noemde maar ik als privépersoon las, telt mee, opgeschaald naar de hele groep nee."""
    antwoorden = _antwoorden(["nee"] * 300)
    te_lezen = pp.te_lezen(antwoorden)
    labels = {p: {"label": "geen"} for p in te_lezen}
    labels[te_lezen[0]] = {"label": "prive", "gevoelig": "geen"}
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": labels}), encoding="utf-8")
    t = pp.telling(antwoorden, pad)
    assert t["gemist"] == 1 and t["prive"] == 0
    assert t["aandeel"] == pytest.approx(300 / pp.NEE_LEZEN / 300)


# --- de afscherming in de uitgave (maatregel 2) -------------------------------------------------------------------------

def _lezing(prive, context="anders", minderjarig=False):
    return {"prive": prive, "naam": "X", "context": context, "minderjarig": minderjarig}


def test_a_private_person_in_a_sensitive_context_or_a_minor_stays_out_of_search():
    for context in ("misdaad", "ziekte", "dood", "seksualiteit"):
        assert pp.afschermen(_lezing("ja", context)) and pp.afschermen(_lezing("twijfel", context)), context
    assert pp.afschermen(_lezing("ja", "anders", True))
    # een privépersoon in een onschuldig verhaal (de kruier van Katni) en een bewering zonder privépersoon blijven vindbaar
    assert not pp.afschermen(_lezing("ja", "anders")) and not pp.afschermen(_lezing("nee", "geen"))
    assert not pp.afschermen(_lezing("nee", "geen", True))


def _vol(pagina, bewering, prive, naam="", context="geen", minderjarig=False):
    return {"pagina": pagina, "bewering": bewering, "prive": prive, "naam": naam, "context": context,
            "minderjarig": minderjarig, "versie": pp.VERSIE}


def test_the_edition_gets_every_page_read_and_a_name_to_mask_only_when_the_second_reading_agrees():
    a = "Jamna Kumari, 12, was attacked in Gujarat"
    b = "Councillor Tahir Hussain killed a girl of 9"
    vol = [_vol("a", a, "ja", "Jamna Kumari", "misdaad", True), _vol("b", b, "ja", "Tahir Hussain", "misdaad", True),
           _vol("c", "Garlic cures covid", "nee"), _vol("d", "Sandhya Marawi is the first woman porter", "ja", "Sandhya Marawi"),
           {"pagina": "e", "bewering": "x", "prive": None, "versie": pp.VERSIE},          # geen geldig antwoord: niet gelezen
           {**_vol("f", "Old", "nee"), "versie": "privepersoon-v0"}]                       # een andere versie telt niet
    tweede = [{"pagina": "a", "bewering": a, "naam": "Jamna Kumari", "prive": True, "minderjarig": True, "gevoelig": True,
               "versie": pp.TWEEDE},
              {"pagina": "b", "bewering": b, "naam": "Tahir Hussain", "prive": False, "minderjarig": False, "gevoelig": True,
               "versie": pp.TWEEDE}]
    uit = pp.uitgave_invoer(vol, tweede)
    assert uit["a"] == {"bron": a, "afschermen": True, "naam": "Jamna Kumari"}
    assert uit["b"] == {"bron": b, "afschermen": True}          # buiten zoekmachines, maar de naam van een raadslid blijft
    assert uit["c"] == {"bron": "Garlic cures covid", "afschermen": False}
    assert uit["d"] == {"bron": "Sandhya Marawi is the first woman porter", "afschermen": False}
    assert set(uit) == {"a", "b", "c", "d"}
    # een tweede lezing van een andere tekst of naam telt niet
    anders = [{**tweede[0], "bewering": "Jamna Kumari was attacked"}]
    assert "naam" not in pp.uitgave_invoer(vol, anders)["a"]


def test_the_second_reading_asks_about_the_named_person_only_and_reads_strictly():
    v = pp.tweede_verzoek([("Jamna Kumari, 12, was attacked", "Jamna Kumari")])
    tekst = v["messages"][0]["content"][0]["text"]
    assert "Jamna Kumari, 12, was attacked" in tekst and "Name: Jamna Kumari" in tekst
    assert v["model"].startswith("claude-sonnet") and "the named person themself" in v["system"]
    goed = json.dumps({"antwoorden": [{"nr": 1, "prive": True, "minderjarig": True, "gevoelig": True}]})
    assert pp.lees_tweede(goed, 1) == [{"prive": True, "minderjarig": True, "gevoelig": True}]
    assert pp.lees_tweede(json.dumps({"antwoorden": [{"nr": 2, "prive": True, "minderjarig": True, "gevoelig": True}]}), 1) == [None]
    assert pp.lees_tweede("geen json", 2) == [None, None]
