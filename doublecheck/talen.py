"""Materiaal per taal (P10 van fase 0, PLAN #32.0g, B47) en de aanvoer (P3, #32.0a).

Per taal van V1 (Engels, Spaans, Duits, Portugees) tellen wat er is om de
machine te meten: ware berichten (Wikinews), bekende en verse onware checks uit
de index, en echte beelden uit factcheckartikelen (M4FC). Een taal doet mee
met 300 ware en 200 valse berichten, waarvan 100 bekend en 100 vers.

Daarnaast de Duitse oordelen in zinsvorm. Daarvan kreeg ~3.900 de categorie
*onbekend*, omdat de redactie een zin schreef in plaats van een label
("Falsch. Bei der Verstorbenen …"). Haiku zet ze om, en ik lees er 50 na.
De omzetting komt in `data/talen/duits.jsonl` en niet in de database: zij
verandert wat de resolver toont, en dat is een release (B22, DR1).

Sinds B63 (#32.59) ook de Nederlandse en Franse oordelen in zinsvorm (vooral dpa), met dezelfde vraag voor een
Nederlandstalige of Franstalige factchecker, in `data/talen/oordelen-<taal>.jsonl`:

    python -m doublecheck.talen omzetten --taal nl|fr indienen|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

UIT = Path("data/talen")
DATABASE = Path("doublecheck.db")
LABELS = Path("docs/steekproeven/32.0g-duitse-oordelen.json")
TALEN = ("en", "es", "de", "pt")
M4FC_TALEN = {"English": "en", "Spanish": "es", "German": "de", "Portuguese": "pt"}
CATEGORIEEN = ("waar", "deels-waar", "misleidend", "onwaar", "onbewezen", "satire", "onbekend")
EIS = {"waar": 300, "onwaar_bekend": 100, "onwaar_vers": 100}
_NAAM = {"waar": "waar", "onwaar_bekend": "bekend onwaar", "onwaar_vers": "vers onwaar"}
VERS_DAGEN = 92  # de laatste drie maanden
ZAAD = 3207
N_LEZEN = 50
BUDGET = 1.0
SCHATTING = 0.0002  # per oordeel, Haiku in een batch

OMZETVRAAG = """A German fact-checker reviewed the claim below and wrote the verdict below. Which category does \
the verdict express?
- onwaar: the claim is false (also fabricated, a fake or wrongly dated photo or video, a scam)
- misleidend: misleading, missing context, out of context
- deels-waar: partly true and partly false
- waar: true
- onbewezen: unproven, no evidence either way
- satire: satire or parody
- onbekend: the verdict does not say which
Judge only what the fact-checker wrote. Do not judge the claim yourself.

Claim: {claim}
Verdict: {oordeel}"""

# De talen met oordelen in zinsvorm, en hoe de vraag de factchecker noemt (B63, #32.59)
OMZET_TALEN = {"de": "German", "nl": "Dutch or Flemish", "fr": "French-language"}
LABELS_TAAL = {"nl": Path("docs/steekproeven/32.59-oordelen-nl.json"), "fr": Path("docs/steekproeven/32.59-oordelen-fr.json")}
N_LEZEN_TAAL = 30


def omzetting_pad(taal: str) -> Path:
    return UIT / ("duits.jsonl" if taal == "de" else f"oordelen-{taal}.jsonl")


def batches_pad(taal: str) -> Path:
    return UIT / ("batches.jsonl" if taal == "de" else f"batches-{taal}.jsonl")


_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["waarom", "oordeel"],
           "properties": {"waarom": {"type": "string"}, "oordeel": {"type": "string", "enum": list(CATEGORIEEN)}}}


class Weigering(RuntimeError):
    pass


def door(telling: dict) -> list[str]:
    """Wat een taal nog mist om mee te doen; leeg als ze door is."""
    return [f"{_NAAM[k]}: {telling.get(k, 0)} van de {n}" for k, n in EIS.items() if telling.get(k, 0) < n]


def lees_omzetting(tekst: str) -> str:
    """De categorie uit het antwoord van Haiku; alles daarbuiten is onbekend, er wordt nooit geraden."""
    try:
        oordeel = json.loads(tekst).get("oordeel")
    except (json.JSONDecodeError, AttributeError):
        return "onbekend"
    return oordeel if oordeel in CATEGORIEEN else "onbekend"


def omzetverzoek(custom_id: str, claim: str, oordeel: str, taal: str = "de") -> dict:
    from doublecheck.leraar import MODELLEN

    vraag = OMZETVRAAG.replace("A German fact-checker", f"A {OMZET_TALEN[taal]} fact-checker")
    return {"custom_id": custom_id, "params": {
        "model": MODELLEN["haiku"]["id"], "max_tokens": 1_000,
        "messages": [{"role": "user", "content": vraag.format(claim=claim, oordeel=oordeel)}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def steekproef(rijen: list[dict], n: int = N_LEZEN) -> list[dict]:
    """Vaste steekproef om na te lezen, onafhankelijk van de volgorde van binnenkomst."""
    rijen = sorted(rijen, key=lambda r: r["id"])
    random.Random(ZAAD).shuffle(rijen)
    return rijen[:n]


def overeenstemming(rijen: list[dict], labels: dict[str, str], n: int = N_LEZEN) -> dict:
    gelezen = steekproef(rijen, n)
    open_ = [r["id"] for r in gelezen if r["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} van de {len(gelezen)} nog zonder label in {LABELS.name}; eerst lezen")
    gelijk = sum(labels[r["id"]] == r["oordeel"] for r in gelezen)
    return {"gelezen": len(gelezen), "gelijk": gelijk, "verschil": len(gelezen) - gelijk}


# --- tellen ----------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def tellen(conn: sqlite3.Connection, vandaag: date | None = None) -> dict:  # pragma: no cover - op de database
    from doublecheck.toelating import buiten_index

    vers = ((vandaag or date.today()) - timedelta(days=VERS_DAGEN)).isoformat()
    buiten = buiten_index(conn)
    omgezet = {r["id"]: r["oordeel"] for r in _jsonl(UIT / "duits.jsonl")}
    checks: dict[str, Counter] = {t: Counter() for t in TALEN}
    nieuwste = ""
    for fid, cid, taal, oordeel, datum in conn.execute(
            "SELECT f.factcheck_id, f.claim_id, c.language, f.verdict_normalized, f.review_date "
            "FROM factcheck f JOIN claim c USING(claim_id) WHERE c.language IN ('en', 'es', 'de', 'pt')"):
        if cid in buiten:
            continue
        nieuwste = max(nieuwste, datum)
        if oordeel == "onbekend" and str(fid) in omgezet:
            oordeel = omgezet[str(fid)]
            checks[taal]["omgezet"] += 1
        checks[taal][oordeel] += 1
        if oordeel == "onwaar" and datum >= vers:
            checks[taal]["onwaar_vers"] += 1
    m4fc = Counter()
    pad = Path("data/extern/m4fc/M4FC.json")
    if pad.exists():
        m4fc = Counter(M4FC_TALEN.get(r.get("claim_language")) for r in json.loads(pad.read_text(encoding="utf-8")))
    uit = {"_meta": f"P10 (PLAN #32.0g): materiaal per taal; vers = review_date vanaf {vers}; nieuwste check in de "
                    f"database {nieuwste[:10]}", "talen": {}}
    for taal in TALEN:
        wikinews = Path(f"data/echtnieuws/wikinews-{taal}.jsonl")
        c = checks[taal]
        telling = {"waar": sum(1 for _ in wikinews.open(encoding="utf-8")) if wikinews.exists() else 0,
                   "onwaar_bekend": c["onwaar"], "onwaar_vers": c["onwaar_vers"]}
        uit["talen"][taal] = {**telling, "checks": {k: c[k] for k in CATEGORIEEN if c[k]},
                              "omgezet": c["omgezet"], "m4fc_beelden": m4fc[taal], "mist": door(telling)}
    return uit


def aanvoer(conn: sqlite3.Connection, feed: Path | None = None) -> dict:  # pragma: no cover - op de database
    """P3 (PLAN #32.0a): per maand over 24 maanden de checks in de database (op de datum van de check, per taal
    van V1, en het aantal uitgevers), en uit de laatste stand van de feed wat er per maand bijkwam (op de
    datum dat het in de feed kwam)."""
    rijen = conn.execute(
        "SELECT substr(f.review_date, 1, 7), count(*), sum(c.language = 'en'), sum(c.language = 'es'), "
        "sum(c.language = 'de'), sum(c.language = 'pt'), count(DISTINCT f.publisher) FROM factcheck f "
        "JOIN claim c USING(claim_id) GROUP BY 1 ORDER BY 1").fetchall()
    uit = {"database": {m: dict(zip(("checks", "en", "es", "de", "pt", "uitgevers"), r)) for m, *r in rijen[-25:]}}
    if feed and feed.exists():
        data = json.loads(feed.read_text(encoding="utf-8"))
        per_maand: Counter = Counter()
        uitgevers: dict[str, set] = {}
        for item in data["dataFeedElement"]:
            m = (item.get("dateCreated") or "")[:7]
            per_maand[m] += 1
            uitgevers.setdefault(m, set()).update((cr.get("author") or {}).get("name") for cr in item.get("item") or [])
        uit["feed"] = {"stand": data.get("dateModified"),
                       "per maand": {m: {"checks": per_maand[m], "uitgevers": len(uitgevers[m])}
                                     for m in sorted(per_maand)[-25:]}}
    return uit


# --- de CLI ------------------------------------------------------------------------------------

def _duitse_rijen(conn: sqlite3.Connection, taal: str = "de") -> list[dict]:  # pragma: no cover - op de database
    from doublecheck.toelating import buiten_index

    buiten = buiten_index(conn)
    return [{"id": str(fid), "claim": claim, "oordeel": oordeel} for fid, cid, claim, oordeel in conn.execute(
        "SELECT f.factcheck_id, f.claim_id, c.canonical_text, f.verdict_original FROM factcheck f "
        "JOIN claim c USING(claim_id) WHERE c.language = ? AND f.verdict_normalized = 'onbekend'", (taal,))
        if cid not in buiten]


def _labels(pad: Path = LABELS) -> dict[str, str]:
    if not pad.exists():
        return {}
    return {r["id"]: r["label"] for r in json.loads(pad.read_text(encoding="utf-8")).get("oordelen", [])}


def main() -> None:  # pragma: no cover - CLI, met de database en de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="Materiaal per taal (PLAN #32.0g)")
    parser.add_argument("stap", choices=("aanvoer", "tellen", "duits", "omzetten"))
    parser.add_argument("sub", nargs="?", default="", choices=("", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("--taal", choices=("nl", "fr"), help="omzetten: de taal (B63, #32.59)")
    args = parser.parse_args()
    taal = "de" if args.stap == "duits" else args.taal
    UIT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    if args.stap == "aanvoer":
        standen = sorted(Path("data/vooruitblik/feed").glob("feed-*.json"))
        uit = aanvoer(conn, standen[-1] if standen else None)
        (UIT / "aanvoer.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(uit, ensure_ascii=False, indent=1))
        return
    if args.stap == "tellen":
        uit = tellen(conn)
        (UIT / "tellen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(uit, ensure_ascii=False, indent=1))
        return
    if args.stap == "omzetten" and not taal:
        raise SystemExit("omzetten vraagt --taal nl of fr")
    rijen = _duitse_rijen(conn, taal)
    per_id = {r["id"]: r for r in rijen}
    omgezet = _jsonl(omzetting_pad(taal))
    if args.sub in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.leraar import MODELLEN
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
        batches = _jsonl(batches_pad(taal))
        if args.sub == "indienen":
            klaar = {r["id"] for r in omgezet} | {i for b in batches for i in b["ids"]}
            verzoeken = [omzetverzoek(f"{taal}-{r['id']}", r["claim"], r["oordeel"], taal) for r in rijen
                         if r["id"] not in klaar]
            geschat = len(verzoeken) * SCHATTING
            uitgegeven = sum(b.get("werkelijk") or b["schatting"] for b in batches)
            if not verzoeken or uitgegeven + geschat > BUDGET:
                raise Weigering(f"{len(verzoeken)} verzoeken, ${uitgegeven:.2f} plus ${geschat:.2f} tegen ${BUDGET:.2f}")
            batch = client.messages.batches.create(requests=verzoeken)
            batches.append({"id": batch.id, "schatting": round(geschat, 3),
                            "ids": [v["custom_id"].split("-", 1)[1] for v in verzoeken]})
            print(f"batch {batch.id}: {len(verzoeken)} verzoeken, geschat ${geschat:.2f}")
        else:
            prijs = MODELLEN["haiku"]
            for b in batches:
                if b.get("werkelijk") is not None or client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    continue
                kosten = 0.0
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded":
                        print(f"{r.custom_id}: {r.result.type}")
                        continue
                    msg = r.result.message
                    tekst = "".join(getattr(blok, "text", "") or "" for blok in msg.content)
                    kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
                    try:
                        waarom = json.loads(tekst).get("waarom", "")
                    except (json.JSONDecodeError, AttributeError):
                        waarom = ""
                    omgezet.append({"id": r.custom_id.split("-", 1)[1], "oordeel": lees_omzetting(tekst), "waarom": waarom})
                b["werkelijk"] = round(kosten, 4)
            omzetting_pad(taal).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in omgezet),
                                           encoding="utf-8")
            print(Counter(r["oordeel"] for r in omgezet), f"${sum(b.get('werkelijk') or 0 for b in batches):.2f}")
        batches_pad(taal).write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        return
    labels = _labels(LABELS_TAAL.get(taal, LABELS))
    n = N_LEZEN if taal == "de" else N_LEZEN_TAAL
    if args.sub == "lezen":
        for r in steekproef(omgezet, n):
            if r["id"] not in labels:
                bron = per_id.get(r["id"], {})
                print(f"\n[{r['id']}] HAIKU: {r['oordeel']} — {r.get('waarom', '')}\n  CLAIM: {bron.get('claim', '')[:300]}"
                      f"\n  OORDEEL: {bron.get('oordeel', '')[:400]}")
        return
    print(json.dumps({"omgezet": len(omgezet), "per categorie": dict(Counter(r["oordeel"] for r in omgezet)),
                      "nagelezen": overeenstemming(omgezet, labels, n)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
