"""De herstelronde (ronde 5, PLAN #31.15): de regels die vóór de eerste vraag
aan het model vastlagen."""

import pytest

from doublecheck import herstel as h

ZELF = {"vorm": "zelf", "beeld": False, "gelezen": True}
OVER = {"vorm": "over een bewering", "beeld": False, "gelezen": True}
BEELD = {"vorm": "zelf", "beeld": True, "gelezen": True}
EIGEN = {"soort": "geheugen", "claim": "c1"}
WEB = {"soort": "web", "url": "https://example.org"}


def _pools():
    def rijen(voorvoegsel, n):
        return [{"id": f"{voorvoegsel}{i:04d}", "sleutel": f"{voorvoegsel}:{i}", "tekst": f"tekst {i}.",
                 "bron": "uit de basisset"} for i in range(n)]

    return {"artikelen": rijen("a", 400), "beeld vers": rijen("v", 28), "beeld oud": rijen("o", 112),
            "onwaar oud": rijen("n", 400)}


def test_the_set_has_the_parts_and_forms_of_the_plan_fixed_by_seed():
    keuze = h.kies(_pools())
    assert keuze == h.kies(_pools())
    tel = {}
    for s in keuze:
        tel[(s["deel"], s["vorm"])] = tel.get((s["deel"], s["vorm"]), 0) + 1
    assert tel == {("W5", "tekst"): 50, ("W5", "chat"): 50, ("B5", "tekst"): 25, ("B5", "chat"): 25,
                   ("N5", "tekst"): 50}
    assert sum(s["id"].startswith("v") for s in keuze) == 28  # alle verse beweringen over beelden
    assert len({s["id"] for s in keuze}) == 200
    assert {s["bron"] for s in keuze if s["deel"] == "W5"} == {"artikel"}  # kop en begin, zoals ronde 4


def test_a_fact_checkers_description_is_not_a_message():
    for tekst in ("Claim: This photo is from Gaza", "Says the vaccine dumps spike proteins into your body.",
                  "Social media posts claim that the president is ill.",
                  "A poster circulating on social media claims that the radio is back.",
                  "post claiming to show a bus crash in Saudi Arabia"):
        assert h.omschrijving(tekst), tekst
    for tekst in ("Video shows flooding in Lipa.", "Vaccines cause autism, doctors confirm.",
                  "Putin sent a letter saying he will help Duterte.", "Bill Gates says he wants to depopulate."):
        assert not h.omschrijving(tekst), tekst


def _stuk(i, deel, eigen=()):
    return {"id": i, "deel": deel, "vorm": "tekst", "label": "waar" if deel == "W5" else "onwaar",
            "eigen": list(eigen)}


def _uit(oordeel, stand, bronnen=(), feit=None):
    laag = "redactie" if any(b["soort"] == "geheugen" for b in bronnen) else "web" if bronnen else "geen bron"
    return {"oordeel": oordeel, "stand": stand, "laag": laag, "feit": feit, "bronnen": list(bronnen)}


def test_one_measurement_gives_the_count_with_and_without_the_rules():
    stukken = [_stuk("w1", "W5"), _stuk("w2", "W5")]
    uit = {"w1": _uit("klopt niet", 3, [WEB]), "w2": _uit("klopt niet", 3, [WEB])}
    vormen = {"w1": OVER, "w2": ZELF}
    labels = {("w1", "klopt niet"): "vals", ("w2", "klopt niet"): "vals"}
    telling = h.telling(stukken, uit, vormen, {}, labels, {})
    assert telling["W5"]["onterecht rood zonder de regels"] == 2
    assert telling["W5"]["onterecht rood met de regels"] == 1
    assert telling["eisen"]["1 ware artikelen met de regels hoogstens 1 van de 100 onterecht rood"] is True


def test_the_count_refuses_while_a_red_article_or_a_green_image_claim_has_no_label():
    for stuk, uitkomst, vorm in ((_stuk("w1", "W5"), _uit("klopt niet", 3, [WEB]), OVER),
                                 (_stuk("b1", "B5"), _uit("klopt", 7, [WEB]), BEELD)):
        with pytest.raises(h.Weigering):
            h.telling([stuk], {stuk["id"]: uitkomst}, {stuk["id"]: vorm}, {}, {}, {})


def test_an_image_claim_that_rule_2_makes_uncertain_is_no_longer_green():
    stukken = [_stuk("b1", "B5"), _stuk("b2", "B5")]
    uit = {"b1": _uit("klopt", 7, [WEB]), "b2": _uit("klopt", 7, [WEB])}
    labels = {("b1", "klopt"): "beeld nodig", ("b2", "klopt"): "vals"}
    telling = h.telling(stukken, uit, {"b1": BEELD, "b2": ZELF}, {}, labels, {})
    assert telling["B5"]["groen zonder de regels"] == 2 and telling["B5"]["groen met de regels"] == 1
    assert telling["eisen"]["2 beweringen over beelden met de regels hoogstens 1 van de 50 groen"] is True


def test_known_fake_news_that_loses_its_red_through_rule_1_counts_against_requirement_3_even_if_justified():
    stukken = [_stuk(f"n{i}", "N5", ["c1"]) for i in range(3)]
    uit = {s["id"]: _uit("klopt niet", 1, [EIGEN]) for s in stukken}
    vormen = {s["id"]: OVER for s in stukken}
    with pytest.raises(h.Weigering):  # elk "over een bewering" bij bekend nepnieuws wordt gelezen
        h.telling(stukken, uit, vormen, {}, {}, {})
    vormlabels = {"n0": "bericht erover", "n1": "bericht erover", "n2": "doet zelf"}
    telling = h.telling(stukken, uit, vormen, {}, {}, vormlabels)
    assert telling["N5"]["rood met bewijs zonder de regels"] == 3 and telling["N5"]["rood met bewijs met de regels"] == 0
    assert telling["N5"]["fout voor eis 3"] == 3 and telling["N5"]["over een bewering, doet zelf"] == 1
    assert telling["eisen"]["3 herkenning blijft: hoogstens 2 van de 50 bekend nepnieuws fout"] is False


def test_every_red_with_another_source_on_fake_news_is_read():
    stukken = [_stuk("n1", "N5", ["c9"]), _stuk("b1", "B5")]
    uit = {"n1": _uit("klopt niet", 3, [WEB]), "b1": _uit("klopt niet", 3, [WEB])}
    vormen = {"n1": ZELF, "b1": BEELD}
    with pytest.raises(h.Weigering):
        h.telling(stukken, uit, vormen, {}, {("n1", "klopt niet"): "bewijst"}, {})
    labels = {("n1", "klopt niet"): "bewijst", ("b1", "klopt niet"): "bewijst via factcheck"}
    telling = h.telling(stukken, uit, vormen, {}, labels, {})
    assert telling["N5"]["rood met bewijs met de regels"] == 1
    assert telling["B5"]["rood met bewijs met de regels"] == 1
    assert telling["B5"]["bewezen via een factcheck op het web"] == 1


def test_the_count_checks_per_message_that_the_rules_never_colour():
    stukken = [_stuk("w1", "W5"), _stuk("n1", "N5", ["c1"]), _stuk("b1", "B5")]
    uit = {"w1": _uit("klopt", 7, [WEB]), "n1": _uit("klopt niet", 1, [EIGEN]), "b1": _uit("onzeker", 5, [WEB])}
    telling = h.telling(stukken, uit, {"w1": BEELD, "n1": ZELF, "b1": OVER}, {}, {}, {"b1": "bericht erover"})
    assert telling["controle"]["door de regels rood of groen"] == 0
    assert telling["eisen"]["4 de regels maken nooit iets rood of groen"] is True
    assert telling["W5"]["groen weg door regel 2"] == 1


def test_an_unreadable_form_answer_is_counted_apart():
    stukken = [_stuk("w1", "W5")]
    telling = h.telling(stukken, {"w1": _uit("klopt", 7, [WEB])},
                        {"w1": {"vorm": "zelf", "beeld": False, "gelezen": False}}, {}, {}, {})
    assert telling["W5"]["vormvraag onleesbaar"] == 1


def test_a_10_is_always_read():
    stukken = [_stuk("w1", "W5")]
    uit = {"w1": _uit("klopt", 10, feit="earth-round")}
    with pytest.raises(h.Weigering):
        h.telling(stukken, uit, {"w1": ZELF}, {}, {}, {})
    telling = h.telling(stukken, uit, {"w1": ZELF}, {}, {("w1", 10, "earth-round"): "fout"}, {})
    assert telling["controle"]["verkeerde 10"] == 1


def test_the_form_question_is_only_asked_for_a_red_or_green_result_with_its_claim():
    from doublecheck.config import load_config

    stukken = [{**_stuk(i, "W5"), "tekst": f"bericht {i}"} for i in ("w1", "w2", "w3")]
    uit = {"w1": {**_uit("klopt niet", 3, [WEB]), "bewering": "Het virus is gepatenteerd"},
           "w2": {**_uit("onzeker", 5, [WEB]), "bewering": "Iets onzekers"},
           "w3": {**_uit("klopt", 7, [WEB]), "bewering": None}}
    vragen = h.vormvragen(stukken, uit, load_config(), set())
    assert [v["custom_id"] for v in vragen] == ["v-w1"]
    assert "Het virus is gepatenteerd" in vragen[0]["params"]["messages"][0]["content"]
    vormen = h.vormen_van([], uit)
    assert set(vormen) == {"w2", "w3"} and vormen["w2"]["gevraagd"] is False  # w1 staat nog uit
