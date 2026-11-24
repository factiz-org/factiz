"""Een klein bestand dat naar een enorme afbeelding ontvouwt (veiligheidssweep).

De byte-limiet (8 MB) zegt niets over het aantal pixels ná decompressie: een PNG
van 76 KB kan 400 megapixels worden. Twee gevaren:

- boven PILs harde grens gooit `Image.open().load()` een `DecompressionBombError`
  — die erft van `Exception`, niet van de drie die de resolver ving, dus het
  werd een 500 in plaats van een nette 422;
- eronder, in het waarschuwingsgebied, laat PIL het bestand gewoon door en kost
  één verzoek seconden aan CPU. Een handvol legt de dienst plat.

Beide worden nu bij binnenkomst geweigerd op een pixel-limiet.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import doublecheck.api as api
from doublecheck.image_fingerprint import MAX_IMAGE_PIXELS, TeGroteAfbeelding, as_image
from doublecheck.storage import connect, init_schema


def _png(breedte, hoogte) -> bytes:
    buffer = io.BytesIO()
    Image.new("1", (breedte, hoogte), 1).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@pytest.fixture
def client():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_as_image_refuses_a_bomb_before_decoding_it():
    # 12000x12000 = 144 MP: klein op schijf, groot ontvouwd.
    with pytest.raises(TeGroteAfbeelding):
        as_image(_png(12000, 12000)).load()


def test_a_pixel_bomb_is_a_clean_refusal_not_a_crash(client):
    for maat in (12000, 20000):
        respons = client.post(
            "/resolve", files={"image": ("bom.png", _png(maat, maat), "image/png")}
        )
        assert respons.status_code == 422, maat
        assert "image" in respons.json()["detail"].lower()


def test_a_large_but_low_byte_text_image_is_refused():
    """De byte-limiet ving dit niet: 5000x5000 = 25 MP, 400 KB op schijf, maar
    tientallen seconden OCR-werk. De pixelgrens is de enige die dit stopt."""
    with pytest.raises(TeGroteAfbeelding):
        as_image(_png(5000, 5000)).load()


def test_an_ordinary_screenshot_still_passes():
    from tests.beelden import kop_screenshot

    buffer = io.BytesIO()
    kop_screenshot(["Een gewone kop"]).save(buffer, format="PNG")
    beeld = as_image(buffer.getvalue())
    beeld.load()
    assert beeld.size[0] * beeld.size[1] < MAX_IMAGE_PIXELS
