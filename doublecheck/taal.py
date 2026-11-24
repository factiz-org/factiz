"""Taalherkenning op de artefactkant (PLAN.md #12.4).

Waarom dit bestaat: cross-linguale gelijkenis ligt structureel lager dan
gelijkenis binnen één taal, dus één globale matchdrempel kiest altijd verkeerd —
of hij mist vertalingen, of hij laat gelijkende ándere claims door. Een aparte,
lagere drempel voor cross-linguale paren vereist weten *dat* een paar
cross-linguaal is. De claimkant draagt een taal, de artefactkant niet: een
screenshot uit het wild is geen record met een taalveld (BENCHMARK.md §20b).

Bewust geen nieuwe afhankelijkheid. Functiewoordfrequentie is grof, maar het
enige dat hier telt is de vraag "zijn dit twee verschillende talen?", niet welke
taal precies. Gevalideerd op de 44 handgemaakte vertaalparen — de enige grond
waarheid die we zelf gemaakt hebben, want de corpuslabels zijn onbetrouwbaar:
27 van de 57 claims gelabeld `en` zijn in werkelijkheid Nederlands (§26a).

`None` is het belangrijkste antwoord. Twijfel valt terug op de strenge drempel,
zodat een misdetectie nooit iets kan versoepelen — de veilige richting (B5).
"""

from __future__ import annotations

import re

# Functiewoorden per markttaal.
#
# **Een woord hoort in élke taal waar het een functiewoord is.** Ontbreekt het in
# één, dan ontstaat een systematische afwijking naar de andere — en dat is geen
# theorie: `a` stond alleen onder `en`/`fr`, terwijl Spaans het in 32% van de
# claims als voorzetsel gebruikt. Gevolg: 219 correct gelabelde Spaanse claims
# werden als Frans gelezen (BENCHMARK.md §27a). Een gedeeld woord telt voor beide
# talen even zwaar en is dus neutraal; een ontbrekend woord telt eenzijdig.
#
# Verder kort gehouden: langere lijsten slepen inhoudswoorden mee, en die zeggen
# meer over het onderwerp dan over de taal.
_FUNCTIEWOORDEN = {
    "nl": "de het een en van in is dat op te zijn voor met niet aan door om die"
          " als er maar ook naar bij uit over worden wordt heeft hebben zal"
          " was were of al per werden",
    "en": "the a an and of in is that on to be for with not at by from as it this"
          " are was were has have will their there would about",
    "de": "der die das und von in ist dass auf zu sein für mit nicht an durch um"
          " als es auch bei aus über werden wird hat haben wurde"
          " des er will worden dem den ein eine",
    "fr": "le la les un une et de en est que sur pour avec ne pas au par dans ce"
          " il elle des du aux sont été a ont plus se y son on ses",
    "es": "el la los las un una y de en es que sobre para con no por al del se su"
          " lo como este son ha han más a le les sus una",
    "ca": "el la els les un una i de en és que sobre per amb no al del seu com"
          " aquest són ha han més però a es se van als des on dels",
}
_LEXICON = {taal: set(woorden.split()) for taal, woorden in _FUNCTIEWOORDEN.items()}

# Een woord dat in vier lexicons staat onderscheidt niets; een woord dat in één
# staat onderscheidt alles. Zonder deze weging domineren juist de gedeelde
# woorden: `de`, `la`, `el` en `no` staan in vier Romaanse en Germaanse lijsten
# tegelijk en drukken het verschil tussen Spaans en Catalaans weg (§27b).
_GEWICHT = {}
for _taal, _woorden in _LEXICON.items():
    for _woord in _woorden:
        _GEWICHT[_woord] = _GEWICHT.get(_woord, 0) + 1
_GEWICHT = {_woord: 1.0 / _aantal for _woord, _aantal in _GEWICHT.items()}

# Onder deze grenzen is het antwoord `None`. Streng afgesteld, en dat is een
# gemeten keuze (BENCHMARK.md §26c): ééntalige paren zijn ~34 keer talrijker dan
# cross-linguale, dus een valse markering weegt veel zwaarder dan een gemiste.
#
#   (4 woorden, 0,03)  5,1% vals · 91% raak   ->  71 onterecht tegen 40 terecht
#   (8 woorden, 0,10)  1,5% vals · 86% raak   ->  22 onterecht tegen 38 terecht
#
# Acht woorden is bovendien geen willekeurige grens: afgekapte koppen zijn de
# grootste artefactklasse, en juist dáár is functiewoordfrequentie onbetrouwbaar.
# Die vallen nu op `None` en dus op de strenge drempel terug.
_MIN_WOORDEN = 8
# Lager dan vóór de weging: gedeelde woorden tellen nu voor een fractie mee, dus
# dezelfde tekst haalt lagere absolute scores. De verhouding tussen beide grenzen
# is opnieuw gemeten (§27b): 0,8% vals op ééntalige paren bij 86% raak op
# vertalingen, tegen 1,5% / 86% vóór de weging.
_MIN_AANDEEL = 0.04
_MIN_VOORSPRONG = 0.02
# Hoeveel verschíllende functiewoorden de winnaar minstens moet raken. Zonder
# deze eis besliste één toevallig token de taal (§32).
_MIN_TREFFERS = 3

_WOORD = re.compile(r"[^\W\d_]+")


def detecteer_taal(text: str) -> str | None:
    """De markttaal van deze tekst, of `None` wanneer we het niet zeker weten."""
    woorden = _WOORD.findall(text.casefold())
    if len(woorden) < _MIN_WOORDEN:
        return None

    treffers = {
        taal: {woord for woord in woorden if woord in lexicon}
        for taal, lexicon in _LEXICON.items()
    }
    scores = {
        taal: sum(_GEWICHT[woord] for woord in woorden if woord in lexicon)
        / len(woorden)
        for taal, lexicon in _LEXICON.items()
    }
    beste = max(scores, key=scores.get)
    tweede = sorted(scores.values())[-2]
    if scores[beste] < _MIN_AANDEEL or scores[beste] - tweede < _MIN_VOORSPRONG:
        return None

    # Genoeg verschíllende functiewoorden, en de voorsprong mag niet op één
    # token rusten. Eigennamen en cijfers komen niet uit de taal maar krijgen
    # door de inverse weging juist het hoogste gewicht: "Von der Leyen" maakte
    # Spaanse tekst Duits, "Juan Carlos I" maakte hem Catalaans (§32).
    if len(treffers[beste]) < _MIN_TREFFERS:
        return None
    zwaarste = max((_GEWICHT[woord] for woord in treffers[beste]), default=0.0)
    if (scores[beste] - zwaarste / len(woorden)) - tweede < _MIN_VOORSPRONG:
        return None
    return beste


def zijn_verschillende_talen(a: str | None, b: str | None) -> bool:
    """Alleen `True` wanneer béíde talen bekend zijn én verschillen.

    Onbekend telt nooit als "verschillend": dan zou twijfel de drempel
    versoepelen, en dat is precies de verkeerde richting (B5).
    """
    return a is not None and b is not None and a != b


# --- corpuskant ---------------------------------------------------------
#
# Twee detectoren, twee taken. `detecteer_taal` hierboven draait in het
# aanvraagpad en beantwoordt één vraag: zijn dit twee verschillende talen
# (#12.4). `corpus_taal` hieronder draait offline en moet 97 talen kunnen
# benoemen, omdat de CC BY-feed geen taalveld draagt (#14.6, BENCHMARK.md §34).
#
# Waarom hier wél een afhankelijkheid en boven niet: gemeten op ons eigen corpus
# haalt de eigen detector 35% op Spaans en 50% op Frans, py3langid 98–99%. Vier
# eigen aanpakken zijn geprobeerd en afgevallen; de tweede daarvan bedierf 54
# corpuslabels (§32). Meten in plaats van aannemen geldt ook voor onszelf.

# Onder deze zekerheid is het antwoord `None`. Gemeten op de feed: 98% van de
# claims haalt 0,60, en de rest is meestal te kort om iets over te zeggen.
_MIN_ZEKERHEID = 0.60
_identifier = None


def corpus_taal(text: str) -> str | None:
    """De taal van een corpustekst over 97 talen, of `None` bij twijfel."""
    global _identifier
    if not text or not text.strip():
        return None
    if _identifier is None:
        # Import hier: py3langid laadt zijn model bij het eerste gebruik, en het
        # aanvraagpad heeft dit nooit nodig.
        import py3langid

        _identifier = py3langid.langid.LanguageIdentifier.from_pickled_model(
            py3langid.langid.MODEL_FILE, norm_probs=True
        )
    taal, zekerheid = _identifier.classify(text)
    return taal if zekerheid >= _MIN_ZEKERHEID else None
