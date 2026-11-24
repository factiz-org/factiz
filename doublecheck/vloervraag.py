"""De vloervraag (B50, vloer-v1 en vloer-v2): twee vragen zonder zoeken bij twijfel; de kern van de controle (PLAN #32.7c)."""

from __future__ import annotations

import json


MODEL = "haiku"


DUIDELIJK = "clearly false"


NIET = "not clearly false"


SLEUTELS = ("A", "B")


VRAGEN = {
    "A": """Message:
{bericht}

Without searching: is the main claim of this message clearly false according to well-established knowledge that a \
well-informed adult would know, and that has not changed in recent years?
- Answer "clearly false" only if the claim contradicts such knowledge outright: an impossible number, the wrong \
country, planet or disease, or the opposite of a well-known fact.
- Answer "not clearly false" if it could be true, if it depends on a recent event, a local fact or a detail you cannot \
know, if it is an opinion or a prediction, or if you are not sure.
Give the reason first, in one short English sentence.""",
    "B": """Would a well-informed person, without looking anything up, immediately recognise the claim below as false, \
because it contradicts long-established common knowledge? Recent events, local news, exact figures, opinions and \
anything you are unsure about do not count: then the answer is "not clearly false".

Claim:
{bericht}

Answer "clearly false" or "not clearly false", with one short English reason first.""",
}


_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["waarom", "oordeel"],
           "properties": {"waarom": {"type": "string"}, "oordeel": {"type": "string", "enum": [DUIDELIJK, NIET]}}}


def verzoek(tekst: str, sleutel: str, config) -> dict:
    """De vraag van één sleutel, zonder zoeken, met vaste JSON."""
    from doublecheck.modellen import MODELLEN

    del config  # de vraag hangt niet af van de controle; Haiku staat vast in `MODEL`
    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 400,
            "messages": [{"role": "user", "content": VRAGEN[sleutel].format(bericht=tekst[:2000])}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees_oordeel(tekst: str) -> str:
    """Wat niet precies past, is niet duidelijk onwaar."""
    try:
        oordeel = json.loads(tekst).get("oordeel")
    except (json.JSONDecodeError, AttributeError):
        return NIET
    return oordeel if oordeel in (DUIDELIJK, NIET) else NIET
