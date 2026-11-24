"""Tekst uit een screenshot halen (E1.S3).

De meeste desinformatie circuleert als beeld van tekst. Wat hier uit komt gaat
de gewone tekstroute in, zodat een screenshot van een gecheckte kop dezelfde
uitslag geeft als de kop zelf.

Levert de OCR te weinig leesbaars op, dan is `readable` False en valt de
resolver terug op alleen de beeld-fingerprint (AC2) — geen fout, geen lege
tekstzoekopdracht. De grens komt uit config, niet uit code (DR6).

De geëxtraheerde tekst is artefactinhoud: hij wordt nergens gelogd of bewaard
(DR3); logging staat op pakketniveau uit.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

import pytesseract

from doublecheck.config import OcrSettings
from doublecheck.image_fingerprint import as_image


@dataclass(frozen=True)
class OcrResult:
    text: str
    readable: bool


def _opschonen(ruw: str) -> str:
    return re.sub(r"[ \t]+", " ", ruw).strip()


_SCHRIFT = re.compile(r"Script:\s*(\S+)")
_ZEKERHEID = re.compile(r"Script confidence:\s*([\d.]+)")


# OSD-naam → het begin van de Unicode-naam van de tekens in dat schrift. Voor
# de meeste schriften is dat de OSD-naam zelf ("CYRILLIC", "TAMIL").
_UNICODENAMEN = {"HanS": ("CJK",), "HanT": ("CJK",), "Japanese": ("HIRAGANA", "KATAKANA", "CJK")}


def aandeel_in_schrift(tekst: str, schrift: str) -> float:
    """Welk deel van de letters (met combinerende tekens) in het schrift staat
    dat de OSD herkende (#25.22, §107)."""
    begin = _UNICODENAMEN.get(schrift, (schrift.upper(),))
    letters = [teken for teken in tekst if unicodedata.category(teken)[0] in "LM"]
    if not letters:
        return 0.0
    return sum(unicodedata.name(teken, "").startswith(begin) for teken in letters) / len(letters)


def _pakketten(afbeelding, settings: OcrSettings) -> tuple[str, tuple[str, str] | None]:
    """Welke pakketten dit beeld leest (#25.21), en bij twijfel een tweede
    lezing (#25.22).

    Eerst het schrift (Tesseract-OSD), dan het pakket uit de tabel. Een
    onzeker of onbekend schrift, Latijn, of een OSD die opgeeft (te weinig
    tekens, tijdgrens) houdt `languages`: zo wordt het nooit slechter dan
    zonder schriftherkenning. Ligt de zekerheid tussen `schrift_ondergrens`
    en `schrift_zekerheid`, dan komen het pakket en de naam van het schrift
    terug als tweede lezing; de eerste blijft `languages`."""
    if not settings.per_schrift or not settings.schriften:
        return settings.languages, None
    try:
        osd = pytesseract.image_to_osd(afbeelding, timeout=settings.timeout_seconds,
                                       config=f"-c min_characters_to_try={settings.schrift_min_tekens}")
    except (pytesseract.TesseractError, RuntimeError):
        return settings.languages, None
    schrift, zekerheid = _SCHRIFT.search(osd), _ZEKERHEID.search(osd)
    if not schrift or not zekerheid or schrift.group(1) not in settings.schriften:
        return settings.languages, None
    waarde = float(zekerheid.group(1))
    if waarde >= settings.schrift_zekerheid:
        return settings.schriften[schrift.group(1)], None
    ondergrens = settings.schrift_zekerheid if settings.schrift_ondergrens is None else settings.schrift_ondergrens
    if waarde >= ondergrens:
        return settings.languages, (settings.schriften[schrift.group(1)], schrift.group(1))
    return settings.languages, None


def _lees_met_zekerheid(afbeelding, pakketten: str, timeout: float) -> tuple[str, float]:
    """Tekst en de gemiddelde woordzekerheid van tesseract zelf (#25.22).
    Een lezing zonder woorden heeft zekerheid -1."""
    data = pytesseract.image_to_data(afbeelding, lang=pakketten, timeout=timeout,
                                     output_type=pytesseract.Output.DICT)
    regels: dict[tuple, list[str]] = {}
    zekerheden = []
    for i, woord in enumerate(data["text"]):
        if not str(woord).strip():
            continue
        regels.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(str(woord))
        zekerheid = float(data["conf"][i])
        if zekerheid >= 0:
            zekerheden.append(zekerheid)
    tekst = "\n".join(" ".join(woorden) for woorden in regels.values())
    return tekst, (sum(zekerheden) / len(zekerheden) if zekerheden else -1.0)


_MIN_LEESTIJD = 0.25   # seconden; minder is geen lezen maar wachten op een kill


def extract_text(bron, settings: OcrSettings) -> OcrResult:
    afbeelding = as_image(bron).convert("RGB")
    begin = time.monotonic()
    pakketten, tweede = _pakketten(afbeelding, settings)
    # Schriftherkenning en lezen delen één tijdgrens (§55): wat de OSD
    # gebruikte gaat van de leestijd af. Blijft er te weinig over om te lezen,
    # dan is het beeld onleesbaar; de grens gaat nooit over (eerder kreeg het
    # lezen minstens een seconde, en kon een beeld 11 van de 10 seconden kosten).
    rest = settings.timeout_seconds - (time.monotonic() - begin)
    if rest < _MIN_LEESTIJD:
        return OcrResult(text="", readable=False)
    try:
        if tweede is None:
            ruw = pytesseract.image_to_string(afbeelding, lang=pakketten, timeout=rest)
        else:
            # Twijfel over het schrift (#25.22): eerst de huidige lezing, dan
            # met de tijd die over is het schrift; de zekerste wint, bij
            # gelijkstand de huidige. Is de tijd op, dan blijft de huidige. En
            # staat de tweede lezing niet grotendeels in het herkende schrift,
            # dan was de herkenning fout (Cyrillisch op een Engelse kop, §107).
            tweede_pakket, schrift = tweede
            ruw, zekerheid = _lees_met_zekerheid(afbeelding, pakketten, rest)
            rest = settings.timeout_seconds - (time.monotonic() - begin)
            if rest >= _MIN_LEESTIJD:
                try:
                    ander, andere_zekerheid = _lees_met_zekerheid(afbeelding, tweede_pakket, rest)
                    if (andere_zekerheid > zekerheid
                            and aandeel_in_schrift(ander, schrift) >= settings.schrift_min_aandeel):
                        ruw = ander
                except RuntimeError:
                    pass
    except RuntimeError:
        # Tesseract overschreed de tijdgrens en is gekillt (#20.1), of choke op
        # dit specifieke beeld. Beide zijn per-verzoekfouten: behandel als
        # onleesbaar en val terug op de beeld-fingerprint, precies zoals bij te
        # weinig tekst. Er is geen tekst, dus niets om te lekken (DR3). Een
        # ontbrekende tesseract is een `TesseractNotFoundError` (EnvironmentError,
        # geen RuntimeError) en blijft dus luid — een kapotte machine mag niet
        # stilletjes elke aanvraag onleesbaar maken.
        return OcrResult(text="", readable=False)
    tekst = _opschonen(ruw)
    leesbaar = len(re.sub(r"\s", "", tekst)) >= settings.min_chars
    return OcrResult(text=tekst, readable=leesbaar)
