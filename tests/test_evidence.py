import numpy as np
import pytest

from doublecheck.categorize import Category, categorize
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.evidence import build_evidence
from doublecheck.search import search_text
from doublecheck.seed import seed_database
from doublecheck.storage import connect, init_schema, save_text_fingerprint


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    seed_database(conn)
    yield conn
    conn.close()


def test_matched_contains_publisher_and_date(conn):
    # Volledige keten tot aan de respons: fingerprint in de index, identieke
    # query → matched, en dan de bewijstoestand van de gematchte claim.
    richting = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    save_text_fingerprint(
        conn, "seed-zeespiegel", TextFingerprint(richting, "testmodel-v1")
    )
    kandidaten = search_text(conn, TextFingerprint(richting, "testmodel-v1"))
    uitkomst = categorize(kandidaten[0].similarity, load_config().thresholds)
    assert uitkomst.category == Category.MATCHED

    bewijs = build_evidence(conn, kandidaten[0].claim_id)

    assert bewijs.claim_id == "seed-zeespiegel"
    assert bewijs.canonical_text == "De zeespiegel daalt al tien jaar wereldwijd"
    assert len(bewijs.factchecks) == 1
    check = bewijs.factchecks[0]
    assert check.publisher == "Nieuwscheckers"
    assert check.verdict_normalized == "onwaar"
    assert check.verdict_original == "Onjuist"
    assert check.url == "https://nieuwscheckers.nl/factcheck/zeespiegel-daalt"
    assert check.review_date == "2024-03-14"
    assert check.language == "nl"


def test_multiple_checks_give_count_and_oldest_date(conn):
    bewijs = build_evidence(conn, "seed-vaccin-microchip-nl", register={}, onbekend="telt-mee")

    assert bewijs.check_count == 2
    assert bewijs.publisher_count == 2
    assert bewijs.oldest_date == "2023-08-02"
    assert bewijs.languages == ("nl",)
    assert {check.publisher for check in bewijs.factchecks} == {
        "Nieuwscheckers",
        "AFP Factcheck Nederland",
    }


def test_unknown_claim_fails_loudly(conn):
    with pytest.raises(LookupError):
        build_evidence(conn, "bestaat-niet")


# --- Uitgeversidentiteit (PLAN.md #17.5) ------------------------------------


def test_one_publisher_written_two_ways_counts_once():
    """`FACTLY` en `FACTLY ` zijn één uitgever.

    Het corpus telt 137 groepen namen die alleen in kast of spaties verschillen
    — `FACTLY`, `FACTLY  `, `Factly`, `factly` — en 2.172 factchecks met
    spaties aan de rand. Dat telde mee als onafhankelijke bevestiging, terwijl
    DR7 juist over onafhankelijkheid gaat: het cijfer stond op 677 en hoort
    655 te zijn (§47).
    """
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language)"
                 " VALUES ('c1', 'Een bewering', 'nl')")
    for nummer, uitgever in enumerate(("FACTLY", "FACTLY ", "factly", "Nieuwscheckers")):
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source)"
            " VALUES ('c1', ?, 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl',"
            " 'datacommons-ccby')",
            (uitgever, f"https://example.org/{nummer}"),
        )
    conn.commit()

    bewijs = build_evidence(conn, "c1", register={}, onbekend="telt-mee")
    assert bewijs.check_count == 4
    assert bewijs.publisher_count == 2, "drie schrijfwijzen van FACTLY zijn één uitgever"
    conn.close()


def _bewijs_met(conn, checks):
    from doublecheck.storage import init_schema
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language)"
                 " VALUES ('c1', 'Een bewering', 'nl')")
    for nummer, (uitgever, url) in enumerate(checks):
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source)"
            " VALUES ('c1', ?, 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl',"
            " 'datacommons-ccby')", (uitgever, url))
    conn.commit()


def test_a_claimant_url_in_the_author_field_is_not_a_second_publisher():
    """ClaimReview's `author` bevat soms de URL van het bericht dat gecheckt
    werd in plaats van de checker. Van de 230 zulke velden wijst het `url`-veld
    er 111 naar pesacheck.org — dat is PesaCheck, niet honderd uitgevers (§48).
    """
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("PesaCheck", "https://pesacheck.org/hoax-a"),
        ("https://www.facebook.com/groups/1/posts/2", "https://pesacheck.org/hoax-b"),
    ])
    bewijs = build_evidence(conn, "c1", register={}, onbekend="telt-mee")
    assert bewijs.check_count == 2
    assert bewijs.publisher_count == 1, "beide checks staan bij PesaCheck"
    conn.close()


def test_two_genuinely_different_publishers_still_count_twice():
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("PesaCheck", "https://pesacheck.org/hoax-a"),
        ("Africa Check", "https://africacheck.org/fact-b"),
    ])
    assert build_evidence(conn, "c1", register={}, onbekend="telt-mee").publisher_count == 2
    conn.close()


def test_publisher_identity_survives_every_script():
    """Een sleutel die niet-Latijnse tekens wegstreept, maakt van elke
    Cyrillische uitgever dezelfde uitgever. Bij het bouwen van deze regel
    smolten `Вокс Чек`, `Вячеслав Вареня` en 107 andere namen tot één (§48)."""
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("Вокс Чек", "https://voxcheck.org/a"),
        ("Доброзайм", "https://dobrozaim.example/b"),
        ("المرصد الفلسطيني", "https://tahaqaq.ps/c"),
    ])
    assert build_evidence(conn, "c1", register={}, onbekend="telt-mee").publisher_count == 3
    conn.close()


def test_the_same_name_written_with_other_punctuation_counts_once():
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("El Detector / Univision Noticias", "https://univision.com/a"),
        ("El Detector/ Univision Noticias", "https://univision.com/b"),
        ("Pesa Check", "https://pesacheck.org/c"),
        ("PesaCheck", "https://pesacheck.org/d"),
    ])
    assert build_evidence(conn, "c1", register={}, onbekend="telt-mee").publisher_count == 2
    conn.close()


def test_the_publisher_key_keeps_combining_marks():
    """`\\w` lijkt Unicode-breed maar laat Mn- en Mc-tekens vallen.

    Daardoor verminkte `क्विंट हिंदी` tot `कवटहद` — 102 namen geraakt, twee
    echte botsingen (§48). Indische en Arabische namen moeten heel blijven.
    """
    from doublecheck.evidence import _uitgeversleutel

    assert _uitgeversleutel("क्विंट हिंदी") == "क्विंटहिंदी"
    assert _uitgeversleutel("अमर उजाला") == "अमरउजाला"
    # Twee namen die alleen in klinkertekens verschillen blijven verschillend.
    assert _uitgeversleutel("क्विंट हिंदी") != _uitgeversleutel("क्विंट हिन्दी")
    # En leestekens en spaties verdwijnen nog steeds.
    assert _uitgeversleutel("El Detector / Univision") == _uitgeversleutel(
        "El Detector/Univision"
    )


def test_an_unknown_publisher_carries_no_consensus_in_the_strict_setting():
    """De stand die de PO koos (#17.7): wie niet in het register staat, telt
    niet mee voor DR7 — maar de check blijft wél zichtbaar (DR1)."""
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("PesaCheck", "https://pesacheck.org/hoax-a"),
        ("Een Onbekende Club", "https://nooit-vertoond.example/x"),
    ])
    bewijs = build_evidence(
        conn, "c1",
        register={"pesacheck.org": "PesaCheck"},
        onbekend="telt-niet-mee",
    )
    assert bewijs.publisher_count == 1, "de onbekende host draagt geen consensus"
    assert bewijs.check_count == 2, "maar de check wordt wél getoond"
    assert len(bewijs.factchecks) == 2
    conn.close()


def test_the_register_merges_a_newsroom_that_writes_its_name_four_ways():
    """`The Quint`, `THE QUINT`, `क्विंट हिंदी` en een eigen journalist staan
    allemaal op thequint.com — één redactie (§48b)."""
    from doublecheck.evidence import build_evidence
    from doublecheck.storage import connect

    conn = connect(":memory:")
    _bewijs_met(conn, [
        ("The Quint", "https://thequint.com/a"),
        ("THE QUINT", "https://thequint.com/b"),
        ("क्विंट हिंदी", "https://hindi.thequint.com/c"),
        ("सर्वजीत सिंह चौहान", "https://thequint.com/d"),
        ("PesaCheck", "https://pesacheck.org/e"),
    ])
    register = {
        "thequint.com": "The Quint",
        "hindi.thequint.com": "The Quint",
        "pesacheck.org": "PesaCheck",
    }
    bewijs = build_evidence(conn, "c1", register=register, onbekend="telt-niet-mee")
    assert bewijs.check_count == 5
    assert bewijs.publisher_count == 2
    conn.close()


def test_a_receipt_names_the_newsroom_behind_the_link_not_the_feed(conn):
    """#25.19 b: de feed zet soms de claimant of een journalist als uitgever
    ("Donald Trump" op politifact.com). Het bonnetje toont de redactie van de
    host; een host die niet in het register staat houdt zijn eigen naam."""
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('t1', ?, 'en')",
                 ("I have a 94% approval rating in the Republican Party",))
    for uitgever, url in (("Donald Trump", "https://www.politifact.com/factchecks/2019/jun/06/x/"),
                          ("Kleine Redactie", "https://kleine-redactie.example/check/1")):
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                     " url, review_date, language) VALUES ('t1', ?, 'onwaar', 'False', ?, '2019-06-06', 'en')",
                     (uitgever, url))
    bewijs = build_evidence(conn, "t1", register={"politifact.com": "PolitiFact"})
    assert [c.publisher for c in bewijs.factchecks] == ["PolitiFact", "Kleine Redactie"]
