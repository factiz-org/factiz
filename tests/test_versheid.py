"""Versheidscadans (PLAN.md #22.2): het geheugen mag niet stilstaan.

Het corpus is een geheugen van wat factcheckers vonden, en een geheugen dat
niet bijgevuld wordt veroudert stil — de nieuwste check bleef vijf weken op
2026-08-29 staan terwijl de feed doorliep. Drie dingen worden hier mechanisch
vastgehouden:

- **Bijvullen is idempotent**: dezelfde feed twee keer importeren voegt niets
  toe — claims dedupliceren op claim_id, checks op (claim_id, url). Zonder
  die eigenschap is een cadans een vermenigvuldiger.
- **Elke run wordt vastgelegd** (wanneer, waarvandaan, hoeveel erbij, hoeveel
  geweigerd): een geheugen dat stiekem groeit is net zo onbetrouwbaar als een
  dat stilstaat.
- **`--vernieuw` haalt de feed écht opnieuw op**: de cache-hergebruik van
  #15.3 ("feed al aanwezig") is voor de schone kloon een feature en voor de
  cadans een val — zonder deze vlag ververste er nooit iets.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from doublecheck.bootstrap import FEED_URL, bootstrap
from doublecheck.embedding import TextFingerprint
from doublecheck.feed import HERDISTRIBUEERBAAR, parse_feed
from doublecheck.ingest import import_claims
from doublecheck.storage import (
    connect,
    importruns,
    init_schema,
    registreer_importrun,
)

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
    """Batchvariant, voor `bootstrap`/`reindex`."""
    uit = []
    for tekst in teksten:
        richting = np.zeros(len(CLAIMS), dtype=np.float32)
        richting[_AS[tekst]] = 1.0
        uit.append(TextFingerprint(richting, model_version))
    return uit


class _NepFingerprinter:
    """Per-tekstvariant, voor `import_claims`."""

    model_version = "testmodel-v1"

    def __call__(self, tekst):
        (fp,) = _nep_fingerprints([tekst], self.model_version)
        return fp


@pytest.fixture
def nep_download(tmp_path):
    pogingen = []

    def download(url, doel, voortgang=None):
        pogingen.append(url)
        doel.write_text(json.dumps(_feed()), encoding="utf-8")
        return doel

    download.pogingen = pogingen
    return download


def test_a_second_import_of_the_same_feed_adds_nothing():
    """Idempotentie is de voorwaarde voor een cadans: claims dedupliceren op
    claim_id, checks op (claim_id, url)."""
    conn = connect(":memory:")
    init_schema(conn)
    claims = parse_feed(_feed())

    eerste = import_claims(conn, claims, fingerprinter=_NepFingerprinter(),
                           source=HERDISTRIBUEERBAAR)
    assert eerste.accepted_claims == len(CLAIMS)

    tweede = import_claims(conn, claims, fingerprinter=_NepFingerprinter(),
                           source=HERDISTRIBUEERBAAR)
    assert tweede.accepted_claims == 0
    assert tweede.accepted_factchecks == 0
    assert tweede.new_fingerprints == 0
    assert tweede.existing_claims == len(CLAIMS)
    assert tweede.duplicate_factchecks == len(CLAIMS)


def test_an_import_run_is_recorded_with_its_counts():
    conn = connect(":memory:")
    init_schema(conn)
    claims = parse_feed(_feed())
    rapport = import_claims(conn, claims, fingerprinter=_NepFingerprinter(),
                            source=HERDISTRIBUEERBAAR)
    registreer_importrun(
        conn, gestart_op="2026-10-04T12:00:00+00:00", bron="proef-feed",
        rapport=rapport, nieuwe_fingerprints=rapport.new_fingerprints,
    )
    (run,) = importruns(conn)
    assert run["bron"] == "proef-feed"
    assert run["gestart_op"] == "2026-10-04T12:00:00+00:00"
    assert run["nieuwe_claims"] == len(CLAIMS)
    assert run["nieuwe_factchecks"] == len(CLAIMS)
    assert run["nieuwe_fingerprints"] == len(CLAIMS)
    assert run["geweigerd"] == 0


def test_bootstrap_records_every_run_including_the_empty_second(tmp_path, nep_download):
    """De cadans in het klein: run één vult, run twee (zelfde feed) voegt
    niets toe — en béíde staan in het logboek."""
    db = str(tmp_path / "corpus.db")
    for _ in range(2):
        bootstrap(db=db, cache=tmp_path / "feed.json", downloader=nep_download,
                  fingerprinter=_nep_fingerprints)
    conn = connect(db)
    runs = importruns(conn)
    assert len(runs) == 2
    nieuwste, eerste = runs  # nieuwste eerst
    assert eerste["nieuwe_claims"] == len(CLAIMS)
    assert nieuwste["nieuwe_claims"] == 0
    assert nieuwste["bron"] == FEED_URL
    conn.close()


def test_vernieuw_refetches_the_feed(tmp_path, nep_download):
    """Zonder `vernieuw` wint de cache (#15.3); mét wordt de feed opnieuw
    opgehaald — anders ververst een cadans nooit iets."""
    db = str(tmp_path / "corpus.db")
    cache = tmp_path / "feed.json"
    bootstrap(db=db, cache=cache, downloader=nep_download,
              fingerprinter=_nep_fingerprints)
    assert len(nep_download.pogingen) == 1

    bootstrap(db=db, cache=cache, downloader=nep_download,
              fingerprinter=_nep_fingerprints)
    assert len(nep_download.pogingen) == 1, "cache hoort hergebruikt"

    bootstrap(db=db, cache=cache, downloader=nep_download,
              fingerprinter=_nep_fingerprints, vernieuw=True)
    assert len(nep_download.pogingen) == 2, "vernieuw hoort opnieuw op te halen"
