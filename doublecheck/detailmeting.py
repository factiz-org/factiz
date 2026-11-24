"""De meting van B48 (PLAN #32.3a): *klopt grotendeels, maar …* bij een echt verhaal
met één vals detail.

De detailvraag (`berichtcontrole.detailverzoek`, `detail-v1`) komt ná het oordeel,
alleen bij *klopt*. Ze verandert vraag v4 niet, dus de bestaande antwoorden van
P11, P8 en ronde 5 zijn te hergebruiken: alleen de detailvraag is nieuw. Daarbij
40 nieuwe verzonnen details uit ongebruikte Sheffield-artikelen, helemaal door
Factiz. Ontwikkeld op de ontwikkelhelft; de eisen gelden voor de toetshelft, de
40 nieuwe en de 100 echte artikelen van ronde 5 (W5).
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

UIT = Path("data/detail")
LABELS = Path("docs/steekproeven/32.3a-vals-detail.json")
BUDGET = 3.0  # PO 2026-10-28
VERSIE = "detail-v3"  # ontwikkeld op de ontwikkelhelft (2026-10-28): v1 passages te kort, v2 citeerde de verkeerde zin
KORT = "e"  # de eerste stap, gelijk in v2 en v3
ZOEK_KORT = "x"  # de zoekstap van v3 (v2 was "z", een eerdere v3 "y")
ZAAD = 3230
N_NIEUW = 40
SCHATTING = {"detail": 0.004, "zoek": 0.02, "factiz": 0.022, "feit": 0.0015, "vorm": 0.0013, "herkansing": 0.03, "sonnet": 0.004}
GEVANGEN = ("klopt grotendeels", "klopt niet")
VALS_SUBS = {"C", "B-feit"}
ECHT_SUBS = {"A", "F-waar"}


class Weigering(RuntimeError):
    pass


def _gewoon(tekst: str | None) -> str:
    return " ".join((tekst or "").lower().split())


def _label(labels: dict, sleutel: tuple) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def gevangen(rij: dict, labels: dict) -> bool:
    """Een verzonnen detail is gevangen bij *klopt niet* of rood, of bij *klopt grotendeels* met het verzonnen
    detail gemarkeerd. Is het verzonnen detail niet bekend, dan wordt de markering gelezen."""
    na = rij["na"]
    if na["oordeel"] == "klopt niet" or na["kleur"] == "rood":
        return True
    if na["oordeel"] != "klopt grotendeels":
        return False
    if not rij.get("nieuw"):
        return _label(labels, (rij["id"], "markering")) == "juist"
    nieuw = _gewoon(rij["nieuw"])
    return any(nieuw in _gewoon(c["woorden"]) or _gewoon(c["woorden"]) in nieuw for c in na["correcties"])


def _maar(rij: dict) -> bool:
    """Heeft de detailvraag het oordeel veranderd?"""
    return rij["voor"]["oordeel"] == "klopt" and rij["na"]["oordeel"] in GEVANGEN


def telling(rijen: list[dict], labels: dict) -> dict:
    """Per helft de verzonnen details (groen voor en na, gevangen) en de echte berichten (een *maar*, terecht of
    onterecht), en de drie eisen van PLAN #32.3a op de toetshelft."""
    uit = {helft: {"vals": Counter(), "echt": Counter()} for helft in ("ontwikkel", "toets")}
    w5_onterecht = 0
    for rij in rijen:
        d = uit[rij["helft"]][rij["soort"]]
        if rij["soort"] == "vals":
            if rij.get("set fout"):
                continue
            if rij["na"]["kleur"] == "groen" and _label(labels, (rij["id"], "groen")) == "set fout":
                continue
            d["n"] += 1
            d["groen voor"] += rij["voor"]["kleur"] == "groen"
            d["groen na"] += rij["na"]["kleur"] == "groen"
            d["klopt grotendeels"] += rij["na"]["oordeel"] == "klopt grotendeels"
            d["gevangen"] += gevangen(rij, labels)
        else:
            d["n"] += 1
            if _maar(rij):
                d["maar"] += 1
                onterecht = _label(labels, (rij["id"], "maar")) == "onterecht"
                d["onterechte maar"] += onterecht
                w5_onterecht += onterecht and rij["bron"] == "W5"
    for helft in uit.values():
        for soort, velden in (("vals", ("n", "groen voor", "groen na", "klopt grotendeels", "gevangen")),
                              ("echt", ("n", "maar", "onterechte maar"))):
            helft[soort] = {v: helft[soort][v] for v in velden}
    v = uit["toets"]["vals"]
    uit["eisen"] = {"verzonnen details: nooit groen": v["groen na"] == 0,
                    "verzonnen details: minstens 90% gevangen": v["n"] > 0 and v["gevangen"] >= 0.9 * v["n"],
                    "echte artikelen: hoogstens 1 van de 100 een onterechte maar": w5_onterecht <= 1}
    return uit


# --- de bronnen, de vragen en de CLI --------------------------------------------------------------

def _na(u: dict) -> dict:
    return {"oordeel": u["oordeel_na"], "stand": {"stand": u["stand"], "woorden": "", "laag": u["laag"]},
            "feit": u["feit"], "kleur": u["kleur"], "regels": u["regels"], "meting": None}


def bronnen(config) -> list[dict]:  # pragma: no cover - op de data van eerdere toetsen
    """Per bericht de uitkomst vóór de detailvraag en wat er nodig is om hem te stellen."""
    from doublecheck import tegenspeler as tg

    tabel = bc.ijktabel(config)
    uit = []

    def voeg_toe(naam, stukken, antwoorden, soort_van, nieuw_van, fout_van, helft_van=lambda s: s.get("helft")):
        for i, u in g.factiz_uitkomsten(stukken, antwoorden, tabel).items():
            s = next(x for x in stukken if x["id"] == i)
            soort = soort_van(s)
            if soort is None:
                continue
            uit.append({"id": i, "bron": naam, "soort": soort, "helft": helft_van(s), "tekst": s["tekst"],
                        "uitkomst": u, "nieuw": nieuw_van(s), "set fout": fout_van(s)})

    p11 = t._jsonl(g.UIT / "set.jsonl")
    p11_gemaakt = {x["id"]: x for x in t._jsonl(g.UIT / "gemaakt.jsonl")}
    p11_labels = g.lees_labels()
    voeg_toe("P11", p11, t._jsonl(g.UIT / "antwoorden.jsonl"),
             lambda s: "vals" if s["sub"] in VALS_SUBS else "echt" if s["sub"] in ECHT_SUBS else None,
             lambda s: (p11_gemaakt.get(s["id"]) or {}).get("nieuw"),
             lambda s: p11_labels.get((s["id"], "factiz", "groen")) == "set fout")
    p8 = [s for s in t._jsonl(tg.UIT / "set.jsonl") if s["deel"] == "C"]
    p8_gemaakt = {x["id"]: x for x in t._jsonl(tg.UIT / "gemaakt.jsonl")}
    p8_labels = {r["id"]: r["label"] for r in tg._labelbestand().get("oordelen", [])}
    voeg_toe("P8", p8, t._jsonl(tg.UIT / "antwoorden.jsonl"), lambda s: "vals",
             lambda s: (p8_gemaakt.get(s["id"]) or {}).get("nieuw"), lambda s: p8_labels.get(s["id"]) == "set fout")
    w5 = [s for s in t._jsonl(h.UIT / "set.jsonl") if s["deel"] == "W5"]
    voeg_toe("W5", w5, t._jsonl(h.UIT / "antwoorden.jsonl"), lambda s: "echt", lambda s: None, lambda s: False,
             lambda s: "toets")
    nieuw = t._jsonl(UIT / "set.jsonl")
    gemaakt = {x["id"]: x for x in t._jsonl(UIT / "gemaakt.jsonl")}
    voeg_toe("nieuw", nieuw, t._jsonl(UIT / "antwoorden.jsonl"), lambda s: "vals",
             lambda s: (gemaakt.get(s["id"]) or {}).get("nieuw"), lambda s: False, lambda s: "toets")
    return uit


def _sleutel(b: dict, kort: str = KORT) -> str:
    return f"{kort}-{b['bron']}-{t.batch_id(b['id'])}"


def nodig(b: dict) -> bool:
    return b["uitkomst"]["oordeel_na"] == "klopt" and bool(bc._passages(b["uitkomst"]["bronnen"]))


def zoeken_nodig(b: dict, eerste: dict, tabel: dict) -> bool:
    """De tweede stap: de eerste vraag gaf geen geldig detail, maar de notitie noemt er een."""
    u = b["uitkomst"]
    return bool(eerste.get("notitie")) and bc.met_detail(tabel, _na(u), b["tekst"], u["bronnen"], eerste["details"]) \
        == _na(u)


def rijen_van(config, alle: list[dict], antwoorden: dict[str, dict], zoek: dict[str, dict]) -> list[dict]:  # pragma: no cover
    tabel = bc.ijktabel(config)
    uit = []
    for b in alle:
        u = b["uitkomst"]
        voor = _na(u)
        if nodig(b):
            eerste = antwoorden.get(_sleutel(b))
            if eerste is None:
                continue  # de detailvraag staat nog uit
            na = bc.met_detail(tabel, voor, b["tekst"], u["bronnen"], eerste["details"])
            if zoeken_nodig(b, eerste, tabel):
                tweede = zoek.get(_sleutel(b, ZOEK_KORT))
                if tweede is None:
                    continue  # de zoekstap staat nog uit
                na = bc.met_detail(tabel, voor, b["tekst"], u["bronnen"], tweede["details"], tweede["passages"])
        else:
            na = voor
        uit.append({**{k: b[k] for k in ("id", "bron", "soort", "helft", "nieuw", "set fout")},
                    "voor": {"oordeel": voor["oordeel"], "kleur": voor["kleur"]},
                    "na": {"oordeel": na["oordeel"], "kleur": na["kleur"], "correcties": na.get("correcties", [])},
                    "tekst": b["tekst"], "uitleg": u.get("uitleg")})
    return uit


def _labels() -> dict:
    if not LABELS.exists():
        return {}
    return {(r["id"], r["wat"]): r["label"] for r in json.loads(LABELS.read_text(encoding="utf-8")).get("oordelen", [])}


def _afgewezen() -> set[str]:
    if not LABELS.exists():
        return set()
    return {r["id"] for r in json.loads(LABELS.read_text(encoding="utf-8")).get("set", [])}


def kies_nieuw(artikelen: list[dict], gebruikt: set[str], afgewezen: set[str], n: int = N_NIEUW) -> list[dict]:
    """Eerst de vaste volgorde, dan pas overslaan wat afgewezen is: zo neemt het volgende artikel de plek in en
    blijft de rest staan."""
    rijen = sorted((a for a in artikelen if a["id"] not in gebruikt), key=lambda a: a["id"])
    random.Random(ZAAD).shuffle(rijen)
    return [{"id": f"N:{a['id']}", "bron_id": a["id"], "bron": a["tekst"], "helft": "toets"}
            for a in rijen if a["id"] not in afgewezen][:n]


def main() -> None:  # pragma: no cover - CLI, met de database, het model en de Batch API
    import argparse

    import anthropic

    from doublecheck import tegenspeler as tg
    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="De meting van B48 (PLAN #32.3a)")
    parser.add_argument("stap", choices=("kiezen", "genereren", "set", "indienen", "herkansing", "vorm", "vragen", "zoeken",
                                         "ophalen", "lezen", "tellen"))
    parser.add_argument("sub", nargs="?", default="")
    parser.add_argument("--helft", default="", choices=("", "ontwikkel", "toets"), help="vragen: alleen deze helft")
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

    def haal_op(verwerk, genereren: bool = False) -> None:
        for b in batches:
            if b.get("werkelijk") is not None or (b["stap"] == "genereren") != genereren:
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

    if args.stap == "kiezen":
        gebruikt = {s.get("bron_id") for s in t._jsonl(g.UIT / "keuze.jsonl")} | \
                   {s.get("bron_id") for s in t._jsonl(tg.UIT / "keuze.jsonl")} | \
                   {r["id"] for r in tg._labelbestand().get("set", [])}
        keuze = kies_nieuw(g.pools()["artikelen"], gebruikt, _afgewezen())
        t._schrijf(UIT / "keuze.jsonl", keuze)
        print(len(keuze))
        return
    keuze = t._jsonl(UIT / "keuze.jsonl")
    gemaakt = {x["id"]: x for x in t._jsonl(UIT / "gemaakt.jsonl")}
    if args.stap == "genereren":
        if args.sub == "indienen":
            verzoeken = [g.haiku_verzoek(f"g-{t.batch_id(s['id'])}", g.DETAIL_VRAAG_2.format(tekst=s["bron"]),
                                         g._SCHEMA_2["C"], "sonnet") for s in keuze if s["id"] not in gemaakt]
            dien_in(verzoeken, len(verzoeken) * SCHATTING["sonnet"], "genereren")
        elif args.sub == "ophalen":
            per_bid = {t.batch_id(s["id"]): s for s in keuze}

            def verwerk(cid, msg):
                kosten = t.kosten_batch(bc.gebruik_uit(msg))
                if cid[2:] not in per_bid:
                    return kosten  # niet meer in de keuze (de verschoven volgorde van 2026-10-28)
                try:
                    rij = json.loads(g._tekst(msg))
                except json.JSONDecodeError:
                    rij = {}
                with (UIT / "gemaakt.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": per_bid[cid[2:]]["id"], **rij}, ensure_ascii=False) + "\n")
                return kosten

            haal_op(verwerk, genereren=True)
        else:
            for s in keuze:
                x = gemaakt.get(s["id"], {})
                vlag = "" if x and g.vervanging_klopt(s["bron"], x) else " VERVANGING-KLOPT-NIET"
                print(f"\n[{s['id']}]{vlag}\n  BRON: {s['bron'][:300]}\n  GEMAAKT: {x.get('bericht')}"
                      f"\n  {x.get('origineel')!r} → {x.get('nieuw')!r}")
        return
    if args.stap == "set":
        from doublecheck.storage import connect

        conn = connect("doublecheck.db")
        uit = []
        for s in keuze:
            x = gemaakt.get(s["id"])
            if not x or not g.vervanging_klopt(s["bron"], x):
                raise Weigering(f"{s['id']}: eerst genereren, of afwijzen in {LABELS.name}")
            bericht = bc.bericht_uit(x["bericht"], None, config.ocr)
            v = bc.voorbereiden(conn, config, bericht)
            uit.append({"id": s["id"], "bron_id": s["bron_id"], "helft": "toets", "tekst": v["tekst"],
                        "geheugen": v["geheugen"], "kandidaten": v["kandidaten"], "eigen": [], "datum": None})
        t._schrijf(UIT / "set.jsonl", uit)
        print(len(uit))
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
            zinnen = bc.feitzinnen()
            for s in stukken:
                b = t.batch_id(s["id"])
                if f"m-{b}" in ingediend:
                    continue
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
    alle = bronnen(config)
    details = {r["sleutel"]: r for r in t._jsonl(UIT / "details.jsonl")}
    zoek = {r["sleutel"]: r for r in t._jsonl(UIT / "zoek.jsonl")}
    if args.stap == "zoeken":
        verzoeken = [{"custom_id": _sleutel(b, ZOEK_KORT), "params": bc.zoekverzoek(
            b["tekst"], details[_sleutel(b)]["notitie"], VERSIE, config)}
            for b in alle if nodig(b) and _sleutel(b) in details and zoeken_nodig(b, details[_sleutel(b)], tabel)
            and _sleutel(b, ZOEK_KORT) not in ingediend]
        dien_in(verzoeken, len(verzoeken) * SCHATTING["zoek"], "zoeken")
        return
    if args.stap == "vragen":
        verzoeken = [{"custom_id": _sleutel(b), "params": bc.detailverzoek(b["tekst"], b["uitkomst"], VERSIE, config)}
                     for b in alle if nodig(b) and _sleutel(b) not in ingediend
                     and (not args.helft or b["helft"] == args.helft)]
        dien_in(verzoeken, len(verzoeken) * SCHATTING["detail"], "vragen")
        return
    if args.stap == "ophalen":
        klaar = {(r["soort"], r["id"], r.get("sleutel")) for r in antwoorden}
        zinnen = bc.feitzinnen()

        def verwerk(cid, msg):
            kort, rest = cid.split("-", 1)
            kosten = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
            if kort in ("d", "e"):
                tekst = g._tekst(msg)
                with (UIT / "details.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"sleutel": cid, "details": bc.lees_detail(tekst),
                                         "notitie": bc.lees_notitie(tekst), "kosten": kosten}, ensure_ascii=False) + "\n")
                return kosten
            if kort in ("z", "y", "x"):
                gevonden, passages = bc.lees_zoekdetail([b.model_dump() for b in msg.content])
                with (UIT / "zoek.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"sleutel": cid, "details": gevonden, "passages": passages, "kosten": kosten},
                                        ensure_ascii=False) + "\n")
                return kosten
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
            rij["kosten"] = kosten
            if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            return kosten

        haal_op(verwerk)
        print(Counter(r["soort"] for r in t._jsonl(UIT / "antwoorden.jsonl")),
              f"details: {len(t._jsonl(UIT / 'details.jsonl'))}", f"uitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    rijen = rijen_van(config, alle, details, zoek)
    labels = _labels()
    if args.stap == "tellen":
        uit = telling(rijen, labels)
        uit["per bron"] = {f"{b} {s}": dict(Counter(f"{r['voor']['oordeel']} → {r['na']['oordeel']}" for r in rijen
                                                    if r["bron"] == b and r["soort"] == s))
                           for b, s in (("P11", "vals"), ("P11", "echt"), ("P8", "vals"), ("W5", "echt"),
                                        ("nieuw", "vals"))}
        print(json.dumps(uit, ensure_ascii=False, indent=1), f"\nuitgegeven ${uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    for r in rijen:
        te_lezen = []
        if r["soort"] == "echt" and _maar(r) and (r["id"], "maar") not in labels:
            te_lezen.append("MAAR bij een echt bericht: terecht of onterecht?")
        if r["soort"] == "vals" and not r.get("set fout"):
            if r["na"]["kleur"] == "groen" and (r["id"], "groen") not in labels:
                te_lezen.append("GROEN bij een verzonnen detail: vals of set fout?")
            if r["na"]["oordeel"] == "klopt grotendeels" and not r.get("nieuw") and (r["id"], "markering") not in labels:
                te_lezen.append("MARKERING: juist of fout?")
        if te_lezen:
            print(f"\n[{r['id']} · {r['bron']} · {r['helft']}] {' | '.join(te_lezen)}"
                  + ("" if r["helft"] == "toets" and r["soort"] == "vals" else f"\n  BERICHT: {r['tekst'][:400]}")
                  + f"\n  VOOR: {r['voor']['oordeel']} · NA: {r['na']['oordeel']} · verzonnen: {r.get('nieuw')!r}")
            for c in r["na"]["correcties"]:
                print(f"  MAAR: {c['woorden']!r} → {c['juist']!r} ({c['url']}): {c['citaat'][:200]}")


if __name__ == "__main__":
    main()
