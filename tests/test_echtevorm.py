"""Bekend nepnieuws in echte vorm (P6 van fase 0, PLAN #32.0d): de regels die vóór
de eerste vraag aan het model vastlagen."""

import pytest

from doublecheck import echtevorm as e


def _info(taal="en", oordeel="onwaar", tekst=None, cluster=()):
    return {"taal": taal, "oordeel": oordeel, "tekst": tekst or "Bill Gates wants to microchip everyone.",
            "cluster": set(cluster)}


def test_the_own_check_and_its_cluster_are_hidden_and_only_another_newsroom_counts_as_proof():
    info = {"a": _info(cluster={"a2"}), "a2": _info(), "b": _info(taal="es", oordeel="misleidend", cluster={"b2"}),
            "b2": _info(taal="es")}
    [stuk] = e.kies_groepen([{"a", "b"}], info, set(), n=1)
    assert stuk["zaak"] == "a" and stuk["tekst"] == info["a"]["tekst"]
    assert set(stuk["verborgen"]) == {"a", "a2"}
    assert set(stuk["eigen"]) == {"b", "b2"} and not set(stuk["eigen"]) & set(stuk["verborgen"])


def test_a_group_without_an_english_false_claim_or_another_newsroom_outside_the_cluster_is_skipped():
    info = {"a": _info(taal="fr"), "b": _info(taal="fr"), "c": _info(cluster={"d"}), "d": _info(cluster={"c"}),
            "e": _info(), "f": _info(oordeel="waar")}
    assert e.kies_groepen([{"a", "b"}, {"c", "d"}, {"e", "f"}], info, set(), n=3) == []


def test_descriptions_by_factcheckers_and_used_claims_are_not_chosen():
    info = {"a": _info(tekst="Claim: Bill Gates wants to microchip everyone."), "b": _info(), "c": _info(),
            "d": _info()}
    gekozen = e.kies_groepen([{"a", "b"}, {"c", "d"}], info, {"c"}, n=2)
    assert [s["zaak"] for s in gekozen] == ["b"]


def test_the_choice_is_fixed_by_seed_and_halves_are_balanced():
    info = {f"x{i}": _info() for i in range(40)}
    groepen = [{f"x{i}", f"x{i + 1}"} for i in range(0, 40, 2)]
    eerst = e.kies_groepen(groepen, info, set(), n=10)
    assert eerst == e.kies_groepen(list(reversed(groepen)), info, set(), n=10)
    helften = [s["helft"] for s in eerst]
    assert helften.count("toets") == helften.count("ontwikkel") == 5


def test_a_rejected_forward_is_replaced_by_the_next_in_the_same_order():
    pool = [{"id": f"c{i:03d}", "tekst": f"claim {i}", "cluster": set()} for i in range(80)]
    voor = e.kies_doorgestuurd(pool, set(), n=50)
    na = e.kies_doorgestuurd(pool, set(), n=50, afgewezen={voor[3]["zaak"]})
    assert [s["zaak"] for s in na[:3]] == [s["zaak"] for s in voor[:3]]
    assert voor[3]["zaak"] not in {s["zaak"] for s in na} and len(na) == 50


def test_reading_the_rewrite():
    assert e.lees_herschrijving('{"bericht": "Forwarded: they are chipping us!!"}') == "Forwarded: they are chipping us!!"
    assert e.lees_herschrijving('{"bericht": "  "}') is None
    assert e.lees_herschrijving("I can't help with that.") is None


def _uit(kleur, eigen=False, bronnen=({"soort": "web", "url": "https://www.reuters.com/x"},)):
    return {"kleur": kleur, "eigen_bewijs": eigen, "bronnen": list(bronnen)}


def test_red_with_the_partner_check_counts_as_proof_without_reading():
    stukken = [{"id": "r1", "deel": "R", "helft": "toets"}, {"id": "d1", "deel": "D", "helft": "ontwikkel"}]
    telling = e.telling(stukken, {"r1": _uit("rood", eigen=True), "d1": _uit(None)}, {})
    assert telling["R"]["rood met bewijs"] == 1 and telling["D"]["rood met bewijs"] == 0
    assert telling["eisen"]["minstens 70% rood met bewijs"] is False


def test_the_count_refuses_while_a_red_with_another_source_is_unread():
    stukken = [{"id": "d1", "deel": "D", "helft": "toets"}]
    with pytest.raises(e.Weigering):
        e.telling(stukken, {"d1": _uit("rood")}, {})
    telling = e.telling(stukken, {"d1": _uit("rood")}, {("d1", "bewijs"): "bewijst niet"})
    assert telling["D"]["rood"] == 1 and telling["D"]["rood met bewijs"] == 0
    assert telling["toetshelft"]["D"]["rood"] == 1


def test_a_claim_in_two_groups_is_chosen_once():
    info = {c: _info() for c in "abc"}
    gekozen = e.kies_groepen([{"a", "b"}, {"a", "c"}], info, set(), n=2)
    alle = [c for s in gekozen for c in [*s["verborgen"], *s["eigen"]]]
    assert len(gekozen) == 1 and len(alle) == len(set(alle))
