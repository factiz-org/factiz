"""Thema's voor het platform (PLAN #33.4, SPECS E9.S5, B72): een vaste lijst van hoogstens twee niveaus.

Eerst verkennen: Haiku zegt van een steekproef beweringen het onderwerp in een paar woorden, een breed veld en het land.
Daaruit komt een voorstel voor de lijst (de PO stelt haar vast). Dan toetsen: Haiku zet een nieuwe steekproef bij een
thema van de lijst, of bij *anders*; hoeveel buiten de lijst valt, zegt of ze past.

    python -m doublecheck.themas verkennen [--n 800]|tellen|toetsen --lijst <json> [--n 400]|uitslag

Leest de publicatiedatabase (openbare beweringen), alleen-lezen. Uitvoer in `data/themas/`.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "themas"
GRENS = 1.50            # dollar voor het verkennen en toetsen samen (PLAN #33.4)
SCHATTING = 0.00015     # per bewering, direct gevraagd
ZAAD = 3304
DRADEN = 8
MAX_TEKENS = 600        # van een bewering in de vraag
VERKENVERSIE = "themaverkenning-v1"
INDEELVERSIE = "thema-v1"
MEERVERSIE = "thema-v2"  # tien beweringen per vraag, met het land; een tweede thema alleen bij uitzondering
LIJST_PAD = WORTEL / "content" / "themas.json"
from doublecheck.sitetalen import BASIS, SITETALEN  # noqa: E402  de talen van de site (B74, B79)
PER_VRAAG = 10
GRENS_VOL = 8.00        # dollar voor de volle ronde via de Batch API (PO 2026-11-11: "prima")
SCHATTING_VOL = 0.000045  # per bewering via de batch; in de hertoets direct $0,000083 bij tien per vraag
# De landcodes van ISO 3166-1 (twee letters), en XK voor Kosovo.
LANDEN = frozenset("""AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT
BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM
FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO
JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT
MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA
SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US
UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW XK""".split())
BREED = ("elections", "politics and government", "international relations", "war and conflict", "health",
         "crime and justice", "disasters and accidents", "economy and business", "climate and environment",
         "science and technology", "migration", "religion and culture", "society and education", "sports",
         "celebrities and entertainment", "other")
_SLEUTEL = re.compile(r"[a-z][a-z0-9-]{1,30}")


class Weigering(Exception):
    """De lijst deugt niet, of de grens in dollars is bereikt."""


def binnen_grens(geschat: float, uitgegeven: float, grens: float = GRENS) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} al uitgegeven plus ${geschat:.2f} is meer dan ${grens:.2f}")


def steekproef(nummers: list[str], n: int, zaad: int = ZAAD, zonder: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """`n` nummers, bij hetzelfde zaad altijd dezelfde, en nooit een nummer uit een eerdere steekproef."""
    kandidaten = sorted(set(nummers) - set(zonder))
    return random.Random(zaad).sample(kandidaten, min(n, len(kandidaten)))


# --- verkennen ----------------------------------------------------------------------------------------------------

_VERKENNEN = """You help organise a public archive of fact-checked claims by subject. For the claim you are given, \
say what it is about. Do not judge whether it is true.

1. "onderwerp": the specific subject in two to five English words, lower case, the way an index would list it \
(for example "covid-19 vaccines", "us presidential election", "india-pakistan conflict", "celebrity death hoax", \
"flood footage"). No names of private persons.
2. "breed": the one broad field that fits best, from the list.
3. "land": the country the claim is mostly about, in English ("India", "United States"); an empty string if it is \
not about one country."""


def _vraagtekst(bewering: str, taal: str) -> str:
    return f"Claim ({taal or 'und'}): {' '.join((bewering or '').split())[:MAX_TEKENS]}"


def verkenverzoek(bewering: str, taal: str) -> dict:
    from doublecheck.modellen import MODELLEN

    schema = {"type": "object", "additionalProperties": False, "required": ["onderwerp", "breed", "land"],
              "properties": {"onderwerp": {"type": "string"}, "breed": {"type": "string", "enum": list(BREED)},
                             "land": {"type": "string"}}}
    # Haiku 5.5 denkt eerst, en dat telt mee in `max_tokens`
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 2000, "system": _VERKENNEN,
            "messages": [{"role": "user", "content": [{"type": "text", "text": _vraagtekst(bewering, taal)}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_verkenning(tekst: str | None) -> dict | None:
    """Het antwoord, opgeruimd. Een antwoord dat niet te lezen is of geen onderwerp noemt, telt nergens mee."""
    try:
        d = json.loads(tekst)  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    onderwerp = " ".join(str(d.get("onderwerp") or "").lower().split())[:60]
    if not onderwerp:
        return None
    land = " ".join(str(d.get("land") or "").split())
    return {"onderwerp": onderwerp, "breed": d.get("breed") if d.get("breed") in BREED else "other",
            "land": "" if land.lower() in ("none", "n/a", "unknown", "-") else land[:60]}


# --- de lijst en het indelen ----------------------------------------------------------------------------------------

def _naam_ok(naam) -> bool:
    """Een naam in elk van de vijf talen van B74; een nieuwe taal mag ontbreken en valt dan terug op het Engels (B79)."""
    return (isinstance(naam, dict) and all(isinstance(naam.get(t), str) and naam[t].strip() for t in BASIS)
            and set(naam) <= set(SITETALEN) and all(isinstance(v, str) and v.strip() for v in naam.values()))


def lees_lijst(pad: str | Path) -> list[dict]:
    """De lijst van thema's uit een bestand, of een weigering: 8 tot 15 thema's, elk met een nette sleutel, een naam
    in de vijf talen van de site, een omschrijving en hoogstens 8 onderdelen; nooit een derde niveau (B72)."""
    try:
        themas = json.loads(Path(pad).read_text(encoding="utf-8"))["themas"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as fout:
        raise Weigering(f"de lijst is niet te lezen: {fout}") from None
    if not isinstance(themas, list) or not 8 <= len(themas) <= 15:
        raise Weigering("een lijst heeft 8 tot 15 thema's")
    gezien: set[str] = set()
    for t in themas:
        if not isinstance(t, dict) or not _SLEUTEL.fullmatch(str(t.get("sleutel", ""))) or not _naam_ok(t.get("naam")):
            raise Weigering(f"een thema zonder nette sleutel of naam: {t!r:.80}")
        if not isinstance(t.get("omschrijving"), str) or not t["omschrijving"].strip():
            raise Weigering(f"thema {t['sleutel']} heeft geen omschrijving")
        onderdelen = t.get("onderdelen", [])
        if not isinstance(onderdelen, list) or len(onderdelen) > 8:
            raise Weigering(f"thema {t['sleutel']} heeft meer dan 8 onderdelen")
        for o in onderdelen:
            if (not isinstance(o, dict) or not _SLEUTEL.fullmatch(str(o.get("sleutel", ""))) or not _naam_ok(o.get("naam"))
                    or "onderdelen" in o):
                raise Weigering(f"een onderdeel van {t['sleutel']} deugt niet (geen derde niveau): {o!r:.80}")
        for sleutel in [t["sleutel"]] + [o["sleutel"] for o in onderdelen]:
            if sleutel in gezien or sleutel in ("anders", "geen"):
                raise Weigering(f"de sleutel {sleutel} komt twee keer voor of is gereserveerd")
            gezien.add(sleutel)
    return themas


def indeelverzoek(bewering: str, taal: str, lijst: list[dict]) -> dict:
    """De vraag bij welk thema van de lijst een bewering hoort. Het antwoord kan de lijst niet verlaten."""
    from doublecheck.modellen import MODELLEN

    regels = []
    for t in lijst:
        onderdelen = ", ".join(f'"{o["sleutel"]}" ({o["naam"]["en"]})' for o in t.get("onderdelen", []))
        regels.append(f'- "{t["sleutel"]}" ({t["naam"]["en"]}): {t["omschrijving"]}'
                      + (f" Parts: {onderdelen}." if onderdelen else ""))
    systeem = ("You file fact-checked claims under a fixed list of themes for a public archive. File the claim by what "
               "it is about; do not judge whether it is true.\n\nThe themes:\n" + "\n".join(regels) + "\n\n"
               '1. "thema": the key of the one theme that fits best, or "anders" if none of them fits.\n'
               '2. "onderdeel": the key of a part of that theme if one clearly fits, otherwise an empty string.\n'
               '3. "tweede": the key of a second theme only if the claim is just as much about that one, otherwise "geen".')
    sleutels = [t["sleutel"] for t in lijst]
    schema = {"type": "object", "additionalProperties": False, "required": ["thema", "onderdeel", "tweede"],
              "properties": {"thema": {"type": "string", "enum": sleutels + ["anders"]},
                             "onderdeel": {"type": "string"},
                             "tweede": {"type": "string", "enum": sleutels + ["geen"]}}}
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 2000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": _vraagtekst(bewering, taal)}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_indeling(tekst: str | None, lijst: list[dict]) -> dict | None:
    """Het antwoord binnen de lijst. Twijfel versoepelt nooit: een thema dat niet in de lijst staat is *anders*, een
    onderdeel dat niet bij het thema hoort vervalt, en een tweede thema dat hetzelfde is of niet bestaat ook."""
    try:
        d = json.loads(tekst)  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    per = {t["sleutel"]: {o["sleutel"] for o in t.get("onderdelen", [])} for t in lijst}
    thema = d.get("thema")
    if thema not in per:
        return {"thema": "anders", "onderdeel": "", "tweede": ""}
    onderdeel = d.get("onderdeel") if d.get("onderdeel") in per[thema] else ""
    tweede = d.get("tweede") if d.get("tweede") in per and d.get("tweede") != thema else ""
    return {"thema": thema, "onderdeel": onderdeel, "tweede": tweede}


# --- tien per vraag, met het land (thema-v2) ----------------------------------------------------------------------------

def land(waarde) -> str:
    """Een land is een code van twee letters uit de officiële lijst, of niets."""
    code = waarde.strip().upper() if isinstance(waarde, str) else ""
    return code if code in LANDEN else ""


def groepen(nummers: list, per: int = PER_VRAAG) -> list[list]:
    return [nummers[i:i + per] for i in range(0, len(nummers), per)]


def _regels(lijst: list[dict]) -> str:
    regels = []
    for t in lijst:
        delen = ", ".join(f'"{o["sleutel"]}" ({o["naam"]["en"]}' + (f': {o["hint"]}' if o.get("hint") else "") + ")"
                          for o in t.get("onderdelen", []))
        regels.append(f'- "{t["sleutel"]}" ({t["naam"]["en"]}): {t["omschrijving"]}' + (f" Parts: {delen}." if delen else ""))
    return "\n".join(regels)


def indeelverzoek_meer(claims: list[tuple[str, str]], lijst: list[dict]) -> dict:
    """Eén vraag over een rijtje beweringen (tekst, taal): bij welk thema hoort elk, en over welk land gaat ze. De
    lijst van thema's gaat zo één keer mee per rijtje in plaats van bij elke bewering."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You file fact-checked claims under a fixed list of themes for a public archive. File each claim by what it "
        "is about; do not judge whether it is true.\n\nThe themes:\n" + _regels(lijst) + "\n\n"
        "Answer for every numbered claim:\n"
        '- "nr": the number of the claim.\n'
        '- "thema": the key of the one theme that fits best, or "anders" if none of them fits.\n'
        '- "onderdeel": the key of a part of that theme only if the claim falls squarely under it (the country or the '
        "subject the part names); otherwise an empty string.\n"
        '- "tweede": a second theme only in the rare case that the claim is equally about two themes and one alone '
        'would mislead; otherwise "geen". Most claims have none.\n'
        '- "land": the country the claim is mostly about, as a two-letter ISO 3166-1 code in capitals ("IN", "US"); '
        "an empty string if it is not about one country.")
    sleutels = [t["sleutel"] for t in lijst]
    item = {"type": "object", "additionalProperties": False, "required": ["nr", "thema", "onderdeel", "tweede", "land"],
            "properties": {"nr": {"type": "integer"}, "thema": {"type": "string", "enum": sleutels + ["anders"]},
                           "onderdeel": {"type": "string"},
                           "tweede": {"type": "string", "enum": sleutels + ["geen"]}, "land": {"type": "string"}}}
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"],
              "properties": {"antwoorden": {"type": "array", "items": item}}}
    tekst = "\n".join(f"{i}. ({taal or 'und'}) {' '.join((bewering or '').split())[:500]}"
                      for i, (bewering, taal) in enumerate(claims, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 6000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_indeling_meer(tekst: str | None, lijst: list[dict], n: int) -> list[dict | None]:
    """De antwoorden op een rijtje van `n` beweringen, op nummer. Een nummer dat ontbreekt of twee keer voorkomt,
    telt niet: welke geldt, is dan niet te zeggen. Binnen een antwoord gelden de regels van `lees_indeling`."""
    uit: list[dict | None] = [None] * n
    try:
        antwoorden = json.loads(tekst)["antwoorden"]  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, KeyError):
        return uit
    if not isinstance(antwoorden, list):
        return uit
    geteld = Counter(a.get("nr") for a in antwoorden if isinstance(a, dict) and isinstance(a.get("nr"), int))
    for a in antwoorden:
        if not isinstance(a, dict) or not isinstance(a.get("nr"), int) or not 1 <= a["nr"] <= n or geteld[a["nr"]] != 1:
            continue
        gelezen = lees_indeling(json.dumps(a), lijst)
        if gelezen is not None:
            gelezen["land"] = land(a.get("land")) if gelezen["thema"] != "anders" else ""
            uit[a["nr"] - 1] = gelezen
    return uit


def overeenkomst(a: dict[str, dict | None], b: dict[str, dict | None]) -> dict:
    """Hoe vaak twee rondes hetzelfde zeggen over dezelfde bewering, bij de beweringen die in beide een antwoord hebben."""
    beide = [k for k in a if a.get(k) and b.get(k) and "onderdeel" in b[k]]
    return {"beide": len(beide), "zelfde_thema": sum(a[k]["thema"] == b[k]["thema"] for k in beide),
            "zelfde_onderdeel": sum((a[k]["thema"], a[k]["onderdeel"]) == (b[k]["thema"], b[k]["onderdeel"]) for k in beide),
            "zelfde_land": sum(a[k].get("land", "") == b[k].get("land", "") for k in beide)}


# --- de poort ---------------------------------------------------------------------------------------------------------

PO_LABELS = WORTEL / "docs" / "steekproeven" / "33.4-themas-po.json"
POORT_N, POORT_GOED = 200, 180
POORT_AANDEEL, POORT_ZEKERHEID = 0.90, 0.95   # de kortere weg: zoveel moet kloppen, met zoveel zekerheid (E9.S5 AC3)
PO_RONDE = "33-4"        # de naam van de nakijkronde in de database van de nakijkpagina


def draagt(goed: int, gelezen: int, aandeel: float = POORT_AANDEEL, zekerheid: float = POORT_ZEKERHEID) -> bool:
    """Volgt uit `goed` van `gelezen` met de gevraagde zekerheid dat minstens `aandeel` klopt? Exact geteld: de kans
    op zoveel goede of meer, als er in het echt precies `aandeel` zou kloppen, is hoogstens 1 - zekerheid. Dat geeft
    29 zonder fout, 46 met één fout, 61 met twee."""
    from math import comb

    if gelezen <= 0 or goed > gelezen:
        return False
    staart = sum(comb(gelezen, i) * aandeel ** i * (1 - aandeel) ** (gelezen - i) for i in range(goed, gelezen + 1))
    return staart <= 1 - zekerheid


def poort(pad: str | Path = PO_LABELS) -> tuple[bool, str]:
    """Mogen de thema's op de site? Alleen op de lezing van de PO zelf (SPECS E9.S5 AC3): (a) van 200 gelezen minstens
    180 goed, of (b) uit wat gelezen is volgt met 95% zekerheid dat minstens 90% klopt. Een kaart waar de PO twijfelde
    en niet koos, telt als gelezen en niet goed. De lezing van een model opent de poort niet."""
    try:
        d = json.loads(Path(pad).read_text(encoding="utf-8"))
        labels = [w for w in d["labels"].values() if w in ("goed", "fout", "twijfel")]
        door = str(d.get("gelezen_door", ""))
    except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return False, "de PO heeft nog niets gelezen"
    goed, gelezen = sum(w == "goed" for w in labels), len(labels)
    if not door.strip().upper().startswith("PO"):
        return False, f"gelezen door {door or 'onbekend'}, niet door de PO"
    if (gelezen >= POORT_N and goed >= POORT_GOED) or draagt(goed, gelezen):
        return True, f"{goed} van de {gelezen} goed"
    return False, (f"{goed} van de {gelezen} goed; dat is nog niet genoeg (van {POORT_N} gelezen {POORT_GOED} goed, of "
                   f"met {POORT_ZEKERHEID:.0%} zekerheid minstens {POORT_AANDEEL:.0%})")


# --- de nakijkronde van de PO --------------------------------------------------------------------------------------

PO_TALEN = ("en", "nl")  # wat de PO zonder vertaling leest
RTL = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})
PO_VELDEN = ("thema", "onderdeel", "tweede", "land")


def po_kaarten(paginas: dict[str, tuple[str, str]], indeling: dict[str, dict], vertalingen: dict[str, str],
               lijst: list[dict], landen: dict[str, dict], n: int = POORT_N, zaad: int = ZAAD + 7,
               zonder: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """De kaarten voor de PO: een willekeurige greep uit de beweringen die een thema van de lijst kregen, die zij kan
    lezen (Engels of Nederlands, of met de Engelse vertaling die er al ligt) en die in geen eerdere steekproef zaten.
    Per kaart de bewering en de indeling in Nederlandse namen; de sleutels blijven in `indeling`."""
    naam = {t["sleutel"]: t["naam"]["nl"] for t in lijst}
    deel = {(t["sleutel"], o["sleutel"]): o["naam"]["nl"] for t in lijst for o in t.get("onderdelen", [])}
    kan = [nr for nr, (_, taal) in paginas.items()
           if (indeling.get(nr) or {}).get("thema") in naam and (taal in PO_TALEN or vertalingen.get(nr))]
    kaarten = []
    for nr in steekproef(kan, n, zaad, zonder):
        tekst, taal = paginas[nr]
        g = indeling[nr]
        kaarten.append({
            "id": nr, "bewering": tekst, "taal": taal, "richting": "rtl" if taal.split("-")[0] in RTL else "ltr",
            "vertaling": "" if taal in PO_TALEN else vertalingen.get(nr, ""), "thema": naam[g["thema"]],
            "onderdeel": deel.get((g["thema"], g.get("onderdeel")), ""), "tweede": naam.get(g.get("tweede"), ""),
            "land": (landen.get(g.get("land")) or {}).get("nl", "")})
    return kaarten


def po_uitslag(kaarten: list[dict], keuzes: dict[str, dict]) -> dict:
    """Wat de keuzes van de PO betekenen. De poort telt het thema: *klopt* is goed, en *klopt niet* is alleen dan
    toch goed voor het thema als zij aanwees dat iets anders mis is. Zegt zij niet wat er mis is, dan telt het thema
    als fout. Onderdeel, tweede thema en land worden apart geteld, over de kaarten die er een hebben. Een notitie
    kan bij elke kaart (een grijs gebied) en verandert de telling niet; alleen een kaart met een notitie en zonder
    keuze krijgt het label *twijfel*, dat bij de poort als gelezen en niet goed telt."""
    labels, opmerkingen = {}, {}
    velden = {veld: {"met": 0, "fout": 0} for veld in PO_VELDEN}
    for k in kaarten:
        keuze = keuzes.get(k["id"]) or {}
        notitie = (keuze.get("opmerking") or "").strip()
        if notitie:                                          # een notitie blijft, ook zonder keuze
            opmerkingen[k["id"]] = notitie
        if keuze.get("oordeel") not in ("goed", "fout"):
            if notitie:                                      # wel gekeken, niet gekozen: de PO twijfelde
                labels[k["id"]] = "twijfel"
            continue
        mis = set(keuze.get("mis") or []) & set(PO_VELDEN) if keuze["oordeel"] == "fout" else set()
        if keuze["oordeel"] == "fout" and not mis:
            mis = {"thema"}
        labels[k["id"]] = "fout" if "thema" in mis else "goed"
        for veld in PO_VELDEN:
            if k.get(veld):
                velden[veld]["met"] += 1
                velden[veld]["fout"] += veld in mis
    return {"labels": labels, "velden": velden, "opmerkingen": opmerkingen}


def po_pagina(kaarten: list[dict]) -> str:
    """De nakijkpagina met de kaarten erin, als JSON in een scripttag; een `</` in een bewering sluit die tag nooit."""
    sjabloon = (Path(__file__).resolve().parent / "themas_pagina.html").read_text(encoding="utf-8")
    data = {"ronde": PO_RONDE, "nodig": POORT_GOED, "kaarten": kaarten}
    return sjabloon.replace("/*KAARTEN*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# --- tellen -------------------------------------------------------------------------------------------------------

def telling_verkenning(gelezen: list[dict | None]) -> dict:
    goed = [g for g in gelezen if g]
    per_veld: dict[str, Counter] = {}
    for g in goed:
        per_veld.setdefault(g["breed"], Counter())[g["onderwerp"]] += 1
    return {"gelezen": len(goed), "onleesbaar": len(gelezen) - len(goed),
            "breed": dict(Counter(g["breed"] for g in goed).most_common()),
            "onderwerpen": {veld: tel.most_common(25) for veld, tel in per_veld.items()},
            "landen": Counter(g["land"] for g in goed if g["land"]).most_common(40),
            "zonder_land": sum(not g["land"] for g in goed)}


def telling_toets(gelezen: list[dict | None]) -> dict:
    goed = [g for g in gelezen if g]
    binnen = [g for g in goed if g["thema"] != "anders"]
    onderdelen: dict[str, Counter] = {}
    for g in binnen:
        onderdelen.setdefault(g["thema"], Counter())[g["onderdeel"]] += 1
    return {"gelezen": len(goed), "onleesbaar": len(gelezen) - len(goed), "anders": len(goed) - len(binnen),
            "aandeel_anders": round((len(goed) - len(binnen)) / len(goed), 3) if goed else None,
            "themas": dict(Counter(g["thema"] for g in binnen).most_common()),
            "onderdelen": {t: dict(tel) for t, tel in onderdelen.items()},
            "met_tweede": sum(bool(g["tweede"]) for g in binnen)}


# --- bestanden en het model -----------------------------------------------------------------------------------------

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


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    return sum(r.get("kosten", 0.0) for naam in ("verkenning.jsonl", "toets.jsonl") for r in _jsonl(MAP / naam))


def _vraag(naam: str, n: int, zaad: int, maak, zonder_ook: tuple[str, ...] = ()) -> None:  # pragma: no cover - een model
    """Stelt de vraag `maak(bewering, taal)` over een steekproef van `n`, direct en tegelijk; hervatbaar."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    conn = _publicatie()
    paginas = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT nummer, bewering, taal FROM pagina")}
    eerder = {r["nummer"] for ander in zonder_ook for r in _jsonl(MAP / ander)}
    proef = steekproef(list(paginas), n, zaad, zonder=eerder)
    klaar = {r["nummer"] for r in _jsonl(MAP / naam)}
    werk = [nr for nr in proef if nr not in klaar]
    if not werk:
        print("niets te vragen")
        return
    binnen_grens(SCHATTING * len(werk), _uitgegeven())
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]

    def een(nr: str) -> None:
        if _uitgegeven() > GRENS:
            return
        bewering, taal = paginas[nr]
        try:
            msg = client.messages.create(**maak(bewering, taal))
            # direct, dus zonder batchkorting: twee keer de batchprijs
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            rij = {"nummer": nr, "taal": taal, "kosten": round(kosten, 6),
                   "antwoord": None if msg.stop_reason == "max_tokens" else
                   "".join(getattr(b, "text", "") or "" for b in msg.content)}
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot:
            _schrijf(MAP / naam, [rij])

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, werk))
    nu = _jsonl(MAP / naam)
    print(f"{len(nu)} beantwoord in {naam}; ${sum(r['kosten'] for r in nu):.3f} hier, samen ${_uitgegeven():.2f} "
          f"van ${GRENS:.2f}")


def _paginas() -> dict[str, tuple[str, str]]:  # pragma: no cover - een bestand
    return {r[0]: (r[1], r[2]) for r in _publicatie().execute("SELECT nummer, bewering, taal FROM pagina")}


def _draai_meer(naam: str, nummers: list[str], per: int, grens: float = GRENS) -> None:  # pragma: no cover - een model
    """Vraagt `thema-v2` over de beweringen, `per` per vraag, direct en tegelijk; per bewering een regel. Hervatbaar."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    lijst, paginas = lees_lijst(LIJST_PAD), _paginas()
    klaar = {r["nummer"] for r in _jsonl(MAP / naam)}
    werk = groepen([nr for nr in nummers if nr not in klaar], per)
    if not werk:
        return
    binnen_grens(SCHATTING * sum(len(g) for g in werk), _uitgegeven_alles(), grens)
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]

    def een(groep: list[str]) -> None:
        try:
            msg = client.messages.create(**indeelverzoek_meer([paginas[nr] for nr in groep], lijst))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        gelezen = lees_indeling_meer(tekst, lijst, len(groep))
        with slot:
            _schrijf(MAP / naam, [{"nummer": nr, "taal": paginas[nr][1], "uit": g, "kosten": round(kosten / len(groep), 7)}
                                  for nr, g in zip(groep, gelezen)])

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, werk))


def _uitgegeven_alles() -> float:  # pragma: no cover - bestanden
    return _uitgegeven() + sum(r.get("kosten", 0.0) for naam in ("hertoets-a.jsonl", "hertoets-a2.jsonl", "hertoets-b.jsonl")
                               for r in _jsonl(MAP / naam))


def _hertoets(n: int) -> None:  # pragma: no cover - een model
    eerder = {r["nummer"] for naam in ("verkenning.jsonl", "toets.jsonl") for r in _jsonl(MAP / naam)}
    proef = steekproef(list(_paginas()), n, ZAAD + 2, zonder=eerder)
    for naam, per in (("hertoets-a.jsonl", 1), ("hertoets-a2.jsonl", 1), ("hertoets-b.jsonl", PER_VRAAG)):
        _draai_meer(naam, proef, per)
        rijen = _jsonl(MAP / naam)
        print(f"{naam}: {len(rijen)} beweringen, ${sum(r['kosten'] for r in rijen):.3f} "
              f"(${sum(r['kosten'] for r in rijen) / max(1, len(rijen)):.6f} per bewering)")
    print(f"samen ${_uitgegeven_alles():.2f} van ${GRENS:.2f}")


def _vergelijk() -> None:  # pragma: no cover - bestanden
    a, a2, b = ({r["nummer"]: r["uit"] for r in _jsonl(MAP / naam)}
                for naam in ("hertoets-a.jsonl", "hertoets-a2.jsonl", "hertoets-b.jsonl"))
    for naam, x, y in (("A tegen A2 (twee keer één per vraag)", a, a2), ("A tegen B (tien per vraag)", a, b)):
        o = overeenkomst(x, y)
        print(f"{naam}: zelfde thema {o['zelfde_thema']} van {o['beide']} ({o['zelfde_thema'] / o['beide']:.1%}); "
              f"zelfde onderdeel {o['zelfde_onderdeel'] / o['beide']:.1%}; zelfde land {o['zelfde_land'] / o['beide']:.1%}")
    for naam, x in (("A", a), ("B", b)):
        goed = [g for g in x.values() if g]
        print(f"{naam}: {len(x)} gevraagd, zonder antwoord {len(x) - len(goed)} ({(len(x) - len(goed)) / len(x):.1%}); "
              f"buiten de lijst {sum(g['thema'] == 'anders' for g in goed)} "
              f"({sum(g['thema'] == 'anders' for g in goed) / len(goed):.1%}); een tweede thema "
              f"{sum(bool(g['tweede']) for g in goed)} ({sum(bool(g['tweede']) for g in goed) / len(goed):.1%}); "
              f"met een land {sum(bool(g.get('land')) for g in goed)}")
    print("thema's bij B:", dict(Counter(g["thema"] for g in b.values() if g).most_common()))


def _nakijken(deel: str, keuzes_pad: str | None) -> None:  # pragma: no cover - bestanden
    """`set` trekt de 200 kaarten en legt ze vast, `pagina` schrijft de nakijkpagina, `tellen` zet de keuzes van de PO
    (een bestand `{nummer: {oordeel, mis, opmerking}}`, door Claude uit de pagina gelezen) om in de labels van de poort."""
    from datetime import date

    kaarten_pad = MAP / "po-kaarten.json"
    if deel == "set":
        if kaarten_pad.exists():
            raise Weigering(f"de kaarten liggen al vast in {kaarten_pad}")
        from doublecheck import publiceren as pb

        lab = sqlite3.connect(f"{(WORTEL / 'doublecheck.db').as_uri()}?mode=ro", uri=True)
        vertalingen: dict[str, str] = {}
        for claim_id, tekst in lab.execute(
                "SELECT claim_id, text FROM claim_variant WHERE language = 'en' ORDER BY variant_id"):
            vertalingen.setdefault(pb.nummer(claim_id), tekst)
        indeling = {r["nummer"]: r["uit"] for r in _jsonl(MAP / "indeling.jsonl") if r["uit"]}
        eerder = {r["nummer"] for naam in ("verkenning.jsonl", "toets.jsonl", "hertoets-a.jsonl")
                  for r in _jsonl(MAP / naam)}
        paginas = _paginas()
        landen = json.loads((WORTEL / "content" / "landen.json").read_text(encoding="utf-8"))["landen"]
        kaarten = po_kaarten(paginas, indeling, vertalingen, lees_lijst(LIJST_PAD), landen, zonder=eerder)
        leesbaar = sum(taal in PO_TALEN or nr in vertalingen for nr, (_, taal) in paginas.items())
        kaarten_pad.write_text(json.dumps({
            "toelichting": (f"De {len(kaarten)} kaarten van de nakijkronde van de PO (PLAN #33.4): willekeurig, zaad "
                            f"{ZAAD + 7}, uit de beweringen met een thema die zij kan lezen ({leesbaar} van "
                            f"{len(paginas)}), zonder de {len(eerder)} uit eerdere steekproeven."),
            "kaarten": kaarten}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(kaarten)} kaarten in {kaarten_pad}; leesbaar voor de PO {leesbaar} van {len(paginas)}; "
              f"met een vertaling {sum(bool(k['vertaling']) for k in kaarten)}, met een onderdeel "
              f"{sum(bool(k['onderdeel']) for k in kaarten)}, een tweede thema {sum(bool(k['tweede']) for k in kaarten)}, "
              f"een land {sum(bool(k['land']) for k in kaarten)}")
        return
    kaarten = json.loads(kaarten_pad.read_text(encoding="utf-8"))["kaarten"]
    if deel == "pagina":
        (MAP / "nakijken.html").write_text(po_pagina(kaarten), encoding="utf-8")
        print(MAP / "nakijken.html")
        return
    if not keuzes_pad:
        raise Weigering("tellen vraagt --keuzes <json>")
    u = po_uitslag(kaarten, json.loads(Path(keuzes_pad).read_text(encoding="utf-8")))
    PO_LABELS.write_text(json.dumps({
        "toelichting": ("De lezing van de PO van 200 indelingen in thema's (PLAN #33.4, SPECS E9.S5 AC3), gekozen op de "
                        "nakijkpagina en door Claude teruggelezen. `labels` telt het thema; `velden` telt per veld "
                        "hoeveel gelezen kaarten het hadden en hoe vaak de PO het fout vond."),
        "gelezen_door": "PO", "datum": date.today().isoformat(), **u}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    goed = sum(w == "goed" for w in u["labels"].values())
    twijfel = sum(w == "twijfel" for w in u["labels"].values())
    print(f"{len(u['labels'])} van {len(kaarten)} gelezen; thema goed bij {goed}, twijfel zonder keuze bij {twijfel}; "
          f"{len(u['opmerkingen'])} notities")
    for veld, t in u["velden"].items():
        print(f"  {veld}: {t['fout']} fout van {t['met']}" + (f" ({t['fout'] / t['met']:.0%})" if t["met"] else ""))
    print("de poort:", poort()[1], "(open)" if poort()[0] else "(dicht)")


def nog_te_vragen(nummers: list[str], rijen: list[dict], kaart: list[dict], batches: list[dict]) -> list[str]:
    """Wat de volle ronde nog moet vragen: alles zonder thema dat niet in een batch zit die nog loopt. Een bewering
    waarvan het antwoord niet te lezen was, gaat dus opnieuw zodra haar batch binnen is."""
    klaar = {r["nummer"] for r in rijen if r["uit"]}
    lopend = {b["id"] for b in batches if b.get("werkelijk") is None}
    onderweg = {nr for k in kaart if k.get("batch") in lopend for nr in k["nummers"]}
    return sorted(set(nummers) - klaar - onderweg)


def _vol(stap: str, wacht: int) -> None:  # pragma: no cover - de Batch API
    """De volle ronde: alle pagina's van de publicatiedatabase, tien per vraag, via de Batch API (openbare beweringen)."""
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    lijst, paginas = lees_lijst(LIJST_PAD), _paginas()
    batches = _jsonl(MAP / "vol-batches.jsonl")

    def uitgegeven() -> float:
        return sum(b["werkelijk"] if b.get("werkelijk") is not None else b["schatting"] for b in batches)

    laad_sleutel()
    client = anthropic.Anthropic()
    if stap == "indienen":
        werk = groepen(nog_te_vragen(list(paginas), _jsonl(MAP / "indeling.jsonl"), _jsonl(MAP / "vol-kaart.jsonl"),
                                     batches), PER_VRAAG)
        if not werk:
            print("niets in te dienen")
            return
        schatting = round(SCHATTING_VOL * sum(len(g) for g in werk), 2)
        from doublecheck import routinegrens as rg

        if rg.uitgave():            # onder de routine per week telt haar grens, niet die voor altijd (PLAN #35.2)
            if not rg.past(schatting):
                raise Weigering(f"geschat ${schatting:.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
        else:
            binnen_grens(schatting, uitgegeven(), GRENS_VOL)
        for begin in range(0, len(werk), 5000):                     # een batch van hoogstens 5.000 vragen
            deel = werk[begin:begin + 5000]
            nr0 = len(_jsonl(MAP / "vol-kaart.jsonl"))
            batch = client.messages.batches.create(requests=[
                {"custom_id": f"th-{nr0 + i}", "params": indeelverzoek_meer([paginas[nr] for nr in g], lijst)}
                for i, g in enumerate(deel)])
            _schrijf(MAP / "vol-kaart.jsonl", [{"custom_id": f"th-{nr0 + i}", "nummers": g, "batch": batch.id}
                                              for i, g in enumerate(deel)])
            rij = rg.merk({"id": batch.id, "vragen": len(deel), "beweringen": sum(len(g) for g in deel),
                           "schatting": round(SCHATTING_VOL * sum(len(g) for g in deel), 2)})
            _schrijf(MAP / "vol-batches.jsonl", [rij])
            batches.append(rij)
            print(f"batch {batch.id}: {rij['vragen']} vragen, {rij['beweringen']} beweringen, schatting ${rij['schatting']}",
                  flush=True)
        print(f"samen ${uitgegeven():.2f} van ${GRENS_VOL:.2f}")
        return
    kaart = {k["custom_id"]: k for k in _jsonl(MAP / "vol-kaart.jsonl")}
    einde = time.time() + 60 * wacht
    while True:
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, regels, leeg = 0.0, [], 0
            for r in client.messages.batches.results(b["id"]):
                k = kaart.get(r.custom_id)
                if k is None:
                    continue
                if r.result.type != "succeeded":
                    gelezen = [None] * len(k["nummers"])
                else:
                    msg = r.result.message
                    werkelijk += kosten_batch(bc.gebruik_uit(msg), "haiku")
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(
                        getattr(x, "text", "") or "" for x in msg.content)
                    gelezen = lees_indeling_meer(tekst, lijst, len(k["nummers"]))
                leeg += sum(g is None for g in gelezen)
                regels += [{"nummer": nr, "uit": g, "versie": MEERVERSIE} for nr, g in zip(k["nummers"], gelezen)]
            _schrijf(MAP / "indeling.jsonl", regels)
            b["werkelijk"], b["zonder_antwoord"] = round(werkelijk, 4), leeg
            print(f"batch {b['id']}: {len(regels)} beweringen, {leeg} zonder antwoord, ${werkelijk:.2f}", flush=True)
        (MAP / "vol-batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        if not open_ or time.time() > einde:
            break
        time.sleep(60)
    goed = {r["nummer"] for r in _jsonl(MAP / "indeling.jsonl") if r["uit"]}
    print(f"{open_} batch(es) lopen nog; {len(goed)} van {len(paginas)} pagina's hebben een thema; "
          f"${uitgegeven():.2f} van ${GRENS_VOL:.2f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["verkennen", "tellen", "toetsen", "uitslag", "hertoets", "vergelijk", "vol",
                                    "nakijken"])
    p.add_argument("deel", nargs="?", choices=["indienen", "ophalen", "set", "pagina", "tellen"],
                   help="vol: indienen of ophalen; nakijken: set, pagina of tellen")
    p.add_argument("--keuzes", help="nakijken tellen: het bestand met de keuzes van de PO")
    p.add_argument("--n", type=int)
    p.add_argument("--lijst")
    p.add_argument("--wacht", type=int, default=0, help="vol ophalen: minuten wachten op de batch")
    a = p.parse_args()
    try:
        if a.stap == "hertoets":
            return _hertoets(a.n or 400)
        if a.stap == "vergelijk":
            return _vergelijk()
        if a.stap == "vol":
            return _vol(a.deel or "ophalen", a.wacht)
        if a.stap == "nakijken":
            return _nakijken(a.deel or "set", a.keuzes)
        if a.stap == "verkennen":
            _vraag("verkenning.jsonl", a.n or 800, ZAAD, verkenverzoek)
        elif a.stap == "tellen":
            t = telling_verkenning([lees_verkenning(r["antwoord"]) for r in _jsonl(MAP / "verkenning.jsonl")])
            (MAP / "verkenning-telling.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{t['gelezen']} gelezen, {t['onleesbaar']} onleesbaar; zonder land {t['zonder_land']}")
            for veld, aantal in t["breed"].items():
                top = ", ".join(f"{o} ({k})" for o, k in t["onderwerpen"][veld][:8])
                print(f"{aantal:4} {aantal / t['gelezen']:4.0%}  {veld}: {top}")
            print("landen:", ", ".join(f"{land} {k}" for land, k in t["landen"][:20]))
        elif a.stap == "toetsen":
            if not a.lijst:
                raise Weigering("toetsen vraagt --lijst <json>")
            lijst = lees_lijst(a.lijst)
            _vraag("toets.jsonl", a.n or 400, ZAAD + 1, lambda b, t: indeelverzoek(b, t, lijst),
                   zonder_ook=("verkenning.jsonl",))
        else:
            if not a.lijst:
                raise Weigering("uitslag vraagt --lijst <json>")
            lijst = lees_lijst(a.lijst)
            u = telling_toets([lees_indeling(r["antwoord"], lijst) for r in _jsonl(MAP / "toets.jsonl")])
            (MAP / "toets-uitslag.json").write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{u['gelezen']} gelezen, {u['onleesbaar']} onleesbaar; buiten de lijst {u['anders']} "
                  f"({u['aandeel_anders']:.1%}); met een tweede thema {u['met_tweede']}")
            for thema, aantal in u["themas"].items():
                delen = ", ".join(f"{o or '(geen)'} {k}" for o, k in sorted(u["onderdelen"][thema].items(),
                                                                         key=lambda x: -x[1]))
                print(f"{aantal:4} {aantal / u['gelezen']:4.0%}  {thema}: {delen}")
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
