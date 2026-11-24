"""De gebruikerstoets (P11 van fase 0, B47; PLAN #32.0k): zoals de PO het zelf
zou testen.

250 Engelse berichten in zes delen, het juiste antwoord uit hoe ze gemaakt zijn:
- A, 50 echte artikelen als screenshot van een nieuwssite (Sheffield);
- B, 50 vervalste: een andere krant of een verzonnen schrijver erboven (20), één
  feit veranderd (20), een verzonnen kop onder een echte krantennaam (10);
- C, 40 echte gebeurtenissen met één vals detail, als post of appbericht;
- D, 40 mythes over gezondheid en wetenschap, als TikTok-bijschrift;
- E, 30 vertekende politieke beweringen, half van links en half van rechts;
- F, 40 overduidelijke leugens en waarheden over de vastgestelde feiten.
Haiku verandert de feiten en schrijft de verzinsels; ik lees ze allemaal vóór de
toets. Elk bericht gaat door Factiz (zoals `try.factiz.org/check`), door het kale
model met zoeken en door een model zonder zoeken. Screenshots bestaan alleen in
het geheugen; een datum staat er niet bij, dus de vraag zegt dat ze onbekend is.

    python -m doublecheck.gebruikerstoets kanten indienen|ophalen
    python -m doublecheck.gebruikerstoets kiezen
    python -m doublecheck.gebruikerstoets genereren indienen|ophalen|lezen
    python -m doublecheck.hittewacht -- python -m doublecheck.gebruikerstoets set
    python -m doublecheck.gebruikerstoets indienen [--proef 3]|herkansing|vorm|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as t
from doublecheck import herstel as h
from doublecheck import verificatie as v

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "gebruikerstoets"
LABELS = WORTEL / "docs" / "steekproeven" / "32.0k-gebruikerstoets.json"
BUDGET = 12.0  # binnen de grens van $30 voor de proeven op data (PO 2026-10-27)
ZAAD = 3200
NR_SCHUIF = 20_000  # andere verzonnen namen en nummers in de chatberichten dan in ronde 4 en 5
DELEN = "ABCDEF"
AANTAL = {"A": 50, "B-krant": 10, "B-schrijver": 10, "B-feit": 20, "B-kop": 10, "C": 40, "D": 40,
          "E-check": 13, "F-onwaar": 20, "F-waar": 20}
RESERVE = {"A": 10, "B-krant": 5, "B-schrijver": 5, "B-feit": 10, "B-kop": 5, "C": 45}
VERWACHT = {"A": ("waar", "echt"), "B-krant": ("waar", "vals"), "B-schrijver": ("waar", "vals"),
            "B-feit": ("onwaar", "vals"), "B-kop": ("onwaar", "vals"), "C": ("onwaar", None), "D": ("onwaar", None),
            "E": ("misleidend", None), "F-onwaar": ("onwaar", None), "F-waar": ("waar", None)}
# Vier vertekende beweringen zonder check in de database, twee per kant (PLAN #32.0k, deel E).
EIGEN_POLITIEK = [
    {"id": "eigen-1", "tekst": "The European Union is deliberately bringing boat refugees into Europe.", "kant": "rechts"},
    {"id": "eigen-2", "tekst": "Most crime in Europe is committed by migrants.", "kant": "rechts"},
    {"id": "eigen-3", "tekst": "Billionaires in America pay no taxes at all.", "kant": "links"},
    {"id": "eigen-4", "tekst": "Corporate greed is the only reason prices went up after 2021.", "kant": "links"},
]
# Alleen gangbare nieuwssites: de PO test met screenshots van krantenartikelen, niet met verdragen of sites van organisaties.
NIEUWS = frozenset({"theguardian.com", "bbc.com", "bbc.co.uk", "dw.com", "rferl.org", "washingtonpost.com", "edition.cnn.com",
                    "cnn.com", "politico.eu", "politico.com", "apnews.com", "euronews.com", "nytimes.com", "france24.com",
                    "independent.co.uk", "cnbc.com", "themoscowtimes.com", "meduza.io", "kyivpost.com", "voanews.com", "npr.org",
                    "newsweek.com", "bloomberg.com", "cbsnews.com", "telegraph.co.uk", "nbcnews.com", "abcnews.go.com",
                    "eu.usatoday.com", "theatlantic.com", "economist.com", "euobserver.com", "irishtimes.com", "latimes.com",
                    "scmp.com", "euractiv.com", "lrt.lt", "news.err.ee", "reuters.com", "aljazeera.com"})
SCHRIJVERS = ["Daniel Hartwell", "Megan Okafor", "Lucas Brennan", "Priya Castellano", "Tobias Wren", "Hannah Voss",
              "Samuel Achterberg", "Clara Lindqvist", "Owen Mbeki", "Isla Moreau"]
GEZONDHEID = re.compile(r"\b(vaccin\w*|cancer|covid\w*|virus\w*|cure[sd]?|doctors?|disease\w*|diabet\w*|vitamin\w*|"
                        r"immun\w*|heart|scientists?|health|drugs?|medic\w*|hospital\w*|infection\w*|flu|autism|5g|"
                        r"garlic|lemon|detox|diet|cholesterol|blood|pharma\w*)\b", re.I)
KAAL_VRAAG = ("Is this true?\n\n{bericht}\n\nAnswer in English: explain briefly, cite your sources, and end with one "
              "line: VERDICT: true, false or uncertain.")
_KAAL_OORDEEL = re.compile(r"VERDICT\W*(true|false|uncertain)", re.I)
# Per vraag via de Batch API, ruim (ronde 4 en 5).
SCHATTING = {"factiz": 0.022, "kaal": 0.02, "zonder": 0.003, "feit": 0.0015, "vorm": 0.0013, "herkansing": 0.03,
             "haiku": 0.0008}


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


# --- de set --------------------------------------------------------------------------

def domein(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").split(":")[0]


def domeinen(bronnen: list[dict]) -> set[str]:
    return {domein(b["url"]) for b in bronnen if b.get("url")}


def _schud(rijen: list[dict], naam: str) -> list[dict]:
    rijen = sorted(rijen, key=lambda r: r["id"])
    random.Random(f"{ZAAD}-{naam}").shuffle(rijen)
    return rijen


def kies(pools: dict[str, list[dict]], afgewezen: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """De 250 berichten van PLAN #32.0k, met het juiste antwoord, de vorm en de helft.
    Wat bij het lezen vóór de toets is afgewezen, wordt vervangen door het volgende
    in dezelfde vaste volgorde; de rest verschuift niet."""
    artikelen = _schud(pools["artikelen"], "artikelen")
    andere = sorted({domein(a["sleutel"][2:]) for a in artikelen})
    uit: list[dict] = []

    def voeg(rij: dict, sub: str, vorm: str, **extra) -> None:
        inhoud, herkomst = VERWACHT[sub if sub in VERWACHT else sub.split("-")[0]]
        uit.append({"id": f"{sub}:{rij['id']}", "bron_id": rij["id"], "sleutel": rij.get("sleutel"),
                    "zaak": rij.get("zaak"), "deel": sub[0], "sub": "E" if sub.startswith("E") else sub,
                    "tekst": rij["tekst"], "vorm": vorm, "kant": rij.get("kant"),
                    "verwacht": {"inhoud": inhoud, "herkomst": herkomst}, "toon_domein": None, "schrijver": None,
                    **extra})

    rng = random.Random(f"{ZAAD}-vervalsing")
    begin = 0
    for sub in ("A", "B-krant", "B-schrijver", "B-feit", "B-kop", "C"):
        # Elk deel een eigen vast blok met reserve: een afwijzing verschuift alleen binnen dat deel.
        blok = artikelen[begin: begin + AANTAL[sub] + RESERVE[sub]]
        begin += AANTAL[sub] + RESERVE[sub]
        for i, rij in enumerate([a for a in blok if a["id"] not in afgewezen][: AANTAL[sub]]):
            eigen = domein(rij["sleutel"][2:])
            if sub == "C":
                voeg(rij, sub, "chat" if i % 2 else "tekst")
                continue
            toon = rng.choice([d for d in andere if d != eigen]) if sub == "B-krant" else eigen
            voeg(rij, sub, "nieuws", toon_domein=toon,
                 schrijver=rng.choice(SCHRIJVERS) if sub == "B-schrijver" else None)
    for rij in [r for r in _schud(pools["gezondheid"], "gezondheid") if r["id"] not in afgewezen][: AANTAL["D"]]:
        voeg(rij, "D", "tiktok")
    for kant in ("links", "rechts"):
        rijen = [p for p in _schud([p for p in pools["politiek"] if p["kant"] == kant], f"politiek-{kant}")
                 if p["id"] not in afgewezen][: AANTAL["E-check"]]
        for rij in rijen + [e for e in EIGEN_POLITIEK if e["kant"] == kant]:
            voeg(rij, "E", "tekst")
    for sub, pool in (("F-onwaar", "feit_onwaar"), ("F-waar", "feit_waar")):
        for rij in [r for r in _schud(pools[pool], pool) if r["id"] not in afgewezen][: AANTAL[sub]]:
            voeg(rij, sub, "tekst")
    for deel in DELEN:  # de vorm om en om binnen E, en de helften per deel
        rijen = [s for s in uit if s["deel"] == deel]
        for i, s in enumerate(rijen):
            if deel == "E":
                s["vorm"] = "chat" if i % 2 else "tekst"
        volgorde = _schud(rijen, f"helft-{deel}")
        for i, s in enumerate(volgorde):
            s["helft"] = "ontwikkel" if i % 2 == 0 else "toets"
    return uit


# --- de kale vraag -----------------------------------------------------------------------

def kaal_verzoek(tekst: str, zoeken: bool, config) -> dict:
    """De vraag die iedereen een taalmodel zou stellen: zonder onze database, regels of schaal."""
    params = {"model": config.berichtcontrole.model_id, "max_tokens": 2_000,
              "messages": [{"role": "user", "content": KAAL_VRAAG.format(bericht=tekst)}],
              "output_config": {"effort": "low"}}
    if zoeken:
        params["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": v.MAX_ZOEKEN}]
    return params


def lees_kaal(tekst: str) -> str | None:
    """Rood of groen uit de laatste regel VERDICT; onzeker of onleesbaar is geen kleur."""
    gevonden = _KAAL_OORDEEL.findall(tekst or "")
    if not gevonden:
        return None
    return {"true": "groen", "false": "rood"}.get(gevonden[-1].lower())


# --- tellen ----------------------------------------------------------------------------

def _label(labels: dict, sleutel: tuple) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def _tel(stukken: list[dict], factiz: dict, kaal: dict, zonder: dict, labels: dict) -> dict:
    uit: dict = {}
    for s in stukken:
        i, deel = s["id"], s["deel"]
        if i not in factiz or i not in kaal or i not in zonder:
            continue
        f, k, z = factiz[i], kaal[i], zonder[i]
        d = uit.setdefault(deel, Counter())
        d["n"] += 1
        for wie, u in (("factiz", f), ("kaal", k), ("zonder", z)):
            if u["kleur"]:
                d[f"{wie} {u['kleur']}"] += 1
        if deel == "A":
            for wie, u in (("factiz", f), ("kaal", k)):
                if u["kleur"] == "rood":
                    label = _label(labels, (i, wie, "rood"))
                    d["set fout"] += wie == "factiz" and label == "set fout"
                    d[f"{wie} onterecht rood"] += label == "vals"
        elif deel == "B":
            for wie, u in (("factiz", f), ("kaal", k), ("zonder", z)):
                if u["kleur"] == "groen":
                    d[f"{wie} groen bij een vervalsing"] += 1
                    d[f"{wie} groen bij {s['sub']}"] += 1
        elif deel == "C":
            for wie, u in (("factiz", f), ("kaal", k)):
                if u["kleur"] == "groen":
                    label = _label(labels, (i, wie, "groen"))
                    d["set fout"] += wie == "factiz" and label == "set fout"
                    d[f"{wie} groen"] -= label != "vals"  # alleen een echt vals groen telt
        elif deel == "D":
            if f["kleur"] == "rood":
                bewijs = f["eigen_bewijs"] or (bool(f["bronnen"]) and
                                               _label(labels, (i, "factiz", "bewijs")) in ("bewijst",
                                                                                           "bewijst via factcheck"))
                d["factiz rood met bewijs"] += bewijs
        elif deel == "E":
            d[f"n {s['kant']}"] += 1
            if f["kleur"] == "rood":
                d[f"factiz rood {s['kant']}"] += 1
            d["factiz context met twee bronnen"] += len(domeinen(f["bronnen"])) >= 2
        elif deel == "F":
            goed = "rood" if s["verwacht"]["inhoud"] == "onwaar" else "groen"
            for wie, u in (("factiz", f), ("kaal", k), ("zonder", z)):
                d[f"{wie} goed"] += u["kleur"] == goed
            d["factiz onzeker waar kaal goed is met bron"] += (f["kleur"] is None and k["kleur"] == goed
                                                               and bool(k["bronnen"]))
    return {deel: dict(d) for deel, d in uit.items()}


def _vul(d: dict, *velden: str) -> dict:
    return {**{v_: 0 for v_ in velden}, **d}


def telling(stukken: list[dict], factiz: dict, kaal: dict, zonder: dict, labels: dict) -> dict:
    """Per deel wat Factiz, het kale model en het model zonder zoeken zeiden, en de
    eisen van PLAN #32.0k. Weigert zolang iets dat telt geen label heeft."""
    uit = _tel(stukken, factiz, kaal, zonder, labels)
    velden = {"A": ("factiz rood", "kaal rood", "factiz onterecht rood", "kaal onterecht rood", "set fout"),
              "B": ("factiz groen bij een vervalsing", "kaal groen bij een vervalsing", "zonder groen bij een vervalsing"),
              "C": ("factiz groen", "kaal groen", "factiz rood", "kaal rood", "set fout"),
              "D": ("factiz rood", "kaal rood", "zonder rood", "factiz rood met bewijs"),
              "E": ("factiz rood links", "factiz rood rechts", "factiz groen", "factiz context met twee bronnen",
                    "n links", "n rechts"),
              "F": ("factiz goed", "kaal goed", "zonder goed", "factiz onzeker waar kaal goed is met bron")}
    for deel, d in uit.items():
        uit[deel] = _vul(d, *velden[deel])
    eisen: dict = {}
    if "A" in uit:
        eisen["A hoogstens 1 van de 50 rood"] = uit["A"]["factiz onterecht rood"] <= 1
    if "C" in uit:
        eisen["C hoogstens 2 van de 40 groen"] = uit["C"]["factiz groen"] <= 2
    if "D" in uit:
        eisen["D minstens 90% rood met bewijs"] = uit["D"]["factiz rood met bewijs"] >= 0.9 * uit["D"]["n"]
    if "E" in uit:
        e = uit["E"]
        eisen["E elk antwoord context met minstens twee onafhankelijke bronnen"] = \
            e["factiz context met twee bronnen"] == e["n"]
        eisen["E hoogstens 2 groen"] = e["factiz groen"] <= 2
        eisen["E links en rechts rood binnen 3 van elkaar"] = abs(e["factiz rood links"] - e["factiz rood rechts"]) <= 3
    if "F" in uit:
        f = uit["F"]
        eisen["F minstens 95% goed"] = f["factiz goed"] >= 0.95 * f["n"]
        eisen["F vloer: nooit onzeker waar het kale model het goed heeft"] = \
            f["factiz onzeker waar kaal goed is met bron"] == 0
    vergelijk = []
    if "A" in uit:
        vergelijk.append(uit["A"]["factiz onterecht rood"] <= uit["A"]["kaal onterecht rood"])
    if "C" in uit:
        vergelijk.append(uit["C"]["factiz groen"] <= uit["C"]["kaal groen"])
    if "D" in uit:
        vergelijk.append(uit["D"]["factiz rood"] >= uit["D"]["kaal rood"])
    if "F" in uit:
        vergelijk.append(uit["F"]["factiz goed"] >= uit["F"]["kaal goed"])
    if vergelijk:
        eisen["niet slechter dan het kale model op A, C, D en F"] = all(vergelijk)
    uit["eisen"] = eisen
    uit["toetshelft"] = _tel([s for s in stukken if s.get("helft") == "toets"], factiz, kaal, zonder, labels)
    return uit


# --- de sjablonen ------------------------------------------------------------------------

def _letters():  # pragma: no cover - met Pillow
    from PIL import ImageFont

    gewoon = next(p for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(p).exists())
    vet = next((p for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if Path(p).exists()), gewoon)
    return lambda grootte, dik=False: ImageFont.truetype(vet if dik else gewoon, grootte)


def teken_nieuws(domein_: str, kop: str, lead: str, schrijver: str | None = None):  # pragma: no cover - Pillow
    """Een screenshot van een artikel op een nieuwssite: de adresbalk, de naam van de
    site als tekst (geen echt logo), de kop, eventueel een schrijver, het begin."""
    from PIL import Image, ImageDraw

    from doublecheck.routemeting import _breek

    letter = _letters()
    breed = 1000
    kopregels = _breek(kop, letter(46, True), breed - 100)
    leadregels = _breek(lead, letter(28), breed - 100)
    hoog = 260 + 58 * len(kopregels) + (50 if schrijver else 0) + 40 * len(leadregels) + 60
    beeld = Image.new("RGB", (breed, hoog), "white")
    d = ImageDraw.Draw(beeld)
    d.rectangle([0, 0, breed, 70], fill=(241, 243, 244))
    d.rounded_rectangle([20, 14, breed - 20, 56], radius=20, fill="white")
    d.text((44, 22), f"https://www.{domein_}/news", font=letter(22), fill=(60, 64, 67))
    d.text((50, 100), domein_.split(".")[0].upper(), font=letter(40, True), fill=(20, 20, 20))
    d.line([50, 160, breed - 50, 160], fill=(200, 200, 200), width=2)
    y = 190
    for regel in kopregels:
        d.text((50, y), regel, font=letter(46, True), fill=(10, 10, 10))
        y += 58
    if schrijver:
        d.text((50, y + 10), f"By {schrijver}", font=letter(24), fill=(90, 90, 90))
        y += 50
    y += 20
    for regel in leadregels:
        d.text((50, y), regel, font=letter(28), fill=(40, 40, 40))
        y += 40
    return beeld


def teken_tiktok(bijschrift: str, handle: str):  # pragma: no cover - met Pillow
    """Een screenshot van een TikTok-video: donker, het account en het bijschrift onderaan."""
    from PIL import Image, ImageDraw

    from doublecheck.routemeting import _breek

    letter = _letters()
    beeld = Image.new("RGB", (720, 1280), (22, 24, 35))
    d = ImageDraw.Draw(beeld)
    d.text((220, 50), "Following   For You", font=letter(30, True), fill="white")
    for j, tekst in enumerate(("♥ 48.2K", "💬 1,204", "↗ Share")):
        d.text((600, 640 + 110 * j), tekst, font=letter(24), fill="white")
    regels = _breek(bijschrift, letter(30), 540)
    y = 1180 - 42 * len(regels)
    d.text((30, y - 60), f"@{handle}", font=letter(30, True), fill="white")
    for regel in regels:
        d.text((30, y), regel, font=letter(30), fill="white")
        y += 42
    return beeld


# --- de pools, de keuze en wat Haiku maakt ---------------------------------------------------

def _gebruikt() -> tuple[set[str], set[str]]:  # pragma: no cover - op de eerdere rondes
    ids, sleutels = t._gebruikt()
    for pad in (t.UIT / "set.jsonl", h.UIT / "set.jsonl"):
        for s in t._jsonl(pad):
            ids.add(s["id"])
            sleutels.add(s["sleutel"])
    return ids, sleutels


def kandidaten_politiek() -> list[dict]:  # pragma: no cover - op de database
    """Checks met het oordeel misleidend of deels waar, in het Engels, nog nergens gebruikt."""
    import sqlite3

    ids, sleutels = _gebruikt()
    conn = sqlite3.connect(WORTEL / "doublecheck.db")
    rijen = conn.execute("SELECT c.claim_id, c.canonical_text FROM claim c JOIN factcheck f ON f.claim_id = c.claim_id "
                         "WHERE f.language = 'en' AND f.verdict_normalized IN ('misleidend', 'deels-waar') "
                         "GROUP BY c.claim_id").fetchall()
    uit = [{"id": cid, "sleutel": f"C:{cid}", "zaak": cid, "tekst": " ".join(tekst.split())} for cid, tekst in rijen
           if f"C:{cid}" not in sleutels and 40 <= len(tekst) <= 300 and not h.omschrijving(tekst)]
    return _schud(uit, "kandidaten-politiek")[:200]


def pools() -> dict[str, list[dict]]:  # pragma: no cover - op de basisset, de database en ronde 1
    from doublecheck import basisset
    from doublecheck.leerstof import taalcode

    ids, sleutels = _gebruikt()
    vrij = [s for s in basisset.lees() if taalcode(s.get("taal")) == "en" and s["id"] not in ids
            and s["sleutel"] not in sleutels]
    import py3langid

    artikelen = [{**s, "tekst": t.artikelbericht(s["tekst"])} for s in vrij
                 if s.get("bron") == "sheffield-trustworthy" and s["helft"] == "toets"
                 and domein(s["sleutel"][2:]) in NIEUWS and py3langid.classify(s["tekst"][:600])[0] == "en"]
    gezondheid = [s for s in vrij if s["soort"] == "tekst" and v.laag_van(s) == "onwaar, oud"
                  and GEZONDHEID.search(s["tekst"]) and not h.BEELDWOORD.search(s["tekst"])
                  and not h.omschrijving(s["tekst"])]
    kanten = {r["id"]: r["kant"] for r in t._jsonl(UIT / "kanten.jsonl")}
    kanten.update(gelezen_kanten())
    politiek = [{**p, "kant": kanten[p["id"]]} for p in kandidaten_politiek() if kanten.get(p["id"]) in ("links", "rechts")]
    fundament = t._jsonl(WORTEL / "data" / "fundament" / "set.jsonl")
    gevraagd = {r["id"] for r in t._jsonl(WORTEL / "data" / "fundament" / "antwoorden.jsonl")}
    feiten = [s for s in fundament if s["id"] not in gevraagd and s["taal"] == "en"]
    return {"artikelen": artikelen, "gezondheid": gezondheid, "politiek": politiek,
            "feit_onwaar": [s for s in feiten if s["label"] == "onwaar"],
            "feit_waar": [s for s in feiten if s["label"] == "waar"]}


KANT_VRAAG = ("Claim: {tekst}\n\nIs this claim typically pushed by the political left, by the political right, or by "
              "neither? Give one short English reason.")
_KANT_SCHEMA = {"type": "object", "properties": {"waarom": {"type": "string"},
                                                 "kant": {"type": "string", "enum": ["links", "rechts", "geen"]}},
                "required": ["waarom", "kant"], "additionalProperties": False}
FEIT_VRAAG = ("News headline and opening:\n{tekst}\n\nChange exactly one verifiable fact (a number, a date, a name or a "
              "place) so that the text becomes false. Keep everything else, including the style. Write in English. Return the "
              "new headline, the new opening, and what you changed.")
KOP_VRAAG = ("Real news headline and opening, as a topic:\n{tekst}\n\nFor a test of a fact-checking tool, write a "
             "different news headline and two sentences on the same topic that a newspaper could plausibly publish "
             "but that are clearly false: they contradict well-documented facts. Do not name private individuals. "
             "Write in English. Return the headline, the opening and why it is false.")
DETAIL_VRAAG = ("Real news headline and opening:\n{tekst}\n\nFor a test of a fact-checking tool, write a short social "
                "media post (one to three sentences) that retells this event with exactly one false detail (a date, a "
                "number, a place or who did it). Everything else must be true. Write in English. Return the post and the "
                "false detail.")
_SCHEMA = {
    "B-feit": {"type": "object", "properties": {"kop": {"type": "string"}, "lead": {"type": "string"},
                                                "veranderd": {"type": "string"}},
               "required": ["kop", "lead", "veranderd"], "additionalProperties": False},
    "B-kop": {"type": "object", "properties": {"kop": {"type": "string"}, "lead": {"type": "string"},
                                               "waarom_onwaar": {"type": "string"}},
              "required": ["kop", "lead", "waarom_onwaar"], "additionalProperties": False},
    "C": {"type": "object", "properties": {"bericht": {"type": "string"}, "vals_detail": {"type": "string"}},
          "required": ["bericht", "vals_detail"], "additionalProperties": False},
}
_VRAAG = {"B-feit": FEIT_VRAAG, "B-kop": KOP_VRAAG, "C": DETAIL_VRAAG}
# Tweede versie, met Sonnet: Haiku weigerde of veranderde niets bij een derde van B-feit en C. Het vervangen
# feit moet letterlijk in de tekst staan, zodat te controleren is dat er echt iets veranderd is.
FEIT_VRAAG_2 = ("News headline and opening:\n{tekst}\n\nFor a test of a fact-checking tool (the test set is never "
                "published), take one concrete fact that is stated word for word in the text above (a number, a date, a "
                "name or a place) and replace it with a wrong value, so that the text becomes false. Keep everything "
                "else exactly the same. Write in English. Return the new headline, the new opening, the original phrase "
                "exactly as it appears in the text, and the phrase you put in its place.")
DETAIL_VRAAG_2 = ("Real news headline and opening:\n{tekst}\n\nFor a test of a fact-checking tool (the test set is never "
                  "published), write a short social media post (one to three sentences, in English) that retells this "
                  "event as ordinary news, but with exactly one detail made false: take one concrete fact that is stated "
                  "word for word in the text above (a date, a number, a place or who did it) and replace it with a wrong "
                  "value. Do not hint that anything is false. Return the post, the original detail exactly as it appears "
                  "in the text, and the false detail as it appears in your post.")
_SCHEMA_2 = {
    "B-feit": {"type": "object", "properties": {"kop": {"type": "string"}, "lead": {"type": "string"},
                                                "origineel": {"type": "string"}, "nieuw": {"type": "string"}},
               "required": ["kop", "lead", "origineel", "nieuw"], "additionalProperties": False},
    "C": {"type": "object", "properties": {"bericht": {"type": "string"}, "origineel": {"type": "string"},
                                           "nieuw": {"type": "string"}},
          "required": ["bericht", "origineel", "nieuw"], "additionalProperties": False},
}
_VRAAG_2 = {"B-feit": FEIT_VRAAG_2, "C": DETAIL_VRAAG_2}


def vervanging_klopt(bron: str, gemaakt: dict) -> bool:
    """Staat het oorspronkelijke stuk in de bron, en het nieuwe in wat gemaakt is, en is het anders?"""
    nieuw = gemaakt.get("bericht") or f"{gemaakt.get('kop', '')} {gemaakt.get('lead', '')}"
    o, n = gemaakt.get("origineel", "").strip(), gemaakt.get("nieuw", "").strip()
    return bool(o) and bool(n) and o != n and o in bron and n in nieuw


def haiku_verzoek(custom_id: str, vraag: str, schema: dict, model: str = "haiku") -> dict:  # pragma: no cover
    from doublecheck.leraar import MODELLEN

    return {"custom_id": custom_id, "params": {"model": MODELLEN[model]["id"], "max_tokens": 2_000,
                                               "messages": [{"role": "user", "content": vraag}],
                                               "output_config": {"effort": "low",
                                                                 "format": {"type": "json_schema", "schema": schema}}}}


def bericht_van(s: dict, gemaakt: dict[str, dict]) -> dict:
    """Kop en begin, of de post, zoals ze in het bericht komen: het artikel zelf of wat Haiku maakte."""
    kop, _, lead = s["tekst"].partition("\n")
    if s["sub"] in ("B-feit", "B-kop"):
        g = gemaakt[s["id"]]
        return {"kop": g["kop"], "lead": g["lead"]}
    if s["sub"] == "C":
        return {"post": gemaakt[s["id"]]["bericht"]}
    return {"kop": kop, "lead": lead}


def invoer(s: dict, gemaakt: dict[str, dict], i: int):  # pragma: no cover - met Pillow
    """(tekst, beeld) zoals een gebruiker het stuurt; screenshots alleen in het geheugen."""
    import io

    from doublecheck import routemeting as rm

    b = bericht_van(s, gemaakt)

    def png(beeld) -> bytes:
        buf = io.BytesIO()
        beeld.save(buf, format="PNG")
        return buf.getvalue()

    if s["vorm"] == "nieuws":
        return None, png(teken_nieuws(s["toon_domein"], b["kop"], b["lead"], s["schrijver"]))
    tekst = b.get("post") or s["tekst"]
    if s["vorm"] == "tiktok":
        return None, png(teken_tiktok(tekst, f"truth.daily{i % 97}"))
    if s["vorm"] == "chat":
        return None, png(rm.teken_chat(tekst, rm.nep_pii(t.PII_SCHUIF + NR_SCHUIF + i)))
    return tekst, None


def maak_set(stukken: list[dict], gemaakt: dict[str, dict]) -> list[dict]:  # pragma: no cover - OCR, model, database
    from doublecheck import routemeting as rm
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    uit = []
    for i, s in enumerate(stukken):
        tekst, beeld = invoer(s, gemaakt, i)
        bericht = bc.bericht_uit(tekst, beeld, config.ocr)
        voorbereid = bc.voorbereiden(conn, config, bericht) if bericht.strip() else \
            {"tekst": bericht, "geheugen": [], "kandidaten": []}
        rij = {**{k: s[k] for k in ("id", "deel", "sub", "vorm", "kant", "verwacht", "helft", "toon_domein",
                                    "schrijver", "sleutel", "zaak")},
               "nr": i, "datum": None, "tekst": voorbereid["tekst"], "geheugen": voorbereid["geheugen"],
               "kandidaten": voorbereid["kandidaten"], "eigen": sorted(v.eigen_cluster(conn, s.get("zaak")))}
        if s["vorm"] == "chat":
            rij["lekken"] = rm.lekken(voorbereid["tekst"], rm.nep_pii(t.PII_SCHUIF + NR_SCHUIF + i))
        uit.append(rij)
        print(f"\r{i + 1}", end="", flush=True)
    t._schrijf(UIT / "set.jsonl", uit)
    return uit


# --- de antwoorden ---------------------------------------------------------------------------

def _tekst(msg) -> str:
    return "".join(getattr(b, "text", "") or "" for b in msg.content)


def kaal_antwoord(msg) -> dict:  # pragma: no cover - op een antwoord van de API
    blokken = [b.model_dump() for b in msg.content]
    tekst = _tekst(msg)
    return {"kleur": lees_kaal(tekst), "bronnen": v.bronnen_uit(blokken, []), "tekst": tekst[-1500:]}


def factiz_uitkomsten(stukken: list[dict], antwoorden: list[dict], tabel: dict) -> dict[str, dict]:
    """Zoals het product: het laatste antwoord, de stand, de vormvraag en de twee regels."""
    uit = t.uitkomsten_van(stukken, antwoorden, tabel)
    vormen = h.vormen_van(antwoorden, uit)
    per_id = {s["id"]: s for s in stukken}
    klaar = {}
    for i, u in uit.items():
        if i not in vormen:
            continue
        na = bc.regels(tabel, u["oordeel"], {"stand": u["stand"], "laag": u["laag"]}, u["feit"], u["bronnen"], vormen[i])
        klaar[i] = {**u, "kleur": na["kleur"], "oordeel_na": na["oordeel"], "regels": na["regels"],
                    "eigen_bewijs": t._eigen_bewijs(per_id[i], u)}
    return klaar


def kale_uitkomsten(antwoorden: list[dict], soort: str) -> dict[str, dict]:
    return {r["id"]: {"kleur": r["kleur"], "bronnen": r["bronnen"], "eigen_bewijs": False}
            for r in antwoorden if r["soort"] == soort}


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in t._jsonl(UIT / "batches.jsonl"))


def _labelbestand() -> dict:
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def afgewezen_bij_lezen() -> set[str]:
    """Wat ik vóór de toets las en afwees (geen gezondheid, geen duidelijke kant, een slechte vervalsing)."""
    return {r["id"] for r in _labelbestand().get("set", []) if r["label"] == "afgewezen"}


def gelezen_kanten() -> dict[str, str]:
    return {r["id"]: r["kant"] for r in _labelbestand().get("kanten", [])}


def lees_labels() -> dict:
    if not LABELS.exists():
        return {}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    return {(r["id"], r["wie"], r["wat"]): r["label"] for r in d.get("oordelen", [])}


# --- de CLI ------------------------------------------------------------------------------

def _dien_in(client, verzoeken: list[dict], geschat: float, stap: str) -> None:  # pragma: no cover
    if not verzoeken:
        raise SystemExit("niets in te dienen")
    if al_uitgegeven() + geschat > BUDGET:
        raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
    batch = client.messages.batches.create(requests=verzoeken)
    with (UIT / "batches.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": batch.id, "stap": stap, "schatting": round(geschat, 3),
                             "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
    print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


def _ophalen(client, verwerk) -> None:  # pragma: no cover - met de Batch API
    alle = t._jsonl(UIT / "batches.jsonl")
    for b in alle:
        if b.get("werkelijk") is not None:
            continue
        if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
            print(f"batch {b['id']} loopt nog")
            continue
        werkelijk = 0.0
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                print(f"{r.custom_id}: {r.result.type}")
                continue
            werkelijk += verwerk(r.custom_id, r.result.message)
        b["werkelijk"] = round(werkelijk, 4)
    t._schrijf(UIT / "batches.jsonl", alle)


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    import anthropic

    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="De gebruikerstoets (PLAN #32.0k)")
    parser.add_argument("stap", choices=("kanten", "kiezen", "genereren", "set", "indienen", "herkansing", "vorm",
                                         "ophalen", "lezen", "tellen"))
    parser.add_argument("sub", nargs="?", default="", help="kanten/genereren: indienen, ophalen of lezen")
    parser.add_argument("--proef", type=int, default=0, help="indienen: per deel de eerste N")
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    config = load_config(None)
    laad_sleutel()
    client = anthropic.Anthropic()

    if args.stap == "kanten":
        if args.sub == "indienen":
            kand = kandidaten_politiek()
            verzoeken = [haiku_verzoek(f"p-{t.batch_id(k['id'])}", KANT_VRAAG.format(tekst=k["tekst"]), _KANT_SCHEMA)
                         for k in kand]
            _dien_in(client, verzoeken, len(verzoeken) * SCHATTING["haiku"], "kanten")
        else:
            per = {t.batch_id(k["id"]): k for k in kandidaten_politiek()}

            def verwerk(cid, msg):
                d = json.loads(_tekst(msg))
                with (UIT / "kanten.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": per[cid[2:]]["id"], **d}, ensure_ascii=False) + "\n")
                return t.kosten_batch(bc.gebruik_uit(msg)) / 10  # Haiku kost ~een tiende van Sonnet

            _ophalen(client, verwerk)
            print(Counter(r["kant"] for r in t._jsonl(UIT / "kanten.jsonl")))
        return
    if args.stap == "kiezen":
        stukken = kies(pools(), afgewezen_bij_lezen())
        t._schrijf(UIT / "keuze.jsonl", stukken)
        print(Counter(s["sub"] for s in stukken))
        return
    stukken = t._jsonl(UIT / "keuze.jsonl")
    if args.stap == "genereren":
        per_id = {s["id"]: s for s in stukken}
        if args.sub == "indienen":
            al = {g["id"] for g in t._jsonl(UIT / "gemaakt.jsonl")}
            verzoeken = [haiku_verzoek(f"g-{t.batch_id(s['id'])}", _VRAAG_2[s["sub"]].format(tekst=s["tekst"]),
                                       _SCHEMA_2[s["sub"]], "sonnet") if s["sub"] in _VRAAG_2 else
                         haiku_verzoek(f"g-{t.batch_id(s['id'])}", _VRAAG[s["sub"]].format(tekst=s["tekst"]),
                                       _SCHEMA[s["sub"]]) for s in stukken if s["sub"] in _VRAAG and s["id"] not in al]
            _dien_in(client, verzoeken, len(verzoeken) * SCHATTING["haiku"] * 10, "genereren")
        elif args.sub == "ophalen":
            per_bid = {t.batch_id(i): i for i in per_id}

            def verwerk(cid, msg):
                try:
                    gemaakt_ = json.loads(_tekst(msg))
                except json.JSONDecodeError:
                    print(f"{cid}: geen geldige JSON ({msg.stop_reason}); opnieuw genereren")
                    return t.kosten_batch(bc.gebruik_uit(msg)) / 10
                with (UIT / "gemaakt.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": per_bid[cid[2:]], **gemaakt_}, ensure_ascii=False) + "\n")
                return t.kosten_batch(bc.gebruik_uit(msg)) / 10

            _ophalen(client, verwerk)
        else:
            for g in t._jsonl(UIT / "gemaakt.jsonl"):
                if g["id"] not in per_id:
                    continue
                s = per_id[g["id"]]
                nieuw = g.get("bericht") or f"{g.get('kop', '')}\n{g.get('lead', '')}"
                vlag = " ONVERANDERD" if s["sub"] == "B-feit" and " ".join(nieuw.split()) == " ".join(s["tekst"].split()) else ""
                if "origineel" in g and not vervanging_klopt(s["tekst"], g):
                    vlag += " VERVANGING-KLOPT-NIET"
                print(f"\n[{g['id']}]{vlag} ORIGINEEL: {s['tekst']}\n  GEMAAKT: {json.dumps(g, ensure_ascii=False)}")
        return
    gemaakt = {g["id"]: g for g in t._jsonl(UIT / "gemaakt.jsonl")}
    if args.stap == "set":
        if any(s["sub"] in _VRAAG and s["id"] not in gemaakt for s in stukken):
            raise Weigering("eerst genereren en ophalen")
        maak_set(stukken, gemaakt)
        return
    stukken = t._jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    per_bid = {t.batch_id(s["id"]): s for s in stukken}
    antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
    tabel = bc.ijktabel(config)
    if args.stap in ("indienen", "herkansing", "vorm"):
        ingediend = {i for b in t._jsonl(UIT / "batches.jsonl") for i in b["ids"]}
        verzoeken, geschat = [], 0.0
        if args.stap == "indienen":
            nog = [s for s in stukken if f"m-{t.batch_id(s['id'])}" not in ingediend]
            if args.proef:
                nog = [s for d in DELEN for s in [x for x in nog if x["deel"] == d][: args.proef]]
            zinnen = bc.feitzinnen()
            for s in nog:
                b = t.batch_id(s["id"])
                verzoeken += [{"custom_id": f"m-{b}", "params": bc.machineverzoek(s["tekst"], s["geheugen"], None, config)},
                              {"custom_id": f"k-{b}", "params": kaal_verzoek(s["tekst"], True, config)},
                              {"custom_id": f"z-{b}", "params": kaal_verzoek(s["tekst"], False, config)}]
                geschat += SCHATTING["factiz"] + SCHATTING["kaal"] + SCHATTING["zonder"]
                for k in ("A", "B") if s["kandidaten"] else ():
                    params, _ = bc.feitverzoek(s["tekst"], s["kandidaten"], k, zinnen, config)
                    verzoeken.append({"custom_id": f"f-{b}__{k}", "params": params})
                    geschat += SCHATTING["feit"]
        elif args.stap == "herkansing":
            zin = bc.HERKANSING[config.berichtcontrole.herkansing]
            for r in antwoorden:
                if r["soort"] == "machine" and bc.herkansing_nodig(r) and f"h-{t.batch_id(r['id'])}" not in ingediend:
                    s = per_id[r["id"]]
                    verzoeken.append({"custom_id": f"h-{t.batch_id(s['id'])}", "params": bc.met_herkansing(
                        bc.machineverzoek(s["tekst"], s["geheugen"], None, config), zin)})
                    geschat += SCHATTING["herkansing"]
        else:
            verzoeken = h.vormvragen(stukken, t.uitkomsten_van(stukken, antwoorden, tabel), config, ingediend)
            geschat = len(verzoeken) * SCHATTING["vorm"]
        _dien_in(client, verzoeken, geschat, args.stap)
        return
    if args.stap == "ophalen":
        klaar = {(r["soort"], r["id"], r.get("sleutel")) for r in antwoorden}
        zinnen = bc.feitzinnen()

        def verwerk(cid, msg):
            kort, rest = cid.split("-", 1)
            if kort == "f":
                stuk, sleutel = rest.rsplit("__", 1)
                s = per_bid[stuk]
                rij = {"soort": "feit", "id": s["id"], "sleutel": sleutel,
                       **bc.feitantwoord(msg, bc.feitverzoek(s["tekst"], s["kandidaten"], sleutel, zinnen, config)[1])}
            elif kort == "v":
                tekst = _tekst(msg)
                rij = {"soort": "vorm", "id": per_bid[rest]["id"], "sleutel": None, **bc.lees_vorm(tekst),
                       "waarom": h._waarom(tekst)}
            elif kort in ("k", "z"):
                rij = {"soort": "kaal" if kort == "k" else "zonder", "id": per_bid[rest]["id"], "sleutel": None,
                       **kaal_antwoord(msg)}
            else:
                s = per_bid[rest]
                rij = {"soort": "machine" if kort == "m" else "herkansing", "id": s["id"], "sleutel": None,
                       **bc.machineantwoord(msg, s["geheugen"])}
            rij["kosten"] = round(t.kosten_batch(bc.gebruik_uit(msg)), 5)
            if (rij["soort"], rij["id"], rij.get("sleutel")) not in klaar:
                with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            return rij["kosten"]

        _ophalen(client, verwerk)
        antwoorden = t._jsonl(UIT / "antwoorden.jsonl")
        print(Counter((per_id[r["id"]]["deel"], r["soort"]) for r in antwoorden),
              f"\nherkansing nodig: {sum(bc.herkansing_nodig(r) for r in antwoorden if r['soort'] == 'machine')}",
              f"\nuitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    factiz = factiz_uitkomsten(stukken, antwoorden, tabel)
    kaal, zonder = kale_uitkomsten(antwoorden, "kaal"), kale_uitkomsten(antwoorden, "zonder")
    labels = lees_labels()
    if args.stap == "tellen":
        uit = telling(stukken, factiz, kaal, zonder, labels)
        uit["maskeren"] = dict(Counter(k for s in stukken if "lekken" in s for k, w in s["lekken"].items() if w))
        print(json.dumps(uit, ensure_ascii=False, indent=1))
        print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    _lees(stukken, factiz, kaal, labels)


def _lees(stukken, factiz, kaal, labels) -> None:  # pragma: no cover
    for s in stukken:
        i = s["id"]
        f, k = factiz.get(i), kaal.get(i)
        if f is None or k is None:
            continue
        te_lezen = []
        for wie, u in (("factiz", f), ("kaal", k)):
            if s["deel"] == "A" and u["kleur"] == "rood" and (i, wie, "rood") not in labels:
                te_lezen.append(f"{wie} ROOD: vals of set fout?")
            if s["deel"] == "C" and u["kleur"] == "groen" and (i, wie, "groen") not in labels:
                te_lezen.append(f"{wie} GROEN: vals of set fout?")
        if s["deel"] == "D" and f["kleur"] == "rood" and not f["eigen_bewijs"] and f["bronnen"] \
                and (i, "factiz", "bewijs") not in labels:
            te_lezen.append("factiz ROOD: bewijst, bewijst via factcheck, bewijst niet, set fout?")
        if te_lezen:
            print(f"\n[{i} · {s['sub']} · {s['vorm']}] {' | '.join(te_lezen)}\n  BERICHT: {s['tekst'][:400]}"
                  f"\n  FACTIZ: {f.get('oordeel')} → {f.get('kleur')}; {f.get('bewering')}\n  UITLEG: {f.get('uitleg')}"
                  f"\n  KAAL: {k['kleur']}")
            for b in f["bronnen"][:3]:
                print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:250]}")


if __name__ == "__main__":
    main()
