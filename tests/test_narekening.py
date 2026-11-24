"""Herrekening van *niet bevestigd* op de bewaarde antwoorden (PLAN #32.42, PO 2026-11-06): niet voor oud nieuws, en
niet als een onafhankelijke bron zonder band het bevestigt; zonder nieuwe vragen."""

from doublecheck import narekening as nr

STAAT = {"domeinen": {"rt.com": {"naam": "RT"}}}


def _item(set_="W", datum="2010-05-01", tekst="Een kop"):
    return {"id": "x", "set": set_, "datum": datum, "tekst": tekst}


def _rij(uitkomst="niet bevestigd", bronnen=()):
    return {"id": "x", "set": "W", "arm": "C", "kleur": None, "uitkomst": uitkomst, "bronnen": list(bronnen)}


def _bron(site, rol="bevestigt", band=None, soort="overig"):
    return {"url": f"https://{site}/a", "site": site, "rol": rol, "band": band, "soort": soort}


def test_old_news_by_its_own_date_is_from_before_two_years_and_ordinary_text_has_no_event():
    assert nr.oud_volgens_datum(_item(datum="2024-11-04"))
    assert not nr.oud_volgens_datum(_item(datum="2024-11-05"))
    assert not nr.oud_volgens_datum(_item(datum=None))
    assert not nr.oud_volgens_datum(_item(set_="G", datum="2019-01-01"))
    assert nr.oud_volgens_datum(_item(datum="2025-01-01"), jaren=1)


def test_a_year_in_the_message_makes_it_old_only_when_the_newest_year_is_2023_or_earlier():
    assert nr.oud_volgens_tekst(_item(tekst="Salzburg (Österreich), 20.08.2005: Brücke eingestürzt"))
    assert not nr.oud_volgens_tekst(_item(tekst="Gab es 2016 164.000, sind es 2024 ganze 188.000"))
    assert not nr.oud_volgens_tekst(_item(tekst="Geen jaartal, dus de waarschuwing blijft"))
    assert not nr.oud_volgens_tekst(_item(tekst="Bestelnummer 12023 en 20230"))


def test_an_unbanded_confirmation_counts_unless_it_is_a_platform_state_media_low_or_a_contradiction():
    assert nr.bevestigd_zonder_band(_rij(bronnen=[_bron("terra.com.br")]), STAAT)
    for bron in (_bron("x.com", soort="platform"), _bron("rt.com"), _bron("blog.net", band="laag"),
                 _bron("terra.com.br", rol="spreekt tegen"), _bron("bbc.com", band="goed")):
        assert not nr.bevestigd_zonder_band(_rij(bronnen=[bron]), STAAT), bron
    assert not nr.bevestigd_zonder_band(_rij(bronnen=[_bron("a.pt", band="wisselend")]), STAAT)
    assert nr.bevestigd_zonder_band(_rij(bronnen=[_bron("a.pt", band="wisselend")]), STAAT, banden=(None, "wisselend"))
    dubbel = _rij(bronnen=[_bron("a.pt"), _bron("a.pt")])
    assert not nr.bevestigd_zonder_band(dubbel, STAAT, minimum=2)
    assert nr.bevestigd_zonder_band(_rij(bronnen=[_bron("a.pt"), _bron("b.pt")]), STAAT, minimum=2)


def test_only_unconfirmed_turns_into_unsure_and_every_other_answer_stays():
    rijen = [_rij(), {**_rij("klopt"), "id": "y"}, {**_rij(), "id": "z"}]
    items = {"x": _item(datum="2008-01-01"), "y": _item(datum="2008-01-01"), "z": _item(datum="2026-11-01")}
    uit = nr.toepassen(rijen, items, lambda r, i: nr.oud_volgens_datum(i))
    assert [r["uitkomst"] for r in uit] == ["onzeker", "klopt", "niet bevestigd"]
    assert rijen[0]["uitkomst"] == "niet bevestigd"


def _met(kleur, uitkomst, *bronnen):
    return {**_rij(uitkomst, bronnen), "kleur": kleur}


def test_an_alarm_whose_only_contradiction_is_a_fact_check_page_loses_its_proof_on_the_first_day():
    weg = lambda url: "fullfact.org" in url or "/confere/" in url  # noqa: E731
    rijen = [{**_met("rood", "klopt niet", _bron("fullfact.org", rol="spreekt tegen")), "id": "a"},
             {**_met("rood", "klopt niet", _bron("fullfact.org", rol="spreekt tegen"),
                     _bron("bbc.com", rol="spreekt tegen", band="goed")), "id": "b"},
             {**_met(None, "niet bevestigd"), "id": "c"},
             {**_met("groen", "klopt", _bron("fullfact.org", band="goed"), _bron("bbc.com", band="goed")), "id": "d"},
             {**_met("groen", "klopt", _bron("cnn.com", band="goed"), _bron("bbc.com", band="goed")), "id": "e"}]
    labels = {"a#C": "bewijst", "b#C": "bewijst", "d#C": "vals"}
    uit = nr.zonder_lek(rijen, labels, weg)
    assert uit == {"alarm": 2, "alarm zonder tegenspraak": 1, "bewijst": 2, "bewijst zonder tegenspraak": 1,
                   "bewijst met tegenspraak": 1, "niet bevestigd": 1, "groen": 2, "groen niet meer gedragen": 1,
                   "groen vals niet meer gedragen": 1}


def _kop(titel, site="dw.com", band="goed", rol="bevestigt"):
    return {"url": f"https://www.{site}/a", "site": site, "titel": titel, "band": band, "rol": rol}


def test_a_real_headline_on_the_own_site_of_the_named_outlet_may_turn_green():
    bericht = "DW\nZambia's civil service overhaul raises questions"
    rij = {**_rij("onzeker", [_kop("Zambia’s civil service overhaul raises questions | DW | 06.11.2026")]),
           "oordeel": "klopt"}
    assert nr.eigen_kop(rij, bericht)
    assert not nr.eigen_kop({**rij, "oordeel": "onzeker"}, bericht)
    assert not nr.eigen_kop(rij, "BBC News\nZambia's civil service overhaul raises questions")
    assert not nr.eigen_kop(rij, "Zambia's civil service overhaul raises questions")
    assert not nr.eigen_kop(rij, "DW\nZambia overhaul")
    assert nr.eigen_kop(rij, "dw.\nZambia's civil service overhaul raises questions")


def test_never_from_another_site_a_site_without_band_a_different_title_or_with_a_contradiction():
    bericht = "DW\nZambia's civil service overhaul raises questions"
    for bron in (_kop("Zambia's civil service overhaul raises questions", site="blog.example"),
                 _kop("Zambia's civil service overhaul raises questions", band=None),
                 _kop("Zambia cuts thousands of jobs in the civil service")):
        assert not nr.eigen_kop({**_rij("onzeker", [bron]), "oordeel": "klopt"}, bericht), bron
    tegen = [_kop("Zambia's civil service overhaul raises questions"), _kop("Fake", site="bbc.com", rol="spreekt tegen")]
    assert not nr.eigen_kop({**_rij("onzeker", tegen), "oordeel": "klopt"}, bericht)
