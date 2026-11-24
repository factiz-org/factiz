"""Alle vetoblokkades van het corpus (PLAN.md #25.14d, d en g).

Een blokkade is een paar dat de clustering zou samenvoegen (zelfde taal,
gelijkenis boven `cluster_same`, geen tegenspraak in getallen of
ontkenningen, DR8) maar dat het NLI-veto tegenhoudt. In een steekproef rond
8.000 claims trok het veto onder bge-m3 8 van de 12 leesbare blokkades
dezelfde bewering uit elkaar (BENCHMARK §77b); te weinig om de regel te
veranderen. Dit telt ze allemaal, scoort ze met hetzelfde model en dezelfde
maat als het veto, en levert de lijst om te labelen.

Alleen claim-id's, taal, gelijkenis en score gaan naar schijf; de teksten
blijven in de database. Het scoren is hervatbaar: een paar dat al een score
heeft, wordt niet opnieuw gescoord.

    python -m doublecheck.vetoblokkades tellen
    python -m doublecheck.vetoblokkades scoren [--threads 2]
    python -m doublecheck.vetoblokkades meten
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations, extract_numbers

MAP = Path("data/vetoblokkades")


@dataclass(frozen=True)
class Paar:
    a: str
    b: str
    taal: str
    gelijkenis: float

    @property
    def sleutel(self) -> str:
        return f"{self.a}|{self.b}"


def _tegenspraak(a: str, b: str) -> bool:
    """De regel van de clustering (DR8), in beide richtingen: een paar dat al
    op getallen of ontkenningen vastloopt, is geen blokkade van het veto."""
    return any(
        contradicts(extract_numbers(x), extract_negations(x), y, artefact_text=x,
                    artefact_negation_tokens=extract_negation_tokens(x))
        for x, y in ((a, b), (b, a))
    )


def kandidaten(conn: sqlite3.Connection, model_version: str, drempel: float, *,
               ook_tegenspraak: bool = False, portie: int = 512) -> list[Paar]:
    """Elk paar in dezelfde taal met gelijkenis ≥ `drempel` dat niet in één
    cluster zit, zonder de paren die de tegenspraakregel al tegenhoudt."""
    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, c.language, c.cluster_id, f.payload"
        " FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
        " WHERE f.kind = 'text' AND f.model_version = ? ORDER BY c.claim_id",
        (model_version,),
    ).fetchall()
    per_taal: dict[str, list[int]] = {}
    for i, r in enumerate(rijen):
        per_taal.setdefault(r[2], []).append(i)

    paren: list[Paar] = []
    for taal, leden in sorted(per_taal.items()):
        if len(leden) < 2 or not taal:
            continue
        matrix = np.vstack([np.frombuffer(rijen[i][4], dtype=np.float32) for i in leden])
        for start in range(0, len(leden), portie):
            sims = matrix[start:start + portie] @ matrix.T
            for x, y in zip(*np.nonzero(sims >= drempel)):
                i, j = start + int(x), int(y)
                if j <= i:
                    continue
                ra, rb = rijen[leden[i]], rijen[leden[j]]
                if ra[3] is not None and ra[3] == rb[3]:
                    continue
                if not ook_tegenspraak and _tegenspraak(ra[1], rb[1]):
                    continue
                paren.append(Paar(ra[0], rb[0], taal, float(sims[x, y])))
    return paren


def _lees(pad: Path) -> list[dict]:
    """Alleen afgemaakte regels: een onderbroken run laat er hooguit één half."""
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    inhoud = inhoud[:inhoud.rfind("\n") + 1]
    return [json.loads(r) for r in inhoud.splitlines() if r.strip()]


def _gescoord(pad: Path) -> set[str]:
    return {r["sleutel"] for r in _lees(pad)}


def scoor(conn: sqlite3.Connection, paren: list[Paar], score, pad: Path, *, voortgang=None) -> int:
    """Scoort de paren die nog geen score hebben met `score(tekst_a, tekst_b)`
    en schrijft elke uitslag meteen weg. Geeft het aantal nieuw gescoorde."""
    klaar = _gescoord(pad)
    nieuw = 0
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as uit:
        for paar in paren:
            if paar.sleutel in klaar:
                continue
            ta, tb = (conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (c,)).fetchone()[0]
                      for c in (paar.a, paar.b))
            uit.write(json.dumps({"sleutel": paar.sleutel, "a": paar.a, "b": paar.b, "taal": paar.taal,
                                  "gelijkenis": round(paar.gelijkenis, 4), "score": round(score(ta, tb), 4)},
                                 ensure_ascii=False) + "\n")
            uit.flush()
            klaar.add(paar.sleutel)
            nieuw += 1
            if voortgang is not None and nieuw % 200 == 0:
                voortgang(nieuw)
    return nieuw


def blokkades(pad: Path, drempel: float) -> list[dict]:
    """De gescoorde paren die het veto tegenhoudt: score ≥ de vetodrempel."""
    return [r for r in _lees(pad) if r["score"] >= drempel]


def ongelabeld(pad: Path, labels: dict[str, dict], drempel: float) -> list[dict]:
    """De blokkades die nog geen label hebben: het werk van een nieuwe ronde.
    Labels uit een latere ronde dan de eerste zijn de achtergehouden toets
    voor elke grens die later gekozen wordt (§86)."""
    return [r for r in blokkades(pad, drempel) if r["sleutel"] not in labels]


LABELS = Path("docs/steekproeven/25.14d-vetolabels.json")
_KLASSEN = ("terecht", "onterecht", "twijfel")


def _tel(paren) -> dict[str, int]:
    labels = [p["label"] for p in paren]
    return {k: labels.count(k) for k in _KLASSEN}


def afweging(paren: dict[str, dict], drempels) -> list[dict]:
    """Wat het veto per drempel nog tegenhoudt, per label. Een hogere drempel
    laat elke blokkade met een lagere score door: die paren gaan samen."""
    return [{"drempel": t, **_tel(p for p in paren.values() if p["score"] >= t)} for t in drempels]


def per_gelijkenis(paren: dict[str, dict], grenzen) -> list[dict]:
    """De labels per gelijkenisband: liggen de onterechte blokkades dichter
    bij elkaar dan de terechte?"""
    return [{"band": f"{lo:.2f}-{hi:.2f}", **_tel(p for p in paren.values() if lo <= p["gelijkenis"] < hi)}
            for lo, hi in zip(grenzen, grenzen[1:])]


def main() -> None:
    import argparse
    import collections
    import os

    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="Alle vetoblokkades van het corpus (#25.14d)")
    parser.add_argument("stap", choices=("tellen", "scoren", "meten"))
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    config = load_config()
    if args.stap == "meten":
        paren = json.loads(LABELS.read_text(encoding="utf-8"))["paren"]
        print(f"{len(paren)} gelabelde blokkades: {_tel(paren.values())}")
        per_ronde = collections.Counter(p.get("ronde", "?") for p in paren.values())
        print("per ronde:", dict(sorted(per_ronde.items())))
        if (MAP / "scores.jsonl").exists():
            open_ = ongelabeld(MAP / "scores.jsonl", paren, config.thresholds.nli_contradiction)
            print(f"nog te labelen: {len(open_)}" + "".join(
                f"\n  {r['sleutel']} [{r['taal']}] gelijkenis {r['gelijkenis']:.3f} score {r['score']:.2f}"
                for r in open_))
        print("per soort:", dict(collections.Counter((p["label"], p["soort"]) for p in paren.values())))
        for rij in afweging(paren, (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)):
            print(f"  veto vanaf {rij['drempel']:.2f}: houdt {rij['terecht']} terecht,"
                  f" {rij['onterecht']} onterecht, {rij['twijfel']} twijfel tegen")
        for rij in per_gelijkenis(paren, (0.91, 0.93, 0.95, 0.97, 1.01)):
            print(f"  gelijkenis {rij['band']}: {rij['terecht']} terecht, {rij['onterecht']} onterecht,"
                  f" {rij['twijfel']} twijfel")
        return
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    paren = kandidaten(conn, config.model_versions.text_embedding, config.thresholds.cluster_same)
    per_taal = collections.Counter(p.taal for p in paren)
    print(f"{len(paren)} kandidaatparen boven {config.thresholds.cluster_same} in {len(per_taal)} talen:"
          f" {dict(per_taal.most_common(12))}", flush=True)
    if args.stap == "scoren":
        import torch

        from doublecheck.nli import contradiction_score

        torch.set_num_threads(args.threads)
        pad = MAP / "scores.jsonl"
        nieuw = scoor(conn, paren, lambda a, b: contradiction_score(a, b, config.model_versions.nli), pad,
                      voortgang=lambda n: print(f"  {n} gescoord", flush=True))
        geblokkeerd = blokkades(pad, config.thresholds.nli_contradiction)
        print(f"nieuw gescoord: {nieuw}; blokkades (score ≥ {config.thresholds.nli_contradiction}):"
              f" {len(geblokkeerd)}", flush=True)


if __name__ == "__main__":
    main()
