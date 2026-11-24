"""De eigen factcheck (PLAN #37.4, B82, SPECS E10.S4): een mens schrijft, een ander leest na, en de controle weigert wat
de code van het EFCSN niet toelaat. Het voorstel: docs/voorstellen/2026-11-18-eigen-factcheck.md."""

from pathlib import Path

import pytest

from doublecheck import redactie

WORTEL = Path(__file__).resolve().parent.parent


def _check(**anders):
    check = {
        "sleutel": "proef", "status": "concept", "taal": "nl",
        "adres": "standbeeld-anne-frank-ai", "adres_en": "anne-frank-statue-ai",
        "kop": "Dit beeld van een beklad standbeeld is gemaakt met AI",
        "oordeel": "onwaar", "oordeel_zin": "Het beeld is gemaakt met AI; het echte standbeeld zag er zo nooit uit.",
        "soort": "ai", "vorm": "beeld",
        "bewering": "Het standbeeld van Anne Frank is beklad.", "platform": "X", "eerst_gezien": "2026-11-08", "posts": 5,
        "kort": "Er gaat een beeld rond. Het is gemaakt met AI [1]. De echte bekladding was in 2024 [2].",
        "tekst": "Het Anne Frank Huis meldde de bekladding op 4 augustus 2024 [1]. Ook het Parool schreef erover [2].",
        "niet_weten": "We weten niet wie het beeld maakte.",
        "auteur": "Claude (concept)", "nalezer": "",
        "beeld": [{"rol": "rondgaat", "bestand": "beeld-1.png", "stempel": True,
                   "bijschrift": "Post op X, 8 november 2026, gearchiveerd", "alt": "Een standbeeld met verf; ONWAAR"}],
        "bron": [{"nr": 1, "soort": "bron", "uitgever": "Anne Frank Huis", "titel": "Standbeeld beklad",
                  "datum": "2024-08-04", "url": "https://www.annefrank.org/nl/"},
                 {"nr": 2, "soort": "nieuws", "uitgever": "Het Parool", "titel": "Standbeeld beklad", "datum": "2024-08-04",
                  "url": "https://www.parool.nl/"}],
    }
    check.update(anders)
    return check


def test_a_draft_with_two_sources_for_its_core_passes():
    assert redactie.controleer(_check()) == []


def test_an_address_is_a_short_name_of_the_claim_and_a_translation_gets_an_english_one():
    """PLAN #37.11 (PO 2026-11-21: "Jaar en maand"): het adres is geen werknaam maar een korte naam van de bewering, in
    kleine letters zonder accenten; de vertalingen dragen een Engelse naam."""
    for slecht in ("privébezit-klaver", "Klaver-citaat", "klaver", "klaver--citaat", "-klaver-citaat", "a-" + "b" * 60):
        assert any("adres" in f for f in redactie.controleer(_check(adres=slecht))), slecht
    zonder = _check()
    del zonder["adres_en"]
    assert any("adres_en ontbreekt" in f for f in redactie.controleer(zonder))
    # een Engelse check heeft aan haar eigen naam genoeg
    assert redactie.controleer({**zonder, "taal": "en"}) == []
    assert any("adres ontbreekt" in f for f in redactie.controleer({k: v for k, v in _check().items() if k != "adres"}))


def test_the_address_carries_the_year_and_month_of_publication_and_the_name_in_the_language_of_the_page():
    check = _check(status="gepubliceerd", gepubliceerd="2026-11-19")
    assert redactie.maand(check, "2026-12-02") == "2026-11"
    assert redactie.pad_in(check, "nl", "2026-11") == "/nl/radar/2026/11/standbeeld-anne-frank-ai/"
    assert redactie.pad_in(check, "en", "2026-11") == "/radar/2026/11/anne-frank-statue-ai/"
    assert redactie.pad_in(check, "pt", "2026-11") == "/pt-br/radar/2026/11/anne-frank-statue-ai/"
    # een concept heeft nog geen datum van publicatie: dan de dag van de uitgave
    assert redactie.maand(_check(), "2026-12-02") == "2026-12"


def test_two_checks_with_the_same_name_in_the_same_month_are_refused_but_not_in_another_month():
    a = _check(sleutel="a", gepubliceerd="2026-11-19")
    b = _check(sleutel="b", gepubliceerd="2026-11-30", adres="iets-anders", adres_en="anne-frank-statue-ai")
    assert redactie.botsingen([a, b], "2026-12-02") == [
        "b: het adres 'anne-frank-statue-ai' heeft a in 2026-11 al"]
    assert redactie.botsingen([a, {**b, "gepubliceerd": "2026-12-01"}], "2026-12-02") == []
    # de eigen naam en de Engelse naam van één check mogen gelijk zijn
    assert redactie.botsingen([_check(adres="zelfde-naam", adres_en="zelfde-naam")], "2026-12-02") == []


def test_another_fact_checker_never_counts_as_one_of_the_two_sources():
    bronnen = [_check()["bron"][0], {"nr": 2, "soort": "factcheck", "uitgever": "AFP Factcheck", "titel": "x",
                                     "datum": "2026-11-12", "url": "https://factchecknederland.afp.com/x"}]
    fouten = redactie.controleer(_check(bron=bronnen))
    assert any("twee bronnen" in f for f in fouten)
    # één bron mag alleen met een opgeschreven reden (een eigen verklaring van de politie)
    assert redactie.controleer(_check(bron=bronnen, een_bron="alleen de politie kan dit zeggen")) == []


def test_every_number_in_the_text_points_to_a_source_and_every_source_is_cited():
    fouten = redactie.controleer(_check(tekst="Het Anne Frank Huis meldde het [1] en [3]."))
    assert any("[3]" in f for f in fouten)
    fouten = redactie.controleer(_check(kort="Er gaat een beeld rond.", tekst="Het Anne Frank Huis meldde het [1]."))
    assert any("bron 2" in f for f in fouten)


def test_the_verdict_comes_from_the_scale_and_the_kind_and_form_from_the_archive():
    assert any("oordeel" in f for f in redactie.controleer(_check(oordeel="nep")))
    assert any("soort" in f for f in redactie.controleer(_check(soort="deepfake")))
    assert any("vorm" in f for f in redactie.controleer(_check(vorm="geluid")))
    assert redactie.controleer(_check(soort=None, vorm=None)) == []
    assert redactie.SCHAAL["context"] == {"nl": "Ontbrekende context", "en": "Missing context"}


def test_a_published_check_has_a_named_writer_and_a_human_reader_who_is_not_the_writer():
    """B84 (PO 2026-11-19, "Claude schreef, ik las na"): Claude mag de schrijver zijn, als een mens of de redactie naleest;
    nooit Claude als nalezer, nooit dezelfde naam twee keer, en een concept draagt die naam niet naar buiten."""
    for auteur, nalezer in (("Claude (concept voor de redactie)", "De redactie van Factiz"), ("A. de Vries", ""),
                            ("A. de Vries", "A. de Vries"), ("A. de Vries", "Claude"), ("Claude (AI)", "Claude"),
                            ("", "De redactie van Factiz")):
        fouten = redactie.controleer(_check(status="gepubliceerd", auteur=auteur, nalezer=nalezer, gepubliceerd="2026-12-01"))
        assert fouten, (auteur, nalezer)
    for auteur, nalezer in (("A. de Vries", "B. Jansen"), ("Claude (AI)", "De redactie van Factiz")):
        assert redactie.controleer(_check(status="gepubliceerd", auteur=auteur, nalezer=nalezer,
                                          gepubliceerd="2026-12-01")) == [], (auteur, nalezer)


def test_an_image_that_circulates_always_carries_a_stamp_a_source_line_and_an_alt_text():
    for mis in ({"stempel": False}, {"bijschrift": ""}, {"alt": ""}):
        beeld = [{**_check()["beeld"][0], **mis}]
        assert redactie.controleer(_check(beeld=beeld)), mis
    # het origineel krijgt nooit een stempel
    origineel = {"rol": "origineel", "link": "https://www.annefrank.org/", "stempel": True, "bijschrift": "Anne Frank Huis",
                 "alt": "Het echte standbeeld"}
    assert any("origineel" in f for f in redactie.controleer(_check(beeld=_check()["beeld"] + [origineel])))


def test_an_image_is_blurred_only_with_a_reason_and_a_path_stays_in_the_folder_of_its_check():
    """Vervagen is nooit de standaard (PO 2026-11-18): alleen met een reden, zoals een minderjarige."""
    zonder = [{**_check()["beeld"][0], "vervaag": [[0.4, 0.3, 0.3, 0.1]]}]
    assert any("zonder reden" in f for f in redactie.controleer(_check(beeld=zonder)))
    met = [{**zonder[0], "vervaag_reden": "minderjarige"}]
    assert redactie.controleer(_check(beeld=met)) == []
    scheef = [{**met[0], "vervaag": [[0.4, 0.3, 1.3]]}]
    assert any("vier getallen" in f for f in redactie.controleer(_check(beeld=scheef)))
    elders = [{**_check()["beeld"][0], "pad": "/static/redactie/een-andere/beeld-1.jpg"}]
    assert any("buiten de map" in f for f in redactie.controleer(_check(beeld=elders)))
    eigen = [{**_check()["beeld"][0], "pad": "/static/redactie/proef/beeld-1.jpg"}]
    assert redactie.controleer(_check(beeld=eigen)) == []


def test_the_text_has_no_dash_for_a_pause_and_no_exclamation_mark():
    assert any("streepje" in f for f in redactie.controleer(_check(tekst="Het Huis [1] — en het Parool [2].")))
    assert any("uitroepteken" in f for f in redactie.controleer(_check(kort="Let op! [1] [2]")))


def test_the_claim_is_quoted_as_it_circulated_so_its_own_exclamation_marks_and_dashes_stay():
    """De bewering staat in de woorden van de post zelf (PO 2026-11-18: "De bewering vervangen door de woorden van de posts
    zelf"): haar uitroepteken en streepje zijn van de schrijver, niet van ons. Onze eigen tekst blijft zonder."""
    assert redactie.controleer(_check(bewering="Van Ranst zou BESTRAFT moeten worden — voor zijn aandeel!")) == []
    assert any("uitroepteken" in f for f in redactie.controleer(_check(kop="Let op!")))


def test_the_drafts_in_the_content_folder_pass_the_check():
    mappen = sorted((WORTEL / "content" / "redactie").glob("*/check.toml"))
    for pad in mappen:
        check = redactie.lees(pad)
        assert check["sleutel"] == pad.parent.name
        assert redactie.controleer(check) == [], pad.parent.name


def test_reading_refuses_a_file_that_is_not_toml(tmp_path):
    pad = tmp_path / "x" / "check.toml"
    pad.parent.mkdir()
    pad.write_text("kop = ", encoding="utf-8")
    with pytest.raises(redactie.Weigering):
        redactie.lees(pad)


def test_a_post_by_a_private_person_is_linked_only_through_an_archive_copy():
    post = {"nr": 3, "soort": "bron", "uitgever": "X", "titel": "De post met de bewering", "datum": "2026-11-08",
            "prive": True}
    tekst = _check()["tekst"] + " De post stond er om 12:23 [3]."
    assert redactie.controleer(_check(bron=_check()["bron"] + [post], tekst=tekst)) == []
    # een directe link naar de post van een privépersoon mag niet
    fouten = redactie.controleer(_check(bron=_check()["bron"] + [{**post, "url": "https://x.com/i/status/1"}], tekst=tekst))
    assert any("privépersoon" in f for f in fouten)
    # bij publicatie moet de archiefkopie er zijn
    klaar = dict(status="gepubliceerd", auteur="A. de Vries", nalezer="B. Jansen", gepubliceerd="2026-12-01")
    assert any("archiefkopie" in f for f in redactie.controleer(_check(bron=_check()["bron"] + [post], tekst=tekst, **klaar)))
    gearchiveerd = {**post, "archief": "https://archive.ph/abcde"}
    assert redactie.controleer(_check(bron=_check()["bron"] + [gearchiveerd], tekst=tekst, **klaar)) == []


def test_a_post_that_is_gone_may_stay_without_an_archive_copy_when_the_check_says_so():
    """B84: een post van een privépersoon die niet meer te zien is en waarvan geen kopie bestaat, mag als bron, met de
    vermelding (`weg`); zonder die vermelding blijft de kopie nodig."""
    post = {"nr": 3, "soort": "bron", "uitgever": "X", "titel": "De post met de bewering", "datum": "2026-11-08",
            "prive": True}
    tekst = _check()["tekst"] + " De post stond er om 12:23 [3]."
    klaar = dict(status="gepubliceerd", auteur="Claude (AI)", nalezer="De redactie van Factiz", gepubliceerd="2026-12-01")
    assert any("archiefkopie" in f for f in redactie.controleer(_check(bron=_check()["bron"] + [post], tekst=tekst, **klaar)))
    assert redactie.controleer(_check(bron=_check()["bron"] + [{**post, "weg": True}], tekst=tekst, **klaar)) == []


def test_a_post_that_could_not_be_archived_stays_only_with_the_reason_in_words():
    """Een post van een privépersoon waarvan geen kopie te maken was, mag als bron met de reden (`geen_kopie`), nooit met
    een lege reden en nooit met een directe link (B70)."""
    post = {"nr": 3, "soort": "bron", "uitgever": "X", "titel": "De post uit 2020", "datum": "2020-10-14", "prive": True}
    tekst = _check()["tekst"] + " De post stond er in 2020 [3]."
    klaar = dict(status="gepubliceerd", auteur="Claude (AI)", nalezer="De redactie van Factiz", gepubliceerd="2026-12-01")
    leeg = _check(bron=_check()["bron"] + [{**post, "geen_kopie": "  "}], tekst=tekst, **klaar)
    assert any("archiefkopie" in f for f in redactie.controleer(leeg))
    reden = _check(bron=_check()["bron"] + [{**post, "geen_kopie": "het nummer van de post hebben we niet bewaard"}],
                   tekst=tekst, **klaar)
    assert redactie.controleer(reden) == []


def test_a_published_check_never_carries_a_placeholder_for_a_missing_fact():
    """Een aanduiding [FEIT NODIG: ...] mag in een concept, nooit in een gepubliceerde check: wat ontbreekt, staat bij
    nog uit te zoeken (B84)."""
    klaar = dict(status="gepubliceerd", auteur="Claude (AI)", nalezer="De redactie van Factiz", gepubliceerd="2026-12-01")
    tekst = _check()["tekst"] + " [FEIT NODIG: de tekst van de post.]"
    assert any("FEIT NODIG" in f for f in redactie.controleer(_check(tekst=tekst, **klaar)))
    assert not any("FEIT NODIG" in f for f in redactie.controleer(_check(tekst=tekst)))


def test_a_published_check_keeps_its_open_questions_for_the_reader():
    """B84: wat nog uit te zoeken is, staat op de pagina; alleen wat intern nog moet (`nog_doen`) houdt publicatie tegen."""
    klaar = dict(status="gepubliceerd", auteur="Claude (AI)", nalezer="De redactie van Factiz", gepubliceerd="2026-12-01")
    assert redactie.controleer(_check(nog_uitzoeken=["Wie maakte het beeld?"], **klaar)) == []
    assert any("uit te zoeken" in f for f in redactie.controleer(_check(nog_uitzoeken="Wie maakte het beeld?")))


def test_a_source_link_is_a_web_address():
    bronnen = [_check()["bron"][0], {**_check()["bron"][1], "url": "het Parool van maandag"}]
    assert any("adres" in f for f in redactie.controleer(_check(bron=bronnen)))


def test_a_draft_keeps_what_a_person_still_has_to_do_and_a_published_check_has_nothing_left():
    assert redactie.controleer(_check(nog_doen=["De video naast die van AT5 leggen."])) == []
    klaar = dict(status="gepubliceerd", auteur="A. de Vries", nalezer="B. Jansen", gepubliceerd="2026-12-01")
    assert any("nog te doen" in f for f in redactie.controleer(_check(nog_doen=["De video bekijken."], **klaar)))


def test_a_check_says_whether_it_is_local_or_international_and_nothing_else():
    """B85 (PO 2026-11-19): lokaal of internationaal bepaalt de volgorde op de Radar in een andere taal."""
    assert redactie.controleer(_check(reikwijdte="internationaal")) == []
    assert any("reikwijdte" in f for f in redactie.controleer(_check(reikwijdte="wereldwijd")))


def test_a_published_check_in_a_language_the_editors_do_not_read_says_in_which_language_it_was_reviewed():
    # de PO leest een check in het Turks na in de Engelse vertaling (B85 punt 5, #37.10); de pagina zegt dat, dus een
    # gepubliceerde check in zo'n taal draagt nagelezen_in, en alleen een taal die de redactie leest
    los = dict(status="gepubliceerd", auteur="Claude (AI)", nalezer="De redactie van Factiz", gepubliceerd="2026-11-20",
               taal="tr")
    assert any("nagelezen_in" in f for f in redactie.controleer(_check(**los)))
    assert redactie.controleer(_check(**los, nagelezen_in="en")) == []
    assert any("nagelezen_in" in f for f in redactie.controleer(_check(**los, nagelezen_in="tr")))
    assert redactie.controleer(_check(**{**los, "taal": "en"})) == []
