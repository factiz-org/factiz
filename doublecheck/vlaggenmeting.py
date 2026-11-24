"""Valse vlaggen op een echt trainingscorpus (PLAN.md #21.9).

De eerste vraag van een AI-lab bij de datacontrole van B17 is hoe vaak ze ten
onrechte vlagt op gewone trainingsdata. De stiltetoets (#28.6 g) heeft 289.880
stukken uit mC4, de meertalige C4, al geëmbed; deze meting legt dezelfde
stukken langs de batchcontrole.

Vastgelegd vóór het meten (PLAN #21.9): elk stuk is één document en gaat door
`controleer_teksten` zoals in productie (zinnen, embedding, screeningpoort met
de varianten, tegenspraakcheck, stance-laag). Alleen de stukken waarvan de
vector van het hele stuk boven de poort min `MARGE` uitkomt; een vaste
steekproef van de rest gaat door hetzelfde pad, om te zien of de voorselectie
lekt. Elke vlag met de hand gelabeld.

    python -m doublecheck.vlaggenmeting meten|tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import numpy as np

MAP = Path("data/stiltetoets")
LABELS = Path("docs/steekproeven/21.9-vlaggen-c4.json")
MARGE = 0.15
STEEKPROEF = 2_000


class Weigering(Exception):
    pass


def verdeel(hoogste: np.ndarray, *, poort: float, n_steekproef: int = STEEKPROEF, zaad: int = 219):
    """De stukken in de buurt van de poort, en een vaste steekproef van de rest."""
    boven = np.nonzero(hoogste >= poort - MARGE)[0]
    rest = sorted(set(range(len(hoogste))) - set(boven.tolist()))
    steekproef = sorted(random.Random(zaad).sample(rest, min(n_steekproef, len(rest))))
    return boven, steekproef


def vlaggen(uitslagen) -> list[dict]:
    """De vlaggen: wat een document als waar brengt, met weerlegt-wint (#21.5)."""
    uit = []
    for doc in uitslagen:
        for t in doc.beweert:
            uit.append({"stuk_id": doc.document_id, "taal": doc.document_id.split("-")[0],
                        "claim_id": t.claim_id, "zin": t.zin, "claim_tekst": t.claim_tekst,
                        "similarity": round(t.similarity, 4), "entailment": t.entailment})
    return uit


def uitslag(vlag: list[dict], labels: dict[str, str], n_per_taal: dict[str, int]) -> dict:
    """Vlaggen, terecht en vals op n, per taal en in totaal, met de eenzijdige
    95%-bovengrens voor vals. Weigert zolang een vlag geen label heeft."""
    from doublecheck.cijfers import _bovengrens

    def sleutel(v: dict) -> str:
        return f"{v['stuk_id']}|{v['claim_id']}"

    ontbreekt = [sleutel(v) for v in vlag if labels.get(sleutel(v)) not in ("terecht", "vals")]
    if ontbreekt:
        raise Weigering(f"{len(ontbreekt)} vlaggen zonder label (bijvoorbeeld {ontbreekt[:3]}); label in {LABELS}")

    def leeg(n: int) -> dict:
        return {"n": n, "vlaggen": 0, "terecht": 0, "vals": 0}

    per_taal = {t: leeg(n) for t, n in n_per_taal.items()}
    totaal = leeg(sum(n_per_taal.values()))
    for v in vlag:
        for doel in (per_taal[v["taal"]], totaal):
            doel["vlaggen"] += 1
            doel[labels[sleutel(v)]] += 1
    for doel in (*per_taal.values(), totaal):
        doel["bovengrens"] = _bovengrens(doel["vals"], doel["n"])
    return {"per_taal": per_taal, "totaal": totaal}


def main() -> None:
    import argparse
    import os

    from doublecheck.config import load_config
    from doublecheck.controle import controleer_teksten
    from doublecheck.storage import connect
    from doublecheck.variantenbatch import lees_regels

    parser = argparse.ArgumentParser(description="Valse vlaggen op mC4 (PLAN #21.9)")
    parser.add_argument("stap", choices=("meten", "tellen"))
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    rijen = lees_regels(MAP)
    uitvoer = MAP / "vlaggen.json"

    if args.stap == "meten":
        import torch
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        config = load_config()
        poort = config.thresholds.screening_poort
        boven, steekproef = verdeel(np.load(MAP / "hoogste.npy"), poort=poort)
        print(f"{len(rijen)} stukken; {len(boven)} op of boven {poort - MARGE:.2f} door de batchcontrole;"
              f" steekproef van {len(steekproef)} eronder", flush=True)
        conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))

        def documenten(indices):
            return [(rijen[i]["claim_id"], rijen[i]["varianten"][0]["tekst"]) for i in indices]

        rapport = controleer_teksten(conn, documenten(boven), config=config)
        controle = controleer_teksten(conn, documenten(steekproef), config=config)
        uit = {
            "poort": poort, "marge": MARGE, "kandidaten": len(boven), "steekproef": len(steekproef),
            "vlaggen": vlaggen(rapport.documenten),
            "kandidaten_met_treffer": sum(bool(d.treffers) for d in rapport.documenten),
            "steekproef_vlaggen": vlaggen(controle.documenten),
            "steekproef_met_treffer": sum(bool(d.treffers) for d in controle.documenten),
        }
        uitvoer.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"vlaggen: {len(uit['vlaggen'])} (stukken met een treffer boven de poort:"
              f" {uit['kandidaten_met_treffer']}); in de steekproef eronder: {len(uit['steekproef_vlaggen'])}"
              f" vlaggen, {uit['steekproef_met_treffer']} stukken met een treffer", flush=True)
        return

    uit = json.loads(uitvoer.read_text(encoding="utf-8"))
    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}
    n_per_taal = dict(Counter(r["taal"] for r in rijen))
    tel = uitslag(uit["vlaggen"], labels, n_per_taal)
    t = tel["totaal"]
    print(f"{t['n']} stukken: {t['vlaggen']} vlaggen ({t['terecht']} terecht, {t['vals']} vals);"
          f" bovengrens valse vlaggen {t['bovengrens']:.2e}; lek van de voorselectie:"
          f" {uit['steekproef_met_treffer']} van {uit['steekproef']} stukken eronder met een treffer")
    for taal, d in sorted(tel["per_taal"].items(), key=lambda kv: -kv[1]["n"]):
        if d["vlaggen"]:
            print(f"  {taal}: n {d['n']}, vlaggen {d['vlaggen']}, vals {d['vals']}, bovengrens {d['bovengrens']:.2e}")


if __name__ == "__main__":
    main()
