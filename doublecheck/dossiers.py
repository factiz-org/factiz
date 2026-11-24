"""De dossiers van het platform (PLAN #33.6, SPECS E9.S7, B72): een verhaal of een netwerk, door een mens samengesteld.

Een dossier is een map `content/dossiers/<sleutel>/` met twee bestanden. `dossier.toml` schrijft een mens: de soort, de
status, het thema, de naam en één alinea in vijf talen, en de items op de tijdlijn die geen factcheck zijn.
`factchecks.json` schrijft de goedkeurstap: de factchecks die een mens goedkeurde. Een model stelt voor, een mens beslist
(AC3). Deze module leest en keurt die bestanden voor `publiceren`, en doet het voorstellen en het goedkeuren.

Niet te verwarren met `dossier.py`: dat is de proef van #32.70, waar een dossier nog een thema was.

    python -m doublecheck.dossiers kandidaten|voorstellen [--proef N]|toets|pagina|goedkeuren --keuzes <json> --dossier <sleutel>
    python -m doublecheck.dossiers versies|versiepagina|versies-goedkeuren --keuzes <json> --dossier <sleutel>

Een **versie** is hetzelfde bericht in andere woorden of een andere taal, binnen één verhaaldossier (AC8). Ook daar stelt
een model voor en keurt een mens goed, per versie; op de site staat ze onder *Komt ook voor als*.

Het voorstellen vraagt Haiku 5.5 direct, op openbare beweringen uit de uitgave; niet in het aanvraagpad. Werkbestanden in
`data/dossiers/<sleutel>/`, buiten git.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "content" / "dossiers"
WERK = WORTEL / "data" / "dossiers"
LEZINGEN = WORTEL / "docs" / "steekproeven"
from doublecheck.sitetalen import BASIS, SITETALEN  # noqa: E402  de talen van de site (B74, B79)
SOORTEN = ("verhaal", "netwerk")
STATUSSEN = ("concept", "akkoord")
ITEMSOORTEN = ("pers", "onderzoek", "besluit", "rapport")
NIVEAUS = ("waargenomen", "toegeschreven")
RTL = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})
VERSIE = "dossiervoorstel-v1"
VERSIEVRAAG = "dossierversie-v1"
MAX_PER_VERSIEVRAAG = 80     # alle factchecks van een dossier in één vraag, anders kan het model ze niet naast elkaar leggen
GRENS = 0.50             # dollar voor het voorstellen bij één dossier (PLAN #33.6)
SCHATTING = 0.00006      # per bewering, direct gevraagd met tien per vraag
PER_VRAAG = 10
DRADEN = 8
MAX_NAAM, MAX_ALINEA, MAX_TITEL = 90, 1200, 200
MAX_PER_JAAR = 25       # een dossier, na de strenge keuze: per jaar hoogstens zoveel beweringen (SPECS E9.S7 AC10)
ZELFDE = 0.80            # dezelfde bewering, met de vectoren van *Lijkt op* (#34.2p)
VERHAAL = 0.70           # hetzelfde verhaal: wat het archief erover checkte, ook in andere woorden
VARIANT = 0.75           # binnen een dossier: dezelfde bewering in andere woorden, één keer gekozen

_SLEUTEL = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_NUMMER = re.compile(r"[0-9a-f]{16}")
_DAG = re.compile(r"\d{4}-\d{2}-\d{2}")
_AKKOORD = re.compile(r'(\d{4}-\d{2}-\d{2}), PO: "[^"\n]{2,}"')
_STUUR = re.compile("[‪-‮⁦-⁩﻿\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_VELDEN = {"soort", "status", "akkoord", "thema", "onderdeel", "verwant", "naam", "inleiding", "nagelezen",
           "vastgesteld", "item", "voorstel"}
_VERPLICHT = ("soort", "status", "thema", "naam", "inleiding", "nagelezen")


class Weigering(Exception):
    """Het dossier mag zo niet in een uitgave, of de stap mag zo niet draaien."""


# --- het bestand lezen en keuren -----------------------------------------------------------------------------------

def _dag(waarde, wat: str) -> str:
    if not isinstance(waarde, str) or not _DAG.fullmatch(waarde):
        raise Weigering(f"{wat}: geen dag in de vorm 2024-03-05")
    try:
        date.fromisoformat(waarde)
    except ValueError:
        raise Weigering(f"{wat}: die dag bestaat niet") from None
    return waarde


def _webadres(waarde, wat: str) -> str:
    if not isinstance(waarde, str) or _STUUR.search(waarde) or any(t.isspace() for t in waarde):
        raise Weigering(f"{wat}: geen webadres")
    delen = urlsplit(waarde)
    if delen.scheme not in ("http", "https") or not delen.hostname or "." not in delen.hostname:
        raise Weigering(f"{wat}: geen webadres dat met https:// of http:// begint")
    return waarde


def _regel(waarde, wat: str, maximum: int, alinea: bool = False) -> str:
    """Eén regel platte tekst (of één alinea, waarin een regeleinde een spatie wordt); nooit leeg, nooit een stuurteken."""
    if not isinstance(waarde, str) or not waarde.strip():
        raise Weigering(f"{wat} ontbreekt of is leeg")
    if _STUUR.search(waarde) or (not alinea and ("\n" in waarde or "\r" in waarde)):
        raise Weigering(f"{wat}: een regeleinde of een stuurteken")
    if alinea and re.search(r"\n\s*\n", waarde.strip()):
        raise Weigering(f"{wat}: meer dan één alinea")
    tekst = " ".join(waarde.split())
    if len(tekst) > maximum:
        raise Weigering(f"{wat}: langer dan {maximum} tekens")
    return tekst


def _vijf(waarde, wat: str, maximum: int, alinea: bool = False) -> dict[str, str]:
    if not isinstance(waarde, dict):
        raise Weigering(f"{wat} ontbreekt of is geen tabel per taal")
    if set(waarde) - set(SITETALEN):
        raise Weigering(f"{wat}: een taal die de site niet heeft: {sorted(set(waarde) - set(SITETALEN))}")
    # de vijf van B74 moeten er zijn; een nieuwe taal (B79) mag ontbreken en valt dan terug op het Engels
    uit = {taal: _regel(waarde.get(taal), f"{wat}.{taal}", maximum, alinea) for taal in BASIS}
    return {taal: uit[taal] if taal in uit else _regel(waarde[taal], f"{wat}.{taal}", maximum, alinea) if taal in waarde
            else uit["en"] for taal in SITETALEN}


def _onbekend(tabel: dict, bekend: set[str], wat: str) -> None:
    vreemd = sorted(set(tabel) - bekend)
    if vreemd:
        raise Weigering(f"{wat}: onbekend veld {', '.join(vreemd)}")


def _factchecks(goed: dict | None, soort: str) -> tuple[list[dict], dict | None]:
    if goed is None:
        return [], None
    if not isinstance(goed, dict):
        raise Weigering("factchecks.json is geen tabel")
    _onbekend(goed, {"toelichting", "goedgekeurd_door", "datum", "factchecks"}, "factchecks.json")
    door = _regel(goed.get("goedgekeurd_door"), "factchecks.json: goedgekeurd_door", 60)
    dag = _dag(goed.get("datum"), "factchecks.json: datum")
    lijst = goed.get("factchecks")
    if not isinstance(lijst, list):
        raise Weigering("factchecks.json: factchecks is geen lijst")
    uit, gezien = [], set()
    for i, f in enumerate(lijst, 1):
        wat = f"factcheck {i}"
        if not isinstance(f, dict) or not isinstance(f.get("nummer"), str) or not _NUMMER.fullmatch(f["nummer"]):
            raise Weigering(f"{wat}: geen nummer van een factcheck (zestien tekens)")
        if f["nummer"] in gezien:
            raise Weigering(f"{wat}: nummer {f['nummer']} staat er twee keer in")
        gezien.add(f["nummer"])
        if soort == "netwerk":
            # B62: een factcheck staat alleen in een netwerkdossier met de bron die het verband legde, en het niveau
            _onbekend(f, {"nummer", "niveau", "bron", "url"}, wat)
            if f.get("niveau") not in NIVEAUS:
                raise Weigering(f"{wat}: niveau moet {' of '.join(NIVEAUS)} zijn")
            uit.append({"nummer": f["nummer"], "niveau": f["niveau"], "bron": _regel(f.get("bron"), f"{wat}: bron", 120),
                        "url": _webadres(f.get("url"), f"{wat}: url")})
        else:
            _onbekend(f, {"nummer", "versie"}, wat)
            regel = {"nummer": f["nummer"]}
            if "versie" in f:
                # hetzelfde bericht in andere woorden of een andere taal (AC8); alleen in een verhaaldossier
                v = f["versie"]
                if not isinstance(v, str) or not _SLEUTEL.fullmatch(v) or not 2 <= len(v) <= 40:
                    raise Weigering(f"{wat}: versie moet een sleutel van kleine letters, cijfers en streepjes zijn")
                regel["versie"] = v
            uit.append(regel)
    return uit, {"door": door, "datum": dag}


def keur(sleutel: str, ruw: dict, goed: dict | None) -> dict:
    """Eén dossier uit wat er in `dossier.toml` (`ruw`) en `factchecks.json` (`goed`) staat, of een weigering die zegt
    welk veld niet klopt. Wat hier doorheen komt, mag `publiceren` zonder verder kijken overnemen."""
    try:
        return _keur(sleutel, ruw, goed)
    except Weigering as fout:
        raise Weigering(f"{sleutel}: {fout}") from None


def _keur(sleutel: str, ruw: dict, goed: dict | None) -> dict:
    if not isinstance(sleutel, str) or not _SLEUTEL.fullmatch(sleutel) or not 2 <= len(sleutel) <= 40:
        raise Weigering("de sleutel (de naam van de map) moet kleine letters, cijfers en streepjes zijn, 2 tot 40 tekens")
    if not isinstance(ruw, dict):
        raise Weigering("dossier.toml is geen tabel")
    _onbekend(ruw, _VELDEN, "dossier.toml")
    for veld in _VERPLICHT:
        if veld not in ruw:
            raise Weigering(f"{veld} ontbreekt")
    soort, status = ruw["soort"], ruw["status"]
    if soort not in SOORTEN:
        raise Weigering(f"soort moet {' of '.join(SOORTEN)} zijn")
    if status not in STATUSSEN:
        raise Weigering(f"status moet {' of '.join(STATUSSEN)} zijn")
    akkoord = ruw.get("akkoord", "")
    if status == "akkoord":
        gevonden = _AKKOORD.fullmatch(akkoord) if isinstance(akkoord, str) else None
        if not gevonden:
            raise Weigering('akkoord: bij status akkoord horen de datum en de woorden van de PO (2026-11-12, PO: "…")')
        _dag(gevonden.group(1), "akkoord")
    elif akkoord:
        raise Weigering("akkoord: een concept draagt geen akkoord; zet de status op akkoord of haal de regel weg")
    nagelezen = ruw["nagelezen"]
    if not isinstance(nagelezen, dict) or not set(BASIS) <= set(nagelezen) <= set(SITETALEN) or not all(
            isinstance(w, bool) for w in nagelezen.values()):
        raise Weigering("nagelezen: per taal van de site true of false (las een moedertaallezer de tekst?)")
    thema = _regel(ruw["thema"], "thema", 40)
    onderdeel = _regel(ruw["onderdeel"], "onderdeel", 40) if ruw.get("onderdeel") else ""
    verwant = ruw.get("verwant", [])
    if not isinstance(verwant, list) or not all(isinstance(v, str) and _SLEUTEL.fullmatch(v) for v in verwant):
        raise Weigering("verwant: een lijst van sleutels van andere dossiers")
    vastgesteld = None
    if soort == "netwerk":
        v = ruw.get("vastgesteld")
        if not isinstance(v, dict):
            raise Weigering("vastgesteld ontbreekt: een netwerkdossier noemt wie het netwerk vaststelde, met link en datum")
        _onbekend(v, {"door", "url", "datum"}, "vastgesteld")
        vastgesteld = {"door": _regel(v.get("door"), "vastgesteld.door", 120),
                       "url": _webadres(v.get("url"), "vastgesteld.url"), "datum": _dag(v.get("datum"), "vastgesteld.datum")}
    elif "vastgesteld" in ruw:
        raise Weigering("vastgesteld: een verhaaldossier noemt geen vaststeller")
    items = []
    ruwe_items = ruw.get("item", [])
    if not isinstance(ruwe_items, list):
        raise Weigering("item: een lijst van items")
    for i, it in enumerate(ruwe_items, 1):
        wat = f"item {i}"
        if not isinstance(it, dict):
            raise Weigering(f"{wat}: geen tabel")
        _onbekend(it, {"soort", "datum", "bron", "url", "titel"}, wat)
        if it.get("soort") not in ITEMSOORTEN:
            raise Weigering(f"{wat}: soort moet een van {', '.join(ITEMSOORTEN)} zijn")
        items.append({"soort": it["soort"], "datum": _dag(it.get("datum"), f"{wat}: datum"),
                      "bron": _regel(it.get("bron"), f"{wat}: bron", 120), "url": _webadres(it.get("url"), f"{wat}: url"),
                      "titel": _vijf(it.get("titel"), f"{wat}: titel", MAX_TITEL)})
    voorstel = None
    if "voorstel" in ruw:
        v = ruw["voorstel"]
        if not isinstance(v, dict):
            raise Weigering("voorstel: geen tabel")
        _onbekend(v, {"woorden", "omschrijving"}, "voorstel")
        woorden = v.get("woorden", [])
        if not isinstance(woorden, list) or not all(isinstance(w, str) and w.strip() for w in woorden):
            raise Weigering("voorstel.woorden: een lijst van woorden")
        voorstel = {"woorden": [" ".join(w.split()) for w in woorden],
                    "omschrijving": _regel(v.get("omschrijving"), "voorstel.omschrijving", 1200, alinea=True)}
    factchecks, goedgekeurd = _factchecks(goed, soort)
    return {"sleutel": sleutel, "soort": soort, "status": status, "akkoord": akkoord if status == "akkoord" else "",
            "thema": thema, "onderdeel": onderdeel, "verwant": list(verwant),
            "naam": _vijf(ruw["naam"], "naam", MAX_NAAM), "inleiding": _vijf(ruw["inleiding"], "inleiding", MAX_ALINEA, True),
            "nagelezen": dict(nagelezen), "vastgesteld": vastgesteld, "items": items, "factchecks": factchecks,
            "goedgekeurd": goedgekeurd, "voorstel": voorstel}


def lees_dossier(map_: Path) -> dict:
    """Het dossier in deze map: `dossier.toml`, en `factchecks.json` als die er is."""
    map_ = Path(map_)
    sleutel = map_.name
    try:
        ruw = tomllib.loads((map_ / "dossier.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Weigering(f"{sleutel}: geen dossier.toml in de map") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as fout:
        raise Weigering(f"{sleutel}: dossier.toml is niet te lezen ({fout})") from None
    goed = None
    if (map_ / "factchecks.json").exists():
        try:
            goed = json.loads((map_ / "factchecks.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as fout:
            raise Weigering(f"{sleutel}: factchecks.json is niet te lezen ({fout})") from None
    return keur(sleutel, ruw, goed)


def lees_alle(map_: Path = MAP, themas: list[dict] | None = None) -> list[dict]:
    """Alle dossiers, op sleutel, na de toetsen die over meer dan één dossier gaan: een verwant dossier bestaat, een
    thema en een onderdeel staan in de lijst (als die meegegeven is), en een factcheck staat in hoogstens één
    verhaaldossier (B72)."""
    map_ = Path(map_)
    if not map_.is_dir():
        return []
    dossiers = [lees_dossier(m) for m in sorted(map_.iterdir()) if m.is_dir() and not m.name.startswith((".", "_"))]
    sleutels = {d["sleutel"] for d in dossiers}
    delen = None if themas is None else {t["sleutel"]: {o["sleutel"] for o in t.get("onderdelen", [])} for t in themas}
    verhaal_van: dict[str, str] = {}
    for d in dossiers:
        for v in d["verwant"]:
            if v == d["sleutel"]:
                raise Weigering(f"{d['sleutel']}: verwant: een dossier verwijst niet naar zichzelf")
            if v not in sleutels:
                raise Weigering(f"{d['sleutel']}: verwant: het dossier {v} bestaat niet")
        if delen is not None:
            if d["thema"] not in delen:
                raise Weigering(f"{d['sleutel']}: het thema {d['thema']} staat niet in de lijst van thema's")
            if d["onderdeel"] and d["onderdeel"] not in delen[d["thema"]]:
                raise Weigering(f"{d['sleutel']}: het onderdeel {d['onderdeel']} hoort niet bij het thema {d['thema']}")
        if d["soort"] == "verhaal":
            for f in d["factchecks"]:
                if f["nummer"] in verhaal_van:
                    raise Weigering(f"factcheck {f['nummer']} staat in twee verhaaldossiers: "
                                    f"{verhaal_van[f['nummer']]} en {d['sleutel']}")
                verhaal_van[f["nummer"]] = d["sleutel"]
    return dossiers


# --- voorstellen -----------------------------------------------------------------------------------------------------

def open_uitgave(pad: str | Path | None = None) -> sqlite3.Connection:
    """De publicatiedatabase, alleen lezen: de nieuwste, of het bestand dat genoemd is."""
    if pad is None:
        kandidaten_ = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
        if not kandidaten_:
            raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
        pad = kandidaten_[-1]
    conn = sqlite3.connect(f"{Path(pad).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def kandidaten(pub: sqlite3.Connection, woorden: list[str]) -> list[str]:
    """De nummers van elke pagina waarin een van de woorden staat: in de bewering of een vertaling (het register op
    woorden), of als deel van een woord en in een schrift zonder spaties (het register op drietallen). Een woord is een
    letterlijke zin voor het register, nooit een opdracht; een woord korter dan drie tekens doet niet mee."""
    gevonden: set[str] = set()
    for woord in woorden:
        kaal = " ".join(str(woord).replace('"', " ").split())
        if len(kaal) < 3:
            continue
        for tabel in ("zoek", "zoek3"):
            try:
                gevonden.update(r[0] for r in pub.execute(f"SELECT nummer FROM {tabel} WHERE {tabel} MATCH ?", (f'"{kaal}"',)))
            except sqlite3.OperationalError:
                continue                       # een woord dat het register niet kan lezen, vindt niets
    return sorted(gevonden)


_SYSTEEM = """You help an editor collect fact-checked claims into a dossier for a public archive. A dossier holds one \
recurring story: the same story told again and again in other words, about other objects, in other languages.

The dossier: {naam}
What belongs in it: {omschrijving}

You get a numbered list of claims that fact-checkers examined. For every claim, say whether it tells this story. Do not \
judge whether a claim is true or false; only whether it belongs in this dossier.

Answer for every numbered claim:
- "nr": the number of the claim.
- "oordeel": "ja" if the claim is a version of this story; "nee" if it is about something else, also when it is about \
the same person or the same country; "twijfel" if it is close to the story but you cannot tell from the claim alone.
- "reden": the reason in at most eight English words."""

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {"antwoorden": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["nr", "oordeel", "reden"],
                               "properties": {"nr": {"type": "integer"},
                                              "oordeel": {"type": "string", "enum": ["ja", "nee", "twijfel"]},
                                              "reden": {"type": "string"}}}}}}


def voorstelverzoek(dossier: dict, claims: list[tuple[str, str]]) -> dict:
    """Eén vraag over een rijtje beweringen (tekst, taal): vertelt elk het verhaal van dit dossier? Alleen voor een
    verhaaldossier: in een netwerkdossier staat alleen wat een bron met naam aan het netwerk toeschreef (B62), en dat
    kan een model niet uit de bewering lezen."""
    from doublecheck.modellen import MODELLEN

    if dossier["soort"] != "verhaal":
        raise Weigering(f"{dossier['sleutel']}: een netwerkdossier krijgt geen voorstel van een model (B62)")
    if not dossier.get("voorstel"):
        raise Weigering(f"{dossier['sleutel']}: zonder [voorstel] met woorden en een omschrijving valt er niets voor te stellen")
    tekst = "\n".join(f"{i}. ({taal or 'und'}) {' '.join((bewering or '').split())[:500]}"
                      for i, (bewering, taal) in enumerate(claims, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 4000,
            "system": _SYSTEEM.format(naam=dossier["naam"]["en"], omschrijving=dossier["voorstel"]["omschrijving"]),
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees_voorstel(tekst: str | None, n: int) -> list[dict | None]:
    """De antwoorden op een rijtje van `n` beweringen, op nummer. Een nummer dat ontbreekt, buiten het rijtje valt of
    twee keer voorkomt, telt niet; een oordeel buiten de drie ook niet."""
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
        if a.get("oordeel") in ("ja", "nee", "twijfel"):
            reden = a.get("reden") if isinstance(a.get("reden"), str) else ""
            uit[a["nr"] - 1] = {"oordeel": a["oordeel"], "reden": " ".join(_STUUR.sub("", reden).split())[:120]}
    return uit


_VERSIESYSTEEM = """You help an editor of a public archive of fact-checked claims. All claims below belong to one dossier: \
{naam}. Many of them are the same message in other words or in another language: the same alleged purchase of the same \
object, the same alleged document, the same alleged fact. Find those groups. Do not judge whether a claim is true.

Answer for every numbered claim:
- "nr": the number of the claim.
- "versie": a short English name of two to four words for the specific message this claim tells, naming the object or \
the fact ("Highgrove House purchase", "two yachts purchase"). Give exactly the same name to every claim that tells the \
same message, in whatever language. Two claims about different objects are different messages, also when they are of \
the same kind. Use an empty string if no other claim in the list tells the same message."""

_VERSIESCHEMA = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {"antwoorden": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["nr", "versie"],
                               "properties": {"nr": {"type": "integer"}, "versie": {"type": "string"}}}}}}


def versieverzoek(dossier: dict, claims: list[tuple[str, str]]) -> dict:
    """Eén vraag over alle factchecks van een verhaaldossier (tekst, taal): welke zijn hetzelfde bericht? Het model
    geeft elke bewering een korte Engelse naam; dezelfde naam is dezelfde versie."""
    from doublecheck.modellen import MODELLEN

    if dossier["soort"] != "verhaal":
        raise Weigering(f"{dossier['sleutel']}: een netwerkdossier heeft geen versies (AC8)")
    tekst = "\n".join(f"{i}. ({taal or 'und'}) {' '.join((bewering or '').split())[:500]}"
                      for i, (bewering, taal) in enumerate(claims, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 6000, "system": _VERSIESYSTEEM.format(naam=dossier["naam"]["en"]),
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _VERSIESCHEMA}}}


def _versiesleutel(naam) -> str:
    """De naam die het model gaf als sleutel: kleine letters, cijfers en streepjes; een naam zonder Latijnse letter
    is geen sleutel."""
    kaal = re.sub(r"[^a-z0-9]+", "-", naam.lower()).strip("-") if isinstance(naam, str) else ""
    if kaal[:1].isdigit():
        kaal = "v-" + kaal
    kaal = kaal[:40].strip("-")
    return kaal if len(kaal) >= 2 and _SLEUTEL.fullmatch(kaal) else ""


def lees_versies(tekst: str | None, n: int) -> list[str]:
    """Per bewering de sleutel van haar versie, of niets. Een nummer dat ontbreekt of twee keer voorkomt telt niet, en
    een versie waar maar één bewering in zit, is geen versie."""
    uit = [""] * n
    try:
        antwoorden = json.loads(tekst)["antwoorden"]  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, KeyError):
        return uit
    if not isinstance(antwoorden, list):
        return uit
    geteld = Counter(a.get("nr") for a in antwoorden if isinstance(a, dict) and isinstance(a.get("nr"), int))
    for a in antwoorden:
        if isinstance(a, dict) and isinstance(a.get("nr"), int) and 1 <= a["nr"] <= n and geteld[a["nr"]] == 1:
            uit[a["nr"] - 1] = _versiesleutel(a.get("versie"))
    leden = Counter(v for v in uit if v)
    return [v if leden[v] >= 2 else "" for v in uit]


def delen(x, nummers: list[str], maximum: int = MAX_PER_VERSIEVRAAG) -> list[list[str]]:
    """Een groot dossier in stukken van hoogstens `maximum` voor de versievraag, zodat wat op elkaar lijkt in één vraag
    komt: steeds in twee groepen rond twee middelpunten (begonnen bij de twee uitersten langs de richting waarin de
    beweringen het meest verschillen), tot elk stuk klein genoeg is. Vast: dezelfde vectoren geven dezelfde stukken,
    en binnen een stuk blijft de volgorde van `nummers`."""
    import numpy as np

    if len(nummers) <= maximum:
        return [list(nummers)]
    x = np.asarray(x, dtype=np.float64)
    y = x - x.mean(axis=0)
    as_ = np.linalg.svd(y, full_matrices=False)[2][0]
    as_ = as_ if as_[np.argmax(np.abs(as_))] >= 0 else -as_      # het teken vast, anders wisselt de volgorde
    proj = y @ as_
    midden = np.stack([x[np.argmin(proj)], x[np.argmax(proj)]])
    rechts = np.zeros(len(nummers), dtype=bool)
    for _ in range(50):
        nieuw = ((x - midden[1]) ** 2).sum(axis=1) < ((x - midden[0]) ** 2).sum(axis=1)
        if nieuw.all() or not nieuw.any() or (nieuw == rechts).all():
            rechts = nieuw
            break
        rechts = nieuw
        midden = np.stack([x[~rechts].mean(axis=0), x[rechts].mean(axis=0)])
    if rechts.all() or not rechts.any():                         # alles gelijk: dan doormidden langs de as
        rechts = np.zeros(len(nummers), dtype=bool)
        rechts[np.argsort(proj, kind="stable")[len(nummers) // 2:]] = True
    links_i, rechts_i = np.flatnonzero(~rechts), np.flatnonzero(rechts)
    return (delen(x[links_i], [nummers[i] for i in links_i], maximum)
            + delen(x[rechts_i], [nummers[i] for i in rechts_i], maximum))


def versiegroepen(dossier: dict, voorstel: dict[str, str], paginas: dict[str, dict]) -> list[dict]:
    """De voorgestelde versies voor de PO: alleen goedgekeurde factchecks, en alleen een versie met minstens twee
    daarvan. Binnen een versie op de datum van de eerste check; de versies zelf ook."""
    per: dict[str, list[str]] = {}
    for f in dossier["factchecks"]:
        sleutel = voorstel.get(f["nummer"]) or ""
        if sleutel and f["nummer"] in paginas:
            per.setdefault(sleutel, []).append(f["nummer"])
    groepen = []
    for sleutel, nummers in per.items():
        if len(nummers) < 2:
            continue
        nummers.sort(key=lambda nr: (paginas[nr]["eerste_datum"] or "9999", nr))
        groepen.append({"sleutel": sleutel, "kaarten": [{
            "id": nr, "bewering": paginas[nr]["bewering"], "taal": paginas[nr]["taal"],
            "richting": "rtl" if (paginas[nr]["taal"] or "").split("-")[0] in RTL else "ltr",
            "vertaling": paginas[nr]["vertaling"], "label": paginas[nr]["label"], "datum": paginas[nr]["eerste_datum"],
            "redacties": paginas[nr]["redacties"], "url": paginas[nr]["url"]} for nr in nummers]})
    groepen.sort(key=lambda g: (g["kaarten"][0]["datum"] or "9999", g["sleutel"]))
    return groepen


def versies_goedkeuren(dossier: dict, groepen: list[dict], keuzes: dict[str, dict], datum: str,
                       door: str = "PO") -> tuple[dict, dict]:
    """Wat de keuzes van de PO over de versies betekenen: de inhoud van `factchecks.json` en haar lezing per versie.
    Een factcheck krijgt haar versie alleen als de PO de versie goedkeurde en de kaart er niet uit haalde; een versie
    waar zo minder dan twee factchecks in blijven, vervalt. Een versie die zij niet las, blijft zoals ze was."""
    if dossier["soort"] != "verhaal":
        raise Weigering(f"{dossier['sleutel']}: een netwerkdossier heeft geen versies (AC8)")
    huidig = {f["nummer"]: f.get("versie", "") for f in dossier["factchecks"]}
    lezing: dict[str, dict] = {}
    for g in groepen:
        keuze = keuzes.get(g["sleutel"]) or {}
        if keuze.get("oordeel") not in ("ja", "nee"):
            continue
        kaarten_ = [k["id"] for k in g["kaarten"] if k["id"] in huidig]
        zonder = [nr for nr in kaarten_ if nr in set(keuze.get("zonder") or [])]
        leden = [nr for nr in kaarten_ if nr not in zonder] if keuze["oordeel"] == "ja" else []
        if len(leden) < 2:
            leden = []
        for nr, versie in huidig.items():
            if versie == g["sleutel"]:
                huidig[nr] = ""
        for nr in leden:
            huidig[nr] = g["sleutel"]
        lezing[g["sleutel"]] = {"oordeel": keuze["oordeel"], "leden": leden, "zonder": zonder,
                                "opmerking": " ".join(_STUUR.sub("", keuze.get("opmerking") or "").split())}
    return ({"goedgekeurd_door": door, "datum": datum,
             "factchecks": [{"nummer": nr, **({"versie": v} if v else {})} for nr, v in huidig.items()]}, lezing)


def versiepagina(dossier: dict, groepen: list[dict]) -> str:
    """De leespagina voor de versies, met de groepen erin als JSON in een scripttag."""
    sjabloon = (Path(__file__).resolve().parent / "dossiers_versies.html").read_text(encoding="utf-8")
    sjabloon = sjabloon.replace("<title>Dossier versies</title>", f"<title>Dossier {dossier['sleutel']} versies</title>")
    data = {"dossier": dossier["sleutel"], "naam": dossier["naam"]["nl"], "groepen": groepen}
    return sjabloon.replace("/*GROEPEN*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def binnen_grens(geschat: float, uitgegeven: float, grens: float = GRENS) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"boven de grens van ${grens:.2f}: al ${uitgegeven:.2f} uitgegeven, deze stap kost ~${geschat:.2f}")


# --- goedkeuren ------------------------------------------------------------------------------------------------------

def inkorten(kandidaten: list[dict], per_jaar: int = MAX_PER_JAAR) -> list[str]:
    """De factchecks van een dossier na een strenge keuze (SPECS E9.S7 AC10, PO 2026-11-19: "alleen de grootste
    misinformatie die het vaakst voorbij komt", "een max aantal per jaar is beter"): de eigen checks van Factiz altijd,
    dan per bewering (`groep`: factchecks van het dossier die op elkaar lijken) één factcheck, de beweringen die het
    archief door de meeste redacties gecheckt heeft voorop, dan op het aantal checks; daarna op hoe vaak het archief
    hetzelfde verhaal checkte (`ruim_redacties`, `ruim_checks`: wat er vanaf `VERHAAL` op lijkt) en op de talen. Binnen
    een bewering die met de meeste eigen redacties. Hoogstens `per_jaar` per jaar van de eerste check (`jaar`; zonder
    datum telt als een eigen jaar)."""
    eigen = [k["nummer"] for k in kandidaten if k.get("eigen")]
    groepen: dict[str, list[dict]] = {}
    for k in kandidaten:
        if not k.get("eigen"):
            groepen.setdefault(k["groep"], []).append(k)
    sterkte = lambda leden: tuple(max(k.get(veld, 0) for k in leden)
                                  for veld in ("redacties", "checks", "ruim_redacties", "ruim_checks", "talen"))
    orde = sorted(groepen.values(), key=lambda leden: (*(-x for x in sterkte(leden)), min(k["nummer"] for k in leden)))
    gekozen, per = [], Counter()
    for leden in orde:
        beste = min(leden, key=lambda k: (-k.get("eigen_redacties", 0), k["nummer"]))
        jaar = beste.get("jaar", "")
        if per[jaar] < per_jaar:
            per[jaar] += 1
            gekozen.append(beste["nummer"])
    return eigen + gekozen


def kaarten(voorstellen: dict[str, dict], paginas: dict[str, dict], gelezen: set[str] | frozenset[str]) -> list[dict]:
    """De kaarten voor de PO: wat het model *ja* of *twijfel* noemde, nog in de uitgave staat en nog niet gelezen is.
    Eerst de ja's, dan de twijfel; daarbinnen op de datum van de eerste check, zodat hetzelfde verhaal in een andere
    taal er vlak bij staat."""
    rijen = [(v["oordeel"] != "ja", paginas[nr]["eerste_datum"] or "9999", nr) for nr, v in voorstellen.items()
             if v and v["oordeel"] in ("ja", "twijfel") and nr in paginas and nr not in gelezen]
    uit = []
    for _, _, nr in sorted(rijen):
        p, v = paginas[nr], voorstellen[nr]
        uit.append({"id": nr, "bewering": p["bewering"], "taal": p["taal"],
                    "richting": "rtl" if (p["taal"] or "").split("-")[0] in RTL else "ltr", "vertaling": p["vertaling"],
                    "label": p["label"], "datum": p["eerste_datum"], "redacties": p["redacties"], "url": p["url"],
                    "voorstel": v["oordeel"], "reden": v["reden"]})
    return uit


def elders(dossiers: list[dict], sleutel: str) -> dict[str, str]:
    """Per factcheck het andere verhaaldossier waarin ze al goedgekeurd staat. Een factcheck staat in hoogstens één
    verhaaldossier (AC6), dus zo'n factcheck hoort niet meer op de kaarten van `sleutel`; een netwerk telt niet mee."""
    return {f["nummer"]: d["sleutel"] for d in dossiers if d["soort"] == "verhaal" and d["sleutel"] != sleutel
            for f in d["factchecks"]}


def goedkeuring(dossier: dict, kaarten_: list[dict], keuzes: dict[str, dict], datum: str, door: str = "PO",
                eerder: dict[str, str] | None = None) -> tuple[dict, dict]:
    """Wat de keuzes van de PO betekenen: de inhoud van `factchecks.json` (wat al goedgekeurd was en nu geen nee kreeg,
    plus wat nu ja kreeg) en haar hele lezing (ja, nee, en twijfel waar zij alleen een notitie schreef). Alleen een
    kaart die zij zag telt; een nummer van buiten de kaarten doet niets."""
    if dossier["soort"] != "verhaal":
        raise Weigering(f"{dossier['sleutel']}: een netwerkdossier wordt met de hand gevuld, met de bron per factcheck (B62)")
    labels, opmerkingen = dict(eerder or {}), {}
    for k in kaarten_:
        keuze = keuzes.get(k["id"]) or {}
        notitie = " ".join(_STUUR.sub("", keuze.get("opmerking") or "").split())
        if notitie:
            opmerkingen[k["id"]] = notitie
        if keuze.get("oordeel") in ("ja", "nee"):
            labels[k["id"]] = keuze["oordeel"]
        elif notitie:
            labels[k["id"]] = "twijfel"                     # wel gekeken, niet gekozen
    nummers = [f["nummer"] for f in dossier["factchecks"] if labels.get(f["nummer"], "ja") == "ja"]
    nummers += [k["id"] for k in kaarten_ if labels.get(k["id"]) == "ja" and k["id"] not in nummers]
    # wat blijft, houdt zijn versie; een versie die zo één factcheck overhoudt, is geen versie meer (AC8)
    versie = {f["nummer"]: f["versie"] for f in dossier["factchecks"] if f.get("versie")}
    over = Counter(versie[nr] for nr in nummers if nr in versie)
    return ({"goedgekeurd_door": door, "datum": datum,
             "factchecks": [{"nummer": nr, **({"versie": versie[nr]} if over.get(versie.get(nr), 0) >= 2 else {})}
                            for nr in nummers]},
            {"gelezen_door": door, "datum": datum, "labels": labels, "opmerkingen": opmerkingen})


def voeg_lezing_samen(oud: dict, nieuw: dict) -> dict:
    """Een nieuwe lezing bij de oude: de nieuwste keuze en notitie per factcheck gelden, een notitie zonder nieuwe
    blijft, en wat de oude lezing verder droeg (de versies) blijft staan."""
    return {**oud, **nieuw, "opmerkingen": {**oud.get("opmerkingen", {}), **nieuw.get("opmerkingen", {})}}


def po_pagina(dossier: dict, kaarten_: list[dict]) -> str:
    """De leespagina met de kaarten erin, als JSON in een scripttag; een `</` in een bewering sluit die tag nooit."""
    sjabloon = (Path(__file__).resolve().parent / "dossiers_pagina.html").read_text(encoding="utf-8")
    data = {"dossier": dossier["sleutel"], "naam": dossier["naam"]["nl"],
            "omschrijving": dossier["inleiding"]["nl"], "kaarten": kaarten_}
    # de naam van de pagina noemt het dossier: zo is ze tussen de andere leespagina's terug te vinden
    sjabloon = sjabloon.replace("<title>Dossier nakijken</title>", f"<title>Dossier {dossier['sleutel']} nakijken</title>")
    return sjabloon.replace("/*KAARTEN*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# --- Claude leest, de PO beslist over de twijfel (SPECS E9.S7 AC3, PO 2026-11-12) ----------------------------------------

def twijfelgroepen(kaarten_: list[dict], claude: dict) -> list[dict]:
    """De groepen voor de PO uit de lezing van Claude: elke kaart die hij *twijfel* noemde staat in precies één groep,
    en een groep houdt alleen zulke kaarten. Per groep de vraag, de uitleg, of de PO per kaart kiest, en de kaarten
    zelf met de reden van Claude erbij."""
    bekend = {k["id"]: k for k in kaarten_}
    labels, notities = claude.get("labels", {}), claude.get("notities", {})
    twijfel = {nr for nr, oordeel in labels.items() if oordeel == "twijfel"}
    sleutels = Counter(g.get("sleutel") for g in claude.get("groepen", []))
    if dubbel := sorted(s for s, n in sleutels.items() if n > 1 or not _SLEUTEL.fullmatch(s or "")):
        raise Weigering(f"een groep heeft geen eigen sleutel: {', '.join(map(str, dubbel))}")
    gezien = Counter(nr for g in claude.get("groepen", []) for nr in g["kaarten"])
    if twee := sorted(nr for nr, n in gezien.items() if n > 1):
        raise Weigering(f"in twee groepen: {', '.join(twee)}")
    if los := sorted(twijfel - set(gezien)):
        raise Weigering(f"twijfel zonder groep: {', '.join(los)}")
    if vreemd := sorted(set(gezien) - twijfel):
        raise Weigering(f"in een groep maar geen twijfel van Claude: {', '.join(vreemd)}")
    if weg := sorted(set(gezien) - set(bekend)):
        raise Weigering(f"geen kaart van dit dossier: {', '.join(weg)}")
    return [{"sleutel": g["sleutel"], "vraag": _regel(g.get("vraag"), f"groep {g['sleutel']}: vraag", 240),
             "uitleg": _regel(g.get("uitleg"), f"groep {g['sleutel']}: uitleg", 900, alinea=True),
             "per_kaart": bool(g.get("per_kaart")),
             "kaarten": [{**bekend[nr], "notitie": notities.get(nr, "")} for nr in g["kaarten"]]}
            for g in claude.get("groepen", [])]


def keuzes_uit_groepen(groepen: list[dict], groepkeuzes: dict, kaartkeuzes: dict) -> dict[str, dict]:
    """De keuzes per kaart uit de keuzes per groep: een eigen keuze bij een kaart gaat voor, anders geldt die van de
    groep, behalve in een groep waar de PO per kaart kiest. De notitie bij de groep gaat mee naar elke kaart erin.
    Een kaart van buiten de groepen doet niets."""
    uit = {}
    for g in groepen:
        groep = (groepkeuzes or {}).get(g["sleutel"]) or {}
        for k in g["kaarten"]:
            eigen = (kaartkeuzes or {}).get(k["id"]) or {}
            oordeel = eigen.get("oordeel") if eigen.get("oordeel") in ("ja", "nee") else None
            if oordeel is None and not g["per_kaart"] and groep.get("oordeel") in ("ja", "nee"):
                oordeel = groep["oordeel"]
            opmerking = " ".join(_STUUR.sub("", eigen.get("opmerking") or groep.get("opmerking") or "").split())
            if oordeel or opmerking:
                uit[k["id"]] = {"oordeel": oordeel, "opmerking": opmerking}
    return uit


def goedkeuring_met_claude(dossier: dict, kaarten_: list[dict], claude: dict, groepkeuzes: dict, kaartkeuzes: dict,
                           datum: str, akkoord: str, eerder: dict[str, str] | None = None) -> tuple[dict, dict]:
    """Als `goedkeuring`, maar Claude las elke kaart en de PO besliste over zijn twijfel: zijn ja en nee gelden, haar
    keuzes gaan erover. De lezing zegt welke kaarten zij besliste, wat Claude bij elke kaart noteerde, de groepen met
    haar keuze, en haar akkoord op deze werkwijze met haar woorden en de datum; zonder dat akkoord niets."""
    if not _AKKOORD.fullmatch(akkoord or ""):
        raise Weigering('het akkoord van de PO hoort erbij, als 2026-11-12, PO: "haar woorden"')
    groepen = twijfelgroepen(kaarten_, claude)
    keuzes = keuzes_uit_groepen(groepen, groepkeuzes, kaartkeuzes)
    goed, lezing = goedkeuring(dossier, kaarten_, keuzes, datum, door="Claude en PO",
                               eerder={**(eerder or {}), **claude.get("labels", {})})

    def keuze(g: dict) -> str | None:
        oordeel = ((groepkeuzes or {}).get(g["sleutel"]) or {}).get("oordeel")
        return oordeel if oordeel in ("ja", "nee") and not g["per_kaart"] else None

    lezing.update({
        "door_po": [nr for nr in keuzes if keuzes[nr]["oordeel"]],
        "akkoord": akkoord,
        "notities_claude": dict(claude.get("notities", {})),
        "groepen": [{"sleutel": g["sleutel"], "vraag": g["vraag"], "kaarten": [k["id"] for k in g["kaarten"]],
                     "keuze": keuze(g)} for g in groepen]})
    if claude.get("afbakening"):
        lezing["afbakening"] = claude["afbakening"]
    return goed, lezing


def twijfelpagina(delen: list[tuple[dict, dict, list[dict]]]) -> str:
    """Eén leespagina voor de twijfel van één of meer dossiers: per dossier de naam, wat Claude las, en de groepen met
    hun kaarten, als JSON in een scripttag; een `</` in een bewering sluit die tag nooit."""
    sjabloon = (Path(__file__).resolve().parent / "dossiers_twijfel.html").read_text(encoding="utf-8")
    data = {"dossiers": [{"dossier": d["sleutel"], "naam": d["naam"]["nl"], "omschrijving": d["inleiding"]["nl"],
                          "afbakening": claude.get("afbakening", ""),
                          "telling": {w: sum(v == w for v in claude.get("labels", {}).values())
                                      for w in ("ja", "nee", "twijfel")},
                          "groepen": groepen} for d, claude, groepen in delen]}
    return sjabloon.replace("/*DOSSIERS*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _paginas(pub: sqlite3.Connection, nummers: list[str]) -> dict[str, dict]:  # pragma: no cover - op de uitgave
    """Per nummer wat een kaart nodig heeft: de bewering, het label, de eerste check met haar link, de redacties en een
    vertaling die de PO leest (Nederlands, anders Engels)."""
    uit: dict[str, dict] = {}
    for nr in nummers:
        p = pub.execute("SELECT nummer, bewering, taal, label, eerste_datum FROM pagina WHERE nummer = ?", (nr,)).fetchone()
        if p is None:
            continue
        checks = pub.execute("SELECT redactie, url, datum FROM check_ WHERE pagina = ? ORDER BY datum = '', datum, volg",
                             (nr,)).fetchall()
        vertaling = dict(pub.execute("SELECT taal, tekst FROM vertaling WHERE pagina = ?", (nr,)).fetchall())
        uit[nr] = {**dict(p), "redacties": sorted({c["redactie"] for c in checks}), "url": checks[0]["url"] if checks else "",
                   "vertaling": "" if p["taal"] in ("nl", "en") else vertaling.get("nl") or vertaling.get("en") or ""}
    return uit


def _lezing_pad(sleutel: str) -> Path:  # pragma: no cover - een pad
    return LEZINGEN / f"33.6-dossier-{sleutel}.json"


def _lezing(sleutel: str) -> dict:  # pragma: no cover - een bestand
    pad = _lezing_pad(sleutel)
    return json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}


def _voorstellen(sleutel: str) -> dict[str, dict]:  # pragma: no cover - een bestand
    return {r["nummer"]: r["uit"] for r in _jsonl(WERK / sleutel / "voorstellen.jsonl") if r.get("uit")}


def _vraag(dossier: dict, nummers: list[str], pub: sqlite3.Connection) -> None:  # pragma: no cover - een model
    """Vraagt `dossiervoorstel-v1` over de nummers, tien per vraag, direct en tegelijk; per bewering een regel. Hervatbaar."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    pad = WERK / dossier["sleutel"] / "voorstellen.jsonl"
    rijen = _jsonl(pad)
    klaar = {r["nummer"] for r in rijen if r.get("uit")}
    werk = [nr for nr in nummers if nr not in klaar]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(r.get("kosten", 0.0) for r in rijen)
    binnen_grens(SCHATTING * len(werk), uitgegeven)
    tekst = {r["nummer"]: (r["bewering"], r["taal"]) for r in pub.execute(
        f"SELECT nummer, bewering, taal FROM pagina WHERE nummer IN ({','.join('?' * len(werk))})", werk)}
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]
    pad.parent.mkdir(parents=True, exist_ok=True)

    def een(groep: list[str]) -> None:
        try:
            msg = client.messages.create(**voorstelverzoek(dossier, [tekst[nr] for nr in groep]))
            # direct, dus zonder batchkorting: twee keer de batchprijs
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            antwoord = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        gelezen = lees_voorstel(antwoord, len(groep))
        with slot, pad.open("a", encoding="utf-8") as f:
            for nr, g in zip(groep, gelezen):
                f.write(json.dumps({"nummer": nr, "versie": VERSIE, "uit": g, "kosten": round(kosten / len(groep), 7)},
                                   ensure_ascii=False) + "\n")

    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(pad)
    oordelen = Counter((r["uit"] or {}).get("oordeel", "geen antwoord") for r in nu)
    print(f"{len([r for r in nu if r.get('uit')])} beantwoord: {dict(oordelen)}; ${sum(r.get('kosten', 0.0) for r in nu):.3f} "
          f"van ${GRENS:.2f}")


def _inkortstap(dossier: dict, pub: sqlite3.Connection, werk: Path, per_jaar: int) -> None:  # pragma: no cover - op de uitgave
    """Kort `factchecks.json` in tot de beweringen die het vaakst rondgingen (`inkorten`): per factcheck van het dossier
    de pagina's in het hele archief die er met de vectoren van *Lijkt op* op lijken (vanaf `ZELFDE`), met hun redacties
    en talen; de factchecks van het dossier die op elkaar lijken zijn één bewering. Wat eruit gaat, staat met de
    cijfers in `data/dossiers/<sleutel>/inkorten.json`."""
    import numpy as np

    sleutel = dossier["sleutel"]
    pad = MAP / sleutel / "factchecks.json"
    goed = json.loads(pad.read_text(encoding="utf-8"))
    nummers = [f["nummer"] for f in goed["factchecks"]]
    vorige = werk / "inkorten.json"
    if vorige.exists():          # opnieuw kiezen begint bij alles wat de lezing goedkeurde, niet bij de vorige keuze
        nummers = json.loads(vorige.read_text(encoding="utf-8"))["voor"]
        goed["factchecks"] = [{"nummer": nr} for nr in nummers]
    eigen = {r[0] for r in pub.execute(
        f"SELECT DISTINCT pagina FROM check_ WHERE bron = 'factiz-redactie' AND pagina IN ({','.join('?' * len(nummers))})",
        nummers)}
    redacties: dict[str, set] = {}
    for nr, red in pub.execute("SELECT pagina, redactie FROM check_"):
        redacties.setdefault(nr, set()).add(red)
    taal = dict(pub.execute("SELECT nummer, taal FROM pagina"))
    jaar = {nr: (d or "")[:4] for nr, d in pub.execute("SELECT nummer, eerste_datum FROM pagina")}
    lt = WORTEL / "data" / "lijktop"
    namen = json.loads((lt / "vectoren.json").read_text(encoding="utf-8"))["namen"]
    plek = {nr: i for i, nr in enumerate(namen)}
    v = np.load(lt / "vectoren.npy", mmap_mode="r")
    met = [nr for nr in nummers if nr in plek and nr not in eigen]
    x = np.array(v[[plek[nr] for nr in met]], dtype=np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    buren: dict[str, set[str]] = {nr: {nr} for nr in met}
    ruim: dict[str, set[str]] = {nr: {nr} for nr in met}
    for begin in range(0, len(namen), 20000):
        blok = np.array(v[begin:begin + 20000], dtype=np.float32)
        blok /= np.linalg.norm(blok, axis=1, keepdims=True)
        lijkt = x @ blok.T
        for i, j in zip(*np.nonzero(lijkt >= VERHAAL)):
            ruim[met[i]].add(namen[begin + j])
            if lijkt[i, j] >= ZELFDE:
                buren[met[i]].add(namen[begin + j])
    binnen = x @ x.T
    groep: dict[str, str] = {}
    for i in sorted(range(len(met)), key=lambda i: -len(buren[met[i]])):     # de breedste bewering wordt de kern
        if met[i] in groep:
            continue
        for j in np.nonzero(binnen[i] >= VARIANT)[0]:
            groep.setdefault(met[j], met[i])
    kandidaten = []
    for nr in nummers:
        b, r = buren.get(nr, {nr}), ruim.get(nr, {nr})
        kandidaten.append({"nummer": nr, "groep": groep.get(nr, nr), "eigen": nr in eigen,
                           "redacties": len(set().union(*(redacties.get(p, set()) for p in b))),
                           "checks": len(b), "talen": len({taal.get(p) for p in b} - {None}),
                           "ruim_redacties": len(set().union(*(redacties.get(p, set()) for p in r))), "ruim_checks": len(r),
                           "eigen_redacties": len(redacties.get(nr, set())), "jaar": jaar.get(nr, "")})
    gekozen = inkorten(kandidaten, per_jaar)
    werk.mkdir(parents=True, exist_ok=True)
    (werk / "inkorten.json").write_text(json.dumps({
        "toelichting": f"De strenge keuze (SPECS E9.S7 AC10): {len(gekozen)} van de {len(nummers)} goedgekeurde factchecks, "
                       f"per bewering één, hoogstens {per_jaar} per jaar, op het aantal redacties dat haar in het archief checkte "
                       f"(vectoren {ZELFDE}).",
        "voor": nummers, "gekozen": gekozen, "kandidaten": kandidaten}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bewaard = {f["nummer"]: f for f in goed["factchecks"]}
    goed["factchecks"] = [bewaard[nr] for nr in gekozen]
    goed["toelichting"] = (goed.get("toelichting", "").split(" Strenge keuze")[0].rstrip() + f" Strenge keuze (SPECS E9.S7 AC10): de {len(gekozen)} "
                           f"beweringen die het vaakst rondgingen, hoogstens {per_jaar} per jaar, van de {len(nummers)}; de rest in "
                           f"data/dossiers/{sleutel}/inkorten.json.")
    pad.write_text(json.dumps(goed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sleutel}: {len(gekozen)} van de {len(nummers)} ({len(eigen)} eigen, {len(set(groep.values()))} beweringen)")


def _versiestap(stap: str, dossier: dict, pub: sqlite3.Connection, werk: Path, keuzes_pad: str | None,  # pragma: no cover
                door: str = "PO", akkoord: str | None = None) -> None:
    """`versies` vraagt het model welke goedgekeurde factchecks hetzelfde bericht zijn, `versiepagina` schrijft de
    leespagina voor de PO, `versies-goedkeuren` zet haar keuzes in `factchecks.json` en bij haar lezing."""
    sleutel = dossier["sleutel"]
    nummers = [f["nummer"] for f in dossier["factchecks"]]
    if stap == "versies":
        import anthropic

        from doublecheck.modellen import MODELLEN
        from doublecheck.varianten import laad_sleutel

        if len(nummers) < 2:
            raise Weigering(f"{sleutel}: {len(nummers)} goedgekeurde factchecks; een versie vraagt er minstens twee")
        uitgegeven = sum(r.get("kosten", 0.0) for r in _jsonl(werk / "voorstellen.jsonl")) + sum(
            r.get("kosten", 0.0) for r in _jsonl(werk / "versies.jsonl"))
        stukken_aantal = -(-len(nummers) // MAX_PER_VERSIEVRAAG)
        binnen_grens(0.01 * stukken_aantal, uitgegeven)
        tekst = {r["nummer"]: (r["bewering"], r["taal"]) for r in pub.execute(
            f"SELECT nummer, bewering, taal FROM pagina WHERE nummer IN ({','.join('?' * len(nummers))})", nummers)}
        hier = [nr for nr in nummers if nr in tekst]
        indeling = None
        if len(hier) <= MAX_PER_VERSIEVRAAG:
            stukken = [hier]
        else:
            # te veel voor één vraag: in stukken die op elkaar lijken, met de vectoren van *Lijkt op* (#34.2p)
            import numpy as np
            lt = WORTEL / "data" / "lijktop"
            namen = json.loads((lt / "vectoren.json").read_text(encoding="utf-8"))
            plek = {nr: i for i, nr in enumerate(namen["namen"])}
            if ontbreekt := [nr for nr in hier if nr not in plek]:
                raise Weigering(f"{sleutel}: {len(ontbreekt)} factchecks zonder vector in {lt}; draai eerst lijktop rekenen")
            x = np.load(lt / "vectoren.npy", mmap_mode="r")
            stukken = delen(np.asarray(x[[plek[nr] for nr in hier]]), hier)
            indeling = {"vectoren": f"{namen['versie']} {namen['model']}", "stukken": [len(s) for s in stukken]}
        laad_sleutel()
        client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN["haiku"]
        voorstel, antwoorden, kosten = {}, [], 0.0
        for i, stuk in enumerate(stukken):
            msg = client.messages.create(**versieverzoek(dossier, [tekst[nr] for nr in stuk]))
            kosten += 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            antwoord = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
            antwoorden.append(antwoord)
            # dezelfde naam in twee stukken is dezelfde versie: de namen zeggen welk bericht het is, en ik lees ze na
            voorstel.update(zip(stuk, lees_versies(antwoord, len(stuk))))
        werk.mkdir(parents=True, exist_ok=True)
        with (werk / "versies.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"versie": VERSIEVRAAG, "kosten": round(kosten, 6), "voorstel": voorstel,
                                "antwoord": antwoorden[0] if len(antwoorden) == 1 else antwoorden,
                                **({"indeling": indeling} if indeling else {})}, ensure_ascii=False) + "\n")
        telling = Counter(v for v in voorstel.values() if v)
        print(f"{len(telling)} versies over {sum(telling.values())} van de {len(hier)} factchecks; ${kosten:.4f}")
        for naam, n in telling.most_common():
            print(f"  {n:2}  {naam}")
        return
    rondes = _jsonl(werk / "versies.jsonl")
    if not rondes:
        raise Weigering(f"{sleutel}: nog geen voorstel voor versies; draai eerst `versies`")
    groepen = versiegroepen(dossier, rondes[-1]["voorstel"], _paginas(pub, nummers))
    if stap == "versiepagina":
        (werk / "versiegroepen.json").write_text(json.dumps(groepen, ensure_ascii=False, indent=1), encoding="utf-8")
        (werk / "versies.html").write_text(versiepagina(dossier, groepen), encoding="utf-8")
        print(f"{len(groepen)} versies met samen {sum(len(g['kaarten']) for g in groepen)} factchecks in {werk / 'versies.html'}")
        return
    if not keuzes_pad:
        raise Weigering("versies-goedkeuren vraagt --keuzes <json>")
    groepen = json.loads((werk / "versiegroepen.json").read_text(encoding="utf-8"))
    keuzes = json.loads(Path(keuzes_pad).read_text(encoding="utf-8"))
    if isinstance(keuzes.get("keuzes"), dict):            # een lezing van Claude: {gelezen_door, datum, keuzes}
        keuzes = keuzes["keuzes"]
    if door != "PO" and not _AKKOORD.fullmatch(akkoord or ""):
        raise Weigering('Claude leest alleen met het akkoord van de PO: --akkoord \'2026-11-12, PO: "haar woorden"\'')
    goed, lezing = versies_goedkeuren(dossier, groepen, keuzes, datum=date.today().isoformat(), door=door)
    pad = MAP / sleutel / "factchecks.json"
    oud = json.loads(pad.read_text(encoding="utf-8"))
    pad.write_text(json.dumps({"toelichting": oud.get("toelichting", ""), **goed}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    alles = _lezing(sleutel)
    alles["versies"] = {**alles.get("versies", {}), **lezing}
    if door != "PO":                                       # wie de versies las, en op welk akkoord (AC3, AC8)
        alles["versies_gelezen"] = {"door": door, "datum": date.today().isoformat(), "akkoord": akkoord}
    _lezing_pad(sleutel).write_text(json.dumps(alles, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    met = sum("versie" in f for f in goed["factchecks"])
    print(f"{sum(bool(v['leden']) for v in lezing.values())} van de {len(lezing)} gelezen versies goedgekeurd; "
          f"{met} van de {len(goed['factchecks'])} factchecks dragen nu een versie")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["kandidaten", "voorstellen", "toets", "pagina", "twijfel", "goedkeuren", "inkorten", "versies",
                                    "versiepagina", "versies-goedkeuren"])
    p.add_argument("--dossier", required=True, help="de sleutel: de naam van de map in content/dossiers/; bij twijfel "
                                                     "meer sleutels met komma's")
    p.add_argument("--proef", type=int, help="voorstellen: alleen de eerste N kandidaten")
    p.add_argument("--per-jaar", type=int, help=f"inkorten: hoogstens zoveel beweringen per jaar (standaard {MAX_PER_JAAR})")
    p.add_argument("--keuzes", help="goedkeuren: het bestand met de keuzes van de PO ({nummer: {oordeel, opmerking}}; "
                                    "met --claude {groepen: {sleutel: {...}}, kaarten: {nummer: {...}}})")
    p.add_argument("--claude", action="store_true", help="goedkeuren: Claude las elke kaart (data/dossiers/<sleutel>/"
                                                         "claude-lezing.json), de PO besliste over zijn twijfel")
    p.add_argument("--akkoord", help='goedkeuren --claude: 2026-11-12, PO: "haar woorden"')
    p.add_argument("--uitgave", help="een ander bestand dan de nieuwste publicatiedatabase")
    a = p.parse_args()
    try:
        if a.stap == "twijfel":
            # één leespagina met de twijfel van Claude bij elk genoemd dossier (SPECS E9.S7 AC3)
            delen = []
            for sleutel in a.dossier.split(","):
                claude = json.loads((WERK / sleutel / "claude-lezing.json").read_text(encoding="utf-8"))
                kaarten_ = json.loads((WERK / sleutel / "kaarten.json").read_text(encoding="utf-8"))
                delen.append((lees_dossier(MAP / sleutel), claude, twijfelgroepen(kaarten_, claude)))
            (WERK / "twijfel.html").write_text(twijfelpagina(delen), encoding="utf-8")
            print(f"{sum(len(g) for _, _, g in delen)} groepen met "
                  f"{sum(len(x['kaarten']) for _, _, g in delen for x in g)} kaarten in {WERK / 'twijfel.html'}")
            return
        dossier = lees_dossier(MAP / a.dossier)
        pub = open_uitgave(a.uitgave)
        werk = WERK / a.dossier
        if a.stap == "inkorten":
            _inkortstap(dossier, pub, werk, a.per_jaar or MAX_PER_JAAR)
            return
        if a.stap in ("versies", "versiepagina", "versies-goedkeuren"):
            _versiestap(a.stap, dossier, pub, werk, a.keuzes, door="Claude en PO" if a.claude else "PO", akkoord=a.akkoord)
            return
        if not dossier.get("voorstel"):
            raise Weigering(f"{a.dossier}: zonder [voorstel] met woorden en een omschrijving valt er niets voor te stellen")
        nummers = kandidaten(pub, dossier["voorstel"]["woorden"])
        if a.stap == "kandidaten":
            talen = Counter(r[0] for r in pub.execute(
                f"SELECT taal FROM pagina WHERE nummer IN ({','.join('?' * len(nummers))})", nummers))
            print(f"{len(nummers)} kandidaten; talen {dict(talen.most_common(8))}; ~${SCHATTING * len(nummers):.3f} om te vragen")
        elif a.stap == "voorstellen":
            _vraag(dossier, nummers[:a.proef] if a.proef else nummers, pub)
        elif a.stap == "toets":
            # Wat ik vooraf als *hoort erbij* las, tegen wat het model zegt (PLAN #33.6): minstens 90% ja.
            toets = json.loads((LEZINGEN / f"33.6-dossier-{a.dossier}-toets.json").read_text(encoding="utf-8"))["labels"]
            voorstellen = _voorstellen(a.dossier)
            horen = [nr for nr, w in toets.items() if w == "hoort"]
            niet = [nr for nr, w in toets.items() if w == "hoort-niet"]
            ja = [nr for nr in horen if (voorstellen.get(nr) or {}).get("oordeel") == "ja"]
            vals = [nr for nr in niet if (voorstellen.get(nr) or {}).get("oordeel") == "ja"]
            print(f"van de {len(horen)} die erbij horen zegt het model bij {len(ja)} ja "
                  f"({len(ja) / len(horen):.0%}; eis 90%); van de {len(niet)} die er niet bij horen bij {len(vals)} ja")
            for nr in horen:
                if nr not in ja:
                    print("  gemist:", nr, voorstellen.get(nr))
        elif a.stap == "pagina":
            lezing = _lezing(a.dossier)
            ander = elders(lees_alle(), a.dossier)
            voorstellen_ = _voorstellen(a.dossier)
            weg = Counter(ander[nr] for nr, v in voorstellen_.items()
                          if nr in ander and v and v["oordeel"] in ("ja", "twijfel"))
            kaarten_ = kaarten(voorstellen_, _paginas(pub, list(voorstellen_)),
                               gelezen=set(lezing.get("labels", {})) | set(ander))
            if weg:
                print(f"{sum(weg.values())} voorgestelde factchecks staan al in een ander verhaaldossier en blijven weg: "
                      f"{dict(weg)}")
            werk.mkdir(parents=True, exist_ok=True)
            (werk / "kaarten.json").write_text(json.dumps(kaarten_, ensure_ascii=False, indent=1), encoding="utf-8")
            (werk / "nakijken.html").write_text(po_pagina(dossier, kaarten_), encoding="utf-8")
            print(f"{len(kaarten_)} kaarten ({sum(k['voorstel'] == 'ja' for k in kaarten_)} ja, "
                  f"{sum(k['voorstel'] == 'twijfel' for k in kaarten_)} twijfel) in {werk / 'nakijken.html'}")
        else:
            if not a.keuzes:
                raise Weigering("goedkeuren vraagt --keuzes <json>")
            kaarten_ = json.loads((werk / "kaarten.json").read_text(encoding="utf-8"))
            oud = _lezing(a.dossier)
            keuzes = json.loads(Path(a.keuzes).read_text(encoding="utf-8"))
            if a.claude:
                claude = json.loads((werk / "claude-lezing.json").read_text(encoding="utf-8"))
                goed, lezing = goedkeuring_met_claude(dossier, kaarten_, claude, keuzes.get("groepen", {}),
                                                      keuzes.get("kaarten", {}), datum=date.today().isoformat(),
                                                      akkoord=a.akkoord, eerder=oud.get("labels"))
            else:
                goed, lezing = goedkeuring(dossier, kaarten_, keuzes, datum=date.today().isoformat(),
                                           eerder=oud.get("labels"))
            lezing = voeg_lezing_samen(oud, lezing)
            (MAP / a.dossier / "factchecks.json").write_text(json.dumps({
                "toelichting": (("De factchecks die Claude en de PO bij dit dossier goedkeurden: Claude las elke kaart, "
                                 "de PO besliste over zijn twijfel" if a.claude else
                                 "De factchecks die de PO bij dit dossier goedkeurde") +
                                " (PLAN #33.6, SPECS E9.S7 AC3). Geschreven door `python -m doublecheck.dossiers "
                                f"goedkeuren`; de hele lezing staat in docs/steekproeven/33.6-dossier-{a.dossier}.json."),
                **goed},
                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            _lezing_pad(a.dossier).write_text(json.dumps({**lezing, "toelichting": (
                (f"De lezing van de voorstellen bij het dossier {a.dossier} (PLAN #33.6, SPECS E9.S7 AC3): Claude las elke "
                 "kaart (zijn reden onder `notities_claude`), de PO besliste over zijn twijfel per groep (`groepen`) of per "
                 "kaart; `door_po` zegt welke kaarten zij besliste, `akkoord` haar woorden. "
                 if a.claude else
                 f"De lezing van de PO van de voorstellen bij het dossier {a.dossier} (PLAN #33.6): per factcheck ja, nee of "
                 "twijfel (alleen een notitie), gekozen op de leespagina en door Claude teruggelezen. ") +
                "Onder `versies` de lezing van welke factchecks hetzelfde bericht zijn. Wat hier staat, vraagt een "
                "volgende ronde niet opnieuw.")},
                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            telling = Counter(lezing["labels"].values())
            print(f"{len(goed['factchecks'])} factchecks in het dossier; gelezen {dict(telling)}; "
                  f"{len(lezing['opmerkingen'])} notities")
    except Weigering as fout:
        raise SystemExit(f"geweigerd: {fout}") from None


if __name__ == "__main__":  # pragma: no cover
    main()
