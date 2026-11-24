"""Eerst meten of een radar iets vindt (PLAN #37.0; PO 2026-11-18: "moeten we niet eerst een 'bullshit radar' bouwen om te
weten óf we iets kunnen vinden?").

    python -m doublecheck.radarvoormeting notes [--export data/communitynotes/2026-11-17] [--vanaf 2026-05-25]
    python -m doublecheck.hittewacht -- python -m doublecheck.radarvoormeting koppelen
    python -m doublecheck.radarvoormeting lezen [--vooruit]
    python -m doublecheck.radarvoormeting tellen

*Terug:* de maatstaf is `docs/steekproeven/37.0-maatstaf.json`, de factchecks van AFP Factcheck Nederland (titel, datum,
link). Per factcheck zoeken we of de bewering eerder opduikt in twee bronnen die wij kunnen lezen: een note op X in het
Nederlands (de export van X, alleen intern), of een check in een andere taal in het archief. Koppelen lokaal met bge-m3
(de versie uit config); elke koppeling wordt gelezen. *Vooruit:* de notes in het Nederlands van de laatste zeven dagen, per
post, als lijst van kandidaten; gelezen of het een bewering is die te checken valt en of iemand haar al checkte.

De lat staat vooraf in PLAN: een radar als een derde van de factchecks minstens twee dagen eerder in een bron opduikt, of
als de week minstens drie te checken kandidaten heeft met minstens één die nog niemand checkte.

Van een note bewaren we het nummer, de datum, de status en de vector, nooit de tekst: `lezen` haalt de tekst opnieuw uit
de zip, alleen in het geheugen (zoals `communitynotes`). De labels staan in `docs/steekproeven/37.0-radar.json`; `tellen`
weigert zolang een koppeling of kandidaat geen label heeft. Uitvoer in `data/radar/voormeting/`.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAATSTAF = WORTEL / "docs" / "steekproeven" / "37.0-maatstaf.json"
LABELS = WORTEL / "docs" / "steekproeven" / "37.0-radar.json"
MAP = WORTEL / "data" / "radar" / "voormeting"
EXPORT = WORTEL / "data" / "communitynotes" / "2026-11-17"
VECTOREN = WORTEL / "data" / "lijktop"
TOP = 5                     # kandidaten per bron en per factcheck, die allemaal gelezen worden
VOORSPRONG = 2              # dagen: zo veel eerder moet een bron het hebben om te tellen (de lat in PLAN)
DEEL = 1 / 3                # het aandeel factchecks dat eerder moet opduiken
WEEK_KANDIDATEN = 3         # of zo veel te checken kandidaten in één week
WEEK_NIEUW = 1              # waarvan minstens zoveel die nog niemand checkte
ARCHIEF_RECENT = 60         # dagen: een check in het archief zegt alleen dat iets nu rondgaat als ze zo recent is; een oude
                            # check van dezelfde bewering zegt dat ze terugkomt, niet dat ze nu rondgaat (2026-11-18)


class Weigering(Exception):
    """De meting mag zo niet verder."""


def dagen_eerder(bron: str | None, check: str) -> int | None:
    """Hoeveel dagen de bron (een datum) vóór de factcheck lag; niets zonder bron."""
    if not bron:
        return None
    return (date.fromisoformat(check[:10]) - date.fromisoformat(bron[:10])).days


def telt(bron: str, koppeling: dict, check: str) -> bool:
    """Of een koppeling meetelt als vroeg signaal: gelezen als dezelfde bewering, en uit het archief alleen als recent."""
    if not koppeling.get("zelfde"):
        return False
    voor = dagen_eerder(koppeling["datum"], check)
    return voor is not None and (bron != "archief" or voor <= ARCHIEF_RECENT)


def eerste_vondst(labels: dict, check: str = "9999-12-31") -> str | None:
    """De vroegste datum van een koppeling die meetelt, over beide bronnen."""
    data = [k["datum"] for bron in ("notes", "archief") for k in labels.get(bron, []) if telt(bron, k, check)]
    return min(data) if data else None


def tellen(maatstaf: list[dict], labels: dict, vooruit: list[dict]) -> dict:
    """De uitslag tegen de lat. Weigert zolang een factcheck of kandidaat geen label heeft."""
    open_ = [c["id"] for c in maatstaf if c["id"] not in labels]
    open_ += [k["post"] for k in vooruit if "te_checken" not in k]
    if open_:
        raise Weigering(f"nog {len(open_)} zonder label, bijvoorbeeld {open_[:3]}")
    per_check, per_bron = [], {"notes": 0, "archief": 0}
    for c in maatstaf:
        lab = labels[c["id"]]
        eerst = eerste_vondst(lab, c["datum"])
        voor = dagen_eerder(eerst, c["datum"])
        per_check.append({"id": c["id"], "datum": c["datum"], "eerst": eerst, "dagen_eerder": voor})
        for bron in per_bron:
            if any(telt(bron, k, c["datum"]) and dagen_eerder(k["datum"], c["datum"]) >= VOORSPRONG for k in lab.get(bron, [])):
                per_bron[bron] += 1
    op_tijd = [p for p in per_check if p["dagen_eerder"] is not None and p["dagen_eerder"] >= VOORSPRONG]
    voorsprongen = sorted(p["dagen_eerder"] for p in op_tijd)
    te_checken = [k for k in vooruit if k["te_checken"]]
    nieuw = [k for k in te_checken if not k.get("al_gecheckt")]
    terug_gehaald = len(op_tijd) >= DEEL * len(maatstaf)
    vooruit_gehaald = len(te_checken) >= WEEK_KANDIDATEN and len(nieuw) >= WEEK_NIEUW
    return {"factchecks": len(maatstaf), "eerder_in_een_bron": len(op_tijd), "per_bron": per_bron,
            "mediaan_dagen_eerder": voorsprongen[len(voorsprongen) // 2] if voorsprongen else None,
            "week_kandidaten": len(vooruit), "week_te_checken": len(te_checken), "week_nog_niet_gecheckt": len(nieuw),
            "terug_gehaald": terug_gehaald, "vooruit_gehaald": vooruit_gehaald,
            "radar": terug_gehaald or vooruit_gehaald, "per_check": per_check}


# --- de bestanden en het model ---------------------------------------------------------------------------------------

def _datum(millis: str) -> str:
    return datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).date().isoformat()


def _rijen(export: Path, naam: str):  # pragma: no cover - bestanden
    for pad in sorted(export.glob(f"{naam}-*.zip")):
        with zipfile.ZipFile(pad) as z:
            for binnen in z.namelist():
                with z.open(binnen) as f:
                    yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t",
                                              quoting=csv.QUOTE_NONE)


def _notes(export: Path, vanaf: str) -> None:  # pragma: no cover - bestanden en het model
    """De notes in het Nederlands vanaf `vanaf`: nummer, datum, post, status en vector; de tekst alleen in het geheugen."""
    import numpy as np
    import py3langid

    from doublecheck.config import load_config
    from doublecheck.embedding import _load_model, normaliseer_voor_embedding

    csv.field_size_limit(10_000_000)
    status = {r["noteId"]: r["currentStatus"] for r in _rijen(export, "noteStatusHistory")}
    gekozen, teksten = [], []
    gezien = 0
    for r in _rijen(export, "notes"):
        gezien += 1
        dag = _datum(r["createdAtMillis"])
        tekst = (r.get("summary") or "").strip()
        if dag < vanaf or len(tekst) < 30 or py3langid.classify(tekst)[0] != "nl":
            continue
        gekozen.append({"note": r["noteId"], "datum": dag, "post": r["tweetId"], "status": status.get(r["noteId"], ""),
                        "classificatie": r.get("classification", "")})
        teksten.append(tekst)
    print(f"{gezien} notes gelezen, {len(gekozen)} in het Nederlands vanaf {vanaf}", flush=True)
    versie = load_config(None).model_versions.text_embedding
    model = _load_model(versie, "mps")
    model.max_seq_length = 256
    x = model.encode([normaliseer_voor_embedding(t) for t in teksten], normalize_embeddings=True, batch_size=64,
                     show_progress_bar=False).astype(np.float32)
    MAP.mkdir(parents=True, exist_ok=True)
    np.save(MAP / "notes.npy", x)
    (MAP / "notes.json").write_text(json.dumps({"model": versie, "export": export.name, "vanaf": vanaf,
                                                "notes": gekozen}, ensure_ascii=False), encoding="utf-8")


def _koppelen() -> None:  # pragma: no cover - bestanden en het model
    """Per factcheck de vijf notes en de vijf pagina's van het archief die er het meest op lijken."""
    import sqlite3

    import numpy as np

    from doublecheck.config import load_config
    from doublecheck.embedding import _load_model, normaliseer_voor_embedding

    versie = load_config(None).model_versions.text_embedding
    notes = json.loads((MAP / "notes.json").read_text(encoding="utf-8"))
    archief = json.loads((VECTOREN / "vectoren.json").read_text(encoding="utf-8"))
    if notes["model"] != versie or archief["model"] != versie:
        raise Weigering(f"vectoren van een ander model: notes {notes['model']}, archief {archief['model']}, config {versie}")
    xn, xa = np.load(MAP / "notes.npy"), np.load(VECTOREN / "vectoren.npy")
    pub = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))[-1]
    with sqlite3.connect(f"file:{pub}?mode=ro", uri=True) as c:
        pagina = {nr: (taal, eerste, bewering) for nr, taal, eerste, bewering in
                  c.execute("SELECT nummer, taal, eerste_datum, bewering FROM pagina")}
        redacties = {}
        for nr, red in c.execute("SELECT pagina, redactie FROM check_"):
            redacties.setdefault(nr, set()).add(red)
    maatstaf = json.loads(MAATSTAF.read_text(encoding="utf-8"))["checks"]
    model = _load_model(versie, "mps")
    q = model.encode([normaliseer_voor_embedding(c["titel"]) for c in maatstaf], normalize_embeddings=True)
    uit = []
    for c, v in zip(maatstaf, q):
        sn, sa = xn @ v, xa @ v
        top_n = [i for i in np.argsort(-sn) if notes["notes"][i]["datum"] <= c["datum"]][:TOP]
        top_a = [i for i in np.argsort(-sa) if archief["namen"][i] in pagina
                 and not any("AFP" in r for r in redacties.get(archief["namen"][i], ()))][:TOP]
        uit.append({"id": c["id"], "datum": c["datum"], "titel": c["titel"],
                    "notes": [{**notes["notes"][i], "score": round(float(sn[i]), 3)} for i in top_n],
                    "archief": [{"pagina": archief["namen"][i], "taal": pagina[archief["namen"][i]][0],
                                 "datum": pagina[archief["namen"][i]][1], "score": round(float(sa[i]), 3),
                                 "bewering": pagina[archief["namen"][i]][2][:200]} for i in top_a]})
    # vooruit: de notes in het Nederlands van de laatste zeven dagen van de export, per post
    laatste = max(n["datum"] for n in notes["notes"])
    begin = date.fromordinal(date.fromisoformat(laatste).toordinal() - 6).isoformat()
    per_post: dict[str, dict] = {}
    for i, n in enumerate(notes["notes"]):
        if n["datum"] >= begin:
            p = per_post.setdefault(n["post"], {"post": n["post"], "notes": [], "eerste": n["datum"], "i": i})
            p["notes"].append(n["note"])
            p["eerste"] = min(p["eerste"], n["datum"])
    vooruit = []
    for p in sorted(per_post.values(), key=lambda p: (-len(p["notes"]), p["post"])):
        sa = xa @ xn[p.pop("i")]
        beste = int(np.argmax(sa))
        vooruit.append({**p, "archief_beste": {"pagina": archief["namen"][beste], "score": round(float(sa[beste]), 3)}})
    (MAP / "koppelingen.json").write_text(json.dumps({"terug": uit, "vooruit": {"van": begin, "tot": laatste,
                                                                                   "posts": vooruit}},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(uit)} factchecks gekoppeld; vooruit {len(vooruit)} posts met een note van {begin} tot {laatste}")


def _teksten(export: Path, nummers: set[str]) -> dict[str, str]:  # pragma: no cover - bestanden
    """De tekst van deze notes, opnieuw uit de zip, alleen in het geheugen."""
    csv.field_size_limit(10_000_000)
    return {r["noteId"]: r["summary"] for r in _rijen(export, "notes") if r["noteId"] in nummers}


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="Eerst meten of een radar iets vindt (PLAN #37.0)")
    p.add_argument("stap", choices=["notes", "koppelen", "lezen", "tellen"])
    p.add_argument("--export", default=str(EXPORT))
    p.add_argument("--vanaf", default="2026-05-25")
    p.add_argument("--vooruit", action="store_true", help="lezen: de kandidaten van de laatste week")
    a = p.parse_args()
    try:
        if a.stap == "notes":
            _notes(Path(a.export), a.vanaf)
        elif a.stap == "koppelen":
            _koppelen()
        elif a.stap == "lezen":
            k = json.loads((MAP / "koppelingen.json").read_text(encoding="utf-8"))
            if a.vooruit:
                posts = k["vooruit"]["posts"]
                teksten = _teksten(Path(a.export), {n for p_ in posts for n in p_["notes"]})
                for p_ in posts:
                    print(f"\n== post {p_['post']} ({len(p_['notes'])} notes, eerste {p_['eerste']}; archief "
                          f"{p_['archief_beste']['pagina']} {p_['archief_beste']['score']})")
                    print("   " + " | ".join(teksten.get(n, "")[:300].replace("\n", " ") for n in p_["notes"][:2]))
            else:
                teksten = _teksten(Path(a.export), {n["note"] for c in k["terug"] for n in c["notes"]})
                for c in k["terug"]:
                    print(f"\n== {c['id']} {c['datum']} {c['titel']}")
                    for n in c["notes"]:
                        print(f"   note {n['note']} {n['datum']} {n['score']} {n['status'][:20]}: "
                              f"{teksten.get(n['note'], '')[:220].replace(chr(10), ' ')}")
                    for x in c["archief"]:
                        print(f"   archief {x['pagina']} {x['taal']} {x['datum']} {x['score']}: {x['bewering'][:160]}")
        else:
            labels = json.loads(LABELS.read_text(encoding="utf-8"))
            maatstaf = json.loads(MAATSTAF.read_text(encoding="utf-8"))["checks"]
            uitslag = tellen(maatstaf, labels["terug"], labels["vooruit"])
            MAP.mkdir(parents=True, exist_ok=True)
            (MAP / "uitslag.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps({k: v for k, v in uitslag.items() if k != "per_check"}, ensure_ascii=False, indent=1))
    except Weigering as e:
        raise SystemExit(f"geweigerd: {e}") from None


if __name__ == "__main__":  # pragma: no cover
    main()
