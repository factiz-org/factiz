"""De reikwijdte van het archief (B92, PLAN #37.14): elke bewering internationaal, regionaal, lokaal, persoonlijk of twijfel;
alleen wat internationaal, regionaal of twijfel is, gaat mee in de vertaalronde, en pas na een gelezen greep van 200."""

import json

from doublecheck import reikwijdte as rw


def test_each_claim_gets_one_of_five_labels_and_nothing_else_counts():
    teksten = ["a", "b", "c", "d"]
    antwoord = {"antwoorden": [{"nr": 1, "oordeel": "internationaal"}, {"nr": 2, "oordeel": "lokaal"},
                               {"nr": 2, "oordeel": "regionaal"}, {"nr": 4, "oordeel": "wereldwijd"}]}
    assert rw.lees_oordelen(json.dumps(antwoord), teksten) == ["internationaal", None, None, None]
    assert rw.lees_oordelen("geen json", teksten) == [None] * 4


def test_the_question_carries_the_yardstick_of_the_radar_and_asks_haiku():
    v = rw.verzoek(["Video shows missiles over Kyiv"])
    assert v["model"].startswith("claude-haiku")
    # de lat van de PO (B92): lokaal is alleen wat binnen één plaats blijft; nationaal en deelstaat worden vertaald
    for regel in ("beyond one country", "war", "migration", "climate", "several countries", "another country",
                  "national or state-wide", "one town, city or district", "private person", "choose \"regionaal\""):
        assert regel in v["system"], regel
    assert v["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]["oordeel"]["enum"] == \
        list(rw.OORDELEN)


def test_the_draw_to_read_is_fixed_and_leaves_out_nothing_it_needs():
    paginas = {f"{i:016x}": f"claim {i}" for i in range(1000)}
    a, b = rw.te_lezen(paginas), rw.te_lezen(dict(reversed(list(paginas.items()))))
    assert a == b and len(a) == rw.PROEF_N and len(set(a)) == rw.PROEF_N


def _labels(tmp_path, labels):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": {nr: {"label": l} for nr, l in labels.items()}}), encoding="utf-8")
    return pad


def test_the_gate_opens_only_with_every_drawn_claim_read_and_at_most_twenty_on_the_wrong_side(tmp_path):
    greep = [f"p{i}" for i in range(rw.PROEF_N)]
    model = {p: "internationaal" for p in greep}
    goed = {p: "regionaal" for p in greep}                     # dezelfde kant: vertalen
    assert rw.poort(greep, model, tmp_path / "geen.json") == (False, "nog niets gelezen")
    assert rw.poort(greep, model, _labels(tmp_path, goed))[0] is True
    fout = {**goed, **{p: "lokaal" for p in greep[:rw.MAX_FOUT]}}
    assert rw.poort(greep, model, _labels(tmp_path, fout))[0] is True
    fout = {**goed, **{p: "lokaal" for p in greep[:rw.MAX_FOUT + 1]}}
    assert rw.poort(greep, model, _labels(tmp_path, fout))[0] is False
    open_ = {k: v for k, v in goed.items() if k != greep[0]}
    assert rw.poort(greep, model, _labels(tmp_path, open_)) == (False, "1 nog te lezen")


def test_translation_takes_international_regional_and_doubt_for_the_text_that_was_read():
    vol = [{"pagina": "a", "bewering": "A", "oordeel": "internationaal", "versie": rw.VERSIE},
           {"pagina": "b", "bewering": "B", "oordeel": "lokaal", "versie": rw.VERSIE},
           {"pagina": "c", "bewering": "C", "oordeel": "twijfel", "versie": rw.VERSIE},
           {"pagina": "d", "bewering": "D", "oordeel": "persoonlijk", "versie": rw.VERSIE},
           {"pagina": "e", "bewering": "E", "oordeel": "regionaal", "versie": rw.VERSIE}]
    assert rw.voor_vertaling(vol, {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E anders"}) == {"a", "c"}


def test_the_translation_round_skips_only_what_was_read_as_local_or_personal_for_its_current_text():
    vol = [{"pagina": "a", "bewering": "A", "oordeel": "lokaal", "versie": rw.VERSIE},
           {"pagina": "b", "bewering": "B", "oordeel": "persoonlijk", "versie": rw.VERSIE},
           {"pagina": "c", "bewering": "C", "oordeel": "regionaal", "versie": rw.VERSIE},
           {"pagina": "d", "bewering": "D oud", "oordeel": "lokaal", "versie": rw.VERSIE}]
    # d veranderde na de scan en e is nieuw: die gaan mee tot ze gelezen zijn
    assert rw.te_vertalen(vol, {"a": "A", "b": "B", "c": "C", "d": "D nieuw", "e": "E"}) == {"c", "d", "e"}


def test_the_gate_reads_the_drawn_claims_from_the_labels_file_so_a_new_edition_does_not_close_it(tmp_path):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": {"p1": {"label": "lokaal"}, "p2": {"label": "regionaal"}}}), encoding="utf-8")
    assert rw.poort_vast({"p1": "lokaal", "p2": "internationaal", "p9": "lokaal"}, pad) == (True, "2 van de 2 aan de goede kant, 0 fout (hoogstens 20)")
    assert rw.poort_vast({"p1": "lokaal"}, pad)[0] is False             # een getrokken bewering zonder antwoord van het model
