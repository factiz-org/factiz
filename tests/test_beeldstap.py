"""De beeldstap (PLAN #32.35, deel 2 van het releasevoorstel): het beeld van een screenshot bevestigt checks via de
punten van de virale beelden in de factcheckartikelen. Lokaal; het beeld van de gebruiker gaat nergens heen."""

import io
import json

import numpy as np
import pytest

from doublecheck import beeldstap as bs
from doublecheck import beeldvraag as bv
from doublecheck import zoekcontrole as zc
from tests.beelden import kop_screenshot, vormen

VERSIES = {"punten": bv.PUNTVERSIE, "vergelijking": bv.VERGELIJKING, "rol": "rol-v3", "tekst": "bge-m3@test"}


def _bytes(beeld) -> bytes:
    uit = io.BytesIO()
    beeld.save(uit, format="PNG")
    return uit.getvalue()


def _index(tmp_path, beelden: dict[str, list], teksten: list[tuple[str, list[float]]] = (), versies=VERSIES):
    """Een kleine index op schijf, zoals `beeldindexbouw` haar schrijft: per viraal beeld PDQ en de punten."""
    (tmp_path / "punten").mkdir()
    rijen = []
    for artikel, lijst in beelden.items():
        for i, beeld in enumerate(lijst):
            kenm = bs.beeldkenmerken(_bytes(beeld))
            pad = f"punten/{abs(hash((artikel, i)))}.npz"
            (tmp_path / pad).write_bytes(bv.punten_naar_bytes(kenm["punten"]))
            rijen.append({"adres": bs.adres(artikel), "artikel": artikel, "beeld": f"{artikel}/b{i}.jpg",
                          "pdq": kenm["pdq"], "kwaliteit": kenm["kwaliteit"], "punten": pad})
    (tmp_path / "beelden.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rijen))
    (tmp_path / "versies.json").write_text(json.dumps(versies))
    if teksten:
        (tmp_path / "teksten.jsonl").write_text("".join(json.dumps({"adres": bs.adres(a)}) + "\n" for a, _ in teksten))
        np.save(tmp_path / "teksten.npy", np.array([v for _, v in teksten], dtype=np.float32))
    return bs.laad(tmp_path, VERSIES)


def test_the_index_refuses_other_versions_of_the_points_or_the_rol():
    with pytest.raises(bs.Versiefout):
        bs.controleer_versies({**VERSIES, "punten": "sift-500-v0"}, VERSIES)
    with pytest.raises(bs.Versiefout):
        bs.controleer_versies({**VERSIES, "rol": "rol-v2"}, VERSIES)
    bs.controleer_versies(dict(VERSIES), VERSIES)


def test_candidates_are_the_articles_of_the_checks_and_the_best_texts_on_viral_images(tmp_path):
    index = _index(tmp_path, {}, teksten=[("https://a.org/x", [1, 0]), ("https://b.org/y", [0, 1]),
                                          ("https://c.org/z", [0.7, 0.7])])
    checks = [{"url": "https://www.factly.in/een/"}]
    uit = bs.kandidaten(checks, np.array([1.0, 0.0], dtype=np.float32), index, top=2)
    assert list(uit) == ["factly.in/een", "a.org/x", "c.org/z"]
    assert uit["factly.in/een"] == {"check"} and uit["a.org/x"] == {"beeldtekst"}


def test_the_same_viral_image_confirms_and_another_image_does_not(tmp_path):
    viraal = kop_screenshot(["Old photo shared as new", "flood in the city"], hoogte=300)
    index = _index(tmp_path, {"https://a.org/x": [viraal], "https://b.org/y": [vormen(3, 400, 300)]})
    vraag = bs.beeldkenmerken(_bytes(viraal))
    drempels = {"drempel_pdq": 31, "min_punten": 50, "min_dekking": 0.10}
    assert bs.bevestigde_artikelen(vraag, ["a.org/x", "b.org/y", "c.org/geen"], index, **drempels) == ["a.org/x"]


def test_points_of_another_version_are_never_compared(tmp_path):
    index = _index(tmp_path, {"https://a.org/x": [vormen(1, 400, 300)]})
    vraag = bs.beeldkenmerken(_bytes(vormen(1, 400, 300)))
    vraag["punten"] = {**vraag["punten"], "versie": "sift-500-v0"}
    with pytest.raises(bv.Versiefout):
        bs.bevestigde_artikelen(vraag, ["a.org/x"], index, drempel_pdq=-1, min_punten=50, min_dekking=0.1)


def test_a_confirmed_check_gets_the_image_sentence_and_one_outside_the_five_is_added():
    checks = [{"claim": "c1", "url": "https://a.org/x", "beeld": False}, {"claim": "c2", "url": "https://b.org/y"}]
    extra = {"claim": "c3", "url": "https://c.org/z", "tekst": "t", "redactie": "R", "oordeel": "onwaar", "datum": "d"}
    uit = bs.met_beeld(checks, ["a.org/x", "c.org/z"], lambda a: [extra] if a == "c.org/z" else [])
    assert [(k["claim"], k["beeld"]) for k in uit] == [("c1", True), ("c2", False), ("c3", True)]
    assert bs.met_beeld(checks, [], lambda a: []) == [{**k, "beeld": False} for k in checks]


def test_the_address_is_the_one_the_database_and_the_harvest_use():
    from doublecheck.eigenaanvoer import adres
    for url in ("https://www.Factly.in/a//b/?x=1", "http://snopes.com/fact-check/x/", "https://t.co"):
        assert bs.adres(url) == adres(url)


def test_the_step_is_off_by_default_and_refuses_to_be_on_without_its_versions(tmp_path):
    from doublecheck.config import ConfigError, load_config

    from pathlib import Path

    assert load_config().beeldstap.aan is False
    bron = Path("config.toml").read_text(encoding="utf-8")
    pad = tmp_path / "config.toml"
    aangezet = bron.replace('aan = false\nindex = "data/beeldindex-vol"', 'aan = true\nindex = ""')
    assert aangezet != bron
    pad.write_text(aangezet, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(pad)


def test_the_check_lets_the_image_step_mark_checks_beside_the_search_and_only_when_it_is_on():
    import dataclasses
    import sqlite3

    from tests.test_zoekcontrole import BERICHT, PNG, SITES, NepModel, _brave, _config

    gevraagd = []

    def stap(beeld, bericht, checks):
        gevraagd.append((beeld, bericht))
        return [{**k, "beeld": True} for k in checks]

    checks = [{"claim": "c1", "tekst": "Old photo", "redactie": "BOOM", "oordeel": "onwaar", "datum": "2020-01-01",
               "url": "https://www.boomlive.in/x/", "beeld": False}]
    zoek = lambda q: _brave("https://www.nytimes.com/a")  # noqa: E731
    for aan in (False, True):
        config = _config(lezer="lezer-v7")
        config = dataclasses.replace(config, beeldstap=dataclasses.replace(config.beeldstap, aan=aan))
        nep = NepModel()
        bs_checks = list(checks)
        zc.controleer(
            sqlite3.connect(":memory:"), BERICHT, config, nep, zoek, lambda t: None, SITES, None, beeld=PNG,
            checks=bs_checks, beeldstap=stap)
        inhoud = nep.verzoeken[-1]["messages"][0]["content"]
        tekst = inhoud if isinstance(inhoud, str) else inhoud[-1]["text"]
        assert (zc.BEELDZIN in tekst) is aan
    assert gevraagd == [(PNG, BERICHT)]


def test_the_whole_step_confirms_from_the_index_and_brings_the_check_of_an_article_outside_the_five(tmp_path):
    import dataclasses

    from doublecheck.config import load_config

    viraal = kop_screenshot(["Old photo shared as new", "flood in the city"], hoogte=300)
    index = _index(tmp_path, {"https://c.org/z": [viraal]}, teksten=[("https://c.org/z", [1.0, 0.0])])
    index.checks = {"c.org/z": [{"claim": "c3", "tekst": "Old flood photo", "redactie": "R", "oordeel": "onwaar",
                                 "datum": "2020-01-01", "url": "https://c.org/z"}]}
    instellingen = dataclasses.replace(load_config().beeldstap, top_beeldtekst=1)
    checks = [{"claim": "c1", "tekst": "x", "redactie": "B", "oordeel": "onwaar", "datum": "d", "url": "https://a.org/x"}]
    uit = bs.bevestig_checks(_bytes(viraal), np.array([1.0, 0.0], dtype=np.float32), checks, index, instellingen)
    assert [(k["claim"], k["beeld"]) for k in uit] == [("c1", False), ("c3", True)]
