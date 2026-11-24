"""Hermeting van de screeningpoort op de 21.3-proefset (PLAN.md #25.14d, BENCHMARK §60).

De batchcontrole (B17) zoekt per zin een weerlegde claim en laat het
relatiemodel beslissen of het document die claim beweert. De screeningpoort
bepaalt welke zinnen het relatiemodel te zien krijgen. Die poort staat op de
schaal van het tekstmodel, dus na een modelwissel moet ze opnieuw gemeten
worden.

De proefset is die van §59 en §60: 60 modeluitvoeren uit de repository
(`docs/steekproeven/21.3-echte-data.json`) en 47 gescrapete pagina's, opnieuw
opgehaald en tegen de vastgelegde hash gecontroleerd. De paginateksten blijven
lokaal (auteursrecht); alleen tellingen gaan naar de repository.

Grondwaarheid per document: een "beweert"-uitvoer hoort een vlag te krijgen
voor zijn eigen claim (of een ander lid van diens cluster); elke vlag op een
schone tekst, een factcheckpagina of een Wikipedia-pagina is vals.

De vorige hermeting draaide met een script in de kladmap dat daarna
verdween. Deze module is dat script, teruggehaald en vastgelegd.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
PROEFSET = WORTEL / "docs" / "steekproeven" / "21.3-echte-data.json"
HERMETING_215 = WORTEL / "docs" / "steekproeven" / "21.5-hermeting.json"


class _Alinea(HTMLParser):
    """Dezelfde extractie als bij §60: alleen alinea's, zonder navigatie,
    scripts en formulieren, en alleen regels langer dan 40 tekens."""

    SLA_OVER = {"script", "style", "nav", "footer", "header", "aside", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blok = 0
        self.in_p = False
        self.stukken: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SLA_OVER:
            self.blok += 1
        elif tag == "p" and not self.blok:
            self.in_p = True
            self.stukken.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SLA_OVER and self.blok:
            self.blok -= 1
        elif tag == "p":
            self.in_p = False

    def handle_data(self, data):
        if self.in_p and not self.blok:
            self.stukken.append(data)


def alineatekst(html: str) -> str:
    parser = _Alinea()
    parser.feed(html)
    regels = "".join(parser.stukken).split("\n")
    return "\n".join(r.strip() for r in regels if len(r.strip()) > 40)


@dataclass
class Uitkomst:
    terecht: set[str] = field(default_factory=set)
    gemist: set[str] = field(default_factory=set)
    vlag_op_andere_claim: int = 0
    vals: int = 0
    vlaggen: int = 0
    # Valse vlaggen als paren (document, claim) (#21.7): overlappende vensters
    # vlaggen dezelfde claim anders twee keer.
    vals_paren: set[tuple[str, str]] = field(default_factory=set)


def beoordeel(uitslagen, verwacht: dict[str, str], cluster_van: dict[str, str]) -> Uitkomst:
    """Telt per document tegen de grondwaarheid.

    `verwacht` bevat alleen de bruikbare "beweert"-documenten met hun claim;
    elk ander document hoort geen vlag te krijgen.
    """
    def zelfde(a: str, b: str) -> bool:
        return a == b or (a in cluster_van and cluster_van.get(a) == cluster_van.get(b))

    u = Uitkomst()
    for uitslag in uitslagen:
        vlaggen = [t.claim_id for t in uitslag.beweert]
        u.vlaggen += len(vlaggen)
        doel = verwacht.get(uitslag.document_id)
        if doel is None:
            u.vals += len(vlaggen)
            u.vals_paren |= {(uitslag.document_id, c) for c in vlaggen}
            continue
        if any(zelfde(doel, c) for c in vlaggen):
            u.terecht.add(uitslag.document_id)
        else:
            u.gemist.add(uitslag.document_id)
        u.vlag_op_andere_claim += sum(not zelfde(doel, c) for c in vlaggen)
    # Een "beweert"-document zonder uitslag is ook gemist.
    u.gemist |= set(verwacht) - u.terecht - {x.document_id for x in uitslagen}
    return u


def kies_poort(rijen: dict[float, tuple[int, int]], *, budget: int) -> float | None:
    """De poort met de meeste terechte vlaggen bij hoogstens `budget` valse;
    bij gelijkspel de strengere (twijfel versoepelt nooit)."""
    toegestaan = [(terecht, poort) for poort, (terecht, vals) in rijen.items() if vals <= budget]
    if not toegestaan:
        return None
    return max(toegestaan)[1]


def herbouw_documenten(cachemap: Path, *, client=None) -> tuple[list[tuple[str, str]], dict, dict]:
    """De 60 modeluitvoeren exact uit de repository, de 47 pagina's opnieuw
    opgehaald (of uit de lokale cache) en tegen hun hash gecontroleerd."""
    import time

    proef = json.loads(PROEFSET.read_text(encoding="utf-8"))
    docs, meta = [], {}
    verificatie = {"identiek": 0, "gewijzigd": 0, "weg": []}
    for r in proef["modeluitvoer"]:
        docs.append((r["id"], r["tekst"]))
        meta[r["id"]] = r
    cachemap.mkdir(parents=True, exist_ok=True)
    for r in proef["scrapes"]:
        pad = cachemap / f"{r['id']}.txt"
        if pad.exists():
            tekst = pad.read_text(encoding="utf-8")
        else:
            if client is None:
                import httpx

                client = httpx.Client(follow_redirects=True, timeout=20, headers={
                    "User-Agent": "Factiz-benchmark/25.14d (hermeting van 21.3)"})
            try:
                antwoord = client.get(r["url"])
                if antwoord.status_code != 200:
                    raise RuntimeError(f"status {antwoord.status_code}")
                tekst = alineatekst(antwoord.text)
                if r["id"].startswith("scrape-wiki"):
                    tekst = tekst[:20000]
                if len(tekst) < 800:
                    raise RuntimeError(f"te kort ({len(tekst)})")
            except Exception as exc:  # noqa: BLE001 - een onbereikbare pagina wordt geteld, niet verzwegen
                verificatie["weg"].append([r["id"], str(exc)[:60]])
                continue
            pad.write_text(tekst, encoding="utf-8")
            time.sleep(0.7)
        hasj = hashlib.sha256(tekst.encode()).hexdigest()[:16]
        verificatie["identiek" if hasj == r["sha256"] else "gewijzigd"] += 1
        # De bron-URL als document-id, zodat de bonnetjesregel werkt zoals in
        # productie: een pagina die zelf de check is, weerlegt de claim (§60).
        docs.append((r["url"], tekst))
        meta[r["url"]] = r
    return docs, meta, verificatie


def main() -> None:
    import argparse
    import dataclasses
    import os

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.controle import controleer_teksten
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Hermeting van de screeningpoort (#25.14d)")
    parser.add_argument("--poorten", default="0.72,0.75,0.78,0.80,0.82,0.84")
    parser.add_argument("--cache", default="data/proef213-paginas",
                        help="lokale map voor de opgehaalde paginateksten (niet in git)")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--eenheid", default="zin", choices=("zin", "venster2", "venster3"),
                        help="#21.7: de eenheid waarop gezocht wordt")
    parser.add_argument("--top", type=int, default=1, help="#21.7: kandidaten per eenheid op betekenis")
    parser.add_argument("--bm25", type=int, default=0,
                        help="#21.7: zoveel extra kandidaten per eenheid op woorden (0 = uit)")
    parser.add_argument("--herordenaar-poorten",
                        help="#21.7 stap 3: poorten op de score van de herordenaar (bijvoorbeeld 0.05,0.1,0.5);"
                             " dan is die score de poort in plaats van de gelijkenis")
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)

    config = load_config()
    docs, meta, verificatie = herbouw_documenten(Path(args.cache))
    print(f"proefset: {len(docs)} documenten · pagina's {verificatie}", flush=True)
    vorige = json.loads(HERMETING_215.read_text(encoding="utf-8"))["bevestiging_productiepad"]
    bruikbaar = set(vorige["tp"]) | set(vorige["gemist"])
    verwacht = {d: meta[d]["claim_id"] for d in bruikbaar}
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    cluster_van = {c: k for c, k in conn.execute(
        "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL")}

    extra = None
    if args.bm25:
        from doublecheck.embedding import _load_model, normaliseer_voor_embedding
        from doublecheck.retrievalmeting import Bm25
        from doublecheck.toelating import buiten_index

        tokenizer = _load_model(config.model_versions.text_embedding).tokenizer
        buiten = buiten_index(conn)
        claims = [(c, t) for c, t in conn.execute("SELECT claim_id, canonical_text FROM claim") if c not in buiten]

        def woorden(tekst):
            return tokenizer(normaliseer_voor_embedding(tekst), add_special_tokens=False)["input_ids"]

        index = Bm25([woorden(t) for _, t in claims])

        def extra(tekst):
            return [claims[i][0] for i, _ in index.top(woorden(tekst), args.bm25)]

    # Hetzelfde model geeft voor dezelfde invoer hetzelfde oordeel: onthouden
    # over de poorten heen verandert geen uitkomst, alleen de rekentijd.
    from doublecheck.controle import _stance_uit_config

    stance_model = _stance_uit_config(config)
    stance_geheugen: dict = {}

    def stance(premisse, hypothese):
        sleutel = (premisse, hypothese)
        if sleutel not in stance_geheugen:
            stance_geheugen[sleutel] = stance_model(premisse, hypothese)
        return stance_geheugen[sleutel]

    herorden, herordenaar_geheugen = None, {}
    if args.herordenaar_poorten:
        from doublecheck import herordenaar

        print(f"herordenaar {herordenaar.HERORDENAAR}", flush=True)

        def herorden(paren):
            nieuw = [p for p in dict.fromkeys(paren) if p not in herordenaar_geheugen]
            if nieuw:
                herordenaar_geheugen.update(zip(nieuw, herordenaar.scores(nieuw)))
            return [herordenaar_geheugen[p] for p in paren]

    print(f"eenheid {args.eenheid} · top {args.top} op betekenis · {args.bm25} op woorden"
          + (" · de herordenaar is de poort" if herorden else ""), flush=True)
    rijen = {}
    print(f"{'poort':>6}{'terecht':>9}{'vals':>6}{'paren':>7}{'vlaggen':>9}{'andere claim':>14}")
    poorten = args.herordenaar_poorten if herorden else args.poorten
    for poort in [float(p) for p in poorten.split(",")]:
        if herorden:
            rapport = controleer_teksten(conn, docs, config=config, stance=stance, eenheid=args.eenheid,
                                         top=args.top, extra_kandidaten=extra,
                                         herordenaar=herorden, herordenaar_poort=poort)
        else:
            drempels = dataclasses.replace(config.thresholds, screening_poort=poort)
            rapport = controleer_teksten(conn, docs, config=dataclasses.replace(config, thresholds=drempels),
                                         stance=stance, eenheid=args.eenheid, top=args.top,
                                         extra_kandidaten=extra)
        u = beoordeel(rapport.documenten, verwacht, cluster_van)
        rijen[poort] = (len(u.terecht), len(u.vals_paren))
        print(f"{poort:>6.2f}{len(u.terecht):>5}/{len(bruikbaar):<3}{u.vals:>6}{len(u.vals_paren):>7}{u.vlaggen:>9}"
              f"{u.vlag_op_andere_claim:>14}", flush=True)
    budget = len(vorige["vals"])
    keuze = kies_poort(rijen, budget=budget)
    print(f"\nkeuze (meeste terechte vlaggen bij hoogstens {budget} valse paren, zoals MiniLM in §60): {keuze}")
    if herorden:
        _diagnose_herordenaar(conn, config, docs, verwacht, cluster_van, args.top, herorden,
                              [float(p) for p in poorten.split(",")])


def _diagnose_herordenaar(conn, config, docs, verwacht, cluster_van, top, herorden, poorten) -> None:
    """Zoals stap 1 van #21.7: voor de documenten die hun claim beweren, de
    beste score van de doelclaim onder de top per zin, en of hij na het
    herordenen bovenaan staat."""
    import statistics

    from doublecheck.controle import _MIN_ZINLENGTE, _zinnen
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.search import search_text

    def zelfde(a, b):
        return a == b or (a in cluster_van and cluster_van.get(a) == cluster_van.get(b))

    tekst_van = dict(docs)
    beste_score, bovenaan = {}, {}
    for doc_id, doel in verwacht.items():
        zinnen = [z for z in _zinnen(tekst_van[doc_id]) if len(z) >= _MIN_ZINLENGTE]
        for zin, fp in zip(zinnen, fingerprint_texts(zinnen, config.model_versions.text_embedding)):
            kandidaten = [k.claim_id for k in search_text(conn, fp, top, varianten=config.varianten.in_resolver)]
            teksten = [conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (c,)).fetchone()[0]
                       for c in kandidaten]
            scores = herorden([(zin, tekst) for tekst in teksten])
            for plaats, (c, s) in enumerate(sorted(zip(kandidaten, scores), key=lambda x: -x[1])):
                if zelfde(doel, c):
                    beste_score[doc_id] = max(beste_score.get(doc_id, 0.0), s)
                    if plaats == 0:
                        bovenaan[doc_id] = max(bovenaan.get(doc_id, 0.0), s)
    print(f"\ndoelclaim in de top {top} van een zin: {len(beste_score)} van {len(verwacht)}; beste score mediaan "
          f"{statistics.median(beste_score.values()) if beste_score else 0:.3f}")
    print("na herordenen bovenaan, met score vanaf de poort: "
          + " · ".join(f"{p}: {sum(1 for s in bovenaan.values() if s >= p)}" for p in poorten))


if __name__ == "__main__":
    main()
