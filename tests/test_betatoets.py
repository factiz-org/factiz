"""De toets voor de beta (ronde 4, PLAN #31.14): de regels die vóór de eerste
vraag aan het model vastlagen."""

import pytest

from doublecheck import betatoets as t
from doublecheck import verificatie as v
from doublecheck.config import load_config


def test_a_news_article_becomes_its_headline_and_first_sentences_without_the_outlet():
    tekst = ("'We like partisan warfare.' Chechens fighting in Ukraine – on both sides | Ukraine | The Guardian\n"
             "On one side, fighters loyal to Ramzan Kadyrov. On the other, Chechens who fled. " + "More text. " * 80)
    uit = t.artikelbericht(tekst)
    assert uit.startswith("'We like partisan warfare.' Chechens fighting in Ukraine – on both sides\n")
    assert "The Guardian" not in uit and "| Ukraine" not in uit
    assert "On one side, fighters loyal to Ramzan Kadyrov." in uit and len(uit) <= t.MAX_ARTIKEL
    assert uit.endswith(".")  # afgebroken op een zin, niet midden in een woord


def _pools():
    def rijen(voorvoegsel, n):
        return [{"id": f"{voorvoegsel}{i:04d}", "sleutel": f"{voorvoegsel}:{i}", "tekst": f"tekst {i}."} for i in range(n)]

    return {"ware checks": rijen("c", 92), "artikelen": rijen("a", 400), "onwaar oud": rijen("o", 300),
            "screenshots": rijen("s", 150), "onwaar vers": rijen("n", 250), "zonder": rijen("z", 200)}


def test_the_set_has_the_parts_and_forms_of_the_plan_fixed_by_seed():
    keuze = t.kies(_pools())
    assert keuze == t.kies(_pools())
    tel = {}
    for s in keuze:
        tel[(s["deel"], s["vorm"])] = tel.get((s["deel"], s["vorm"]), 0) + 1
    assert tel == {("waar", "tekst"): 150, ("waar", "chat"): 150, ("bekend", "tekst"): 100,
                   ("bekend", "screenshot"): 100, ("onbekend", "tekst"): 100, ("onbekend", "chat"): 100,
                   ("zonder bewering", "tekst"): 50, ("zonder bewering", "chat"): 50}
    assert sum(s["id"].startswith("c") for s in keuze) == 92  # alle vrije ware checks
    assert len({s["id"] for s in keuze}) == 800


def test_red_is_one_to_three_on_the_scale_or_false_and_green_is_seven_or_more():
    assert t.rood(3, "klopt") and t.rood(5, "klopt niet") and not t.rood(5, "let op")
    assert t.groen(7) and t.groen(10) and not t.groen(5)


def test_unknown_fake_news_gets_no_memory_and_the_fact_check_sites_are_blocked():
    config = load_config()
    params = t.machineverzoek_b("5G spreads the virus", "2026-09-01", ["snopes.com", "afp.com"], config)
    assert params["tools"][0]["blocked_domains"] == ["snopes.com", "afp.com"]
    assert "Factiz memory: no fact-check found" in params["messages"][0]["content"][0]["text"]
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["model"] == config.berichtcontrole.model_id


def test_the_batch_halves_the_tokens_but_not_the_search_fee():
    kosten = t.kosten_batch({"in": 1_000, "uit": 100, "cache_lees": 0, "cache_schrijf": 0, "zoek": 1})
    assert kosten == pytest.approx((1_000 * 2 + 100 * 10) / 2 / 1e6 + v.ZOEKEN_PER_1000 / 1000)


def _stuk(i, deel, eigen=()):
    label = {"waar": "waar", "zonder bewering": "geen bewering"}.get(deel, "onwaar")
    return {"id": i, "deel": deel, "vorm": "tekst", "label": label, "eigen": list(eigen)}


def _uit(oordeel, stand, bronnen=(), feit=None):
    return {"oordeel": oordeel, "stand": stand, "feit": feit, "bronnen": list(bronnen)}


EIGEN = {"soort": "geheugen", "claim": "c1"}
WEB = {"soort": "web", "url": "https://example.org"}


def test_the_count_refuses_while_something_that_counts_has_no_label():
    stukken = [_stuk("w1", "waar"), _stuk("b1", "bekend", ["c1"]), _stuk("b2", "bekend"),
               _stuk("o1", "onbekend"), _stuk("z1", "zonder bewering")]
    uit = {"w1": _uit("klopt niet", 1, [WEB]), "b1": _uit("klopt niet", 1, [EIGEN]), "b2": _uit("klopt niet", 3, [WEB]),
           "o1": _uit("klopt", 7, [WEB]), "z1": _uit("let op", 3)}
    with pytest.raises(t.Weigering):
        t.telling(stukken, uit, {}, {})
    labels = {("w1", "klopt niet"): "vals", ("o1", "klopt"): "vals", ("z1", "let op"): "vals"}
    telling = t.telling(stukken, uit, labels, {"b2": "past"})
    assert telling["waar"]["onterecht rood"] == 1 and telling["eis B45"]["gehaald"] == "onder 97%"
    assert telling["bekend"]["bewezen"] == 2
    assert telling["eisen"]["2 bekend nepnieuws minstens 90% rood met bewijs"] is True
    assert telling["eisen"]["3 nepnieuws hoogstens 4 keer groen"] is True
    assert telling["eisen"]["4 zonder bewering nooit rood"] is False


def test_a_10_is_always_read_and_a_wrong_one_breaks_the_bar():
    stukken = [_stuk("w1", "waar")]
    uit = {"w1": _uit("klopt", 10, feit="earth-round")}
    with pytest.raises(t.Weigering):
        t.telling(stukken, uit, {}, {})
    telling = t.telling(stukken, uit, {("w1", 10, "earth-round"): "fout"}, {})
    assert telling["eisen"]["5 geen verkeerde 10"] is False


def test_masking_and_waiting_time_have_their_own_bars():
    stukken = [_stuk("w1", "waar")]
    uit = {"w1": _uit("klopt", 7, [WEB])}
    lek = {"w1": {"telefoon": False, "e-mail": False, "handle": True, "naam": False, "groep": False}}
    tijden = [{"route": 5.0}] * 19 + [{"route": 30.0}]
    telling = t.telling(stukken, uit, {}, {}, lekdata=lek, tijden=tijden)
    assert telling["eisen"]["6 geen nummer, adres of handle gelekt"] is False
    assert telling["eisen"]["7 95% binnen 20 seconden"] is True


def test_a_fact_check_found_on_another_site_counts_as_proof_but_apart():
    """Ook met de factchecksites geblokkeerd vindt het model soms de check zelf, via
    een site die factchecks overneemt. Dat is bewezen, maar niet zelf herkend."""
    stukken = [_stuk("o1", "onbekend"), _stuk("o2", "onbekend")]
    uit = {"o1": _uit("klopt niet", 3, [WEB]), "o2": _uit("klopt niet", 3, [WEB])}
    labels = {("o1", "klopt niet"): "bewijst via factcheck", ("o2", "klopt niet"): "bewijst"}
    telling = t.telling(stukken, uit, labels, {"o1": "past niet"})
    assert telling["onbekend"]["bewezen"] == 2 and telling["onbekend"]["bewezen via een factcheck op het web"] == 1


def test_every_red_with_a_source_on_unknown_fake_news_is_read():
    stukken = [_stuk("o1", "onbekend")]
    uit = {"o1": _uit("klopt niet", 3, [WEB])}
    with pytest.raises(t.Weigering):
        t.telling(stukken, uit, {}, {})
    assert t.steekproef(stukken, uit) == []  # de steekproef is alleen voor bekend nepnieuws
