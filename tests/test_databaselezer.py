"""De lezer leest ook de checks uit de database, en het beeld helpt kiezen (PLAN #32.28): drie armen op dezelfde
zoekresultaten van Brave. Arm 0 is het product nu (`lezer-v3`), arm 1 `lezer-v5` met de beste 5 checks uit de
database, arm 2 daarbij het beeld dat een check bevestigt. Een nepzoeker en een nepmodel staan in voor Brave en
Anthropic."""

import dataclasses

import pytest

from doublecheck import databaselezer as dl
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config
from tests.test_zoekcontrole import SITES, NepModel, _brave

BERICHT = "Photo shows the floods in Hyderabad this week."


def _config(**instellingen):
    config = load_config()
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **instellingen))


def _check(claim, url, oordeel="onwaar", groep=None, beeld=False):
    return {"claim": claim, "groep": groep or claim, "tekst": f"bewering {claim}", "redactie": "BOOM",
            "oordeel": oordeel, "datum": "2020-10-15", "url": url, "beeld": beeld}


def test_arm_0_is_the_product_now_and_arms_1_and_2_read_the_database_and_none_sees_the_image():
    config = _config(lezer="lezer-v4", beeld=True)
    armen = dl.armen(config)
    assert armen["0"].berichtcontrole.lezer == "lezer-v3"
    assert armen["1"].berichtcontrole.lezer == armen["2"].berichtcontrole.lezer == "lezer-v5"
    assert not any(a.berichtcontrole.beeld for a in armen.values())
    assert all(a.berichtcontrole.kring1 == config.berichtcontrole.kring1 for a in armen.values())
    assert config.berichtcontrole.lezer == "lezer-v4" and config.berichtcontrole.beeld is True


def test_the_database_checks_are_the_five_of_the_words_with_what_the_database_says_about_them():
    k1 = [{"claim": "c1", "url": "https://factly.in/a/", "gelijkenis": 0.71, "groep": "g1"},
          {"claim": "c2", "url": "https://boomlive.in/b/", "gelijkenis": 0.66, "groep": "c2"},
          {"claim": "weg", "url": "https://x.org/c/", "gelijkenis": 0.62, "groep": "weg"}]
    info = {("c1", "https://factly.in/a/"): {"tekst": "t1", "redactie": "FACTLY", "oordeel": "misleidend",
                                             "datum": "2021-11-10"},
            ("c2", "https://boomlive.in/b/"): {"tekst": "t2", "redactie": "BOOM", "oordeel": "onwaar",
                                               "datum": "2020-10-15"}}
    checks, ontbreekt = dl.checks_uit(k1, info)
    assert [(c["claim"], c["groep"], c["tekst"], c["oordeel"], c["beeld"]) for c in checks] == [
        ("c1", "g1", "t1", "misleidend", False), ("c2", "c2", "t2", "onwaar", False)]
    assert ontbreekt == 1  # een claim die niet meer in de database staat, valt weg en wordt gemeld


def test_the_image_marks_a_check_already_in_the_five_and_adds_one_that_was_not_there():
    vijf = [_check("c1", "https://factly.in/a/"), _check("c2", "https://www.boomlive.in/b/")]
    bevestigd = [_check("c2", "http://boomlive.in/b"), _check("c9", "https://altnews.in/z/")]
    twee = dl.met_beeld(vijf, bevestigd)
    assert [(c["claim"], c["beeld"]) for c in twee] == [("c1", False), ("c2", True), ("c9", True)]
    assert vijf[1]["beeld"] is False  # de lijst van arm 1 blijft zoals hij was
    assert dl.met_beeld(vijf, []) == vijf


def _paar(vraag, artikel, beeld="https://x.org/b.jpg", punten=120, uitgesloten=False, via=("tekst",), set_="N"):
    return {"set": set_, "vraag": vraag, "artikel": artikel, "beeld": beeld, "pdq": 120, "punten": punten,
            "dekking": 0.4, "uitgesloten": uitgesloten, "via": {"productie": list(via), "kopie": list(via)},
            "groepen": {"productie": ["g"], "kopie": ["g"]}}


def test_only_a_confirmed_viral_image_found_in_production_and_not_the_screenshot_itself_counts():
    paren = [_paar("n1", "https://a.org/1/", punten=80), _paar("n1", "https://a.org/2/", punten=300),
             _paar("n1", "https://a.org/2/", beeld="https://x.org/c.jpg", punten=90),
             _paar("n1", "https://a.org/3/", uitgesloten=True), _paar("n1", "https://a.org/4/", via=()),
             _paar("n1", "https://a.org/5/", beeld="https://x.org/huis.jpg"), _paar("n1", "https://a.org/6/", punten=3),
             _paar("n2", "https://a.org/7/"), _paar("n1", "https://a.org/8/", set_="W")]
    rollen = {(p["artikel"], p["beeld"]): "viraal" for p in paren}
    rollen[("https://a.org/5/", "https://x.org/huis.jpg")] = "huisstijl"
    assert dl.bevestigde_artikelen(paren, rollen, "N", "n1") == ["https://a.org/2/", "https://a.org/1/"]
    assert dl.bevestigde_artikelen(paren, {}, "N", "n1") == []


def _nep(oordeel="klopt niet", zelfde=(1,)):
    nep = NepModel(oordeel, steunt=(), tegen=())
    nep.d["checks"] = [{"nr": n, "zelfde": True} for n in zelfde]
    return nep


STUK = {"id": "n1", "set": "N", "tekst": BERICHT, "datum": "2020-10-20"}


def test_all_arms_share_one_search_and_one_database_look_and_arm_2_is_asked_only_when_the_image_adds_something():
    nep, gezocht, gekeken = _nep(), [], []
    zoek = lambda q: gezocht.append(q) or _brave("https://www.infowars.com/c")  # noqa: E731
    snel = lambda t: gekeken.append(t)  # noqa: E731
    vijf = [_check("c1", "https://www.boomlive.in/old-flood/", groep="eigen")]
    uit = dl.drie(STUK, vijf, vijf, dl.armen(_config()), nep, zoek, snel, SITES,
                  eigen_urls={"https://boomlive.in/old-flood"}, eigen_groepen={"eigen"})
    assert gezocht == [zc.zoekvraag(BERICHT)] and gekeken == [BERICHT] and len(nep.verzoeken) == 2
    nul, een = (v["messages"][0]["content"] for v in nep.verzoeken)
    assert "[D1]" not in nul and "[D1] BOOM" in een and "2020-10-20" in nul and "2020-10-20" in een
    assert uit["0"]["kleur"] is None and uit["1"]["kleur"] == "rood"  # alleen de check uit de database spreekt tegen
    assert uit["1"]["eigen_check"] and uit["1"]["eigen_gekozen"] and uit["1"]["gekozen"] == ["eigen"]
    assert not uit["0"]["eigen_check"] and uit["0"]["gekozen"] == []
    assert uit["2"]["kopie_van"] == "1" and uit["2"]["kleur"] == "rood" and uit["2"]["kosten"] == 0
    # de zoekvraag is één keer betaald, bij arm 0
    assert uit["0"]["kosten"] == pytest.approx(uit["1"]["kosten"] + zc.ZOEKPRIJS)

    nep2 = _nep(zelfde=(2,))
    met = dl.met_beeld(vijf, [_check("c9", "https://altnews.in/z/")])
    uit2 = dl.drie(STUK, vijf, met, dl.armen(_config()), nep2, zoek, lambda t: None, SITES, set(), {"eigen"})
    assert len(nep2.verzoeken) == 3 and dl.zc.BEELDZIN in nep2.verzoeken[2]["messages"][0]["content"]
    assert uit2["2"]["kopie_van"] is None and uit2["2"]["beeldchecks"] == 1 and uit2["1"]["beeldchecks"] == 0
    assert uit2["2"]["kleur"] == "rood" and not uit2["2"]["eigen_gekozen"] and uit2["2"]["gekozen"] == ["c9"]
    assert uit2["1"]["kleur"] is None  # D2 bestaat niet in arm 1


def test_an_answer_from_the_first_ring_is_the_same_in_all_arms_and_costs_nothing():
    nep, gezocht = _nep(), []
    snel = {"oordeel": "klopt niet", "kleur": "rood",
            "bronnen": [{"soort": "check van een redactie", "url": "https://factly.in/x/"}]}
    vijf = [_check("c1", "https://factly.in/x/")]
    uit = dl.drie(STUK, vijf, dl.met_beeld(vijf, [_check("c9", "https://a.org/z/")]), dl.armen(_config()), nep,
                  lambda q: gezocht.append(q), lambda t: snel, SITES, {"https://factly.in/x"}, set())
    assert gezocht == [] and nep.verzoeken == []
    assert all(r["route"] == "database" and r["kosten"] == 0 and r["eigen_check"] for r in uit.values())


def _r(kleur, eigen=False, route="zoeken", kopie_van=None, eigen_gekozen=False, gekozen=(), andere=0):
    return {"kleur": kleur, "eigen_check": eigen, "route": route, "kopie_van": kopie_van, "over_beeld": False,
            "eigen_gekozen": eigen_gekozen, "gekozen": list(gekozen), "andere_gekozen": andere, "kosten": 0.01,
            "seconden": 3.0}


STUKKEN = [{"id": "n1", "set": "N"}, {"id": "n2", "set": "N"}, {"id": "w1", "set": "W"}]


def test_the_count_refuses_while_an_alarm_or_a_green_that_counts_is_unread_and_a_copy_shares_its_label():
    per_arm = {"0": {"n1": _r(None), "n2": _r("oranje"), "w1": _r(None)},
               "1": {"n1": _r("rood", eigen=True, eigen_gekozen=True, gekozen=["e"]), "n2": _r("groen"),
                     "w1": _r("rood", gekozen=["x"], andere=1)},
               "2": {"n1": _r("rood", eigen=True, kopie_van="1", eigen_gekozen=True, gekozen=["e"]),
                     "n2": _r("groen", kopie_van="1"), "w1": _r("rood", kopie_van="1", gekozen=["x"], andere=1)}}
    with pytest.raises(dl.Weigering):
        dl.telling(STUKKEN, per_arm, {("n2", "0"): "bewijst", ("n2", "1"): "vals groen"})
    labels = {("n2", "0"): "bewijst", ("n2", "1"): "vals groen", ("w1", "1"): "vals"}
    uit = dl.telling(STUKKEN, per_arm, labels)
    assert uit["0"]["N"]["gewaarschuwd met bewijs"] == 1 and uit["1"]["N"]["gewaarschuwd met bewijs"] == 1
    assert uit["1"]["N"]["met de eigen check"] == 1 and uit["2"]["N"]["onterecht groen"] == 1
    assert uit["1"]["N"]["eigen check gekozen"] == 1 and uit["1"]["W"]["andere check gekozen"] == 1
    assert uit["2"]["W"]["vals alarm"] == 1 and uit["0"]["W"].get("vals alarm", 0) == 0
    assert uit["eisen"] == {"1. N: arm 1 minstens 10 meer gewaarschuwd met bewijs dan arm 0": False,
                            "2. N: arm 2 minstens 4 meer gewaarschuwd met bewijs dan arm 1": False,
                            "3. W: in arm 1 en arm 2 niet meer vals alarm dan in arm 0": False,
                            "4. N: in arm 1 en arm 2 niet meer onterecht groen dan in arm 0": False}
    assert uit["database kandidaat"] is False and uit["beeld kandidaat"] is False
    with pytest.raises(dl.Weigering):
        dl.telling(STUKKEN, per_arm, {**labels, ("w1", "1"): "misschien"})


def test_the_requirements_are_counted_as_written_in_advance_and_an_incomplete_run_never_passes():
    n = [{"id": f"n{i}", "set": "N"} for i in range(16)] + [{"id": "w1", "set": "W"}]
    per_arm = {"0": {s["id"]: _r(None) for s in n},
               "1": {**{s["id"]: _r("rood", eigen=i < 10) for i, s in enumerate(n[:16])}, "w1": _r(None)},
               "2": {**{s["id"]: _r("rood", eigen=True) for s in n[:16]}, "w1": _r(None)}}
    labels = {(f"n{i}", "1"): "bewijst niet" for i in range(10, 16)}
    uit = dl.telling(n, per_arm, labels)
    assert uit["1"]["N"]["gewaarschuwd met bewijs"] == 10 and uit["2"]["N"]["gewaarschuwd met bewijs"] == 16
    assert all(uit["eisen"].values()) and uit["database kandidaat"] and uit["beeld kandidaat"]
    del per_arm["2"]["w1"]
    onvolledig = dl.telling(n, per_arm, labels)
    assert onvolledig["volledig"] == "16 van 17" and not onvolledig["database kandidaat"]
