"""Oordeellabels buiten het Engels (PLAN.md #18.1).

53% van het corpus kwam terug als `onbekend` omdat de tabel alleen Nederlands
en Engels kende — tien talen stonden op ~100% onbekend, waaronder Portugees
(7.864 checks) en Duits (4.147).

Twee dingen bewaken deze tests, en ze trekken tegengesteld.

**Dekking mag groeien.** Een leeg genormaliseerd veld maakt DR7 onbruikbaar:
"weerlegd door 14 factcheckers" leunt erop.

**Maar nooit door te raden.** Een verkeerd label geeft het oordeel van een
uitgever verkeerd weer, en dat is erger dan geen label (DR1). Daarom: exacte
matches, geen nieuwe categorieën, en elke vertaalde regel draagt haar taal en
een letterlijke glos zodat een moedertaalspreker haar kan nakijken.
"""

import pytest

from doublecheck.verdicts import (
    NORMALIZED_CATEGORIES,
    VERTAALDE_LABELS,
    normalize_verdict,
)

VASTGELEGDE_CATEGORIEEN = (
    "waar", "deels-waar", "misleidend", "onwaar", "onbewezen", "satire", "onbekend",
)


def test_no_new_normalised_category_was_invented():
    """Meer talen mag; een nieuwe uitspraakvorm niet (DR2, B10)."""
    assert NORMALIZED_CATEGORIES == VASTGELEGDE_CATEGORIEEN


def test_every_translated_label_is_auditable():
    """Wie de tabel niet kan nakijken, moet hem geloven — en dat is precies
    wat dit project van resolvers weigert te vragen."""
    for label, (categorie, taal, glos) in VERTAALDE_LABELS.items():
        assert categorie in VASTGELEGDE_CATEGORIEEN, label
        assert taal and len(taal) == 2, f"{label}: taal ontbreekt of is geen ISO-code"
        assert glos and glos.strip(), f"{label}: geen letterlijke glos"
        if taal != "nl":
            # Nederlandse labels zijn niet vertaald; daar valt niets na te
            # kijken. Bij elke andere taal moet de glos iets toevoegen.
            assert glos != label, f"{label}: de glos herhaalt het label"


@pytest.mark.parametrize(
    "label,verwacht",
    [
        ("Falso", "onwaar"),            # pt/es, samen 10.151 checks
        ("FALSO", "onwaar"),            # kapitalisatie doet er niet toe
        ("Verdadeiro", "waar"),
        ("Engañoso", "misleidend"),
        ("Falsch", "onwaar"),
        ("Faux", "onwaar"),
        ("Fałsz", "onwaar"),
        ("Yanlış", "onwaar"),
        ("Yanlış ", "onwaar"),          # spatie aan het eind, komt echt zo voor
        ("Keliru", "onwaar"),
        ("Hindi totoo", "onwaar"),
        ("نادرست", "onwaar"),
        ("مضلل", "misleidend"),
        ("不實", "onwaar"),
        ("誤り", "onwaar"),
        ("לא נכון", "onwaar"),
        ("भ्रामक", "misleidend"),
        ("Фейк", "onwaar"),
        ("Altered", "onwaar"),
        ("Needs context", "misleidend"),
        ("Four Pinocchios", "onwaar"),
        ("Partly False", "deels-waar"),
        ("Fact Crescendo Rating: False", "onwaar"),   # dubbele punt blijft staan
        ("Fact Crescendo Rating FALSE", "onwaar"),
    ],
)
def test_labels_from_the_real_corpus_are_recognised(label, verwacht):
    assert normalize_verdict(label) == verwacht


@pytest.mark.parametrize(
    "label",
    [
        "not true",                  # bevat "true"; substringmatchen zou raden
        "Falsomente",                # bevat "falso"
        "no es falso",               # ontkenning van een gemapt label
        "5",                         # kale schaalwaarde zonder legenda
        "شاخ‌دار",                    # eigenzinnig label van één uitgever
        "Das angebliche Gewinnspiel",  # een zin, geen oordeel
        "True. However, its link to infertility remains uncertain",
    ],
)
def test_ambiguous_or_unknown_labels_stay_unknown(label):
    """Twijfel versoepelt nooit: liever geen oordeel dan het verkeerde."""
    assert normalize_verdict(label) == "onbekend"


@pytest.mark.parametrize(
    "label",
    [
        "Sátira",           # SBT News, Folha, Metrópoles, Comprova: 16
        "Netočno, Satira",  # Du-Check: "onjuist, satire"
        "Labeled Satire", "Originated as Satire", "Satire", "Satirisch",
    ],
)
def test_satire_labels_count_as_false_until_it_is_clear_it_was_meant_as_a_joke(label):
    """B56 (PO 2026-11-04): als nieuws klopt het niet, en een site die zich satire noemt maar hoaxes maakt, is geen
    satire. Een label zegt niet welke van de twee het is, dus onwaar; geen onbekend, want dan verdween het oordeel uit
    beeld (#25.24)."""
    assert normalize_verdict(label) == "onwaar"
