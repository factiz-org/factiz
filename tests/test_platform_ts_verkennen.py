"""Verkennen en het netwerk van namen in TypeScript naast Python (B80, PLAN #34.2bo stap 3): per taal, thema, weergave en
naam hetzelfde antwoord na inlezen, dezelfde 404, en de schikking van het netwerk op dezelfde plek tot op de tiende."""

import itertools
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from factiz_site import app as fa
from factiz_site import db as fdb
from factiz_site import gelijk_verkennen as gv
from factiz_site import i18n, netwerk
from tests.test_factiz_context import bestand  # noqa: F401  (fixture: thema's, landen, namen en een dossier)
from tests.test_factiz_dossiers import _site as _dossiersite
from tests.test_factiz_namen import _site as _namensite
from tests.test_factiz_netwerk import _maak
from tests.test_factiz_verkennen import site  # noqa: F401  (fixture: thema's met een tweede thema en landen)

SITE = Path(__file__).resolve().parent.parent / "site"


def _node(code: str, invoer):
    uit = subprocess.run(["node", "--input-type=module", "-e", code], input=json.dumps(invoer), capture_output=True,
                         text=True, cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def _lees(module: str, functie: str) -> str:
    """Een stukje Node dat de invoer leest, `functie` op elk element loslaat en het antwoord schrijft."""
    return (f"import * as m from './src/platform/{module}';\nlet s = '';\nfor await (const d of process.stdin) s += d;\n"
            f"process.stdout.write(JSON.stringify(JSON.parse(s).map({functie})));")


def verschillen(client, adressen):
    return gv.verschillen(client, client.bestand, adressen)


@pytest.fixture
def lage_drempels(monkeypatch):
    # zoals de Python-toetsen: de echte drempels haalt een proefuitgave van acht beweringen nooit
    monkeypatch.setattr(fdb, "VERHOUDING_LAND", 2)
    monkeypatch.setattr(fdb, "VERHOUDING_THEMA", 1)


@pytest.fixture(scope="module")
def netwerkbestand(tmp_path_factory):
    return _maak(tmp_path_factory)


def _client(pad):
    client = TestClient(fa.maak_app(pad), follow_redirects=False)
    client.bestand = pad
    return client


# --- Verkennen --------------------------------------------------------------------------------------------------------

def test_explore_answers_the_same_for_every_view_and_every_refusal_in_every_language(site):  # noqa: F811
    client, _ = site
    assert verschillen(client, gv.adressen(fdb.Publicatie(client.bestand))) == []


def test_the_ratio_its_map_and_its_legend_answer_the_same_when_countries_pass_the_thresholds(site, lage_drempels,  # noqa: F811
                                                                                             monkeypatch):
    client, _ = site
    adressen = [f"/api/{taal}/verkennen?{v}" for taal in i18n.TALEN
                for v in ("thema=health&maat=verhouding", "maat=verhouding&thema=war", "thema=migration&maat=verhouding")]
    assert verschillen(client, adressen) == []
    # alleen de top van de staven, de kaart houdt alles
    monkeypatch.setattr(fdb, "VERKEN_LANDEN", 1)
    assert verschillen(client, adressen) == []
    # een land onder de drempel van het thema: geen verhouding, en de zin dat er geen land is
    monkeypatch.setattr(fdb, "VERHOUDING_THEMA", 3)
    assert verschillen(client, adressen) == []
    assert client.get(adressen[0]).json()["waar"]["leeg"]


def test_fewer_years_on_the_time_line_answer_the_same(site, monkeypatch):  # noqa: F811
    client, _ = site
    monkeypatch.setattr(fdb, "VERKEN_JAREN", 3)          # 2024 tot 2026: de rest telt als eerder
    adressen = [f"/api/{taal}/verkennen{v}" for taal in ("en", "nl", "ar") for v in ("", "?thema=health", "?thema=migration")]
    assert client.get("/api/en/verkennen").json()["tijd"]["eerder"] > 0
    assert verschillen(client, adressen) == []


def test_a_release_with_a_check_without_a_date_and_dossiers_answers_the_same(tmp_path_factory):
    client = _dossiersite(tmp_path_factory)[0]
    assert verschillen(client, gv.adressen(fdb.Publicatie(client.bestand))) == []


def test_a_release_without_themes_still_explores_time_and_place_the_same(tmp_path_factory):
    client = _namensite(tmp_path_factory)[0]
    assert fdb.Publicatie(client.bestand).themas == []
    adressen = [f"/api/{taal}/verkennen{v}" for taal in i18n.TALEN for v in ("", "?thema=war", "?maat=verhouding")]
    assert verschillen(client, adressen) == []


# --- het netwerk van namen --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("namen, samen", [(4, 1), (4, 2), (5, 1), (70, 25)])
def test_the_network_answers_the_same_for_every_name_and_refusal_at_every_threshold(netwerkbestand, monkeypatch, namen,
                                                                                    samen):
    monkeypatch.setattr(fdb, "NETWERK_NAMEN", namen)
    monkeypatch.setattr(fdb, "NETWERK_SAMEN", samen)
    client = _client(netwerkbestand)
    assert verschillen(client, gv.adressen(fdb.Publicatie(netwerkbestand))) == []


def test_a_release_without_names_has_no_network_in_both(tmp_path_factory):
    client = _client(_maak(tmp_path_factory, met_namen=False))
    adressen = [f"/api/{taal}/{a}" for taal in ("en", "nl") for a in ("netwerk", "netwerk?naam=Q812", "verkennen")]
    assert client.get("/api/en/verkennen").json()["netwerk"] is None
    assert verschillen(client, adressen) == []


def test_names_themes_countries_and_a_dossier_together_answer_the_same(bestand, monkeypatch):  # noqa: F811
    for naam, waarde in (("NETWERK_NAMEN", 4), ("NETWERK_SAMEN", 1), ("VERHOUDING_LAND", 1), ("VERHOUDING_THEMA", 1)):
        monkeypatch.setattr(fdb, naam, waarde)
    client = _client(bestand[0])
    assert verschillen(client, gv.adressen(fdb.Publicatie(client.bestand))) == []


def test_names_in_other_scripts_get_the_same_network_and_labels(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(fdb, "NETWERK_SAMEN", 1)
    client = _namensite(tmp_path_factory)[0]
    assert verschillen(client, [f"/api/{taal}/netwerk" for taal in i18n.TALEN]
                       + [f"/api/{taal}/netwerk?naam=Q3874799" for taal in i18n.TALEN]) == []


# --- de schikking en het rekenen --------------------------------------------------------------------------------------

def _dichte(zaad: int, randen: bool = True):
    rnd = random.Random(zaad)
    n = 70
    stralen = [4 + rnd.random() * 22 for _ in range(n)]
    labels = [rnd.choice([0, 0, 40 + rnd.random() * 90]) for _ in range(n)]
    lijnen = [(i, j, rnd.randint(25, 1800)) for i, j in itertools.combinations(range(n), 2) if rnd.random() < .09]
    return stralen, lijnen if randen else [], labels


def test_the_layout_lands_on_the_same_tenth_for_dense_networks_and_the_smallest_ones():
    gevallen = [_dichte(z, r) for z in (1, 2, 3) for r in (True, False)]
    gevallen += [([], [], []), ([10.0], [], [50.0]), ([10.0, 20.0], [(0, 1, 3)], [0.0, 80.0]),
                 ([26.0, 19.6, 18.0, 16.7], [(0, 1, 1), (1, 2, 2), (2, 3, 1)], [70.0, 70.0, 0.0, 0.0])]
    ts = _node(_lees("verkennen-schikking.ts", "([s, r, l]) => m.schik(s, r, l)"), gevallen)
    py = json.loads(json.dumps([netwerk.schik(s, r, l) for s, r, l in gevallen]))
    assert [t == p for t, p in zip(ts, py)] == [True] * len(gevallen)


def test_rounding_and_one_decimal_go_to_even_on_an_exact_half_like_python():
    rnd = random.Random(5)
    waarden = [k / 8 for k in range(-40, 41)] + [k / 4 + 0.05 for k in range(20)] + [1.005, 2.675, 0.125, 0.375, 1e-9]
    waarden += [rnd.uniform(0, 1000) for _ in range(300)] + [4 + 22 * math.sqrt(a / 977) for a in range(1, 400)]
    vragen = [[x, n] for x in waarden for n in (1, 2)]
    ts = _node(_lees("verkennen-getal.ts", "([x, n]) => [m.rond(x, n), m.vast(x, n)]"), vragen)
    assert ts == [[round(x, n), f"{x:.{n}f}"] for x, n in vragen]


def test_the_logarithm_is_correctly_rounded():
    mpmath = pytest.importorskip("mpmath")
    mpmath.mp.prec = 200
    rnd = random.Random(8)
    xs = [rnd.uniform(0, 3000) for _ in range(3000)] + [rnd.uniform(0, 1) for _ in range(1000)] + [1e-12, 0.5, 1.0, 2.0]
    ts = _node(_lees("verkennen-getal.ts", "(x) => [m.ln1p(x), m.ln(x)]"), xs)
    assert ts == [[float(mpmath.log1p(x)), float(mpmath.log(x))] for x in xs]


@pytest.mark.skipif(sys.platform != "darwin", reason="de uitzonderingen zijn die van macOS, waar Python de maat is")
def test_how_often_two_names_meet_weighs_exactly_as_in_python_up_to_200000():
    ts = _node("import { ln1p } from './src/platform/verkennen-getal.ts';\n"
               "import { binnenkant } from './src/platform/verkennen-schikking.ts';\n"
               "let s = ''; for await (const d of process.stdin) s += d;\n"
               "process.stdout.write(JSON.stringify(JSON.parse(s).map((k) => binnenkant.gewicht(k))));", list(range(1, 200001)))
    assert [i + 1 for i, (t, p) in enumerate(zip(ts, (math.log1p(k) for k in range(1, 200001)))) if t != p] == []


def test_the_bounds_of_the_map_and_their_steps_are_those_of_python():
    rnd = random.Random(3)
    lijsten = [[], [0, 0], [1], [5, 5, 5], [1, 2, 3], [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987],
               [1450, 1350, 2350, 99, 100, 105, 994, 995, 9950, 12345]]
    lijsten += [[rnd.randint(0, 40000) for _ in range(rnd.randint(1, 120))] for _ in range(40)]
    ts = _node(_lees("verkennen.ts", "(w) => { const g = m.binnenkant.grenzenAantal(w); "
                                     "return [g, w.map((x) => m.binnenkant.trap(x, g))]; }"), lijsten)
    assert ts == [[fa.grenzen_aantal(w), [fa.trap(x, fa.grenzen_aantal(w)) for x in w]] for w in lijsten]
