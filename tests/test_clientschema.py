"""Haalbaarheid van een clientschema voor tekst (PLAN #24.2b, PROTOCOL §4).

De meting zelf draait het model en hoort niet in de suite; hier staan de
rekenstukken waar de conclusie op rust: wanneer telt iets als een gesprongen
beslissing, hoe groot is de kwantiseringsfout, en vindt de herleiding van de
artefacten voor elke testsetsoort de juiste kandidaten.
"""

import numpy as np

from doublecheck import clientschema as cs


def test_band_respects_each_threshold():
    assert cs.band(0.95, 0.92, 0.80) == "matched"
    assert cs.band(0.92, 0.92, 0.80) == "matched"
    assert cs.band(0.919, 0.92, 0.80) == "related"
    assert cs.band(0.80, 0.92, 0.80) == "related"
    assert cs.band(0.799, 0.92, 0.80) == "none"


def test_flips_are_counted_per_kind_and_direction():
    rijen = [
        cs.Meting("vervorming", True, 0.93, 0.91, 0.92, 0.80),   # matched -> related
        cs.Meting("ontkenning", False, 0.90, 0.93, 0.92, 0.80),  # related -> matched
        cs.Meting("origineel", True, 1.0, 0.999, 0.92, 0.80),    # geen wissel
    ]
    rapport = cs.wissels(rijen)
    assert rapport["totaal"] == 1 + 1
    assert rapport["per_soort"] == {"vervorming": 1, "ontkenning": 1}
    # Een niet-zelfde paar dat naar matched springt is een nieuwe fout, het
    # zwaarste soort wissel.
    assert rapport["nieuwe_fouten"] == 1
    assert rapport["verloren_dekking"] == 1


def test_row_quantisation_error_stays_within_half_a_step():
    rng = np.random.default_rng(3)
    m = rng.normal(size=(50, 384)).astype(np.float32)
    m[7] = 0.0
    q = cs.kwantiseer_rijen(m)
    stap = np.abs(m).max(axis=1, keepdims=True) / 127.0
    assert np.all(np.abs(q - m) <= stap / 2 + 1e-7)
    assert np.all(q[7] == 0.0)


def test_candidates_cover_every_testset_kind():
    tekst = "De regering verhoogt de btw op boodschappen volgend jaar naar 25 procent"
    buren = {"gfc-buur": "Een heel andere bewering over iets anders"}
    vertalingen = {"gfc-a": ["The government raises VAT on groceries next year"]}
    assert cs.kandidaten("origineel", "gfc-a", tekst, "nl", buren, vertalingen) == [tekst]
    vormen = cs.kandidaten("vervorming", "gfc-a", tekst, "nl", buren, vertalingen)
    assert len(vormen) == 4 and tekst.upper() in vormen
    assert cs.kandidaten("hardste-buur:gfc-buur", "gfc-a", tekst, "nl", buren, vertalingen) == [
        buren["gfc-buur"]
    ]
    assert cs.kandidaten("vertaling", "gfc-a", tekst, "nl", buren, vertalingen) == vertalingen["gfc-a"]
    assert cs.kandidaten("inkorting", "gfc-a", tekst, "nl", buren, vertalingen)
    assert cs.kandidaten("cijferwissel", "gfc-a", tekst, "nl", buren, vertalingen)
    assert cs.kandidaten("onbekende-soort", "gfc-a", tekst, "nl", buren, vertalingen) == []


def test_tradeoff_finds_the_best_threshold_at_equal_or_fewer_errors():
    """Een eigen schema krijgt een eigen drempel (§4): de vraag is welke
    dekking het haalt bij hooguit evenveel fouten als het referentieschema."""
    sims = np.array([0.99, 0.95, 0.91, 0.90, 0.89, 0.93, 0.85])
    zelfde = np.array([True, True, True, True, False, False, False])
    fouten, dekking = cs.afruil(sims, zelfde, 0.92)
    assert (fouten, dekking) == (1, 2)
    assert cs.beste_drempel(sims, zelfde, max_fouten=0) == (0.95, 0, 2)
    assert cs.beste_drempel(sims, zelfde, max_fouten=1) == (0.90, 1, 4)
    # Bij gelijke dekking wint de strengere drempel: 0,89 haalt ook dekking 4,
    # maar met een fout meer.
    assert cs.beste_drempel(sims, zelfde, max_fouten=2) == (0.90, 1, 4)
