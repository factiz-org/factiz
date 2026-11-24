"""Alle vetoblokkades van het corpus (PLAN #25.14d, d en g).

Een blokkade is een paar dat de clustering zou samenvoegen (zelfde taal,
gelijkenis boven `cluster_same`, geen tegenspraak in getallen of
ontkenningen) maar dat het NLI-veto tegenhoudt. Eerst tellen en scoren, dan
labelen: trekt het veto dezelfde bewering uit elkaar, of houdt het terecht
twee beweringen apart?
"""

import json

import numpy as np

from doublecheck import vetoblokkades as vb
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

VERSIE = "testmodel-v1"


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _db():
    conn = connect(":memory:")
    init_schema(conn)
    claims = [
        # id, tekst, taal, cluster, richting
        ("A", "De burgemeester van Utrecht sloot alle scholen", "nl", None, (1, 0, 0, 0)),
        ("B", "Burgemeester Utrecht sluit alle scholen", "nl", "cl-x", (0.96, 0.28, 0, 0)),
        ("C", "Het vaccin bevat een chip", "nl", "cl-y", (0, 1, 0, 0)),
        ("D", "Vaccins bevatten een microchip", "nl", "cl-y", (0, 0.97, 0.243, 0)),
        ("E", "Der Impfstoff enthält einen Chip", "de", None, (0, 0.99, 0.141, 0)),
        ("F", "Bij de ramp vielen 10.000 doden", "nl", None, (0, 0, 0, 1)),
        ("G", "Bij de ramp vielen 20.000 doden", "nl", None, (0, 0, 0.2, 0.98)),
        ("H", "Een heel andere bewering", "nl", None, (0.6, 0, 0, 0.8)),
    ]
    for cid, tekst, taal, cluster, richting in claims:
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, ?, ?)",
                     (cid, tekst, taal, cluster))
        save_text_fingerprint(conn, cid, TextFingerprint(_v(*richting), VERSIE))
    conn.commit()
    return conn


def test_only_same_language_pairs_above_the_merge_threshold_that_are_apart_are_candidates():
    """C en D zitten al samen, E is Duits (het veto oordeelt alleen binnen één
    taal), H ligt te ver weg. F en G vallen af op de getallenregel."""
    paren = vb.kandidaten(_db(), VERSIE, 0.91)
    assert [(p.a, p.b, p.taal) for p in paren] == [("A", "B", "nl")]
    assert paren[0].gelijkenis > 0.91


def test_a_pair_the_number_rule_already_blocks_is_not_a_veto_blockage():
    conn = _db()
    alle = vb.kandidaten(conn, VERSIE, 0.91, ook_tegenspraak=True)
    assert ("F", "G") in [(p.a, p.b) for p in alle]
    assert ("F", "G") not in [(p.a, p.b) for p in vb.kandidaten(conn, VERSIE, 0.91)]


def test_scoring_is_resumable_and_never_scores_a_pair_twice(tmp_path):
    conn = _db()
    paren = vb.kandidaten(conn, VERSIE, 0.91)
    gescoord = []

    def score(a, b):
        gescoord.append((a, b))
        return 0.73

    pad = tmp_path / "scores.jsonl"
    assert vb.scoor(conn, paren, score, pad) == 1
    assert vb.scoor(conn, paren, score, pad) == 0
    assert len(gescoord) == 1
    regel = json.loads(pad.read_text(encoding="utf-8").splitlines()[0])
    assert regel == {"sleutel": "A|B", "a": "A", "b": "B", "taal": "nl",
                     "gelijkenis": round(paren[0].gelijkenis, 4), "score": 0.73}


def test_a_blockage_is_a_candidate_scored_at_or_above_the_veto_threshold(tmp_path):
    pad = tmp_path / "scores.jsonl"
    pad.write_text("\n".join(json.dumps(r) for r in [
        {"sleutel": "A|B", "a": "A", "b": "B", "taal": "nl", "gelijkenis": 0.96, "score": 0.5},
        {"sleutel": "C|X", "a": "C", "b": "X", "taal": "nl", "gelijkenis": 0.93, "score": 0.4999},
    ]) + "\n", encoding="utf-8")
    assert [r["sleutel"] for r in vb.blokkades(pad, 0.5)] == ["A|B"]


def test_the_trade_off_counts_what_each_threshold_still_blocks():
    """Per vetodrempel: hoeveel terechte, onterechte en twijfelachtige
    blokkades er blijven staan. Een hogere drempel laat alles eronder door."""
    paren = {
        "a|b": {"label": "terecht", "score": 0.95, "gelijkenis": 0.92},
        "c|d": {"label": "onterecht", "score": 0.55, "gelijkenis": 0.99},
        "e|f": {"label": "onterecht", "score": 0.85, "gelijkenis": 0.93},
        "g|h": {"label": "twijfel", "score": 0.7, "gelijkenis": 0.96},
    }
    assert vb.afweging(paren, (0.5, 0.8, 0.9)) == [
        {"drempel": 0.5, "terecht": 1, "onterecht": 2, "twijfel": 1},
        {"drempel": 0.8, "terecht": 1, "onterecht": 1, "twijfel": 0},
        {"drempel": 0.9, "terecht": 1, "onterecht": 0, "twijfel": 0},
    ]
    assert vb.per_gelijkenis(paren, (0.91, 0.95, 1.01)) == [
        {"band": "0.91-0.95", "terecht": 1, "onterecht": 1, "twijfel": 0},
        {"band": "0.95-1.01", "terecht": 0, "onterecht": 1, "twijfel": 1},
    ]


def test_new_blockages_without_a_label_are_reported_for_the_next_round(tmp_path):
    """Elke versheidsronde scoort alleen de nieuwe paren; wat het veto daarvan
    tegenhoudt en nog geen label heeft, is het werk van die ronde, en die
    labels zijn de achtergehouden toets voor elke grens die we later kiezen."""
    pad = tmp_path / "scores.jsonl"
    pad.write_text("\n".join(json.dumps(r) for r in [
        {"sleutel": "A|B", "a": "A", "b": "B", "taal": "nl", "gelijkenis": 0.96, "score": 0.9},
        {"sleutel": "C|D", "a": "C", "b": "D", "taal": "en", "gelijkenis": 0.93, "score": 0.7},
        {"sleutel": "E|F", "a": "E", "b": "F", "taal": "en", "gelijkenis": 0.92, "score": 0.2},
    ]) + "\n", encoding="utf-8")
    labels = {"A|B": {"label": "onterecht", "ronde": "2026-10-12"}}
    assert [r["sleutel"] for r in vb.ongelabeld(pad, labels, 0.5)] == ["C|D"]
