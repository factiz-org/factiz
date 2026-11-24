import dataclasses

import pytest

from doublecheck.config import load_config
from doublecheck.ocr import extract_text
from doublecheck.source import ObservedSource, observe_sources
from tests.beelden import kop_screenshot, vormen

VERBODEN = ("verified", "geverifieerd", "confirmed", "bevestigd", "authentic")


def test_source_marked_observed_not_verified():
    # Volledige route: screenshot met zichtbare bron → OCR → bronwaarneming.
    afbeelding = kop_screenshot(
        ["Minister Jansen is afgetreden", "nieuwscheckers.nl"]
    )
    tekst = extract_text(afbeelding, load_config().ocr).text

    bronnen = observe_sources(tekst)

    assert len(bronnen) == 1
    bron = bronnen[0]
    assert bron.value == "nieuwscheckers.nl"
    assert bron.status == "waargenomen"

    # Structureel: het type kan geen geverifieerde status uitdrukken.
    veldnamen = {veld.name for veld in dataclasses.fields(ObservedSource)}
    assert not any(
        token in naam.lower() for naam in veldnamen for token in VERBODEN
    ), veldnamen
    with pytest.raises(AttributeError):
        bron.status = "geverifieerd"


def test_recognises_url_and_bare_domain():
    bronnen = observe_sources(
        "Bekijk https://www.knack.be/factcheck/xyz en ook factcheck.vlaanderen"
    )

    waarden = {bron.value for bron in bronnen}
    assert waarden == {"knack.be", "factcheck.vlaanderen"}
    assert all(bron.status == "waargenomen" for bron in bronnen)


def test_no_source_observed_when_none_visible():
    assert observe_sources("Minister Jansen is afgetreden vanwege het datalek") == ()
    assert observe_sources("") == ()


def test_screenshot_without_text_observes_nothing():
    tekst = extract_text(vormen(1), load_config().ocr).text

    assert observe_sources(tekst) == ()


def test_sentence_punctuation_is_not_a_domain():
    bronnen = observe_sources("Dat klopt niet.Volgens de minister is het anders")

    assert bronnen == ()
