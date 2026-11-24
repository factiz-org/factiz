"""Van schone kloon naar werkend corpus, met één commando (PLAN.md #15.3, B13).

De repo levert geen database. Dat is geen omissie maar de kern van B13: het
corpus is CC BY-materiaal van andermans uitgevers, en de code is van ons. Wat
de repo wél moet leveren is de weg ernaartoe — anders is "open source" een
motor zonder brandstof en zonder tankadres.

Twee dingen worden hier mechanisch vastgehouden. De bootstrap **vertelt eerst
wat hij gaat doen** — 190 MB downloaden en tienduizenden claims embedden is
geen verrassing die je achteraf uitlegt. En elke geïmporteerde regel **draagt
zijn herkomst**, zodat een uitgave die API-gebonden materiaal bevat te
betrappen is in plaats van te vertrouwen.
"""

import json
import pathlib
import sqlite3
import subprocess

import numpy as np
import pytest

from doublecheck.bootstrap import (
    FEED_URL,
    HerkomstRapport,
    bootstrap,
    herkomstrapport,
    plan,
)
from doublecheck.embedding import TextFingerprint
from doublecheck.feed import API_GEBONDEN, HERDISTRIBUEERBAAR
from doublecheck.storage import connect, init_schema

WORTEL = pathlib.Path(__file__).resolve().parent.parent

CLAIMS = [
    ("De zeespiegel daalt al tien jaar wereldwijd", "Nieuwscheckers", "nieuwscheckers.nl"),
    ("Minister Jansen is vanochtend afgetreden", "Nieuwscheckers", "nieuwscheckers.nl"),
    ("Vaccines contain microchips for tracking people", "Full Fact", "fullfact.org"),
    ("The moon landing was filmed in a studio", "Snopes", "snopes.com"),
]


def _feed() -> dict:
    return {
        "dataFeedElement": [
            {
                "item": {
                    "claimReviewed": tekst,
                    "url": f"https://{site}/check/{nummer}",
                    "datePublished": "2024-03-14",
                    "author": {"name": uitgever, "url": f"https://{site}"},
                    "reviewRating": {"alternateName": "Onjuist"},
                }
            }
            for nummer, (tekst, uitgever, site) in enumerate(CLAIMS)
        ]
    }


_AS = {tekst: nummer for nummer, (tekst, _, _) in enumerate(CLAIMS)}


def _nep_fingerprints(teksten, model_version):
    """Eén eigen as per claim: deterministisch, en niets clustert per ongeluk."""
    uit = []
    for tekst in teksten:
        richting = np.zeros(len(CLAIMS), dtype=np.float32)
        richting[_AS[tekst]] = 1.0
        uit.append(TextFingerprint(richting, model_version))
    return uit


@pytest.fixture
def nep_download(tmp_path):
    """Schrijft de minifeed alsof hij zojuist opgehaald is; telt de pogingen."""
    pogingen = []

    def download(url, doel, voortgang=None):
        pogingen.append(url)
        doel.write_text(json.dumps(_feed()), encoding="utf-8")
        return doel

    download.pogingen = pogingen
    return download


def test_bootstrap_says_what_it_will_cost_before_it_starts(tmp_path):
    """Ramen ná afloop is precies hoe een machine 76 minuten op 273% CPU gaat."""
    db = tmp_path / "corpus.db"
    cache = tmp_path / "feed.json"
    regels = plan(
        db=str(db),
        cache=cache,
        url=FEED_URL,
        max_claims=None,
        groottelezer=lambda url: 199_471_513,
    )
    tekst = "\n".join(regels)
    assert "190" in tekst, "downloadomvang wordt niet genoemd"
    assert "MB" in tekst
    assert FEED_URL in tekst, "de bron wordt niet genoemd"
    assert not db.exists(), "plannen mag niets aanmaken"
    assert not cache.exists()


def test_bootstrap_turns_a_clean_clone_into_a_working_corpus(tmp_path, nep_download):
    db = tmp_path / "corpus.db"
    rapport = bootstrap(
        db=str(db),
        cache=tmp_path / "feed.json",
        downloader=nep_download,
        fingerprinter=_nep_fingerprints,
    )
    assert rapport.claims == len(CLAIMS), rapport
    assert rapport.fingerprints == len(CLAIMS)
    assert rapport.clusters >= 1

    conn = connect(str(db))
    aantal = conn.execute("SELECT count(*) FROM fingerprint WHERE kind='text'").fetchone()[0]
    assert aantal == len(CLAIMS), "corpus zonder index is geen werkend corpus"
    conn.close()


def test_a_corpus_built_from_scratch_carries_the_publisher_whitelist(tmp_path, nep_download):
    """B28: anders zou een schone kloon stil elke host toelaten."""
    from doublecheck.toelating import staat_aan

    db = tmp_path / "corpus.db"
    bootstrap(db=str(db), cache=tmp_path / "feed.json", downloader=nep_download,
              fingerprinter=_nep_fingerprints)
    conn = connect(str(db))
    assert staat_aan(conn)
    conn.close()


def test_bootstrap_records_ccby_provenance_on_everything_it_imports(tmp_path, nep_download):
    db = tmp_path / "corpus.db"
    bootstrap(
        db=str(db),
        cache=tmp_path / "feed.json",
        downloader=nep_download,
        fingerprinter=_nep_fingerprints,
    )
    conn = connect(str(db))
    bronnen = {rij[0] for rij in conn.execute("SELECT DISTINCT source FROM factcheck")}
    conn.close()
    assert bronnen == {HERDISTRIBUEERBAAR}


def test_bootstrap_reuses_a_cached_feed_instead_of_fetching_it_again(tmp_path, nep_download):
    cache = tmp_path / "feed.json"
    for keer in range(2):
        bootstrap(
            db=str(tmp_path / f"corpus{keer}.db"),
            cache=cache,
            downloader=nep_download,
            fingerprinter=_nep_fingerprints,
        )
    assert len(nep_download.pogingen) == 1, "190 MB wordt twee keer opgehaald"


def test_a_corpus_holding_api_bound_records_is_flagged_not_released(tmp_path):
    """`source` bestaat om dit te kunnen betrappen, niet om het te vertrouwen."""
    db = tmp_path / "gemengd.db"
    conn = connect(str(db))
    init_schema(conn)
    for nummer, bron in enumerate((HERDISTRIBUEERBAAR, HERDISTRIBUEERBAAR, API_GEBONDEN)):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
            (f"c{nummer}", f"Een bewering nummer {nummer}"),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source)"
            " VALUES (?, 'Uitgever', 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl', ?)",
            (f"c{nummer}", f"https://example.org/{nummer}", bron),
        )
    conn.commit()

    rapport = herkomstrapport(conn)
    conn.close()
    assert isinstance(rapport, HerkomstRapport)
    assert rapport.totaal == 3
    assert rapport.herdistribueerbaar == 2
    assert rapport.gebonden == 1
    assert not rapport.mag_uitgegeven_worden
    assert API_GEBONDEN in rapport.toelichting()


def test_a_clean_corpus_may_be_released(tmp_path):
    db = tmp_path / "schoon.db"
    conn = connect(str(db))
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language)"
                 " VALUES ('c1', 'Een bewering', 'nl')")
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source)"
        " VALUES ('c1', 'Uitgever', 'onwaar', 'Onjuist', 'https://example.org/1',"
        " '2024-01-01', 'nl', ?)", (HERDISTRIBUEERBAAR,))
    conn.commit()
    rapport = herkomstrapport(conn)
    conn.close()
    assert rapport.mag_uitgegeven_worden


def test_a_corpus_can_never_be_committed_by_accident():
    """Corpus én opgehaalde feed horen niet in de repo; dat mag niet van
    oplettendheid afhangen. De feed is 190 MB en het standaard cachepad ligt
    ín de werkmap — precies de vorm waarin eerder een SQLite-journaal
    meegecommit werd (#14.4-nasleep)."""
    for naam in ("doublecheck.db", "corpus.db", "iets/anders.db",
                 "data/datacommons-claimreview.json", "data/wat-dan-ook"):
        uit = subprocess.run(
            ["git", "check-ignore", "-q", naam], cwd=WORTEL, capture_output=True
        )
        assert uit.returncode == 0, f"{naam} zou gecommit kunnen worden"


def test_the_heavy_step_reports_progress(tmp_path, nep_download):
    """Embedden duurt op het volle corpus ruim tien minuten.

    De eerste versie meldde voortgang bij `gedaan % 5000 == 0`, terwijl
    `reindex_text` in batches van 256 werkt — 5.000 is daar geen veelvoud van,
    dus de regel drukte nóóit af. Tien minuten stilte in precies het commando
    dat "zeg eerst wat het kost" als uitgangspunt heeft (#15.3).
    """
    regels = []
    bootstrap(
        db=str(tmp_path / "corpus.db"),
        cache=tmp_path / "feed.json",
        downloader=nep_download,
        fingerprinter=_nep_fingerprints,
        voortgang=regels.append,
        meldkorrel=2,
    )
    embedregels = [r for r in regels if "embedden" in r]
    assert embedregels, f"geen voortgang tijdens het embedden; wel: {regels}"
    assert any("/" in r for r in embedregels), embedregels


def test_a_source_that_may_not_be_redistributed_blocks_a_release(tmp_path):
    """E7.S1-AC2: een attributie uit een bron die niet herverdeeld mag worden
    (Community Notes, X Developer Agreement) maakt de database even gebonden
    als een check uit de API."""
    from doublecheck import attributie as at

    conn = connect(str(tmp_path / "met-notes.db"))
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', 'Een bewering', 'nl')")
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
        " review_date, language, source) VALUES ('c1', 'Uitgever', 'onwaar', 'Onjuist',"
        " 'https://example.org/1', '2024-01-01', 'nl', ?)", (HERDISTRIBUEERBAAR,))
    at.registreer_bron(conn, bron_id="communitynotes", naam="Community Notes (X)", soort="platform",
                       licentie="X Developer Agreement and Policy", attributietekst="Community Notes",
                       url="https://communitynotes.x.com", herverdeelbaar=False)
    assert herkomstrapport(conn).mag_uitgegeven_worden      # geregistreerd, nog geen record
    x = at.registreer_actor(conn, naam="X", soort="platform")
    at.voeg_attributie(conn, claim_id="c1", actor_id=x, bron_id="communitynotes", datum="2025-03-15",
                       url="https://x.com/i/birdwatch/n/1", niveau="waargenomen")
    rapport = herkomstrapport(conn)
    conn.close()
    assert not rapport.mag_uitgegeven_worden
    assert "Community Notes (X)" in rapport.toelichting()
    assert "Uitgeefbaar" not in rapport.toelichting()       # niet allebei tegelijk


def test_a_cc_by_source_from_the_register_does_not_block_a_release(tmp_path):
    """EUvsDisinfo is CC BY en staat als herverdeelbaar in het register; zijn
    checks (`source` "euvsdisinfo:…") zijn geen API-records. `--herkomst`
    blokkeerde de uitgave er sinds #24.6 ten onrechte op."""
    from doublecheck import attributie as at

    conn = connect(str(tmp_path / "met-euvsdisinfo.db"))
    init_schema(conn)
    at.registreer_bron(conn, bron_id="euvsdisinfo", naam="EUvsDisinfo", soort="overheid", licentie="CC BY 4.0",
                       attributietekst="EUvsDisinfo", url="https://euvsdisinfo.eu", herverdeelbaar=True)
    for nummer, bron in enumerate((HERDISTRIBUEERBAAR, "euvsdisinfo:mendeley-yhdtkszvgp-v3")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')",
                     (f"c{nummer}", f"Een bewering {nummer}"))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language, source) VALUES (?, 'U', 'onwaar', 'False', ?, '2024-01-01', 'en', ?)",
                     (f"c{nummer}", f"https://example.org/{nummer}", bron))
    conn.commit()
    rapport = herkomstrapport(conn)
    assert rapport.mag_uitgegeven_worden, rapport.toelichting()
    assert rapport.gebonden == 0
    conn.execute("UPDATE bron SET herverdeelbaar = 0 WHERE bron_id = 'euvsdisinfo'")
    rapport = herkomstrapport(conn)
    assert not rapport.mag_uitgegeven_worden
    assert "factchecktools-api" not in rapport.toelichting()     # de echte bron genoemd, niet de API
