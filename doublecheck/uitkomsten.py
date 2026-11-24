"""De lezer met alle uitkomsten (`lezer-v6`), gemeten op gewone tekst, met de bewaking (PLAN #32.31).

Zoals het product: het gemaskeerde bericht, kring 1, één zoekvraag bij Brave, de 5 checks uit de database,
`zoekcontrole.leesverzoek` en `zoekcontrole.na_lezen`. Alleen Sonnet gaat via de Batch API (offline, openbare data);
de zoekresultaten blijven in het geheugen tot het antwoord er is, dus per stuk van 100 berichten zoeken, indienen,
wachten en afmaken in één proces.
- G: 100 echte tiplineberichten zonder bewering en 25 met, volgens de annotatoren (Kazemi e.a. 2021), niet uit ronde 6;
- G-ontwikkel: 20 andere, zonder batch door `zoekcontrole.controleer`; alleen hierop wordt de vraag bijgesteld;
- W: de 300 ware berichten van ronde 4 (kring 1 aan), zoals §206;
- O': de 100 verse onware berichten van §182: kring 1 uit, zonder IFCN-factcheckers, de eigen claim verborgen;
- D: de 40 verzonnen details van §166 (kring 1 aan).
Elk rood en oranje bij G en W, elk groen bij O' en D en elke *klopt grotendeels* bij W krijgt een label in
`docs/steekproeven/32.31-uitkomsten.json`.

De tweede ronde (`--lezer lezer-v7`, PLAN #32.32): W2, 200 artikelen van Wikinews (2010 tot en met 2024); G2, 100
tiplineberichten zonder bewering waarover de annotatoren het eens zijn; O' en D zoals hierboven; S-bron, 20 koppen van
satiresites met de naam ervoor; S-los, 25 beweringen die een factchecker satire noemde, zoals O' (onbekend). De
ontwikkelset: 12 ware berichten van W. Labels in `docs/steekproeven/32.32-uitkomsten-v7.json`.

    python -m doublecheck.uitkomsten set [--lezer lezer-v7]
    python -m doublecheck.hittewacht -- python -m doublecheck.uitkomsten ontwikkel [--lezer lezer-v7]
    python -m doublecheck.hittewacht -- python -m doublecheck.uitkomsten draaien [--proef 5] [--lezer lezer-v7]
    python -m doublecheck.uitkomsten lezen|tellen [--lezer lezer-v7]
"""

from __future__ import annotations

import hashlib
import html
import json
import random
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "uitkomsten"
LABELS = WORTEL / "docs" / "steekproeven" / "32.31-uitkomsten.json"
TIPLINES = WORTEL / "data" / "extern" / "meedan-tiplines" / "claim_detection_dataset.csv"
LEZER = "lezer-v6"
BUDGET = 6.0  # PO 2026-11-03: "draai binnen $6", voor elke ronde
SCHATTING = 0.011  # per bericht na kring 1: Brave $0,005 en Sonnet in de batch ~$0,006 (§207: $0,0108)
GRENS_BATCH = 20 * 60  # PO 2026-11-03: na 20 minuten annuleren; één vraag hield een batch van 30 1 uur 40 open
HERKANSINGEN = 2  # wat dan nog openstaat, gaat hoogstens twee keer opnieuw
N_GEEN, N_WEL, N_ONTWIKKEL, ZAAD, STUK = 100, 25, 10, 32311, 100  # vooraf vastgelegd in PLAN #32.31
N_W2, N_G2, N_S_BRON, N_S_LOS, ZAAD_2, LEAD = 200, 100, 20, 25, 32321, 350  # vooraf vastgelegd in PLAN #32.32
JAREN_W2 = ("2010", "2024")
N_PER_SITE = 10  # 2026-11-03: Waterford Whispers News sluit de feed uit in robots.txt, dus 10 van elk van de andere twee
# satiresites waarvan robots.txt ophalen toelaat en AI niet uitsluit (2026-11-03); The Onion sluit `anthropic-ai` uit
SATIRE = {"The Beaverton": "https://www.thebeaverton.com/feed/",
          "Waterford Whispers News": "https://waterfordwhispersnews.com/feed/",
          "The Hard Times": "https://thehardtimes.net/feed/"}
RONDES = {"lezer-v6": {"lezer": "lezer-v6", "map": UIT, "labels": LABELS, "sets": ("G", "W", "O'", "D"), "ontwikkel": "G-ontwikkel"},
          "lezer-v7": {"lezer": "lezer-v7", "map": UIT / "lezer-v7", "labels": WORTEL / "docs" / "steekproeven" / "32.32-uitkomsten-v7.json",
                       "sets": ("W2", "O'", "G2", "D", "S-los", "S-bron"), "ontwikkel": "ontwikkel"}}
SETS = RONDES[LEZER]["sets"]
ONBEKEND = ("O'", "S-los")  # kring 1 uit, zonder IFCN-factcheckers, de eigen claim verborgen
ALARM_SETS, GROEN_SETS, MAAR_SETS = ("G", "G2", "W", "W2"), ("O'", "D", "S-los", "S-bron"), ("W", "W2")
ALARM = ("rood", "oranje")
LABELWAARDEN = ("vals", "terecht", "set fout")


class Weigering(Exception):
    """Tellen kan niet: iets dat telt heeft geen label, of de vraag is niet overal dezelfde."""


def vingerafdruk(lezer: str) -> str:
    """De vraag, het systeem en het schema van een lezer samen; verandert er iets, dan verandert dit."""
    d = zc.LEZERS[lezer]
    inhoud = d["systeem"] + d["vraag"] + json.dumps(d["schema"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(inhoud.encode("utf-8")).hexdigest()[:12]


def kies_g(rijen: list[dict], uitgesloten: set[int], n_geen: int = N_GEEN, n_wel: int = N_WEL,
           n_ontwikkel: int = N_ONTWIKKEL, zaad: int = ZAAD, eenstemmig: bool = False,
           naam: str = "G") -> tuple[list[dict], list[dict]]:
    """De gewone teksten: Engels, sociale media, een duidelijke meerderheid van de annotatoren, niet in `uitgesloten`
    (ronde 6, en in de tweede ronde de eerste), elk bericht één keer (de eerste in het bestand). `eenstemmig` (#32.32):
    alleen waar de drie annotatoren het eens zijn. Vast zaad; de volgorde van de invoer telt niet. Eerst de toets
    (`n_geen` zonder bewering, `n_wel` met), daarna de ontwikkelset (`n_ontwikkel` van elk)."""
    gezien, per_label = set(), {"No": [], "Yes": []}
    for r in sorted(rijen, key=lambda r: r["nr"]):
        sleutel = " ".join(r["text"].lower().split())
        stemmen = {r["annotator1"], r["annotator2"], r["annotator3"]}
        if (r["language"] != "en" or r["source"] != "social media" or r["majority_label"] not in per_label
                or r["nr"] in uitgesloten or sleutel in gezien or (eenstemmig and len(stemmen) != 1)):
            continue
        gezien.add(sleutel)
        per_label[r["majority_label"]].append(r)
    rng = random.Random(zaad)
    for lijst in per_label.values():
        rng.shuffle(lijst)

    def stuk(r: dict, set_: str) -> dict:
        stemmen = {r["annotator1"], r["annotator2"], r["annotator3"]}
        return {"id": f"G:t-{r['nr']:05d}", "set": set_, "tekst": r["text"], "datum": "2019–2021 (exact date unknown)",
                "label": "geen bewering" if r["majority_label"] == "No" else "bewering", "eenstemmig": len(stemmen) == 1}

    geen, wel = per_label["No"], per_label["Yes"]
    toets = [stuk(r, naam) for r in geen[:n_geen] + wel[:n_wel]]
    ontwikkel = [stuk(r, "G-ontwikkel") for r in geen[n_geen:n_geen + n_ontwikkel] + wel[n_wel:n_wel + n_ontwikkel]]
    return toets, ontwikkel


def _zinnen(tekst: str, n: int, grens: int) -> str:
    """De eerste `n` zinnen, zolang ze samen binnen `grens` tekens blijven; de eerste altijd."""
    uit = ""
    for zin in re.split(r"(?<=[.!?])\s+", " ".join(tekst.split())):
        if uit and (len(uit) + 1 + len(zin) > grens or uit.count(". ") + 1 >= n):
            break
        uit = f"{uit} {zin}".strip()
    return uit[:grens]


def kies_w2(rijen: list[dict], n: int = N_W2, zaad: int = ZAAD_2) -> list[dict]:
    """Vers waar nieuws (#32.32): Engelse Wikinews-artikelen uit `JAREN_W2`, met een herkenbaar begin van de tekst, geen
    interview of korte berichten; de kop en de eerste twee zinnen, met de datum van het artikel. Vast zaad."""
    kandidaten = sorted((r for r in rijen if JAREN_W2[0] <= (r.get("datum") or "")[:4] <= JAREN_W2[1]
                         and "Writing an article " in r["tekst"] and not r["titel"].startswith("Wikinews")),
                        key=lambda r: r["sleutel"])
    uit = []
    for r in random.Random(zaad).sample(kandidaten, min(n, len(kandidaten))):
        lead = _zinnen(r["tekst"].split("Writing an article ", 1)[1], 2, LEAD)
        uit.append({"id": f"W2:{r['sleutel']}", "set": "W2", "bron": r["sleutel"], "titel": r["titel"],
                    "tekst": f"{r['titel']}\n{lead}", "datum": r["datum"], "url": r["url"]})
    return uit


def koppen_uit_feed(xml: str, naam: str) -> list[dict]:
    """Satire met de bron erbij (#32.32): per bericht in de feed de naam van de site, de kop en de eerste zin van de
    inleiding, zoals een screenshot met de bron."""
    from email.utils import parsedate_to_datetime
    from xml.etree import ElementTree

    uit = []
    for item in ElementTree.fromstring(xml).iter("item"):
        titel = " ".join(html.unescape(item.findtext("title") or "").split())
        inleiding = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        link = (item.findtext("link") or "").strip()
        datum = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat() if item.findtext("pubDate") else None
        uit.append({"id": f"S-bron:{link}", "set": "S-bron", "site": naam, "url": link, "datum": datum,
                    "tekst": f"{naam}\n{titel}\n{_zinnen(inleiding, 1, 250)}".strip()})
    return uit


_OMSCHRIJVING = re.compile(r"\s*(?:a |an )?(?:\w+ )?(?:post|video|photo|image|picture|screenshot)s?\b", re.IGNORECASE)


def kies_s_los(rijen: list[tuple[str, str, str]], n: int = N_S_LOS, zaad: int = ZAAD_2) -> list[dict]:
    """Losgeknipte satire (#32.32): beweringen die een factchecker satire noemde (claim, tekst, datum), zonder
    omschrijvingen van een bericht ("post on Facebook claiming ..."). Vast zaad."""
    kandidaten = sorted((c, " ".join(t.split()), d) for c, t, d in rijen if not _OMSCHRIJVING.match(t))
    return [{"id": f"S:{c}", "set": "S-los", "claim": c, "tekst": t, "datum": d}
            for c, t, d in random.Random(zaad).sample(kandidaten, min(n, len(kandidaten)))]


def voorbereiden(s: dict, config, zoek, snel, sites: dict, checks_voor, beeld=None) -> dict:
    """Eén bericht tot aan de vraag aan de lezer, met de functies van `/check`. Bij O' en S-los geen kring 1, de
    resultaten zonder IFCN-factcheckers en de eigen claim verborgen in de database. Geeft het antwoord van kring 1
    (`rij`), of het verzoek met de resultaten en de checks, die in het geheugen blijven."""
    from doublecheck import tekstlezer as tl

    onbekend = s["set"] in ONBEKEND
    uit = snel(s["tekst"]) if config.berichtcontrole.kring1 and not onbekend else None
    if uit is not None:
        return {"route": "database", "rij": _rij(s, zc.uit_kring1(uit, s["tekst"], {}), 0.0,
                                                 config.berichtcontrole.lezer)}
    antwoord = zoek(zc.zoekvraag(s["tekst"]))
    resultaten = zc.resultaten_uit(tl.zonder_factcheckers(antwoord, sites) if onbekend else antwoord, sites)
    checks = checks_voor(s["tekst"], frozenset(s.get("verborgen") or ()))
    # B55 (#32.36): `beeld()` geeft het zwartgemaakte beeld, het aantal zwarte vakken en de tijd; pas na kring 1
    voor_model, extra = None, {}
    if beeld is not None and config.berichtcontrole.beeld:
        voor_model, n, seconden = beeld()
        extra = {"zwart": n, "zwart_s": round(seconden, 2)}
    return {"route": "zoeken", "resultaten": resultaten, "checks": checks, "beeld_gezien": voor_model is not None,
            **extra, "verzoek": zc.leesverzoek(s["tekst"], resultaten, s.get("datum"), config, voor_model, checks)}


def _rij(s: dict, uit: dict, kosten: float, lezer: str = LEZER) -> dict:
    """Wat bewaard wordt: de uitkomst, en van de genoemde zoekresultaten alleen adres, site, titel, band en rol."""
    bronnen = [{k: b.get(k) for k in ("url", "site", "titel", "band", "soort", "rol", "redactie", "oordeel")
                if b.get(k) is not None} for b in uit["bronnen"]]
    correctie = {k: v for k, v in (uit.get("correctie") or {}).items()} or None
    return {"id": s["id"], "set": s["set"], "route": uit["route"], "oordeel": uit["oordeel"], "kleur": uit["kleur"],
            "uitkomst": uit["uitkomst"], "vorm": uit.get("vorm"), "kleur_bewering": uit.get("kleur_bewering"),
            "over_beeld": uit.get("over_beeld"), "uitleg": uit.get("uitleg"), "correctie": correctie,
            "bronnen": bronnen, "label": s.get("label"), "vraag": vingerafdruk(lezer), "kosten": round(kosten, 5)}


def afmaken(s: dict, voor: dict, msg, config) -> dict:
    """Het antwoord uit de batch door `na_lezen`, zoals `controleer` het doet, tegen de batchprijs plus de
    zoekvraag."""
    from doublecheck import berichtcontrole as bc
    from doublecheck.betatoets import kosten_batch

    antwoord = zc.lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
    na = zc.na_lezen(antwoord, s["tekst"], voor["resultaten"], voor["checks"], config.berichtcontrole.lezer,
                     voor.get("beeld_gezien", False))
    rij = _rij(s, {"route": "zoeken", **na}, kosten_batch(bc.gebruik_uit(msg)) + zc.ZOEKPRIJS,
               config.berichtcontrole.lezer)
    return {**rij, **{k: voor[k] for k in ("zwart", "zwart_s") if k in voor}}


def _moet_lezen(r: dict) -> bool:
    return ((r["set"] in ALARM_SETS and r["kleur"] in ALARM) or (r["set"] in GROEN_SETS and r["kleur"] == "groen")
            or (r["set"] in MAAR_SETS and r["uitkomst"] == "klopt grotendeels"))


def telling(rijen: list[dict], labels: dict[str, str], ronde: str = LEZER) -> dict:
    """Per set de uitkomsten en de kleuren, en de eisen van PLAN #32.31 (`lezer-v6`) of #32.32 (`lezer-v7`). Een
    rood of oranje bij een gewone tekst telt altijd tegen, wat het label ook is. Weigert zolang iets dat telt geen
    label heeft, of als de antwoorden niet op één vraag rusten."""
    if len({r["vraag"] for r in rijen}) > 1:
        raise Weigering(f"de antwoorden rusten op meer dan één vraag: {sorted({r['vraag'] for r in rijen})}")
    open_ = sorted(r["id"] for r in rijen if _moet_lezen(r) and r["id"] not in labels)
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {RONDES[ronde]['labels'].name}, bijvoorbeeld {open_[0]}")
    uit: dict = {}
    for r in rijen:
        naam = f"{r['set']} ({r['label']})" if r["set"] in ("G", "G2") else r["set"]
        d = uit.setdefault(naam, Counter())
        d["n"] += 1
        d["kleur " + (r["kleur"] or "geen")] += 1
        d[r["uitkomst"]] += 1
        d["kosten"] += r["kosten"]
        if _moet_lezen(r):
            d[f"label {labels[r['id']]}"] += 1
    uit = {s: dict(c) for s, c in uit.items()}

    def tel(set_: str, regel) -> int:
        return sum(1 for r in rijen if r["set"] == set_ and regel(r))

    def n(set_: str) -> int:
        return tel(set_, lambda r: True)

    vals = lambda r: _moet_lezen(r) and labels[r["id"]] == "vals"  # noqa: E731
    if ronde == "lezer-v7":
        g2 = [r for r in rijen if r["set"] == "G2"]
        uit["eisen"] = {
            "G2: nooit rood of oranje": not any(r["kleur"] in ALARM for r in g2),
            "G2: minstens 80% geen bewering": sum(r["uitkomst"] == "geen bewering" for r in g2) >= 0.8 * len(g2),
            "W2: hoogstens 1% vals alarm": tel("W2", lambda r: vals(r) and r["kleur"] in ALARM) <= 0.01 * n("W2"),
            "W2: hoogstens 10% over een bewering": tel("W2", lambda r: r["uitkomst"] == "over een bewering")
            <= 0.10 * n("W2"),
            "W2: hoogstens 5% geen bewering": tel("W2", lambda r: r["uitkomst"] == "geen bewering") <= 0.05 * n("W2"),
            "W2: hoogstens 1 onterechte klopt grotendeels": tel("W2", lambda r: vals(r) and r["uitkomst"]
                                                                 == "klopt grotendeels") <= 1,
            "O': hoogstens 1 onterecht groen": tel("O'", lambda r: vals(r)) <= 1,
            "O': minstens 33% rood of oranje": tel("O'", lambda r: r["kleur"] in ALARM) >= 0.33 * n("O'"),
            "D: nooit groen": tel("D", lambda r: vals(r)) == 0,
            "S: nooit groen": tel("S-bron", lambda r: vals(r)) + tel("S-los", lambda r: vals(r)) == 0,
            "S-bron: minstens 75% satire": tel("S-bron", lambda r: r["uitkomst"] == "satire") >= 0.75 * n("S-bron")}
        return uit
    geen = [r for r in rijen if r["set"] == "G" and r["label"] == "geen bewering"]
    uit["eisen"] = {
        "G: nooit rood of oranje": not any(r["kleur"] in ALARM for r in geen),
        "G: minstens 80% geen bewering": sum(r["uitkomst"] == "geen bewering" for r in geen) >= 0.8 * len(geen),
        "W: hoogstens 3 van 300 vals alarm": tel("W", lambda r: vals(r) and r["kleur"] in ALARM) <= 3 * n("W") / 300,
        "W: minstens 70% groen": tel("W", lambda r: r["kleur"] == "groen") >= 0.7 * n("W"),
        "W: hoogstens 1 onterechte klopt grotendeels": tel("W", lambda r: vals(r) and r["uitkomst"] == "klopt grotendeels")
        <= 1,
        "O': hoogstens 1 onterecht groen": tel("O'", lambda r: vals(r)) <= 1,
        "O': minstens 33% rood of oranje": tel("O'", lambda r: r["kleur"] in ALARM) >= 0.33 * n("O'"),
        "D: nooit groen": tel("D", lambda r: vals(r)) == 0}
    return uit


def lees_labels(d: dict) -> dict[str, str]:
    labels = {r["id"]: r["label"] for r in d.get("oordelen", [])}
    fout = [k for k, v in labels.items() if v not in LABELWAARDEN]
    if fout:
        raise Weigering(f"onbekende labels: {fout[:3]}")
    return labels


def mag_nog(uitgegeven: float, erbij: int, budget: float = BUDGET) -> bool:
    """Nog `erbij` berichten binnen de grens, met de schatting per bericht."""
    return uitgegeven + erbij * SCHATTING <= budget


def _wacht_dicht(client, batch_id: str, slaap, klok, grens: float, poll: float = 5) -> None:
    begin = klok()
    while client.messages.batches.retrieve(batch_id).processing_status != "ended":
        if klok() - begin >= grens:
            raise RuntimeError(f"batch {batch_id} sluit niet na annuleren")
        slaap(poll)


def batch_met_grens(client, verzoeken: dict, verwerk, aangemeld, afgemeld, *, grens: float = GRENS_BATCH,
                    poll: float = 30, herkansingen: int = HERKANSINGEN, slaap=time.sleep, klok=time.monotonic,
                    melding=None) -> list[str]:
    """Dient `verzoeken` (custom_id → params) in als één batch. Een batch sluit pas als elke vraag klaar is, en de
    tellers staan tot dan op *in behandeling*; is hij na `grens` seconden niet dicht, dan annuleren: Anthropic sluit
    hem binnen een halve minuut, met de klare antwoorden erbij (2026-11-03: 29 van 30). Alleen wat geen antwoord kreeg,
    gaat opnieuw, hoogstens `herkansingen` keer. `verwerk` krijgt per batch de klare berichten (custom_id → bericht);
    `aangemeld(batch_id, ids)` en `afgemeld(batch_id)` houden de open batch bij voor de teller van de grens. Geeft de
    ids zonder antwoord."""
    melding = melding or (lambda m: print(m, flush=True))
    open_ = dict(verzoeken)
    for _ in range(herkansingen + 1):
        if not open_:
            break
        batch = client.messages.batches.create(requests=[{"custom_id": c, "params": p} for c, p in open_.items()])
        aangemeld(batch.id, list(open_))
        melding(f"batch {batch.id}: {len(open_)} verzoeken")
        begin = klok()
        while client.messages.batches.retrieve(batch.id).processing_status != "ended":
            if klok() - begin >= grens:
                melding(f"batch {batch.id} na {grens / 60:.0f} minuten niet dicht: geannuleerd")
                client.messages.batches.cancel(batch.id)
                _wacht_dicht(client, batch.id, slaap, klok, grens)
                break
            slaap(poll)
        klaar = {}
        for r in client.messages.batches.results(batch.id):
            if r.result.type == "succeeded":
                klaar[r.custom_id] = r.result.message
            else:
                melding(f"{r.custom_id}: {r.result.type}")
        for c in klaar:
            open_.pop(c)
        if klaar:
            verwerk(klaar)
        afgemeld(batch.id)
    return list(open_)


def kosten_van_batch(client, batch_id: str, zoekkosten: float, *, slaap=time.sleep, klok=time.monotonic) -> float:
    """Wat een batch kostte waarvan de antwoorden verloren gingen: eerst dicht (annuleren als hij nog loopt), dan de
    tokens van wat beantwoord werd tegen de batchprijs, plus de zoekvragen. Geannuleerde vragen kosten niets."""
    from doublecheck import berichtcontrole as bc
    from doublecheck.betatoets import kosten_batch

    if client.messages.batches.retrieve(batch_id).processing_status != "ended":
        client.messages.batches.cancel(batch_id)
        _wacht_dicht(client, batch_id, slaap, klok, GRENS_BATCH)
    return zoekkosten + sum(kosten_batch(bc.gebruik_uit(r.result.message))
                            for r in client.messages.batches.results(batch_id) if r.result.type == "succeeded")


# --- de bestanden en de CLI ----------------------------------------------------------------------

def _paden(ronde: dict) -> tuple[Path, Path, Path, Path]:  # pragma: no cover - de paden van een ronde
    m = ronde["map"]
    return m / "set.jsonl", m / "ontwikkel.jsonl", m / "antwoorden.jsonl", ronde["labels"]


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _voeg_toe(pad: Path, rijen: list[dict]) -> None:  # pragma: no cover - een bestand
    with pad.open("a", encoding="utf-8") as fh:
        for r in rijen:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _labels(ronde: dict) -> dict[str, str]:  # pragma: no cover - een bestand
    pad = _paden(ronde)[3]
    return lees_labels(json.loads(pad.read_text(encoding="utf-8"))) if pad.exists() else {}


def _boek(ronde: dict) -> tuple[Path, Path]:
    """De open batches (met de zoekvragen die er al voor betaald zijn) en wat verloren ging."""
    return ronde["map"] / "lopend.json", ronde["map"] / "verloren.jsonl"


def _uitgegeven(ronde: dict) -> float:
    """Alles wat de ronde kostte: de ontwikkelset, de antwoorden en wat verloren ging."""
    _, ontwikkel, antwoorden, _ = _paden(ronde)
    return sum(r["kosten"] for pad in (ontwikkel, antwoorden, _boek(ronde)[1]) for r in _jsonl(pad))


def _lopend(ronde: dict) -> dict:
    pad = _boek(ronde)[0]
    return json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}


def _schrijf_lopend(ronde: dict, lopend: dict) -> None:
    _boek(ronde)[0].write_text(json.dumps(lopend, ensure_ascii=False, indent=1), encoding="utf-8")


def _meld_aan(ronde: dict, batch_id: str, zoekkosten: float) -> None:
    _schrijf_lopend(ronde, {**_lopend(ronde), batch_id: {"zoekkosten": round(zoekkosten, 5)}})


def _meld_af(ronde: dict, batch_id: str) -> None:
    _schrijf_lopend(ronde, {b: v for b, v in _lopend(ronde).items() if b != batch_id})


def _vereffen(ronde: dict, client, *, slaap=time.sleep) -> None:
    """Een batch die nog open staat, is van een gestopt proces: de zoekresultaten zijn weg, dus de antwoorden ook.
    Wat hij kostte, gaat naar de verloren kosten, zodat de grens het meetelt."""
    for batch_id, v in _lopend(ronde).items():
        kosten = kosten_van_batch(client, batch_id, v["zoekkosten"], slaap=slaap)
        _voeg_toe(_boek(ronde)[1], [{"batch": batch_id, "kosten": round(kosten, 5),
                                     "reden": "batch van een gestopt proces, de antwoorden zonder zoekresultaten"}])
        _meld_af(ronde, batch_id)
        print(f"verloren: batch {batch_id}, ${kosten:.3f}", flush=True)


def _schoon(s: dict, config) -> dict:  # pragma: no cover - met de maskering van het product
    from doublecheck import berichtcontrole as bc

    s = {k: v for k, v in s.items() if k in ("id", "set", "tekst", "datum", "label", "eenstemmig", "claim",
                                                "verborgen", "origineel", "nieuw", "bron", "url", "site")}
    if "verborgen" in s:
        s["verborgen"] = sorted(s["verborgen"])
    return {**s, "tekst": bc.bericht_uit(s["tekst"], None, config.ocr)}


def _tiplines() -> list[dict]:  # pragma: no cover - een bestand
    import csv

    with TIPLINES.open(encoding="utf-8") as fh:
        return [{**r, "nr": i} for i, r in enumerate(csv.DictReader(fh))]


def _set(ronde: dict) -> None:  # pragma: no cover - op de bestanden, de database en, bij v7, drie feeds
    from doublecheck import tekstlezer as tl
    from doublecheck import verificatie
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    pad = _paden(ronde)[0]
    if pad.exists():
        raise SystemExit(f"{pad} ligt al vast")
    config = load_config(None)
    rijen = _tiplines()
    ronde6 = {int(s["id"][2:]) for s in verificatie.wilde_steekproef(rijen) if s["taal"] == "en"}
    if ronde["lezer"] == "lezer-v6":
        g, ontwikkel = kies_g(rijen, ronde6)
        bewaking = [s for s in tl.stukken(connect(str(WORTEL / "doublecheck.db"))) if s["set"] in ("W", "O'")]
        gemaakt = {x["id"]: x for x in _jsonl(WORTEL / "data" / "detail" / "gemaakt.jsonl")}
        d = [{"id": f"D:{x['id'].split(':', 1)[1]}", "set": "D", "tekst": x["tekst"], "datum": None,
              "origineel": gemaakt[x["id"]]["origineel"], "nieuw": gemaakt[x["id"]]["nieuw"]}
             for x in _jsonl(WORTEL / "data" / "detail" / "set.jsonl")]
        alle = [_schoon(s, config) for s in g + ontwikkel + bewaking + d]
    else:
        alle = _set_v7(config, rijen, ronde6)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in alle), encoding="utf-8")
    print(Counter(s["set"] for s in alle))


def _set_v7(config, tiplines: list[dict], ronde6: set[int]) -> list[dict]:  # pragma: no cover - live
    """De sets van #32.32. O' en D en de ontwikkelset komen uit de eerste ronde; G2 sluit G en de ontwikkelset van
    de eerste ronde uit; de satirekoppen per site één verzoek, met robots.txt, als FactizResearch."""
    import sqlite3 as sql
    import time
    import urllib.request
    import urllib.robotparser

    v6_set, _, v6_antwoorden, v6_labels = _paden(RONDES["lezer-v6"])
    eerste = _jsonl(v6_set)
    gebruikt = {int(s["id"].split("-")[1]) for s in eerste if s["set"].startswith("G")}
    g2, _ = kies_g(tiplines, ronde6 | gebruikt, n_geen=N_G2, n_wel=0, n_ontwikkel=0, zaad=ZAAD_2, eenstemmig=True,
                   naam="G2")
    w2 = kies_w2(_jsonl(WORTEL / "data" / "echtnieuws" / "wikinews-en.jsonl"))
    bewaking = [s for s in eerste if s["set"] in ("O'", "D")]
    conn = sql.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    satire = conn.execute("SELECT DISTINCT c.claim_id, c.canonical_text, f.review_date FROM claim c JOIN factcheck f "
                          "USING (claim_id) WHERE f.verdict_normalized = 'satire' AND c.language = 'en'").fetchall()
    groep = {c: g for c, g in conn.execute("SELECT claim_id, COALESCE(cluster_id, claim_id) FROM claim")}
    leden: dict[str, set[str]] = {}
    for c, g in groep.items():
        leden.setdefault(g, set()).add(c)
    s_los = [{**s, "verborgen": leden.get(groep.get(s["claim"], s["claim"]), {s["claim"]})} for s in kies_s_los(satire)]
    s_bron = []
    for naam, url in SATIRE.items():
        robots = urllib.robotparser.RobotFileParser(url.split("/feed/")[0] + "/robots.txt")
        robots.read()
        if not robots.can_fetch("FactizResearch", url):
            print(f"{naam}: robots.txt laat de feed niet toe")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "FactizResearch"})
        s_bron += koppen_uit_feed(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"), naam)[:N_PER_SITE]
        time.sleep(2)
    s_bron = s_bron[:N_S_BRON]
    labels = lees_labels(json.loads(v6_labels.read_text(encoding="utf-8")))
    w = sorted((r for r in _jsonl(v6_antwoorden) if r["set"] == "W"), key=lambda r: r["id"])
    gekozen = ([r["id"] for r in w if r["uitkomst"] == "over een bewering"][:9]
               + [r["id"] for r in w if r["uitkomst"] == "klopt grotendeels" and labels.get(r["id"]) == "vals"])
    per_id = {s["id"]: s for s in eerste}
    ontwikkel = [{**per_id[i], "set": "ontwikkel"} for i in gekozen]
    return [_schoon(s, config) for s in w2 + bewaking + g2 + s_los + s_bron] + ontwikkel


def _omgeving(ronde: dict):  # pragma: no cover - live
    import dataclasses
    import os

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    config = dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, lezer=ronde["lezer"],
                                                                             beeld=ronde.get("beeld", False)))
    conn, tabel = connect(str(WORTEL / "doublecheck.db")), bc.ijktabel(config)
    sleutel = os.environ["BRAVE_API_KEY"]

    def snel(tekst: str) -> dict | None:
        return bc.snel_antwoord(api.los_op(conn, config, tekst, None, None).model_dump(), tabel, tekst,
                                config.model_versions.text_embedding)

    def checks_voor(tekst: str, verborgen: frozenset) -> list[dict]:
        fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
        return zc.checks_uit(bc.geheugen_met(conn, config, tekst, fp, [], verborgen))

    def zoek(q: str) -> dict:
        import time

        time.sleep(1.1)  # binnen de grens van de zoekdienst
        return zc.brave(q, sleutel)

    return config, anthropic.Anthropic(max_retries=6), zoek, snel, checks_voor, bc.herkomstlijst()["sites"]


def _ontwikkel(ronde: dict) -> None:  # pragma: no cover - live
    """De ontwikkelset zonder batch, door `zoekcontrole.controleer` zelf, zoals `/check`."""
    config, client, zoek, snel, checks_voor, sites = _omgeving(ronde)
    set_, ontwikkel, _, _ = _paden(ronde)
    stukken = [s for s in _jsonl(set_) if s["set"] == ronde["ontwikkel"]]
    rijen = []
    for s in stukken:
        uit = zc.controleer(sqlite3.connect(":memory:"), s["tekst"], config, client, zoek, snel, sites, "meting",
                            datum=s["datum"], zoek_checks=lambda b: checks_voor(b, frozenset()))
        rijen.append(_rij(s, uit, uit["kosten"], ronde["lezer"]))
        print(f"{s['id']} [{s.get('label') or s['set']}]: {uit['uitkomst']} ({uit['oordeel']}, {uit['vorm']}, "
              f"{uit['kleur']}) {(uit['uitleg'] or '')[:100]}"
              + (f" | {uit['correctie']['woorden']} -> {uit['correctie']['juist']}" if uit.get("correctie") else ""),
              flush=True)
    _voeg_toe(ontwikkel, rijen)
    print(f"{len(rijen)} berichten, ${sum(r['kosten'] for r in rijen):.3f}; samen ${_uitgegeven(ronde):.2f}")


def _beeld_van(s: dict, config):  # pragma: no cover - een bestand
    """Het openbare beeld van een screenshot uit de set, zwartgemaakt zoals het product het meestuurt (B55)."""
    def laad():
        from doublecheck import opknippen

        begin = time.perf_counter()
        uit, n = opknippen.zwart_beeld(Path(s["beeld"]).read_bytes(), config.ocr)
        return uit, n, time.perf_counter() - begin
    return laad


def _draai(ronde: dict, proef: int | None) -> None:  # pragma: no cover - live
    """Per stuk van `STUK` berichten: kring 1 en zoeken, één batch met de grens van `GRENS_BATCH`, afmaken;
    hervatbaar per bericht, binnen de grens van de ronde (`budget`, anders `BUDGET`). Een open batch van een gestopt proces gaat eerst naar de verloren kosten."""
    config, client, zoek, snel, checks_voor, sites = _omgeving(ronde)
    _vereffen(ronde, client)
    set_, _, antwoorden, _ = _paden(ronde)
    sets = ronde["sets"]
    gedaan = {r["id"] for r in _jsonl(antwoorden)}
    werk = sorted((s for s in _jsonl(set_) if s["set"] in sets and s["id"] not in gedaan),
                  key=lambda s: sets.index(s["set"]))
    if proef:
        werk = [s for set_naam in sets for s in [x for x in werk if x["set"] == set_naam][:proef]]
    print(f"{len(werk)} berichten ({len(gedaan)} al gedaan), vraag {vingerafdruk(ronde["lezer"])}", flush=True)
    stukgrootte = ronde.get("stuk", STUK)
    for begin in range(0, len(werk), stukgrootte):
        stuk = werk[begin:begin + stukgrootte]
        if not mag_nog(_uitgegeven(ronde), len(stuk), ronde.get("budget", BUDGET)):
            print(f"gestopt vóór de grens: ${_uitgegeven(ronde):.2f} plus {len(stuk)} berichten", flush=True)
            break
        db, wacht = [], {}
        for i, s in enumerate(stuk):
            try:
                voor = voorbereiden(s, config, zoek, snel, sites, checks_voor,
                                    beeld=_beeld_van(s, config) if ronde.get("beeld") else None)
            except Exception as e:  # noqa: BLE001 - de soort fout, nooit de inhoud
                print(f"{s['id']}: {type(e).__name__}", flush=True)
                continue
            if voor["route"] == "database":
                db.append(voor["rij"])
            else:
                wacht[f"m{begin + i:04d}"] = (s, voor)
        _voeg_toe(antwoorden, db)
        if not wacht:
            continue
        print(f"{len(wacht)} naar de lezer, {len(db)} uit kring 1", flush=True)

        def verwerk(klaar: dict) -> None:
            rijen = [afmaken(*wacht[cid], msg, config) for cid, msg in klaar.items()]
            _voeg_toe(antwoorden, rijen)
            print(f"{len(rijen)} afgemaakt: {Counter((x['set'], x['uitkomst']) for x in rijen)}; "
                  f"samen ${_uitgegeven(ronde):.2f} van ${ronde.get('budget', BUDGET):.2f}", flush=True)

        gemist = batch_met_grens(client, {cid: voor["verzoek"] for cid, (_, voor) in wacht.items()}, verwerk,
                                 aangemeld=lambda b, ids: _meld_aan(ronde, b, zc.ZOEKPRIJS * len(ids)),
                                 afgemeld=lambda b: _meld_af(ronde, b))
        if gemist:
            ids = [wacht[c][0]["id"] for c in gemist]
            _voeg_toe(_boek(ronde)[1], [{"kosten": round(zc.ZOEKPRIJS * len(ids), 5), "ids": ids,
                                         "reden": "gezocht, maar geen antwoord na de herkansingen"}])
            print(f"zonder antwoord, de volgende keer opnieuw: {ids}", flush=True)


def _lezen(ronde: dict) -> None:  # pragma: no cover - op de bestanden
    set_, _, antwoorden, _ = _paden(ronde)
    labels, per_id = _labels(ronde), {s["id"]: s for s in _jsonl(set_)}
    nieuw = ("geen bewering", "satire", "over een bewering")
    for r in sorted(_jsonl(antwoorden), key=lambda r: (r["set"], r["id"])):
        te_labelen = _moet_lezen(r) and r["id"] not in labels
        bekijken = (r["set"] in ("W", "W2", "O'", "D") and r["uitkomst"] in nieuw) or r["set"].startswith("S-")
        if not te_labelen and not bekijken:
            continue
        s = per_id[r["id"]]
        print(f"\n== {r['id']} [{r['set']}{', ' + s['label'] if s.get('label') else ''}]"
              f"{' LABEL' if te_labelen else ''}: {r['uitkomst']} ({r['oordeel']}, {r['vorm']}, {r['kleur']}"
              f"{', bewering ' + str(r['kleur_bewering']) if r.get('kleur_bewering') else ''})\n{s['tekst'][:600]}\n"
              f"uitleg: {r['uitleg']}" + (f"\ndetail: {s['nieuw']} moet {s['origineel']} zijn" if s.get("nieuw") else "")
              + (f"\nverbetering: {r['correctie']['woorden']} -> {r['correctie']['juist']} ({r['correctie']['site']})"
                 if r.get("correctie") else ""))
        for b in r["bronnen"]:
            print(f"  - {b.get('rol')}: {b.get('site') or b.get('redactie')} {b.get('band') or b.get('oordeel') or ''} "
                  f"{b.get('url')}")


def _tellen(ronde: dict) -> None:  # pragma: no cover - op de bestanden
    _, _, antwoorden, _ = _paden(ronde)
    rijen = _jsonl(antwoorden)
    if {r["vraag"] for r in rijen} - {vingerafdruk(ronde["lezer"])}:
        raise Weigering("de antwoorden rusten op een andere vraag dan de code nu stelt")
    tel = telling(rijen, _labels(ronde), ronde["lezer"])
    (ronde["map"] / "telling.json").write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")
    for naam, c in tel.items():
        print(naam, c)
    print(f"samen ${_uitgegeven(ronde):.2f} van ${BUDGET:.2f}")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De lezer met alle uitkomsten (PLAN #32.31, #32.32)")
    parser.add_argument("stap", choices=("set", "ontwikkel", "draaien", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--lezer", default=LEZER, choices=tuple(RONDES))
    args = parser.parse_args()
    ronde = RONDES[args.lezer]
    {"set": lambda: _set(ronde), "ontwikkel": lambda: _ontwikkel(ronde), "draaien": lambda: _draai(ronde, args.proef),
     "lezen": lambda: _lezen(ronde), "tellen": lambda: _tellen(ronde)}[args.stap]()


if __name__ == "__main__":
    main()
