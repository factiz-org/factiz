"""Bekend nepnieuws in echte vorm (P6 van fase 0, PLAN #32.0d, B47).

Bekend nepnieuws kwam in de eerdere rondes vaak in de woorden van de
factchecker binnen, en dan vindt het geheugen de check bijna altijd. In het
wild staat het er anders. Twee delen van elk 50, vooraf vastgelegd:

- *R, zoals een andere redactie het opschreef:* uit de groepen van §71 (een
  virale post, gecheckt door twee of meer redacties). Het bericht is de
  Engelse claimtekst van redactie A. A en zijn cluster zijn verborgen, dus
  bewijs komt van een andere redactie in de groep of van het web;
- *D, zoals iemand het doorstuurt:* een bekende Engelse onware check, door
  Haiku herschreven als doorgestuurd appbericht, getekend als chatbericht
  (alleen in het geheugen) en gelezen door de OCR zoals in het product.

Door Factiz zoals het product (`berichtcontrole`). Telt rood met bewijs.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as t
from doublecheck import gebruikerstoets as g
from doublecheck import herstel as h

UIT = Path("data/echtevorm")
LABELS = Path("docs/steekproeven/32.0d-echte-vorm.json")
BUDGET = 4.0  # PLAN #32.0d
ZAAD = 3204
N = 50
EIS = 0.70
PII_SCHUIF = 30_000  # andere verzonnen namen en nummers dan in eerdere toetsen
ONWAAR = ("onwaar", "misleidend")
SCHATTING = {"factiz": 0.022, "feit": 0.0015, "vorm": 0.0013, "herkansing": 0.03, "haiku": 0.0003}
BEWEZEN = ("bewijst", "bewijst via factcheck")

HERSCHRIJFVRAAG = """Below is a false claim that fact-checkers have debunked. For a test of a fact-checking tool, \
rewrite it as a message that someone would forward in a WhatsApp group: in English, in their own words, as if they \
believe it, in one to three sentences. Urgency, capitals or emojis are fine. Keep the core claim exactly the same: \
do not add, remove or change facts, names, numbers or places. Do not mention fact-checks or that it is false.

Claim: {claim}"""

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["bericht"],
           "properties": {"bericht": {"type": "string"}}}


class Weigering(RuntimeError):
    pass


def _schud(rijen: list, naam: str) -> list:
    rijen = sorted(rijen, key=lambda r: r if isinstance(r, str) else r["id"] if isinstance(r, dict) else min(r))
    random.Random(f"{ZAAD}-{naam}").shuffle(rijen)
    return rijen


def _helften(stukken: list[dict], naam: str) -> list[dict]:
    volgorde = {sid: i for i, sid in enumerate(_schud([s["id"] for s in stukken], naam))}
    return [{**s, "helft": "toets" if volgorde[s["id"]] % 2 == 0 else "ontwikkel"} for s in stukken]


def kies_groepen(groepen: list[set[str]], info: dict[str, dict], gebruikt: set[str], n: int = N) -> list[dict]:
    """Deel R: per groep één Engelse onware claim van redactie A als bericht, A en zijn cluster verborgen,
    en minstens één andere redactie (onwaar of misleidend, buiten het cluster van A) als mogelijk bewijs."""
    uit, bezet = [], set()
    for groep in _schud([frozenset(x) for x in groepen], "groepen"):
        if len(uit) >= n:
            break
        if groep & (gebruikt | bezet) or not all(c in info for c in groep):
            continue
        for a in sorted(groep):
            ia = info[a]
            if ia["taal"] != "en" or ia["oordeel"] != "onwaar" or h.omschrijving(ia["tekst"]):
                continue
            verborgen = {a} | set(ia["cluster"])
            partners = [b for b in sorted(groep) if b not in verborgen and info[b]["oordeel"] in ONWAAR]
            if not partners:
                continue
            eigen = (set(partners) | {c for b in partners for c in info[b]["cluster"]}) - verborgen
            uit.append({"id": f"R:{a}", "deel": "R", "zaak": a, "tekst": " ".join(ia["tekst"].split()),
                        "verborgen": sorted(verborgen), "eigen": sorted(eigen)})
            bezet |= set(groep) | verborgen | eigen
            break
    return _helften(uit, "R")


def kies_doorgestuurd(pool: list[dict], gebruikt: set[str], n: int = N,
                      afgewezen: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """Deel D: bekende onware checks in een vaste volgorde; een afgewezen herschrijving wordt vervangen door de
    volgende in dezelfde volgorde."""
    uit = []
    for c in _schud(pool, "doorgestuurd"):
        if len(uit) >= n:
            break
        if c["id"] in gebruikt or c["id"] in afgewezen:
            continue
        uit.append({"id": f"D:{c['id']}", "deel": "D", "zaak": c["id"], "claim": c["tekst"], "verborgen": [],
                    "eigen": sorted({c["id"]} | set(c["cluster"]))})
    return _helften(uit, "D")


def lees_herschrijving(tekst: str) -> str | None:
    """Het appbericht uit het antwoord van Haiku; een weigering of iets leegs is geen bericht."""
    try:
        bericht = json.loads(tekst).get("bericht")
    except (json.JSONDecodeError, AttributeError):
        return None
    return bericht.strip() if isinstance(bericht, str) and bericht.strip() else None


def _tel(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict) -> dict:
    uit: dict = {}
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if u is None:
            continue
        d = uit.setdefault(s["deel"], Counter())
        d["n"] += 1
        d[u["kleur"] or "geen kleur"] += 1
        if "over een bewering" in (u.get("regels") or ()):
            d["over een bewering"] += 1
        if u["kleur"] != "rood":
            continue
        if u["eigen_bewijs"]:
            d["rood met bewijs"] += 1
            d["bewijs uit de eigen groep"] += 1
        elif u["bronnen"]:
            if (s["id"], "bewijs") not in labels:
                raise Weigering(f"({s['id']}, bewijs) heeft geen label in {LABELS.name}; eerst lezen")
            if labels[(s["id"], "bewijs")] in BEWEZEN:
                d["rood met bewijs"] += 1
                d["bewijs van een andere bron"] += 1
        else:
            d["rood zonder bron"] += 1
    velden = ("n", "rood", "rood met bewijs", "groen", "geen kleur", "over een bewering")
    return {deel: {**{v: 0 for v in velden}, **d} for deel, d in uit.items()}


def telling(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict) -> dict:
    """Per deel rood met bewijs, en de eis van PLAN #32.0d. Weigert zolang een rood met een andere bron dan de
    eigen groep niet gelezen is."""
    uit = _tel(stukken, uitkomsten, labels)
    n = sum(d["n"] for d in uit.values())
    bewezen = sum(d["rood met bewijs"] for d in uit.values())
    uit["eisen"] = {"minstens 70% rood met bewijs": n > 0 and bewezen >= EIS * n}
    uit["toetshelft"] = _tel([s for s in stukken if s.get("helft") == "toets"], uitkomsten, labels)
    return uit


# --- de pools, de set en de CLI -------------------------------------------------------------------

def _gebruikt() -> set[str]:  # pragma: no cover - op de eerdere sets
    ids = set()
    for pad in Path("data").glob("*/set.jsonl"):
        for s in t._jsonl(pad):
            ids.update(x for x in [s.get("zaak"), *(s.get("eigen") or [])] if x)
            if str(s.get("sleutel", "")).startswith("C:"):
                ids.add(s["sleutel"][2:])
    return ids


def pools() -> tuple[list[dict], list[dict]]:  # pragma: no cover - op de database en de feed
    import sqlite3

    from doublecheck import natuurlijk
    from doublecheck import verificatie as v
    from doublecheck.clustering import cluster_members
    from doublecheck.toelating import buiten_index

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    buiten = buiten_index(conn)
    groepen = natuurlijk.groepen_uit_feed(conn, "data/datacommons-claimreview.json")

    def info_van(cid: str) -> dict:
        c = conn.execute("SELECT language, canonical_text FROM claim WHERE claim_id = ?", (cid,)).fetchone()
        f = conn.execute("SELECT verdict_normalized FROM factcheck WHERE claim_id = ? ORDER BY review_date DESC "
                         "LIMIT 1", (cid,)).fetchone()
        return {"taal": c["language"], "oordeel": f["verdict_normalized"], "tekst": c["canonical_text"],
                "cluster": cluster_members(conn, cid) - {cid}}

    nodig = {c for gr in groepen for c in gr if c not in buiten}
    info = {c: info_van(c) for c in nodig}
    gebruikt = _gebruikt()
    r = kies_groepen([gr for gr in groepen if not gr & buiten], info, gebruikt)
    in_groepen = {c for gr in groepen for c in gr}
    rijen = conn.execute("SELECT c.claim_id, c.canonical_text FROM claim c JOIN factcheck f USING(claim_id) "
                         "WHERE c.language = 'en' AND f.verdict_normalized = 'onwaar' GROUP BY c.claim_id").fetchall()
    pool = [{"id": cid, "tekst": " ".join(tekst.split())} for cid, tekst in rijen
            if cid not in buiten and cid not in in_groepen and 40 <= len(tekst) <= 300 and not h.omschrijving(tekst)]
    gekozen = _schud(pool, "doorgestuurd")[:200]  # het cluster alleen voor wat in aanmerking komt
    for c in gekozen:
        c["cluster"] = cluster_members(conn, c["id"]) - {c["id"]}
    _ = v
    return r, gekozen


def _labelbestand() -> dict:
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def lees_labels() -> dict:
    return {(r["id"], r["wat"]): r["label"] for r in _labelbestand().get("oordelen", [])}


def main() -> None:  # pragma: no cover - CLI, met de database, de OCR en de Batch API
    import argparse

    import anthropic

    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="Bekend nepnieuws in echte vorm (PLAN #32.0d)")
    parser.add_argument("stap", choices=("kiezen", "herschrijven", "set", "indienen", "herkansing", "vorm", "ophalen",
                                         "lezen", "tellen"))
    parser.add_argument("sub", nargs="?", default="", help="herschrijven: indienen, ophalen of lezen")
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    config = load_config(None)
    laad_sleutel()
    client = anthropic.Anthropic()
    batches = t._jsonl(UIT / "batches.jsonl")

    def uitgegeven() -> float:
        return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in batches)

    def dien_in(verzoeken: list[dict], geschat: float, stap: str) -> None:
        if not verzoeken:
            raise SystemExit("niets in te dienen")
        if uitgegeven() + geschat > BUDGET:
            raise Weigering(f"${uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        batch = client.messages.batches.create(requests=verzoeken)
        batches.append({"id": batch.id, "stap": stap, "schatting": round(geschat, 3),
                        "ids": [r["custom_id"] for r in verzoeken]})
        t._schrijf(UIT / "batches.jsonl", batches)
        print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${uitgegeven():.2f} van ${BUDGET:.2f}")

    def haal_op(verwerk) -> None:
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                werkelijk += verwerk(r.custom_id, r.result.message)
            b["werkelijk"] = round(werkelijk, 4)
        t._schrijf(UIT / "batches.jsonl", batches)

    afgewezen = {r["id"] for r in _labelbestand().get("set", [])}
    if args.stap == "kiezen":
        r, pool = pools()
        d = kies_doorgestuurd(pool, _gebruikt(), afgewezen=afgewezen)
        t._schrijf(UIT / "pool-d.jsonl", [{**c, "cluster": sorted(c["cluster"])} for c in pool])
        t._schrijf(UIT / "keuze.jsonl", r + d)
        print(Counter(s["deel"] for s in r + d), Counter((s["deel"], s["helft"]) for s in r + d))
        return
    keuze = t._jsonl(UIT / "keuze.jsonl")
    gemaakt = {x["id"]: x["bericht"] for x in t._jsonl(UIT / "gemaakt.jsonl")}
    if args.stap == "herschrijven":
        d = [s for s in keuze if s["deel"] == "D"]
        if args.sub == "indienen":
            verzoeken = [g.haiku_verzoek(f"g-{t.batch_id(s['id'])}", HERSCHRIJFVRAAG.format(claim=s["claim"]), _SCHEMA)
                         for s in d if s["id"] not in gemaakt]
            dien_in(verzoeken, len(verzoeken) * SCHATTING["haiku"], "herschrijven")
        elif args.sub == "ophalen":
            per_bid = {t.batch_id(s["id"]): s for s in d}

            def verwerk(cid, msg):
                bericht = lees_herschrijving(g._tekst(msg))
                with (UIT / "gemaakt.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": per_bid[cid[2:]]["id"], "bericht": bericht}, ensure_ascii=False) + "\n")
                return t.kosten_batch(bc.gebruik_uit(msg)) / 20  # Haiku kost ~een twintigste van Sonnet

            haal_op(verwerk)
        else:
            for s in d:
                print(f"\n[{s['id']}] CLAIM: {s['claim']}\n  BERICHT: {gemaakt.get(s['id'])}")
        return
    if args.stap == "set":
        from doublecheck import routemeting as rm
        from doublecheck import verificatie as v
        from doublecheck.storage import connect

        conn = connect("doublecheck.db")
        uit = []
        for i, s in enumerate(keuze):
            if s["deel"] == "R":
                bericht = bc.bericht_uit(s["tekst"], None, config.ocr)
                pii = None
            else:
                if not gemaakt.get(s["id"]):
                    raise Weigering(f"{s['id']}: eerst herschrijven, of afwijzen in {LABELS.name}")
                import io

                pii = rm.nep_pii(PII_SCHUIF + i)
                buf = io.BytesIO()
                rm.teken_chat(gemaakt[s["id"]], pii).save(buf, format="PNG")
                bericht = bc.bericht_uit(None, buf.getvalue(), config.ocr)
            voorbereid = bc.voorbereiden(conn, config, bericht, frozenset(s["verborgen"])) if bericht.strip() else \
                {"tekst": bericht, "geheugen": [], "kandidaten": []}
            rij = {**s, "tekst": voorbereid["tekst"], "geheugen": voorbereid["geheugen"],
                   "kandidaten": voorbereid["kandidaten"], "datum": None,
                   "eigen in geheugen": any(k["claim"] in set(s["eigen"]) for k in voorbereid["geheugen"])}
            assert not {k["claim"] for k in voorbereid["geheugen"]} & set(s["verborgen"])
            if pii:
                rij["lekken"] = rm.lekken(voorbereid["tekst"], pii)
            uit.append(rij)
            print(f"\r{i + 1}", end="", flush=True)
        t._schrijf(UIT / "set.jsonl", uit)
        print("\n", Counter((s["deel"], s["eigen in geheugen"]) for s in uit))
        _ = v
        return
    stukken = t._jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    per_bid = {t.batch_id(s["id"]): s for s in stukken}
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    tabel = bc.ijktabel(config)
    ingediend = {i for b in batches for i in b["ids"]}
    if args.stap in ("indienen", "herkansing", "vorm"):
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            nog = [s for s in stukken if f"m-{t.batch_id(s['id'])}" not in ingediend]
            if args.proef:
                nog = [s for deel in "RD" for s in [x for x in nog if x["deel"] == deel][: args.proef]]
            zinnen = bc.feitzinnen()
            for s in nog:
                b = t.batch_id(s["id"])
                verzoeken.append({"custom_id": f"m-{b}", "params": bc.machineverzoek(s["tekst"], s["geheugen"], None,
                                                                                      config)})
                geschat += SCHATTING["factiz"]
                for k in ("A", "B") if s["kandidaten"] else ():
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{b}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        elif args.stap == "herkansing":
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and f"h-{t.batch_id(r['id'])}" not in ingediend:
                    s = per_id[r["id"]]
                    verzoeken.append({"custom_id": f"h-{t.batch_id(s['id'])}", "params": bc.met_herkansing(
                        bc.machineverzoek(s["tekst"], s["geheugen"], None, config), zin)})
                    geschat += SCHATTING["herkansing"]
        else:
            verzoeken = h.vormvragen(stukken, t.uitkomsten_van(stukken, antwoorden, tabel), config, ingediend)
            geschat = len(verzoeken) * SCHATTING["vorm"]
        dien_in(verzoeken, geschat, args.stap)
        return
    if args.stap == "ophalen":
        klaar = {(r["soort"], r["id"], r.get("sleutel")) for r in antwoorden}
        zinnen = bc.feitzinnen()

        def verwerk(cid, msg):
            kort, rest = cid.split("-", 1)
            if kort == "f":
                stuk, sleutel = rest.rsplit("__", 1)
                s = per_bid[stuk]
                rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel,
                       **bc.feitantwoord(msg, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel, zinnen, config)[1])}
            elif kort == "v":
                tekst = g._tekst(msg)
                rij = {"soort": "vorm", "id": per_bid[rest]["id"], "sleutel": None, **bc.lees_vorm(tekst),
                       "waarom": h._waarom(tekst)}
            else:
                s = per_bid[rest]
                rij = {"soort": "machine" if kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                       **bc.machineantwoord(msg, s["geheugen"])}
            rij["kosten"] = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
            if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            return rij["kosten"]

        haal_op(verwerk)
        antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
        print(Counter((per_id[r["id"]]["deel"], r["soort"]) for r in antwoorden),
              f"\nherkansing nodig: {sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}",
              f"\nuitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    uitkomsten = g.factiz_uitkomsten(stukken, antwoorden, tabel)
    labels = lees_labels()
    if args.stap == "tellen":
        uit = telling(stukken, uitkomsten, labels)
        uit["eigen check in het geheugen"] = {deel: sum(s["eigen in geheugen"] for s in stukken if s["deel"] == deel)
                                              for deel in "RD"}
        uit["maskeren"] = dict(Counter(k for s in stukken if "lekken" in s for k, w in s["lekken"].items() if w))
        print(json.dumps(uit, ensure_ascii=False, indent=1))
        print(f"uitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if not u or u["kleur"] != "rood" or u["eigen_bewijs"] or not u["bronnen"] or (s["id"], "bewijs") in labels:
            continue
        if s.get("helft") == "toets":
            print(f"\n[{s['id']}] (toetshelft: alleen het bewijs lezen)")
        print(f"\n[{s['id']} · {s['deel']}] ROOD: bewijst, bewijst via factcheck, bewijst niet, set fout?"
              f"\n  BERICHT: {s['tekst'][:400]}\n  FACTIZ: {u.get('oordeel')}; {u.get('bewering')}"
              f"\n  UITLEG: {u.get('uitleg')}")
        for b in u["bronnen"][:3]:
            print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:250]}")


if __name__ == "__main__":
    main()
