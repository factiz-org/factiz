"""Vertalingen van beweringen voor weergave op het platform (PLAN #33.5, SPECS E9.S3 AC6, B32).

De Engelse versies uit #25.17 zijn als zoekvariant geschreven. Voor Nederlands, Duits, Spaans en Frans vraagt dit om
een trouwe vertaling: niets erbij, niets eraf. Eén vraag per bewering, zodat een vertaling nooit onder de verkeerde
bewering kan komen. Een doeltaal komt pas op de site na een leesproef van honderd zonder betekenisfout.

Sinds #34.2x (PO 2026-11-12: "Ja, zelfde methode") meet die leesproef de methode. Ze ligt vast op de eerste ronde
waarin een doeltaal gevraagd werd, en een latere ronde met dezelfde vraag gaat zonder eigen leesproef op de site. Na elke
5.000 nieuwe per doeltaal lees ik er 50, en tot dan wacht wat erna komt. Engels wordt gevraagd waar het lab geen Engelse
versie schreef, met Sonnet: een methode is de vraag samen met het model (`METHODE`), en Haiku had in het Engels drie van
de honderd fout.

    python -m doublecheck.weergave proef [--n 40]|plan|indienen|ophalen [--wacht M]|lezen --taal nl [--ronde 2]|tellen
    python -m doublecheck.weergave lezen --taal nl --import       (de steekproef van 50 uit een vol blok)
    python -m doublecheck.weergave controle proef [--versie V] [--model sonnet]|tellen|indienen|ophalen [--wacht M]

De controlestap (stap 4) legt elke vertaling naast het origineel en meldt een verschil in wie, wat, waar, wanneer of
hoeveel; wat gemeld wordt of geen oordeel krijgt, staat niet op de site. Eerst gemeten op de 400 paren die ik al las.

Leest de publicatiedatabase (openbare beweringen, met de herstelde taal), alleen-lezen. Uitvoer in `data/vertalingen/`,
buiten de database van het lab; mijn lezing in `docs/steekproeven/33.5-vertalingen.json`.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

from doublecheck.sitetalen import BASIS, SITETALEN

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "vertalingen"
ANTWOORDEN = MAP / "antwoorden.jsonl"
BATCHES = MAP / "batches.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "33.5-vertalingen.json"
VERSIE = "weergave-v1"
VIER = ("nl", "de", "es", "fr")                # de doeltalen voor elke bewering
# de tien talen die de site er in B79 bij kreeg (PLAN #34.2be, fase 2): de sitetalen zonder de vijf van B74
NIEUW = tuple(t for t in SITETALEN if t not in BASIS)
DOELTALEN = (*VIER, "en", *NIEUW)              # Engels alleen waar het lab geen Engelse versie schreef (#34.2x)
NAAM = {"nl": "Dutch", "de": "German", "es": "Spanish", "fr": "French", "en": "English",
        "pt": "Brazilian Portuguese", "ru": "Russian", "uk": "Ukrainian", "id": "Indonesian", "tr": "Turkish",
        "zh": "Traditional Chinese (as written in Taiwan)", "ja": "Japanese", "hi": "Hindi",
        "ar": "Arabic (Modern Standard)", "fa": "Persian"}
GRENS = 20.00           # dollar, voor de vier talen en het Engels samen (PO 2026-11-11: "graag")
GRENS_NIEUW = 39.00     # dollar, voor de tien nieuwe talen (PO 2026-11-15: "$39.91 promotional credit available, als het
                        # je lukt hierbinnen te blijven zou dat heel fijn zijn")
MARGE = 1.15            # een schatting uit een kleine proef kan ernaast zitten: de grens houdt er rekening mee
MAX_TEKENS = 1200       # van een bewering in de vraag
PORTIE = 20_000         # vragen per batch
ZAAD = 3360
PROEF_N = 100
FOUT = ("betekenisfout", "onzeker")
GELDIG = ("trouw", "klein", *FOUT)
# Een methode is de vraag samen met het model. Per doeltaal geldt er één; een vertaling met een andere komt niet op de
# site. Haiku voor de vier (33.5); Sonnet voor het Engels, na drie fouten van Haiku in de leesproef (PO 2026-11-12:
# "Yes, with Sonnet"). De lezing van de methode van 33.5 staat bovenaan in het labelbestand, die van een andere onder
# `methoden`.
EERSTE = f"{VERSIE}/haiku"
# De tien nieuwe talen (#34.2be): dezelfde vraag, zonder denkwerk (Haiku 5.5 denkt anders standaard mee, ook bij effort
# low, en dat wordt betaald als uitvoer) en met ruimte voor tien talen in één antwoord. Een eigen methode, dus een eigen
# leesproef per taal.
VERSIE_NIEUW = "weergave-v2"
# Na de leesproef van fase 2 (alleen het Perzisch door de poort): dezelfde vraag mét denkwerk, zoals weergave-v1 dat had,
# eerst als proef gemeten
VERSIE_DENKEN = "weergave-v3"
# Gericht op wat de leesproef van fase 2 vond (getallen, 'Claim', een voorbehoud erbij, woorden half in een ander schrift,
# vereenvoudigd Chinees, en begrip van brontalen als Khmer of Somalisch): regels erbij, en de Engelse versie als hulp
VERSIE_V4 = "weergave-v4"
# v4 zette 'Claim:' voor 21 tot 33% van de vertalingen zonder zo'n label in het origineel: v5 laat een label alleen staan
VERSIE_V5 = "weergave-v5"
# v5 begon de vraag met 'Claim (language: en):' en nam dat 16 van de 100 keer over: v6 zet de bewering tussen markeringen
VERSIE_V6 = "weergave-v6"
NIEUWE_VERSIES = frozenset({VERSIE_NIEUW, VERSIE_DENKEN, VERSIE_V4, VERSIE_V5, VERSIE_V6})


def van_nieuw(rij: dict) -> bool:
    """Hoort een batch, proef of methode bij de tien nieuwe talen (onder `GRENS_NIEUW`)? Elke vraag na weergave-v1."""
    return (rij.get("versie") or VERSIE) in NIEUWE_VERSIES
METHODE = {"nl": EERSTE, "de": EERSTE, "es": EERSTE, "fr": EERSTE, "en": f"{VERSIE}/sonnet",
           **{t: f"{VERSIE_NIEUW}/haiku" for t in NIEUW}}
# Na de leesproef van fase 2 haalde alleen het Perzisch de poort; binnen het tegoed kreeg het Portugees een tweede ronde
# met weergave-v6, de vraag die in de proef op dezelfde 100 beweringen één betekenisfout liet (PLAN #34.2be)
METHODE["pt"] = "weergave-v6/haiku"
PROEF_NIEUW = MAP / "proef-nieuw.jsonl"   # de proef voor de kosten van de nieuwe talen; telt niet als ronde
BLOK = 5_000            # nieuwe vertalingen per doeltaal na de eerste ronde, per steekproef (#34.2x)
BLOK_N = 50             # de steekproef per vol blok
ZAAD_BLOK = 3380
ZAAD_BRON = 3390        # de nieuwe proef voor één brontaal (#34.2aa)

CONTROLE = MAP / "controle.jsonl"
CONTROLE_PROEF = MAP / "controle-proef.jsonl"
CONTROLE_BATCHES = MAP / "controle-batches.jsonl"
CONTROLE_VERSIE = "controle-v1"
ZAAD_NA = 3370          # de leesproef na de controle: een nieuwe greep
EIS_VANGST = 5          # van de 6 fouten uit de eerste leesproef
EIS_WEG = 0.10          # hoogstens zoveel van de goede paren gemeld
GRENS_SONNET = 1.50     # dollar, voor één meting met Sonnet op de gelezen paren
DOOR = ("gelijk", "klein")
_OORDEEL = {"same": "gelijk", "wording": "klein", "meaning": "verschil"}

_SYSTEEM = (
    "You translate claims that fact-checkers have checked, for a public archive. A reader sees your translation above "
    "the original text, marked as a machine translation.\n"
    "- Translate faithfully and completely: keep every statement, name, number, date and place. Add nothing and leave "
    "nothing out.\n"
    "- Do not correct, soften or comment on the claim, even when it is false, offensive or badly written. Keep its "
    "tone: a question stays a question, a quote stays a quote.\n"
    "- Write names of people, organisations and places the way they are usually written in the target language.\n"
    "- Keep hashtags, @-names and links unchanged. If the text is only a name, a number or a link, give it back "
    "unchanged.\n"
    "- Write plain, natural language.")

_SYSTEEM_V4 = _SYSTEEM + (
    "\n- Numbers, amounts, currencies, units and dates: copy them exactly as the original gives them. Do not convert a "
    "currency, a unit or a number system (no lakh or crore where the original has none, and none dropped where it has "
    "them): 102 milhões is 102 million, $400K is 400,000 dollars.\n"
    "- Keep a label such as 'Claim:' at the start, translated: it marks the text as a claim. Never turn a claim into a "
    "plain statement.\n"
    "- Do not add words like 'allegedly', 'supposedly' or 'reportedly' that the original does not have, and keep them "
    "where it does. A firm statement stays firm; a question stays a question.\n"
    "- Write every word wholly in the usual script of the target language. A name is either written fully in that "
    "script or kept fully in its original form; never mix scripts inside one word.\n"
    "- Traditional Chinese means traditional characters only, as used in Taiwan.\n"
    "- You may get an English rendering of the claim. It was made separately and may be loose or wrong; the original "
    "decides. Use it only to understand the original.")

_SYSTEEM_V5 = _SYSTEEM_V4.replace(
    "- Keep a label such as 'Claim:' at the start, translated: it marks the text as a claim. Never turn a claim into a "
    "plain statement.",
    "- If the original starts with a label such as 'Claim:', keep it, translated: it marks the text as a claim. Never add "
    "a label the original does not have.")

_SYSTEEM_V6 = _SYSTEEM_V5.replace(
    "- If the original starts with a label such as 'Claim:', keep it, translated: it marks the text as a claim. Never add "
    "a label the original does not have.",
    "- The claim is the text inside <claim>. If that text itself starts with a label such as 'Claim:', keep it, "
    "translated. Never add a label, a heading or the name of a language that the text does not have.").replace(
    "- You may get an English rendering of the claim. It was made separately and may be loose or wrong; the original "
    "decides. Use it only to understand the original.",
    "- You may get an English rendering inside <english_rendering>. It was made separately and may be loose or wrong; "
    "the text inside <claim> decides. Use it only to understand the claim, never translate it.")

_CONTROLE = {"controle-v1": {"effort": "low", "systeem": (
    "You check machine translations of claims that fact-checkers have checked, for a public archive. A reader sees a "
    "translation above the original, so it must say what the original says: no more and no less.\n"
    "Compare each translation with the original, piece by piece: who (people, organisations, their rank or role), "
    "what happened and who did it to whom, where, when, how many or how much, and whether something is asserted, "
    "denied, asked or only alleged. Read the original itself; the translations may share a mistake.\n"
    "Give one verdict per translation:\n"
    "- meaning: the translation says something the original does not say. A different person, rank, place, time or "
    "number; a relation turned around; a negation lost or added; a part attached to the wrong person or thing; a "
    "firm statement made doubtful or the reverse; something added; something left out.\n"
    "- wording: only word choice, style or grammar differ, or a part was left untranslated. The facts are the same.\n"
    "- same: a faithful translation.\n"
    "A name written the way it is usually written in the target language is not a difference. The claim may be "
    "false, offensive or badly written: judge only whether the translation matches it.\n"
    "In `note`, say in a few English words what differs; leave it empty for `same`.")},
    # v2: twee lezingen van hetzelfde model verschillen soms; de Engelse versie die er al lag (#25.17) is zo'n tweede
    "controle-v2": {"effort": "low", "tweede": True, "systeem": (
        "You check machine translations of claims that fact-checkers have checked, for a public archive. A reader "
        "sees a translation above the original, so it must say what the original says: no more and no less.\n"
        "You get the original, sometimes a second reading of it in English that was made separately, and the "
        "translations. The translations were made together and may share a mistake. The second reading may be loose "
        "or leave things out; that is fine. But where it states a fact differently from a translation, go back to the "
        "original and decide which one is right. If you cannot tell, the verdict is `meaning`.\n"
        "Compare piece by piece: who (people, organisations, their rank or role), what happened and who did it to "
        "whom, where, when, how many or how much, and whether something is asserted, denied, asked or only alleged.\n"
        "One verdict per translation:\n"
        "- meaning: the translation says something the original does not say. A different person, rank, place, time "
        "or number; a relation turned around; a negation lost or added; a part attached to the wrong person or thing; "
        "a firm statement made doubtful or the reverse; something added; something left out.\n"
        "- wording: only word choice, style or grammar differ, or a part was left untranslated. The facts are the "
        "same.\n"
        "- same: a faithful translation.\n"
        "A name written the way it is usually written in the target language is not a difference. The claim may be "
        "false, offensive or badly written: judge only whether the translation matches it.\n"
        "`note`: for `meaning`, a few English words on what differs; otherwise leave it empty.")},
    # v3: het origineel helemaal niet tonen. Het model vergelijkt twee teksten in talen die het goed leest; alleen
    # mogelijk waar een tweede lezing ligt (niet bij Engelse beweringen)
    "controle-v3": {"effort": "low", "tweede": True, "zonder_origineel": True, "systeem": (
        "You compare renderings of one claim that fact-checkers have checked. A is an English rendering. It may be "
        "loose: it may merge sentences, shorten, or leave details out. The others are translations of the same claim "
        "into other languages, made separately from A.\n"
        "For each translation, go through its facts one by one and look for the same fact in A: each person, "
        "organisation, rank or role; each place name; each time and number; what was done, how, and who did it to "
        "whom; whether something happened or not.\n"
        "- meaning: the translation and A state a fact differently. A different person, rank, place name, time or "
        "number; something done to a different person or in a different way; a yes against a no.\n"
        "- wording: they state the same facts in other words.\n"
        "- same: no difference.\n"
        "A detail that A leaves out is not a difference. A name written the way it is usually written in the target "
        "language is not a difference.\n"
        "`note`: for `meaning`, a few English words on what differs; otherwise leave it empty.")}}


class Weigering(Exception):
    """De grens in dollars is bereikt, of er ontbreekt iets."""


def doelen(taal: str | None, engels: bool = False, sitetalen: bool = False) -> list[str]:
    """De doeltalen voor een bewering in deze taal: de vier, behalve haar eigen, Engels als het lab er geen Engelse
    versie van schreef (`engels`), en met `sitetalen` de tien nieuwe talen behalve haar eigen (#34.2be). Zonder taal geen
    vertaling. Zonder `sitetalen` is het wat een antwoord van vóór #34.2x vroeg."""
    if (taal or "und") == "und":
        return []
    return ([t for t in VIER if t != taal] + (["en"] if engels and taal != "en" else [])
            + ([t for t in NIEUW if t != taal] if sitetalen else []))


def verzoek(tekst: str, taal: str, gevraagd: list[str] | None = None, model: str = "haiku", versie: str = VERSIE,
            engels: str | None = None) -> dict:
    """Eén vraag over één bewering: vertaal haar in de doeltalen die niet haar eigen taal zijn, of in `gevraagd`. De
    vraag is voor elk model dezelfde. `weergave-v2` (de tien nieuwe talen) vraagt hetzelfde zonder denkwerk en met ruimte
    voor elke gevraagde taal."""
    from doublecheck.modellen import MODELLEN

    gevraagd = doelen(taal) if gevraagd is None else gevraagd
    schema = {"type": "object", "additionalProperties": False, "required": ["vertalingen"], "properties": {
        "vertalingen": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["taal", "tekst"],
            "properties": {"taal": {"type": "string", "enum": gevraagd}, "tekst": {"type": "string"}}}}}}
    talen = ', '.join(f'{NAAM[t]} ({t})' for t in gevraagd)
    if versie == VERSIE_V6:
        hulp = (f"<english_rendering>\n{engels[:MAX_TEKENS]}\n</english_rendering>\n\n"
                if engels and taal != "en" else "")
        vraag = (f'<claim language="{taal}">\n{(tekst or "")[:MAX_TEKENS]}\n</claim>\n\n{hulp}'
                 f"Translate the text inside <claim> into: {talen}.")
    else:
        hulp = (f"English rendering (a help only; the original decides):\n{engels[:MAX_TEKENS]}\n\n"
                if versie in (VERSIE_V4, VERSIE_V5) and engels and taal != "en" else "")
        vraag = (f"Claim (language: {taal}):\n{(tekst or '')[:MAX_TEKENS]}\n\n{hulp}"
                 f"Translate the claim into: {talen}.")
    v = {"model": MODELLEN[model]["id"], "max_tokens": 4000, "system": _SYSTEEM,
         "messages": [{"role": "user", "content": vraag}],
         "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}
    if versie in (VERSIE_NIEUW, VERSIE_V4, VERSIE_V5, VERSIE_V6):
        v.update(max_tokens=min(16000, 1000 + 1000 * len(gevraagd)), thinking={"type": "disabled"})
    if versie == VERSIE_V4:
        v["system"] = _SYSTEEM_V4
    elif versie == VERSIE_V5:
        v["system"] = _SYSTEEM_V5
    elif versie == VERSIE_V6:
        v["system"] = _SYSTEEM_V6
    if model == "sonnet" and v.get("thinking") == {"type": "disabled"}:
        v["thinking"] = {"type": "between_tools"}      # Sonnet 5.5 weigert 'disabled'; dit zet het uit bij effort low
    elif versie == VERSIE_DENKEN:
        v.update(max_tokens=min(16000, 3000 + 1000 * len(gevraagd)))
    return v


_EIGEN_SCHRIFT = {"ru": "\u0400-\u04FF", "uk": "\u0400-\u04FF", "hi": "\u0900-\u097F", "ar": "\u0600-\u06FF",
                  "fa": "\u0600-\u06FF", "ja": "\u3040-\u30FF\u4E00-\u9FFF", "zh": "\u4E00-\u9FFF"}


def gemengd(tekst: str, taal: str, origineel: str = "") -> bool:
    """Staat er in een vertaling een woord half in het eigen schrift en half in Latijnse letters ('documentируют',
    'シriraj', 'پانDYA'), terwijl het origineel dat niet heeft? Een teken dat de vertaling ontspoort. In het Japans en het
    Chinees alleen een kleine letter direct na een eigen teken: 'GitHubの' is gewoon."""
    import re

    s = _EIGEN_SCHRIFT.get(taal)
    if not s:
        return False
    patroon = rf"[{s}][a-z]" if taal in ("ja", "zh") else rf"[{s}][A-Za-z]|[A-Za-z][{s}]"
    return bool(re.search(patroon, tekst or "")) and not re.search(patroon, origineel or "")


def lees(tekst: str | None, gevraagd: list[str]) -> dict[str, str]:
    """De vertalingen uit een antwoord, per taal: alleen een taal die gevraagd was, precies één keer genoemd is en
    iets zegt."""
    try:
        rijen = json.loads(tekst or "")["vertalingen"]
        gezien = Counter(r["taal"] for r in rijen)
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}
    uit = {}
    for r in rijen:
        taal, zin = r.get("taal"), " ".join(str(r.get("tekst") or "").split())
        if taal in gevraagd and gezien[taal] == 1 and zin:
            uit[taal] = zin
    return uit


def _ronde(a: dict) -> int:
    """De ronde van een antwoord: alles van vóór #34.2x is ronde 1."""
    return a.get("ronde") or 1


def maker(taal: str) -> str:
    """Wie de vertalingen in deze doeltaal maakte, zoals de uitgave het vastlegt: het model en de vraag van haar methode."""
    from doublecheck.modellen import MODELLEN

    vraag, model = METHODE[taal].split("/")
    return f"{MODELLEN[model]['id']}, {vraag}"


def methode(a: dict) -> str:
    """De methode van een antwoord: de vraag en het model. Een antwoord zonder model is van Haiku (33.5)."""
    return f"{a.get('versie') or VERSIE}/{a.get('model') or 'haiku'}"


def _met(a: dict, taal: str, m: str | None = None) -> bool:
    return bool((a.get("vertalingen") or {}).get(taal)) and (m is None or methode(a) == m)


def eerste_ronde(antwoorden: list[dict], taal: str, m: str | None = None) -> int | None:
    """De eerste ronde waarin deze doeltaal met deze methode een vertaling kreeg: daaruit komt haar leesproef."""
    m = m or METHODE.get(taal)
    return min((_ronde(a) for a in antwoorden if _met(a, taal, m)), default=None)


def leesproef(antwoorden: list[dict], taal: str, n: int = PROEF_N, m: str | None = None) -> list[str]:
    """De nummers die voor deze doeltaal en methode nagelezen worden: honderd willekeurige uit de eerste ronde met die
    methode, per taal een eigen greep. Een latere ronde verandert haar niet (#34.2x). Een methode na de eerste trekt
    een nieuwe greep, zonder de pagina's die voor een eerdere methode in deze taal al gelezen zijn."""
    m = m or METHODE.get(taal)
    eerst = eerste_ronde(antwoorden, taal, m)
    met = {a["nummer"] for a in antwoorden if _met(a, taal, m) and _ronde(a) == eerst}
    if m == EERSTE:
        return random.Random(ZAAD + DOELTALEN.index(taal)).sample(sorted(met), min(n, len(met)))
    eerder = {methode(a) for a in antwoorden if _met(a, taal) and eerst is not None and _ronde(a) < eerst}
    gelezen = {nr for e in eerder for nr in leesproef(antwoorden, taal, n, e)}
    met = sorted(met - gelezen)
    return random.Random(f"{ZAAD}-{taal}-{m}").sample(met, min(n, len(met)))


def nieuw(antwoorden: list[dict], taal: str, m: str | None = None) -> list[str]:
    """De vertalingen in deze doeltaal met deze methode na haar eerste ronde, in de volgorde waarin ze kwamen; elk
    nummer één keer, en niet een nummer dat in de eerste ronde al een vertaling kreeg."""
    m = m or METHODE.get(taal)
    eerst = eerste_ronde(antwoorden, taal, m)
    gezien = {a["nummer"] for a in antwoorden if _met(a, taal, m) and _ronde(a) == eerst}
    uit = []
    for a in sorted(antwoorden, key=_ronde):
        if _met(a, taal, m) and _ronde(a) != eerst and a["nummer"] not in gezien:
            gezien.add(a["nummer"])
            uit.append(a["nummer"])
    return uit


def blokproef(antwoorden: list[dict], taal: str, i: int, m: str | None = None) -> list[str]:
    """De steekproef van 50 uit blok `i` van de nieuwe vertalingen, alleen als dat blok vol is; altijd dezelfde."""
    m = m or METHODE.get(taal)
    blok = nieuw(antwoorden, taal, m)[i * BLOK:(i + 1) * BLOK]
    if len(blok) < BLOK:
        return []
    zaad = f"{ZAAD_BLOK}-{taal}-{i}" if m == EERSTE else f"{ZAAD_BLOK}-{taal}-{m}-{i}"
    return random.Random(zaad).sample(sorted(blok), BLOK_N)


def _blad(pad: str | Path, m: str) -> dict:
    """Het deel van het labelbestand met de lezing van deze methode: bovenaan voor die van 33.5, anders onder
    `methoden`. Een fout bij het lezen is een leeg blad (twijfel versoepelt nooit)."""
    blad = json.loads(Path(pad).read_text(encoding="utf-8"))
    return blad if m == EERSTE else ((blad.get("methoden") or {}).get(m) or {})


def bronproef(antwoorden: list[dict], taal: str, bron: str, pad: str | Path = LABELS, n: int = PROEF_N,
              m: str | None = None) -> list[str]:
    """De nieuwe proef voor één brontaal in deze doeltaal (PLAN #34.2aa): honderd willekeurige paren uit alleen die
    brontaal, uit de eerste ronde van de methode, zonder een paar dat voor deze doeltaal al gelezen is (de eerste greep
    en wat buiten de greep gelezen is). Bij dezelfde eerste ronde altijd dezelfde."""
    m = m or METHODE.get(taal)
    eerst = eerste_ronde(antwoorden, taal, m)
    try:
        buiten = set(((_blad(pad, m).get("buiten_de_greep") or {}).get("labels") or {}).get(taal) or {})
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        buiten = set()
    weg = set(leesproef(antwoorden, taal, m=m)) | buiten
    met = sorted({a["nummer"] for a in antwoorden if _met(a, taal, m) and _ronde(a) == eerst
                  and (a.get("bron") or "und") == bron} - weg)
    return random.Random(f"{ZAAD_BRON}-{taal}-{bron}-{m}").sample(met, min(n, len(met)))


def poort(taal: str, antwoorden: list[dict], pad: str | Path = LABELS, m: str | None = None
          ) -> tuple[bool, str, frozenset[str]]:
    """Mag deze doeltaal met deze methode op de site (B32)? Na honderd gelezen paren: geen betekenisfout en geen twijfel
    zet haar aan; bij één of twee blijft de brontaal waarin het misging uit; bij drie of meer blijft de doeltaal uit.
    Een brontaal die zo uit ging, gaat weer aan na een nieuwe proef van honderd uit alleen die brontaal zonder één fout
    of twijfel (`bronproef`, PLAN #34.2aa)."""
    m = m or METHODE.get(taal)
    proef = leesproef(antwoorden, taal, m=m)
    try:
        deel = _blad(pad, m)
        labels = (deel.get("labels") or {}).get(taal, {})
        gelezen = {nr: labels[nr] for nr in proef if labels.get(nr) in GELDIG}
        bronproeven = (deel.get("bronproeven") or {}).get(taal) or {}
    except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return False, "nog niets gelezen", frozenset()
    if not proef or len(gelezen) < len(proef):
        return False, f"{len(gelezen)} van de {len(proef)} gelezen", frozenset()
    mis = [nr for nr, w in gelezen.items() if w in FOUT]
    if not mis:
        return True, f"{len(proef)} gelezen, geen betekenisfout", frozenset()
    if len(mis) >= 3:
        return False, f"{len(mis)} van de {len(proef)} fout of onzeker: de doeltaal blijft uit", frozenset()
    bron = {a["nummer"]: a.get("bron") or "und" for a in antwoorden}
    uit = {bron[nr] for nr in mis}
    waarom = f"{len(proef)} gelezen, {len(mis)} fout of onzeker; uit voor de brontaal {', '.join(sorted(uit))}"
    for b in sorted(uit & set(bronproeven)):
        nieuw = bronproef(antwoorden, taal, b, pad, m=m)
        gelezen_b = {nr: bronproeven[b][nr] for nr in nieuw if bronproeven[b].get(nr) in GELDIG}
        if len(nieuw) < PROEF_N or len(gelezen_b) < len(nieuw):
            waarom += f"; brontaal {b}: {len(gelezen_b)} van de {len(nieuw)} nieuwe gelezen"
        elif any(w in FOUT for w in gelezen_b.values()):
            waarom += f"; brontaal {b}: in de nieuwe proef weer fout of twijfel, blijft uit"
        else:
            uit.discard(b)
            waarom += f"; brontaal {b} weer aan na {len(nieuw)} nieuwe zonder fout"
    return True, waarom, frozenset(uit)


def toelating(taal: str, antwoorden: list[dict], pad: str | Path = LABELS, m: str | None = None
              ) -> tuple[bool, str, frozenset[str], frozenset[str]]:
    """De poort van B32 met wat er na de eerste ronde kwam (#34.2x): (open, waarom, brontalen die uit blijven, nummers
    die wachten). Een latere ronde met dezelfde methode gaat mee; een andere methode wacht. Na elk vol blok van 5.000
    lees ik 50: tot dan wacht wat erna komt; één fout zet haar brontaal uit, twee de hele doeltaal."""
    m = m or METHODE.get(taal)
    open_, waarom, zonder = poort(taal, antwoorden, pad, m)
    if not open_:
        return False, waarom, zonder, frozenset()
    eigen = {a["nummer"] for a in antwoorden if _met(a, taal, m)}
    anders = frozenset(a["nummer"] for a in antwoorden if _met(a, taal) and methode(a) != m) - eigen
    try:
        labels = ((_blad(pad, m).get("na_import") or {}).get("labels") or {}).get(taal) or {}
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        labels = {}
    bron = {a["nummer"]: a.get("bron") or "und" for a in antwoorden}
    rij = nieuw(antwoorden, taal, m)
    uit, wacht = set(zonder), set(anders)
    for i in range(len(rij) // BLOK):
        proef = blokproef(antwoorden, taal, i, m)
        gelezen = {nr: labels[nr] for nr in proef if labels.get(nr) in GELDIG}
        mis = [nr for nr, w in gelezen.items() if w in FOUT]
        if len(mis) >= 2:
            return False, f"blok {i + 1} na de eerste ronde: {len(mis)} van de {len(proef)} fout of onzeker: de doeltaal blijft uit", frozenset(), frozenset()
        uit |= {bron[nr] for nr in mis}
        if len(gelezen) < len(proef):
            wacht |= set(rij[(i + 1) * BLOK:])
            waarom += (f"; blok {i + 1} na de eerste ronde: {len(gelezen)} van de {len(proef)} gelezen, "
                       f"{len(rij) - (i + 1) * BLOK} wachten")
            break
    if rij:
        waarom += f"; {len(rij)} na de eerste ronde"
    if anders:
        waarom += f"; {len(anders)} met een andere methode wachten op hun eigen leesproef"
    if uit - zonder:
        waarom += f"; na een import uit voor de brontaal {', '.join(sorted(uit - zonder))}"
    return True, waarom, frozenset(uit), frozenset(wacht)


def vrijgegeven(antwoorden: list[dict], poort_van, controle: dict[str, dict[str, str]] | None = None,
                fout: frozenset[tuple[str, str]] = frozenset(),
                wacht: dict[str, frozenset[str]] | None = None,
                methode: dict[str, str] | None = None,
                originelen: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    """Per doeltaal die haar leesproef haalde de vertalingen, zonder de brontalen die uit blijven en zonder wat op een
    steekproef wacht (`wacht`, #34.2x); met `methode` alleen die van de methode van die doeltaal. Met de controle erbij
    alleen wat zij doorliet; een paar dat ik zelf fout las, nooit. Met `originelen` nooit een vertaling met een woord
    half in een ander schrift (`gemengd`, #34.2be)."""
    uit: dict[str, dict[str, str]] = {}
    for taal in DOELTALEN:
        open_, _, zonder = poort_van(taal)
        if not open_:
            continue
        houd = (wacht or {}).get(taal) or frozenset()
        per = {a["nummer"]: a["vertalingen"][taal] for a in antwoorden
               if _met(a, taal, (methode or {}).get(taal)) and (a.get("bron") or "und") not in zonder
               and a["nummer"] not in houd
               and (controle is None or doorgelaten(controle, a["nummer"], taal))
               and (taal, a["nummer"]) not in fout
               and not (originelen is not None and gemengd(a["vertalingen"][taal], taal, originelen.get(a["nummer"], "")))}
        if per:
            uit[taal] = per
    return uit


def voorlopige_vertalingen(antwoorden: list[dict], geldig: dict[str, dict[str, str]], fout: frozenset[tuple[str, str]],
                           originelen: dict[str, str], houden: set[str]) -> dict[str, dict[str, str]]:
    """De voorlopige vertalingen (B93): per doeltaal de vertalingen met de methode van die taal die hun leesproef niet
    haalden, alleen van pagina's in `houden` (wat de scan van B92 doorlaat), en nooit een die al geldig is, die ik fout las,
    in de taal van de bewering zelf, of met een woord half in een ander schrift. Een latere ronde gaat voor."""
    uit: dict[str, dict[str, str]] = {}
    for taal in DOELTALEN:
        per: dict[str, str] = {}
        for a in sorted(antwoorden, key=_ronde):
            nr = a["nummer"]
            if (not _met(a, taal, METHODE.get(taal)) or nr not in houden or nr in (geldig.get(taal) or {})
                    or (taal, nr) in fout or (a.get("bron") or "und") == taal):
                continue
            tekst = a["vertalingen"][taal]
            if not gemengd(tekst, taal, originelen.get(nr, "")):
                per[nr] = tekst
        if per:
            uit[taal] = per
    return uit


def voorlopige(geldig: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:  # pragma: no cover - bestanden
    """`voorlopige_vertalingen` op de bestanden: met de poort van de reikwijdte open alleen wat de scan doorlaat."""
    from doublecheck import reikwijdte as rw

    paginas = _paginas()
    originelen = {nr: tekst for nr, (tekst, _) in paginas.items()}
    return voorlopige_vertalingen(_jsonl(ANTWOORDEN), geldig, bekend_fout(), originelen, set(paginas))


def geldige_vertalingen() -> tuple[dict[str, dict[str, str]], dict[str, str]]:  # pragma: no cover - bestanden
    """Wat de uitgave mag meenemen, en per doeltaal waarom wel of niet. Ligt er een controle, dan geldt de poort na
    de controle."""
    antwoorden, controle, fout = _jsonl(ANTWOORDEN), _controle(), bekend_fout()
    if controle:
        def poort_van(taal):
            return poort_na(taal, antwoorden, controle)
        wacht = None
    else:
        stand = {taal: toelating(taal, antwoorden) for taal in DOELTALEN}

        def poort_van(taal):
            return stand[taal][:3]
        wacht = {taal: s[3] for taal, s in stand.items()}
    originelen = {nr: tekst for nr, (tekst, _) in _paginas().items()}
    return (vrijgegeven(antwoorden, poort_van, controle or None, fout, wacht, None if controle else METHODE, originelen),
            {taal: poort_van(taal)[1] for taal in DOELTALEN})


def samengevoegd(antwoorden: list[dict]) -> dict[str, dict]:
    """Per nummer alles wat er ligt: de vertalingen uit elke ronde samen (een latere ronde vraagt alleen wat ontbrak; bij
    twee methoden voor dezelfde taal die van de methode van nu), en welke doeltalen al met welke methode gevraagd zijn
    (`gevraagd`: paren van taal en methode). Een antwoord van vóór #34.2x vroeg de vier zonder het Engels."""
    uit: dict[str, dict] = {}
    for a in sorted(antwoorden, key=_ronde):
        x = uit.setdefault(a["nummer"], {"nummer": a["nummer"], "vertalingen": {}, "gevraagd": set()})
        x["bron"] = a.get("bron")
        for taal, tekst in (a.get("vertalingen") or {}).items():
            if taal not in x["vertalingen"] or methode(a) == METHODE.get(taal):
                x["vertalingen"][taal] = tekst
        x["gevraagd"] |= {(t, methode(a)) for t in (a["gevraagd"] if "gevraagd" in a else doelen(a.get("bron")))}
    return uit


def nog_te_vragen(antwoorden: list[dict], paginas: dict[str, tuple[str, str]], zonder_engels: set[str]
                  ) -> dict[str, list[str]]:
    """Per pagina de doeltalen die nog niet gevraagd zijn: de vier, en Engels waar het lab geen Engelse versie schreef.
    Wat gevraagd is en leeg terugkwam, wordt niet nog eens gevraagd."""
    al = samengevoegd(antwoorden)
    uit = {}
    for nr, (_, taal) in paginas.items():
        gevraagd = (al.get(nr) or {}).get("gevraagd") or set()
        nodig = [t for t in doelen(taal, engels=nr in zonder_engels, sitetalen=True) if (t, METHODE[t]) not in gevraagd]
        if nodig:
            uit[nr] = nodig
    return uit


# --- de controlestap (stap 4) -----------------------------------------------------------------------------------------

def vraagt_tweede(versie: str) -> bool:
    """Kan deze versie van de controle alleen oordelen waar een tweede lezing ligt?"""
    return bool(_CONTROLE[versie].get("zonder_origineel"))


def controleverzoek(tekst: str, taal: str, vertalingen: dict[str, str], versie: str = CONTROLE_VERSIE,
                    model: str = "haiku", tweede: str | None = None) -> dict:
    """Eén vraag over één bewering: zegt elke vertaling die er ligt hetzelfde als het origineel? `tweede` is een
    eerdere Engelse lezing van hetzelfde origineel; alleen een versie die erom vraagt, krijgt haar te zien."""
    from doublecheck.modellen import MODELLEN

    talen = [t for t in VIER if vertalingen.get(t)]       # de controle is gemeten op de vier (stap 4 van 33.5)
    schema = {"type": "object", "additionalProperties": False, "required": ["checks"], "properties": {
        "checks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["lang", "note", "verdict"],
            "properties": {"lang": {"type": "string", "enum": talen}, "note": {"type": "string"},
                           "verdict": {"type": "string", "enum": list(_OORDEEL)}}}}}}
    lezing = (f"Second reading (English, made separately):\n{tweede}\n\n"
              if tweede and _CONTROLE[versie].get("tweede") else "")
    kop = f"Original (language: {taal}):\n{(tekst or '')[:MAX_TEKENS]}\n\n" + lezing
    if vraagt_tweede(versie):
        if not tweede:
            raise Weigering(f"{versie} vergelijkt met een tweede lezing, en die is er voor deze bewering niet")
        kop = f"A (English):\n{tweede}\n\n"
    vraag = kop + "\n\n".join(f"{NAAM[t]} ({t}):\n{vertalingen[t]}" for t in talen)
    return {"model": MODELLEN[model]["id"], "max_tokens": 2000, "system": _CONTROLE[versie]["systeem"],
            "messages": [{"role": "user", "content": vraag}],
            "output_config": {"effort": _CONTROLE[versie]["effort"],
                              "format": {"type": "json_schema", "schema": schema}}}


def lees_controle(tekst: str | None, gevraagd: list[str]) -> dict[str, dict[str, str]]:
    """De oordelen uit een antwoord, per taal: alleen een taal die gevraagd was, precies één keer genoemd is en een
    oordeel draagt dat we kennen."""
    try:
        rijen = json.loads(tekst or "")["checks"]
        gezien = Counter(r["lang"] for r in rijen)
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}
    uit = {}
    for r in rijen:
        taal, oordeel = r.get("lang"), _OORDEEL.get(r.get("verdict"))
        if taal in gevraagd and gezien[taal] == 1 and oordeel:
            uit[taal] = {"oordeel": oordeel, "wat": " ".join(str(r.get("note") or "").split())[:300]}
    return uit


def doorgelaten(controle: dict[str, dict[str, str]], nummer: str, taal: str) -> bool:
    """Liet de controle deze vertaling door? Geen oordeel is niet door (twijfel versoepelt nooit)."""
    return (controle.get(nummer) or {}).get(taal) in DOOR


def bekend_fout(pad: str | Path = LABELS) -> frozenset[tuple[str, str]]:
    """De paren (doeltaal, nummer) die ik fout of onzeker noemde, in een leesproef of steekproef van welke methode ook,
    of daarbuiten (dezelfde bewering in een andere taal): die staan nooit op de site, wat de controle er ook van zegt.
    Een fout van de ene methode houdt die pagina in die taal ook voor de andere van de site (twijfel versoepelt nooit)."""
    try:
        blad = json.loads(Path(pad).read_text(encoding="utf-8"))
        delen = [blad, *((blad.get("methoden") or {}).values())]
        lagen = [laag for deel in delen for laag in (
                 deel.get("labels") or {}, (deel.get("na_controle") or {}).get("labels") or {},
                 (deel.get("buiten_de_greep") or {}).get("labels") or {}, (deel.get("na_import") or {}).get("labels") or {},
                 {taal: {nr: w for per in bronnen.values() for nr, w in per.items()}
                  for taal, bronnen in (deel.get("bronproeven") or {}).items()})]
        return frozenset((taal, nr) for laag in lagen for taal, per in laag.items() for nr, w in per.items() if w in FOUT)
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return frozenset()


def proefuitslag(pad: str | Path, oordelen: dict[str, dict[str, str]], alleen: set[str] | None = None) -> dict:
    """De controle tegen mijn eerste leesproef: hoeveel van de fouten zij meldt, en hoeveel van de goede paren van de
    site zouden verdwijnen (gemeld, of zonder oordeel). Een grensgeval (klein, met een opmerking) telt bij geen van
    beide. `alleen` telt op een deel van de beweringen; de eis blijft die op alle fouten."""
    blad = json.loads(Path(pad).read_text(encoding="utf-8"))
    opmerking = blad.get("opmerkingen") or {}
    u = {"fouten": 0, "gevangen": 0, "gemist": [], "goed": 0, "weg": 0, "zonder_oordeel": 0, "grens": 0,
         "grens_gemeld": 0, "gemeld": []}
    for taal, per in blad["labels"].items():
        for nr, label in per.items():
            if alleen is not None and nr not in alleen:
                continue
            oordeel = (oordelen.get(nr) or {}).get(taal)
            if label in FOUT:
                u["fouten"] += 1
                u["gevangen"] += oordeel == "verschil"
                if oordeel != "verschil":
                    u["gemist"].append((taal, nr))
            elif nr in (opmerking.get(taal) or {}):
                u["grens"] += 1
                u["grens_gemeld"] += oordeel == "verschil"
            else:
                u["goed"] += 1
                u["weg"] += oordeel not in DOOR
                u["zonder_oordeel"] += oordeel is None
                if oordeel == "verschil":
                    u["gemeld"].append((taal, nr))
    u["haalt"] = alleen is None and u["gevangen"] >= EIS_VANGST and u["weg"] <= EIS_WEG * u["goed"]
    return u


def leesproef_na(antwoorden: list[dict], controle: dict[str, dict[str, str]], taal: str, n: int = PROEF_N) -> list[str]:
    """De nummers voor de leesproef na de controle: honderd willekeurige die de controle doorliet en die niet in de
    eerste leesproef zaten."""
    eerder = set(leesproef(antwoorden, taal))
    met = sorted({a["nummer"] for a in antwoorden if (a.get("vertalingen") or {}).get(taal)
                  and a["nummer"] not in eerder and doorgelaten(controle, a["nummer"], taal)})
    return random.Random(ZAAD_NA + DOELTALEN.index(taal)).sample(met, min(n, len(met)))


def poort_na(taal: str, antwoorden: list[dict], controle: dict[str, dict[str, str]],
             pad: str | Path = LABELS) -> tuple[bool, str, frozenset[str]]:
    """De poort na de controlestap: dezelfde regel van B32 op de nieuwe leesproef. Een brontaal die na de eerste
    leesproef uit ging, gaat alleen weer aan als de controle de fout meldde die haar uitzette."""
    proef = leesproef_na(antwoorden, controle, taal)
    try:
        blad = json.loads(Path(pad).read_text(encoding="utf-8"))
        eerst = blad["labels"].get(taal, {})
        labels = blad["na_controle"]["labels"].get(taal, {})
        gelezen = {nr: labels[nr] for nr in proef if labels.get(nr) in GELDIG}
    except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return False, "na de controle nog niets gelezen", frozenset()
    if not proef or len(gelezen) < len(proef):
        return False, f"na de controle {len(gelezen)} van de {len(proef)} gelezen", frozenset()
    mis = [nr for nr, w in gelezen.items() if w in FOUT]
    if len(mis) >= 3:
        return False, f"na de controle {len(mis)} van de {len(proef)} fout of onzeker: de doeltaal blijft uit", frozenset()
    bron = {a["nummer"]: a.get("bron") or "und" for a in antwoorden}
    blijft = {bron[nr] for nr, w in eerst.items()
              if w in FOUT and nr in bron and (controle.get(nr) or {}).get(taal) != "verschil"}
    uit = frozenset({bron[nr] for nr in mis} | blijft)
    waarom = (f"na de controle {len(proef)} gelezen, "
              + ("geen betekenisfout" if not mis else f"{len(mis)} fout of onzeker"))
    return True, waarom + (f"; uit voor de brontaal {', '.join(sorted(uit))}" if uit else ""), uit


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for rij in rijen:
            f.write(json.dumps(rij, ensure_ascii=False) + "\n")


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    return sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)


def _paginas() -> dict[str, tuple[str, str]]:  # pragma: no cover - een bestand
    """Elke pagina met een taal: nummer -> (bewering, taal). De taal is de herstelde uit de uitgave. Met de poort van de
    reikwijdte open (B92) niet wat als lokaal of persoonlijk gelezen is: dat blijft in de taal van de redactie."""
    from doublecheck import reikwijdte as rw

    alle = {nr: (tekst, taal) for nr, tekst, taal in _publicatie().execute("SELECT nummer, bewering, taal FROM pagina")
            if doelen(taal)}
    if not rw.filter_open():
        return alle
    houden = rw.te_vertalen(rw._jsonl(rw.VOL), {nr: tekst for nr, (tekst, _) in alle.items()})
    return {nr: v for nr, v in alle.items() if nr in houden}


def _zonder_engels() -> set[str]:  # pragma: no cover - een bestand
    """De pagina's in een andere taal dan het Engels zonder Engelse versie uit het lab (#25.17): daar vraagt de
    vertaalstap ook Engels (#34.2x). Een Engelse versie van de vertaalstap zelf telt hier niet."""
    conn = _publicatie()
    lab = {nr for nr, maker in conn.execute("SELECT pagina, maker FROM vertaling WHERE taal = 'en'") if VERSIE not in maker}
    return {nr for nr, taal in conn.execute("SELECT nummer, taal FROM pagina") if doelen(taal) and taal != "en"
            and nr not in lab}


def _uitgegeven(nieuw: bool = False) -> float:  # pragma: no cover - bestanden
    """Wat voor de vertalingen en hun controle is uitgegeven, onder `GRENS`; met `nieuw` wat voor de tien nieuwe talen
    is uitgegeven (hun proef en hun batches), onder `GRENS_NIEUW`."""
    batches = [b for b in _jsonl(BATCHES) if van_nieuw(b) == nieuw] + ([] if nieuw else _jsonl(CONTROLE_BATCHES))
    los = _jsonl(PROEF_NIEUW) if nieuw else _jsonl(ANTWOORDEN) + _jsonl(CONTROLE_PROEF)
    return (sum(a.get("kosten", 0.0) for a in los)
            + sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"] for b in batches))


def _controle() -> dict[str, dict[str, str]]:  # pragma: no cover - bestanden
    """De oordelen van de volle ronde: nummer -> {doeltaal: oordeel}."""
    return {r["nummer"]: {taal: o["oordeel"] for taal, o in (r.get("oordelen") or {}).items()}
            for r in _jsonl(CONTROLE)}


def _tweede() -> dict[str, str]:  # pragma: no cover - een bestand
    """De Engelse versie die al in de uitgave staat (#25.17, nagelezen in §117): een tweede lezing van het origineel."""
    return dict(_publicatie().execute("SELECT pagina, tekst FROM vertaling WHERE taal = 'en' AND maker NOT LIKE ?",
                                      (f"%{VERSIE}%",)))


def _proefoordelen(versie: str, model: str) -> dict[str, dict]:  # pragma: no cover - bestanden
    return {r["nummer"]: r for r in _jsonl(CONTROLE_PROEF) if r["versie"] == versie and r["model"] == model}


def _controleproef(versie: str, model: str, wacht: int = 0) -> None:  # pragma: no cover - een model
    """De controle op de paren van de eerste leesproef. Hoogstens drie versies met Haiku, direct; Sonnet één keer, via
    de Batch API."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = {(r["versie"], r["model"]) for r in _jsonl(CONTROLE_PROEF)}
    if (versie, model) not in eerder:
        if model == "haiku" and len({v for v, m in eerder if m == "haiku"}) >= 3:
            raise Weigering("geweigerd: er zijn al drie versies op de gelezen paren gemeten")
        if model != "haiku" and any(m == model for _, m in eerder):
            raise Weigering(f"geweigerd: {model} is al een keer op de gelezen paren gemeten")
    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"]
    nummers = sorted({nr for per in labels.values() for nr in per})
    paginas, laatste, tweede = _paginas(), samengevoegd(_jsonl(ANTWOORDEN)), _tweede()
    klaar = _proefoordelen(versie, model)
    werk = [nr for nr in nummers if nr not in klaar and nr in paginas
            and (tweede.get(nr) or not vraagt_tweede(versie))]
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN[model]

    def een(nr: str) -> dict:
        tekst, taal = paginas[nr]
        vertalingen = laatste[nr]["vertalingen"]
        msg = client.messages.create(**controleverzoek(tekst, taal, vertalingen, versie, model, tweede.get(nr)))
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        antwoord = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        return {"nummer": nr, "bron": taal, "oordelen": lees_controle(antwoord, list(vertalingen)), "versie": versie,
                "model": model, "kosten": round(kosten, 7),
                "tokens": [msg.usage.input_tokens, msg.usage.output_tokens]}

    if model != "haiku" and werk:
        # het sterkere model via de Batch API (de helft van de prijs, openbare beweringen): de schatting komt uit de
        # tokens die Haiku voor dezelfde vraag gebruikte
        haiku = _proefoordelen(versie, "haiku")
        if not haiku:
            raise Weigering("eerst dezelfde versie met Haiku: die meet de tokens voor de schatting")
        schatting = sum(haiku[nr]["tokens"][0] * prijs["in"] + haiku[nr]["tokens"][1] * prijs["uit"]
                        for nr in werk if nr in haiku) / 1e6
        if schatting > GRENS_SONNET:
            raise Weigering(f"geweigerd: geschat ${schatting:.2f} is meer dan ${GRENS_SONNET:.2f}")
        lopend = MAP / f"controle-proef-{versie}-{model}.batch"
        if lopend.exists():
            batch_id = lopend.read_text(encoding="utf-8").strip()
        else:
            batch_id = client.messages.batches.create(requests=[
                {"custom_id": nr, "params": controleverzoek(*paginas[nr], laatste[nr]["vertalingen"], versie, model,
                                                            tweede.get(nr))} for nr in werk]).id
            lopend.write_text(batch_id, encoding="utf-8")
            print(f"batch {batch_id}: {len(werk)} beweringen, geschat ${schatting:.2f}", flush=True)
        einde = time.time() + 60 * wacht
        while client.messages.batches.retrieve(batch_id).processing_status != "ended":
            if time.time() > einde:
                print(f"batch {batch_id} loopt nog; draai dit commando opnieuw")
                return
            time.sleep(30)
        rijen = []
        for r in client.messages.batches.results(batch_id):
            gelezen, kosten, tokens = {}, 0.0, [0, 0]
            if r.result.type == "succeeded":
                msg = r.result.message
                tokens = [msg.usage.input_tokens, msg.usage.output_tokens]
                kosten = (tokens[0] * prijs["in"] + tokens[1] * prijs["uit"]) / 1e6
                tekst = None if msg.stop_reason == "max_tokens" else "".join(
                    getattr(b, "text", "") or "" for b in msg.content)
                gelezen = lees_controle(tekst, list(laatste[r.custom_id]["vertalingen"]))
            rijen.append({"nummer": r.custom_id, "bron": paginas[r.custom_id][1], "oordelen": gelezen,
                          "versie": versie, "model": model, "kosten": round(kosten, 7), "tokens": tokens,
                          "batch": True})
        _schrijf(CONTROLE_PROEF, rijen)
        lopend.unlink()
        werk = []
    for begin in range(0, len(werk), 40):
        deel = werk[begin:begin + 40]
        with ThreadPoolExecutor(8) as pool:
            rijen = list(pool.map(een, deel))
        _schrijf(CONTROLE_PROEF, rijen)
    alles = list(_proefoordelen(versie, model).values())
    # wat een bewering via de batch kost: een directe vraag kostte het dubbele
    per = sum(r["kosten"] / (1 if r.get("batch") else 2) for r in alles) / max(1, len(alles))
    n = sum(1 for a in laatste.values() if a.get("vertalingen"))
    print(f"{versie} met {model}: {len(alles)} beweringen, ${sum(r['kosten'] for r in alles):.3f} uitgegeven; gemiddeld "
          f"{sum(r['tokens'][0] for r in alles) / len(alles):.0f} tokens in en "
          f"{sum(r['tokens'][1] for r in alles) / len(alles):.0f} uit; via de batch ${per:.6f} per bewering, "
          f"voor {n} beweringen ${per * n:.2f}; uitgegeven ${_uitgegeven():.2f} van ${GRENS:.2f}")


def _controletellen() -> None:  # pragma: no cover - bestanden
    """Elke gemeten versie tegen mijn eerste leesproef, met wat zij miste en wat zij van de goede paren meldde."""
    for versie, model in sorted({(r["versie"], r["model"]) for r in _jsonl(CONTROLE_PROEF)}):
        rijen = _proefoordelen(versie, model)
        oordelen = {nr: {taal: o["oordeel"] for taal, o in r["oordelen"].items()} for nr, r in rijen.items()}
        u = proefuitslag(LABELS, oordelen, set(rijen) if vraagt_tweede(versie) else None)
        if vraagt_tweede(versie):
            print(f"\n{versie} oordeelt alleen over de {len(rijen)} beweringen met een tweede lezing:", end="")
        print(f"\n{versie} met {model}: {u['gevangen']} van de {u['fouten']} fouten gemeld (eis {EIS_VANGST}); "
              f"{u['weg']} van de {u['goed']} goede weg (eis hoogstens {EIS_WEG * u['goed']:.0f}), waarvan "
              f"{u['zonder_oordeel']} zonder oordeel; {u['grens_gemeld']} van de {u['grens']} grensgevallen gemeld; "
              f"haalt de eisen: {'ja' if u['haalt'] else 'nee'}")
        for taal, nr in u["gemist"]:
            print(f"  gemist  {taal} {nr}: {(oordelen.get(nr) or {}).get(taal)}")
        for taal, nr in u["gemeld"]:
            print(f"  gemeld  {taal} {nr} [{rijen[nr]['bron']}]: {rijen[nr]['oordelen'][taal]['wat']}")


def _controle_indienen(versie: str) -> None:  # pragma: no cover - de Batch API
    import anthropic

    from doublecheck.varianten import laad_sleutel

    proef = _proefoordelen(versie, "haiku")
    if not proef:
        raise Weigering("eerst de proef op de gelezen paren")
    u = proefuitslag(LABELS, {nr: {taal: o["oordeel"] for taal, o in r["oordelen"].items()} for nr, r in proef.items()})
    if not u["haalt"]:
        raise Weigering(f"geweigerd: {versie} haalt de eisen niet ({u['gevangen']} van de {u['fouten']} fouten gemeld, "
                        f"{u['weg']} van de {u['goed']} goede weg)")
    paginas, tweede = _paginas(), _tweede()
    laatste = {nr: x for nr, x in samengevoegd(_jsonl(ANTWOORDEN)).items() if x["vertalingen"]}
    klaar = {r["nummer"] for r in _jsonl(CONTROLE)}
    onderweg = {nr for b in _jsonl(CONTROLE_BATCHES) if b.get("werkelijk") is None for nr in b["nummers"]}
    werk = sorted(set(laatste) & set(paginas) - klaar - onderweg)
    if not werk:
        print("niets in te dienen")
        return
    per = sum(r["kosten"] for r in proef.values()) / len(proef) / 2
    if _uitgegeven() + per * len(werk) > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${per * len(werk):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client = anthropic.Anthropic()
    for begin in range(0, len(werk), PORTIE):
        deel = werk[begin:begin + PORTIE]
        batch = client.messages.batches.create(requests=[
            {"custom_id": nr, "params": controleverzoek(*paginas[nr], laatste[nr]["vertalingen"], versie,
                                                        tweede=tweede.get(nr))} for nr in deel])
        _schrijf(CONTROLE_BATCHES, [{"id": batch.id, "nummers": deel, "versie": versie,
                                     "schatting": round(per * len(deel), 2)}])
        print(f"batch {batch.id}: {len(deel)} beweringen, schatting ${per * len(deel):.2f}", flush=True)
    print(f"samen ${_uitgegeven():.2f} van ${GRENS:.2f}")


def _controle_ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laatste = {nr: x for nr, x in samengevoegd(_jsonl(ANTWOORDEN)).items() if x["vertalingen"]}
    batches = _jsonl(CONTROLE_BATCHES)
    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, rijen, leeg = 0.0, [], 0
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id not in laatste:
                    continue
                gelezen = {}
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += kosten_batch(bc.gebruik_uit(msg), "haiku")
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                    gelezen = lees_controle(tekst, list(laatste[r.custom_id]["vertalingen"]))
                leeg += not gelezen
                rijen.append({"nummer": r.custom_id, "oordelen": gelezen, "versie": b["versie"]})
            _schrijf(CONTROLE, rijen)
            b["werkelijk"], b["zonder_antwoord"] = round(werkelijk, 4), leeg
            print(f"batch {b['id']}: {len(rijen)} beweringen, {leeg} zonder oordeel, ${werkelijk:.2f}", flush=True)
        CONTROLE_BATCHES.write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; ${_uitgegeven():.2f} van ${GRENS:.2f}")


def past(uitgegeven: float, schatting: float, grens: float, marge: float = MARGE) -> bool:
    """Blijft wat al uitgegeven is plus de schatting, met ruimte voor een schatting die ernaast zit, binnen de grens?"""
    return uitgegeven + schatting * marge <= grens


def batchverzoek(nummer: str, pagina: tuple[str, str], gevraagd: list[str], methode: str,
                 engels: dict[str, str]) -> dict:
    """Eén vraag voor de Batch API: de methode (vraag en model) van de doeltalen, met de Engelse versie als hulp voor de
    vragen die haar gebruiken (v4 tot v6)."""
    versie, model = methode.split("/")
    hulp = engels.get(nummer) if versie in (VERSIE_V4, VERSIE_V5, VERSIE_V6) else None
    return {"custom_id": nummer, "params": verzoek(*pagina, gevraagd, model, versie, engels=hulp)}


def kosten_vraag(rijen: list[dict], k: int, prijs: dict) -> float:
    """Wat één vraag met `k` doeltalen kost via de batch, uit een proef: de gemiddelde invoer per vraag (die telt één keer)
    en de uitvoer per gevraagde taal. `prijs` in dollar per miljoen tokens (de batchprijs van `modellen`)."""
    invoer = sum(r["tokens"][0] for r in rijen) / len(rijen)
    per_taal = sum(r["tokens"][1] for r in rijen) / sum(len(r["gevraagd"]) for r in rijen)
    return (invoer * prijs["in"] + k * per_taal * prijs["uit"]) / 1e6


def per_doeltaal(batches: list[dict], versie: str | None = None) -> float | None:
    """Wat één vertaling in één doeltaal met Haiku kostte: de werkelijke kosten gedeeld door wat er gevraagd werd, op de
    batches van Haiku die bijhielden wat ze vroegen (#34.2x), met `versie` alleen die van die vraag (de tien nieuwe talen
    vragen zonder denkwerk, #34.2be). Zonder zo'n batch niets."""
    kosten = vragen = 0
    for b in batches:
        if versie is not None and (b.get("versie") or VERSIE) != versie:
            continue
        if b.get("werkelijk") is not None and b.get("gevraagd") and (b.get("model") or "haiku") == "haiku":
            kosten += b["werkelijk"]
            vragen += sum(len(t) for t in b["gevraagd"].values())
    return kosten / vragen if vragen else None


def _per_bewering() -> float:  # pragma: no cover - bestanden
    """De gemeten kosten per bewering via de batch: de helft van wat de proef direct kostte."""
    proef = [a["kosten"] for a in _jsonl(ANTWOORDEN) if a.get("kosten")]
    if not proef:
        raise Weigering("eerst de proef: die meet de kosten per bewering")
    return sum(proef) / len(proef) / 2


def _proef(n: int) -> None:  # pragma: no cover - een model
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    if _jsonl(ANTWOORDEN):
        raise Weigering("geweigerd: de proef hoort vóór de eerste ronde; een proef nu zou in de greep van de leesproef "
                        "komen (#34.2x). De kosten per bewering zijn al gemeten")
    werk = random.Random(ZAAD).sample(sorted(paginas), n)
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN["haiku"]

    def een(nr: str) -> dict:
        tekst, taal = paginas[nr]
        msg = client.messages.create(**verzoek(tekst, taal))
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        antwoord = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        return {"nummer": nr, "bron": taal, "vertalingen": lees(antwoord, doelen(taal)), "versie": VERSIE,
                "kosten": round(kosten, 7)}

    with ThreadPoolExecutor(8) as pool:
        rijen = list(pool.map(een, werk))
    _schrijf(ANTWOORDEN, rijen)
    alles = [a for a in _jsonl(ANTWOORDEN) if a.get("kosten")]
    per = sum(a["kosten"] for a in alles) / max(1, len(alles))
    print(f"{len(rijen)} gevraagd; ${per:.6f} per bewering direct, ${per / 2:.6f} via de batch; "
          f"voor {len(paginas)} beweringen ${per / 2 * len(paginas):.2f}")


def _proef_nieuw(n: int, versie: str = VERSIE_NIEUW) -> None:  # pragma: no cover - een model
    """De kosten en een eerste blik op de tien nieuwe talen (#34.2be): `n` willekeurige beweringen direct gevraagd met
    `versie`, in een eigen bestand. Telt niet als ronde, dus niet in de leesproef; in de batch worden ze opnieuw
    gevraagd. Met `weergave-v3` dezelfde beweringen als de eerste proef en daarna nieuwe, met naast elkaar hoe vaak een
    woord half in een ander schrift staat bij v2 en v3."""
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    if _uitgegeven(nieuw=True) + 1.0 > GRENS_NIEUW:
        raise Weigering(f"geweigerd: ${_uitgegeven(nieuw=True):.2f} van ${GRENS_NIEUW:.2f} al uitgegeven")
    gezien = {r["nummer"] for r in _jsonl(PROEF_NIEUW) if (r.get("versie") or VERSIE_NIEUW) == versie}
    werk = [nr for nr in random.Random(ZAAD + 99).sample(sorted(paginas), n + len(gezien)) if nr not in gezien][:n]
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN["haiku"]

    def een(nr: str) -> dict:
        tekst, taal = paginas[nr]
        gevraagd = [t for t in NIEUW if t != taal]
        msg = client.messages.create(**verzoek(tekst, taal, gevraagd, versie=versie))
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        antwoord = None if msg.stop_reason == "max_tokens" else "".join(
            getattr(b, "text", "") or "" for b in msg.content if getattr(b, "type", "") == "text")
        return {"nummer": nr, "bron": taal, "gevraagd": gevraagd, "vertalingen": lees(antwoord, gevraagd),
                "versie": versie, "kosten": round(kosten, 7), "stop": msg.stop_reason,
                "tokens": [msg.usage.input_tokens, msg.usage.output_tokens]}

    with ThreadPoolExecutor(8) as pool:
        rijen = list(pool.map(een, werk))
    _schrijf(PROEF_NIEUW, rijen)
    alles = [r for r in _jsonl(PROEF_NIEUW) if (r.get("versie") or VERSIE_NIEUW) == versie]
    if versie != VERSIE_NIEUW:
        # dezelfde beweringen met de eerste vraag, uit de volle ronde: hoe vaak een woord half in een ander schrift staat
        v2 = {a["nummer"]: a["vertalingen"] for a in _jsonl(ANTWOORDEN) if a.get("versie") == VERSIE_NIEUW}
        for t in _EIGEN_SCHRIFT:
            paren = [(r["vertalingen"].get(t), (v2.get(r["nummer"]) or {}).get(t), paginas[r["nummer"]][0])
                     for r in alles if r["nummer"] in v2]
            print(f"  {t}: gemengd met denkwerk {sum(gemengd(a, t, o) for a, _, o in paren if a)}, zonder "
                  f"{sum(gemengd(b, t, o) for _, b, o in paren if b)}, van {sum(1 for a, _, _ in paren if a)}")
    vragen = sum(len(r["gevraagd"]) for r in alles)
    per = sum(r["kosten"] for r in alles) / 2 / vragen
    nodig = sum(len(t) for nr, t in nog_te_vragen(_jsonl(ANTWOORDEN), paginas, set()).items()
                for t in [[x for x in t if x in NIEUW]])
    leeg = sum(1 for r in alles for t in r["gevraagd"] if t not in r["vertalingen"])
    print(f"{len(rijen)} gevraagd, samen {len(alles)} in de proef; {leeg} van de {vragen} vertalingen leeg; gemiddeld "
          f"{sum(r['tokens'][0] for r in alles) / len(alles):.0f} tokens in en "
          f"{sum(r['tokens'][1] for r in alles) / len(alles):.0f} uit per bewering")
    print(f"via de batch ${per:.7f} per vertaling; nog {nodig} vertalingen in de tien talen: ${per * nodig:.2f} "
          f"(met marge ${per * nodig * MARGE:.2f}); uitgegeven ${_uitgegeven(nieuw=True):.2f} van ${GRENS_NIEUW:.2f}")


def _proef_greep(talen: list[str], versie: str = VERSIE_V6, vragen: list[str] | None = None,
                 model: str = "haiku") -> None:  # pragma: no cover - een model
    """Een nieuwe vraag op precies de beweringen van de leesproef van `talen` (PLAN #34.2be): vertaald in de negen talen
    die niet door de poort kwamen, direct, in het eigen proefbestand. Per taal een bestand met de oude en de nieuwe
    vertaling naast elkaar en mijn oude label, om te lezen of de fouten weg zijn en het goede goed blijft."""
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paginas, antwoorden, tweede = _paginas(), _jsonl(ANTWOORDEN), _tweede()
    negen = vragen or [t for t in NIEUW if t != "fa"]
    def van_proef(r: dict) -> bool:
        return r.get("versie") == versie and (r.get("model") or "haiku") == model

    gezien = {r["nummer"] for r in _jsonl(PROEF_NIEUW) if van_proef(r)}
    greep = {t: leesproef(antwoorden, t) for t in talen}
    werk = sorted({nr for nrs in greep.values() for nr in nrs} - gezien)
    schatting = (0.0005 if model == "haiku" else 0.005) * len(werk)
    if not past(_uitgegeven(nieuw=True), schatting, GRENS_NIEUW):
        raise Weigering(f"geweigerd: ${_uitgegeven(nieuw=True):.2f} plus ${schatting:.2f} is meer dan ${GRENS_NIEUW:.2f}")
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN[model]

    def een(nr: str) -> dict:
        tekst, taal = paginas[nr]
        gevraagd = [t for t in negen if t != taal]
        msg = client.messages.create(**verzoek(tekst, taal, gevraagd, model, versie, engels=tweede.get(nr)))
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        antwoord = None if msg.stop_reason == "max_tokens" else "".join(
            getattr(b, "text", "") or "" for b in msg.content if getattr(b, "type", "") == "text")
        return {"nummer": nr, "bron": taal, "gevraagd": gevraagd, "vertalingen": lees(antwoord, gevraagd),
                "versie": versie, "model": model, "kosten": round(kosten, 7), "stop": msg.stop_reason,
                "tokens": [msg.usage.input_tokens, msg.usage.output_tokens]}

    with ThreadPoolExecutor(8) as pool:
        _schrijf(PROEF_NIEUW, list(pool.map(een, werk)))
    nieuw_ = {r["nummer"]: r for r in _jsonl(PROEF_NIEUW) if van_proef(r)}
    oud = {a["nummer"]: a["vertalingen"] for a in antwoorden if a.get("versie") == VERSIE_NIEUW}
    blad = (json.loads(LABELS.read_text(encoding="utf-8")).get("methoden") or {}).get(f"{VERSIE_NIEUW}/haiku") or {}
    for t, nrs in greep.items():
        labels, noten = (blad.get("labels") or {}).get(t) or {}, (blad.get("opmerkingen") or {}).get(t) or {}
        uit = [{"nummer": nr, "bron": paginas[nr][1], "origineel": paginas[nr][0][:MAX_TEKENS], "engels": tweede.get(nr, ""),
                "oud": (oud.get(nr) or {}).get(t, ""), "oud_label": labels.get(nr), "oud_noot": noten.get(nr, ""),
                "nieuw": (nieuw_.get(nr) or {}).get("vertalingen", {}).get(t, "")} for nr in nrs]
        naam = f"proef-{versie}-{t}.json" if model == "haiku" else f"proef-{versie}-{model}-{t}.json"
        (MAP / naam).write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{t}: {len(uit)} beweringen, {sum(1 for u in uit if u['oud_label'] in FOUT)} oude fouten; gemengd oud "
              f"{sum(gemengd(u['oud'], t, u['origineel']) for u in uit)}, nieuw {sum(gemengd(u['nieuw'], t, u['origineel']) for u in uit)}")
    alles = list(nieuw_.values())
    per = sum(r["kosten"] for r in alles) / 2 / sum(len(r["gevraagd"]) for r in alles)
    print(f"{model}: per bewering met één taal via de batch ${kosten_vraag(alles, 1, prijs):.6f}, "
          f"met twee talen ${kosten_vraag(alles, 2, prijs):.6f}")
    print(f"via de batch ${per:.7f} per vertaling, ${per * 9 * len(paginas):.2f} voor de negen talen samen; gemiddeld "
          f"{sum(r['tokens'][0] for r in alles) / len(alles):.0f} tokens in, {sum(r['tokens'][1] for r in alles) / len(alles):.0f} "
          f"uit; uitgegeven ${_uitgegeven(nieuw=True):.2f} van ${GRENS_NIEUW:.2f}")


def _per_vertaling(versie: str, model: str, batches: list[dict]) -> float:  # pragma: no cover - bestanden
    """De schatting per vertaling in één doeltaal: uit de batches van die vraag, anders uit haar proef."""
    from doublecheck.modellen import MODELLEN

    if versie in NIEUWE_VERSIES:
        gemeten = per_doeltaal(batches, versie)
        if gemeten is None:
            proef = [r for r in _jsonl(PROEF_NIEUW) if (r.get("versie") or VERSIE_NIEUW) == versie]
            if not proef:
                raise Weigering("eerst de proef van de nieuwe talen: `proef --nieuw`")
            gemeten = sum(r["kosten"] for r in proef) / 2 / sum(len(r["gevraagd"]) for r in proef)
        return gemeten * MODELLEN[model]["uit"] / MODELLEN["haiku"]["uit"]
    per_taal = per_doeltaal(batches, VERSIE) or _per_bewering() / 3
    return per_taal * MODELLEN[model]["uit"] / MODELLEN["haiku"]["uit"]


def _indienen() -> None:  # pragma: no cover - de Batch API
    import anthropic

    from doublecheck.varianten import laad_sleutel

    paginas, antwoorden = _paginas(), _jsonl(ANTWOORDEN)
    batches = _jsonl(BATCHES)
    onderweg = {nr for b in batches if b.get("werkelijk") is None for nr in b["nummers"]}
    nodig = nog_te_vragen(antwoorden, paginas, _zonder_engels())
    werk = sorted(set(nodig) - onderweg)
    if not werk:
        print("niets in te dienen")
        return
    # elke keer indienen is een nieuwe ronde: de leesproef van een doeltaal blijft in haar eerste (#34.2x). Per methode
    # (de vraag en het model) een eigen vraag: de doeltalen van een pagina gaan samen naar de methode van hun taal
    ronde = max([_ronde(a) for a in antwoorden] + [b.get("ronde") or 1 for b in batches], default=1) + 1
    per_methode: dict[str, dict[str, list[str]]] = {}
    for nr in werk:
        for t in nodig[nr]:
            per_methode.setdefault(METHODE[t], {}).setdefault(nr, []).append(t)
    per = {m: _per_vertaling(*m.split("/"), batches) for m in per_methode}
    schatting = {m: per[m] * sum(len(t) for t in w.values()) for m, w in per_methode.items()}
    # voor de nieuwe vragen: per vraag, uit hun proef, want de invoer telt per vraag en niet per taal
    from doublecheck.modellen import MODELLEN

    for m, w in per_methode.items():
        versie, model = m.split("/")
        proef = [r for r in _jsonl(PROEF_NIEUW) if r.get("versie") == versie and r.get("tokens")]
        if proef and model == "haiku":
            schatting[m] = sum(kosten_vraag(proef, len(t), MODELLEN["haiku"]) for t in w.values())
            per[m] = schatting[m] / max(1, sum(len(t) for t in w.values()))
    oud = sum(k for m, k in schatting.items() if not van_nieuw({"versie": m.split("/")[0]}))
    nieuw_ = sum(k for m, k in schatting.items() if van_nieuw({"versie": m.split("/")[0]}))
    from doublecheck import routinegrens as rg

    if rg.uitgave():                # onder de routine per week telt haar grens, niet die voor altijd (PLAN #35.2)
        if not rg.past(oud + nieuw_, MARGE):
            raise Weigering(f"geweigerd: ${oud + nieuw_:.2f} (x {MARGE}) past niet in de ruimte van de routine "
                            f"(${rg.ruimte():.2f})")
    elif oud and not past(_uitgegeven(), oud, GRENS):
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${oud:.2f} (x {MARGE}) is meer dan ${GRENS:.2f}")
    elif nieuw_ and not past(_uitgegeven(nieuw=True), nieuw_, GRENS_NIEUW):
        raise Weigering(f"geweigerd: voor de nieuwe talen ${_uitgegeven(nieuw=True):.2f} uitgegeven plus ${nieuw_:.2f} "
                        f"(x {MARGE}) is meer dan ${GRENS_NIEUW:.2f}")
    laad_sleutel()
    client = anthropic.Anthropic()
    tweede = _tweede()
    for m, gevraagd in sorted(per_methode.items()):
        versie, model = m.split("/")
        nummers = sorted(gevraagd)
        for begin in range(0, len(nummers), PORTIE):
            deel = nummers[begin:begin + PORTIE]
            batch = client.messages.batches.create(requests=[
                batchverzoek(nr, paginas[nr], gevraagd[nr], m, tweede) for nr in deel])
            kost = per[m] * sum(len(gevraagd[nr]) for nr in deel)
            _schrijf(BATCHES, [rg.merk({"id": batch.id, "nummers": deel, "schatting": round(kost, 2), "ronde": ronde,
                                        "model": model, "versie": versie, "gevraagd": {nr: gevraagd[nr] for nr in deel}})])
            print(f"batch {batch.id}: ronde {ronde}, {m}, {len(deel)} beweringen, "
                  f"{sum(len(gevraagd[nr]) for nr in deel)} vertalingen, schatting ${kost:.2f}", flush=True)
    print(f"samen ${_uitgegeven():.2f} van ${GRENS:.2f}; nieuwe talen ${_uitgegeven(nieuw=True):.2f} van ${GRENS_NIEUW:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    batches = _jsonl(BATCHES)
    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, rijen, leeg = 0.0, [], 0
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id not in paginas:
                    continue
                taal = paginas[r.custom_id][1]
                gevraagd = (b.get("gevraagd") or {}).get(r.custom_id) or doelen(taal)
                model = b.get("model") or "haiku"
                gelezen = {}
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += kosten_batch(bc.gebruik_uit(msg), model)
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                    gelezen = lees(tekst, gevraagd)
                leeg += not gelezen
                rij = {"nummer": r.custom_id, "bron": taal, "vertalingen": gelezen, "versie": b.get("versie") or VERSIE}
                if b.get("ronde"):
                    rij.update(ronde=b["ronde"], gevraagd=gevraagd)
                if b.get("model"):
                    rij["model"] = b["model"]
                rijen.append(rij)
            _schrijf(ANTWOORDEN, rijen)
            b["werkelijk"], b["zonder_antwoord"] = round(werkelijk, 4), leeg
            print(f"batch {b['id']}: {len(rijen)} beweringen, {leeg} zonder vertaling, ${werkelijk:.2f}", flush=True)
        BATCHES.write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; ${_uitgegeven():.2f} van ${GRENS:.2f}; nieuwe talen "
          f"${_uitgegeven(nieuw=True):.2f} van ${GRENS_NIEUW:.2f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["proef", "plan", "indienen", "ophalen", "lezen", "tellen", "controle"])
    p.add_argument("deel", nargs="?", choices=["proef", "tellen", "indienen", "ophalen"])
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--wacht", type=int, default=0)
    p.add_argument("--taal", choices=DOELTALEN)
    p.add_argument("--ronde", type=int, choices=[1, 2], default=1)
    p.add_argument("--bron", help="lezen: de nieuwe proef voor deze brontaal (#34.2aa)")
    p.add_argument("--import", dest="na_import", action="store_true",
                   help="lezen: de steekproef van 50 uit elk vol blok na de eerste ronde (#34.2x)")
    p.add_argument("--versie", choices=sorted(_CONTROLE), default=CONTROLE_VERSIE)
    p.add_argument("--model", choices=["haiku", "sonnet"], default="haiku")
    p.add_argument("--nieuw", action="store_true", help="proef: de tien nieuwe talen (#34.2be), in een eigen bestand")
    p.add_argument("--denken", action="store_true", help="proef --nieuw: de vraag mét denkwerk (weergave-v3)")
    p.add_argument("--greep", help="proef --nieuw: weergave-v4 op de beweringen van de leesproef van deze talen (pt,hi,...)")
    a = p.parse_args()
    try:
        if a.stap == "controle":
            if a.deel == "proef":
                return _controleproef(a.versie, a.model, a.wacht)
            if a.deel == "tellen":
                return _controletellen()
            if a.deel == "indienen":
                return _controle_indienen(a.versie)
            if a.deel == "ophalen":
                return _controle_ophalen(a.wacht)
            raise Weigering("controle vraagt proef, tellen, indienen of ophalen")
        if a.stap == "proef":
            if a.nieuw and a.greep:
                return _proef_greep(a.greep.split(","), vragen=a.greep.split(","), model=a.model)
            return _proef_nieuw(a.n, VERSIE_DENKEN if a.denken else VERSIE_NIEUW) if a.nieuw else _proef(a.n)
        if a.stap == "indienen":
            return _indienen()
        if a.stap == "ophalen":
            return _ophalen(a.wacht)
        paginas = _paginas()
        antwoorden = _jsonl(ANTWOORDEN)
        if a.stap == "plan":
            nodig = nog_te_vragen(antwoorden, paginas, _zonder_engels())
            batches = _jsonl(BATCHES)
            telling = Counter(t for talen in nodig.values() for t in talen)
            schatting = Counter()
            for t, n in telling.items():
                schatting[METHODE[t]] += n * _per_vertaling(*METHODE[t].split("/"), batches)
            print(f"{len(paginas)} beweringen met een taal; nog te vragen voor {len(nodig)}, per doeltaal: "
                  f"{ {t: f'{n} met {METHODE[t]}' for t, n in telling.items()} }")
            print(f"geschat via de batch: { {m: round(k, 2) for m, k in schatting.items()} }; al uitgegeven "
                  f"${_uitgegeven():.2f} van ${GRENS:.2f}, nieuwe talen ${_uitgegeven(nieuw=True):.2f} van "
                  f"${GRENS_NIEUW:.2f} (marge x {MARGE})")
            return
        if a.stap == "lezen":
            if not a.taal:
                raise Weigering("lezen vraagt --taal")
            m = METHODE[a.taal]
            laatste = samengevoegd(antwoorden)
            tekst_van = {x["nummer"]: x["vertalingen"][a.taal] for x in antwoorden if _met(x, a.taal, m)}
            engels = dict(_publicatie().execute(
                "SELECT pagina, tekst FROM vertaling WHERE taal = 'en' AND maker NOT LIKE ?", (f"%{VERSIE}%",)))
            # de methode in de naam, zodat een tweede methode in dezelfde taal het bestand van de eerste niet overschrijft
            vraag_, model_ = m.split("/")
            achter = "" if m == EERSTE else (f"-{model_}" if vraag_ in (VERSIE, VERSIE_NIEUW) else f"-{vraag_}-{model_}")
            if a.bron:
                greep, naam = bronproef(antwoorden, a.taal, a.bron, m=m), f"te-lezen-{a.taal}{achter}-bron-{a.bron}.json"
            elif a.na_import:
                greep = [nr for i in range(len(nieuw(antwoorden, a.taal, m)) // BLOK)
                         for nr in blokproef(antwoorden, a.taal, i, m)]
                naam = f"te-lezen-{a.taal}{achter}-import.json"
            elif a.ronde == 1:
                greep, naam = leesproef(antwoorden, a.taal, m=m), f"te-lezen-{a.taal}{achter}.json"
            else:
                greep, naam = leesproef_na(antwoorden, _controle(), a.taal), f"te-lezen-{a.taal}-2.json"
            uit = [{"nummer": nr, "bron": laatste[nr]["bron"], "origineel": paginas[nr][0][:MAX_TEKENS],
                    "engels": "" if a.taal == "en" else engels.get(nr, ""), "vertaling": tekst_van[nr]}
                   for nr in greep if nr in paginas]
            pad = MAP / naam
            pad.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(pad, len(uit), Counter(u["bron"] for u in uit).most_common(12))
            return
        laatste = samengevoegd(antwoorden)
        controle = _controle()
        zonder_engels = _zonder_engels()
        print(f"{len(laatste)} beweringen beantwoord van {len(paginas)}; ${_uitgegeven():.2f} van ${GRENS:.2f}")
        for taal in DOELTALEN:
            met = len({x["nummer"] for x in antwoorden if _met(x, taal, METHODE[taal])})
            nodig = (len(zonder_engels) if taal == "en" else sum(1 for _, t in paginas.values() if t != taal))
            print(f"  {taal} ({METHODE[taal]}): {met} van {nodig} vertaald; de poort: {toelating(taal, antwoorden)[:3]}")
            if controle:
                door = sum(1 for x in laatste.values() if (x.get("vertalingen") or {}).get(taal)
                           and doorgelaten(controle, x["nummer"], taal))
                print(f"      de controle liet {door} van {met} door; de poort daarna: "
                      f"{poort_na(taal, antwoorden, controle)}")
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
