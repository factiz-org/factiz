"""Een stroom van consensus naast de factchecks: de eerste meting met het nieuwsoverzicht van Wikipedia (PLAN #32.55,
PO 2026-11-07: "De echte work ground zit hem dus in een soort database met consensus, laten we zeggen Wikipedia")."""

import datetime as dt
import json

import numpy as np
import pytest

from doublecheck import consensus as cs


def test_the_portal_page_of_a_day_has_the_title_wikipedia_uses():
    assert cs.portaaltitel(dt.date(2026, 11, 7)) == "Portal:Current events/2026 November 7"
    assert cs.portaaltitel(dt.date(2008, 3, 9)) == "Portal:Current events/2008 March 9"


def test_a_message_is_held_against_its_own_day_and_the_three_before():
    assert cs.venster("2026-11-02") == [dt.date(2026, 10, 30), dt.date(2026, 10, 31), dt.date(2026, 11, 1),
                                        dt.date(2026, 11, 2)]
    assert cs.venster(None) == [] and cs.venster("onbekend") == []


def test_the_set_has_no_message_that_came_from_the_portal_and_knows_what_is_true():
    duel = [{"id": "K:1", "set": "K", "tekst": "a", "datum": "2026-11-06"},
            {"id": "F:1", "set": "F", "tekst": "b", "datum": "2026-11-06", "beeld": "u"},
            {"id": "O:gfc-1", "set": "O", "tekst": "c", "datum": "2026-10-01"}]
    vers = [{"id": "O:gfc-2", "set": "O", "tekst": "d", "datum": "2026-09-01"},
            {"id": "W:wikinews:en:1", "set": "W", "tekst": "e", "datum": "2008-03-19"},
            {"id": "W-merk:1", "set": "W-merk", "tekst": "f", "datum": "2026-11-01"},
            {"id": "O:gfc-1", "set": "O", "tekst": "c", "datum": "2026-10-01"}]
    uit = cs.kies_set(duel, vers)
    assert [(r["id"], r["waar"]) for r in uit] == [("K:1", True), ("F:1", True), ("O:gfc-1", False), ("O:gfc-2", False),
                                                   ("W:wikinews:en:1", True), ("W-merk:1", True)]
    with pytest.raises(ValueError):
        cs.kies_set([{"id": "W2:x", "set": "W2", "tekst": "g", "datum": "2026-10-01"}], [])


def test_the_three_lines_most_like_the_message_are_chosen():
    regels = np.array([[1, 0], [0, 1], [0.9, 0.1], [0.5, 0.5]], dtype=float)
    assert cs.kandidaten(np.array([1.0, 0.0]), regels, n=3) == [0, 2, 3]
    assert cs.kandidaten(np.array([1.0, 0.0]), regels[:0], n=3) == []


def test_haiku_judges_each_line_against_the_message_without_knowing_the_answer():
    v = cs.verzoek("Tesla recalls 2 million cars", "2026-11-01", ["Tesla recalls cars.", "A storm hits Japan."])
    tekst = v["messages"][0]["content"]
    assert "Tesla recalls 2 million cars" in tekst and "[1] Tesla recalls cars." in tekst and "[2] A storm" in tekst
    assert "2026-11-01" in tekst and v["model"] == "claude-haiku-5-5"
    schema = v["output_config"]["format"]["schema"]
    assert schema["properties"]["regels"]["items"]["properties"]["relatie"]["enum"] == ["bevestigt", "spreekt tegen",
                                                                                       "niets"]
    assert "wikinews" not in json.dumps(v).lower() and "fact-check" not in tekst.lower()


def test_the_answer_is_read_strictly_and_a_contradiction_outweighs_a_confirmation():
    goed = json.dumps({"regels": [{"nr": 1, "relatie": "bevestigt"}, {"nr": 2, "relatie": "niets"}]})
    assert cs.lees_relaties(goed, 2) == ["bevestigt", "niets"]
    assert cs.lees_relaties(json.dumps({"regels": [{"nr": 5, "relatie": "bevestigt"}]}), 2) == ["niets", "niets"]
    assert cs.lees_relaties("geen json", 3) == ["niets"] * 3
    assert cs.samen(["niets", "bevestigt"]) == "bevestigt"
    assert cs.samen(["bevestigt", "spreekt tegen"]) == "spreekt tegen" and cs.samen([]) == "niets"


def _rij(i, waar, uitkomst):
    return {"id": i, "waar": waar, "uitkomst": uitkomst, "regels": ["r"]}


def test_the_count_refuses_while_a_confirmation_or_contradiction_is_unread_and_checks_the_requirements():
    berichten = ([{"id": f"w{i}", "waar": True} for i in range(175)] + [{"id": f"n{i}", "waar": False} for i in range(125)])
    antwoorden = {f"w{i}": _rij(f"w{i}", True, "bevestigt") for i in range(40)}
    antwoorden.update({f"n{i}": _rij(f"n{i}", False, "spreekt tegen") for i in range(10)})
    antwoorden["n10"] = _rij("n10", False, "bevestigt")
    with pytest.raises(cs.Weigering):
        cs.telling(berichten, antwoorden, {})
    labels = {**{f"w{i}": "terecht" for i in range(38)}, "w38": "onterecht", "w39": "onterecht",
              **{f"n{i}": "terecht" for i in range(10)}, "n10": "onterecht"}
    t = cs.telling(berichten, antwoorden, labels)
    assert t["waar"]["bevestigt terecht"] == 38 and t["nep"]["bevestigt onterecht"] == 1
    assert t["nep"]["spreekt tegen terecht"] == 10 and t["waar"]["zonder overzicht"] == 135
    assert t["eisen"] == {"1 nut (minstens 35)": True, "2 veilig (hoogstens 1)": True, "3 geen vals alarm (hoogstens 2)": True}
