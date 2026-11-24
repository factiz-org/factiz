"""De opmaak eruit (PLAN #32.22): de referentie per site, het eigen artikel, de telling en de eisen zoals vooraf."""

from pathlib import Path

import pytest

from doublecheck import opmaakmeting as om
from doublecheck import vindronde as vr

G, A, V = vr.GEVONDEN, vr.ANDERE, vr.VALS


def _b(artikel, beeld, deel=False):
    return {"artikel": artikel, "beeld": beeld, "deel": deel}


def test_the_reference_takes_at_most_80_articles_and_3_images_each_share_image_first_the_same_each_time():
    pool = [_b(f"https://leadstories.com/a/{i}", f"https://cdn.ls.com/{i}/{j}.jpg", deel=(j == 4))
            for i in range(120) for j in range(5)]
    pool += [_b("https://www.snopes.com/x/1", "https://media.snopes.com/1.jpg")]
    ref = om.referentie(pool)
    assert set(ref) == {"leadstories.com", "snopes.com"}
    assert len(ref["leadstories.com"]) == om.bv.OPMAAK_ARTIKELEN == 80
    assert all(len(b) <= om.bv.OPMAAK_BEELDEN == 3 for b in ref["leadstories.com"].values())
    assert all(b[0].endswith("/4.jpg") for b in ref["leadstories.com"].values()), "het deelbeeld eerst"
    assert ref == om.referentie(list(reversed(pool)))


def test_the_own_article_never_counts_as_another_article():
    ref = {"leadstories.com": {vr.adres(f"https://leadstories.com/a/{i}"): [f"b{i}"] for i in range(6)}}
    andere = om.andere_artikelen("https://leadstories.com/a/2/", ref)
    assert vr.adres("https://leadstories.com/a/2") not in andere and len(andere) == 5
    assert om.andere_artikelen("https://example.org/x", ref) == []


def _paar(set_="R3", vraag="q", beeld="b", punten=80, dekking=0.5, modus="productie"):
    return {"set": set_, "vraag": vraag, "beeld": beeld, "artikel": "art", "punten": punten, "dekking": dekking,
            "pdq": None, "uitgesloten": False, "groepen": {modus: ["e"]}, "via": {modus: ["tekst"]}}


def _vraag(set_="R3", id_="q"):
    return {"set": set_, "id": id_, "claim_id": "c", "eigen": {"productie": ["e"], "kopie": ["e"]}}


ROLLEN = {("art", "b"): "viraal", ("art", "b2"): "viraal"}


def test_a_pair_that_cannot_be_measured_is_neither_lost_nor_won():
    paren = [_paar()]
    na = om.na_regel(paren, {vr.labelsleutel(paren[0]): {"status": "niet te meten"}})
    assert na[0]["punten"] == 80 and na[0]["dekking"] == 0.5
    na = om.na_regel(paren, {vr.labelsleutel(paren[0]): {"status": "gemeten", "punten": 12, "dekking": 0.04}})
    assert vr.telling([_vraag()], na, {"R3|q|b": G}, ROLLEN, "productie")["R3"]["gevonden"] == 0


def test_counting_refuses_while_a_confirmation_the_rule_adds_has_no_label():
    paren = [_paar(punten=20, dekking=0.02)]
    na = om.na_regel(paren, {vr.labelsleutel(paren[0]): {"status": "gemeten", "punten": 90, "dekking": 0.4}})
    with pytest.raises(vr.Weigering):
        vr.telling([_vraag()], na, {}, ROLLEN, "productie")


def _t(**gevonden_vals):
    return {s: {"gevonden": g, "vals": v, "vragen": 100} for s, (g, v) in gevonden_vals.items()}


def test_the_requirements_as_written_in_advance():
    voor_p = _t(N=(27, 0), R3=(16, 9), W=(0, 0), S3=(0, 1))
    voor_k = _t(N=(27, 0), R3=(16, 9), R4=(68, 54), F=(40, 0), W=(0, 0), S3=(0, 1))
    na_p = _t(N=(25, 0), R3=(15, 1), W=(0, 0), S3=(0, 0))
    na_k = _t(N=(25, 0), R3=(15, 1), R4=(62, 1), F=(36, 0), W=(0, 0), S3=(0, 0))
    e = om.eisen(voor_p, voor_k, na_p, na_k, vragen=2393)
    assert e["gehaald"], e
    assert not om.eisen(voor_p, voor_k, na_p, {**na_k, "F": {"gevonden": 35, "vals": 0}}, vragen=2393)["2. behoud"]
    assert not om.eisen(voor_p, voor_k, na_p, {**na_k, "S3": {"gevonden": 0, "vals": 1}}, vragen=2393)["1. vals"]
    assert not om.eisen(voor_p, voor_k, na_p, {**na_k, "R4": {"gevonden": 62, "vals": 0},
                                                    "W": {"gevonden": 0, "vals": 1}}, vragen=2393)["1. vals"]


def test_ninety_percent_is_rounded_up_in_whole_claims():
    assert [om.behoud(n) for n in (27, 16, 68, 40, 0)] == [25, 15, 62, 36, 0]


def test_the_control_sample_is_the_same_each_time_and_holds_only_unconfirmed_pairs_with_30_points():
    paren = [_paar(vraag=f"q{i}", punten=p, dekking=0.01) for i, p in enumerate([10, 30, 40, 29, 300] * 300)]
    paren.append(_paar(vraag="z", punten=200, dekking=0.5))
    a = om.controle(paren, n=50)
    assert len(a) == 50 and a == om.controle(list(reversed(paren)), n=50)
    assert all(p["punten"] >= 30 and not vr.bb.bevestigd(p) for p in a)


def test_no_image_and_no_text_of_a_copy_ever_goes_to_disk(tmp_path: Path):
    with pytest.raises(ValueError):
        om.schrijf(tmp_path / "x.jsonl", [{"sleutel": "k", "beeld": b"\xff\xd8\xff"}])
    with pytest.raises(ValueError):
        om.schrijf(tmp_path / "x.jsonl", [{"sleutel": "k", "tekst": "wat erop stond"}])
    om.schrijf(tmp_path / "x.jsonl", [{"sleutel": "k", "punten": 3}])
    assert (tmp_path / "x.jsonl").read_text().count("\n") == 1


# --- de voormeting van de opmaak op haar vaste plek (#32.23) ---------------------------------------------------------

def test_the_pre_measurement_takes_false_pairs_lost_good_pairs_and_added_pairs_only():
    paren = [_paar(vraag="vals"), _paar(vraag="weg"), _paar(vraag="blijft"), _paar(vraag="erbij", punten=20),
             _paar(vraag="niets", punten=20)]
    labels = {"R3|vals|b": V, "R3|weg|b": G, "R3|blijft|b": G, "R3|erbij|b": G}
    v1 = {"R3|vals|b": {"status": "gemeten", "punten": 10, "dekking": 0.0},
          "R3|weg|b": {"status": "gemeten", "punten": 10, "dekking": 0.0},
          "R3|blijft|b": {"status": "gemeten", "punten": 90, "dekking": 0.5},
          "R3|erbij|b": {"status": "gemeten", "punten": 90, "dekking": 0.5}}
    gekozen = om.voormeting_paren(paren, labels, ROLLEN, v1)
    assert [p["vraag"] for p in gekozen] == ["erbij", "vals", "weg"]


def test_the_gates_of_the_pre_measurement_as_written_in_advance():
    na = _t(N=(25, 0), R3=(15, 1), R4=(66, 1), F=(39, 0), W=(0, 0))
    assert om.poorten(ls_weg=90, terug=39, na_p=na, na_k=na, vragen=2393)["volle ronde"]
    assert not om.poorten(ls_weg=89, terug=49, na_p=na, na_k=na, vragen=2393)["V1. Lead Stories"]
    assert not om.poorten(ls_weg=99, terug=38, na_p=na, na_k=na, vragen=2393)["V2. behoud"]
    weinig_n = {**na, "N": {"gevonden": 24, "vals": 0}}
    assert not om.poorten(ls_weg=99, terug=49, na_p=na, na_k=weinig_n, vragen=2393)["V2. behoud"]
    te_veel = {**na, "S3": {"gevonden": 0, "vals": 1}}
    g = om.poorten(ls_weg=99, terug=49, na_p=na, na_k=te_veel, vragen=2393)
    assert not g["V3. vals"] and not g["volle ronde"]


# --- de rest van de foto (#32.24) ------------------------------------------------------------------------------------

def test_the_rest_pre_measurement_takes_the_163_and_every_other_good_confirmation():
    paren = [_paar(vraag="vals"), _paar(vraag="goed"), _paar(vraag="weg"), _paar(vraag="ander"),
             _paar(vraag="niets", punten=20)]
    labels = {"R3|vals|b": V, "R3|goed|b": G, "R3|weg|b": G, "R3|ander|b": A}
    v1 = {"R3|weg|b": {"status": "gemeten", "punten": 10, "dekking": 0.0}}
    assert [p["vraag"] for p in om.rest_paren(paren, labels, ROLLEN, v1)] == ["goed", "vals", "weg"]


def test_a_failed_rest_check_takes_the_confirmation_away_and_pdq_is_never_checked():
    paren = [_paar(vraag="a"), _paar(vraag="b"), dict(_paar(vraag="c"), pdq=12)]
    uit = {"R3|a|b": {"status": "gemeten", "punten": 90, "dekking": 0.5, "rest": False},
           "R3|b|b": {"status": "gemeten", "punten": 90, "dekking": 0.5, "rest": True},
           "R3|c|b": {"status": "gemeten", "punten": 90, "dekking": 0.5, "rest": "pdq"}}
    na = {p["vraag"]: p for p in om.na_rest(paren, uit)}
    assert not vr.bb.bevestigd(na["a"]) and vr.bb.bevestigd(na["b"]) and vr.bb.bevestigd(na["c"])


def test_the_gates_of_the_rest_check_as_written_in_advance():
    voor = _t(N=(27, 0), R3=(16, 9), R4=(68, 54), F=(40, 0), W=(0, 0))
    na = _t(N=(25, 0), R3=(15, 1), R4=(62, 1), F=(36, 0), W=(0, 0))
    assert om.restpoorten(voor, voor, na, na, vragen=2393)["volle ronde"]
    assert not om.restpoorten(voor, voor, na, {**na, "R4": {"gevonden": 61, "vals": 1}}, vragen=2393)["R2. behoud"]
    assert not om.restpoorten(voor, voor, na, {**na, "S3": {"gevonden": 0, "vals": 1}}, vragen=2393)["R1. vals"]
