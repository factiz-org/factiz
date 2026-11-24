"""De sets per taal voor de controle in het Spaans, Portugees en Duits (PLAN #32.42): verse en bekende onware
berichten uit de database, ware berichten van Wikinews en van de media zelf, en gewone webtekst."""

from doublecheck import talenset as ts


def _check(i, jaar="2025", oordeel="onwaar", uitgever="EFE Verifica", tekst=None, claim=None):
    return {"factcheck_id": i, "claim_id": claim or f"c{i}", "tekst": tekst or f"Una afirmación falsa número {i}",
            "datum": f"{jaar}-03-01", "url": f"https://verifica.efe.com/{i}", "publisher": uitgever, "oordeel": oordeel}


def test_fresh_false_takes_only_false_or_misleading_checks_from_the_chosen_years_one_per_claim():
    rijen = [_check(1), _check(2, oordeel="waar"), _check(3, jaar="2019"), _check(4, claim="c1"),
             _check(5, oordeel="misleidend"), _check(6, tekst="kort")]
    uit = ts.kies_checks(rijen, jaren=("2025", "2026"), n=10, set_naam="O")
    assert sorted(r["claim_id"] for r in uit) == ["c1", "c5"]
    assert all(r["set"] == "O" and r["id"].startswith("O:") for r in uit)


def test_no_outlet_fills_more_than_its_share_and_the_sample_is_fixed():
    rijen = [_check(i, uitgever="EFE Verifica") for i in range(100)] + [_check(i, uitgever="Fast Check CL")
                                                                        for i in range(100, 120)]
    a = ts.kies_checks(rijen, jaren=("2025",), n=40, set_naam="O", max_per=25)
    b = ts.kies_checks(list(reversed(rijen)), jaren=("2025",), n=40, set_naam="O", max_per=25)
    assert [r["id"] for r in a] == [r["id"] for r in b]
    assert sum(r["publisher"] == "EFE Verifica" for r in a) == 25 and len(a) == 40


def test_known_false_carries_the_addresses_of_its_own_checks_and_never_a_fresh_claim():
    rijen = [_check(1, jaar="2020"), _check(2, jaar="2020", claim="c1"), _check(3, jaar="2025")]
    uit = ts.kies_checks(rijen, jaren=("2020",), n=5, set_naam="K", eigen=True, uitgesloten={"c3"})
    assert len(uit) == 1 and sorted(uit[0]["eigen_urls"]) == ["https://verifica.efe.com/1", "https://verifica.efe.com/2"]


def test_a_german_check_without_a_category_takes_the_verdict_haiku_read_from_its_sentence():
    rijen = [_check(1, oordeel="onbekend"), _check(2, oordeel="onbekend"), _check(3, oordeel="onwaar")]
    uit = ts.met_omzetting(rijen, {"1": "onwaar", "2": "waar"})
    assert [r["oordeel"] for r in uit] == ["onwaar", "waar", "onwaar"]


def test_wikinews_gives_the_title_and_the_start_of_the_article():
    rijen = [{"sleutel": f"wikinews:es:{i}", "titel": f"Titular {i}", "tekst": f"Titular {i}\n" + "Texto largo. " * 200,
              "datum": "2010-01-01"} for i in range(5)]
    uit = ts.kies_wikinews(rijen, n=3)
    assert len(uit) == 3 and all(r["set"] == "W" and len(r["tekst"]) <= ts.MAX_TEKENS for r in uit)
    assert uit[0]["tekst"].startswith("Titular")


def test_ordinary_text_comes_from_the_web_text_of_that_language_only():
    rijen = [{"claim_id": f"es-{i}", "taal": "es", "varianten": [{"taal": "es", "tekst": f"Hola a todos {i}"}]}
             for i in range(10)] + [{"claim_id": "en-1", "taal": "en", "varianten": [{"taal": "en", "tekst": "Hi"}]}]
    uit = ts.kies_gewoon(rijen, "es", n=4)
    assert len(uit) == 4 and all(r["set"] == "G" and r["tekst"].startswith("Hola") for r in uit)


def test_the_verdict_a_fact_checker_wrote_behind_the_claim_never_goes_along():
    assert ts._kort("Boric fue al hotel más caro de Tokio: #Falso") == "Boric fue al hotel más caro de Tokio"
    assert ts._kort("Una foto de Lula #Engañoso ") == "Una foto de Lula"
    assert ts._kort("Protesta en Brasilia #ForaLula") == "Protesta en Brasilia #ForaLula"  # geen oordeel, dus blijft



PAGINA = ("<div><ul><li>17 de fevereiro de 2025: Uma manchete da balança</li></ul></div>"
          "<p><span>Agência Brasil</span> </p>"
          '<p><span style="font-size: 85%;">9 de maio de 2016</span></p>'
          "<p>A presidenta Dilma Rousseff chamou o processo de impeachment de interrupção ilegal e usurpadora do seu "
          "mandato e disse que vai lutar com todos os instrumentos para impedir que saia do cargo.</p>"
          "<p>Tem uma opinião sobre a notícia? Diga-nos!</p>")


def test_a_wikinews_page_gives_its_own_date_and_its_paragraphs_and_never_the_box_of_headlines():
    uit = ts.artigo_wikinews(PAGINA)
    assert uit.startswith("9 de maio de 2016 A presidenta Dilma Rousseff")
    assert "manchete" not in uit and "<" not in uit and "Diga-nos" not in uit
    assert ts.artigo_wikinews("<div><ul><li>17 de fevereiro de 2025: Só a balança</li></ul></div>") == ""


def test_the_repaired_set_keeps_the_same_sample_and_drops_an_article_without_text():
    oud = [{"id": "W:wikinews:pt:1", "set": "W", "tekst": "Kop Brasil 17 de fevereiro de 2025: …", "datum": "2016-05-09"},
           {"id": "W:wikinews:pt:2", "set": "W", "tekst": "Outra", "datum": "2010-01-01"}]
    kop = {"W:wikinews:pt:1": "Dilma chama impeachment de ilegal", "W:wikinews:pt:2": "Outra"}
    uit = ts.herstelde_w(oud, kop, {"W:wikinews:pt:1": ts.artigo_wikinews(PAGINA), "W:wikinews:pt:2": ""})
    assert [r["id"] for r in uit] == ["W:wikinews:pt:1"]
    assert uit[0]["tekst"].startswith("Dilma chama impeachment de ilegal 9 de maio de 2016 A presidenta")
    assert uit[0]["datum"] == "2016-05-09" and len(uit[0]["tekst"]) <= ts.MAX_TEKENS


# --- verse sets voor lezer-v10 (#32.43) --------------------------------------------------------------------------

def _wikinews(i, datum="2015-06-01", tekst=None):
    return {"sleutel": f"wikinews:es:{i}", "titel": f"Kop {i}", "url": f"https://es.wikinews.org/wiki/{i}",
            "datum": datum, "tekst": tekst or f"Kop {i}\nlunes 1 de junio de 2015 Het begin van artikel {i}."}


def test_what_earlier_runs_used_is_read_from_their_ids_and_texts():
    rijen = [{"id": "O:gfc-aaa", "set": "O", "tekst": "Una  afirmación"}, {"id": "W:wikinews:es:7", "set": "W",
                                                                            "tekst": "x"},
             {"id": "W2:wikinews:en:9", "set": "W2", "bron": "wikinews:en:9", "tekst": "y"},
             {"id": "M:05d3", "set": "M", "tekst": "Een nagemaakt merk"}, {"id": "WM:abc", "set": "W-merk", "tekst": "z"}]
    weg = ts.gebruikt(rijen)
    assert weg["claims"] == {"gfc-aaa"} and weg["sleutels"] == {"wikinews:es:7", "wikinews:en:9"}
    assert "WM:abc" in weg["ids"] and "una afirmación" in weg["teksten"] and "een nagemaakt merk" in weg["teksten"]


def test_a_fresh_set_never_holds_a_claim_article_headline_or_text_an_earlier_run_used():
    checks = [_check(i, jaar="2026") for i in range(10)] + [_check(10, jaar="2026", tekst="Ya usada antes")]
    wikinews = [_wikinews(i) for i in range(10)]
    w_merk = [{"id": f"WM:{i}", "set": "W-merk", "tekst": f"El País\nKop {i}", "datum": "2026-11-10"} for i in range(5)]
    weg = ts.gebruikt([{"id": "O:c1", "set": "O", "tekst": "x"}, {"id": "O:x", "set": "O", "tekst": "Ya  usada antes"},
                       {"id": "W:wikinews:es:2", "set": "W", "tekst": "y"}, {"id": "WM:3", "set": "W-merk", "tekst": "z"}])
    weg["claims"].add("c1")
    uit = ts.verse_set(checks, wikinews, w_merk, ("2026",), weg, aantal={"O": 20, "W": 20, "W-merk": 20})
    o, w, wm = ([r for r in uit if r["set"] == s] for s in ("O", "W", "W-merk"))
    assert {r["claim_id"] for r in o} == {f"c{i}" for i in (0, 2, 3, 4, 5, 6, 7, 8, 9)}
    assert len(w) == 9 and "W:wikinews:es:2" not in {r["id"] for r in w}
    assert [r["id"] for r in wm] == ["WM:0", "WM:1", "WM:2", "WM:4"]


def test_a_fresh_set_skips_wikinews_text_that_is_the_box_of_recent_headlines_and_is_fixed():
    balk = _wikinews(1, datum="2012-03-01", tekst="Kop 1\nÚltimas: 2025 x; 2026 y; 2025 z")
    wikinews = [balk] + [_wikinews(i) for i in range(2, 30)]
    weg = ts.gebruikt([])
    a = ts.verse_set([], wikinews, [], ("2026",), weg, aantal={"O": 0, "W": 10, "W-merk": 0})
    b = ts.verse_set([], list(reversed(wikinews)), [], ("2026",), weg, aantal={"O": 0, "W": 10, "W-merk": 0})
    assert [r["id"] for r in a] == [r["id"] for r in b] and len(a) == 10
    assert ts.verse_set([], [balk], [], ("2026",), weg, aantal={"O": 0, "W": 10, "W-merk": 0}) == []


# --- de datum van een oud artikel (#32.44) ------------------------------------------------------------------------

OUDE_PAGINA = ("<p>Representantes israelenses já chegaram ao Cairo, no Egito, para discutir uma proposta de "
               "cessar-fogo na Faixa de Gaza.</p>"
               "<ul><li><cite>Israel na mesa — <i>Télam</i>, 7 de janeiro de 2009</cite></li></ul>"
               '<div id="catlinks"><ul><li><a href="/wiki/Categoria:Publicado" title="Categoria:Publicado">Publicado'
               '</a></li><li><a href="/wiki/Categoria:8_de_janeiro_de_2009" title="Categoria:8 de janeiro de 2009">'
               "8 de janeiro de 2009</a></li></ul></div>")


def test_an_old_wikinews_page_without_a_dateline_takes_its_date_from_its_date_category():
    uit = ts.artigo_wikinews(OUDE_PAGINA)
    assert uit.startswith("8 de janeiro de 2009 Representantes israelenses")
    met_beide = PAGINA + '<a href="/wiki/Categoria:1_de_junho_de_2016" title="Categoria:1 de junho de 2016">x</a>'
    assert ts.artigo_wikinews(met_beide).startswith("9 de maio de 2016 A presidenta")
    sem_data = ("<p>Representantes israelenses já chegaram ao Cairo, no Egito, para discutir uma proposta de "
                "cessar-fogo na Faixa de Gaza.</p>")
    assert ts.artigo_wikinews(sem_data).startswith("Representantes israelenses")


def test_only_articles_without_a_year_in_their_text_are_fetched_again():
    rijen = [{"id": "W:wikinews:pt:1", "set": "W", "tekst": "Kop 9 de maio de 2016 A presidenta"},
             {"id": "W:wikinews:pt:2", "set": "W", "tekst": "Kop sem ano, ontem (7)"},
             {"id": "O:gfc-1", "set": "O", "tekst": "Sem ano"},
             {"id": "W:wikinews:pt:3", "set": "W", "tekst": "Kop met nummer 12023"}]
    assert [r["id"] for r in ts.zonder_jaartal(rijen)] == ["W:wikinews:pt:2", "W:wikinews:pt:3"]


# --- bekende nepbeelden per taal uit M4FC (#32.46, stap 3) ---------------------------------------------------------

def _m4fc(i, taal="Spanish", oordeel="false", claim=None):
    return {"image_url": f"https://img.example/{i}.jpg", "wayback_image_url": f"https://web.archive.org/x/{i}.jpg",
            "article_url": f"https://check.example/{i}", "claim_language": taal, "verdict_coarse": oordeel,
            "multilingual_claim": claim if claim is not None else f"Una foto muestra algo falso número {i}",
            "fc_pub_date": "2023-05-01", "fc_org": "larepublica.pe"}


def test_known_fake_images_of_one_language_come_with_their_claim_their_image_and_their_own_check():
    rijen = [_m4fc(i) for i in range(10)] + [_m4fc(10, taal="German"), _m4fc(11, oordeel="true"),
                                             _m4fc(12, claim="not enough information")]
    uit = ts.kies_m4fc(rijen, "es", n=5)
    assert len(uit) == 5 and uit == ts.kies_m4fc(list(reversed(rijen)), "es", n=5)
    r = uit[0]
    assert r["set"] == "N" and r["id"].startswith("N:") and r["beeld"].startswith("https://img.example/")
    assert r["beeld_reserve"].startswith("https://web.archive.org/") and r["eigen_urls"][0].startswith("https://check")
    assert {x["tekst"][:9] for x in uit} == {"Una foto "}
    assert len(ts.kies_m4fc(rijen, "es", n=50)) == 10


def test_a_second_fresh_round_leaves_out_the_first_one_and_every_later_use_and_has_its_own_seed():
    paden = ts.gebruikte_paden("en", ronde=2)
    assert "data/talen/vers/en.jsonl" in paden and set(ts.GEBRUIKT["en"]) <= set(paden)
    assert "data/duel/duel-2026-11-07-berichten.jsonl" in paden
    assert ts.gebruikte_paden("en", ronde=1) == list(ts.GEBRUIKT["en"])
    assert ts.zaad_vers(2) != ts.zaad_vers(1) == ts.ZAAD_VERS
    assert ts.vers_pad("en", 1).name == "en.jsonl" and ts.vers_pad("en", 2).parent.name == "vers2"


def test_a_third_fresh_round_also_leaves_out_the_second():
    paden = ts.gebruikte_paden("en", ronde=3)
    assert "data/talen/vers2/en.jsonl" in paden and "data/talen/vers/en.jsonl" in paden
    assert ts.zaad_vers(3) not in (ts.zaad_vers(1), ts.zaad_vers(2)) and ts.vers_pad("en", 3).parent.name == "vers3"


def test_dutch_and_french_have_their_own_media_and_years_and_nothing_used_yet():
    """B63, #32.59: Nederland en Vlaanderen, Frankrijk en Wallonië; vijf media met een band, elk in `MEDIA`."""
    from doublecheck import zoekcontrole as zc

    for taal in ("nl", "fr"):
        t = ts.TALEN[taal]
        assert len(t["feeds"]) == 5 and t["vers"] and t["bekend"] and not set(t["vers"]) & set(t["bekend"])
        assert all(naam in zc.MEDIA for naam in t["feeds"])
        assert ts.GEBRUIKT[taal] == () and ts.VERS[taal] == t["vers"]
    assert {"VRT NWS", "HLN"} <= set(ts.TALEN["nl"]["feeds"]) and {"Le Soir", "La Libre"} <= set(ts.TALEN["fr"]["feeds"])


def test_a_wikinews_page_that_is_no_article_never_enters_a_set():
    """§243: een categorie, een testpagina en een pagina zonder datumregel kwamen in W en kregen terecht *geen bewering*."""
    assert ts.wikinews_artikel({"titel": "Kop", "tekst": "Kop\nSaturday, November 13, 2004 Brazil ..."})
    assert ts.wikinews_artikel({"titel": "Kop", "tekst": "Kop\nzaterdag 13 november 2004 De minister ..."})
    assert not ts.wikinews_artikel({"titel": "Pages with broken graphs",
                                    "tekst": "Pages with broken graphs\nThis category is a tracking category."})
    assert not ts.wikinews_artikel({"titel": "Main Page/Sandbox4", "tekst": "Main Page/Sandbox4\n2005 Shqip (Albanian)"})
    assert not ts.wikinews_artikel({"titel": "How the Army Corps closed one breach",
                                    "tekst": "How the Army Corps closed one breach\nNew Orleans Disaster Related stories"})
    wikinews = [_wikinews(i) for i in range(5)] + [_wikinews(9, tekst="Kop 9\nThis category is a tracking category.")]
    uit = ts.verse_set([], wikinews, [], ("2026",), ts.gebruikt([]), aantal={"O": 0, "W": 10, "W-merk": 0})
    assert len(uit) == 5 and "W:wikinews:es:9" not in {r["id"] for r in uit}


def test_known_fake_images_also_come_in_dutch_and_french():
    rijen = [_m4fc(i, taal="Dutch") for i in range(4)] + [_m4fc(i, taal="French") for i in range(4, 7)]
    assert len(ts.kies_m4fc(rijen, "nl", n=60)) == 4 and len(ts.kies_m4fc(rijen, "fr", n=60)) == 3


def test_true_photos_of_one_language_leave_out_those_already_in_w_and_carry_their_own_check():
    """#32.54: echte foto's met een ware bewering, als W in een andere taal; wat al in de Engelse W staat (dezelfde
    rij van M4FC) valt eruit, zodat geen foto twee keer telt."""
    rijen = [_m4fc(i, taal="Portuguese", oordeel="true") for i in range(8)] + [_m4fc(8, taal="Portuguese")] + [
        {**_m4fc(9, taal="Portuguese", oordeel="true"), "fc_language": "french"}]
    al = {"https://img.example/0.jpg", "https://img.example/1.jpg"}
    uit = ts.kies_m4fc_waar(rijen, "pt", al_in_w=al, n=60)
    assert len(uit) == 6 and {r["set"] for r in uit} == {"W"} and all(r["id"].startswith("W:") for r in uit)
    assert "https://img.example/0.jpg" not in {r["beeld"] for r in uit}
    assert uit[0]["eigen_urls"][0].startswith("https://check.example/") and uit[0]["beeld_reserve"]
    assert uit == ts.kies_m4fc_waar(list(reversed(rijen)), "pt", al_in_w=al, n=60)


def test_a_fresh_set_leaves_out_images_already_measured():
    """#32.54, versie 2: verse Engelse sets zonder de beelden van N en W."""
    rijen = [_m4fc(i, taal="English") for i in range(6)]
    uit = ts.kies_m4fc(rijen, "en", n=60, uitsluiten={"https://img.example/0.jpg"})
    assert len(uit) == 5 and "https://img.example/0.jpg" not in {r["beeld"] for r in uit}
    assert ts.kies_m4fc(rijen, "en", n=60) == ts.kies_m4fc(rijen, "en", n=60, uitsluiten=set())


def test_an_english_claim_comes_from_the_claim_field_where_m4fc_leaves_the_translation_empty():
    rijen = [{**_m4fc(i, taal="English", claim="not enough information"), "claim": f"A photo shows thing {i}"}
             for i in range(3)]
    assert [r["tekst"] for r in ts.kies_m4fc(rijen, "en", n=60)] == [f"A photo shows thing {i}" for i in range(3)]
