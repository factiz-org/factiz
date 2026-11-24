"""OCR per schrift (PLAN #25.21, BENCHMARK §78).

De OCR las alleen `nld+eng+deu+fra+spa`; van 170 Telugu-beelden van FACTLY
herkende de resolver er nul. Tesseract kan eerst het schrift herkennen (OSD)
en dan het juiste pakket lezen. Twijfel versoepelt nooit, maar hier ook
niet: bij een onzeker of onbekend schrift blijft het de huidige set, dus het
wordt nooit slechter dan het was.
"""

import pathlib
import re
import shutil

import pytest
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from doublecheck import ocr
from doublecheck.config import OcrSettings, load_config


def _instellingen(**anders):
    basis = dict(languages="nld+eng", min_chars=12, timeout_seconds=10,
                 schriften={"Telugu": "tel+eng", "Arabic": "ara+fas+eng"}, schrift_zekerheid=2.0,
                 per_schrift=True)
    return OcrSettings(**{**basis, **anders})


@pytest.fixture
def gelezen(monkeypatch):
    talen = []

    def _lees(afbeelding, lang, timeout):
        talen.append(lang)
        return "een tekst die lang genoeg is om te tellen"

    monkeypatch.setattr(pytesseract, "image_to_string", _lees)
    return talen


def _osd(monkeypatch, uitvoer=None, fout=None):
    def _detecteer(afbeelding, **kw):
        if fout:
            raise fout
        return uitvoer
    monkeypatch.setattr(pytesseract, "image_to_osd", _detecteer)


def _wit():
    return Image.new("RGB", (64, 64), "white")


def test_a_telugu_image_is_read_with_the_telugu_pack(monkeypatch, gelezen):
    _osd(monkeypatch, "Page number: 0\nScript: Telugu\nScript confidence: 6.20\n")
    ocr.extract_text(_wit(), _instellingen())
    assert gelezen == ["tel+eng"]


@pytest.mark.parametrize("uitvoer", [
    "Script: Telugu\nScript confidence: 0.40\n",      # onzeker
    "Script: Khmer\nScript confidence: 9.00\n",       # niet in de tabel
    "Script: Latin\nScript confidence: 9.00\n",       # Latijn: de bestaande set
])
def test_an_uncertain_unknown_or_latin_script_keeps_the_configured_languages(monkeypatch, gelezen, uitvoer):
    _osd(monkeypatch, uitvoer)
    ocr.extract_text(_wit(), _instellingen())
    assert gelezen == ["nld+eng"]


@pytest.mark.parametrize("fout", [pytesseract.TesseractError(1, "Too few characters. Skipping this page"),
                                  RuntimeError("Tesseract process timeout")])
def test_a_script_detection_that_gives_up_keeps_the_configured_languages(monkeypatch, gelezen, fout):
    _osd(monkeypatch, fout=fout)
    uitslag = ocr.extract_text(_wit(), _instellingen())
    assert gelezen == ["nld+eng"] and uitslag.readable


def test_without_a_script_table_no_detection_runs(monkeypatch, gelezen):
    _osd(monkeypatch, fout=AssertionError("OSD hoort niet te draaien"))
    ocr.extract_text(_wit(), _instellingen(schriften={}))
    assert gelezen == ["nld+eng"]


_LETTER = pathlib.Path("/System/Library/Fonts/KohinoorTelugu.ttc")


@pytest.mark.skipif(not _LETTER.exists() or shutil.which("tesseract") is None,
                    reason="geen Telugu-lettertype of geen tesseract op deze machine")
def test_real_telugu_text_comes_back_in_telugu_script():
    """Eind tot eind, met de echte config: een kop in Telugu op een beeld."""
    if "tel" not in pytesseract.get_languages(config=""):
        pytest.skip("tesseract heeft geen Telugu-pakket")
    beeld = Image.new("RGB", (1400, 220), "white")
    teken = ImageDraw.Draw(beeld)
    teken.text((30, 60), "ఈ ఫోటో పాతది, ఇటీవలి సంఘటనకు సంబంధం లేదు",
               font=ImageFont.truetype(str(_LETTER), 64), fill="black")
    telugu = lambda tekst: sum("ఀ" <= c <= "౿" for c in tekst)
    import dataclasses

    met = ocr.extract_text(beeld, dataclasses.replace(load_config().ocr, per_schrift=True)).text
    zonder = ocr.extract_text(beeld, _instellingen(languages=load_config().ocr.languages, schriften={})).text
    assert telugu(met) >= 15
    assert telugu(zonder) == 0


def test_the_switch_off_keeps_the_old_ocr_whatever_the_table_says(monkeypatch, gelezen):
    """Aanzetten is een release (B22); tot dan leest elk beeld als voorheen."""
    _osd(monkeypatch, fout=AssertionError("OSD hoort niet te draaien"))
    ocr.extract_text(_wit(), _instellingen(per_schrift=False))
    assert gelezen == ["nld+eng"]


# --- Twee keer lezen bij twijfel over het schrift (#25.22) -------------------

def _data(lezingen, gelezen):
    """Nep-`image_to_data`: per pakket een tekst en een woordzekerheid."""
    def _lees(afbeelding, lang, timeout, output_type):
        gelezen.append(lang)
        tekst, zekerheid = lezingen[lang]
        woorden = tekst.split()
        return {"text": woorden, "conf": [zekerheid] * len(woorden), "block_num": [1] * len(woorden),
                "par_num": [1] * len(woorden), "line_num": [1] * len(woorden)}
    return _lees


TWIJFEL = "Page number: 0\nScript: Arabic\nScript confidence: 2.00\n"


@pytest.mark.parametrize("arabisch, verwacht", [
    (80.0, "خبر کاذب درباره واکسن"),            # het schriftpakket leest zekerder
    (20.0, "DI ua islas ai el ga pl"),         # de huidige lezing leest zekerder
    (45.0, "DI ua islas ai el ga pl"),         # gelijkstand: de huidige set
])
def test_in_doubt_both_readings_are_made_and_the_surer_one_wins(monkeypatch, arabisch, verwacht):
    gelezen = []
    lezingen = {"nld+eng": ("DI ua islas ai el ga pl", 45.0), "ara+fas+eng": ("خبر کاذب درباره واکسن", arabisch)}
    monkeypatch.setattr(pytesseract, "image_to_data", _data(lezingen, gelezen))
    _osd(monkeypatch, TWIJFEL)
    uitslag = ocr.extract_text(_wit(), _instellingen(schrift_zekerheid=3.0, schrift_ondergrens=1.5))
    assert gelezen == ["nld+eng", "ara+fas+eng"]       # de huidige lezing eerst
    assert uitslag.text == verwacht


@pytest.mark.parametrize("osd, verwacht", [
    ("Script: Arabic\nScript confidence: 6.00\n", ["ara+fas+eng"]),   # zeker: alleen het schrift
    ("Script: Arabic\nScript confidence: 1.00\n", ["nld+eng"]),       # onder de ondergrens: zoals nu
])
def test_outside_the_doubt_band_nothing_changes(monkeypatch, gelezen, osd, verwacht):
    _osd(monkeypatch, osd)
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("buiten de twijfel wordt niet twee keer gelezen")))
    ocr.extract_text(_wit(), _instellingen(schrift_zekerheid=3.0, schrift_ondergrens=1.5))
    assert gelezen == verwacht


def test_without_time_for_a_second_reading_the_current_one_stays(monkeypatch):
    """De tijdgrens geldt voor beide lezingen samen (§55)."""
    gelezen = []
    lezingen = {"nld+eng": ("DI ua islas ai el ga pl", 30.0), "ara+fas+eng": ("خبر کاذب", 90.0)}
    klok = iter([0.0, 0.1, 9.9, 9.9, 9.9])
    monkeypatch.setattr(ocr.time, "monotonic", lambda: next(klok))
    monkeypatch.setattr(pytesseract, "image_to_data", _data(lezingen, gelezen))
    _osd(monkeypatch, TWIJFEL)
    uitslag = ocr.extract_text(_wit(), _instellingen(schrift_zekerheid=3.0, schrift_ondergrens=1.5))
    assert gelezen == ["nld+eng"] and uitslag.text == "DI ua islas ai el ga pl"


def test_the_doubt_band_in_config_is_the_one_that_was_measured():
    """Aanzetten verandert wat de resolver op beelden antwoordt: een release
    (B22). Staat de band aan, dan met de waarden die §107 vooraf vastlegde en
    mat: ondergrens 1,5 en de helft van de letters in het herkende schrift."""
    instellingen = load_config().ocr
    if instellingen.schrift_ondergrens < instellingen.schrift_zekerheid:
        assert instellingen.schrift_ondergrens == 1.5
        assert instellingen.schrift_min_aandeel == 0.5


def test_the_script_share_of_a_second_reading_comes_from_config(tmp_path):
    """Drempels komen uit config, nooit uit code (DR6): ook het deel van de
    letters dat in het herkende schrift moet staan."""
    from doublecheck.config import _DEFAULT_PATH

    zonder = re.sub(r"(?m)^schrift_min_aandeel\s*=.*\n", "", _DEFAULT_PATH.read_text(encoding="utf-8"))
    tekst = zonder.replace("[ocr]\n", "[ocr]\nschrift_min_aandeel = 0.8\n", 1)
    eigen = tmp_path / "config.toml"
    eigen.write_text(tekst, encoding="utf-8")
    assert load_config(eigen).ocr.schrift_min_aandeel == 0.8


def test_a_measurement_can_turn_the_doubt_band_on_without_touching_config():
    """De ruwe test en de gemengde benchmark meten de regel met een eigen
    ondergrens (#25.22); de rest van de config blijft precies wat hij is."""
    from doublecheck.ruwetest import config_met_ondergrens

    basis = load_config()
    gemeten = config_met_ondergrens(1.5)
    assert gemeten.ocr.schrift_ondergrens == 1.5
    assert gemeten.ocr.languages == basis.ocr.languages and gemeten.thresholds == basis.thresholds
    assert load_config().ocr.schrift_ondergrens == basis.ocr.schrift_ondergrens


def test_a_second_reading_without_letters_of_the_detected_script_is_ignored(monkeypatch):
    """§107: de OSD zag Cyrillisch op een Engelse kop. Het Cyrillische pakket
    las hetzelfde Engels, half een punt zekerder, en dat tipte een grensgeval.
    Staan er geen letters van het herkende schrift in, dan was de herkenning
    fout en blijft de huidige lezing."""
    gelezen = []
    lezingen = {"nld+eng": ("the corrupt can't accomplish their goals", 95.0),
                "rus+mon+eng": ("the corrupt can’t accomplish their goals", 95.5)}
    monkeypatch.setattr(pytesseract, "image_to_data", _data(lezingen, gelezen))
    _osd(monkeypatch, "Script: Cyrillic\nScript confidence: 2.22\n")
    instellingen = _instellingen(schriften={"Cyrillic": "rus+mon+eng"}, schrift_zekerheid=3.0, schrift_ondergrens=1.5)
    uitslag = ocr.extract_text(_wit(), instellingen)
    assert gelezen == ["nld+eng", "rus+mon+eng"]
    assert uitslag.text == "the corrupt can't accomplish their goals"


@pytest.mark.parametrize("tekst, schrift, deel", [
    ("Москва не верит слезам", "Cyrillic", 1.0),
    ("Moscow does not believe", "Cyrillic", 0.0),
    ("خبر کاذب about vaccines", "Arabic", 7 / 20),
    ("中国 and 日本", "HanS", 4 / 7),
    ("ひらがな と 漢字", "Japanese", 1.0),
    ("தமிழ் செய்தி", "Tamil", 1.0),
])
def test_the_share_of_letters_in_the_detected_script(tekst, schrift, deel):
    assert ocr.aandeel_in_schrift(tekst, schrift) == pytest.approx(deel)
