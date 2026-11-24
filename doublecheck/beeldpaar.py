"""V1 en V2 van de radar (PLAN #32.69): het virale beeld en het origineel uit hetzelfde factcheckartikel.

De hypothese van de PO (2026-11-10): wie de mening wil beïnvloeden, heeft meestal een echte nieuwsfoto nodig die hij
manipuleert. Dan moet Factiz het virale beeld kunnen terugvinden bij het origineel, en zeggen wat er veranderde.

- **V1:** 1.959 factcheckartikelen tonen het virale beeld én het origineel (`rol-v3`, de beeldoogst, #32.35). Op 50 paren
  en 25 schijnparen (het virale beeld naast het origineel van een ander artikel): (a) lokaal, hoe dicht de twee bij
  elkaar liggen (PDQ, DINOv2, SIFT); (b) Sonnet 5.5, Opus 5.5 en Fable 5.2 krijgen beide beelden, de bewering en het
  bijschrift van het origineel, met dezelfde vraag: komt A van B, wat veranderde er, wat toont B echt. Ik label per paar
  wat er echt veranderde, uit het artikel (B34).
- **V2:** waar de originelen vandaan komen (een persbureau, een groot medium, sociale media, een archief), uit de tekst
  rond het origineel in het artikel.

De beelden alleen in het geheugen (B35); de Batch API op openbare beelden.

    python -m doublecheck.beeldpaar set|teksten|lezen
    python -m doublecheck.hittewacht -- python -m doublecheck.beeldpaar lokaal
    python -m doublecheck.beeldpaar indienen [--proef N]|ophalen|tellen|bronnen|opruimen
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "radar" / "v1"
LABELS = WORTEL / "docs" / "steekproeven" / "32.69-beeldparen.json"
ZAAD = 3269
AANTAL_PAREN, AANTAL_SCHIJN, PER_HOST = 50, 25, 3
MODELLEN_V1 = ("sonnet", "opus", "fable")
VERSIE = "beeldpaar-v1"
VERANDERINGEN = ("andere context", "bijgesneden", "bewerkt", "tekst toegevoegd", "AI-gemaakt", "geen verandering")
AFGELEID = ("ja", "nee", "twijfel")
GRENS = 8.00
SCHATTING = {"sonnet": 0.008, "opus": 0.016, "fable": 0.07}   # per paar, ruim; de werkelijke kosten bij het ophalen
MAX_TOKENS = {"sonnet": 3000, "opus": 3000, "fable": 8000}    # Fable denkt altijd, en dat telt mee (RESEARCH §12)


class Weigering(RuntimeError):
    pass


def _sha(*delen: str) -> str:
    return hashlib.sha1("|".join(delen).encode()).hexdigest()[:12]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def kies_paren(rollen: list[dict], context: dict[str, str], claims: dict[str, dict], n: int = AANTAL_PAREN,
               per_host: int = PER_HOST, zaad: int = ZAAD) -> list[dict]:
    """Per artikel met een check het virale beeld dat iemand zou doorsturen (`latset.kies_viraal`: geen stempelwoord) en
    het eerste origineel; een vaste steekproef van `n`, hoogstens `per_host` per site."""
    from doublecheck.latset import kies_viraal
    from doublecheck.terugaanvoer import artikel

    kandidaten = []
    for r in sorted(rollen, key=lambda r: r["artikel"]):
        viraal = kies_viraal(r["beelden"], r["rollen"])
        origineel = next((b for b, rol in zip(r["beelden"], r["rollen"]) if rol == "origineel"), None)
        c = claims.get(artikel(r["artikel"]))
        if viraal and origineel and c:
            kandidaten.append({"id": "P:" + _sha(r["artikel"]), "soort": "paar", "host": _host(r["artikel"]),
                               "artikel": r["artikel"], "artikel_origineel": r["artikel"], "viraal": viraal,
                               "origineel": origineel, "claim": c["tekst"], "oordeel": c["oordeel"],
                               "taal": c["taal"], "context_origineel": context.get(origineel, "")})
    random.Random(zaad).shuffle(kandidaten)
    uit, per = [], collections.Counter()
    for k in kandidaten:
        if len(uit) >= n:
            break
        if per[k["host"]] < per_host:
            per[k["host"]] += 1
            uit.append(k)
    return uit


def schijnparen(paren: list[dict], n: int = AANTAL_SCHIJN, zaad: int = ZAAD) -> list[dict]:
    """Het virale beeld naast het origineel van een ander artikel, liefst van dezelfde site (dezelfde huisstijl): daar
    moet het antwoord *nee* zijn."""
    rnd = random.Random(zaad)
    uit = []
    for p in rnd.sample(paren, min(n, len(paren))):
        zelfde = [q for q in paren if q["host"] == p["host"] and q["artikel"] != p["artikel"]]
        ander = [q for q in paren if q["artikel"] != p["artikel"]]
        q = rnd.choice(zelfde or ander)
        uit.append({**p, "id": "S:" + _sha(p["viraal"], q["origineel"]), "soort": "schijn", "origineel": q["origineel"],
                    "artikel_origineel": q["artikel"], "context_origineel": q["context_origineel"]})
    return uit


_VRAAG = """Image A was shared online with this claim: "{claim}"
Image B is a photo that was published earlier. What the page around image B says about it: "{context}"

1. stempel: does image A carry a mark that a fact-checker added (a stamp or label such as FALSE, FAKE, BULO, FALSO, a \
cross, a red frame, or a fact-checker's logo)?
2. afgeleid: is image A made from image B: the same photo or footage, possibly cropped, edited, combined or with text \
added? Answer ja, nee or twijfel.
3. veranderingen: if ja, what was done to it, from this list: andere context (B is shown with another place, date, event \
or meaning), bijgesneden, bewerkt (something in the picture was changed, added or removed), tekst toegevoegd, AI-gemaakt \
(A was generated with AI from or after B), geen verandering. Give an empty list if nee.
4. wat_echt: one sentence on what image B really shows, as far as the image and the text around it tell.
5. uitleg: two or three sentences on how A differs from B and whether the claim holds.
Judge only from the two images and the text given."""

_SCHEMA = {"type": "object", "additionalProperties": False,
           "required": ["stempel", "afgeleid", "veranderingen", "wat_echt", "uitleg"],
           "properties": {"stempel": {"type": "boolean"}, "afgeleid": {"type": "string", "enum": list(AFGELEID)},
                          "veranderingen": {"type": "array", "items": {"type": "string", "enum": list(VERANDERINGEN)}},
                          "wat_echt": {"type": "string"}, "uitleg": {"type": "string"}}}


def paarverzoek(p: dict, viraal: bytes, origineel: bytes, model: str) -> dict:
    """Dezelfde vraag aan elk model: beide beelden (verkleind, alleen in het geheugen), de bewering en de tekst rond het
    origineel, met vast JSON."""
    from doublecheck.beschrijvingvraag import _jpeg
    from doublecheck.modellen import MODELLEN

    inhoud = [{"type": "text", "text": "Image A:"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(viraal)}},
              {"type": "text", "text": "Image B:"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(origineel)}},
              {"type": "text", "text": _VRAAG.format(claim=" ".join(p["claim"].split())[:600],
                                                    context=" ".join((p.get("context_origineel") or "").split())[:600])}]
    return {"custom_id": f"{model}-{p['id'].split(':', 1)[1]}", "params": {
        "model": MODELLEN[model]["id"], "max_tokens": MAX_TOKENS[model],
        "messages": [{"role": "user", "content": inhoud}],
        "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def lees_paar(tekst: str) -> dict:
    """Het antwoord in vaste woorden; wat daarbuiten valt is twijfel, een onbekende verandering valt weg."""
    leeg = {"stempel": None, "afgeleid": "twijfel", "veranderingen": [], "wat_echt": "", "uitleg": ""}
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return leeg
    if not isinstance(d, dict):
        return leeg
    veranderingen = d.get("veranderingen") if isinstance(d.get("veranderingen"), list) else []
    return {"stempel": d["stempel"] if isinstance(d.get("stempel"), bool) else None,
            "afgeleid": d.get("afgeleid") if d.get("afgeleid") in AFGELEID else "twijfel",
            "veranderingen": [v for v in veranderingen if v in VERANDERINGEN],
            "wat_echt": " ".join(str(d.get("wat_echt") or "").split()),
            "uitleg": " ".join(str(d.get("uitleg") or "").split())}


def telling(paren: list[dict], antwoorden: dict[str, dict[str, dict]], labels: dict[str, str]) -> dict:
    """Per model, op de echte paren (zonder *geen bron*):
    - waar het virale beeld van het origineel komt: hoeveel gekoppeld, en hoeveel met het juiste woord voor de
      verandering (precies dat woord, geen synoniem);
    - *andere foto* (dezelfde gebeurtenis, een andere opname): het juiste antwoord is *nee*;
    - *valse bewerking*: bij een echt beeld in een andere context toch *bewerkt* of *AI-gemaakt*;
    en van de schijnparen hoeveel *nee*. Weigert zolang een echt paar geen label heeft."""
    open_ = [p["id"] for p in paren if p["soort"] == "paar" and p["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} paar/paren zonder label in {LABELS.name}")
    uit = {}
    for model, antw in antwoorden.items():
        t = collections.Counter()
        for p in paren:
            a = antw.get(p["id"])
            if a is None:
                continue
            if p["soort"] == "schijn":
                t["schijn"] += 1
                t["schijn nee"] += a["afgeleid"] == "nee"
                continue
            label = labels[p["id"]]
            if label == "geen bron":
                continue
            if label == "andere foto":
                t["andere foto"] += 1
                t["andere foto nee"] += a["afgeleid"] == "nee"
                continue
            t["paren"] += 1
            t["gekoppeld"] += a["afgeleid"] == "ja"
            t["verandering goed"] += a["afgeleid"] == "ja" and label in a["veranderingen"]
            if label == "andere context":
                t["andere context"] += 1
                t["valse bewerking"] += bool({"bewerkt", "AI-gemaakt"} & set(a["veranderingen"]))
        uit[model] = {k: t[k] for k in ("paren", "gekoppeld", "verandering goed", "andere context", "valse bewerking",
                                         "andere foto", "andere foto nee", "schijn", "schijn nee")}
    return uit


_BRONNEN = (
    ("persbureau", r"\b(reuters|associated press|\bap\b|afp|agence france|efe\b|europa press|anp\b|dpa\b|getty|epa\b|"
                   r"xinhua|anadolu|ansa\b|lusa\b|belga\b)"),
    ("beeldbank", r"\b(shutterstock|alamy|istock|adobe stock|dreamstime|depositphotos|pexels|unsplash|pixabay)"),
    ("archief", r"\b(wayback|archive\.org|archive\.today|archive\.ph)"),
    ("sociale media", r"\b(facebook|twitter|instagram|tiktok|youtube|telegram|whatsapp|reddit|threads|bluesky)"),
    ("media", r"\b(el país|el pais|el mundo|bbc|cnn|new york times|guardian|washington post|le monde|nos\b|vrt|"
              r"periódico|periodico|diario|newspaper|krant|tv\b|televisi|canal|channel|news|noticias|nieuws)"),
)


def bron_van(context: str) -> str:
    """Waar het origineel vandaan komt, uit de tekst eromheen: het eerste soort dat genoemd wordt, in deze volgorde."""
    tekst = (context or "").lower()
    for soort, patroon in _BRONNEN:
        if re.search(patroon, tekst):
            return soort
    return "onbekend"


# --- de bestanden, de database en het netwerk ----------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict], toevoegen: bool = False) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a" if toevoegen else "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen)


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    return json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}


def _context() -> dict[str, str]:  # pragma: no cover - een bestand
    """Per beeld de tekst eromheen in het artikel: alt, bijschrift, ervoor en erna."""
    uit = {}
    for r in _jsonl(WORTEL / "data" / "beeldoogst" / "beelden.jsonl"):
        delen = [r.get(k) or "" for k in ("onderschrift", "alt", "voor", "na")]
        uit[r["beeld"]] = " | ".join(d.strip() for d in delen if d.strip())
    return uit


def _claims() -> dict[str, dict]:  # pragma: no cover - de database
    import sqlite3

    from doublecheck.terugaanvoer import artikel

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    uit: dict[str, dict] = {}
    for url, oordeel, taal, tekst in conn.execute(
            "SELECT f.url, f.verdict_normalized, f.language, c.canonical_text FROM factcheck f JOIN claim c "
            "USING (claim_id) ORDER BY f.url, c.canonical_text"):
        uit.setdefault(artikel(url), {"tekst": " ".join(tekst.split()), "oordeel": oordeel, "taal": taal})
    conn.close()
    return uit


def _set() -> None:  # pragma: no cover - op de bestanden en de database
    pad = MAP / "paren.jsonl"
    if pad.exists():
        raise Weigering(f"{pad} ligt al vast")
    paren = kies_paren(_jsonl(WORTEL / "data" / "beeldoogst" / "rollen.jsonl"), _context(), _claims())
    alle = paren + schijnparen(paren)
    _schrijf(pad, alle)
    print(f"{len(paren)} paren op {len({p['host'] for p in paren})} sites, {len(alle) - len(paren)} schijnparen; "
          f"talen {dict(collections.Counter(p['taal'] for p in paren))}")


_ORIGINEEL = re.compile(r"(?i)origin|eerder|earlier|en realidad|in werkelijkheid|actually|in fact|archiv|revers|"
                        r"búsqueda inversa|omgekeerd|tineye|google lens|yandex|primera vez|first (posted|published|appeared)|"
                        r"foto(grafía)? (real|de)|photo (was|shows|from)|tomada|taken|captured|fecha|in 20\d\d|en 20\d\d")


def _teksten() -> None:  # pragma: no cover - netwerk
    """Per artikel de zinnen die over het origineel gaan, om het label te zetten; tijdelijk, tot `opruimen`."""
    from doublecheck.beeldindexmeting import Beleefd
    from doublecheck.screeningmeting import alineatekst

    pad = MAP / "teksten.jsonl"
    klaar = {r["artikel"] for r in _jsonl(pad)}
    web = Beleefd()
    for p in _jsonl(MAP / "paren.jsonl"):
        if p["soort"] != "paar" or p["artikel"] in klaar:
            continue
        zinnen, status = [], "robots"
        if web.mag(p["artikel"]):
            antwoord = web._vraag(p["artikel"])
            status = getattr(antwoord, "status_code", "fout")
            if antwoord is not None and antwoord.status_code == 200:
                tekst = alineatekst(antwoord.text)
                zinnen = [z.strip() for z in re.split(r"(?<=[.!?])\s+", tekst) if _ORIGINEEL.search(z)][:8]
        _schrijf(pad, [{"artikel": p["artikel"], "status": status, "zinnen": zinnen}], toevoegen=True)
        klaar.add(p["artikel"])
    print(f"{len(klaar)} artikelen")


def _lezen() -> None:  # pragma: no cover - bestanden
    teksten = {r["artikel"]: r for r in _jsonl(MAP / "teksten.jsonl")}
    labels = _labels()
    for p in _jsonl(MAP / "paren.jsonl"):
        if p["soort"] != "paar" or p["id"] in labels:
            continue
        t = teksten.get(p["artikel"], {})
        print(f"\n[{p['id']}] {p['host']} · {p['oordeel']} · {p['taal']}\n  CLAIM: {p['claim'][:250]}\n"
              f"  RONDOM B: {p['context_origineel'][:300]}")
        for z in t.get("zinnen", []):
            print(f"  - {z[:300]}")


def _paarbeelden(web, p: dict) -> tuple[bytes | None, bytes | None]:  # pragma: no cover - netwerk
    return web.beeld(p["viraal"]), web.beeld(p["origineel"])


def _lokaal() -> None:  # pragma: no cover - netwerk en rekenen
    """Per paar en schijnpaar hoe dicht de twee beelden bij elkaar liggen: de kleinste PDQ-afstand (ook over de
    uitsneden), de cosinus van DINOv2 en de SIFT-punten die met één vorm passen. Alleen getallen."""
    import numpy as np

    from doublecheck import beeldvraag as bv
    from doublecheck.beeldindexmeting import Beleefd

    pad = MAP / "lokaal.jsonl"
    klaar = {r["id"] for r in _jsonl(pad)}
    web = Beleefd()
    for p in _jsonl(MAP / "paren.jsonl"):
        if p["id"] in klaar:
            continue
        a, b = _paarbeelden(web, p)
        if a is None or b is None:
            _schrijf(pad, [{"id": p["id"], "soort": p["soort"], "fout": "beeld niet te halen"}], toevoegen=True)
            continue
        try:
            va, vb = bv.vraagkenmerken(a), bv.indexkenmerken(b)
            pdq = min(bin(int(x, 16) ^ int(y, 16)).count("1") for x in va["pdq"] for y in vb["pdq"])
            v1, v2 = bv.vector_uit_tekst(va["vectoren"][0]), bv.vector_uit_tekst(vb["vector"])
            dino = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
            punten, dekking = bv.puntvergelijking(bv.puntkenmerken(a), bv.puntkenmerken(b))
            rij = {"id": p["id"], "soort": p["soort"], "pdq": pdq, "dino": round(dino, 4), "punten": int(punten),
                   "dekking": round(float(dekking), 3)}
        except Exception as e:   # kapot beeld: alleen de soort fout (DR3)
            rij = {"id": p["id"], "soort": p["soort"], "fout": type(e).__name__}
        del a, b
        _schrijf(pad, [rij], toevoegen=True)
    rijen = _jsonl(pad)
    for soort in ("paar", "schijn"):
        r = [x for x in rijen if x["soort"] == soort and "fout" not in x]
        if r:
            print(f"{soort}: n {len(r)}, PDQ ≤31 {sum(x['pdq'] <= 31 for x in r)}, DINOv2 ≥0,80 "
                  f"{sum(x['dino'] >= 0.80 for x in r)}, SIFT ≥15 punten {sum(x['punten'] >= 15 for x in r)}")


def _uitgegeven() -> float:  # pragma: no cover - een bestand
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in _jsonl(MAP / "batches.jsonl"))


def _indienen(proef: int | None) -> None:  # pragma: no cover - netwerk en de Batch API
    import anthropic

    from doublecheck.beeldindexmeting import Beleefd
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    gevraagd = {i for b in _jsonl(MAP / "batches.jsonl") for i in b["ids"]}
    labels = _labels()
    # een paar dat ik als *geen bron* las, telt niet mee en kost dan alleen geld
    werk = [p for p in _jsonl(MAP / "paren.jsonl") if f"sonnet-{p['id'].split(':', 1)[1]}" not in gevraagd
            and labels.get(p["id"]) != "geen bron"][:proef]
    geschat = sum(SCHATTING.values()) * len(werk)
    if _uitgegeven() + geschat > GRENS:
        raise Weigering(f"${_uitgegeven() + geschat:.2f} gaat over de grens van ${GRENS:.2f}")
    web, verzoeken, dood = Beleefd(), collections.defaultdict(list), 0
    for p in werk:
        a, b = _paarbeelden(web, p)
        if a is None or b is None:
            dood += 1
            continue
        for model in MODELLEN_V1:
            verzoeken[model].append(paarverzoek(p, a, b, model))
        del a, b
    for model, lijst in verzoeken.items():
        batch = client.messages.batches.create(requests=lijst)
        _schrijf(MAP / "batches.jsonl", [{"id": batch.id, "model": model, "versie": VERSIE, "aantal": len(lijst),
                                          "schatting": round(SCHATTING[model] * len(lijst), 4),
                                          "ids": [v["custom_id"] for v in lijst]}], toevoegen=True)
        print(f"batch {batch.id}: {model}, {len(lijst)} paren")
    print(f"{dood} paren zonder beeld; geschat ${geschat:.2f}, samen ${_uitgegeven():.2f} van ${GRENS:.2f}")


def _ophalen() -> None:  # pragma: no cover - de Batch API
    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    ids = {p["id"].split(":", 1)[1]: p["id"] for p in _jsonl(MAP / "paren.jsonl")}
    batches = _jsonl(MAP / "batches.jsonl")
    for b in batches:
        if b.get("werkelijk") is not None:
            continue
        status = client.messages.batches.retrieve(b["id"])
        if status.processing_status != "ended":
            print(f"batch {b['id']} ({b['model']}): {status.processing_status}, {status.request_counts}")
            continue
        prijs, kosten, nieuw = MODELLEN[b["model"]], 0.0, []
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                nieuw.append({"id": ids[r.custom_id.split("-", 1)[1]], "model": b["model"], "fout": r.result.type})
                continue
            msg = r.result.message
            k = (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            kosten += k
            tekst = "".join(getattr(blok, "text", "") or "" for blok in msg.content if getattr(blok, "type", "") == "text")
            nieuw.append({"id": ids[r.custom_id.split("-", 1)[1]], "model": b["model"], "versie": b["versie"],
                          "kosten": round(k, 5), "stop": msg.stop_reason, **lees_paar(tekst)})
        _schrijf(MAP / "antwoorden.jsonl", nieuw, toevoegen=True)
        b["werkelijk"] = round(kosten, 4)
        print(f"batch {b['id']} ({b['model']}): {len(nieuw)} antwoorden, ${kosten:.3f}")
    _schrijf(MAP / "batches.jsonl", batches)
    print(f"samen ${_uitgegeven():.3f} van ${GRENS:.2f}")


def _tellen() -> None:  # pragma: no cover - bestanden
    paren = _jsonl(MAP / "paren.jsonl")
    antwoorden: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    kosten = collections.Counter()
    for r in _jsonl(MAP / "antwoorden.jsonl"):
        if "fout" not in r:
            antwoorden[r["model"]][r["id"]] = r
            kosten[r["model"]] += r["kosten"]
    uit = telling(paren, antwoorden, _labels())
    for model in uit:
        n = len(antwoorden[model])
        uit[model]["kosten per paar"] = round(kosten[model] / n, 4) if n else None
        uit[model]["stempel gezien"] = sum(a["stempel"] is True for a in antwoorden[model].values())
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def _bronnen() -> None:  # pragma: no cover - bestanden
    """V2: over alle artikelen met een viraal beeld en een origineel, waar het origineel vandaan komt."""
    context = _context()
    tel, voorbeelden = collections.Counter(), collections.defaultdict(list)
    for r in _jsonl(WORTEL / "data" / "beeldoogst" / "rollen.jsonl"):
        if "viraal" not in r["rollen"] or "origineel" not in r["rollen"]:
            continue
        b = next(b for b, rol in zip(r["beelden"], r["rollen"]) if rol == "origineel")
        soort = bron_van(context.get(b, ""))
        tel[soort] += 1
        if len(voorbeelden[soort]) < 8:
            voorbeelden[soort].append(context.get(b, "")[:200])
    n = sum(tel.values())
    print(f"{n} originelen: " + ", ".join(f"{s} {c} ({100 * c / n:.0f}%)" for s, c in tel.most_common()))
    for s, v in voorbeelden.items():
        print(f"\n{s}:")
        for x in v:
            print(f"  - {x}")


def _opruimen() -> None:  # pragma: no cover - een bestand
    (MAP / "teksten.jsonl").unlink(missing_ok=True)
    print("de zinnen uit de artikelen zijn weg")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Het virale beeld en het origineel (PLAN #32.69, V1 en V2)")
    parser.add_argument("stap", choices=("set", "teksten", "lezen", "lokaal", "indienen", "ophalen", "tellen",
                                         "bronnen", "opruimen"))
    parser.add_argument("--proef", type=int, default=None)
    args = parser.parse_args()
    {"set": _set, "teksten": _teksten, "lezen": _lezen, "lokaal": _lokaal, "indienen": lambda: _indienen(args.proef),
     "ophalen": _ophalen, "tellen": _tellen, "bronnen": _bronnen, "opruimen": _opruimen}[args.stap]()


if __name__ == "__main__":
    main()
