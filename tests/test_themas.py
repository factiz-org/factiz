"""Thema's voor het platform (PLAN #33.4, SPECS E9.S5): eerst verkennen wat er is, dan een lijst toetsen."""

import json

import pytest

from doublecheck.sitetalen import SITETALEN

from doublecheck import themas as th

def _n(nl, en):
    return {"nl": nl, "en": en, "de": en, "es": en, "fr": en}


LIJST = {"_meta": {"toelichting": "proeflijst"}, "themas": [
    {"sleutel": "gezondheid", "naam": _n("Gezondheid", "Health"), "omschrijving": "Diseases, medicine, food.",
     "onderdelen": [{"sleutel": "vaccins", "naam": _n("Vaccins", "Vaccines"), "hint": "any vaccine"},
                    {"sleutel": "corona", "naam": _n("Corona", "Covid-19")}]},
    {"sleutel": "oorlog", "naam": _n("Oorlog en conflict", "War and conflict"), "omschrijving": "Wars.",
     "onderdelen": [{"sleutel": "oekraine", "naam": _n("Oekraïne", "Ukraine")}]},
] + [{"sleutel": f"thema-{i}", "naam": _n(f"Thema {i}", f"Theme {i}"), "omschrijving": "x", "onderdelen": []}
     for i in range(6)]}


def test_the_exploring_question_shows_the_claim_and_asks_for_a_subject_a_broad_field_and_a_country():
    from doublecheck.modellen import MODELLEN

    p = th.verkenverzoek("Las vacunas contienen microchips " * 60, "es")
    assert p["model"] == MODELLEN["haiku"]["id"] and p["max_tokens"] >= 2000
    tekst = p["messages"][0]["content"][0]["text"]
    assert "Las vacunas contienen microchips" in tekst and "(es)" in tekst and len(tekst) < 800     # een lange tekst wordt ingekort
    schema = p["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"onderwerp", "breed", "land"}
    assert set(schema["properties"]["breed"]["enum"]) == set(th.BREED) and "other" in th.BREED


def test_an_exploring_answer_is_tidied_and_an_unreadable_one_counts_for_nothing():
    a = th.lees_verkenning(json.dumps({"onderwerp": "  COVID-19   Vaccines ", "breed": "health", "land": "India"}))
    assert a == {"onderwerp": "covid-19 vaccines", "breed": "health", "land": "India"}
    assert th.lees_verkenning(json.dumps({"onderwerp": "x", "breed": "health", "land": "none"}))["land"] == ""
    assert th.lees_verkenning(json.dumps({"onderwerp": "x", "breed": "astrology", "land": ""}))["breed"] == "other"
    for kapot in ("kapot", None, json.dumps(["x"]), json.dumps({"onderwerp": "", "breed": "health", "land": ""})):
        assert th.lees_verkenning(kapot) is None


def test_a_list_of_themes_must_be_short_closed_and_two_levels_deep_at_most(tmp_path):
    pad = tmp_path / "lijst.json"
    pad.write_text(json.dumps(LIJST), encoding="utf-8")
    lijst = th.lees_lijst(pad)
    assert [t["sleutel"] for t in lijst][:2] == ["gezondheid", "oorlog"] and len(lijst) == 8

    def kapot(wijzig):
        d = json.loads(json.dumps(LIJST))
        wijzig(d)
        pad.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(th.Weigering):
            th.lees_lijst(pad)

    kapot(lambda d: d["themas"].__delitem__(slice(3, None)))                                 # te weinig thema's
    kapot(lambda d: d["themas"].extend(dict(d["themas"][2], sleutel=f"extra-{i}") for i in range(9)))   # te veel
    kapot(lambda d: d["themas"].append(dict(d["themas"][0])))                                # twee keer dezelfde sleutel
    kapot(lambda d: d["themas"][0].__setitem__("sleutel", "Gezondheid & Zo"))                # geen nette sleutel
    kapot(lambda d: d["themas"][0]["naam"].pop("en"))                                        # een naam ontbreekt
    kapot(lambda d: d["themas"][0]["onderdelen"][0]["naam"].pop("fr"))                       # ook niet in het Frans
    kapot(lambda d: d["themas"][0]["onderdelen"][0].__setitem__("onderdelen", [{}]))         # een derde niveau
    kapot(lambda d: d["themas"][0]["onderdelen"].extend(
        {"sleutel": f"o{i}", "naam": _n("x", "x")} for i in range(12)))                     # te veel onderdelen


def test_the_sorting_question_offers_only_the_list_and_the_answer_cannot_leave_it():
    lijst = LIJST["themas"]
    p = th.indeelverzoek("Vaccines contain microchips", "en", lijst)
    assert "gezondheid" in p["system"] and "vaccins" in p["system"] and "Diseases, medicine, food." in p["system"]
    schema = p["output_config"]["format"]["schema"]
    assert set(schema["properties"]["thema"]["enum"]) == {t["sleutel"] for t in lijst} | {"anders"}
    assert set(schema["properties"]["tweede"]["enum"]) == {t["sleutel"] for t in lijst} | {"geen"}

    def lees(**a):
        return th.lees_indeling(json.dumps(a), lijst)

    assert lees(thema="gezondheid", onderdeel="vaccins", tweede="geen") == {
        "thema": "gezondheid", "onderdeel": "vaccins", "tweede": ""}
    # een onderdeel van een ander thema hoort er niet bij; het thema blijft
    assert lees(thema="gezondheid", onderdeel="oekraine", tweede="oorlog") == {
        "thema": "gezondheid", "onderdeel": "", "tweede": "oorlog"}
    assert lees(thema="gezondheid", onderdeel="", tweede="gezondheid")["tweede"] == ""      # twee keer hetzelfde is één
    # twijfel versoepelt nooit: een thema buiten de lijst is geen thema
    assert lees(thema="astrologie", onderdeel="x", tweede="geen") == {"thema": "anders", "onderdeel": "", "tweede": ""}
    assert lees(thema="anders", onderdeel="vaccins", tweede="oorlog") == {"thema": "anders", "onderdeel": "", "tweede": ""}
    assert th.lees_indeling("kapot", lijst) is None and th.lees_indeling(None, lijst) is None


def test_a_sample_is_the_same_every_time_and_never_overlaps_an_earlier_one():
    nummers = [f"{i:016x}" for i in range(1000)]
    een = th.steekproef(nummers, 100, zaad=1)
    assert een == th.steekproef(nummers, 100, zaad=1) and len(set(een)) == 100
    twee = th.steekproef(nummers, 100, zaad=2, zonder=set(een))
    assert not set(een) & set(twee) and len(twee) == 100
    assert len(th.steekproef(nummers[:10], 100, zaad=1)) == 10


def test_the_counts_show_the_broad_fields_the_commonest_subjects_and_how_much_falls_outside_a_list():
    verkend = [{"onderwerp": "covid-19 vaccines", "breed": "health", "land": "India"},
               {"onderwerp": "covid-19 vaccines", "breed": "health", "land": ""},
               {"onderwerp": "us election", "breed": "elections", "land": "United States"}, None]
    t = th.telling_verkenning(verkend)
    assert t["gelezen"] == 3 and t["onleesbaar"] == 1 and t["breed"] == {"health": 2, "elections": 1}
    assert t["onderwerpen"]["health"][0] == ("covid-19 vaccines", 2) and t["landen"][0] == ("India", 1)
    ingedeeld = [{"thema": "gezondheid", "onderdeel": "vaccins", "tweede": ""},
                 {"thema": "gezondheid", "onderdeel": "", "tweede": "oorlog"},
                 {"thema": "anders", "onderdeel": "", "tweede": ""}, None]
    u = th.telling_toets(ingedeeld)
    assert u["gelezen"] == 3 and u["anders"] == 1 and u["aandeel_anders"] == pytest.approx(1 / 3, abs=0.001)
    assert u["themas"] == {"gezondheid": 2} and u["onderdelen"] == {"gezondheid": {"vaccins": 1, "": 1}}
    assert u["met_tweede"] == 1


def test_spending_past_the_limit_is_refused():
    th.binnen_grens(0.2, 0.5, grens=1.0)
    with pytest.raises(th.Weigering):
        th.binnen_grens(0.6, 0.5, grens=1.0)


# --- de vastgestelde lijst, tien per vraag, en het land ---------------------------------------------------------------

def test_the_approved_list_is_valid_and_names_every_theme_and_part_in_every_site_language():
    lijst = th.lees_lijst(th.LIJST_PAD)
    assert len(lijst) == 13 and sum(len(t["onderdelen"]) for t in lijst) == 42
    assert {t["sleutel"] for t in lijst} >= {"politics", "health", "war", "elections", "migration", "climate"}
    for t in lijst:
        for ding in [t] + t["onderdelen"]:
            assert set(ding["naam"]) == set(SITETALEN) and all(v.strip() for v in ding["naam"].values())


def test_a_country_is_a_two_letter_code_from_the_official_list_or_nothing():
    assert len(th.LANDEN) == 250 and {"NL", "IN", "US", "BR", "UA", "XK"} <= th.LANDEN      # 249 landen en Kosovo
    assert th.land("nl") == "NL" and th.land(" IN ") == "IN"
    for geen in ("Netherlands", "XX", "EU", "", None, "N", 12):
        assert th.land(geen) == ""


def test_ten_claims_go_into_one_question_each_with_its_number():
    lijst = LIJST["themas"]
    p = th.indeelverzoek_meer([("Vaccines contain microchips", "en"), ("Las vacunas causan autismo " * 60, "es")], lijst)
    tekst = p["messages"][0]["content"][0]["text"]
    assert "1. (en) Vaccines contain microchips" in tekst and "\n2. (es) Las vacunas causan autismo" in tekst
    assert len(tekst) < 1200                                                      # een lange bewering wordt ingekort
    assert '"vaccins" (Vaccines: any vaccine)' in p["system"] and "ISO" in p["system"] and "rare" in p["system"]
    item = p["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]
    assert set(item["required"]) == {"nr", "thema", "onderdeel", "tweede", "land"}
    assert set(item["properties"]["thema"]["enum"]) == {t["sleutel"] for t in lijst} | {"anders"}


def test_answers_are_matched_by_number_and_a_missing_or_doubled_number_counts_for_nothing():
    lijst = LIJST["themas"]
    antwoord = json.dumps({"antwoorden": [
        {"nr": 1, "thema": "gezondheid", "onderdeel": "vaccins", "tweede": "geen", "land": "in"},
        {"nr": 3, "thema": "oorlog", "onderdeel": "", "tweede": "geen", "land": ""},
        {"nr": 3, "thema": "gezondheid", "onderdeel": "", "tweede": "geen", "land": ""},
        {"nr": 4, "thema": "astrologie", "onderdeel": "vaccins", "tweede": "oorlog", "land": "Atlantis"},
        {"nr": 9, "thema": "oorlog", "onderdeel": "", "tweede": "geen", "land": ""},
        "rommel"]})
    uit = th.lees_indeling_meer(antwoord, lijst, 5)
    assert uit[0] == {"thema": "gezondheid", "onderdeel": "vaccins", "tweede": "", "land": "IN"}
    assert uit[1] is None                # nummer 2 ontbreekt
    assert uit[2] is None                # nummer 3 staat er twee keer: welke geldt, is niet te zeggen
    assert uit[3] == {"thema": "anders", "onderdeel": "", "tweede": "", "land": ""}
    assert uit[4] is None
    assert th.lees_indeling_meer("kapot", lijst, 2) == [None, None]
    assert th.lees_indeling_meer(json.dumps({"antwoorden": "x"}), lijst, 1) == [None]


def test_groups_of_ten_and_how_often_two_runs_agree():
    assert th.groepen(list(range(25)), 10) == [list(range(10)), list(range(10, 20)), list(range(20, 25))]
    a = {"1": {"thema": "health", "onderdeel": "covid", "tweede": "", "land": "IN"},
         "2": {"thema": "war", "onderdeel": "", "tweede": "", "land": ""},
         "3": {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"}, "4": None}
    b = {"1": {"thema": "health", "onderdeel": "vaccines", "tweede": "", "land": "IN"},
         "2": {"thema": "world", "onderdeel": "", "tweede": "", "land": ""},
         "3": {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "RU"}, "4": {"thema": "war"}}
    assert th.overeenkomst(a, b) == {"beide": 3, "zelfde_thema": 2, "zelfde_onderdeel": 1, "zelfde_land": 2}


# --- de poort: pas tonen na de 200 van de PO (SPECS E9.S5 AC3) -----------------------------------------------------------

def _po(pad, goed, fout, twijfel=0, door="PO"):
    labels = ({f"{i:016x}": "goed" for i in range(goed)} | {f"f{i:015x}": "fout" for i in range(fout)}
              | {f"e{i:015x}": "twijfel" for i in range(twijfel)})
    pad.write_text(json.dumps({"toelichting": "x", "gelezen_door": door, "labels": labels}), encoding="utf-8")


def test_themes_are_shown_only_after_the_owner_read_two_hundred_and_found_ninety_percent_right(tmp_path):
    pad = tmp_path / "po.json"
    assert th.poort(pad) == (False, "de PO heeft nog niets gelezen")
    _po(pad, 179, 21)
    assert th.poort(pad)[0] is False and "179 van de 200" in th.poort(pad)[1]
    _po(pad, 180, 20)
    assert th.poort(pad) == (True, "180 van de 200 goed")
    _po(pad, 200, 0, door="Claude")                      # alleen de lezing van de PO opent de poort
    assert th.poort(pad)[0] is False
    pad.write_text("kapot", encoding="utf-8")
    assert th.poort(pad)[0] is False


def test_fewer_cards_are_enough_only_when_they_carry_ninety_percent_with_ninety_five_percent_certainty(tmp_path):
    pad = tmp_path / "po.json"
    for goed, fout, open_ in [(28, 0, False), (29, 0, True), (44, 1, False), (45, 1, True), (59, 2, True),
                              (150, 10, False), (162, 0, True)]:
        _po(pad, goed, fout)
        assert th.poort(pad)[0] is open_, (goed, fout)
    _po(pad, 150, 10)
    assert "150 van de 160" in th.poort(pad)[1]
    # een kaart waar de PO twijfelde en niet koos, telt als gelezen en niet goed: twijfel versoepelt nooit
    _po(pad, 29, 0, twijfel=1)
    assert th.poort(pad)[0] is False and "29 van de 30" in th.poort(pad)[1]
    _po(pad, 162, 0, twijfel=1)
    assert th.poort(pad) == (True, "162 van de 163 goed")
    _po(pad, 29, 0, door="Claude")
    assert th.poort(pad)[0] is False


# --- de volle ronde: wat nog gevraagd moet worden ------------------------------------------------------------------------

def test_a_claim_without_a_readable_answer_is_asked_again_and_one_in_a_running_batch_is_not():
    rijen = [{"nummer": "a", "uit": {"thema": "health"}}, {"nummer": "b", "uit": None}]
    kaart = [{"custom_id": "th-0", "nummers": ["a", "b"], "batch": "klaar"},
             {"custom_id": "th-1", "nummers": ["c"], "batch": "loopt"}]
    batches = [{"id": "klaar", "werkelijk": 0.01}, {"id": "loopt"}]
    # a heeft een thema; b kreeg geen leesbaar antwoord en gaat opnieuw; c zit in een batch die nog loopt; d is nieuw
    assert th.nog_te_vragen(["a", "b", "c", "d"], rijen, kaart, batches) == ["b", "d"]
    assert th.nog_te_vragen(["a", "b"], rijen + [{"nummer": "b", "uit": {"thema": "war"}}], kaart, batches) == []


# --- de nakijkronde van de PO: 200 kaarten, en wat haar keuzes betekenen ------------------------------------------------

def _lijst_klein():
    def n(naam):
        return {t: naam for t in th.SITETALEN}
    return [{"sleutel": "health", "naam": n("Gezondheid"), "onderdelen": [{"sleutel": "vaccines", "naam": n("Vaccins")}]},
            {"sleutel": "war", "naam": n("Oorlog"), "onderdelen": []}]


def test_the_review_cards_are_only_claims_with_a_theme_that_the_owner_can_read_and_was_not_shown_before():
    paginas = {f"{i:016x}": (f"claim {i}", "en") for i in range(40)}
    paginas["hindi"] = ("यह दावा", "hi")                       # geen vertaling: niet te lezen
    paginas["tamil"] = ("இது ஒரு கூற்று", "ta")                 # met vertaling: wel
    paginas["anders"] = ("something else", "en")
    paginas["eerder"] = ("seen before", "en")
    uit = {"thema": "health", "onderdeel": "vaccines", "tweede": "war", "land": "IN"}
    indeling = {nr: uit for nr in paginas} | {"anders": {"thema": "anders", "onderdeel": "", "tweede": "", "land": ""}}
    landen = {"IN": {"nl": "India"}}
    kaarten = th.po_kaarten(paginas, indeling, {"tamil": "This is a claim"}, _lijst_klein(), landen, n=41,
                            zonder={"eerder"})
    ids = {k["id"] for k in kaarten}
    assert len(kaarten) == 41 and ids == set(paginas) - {"hindi", "anders", "eerder"}
    tamil = next(k for k in kaarten if k["id"] == "tamil")
    assert tamil == {"id": "tamil", "bewering": "இது ஒரு கூற்று", "taal": "ta", "richting": "ltr",
                     "vertaling": "This is a claim", "thema": "Gezondheid", "onderdeel": "Vaccins", "tweede": "Oorlog",
                     "land": "India"}
    assert next(k for k in kaarten if k["taal"] == "en")["vertaling"] == ""
    # hetzelfde zaad geeft dezelfde kaarten in dezelfde volgorde; een kleinere steekproef is geen nieuwe volgorde
    zelfde = th.po_kaarten(paginas, indeling, {"tamil": "This is a claim"}, _lijst_klein(), landen, n=41, zonder={"eerder"})
    assert [k["id"] for k in zelfde] == [k["id"] for k in kaarten]
    assert len(th.po_kaarten(paginas, indeling, {}, _lijst_klein(), landen, n=10)) == 10


def test_the_gate_counts_the_theme_and_the_other_fields_are_counted_on_their_own():
    kaarten = [{"id": "a", "thema": "Gezondheid", "onderdeel": "Vaccins", "tweede": "", "land": "India"},
               {"id": "b", "thema": "Gezondheid", "onderdeel": "", "tweede": "Oorlog", "land": "India"},
               {"id": "c", "thema": "Oorlog", "onderdeel": "", "tweede": "", "land": ""},
               {"id": "d", "thema": "Oorlog", "onderdeel": "", "tweede": "", "land": "India"},
               {"id": "e", "thema": "Oorlog", "onderdeel": "", "tweede": "", "land": ""}]
    keuzes = {"a": {"oordeel": "goed", "opmerking": " grijs gebied: kan ook politiek zijn "},
              "b": {"oordeel": "fout", "mis": ["land", "tweede"], "opmerking": "gaat over Nepal"},   # het thema klopt wel
              "c": {"oordeel": "fout", "mis": ["thema"]},
              "d": {"oordeel": "fout", "mis": []},          # niet gezegd wat er mis is: dan telt het thema als fout
              "x": {"oordeel": "goed"},                     # geen kaart van deze ronde
              "e": {"oordeel": None, "opmerking": "nog niet gekozen, eerst nazoeken"}}   # geen keuze, wel een notitie
    u = th.po_uitslag(kaarten, keuzes)
    # e kreeg een notitie en geen keuze: de PO twijfelde, en dat telt bij de poort als niet goed
    assert u["labels"] == {"a": "goed", "b": "goed", "c": "fout", "d": "fout", "e": "twijfel"}
    assert u["velden"] == {"thema": {"met": 4, "fout": 2}, "onderdeel": {"met": 1, "fout": 0},
                           "tweede": {"met": 1, "fout": 1}, "land": {"met": 3, "fout": 1}}
    # een notitie hoort bij elke kaart: bij een die klopt, bij een die niet klopt en bij een die nog open is
    assert u["opmerkingen"] == {"a": "grijs gebied: kan ook politiek zijn", "b": "gaat over Nepal",
                                "e": "nog niet gekozen, eerst nazoeken"}


def test_the_review_page_carries_the_cards_as_data_that_cannot_close_its_own_script_tag():
    kaarten = [{"id": "a", "bewering": 'He said </script><script>alert(1)</script>', "taal": "en", "richting": "ltr",
                "vertaling": "", "thema": "Gezondheid", "onderdeel": "", "tweede": "", "land": ""}]
    html = th.po_pagina(kaarten)
    assert "/*KAARTEN*/" not in html and html.count("</script>") == 2          # de twee van het sjabloon zelf
    begin = html.index('id="data">') + len('id="data">')
    data = json.loads(html[begin:html.index("</script>", begin)])
    assert data == {"ronde": "33-4", "nodig": 180, "kaarten": kaarten}
    assert "—" not in html and "<title>Thema's nakijken</title>" in html
