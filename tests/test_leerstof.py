"""De leerstof van de eerste leerling (PLAN #31.3, E8.S3): de regels die vóór
het bouwen vastlagen."""

from doublecheck import leerstof


def _stuk(sleutel, label, taal="en", helft="ontwikkel", bron="claimreview", vers=False, zaak=None, soort="tekst"):
    return {"sleutel": sleutel, "label": label, "taal": taal, "helft": helft, "bron": bron, "vers": vers,
            "zaak": zaak, "soort": soort, "tekst": f"tekst van {sleutel}"}


def test_only_the_lesson_part_of_the_development_half_may_be_taught():
    zaken = [f"gfc-{i}" for i in range(200)]
    les = next(z for z in zaken if leerstof.deel_van({"zaak": z, "sleutel": z}) == "les")
    keuze = next(z for z in zaken if leerstof.deel_van({"zaak": z, "sleutel": z}) == "keuze")
    assert leerstof.mag_leren(_stuk(les, "onwaar", zaak=les))
    assert not leerstof.mag_leren(_stuk(keuze, "onwaar", zaak=keuze))
    assert not leerstof.mag_leren(_stuk(les, "onwaar", zaak=les, helft="toets"))
    assert not leerstof.mag_leren(_stuk(les, "onwaar", zaak=les, vers=True))
    assert not leerstof.mag_leren(_stuk(les, "waar", zaak=les, bron="n3-kern", soort="feit"))
    assert not leerstof.mag_leren(_stuk(les, "onwaar", zaak=les, bron="minimale-paren", soort="feit"))


def test_the_student_label_is_one_only_for_what_an_editor_or_the_source_calls_false():
    assert leerstof.label_leerling("onwaar") == 1
    assert leerstof.label_leerling("waar") == 0
    assert leerstof.label_leerling("neutraal") == 0


def test_each_language_gets_as_many_zeros_as_ones_never_borrowed_from_another_language():
    een = [_stuk(f"e{i}", "onwaar", taal="ru") for i in range(3)] + [_stuk("e9", "onwaar", taal="en")]
    nul = {"ru": {"claimreview": [_stuk("w1", "waar", taal="ru")], "sheffield-trustworthy": [],
                  "wikinews": [_stuk(f"n{i}", "waar", taal="ru", bron="wikinews") for i in range(5)],
                  "wikipedia": [_stuk(f"p{i}", "waar", taal="ru", bron="wikipedia") for i in range(5)],
                  "stiltepool": []},
           "en": {"claimreview": [], "sheffield-trustworthy": [], "wikinews": [], "wikipedia": [], "stiltepool": []}}
    gekozen = leerstof.nullen_per_taal(een, nul, zaad=3001)
    per_taal = {}
    for s in gekozen:
        per_taal.setdefault(s["taal"], []).append(s)
    assert len(per_taal["ru"]) == 3 and "en" not in per_taal
    assert per_taal["ru"][0]["sleutel"] == "w1"  # eerst de ware checks, in claimstijl
    assert {s["bron"] for s in per_taal["ru"][1:]} == {"wikinews", "wikipedia"}  # dan om en om


def test_cleaning_removes_markup_and_templates_but_keeps_every_script():
    vuil = "Moscow  <dynamicpagelist> category = X </dynamicpagelist> {{Infobox x}} Москва — столица. القاهرة"
    schoon = leerstof.schoon(vuil)
    assert "<" not in schoon and "{{" not in schoon and "  " not in schoon
    assert "Москва — столица." in schoon and "القاهرة" in schoon
    assert len(leerstof.schoon("x" * 5000)) == leerstof.MAX_TEKENS


# De lastige paren (PLAN #31.3): Sonnet schrijft bij een onware claim de ware
# tegenhanger, met een bron; alleen wat gelezen en goedgekeurd is, telt.

def test_a_counterpart_needs_a_sentence_and_a_source_or_it_is_not_known():
    import json

    assert leerstof.lees_paar(json.dumps({"weet": True, "ware_zin": " The photo is from 2015. ", "bron": "https://x.org"})) \
        == ("bekend", "The photo is from 2015.", "https://x.org")
    assert leerstof.lees_paar(json.dumps({"weet": True, "ware_zin": "x", "bron": ""})) == ("onbekend", None, None)
    assert leerstof.lees_paar(json.dumps({"weet": False, "ware_zin": "", "bron": ""})) == ("onbekend", None, None)
    assert leerstof.lees_paar('{"weet": true, "ware') == ("onleesbaar", None, None)


def test_the_counterpart_request_carries_the_claim_its_language_and_date():
    v = leerstof.paar_verzoek("p-001", "Photo shows floods in Chennai in 2021", "en", "2021-11-10")
    tekst = v["params"]["messages"][0]["content"][0]["text"]
    assert "Photo shows floods in Chennai in 2021" in tekst and "2021-11-10" in tekst and "(en)" in tekst
    assert v["params"]["model"] == "claude-sonnet-5-5"


# Leerstof v2 (PLAN #31.3, akkoord PO 2026-10-23): stijl tegen stijl.

def test_style_against_style_matches_claims_with_claims_and_articles_with_articles():
    een = [_stuk(f"c{i}", "onwaar", taal="ru", soort="tekst") for i in range(4)] + \
          [_stuk("b1", "onwaar", taal="ru", soort="beeld")] + \
          [_stuk(f"a{i}", "onwaar", taal="ru", soort="artikel") for i in range(2)]
    nul = {"ru": {"claimreview": [_stuk("w1", "waar", taal="ru")],
                  "wikinews-kop": [_stuk(f"k{i}", "waar", taal="ru", bron="wikinews-kop", soort="kop") for i in range(2)],
                  "wikipedia": [_stuk(f"p{i}", "waar", taal="ru", bron="wikipedia", soort="feit") for i in range(9)],
                  "sheffield-trustworthy": [_stuk("s1", "waar", taal="ru", bron="sheffield-trustworthy", soort="artikel")],
                  "wikinews": [_stuk(f"n{i}", "waar", taal="ru", bron="wikinews", soort="nieuws") for i in range(9)],
                  "stiltepool": [_stuk(f"x{i}", "neutraal", taal="ru", bron="stiltepool", soort="webtekst") for i in range(9)]}}
    gekozen = leerstof.stijl_tegen_stijl(een, nul, zaad=3001)
    bronnen = [s["bron"] for s in gekozen]
    # Vijf claimzinnen: de ware check, beide koppen, dan twee Wikipedia-zinnen.
    assert bronnen[:5] == ["claimreview", "wikinews-kop", "wikinews-kop", "wikipedia", "wikipedia"]
    # Twee artikelen: eerst Sheffield, dan Wikinews.
    assert bronnen[5:7] == ["sheffield-trustworthy", "wikinews"]
    # Een vijfde van zeven onware is één webtekst.
    assert bronnen[7:] == ["stiltepool"]


def test_a_question_headline_is_no_claim():
    assert leerstof.is_kop("Iran Agrees to Suspend Uranium Conversion")
    assert not leerstof.is_kop("صدام حسين هل يدلي بصوته بالسجن اليوم؟")
    assert not leerstof.is_kop("Is this the end?")
    assert not leerstof.is_kop("Kort")


# Leerstof v3 (PLAN #31.5, akkoord PO 2026-10-23): onderwerp tegen onderwerp.

def test_topic_against_topic_puts_wikipedia_on_the_same_subject_right_after_true_checks_and_articles():
    een = [_stuk(f"c{i}", "onwaar", taal="ru", soort="tekst") for i in range(3)] + \
          [_stuk(f"a{i}", "onwaar", taal="ru", soort="artikel") for i in range(3)]
    nul = {"ru": {"claimreview": [_stuk("w1", "waar", taal="ru")],
                  "wikipedia-onderwerp": [_stuk("o1", "waar", taal="ru", bron="wikipedia-onderwerp", soort="feit")],
                  "wikinews-kop": [_stuk(f"k{i}", "waar", taal="ru", bron="wikinews-kop", soort="kop") for i in range(3)],
                  "sheffield-trustworthy": [_stuk("s1", "waar", taal="ru", bron="sheffield-trustworthy", soort="artikel")],
                  "wikipedia-onderwerp-inleiding": [_stuk("i1", "waar", taal="ru", bron="wikipedia-onderwerp-inleiding",
                                                          soort="artikel")],
                  "wikinews": [_stuk(f"n{i}", "waar", taal="ru", bron="wikinews", soort="nieuws") for i in range(3)]}}
    gekozen = leerstof.stijl_tegen_stijl(een, nul, zaad=3001, claimstijl=leerstof.CLAIMSTIJL_V3,
                                         artikelstijl=leerstof.ARTIKELSTIJL_V3)
    assert [s["bron"] for s in gekozen][:6] == ["claimreview", "wikipedia-onderwerp", "wikinews-kop",
                                                "sheffield-trustworthy", "wikipedia-onderwerp-inleiding", "wikinews"]


def test_topic_against_topic_changes_only_which_true_pieces_not_how_many():
    assert len(leerstof.CLAIMSTIJL_V3) == len(leerstof.CLAIMSTIJL) + 1
    assert set(leerstof.CLAIMSTIJL) < set(leerstof.CLAIMSTIJL_V3)
    assert set(leerstof.ARTIKELSTIJL) < set(leerstof.ARTIKELSTIJL_V3)


# Leerstof v4 (PLAN #31.5 ronde 2, akkoord PO 2026-10-25): stijl én onderwerp.

def test_style_and_topic_alternate_a_topic_sentence_with_a_claim_style_sentence():
    een = [_stuk(f"c{i}", "onwaar", taal="ru", soort="tekst") for i in range(5)]
    nul = {"ru": {"wikipedia-onderwerp": [_stuk(f"o{i}", "waar", taal="ru", bron="wikipedia-onderwerp", soort="feit")
                                          for i in range(9)],
                  "claimreview": [_stuk("w1", "waar", taal="ru")],
                  "wikinews-kop": [_stuk("k1", "waar", taal="ru", bron="wikinews-kop", soort="kop")],
                  "wikipedia": [_stuk("p1", "waar", taal="ru", bron="wikipedia", soort="feit")]}}
    gekozen = leerstof.stijl_tegen_stijl(een, nul, zaad=3001, claimgroepen=leerstof.CLAIMGROEPEN_V4)
    # Om en om; zodra de claimstijl op is, gaat het onderwerp verder.
    assert [s["bron"] for s in gekozen][:5] == ["wikipedia-onderwerp", "claimreview", "wikipedia-onderwerp",
                                                "wikinews-kop", "wikipedia-onderwerp"]


def test_when_both_groups_run_out_general_wikipedia_fills_up():
    een = [_stuk(f"c{i}", "onwaar", taal="ru", soort="tekst") for i in range(3)]
    nul = {"ru": {"claimreview": [_stuk("w1", "waar", taal="ru")],
                  "wikipedia": [_stuk(f"p{i}", "waar", taal="ru", bron="wikipedia", soort="feit") for i in range(5)]}}
    gekozen = leerstof.stijl_tegen_stijl(een, nul, zaad=3001, claimgroepen=leerstof.CLAIMGROEPEN_V4)
    assert [s["bron"] for s in gekozen][:3] == ["claimreview", "wikipedia", "wikipedia"]
