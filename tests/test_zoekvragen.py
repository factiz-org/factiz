"""De vraag zoals mensen haar stellen (PLAN #34.2cf, SPECS E9.S8 AC11)."""

from __future__ import annotations

import json

from doublecheck import zoekvragen as zv


def test_the_question_is_in_the_language_the_page_is_findable_in():
    """De taal van de bewering als het een taal van de site is; anders het Engels (x_default), uit de Engelse vertaling."""
    assert zv.bron("nl", "Rutte zei dat", {"en": "Rutte said that"}) == ("nl", "Rutte zei dat")
    assert zv.bron("ta", "தமிழ் கூற்று", {"en": "A Tamil claim", "hi": "एक दावा"}) == ("en", "A Tamil claim")
    # zonder Engelse vertaling de eerste vertaling in een taal van de site
    assert zv.bron("ta", "தமிழ் கூற்று", {"hi": "एक दावा"}) == ("hi", "एक दावा")
    # zonder enige vertaling de hoofdmap, en het model schrijft de vraag uit de bewering zelf
    assert zv.bron("ml", "മലയാളം", {}) == ("en", "മലയാളം")


def _antwoord(*rijen):
    return json.dumps({"antwoorden": [{"nr": n, "vraag": v, "onderwerp": o} for n, v, o in rijen]})


def test_only_a_real_question_and_a_short_noun_phrase_pass():
    teksten = ["Greta Thunberg houdt het boek omhoog.", "Claim vier", "Claim vijf", "Claim zes"]
    tekst = _antwoord(
        (1, "Klopt het dat Greta Thunberg het boek omhooghoudt?", "Greta Thunberg en het boek"),
        (2, "Klopt het dat claim vier waar is", "Claim vier"),                       # geen vraagteken
        (3, "Klopt het dat claim vijf waar is?", "Claim vijf is niet waar."),        # een onderwerp dat iets beweert
        (4, "Claim zes?", "Claim zes"))                                              # de bewering met een vraagteken
    uit = zv.lees_vragen(tekst, "nl", teksten)
    assert [bool(u) for u in uit] == [True, False, False, False]
    assert uit[0] == {"vraag": "Klopt het dat Greta Thunberg het boek omhooghoudt?", "onderwerp": "Greta Thunberg en het boek"}
    # een Chinees en een Arabisch vraagteken tellen, en een korte Chinese vraag is een volle vraag
    assert zv.lees_vragen(_antwoord((1, "這張照片是真的嗎？", "照片")), "zh", ["這張照片是真的"])[0]
    assert zv.lees_vragen(_antwoord((1, "هل صحيح أن هذه الصورة حقيقية؟", "الصورة")), "ar", ["هذه الصورة حقيقية"])[0]
    # een bewering die zelf al een vraag is, mag de vraag zijn
    assert zv.lees_vragen(_antwoord((1, "What were the final words of Lata Mangeshkar?", "Lata Mangeshkar's final words")),
                          "en", ["What were the final words of Lata Mangeshkar?"])[0]


def test_a_question_or_subject_in_another_language_than_the_page_does_not_pass():
    """In de eerste proef schreef het model op een Spaanse pagina Nederlands en op een Engelse pagina een Nederlands
    onderwerp (zoekvraag-v1)."""
    es = ["Una foto muestra a Lisa Monaco con el presidente"]
    assert zv.lees_vragen(_antwoord((1, "Is deze foto echt en toont hij Lisa Monaco met de president?", "Foto van Lisa Monaco")),
                          "es", es) == [None]
    assert zv.lees_vragen(_antwoord((1, "¿Es real la foto de Lisa Monaco con el presidente?", "Foto de Lisa Monaco")),
                          "es", es)[0]
    en = ["Hindu children were shaved and beaten after visiting a church"]
    assert zv.lees_vragen(_antwoord((1, "Is it true that Hindu children were shaved and beaten after visiting a church?",
                                     "Hindoe-kinderen kaalgeschoren en geslagen na kerkbezoek")), "en", en) == [None]
    # een taal met een eigen schrift: het onderwerp moet er tekens van hebben
    fa = ["ویدیوی دو کودک از غزه"]
    assert zv.lees_vragen(_antwoord((1, "آیا این ویدیو دو کودک از غزه را نشان می‌دهد؟", "Video von zwei Kindern aus Gaza")),
                          "fa", fa) == [None]
    assert zv.lees_vragen(_antwoord((1, "آیا این ویدیو دو کودک از غزه را نشان می‌دهد؟", "ویدیوی دو کودک از غزه")), "fa", fa)[0]


def test_a_number_given_twice_or_out_of_range_never_counts():
    teksten = ["One", "Two"]
    tekst = _antwoord((1, "Is it true that one is the case?", "One"), (1, "Is it really true that one is the case?", "One"),
                      (3, "Is it true that three is the case?", "Three"))
    assert zv.lees_vragen(tekst, "en", teksten) == [None, None]
    assert zv.lees_vragen("geen json", "en", teksten) == [None, None]


def test_too_long_questions_and_subjects_do_not_pass():
    tekst = _antwoord((1, "Is it true that " + "the claim is long " * 12 + "?", "A"), (2, "Is it true that B is the case?", "B" * 80))
    assert zv.lees_vragen(tekst, "en", ["A", "B"]) == [None, None]


def _antwoorden(n, label_vraag=None):
    return [{"pagina": f"p{i:03}", "taal": "en", "bron": f"Claim {i}", "vraag": f"Is claim {i} true?",
             "onderwerp": f"Claim {i}", "versie": zv.VERSIE} for i in range(n)]


def _labels(tmp_path, antwoorden, labels):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": {a["pagina"]: {"label": l, "vraag": a["vraag"], "onderwerp": a["onderwerp"]}
                                          for a, l in zip(antwoorden, labels)}}), encoding="utf-8")
    return pad


def test_the_gate_opens_only_after_190_read_with_at_most_one_error_in_a_hundred(tmp_path):
    antwoorden = _antwoorden(250)
    assert zv.poort(antwoorden, tmp_path / "geen.json")[0] is False
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 189))[0] is False
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 190))[0] is True
    # hoogstens 1 fout op de 100, naar boven afgerond (B87, zoals B77): 2 van de 200 mag, 3 niet
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 198 + ["fout"] * 2))[0] is True
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 197 + ["fout"] * 3))[0] is False
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 192 + ["fout"] * 2))[0] is True
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 199 + ["twijfel"]))[0] is False
    assert zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 194 + ["klein"] * 6))[0] is False
    open_, reden = zv.poort(antwoorden, _labels(tmp_path, antwoorden, ["goed"] * 195 + ["klein"] * 5))
    assert open_ and "195 goed, 5 klein en 0 fout" in reden
    assert len(zv.geldig(antwoorden, tmp_path / "labels.json")[0]) == 250
    assert zv.geldig(antwoorden, tmp_path / "geen.json")[0] == {}


def test_a_label_counts_only_for_the_exact_question_that_was_read(tmp_path):
    """Schrijft het model een vraag opnieuw, dan telt mijn oude lezing er niet meer voor."""
    antwoorden = _antwoorden(200)
    pad = _labels(tmp_path, antwoorden, ["goed"] * 200)
    nieuw = [*antwoorden, *({**a, "vraag": a["vraag"].replace("Is", "Is it really")} for a in antwoorden[:11])]
    assert zv.poort(antwoorden, pad)[0] is True
    assert zv.poort(nieuw, pad) == (False, "189 gelezen, minstens 190")


def test_the_sample_is_the_same_for_the_same_pages():
    paginas = [f"p{i}" for i in range(1000)]
    assert zv.proefpaginas(paginas) == zv.proefpaginas(list(reversed(paginas))) and len(zv.proefpaginas(paginas)) == 200


def test_one_question_to_the_model_is_for_one_language_with_its_own_question_forms():
    v = zv.vraagverzoek("nl", ["Rutte zei X", "Een foto toont Y"])
    tekst = v["messages"][0]["content"][0]["text"]
    assert tekst.startswith("Write in Dutch.") and "1. Rutte zei X" in tekst and "2. Een foto toont Y" in tekst
    assert "Klopt het dat" in v["system"] and "in Dutch" in v["system"] and "never add a first name" in v["system"]
    assert "never reveals or presupposes the answer" in v["system"] and v["model"].startswith("claude-haiku")
    assert set(zv.VORMEN) == set(zv.TAALNAMEN)                  # voor elke taal van de site voorbeelden in die taal


def test_one_question_mark_and_no_letters_from_a_foreign_script():
    """In de ontwikkelset van v2: twee vragen in één (Chinees) en een Hebreeuwse letter in een Arabische naam."""
    zh = ["行政院下令要政府部門所有系統改『稱謂』"]
    assert zv.lees_vragen(_antwoord((1, "行政院是否下令改「稱謂」？同婚修法後什麼都不會變是真的嗎？", "行政院與稱謂")), "zh", zh) == [None]
    ar = ["مقتل رئيس الوزراء الإسرائيلي بنيامين نتنياهو"]
    assert zv.lees_vragen(_antwoord((1, "هل قُتل بنيامين نتنياהו؟", "مقتل نتنياهو")), "ar", ar) == [None]
    assert zv.lees_vragen(_antwoord((1, "هل قُتل بنيامين نتنياهو؟", "مقتل نتنياهو")), "ar", ar)[0]
    # een Latijnse naam in een Arabische vraag mag, en een schrift dat in de bewering staat ook
    assert zv.schrift_klopt("هل قال Biden ذلك؟", "قال بايدن", "ar") and zv.schrift_klopt("Did Modi say ‘नमस्ते’?", "‘नमस्ते’", "en")


def test_the_v3_instructions_carry_the_lessons_of_the_development_set():
    s = zv.vraagverzoek("en", ["x"])["system"]
    for regel in ("never name or describe a speaker", "never add a first name", "Mention a photo, video or image only if",
                  "without the finding", "do not translate them", "Exactly one question", 'not "someone"',
                  "Is this Dilip Kumar's last video?"):
        assert regel in s, regel


def test_an_euvsdisinfo_claim_carries_its_headline_from_the_address():
    """In de tweede ontwikkelset vroeg het model bij 9 van de 13 fouten naar een waar bijfeit uit een lange samenvatting
    van EUvsDisinfo. Hun adres noemt de kern; bij andere redacties noemt het vaak de bevinding, dus daar niet."""
    assert zv.kop_uit_adres("https://euvsdisinfo.eu/report/wests-support-for-ukraine-fosters-russophobia") == \
        "wests support for ukraine fosters russophobia"
    assert zv.kop_uit_adres("https://euvsdisinfo.eu/report/there-was-a-coup-in-ukraine-2/") == "there was a coup in ukraine"
    assert zv.kop_uit_adres("https://www.snopes.com/fact-check/no-biden-did-not/") == ""
    v = zv.vraagverzoek("en", ["Western initiatives ... a fund", "Garlic cures"], ["wests support for ukraine fosters russophobia", ""])
    tekst = v["messages"][0]["content"][0]["text"]
    assert "1. [headline: wests support for ukraine fosters russophobia] Western initiatives" in tekst and "2. Garlic cures" in tekst
    assert "Keep the polarity of the claim" in v["system"] and "a yes to your question must mean the claim is true" in v["system"]
