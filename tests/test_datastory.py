"""De datastory "desinformatie sterft niet, ze verhuist" (PLAN #25.14d c, #22.6).

De cijferbijlage zei dat de meetlogica in de repository stond; er stonden
alleen de regels in woorden. Nu is het een module, zodat elk getal in de
blog en de pers opnieuw te berekenen is, ook na een modelwissel die de
clusters verandert.
"""

import pytest

from doublecheck import datastory as ds
from doublecheck.storage import connect, init_schema


def _claim(conn, cid, tekst, taal, cluster, datums):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, ?, ?)",
                 (cid, tekst, taal, cluster))
    for i, datum in enumerate(datums):
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original,"
                     " url, review_date, language) VALUES (?, 'R', 'onwaar', 'Onwaar', ?, ?, ?)",
                     (cid, f"https://r.org/{cid}/{i}", datum, taal))


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    lang = "Een bewering die lang genoeg is om mee te tellen"
    # Meertalig en een zombie van ruim vier jaar.
    _claim(c, "a1", lang, "nl", "k1", ["2019-01-01"])
    _claim(c, "a2", lang + " (en)", "en", "k1", ["2023-06-01"])
    # Eén taal, anderhalf jaar.
    _claim(c, "b1", lang + " b", "en", "k2", ["2020-01-01"])
    _claim(c, "b2", lang + " b2", "en", "k2", ["2021-07-01"])
    # Rommel: een korte claimtekst sluit het hele cluster uit (C1).
    _claim(c, "c1", "Facebook", "en", "k3", ["2015-01-01"])
    _claim(c, "c2", lang + " c", "es", "k3", ["2022-01-01"])
    # Een ongeldige en een toekomstige datum tellen niet mee.
    _claim(c, "d1", lang + " d", "fr", "k4", ["2024-01-01", "binnenkort", "2999-01-01"])
    _claim(c, "d2", lang + " d2", "fr", "k4", ["2024-03-01"])
    # Een losse claim is geen cluster.
    _claim(c, "e1", lang + " e", "de", None, ["2018-01-01"])
    c.commit()
    yield c
    c.close()


def test_only_clusters_whose_every_claim_is_long_enough_count(conn):
    uitslag = ds.bereken(conn, vandaag="2026-10-11")
    assert uitslag.clusters == 3
    assert uitslag.geweerd_c1 == 1


def test_multilingual_and_zombie_clusters_are_counted_with_their_gap(conn):
    uitslag = ds.bereken(conn, vandaag="2026-10-11")
    assert uitslag.meertalig == 1
    assert uitslag.zombies == 2
    assert uitslag.zombies_twee_jaar == 1
    assert uitslag.per_kloof == {"1-2 jaar": 1, "2-4 jaar": 0, "4+ jaar": 1}


def test_an_invalid_or_future_date_never_stretches_the_gap(conn):
    uitslag = ds.bereken(conn, vandaag="2026-10-11")
    assert uitslag.kloof_per_cluster["k4"] == 60


def test_an_editorial_example_is_found_with_its_languages_and_gap(conn):
    gevonden = ds.zoek_voorbeeld(conn, ["mee te tellen (en)"], vandaag="2026-10-11")
    assert gevonden["talen"] == ["en", "nl"]
    assert gevonden["kloof_dagen"] == 1612
