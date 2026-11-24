"""Een eigen beoordeling voor factcheckers en redacties zonder Lin e.a. en zonder teken (PLAN #32.29d): punten alleen
met een citaat dat letterlijk op de opgehaalde pagina staat, een factchecker van een staat of partij nooit goed, en
eerst een ijking met eisen vooraf."""

import json

import pytest

from doublecheck import eigenscore as es

PAGINAS = [{"url": "https://voorbeeld.es/", "tekst": "Últimas noticias. El Gobierno aprueba el presupuesto. " * 20},
           {"url": "https://voorbeeld.es/correcciones", "tekst": "Política de correcciones: corregimos los errores "
                                                                 "de forma visible y con fecha."},
           {"url": "https://voorbeeld.es/quienes-somos", "tekst": "Voorbeeld S.L. es propiedad de la familia García. "
                                                                  "Director: Ana López."}]


@pytest.fixture(autouse=True)
def _korte_paginas(monkeypatch):
    """De voorbeeldpagina's zijn kort; de grens voor te weinig tekst heeft een eigen test."""
    monkeypatch.setattr(es, "MIN_TEKST", 0)


def _antwoord(soort="newsroom", staat=False, staat_citaat="", **ja):
    antwoorden = [{"vraag": v, "ja": True, "citaat": c, "pagina": p} for v, (c, p) in ja.items()]
    return json.dumps({"soort": soort, "staat_of_partij": staat, "staat_citaat": staat_citaat,
                       "antwoorden": antwoorden})


def test_a_point_counts_only_with_a_quote_found_on_the_page():
    tekst = _antwoord(correcties=("corregimos los errores de forma visible", 2),
                      eigenaar=("es propiedad de la familia García", 3),
                      code=("tenemos un código ético público", 3))  # dit citaat staat nergens
    uit = es.lees(tekst, PAGINAS, signaal=False)
    assert uit["punten"]["correcties"] == 15 and uit["punten"]["eigenaar"] == 10
    assert uit["punten"]["code"] == 0 and "code" in uit["niet gevonden"]


def test_a_quote_on_another_page_than_named_still_counts_but_a_paraphrase_does_not():
    uit = es.lees(_antwoord(eigenaar=("Es propiedad de la familia   García", 1),
                            leiding=("La directora es Ana López", 3)), PAGINAS, signaal=False)
    assert uit["punten"]["eigenaar"] == 10  # hoofdletters en spaties tellen niet, de pagina ook niet
    assert uit["punten"]["leiding"] == 0


def test_a_newsroom_gets_the_30_points_for_no_repeated_false_news_unless_a_signal_says_otherwise():
    schoon = es.lees(_antwoord(), PAGINAS, signaal=False)
    vlag = es.lees(_antwoord(), PAGINAS, signaal=True)
    assert schoon["punten"]["nepnieuws"] == 30 and vlag["punten"]["nepnieuws"] == 0
    assert schoon["totaal"] == 30 and schoon["band"] == "laag"


def test_the_band_lines_are_65_and_40():
    assert es.band(65) == "goed" and es.band(64) == "wisselend" and es.band(41) == "wisselend"
    assert es.band(40) == "laag" and es.band(0) == "laag"


def test_a_fact_checker_scores_on_the_five_principles_of_the_ifcn():
    paginas = [{"url": "https://fc.org/about", "tekst": "We are nonpartisan. Our funding comes from readers and the "
                                                        "Open Society grant. We explain our methodology for every "
                                                        "check. We link to all sources. Corrections are noted."}]
    uit = es.lees(_antwoord("fact-checker", partijloos=("We are nonpartisan", 1),
                            geld=("Our funding comes from readers", 1), werkwijze=("We explain our methodology", 1),
                            bronnen=("We link to all sources", 1), correcties=("Corrections are noted", 1)),
                  paginas, signaal=False)
    assert uit["soort"] == "factchecker" and uit["totaal"] == 100 and uit["band"] == "goed"


def test_a_state_or_party_fact_checker_is_never_good():
    paginas = [{"url": "https://staat.cn/", "tekst": "Hosted by the Cyberspace Administration. We are nonpartisan. "
                                                     "Our funding comes from the state. We explain our methodology. "
                                                     "We link to all sources. Corrections are noted."}]
    ja = dict(partijloos=("We are nonpartisan", 1), geld=("Our funding comes from the state", 1),
              werkwijze=("We explain our methodology", 1), bronnen=("We link to all sources", 1),
              correcties=("Corrections are noted", 1))
    uit = es.lees(_antwoord("fact-checker", True, "Hosted by the Cyberspace Administration", **ja), paginas,
                  signaal=False)
    assert uit["totaal"] == 100 and uit["band"] == "wisselend" and uit["staat"]
    # zonder citaat telt de bewering over de staat niet, en ook het signaal van buiten (staatsmedia) sluit goed uit
    zonder = es.lees(_antwoord("fact-checker", True, "", **ja), paginas, signaal=False)
    assert zonder["band"] == "goed" and not zonder["staat"]
    assert es.lees(_antwoord("fact-checker", **ja), paginas, signaal=False, staat=True)["band"] == "wisselend"


def test_other_sites_and_unreadable_answers_get_no_band():
    assert es.lees(_antwoord("other"), PAGINAS, signaal=False)["band"] is None
    for kapot in ("", "geen json", json.dumps({"soort": "newsroom"}), None):
        uit = es.lees(kapot, PAGINAS, signaal=False)
        assert uit["band"] is None and uit["soort"] is None


def test_page_links_are_chosen_by_keyword_on_the_same_site():
    html = ('<html><head><script>var x="quienes-somos"</script><style>.a{}</style></head><body>'
            '<a href="/quienes-somos">Quiénes somos</a><a href="https://otro.com/about">About</a>'
            '<a href="/deportes">Deportes</a><a href="/politica-de-correcciones">Correcciones</a>'
            '<a href="mailto:x@y.es">contacto</a><a href="/quienes-somos#equipo">Equipo</a>'
            '<p>El texto de la portada.</p></body></html>')
    tekst, links = es.tekst_en_links(html, "https://www.voorbeeld.es/")
    assert "El texto de la portada." in tekst and "var x" not in tekst and ".a{}" not in tekst
    gekozen = es.kies_links(links, "https://www.voorbeeld.es/", 5)
    assert gekozen == ["https://www.voorbeeld.es/quienes-somos", "https://www.voorbeeld.es/politica-de-correcciones"]


def test_the_request_shows_each_page_once_with_its_number():
    params = es.verzoek("voorbeeld.es", PAGINAS)
    tekst = params["messages"][0]["content"][0]["text"]
    assert "[P1] https://voorbeeld.es/" in tekst and "[P3] https://voorbeeld.es/quienes-somos" in tekst
    assert params["output_config"]["format"]["type"] == "json_schema"


def test_the_calibration_requirements_are_those_set_in_advance():
    redacties = [("goed", "goed")] * 6 + [("wisselend", "wisselend")] * 4 + [("laag", "laag")] * 2 + \
        [("goed", "wisselend"), ("laag", "wisselend")]
    fc = {"met teken": ["goed"] * 14 + ["wisselend"], "propaganda": ["wisselend", "laag", None]}
    eisen = es.ijk_eisen(redacties, fc)
    assert eisen == {"redacties in dezelfde band": True, "nooit goed tegen laag": True,
                     "factcheckers met teken goed": True, "geen propaganda goed": True}
    slecht = es.ijk_eisen(redacties[:-2] + [("goed", "laag"), ("laag", "goed"), ("wisselend", "goed")],
                          {"met teken": ["goed"] * 13 + ["laag"] * 2, "propaganda": ["goed", "laag", "laag"]})
    assert not any(slecht.values())


def test_a_site_the_model_calls_other_drops_out_of_the_newsroom_calibration_and_the_line_scales():
    """12 van de 14; valt er een als *anders*, dan 11 van de 13 (afgerond naar boven, 86%)."""
    assert es.ijk_eisen([("goed", "goed")] * 11 + [("goed", "wisselend")] * 2, {"met teken": [], "propaganda": []}
                        )["redacties in dezelfde band"]
    assert not es.ijk_eisen([("goed", "goed")] * 10 + [("goed", "wisselend")] * 3,
                            {"met teken": [], "propaganda": []})["redacties in dezelfde band"]


def test_the_calibration_draw_is_fixed_and_per_band():
    kandidaten = {f"site{i}.com": ("goed" if i < 20 else "wisselend" if i < 30 else "laag") for i in range(40)}
    a, b = es.trek_ijkset(kandidaten, {"goed": 7, "wisselend": 4, "laag": 3}, 32293), \
        es.trek_ijkset(dict(reversed(list(kandidaten.items()))), {"goed": 7, "wisselend": 4, "laag": 3}, 32293)
    assert a == b and len(a) == 14
    assert sum(kandidaten[s] == "goed" for s in a) == 7 and sum(kandidaten[s] == "laag" for s in a) == 3


def test_an_unknown_version_is_refused():
    with pytest.raises(ValueError):
        es.verzoek("x.org", PAGINAS, versie="eigenscore-v0")


def test_outside_signals_take_the_30_points_and_state_media_are_never_good():
    staat = {"domeinen": {"staat.ru": {"naam": "Staat"}}}
    ja = dict(correcties=("corregimos los errores de forma visible", 2), eigenaar=("es propiedad de la familia García", 3))
    schoon = es.beoordeel_site("voorbeeld.es", _antwoord(**ja), PAGINAS, set(), staat)
    genoemd = es.beoordeel_site("voorbeeld.es", _antwoord(**ja), PAGINAS, {"voorbeeld.es"}, staat)
    assert schoon["totaal"] == 55 and genoemd["totaal"] == 25 and genoemd["band"] == "laag"
    alles = {v: ("corregimos los errores de forma visible", 2) for v, _, wat in es.VRAGEN["redactie"] if wat}
    assert es.beoordeel_site("voorbeeld.es", _antwoord(**alles), PAGINAS, set(), staat)["band"] == "goed"
    assert es.beoordeel_site("www.staat.ru", _antwoord(**alles), PAGINAS, set(), staat)["band"] == "wisselend"


def test_links_are_found_in_other_languages_and_scripts():
    links = [("https://vistinomer.mk/za-vistinomer/", "За Вистиномер"), ("https://vistinomer.mk/metodologija/", "Методологија"),
             ("https://www.delfi.lt/apie/kontaktai/", "Kontaktai"), ("https://www.piyao.org.cn/gywm.htm", "关于我们"),
             ("https://kashif.ps/x", "من نحن"), ("https://vistinomer.mk/sport/", "Спорт")]
    gekozen = es.kies_links(links, "https://vistinomer.mk/", 10) + es.kies_links(links, "https://www.delfi.lt/", 10) \
        + es.kies_links(links, "https://www.piyao.org.cn/", 10) + es.kies_links(links, "https://kashif.ps/", 10)
    assert gekozen == ["https://vistinomer.mk/za-vistinomer/", "https://vistinomer.mk/metodologija/",
                       "https://www.delfi.lt/apie/kontaktai/", "https://www.piyao.org.cn/gywm.htm", "https://kashif.ps/x"]


def test_a_site_with_too_little_text_gets_no_band_instead_of_a_low_score(monkeypatch):
    monkeypatch.setattr(es, "MIN_TEKST", 1500)
    weinig = [{"url": "https://js.cl/", "tekst": "Cargando..."}]
    uit = es.lees(_antwoord(), weinig, signaal=False)
    assert uit["band"] is None and uit["te weinig tekst"]
    assert not es.lees(_antwoord(), PAGINAS * 20, signaal=False)["te weinig tekst"]


def test_a_question_given_with_its_explanation_still_counts():
    """Haiku zette in de eerste ijking de hele vraag ("partijloos: a commitment ...") in plaats van de naam."""
    tekst = json.dumps({"soort": "newsroom", "staat_of_partij": False, "staat_citaat": "", "antwoorden": [
        {"vraag": "correcties: a published corrections policy", "ja": True,
         "citaat": "corregimos los errores de forma visible", "pagina": 2},
        {"vraag": " Eigenaar ", "ja": True, "citaat": "es propiedad de la familia García", "pagina": 3}]})
    uit = es.lees(tekst, PAGINAS, signaal=False)
    assert uit["punten"]["correcties"] == 15 and uit["punten"]["eigenaar"] == 10


def test_a_cut_off_answer_gets_no_band():
    tekst = json.dumps({"soort": "newsroom", "staat_of_partij": False, "staat_citaat": "", "antwoorden": []})[:-20]
    assert es.lees(tekst, PAGINAS, signaal=False)["band"] is None
