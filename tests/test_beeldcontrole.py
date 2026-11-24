"""Het beeld in de nieuwe controle (PLAN #32.16): `zoekcontrole.controleer` met en zonder het beeld, met voor beide
armen dezelfde zoekvraag en dezelfde database. Een nepzoeker en een nepmodel staan in voor Brave en Anthropic."""

import dataclasses

import pytest

from doublecheck import beeldcontrole as bk
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config
from tests.test_zoekcontrole import PNG, SITES, NepModel, _brave

BERICHT = "Photo shows the floods in Hyderabad this week."


def _config(**instellingen):
    config = load_config()
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def test_the_switch_is_on_only_in_a_copy_for_the_arm_with_the_image():
    config = _config(beeld=False)
    armen = bk.armen(config)
    assert armen["zonder"].berichtcontrole.beeld is False and armen["met"].berichtcontrole.beeld is True
    assert armen["met"].berichtcontrole.lezer == armen["zonder"].berichtcontrole.lezer == bk.LEZER == "lezer-v3"
    assert config.berichtcontrole.beeld is False
    assert bk.armen(_config(beeld=True))["zonder"].berichtcontrole.beeld is False


def test_both_arms_share_one_search_and_one_database_look_and_only_one_sees_the_image():
    nep, gezocht, gekeken = NepModel("klopt niet", steunt=(), tegen=(1,)), [], []
    zoek = lambda q: gezocht.append(q) or _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b")  # noqa: E731
    snel = lambda t: gekeken.append(t)  # noqa: E731
    stuk = {"id": "n1", "set": "N", "tekst": BERICHT, "datum": "2021-11-10"}
    uit = bk.beide(stuk, PNG, bk.armen(_config()), nep, zoek, snel, SITES, eigen_urls=set())
    assert gezocht == [zc.zoekvraag(BERICHT)] and gekeken == [BERICHT]
    zonder, met = (v["messages"][0]["content"] for v in nep.verzoeken)
    assert isinstance(zonder, str) and met[0]["type"] == "image" and met[1]["text"] == zonder
    assert "2021-11-10" in zonder
    assert uit["zonder"]["kleur"] == uit["met"]["kleur"] == "rood"
    # de zoekvraag is één keer betaald, bij de arm zonder beeld
    assert uit["zonder"]["kosten"] == pytest.approx(uit["met"]["kosten"] + zc.ZOEKPRIJS) and uit["met"]["kosten"] > 0


def test_an_answer_from_the_database_is_the_same_in_both_arms_and_costs_nothing():
    nep, gezocht = NepModel(), []
    snel = {"oordeel": "klopt niet", "kleur": "rood",
            "bronnen": [{"soort": "check van een redactie", "url": "https://factly.in/x/"}]}
    uit = bk.beide({"id": "n1", "set": "N", "tekst": BERICHT}, PNG, bk.armen(_config()), nep,
                   lambda q: gezocht.append(q), lambda t: snel, SITES, eigen_urls={"http://www.factly.in/x"})
    assert gezocht == [] and nep.verzoeken == []
    assert all(r["route"] == "database" and r["kosten"] == 0 and r["eigen_check"] for r in uit.values())


def test_an_alarm_is_proven_by_its_own_check_from_the_database_or_as_a_contradicting_result():
    eigen = {"https://factly.in/unrelated-photos/"}
    database = {"bronnen": [{"soort": "check van een redactie", "url": "http://www.factly.in/unrelated-photos"}]}
    tegen = {"bronnen": [{"url": "https://factly.in/unrelated-photos/?amp=1", "rol": "spreekt tegen"}]}
    bevestigt = {"bronnen": [{"url": "https://factly.in/unrelated-photos/", "rol": "bevestigt"}]}
    ander = {"bronnen": [{"url": "https://www.altnews.in/other/", "rol": "spreekt tegen"}]}
    assert bk.met_eigen_check(database, eigen) and bk.met_eigen_check(tegen, eigen)
    assert not bk.met_eigen_check(bevestigt, eigen) and not bk.met_eigen_check(ander, eigen)
    assert not bk.met_eigen_check(tegen, set())


def _r(kleur, eigen=False, route="zoeken", over_beeld=False):
    return {"kleur": kleur, "eigen_check": eigen, "route": route, "over_beeld": over_beeld, "kosten": 0.01,
            "seconden": 3.0}


STUKKEN = [{"id": "n1", "set": "N"}, {"id": "n2", "set": "N"}, {"id": "w1", "set": "W"}, {"id": "w2", "set": "W"}]


def test_the_count_refuses_while_an_alarm_or_a_green_that_counts_is_unread():
    per_arm = {"zonder": {"n1": _r("rood", eigen=True), "n2": _r("oranje"), "w1": _r("groen"), "w2": _r(None)},
               "met": {"n1": _r("rood", eigen=True), "n2": _r("groen"), "w1": _r("rood"), "w2": _r("groen")}}
    with pytest.raises(bk.Weigering):
        bk.telling(STUKKEN, per_arm, {("n2", "zonder"): "bewijst", ("n2", "met"): "vals groen"})
    labels = {("n2", "zonder"): "bewijst", ("n2", "met"): "vals groen", ("w1", "met"): "vals"}
    uit = bk.telling(STUKKEN, per_arm, labels)
    assert uit["zonder"]["N"]["gewaarschuwd met bewijs"] == 2 and uit["met"]["N"]["gewaarschuwd met bewijs"] == 1
    assert uit["met"]["N"]["met de eigen check"] == 1 and uit["met"]["N"]["onterecht groen"] == 1
    assert uit["met"]["W"]["vals alarm"] == 1 and uit["zonder"]["W"].get("vals alarm", 0) == 0
    assert uit["eisen"] == {"1. N: met beeld minstens zoveel gewaarschuwd met bewijs als zonder": False,
                            "2. W: met beeld niet meer vals alarm dan zonder": False,
                            "3. N: met beeld geen onterecht groen": False}
    assert uit["gehaald"] is False


def test_an_alarm_whose_source_does_not_prove_it_or_a_set_error_never_counts_against_the_requirements():
    per_arm = {"zonder": {"n1": _r("rood"), "n2": _r(None), "w1": _r("rood"), "w2": _r("groen")},
               "met": {"n1": _r("rood"), "n2": _r("groen"), "w1": _r("rood"), "w2": _r("groen")}}
    labels = {("n1", "zonder"): "bewijst niet", ("n1", "met"): "bewijst", ("n2", "met"): "set fout",
              ("w1", "zonder"): "set fout", ("w1", "met"): "set fout"}
    uit = bk.telling(STUKKEN, per_arm, labels)
    assert uit["zonder"]["N"].get("gewaarschuwd met bewijs", 0) == 0 and uit["met"]["N"]["gewaarschuwd met bewijs"] == 1
    assert uit["met"]["N"].get("onterecht groen", 0) == 0 and uit["met"]["W"].get("vals alarm", 0) == 0
    assert all(uit["eisen"].values()) and uit["gehaald"] is True


def test_only_messages_answered_in_both_arms_count_and_an_incomplete_run_never_passes():
    per_arm = {"zonder": {"n1": _r("rood", eigen=True), "w1": _r("groen")},
               "met": {"n1": _r("rood", eigen=True)}}
    uit = bk.telling(STUKKEN, per_arm, {})
    assert uit["zonder"]["N"]["n"] == 1 and "n" not in uit["zonder"]["W"]
    assert all(uit["eisen"].values()) and uit["volledig"] == "1 van 4" and uit["gehaald"] is False
