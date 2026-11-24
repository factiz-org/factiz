"""De controle per bericht, `POST /check` (B43, B44, B45; PLAN #31.12, SPECS E5.S4).

Iemand stuurt een tekst of een screenshot en krijgt één antwoord: het oordeel,
de stand op de schaal van 0 tot 10 en de bronnen. In deze volgorde:
1. een screenshot wordt op deze server gelezen (OCR per schrift) en niet bewaard;
2. opknippen en maskeren (`opknippen`): namen, nummers, adressen en handles eruit;
3. de database met factchecks doorzoeken en de kandidaten voor de lijst met
   vastgestelde feiten ophalen (`voorbereiden`, lokaal). Bij een screenshot
   eerst de beweringen (`beweringen-v1`, #32.6): Haiku haalt ze met zoekvragen
   uit de gemaskeerde tekst, en het geheugen zoekt met alles samen;
4. drie vragen tegelijk: de machine (vraag v4, de database en zoeken op het
   web) en de twee sleutels van `feitstap-v3` (`beoordeel`);
5. zegt de machine *onzeker* zonder gezocht te hebben, dan nog één keer, met de
   opdracht eerst te zoeken (`herkansing-v1`, §156). Sonnet 5.5 kan niet
   verplicht worden een zoekfunctie te gebruiken, dus het is een extra zin;
6. de stand op de schaal (B44, stand 0 dicht);
7. twijfelt de machine zonder bron bij een Engels bericht, de vloerstap (`vloer-v1`,
   B50): twee korte vragen zonder zoeken; zeggen beide dat de bewering duidelijk
   in strijd is met algemeen bekende kennis, dan *klopt niet* op de laag
   *algemene kennis*, hoogstens stand 3, alleen met een ijking van die laag;
8. bij rood of groen de vormvraag (`vorm-v2`) en de twee regels (#31.15, §159):
   een bericht over een bewering van een ander krijgt geen kleur, en een
   bewering over wat een beeld toont is zonder het beeld nooit groen.

Naar het model gaat alleen de gemaskeerde tekst, nooit het beeld (B43, DR3).
Niets naar schijf, log of cache; de kosten per dag zijn één getal per dag. In
dit pad nooit de Batch API, de Files API of zoeken dat zelf filtert (B43). Het
vaste deel van de vraag (de zoekfunctie en de systeemtekst) wordt gemarkeerd om
onthouden te worden; Sonnet krijgt precies de tekst van de metingen. De
categorie van `/resolve` wordt hier niet gezet (DR4).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache
from pathlib import Path

from doublecheck import feitvraag as f
from doublecheck import meter
from doublecheck import machinevraag as v
from doublecheck import beweringvraag as zh
from doublecheck.ocr import extract_text
from doublecheck.opknippen import opknippen

# DR3: de bibliotheken van het model loggen op debugniveau de hele vraag.
for _naam in ("anthropic", "httpx"):
    logging.getLogger(_naam).setLevel(logging.WARNING)

WORTEL = Path(__file__).resolve().parent.parent
# Dollar per miljoen tokens, zonder batchkorting: Sonnet 5.5 in, uit, uit de cache gelezen, in de cache gezet (5 min).
PRIJS = {"in": 2.0, "uit": 10.0, "cache_lees": 0.2, "cache_schrijf": 2.5}
# De vloerstap (B50, PLAN #32.0m): de vraag van de voormeting (§169), met het model waarmee hij gemeten is.
# `vloer-v2` (PLAN #32.0n, §170): dezelfde vragen, ook als de machine wel bronnen had.
VLOER = {"vloer-v1": {"model": "haiku", "met_bron": False}, "vloer-v2": {"model": "haiku", "met_bron": True}}
LAAG_VLOER = "algemene kennis"
# "Beweringen eerst" (PLAN #32.6): de vraag van V2 in P4 (§162), met het model waarmee hij gemeten is.
BEWERINGEN = {"beweringen-v1": {"model": "haiku", "vraag": zh.EXTRACTIEVRAAG}}
HERKANSING = {
    "herkansing-v1": ("You answered without searching the web. Search the web now for reliable sources about "
                      "this claim before you decide, and end with the same three lines."),
}
_GEEN_FEIT = {"richting": "geen", "feit": None}
# De vormvraag (PLAN #31.15): alleen over de vorm van het bericht, nooit over de waarheid.
VORMEN = {
    "vorm-v1": {
        "systeem": "You describe the form of a message. You never judge whether anything in it is true.",
        "vraag": """Message:
<message>
{bericht}
</message>

Answer two questions about the form of this message. Do not judge whether anything in it is true.

1. "vorm": does the message make its main claim itself, or is it about a claim made by someone else?
- "over een bewering": the message reports on, examines or questions a claim of another person or group without endorsing it: a news report on what a party says, alleges or accuses others of, keeping its distance; a fact-check or debunk; an investigation or analysis of allegations; or a question whether something is true ("Is it true that ...?").
- "zelf": everything else. This includes a message that states its claim as true, a message that backs its claim with an authority or a source ("doctors confirm that ...", "according to a leaked report ..."), a message that passes on a rumour as fact, and a message whose only checkable claim is that a person said, wrote or did something (a quote, a letter, a speech).
If in doubt, answer "zelf".

2. "beeld": is the main claim about what a photo, video, map or other image shows, so that it can only be checked by looking at that image ("video shows flooding in ...", "photo of ...", "this map shows ...")? Answer true or false.

Give the reason in one short English sentence first.""",
    },
    # Na de machine, met haar bewering: de regel gaat over de bewering die beoordeeld is.
    "vorm-v2": {
        "systeem": "You describe the form of a message. You never judge whether anything in it is true.",
        "vraag": """Message:
<message>
{bericht}
</message>

Claim found in this message (it may be written in Dutch):
<claim>
{bewering}
</claim>

Answer two questions about how the message presents this claim. Do not judge whether the claim is true.

1. "vorm": does the message itself assert this claim, or does it attribute the claim to someone else without endorsing it?
- "over een bewering": the message attributes the claim to another person or group and keeps its distance, or it refutes, examines or questions the claim: a news report on what a party says, alleges or accuses others of; a fact-check or debunk; an investigation of allegations; or a question whether the claim is true ("Is it true that ...?").
- "zelf": the message asserts the claim in its own voice. This includes a message that backs the claim with an authority or a source ("doctors confirm that ...", "according to a report ...", "..., reports X"), a message that passes on a rumour as fact, and a message that casts doubt on something in its own voice. If the claim is that a person said, wrote or did something, and the message states that as fact, the message asserts it.
If in doubt, answer "zelf".

2. "beeld": is the claim about what a photo, video, map or other image shows, so that it can only be checked by looking at that image ("video shows flooding in ...", "photo of ...", "this map shows ...")? Answer true or false.

Give the reason in one short English sentence first.""",
    },
}
_VORM_SCHEMA = {"type": "object",
                "properties": {"waarom": {"type": "string"},
                               "vorm": {"type": "string", "enum": ["zelf", "over een bewering"]},
                               "beeld": {"type": "boolean"}},
                "required": ["waarom", "vorm", "beeld"], "additionalProperties": False}
_GEEN_REGEL = {"vorm": "zelf", "beeld": False}

# De detailvraag van B48 (PLAN #32.3a): na *klopt*, met de passages die de machine citeerde.
DETAILS = {
    "detail-v1": {
        "systeem": "You compare a message with source passages. You never search and never add facts.",
        "vraag": """Message:
<message>
{bericht}
</message>

A fact-checker judged the main claim of this message to be true, with this note (it may be in Dutch):
<note>
{uitleg}
</note>

These are the passages it cited:
<passages>
{passages}
</passages>

Does the message state a specific detail (a date, a year, a number, a place, a name or a title) that one of these passages explicitly contradicts, by giving a different value for the same thing?
- Only report a detail if a passage states the other value in so many words. Do not report what the passages do not mention, rounding, or a different but compatible way of saying the same thing.
- "woorden": the wrong words exactly as they appear in the message; copy them.
- "juist": the correct value exactly as it appears in the passage.
- "bron": the number of the passage.
- "citaat": the shortest quote from that passage that gives the correct value.
Return an empty list if there is no such detail. Give the reason in one short English sentence first.""",
    },
}
DETAILS["detail-v2"] = {
    "systeem": DETAILS["detail-v1"]["systeem"],
    "vraag": DETAILS["detail-v1"]["vraag"].replace(
        "- Only report a detail if a passage states the other value in so many words. Do not report what the passages "
        "do not mention, rounding, or a different but compatible way of saying the same thing.",
        "- Only report a detail if a passage states the other value in so many words. Do not report what the passages "
        "do not mention, rounding, or a different but compatible way of saying the same thing. Two places can both be "
        "right (a village inside a district, a city inside a region): report a place only if the passage puts the "
        "same event somewhere that cannot include the place in the message.").replace(
        "Return an empty list if there is no such detail.",
        "Return an empty list if there is no such detail.\n\nSeparately, in \"notitie\": does the fact-checker's note "
        "itself say that a specific detail in the message is wrong (a date, number, place, name or title)? If so, "
        "\"afwijking\" is true, with the wrong words exactly as in the message and the correct value as the note gives "
        "it; otherwise false with empty strings."),
}
# De tweede stap van detail-v2: alleen als de notitie een fout detail noemt dat geen passage bewijst.
ZOEKVRAGEN = {
    "detail-v2": """Message:
<message>
{bericht}
</message>

A fact-checker noted that in this message "{woorden}" is wrong and should be "{juist}". Search for a reliable source that states the correct value, and cite the sentence from that source that states it.

Then answer with exactly two lines:
WOORDEN: the wrong words exactly as they appear in the message
JUIST: the correct value exactly as it appears in the source you cite
If no source states the correct value, answer with the single line: GEEN""",
}
ZOEKVRAGEN["detail-v3"] = ZOEKVRAGEN["detail-v2"].replace(
    "Search for a reliable source that states the correct value, and cite the sentence from that source that "
    "states it.",
    "Search for a reliable source that states the correct value. Then write one sentence that restates what that "
    "source says, including the correct value, so that your citation is the sentence of the source that contains "
    "the value. Do not cite a headline or an opening sentence that does not contain it.").replace(
    "JUIST: the correct value exactly as it appears in the source you cite",
    "JUIST: only the correct value, as short as possible (a date, a number, a place or a name), copied letter for "
    "letter from the source you cite")
# v3: dezelfde eerste stap; de zoekstap citeert de zin met de juiste waarde (ontwikkelhelft, 2026-10-28).
DETAILS["detail-v3"] = DETAILS["detail-v2"]
# De herkomstcontrole (PLAN #32.3e): staat het artikel op de site die het screenshot noemt? Eén zoekvraag,
# alleen op die site, tegelijk met de machine.
HERKOMST = {
    "herkomst-v1": {
        "systeem": "You check whether a news article shown in a screenshot appears on the website it claims to come "
                   "from. You search only that website, once.",
        "vraag": """Text read from a screenshot of a news article (names and numbers of private persons may be masked):
<message>
{bericht}
</message>

The screenshot presents this as an article from {site}. Search {site} once for this article, with its headline or its most specific words.

Then compare what you found with the screenshot. Answer one of:
- "gelijk": the article is on {site}, and the headline and every specific detail shown in the screenshot (names, numbers, dates, places, the author if shown) match it.
- "anders": an article on {site} is clearly the same story, but something shown in the screenshot differs from it.
- "niet gevonden": you found no article on {site} with this headline or this story.
The screenshot shows only the beginning of the article: what it does not show is not a difference. Rounding or a different but compatible wording is not a difference. If the search results do not show enough of the article to compare a detail, do not report it.

For each difference:
- "soort": "inhoud" for the headline or a fact (a name, number, date or place); "herkomst" for the author, the website or the date of publication;
- "woorden": the words exactly as they appear in the screenshot text;
- "juist": the words exactly as they appear on {site}.
Write one sentence per difference that restates what the article on {site} says, so that your citation is the sentence of the article that contains the correct words.

End with one line of JSON and nothing after it:
{{"uitkomst": "gelijk" or "anders" or "niet gevonden", "url": "the address of the article, or empty", "verschillen": [{{"soort": "...", "woorden": "...", "juist": "..."}}]}}""",
    },
}
# v2: een bijgewerkte kop met dezelfde feiten is geen verschil; op de ontwikkelhelft werd een echt artikel rood om
# "Alleged Airspace Violation" tegen "Violation of Airspace" (2026-10-28, PLAN #32.3e).
KOPREGEL = (" Sites often edit a headline after publication: a headline worded differently that states the same facts "
            "is not a difference. Report the headline only when it states a different fact (another name, number, "
            "date or place, or the opposite).")
_COMPATIBEL = "Rounding or a different but compatible wording is not a difference."
HERKOMST["herkomst-v2"] = {**HERKOMST["herkomst-v1"],
                           "vraag": HERKOMST["herkomst-v1"]["vraag"].replace(_COMPATIBEL, _COMPATIBEL + KOPREGEL)}
UITKOMSTEN = ("gelijk", "anders", "niet gevonden")
# Sites die de zoekfunctie van Anthropic niet toelaat: een vraag met `allowed_domains` op zo'n site weigert meteen.
# Gemeten met `python -m doublecheck.herkomst toegang`; daar loopt de herkomstcontrole niet.
# Gemeten 2026-10-28 op 39 nieuwssites; ook gewoon zoeken toont deze sites niet (BENCHMARK §175).
GEEN_TOEGANG: frozenset[str] = frozenset({
    "apnews.com",
    "bbc.co.uk",
    "bbc.com",
    "dw.com",
    "economist.com",
    "euractiv.com",
    "independent.co.uk",
    "latimes.com",
    "nytimes.com",
    "politico.com",
    "politico.eu",
    "reuters.com",
    "telegraph.co.uk",
    "theatlantic.com",
    "theguardian.com",
    "usatoday.com"})
_DOMEIN = re.compile(r"(?<![\w@.-])(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?![\w-])", re.I)
_DETAIL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["waarom", "details"], "properties": {
    "waarom": {"type": "string"},
    "details": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["woorden", "juist", "bron", "citaat"],
        "properties": {"woorden": {"type": "string"}, "juist": {"type": "string"}, "bron": {"type": "integer"},
                       "citaat": {"type": "string"}}}}}}
_DETAIL_SCHEMA_V2 = {**_DETAIL_SCHEMA, "required": ["waarom", "details", "notitie"], "properties": {
    **_DETAIL_SCHEMA["properties"],
    "notitie": {"type": "object", "additionalProperties": False, "required": ["afwijking", "woorden", "juist"],
                "properties": {"afwijking": {"type": "boolean"}, "woorden": {"type": "string"},
                               "juist": {"type": "string"}}}}}


class VersieFout(Exception):
    """De code wijkt af van de versies in config (DR6): de controle weigert."""


class Plafond(Exception):
    """Het dagplafond is bereikt: geen vraag aan een model."""


# --- het bericht ------------------------------------------------------------------------

def samenstellen(tekst: str | None, beeldtekst: str) -> str:
    """Een bijschrift en de tekst in het beeld samen, zoals in de route (#31.10)."""
    beeldtekst = " ".join(beeldtekst.split())
    if tekst and beeldtekst:
        return f"{tekst}\n[Text in the attached image: {beeldtekst}]"
    return beeldtekst or tekst or ""


def bericht_uit(tekst: str | None, beeld: bytes | None, ocr) -> str:
    """Wat naar het model mag: het beeld gelezen op deze server, alles opgeknipt en gemaskeerd."""
    beeldtekst = opknippen(extract_text(beeld, ocr).text) if beeld is not None else ""
    return samenstellen(opknippen(tekst) if tekst else None, beeldtekst)


# --- de vragen --------------------------------------------------------------------------

def machineverzoek(tekst: str, geheugen: list[dict], datum: str | None, config) -> dict:
    """De vraag aan de machine, gelijk aan die van de metingen; met de markering
    voor het vaste deel als `cache` aan staat."""
    c = config.berichtcontrole
    if c.vraag not in v.VRAGEN:
        raise VersieFout(f"vraag {c.vraag!r} bestaat niet in de code")
    s = {"id": "controle", "soort": "tekst", "tekst": tekst, "datum": datum}
    params = v.verzoek(s, geheugen, "a", [], "sonnet", c.vraag)["params"]
    if params["model"] != c.model_id:
        raise VersieFout(f"de code vraagt {params['model']}, config zegt {c.model_id}")
    return met_cache(params) if c.cache else params


def met_cache(params: dict) -> dict:
    """De markering op de systeemtekst: de zoekfunctie en de systeemtekst samen onthouden."""
    return {**params, "system": [{"type": "text", "text": params["system"], "cache_control": {"type": "ephemeral"}}]}


def met_herkansing(params: dict, zin: str) -> dict:
    """Dezelfde vraag met één zin erachter; het vaste deel blijft gelijk, dus onthouden."""
    bericht = params["messages"][0]
    inhoud = list(bericht["content"]) + [{"type": "text", "text": zin}]
    return {**params, "messages": [{**bericht, "content": inhoud}]}


def feitverzoek(tekst: str, kandidaten: list, sleutel: str, zinnen: dict[str, str], config) -> tuple[dict, list[str]]:
    """De vraag van één sleutel van `feitstap-v3`, en de feiten in de volgorde van die vraag."""
    c, v3 = config.berichtcontrole, f.KERN["v3"]
    if c.feitenstap != v3["naam"]:
        raise VersieFout(f"feitenstap {c.feitenstap!r}, de code heeft {v3['naam']!r}")
    volg = f.volgorde(kandidaten, sleutel)
    vraag = f.vraag(tekst, [(x, zinnen[x]) for x in volg], v3["vraag_b"] if sleutel == "B" else v3["vraag"])
    params = f._verzoek(f.verzoek_id("controle", sleutel), "sonnet", f.SYSTEEM, vraag, f._SCHEMA, 500)["params"]
    if params["model"] != c.model_id:
        raise VersieFout(f"de code vraagt {params['model']}, config zegt {c.model_id}")
    return params, volg


def vormverzoek(tekst: str, versie: str, config, bewering: str | None = None) -> dict:
    """De vormvraag: doet het bericht de bewering zelf, en gaat ze over wat een beeld
    toont? Zonder zoeken, met vaste JSON. Vanaf `vorm-v2` met de bewering van de machine."""
    if versie not in VORMEN:
        raise VersieFout(f"vormvraag {versie!r} bestaat niet in de code")
    vorm = VORMEN[versie]
    if "{bewering}" in vorm["vraag"] and not bewering:
        raise ValueError(f"{versie} vraagt de bewering van de machine")
    inhoud = vorm["vraag"].format(bericht=tekst, bewering=bewering or "")
    return {"model": config.berichtcontrole.model_id, "max_tokens": 400, "system": vorm["systeem"],
            "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _VORM_SCHEMA}}}


def _passages(bronnen: list[dict]) -> list[dict]:
    """De letterlijk geciteerde webpassages, in de volgorde waarin de detailvraag ze nummert."""
    return [b for b in bronnen if b.get("soort") == "web" and b.get("citaat")]


def detailverzoek(tekst: str, antwoord: dict, versie: str, config) -> dict:
    """De detailvraag (B48): noemt het bericht een detail dat een geciteerde passage anders noemt? Zonder zoeken."""
    if versie not in DETAILS:
        raise VersieFout(f"detailvraag {versie!r} bestaat niet in de code")
    d = DETAILS[versie]
    passages = "\n".join(f"[B{n}] {b['url']}: {' '.join(b['citaat'].split())}"
                          for n, b in enumerate(_passages(antwoord["bronnen"]), 1))
    inhoud = d["vraag"].format(bericht=tekst, uitleg=antwoord.get("uitleg") or "", passages=passages)
    return {"model": config.berichtcontrole.model_id, "max_tokens": 600, "system": d["systeem"],
            "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {
                "type": "json_schema", "schema": _DETAIL_SCHEMA_V2 if versie != "detail-v1" else _DETAIL_SCHEMA}}}


def zoekverzoek(tekst: str, notitie: dict, versie: str, config) -> dict:
    """De tweede stap (B48): zoek een bron die de juiste waarde noemt van het detail dat de notitie fout noemt."""
    if versie not in ZOEKVRAGEN:
        raise VersieFout(f"zoekstap {versie!r} bestaat niet in de code")
    inhoud = ZOEKVRAGEN[versie].format(bericht=tekst, woorden=notitie["woorden"], juist=notitie["juist"])
    return {"model": config.berichtcontrole.model_id, "max_tokens": 1_500,
            "messages": [{"role": "user", "content": inhoud}], "output_config": {"effort": "low"},
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]}


def herkomst_site(tekst: str, sites: dict[str, list], geblokkeerd: frozenset[str] | None = None) -> str | None:
    """Het eerste domein in de gelezen tekst dat in de lijst van #32.3c band goed heeft en dat de zoekfunctie
    toelaat; een platform telt nooit, een naam zonder domein ("BBC") in deze versie ook niet."""
    from doublecheck import bronnen as br

    geblokkeerd = GEEN_TOEGANG if geblokkeerd is None else geblokkeerd
    for m in _DOMEIN.finditer(tekst):
        b = br.beoordeel(m.group(1), sites)
        if b["band"] == "goed" and b["soort"] != "platform" and b["site"] not in geblokkeerd:
            return b["site"]
    return None


def herkomstverzoek(tekst: str, site: str, versie: str, config) -> dict:
    """De herkomstcontrole (PLAN #32.3e): één zoekvraag, alleen op `site`, binnen ZDR (geen zoeken dat zelf filtert)."""
    if versie not in HERKOMST:
        raise VersieFout(f"herkomstcontrole {versie!r} bestaat niet in de code")
    h = HERKOMST[versie]
    return {"model": config.berichtcontrole.model_id, "max_tokens": 1_500, "system": h["systeem"],
            "messages": [{"role": "user", "content": h["vraag"].format(bericht=tekst, site=site)}],
            "output_config": {"effort": "low"},
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1, "allowed_domains": [site]}]}


@lru_cache(maxsize=1)
def herkomstlijst() -> dict:  # pragma: no cover - een bestand
    """De lijst met betrouwbare bronnen van #32.3c; zonder lijst, of met een lijst van een andere versie of die niet
    meer vastligt, weigert de controle (#32.29, DR6)."""
    from doublecheck import bronnen as br
    from doublecheck import bronnenlijst as bl

    if not br.BESTAND.exists():
        raise VersieFout(f"de herkomstcontrole staat aan, maar {br.BESTAND.name} ontbreekt (#32.3c)")
    lijst = json.loads(br.BESTAND.read_text(encoding="utf-8"))
    if lijst.get("_meta", {}).get("versie") != br.VERSIE or not bl.vastgelegd(lijst):
        raise VersieFout(f"{br.BESTAND.name} is niet {br.VERSIE} of ligt niet vast (#32.29)")
    return lijst


# --- de antwoorden ----------------------------------------------------------------------

def kosten(gebruik: dict) -> float:
    """Dollar voor één antwoord, zonder batchkorting, met de cache en de zoekopdrachten."""
    tokens = sum(gebruik.get(k, 0) * PRIJS[k] for k in PRIJS)
    return tokens / 1e6 + gebruik.get("zoek", 0) * v.ZOEKEN_PER_1000 / 1000


def gebruik_uit(msg) -> dict:
    u = msg.usage
    zoek = getattr(u.server_tool_use, "web_search_requests", 0) if getattr(u, "server_tool_use", None) else 0
    return {"in": u.input_tokens, "uit": u.output_tokens, "cache_lees": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_schrijf": getattr(u, "cache_creation_input_tokens", 0) or 0, "zoek": zoek or 0}


def machineantwoord(msg, geheugen: list[dict]) -> dict:
    blokken = [b.model_dump() for b in msg.content]
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    oordeel, bewering, uitleg = v.lees_antwoord(tekst)
    gebruik = gebruik_uit(msg)
    return {"oordeel": oordeel, "bewering": bewering, "uitleg": uitleg, "bronnen": v.bronnen_uit(blokken, geheugen),
            "zoekverzoeken": gebruik["zoek"], "gebruik": gebruik, "kosten": kosten(gebruik)}


def feitantwoord(msg, volg: list[str]) -> dict:
    tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
    richting, nummer = f.lees_feitoordeel(tekst, len(volg))
    return {"richting": richting, "feit": volg[nummer - 1] if nummer else None, "kosten": kosten(gebruik_uit(msg))}


def herkansing_nodig(antwoord: dict) -> bool:
    return antwoord["oordeel"] == "onzeker" and antwoord["zoekverzoeken"] == 0


def stand_van(tabel: dict, machine: dict, feit_a: dict, feit_b: dict) -> tuple[dict, str | None, dict]:
    """De stand op de schaal: 10 alleen als beide sleutels hetzelfde feit bevestigen
    (B44); en wat de ijking over die klasse zegt (hoeveel berichten, aandeel waar)."""
    twee = f.twee_sleutels({"x": feit_a}, {"x": feit_b})["x"]
    feitstand = {"bevestigt": "waar", "spreekt tegen": "onwaar"}.get(twee["richting"])
    m = meter.meterstand(tabel, machine["oordeel"], meter.laag_van_antwoord(machine["bronnen"]), feitstand)
    return ({"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]},
            twee["feit"] if m["stand"] == 10 else None, {"n": m["n"], "aandeel waar": m["aandeel waar"]})


def lees_vorm(tekst: str) -> dict:
    """Het antwoord op de vormvraag; wat niet precies past, krijgt geen regel (zoals ronde 4)."""
    try:
        d = json.loads(tekst)
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or d.get("vorm") not in ("zelf", "over een bewering") \
            or not isinstance(d.get("beeld"), bool):
        return {**_GEEN_REGEL, "gelezen": False}
    return {"vorm": d["vorm"], "beeld": d["beeld"], "gelezen": True}


def kleur(stand: int, oordeel: str) -> str | None:
    """Rood en groen voor de gebruiker (B45): rood is 1 tot 3 op de schaal of *klopt
    niet*, groen is 7 of meer."""
    if stand <= 3 or oordeel == "klopt niet":
        return "rood"
    return "groen" if stand >= 7 else None


def regels(tabel: dict, oordeel: str, stand: dict, feit: str | None, bronnen: list[dict], vorm: dict) -> dict:
    """De twee regels van PLAN #31.15, ná het oordeel:
    - een bewering over wat een beeld toont is zonder het beeld nooit *klopt* of
      groen: dan *onzeker*, met de gemeten stand daarvan (5 bij elke bron);
    - een bericht over een bewering van een ander krijgt geen kleur; de stand
      blijft die van de bewering waarover het bericht gaat.
    Geen van beide maakt iets rood of groen. `bronnen`: die van de machine."""
    toegepast = []
    meting = None
    if vorm["beeld"] and (oordeel == "klopt" or stand["stand"] >= 7):
        m = meter.meterstand(tabel, "onzeker", meter.laag_van_antwoord(bronnen))
        oordeel, stand, feit = "onzeker", {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]}, None
        meting = {"n": m["n"], "aandeel waar": m["aandeel waar"]}
        toegepast.append("beeld")
    if vorm["vorm"] == "over een bewering":
        toegepast.append("over een bewering")
    k = None if "over een bewering" in toegepast else kleur(stand["stand"], oordeel)
    return {"oordeel": oordeel, "stand": stand, "feit": feit, "kleur": k, "regels": toegepast, "meting": meting}


def bronnen_voor(bronnen: list[dict], geheugen: list[dict]) -> list[dict]:
    """Een check uit de database als check van een redactie, met redactie en oordeel (DR5)."""
    per_claim = {k["claim"]: k for k in geheugen}
    uit = []
    for b in bronnen:
        if b["soort"] == "geheugen":
            k = per_claim.get(b.get("claim"), {})
            uit.append({"soort": "check van een redactie", "url": b.get("url"), "redactie": k.get("redactie"),
                        "oordeel": k.get("oordeel"), "datum": k.get("datum"), "titel": None, "citaat": None})
        else:
            uit.append({"soort": "web", "url": b.get("url"), "redactie": None, "oordeel": None, "datum": None,
                        "titel": b.get("titel"), "citaat": b.get("citaat")})
    return uit


# --- de eerste kring (PLAN #32.7a) -----------------------------------------------------------
# Raakt het bericht een check uit de database die één kant op wijst, dan dat antwoord meteen, zonder model:
# het snelle antwoord zat op 1.489 antwoorden nooit fout (BENCHMARK §172).
ONWAAR = ("onwaar", "misleidend")


def snel_oordeel(antwoord: dict) -> str | None:
    """*matched* met checks die allemaal één kant op wijzen; anders geen snel antwoord."""
    if antwoord.get("category") != "matched" or not antwoord.get("evidence"):
        return None
    oordelen = {c["verdict_normalized"] for c in antwoord["evidence"]["checks"]}
    if oordelen and oordelen <= set(ONWAAR):
        return "onwaar"
    return "waar" if oordelen == {"waar"} else None


def snel_antwoord(antwoord: dict, tabel: dict, tekst: str, tekstversie: str) -> dict | None:
    """De eerste kring: het antwoord van `/resolve` (als dict) met een check die één kant op wijst, in de vorm van
    `beoordeel`, met de stand van de laag *redactie* en de checks als bron (DR5). Anders None: door naar de machine."""
    snel = snel_oordeel(antwoord)
    if snel is None:
        return None
    oordeel = "klopt niet" if snel == "onwaar" else "klopt"
    m = meter.meterstand(tabel, oordeel, "redactie")
    # #32.11: zeggen alle checks *misleidend*, dan een zachtere uitkomst, oranje; zegt er één onwaar, dan niet.
    alleen_misleidend = {c["verdict_normalized"] for c in antwoord["evidence"]["checks"]} == {"misleidend"}
    bronnen = [{"soort": "check van een redactie", "url": c["url"], "redactie": c["publisher"],
                "oordeel": c["verdict_normalized"], "datum": c["review_date"], "titel": None, "citaat": None}
               for c in antwoord["evidence"]["checks"]]
    return {"oordeel": "misleidend" if alleen_misleidend else oordeel,
            "bewering": (antwoord.get("claim") or {}).get("text"), "uitleg": None,
            "bronnen": bronnen, "stand": {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]},
            "meting": {"n": m["n"], "aandeel waar": m["aandeel waar"]}, "feit": None,
            "kleur": "oranje" if alleen_misleidend else kleur(m["stand"], oordeel), "regels": [], "correcties": [], "herkansing": False,
            "herkomst": None, "gelezen": tekst, "kosten": 0.0, "gebruik": {},
            "versies": {"route": "database", "text_embedding": tekstversie}}


# --- de kosten per dag ------------------------------------------------------------------
# In een eigen bestand (`[berichtcontrole] kosten_db`), nooit in de index: een schrijfactie
# daar leegt de zoekcache, en dan leest elke volgende vraag alle checks opnieuw in (~13 s).

def kostenverbinding(config) -> sqlite3.Connection:  # pragma: no cover - een bestand
    pad = Path(config.berichtcontrole.kosten_db)
    pad.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(pad, check_same_thread=False)


def _kostentabel(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS controle_kosten (dag TEXT PRIMARY KEY, bedrag REAL NOT NULL)")


def uitgegeven(conn, dag: str) -> float:
    _kostentabel(conn)
    rij = conn.execute("SELECT bedrag FROM controle_kosten WHERE dag = ?", (dag,)).fetchone()
    return float(rij[0]) if rij else 0.0


def boek(conn, dag: str, bedrag: float) -> None:
    _kostentabel(conn)
    conn.execute("INSERT INTO controle_kosten (dag, bedrag) VALUES (?, ?) "
                 "ON CONFLICT(dag) DO UPDATE SET bedrag = bedrag + excluded.bedrag", (dag, bedrag))
    conn.commit()


# --- de controle ------------------------------------------------------------------------

def lees_detail(tekst: str) -> list[dict]:
    """De details uit het antwoord op de detailvraag, hoogstens drie; wat niet precies past, telt niet."""
    try:
        details = json.loads(tekst).get("details")
    except (json.JSONDecodeError, AttributeError):
        return []
    if not isinstance(details, list):
        return []
    uit = []
    for d in details[:3]:
        if not isinstance(d, dict):
            continue
        woorden, juist, bron, citaat = d.get("woorden"), d.get("juist"), d.get("bron"), d.get("citaat", "")
        if isinstance(woorden, str) and woorden.strip() and isinstance(juist, str) and juist.strip() \
                and isinstance(bron, int) and not isinstance(bron, bool) and isinstance(citaat, str):
            uit.append({"woorden": woorden, "juist": juist, "bron": bron, "citaat": citaat})
    return uit


def lees_notitie(tekst: str) -> dict | None:
    """Wat de detailvraag van v2 uit de uitleg van de machine haalt: een fout detail dat de machine zelf noemt."""
    try:
        n = json.loads(tekst).get("notitie")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(n, dict) or n.get("afwijking") is not True:
        return None
    woorden, juist = n.get("woorden"), n.get("juist")
    if not (isinstance(woorden, str) and woorden.strip() and isinstance(juist, str) and juist.strip()):
        return None
    return {"afwijking": True, "woorden": woorden, "juist": juist}


def lees_zoekdetail(blokken: list[dict]) -> tuple[list[dict], list[dict]]:
    """Het antwoord van de tweede stap: het detail en de passages die het citeert. Het detail verwijst naar de
    eerste passage die de juiste waarde noemt; de controle in `met_detail` beslist."""
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    per_pagina: dict[str, list[str]] = {}
    for p in _passages(v.bronnen_uit(blokken, [])):
        per_pagina.setdefault(p["url"], []).append(p["citaat"])
    passages = [{"soort": "web", "url": u, "citaat": " … ".join(c)} for u, c in per_pagina.items()]
    woorden = re.search(r"WOORDEN:\s*(.+)", tekst)
    juist = re.search(r"JUIST:\s*(.+)", tekst)
    if not (woorden and juist):
        return [], passages
    w, j = woorden.group(1).strip().strip('"'), juist.group(1).strip().strip('"')
    nummer = next((n for n, p in enumerate(passages, 1) if _gewoon(j) in _gewoon(p["citaat"])), 0)
    return [{"woorden": w, "juist": j, "bron": nummer, "citaat": ""}], passages


def _gewoon(tekst: str) -> str:
    return " ".join((tekst or "").lower().split())


def plaats(bericht: str, woorden: str) -> tuple[int, int] | None:
    """Waar de woorden in het bericht staan (begin en eind in tekens), ongeacht hoofdletters en witruimte."""
    delen = woorden.split()
    if not delen:
        return None
    m = re.search(r"\s+".join(map(re.escape, delen)), bericht, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def _geldig(bericht: str, passages: list[dict], d: dict) -> bool:
    """B48: de woorden staan letterlijk in het bericht en niet in de passage, de juiste waarde staat letterlijk in
    de passage, en ze verschillen."""
    if not 1 <= d["bron"] <= len(passages):
        return False
    woorden, juist, passage = _gewoon(d["woorden"]), _gewoon(d["juist"]), _gewoon(passages[d["bron"] - 1]["citaat"])
    return (woorden != juist and woorden in _gewoon(bericht) and juist in passage and woorden not in passage
            and plaats(bericht, d["woorden"]) is not None)


def met_detail(tabel: dict, na: dict, bericht: str, bronnen: list[dict], details: list[dict],
               passages: list[dict] | None = None) -> dict:
    """De uitkomst na de detailvraag (B48): bij *klopt* met één geldig vals detail *klopt grotendeels*, zonder
    kleur en met de verbetering; met twee of meer *klopt niet*. Anders blijft alles. `passages`: die van de
    tweede stap, anders de passages die de machine citeerde. Het citaat bij een verbetering is de passage
    zelf, letterlijk uit de bron (een bonnetje), niet wat het model ervan overnam."""
    if na["oordeel"] != "klopt":
        return na
    passages = _passages(bronnen) if passages is None else passages
    geldig, gezien = [], set()
    for d in details:
        if _geldig(bericht, passages, d) and _gewoon(d["woorden"]) not in gezien:
            gezien.add(_gewoon(d["woorden"]))
            geldig.append(d)
    if not geldig:
        return na
    correcties = []
    for d in geldig:
        begin, eind = plaats(bericht, d["woorden"])
        p = passages[d["bron"] - 1]
        correcties.append({"woorden": bericht[begin:eind], "juist": d["juist"], "url": p["url"],
                           "citaat": p["citaat"], "begin": begin, "eind": eind})
    oordeel = "klopt grotendeels" if len(geldig) == 1 else "klopt niet"
    m = meter.meterstand(tabel, "onzeker" if oordeel == "klopt grotendeels" else "klopt niet",
                         meter.laag_van_antwoord(bronnen))
    return {**na, "oordeel": oordeel, "stand": {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]},
            "feit": None, "kleur": None if oordeel == "klopt grotendeels" else kleur(m["stand"], oordeel),
            "regels": [*na["regels"], "vals detail"], "meting": {"n": m["n"], "aandeel waar": m["aandeel waar"]},
            "correcties": correcties}


def lees_herkomst(blokken: list[dict]) -> dict:
    """Het antwoord op de herkomstcontrole: de uitkomst uit de laatste JSON-regel, de verschillen met een bekende
    soort, en de passages die de API letterlijk citeert, per pagina samen. Wat niet te lezen is: geen uitkomst."""
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    per_pagina: dict[str, list[str]] = {}
    for p in _passages(v.bronnen_uit(blokken, [])):
        per_pagina.setdefault(p["url"], []).append(p["citaat"])
    passages = [{"soort": "web", "url": u, "citaat": " … ".join(c)} for u, c in per_pagina.items()]
    d = None
    for begin in reversed([i for i, teken in enumerate(tekst) if teken == "{"]):
        try:
            d, _ = json.JSONDecoder().raw_decode(tekst[begin:])
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and "uitkomst" in d:
            break
        d = None
    if not d or d.get("uitkomst") not in UITKOMSTEN:
        return {"uitkomst": None, "url": "", "verschillen": [], "passages": passages}
    verschillen = [{"soort": x["soort"], "woorden": x["woorden"], "juist": x["juist"]}
                   for x in d.get("verschillen") or [] if isinstance(x, dict) and x.get("soort") in ("inhoud", "herkomst")
                   and isinstance(x.get("woorden"), str) and x["woorden"].strip()
                   and isinstance(x.get("juist"), str) and x["juist"].strip()]
    return {"uitkomst": d["uitkomst"], "url": d.get("url") if isinstance(d.get("url"), str) else "",
            "verschillen": verschillen, "passages": passages}


def herkomst_uitkomst(bericht: str, herkomst: dict) -> dict:
    """Wat de herkomstcontrole bewijst: de verschillen in de inhoud die gelden (de woorden letterlijk in het
    bericht, de juiste waarde letterlijk in een geciteerde passage van de site, zoals B48), en of een groen
    daardoor rood wordt of zijn kleur verliest."""
    passages = herkomst["passages"]
    geldig = []
    for d in herkomst["verschillen"]:
        if d["soort"] != "inhoud":
            continue
        nummer = next((n for n, p in enumerate(passages, 1) if _gewoon(d["juist"]) in _gewoon(p["citaat"])), 0)
        if _geldig(bericht, passages, {**d, "bron": nummer}):
            geldig.append({**d, "bron": nummer})
    rood = herkomst["uitkomst"] == "anders" and bool(geldig)
    return {"uitkomst": herkomst["uitkomst"], "geldig": geldig, "rood": rood,
            "groen weg": herkomst["uitkomst"] in ("anders", "niet gevonden")}


def met_herkomst(tabel: dict, na: dict, bericht: str, herkomst: dict, bronnen: list[dict]) -> dict:
    """De uitkomst na de herkomstcontrole (PLAN #32.3e):
    - *anders* met een bewezen verschil in de inhoud: *klopt niet*, rood, met het echte artikel als bron;
    - *anders* zonder zo'n verschil, of *niet gevonden*: nooit groen; een rood blijft rood;
    - *gelijk* of geen uitkomst: niets verandert.
    `bronnen`: die van de machine, voor de laag van de stand."""
    u = herkomst_uitkomst(bericht, herkomst)
    if u["rood"]:
        correcties = []
        for d in u["geldig"]:
            begin, eind = plaats(bericht, d["woorden"])
            p = herkomst["passages"][d["bron"] - 1]
            correcties.append({"woorden": bericht[begin:eind], "juist": d["juist"], "url": p["url"],
                               "citaat": p["citaat"], "begin": begin, "eind": eind})
        m = meter.meterstand(tabel, "klopt niet", "web")
        return {**na, "oordeel": "klopt niet", "stand": {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]},
                "feit": None, "kleur": kleur(m["stand"], "klopt niet"), "regels": [*na["regels"], "vervalst artikel"],
                "meting": {"n": m["n"], "aandeel waar": m["aandeel waar"]}, "correcties": correcties}
    if not u["groen weg"]:
        return na
    regel = "andere herkomst" if u["uitkomst"] == "anders" else "herkomst niet gevonden"
    if na["kleur"] != "groen":
        return {**na, "regels": [*na["regels"], regel]}
    m = meter.meterstand(tabel, "onzeker", meter.laag_van_antwoord(bronnen))
    return {**na, "oordeel": "onzeker", "stand": {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]},
            "feit": None, "kleur": None, "regels": [*na["regels"], regel],
            "meting": {"n": m["n"], "aandeel waar": m["aandeel waar"]}}


def bewaak_plafond(kosten_conn, config, dag: str | None) -> None:
    """Boven het dagplafond geen enkele vraag meer, ook niet die van "beweringen eerst" (#32.6)."""
    c = config.berichtcontrole
    if uitgegeven(kosten_conn, dag) >= c.dagplafond_dollar:
        raise Plafond(f"het dagplafond van ${c.dagplafond_dollar:.2f} is bereikt")


def beoordeel(kosten_conn, voorbereid: dict, client, config, datum: str | None, tabel: dict, zinnen: dict[str, str],
              dag: str | None = None) -> dict:
    """De drie vragen tegelijk, de herkansing, de stand en de kosten. `kosten_conn`: de
    database van de kosten per dag, niet die van de index; `datum`: wanneer het
    bericht rondging (in de dienst de dag van de vraag); `dag`: de dag voor het plafond."""
    conn = kosten_conn
    c = config.berichtcontrole
    dag = dag or datum
    if c.herkansing not in HERKANSING:
        raise VersieFout(f"herkansing {c.herkansing!r} bestaat niet in de code")
    if c.detail and c.detail not in DETAILS:
        raise VersieFout(f"detailvraag {c.detail!r} bestaat niet in de code")
    if c.vloer:
        vloerverzoek("", "A", config)  # weigert bij een onbekende versie of een ander model, vóór de eerste vraag
    if c.herkomst and c.herkomst not in HERKOMST:
        raise VersieFout(f"herkomstcontrole {c.herkomst!r} bestaat niet in de code")
    bewaak_plafond(conn, config, dag)
    geheugen, tekst = voorbereid["geheugen"], voorbereid["tekst"]
    vraag = machineverzoek(tekst, geheugen, datum, config)
    feitvragen = {k: feitverzoek(tekst, voorbereid["kandidaten"], k, zinnen, config)
                  for k in f.SLEUTELS} if voorbereid["kandidaten"] else {}
    site = herkomst_site(tekst, herkomstlijst()["sites"]) if c.herkomst else None
    with ThreadPoolExecutor(max_workers=4) as pool:
        machine = pool.submit(client.messages.create, **vraag)
        feiten = {k: pool.submit(client.messages.create, **p) for k, (p, _) in feitvragen.items()}
        herkomst = pool.submit(client.messages.create, **herkomstverzoek(tekst, site, c.herkomst, config)) \
            if site else None
        a = machineantwoord(machine.result(), geheugen)
        herkansing = herkansing_nodig(a)
        if herkansing:
            eerste = a["kosten"]
            a = machineantwoord(client.messages.create(**met_herkansing(vraag, HERKANSING[c.herkansing])), geheugen)
            a["kosten"] += eerste
        feitantwoorden = {k: feitantwoord(t.result(), feitvragen[k][1]) for k, t in feiten.items()}
    stand, feit, meting = stand_van(tabel, a, feitantwoorden.get("A", _GEEN_FEIT), feitantwoorden.get("B", _GEEN_FEIT))
    totaal = a["kosten"] + sum(x["kosten"] for x in feitantwoorden.values()) + voorbereid.get("kosten", 0.0)
    oordeel, vloer = a["oordeel"], False
    if c.vloer and vloer_nodig(a, tekst, tabel, c.vloer):
        vloer, k = vloer_vragen(tekst, client, config)
        totaal += k
        if vloer:
            m = meter.meterstand(tabel, "klopt niet", LAAG_VLOER)
            oordeel, feit = "klopt niet", None
            stand = {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"]}
            meting = {"n": m["n"], "aandeel waar": m["aandeel waar"]}
    na = {"oordeel": oordeel, "stand": stand, "feit": feit, "kleur": kleur(stand["stand"], oordeel),
          "regels": [], "meting": None}
    if c.vorm and na["kleur"] is not None and a["bewering"]:
        antwoord = client.messages.create(**vormverzoek(tekst, c.vorm, config, a["bewering"]))
        totaal += kosten(gebruik_uit(antwoord))
        vorm = lees_vorm("".join(getattr(b, "text", "") or "" for b in antwoord.content))
        na = regels(tabel, oordeel, stand, feit, a["bronnen"], vorm)
    if vloer:
        na = {**na, "regels": [*na["regels"], "algemene kennis"]}
    if c.detail and na["oordeel"] == "klopt" and _passages(a["bronnen"]):
        antwoord = client.messages.create(**detailverzoek(tekst, a, c.detail, config))
        totaal += kosten(gebruik_uit(antwoord))
        gelezen = "".join(getattr(b, "text", "") or "" for b in antwoord.content)
        voor = na
        na = met_detail(tabel, na, tekst, a["bronnen"], lees_detail(gelezen))
        notitie = lees_notitie(gelezen) if c.detail in ZOEKVRAGEN else None
        if na is voor and notitie:
            antwoord = client.messages.create(**zoekverzoek(tekst, notitie, c.detail, config))
            totaal += kosten(gebruik_uit(antwoord))
            details, passages = lees_zoekdetail([b.model_dump() for b in antwoord.content])
            na = met_detail(tabel, na, tekst, a["bronnen"], details, passages)
    uit_herkomst = None
    if herkomst is not None:
        antwoord = herkomst.result()
        totaal += kosten(gebruik_uit(antwoord))
        gelezen_h = lees_herkomst([b.model_dump() for b in antwoord.content])
        na = met_herkomst(tabel, na, tekst, gelezen_h, a["bronnen"])
        uit_herkomst = {"site": site, "uitkomst": gelezen_h["uitkomst"], "url": gelezen_h["url"]}
    boek(conn, dag, totaal)
    return {"oordeel": na["oordeel"], "bewering": a["bewering"], "uitleg": a["uitleg"],
            "bronnen": bronnen_voor(a["bronnen"], geheugen), "stand": na["stand"], "meting": na["meting"] or meting,
            "feit": na["feit"], "kleur": na["kleur"], "regels": na["regels"], "correcties": na.get("correcties", []),
            "herkansing": herkansing, "herkomst": uit_herkomst,
            "gelezen": tekst, "kosten": totaal, "gebruik": a["gebruik"],
            "versies": {"model": c.model_id, "question": c.vraag, "retry": c.herkansing, "fact_step": c.feitenstap,
                        "scale": Path(c.ijking).stem, "form": c.vorm, "detail": c.detail, "claims": c.beweringen,
                        "floor": c.vloer, "provenance": c.herkomst}}


def beweringenverzoek(tekst: str, config) -> dict:
    """De vraag van "beweringen eerst" (#32.6): precies die van V2 in P4, op de gemaskeerde tekst. Zonder zoeken."""
    from doublecheck.modellen import MODELLEN

    c = config.berichtcontrole
    if c.beweringen not in BEWERINGEN:
        raise VersieFout(f"beweringen {c.beweringen!r} bestaat niet in de code")
    model = BEWERINGEN[c.beweringen]["model"]
    if MODELLEN[model]["id"] != c.beweringen_model:
        raise VersieFout(f"{c.beweringen} is gemeten met {MODELLEN[model]['id']}, config zegt {c.beweringen_model}")
    vraag = BEWERINGEN[c.beweringen]["vraag"].format(n=zh.MAX_BEWERINGEN, m=zh.MAX_ZOEKVRAGEN, tekst=tekst[:3000])
    return {"model": c.beweringen_model, "max_tokens": 1_500, "messages": [{"role": "user", "content": vraag}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": zh._SCHEMA}}}


def beweringen_vragen(tekst: str, client, config, screenshot: bool) -> tuple[list[dict], float]:
    """De beweringen met hun zoekvragen, en wat dat kostte; alleen bij een screenshot en als het aan staat."""
    from doublecheck.modellen import MODELLEN

    if not (config.berichtcontrole.beweringen and screenshot and tekst.strip()):
        return [], 0.0
    antwoord = client.messages.create(**beweringenverzoek(tekst, config))
    prijs = MODELLEN[BEWERINGEN[config.berichtcontrole.beweringen]["model"]]  # met batchkorting, dus keer twee
    g = gebruik_uit(antwoord)
    kosten_ = 2 * (g["in"] * prijs["in"] + g["uit"] * prijs["uit"]) / 1e6
    return zh.lees_extractie("".join(getattr(b, "text", "") or "" for b in antwoord.content)), kosten_


def vloerverzoek(tekst: str, sleutel: str, config) -> dict:
    """Eén vraag van de vloerstap (B50): precies die van de voormeting, zonder zoeken."""
    from doublecheck import vloervraag as vl
    from doublecheck.modellen import MODELLEN

    c = config.berichtcontrole
    if c.vloer not in VLOER:
        raise VersieFout(f"vloerstap {c.vloer!r} bestaat niet in de code")
    if MODELLEN[VLOER[c.vloer]["model"]]["id"] != c.vloer_model:
        raise VersieFout(f"{c.vloer} is gemeten met {MODELLEN[VLOER[c.vloer]['model']]['id']}, config zegt {c.vloer_model}")
    return vl.verzoek(tekst, sleutel, config)


def vloer_nodig(antwoord: dict, tekst: str, tabel: dict, versie: str = "vloer-v1") -> bool:
    """De vloerstap komt alleen als de machine twijfelt (in `vloer-v1` zonder één bron, in `vloer-v2` met of zonder),
    bij een Engels bericht (twijfel over de taal is geen Engels), en als de laag geijkt is op hoogstens stand 3 met
    genoeg berichten (B44, B50)."""
    from doublecheck.taal import corpus_taal

    klasse = tabel.get(("klopt niet", LAAG_VLOER))
    if not klasse or klasse["n"] < meter.MIN_N or klasse["stand"] > 3:
        return False
    if antwoord["bronnen"] and not VLOER[versie]["met_bron"]:
        return False
    return antwoord["oordeel"] in ("onzeker", "let op") and corpus_taal(tekst) == "en"


def vloer_vragen(tekst: str, client, config) -> tuple[bool, float]:
    """De twee vragen tegelijk; waar alleen als beide "clearly false" zeggen. En wat het kostte, zonder batchkorting."""
    from doublecheck import vloervraag as vl
    from doublecheck.modellen import MODELLEN

    with ThreadPoolExecutor(max_workers=2) as pool:
        antwoorden = list(pool.map(lambda k: client.messages.create(**vloerverzoek(tekst, k, config)), vl.SLEUTELS))
    prijs = MODELLEN[VLOER[config.berichtcontrole.vloer]["model"]]
    kosten_ = sum(2 * (g["in"] * prijs["in"] + g["uit"] * prijs["uit"]) / 1e6 for g in map(gebruik_uit, antwoorden))
    ja = all(vl.lees_oordeel("".join(getattr(b, "text", "") or "" for b in a.content)) == vl.DUIDELIJK
             for a in antwoorden)
    return ja, kosten_


def geheugen_uit(lijsten: list[list[dict]], verborgen: frozenset[str] = frozenset()) -> list[dict]:
    """Eén geheugen uit de checks van een of meer zoekvragen: per check de hoogste gelijkenis, de vijf beste.
    Met één zoekvraag hetzelfde als vóór #32.6."""
    return v.verberg(zh.voeg_samen(lijsten, v.N_GEHEUGEN + len(verborgen)), set(verborgen))


def geheugen_met(conn, config, tekst: str, fp, gehaald: list[dict],
                 verborgen: frozenset[str] = frozenset()) -> list[dict]:  # pragma: no cover - model en database
    """Het geheugen voor de tekst (met haar vingerafdruk `fp`) en, bij "beweringen eerst", de beweringen en
    zoekvragen; ook voor de meting van #32.6, met de beweringen uit de batch."""
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.search import search_texts

    extra = zh.zoekvragen(tekst, gehaald)[1:] if gehaald else []
    fps = [fp] + (fingerprint_texts([q[:600] for q in extra], config.model_versions.text_embedding) if extra else [])
    lijsten = search_texts(conn, fps, 8 + len(verborgen), varianten=True)
    return geheugen_uit([v.kandidaten_uit(conn, lijst) for lijst in lijsten], verborgen)


def voorbereiden(conn, config, tekst: str, verborgen: frozenset[str] = frozenset(), client=None,
                 screenshot: bool = False) -> dict:  # pragma: no cover
    """Het lokale deel: de vingerafdruk, de vijf beste checks boven de vloer en de
    kandidaten voor de lijst met vastgestelde feiten, zoals in de route (#31.10).
    Bij een screenshot en met "beweringen eerst" aan eerst de vraag aan Haiku
    (#32.6); de feitenstap blijft op de tekst. `verborgen` is alleen voor
    metingen: die checks doen alsof ze er niet zijn (P6, PLAN #32.0d); in het
    product is hij leeg."""
    from doublecheck.embedding import fingerprint_texts

    gehaald, kosten_ = beweringen_vragen(tekst, client, config, screenshot) if client is not None else ([], 0.0)
    fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
    geheugen = geheugen_met(conn, config, tekst, fp, gehaald, verborgen)
    index, versie = feitindex()
    if versie != fp.model_version:
        raise VersieFout(f"de lijst met vastgestelde feiten draagt {versie}, het bericht {fp.model_version} (DR6)")
    kandidaten = [[x, round(g, 4)] for x, g in f.kandidaten(fp.vector, index, f.KERN["v3"]["vloer"])]
    return {"tekst": tekst, "geheugen": geheugen, "kandidaten": kandidaten, "beweringen": gehaald, "kosten": kosten_}


@lru_cache(maxsize=1)
def feitindex():  # pragma: no cover - met het model
    """((zinnen, matrix), modelversie) van de lijst met vastgestelde feiten, één keer per proces."""
    return f._index()


@lru_cache(maxsize=1)
def feitzinnen() -> dict[str, str]:  # pragma: no cover - op de kern
    return f.zinnen_van_feiten()


@lru_cache(maxsize=64)
def feitinfo(feit: str) -> dict:
    """Een vastgesteld feit voor de uitslag: de zin en de bronnen, elk met link en
    wat de bron zegt (B34, DESIGN §4f)."""
    from doublecheck.feitenbasis import lees_kern

    rij = next(x for x in lees_kern() if x["id"] == feit)
    return {"id": feit, "zin": rij["zin"],
            "bronnen": [{"url": b["vindplaats"], "steunt": b.get("steunt")} for b in rij["bronnen"]]}


def ijktabel(config) -> dict:
    """De ijking van de meter bij deze machine; een ijking van een andere vraag weigert (DR6)."""
    c = config.berichtcontrole
    pad = WORTEL / c.ijking
    if c.vraag not in pad.stem:
        raise VersieFout(f"de ijking {pad.name} hoort niet bij vraag {c.vraag}")
    return {(k["oordeel"], k["laag"]): k for k in json.loads(pad.read_text(encoding="utf-8"))["klassen"]}
