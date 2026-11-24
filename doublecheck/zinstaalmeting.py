"""De stance in de taal van de zin, gemeten (PLAN.md #25.31).

Vastgelegd vóór het meten (PLAN #25.31): regel V laat de stance-laag bij een
cross-linguaal paar óók oordelen op de variant van de claim in de taal van de
zin. V kan alleen vlaggen weghalen, dus het effect op mC4 is exact te meten op
de stukken die nu een vlag hebben. Twee metingen, elk met de regel uit en aan:

- **mc4**: de zeven stukken die in §100 een vlag kregen, met de labels van
  `docs/steekproeven/21.9-vlaggen-c4.json`;
- **modeluitvoer**: de 60 modeluitvoeren van §59: in de beweert-groep is
  alleen een vlag op de bedoelde claim terecht, in de schone en de vreemde
  groep is elke vlag vals.

Criterium: V gaat aan als hij geen terechte vlag kost en er geen vlag
bijkomt, en minstens twee valse wegneemt. Binnen de steekproef: de valse
vlaggen op mC4 zijn bekend.

    python -m doublecheck.zinstaalmeting
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

UITSLAG = Path("data/stiltetoets/zinstaal.json")


def tel(uit: set[tuple[str, str]], aan: set[tuple[str, str]], oordeel: Callable[[str, str], str]) -> dict:
    def per(vlaggen):
        n = {"terecht": 0, "vals": 0}
        for doc, claim in vlaggen:
            n[oordeel(doc, claim)] += 1
        return n

    return {
        "uit": per(uit), "aan": per(aan),
        "weg": sorted((d, c, oordeel(d, c)) for d, c in uit - aan),
        "erbij": sorted((d, c, oordeel(d, c)) for d, c in aan - uit),
    }


def criterium(metingen: list[dict]) -> dict:
    kost = sum(1 for m in metingen for *_, o in m["weg"] if o == "terecht")
    erbij = sum(len(m["erbij"]) for m in metingen)
    vals_weg = sum(1 for m in metingen for *_, o in m["weg"] if o == "vals")
    return {"terechte_vlaggen_kwijt": kost, "vlaggen_erbij": erbij, "valse_vlaggen_weg": vals_weg,
            "gehaald": kost == 0 and erbij == 0 and vals_weg >= 2}


def _vlaggen(rapport) -> set[tuple[str, str]]:
    return {(d.document_id, t.claim_id) for d in rapport.documenten for t in d.beweert}


def main() -> None:
    import dataclasses

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.controle import controleer_teksten
    from doublecheck.storage import connect
    from doublecheck.variantenbatch import lees_regels

    threadpool_limits(limits=2)
    torch.set_num_threads(2)
    config = load_config()
    standen = {aan: dataclasses.replace(config, varianten=dataclasses.replace(config.varianten,
                                                                              stance_in_zinstaal=aan))
               for aan in (False, True)}
    conn = connect("doublecheck.db")

    vlag = json.loads(Path("data/stiltetoets/vlaggen.json").read_text(encoding="utf-8"))
    labels = json.loads(Path("docs/steekproeven/21.9-vlaggen-c4.json").read_text(encoding="utf-8"))["labels"]
    stukken = {v["stuk_id"] for v in vlag["vlaggen"]}
    mc4 = sorted((r["claim_id"], r["varianten"][0]["tekst"]) for r in lees_regels(Path("data/stiltetoets"))
                 if r["claim_id"] in stukken)
    uitvoer = json.loads(Path("docs/steekproeven/21.3-echte-data.json").read_text(encoding="utf-8"))["modeluitvoer"]
    bedoeld = {m["id"]: m["claim_id"] if m["groep"] == "beweert" else None for m in uitvoer}
    model = [(m["id"], m["tekst"]) for m in uitvoer]

    def oordeel_mc4(doc, claim):
        return "terecht" if labels.get(f"{doc}|{claim}") == "terecht" else "vals"

    def oordeel_model(doc, claim):
        return "terecht" if bedoeld.get(doc) == claim else "vals"

    metingen = {}
    for naam, documenten, oordeel in (("mc4", mc4, oordeel_mc4), ("modeluitvoer", model, oordeel_model)):
        rapporten = {aan: controleer_teksten(conn, documenten, config=standen[aan]) for aan in (False, True)}
        metingen[naam] = tel(_vlaggen(rapporten[False]), _vlaggen(rapporten[True]), oordeel)
        metingen[naam]["zinstaal"] = sorted(
            (d.document_id, t.claim_id, t.entailment, t.entailment_zinstaal)
            for d in rapporten[True].documenten for t in d.treffers if t.entailment_zinstaal is not None)
        print(naam, json.dumps({k: v for k, v in metingen[naam].items() if k != "zinstaal"}, ensure_ascii=False),
              flush=True)
    uit = {"metingen": metingen, "criterium": criterium(list(metingen.values()))}
    UITSLAG.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print("criterium:", uit["criterium"])


if __name__ == "__main__":
    main()
