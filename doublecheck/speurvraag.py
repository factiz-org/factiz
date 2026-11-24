"""De zoekvragen vooraf (`speurvraag-v1`, B57, PLAN #32.41): een klein model bedenkt bij een bericht tot drie
zoekvragen zoals een factchecker (de eigen site van wie het bericht noemt, het echte nieuws, de bron zelf), zodat alles
tegelijk naar de zoekdienst kan en de lezer één keer leest. Het oordeelt nooit. De kern van de controle (#32.7c)."""

from __future__ import annotations

import base64
import json

VERSIE = "speurvraag-v1"
# Haiku 5.5 denkt eerst na: met 400 bleef in de proef van #32.41 de helft van de antwoorden leeg (max_tokens)
MAX_TOKENS = 1500
SYSTEEM = "You plan web searches for a fact-checker. You never judge whether a message is true."
VRAAG = """A message people share online{met_beeld}:
{bericht}

{datum}

Plan the web searches a fact-checker would do to find out whether its main claim is true, at most three, each of one kind:
- "eigen site": on the website of the outlet, person or institution the message names or presents as its source (by name or logo), to see whether they really published or said this; give that website's domain in site;
- "echt nieuws": the real event in plain words (who, what, where, when), without the message's own framing, to find what credible news media reported; if there is a photo, describe what it actually shows (place, people, event) rather than what the message says about it;
- "bron zelf": the report, statistics, law or statement the message relies on; give the domain of its official or institutional website in site if you know it, otherwise leave site empty.
Each search at most 12 words, in the language most likely to find it. If the message makes no checkable factual claim (a greeting, an opinion, an advertisement, a personal message), give an empty list."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verder_zoeken"], "properties": {
    "verder_zoeken": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["soort", "vraag", "site"],
        "properties": {"soort": {"type": "string", "enum": ["eigen site", "echt nieuws", "bron zelf"]},
                       "vraag": {"type": "string"}, "site": {"type": "string"}}}}}}


def verzoek(bericht: str, datum: str | None, model_id: str, beeld: bytes | None = None) -> dict:
    """De vraag aan het kleine model: het gemaskeerde bericht, en het zwartgemaakte beeld als dat mee mag (B55)."""
    from doublecheck.zoekcontrole import media_soort

    wanneer = f"It circulated around {datum}." if datum else "The date is unknown."
    tekst = VRAAG.format(met_beeld=", with the photo it shows" if beeld else "", bericht=bericht, datum=wanneer)
    inhoud = tekst if beeld is None else [
        {"type": "image", "source": {"type": "base64", "media_type": media_soort(beeld),
                                     "data": base64.b64encode(beeld).decode()}},
        {"type": "text", "text": tekst}]
    return {"model": model_id, "max_tokens": MAX_TOKENS, "system": SYSTEEM,
            "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}}


def lees(tekst: str) -> list[dict]:
    """De zoekvragen uit het antwoord, streng gelezen zoals de speurstap (`zoekcontrole.speurvragen`); onleesbaar is
    geen zoekvraag."""
    from doublecheck.zoekcontrole import speurvragen

    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return []
    return speurvragen(d.get("verder_zoeken")) if isinstance(d, dict) else []


def kosten(gebruik: dict) -> float:
    """Dollar voor één antwoord van Haiku zonder batchkorting: twee keer de batchprijs van `modellen.MODELLEN`."""
    from doublecheck.modellen import MODELLEN

    p = MODELLEN["haiku"]
    tokens = (gebruik.get("in", 0) * p["in"] + gebruik.get("uit", 0) * p["uit"]
              + gebruik.get("cache_lees", 0) * p["in"] * 0.1 + gebruik.get("cache_schrijf", 0) * p["in"] * 1.25)
    return 2 * tokens / 1e6
