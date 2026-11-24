"""Wat een foto toont, in woorden (beschrijving-v1, PLAN #32.17): de vraag die een beeld beschrijft zoals een
factchecker het virale beeld beschrijft, met twee zoekvragen; de kern van de controle (PLAN #32.7c).

Alleen het beeld gaat mee, nooit de tekst van de post: die is de eerste sleutel. Het beeld wordt in het geheugen
verkleind tot een JPEG en verlaat deze module alleen in de vraag zelf (DR3). In het product pas na een besluit van de
PO over het beeld naar het model (B43, REQUIREMENTS §9).
"""

from __future__ import annotations

import base64
import io
import json

MAX_ZIJDE = 1024          # genoeg om te zien wat er staat; ~1.000 beeldtokens
MAX_ZOEKVRAGEN = 2


VRAAG_V1 = """This image was shared online, perhaps as a screenshot of a post. Describe in one English sentence what \
the photo (or the video still) in it shows, the way a fact-checker describes a viral image ("Photo shows ...", \
"Video shows ..."). Also give {m} short English search queries a fact-checker would use to find a fact-check of this \
image.

Rules:
- Describe only what is visible: the scene, the people by what they do and wear, objects, the setting, the kind of \
event.
- Text that is part of the scene itself (a sign, a banner, a label, a caption burned into the picture) may be used. \
Do not use the text of the post around the photo (the caption, the user name, the comments), neither in the \
description nor in the search queries: build both only from what the photo itself shows.
- Name a person or a place only if the name is written in the image. Never identify anyone by their face.
- Do not judge whether anything is true, and do not guess what the post claims.
- If the image contains no photo or video still at all (only text, a chart or a document), set "foto" to false and \
leave the description and the queries empty."""


VRAGEN = {"beschrijving-v1": {"model": "haiku", "vraag": VRAAG_V1.format(m=MAX_ZOEKVRAGEN)}}


_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["foto", "beschrijving", "zoekvragen"],
           "properties": {"foto": {"type": "boolean"}, "beschrijving": {"type": "string"},
                          "zoekvragen": {"type": "array", "items": {"type": "string"}}}}


def _jpeg(beeld: bytes) -> str:
    """Het beeld verkleind tot hoogstens `MAX_ZIJDE` pixels, als JPEG in base64; alleen in het geheugen."""
    from PIL import Image

    with Image.open(io.BytesIO(beeld)) as b:
        klein = b.convert("RGB")
    klein.thumbnail((MAX_ZIJDE, MAX_ZIJDE))
    buf = io.BytesIO()
    klein.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def verzoek(beeld: bytes, versie: str = "beschrijving-v1") -> dict:
    """De vraag aan het model: het beeld en de vaste vraag, zonder zoeken, met vaste JSON."""
    from doublecheck.modellen import MODELLEN

    if versie not in VRAGEN:
        raise ValueError(f"beschrijving {versie!r} bestaat niet in de code")
    v = VRAGEN[versie]
    inhoud = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(beeld)}},
              {"type": "text", "text": v["vraag"]}]
    return {"model": MODELLEN[v["model"]]["id"], "max_tokens": 400, "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees_beschrijving(tekst: str) -> dict | None:
    """De beschrijving met hoogstens twee zoekvragen uit het JSON-antwoord; onleesbaar, zonder foto of leeg is geen
    beschrijving."""
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("foto") is not True:
        return None
    beschrijving, vragen = d.get("beschrijving"), d.get("zoekvragen")
    if not isinstance(beschrijving, str) or not isinstance(vragen, list):
        return None
    beschrijving = " ".join(beschrijving.split())
    if not beschrijving:
        return None
    vragen = [" ".join(q.split()) for q in vragen if isinstance(q, str)]
    return {"beschrijving": beschrijving, "zoekvragen": [q for q in vragen if q][:MAX_ZOEKVRAGEN]}


def als_beweringen(beschrijving: dict | None) -> list[dict]:
    """De beschrijving in de vorm van "beweringen eerst", zodat hetzelfde geheugen ermee zoekt."""
    if not beschrijving:
        return []
    return [{"bewering": beschrijving["beschrijving"], "zoekvragen": list(beschrijving["zoekvragen"])}]
