"""De feitenlaag (PLAN #30.3b): een vraag die een vastgesteld feit is, wordt
herkend met de rechter; zonder zijn *zelfde* geen feit, want een valse
bewering die op een feit lijkt, mag nooit een terechte ontkrachting kwijtraken.
"""

import dataclasses
import sqlite3

import numpy as np

from doublecheck import feitenlaag
from doublecheck.config import load_config


def _config(aan=True):
    c = load_config()
    return dataclasses.replace(
        c, feiten=dataclasses.replace(c.feiten, aan=aan),
        thresholds=dataclasses.replace(c.thresholds, feit_vloer=0.80, feit_zelfde=0.95),
        rechter=dataclasses.replace(c.rechter, aan=True, model="rechter-d@x", pad="x", diepte=3))


class _Fp:
    def __init__(self, v):
        self.vector = np.asarray(v, dtype=np.float32)


INDEX = ([("crimea", "Russia annexed Crimea in 2014."), ("apollo", "Neil Armstrong walked on the Moon in 1969.")],
         np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))


def test_with_the_layer_off_nothing_is_recognised():
    assert feitenlaag.herken("x", _Fp([1, 0]), _config(aan=False), scorer=lambda v, t: [1.0], index=INDEX) is None


def test_a_question_close_to_a_fact_that_the_judge_calls_the_same_is_recognised():
    feit = feitenlaag.herken("Rusia se anexionó Crimea", _Fp([0.9, 0.1]), _config(), scorer=lambda v, t: [0.99],
                             index=INDEX)
    assert feit.feit == "crimea" and feit.score == 0.99


def test_a_false_claim_close_to_a_fact_is_not_recognised_when_the_judge_says_no():
    assert feitenlaag.herken("Crimea decided to join Russia", _Fp([0.9, 0.1]), _config(),
                             scorer=lambda v, t: [0.2], index=INDEX) is None


def test_below_the_floor_the_judge_is_not_even_asked():
    gevraagd = []
    uit = feitenlaag.herken("x", _Fp([0.5, 0.5]), _config(), scorer=lambda v, t: gevraagd.append(t) or [1.0],
                            index=INDEX)
    assert uit is None and gevraagd == []


def test_a_claim_is_red_when_its_checks_say_false_or_disputed():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE factcheck (claim_id TEXT, verdict_normalized TEXT, review_date TEXT)")
    conn.executemany("INSERT INTO factcheck VALUES (?, ?, ?)",
                     [("rood", "onwaar", "2024-01-01"), ("groen", "waar", "2024-01-01")])
    assert feitenlaag.rood(conn, "rood") is True
    assert feitenlaag.rood(conn, "groen") is False
    assert feitenlaag.rood(conn, "onbekend") is False
