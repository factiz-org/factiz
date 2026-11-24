"""Claimvarianten aan de kant van de index (PLAN.md #25.17, B26).

De zwakke plek van laag 1 is hoe verschillend mensen dezelfde claim
opschrijven, en vooral over taalgrenzen: van twee redacties die dezelfde
post checkten in verschillende talen, vindt de motor er 4,1% (#25.14d e).
Hier schrijft een frontiermodel (Claude Haiku 5.5) offline, op openbare
CC BY-claimtekst, extra formuleringen van elke gecheckte claim: vertalingen
en de vormen waarin een post haar zou brengen. Het lokale model maakt er
vingerafdrukken van.

Een gebruikersvraag gaat nooit naar een externe dienst (DR3, B26): de
varianten liggen in de index, het zoeken blijft lokaal. Een variant die een
getal verandert of laat vallen, valt weg: anders smokkelt een vertaling een
cijferwissel binnen die de tegenspraakcontrole juist moet tegenhouden (DR8).

Dit is de proef. Varianten komen pas in productie na een gemeten winst op de
natuurlijke parafrasen zonder extra foute koppelingen, en dat is een release
(B22).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from doublecheck.relation import extract_numbers

MODEL = "claude-haiku-5-5"
PROMPTVERSIE = "varianten-v1"

# Vaste doeltalen, onafhankelijk van wie er later zoekt: de grootste talen
# van het corpus en de Zuid-Aziatische talen waar de kloof het grootst is.
DOELTALEN = ("en", "hi", "te", "ta", "bn", "ml", "kn", "mr",
             "pt", "es", "fr", "de", "nl", "ar", "fa")

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
        "formuleringen": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["vertalingen", "formuleringen"],
    "additionalProperties": False,
}

_SYSTEEM = (
    "You rewrite claims that fact-checkers have checked, so that a search engine can recognise "
    "the same claim when it circulates in other words or other languages. You never judge whether "
    "a claim is true, and you never correct it: you restate the claim itself. Keep every name, "
    "number, date and negation exactly as in the original."
)


def doeltalen(taal: str | None) -> list[str]:
    return [t for t in DOELTALEN if t != taal]


@dataclass(frozen=True)
class Variant:
    soort: str  # "vertaling" of "formulering"
    taal: str
    tekst: str


@dataclass
class Uitslag:
    varianten: list[Variant] = field(default_factory=list)
    geweigerd: bool = False
    invoer_tokens: int = 0
    uitvoer_tokens: int = 0


def _prompt(tekst: str, taal: str | None) -> str:
    talen = ", ".join(doeltalen(taal))
    return (
        f"Claim (language: {taal or 'unknown'}):\n{tekst}\n\n"
        f"1. Translate the claim into each of these languages: {talen}. One natural sentence each, "
        "as a person in that country would write it in a social media post.\n"
        "2. Write three rewrites in the claim's own language, the way the claim circulates: as a "
        "quote of what someone said, as a short headline, and as a casual post. Same meaning, other words."
    )


def lees_antwoord(antwoord: str, origineel: str, taal: str | None) -> list[Variant]:
    """Houdt alleen bruikbare varianten: niet leeg, niet gelijk aan de claim,
    en met precies dezelfde getallen."""
    data = json.loads(antwoord)
    getallen = extract_numbers(origineel)
    gezien = {origineel.strip().casefold().rstrip(".")}
    uit = []
    kandidaten = [("vertaling", v.get("taal", ""), v.get("tekst", "")) for v in data.get("vertalingen", [])]
    kandidaten += [("formulering", taal or "und", t) for t in data.get("formuleringen", [])]
    for soort, doel, tekst in kandidaten:
        tekst = (tekst or "").strip()
        sleutel = tekst.casefold().rstrip(".")
        if not tekst or sleutel in gezien:
            continue
        if extract_numbers(tekst) != getallen:
            continue
        gezien.add(sleutel)
        uit.append(Variant(soort, doel, tekst))
    return uit


def genereer(client, tekst: str, taal: str | None) -> Uitslag:
    """Eén verzoek per claim. Een weigering wordt geteld, niet verzwegen."""
    antwoord = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=_SYSTEEM,
        messages=[{"role": "user", "content": _prompt(tekst, taal)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    uitslag = Uitslag(invoer_tokens=getattr(antwoord.usage, "input_tokens", 0),
                      uitvoer_tokens=getattr(antwoord.usage, "output_tokens", 0))
    if antwoord.stop_reason == "refusal":
        uitslag.geweigerd = True
        return uitslag
    teksten = [b.text for b in antwoord.content if getattr(b, "type", "") == "text"]
    if not teksten:
        return uitslag
    try:
        uitslag.varianten = lees_antwoord(teksten[0], tekst, taal)
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return uitslag


def beste_zonder(vraagrij: int, eigen: list[str], matrix: np.ndarray, rij_claim: list[str]):
    """De beste rij voor de zoekvraag, zonder de claim zelf én zonder zijn
    eigen varianten: anders vindt de toets zichzelf terug."""
    sims = matrix @ matrix[vraagrij]
    uitsluiten = np.isin(np.asarray(rij_claim), eigen)
    sims[uitsluiten] = -np.inf
    rij = int(np.argmax(sims))
    return rij_claim[rij], float(sims[rij]), rij


def laad_sleutel(pad: str = ".env") -> None:
    """Zet de variabelen uit `.env` in de omgeving, zonder ze te tonen."""
    import os
    from pathlib import Path

    if not Path(pad).exists():
        return
    for regel in Path(pad).read_text(encoding="utf-8").splitlines():
        regel = regel.strip()
        if regel and not regel.startswith("#") and "=" in regel:
            sleutel, waarde = regel.split("=", 1)
            os.environ.setdefault(sleutel.strip(), waarde.strip().strip('"').strip("'"))


def _meet_parafrasen(matrix, rij_claim, rij_tekst, rij_taal, groepen, claimrij, drempels):
    """De toets van #25.13 op een index met varianten: per zoekvraag de beste
    rij zonder de vraag zelf en zonder haar eigen varianten."""
    import collections

    from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations

    tel = collections.Counter()
    per_soort = collections.defaultdict(collections.Counter)
    per_taal = collections.defaultdict(collections.Counter)
    for groep in groepen:
        leden = [c for c in groep if c in claimrij]
        for a in leden:
            i = claimrij[a]
            beste, sim, rij = beste_zonder(i, [a], matrix, rij_claim)
            zelfde_taal = any(rij_taal[claimrij[b]] == rij_taal[i] for b in leden if b != a)
            soort = "zelfde taal" if zelfde_taal else "over talen"
            if sim >= drempels.text_match:
                if contradicts(extract_numbers(rij_tekst[i]), extract_negations(rij_tekst[i]), rij_tekst[rij],
                               artefact_text=rij_tekst[i],
                               artefact_negation_tokens=extract_negation_tokens(rij_tekst[i])):
                    uitkomst = "tegenspraak"
                else:
                    uitkomst = "gevonden" if beste in groep else "ander record"
            elif sim >= drempels.text_related:
                uitkomst = "verwant"
            else:
                uitkomst = "niets"
            tel[uitkomst] += 1
            per_soort[soort][uitkomst] += 1
            per_taal[rij_taal[i]][uitkomst] += 1
    return tel, per_soort, per_taal



def _benchmark(matrix, rij_claim, rij_tekst, rij_taal, paren, drempels) -> tuple[int, int, int]:
    """De testparen tegen een index met varianten, met de telregels van de
    benchmark: (foute koppelingen, juiste matches, zelfde-paren)."""
    from doublecheck.benchmark import _is_fout
    from doublecheck.categorize import Category, categorize
    from doublecheck.relation import contradicts
    from doublecheck.taal import zijn_verschillende_talen

    fouten = goed = zelfde = 0
    for paar in paren:
        if paar.kind != "text":
            continue
        sims = matrix @ paar.fingerprint.vector
        rij = int(np.argmax(sims))
        tegenspraak = contradicts(paar.fingerprint.numbers, paar.fingerprint.negations, rij_tekst[rij],
                                  artefact_negation_tokens=getattr(paar.fingerprint, "negation_tokens", None))
        cross = zijn_verschillende_talen(getattr(paar.fingerprint, "language", None), rij_taal[rij])
        cat = categorize(float(sims[rij]), drempels, contradiction=tegenspraak, crosslinguaal=cross)
        raak = cat.category is Category.MATCHED
        doel = rij_claim[rij] if raak else None
        fouten += _is_fout(paar, cat.category, doel)
        zelfde += paar.is_same
        goed += bool(raak and paar.is_same and doel == paar.claim_id)
    return fouten, goed, zelfde


def main() -> None:
    import argparse
    import concurrent.futures as cf
    import os
    import sqlite3
    import time
    from pathlib import Path

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.natuurlijk import groepen_uit_feed

    parser = argparse.ArgumentParser(description="Claimvarianten, de proef (#25.17)")
    parser.add_argument("--map", default="data/varianten")
    parser.add_argument("--gelijktijdig", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)
    laad_sleutel()

    config = load_config()
    versie = config.model_versions.text_embedding
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    groepen = groepen_uit_feed(conn, args.feed)
    proef = sorted(set().union(*groepen))
    tekst_van = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    taal_van = dict(conn.execute("SELECT claim_id, language FROM claim"))
    print(f"proefclaims: {len(proef)} uit {len(groepen)} parafrasegroepen", flush=True)

    # 1. Genereren, hervatbaar: elke claim één regel in het bestand.
    map_ = Path(args.map)
    map_.mkdir(parents=True, exist_ok=True)
    bestand = map_ / "proef-varianten.jsonl"
    klaar = set()
    if bestand.exists():
        klaar = {json.loads(r)["claim_id"] for r in bestand.read_text(encoding="utf-8").splitlines() if r}
    todo = [c for c in proef if c not in klaar]
    print(f"te genereren: {len(todo)} (al klaar: {len(klaar)})", flush=True)
    if todo:
        import anthropic

        client = anthropic.Anthropic()

        def een(cid):
            for poging in range(3):
                try:
                    return cid, genereer(client, tekst_van[cid], taal_van[cid])
                except anthropic.APIStatusError as fout:
                    if fout.status_code < 500 and fout.status_code != 429:
                        raise
                    time.sleep(5 * (poging + 1))
            return cid, Uitslag(geweigerd=True)

        start, gedaan = time.time(), 0
        with cf.ThreadPoolExecutor(args.gelijktijdig) as pool, bestand.open("a", encoding="utf-8") as uit:
            for cid, u in pool.map(een, todo):
                uit.write(json.dumps({"claim_id": cid, "geweigerd": u.geweigerd, "model": MODEL,
                                      "prompt": PROMPTVERSIE, "tokens": [u.invoer_tokens, u.uitvoer_tokens],
                                      "varianten": [v.__dict__ for v in u.varianten]},
                                     ensure_ascii=False) + "\n")
                gedaan += 1
                if gedaan % 100 == 0:
                    uit.flush()
                    print(f"  {gedaan}/{len(todo)} · {time.time() - start:.0f}s", flush=True)

    regels = [json.loads(r) for r in bestand.read_text(encoding="utf-8").splitlines() if r]
    invoer = sum(r["tokens"][0] for r in regels)
    uitvoer = sum(r["tokens"][1] for r in regels)
    geweigerd = sum(r["geweigerd"] for r in regels)
    varianten = [(r["claim_id"], v) for r in regels for v in r["varianten"]]
    print(f"varianten: {len(varianten)} · geweigerd: {geweigerd} · tokens in {invoer} uit {uitvoer}"
          f" · kosten ongeveer ${invoer * 0.10 / 1e6 + uitvoer * 0.50 / 1e6:.2f}", flush=True)

    # 2. Vingerafdrukken van de varianten, met het lokale model.
    vecbestand = map_ / f"proef-vectoren-{len(varianten)}.npy"
    if vecbestand.exists():
        varmatrix = np.load(vecbestand)
    else:
        blokken = []
        for start in range(0, len(varianten), 256):
            blok = [v["tekst"] for _, v in varianten[start:start + 256]]
            blokken.append(np.vstack([f.vector for f in fingerprint_texts(blok, versie)]))
            print(f"  embedden {start + len(blok)}/{len(varianten)}", flush=True)
        varmatrix = np.vstack(blokken)
        np.save(vecbestand, varmatrix)

    # 3. De index: alle claims, plus de varianten van de proefclaims.
    rijen = conn.execute("SELECT f.claim_id, f.payload FROM fingerprint f WHERE f.kind = 'text'"
                         " AND f.model_version = ?", (versie,)).fetchall()
    claimmatrix = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rijen])
    rij_claim = [r[0] for r in rijen]
    rij_tekst = [tekst_van[c] for c in rij_claim]
    rij_taal = [taal_van[c] for c in rij_claim]
    claimrij = {c: i for i, c in enumerate(rij_claim)}
    drempels = config.thresholds
    from doublecheck.testset import load_test_pairs

    prod = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    prod.row_factory = sqlite3.Row
    paren = load_test_pairs(prod)
    print("\nparafrasetoets en benchmark, zonder en met varianten:", flush=True)
    for naam, (matrix, rc, rt, rl) in (
        ("zonder varianten", (claimmatrix, rij_claim, rij_tekst, rij_taal)),
        ("met varianten", (np.vstack([claimmatrix, varmatrix]), rij_claim + [c for c, _ in varianten],
                           rij_tekst + [v["tekst"] for _, v in varianten],
                           rij_taal + [v["taal"] for _, v in varianten])),
    ):
        tel, per_soort, _ = _meet_parafrasen(matrix, rc, rt, rl, groepen, claimrij, drempels)
        n = sum(tel.values())
        regel = " · ".join(f"{s} {c['gevonden'] / max(sum(c.values()), 1):.1%} (n={sum(c.values())})"
                          for s, c in sorted(per_soort.items()))
        print(f"  {naam:17} gevonden {tel['gevonden'] / n:.1%} · ander record {tel['ander record']}"
              f" · tegenspraak {tel['tegenspraak']} · verwant {tel['verwant'] / n:.1%} · {regel}", flush=True)
        fouten, goed, zelfde = _benchmark(matrix, rc, rt, rl, paren, drempels)
        print(f"  {'':17} benchmark: {fouten} fouten, dekking {goed}/{zelfde} ({goed / zelfde:.1%})", flush=True)


if __name__ == "__main__":
    main()
