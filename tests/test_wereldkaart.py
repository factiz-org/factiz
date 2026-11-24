"""De vormen van de wereldkaart (PLAN #34.2am, SPECS E9.S20 AC4): Equal Earth, vereenvoudigd, zonder Antarctica, met
de herkomst erbij."""

import json
import math
import re

import pytest

from doublecheck import wereldkaart as wk


def test_equal_earth_keeps_the_centre_and_the_symmetry_and_reaches_its_known_edges():
    assert wk.projecteer(0, 0) == (0.0, 0.0)
    x, y = wk.projecteer(37, 21)
    assert wk.projecteer(-37, -21) == pytest.approx((-x, -y))
    # de rand op de evenaar en de pool (Šavrič e.a. 2018): 2,70664 en 1,31736 op de eenheidsbol
    assert wk.projecteer(180, 0)[0] == pytest.approx(2.70664, abs=1e-4)
    assert wk.projecteer(0, 90)[1] == pytest.approx(1.31736, abs=1e-4)


def test_simplifying_keeps_the_ends_and_drops_points_on_a_straight_line():
    lijn = [(0, 0), (1, 0.01), (2, 0), (3, 5), (4, 0)]
    assert wk.vereenvoudig(lijn, 0.1) == [(0, 0), (2, 0), (3, 5), (4, 0)]
    assert wk.vereenvoudig([(0, 0), (1, 1)], 5) == [(0, 0), (1, 1)]


def _land(code, ringen, naam="X"):
    return {"type": "Feature", "properties": {"ISO_A2_EH": code, "NAME": naam},
            "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in ringen]}}


def _vierkant(lon, lat, d):
    return [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]


def test_a_map_holds_every_country_with_a_code_but_never_antarctica_and_keeps_a_tiny_country():
    bron = {"type": "FeatureCollection", "features": [
        _land("NL", [_vierkant(4, 51, 3)]), _land("BR", [_vierkant(-60, -15, 20), _vierkant(-30, -5, 0.001)]),
        _land("LU", [_vierkant(6, 49.5, 0.2)]), _land("-99", [_vierkant(30, 10, 5)]), _land("AQ", [_vierkant(0, -80, 30)])]}
    kaart = wk.bouw(bron)
    assert set(kaart["landen"]) == {"NL", "BR", "LU"}
    # een eiland dat op deze schaal niets is, valt weg; het land zelf nooit, hoe klein ook
    assert kaart["landen"]["BR"].count("M") == 1 and kaart["landen"]["LU"].startswith("M")
    getallen = [float(g) for pad in kaart["landen"].values() for g in re.findall(r"-?\d+(?:\.\d+)?", pad)]
    assert min(getallen) >= 0 and max(getallen[0::2]) <= kaart["breed"] + 0.1 and max(getallen[1::2]) <= kaart["hoog"] + 0.1
    assert kaart["breed"] == wk.BREED and kaart["hoog"] > 0     # de hoogte volgt uit de landen zelf
    assert wk.bouw(bron) == kaart


def test_the_map_of_the_site_comes_from_natural_earth_and_says_so():
    kaart = json.loads(wk.UIT.read_text(encoding="utf-8"))
    assert {"IN", "US", "UA", "RU", "BR", "NL", "CN", "PS", "TW"} <= set(kaart["landen"]) and "AQ" not in kaart["landen"]
    herkomst = kaart["_meta"]["herkomst"]
    assert "Natural Earth" in herkomst and "publiek domein" in herkomst and "Equal Earth" in herkomst
    assert all(re.fullmatch(r"(M[-\d. L]+Z)+", pad) for pad in kaart["landen"].values())
    assert len(wk.UIT.read_bytes()) < 200_000          # het staat in elke pagina van Verkennen
    # de verhouding van breedte en hoogte van Equal Earth zonder Antarctica
    assert 0.4 < kaart["hoog"] / kaart["breed"] < 0.55 and math.isclose(kaart["breed"], wk.BREED)
