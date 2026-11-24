"""Schriftbewuste artefactvarianten (PLAN.md #11.2, E4.S1).

Aanleiding: de testsetbouwer was Latijns-schrift-gebonden en faalde *stil en
gunstig*. `.upper()` is een no-op in schriften zonder hoofdletters, dus het
"artefact" werd de claim zélf — Arabisch en Chinees scoorden mediaan 1,000
gelijkenis, wat geen prestatie is maar een tautologie. Chinees schrijft zonder
woordspaties, dus `_truncation_variant` telde één woord en sloeg over
(BENCHMARK.md §17a-b).

De eis is per constructie: élke gegenereerde variant moet verschillen van zijn
bron. Een variant die gelijk is aan de bron meet niets.
"""

import pytest

from doublecheck.testset import (
    _dressing_variant,
    _truncation_variant,
    _zonder_woordspaties,
)

# (schrift, voorbeeldclaim). Geen ontkenningen: die blokkeren de inkorting
# per ontwerp, en dat is hier niet wat we testen.
GESPATIEERD = [
    ("Latijn (nl)", "Het coronavaccin bevat microchips om mensen te volgen en te sturen"),
    ("Cyrillisch", "Вакцина содержит микрочипы для слежки за людьми и полного контроля"),
    ("Arabisch", "يحتوي اللقاح على شريحة إلكترونية لتتبع الناس والسيطرة عليهم تماما"),
    ("Devanagari", "कोरोना वायरस के टीके में लोगों को ट्रैक करने के लिए माइक्रोचिप लगी है"),
    ("Bengaals", "করোনা টিকায় মানুষকে ট্র্যাক করার জন্য মাইক্রোচিপ রয়েছে বলে দাবি করা হচ্ছে"),
]
ZONDER_SPATIES = [
    ("Han (zh)", "新冠疫苗含有微芯片用于追踪和控制人群的日常行动轨迹并上传数据"),
    ("Japans", "新型コロナワクチンには人々を追跡し行動を管理するためのマイクロチップが入っている"),
    ("Thai", "วัคซีนโควิดมีไมโครชิปสำหรับติดตามและควบคุมผู้คนในชีวิตประจำวัน"),
]
ALLE = GESPATIEERD + ZONDER_SPATIES


@pytest.mark.parametrize("schrift,tekst", ALLE)
def test_every_dressing_rotation_differs_from_its_source(schrift, tekst):
    """Geen enkele rotatie mag de bron teruggeven — anders meet dat paar niets."""
    for keuze in range(4):
        assert _dressing_variant(tekst, keuze) != tekst, f"{schrift}, rotatie {keuze}"


@pytest.mark.parametrize("schrift,tekst", ALLE)
def test_truncation_yields_a_real_shorter_prefix(schrift, tekst):
    variant = _truncation_variant(tekst)
    assert variant is not None, f"{schrift}: geen inkorting gebouwd"
    assert variant != tekst, f"{schrift}: inkorting gelijk aan bron"
    assert tekst.startswith(variant), f"{schrift}: inkorting is geen prefix"
    assert len(variant) < len(tekst), schrift


@pytest.mark.parametrize("schrift,tekst", GESPATIEERD)
def test_spaced_scripts_still_truncate_on_word_boundaries(schrift, tekst):
    """Waar spaties bestaan blijft het woordafkappen — geen halve woorden."""
    variant = _truncation_variant(tekst)
    assert variant in tekst
    assert tekst[len(variant): len(variant) + 1] in ("", " "), schrift


def test_negation_still_blocks_truncation_in_every_script():
    """Afkappen mag de betekenis niet omdraaien — die regel geldt onverkort."""
    assert _truncation_variant("Het vaccin bevat geen microchips om mensen te volgen") is None


def test_latin_behaviour_is_unchanged():
    """Regressie: run #10 mag niet bewegen op NL/DE/FR/EN."""
    tekst = "Het coronavaccin bevat microchips om mensen te volgen en te sturen"
    assert _dressing_variant(tekst, 0) == tekst.upper()
    assert _dressing_variant(tekst, 1) == f'"{tekst}"'
    assert _dressing_variant(tekst, 2) == f">>> {tekst} <<<"
    assert _dressing_variant(tekst, 3) == f"{tekst}!!!"
    assert _truncation_variant(tekst) == "Het coronavaccin bevat microchips om mensen"


@pytest.mark.parametrize(
    "tekst",
    [
        "Q10-suppletie verbetert sportprestaties.",
        "Corona-Impfstoffe enthalten Graphenoxid",
        "Covid-19-Impfstoffe machen unfruchtbar",
        "Moslimvluchtelingen trekken uitsluitend naar niet-moslimlanden.",
    ],
)
def test_compound_words_are_not_mistaken_for_a_spaceless_script(tekst):
    """Regressie op een eerdere, foute heuristiek.

    Gemiddelde tokenlengte als maat sneuvelde hierop: deze vier echte
    corpusclaims halen allemaal meer dan 12 tekens per token door hun
    samenstellingen, en zouden middenin een woord zijn afgekapt.
    """
    assert not _zonder_woordspaties(tekst)
    variant = _truncation_variant(tekst)
    assert variant is None or tekst[len(variant): len(variant) + 1] in ("", " ")


def test_all_caps_source_still_yields_a_different_artefact():
    """Twee Duitse corpusclaims staan volledig in kapitalen — daar was
    `.upper()` óók een no-op, dus de bug vuurde ook binnen ons eigen corpus."""
    tekst = "DEUTSCHER GEWINNT BEIM EU GERICHT: FINGERABDRUCK AUF PERSONALAUSWEIS"
    for keuze in range(4):
        assert _dressing_variant(tekst, keuze) != tekst


def test_short_latin_text_still_yields_no_truncation():
    """Te weinig materiaal blijft een overslag, geen halfwoord-afkapping."""
    assert _truncation_variant("Vaccins bevatten chips") is None
