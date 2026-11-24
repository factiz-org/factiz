"""Import uit de CC BY-feed (PLAN.md #14.5, B13).

De Fact Check Tools API verbiedt onder Google APIs ToS §5 het bouwen van
databases, herdistribueren én afgeleide werken — precies wat we drie maanden
hebben gedaan (PROTOCOL.md §11.5). De Data Commons-feed draagt CC BY en mag dat
allemaal wel.

Twee dingen die deze bron anders maakt dan de API:

- **geen taalveld.** 0 van de 98.997 records draagt `inLanguage` (BENCHMARK.md
  §33a). De taal komt daarom uit `corpus_taal`, per claim. Een eerdere versie
  telde een meerderheid per uitgever; dat was een krukje voor een detector die
  zes talen kende, en het kon meertalige uitgevers niet splitsen (§35);
- **herkomst moet vastgelegd.** Zonder dat kunnen we bij het vrijgeven niet
  scheiden wat wél en niet mee mag (15.3). Dat is een mechanische eis, geen
  administratieve.
"""

import pytest

from doublecheck.feed import HERDISTRIBUEERBAAR, parse_feed

def _item(claim, uitgever, url, datum="2024-03-01", oordeel="Onjuist"):
    return {
        "@type": "DataFeedItem",
        "item": [{
            "@type": "ClaimReview",
            "claimReviewed": claim,
            "author": {"@type": "Organization", "name": uitgever,
                       "url": f"https://{url.split('/')[2]}/"},
            "url": url,
            "datePublished": datum,
            "reviewRating": {"@type": "Rating", "alternateName": oordeel},
        }],
    }


FEED = {"@type": "DataFeed", "dataFeedElement": [
    _item("Het vaccin bevat microchips om mensen te volgen en te sturen",
          "Nieuwscheckers", "https://nieuwscheckers.nl/a"),
    _item("De zeespiegel daalt al tien jaar wereldwijd volgens onderzoek",
          "Nieuwscheckers", "https://nieuwscheckers.nl/b"),
    _item("Windmolens veroorzaken kanker bij omwonenden in de provincie",
          "Nieuwscheckers", "https://nieuwscheckers.nl/c"),
    _item("The vaccine contains microchips to track and control the people",
          "PolitiFact", "https://politifact.com/a"),
    _item("Scientists have proven that the sea level is falling worldwide",
          "PolitiFact", "https://politifact.com/b"),
    _item("The government has approved a new housing law this week",
          "PolitiFact", "https://politifact.com/c"),
]}


def test_feed_parses_into_the_same_shape_as_the_api():
    """Hergebruik van `RawClaim` houdt één importpad in stand."""
    claims = parse_feed(FEED)

    assert len(claims) == 6
    eerste = claims[0]
    assert eerste.text.startswith("Het vaccin")
    assert eerste.factchecks[0].publisher == "Nieuwscheckers"
    assert eerste.factchecks[0].url == "https://nieuwscheckers.nl/a"
    assert eerste.factchecks[0].verdict_original == "Onjuist"


def test_records_without_claim_text_are_skipped():
    """6.945 van de 98.997 feedrecords missen `claimReviewed` (§33a)."""
    feed = {"dataFeedElement": [
        _item(None, "Nieuwscheckers", "https://nieuwscheckers.nl/leeg"),
        _item("Een echte bewering over vaccins en microchips", "Nieuwscheckers",
              "https://nieuwscheckers.nl/echt"),
    ]}
    assert len(parse_feed(feed)) == 1


def test_language_is_detected_per_claim():
    """Per claim, niet per uitgever — dat splitst meertalige uitgevers (§35)."""
    claims = parse_feed(FEED)
    per_url = {c.factchecks[0].url: c.factchecks[0].language for c in claims}

    assert per_url["https://nieuwscheckers.nl/a"] == "nl"
    assert per_url["https://politifact.com/a"] == "en"


def test_a_multilingual_publisher_is_split_not_averaged():
    """Fact Crescendo publiceert in en/hi/ml/km/bn; een meerderheid kon dat niet."""
    feed = {"dataFeedElement": [
        _item("Het vaccin bevat microchips om mensen te volgen en te sturen",
              "Fact Crescendo", "https://factcrescendo.com/a"),
        _item("The vaccine contains microchips to track and control the people",
              "Fact Crescendo", "https://factcrescendo.com/b"),
    ]}
    talen = {c.factchecks[0].url: c.factchecks[0].language for c in parse_feed(feed)}
    assert talen["https://factcrescendo.com/a"] == "nl"
    assert talen["https://factcrescendo.com/b"] == "en"


def test_unrecognisable_text_becomes_undetermined():
    """Twijfel versoepelt nooit — ook hier niet."""
    feed = {"dataFeedElement": [
        _item("Pfizer 2024", "Onbekend", "https://onbekend.nl/a")]}
    assert parse_feed(feed)[0].factchecks[0].language == "und"


def test_the_licence_of_this_source_is_recorded_as_redistributable():
    """15.3 moet mechanisch kunnen scheiden wat mee mag in de repo."""
    assert HERDISTRIBUEERBAAR == "datacommons-ccby"


# --- herkomst vastleggen (15.3) ---

@pytest.fixture
def conn():
    from doublecheck.storage import connect, init_schema

    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


class _NepFingerprinter:
    model_version = "testmodel-v1"

    def __call__(self, tekst):
        import numpy as np

        from doublecheck.embedding import TextFingerprint

        vector = np.ones(3, dtype=np.float32) / np.sqrt(3)
        vector.setflags(write=False)
        return TextFingerprint(vector=vector, model_version="testmodel-v1")


def test_imported_checks_carry_their_source(conn):
    from doublecheck.ingest import import_claims

    import_claims(conn, parse_feed(FEED), fingerprinter=_NepFingerprinter(),
                  source=HERDISTRIBUEERBAAR)

    bronnen = {r[0] for r in conn.execute("SELECT DISTINCT source FROM factcheck")}
    assert bronnen == {HERDISTRIBUEERBAAR}


def test_redistributable_claims_exclude_api_bound_material(conn):
    """Een claim mag alleen mee als élke check erachter herdistribueerbaar is."""
    from doublecheck.feed import API_GEBONDEN, redistribueerbare_claims
    from doublecheck.ingest import import_claims

    import_claims(conn, parse_feed(FEED), fingerprinter=_NepFingerprinter(),
                  source=HERDISTRIBUEERBAAR)
    # Dezelfde bewering, maar óók gezien via de API-route.
    gemengd = parse_feed({"dataFeedElement": [
        _item("Het vaccin bevat microchips om mensen te volgen en te sturen",
              "Andere Checker", "https://ander.nl/x")]})
    import_claims(conn, gemengd, fingerprinter=_NepFingerprinter(),
                  source=API_GEBONDEN)

    vrij = redistribueerbare_claims(conn)
    teksten = {
        r[0] for r in conn.execute(
            f"SELECT canonical_text FROM claim WHERE claim_id IN "
            f"({','.join('?' * len(vrij))})", tuple(vrij))
    } if vrij else set()
    assert not any(t.startswith("Het vaccin bevat microchips") for t in teksten)
    assert any(t.startswith("De zeespiegel daalt") for t in teksten)


def test_source_is_required_so_it_cannot_be_forgotten(conn):
    """Een herkomstloze import is precies de fout die 15.3 moet uitsluiten."""
    from doublecheck.ingest import import_claims

    with pytest.raises(TypeError):
        import_claims(conn, parse_feed(FEED), fingerprinter=_NepFingerprinter())


def test_import_can_defer_fingerprinting(conn):
    """Bulkimport embedt niet per claim; `reindex` doet het gebatcht (#14.4).

    Stuk voor stuk embedden kost 28 seconden per duizend claims — bijna een uur
    voor de hele feed. Gebatcht is dat een fractie, en het herindexeerpad bestaat
    al voor precies dit doel.
    """
    from doublecheck.ingest import import_claims

    rapport = import_claims(conn, parse_feed(FEED), source=HERDISTRIBUEERBAAR,
                            uitgesteld=True)

    assert rapport.accepted_claims == 6
    assert rapport.new_fingerprints == 0
    assert conn.execute("SELECT count(*) FROM fingerprint").fetchone()[0] == 0


def test_deferred_import_is_completed_by_reindex(conn):
    """Na uitstel moet herindexeren de index alsnog compleet maken."""
    from doublecheck.ingest import import_claims
    from doublecheck.reindex import reindex_text

    import_claims(conn, parse_feed(FEED), source=HERDISTRIBUEERBAAR,
                  uitgesteld=True)
    rapport = reindex_text(conn, "testmodel-v1",
                           fingerprinter=lambda teksten, versie: [
                               _NepFingerprinter()(t) for t in teksten])

    assert rapport.nieuwe_fingerprints == 6
