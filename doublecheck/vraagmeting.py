"""De meting van #25.36 (stap b en e): de meetset door het echte pad.

Elke post uit `docs/steekproeven/25.36-meetset.json` gaat door `POST /resolve`
en `POST /ask`, met de schakelaar `[vraagvorm] aan` uit (de nulmeting) of aan.
Gevonden is alleen wat naar de claim van het paar wijst, of naar een claim in
hetzelfde cluster. Een `matched` op iets anders telt apart en gaat naar de
leesproef: het kan dezelfde bewering onder een ander record zijn, of een
valse treffer.

De toetshelft blijft dicht tot stap e: zonder `--stap-e` weigert de meting
hem. Een paar dat bij de leesproef een fout kreeg, gaat eruit; een paar zonder
lezing blijft erin.

    python -m doublecheck.vraagmeting meten [--aan] [--helft ontwikkel]
    python -m doublecheck.vraagmeting stilte [--pool data/stiltetoets]

`stilte` haalt de gewone webtekst van een stiltepool door `/resolve`, met de
schakelaar uit én aan, maar alleen de teksten waar de regel iets doet: bij de
rest is het antwoord per constructie gelijk. Een `matched` die er met de
regel bijkomt, gaat naar de leesproef; de poort van #25.36 is: geen enkele
extra valse `matched`. Hervatbaar.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

MEETSET = Path("docs/steekproeven/25.36-meetset.json")
UIT = Path("data/vraagvorm/metingen")


class Dicht(Exception):
    """De toetshelft wordt pas bij stap e gemeten (PLAN #25.36)."""


def kies_helft(paren: list[dict], helft: str, *, stap_e: bool = False) -> list[dict]:
    if helft == "toets" and not stap_e:
        raise Dicht("de toetshelft blijft dicht tot stap e (PLAN #25.36); meet de ontwikkelhelft")
    return [p for p in paren if p["helft"] == helft and p.get("lezing") in (None, "goed")]


def _zelfde(claim_id: str | None, verwacht: str, clusters: dict[str, str | None]) -> bool:
    if claim_id is None:
        return False
    if claim_id == verwacht:
        return True
    cluster = clusters.get(verwacht)
    return cluster is not None and clusters.get(claim_id) == cluster


def resolve_uitkomst(antwoord: dict, verwacht: str, clusters: dict[str, str | None]) -> str:
    categorie = antwoord.get("category")
    if categorie not in ("matched", "related"):
        return "niets"
    raak = _zelfde((antwoord.get("claim") or {}).get("id"), verwacht, clusters)
    if categorie == "matched":
        return "gevonden" if raak else "ander matched"
    return "verwant" if raak else "ander verwant"


def ask_uitkomst(antwoord: dict, verwacht: str, clusters: dict[str, str | None]) -> str:
    ids = [(r.get("claim") or {}).get("id") for r in antwoord.get("results", [])]
    if not ids:
        return "niets"
    if _zelfde(ids[0], verwacht, clusters):
        return "eerste"
    if any(_zelfde(i, verwacht, clusters) for i in ids):
        return "getoond"
    return "ander"


def tel(regels: list[dict]) -> dict:
    tabel: dict = defaultdict(lambda: {"n": 0, "resolve": Counter(), "ask": Counter()})
    for regel in regels:
        for sleutel in ((regel["richting"], regel["taal"]), (regel["richting"], "alle"), ("alle", "alle")):
            tabel[sleutel]["n"] += 1
            tabel[sleutel]["resolve"][regel["resolve"]] += 1
            tabel[sleutel]["ask"][regel["ask"]] += 1
    return {k: {"n": v["n"], "resolve": dict(v["resolve"]), "ask": dict(v["ask"])} for k, v in tabel.items()}


def meet(conn, config, paren: list[dict], *, aan: bool) -> list[dict]:
    """Elk paar door het echte `/resolve` en `/ask`, met de schakelaar zoals
    gevraagd; de rest van de config is die van `config.toml`."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.config import VraagvormSettings

    instelling = replace(config, vraagvorm=VraagvormSettings(aan=aan))
    clusters = dict(conn.execute("SELECT claim_id, cluster_id FROM claim"))
    regels = []
    api.app.dependency_overrides[api.get_config] = lambda: instelling
    # Een meting is geen piek van buiten: de rate-limiter uit, zoals de
    # stiltetoets, en daarna weer zoals hij was.
    was = api.limiter.enabled
    api.limiter.enabled = False
    try:
        # Zonder `with`: geen opstartstap, die verlopen betwistingen opruimt; een
        # meting kijkt, ze ruimt niet op (zoals de stiltetoets).
        client = TestClient(api.app)
        for paar in paren:
            resolve = client.post("/resolve", json={"text": paar["post"]})
            ask = client.post("/ask", json={"question": paar["post"]})
            if resolve.status_code != 200 or ask.status_code != 200:
                # Een toets stopt bij een fout van de resolver, in plaats van
                # hem als "niets" te tellen (zoals de netwerktoets, #28.5).
                raise RuntimeError(f"{paar['id']}: resolve {resolve.status_code}, ask {ask.status_code}")
            antwoord = resolve.json()
            regels.append({"id": paar["id"], "richting": paar["richting"], "taal": paar["taal"],
                           "resolve": resolve_uitkomst(antwoord, paar["claim_id"], clusters),
                           "ask": ask_uitkomst(ask.json(), paar["claim_id"], clusters),
                           "categorie": antwoord.get("category"),
                           "gelijkenis": antwoord.get("similarity"),
                           "claim": (antwoord.get("claim") or {}).get("id")})
    finally:
        api.app.dependency_overrides.pop(api.get_config, None)
        api.limiter.enabled = was
    return regels


def geraakt(teksten: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """De teksten waar de regel iets aan verandert; bij de rest is het
    antwoord met de schakelaar aan per constructie gelijk aan dat zonder."""
    from doublecheck.vraagvorm import als_bewering

    return [(sleutel, tekst) for sleutel, tekst in teksten if als_bewering(tekst) != tekst]


def nieuwe_matches(regels: list[dict]) -> list[dict]:
    """Waar de regel van niet-`matched` een `matched` maakt: die gaan naar de
    leesproef."""
    return [r for r in regels if r["aan"]["categorie"] == "matched" and r["uit"]["categorie"] != "matched"]


def stilte(teksten: list[tuple[str, str]], uitpad: Path, config) -> None:
    """Elke tekst door het echte `/resolve`, uit en aan; schrijft per tekst een
    regel en slaat over wat al in `uitpad` staat."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.config import VraagvormSettings

    gedaan = set()
    if uitpad.exists():
        gedaan = {json.loads(r)["sleutel"] for r in uitpad.read_text(encoding="utf-8").splitlines() if r.strip()}
    standen = {stand: replace(config, vraagvorm=VraagvormSettings(aan=stand)) for stand in (False, True)}
    huidig = {"stand": False}
    api.app.dependency_overrides[api.get_config] = lambda: standen[huidig["stand"]]
    was = api.limiter.enabled
    api.limiter.enabled = False
    try:
        client = TestClient(api.app)
        with uitpad.open("a", encoding="utf-8") as uit:
            for n, (sleutel, tekst) in enumerate(teksten, 1):
                if sleutel in gedaan:
                    continue
                regel = {"sleutel": sleutel}
                for stand, naam in ((False, "uit"), (True, "aan")):
                    huidig["stand"] = stand
                    antwoord = client.post("/resolve", json={"text": tekst})
                    if antwoord.status_code != 200:
                        raise RuntimeError(f"{sleutel}: resolve {antwoord.status_code}")
                    d = antwoord.json()
                    regel[naam] = {"categorie": d.get("category"), "claim": (d.get("claim") or {}).get("id"),
                                   "gelijkenis": d.get("similarity")}
                uit.write(json.dumps(regel, ensure_ascii=False) + "\n")
                if n % 500 == 0:
                    uit.flush()
                    print(f"  {n}/{len(teksten)}", flush=True)
    finally:
        api.app.dependency_overrides.pop(api.get_config, None)
        api.limiter.enabled = was


def _toon(tabel: dict) -> None:
    def deel(teller: dict, sleutel: str, n: int) -> str:
        return f"{teller.get(sleutel, 0)} ({teller.get(sleutel, 0) / n:.0%})" if n else "-"

    print("richting  taal   n   resolve: gevonden / verwant / ander matched / ander verwant / niets"
          "   ask: eerste / getoond")
    for (richting, taal), rij in sorted(tabel.items()):
        n, r, a = rij["n"], rij["resolve"], rij["ask"]
        print(f"{richting:9} {taal:5} {n:3}   {deel(r, 'gevonden', n)} / {deel(r, 'verwant', n)} / "
              f"{deel(r, 'ander matched', n)} / {deel(r, 'ander verwant', n)} / {deel(r, 'niets', n)}   "
              f"{deel(a, 'eerste', n)} / {deel(a, 'getoond', n)}")


def main() -> None:
    import argparse
    import os
    import sqlite3

    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="De meting van #25.36: de meetset door het echte pad")
    parser.add_argument("stap", choices=("meten", "stilte"))
    parser.add_argument("--pool", default="data/stiltetoets", help="bij stilte: de map met regels.jsonl")
    parser.add_argument("--aan", action="store_true", help="met de schakelaar [vraagvorm] aan")
    parser.add_argument("--helft", default="ontwikkel", choices=("ontwikkel", "toets"))
    parser.add_argument("--stap-e", action="store_true", help="alleen bij stap e: de toetshelft openen")
    parser.add_argument("--label", default="",
                        help="achter de naam van het uitvoerbestand, bijvoorbeeld 'kopie' bij een meting op een kopie")
    args = parser.parse_args()

    if args.stap == "stilte":
        pool = Path(args.pool)
        teksten = [(f"{r['claim_id']}#{i}", v["tekst"])
                   for r in map(json.loads, (pool / "regels.jsonl").read_text(encoding="utf-8").splitlines())
                   for i, v in enumerate(r["varianten"])]
        doel = geraakt(teksten)
        UIT.mkdir(parents=True, exist_ok=True)
        pad = UIT / f"stilte-{pool.name}.jsonl"
        print(f"{len(teksten)} teksten in {pool}, {len(doel)} waar de regel iets doet; naar {pad}", flush=True)
        stilte(doel, pad, load_config())
        regels = [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]
        nieuw = nieuwe_matches(regels)
        print(f"klaar: {len(regels)} teksten; matched uit {sum(r['uit']['categorie'] == 'matched' for r in regels)},"
              f" aan {sum(r['aan']['categorie'] == 'matched' for r in regels)}; nieuw matched {len(nieuw)}")
        return
    meetset = json.loads(MEETSET.read_text(encoding="utf-8"))
    paren = kies_helft(meetset["paren"], args.helft, stap_e=args.stap_e)
    conn = sqlite3.connect(f"file:{os.environ.get('DOUBLECHECK_DB', 'doublecheck.db')}?mode=ro", uri=True)
    regels = meet(conn, load_config(), paren, aan=args.aan)
    UIT.mkdir(parents=True, exist_ok=True)
    pad = UIT / f"{args.helft}-{'aan' if args.aan else 'uit'}{'-' + args.label if args.label else ''}.jsonl"
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels), encoding="utf-8")
    _toon(tel(regels))
    print(f"regels naar {pad}")


if __name__ == "__main__":
    main()
