"""OCR mag niet ongelimiteerd draaien (PLAN.md #20.1, BENCHMARK §54).

§54 dichtte de decompressiebom met een pixelgrens; wat overbleef is dat OCR de
zwaarste kostenpost is. Ná de 12 MP-grens is de zwaarste legale plaat 4,8s, maar
tesseract-tijd is geen zuivere functie van pixels — een pathologisch beeld vol
ruis dat op tekst lijkt kan tesseract veel langer laten spinnen.

`pytesseract` heeft een `timeout` die de tesseract-**subprocess** SIGKILL't, dus
die grens komt écht vrij (anders dan een asyncio-timeout, die een blokkerende
C-aanroep niet stopt). De grens komt uit config (DR6), en een timeout is geen
fout maar "onleesbaar": de resolver valt terug op de beeld-fingerprint, precies
zoals bij te weinig tekst. Een kapotte tesseract-installatie blijft wél luid.
"""

from __future__ import annotations

import dataclasses
import io
import time

import pytesseract
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import doublecheck.api as api
from doublecheck.config import OcrSettings, load_config
from doublecheck.ocr import extract_text
from doublecheck.storage import connect, init_schema


def _instellingen(**overschrijf) -> OcrSettings:
    return dataclasses.replace(load_config().ocr, **overschrijf)


def _dichte_plaat(zijde: int = 2400) -> Image.Image:
    beeld = Image.new("RGB", (zijde, zijde), "white")
    tekenaar = ImageDraw.Draw(beeld)
    for y in range(0, zijde, 16):
        tekenaar.text((5, y), "lorem ipsum dolor sit amet consectetur " * 3, fill="black")
    return beeld


def test_ocr_settings_carries_a_positive_timeout():
    assert load_config().ocr.timeout_seconds > 0


def test_the_timeout_is_handed_to_tesseract(monkeypatch):
    """DR6: de waarde komt uit config, niet uit code. Sinds #25.21 delen
    schriftherkenning en lezen die ene grens: de herkenning krijgt hem, het
    lezen wat er daarna over is."""
    gezien = {}

    def vang(afbeelding, lang=None, timeout=0, **rest):
        gezien["lezen"] = timeout
        return "iets"

    def osd(afbeelding, timeout=0, **rest):
        gezien["herkennen"] = timeout
        return "Script: Latin\nScript confidence: 9.0\n"

    monkeypatch.setattr(pytesseract, "image_to_string", vang)
    monkeypatch.setattr(pytesseract, "image_to_osd", osd)
    settings = _instellingen(timeout_seconds=7, per_schrift=True)
    extract_text(Image.new("RGB", (50, 50), "white"), settings)
    assert gezien.get("herkennen", 7) == 7
    assert 6.5 < gezien["lezen"] <= 7


def test_a_timed_out_ocr_falls_back_to_unreadable(monkeypatch):
    def val_om(*a, **k):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_string", val_om)
    uit = extract_text(Image.new("RGB", (50, 50), "white"), _instellingen())
    assert uit.readable is False
    assert uit.text == ""


def test_a_broken_install_stays_loud(monkeypatch):
    """Een ontbrekende tesseract is geen per-verzoekfout maar een kapotte
    machine; die mag niet stilletjes elke aanvraag onleesbaar maken."""
    def geen_tesseract(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", geen_tesseract)
    with pytest.raises(pytesseract.TesseractNotFoundError):
        extract_text(Image.new("RGB", (50, 50), "white"), _instellingen())


def test_a_real_dense_image_is_bounded_by_the_timeout():
    """Het bewijs dat de subprocess écht gekillt wordt: een plaat die zonder
    grens seconden kost, met timeout 1 in ruim onder de twee."""
    start = time.perf_counter()
    uit = extract_text(_dichte_plaat(), _instellingen(timeout_seconds=1))
    verstreken = time.perf_counter() - start
    assert uit.readable is False
    assert verstreken < 3.0, f"timeout hield niet: {verstreken:.1f}s"


@pytest.fixture
def client():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_resolve_answers_gracefully_when_ocr_times_out(client, monkeypatch):
    """Een traag beeld hangt de dienst niet en geeft geen 500: het valt terug
    op de beeldroute, precies zoals een beeld zonder leesbare tekst."""
    def val_om(*a, **k):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_string", val_om)
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buffer, format="PNG")
    respons = client.post("/resolve", files={"image": ("s.png", buffer.getvalue(), "image/png")})
    assert respons.status_code == 200
    assert respons.json()["category"] == "none"


def test_detection_and_reading_together_never_exceed_the_timeout(monkeypatch):
    """Schriftherkenning en lezen delen één tijdgrens (§55). Het lezen kreeg
    eerst altijd minstens een seconde, ook als de herkenning de grens al
    opmaakte; met een grens van 10 seconden kon één beeld er 11 kosten, en
    onder drukte viel de test hierboven daardoor af en toe om."""
    import pytesseract

    gekregen = []

    def trage_osd(afbeelding, **kw):
        time.sleep(0.9)
        return "Script: Telugu\nScript confidence: 9.0\n"

    def lees(afbeelding, lang, timeout):
        gekregen.append(timeout)
        return "tekst"

    monkeypatch.setattr(pytesseract, "image_to_osd", trage_osd)
    monkeypatch.setattr(pytesseract, "image_to_string", lees)
    start = time.perf_counter()
    uit = extract_text(Image.new("RGB", (50, 50), "white"),
                       _instellingen(timeout_seconds=1, per_schrift=True, schriften={"Telugu": "tel+eng"}))
    assert time.perf_counter() - start < 1.2
    assert gekregen == [] and uit.readable is False      # geen tijd meer over: niet lezen, onleesbaar
