"""Waar zit het retrievalplafond van de batchcontrole (PLAN #21.7, stap 1)?

De batchcontrole kijkt per zin naar alleen de beste kandidaat, en alleen boven
de screeningpoort; op de 21.3-proefset vindt ze 2 van de 28 documenten die hun
claim beweren (§96). Deze meting zegt waar dat aan ligt. Voor elk van die 28:
de beste rang en de beste gelijkenis van de doelclaim (of een lid van haar
cluster) over vier soorten eenheden (zinnen, vensters van twee en drie zinnen,
het hele document), met zoeken op betekenis (de productie-index, zoals de
resolver zoekt) en met zoeken op woorden (BM25 over de claimteksten, met de
tokens van de bge-m3-tokenizer als woorden: lokaal en voor elk schrift).

Staat de doelclaim op rang 1 maar onder de poort, dan is de poort het plafond;
staat hij niet in de top 20, dan is het de rangorde. Er wordt niets beslist:
stap 2 (de hele batchcontrole) volgt alleen voor een methode die hier de
vooraf vastgelegde grens haalt. De documentteksten blijven lokaal; alleen
rangen en tellingen gaan naar de uitvoer.

    python -m doublecheck.retrievalmeting
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import numpy as np

SOORTEN = ("zin", "venster2", "venster3", "document")
RANGEN = (1, 5, 20)
DIEPTE = 20


def eenheden(tekst: str, soort: str) -> list[str]:
    """De eenheden waarop gezocht wordt. Zinnen zoals de batchcontrole ze nu
    neemt; vensters schuiven één zin per stap over álle zinnen."""
    from doublecheck.controle import _MIN_ZINLENGTE, _zinnen

    zinnen = _zinnen(tekst)
    if soort == "zin":
        return [zin for zin in zinnen if len(zin) >= _MIN_ZINLENGTE]
    if soort == "document":
        return [tekst.strip()] if tekst.strip() else []
    breedte = {"venster2": 2, "venster3": 3}[soort]
    if len(zinnen) <= breedte:
        return [" ".join(zinnen)] if zinnen else []
    return [" ".join(zinnen[i:i + breedte]) for i in range(len(zinnen) - breedte + 1)]


class Bm25:
    """BM25 over documenten als lijsten woordnummers (k1 1,5, b 0,75).
    Een vraagwoord telt één keer; een woord dat nergens staat, vindt niets."""

    def __init__(self, documenten: list[list[int]], *, k1: float = 1.5, b: float = 0.75):
        from scipy.sparse import csr_matrix

        rijen, kolommen, waarden = [], [], []
        lengtes = np.array([len(d) for d in documenten], dtype=np.float64)
        gemiddeld = lengtes.mean() if len(lengtes) else 1.0
        df: dict[int, int] = {}
        tellingen = []
        for doc in documenten:
            tel: dict[int, int] = {}
            for woord in doc:
                tel[woord] = tel.get(woord, 0) + 1
            tellingen.append(tel)
            for woord in tel:
                df[woord] = df.get(woord, 0) + 1
        n = len(documenten)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.kolom = {w: i for i, w in enumerate(sorted(df))}
        for r, (tel, lengte) in enumerate(zip(tellingen, lengtes)):
            norm = k1 * (1 - b + b * lengte / gemiddeld)
            for woord, tf in tel.items():
                rijen.append(r)
                kolommen.append(self.kolom[woord])
                waarden.append(self.idf[woord] * tf * (k1 + 1) / (tf + norm))
        self.gewichten = csr_matrix((waarden, (rijen, kolommen)), shape=(n, max(1, len(self.kolom))))
        self.gewichten_t = self.gewichten.T.tocsr()

    def top(self, vraag: list[int], k: int) -> list[tuple[int, float]]:
        kolommen = sorted({self.kolom[w] for w in vraag if w in self.kolom})
        if not kolommen:
            return []
        scores = np.asarray(self.gewichten_t[kolommen].sum(axis=0)).ravel()
        kandidaten = np.flatnonzero(scores > 0)
        volgorde = kandidaten[np.argsort(-scores[kandidaten], kind="stable")][:k]
        return [(int(i), float(scores[i])) for i in volgorde]


def rang(kandidaten: list[str], doel: str, cluster_van: dict[str, str]) -> int | None:
    """De plaats van de doelclaim (of een lid van haar cluster), vanaf 1."""
    for plaats, claim_id in enumerate(kandidaten, 1):
        if claim_id == doel or (doel in cluster_van and cluster_van.get(claim_id) == cluster_van[doel]):
            return plaats
    return None


def telling(beste: dict[str, int | None]) -> dict[int, int]:
    return {k: sum(1 for r in beste.values() if r is not None and r <= k) for k in RANGEN}


def _beste(rangen: list[int | None]) -> int | None:
    gezien = [r for r in rangen if r is not None]
    return min(gezien) if gezien else None


def main() -> None:
    import argparse
    import os

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.embedding import _load_model, fingerprint_texts, normaliseer_voor_embedding
    from doublecheck.screeningmeting import HERMETING_215, herbouw_documenten
    from doublecheck.search import search_text
    from doublecheck.storage import connect
    from doublecheck.toelating import buiten_index

    parser = argparse.ArgumentParser(description="Het retrievalplafond van de batchcontrole (#21.7, stap 1)")
    parser.add_argument("--cache", default="data/proef213-paginas")
    parser.add_argument("--uit", default="data/retrievalmeting/stap1.json")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)

    config = load_config()
    versie = config.model_versions.text_embedding
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    docs, meta, _ = herbouw_documenten(Path(args.cache))
    vorige = json.loads(HERMETING_215.read_text(encoding="utf-8"))["bevestiging_productiepad"]
    doelen = {d: meta[d]["claim_id"] for d in set(vorige["tp"]) | set(vorige["gemist"])}
    teksten = {d: t for d, t in docs if d in doelen}
    cluster_van = {c: k for c, k in conn.execute(
        "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL")}
    leden: dict[str, set[str]] = {}
    for claim_id, cluster in cluster_van.items():
        leden.setdefault(cluster, set()).add(claim_id)
    print(f"{len(teksten)} van de {len(doelen)} documenten die hun claim beweren", flush=True)

    # De vectoren van elke doelclaim en haar clusterleden, voor de beste gelijkenis.
    doelvectoren: dict[str, np.ndarray] = {}
    for doel in set(doelen.values()):
        groep = leden.get(cluster_van.get(doel), set()) | {doel}
        rijen = [np.frombuffer(p, dtype=np.float32) for (p,) in conn.execute(
            f"SELECT payload FROM fingerprint WHERE kind = 'text' AND model_version = ?"
            f" AND claim_id IN ({','.join('?' for _ in groep)})", (versie, *sorted(groep)))]
        doelvectoren[doel] = np.vstack(rijen) if rijen else np.empty((0, 1024), dtype=np.float32)

    # BM25 over de claimteksten in de index, met de woorden van de bge-m3-tokenizer.
    tokenizer = _load_model(versie).tokenizer
    buiten = buiten_index(conn)
    claims = [(c, t) for c, t in conn.execute("SELECT claim_id, canonical_text FROM claim") if c not in buiten]
    claim_ids = [c for c, _ in claims]

    def woorden(tekst: str) -> list[int]:
        return tokenizer(normaliseer_voor_embedding(tekst), add_special_tokens=False,
                         truncation=False)["input_ids"]

    index = Bm25([woorden(t) for _, t in claims])
    print(f"BM25 over {len(claims)} claims", flush=True)

    uitslag: dict[str, dict] = {}
    for doc_id, tekst in sorted(teksten.items()):
        doel = doelen[doc_id]
        per_doc = {"doel": doel}
        for soort in SOORTEN:
            delen = eenheden(tekst, soort)
            prints = fingerprint_texts(delen, versie) if delen else []
            dicht = [rang([k.claim_id for k in search_text(conn, fp, DIEPTE, varianten=config.varianten.in_resolver)],
                          doel, cluster_van) for fp in prints]
            woord = [rang([claim_ids[i] for i, _ in index.top(woorden(deel), DIEPTE)], doel, cluster_van)
                     for deel in delen]
            gelijkenis = max((float((doelvectoren[doel] @ fp.vector).max()) for fp in prints
                              if doelvectoren[doel].size), default=None)
            per_doc[soort] = {"dicht": _beste(dicht), "bm25": _beste(woord),
                              "hybride": _beste([r for r in dicht + woord]),
                              "gelijkenis": None if gelijkenis is None else round(gelijkenis, 4)}
        uitslag[doc_id] = per_doc
        print(f"  {doc_id}: " + " · ".join(
            f"{s} {per_doc[s]['dicht']}/{per_doc[s]['bm25']} {per_doc[s]['gelijkenis']}" for s in SOORTEN),
            flush=True)

    print(f"\n{'eenheid':<10}{'methode':<9}" + "".join(f"{'@' + str(k):>6}" for k in RANGEN)
          + f"{'gelijkenis (mediaan)':>22}")
    for soort in SOORTEN:
        sims = [u[soort]["gelijkenis"] for u in uitslag.values() if u[soort]["gelijkenis"] is not None]
        for methode in ("dicht", "bm25", "hybride"):
            tel = telling({d: u[soort][methode] for d, u in uitslag.items()})
            mediaan = f"{statistics.median(sims):.3f}" if sims and methode == "dicht" else ""
            print(f"{soort:<10}{methode:<9}" + "".join(f"{tel[k]:>6}" for k in RANGEN) + f"{mediaan:>22}")
    poort = config.thresholds.screening_poort
    nu = sum(1 for u in uitslag.values() if u["zin"]["dicht"] == 1 and (u["zin"]["gelijkenis"] or 0) >= poort)
    print(f"\nbenadering van nu (zin, rang 1, beste gelijkenis vanaf {poort}): {nu} van {len(uitslag)}")
    pad = Path(args.uit)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(uitslag, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"per document: {pad}")


if __name__ == "__main__":
    main()
