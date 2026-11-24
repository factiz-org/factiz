"""Claimvarianten voor het hele corpus, via de Batch API (PLAN.md #25.17).

Besluit van de PO (2026-10-11): alleen vertalingen, in vijf talen. De regel
was "Engels plus de vier talen met de meeste checks"; dat zijn Portugees,
Spaans, Telugu en Tamil. Op de proefvarianten nagerekend vinden alleen die
vertalingen 24,5% van de natuurlijke parafrasen, tegen 26,0% voor de hele
proef met 14,7 varianten per claim (BENCHMARK §77g).

Dit is de stap die geld uitgeeft van een persoonlijke sleutel (#23.9), dus
drie regels zijn hard:

- **Eerst een proefbatch.** Die meet de echte kosten per claim; zolang hij
  niet is opgehaald gaat er niets anders weg.
- **Binnen het budget.** Uitgegeven plus gemeten kosten per claim maal wat
  nog openstaat moet onder het budget blijven, anders weigert de run.
- **Nooit blind opnieuw.** Vóór het indienen komt een markering in de stand,
  erna het batch-id. Valt het proces daartussen weg, dan weet niemand of die
  batch loopt; de run weigert tot iemand het met `batches.list()` nagaat.

Een gebruikersvraag gaat nooit naar buiten (DR3, B26): dit draait offline op
openbare claimtekst. De vingerafdrukken blijven buiten de productie-index,
naast de regels, tot de benchmark met varianten voor het hele corpus is
gemeten; in de index komen ze pas met een release (B22).

    python -m doublecheck.variantenbatch plan
    python -m doublecheck.variantenbatch indienen [--budget 30]
    python -m doublecheck.variantenbatch ophalen
    python -m doublecheck.variantenbatch embedden [--deel 0/2]
    python -m doublecheck.variantenbatch meten
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np

from doublecheck.varianten import MODEL, _SYSTEEM, lees_antwoord

TALEN = ("en", "pt", "es", "te", "ta")
PROMPTVERSIE = "vertalingen-v1"
PROEFGROOTTE = 2_000
PORTIE = 20_000
BUDGET = 30.0

# Dollar per miljoen tokens voor Claude Haiku 5.5 met de batchkorting (50%).
PRIJS_IN, PRIJS_UIT = 0.05, 0.25

_SCHEMA = {
    "type": "object",
    "properties": {
        "vertalingen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"taal": {"type": "string"}, "tekst": {"type": "string"}},
                "required": ["taal", "tekst"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["vertalingen"],
    "additionalProperties": False,
}


class Weigering(Exception):
    """De run doet iets niet, met de reden erbij."""


def doeltalen(taal: str | None) -> list[str]:
    return [t for t in TALEN if t != taal]


def verzoek(claim_id: str, tekst: str, taal: str | None) -> dict:
    """Eén batchverzoek. De opdracht is letterlijk die van de proef voor
    vertalingen, zodat de gemeten varianten en deze dezelfde soort zijn."""
    prompt = (
        f"Claim (language: {taal or 'unknown'}):\n{tekst}\n\n"
        f"Translate the claim into each of these languages: {', '.join(doeltalen(taal))}. "
        "One natural sentence each, as a person in that country would write it in a social media post."
    )
    return {
        "custom_id": claim_id,
        "params": {
            "model": MODEL,
            "max_tokens": 4000,
            "system": _SYSTEEM,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
        },
    }


# --- stand -------------------------------------------------------------------

def lees_stand(map_: Path) -> dict:
    pad = Path(map_) / "stand.json"
    if not pad.exists():
        return {"batches": [], "bezig": None}
    return json.loads(pad.read_text(encoding="utf-8"))


def schrijf_stand(map_: Path, stand: dict) -> None:
    map_ = Path(map_)
    map_.mkdir(parents=True, exist_ok=True)
    tijdelijk = map_ / "stand.json.tmp"
    tijdelijk.write_text(json.dumps(stand, indent=1, ensure_ascii=False), encoding="utf-8")
    tijdelijk.replace(map_ / "stand.json")


def lees_regels(map_: Path) -> list[dict]:
    pad = Path(map_) / "regels.jsonl"
    if not pad.exists():
        return []
    # Alleen afgemaakte regels: `ophalen` kan op dit moment nog schrijven.
    inhoud = pad.read_text(encoding="utf-8")
    inhoud = inhoud[:inhoud.rfind("\n") + 1]
    return [json.loads(r) for r in inhoud.splitlines() if r.strip()]


def _batchclaims(map_: Path, batch_id: str) -> list[list]:
    return json.loads((Path(map_) / f"batch-{batch_id}.json").read_text(encoding="utf-8"))


def _onderweg(map_: Path, stand: dict) -> set[str]:
    return {c[0] for b in stand["batches"] if not b["opgehaald"] for c in _batchclaims(map_, b["id"])}


def nog_te_doen(map_: Path, claims: list[tuple]) -> list[tuple]:
    """Claims zonder regel die niet in een lopende batch zitten. Een fout of
    verlopen verzoek heeft geen regel en komt dus vanzelf terug."""
    klaar = {r["claim_id"] for r in lees_regels(map_)}
    onderweg = _onderweg(map_, lees_stand(map_))
    return [c for c in claims if c[0] not in klaar and c[0] not in onderweg]


def kosten(regels: list[dict]) -> float:
    return sum(r["tokens"][0] * PRIJS_IN + r["tokens"][1] * PRIJS_UIT for r in regels) / 1e6


# --- indienen ------------------------------------------------------------------

def dien_volgende_in(client, map_: Path, claims: list[tuple], *, budget: float = BUDGET,
                     proefgrootte: int = PROEFGROOTTE, portie: int = PORTIE) -> str | None:
    """Dient de volgende portie in en geeft het batch-id terug, of `None` als
    er niets meer te doen is. `claims` is [(claim_id, tekst, taal)]."""
    map_ = Path(map_)
    stand = lees_stand(map_)
    if stand["bezig"]:
        raise Weigering(
            "een vorige indiening werd onderbroken vóór het batch-id bewaard was "
            f"({stand['bezig']}). Kijk met client.messages.batches.list() of die batch "
            "bestaat; zet daarna 'bezig' in stand.json op null.")
    open_ = nog_te_doen(map_, claims)
    if not open_:
        return None
    if not stand["batches"]:
        return _dien_in(client, map_, stand, open_[:proefgrootte], proef=True)
    if any(b["proef"] and not b["opgehaald"] for b in stand["batches"]):
        raise Weigering("de proefbatch is nog niet opgehaald; die meet eerst de echte kosten per claim")
    regels = lees_regels(map_)
    if not regels:
        raise Weigering("de proefbatch leverde geen enkele regel op; geen kosten per claim te meten")
    uitgegeven = kosten(regels)
    per_claim = uitgegeven / len(regels)
    zonder_regel = len(claims) - len({r["claim_id"] for r in regels})
    verwacht = uitgegeven + per_claim * zonder_regel
    if verwacht > budget:
        raise Weigering(
            f"verwachte kosten ${verwacht:.2f} (uitgegeven ${uitgegeven:.2f}, ${per_claim:.5f} per claim)"
            f" gaan over het budget van ${budget:.2f}")
    return _dien_in(client, map_, stand, open_[:portie], proef=False)


def _dien_in(client, map_: Path, stand: dict, portie: list[tuple], *, proef: bool) -> str:
    nu = dt.datetime.now().isoformat(timespec="seconds")
    stand["bezig"] = {"claims": len(portie), "proef": proef, "sinds": nu}
    schrijf_stand(map_, stand)
    try:
        batch = client.messages.batches.create(
            requests=[verzoek(cid, tekst, taal) for cid, tekst, taal in portie])
    except Exception as fout:
        # Met een HTTP-antwoord weet je zeker dat er geen batch is; bij een
        # time-out niet, dan blijft de markering staan.
        if getattr(fout, "status_code", None) is not None:
            stand["bezig"] = None
            schrijf_stand(map_, stand)
        raise
    (map_ / f"batch-{batch.id}.json").write_text(
        json.dumps([list(c) for c in portie], ensure_ascii=False), encoding="utf-8")
    stand["batches"].append({"id": batch.id, "aantal": len(portie), "proef": proef,
                             "opgehaald": False, "ingediend": nu})
    stand["bezig"] = None
    schrijf_stand(map_, stand)
    return batch.id


# --- ophalen -------------------------------------------------------------------

def _regel(uitslag, claim: list, batch_id: str) -> dict:
    claim_id, tekst, taal = claim
    bericht = uitslag.result.message
    regel = {"claim_id": claim_id, "batch": batch_id, "model": MODEL, "prompt": PROMPTVERSIE,
             "tokens": [bericht.usage.input_tokens, bericht.usage.output_tokens],
             "geweigerd": bericht.stop_reason == "refusal", "onleesbaar": False, "varianten": []}
    if regel["geweigerd"]:
        return regel
    teksten = [b.text for b in bericht.content if getattr(b, "type", "") == "text"]
    try:
        varianten = lees_antwoord(teksten[0], tekst, taal) if teksten else []
    except (json.JSONDecodeError, AttributeError, TypeError):
        regel["onleesbaar"] = True
        return regel
    gevraagd = set(doeltalen(taal))
    regel["varianten"] = [v.__dict__ for v in varianten if v.taal in gevraagd]
    return regel


def haal_op(client, map_: Path) -> dict:
    """Haalt elke afgeronde batch binnen: per geslaagde claim één regel.
    Fout, verlopen of geannuleerd krijgt geen regel en gaat dus opnieuw mee."""
    map_ = Path(map_)
    stand = lees_stand(map_)
    klaar = {r["claim_id"] for r in lees_regels(map_)}
    telling = {"regels": 0, "zonder regel": 0, "lopend": 0}
    for batch in stand["batches"]:
        if batch["opgehaald"]:
            continue
        if client.messages.batches.retrieve(batch["id"]).processing_status != "ended":
            telling["lopend"] += 1
            continue
        claims = {c[0]: c for c in _batchclaims(map_, batch["id"])}
        with (map_ / "regels.jsonl").open("a", encoding="utf-8") as uit:
            for uitslag in client.messages.batches.results(batch["id"]):
                if uitslag.result.type != "succeeded" or uitslag.custom_id in klaar:
                    telling["zonder regel"] += uitslag.result.type != "succeeded"
                    continue
                uit.write(json.dumps(_regel(uitslag, claims[uitslag.custom_id], batch["id"]),
                                     ensure_ascii=False) + "\n")
                klaar.add(uitslag.custom_id)
                telling["regels"] += 1
        batch["opgehaald"] = True
        schrijf_stand(map_, stand)
    return telling


# --- embedden ------------------------------------------------------------------

def _plat(map_: Path) -> list[tuple[str, str, str]]:
    return [(r["claim_id"], v["taal"], v["tekst"]) for r in lees_regels(map_) for v in r["varianten"]]


def _vectormap(map_: Path, versie: str) -> Path:
    return Path(map_) / "vectoren" / hashlib.sha1(versie.encode("utf-8")).hexdigest()[:12]


def embed(map_: Path, versie: str, vingerafdruk, *, portie: int = 4096, deel=(0, 1)) -> int:
    """Embedt de varianten in porties van vaste plaats. Een portie die er al
    volledig staat wordt overgeslagen; een korte staart wordt opnieuw gedaan
    zodra er regels bij zijn. `deel=(i, n)` doet elke n-de portie, zodat twee
    processen naast elkaar kunnen werken. Geeft het aantal nieuw embedde
    varianten terug."""
    plat = _plat(map_)
    doel = _vectormap(map_, versie)
    doel.mkdir(parents=True, exist_ok=True)
    meta = {"versie": versie, "portie": portie}
    bestaand = doel / "meta.json"
    if bestaand.exists() and json.loads(bestaand.read_text(encoding="utf-8")) != meta:
        raise Weigering(f"de vectoren in {doel} hebben {bestaand.read_text(encoding='utf-8')}, niet {meta}")
    bestaand.write_text(json.dumps(meta), encoding="utf-8")
    nieuw = 0
    for nummer, start in enumerate(range(0, len(plat), portie)):
        if nummer % deel[1] != deel[0]:
            continue
        pad = doel / f"{start:08d}.npy"
        verwacht = min(portie, len(plat) - start)
        if pad.exists() and np.load(pad, mmap_mode="r").shape[0] == verwacht:
            continue
        teksten = [t for _, _, t in plat[start:start + verwacht]]
        matrix = np.vstack([f.vector for f in vingerafdruk(teksten, versie)]).astype(np.float32)
        tijdelijk = doel / f"{start:08d}.tmp.npy"
        np.save(tijdelijk, matrix)
        tijdelijk.replace(pad)
        nieuw += verwacht
    return nieuw


def lees_vectoren(map_: Path, versie: str):
    """De varianten en hun vectoren voor deze modelversie, zover ze aaneen
    gesloten klaar zijn: [(claim_id, taal, tekst)] en een matrix."""
    doel = _vectormap(map_, versie)
    if not (doel / "meta.json").exists():
        return [], np.empty((0, 0), dtype=np.float32)
    meta = json.loads((doel / "meta.json").read_text(encoding="utf-8"))
    if meta["versie"] != versie:  # pragma: no cover - sha1-botsing
        raise Weigering(f"{doel} hoort bij {meta['versie']}, niet bij {versie}")
    portie = meta["portie"]
    plat = _plat(map_)
    blokken = []
    for start in range(0, len(plat), portie):
        pad = doel / f"{start:08d}.npy"
        verwacht = min(portie, len(plat) - start)
        if not pad.exists():
            break
        blok = np.load(pad)
        if blok.shape[0] != verwacht:
            break
        blokken.append(blok)
    if not blokken:
        return [], np.empty((0, 0), dtype=np.float32)
    matrix = np.vstack(blokken)
    return plat[:matrix.shape[0]], matrix


def alleen_bestaande(varianten: list[tuple], matrix: np.ndarray, claims: set[str]):
    """Alleen varianten van claims die nog in de index staan; na het opruimen
    (#25.19) zitten er claims in de batches die er niet meer zijn."""
    houd = [i for i, (claim_id, _, _) in enumerate(varianten) if claim_id in claims]
    return [varianten[i] for i in houd], matrix[houd] if len(varianten) else matrix


def importeer(conn, map_: Path, versie: str) -> int:
    """De gemeten varianten in de index (`claim_variant`), met herkomst en
    modelversie (DR6). Herhaalbaar: wat er van dezelfde generator, promptversie
    en modelversie stond, wordt vervangen. Claims die niet meer in de index
    staan (#25.19) slaan we over. Geeft het aantal ingevoegde varianten."""
    import numpy as np  # noqa: F401  (lees_vectoren levert numpy-rijen)

    from doublecheck.embedding import TextFingerprint
    from doublecheck.storage import save_variant

    herkomst = [(r.get("model", MODEL), r.get("prompt", PROMPTVERSIE))
                for r in lees_regels(map_) for _ in r["varianten"]]
    rijen, matrix = lees_vectoren(map_, versie)
    bestaand = {rij[0] for rij in conn.execute("SELECT claim_id FROM claim")}
    with conn:
        for generator, prompt in set(herkomst[:len(rijen)]):
            conn.execute("DELETE FROM claim_variant WHERE model_version = ? AND generator = ?"
                         " AND prompt_version = ?", (versie, generator, prompt))
        ingevoegd = 0
        for (claim_id, taal, tekst), (generator, prompt), vector in zip(rijen, herkomst, matrix):
            if claim_id not in bestaand:
                continue
            save_variant(conn, claim_id, taal, tekst, generator, prompt, TextFingerprint(vector, versie))
            ingevoegd += 1
    return ingevoegd


# --- opdrachtregel -------------------------------------------------------------

def _corpusclaims(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(
        "SELECT claim_id, canonical_text, language FROM claim ORDER BY claim_id")]


def _plan(map_: Path, claims: list[tuple], budget: float) -> None:
    stand = lees_stand(map_)
    regels = lees_regels(map_)
    onderweg = _onderweg(map_, stand)
    open_ = nog_te_doen(map_, claims)
    print(f"claims {len(claims)} · met regel {len(regels)} · onderweg {len(onderweg)} · nog in te dienen {len(open_)}")
    if regels:
        uitgegeven = kosten(regels)
        per_claim = uitgegeven / len(regels)
        varianten = sum(len(r["varianten"]) for r in regels)
        print(f"uitgegeven ${uitgegeven:.2f} · ${per_claim:.5f} per claim · verwacht totaal"
              f" ${uitgegeven + per_claim * (len(claims) - len(regels)):.2f} (budget ${budget:.2f})")
        print(f"varianten {varianten} ({varianten / len(regels):.2f} per claim) · geweigerd"
              f" {sum(r['geweigerd'] for r in regels)} · onleesbaar {sum(r['onleesbaar'] for r in regels)}")
    elif stand["batches"]:
        print("de proefbatch loopt; 'ophalen' haalt hem binnen zodra hij klaar is")
    else:
        print(f"nog niets gemeten; de eerste indiening is een proefbatch van {PROEFGROOTTE} claims")
    if stand["bezig"]:
        print(f"LET OP: onderbroken indiening {stand['bezig']}; zie de uitleg bij 'indienen'")


def _meet(map_: Path, conn, config, feed: str) -> None:
    from doublecheck.natuurlijk import groepen_uit_feed
    from doublecheck.testset import load_test_pairs
    from doublecheck.varianten import _benchmark, _meet_parafrasen

    versie = config.model_versions.text_embedding
    varianten, varmatrix = lees_vectoren(map_, versie)
    tekst_van = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    varianten, varmatrix = alleen_bestaande(varianten, varmatrix, set(tekst_van))
    taal_van = dict(conn.execute("SELECT claim_id, language FROM claim"))
    rijen = conn.execute("SELECT claim_id, payload FROM fingerprint WHERE kind = 'text'"
                         " AND model_version = ?", (versie,)).fetchall()
    claimmatrix = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rijen])
    rij_claim = [r[0] for r in rijen]
    rij_tekst = [tekst_van[c] for c in rij_claim]
    rij_taal = [taal_van[c] for c in rij_claim]
    claimrij = {c: i for i, c in enumerate(rij_claim)}
    gedekt = len({c for c, _, _ in varianten})
    print(f"varianten met vingerafdruk: {len(varianten)} van {gedekt} claims", flush=True)
    groepen = groepen_uit_feed(conn, feed)
    paren = load_test_pairs(conn)
    talen = {}
    for naam, (matrix, rc, rt, rl) in (
        ("zonder varianten", (claimmatrix, rij_claim, rij_tekst, rij_taal)),
        ("met varianten", (np.vstack([claimmatrix, varmatrix]) if len(varianten) else claimmatrix,
                           rij_claim + [c for c, _, _ in varianten],
                           rij_tekst + [t for _, _, t in varianten],
                           rij_taal + [taal for _, taal, _ in varianten])),
    ):
        tel, per_soort, talen[naam] = _meet_parafrasen(matrix, rc, rt, rl, groepen, claimrij, config.thresholds)
        n = sum(tel.values())
        regel = " · ".join(f"{s} {c['gevonden'] / max(sum(c.values()), 1):.1%} (n={sum(c.values())})"
                          for s, c in sorted(per_soort.items()))
        print(f"  {naam:17} gevonden {tel['gevonden'] / n:.1%} · ander record {tel['ander record']}"
              f" · tegenspraak {tel['tegenspraak']} · verwant {tel['verwant'] / n:.1%} · {regel}", flush=True)
        fouten, goed, zelfde = _benchmark(matrix, rc, rt, rl, paren, config.thresholds)
        print(f"  {'':17} benchmark: {fouten} fouten, dekking {goed}/{zelfde} ({goed / zelfde:.1%})", flush=True)
    # Per taal van de zoekvraag: zit de winst alleen in de vijf doeltalen?
    print("\n  per taal van de zoekvraag (gevonden, zonder -> met varianten):")
    zonder, met = talen["zonder varianten"], talen["met varianten"]
    for taal in sorted(zonder, key=lambda t: -sum(zonder[t].values()))[:20]:
        n = sum(zonder[taal].values())
        doel = "  (doeltaal)" if taal in TALEN else ""
        print(f"    {taal:5} n={n:4}  {zonder[taal]['gevonden'] / n:6.1%} -> {met[taal]['gevonden'] / n:6.1%}{doel}")


def main() -> None:
    import argparse
    import os
    import sqlite3

    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="Claimvarianten voor het hele corpus (#25.17)")
    parser.add_argument("stap", choices=("plan", "indienen", "ophalen", "embedden", "meten", "importeren"))
    parser.add_argument("--map", default="data/varianten/corpus")
    parser.add_argument("--budget", type=float, default=BUDGET)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--deel", default="0/1", help="i/n: elke n-de portie vanaf i")
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    args = parser.parse_args()

    map_ = Path(args.map)
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    claims = _corpusclaims(conn)
    config = load_config()

    if args.stap == "plan":
        _plan(map_, claims, args.budget)
    elif args.stap in ("indienen", "ophalen"):
        import anthropic

        laad_sleutel()
        client = anthropic.Anthropic()
        if args.stap == "indienen":
            try:
                batch_id = dien_volgende_in(client, map_, claims, budget=args.budget)
            except Weigering as reden:
                raise SystemExit(f"geweigerd: {reden}")
            print(f"ingediend: {batch_id}" if batch_id else "niets meer in te dienen")
        else:
            print(haal_op(client, map_))
        _plan(map_, claims, args.budget)
    elif args.stap == "embedden":
        import torch
        from threadpoolctl import threadpool_limits

        from doublecheck.embedding import fingerprint_texts

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        i, n = (int(x) for x in args.deel.split("/"))
        nieuw = embed(map_, config.model_versions.text_embedding, fingerprint_texts, deel=(i, n))
        print(f"nieuw embed: {nieuw}")
    elif args.stap == "importeren":
        from doublecheck.storage import connect, init_schema

        schrijf = connect(bron)
        init_schema(schrijf)
        n = importeer(schrijf, map_, config.model_versions.text_embedding)
        print(f"geïmporteerd: {n} varianten in claim_variant ({config.model_versions.text_embedding})")
    else:
        _meet(map_, conn, config, args.feed)


if __name__ == "__main__":
    main()
