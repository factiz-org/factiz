"""Namen voor het platform (PLAN #33.7, SPECS E9.S11): publieke personen, organisaties en plaatsen met een nummer van
Wikidata, zodat dezelfde naam in elke taal dezelfde is. Een naam is een ingang, geen oordeel: de site zegt alleen dat
een naam in een bewering voorkomt. Een privépersoon komt er nooit op.

De weg: (1) Haiku leest elke bewering, tien per vraag, en noemt hoogstens vijf namen met hun soort (`namen-v1`);
(2) elke naam die vaak genoeg voorkomt, wordt opgezocht bij Wikidata, en Haiku kiest uit de kandidaten of *geen*
(`naamkeuze-v1`); (3) van het gekozen nummer komen de naam in vijf talen, het aantal talen van Wikipedia en of het een
mens is; (4) vier regels beslissen welke namen op de site mogen (`stel_samen`). Daarna leest de PO (`poort`).

    python -m doublecheck.namen proef [--n 300]                 # direct, voor de kosten en de aantallen
    python -m doublecheck.namen vol indienen|ophalen [--wacht M]   # alle pagina's via de Batch API
    python -m doublecheck.namen tellen
    python -m doublecheck.namen zoeken [--max N]                # Wikidata, één verzoek tegelijk, hervatbaar
    python -m doublecheck.namen kiezen indienen|ophalen [--wacht M]
    python -m doublecheck.namen kenmerken                       # Wikidata: namen, Wikipedia's, mens of niet
    python -m doublecheck.namen samenstellen
    python -m doublecheck.namen staart [--n 100]                # de personen met de minste pagina's, om te lezen
    python -m doublecheck.namen nakijken set|pagina|tellen [--keuzes <json>]

De beweringen zijn openbaar (de publicatiedatabase); de Batch API staat niet in het aanvraagpad. Uitvoer in
`data/namen/`. Leest de publicatiedatabase alleen."""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

from doublecheck.themas import POORT_AANDEEL, POORT_GOED, POORT_N, POORT_ZEKERHEID, draagt

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "namen"
NIET_PAD = WORTEL / "content" / "namen-niet.json"       # wat een mens weghaalde (SPECS E9.S11 AC6)
PO_LABELS = WORTEL / "docs" / "steekproeven" / "33.7-namen-po.json"
PO_RONDE = "33-7"
GRENS = 6.00              # dollar voor het lezen en het kiezen samen (PLAN #33.7)
SCHATTING = 0.000032      # per bewering via de batch, tien per vraag (gemeten in de proef); direct het dubbele
SCHATTING_KEUZE = 0.00004  # per naam via de batch
VERSIE = "namen-v1"
KEUZEVERSIE = "naamkeuze-v1"
SOORTEN = ("persoon", "organisatie", "plaats")
SITETALEN = ("en", "nl", "de", "es", "fr")
PER_VRAAG = 10
MAX_NAMEN = 5             # per bewering
MAX_LENGTE = 80           # van een naam
MAX_TEKENS = 500          # van een bewering in de vraag
ZOEK_VANAF = 2            # een schrijfwijze wordt opgezocht als zij op minstens zoveel pagina's staat
MIN_WIKIS = 3             # talen van Wikipedia met een artikel
MIN_PAGINAS = 5
MIN_REDACTIES = 2         # voor een persoon
ZAAD = 3307
DRADEN = 8
AGENT = "FactizResearch/1.0 (https://factiz.org; alleen tekst, PLAN #33.7)"
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
PAUZE = 1.0               # seconden tussen twee vragen aan Wikipedia of Wikidata: sneller remt de dienst ons af
SPARQL = "https://query.wikidata.org/sparql"

# Wat geen persoon, organisatie of plaats is, wat het model ook zei: een doorverwijspagina, een voor- of achternaam,
# een lijst, een categorie of een sjabloon van Wikimedia.
WEG = frozenset({"Q4167410", "Q101352", "Q202444", "Q11879590", "Q12308941", "Q3409032", "Q13406463", "Q4167836",
                 "Q11266439", "Q17633526", "Q22808320"})
# Een ding, een werk, een wet, een verdrag of een gebeurtenis is geen organisatie en geen plaats, al noemde het model
# het zo (gelezen in de soorten van de namen die de regels haalden, 2026-11-11): een gifstof, een medicijn of vaccin,
# een aanslag of oorlogsmisdaad, een toernooi of prijs, een wet of verdrag, een ambtstermijn, een protest of
# staatsgreep, een complottheorie, een vliegtuigtype, een godsdienst of geloofsgroep, een bedevaart, een schandaal,
# een uittreding, een ruimtemissie.
WEG |= frozenset({"Q56256173", "Q12140", "Q134808", "Q135010", "Q6539177", "Q1955280", "Q34542827", "Q47443726",
                  "Q135976384", "Q107655869", "Q9639292", "Q476068", "Q820655", "Q1269627", "Q3176665", "Q33283984",
                  "Q131569", "Q2006324", "Q321839", "Q625298", "Q16567729", "Q1414472", "Q1143371", "Q15284636",
                  "Q45382", "Q273120", "Q159535", "Q105226648", "Q15056993", "Q6957341", "Q11197007", "Q113071362",
                  "Q192909", "Q2223653", "Q3123616", "Q2133344",
                  "Q106955175", "Q117467246", "Q34439356"})     # een vlucht, een tekenfilmserie, een orkaan
MENS = "Q5"
# Sites van Wikimedia die geen Wikipedia in een taal zijn, al eindigt hun sleutel op "wiki".
NIET_WIKI = frozenset({"commonswiki", "specieswiki", "metawiki", "wikidatawiki", "mediawikiwiki", "sourceswiki",
                       "foundationwiki", "outreachwiki", "incubatorwiki", "wikimaniawiki", "wikifunctionswiki"})
_WIKI = re.compile(r"[a-z_]+wiki")
_NUMMER = re.compile(r"Q[1-9][0-9]*")
# Tekens die de leesrichting omgooien of verbergen: die horen niet in een naam. Verbindingstekens (ZWJ, ZWNJ) blijven:
# in het Perzisch en de Indiase schriften dragen zij betekenis.
_RICHTING = frozenset("‎‏؜‪‫‬‭‮⁦⁧⁨⁩")
PO_TALEN = ("en", "nl")
RTL = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})
PO_MIS = ("niet-genoemd", "verkeerde", "prive")


class Weigering(Exception):
    pass


def binnen_grens(geschat: float, uitgegeven: float, grens: float = GRENS) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"geschat ${geschat:.2f} bij ${uitgegeven:.2f} uitgegeven gaat over de grens van ${grens:.2f}")


def groepen(nummers: list, per: int = PER_VRAAG) -> list[list]:
    return [nummers[i:i + per] for i in range(0, len(nummers), per)]


# --- een naam --------------------------------------------------------------------------------------------------------

def schoon(naam: str) -> str:
    """Een naam als platte tekst: zonder stuurtekens en zonder tekens die de leesrichting omgooien, met enkele
    spaties. Letters en combinerende tekens blijven, in elk schrift."""
    kaal = "".join(" " if unicodedata.category(t) == "Cc" else t for t in naam if t not in _RICHTING)
    return " ".join(kaal.split())


def sleutel(naam: str) -> str:
    """Waaronder schrijfwijzen van één naam samen tellen: zonder hoofdletters en dubbele spaties. Een accent of een
    klinkerteken is geen spelfout en blijft."""
    return schoon(naam).casefold()


# --- de vraag: welke namen staan er in een bewering -----------------------------------------------------------------

_SYSTEEM = (
    "You index a public archive of fact-checked claims by the names in them. For every numbered claim, list the "
    "public persons, organisations and places that the claim names. Do not judge whether a claim is true, and do not "
    "say who made it.\n\n"
    "Rules:\n"
    "- Only names that are written in the claim, in full or in a usual short form (\"Modi\", \"Lula\", \"WHO\"); "
    "you then give the full name. A role without a name (\"the president\", \"the governor of Bahia\", \"a doctor\", \"the police\") "
    "is not a name: do not work out who holds the role.\n"
    "- Not a name here: a disease, an event, a law, a product, a religion, a people, a language or a work of art.\n"
    "- Leave out the platform or medium on which the claim was posted or shared (\"a post on X\", \"a Facebook "
    "video\"), unless the claim is about that platform or medium itself.\n"
    '- "naam": the usual English form of the full name, as the English Wikipedia titles it ("Volodymyr Zelensky", '
    '"World Health Organization", "São Paulo"), whatever the language of the claim, without anything in brackets.\n'
    '- "soort": "persoon" for a person, "organisatie" for a company, party, government body, international body, '
    'medium, club, armed group or other organisation, "plaats" for a country, region, city or named building.\n'
    "- Persons: only public figures, such as politicians, officials, heads of state, royals, celebrities, athletes, "
    "business leaders, well-known writers, scientists and journalists, and historical figures. Leave every private "
    "person out, even if the claim names them: a victim, a suspect, a patient, a child, a relative of someone, a "
    "local resident, an employee, or someone known only from one post or video. When in doubt, leave the person out.\n"
    "- At most five names per claim, the ones the claim is most about first. A claim without such a name gets an "
    "empty list.")


def naamverzoek(claims: list[tuple[str, str]]) -> dict:
    """Eén vraag over een rijtje beweringen (tekst, taal): welke publieke personen, organisaties en plaatsen noemt
    elk. Geen oordeel over de bewering, en geen privépersonen."""
    from doublecheck.modellen import MODELLEN

    naam = {"type": "object", "additionalProperties": False, "required": ["naam", "soort"],
            "properties": {"naam": {"type": "string"}, "soort": {"type": "string", "enum": list(SOORTEN)}}}
    item = {"type": "object", "additionalProperties": False, "required": ["nr", "namen"],
            "properties": {"nr": {"type": "integer"}, "namen": {"type": "array", "items": naam}}}
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"],
              "properties": {"antwoorden": {"type": "array", "items": item}}}
    tekst = "\n".join(f"{i}. ({taal or 'und'}) {' '.join((bewering or '').split())[:MAX_TEKENS]}"
                      for i, (bewering, taal) in enumerate(claims, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 6000, "system": _SYSTEEM,
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def _namen_van(ruw) -> list[dict] | None:
    if not isinstance(ruw, list):
        return None
    uit, gezien = [], set()
    for n in ruw:
        if not isinstance(n, dict) or n.get("soort") not in SOORTEN or not isinstance(n.get("naam"), str):
            continue
        naam = schoon(n["naam"])
        if not 2 <= len(naam) <= MAX_LENGTE or not any(t.isalpha() for t in naam) or sleutel(naam) in gezien:
            continue
        gezien.add(sleutel(naam))
        uit.append({"naam": naam, "soort": n["soort"]})
    return uit[:MAX_NAMEN]


def lees_namen(tekst: str | None, n: int) -> list[list[dict] | None]:
    """De namen per bewering, op nummer. Een nummer dat ontbreekt of twee keer voorkomt, telt niet. Een lege lijst
    is een antwoord: de bewering noemt niemand."""
    uit: list[list[dict] | None] = [None] * n
    try:
        antwoorden = json.loads(tekst)["antwoorden"]  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, KeyError):
        return uit
    if not isinstance(antwoorden, list):
        return uit
    geteld = Counter(a.get("nr") for a in antwoorden if isinstance(a, dict) and isinstance(a.get("nr"), int))
    for a in antwoorden:
        if isinstance(a, dict) and isinstance(a.get("nr"), int) and 1 <= a["nr"] <= n and geteld[a["nr"]] == 1:
            uit[a["nr"] - 1] = _namen_van(a.get("namen"))
    return uit


def laatste(rijen: list[dict]) -> dict[str, list[dict]]:
    """Per pagina de laatste lezing die te lezen was: een pagina die opnieuw gevraagd is, telt één keer."""
    return {r["nummer"]: r["namen"] for r in rijen if r.get("namen") is not None}


def tel(rijen: list[dict]) -> dict[str, dict]:
    """Per schrijfwijze (zonder hoofdletters): de meest gebruikte vorm, de soort die de meeste pagina's noemen, en de
    pagina's waarop zij staat."""
    vormen: dict[str, Counter] = {}
    soorten: dict[str, Counter] = {}
    paginas: dict[str, set[str]] = {}
    for nummer, namen in laatste(rijen).items():
        for n in namen:
            s = sleutel(n["naam"])
            vormen.setdefault(s, Counter())[n["naam"]] += 1
            soorten.setdefault(s, Counter())[n["soort"]] += 1
            paginas.setdefault(s, set()).add(nummer)
    return {s: {"naam": vormen[s].most_common(1)[0][0], "soort": soorten[s].most_common(1)[0][0],
                "paginas": sorted(paginas[s])} for s in vormen}


# --- Wikidata --------------------------------------------------------------------------------------------------------

def kandidaten_uit(antwoord: dict | None) -> list[dict]:
    """De kandidaten uit een zoekantwoord van Wikidata: hoogstens vijf items met een nummer."""
    uit = []
    for s in (antwoord or {}).get("search") or []:
        if isinstance(s, dict) and isinstance(s.get("id"), str) and _NUMMER.fullmatch(s["id"]):
            uit.append({"nummer": s["id"], "naam": schoon(str(s.get("label") or "")),
                        "omschrijving": schoon(str(s.get("description") or ""))[:200]})
    return uit[:5]


def titels_uit(antwoord: dict | None, gevraagd: list[str]) -> dict[str, str]:
    """Welke gevraagde namen een artikel in de Engelse Wikipedia zijn, met het nummer van dat artikel bij Wikidata.
    Een naam volgt zijn doorverwijzing ("Lula da Silva" naar het volle artikel); een doorverwijspagina ("Georgia"),
    een artikel dat niet bestaat en een artikel zonder nummer zijn geen antwoord."""
    vraag = (antwoord or {}).get("query")
    if not isinstance(vraag, dict):
        return {}
    gewoon = {n["from"]: n["to"] for n in vraag.get("normalized") or []}
    door = {r["from"]: r["to"] for r in vraag.get("redirects") or []}
    nummer = {}
    for p in vraag.get("pages") or []:
        eigenschappen = p.get("pageprops") or {}
        q = eigenschappen.get("wikibase_item")
        if isinstance(q, str) and _NUMMER.fullmatch(q) and "disambiguation" not in eigenschappen and not p.get("missing"):
            nummer[p["title"]] = q
    uit = {}
    for naam in gevraagd:
        titel = gewoon.get(naam, naam)
        titel = door.get(titel, titel)
        if titel in nummer:
            uit[naam] = nummer[titel]
    return uit


def kandidaat_van(entiteit: dict | None) -> dict | None:
    """Een item van Wikidata als kandidaat: zijn nummer, zijn Engelse naam en zijn Engelse omschrijving."""
    if not isinstance(entiteit, dict) or "missing" in entiteit or not _NUMMER.fullmatch(str(entiteit.get("id"))):
        return None
    labels = entiteit.get("labels") or {}
    naam = schoon(str((labels.get("en") or labels.get("mul") or {}).get("value") or ""))
    if not naam:
        return None
    omschrijving = schoon(str(((entiteit.get("descriptions") or {}).get("en") or {}).get("value") or ""))[:200]
    return {"nummer": entiteit["id"], "naam": naam, "omschrijving": omschrijving}


def compact(entiteit: dict) -> dict:
    """Wat er van een item bewaard wordt: namen, andere schrijfwijzen, omschrijvingen en in welke Wikipedia's het een
    artikel heeft. De rest van het item (alle uitspraken) blijft bij Wikidata."""
    return {"id": entiteit.get("id"), "labels": entiteit.get("labels") or {}, "aliases": entiteit.get("aliases") or {},
            "descriptions": {t: v for t, v in (entiteit.get("descriptions") or {}).items() if t == "en"},
            "sitelinks": {k: {} for k in entiteit.get("sitelinks") or {}}}


def wikis_van(sitelinks: dict | None) -> int:
    """In hoeveel talen van Wikipedia er een artikel is; Commons, Wikiquote en dergelijke tellen niet."""
    return sum(1 for k in (sitelinks or {}) if _WIKI.fullmatch(k) and k not in NIET_WIKI)


def kenmerken(entiteit: dict | None, p31: list[str]) -> dict | None:
    """Wat de site van een nummer nodig heeft: de naam in de vijf talen (anders de Engelse), het aantal Wikipedia's,
    en of Wikidata het een mens noemt of iets dat nooit een naam is. Zonder Engelse naam: niets."""
    if not isinstance(entiteit, dict) or "missing" in entiteit:
        return None
    labels = {t: schoon(str(v.get("value") or "")) for t, v in (entiteit.get("labels") or {}).items() if isinstance(v, dict)}
    engels = labels.get("en") or labels.get("mul")
    if not engels:
        return None
    anders = [schoon(str(a.get("value") or "")) for lijst in (entiteit.get("aliases") or {}).values()
              if isinstance(lijst, list) for a in lijst if isinstance(a, dict)]
    return {"namen": {t: labels.get(t) or labels.get("mul") or engels for t in SITETALEN},
            "vormen": sorted({v for v in [*labels.values(), *anders] if v}),
            "wikis": wikis_van(entiteit.get("sitelinks")), "mens": MENS in p31, "weg": any(p in WEG for p in p31),
            "zonder_soort": not p31}


def bijnamen(vormen: list[str], namen: dict[str, str], lengte: int = 100) -> list[str]:
    """De andere schrijfwijzen van een naam voor de uitgave (PLAN #34.2z): wat Wikidata kent, met de witruimte
    rechtgezet, zonder de vijf namen die er al staan (hoofdletters tellen niet), zonder een vorm zonder letter (emoji,
    tekens) en zonder een vorm langer dan `lengte`. Welke ervan helpen bij zoeken, beslist het zoeken zelf."""
    eigen = {schoon(n).casefold() for n in namen.values()}
    uit = set()
    for v in vormen:
        v = " ".join(str(v or "").split())
        if (v and len(v) <= lengte and v.casefold() not in eigen
                and any(unicodedata.category(t).startswith("L") for t in v)):
            uit.add(v)
    return sorted(uit)


def soort_past(soort: str, wd: dict) -> bool:
    """Spreken het model en Wikidata elkaar niet tegen? Een persoon is een mens. Een organisatie of plaats is geen mens,
    geen ding of gebeurtenis (`WEG`), en heeft bij Wikidata een soort: een algemeen begrip ("verkiezingscommissie")
    heeft er geen."""
    if wd["weg"]:
        return False
    return wd["mens"] if soort == "persoon" else not wd["mens"] and not wd.get("zonder_soort")


# --- staat de naam er ook -------------------------------------------------------------------------------------------

# Woordjes in een naam die niets bewijzen als ze los in een tekst staan.
_LIDWOORD = frozenset("de da do dos das del della di du la le el al bin ibn van von der den ter te y e i jr sr ii iii".split())


def _woorden(tekst: str) -> list[str]:
    """De woorden van een tekst zonder hoofdletters: gesplitst op witruimte en op leestekens binnen een woord, nooit op
    een patroon van "woordtekens" (dat breekt de Indiase schriften)."""
    plat = "".join(t if unicodedata.category(t)[0] in "LMN" else " " for t in tekst.casefold())
    return plat.split()


# Titels en aanspreekvormen: een deel van hoe iemand heet ("Pope Francis", "Queen Camilla"), maar geen naam. Staat
# alleen de titel in een bewering, dan is niet gezegd wie bedoeld is.
_TITEL = frozenset("""of the and pope queen king prince princess duke duchess president minister prime sir lord lady dr mr mrs ms
saint st san santa sheikh shri sri general senator governor mayor chief justice judge emperor empress sultan
presidente ministro rey reina papa könig königin papst prinz prinzessin präsident roi reine pape président ministre
koning koningin paus prins prinses""".split())


def genoemd(teksten: list[str], vormen: list[str], delen: list[str] | tuple[str, ...] = ()) -> bool:
    """Staat de naam in de bewering of in een vertaling ervan? Een vorm die Wikidata kent (de naam of een andere
    schrijfwijze), telt als zij er als hele woorden staat, en een vorm van vijf tekens of meer ook binnen een woord
    (een hashtag, "Ugandan"). Bij een persoon is één deel van de naam genoeg (de achternaam): `delen` zijn de namen
    waarvan de delen zo tellen. Een lidwoord of een titel is geen deel, en een woord uit een andere schrijfwijze
    ("Minister Barroso") ook niet. Wat niet na te gaan is, staat er niet."""
    woorden = [w for tekst in teksten for w in _woorden(tekst or "")]
    if not woorden:
        return False
    los, zin = set(woorden), " " + " ".join(woorden) + " "
    for vorm in vormen:
        stukken = _woorden(vorm)
        if not stukken:
            continue
        heel = " ".join(stukken)
        if len(heel) >= 2 and f" {heel} " in zin:
            return True
        aaneen = "".join(stukken)
        if len(aaneen) >= 5 and any(aaneen in w for w in los):
            return True
    for naam in delen:
        for d in _woorden(naam):
            if d in _LIDWOORD or d in _TITEL or len(d) < 2:
                continue
            if d in los or (len(d) >= 5 and any(d in w for w in los)):
                return True
    return False


def houd_genoemd(geteld: dict[str, dict], keuzes: dict[str, str | None], wikidata: dict[str, dict | None],
                 teksten: dict[str, list[str]]) -> tuple[dict[str, dict], int]:
    """Laat per schrijfwijze alleen de pagina's staan waar de naam (in een vorm die Wikidata kent) ook staat, en zegt
    hoeveel paren vervielen. Een schrijfwijze zonder nummer blijft zoals zij is: die valt bij het samenstellen af."""
    uit, weg = {}, 0
    for s, t in geteld.items():
        wd = wikidata.get(keuzes.get(s) or "")
        if not wd:
            uit[s] = t
            continue
        delen = sorted(set((wd.get("namen") or {}).values())) if wd.get("mens") else ()
        blijft = [p for p in t["paginas"] if genoemd(teksten.get(p, []), wd.get("vormen", []), delen)]
        weg += len(t["paginas"]) - len(blijft)
        uit[s] = {**t, "paginas": blijft}
    return uit, weg


# --- de keuze tussen kandidaten -------------------------------------------------------------------------------------

_KEUZE = (
    "You link a name that was found in fact-checked claims to its item on Wikidata. You get the name, its kind, the "
    "numbered candidate items with their descriptions, and claims that mention the name. Choose the item the claims "
    'are about and answer with its number in the list ("1", "2", ...). Answer "geen" if no candidate fits, if you cannot tell which one is meant, if the claims are about '
    "different bearers of the name, or if they are about a private person who only shares the name with a candidate. "
    "Do not judge whether the claims are true.")
_SOORT_EN = {"persoon": "person", "organisatie": "organisation", "plaats": "place"}
_KEUZES = ("1", "2", "3", "4", "5", "geen")


def keuzeverzoek(naam: str, soort: str, kandidaten: list[dict], voorbeelden: list[str]) -> dict:
    from doublecheck.modellen import MODELLEN

    regels = [f"Name: {naam} ({_SOORT_EN.get(soort, soort)})", "Candidates:"]
    regels += [f"{i}. {k['nummer']}: {k['naam']}" + (f" ({k['omschrijving']})" if k["omschrijving"] else "")
               for i, k in enumerate(kandidaten[:len(_KEUZES) - 1], 1)]
    regels.append("Claims that mention the name:")
    regels += [f"- {' '.join((v or '').split())[:300]}" for v in voorbeelden[:3]]
    # Eén vast antwoordschema voor elke naam: een schema per naam (met haar eigen nummers) loopt bij de aanbieder
    # tegen de grens van vijftig nieuwe schema's per minuut aan.
    schema = {"type": "object", "additionalProperties": False, "required": ["keuze"],
              "properties": {"keuze": {"type": "string", "enum": list(_KEUZES)}}}
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 1500, "system": _KEUZE,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "\n".join(regels)}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_keuze(tekst: str | None, kandidaten: list[dict]) -> str | None:
    """Het nummer bij Wikidata van de gekozen kandidaat, een lege tekst bij *geen*, en niets als het antwoord niet te
    lezen is of een plek in de lijst noemt waar geen kandidaat stond."""
    try:
        keuze = json.loads(tekst)["keuze"]  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
    if keuze == "geen":
        return ""
    if keuze in _KEUZES and int(keuze) <= len(kandidaten):
        return kandidaten[int(keuze) - 1]["nummer"]
    return None


def geldende_keuzes(rijen: list[dict]) -> dict[str, str]:
    """Per schrijfwijze de laatste keuze. Een regel zonder keuze na een keuze trekt haar in (de naam is opnieuw
    opgezocht en heeft andere kandidaten); een antwoord dat niet te lezen was, verandert niets aan een eerdere keuze
    die er niet was."""
    laatste: dict[str, str | None] = {}
    for r in rijen:
        laatste[r["sleutel"]] = r.get("keuze")
    return {s: k for s, k in laatste.items() if k is not None}


# --- welke namen op de site mogen -----------------------------------------------------------------------------------

def niet_lijst(pad: str | Path = NIET_PAD) -> frozenset[str]:
    """De nummers die een mens weghaalde, elk met een reden. Geen bestand: niemand weggehaald."""
    pad = Path(pad)
    if not pad.exists():
        return frozenset()
    try:
        namen = json.loads(pad.read_text(encoding="utf-8"))["namen"]
        if not isinstance(namen, list):
            raise TypeError
        for n in namen:
            if not _NUMMER.fullmatch(n["nummer"]) or not str(n["reden"]).strip():
                raise ValueError
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as fout:
        raise Weigering(f"{pad.name}: elke regel heeft een nummer (Q…) en een reden") from fout
    return frozenset(n["nummer"] for n in namen)


def stel_samen(geteld: dict[str, dict], keuzes: dict[str, str | None], wikidata: dict[str, dict | None],
               redacties: dict[str, set[str]], niet: frozenset[str] | set[str] = frozenset()) -> dict:
    """De namen die op de site mogen, per nummer van Wikidata, en hoeveel er afvielen per regel. Schrijfwijzen die
    naar hetzelfde nummer wijzen, tellen samen. Een naam mag alleen als (1) er een nummer bij hoort met een artikel in
    minstens `MIN_WIKIS` talen van Wikipedia, (2) hij op minstens `MIN_PAGINAS` pagina's staat, (3) bij een persoon
    Wikidata het een mens noemt en de pagina's van minstens `MIN_REDACTIES` redacties komen, en (4) de soort van het
    model en die van Wikidata elkaar niet tegenspreken. Wat een mens weghaalde, valt altijd af."""
    afgevallen: Counter = Counter()
    per: dict[str, dict] = {}
    for s, t in geteld.items():
        nummer = keuzes.get(s)
        if not nummer:
            afgevallen["geen-nummer"] += 1
            continue
        p = per.setdefault(nummer, {"paginas": set(), "soort": Counter()})
        p["paginas"].update(t["paginas"])
        p["soort"][t["soort"]] += len(t["paginas"])
    namen = {}
    for nummer in sorted(per, key=lambda q: int(q[1:])):
        p, wd = per[nummer], wikidata.get(nummer)
        soort = p["soort"].most_common(1)[0][0]
        if nummer in niet:
            reden = "weggehaald"
        elif wd is None:
            reden = "onleesbaar"
        elif not soort_past(soort, wd):
            reden = "soort"
        elif wd["wikis"] < MIN_WIKIS:
            reden = "wikis"
        elif len(p["paginas"]) < MIN_PAGINAS:
            reden = "paginas"
        elif soort == "persoon" and len(set().union(*(redacties.get(x, set()) for x in p["paginas"]))) < MIN_REDACTIES:
            reden = "redacties"
        else:
            namen[nummer] = {"soort": soort, "namen": wd["namen"], "wikis": wd["wikis"], "paginas": sorted(p["paginas"])}
            continue
        afgevallen[reden] += 1
    return {"namen": namen, "afgevallen": dict(afgevallen)}


def per_pagina(rijen: list[dict], keuzes: dict[str, str | None], namen: dict[str, dict]) -> dict[str, list[str]]:
    """Per pagina de nummers van haar namen, in de volgorde waarin het model ze noemde; alleen namen die mogen."""
    uit: dict[str, list[str]] = {}
    for nummer, lijst in laatste(rijen).items():
        rij = []
        for n in lijst:
            q = keuzes.get(sleutel(n["naam"]))
            if q and q in namen and q not in rij and nummer in namen[q]["paginas"]:
                rij.append(q)
        if rij:
            uit[nummer] = rij
    return uit


# --- de poort en de leesronde van de PO ------------------------------------------------------------------------------

_AKKOORD = re.compile(r'(\d{4}-\d{2}-\d{2}), PO: "[^"\n]{2,}"')


def akkoord_geldig(akkoord) -> bool:
    """Een akkoord van de PO is haar woorden met de datum erbij: `2026-11-12, PO: "…"`."""
    from datetime import date

    gevonden = _AKKOORD.fullmatch(akkoord) if isinstance(akkoord, str) else None
    try:
        return bool(gevonden and date.fromisoformat(gevonden.group(1)))
    except ValueError:
        return False


def poort(pad: str | Path = PO_LABELS) -> tuple[bool, str]:
    """Mogen de namen op de site? (SPECS E9.S11 AC3.) Een willekeurige steekproef is nagelezen volgens de regel van de
    thema's (van 200 gelezen 180 goed, of wat met 95% zekerheid 90% draagt), en er zat geen enkele privépersoon in:
    één privépersoon sluit de poort, wat de rest ook is. Wie las: de PO, of Claude met een akkoord van de PO dat met
    haar woorden en de datum is vastgelegd (PO 2026-11-12). Een lezing zonder dat akkoord opent niets, en een akkoord
    zonder lezing ook niet."""
    try:
        d = json.loads(Path(pad).read_text(encoding="utf-8"))
        labels = [w for w in d["labels"].values() if w in ("goed", "fout", "twijfel", "prive")]
        door = str(d.get("gelezen_door", "")).strip()
        akkoord = d.get("akkoord")
    except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return False, "er is nog niets gelezen"
    goed, gelezen, prive = sum(w == "goed" for w in labels), len(labels), sum(w == "prive" for w in labels)
    zelf = door.upper().startswith("PO")
    if not zelf and not akkoord_geldig(akkoord):
        return False, f"gelezen door {door or 'onbekend'}, zonder een vastgelegd akkoord van de PO"
    wie = "door de PO gelezen" if zelf else f"gelezen door {door}, met het akkoord van de PO"
    if prive:
        return False, f"{prive} privépersoon in wat gelezen is: de namen blijven dicht"
    if (gelezen >= POORT_N and goed >= POORT_GOED) or draagt(goed, gelezen):
        return True, f"{goed} van de {gelezen} goed, geen privépersoon; {wie}"
    return False, (f"{goed} van de {gelezen} goed; dat is nog niet genoeg (van {POORT_N} gelezen {POORT_GOED} goed, of "
                   f"met {POORT_ZEKERHEID:.0%} zekerheid minstens {POORT_AANDEEL:.0%})")


def po_kaarten(samen: dict, paginas: dict[str, tuple[str, str]], vertalingen: dict[str, str],
               omschrijvingen: dict[str, str], n: int = POORT_N, zaad: int = ZAAD) -> list[dict]:
    """De kaarten voor de PO: willekeurige paren van een bewering en een naam, elke naam hoogstens één keer, en alleen
    beweringen die zij kan lezen (Engels of Nederlands, of met de Engelse vertaling die er ligt)."""
    paren = sorted((p, q) for q, naam in samen["namen"].items() for p in naam["paginas"]
                   if p in paginas and (paginas[p][1] in PO_TALEN or vertalingen.get(p)))
    random.Random(zaad).shuffle(paren)
    kaarten, gehad = [], set()
    for p, q in paren:
        if q in gehad:
            continue
        gehad.add(q)
        tekst, taal = paginas[p]
        naam = samen["namen"][q]
        kaarten.append({"id": f"{p}-{q}", "pagina": p, "nummer": q, "bewering": tekst, "taal": taal,
                        "richting": "rtl" if taal.split("-")[0] in RTL else "ltr",
                        "vertaling": "" if taal in PO_TALEN else vertalingen.get(p, ""),
                        "naam": naam["namen"]["en"], "naam_nl": naam["namen"].get("nl", ""), "soort": naam["soort"],
                        "omschrijving": omschrijvingen.get(q, "")})
        if len(kaarten) == n:
            break
    return kaarten


def po_uitslag(kaarten: list[dict], keuzes: dict[str, dict]) -> dict:
    """Wat de keuzes van de PO betekenen: *klopt* is goed; *klopt niet* is fout, en met *dit is een privépersoon*
    het eigen label `prive`, dat de poort sluit. Een kaart met een notitie en zonder keuze is twijfel: gelezen en
    niet goed. `mis` telt wat zij aanwees."""
    labels, opmerkingen, mis = {}, {}, {m: 0 for m in PO_MIS}
    for k in kaarten:
        keuze = keuzes.get(k["id"]) or {}
        notitie = (keuze.get("opmerking") or "").strip()
        if notitie:
            opmerkingen[k["id"]] = notitie
        if keuze.get("oordeel") not in ("goed", "fout"):
            if notitie:
                labels[k["id"]] = "twijfel"
            continue
        aangewezen = set(keuze.get("mis") or []) & set(PO_MIS) if keuze["oordeel"] == "fout" else set()
        for m in aangewezen:
            mis[m] += 1
        labels[k["id"]] = "goed" if keuze["oordeel"] == "goed" else "prive" if "prive" in aangewezen else "fout"
    return {"labels": labels, "opmerkingen": opmerkingen, "mis": mis}


def po_pagina(kaarten: list[dict]) -> str:
    """De nakijkpagina met de kaarten erin, als JSON in een scripttag; een `</` in een bewering sluit die tag nooit."""
    sjabloon = (Path(__file__).resolve().parent / "namen_pagina.html").read_text(encoding="utf-8")
    data = {"ronde": PO_RONDE, "nodig": POORT_GOED, "kaarten": kaarten}
    return sjabloon.replace("/*KAARTEN*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# --- bestanden, het model en het netwerk ----------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    kandidaten = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not kandidaten:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    return sqlite3.connect(f"{kandidaten[-1].resolve().as_uri()}?mode=ro", uri=True)


def _paginas() -> dict[str, tuple[str, str]]:  # pragma: no cover - een bestand
    return {r[0]: (r[1], r[2]) for r in _publicatie().execute("SELECT nummer, bewering, taal FROM pagina")}


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    direct = sum(r.get("kosten", 0.0) for pad in sorted(MAP.glob("proef*.jsonl")) for r in _jsonl(pad))
    batches = sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"]
                  for naam in ("vol-batches.jsonl", "keuze-batches.jsonl") for b in _jsonl(MAP / naam))
    return direct + batches


def _proef(n: int) -> None:  # pragma: no cover - een model
    """Een greep van `n` beweringen, direct en tegelijk: wat kost het, en hoeveel namen komen eruit?"""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.themas import steekproef
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    klaar = {r["nummer"] for r in _jsonl(MAP / "proef.jsonl")}
    werk = groepen([nr for nr in steekproef(list(paginas), n, ZAAD) if nr not in klaar])
    if werk:
        binnen_grens(2 * SCHATTING * sum(len(g) for g in werk), _uitgegeven())
        laad_sleutel()
        client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]

        def een(groep: list[str]) -> None:
            try:
                msg = client.messages.create(**naamverzoek([paginas[nr] for nr in groep]))
                kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
                tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
            except Exception as fout:  # noqa: BLE001 - alleen de soort fout
                print("fout:", type(fout).__name__, flush=True)
                return
            with slot:
                _schrijf(MAP / "proef.jsonl", [{"nummer": nr, "taal": paginas[nr][1], "namen": g,
                                               "kosten": round(kosten / len(groep), 7)}
                                              for nr, g in zip(groep, lees_namen(tekst, len(groep)))])

        with ThreadPoolExecutor(DRADEN) as pool:
            list(pool.map(een, werk))
    rijen = _jsonl(MAP / "proef.jsonl")
    gelezen = [r for r in rijen if r["namen"] is not None]
    kosten = sum(r["kosten"] for r in rijen)
    per_soort = Counter(x["soort"] for r in gelezen for x in r["namen"])
    print(json.dumps({
        "gevraagd": len(rijen), "onleesbaar": len(rijen) - len(gelezen),
        "met_een_naam": sum(bool(r["namen"]) for r in gelezen), "namen": sum(per_soort.values()), "per_soort": dict(per_soort),
        "kosten_direct": round(kosten, 4),
        "geschat_vol_batch": round(kosten / 2 / max(len(rijen), 1) * len(paginas), 2), "paginas": len(paginas)},
        ensure_ascii=False, indent=1))


def nog_te_vragen(nummers: list[str], rijen: list[dict], kaart: list[dict], batches: list[dict]) -> list[str]:
    """Wat de volle ronde nog moet vragen: alles zonder leesbaar antwoord dat niet in een batch zit die nog loopt."""
    klaar = {r["nummer"] for r in rijen if r.get("namen") is not None}
    lopend = {b["id"] for b in batches if b.get("werkelijk") is None}
    onderweg = {nr for k in kaart if k.get("batch") in lopend for nr in k["nummers"]}
    return sorted(set(nummers) - klaar - onderweg)


def _batches(stap: str, wacht: int, deel: str, werk_fn, verzoek_fn, lees_fn, schatting: float) -> None:  # pragma: no cover
    """Indienen en ophalen via de Batch API, voor het lezen (`vol`) en het kiezen (`keuze`). `werk_fn()` geeft de
    groepen die nog moeten, `verzoek_fn(groep)` de vraag, `lees_fn(groep, tekst)` de regels voor het uitvoerbestand."""
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    uit = MAP / ("namen.jsonl" if deel == "vol" else "keuzes.jsonl")
    batches = _jsonl(MAP / f"{deel}-batches.jsonl")
    laad_sleutel()
    client = anthropic.Anthropic()
    if stap == "indienen":
        werk = werk_fn()
        if not werk:
            print("niets in te dienen")
            return
        from doublecheck import routinegrens as rg

        geschat = round(schatting * sum(len(g) for g in werk), 2)
        if rg.uitgave():            # onder de routine per week telt haar grens, niet die voor altijd (PLAN #35.2)
            if not rg.past(geschat):
                raise Weigering(f"geschat ${geschat:.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
        else:
            binnen_grens(geschat, _uitgegeven())
        for begin in range(0, len(werk), 5000):
            stuk = werk[begin:begin + 5000]
            nr0 = len(_jsonl(MAP / f"{deel}-kaart.jsonl"))
            batch = client.messages.batches.create(requests=[
                {"custom_id": f"{deel}-{nr0 + i}", "params": verzoek_fn(g)} for i, g in enumerate(stuk)])
            _schrijf(MAP / f"{deel}-kaart.jsonl", [{"custom_id": f"{deel}-{nr0 + i}", "nummers": g, "batch": batch.id}
                                                  for i, g in enumerate(stuk)])
            rij = rg.merk({"id": batch.id, "vragen": len(stuk), "stuks": sum(len(g) for g in stuk),
                           "schatting": round(schatting * sum(len(g) for g in stuk), 2)})
            _schrijf(MAP / f"{deel}-batches.jsonl", [rij])
            print(f"batch {batch.id}: {rij['vragen']} vragen, {rij['stuks']} stuks, schatting ${rij['schatting']}", flush=True)
        print(f"samen ${_uitgegeven():.2f} van ${GRENS:.2f}")
        return
    kaart = {k["custom_id"]: k for k in _jsonl(MAP / f"{deel}-kaart.jsonl")}
    einde = time.time() + 60 * wacht
    while True:
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, regels = 0.0, []
            for r in client.messages.batches.results(b["id"]):
                k = kaart.get(r.custom_id)
                if k is None:
                    continue
                tekst = None
                if r.result.type == "succeeded":
                    msg = r.result.message
                    werkelijk += kosten_batch(bc.gebruik_uit(msg), "haiku")
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                regels += lees_fn(k["nummers"], tekst)
            _schrijf(uit, regels)
            b["werkelijk"] = round(werkelijk, 4)
            print(f"batch {b['id']}: {len(regels)} regels, ${werkelijk:.2f}", flush=True)
        (MAP / f"{deel}-batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    print(f"{open_} batch(es) lopen nog; ${_uitgegeven():.2f} van ${GRENS:.2f}")


def _vol(stap: str, wacht: int) -> None:  # pragma: no cover - de Batch API
    paginas = _paginas()
    _batches(
        stap, wacht, "vol",
        lambda: groepen(nog_te_vragen(list(paginas), _jsonl(MAP / "namen.jsonl"), _jsonl(MAP / "vol-kaart.jsonl"),
                                      _jsonl(MAP / "vol-batches.jsonl"))),
        lambda g: naamverzoek([paginas[nr] for nr in g]),
        lambda g, tekst: [{"nummer": nr, "namen": x, "versie": VERSIE} for nr, x in zip(g, lees_namen(tekst, len(g)))],
        SCHATTING)
    rijen = _jsonl(MAP / "namen.jsonl")
    print(f"{len(laatste(rijen))} van {len(paginas)} pagina's gelezen")


def _geteld() -> dict[str, dict]:  # pragma: no cover - een bestand
    return tel(_jsonl(MAP / "namen.jsonl"))


def _tellen() -> None:  # pragma: no cover - bestanden
    rijen = _jsonl(MAP / "namen.jsonl")
    gelezen, geteld = laatste(rijen), _geteld()
    verdeling = Counter(min(len(t["paginas"]), 10) for t in geteld.values())
    print(json.dumps({
        "paginas_gelezen": len(gelezen), "met_een_naam": sum(bool(v) for v in gelezen.values()),
        "schrijfwijzen": len(geteld), "per_soort": dict(Counter(t["soort"] for t in geteld.values())),
        "op_n_paginas": {str(k) + ("+" if k == 10 else ""): verdeling[k] for k in sorted(verdeling)},
        "op_te_zoeken": sum(len(t["paginas"]) >= ZOEK_VANAF for t in geteld.values()),
        "vaakst": [(t["naam"], t["soort"], len(t["paginas"]))
                   for t in sorted(geteld.values(), key=lambda t: -len(t["paginas"]))[:40]]}, ensure_ascii=False, indent=1))


def _vraag_wikimedia(web, url: str, params: dict, pogingen: int = 5):  # pragma: no cover - het netwerk
    """Eén leesvraag aan Wikipedia of Wikidata: nooit twee tegelijk, een vaste pauze ervoor, en geduld als de dienst
    zegt dat het druk is. Geen antwoord na vijf keer: niets, en de aanroeper stopt (hervatbaar)."""
    import time

    for poging in range(pogingen):
        time.sleep(PAUZE)
        r = web.get(url, params={**params, "format": "json", "maxlag": 5})
        if r.status_code == 200:
            try:
                antwoord = r.json()
            except ValueError:
                antwoord = None
            if isinstance(antwoord, dict) and "error" not in antwoord:
                return antwoord
        wacht = r.headers.get("retry-after", "")
        time.sleep(min(120, (int(wacht) if wacht.isdigit() else 10) * (poging + 1)))
    return None


def _entiteiten(web, nummers: list[str]) -> dict[str, dict] | None:  # pragma: no cover - het netwerk
    """De items bij deze nummers, vijftig per vraag; wat al eens gehaald is, komt uit `entiteiten.jsonl`."""
    bekend = {r["id"]: r for r in _jsonl(MAP / "entiteiten.jsonl")}
    nodig = [q for q in nummers if q not in bekend]
    for begin in range(0, len(nodig), 50):
        deel = nodig[begin:begin + 50]
        antwoord = _vraag_wikimedia(web, WIKIDATA, {"action": "wbgetentities", "ids": "|".join(deel),
                                                    "props": "labels|descriptions|aliases|sitelinks",
                                                    "languages": "|".join(SITETALEN + ("mul",))})
        if antwoord is None:
            return None
        nieuw = [compact({**(antwoord.get("entities", {}).get(q) or {}), "id": q}) for q in deel]
        _schrijf(MAP / "entiteiten.jsonl", nieuw)
        bekend.update({e["id"]: e for e in nieuw})
    return {q: bekend[q] for q in nummers}


def _zoeken(maximum: int | None) -> None:  # pragma: no cover - het netwerk
    """Brengt elke schrijfwijze die vaak genoeg voorkomt naar kandidaten bij Wikidata; de vaakste eerst. Eerst als
    titel bij de Engelse Wikipedia (het model geeft de naam zoals die haar artikel noemt), vijftig per vraag; wat
    daar geen artikel is of een doorverwijspagina, wordt bij Wikidata gezocht, één per vraag. Hervatbaar."""
    import httpx

    geteld = _geteld()

    def klaar() -> set[str]:
        # een naam met iets tussen haken die niets vond, gaat nog één keer, zonder de haken
        return {r["sleutel"] for r in _jsonl(MAP / "zoek.jsonl")
                if r["kandidaten"] or "(" not in r["naam"] or r.get("zonder_haken")}

    gedaan = klaar()
    werk = sorted((s for s, t in geteld.items() if len(t["paginas"]) >= ZOEK_VANAF and s not in gedaan),
                  key=lambda s: -len(geteld[s]["paginas"]))[:maximum]
    # Wat vóór de titelstap alleen bij de zoekfunctie is opgezocht (zonder `via`), gaat alsnog langs zijn titel: de
    # zoekfunctie zet bij "China" de cultuurregio boven het land. Vindt de titel iets, dan vervalt de oude keuze.
    oud = [s for s, r in {r["sleutel"]: r for r in _jsonl(MAP / "zoek.jsonl")}.items() if "via" not in r and s in geteld]
    print(f"{len(werk)} schrijfwijzen op te zoeken, {len(gedaan)} al gedaan, {len(oud)} opnieuw langs hun titel", flush=True)
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=60) as web:
        titels = [s for s in werk + oud if "|" not in geteld[s]["naam"]]
        for begin in range(0, len(titels), 50):
            deel = titels[begin:begin + 50]
            antwoord = _vraag_wikimedia(web, WIKIPEDIA, {
                "action": "query", "formatversion": 2, "redirects": 1, "prop": "pageprops",
                "ppprop": "wikibase_item|disambiguation", "titles": "|".join(geteld[s]["naam"] for s in deel)})
            gevonden = titels_uit(antwoord, [geteld[s]["naam"] for s in deel]) if antwoord is not None else None
            items = _entiteiten(web, sorted(set(gevonden.values()))) if gevonden is not None else None
            if items is None:
                print("Wikipedia of Wikidata antwoordt niet; later verder", flush=True)
                return
            rijen = []
            for s in deel:
                k = kandidaat_van(items.get(gevonden.get(geteld[s]["naam"], "")))
                if k:
                    rijen.append({"sleutel": s, "naam": geteld[s]["naam"], "kandidaten": [k], "via": "titel"})
            _schrijf(MAP / "zoek.jsonl", rijen)
            opnieuw = [r["sleutel"] for r in rijen if r["sleutel"] in oud]
            _schrijf(MAP / "keuzes.jsonl", [{"sleutel": s, "keuze": None, "versie": KEUZEVERSIE, "reden": "opnieuw opgezocht"}
                                            for s in opnieuw])
            if (begin // 50) % 20 == 19:
                print(f"titels: {begin + 50} van {len(titels)}", flush=True)
        gedaan = klaar()
        rest = [s for s in werk if s not in gedaan]
        print(f"{len(werk) - len(rest)} hebben een kandidaat via hun titel; {len(rest)} gaan naar de zoekfunctie", flush=True)
        for i, s in enumerate(rest, 1):
            vraag = {"action": "wbsearchentities", "language": "en", "uselang": "en", "type": "item", "limit": 5}
            antwoord = _vraag_wikimedia(web, WIKIDATA, {**vraag, "search": geteld[s]["naam"]})
            kaal = schoon(re.sub(r"\([^)]*\)", " ", geteld[s]["naam"]))
            zonder_haken = antwoord is not None and not kandidaten_uit(antwoord) and kaal and kaal != geteld[s]["naam"]
            if zonder_haken:
                antwoord = _vraag_wikimedia(web, WIKIDATA, {**vraag, "search": kaal})
            if antwoord is None:
                print("Wikidata antwoordt niet; later verder", flush=True)
                break
            _schrijf(MAP / "zoek.jsonl", [{"sleutel": s, "naam": geteld[s]["naam"], "kandidaten": kandidaten_uit(antwoord),
                                          "via": "zoek", **({"zonder_haken": True} if zonder_haken else {})}])
            if i % 250 == 0:
                print(f"zoeken: {i} van {len(rest)}", flush=True)
    rijen = {r["sleutel"]: r for r in _jsonl(MAP / "zoek.jsonl")}
    print(f"{len(rijen)} opgezocht, {sum(not r['kandidaten'] for r in rijen.values())} zonder kandidaat, "
          f"{sum(r.get('via') == 'titel' for r in rijen.values())} via hun titel")


def _kiezen(stap: str, wacht: int) -> None:  # pragma: no cover - de Batch API
    geteld, paginas = _geteld(), _paginas()
    zoek = {s: r for s, r in {r["sleutel"]: r for r in _jsonl(MAP / "zoek.jsonl")}.items() if r["kandidaten"]}

    def werk() -> list[list[str]]:
        klaar = set(_keuzes())
        lopend = {b["id"] for b in _jsonl(MAP / "keuze-batches.jsonl") if b.get("werkelijk") is None}
        onderweg = {s for k in _jsonl(MAP / "keuze-kaart.jsonl") if k.get("batch") in lopend for s in k["nummers"]}
        return [[s] for s in sorted(zoek) if s in geteld and s not in klaar and s not in onderweg]

    def verzoek(groep: list[str]) -> dict:
        s = groep[0]
        # alleen pagina's die in de uitgave staan: een gelezen pagina kan er sindsdien uit zijn (PLAN #35.2)
        bestaand = [p for p in geteld[s]["paginas"] if p in paginas]
        voorbeelden = [paginas[p][0] for p in random.Random(ZAAD).sample(bestaand, min(3, len(bestaand)))]
        return keuzeverzoek(geteld[s]["naam"], geteld[s]["soort"], zoek[s]["kandidaten"], voorbeelden)

    _batches(stap, wacht, "keuze", werk, verzoek,
             lambda g, tekst: [{"sleutel": g[0], "keuze": lees_keuze(tekst, zoek[g[0]]["kandidaten"]), "versie": KEUZEVERSIE}],
             SCHATTING_KEUZE)
    keuzes = _keuzes()
    print(f"{len(keuzes)} keuzes: {sum(bool(v) for v in keuzes.values())} met een nummer, "
          f"{sum(v == '' for v in keuzes.values())} zonder")


def _keuzes() -> dict[str, str | None]:  # pragma: no cover - een bestand
    return geldende_keuzes(_jsonl(MAP / "keuzes.jsonl"))


def _kenmerken() -> None:  # pragma: no cover - het netwerk
    """Haalt van elk gekozen nummer de namen en de Wikipedia's (wat bij het zoeken al gehaald is, ligt er) en wat voor
    iets het is (de zoekdienst van Wikidata, tweehonderd per vraag). Hervatbaar."""
    import httpx

    klaar = {r["nummer"] for r in _jsonl(MAP / "wikidata.jsonl")}
    werk = sorted({q for q in _keuzes().values() if q} - klaar, key=lambda q: int(q[1:]))
    print(f"{len(werk)} nummers op te halen, {len(klaar)} al gedaan", flush=True)
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=60) as web:
        for begin in range(0, len(werk), 200):
            deel = werk[begin:begin + 200]
            vraag = "SELECT ?i ?t WHERE { VALUES ?i { " + " ".join("wd:" + q for q in deel) + " } ?i wdt:P31 ?t }"
            antwoord = _vraag_wikimedia(web, SPARQL, {"query": vraag})
            items = _entiteiten(web, deel) if antwoord is not None else None
            if items is None:
                print("Wikidata antwoordt niet; later verder", flush=True)
                return
            p31: dict[str, list[str]] = {}
            for b in antwoord["results"]["bindings"]:
                p31.setdefault(b["i"]["value"].rsplit("/", 1)[-1], []).append(b["t"]["value"].rsplit("/", 1)[-1])
            _schrijf(MAP / "wikidata.jsonl", [{"nummer": q, "kenmerken": kenmerken(items[q], p31.get(q, [])),
                                              "p31": p31.get(q, [])} for q in deel])
            print(f"{min(begin + 200, len(werk))} van {len(werk)}", flush=True)
    rijen = _jsonl(MAP / "wikidata.jsonl")
    print(f"{len(rijen)} nummers, {sum(r['kenmerken'] is None for r in rijen)} zonder Engelse naam")


def vormen_van_wikidata() -> dict[str, list[str]]:  # pragma: no cover - een bestand
    """Per nummer de schrijfwijzen die Wikidata kent: de labels en aliassen in de vijf talen en `mul`, opgehaald bij
    `kenmerken` (33.7). Geen nieuwe vraag aan Wikidata."""
    uit = {}
    for r in _jsonl(MAP / "wikidata.jsonl"):
        if (r.get("kenmerken") or {}).get("vormen"):
            uit[r["nummer"]] = r["kenmerken"]["vormen"]
    return uit


def _redacties() -> dict[str, set[str]]:  # pragma: no cover - een bestand
    uit: dict[str, set[str]] = {}
    for pagina, redactie in _publicatie().execute("SELECT pagina, redactie FROM check_"):
        uit.setdefault(pagina, set()).add(redactie)
    return uit


def _teksten() -> dict[str, list[str]]:  # pragma: no cover - een bestand
    """Per pagina de bewering en haar vertalingen: waarin een naam moet staan."""
    pub = _publicatie()
    uit = {nr: [bewering] for nr, bewering in pub.execute("SELECT nummer, bewering FROM pagina")}
    for pagina, tekst in pub.execute("SELECT pagina, tekst FROM vertaling"):
        uit[pagina].append(tekst)
    return uit


def _samenstellen() -> dict:  # pragma: no cover - bestanden
    items = {r["id"]: r for r in _jsonl(MAP / "entiteiten.jsonl")}
    wikidata = {r["nummer"]: kenmerken(items.get(r["nummer"]), r["p31"]) for r in _jsonl(MAP / "wikidata.jsonl")}
    alles, keuzes = _geteld(), _keuzes()
    geteld, niet_genoemd = houd_genoemd(alles, keuzes, wikidata, _teksten())
    samen = stel_samen(geteld, keuzes, wikidata, _redacties(), niet_lijst())
    samen["niet_genoemd"] = niet_genoemd
    samen["per_pagina"] = per_pagina(_jsonl(MAP / "namen.jsonl"), keuzes, samen["namen"])
    samen["versie"] = {"lezen": VERSIE, "kiezen": KEUZEVERSIE,
                       "regels": {"wikis": MIN_WIKIS, "paginas": MIN_PAGINAS, "redacties": MIN_REDACTIES}}
    (MAP / "samen.json").write_text(json.dumps(samen, ensure_ascii=False), encoding="utf-8")
    namen = samen["namen"]
    print(json.dumps({
        "namen": len(namen), "per_soort": dict(Counter(n["soort"] for n in namen.values())),
        "afgevallen": samen["afgevallen"], "paren_niet_genoemd": niet_genoemd,
        "paginas_met_een_naam": len(samen["per_pagina"]),
        "paren": sum(len(v) for v in samen["per_pagina"].values()), "paginas": len(_paginas()),
        "paren_gelezen": sum(len(t["paginas"]) for t in alles.values()),
        "schrijfwijzen": len(alles), "niet_opgezocht": sum(len(t["paginas"]) < ZOEK_VANAF for t in alles.values())},
        ensure_ascii=False, indent=1))
    return samen


def _omschrijvingen() -> dict[str, str]:  # pragma: no cover - een bestand
    return {k["nummer"]: k["omschrijving"] for r in _jsonl(MAP / "zoek.jsonl") for k in r["kandidaten"]}


def _staart(n: int) -> None:  # pragma: no cover - bestanden
    """De personen met de minste pagina's die de regels halen, met een bewering erbij: wat ik zelf lees (eis a)."""
    samen, paginas, omschrijving = json.loads((MAP / "samen.json").read_text(encoding="utf-8")), _paginas(), _omschrijvingen()
    personen = sorted(((q, v) for q, v in samen["namen"].items() if v["soort"] == "persoon"),
                      key=lambda x: (len(x[1]["paginas"]), x[1]["wikis"], int(x[0][1:])))[:n]
    for q, v in personen:
        print(f"{q} | {v['namen']['en']} | {omschrijving.get(q, '')} | {len(v['paginas'])} pagina's, {v['wikis']} wiki's")
        print("    " + " ".join(paginas[v["paginas"][0]][0].split())[:200])


def _nakijken(deel: str, keuzes_pad: str | None, door: str = "PO", akkoord: str | None = None) -> None:  # pragma: no cover
    kaarten_pad = MAP / "po-kaarten.json"
    if deel == "set":
        if kaarten_pad.exists():
            raise Weigering("de kaarten liggen al vast; een nieuwe trekking is een nieuwe ronde")
        samen = json.loads((MAP / "samen.json").read_text(encoding="utf-8"))
        vertalingen = dict(_publicatie().execute("SELECT pagina, tekst FROM vertaling WHERE taal = 'en'"))
        kaarten = po_kaarten(samen, _paginas(), vertalingen, _omschrijvingen())
        kaarten_pad.write_text(json.dumps(kaarten, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(kaarten)} kaarten; {dict(Counter(k['soort'] for k in kaarten))}")
        return
    kaarten = json.loads(kaarten_pad.read_text(encoding="utf-8"))
    if deel == "pagina":
        (MAP / "nakijken.html").write_text(po_pagina(kaarten), encoding="utf-8")
        print(MAP / "nakijken.html")
        return
    if not keuzes_pad:
        raise Weigering("tellen vraagt --keuzes <json>: de keuzes van de nakijkpagina, of van wie las")
    if akkoord is not None and not akkoord_geldig(akkoord):
        raise Weigering('--akkoord is de datum en de woorden van de PO: 2026-11-12, PO: "…"')
    uit = po_uitslag(kaarten, json.loads(Path(keuzes_pad).read_text(encoding="utf-8")))
    meta = {"taak": "PLAN #33.7, SPECS E9.S11 AC3",
            "herkomst": f"Eigen werk: de lezing van {len(kaarten)} paren (bewering, naam) uit de publicatiedatabase, door "
                        f"{door}" + (", met het akkoord van de PO" if akkoord else "") + ". De beweringen zelf staan niet in "
                        "dit bestand, alleen hun nummer en dat van de naam bij Wikidata.",
            "labels": "goed, fout, twijfel of prive per kaart (pagina-nummer en Q-nummer)"}
    PO_LABELS.write_text(json.dumps({"_meta": meta, "gelezen_door": door, **({"akkoord": akkoord} if akkoord else {}),
                                     "ronde": PO_RONDE, **uit}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tel_ = Counter(uit["labels"].values())
    print(json.dumps({"gelezen": sum(tel_.values()), **tel_, "mis": uit["mis"], "poort": poort()}, ensure_ascii=False))


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["proef", "vol", "tellen", "zoeken", "kiezen", "kenmerken", "samenstellen", "staart",
                                    "nakijken"])
    p.add_argument("deel", nargs="?", help="vol en kiezen: indienen of ophalen; nakijken: set, pagina of tellen")
    p.add_argument("--n", type=int, help="proef: aantal beweringen (300); staart: aantal personen (100)")
    p.add_argument("--max", type=int, help="zoeken: hoogstens zoveel schrijfwijzen in deze ronde")
    p.add_argument("--wacht", type=int, default=0, help="ophalen: zoveel minuten wachten op de batch")
    p.add_argument("--keuzes", help="nakijken tellen: het bestand met de keuzes van wie las")
    p.add_argument("--door", default="PO", help="nakijken tellen: wie las (PO of Claude)")
    p.add_argument("--akkoord", help='nakijken tellen: bij een lezing van Claude het akkoord van de PO, 2026-11-12, PO: "…"')
    a = p.parse_args()
    try:
        if a.stap == "proef":
            _proef(a.n or 300)
        elif a.stap in ("vol", "kiezen"):
            if a.deel not in ("indienen", "ophalen"):
                raise Weigering(f"{a.stap} vraagt indienen of ophalen")
            (_vol if a.stap == "vol" else _kiezen)(a.deel, a.wacht)
        elif a.stap == "tellen":
            _tellen()
        elif a.stap == "zoeken":
            _zoeken(a.max)
        elif a.stap == "kenmerken":
            _kenmerken()
        elif a.stap == "samenstellen":
            _samenstellen()
        elif a.stap == "staart":
            _staart(a.n or 100)
        else:
            if a.deel not in ("set", "pagina", "tellen"):
                raise Weigering("nakijken vraagt set, pagina of tellen")
            _nakijken(a.deel, a.keuzes, a.door, a.akkoord)
    except Weigering as fout:
        raise SystemExit(f"geweigerd: {fout}") from fout


if __name__ == "__main__":  # pragma: no cover
    main()
