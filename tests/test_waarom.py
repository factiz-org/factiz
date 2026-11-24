"""Waarom het niet klopt (PLAN #34.2j): hoogstens drie korte punten uit de weerlegging van de redactie, elk met een
citaat dat er letterlijk in staat. Een punt dat de bron niet draagt, staat er nooit; naar de site pas na een leesproef
van 200 zonder één punt dat niet gedragen wordt."""

import json

from doublecheck import waarom as w

BRON = ("Recurring pro-Kremlin disinformation narrative about Ukraine being a Nazi state.In the 2019 parliamentary "
        "elections, the far-right Svoboda party won 2.15% of the vote and failed to enter parliament. President "
        "Zelenskyy, who is Jewish, won the presidential election with 73% of the vote.")


def _antwoord(*punten):
    return json.dumps({"punten": [{"punt": p, "citaat": c} for p, c in punten]})


def test_a_point_counts_only_when_its_quote_is_literally_in_the_disproof():
    gelezen = w.lees(_antwoord(
        ("In the 2019 parliamentary elections, the far-right Svoboda party won 2.15% of the vote.",
         "In the 2019 parliamentary elections, the far-right Svoboda party won 2.15% of the vote"),
        ("Zelenskyy is Jewish.", "President Zelensky is a Jew")), BRON)
    assert [p["punt"] for p in gelezen] == ["In the 2019 parliamentary elections, the far-right Svoboda party won 2.15% of the vote."]


def test_every_number_in_a_point_must_be_in_its_quote():
    gelezen = w.lees(_antwoord(
        ("Svoboda won only 3% of the vote.", "the far-right Svoboda party won 2.15% of the vote"),
        ("Zelenskyy won 73% of the vote.", "won the presidential election with 73% of the vote")), BRON)
    assert [p["punt"] for p in gelezen] == ["Zelenskyy won 73% of the vote."]


def test_a_quote_matches_despite_spacing_quote_marks_and_capitals():
    gelezen = w.lees(_antwoord(("Zelenskyy is Jewish.", "president  ZELENSKYY, who is Jewish")), BRON)
    assert len(gelezen) == 1


def test_at_most_three_short_points_and_never_an_empty_one():
    lang = " ".join(["word"] * 31)
    citaat = "the far-right Svoboda party won 2.15% of the vote"
    punten = [f"The far-right Svoboda party won 2.15% of the vote{'!' * i}" for i in range(5)]
    gelezen = w.lees(_antwoord(("", citaat), (lang, citaat), *[(p, citaat) for p in punten]), BRON)
    assert [p["punt"] for p in gelezen] == punten[:3]


def test_an_unreadable_answer_gives_no_points():
    for tekst in ("geen json", None, '{"punten": "x"}', '{"punten": [{"punt": 1}]}'):
        assert w.lees(tekst, BRON) == []


def test_each_page_gets_the_newest_case_with_a_disproof():
    checks = {"p1": [("2019-01-01", "https://euvsdisinfo.eu/report/oud"), ("2021-05-05", "https://euvsdisinfo.eu/report/nieuw"),
                     ("2023-01-01", "https://euvsdisinfo.eu/report/zonder-geval")],
              "p2": [("2020-01-01", "https://snopes.com/x")]}
    gevallen = {"/report/oud": {"weerlegging": "a"}, "/report/nieuw": {"weerlegging": "b"}}
    assert w.koppel(checks, gevallen) == {"p1": "/report/nieuw"}


def _labels(tmp_path, n, fout=0, regels=None, lezer=None):
    paginas = {f"p{i}": {"punten": ["niet_gedragen" if i < fout else "gedragen", "zwak"]} for i in range(n)}
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"versie": w.VERSIE, "regels": regels or w.REGELS, "lezer": lezer or w.LEZER_NAAM,
                               "paginas": paginas}), encoding="utf-8")
    return pad


def test_the_gate_opens_only_after_200_pages_with_at_most_one_in_a_hundred_unsupported_points(tmp_path):
    """B77 (PO 2026-11-12): hoogstens 1 op de 100 punten niet gedragen, naar boven afgerond op een hele fout. De
    leesproef van `_labels` heeft twee punten per pagina, dus 400 punten: 4 fouten mag, 5 niet."""
    assert w.poort(_labels(tmp_path, 200))[0] is True
    assert w.poort(_labels(tmp_path, 200, fout=4))[0] is True
    assert w.poort(_labels(tmp_path, 200, fout=5))[0] is False
    assert w.poort(_labels(tmp_path, 199))[0] is False
    assert w.poort(tmp_path / "bestaat-niet.json")[0] is False


def test_the_measured_margin_of_the_second_reading_test_is_exactly_what_the_po_accepted():
    """3 van 292: 1,03%, naar boven afgerond op een hele fout binnen 1%; een vierde fout zou er niet in passen."""
    assert w.mag_fouten(292) == 3 and w.mag_fouten(300) == 3 and w.mag_fouten(301) == 4 and w.mag_fouten(0) == 0


def test_a_point_that_adds_what_its_sentence_does_not_say_falls_away():
    """De inhoudswoorden van een punt staan in de zin van zijn citaat; een punt dat er iets bij verzint, valt weg."""
    gelezen = w.lees(_antwoord(
        ("Svoboda won 2.15% and the EU does not recognise the result.", "the far-right Svoboda party won 2.15% of the vote"),
        ("Zelenskyy, who is Jewish, won the presidential election.", "who is Jewish, won the presidential election")), BRON)
    # de naam staat niet in het citaat maar wel in zijn zin: die telt mee
    assert [p["punt"] for p in gelezen] == ["Zelenskyy, who is Jewish, won the presidential election."]


def test_no_evidence_is_about_the_claim_never_about_the_disproof():
    bron = "No evidence given. The allegation aims to discredit critical writers."
    gelezen = w.lees(_antwoord(("The disproof gives no evidence supporting the claim.", "No evidence given.")), bron)
    assert gelezen == []



def test_the_reading_shows_the_quote_in_its_own_sentences():
    """De leesproef (PLAN #34.2j): bij elk punt het citaat gemarkeerd, met de tekst ervoor en erna in de eigen
    hoofdletters, ook als het citaat met andere spaties of hoofdletters werd gegeven."""
    rond = w.rond(BRON, "president  ZELENSKYY, who is Jewish", breedte=40)
    assert "«President Zelenskyy, who is Jewish»" in rond
    assert rond.startswith("…") and "failed to enter parliament." in rond
    assert w.rond(BRON, "niet in de bron") == ""


# De coderegels na de leesproef (PLAN #34.2j, PO 2026-11-12: "Ja, de coderegels").
NAVO = ("As stated in the Brussels Summit Declaration from 11 July 2018, NATO is a defensive Alliance. Its greatest "
        "responsibility is to protect and defend the territories and populations of all member countries against attack. "
        "Read similar disinformation case here.")
HV = ("The US is an important ally to the EU but the latter's policy is not determined by the US, as explained by the EU "
      "High Representative. There is no wish or desire to start a war with Russia. The US is a founding member of NATO.")


def test_the_sentence_of_a_quote_ends_where_the_quote_ends():
    """Eindigt een citaat met een punt, dan telt de zin erna niet mee voor de inhoudswoorden (10d12484)."""
    punt = ("NATO is a defensive Alliance whose greatest responsibility is protecting and defending the territories and "
            "populations of its member countries, according to the Brussels Summit Declaration of 11 July 2018.")
    citaat = "As stated in the Brussels Summit Declaration from 11 July 2018, NATO is a defensive Alliance."
    assert w.lees(_antwoord((punt, citaat)), NAVO) == []
    kort = "As stated in the Brussels Summit Declaration of 11 July 2018, NATO is a defensive Alliance."
    assert len(w.lees(_antwoord((kort, citaat)), NAVO)) == 1


def test_a_point_that_makes_someone_say_something_rests_on_a_quote_of_one_sentence():
    """Wie iets laat zeggen, mag er geen tweede zin bij trekken: de Hoge Vertegenwoordiger zei de eerste, niet de
    tweede (16df53c9)."""
    punt = ("The EU High Representative explained that EU policy is not determined by the US and that there is no wish "
            "to start a war with Russia.")
    citaat = ("the latter's policy is not determined by the US, as explained by the EU High Representative. There is no "
              "wish or desire to start a war with Russia.")
    assert w.lees(_antwoord((punt, citaat)), HV) == []
    een = "The EU High Representative explained that EU policy is not determined by the US."
    een_zin = "the latter's policy is not determined by the US, as explained by the EU High Representative"
    assert len(w.lees(_antwoord((een, een_zin)), HV)) == 1
    # zonder iemand die iets zegt, mag een citaat van twee zinnen
    zonder = "EU policy is not determined by the US, and there is no wish to start a war with Russia."
    assert len(w.lees(_antwoord((zonder, citaat)), HV)) == 1


def test_a_bare_no_evidence_point_falls_away_next_to_a_real_one():
    """'The claim offers no evidence' zonder feit erbij zegt een lezer niets; staat er een ander punt, dan valt het weg.
    Staat het alleen, of zegt het er iets bij na een puntkomma, dan blijft het."""
    bron = ("No evidence given. The Christchurch shooter, a man named Brenton Tarrant, was a white supremacist. "
            "This claim offers no evidence and is based entirely on the statements of Igor Strelkov.")
    leeg = ("The claim offers no evidence.", "No evidence given")
    feit = ("The Christchurch shooter, Brenton Tarrant, was a white supremacist.", "Brenton Tarrant, was a white supremacist")
    met = ("The claim offers no evidence; it is based entirely on the statements of Igor Strelkov.",
           "offers no evidence and is based entirely on the statements of Igor Strelkov")
    assert [p["punt"] for p in w.lees(_antwoord(leeg, feit), bron)] == [feit[0]]
    assert [p["punt"] for p in w.lees(_antwoord(leeg), bron)] == [leeg[0]]
    assert [p["punt"] for p in w.lees(_antwoord(met, feit), bron)] == [met[0], feit[0]]


def test_the_rules_apply_again_to_points_that_were_kept_before():
    """De bewaarde punten van de ronde gingen door de oude regels; `herlees` legt de nieuwe erop, zonder nieuwe vraag."""
    oud = [{"punt": "The EU High Representative explained that EU policy is not determined by the US and that there is "
                    "no wish to start a war with Russia.",
            "citaat": "the latter's policy is not determined by the US, as explained by the EU High Representative. "
                      "There is no wish or desire to start a war with Russia."},
           {"punt": "The US is a founding member of NATO.", "citaat": "The US is a founding member of NATO."}]
    assert [p["punt"] for p in w.herlees(oud, HV)] == ["The US is a founding member of NATO."]
    assert w.herlees(oud, HV) == w.lees(json.dumps({"punten": oud}), HV)


def test_the_new_rules_are_counted_against_the_labels_of_the_reading_test():
    """Per label hoeveel punten de nieuwe regels houden en laten vallen, en welke pagina's alles kwijtraken."""
    paginas = {"a": {"punten": ["niet_gedragen", "gedragen"]}, "b": {"punten": ["zwak"]}}
    punten = {"a": [{"punt": "The EU High Representative explained that EU policy is not determined by the US and that "
                             "there is no wish to start a war with Russia.",
                     "citaat": "the latter's policy is not determined by the US, as explained by the EU High "
                               "Representative. There is no wish or desire to start a war with Russia."},
                    {"punt": "The US is a founding member of NATO.", "citaat": "The US is a founding member of NATO."}],
              "b": [{"punt": "There is no wish to start a war with Russia.", "citaat": "There is no wish or desire to start a war with Russia."}]}
    uit = w.vergelijk(paginas, punten, {"a": HV, "b": HV})
    assert uit["weg"] == {"niet_gedragen": 1} and uit["blijft"] == {"gedragen": 1, "zwak": 1}
    assert uit["leeg"] == [] and uit["weg_bij"] == {"niet_gedragen": ["a"]}


def test_a_reading_test_of_other_rules_never_opens_the_gate(tmp_path):
    """De labels gelden voor de regels waarmee de punten gelezen zijn: een leesproef van regels-v1 opent de poort niet
    voor regels-v2, ook niet zonder fout (zoals een vingerafdruk zijn modelversie draagt, DR6)."""
    assert w.poort(_labels(tmp_path, 200, regels="regels-v1"))[0] is False
    zonder = tmp_path / "zonder.json"
    zonder.write_text(json.dumps({"versie": w.VERSIE, "paginas": {f"p{i}": {"punten": ["gedragen"]} for i in range(200)}}),
                      encoding="utf-8")
    assert w.poort(zonder)[0] is False


# De tweede lezing (PLAN #34.2j, PO 2026-11-12: "Eerst de tweede lezing").
def _lezing(*oordelen):
    return json.dumps({"punten": [{"nummer": i + 1, "concedes": c, "drops_qualification": q, "adds": a, "reason": "r"}
                                  for i, (c, q, a) in enumerate(oordelen)]})


def test_the_second_reading_sees_the_claim_the_disproof_and_every_point_by_number():
    v = w.lezingverzoek("The corridor is blocked by terrorists.", "The corridor remained unused.",
                        [{"punt": "The corridor remained unused.", "citaat": "remained unused"},
                         {"punt": "People fear detention.", "citaat": "fear"}], "sonnet", versie="lezing-v1")
    vraag = v["messages"][0]["content"]
    assert "The corridor is blocked by terrorists." in vraag and "The corridor remained unused." in vraag
    assert "[1] The corridor remained unused." in vraag and "[2] People fear detention." in vraag
    assert v["output_config"]["format"]["type"] == "json_schema"


def test_a_point_stays_only_when_the_second_reading_says_no_three_times():
    assert w.lees_lezing(_lezing((False, False, False), (True, False, False), (False, False, True)), 3,
                         versie="lezing-v1") == [True, False, False]
    assert w.lees_lezing(_lezing((False, True, False)), 1, versie="lezing-v1") == [False]


def test_a_point_the_second_reading_did_not_answer_never_stays():
    """Twijfel versoepelt nooit: een punt zonder antwoord, of een antwoord dat zich niet laat lezen, laat niets staan."""
    assert w.lees_lezing(_lezing((False, False, False)), 2, versie="lezing-v1") == [True, False]
    for tekst in ("geen json", None, '{"punten": "x"}', json.dumps({"punten": [{"nummer": 1, "concedes": "nee"}]})):
        assert w.lees_lezing(tekst, 2, versie="lezing-v1") is None
    # een nummer dat niet bestaat, telt niet; twee antwoorden voor hetzelfde punt: het strengste
    dubbel = json.dumps({"punten": [
        {"nummer": 1, "concedes": False, "drops_qualification": False, "adds": False, "reason": ""},
        {"nummer": 1, "concedes": True, "drops_qualification": False, "adds": False, "reason": ""},
        {"nummer": 9, "concedes": False, "drops_qualification": False, "adds": False, "reason": ""}]})
    assert w.lees_lezing(dubbel, 1, versie="lezing-v1") == [False]


def test_the_second_reading_is_counted_against_the_labels():
    paginas = {"a": {"punten": ["niet_gedragen", "gedragen"]}, "b": {"punten": ["gedragen"]}}
    uit = w.vergelijk_lezing(paginas, {"a": [False, True], "b": None})
    assert uit["blijft"] == {"gedragen": 1} and uit["weg"] == {"niet_gedragen": 1, "gedragen": 1}
    assert uit["ongelezen"] == ["b"] and uit["weg_bij"]["niet_gedragen"] == ["a"]


# De scherpere vraag (PLAN #34.2j, PO 2026-11-12: "Scherpere vraag, ~$1").
BRON_V2 = ("Accusations of Viagra use were made by the US ambassador and the prosecutor. The claim remained controversial, "
           "as it could not be confirmed independently. Turnout was 61%.")
PUNTEN_V2 = [{"punt": "The prosecutor also made the Viagra accusation.", "citaat": "x"},
             {"punt": "Turnout was 61%, as the commission reported.", "citaat": "x"},
             {"punt": "Turnout was 61%.", "citaat": "x"}]


def _v2(*oordelen):
    velden = ("concedes", "concedes_words", "drops_qualification", "qualification_words", "adds", "added_words")
    return json.dumps({"punten": [{"nummer": i + 1, **dict(zip(velden, o)), "reason": "r"}
                                  for i, o in enumerate(oordelen)]})


def test_the_sharper_reading_asks_for_the_words_of_every_yes():
    v = w.lezingverzoek("c", "d", PUNTEN_V2, "sonnet", versie="lezing-v2")
    velden = v["output_config"]["format"]["schema"]["properties"]["punten"]["items"]["required"]
    assert {"concedes_words", "qualification_words", "added_words"} <= set(velden)
    assert v["system"] != w.lezingverzoek("c", "d", PUNTEN_V2, "sonnet", versie="lezing-v1")["system"]


def test_a_yes_of_the_sharper_reading_counts_only_with_words_that_are_really_there():
    """Een voorbehoud telt met beperkende woorden uit de weerlegging, een toevoeging en een toegeving met woorden uit het
    punt; een ja zonder die woorden telt niet, zoals een punt niet telt zonder een citaat dat er staat."""
    houd = w.lees_lezing(_v2((False, "", True, "remained controversial", False, ""),
                             (False, "", False, "", True, "as the commission reported"),
                             (True, "Turnout was 61%", False, "", False, "")),
                         3, punten=PUNTEN_V2, bron=BRON_V2)
    assert houd == [False, False, False]
    zonder = w.lees_lezing(_v2((False, "", True, "was never proven", False, ""),
                               (False, "", False, "", True, "according to the minister"),
                               (True, "", False, "", False, "")),
                           3, punten=PUNTEN_V2, bron=BRON_V2)
    assert zonder == [True, True, True]


def test_the_sharper_reading_without_its_words_is_unreadable():
    los = json.dumps({"punten": [{"nummer": 1, "concedes": False, "drops_qualification": False, "adds": False,
                                  "reason": ""}]})
    assert w.lees_lezing(los, 1, punten=PUNTEN_V2[:1], bron=BRON_V2) is None


# De volle ronde van de tweede lezing (PLAN #34.2j, PO 2026-11-12: "Ja, start").
def test_the_site_shows_only_the_points_the_second_reading_kept():
    punten = [{"punt": "a", "citaat": "a"}, {"punt": "b", "citaat": "b"}]
    assert w.toon(punten, [True, False]) == [punten[0]]
    assert w.toon(punten, None) == [] and w.toon(punten, [False, False]) == []
    assert w.LEZER == ("lezing-v2", "haiku", "medium")


def test_the_gate_refuses_a_reading_test_of_another_second_reader(tmp_path):
    assert w.poort(_labels(tmp_path, 200))[0] is True
    assert w.poort(_labels(tmp_path, 200, lezer="lezing-v1/sonnet/low"))[0] is False


def test_the_link_is_the_case_the_points_came_from():
    """Een pagina kan meer cases van EUvsDisinfo hebben; de link is die waaruit de punten komen, zoals hij in de uitgave
    staat."""
    urls = ["https://euvsdisinfo.eu/report/oud/", "https://euvsdisinfo.eu/report/nieuw", "https://snopes.com/x"]
    assert w.case_url(urls, "/report/nieuw") == "https://euvsdisinfo.eu/report/nieuw"
    assert w.case_url(urls, "/report/oud") == "https://euvsdisinfo.eu/report/oud/"
    assert w.case_url(urls, "/report/weg") is None


def test_the_measurement_comes_from_the_reading_test_that_opened_the_gate(tmp_path):
    pad = _labels(tmp_path, 200, fout=2)
    assert w.meting(pad) == {"punten": 400, "niet_gedragen": 2, "regels": w.REGELS, "lezer": w.LEZER_NAAM,
                             "paginas": 200, "datum": ""}


# --- wat een mens weghaalde (B77: een gemelde fout is binnen een werkdag weg) -----------------------------------------

def test_a_removed_point_never_reaches_the_site():
    toont = {"a": [{"punt": "x"}, {"punt": "y"}], "b": [{"punt": "z"}]}
    niet = [{"pagina": "a", "punt": "x", "reden": "gemeld"}]
    assert w.weg(toont, niet) == {"a": [{"punt": "y"}], "b": [{"punt": "z"}]}


def test_a_line_without_a_point_removes_the_whole_page():
    assert w.weg({"a": [{"punt": "x"}], "b": [{"punt": "z"}]}, [{"pagina": "a", "reden": "gemeld"}]) == {"b": [{"punt": "z"}]}


def test_a_page_left_without_points_is_not_shown():
    assert w.weg({"a": [{"punt": "x"}]}, [{"pagina": "a", "punt": "x", "reden": "gemeld"}]) == {}


def test_a_removal_without_a_reason_is_refused(tmp_path):
    pad = tmp_path / "waarom-niet.json"
    pad.write_text(json.dumps({"punten": [{"pagina": "a", "punt": "x", "reden": " "}]}), encoding="utf-8")
    try:
        w.niet_lijst(pad)
    except ValueError:
        return
    raise AssertionError("een regel zonder reden telt niet")


def test_no_removal_file_means_nothing_removed(tmp_path):
    assert w.niet_lijst(tmp_path / "bestaat-niet.json") == []


def test_the_points_of_a_reading_test_are_read_back_per_page():
    tekst = ("=== aaaa /report/een\nBEWERING: iets\n  [0] Het eerste punt.\n      in de tekst: …\n"
             "  [1] Het tweede punt.\n      in de tekst: …\n\n=== bbbb /report/twee\n  [0] Nog een.\n")
    assert w.leesproef_punten(tekst) == {"aaaa": ["Het eerste punt.", "Het tweede punt."], "bbbb": ["Nog een."]}


def test_every_point_read_as_not_carried_is_on_the_removal_list():
    """Een punt dat ik bij een leesproef niet gedragen las, staat nooit op de site, ook al houdt de marge van B77 het."""
    niet = w.niet_lijst()
    per_pagina = {}
    for r in niet:
        per_pagina[r["pagina"]] = per_pagina.get(r["pagina"], 0) + 1
    for pad in (w.LABELS_V1, w.LABELS):
        for pagina, g in json.loads(pad.read_text(encoding="utf-8"))["paginas"].items():
            fout = g["punten"].count("niet_gedragen")
            if fout:
                assert per_pagina.get(pagina, 0) >= fout, (pad.name, pagina)
                assert all(r.get("punt") for r in niet if r["pagina"] == pagina)


def test_a_case_from_the_server_is_read_like_one_from_the_snapshot_and_never_replaces_one():
    """PLAN #35.3: de gevallen van 2026 komen van de server van EUvsDisinfo; hun weerlegging gaat net zo naar de lezer."""
    from doublecheck import euvsdisinfo as eu

    snapshot = {"/report/oud": {"titel": "Oud", "bewering": "Old.", "weerlegging": "Snapshot text.", "datum": "01.11.2022"}}
    server = [eu.Geval(datum="2026-11-16", url="https://euvsdisinfo.eu/report/nieuw", titel="Nieuw",
                       claim="The war is ruining Europe.", weerlegging="This is a recurring narrative.",
                       outlets=(), landen=()),
              eu.Geval(datum="2026-11-16", url="https://euvsdisinfo.eu/report/oud", titel="Anders",
                       claim="Other.", weerlegging="Server text.", outlets=(), landen=())]
    samen = w.met_server(snapshot, server)
    assert samen["/report/nieuw"] == {"titel": "Nieuw", "bewering": "The war is ruining Europe.",
                                      "weerlegging": "This is a recurring narrative.", "datum": "2026-11-16"}
    assert samen["/report/oud"]["weerlegging"] == "Snapshot text."
