"""De stiltetoets: gewone berichten die nooit `matched` mogen geven (PLAN.md #28.6 g).

Pangram meet zijn valse alarmen op een miljoen menselijke teksten, en pas
die omvang maakt "bijna nooit" tot een getal: zonder fout in n proeven ligt
de eenzijdige 95%-bovengrens rond 3/n. Onze tegenhanger is de valse treffer:
`matched` op een bericht dat geen gecheckte bewering doet. Tot nu toe 0 op
1.000 screenshots, bovengrens 0,30%; dit maakt er ongeveer 300.000 van.

Alles hieronder is vastgelegd vóór er gemeten werd (PLAN #28.6 g):

- **bron**: mC4 (`allenai/c4`, ODC-BY), de validatiebestanden, in de 19
  talen met 95% van de claims. Webtekst op postlengte, geen echte posts;
- **verdeling**: naar het aandeel van de taal in het corpus, vloer 5.000;
- **knipregel**: alinea's van 60 tot 280 tekens, zonder link, met minstens
  60% letters of combinerende tekens, hoogstens drie per document, geen
  dubbelen;
- **meting**: alles embedden; wat met geen claim of variant boven de laagste
  drempel min `MARGE` uitkomt, kan nooit een treffer worden. De rest gaat
  door het echte `/resolve`, zodat de uitslag het productiepad is;
- **tellen**: elke `matched` gelabeld, terecht of vals, vóór de bovengrens
  berekend wordt. Op het web kan een stuk echt een gecheckte bewering doen.

De stukken blijven buiten git, net als de bronbestanden; alleen tellingen en
labels (per stuk-id) komen in de repo.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

REPO = "allenai/c4"
TALEN = ("en", "pt", "es", "te", "ta", "hi", "de", "fa", "nl", "ar",
         "fr", "si", "ml", "bn", "id", "zh", "kn", "ja", "tr")
MAP = Path("data/stiltetoets")
LABELS = Path("docs/steekproeven/28.6g-stiltetoets.json")

MIN_LENGTE, MAX_LENGTE = 60, 280   # de lengte van een post
MIN_LETTERS = 0.6
PER_DOCUMENT = 3
TOTAAL, VLOER = 300_000, 5_000
MARGE = 0.02

_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


class Weigering(Exception):
    pass


def _letteraandeel(tekst: str) -> float:
    """Letters én combinerende tekens: de klinkertekens van Devanagari zijn
    voor `isalpha` geen letters, en dan viel Hindi buiten de toets."""
    tekens = [c for c in tekst if not c.isspace()]
    if not tekens:
        return 0.0
    return sum(unicodedata.category(c)[0] in "LM" for c in tekens) / len(tekens)


def knip(tekst: str) -> list[str]:
    """De stukken op postlengte uit één document, volgens de vaste regel."""
    stukken: list[str] = []
    for alinea in tekst.split("\n"):
        alinea = " ".join(alinea.split())
        if not MIN_LENGTE <= len(alinea) <= MAX_LENGTE:
            continue
        if _LINK.search(alinea) or _letteraandeel(alinea) < MIN_LETTERS:
            continue
        if alinea not in stukken:
            stukken.append(alinea)
        if len(stukken) == PER_DOCUMENT:
            break
    return stukken


def stukken(documenten: Iterable[str], aantal: int, gezien: set[str]) -> list[str]:
    """Knipt documenten tot er `aantal` nieuwe stukken zijn; `gezien` houdt
    dubbelen over documenten en bestanden heen tegen."""
    uit: list[str] = []
    for document in documenten:
        for stuk in knip(document):
            if stuk in gezien:
                continue
            gezien.add(stuk)
            uit.append(stuk)
            if len(uit) == aantal:
                return uit
    return uit


def quota(aantallen: dict[str, int], *, totaal: int = TOTAAL, vloer: int = VLOER) -> dict[str, int]:
    """Naar het aandeel van de taal in het corpus, met een vloer, zodat een
    kleine taal genoeg stukken heeft voor een eigen bovengrens."""
    som = sum(aantallen.values())
    return {taal: max(vloer, round(totaal * n / som)) for taal, n in aantallen.items()}


def ondergrens(drempels) -> float:
    """Onder deze gelijkenis kan geen stuk `matched` of `related` worden."""
    return min(drempels.text_related, drempels.text_match, drempels.text_match_crosslingual) - MARGE


def lees_db(pad) -> sqlite3.Connection:
    """De database alleen-lezend, met rijen op kolomnaam zoals de zoekmatrix
    ze leest."""
    conn = sqlite3.connect(f"file:{pad}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def lees_documenten(pad: Path) -> Iterator[str]:
    with gzip.open(pad, "rt", encoding="utf-8") as f:
        for regel in f:
            if regel.strip():
                yield json.loads(regel)["text"]


def uitslag(treffers: list[dict], labels: dict[str, str], n_per_taal: dict[str, int]) -> dict:
    """Valse `matched` op n, per taal en in totaal, met de eenzijdige
    95%-bovengrens. Weigert zolang een `matched` geen label heeft."""
    from doublecheck.cijfers import _bovengrens

    ontbreekt = [t["stuk_id"] for t in treffers
                 if t["categorie"] == "matched" and labels.get(t["stuk_id"]) not in ("terecht", "vals")]
    if ontbreekt:
        raise Weigering(f"{len(ontbreekt)} keer `matched` zonder label (bijvoorbeeld {ontbreekt[:3]});"
                        f" label eerst in {LABELS}")

    def leeg(n: int) -> dict:
        return {"n": n, "matched": 0, "terecht": 0, "vals": 0, "related": 0}

    per_taal = {taal: leeg(n) for taal, n in n_per_taal.items()}
    totaal = leeg(sum(n_per_taal.values()))
    for t in treffers:
        for doel in (per_taal[t["taal"]], totaal):
            if t["categorie"] == "matched":
                doel["matched"] += 1
                doel[labels[t["stuk_id"]]] += 1
            elif t["categorie"] == "related":
                doel["related"] += 1
    for doel in (*per_taal.values(), totaal):
        doel["bovengrens"] = _bovengrens(doel["vals"], doel["n"])
    return {"per_taal": per_taal, "totaal": totaal}


# --- de stappen -------------------------------------------------------------

def kies_bestanden(namen: list[str], taal: str, *, overslaan=frozenset(), max_bestanden: int | None = None) -> list[str]:
    """De validatieshards van een taal, zonder wat een vorige ronde gebruikte
    (#25.32). Is er geen ongebruikte validatieshard meer, dan de
    trainingsshards, de eerste eerst: ook gewone webtekst, en nooit eerder
    gezien."""
    def gesorteerd(voorvoegsel):
        return sorted(n for n in namen if n.startswith(voorvoegsel) and n.endswith(".json.gz") and n not in overslaan)

    if taal == "en":
        validatie, training = gesorteerd("en/c4-validation."), gesorteerd("en/c4-train.")
    else:
        validatie = gesorteerd(f"multilingual/c4-{taal}-validation.")
        training = gesorteerd(f"multilingual/c4-{taal}.tfrecord-")
    gekozen = validatie or (training if overslaan else [])
    return gekozen[:max_bestanden] if max_bestanden else gekozen


def _bestanden(revisie: str, *, overslaan=frozenset(), max_bestanden: int | None = None) -> dict[str, list[str]]:
    from huggingface_hub import HfApi

    namen = sorted(HfApi().list_repo_files(REPO, repo_type="dataset", revision=revisie))
    return {taal: kies_bestanden(namen, taal, overslaan=overslaan, max_bestanden=max_bestanden) for taal in TALEN}


def ophalen(conn: sqlite3.Connection, map_: Path, *, totaal: int = TOTAAL, vloer: int = VLOER,
            vorige: Path | None = None) -> dict[str, int]:
    """Haalt per taal bestand na bestand op tot de quota vol is, knipt, en
    schrijft `regels.jsonl` in de vorm die het embedden verwacht.

    `vorige`: een verse ronde (#25.32). Dezelfde revisie, per taal één bestand
    dat de vorige ronde niet gebruikte, en geen stuk dat er al in zat."""
    from huggingface_hub import HfApi, hf_hub_download

    overslaan: set[str] = set()
    al_gezien: set[str] = set()
    max_bestanden = None
    if vorige is not None:
        oud = json.loads((vorige / "meta.json").read_text(encoding="utf-8"))
        revisie = oud["revisie"]
        overslaan = {f for lijst in oud["bestanden"].values() for f in lijst}
        al_gezien = {json.loads(r)["varianten"][0]["tekst"]
                     for r in (vorige / "regels.jsonl").read_text(encoding="utf-8").splitlines() if r}
        max_bestanden = 1
    else:
        revisie = HfApi().dataset_info(REPO).sha
    aantallen = dict(conn.execute(
        f"SELECT language, count(*) FROM claim WHERE language IN ({','.join('?' * len(TALEN))}) GROUP BY 1",
        TALEN).fetchall())
    doel = quota(aantallen, totaal=totaal, vloer=vloer)
    bestanden = _bestanden(revisie, overslaan=overslaan, max_bestanden=max_bestanden)
    map_.mkdir(parents=True, exist_ok=True)
    gekregen: dict[str, int] = {}
    gebruikt: dict[str, list[str]] = {}
    with (map_ / "regels.jsonl").open("w", encoding="utf-8") as uit:
        for taal in TALEN:
            gezien: set[str] = set(al_gezien)
            verzameld: list[str] = []
            for naam in bestanden[taal]:
                if len(verzameld) >= doel[taal]:
                    break
                pad = hf_hub_download(REPO, naam, repo_type="dataset", revision=revisie,
                                      local_dir=map_ / "bron")
                gebruikt.setdefault(taal, []).append(naam)
                verzameld += stukken(lees_documenten(Path(pad)), doel[taal] - len(verzameld), gezien)
            for i, stuk in enumerate(verzameld):
                uit.write(json.dumps({"claim_id": f"{taal}-{i:06d}", "taal": taal,
                                      "varianten": [{"taal": taal, "tekst": stuk}]}, ensure_ascii=False) + "\n")
            gekregen[taal] = len(verzameld)
            print(f"{taal}: {len(verzameld)} van {doel[taal]} uit {len(gebruikt.get(taal, []))} bestand(en)", flush=True)
    (map_ / "meta.json").write_text(json.dumps(
        {"bron": REPO, "revisie": revisie, "quota": doel, "gekregen": gekregen, "bestanden": gebruikt},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return gekregen


def voorselectie(conn: sqlite3.Connection, matrix, versie: str, grens: float, *, blok: int = 128):
    """De hoogste gelijkenis van elk stuk met alle claims én varianten (meer
    dan de resolver doorzoekt als de varianten uit staan, dus nooit te
    weinig), en de stukken op of boven `grens`."""
    import numpy as np

    from doublecheck.search import _gecachet, _tekstmatrix, _variantenmatrix

    _, claims = _gecachet(conn, ("text", versie), lambda: _tekstmatrix(conn, versie))
    _, _, varianten, _ = _gecachet(conn, ("variant", versie), lambda: _variantenmatrix(conn, versie))
    index = [m for m in (claims, varianten) if len(m)]
    hoogste = np.full(len(matrix), -1.0, dtype=np.float32)
    for start in range(0, len(matrix), blok):
        deel = matrix[start:start + blok]
        for m in index:
            hoogste[start:start + blok] = np.maximum(hoogste[start:start + blok], (deel @ m.T).max(axis=1))
    return hoogste, np.nonzero(hoogste >= grens)[0]


def door_resolver(kandidaten: list[dict]) -> list[dict]:
    """Het productiepad: `/resolve` met de tekst, zoals een gebruiker hem
    stuurt. Zonder snelheidsbegrenzing, en zonder de opstartstap (die ruimt
    verlopen betwistingen op; dat hoort niet bij een meting)."""
    from fastapi.testclient import TestClient

    from doublecheck import api

    api.limiter.enabled = False
    client = TestClient(api.app)
    uit = []
    for k in kandidaten:
        antwoord = client.post("/resolve", json={"text": k["tekst"]})
        antwoord.raise_for_status()
        d = antwoord.json()
        uit.append({**k, "categorie": d["category"], "gelijkenis": d["similarity"],
                    "claim_id": (d["claim"] or {}).get("id"), "via": d.get("via")})
    return uit


def _lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    return json.loads(LABELS.read_text(encoding="utf-8"))["labels"]


def main() -> None:
    import argparse
    import os

    import numpy as np

    from doublecheck.config import load_config
    from doublecheck.variantenbatch import embed, lees_regels, lees_vectoren

    parser = argparse.ArgumentParser(description="De stiltetoets (PLAN #28.6 g)")
    parser.add_argument("stap", choices=("ophalen", "embedden", "meten", "tellen"))
    parser.add_argument("--map", default=str(MAP))
    parser.add_argument("--totaal", type=int, default=TOTAAL)
    parser.add_argument("--vloer", type=int, default=VLOER)
    parser.add_argument("--deel", default="0/1")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--vorige", help="verse ronde (#25.32): de map van de vorige, die wordt overgeslagen")
    args = parser.parse_args()
    config = load_config()
    versie = config.model_versions.text_embedding
    map_ = Path(args.map)
    db = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")

    if args.stap == "ophalen":
        conn = lees_db(db)
        gekregen = ophalen(conn, map_, totaal=args.totaal, vloer=args.vloer,
                           vorige=Path(args.vorige) if args.vorige else None)
        print(f"samen {sum(gekregen.values())} stukken in {map_ / 'regels.jsonl'}")
    elif args.stap == "embedden":
        import torch
        from threadpoolctl import threadpool_limits

        from doublecheck.embedding import fingerprint_texts

        threadpool_limits(limits=args.threads)
        torch.set_num_threads(args.threads)
        i, n = (int(x) for x in args.deel.split("/"))
        print(f"nieuw embed: {embed(map_, versie, fingerprint_texts, deel=(i, n))}", flush=True)
    elif args.stap == "meten":
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=args.threads)
        rijen = lees_regels(map_)
        _, matrix = lees_vectoren(map_, versie)
        if len(matrix) < len(rijen):
            raise Weigering(f"{len(matrix)} van {len(rijen)} stukken embed; eerst `embedden` afmaken")
        conn = lees_db(db)
        grens = ondergrens(config.thresholds)
        hoogste, boven = voorselectie(conn, matrix, versie, grens)
        np.save(map_ / "hoogste.npy", hoogste)
        kandidaten = [{"stuk_id": rijen[i]["claim_id"], "taal": rijen[i]["taal"],
                       "tekst": rijen[i]["varianten"][0]["tekst"], "hoogste": float(hoogste[i])} for i in boven]
        print(f"{len(rijen)} stukken; {len(kandidaten)} op of boven {grens:.2f}, die gaan door /resolve", flush=True)
        uitkomsten = door_resolver(kandidaten)
        tekst_van = dict(conn.execute("SELECT claim_id, canonical_text FROM claim").fetchall())
        with (map_ / "treffers.jsonl").open("w", encoding="utf-8") as uit:
            for u in uitkomsten:
                if u["categorie"] in ("matched", "related"):
                    u["claimtekst"] = tekst_van.get(u["claim_id"])
                    uit.write(json.dumps(u, ensure_ascii=False) + "\n")
        print(dict(Counter(u["categorie"] for u in uitkomsten)))
        print(f"te labelen: de `matched` in {map_ / 'treffers.jsonl'}, labels in {LABELS}")
    else:
        rijen = lees_regels(map_)
        n_per_taal = dict(Counter(r["taal"] for r in rijen))
        treffers = [json.loads(r) for r in (map_ / "treffers.jsonl").read_text(encoding="utf-8").splitlines() if r]
        uit = uitslag(treffers, _lees_labels(), n_per_taal)
        meta = json.loads((map_ / "meta.json").read_text(encoding="utf-8"))
        uit["bron"] = {"repo": meta["bron"], "revisie": meta["revisie"], "motor": versie}
        (map_ / "uitslag.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        t = uit["totaal"]
        print(f"{t['n']} stukken: {t['matched']} matched ({t['terecht']} terecht, {t['vals']} vals),"
              f" {t['related']} related; bovengrens valse matched {t['bovengrens']:.2e}")
        for taal, d in sorted(uit["per_taal"].items(), key=lambda kv: -kv[1]["n"]):
            print(f"  {taal}: n {d['n']}, vals {d['vals']}, terecht {d['terecht']}, related {d['related']},"
                  f" bovengrens {d['bovengrens']:.2e}")


if __name__ == "__main__":
    main()
