"""Waarom het niet klopt (PLAN #34.2j): hoogstens drie korte punten uit de weerlegging van de redactie zelf, voor de
factcheckpagina, direct onder het oordeel.

Stap 1 is EUvsDisinfo: elk geval in de Mendeley-snapshot (CC BY 4.0; de EEAS staat hergebruik toe met bronvermelding)
heeft een eigen weerlegging. Per pagina het nieuwste geval. Haiku leest de weerlegging (`waarom-v1`) en geeft punten
met een letterlijk citaat; een punt staat er alleen als dat citaat in de weerlegging staat, elk getal uit het punt in dat
citaat staat, en het kort is. Het zijn de redenen van de redactie, nooit een oordeel van Factiz (DR2). Naar de site pas
na een leesproef van 200 pagina's zonder één punt dat de weerlegging niet draagt.

    python -m doublecheck.waarom proef [--n 20]|indienen|ophalen [--wacht M]|lezen [--n 200]|tellen

Leest de snapshot (`data/euvsdisinfo_all_texts_rename.csv`) en de publicatiedatabase, alleen-lezen. Uitvoer in
`data/waarom/`; mijn lezing in `docs/steekproeven/34.2j-waarom.json`.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
SNAPSHOT = WORTEL / "data" / "euvsdisinfo_all_texts_rename.csv"
MAP = WORTEL / "data" / "waarom"
ANTWOORDEN = MAP / "antwoorden.jsonl"
BATCHES = MAP / "batches.jsonl"
LEZING = MAP / "lezing.jsonl"   # de tweede lezing (PLAN #34.2j)
LEZING_VERSIE = "lezing-v2"     # v1: elk ontbrekend stuk context heette een voorbehoud (PLAN #34.2j)
LEZING_GRENS_PROEF = {"lezing-v1": 1.50, "lezing-v2": 1.20}   # dollar per proef op de 200, beide modellen samen
LEZING_BATCHES = MAP / "lezing-batches.jsonl"
LEZING_GRENS_VOL = 4.00        # dollar, de volle ronde met de gekozen lezer (PO 2026-11-12: "Ja, start")
# de lezer die telt voor de site: haalde in de proef alle vier de fouten weg en minder dan 10% van de goede punten
LEZER = ("lezing-v2", "haiku", "medium")
LEZER_NAAM = "/".join(LEZER)
LABELS_V1 = WORTEL / "docs" / "steekproeven" / "34.2j-waarom.json"     # de leesproef van regels-v1 (200, dicht)
LABELS = WORTEL / "docs" / "steekproeven" / "34.2j-waarom-v2.json"     # de leesproef van de regels van nu
NIET = WORTEL / "content" / "waarom-niet.json"   # wat een mens weghaalde: een gemelde fout, of fout gelezen (B77)
VERSIE = "waarom-v3"   # v1 voegde toe wat het citaat niet zegt; v2 gaf nog een feit dat de bewering half toegeeft
GRENS = 40.00           # dollar, voor de hele ronde (PO 2026-11-12, op ongeveer $35 met Sonnet: "sonnet is goed")
MODEL = "sonnet"        # Haiku gaf soms een feit dat de bewering half toegeeft (de proef van 40, PLAN #34.2j)
MAX_PUNTEN = 3
MAX_WOORDEN = 30
MAX_TEKENS = 6000       # van een weerlegging in de vraag
PROEF_N = 200
MAX_FOUT = 100    # hoogstens 1 op de 100 punten niet gedragen, naar boven afgerond (B77, PO 2026-11-12); alleen omlaag
ZAAD = 34210
LEESZAAD = ZAAD + 2   # de leesproef van regels-v2; die van regels-v1 had ZAAD + 1, haar 200 zijn gezien
PORTIE = 20_000
LABELS_GELDIG = ("gedragen", "zwak", "niet_gedragen")

_GETAL = re.compile(r"\d+(?:[.,]\d+)*")
_WOORD = re.compile(r"[^\W\d_]+")
DEKKING = 0.9           # zoveel van de inhoudswoorden van een punt staan in de zin van zijn citaat
REGELS = "regels-v2"     # de regels van `herlees`; v2 na de leesproef van 200 (PLAN #34.2j)
# een punt dat iemand iets laat zeggen of vinden; "states" en "reports" niet, want die zijn ook een naam of een ding
_ZEGT = re.compile(r"\b(?:said|says|explained|explains|stated|according to|confirm|confirmed|confirms|told|wrote|"
                   r"announced|reported|noted|declared|stressed|warned|accused|admitted|argued|insisted|concluded|found)"
                   r"\b", re.IGNORECASE)
# een grens tussen twee zinnen in een citaat: een woord van twee tekens of een cijfer, een punt, dan een hoofdletter
# ("U. S." en "Mr. Smith" tellen zo als grens, en dat is de strengere kant)
_ZINGRENS = re.compile(r"(?:\w{2,}|\d)[.!?][\"'”’»)\]]*\s+[\"'“‘«(\[]?[A-Z0-9]")
# alleen "geen bewijs", zonder iets erbij na een puntkomma
_GEEN_BEWIJS = re.compile(r"^(?:The claim (?:offers|provides|gives|presents) no (?:evidence|proof)|The claim is not "
                          r"supported by (?:any )?evidence|No evidence)\b[^;]*$", re.IGNORECASE)
# woorden die niets zeggen, en woorden over de bewering zelf ("The claim offers no evidence"): die tellen niet mee
_LEEG = frozenset("""the and that this with from have has had were was are been being which their there they them than
then also into onto over under about after before such these those what when where while who whom whose will would could
should might must does did done doing not nor only very more most much many some any each other another both either just
even ever never upon within without between among against because since until though although however therefore thus
claim claims claimed allegation allegations offers offer provides provide provided presents presented""".split())
_TEKENS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "„": '"', "–": "-", "—": "-", " ": " "})

_SYSTEEM = """You read a disproof written by EUvsDisinfo (the East StratCom Task Force of the EU) about a disinformation \
claim. Give at most three short points that tell a reader why the claim is false, using only what the disproof says.

Rules:
- Each point is one plain English sentence of at most 25 words that states a fact directly. Never start with "The \
disproof says" or "EUvsDisinfo says".
- Each point has a quote: words copied exactly from the disproof that support everything in the point. Stay close to the \
words of the quote and add nothing that is not in it.
- Every point must be a reason the claim is false. Never give a fact that on its own seems to support the claim. If the \
disproof concedes part of the claim, leave that part out, or keep the qualification the disproof gives in the same point.
- If the disproof reports what someone said or found (a person, a medium, an organisation, satellite images), say who or \
what.
- "No evidence" in the disproof is about the claim: write "The claim offers no evidence", never that the disproof gives \
none.
- Prefer concrete facts (what actually happened, figures, who said what) over describing the narrative. At most one \
point may say that the claim is part of a recurring narrative.
- Use no fact, number, name or date that is not in the disproof. Do not repeat the claim.
- If the disproof gives no concrete reason, return an empty list."""


_LEZING_SYSTEEM = """You check short points that tell a reader why a disinformation claim is false. Each point was \
written from a disproof by EUvsDisinfo. A point may only be shown if a reader who sees nothing but the claim and the \
point is not misled. For every numbered point, answer three questions about that point alone.

concedes: Read next to the claim, could this point make a reader think the claim is true or partly true? This is true \
for a fact the claim builds on or that fits the claim's story (for example "turnout was unusually high in two regions" \
next to "the election was rigged"), and for an admission without the qualification the disproof gives.
drops_qualification: Does the disproof limit, doubt or qualify what the point states (for example "remained \
controversial", "could not be confirmed", "allegedly", "suggests", "some"), while the point leaves that out?
adds: Does the point state a conclusion, cause, attribution or fact that the disproof does not state? A conclusion that \
follows directly and necessarily from the disproof's words is not an addition. Saying that a person or organisation \
said something the disproof does not attribute to them is an addition.

Answer true whenever you are unsure: dropping a good point costs little, showing a misleading one costs much. Give one \
short reason per point, at most 20 words. Answer for every point."""

_LEZING_SYSTEEM_V2 = """You check short points that tell a reader why a disinformation claim is false. Each point was \
written from a disproof by EUvsDisinfo. A point may be shown only if a reader who sees nothing but the claim and the \
point is not misled. For every numbered point, answer three questions about that point alone. Answer true only when \
you can copy the exact words that show it; otherwise answer false and leave the words empty.

concedes: After reading only the claim and this point, would a reader believe the claim more than before? True for a \
fact that fits the claim's story without contradicting it (for example "turnout was unusually high in two regions" \
next to "the election was rigged"). False when the point mentions something from the claim but corrects it or gives \
the real context (for example "Germany paused the vaccine for three days and then resumed it" next to "Germany banned \
the vaccine"). concedes_words: the words of the point that make the reader believe the claim more, copied exactly.

drops_qualification: Does the disproof itself limit or doubt the very statement this point makes (words such as \
"allegedly", "suggests", "could not be confirmed", "remained controversial"), while the point states it without that \
limit? Other context, dates or facts from the disproof that the point leaves out do not count. qualification_words: \
the limiting words, copied exactly from the disproof.

adds: Does the point state a new fact, cause, conclusion or speaker that the disproof does not give? Paraphrase, \
shorter wording, left-out details and a conclusion that follows directly from the disproof are not additions. \
added_words: the added words, copied exactly from the point.

Give one short reason per point, at most 20 words. Answer for every point."""
_LEZING_WOORDEN = {"concedes": "concedes_words", "drops_qualification": "qualification_words", "adds": "added_words"}


class Weigering(RuntimeError):
    """Een stap die niet mag: de grens, of geen proef eerst."""


def verzoek(bewering: str, weerlegging: str, model: str = MODEL) -> dict:
    """Eén vraag over één geval: de bewering en de weerlegging van EUvsDisinfo."""
    from doublecheck.modellen import MODELLEN

    schema = {"type": "object", "additionalProperties": False, "required": ["punten"], "properties": {
        "punten": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["punt", "citaat"],
            "properties": {"punt": {"type": "string"}, "citaat": {"type": "string"}}}}}}
    vraag = f"Claim:\n{(bewering or '')[:800]}\n\nDisproof by EUvsDisinfo:\n{(weerlegging or '')[:MAX_TEKENS]}"
    return {"model": MODELLEN[model]["id"], "max_tokens": 1200, "system": _SYSTEEM,
            "messages": [{"role": "user", "content": vraag}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees(tekst: str | None, bron: str) -> list[dict]:
    """De punten die blijven uit een antwoord van het model (`herlees` zegt welke). Een antwoord dat zich niet laat
    lezen, geeft niets."""
    try:
        punten = json.loads(tekst or "")["punten"]
        if not isinstance(punten, list):
            return []
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return herlees(punten, bron)


def herlees(punten: list, bron: str) -> list[dict]:
    """De punten die blijven: een punt met tekst, van hoogstens 30 woorden, met een citaat dat letterlijk in de bron
    staat (spaties, aanhalingstekens en hoofdletters tellen niet), met elk getal uit het punt in dat citaat, en met
    minstens 90% van zijn inhoudswoorden in de zin van dat citaat (zo valt een punt weg dat er iets bij verzint). Sinds
    `regels-v2` (de leesproef, PLAN #34.2j): een punt dat iemand iets laat zeggen, rust op een citaat van één zin, en
    zijn inhoudswoorden staan in die zin zelf, niet in de zin erna; en een punt dat alleen zegt dat de bewering geen
    bewijs geeft, valt weg naast een ander punt. Hoogstens drie. Werkt ook op punten die al eerder bleven, zonder nieuwe vraag aan het model."""
    def vlak(t: str) -> str:
        return " ".join(t.translate(_TEKENS).casefold().split())

    plat = vlak(bron or "")
    # een weerlegging plakt soms twee alinea's aan elkaar ("state.In the"): een citaat over die naad telt ook
    naadloos = re.sub(r"\.(?=\S)", ". ", plat)
    uit = []
    for p in punten:
        if not isinstance(p, dict) or not isinstance(p.get("punt"), str) or not isinstance(p.get("citaat"), str):
            continue
        punt, citaat = " ".join(p["punt"].split()), vlak(p["citaat"])
        if not punt or not citaat or len(punt.split()) > MAX_WOORDEN:
            continue
        tekst_bron = plat if citaat in plat else naadloos if citaat in naadloos else None
        if tekst_bron is None:
            continue
        if any(g not in citaat for g in _GETAL.findall(punt)):
            continue
        # wie iets laat zeggen, trekt er geen tweede zin bij (16df53c9, 0d337205)
        zegt = bool(_ZEGT.search(punt))
        if zegt and _ZINGRENS.search(" ".join(p["citaat"].split())):
            continue
        # de zin rond het citaat: van de punt ervoor tot de punt erna. Laat het punt iemand iets zeggen, dan stopt die zin
        # bij het einde van het citaat, zodat de zin erna niet aan die bron wordt toegeschreven (10d12484); de leesproef
        # liet zien dat andere punten de zin erna terecht gebruiken (19 gedragen punten zouden anders wegvallen)
        begin = tekst_bron.find(citaat)
        kern = begin + len(citaat.rstrip(" \"')»"))
        links = tekst_bron.rfind(". ", 0, begin)
        rechts = tekst_bron.find(". ", max(begin, kern - 1) if zegt else begin + len(citaat))
        zin = tekst_bron[links + 2 if links >= 0 else 0: rechts if rechts >= 0 else len(tekst_bron)]
        zinwoorden = set(_WOORD.findall(zin))
        inhoud = [w for w in _WOORD.findall(punt.casefold()) if len(w) >= 4 and w not in _LEEG]
        gedekt = [w for w in inhoud if any(z.startswith(w[:5] if len(w) >= 5 else w) for z in zinwoorden)]
        if inhoud and len(gedekt) / len(inhoud) < DEKKING:
            continue
        uit.append({"punt": punt, "citaat": " ".join(p["citaat"].split())})
    # "The claim offers no evidence" zonder feit erbij zegt een lezer niets naast een punt dat wel iets zegt
    if any(not _GEEN_BEWIJS.match(q["punt"]) for q in uit):
        uit = [q for q in uit if not _GEEN_BEWIJS.match(q["punt"])]
    return uit[:MAX_PUNTEN]


def lezingverzoek(bewering: str, weerlegging: str, punten: list[dict], model: str = MODEL, effort: str = "medium",
                  versie: str = LEZING_VERSIE) -> dict:
    """De tweede lezing van één pagina (`lezing-v1`): de bewering, de weerlegging en de punten met hun nummer. Het model
    denkt eerst na; 2.000 tokens, want met 800 raakte de ruimte bij 34 van de 196 pagina's op vóór het antwoord."""
    from doublecheck.modellen import MODELLEN

    velden = {"nummer": {"type": "integer"}, "concedes": {"type": "boolean"},
              "drops_qualification": {"type": "boolean"}, "adds": {"type": "boolean"}, "reason": {"type": "string"}}
    if versie == "lezing-v2":   # bij elk ja de woorden die het laten zien
        velden.update({w: {"type": "string"} for w in _LEZING_WOORDEN.values()})
    oordeel = {"type": "object", "additionalProperties": False, "required": list(velden), "properties": velden}
    schema = {"type": "object", "additionalProperties": False, "required": ["punten"],
              "properties": {"punten": {"type": "array", "items": oordeel}}}
    lijst = "\n".join(f"[{i + 1}] {p['punt']}" for i, p in enumerate(punten))
    vraag = (f"Claim:\n{(bewering or '')[:800]}\n\nDisproof by EUvsDisinfo:\n{(weerlegging or '')[:MAX_TEKENS]}\n\n"
             f"Points:\n{lijst}")
    systeem = _LEZING_SYSTEEM_V2 if versie == "lezing-v2" else _LEZING_SYSTEEM
    return {"model": MODELLEN[model]["id"], "max_tokens": 2000, "system": systeem,
            "messages": [{"role": "user", "content": vraag}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}}}


def lees_lezing(tekst: str | None, n: int, punten: list[dict] | None = None, bron: str = "",
                versie: str = LEZING_VERSIE) -> list[bool] | None:
    """Per punt of het blijft: alleen als de lezing drie keer nee zegt. Een punt zonder antwoord blijft niet; zegt de
    lezing twee keer iets over hetzelfde punt, dan telt het strengste. Een antwoord dat zich niet laat lezen: `None`.
    Bij `lezing-v2` telt een ja alleen met zijn woorden: bij een toegeving en een toevoeging letterlijk in het punt, bij
    een voorbehoud letterlijk in de weerlegging (spaties, aanhalingstekens en hoofdletters tellen niet)."""
    def vlak(s: str) -> str:
        return " ".join((s or "").translate(_TEKENS).casefold().split()).strip(" .,;:")

    def staat(woorden: str, waar: str) -> bool:
        return bool(vlak(woorden)) and vlak(woorden) in vlak(waar)

    try:
        oordelen = json.loads(tekst or "")["punten"]
        if not isinstance(oordelen, list):
            return None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    houd: dict[int, bool] = {}
    for o in oordelen:
        velden = ("concedes", "drops_qualification", "adds")
        if (not isinstance(o, dict) or not isinstance(o.get("nummer"), int)
                or not all(isinstance(o.get(v), bool) for v in velden)):
            return None
        if versie == "lezing-v2" and not all(isinstance(o.get(w), str) for w in _LEZING_WOORDEN.values()):
            return None
        if not 1 <= o["nummer"] <= n:
            continue
        if versie == "lezing-v2":
            punt = (punten or [{}] * n)[o["nummer"] - 1].get("punt", "")
            ja = [o["concedes"] and staat(o["concedes_words"], punt),
                  o["drops_qualification"] and staat(o["qualification_words"], bron),
                  o["adds"] and staat(o["added_words"], punt)]
        else:
            ja = [o[v] for v in velden]
        houd[o["nummer"]] = houd.get(o["nummer"], True) and not any(ja)
    return [houd.get(i + 1, False) for i in range(n)]


def toon(punten: list[dict], houd: list[bool] | None) -> list[dict]:
    """Wat de site van een pagina toont: de punten na de regels waar de tweede lezing drie keer nee zei. Zonder lezing,
    of met een lezing die zich niet liet lezen, niets."""
    return [p for p, h in zip(punten, houd or []) if h]


def vergelijk_lezing(paginas: dict, houden: dict) -> dict:
    """De tweede lezing naast de labels: per label hoeveel punten blijven en hoeveel er wegvallen, met de pagina's, en
    welke pagina's niet gelezen konden worden. De labels staan in de volgorde van de punten die gelezen werden."""
    blijft, weg, weg_bij, ongelezen = {}, {}, {}, []
    for pagina, labels in paginas.items():
        houd = houden.get(pagina)
        if houd is None:
            ongelezen.append(pagina)
            houd = [False] * len(labels["punten"])
        for label, h in zip(labels["punten"], houd):
            if h:
                blijft[label] = blijft.get(label, 0) + 1
            else:
                weg[label] = weg.get(label, 0) + 1
                weg_bij.setdefault(label, []).append(pagina)
    return {"blijft": blijft, "weg": weg, "weg_bij": weg_bij, "ongelezen": ongelezen}


def rond(bron: str, citaat: str, breedte: int = 350) -> str:
    """Het citaat in zijn eigen tekst, voor de leesproef: «zo» gemarkeerd, met tot `breedte` tekens ervoor en erna, in de
    hoofdletters van de bron. Leeg als het citaat er niet in staat."""
    gewoon = " ".join((bron or "").translate(_TEKENS).split())
    gewoon = re.sub(r"\.(?=[A-Z])", ". ", gewoon)
    plat, zoek = gewoon.casefold(), " ".join(citaat.translate(_TEKENS).casefold().split())
    tekst = gewoon if len(plat) == len(gewoon) else plat
    begin = plat.find(zoek) if zoek else -1
    if begin < 0:
        return ""
    eind = begin + len(zoek)
    links, rechts = max(0, begin - breedte), min(len(tekst), eind + breedte)
    return (("…" if links else "") + tekst[links:begin] + "«" + tekst[begin:eind] + "»" + tekst[eind:rechts]
            + ("…" if rechts < len(tekst) else ""))


def vergelijk(paginas: dict, punten: dict, bronnen: dict) -> dict:
    """De regels van `herlees` op de punten van een leesproef, naast de labels: per label hoeveel punten blijven en
    hoeveel er wegvallen (met de pagina's), en welke pagina's al hun punten verliezen. Een punt wordt herkend aan zijn
    tekst, in de volgorde van de labels."""
    blijft, weg, weg_bij, leeg = {}, {}, {}, []
    for pagina, gelezen in paginas.items():
        oud = punten[pagina]
        nieuw = {q["punt"] for q in herlees(oud, bronnen[pagina])}
        for p, label in zip(oud, gelezen["punten"]):
            if " ".join(p["punt"].split()) in nieuw:
                blijft[label] = blijft.get(label, 0) + 1
            else:
                weg[label] = weg.get(label, 0) + 1
                weg_bij.setdefault(label, []).append(pagina)
        if oud and not nieuw:
            leeg.append(pagina)
    return {"blijft": blijft, "weg": weg, "weg_bij": weg_bij, "leeg": leeg}


def case_url(urls: list[str], geval: str) -> str | None:
    """De link naar de case waaruit de punten komen, zoals hij in de uitgave staat (`koppel` maakt van een link het pad
    `/report/…`)."""
    for url in urls:
        if "euvsdisinfo.eu/" in url and "/" + url.split("euvsdisinfo.eu/", 1)[1].strip("/") == geval:
            return url
    return None


def meting(pad: str | Path = LABELS) -> dict:
    """Wat de site bij het blok laat zien (B77): hoeveel punten nagelezen, hoeveel niet gedragen, met welke regels en
    lezer, op hoeveel pagina's en wanneer."""
    inhoud = json.loads(Path(pad).read_text(encoding="utf-8"))
    labels = [l for g in inhoud.get("paginas", {}).values() for l in g.get("punten", [])]
    return {"punten": len(labels), "niet_gedragen": labels.count("niet_gedragen"), "regels": inhoud.get("regels"),
            "lezer": inhoud.get("lezer"), "paginas": len(inhoud.get("paginas", {})), "datum": inhoud.get("datum", "")}


def koppel(checks: dict[str, list[tuple[str, str]]], gevallen: dict[str, dict]) -> dict[str, str]:
    """Per pagina het nieuwste geval van EUvsDisinfo met een weerlegging: het pad (`/report/…`) van haar check."""
    uit = {}
    for pagina, rijen in checks.items():
        paden = [(datum, "/" + url.split("euvsdisinfo.eu/", 1)[1].strip("/"))
                 for datum, url in rijen if "euvsdisinfo.eu/" in url]
        paden = [(d, p) for d, p in paden if gevallen.get(p, {}).get("weerlegging")]
        if paden:
            uit[pagina] = max(paden)[1]
    return uit


def mag_fouten(punten: int) -> int:
    """Hoeveel niet gedragen punten een leesproef van zoveel punten mag hebben: 1 op de 100, naar boven afgerond op een
    hele fout (B77). In gehele getallen, zodat 300 punten 3 geeft en niet 4."""
    return (punten + MAX_FOUT - 1) // MAX_FOUT


def poort(pad: str | Path = LABELS) -> tuple[bool, str]:
    """Open na een leesproef van minstens 200 pagina's met hoogstens 1 op de 100 punten die de weerlegging niet draagt
    (`mag_fouten`, B77), gelezen met de regels van nu (`REGELS`) en de tweede lezer van nu (`LEZER`)."""
    pad = Path(pad)
    if not pad.is_file():
        return False, "geen leesproef"
    inhoud = json.loads(pad.read_text(encoding="utf-8"))
    if inhoud.get("regels") != REGELS:
        return False, f"leesproef van {inhoud.get('regels', 'regels-v1')}, de regels zijn {REGELS}"
    if inhoud.get("lezer") != LEZER_NAAM:
        return False, f"leesproef met lezer {inhoud.get('lezer', 'geen')}, de lezer is {LEZER_NAAM}"
    gelezen = inhoud.get("paginas", {})
    labels = [l for g in gelezen.values() for l in g.get("punten", [])]
    if any(l not in LABELS_GELDIG for l in labels):
        return False, "een onbekend label"
    fout, zwak = labels.count("niet_gedragen"), labels.count("zwak")
    if len(gelezen) < PROEF_N:
        return False, f"{len(gelezen)} van de {PROEF_N} gelezen"
    if fout > mag_fouten(len(labels)):
        return False, (f"{fout} van {len(labels)} punten niet gedragen door de weerlegging, hoogstens "
                       f"{mag_fouten(len(labels))} mag")
    return True, (f"{len(gelezen)} pagina's, {len(labels)} punten, {zwak} zwak, {fout} niet gedragen "
                  f"(hoogstens {mag_fouten(len(labels))})")


def niet_lijst(pad: str | Path = NIET) -> list[dict]:
    """Wat een mens weghaalde (B77): per regel de pagina, het punt woord voor woord (zonder punt: de hele pagina) en de
    reden. Geen bestand: niemand haalde iets weg. Een regel zonder pagina of reden weigert."""
    pad = Path(pad)
    if not pad.is_file():
        return []
    regels = json.loads(pad.read_text(encoding="utf-8")).get("punten")
    if not isinstance(regels, list) or any(
            not isinstance(r, dict) or not str(r.get("pagina", "")).strip() or not str(r.get("reden", "")).strip()
            for r in regels):
        raise ValueError(f"{pad.name}: elke regel heeft een pagina en een reden")
    return regels


def weg(toont: dict[str, list[dict]], niet: list[dict]) -> dict[str, list[dict]]:
    """Wat de site toont zonder wat een mens weghaalde; een pagina zonder punten valt weg."""
    hele = {r["pagina"] for r in niet if not r.get("punt")}
    punten = {(r["pagina"], r["punt"]) for r in niet if r.get("punt")}
    uit = {}
    for pagina, lijst in toont.items():
        over = [q for q in lijst if (pagina, q["punt"]) not in punten]
        if pagina not in hele and over:
            uit[pagina] = over
    return uit


def leesproef_punten(tekst: str) -> dict[str, list[str]]:
    """De punten per pagina zoals een leesbestand (`lezen`) ze liet zien, in volgorde: de index van een label."""
    uit: dict[str, list[str]] = {}
    pagina = None
    for regel in tekst.splitlines():
        if regel.startswith("=== "):
            pagina = regel.split()[1]
            uit[pagina] = []
        elif pagina and (m := re.match(r"  \[(\d+)\] (.*)", regel)):
            uit[pagina].append(m.group(2))
    return uit


# --- bestanden en modellen ---------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.is_file():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def met_server(snapshot: dict[str, dict], server: list) -> dict[str, dict]:
    """De gevallen van de snapshot met die van de server van EUvsDisinfo erbij (PLAN #35.3), op hun pad (`/report/…`).
    Een geval dat de snapshot al heeft, houdt haar tekst: dan veranderen de punten van een pagina nooit stil."""
    uit = dict(snapshot)
    for g in server:
        if "euvsdisinfo.eu/" not in g.url:
            continue
        pad = "/" + g.url.split("euvsdisinfo.eu/", 1)[1].strip("/")
        uit.setdefault(pad, {"titel": g.titel, "bewering": g.claim, "weerlegging": g.weerlegging, "datum": g.datum})
    return uit


def gevallen_uit(pad: Path = SNAPSHOT) -> dict[str, dict]:  # pragma: no cover - een bestand
    """De gevallen van de snapshot op hun pad: titel, samenvatting van de bewering en de weerlegging; met wat de server
    van EUvsDisinfo sindsdien gaf (`euvsdisinfo.bewaarde`)."""
    from doublecheck import euvsdisinfo

    csv.field_size_limit(10 ** 8)
    with pad.open(encoding="utf-8", errors="replace") as f:
        snapshot = {r["Links"].strip().rstrip("/"): {"titel": r["Title"], "bewering": r["Disinformation"],
                                                    "weerlegging": r["Information"], "datum": r["Date"]}
                    for r in csv.DictReader(f) if (r.get("Links") or "").startswith("/report/")}
    return met_server(snapshot, euvsdisinfo.bewaarde())


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    pad = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))[-1]
    return sqlite3.connect(f"{pad.resolve().as_uri()}?mode=ro", uri=True)


def werkset() -> dict[str, dict]:  # pragma: no cover - bestanden
    """Per pagina het geval dat gelezen wordt."""
    gevallen = gevallen_uit()
    checks: dict[str, list[tuple[str, str]]] = {}
    for pagina, datum, url in _publicatie().execute(
            "SELECT pagina, datum, url FROM check_ WHERE url LIKE '%euvsdisinfo.eu/report/%'"):
        checks.setdefault(pagina, []).append((datum or "", url))
    return {pagina: {"geval": pad, **gevallen[pad]} for pagina, pad in koppel(checks, gevallen).items()}


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    # met wat de tweede vraag (richting-v1, gemeten en afgewezen) al kostte
    return (sum(a.get("kosten", 0.0) for a in _jsonl(ANTWOORDEN)) + sum(b.get("werkelijk") or 0.0 for b in _jsonl(BATCHES))
            + sum(t.get("kosten", 0.0) for t in _jsonl(MAP / "richting.jsonl")) + _lezing_uitgegeven())


def _lezing_uitgegeven() -> float:  # pragma: no cover - bestanden
    return sum(r.get("kosten", 0.0) for r in _jsonl(LEZING))


def _proef(n: int, model: str = MODEL) -> None:  # pragma: no cover - een model
    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    werk = werkset()
    klaar = {a["pagina"] for a in _jsonl(ANTWOORDEN) if a["versie"] == VERSIE and a.get("model", "haiku") == model}
    kies = [p for p in random.Random(ZAAD).sample(sorted(werk), len(werk)) if p not in klaar][:n]
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN[model]
    for pagina in kies:
        g = werk[pagina]
        msg = client.messages.create(**verzoek(g["bewering"] or g["titel"], g["weerlegging"], model))
        tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        try:
            gevraagd = len(json.loads(tekst or "")["punten"])
        except (json.JSONDecodeError, KeyError, TypeError):
            gevraagd = 0
        punten = lees(tekst, g["weerlegging"])
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6   # rechtstreeks: twee keer de batchprijs
        _schrijf(ANTWOORDEN, [{"pagina": pagina, "geval": g["geval"], "versie": VERSIE, "model": model, "punten": punten,
                               "gevraagd": gevraagd, "kosten": round(kosten, 7), "direct": True}])
        print(f"{pagina}: {len(punten)} van {gevraagd} punten", flush=True)
    print(f"${_uitgegeven():.3f} uitgegeven")


def _gelezen_punten() -> tuple[dict, dict, dict]:  # pragma: no cover - bestanden
    """De pagina's van de eerste leesproef met hun punten onder de regels van nu, en per pagina de labels van precies die
    punten, in hun volgorde."""
    werk = werkset()
    paginas = json.loads(LABELS_V1.read_text(encoding="utf-8"))["paginas"]
    antwoorden = {a["pagina"]: a for a in _jsonl(ANTWOORDEN) if a["versie"] == VERSIE and a.get("model") == MODEL}
    punten, labels = {}, {}
    for pagina, gelezen in paginas.items():
        oud = antwoorden[pagina]["punten"]
        nu = herlees(oud, werk[pagina]["weerlegging"])
        tekst = {q["punt"] for q in nu}
        punten[pagina] = nu
        labels[pagina] = {"punten": [l for p, l in zip(oud, gelezen["punten"]) if " ".join(p["punt"].split()) in tekst]}
    return werk, punten, labels


def _lezing_proef(model: str, effort: str = "medium", versie: str = LEZING_VERSIE) -> None:  # pragma: no cover - een model
    """De tweede lezing op de 200 pagina's van de eerste leesproef, rechtstreeks; hervatbaar (een pagina zonder leesbaar
    antwoord gaat opnieuw), en stopt bij de grens."""
    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    werk, punten, _ = _gelezen_punten()
    grens = LEZING_GRENS_PROEF[versie]
    klaar = {r["pagina"] for r in _jsonl(LEZING) if r["versie"] == versie and r["model"] == model
             and r.get("effort", "medium") == effort and r["houd"] is not None}
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN[model]
    for pagina, lijst in punten.items():
        if pagina in klaar or not lijst:
            continue
        if sum(r.get("kosten", 0.0) for r in _jsonl(LEZING) if r["versie"] == versie) >= grens:
            raise Weigering(f"de grens van ${grens:.2f} voor de proef is bereikt")
        g = werk[pagina]
        msg = client.messages.create(**lezingverzoek(g["bewering"] or g["titel"], g["weerlegging"], lijst, model, effort,
                                                     versie))
        tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        houd = lees_lezing(tekst, len(lijst), lijst, g["weerlegging"], versie)
        try:
            antwoord = json.loads(tekst or "")["punten"]
            redenen = {o["nummer"]: o["reason"] for o in antwoord}
        except (json.JSONDecodeError, KeyError, TypeError):
            antwoord, redenen = None, {}
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        _schrijf(LEZING, [{"pagina": pagina, "versie": versie, "model": model, "effort": effort, "regels": REGELS,
                           "stop": msg.stop_reason,
                           "punten": [q["punt"] for q in lijst], "houd": houd,
                           "redenen": [redenen.get(i + 1, "") for i in range(len(lijst))],
                           # het ruwe antwoord, zodat te zien is welk ja de woordcontrole liet vallen (sinds lezing-v2)
                           "antwoord": antwoord,
                           "kosten": round(kosten, 7), "direct": True}])
    print(f"{model} ({effort}): ${_lezing_uitgegeven():.3f} voor de lezing samen")


def _te_lezen() -> tuple[dict, dict]:  # pragma: no cover - bestanden
    """Per pagina de punten na de regels van nu, voor elke pagina die er nog heeft."""
    werk = werkset()
    punten = {}
    for a in _jsonl(ANTWOORDEN):
        # een pagina die er niet meer is (een nieuwe groepering, of een uitgave zonder haar): niets, geen fout
        if a["versie"] == VERSIE and a.get("model") == MODEL and a["pagina"] in werk:
            nu = herlees(a["punten"], werk[a["pagina"]]["weerlegging"])
            if nu:
                punten[a["pagina"]] = nu
    return werk, punten


def _lezer_rijen() -> dict:  # pragma: no cover - bestanden
    """De laatste lezing per pagina van de lezer die telt (`LEZER`)."""
    versie, model, effort = LEZER
    return {r["pagina"]: r for r in _jsonl(LEZING)
            if r["versie"] == versie and r["model"] == model and r.get("effort", "medium") == effort}


def getoond() -> tuple[dict, dict]:  # pragma: no cover - bestanden
    """Per pagina wat de site toont (`toon`), met de regels en de lezer van nu; een lezing van andere punten telt niet."""
    werk, punten = _te_lezen()
    rijen = _lezer_rijen()
    uit = {}
    for pagina, lijst in punten.items():
        r = rijen.get(pagina)
        houd = r["houd"] if r and r["punten"] == [q["punt"] for q in lijst] else None
        uit[pagina] = toon(lijst, houd)
    return werk, uit


def geldige_punten() -> tuple[dict | None, str]:  # pragma: no cover - bestanden
    """Voor de uitgave (`publiceren`): per pagina de punten die de site toont en de link naar hun case, met de meting;
    niets zolang de poort dicht is (PLAN #34.2j, B77)."""
    open_, reden = poort()
    if not open_:
        return None, f"dicht ({reden})"
    werk, toont = getoond()
    toont = weg(toont, niet_lijst())
    urls: dict[str, list[str]] = {}
    for pagina, url in _publicatie().execute("SELECT pagina, url FROM check_ WHERE url LIKE '%euvsdisinfo.eu/report/%'"):
        urls.setdefault(pagina, []).append(url)
    punten = {}
    for pagina, lijst in toont.items():
        url = case_url(urls.get(pagina, []), werk[pagina]["geval"]) if lijst else None
        if url:
            punten[pagina] = {"punten": [q["punt"] for q in lijst], "url": url}
    return {"punten": punten, "meting": meting()}, f"open ({reden}); {len(punten)} pagina's"


def _lezing_indienen() -> None:  # pragma: no cover - de Batch API
    """De volle ronde met de lezer die telt, via de Batch API op openbare gegevens; binnen `LEZING_GRENS_VOL`."""
    import anthropic

    from doublecheck.varianten import laad_sleutel

    versie, model, effort = LEZER
    rijen = _lezer_rijen()
    proef = [r for r in rijen.values() if r.get("direct") and r["houd"] is not None]
    if len(proef) < 100:
        raise Weigering("eerst de proef met deze lezer")
    werk, punten = _te_lezen()
    klaar = {p for p, r in rijen.items() if r["houd"] is not None and r["punten"] == [q["punt"] for q in punten.get(p, [])]}
    onderweg = {p for b in _jsonl(LEZING_BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    te_doen = sorted(set(punten) - klaar - onderweg)
    per = sum(r["kosten"] for r in proef) / len(proef) / 2      # de batch kost de helft
    al = sum(b.get("werkelijk") or b["schatting"] for b in _jsonl(LEZING_BATCHES))
    if not te_doen:
        print("niets te lezen")
        return
    from doublecheck import routinegrens as rg

    if rg.uitgave():            # onder de routine telt haar ruimte (PLAN #35.3)
        if not rg.past(per * len(te_doen)):
            raise Weigering(f"geschat ${per * len(te_doen):.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
    elif al + per * len(te_doen) > LEZING_GRENS_VOL:
        raise Weigering(f"geweigerd: ${al:.2f} plus ${per * len(te_doen):.2f} is meer dan ${LEZING_GRENS_VOL:.2f}")
    laad_sleutel()
    client = anthropic.Anthropic()
    for begin in range(0, len(te_doen), PORTIE):
        deel = te_doen[begin:begin + PORTIE]
        batch = client.messages.batches.create(requests=[
            {"custom_id": p, "params": lezingverzoek(werk[p]["bewering"] or werk[p]["titel"], werk[p]["weerlegging"],
                                                     punten[p], model, effort, versie)}
            for p in deel])
        _schrijf(LEZING_BATCHES, [rg.merk({"id": batch.id, "paginas": deel, "lezer": LEZER_NAAM,
                                           "schatting": round(per * len(deel), 2)})])
        print(f"batch {batch.id}: {len(deel)} pagina's, schatting ${per * len(deel):.2f}", flush=True)


def _lezing_ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    versie, model, effort = LEZER
    werk, punten = _te_lezen()
    batches = _jsonl(LEZING_BATCHES)
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
            werkelijk, rijen = 0.0, []
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id not in punten:
                    continue
                lijst, houd, antwoord, kosten, stop = punten[r.custom_id], None, None, 0.0, r.result.type
                if r.result.type == "succeeded":
                    msg = r.result.message
                    kosten = kosten_batch(bc.gebruik_uit(msg), model)
                    werkelijk += kosten
                    stop = msg.stop_reason
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                    houd = lees_lezing(tekst, len(lijst), lijst, werk[r.custom_id]["weerlegging"], versie)
                    try:
                        antwoord = json.loads(tekst or "")["punten"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        antwoord = None
                rijen.append({"pagina": r.custom_id, "versie": versie, "model": model, "effort": effort,
                              "regels": REGELS, "stop": stop, "punten": [q["punt"] for q in lijst], "houd": houd,
                              "redenen": [(o.get("reason", "") if isinstance(o, dict) else "") for o in (antwoord or [])],
                              "antwoord": antwoord, "kosten": round(kosten, 7), "direct": False, "batch": b["id"]})
            _schrijf(LEZING, rijen)
            b["werkelijk"] = round(werkelijk, 4)
            print(f"batch {b['id']}: {len(rijen)} pagina's, ${werkelijk:.2f}, "
                  f"{sum(1 for x in rijen if x['houd'] is None)} zonder leesbaar antwoord", flush=True)
        LEZING_BATCHES.write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; ${_lezing_uitgegeven():.2f} voor de lezing samen")


def _lezing_tellen() -> None:  # pragma: no cover - bestanden
    """De proef naast de labels, per model, met de reden bij elk weggevallen punt dat gedragen of niet gedragen was."""
    _, punten, labels = _gelezen_punten()
    rijen = _jsonl(LEZING)
    for versie, model, effort in sorted({(r["versie"], r["model"], r.get("effort", "medium")) for r in rijen}):
        van = {r["pagina"]: r for r in rijen
               if r["versie"] == versie and r["model"] == model and r.get("effort", "medium") == effort}
        houden = {p: (van[p]["houd"] if p in van and van[p]["punten"] == [q["punt"] for q in punten[p]] else None)
                  for p in labels if punten[p]}
        uit = vergelijk_lezing({p: labels[p] for p in houden}, houden)
        kosten = sum(r["kosten"] for r in van.values())
        g = uit["weg"].get("gedragen", 0)
        print(f"{versie}, {model}, {effort} (${kosten:.3f}): gedragen weg {g} van {g + uit['blijft'].get('gedragen', 0)}; "
              f"blijft {uit['blijft']}, weg {uit['weg']}, "
              f"ongelezen {len(uit['ongelezen'])}")
        for label in ("niet_gedragen", "gedragen"):
            for pagina in dict.fromkeys(uit["weg_bij"].get(label, [])):
                r = van.get(pagina)
                for p, l, h, reden in zip(r["punten"], labels[pagina]["punten"], r["houd"] or [], r["redenen"]):
                    if l == label and not h:
                        print(f"  {label} weg, {pagina}: {p[:90]}\n      reden: {reden}")


def _indienen() -> None:  # pragma: no cover - de Batch API
    import anthropic

    from doublecheck.varianten import laad_sleutel

    proef = [a for a in _jsonl(ANTWOORDEN) if a.get("direct") and a["versie"] == VERSIE and a.get("model") == MODEL]
    if len(proef) < 20:
        raise Weigering("eerst de proef van 20, gelezen")
    werk = werkset()
    klaar = {a["pagina"] for a in _jsonl(ANTWOORDEN) if a["versie"] == VERSIE and a.get("model") == MODEL}
    onderweg = {p for b in _jsonl(BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    te_doen = sorted(set(werk) - klaar - onderweg)
    per = sum(a["kosten"] for a in proef) / len(proef) / 2      # de batch kost de helft
    if not te_doen:
        print("niets te lezen")
        return
    from doublecheck import routinegrens as rg

    if rg.uitgave():            # onder de routine telt haar ruimte, niet de grens van de eerste ronde (PLAN #35.3)
        if not rg.past(per * len(te_doen)):
            raise Weigering(f"geschat ${per * len(te_doen):.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
    elif _uitgegeven() + per * len(te_doen) > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} plus ${per * len(te_doen):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client = anthropic.Anthropic()
    for begin in range(0, len(te_doen), PORTIE):
        deel = te_doen[begin:begin + PORTIE]
        batch = client.messages.batches.create(requests=[
            {"custom_id": p, "params": verzoek(werk[p]["bewering"] or werk[p]["titel"], werk[p]["weerlegging"], MODEL)}
            for p in deel])
        _schrijf(BATCHES, [rg.merk({"id": batch.id, "paginas": deel, "versie": VERSIE, "model": MODEL,
                                    "schatting": round(per * len(deel), 2)})])
        print(f"batch {batch.id}: {len(deel)} pagina's, schatting ${per * len(deel):.2f}", flush=True)


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    werk = werkset()
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
            werkelijk, rijen = 0.0, []
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id not in werk:
                    continue
                punten, gevraagd = [], 0
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += kosten_batch(bc.gebruik_uit(msg), b.get("model", "haiku"))
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                    try:
                        gevraagd = len(json.loads(tekst or "")["punten"])
                    except (json.JSONDecodeError, KeyError, TypeError):
                        gevraagd = 0
                    punten = lees(tekst, werk[r.custom_id]["weerlegging"])
                rijen.append({"pagina": r.custom_id, "geval": werk[r.custom_id]["geval"], "versie": b["versie"],
                              "model": b.get("model", "haiku"), "punten": punten, "gevraagd": gevraagd})
            _schrijf(ANTWOORDEN, rijen)
            b["werkelijk"] = round(werkelijk, 4)
            print(f"batch {b['id']}: {len(rijen)} pagina's, ${werkelijk:.2f}", flush=True)
        BATCHES.write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; ${_uitgegeven():.2f} van ${GRENS:.2f}")


def _lezen(n: int, alleen_direct: bool) -> None:  # pragma: no cover - bestanden
    """De pagina's om te lezen, op een vast zaad: alleen pagina's die iets tonen na de regels en de lezer van nu
    (`getoond`), want alleen die tonen iets op de site, en nooit een pagina uit een eerdere leesproef. Per punt het
    citaat in zijn eigen tekst (`rond`)."""
    werk, toont = getoond()
    gezien = set(json.loads(LABELS_V1.read_text(encoding="utf-8"))["paginas"]) if LABELS_V1.is_file() else set()
    antwoorden = []
    for a in _jsonl(ANTWOORDEN):
        if a["versie"] != VERSIE or a.get("model") != MODEL or a["pagina"] in gezien:
            continue
        if toont.get(a["pagina"]) and (a.get("direct") or not alleen_direct):
            antwoorden.append({**a, "punten": toont[a["pagina"]]})
    antwoorden.sort(key=lambda a: a["pagina"])
    for a in random.Random(LEESZAAD).sample(antwoorden, min(n, len(antwoorden))):
        g = werk[a["pagina"]]
        print(f"=== {a['pagina']} {a['geval']}\nBEWERING: {(g['bewering'] or g['titel'])[:400]}")
        for i, p in enumerate(a["punten"]):
            print(f"  [{i}] {p['punt']}\n      in de tekst: {rond(g['weerlegging'], p['citaat'])}")
        print()


def _bekend() -> None:  # pragma: no cover - bestanden
    """Zet elk punt dat ik bij een leesproef niet gedragen las in de lijst van wat weg is (`NIET`), woord voor woord uit
    het leesbestand van die proef; wat er al stond, blijft. Daarna: hoeveel ervan de site nu zou tonen."""
    niet = niet_lijst()
    al = {(r["pagina"], r.get("punt")) for r in niet}
    for labels, tekst in ((LABELS_V1, MAP / "leesproef.txt"), (LABELS, MAP / "leesproef-v2.txt")):
        inhoud = json.loads(labels.read_text(encoding="utf-8"))
        gelezen = leesproef_punten(tekst.read_text(encoding="utf-8"))
        for pagina, g in inhoud["paginas"].items():
            for i, label in enumerate(g["punten"]):
                if label != "niet_gedragen" or (pagina, gelezen[pagina][i]) in al:
                    continue
                niet.append({"pagina": pagina, "punt": gelezen[pagina][i],
                             "reden": f"niet gedragen bij de leesproef ({labels.name}): {g.get('noot', '')}",
                             "door": inhoud.get("gelezen_door", "Claude"), "datum": inhoud.get("datum", "")})
                al.add((pagina, gelezen[pagina][i]))
    NIET.write_text(json.dumps({"_meta": {"toelichting": (
        "Punten van Waarom het niet klopt die in geen uitgave mogen staan, wat de regels en de lezing ook zeggen (B77, "
        "PLAN #34.2j): een fout die een bezoeker meldde, of een punt dat bij een leesproef niet gedragen bleek. Per regel "
        "de pagina, het punt woord voor woord (zonder punt: de hele pagina), de reden, door wie en wanneer. "
        "`publiceren bouwen` laat ze weg; een gemelde fout komt hier binnen een werkdag, met een nieuwe uitgave.")},
        "punten": niet}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _, toont = getoond()
    raakt = sum(1 for r in niet if r.get("punt") and any(q["punt"] == r["punt"] for q in toont.get(r["pagina"], [])))
    print(f"{len(niet)} regels in {NIET.name}; {raakt} ervan zou de site zonder de lijst nu tonen")


def _tellen() -> None:  # pragma: no cover - bestanden
    """De ronde, met de regels van nu (`REGELS`) op de bewaarde punten."""
    werk = werkset()
    antwoorden = [a for a in _jsonl(ANTWOORDEN) if a["versie"] == VERSIE and a.get("model") == MODEL]
    gevraagd = sum(a["gevraagd"] for a in antwoorden)
    nu = {a["pagina"]: herlees(a["punten"], werk[a["pagina"]]["weerlegging"]) for a in antwoorden}
    print(f"{len(antwoorden)} pagina's gelezen, {sum(1 for p in nu.values() if p)} met punten; "
          f"{sum(len(p) for p in nu.values())} van {gevraagd} punten door de regels ({REGELS}); "
          f"${_uitgegeven():.3f} uitgegeven")
    _, toont = getoond()
    print(f"na de tweede lezing ({LEZER_NAAM}): {sum(1 for p in toont.values() if p)} pagina's tonen "
          f"{sum(len(p) for p in toont.values())} punten")
    print("poort:", *poort())


def _regels() -> None:  # pragma: no cover - bestanden
    """Wat de regels van nu doen met de leesproef: per label wat blijft en wat wegvalt."""
    werk = werkset()
    paginas = json.loads(LABELS_V1.read_text(encoding="utf-8"))["paginas"]
    antwoorden = {a["pagina"]: a for a in _jsonl(ANTWOORDEN) if a["versie"] == VERSIE and a.get("model") == MODEL}
    uit = vergelijk(paginas, {p: antwoorden[p]["punten"] for p in paginas},
                    {p: werk[p]["weerlegging"] for p in paginas})
    print(f"{REGELS} op de leesproef van {len(paginas)} pagina's")
    print("  blijft:", uit["blijft"])
    print("  weg:   ", uit["weg"])
    for label, bij in sorted(uit["weg_bij"].items()):
        print(f"  weg bij {label}: {' '.join(bij)}")
    print(f"  pagina's zonder punten: {len(uit['leeg'])} ({' '.join(uit['leeg'])})")


def main() -> None:  # pragma: no cover - de opdrachtregel
    parser = argparse.ArgumentParser(description="Waarom het niet klopt (PLAN #34.2j)")
    parser.add_argument("stap", choices=("proef", "indienen", "ophalen", "lezen", "tellen", "regels", "lezing-proef", "lezing-tellen", "lezing-indienen", "lezing-ophalen", "bekend"))
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--wacht", type=int, default=0)
    parser.add_argument("--proef", action="store_true", help="bij lezen: alleen de proef")
    parser.add_argument("--model", default=MODEL, choices=("haiku", "sonnet"))
    parser.add_argument("--effort", default="medium", choices=("low", "medium"), help="bij lezing-proef")
    parser.add_argument("--versie", default=LEZING_VERSIE, choices=("lezing-v1", "lezing-v2"), help="bij lezing-proef")
    args = parser.parse_args()
    if args.stap == "proef":
        _proef(args.n, args.model)
    elif args.stap == "indienen":
        _indienen()
    elif args.stap == "ophalen":
        _ophalen(args.wacht)
    elif args.stap == "lezen":
        _lezen(args.n, args.proef)
    elif args.stap == "regels":
        _regels()
    elif args.stap == "lezing-proef":
        _lezing_proef(args.model, args.effort, args.versie)
    elif args.stap == "lezing-tellen":
        _lezing_tellen()
    elif args.stap == "lezing-indienen":
        _lezing_indienen()
    elif args.stap == "lezing-ophalen":
        _lezing_ophalen(args.wacht)
    elif args.stap == "bekend":
        _bekend()
    else:
        _tellen()


if __name__ == "__main__":
    main()
