"""Factiz tegen gewoon zoeken: een blind duel met Gemini in de kaartenbak (PLAN #32.47, PO 2026-11-07: "eigenlijk willen
we ook het verschil testen tussen een check met Factiz vs een check met 'gewoon' Google (gemini) ... dit is immers
uiteindelijk ons doel"; "Alleen Gemini").

Dezelfde berichten naar Factiz (`lezer-v11`, zoals het product: kring 1, de database, de factchecksites, het beeld) en
naar Gemini met Google Search (`GEMINI_MODEL`), met de vraag die een Nederlandse gebruiker zou stellen (`VRAAG`). De PO ziet
per bericht de twee antwoorden blind als A en B, kiest welk antwoord klopt en welk het meest helpt, en ziet daarna wie wie
was. Naar Google gaat alleen openbaar nieuws, openbare factchecks en openbare nieuwsfoto's.

    python -m doublecheck.duel set --zaad <ronde>
    python -m doublecheck.meting docs/meetplannen/<ronde>.json set|draaien [--proef N]
    python -m doublecheck.duel gemini --zaad <ronde> [--proef N]
    python -m doublecheck.duel kaarten --zaad <ronde> --titel <tekst>
    python -m doublecheck.poproef pagina --zaad <ronde>
"""

from __future__ import annotations

import base64
import json
import random
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "duel"
GEMINI_MODEL = "gemini-4-argon"
GEMINI_ADRES = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Gelezen 2026-11-07 op aistudio.google.com/docs/pricing: per miljoen woorddelen tot 30 november 2026 (daarna het
# dubbele); zoeken de eerste 5.000 per maand gratis, daarna per 1.000
PRIJS_IN, PRIJS_UIT, PRIJS_ZOEKEN = 2.0, 10.0, 14.0
GRATIS_ZOEKEN = 5000
BUDGET = 2.0
N_NEP, DAGEN_NEP = 25, 60
VRAAG = ("Klopt dit? Begin je antwoord met één regel: 'OORDEEL: klopt', 'OORDEEL: klopt niet', 'OORDEEL: misleidend' of "
         "'OORDEEL: weet ik niet'. Leg daarna in het Nederlands kort uit waarom, en noem je bronnen.\n\nHet bericht:\n")
_OORDEEL = re.compile(r"OORDEEL\s*:\s*\**\s*([^\n*]+)", re.IGNORECASE)
KLEUR = {"klopt": "groen", "klopt niet": "rood", "misleidend": "oranje"}
_BRONNENKOP = re.compile(r"\n\s*[*#_ ]*(?:Bronnen|Sources)\s*:?[*_ ]*:?\s*\n", re.IGNORECASE)
_UITLEGKOP = re.compile(r"^[*#_ ]*(?:Uitleg|Toelichting)\s*:?[*_ ]*:?[*_ ]*\s*", re.IGNORECASE)


def verse_nep(checks: list[dict], gezien: set[str], n: int = N_NEP, zaad: str = "", sinds: str = "") -> list[dict]:
    """Verse nepberichten: Engelse checks van een westerse factchecker (`poproef.WESTERSE_FACTCHECKERS`) met *onwaar* of
    *misleidend*, vanaf `sinds`, één per bewering, nooit een die de PO al zag. Vast zaad; de volgorde telt niet."""
    from doublecheck.poproef import WESTERSE_FACTCHECKERS

    per_claim: dict[str, dict] = {}
    for c in sorted(checks, key=lambda c: (c["claim_id"], c["datum"], c["url"])):
        if (c["taal"] == "en" and c["publisher"] in WESTERSE_FACTCHECKERS and c["oordeel"] in ("onwaar", "misleidend")
                and c["datum"] >= sinds and c["claim_id"] not in gezien):
            per_claim.setdefault(c["claim_id"], c)
    alle = sorted(per_claim.values(), key=lambda c: c["claim_id"])
    gekozen = sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda c: c["claim_id"])
    return [{"id": f"O:{c['claim_id']}", "set": "O", "tekst": " ".join(c["tekst"].split()), "datum": c["datum"],
             "publisher": c["publisher"], "oordeel": c["oordeel"], "claim_id": c["claim_id"], "eigen_urls": [c["url"]]}
            for c in gekozen]


def gemini_verzoek(bericht: str, beeld: bytes | None = None, mime: str | None = None) -> dict:
    """De vraag aan Gemini met Google Search, zoals een Nederlandse gebruiker hem stelt; bij een foto de foto erbij."""
    delen = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(beeld).decode()}}] if beeld else []
    return {"contents": [{"parts": [*delen, {"text": VRAAG + bericht}]}], "tools": [{"google_search": {}}]}


def _zonder_koppen(uitleg: str) -> str:
    """Zonder het kopje *Uitleg* en zonder het eigen lijstje *Bronnen*: de bronnen staan al onder elk antwoord (uit
    Google Search), en zo verraadt de vorm niet wie het schreef."""
    uitleg = _BRONNENKOP.split(uitleg)[0]
    return _UITLEGKOP.sub("", uitleg.strip(" *\n")).strip(" *\n")


def lees_gemini(antwoord: dict) -> dict:
    """Het oordeel (de regel `OORDEEL:`; zonder zo'n regel *weet ik niet*), de uitleg, de bronnen van Google Search, het
    aantal zoekvragen en de woorddelen."""
    gebruik = antwoord.get("usageMetadata") or {}
    tokens = {"in": gebruik.get("promptTokenCount", 0),
              "uit": gebruik.get("candidatesTokenCount", 0) + gebruik.get("thoughtsTokenCount", 0)}
    kandidaten = antwoord.get("candidates") or []
    if not kandidaten:
        return {"oordeel": "geen antwoord", "uitleg": "", "bronnen": [], "zoekvragen": 0, "tokens": tokens, "tekst": ""}
    k = kandidaten[0]
    tekst = "".join(d.get("text", "") for d in (k.get("content") or {}).get("parts") or []).strip()
    m = _OORDEEL.search(tekst)
    ruw = m.group(1).strip().lower().rstrip(".") if m else ""
    oordeel = next((o for o in ("klopt niet", "misleidend", "weet ik niet", "klopt") if ruw.startswith(o)), "weet ik niet")
    uitleg = _zonder_koppen((tekst[:m.start()] + tekst[m.end():]) if m else tekst)
    meta = k.get("groundingMetadata") or {}
    bronnen = [{"site": (c.get("web") or {}).get("title"), "url": (c.get("web") or {}).get("uri")}
               for c in meta.get("groundingChunks") or [] if (c.get("web") or {}).get("uri")]
    return {"oordeel": oordeel, "uitleg": uitleg, "bronnen": bronnen, "zoekvragen": len(meta.get("webSearchQueries") or []),
            "tokens": tokens, "tekst": tekst}


def gemini_sleutel(omgeving) -> str | None:
    """De sleutel voor Gemini: een eigen `GEMINI_API_KEY`, anders die van het Google-project van Factiz (Factiz-org,
    waar sinds 2026-11-07 ook de Gemini API aanstaat; dezelfde sleutel als Google Vision)."""
    return omgeving.get("GEMINI_API_KEY") or omgeving.get("GOOGLE_VISION_API_KEY")


def kosten(uit: dict, gratis_over: int = 0) -> float:
    """Wat één antwoord van Gemini kost: de woorddelen, en de zoekvragen boven wat er deze maand nog gratis is."""
    zoeken = max(0, uit["zoekvragen"] - max(0, gratis_over))
    return round(uit["tokens"]["in"] * PRIJS_IN / 1e6 + uit["tokens"]["uit"] * PRIJS_UIT / 1e6 + zoeken * PRIJS_ZOEKEN / 1000, 6)


def _kaal(tekst: str | None) -> str:
    """Zonder opmaak in markdown, zodat geen van beide antwoorden er anders uitziet."""
    tekst = re.sub(r"\*\*|__", "", tekst or "")
    tekst = re.sub(r"(?<![\w*])[*_](\S(?:[^*_\n]*\S)?)[*_](?![\w*])", r"\1", tekst)
    return re.sub(r"(?m)^\s*[*-]\s+", "• ", tekst).strip()


def _site(url: str) -> str:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def duelkaart(factiz: dict, gemini: dict, zaad: str = "") -> dict:
    """De twee antwoorden op één bericht, blind als A en B, in een vaste willekeurige volgorde per bericht. Niets in de
    vorm verraadt wie wie is: dezelfde bronregel (site en adres, geen band), geen opmaak, *weet ik niet* als *onzeker*,
    en een antwoord uit de database als de zin van de redactie."""
    uitleg = factiz.get("uitleg")
    if not uitleg and factiz.get("route") == "database":
        uitleg = " ".join(f"Dit is al gecontroleerd: {b['redactie']} noemde het {b.get('oordeel') or 'onwaar'}."
                          for b in factiz.get("bronnen") or [] if b.get("redactie"))
    van_factiz = {"wie": "Factiz", "oordeel": factiz["uitkomst"], "kleur": factiz.get("kleur"), "uitleg": _kaal(uitleg),
                  "bronnen": [{"site": _site(b["url"]), "url": b["url"]} for b in factiz.get("bronnen") or []
                              if b.get("url")]}
    van_gemini = {"wie": "Gemini", "oordeel": "onzeker" if gemini["oordeel"] == "weet ik niet" else gemini["oordeel"],
                  "kleur": KLEUR.get(gemini["oordeel"]), "uitleg": _kaal(_zonder_koppen(gemini.get("uitleg") or "")),
                  "bronnen": [{"site": b.get("site") or _site(b["url"]), "url": b["url"]} for b in gemini.get("bronnen") or []]}
    paar = [van_factiz, van_gemini]
    if random.Random(f"{zaad}|{factiz['id']}").random() < 0.5:
        paar.reverse()
    return {"id": factiz["id"], "antwoorden": paar}


# --- de bestanden en het netwerk -------------------------------------------------------------------------------

def _checks_uit_database() -> list[dict]:  # pragma: no cover - op de database
    import sqlite3

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    return [{"claim_id": c, "tekst": t, "datum": (d or "")[:10], "url": u, "publisher": p, "oordeel": o, "taal": lang}
            for c, t, d, u, p, o, lang in conn.execute(
                "SELECT f.claim_id, c.canonical_text, f.review_date, f.url, f.publisher, f.verdict_normalized, f.language "
                "FROM factcheck f JOIN claim c USING (claim_id)")]


def _gezien() -> set[str]:  # pragma: no cover - op de bestanden
    """Elke bewering die de PO al zag, of die in een meetset zat waarop regels gebouwd of gemeten zijn."""
    uit = set()
    for p in [*(WORTEL / "data" / "poproef").glob("*.json"), *UIT.glob("*-berichten.jsonl"),
              *(WORTEL / "data" / "talen").rglob("*.jsonl"), *(WORTEL / "data" / "meting").glob("*/set.jsonl")]:
        tekst = p.read_text(encoding="utf-8")
        uit |= set(re.findall(r"gfc-[0-9a-f]{16}", tekst))
    return uit


def _set(zaad: str) -> None:  # pragma: no cover - het netwerk, de database en de bestanden
    import datetime

    from doublecheck import poproef as pp

    bron = UIT / f"{zaad}-berichten.jsonl"
    if bron.exists():
        raise SystemExit(f"{bron.name} ligt al vast")
    items, media = pp._feeds_ophalen()
    sinds = (datetime.date.today() - datetime.timedelta(days=pp.DAGEN)).isoformat()
    nieuws = pp.nieuwsronde([i for i in items if (i["datum"] or "") >= sinds], pp.N_KOPPEN, pp.N_FOTOS, zaad)
    sinds_nep = (datetime.date.today() - datetime.timedelta(days=DAGEN_NEP)).isoformat()
    nep = verse_nep(_checks_uit_database(), _gezien(), N_NEP, zaad, sinds_nep)
    UIT.mkdir(parents=True, exist_ok=True)
    bron.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in nieuws + nep), encoding="utf-8")
    plan = {"taak": zaad,
            "toelichting": (f"Het duel met Gemini (PLAN #32.47): {len(nieuws)} berichten uit het nieuws van {len(media)} media "
                            f"en {len(nep)} verse nepberichten van westerse factcheckers (vanaf {sinds_nep}). Factiz zoals het "
                            "product, met `lezer-v11`. Geen eisen: de keuzes van de PO zijn de labels."),
            "map": f"data/meting/{zaad}", "labels": f"docs/steekproeven/{zaad}-meting.json",
            "budget": 2.0, "zaad": 3254,
            "sets": {"K": {"bron": str(bron.relative_to(WORTEL)), "set": "K"},
                     "F": {"bron": str(bron.relative_to(WORTEL)), "set": "F", "beeld": True},
                     "O": {"bron": str(bron.relative_to(WORTEL)), "set": "O"}},
            "armen": {"C": {"lezer": "lezer-v11", "speurvraag_model": "claude-haiku-5-5"}},
            "onwaar": [], "waar": [], "eisen": [], "zoekvragen_max": 250}
    pad = WORTEL / "docs" / "meetplannen" / f"{zaad}.json"
    pad.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(nieuws)} nieuws en {len(nep)} nep in {bron.name}; meetplan {pad.name}")


def _gemini(zaad: str, proef: int | None) -> None:  # pragma: no cover - het netwerk
    """Elk bericht één keer naar Gemini met Google Search; hervatbaar; stopt bij de grens of bij een fout."""
    import os
    import time

    import httpx

    from doublecheck import zoekcontrole as zc
    from doublecheck.meting import beeld_of_reserve
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    sleutel = gemini_sleutel(os.environ)
    if not sleutel:
        raise SystemExit("geen sleutel voor Gemini in .env (GEMINI_API_KEY of GOOGLE_VISION_API_KEY)")
    berichten = [json.loads(r) for r in (UIT / f"{zaad}-berichten.jsonl").read_text(encoding="utf-8").splitlines() if r]
    pad = UIT / f"{zaad}-gemini.jsonl"
    klaar = [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r] if pad.exists() else []
    gedaan, uitgegeven = {r["id"] for r in klaar}, sum(r["kosten"] for r in klaar)
    zoekvragen = sum(r["zoekvragen"] for r in klaar)
    werk = [b for b in berichten if b["id"] not in gedaan][:proef or None]
    with httpx.Client(timeout=300) as web, pad.open("a", encoding="utf-8") as uit:
        for b in werk:
            if uitgegeven >= BUDGET:
                print(f"gestopt bij de grens: ${uitgegeven:.2f}")
                return
            beeld = beeld_of_reserve(b) if b.get("beeld") else None
            if b.get("beeld") and not beeld:
                print(f"{b['id']}: de foto opent niet meer; overgeslagen, zoals bij Factiz")
                continue
            begin = time.monotonic()
            verzoek = gemini_verzoek(b["tekst"], beeld, zc.media_soort(beeld) if beeld else None)
            try:
                r = web.post(GEMINI_ADRES.format(model=GEMINI_MODEL), headers={"x-goog-api-key": sleutel}, json=verzoek)
            except httpx.TimeoutException:
                print(f"{b['id']}: geen antwoord binnen 300 seconden; bij de volgende keer opnieuw")
                continue
            if r.status_code != 200:
                print(f"{b['id']}: status {r.status_code}; gestopt")
                return
            seconden = round(time.monotonic() - begin, 2)
            antwoord = lees_gemini(r.json())
            prijs = kosten(antwoord, GRATIS_ZOEKEN - zoekvragen)
            zoekvragen += antwoord["zoekvragen"]
            uitgegeven += prijs
            uit.write(json.dumps({"id": b["id"], "set": b["set"], **antwoord, "kosten": prijs,
                                  "seconden": seconden, "model": GEMINI_MODEL}, ensure_ascii=False) + "\n")
            uit.flush()
            print(f"{b['id']}: {antwoord['oordeel']} ({antwoord['zoekvragen']} zoekvragen, ${prijs:.4f})", flush=True)
    print(f"samen ${uitgegeven:.2f}, {zoekvragen} zoekvragen bij Google")


def _kaarten(zaad: str, titel: str | None, bron: str | None = None) -> None:  # pragma: no cover - op de bestanden
    """De duelkaarten van meetplan `zaad`; `bron`: de ronde waarvan de berichten en de antwoorden van Gemini komen
    (een nieuwe lezer tegen dezelfde antwoorden, #32.49)."""
    bron = bron or zaad
    from doublecheck import berichtcontrole as bc
    from doublecheck import meting as mt
    from doublecheck import poproef as pp
    from doublecheck.speuren import eerste_dag_domeinen, van_factchecker

    hosts = eerste_dag_domeinen(bc.herkomstlijst()["sites"])
    plan = mt.lees_plan(f"docs/meetplannen/{zaad}.json")
    factiz = {r["id"]: r for r in mt._jsonl(plan["_map"] / "antwoorden.jsonl")}
    gemini = {r["id"]: r for r in mt._jsonl(UIT / f"{bron}-gemini.jsonl")}
    items = {i["id"]: i for i in mt._jsonl(UIT / f"{bron}-berichten.jsonl")}
    kaarten = []
    for i in sorted(set(factiz) & set(gemini), key=lambda i: random.Random(zaad + i).random()):
        urls = {i: items[i]["eigen_urls"][0]} if items[i].get("eigen_urls") else {}
        basis = pp._kaart(factiz[i], items[i], urls, lambda u: van_factchecker(u, hosts))
        kaarten.append({**basis, **duelkaart(factiz[i], gemini[i], zaad)})
    doel = pp.UIT / f"{zaad}.json"
    doel.write_text(json.dumps({"ronde": zaad, "titel": titel, "modus": "product", "soort": "duel", "meting": plan["taak"],
                                "lezer": plan["armen"]["C"]["lezer"], "tegen": GEMINI_MODEL, "voorraad": len(items),
                                "kaarten": kaarten}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(kaarten)} duelkaarten in {doel}")


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import datetime

    parser = argparse.ArgumentParser(description="Factiz tegen Gemini (PLAN #32.47)")
    parser.add_argument("stap", choices=("set", "gemini", "kaarten"))
    parser.add_argument("--zaad", default=f"duel-{datetime.date.today().isoformat()}")
    parser.add_argument("--proef", type=int)
    parser.add_argument("--titel")
    parser.add_argument("--bron", help="kaarten: de ronde met de berichten en de antwoorden van Gemini")
    args = parser.parse_args()
    {"set": lambda: _set(args.zaad), "gemini": lambda: _gemini(args.zaad, args.proef),
     "kaarten": lambda: _kaarten(args.zaad, args.titel, args.bron)}[args.stap]()


if __name__ == "__main__":
    main()
