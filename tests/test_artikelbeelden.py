"""De virale tekst uit de screenshots in het factcheckartikel (PLAN #25.12).

Factcheckartikelen citeren de virale tekst zelden in hun eigen tekst (§82);
hij staat in de beelden die ze tonen. Die beelden lezen we met de OCR per
schrift (#25.21) en de tekst wordt een extra formulering van dezelfde claim.
Alleen tekst en vingerafdruk, nooit het beeld (DR3).
"""

import json

import numpy as np

from doublecheck import artikelbeelden as ab
from doublecheck import variantenbatch as vb

PAGINA = """<html><head>
<meta property="og:image" content="https://cdn.factly.in/2024/viral-post.jpg">
</head><body>
<img src="/wp-content/themes/factly/logo.png" width="180">
<div class="entry-content"><div class="wp-block">
<img src="https://cdn.factly.in/2024/viral-post.jpg">
<img src="/uploads/2024/screenshot-1.jpg" srcset="/uploads/2024/screenshot-1-300.jpg 300w, /uploads/2024/screenshot-1-1200.jpg 1200w">
</div>
<img data-src="/uploads/2024/screenshot-2.png" src="data:image/gif;base64,R0lGOD">
<img src="/icons/whatsapp-share.svg">
<img src="https://secure.gravatar.com/avatar/abc?s=96">
<img src="/uploads/2024/tiny.jpg" width="40" height="40">
<img src="/uploads/2023/10/Follow-WhatsApp-channel-minified-scaled.jpeg">
</div>
<div class="related-posts"><img src="/uploads/2024/other-article-featured-image.jpg"></div>
</body></html>"""


def test_the_images_of_an_article_are_found_without_logos_icons_and_placeholders():
    beelden = ab.beelden_uit_artikel(PAGINA, "https://factly.in/a/")
    assert beelden == [
        "https://cdn.factly.in/2024/viral-post.jpg",               # og:image eerst, en maar één keer
        "https://factly.in/uploads/2024/screenshot-1-1200.jpg",    # de grootste uit srcset
        "https://factly.in/uploads/2024/screenshot-2.png",         # lui geladen: data-src
    ]


def test_a_stamp_or_verdict_line_is_not_viral_text():
    tekst = "FALSE\nFACT CHECK\nBill Gates wil iedereen chippen\nmet het coronavaccin, zegt hij zelf"
    assert ab.schoon_ocr(tekst) == "Bill Gates wil iedereen chippen met het coronavaccin, zegt hij zelf"
    assert ab.schoon_ocr("FAKE\nfact-check") == ""


def test_a_line_carries_its_origin_and_fits_the_variant_pipeline(tmp_path):
    """Dezelfde vorm als de claimvarianten, zodat embedden en meten hetzelfde
    gereedschap gebruiken; de herkomst gaat mee per tekst."""
    regel = ab.regel("gfc-1", "https://factly.in/a/", [
        ("https://cdn.factly.in/v.jpg", "Bill Gates wil iedereen chippen met het coronavaccin", "nl")])
    assert regel["varianten"] == [{"soort": "ocr-artikelbeeld", "taal": "nl",
                                   "tekst": "Bill Gates wil iedereen chippen met het coronavaccin",
                                   "beeld": "https://cdn.factly.in/v.jpg"}]
    assert regel["ocr"] and regel["claim_id"] == "gfc-1"
    (tmp_path / "regels.jsonl").write_text(json.dumps(regel) + "\n", encoding="utf-8")

    def vingerafdruk(teksten, versie):
        from types import SimpleNamespace
        return [SimpleNamespace(vector=np.ones(4, dtype=np.float32)) for _ in teksten]

    vb.embed(tmp_path, "model-a", vingerafdruk, portie=4)
    rijen, matrix = vb.lees_vectoren(tmp_path, "model-a")
    assert rijen == [("gfc-1", "nl", "Bill Gates wil iedereen chippen met het coronavaccin")]
    assert matrix.shape == (1, 4)


def test_an_article_already_read_is_skipped_on_resume(tmp_path):
    (tmp_path / "regels.jsonl").write_text(
        json.dumps(ab.regel("gfc-1", "https://factly.in/a/", [])) + "\n", encoding="utf-8")
    assert ab.al_gelezen(tmp_path) == {"https://factly.in/a/"}


def test_without_a_recognisable_article_body_only_the_shared_image_counts():
    """Liever minder dan verkeerd: zonder inhoudsblok kunnen de beelden van
    andere artikelen of reclame zijn."""
    pagina = """<html><head><meta property="og:image" content="https://x.org/deelbeeld.jpg"></head>
    <body><img src="/a.jpg"><img src="/b.jpg"></body></html>"""
    assert ab.beelden_uit_artikel(pagina, "https://x.org/c/") == ["https://x.org/deelbeeld.jpg"]


def test_an_unfetchable_address_is_skipped_not_fatal():
    """Een beeldadres met een ongeldige hostnaam gaf een UnicodeError die de
    proef stopte; een slecht adres in andermans artikel hoort overgeslagen."""
    class Web:
        def get(self, url):
            raise UnicodeError("encoding with 'idna' codec failed (UnicodeError: label too long)")

    assert ab._haal(Web(), "https://" + "x" * 80 + ".example/beeld.jpg") is None
