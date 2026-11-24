"""Route A terug in de tijd (PLAN #32.38): de grote open factcheckers uit de VS en Europa, zonder venster, buiten de
database, beleefd en hervatbaar."""

from doublecheck import eigenaanvoer as ea
from doublecheck import terugaanvoer as ta


def test_the_first_round_is_the_four_sites_the_po_named_and_never_afp():
    namen = [s["naam"] for s in ta.sites(ta.EERSTE_RONDE)]
    assert namen == ["Snopes", "Full Fact", "Lead Stories", "EFE Verifica"]
    assert not any("AFP" in n for n in ta.EERSTE_RONDE + ta.NA_DE_BEELDOOGST)
    assert set(ta.NA_DE_BEELDOOGST) == {"Maldita", "Newtral"}
    assert all(s in {x["naam"] for x in ea.SITES} for s in ta.EERSTE_RONDE + ta.NA_DE_BEELDOOGST)


def test_every_article_of_the_site_counts_whatever_its_date_and_only_its_articles():
    snopes = next(s for s in ea.SITES if s["naam"] == "Snopes")
    urls = [("https://www.snopes.com/fact-check/oud-verhaal/", "2009-04-01"),
            ("https://www.snopes.com/fact-check/nieuw/", "2026-10-30"),
            ("https://www.snopes.com/fact-check/nieuw/", "2026-10-31"),
            ("https://www.snopes.com/news/2026/10/30/iets/", "2026-10-30"),
            ("https://media.snopes.com/fact-check/elders/", None)]
    uit = ta.artikelen_uit(urls, snopes)
    assert uit == [("https://www.snopes.com/fact-check/nieuw/", "2026-10-30"),
                   ("https://www.snopes.com/fact-check/oud-verhaal/", "2009-04-01")]


def test_a_restart_skips_the_pages_already_asked():
    lijst = [("https://a.org/1", "2026-01-01"), ("https://a.org/2", None), ("https://a.org/3", "2020-01-01")]
    assert ta.nog_te_doen(lijst, {"https://a.org/2"}) == ["https://a.org/1", "https://a.org/3"]


def test_an_article_with_several_claims_counts_each_claim_once():
    c = {"site": "Full Fact", "adres": "https://fullfact.org/x/"}
    checks = [{**c, "bewering": "A"}, {**c, "bewering": "B"}, {**c, "bewering": "A"}]
    assert [x["bewering"] for x in ta.uniek(checks)] == ["A", "B"]


def test_what_is_kept_of_a_check_is_the_claim_the_rating_the_date_and_the_link_never_the_page():
    review = {"@type": "ClaimReview", "url": "https://www.snopes.com/fact-check/x/", "claimReviewed": "A claim",
              "datePublished": "2015-03-02", "reviewRating": {"alternateName": "False"},
              "author": {"@type": "Organization", "name": "Snopes"}}
    snopes = next(s for s in ea.SITES if s["naam"] == "Snopes")
    c = ta.check_van(review, "https://www.snopes.com/fact-check/x/", snopes, bekend=set())
    assert set(c) == {"adres", "site", "taal", "bewering", "oordeel", "categorie", "datum", "uitgever", "nieuw"}
    assert c["bewering"] == "A claim" and c["datum"] == "2015-03-02" and c["nieuw"] is True
    assert ta.check_van(review, "https://www.snopes.com/fact-check/x/", snopes,
                        bekend={"snopes.com/fact-check/x"})["nieuw"] is False


# --- stap 3: de oordelen lezen ---------------------------------------------------------------------------

def _c(site, oordeel, bewering="A claim", adres="https://x.org/1"):
    return {"site": site, "adres": adres, "bewering": bewering, "oordeel": oordeel}


def test_a_check_keeps_one_id_and_a_different_claim_gets_another():
    a = ta.check_id(_c("Full Fact", "False."))
    assert a == ta.check_id(_c("Full Fact", "Other text."))
    assert a != ta.check_id(_c("Full Fact", "False.", bewering="Another claim"))
    import re
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", ta.custom_id(a))


def test_the_rules_go_first_and_only_what_they_leave_goes_to_the_reader():
    assert ta.categorie_nu(_c("EFE Verifica", "Falsa.")) == "onwaar"
    assert ta.categorie_nu(_c("Snopes", "Unproven (retired)")) == "onbewezen"
    assert not ta.naar_lezer(_c("EFE Verifica", "Falsa."))
    assert ta.naar_lezer(_c("Lead Stories", "AI Generated"))
    assert ta.categorie_nu(_c("Full Fact", "False. This is not a genuine Currys offer.")) == "onwaar"
    assert not ta.naar_lezer(_c("Full Fact", "False. This is not a genuine Currys offer."))


def test_what_the_publisher_says_is_no_verdict_never_goes_to_the_reader():
    assert not ta.naar_lezer(_c("Snopes", "Scam"))
    assert not ta.naar_lezer(_c("Snopes", "Research In Progress (retired)"))
    assert not ta.naar_lezer(_c("Lead Stories", ""))


def test_the_question_names_the_fact_checker_the_claim_and_the_rating_and_asks_haiku():
    from doublecheck.modellen import MODELLEN

    v = ta.oordeelverzoek(_c("Lead Stories", "Bait & Switch", bewering="Video shows a flood in Paris"))
    inhoud = v["params"]["messages"][0]["content"]
    assert "Lead Stories" in inhoud and "Video shows a flood in Paris" in inhoud and "Bait & Switch" in inhoud
    assert v["params"]["model"] == MODELLEN["haiku"]["id"]
    assert v["params"]["output_config"]["format"]["schema"]["properties"]["oordeel"]["enum"] == list(ta.CATEGORIEEN)
    assert v["custom_id"] == ta.custom_id(ta.check_id(_c("Lead Stories", "x", bewering="Video shows a flood in Paris")))


def test_an_answer_outside_the_set_is_unknown_never_a_guess():
    assert ta.lees_oordeel('{"waarom": "x", "oordeel": "onwaar"}') == "onwaar"
    assert ta.lees_oordeel('{"waarom": "x", "oordeel": "false"}') == "onbekend"
    assert ta.lees_oordeel("geen json") == "onbekend"


def test_the_sample_is_fixed_per_site_whatever_the_order():
    rijen = [{"id": f"{s[0]}{i}", "site": s} for s in ("Lead Stories", "Full Fact", "EFE Verifica") for i in range(80)]
    a = ta.steekproef(rijen)
    assert [r["id"] for r in a] == [r["id"] for r in ta.steekproef(list(reversed(rijen)))]
    from collections import Counter
    assert Counter(r["site"] for r in a) == {"Lead Stories": 50, "Full Fact": 40, "EFE Verifica": 10}


def test_the_sides_follow_the_label_classes():
    assert ta.kant("onwaar") == ta.kant("misleidend") != ta.kant("waar")
    assert ta.kant("deels-waar") not in (ta.kant("onwaar"), ta.kant("waar"))
    assert len({ta.kant(c) for c in ("onbewezen", "satire", "onwaar", "waar", "deels-waar")}) == 5


def test_the_count_refuses_while_a_read_answer_has_no_label():
    import pytest
    rijen = [{"id": "a", "site": "Full Fact", "categorie": "onwaar"}]
    with pytest.raises(ta.Weigering):
        ta.telling(rijen, {}, gelezen=rijen)


def test_another_side_or_a_verdict_where_none_was_given_is_an_error_a_neighbour_is_not():
    rijen = [{"id": i, "site": "Lead Stories", "categorie": h} for i, h in
             [("1", "onwaar"), ("2", "onwaar"), ("3", "onbekend"), ("4", "onwaar"), ("5", "satire"), ("6", "waar")]]
    labels = {"1": "onwaar", "2": "misleidend", "3": "onwaar", "4": "onbekend", "5": "onwaar", "6": "deels-waar"}
    t = ta.telling(rijen, labels, gelezen=rijen)
    assert (t["gelijk"], t["naburig"], t["gemist"], t["fout"]) == (1, 1, 1, 3)
    assert t["eis gehaald"] is False


def test_the_reader_never_runs_past_its_limit():
    import pytest
    ta.binnen_grens(0.5, 1.4)
    with pytest.raises(ta.Weigering):
        ta.binnen_grens(0.7, 1.4)


# --- stap 3b: de vraag met onze leesregels, op een nieuwe toets ----------------------------------------------

def test_the_second_question_gives_haiku_our_reading_rules():
    v2 = ta.oordeelverzoek(_c("Full Fact", "There is no evidence for this."), versie="oordeel-terug-v2")
    tekst = v2["params"]["messages"][0]["content"]
    assert "no evidence" in tekst and "contradicts" in tekst     # onbewezen alleen zonder weerlegging
    assert "one part" in tekst                                    # een deel goed, een deel fout: deels waar
    assert "names what is wrong" in tekst                         # de korte labels van Lead Stories
    assert "unsure" not in tekst                                  # geen "bij twijfel onbekend" meer
    assert "There is no evidence for this." in tekst and "Full Fact" in tekst
    v1 = ta.oordeelverzoek(_c("Full Fact", "There is no evidence for this."), versie="oordeel-terug-v1")
    assert "unsure" in v1["params"]["messages"][0]["content"]
    assert ta.VERSIE == "oordeel-terug-v1" and set(ta.VRAGEN) == {"oordeel-terug-v1", "oordeel-terug-v2"}


def test_the_test_set_leaves_out_what_was_read_for_development_and_stays_fixed():
    from collections import Counter

    rijen = [{"id": f"{s[0]}{i:03}", "site": s} for s in ("Lead Stories", "Full Fact", "EFE Verifica") for i in range(200)]
    ontwikkel = {r["id"] for r in ta.steekproef(rijen)[:50]}
    toets = ta.toets(rijen, ontwikkel)
    assert not ontwikkel & {r["id"] for r in toets}
    assert Counter(r["site"] for r in toets) == ta.STEEKPROEF
    assert [r["id"] for r in toets] == [r["id"] for r in ta.toets(list(reversed(rijen)), ontwikkel)]


def test_answers_of_another_version_never_count_for_this_one():
    rijen = [{"id": "a", "versie": "oordeel-terug-v1", "categorie": "onwaar"},
             {"id": "a", "versie": "oordeel-terug-v2", "categorie": "onbewezen"},
             {"id": "b", "versie": "oordeel-terug-v1", "categorie": "waar"}]
    assert ta.antwoorden(rijen, "oordeel-terug-v2") == {"a": rijen[1]}
    assert set(ta.antwoorden(rijen, "oordeel-terug-v1")) == {"a", "b"}


# --- stap 3c: Full Fact met de kopregel, de rest zonder categorie ---------------------------------------------

def test_the_rest_of_full_fact_never_goes_to_the_reader():
    assert not ta.naar_lezer(_c("Full Fact", "Not quite, the population is projected to rise to 72.5 million."))
    assert ta.naar_lezer(_c("EFE Verifica", "Ni es en Gaza ni son palestinos."))


def test_the_head_rule_sample_takes_only_full_fact_checks_the_rule_decides_and_leaves_out_what_was_read():
    from collections import Counter

    checks = [{"site": "Full Fact", "adres": f"https://fullfact.org/{i}", "bewering": f"claim {i}",
               "oordeel": "This is not true. No." if i % 2 else "Not quite, no."} for i in range(300)]
    checks += [{"site": "Lead Stories", "adres": f"https://leadstories.com/{i}", "bewering": "c", "oordeel": "False"}
               for i in range(10)]
    gelezen = {ta.check_id(checks[1])}
    keuze = ta.kopregel_keuze(checks, gelezen)
    assert len(keuze) == 50 and Counter(c["site"] for c in keuze) == {"Full Fact": 50}
    assert all(ta.categorie_nu(c) != "onbekend" for c in keuze)
    assert not gelezen & {c["id"] for c in keuze}
    assert [c["id"] for c in keuze] == [c["id"] for c in ta.kopregel_keuze(list(reversed(checks)), gelezen)]


# --- stap 4: het nakijken ----------------------------------------------------------------------------------

def test_the_import_category_takes_the_rules_first_then_haiku_and_never_haiku_for_full_fact():
    lees = _c("Lead Stories", "AI Generated", bewering="b1")
    ff = _c("Full Fact", "Not quite, the figure is lower.", bewering="b2")
    efe = _c("EFE Verifica", "Falsa.", bewering="b3")
    v1 = {ta.check_id(lees): {"categorie": "onwaar"}, ta.check_id(ff): {"categorie": "deels-waar"},
          ta.check_id(efe): {"categorie": "waar"}}
    assert ta.eindcategorie(lees, v1) == ("onwaar", "haiku")
    assert ta.eindcategorie(efe, v1) == ("onwaar", "regel")
    assert ta.eindcategorie(ff, v1) == ("onbekend", "geen")
    assert ta.eindcategorie(_c("Lead Stories", "Odd Label", bewering="b4"), v1) == ("onbekend", "geen")


def test_the_review_sets_are_fixed_per_language_leave_out_what_was_read_and_the_po_reads_half_of_mine():
    checks = [{"site": s, "taal": t, "adres": f"https://{s}/{i}", "bewering": f"claim {i}", "oordeel": "False"}
              for s, t in (("Snopes", "en"), ("Lead Stories", "en"), ("EFE Verifica", "es")) for i in range(300)]
    gelezen = {ta.check_id(checks[0]), ta.check_id(checks[700])}
    sets = ta.nakijk_sets(checks, gelezen)
    assert len(sets["nakijk-en"]) == 100 and len(sets["nakijk-es"]) == 100
    assert sets["nakijk-po"] == sets["nakijk-en"][:50]
    per_id = {ta.check_id(c): c for c in checks}
    assert {per_id[i]["taal"] for i in sets["nakijk-en"]} == {"en"}
    assert not gelezen & set(sets["nakijk-en"] + sets["nakijk-es"])
    assert sets == ta.nakijk_sets(list(reversed(checks)), gelezen)


def test_a_review_error_found_by_either_reader_counts_and_a_near_miss_does_not():
    eind = {"a": "onwaar", "b": "onwaar", "c": "onbekend", "d": "waar", "e": "onwaar"}
    mijn = {"a": {"bewering": "klopt", "categorie": "onwaar"},
            "b": {"bewering": "klopt", "categorie": "misleidend"},     # bijna
            "c": {"bewering": "klopt", "categorie": "onwaar"},         # te voorzichtig
            "d": {"bewering": "klopt", "categorie": "onwaar"},         # fout: andere kant
            "e": {"bewering": "fout", "categorie": "onwaar"}}          # fout: de bewering
    po = {"a": {"bewering": "klopt", "categorie": "fout"}}             # de PO vindt er nog een
    t = ta.telling_nakijken(list(eind), eind, mijn, po)
    assert (t["fout"], t["bijna"], t["te voorzichtig"]) == (3, 1, 1)
    assert t["fout in de bewering"] == 1 and t["eis gehaald"] is False
    import pytest
    with pytest.raises(ta.Weigering):
        ta.telling_nakijken(["a", "x"], {**eind, "x": "waar"}, mijn, {})



# --- stap 4b: B56, satire alleen als het echt satire is, en Lead Stories niet in de import ---------------------

def test_haikus_satire_counts_as_false_and_lead_stories_stays_out_of_the_import():
    efe = _c("EFE Verifica", "Es una parodia publicada por un sitio satírico.", bewering="b5")
    assert ta.eindcategorie(efe, {ta.check_id(efe): {"categorie": "satire"}}) == ("onwaar", "haiku")
    assert ta.eindcategorie(_c("Snopes", "Labeled Satire", bewering="b6"), {}) == ("onwaar", "regel")
    assert "Lead Stories" in ta.NIET_IMPORTEREN and "Snopes" not in ta.NIET_IMPORTEREN


def test_a_po_choice_about_a_category_lapses_when_the_category_changed_but_the_claim_choice_stays():
    po = {"a": {"bewering": "klopt", "categorie": "fout"}, "b": {"bewering": "fout", "categorie": "klopt"}}
    getoond = {"a": "satire", "b": "onwaar"}
    nu = {"a": "onwaar", "b": "onwaar"}
    assert ta.po_keuzes_nu(po, getoond, nu) == {"a": {"bewering": "klopt"}, "b": {"bewering": "fout", "categorie": "klopt"}}


def test_the_second_english_review_leaves_out_lead_stories_and_everything_read_before():
    checks = [{"site": s, "taal": "en", "adres": f"https://{s}/{i}", "bewering": f"claim {i}", "oordeel": "False"}
              for s in ("Snopes", "Lead Stories", "Full Fact") for i in range(200)]
    gelezen = {ta.check_id(checks[0]), ta.check_id(checks[450])}
    toets = ta.tweede_toets(checks, gelezen)
    per_id = {ta.check_id(c): c for c in checks}
    assert len(toets) == 100 and not gelezen & set(toets)
    assert not {per_id[i]["site"] for i in toets} & ta.NIET_IMPORTEREN
    assert toets == ta.tweede_toets(list(reversed(checks)), gelezen)


# --- stap 5 en 6: de toelating en de import voorbereiden ---------------------------------------------------

def test_every_site_that_goes_into_the_import_is_admitted_and_lead_stories_is_not_imported():
    from doublecheck.uitgevers import load_hosts

    hosts = load_hosts()
    assert ta.IMPORT_SITES == ("Snopes", "Full Fact", "EFE Verifica", "Maldita", "Newtral")  # #32.66
    for naam in ta.IMPORT_SITES:
        assert ta._host(naam) in hosts, naam


def test_the_import_cleans_the_claim_and_leaves_out_what_is_no_claim():
    checks = [
        {"site": "Snopes", "adres": "https://www.snopes.com/fact-check/a/", "taal": "en", "datum": "2003-01-02",
         "bewering": "Sailors spelled a word on the deck of a <NOBR>U.S. aircraft</NOBR>  carrier.",
         "oordeel": "False", "uitgever": "Snopes"},
        {"site": "EFE Verifica", "adres": "https://verifica.efe.com/b/", "taal": "es", "datum": "2026-05-01",
         "bewering": "No es cierto que una imagen muestre a un conductor sin equipo.", "oordeel": "Falso.",
         "uitgever": "EFE"},
        {"site": "Lead Stories", "adres": "https://leadstories.com/c.html", "taal": "en", "datum": "2024-01-01",
         "bewering": "A claim", "oordeel": "Not Real", "uitgever": "Lead Stories"},
    ]
    claims, weg = ta.naar_import(checks)
    assert len(claims) == 1
    c = claims[0]
    assert c.text == "Sailors spelled a word on the deck of a U.S. aircraft carrier."
    (f,) = c.factchecks
    assert (f.publisher, f.publisher_site, f.url, f.review_date, f.verdict_original, f.language) == (
        "Snopes", "snopes.com", "https://www.snopes.com/fact-check/a/", "2003-01-02", "False", "en")
    assert weg == {"de conclusie als bewering": 1, "Lead Stories (B56)": 1}


def test_maldita_and_newtral_are_imported_but_a_maldita_article_title_is_not_a_claim():
    # #32.66: bij Maldita staat soms de titel van het artikel in het veld van de bewering, met "[T]" ervoor, vaak de
    # ontkrachting zelf ("No, Pablo Iglesias no ha tuiteado ..."); met "Bulo" erbij zou de database het omgekeerde
    # beweren.
    checks = [
        {"site": "Maldita", "adres": "https://maldita.es/malditobulo/a/", "taal": "es", "datum": "2026-01-02",
         "bewering": "El petróleo no es un combustible fósil", "oordeel": "Bulo", "uitgever": "Maldita.es"},
        {"site": "Maldita", "adres": "https://maldita.es/malditobulo/b/", "taal": "es", "datum": "2026-01-03",
         "bewering": "[T] No, Pablo Iglesias no ha tuiteado eso", "oordeel": "Bulo", "uitgever": "Maldita.es"},
        {"site": "Newtral", "adres": "https://www.newtral.es/c/", "taal": "es", "datum": "2026-01-04",
         "bewering": "Esta imagen muestra un tren accidentado en enero", "oordeel": "Engañoso", "uitgever": "Newtral"},
    ]
    claims, weg = ta.naar_import(checks)
    assert [c.text for c in claims] == ["El petróleo no es un combustible fósil",
                                        "Esta imagen muestra un tren accidentado en enero"]
    assert weg == {"de titel van het artikel als bewering": 1}


def test_route_a_is_registered_before_the_first_import_and_is_not_redistributable():
    from doublecheck.bootstrap import herkomstrapport
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    ta.registreer_route_a(conn)
    rij = conn.execute("SELECT naam, soort, herverdeelbaar FROM bron WHERE bron_id = ?", (ta.BRON,)).fetchone()
    assert rij[1] == "factchecker" and rij[2] == 0 and rij[0]
    assert ta.BRON == "route-a"
    assert herkomstrapport(conn).vrij == frozenset({"datacommons-ccby"})


def test_two_sites_whose_names_start_with_the_same_word_keep_their_own_list():
    """Les Décodeurs en Les Surligneurs schreven allebei naar `lijst-les.json` (#32.66): de tweede wiste de eerste."""
    namen = ("Les Décodeurs", "Les Surligneurs", "AFP Factuel", "AFP Factual", "Maldita")
    paden = {ta._lijstpad({"naam": n}) for n in namen}
    assert len(paden) == len(namen)
    assert ta._lijstpad({"naam": "Maldita"}).name == "lijst-maldita.json"


def test_an_article_already_in_the_database_is_not_added_again_unless_route_a_brings_the_missing_verdict():
    # #32.66: 660 artikelen van Maldita en Newtral stonden er al via Data Commons, met de bewering in andere woorden;
    # route A zette ze er nog eens bij. Bij een deel was de nieuwe tekst de conclusie ("El Santiago Abascal … no es el
    # líder de VOX", Falso), zodat de database het omgekeerde beweerde. Een artikel komt er dus één keer in; alleen als
    # elke bestaande check van dat artikel onbekend is en route A het oordeel weet, gaat de check van route A mee.
    checks = [
        {"site": "Newtral", "adres": "https://www.newtral.es/santiago-abascal-papeles-de-barcenas/20191101/",
         "taal": "es", "datum": "2019-11-01", "categorie": "onwaar", "oordeel": "Falso", "uitgever": "Newtral",
         "bewering": "El Santiago Abascal que aparece en los «papeles de Bárcenas» no es el líder de VOX"},
        {"site": "Maldita", "adres": "https://maldita.es/malditobulo/20200328/rosa-diez/", "taal": "es",
         "datum": "2020-03-28", "categorie": "onwaar", "oordeel": "Bulo", "uitgever": "Maldita.es",
         "bewering": "Tuit de Rosa Díez: \"es el momento de que el ejército se haga cargo\""},
        {"site": "Maldita", "adres": "https://maldita.es/malditobulo/20200918/pateras/", "taal": "es",
         "datum": "2020-09-18", "categorie": "onbekend", "oordeel": "Qué sabemos", "uitgever": "Maldita.es",
         "bewering": "Miles de pateras hacinadas en Mauritania tienen como destino Canarias"},
        {"site": "Newtral", "adres": "https://www.newtral.es/nieuw/20260101/", "taal": "es", "datum": "2026-01-01",
         "categorie": "onwaar", "oordeel": "Falso", "uitgever": "Newtral", "bewering": "Una bewering die er nog niet is"},
    ]
    aanwezig = {
        ta.artikel("http://newtral.es/santiago-abascal-papeles-de-barcenas/20191101"): ["onwaar"],
        ta.artikel("https://maldita.es/malditobulo/20200328/rosa-diez"): ["onbekend"],
        ta.artikel("https://maldita.es/malditobulo/20200918/pateras/"): ["onbekend"],
    }
    claims, weg = ta.naar_import(checks, aanwezig)
    assert [c.text for c in claims] == ["Tuit de Rosa Díez: \"es el momento de que el ejército se haga cargo\"",
                                        "Una bewering die er nog niet is"]
    assert weg == {"het artikel stond er al": 2}


def test_the_article_key_ignores_scheme_www_case_and_the_closing_slash_but_not_the_path():
    assert ta.artikel("https://www.Newtral.es/a/20191101/") == ta.artikel("http://newtral.es/a/20191101")
    assert ta.artikel("https://www.newtral.es/a/") != ta.artikel("https://www.newtral.es/b/")
    assert ta.artikel("https://maldita.es/a/") != ta.artikel("https://newtral.es/a/")


def _rij(conn, cid, tekst, url, oordeel, bron):
    if not conn.execute("SELECT 1 FROM claim WHERE claim_id = ?", (cid,)).fetchone():
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'es')", (cid, tekst))
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url, review_date,"
                 " language, source) VALUES (?, 'Newtral', ?, 'Falso', ?, '2020-01-01', 'es', ?)",
                 (cid, oordeel, url, bron))


def test_the_cleanup_removes_route_a_copies_of_an_article_already_there_and_keeps_the_rest(tmp_path):
    import json

    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    _rij(conn, "dc1", "El limón y el bicarbonato matan el coronavirus", "https://www.newtral.es/limon/", "onwaar",
         "datacommons-ccby")
    _rij(conn, "ra1", "El limón y el bicarbonato no matan el coronavirus", "https://newtral.es/limon", "onwaar",
         ta.BRON)
    # route A weet het oordeel en de kopie die er al was niet: die blijft
    _rij(conn, "dc2", "Tuit falso de Rosa Díez", "https://maldita.es/r/", "onbekend", "datacommons-ccby")
    _rij(conn, "ra2", "Tuit de Rosa Díez", "https://maldita.es/r/", "onwaar", ta.BRON)
    # twee beweringen uit één artikel, allebei uit route A: die blijven
    _rij(conn, "ra3", "Eerste bewering", "https://maldita.es/twee/", "onwaar", ta.BRON)
    _rij(conn, "ra4", "Tweede bewering", "https://maldita.es/twee/", "onwaar", ta.BRON)
    # een bewering die ook bij een ander artikel hoort: alleen de rij van het dubbele artikel gaat weg
    _rij(conn, "ra5", "Gedeelde bewering", "https://www.newtral.es/dubbel/", "onwaar", ta.BRON)
    _rij(conn, "ra5", "Gedeelde bewering", "https://www.newtral.es/ander/", "onwaar", ta.BRON)
    _rij(conn, "dc5", "Gedeelde bewering in andere woorden", "https://www.newtral.es/dubbel/", "onwaar",
         "datacommons-ccby")
    conn.commit()

    dubbel = ta.dubbele_artikelen(conn)
    assert sorted((d["claim_id"], d["url"]) for d in dubbel) == [
        ("ra1", "https://newtral.es/limon"), ("ra5", "https://www.newtral.es/dubbel/")]
    rapportpad = tmp_path / "dubbel.json"
    assert ta.haal_dubbele_weg(conn, dubbel, rapportpad) == {"checks": 2, "beweringen": 1}
    over = {(c, u) for c, u in conn.execute("SELECT claim_id, url FROM factcheck")}
    assert ("ra1", "https://newtral.es/limon") not in over and ("ra5", "https://www.newtral.es/dubbel/") not in over
    assert {c for c, _ in over} == {"dc1", "dc2", "ra2", "ra3", "ra4", "ra5", "dc5"}
    assert not conn.execute("SELECT 1 FROM claim WHERE claim_id = 'ra1'").fetchone()
    rapport = json.loads(rapportpad.read_text(encoding="utf-8"))
    assert rapport["aantal"] == 2 and {r["claim_id"] for r in rapport["weg"]} == {"ra1", "ra5"}
    assert rapport["weg"][0]["al_er"]


def test_the_cleanup_refuses_a_claim_in_the_test_set_and_never_overwrites_an_earlier_report(tmp_path):
    import pytest

    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    _rij(conn, "dc1", "Una bewering", "https://www.newtral.es/a/", "onwaar", "datacommons-ccby")
    _rij(conn, "ra1", "Una bewering in andere woorden", "https://www.newtral.es/a/", "onwaar", ta.BRON)
    conn.execute("INSERT INTO testpair (claim_id, is_same, provenance, language, model_version, payload)"
                 " VALUES ('ra1', 1, 'x', 'es', 'm', x'00')")
    dubbel = ta.dubbele_artikelen(conn)
    with pytest.raises(ValueError):
        ta.haal_dubbele_weg(conn, dubbel, tmp_path / "a.json")
    assert conn.execute("SELECT count(*) FROM factcheck").fetchone()[0] == 2
    conn.execute("DELETE FROM testpair")
    (tmp_path / "b.json").write_text("{}")
    with pytest.raises(FileExistsError):
        ta.haal_dubbele_weg(conn, dubbel, tmp_path / "b.json")
