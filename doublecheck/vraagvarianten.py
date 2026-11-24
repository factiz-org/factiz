"""De vraag-claims ook als bewering in de index (PLAN #25.37).

Van de 108.922 claims zijn er 3.792 als vraag opgeschreven, in het Singalees
60%. Een bewering die zo'n claim zoekt, scoort lager dan nodig. Elke claim
die als vraag is opgeschreven, krijgt daarom één variant: dezelfde tekst door
de regel van #25.36 (`vraagvorm.als_bewering`), dus zonder vraagteken en,
waar de taal zeker is, zonder vraagwoord. Geen taalmodel: zo lijkt de variant
niet op de posts van de meetset van #25.36 (die komen van een taalmodel),
mogen de claims van de meetset hun variant houden, en kost het niets.

De varianten gaan alleen in een kopie van de database. In de productie-index
komen ze pas met een release (B22); de import weigert de database van de
resolver.

    python -m doublecheck.vraagvarianten plan
    python -m doublecheck.vraagvarianten kopie --naar data/vraagvorm/kopie.db
    python -m doublecheck.vraagvarianten importeren --db data/vraagvorm/kopie.db
    python -m doublecheck.vraagvarianten stilte --pool data/stiltetoets

`stilte` zoekt de gewone webtekst van een stiltepool die een nieuwe variant
dichter nadert dan `text_related`; alleen die kan een ander antwoord krijgen.
Die gaan door `/resolve` op productie en op de kopie; een `matched` die er op
de kopie bijkomt, gaat naar de leesproef.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from doublecheck.vraagvorm import als_bewering, is_vraag

GENERATOR = "regel"
# v2 (2026-10-16, gegroeid op de ontwikkelhelft): aan de claimkant ook het
# Singalese vraagpartikel ද (los of aan het laatste woord).
PROMPTVERSIE = "vraagvorm-v2"
_SINGALEES = re.compile(r"[\u0D80-\u0DFF]")
_SINGALEES_PARTIKEL = re.compile(r"\s*\u0DAF$")
PORTIE = 512


class Weigering(Exception):
    """De import doet iets niet, met de reden erbij."""


def als_bewering_claim(tekst: str) -> str:
    """De claimtekst als bewering: de regel van #25.36, en in het Singalees
    ook het vraagpartikel ද aan het eind. Alleen voor claimteksten (#25.37);
    de uitgebrachte invoerregel verandert niet."""
    uit = als_bewering(tekst)
    if uit != tekst and _SINGALEES.search(uit):
        kaal = _SINGALEES_PARTIKEL.sub("", uit.rstrip())
        if kaal.strip():
            return kaal
    return uit


def varianten(conn) -> list[tuple[str, str, str]]:
    """(claim_id, taal, varianttekst) voor elke claim die als vraag is
    opgeschreven en waar de regel iets aan verandert."""
    uit = []
    for claim_id, tekst, taal in conn.execute("SELECT claim_id, canonical_text, language FROM claim ORDER BY claim_id"):
        if not tekst or not is_vraag(tekst):
            continue
        variant = als_bewering_claim(tekst).strip()
        if variant and variant != tekst.strip():
            uit.append((claim_id, taal or "und", variant))
    return uit


def importeer(conn, rijen: list[tuple[str, str, str]], vingerafdrukken, versie: str) -> int:
    """De varianten in `claim_variant` van déze database, met herkomst en
    modelversie (DR6). Herhaalbaar: wat er van deze regel en dit model stond,
    wordt vervangen. Geeft het aantal ingevoegde varianten."""
    from doublecheck.storage import save_variant

    with conn:
        # Eén regelset tegelijk: ook een eerdere versie van de regel gaat eruit.
        conn.execute("DELETE FROM claim_variant WHERE model_version = ? AND generator = ?", (versie, GENERATOR))
        for begin in range(0, len(rijen), PORTIE):
            portie = rijen[begin:begin + PORTIE]
            for (claim_id, taal, tekst), vingerafdruk in zip(portie, vingerafdrukken([r[2] for r in portie], versie)):
                save_variant(conn, claim_id, taal, tekst, GENERATOR, PROMPTVERSIE, vingerafdruk)
    return len(rijen)


def boven_drempel(web, nieuw, grens: float, *, blok: int = 8192):
    """Per webtekst de hoogste gelijkenis met een nieuwe variant, en de
    teksten op of boven `grens`."""
    import numpy as np

    hoogste = np.full(len(web), -1.0, dtype=np.float32)
    for start in range(0, len(web), blok):
        hoogste[start:start + blok] = (web[start:start + blok] @ nieuw.T).max(axis=1)
    return hoogste, np.nonzero(hoogste >= grens)[0]


def stilte(pool: Path, kopie: Path, productie: Path, config, uitpad: Path) -> list[dict]:
    """De webtekst bij de nieuwe varianten door `/resolve`, op productie en
    op de kopie, met de rest van de config zoals hij is."""
    import json
    import sqlite3

    import numpy as np
    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.storage import connect
    from doublecheck.variantenbatch import lees_regels, lees_vectoren

    versie = config.model_versions.text_embedding
    rijen = lees_regels(pool)
    _, web = lees_vectoren(pool, versie)
    lees = sqlite3.connect(f"file:{kopie}?mode=ro", uri=True)
    nieuw = np.vstack([np.frombuffer(p, dtype=np.float32) for (p,) in lees.execute(
        "SELECT payload FROM claim_variant WHERE generator = ? AND prompt_version = ? AND model_version = ?",
        (GENERATOR, PROMPTVERSIE, versie))])
    _, boven = boven_drempel(np.asarray(web, dtype=np.float32), nieuw, config.thresholds.text_related)
    print(f"{len(rijen)} stukken in {pool}; {len(boven)} op of boven {config.thresholds.text_related} bij een nieuwe"
          " variant", flush=True)
    verbindingen = {"productie": connect(productie), "kopie": connect(kopie)}
    huidig = {"db": "productie"}

    def verbinding():
        yield verbindingen[huidig["db"]]

    api.app.dependency_overrides[api.get_conn] = verbinding
    was = api.limiter.enabled
    api.limiter.enabled = False
    uit = []
    try:
        client = TestClient(api.app)
        for i in boven:
            tekst = rijen[i]["varianten"][0]["tekst"]
            regel = {"stuk": rijen[i]["claim_id"]}
            for db in ("productie", "kopie"):
                huidig["db"] = db
                antwoord = client.post("/resolve", json={"text": tekst})
                if antwoord.status_code != 200:
                    raise RuntimeError(f"{rijen[i]['claim_id']}: resolve {antwoord.status_code} op {db}")
                d = antwoord.json()
                regel[db] = {"categorie": d.get("category"), "claim": (d.get("claim") or {}).get("id"),
                             "gelijkenis": d.get("similarity")}
            uit.append(regel)
    finally:
        api.app.dependency_overrides.pop(api.get_conn, None)
        api.limiter.enabled = was
        for c in verbindingen.values():
            c.close()
    uitpad.parent.mkdir(parents=True, exist_ok=True)
    uitpad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    return uit


def controleer_doel(pad: Path, *, release: bool = False) -> None:
    """Weigert de database van de resolver: daar komen de varianten pas met
    een release (B22), en dan met `--release`."""
    productie = Path(os.environ.get("DOUBLECHECK_DB", "doublecheck.db")).resolve()
    if not release and Path(pad).resolve() == productie:
        raise Weigering(f"{pad} is de database van de resolver; varianten komen daar pas met een release (B22)")


def main() -> None:
    import argparse
    import sqlite3
    from collections import Counter

    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="De vraag-claims ook als bewering in de index (#25.37)")
    parser.add_argument("stap", choices=("plan", "kopie", "importeren", "stilte"))
    parser.add_argument("--pool", default="data/stiltetoets", help="bij stilte: de map met regels en vectoren")
    parser.add_argument("--naar", default="data/vraagvorm/kopie.db", help="bij kopie: waar de kopie komt")
    parser.add_argument("--db", default="data/vraagvorm/kopie.db", help="bij importeren: de kopie")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--release", action="store_true",
                        help="bij importeren: ook in de database van de resolver, als onderdeel van een release (B22)")
    args = parser.parse_args()

    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    if args.stap == "plan":
        conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
        rijen = varianten(conn)
        print(f"{len(rijen)} varianten; per taal: {dict(Counter(t for _, t, _ in rijen).most_common(12))}")
    elif args.stap == "kopie":
        doel = Path(args.naar)
        controleer_doel(doel)
        doel.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(f"file:{bron}?mode=ro", uri=True) as van, sqlite3.connect(doel) as naar:
            van.backup(naar)
        print(f"kopie van {bron} naar {doel}")
    elif args.stap == "stilte":
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        pool = Path(args.pool)
        uit = stilte(pool, Path(args.db), Path(bron), load_config(),
                     Path("data/vraagvorm/metingen") / f"stilte-varianten-{pool.name}.jsonl")
        nieuw = [r for r in uit if r["kopie"]["categorie"] == "matched" and r["productie"]["categorie"] != "matched"]
        anders = [r for r in uit if r["kopie"]["categorie"] != r["productie"]["categorie"]]
        print(f"{len(uit)} door /resolve; matched productie {sum(r['productie']['categorie'] == 'matched' for r in uit)},"
              f" kopie {sum(r['kopie']['categorie'] == 'matched' for r in uit)}; nieuw matched {len(nieuw)};"
              f" ander antwoord {len(anders)}")
        for r in anders:
            print("  ", r)
    else:
        try:
            controleer_doel(Path(args.db), release=args.release)
        except Weigering as reden:
            raise SystemExit(f"geweigerd: {reden}")
        import torch
        from threadpoolctl import threadpool_limits

        from doublecheck.embedding import fingerprint_texts
        from doublecheck.storage import connect

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        conn = connect(args.db)
        n = importeer(conn, varianten(conn), fingerprint_texts, load_config().model_versions.text_embedding)
        print(f"{n} varianten in {args.db} ({GENERATOR}/{PROMPTVERSIE})")


if __name__ == "__main__":
    main()
