"""Eén vaste meetopzet (PLAN #32.41): een ronde is een meetplan met sets, armen, wat gelabeld wordt en de eisen als
tellingen; dezelfde module draait elke ronde."""

import pytest

from doublecheck import meting as mt

PLAN = {"taak": "proef", "map": "data/meting/proef", "labels": "docs/steekproeven/proef.json", "budget": 1.0,
        "zaad": 7,
        "sets": {"O'": {"bron": "a.jsonl", "set": "O'", "eerste_dag": True},
                 "W2": {"bron": "a.jsonl", "set": "W2", "n": 2, "eerste_dag": True},
                 "N": {"bron": "b.jsonl", "set": "N", "beeld": True}},
        "armen": {"C": {"lezer": "lezer-v9", "speurvraag_model": "claude-haiku-5-5"}},
        "onwaar": ["O'", "N"], "waar": ["W2"],
        "eisen": [
            {"naam": "O' en N: met bewijs minstens 2",
             "tel": {"arm": "C", "sets": ["O'", "N"], "kleuren": ["rood", "oranje"], "labels": ["bewijst"]},
             "op": ">=", "waarde": 2},
            {"naam": "O': met bewijs plus niet bevestigd minstens 2",
             "tel": [{"arm": "C", "sets": ["O'"], "kleuren": ["rood", "oranje"], "labels": ["bewijst"]},
                     {"arm": "C", "sets": ["O'"], "uitkomsten": ["niet bevestigd"]}], "op": ">=", "waarde": 2},
            {"naam": "W2: geen vals alarm",
             "tel": {"arm": "C", "sets": ["W2"], "kleuren": ["rood", "oranje"], "labels": ["vals"]},
             "op": "<=", "waarde": 0}]}
BRONNEN = {"a.jsonl": [{"id": "o1", "set": "O'", "tekst": "x"}, {"id": "o2", "set": "O'", "tekst": "y"},
                       {"id": "w1", "set": "W2", "tekst": "z"}, {"id": "w2", "set": "W2", "tekst": "z"},
                       {"id": "w3", "set": "W2", "tekst": "z"}],
           "b.jsonl": [{"id": "n1", "set": "N", "tekst": "q", "beeld": "/p/1.jpg",
                        "eigen_urls": ["https://factly.in/eigen"]}]}


def test_the_set_follows_the_plan_with_a_fixed_sample_and_the_conditions_per_set():
    a, b = mt.kies_set(PLAN, BRONNEN), mt.kies_set(PLAN, {k: list(reversed(v)) for k, v in BRONNEN.items()})
    assert [r["id"] for r in a] == [r["id"] for r in b]
    assert sorted(r["set"] for r in a) == ["N", "O'", "O'", "W2", "W2"]
    o = next(r for r in a if r["set"] == "O'")
    n = next(r for r in a if r["set"] == "N")
    assert o["eerste_dag"] and not o.get("beeld") and not n["eerste_dag"] and n["beeld"] == "/p/1.jpg"


def test_the_plan_is_refused_when_an_arm_names_a_reader_that_does_not_exist():
    with pytest.raises(mt.Weigering):
        mt.controleer_plan({**PLAN, "armen": {"C": {"lezer": "lezer-v99"}}})
    with pytest.raises(mt.Weigering):
        mt.controleer_plan({**PLAN, "eisen": [{"naam": "x", "tel": {"arm": "Z", "sets": ["O'"]}, "op": ">=",
                                               "waarde": 1}]})
    mt.controleer_plan(PLAN)


def _rij(i, set_, kleur=None, uitkomst="onzeker", bronnen=()):
    return {"id": i, "set": set_, "arm": "C", "kleur": kleur, "uitkomst": uitkomst, "bronnen": list(bronnen),
            "kosten": 0.01}


def test_what_is_read_is_every_alarm_every_green_on_false_news_and_every_unconfirmed_on_true_news():
    assert mt.moet_lezen(_rij("o1", "O'", "rood"), PLAN)
    assert mt.moet_lezen(_rij("o1", "O'", "groen"), PLAN)
    assert mt.moet_lezen(_rij("w1", "W2", "oranje"), PLAN)
    assert mt.moet_lezen(_rij("w1", "W2", None, "niet bevestigd"), PLAN)
    assert not mt.moet_lezen(_rij("w1", "W2", "groen"), PLAN)
    assert not mt.moet_lezen(_rij("o1", "O'", None, "niet bevestigd"), PLAN)


def test_an_alarm_that_cites_the_own_fact_check_proves_itself():
    item = {"id": "n1", "eigen_urls": ["https://factly.in/eigen"]}
    rij = _rij("n1", "N", "rood", "klopt niet", [{"url": "https://factly.in/eigen", "rol": "spreekt tegen"}])
    assert mt.auto_label(rij, item) == "bewijst"
    assert mt.auto_label(_rij("n1", "N", "rood", "klopt niet", [{"url": "https://other.org/x"}]), item) is None


def test_counting_is_refused_while_something_that_counts_has_no_label():
    rijen = [_rij("o1", "O'", "rood")]
    with pytest.raises(mt.Weigering):
        mt.telling(rijen, {}, PLAN, items={"o1": {"id": "o1"}})


def test_the_bars_are_counts_from_the_plan():
    rijen = [_rij("o1", "O'", "rood", "klopt niet"), _rij("o2", "O'", None, "niet bevestigd"),
             _rij("n1", "N", "oranje", "misleidend", [{"url": "https://factly.in/eigen", "rol": "spreekt tegen"}]),
             _rij("w1", "W2", "groen", "klopt"), _rij("w2", "W2", "rood", "klopt niet")]
    items = {r["id"]: r for r in BRONNEN["a.jsonl"] + BRONNEN["b.jsonl"]}
    labels = {"o1#C": "bewijst", "w2#C": "vals"}
    uit = mt.telling(rijen, labels, PLAN, items=items)
    assert uit["eisen"] == {"O' en N: met bewijs minstens 2": {"waarde": 2, "gehaald": True},
                            "O': met bewijs plus niet bevestigd minstens 2": {"waarde": 2, "gehaald": True},
                            "W2: geen vals alarm": {"waarde": 1, "gehaald": False}}
    assert uit["per set"]["O' C"]["niet bevestigd"] == 1


def test_an_empty_search_credit_is_recognised_so_the_run_stops_before_it_pays_the_reader():
    import io
    import urllib.error

    leeg = urllib.error.HTTPError("https://api.search.brave.com", 402, "Payment Required", {}, io.BytesIO(b"{}"))
    druk = urllib.error.HTTPError("https://api.search.brave.com", 429, "Too Many Requests", {}, io.BytesIO(b"{}"))
    assert mt.tegoed_op(leeg) and not mt.tegoed_op(druk) and not mt.tegoed_op(TimeoutError())


def test_the_plan_can_cap_the_searches_of_a_run_and_the_estimate_says_how_many_it_will_need():
    plan = {**PLAN, "zoekvragen_max": 10}
    mt.controleer_plan(plan)
    with pytest.raises(mt.Weigering):
        mt.controleer_plan({**PLAN, "zoekvragen_max": 0})
    # een bericht zoekt zichzelf en hoogstens drie zoekvragen vooraf; een gewone tekst meestal alleen zichzelf
    assert mt.zoekvragen_geschat({"O'": 100, "G2": 40}, gewoon={"G2"}) == 100 * 4 + 40 * 1


def test_an_image_that_is_gone_falls_back_to_its_archived_copy_and_otherwise_the_message_is_skipped():
    def halen(bron):
        if "weg" in bron:
            raise OSError("404")
        return bron.encode()
    assert mt.beeld_of_reserve({"beeld": "https://a/1.jpg", "beeld_reserve": "https://archief/1.jpg"}, halen) == b"https://a/1.jpg"
    assert mt.beeld_of_reserve({"beeld": "https://weg/1.jpg", "beeld_reserve": "https://archief/1.jpg"}, halen) == \
        b"https://archief/1.jpg"
    assert mt.beeld_of_reserve({"beeld": "https://weg/1.jpg", "beeld_reserve": "https://ook-weg/1.jpg"}, halen) is None
    plan = {"sets": {"N": {"bron": "b.jsonl", "set": "N", "beeld": True}}}
    item = mt.kies_set(plan, {"b.jsonl": [{"id": "n1", "set": "N", "tekst": "q", "beeld": "https://a/1.jpg",
                                           "beeld_reserve": "https://archief/1.jpg"}]})[0]
    assert item["beeld_reserve"] == "https://archief/1.jpg"


def test_the_own_check_is_recognised_with_or_without_www_or_a_trailing_slash():
    item = {"id": "n1", "eigen_urls": ["https://correctiv.org/faktencheck/2021/12/09/scholz-raf"]}
    for url in ("https://correctiv.org/faktencheck/2021/12/09/scholz-raf/",
                "https://www.correctiv.org/faktencheck/2021/12/09/scholz-raf"):
        assert mt.auto_label(_rij("n1", "N", "rood", "klopt niet", [{"url": url}]), item) == "bewijst", url
    assert mt.auto_label(_rij("n1", "N", "rood", "klopt niet", [{"url": "https://correctiv.org/faktencheck/ander"}]),
                         item) is None


def test_the_row_keeps_what_the_reader_saw_for_each_source_it_named_and_nothing_else():
    res = [{"nr": 1, "url": "https://bbc.com/a", "titel": "Kop", "fragment": "x" * 500, "site": "bbc.com"},
           {"nr": 2, "url": "https://other.org/b", "titel": "Ander", "fragment": "niet genoemd", "site": "other.org"}]
    checks = [{"url": "https://snopes.com/c", "tekst": "De bewering van de check", "redactie": "Snopes"}]
    bronnen = [{"url": "https://bbc.com/a"}, {"url": "https://snopes.com/c", "redactie": "Snopes"}]
    gezien = mt.wat_de_lezer_zag(bronnen, res, checks)
    assert gezien == {"https://bbc.com/a": "Kop — " + "x" * 400, "https://snopes.com/c": "De bewering van de check"}
    uit = {"oordeel": "klopt", "kleur": "groen", "uitkomst": "klopt", "bronnen": bronnen}
    item = {"id": "W:1", "set": "W"}
    assert mt._rij(item, "C", uit, 0.0, [], "v", gezien)["gezien"] == gezien
    assert "gezien" not in mt._rij(item, "C", uit, 0.0, [], "v")


def test_the_row_also_keeps_every_result_and_check_the_explanation_cites_by_number():
    """§241: de nakijker zag alleen de bronnen die steunen of tegenspreken; een zin met [2] of [D1] wees naar een resultaat
    dat niet bewaard was, en heette dan *niet gedekt*."""
    res = [{"nr": 1, "url": "https://bbc.com/a", "titel": "Kop", "fragment": "f1", "site": "bbc.com"},
           {"nr": 2, "url": "https://other.org/b", "titel": "Ander", "fragment": "f2", "site": "other.org"},
           {"nr": 3, "url": "https://third.org/c", "titel": "Derde", "fragment": "f3", "site": "third.org"}]
    checks = [{"url": "https://snopes.com/c", "tekst": "De bewering van de check", "redactie": "Snopes"}]
    uitleg = "Dit klopt niet [2]. Snopes noemde het onwaar [D1]."
    gezien = mt.wat_de_lezer_zag([{"url": "https://bbc.com/a"}], res, checks, uitleg)
    assert gezien == {"https://bbc.com/a": "Kop — f1", "https://other.org/b": "Ander — f2",
                      "https://snopes.com/c": "De bewering van de check"}
    assert mt.wat_de_lezer_zag([], res, checks, "Een zin zonder nummer.") == {}



def test_the_row_keeps_the_colour_of_a_claim_the_message_only_reports():
    """§246: bij *over een bewering* krijgt het bericht geen kleur, de bewering zelf wel; die moet de meting bewaren."""
    uit = {"oordeel": "klopt niet", "kleur": None, "uitkomst": "over een bewering", "bronnen": [], "kleur_bewering": "rood"}
    item = {"id": "K:1", "set": "K"}
    assert mt._rij(item, "C", uit, 0.0, [], "v")["kleur_bewering"] == "rood"
    assert "kleur_bewering" not in mt._rij(item, "C", {**uit, "kleur_bewering": None}, 0.0, [], "v")


# --- de foto bij de bron (#32.54) ----------------------------------------------------------------------------------

def _antwoord(id_, set_, kleur, uitkomst, arm="C", vraag=None):
    return {"id": id_, "set": set_, "arm": arm, "kleur": kleur, "uitkomst": uitkomst, "oordeel": "klopt",
            "uitleg": "Dit klopt [1].", "bronnen": [{"url": "https://bbc.com/a", "rol": "bevestigt", "band": "goed"}],
            "kosten": 0.03, "vraag": vraag or mt.vingerafdruk(PLAN["armen"]["C"])}


def test_answers_of_the_same_arm_and_question_are_taken_over_and_another_question_is_refused():
    plan = {**PLAN, "overnemen": {"map": "data/meting/oud", "arm": "X", "sets": ["N"]}}
    oud = [_antwoord("n1", "N", "rood", "klopt niet", arm="X"), _antwoord("o1", "O'", "groen", "klopt", arm="X"),
           _antwoord("n2", "N", "groen", "klopt", arm="Y")]
    uit = mt.overgenomen(oud, plan, {"n1", "o1"})
    assert [(r["id"], r["arm"], r["overgenomen"]) for r in uit] == [("n1", "C", "data/meting/oud")]
    with pytest.raises(mt.Weigering):
        mt.overgenomen([_antwoord("n1", "N", "rood", "klopt niet", arm="X", vraag="anders")], plan, {"n1"})


def test_the_rule_runs_on_the_stored_answers_so_with_and_without_count_on_the_same_reading():
    rijen = [_antwoord("n1", "N", "groen", "klopt"), _antwoord("w1", "W2", "groen", "klopt"),
             _antwoord("w2", "W2", "groen", "klopt"), _antwoord("o1", "O'", "rood", "klopt niet")]
    niet = {"versie": "fotobron-v1", "gevonden": None, "paginas": 1, "geopend": 1, "beelden": 3}
    fotos = {("n1", "C"): {"vondst": niet},
             ("w1", "C"): {"vondst": {**niet, "gevonden": "https://bbc.com/a"}, "zonder_eigen": niet},
             ("w2", "C"): {"vondst": niet}}
    uit = {r["id"]: r for r in mt.met_foto(rijen, fotos)}
    assert uit["n1"]["kleur"] is None and uit["n1"]["uitkomst"] == "foto niet bij de bron"
    assert uit["n1"]["zonder_foto"] == {"kleur": "groen", "uitkomst": "klopt"}
    assert uit["w1"]["kleur"] == "groen" and uit["w1"]["zonder_eigen"]["kleur"] is None
    assert uit["o1"] == rijen[3]
    labels = {"n1#C": "vals", "w2#C": "terecht"}
    tel = lambda **f: mt._tel(list(uit.values()), labels, {}, {"arm": "C", **f})  # noqa: E731
    assert tel(sets=["N"], kleuren=["groen"], labels=["vals"]) == 0
    assert tel(sets=["N"], kleuren=["groen"], labels=["vals"], variant="zonder_foto") == 1
    assert tel(sets=["W2"], kleuren=["groen"]) == 1 and tel(sets=["W2"], kleuren=["groen"], variant="zonder_foto") == 2
    assert tel(sets=["W2"], kleuren=["groen"], variant="zonder_eigen") == 0


def test_a_green_the_rule_took_away_is_still_read_on_false_and_on_true_news():
    weg = {**_antwoord("n1", "N", None, "foto niet bij de bron"), "zonder_foto": {"kleur": "groen", "uitkomst": "klopt"}}
    assert mt.moet_lezen(weg, PLAN) and mt.moet_lezen({**weg, "set": "W2"}, PLAN)
    assert not mt.moet_lezen(_antwoord("w1", "W2", "groen", "klopt"), PLAN)


def test_a_bar_can_be_a_share_of_another_count_on_the_same_answers():
    rijen = [_antwoord("w1", "W2", "groen", "klopt"), _antwoord("w2", "W2", "groen", "klopt"),
             _antwoord("w3", "W2", "groen", "klopt")]
    niet = {"versie": "fotobron-v1", "gevonden": None, "paginas": 1, "geopend": 1, "beelden": 1}
    rijen = mt.met_foto(rijen, {("w3", "C"): {"vondst": niet}})
    eis = {"naam": "W2: 80% van het groen blijft", "tel": {"arm": "C", "sets": ["W2"], "kleuren": ["groen"]},
           "op": ">=", "aandeel": 0.8,
           "van": {"arm": "C", "sets": ["W2"], "kleuren": ["groen"], "variant": "zonder_foto"}}
    plan = {**PLAN, "eisen": [eis]}
    mt.controleer_plan(plan)
    uit = mt.telling(rijen, {"w3#C": "terecht"}, plan, {})["eisen"][eis["naam"]]
    assert uit == {"waarde": 2, "van": 3, "gehaald": False}


def test_direct_asks_each_question_on_its_own_and_returns_what_got_no_answer():
    """PO 2026-11-08: "doe maar direct dan, hoe sneller hoe beter": dezelfde vragen, zonder de Batch API."""
    class Client:
        class messages:
            @staticmethod
            def create(**p):
                if p["id"] == "b":
                    raise RuntimeError("overbelast")
                return f"antwoord {p['id']}"

    ontvangen = {}
    gemist = mt.vraag_alles(Client, {"a": {"id": "a"}, "b": {"id": "b"}, "c": {"id": "c"}}, ontvangen.update,
                            None, None, direct=True)
    assert gemist == ["b"] and ontvangen == {"a": "antwoord a", "c": "antwoord c"}
    assert mt.prijsfactor(True) == 2 and mt.prijsfactor(False) == 1


def test_answers_taken_over_cost_nothing_in_this_round():
    plan = {**PLAN, "overnemen": {"map": "data/meting/oud", "arm": "X", "sets": ["N"]}}
    r = mt.overgenomen([_antwoord("n1", "N", "rood", "klopt niet", arm="X")], plan, {"n1"})[0]
    assert r["kosten"] == 0.0 and r["kosten_oud"] == 0.03


def test_each_version_of_the_photo_rule_writes_its_own_file():
    assert mt.fotobestand("fotobron-v1") == "foto.jsonl" and mt.fotobestand("fotobron-v2") == "foto-v2.jsonl"
    assert mt.fotobestand("fotobron-v2", snel=True) == "wachttijd-fotobron-v2.jsonl"


def test_a_busy_archive_is_asked_again_after_a_pause_and_a_missing_image_is_not():
    """#32.54: het webarchief zegt bij snel na elkaar vragen "te veel verzoeken" (429); dan wachten en opnieuw. Een 404
    is echt weg en wordt niet herhaald."""
    antwoorden, wachten = [429, 503, 200], []
    def vraag():
        return antwoorden.pop(0)
    assert mt.met_geduld(vraag, wachten.append) == 200 and wachten == [5, 20]
    antwoorden[:], wachten[:] = [404, 200], []
    assert mt.met_geduld(vraag, wachten.append) == 404 and wachten == []
    antwoorden[:] = [429, 429, 429, 429]
    assert mt.met_geduld(vraag, wachten.append) == 429 and wachten == [5, 20, 60]
