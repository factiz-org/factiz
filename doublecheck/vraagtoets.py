"""De testset voor Ask Factiz (PLAN #24.10 b).

53 vragen in gewone woorden, geschreven vóór de resolver ze zag
(`docs/steekproeven/24.10-vragen.json`): vijftig over de evergreens van §111
en de drie voorbeelden van de PO. Per vraag zoekt de toets zoals Ask Factiz
zou zoeken: de vijf beweringen die het dichtst bij liggen, elk met de
categorie uit de categoriseringsfunctie (DR4). Goed is: een claim uit de
evergreen-groep van de vraag (of, bij de voorbeelden van de PO, een claim met
een van de trefwoorden). Per vraag ook het label dat de lezer bij de eerste
regel zou zien, jongste oordeel voorop, om na te lopen.

    python -m doublecheck.vraagtoets
"""

from __future__ import annotations

import json
from pathlib import Path

VRAGEN = Path(__file__).resolve().parent.parent / "docs" / "steekproeven" / "24.10-vragen.json"
DIEPTE = 5


def tel_getoond(goed: list[bool]) -> dict:
    """Wat de pagina toont (#24.10 c): per kaart, in volgorde, of die goed
    is. Elk cluster staat er één keer (`ask.getoond`)."""
    return {"getoond": any(goed), "eerste_getoond": bool(goed and goed[0]), "niets": not goed,
            "kaarten": len(goed)}


def is_goed(claim_id: str, tekst: str, vraag: dict) -> bool:
    """Hoort deze claim bij het antwoord dat de vraag verwacht?"""
    if vraag.get("leden"):
        return claim_id in set(vraag["leden"])
    return any(woord in tekst.lower() for woord in vraag.get("trefwoorden", ()))


def beoordeel(kandidaten: list[tuple[str, str, str]], vraag: dict) -> dict:
    """`kandidaten`: (claim_id, tekst, categorie) in volgorde van de zoektocht.
    Goed op de eerste regel, ergens in de top vijf, en ergens tussen de regels
    die Ask Factiz zou tonen (`matched` of `related`)."""
    goed = [is_goed(c, t, vraag) for c, t, _ in kandidaten]
    getoond = [g for g, (_, _, categorie) in zip(goed, kandidaten) if categorie in ("matched", "related")]
    return {"eerste": bool(goed and goed[0]), "top5": any(goed), "getoond": any(getoond),
            "getoonde_regels": len(getoond)}


STILTE = VRAGEN.with_name("24.10-stilte.json")
STILTE_WEB = VRAGEN.with_name("24.10-stilte-web.json")
POORTEN = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


def kies_poort(rijen: dict[float, tuple[int, int]]) -> float | None:
    """De poort met de meeste juist getoonde regels bij nul valse regels op de
    stilteset; bij gelijkspel de strengere (twijfel versoepelt nooit)."""
    toegestaan = [(juist, poort) for poort, (juist, vals) in rijen.items() if vals == 0]
    return max(toegestaan)[1] if toegestaan else None


def _poortmeting(conn, config, vragen, stil, herorden) -> None:  # pragma: no cover - met de modellen
    """De poort voor Ask Factiz (#24.10): de herordenaar op de top vijf, op
    de positieve set en de stilteset."""
    from doublecheck.embedding import fingerprint_text
    from doublecheck.search import search_text

    def top(tekst):
        fp = fingerprint_text(tekst, config.model_versions.text_embedding)
        uit = []
        for k in search_text(conn, fp, DIEPTE, varianten=config.varianten.in_resolver):
            claimtekst = conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (k.claim_id,)).fetchone()[0]
            uit.append((k.claim_id, claimtekst, float(k.similarity)))
        scores = herorden([(tekst, c) for _, c, _ in uit])
        return [(c, ct, s, h) for (c, ct, s), h in zip(uit, scores)]

    positief = [(v, top(v["vraag"])) for v in vragen]
    stilte = [(v, top(v["vraag"])) for v in stil]
    rijen = {}
    print(f"\n{'poort':>12}{'juist getoond':>15}{'andere regels':>15}{'valse regels (stilte)':>23}")
    related = config.thresholds.text_related
    basis_juist = sum(any(is_goed(c, ct, v) and s >= related for c, ct, s, _ in r) for v, r in positief)
    basis_vals = sum(sum(s >= related for _, _, s, _ in r) for _, r in stilte)
    print(f"{'gelijkenis ' + str(related):>12}{basis_juist:>15}{'':>15}{basis_vals:>23}")
    for poort in POORTEN:
        juist = sum(any(is_goed(c, ct, v) and h >= poort for c, ct, _, h in r) for v, r in positief)
        andere = sum(sum((not is_goed(c, ct, v)) and h >= poort for c, ct, _, h in r) for v, r in positief)
        vals = sum(sum(h >= poort for _, _, _, h in r) for _, r in stilte)
        rijen[poort] = (juist, vals)
        print(f"{poort:>12}{juist:>15}{andere:>15}{vals:>23}", flush=True)
    print(f"\nkeuze (meeste juist getoond bij nul valse regels op de stilteset): {kies_poort(rijen)}")
    print("\nregels op de stilteset vanaf de laagste poort, om na te lezen:")
    for v, r in stilte:
        for c, ct, s, h in r:
            if h >= POORTEN[0]:
                print(f"  {h:.3f} {v['vraag'][:50]!r} -> {ct[:90]!r}")


def trek(aantal: int, totaal: int, zaad: int) -> list[int]:
    """Een vaste, reproduceerbare steekproef van posities in de pool."""
    import random

    return sorted(random.Random(zaad).sample(range(totaal), min(aantal, totaal)))


def tel_regels(uitkomsten: list[dict], poorten=(0.5, 0.7, 0.9)) -> dict[float, int]:
    """Per poort het aantal getoonde regels: (tekst, claim)-paren met een
    score van de herordenaar vanaf die poort."""
    return {p: sum(1 for u in uitkomsten for r in u["regels"] if r["score"] >= p) for p in poorten}


def tel_vals(uitkomsten: list[dict], labels: dict[tuple[str, str], str],
             poorten=(0.7, 0.8, 0.9)) -> dict[float, dict[str, int]]:
    """Per poort de nagelezen regels: vals, terecht en randgeval (een randgeval
    telt niet als vals), en het aantal stukken met minstens één valse regel.
    Weigert zolang een regel vanaf de laagste poort geen label heeft."""
    laagste = min(poorten)
    zonder = [(u["id"], r["claim"]) for u in uitkomsten for r in u["regels"]
              if r["score"] >= laagste and (u["id"], r["claim"]) not in labels]
    if zonder:
        raise ValueError(f"{len(zonder)} regels vanaf {laagste} zonder label, bijvoorbeeld {zonder[0]}")
    uit = {}
    for poort in poorten:
        telling = {"vals": 0, "terecht": 0, "randgeval": 0}
        stukken = set()
        for u in uitkomsten:
            for r in u["regels"]:
                if r["score"] >= poort:
                    label = labels[(u["id"], r["claim"])]
                    telling[label] += 1
                    if label == "vals":
                        stukken.add(u["id"])
        uit[poort] = {**telling, "stukken_met_vals": len(stukken)}
    return uit


def stiltepoort(vals_per_poort: dict[float, int]) -> float | None:
    """De regel van vooraf (PLAN #24.10): nul valse regels op 0,7 houdt 0,7;
    anders de laagste poort uit {0,8, 0,9} zonder valse regels; anders geen."""
    if vals_per_poort.get(0.7) == 0:
        return 0.7
    for poort in (0.8, 0.9):
        if vals_per_poort.get(poort) == 0:
            return poort
    return None


def _stilte_web(conn, config, pool: Path, aantal: int, zaad: int, uit: Path, herorden) -> None:  # pragma: no cover
    """De stiltemeting op schaal (#24.10): gewone webtekst door de poort van
    Ask Factiz. Hervatbaar: elk stuk krijgt één regel in `uit`."""
    import numpy as np

    from doublecheck.embedding import TextFingerprint
    from doublecheck.search import search_text
    from doublecheck.variantenbatch import lees_vectoren

    versie = config.model_versions.text_embedding
    plat, matrix = lees_vectoren(pool, versie)
    gekozen = trek(aantal, len(plat), zaad)
    klaar = set()
    if uit.exists():
        inhoud = uit.read_text(encoding="utf-8")
        klaar = {json.loads(r)["id"] for r in inhoud[:inhoud.rfind("\n") + 1].splitlines() if r.strip()}
    print(f"pool {pool}: {len(plat)} stukken, steekproef {len(gekozen)} (zaad {zaad}), al gedaan {len(klaar)}",
          flush=True)
    with uit.open("a", encoding="utf-8") as schrijf:
        for n, i in enumerate(gekozen, 1):
            stuk_id, taal, tekst = plat[i]
            if stuk_id in klaar:
                continue
            fp = TextFingerprint(np.asarray(matrix[i], dtype=np.float32), versie)
            kandidaten = search_text(conn, fp, DIEPTE, varianten=config.varianten.in_resolver)
            teksten = [conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?",
                                    (k.claim_id,)).fetchone()[0] for k in kandidaten]
            scores = herorden([(tekst, c) for c in teksten])
            schrijf.write(json.dumps({"id": stuk_id, "taal": taal, "regels": [
                {"claim": k.claim_id, "score": round(float(s), 4), "gelijkenis": round(float(k.similarity), 4)}
                for k, s in zip(kandidaten, scores)]}, ensure_ascii=False) + "\n")
            schrijf.flush()
            if n % 250 == 0:
                print(f"  {n}/{len(gekozen)}", flush=True)
    uitkomsten = [json.loads(r) for r in uit.read_text(encoding="utf-8").splitlines() if r.strip()]
    telling = tel_regels(uitkomsten)
    print(f"\n{len(uitkomsten)} stukken · getoonde regels per poort: "
          + " · ".join(f"{p}: {n}" for p, n in telling.items()))
    tekst_van = {plat[i][0]: plat[i][2] for i in gekozen}
    print("\nregels vanaf 0,5, om na te lezen:")
    for u in uitkomsten:
        for r in u["regels"]:
            if r["score"] >= 0.5:
                claim = conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (r["claim"],)).fetchone()[0]
                print(f"  {r['score']:.3f} [{u['id']}] {tekst_van[u['id']][:110]!r}\n        -> {claim[:110]!r}")


def main() -> None:  # pragma: no cover - draait op de productiedatabase met het tekstmodel
    import argparse
    import os

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_text
    from doublecheck.storage import connect
    from doublecheck.verdicts import labelklasse_in_tijd

    parser = argparse.ArgumentParser(description="De testset voor Ask Factiz (#24.10 b)")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--uit", default="data/vraagtoets.json")
    parser.add_argument("--poort", action="store_true",
                        help="de poort voor Ask Factiz meten met de herordenaar en de stilteset")
    parser.add_argument("--stilte-web", type=int, default=0,
                        help="zoveel stukken gewone webtekst door de poort van Ask Factiz (#24.10)")
    parser.add_argument("--pool", default="data/stiltetoets-vers")
    parser.add_argument("--zaad", type=int, default=2410)
    parser.add_argument("--vraagvorm-aan", action="store_true",
                        help="met de schakelaar [vraagvorm] aan (#25.36); de rest van de config blijft")
    parser.add_argument("--stilte-tel", action="store_true",
                        help="de nagelezen regels van --stilte-web tellen en de regel van vooraf toepassen")
    args = parser.parse_args()
    if args.stilte_tel:
        uit = Path(f"data/vraagtoets-stilte-{Path(args.pool).name}-{args.zaad}.jsonl")
        uitkomsten = [json.loads(r) for r in uit.read_text(encoding="utf-8").splitlines() if r.strip()]
        labels = {(r["stuk"], r["claim"]): r["label"]
                  for r in json.loads(STILTE_WEB.read_text(encoding="utf-8"))["regels"]}
        telling = tel_vals(uitkomsten, labels)
        print(f"{len(uitkomsten)} stukken uit {args.pool} (zaad {args.zaad})")
        print(f"{'poort':>6}{'vals':>7}{'terecht':>9}{'randgeval':>11}{'stukken met vals':>18}")
        for poort, n in telling.items():
            print(f"{poort:>6}{n['vals']:>7}{n['terecht']:>9}{n['randgeval']:>11}{n['stukken_met_vals']:>18}")
        keuze = stiltepoort({p: n["vals"] for p, n in telling.items()})
        print(f"\nregel van vooraf: {keuze if keuze is not None else 'geen poort uit {0,7, 0,8, 0,9} zonder valse regels'}")
        return
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)

    config = load_config()
    if args.vraagvorm_aan:
        from dataclasses import replace

        from doublecheck.config import VraagvormSettings

        config = replace(config, vraagvorm=VraagvormSettings(aan=True))
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    vragen = json.loads(VRAGEN.read_text(encoding="utf-8"))["vragen"]
    if args.stilte_web:
        from doublecheck import herordenaar

        uit = Path(f"data/vraagtoets-stilte-{Path(args.pool).name}-{args.zaad}.jsonl")
        _stilte_web(conn, config, Path(args.pool), args.stilte_web, args.zaad, uit,
                    lambda paren: herordenaar.scores(paren) if paren else [])
        return
    if args.poort:
        from doublecheck import herordenaar

        stil = json.loads(STILTE.read_text(encoding="utf-8"))["vragen"]
        _poortmeting(conn, config, vragen, stil, lambda paren: herordenaar.scores(paren) if paren else [])
        return
    # Door hetzelfde pad als `POST /ask` (kritiek AC van E5.S3): het cijfer
    # op de pagina is het cijfer van dit pad.
    from doublecheck import ask

    def door_ask(tekst):
        fp = fingerprint_text(tekst, config.model_versions.text_embedding)
        rijen = ask.kandidaten(conn, config, tekst, fp)
        return rijen, ask.getoond(conn, rijen)

    rijen_uit = []
    telling = {"eerste": 0, "top5": 0, "getoond": 0, "eerste_getoond": 0, "niets": 0}
    for vraag in vragen:
        rijen, getoonde = door_ask(vraag["vraag"])
        uitslag = beoordeel([(k.claim_id, k.tekst, str(k.categorie)) for k in rijen], vraag)
        uitslag.update(tel_getoond([is_goed(k.claim_id, k.tekst, vraag) for k, _ in getoonde]))
        for sleutel in telling:
            telling[sleutel] += uitslag[sleutel]
        label = None
        if getoonde:
            klasse, eerder = labelklasse_in_tijd(
                (x.verdict_normalized, x.review_date) for x in getoonde[0][1].factchecks)
            label = {"klasse": klasse, "eerder": eerder}
        rijen_uit.append({"nr": vraag["nr"], "vraag": vraag["vraag"], **uitslag, "label_eerste": label,
                          "regels": [{"claim": k.claim_id, "tekst": k.tekst[:160], "categorie": str(k.categorie),
                                      "gelijkenis": round(k.gelijkenis, 3), "goed": is_goed(k.claim_id, k.tekst, vraag),
                                      "getoond": any(k.claim_id == g.claim_id for g, _ in getoonde)}
                                     for k in rijen]})
        teken = "+" if uitslag["eerste_getoond"] else ("~" if uitslag["getoond"] else ("0" if uitslag["niets"] else "-"))
        print(f"{vraag['nr']:>3} {teken} {vraag['vraag'][:70]}", flush=True)
    stil = json.loads(STILTE.read_text(encoding="utf-8"))["vragen"]
    stilte_uit = []
    for vraag in stil:
        _, getoonde = door_ask(vraag["vraag"])
        stilte_uit.append({"vraag": vraag["vraag"], "kaarten": [{"claim": k.claim_id, "tekst": k.tekst[:160],
                                                                 "categorie": str(k.categorie)} for k, _ in getoonde]})
        for k, _ in getoonde:
            print(f"  stilte: {vraag['vraag'][:50]!r} -> {k.tekst[:90]!r} ({k.categorie})", flush=True)
    n = len(vragen)
    print(f"\njuiste eerste regel {telling['eerste']} van {n} · juist in de top vijf {telling['top5']}")
    print(f"wat de pagina toont: juist getoond {telling['getoond']}, als eerste kaart {telling['eerste_getoond']},"
          f" niets {telling['niets']}, alleen andere beweringen {n - telling['getoond'] - telling['niets']}")
    print(f"stillevragen: {sum(len(s['kaarten']) for s in stilte_uit)} kaarten op {len(stil)} vragen")
    Path(args.uit).write_text(json.dumps({"telling": telling, "n": n, "vragen": rijen_uit, "stilte": stilte_uit},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"per vraag: {args.uit}")


if __name__ == "__main__":
    main()
