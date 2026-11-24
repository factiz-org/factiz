"""Signaal 2 van B62, de voormeting: hoe vaak draagt een nepbeeld het merk van een nieuwsmedium (logo, sjabloon, naam)?
(PLAN #32.58, PO 2026-11-07: "altijd plakken ze dan zo'n logo erin"; "graag").

Haiku kijkt naar de bekende nepbeelden van de metingen (Engels N van §220, Spaans, Portugees en Duits N van §234) en zegt
alleen welk nieuwsmerk het beeld draagt. De beelden alleen in het geheugen (B35), via de Batch API op openbare beelden.
Daarna per beeld met een merk: wat Factiz er toen van zei.

    python -m doublecheck.merkinbeeld vragen|tellen
"""

from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "merkinbeeld"
MODEL = "haiku"
METINGEN = ("32.41", "32.46-beeld-es", "32.46-beeld-pt", "32.46-beeld-de")
HOE = ("logo", "sjabloon", "naam", "geen")

SYSTEEM = "You describe how an image presents itself. You do not judge whether it is true."
VRAAG = """Does this image present itself as coming from a news outlet or broadcaster? Look for a logo, a station or
channel bug, a recognisable template (the graphics, colours and layout of a known outlet), or the outlet's name shown as
the source. Give the outlet's name (for example "Euronews", "BBC News", "DW", "Al Jazeera", "CNN"), and how it shows:
"logo", "sjabloon" (template), "naam" (only the name as text) or "geen" (no outlet, then an empty name). A fact-checker's
own stamp or watermark (such as "FALSE" or the fact-checker's logo) is not the outlet."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["merk", "hoe"],
          "properties": {"merk": {"type": "string"}, "hoe": {"type": "string", "enum": list(HOE)}}}


def verzoek(beeld: bytes, mime: str) -> dict:
    from doublecheck.modellen import MODELLEN

    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 800, "system": SYSTEEM,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": base64.b64encode(beeld).decode()}},
                {"type": "text", "text": VRAAG}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}}


def lees(tekst: str) -> dict:
    """Het merk en hoe; zonder geldige *hoe* of zonder naam telt het als geen merk (twijfel versoepelt nooit)."""
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return {"merk": "", "hoe": "geen"}
    merk = (d.get("merk") or "").strip() if isinstance(d, dict) else ""
    hoe = d.get("hoe") if isinstance(d, dict) else None
    if hoe not in HOE or hoe == "geen" or not merk:
        return {"merk": "", "hoe": "geen"}
    return {"merk": merk, "hoe": hoe}


def medium(naam: str) -> tuple[str, tuple[str, ...]] | None:
    """Het medium uit `zoekcontrole.MEDIA` bij een naam (ongeacht hoofdletters en leestekens), met zijn eigen sites."""
    from doublecheck.zoekcontrole import MEDIA, kop_gewoon

    gewoon = kop_gewoon(naam or "")
    if not gewoon:
        return None
    for m, sites in MEDIA.items():
        if kop_gewoon(m) == gewoon:
            return m, sites
    return None


# --- de bestanden en het model -----------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _vragen() -> None:  # pragma: no cover - het netwerk en de Batch API op openbare beelden
    import anthropic

    from doublecheck.berichtcontrole import gebruik_uit
    from doublecheck.meting import beeld_of_reserve
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.uitkomsten import batch_met_grens
    from doublecheck.varianten import laad_sleutel
    from doublecheck.zoekcontrole import media_soort

    laad_sleutel()
    pad = UIT / "antwoorden.jsonl"
    klaar = {r["id"] for r in _jsonl(pad)}
    items = [s for m in METINGEN for s in _jsonl(WORTEL / "data" / "meting" / m / "set.jsonl")
             if s["set"] == "N" and s.get("beeld") and s["id"] not in klaar]
    verzoeken, ids = {}, {}
    for i, s in enumerate(items):
        beeld = beeld_of_reserve(s)
        if beeld is None:
            print(f"beeld niet bereikbaar: {s['id']}", flush=True)
            continue
        verzoeken[f"b{i:04d}"] = verzoek(beeld, media_soort(beeld))
        ids[f"b{i:04d}"] = s["id"]
    print(f"{len(verzoeken)} beelden naar Haiku", flush=True)
    gelezen = {}
    batch_met_grens(anthropic.Anthropic(max_retries=6), verzoeken, gelezen.update, aangemeld=lambda b, x: None,
                    afgemeld=lambda b: None)
    UIT.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for c, msg in gelezen.items():
            r = {"id": ids[c], **lees("".join(getattr(b, "text", "") or "" for b in msg.content)),
                 "kosten": round(kosten_batch(gebruik_uit(msg), MODEL), 6)}
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(gelezen)} beantwoord")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    antwoorden = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
    factiz = {r["id"]: r for m in METINGEN for r in _jsonl(WORTEL / "data" / "meting" / m / "antwoorden.jsonl")}
    met = [a for a in antwoorden.values() if a["hoe"] != "geen"]
    print(f"{len(met)} van {len(antwoorden)} nepbeelden dragen een nieuwsmerk; kosten ${sum(a['kosten'] for a in antwoorden.values()):.3f}")
    print("hoe:", Counter(a["hoe"] for a in met), "| merken:", Counter(a["merk"] for a in met).most_common(12))
    print("bekend medium:", sum(medium(a["merk"]) is not None for a in met))
    print("wat Factiz zei bij die beelden:", Counter((factiz[a["id"]]["kleur"] or "-", factiz[a["id"]]["uitkomst"])
                                                  for a in met if a["id"] in factiz).most_common(8))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Hoe vaak draagt een nepbeeld een nieuwsmerk? (PLAN #32.58)")
    parser.add_argument("stap", choices=("vragen", "tellen"))
    {"vragen": _vragen, "tellen": _tellen}[parser.parse_args().stap]()


if __name__ == "__main__":
    main()
