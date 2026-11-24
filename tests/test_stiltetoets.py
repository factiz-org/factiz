"""De stiltetoets: gewone berichten die nooit `matched` mogen geven (PLAN.md #28.6 g)."""

import gzip
import json

import pytest

from doublecheck import stiltetoets as st
from doublecheck.config import load_config

ENGELS = "The council voted on Tuesday to extend the opening hours of the public library during the exam period."
HINDI = "तमिलनाडु में भारी बारिश के कारण कई जिलों में स्कूल बंद रहे और लोगों से घरों में रहने की अपील की गई है।"


def test_a_piece_is_post_sized_without_links_and_mostly_words():
    document = "\n".join([
        "Home",                                                     # te kort
        ENGELS,
        "Read more at https://example.org/library-hours and share it with your friends today.",
        "x " * 200,                                                 # te lang
        "12.30 14.45 16.00 18.15 20.30 22.45 | 12.30 14.45 16.00 18.15 20.30 22.45 | 12.30",
    ])
    assert st.knip(document) == [ENGELS]


def test_a_devanagari_paragraph_is_not_lost_to_its_vowel_signs():
    """Klinkertekens zijn combinerende tekens, geen letters voor `isalpha`;
    wie alleen letters telt, gooit Hindi weg (het schriftpaneel, §17a)."""
    zonder_ruimte = [c for c in HINDI if not c.isspace()]
    assert sum(c.isalpha() for c in zonder_ruimte) / len(zonder_ruimte) < st.MIN_LETTERS
    assert st.knip(HINDI) == [HINDI]


def test_at_most_three_pieces_come_from_one_document():
    alineas = [f"{ENGELS} Paragraph number {i} adds a little more context here." for i in range(5)]
    assert len(st.knip("\n".join(alineas))) == st.PER_DOCUMENT


def test_pieces_are_unique_and_stop_at_the_quota():
    documenten = [ENGELS, ENGELS, HINDI, ENGELS.replace("Tuesday", "Monday"), ENGELS.replace("Tuesday", "Friday")]
    gezien: set[str] = set()
    assert st.stukken(documenten, 3, gezien) == [ENGELS, HINDI, ENGELS.replace("Tuesday", "Monday")]


def test_the_quota_follows_the_corpus_with_a_floor():
    quota = st.quota({"en": 478, "nl": 24, "si": 1}, totaal=1000, vloer=50)
    assert quota == {"en": round(1000 * 478 / 503), "nl": 50, "si": 50}


def test_the_prefilter_sits_below_every_threshold_that_can_give_a_hit():
    """Wat onder de voorselectie blijft, gaat niet door de resolver; dat mag
    alleen als het daar per constructie nooit `matched` of `related` had
    gekregen."""
    drempels = load_config().thresholds
    grens = st.ondergrens(drempels)
    assert grens < min(drempels.text_related, drempels.text_match, drempels.text_match_crosslingual)


def test_documents_are_read_from_the_compressed_lines(tmp_path):
    pad = tmp_path / "c4-nl-validation.json.gz"
    with gzip.open(pad, "wt", encoding="utf-8") as f:
        for tekst in ("eerste document", "tweede document"):
            f.write(json.dumps({"text": tekst, "url": "https://example.org", "timestamp": "2020"}) + "\n")
    assert list(st.lees_documenten(pad)) == ["eerste document", "tweede document"]


def _treffer(stuk_id, taal, categorie):
    return {"stuk_id": stuk_id, "taal": taal, "categorie": categorie}


def test_counting_refuses_a_match_without_a_label():
    treffers = [_treffer("nl-000001", "nl", "matched")]
    with pytest.raises(st.Weigering):
        st.uitslag(treffers, {}, {"nl": 1000})


def test_a_rightful_match_is_not_a_false_alarm_and_the_bound_follows_n():
    treffers = [
        _treffer("en-000001", "en", "matched"),   # het stuk doet echt de gecheckte bewering
        _treffer("en-000002", "en", "matched"),
        _treffer("en-000003", "en", "related"),
    ]
    labels = {"en-000001": "terecht", "en-000002": "vals"}
    uit = st.uitslag(treffers, labels, {"en": 200_000, "nl": 100_000})
    assert uit["totaal"]["n"] == 300_000
    assert (uit["totaal"]["matched"], uit["totaal"]["terecht"], uit["totaal"]["vals"]) == (2, 1, 1)
    assert uit["totaal"]["related"] == 1
    assert uit["per_taal"]["nl"]["vals"] == 0
    # Nul valse in 100.000: de bovengrens is ongeveer 3/n.
    assert 2.9e-5 < uit["per_taal"]["nl"]["bovengrens"] < 3.1e-5


def test_the_read_only_database_feeds_the_prefilter(tmp_path):
    """De meting opent de database alleen-lezend; de zoekmatrix leest
    kolommen op naam, dus de verbinding moet rijen met namen geven."""
    import numpy as np

    from doublecheck.embedding import TextFingerprint
    from doublecheck.storage import connect, init_schema, save_text_fingerprint

    pad = tmp_path / "klein.db"
    conn = connect(pad)
    init_schema(conn)
    v = np.zeros(4, dtype=np.float32); v[0] = 1.0
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', 'een bewering', 'nl')")
    save_text_fingerprint(conn, "c1", TextFingerprint(vector=v, model_version="m"))
    conn.commit()
    conn.close()
    lees = st.lees_db(pad)
    hoogste, boven = st.voorselectie(lees, np.array([v, -v]), "m", 0.5)
    assert list(boven) == [0] and hoogste[0] > 0.99


def test_a_fresh_sample_skips_the_files_of_the_last_round_and_falls_back_to_training_data():
    """#25.32: een verse steekproef neemt per taal één ongebruikt bestand;
    is de enige validatieshard al op, dan de eerste trainingsshard."""
    namen = ["en/c4-validation.00000-of-00008.json.gz", "en/c4-validation.00001-of-00008.json.gz",
             "en/c4-validation.00002-of-00008.json.gz", "en/c4-train.00000-of-01024.json.gz",
             "multilingual/c4-te-validation.tfrecord-00000-of-00001.json.gz",
             "multilingual/c4-te.tfrecord-00000-of-00128.json.gz",
             "multilingual/c4-te.tfrecord-00001-of-00128.json.gz"]
    oud = {"en/c4-validation.00000-of-00008.json.gz", "en/c4-validation.00001-of-00008.json.gz",
           "multilingual/c4-te-validation.tfrecord-00000-of-00001.json.gz"}
    assert st.kies_bestanden(namen, "en", overslaan=oud, max_bestanden=1) == ["en/c4-validation.00002-of-00008.json.gz"]
    assert st.kies_bestanden(namen, "te", overslaan=oud, max_bestanden=1) == [
        "multilingual/c4-te.tfrecord-00000-of-00128.json.gz"]
    # Zonder verse ronde: alle validatieshards, zoals de eerste keer.
    assert st.kies_bestanden(namen, "en") == namen[:3]


def test_a_fresh_sample_never_repeats_a_piece_from_the_last_round():
    gezien = {ENGELS}
    assert st.stukken([ENGELS, HINDI], 5, gezien) == [HINDI]
