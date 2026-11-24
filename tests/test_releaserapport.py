"""Het releaserapport uit de metingen (PLAN #23.10).

Tot de lancering is de aankondiging een gegenereerd rapport (PO 2026-10-12).
Het vult het skelet uit RELEASES.md met wat gemeten is, en weigert waar de
vergelijking niet eerlijk is: twee runs op verschillende testparen, of een
run die niet met de motor uit `config.toml` gemaakt is.
"""

import dataclasses
import json

import pytest

from doublecheck import releaserapport as rr
from doublecheck.benchmark import upper_bound_95
from doublecheck.config import VariantSettings, load_config
from doublecheck.storage import connect, init_schema

VARIANTEN = "claude-haiku-5-5/vertalingen-v1 · 460698 varianten"
KAART = """# Releases

## Huidige release

### Factiz 7 (proef, 2026-10)

| protocol | protocol v0.1 (concept) |

**Wat slechter werd.** Zoeken werd trager: p95 van 24 naar 223 ms.

**Wat niet werkt.** Een bijgesneden beeld verslaat beide hashes.

## Richting in releases

Factiz 8 doet alles beter.
"""


def taal(paren, zelfde, fout, goed):
    return {"pairs": paren, "same_pairs": zelfde, "wrong_links": fout, "correct_matches": goed}


VOOR = {"nl": taal(500, 250, 0, 200), "en": taal(100, 50, 1, 40), "crosslinguaal": taal(50, 50, 0, 40)}
NA = {"nl": taal(500, 250, 0, 210), "en": taal(100, 50, 2, 40), "crosslinguaal": taal(50, 50, 0, 46)}


def _config(varianten=True):
    return dataclasses.replace(load_config(), varianten=VariantSettings(in_resolver=varianten))


def _run(conn, run_id, per_taal, config, variant_set="", **anders):
    waarden = dict(
        run_id=run_id, started_at=f"2026-10-{run_id:02d}T10:00:00+00:00",
        text_match=config.thresholds.text_match, text_related=config.thresholds.text_related,
        image_same=config.thresholds.image_same, model_version_text=config.model_versions.text_embedding,
        model_version_image=config.model_versions.image_hash, results_per_language=json.dumps(per_taal),
        variant_set=variant_set,
        **{k: sum(v[k] for v in per_taal.values()) for k in ("pairs", "same_pairs", "wrong_links", "correct_matches")},
    )
    waarden.update(anders)
    conn.execute(f"INSERT INTO benchmark_run ({', '.join(waarden)}) VALUES ({', '.join('?' * len(waarden))})",
                 tuple(waarden.values()))


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    config = _config()
    _run(conn, 3, VOOR, config)
    _run(conn, 4, NA, config, variant_set=VARIANTEN)
    return conn


def _maak(conn, tmp_path, voor=3, na=4, config=None, conformantie=None):
    pad = tmp_path / "conformance-latest.json"
    if conformantie is not None:
        pad.write_text(json.dumps(conformantie), encoding="utf-8")
    return rr.rapport(conn, config or _config(), voor, na, kaart=KAART, conformantie_pad=str(pad))


def _sectie(tekst, kop):
    return tekst.split(f"## {kop}")[1].split("\n## ")[0]


def test_the_sentence_compares_coverage_and_error_bound_on_the_same_pairs(conn, tmp_path):
    tekst = _maak(conn, tmp_path)
    assert tekst.startswith("# Factiz 7 release report")
    assert (f"Coverage from 80.0% to 84.6% on the same 650 test pairs in 2 languages, with the error "
            f"bound from {upper_bound_95(1, 650):.2%} to {upper_bound_95(2, 650):.2%}.") in tekst
    assert "Across languages: coverage from 80.0% to 92.0% on 50 pairs" in tekst


def test_a_language_with_more_errors_is_named_under_what_got_worse(conn, tmp_path):
    slechter = _sectie(_maak(conn, tmp_path), "What got worse, and what we still miss")
    assert "en: errors from 1 to 2" in slechter
    assert "nl" not in slechter.split("Still missing")[0]


def test_what_got_worse_is_never_empty(tmp_path):
    """Regel 2: werd er niets slechter, dan staat er wat nog niet werkt."""
    conn = connect(":memory:")
    init_schema(conn)
    config = _config(varianten=False)
    _run(conn, 5, VOOR, config)
    _run(conn, 6, VOOR, config)
    slechter = _sectie(_maak(conn, tmp_path, 5, 6, config=config), "What got worse, and what we still miss")
    assert "Nothing got worse between run #5 and run #6." in slechter
    assert "We do not find 70 of the 350 test pairs whose claim is known (20.0%)." in slechter
    assert "Lowest coverage: en 80.0%, nl 80.0%." in slechter


def test_the_card_on_what_got_worse_comes_along_verbatim(conn, tmp_path):
    """Regel 2 eist de missers in de aankondiging zelf, niet in een verwijzing;
    wat de runs niet meten (snelheid, geheugen) staat op de kaart."""
    tekst = _maak(conn, tmp_path)
    assert "Zoeken werd trager: p95 van 24 naar 223 ms." in tekst
    assert "Een bijgesneden beeld verslaat beide hashes." in tekst
    assert "Factiz 8 doet alles beter." not in tekst


def test_runs_on_different_test_pairs_are_refused(conn, tmp_path):
    _run(conn, 5, {**NA, "nl": taal(400, 200, 0, 170)}, _config(), variant_set=VARIANTEN)
    with pytest.raises(rr.OnvergelijkbareRuns, match="nl"):
        _maak(conn, tmp_path, 3, 5)


def test_a_language_new_in_the_later_run_is_shown_but_not_compared(conn, tmp_path):
    """B14: een nieuwe markt heeft geen vóórcijfer; de zin vergelijkt alleen
    de paren die beide runs maten."""
    _run(conn, 5, {**NA, "ta": taal(200, 100, 0, 82)}, _config(), variant_set=VARIANTEN)
    tekst = _maak(conn, tmp_path, 3, 5)
    assert "on the same 650 test pairs in 2 languages" in tekst
    assert "New in run #5: ta (200 pairs, coverage 82.0%" in tekst


@pytest.mark.parametrize("anders", [dict(text_match=0.5), dict(model_version_text="ander-model"),
                                    dict(variant_set="")])
def test_a_run_not_made_with_the_engine_in_config_is_refused(conn, tmp_path, anders):
    """Een rapport over een run die niet de motor van nu is, misleidt."""
    _run(conn, 5, NA, _config(), **{"variant_set": VARIANTEN, **anders})
    with pytest.raises(rr.AndereMotor):
        _maak(conn, tmp_path, 3, 5)


def test_engine_changes_between_runs_are_listed(conn, tmp_path):
    motor = _sectie(_maak(conn, tmp_path), "What changed in the engine")
    assert f"claim variants: none to `{VARIANTEN}`" in motor
    conn2 = connect(":memory:")
    init_schema(conn2)
    config = _config(varianten=False)
    _run(conn2, 5, VOOR, config)
    _run(conn2, 6, VOOR, config)
    motor = _sectie(_maak(conn2, tmp_path, 5, 6, config=config), "What changed in the engine")
    assert "Nothing the runs record changed" in motor


def test_conformance_is_read_from_its_output_never_assumed(conn, tmp_path):
    zonder = _sectie(_maak(conn, tmp_path), "For implementers")
    assert "No conformance output found" in zonder
    met = _sectie(_maak(conn, tmp_path, conformantie={
        "conformant": True, "complete": False,
        "results": [{"obligation": 3, "name": "x", "status": "not observed", "note": ""},
                    {"obligation": 10, "name": "y", "status": "passed", "note": ""}]}),
        "For implementers")
    assert "conformant, not fully tested: obligation 3 unobserved" in met
    assert "Protocol: v0.1" in met
