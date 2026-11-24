"""Schaallegenda per uitgever (PLAN #25.3b) en de oordeelwoorden van de
negen nieuwe talen (#25.18).

Een label als "Three Pinocchios", "Nì" of "شاخ‌دار" betekent pas iets naast
de methode van de redactie die het gebruikt. De algemene tabel laat zulke
labels bewust `onbekend` (twijfel versoepelt nooit); een legenda per host,
met de bron erbij, mag ze indelen. Op een andere host, of zonder host,
blijft het `onbekend`.
"""

import pytest

from doublecheck.verdicts import SCHAALLEGENDA, VERTAALDE_LABELS, normalize_verdict


@pytest.mark.parametrize("host, label, verwacht", [
    ("washingtonpost.com", "Three Pinocchios", "deels-waar"),
    ("washingtonpost.com", "Two Pinocchios", "deels-waar"),
    ("pagellapolitica.it", "C'eri quasi", "deels-waar"),
    ("pagellapolitica.it", "Nì", "deels-waar"),
    ("pagellapolitica.it", "Pinocchio andante", "deels-waar"),
    ("pagellapolitica.it", "Panzana Pazzesca", "onwaar"),
    ("lupa.uol.com.br", "Exagerado", "deels-waar"),
    ("lupa.uol.com.br", "Subestimado", "deels-waar"),
    ("factnameh.com", "شاخ‌دار", "onwaar"),
    ("factnameh.com", "شاخ دار", "onwaar"),          # spatie in plaats van halve spatie
])
def test_a_scale_label_is_read_with_the_publishers_own_legend(host, label, verwacht):
    assert normalize_verdict(label, host=host) == verwacht


@pytest.mark.parametrize("label", ["Three Pinocchios", "Nì", "Exagerado", "شاخ‌دار"])
def test_without_the_publishers_host_a_scale_label_stays_unknown(label):
    assert normalize_verdict(label) == "onbekend"
    assert normalize_verdict(label, host="voorbeeld-redactie.org") == "onbekend"


def test_a_label_outside_the_legend_falls_back_to_the_general_table():
    assert normalize_verdict("Falso", host="pagellapolitica.it") == "onwaar"
    assert normalize_verdict("Four Pinocchios", host="washingtonpost.com") == "onwaar"
    # Wat geen bron draagt, blijft onbekend: één Pinokkio en de omgekeerde.
    assert normalize_verdict("One Pinocchio", host="washingtonpost.com") == "onbekend"


def test_every_legend_names_its_source_and_glosses_every_label():
    for host, legenda in SCHAALLEGENDA.items():
        assert legenda["bron"].startswith("https://"), host
        for label, (categorie, glos) in legenda["labels"].items():
            assert categorie in ("waar", "deels-waar", "misleidend", "onwaar", "onbewezen", "satire"), label
            assert glos.strip(), label


@pytest.mark.parametrize("host, label, verwacht", [
    ("tamil.factcrescendo.com", "Fact Crescendo Rating: Mixture", "deels-waar"),
    ("tamil.factcrescendo.com", "ஃபேக்ட் கிரஸண்டோ ரேட்டிங்: ALTERED", "onwaar"),
    ("tamil.factcrescendo.com", "ஃபேக்ட் கிரஸண்டோ ரேட்டிங்: MISSING CONTEXT", "misleidend"),
    ("factcrescendo.com", "Fact Crescendo Rating : FALSE", "onwaar"),
    ("malayalam.factcrescendo.com", "Fact Crescendo Rating: Mixture", "deels-waar"),
])
def test_fact_crescendos_fixed_rating_prefix_is_read_on_its_own_hosts(host, label, verwacht):
    assert normalize_verdict(label, host=host) == verwacht


def test_the_fact_crescendo_prefix_means_nothing_on_another_host():
    assert normalize_verdict("Fact Crescendo Rating: Mixture", host="voorbeeld-redactie.org") == "onbekend"


@pytest.mark.parametrize("label, verwacht", [
    ("ತಪ್ಪು", "onwaar"), ("ತಪ್ಪು ", "onwaar"), ("ಫೇಕ್", "onwaar"),
    ("ಸಂದರ್ಭದಿಂದ ಹೊರಗಿಡಲಾಗಿದೆ", "misleidend"),
    ("মিথ্যা", "onwaar"), ("বিভ্রান্তিকর", "misleidend"), ("ভুয়া", "onwaar"),
    ("বিভ্ৰান্তিকৰ", "misleidend"), ("ভুৱা", "onwaar"), ("মিছা।", "onwaar"),
    ("আংশিকভাৱে মিছা", "deels-waar"), ("প্ৰসংগ সংগতিহীন", "misleidend"),
    ("फ़ेक", "onwaar"), ("फर्जी", "onwaar"),
])
def test_plain_verdict_words_of_the_new_languages_are_recognised(label, verwacht):
    """Bij #25.18 kwamen negen talen binnen zonder hun oordeelwoorden."""
    assert normalize_verdict(label) == verwacht


@pytest.mark.parametrize("label", ["সম্পাদিত", "Explainer", "Insight", "Mix", "Sarcasm"])
def test_labels_that_are_no_verdict_or_need_a_legend_stay_unknown(label):
    """"Bewerkt" is in het Engels ook `onbekend`; een uitleg is geen oordeel;
    "Mix" en "Sarcasm" van YouTurn hebben nog geen legenda (#25.24)."""
    assert normalize_verdict(label) == "onbekend"


def test_persian_half_space_and_space_variants_are_one_label():
    """Perzisch schrijft dezelfde woorden met een halve spatie, een spatie
    of aaneen; bij Factnameh bleven zo 25 checks `onbekend`."""
    for variant in ("غیرقابل اثبات", "غیر‌قابل اثبات", "غیرقابل‌اثبات", "غیر قابل اثبات"):
        assert normalize_verdict(variant) == "onbewezen", variant
    assert normalize_verdict("گمراه کننده") == "misleidend"


def test_the_new_words_carry_language_and_gloss():
    for label in ("ತಪ್ಪು", "মিথ্যা", "বিভ্ৰান্তিকৰ", "फ़ेक"):
        categorie, taal, glos = VERTAALDE_LABELS[label]
        assert taal and glos


def test_the_import_reads_a_scale_label_with_the_legend_of_its_host():
    from doublecheck.factchecktools import RawClaim, RawFactcheck
    from doublecheck.ingest import import_claims
    from doublecheck.storage import connect, init_schema
    from tests.test_ingest import NEP

    conn = connect(":memory:")
    init_schema(conn)
    claim = RawClaim(text="Il debito pubblico è sceso di cento miliardi in un anno", claimant=None, claim_date=None,
                     factchecks=(RawFactcheck(publisher="Pagella Politica", publisher_site="pagellapolitica.it",
                                              url="https://pagellapolitica.it/dichiarazioni/1", review_date="2021-01-01",
                                              verdict_original="Pinocchio andante", language="it"),))
    import_claims(conn, [claim], source="test", fingerprinter=NEP)
    assert conn.execute("SELECT verdict_normalized FROM factcheck").fetchone()[0] == "deels-waar"


# --- de legenda's van de proef van route A (#32.19, BENCHMARK §190) -----------------------------------

@pytest.mark.parametrize("host, label, verwacht", [
    ("snopes.com", "Correct Attribution", "waar"),
    ("snopes.com", "Incorrect Attribution", "onwaar"),
    ("snopes.com", "Miscaptioned", "misleidend"),
    ("snopes.com", "Legit", "waar"),
    ("maldita.es", "Alerta", "onbewezen"),
    ("aosfatos.org", "não_é_bem_assim", "misleidend"),
    ("aosfatos.org", "Não é bem assim", "misleidend"),
])
def test_the_scales_of_snopes_maldita_and_aos_fatos_are_read_with_their_own_legend(host, label, verwacht):
    assert normalize_verdict(label, host=host) == verwacht


def test_maldita_context_stays_unknown_because_its_definition_needs_weighing():
    assert normalize_verdict("Contexto", host="maldita.es") == "onbekend"


@pytest.mark.parametrize("label", ["Bulo", "bulo", "Timo"])
def test_a_maldita_bulo_is_false_because_its_own_methodology_says_so(label):
    # #32.66: "Calificamos como Falso o Bulo aquellos contenidos que podemos verificar de forma independiente que son
    # falsos" (maldita.es/metodologia-maldita, versie van 27 mei 2026); de kop van die soort is "Falso/ Bulo/ Timo".
    assert normalize_verdict(label, host="maldita.es") == "onwaar"


def test_a_bulo_elsewhere_stays_unknown_because_only_maldita_defined_it():
    assert normalize_verdict("Bulo") == "onbekend"


def test_maldita_context_never_goes_to_a_language_model_because_maldita_calls_it_a_debate():
    from doublecheck.verdicts import geen_oordeel

    assert geen_oordeel("Contexto", "maldita.es")
    assert not geen_oordeel("Bulo", "maldita.es")


@pytest.mark.parametrize("label, verwacht", [
    ("False. The video is AI-generated.", "onwaar"),
    ("Mixed. The coalition raised excise by 215 per cent", "deels-waar"),
    ("Misleading. Many of the nurses were recruited under the previous government.", "misleidend"),
    ("Mostly False. The figure is inflated.", "deels-waar"),
    ("False", "onwaar"),
])
def test_aaps_verdict_word_leads_its_verdict_sentence(label, verwacht):
    assert normalize_verdict(label, host="aap.com.au") == verwacht


def test_the_leading_verdict_word_counts_only_on_aap_and_only_from_its_scale():
    # #25.3: geen algemene kopregel, dus elders blijft een zin onbekend
    assert normalize_verdict("False. The video is AI-generated.") == "onbekend"
    assert normalize_verdict("False. The video is AI-generated.", host="voorbeeld-redactie.org") == "onbekend"
    # op AAP alleen een woord van de eigen schaal, geen willekeurige kop
    assert normalize_verdict("Fake news. The quote is fabricated.", host="aap.com.au") == "onbekend"
    assert normalize_verdict("The claim is wrong. Labour made no such commitment.", host="aap.com.au") == "onbekend"


@pytest.mark.parametrize("label, verwacht", [("Necesita contexto", "misleidend"), ("No hay pruebas", "onbewezen"),
                                             ("No hay pruebas.", "onbewezen")])
def test_two_spanish_verdicts_are_literal_translations_of_the_general_table(label, verwacht):
    assert normalize_verdict(label) == verwacht
    assert VERTAALDE_LABELS[label.strip(".").casefold()][1] == "es"


# --- route A terug in de tijd, stap 3 (PLAN #32.38) -------------------------------------------------------

@pytest.mark.parametrize("label, verwacht", [
    ("Falsa.", "onwaar"), ("Falsa", "onwaar"), ("Es falso.", "onwaar"), ("Es Falso", "onwaar"), ("Es falsa", "onwaar"),
    ("Parcialmente falso.", "deels-waar"), ("Parcialmente falso-", "deels-waar"), ("Parcialmente falsa", "deels-waar"),
    ("Falso en su mayor parte.", "deels-waar"), ("Falsa en su mayor parte", "deels-waar"),
    ("Parcialmente veraz.", "deels-waar"), ("Sin pruebas", "onbewezen"), ("Sin evidencia.", "onbewezen"),
    ("Cierto.", "waar"), ("Descontextualizado.", "misleidend"), ("Falta de Contexto", "misleidend"),
])
def test_efes_verdicts_are_whole_spanish_labels(label, verwacht):
    assert normalize_verdict(label) == verwacht


@pytest.mark.parametrize("label", ["Es falso. Es un montaje.", "Falos.", "Parcfialmente falso", "Es un fotomontaje."])
def test_a_spanish_verdict_sentence_or_a_typo_stays_unknown(label):
    # geen kopregel (#25.3) en geen raden bij een tikfout: die gaan naar het lezen, niet naar de tabel
    assert normalize_verdict(label) == "onbekend"


@pytest.mark.parametrize("label, verwacht", [
    ("Unproven (retired)", "onbewezen"), ("Unfounded", "onbewezen"), ("Unfounded (retired)", "onbewezen"),
    ("Recall", "waar"), ("False (retired)", "onwaar"),
    ("Research In Progress (retired)", "onbekend"), ("Lost Legend (retired)", "onbekend"),
])
def test_snopes_retired_ratings_keep_their_meaning(label, verwacht):
    assert normalize_verdict(label, host="snopes.com") == verwacht


def test_retired_and_snopes_own_labels_mean_nothing_on_another_host():
    assert normalize_verdict("Unproven (retired)") == "onbekend"
    assert normalize_verdict("Recall", host="fullfact.org") == "onbekend"


@pytest.mark.parametrize("label", ["Scam", "Legend", "Outdated", "Lost Legend", "Lost Legend (retired)",
                                   "Research In Progress", "Research in Progress (retired)"])
def test_snopes_says_which_of_its_labels_are_no_verdict_on_the_claim(label):
    from doublecheck.verdicts import geen_oordeel

    assert normalize_verdict(label, host="snopes.com") == "onbekend"
    assert geen_oordeel(label, "snopes.com")


def test_a_real_verdict_or_another_host_is_not_marked_as_no_verdict():
    from doublecheck.verdicts import geen_oordeel

    assert not geen_oordeel("False", "snopes.com")
    assert not geen_oordeel("Scam", "fullfact.org")
    assert not geen_oordeel("AI Generated", "leadstories.com")


# Full Fact (#32.38, stap 3c, PO 2026-11-04): een vaste kopregel op hun eigen host, alleen bij een afwijzende eerste zin

@pytest.mark.parametrize("label, verwacht", [
    ("False. This is not a genuine Currys offer.", "onwaar"),
    ("This is not true. A reference number was created following reports …", "onwaar"),
    ("This isn’t true. The figure is lower.", "onwaar"),
    ("This isn't correct.", "onwaar"),
    ("Incorrect. Pensions are taxed like any other.", "onwaar"),
    ("Inaccurate. The WHO has said processed meat is proven to cause cancer.", "onwaar"),
    ("This is a hoax. There is no such appeal.", "onwaar"),
    ("This is misleading. The overall budget is increasing.", "misleidend"),
    ("This is not true", "onwaar"),
])
def test_full_facts_rejecting_first_sentence_gives_the_verdict(label, verwacht):
    assert normalize_verdict(label, host="fullfact.org") == verwacht


@pytest.mark.parametrize("label", [
    "Correct. The FSB also said its top priority is a transition period.",   # geen goedkeurende kop: vaak volgt een maar
    "True. However, its link to infertility remains uncertain.",
    "Not quite, the population is projected to rise to 72.5 million by 2039.",
    "This isn't quite right. The number fell last year.",
    "This is incorrect for the UK. Maternity pay can be for up to 39 weeks.",  # een langere eerste zin telt niet
    "There is no evidence for this.",
])
def test_full_facts_other_sentences_stay_unknown(label):
    assert normalize_verdict(label, host="fullfact.org") == "onbekend"


def test_full_facts_heads_mean_nothing_on_another_host():
    assert normalize_verdict("This is not true. A reference number was created.", host="aap.com.au") == "onbekend"
    assert normalize_verdict("This is not true. A reference number was created.") == "onbekend"


# --- de Duitstalige redacties zonder schaal: de conclusie vooraan (#32.46, stap 2) ---------------------------------

@pytest.mark.parametrize("host", ["dpa-factchecking.com", "presseportal.de", "apa.at"])
@pytest.mark.parametrize("label, verwacht", [
    ("Falsch. Das Bild ist KI-generiert.", "onwaar"),
    ("Das ist falsch. Die britische Regierung hat nicht behauptet, …", "onwaar"),
    ("Die Behauptung ist falsch. Nach Angaben der CDC sind bisher …", "onwaar"),
    ("Das stimmt nicht. Die technische Vorbereitung erfolgte nicht …", "onwaar"),
    ("Frei erfunden. Das Video ist ein \"Cheap Fake\".", "onwaar"),
    ("Irreführend. Die Zahlen stammen aus dem Jahr 2019.", "misleidend"),
    ("Falscher Kontext. Das Foto entstand 2015 in Syrien.", "misleidend"),
])
def test_a_german_newsrooms_rejecting_first_sentence_gives_the_verdict(host, label, verwacht):
    assert normalize_verdict(label, host=host) == verwacht


@pytest.mark.parametrize("label", [
    "Richtig ist, dass Menschen mit bestimmten Lungen-Erkrankungen …",   # geen goedkeurende of omweg-kop
    "Richtig. Aber die Zahl stammt aus dem Vorjahr.",
    "Falsch ist, dass die Regierung das plant.",                       # een langere eerste zin telt niet
    "Das Video zeigt eine Demonstration in Paris aus dem Jahr 2019.",
    "Nein. Das Gesetz gilt seit 2020.",
])
def test_a_german_newsrooms_other_sentences_stay_unknown(label):
    assert normalize_verdict(label, host="dpa-factchecking.com") == "onbekend"


def test_german_heads_mean_nothing_on_another_host():
    assert normalize_verdict("Falsch. Das Bild ist KI-generiert.", host="example.de") == "onbekend"
    assert normalize_verdict("Falsch. Das Bild ist KI-generiert.") == "onbekend"
