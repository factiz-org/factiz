"""Modelvergelijking op natuurlijke parafrasen (PLAN #25.14).

Elk model heeft zijn eigen gelijkenisschaal: 0,92 betekent bij het ene model
iets anders dan bij het andere. Een eerlijke vergelijking legt daarom geen
drempel op, maar vraagt per model: hoeveel vind je terug bij hetzelfde
foutniveau? En elk model krijgt precies dezelfde pool, anders meet de
vergelijking de pool in plaats van het model.
"""

import re

import numpy as np
import pytest

from doublecheck import modelmeting as mm


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_every_group_claim_is_in_the_pool_and_the_pool_is_reproducible():
    groepen = [{"a1", "a2"}, {"b1", "b2", "b3"}]
    alle = [f"x{i}" for i in range(100)] + ["a1", "a2", "b1", "b2", "b3"]
    pool = mm.kies_pool(groepen, alle, n=10, seed=7)
    assert {"a1", "a2", "b1", "b2", "b3"} <= set(pool)
    assert len(pool) == 15
    assert pool == mm.kies_pool(groepen, list(reversed(alle)), n=10, seed=7)
    assert pool != mm.kies_pool(groepen, alle, n=10, seed=8)


def test_the_partner_must_beat_every_distractor_and_a_tie_is_not_found():
    ids = ["A", "B", "C", "D"]
    matrix = np.vstack([_v(1, 0, 0), _v(0.9, 0.44, 0), _v(0.8, 0, 0.6), _v(0, 1, 0)])
    taal = dict.fromkeys(ids, "nl")
    vragen = mm.herkenning(matrix, ids, [{"A", "B"}], taal)
    a = next(v for v in vragen if v.claim_id == "A")
    assert a.beste_partner == pytest.approx(0.898, abs=1e-3)
    assert a.beste_afleider == pytest.approx(0.8, abs=1e-3)
    assert a.gevonden_bovenaan
    # Gelijkstand telt als niet gevonden: twijfel versoepelt nooit.
    gelijk = mm.Zoekvraag("A", "zelfde taal", beste_partner=0.8, beste_afleider=0.8)
    assert not gelijk.gevonden_bovenaan


def test_the_query_itself_is_never_its_own_partner():
    ids = ["A", "B", "C"]
    matrix = np.vstack([_v(1, 0), _v(0, 1), _v(0.6, 0.8)])
    vragen = mm.herkenning(matrix, ids, [{"A", "B"}], dict.fromkeys(ids, "en"))
    a = next(v for v in vragen if v.claim_id == "A")
    assert a.beste_partner == pytest.approx(0.0, abs=1e-6)
    assert not a.gevonden_bovenaan


def test_the_split_follows_the_language_of_the_partners_not_of_the_hit():
    ids = ["A", "B", "C", "D"]
    matrix = np.vstack([_v(1, 0), _v(0.9, 0.44), _v(0.7, 0.71), _v(0, 1)])
    taal = {"A": "nl", "B": "en", "C": "nl", "D": "und"}
    vragen = {v.claim_id: v for v in mm.herkenning(matrix, ids, [{"A", "B"}, {"C", "D"}], taal)}
    assert vragen["A"].soort == "cross-linguaal"
    assert vragen["B"].soort == "cross-linguaal"
    # Een onbekende taal is geen bewijs van een andere taal.
    assert vragen["C"].soort == "taal onbekend"
    assert vragen["D"].soort == "taal onbekend"


def test_found_at_equal_error_level_does_not_depend_on_the_model_scale():
    rng = np.random.default_rng(1)
    partner = rng.uniform(0.3, 0.95, 400)
    afleider = rng.uniform(0.3, 0.95, 400)
    a = [mm.Zoekvraag(str(i), "zelfde taal", p, d) for i, (p, d) in enumerate(zip(partner, afleider))]
    # Model B rangschikt precies hetzelfde, op een andere schaal.
    b = [mm.Zoekvraag(v.claim_id, v.soort, 0.5 * v.beste_partner + 0.45, 0.5 * v.beste_afleider + 0.45) for v in a]
    for niveau in (0.02, 0.05, 0.10):
        _, gevonden_a, fout_a = mm.gevonden_bij_foutniveau(a, niveau)
        _, gevonden_b, fout_b = mm.gevonden_bij_foutniveau(b, niveau)
        assert gevonden_a == pytest.approx(gevonden_b)
        assert fout_a == pytest.approx(fout_b)
        assert fout_a <= niveau


def test_the_error_level_is_never_exceeded_even_when_nothing_can_be_found():
    vragen = [mm.Zoekvraag(str(i), "zelfde taal", 0.1, 0.9) for i in range(50)]
    drempel, gevonden, fout = mm.gevonden_bij_foutniveau(vragen, 0.05)
    assert gevonden == 0.0
    assert fout <= 0.05
    assert drempel > 0.9


def test_a_better_ranking_finds_more_at_the_same_error_level():
    slecht = [mm.Zoekvraag(str(i), "zelfde taal", 0.6, 0.7 if i % 2 else 0.5) for i in range(100)]
    goed = [mm.Zoekvraag(str(i), "zelfde taal", 0.6, 0.5) for i in range(100)]
    assert mm.gevonden_bij_foutniveau(goed, 0.02)[1] > mm.gevonden_bij_foutniveau(slecht, 0.02)[1]


class _NepModel:
    def __init__(self):
        self.gezien = []
        self.prompts = []

    def encode(self, teksten, *, prompt_name=None, normalize_embeddings, **_):
        assert normalize_embeddings
        self.gezien.extend(teksten)
        self.prompts.append(prompt_name)
        return np.vstack([_v(len(t), 1.0) for t in teksten])


def test_every_model_gets_the_production_casefold_plus_its_own_prefix():
    e5 = mm.Kandidaat("e5", "x/e5", "a" * 40, voorvoegsel="query: ")
    model = _NepModel()
    mm.embed(e5, ["VACCINS bevatten Chips", "ß"], model=model, portie=1, pauze=0)
    assert model.gezien == ["query: vaccins bevatten chips", "query: ss"]


def test_a_prompt_model_receives_its_prompt_and_vectors_come_back_in_order():
    voyage = mm.Kandidaat("voyage", "x/voyage", "b" * 40, prompt="document", eigen_code=True)
    model = _NepModel()
    teksten = ["a", "bbb", "cc", "dddd", "e"]
    m = mm.embed(voyage, teksten, model=model, portie=2, pauze=0)
    assert model.prompts == ["document", "document", "document"]
    assert m.shape == (5, 2) and m.dtype == np.float32
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0)
    assert np.allclose(m[3], _v(4, 1))


def test_every_candidate_is_measured_on_a_pinned_revision():
    for k in mm.KANDIDATEN.values():
        assert re.fullmatch(r"[0-9a-f]{40}", k.revisie), k.slug


def test_model_code_from_a_repository_only_runs_on_a_pinned_revision():
    with pytest.raises(ValueError):
        mm.controleer(mm.Kandidaat("v", "x/v", "main", eigen_code=True))
    mm.controleer(mm.Kandidaat("v", "x/v", "c" * 40, eigen_code=True))
    mm.controleer(mm.Kandidaat("m", "x/m", "main"))


# --- ronde twee: het volledige corpus, dezelfde testparen --------------------

import hashlib  # noqa: E402

from doublecheck.benchmark import run_benchmark  # noqa: E402
from doublecheck.config import Thresholds  # noqa: E402
from doublecheck.embedding import TextFingerprint  # noqa: E402
from doublecheck.reindex import reindex_text  # noqa: E402
from doublecheck.storage import connect, init_schema  # noqa: E402
from doublecheck.testset import herleid_artefactteksten, voeg_talen_toe  # noqa: E402
from tests.test_elke_taal import _claims  # noqa: E402
from tests.test_ingest import NEP  # noqa: E402


def _ander(tekst):
    """Een tweede nep-model: andere vectoren voor dezelfde tekst."""
    d = hashlib.sha256(tekst[::-1].encode("utf-8")).digest()[:8]
    v = np.frombuffer(d, dtype=np.uint8).astype(np.float32)
    return v / np.linalg.norm(v)


def _ander_batch(teksten, versie="kandidaat-v1"):
    return [TextFingerprint(vector=_ander(t), model_version=versie) for t in teksten]


@pytest.fixture
def db():
    c = connect(":memory:")
    init_schema(c)
    _claims(c, "nl", 30, "De heffing is {j} procent gestegen in het jaar 20{i:02d} volgens het rapport")
    _claims(c, "pt", 30, "O governo é responsável por {j} mortes em 20{i:02d} segundo o relatório oficial")
    voeg_talen_toe(c, NEP, ["nl", "pt"], per_taal=20)
    yield c
    c.close()


def test_every_test_artefact_comes_back_exactly_from_the_claim_text(db):
    teksten = herleid_artefactteksten(db, NEP)
    rijen = db.execute("SELECT testpair_id, payload FROM testpair WHERE kind = 'text'").fetchall()
    assert set(teksten) == {r[0] for r in rijen}
    for r in rijen:
        assert teksten[r[0]] is not None
        assert np.allclose(NEP(teksten[r[0]]).vector, np.frombuffer(r[1], dtype=np.float32))


def test_an_unrecoverable_artefact_is_reported_not_guessed(db):
    db.execute("UPDATE testpair SET payload = ? WHERE testpair_id = (SELECT min(testpair_id) FROM testpair)",
               (bytes(32),))
    assert list(herleid_artefactteksten(db, NEP).values()).count(None) == 1


def test_the_candidate_is_measured_on_the_same_pairs_with_its_own_vectors(db):
    voor = db.execute("SELECT testpair_id, claim_id, provenance, numbers, negations FROM testpair"
                      " ORDER BY 1").fetchall()
    teksten = herleid_artefactteksten(db, NEP)
    db.execute("UPDATE testpair SET payload = ? WHERE testpair_id = ?", (bytes(32), voor[0][0]))
    teksten[voor[0][0]] = None
    weggelaten = mm.herbouw_testset(db, teksten, "kandidaat-v1",
                                    lambda ts: np.vstack([_ander(t) for t in ts]))
    assert weggelaten == 1
    na = db.execute("SELECT testpair_id, claim_id, provenance, numbers, negations, model_version, payload"
                    " FROM testpair ORDER BY 1").fetchall()
    assert [tuple(r[:5]) for r in na] == [tuple(r) for r in voor[1:]]
    assert {r[5] for r in na} == {"kandidaat-v1"}
    for r in na:
        assert np.allclose(np.frombuffer(r[6], dtype=np.float32), _ander(teksten[r[0]]))


def test_the_fast_threshold_search_counts_exactly_like_the_benchmark(db):
    teksten = herleid_artefactteksten(db, NEP)
    mm.herbouw_testset(db, teksten, "kandidaat-v1", lambda ts: np.vstack([_ander(t) for t in ts]))
    reindex_text(db, "kandidaat-v1", fingerprinter=_ander_batch)
    bovenste = mm.bovenste_per_paar(db, "kandidaat-v1")
    for match, cross in ((0.99, 0.99), (0.95, 0.90), (0.90, 0.85), (0.80, 0.80)):
        t = Thresholds(text_match=match, text_related=0.5, image_same=31, text_match_crosslingual=cross)
        snel = mm.tel(bovenste, t)
        echt = run_benchmark(db, t, "kandidaat-v1").totals
        assert snel == (echt.wrong_links, echt.correct_matches, echt.same_pairs)


def test_calibration_never_exceeds_the_error_budget_and_prefers_the_stricter_tie():
    # (gelijkenis, is_zelfde, juiste_doel, tegenspraak, crosslinguaal)
    bovenste = [mm.Bovenste(0.95, True, True, False, False), mm.Bovenste(0.91, False, False, False, False),
                mm.Bovenste(0.90, True, True, False, False), mm.Bovenste(0.88, True, True, False, True),
                mm.Bovenste(0.70, True, True, False, False)]
    rooster = [x / 100 for x in range(60, 100)]
    t, fouten, goed = mm.kalibreer(bovenste, budget=0, rooster=rooster)
    assert fouten == 0
    assert t.text_match > 0.91
    # Cross-linguaal mag lager: de 0,88 haalt het zonder fout.
    assert goed == 2 and t.text_match_crosslingual <= 0.88
    assert t.text_match_crosslingual <= t.text_match


# --- per taal: een winst in het totaal mag geen taal verbergen (B14) --------

from doublecheck.benchmark import LanguageStats  # noqa: E402


def _st(zelfde, goed, fout):
    return LanguageStats(pairs=zelfde + 10, same_pairs=zelfde, lookalike_pairs=10,
                         wrong_links=fout, correct_matches=goed)


def test_every_language_is_compared_and_a_drop_is_flagged():
    basis = {"nl": _st(100, 60, 0), "hi": _st(100, 50, 1)}
    kandidaat = {"nl": _st(100, 75, 0), "hi": _st(100, 44, 0)}
    rijen = {r.taal: r for r in mm.per_taal(basis, kandidaat, marge=0.05)}
    assert rijen["nl"].verschil == pytest.approx(0.15) and not rijen["nl"].achteruit
    assert rijen["hi"].verschil == pytest.approx(-0.06) and rijen["hi"].achteruit


def test_more_errors_in_a_language_is_a_drop_even_with_more_coverage():
    rijen = mm.per_taal({"ar": _st(50, 20, 0)}, {"ar": _st(50, 30, 2)}, marge=0.05)
    assert rijen[0].achteruit


def test_a_language_missing_on_one_side_is_never_silently_skipped():
    with pytest.raises(ValueError):
        mm.per_taal({"nl": _st(10, 5, 0)}, {"en": _st(10, 5, 0)}, marge=0.05)


# --- de wissel: vectoren uit ronde twee naar productie (#25.14c) ------------


def test_vectors_move_over_under_the_production_version_and_only_once(db, tmp_path):
    import sqlite3

    bronpad = tmp_path / "bron.db"
    kopie = sqlite3.connect(bronpad)
    db.backup(kopie)
    kopie.close()
    bron = connect(bronpad)
    reindex_text(bron, "kandidaat-meet", fingerprinter=lambda ts, v: _ander_batch(ts, v))
    db.execute("DELETE FROM claim WHERE claim_id = 'nl-0'")  # alleen in de bron: blijft weg
    n = mm.neem_vectoren_over(db, bron, "kandidaat-meet", "kandidaat@prod")
    assert n == db.execute("SELECT count(*) FROM claim").fetchone()[0]
    for cid, payload in db.execute("SELECT f.claim_id, f.payload FROM fingerprint f"
                                   " WHERE f.model_version = 'kandidaat@prod'"):
        tekst = db.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (cid,)).fetchone()[0]
        assert np.allclose(np.frombuffer(payload, dtype=np.float32), _ander(tekst))
    assert mm.neem_vectoren_over(db, bron, "kandidaat-meet", "kandidaat@prod") == 0


def test_test_pairs_move_over_only_when_they_are_the_same_pairs(db, tmp_path):
    import sqlite3

    bronpad = tmp_path / "bron.db"
    kopie = sqlite3.connect(bronpad)
    db.backup(kopie)
    kopie.close()
    bron = connect(bronpad)
    teksten = herleid_artefactteksten(bron, NEP)
    mm.herbouw_testset(bron, teksten, "kandidaat-meet", lambda ts: np.vstack([_ander(t) for t in ts]))
    assert mm.neem_testparen_over(db, bron, "kandidaat@prod") == len(teksten)
    assert {r[0] for r in db.execute("SELECT DISTINCT model_version FROM testpair")} == {"kandidaat@prod"}
    # Een paar dat in de bron anders is: niets gaat over.
    bron.execute("UPDATE testpair SET provenance = 'origineel' WHERE testpair_id ="
                 " (SELECT min(testpair_id) FROM testpair WHERE provenance != 'origineel')")
    with pytest.raises(ValueError, match="testparen"):
        mm.neem_testparen_over(db, bron, "kandidaat@prod")
