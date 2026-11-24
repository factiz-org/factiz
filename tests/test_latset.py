"""De sets voor de lat van B68 per taal (PLAN #32.66, stap 2): eerst het Spaans."""

import json

from doublecheck import latset as ls


def _check(cid, publisher, datum, oordeel="onwaar", tekst=None):
    return {"claim_id": cid, "publisher": publisher, "datum": datum, "oordeel": oordeel, "url": f"https://x/{cid}",
            "tekst": tekst or f"Una bewering die lang genoeg is om mee te tellen, nummer {cid}"}


def test_fresh_fakes_come_only_from_the_spanish_fact_checkers_in_the_window_with_a_cap_per_newsroom():
    rijen = ([_check(f"m{i}", "Maldita", "2026-10-15") for i in range(10)]
             + [_check(f"n{i}", "Newtral", "2026-11-02") for i in range(10)]
             + [_check("oud", "Maldita", "2026-09-30"), _check("laat", "Newtral", "2026-11-11"),
                _check("ander", "Fast Check CL", "2026-10-20"), _check("waar", "EFE Verifica", "2026-10-20", "waar")])
    o = ls.kies_o(rijen, n=8, max_per=4, zaad=1)
    assert len(o) == 8 and {r["publisher"] for r in o} == {"Maldita", "Newtral"}
    assert sum(r["publisher"] == "Maldita" for r in o) == 4
    assert not {r["claim_id"] for r in o} & {"oud", "laat", "ander", "waar"}
    assert all(r["id"].startswith("O:") and r["set"] == "O" for r in o)
    assert ls.kies_o(rijen, n=8, max_per=4, zaad=1) == o


def test_a_correction_is_a_title_that_starts_with_no_and_every_conclusion_found_goes_in_without_its_own_article():
    titels = [{"site": "Maldita", "adres": f"https://maldita.es/{i}", "datum": "2019-05-01", "oordeel": "Bulo",
               "bewering": f"[T] No, Pablo Iglesias no ha tuiteado eso, versión {i}"} for i in range(6)]
    titels += [{"site": "Maldita", "adres": "https://maldita.es/x", "datum": "2019-05-01", "oordeel": "Bulo",
                "bewering": "[T] Bulos y desinformaciones sobre el incendio de Notre Dame"}]
    conclusies = [{"site": "Newtral", "adres": "https://www.newtral.es/b/", "datum": "2024-01-01",
                   "bewering": "El Banco de España no ha recomendado tener dinero en efectivo en casa"}]
    c = ls.correcties(titels, conclusies, n=4, zaad=2)
    teksten = [r["tekst"] for r in c]
    assert len(c) == 4 and "El Banco de España no ha recomendado tener dinero en efectivo en casa" in teksten
    assert all(not t.startswith("[T]") for t in teksten) and not any("Notre Dame" in t for t in teksten)
    # de eigen check van een correctie is geen bewijs: een rood dat het artikel noemt, blijft een vals alarm
    assert all("eigen_urls" not in r and r["artikel"].startswith("https://") for r in c)
    assert all(r["set"] == "C" and r["id"].startswith("C:") for r in c)


def test_an_old_viral_image_needs_a_negative_check_takes_one_image_per_article_and_gets_a_wayback_copy():
    rollen = [{"artikel": "https://maldita.es/malditobulo/20200301/a/", "beelden": ["https://maldita.es/i/a.jpg",
               "https://maldita.es/i/a2.jpg"], "rollen": ["viraal", "bewijs"]},
              {"artikel": "https://maldita.es/malditobulo/20200302/twee/", "beelden": ["https://m/1.jpg", "https://m/2.jpg"],
               "rollen": ["viraal", "viraal"]},
              {"artikel": "https://www.newtral.es/b/20190505/", "beelden": ["https://n/b.jpg"], "rollen": ["viraal"]},
              {"artikel": "https://www.newtral.es/zonder-check/20190505/", "beelden": ["https://n/c.jpg"],
               "rollen": ["viraal"]}]
    negatief = {"maldita.es/malditobulo/20200301/a": {"tekst": "Esta foto muestra a", "datum": "2020-03-01",
                                                       "redactie": "Maldita"},
                "maldita.es/malditobulo/20200302/twee": {"tekst": "Dos fotos", "datum": "2020-03-02",
                                                          "redactie": "Maldita"},
                "newtral.es/b/20190505": {"tekst": "Esta imagen muestra b", "datum": "2019-05-05",
                                          "redactie": "Newtral"}}
    b = ls.virale_oud(rollen, negatief, per_redactie=5, zaad=3)
    assert sorted((r["redactie"], r["beeld"]) for r in b) == [
        ("Maldita", "https://m/1.jpg"), ("Maldita", "https://maldita.es/i/a.jpg"), ("Newtral", "https://n/b.jpg")]
    m = next(r for r in b if r["redactie"] == "Maldita")
    assert m["beeld_reserve"] == "https://web.archive.org/web/2020id_/https://maldita.es/i/a.jpg"
    assert m["eigen_urls"] == ["https://maldita.es/malditobulo/20200301/a/"] and m["deel"] == "oud"
    assert m["bewering"] == "Esta foto muestra a" and m["set"] == "B"


def test_the_forward_question_shows_the_image_names_the_claim_and_asks_for_a_stamp_and_a_message_in_spanish():
    from doublecheck.modellen import MODELLEN

    k = {"id": "B:1", "bewering": "Esta foto muestra a Pedro Sánchez en Marruecos", "redactie": "Maldita"}
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
           b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")
    v = ls.doorstuurverzoek(k, png)
    assert v["custom_id"] == "ds-1" and v["params"]["model"] == MODELLEN["haiku"]["id"]
    inhoud = v["params"]["messages"][0]["content"]
    assert inhoud[0]["type"] == "image" and "Pedro Sánchez en Marruecos" in inhoud[1]["text"]
    assert "Spanish" in inhoud[1]["text"] and "stamp" in inhoud[1]["text"]
    schema = v["params"]["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"waarom", "stempel", "tekst"}


def test_a_forward_answer_without_a_clear_no_to_the_stamp_never_counts_as_clean():
    assert ls.lees_doorsturen(json.dumps({"waarom": "", "stempel": False, "tekst": "  Mirad esto  "})) == {
        "stempel": False, "tekst": "Mirad esto"}
    assert ls.lees_doorsturen(json.dumps({"stempel": "no", "tekst": "x"}))["stempel"] is None
    assert ls.lees_doorsturen("kapot") == {"stempel": None, "tekst": ""}


def test_the_image_set_takes_per_part_only_clean_images_with_a_message_i_read_as_the_claim():
    kand = [{"id": f"B:{d}{i}", "set": "B", "deel": d, "bewering": f"claim {d}{i}", "beeld": f"https://b/{d}{i}"}
            for d in ("oud", "nieuw") for i in range(4)]
    antw = {"B:oud0": {"stempel": True, "tekst": "a"}, "B:oud1": {"stempel": False, "tekst": "b"},
            "B:oud2": {"stempel": False, "tekst": ""}, "B:oud3": {"stempel": False, "tekst": "d"},
            "B:nieuw0": {"stempel": False, "tekst": "e"}, "B:nieuw1": {"stempel": None, "tekst": "f"},
            "B:nieuw2": {"stempel": False, "tekst": "g"}, "B:nieuw3": {"stempel": False, "tekst": "h"}}
    labels = {"B:oud1": "goed", "B:oud3": "goed", "B:nieuw0": "anders", "B:nieuw2": "goed", "B:nieuw3": "goed"}
    b = ls.b_set(kand, antw, labels, per_deel=2)
    assert [(r["id"], r["tekst"], r["bewering"]) for r in b] == [
        ("B:oud1", "b", "claim oud1"), ("B:oud3", "d", "claim oud3"),
        ("B:nieuw2", "g", "claim nieuw2"), ("B:nieuw3", "h", "claim nieuw3")]


def test_the_spanish_headlines_come_from_nine_media_without_the_dead_feed_of_rtve():
    assert len(ls.FEEDS["es"]) == 9 and "RTVE" not in ls.FEEDS["es"]
    assert {"El País", "ABC", "elDiario.es", "El Confidencial"} <= set(ls.FEEDS["es"])


def test_headlines_are_taken_in_turn_per_medium_so_none_falls_short_when_cut():
    rijen = [{"merk": m, "id": f"{m}{i}"} for m, k in (("A", 5), ("B", 2), ("C", 5)) for i in range(k)]
    assert [r["id"] for r in ls.om_de_beurt(rijen, 8)] == ["A0", "B0", "C0", "A1", "B1", "C1", "A2", "C2"]


def test_the_year_of_the_archive_copy_comes_from_the_check_or_else_from_the_article_address():
    assert ls.jaar_van("2019-05-05", "https://x/") == "2019"
    assert ls.jaar_van("", "https://maldita.es/malditobulo/20200301/a/") == "2020"
    assert ls.jaar_van("", "https://www.newtral.es/b/20191107/") == "2019"
    assert ls.jaar_van("", "https://maldita.es/x/", "2026") == "2026"


def test_the_image_someone_would_forward_is_a_viral_one_that_is_not_the_share_image_and_has_no_stamp_word():
    beelden = ["https://m/portada.jpg", "https://m/BULO-32.jpg", "https://m/deel.jpg", "https://m/captura.png",
               "https://m/later.png"]
    rollen = ["viraal", "viraal", "viraal", "viraal", "viraal"]
    assert ls.kies_viraal(beelden, rollen, frozenset({"https://m/deel.jpg"})) == "https://m/captura.png"
    assert ls.kies_viraal(["https://m/a.jpg"], ["bewijs"]) is None
    assert ls.kies_viraal(["https://n/FAKE-ROCIO.jpg", "https://n/Fake-GC.jpg"], ["viraal", "viraal"]) is None
