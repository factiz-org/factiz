"""De vindronde (PLAN #32.21): de eigen check vinden met vier sleutels, de rol van elk beeld en een meetkopie."""

from pathlib import Path

import numpy as np
import pytest

from doublecheck import vindronde as vr

G, A, V = vr.GEVONDEN, vr.ANDERE, vr.VALS


# --- de sets ---------------------------------------------------------------------------------

def _ra(i, taal="en", bewering="Photo shows a flood in Kathmandu", site="leadstories.com"):
    return {"adres": f"https://{site}/a/{i}", "bewering": bewering, "taal": taal, "oordeel": "False",
            "datum": "2026-10-10", "uitgever": "X", "site": "X"}


def test_r4_takes_english_image_claims_from_route_a_the_same_each_time():
    checks = [_ra(i) for i in range(150)] + [_ra(900, taal="es"), _ra(901, bewering="Taxes went up in 2025")]
    a = vr.r4_keuze(checks, n=100)
    assert len(a) == 100 and a == vr.r4_keuze(list(reversed(checks)), n=100)
    assert all(c["taal"] == "en" and "flood" in c["bewering"] for c in a)


def test_f_takes_only_images_whose_check_is_only_in_factors():
    m4fc = [{"article_url": f"https://snopes.com/fact-check/{i}/", "fc_language": "english"} for i in range(10)]
    bekend = {vr.adres("https://snopes.com/fact-check/0/")}
    factors = {vr.adres(f"https://snopes.com/fact-check/{i}/"): "Snopes" for i in range(8)}
    keuze = vr.f_keuze(m4fc, bekend, factors, gebruikt={1}, n=100)
    assert keuze == [2, 3, 4, 5, 6, 7]


# --- de meetkopie ---------------------------------------------------------------------------------

def test_the_copy_refuses_the_production_database(tmp_path):
    prod = tmp_path / "doublecheck.db"
    with pytest.raises(vr.Weigering):
        vr.controleer_kopie(prod, prod)
    vr.controleer_kopie(tmp_path / "kopie.db", prod)


def test_new_checks_skip_what_the_database_has_and_get_a_stable_id():
    factors = [{"url": "https://snopes.com/fact-check/a/", "claim": "Photo shows a shark on a highway.",
                "organisation": "Snopes", "original_verdict": "False", "date_published": "2024-01-02T00:00:00"},
               {"url": "https://factly.in/x/", "claim": "Known", "organisation": "FACTLY", "original_verdict": "False",
                "date_published": "2024-01-02T00:00:00"}]
    nieuw = vr.nieuwe_checks(factors, [_ra(1)], bekend={vr.adres("https://factly.in/x/")})
    assert [c["bron"] for c in nieuw] == ["FACTors", "route A"]
    assert nieuw[0]["claim_id"].startswith("fac-") and nieuw[1]["claim_id"].startswith("ra-")
    assert nieuw == vr.nieuwe_checks(factors, [_ra(1)], bekend={vr.adres("https://factly.in/x/")})
    assert nieuw[0]["taal"] == "en" and nieuw[0]["datum"] == "2024-01-02"


# --- sleutel 3 en 4: alleen virale beelden ------------------------------------------------------------

def test_the_image_keys_search_only_viral_images():
    items = [{"artikel": "a1", "beeld": "b1", "tekst": "x"}, {"artikel": "a1", "beeld": "b2", "tekst": "y"},
             {"artikel": "a2", "beeld": "b3", "tekst": "z"}]
    rollen = {("a1", "b1"): "viraal", ("a1", "b2"): "bewijs", ("a2", "b3"): "onbekend"}
    assert [i["beeld"] for i in vr.virale(items, rollen)] == ["b1"]


def test_the_image_text_key_keeps_every_claim_and_its_queries():
    gehaald = [{"bewering": "A shark swims on a highway", "zoekvragen": ["shark highway flood", "shark highway"]},
               {"bewering": "Flood in Houston", "zoekvragen": []}]
    assert vr.extra_zoekvragen(gehaald) == ["A shark swims on a highway", "shark highway flood", "shark highway",
                                            "Flood in Houston"]
    assert vr.extra_zoekvragen([]) == []


def test_the_best_articles_rank_by_their_best_image_and_respect_the_mode():
    scores = np.array([0.2, 0.9, 0.5, 0.8])
    artikelen = ["a1", "a2", "a1", "a3"]
    assert vr.beste_artikelen(scores, artikelen, n=2) == [("a2", 0.9), ("a3", 0.8)]
    assert vr.beste_artikelen(scores, artikelen, n=5, toegestaan={"a1", "a3"}) == [("a3", 0.8), ("a1", 0.5)]


# --- tellen ---------------------------------------------------------------------------------------------

def _paar(set_="R3", vraag="q", beeld="b", artikel="art", punten=80, uitgesloten=False, groepen=("e",),
          modus="productie"):
    return {"set": set_, "vraag": vraag, "beeld": beeld, "artikel": artikel, "punten": punten, "dekking": 0.5,
            "pdq": None, "uitgesloten": uitgesloten, "groepen": {modus: list(groepen)}, "via": {modus: ["tekst"]}}


def _vraag(set_="R3", id_="q", claim="c", eigen=("e",)):
    return {"set": set_, "id": id_, "claim_id": claim, "eigen": {"productie": list(eigen), "kopie": list(eigen)}}


def test_a_confirmation_on_an_image_that_is_not_viral_never_counts_as_found():
    labels = {"R3|q|b": G}
    for rol, verwacht in (("viraal", 1), ("origineel", 0), ("bewijs", 0), ("huisstijl", 0), ("onbekend", 0)):
        t = vr.telling([_vraag()], [_paar()], labels, {("art", "b"): rol}, "productie")
        assert t["R3"]["gevonden"] == verwacht


def test_the_query_itself_in_the_article_never_counts():
    t = vr.telling([_vraag("N", claim=None)], [_paar("N", uitgesloten=True)], {"N|q|b": G}, {("art", "b"): "viraal"},
                   "productie")
    assert t["N"]["gevonden"] == 0


def test_a_check_only_in_the_copy_is_not_found_in_production():
    paar = _paar("R4", groepen=("ra-1",), modus="kopie")
    vraag = {"set": "R4", "id": "q", "claim_id": "ra-1", "eigen": {"productie": [], "kopie": ["ra-1"]}}
    rollen, labels = {("art", "b"): "viraal"}, {"R4|q|b": G}
    assert vr.telling([vraag], [paar], labels, rollen, "kopie")["R4"]["gevonden"] == 1
    assert vr.telling([vraag], [paar], labels, rollen, "productie")["R4"]["gevonden"] == 0


def test_counting_refuses_while_a_confirmation_that_counts_has_no_label():
    with pytest.raises(vr.Weigering):
        vr.telling([_vraag()], [_paar()], {}, {("art", "b"): "viraal"}, "productie")
    # een bevestiging op een beeld dat niet viraal is, hoeft geen label
    vr.telling([_vraag()], [_paar()], {}, {("art", "b"): "bewijs"}, "productie")


def test_false_confirmations_count_per_query():
    paren = [_paar(beeld="b1", groepen=("x",)), _paar(beeld="b2", groepen=("y",))]
    rollen = {("art", "b1"): "viraal", ("art", "b2"): "viraal"}
    t = vr.telling([_vraag()], paren, {"R3|q|b1": V, "R3|q|b2": V}, rollen, "productie")
    assert t["R3"]["vals"] == 1 and t["R3"]["vals paren"] == 2


def test_the_requirements_as_written_in_advance():
    t = {"R3": {"gevonden": 30, "vals": 0, "vragen": 260}, "N": {"gevonden": 29, "vals": 0, "vragen": 58},
         "W": {"gevonden": 0, "vals": 0, "vragen": 60}, "S3": {"gevonden": 0, "vals": 1, "vragen": 1450}}
    k = {"R4": {"gevonden": 30, "vals": 0, "vragen": 300}, "F": {"gevonden": 30, "vals": 0, "vragen": 120},
         **{s: dict(v) for s, v in t.items()}}
    rol = {"viraal precisie": 0.95, "viraal recall": 0.85}
    e = vr.eisen(t, k, rol, po_verschillen=1)
    assert e["gehaald"]
    k["W"]["vals"] = 1
    assert not vr.eisen(t, k, rol, po_verschillen=1)["4. vals"]
    assert not vr.eisen(t, k, {"viraal precisie": 0.94, "viraal recall": 0.9}, po_verschillen=0)["5. de rol"]


def test_the_role_count_gives_precision_and_recall_of_viral():
    gelezen = {"1": "viraal", "2": "viraal", "3": "bewijs", "4": "origineel"}
    voorspeld = {"1": "viraal", "2": "onbekend", "3": "viraal", "4": "origineel"}
    r = vr.rol_telling(gelezen, voorspeld)
    assert r["viraal precisie"] == 0.5 and r["viraal recall"] == 0.5 and r["gelezen"] == 4


def test_the_text_of_a_copy_never_goes_to_disk(tmp_path: Path):
    with pytest.raises(ValueError):
        vr.schrijf_vraag(tmp_path / "v.jsonl", {"set": "R3", "id": "q", "tekst": "wat erop stond"})
    with pytest.raises(ValueError):
        vr.schrijf_vraag(tmp_path / "v.jsonl", {"set": "R3", "id": "q", "beeld": b"\xff\xd8"})
    vr.schrijf_vraag(tmp_path / "v.jsonl", {"set": "R3", "id": "q", "tekens": 41})
    assert (tmp_path / "v.jsonl").read_text().count("\n") == 1


def test_the_po_sample_is_the_same_each_time_whatever_the_order():
    sleutels = [f"R4|q{i}|b" for i in range(80)]
    keuze = vr.po_keuze(sleutels)
    assert len(keuze) == vr.PO_N == len(set(keuze))
    assert keuze == vr.po_keuze(list(reversed(sleutels)) + sleutels[:5])
    assert vr.po_keuze(sleutels[:7]) == sorted(sleutels[:7])


def test_po_differences_refuse_until_the_po_has_read_every_one():
    mijn = {"a": G, "b": V, "c": G}
    with pytest.raises(vr.Weigering):
        vr.po_verschillen(mijn, {"a": G, "b": V}, ["a", "b", "c"])
    assert vr.po_verschillen(mijn, {"a": G, "b": G, "c": G}, ["a", "b", "c"]) == 1


def test_the_role_count_is_also_given_apart_for_share_images():
    gelezen = {"a|deel": "viraal", "a|b2": "bewijs", "b|deel": "huisstijl", "b|b2": "viraal"}
    voorspeld = {"a|deel": "viraal", "a|b2": "viraal", "b|deel": "huisstijl", "b|b2": "onbekend"}
    r = vr.rol_per_soort(gelezen, voorspeld, {"a|deel", "b|deel"})
    assert r["deelbeelden"]["gelezen"] == 2 and r["deelbeelden"]["viraal precisie"] == 1.0
    assert r["andere beelden"]["viraal precisie"] == 0.0 and r["andere beelden"]["viraal recall"] == 0.0


# --- de rol van het beeld, de voormeting (#32.25) ----------------------------------------------------------------------

def test_the_role_pre_measurement_takes_confirming_images_that_are_not_called_viral():
    vragen = [_vraag(id_="q1"), _vraag(id_="q2"), _vraag("N", id_="n1"), _vraag("R4", id_="r4")]
    paren = [_paar(vraag="q1", beeld="b1"), _paar(vraag="q1", beeld="b2", punten=10),
             _paar(vraag="q2", beeld="b3"), _paar("N", vraag="n1", beeld="b4"), _paar("N", vraag="n1", beeld="b5",
                                                                                     uitgesloten=True),
             _paar("R4", vraag="r4", beeld="b6"), _paar(vraag="q1", beeld="b7", groepen=("ander",))]
    rollen = {("art", "b1"): "bewijs", ("art", "b2"): "onbekend", ("art", "b3"): "viraal", ("art", "b4"): "onbekend",
              ("art", "b5"): "bewijs", ("art", "b6"): "bewijs", ("art", "b7"): "bewijs"}
    gekozen = vr.rol_voormeting_beelden(vragen, paren, rollen)
    # b2 bevestigt niet, b3 telt al (q2 is gevonden), b5 is de vraag zelf, b6 is van R4, b7 is niet de eigen check
    assert [(b["artikel"], b["beeld"]) for b in gekozen] == [("art", "b1"), ("art", "b4")]
    assert gekozen[0]["paren"] == ["R3|q1|b1"]


def test_a_read_role_replaces_the_role_from_haiku_and_then_needs_a_pair_label():
    rollen = {("art", "b"): "bewijs", ("art", "c"): "onbekend"}
    nieuw = vr.met_gelezen_rollen(rollen, {"art|b": "viraal"})
    assert nieuw == {("art", "b"): "viraal", ("art", "c"): "onbekend"} and rollen[("art", "b")] == "bewijs"
    with pytest.raises(vr.Weigering):
        vr.telling([_vraag()], [_paar()], {}, nieuw, "productie")
    assert vr.telling([_vraag()], [_paar()], {"R3|q|b": G}, nieuw, "productie")["R3"]["gevonden"] == 1


def test_the_two_conditions_for_the_role_round_as_written_in_advance():
    rollen = ["viraal"] * 21 + ["bewijs"] * 21
    assert vr.rol_voorwaarden(rollen, n_gevonden=31, r3_gevonden=16)["ronde"]
    assert vr.rol_voorwaarden(rollen, n_gevonden=27, r3_gevonden=22)["ronde"]
    assert not vr.rol_voorwaarden(rollen, n_gevonden=30, r3_gevonden=21)["ronde"]
    assert not vr.rol_voorwaarden(["viraal"] * 20 + ["bewijs"] * 22, n_gevonden=40, r3_gevonden=30)["ronde"]


# --- de rolronde, rol-v3 (#32.26) ---------------------------------------------------------------------------------

def test_the_role_round_asks_every_article_with_a_confirmation_or_a_read_image():
    paren = [_paar(beeld="b1"), _paar(beeld="b2", punten=10), dict(_paar(beeld="b3"), artikel="ander"),
             _paar(beeld="b4", uitgesloten=True)]
    paren[2]["artikel"] = "art2"
    gekozen = vr.rolronde_artikelen(paren, gelezen=["art3|x", "art|y"])
    assert gekozen == ["art", "art2", "art3"]
    assert vr.rolronde_artikelen([_paar(beeld="b2", punten=10)], gelezen=[]) == []


def _rt(**gevonden_vals):
    return {s: {"gevonden": g, "vals": v, "vragen": 100} for s, (g, v) in gevonden_vals.items()}


def test_the_requirements_of_the_role_round_as_written_in_advance():
    lees125 = {f"a|{i}": "viraal" for i in range(40)} | {f"a|n{i}": "bewijs" for i in range(60)}
    v3_125 = {f"a|{i}": "viraal" for i in range(34)} | {f"a|n{i}": "bewijs" for i in range(60)}
    lees42 = {f"b|{i}": "viraal" for i in range(20)} | {f"b|o{i}": "origineel" for i in range(22)}
    v3_42 = {f"b|{i}": "viraal" for i in range(17)} | {f"b|o{i}": "origineel" for i in range(21)} | {"b|o21": "viraal"}
    voor_p, voor_k = _rt(N=(27, 0), R3=(16, 9), W=(0, 0)), _rt(N=(27, 0), R3=(16, 9), R4=(68, 54), F=(40, 0), W=(0, 0))
    na_p, na_k = _rt(N=(31, 0), R3=(22, 9), W=(0, 0)), _rt(N=(31, 0), R3=(22, 9), R4=(62, 54), F=(36, 0), W=(0, 0))
    e = vr.rolronde_eisen(lees125, v3_125, lees42, v3_42, voor_p, voor_k, na_p, na_k)
    assert e["gehaald"], e
    assert not vr.rolronde_eisen(lees125, {**v3_125, "a|n0": "viraal", "a|n1": "viraal"}, lees42, v3_42, voor_p, voor_k,
                                 na_p, na_k)["1. de 125"], "twee valse viraal op 36: minder dan 95% juist"
    assert not vr.rolronde_eisen(lees125, v3_125, lees42, {**v3_42, "b|16": "onbekend"}, voor_p, voor_k, na_p,
                                 na_k)["2. de 42"]
    assert not vr.rolronde_eisen(lees125, v3_125, lees42, v3_42, voor_p, voor_k, {**na_p, "N": {"gevonden": 30, "vals": 0}},
                                 na_k)["3. gevonden"]
    assert not vr.rolronde_eisen(lees125, v3_125, lees42, v3_42, voor_p, voor_k, na_p,
                                 {**na_k, "S3": {"gevonden": 0, "vals": 1}})["4. vals"]
