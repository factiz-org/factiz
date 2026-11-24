"""Relatiecheck-v0: deterministische tegenspraak-detectie (E3.S4, DR8).

Twee signalen, beide zonder model:
- getalconflict: het artefact beweert een getal dat de kandidaatclaim niet
  bevat (en beide kanten bevatten getallen). Een deelverzameling — zoals bij
  een afgekapte kop — is géén conflict;
- negatieflip: precies één van beide kanten bevat een ontkenning.

De functies doen alleen detectie. Wat er met een tegenspraak gebeurt beslist
uitsluitend de categoriseringsfunctie (DR4/DR8): die geeft dan nooit `matched`.
Frans kende in v0 geen negatietokens, met als motivering dat ne/pas mechanisch
te dubbelzinnig zou zijn. Die aanname is gemeten en hield geen stand: van de 44
Franse corpusclaims met los `pas` is er geen enkele het zelfstandig naamwoord
(PLAN.md #11.3, BENCHMARK.md §20).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter

# Een getal mét zijn scheidingstekens als één geheel. Twee vormen:
#   punt/komma  — "30.000", "3,5", "1.234,56"  (NL, DE, EN)
#   spatie      — "40 000", "123 456 789"      (FR, SV)
# De spatievorm is bewust streng: een voorloopgroep van hoogstens drie cijfers
# gevolgd door groepen van exact drie. Zo smelt "40 000" wél samen en
# "In 2020 300 mensen" niet — 2020 heeft vier cijfers (PLAN.md #8.1, #9.1).
_SPATIE_DUIZENDTAL = r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?"
_PUNT_KOMMA = r"\d+(?:[.,]\d+)*"
_GETAL = re.compile(f"{_SPATIE_DUIZENDTAL}|{_PUNT_KOMMA}")
# Eén lijst voor alle talen, bewust. Een artefact uit het wild draagt geen
# taallabel, dus de artefactkant kán geen taalafhankelijk lexicon gebruiken.
# Gevolg: `pas` vlagt ook Nederlandse tekst waar het "zojuist" betekent — 4 van
# 2.583 corpusclaims. Die richting is veilig: overdetectie degradeert `matched`
# → `related` en kost dekking, ónderdetectie zou een ontkend paar laten matchen
# en dat is een G1-fout (B5). Zie BENCHMARK.md §20.
_NEGATIE = re.compile(
    r"\b(niet|geen|nooit|nergens|not|never|cannot|no|nicht|kein|keine|nie"
    r"|pas|ne|ni|rien|jamais|aucun\w*"
    r"|nunca|jamás|ningún|ninguna|ninguno|nada|nadie|tampoco"
    # #25.1b: pt, it, ru, id. `tak` (id) bewust niet: in het Pools en Tsjechisch
    # betekent het "ja"/"zo", en overdetectie kost dekking.
    r"|não|nem|nenhum|nenhuma"
    r"|non|nessun|nessuna|nessuno|niente|nulla"
    r"|не|нет|никогда|ничего|никто"
    r"|tidak|bukan|belum|jangan)\b"
    # Hindi: `\b` werkt niet op Devanagari, want klinkertekens en de anusvara
    # zijn in Python geen woordtekens; `\bनहीं\b` matcht dus nooit (#25.1b).
    r"|(?<![\w\u0900-\u097F])(?:नहीं|नही)(?![\w\u0900-\u097F])"
    # `sin` = "zonder", maar `sin embargo` = "echter" en is géén ontkenning.
    # Gemeten: 5 van de 205 `sin`-claims in het Spaanse corpus (§22b).
    r"|\bsin\b(?!\s+embargo\b)"
    r"|\bn['\u2019]"  # Franse elisie: n'est, n'a — ook met typografische apostrof
    r"|n't\b"
    # #25.20: de Zuid-Aziatische talen. In de Dravidische talen hangt de
    # ontkenning als achtervoegsel aan het werkwoord: dan wordt de
    # onafhankelijke klinker een klinkerteken ("இல்லை" naast "செய்யவில்லை"),
    # dus beide vormen staan erin, zonder woordgrens links. Elke uitzondering
    # is een woord dat erop lijkt en geen ontkenning is.
    # Tamil: niet அல்லது (of).
    r"|(?:இ|ி)ல்லை|(?<![\u0B80-\u0BFF])அல்ல(?!து)|மாட்டா"
    # Telugu: లేదా (of) eindigt op een ander klinkerteken en valt er vanzelf buiten.
    r"|లేదు|లేరు|కాదు|లేని"
    # Malayalam: niet ജില്ല (district), അല്ലെങ്കിൽ (anders) en അല്ലാഹു (Allah).
    r"|ഇല്ല|(?<!ജ)ില്ല|അല്ല(?!െ|ാഹ)"
    # Kannada: niet ಜಿಲ್ಲೆ (district) en ಅಲ್ಲದೆ (bovendien).
    r"|ಇಲ್ಲ|(?<!ಜ)ಿಲ್ಲ|ಅಲ್ಲ(?!ದೆ)"
    # Bengaals en Assamees, één schrift. Losse woorden met een eigen woordgrens
    # (klinkertekens zijn in Python geen woordtekens, zoals bij Hindi), en de
    # werkwoordsuitgang -নি na এ, য় of ন (করেনি, হয়নি, করেননি); য় komt
    # samengesteld en als য plus nukta voor.
    r"|(?<![\u0980-\u09FF])(?:না|নয়|ন\u09df|নেই|নাই|নহয়|নহ\u09df|নোহে)(?![\u0980-\u09FF])"
    r"|(?:ে|য়|\u09df|ন)নি(?![\u0980-\u09FF])"
    # Singalees: het voorvoegsel නො- aan het begin van een woord, maar niet
    # in නොවැම්බර් (november).
    r"|නැත|නැති|නැහැ|(?<![\u0D80-\u0DFF])නෑ(?![\u0D80-\u0DFF])|(?<![\u0D80-\u0DFF])නො(?!වැම්බ)"
    # Punjabi (Gurmukhi).
    r"|ਨਹੀਂ|ਨਹੀ"
    # Khmer schrijft zonder spaties; maart is មីនា, met een andere klinker.
    r"|មិន|គ្មាន",
    re.IGNORECASE,
)


def _vouw_cijfers(ruw: str) -> str:
    """Vouwt elk Unicode-decimaalcijfer naar zijn ASCII-equivalent.

    Generiek via `unicodedata`, niet via een tabel per schrift: `٣` (Arabisch-
    Indisch), `৩` (Bengaals), `۳` (Perzisch) en `३` (Devanagari) zijn alle vier
    een drie, en elk schrift dat later langskomt werkt vanzelf mee.

    Nodig omdat een claim en een artefact hetzelfde getal in verschillende
    schriften kunnen schrijven — en zelfs binnen één claim gemengd, zoals in
    echte Arabische factchecks (BENCHMARK.md §17c).
    """
    if ruw.isascii():
        return ruw
    gevouwen = []
    for teken in ruw:
        waarde = unicodedata.decimal(teken, None)
        gevouwen.append(teken if waarde is None else str(waarde))
    return "".join(gevouwen)


def _canoniek_getal(ruw: str) -> str:
    """Normaliseert scheidingstekens zonder de taal te hoeven kennen.

    De heuristiek is de groepslengte, niet de landinstelling: een scheidingsteken
    gevolgd door precies drie cijfers is een duizendtalscheiding en verdwijnt;
    elk ander scheidingsteken is een decimaalteken en wordt een punt. Zo wordt
    "30.000" → "30000" en "1.234,56" → "1234.56", ongeacht of de tekst Nederlands,
    Duits of Engels is. Het cijferschrift wordt eerst gevouwen, zodat de
    heuristiek ook op `٣٠.٠٠٠` werkt (PLAN.md #11.1).
    """
    ruw = _vouw_cijfers(re.sub(r"[ \u00a0\u202f]", "", ruw))
    delen = re.split(r"[.,]", ruw)
    resultaat = delen[0]
    for deel in delen[1:]:
        if len(deel) == 3:
            resultaat += deel
        else:
            resultaat += "." + deel
    return resultaat


def extract_numbers(text: str) -> frozenset[str]:
    return frozenset(_canoniek_getal(ruw) for ruw in _GETAL.findall(text))


def extract_number_contexts(text: str) -> dict[str, str]:
    """Koppelt elk getal aan het woord erna: {"migranten": "8", "jarig": "15"}.

    Het contextwoord is de sleutel, niet het getal — want de vraag is of
    dezelfde grootheid een ánder getal krijgt. Dat is precies het signaal dat
    een deelverzameling-vergelijking mist wanneer het gewisselde getal
    toevallig elders in de tekst staat (PLAN.md #8.4).
    """
    contexten: dict[str, str] = {}
    for treffer in re.finditer(
        r"(\d+(?:[.,]\d+)*)\s*[-\s]\s*([^\W\d_]+)", text
    ):
        woord = treffer.group(2).casefold()
        # Eerste vermelding wint; herhaling zegt niets extra.
        contexten.setdefault(woord, _canoniek_getal(treffer.group(1)))
    return contexten


def extract_negations(text: str) -> frozenset[str]:
    return frozenset(
        treffer.group().casefold() for treffer in _NEGATIE.finditer(text)
    )


def extract_negation_tokens(text: str) -> tuple[str, ...]:
    """Dezelfde ontkenningen als `extract_negations`, maar mét herhalingen en
    gesorteerd: een tweede "não" in een al ontkende zin telt (#25.1c)."""
    return tuple(sorted(treffer.group().casefold() for treffer in _NEGATIE.finditer(text)))


def _bevat_strikt(groot: Counter, klein: Counter) -> bool:
    """`groot` bevat elke ontkenning van `klein` minstens zo vaak, plus meer."""
    return groot != klein and all(groot[k] >= n for k, n in klein.items())


def contradicts(
    artefact_numbers: frozenset[str],
    artefact_negations: frozenset[str],
    claim_text: str,
    artefact_text: str | None = None,
    artefact_negation_tokens: tuple[str, ...] | None = None,
) -> bool:
    """Twee onafhankelijke getalsignalen plus de negatieflip.

    1. *Contextconflict* — dezelfde grootheid met een ánder getal
       ("8 migranten" tegenover "15 migranten"). Vereist `artefact_text`.
    2. *Deelverzameling* — het artefact voert een getal op dat de claim niet
       kent. Vangt gevallen zonder gedeeld contextwoord.

    Signaal 1 is scherper maar heeft context nodig; signaal 2 is grover maar
    werkt altijd. Samen dekken ze meer dan elk apart.
    """
    if artefact_text is not None:
        artefact_context = extract_number_contexts(artefact_text)
        claim_context = extract_number_contexts(claim_text)
        for woord, getal in artefact_context.items():
            if woord in claim_context and claim_context[woord] != getal:
                return True

    claim_numbers = extract_numbers(claim_text)
    if artefact_numbers and claim_numbers and not artefact_numbers <= claim_numbers:
        return True
    # Negatieflip, geteld (#25.1c): omslag als de ontkenningen van de ene kant
    # een strikte deelverzameling met herhalingen zijn van die van de andere.
    # "Wel tegenover geen" is daar een speciaal geval van; een tweede ontkenning
    # in een al ontkende zin wordt nu ook gezien. Twee kanten die elkaar niet
    # bevatten (Frans "n' … pas" tegenover Engels "not") gelden niet als
    # omslag, zodat vertalingen blijven matchen.
    # De telling komt uit de fingerprint, net als de getallen: de fingerprint is
    # de bron van wat we over het artefact weten. Zonder telling geldt de
    # verzameling (elke ontkenning één keer), wat het oude gedrag is.
    # Een lege telling naast een gevulde verzameling is "geen telling bekend"
    # (een fingerprint van vóór #25.1c), niet "nul ontkenningen".
    claim_telling = Counter(extract_negation_tokens(claim_text))
    if artefact_negation_tokens and len(set(artefact_negation_tokens)) >= len(artefact_negations):
        artefact_telling = Counter(artefact_negation_tokens)
    else:
        artefact_telling = Counter(artefact_negations)
    return _bevat_strikt(artefact_telling, claim_telling) or _bevat_strikt(
        claim_telling, artefact_telling
    )


# Proefteksten voor de gedragsvingerafdruk. Elk mechanisme dat we hebben gebouwd
# staat hier met een voorbeeld; wie er een mechanisme bij bouwt, zet er een proef
# bij. Dat is dezelfde discipline als een test schrijven.
_PROEVEN = (
    # duizendtal- en decimaalscheiding (etappe 8, #8.1)
    "bekommt 30.000 Euro",
    "costs 30,000 euros",
    "1.234,56 en 40 000 en 123 456 789",
    "In 2020 300 mensen",
    # cijferschriften (#11.1)
    "٣٠٠٠٠ en ৩০০০০ en ۳۰۰۰۰ en ३०००० en ٣٠.٠٠٠ en ٣,٥",
    "منذ ١٤ عاما و 19 شهرا و 5 أيام",
    # getal in context (#8.4)
    "8 migranten en 15 jarigen",
    "٨ migranten",
    # ontkenningen per taal (#1.11, #11.3, #11.4)
    "Het vaccin bevat geen microchips",
    "Die Impfung ist nicht wirksam",
    "The vaccine does not contain chips and cannot be proven",
    "Le vaccin n’est pas efficace et n'existe pas",
    "Pas de 2ème vague, ni en Asie, jamais, aucune étude, rien ne prend feu",
    "Nunca, jamás, ningún, ninguna, ninguno, nada, nadie, tampoco, sin visado",
    # ontkenningen in pt, it, ru, id, hi (#25.1b)
    "A vacina não contém chips, nem o governo, nenhum estudo",
    "Il vaccino non funziona, nessuno studio, niente",
    "Вакцина не работает, его нет, никто",
    "Vaksin tidak aman, bukan dari sini, belum terbukti",
    "यह वीडियो असली नहीं है",
    # en hun lijkt-erop-woorden
    "Saya takut, немец, nonostante, nemátodo, यहनहींहै",
    # ontkenningen in de Zuid-Aziatische talen, los en als achtervoegsel (#25.20)
    "இது உண்மை அல்ல, அமைச்சர் கைது செய்யப்படவில்லை, வீடியோ இல்லை",
    "ఇది నిజం కాదు, భూకంపం జరగలేదు, ఆధారం లేని వార్త",
    "ഇത് സത്യം അല്ല, അദ്ദേഹം അത് ചെയ്തില്ല",
    "ಇದು ಸತ್ಯ ಅಲ್ಲ, ಲಾಕ್‌ಡೌನ್ ಜಾರಿ ಆಗಿಲ್ಲ",
    "ভূমিকম্প হয়নি, তিনি করেননি, এটা সত্য না, সঁচা নহয়",
    "මෙය සත්‍ය නොවේ, චිප් එකක් නැත, ඔහු එය නොකළේය",
    "ਇਹ ਵੀਡੀਓ ਸੱਚੀ ਨਹੀਂ ਹੈ, វីដេអូនេះមិនពិតទេ",
    # en hun lijkt-erop-woorden
    "அல்லது இல்லம், లేదా, ജില്ലാ അല്ലെങ്കിൽ നല്ല, ಜಿಲ್ಲೆಯ ಅಲ್ಲದೆ, পানি জানি নানা, නොවැම්බර්, ਨਾਲ, ខែមីនា",
    # dubbele ontkenning: telt als twee (#25.1c)
    "Não é verdade que a vacina não funciona",
    # niet-ontkenningen die er wél op lijken (#11.3)
    "Une Unie une chaîne jeune",
    "Het rapport is pas gisteren gepubliceerd",
    "John's report confirms the finding",
    "Los presupuestos destinan 248 millones; sin embargo la cifra es menor",
)


def derivation_version() -> str:
    """Gedragsvingerafdruk van de afleidingscode achter `numbers` en `negations`.

    De testset slaat die afleidingen op. Verandert de extractiecode, dan is de
    opgeslagen data verouderd — en niets dwong tot nu toe een herbouw af: de
    spatie-duizendtalregex uit etappe 8 zat nooit in de testset, waardoor twee
    benchmarkruns op oude afleidingen zijn gemeten (BENCHMARK.md §19c).

    Afgeleid uit het **gedrag én de patronen**, niet uit een handmatig opgehoogd
    nummer: de bug ontstond juist doordat een mens eraan moest denken.

    Beide helften zijn nodig, want ze dekken elkaars blinde vlek. Alleen patronen
    hashen mist #11.1 — dat wijzigde het gedrag zonder één patroon aan te raken.
    Alleen gedrag hashen mist #11.4 — dat breidde het lexicon met Spaanse tokens
    uit terwijl geen enkele proeftekst Spaans was, dus geen uitkomst veranderde.
    """
    from doublecheck.taal import detecteer_taal

    waarnemingen = [
        [
            tekst,
            sorted(extract_numbers(tekst)),
            sorted(extract_negations(tekst)),
            list(extract_negation_tokens(tekst)),
            sorted(extract_number_contexts(tekst).items()),
            detecteer_taal(tekst),
        ]
        for tekst in _PROEVEN
    ]
    # De patronen zélf horen er ook in. Gedrag en patronen dekken elkaars blinde
    # vlek: #11.1 wijzigde het gedrag zonder een patroon aan te raken, en #11.4
    # breidde het lexicon uit zonder dat een proeftekst het zag — die tweede
    # ontsnapte bijna, want de Spaanse tokens raakten geen enkele proef.
    from doublecheck.taal import _FUNCTIEWOORDEN

    patronen = [
        _GETAL.pattern,
        _NEGATIE.pattern,
        _SPATIE_DUIZENDTAL,
        _PUNT_KOMMA,
        sorted(_FUNCTIEWOORDEN.items()),
    ]
    ruw = json.dumps([patronen, waarnemingen], ensure_ascii=False, sort_keys=True)
    return "afleiding-" + hashlib.sha256(ruw.encode("utf-8")).hexdigest()[:12]
