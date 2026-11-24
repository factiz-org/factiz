"""De controlepagina op try.factiz.org (PLAN #31.13, DESIGN §4g): de regels
die vóór het bouwen vastlagen."""

import dataclasses
import re

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import checkui
from doublecheck.config import load_config

# Wat de pagina nooit mag gebruiken; in stukken, zodat dit bestand ze zelf niet aanroept.
HTML_UIT_TEKST = ("inner" + "HTML", "outer" + "HTML", "insertAdjacent" + "HTML", "document." + "write")


def _pagina(aan: bool) -> str:
    config = load_config()
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, aan=aan))
    api.app.dependency_overrides[api.get_config] = lambda: config
    try:
        antwoord = TestClient(api.app).get("/check")
    finally:
        api.app.dependency_overrides.clear()
    assert antwoord.status_code == 200 and antwoord.headers["content-type"].startswith("text/html")
    return antwoord.text


def _kort() -> str:
    """De korte privacytekst die bij de huidige config hoort: met het beeld aan die van B55."""
    return checkui.PRIVACY_KORT_BEELD if load_config().berichtcontrole.beeld else checkui.PRIVACY_KORT


@pytest.fixture(scope="module")
def pagina():
    return _pagina(aan=True)


def test_the_page_is_served_next_to_ask_and_sends_the_message_in_the_body(pagina):
    assert "fetch('/check'" in pagina and "method: 'POST'" in pagina
    assert "?text=" not in pagina and "URLSearchParams" not in pagina  # DR3: nooit in een adres


def test_the_page_never_builds_html_from_a_string(pagina):
    for verboden in HTML_UIT_TEKST:
        assert verboden not in pagina, verboden


def test_when_the_check_is_off_the_page_says_so_and_sends_nothing():
    uit = _pagina(aan=False)
    assert 'data-aan="false"' in uit and checkui.FOUTEN["off"] in uit
    assert '<button type="submit" id="knop" disabled>' in uit
    assert 'data-aan="true"' in _pagina(aan=True)


def test_the_privacy_short_version_sits_next_to_the_input(pagina):
    assert _kort() in pagina and 'href="https://factiz.org/privacy/"' in pagina


def test_the_model_explanation_is_only_in_the_raw_response(pagina):
    """B31: de uitlegzin van het model is niet gemeten op trouw aan de bonnetjes."""
    assert ".explanation" not in pagina


def test_every_error_state_has_its_own_text(pagina):
    assert set(checkui.FOUTEN) >= {"off", "no_text", "image_unreadable", "too_large", "cap", "model_unreachable"}
    for tekst in checkui.FOUTEN.values():
        assert tekst in pagina, tekst


def test_the_verdict_has_words_for_every_outcome_and_a_second_line_without_colour(pagina):
    """B51: groen en rood alleen waar de bronnenlijst het draagt; zonder kleur zegt een tweede regel waarom."""
    assert set(checkui.UITKOMST) == set(checkui.ZONDER_KLEUR) == {"klopt", "klopt niet", "misleidend", "onzeker"}
    for tekst in [*checkui.UITKOMST.values(), *checkui.ZONDER_KLEUR.values()]:
        assert tekst in pagina, tekst
    zichtbaar = re.sub(r"<style>.*?</style>", " ", pagina, flags=re.S)
    assert "100%" not in zichtbaar  # D1: nooit honderd procent


def test_each_source_shows_whether_it_confirms_or_contradicts_and_how_reliable_it_is(pagina):
    for tekst in [*checkui.BAND.values(), *checkui.ROL.values(), *checkui.ROUTE.values()]:
        assert tekst in pagina, tekst
    assert "b.band" in pagina and "b.role" in pagina and "d.route" in pagina


def test_the_privacy_text_names_the_search_service_too(pagina):
    """B51: de gemaskeerde tekst gaat ook naar de zoekdienst; dat staat er eerlijk."""
    assert "search service" in checkui.PRIVACY_KORT and "search service" in checkui.PRIVACY_KORT_BEELD
    assert _kort() in pagina



def test_misleading_is_its_own_outcome_and_state_media_carry_a_label(pagina):
    """#32.11: misleidend in oranje met een eigen woord, en het label bij een bron van een staat."""
    assert checkui.UITKOMST["misleidend"] in pagina and checkui.ZONDER_KLEUR["misleidend"] in pagina
    assert "orange: 'oranje'" in pagina and checkui.STAATSMEDIA in pagina and "b.state_media" in pagina


def test_a_claim_about_an_image_without_colour_says_why(pagina):
    """#32.12: zonder het beeld wordt een bewering over een beeld nooit groen; de pagina zegt waarom."""
    assert "photo or video" in checkui.OVER_BEELD and checkui.OVER_BEELD in pagina and "d.about_image" in pagina


def test_the_two_layers_have_their_own_words_and_come_only_from_their_own_fields(pagina):
    """#32.13: de bewering met haar kleur, wat klopt, en wat er echt gebeurde; nooit de uitlegzin (B31)."""
    assert set(checkui.LAGEN) == {"bewering", "feit", "anders"}
    for tekst in checkui.LAGEN.values():
        assert tekst in pagina, tekst
    assert "d.fact" in pagina and "d.what_happened" in pagina and checkui.ROL["confirms_fact"] in pagina


def test_a_fact_check_from_the_database_that_contradicts_is_counted_on_the_search_route(pagina):
    """#32.30: met lezer-v5 kan een check uit de database de kleur geven; de herkomstregel noemt hem dan."""
    assert "fact-check" in checkui.ROL.get("same_claim", "").lower() or "same_claim" in checkui.ROL
    assert "factchecks_tegen" in pagina


def test_no_claim_and_satire_have_their_own_words_and_no_verdict_line(pagina):
    """#32.32, DESIGN §4g: geen bewering en satire krijgen geen kleur en geen oordeel over waar of onwaar."""
    assert set(checkui.ZONDER_BEWERING) == {"no_claim", "satire"}
    for kop, zin in checkui.ZONDER_BEWERING.values():
        assert kop in pagina and zin in pagina
    assert "d.outcome" in pagina


def test_no_claim_says_what_factiz_found_and_never_that_the_message_makes_none(pagina):
    """DESIGN §4g (PO 2026-11-03, BENCHMARK §209): bij een screenshot met onleesbare tekst kan de bewering in de foto
    zitten; de pagina zegt wat Factiz vond, en bij een screenshot dat het de foto niet bekijkt."""
    kop, zin = checkui.ZONDER_BEWERING["no_claim"]
    assert kop == "No checkable claim found" and zin == "Factiz found no checkable claim in this message."
    assert "screenshot" in checkui.GEEN_BEWERING_BEELD and "photo" in checkui.GEEN_BEWERING_BEELD
    assert checkui.GEEN_BEWERING_BEELD in pagina and "makes no checkable claim" not in pagina
    assert "vanBeeld" in pagina and "toon(d, !!bestand)" in pagina


def test_mostly_true_marks_the_wrong_words_in_what_was_read_and_says_the_correction_in_words(pagina):
    """B48, DESIGN §4i: de markering op de foute woorden, de verbetering in woorden ernaast, ook voor een
    schermlezer; nooit in het groen."""
    assert "d.correction" in pagina and "el('mark'" in pagina and "c.should_be" in pagina
    for tekst in checkui.MAAR.values():
        assert tekst in pagina, tekst
    assert "marked: " in pagina and ".sr {" in pagina


def test_a_message_about_a_claim_says_so_above_the_verdict_on_that_claim(pagina):
    """DESIGN §4g: het bericht zelf krijgt geen kleur; de bewering waarover het gaat wel."""
    assert checkui.OVER_BEWERING.startswith("This message reports on a claim made by someone else")
    assert checkui.OVER_BEWERING in pagina and "d.claim_colour" in pagina


def test_the_privacy_text_says_how_long_anthropic_keeps_the_text_and_promises_no_zero_retention(pagina):
    """B54 (PO 2026-11-03): zonder zero data retention de standaard van Anthropic; de korte tekst zegt dat eerlijk."""
    assert "at most 30 days" in checkui.PRIVACY_KORT and "does not train on it" in checkui.PRIVACY_KORT
    assert "does not keep it" not in checkui.PRIVACY_KORT + checkui.PRIVACY_KORT_BEELD and _kort() in pagina


def test_the_upload_sentence_of_b55_shows_only_when_the_image_goes_along():
    """B55: één duidelijke zin bij het uploaden, geen knop per controle; alleen als `beeld` aan staat."""
    assert "Anthropic's model" in checkui.BEELD_ZIN and "30 days" in checkui.BEELD_ZIN
    assert checkui.BEELD_ZIN in checkui.pagina(True, beeld=True)
    assert checkui.BEELD_ZIN not in checkui.pagina(True, beeld=False)
    formulier = lambda b: checkui.pagina(True, beeld=b).split('<form id="formulier">')[1].split("</form>")[0]  # noqa: E731
    assert "checkbox" not in formulier(True) and formulier(True).count("<input") == formulier(False).count("<input")


def test_with_the_image_on_the_short_privacy_text_says_the_screenshot_goes_along_too():
    """B55 (tussenrelease 2026-11-03): met `beeld` aan zegt de korte tekst eerlijk dat ook het screenshot naar het
    model gaat, met eerst zwart wat de tekstherkenning vindt; zonder beeld blijft de tekst van B54."""
    met, zonder = checkui.pagina(True, beeld=True), checkui.pagina(True, beeld=False)
    assert checkui.PRIVACY_KORT_BEELD in met and checkui.PRIVACY_KORT not in met
    assert checkui.PRIVACY_KORT in zonder and checkui.PRIVACY_KORT_BEELD not in zonder
    laag = checkui.PRIVACY_KORT_BEELD.lower()
    assert "screenshot" in laag and "blacked out" in laag and "at most 30 days" in laag and "brave search" in laag


def test_not_confirmed_has_its_own_words_no_colour_and_lists_the_searches(pagina):
    """B57, DESIGN §4l: *niet bevestigd* is een eigen uitkomst, nooit rood, oranje of groen; daaronder de zoekvragen
    die Factiz deed, elk met wat ze vonden."""
    assert checkui.NIET_BEVESTIGD["kop"] == "Not confirmed"
    assert checkui.NIET_BEVESTIGD["zin"] == "No reliable source reports this."
    for tekst in (*checkui.NIET_BEVESTIGD.values(), *checkui.ZOEKSOORT.values()):
        assert tekst in pagina
    assert "uit === 'unconfirmed'" in pagina and "d.searches" in pagina
    assert set(checkui.ZOEKSOORT) == {"own_site", "real_news", "the_source"}


def test_the_privacy_texts_say_honestly_that_the_name_of_who_published_a_post_can_remain():
    """B67 (§252): nummers, e-mailadressen, handles, profiellinks en namen in chats gaan eruit; de naam van wie een
    openbare post plaatste, en namen bij reacties, kunnen blijven. Nergens meer "names are removed" zonder voorbehoud."""
    for tekst in (checkui.BEELD_ZIN, checkui.PRIVACY_KORT, checkui.PRIVACY_KORT_BEELD):
        assert "published" in tekst and "can remain" in tekst, tekst
        assert not tekst.startswith("Your screenshot is read on our server in the EU and not kept. Names,")


def test_while_checking_the_page_says_what_factiz_does_how_long_it_takes_and_counts_the_seconds():
    """§251, PO 2026-11-09: "in korte stappen naar werkend". Een controle duurt 10 tot 15 seconden; de pagina zegt wat
    Factiz doet en telt de seconden, in plaats van "a few seconds"."""
    pagina = checkui.pagina(True, beeld=True)
    assert "This takes a few seconds" not in pagina
    assert checkui.BEZIG["tekst"] in pagina and checkui.BEZIG["beeld"] in pagina
    assert "10 to 15 seconds" in checkui.BEZIG["tekst"] and "setInterval" in pagina and "clearInterval" in pagina
