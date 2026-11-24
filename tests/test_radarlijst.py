"""De radar van de eigen redactie (PLAN #37.1, B82; PO 2026-11-18: "Ja, bouw de radar maar"): elke week een lijst met wat in
het Nederlands rondgaat, uit de Community Notes van X en de tips. Lokaal: een notetekst gaat nooit naar een externe
dienst en nooit op de site."""

import json

import numpy as np

from doublecheck import radarlijst as rl


def _note(nr, post, datum, tekst, status=""):
    return {"note": nr, "post": post, "datum": datum, "tekst": tekst, "status": status}


def test_the_week_is_the_seven_days_up_to_the_last_note_in_the_export():
    notes = [_note("1", "a", "2026-11-07", "x"), _note("2", "b", "2026-11-08", "x"), _note("3", "c", "2026-11-14", "x")]
    assert [n["note"] for n in rl.van_de_week(notes)] == ["2", "3"]
    assert rl.van_de_week([]) == []


def test_notes_on_one_post_and_near_identical_notes_on_several_posts_become_one_claim():
    notes = [_note("1", "a", "2026-11-08", "AI-beeld van het standbeeld"), _note("2", "a", "2026-11-08", "nog een"),
             _note("3", "b", "2026-11-09", "AI-beeld van het standbeeld, ander bericht"), _note("4", "c", "2026-11-09", "box 3")]
    v = np.array([[1, 0], [0.2, 0.98], [0.99, 0.14], [0, 1]], dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    groepen = rl.groepeer(notes, v, drempel=0.9)
    assert sorted(sorted(g["posts"]) for g in groepen) == [["a", "b"], ["c"]]
    eerste = next(g for g in groepen if "a" in g["posts"])
    assert eerste["notes"] == ["1", "2", "3"] and eerste["eerst"] == "2026-11-08"


def test_a_note_that_says_parody_stolen_post_bot_or_fake_account_is_probably_not_a_claim():
    for tekst in ("Parody.  https://x.com/a", "stolen post https://x.com/b", "Dit account is niet echt, het is een bot.",
                  "Deze post is een kopie van een eerdere post van @x.", "Dit is een nep account.", "Deze post is satirisch bedoeld"):
        assert rl.geen_bewering(tekst), tekst
    assert not rl.geen_bewering("De afbeelding is AI-gegenereerd en toont niet het echte standbeeld.")
    # een lange note die een bewering uit satire-accounts weerlegt, gaat over een echte bewering (2026-11-09)
    assert not rl.geen_bewering("De EU dreigt niet met een boete van 5 miljard euro of Starlink-verbod; claims komen uit "
                                "satire-accounts en zijn ongegrond. Musk deed geen dergelijke uitspraak over satellieten.")


def test_a_note_that_links_to_a_fact_checker_says_the_claim_was_already_checked_and_names_its_sources():
    tekst = ("Bevestigt het: https://factchecknederland.afp.com/doc.afp.com.84L43NQ en "
             "https://nos.nl/artikel/2638774-veel-kritiek en https://www.belastingdienst.nl/wps/wcm")
    assert rl.al_gecheckt(tekst, {"factchecknederland.afp.com"}) == ["https://factchecknederland.afp.com/doc.afp.com.84L43NQ"]
    assert rl.al_gecheckt("geen links", {"afp.com"}) == []
    assert rl.bronnen(tekst) == ["factchecknederland.afp.com", "nos.nl", "belastingdienst.nl"]


def test_the_list_puts_claims_seen_on_more_posts_and_with_helpful_notes_first():
    g = [{"posts": ["a"], "notes": ["1"], "behulpzaam": 0}, {"posts": ["b", "c"], "notes": ["2", "3"], "behulpzaam": 0},
         {"posts": ["d"], "notes": ["4", "5"], "behulpzaam": 1}]
    assert [x["posts"][0] for x in sorted(g, key=rl.rangorde)] == ["b", "d", "a"]


def test_a_tip_keeps_what_it_says_and_where_it_was_seen_never_who_sent_it(tmp_path):
    pad = tmp_path / "tips.jsonl"
    rl.tip_erbij(pad, "Video van een 'martelkelder' bij Kiev", link="https://x.com/i/status/1", vandaag="2026-11-18")
    tips = rl.tips(pad)
    assert tips == [{"datum": "2026-11-18", "tekst": "Video van een 'martelkelder' bij Kiev", "link": "https://x.com/i/status/1"}]
    assert set(tips[0]) == {"datum", "tekst", "link"}


def test_the_weekly_page_shows_each_claim_with_its_counts_sources_and_links_and_leaves_non_claims_out():
    """PO 2026-11-22: "'Waarschijnlijk geen bewering' kan allemaal weg"."""
    groep = {"posts": ["2119390304184782910"], "notes": ["n1"], "behulpzaam": 1, "eerst": "2026-11-08",
             "tekst": "Dit fragment komt niet van de Rode Lijn-demonstratie maar van een protest bij een datacentrum.",
             "bronnen": ["at5.nl", "nos.nl"], "gecheckt": [], "archief": None, "geen_bewering": False}
    tweede = {**groep, "posts": ["7"], "notes": ["n3"], "tekst": "Nog een video van hetzelfde protest."}
    tekst = rl.pagina({"van": "2026-11-08", "tot": "2026-11-14", "notes": 37, "posts": 37}, [[groep, tweede]], [])
    assert "ook over dit onderwerp (1 bewering meer, 2 posts samen)" in tekst and "Nog een video" in tekst
    for deel in ("2026-11-08", "Rode Lijn", "at5.nl", "https://x.com/i/status/2119390304184782910",
                 "https://x.com/i/birdwatch/n/n1", "1 post"):
        assert deel in tekst, deel
    assert "geen bewering" not in tekst


def test_claims_about_the_same_subject_are_listed_together_with_the_biggest_first():
    groepen = [{"posts": ["a"], "notes": ["1"], "behulpzaam": 0, "tekst": "box 3 tabel"},
               {"posts": ["b", "c"], "notes": ["2", "3"], "behulpzaam": 0, "tekst": "AI-beeld standbeeld"},
               {"posts": ["d"], "notes": ["4"], "behulpzaam": 0, "tekst": "box 3 andere tabel"}]
    v = np.array([[1, 0], [0, 1], [0.8, 0.6]], dtype=np.float32)
    per = rl.onderwerpen(groepen, v, [0, 1, 2], drempel=0.65)
    assert [[g["tekst"] for g in o] for o in per] == [["AI-beeld standbeeld"], ["box 3 tabel", "box 3 andere tabel"]]


def test_an_ordinary_article_of_a_news_medium_with_a_fact_check_desk_is_not_a_fact_check():
    # vrt.be staat bij de checks in de database, maar een gewoon artikel van de VRT is geen factcheck (2026-11-18)
    domeinen = rl.zonder_nieuwsmedia({"vrt.be", "factchecknederland.afp.com", "nieuwscheckers.nl"})
    assert domeinen == {"nieuwscheckers.nl"}
    assert rl.al_gecheckt("https://www.vrt.be/vrtnws/nl/2026/11/10/grensoverschrijdend-gedrag-content-creator/",
                          domeinen) == []
    # de factcheckrubriek van een nieuwsmedium telt wel, op het adres
    assert rl.al_gecheckt("https://factchecknederland.afp.com/doc.afp.com.84L43NQ", domeinen) == [
        "https://factchecknederland.afp.com/doc.afp.com.84L43NQ"]
    assert rl.al_gecheckt("https://nieuwscheckers.nl/x/", domeinen) == ["https://nieuwscheckers.nl/x/"]


def test_a_link_does_not_make_an_english_note_dutch():
    assert not rl.in_het_nederlands(
        "It’s $59.99 https://www.nintendo.com/us/store/products/the-legend-of-zelda-ocarina-of-time-switch-2/")
    assert rl.in_het_nederlands("Deze afbeelding is gemaakt met AI en toont niet het echte standbeeld. https://nos.nl/a")
    assert not rl.in_het_nederlands("https://nos.nl/artikel/2638774-veel-kritiek")
    # py3langid zegt bij korte Engelse zinnen soms Nederlands (0,997 bij "Jensen"), dus tellen de kleine woorden mee
    assert not rl.in_het_nederlands("Jensen did not get fired. He resigned.")
    assert not rl.in_het_nederlands("Virgil van Dijk (pictured) has ~92 career G/A (70 goals + 22 assists) across senior "
                                    "competitions, not 110.")
    assert rl.in_het_nederlands("Nederland was neutraal tijdens WOI en niet door Duitsland bezet")


# --- de radar per taal (PLAN #37.7, B85) ---------------------------------------------------------------------------


def test_a_note_belongs_to_a_site_language_and_dutch_keeps_its_strict_rule():
    assert rl.taal_van("The video shows a riot in The Hague in February 2024, not this week.") == "en"
    assert rl.taal_van("El vídeo no es de este año, se grabó en Málaga en julio de 2026.") == "es"
    assert rl.taal_van("De video is niet van deze week maar van februari 2024 in Den Haag.") == "nl"
    # een link maakt een Engelse note niet Nederlands, en wat te kort is, telt nergens
    assert rl.taal_van("It's $59.99 https://www.nintendo.com/us/store/products/the-legend-of-zelda/") != "nl"
    assert rl.taal_van("Fake. https://x.com/a") is None
    assert set(rl.TALEN) == set(rl.TAALNAAM) and rl.TALEN[0] == "nl" and len(rl.TALEN) == 15


def test_grouping_thousands_of_posts_gives_the_same_claims_as_comparing_them_one_by_one():
    rng = np.random.default_rng(7)
    basis = rng.normal(size=(40, 16))
    v = np.concatenate([basis[rng.integers(0, 40, 300)] + rng.normal(scale=.15, size=(300, 16))]).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    notes = [_note(str(i), f"p{i // 2}", f"2026-11-{10 + i % 5:02d}", "x") for i in range(300)]

    def een_voor_een(notes, v, drempel):
        per = {}
        for i, n in enumerate(notes):
            per.setdefault(n["post"], []).append(i)
        orde = sorted(per, key=lambda p: (-len(per[p]), min(notes[i]["datum"] for i in per[p]), p))
        kernen, posts = [], []
        for p in orde:
            k = next((j for j, kern in enumerate(kernen) if float(v[kern] @ v[per[p][0]]) >= drempel), None)
            if k is None:
                kernen.append(per[p][0]); posts.append([])
                k = len(kernen) - 1
            posts[k].append(p)
        return posts

    assert [g["posts"] for g in rl.groepeer(notes, v, drempel=0.9)] == een_voor_een(notes, v, 0.9)


def test_the_radar_puts_unchecked_claims_seen_in_more_languages_and_with_an_image_or_video_first():
    g = [{"posts": ["a", "b", "c"], "notes": ["1"], "behulpzaam": 2, "gecheckt": ["https://afp.com/x"]},
         {"posts": ["d"], "notes": ["2"], "behulpzaam": 0, "gecheckt": [], "ook_in": ["es", "fr"]},
         {"posts": ["e", "f"], "notes": ["3"], "behulpzaam": 0, "gecheckt": [], "media": True},
         {"posts": ["g", "h"], "notes": ["4"], "behulpzaam": 0, "gecheckt": []}]
    assert [x["posts"][0] for x in sorted(g, key=rl.rangorde_radar)] == ["d", "e", "g", "a"]


def test_a_claim_that_circulates_in_another_language_the_same_week_names_that_language():
    kernen = {"nl": np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
              "en": np.array([[0.96, 0.28, 0], [0, 0, 1]], dtype=np.float32),
              "es": np.array([[0.9, 0.436, 0]], dtype=np.float32)}
    ook = rl.ook_in(kernen, drempel=0.85)
    assert ook["nl"] == [["en", "es"], []] and ook["en"] == [["nl", "es"], []] and ook["es"] == [["nl", "en"]]


def test_the_weekly_page_of_another_language_names_it_marks_images_and_other_languages_and_stays_short():
    groep = {"posts": ["1"], "notes": ["n1"], "behulpzaam": 0, "eerst": "2026-11-10", "tekst": "The video is from 2024.",
             "bronnen": [], "gecheckt": [], "archief": None, "geen_bewering": False, "media": True, "ook_in": ["es"]}
    veel = [[{**groep, "posts": [str(i)], "notes": [f"n{i}"]}] for i in range(rl.MAX_ONDERWERPEN + 5)]
    tekst = rl.pagina({"van": "2026-11-09", "tot": "2026-11-15", "notes": 99, "posts": 50}, veel, [], taal="en")
    assert "99 notes in het Engels" in tekst and "met beeld of video" in tekst and "ook in: het Spaans" in tekst
    assert tekst.count("https://x.com/i/birdwatch/n/") == rl.MAX_ONDERWERPEN and "en nog 5 onderwerpen" in tekst


def test_the_overview_lists_each_claim_seen_in_several_languages_once_with_the_most_languages_first():
    a = {"posts": ["1", "2"], "notes": ["n1"], "eerst": "2026-11-10", "tekst": "Video uit 2024", "ook_in": ["es"]}
    b = {"posts": ["3"], "notes": ["n2"], "eerst": "2026-11-11", "tekst": "Vídeo de 2024", "ook_in": ["nl"]}
    c = {"posts": ["4"], "notes": ["n3"], "eerst": "2026-11-12", "tekst": "Fake quote", "ook_in": ["nl", "es"]}
    kernen = {"nl": np.array([[1, 0]], dtype=np.float32), "es": np.array([[0.99, 0.14]], dtype=np.float32),
              "en": np.array([[0, 1]], dtype=np.float32)}
    tekst = rl.overzicht({"van": "2026-11-09", "tot": "2026-11-15"}, {"nl": [a], "es": [b], "en": [c]}, kernen, drempel=0.9)
    assert tekst.index("Fake quote") < tekst.index("Video uit 2024") and "Vídeo de 2024" not in tekst
    assert "ook in: het Nederlands, het Spaans" in tekst


# --- internationaal genoeg (PO 2026-11-19: "Ja, bouw het zo in met 20 talen") ---------------------------------------


def _register(tmp_path):
    import sqlite3

    pad = tmp_path / "publicatie.db"
    if pad.exists():
        return pad
    c = sqlite3.connect(pad)
    c.execute("CREATE TABLE naam (nummer TEXT, soort TEXT, naam_en TEXT, naam_nl TEXT, naam_ja TEXT, wikis INTEGER)")
    c.execute("CREATE TABLE naam_vorm (naam TEXT, vorm TEXT)")
    c.executemany("INSERT INTO naam VALUES (?,?,?,?,?,?)", [
        ("Q1", "persoon", "Rob Jetten", "Rob Jetten", "ロブ・イェッテン", 45), ("Q2", "organisatie", "NATO", "NAVO", "北大西洋条約機構", 200),
        ("Q3", "persoon", "Jan Jansen", "Jan Jansen", "", 4), ("Q4", "plaats", "Den Haag", "Den Haag", "", 150)])
    c.executemany("INSERT INTO naam VALUES (?,?,?,?,?,?)", [
        ("Q5", "persoon", "Boris Johnson", "Boris Johnson", "", 200), ("Q6", "persoon", "Lyndon B. Johnson", "Lyndon B. Johnson", "", 150),
        ("Q7", "organisatie", "Facebook", "Facebook", "", 250), ("Q8", "persoon", "Catherine II of Russia", "Catharina II van Rusland", "", 121),
        ("Q9", "plaats", "Russia", "Rusland", "", 300), ("Q10", "organisatie", "Reuters", "Reuters", "", 85)])
    c.executemany("INSERT INTO naam_vorm VALUES (?,?)", [("Q1", "Jetten"), ("Q2", "North Atlantic Treaty Organization"),
                                                       ("Q5", "BoJo"), ("Q5", "Johnson")])
    c.commit()
    return pad


def _wikidata(tmp_path):
    pad = tmp_path / "wikidata.jsonl"
    pad.write_text(json.dumps({"nummer": "Q10", "p31": ["Q192283"], "kenmerken": {"mens": False, "wikis": 85}}) + "\n" +
                   json.dumps({"nummer": "Q11", "p31": ["Q5"], "kenmerken": {"mens": True, "wikis": 20, "namen": {"en": "Jesse Klaver"},
                                                                         "vormen": []}}) + "\n", encoding="utf-8")
    return pad


def test_a_claim_naming_someone_with_articles_in_twenty_languages_of_wikipedia_is_international_enough(tmp_path):
    index = rl.bekende_namen(_register(tmp_path), drempel=20)
    assert rl.namen_in("Premier Jetten maakte geen gebaar in de RAI.", index) == [("Rob Jetten", 45)]
    assert rl.namen_in("De NAVO sprak dat tegen.", index) == [("NATO", 200)]
    assert rl.namen_in("北大西洋条約機構は否定した", index) == [("NATO", 200)]
    # een naam met te weinig talen, een plaats, en een gewoon woord dat op een naam lijkt, tellen niet
    assert rl.namen_in("Jan Jansen in Den Haag zei dat de jetten niet klopten.", index) == []
    # een achternaam die twee bekende namen delen, een losse alias en een platform tellen ook niet
    assert rl.namen_in("Johnson zei het op Facebook, schreef BoJo.", index) == []
    assert rl.namen_in("Boris Johnson zei het.", index) == [("Boris Johnson", 200)]
    # een vorst krijgt geen achternaam, en een persbureau is een bron, geen onderwerp (met de soort uit Wikidata)
    index = rl.bekende_namen(_register(tmp_path), drempel=20, wikidata=_wikidata(tmp_path))
    assert rl.namen_in("Russia denied it, Reuters reported.", index) == []
    assert rl.namen_in("Jesse Klaver zei het niet.", index) == [("Jesse Klaver", 20)]
    # een bijnaam van gewone woorden telt alleen als eigennaam (Al-Qaeda heet ook "The Base")
    assert rl.namen_in("a kite over the north atlantic treaty organization base", index) == []
    assert rl.namen_in("The North Atlantic Treaty Organization denied it.", index) == [("NATO", 200)]


def test_the_radar_puts_a_known_name_first_then_other_languages_then_a_universal_trick_before_a_local_claim():
    lokaal = {"posts": ["a", "b", "c"], "notes": ["1"], "behulpzaam": 0, "gecheckt": []}
    naam = {"posts": ["d"], "notes": ["2"], "behulpzaam": 0, "gecheckt": [], "namen": [("Rob Jetten", 45)]}
    truc = {"posts": ["e"], "notes": ["3"], "behulpzaam": 0, "gecheckt": [], "truc": ["oud als nieuw"]}
    meer_talen = {"posts": ["f"], "notes": ["4"], "behulpzaam": 0, "gecheckt": [], "ook_in": ["en"]}
    assert [g["posts"][0] for g in sorted([lokaal, truc, naam, meer_talen], key=rl.rangorde_radar)] == ["d", "f", "e", "a"]


def test_the_page_says_which_known_name_and_which_trick_make_a_claim_international():
    g = {"posts": ["1"], "notes": ["n1"], "behulpzaam": 0, "eerst": "2026-11-10", "tekst": "Het beeld is van 2024.",
         "bronnen": [], "gecheckt": [], "archief": None, "geen_bewering": False, "namen": [("Rob Jetten", 45)],
         "truc": ["oud als nieuw"]}
    tekst = rl.pagina({"van": "2026-11-09", "tot": "2026-11-15", "notes": 1, "posts": 1}, [[g]], [])
    assert "bekende naam: Rob Jetten (45 talen op Wikipedia)" in tekst and "truc: oud als nieuw" in tekst


def test_a_subject_is_joined_through_its_first_claim_only_so_thousands_of_claims_do_not_chain_together():
    """In het Engels ketende "lijkt op een lid" 5.816 beweringen aan elkaar (2026-11-19): nu alleen via de eerste."""
    groepen = [{"posts": [p] * n, "notes": [p], "behulpzaam": 0, "tekst": p} for p, n in (("a", 3), ("b", 2), ("c", 1))]
    v = np.array([[1, 0], [0.7, 0.714], [0.0, 1]], dtype=np.float32)   # a~b en b~c, maar a en c niet
    per = rl.onderwerpen(groepen, v, [0, 1, 2], drempel=0.65)
    assert [[g["tekst"] for g in o] for o in per] == [["a", "b"], ["c"]]


def test_the_notification_says_where_the_english_list_is():
    """PO 2026-11-22: "Ik zag net de 'weekradar' van factiz langskomen, maar weet niet waar ik deze kan terugvinden"; sinds
    2026-11-23 is de Engelse lijst de enige (PO: "Mag gewoon in het engels, NL wordt 1 van de vertaal talen later")."""
    lijst = rl.MAP / "lijst"
    paden = [lijst / "2026-11-20-en.md", lijst / "2026-11-20-talen.md"]
    tekst = rl.meldtekst(paden)
    assert "2 lijsten" in tekst and "data/radar/lijst/2026-11-20-en.md" in tekst
    # zonder Engelse lijst de map, en nooit een aanhalingsteken dat de melding breekt
    assert "data/radar/lijst/" in rl.meldtekst(paden[1:]) and '"' not in tekst


def test_the_radar_reads_every_language_but_writes_only_the_english_list():
    """De andere talen blijven nodig om te zien waar een onderwerp ook rondgaat (ook in), maar alleen de Engelse lijst en het
    overzicht over de talen heen komen op schijf; weg en tips horen bij die lijst (PO 2026-11-23)."""
    assert rl.LIJSTEN == ("en",)
    assert "en" in rl.TALEN and len(rl.TALEN) > 1


def test_a_note_that_says_no_note_is_needed_is_not_a_claim():
    """PO 2026-11-22, nummer 4 van de Nederlandse lijst: "Geen Note nodig voor deze post"."""
    for tekst in ("Op de post staat duidelijk dat het een citaat is. Geen Note nodig voor deze post.", "NNN. Dit is een mening.",
                  "No note needed, this is clearly an opinion.", "NNN - the post is accurate"):
        assert rl.geen_bewering(tekst), tekst
    assert not rl.geen_bewering("De video is van 2019 en toont geen protest in Den Haag.")


LIJST = """# De radar: 2026-11-14 tot 2026-11-20

14 notes in het Nederlands op 14 posts: 4 onderwerpen met 4 beweringen. Uit de Community Notes van X.

## Onderwerpen

1. Eerste.
   - 1 post, 1 note (0 behulpzaam), eerst gezien 2026-11-16
   - https://x.com/i/status/11 · https://x.com/i/birdwatch/n/111
2. Tweede, weg.
   - 1 post, 1 note (0 behulpzaam), eerst gezien 2026-11-14
   - https://x.com/i/status/22 · https://x.com/i/status/23 · https://x.com/i/birdwatch/n/222
3. Derde.
   - ook over dit onderwerp (1 bewering meer, 2 posts samen):
     - Een andere. https://x.com/i/status/34
   - https://x.com/i/status/33 · https://x.com/i/birdwatch/n/333
4. Vierde, weg.
   - https://x.com/i/status/44 · https://x.com/i/birdwatch/n/444

## Tips

- 2026-11-15: een tip
"""


def test_the_editor_takes_numbers_out_of_the_list_renumbers_the_rest_and_keeps_their_posts_and_notes():
    """PO 2026-11-22: "IN NL kunnen weg: 4 5 8 11"; wat weg is, komt de week erna niet terug."""
    tekst, weg = rl.haal_weg(LIJST, [2, 4])
    assert "Tweede" not in tekst and "Vierde" not in tekst and "## Tips" in tekst and "een tip" in tekst
    assert [r for r in tekst.splitlines() if r[:2] in ("1.", "2.", "3.")] == ["1. Eerste.", "2. Derde."]
    assert weg == [{"posts": ["22", "23"], "notes": ["222"], "tekst": "Tweede, weg."},
                   {"posts": ["44"], "notes": ["444"], "tekst": "Vierde, weg."}]


def test_what_was_taken_out_does_not_come_back_the_next_week():
    groepen = [{"posts": ["22"], "notes": ["999"]}, {"posts": ["55"], "notes": ["444"]}, {"posts": ["66"], "notes": ["666"]}]
    weg = [{"posts": ["22", "23"], "notes": ["222"]}, {"posts": ["44"], "notes": ["444"]}]
    assert rl.zonder_weg(groepen, weg) == [{"posts": ["66"], "notes": ["666"]}]
