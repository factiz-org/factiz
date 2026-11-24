"""De feitenstap (feitstap-v1 tot en met v3, B44): ophalen uit de vastgestelde feiten en de vraag met twee sleutels voor stand 0 en 10; de kern van de controle (PLAN #32.7c)."""

from __future__ import annotations

import json


VERSIE = "feitstap-v1"


VLOER = 0.60


N_KANDIDATEN = 3


SLEUTELS = ("A", "B")


def kandidaten(vector, index, vloer: float = VLOER, n: int = N_KANDIDATEN) -> list[tuple[str, float]]:
    """De feiten met een zin boven de vloer, elk één keer met zijn beste gelijkenis,
    de beste eerst. `index`: (zinnen als (feit, tekst), genormaliseerde matrix)."""
    zinnen, matrix = index
    beste: dict[str, float] = {}
    for (feit, _), s in zip(zinnen, matrix @ vector):
        if s >= vloer and s > beste.get(feit, -1.0):
            beste[feit] = float(s)
    return sorted(beste.items(), key=lambda x: -x[1])[:n]


SYSTEEM = ("You compare a message with established facts. You decide only whether the main claim of the message "
           "is one of these facts, contradicts one of them, or neither.")


VRAAG = """Established facts (each confirmed by at least four independent sources):
{feiten}

Message:
{bericht}

Does the main claim of the message confirm one of these facts, contradict one of them, or neither?
- "bevestigt": the main claim of the message is the same fact: the same event, actors, place, time and numbers. A paraphrase or a translation counts.
- "spreekt tegen": the main claim cannot be true if the fact is true: another date, place, actor or number for the same fact, or its opposite.
- "geen": anything else, including a message on the same topic that makes a different claim, a claim that only partly overlaps, and a message that uses the fact only as a lead-in to another claim.
Give the number of the fact (V1, V2, ...) for "bevestigt" or "spreekt tegen", and an empty string for "geen". Give the reason in one short Dutch sentence."""


VRAAG_V2 = """Established facts (each confirmed by at least four independent sources):
{feiten}

Message:
{bericht}

Does the main claim of the message confirm one of these facts, contradict one of them, or neither?
- "bevestigt": the main claim of the message is the same fact: the same event, actors, place, time and numbers. A paraphrase, a translation or a shorter version counts. Every concrete detail in the message (a date, a time of day, a number, a name, a place) must be stated in the fact or follow from it. If the message adds a concrete detail that the fact does not state, the answer is not "bevestigt", even if that detail may be true.
- "spreekt tegen": the message cannot be true if the fact, exactly as written above, is true: another date, place, actor or number for the same fact, or its opposite. Decide this on what the fact itself states, not on your own knowledge: a false detail that the fact does not mention is not a contradiction of the fact.
- "geen": anything else, including a message that adds a concrete detail the fact does not state, whether that detail is true or false, a message on the same topic that makes a different claim, a claim that only partly overlaps, and a message that uses the fact only as a lead-in to another claim.
Give the number of the fact (V1, V2, ...) for "bevestigt" or "spreekt tegen", and an empty string for "geen". Give the reason in one short Dutch sentence."""


VRAAG_V3B = VRAAG_V2.replace("Give the reason in one short Dutch sentence.",
                             "Give the reason in one short English sentence.")


_SCHEMA = {"type": "object",
           "properties": {"richting": {"type": "string", "enum": ["bevestigt", "spreekt tegen", "geen"]},
                          "feit": {"type": "string"}, "waarom": {"type": "string"}},
           "required": ["richting", "feit", "waarom"], "additionalProperties": False}


def vraag(bericht: str, feiten: list[tuple[str, str]], sjabloon: str = VRAAG) -> str:
    """De vraag aan het model; `feiten`: (feit, zin), in de volgorde van V1, V2, ..."""
    return sjabloon.format(feiten="\n".join(f"[V{i}] {zin}" for i, (_, zin) in enumerate(feiten, 1)), bericht=bericht)


def lees_feitoordeel(tekst: str, n: int) -> tuple[str, int | None]:
    """(richting, nummer van het feit) uit het JSON-antwoord; alles wat niet
    precies past (geen JSON, een andere richting, een V die er niet was) is *geen*."""
    try:
        d = json.loads(tekst)
    except json.JSONDecodeError:
        return "geen", None
    if not isinstance(d, dict) or d.get("richting") not in ("bevestigt", "spreekt tegen"):
        return "geen", None
    v = str(d.get("feit") or "").strip().upper()
    if not (v.startswith("V") and v[1:].isdigit() and 1 <= int(v[1:]) <= n):
        return "geen", None
    return d["richting"], int(v[1:])


def volgorde(kandidaten: list, sleutel: str) -> list[str]:
    """De feiten zoals ze in de vraag staan: A de beste eerst, B omgekeerd."""
    feiten = [f for f, _ in kandidaten]
    return feiten[::-1] if sleutel == "B" else feiten


def verzoek_id(stuk_id: str, sleutel: str) -> str:
    return f"{stuk_id}__{sleutel}"


def twee_sleutels(a: dict[str, dict], b: dict[str, dict]) -> dict[str, dict]:
    """0 of 10 alleen als A en B dezelfde richting en hetzelfde feit geven; anders *geen*."""
    geen = {"richting": "geen", "feit": None}
    uit = {}
    for i, x in a.items():
        y = b.get(i)
        samen = y and x["richting"] == y["richting"] and x.get("feit") == y.get("feit") and x["richting"] != "geen"
        uit[i] = x if samen else geen
    return uit


def _verzoek(custom_id: str, model: str, systeem: str | None, tekst: str, schema: dict,
             max_tokens: int = 1_000) -> dict:  # pragma: no cover - vorm van de Batch API
    from doublecheck.modellen import MODELLEN

    params = {"model": MODELLEN[model]["id"], "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": tekst}],
              "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}
    if systeem:
        params["system"] = systeem
    return {"custom_id": custom_id, "params": params}


def _index():  # pragma: no cover - met het model
    import numpy as np

    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.feitenbasis import laagformuleringen, lees_kern

    kern = lees_kern()
    zinnen = laagformuleringen(kern) + [(f["id"], f["zin"]) for f in kern]
    versie = load_config(None).model_versions.text_embedding
    vingers = fingerprint_texts([t for _, t in zinnen], versie)
    return (zinnen, np.stack([fp.vector for fp in vingers])), versie


def zinnen_van_feiten() -> dict[str, str]:  # pragma: no cover - op de kern
    from doublecheck.feitenbasis import lees_kern

    return {f["id"]: f["zin"] for f in lees_kern()}


# Wat de controle per versie gebruikt; de meting (`feitstap.VERSIES`) voegt haar bestanden en budgetten toe.
KERN = {
    "v1": {"naam": VERSIE, "vloer": VLOER, "vraag": VRAAG},
    "v2": {"naam": "feitstap-v2", "vloer": 0.55, "vraag": VRAAG_V2},
    "v3": {"naam": "feitstap-v3", "vloer": 0.55, "vraag": VRAAG_V2, "vraag_b": VRAAG_V3B},
}
