"""De dekking van de bronnenlijst op echte zoekresultaten (PLAN #32.29c): per taal hoe vaak de top 10 van Brave 1 en 2
goede uitgevers heeft, met `bronnen-v2` en `bronnen-v3` op dezelfde resultaten, met en zonder de factcheckers."""

import pytest

from doublecheck import bronnendekking as bd
from doublecheck import zoekcontrole as zc

SITES = {"elpais.com": [["goed", "Lin e.a. 0.79"]], "maldita.es": [["goed", "EFCSN, PO 2026-11-02"]],
         "newtral.es": [["goed", "IFCN"]], "larazon.es": [["goed", "JTI, PO 2026-11-02"]],
         "okdiario.com": [["laag", "Lin e.a. 0.30"]], "elmundo.es": [["goed", "Lin e.a. 0.78"]],
         "publico.pt": [["goed", "IFCN vernieuwing, PO 2026-11-02"]]}


def _tel(urls, sites=SITES):
    return bd.tel_vraag(urls, sites, staat={"domeinen": {}})


def test_good_outlets_are_counted_once_per_owner_and_officials_count_as_good():
    uit = _tel(["https://elpais.com/a", "https://elpais.com/b", "https://www.boe.gob.es/x", "https://okdiario.com/c"])
    assert uit["goed"] == 2  # El País één keer, de overheid erbij; okdiario is laag


def test_without_the_fact_checkers_only_the_newsrooms_count():
    """Een site met het IFCN of het EFCSN als herkomst is een factchecker, ook in vernieuwing; de JTI en Lin niet."""
    uit = _tel(["https://maldita.es/a", "https://newtral.es/b", "https://www.larazon.es/c", "https://publico.pt/d"])
    assert uit["goed"] == 4 and uit["goed_zonder"] == 1


def test_a_platform_never_counts_as_good():
    assert _tel(["https://www.youtube.com/watch?v=1", "https://x.com/iemand"])["goed"] == 0


def test_the_green_upper_bound_follows_the_wide_rule_of_the_check():
    """Twee goede, of één goede plus één andere die niet laag is, geen platform en geen staatsmedia (#32.11)."""
    assert _tel(["https://elpais.com/a", "https://www.elmundo.es/b"])["groen"]
    assert _tel(["https://elpais.com/a", "https://onbekend.example/b"])["groen"]
    assert not _tel(["https://elpais.com/a", "https://okdiario.com/b"])["groen"]
    assert not _tel(["https://maldita.es/a", "https://onbekend.example/b"])["groen_zonder"]


def test_the_count_per_language_uses_the_same_results_for_both_lists():
    rijen = [{"taal": "es", "urls": ["https://www.larazon.es/a", "https://elpais.com/b"]},
             {"taal": "es", "urls": ["https://onbekend.example/c"]}]
    v2 = {k: v for k, v in SITES.items() if k != "larazon.es"}
    tel = bd.telling(rijen, {"v2": v2, "v3": SITES}, staat={"domeinen": {}})
    # met v2 is La Razón zonder band: met de ruime regel kan groen al met El País plus een andere uitgever
    assert tel["es"]["v2"] == {"n": 2, "1 goed": 1, "2 goed": 0, "1 goed zonder factcheckers": 1,
                               "2 goed zonder factcheckers": 0, "groen kan": 1, "groen kan zonder factcheckers": 1}
    assert tel["es"]["v3"]["2 goed"] == 1 and tel["es"]["v3"]["groen kan"] == 1


def test_the_set_is_drawn_per_language_with_a_fixed_seed():
    rijen = [(f"{taal}{i}", taal, f"bewering nummer {i} in het {taal}, lang genoeg") for taal in ("en", "es") for i in range(30)]
    a, b = bd.kies(rijen, 10, 32291), bd.kies(list(reversed(rijen)), 10, 32291)
    assert a == b and len(a) == 20
    assert {s["taal"] for s in a} == {"en", "es"} and sum(s["taal"] == "es" for s in a) == 10
    assert len({s["claim"] for s in a}) == 20


def test_the_run_stops_before_the_limit():
    assert bd.mag_nog(399, 2.50) and not bd.mag_nog(500, 2.50)
    assert bd.mag_nog(0, 2.50) and zc.ZOEKPRIJS * 400 <= bd.BUDGET


def test_the_count_refuses_results_of_an_unknown_language():
    with pytest.raises(ValueError):
        bd.telling([{"taal": "fr", "urls": []}], {"v2": {}, "v3": {}}, staat={"domeinen": {}})
