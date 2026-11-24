"""Beweringen eerst (beweringen-v1, #32.6): de vraag die de beweringen met zoekvragen uit een screenshot haalt; de kern van de controle (PLAN #32.7c)."""

from __future__ import annotations

import json


TOP = 5


MAX_BEWERINGEN, MAX_ZOEKVRAGEN = 3, 2


EXTRACTIEVRAAG = """Below is the text that OCR read from a screenshot that people share online. The OCR may contain \
errors, and names, numbers and handles are masked.

List the factual claims this screenshot makes that a fact-checker could check, most important first, at most \
{n}. Write each claim as one clear English sentence, the way a fact-checker would summarise it ("Video shows \
...", "X said ...", "Photo of ..."), even if the screenshot is in another language. For each claim, also give \
{m} short alternative search queries in English. If there is no checkable claim, return an empty list.

Do not judge whether the claims are true. Do not add facts that are not in the text.

Screenshot text:
{tekst}"""


_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["beweringen"], "properties": {
    "beweringen": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["bewering", "zoekvragen"],
        "properties": {"bewering": {"type": "string"}, "zoekvragen": {"type": "array", "items": {"type": "string"}}}}}}}


def voeg_samen(lijsten: list[list[dict]], n: int = TOP) -> list[dict]:
    """Eén lijst uit de uitslagen van meerdere zoekvragen: per check de hoogste gelijkenis, de n beste."""
    beste: dict[str, dict] = {}
    for lijst in lijsten:
        for k in lijst:
            if k["claim"] not in beste or k["gelijkenis"] > beste[k["claim"]]["gelijkenis"]:
                beste[k["claim"]] = k
    return sorted(beste.values(), key=lambda k: -k["gelijkenis"])[:n]


def zoekvragen(tekst: str, gehaald: list[dict]) -> list[str]:
    """De tekst zelf, dan per bewering de bewering en haar zoekvragen; zonder lege en dubbele."""
    vragen = [tekst] + [v for b in gehaald for v in [b["bewering"], *b["zoekvragen"]]]
    uit: list[str] = []
    for v in vragen:
        v = " ".join(v.split())
        if v and v not in uit:
            uit.append(v)
    return uit


def lees_extractie(tekst: str) -> list[dict]:
    """De beweringen uit het JSON-antwoord, hoogstens drie met elk twee zoekvragen; onleesbaar is geen bewering."""
    try:
        beweringen = json.loads(tekst).get("beweringen")
    except (json.JSONDecodeError, AttributeError):
        return []
    if not isinstance(beweringen, list):
        return []
    return [{"bewering": str(b.get("bewering", "")), "zoekvragen": [str(v) for v in b.get("zoekvragen", [])][:MAX_ZOEKVRAGEN]}
            for b in beweringen[:MAX_BEWERINGEN] if isinstance(b, dict)]
