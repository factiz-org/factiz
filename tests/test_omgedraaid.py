"""De conclusie in het veld van de bewering (#32.66): Haiku leest, ik lees na, en wat gelezen omgedraaid is gaat weg."""

import json

import pytest

from doublecheck import omgedraaid as om
from doublecheck import terugaanvoer as ta


def _c(site="Newtral", bewering="El Banco de España no ha recomendado tener dinero en efectivo en casa",
       oordeel="Falso", adres="https://www.newtral.es/a/"):
    return {"site": site, "adres": adres, "taal": "es", "datum": "2024-01-01", "bewering": bewering, "oordeel": oordeel}


def test_only_negative_checks_of_the_three_spanish_sites_go_to_the_reader():
    assert om.in_set(_c(), "onwaar") and om.in_set(_c(site="Maldita"), "misleidend")
    assert om.in_set(_c(site="EFE Verifica"), "deels-waar")
    # een conclusie bij *waar* zegt hetzelfde als de bewering, en *onbewezen* wordt nooit rood
    assert not om.in_set(_c(), "waar") and not om.in_set(_c(), "onbewezen") and not om.in_set(_c(), None)
    assert not om.in_set(_c(site="Snopes"), "onwaar")


def test_the_question_names_the_site_the_rating_and_the_text_and_asks_haiku_for_one_of_three():
    from doublecheck.modellen import MODELLEN

    v = om.verzoek(_c())
    assert v["custom_id"] == f"om-{ta.check_id(_c())}"
    p = v["params"]
    assert p["model"] == MODELLEN["haiku"]["id"]
    inhoud = p["messages"][0]["content"]
    assert "Newtral" in inhoud and "Falso" in inhoud and "El Banco de España no ha recomendado" in inhoud
    # een ontkenning alleen is geen conclusie: de vraag zegt het met een voorbeeld
    assert "not a virus" in inhoud
    schema = p["output_config"]["format"]["schema"]
    assert schema["properties"]["soort"]["enum"] == ["bewering", "conclusie", "twijfel"]


def test_an_unreadable_or_unknown_answer_is_doubt_never_a_claim():
    assert om.lees_soort('{"waarom": "x", "soort": "conclusie"}') == "conclusie"
    assert om.lees_soort('{"waarom": "x", "soort": "bewering"}') == "bewering"
    assert om.lees_soort('{"soort": "misschien"}') == "twijfel"
    assert om.lees_soort("geen json") == "twijfel"


def test_what_is_read_as_conclusion_or_doubt_leaves_and_a_claim_stays():
    labels = {"a": "conclusie", "b": "twijfel", "c": "bewering"}
    assert om.weg(labels) == {"a", "b"}


def test_a_check_read_as_conclusion_never_comes_back_in_an_import():
    checks = [_c(), _c(bewering="El COVID19 no es un virus, es un exosoma", adres="https://www.newtral.es/b/")]
    claims, weg = ta.naar_import(checks, weg_ids={ta.check_id(checks[0])})
    assert [c.text for c in claims] == ["El COVID19 no es un virus, es un exosoma"]
    assert weg == {"de conclusie als bewering, gelezen": 1}


def test_the_count_refuses_while_a_flagged_check_has_no_label_and_measures_the_misses_on_the_development_set():
    antwoorden = {"a": "conclusie", "b": "bewering", "c": "twijfel", "d": "bewering", "e": "conclusie"}
    with pytest.raises(om.Weigering):
        om.telling(antwoorden, {"a": "conclusie"}, ontwikkel=["a", "b", "d"])
    labels = {"a": "conclusie", "b": "conclusie", "c": "bewering", "d": "bewering", "e": "twijfel"}
    t = om.telling(antwoorden, labels, ontwikkel=["a", "b", "d"])
    assert t["gelezen"] == 5 and t["door haiku gemarkeerd"] == 3
    assert t["gemarkeerd en weg"] == 2 and t["gemarkeerd maar een bewering"] == 1
    # op de ontwikkelset: van de twee omgedraaide vond Haiku er één
    assert t["ontwikkel"] == {"n": 3, "omgedraaid": 2, "gevonden": 1, "gemist": ["b"]}


def test_a_removal_writes_its_report_first_and_uses_the_rule_of_this_round(tmp_path):
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('k1', 'x', 'es')")
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url, review_date,"
                 " language, source) VALUES ('k1', 'Newtral', 'onwaar', 'Falso', 'https://n/a', '2024', 'es', ?)",
                 (ta.BRON,))
    rijen = [{"claim_id": "k1", "url": "https://n/a", "tekst": "x", "label": "conclusie"}]
    assert ta.haal_dubbele_weg(conn, rijen, tmp_path / "w.json", regel=om.REGEL) == {"checks": 1, "beweringen": 1}
    assert json.loads((tmp_path / "w.json").read_text(encoding="utf-8"))["regel"] == om.REGEL


def test_two_versions_read_together_flag_a_check_when_either_flags_it_and_only_what_both_read_counts():
    v1 = {"a": "conclusie", "b": "bewering", "c": "bewering", "d": "twijfel"}
    v2 = {"a": "bewering", "b": "twijfel", "c": "bewering", "d": "conclusie"}
    assert om.samen(v1, v2) == {"a": "conclusie", "b": "twijfel", "c": "bewering", "d": "conclusie"}
    assert om.samen(v1, {"a": "bewering"}) == {"a": "conclusie"}


# --- De hele publicatiedatabase (2026-11-12, `--ronde publicatie`) ---

def test_a_negation_counts_as_a_form_in_the_language_of_the_claim_at_the_start_or_where_the_verb_ends():
    assert om.vorm("No se descartaron votos en Arizona porque las boletas se llenaron con marcadores Sharpie",
                   "es") == "begin"
    assert om.vorm("Es falso que el director de la OMS pidió no vacunar a los niños", "es") == "begin"
    assert om.vorm("“Nobody is asking for ventilators.”", "en") == "begin"
    assert om.vorm("Não é verdade que o TSE conta os votos", "pt-BR") == "begin"
    assert om.vorm("Kein anderes Land hilft Deutschland beim Hochwasser", "de") == "begin"
    # Hindi en Sinhala zetten de ontkenning achteraan, bij het werkwoord
    assert om.vorm("ANI की ट्वीट की गई मजदूरों की तस्वीरें उत्तरप्रदेश की नहीं हैं", "hi") == "eind"
    assert om.vorm("කතෝලික පූජකයෙකු කාන්තාවන් සමඟ නර්තනයේ යෙදෙන දර්ශනයක් නොවේ! ", "si") == "eind"
    # een ontkenning midden in de zin is geen vorm; een woord dat met dezelfde letters begint ook niet
    assert om.vorm("El COVID19 no es un virus, es un exosoma", "es") is None
    assert om.vorm("Noticias falsas sobre el Papa", "es") is None and om.vorm("Nothingness is a book", "en") is None
    assert om.vorm("Nicht ein Virus", "xx") is None


def test_the_preliminary_count_is_per_newsroom_over_negative_checks_only():
    rijen = [{"redactie": "El Detector", "oordeel": "onwaar", "tekst": "No se descartaron votos", "taal": "es"},
             {"redactie": "El Detector", "oordeel": "misleidend", "tekst": "Una foto de 2015", "taal": "es"},
             {"redactie": "El Detector", "oordeel": "waar", "tekst": "No hubo fraude", "taal": "es"},
             {"redactie": "The Quint", "oordeel": "onwaar", "tekst": "तस्वीरें उत्तरप्रदेश की नहीं हैं", "taal": "hi"}]
    t = om.voormeting(rijen)
    assert t["El Detector"] == {"negatief": 2, "met vorm": 1, "begin": 1, "eind": 0, "talen": {"es": 2}}
    assert t["The Quint"]["eind"] == 1 and t["The Quint"]["met vorm"] == 1


def test_euvsdisinfo_and_a_positive_or_unknown_rating_never_go_to_the_reader_of_the_publication():
    assert om.voor_lezer({"oordeel": "onwaar", "bron": "datacommons-ccby"})
    assert om.voor_lezer({"oordeel": "deels-waar", "bron": "datacommons-ccby"})
    assert not om.voor_lezer({"oordeel": "onwaar", "bron": "euvsdisinfo"})
    assert not om.voor_lezer({"oordeel": "waar", "bron": "datacommons-ccby"})
    assert not om.voor_lezer({"oordeel": "onbewezen", "bron": "datacommons-ccby"})


def test_the_key_of_a_check_survives_a_new_import_and_is_what_the_reader_answers_on():
    from doublecheck.ingest import check_sleutel

    url = "https://www.univision.com/x"
    a = check_sleutel(url, "No se descartaron votos en Arizona")
    # zoals het nummer van een bewering: hoofdletters en witruimte tellen niet, het adres wel
    assert a == check_sleutel(url, "  no se descartaron  votos en ARIZONA ") and len(a) == 16
    assert a != check_sleutel(url + "y", "No se descartaron votos en Arizona")
    c = dict(_c(site="El Detector / Univision Noticias", adres=url, bewering="No se descartaron votos en Arizona"), id=a)
    assert om.verzoek(c)["custom_id"] == f"om-{a}"
    # route A houdt zijn eigen sleutel
    assert om.verzoek(_c())["custom_id"] == f"om-{ta.check_id(_c())}"


def test_round_two_takes_whole_newsrooms_with_a_read_conclusion_most_first_and_skips_what_does_not_fit():
    labels = {"a": "conclusie", "b": "conclusie", "c": "conclusie", "d": "twijfel", "e": "bewering"}
    redactie = {"a": "Newtral", "b": "Newtral", "c": "The Quint", "d": "Vishvas News", "e": "PolitiFact"}
    kosten = {"Newtral": 0.40, "The Quint": 2.00, "Vishvas News": 0.10, "PolitiFact": 0.10}
    # alleen een gelezen conclusie telt, niet twijfel en niet een bewering; The Quint past niet meer
    assert om.tweede_ronde(labels, redactie, kosten, ruimte=1.00) == (["Newtral"], ["The Quint"])
    assert om.tweede_ronde(labels, redactie, kosten, ruimte=3.00) == (["Newtral", "The Quint"], [])


def test_round_three_takes_the_newsrooms_with_a_read_conclusion_that_round_two_did_not_read_whole():
    labels = {"a": "conclusie", "b": "conclusie", "c": "conclusie", "d": "conclusie", "e": "twijfel"}
    redactie = {"a": "Newtral", "b": "Newtral", "c": "PolitiFact", "d": "FACTLY", "e": "The Quint"}
    kosten = {"PolitiFact": 1.00, "FACTLY": 2.00, "The Quint": 0.10}
    # Newtral las ronde 2 heel; twijfel alleen haalt The Quint er niet bij; wat niet past, wordt genoemd
    assert om.derde_ronde(labels, redactie, {"Newtral"}, kosten, ruimte=5.00) == (["FACTLY", "PolitiFact"], [])
    assert om.derde_ronde(labels, redactie, {"Newtral"}, kosten, ruimte=1.50) == (["PolitiFact"], ["FACTLY"])


def test_a_later_removal_on_the_same_day_gets_its_own_report_and_the_first_stays(tmp_path):
    assert om.rapportpad(tmp_path, "2026-11-12") == tmp_path / "weg-2026-11-12.json"
    (tmp_path / "weg-2026-11-12.json").write_text("{}", encoding="utf-8")
    assert om.rapportpad(tmp_path, "2026-11-12") == tmp_path / "weg-2026-11-12-2.json"
    (tmp_path / "weg-2026-11-12-2.json").write_text("{}", encoding="utf-8")
    assert om.rapportpad(tmp_path, "2026-11-12") == tmp_path / "weg-2026-11-12-3.json"


def test_a_check_read_as_conclusion_is_refused_by_every_import_and_the_rest_of_the_claim_stays():
    from doublecheck.factchecktools import RawClaim, RawFactcheck
    from doublecheck.feed import HERDISTRIBUEERBAAR
    from doublecheck.ingest import check_sleutel, import_claims
    from doublecheck.storage import connect, init_schema

    def fc(url, uitgever="El Detector / Univision Noticias"):
        return RawFactcheck(publisher=uitgever, publisher_site=None, url=url, review_date="2020-11-05",
                            verdict_original="Falso", language="es")

    conn = connect(":memory:")
    init_schema(conn)
    tekst = "No se descartaron votos en Arizona porque las boletas se llenaron con marcadores Sharpie"
    url = "https://www.univision.com/noticias/es-falso-el-sharpiegate"
    weg = frozenset({check_sleutel(url, tekst)})
    r = import_claims(conn, [RawClaim(text=tekst, claimant=None, claim_date=None, factchecks=(fc(url),))],
                      source=HERDISTRIBUEERBAAR, uitgesteld=True, weg=weg)
    assert r.accepted_claims == 0 and r.accepted_factchecks == 0
    assert "conclusie_als_bewering" in {w.reason for w in r.refusals}
    # dezelfde tekst onder een ander adres is een andere check en komt wel binnen
    r = import_claims(conn, [RawClaim(text=tekst, claimant=None, claim_date=None, factchecks=(
        fc(url), fc("https://www.politifact.com/x", "PolitiFact")))], source=HERDISTRIBUEERBAAR, uitgesteld=True,
        weg=weg)
    assert r.accepted_factchecks == 1
    assert [u for (u,) in conn.execute("SELECT url FROM factcheck")] == ["https://www.politifact.com/x"]


def test_without_an_explicit_list_the_import_reads_the_committed_list_of_removed_checks():
    from doublecheck.ingest import weggehaalde_checks

    lijst = weggehaalde_checks()
    assert isinstance(lijst, frozenset) and all(len(i) == 16 for i in lijst)


def test_the_committed_list_is_what_was_read_as_conclusion_or_doubt_except_what_waits_on_the_test_set():
    from doublecheck.ingest import weggehaalde_checks

    d = json.loads(om.RONDES["publicatie"]["labels"].read_text(encoding="utf-8"))
    wacht = set(d["sets"].get(om.WACHT, []))
    assert wacht <= om.weg(d["labels"])
    assert weggehaalde_checks() == frozenset(om.weg(d["labels"]) - wacht)


def test_a_claim_in_the_test_set_of_the_benchmark_is_held_back_and_named_never_removed_silently():
    rijen = [{"id": "a", "claim_id": "k1"}, {"id": "b", "claim_id": "k2"}, {"id": "c", "claim_id": "k1"}]
    weg, wacht = om.zonder_testset(rijen, {"k1"})
    assert [r["id"] for r in weg] == ["b"] and [r["id"] for r in wacht] == ["a", "c"]


def test_a_dossier_loses_exactly_the_factchecks_whose_page_disappeared():
    doc = {"toelichting": "t", "factchecks": [{"nummer": "a"}, {"nummer": "b", "versie": "v"}, {"nummer": "c"}]}
    nieuw, weg = om.uit_dossier(doc, {"b", "x"})
    assert [f["nummer"] for f in nieuw["factchecks"]] == ["a", "c"] and weg == [{"nummer": "b", "versie": "v"}]
    assert doc["factchecks"][1]["nummer"] == "b", "het origineel blijft onaangeroerd"
    assert om.uit_dossier(doc, set()) == (doc, [])
