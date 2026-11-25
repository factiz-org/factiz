"""De taal van een bewering nalopen voor het platform (PLAN #33.5): wie verdacht is, wat het model mag antwoorden, en
wanneer een correctie telt."""

import json

from doublecheck import taallabels as tl


def test_a_label_is_suspect_when_it_is_unknown_galician_or_rare_at_its_own_site():
    rijen = ([(f"p{i}", "pt", "boatos.org") for i in range(95)] + [(f"s{i}", "es", "boatos.org") for i in range(5)]
             + [("g1", "gl", "lupa.com"), ("u1", "und", "lupa.com"), ("l1", "pt", "lupa.com")]
             + [(f"k{i}", "en", "klein.org") for i in range(9)] + [("k9", "it", "klein.org")])
    verdacht = tl.kandidaten(rijen)
    # Spaans is bij deze Braziliaanse site 5 van de 100: verdacht. Portugees daar niet.
    assert {f"s{i}" for i in range(5)} <= verdacht and "p0" not in verdacht
    assert {"g1", "u1"} <= verdacht and "l1" not in verdacht           # Galicisch en onbekend altijd
    assert "k9" not in verdacht                                         # een site met te weinig pagina's zegt niets


def test_the_model_sees_the_texts_without_the_label_we_doubt():
    v = tl.taalverzoek(["Cacau Show está vendendo caixa branca", "Prof Anyang Nyong'o is dead"])
    assert v["model"] == "claude-haiku-5-5" and "json_schema" in json.dumps(v["output_config"])
    vraag = v["messages"][0]["content"][0]["text"]
    assert vraag == "1. Cacau Show está vendendo caixa branca\n2. Prof Anyang Nyong'o is dead"
    assert "(es)" not in vraag and "(id)" not in vraag                  # blind: het oude label gaat niet mee
    lang = tl.taalverzoek(["x" * 2000])["messages"][0]["content"][0]["text"]
    assert len(lang) < 500                                              # een lange tekst is niet nodig voor de taal


def test_an_answer_counts_only_as_a_known_code_on_its_own_number():
    tekst = json.dumps({"antwoorden": [{"nr": 1, "taal": "pt"}, {"nr": 2, "taal": "EN"}, {"nr": 3, "taal": "Portuguese"},
                                       {"nr": 4, "taal": "und"}, {"nr": 5, "taal": "zz"}, {"nr": 5, "taal": "en"},
                                       {"nr": 9, "taal": "en"}]})
    # 2: hoofdletters mogen; 3: een naam is geen code; 5: twee keer genoemd, dus geen van beide; 6: ontbreekt
    assert tl.lees_talen(tekst, 6) == ["pt", "en", None, "und", None, None]
    assert tl.lees_talen(None, 2) == [None, None] and tl.lees_talen("kapot", 2) == [None, None]
    assert tl.lees_talen(json.dumps({"antwoorden": "x"}), 1) == [None]


def test_a_correction_is_a_readable_answer_that_differs_from_the_label():
    antwoorden = [{"nummer": "a", "was": "es", "taal": "pt"}, {"nummer": "b", "was": "kn", "taal": "kn"},
                  {"nummer": "c", "was": "id", "taal": None}, {"nummer": "d", "was": "und", "taal": "hi"},
                  {"nummer": "e", "was": "it", "taal": "und"}]
    assert tl.correcties(antwoorden) == {"a": "pt", "d": "hi", "e": "und"}


def test_corrections_apply_only_after_a_reading_of_one_hundred_finds_ninety_five_right(tmp_path):
    antwoorden = [{"nummer": f"{i:04d}", "was": "es", "taal": "pt"} for i in range(300)]
    proef = tl.leesproef(antwoorden)
    assert len(proef["gewijzigd"]) == 100 and proef == tl.leesproef(antwoorden)          # vast zaad
    pad = tmp_path / "labels.json"
    assert tl.poort(antwoorden, pad) == (False, "nog niets gelezen")

    def schrijf(goed, fout, twijfel=0):
        ids = proef["gewijzigd"]
        labels = ({i: "goed" for i in ids[:goed]} | {i: "fout" for i in ids[goed:goed + fout]}
                  | {i: "twijfel" for i in ids[goed + fout:goed + fout + twijfel]})
        pad.write_text(json.dumps({"toelichting": "x", "gelezen_door": "Claude", "labels": labels}), encoding="utf-8")

    schrijf(90, 0)
    assert tl.poort(antwoorden, pad)[0] is False and "90 van de 100 gelezen" in tl.poort(antwoorden, pad)[1]
    schrijf(94, 6)
    assert tl.poort(antwoorden, pad)[0] is False
    schrijf(94, 0, twijfel=6)                                            # twijfel telt als fout
    assert tl.poort(antwoorden, pad)[0] is False
    schrijf(95, 5)
    assert tl.poort(antwoorden, pad) == (True, "95 van de 100 goed")
    assert tl.poort(antwoorden[:50], pad)[0] is False                    # een andere set antwoorden, een andere proef


def test_a_language_a_person_read_wins_over_the_model_even_while_its_reading_is_closed():
    # het model maakte van een Russische bewering Oekraïens; een mens las haar en zegt Russisch (PO 2026-11-25)
    model = {"34b3d58dbae23ee3": "uk", "a6fb51005e18ba22": "hi"}
    gelezen = {"34b3d58dbae23ee3": {"taal": "ru", "reden": "Russisch: Польши, обвалился"},
               "bedcb75e56432300": {"taal": "en", "reden": "Engels"}}
    assert tl.met_gelezen(model, gelezen) == {"34b3d58dbae23ee3": "ru", "a6fb51005e18ba22": "hi",
                                              "bedcb75e56432300": "en"}
    assert tl.met_gelezen({}, gelezen)["34b3d58dbae23ee3"] == "ru"      # ook als de poort van het model dicht is
    # alleen een bekende code, met een reden, op een echt nummer
    fout = {"34b3d58dbae23ee3": {"taal": "Russian", "reden": "x"}, "bedcb75e56432300": {"taal": "en"},
            "kort": {"taal": "en", "reden": "x"}, "a6fb51005e18ba22": "ru"}
    assert tl.met_gelezen(model, fout) == model


def test_the_languages_people_read_are_in_one_file_that_the_build_reads():
    gelezen = tl.gelezen()
    assert gelezen["34b3d58dbae23ee3"]["taal"] == "ru"
    assert all(tl.met_gelezen({}, {nr: r}) == {nr: r["taal"]} for nr, r in gelezen.items())   # elke regel telt
