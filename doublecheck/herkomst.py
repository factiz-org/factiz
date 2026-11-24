"""De herkomstcontrole voor screenshots van artikelen, gemeten (PLAN #32.3e).

Een screenshot dat een site met band goed noemt (de lijst van #32.3c), krijgt één
zoekvraag van Sonnet, alleen op die site (`berichtcontrole.herkomstverzoek`):
gelijk, anders of niet gevonden. Gemeten op:
- de ontwikkelhelft van deel A en B van de gebruikerstoets (P11): hierop wordt de
  vraag afgemaakt;
- de toetshelft van deel A en B, één keer;
- een nieuwe set: 40 echte artikelen en 40 vervalsingen uit de Sheffield-set, met
  dezelfde maker als de gebruikerstoets (een andere krant, een verzonnen
  schrijver, één veranderd feit, een verzonnen kop; 10 van elk).
Screenshots bestaan alleen in het geheugen; wat bewaard wordt, is de gelezen tekst.

    python -m doublecheck.herkomst kiezen
    python -m doublecheck.herkomst genereren indienen|ophalen|lezen
    python -m doublecheck.hittewacht -- python -m doublecheck.herkomst set
    python -m doublecheck.herkomst indienen --set ontwikkel|toets [--proef N]|ophalen|live|lezen|tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as t
from doublecheck import bronnen as br
from doublecheck import gebruikerstoets as g
from doublecheck import verificatie as v
from doublecheck.snelantwoord import percentiel

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "herkomst"
LABELS = WORTEL / "docs" / "steekproeven" / "32.3e-herkomst.json"
BUDGET = 8.0  # PO 2026-10-28
VERSIE = "herkomst-v2"  # vastgelegd na de ontwikkelhelft, 2026-10-28
SUBS = ("A", "B-krant", "B-schrijver", "B-feit", "B-kop")
AANTAL = {"A": 40, "B-krant": 10, "B-schrijver": 10, "B-feit": 10, "B-kop": 10}
RESERVE = {"A": 5, "B-krant": 3, "B-schrijver": 3, "B-feit": 5, "B-kop": 5}
MAX_PER_SITE = 6
P11_BLOK = 220  # de blokken van de gebruikerstoets met hun reserve (`gebruikerstoets.kies`)
SCHATTING = 0.035  # per vraag in de batch; de zoekstap van de detailvraag kostte ~$0,027
LIVE = 10
KWIJT, NIET_GROEN, DETAIL_JUIST, P95 = 0.10, 0.70, 0.80, 10.0


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


def kies_nieuw(artikelen: list[dict], sites: dict[str, list], andere: list[str],
               afgewezen: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """De nieuwe set: alleen artikelen op een site met band goed, hoogstens zes per site, in de gegeven volgorde;
    per soort een vast blok met reserve, zoals in de gebruikerstoets. Wat bij het lezen is afgewezen, wordt
    vervangen door het volgende in hetzelfde blok."""
    per_site: Counter = Counter()
    goed = []
    for a in artikelen:
        b = br.beoordeel("https://" + g.domein(a["sleutel"][2:]), sites)
        if b["band"] != "goed" or b["soort"] == "platform" or per_site[b["site"]] >= MAX_PER_SITE:
            continue
        per_site[b["site"]] += 1
        goed.append(a)
    rng = random.Random(f"{g.ZAAD}-herkomst")
    uit, begin = [], 0
    for sub in SUBS:
        blok = goed[begin: begin + AANTAL[sub] + RESERVE[sub]]
        begin += AANTAL[sub] + RESERVE[sub]
        for rij in [a for a in blok if a["id"] not in afgewezen][: AANTAL[sub]]:
            eigen = g.domein(rij["sleutel"][2:])
            inhoud, herkomst = g.VERWACHT[sub]
            uit.append({"id": f"N-{sub}:{rij['id']}", "bron_id": rij["id"], "sleutel": rij["sleutel"],
                        "zaak": rij.get("zaak"), "deel": sub[0], "sub": sub, "tekst": rij["tekst"], "vorm": "nieuws",
                        "verwacht": {"inhoud": inhoud, "herkomst": herkomst},
                        "toon_domein": rng.choice([d for d in andere if d != eigen]) if sub == "B-krant" else eigen,
                        "schrijver": rng.choice(g.SCHRIJVERS) if sub == "B-schrijver" else None, "helft": "nieuw"})
    return uit


def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict, wachttijden: list[float] | None) -> dict:
    """De vier eisen van PLAN #32.3e, alleen waar de stap loopt. Elk verlies bij een echt artikel, elke gemiste
    vervalsing en elk *anders* in de inhoud bij een veranderd feit of een verzonnen kop moet gelezen zijn."""
    echt, vals, detail = {"n": 0, "rood": 0, "kwijt": 0}, {"n": 0, "niet groen": 0}, {"n": 0, "juist": 0}
    per_sub: dict[str, Counter] = {}
    loopt_niet: Counter = Counter()
    open_ = []
    for s in stukken:
        u = antwoorden.get(s["id"])
        if u is None:
            loopt_niet[s["sub"]] += 1
            continue
        weg = u["uitkomst"] in ("anders", "niet gevonden")
        per_sub.setdefault(s["sub"], Counter())[u["uitkomst"] or "geen"] += 1
        if s["verwacht"]["herkomst"] == "echt":
            echt["n"] += 1
            echt["rood"] += bool(u["rood"])
            echt["kwijt"] += weg
            if weg and (s["id"], "verlies") not in labels:
                open_.append(f"{s['id']} verlies")
            continue
        vals["n"] += 1
        vals["niet groen"] += weg
        if not weg and (s["id"], "gemist") not in labels:
            open_.append(f"{s['id']} gemist")
        if s["sub"] in ("B-feit", "B-kop") and u["uitkomst"] == "anders" and u["inhoud"]:
            label = labels.get((s["id"], "detail"))
            if label is None:
                open_.append(f"{s['id']} detail")
            else:
                detail["n"] += 1
                detail["juist"] += label == "juist"
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    p95 = percentiel(wachttijden, 0.95) if wachttijden else None
    eisen = {"geen echt artikel rood": echt["rood"] == 0,
             "hoogstens 10% van de echte artikelen kwijt": echt["n"] > 0 and echt["kwijt"] <= KWIJT * echt["n"],
             "minstens 70% van de vervalsingen niet groen": vals["n"] > 0 and vals["niet groen"] >= NIET_GROEN * vals["n"],
             "het veranderde detail juist in minstens 80%": detail["n"] > 0
             and detail["juist"] >= DETAIL_JUIST * detail["n"],
             "p95 hoogstens 10 s": p95 is not None and p95 <= P95}
    return {"echt": echt, "vals": vals, "detail": detail, "per soort": {k: dict(v) for k, v in per_sub.items()},
            "loopt niet": dict(loopt_niet), "p95": p95, "eisen": eisen}


# --- de bestanden en de CLI ----------------------------------------------------------------------

def _labelbestand() -> dict:
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def afgewezen_bij_lezen() -> set[str]:
    return {r["id"] for r in _labelbestand().get("set", []) if r["label"] == "afgewezen"}


def lees_labels() -> dict:
    return {(r["id"], r["wat"]): r["label"] for r in _labelbestand().get("oordelen", [])}


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in t._jsonl(UIT / "batches.jsonl"))


def p11(helft: str) -> list[dict]:  # pragma: no cover - op de set van de gebruikerstoets
    return [s for s in t._jsonl(g.UIT / "set.jsonl") if s["deel"] in ("A", "B") and s["helft"] == helft]


def stukken(welke: str) -> list[dict]:  # pragma: no cover - op de bestanden
    if welke == "ontwikkel":
        return p11("ontwikkel")
    return p11("toets") + t._jsonl(UIT / "set.jsonl")


def antwoorden_van(versie: str) -> dict[str, dict]:  # pragma: no cover - een bestand
    """Per bericht het gelezen antwoord van deze versie, in de vorm van `telling`."""
    return {r["id"]: {**r["uitkomst"], "inhoud": bool(r["uitkomst"]["geldig"])}
            for r in t._jsonl(UIT / "antwoorden.jsonl") if r["versie"] == versie}


def _maak_set(keuze: list[dict], gemaakt: dict[str, dict]) -> list[dict]:  # pragma: no cover - Pillow en OCR
    import io

    from doublecheck.config import load_config

    config = load_config(None)
    uit = []
    for i, s in enumerate(keuze):
        b = g.bericht_van(s, gemaakt)
        buf = io.BytesIO()
        g.teken_nieuws(s["toon_domein"], b["kop"], b["lead"], s["schrijver"]).save(buf, format="PNG")
        tekst = bc.bericht_uit(None, buf.getvalue(), config.ocr)
        uit.append({k: s[k] for k in ("id", "deel", "sub", "vorm", "verwacht", "helft", "toon_domein", "schrijver",
                                      "sleutel", "zaak")} | {"tekst": tekst})
        print(f"\r{i + 1}/{len(keuze)}", end="", flush=True)
    print()
    t._schrijf(UIT / "set.jsonl", uit)
    return uit


def _dien_in(client, verzoeken: list[dict], geschat: float, stap: str) -> None:  # pragma: no cover - Batch API
    if not verzoeken:
        raise SystemExit("niets in te dienen")
    if al_uitgegeven() + geschat > BUDGET:
        raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
    batch = client.messages.batches.create(requests=verzoeken)
    with (UIT / "batches.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": batch.id, "stap": stap, "schatting": round(geschat, 3),
                             "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
    print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


def _ophalen(client, verwerk, genereren: bool) -> None:  # pragma: no cover - Batch API
    """Haalt de afgelopen batches van één soort op: de vervalsingen of de herkomstvragen."""
    alle = t._jsonl(UIT / "batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None or b["stap"] == "live" or (b["stap"] == "genereren") != genereren:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog")
            continue
        werkelijk = 0.0
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                print(f"{r.custom_id}: {r.result.type}")
                continue
            werkelijk += verwerk(r.custom_id, r.result.message, b["stap"])
        b["werkelijk"] = round(werkelijk, 4)
    t._schrijf(UIT / "batches.jsonl", alle)


def _rij(s: dict, site: str, versie: str, msg, seconden: float | None = None) -> dict:  # pragma: no cover - API
    blokken = [b.model_dump() for b in msg.content]
    gelezen = bc.lees_herkomst(blokken)
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    return {"id": s["id"], "versie": versie, "site": site, "gelezen": gelezen,
            "uitkomst": bc.herkomst_uitkomst(s["tekst"], gelezen), "antwoord": tekst[-2500:],
            "zoekvragen": v.zoekopdrachten(blokken), "seconden": seconden}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse
    import time

    import anthropic

    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="De herkomstcontrole, gemeten (PLAN #32.3e)")
    parser.add_argument("stap", choices=("kiezen", "toegang", "genereren", "set", "indienen", "ophalen", "live",
                                         "lezen", "tellen"))
    parser.add_argument("sub", nargs="?", default="", help="genereren: indienen, ophalen of lezen")
    parser.add_argument("--set", dest="welke", choices=("ontwikkel", "toets"), default="ontwikkel")
    parser.add_argument("--proef", type=int, default=0)
    parser.add_argument("--versie", default=VERSIE)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    config = load_config(None)
    lijst = json.loads(br.BESTAND.read_text(encoding="utf-8"))

    if args.stap == "kiezen":
        artikelen = g._schud(g.pools()["artikelen"], "artikelen")
        andere = sorted({g.domein(a["sleutel"][2:]) for a in artikelen})
        keuze = kies_nieuw(artikelen[P11_BLOK:], lijst["sites"], andere, afgewezen_bij_lezen())
        t._schrijf(UIT / "keuze.jsonl", keuze)
        print(Counter(s["sub"] for s in keuze), Counter(g.domein(s["sleutel"][2:]) for s in keuze).most_common(8))
        return
    laad_sleutel()
    client = anthropic.Anthropic()
    keuze = t._jsonl(UIT / "keuze.jsonl")
    if args.stap == "toegang":
        # Welke sites de zoekfunctie van Anthropic niet toelaat: een vraag met `allowed_domains` op zo'n site
        # weigert meteen (400). Eén korte vraag per site, zonder te zoeken.
        sites = sorted({site for s in stukken("ontwikkel") + stukken("toets") + keuze
                        if (site := bc.herkomst_site(s["tekst"], lijst["sites"], geblokkeerd=frozenset()))}
                       | {br.beoordeel("https://" + d, lijst["sites"])["site"] for d in g.NIEUWS})
        dicht, kosten_ = [], 0.0
        for site in sites:
            try:
                msg = client.messages.create(model=config.berichtcontrole.model_id, max_tokens=5,
                                             messages=[{"role": "user", "content": "Reply with OK only. Do not search."}],
                                             tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1,
                                                     "allowed_domains": [site]}])
                kosten_ += bc.kosten(bc.gebruik_uit(msg))
            except anthropic.BadRequestError as fout:
                if "not accessible" not in str(fout):
                    raise
                dicht.append(site)
        (UIT / "geen-toegang.json").write_text(json.dumps({"datum": time.strftime("%Y-%m-%d"), "getest": sites,
                                                           "geen toegang": dicht}, indent=1), encoding="utf-8")
        with (UIT / "batches.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "toegang", "stap": "live", "schatting": 0.0, "ids": [],
                                 "werkelijk": round(kosten_, 4)}) + "\n")
        print(f"{len(dicht)} van de {len(sites)} sites zonder toegang: {dicht}; ${kosten_:.3f}")
        return
    if args.stap == "genereren":
        if args.sub == "indienen":
            al = {x["id"] for x in t._jsonl(UIT / "gemaakt.jsonl")}
            verzoeken = [g.haiku_verzoek(f"g-{t.batch_id(s['id'])}", g._VRAAG_2[s["sub"]].format(tekst=s["tekst"]),
                                         g._SCHEMA_2[s["sub"]], "sonnet") if s["sub"] in g._VRAAG_2 else
                         g.haiku_verzoek(f"g-{t.batch_id(s['id'])}", g._VRAAG[s["sub"]].format(tekst=s["tekst"]),
                                         g._SCHEMA[s["sub"]]) for s in keuze if s["sub"] in g._VRAAG and s["id"] not in al]
            _dien_in(client, verzoeken, len(verzoeken) * g.SCHATTING["haiku"] * 10, "genereren")
        elif args.sub == "ophalen":
            per_bid = {t.batch_id(s["id"]): s["id"] for s in keuze}

            def verwerk(cid, msg, stap):
                try:
                    gemaakt_ = json.loads(g._tekst(msg))
                except json.JSONDecodeError:
                    print(f"{cid}: geen geldige JSON; opnieuw genereren")
                    return t.kosten_batch(bc.gebruik_uit(msg)) / 10
                with (UIT / "gemaakt.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": per_bid[cid[2:]], **gemaakt_}, ensure_ascii=False) + "\n")
                return t.kosten_batch(bc.gebruik_uit(msg)) / 10

            _ophalen(client, verwerk, True)
        else:
            per_id = {s["id"]: s for s in keuze}
            for x in t._jsonl(UIT / "gemaakt.jsonl"):
                s = per_id.get(x["id"])
                if not s:
                    continue
                vlag = " VERVANGING-KLOPT-NIET" if "origineel" in x and not g.vervanging_klopt(s["tekst"], x) else ""
                print(f"\n[{x['id']}]{vlag} ORIGINEEL: {s['tekst'][:500]}\n  GEMAAKT: {json.dumps(x, ensure_ascii=False)}")
        return
    if args.stap == "set":
        gemaakt = {x["id"]: x for x in t._jsonl(UIT / "gemaakt.jsonl")}
        if any(s["sub"] in g._VRAAG and s["id"] not in gemaakt for s in keuze):
            raise Weigering("eerst genereren en ophalen")
        _maak_set(keuze, gemaakt)
        return
    rijen = stukken(args.welke)
    per_bid = {t.batch_id(s["id"]): s for s in rijen}
    code = "h" + args.versie.rsplit("-v", 1)[1]
    if args.stap == "indienen":
        gevraagd = {r["id"] for r in t._jsonl(UIT / "antwoorden.jsonl") if r["versie"] == args.versie}
        ingediend = {i for b in t._jsonl(UIT / "batches.jsonl") for i in b["ids"]}
        verzoeken = []
        for s in rijen:
            site = bc.herkomst_site(s["tekst"], lijst["sites"])
            cid = f"{code}-{t.batch_id(s['id'])}"
            if site and s["id"] not in gevraagd and cid not in ingediend:
                verzoeken.append({"custom_id": cid, "params": bc.herkomstverzoek(s["tekst"], site, args.versie, config)})
        if args.proef:
            verzoeken = verzoeken[: args.proef]
        _dien_in(client, verzoeken, len(verzoeken) * SCHATTING, f"{args.welke} {args.versie}")
        return
    if args.stap == "ophalen":
        per_bid_alle = {t.batch_id(s["id"]): s for s in stukken("ontwikkel") + stukken("toets")}

        def verwerk(cid, msg, stap):
            versie = stap.split(" ", 1)[1]
            s = per_bid_alle[cid.split("-", 1)[1]]
            rij = _rij(s, bc.herkomst_site(s["tekst"], lijst["sites"]), versie, msg)
            with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            return t.kosten_batch(bc.gebruik_uit(msg))

        _ophalen(client, verwerk, False)
        print(Counter((r["versie"], r["uitkomst"]["uitkomst"]) for r in t._jsonl(UIT / "antwoorden.jsonl")))
        return
    if args.stap == "live":
        kandidaten = [s for s in sorted(rijen, key=lambda s: s["id"]) if bc.herkomst_site(s["tekst"], lijst["sites"])]
        stap = max(1, len(kandidaten) // LIVE)
        live = []
        for s in kandidaten[::stap][:LIVE]:
            site = bc.herkomst_site(s["tekst"], lijst["sites"])
            begin = time.perf_counter()
            msg = client.messages.create(**bc.herkomstverzoek(s["tekst"], site, args.versie, config))
            sec = time.perf_counter() - begin
            live.append({**_rij(s, site, args.versie, msg, round(sec, 2)), "kosten": bc.kosten(bc.gebruik_uit(msg))})
            print(f"{s['id']}: {sec:.1f} s, {live[-1]['gelezen']['uitkomst']}")
        t._schrijf(UIT / f"live-{args.versie}.jsonl", live)
        with (UIT / "batches.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "live", "stap": "live", "schatting": 0.0, "ids": [],
                                 "werkelijk": round(sum(r["kosten"] for r in live), 4)}) + "\n")
        print(f"p95 {percentiel([r['seconden'] for r in live], .95):.1f} s; ${sum(r['kosten'] for r in live):.2f}")
        return
    antwoorden = antwoorden_van(args.versie)
    labels = lees_labels()
    if args.stap == "lezen":
        ruw = {r["id"]: r for r in t._jsonl(UIT / "antwoorden.jsonl") if r["versie"] == args.versie}
        for s in rijen:
            u = antwoorden.get(s["id"])
            if u is None:
                continue
            weg = u["uitkomst"] in ("anders", "niet gevonden")
            wat = ("verlies" if weg else None) if s["verwacht"]["herkomst"] == "echt" else \
                ("detail" if s["sub"] in ("B-feit", "B-kop") and u["uitkomst"] == "anders" and u["inhoud"]
                 else None if weg else "gemist")
            if wat and (s["id"], wat) not in labels:
                r = ruw[s["id"]]
                print(f"\n=== {s['id']} [{s['sub']}] {wat}: {u['uitkomst']} op {r['site']} rood={u['rood']}\n"
                      f"SCREENSHOT: {s['tekst'][:400]}\nECHT: {s.get('sleutel')}\n"
                      f"VERSCHILLEN: {r['gelezen']['verschillen']}\nANTWOORD: {r['antwoord'][-900:]}")
        return
    live = t._jsonl(UIT / f"live-{args.versie}.jsonl")
    uit = telling(rijen, antwoorden, labels, [r["seconden"] for r in live] if live else None)
    uit["kosten"] = round(al_uitgegeven(), 2)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
