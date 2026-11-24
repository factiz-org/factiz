"""De route zoals in het product, op echte screenshots (B43, PLAN #31.10): de
regels die vóór de eerste vraag aan het model vastlagen."""

import pytest

from doublecheck import routemeting as r


def test_the_ocr_decides_screenshot_or_photo_and_the_middle_is_left_out():
    assert r.soort_van("Bill Gates admits the vaccine contains a chip that tracks everyone who takes it") == "S"
    assert r.soort_van("") == "B" and r.soort_van("IMG 2041") == "B"
    assert r.soort_van("Breaking news from the capital today") is None   # tussen 15 en 60 letters


def test_a_stamp_or_a_fact_checker_in_the_image_text_gives_the_verdict_away():
    assert r.verraadt("FALSE\nThis photo shows the floods in Kerala")
    assert r.verraadt("Fake news alert! viral claim")
    assert r.verraadt("photo: factly.in")
    assert r.verraadt("FACT CHECK: the minister never said this")
    assert not r.verraadt("The minister said all schools close tomorrow, share widely")


def test_the_model_gets_the_masked_text_and_for_a_photo_the_caption_first():
    assert r.bericht("S-onwaar", "masked claim text", None) == "masked claim text"
    assert r.bericht("B-onwaar", "SALE 50%", "Floods in Kerala today") == \
        "Floods in Kerala today\n[Text in the attached image: SALE 50%]"
    assert r.bericht("B-paar", "", "Floods in Kerala today") == "Floods in Kerala today"


def test_fake_personal_data_is_fixed_by_seed_and_every_leak_is_found():
    pii = r.nep_pii(7)
    assert pii == r.nep_pii(7) and pii != r.nep_pii(8)
    schoon = r.lekken("Drinking hot water kills the virus. Call [telefoon]", pii)
    assert not any(schoon.values())
    lek = r.lekken(f"{pii['naam']} {pii['telefoon']} {pii['groep']}", pii)
    assert lek["naam"] and lek["telefoon"] and lek["groep"]


def test_p95_is_the_value_below_which_95_percent_fall():
    assert r.p95([float(i) for i in range(1, 101)]) == 95.0
    assert r.p95([3.0]) == 3.0


def _set():
    return [{"id": "so1", "deel": "S-onwaar", "label": "onwaar", "eigen": ["c1"]},
            {"id": "so2", "deel": "S-onwaar", "label": "onwaar", "eigen": ["c2"]},
            {"id": "sw1", "deel": "S-waar", "label": "waar", "eigen": []},
            {"id": "ss1", "deel": "S-stilte", "label": "geen bewering", "eigen": []}]


def test_a_false_message_counts_as_proven_by_its_own_check_and_anything_else_is_read():
    antwoorden = {"so1": {"oordeel": "klopt niet", "bronnen": [{"soort": "geheugen", "claim": "c1"}]},
                  "so2": {"oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "x"}]},
                  "sw1": {"oordeel": "klopt niet", "bronnen": [{"soort": "web", "url": "y"}]},
                  "ss1": {"oordeel": "geen bewering", "bronnen": []}}
    standen = {i: {"stand": 1} for i in antwoorden}
    with pytest.raises(r.Weigering):
        r.telling(_set(), antwoorden, standen, {("sw1", "klopt niet"): "vals"})
    t = r.telling(_set(), antwoorden, standen, {("so2", "klopt niet"): "bewijst", ("sw1", "klopt niet"): "vals"})
    assert t["S-onwaar"]["bewezen"] == 2
    assert t["S-waar"]["valse vlaggen"] == 1
    assert t["latten"]["ware berichten nooit klopt niet"] is False


def test_a_10_needs_a_label_and_a_wrong_10_breaks_the_bar():
    antwoorden = {"sw1": {"oordeel": "klopt", "bronnen": []}}
    standen = {"sw1": {"stand": 10, "feit": "earth-round"}}
    with pytest.raises(r.Weigering):
        r.telling(_set()[2:3], antwoorden, standen, {})
    t = r.telling(_set()[2:3], antwoorden, standen, {("sw1", 10, "earth-round"): "fout"})
    assert t["latten"]["geen verkeerde 10"] is False


def test_a_true_text_on_a_false_image_counts_apart_but_against_the_bar():
    stukken = [{"id": f"so{i}", "deel": "S-onwaar", "label": "onwaar", "eigen": []} for i in range(3)]
    antwoorden = {s["id"]: {"oordeel": "klopt", "bronnen": []} for s in stukken}
    labels = {("so0", "klopt"): "beeld nodig", ("so1", "klopt"): "beeld nodig", ("so2", "klopt"): "vals"}
    t = r.telling(stukken, antwoorden, {}, labels)
    assert t["S-onwaar"]["klopt, beeld nodig"] == 2 and t["S-onwaar"]["klopt vals"] == 1
    assert t["latten"]["S-onwaar bewezen ≥ 80%"] is False
