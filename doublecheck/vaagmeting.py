"""Vage claimteksten opsporen (PLAN.md #25.26).

Zeven van de twaalf valse vlaggen op mC4 (BENCHMARK §97) kwamen door
claimteksten die niets beweren: "Something to think about.", een dankzegging,
"Miraculous moment is going viral". De check erachter is echt, maar in de
ClaimReview staat het onderschrift van de post in plaats van de bewering, en
elke gewone zin die erop lijkt raakt hem.

Zo'n claim verraadt zich doordat hij veel ongerelateerde tekst aantrekt.
Vastgelegd vóór het meten (PLAN #25.26): voor elk van de 289.880 stukken uit
mC4 de dichtstbijzijnde claim, over claims en varianten; een *trekker* is een
claim die voor minstens `MINIMUM` stukken de dichtstbijzijnde is met een
gelijkenis van minstens `DREMPEL`. Elke trekker met de hand gelabeld: vaag of
bewering. Een populaire echte bewering trekt ook stukken aan, en is dan niet
vaag; daarom beslist het label, niet het aantal.

Wat vaag is, gaat uit de zoekindex (#25.28, B28): `toepassen` zet de labels
*vaag* in `doublecheck/vage_claims.json`, met hun tekst. De meting hoort bij
elke corpusuitbreiding (RELEASES.md): de vage claims van vorige keer zitten
dan niet meer in de matrix, dus wat bovenkomt is nieuw en heeft nog geen
label.

    python -m doublecheck.vaagmeting meten|tellen|toepassen
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

MAP = Path("data/stiltetoets")
LABELS = Path("docs/steekproeven/25.26-vage-claims.json")
DREMPEL = 0.70
MINIMUM = 5


class Weigering(Exception):
    pass


def dichtste(stukken: np.ndarray, claims: np.ndarray, claim_ids: list[str], varianten: np.ndarray,
             variant_claims: list[str], *, blok: int = 128) -> tuple[list[str], np.ndarray]:
    """Per stuk de dichtstbijzijnde claim (een variant telt als haar claim)
    en de gelijkenis."""
    eigenaar = list(claim_ids) + list(variant_claims)
    beste = np.empty(len(stukken), dtype=np.int64)
    hoogste = np.full(len(stukken), -1.0, dtype=np.float32)
    for start in range(0, len(stukken), blok):
        deel = stukken[start:start + blok]
        for verschuiving, m in ((0, claims), (len(claim_ids), varianten)):
            if not len(m):
                continue
            s = deel @ m.T
            j = s.argmax(axis=1)
            w = s[np.arange(len(deel)), j]
            beter = w > hoogste[start:start + blok]
            hoogste[start:start + blok][beter] = w[beter]
            beste[start:start + blok][beter] = j[beter] + verschuiving
    return [eigenaar[i] for i in beste], hoogste


def trekkers(ids: list[str], gelijkenis: np.ndarray, *, drempel: float = DREMPEL,
             minimum: int = MINIMUM) -> dict[str, int]:
    tel = Counter(i for i, g in zip(ids, gelijkenis) if g >= drempel)
    return {c: n for c, n in tel.most_common() if n >= minimum}


def uitslag(trekkers_: dict[str, int], labels: dict[str, str], vlaggen: dict) -> dict:
    """Hoeveel trekkers vaag zijn, en hoeveel valse vlaggen (§97) bij een vage
    claim horen. Weigert zolang een trekker geen label heeft."""
    ontbreekt = [c for c in trekkers_ if labels.get(c) not in ("vaag", "bewering")]
    if ontbreekt:
        raise Weigering(f"{len(ontbreekt)} trekkers zonder label (bijvoorbeeld {ontbreekt[:3]}); label in {LABELS}")
    vaag = {c for c in trekkers_ if labels[c] == "vaag"}
    vals = [v for v in vlaggen.get("vlaggen", []) if v.get("label") == "vals"]
    return {
        "trekkers": len(trekkers_),
        "vaag": len(vaag),
        "bewering": len(trekkers_) - len(vaag),
        "valse_vlaggen": len(vals),
        "valse_vlaggen_bij_vaag": sum(v["claim_id"] in vaag for v in vals),
    }


def lijst(labels: dict[str, str], teksten: dict[str, str]) -> dict[str, str]:
    """De claims die uit de index gaan, met hun tekst, zodat wie de lijst
    leest ziet wat er wegvalt. Weigert een vage claim zonder tekst."""
    vaag = sorted(c for c, label in labels.items() if label == "vaag")
    zonder = [c for c in vaag if not teksten.get(c)]
    if zonder:
        raise Weigering(f"{len(zonder)} vage claims zonder tekst (bijvoorbeeld {zonder[:3]})")
    return {c: teksten[c] for c in vaag}


def lees_vlaggen(map_: Path) -> dict:
    """De vlaggen van #21.9 met hun labels, als deze pool ze heeft; de verse
    pool van #25.32 heeft ze niet (#25.33)."""
    pad = Path(map_) / "vlaggen.json"
    if not pad.exists():
        return {"vlaggen": []}
    vlaggen = json.loads(pad.read_text(encoding="utf-8"))
    vlaglabels = json.loads(Path("docs/steekproeven/21.9-vlaggen-c4.json").read_text(encoding="utf-8"))["labels"]
    for v in vlaggen["vlaggen"]:
        v["label"] = vlaglabels.get(f"{v['stuk_id']}|{v['claim_id']}")
    return vlaggen


def main() -> None:
    import argparse
    import os
    import sqlite3

    parser = argparse.ArgumentParser(description="Vage claimteksten opsporen (PLAN #25.26)")
    parser.add_argument("stap", choices=("meten", "tellen", "toepassen"))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--map", default=str(MAP), help="de pool; de verse van #25.32 is data/stiltetoets-vers")
    args = parser.parse_args()
    map_ = Path(args.map)
    uitvoer = map_ / "trekkers.json"

    if args.stap == "meten":
        from threadpoolctl import threadpool_limits

        from doublecheck.config import load_config
        from doublecheck.search import _tekstmatrix, _variantenmatrix
        from doublecheck.variantenbatch import lees_regels, lees_vectoren

        threadpool_limits(limits=args.threads)
        versie = load_config().model_versions.text_embedding
        rijen = lees_regels(map_)
        _, stukken = lees_vectoren(map_, versie)
        conn = sqlite3.connect(f"file:{os.environ.get('DOUBLECHECK_DB', 'doublecheck.db')}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        claim_ids, claims = _tekstmatrix(conn, versie)
        variant_claims, _, varianten, _ = _variantenmatrix(conn, versie)
        print(f"{len(stukken)} stukken tegen {len(claim_ids)} claims en {len(variant_claims)} varianten", flush=True)
        ids, gelijkenis = dichtste(stukken, claims, list(claim_ids), varianten, list(variant_claims))
        gevonden = trekkers(ids, gelijkenis)
        tekst = dict(conn.execute("SELECT claim_id, canonical_text FROM claim").fetchall())
        uitgevers: dict[str, list[str]] = {}
        for c, u in conn.execute("SELECT claim_id, publisher FROM factcheck"):
            uitgevers.setdefault(c, []).append(u)
        voorbeelden: dict[str, list[str]] = {}
        volgorde = np.argsort(-gelijkenis)
        for i in volgorde:
            c = ids[i]
            if c in gevonden and len(voorbeelden.setdefault(c, [])) < 3 and gelijkenis[i] >= DREMPEL:
                voorbeelden[c].append(f"{gelijkenis[i]:.2f} {rijen[i]['varianten'][0]['tekst'][:160]}")
        uit = [{"claim_id": c, "stukken": n, "tekst": tekst.get(c), "uitgevers": sorted(set(uitgevers.get(c, []))),
                "voorbeelden": voorbeelden.get(c, [])} for c, n in gevonden.items()]
        uitvoer.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"trekkers (minstens {MINIMUM} stukken op of boven {DREMPEL}): {len(uit)}; om te labelen in {uitvoer}")
        return

    if args.stap == "toepassen":
        from doublecheck.toelating import VAGE_CLAIMS_PATH

        labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"]
        teksten = {t["claim_id"]: t["tekst"] for t in json.loads(uitvoer.read_text(encoding="utf-8"))}
        if VAGE_CLAIMS_PATH.exists():
            # Wat eerder vaag was, blijft vaag: een nieuwe meting ziet die claims niet meer.
            teksten = {**json.loads(VAGE_CLAIMS_PATH.read_text(encoding="utf-8"))["claims"], **teksten}
        # Een label van buiten de pool (de zeef per zin, #30.11b) heeft geen
        # tekst in trekkers.json; die komt dan uit de database.
        ontbreekt = [c for c, label in labels.items() if label == "vaag" and c not in teksten]
        if ontbreekt:
            conn = sqlite3.connect(f"file:{os.environ.get('DOUBLECHECK_DB', 'doublecheck.db')}?mode=ro", uri=True)
            teksten |= {c: t for c, t in conn.execute(
                f"SELECT claim_id, canonical_text FROM claim WHERE claim_id IN ({','.join('?' * len(ontbreekt))})",
                ontbreekt)}
        claims = lijst(labels, teksten)
        VAGE_CLAIMS_PATH.write_text(json.dumps({
            "_meta": ("Claimteksten die niets toetsbaars zeggen, met de hand gelabeld in"
                      f" {LABELS} (#25.26, BENCHMARK §99). Het zoeken slaat ze over (B28,"
                      " #25.28); claim en checks blijven in de database. Geschreven door"
                      " `python -m doublecheck.vaagmeting toepassen`; niet met de hand bewerken."),
            "claims": claims,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(claims)} vage claims in {VAGE_CLAIMS_PATH}")
        return

    gevonden = {t["claim_id"]: t["stukken"] for t in json.loads(uitvoer.read_text(encoding="utf-8"))}
    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}
    print(uitslag(gevonden, labels, lees_vlaggen(map_)))


if __name__ == "__main__":
    main()
