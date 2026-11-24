"""De terugkijktoets (PLAN #28.6 c): had het geheugen het toen al, en vond het dat?

Het eerste punt onder het kopgetal. Per vraag het geheugen zoals het was op
de dag van de latere check: alleen claims met een toegelaten check (B28) met
een geldige datum strikt vóór die dag. Gezocht wordt zoals de resolver
zoekt, met varianten, de cross-linguale drempel en DR8.

Wat goed is, legden mensen vast, nooit ons eigen model (de regel van #28.4):

- **dezelfde post** (#25.13): een eerdere check wees naar dezelfde virale
  post; de vraag is de claimtekst van de latere check;
- **Community Notes** (#25.15): een behulpzame note linkt naar een check in
  het corpus; de vraag is de notetekst zonder URL's. Lokaal, en alleen
  tellingen gaan naar buiten (X Developer Agreement);
- **sinds juli**: de checks van 2026-07-01 en later tegen de index van 1 juli,
  met elke `matched` door een mens gelezen.

Licht lek, en dat staat bij het cijfer: model en drempels zijn gekozen met
het hele corpus, ook met checks van na de dag van de vraag.

    python -m doublecheck.terugkijk meten
    python -m doublecheck.terugkijk tellen
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
LABELS = WORTEL / "docs" / "steekproeven" / "28.6c-ander-record.json"
LABELS_JULI = WORTEL / "docs" / "steekproeven" / "28.6c-sinds-juli.json"
UIT = WORTEL / "data" / "terugkijk"
PEILDATUM = "2026-07-01"
STEEKPROEF = {"post": 100, "notes": 100, "juli": 150}
ZAAD = 2860
DIEPTE = 1000


def eerste_datums(rijen) -> dict[str, str]:
    """(claim_id, reviewdatum, toegelaten) naar de dag waarop een claim het
    geheugen in kwam: de vroegste geldige datum van een toegelaten check."""
    from doublecheck.datums import geldige_review_datum

    uit: dict[str, str] = {}
    for claim_id, datum, toegelaten in rijen:
        geldig = geldige_review_datum(datum or "") if toegelaten else ""
        if geldig and (claim_id not in uit or geldig < uit[claim_id]):
            uit[claim_id] = geldig
    return uit


def in_de_tijd(kandidaten, eerste: dict[str, str], dag: str, *, met_ongedateerd: bool = False):
    """De beste kandidaat die op `dag` al in het geheugen stond: strikt eerder.
    Zonder geldige datum is een claim niet in de tijd te plaatsen; die doet
    alleen mee als de gevoeligheidsrun erom vraagt."""
    for kandidaat in kandidaten:
        begin = eerste.get(kandidaat.claim_id)
        if (begin is None and met_ongedateerd) or (begin is not None and begin < dag):
            return kandidaat
    return None


def paren(per_post: dict[str, dict[str, tuple[str, str, str]]]) -> list[dict]:
    """Per post {check-url: (claim_id, datum, redactie)}. Elke check met een
    strikt eerdere check van dezelfde post wordt één vraag, ook als hij onder
    meer posts staat; de doelen zijn de claims van de eerdere checks."""
    vragen: dict[str, dict] = {}
    for checks in per_post.values():
        for url, (claim, dag, redactie) in checks.items():
            eerder = [(c, d, r) for u, (c, d, r) in checks.items() if d < dag]
            if not eerder:
                continue
            vraag = vragen.setdefault(url, {"url": url, "claim": claim, "dag": dag, "redactie": redactie,
                                            "doelen": set(), "redacties": set(), "laatste": ""})
            vraag["doelen"].update(c for c, _, _ in eerder)
            vraag["redacties"].update(r for _, _, r in eerder)
            vraag["laatste"] = max([vraag["laatste"], *(d for _, d, _ in eerder)])
    uit = []
    for vraag in vragen.values():
        uit.append({
            "url": vraag["url"], "claim": vraag["claim"], "dag": vraag["dag"], "doelen": vraag["doelen"],
            "zelfde_tekst": vraag["claim"] in vraag["doelen"],
            "andere_redactie": bool(vraag["redacties"] - {vraag["redactie"]}),
            "dagen": (date.fromisoformat(vraag["dag"]) - date.fromisoformat(vraag["laatste"])).days,
        })
    return sorted(uit, key=lambda v: v["url"])


def uitkomst(categorie: str, tegenspraak: bool, claim_id: str | None, doelen: set[str]) -> str:
    """Gevonden alleen op een claim die mensen koppelden; een `matched` op iets
    anders is een ander record, dat gelezen moet worden."""
    if categorie == "matched":
        return "gevonden" if claim_id in doelen else "ander record"
    if tegenspraak:
        return "tegenspraak"
    return "verwant" if categorie == "related" else "niets"


def gatklasse(dagen: int) -> str:
    return "0-29" if dagen < 30 else ("30-364" if dagen < 365 else "365+")


def steekproef(rijen: list[dict], aantal: int, zaad: int = ZAAD) -> list[dict]:
    """Een vaste, willekeurige steekproef om te lezen; alles als het minder is."""
    if len(rijen) <= aantal:
        return list(rijen)
    return random.Random(zaad).sample(rijen, aantal)


def tel(uitkomsten: list[dict], labels: dict[tuple[str, str, str], str]) -> dict[str, dict]:
    """Per bron de uitkomsten, en wat het lezen van de ander-records zei.
    Weigert zolang een ander record uit de steekproef geen label heeft."""
    import collections

    per_bron: dict[str, list[dict]] = collections.defaultdict(list)
    for rij in uitkomsten:
        per_bron[rij["bron"]].append(rij)
    uit = {}
    for bron, rijen in per_bron.items():
        anders = [r for r in rijen if r["uitkomst"] == "ander record"]
        gekozen = steekproef(anders, STEEKPROEF.get(bron, 100))
        zonder = [r["vraag"] for r in gekozen if (bron, r["vraag"], r["kandidaat"]) not in labels]
        if zonder:
            raise ValueError(f"{len(zonder)} ander-records van {bron} zonder label, bijvoorbeeld {zonder[0]}")
        telling = collections.Counter(r["uitkomst"] for r in rijen)
        uit[bron] = {**telling, "n": len(rijen),
                     "ander record gelezen": dict(collections.Counter(
                         labels[(bron, r["vraag"], r["kandidaat"])] for r in gekozen))}
    return uit


def _labels() -> dict[tuple[str, str, str], str]:
    uit = {}
    for pad in (LABELS, LABELS_JULI):
        if pad.exists():
            uit.update({(r["bron"], r["vraag"], r["claim"]): r["label"]
                        for r in json.loads(pad.read_text(encoding="utf-8"))["labels"]})
    return uit


def _bovengrens(k: int, n: int) -> float:
    """Eenzijdige 95%-bovengrens (Clopper-Pearson), zoals in BENCHMARK."""
    from scipy.stats import beta

    return float(beta.ppf(0.95, k + 1, n - k)) if n and k < n else 1.0


def _twee(uitkomsten: dict) -> dict:
    """De hoofduitkomst plat in de rij, de gevoeligheidsrun ernaast."""
    return {**uitkomsten[""], "met_ongedateerd": uitkomsten["met_ongedateerd"]}


def _meten(conn, config, feed: Path, notesmap: Path) -> None:  # pragma: no cover - op de productiedatabase
    import collections
    import re
    from datetime import datetime, timezone
    from urllib.parse import urlsplit

    import numpy as np

    from doublecheck.categorize import categorize
    from doublecheck.communitynotes import _URL, _rijen, meet
    from doublecheck.datums import geldige_review_datum
    from doublecheck.embedding import TextFingerprint, fingerprint_texts
    from doublecheck.evidence import _host
    from doublecheck.natuurlijk import post_sleutel
    from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations, extract_numbers
    from doublecheck import artikel, artikellezer, feitenlaag, rechter, vraagvorm, zinnen
    from doublecheck.taal import detecteer_taal, zijn_verschillende_talen
    from doublecheck.toelating import buiten_index, register, staat_aan

    versie, t = config.model_versions.text_embedding, config.thresholds
    buiten, aan, hosts = buiten_index(conn), staat_aan(conn), register()
    checks = {}
    for url, claim, datum in conn.execute("SELECT url, claim_id, review_date FROM factcheck"):
        toegelaten = claim not in buiten and (not aan or (_host(url) or "") in hosts)
        checks[url] = (claim, geldige_review_datum(datum or ""), toegelaten)
    eerste = eerste_datums(checks.values())
    tekst, taal = {}, {}
    for claim, t_, l_ in conn.execute("SELECT claim_id, canonical_text, language FROM claim"):
        tekst[claim], taal[claim] = t_, l_
    vector = {c: np.frombuffer(p, dtype=np.float32) for c, p in conn.execute(
        "SELECT claim_id, payload FROM fingerprint WHERE kind = 'text' AND model_version = ?", (versie,))}
    print(f"{len(eerste):,} claims met een datum in het geheugen", flush=True)

    def zoek(fp, vraagtekst, dag, doelen):
        # Een artikel per zin (#30.11), zoals de resolver: met de schakelaar
        # uit, of bij één zin, precies de oude zoekvraag via de vraagvorm (#25.36).
        eenheden = zinnen.eenheden(vraagtekst) if config.artikel.per_zin else [vraagtekst]
        if len(eenheden) == 1:
            vingers, lijsten = [fp], [vraagvorm.zoek(conn, config, vraagtekst, fp, DIEPTE)]
        else:
            vingers = fingerprint_texts(eenheden, versie)
            lijsten = vraagvorm.zoek_alle(conn, config, eenheden, vingers, DIEPTE)
        # De artikellezer (#30.11b) leest de eenheden ook als de gewone weg ze
        # als één tekst zocht, zoals de resolver.
        lees_eenheden, lees_vingers, lees_lijsten = eenheden, vingers, lijsten
        if config.artikellezer.aan and len(eenheden) == 1 and len(alle := zinnen.eenheden(vraagtekst)) > 1:
            lees_eenheden, lees_vingers = alle, fingerprint_texts(alle, versie)
            lees_lijsten = vraagvorm.zoek_alle(conn, config, lees_eenheden, lees_vingers, DIEPTE)
        uit = {}
        for sleutel, met in (("", False), ("met_ongedateerd", True)):
            # De rechter (#30.3) leest alleen wat op die dag al in het geheugen
            # stond; met de schakelaar uit is dit precies in_de_tijd.
            geldig = [[c for c in lijst if in_de_tijd([c], eerste, dag, met_ongedateerd=met) is not None]
                      for lijst in lijsten]
            gezien = []
            if config.rechter.aan:
                rechter.waarnemer = gezien.append
            try:
                for i in artikel.te_lezen(geldig, config):
                    geldig[i] = rechter.herorden(
                        conn, config, eenheden[i], geldig[i],
                        tegenspraak=lambda tx, v=vingers[i], e=eenheden[i]: contradicts(
                            v.numbers, v.negations, tx, artefact_text=e, artefact_negation_tokens=v.negation_tokens))
            finally:
                rechter.waarnemer = None
            # Wat de rechter las, zodat zijn drempels offline te kiezen zijn (alleen met hem aan).
            extra = {"gelezen": [list(g) for g in gezien[-1]] if gezien else []} if config.rechter.aan else {}
            uitslagen = []
            for eenheid, vinger, lijst in zip(eenheden, vingers, geldig):
                k = lijst[0] if lijst else None
                if k is None:
                    uitslagen.append((categorize(None, t), None, 0.0, False, False))
                    continue
                cross = zijn_verschillende_talen(vinger.language, taal[k.claim_id])
                tegen = contradicts(vinger.numbers, vinger.negations, tekst[k.claim_id], artefact_text=eenheid,
                                    artefact_negation_tokens=vinger.negation_tokens)
                u = categorize(k.similarity, t, contradiction=tegen, crosslinguaal=cross,
                               rechter=rechter.oordeel(k, config),
                               feit_rood=(config.feiten.aan and feitenlaag.rood(conn, k.claim_id)
                                          and feitenlaag.herken(eenheid, vinger, config) is not None))
                uitslagen.append((u, k, artikel.marge(k, config, cross), tegen, cross))
            u, k, _, tegen, cross = artikel.winnaar(uitslagen)
            if config.artikellezer.aan and u.category != "matched" and len(lees_eenheden) > 1:
                gelezen = artikellezer.lees(
                    config, vraagtekst,
                    [[c for c in lijst if in_de_tijd([c], eerste, dag, met_ongedateerd=met) is not None]
                     for lijst in lees_lijsten],
                    lambda c: tekst[c])
                if gelezen is not None:
                    kl, score, i = gelezen
                    v, e = lees_vingers[i], lees_eenheden[i]
                    cross_l = zijn_verschillende_talen(v.language, taal[kl.claim_id])
                    tegen_l = contradicts(v.numbers, v.negations, tekst[kl.claim_id], artefact_text=e,
                                          artefact_negation_tokens=v.negation_tokens)
                    ul = categorize(kl.similarity, t, contradiction=tegen_l, crosslinguaal=cross_l, lezer=score,
                                    feit_rood=(config.feiten.aan and feitenlaag.rood(conn, kl.claim_id)
                                               and feitenlaag.herken(e, v, config) is not None))
                    if ul.category == "matched":
                        u, k, tegen, cross = ul, kl, tegen_l, cross_l
            if k is None:
                uit[sleutel] = {"kandidaat": None, "gelijkenis": None, "categorie": "none", "uitkomst": "niets",
                                **extra}
                continue
            drempel = t.text_match_crosslingual if cross else t.text_match
            uit[sleutel] = {"kandidaat": k.claim_id, "gelijkenis": round(float(k.similarity), 4),
                            "categorie": str(u.category),
                            "uitkomst": uitkomst(str(u.category), tegen and k.similarity >= drempel,
                                                 k.claim_id, doelen), **extra}
        return uit

    def claim_fp(claim):
        tx = tekst[claim]
        return TextFingerprint(vector[claim], versie, numbers=extract_numbers(tx), negations=extract_negations(tx),
                               negation_tokens=extract_negation_tokens(tx), language=detecteer_taal(tx))

    # De posts uit de feed: per losse post de toegelaten, gedateerde checks.
    data = json.loads(feed.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("dataFeedElement", [])
    per_post: dict[str, dict] = collections.defaultdict(dict)
    for rec in items:
        item = (rec or {}).get("item") if isinstance(rec, dict) else None
        if isinstance(item, list):
            item = item[0] if item and isinstance(item[0], dict) else None
        if not isinstance(item, dict) or item.get("url") not in checks:
            continue
        claim, dag, toegelaten = checks[item["url"]]
        if not dag or not toegelaten:
            continue
        redactie = re.sub(r"^www\.", "", (urlsplit(item["url"]).hostname or "").lower())
        verschijningen = (item.get("itemReviewed") or {}).get("appearance") or []
        if isinstance(verschijningen, dict):
            verschijningen = [verschijningen]
        for v in verschijningen if isinstance(verschijningen, list) else []:
            u = v.get("url") if isinstance(v, dict) else (v if isinstance(v, str) else None)
            post = post_sleutel(u) if u else None
            if post:
                per_post[post][item["url"]] = (claim, dag, redactie)

    UIT.mkdir(parents=True, exist_ok=True)
    rijen, buiten_geheugen = [], collections.Counter()

    # Bron 1: dezelfde post.
    for paar in paren(per_post):
        dag, claim = paar["dag"], paar["claim"]
        doelen = {c for c in paar["doelen"] if eerste.get(c, "9999") < dag}
        zelfde = paar["zelfde_tekst"] or eerste.get(claim, "9999") < dag
        if zelfde:
            doelen.add(claim)
        if not doelen or claim not in vector:
            buiten_geheugen["post"] += 1
            continue
        rijen.append({"bron": "post", "vraag": paar["url"], "dag": dag, "doelen": sorted(doelen),
                      "zelfde_tekst": zelfde, "andere_redactie": paar["andere_redactie"],
                      "dagen": paar["dagen"], "taal": taal[claim],
                      **_twee(zoek(claim_fp(claim), tekst[claim], dag, doelen))})
    print(f"dezelfde post: {sum(r['bron'] == 'post' for r in rijen):,} vragen", flush=True)

    # Bron 2: Community Notes. De notetekst blijft lokaal en gaat niet in de uitvoer.
    r = meet(conn, notesmap, factcheck_hosts={h.lower() for h in hosts})
    nodig = {note for note, _, _ in r["bruggen"]}
    notetekst = {}
    for pad in sorted(notesmap.glob("notes-*.zip")):
        for rij in _rijen(notesmap, pad.stem):
            if rij["noteId"] in nodig:
                notetekst[rij["noteId"]] = " ".join(_URL.sub(" ", rij.get("summary", "")).split())
    notes = []
    for note, _, claim in r["bruggen"]:
        moment = r["brugdatum"].get(note)
        dag = datetime.fromtimestamp(moment / 1000, tz=timezone.utc).date().isoformat() if moment else ""
        if not dag or eerste.get(claim, "9999") >= dag or not notetekst.get(note):
            buiten_geheugen["notes"] += 1
            continue
        notes.append((note, claim, dag))
    fps = fingerprint_texts([notetekst[n] for n, _, _ in notes], versie)
    for (note, claim, dag), fp in zip(notes, fps):
        rijen.append({"bron": "notes", "vraag": note, "dag": dag, "doelen": [claim], "zelfde_tekst": False,
                      "andere_redactie": True, "dagen": (date.fromisoformat(dag)
                                                          - date.fromisoformat(eerste[claim])).days,
                      "taal": fp.language or "", **_twee(zoek(fp, notetekst[note], dag, {claim}))})
    print(f"Community Notes: {len(notes):,} vragen", flush=True)

    # Tweede punt: alles van 1 juli en later tegen de index van 1 juli.
    eerder_per_url = collections.defaultdict(set)
    for post_checks in per_post.values():
        for url, (claim, dag, _) in post_checks.items():
            eerder_per_url[url].update(c for c, d, _ in post_checks.values() if d < PEILDATUM)
    for url, (claim, dag, toegelaten) in sorted(checks.items()):
        if not toegelaten or not dag or dag < PEILDATUM or claim not in vector:
            continue
        doelen = {c for c in eerder_per_url.get(url, set()) if eerste.get(c, "9999") < PEILDATUM}
        zelfde = eerste.get(claim, "9999") < PEILDATUM
        if zelfde:
            doelen.add(claim)
        rijen.append({"bron": "juli", "vraag": url, "dag": dag, "doelen": sorted(doelen), "zelfde_tekst": zelfde,
                      "andere_redactie": None, "dagen": None, "taal": taal[claim],
                      **_twee(zoek(claim_fp(claim), tekst[claim], PEILDATUM, doelen))})
    print(f"sinds juli: {sum(r['bron'] == 'juli' for r in rijen):,} vragen", flush=True)

    (UIT / "uitkomsten.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen),
                                          encoding="utf-8")
    (UIT / "buiten-geheugen.json").write_text(json.dumps(buiten_geheugen), encoding="utf-8")
    # Om te lezen, lokaal: de ander-records uit de steekproef, met de teksten naast elkaar.
    for bron in ("post", "notes", "juli"):
        anders = [r for r in rijen if r["bron"] == bron and r["uitkomst"] == "ander record"]
        regels = []
        for r_ in steekproef(anders, STEEKPROEF[bron]):
            vraagtekst = notetekst[r_["vraag"]] if bron == "notes" else tekst[checks[r_["vraag"]][0]]
            regels.append(f"[{bron}] {r_['vraag']} -> {r_['kandidaat']} ({r_['gelijkenis']})\n"
                          f"  VRAAG: {vraagtekst[:400]}\n  GEVONDEN: {tekst[r_['kandidaat']][:300]}\n"
                          + "".join(f"  DOEL: {tekst[d][:200]}\n" for d in r_["doelen"][:2]))
        (UIT / f"te-lezen-{bron}.txt").write_text("\n".join(regels), encoding="utf-8")
    print(f"buiten het geheugen (doel nog niet gecheckt of buiten de index): {dict(buiten_geheugen)}")
    for bron in ("post", "notes", "juli"):
        c = collections.Counter(r["uitkomst"] for r in rijen if r["bron"] == bron)
        print(f"{bron}: {dict(c)}")


def _tellen() -> None:  # pragma: no cover - leest de uitvoer van meten
    import collections

    rijen = [json.loads(r) for r in (UIT / "uitkomsten.jsonl").read_text(encoding="utf-8").splitlines() if r]
    telling = tel(rijen, _labels())
    soorten = ("gevonden", "ander record", "verwant", "tegenspraak", "niets")
    for bron, n in telling.items():
        gelezen = n["ander record gelezen"]
        k, m = gelezen.get("anders", 0), sum(gelezen.values())
        print(f"\n{bron}: n {n['n']:,} · " + " · ".join(f"{s} {n.get(s, 0):,}" for s in soorten))
        if m:
            print(f"  ander record gelezen: {m}, zelfde bewering {gelezen.get('zelfde', 0)}, iets anders {k} "
                  f"(bovengrens {_bovengrens(k, m):.1%})")
        alle = [r for r in rijen if r["bron"] == bron]
        if bron == "post":
            for naam, deel in (("eigen formulering", [r for r in alle if not r["zelfde_tekst"]]),
                               ("letterlijk dezelfde tekst", [r for r in alle if r["zelfde_tekst"]])):
                c = collections.Counter(r["uitkomst"] for r in deel)
                print(f"  {naam}: n {len(deel):,} · " + " · ".join(f"{s} {c.get(s, 0)}" for s in soorten))
            for sleutel, waarde in (("andere redactie", lambda r: r["andere_redactie"]),
                                    ("gat", lambda r: gatklasse(r["dagen"]))):
                groepen = collections.defaultdict(list)
                for r in alle:
                    if not r["zelfde_tekst"]:
                        groepen[waarde(r)].append(r)
                for g, deel in sorted(groepen.items(), key=lambda kv: str(kv[0])):
                    c = collections.Counter(r["uitkomst"] for r in deel)
                    print(f"  {sleutel} {g}: n {len(deel):,} · gevonden {c['gevonden'] / len(deel):.1%}"
                          f" · ander record {c['ander record'] / len(deel):.1%} · niets {c['niets'] / len(deel):.1%}")
        if bron == "juli":
            gekoppeld = sum(1 for r in alle if r["doelen"])
            print(f"  met een menselijke koppeling aan een check van vóór 1 juli: {gekoppeld} van {len(alle)}")
        gevoelig = collections.Counter(r["met_ongedateerd"]["uitkomst"] for r in alle)
        print("  gevoeligheid, mét claims zonder datum: " + " · ".join(f"{s} {gevoelig.get(s, 0)}" for s in soorten))


def main() -> None:  # pragma: no cover
    import argparse
    import os

    import torch
    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="De terugkijktoets (#28.6 c)")
    parser.add_argument("stap", choices=("meten", "tellen"))
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    parser.add_argument("--notes", default="data/communitynotes")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--uit", help="een eigen uitvoermap, bijvoorbeeld bij een meting op een kopie (#25.37)")
    args = parser.parse_args()
    if args.uit:
        global UIT
        UIT = Path(args.uit)
    if args.stap == "tellen":
        _tellen()
        return
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    _meten(conn, load_config(), Path(args.feed), Path(args.notes))


if __name__ == "__main__":
    main()
