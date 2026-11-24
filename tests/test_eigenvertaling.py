"""De eigen checks van Factiz Radar vertaald (PLAN #37.8, B85; PO 2026-11-19: "Ja, alle veertien talen"): een
machinevertaling geldt alleen zolang de check niet veranderde, en een antwoord van het model alleen als het dezelfde velden,
lijsten en bronnummers heeft."""

import json

from doublecheck import eigenvertaling as ev
from tests import test_redactie as tr


def _c(**anders):
    return tr._check(**{"status": "gepubliceerd", "tijdlijn": [{"datum": "2026-11-08", "wat": "De post [1]."}], **anders})


def _vertaald(c, voor="EN"):
    """Een vertaling van elk tekstveld met dezelfde bronnummers die het origineel niet bevat (`onvertaald`): de woorden
    achterstevoren, met een merkteken ervoor."""
    return {k: f"{voor} " + " ".join(reversed(v.split())) if isinstance(v, str) else v for k, v in ev.bron(c).items()}


def test_the_fields_a_reader_reads_are_translated_and_nothing_else():
    c = _c(nog_uitzoeken=["Wie maakte het beeld?"])
    b = ev.bron(c)
    assert {"kop", "oordeel_zin", "bewering", "kort", "tekst", "niet_weten", "nog_uitzoeken", "tijdlijn",
            "beeld_bijschrift", "beeld_alt"} <= set(b)
    assert "bron" not in b and "sleutel" not in b and "auteur" not in b
    assert b["nog_uitzoeken"] == ["Wie maakte het beeld?"] and b["tijdlijn"] == ["De post [1]."]
    assert ev.doeltalen(c) == [t for t in ev.TALEN if t != "nl"] and len(ev.doeltalen(c)) == 14


def test_a_translation_stops_counting_when_the_check_changes():
    c = _c()
    v = {"vingerafdruk": ev.vingerafdruk(c), "velden": _vertaald(c), "maker": "x"}
    assert ev.geldig(c, v)
    assert not ev.geldig({**c, "tekst": c["tekst"] + " Nog een zin [1]."}, v)
    assert not ev.geldig(c, None)


def test_an_answer_counts_only_with_the_same_fields_lists_and_source_numbers():
    velden = {"kop": "De kop", "tekst": "Het klopt niet [1] [2].", "nog_uitzoeken": ["Een vraag."], "tijdlijn": ["De post [3]."]}
    goed = {"kop": "The headline", "tekst": "It is false [1] [2].", "nog_uitzoeken": ["A question."], "tijdlijn": ["The post [3]."]}
    assert ev.lees_antwoord(json.dumps(goed), velden) == goed
    assert ev.lees_antwoord("```json\n" + json.dumps(goed) + "\n```", velden) == goed
    assert ev.lees_antwoord(json.dumps({**goed, "tekst": "It is false [1]."}), velden) is None      # een bron weg
    assert ev.lees_antwoord(json.dumps({**goed, "tekst": "False [1] [3]."}), velden) is None       # een bron erbij
    # een nummer twee keer mag, als de zin in de andere taal anders loopt (het Russisch, 2026-11-19)
    assert ev.lees_antwoord(json.dumps({**goed, "tekst": "It [1] is false [1] [2]."}), velden) is not None
    assert ev.lees_antwoord(json.dumps({**goed, "nog_uitzoeken": []}), velden) is None              # een punt weg
    assert ev.lees_antwoord(json.dumps({**goed, "extra": "x"}), velden) is None                     # een veld erbij
    assert ev.lees_antwoord(json.dumps({**goed, "kop": "The headline — really"}), velden) is None
    assert ev.lees_antwoord("geen json", velden) is None and ev.lees_antwoord(None, velden) is None


def test_the_plan_asks_only_the_languages_without_a_valid_translation(tmp_path):
    c = _c(sleutel="proef")
    p = ev.pad("proef", "en", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"vingerafdruk": ev.vingerafdruk(c), "velden": _vertaald(c), "maker": "m"}), encoding="utf-8")
    te_doen = ev.nog_te_doen([c, _c(sleutel="concept", status="concept")], tmp_path)
    assert ("proef", "en") not in te_doen and len(te_doen) == 13 and all(s == "proef" for s, _ in te_doen)
    assert ev.geldige(c, tmp_path) == {"en": {"velden": _vertaald(c), "maker": "m", "nagelezen": False}}
    assert ev.schatting([c], te_doen) > 0


def test_a_translation_file_says_where_it_came_from():
    # elk databestand dat de site verspreidt, zegt waar het vandaan komt (tests/test_licenties.py): eigen werk van Factiz,
    # een machinevertaling, uit welke taal en door welk model
    c = _c()
    v = ev.bestand(c, "en", _vertaald(c), "claude-sonnet-5-5, eigenvertaling-v1")
    assert list(v)[0] == "_meta"
    assert "Factiz" in v["_meta"] and "machinevertaling" in v["_meta"].lower()
    assert "nl" in v["_meta"] and "claude-sonnet-5-5" in v["_meta"]
    assert ev.geldig(c, v)


def test_an_answer_that_repeats_the_question_around_the_translation_still_counts():
    # soms geeft het model de vraag terug met de vertaling onder "velden"; dat is dezelfde vertaling (#37.9, trump-nigeria-video
    # in het Frans, twee keer); de controle op velden, lijsten en nummers blijft gelijk
    c = _c()
    velden, vertaald = ev.bron(c), _vertaald(c, "FR")
    ingepakt = json.dumps({"doeltaal": "Frans", "brontaal": "Nederlands", "velden": vertaald})
    assert ev.lees_antwoord(ingepakt, velden) == vertaald
    fout = json.dumps({"doeltaal": "Frans", "velden": {**vertaald, "kop": vertaald["kop"] + " [9]"}})
    assert ev.lees_antwoord(fout, velden) is None


def test_a_draft_in_a_language_the_editors_do_not_read_gets_only_an_english_translation(tmp_path):
    # de PO leest een check in een andere taal na in het Engels (B85, punt 5, #37.10); een concept in het Nederlands of het
    # Engels wacht op het nalezen, en een gepubliceerde check krijgt alle talen
    concept_hi = _c(sleutel="a", taal="hi", status="concept")
    concept_nl = _c(sleutel="b", taal="nl", status="concept")
    gepubliceerd = _c(sleutel="c", taal="hi")
    te_doen = ev.nog_te_doen([concept_hi, concept_nl, gepubliceerd], tmp_path)
    assert [t for s, t in te_doen if s == "a"] == ["en"]
    assert [t for s, t in te_doen if s == "b"] == []
    assert len([t for s, t in te_doen if s == "c"]) == 14


def test_a_local_check_goes_only_to_english_and_an_international_one_everywhere(tmp_path):
    # PO 2026-11-20 ("Yes, set it up"): een lokale check alleen naar het Engels, waar de redactie haar leest; een
    # internationale naar alle talen; een lokale Engelse check nergens heen
    lokaal_nl = _c(sleutel="a", taal="nl", reikwijdte="lokaal")
    lokaal_en = _c(sleutel="b", taal="en", reikwijdte="lokaal")
    internationaal = _c(sleutel="c", taal="nl", reikwijdte="internationaal")
    te_doen = ev.nog_te_doen([lokaal_nl, lokaal_en, internationaal], tmp_path)
    assert [t for s, t in te_doen if s == "a"] == ["en"]
    assert [t for s, t in te_doen if s == "b"] == []
    assert len([t for s, t in te_doen if s == "c"]) == 14


def test_the_weekly_limit_counts_only_this_week_and_takes_the_english_for_review_first():
    # $5 per week (PO 2026-11-20); wat niet past, schuift naar de week erna; eerst het Engels om na te lezen
    batches = [{"dag": "2026-11-16", "werkelijk": 3.0}, {"dag": "2026-11-12", "werkelijk": 9.0}, {"werkelijk": 4.0},
               {"dag": "2026-11-18", "schatting": 1.0, "werkelijk": None}]
    assert ev.weekbedrag(batches, "2026-11-20") == 4.0
    c1, c2 = _c(sleutel="a", taal="tr", status="concept"), _c(sleutel="b", taal="nl")
    vragen = [("b", t) for t in ev.doeltalen(c2)] + [("a", "en")]
    gekozen = ev.binnen_grens([c1, c2], vragen, ruimte=ev.schatting([c1, c2], [("a", "en"), ("b", "en")]) + 1e-9)
    assert gekozen[0] == ("a", "en") and len(gekozen) == 2
    assert ev.schatting([c1, c2], gekozen) <= ev.schatting([c1, c2], [("a", "en"), ("b", "en")]) + 1e-9


def test_a_changed_field_is_asked_again_alone_and_merged_into_the_translation(tmp_path):
    # een zin uit Wat we niet weten weg (PO 2026-11-20) mag niet de hele check in veertien talen opnieuw kosten: alleen het
    # veld dat veranderde gaat naar het model, en het komt terug in de vertaling die er lag
    c = _c(niet_weten="We weten niet wie het beeld maakte [1]. De post konden we niet openen [1].")
    oud = ev.bestand(c, "de", {**_vertaald(c), "niet_weten": "Alt [1]."}, "m")
    nieuw_c = {**c, "niet_weten": "We weten niet wie het beeld maakte [1]."}
    assert not ev.geldig(nieuw_c, oud)
    assert ev.gewijzigd(nieuw_c, oud) == ["niet_weten"]
    vraag = json.loads(ev.verzoek(nieuw_c, "de", ["niet_weten"])["messages"][0]["content"])
    assert list(vraag["velden"]) == ["niet_weten"]
    samen = ev.samenvoegen(nieuw_c, "de", oud, {"niet_weten": "Neu [1]."}, "m2")
    assert ev.geldig(nieuw_c, samen) and samen["velden"]["niet_weten"] == "Neu [1]." and samen["velden"]["kop"] == oud["velden"]["kop"]
    assert ev.gewijzigd(nieuw_c, {k: v for k, v in oud.items() if k != "veldafdrukken"}) is None   # oud bestand: alles


def test_the_plan_asks_only_the_changed_fields_and_estimates_them_so(tmp_path):
    c = _c(sleutel="a", niet_weten="Een zin [1]. Nog een zin die we wegdoen [1].")
    p = ev.pad("a", "de", tmp_path)
    ev.schrijf(p, ev.bestand(c, "de", _vertaald(c), "m"))
    nieuw_c = {**c, "niet_weten": "Een zin [1]."}
    assert ("a", "de") in ev.nog_te_doen([nieuw_c], tmp_path)
    delen = ev.delen([nieuw_c], [("a", "de")], tmp_path)
    assert delen == {("a", "de"): ["niet_weten"]}
    assert ev.schatting([nieuw_c], [("a", "de")], delen) < ev.schatting([nieuw_c], [("a", "de")]) / 3


def test_a_translation_the_editors_read_counts_as_read_only_while_its_text_is_unchanged(tmp_path):
    """PLAN #37.11 (PO 2026-11-21: "ja dat ook graag"): een vertaling die de redactie las, mag naar zoekmachines; wordt ze
    opnieuw gemaakt, dan geldt het lezen niet meer."""
    c = _c()
    p = ev.pad(c["sleutel"], "en", tmp_path)
    velden = _vertaald(c)
    ev.schrijf(p, ev.bestand(c, "en", velden, "sonnet"))
    assert ev.geldige(c, tmp_path)["en"]["nagelezen"] is False

    ev.nagelezen(c, "en", "De redactie van Factiz", "2026-11-21", tmp_path)
    v = json.loads(p.read_text(encoding="utf-8"))
    assert list(v)[0] == "_meta" and v["nagelezen"]["door"] == "De redactie van Factiz"
    assert ev.geldige(c, tmp_path)["en"]["nagelezen"] is True

    # een nieuwe vertaling van een veld: het lezen telt niet meer
    ev.schrijf(p, ev.samenvoegen(c, "en", v, {"kop": "EN Another headline"}, "sonnet"))
    assert ev.geldige(c, tmp_path)["en"]["nagelezen"] is False


def test_only_a_valid_translation_in_a_language_the_editors_read_can_be_marked_read(tmp_path):
    import pytest

    c = _c()
    velden = _vertaald(c, "X")
    ev.schrijf(ev.pad(c["sleutel"], "de", tmp_path), ev.bestand(c, "de", velden, "sonnet"))
    with pytest.raises(ValueError, match="leest de redactie niet"):
        ev.nagelezen(c, "de", "De redactie van Factiz", "2026-11-21", tmp_path)
    with pytest.raises(ValueError, match="geen geldige vertaling"):
        ev.nagelezen(c, "en", "De redactie van Factiz", "2026-11-21", tmp_path)
    # een vertaling in een taal die de redactie niet leest, is nooit gelezen, ook niet met een merk erin
    p = ev.pad(c["sleutel"], "de", tmp_path)
    v = json.loads(p.read_text(encoding="utf-8"))
    ev.schrijf(p, {**v, "nagelezen": {"door": "x", "datum": "2026-11-21", "afdruk": ev.tekstafdruk(v["velden"])}})
    assert ev.geldige(c, tmp_path)["de"]["nagelezen"] is False


def test_an_answer_that_leaves_a_text_in_the_source_language_or_keeps_the_original_beside_it_does_not_count():
    """2026-11-23: Sonnet liet 41 beweringen van 22 checks onvertaald (de Engelse versie van een Nederlandse bewering was
    Nederlands), en zette één keer het origineel voor de Japanse vertaling."""
    velden = {"kop": "Trump", "bewering": "Het standbeeld van Anne Frank in Amsterdam is beklad.", "tekst": "Het klopt niet [1]."}
    goed = {"kop": "Trump", "bewering": "The statue of Anne Frank in Amsterdam was defaced.", "tekst": "It is false [1]."}
    assert ev.lees_antwoord(json.dumps(goed), velden) == goed           # een naam of kort woord mag gelijk blijven
    assert ev.lees_antwoord(json.dumps({**goed, "bewering": velden["bewering"]}), velden) is None
    assert ev.lees_antwoord(json.dumps({**goed, "bewering": f"{velden['bewering']} Vertaald: {goed['bewering']}"}), velden) is None
    assert ev.onvertaald(velden, {**goed, "bewering": f" {velden['bewering']} "}) == ["bewering"]
    # en de vraag zegt het het model ook
    assert "Never leave it in the source language" in ev.verzoek(_c(), "en")["system"]


def test_an_untranslated_text_already_on_disk_stops_counting_and_only_that_field_is_asked_again(tmp_path):
    c = _c(sleutel="a")
    p = ev.pad("a", "en", tmp_path)
    ev.schrijf(p, ev.bestand(c, "en", {**_vertaald(c), "bewering": c["bewering"]}, "m"))
    assert not ev.geldig(c, json.loads(p.read_text(encoding="utf-8")))
    assert ev.geldige(c, tmp_path) == {}                                # zo komt ze in geen uitgave
    assert ("a", "en") in ev.nog_te_doen([c], tmp_path)
    assert ev.delen([c], [("a", "en")], tmp_path) == {("a", "en"): ["bewering"]}
    samen = ev.samenvoegen(c, "en", json.loads(p.read_text(encoding="utf-8")), {"bewering": "The statue was defaced."}, "m2")
    assert ev.geldig(c, samen) and samen["velden"]["kop"] == _vertaald(c)["kop"]
