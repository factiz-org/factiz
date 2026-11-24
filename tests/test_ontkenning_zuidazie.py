"""Ontkenningen in de Zuid-Aziatische talen (PLAN.md #25.20).

In Tamil, Telugu, Malayalam en Kannada hangt de ontkenning vaak als
achtervoegsel aan het werkwoord ("செய்யவில்லை", "చేయలేదు"); een woordenlijst
volstaat daar niet. Stap 1 maakt het gat zichtbaar: ontkenningsparen in de
testset, per constructie een andere bewering.
"""

import pytest

from doublecheck.storage import connect, init_schema, save_text_fingerprint
from doublecheck.testset import TestPair, _negation_variant, load_test_pairs, save_test_pair, voeg_ontkenningsparen_toe
from tests.test_ingest import NEP


@pytest.mark.parametrize("taal, claim, ontkend", [
    ("ta", "இந்த வீடியோ இணையத்தில் வைரலாக உள்ளது", "இந்த வீடியோ இணையத்தில் வைரலாக இல்லை"),
    ("ta", "அமைச்சர் கைது செய்யப்பட்டது", "அமைச்சர் கைது செய்யப்படவில்லை"),
    ("te", "ఈ వీడియో సోషల్ మీడియాలో ఉంది", "ఈ వీడియో సోషల్ మీడియాలో లేదు"),
    ("te", "హైదరాబాద్‌లో భూకంపం జరిగింది", "హైదరాబాద్‌లో భూకంపం జరగలేదు"),
    ("ml", "ഈ മരുന്നിന് പാർശ്വഫലങ്ങൾ ഉണ്ട്", "ഈ മരുന്നിന് പാർശ്വഫലങ്ങൾ ഇല്ല"),
    ("ml", "ഈ ചിത്രം കേരളത്തിൽ നിന്നുള്ളത് ആണ്", "ഈ ചിത്രം കേരളത്തിൽ നിന്നുള്ളത് അല്ല"),
    ("kn", "ಈ ಲಸಿಕೆಯಲ್ಲಿ ಚಿಪ್ ಇದೆ", "ಈ ಲಸಿಕೆಯಲ್ಲಿ ಚಿಪ್ ಇಲ್ಲ"),
    ("kn", "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಲಾಕ್‌ಡೌನ್ ಜಾರಿ ಆಗಿದೆ", "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಲಾಕ್‌ಡೌನ್ ಜಾರಿ ಆಗಿಲ್ಲ"),
    ("bn", "এই ভিডিওতে প্রধানমন্ত্রী আছে", "এই ভিডিওতে প্রধানমন্ত্রী নেই"),
    ("bn", "ঢাকায় ভূমিকম্প হয়েছে", "ঢাকায় ভূমিকম্প হয়নি"),
    # dezelfde zin met de samengestelde য় (U+09DF), zoals in een derde van het corpus
    ("bn", "ঢাকায় ভূমিকম্প \u09b9\u09df\u09c7\u099b\u09c7", "ঢাকায় ভূমিকম্প \u09b9\u09df\u09a8\u09bf"),
    ("si", "මෙම එන්නතේ චිප් එකක් ඇත", "මෙම එන්නතේ චිප් එකක් නැත"),
    ("si", "මෙය සත්‍ය වේ", "මෙය සත්‍ය නොවේ"),
])
def test_a_negation_pair_is_another_claim_in_each_south_asian_language(taal, claim, ontkend):
    assert _negation_variant(claim, taal, controleer=False) == ontkend


def _corpus(conn, taal, teksten):
    for i, tekst in enumerate(teksten):
        claim_id = f"{taal}-{i}"
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)", (claim_id, tekst, taal))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'Fact Crescendo', 'onwaar', 'False', ?, '2024-01-01', ?)",
                     (claim_id, f"https://tamil.factcrescendo.com/{claim_id}", taal))
        save_text_fingerprint(conn, claim_id, NEP(tekst))
    conn.commit()


def test_negation_pairs_are_added_beside_the_existing_pairs_and_only_once():
    """Additief, zoals #25.1: de bestaande paren blijven, zodat eerdere runs
    te herleiden zijn. Een tweede ronde in dezelfde taal wordt geweigerd."""
    conn = connect(":memory:")
    init_schema(conn)
    _corpus(conn, "ta", [f"செய்தி எண் {i} இணையத்தில் வைரலாக உள்ளது" for i in range(6)] + ["வேறு ஒரு கூற்று"])
    save_test_pair(conn, TestPair(claim_id="ta-0", is_same=True, provenance="origineel", language="ta",
                                  fingerprint=NEP("செய்தி எண் 0 இணையத்தில் வைரலாக உள்ளது")))
    conn.commit()
    aantallen = voeg_ontkenningsparen_toe(conn, NEP, ["ta"], per_taal=3, rng_seed=1)
    assert aantallen == {"ta": 3}
    paren = load_test_pairs(conn)
    nieuw = [p for p in paren if p.provenance == "ontkenning"]
    assert len(nieuw) == 3 and all(not p.is_same and p.language == "ta" for p in nieuw)
    assert "ta-0" not in {p.claim_id for p in nieuw}      # een claim met paren blijft onaangeraakt
    assert [p.provenance for p in paren if p.claim_id == "ta-0"] == ["origineel"]
    with pytest.raises(ValueError, match="ontkenningsparen"):
        voeg_ontkenningsparen_toe(conn, NEP, ["ta"], per_taal=3, rng_seed=1)


# --- Stap 2: de wachter (relation._NEGATIE) --------------------------------

@pytest.mark.parametrize("taal, tekst", [
    ("ta", "இந்த வீடியோ இணையத்தில் வைரலாக இல்லை"),
    ("ta", "அமைச்சர் கைது செய்யப்படவில்லை"),                 # achtervoegsel
    ("ta", "இது உண்மை அல்ல"),
    ("ta", "அவர் இனி வர மாட்டார்"),
    ("te", "ఈ వీడియో సోషల్ మీడియాలో లేదు"),
    ("te", "హైదరాబాద్‌లో భూకంపం జరగలేదు"),                    # achtervoegsel
    ("te", "ఇది నిజం కాదు"),
    ("te", "ఆధారం లేని వార్త"),
    ("ml", "ഈ മരുന്നിന് പാർശ്വഫലങ്ങൾ ഇല്ല"),
    ("ml", "അദ്ദേഹം അത് ചെയ്തില്ല"),                          # achtervoegsel
    ("ml", "ഇത് സത്യം അല്ല"),
    ("kn", "ಈ ಲಸಿಕೆಯಲ್ಲಿ ಚಿಪ್ ಇಲ್ಲ"),
    ("kn", "ಲಾಕ್‌ಡೌನ್ ಜಾರಿ ಆಗಿಲ್ಲ"),                          # achtervoegsel
    ("kn", "ಇದು ಸತ್ಯ ಅಲ್ಲ"),
    ("bn", "এই ভিডিওতে প্রধানমন্ত্রী নেই"),
    ("bn", "ঢাকায় ভূমিকম্প হয়নি"),  # হয়নি, য + nukta
    ("bn", "ঢাকায় ভূমিকম্প হয়নি"),        # হয়নি, samengesteld
    ("bn", "তিনি এই কাজ করেননি"),
    ("bn", "এটা সত্য না"),
    ("as", "এইটো খবৰ সঁচা নহয়"),
    ("si", "මෙම එන්නතේ චිප් එකක් නැත"),
    ("si", "මෙය සත්‍ය නොවේ"),
    ("si", "ඔහු එය නොකළේය"),                                    # voorvoegsel
    ("pa", "ਇਹ ਵੀਡੀਓ ਸੱਚੀ ਨਹੀਂ ਹੈ"),
    ("km", "វីដេអូនេះមិនពិតទេ"),
    ("km", "គ្មានភស្តុតាងទេ"),
])
def test_the_guard_sees_a_negation_in_every_south_asian_language(taal, tekst):
    from doublecheck.relation import extract_negations

    assert extract_negations(tekst), (taal, tekst)


@pytest.mark.parametrize("taal, tekst", [
    ("ta", "அவர் அல்லது அவள் வந்தார்"),         # அல்லது = of
    ("ta", "புதிய இல்லம் திறக்கப்பட்டது"),       # இல்லம் = huis
    ("ta", "மாட்டு வண்டி ஊர்வலம்"),              # மாட்டு = koe
    ("te", "ఇది నిజమా లేదా అబద్ధమా"),           # లేదా = of
    ("ml", "ജില്ലാ കളക്ടർ ഉത്തരവിട്ടു"),          # ജില്ല = district
    ("ml", "അല്ലെങ്കിൽ നാളെ വരും"),               # അല്ലെങ്കിൽ = anders
    ("ml", "അല്ലാഹുവിന്റെ നാമത്തിൽ"),            # Allah
    ("ml", "നല്ല വാർത്ത"),                        # നല്ല = goed
    ("kn", "ಜಿಲ್ಲೆಯ ಆಸ್ಪತ್ರೆ"),                   # ಜಿಲ್ಲೆ = district
    ("kn", "ಅಲ್ಲದೆ ಇನ್ನೊಂದು ವಿಷಯ"),             # ಅಲ್ಲದೆ = bovendien
    ("kn", "ಎಲ್ಲ ಜನರು ಬಂದರು"),                   # ಎಲ್ಲ = alle
    ("bn", "পানি খাওয়া জরুরি"),                 # পানি = water
    ("bn", "আমি জানি"),                          # জানি = ik weet
    ("bn", "নানা রকম খাবার"),                     # নানা = allerlei
    ("si", "නොවැම්බර් මාසයේ උත්සවය"),            # november
    ("pa", "ਉਸ ਦੇ ਨਾਲ ਗਿਆ"),                      # ਨਾਲ = met
    ("km", "ខែមីនា ឆ្នាំនេះ"),                     # មីនា = maart
])
def test_lookalike_words_are_not_negations(taal, tekst):
    from doublecheck.relation import extract_negations

    assert extract_negations(tekst) == frozenset(), (taal, tekst)
