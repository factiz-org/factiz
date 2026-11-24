"""De route zoals in het product, op echte screenshots (B43, PLAN #31.10).

Het beeld blijft lokaal: OCR per schrift, opknippen en maskeren
(`opknippen`), de vingerafdruk, het geheugen en de kandidaten van de
feitenstap. Naar het model gaat alleen de gemaskeerde bewering: de vastgezette
machine (vraag v4, het geheugen en webzoeken, zoals ronde 7 a) en
`feitstap-v3` met twee sleutels. De meter geeft de stand (stand 0 dicht).

De set, vooraf vastgelegd (PLAN #31.10), Engels, 750 berichten:
- S-onwaar: 150 echte screenshots met tekst uit M4FC (de OCR leest minstens
  60 letters), het bericht is alleen het beeld;
- B-onwaar: 100 echte foto's uit M4FC (hoogstens 15 letters), met de claim van
  M4FC als doorgestuurde tekst;
- B-paar: de 100 beelden van ronde 5, nu zonder dat het model ze ziet;
- S-waar: 300 ware checks, als chatbericht getekend met nep-persoonsgegevens;
- S-stilte: 100 tiplineberichten zonder bewering, in hetzelfde kader.
Een M4FC-beeld waarvan de OCR een stempel of de naam van een redactie leest,
doet niet mee: het model ziet het beeld niet, maar wel die tekst.

Beelden worden nooit gekopieerd of bewaard (B35, DR3): de M4FC-beelden staan
al op schijf, de chatberichten bestaan alleen in het geheugen. De ruwe
OCR-tekst van de handsteekproef gaat weg met `opruimen`. Alleen openbaar
materiaal gaat naar het model, dus de Batch API mag (offline, B43).

    python -m doublecheck.hittewacht -- python -m doublecheck.routemeting set
    python -m doublecheck.routemeting indienen [--proef 10]|ophalen|live|lezen [--masker]|tellen|opruimen
"""

from __future__ import annotations

import json
import math
import random
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "route"
LABELS = WORTEL / "docs" / "steekproeven" / "31.10-route.json"
BUDGET = 15.0  # PO 2026-10-26: "grens $15"
LAT_ROUTE = 20.0  # PO 2026-10-26: "met p95 hoogstens 20 seconden als lat voor de hele route"
LAT_LOKAAL = 3.0  # B41: /resolve p95 onder 3 seconden
ZAAD = 3110
DELEN = {"S-onwaar": 150, "B-onwaar": 100, "B-paar": 100, "S-waar": 300, "S-stilte": 100}
KORT = {"S-onwaar": "so", "B-onwaar": "bo", "B-paar": "bp", "S-waar": "sw", "S-stilte": "ss"}
MIN_LETTERS_S, MAX_LETTERS_B = 60, 15
N_LIVE = 20  # per deel, voor de wachttijd
N_MASKER = 50  # echte screenshots, met de hand nagelezen
MAX_TEKENS = 1_000
VERSIE = "verificatie-v4"
OMSTANDIGHEID = "a"  # het geheugen en webzoeken, zonder blokkade: zoals in het product
SCHATTING = {"machine": 0.012, "feit": 0.0015}  # per verzoek via de Batch API, ruim (§150: $0,0065; §154: $0,0012)
LIVE_PRIJS = (2.0, 10.0)  # Sonnet 5.5 zonder batchkorting, dollar per miljoen tokens in en uit
DATUM_STILTE = "2019–2021 (exact date unknown)"  # zoals ronde 6

VERRAAD = re.compile(
    r"\b(false|fake|misleading|fact[\s-]?check\w*|hoax|debunk\w*|fabricated|not true|misinformation|disinformation"
    r"|doctored|photoshopped|morphed|missing context|altered|satire|factly|fatabyyano|pesa\s?check|snopes"
    r"|india\s?today|lead\s?stories|poligrafo|congo\s?check|la\s?republica|correctiv|dfrac|knack|myth\s?detector"
    r"|dubawa|you\s?turn|dogrula|211check|verify-sy|tjek\s?det|factchecker|boom\s?live|newschecker|vishvas|afp"
    r"|reuters)\b", re.I)
NAMEN = ("Marieke Hoogenboom", "Tariq Bensaid", "Lotte van Dijk", "Priya Raghunathan", "Owen Gallagher",
         "Sofia Marchetti", "Daniel Okonkwo", "Hannah Lindqvist", "Ravi Chandrasekar", "Emma Whitfield",
         "Joost Verbruggen", "Amira Haddad", "Lucas Ferreira", "Grace Mbeki", "Pieter de Wolff", "Nadia Kowalczyk")
VOORNAMEN = ("Anna", "Mark", "Fatima", "Tom", "Ines", "Kofi")
GROEPEN = ("Buurtapp Westwijk", "Family Chat", "Parents Class 4B", "Football Dads", "Church Choir Updates",
           "Old Classmates 1998", "Neighbours Elm Street", "Running Club Sunday")


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


# --- de regels die vóór de meting vastlagen -------------------------------------------

def letters(tekst: str) -> int:
    return sum(unicodedata.category(c)[0] in "LM" for c in tekst)


def soort_van(ocr: str) -> str | None:
    """S (screenshot met tekst), B (foto) of niets: wat ertussen valt doet niet mee."""
    n = letters(ocr)
    return "S" if n >= MIN_LETTERS_S else "B" if n <= MAX_LETTERS_B else None


def verraadt(ocr: str) -> bool:
    """Een stempel, een oordeel of de naam van een redactie in de tekst van het beeld."""
    return bool(VERRAAD.search(ocr))


def bericht(deel: str, gemaskeerd: str, bijschrift: str | None) -> str:
    """Wat het model krijgt: bij een screenshot de gemaskeerde tekst, bij een foto
    het bijschrift en, als de OCR iets leest, die tekst erbij."""
    if deel.startswith("S"):
        return gemaskeerd
    beeldtekst = " ".join(gemaskeerd.split())
    return bijschrift + (f"\n[Text in the attached image: {beeldtekst}]" if beeldtekst else "")


def nep_pii(i: int) -> dict:
    """Nep-persoonsgegevens voor het i-de getekende bericht, vast per zaad: de
    afzender met nummer, de groep, de tijd, en in de helft van de berichten een
    regel met een nummer, een adres of een handle in de tekst zelf."""
    rng = random.Random(ZAAD * 1_000 + i)

    def cijfers(n: int) -> str:
        return "".join(str(rng.randrange(10)) for _ in range(n))

    def nummer() -> str:
        return (f"+31 6 {cijfers(4)} {cijfers(4)}", f"+44 7700 900{cijfers(3)}", f"06-{cijfers(8)}",
                f"+1 (555) {cijfers(3)}-{cijfers(4)}")[rng.randrange(4)]

    pii = {"naam": rng.choice(NAMEN), "telefoon": nummer(), "groep": rng.choice(GROEPEN),
           "leden": rng.randrange(5, 60), "tijd": f"{rng.randrange(7, 23):02d}:{rng.randrange(60):02d}"}
    soort = rng.randrange(6)
    if soort == 0:
        pii["regel_telefoon"] = nummer()
        pii["regel"] = f"Questions? Call {rng.choice(VOORNAMEN)} on {pii['regel_telefoon']}"
    elif soort == 1:
        voor, achter = rng.choice(NAMEN).split(" ", 1)
        pii["regel_email"] = f"{voor.lower()}.{achter.replace(' ', '').lower()}{cijfers(2)}@gmail.com"
        pii["regel"] = f"Mail {pii['regel_email']} for the full report"
    elif soort == 2:
        pii["regel_handle"] = f"@{rng.choice(VOORNAMEN).lower()}_{cijfers(3)}"
        pii["regel"] = f"Follow {pii['regel_handle']} for more"
    return pii


def _cijfers(tekst: str) -> str:
    return re.sub(r"\D", "", tekst)


def lekken(tekst: str, pii: dict) -> dict[str, bool]:
    """Welke nep-persoonsgegevens na het maskeren nog in de tekst staan."""
    plat, laag = _cijfers(tekst), tekst.casefold()
    nummers = [pii[k] for k in ("telefoon", "regel_telefoon") if pii.get(k)]
    return {"telefoon": any(_cijfers(n)[-7:] in plat for n in nummers),
            "e-mail": bool(pii.get("regel_email")) and pii["regel_email"].split("@")[0].casefold() in laag,
            "handle": bool(pii.get("regel_handle")) and pii["regel_handle"].lstrip("@").casefold() in laag,
            "naam": pii["naam"].split()[-1].casefold() in laag,
            "groep": pii["groep"].casefold() in laag}


def p95(waarden: list[float]) -> float:
    rij = sorted(waarden)
    return rij[max(0, math.ceil(0.95 * len(rij)) - 1)]


# --- tellen ----------------------------------------------------------------------------

def _label(labels: dict, sleutel: tuple) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def telling(stukken: list[dict], antwoorden: dict[str, dict], standen: dict[str, dict], labels: dict,
            lekdata: dict[str, dict] | None = None, masker: list[dict] | None = None,
            tijden: list[dict] | None = None) -> dict:
    """Per deel de oordelen en wat ze waard zijn, en de latten van PLAN #31.10.
    Een *klopt niet* bij een onwaar bericht dat een check uit zijn eigen cluster
    aanhaalt, is bewezen (vaste regel); elke andere *klopt niet*, *let op* of
    *klopt* die telt, en elke 10, heeft een label nodig. Weigert zolang er een
    ontbreekt."""
    uit: dict = {}
    verkeerde_10 = 0
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        o = a["oordeel"]
        d = uit.setdefault(s["deel"], {"n": 0, "oordelen": Counter(), "bewezen": 0, "klopt niet zonder bewijs": 0,
                                       "let op terecht": 0, "klopt vals": 0, "klopt, beeld nodig": 0,
                                       "valse vlaggen": 0, "op 10": 0, "set fout": 0})
        d["n"] += 1
        d["oordelen"][o] += 1
        st = standen.get(s["id"]) or {}
        if st.get("stand") == 10:
            d["op 10"] += 1
            verkeerde_10 += _label(labels, (s["id"], 10, st.get("feit"))) == "fout"
        if s["label"] == "onwaar":
            if o == "klopt niet":
                eigen = set(s.get("eigen") or ())
                if any(b.get("soort") == "geheugen" and b.get("claim") in eigen for b in a["bronnen"]):
                    d["bewezen"] += 1
                elif a["bronnen"] and _label(labels, (s["id"], o)) == "bewijst":
                    d["bewezen"] += 1
                else:
                    d["klopt niet zonder bewijs"] += 1
            elif o == "let op":
                d["let op terecht"] += _label(labels, (s["id"], o)) == "terecht"
            elif o == "klopt":  # "beeld nodig": de tekst klopt, de onwaarheid zit in het beeld dat lokaal blijft
                label = _label(labels, (s["id"], o))
                d[{"vals": "klopt vals", "beeld nodig": "klopt, beeld nodig"}.get(label, "set fout")] += 1
        elif o in ("klopt niet", "let op") or (s["label"] == "geen bewering" and o == "klopt"):
            label = _label(labels, (s["id"], o))
            if label == "vals":
                sleutel = "valse vlaggen" if o == "klopt niet" else f"{o} vals"
                d[sleutel] = d.get(sleutel, 0) + 1
            elif label == "set fout":
                d["set fout"] += 1

    def aandeel(deel: str, *velden: str) -> float | None:
        d = uit.get(deel)
        return sum(d[v] for v in velden) / d["n"] if d and d["n"] else None

    def lat(waarde: float | None, grens: float, deel: str) -> bool | None:
        d = uit.get(deel, {})
        return None if waarde is None else waarde >= grens and d["klopt vals"] + d["klopt, beeld nodig"] <= 2

    latten = {
        "ware berichten nooit klopt niet": all(uit[d]["valse vlaggen"] == 0 for d in ("S-waar", "B-paar") if d in uit),
        "geen verkeerde 10": verkeerde_10 == 0,
        "S-onwaar bewezen ≥ 80%": lat(aandeel("S-onwaar", "bewezen"), 0.80, "S-onwaar"),
        "B-onwaar gewaarschuwd ≥ 80%": lat(aandeel("B-onwaar", "bewezen", "let op terecht"), 0.80, "B-onwaar"),
        "stilte nooit klopt niet": (uit["S-stilte"]["valse vlaggen"] == 0) if "S-stilte" in uit else None,
    }
    if lekdata:
        n = len(lekdata)
        tel = Counter(k for lek in lekdata.values() for k, v in lek.items() if v)
        namen_weg = 1 - (tel["naam"] + tel["groep"]) / (2 * n)
        uit["maskeren, gerenderd"] = {"n": n, **dict(tel), "namen weg": round(namen_weg, 4)}
        latten["geen nummer, adres of handle gelekt (gerenderd)"] = tel["telefoon"] + tel["e-mail"] + tel["handle"] == 0
        latten["namen uit de chatomgeving ≥ 95% weg"] = namen_weg >= 0.95
    if masker:
        lek = sum(m.get("telefoon", 0) + m.get("e-mail", 0) for m in masker)
        uit["maskeren, echte screenshots"] = {"n": len(masker), "telefoon of e-mail gelekt": lek}
        latten["geen nummer of adres gelekt (echte screenshots)"] = lek == 0
    if tijden:
        lokaal, route = p95([t["lokaal"] for t in tijden]), p95([t["route"] for t in tijden])
        uit["wachttijd"] = {"n": len(tijden), "p95 lokaal": round(lokaal, 2), "p95 route": round(route, 2),
                            "p50 route": round(sorted(t["route"] for t in tijden)[len(tijden) // 2], 2)}
        latten["p95 lokaal ≤ 3 s"] = lokaal <= LAT_LOKAAL
        latten["p95 route ≤ 20 s"] = route <= LAT_ROUTE
    for d in uit.values():
        if "oordelen" in d:
            d["oordelen"] = dict(d["oordelen"])
    uit["latten"] = latten
    return uit


# --- de set: kiezen, tekenen, lezen ----------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in Path(pad).read_text(encoding="utf-8").splitlines() if x.strip()] \
        if Path(pad).exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")


def _gebruikte_sleutels() -> set[str]:  # pragma: no cover - op de rondes
    from doublecheck import verificatie as v

    gebruikt = {s.get("sleutel") for r in (1, 2, 3, 5) for s in v.gekozen_stukken(r)}
    _, kandidaten = v.kandidaten_ronde5()
    return gebruikt | {s["sleutel"] for s in kandidaten}


def beeldkandidaten() -> list[dict]:  # pragma: no cover - op de basisset en M4FC
    """Onware Engelse M4FC-beelden, nooit gebruikt: eerst de toetshelft, dan de
    ontwikkelhelft, elk willekeurig met een vast zaad."""
    from doublecheck import basisset, beeldzoeken
    from doublecheck.leerstof import taalcode

    m4fc = json.loads(beeldzoeken.M4FC_JSON.read_text(encoding="utf-8"))
    gebruikt = _gebruikte_sleutels()
    uit = []
    for helft in ("toets", "ontwikkel"):
        groep = sorted((s for s in basisset.lees() if s["soort"] == "beeld" and s["label"] == "onwaar"
                        and s["helft"] == helft and taalcode(s.get("taal")) == "en" and s["sleutel"] not in gebruikt),
                       key=lambda s: s["id"])
        random.Random(ZAAD).shuffle(groep)
        for s in groep:
            x = m4fc[int(s["sleutel"].split(":")[1])]
            uit.append({**s, "bijschrift": x["claim"], "datum": (x.get("fc_pub_date") or "")[:10] or s.get("datum")})
    return uit


def ware_checks(n: int = DELEN["S-waar"]) -> list[dict]:  # pragma: no cover - op de basisset
    """Ware Engelse checks die nooit gebruikt zijn: de toetshelft eerst, de rest
    uit de ontwikkelhelft, willekeurig met een vast zaad."""
    from doublecheck import basisset
    from doublecheck import verificatie as v
    from doublecheck.leerstof import taalcode

    gebruikt = {s["id"] for r in (1, 2, 7) for s in v.gekozen_stukken(r)}
    uit = []
    for helft in ("toets", "ontwikkel"):
        groep = sorted((s for s in basisset.lees() if s["soort"] == "tekst" and v.laag_van(s) == "ware check"
                        and s["helft"] == helft and taalcode(s.get("taal")) == "en" and s["id"] not in gebruikt),
                       key=lambda s: s["id"])
        uit += random.Random(ZAAD + 1).sample(groep, min(len(groep), n - len(uit)))
    return uit


def stilteberichten(n: int = DELEN["S-stilte"]) -> list[dict]:  # pragma: no cover - op de tiplineset
    """Engelse berichten van sociale media zonder bewering (meerderheid *No*),
    buiten de steekproef van ronde 6."""
    import csv

    from doublecheck import verificatie as v

    with v.TIPLINES.open(encoding="utf-8") as f:
        rijen = list(csv.DictReader(f))
    gebruikt = {s["sleutel"] for s in v.gekozen_stukken(6)}
    groep = [i for i, r in enumerate(rijen) if r["language"] == "en" and r["source"] == "social media"
             and r["majority_label"] == "No" and f"tipline:{i:05d}" not in gebruikt and r["text"].strip()]
    return [{"sleutel": f"tipline:{i:05d}", "tekst": rijen[i]["text"]} for i in
            sorted(random.Random(ZAAD + 2).sample(groep, n))]


def _breek(tekst: str, lettertype, breedte: int) -> list[str]:  # pragma: no cover - met Pillow
    regels: list[str] = []
    for alinea in tekst.splitlines() or [""]:
        regel = ""
        for woord in alinea.split():
            proef = f"{regel} {woord}".strip()
            if regel and lettertype.getlength(proef) > breedte:
                regels.append(regel)
                regel = woord
            else:
                regel = proef
        regels.append(regel)
    return [r for r in regels if r]


def teken_chat(tekst: str, pii: dict):  # pragma: no cover - met Pillow
    """Een doorgestuurd bericht in een groepsapp: statusbalk, de kop van de
    groep, de afzender met nummer, "Forwarded many times", de tekst, de tijd en
    de invoerbalk. Bestaat alleen in het geheugen."""
    from PIL import Image, ImageDraw, ImageFont

    pad = next(p for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(p).exists())
    groot, klein = ImageFont.truetype(pad, 30), ImageFont.truetype(pad, 24)
    breed = 900
    regels = _breek(tekst[:MAX_TEKENS], groot, breed - 150) + (_breek(pii["regel"], groot, breed - 150)
                                                              if pii.get("regel") else [])
    ballon = 110 + 42 * len(regels) + 50
    beeld = Image.new("RGB", (breed, 190 + ballon + 130), (236, 229, 221))
    t = ImageDraw.Draw(beeld)
    t.rectangle([0, 0, breed, 150], fill=(7, 94, 84))
    t.text((24, 12), "9:41", font=klein, fill="white")
    t.text((breed - 130, 12), "LTE 87%", font=klein, fill="white")
    t.text((24, 62), pii["groep"], font=groot, fill="white")
    t.text((24, 104), f"{pii['leden']} participants", font=klein, fill=(215, 230, 228))
    y = 180
    t.rounded_rectangle([40, y, breed - 60, y + ballon], radius=18, fill="white")
    t.text((64, y + 16), f"~ {pii['naam']}  {pii['telefoon']}", font=klein, fill=(53, 120, 190))
    t.text((64, y + 52), "Forwarded many times", font=klein, fill=(130, 130, 130))
    y2 = y + 96
    for regel in regels:
        t.text((64, y2), regel, font=groot, fill=(20, 20, 20))
        y2 += 42
    t.text((breed - 160, y2 + 6), pii["tijd"], font=klein, fill=(130, 130, 130))
    t.rounded_rectangle([20, beeld.height - 90, breed - 20, beeld.height - 30], radius=30, fill="white")
    t.text((50, beeld.height - 76), "Type a message", font=klein, fill=(150, 150, 150))
    return beeld


def maak_set() -> list[dict]:  # pragma: no cover - met de OCR, het model en de database
    """Alle 750 berichten door het lokale deel van de route, elk gemeten zoals
    in de dienst (het model al geladen). Schrijft `set.jsonl`, en de ruwe OCR
    van de handsteekproef in `ruw.jsonl` (weg met `opruimen`)."""
    import difflib
    import io
    import sqlite3

    from doublecheck import feitstap
    from doublecheck import verificatie as v
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.ocr import extract_text
    from doublecheck.opknippen import knip, maskeer
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    config = load_config(None)
    versie = config.model_versions.text_embedding
    conn = connect("doublecheck.db")
    lees = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    lees.row_factory = sqlite3.Row
    index, _ = feitstap._index()
    fingerprint_texts(["warm"], versie)  # het model is in de dienst al geladen
    vloer = feitstap.VERSIES["v3"]["vloer"]

    def lokaal(deel: str, nr: int, beeld, bijschrift: str | None, extra: dict) -> dict:
        tijden = {}
        begin = time.perf_counter()
        ruw = extract_text(beeld, config.ocr).text
        tijden["ocr"] = time.perf_counter() - begin
        t0 = time.perf_counter()
        gemaskeerd = maskeer(knip(ruw))
        tijden["opknippen"] = time.perf_counter() - t0
        tekst = bericht(deel, gemaskeerd, bijschrift)
        t0 = time.perf_counter()
        fp = fingerprint_texts([tekst[:600]], versie)[0]
        tijden["vingerafdruk"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        lijst = search_texts(conn, [fp], 8, varianten=True)[0]
        tijden["geheugen"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        kand = [[f, round(g, 4)] for f, g in feitstap.kandidaten(fp.vector, index, vloer)]
        tijden["kandidaten"] = time.perf_counter() - t0
        tijden["lokaal"] = time.perf_counter() - begin
        s = {"id": f"{KORT[deel]}-{nr:03d}", "deel": deel, "soort": "tekst", "tekst": tekst,
             "geheugen": v.kandidaten_uit(lees, lijst), "kandidaten": kand,
             "tijden": {k: round(w, 4) for k, w in tijden.items()}, **extra}
        s["eigen"] = sorted(v.eigen_cluster(lees, s.get("zaak")))
        return s, ruw

    stukken, ruw_rijen = [], []
    # S-onwaar en B-onwaar: echte M4FC-beelden, de OCR beslist.
    n = {"S": 0, "B": 0}
    nodig = {"S": DELEN["S-onwaar"], "B": DELEN["B-onwaar"]}
    for kandidaat in beeldkandidaten():
        if n["S"] >= nodig["S"] and n["B"] >= nodig["B"]:
            break
        data = Path(kandidaat["beeld"]).read_bytes()
        voorlezing = extract_text(data, config.ocr).text
        soort = soort_van(voorlezing)
        if soort is None or verraadt(voorlezing) or n[soort] >= nodig[soort]:
            continue
        deel = "S-onwaar" if soort == "S" else "B-onwaar"
        extra = {"label": "onwaar", "sleutel": kandidaat["sleutel"], "zaak": kandidaat.get("zaak"),
                 "datum": kandidaat.get("datum"), "helft": kandidaat["helft"]}
        s, ruw = lokaal(deel, n[soort], data, kandidaat["bijschrift"] if soort == "B" else None, extra)
        stukken.append(s)
        if soort == "S":
            ruw_rijen.append({"id": s["id"], "ruw": ruw})
        n[soort] += 1
        print(f"\r{n}", end="", flush=True)
    # B-paar: de beelden van ronde 5, met hun bijschrift.
    for i, r5 in enumerate(v.gekozen_stukken(5)):
        extra = {"label": r5["label"], "sleutel": r5["sleutel"], "zaak": r5.get("zaak"), "datum": r5.get("datum"),
                 "ronde5": r5["id"]}
        s, _ = lokaal("B-paar", i, Path(r5["beeld"]).read_bytes(), r5["tekst"], extra)
        stukken.append(s)
    # S-waar en S-stilte: getekend met nep-persoonsgegevens, alleen in het geheugen.
    for deel, bron in (("S-waar", ware_checks()), ("S-stilte", stilteberichten())):
        for i, x in enumerate(bron):
            pii = nep_pii(len(stukken))
            plaat = teken_chat(x["tekst"], pii)
            buf = io.BytesIO()
            plaat.save(buf, format="PNG")
            extra = {"label": "waar" if deel == "S-waar" else "geen bewering", "sleutel": x["sleutel"],
                     "zaak": x.get("zaak"), "datum": x.get("datum") if deel == "S-waar" else DATUM_STILTE,
                     "helft": x.get("helft"), "pii": pii}
            s, ruw = lokaal(deel, i, buf.getvalue(), None, extra)
            s["lekken"] = lekken(s["tekst"], pii)
            s["ocr gelijkenis"] = round(difflib.SequenceMatcher(
                None, " ".join(x["tekst"][:MAX_TEKENS].split()), " ".join(knip(ruw).split())).ratio(), 4)
            stukken.append(s)
    hand = sorted(random.Random(ZAAD + 3).sample([r["id"] for r in ruw_rijen], N_MASKER))
    _schrijf(UIT / "set.jsonl", stukken)
    _schrijf(UIT / "ruw.jsonl", [r for r in ruw_rijen if r["id"] in hand])
    return stukken


# --- de vragen ---------------------------------------------------------------------------

def _machineverzoek(s: dict) -> dict:  # pragma: no cover - vorm van de API
    from doublecheck import verificatie as v

    g = {"kandidaten": s["geheugen"], "eigen": []}
    return v.verzoek(s, v.geheugen_voor(OMSTANDIGHEID, g), OMSTANDIGHEID, [], "sonnet", VERSIE)


def _feitverzoek(s: dict, sleutel: str) -> dict:  # pragma: no cover - vorm van de API
    from doublecheck import feitstap as f

    v3 = f.VERSIES["v3"]
    zin = f.zinnen_van_feiten()
    tekst = f.vraag(s["tekst"], [(x, zin[x]) for x in f.volgorde(s["kandidaten"], sleutel)],
                    v3["vraag_b"] if sleutel == "B" else v3["vraag"])
    return f._verzoek(f.verzoek_id(s["id"], sleutel), "sonnet", f.SYSTEEM, tekst, f._SCHEMA, 500)


def _machineantwoord(s: dict, msg, prijs: tuple[float, float]) -> dict:  # pragma: no cover - vorm van de API
    from doublecheck import verificatie as v

    blokken = [b.model_dump() for b in msg.content]
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    oordeel, bewering, uitleg = v.lees_antwoord(tekst)
    zoek = getattr(msg.usage.server_tool_use, "web_search_requests", 0) if msg.usage.server_tool_use else 0
    kosten = (msg.usage.input_tokens * prijs[0] + msg.usage.output_tokens * prijs[1]) / 1e6 \
        + zoek * v.ZOEKEN_PER_1000 / 1000
    return {"id": s["id"], "oordeel": oordeel, "bewering": bewering, "uitleg": uitleg,
            "bronnen": v.bronnen_uit(blokken, v.geheugen_voor(OMSTANDIGHEID, {"kandidaten": s["geheugen"]})),
            "zoekverzoeken": zoek, "kosten": round(kosten, 5), "stop": msg.stop_reason}


def _feitantwoord(s: dict, sleutel: str, msg, prijs: tuple[float, float]) -> dict:  # pragma: no cover
    from doublecheck import feitstap as f

    tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
    feiten = f.volgorde(s["kandidaten"], sleutel)
    richting, nummer = f.lees_feitoordeel(tekst, len(feiten))
    kosten = (msg.usage.input_tokens * prijs[0] + msg.usage.output_tokens * prijs[1]) / 1e6
    return {"id": s["id"], "sleutel": sleutel, "richting": richting, "feit": feiten[nummer - 1] if nummer else None,
            "kosten": round(kosten, 5)}


def al_uitgegeven() -> float:
    """Van een afgeronde batch het werkelijke bedrag, van een lopende de schatting, en de live vragen."""
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
               for b in _jsonl(UIT / "batches.jsonl")) + sum(r.get("kosten", 0) for r in _jsonl(UIT / "live.jsonl"))


def standen_van(stukken: list[dict], machine: dict[str, dict], feit: list[dict]) -> dict[str, dict]:
    """De stand op de meter per bericht: twee sleutels voor de feitenbasis, anders
    de gemeten stand bij het oordeel en de laag van de bron (stand 0 dicht)."""
    from doublecheck import feitstap as f
    from doublecheck import meter

    tabel = {(k["oordeel"], k["laag"]): k for k in json.loads(meter.UIT.read_text(encoding="utf-8"))["klassen"]}
    per = {k: {r["id"]: r for r in feit if r["sleutel"] == k} for k in f.SLEUTELS}
    geen = {"richting": "geen", "feit": None}
    uit = {}
    for s in stukken:
        a = machine.get(s["id"])
        if a is None:
            continue
        x, y = per["A"].get(s["id"], geen), per["B"].get(s["id"], geen)
        twee = f.twee_sleutels({s["id"]: x}, {s["id"]: y})[s["id"]]
        feitstand = {"bevestigt": "waar", "spreekt tegen": "onwaar"}.get(twee["richting"])
        m = meter.meterstand(tabel, a["oordeel"], meter.laag_van_antwoord(a["bronnen"]), feitstand)
        uit[s["id"]] = {"stand": m["stand"], "woorden": m["woorden"], "laag": m["laag"],
                        "feit": twee["feit"] if m["stand"] == 10 else None}
    return uit


def lees_labels() -> tuple[dict, list[dict]]:
    """(labels per uitkomst, de handsteekproef van het maskeren)."""
    if not LABELS.exists():
        return {}, []
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {}
    for r in d.get("oordelen", []):
        sleutel = (r["id"], r["oordeel"]) if r["oordeel"] != 10 else (r["id"], 10, r.get("feit"))
        labels[sleutel] = r["label"]
    return labels, d.get("masker", [])


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="De route op echte screenshots (B43, PLAN #31.10)")
    parser.add_argument("stap", choices=("set", "indienen", "ophalen", "live", "lezen", "tellen", "opruimen"))
    parser.add_argument("--proef", type=int, default=0, help="indienen: per deel de eerste N")
    parser.add_argument("--masker", action="store_true", help="lezen: de handsteekproef van het maskeren")
    args = parser.parse_args()
    if args.stap == "set":
        stukken = maak_set()
        print("\n", Counter(s["deel"] for s in stukken))
        return
    stukken = _jsonl(UIT / "set.jsonl")
    per_id = {s["id"]: s for s in stukken}
    machine = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
    feit = _jsonl(UIT / "feit-antwoorden.jsonl")
    if args.stap == "opruimen":
        (UIT / "ruw.jsonl").unlink(missing_ok=True)
        print("ruwe OCR van de handsteekproef verwijderd")
        return
    if args.stap in ("lezen", "tellen"):
        labels, masker = lees_labels()
        standen = standen_van(stukken, machine, feit)
        if args.stap == "tellen":
            live = _jsonl(UIT / "live.jsonl")
            lekdata = {s["id"]: s["lekken"] for s in stukken if "lekken" in s}
            print(json.dumps(telling(stukken, machine, standen, labels, lekdata, masker, live or None),
                             ensure_ascii=False, indent=1))
            print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
            return
        if args.masker:
            for r in _jsonl(UIT / "ruw.jsonl"):
                print(f"\n[{r['id']}] RUW:\n{r['ruw']}\n  NAAR HET MODEL:\n{per_id[r['id']]['tekst']}")
            return
        from doublecheck.feitstap import zinnen_van_feiten

        zin = zinnen_van_feiten()
        for s in stukken:
            a, st = machine.get(s["id"]), standen.get(s["id"], {})
            if a is None:
                continue
            o = a["oordeel"]
            te_lezen = []
            if st.get("stand") == 10 and (s["id"], 10, st.get("feit")) not in labels:
                te_lezen.append(f"STAND 10 bij {st.get('feit')}: {zin.get(st.get('feit'))}")
            eigen = set(s.get("eigen") or ())
            if s["label"] == "onwaar":
                if (o in ("let op", "klopt") or (o == "klopt niet" and a["bronnen"] and not any(
                        b.get("soort") == "geheugen" and b.get("claim") in eigen for b in a["bronnen"]))) \
                        and (s["id"], o) not in labels:
                    te_lezen.append(f"OORDEEL {o}")
            elif (o in ("klopt niet", "let op") or (s["label"] == "geen bewering" and o == "klopt")) \
                    and (s["id"], o) not in labels:
                te_lezen.append(f"OORDEEL {o}")
            if te_lezen:
                print(f"\n[{s['id']} · {s['deel']} · label {s['label']}] {' | '.join(te_lezen)}\n"
                      f"  BERICHT: {s['tekst'][:400]}\n  BEWERING: {a.get('bewering')}\n  UITLEG: {a.get('uitleg')}")
                for b in a["bronnen"]:
                    print(f"  BRON ({b['soort']}): {b.get('url')} — {b.get('citaat') or b.get('claim')}")
        return
    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    batches = UIT / "batches.jsonl"
    if args.stap == "indienen":
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        nog = [s for s in stukken if f"a-{s['id']}" not in ingediend]
        if args.proef:
            nog = [s for d in DELEN for s in [x for x in nog if x["deel"] == d][: args.proef]]
        if not nog:
            raise SystemExit("niets in te dienen")
        mach = [{**_machineverzoek(s), "custom_id": f"a-{s['id']}"} for s in nog]
        feiten = [_feitverzoek(s, k) for s in nog if s["kandidaten"] for k in ("A", "B")]
        geschat = len(mach) * SCHATTING["machine"] + len(feiten) * SCHATTING["feit"]
        if al_uitgegeven() + geschat > BUDGET:
            raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        for soort, verzoeken, schatting in (("machine", mach, len(mach) * SCHATTING["machine"]),
                                            ("feit", feiten, len(feiten) * SCHATTING["feit"])):
            if not verzoeken:
                continue
            batch = client.messages.batches.create(requests=verzoeken)
            with batches.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": batch.id, "soort": soort, "schatting": round(schatting, 3),
                                     "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
            print(f"batch {batch.id}: {len(verzoeken)} {soort}verzoeken")
        print(f"samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    if args.stap == "ophalen":
        prijs = (MODELLEN["sonnet"]["in"], MODELLEN["sonnet"]["uit"])  # met batchkorting
        alle = _jsonl(batches)
        klaar_m = set(machine)
        klaar_f = {(r["id"], r["sleutel"]) for r in feit}
        with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fm, \
                (UIT / "feit-antwoorden.jsonl").open("a", encoding="utf-8") as ff:
            for b in alle:
                if b.get("werkelijk") is not None:
                    continue
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    continue
                werkelijk = 0.0
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded":
                        continue
                    if b["soort"] == "machine":
                        s = per_id[r.custom_id.removeprefix("a-")]
                        rij = _machineantwoord(s, r.result.message, prijs)
                        werkelijk += rij["kosten"]
                        if s["id"] not in klaar_m:
                            fm.write(json.dumps(rij, ensure_ascii=False) + "\n")
                    else:
                        from doublecheck.feitstap import uit_verzoek_id

                        stuk_id, sleutel = uit_verzoek_id(r.custom_id)
                        rij = _feitantwoord(per_id[stuk_id], sleutel, r.result.message, prijs)
                        werkelijk += rij["kosten"]
                        if (stuk_id, sleutel) not in klaar_f:
                            ff.write(json.dumps(rij, ensure_ascii=False) + "\n")
                b["werkelijk"] = round(werkelijk, 4)
        _schrijf(batches, alle)
        machine = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
        print(Counter((per_id[i]["deel"], a["oordeel"]) for i, a in machine.items()),
              f"\nuitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    # live: de wachttijd, 20 per deel; de drie vragen tegelijk, zoals de dienst ze zou stellen.
    from concurrent.futures import ThreadPoolExecutor

    gedaan = {r["id"] for r in _jsonl(UIT / "live.jsonl")}
    rng = random.Random(ZAAD + 4)
    kies = [s for d in DELEN for s in sorted(rng.sample([x for x in stukken if x["deel"] == d], N_LIVE),
                                             key=lambda x: x["id"]) if s["id"] not in gedaan]
    geschat = len(kies) * 0.03
    if al_uitgegeven() + geschat > BUDGET:
        raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")

    def vraag(params: dict):
        begin = time.perf_counter()
        msg = client.messages.create(**params)
        return msg, time.perf_counter() - begin

    for s in kies:
        verzoeken = {"machine": _machineverzoek(s)["params"]}
        if s["kandidaten"]:
            verzoeken |= {k: _feitverzoek(s, k)["params"] for k in ("A", "B")}
        begin = time.perf_counter()
        with ThreadPoolExecutor(max_workers=3) as pool:
            klaar = {k: pool.submit(vraag, p) for k, p in verzoeken.items()}
            uitslag = {k: f.result() for k, f in klaar.items()}
        model = time.perf_counter() - begin
        a = _machineantwoord(s, uitslag["machine"][0], LIVE_PRIJS)
        feiten = [_feitantwoord(s, k, uitslag[k][0], LIVE_PRIJS) for k in ("A", "B") if k in uitslag]
        rij = {"id": s["id"], "deel": s["deel"], "lokaal": s["tijden"]["lokaal"], "model": round(model, 3),
               "route": round(s["tijden"]["lokaal"] + model, 3),
               "per vraag": {k: round(w, 3) for k, (_, w) in uitslag.items()}, "oordeel": a["oordeel"],
               "feit": [(x["sleutel"], x["richting"], x["feit"]) for x in feiten],
               "kosten": round(a["kosten"] + sum(x["kosten"] for x in feiten), 5)}
        with (UIT / "live.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
        print(f"{s['id']}: route {rij['route']:.1f} s ({a['oordeel']}); ${al_uitgegeven():.2f}", flush=True)


if __name__ == "__main__":
    main()
