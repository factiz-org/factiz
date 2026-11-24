"""Zoeken in de eigen taal (PLAN #37.16, na B93; PO 2026-11-23: "Ja, bouw het"): elke vertaling, ook een voorlopige, in
het register op woorden, de Chinese en Japanse ook in dat op drietallen; de woordenlijst als tabel `woord` in de uitgave
in plaats van in het geheugen van de Worker (128 MB); en een zoekvraag die niet vaker heen en weer gaat naar de database
omdat ze meer woorden heeft."""

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db as fdb
from factiz_site import gelijk
from tests.test_publiceren import REGISTER, _check, _claim, _lab

SITE = Path(__file__).resolve().parent.parent / "site"


def _bouw(map_):
    map_.mkdir(parents=True, exist_ok=True)
    lab = _lab(map_)
    dna = _claim(lab, 1, "A vaccine changes your DNA.")
    chip = _claim(lab, 2, "The vaccine contains a microchip.")
    straat = _claim(lab, 3, "The street was closed for the vaccine protest.")
    for n, (c, url) in enumerate(((dna, "https://snopes.com/dna"), (chip, "https://snopes.com/chip"),
                                  (straat, "https://snopes.com/straat"))):
        _check(lab, c, url, datum=f"2025-0{n + 1}-01")
    lab.commit()
    nr = {k: pb.nummer(c) for k, c in (("dna", dna), ("chip", chip), ("straat", straat))}
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-24",
                vertalingen={"es": {nr["dna"]: "Una vacuna cambia tu ADN."},
                             "ja": {nr["dna"]: "ワクチンがDNAを変える。"},
                             "de": {nr["straat"]: "Die Straße wurde für den Impfprotest gesperrt."}},
                vertaalmaker="weergave",
                voorlopig={"pt": {nr["dna"]: "Uma vacina altera o seu DNA.", nr["chip"]: "A vacina contém um microchip."}},
                voorlopig_maker={"pt": "claude-haiku-5-5, weergave-v6"})
    return m["bestand"], nr


@pytest.fixture(scope="module")
def uitgave(tmp_path_factory):
    bestand, nr = _bouw(tmp_path_factory.mktemp("vertaald"))
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    client.bestand, client.nr = bestand, nr
    return client


def _nummers(client, taal, q):
    r = client.post(f"/api/{taal}/zoek", data={"q": q})
    assert r.status_code == 200
    return [rij["href"].rstrip("/").rsplit("/", 1)[-1] for rij in r.json()["rijen"]]


def test_a_translation_finds_its_fact_check_also_while_it_is_provisional(uitgave):
    nr = uitgave.nr
    assert nr["dna"] in _nummers(uitgave, "pt", "vacina altera")          # voorlopig (B93), toch vindbaar op de site
    assert nr["dna"] in _nummers(uitgave, "es", "vacuna")                  # een geldige vertaling, zoals altijd
    # Japans heeft geen spaties: het zoekt in het register op drietallen, waar de Japanse vertaling nu ook staat
    assert nr["dna"] in _nummers(uitgave, "ja", "ワクチン")
    assert nr["straat"] in _nummers(uitgave, "de", "Straße")


def test_the_word_table_is_the_vocabulary_of_the_search_register(uitgave):
    c = sqlite3.connect(uitgave.bestand)
    c.execute("CREATE VIRTUAL TABLE temp.v USING fts5vocab(main, zoek, row)")
    register = dict(c.execute("SELECT term, doc FROM temp.v"))
    woord = {t: (d, n, k, g) for t, d, n, k, g in c.execute("SELECT term, doc, lengte, kandidaat, gewoon FROM woord")}
    assert {t: d for t, (d, *_rest) in woord.items()} == register
    assert woord["vaccine"][2] == 1 and woord["microchip"][2] == 0           # een kandidaat staat in minstens twee beweringen
    assert woord["vacina"][0] == 2                                          # de voorlopige vertalingen tellen mee
    assert woord["straße"][3] == "strasse" and woord["vaccine"][3] is None   # bijzondere letters: hoe iemand ze zonder typt
    assert woord["vaccine"][1] == len("vaccine")


def test_the_check_refuses_a_word_table_that_does_not_match_the_register(uitgave, tmp_path):
    kopie = tmp_path / "kopie.db"
    kopie.write_bytes(Path(uitgave.bestand).read_bytes())
    c = sqlite3.connect(kopie)
    c.execute("DELETE FROM woord WHERE term = 'vacina'")
    c.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(c),))
    c.commit()
    c.close()
    with pytest.raises(pb.Weigering, match="woord"):
        pb.controleer(kopie)


def test_typescript_answers_the_same_with_the_word_list_in_the_database(uitgave):
    zoek = ["vacina", "vacina altera", "ワクチン", "vacuna", "vaccnie", "strasse", "Straße", "vaccine dna", "vac", "microchips"]
    adressen = [{"pad": f"/api/{taal}/zoek", "methode": "POST", "bericht": f"q={q}"} for taal in ("en", "pt", "ja") for q in zoek]
    adressen += [{"pad": f"/api/{taal}/suggesties", "methode": "POST", "bericht": f"q={q}"}
                 for taal in ("en", "pt") for q in ("vac", "vacc", "vaci", "stras", "micro", "vaccine d")]
    assert gelijk.verschillen(uitgave, uitgave.bestand, adressen) == []


def test_the_memory_of_a_worker_no_longer_holds_the_word_list(uitgave, tmp_path):
    map_ = tmp_path / "geheugen"
    uit = subprocess.run(["node", "scripts/geheugen.ts", str(uitgave.bestand), str(map_), "--alles"], capture_output=True,
                         text=True, cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    stukken = {s["naam"] for s in json.loads((map_ / "index.json").read_text(encoding="utf-8"))["stukken"]}
    assert not {s for s in stukken if "woord" in s}


def _rondes(bestand, geheugen, pad, q):
    v = json.dumps({"pad": pad, "methode": "POST", "bericht": f"q={q}"})
    uit = subprocess.run(["node", "scripts/rondes.ts", str(bestand), str(geheugen), v], capture_output=True, text=True,
                         cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    return json.loads(uit.stdout)


def test_more_words_or_more_completions_do_not_mean_more_trips_to_the_database(uitgave, tmp_path):
    """De stukken van een vraag en de aanvullingen van een suggestie gaan tegelijk naar de database (`bundel.js`), niet
    na elkaar: een tweede woord kost geen extra keer heen en weer."""
    map_ = tmp_path / "geheugen"
    uit = subprocess.run(["node", "scripts/geheugen.ts", str(uitgave.bestand), str(map_)], capture_output=True, text=True,
                         cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    een = _rondes(uitgave.bestand, map_, "/api/en/zoek", "vaccine")
    twee = _rondes(uitgave.bestand, map_, "/api/en/zoek", "vaccine protest")
    assert twee["warm"] <= een["warm"], (een, twee)


def test_the_memory_builder_and_the_worker_build_use_one_list_of_what_must_be_in_memory():
    """Twee kopieën van die lijst liepen uit elkaar (2026-11-23: de Worker-bouw eiste de woordenlijst nog, die #37.16 uit het
    geheugen haalde). Eén bestand, en de woordenlijst staat er niet in."""
    scripts = SITE / "scripts"
    lijst = (scripts / "geheugen-nodig.mjs").read_text(encoding="utf-8")
    assert "export const NODIG" in lijst and "woordtabel" not in lijst.split("export const NODIG")[1]
    for naam in ("geheugen.ts", "worker-voorraad.mjs"):
        tekst = (scripts / naam).read_text(encoding="utf-8")
        assert "from './geheugen-nodig.mjs'" in tekst and "const NODIG = [" not in tekst, naam


def test_a_typo_takes_its_candidates_from_the_memory_and_not_thousands_of_words_from_the_database(uitgave, tmp_path,
                                                                                                  monkeypatch):
    """De kandidaten per beginletter staan vooraf in het geheugen (`zoeken:tikfout:<letter>`): live haalde `presidnet` er
    ~9.000 woorden voor uit D1 en duurde 817 in plaats van 520 ms. Het antwoord blijft dat van Python."""
    map_ = tmp_path / "geheugen"
    uit = subprocess.run(["node", "scripts/geheugen.ts", str(uitgave.bestand), str(map_)], capture_output=True, text=True,
                         cwd=SITE, timeout=300)
    assert uit.returncode == 0, uit.stderr[-2000:]
    stukken = {s["naam"] for s in json.loads((map_ / "index.json").read_text(encoding="utf-8"))["stukken"]}
    assert {"zoeken:tikfout:v", "zoeken:tikfout:t"} <= stukken
    v = json.dumps({"pad": "/api/en/zoek", "methode": "POST", "bericht": "q=vaccnie"})
    uit = subprocess.run(["node", "scripts/rondes.ts", str(uitgave.bestand), str(map_), v], capture_output=True, text=True,
                         cwd=SITE, timeout=300, env={**__import__("os").environ, "RONDES_TOON": "1"})
    assert uit.returncode == 0, uit.stderr[-2000:]
    assert "kandidaat = 1 ORDER BY lengte" not in uit.stderr          # ook niet bij een Worker die net begint
    monkeypatch.setenv("FACTIZ_GEHEUGEN", str(map_))
    adressen = [{"pad": f"/api/{taal}/zoek", "methode": "POST", "bericht": f"q={q}"} for taal in ("en", "pt")
                for q in ("vaccnie", "microchp", "vacinna", "strase")]
    assert gelijk.verschillen(uitgave, uitgave.bestand, adressen) == []
