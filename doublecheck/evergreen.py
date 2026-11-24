"""De evergreen-meting (PLAN #27.2a): welke verhalen komen over de jaren terug?

Het inzicht van de PO: de meeste checks zijn na een paar jaar niet meer
relevant, maar een deel zijn evergreens die steeds opnieuw verpakt terugkomen
(biolabs in Oekraïne en dan in Georgië, de NAVO-uitbreiding). Per claimcluster
komt bijna niets terug; een verhaal leeft een niveau hoger.

De meting verbindt claims in de index waarvan de vingerafdrukken vanaf een
drempel op elkaar lijken; de samenhangende delen zijn verhaalgroepen. Een
groep met checks in minstens drie kalenderjaren is een evergreen. Per
evergreen ook de kant van het oordeel per jaar, om te zien of die verschuift
(zoals bij het lab in Wuhan). Alles uit de eigen database, lokaal; er gaat
niets naar buiten.

Een groep op gelijkenis is een benadering van een verhaal: binnen een groep
kunnen verschillende beweringen staan, dus een verschuivend oordeel is een
aanwijzing, geen vaststelling.

    python -m doublecheck.evergreen
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

MIN_JAREN = 3
KETTING = 1000
_KANT = {"onwaar": "rood", "misleidend": "rood", "onwaar-of-misleidend": "rood", "waar": "groen",
         "deels-waar": "midden", "omstreden": "omstreden", "onbewezen": "onbewezen"}


def verhaalgroepen(matrix: np.ndarray, drempel: float, *, blok: int = 1024) -> np.ndarray:
    """Groepnummer per rij: rijen die vanaf `drempel` op elkaar lijken zijn
    verbonden, en verbonden is samenhangend. In blokken, zodat de volle
    gelijkenismatrix nooit in het geheugen staat."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(matrix)
    rijen, kolommen = [], []
    for begin in range(0, n, blok):
        gelijkenis = matrix[begin:begin + blok] @ matrix.T
        r, k = np.nonzero(gelijkenis >= drempel)
        r = r + begin
        boven = k > r
        rijen.append(r[boven])
        kolommen.append(k[boven])
    r = np.concatenate(rijen) if rijen else np.empty(0, dtype=np.int64)
    k = np.concatenate(kolommen) if kolommen else np.empty(0, dtype=np.int64)
    graaf = coo_matrix((np.ones(len(r), dtype=np.int8), (r, k)), shape=(n, n))
    _, labels = connected_components(graaf, directed=False)
    return labels


def jaren(datums) -> set[str]:
    """De kalenderjaren met een geldige reviewdatum (#21.4: geen 1970, geen 2924)."""
    from doublecheck.datums import geldige_review_datum

    return {geldig[:4] for geldig in (geldige_review_datum(d or "") for d in datums) if geldig}


def is_evergreen(jaren_: set[str], minimaal: int = MIN_JAREN) -> bool:
    return len(jaren_) >= minimaal


def kant_per_jaar(checks) -> dict[str, str]:
    """(jaar, genormaliseerd oordeel) naar de kant van de labelklasse per jaar;
    een jaar zonder kant (satire, geen oordeel) valt weg. Een oordeel dat niet
    te normaliseren was ("onbekend") zegt hier niets en telt niet mee; de
    labelregel zelf blijft die van het label."""
    from doublecheck.verdicts import labelklasse

    per_jaar: dict[str, list[str]] = {}
    for jaar, oordeel in checks:
        if oordeel != "onbekend":
            per_jaar.setdefault(jaar, []).append(oordeel)
    uit = {}
    for jaar, oordelen in per_jaar.items():
        kant = _KANT.get(labelklasse(oordelen))
        if kant:
            uit[jaar] = kant
    return uit


def verschuift(kanten: dict[str, str]) -> bool:
    return len(set(kanten.values())) > 1


def main() -> None:  # noqa: C901
    import argparse
    import os

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.datums import geldige_review_datum
    from doublecheck.search import _tekstmatrix
    from doublecheck.storage import connect
    from doublecheck.toelating import register, staat_aan

    parser = argparse.ArgumentParser(description="De evergreen-meting (#27.2a)")
    parser.add_argument("--drempels", default="0.80,0.85")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--uit", default="data/evergreen")
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)

    config = load_config()
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    ids, matrix = _tekstmatrix(conn, config.model_versions.text_embedding)   # alleen de index (B28)
    index = {claim_id: i for i, claim_id in enumerate(ids)}
    tekst_van = {c: t for c, t in conn.execute("SELECT claim_id, canonical_text FROM claim") if c in index}
    from doublecheck.evidence import _host

    aan, hosts = staat_aan(conn), register()
    checks: dict[str, list[tuple[str, str, str]]] = {}
    for claim_id, oordeel, datum, taal, url in conn.execute(
            "SELECT claim_id, verdict_normalized, review_date, language, url FROM factcheck"):
        if claim_id in index and (not aan or (_host(url) or "") in hosts):
            checks.setdefault(claim_id, []).append((geldige_review_datum(datum or "")[:4], oordeel, taal))
    alle_checks = sum(len(v) for v in checks.values())
    print(f"{len(ids)} claims in de index, {alle_checks} checks van toegelaten uitgevers", flush=True)

    voorbeelden = {"biolabs": ("biolab", "biological lab", "biological laborator", "biolaborator"),
                   "NAVO-uitbreiding": ("nato expansion", "nato enlargement", "expand eastward", "eastward expansion",
                                        "not one inch"),
                   "lab in Wuhan": ("wuhan lab", "lab in wuhan", "wuhan institute of virology",
                                    "laboratory in wuhan", "lab leak")}
    uit = Path(args.uit)
    uit.mkdir(parents=True, exist_ok=True)
    for drempel in [float(d) for d in args.drempels.split(",")]:
        labels = verhaalgroepen(matrix, drempel)
        leden: dict[int, list[str]] = {}
        for claim_id, label in zip(ids, labels):
            leden.setdefault(int(label), []).append(claim_id)
        groottes = Counter(len(v) for v in leden.values())
        ketting = {g: v for g, v in leden.items() if len(v) > KETTING}
        groepen = []
        for g, claims in leden.items():
            cs = [c for claim_id in claims for c in checks.get(claim_id, [])]
            js = {j for j, _, _ in cs if j}
            kanten = kant_per_jaar([(j, o) for j, o, _ in cs if j])
            groepen.append({"groep": g, "claims": len(claims), "checks": len(cs), "jaren": sorted(js),
                            "talen": sorted({t for _, _, t in cs if t}), "kanten": kanten,
                            "verschuift": verschuift(kanten), "ketting": g in ketting,
                            "voorbeeld": [tekst_van[c][:160] for c in claims[:3]]})
        evergreen = [x for x in groepen if is_evergreen(set(x["jaren"])) and not x["ketting"]]
        twee = [x for x in groepen if len(x["jaren"]) == 2 and not x["ketting"]]
        claims_eg = sum(x["claims"] for x in evergreen)
        checks_eg = sum(x["checks"] for x in evergreen)
        print(f"\ndrempel {drempel}: {len(groepen)} groepen · groottes 1: {groottes[1]}, 2-9: "
              f"{sum(n for s, n in groottes.items() if 2 <= s <= 9)}, 10-99: "
              f"{sum(n for s, n in groottes.items() if 10 <= s <= 99)}, 100+: "
              f"{sum(n for s, n in groottes.items() if s >= 100)}"
              + (f" · kettingen boven {KETTING}: {[len(v) for v in ketting.values()]}" if ketting else ""))
        print(f"  evergreens (3+ jaren): {len(evergreen)} groepen, {claims_eg} claims ({claims_eg / len(ids):.1%}),"
              f" {checks_eg} checks ({checks_eg / alle_checks:.1%}); twee jaren: {len(twee)} groepen")
        print(f"  waarvan met een verschuivende kant: {sum(x['verschuift'] for x in evergreen)}")
        for naam, woorden in voorbeelden.items():
            raak = [x for x in groepen if any(any(w in v.lower() for w in woorden) for v in x["voorbeeld"])]
            raak_claims = [c for c, t in tekst_van.items() if any(w in t.lower() for w in woorden)]
            in_eg = sum(1 for c in raak_claims if any(c in leden[x["groep"]] for x in evergreen))
            print(f"  toets {naam}: {len(raak_claims)} claims met het trefwoord, {in_eg} daarvan in een evergreen")
        evergreen.sort(key=lambda x: (-len(x["jaren"]), -x["checks"]))
        (uit / f"evergreens-{drempel}.json").write_text(json.dumps(evergreen, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
        print(f"  de evergreens staan in {uit / f'evergreens-{drempel}.json'}")


if __name__ == "__main__":
    main()
