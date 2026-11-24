"""Notes voor beweringen die nog geen redactie checkte: de offline meting
(PLAN.md #25.16 d).

Een behulpzame Community Note wordt vaak eerder geschreven dan een
redactie de bewering checkt, en er komen er ruim 2.000 per week bij (§72).
Kan een bewering de note vinden die erover gaat? Besluit PO 2026-10-12:
eerst offline meten, pas daarna een besluit over het antwoord.

De vragen met een bekend antwoord zijn de bruggen: notes die naar een check
in ons corpus verwijzen. De claimvector van die check zoekt tussen alle
geselecteerde notes; goed als de bovenste note naar dezelfde claim of naar
een claim uit hetzelfde cluster verwijst. Precisie op beweringen zonder brug
vraagt lezen: `steekproef` zet claim en dichtstbijzijnde note naast elkaar.

De noteteksten staan alleen in `data/notesmeting/` (buiten git) en gaan nooit
mee in een uitgave (X Developer Agreement, E7.S6).

    python -m doublecheck.notesmeting selecteren [--afleiders 50000]
    python -m doublecheck.notesmeting embedden [--deel 0/2]
    python -m doublecheck.notesmeting meten
    python -m doublecheck.notesmeting herordenen --map data/notesmeting/alles   (#25.23)
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from pathlib import Path

import numpy as np

from doublecheck.communitynotes import _rijen, meet

MAP = Path("data/notesmeting")
_URL = re.compile(r"https?://\S+")


def schoon(tekst: str) -> str:
    """De note zonder links: een adres zegt het model niets over de bewering."""
    return " ".join(_URL.sub(" ", tekst).split())


def selecteer(conn: sqlite3.Connection, map_: Path, *, factcheck_hosts: set[str], afleiders: int,
              zaad: int = 2516) -> list[dict]:
    """Elke behulpzame note met een brug, plus een vaste steekproef van andere
    behulpzame notes als afleiders; in de vorm van de claimvarianten, zodat
    de embedder van #25.17 ze kan lezen."""
    uitslag = meet(conn, map_, factcheck_hosts=factcheck_hosts)
    brug = {note: claim for note, _, claim in uitslag["bruggen"]}
    behulpzaam = sorted(
        r["noteId"] for r in _rijen(map_, "noteStatusHistory-00000")
        if r.get("currentStatus") == "CURRENTLY_RATED_HELPFUL"
    )
    andere = [n for n in behulpzaam if n not in brug]
    gekozen = set(brug) | set(random.Random(zaad).sample(andere, min(afleiders, len(andere))))
    regels = []
    for pad in sorted(Path(map_).glob("notes-*.zip")):
        for r in _rijen(map_, pad.stem):
            if r["noteId"] not in gekozen:
                continue
            tekst = schoon(r.get("summary", ""))
            if not tekst:
                continue
            regels.append({"claim_id": r["noteId"], "post": r["tweetId"], "brug": brug.get(r["noteId"]),
                           "varianten": [{"taal": "", "tekst": tekst}]})
    return sorted(regels, key=lambda r: int(r["claim_id"]))


def _groep(conn: sqlite3.Connection) -> dict[str, str]:
    return {cid: (cl or cid) for cid, cl in conn.execute("SELECT claim_id, cluster_id FROM claim")}


def meet_bruggen(conn: sqlite3.Connection, rijen: list[dict], matrix: np.ndarray, versie: str) -> dict:
    """Per claim met een brug: op welke plek staat de eerste goede note
    (eigen brug of een brug uit het cluster), en is de bovenste goed?"""
    groep = _groep(conn)
    groep_van_note = np.array([groep.get(r["brug"], r["brug"]) if r["brug"] else "" for r in rijen], dtype=object)
    vragen = sorted({r["brug"] for r in rijen if r["brug"]})
    rang: dict[str, int] = {}
    bovenaan = []
    for claim in vragen:
        rij = conn.execute("SELECT payload FROM fingerprint WHERE claim_id = ? AND kind = 'text' AND model_version = ?",
                           (claim, versie)).fetchone()
        if rij is None:
            continue
        sims = matrix @ np.frombuffer(rij[0], dtype=np.float32)
        volgorde = np.argsort(-sims, kind="stable")
        goed = groep_van_note[volgorde] == groep.get(claim, claim)
        rang[claim] = int(np.argmax(goed)) + 1
        bovenaan.append((float(sims[volgorde[0]]), bool(goed[0])))
    return {"vragen": len(rang), "rang": rang, "bovenaan_goed": sum(g for _, g in bovenaan),
            "bovenaan": bovenaan}


def steekproef(conn: sqlite3.Connection, rijen: list[dict], matrix: np.ndarray, versie: str, *,
               n: int, zaad: int = 2516) -> list[dict]:
    """Willekeurige claims zonder brug, elk met de dichtstbijzijnde note en de
    gelijkenis; om te lezen, want hier is geen antwoord bekend."""
    met_brug = {r["brug"] for r in rijen if r["brug"]}
    claims = [c for (c,) in conn.execute(
        "SELECT claim_id FROM fingerprint WHERE kind = 'text' AND model_version = ? ORDER BY claim_id", (versie,))
        if c not in met_brug]
    uit = []
    for claim in random.Random(zaad).sample(claims, min(n, len(claims))):
        tekst, payload = conn.execute(
            "SELECT c.canonical_text, f.payload FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
            " WHERE c.claim_id = ? AND f.kind = 'text' AND f.model_version = ?", (claim, versie)).fetchone()
        sims = matrix @ np.frombuffer(payload, dtype=np.float32)
        j = int(np.argmax(sims))
        uit.append({"claim": claim, "claimtekst": tekst, "note": rijen[j]["claim_id"],
                    "notetekst": rijen[j]["varianten"][0]["tekst"], "gelijkenis": round(float(sims[j]), 4)})
    return sorted(uit, key=lambda r: -r["gelijkenis"])


def herorden_vragen(vragen: list[tuple[str, np.ndarray, str]], rijen: list[dict], matrix: np.ndarray, score,
                    *, k: int = 20) -> list[dict]:
    """Per vraag (id, vector, tekst): de k dichtstbijzijnde notes volgens de
    embedding, opnieuw gerangschikt door `score([(vraag, note), ...])`. Geeft
    de beste met haar score en haar plek in de embeddingvolgorde."""
    uit = []
    for vraag_id, vector, tekst in vragen:
        sims = matrix @ vector
        k_ = min(k, len(sims))
        top = np.argpartition(-sims, k_ - 1)[:k_]
        top = top[np.argsort(-sims[top], kind="stable")]
        s = score([(tekst, rijen[j]["varianten"][0]["tekst"]) for j in top])
        b = int(np.argmax(s))
        uit.append({"vraag": vraag_id, "note": rijen[top[b]]["claim_id"], "brug": rijen[top[b]]["brug"],
                    "score": float(s[b]), "plek": b + 1, "gelijkenis": round(float(sims[top[b]]), 4)})
    return uit


_ONGELIJK = ("Somewhat Dissimilar", "Very Dissimilar")


def meedan_toets(paren: list[dict], score, *, drempels=(0.3, 0.5, 0.7, 0.9)) -> dict:
    """De herordenaar tegen de menselijke labels van de Meedan-paren (Kazemi
    e.a., CC BY): zet hij boven de drempel wat annotatoren "Very Similar"
    noemden, en niet wat ze ongelijk vonden? Beide richtingen, gemiddeld;
    paren met "N/A" (geen bewering, andere taal) of zonder meerderheid tellen
    niet mee: daar zegt het label niets over goed of fout."""
    bruikbaar = [p for p in paren if p["majority_label"] and not p["majority_label"].startswith("N/A")
                 and p["majority_label"] != "No Majority"]
    heen = score([(p["text1"], p["text2"]) for p in bruikbaar])
    terug = score([(p["text2"], p["text1"]) for p in bruikbaar])
    waarden = [(a + b) / 2 for a, b in zip(heen, terug)]
    per_drempel = {}
    for t in drempels:
        boven = [p for p, w in zip(bruikbaar, waarden) if w >= t]
        per_drempel[t] = {
            "zeer_gelijk": sum(p["majority_label"] == "Very Similar" for p in bruikbaar),
            "gevonden": sum(p["majority_label"] == "Very Similar" for p in boven),
            "boven_drempel": len(boven),
            "waarvan_zeer_gelijk": sum(p["majority_label"] == "Very Similar" for p in boven),
            "waarvan_ongelijk": sum(p["majority_label"] in _ONGELIJK for p in boven),
        }
    return {"paren": len(bruikbaar), "per_drempel": per_drempel}


def main() -> None:
    import argparse
    import os

    from doublecheck.config import load_config
    from doublecheck.variantenbatch import embed, lees_vectoren

    parser = argparse.ArgumentParser(description="Notes voor ongecheckte beweringen: de offline meting (#25.16 d)")
    parser.add_argument("stap", choices=("selecteren", "embedden", "meten", "herordenen"))
    parser.add_argument("--map", default=str(MAP))
    parser.add_argument("--notes", default="data/communitynotes")
    parser.add_argument("--afleiders", type=int, default=50_000)
    parser.add_argument("--deel", default="0/1")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--meedan", default="data/extern/meedan-tiplines/claim_matching_dataset.csv")
    args = parser.parse_args()
    config = load_config()
    versie = config.model_versions.text_embedding
    map_ = Path(args.map)
    conn = sqlite3.connect(f"file:{os.environ.get('DOUBLECHECK_DB', 'doublecheck.db')}?mode=ro", uri=True)
    if args.stap == "selecteren":
        hosts = {h.lower() for h in json.load(open("doublecheck/uitgevers.json", encoding="utf-8"))["hosts"]}
        regels = selecteer(conn, Path(args.notes), factcheck_hosts=hosts, afleiders=args.afleiders)
        map_.mkdir(parents=True, exist_ok=True)
        with (map_ / "regels.jsonl").open("w", encoding="utf-8") as uit:
            for r in regels:
                uit.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{len(regels)} notes, waarvan {sum(bool(r['brug']) for r in regels)} met een brug")
    elif args.stap == "embedden":
        import torch
        from threadpoolctl import threadpool_limits

        from doublecheck.embedding import fingerprint_texts

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        i, n = (int(x) for x in args.deel.split("/"))
        print(f"nieuw embed: {embed(map_, versie, fingerprint_texts, deel=(i, n))}", flush=True)
    elif args.stap == "herordenen":
        _herordenen(conn, map_, versie, Path(args.meedan), args.threads)
    else:
        from doublecheck.variantenbatch import lees_regels

        rijen = lees_regels(map_)
        _, matrix = lees_vectoren(map_, versie)
        rijen = rijen[:len(matrix)]
        uit = meet_bruggen(conn, rijen, matrix, versie)
        rangen = sorted(uit["rang"].values())
        n = len(rangen) or 1
        print(f"{len(rijen)} notes in de pool; {uit['vragen']} claims met een brug als vraag")
        for k in (1, 5, 20):
            print(f"  goede note bij de eerste {k}: {sum(r <= k for r in rangen)} ({sum(r <= k for r in rangen) / n:.1%})")
        print(f"  mediane rang {rangen[len(rangen) // 2] if rangen else '-'}")
        for lo in (0.5, 0.6, 0.7, 0.8):
            band = [g for s, g in uit["bovenaan"] if s >= lo]
            print(f"  bovenste note met gelijkenis ≥ {lo}: {len(band)} vragen, goed {sum(band)}")
        proef = steekproef(conn, rijen, matrix, versie, n=200)
        (map_ / "steekproef.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in proef),
                                               encoding="utf-8")
        print(f"steekproef om te lezen: {map_ / 'steekproef.jsonl'} (200 claims zonder brug)")


def _herordenen(conn, map_: Path, versie: str, meedan: Path, threads: int) -> None:
    """De tweede ronde (#25.23): de embedding levert twintig kandidaten, de
    herordenaar kiest. Drie metingen, elk weggeschreven om na te lezen."""
    import csv

    import torch

    from doublecheck import herordenaar
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.variantenbatch import lees_regels, lees_vectoren

    torch.set_num_threads(threads)
    rijen = lees_regels(map_)
    _, matrix = lees_vectoren(map_, versie)
    rijen = rijen[:len(matrix)]
    groep = _groep(conn)
    print(f"pool: {len(rijen)} notes · herordenaar {herordenaar.HERORDENAAR}", flush=True)

    def claimvraag(claim):
        tekst, payload = conn.execute(
            "SELECT c.canonical_text, f.payload FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
            " WHERE c.claim_id = ? AND f.kind = 'text' AND f.model_version = ?", (claim, versie)).fetchone()
        return claim, np.frombuffer(payload, dtype=np.float32), tekst

    # 1. Claims met een brug: wint de herordenaar het van de embedding?
    bruggen = sorted({r["brug"] for r in rijen if r["brug"]})
    uit = herorden_vragen([claimvraag(c) for c in bruggen], rijen, matrix, herordenaar.scores)
    goed = [groep.get(u["brug"], u["brug"]) == groep.get(u["vraag"], u["vraag"]) if u["brug"] else False for u in uit]
    (map_ / "bruggen-herordend.jsonl").write_text(
        "".join(json.dumps({**u, "goed": g}, ensure_ascii=False) + "\n" for u, g in zip(uit, goed)), encoding="utf-8")
    print(f"bruggen: {len(uit)} vragen; herordend strikt goed bovenaan {sum(goed)}", flush=True)
    for t in (0.5, 0.7, 0.9):
        band = [g for u, g in zip(uit, goed) if u["score"] >= t]
        print(f"  score ≥ {t}: {len(band)} vragen, strikt goed {sum(band)}", flush=True)

    # 2. Claims zonder brug: om te lezen.
    met_brug = set(bruggen)
    claims = [c for (c,) in conn.execute(
        "SELECT claim_id FROM fingerprint WHERE kind = 'text' AND model_version = ? ORDER BY claim_id", (versie,))
        if c not in met_brug]
    vragen = [claimvraag(c) for c in random.Random(2516).sample(claims, 200)]
    uit = herorden_vragen(vragen, rijen, matrix, herordenaar.scores)
    tekst_van = {r["claim_id"]: r["varianten"][0]["tekst"] for r in rijen}
    lees = sorted(({**u, "claimtekst": t, "notetekst": tekst_van[u["note"]]} for u, (_, _, t) in zip(uit, vragen)),
                  key=lambda r: -r["score"])
    (map_ / "steekproef-herordend.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lees), encoding="utf-8")
    print(f"zonder brug: 200 vragen; score ≥ 0,5: {sum(r['score'] >= 0.5 for r in lees)},"
          f" ≥ 0,9: {sum(r['score'] >= 0.9 for r in lees)} (om te lezen)", flush=True)

    # 3. Meedan: de herordenaar tegen menselijke labels, en tiplinevragen tegen de notes.
    if meedan.exists():
        paren = list(csv.DictReader(meedan.open(encoding="utf-8")))
        toets = meedan_toets(paren, herordenaar.scores)
        print(f"meedan: {toets['paren']} paren met een label", flush=True)
        for t, d in toets["per_drempel"].items():
            print(f"  ≥ {t}: {d['gevonden']}/{d['zeer_gelijk']} zeer gelijk gevonden; boven de drempel"
                  f" {d['boven_drempel']}, waarvan ongelijk {d['waarvan_ongelijk']}", flush=True)
        # De berichten van sociale media en tiplines zijn de vragen van echte
        # gebruikers; de andere bron is de kop van een factcheck.
        tipline = sorted({p[f"text{i}"] for p in paren for i in (1, 2) if p.get(f"source{i}") == "social media"
                          and p[f"text{i}"].strip()})
        tipline = sorted(random.Random(2523).sample(tipline, min(1000, len(tipline))))
        vectoren = fingerprint_texts(tipline, versie)
        uit = herorden_vragen([(f"tip-{i}", f.vector, t) for i, (t, f) in enumerate(zip(tipline, vectoren))],
                              rijen, matrix, herordenaar.scores)
        lees = sorted(({**u, "vraagtekst": t, "notetekst": tekst_van[u["note"]]} for u, t in zip(uit, tipline)),
                      key=lambda r: -r["score"])
        (map_ / "meedan-herordend.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lees), encoding="utf-8")
        print(f"tiplinevragen: {len(tipline)}; score ≥ 0,5: {sum(r['score'] >= 0.5 for r in lees)},"
              f" ≥ 0,9: {sum(r['score'] >= 0.9 for r in lees)} (om te lezen)", flush=True)


if __name__ == "__main__":
    main()
