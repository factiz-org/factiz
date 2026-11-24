"""Lijkt op (PLAN #34.2p): andere factchecks over hetzelfde verhaal, uit de vectoren die er al liggen, met een drempel die
een leesproef vastlegt volgens een regel die vóór het lezen vaststond."""

import json

import numpy as np

from doublecheck import lijktop as lo


def _vectoren():
    rng = np.random.default_rng(1)
    basis = rng.normal(size=(4, 16)).astype(np.float32)
    rijen = [basis[0], basis[0] + 0.05, basis[0] + 0.3, basis[1], basis[2], basis[3]]
    return np.stack(rijen).astype(np.float32), ["a", "b", "c", "d", "e", "f"]


def test_a_page_never_resembles_itself_and_only_neighbours_above_the_floor_count():
    x, namen = _vectoren()
    buren = lo.buren(x, namen, k=5, vloer=0.9, blok=2)
    assert "a" not in [b for b, _ in buren["a"]]
    assert [b for b, _ in buren["a"]][:1] == ["b"] and all(s >= 0.9 for _, s in buren["a"])
    assert buren["d"] == [] and buren["f"] == []
    assert [b for b, _ in lo.buren(x, namen, k=1, vloer=0.0, blok=4)["a"]] == ["b"]   # het blok verandert niets


def _paren(n=400):
    rng = np.random.default_rng(2)
    return [{"pagina": f"p{i}", "ander": f"q{i}", "score": float(s)} for i, s in enumerate(rng.uniform(0.80, 1.0, n))]


def test_the_reading_sample_takes_fifty_pairs_per_score_band_once_and_always_the_same():
    paren = _paren() + [{"pagina": "q0", "ander": "p0", "score": _paren()[0]["score"]}]   # hetzelfde paar omgekeerd
    proef = lo.leesproef(paren)
    assert proef == lo.leesproef(paren)
    assert len(proef) == 200 and len({tuple(sorted(p)) for p in proef}) == 200
    per_vak = {}
    for a, b in proef:
        s = next(p["score"] for p in paren if {p["pagina"], p["ander"]} == {a, b})
        per_vak[lo.vak(s)] = per_vak.get(lo.vak(s), 0) + 1
    assert per_vak == {v: 50 for v in lo.VAKKEN}


def _labels(tmp_path, paren, ander_per_vak):
    proef = lo.leesproef(paren)
    score = {frozenset((p["pagina"], p["ander"])): p["score"] for p in paren}
    gezien: dict[float, int] = {}
    labels = {}
    for a, b in proef:
        v = lo.vak(score[frozenset((a, b))])
        gezien[v] = gezien.get(v, 0) + 1
        labels[f"{a}|{b}"] = "ander" if gezien[v] <= ander_per_vak.get(v, 0) else "zelfde"
    pad = tmp_path / "paren.json"
    pad.write_text(json.dumps({"toelichting": "proef", "paren": labels}), encoding="utf-8")
    return pad


def test_the_threshold_is_the_lowest_band_from_which_every_band_above_holds_95_percent(tmp_path):
    paren = _paren()
    assert lo.poort(paren, _labels(tmp_path, paren, {}))[0] == 0.80
    # de laagste twee vakken halen het niet: de drempel wordt 0,90
    assert lo.poort(paren, _labels(tmp_path, paren, {0.80: 10, 0.85: 3}))[0] == 0.90
    # een gat erboven telt: 0,85 haalt het, 0,90 niet, dus pas vanaf 0,95
    assert lo.poort(paren, _labels(tmp_path, paren, {0.80: 10, 0.90: 3}))[0] == 0.95
    # haalt het hoogste vak het niet, dan geen Lijkt op
    assert lo.poort(paren, _labels(tmp_path, paren, {0.95: 3}))[0] is None
    assert lo.poort(paren, tmp_path / "bestaat-niet.json")[0] is None


def test_doubt_counts_as_another_story(tmp_path):
    paren = _paren()
    pad = _labels(tmp_path, paren, {})
    d = json.loads(pad.read_text())
    hoog = [k for k, _ in d["paren"].items()
            if lo.vak(next(p["score"] for p in paren if f"{p['pagina']}|{p['ander']}" == k
                           or f"{p['ander']}|{p['pagina']}" == k)) == 0.95][:3]
    for k in hoog:
        d["paren"][k] = "twijfel"
    pad.write_text(json.dumps(d))
    assert lo.poort(paren, pad)[0] is None


def test_only_pairs_above_the_threshold_and_at_most_five_per_page_go_into_the_publication():
    paren = [{"pagina": "a", "ander": x, "score": s} for x, s in
             [("b", 0.99), ("c", 0.97), ("d", 0.96), ("e", 0.955), ("f", 0.951), ("g", 0.95), ("h", 0.94)]]
    uit = lo.voor_uitgave(paren, 0.95)
    assert uit == {"a": ["b", "c", "d", "e", "f"]}
    assert lo.voor_uitgave(paren, None) == {}


def test_pages_are_compared_on_the_text_the_site_shows_english_first_then_dutch_then_the_original():
    assert lo.getoond("si", "සිංහල", {"en": "Protesters raised a flag", "nl": "Demonstranten hesen een vlag"}) == \
        "Protesters raised a flag"
    assert lo.getoond("si", "සිංහල", {"nl": "Demonstranten hesen een vlag"}) == "Demonstranten hesen een vlag"
    assert lo.getoond("nl", "Een Nederlandse bewering", {"en": "An English one"}) == "An English one"
    assert lo.getoond("en", "An English claim", {"nl": "x"}) == "An English claim"
    assert lo.getoond("fa", "فارسی", {}) == "فارسی"
