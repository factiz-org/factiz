"""Verdict-normalisatie naar een vaste, gedocumenteerde set (E2.S2).

De set:
- ``waar``        — de bewering klopt
- ``deels-waar``  — mengsel van juist en onjuist (incl. "mostly true/false")
- ``misleidend``  — technisch verdedigbaar maar misleidend geframed of
                    zonder context
- ``onwaar``      — de bewering klopt niet
- ``onbewezen``   — gecheckt, maar geen bewijs voor of tegen gevonden
- ``satire``      — als grap bedoeld; alleen als dat vaststaat (B56), dus nooit uit een
                    label alleen: "Labeled Satire" en dergelijke tellen als ``onwaar``
- ``onbekend``    — label niet in de tabel; er wordt nooit geraden (AC3)

Uitsluitend exacte matches op het genormaliseerde label: substring-heuristiek
is raden ("not true" bevat "true"). Het originele uitgeverslabel blijft altijd
naast de genormaliseerde waarde bewaard (AC2; kolom ``verdict_original``).

Meertaligheid *(#18.1)*
-----------------------
De tabel kende alleen Nederlands en Engels, terwijl de index dat allang niet
meer was: **53% van het corpus kwam terug als ``onbekend``**, met tien talen op
bijna 100% — Portugees 7.864 checks, Duits 4.147. Dat is dezelfde vorm als het
Latijns-schrift-gebonden meetharnas uit BENCHMARK §17a: het corpus werd
internationaal, het hulpmiddel bleef Engels.

``VERTAALDE_LABELS`` vult dat aan, met drie beperkingen die er expres in zitten:

- **Elke regel draagt haar taal en een letterlijke glos.** Deze vertalingen zijn
  door één persoon gemaakt zonder moedertaalcontrole. Een verkeerd label geeft
  het oordeel van een uitgever verkeerd weer — erger dan géén label (DR1) —
  dus moet een moedertaalspreker de tabel kunnen nakijken zonder de code te
  lezen.
- **Alleen ondubbelzinnige oordeelwoorden.** Labels waarvan de indeling een
  afweging vergt blijven ``onbekend``: het Perzische ``شاخ‌دار`` ("gehoornd",
  eigenzinnig), het Italiaanse ``Nì`` ("ja-nee"), ``Exagerado`` (overdreven —
  deels-waar of misleidend?), en kale schaalwaarden als ``5`` of ``1`` zonder
  legenda.
- **Geen nieuwe categorie.** De set van zeven ligt vast; meer talen mag, een
  nieuwe uitspraakvorm niet (DR2, B10).

Wat bewust *niet* gebouwd is: een regel die het oordeel uit de kop van een
vrije-tekstlabel plukt (``"Misleading. <claimtekst>"``). Gemeten opbrengst 578
checks — 1% van het onbekende — tegenover een faalvorm die meteen opdook:
``"True. However, its link to infertility remains uncertain"`` zou ``waar``
worden. De rest van de staart is ClaimReviews vrije-tekstoordeel, en dat is een
standaardprobleem (B16), geen tabelprobleem.
"""

from __future__ import annotations

import re
import unicodedata

NORMALIZED_CATEGORIES = (
    "waar",
    "deels-waar",
    "misleidend",
    "onwaar",
    "onbewezen",
    "satire",
    "onbekend",
)

_LABELS: dict[str, str] = {
    # waar
    "true": "waar",
    "waar": "waar",
    "juist": "waar",
    "correct": "waar",
    "accurate": "waar",
    "klopt": "waar",
    # deels-waar
    "half true": "deels-waar",
    "half waar": "deels-waar",
    "deels waar": "deels-waar",
    "partly true": "deels-waar",
    "partially true": "deels-waar",
    "mostly true": "deels-waar",
    "grotendeels waar": "deels-waar",
    "mostly false": "deels-waar",
    "grotendeels onwaar": "deels-waar",
    "grotendeels onjuist": "deels-waar",
    "mixture": "deels-waar",
    "mixed": "deels-waar",
    # misleidend
    "misleading": "misleidend",
    "misleidend": "misleidend",
    "missing context": "misleidend",
    "buiten context": "misleidend",
    "out of context": "misleidend",
    # onwaar
    "false": "onwaar",
    "onwaar": "onwaar",
    "onjuist": "onwaar",
    "untrue": "onwaar",
    "incorrect": "onwaar",
    "pants on fire": "onwaar",
    "fake": "onwaar",
    "disinformation": "onwaar",  # EUvsDisinfo-gevallen (#24.6), naast "disinformasi"
    "nep": "onwaar",
    "onzin": "onwaar",
    # onbewezen
    "unproven": "onbewezen",
    "unverified": "onbewezen",
    "unsubstantiated": "onbewezen",
    "no evidence": "onbewezen",
    "geen bewijs": "onbewezen",
    "onbewezen": "onbewezen",
    # satire (B56, PO 2026-11-04): alleen als vaststaat dat het als grap bedoeld is. Een label zegt dat niet, en een
    # site die zich satire noemt maar hoaxes maakt, is geen satire; als nieuws klopt het niet, dus onwaar.
    "satire": "onwaar",
    "labeled satire": "onwaar",
    "originated as satire": "onwaar",
    "satirisch": "onwaar",
    # Engelse labels die als géhéél één oordeel zijn (#25.3). Geen kopregel:
    # alleen exacte labels, zodat "True. However, …" nooit `waar` wordt.
    "the claim is false": "onwaar",
    "this is false claim": "onwaar",
    "false headline": "onwaar",
    "wrong": "onwaar",
    "inaccurate": "onwaar",
    "not legit": "onwaar",
    "this is misleading": "misleidend",
    "lacks context": "misleidend",
    "not the whole story": "misleidend",
    "spins the facts": "misleidend",
    "old video": "misleidend",
    "unsupported": "onbewezen",
    "no basis": "onbewezen",
}


# Labels buiten het Nederlands en Engels: (categorie, taal, letterlijke glos).
# De glos is er voor de lezer die de taal wél spreekt en de indeling wil
# nakijken — zie de moduletekst hierboven (#18.1).
VERTAALDE_LABELS: dict[str, tuple[str, str, str]] = {
    # --- Portugees · 7.853 onbekend, top-8 dekte 91% ------------------------
    "falso": ("onwaar", "pt", "vals"),
    "verdadeiro": ("waar", "pt", "waar"),
    "enganoso": ("misleidend", "pt", "misleidend"),
    "verdadeiro, mas": ("deels-waar", "pt", "waar, maar…"),
    # --- Spaans · 5.292 onbekend --------------------------------------------
    "verdadero": ("waar", "es", "waar"),
    "verdad": ("waar", "es", "waarheid"),
    "engañoso": ("misleidend", "es", "misleidend"),
    "falta contexto": ("misleidend", "es", "context ontbreekt"),
    "no hay evidencias": ("onbewezen", "es", "er is geen bewijs"),
    # Factchequeado en EFE Verifica (#32.19, BENCHMARK §190): letterlijk "missing context" en "no evidence"
    "necesita contexto": ("misleidend", "es", "heeft context nodig"),
    "no hay pruebas": ("onbewezen", "es", "er zijn geen bewijzen"),
    "real": ("waar", "es", "echt"),
    # EFE Verifica (route A, #32.38): hele labels, ingedeeld zoals hun tegenhanger hierboven ("mostly false" en
    # "partly false" deels-waar, "missing context" misleidend)
    "falsa": ("onwaar", "es", "vals (vrouwelijk)"),
    "es falso": ("onwaar", "es", "het is vals"),
    "es falsa": ("onwaar", "es", "het is vals (vrouwelijk)"),
    "parcialmente falso": ("deels-waar", "es", "gedeeltelijk vals"),
    "parcialmente falsa": ("deels-waar", "es", "gedeeltelijk vals (vrouwelijk)"),
    "falso en su mayor parte": ("deels-waar", "es", "grotendeels vals"),
    "falsa en su mayor parte": ("deels-waar", "es", "grotendeels vals (vrouwelijk)"),
    "parcialmente veraz": ("deels-waar", "es", "gedeeltelijk waarheidsgetrouw"),
    "sin pruebas": ("onbewezen", "es", "zonder bewijzen"),
    "sin evidencia": ("onbewezen", "es", "zonder bewijs"),
    "cierto": ("waar", "es", "waar, juist"),
    "descontextualizado": ("misleidend", "es", "uit de context gehaald"),
    "falta de contexto": ("misleidend", "es", "gebrek aan context"),
    # --- Duits · 4.061 onbekend, maar grotendeels vrije tekst ---------------
    "falsch": ("onwaar", "de", "vals"),
    "richtig": ("waar", "de", "juist"),
    "irreführend": ("misleidend", "de", "misleidend"),
    "unbelegt": ("onbewezen", "de", "niet onderbouwd"),
    "teilweise falsch": ("deels-waar", "de", "gedeeltelijk vals"),
    # --- Frans ---------------------------------------------------------------
    "faux": ("onwaar", "fr", "vals"),
    "vrai": ("waar", "fr", "waar"),
    "trompeur": ("misleidend", "fr", "misleidend"),
    # --- Italiaans (de speelse schaal van Pagella Politica blijft onbekend) --
    "vero": ("waar", "it", "waar"),
    # --- Pools ---------------------------------------------------------------
    "fałsz": ("onwaar", "pl", "leugen"),
    "prawda": ("waar", "pl", "waarheid"),
    "manipulacja": ("misleidend", "pl", "manipulatie"),
    "nieweryfikowalne": ("onbewezen", "pl", "niet verifieerbaar"),
    # --- Nederlands dat nog ontbrak -----------------------------------------
    "eerder onwaar": ("deels-waar", "nl", "eerder onwaar dan waar"),
    "eerder waar": ("deels-waar", "nl", "eerder waar dan onwaar"),
    "niet waar": ("onwaar", "nl", "niet waar"),
    "gedeeltelijk fout": ("deels-waar", "nl", "gedeeltelijk fout"),
    "ontbrekende context": ("misleidend", "nl", "ontbrekende context"),
    # --- Turks · 786 onbekend, top-8 dekte 99% ------------------------------
    "yanlış": ("onwaar", "tr", "verkeerd"),
    "doğru": ("waar", "tr", "juist"),
    "çoğunlukla yanlış": ("deels-waar", "tr", "grotendeels verkeerd"),
    # --- Indonesisch · 1.184 onbekend ---------------------------------------
    "keliru": ("onwaar", "id", "onjuist"),
    "sesat": ("misleidend", "id", "misleidend"),
    "hoaks": ("onwaar", "id", "hoax"),
    "benar": ("waar", "id", "juist"),
    "salah": ("onwaar", "id", "fout"),
    "disinformasi": ("onwaar", "id", "desinformatie"),
    "sebagian benar": ("deels-waar", "id", "gedeeltelijk juist"),
    # --- Tagalog · 405 onbekend ---------------------------------------------
    "hindi totoo": ("onwaar", "tl", "niet waar"),
    "kailangan ng konteksto": ("misleidend", "tl", "context nodig"),
    "nakaliligaw": ("misleidend", "tl", "misleidend"),
    "mali": ("onwaar", "tl", "fout"),
    "peke": ("onwaar", "tl", "nep"),
    "walang basehan": ("onbewezen", "tl", "zonder grondslag"),
    # --- Perzisch · 2.829 onbekend ------------------------------------------
    "نادرست": ("onwaar", "fa", "onjuist"),
    "درست": ("waar", "fa", "juist"),
    "گمراه‌کننده": ("misleidend", "fa", "misleidend"),
    "نیمه‌درست": ("deels-waar", "fa", "half juist"),
    "نیمه درست": ("deels-waar", "fa", "half juist"),
    "غیرقابل اثبات": ("onbewezen", "fa", "niet te bewijzen"),
    # --- Arabisch · 2.381 onbekend ------------------------------------------
    "مضلل": ("misleidend", "ar", "misleidend"),
    "تضليل": ("misleidend", "ar", "misleiding"),
    "خبر كاذب": ("onwaar", "ar", "vals bericht"),
    "خطأ": ("onwaar", "ar", "fout"),
    "صحيح": ("waar", "ar", "juist"),
    "غير صحيح": ("onwaar", "ar", "niet juist"),
    "كذب": ("onwaar", "ar", "leugen"),
    "مش حقيقي": ("onwaar", "ar", "niet echt"),
    # --- Chinees · 1.003 onbekend -------------------------------------------
    "不實": ("onwaar", "zh", "niet naar waarheid"),
    "錯誤": ("onwaar", "zh", "fout"),
    "部分錯誤": ("deels-waar", "zh", "gedeeltelijk fout"),
    "部分不實": ("deels-waar", "zh", "gedeeltelijk onwaar"),
    "大部分不實": ("deels-waar", "zh", "grotendeels onwaar"),
    "屬實": ("waar", "zh", "naar waarheid"),
    "半數屬實": ("deels-waar", "zh", "half naar waarheid"),
    # --- Japans · 873 onbekend ----------------------------------------------
    "誤り": ("onwaar", "ja", "onjuistheid"),
    "不正確": ("onwaar", "ja", "onnauwkeurig"),
    "虚偽": ("onwaar", "ja", "onwaarheid"),
    "根拠不明": ("onbewezen", "ja", "grondslag onbekend"),
    "ミスリード": ("misleidend", "ja", "misleading"),
    # --- Hebreeuws · 423 onbekend -------------------------------------------
    "לא נכון": ("onwaar", "he", "niet juist"),
    "נכון": ("waar", "he", "juist"),
    "לא נכון ברובו": ("deels-waar", "he", "grotendeels niet juist"),
    "נכון ברובו": ("deels-waar", "he", "grotendeels juist"),
    "חצי נכון": ("deels-waar", "he", "half juist"),
    "מטעה": ("misleidend", "he", "misleidend"),
    "דרוש הקשר": ("misleidend", "he", "context vereist"),
    # --- Hindi · 1.068 onbekend ---------------------------------------------
    "भ्रामक": ("misleidend", "hi", "misleidend"),
    "झूठ": ("onwaar", "hi", "leugen"),
    "फ़ेक": ("onwaar", "hi", "nep"),
    "असत्य": ("onwaar", "hi", "onwaar"),
    "गलत": ("onwaar", "hi", "fout"),
    # --- Russisch · 572 onbekend, grotendeels vrije tekst -------------------
    "фейк": ("onwaar", "ru", "fake"),
    "ложь": ("onwaar", "ru", "leugen"),
    "правда": ("waar", "ru", "waarheid"),
    "манипуляция": ("misleidend", "ru", "manipulatie"),
    "полуправда": ("deels-waar", "ru", "halve waarheid"),
    "намеренно созданный фейк": ("onwaar", "ru", "opzettelijk gemaakte fake"),
    "искажение информации": ("misleidend", "ru", "verdraaiing van informatie"),
    "по большей части фейк": ("deels-waar", "ru", "grotendeels fake"),
    # --- Koreaans (de kale cijfers 1-5 blijven onbekend: geen legenda) ------
    "절반의 사실": ("deels-waar", "ko", "de helft van de waarheid"),
    # --- Engels dat ontbrak · 7.343 onbekend --------------------------------
    # `Altered` gaat over een bewerkt beeld dat als echt wordt gepresenteerd;
    # de bewering dat het toont wat het beweert, klopt dan niet. De numerieke
    # score van de uitgevers zelf bevestigt dat: mediaan 0,00 op hun schaal.
    "altered": ("onwaar", "en", "bewerkt"),
    "hoax": ("onwaar", "en", "verzinsel dat als echt is rondgestuurd"),
    "needs context": ("misleidend", "en", "context nodig"),
    "partly false": ("deels-waar", "en", "gedeeltelijk vals"),
    "distorts the facts": ("misleidend", "en", "verdraait de feiten"),
    # Documenteerde uitgeversschaal, net als het al aanwezige "pants on fire".
    "four pinocchios": ("onwaar", "en", "vier Pinokkio's, de zwaarste graad"),
    # Twee schrijfwijzen in het corpus; de dubbele punt overleeft de
    # normalisatie, dus die staat er hier ook in.
    "fact crescendo rating: false": ("onwaar", "en", "Fact Crescendo-oordeel: vals"),
    "fact crescendo rating false": ("onwaar", "en", "Fact Crescendo-oordeel: vals"),
    # --- #25.3: de staart, alleen ondubbelzinnige oordeelwoorden ---------------
    "ஃபேக்ட் கிரஸண்டோ ரேட்டிங்: false": ("onwaar", "ta", "Fact Crescendo-oordeel: vals"),
    "خاطئ": ("onwaar", "ar", "fout"),
    "زائف": ("onwaar", "ar", "vals, nep"),
    "كاذب": ("onwaar", "ar", "leugenachtig, vals"),
    "مفبرك": ("onwaar", "ar", "verzonnen, gefabriceerd"),
    "غير مثبت": ("onbewezen", "ar", "niet bewezen"),
    "صحيح جزئياً": ("deels-waar", "ar", "gedeeltelijk juist"),
    "صحيح جزئيا": ("deels-waar", "ar", "gedeeltelijk juist"),
    "غير صحيح جزئيا": ("deels-waar", "ar", "gedeeltelijk onjuist"),
    "худал": ("onwaar", "mn", "leugen"),
    "төөрөгдүүлсэн": ("misleidend", "mn", "misleidend"),
    "yalan": ("onwaar", "az", "leugen"),
    "əsasən yanlış": ("deels-waar", "az", "grotendeels onjuist"),
    "মিছা": ("onwaar", "as", "vals"),
    "netočno, dezinformacija": ("onwaar", "hr", "onjuist, desinformatie"),
    "verdad a medias": ("deels-waar", "es", "halve waarheid"),
    "fuera de contexto": ("misleidend", "es", "buiten context"),
    "insustentável": ("onbewezen", "pt", "onhoudbaar, niet te onderbouwen"),
    # De negen talen van #25.18 kwamen binnen zonder hun oordeelwoorden.
    # Alleen woorden die in het corpus voorkomen, ingedeeld zoals hun Engelse
    # tegenhanger in deze tabel ("fake" en "false" onwaar, "out of context"
    # en "missing context" misleidend, "partly false" deels-waar).
    "ತಪ್ಪು": ("onwaar", "kn", "fout, onjuist"),
    "ಫೇಕ್": ("onwaar", "kn", "nep (het Engelse fake, getranslitereerd)"),
    "ಸಂದರ್ಭದಿಂದ ಹೊರಗಿಡಲಾಗಿದೆ": ("misleidend", "kn", "uit de context gehaald"),
    "মিথ্যা": ("onwaar", "bn", "onwaar, leugen"),
    "বিভ্রান্তিকর": ("misleidend", "bn", "misleidend"),
    "ভুয়া": ("onwaar", "bn", "nep, vals"),
    "বিভ্ৰান্তিকৰ": ("misleidend", "as", "misleidend"),
    "ভুৱা": ("onwaar", "as", "nep, vals"),
    "আংশিকভাৱে মিছা": ("deels-waar", "as", "gedeeltelijk onwaar"),
    "প্ৰসংগ সংগতিহীন": ("misleidend", "as", "zonder passende context"),
    "फर्जी": ("onwaar", "hi", "nep, vervalst"),
    # --- #25.24: satire bij redacties buiten het Engels ---------------------
    # Du-Check zet "onjuist" en "satire" in één label. Satire is het
    # preciezere oordeel: als feit klopt het niet, bedoeld was het niet.
    # "Sarcasm" van YouTurn blijft onbekend: een eigen label van één redactie,
    # en YouTurn publiceert geen legenda die zegt wat het betekent (#25.3b).
    "sátira": ("onwaar", "pt", "satire; als nieuws onwaar (B56)"),
    "netočno, satira": ("onwaar", "hr", "onjuist, satire (B56)"),
}

_LABELS.update(
    {label: categorie for label, (categorie, _, _) in VERTAALDE_LABELS.items()}
)


def _normaliseer_label(label: str) -> str:
    # NFC: dezelfde letter kan op twee manieren gecodeerd staan. Het corpus
    # schreef "फ़ेक" met één samengesteld teken (U+095E), de tabel met फ plus
    # een losse nukta; voor het oog gelijk, voor een vergelijking niet (#25.3b).
    kaal = unicodedata.normalize("NFC", label).casefold().replace("-", " ").replace("_", " ")
    kaal = re.sub(r"\s+", " ", kaal).strip()
    # De danda (।) sluit een zin af in Devanagari en Bengaals, zoals de punt.
    return kaal.strip(".!,।")


_ARABISCH_SCHRIFT = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")


def _compact(sleutel: str) -> str:
    """Perzisch schrijft dezelfde woorden met een halve spatie (ZWNJ), een
    spatie of aaneen; bij Factnameh bleef "غیرقابل اثبات" zo in drie van de
    vier schrijfwijzen `onbekend`. Alleen in Arabisch schrift vallen spaties en
    halve spaties weg uit de vergelijkingssleutel."""
    if not _ARABISCH_SCHRIFT.search(sleutel):
        return sleutel
    return sleutel.replace("\u200c", "").replace(" ", "")


_INDEX = {_normaliseer_label(k): v for k, v in _LABELS.items()}
_COMPACT_INDEX = {_compact(k): v for k, v in _INDEX.items()}


# Schaallegenda per uitgever (#25.3b). Een label als "Three Pinocchios" of
# "Nì" betekent pas iets naast de methode van de redactie die het gebruikt;
# de algemene tabel laat het daarom `onbekend`. Per host: de bron, en per label
# de categorie met een glos. Alleen wat de bron draagt; de rest blijft onbekend
# (één Pinokkio, de omgekeerde Pinokkio, "Contraditório" van Lupa).
SCHAALLEGENDA: dict[str, dict] = {
    "washingtonpost.com": {
        "bron": "https://www.wfae.org/2025-07-31/glenn-kessler-reflects-on-14-years-as-the-washington-posts-fact-checker",
        "toelichting": "Glenn Kessler, de maker van de schaal: twee Pinokkio's is half waar, drie grotendeels "
                       "onwaar, vier een leugen. De methodepagina (washingtonpost.com/politics/2019/01/07/"
                       "about-fact-checker) zit achter een betaalmuur.",
        "labels": {
            "two pinocchios": ("deels-waar", "half waar"),
            "three pinocchios": ("deels-waar", "grotendeels onwaar; 'mostly false' valt in deze set onder deels-waar"),
        },
    },
    "pagellapolitica.it": {
        "bron": "https://pagellapolitica.it/articoli/il-2021-di-pagella-politica-in-360-fact-checking",
        "toelichting": "De schaal tot maart 2022, uit de eigen jaaroverzichten van 2019 tot 2021: 'Vero' en "
                       "'C'eri quasi' goed of met kleine fouten, 'Nì' meerdere feiten waarvan sommige "
                       "onnauwkeurig, 'Pinocchio andante' vaag met onjuiste conclusies, 'Panzana pazzesca' "
                       "volledig fout.",
        "labels": {
            "c'eri quasi": ("deels-waar", "bijna goed: met kleine fouten"),
            "nì": ("deels-waar", "ja-nee: meerdere feiten, sommige onnauwkeurig"),
            "pinocchio andante": ("deels-waar", "vaag of algemeen, met onjuiste conclusies"),
            "panzana pazzesca": ("onwaar", "volledig fout"),
        },
    },
    "lupa.uol.com.br": {
        "bron": "https://uploads.agencialupa.org/2026/05/Lupa-no-Feed-_-Modulo-2-Os-7-Disfarces-da-Desinformacao.pdf",
        "toelichting": "Lupa's eigen materiaal: 'Exagerado' voor opgeblazen cijfers of overdreven beweringen, "
                       "'Subestimado' (sinds 2018) als het werkelijke probleem groter is dan gezegd.",
        "labels": {
            "exagerado": ("deels-waar", "overdreven: de goede richting, opgeblazen cijfers"),
            "subestimado": ("deels-waar", "onderschat: het probleem is groter dan gezegd"),
        },
    },
    "factnameh.com": {
        "bron": "https://factnameh.com/fa/principles#conclusions",
        "toelichting": "Factnameh's eigen schaal: na نادرست (onwaar) komt شاخ‌دار, een bewering die zo onwaar "
                       "en absurd is dat 'zelfs een gebraden kip erom moet lachen'.",
        "labels": {
            "شاخ‌دار": ("onwaar", "absurd onwaar, voorbij 'onwaar'"),
        },
    },
    # De legenda's van de proef van route A (#32.19, BENCHMARK §190), gelezen op 1 november 2026.
    "snopes.com": {
        "bron": "https://www.snopes.com/fact-check-ratings/",
        "toelichting": "Snopes' eigen lijst (bijgewerkt 7 mei 2026). 'Miscaptioned': echte foto of video, maar het "
                       "bijschrift beschrijft herkomst, context of betekenis verkeerd. 'Legit': lijkt een oplichting, "
                       "maar is echt. 'Scam', 'Legend' en 'Outdated' zijn geen oordeel over de bewering en blijven "
                       "onbekend. Gelezen op 4 november 2026 (#32.38): '(retired)' staat bij een oordeel dat Snopes "
                       "niet meer geeft, met dezelfde betekenis; 'Unfounded' gold voor beweringen zonder aantoonbaar "
                       "bewijs, 'Recall' beschrijft echte terugroepacties; 'Lost Legend' en 'Research In Progress' "
                       "zijn, net als 'Scam', 'Legend' en 'Outdated', geen oordeel over de bewering.",
        "labels": {
            "correct attribution": ("waar", "het citaat is van wie het genoemd wordt"),
            "incorrect attribution": ("onwaar", "het citaat is niet van wie het genoemd wordt"),
            "miscaptioned": ("misleidend", "echt beeld, verkeerd bijschrift"),
            "legit": ("waar", "lijkt oplichting, maar is echt"),
            "unfounded": ("onbewezen", "geen aantoonbaar bewijs, uit geruchten of speculatie"),
            "recall": ("waar", "een echte terugroepactie, zoals 'legit'"),
        },
        "achtervoegsel": " (retired)",
        "geen_oordeel": ("scam", "legend", "outdated", "lost legend", "research in progress"),
    },
    "maldita.es": {
        "bron": "https://maldita.es/metodologia-maldita/",
        "toelichting": "Maldita's methodologie (versie van 27 mei 2026): 'Alerta' is inhoud waarvoor geen bewijs "
                       "bestaat, zonder genoeg onafhankelijke bronnen om haar onwaar te noemen. 'Contexto' (een "
                       "publiek debat met meerdere kanten, of een onderzoek dat nog loopt) vraagt een afweging en "
                       "blijft onbekend; geen taalmodel leest er een oordeel in. 'Falso' of 'Bulo' is inhoud die "
                       "onafhankelijk als onwaar na te gaan is; de soort heet 'Falso/ Bulo/ Timo' (#32.66).",
        "labels": {
            "alerta": ("onbewezen", "waarschuwing: geen bewijs dat het klopt, niet bewezen onwaar"),
            "bulo": ("onwaar", "onafhankelijk na te gaan dat het onwaar is"),
            "timo": ("onwaar", "oplichting, in Maldita's soort 'Falso/ Bulo/ Timo'"),
        },
        "geen_oordeel": ("contexto",),
    },
    "aosfatos.org": {
        "bron": "https://www.aosfatos.org/politica-editorial/",
        "toelichting": "De drie zegels van Aos Fatos ('Os selos'): 'Não é bem assim' is informatie buiten context, "
                       "opgeblazen of veranderd, met als doel een verkeerd beeld van de werkelijkheid.",
        "labels": {
            "não é bem assim": ("misleidend", "zo zit het niet helemaal"),
        },
    },
    "aap.com.au": {
        "bron": "https://www.aap.com.au/factcheck/how-we-work/",
        "toelichting": "AAP FactCheck geeft één van zeven oordelen (True, Mostly True, Mixture, Mostly False, False, "
                       "Misleading, Unproven), 'a clear and simple conclusion'. In de ClaimReview staat dat woord "
                       "vooraan in de zin ('False. The video is AI-generated.'). Alleen op deze host, en alleen een "
                       "woord van deze schaal, telt de kop; een algemene kopregel blijft verworpen (#25.3).",
        "labels": {},
        "kop": ("true", "mostly true", "mixture", "mixed", "mostly false", "false", "misleading", "unproven"),
    },
    # Route A terug in de tijd (#32.38, stap 3c, PO 2026-11-04).
    "fullfact.org": {
        "bron": "https://fullfact.org/how-we-fact-check/",
        "toelichting": "Full Fact geeft geen oordeel op een schaal, maar 'our corresponding conclusions, at the top of "
                       "each article' (gelezen 2026-11-04): een conclusie in een zin. Alleen een afwijzende "
                       "eerste zin telt ('False.', 'This is not true.', 'Incorrect.', 'This is misleading.'), of het hele "
                       "oordeel als dat zo'n zin is. Geen goedkeurende kop ('Correct.', 'True.'), want daar volgt vaak "
                       "een maar (#25.3); geen 'Not quite'. In 60 nagelezen checks waren alle 17 met zo'n kop onwaar; "
                       "de regel ging pas in gebruik na 50 nieuwe, blind gelezen (PLAN #32.38).",
        "labels": {},
        "kop_labels": {
            **{k: ("onwaar", "een afwijzende eerste zin") for k in (
                "false", "untrue", "this is untrue", "not true", "this is not true", "this isn't true",
                "that's not true", "this is false", "incorrect", "this is incorrect", "this is not correct",
                "this isn't correct", "inaccurate", "wrong", "this is wrong", "fake", "this is fake", "this is a hoax",
                "these posts are hoaxes")},
            **{k: ("misleidend", "een eerste zin die het misleidend noemt") for k in ("misleading", "this is misleading")},
        },
    },
}
# De Duitstalige redacties zonder vaste schaal (#32.46, stap 2, PO 2026-11-07: "maken we v10 gelijk wat completer"): de
# conclusie staat vooraan, en net als bij Full Fact telt alleen een afwijzende eerste zin, of het hele oordeel als dat
# zo'n zin is. Geen goedkeurende kop ("Richtig."), geen "Richtig ist, dass …" en geen "Nein." (een antwoord op een vraag).
_DUITSE_KOPPEN = {
    **{k: ("onwaar", "een afwijzende eerste zin") for k in (
        "falsch", "das ist falsch", "die behauptung ist falsch", "diese behauptung ist falsch",
        "die behauptungen sind falsch", "diese behauptungen sind falsch", "die aussage ist falsch", "falschbehauptung",
        "das stimmt nicht", "frei erfunden", "lüge", "fake")},
    **{k: ("misleidend", "een eerste zin die het misleidend of uit zijn verband noemt") for k in (
        "irreführend", "die behauptung ist irreführend", "falscher kontext")},
}
_DPA = ("De dpa gebruikt geen vaste schaal, omdat veel beweringen te ingewikkeld zijn voor goed of fout; de stand van de "
        "feiten staat in de kop of de inleiding (de Faktencheck-Regeln, gelezen 2026-11-07). Alleen een afwijzende eerste "
        "zin telt.")
SCHAALLEGENDA.update({
    "dpa-factchecking.com": {"bron": "https://dpa-factchecking.com/about/austria", "toelichting": _DPA, "labels": {},
                             "kop_labels": _DUITSE_KOPPEN},
    # de dpa publiceert haar factchecks ook via presseportal.de; in de database staan daar alleen die van de dpa
    "presseportal.de": {"bron": "https://dpa-factchecking.com/about/austria", "toelichting": _DPA, "labels": {},
                        "kop_labels": _DUITSE_KOPPEN},
    "apa.at": {"bron": "https://apa.at/faktencheck/regeln/",
               "toelichting": "De APA liet een schaal van waar, deels waar en vals los; de Einschätzung staat vooraan, "
                              "als conclusie vóór de controle (de Regeln des APA-Faktenchecks, gelezen 2026-11-07). Alleen "
                              "een afwijzende eerste zin telt.",
               "labels": {}, "kop_labels": _DUITSE_KOPPEN},
})
for _legenda in SCHAALLEGENDA.values():
    _legenda["_index"] = {_compact(_normaliseer_label(k)): v[0] for k, v in _legenda["labels"].items()}

# Fact Crescendo zet een vaste aanhef voor zijn oordeel, ook in Tamil-schrift:
# "Fact Crescendo Rating: Mixture". Op hun eigen hosts telt wat erna komt.
_FACT_CRESCENDO = re.compile(r"^(?:fact crescendo(?: \S+)? rating|ஃபேக்ட் கிரஸண்டோ ரேட்டிங்)\s*:\s*")


def _tabel(sleutel: str) -> str:
    return _INDEX.get(sleutel) or _COMPACT_INDEX.get(_compact(sleutel), "onbekend")


def normalize_verdict(label: str | None, host: str | None = None) -> str:
    """De categorie van een uitgeverslabel. Met `host` telt eerst de
    schaallegenda van die redactie; zonder host, of op een host zonder
    legenda, alleen de algemene tabel. Er wordt nooit geraden."""
    if not label or not label.strip():
        return "onbekend"
    sleutel = _normaliseer_label(label)
    if host:
        legenda = SCHAALLEGENDA.get(host)
        sleutel = _zonder_achtervoegsel(sleutel, legenda)
        if legenda and _compact(sleutel) in legenda["_index"]:
            return legenda["_index"][_compact(sleutel)]
        if legenda and legenda.get("kop") and "." in sleutel:
            # het oordeelwoord vooraan in de zin, alleen een woord van de eigen schaal (aap.com.au)
            kop = sleutel.split(".", 1)[0].strip()
            if kop in legenda["kop"]:
                return _tabel(kop)
        if legenda and legenda.get("kop_labels"):
            # de eerste zin, of het hele oordeel, is precies een vaste zin van de redactie (fullfact.org)
            kop = sleutel.split(".", 1)[0].strip().replace("’", "'")
            if kop in legenda["kop_labels"]:
                return legenda["kop_labels"][kop][0]
        if host == "factcrescendo.com" or host.endswith(".factcrescendo.com"):
            kaal = _FACT_CRESCENDO.sub("", sleutel, count=1)
            if kaal != sleutel:
                return _tabel(kaal.strip())
    return _tabel(sleutel)


def _zonder_achtervoegsel(sleutel: str, legenda: dict | None) -> str:
    """Een vast achtervoegsel van de redactie dat de betekenis niet verandert (Snopes: "Unproven (retired)")."""
    achter = (legenda or {}).get("achtervoegsel")
    return sleutel[: -len(achter)].strip() if achter and sleutel.endswith(achter) else sleutel


def geen_oordeel(label: str | None, host: str | None) -> bool:
    """Of de eigen lijst van de redactie zegt dat dit label geen oordeel over de bewering is (Snopes: "Scam",
    "Legend"). Zo'n label blijft `onbekend` en gaat niet naar een taalmodel om toch een oordeel te lezen."""
    legenda = SCHAALLEGENDA.get(host or "")
    if not legenda or not label:
        return False
    return _zonder_achtervoegsel(_normaliseer_label(label), legenda) in legenda.get("geen_oordeel", ())


# --- De labelklasse (B30, DESIGN §4c, #24.2c) ----------------------------------
#
# Welk label hoort bij de oordelen van de redacties die de resolver toont? Dit
# is dezelfde regel als `kopVoor` in de demo (`webui.py`): een oordeel zonder
# kant telt niet mee zolang er een check mét kant is, en oordelen op
# verschillende kanten zijn omstreden. De kanten zijn namen, geen kleuren.
_KANT = {"onwaar": "rood", "misleidend": "rood", "waar": "groen", "deels-waar": "midden"}


def labelklasse(oordelen) -> str | None:
    """De labelklasse van een reeks genormaliseerde oordelen: onwaar,
    misleidend, onwaar-of-misleidend, waar, deels-waar, omstreden, satire of
    onbewezen; `None` als geen oordeel iets zegt."""
    oordelen = list(oordelen)
    met_kant = [o for o in oordelen if o in _KANT]
    kanten = {_KANT[o] for o in met_kant}
    if len(kanten) > 1:
        return "omstreden"
    if met_kant:
        if all(o == "onwaar" for o in met_kant):
            return "onwaar"
        if all(o == "misleidend" for o in met_kant):
            return "misleidend"
        return {"rood": "onwaar-of-misleidend", "groen": "waar", "midden": "deels-waar"}[kanten.pop()]
    if oordelen and all(o == "satire" for o in oordelen):
        return "satire"
    if oordelen and all(o == "onbewezen" for o in oordelen):
        return "onbewezen"
    return None


# Jongste oordeel voorop (PO 2026-10-15, B30 aangevuld). Hier telt "onbewezen"
# wél als positie: een redactie die later "onbewezen" zegt, neemt een eerder
# "onwaar" terug (het lab in Wuhan: 2020 onwaar, 2025 onbewezen).
_POSITIE = {"onwaar": "rood", "misleidend": "rood", "onwaar-of-misleidend": "rood", "waar": "groen",
            "deels-waar": "midden", "omstreden": "omstreden", "onbewezen": "onbewezen"}


def labelklasse_in_tijd(checks) -> tuple[str | None, list[tuple[str, str]]]:
    """(oordeel, reviewdatum) naar de labelklasse en wat er eerder gezegd werd.

    Verschuift de positie over de jaren, dan de klasse van het jongste jaar
    met een positie, en per eerdere positie (nieuw naar oud) de klasse en het
    jaar. Anders de klasse over alle checks, zoals `labelklasse`. Checks zonder
    geldige datum en oordelen die niet te normaliseren waren beslissen nooit
    over een verschuiving."""
    from doublecheck.datums import geldige_review_datum

    checks = list(checks)
    per_jaar: dict[str, list[str]] = {}
    for oordeel, datum in checks:
        jaar = geldige_review_datum(datum or "")[:4]
        if jaar and oordeel != "onbekend":
            per_jaar.setdefault(jaar, []).append(oordeel)
    klasse_per_jaar = {jaar: labelklasse(oordelen) for jaar, oordelen in per_jaar.items()}
    positie = {jaar: _POSITIE[k] for jaar, k in klasse_per_jaar.items() if k in _POSITIE}
    if len(set(positie.values())) <= 1:
        return labelklasse(o for o, _ in checks), []
    jaren = sorted(positie, reverse=True)
    eerder, gezien = [], {positie[jaren[0]]}
    for jaar in jaren[1:]:
        if positie[jaar] not in gezien:
            eerder.append((klasse_per_jaar[jaar], jaar))
            gezien.add(positie[jaar])
    return klasse_per_jaar[jaren[0]], eerder
