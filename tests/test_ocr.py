from doublecheck.config import load_config
from doublecheck.ocr import extract_text
from tests.beelden import kop_screenshot, vormen

KOP = ["Minister Jansen is afgetreden", "vanwege het datalek"]


def test_ocr_extracts_headline():
    instellingen = load_config().ocr

    resultaat = extract_text(kop_screenshot(KOP), instellingen)

    assert resultaat.readable is True
    assert "Jansen" in resultaat.text
    assert "afgetreden" in resultaat.text
    assert "datalek" in resultaat.text


def test_no_text_falls_back_to_image():
    instellingen = load_config().ocr

    resultaat = extract_text(vormen(1), instellingen)

    assert resultaat.readable is False
    assert len(resultaat.text) < instellingen.min_chars


def test_ocr_survives_compression_and_noise():
    instellingen = load_config().ocr

    resultaat = extract_text(kop_screenshot(KOP, korrel=True), instellingen)

    assert resultaat.readable is True
    assert "Jansen" in resultaat.text


def test_ocr_accepts_raw_bytes():
    import io

    instellingen = load_config().ocr
    buffer = io.BytesIO()
    kop_screenshot(KOP).save(buffer, format="PNG")

    resultaat = extract_text(buffer.getvalue(), instellingen)

    assert "Jansen" in resultaat.text
