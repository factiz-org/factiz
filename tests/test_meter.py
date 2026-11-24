"""De waarheidsmeter (B44, PLAN #31.9): de regels die vóór de ijking vastlagen."""

from doublecheck import meter


def test_the_layer_of_an_answer_is_the_strongest_source_it_cites():
    assert meter.laag_van_antwoord([{"soort": "web"}, {"soort": "geheugen"}]) == "redactie"
    assert meter.laag_van_antwoord([{"soort": "web"}]) == "web"
    assert meter.laag_van_antwoord([{"soort": "beeld"}]) == "web"
    assert meter.laag_van_antwoord([]) == "geen bron"


def test_a_class_reaches_the_ends_only_when_its_interval_does_and_only_with_a_check_of_an_editor():
    assert meter.stand(3, 151, "redactie", "klopt niet") == 1   # 2% waar, bovengrens ~6%
    assert meter.stand(292, 293, "redactie", "klopt") == 9
    assert meter.stand(10, 158, "web", "klopt niet") == 3       # bovengrens ~11%: niet de uiterste stand
    assert meter.stand(314, 331, "web", "klopt") == 7           # zonder check van een redactie hoogstens 7
    assert meter.stand(0, 300, "web", "klopt niet") == 3


def test_small_or_mixed_classes_stay_in_the_middle_because_doubt_never_loosens():
    assert meter.stand(0, 17, "web", "klopt niet") == 5         # te weinig om iets te zeggen
    assert meter.stand(25, 50, "redactie", "klopt") == 5


def test_the_meter_never_points_against_the_verdict():
    # 67% van de 'onzeker' bleek waar, maar alleen omdat de meetset vooral ware stukken had.
    assert meter.stand(82, 123, "web", "onzeker") == 5
    assert meter.stand(300, 300, "redactie", "klopt niet") == 5
    assert meter.stand(0, 300, "redactie", "klopt") == 5


def test_a_measured_stand_never_shows_0_or_10_and_always_names_its_layer():
    tabel = meter.ijktabel([("klopt niet", "redactie", "onwaar")] * 150 + [("klopt", "web", "waar")] * 40)
    for oordeel, laag in (("klopt niet", "redactie"), ("klopt", "web"), ("let op", "web"), ("onzeker", "geen bron")):
        m = meter.meterstand(tabel, oordeel, laag)
        assert m["stand"] in (1, 3, 5, 7, 9) and m["laag"] == laag and m["woorden"] == meter.STANDEN[m["stand"]]
    assert meter.meterstand(tabel, "let op", "web")["stand"] == 5  # een klasse zonder ijking: het midden
    assert meter.meterstand(tabel, "klopt niet", "redactie")["stand"] == 1


# Aangepast voorstel B44 (PO 2026-10-26): 0 en 10 voor de feitenbasis, 9 zonder factcheck per soort bewering.

def test_only_a_fact_from_the_fact_base_reaches_0_or_10_and_always_in_words():
    tabel = meter.ijktabel([("klopt", "redactie", "waar")] * 300)
    assert meter.meterstand(tabel, "klopt", "redactie")["stand"] == 9          # gemeten: nooit 10
    feit = meter.meterstand(tabel, "klopt", "web", feit="waar")
    assert feit["stand"] == 10 and feit["woorden"] == "vastgesteld feit" and feit["laag"] == "feitenbasis"
    assert meter.stand(300, 300, "redactie", "klopt") == 9 and meter.stand(0, 300, "redactie", "klopt niet") == 1


# PO 2026-10-26, na feitstap-v3 (§154): "stand 10 gaat open voor de 40 kernfeiten [...] en stand 0 blijft dicht."

def test_stand_0_stays_closed_and_a_contradicted_fact_gets_the_measured_stand(monkeypatch):
    tabel = meter.ijktabel([("klopt niet", "redactie", "onwaar")] * 300)
    assert meter.OPEN_UITEINDEN == frozenset({10})
    tegen = meter.meterstand(tabel, "klopt niet", "redactie", feit="onwaar")
    assert tegen["stand"] == 1 and tegen["laag"] == "redactie"                 # de gemeten stand, nooit 0
    assert meter.meterstand(tabel, "onzeker", "geen", feit="onwaar")["stand"] == 5
    assert meter.meterstand(tabel, "klopt", "web", feit="waar")["stand"] == 10
    monkeypatch.setattr(meter, "OPEN_UITEINDEN", frozenset({0, 10}))
    tegen = meter.meterstand(tabel, "klopt niet", "web", feit="onwaar")
    assert tegen["stand"] == 0 and tegen["woorden"] == "in strijd met een vastgesteld feit"


def test_a_kind_of_claim_reaches_1_and_9_without_a_fact_check_only_once_the_calibration_round_frees_it(monkeypatch):
    assert meter.VRIJE_SOORTEN == frozenset()                                   # leeg tot de ijkronde
    assert meter.stand(314, 331, "web", "klopt", soort="vaststaande kennis") == 7
    monkeypatch.setattr(meter, "VRIJE_SOORTEN", frozenset({"vaststaande kennis"}))
    assert meter.stand(314, 331, "web", "klopt", soort="vaststaande kennis") == 9
    assert meter.stand(314, 331, "web", "klopt", soort="beeld in context") == 7
