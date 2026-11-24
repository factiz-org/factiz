"""Omgekeerd zoeken op beelden (PLAN #31.8, ronde 3).

Het derde gereedschap van de factcheckmachine: het beeld gaat naar Google
Cloud Vision (Web Detection), dat teruggeeft op welke pagina's hetzelfde beeld
al stond, met adres en titel. Die lijst gaat als bron naar het model, dat ze
citeert als [R1], [R2] enzovoort. Keuze en kosten in het plan van 2026-10-25:
officiële API, $3,50 per 1.000 beelden en de eerste 1.000 per maand gratis;
Google bewaart het beeld niet en traint er niet op.

Alleen wat eruit is afgeleid, wordt bewaard (pagina's, trefwoorden, de beste
gok), nooit het beeld. Openbare beelden uit M4FC; een beeld van een gebruiker
gaat niet naar Google zonder besluit van de PO (DR3).

Ronde 5 (PO 2026-10-26): 50 ware beelden uit M4FC tegenover 50 ongebruikte
onware. De ware worden opnieuw opgehaald (de map van de stiltetoets is
opgeruimd), met dezelfde beleefdheid en robots.txt; Haiku kijkt per beeld naar
de vorm (kale foto, stempel van een factchecker).

    python -m doublecheck.beeldzoeken [zoeken] [--ronde 3|5] [--proef 1]
    python -m doublecheck.beeldzoeken waar
    python -m doublecheck.beeldzoeken vorm indienen|ophalen
"""

from __future__ import annotations

import base64
import json
import random
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse, urlsplit

WORTEL = Path(__file__).resolve().parent.parent
M4FC_JSON = WORTEL / "data" / "extern" / "m4fc" / "M4FC.json"
WAAR_MAP = WORTEL / "data" / "extern" / "m4fc" / "waar"
WAAR_STATUS = WORTEL / "data" / "extern" / "m4fc" / "waar-status.jsonl"
N_WAAR = 60  # 50 nodig; ruimte voor wat afvalt op de vorm
ZAAD_WAAR = 3149
AGENT = "FactizResearch/1.0 (https://factiz.org; meetset van ware beelden uit M4FC, PLAN #31.8)"

VISION = "https://vision.googleapis.com/v1/images:annotate"
MAX_RESULTATEN = 20
N_IN_VRAAG = 10
PATRONEN_FACTCHECK = ("fact-check", "factcheck", "fact_check", "hoax")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def zonder_factchecks(paginas: list[dict], domeinen: set[str]) -> list[dict]:
    """Zonder de pagina's van factcheckers: hun domeinen (ook subdomeinen) en
    adressen met een woord als "fact-check" of "hoax"."""
    def van_factchecker(url: str) -> bool:
        host = _host(url)
        if any(host == d or host.endswith("." + d) for d in domeinen):
            return True
        return any(p in url.lower() for p in PATRONEN_FACTCHECK)

    return [p for p in paginas if not van_factchecker(p["url"])]


def lees_vision(antwoord: dict) -> dict:
    """De pagina's met hetzelfde beeld (adres, titel zonder opmaak), de
    trefwoorden en de beste gok uit een antwoord van Web Detection."""
    web = ((antwoord.get("responses") or [{}])[0]).get("webDetection") or {}
    paginas = [{"url": p["url"], "titel": " ".join(re.sub(r"<[^>]+>", "", p.get("pageTitle") or "").split())}
               for p in web.get("pagesWithMatchingImages") or [] if p.get("url")]
    return {"paginas": paginas,
            "entiteiten": [e["description"] for e in web.get("webEntities") or [] if e.get("description")],
            "beste_gok": [b["label"] for b in web.get("bestGuessLabels") or [] if b.get("label")]}


def beeldzoek_tekst(paginas: list[dict]) -> str:
    """Het blok voor de vraag aan het model."""
    if not paginas:
        return "Reverse image search: no pages found with this image."
    regels = [f"[R{n}] {p.get('titel') or '(no title)'} — {_host(p['url'])} ({p['url']})"
              for n, p in enumerate(paginas[:N_IN_VRAAG], 1)]
    return ("Reverse image search (pages where this image or near-identical copies appear):\n" + "\n".join(regels))


# --- welke beelden kaal zijn (ronde 3) ----------------------------------------------
# Een schermafdruk van de virale post draagt de valse claim zelf en past niet bij
# het ware verhaal. Eerdere indelingen ("foto zonder tekst", "Haiku las geen
# bewering") lieten zulke schermafdrukken door (2026-10-25); dit is één vaste,
# eenvoudige vraag, en een steekproef wordt nagekeken.

KAAL_VERSIE = "kaal-v1"
KAAL_VRAAG = ("Is this image a plain photograph, with no social media post around it, no caption, headline, "
              "message or other text added on top of it? Ignore small watermarks, logos and text that is part of "
              "the scene itself (signs, banners, shirts). Answer with kaal true if it is a plain photograph, "
              "otherwise false.")
_KAAL_SCHEMA = {"type": "object", "properties": {"kaal": {"type": "boolean"}}, "required": ["kaal"],
                "additionalProperties": False}


def lees_kaal(tekst: str) -> bool | None:
    try:
        waarde = json.loads(tekst).get("kaal")
    except (json.JSONDecodeError, AttributeError):
        return None
    return waarde if isinstance(waarde, bool) else None


def kaal_verzoek(custom_id: str, pad: Path) -> dict:  # pragma: no cover - vorm van de Batch API
    from doublecheck.leraar import MODELLEN

    soort = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(Path(pad).suffix.lower(),
                                                                                  "image/jpeg")
    return {"custom_id": custom_id,
            "params": {"model": MODELLEN["haiku"]["id"], "max_tokens": 1_000,
                       "messages": [{"role": "user", "content": [
                           {"type": "image", "source": {"type": "base64", "media_type": soort,
                                                        "data": base64.b64encode(Path(pad).read_bytes()).decode()}},
                           {"type": "text", "text": KAAL_VRAAG}]}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _KAAL_SCHEMA}}}}


# --- de vorm (ronde 5) ---------------------------------------------------------------
# Factcheckers zetten soms hun oordeel op het beeld; zo'n beeld verraadt het
# antwoord. En kale foto's en schermafdrukken moeten in beide helften even vaak
# voorkomen.

VORM_VERSIE = "vorm-v1"
VORM_VRAAG = (KAAL_VRAAG.replace("Answer with kaal true if it is a plain photograph, otherwise false.",
                                 "Set kaal to true if it is a plain photograph, otherwise false.")
              + " Also: does the image carry a verdict mark added by a fact-checker, such as a stamp, banner or "
                "label saying FALSE, FAKE, FALSO, FALSCH, TRUE, VERDADEIRO, MISLEADING or similar, or a large red "
                "cross or green check mark? Set stempel to true if so, otherwise false.")
_VORM_SCHEMA = {"type": "object", "properties": {"kaal": {"type": "boolean"}, "stempel": {"type": "boolean"}},
                "required": ["kaal", "stempel"], "additionalProperties": False}


def lees_vorm(tekst: str) -> tuple[bool, bool] | None:
    try:
        d = json.loads(tekst)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or not all(isinstance(d.get(k), bool) for k in ("kaal", "stempel")):
        return None
    return d["kaal"], d["stempel"]


def vorm_verzoek(custom_id: str, pad: Path) -> dict:  # pragma: no cover - vorm van de Batch API
    verzoek = kaal_verzoek(custom_id, pad)
    verzoek["params"]["messages"][0]["content"][1]["text"] = VORM_VRAAG
    verzoek["params"]["output_config"]["format"]["schema"] = _VORM_SCHEMA
    return verzoek


def vorm_bestand(ronde: int) -> Path:
    from doublecheck.verificatie import map_van

    return map_van(ronde) / "vorm.jsonl"


def lees_vormen(ronde: int) -> dict[str, tuple[bool, bool]]:
    pad = vorm_bestand(ronde)
    if not pad.exists():
        return {}
    rijen = (json.loads(x) for x in pad.read_text(encoding="utf-8").splitlines() if x)
    return {r["sleutel"]: (r["kaal"], r["stempel"]) for r in rijen if r.get("kaal") is not None}


# --- de ware beelden (ronde 5) -------------------------------------------------------

def ware_kandidaten(m4fc: list[dict], eerder: dict[int, str | None], n: int = N_WAAR,
                    zaad: int = ZAAD_WAAR) -> list[int]:
    """Beelden die M4FC *waar* noemt en die bij de stiltetoets op te halen waren,
    willekeurig en telkens dezelfde."""
    groep = [i for i, x in enumerate(m4fc) if x.get("verdict") == "true" and eerder.get(i)]
    return sorted(random.Random(zaad).sample(groep, min(n, len(groep))))


def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in pad.read_text(encoding="utf-8").splitlines() if x.strip()] if pad.exists() else []


def eerder_opgehaald() -> dict[int, str | None]:  # pragma: no cover - op de statusbestanden van #26.3
    m4fc_map = M4FC_JSON.parent
    return {r["index"]: r.get("bestand") for naam in ("status.jsonl", "rest-status.jsonl")
            for r in _jsonl(m4fc_map / naam)}


def ware_stukken(m4fc: list[dict]) -> list[dict]:
    """De opgehaalde ware beelden als stukken, met de claim van M4FC als bijschrift."""
    uit = []
    for r in _jsonl(WAAR_STATUS):
        if not r.get("bestand"):
            continue
        i, x = r["index"], m4fc[r["index"]]
        uit.append({"id": f"w-{i:05d}", "sleutel": f"waar:{i:05d}", "soort": "beeld", "bron": "m4fc", "label": "waar",
                    "laag": "beeld waar", "helft": "toets", "tekst": x["claim"],
                    "datum": (x.get("fc_pub_date") or "")[:10] or None, "beeld": str(WAAR_MAP / r["bestand"]),
                    "zaak": None, "vers": False})
    return uit


def _mag(client, url: str, regels: dict) -> bool:  # pragma: no cover - met het netwerk
    from urllib.robotparser import RobotFileParser

    deel = urlsplit(url)
    basis = f"{deel.scheme}://{deel.netloc}"
    if basis not in regels:
        rp = RobotFileParser()
        try:
            r = client.get(basis + "/robots.txt", timeout=20, follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:  # geen robots.txt te lezen: zoals een ontbrekende
            rp.parse([])
        regels[basis] = rp
    return regels[basis].can_fetch(AGENT, url)


def ophalen_waar() -> Counter:  # pragma: no cover - met het netwerk
    """De ware kandidaten, één voor één: het origineel als robots.txt het
    toestaat, met 2 s ertussen; anders de Wayback-kopie, één per 4 s.
    Hervatbaar via `waar-status.jsonl`; alleen het beeld, verder niets."""
    import httpx

    from doublecheck.beeldstilte import _haal

    m4fc = json.loads(M4FC_JSON.read_text(encoding="utf-8"))
    klaar = {r["index"] for r in _jsonl(WAAR_STATUS)}
    WAAR_MAP.mkdir(parents=True, exist_ok=True)
    regels: dict = {}
    teller: Counter = Counter()
    laatst = 0.0
    with httpx.Client(headers={"User-Agent": AGENT}) as client:
        for i in ware_kandidaten(m4fc, eerder_opgehaald()):
            if i in klaar:
                continue
            item, data, uitkomst, bron = m4fc[i], None, "geen url", None
            if item.get("image_url"):
                if _mag(client, item["image_url"], regels):
                    data, uitkomst = _haal(client, item["image_url"])
                    bron = "origineel"
                    time.sleep(2)
                else:
                    uitkomst = "robots.txt"
            if data is None and item.get("wayback_image_url"):
                time.sleep(max(0.0, laatst + 4 - time.monotonic()))
                data, uitkomst = _haal(client, item["wayback_image_url"])
                bron, laatst = "wayback", time.monotonic()
            bestand = f"{i:05d}.{uitkomst}" if data is not None else None
            if bestand:
                (WAAR_MAP / bestand).write_bytes(data)
            with WAAR_STATUS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"index": i, "bestand": bestand, "bron": bron if bestand else None,
                                    "uitkomst": None if bestand else uitkomst}) + "\n")
            teller[bron if bestand else f"mislukt: {uitkomst}"] += 1
            print(f"{i:05d}: {bestand or uitkomst}", flush=True)
    (WAAR_MAP / "HERKOMST.txt").write_text(
        "Ware beelden uit M4FC (UKPLab, data onder CC BY-SA 4.0), opnieuw opgehaald 2026-10-26 voor de "
        "beeldenronde van PLAN #31.8; alleen om te meten, buiten git; mag weg na het tellen.\n", encoding="utf-8")
    return teller


# --- met het netwerk -----------------------------------------------------------------

def zoek(pad: Path, sleutel: str) -> dict:  # pragma: no cover - met Google Cloud Vision
    import httpx

    verzoek = {"requests": [{"image": {"content": base64.b64encode(Path(pad).read_bytes()).decode()},
                             "features": [{"type": "WEB_DETECTION", "maxResults": MAX_RESULTATEN}]}]}
    for poging in range(4):
        antwoord = httpx.post(VISION, params={"key": sleutel}, json=verzoek, timeout=60)
        if antwoord.status_code == 200:
            return lees_vision(antwoord.json())
        if antwoord.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"Vision {antwoord.status_code}: {antwoord.text[:300]}")
        time.sleep(5 * 2 ** poging)
    raise RuntimeError("Vision blijft weigeren; later hervatten")


def bestand(ronde: int) -> Path:
    from doublecheck.verificatie import map_van

    return map_van(ronde) / "beeldzoeken.jsonl"


def lees(ronde: int) -> dict[str, dict]:
    pad = bestand(ronde)
    if not pad.exists():
        return {}
    return {r["sleutel"]: r for r in (json.loads(x) for x in pad.read_text(encoding="utf-8").splitlines() if x)}


def _vorm(deel: str | None) -> None:  # pragma: no cover - met de Batch API
    """Ronde 5: de vorm van elke kandidaat (de opgehaalde ware en de onware
    kandidaten), met Haiku in één batch."""
    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.verificatie import kandidaten_ronde5, map_van

    client = anthropic.Anthropic()
    batches = map_van(5) / "vorm-batches.jsonl"
    waar, onwaar = kandidaten_ronde5()
    per_id = {s["id"]: s for s in waar + onwaar}
    if deel == "indienen":
        klaar = {r["id"] for r in _jsonl(vorm_bestand(5))} | {i for b in _jsonl(batches) for i in b["ids"]}
        nog = [s for s in waar + onwaar if s["id"] not in klaar]
        if not nog:
            raise SystemExit("niets in te dienen")
        batch = client.messages.batches.create(requests=[vorm_verzoek(s["id"], Path(s["beeld"])) for s in nog])
        batches.parent.mkdir(parents=True, exist_ok=True)
        with batches.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "versie": VORM_VERSIE, "ids": [s["id"] for s in nog]}) + "\n")
        print(f"batch {batch.id}: {len(nog)} beelden ({len(waar)} ware, {len(onwaar)} onware kandidaten)")
        return
    m = MODELLEN["haiku"]
    alle, teller = _jsonl(batches), Counter()
    with vorm_bestand(5).open("a", encoding="utf-8") as uit:
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                vorm = None
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += (msg.usage.input_tokens * m["in"] + msg.usage.output_tokens * m["uit"]) / 1e6
                    vorm = lees_vorm("".join(getattr(bl, "text", "") or "" for bl in msg.content))
                s = per_id[r.custom_id]
                uit.write(json.dumps({"id": s["id"], "sleutel": s["sleutel"], "label": s["label"],
                                      "kaal": vorm[0] if vorm else None, "stempel": vorm[1] if vorm else None,
                                      "versie": VORM_VERSIE}) + "\n")
                teller[(s["label"], "kaal" if vorm and vorm[0] else "tekst" if vorm else "?",
                        "stempel" if vorm and vorm[1] else "")] += 1
            b["werkelijk"] = round(werkelijk, 4)
    batches.write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    print(sorted(teller.items()), f"werkelijk ${sum(b.get('werkelijk') or 0 for b in alle):.3f}")


def main() -> None:  # pragma: no cover - CLI, met Google Cloud Vision
    import argparse
    import os

    from doublecheck.varianten import laad_sleutel
    from doublecheck.verificatie import gekozen_stukken

    parser = argparse.ArgumentParser(description="Omgekeerd zoeken op beelden (#31.8, ronde 3 en 5)")
    parser.add_argument("stap", nargs="?", default="zoeken", choices=("zoeken", "waar", "vorm"))
    parser.add_argument("deel", nargs="?", choices=("indienen", "ophalen"), help="bij vorm")
    parser.add_argument("--ronde", type=int, default=3)
    parser.add_argument("--proef", type=int, default=0, help="alleen de eerste N beelden")
    args = parser.parse_args()
    if args.stap == "waar":
        print(dict(ophalen_waar()))
        return
    laad_sleutel()
    if args.stap == "vorm":
        _vorm(args.deel)
        return
    sleutel = os.environ.get("GOOGLE_VISION_API_KEY")
    if not sleutel:
        raise SystemExit("GOOGLE_VISION_API_KEY ontbreekt in .env (PO: project met facturering, Vision aan)")
    klaar = lees(args.ronde)
    beelden = list(dict.fromkeys((s["sleutel"], s["beeld"]) for s in gekozen_stukken(args.ronde) if s.get("beeld")))
    if args.proef:
        beelden = beelden[: args.proef]
    pad = bestand(args.ronde)
    pad.parent.mkdir(parents=True, exist_ok=True)
    for sleutel_beeld, beeld in beelden:
        if sleutel_beeld in klaar:
            continue
        r = {"sleutel": sleutel_beeld, **zoek(Path(beeld), sleutel)}
        with pad.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{sleutel_beeld}: {len(r['paginas'])} pagina's; {r['beste_gok'][:1]}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
