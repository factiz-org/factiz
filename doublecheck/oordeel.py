"""De meetset en een eerste oordelaar voor laag 3 (#29.1, #29.2, B25).

Uitsluitend meting: niets hiervan bereikt een gebruiker voordat de poort per
taal en soort claim gehaald is (B25, DR2).

- **Meetset**: claims met een eensgezind, bekend oordeel (onbekend en satire
  doen niet mee), gescheiden in de tijd op de datum van de eerste check. De
  oordelaar leert alleen van vóór de scheiding en wordt getoetst op erna.
- **Eerste oordelaar** (referentie): de k dichtstbijzijnde bekende claims. Hij
  oordeelt alleen als alle k boven de drempel liggen en het eens zijn; anders
  zwijgt hij. Dat is het eenvoudigste dat een "eigen oordeel" kan heten, en dus
  de lat waar sterkere oordelaars overheen moeten.
- **Eerlijk rapporteren**: precisie naast het basisniveau (factcheckers kiezen
  vooral claims die onwaar blijken, 70–89% per jaar), en apart voor "al bekend"
  (gelijkenis ≥ de matchdrempel: dat is laag 1, geen eigen oordeel) en "nieuw"
  (daar gaat laag 3 over).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Rij:
    claim_id: str
    datum: str
    taal: str
    oordeel: str
    vector: np.ndarray


@dataclass(frozen=True)
class Uitkomst:
    voorspelling: str | None
    hoogste_gelijkenis: float


def meetset(conn: sqlite3.Connection, model_version: str, *, scheiding: str) -> tuple[list[Rij], list[Rij]]:
    rijen = conn.execute(
        """
        SELECT c.claim_id, c.language, min(f.review_date) AS datum,
               count(DISTINCT f.verdict_normalized) AS soorten, max(f.verdict_normalized) AS oordeel,
               fp.payload
        FROM claim c
        JOIN factcheck f ON f.claim_id = c.claim_id
        JOIN fingerprint fp ON fp.claim_id = c.claim_id AND fp.kind = 'text' AND fp.model_version = ?
        WHERE f.review_date <> '' AND f.verdict_normalized NOT IN ('onbekend', 'satire')
        GROUP BY c.claim_id
        HAVING soorten = 1
        ORDER BY c.claim_id
        """,
        (model_version,),
    ).fetchall()
    leer, toets = [], []
    for claim_id, taal, datum, _, oordeel, payload in rijen:
        rij = Rij(claim_id, datum, taal, oordeel, np.frombuffer(payload, dtype=np.float32))
        (leer if datum < scheiding else toets).append(rij)
    return leer, toets


def knn_oordeel(toets: list[Rij], leer: list[Rij], *, k: int, drempel: float, blok: int = 512) -> list[Uitkomst]:
    if not toets or not leer:
        return [Uitkomst(None, 0.0) for _ in toets]
    matrix = np.vstack([r.vector for r in leer])
    labels = np.array([r.oordeel for r in leer])
    uit: list[Uitkomst] = []
    for start in range(0, len(toets), blok):
        deel = np.vstack([r.vector for r in toets[start:start + blok]])
        sims = deel @ matrix.T
        kk = min(k, sims.shape[1])
        top = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
        for rij_nr in range(len(deel)):
            idx = top[rij_nr]
            s = sims[rij_nr, idx]
            hoogste = float(sims[rij_nr].max())
            if len(idx) < k or s.min() < drempel:
                uit.append(Uitkomst(None, hoogste))
                continue
            oordelen = set(labels[idx])
            uit.append(Uitkomst(oordelen.pop() if len(oordelen) == 1 else None, hoogste))
        del sims
    return uit


def _maten(paren: list[tuple[Rij, Uitkomst]]) -> dict:
    n = len(paren)
    onwaar = sum(r.oordeel == "onwaar" for r, _ in paren)
    gezegd = [(r, u) for r, u in paren if u.voorspelling is not None]
    gezegd_onwaar = [(r, u) for r, u in gezegd if u.voorspelling == "onwaar"]
    goed_onwaar = sum(r.oordeel == "onwaar" for r, _ in gezegd_onwaar)
    goed = sum(r.oordeel == u.voorspelling for r, u in gezegd)
    return {
        "n": n,
        "basis_onwaar": onwaar / n if n else 0.0,
        "dekking": len(gezegd) / n if n else 0.0,
        "precisie": goed / len(gezegd) if gezegd else 0.0,
        "n_onwaar_gezegd": len(gezegd_onwaar),
        "precisie_onwaar": goed_onwaar / len(gezegd_onwaar) if gezegd_onwaar else 0.0,
    }


def meet(toets: list[Rij], uitkomsten: list[Uitkomst], *, nieuw_onder: float) -> dict:
    paren = list(zip(toets, uitkomsten))
    return {
        "alle": _maten(paren),
        "bekend": _maten([p for p in paren if p[1].hoogste_gelijkenis >= nieuw_onder]),
        "nieuw": _maten([p for p in paren if p[1].hoogste_gelijkenis < nieuw_onder]),
    }


def main() -> None:
    import argparse
    import os

    from threadpoolctl import threadpool_limits

    from doublecheck.benchmark import upper_bound_95
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Eerste oordelaar voor laag 3 meten (#29.2)")
    parser.add_argument("--scheiding", default="2025-07-01")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)

    config = load_config()
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    leer, toets = meetset(conn, config.model_versions.text_embedding, scheiding=args.scheiding)
    print(f"meetset: leren {len(leer)} claims (vóór {args.scheiding}), toetsen {len(toets)} (erna)")
    print(f"matchdrempel {config.thresholds.text_match}: 'bekend' = laag 1, 'nieuw' = laag 3\n")
    print(f"{'k':>2} {'drempel':>7} | {'deel':6} {'n':>5} {'basis':>6} {'dekking':>7} {'gezegd onwaar':>13} {'precisie':>8} {'ondergrens*':>11}")
    for k in (1, 3, 5, 10):
        for drempel in (0.70, 0.80, 0.85, 0.90):
            m = meet(toets, knn_oordeel(toets, leer, k=k, drempel=drempel), nieuw_onder=config.thresholds.text_match)
            for deel in ("nieuw", "bekend"):
                d = m[deel]
                fout = d["n_onwaar_gezegd"] - round(d["precisie_onwaar"] * d["n_onwaar_gezegd"])
                ondergrens = 1 - upper_bound_95(fout, d["n_onwaar_gezegd"]) if d["n_onwaar_gezegd"] else 0.0
                print(f"{k:>2} {drempel:>7.2f} | {deel:6} {d['n']:>5} {d['basis_onwaar']:>6.1%} {d['dekking']:>7.1%}"
                      f" {d['n_onwaar_gezegd']:>13} {d['precisie_onwaar']:>8.1%} {ondergrens:>11.1%}")
    print("\n* ondergrens 95% op de precisie van 'onwaar' (Clopper-Pearson); de poort uit B25 is 99%.")


if __name__ == "__main__":
    main()
