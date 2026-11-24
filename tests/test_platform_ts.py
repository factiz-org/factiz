"""De TypeScript-kant van het platform naast de Python-kant (B80, PLAN #34.2bo stap 3): per ingang en per taal hetzelfde
antwoord, na inlezen, en dezelfde 404. Zo gaat de site naar Cloudflare zonder dat een pagina iets anders zegt."""

import json
import subprocess
from pathlib import Path

import pytest

from factiz_site import app as fa
from factiz_site import db as fdb
from factiz_site import gelijk, i18n
from tests.schriften import PANEEL
from tests.test_factiz_dossiers import _site
from tests.test_factiz_namen import _site as _namensite
from tests.test_factiz_eigen import _site as _eigensite

SITE = Path(__file__).resolve().parent.parent / "site"
LIJSTEN = gelijk.KLAAR


def _node(script, *args, invoer):
    uit = subprocess.run(["node", f"scripts/{script}", *map(str, args)], input=json.dumps(invoer, ensure_ascii=False),
                         capture_output=True, text=True, cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def verschillen(client, adressen):
    return gelijk.verschillen(client, client.bestand, adressen)


@pytest.fixture(scope="module")
def met_dossiers(tmp_path_factory):
    return _site(tmp_path_factory)[0]


@pytest.fixture(scope="module")
def zonder_dossiers(tmp_path_factory):
    return _site(tmp_path_factory, met_dossiers=False)[0]


def test_the_list_pages_answer_the_same_in_every_language(met_dossiers):
    adressen = [f"/api/{taal}/{ingang}" for taal in i18n.TALEN for ingang in LIJSTEN if ingang != "archief"]
    assert verschillen(met_dossiers, adressen) == []


def test_the_list_with_every_filter_order_page_and_refusal_answers_the_same(met_dossiers):
    pub = fdb.Publicatie(met_dossiers.bestand)
    adressen = [f"/api/{taal}/archief{v}" for taal in ("en", "nl", "hi", "ar") for v in gelijk.lijstvragen(pub)]
    assert verschillen(met_dossiers, adressen) == []


def test_a_release_without_dossiers_and_paths_that_do_not_exist_give_the_same_404(zonder_dossiers):
    adressen = ["/api/en/dossiers", "/api/nl/dossiers", "/api/en/onbekend", "/api/xx/bronnen", "/api/en/bronnen/extra",
                "/api/en/themas"]
    assert verschillen(zonder_dossiers, adressen) == []


def test_the_text_helpers_count_and_sort_like_python_in_every_script():
    teksten = list(PANEEL.values()) + ["🙂" * 30 + " eind", "a, b, c; " * 40, "", "één  twee　drie vier"]
    for n in (5, 12, 40, 220):
        assert _node("platform-functie.ts", "kort", invoer=[[t, n] for t in teksten]) == [fa._kort(t, n) for t in teksten]
    data = ["2024-03-05", "2024-01-01", "2024-00-10", "2024-13-01", "2024-03-32", "2024-03", "", "x-y-z", " 2024-3-5"]
    for taal in i18n.TALEN:
        assert _node("platform-functie.ts", "datum", invoer=[[taal, d] for d in data]) == [i18n.datum(taal, d) for d in data]
        assert _node("platform-functie.ts", "getal", invoer=[[taal, n] for n in (0, 7, 999, 1000, 106073, 1234567)]) == [
            i18n.getal(taal, n) for n in (0, 7, 999, 1000, 106073, 1234567)]
    filters = [{"redactie": "Fact Crescendo (Sri Lanka) & co*~"}, {"taal": ["hi", "en"], "jaar": "2024"},
               {"redactie": "مسبار", "thema": "war"}, {}]
    for taal in ("en", "nl", "pt"):
        assert _node("platform-functie.ts", "lijstUrl", invoer=[[taal, f] for f in filters]) == [
            fa.lijst_url(taal, f) for f in filters]


def test_names_a_name_every_theme_and_every_dossier_answer_the_same_in_every_language(met_dossiers):
    pub = fdb.Publicatie(met_dossiers.bestand)
    adressen = [f"/api/{taal}/{a}" for taal in i18n.TALEN for a in gelijk.ingangsadressen(pub) + ["namen"]]
    assert verschillen(met_dossiers, adressen) == []


@pytest.mark.parametrize("concept", [False, True])
def test_a_release_with_names_answers_the_same_for_the_register_every_letter_and_every_name(tmp_path_factory, concept):
    client = _namensite(tmp_path_factory, concept=concept)[0]
    pub = fdb.Publicatie(client.bestand)
    adressen = [f"/api/{taal}/{a}" for taal in i18n.TALEN for a in gelijk.ingangsadressen(pub) + ["namen"]]
    adressen += [f"/api/{taal}/archief{v}" for taal in ("en", "ru") for v in gelijk.lijstvragen(pub)]
    assert verschillen(client, adressen) == []


def test_counting_a_visit_answers_the_same_and_counts_only_day_kind_and_language(met_dossiers):
    vorm = "application/x-www-form-urlencoded"
    verzoeken = [{"pad": "/api/tel", "methode": "POST", "bericht": "soort=factcheck&taal=nl&robot=0"},
                 {"pad": "/api/tel", "methode": "POST", "bericht": "soort=start&taal=en&robot=1"},
                 {"pad": "/api/tel", "methode": "POST", "bericht": "soort=geheim&taal=nl"},
                 {"pad": "/api/tel", "methode": "POST", "bericht": "soort=start&taal=xx"},
                 {"pad": "/api/tel", "methode": "POST", "bericht": ""}, "/api/tel"]
    assert verschillen(met_dossiers, verzoeken) == [], vorm
    script = """
import { antwoord, zetTeller } from './src/platform/api.ts';
import { openDb } from './scripts/platform-node.ts';
const geteld = [];
zetTeller((dag, wat, taal) => geteld.push([dag.length, wat, taal]));
const db = openDb(process.argv[1]);
for (const b of ['soort=factcheck&taal=nl&robot=0', 'soort=start&taal=en&robot=1', 'soort=geheim&taal=nl']) {
  await antwoord(db, '/api/tel', new URLSearchParams(), { methode: 'POST', bericht: b });
}
process.stdout.write(JSON.stringify(geteld));
"""
    uit = subprocess.run(["node", "--input-type=module", "-e", script, str(met_dossiers.bestand)], capture_output=True,
                         text=True, cwd=SITE, timeout=120)
    assert uit.returncode == 0, uit.stderr[-2000:]
    assert json.loads(uit.stdout) == [[10, "factcheck", "nl"], [10, "robot", "en"]]


def test_saved_memory_comes_back_exactly_with_shared_objects_still_shared():
    script = """
import { bewaar, lees } from './src/platform/geheugen.ts';
const gedeeld = { naam: 'Zelensky', _x: 1, __y: 2, _v: 3 };
const waarde = { lijst: [gedeeld, gedeeld], kaart: new Map([['a', gedeeld], [1, new Set([gedeeld, 'b'])]]),
  rij: Int32Array.from([1, -2, 3]), getallen: Float64Array.from([-0, NaN, Infinity, 0.1]), los: [-0, NaN, -Infinity, undefined],
  diep: { '2024': 'jaar', b: null } };
const terug = lees(bewaar(waarde));
const uit = {
  zelfde: terug.lijst[0] === terug.lijst[1] && terug.kaart.get('a') === terug.lijst[0] && [...terug.kaart.get(1)][0] === terug.lijst[0],
  sleutels: Object.keys(terug.lijst[0]), rij: terug.rij instanceof Int32Array && [...terug.rij].join(),
  getallen: [...terug.getallen].map((x) => Object.is(x, -0) ? '-0' : String(x)), los: terug.los.map((x) => Object.is(x, -0) ? '-0' : String(x)),
  diep: terug.diep,
};
process.stdout.write(JSON.stringify(uit));
"""
    uit = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, cwd=SITE, timeout=120)
    assert uit.returncode == 0, uit.stderr[-2000:]
    assert json.loads(uit.stdout) == {
        "zelfde": True, "sleutels": ["naam", "_x", "__y", "_v"], "rij": "1,-2,3",
        "getallen": ["-0", "NaN", "Infinity", "0.1"], "los": ["-0", "NaN", "-Infinity", "undefined"],
        "diep": {"2024": "jaar", "b": None}}


def test_with_the_memory_computed_beforehand_every_answer_stays_the_same(met_dossiers, tmp_path, monkeypatch):
    map_ = tmp_path / "geheugen"
    uit = subprocess.run(["node", "scripts/geheugen.ts", str(met_dossiers.bestand), str(map_), "--alles"], capture_output=True, text=True,
                         cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    assert json.loads((map_ / "index.json").read_text(encoding="utf-8"))["stukken"]
    monkeypatch.setenv("FACTIZ_GEHEUGEN", str(map_))
    pub = fdb.Publicatie(met_dossiers.bestand)
    adressen = [f"/api/{taal}/{a}" for taal in ("en", "ar", "zh") for a in gelijk.ingangsadressen(pub) + ["namen", "themas"]]
    adressen += [f"/api/en/archief{v}" for v in gelijk.lijstvragen(pub)]
    adressen += [{"pad": "/api/en/zoek", "methode": "POST", "bericht": b} for b in ("q=Zelensky", "q=villa+florida", "q=zel")]
    assert verschillen(met_dossiers, adressen) == []


def test_the_link_addresses_stay_compact_enough_for_a_worker(met_dossiers, tmp_path):
    """Een Worker heeft 128 MB (PLAN #34.2bo stap 8). De adressen van de links kostten 19 MB: daarom vingerafdrukken. Dit
    houdt die vorm vast, ook in het geheugen dat de Worker leest. De woordenlijst staat sinds #37.16 als tabel `woord` in de
    uitgave en niet meer in het geheugen (met elke vertaling waren het 1,4 miljoen woorden)."""
    map_ = tmp_path / "geheugen"
    uit = subprocess.run(["node", "scripts/geheugen.ts", str(met_dossiers.bestand), str(map_), "--alles"], capture_output=True,
                         text=True, cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    stukken = {s["naam"]: s["bestand"] for s in json.loads((map_ / "index.json").read_text(encoding="utf-8"))["stukken"]}
    assert "zoeken:woordtabel" not in stukken
    adressen = json.loads((map_ / stukken["zoeken:adresafdrukken"]).read_text(encoding="utf-8"))
    assert {adressen[k]["_r"] for k in ("hoog", "laag", "pagina")} == {"Uint32Array"}
    assert not {"zoeken:woorden", "zoeken:voorvoegsels", "zoeken:adressen"} & set(stukken)
    # de kolommen: alleen de kern, met de nummers als één tekst, geen datums, en de volgordes van de lijst al gesorteerd;
    # een code die in een byte past, staat in een byte
    assert "kolommen" not in stukken
    kern = json.loads((map_ / stukken["kolommen:kern"]).read_text(encoding="utf-8"))
    assert isinstance(kern["nummers"], str) and len(kern["nummers"]) == 16 * kern["n"]
    assert not {"nummer", "plek", "datum"} & set(kern)
    assert {k for k, _ in kern["volgorde"]["_m"]} == {"nieuw", "oud", "redacties"}
    assert kern["kolom"]["taal"].get("k") == "Int8Array"


def test_the_own_fact_checks_answer_the_same_in_every_language(tmp_path_factory):
    client, _ = _eigensite(tmp_path_factory)
    adressen = [f"/api/{taal}/eigen" for taal in i18n.TALEN] + [f"/api/{taal}/eigen/proef" for taal in i18n.TALEN] + [
        "/api/nl/eigen/gepubliceerd", "/api/en/eigen/gepubliceerd", "/api/nl/eigen/onbekend", "/api/nl/eigen/Proef", "/api/nl/eigen/proef/extra"]
    # het adres met jaar en maand, de Radar per jaar en maand, en de naam van een andere taal (PLAN #37.11)
    adressen += ["/api/nl/eigen/2026", "/api/en/eigen/2026", "/api/nl/eigen/2026/12", "/api/en/eigen/2026/12",
                 "/api/nl/eigen/2025", "/api/nl/eigen/2026/11", "/api/nl/eigen/2026/13", "/api/nl/eigen/2026/00",
                 "/api/nl/eigen/26", "/api/nl/eigen/2026/1", "/api/nl/eigen/2026/12/gepubliceerd-check-nl",
                 "/api/en/eigen/2026/12/gepubliceerd-check-en", "/api/en/eigen/2026/12/gepubliceerd-check-nl",
                 "/api/nl/eigen/2026/12/gepubliceerd-check-en", "/api/de/eigen/2026/12/gepubliceerd-check-en",
                 "/api/nl/eigen/2026/12/standbeeld-anne-frank-ai", "/api/nl/eigen/2026/12/onbekend-adres",
                 "/api/nl/eigen/2026/12/gepubliceerd-check-nl/extra"]
    # en in het archief, als redactie Factiz: de lijst, het filter, de pagina en de redacties (#37.4, SPECS E10.S4 AC2)
    from doublecheck import publiceren as pb
    adressen += [f"/api/{taal}/archief" for taal in i18n.TALEN] + [
        "/api/nl/archief?redactie=Factiz", "/api/en/archief?redactie=Factiz", "/api/nl/redacties", "/api/pt/redacties",
        f"/api/nl/factcheck/{pb.nummer('factiz-proef')}", f"/api/en/factcheck/{pb.nummer('factiz-proef')}",
        f"/api/fa/factcheck/{pb.nummer('factiz-gepubliceerd')}"]
    assert verschillen(client, adressen) == []
