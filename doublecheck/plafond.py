"""Het plafond van screenshots (P5 van fase 0, PLAN #32.0c, B47).

In ronde 4 (§158) werd bekend nepnieuws als echt screenshot maar in 54% rood
met bewijs: het beeld bleef lokaal en het model kreeg alleen de OCR-tekst.
Wat valt er te halen als het model het beeld zelf ziet? Dezelfde 100
M4FC-screenshots, dezelfde vraag v4, hetzelfde geheugen, het web, de
herkansing en de feitenstap, nu met het beeld erbij. Via de Batch API, op
openbare beelden; het beeld gaat alleen in het geheugen naar de vraag en
wordt nergens bewaard (B35). In het product blijft het beeld lokaal (B43).
"""

from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as t
from doublecheck import verificatie as v

UIT = Path("data/plafond")
LABELS = Path("docs/steekproeven/32.0c-plafond.json")
BUDGET = 3.5  # PLAN #32.0c
EIS = 0.85
SCHATTING = {"machine": 0.03, "feit": 0.0015, "herkansing": 0.035}
BEWEZEN = ("bewijst", "bewijst via factcheck")
MAX_BYTES = 3_500_000  # ruim onder de grens van de API voor één beeld


class Weigering(RuntimeError):
    pass


def media_soort(data: bytes) -> str:
    """Het soort beeld uit de eerste bytes: de M4FC-bestanden hebben geen extensie."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def verzoek(stuk: dict, geheugen: list[dict], data: bytes, config) -> dict:
    """De vraag van ronde 4 (v4, geheugen en web), met het beeld vooraan; het model leest het beeld zelf."""
    s = {"id": stuk["id"], "soort": "tekst", "tekst": "", "datum": stuk.get("datum")}
    params = v.verzoek(s, geheugen, "a", [], "sonnet", config.berichtcontrole.vraag)["params"]
    tekst = v.vraagtekst({**s, "soort": "beeld"}, geheugen, config.berichtcontrole.vraag)
    params["messages"] = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": media_soort(data),
                                     "data": base64.b64encode(data).decode()}},
        {"type": "text", "text": tekst}]}]
    return params


def _tel(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict[str, str]) -> dict:
    d = Counter()
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if u is None:
            continue
        d["n"] += 1
        kleur = bc.kleur(u["stand"], u["oordeel"])
        d[kleur or "geen kleur"] += 1
        if kleur != "rood":
            continue
        if u["eigen_bewijs"]:
            d["rood met bewijs"] += 1
            d["rood met de eigen check"] += 1
        elif u["bronnen"]:
            if s["id"] not in labels:
                raise Weigering(f"{s['id']} heeft geen label in {LABELS.name}; eerst lezen")
            if labels[s["id"]] in BEWEZEN:
                d["rood met bewijs"] += 1
                d["rood met een andere bron, bewezen"] += 1
        else:
            d["rood zonder bron"] += 1
    velden = ("n", "rood", "rood met bewijs", "rood met de eigen check", "rood met een andere bron, bewezen", "groen",
              "geen kleur")
    return {**{k: 0 for k in velden}, **d}


def telling(stukken: list[dict], uitkomsten: dict[str, dict], labels: dict[str, str]) -> dict:
    """Rood met bewijs over de screenshots, en de eis van PLAN #32.0c. Weigert zolang een rood met een andere
    bron dan de eigen check niet gelezen is."""
    alles = _tel(stukken, uitkomsten, labels)
    return {"alles": alles,
            "eisen": {"minstens 85% rood met bewijs": alles["n"] > 0 and alles["rood met bewijs"] >= EIS * alles["n"]},
            "toetshelft": _tel([s for s in stukken if s.get("helft") == "toets"], uitkomsten, labels)}


# --- de CLI ---------------------------------------------------------------------------------------

def _beeld(pad: str) -> bytes:  # pragma: no cover - met Pillow
    """Het beeld zoals het naar de vraag gaat; te groot wordt kleiner gemaakt, alleen in het geheugen."""
    data = Path(pad).read_bytes()
    if len(data) <= MAX_BYTES:
        return data
    import io

    from PIL import Image

    beeld = Image.open(io.BytesIO(data)).convert("RGB")
    beeld.thumbnail((1568, 1568))
    buf = io.BytesIO()
    beeld.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    return {r["id"]: r["label"] for r in json.loads(LABELS.read_text(encoding="utf-8")).get("oordelen", [])}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    import anthropic

    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="Het plafond van screenshots (PLAN #32.0c)")
    parser.add_argument("stap", choices=("indienen", "herkansing", "ophalen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    config = load_config(None)
    laad_sleutel()
    client = anthropic.Anthropic()
    stukken = [s for s in t._jsonl(t.UIT / "set.jsonl") if s.get("vorm") == "screenshot"]
    per_id = {s["id"]: s for s in stukken}
    per_bid = {t.batch_id(s["id"]): s for s in stukken}
    batches = t._jsonl(UIT / "batches.jsonl")
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    tabel = bc.ijktabel(config)
    ingediend = {i for b in batches for i in b["ids"]}

    def uitgegeven() -> float:
        return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in batches)

    if args.stap in ("indienen", "herkansing"):
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            nog = [s for s in stukken if f"m-{t.batch_id(s['id'])}" not in ingediend][: args.proef or None]
            zinnen = bc.feitzinnen()
            for s in nog:
                b = t.batch_id(s["id"])
                verzoeken.append({"custom_id": f"m-{b}", "params": verzoek(s, s["geheugen"], _beeld(s["beeld"]), config)})
                geschat += SCHATTING["machine"]
                for k in ("A", "B") if s["kandidaten"] else ():
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{b}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        else:
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and f"h-{t.batch_id(r['id'])}" not in ingediend:
                    s = per_id[r["id"]]
                    verzoeken.append({"custom_id": f"h-{t.batch_id(s['id'])}", "params": bc.met_herkansing(
                        verzoek(s, s["geheugen"], _beeld(s["beeld"]), config), zin)})
                    geschat += SCHATTING["herkansing"]
        if not verzoeken:
            raise SystemExit("niets in te dienen")
        if uitgegeven() + geschat > BUDGET:
            raise Weigering(f"${uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        batch = client.messages.batches.create(requests=verzoeken)
        batches.append({"id": batch.id, "stap": args.stap, "schatting": round(geschat, 3),
                        "ids": [r["custom_id"] for r in verzoeken]})
        t._schrijf(UIT / "batches.jsonl", batches)
        print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    if args.stap == "ophalen":
        klaar = {(r["soort"], r["id"], r.get("sleutel")) for r in antwoorden}
        zinnen = bc.feitzinnen()
        for b in batches:
            if b.get("werkelijk") is not None or client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                msg = r.result.message
                kort, rest = r.custom_id.split("-", 1)
                if kort == "f":
                    stuk, sleutel = rest.rsplit("__", 1)
                    s = per_bid[stuk]
                    rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel, **bc.feitantwoord(
                        msg, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel, zinnen, config)[1])}
                else:
                    s = per_bid[rest]
                    rij = {"soort": "machine" if kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                           **bc.machineantwoord(msg, s["geheugen"])}
                rij["kosten"] = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
                werkelijk += rij["kosten"]
                if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                    with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
        t._schrijf(UIT / "batches.jsonl", batches)
        antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
        print(Counter(r["soort"] for r in antwoorden),
              f"herkansing nodig: {sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}",
              f"uitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    uitkomsten = {i: {**u, "eigen_bewijs": t._eigen_bewijs(per_id[i], u)}
                  for i, u in t.uitkomsten_van(stukken, antwoorden, tabel).items()}
    labels = _labels()
    if args.stap == "tellen":
        uit = telling(stukken, uitkomsten, labels)
        vroeger = {i: {**u, "eigen_bewijs": t._eigen_bewijs(per_id[i], u)} for i, u in t.uitkomsten_van(
            stukken, t._jsonl(t.UIT / "antwoorden.jsonl"), tabel).items()}
        uit["ronde 4, zonder beeld: rood met de eigen check"] = sum(
            1 for i, u in vroeger.items() if bc.kleur(u["stand"], u["oordeel"]) == "rood" and u["eigen_bewijs"])
        print(json.dumps(uit, ensure_ascii=False, indent=1), f"\nuitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    for s in stukken:
        u = uitkomsten.get(s["id"])
        if not u or bc.kleur(u["stand"], u["oordeel"]) != "rood" or u["eigen_bewijs"] or not u["bronnen"] \
                or s["id"] in labels:
            continue
        print(f"\n[{s['id']} · {s.get('helft')}] ROOD: bewijst, bewijst via factcheck, bewijst niet, set fout?"
              + ("" if s.get("helft") == "toets" else f"\n  OCR: {s['tekst'][:300]}")
              + f"\n  FACTIZ: {u['oordeel']}; {u.get('bewering')}\n  UITLEG: {u.get('uitleg')}")
        for b in u["bronnen"][:3]:
            print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:250]}")


if __name__ == "__main__":
    main()
