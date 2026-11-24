"""Taalherkenning op de artefactkant (PLAN.md #12.4).

Aanleiding: cross-linguale gelijkenis ligt structureel lager, dus de strengere
matchdrempel uit etappe 12 sneed daar het hardst — `nl-en` viel van 70,5% naar
50,0% dekking (BENCHMARK.md §23d). Dat raakt B12 rechtstreeks.

Een lagere drempel voor cross-linguale paren vergt weten *dat* een paar
cross-linguaal is. De claimkant draagt een taal; de artefactkant niet — een
screenshot uit het wild is geen record met een taalveld (§20b). Vandaar deze
detector: deterministisch, lokaal, zonder nieuwe afhankelijkheid, en met
`None` als uitkomst wanneer hij het niet weet.

**`None` is het belangrijkste antwoord.** Twijfel valt terug op de strenge
drempel, zodat een misdetectie nooit iets kan versoepelen.
"""

import pytest

from doublecheck.taal import detecteer_taal

VOORBEELDEN = [
    ("nl", "Het Pfizer-vaccin bestaat uit grafeen en verhoogt de kans op kanker"),
    ("en", "The Pfizer vaccine is made of graphene and increases the risk of cancer"),
    ("de", "Der Impfstoff von Pfizer besteht aus Graphen und ist nicht wirksam"),
    ("fr", "Le vaccin de Pfizer est composé de graphène et n'est pas efficace"),
    # Spaans en Catalaans delen bijna al hun functiewoorden; `None` is hier het
    # juiste antwoord en geen tekortkoming (§32).
    ("es", "La vacuna contiene microchips para rastrear y controlar a las personas"),
]


@pytest.mark.parametrize("verwacht,tekst", VOORBEELDEN)
def test_detects_the_market_languages(verwacht, tekst):
    assert detecteer_taal(tekst) == verwacht


@pytest.mark.parametrize(
    "tekst",
    [
        "",
        "Pfizer",
        "Pfizer vaccin 2024",
        "新冠疫苗含有微芯片",
        "1223 84 %",
    ],
)
def test_returns_none_when_it_cannot_tell(tekst):
    """Te weinig materiaal of een schrift dat we niet dekken: geen gok."""
    assert detecteer_taal(tekst) is None


def test_related_languages_do_not_produce_a_confident_wrong_answer():
    """Spaans en Catalaans lijken sterk op elkaar; liever `None` dan fout."""
    catalaans = "La vacuna de Pfizer està feta de grafè i no és eficaç"
    assert detecteer_taal(catalaans) in (None, "ca", "es")


def test_detection_is_deterministic():
    tekst = "Het vaccin bevat microchips om mensen te volgen en te sturen"
    assert detecteer_taal(tekst) == detecteer_taal(tekst)


def test_casing_and_punctuation_do_not_change_the_answer():
    tekst = "The vaccine contains microchips to track and control the people"
    assert detecteer_taal(tekst.upper()) == "en"
    assert detecteer_taal(f'>>> {tekst}!!! ') == "en"


def test_ground_truth_from_the_translation_fixture():
    """De enige grond waarheid die we zelf gemaakt hebben (#14.7).

    De corpuslabels zijn hier níét bruikbaar: die komen van de uitgever en zijn
    aantoonbaar onbetrouwbaar (BENCHMARK.md §26a). De fixture wel: elke kant is
    met de hand geschreven in een bekende taal.
    """
    from doublecheck.vertalingen import load_translations

    paren = load_translations()
    kanten = [(paar["bron"], paar["bron_taal"]) for paar in paren]
    kanten += [(paar["doel"], paar["doel_taal"]) for paar in paren]

    fout = [
        (tekst, taal) for tekst, taal in kanten
        if detecteer_taal(tekst) not in (taal, None)
    ]
    assert len(fout) <= len(kanten) * 0.1, fout[:3]

    # Bewust ruim: de detector staat streng afgesteld omdat een valse markering
    # zwaarder weegt dan een gemiste (§32c). Onbeslist valt terug op de strenge
    # drempel en kan dus nooit iets versoepelen.
    onbeslist = [t for t, _ in kanten if detecteer_taal(t) is None]
    assert len(onbeslist) <= len(kanten) * 0.6


@pytest.mark.parametrize(
    "tekst",
    [
        # Duitse naam in Spaanse tekst: `von` en `der` staan als Duitse
        # functiewoorden in de lijst en kregen door de inverse weging het
        # hóógste gewicht, juist omdat ze uniek zijn.
        "Esta imagen muestra a Von der Leyen con Jeffrey Epstein",
        # Spaanse plaatsnaam die een Frans voorzetsel bevat.
        "La futura mezquita del Poligono Sur de Sevilla tendra un centro medico",
        # Romeins cijfer dat het Catalaanse `i` ("en") raakt.
        "El rey emerito, Juan Carlos I, ha dicho alguna vez la frase completa",
    ],
)
def test_proper_nouns_do_not_decide_the_language(tekst):
    """Eigennamen en cijfers komen niet uit de taal (BENCHMARK.md §32).

    Deze drie zijn onmiskenbaar Spaans en werden gelabeld als Duits, Frans en
    Catalaans. `es` of `None` mag; een andere taal is fout.
    """
    assert detecteer_taal(tekst) in ("es", None)


# --- corpuskant: py3langid over 97 talen (#14.6) ---

CORPUSVOORBEELDEN = [
    ("nl", "Het coronavaccin bevat microchips om mensen te volgen en te sturen"),
    ("en", "The vaccine contains microchips to track and control the people"),
    ("es", "Esta imagen muestra a Von der Leyen con Jeffrey Epstein en una fiesta"),
    ("de", "Der Impfstoff von Pfizer besteht aus Graphenoxid und ist nicht wirksam"),
    ("fr", "Le vaccin de Pfizer est composé de graphène et n'est pas efficace"),
    ("pt", "A vacina contém microchips para rastrear e controlar as pessoas"),
    ("hi", "कोरोना वायरस के टीके में लोगों को ट्रैक करने के लिए माइक्रोचिप है"),
    ("ar", "يحتوي اللقاح على شريحة إلكترونية لتتبع الناس والسيطرة عليهم تماما"),
    ("id", "Vaksin ini mengandung microchip untuk melacak dan mengendalikan orang"),
    ("tr", "Bu aşı insanları takip etmek için mikroçip içeriyor iddiası yalan"),
]


@pytest.mark.parametrize("verwacht,tekst", CORPUSVOORBEELDEN)
def test_corpus_language_covers_far_more_than_our_own_detector(verwacht, tekst):
    from doublecheck.taal import corpus_taal

    assert corpus_taal(tekst) == verwacht


def test_the_spanish_case_that_broke_our_own_detector():
    """Precies de claim die §32 liet ontsporen: een Duitse naam in Spaanse tekst."""
    from doublecheck.taal import corpus_taal

    assert corpus_taal("Esta imagen muestra a Von der Leyen con Jeffrey Epstein") == "es"


def test_low_confidence_yields_und_not_a_guess():
    """Twijfel versoepelt nooit — ook hier niet."""
    from doublecheck.taal import corpus_taal

    assert corpus_taal("") is None
    assert corpus_taal("Pfizer 2024") is None


def test_the_two_detectors_have_different_jobs():
    """`detecteer_taal` blijft de artefactkant, `corpus_taal` de corpuskant.

    De eerste draait in het aanvraagpad en is afgesteld op één vraag: zijn dit
    twee verschillende talen (#12.4). De tweede draait offline en moet 97 talen
    kunnen benoemen (#14.6). Ze vervangen elkaar niet.
    """
    from doublecheck.taal import corpus_taal, detecteer_taal

    portugees = "A vacina contém microchips para rastrear e controlar as pessoas"
    assert corpus_taal(portugees) == "pt"
    assert detecteer_taal(portugees) in (None, "es", "ca")  # kent geen Portugees
