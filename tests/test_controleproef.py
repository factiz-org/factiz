"""De proef van ronde 2 (PLAN #31.12): de regels die vóór de eerste vraag vastlagen."""

from doublecheck import controleproef as p


def _stukken():
    return [{"id": f"K{i:04d}", "label": "waar"} for i in range(30)] + \
        [{"id": f"V{i:03d}", "label": "onwaar"} for i in range(30)]


def test_the_trial_takes_half_true_and_half_false_sentences_fixed_by_seed():
    gekozen = p.kies(_stukken(), 20)
    assert gekozen == p.kies(_stukken(), 20)
    assert sum(s["label"] == "waar" for s in gekozen) == 10 and len(gekozen) == 20


def test_the_summary_counts_cache_reads_cost_time_and_agreement_with_round_1():
    rijen = [{"oordeel": "klopt", "ronde1": "klopt", "kosten": 0.04, "lokaal": 1.0, "model": 9.0,
              "gebruik": {"cache_lees": 0, "cache_schrijf": 2900}},
             {"oordeel": "klopt niet", "ronde1": "klopt niet", "kosten": 0.03, "lokaal": 1.0, "model": 7.0,
              "gebruik": {"cache_lees": 2900, "cache_schrijf": 0}},
             {"oordeel": "onzeker", "ronde1": "klopt niet", "kosten": 0.02, "lokaal": 2.0, "model": 5.0,
              "gebruik": {"cache_lees": 2900, "cache_schrijf": 0}}]
    s = p.samenvatting(rijen)
    assert s["n"] == 3 and s["uit de cache gelezen"] == 2 and s["gelijk aan ronde 1"] == 2
    assert s["kosten per bericht"] == 0.03 and s["p95 route (s)"] == 10.0
