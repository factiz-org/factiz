"""De feitenbasis (B34, PLAN #30.1b): een feit krijgt een oormerk met een
openbare regel over bronnen, nooit op eigen gezag; en naast een vastgesteld
feit mag Factiz nooit een rood oordeel zetten (B33, nultolerantie op de kern).
"""

import pytest

from doublecheck import feitenbasis as fb

REGISTER = {
    "britannica": {"naam": "Encyclopaedia Britannica", "uitgever": "Encyclopaedia Britannica, Inc.",
                   "soort": "naslagwerk", "url": "https://www.britannica.com", "waarom": "redactie en correcties"},
    "wikipedia-en": {"naam": "Wikipedia (English)", "uitgever": "Wikimedia Foundation",
                     "soort": "naslagwerk", "url": "https://en.wikipedia.org", "waarom": "bronnen per bewering"},
    "wikipedia-nl": {"naam": "Wikipedia (Nederlands)", "uitgever": "Wikimedia Foundation",
                     "soort": "naslagwerk", "url": "https://nl.wikipedia.org", "waarom": "bronnen per bewering"},
    "nasa": {"naam": "NASA", "uitgever": "NASA", "soort": "wetenschap", "url": "https://www.nasa.gov",
             "waarom": "wetenschappelijk instituut"},
    "smithsonian": {"naam": "Smithsonian Institution", "uitgever": "Smithsonian Institution",
                    "soort": "onderzoek", "url": "https://www.si.edu", "waarom": "archief en collectie"},
    "esa": {"naam": "ESA", "uitgever": "European Space Agency", "soort": "wetenschap", "url": "https://www.esa.int",
            "waarom": "ruimtevaartinstituut"},
    "noaa": {"naam": "NOAA", "uitgever": "NOAA", "soort": "wetenschap", "url": "https://www.noaa.gov",
             "waarom": "wetenschappelijk instituut", "overheid": "Verenigde Staten (federale regering)"},
    "cdc": {"naam": "CDC", "uitgever": "CDC", "soort": "wetenschap", "url": "https://www.cdc.gov",
            "waarom": "volksgezondheidsinstituut", "overheid": "Verenigde Staten (federale regering)",
            "niet_meegeteld": [{"onderwerp": "vaccins", "sinds": "2026-07-22",
                                "reden": "standpunt gewijzigd zonder nieuw bewijs"}]},
}
REGISTER["nasa"]["overheid"] = "Verenigde Staten (federale regering)"


def _feit(*bronnen, oormerk=None, formuleringen=None):
    return {
        "id": "apollo-11",
        "zin": "On 20 July 1969 Apollo 11 astronauts landed on the Moon.",
        "bronnen": [{"bron": b, "vindplaats": f"https://voorbeeld.example/{b}", "nagelopen": "2026-10-17"}
                    for b in bronnen],
        "oormerk": {"door": "Claude", "datum": "2026-10-17"} if oormerk is None else oormerk,
        "formuleringen": formuleringen if formuleringen is not None else [
            {"taal": "en", "tekst": "Apollo 11 landed on the Moon in 1969."},
            {"taal": "en", "tekst": "The moon landing really happened."},
            {"taal": "nl", "tekst": "De maanlanding van 1969 heeft echt plaatsgevonden."},
        ],
    }


def test_a_fact_with_four_independent_sources_of_two_kinds_gets_its_earmark():
    assert fb.problemen_kern([_feit("britannica", "nasa", "smithsonian", "esa")], REGISTER) == []


def test_a_fact_needs_four_independent_sources():
    problemen = fb.problemen_kern([_feit("britannica", "nasa", "smithsonian")], REGISTER)
    assert any("onafhankelijke bronnen" in p for p in problemen)


def test_language_editions_of_one_publisher_count_once():
    problemen = fb.problemen_kern([_feit("wikipedia-en", "wikipedia-nl", "nasa", "smithsonian")], REGISTER)
    assert any("onafhankelijke bronnen" in p for p in problemen)


def test_agencies_of_one_government_count_as_one_voice():
    problemen = fb.problemen_kern([_feit("britannica", "nasa", "noaa", "smithsonian")], REGISTER)
    assert any("onafhankelijke bronnen" in p for p in problemen)


def test_four_publishers_of_one_kind_are_not_enough():
    register = {**REGISTER, **{n: {**REGISTER["britannica"], "naam": n, "uitgever": n} for n in ("larousse", "treccani")}}
    problemen = fb.problemen_kern([_feit("britannica", "wikipedia-en", "larousse", "treccani")], register)
    assert any("soorten" in p for p in problemen)


def test_a_source_outside_the_register_does_not_count():
    problemen = fb.problemen_kern([_feit("britannica", "nasa", "smithsonian", "eigen-blog")], REGISTER)
    assert any("eigen-blog" in p for p in problemen)


def test_a_fact_without_an_earmark_is_refused():
    problemen = fb.problemen_kern([_feit("britannica", "nasa", "smithsonian", "esa", oormerk={})], REGISTER)
    assert any("oormerk" in p for p in problemen)


def test_a_fact_is_measured_in_several_phrasings_and_languages():
    alleen_engels = [{"taal": "en", "tekst": "Apollo 11 landed on the Moon in 1969."}]
    problemen = fb.problemen_kern([_feit("britannica", "nasa", "smithsonian", "esa", formuleringen=alleen_engels)],
                                  REGISTER)
    assert any("formuleringen" in p for p in problemen)


def test_a_register_source_that_contradicts_a_fact_keeps_it_open():
    feit = {**_feit("britannica", "nasa", "smithsonian", "esa"), "onderwerpen": ["ruimtevaart"],
            "tegenspraak": [{"bron": "noaa", "vindplaats": "https://voorbeeld.example/noaa", "nagelopen": "2026-10-17"}]}
    problemen = fb.problemen_kern([feit], REGISTER)
    assert any("open" in p and "noaa" in p for p in problemen)


def test_a_source_that_changed_position_without_new_evidence_does_not_keep_a_fact_open():
    feit = {**_feit("britannica", "nasa", "smithsonian", "esa"), "onderwerpen": ["vaccins"],
            "tegenspraak": [{"bron": "cdc", "vindplaats": "https://voorbeeld.example/cdc", "nagelopen": "2026-10-17"}]}
    assert fb.problemen_kern([feit], REGISTER) == []


def test_a_source_not_counted_on_a_topic_does_not_support_a_fact_there_either():
    feit = {**_feit("britannica", "cdc", "smithsonian", "esa"), "onderwerpen": ["vaccins"]}
    problemen = fb.problemen_kern([feit], REGISTER)
    assert any("onafhankelijke bronnen" in p for p in problemen)


def test_every_register_source_names_kind_publisher_and_reason():
    kapot = {"x": {"naam": "X", "uitgever": "", "soort": "blog", "url": "https://x.example", "waarom": ""}}
    problemen = fb.problemen_register(kapot)
    assert any("soort" in p for p in problemen) and any("uitgever" in p for p in problemen)


def test_the_committed_register_and_core_follow_the_rule_of_b34():
    register = fb.lees_register()
    assert fb.problemen_register(register) == []
    assert fb.problemen_kern(fb.lees_kern(), register) == []


def _antwoord(categorie, *oordelen):
    return {"category": categorie,
            "evidence": {"checks": [{"verdict_normalized": o, "review_date": "2024-01-01"} for o in oordelen]}
            if oordelen else None}


@pytest.mark.parametrize("antwoord, verwacht", [
    (_antwoord("matched", "onwaar"), "rood"),
    (_antwoord("matched", "misleidend"), "rood"),
    (_antwoord("matched", "onwaar", "waar"), "omstreden"),
    (_antwoord("matched", "deels-waar"), "deels-waar"),
    (_antwoord("matched", "onbewezen"), "onbewezen"),
    (_antwoord("matched", "waar"), "waar"),
    (_antwoord("related"), "verwant"),
    (_antwoord("none"), "niets"),
])
def test_next_to_a_fact_red_or_contested_is_a_false_alarm_and_doubt_is_reported_apart(antwoord, verwacht):
    uitkomst = fb.n3_uitkomst(antwoord)
    assert uitkomst == verwacht
    assert (uitkomst in fb.VALS_N3) == (verwacht in {"rood", "omstreden"})


def test_all_phrasings_of_a_fact_land_in_the_same_half():
    feit = _feit("britannica", "nasa", "smithsonian", "esa")
    items = fb.n3_items([feit])
    assert len(items) == 3 and len({i["helft"] for i in items}) == 1
    assert len({i["sleutel"] for i in items}) == 3


def _kranten():
    def krant(naam, groep=None):
        b = {"naam": naam, "uitgever": naam, "soort": "journalistiek", "url": "https://krant.example", "waarom": "redactie"}
        return {**b, "groep": groep} if groep else b
    return {"nrc": krant("NRC", "Mediahuis"), "de-standaard": krant("De Standaard", "Mediahuis"),
            "le-monde": krant("Le Monde"), "el-pais": krant("El País"), "faz": krant("FAZ")}


def test_newspapers_of_one_media_group_count_as_one_voice():
    register = {**REGISTER, **_kranten()}
    problemen = fb.problemen_kern([_feit("nrc", "de-standaard", "britannica", "nasa")], register)
    assert any("onafhankelijke bronnen" in p for p in problemen)
    assert fb.problemen_kern([_feit("nrc", "le-monde", "britannica", "nasa")], register) == []


def test_newspapers_alone_never_earmark_a_fact():
    register = {**REGISTER, **_kranten()}
    problemen = fb.problemen_kern([_feit("nrc", "le-monde", "el-pais", "faz")], register)
    assert any("soorten" in p for p in problemen)


def test_the_true_sentences_of_minimal_pairs_join_n3_in_the_half_of_their_fact():
    feit = _feit("britannica", "nasa", "smithsonian", "esa")
    paren = [{"revid": 7, "feit": "apollo-11", "waar": "Apollo 11 landed in the Sea of Tranquility.", "label": "stijl"}]
    items = fb.n3_items([feit], paren)
    paar = [i for i in items if i["bron"] == "paar"]
    assert len(paar) == 1 and paar[0]["sleutel"] == "N3:paar:7" and paar[0]["tekst"].startswith("Apollo 11 landed")
    assert len({i["helft"] for i in items}) == 1


MOTOR = {"text_embedding": "BAAI/bge-m3@x+casefold", "drempels": {"text_match": 0.87}, "vraagvorm": True}


def test_a_release_is_refused_while_the_core_shows_red():
    uitslag = {"motor": MOTOR, "kern": "abc", "rood": [{"feit": "crimea-annexation", "taal": "en"}]}
    redenen = fb.kernpoort(uitslag, MOTOR, "abc")
    assert any("rood" in r for r in redenen)


def test_a_release_is_refused_without_a_core_check_for_this_engine_and_this_core():
    assert any("kerncheck" in r for r in fb.kernpoort(None, MOTOR, "abc"))
    schoon = {"motor": MOTOR, "kern": "abc", "rood": []}
    assert any("motor" in r for r in fb.kernpoort(schoon, {**MOTOR, "vraagvorm": False}, "abc"))
    assert any("kern" in r for r in fb.kernpoort(schoon, MOTOR, "def"))


def test_a_clean_core_check_lets_the_release_through():
    assert fb.kernpoort({"motor": MOTOR, "kern": "abc", "rood": []}, MOTOR, "abc") == []


def test_a_measurement_names_the_judge_only_when_it_is_on():
    import dataclasses

    from doublecheck.config import load_config
    from doublecheck.feitenbasis import motor_van

    uit = load_config()
    assert "rechter" not in motor_van(uit)
    aan = dataclasses.replace(uit, rechter=dataclasses.replace(uit.rechter, aan=True, model="rechter-d@abc", pad="x"))
    assert motor_van(aan)["rechter"] == {"model": "rechter-d@abc", "diepte": 5}


def test_a_measurement_names_the_article_rule_only_when_it_is_on():
    """#30.11: een run met een artikel per zin is een andere motor dan een
    zonder; uit blijft de motor zoals hij was, zodat oudere runs erbij horen."""
    import dataclasses

    from doublecheck.config import ArtikelSettings, load_config
    from doublecheck.feitenbasis import motor_van

    uit = load_config()
    assert "artikel" not in motor_van(uit)
    assert motor_van(dataclasses.replace(uit, artikel=ArtikelSettings(per_zin=True)))["artikel"] == {"per_zin": True}


def test_once_gate_wordings_exist_the_kern_gate_measures_only_them():
    from doublecheck.feitenbasis import n3_items

    kern = [{"id": "f1", "formuleringen": [{"taal": "en", "tekst": "laag een"},
                                            {"taal": "es", "tekst": "poort uno", "rol": "poort"}]}]
    assert [i["tekst"] for i in n3_items(kern) if i["bron"] == "kern"] == ["poort uno"]
    zonder = [{"id": "f1", "formuleringen": [{"taal": "en", "tekst": "laag een"}]}]
    assert [i["tekst"] for i in n3_items(zonder)] == ["laag een"]


def test_the_layer_feeds_on_the_layer_wordings_only():
    from doublecheck.feitenbasis import laagformuleringen

    kern = [{"id": "f1", "formuleringen": [{"taal": "en", "tekst": "a"}, {"taal": "es", "tekst": "b", "rol": "poort"}]}]
    assert laagformuleringen(kern) == [("f1", "a")]
