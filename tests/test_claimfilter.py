"""Lokale matching voor de plug-in (PLAN #24.2, DESIGN §4b, DR3).

De filter laat het apparaat zelf herkennen of een post een bekende claim
letterlijk bevat, zonder dat er iets de deur uitgaat. Hij bevat alleen
hashes van publieke claimteksten: lidmaatschap, geen inhoud. Een treffer
zegt "het geheugen kent dit"; de bonnetjes komen pas na een klik.
"""

import json
import pathlib
import random
import string

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck import claimfilter as cf
from doublecheck.storage import connect, init_schema

WORTEL = pathlib.Path(__file__).resolve().parent.parent
VECTOREN = WORTEL / "doublecheck" / "claimfilter_vectoren.json"

CLAIMS = [
    "Vaccines have been proven to cause autism. The CDC hid the data for years.",
    "WhatsApp will charge users for sending messages",
    "Prosthetic fingers will be used to cast multiple votes in the upcoming Lok Sabha elections.",
    "ΟΙ ΕΜΒΟΛΙΑΣΜΕΝΟΙ ΠΕΘΑΙΝΟΥΝ ΣΕ ΔΥΟ ΧΡΟΝΙΑ ΑΠΟ ΤΩΡΑ ΣΥΜΦΩΝΑ ΜΕ ΤΟΝ ΟΡΓΑΝΙΣΜΟ",
    "Россия не нападала на Украину, это была специальная операция по защите мирных жителей.",
    "Yes",
]


def test_normalisation_folds_what_a_post_changes_and_nothing_else():
    n = cf.normaliseer_voor_filter
    assert n('  "WhatsApp  will\ncharge users"  ') == "whatsapp will charge users"
    assert n("«Vaccines cause autism»") == "vaccines cause autism"
    # Slot-sigma: JavaScript maakt van een slot-Σ een ς, Python een σ.
    # Beide kanten vouwen naar σ, anders breekt de pariteit op Grieks.
    assert n("ΧΡΟΝΙΑΣ") == n("χρονιας") == "χρονιασ"
    # NFKC: compatibiliteitsvormen (volle breedte, ligaturen) vallen samen.
    assert n("ＷｈａｔｓＡｐｐ") == "whatsapp"
    assert n("ﬁngers") == "fingers"


def test_every_known_claim_and_its_long_sentences_are_members():
    f = cf.bouw_filter(CLAIMS)
    for claim in CLAIMS[:5]:
        assert cf.bevat(f, claim), claim
    # Een lange zin uit een claim is zelf een sleutel: een post die alleen die
    # zin citeert, raakt de filter.
    assert cf.bevat(f, "the cdc hid the data for years")is False  # te kort (<40 tekens)
    assert cf.bevat(f, "VACCINES HAVE BEEN PROVEN TO CAUSE AUTISM.")
    assert cf.bevat(f, "  “Vaccines have been proven to cause autism.”  ")


def test_short_texts_never_enter_the_filter():
    """'Yes' en 'google' staan als claim in het corpus (rommeluitgevers); een
    post van drie letters mag nooit een label krijgen."""
    f = cf.bouw_filter(CLAIMS)
    assert not cf.bevat(f, "Yes")
    assert cf.sleutels("Yes") == []


def test_false_positive_rate_stays_near_the_design_target():
    random.seed(7)
    claims = ["".join(random.choices(string.ascii_lowercase + " ", k=60)) for _ in range(3000)]
    f = cf.bouw_filter(claims, vals_positief=1e-3)
    vreemd = ["".join(random.choices(string.ascii_lowercase + " ", k=61)) for _ in range(20000)]
    treffers = sum(cf.bevat(f, v) for v in vreemd)
    assert treffers / len(vreemd) < 3e-3, treffers


def test_the_wire_format_round_trips_and_carries_no_text():
    f = cf.bouw_filter(CLAIMS)
    draad = cf.naar_json(f)
    assert set(draad) >= {"versie", "normalisatie", "m", "k", "n", "bits"}
    terug = cf.van_json(draad)
    assert all(cf.bevat(terug, c) for c in CLAIMS[:5])
    platte = json.dumps(draad).lower()
    assert "vaccines" not in platte and "whatsapp" not in platte


def test_the_parity_vectors_are_what_the_code_computes():
    """Het contract met de JavaScript-kant (#24.3): dezelfde invoer geeft
    dezelfde genormaliseerde tekst en dezelfde bitposities. Verandert de
    normalisatie, dan breekt deze test en weet de plug-in het."""
    vectoren = json.loads(VECTOREN.read_text(encoding="utf-8"))
    # Het bestand is precies wat de generator nu maakt: niemand heeft er met
    # de hand aan gezeten, en een normalisatiewijziging vergt opnieuw genereren.
    assert vectoren == cf.pariteitsvectoren()
    assert vectoren["normalisatie"] == cf.NORMALISATIE
    assert len(vectoren["gevallen"]) >= 8
    for geval in vectoren["gevallen"]:
        if "kantsleutel" in geval:
            # #24.2c: de kantsleutel is dezelfde hash over "kant:<klasse>|<tekst>".
            sleutel = cf.kantsleutel(geval["klasse"], cf.normaliseer_voor_filter(geval["invoer"]))
            assert sleutel == geval["kantsleutel"], geval
            assert cf.posities(sleutel, vectoren["m"], vectoren["k"]) == geval["posities"]
            continue
        assert cf.normaliseer_voor_filter(geval["invoer"]) == geval["genormaliseerd"], geval
        assert cf.posities(geval["genormaliseerd"], vectoren["m"], vectoren["k"]) == geval["posities"]


@pytest.fixture
def client():
    conn = connect(":memory:")
    init_schema(conn)
    for i, tekst in enumerate(CLAIMS):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
            (f"c{i}", tekst),
        )
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_the_resolver_serves_the_filter_for_download(client):
    antwoord = client.get("/claimfilter")
    assert antwoord.status_code == 200
    f = cf.van_json(antwoord.json())
    assert cf.bevat(f, CLAIMS[1])
    assert "whatsapp" not in antwoord.text.lower()


def test_a_claim_outside_the_index_never_enters_the_filter(tmp_path):
    """B28: een vage tekst in de filter zou de plug-in elke post met
    "Something to think about." laten markeren; en een host buiten de witte
    lijst levert geen bekende claim. Ook op een bestand, waar de filter
    gecachet wordt: de toelating aanzetten moet hem verversen."""
    from doublecheck.ingest import claim_id_for_text
    from doublecheck.toelating import zet_aan

    conn = connect(tmp_path / "filter.db")
    init_schema(conn)
    rijen = [(claim_id_for_text("Something to think about."), "Something to think about.", "https://nieuwscheckers.nl/1"),
             ("winkel", "This webshop delivers every order within one single day", "https://webwinkel.example/r"),
             ("echt", CLAIMS[1], "https://nieuwscheckers.nl/2")]
    for claim_id, tekst, url in rijen:
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')", (claim_id, tekst))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'X', 'false', 'False', ?, '2024-01-01', 'en')", (claim_id, url))
    conn.commit()
    f = cf.van_json(cf.filter_voor(conn))
    assert not cf.bevat(f, "Something to think about.")
    assert cf.bevat(f, "This webshop delivers every order within one single day")
    zet_aan(conn)
    f = cf.van_json(cf.filter_voor(conn))
    assert not cf.bevat(f, "This webshop delivers every order within one single day")
    assert cf.bevat(f, CLAIMS[1])


# --- #24.2c: de kant bij een treffer op de hele tekst ------------------------------


def test_a_whole_text_hit_carries_the_side_of_its_claim():
    """Het label mag zonder netwerk de kant zeggen (PO 2026-10-14); de
    telling blijft een klik."""
    f = cf.bouw_filter(CLAIMS, klassen=[(CLAIMS[1], "misleidend")])
    assert cf.kant(f, CLAIMS[1]) == "misleidend"
    assert cf.kant(f, f'  "{CLAIMS[1].upper()}"  ') == "misleidend"


def test_a_sentence_hit_never_carries_a_side():
    """Een losse zin kan bij een andere bewering horen: neutraal tot de klik."""
    f = cf.bouw_filter(CLAIMS, klassen=[(CLAIMS[0], "onwaar")])
    post = "Vaccines have been proven to cause autism. Share this with everyone you love today."
    assert cf.bevat(f, post)
    assert cf.kant(f, post) is None
    assert cf.kant(f, CLAIMS[0]) == "onwaar"


def test_claims_sharing_a_text_with_different_sides_get_no_side():
    f = cf.bouw_filter(CLAIMS, klassen=[(CLAIMS[1], "onwaar"), (CLAIMS[1].upper(), "waar")])
    assert cf.bevat(f, CLAIMS[1]) and cf.kant(f, CLAIMS[1]) is None


def test_satire_unproven_and_no_verdict_get_no_side():
    f = cf.bouw_filter(CLAIMS, klassen=[(CLAIMS[1], "satire"), (CLAIMS[2], "onbewezen"), (CLAIMS[3], None)])
    assert {cf.kant(f, CLAIMS[i]) for i in (1, 2, 3)} == {None}


def test_the_label_class_follows_the_words_of_the_demo():
    """Dezelfde regel als `kopVoor` in de demo (B30, DESIGN §4c): een oordeel
    zonder kant telt niet mee zolang er een check mét kant is, en
    verschillende kanten zijn omstreden."""
    from doublecheck.verdicts import labelklasse

    gevallen = {
        ("onwaar",): "onwaar", ("misleidend",): "misleidend", ("onwaar", "misleidend"): "onwaar-of-misleidend",
        ("misleidend", "onbekend"): "misleidend", ("waar",): "waar", ("deels-waar",): "deels-waar",
        ("waar", "onwaar"): "omstreden", ("onwaar", "deels-waar"): "omstreden", ("satire",): "satire",
        ("onbewezen",): "onbewezen", ("onbekend",): None, ("onbekend", "onbewezen"): None,
    }
    for oordelen, verwacht in gevallen.items():
        assert labelklasse(oordelen) == verwacht, oordelen
    pagina = (WORTEL / "doublecheck" / "webui.py").read_text(encoding="utf-8")
    for woorden in ("Known to be false", "Known to be misleading", "Known to be false or misleading",
                    "Known to be true", "Partly true", "Disputed by fact-checkers"):
        assert woorden in pagina, woorden


def test_the_side_in_the_filter_is_what_the_resolver_shows(tmp_path):
    """De kant komt uit precies de checks die de resolver toont: alle
    clusterleden in de index, alleen toegelaten uitgevers (B28)."""
    from doublecheck.evidence import build_evidence
    from doublecheck.toelating import zet_aan
    from doublecheck.verdicts import labelklasse_in_tijd

    conn = connect(tmp_path / "kant.db")
    init_schema(conn)
    rijen = [("a", CLAIMS[1], "k1", "onwaar", "https://nieuwscheckers.nl/a"),
             ("b", CLAIMS[2], "k1", "waar", "https://nieuwscheckers.nl/b"),
             ("c", CLAIMS[4], "k2", "onwaar", "https://nieuwscheckers.nl/c"),
             ("d", "Een check die alleen bij een webwinkel staat en dus niet telt", "k2", "waar",
              "https://webwinkel.example/d")]
    for claim_id, tekst, cluster, oordeel, url in rijen:
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, 'en', ?)",
                     (claim_id, tekst, cluster))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'X', ?, 'x', ?, '2024-01-01', 'en')", (claim_id, oordeel, url))
    conn.commit()
    zet_aan(conn)
    klassen = cf.klassen_voor(conn)
    for claim_id in ("a", "b", "c"):
        getoond = labelklasse_in_tijd((c.verdict_normalized, c.review_date)
                                      for c in build_evidence(conn, claim_id).factchecks)[0]
        assert klassen[claim_id] == getoond, claim_id
    assert klassen["a"] == "omstreden" and klassen["c"] == "onwaar"
    f = cf.van_json(cf.filter_voor(conn))
    assert cf.kant(f, CLAIMS[1]) == "omstreden" and cf.kant(f, CLAIMS[4]) == "onwaar"


def test_an_older_filter_format_is_refused():
    draad = cf.naar_json(cf.bouw_filter(CLAIMS))
    assert draad["kanten"] == [*cf.KLASSEN, "geen"]
    with pytest.raises(ValueError):
        cf.van_json({**draad, "versie": "claimfilter-v1"})


def test_a_changed_verdict_refreshes_the_side_in_a_cached_filter(tmp_path):
    """De kant hangt aan de oordelen: een herberekend oordeel (`reindex
    --alleen-oordelen`) moet de gecachete filter verversen, niet alleen een
    nieuwe claim."""
    conn = connect(tmp_path / "ververs.db")
    init_schema(conn)
    # Vulclaims zonder check: een filter van twee sleutels is zo klein dat een
    # kantsleutel toevallig ook een andere klasse raakt, en dan zegt `kant`
    # terecht niets.
    for i in range(300):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
                     (f"vul{i}", f"Een vulclaim zonder check met nummer {i} en wat tekst"))
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('a', ?, 'en')", (CLAIMS[1],))
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES ('a', 'X', 'onwaar', 'False', 'https://x.example/a', '2024-01-01', 'en')")
    conn.commit()
    assert cf.kant(cf.van_json(cf.filter_voor(conn)), CLAIMS[1]) == "onwaar"
    conn.execute("UPDATE factcheck SET verdict_normalized = 'waar' WHERE claim_id = 'a'")
    conn.commit()
    assert cf.kant(cf.van_json(cf.filter_voor(conn)), CLAIMS[1]) == "waar"


def test_every_key_without_a_side_says_so_in_the_filter():
    """Een toevallige botsing mag nooit een kant geven aan een tekst zonder
    kant (een losse zin, satire, geen oordeel): elke sleutel draagt precies
    één kantsleutel, ook "geen". Raakt een botsing een tweede, dan zijn het er
    twee en blijft het label neutraal. Gemeten vóór deze regel: 50 van de
    80.612 zulke teksten kregen toch een kant (#24.2c)."""
    f = cf.bouw_filter(CLAIMS, klassen=[(CLAIMS[0], "onwaar"), (CLAIMS[2], "satire")])
    zinnen = [s for tekst in CLAIMS for s in cf.sleutels(tekst)[1:]]
    assert zinnen
    for sleutel in zinnen + [cf.normaliseer_voor_filter(CLAIMS[2]), cf.normaliseer_voor_filter(CLAIMS[3])]:
        assert cf._bevat_sleutel(f, cf.kantsleutel("geen", sleutel)), sleutel
    assert not cf._bevat_sleutel(f, cf.kantsleutel("geen", cf.normaliseer_voor_filter(CLAIMS[0])))
