"""De radar van de eigen redactie: elke week per taal van de site een lijst met wat er op X rondgaat (PLAN #37.1, B82; PO
2026-11-18: "Ja, bouw de radar maar"; sinds B85, PLAN #37.7, per taal: "Als we van elk land de rondgaande berichten
constant goed in de gaten houden op X, houden we ... vinger aan de pols met onze radar"). Sinds 2026-11-23 komt alleen de
Engelse lijst op schijf (B89, PO: "Ik denk dat we alleen Engels moeten pakken"); de andere talen leest de radar nog, voor
"ook in".

    python -m doublecheck.radarlijst ophalen          # de nieuwste export van X, als die er nog niet is
    python -m doublecheck.radarlijst lijst [--taal alle|nl,en] [--lijsten en] [--melding] [--tot JJJJ-MM-DD] [--weken N]
    python -m doublecheck.radarlijst weg <nummers> [--taal en] [--tot JJJJ-MM-DD]
    python -m doublecheck.radarlijst tip "<wat er rondgaat>" [--link <adres>]

Per taal: X geeft per note geen land, dus de taal van de note is de benadering van de regio. Voorop staat wat de
positionering van Factiz Radar vraagt (`rangorde_radar`): nog door niemand gecheckt, wat dezelfde week ook in een andere
taal rondgaat (bge-m3 over de talen heen, `ook_in`), een note op beeld of video, en dan het bereik. Naast de lijst per taal
een overzicht van wat in meer talen tegelijk rondgaat (`<dag>-talen.md`).

De voormeting (#37.0, BENCHMARK §261) wees de bron aan: de Community Notes van X in het Nederlands. In de week van 8 tot
14 november waren dat 37 posts met een note, 10 te checken beweringen, waarvan 9 nog door niemand gecheckt. De lijst
groepeert de notes per bewering (dezelfde post, of een note die bijna hetzelfde zegt), zet erbij hoeveel posts en notes,
wanneer het eerst gezien is, welke bronnen de notes noemen, en of een factchecker of het archief het al heeft; wat
waarschijnlijk geen bewering is (parodie, een nagemaakt of gestolen account), staat er niet op. Tips van mensen komen erbij
(`tip`): wat er rondgaat en waar, nooit wie het stuurde (B78).

Alles lokaal: een notetekst gaat nooit naar een externe dienst (zoals bij #25.23) en nooit op de site. De lijst is
werkmateriaal voor de PO, in `data/radar/lijst/<dag>.md`, buiten git. De export blijft in `data/communitynotes/<dag>/`; na
een nieuwe blijft er hoogstens één oudere staan. Elke maandag om 8:00 met `deploy/org.factiz.radar.plist`.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import shutil
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
EXPORTS = WORTEL / "data" / "communitynotes"
MAP = WORTEL / "data" / "radar"
TIPS = MAP / "tips.jsonl"
WEG = MAP / "weg.jsonl"         # wat de redactie uit een lijst haalde (`weg`): die posts en notes komen niet terug
VECTOREN = WORTEL / "data" / "lijktop"
BRON = "https://ton.twimg.com/birdwatch-public-data"
BESTANDEN = ("notes/notes-00000", "notes/notes-00001", "notes/notes-00002", "notes/notes-00003", "notes/notes-00004",
             "noteStatusHistory/noteStatusHistory-00000")
DREMPEL = 0.85          # twee notes op verschillende posts zijn dezelfde bewering vanaf deze gelijkenis (bge-m3); gemeten
                        # op de notes sinds 1 oktober: de paren van 0,85 tot 0,90 zijn dezelfde bewering of dezelfde soort
                        # niet-bewering ("stolen post")
ONDERWERP = 0.65        # twee beweringen gaan over hetzelfde onderwerp vanaf deze gelijkenis: de notes over box 3 lagen
                        # onderling op 0,40 tot 0,80 (mediaan 0,69), tegen de andere van die week hoogstens op 0,59
ARCHIEF_VLOER = 0.80    # een check in het archief lijkt erop vanaf deze gelijkenis (de vloer van Lijkt op)
TALEN_DREMPEL = 0.80    # dezelfde bewering in een andere taal vanaf deze gelijkenis; voorlopig, nog niet gemeten (B85).
                        # Bij 0,70 leek "deze video is met AI gemaakt" in tien talen op elkaar, over andere video's
PER_ONDERWERP = 8       # zo veel andere beweringen per onderwerp op de lijst
MAX_ONDERWERPEN = 40    # zo veel onderwerpen per lijst: in het Engels gaan er per week duizenden rond
# de talen van de site (`factiz_site/teksten/sitetalen.json`), het Nederlands eerst; in de lijst voor de PO bij naam
TAALNAAM = {"nl": "het Nederlands", "en": "het Engels", "de": "het Duits", "es": "het Spaans", "fr": "het Frans",
            "pt": "het Portugees", "ru": "het Russisch", "uk": "het Oekraïens", "tr": "het Turks", "ar": "het Arabisch",
            "fa": "het Perzisch", "hi": "het Hindi", "id": "het Indonesisch", "ja": "het Japans", "zh": "het Chinees"}
TALEN = tuple(TAALNAAM)
# welke lijsten op schijf komen (PO 2026-11-23: "alleen Engels ... Mag gewoon in het engels, NL wordt 1 van de vertaal talen
# later"): de radar leest elke taal van de site, want die zijn nodig voor "ook in", maar schrijft alleen de Engelse lijst en
# het overzicht over de talen heen; daaruit houdt de redactie elke week de 20 beste over (PLAN #37.10)
LIJSTEN = ("en",)
BEKEND = 20             # een persoon of organisatie met een artikel in zo veel talen van Wikipedia is internationaal genoeg
                        # (PO 2026-11-19: "Ja, bouw het zo in met 20 talen"; zo telt een premier van Nederland mee)
PUBLICATIE = WORTEL / "data" / "publicatie"
WIKIDATA = WORTEL / "data" / "namen" / "wikidata.jsonl"     # de namen die #33.7 opzocht, ruimer dan het register
# platforms zijn geen onderwerp: een note noemt ze omdat het daar rondging, niet omdat het erover gaat
PLATFORMS = frozenset({"Facebook", "Instagram", "X", "Twitter", "TikTok", "YouTube", "Google", "Telegram", "WhatsApp",
                       "Reddit", "Meta Platforms", "Microsoft", "Bluesky", "Threads", "LinkedIn", "Snapchat", "Wikipedia",
                       "Google Search", "Community Notes", "Apple", "Amazon", "Spotify", "Pinterest", "Truth Social"})
# nieuwsmedia evenmin: een note noemt Reuters of de BBC als bron (de soorten bij Wikidata: krant, persbureau, omroep,
# tv-station, tijdschrift, nieuwssite)
MEDIA = frozenset({"Q11032", "Q192283", "Q1110794", "Q1002697", "Q1153191", "Q1616075", "Q1254874", "Q561068",
                   "Q15265344", "Q2001305", "Q14350", "Q41298", "Q1193236", "Q17232649", "Q1331793", "Q1449648",
                   "Q1962634", "Q66475652", "Q7094076", "Q5398426"})
_TITEL = re.compile(r"\b(?:of|the|von der Vogelweide|[IVX]{1,4})\b")
# de universele trucs die een note zelf aanwijst: een lezer in een ander land leert er evenveel van
TRUCS = (("bewerkt", "bewerkt of met AI"), ("oud", "oud als nieuw"))
_WOORD = re.compile(r"\w+(?:[-'’]\w+)*")
# schriften zonder spaties tussen de woorden: daar zoekt een naam als tekenreeks
_ZONDER_SPATIES = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿]")
HOUD = 2                # zo veel exports blijven staan: de nieuwste en één oudere

_URL = re.compile(r"https?://[^\s\"'<>]+")
# Zeker geen bewering: een gestolen of gekopieerde post, een nagemaakt account of een bot. Parodie en satire alleen in een
# korte note: een lange note die zegt dat een bewering "uit satire-accounts komt", weerlegt juist een bewering (de boete
# van de EU voor Starlink, 2026-11-09).
_GEEN = re.compile(r"\b(stolen|gestolen|copied|kopie van|een kopie|bot\b|nep[- ]?account|fake account|"
                   r"niet het officiële account|"
                   # een note die zelf zegt dat er geen note nodig is (PO 2026-11-22, nummer 4 van de Nederlandse lijst)
                   r"geen note nodig|no note needed|nnn\b)", re.IGNORECASE)
_KORT_GEEN = re.compile(r"\b(parod|satir)", re.IGNORECASE)
# Kleine woorden die alleen in één van de twee talen voorkomen ("in", "is" en "was" staan in beide): py3langid noemde
# "Jensen did not get fired. He resigned." Nederlands, met 0,997 (2026-11-18)
_NL = frozenset("de het een en van niet dat die op te zijn met voor er maar ook aan deze dit wordt werd geen naar om bij "
                "als nog heeft hebben door over uit wat hij zij ze wij je klopt".split())
_EN = frozenset("the a an and of not that to are with for has have had did does he she it they this these by from at "
                "be been his her their which but who".split())


def van_de_week(notes: list[dict]) -> list[dict]:
    """De notes van de zeven dagen tot en met de laatste note in de export."""
    if not notes:
        return []
    laatste = date.fromisoformat(max(n["datum"] for n in notes))
    begin = (laatste - timedelta(days=6)).isoformat()
    return [n for n in notes if n["datum"] >= begin]


def groepeer(notes: list[dict], vectoren, drempel: float = DREMPEL) -> list[dict]:
    """Per bewering één groep: de notes op dezelfde post, en een post waarvan de eerste note bijna hetzelfde zegt als de
    eerste note van een groep (de eerste groep die het haalt). De post met de meeste notes begint een groep. Met numpy
    tegen alle groepen tegelijk, want in het Engels zijn het er per week duizenden (B85); dezelfde uitkomst als een voor
    een."""
    import numpy as np

    per_post: dict[str, list[int]] = {}
    for i, n in enumerate(notes):
        per_post.setdefault(n["post"], []).append(i)
    volgorde = sorted(per_post, key=lambda p: (-len(per_post[p]), min(notes[i]["datum"] for i in per_post[p]), p))
    groepen: list[dict] = []
    kernen = np.empty((len(volgorde), vectoren.shape[1]), dtype=np.float32)
    for post in volgorde:
        eerste = per_post[post][0]
        doel = None
        if groepen:
            boven = np.flatnonzero(kernen[:len(groepen)] @ vectoren[eerste] >= drempel)
            if boven.size:
                doel = groepen[int(boven[0])]
        if doel is None:
            kernen[len(groepen)] = vectoren[eerste]
            doel = {"_kern": eerste, "posts": [], "notes": [], "eerst": notes[eerste]["datum"], "behulpzaam": 0,
                    "tekst": notes[eerste].get("tekst", ""), "media": False}
            groepen.append(doel)
        doel["posts"].append(post)
        for i in per_post[post]:
            doel["notes"].append(notes[i]["note"])
            doel["eerst"] = min(doel["eerst"], notes[i]["datum"])
            doel["behulpzaam"] += notes[i].get("status") == "CURRENTLY_RATED_HELPFUL"
            doel["media"] = doel["media"] or bool(notes[i].get("media"))
            for veld, naam in TRUCS:
                if notes[i].get(veld) and naam not in doel.setdefault("truc", []):
                    doel["truc"].append(naam)
    for g in groepen:
        g.pop("_kern")
    return groepen


def onderwerpen(groepen: list[dict], vectoren, kernen: list[int], drempel: float = ONDERWERP,
                sleutel=None) -> list[list[dict]]:
    """Beweringen over hetzelfde onderwerp bij elkaar (de tabellen van box 3 in zeven notes): een bewering hoort bij het
    eerste onderwerp waarvan de eerste bewering op haar lijkt. Alleen met die eerste, niet met elk lid: in het Engels
    ketende dat 5.816 beweringen aan elkaar, van AI-filmpjes tot de vliegstop in de VS (2026-11-19). Elk onderwerp met de belangrijkste bewering
    voorop; `kernen` is per groep de plek van haar eerste note in `vectoren`. Zonder `sleutel` gaat het grootste onderwerp
    voorop (`rangorde`); met `rangorde_radar` eerst wat die voorop zet, dan het grootste. Met numpy, zoals `groepeer`."""
    import numpy as np

    orde = sleutel or rangorde
    volgorde = sorted(range(len(groepen)), key=lambda i: orde(groepen[i]))
    uit: list[list[int]] = []
    geplaatst = np.empty((len(groepen), vectoren.shape[1] if len(groepen) else 0), dtype=np.float32)
    for i in volgorde:
        v = vectoren[kernen[i]]
        boven = np.flatnonzero(geplaatst[:len(uit)] @ v >= drempel) if uit else np.empty(0, dtype=np.int64)
        if boven.size:
            uit[int(boven[0])].append(i)
        else:
            geplaatst[len(uit)] = v
            uit.append([i])

    def onderwerp(o: list[int]) -> tuple:
        posts = -sum(len(groepen[i]["posts"]) for i in o)
        return (posts, rangorde(groepen[o[0]])) if sleutel is None else (orde(groepen[o[0]])[:3], posts, orde(groepen[o[0]]))
    return [[groepen[i] for i in o] for o in sorted(uit, key=onderwerp)]


def geen_bewering(tekst: str) -> bool:
    """Of een note zegt dat het om een kopie, een nagemaakt account of een bot gaat, of in een korte note om parodie of
    satire: waarschijnlijk geen bewering."""
    zonder_links = _URL.sub("", tekst or "").strip()
    return bool(_GEEN.search(zonder_links)) or (len(zonder_links) < 100 and bool(_KORT_GEEN.search(zonder_links)))


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(url.rstrip(".,);]")).hostname or "").lower().removeprefix("www.")


def bronnen(tekst: str) -> list[str]:
    """De websites die een note noemt, in volgorde, elk één keer."""
    uit: list[str] = []
    for url in _URL.findall(tekst or ""):
        h = _host(url)
        if h and h not in uit:
            uit.append(h)
    return uit


def zonder_nieuwsmedia(domeinen: set[str]) -> set[str]:
    """De factchecksites zonder de nieuwsmedia die ook een factcheckrubriek hebben (`speuren.NIEUWSMEDIA`, ook hun
    subdomeinen): een gewoon artikel van de VRT of van AFP is geen factcheck. Hun rubriek telt nog, op het adres
    (`speuren.PATRONEN`, zoals factchecknederland.afp.com)."""
    from doublecheck.speuren import NIEUWSMEDIA

    return {d for d in domeinen if not any(d == m or d.endswith("." + m) for m in NIEUWSMEDIA)}


def in_het_nederlands(tekst: str) -> bool:
    """Een note in het Nederlands: de taal van de tekst zonder links, met minstens 25 tekens, en meer Nederlandse dan
    Engelse kleine woorden (`_NL`, `_EN`). Een adres als nintendo.com/us/store/... liet "It's $59.99" voor Nederlands
    doorgaan, en py3langid zelf korte Engelse zinnen (2026-11-18)."""
    import py3langid

    kaal = " ".join(_URL.sub(" ", tekst or "").split())
    if len(kaal) < 25 or py3langid.classify(kaal)[0] != "nl":
        return False
    woorden = re.findall(r"[a-z]+", kaal.lower())
    return sum(w in _NL for w in woorden) > sum(w in _EN for w in woorden)


def taal_van(tekst: str) -> str | None:
    """De taal van de site waarin een note geschreven is (B85), of None: een sitetaal als py3langid haar noemt op minstens
    25 tekens zonder links; het Nederlands alleen met de strenge regel van `in_het_nederlands`."""
    import py3langid

    kaal = " ".join(_URL.sub(" ", tekst or "").split())
    if len(kaal) < 25:
        return None
    taal = py3langid.classify(kaal)[0]
    if taal == "nl":
        return "nl" if in_het_nederlands(tekst) else None
    return taal if taal in TAALNAAM else None


def ook_in(kernen: dict, drempel: float = TALEN_DREMPEL) -> dict[str, list[list[str]]]:
    """Per taal en per bewering de andere talen waarin dezelfde week een bewering rondging die erop lijkt (B85): het
    sterkste signaal dat iets internationaal speelt. `kernen` is per taal een matrix met per bewering de vector van haar
    eerste note; de andere talen in de volgorde van `TALEN`."""
    import numpy as np

    talen = [t for t in TALEN if t in kernen] + [t for t in kernen if t not in TALEN]
    uit = {t: [[] for _ in range(len(kernen[t]))] for t in talen}
    for t in talen:
        for ander in talen:
            if ander == t or not len(kernen[t]) or not len(kernen[ander]):
                continue
            for begin in range(0, len(kernen[t]), 2048):
                blok = kernen[t][begin:begin + 2048] @ np.asarray(kernen[ander]).T
                for j in np.flatnonzero(blok.max(axis=1) >= drempel):
                    uit[t][begin + int(j)].append(ander)
    return uit


def rangorde_radar(groep: dict) -> tuple:
    """De volgorde van Factiz Radar (B85): eerst wat nog niemand checkte, dan wat internationaal genoeg is (een bekende
    naam, dan in meer andere talen tegelijk, dan een universele truc; een naam eerst, want een algemene note als "deze
    video is met AI gemaakt" lijkt in elke taal op elkaar), dan een note op beeld of video, en dan zoals
    `rangorde` (posts, behulpzame notes, notes)."""
    return (1 if groep.get("gecheckt") else 0, 0 if groep.get("namen") else 1, -len(groep.get("ook_in") or ()),
            0 if groep.get("truc") else 1, 0 if groep.get("media") else 1, *rangorde(groep))


def _sleutel(vorm: str) -> str:
    return " ".join(_WOORD.findall(vorm))


def bekende_namen(db: Path, drempel: int = BEKEND, wikidata: Path | None = None) -> dict:
    """De personen en organisaties uit het register van de uitgave met een artikel in minstens `drempel` talen van
    Wikipedia, met hun schrijfwijzen (de namen per taal en `naam_vorm`). Een vorm van meer woorden telt ook zonder
    hoofdletters, een vorm in een schrift zonder spaties als tekenreeks. Eén woord telt alleen met dezelfde hoofdletters,
    en alleen als het de naam zelf is ("NAVO", "Gazprom") of de achternaam van een persoon ("Jetten") die geen andere
    bekende naam deelt: een losse alias als "Washington" of "Johnson" wijst te vaak iets anders aan. Een plaats en een
    platform tellen niet: elke stad heeft artikelen in veel talen, en een platform is waar het rondging."""
    import sqlite3

    index: dict = {"woord": {}, "woorden": {}, "tekens": [], "lengte": 1}
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
        kolommen = [r[1] for r in c.execute("PRAGMA table_info(naam)") if r[1].startswith("naam_")]
        rijen = c.execute(f"SELECT nummer, naam_en, wikis, {', '.join(kolommen)} FROM naam WHERE soort IN "
                          "('persoon', 'organisatie') AND wikis >= ?", (drempel,)).fetchall()
        vormen: dict[str, list[str]] = {}
        for naam, vorm in c.execute("SELECT naam, vorm FROM naam_vorm"):
            vormen.setdefault(naam, []).append(vorm)
        soort = dict(c.execute("SELECT nummer, soort FROM naam"))
        plaatswoorden = {w for (n,) in c.execute("SELECT naam_en FROM naam WHERE soort = 'plaats'") for w in _WOORD.findall(n or "")}
    personen = {r[0] for r in rijen if soort.get(r[0]) == "persoon"}
    # de personen ook uit wat #33.7 opzocht (Klaver, Verstappen): het register van de uitgave houdt alleen namen met vijf
    # pagina's en twee redacties; een plaats of organisatie daar niet, want die soort kent dat bestand niet zeker. Uit
    # hetzelfde bestand de soort bij Wikidata, om nieuwsmedia over te slaan
    media: set[str] = set()
    if wikidata and Path(wikidata).exists():
        bekend = {r[0] for r in rijen}
        for regel in Path(wikidata).read_text(encoding="utf-8").splitlines():
            r = json.loads(regel)
            k = r.get("kenmerken") or {}
            if MEDIA & set(r.get("p31") or ()):
                media.add(r["nummer"])
            if (r["nummer"] in bekend or not k.get("mens") or k.get("weg") or (k.get("wikis") or 0) < drempel):
                continue
            namen = k.get("namen") or {}
            rijen.append((r["nummer"], namen.get("en") or next(iter(namen.values()), ""), k["wikis"], *namen.values()))
            vormen[r["nummer"]] = list(k.get("vormen") or [])
            personen.add(r["nummer"])
    rijen = [r for r in rijen if r[1] not in PLATFORMS and r[0] not in media]
    # hoe vaak een woord voorkomt in de namen van verschillende bekende namen: een gedeeld woord is geen achternaam
    van_woord: dict[str, set[str]] = {}
    for nummer, _, _, *namen in rijen:
        for naam in namen:
            for w in _WOORD.findall(naam or ""):
                van_woord.setdefault(w, set()).add(nummer)
    for nummer, naam_en, wikis, *namen in rijen:
        doel = (naam_en, int(wikis))
        labels = {v for v in namen if v}
        for vorm in labels | set(vormen.get(nummer, [])):
            if _ZONDER_SPATIES.search(vorm):
                if len(vorm) >= 2:
                    index["tekens"].append((vorm, doel))
                continue
            woorden = _WOORD.findall(vorm)
            if len(woorden) == 1 and len(woorden[0]) >= 4 and vorm in labels:
                index["woord"].setdefault(woorden[0], doel)
            elif len(woorden) > 1 and len(vorm) >= 5:
                index["woorden"].setdefault(_sleutel(vorm).casefold(), doel)
                index["lengte"] = max(index["lengte"], len(woorden))
        # een achternaam alleen van een persoon, niet van een vorst of een bijnaam ("Catherine II of Russia", "Alexander
        # the Great"), en geen woord dat ook een plaats is ("Russia")
        achternamen = {_WOORD.findall(n)[-1] for n in labels if len(_WOORD.findall(n)) > 1}
        if nummer not in personen or _TITEL.search(naam_en or ""):
            achternamen = set()
        for w in sorted(achternamen):
            if len(w) >= 5 and w[0].isupper() and len(van_woord.get(w, ())) == 1 and w not in plaatswoorden:
                index["woord"].setdefault(w, doel)
    return index


def namen_in(tekst: str, index: dict) -> list[tuple[str, int]]:
    """De bekende namen in een tekst, de bekendste eerst, elk één keer."""
    woorden = _WOORD.findall(tekst or "")
    gevonden = {index["woord"][w] for w in woorden if w in index["woord"]}
    klein = [w.casefold() for w in woorden]

    def eigennaam(w: str) -> bool:     # met een hoofdletter, of in een schrift zonder hoofdletters
        return w[0].isupper() or w[0].lower() == w[0].upper()
    for n in range(2, index["lengte"] + 1):
        for i in range(len(klein) - n + 1):
            # een naam van meer woorden begint en eindigt in de tekst als eigennaam: "the base" is niet Al-Qaeda
            if (doel := index["woorden"].get(" ".join(klein[i:i + n]))) and eigennaam(woorden[i]) and eigennaam(woorden[i + n - 1]):
                gevonden.add(doel)
    if _ZONDER_SPATIES.search(tekst or ""):
        gevonden |= {doel for vorm, doel in index["tekens"] if vorm in tekst}
    return sorted(gevonden, key=lambda d: (-d[1], d[0]))


def al_gecheckt(tekst: str, domeinen: set[str]) -> list[str]:
    """De links in een note naar een factchecker of een onderzoeker van desinformatie (`speuren.van_factchecker`)."""
    from doublecheck.speuren import van_factchecker

    return [u.rstrip(".,);]") for u in _URL.findall(tekst or "") if van_factchecker(u.rstrip(".,);]"), domeinen)]


def rangorde(groep: dict) -> tuple:
    """Eerst wat op de meeste posts rondgaat, dan met de meeste behulpzame notes, dan met de meeste notes."""
    return (-len(groep["posts"]), -groep.get("behulpzaam", 0), -len(groep["notes"]))


def tip_erbij(pad: Path, tekst: str, *, link: str | None = None, vandaag: str | None = None) -> None:
    """Een tip: wat er rondgaat en waar, nooit wie het stuurde (B78)."""
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"datum": vandaag or date.today().isoformat(), "tekst": tekst.strip(), "link": link or ""},
                           ensure_ascii=False) + "\n")


# --- wat de redactie weghaalt ----------------------------------------------------------------------------------------

_BLOK = re.compile(r"^(\d+)\. (.*)$")
_POST = re.compile(r"https://x\.com/i/status/(\d+)")
_NOTE = re.compile(r"https://x\.com/i/birdwatch/n/(\d+)")
_MEER = re.compile(r"ook over dit onderwerp \((\d+) bewering")


def haal_weg(tekst: str, nummers: list[int]) -> tuple[str, list[dict]]:
    """Een lijst zonder de onderwerpen met deze nummers, de rest opnieuw genummerd, en per weggehaald onderwerp zijn posts
    en notes (PO 2026-11-22: "IN NL kunnen weg: 4 5 8 11"). Een onderwerp is de regel met zijn nummer en de ingesprongen
    regels eronder; de telling bovenaan gaat mee."""
    regels, uit, weg, blok, nieuw_nr = tekst.split("\n"), [], [], None, 0
    onderwerpen = beweringen = 0

    def sluit():
        nonlocal onderwerpen, beweringen
        if blok is None:
            return
        nr, eigen = blok
        if nr in nummers:
            samen = "\n".join(eigen)
            weg.append({"posts": list(dict.fromkeys(_POST.findall(samen))), "notes": list(dict.fromkeys(_NOTE.findall(samen))),
                        "tekst": _BLOK.match(eigen[0]).group(2)})
            onderwerpen += 1
            m = _MEER.search(samen)
            beweringen += 1 + (int(m.group(1)) if m else 0)
        else:
            uit.extend(eigen)

    for r in regels:
        m = _BLOK.match(r)
        if m:
            sluit()
            nr = int(m.group(1))
            if nr not in nummers:
                nieuw_nr += 1
                r = f"{nieuw_nr}. {m.group(2)}"
            blok = (nr, [r])
        elif blok is not None and r.startswith("   "):
            blok[1].append(r)
        else:
            sluit()
            blok = None
            uit.append(r)
    sluit()
    tekst_uit = "\n".join(uit)
    kop = re.search(r"(\d+) onderwerpen met (\d+) beweringen", tekst_uit)
    if kop and weg:
        tekst_uit = tekst_uit.replace(kop.group(0), f"{int(kop.group(1)) - onderwerpen} onderwerpen met "
                                                    f"{int(kop.group(2)) - beweringen} beweringen", 1)
    return tekst_uit, weg


def zonder_weg(groepen: list[dict], weg: list[dict]) -> list[dict]:
    """De beweringen zonder wat de redactie eerder weghaalde: geen post en geen note van een weggehaald onderwerp."""
    posts = {str(p) for w in weg for p in w.get("posts", [])}
    notes = {str(n) for w in weg for n in w.get("notes", [])}
    return [g for g in groepen if not ({str(p) for p in g["posts"]} & posts or {str(n) for n in g["notes"]} & notes)]


def tips(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def _kort(tekst: str, n: int = 320) -> str:
    t = re.sub(r"\s+", " ", tekst or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " ..."


def pagina(kop: dict, onderwerpen_: list[list[dict]], tips_: list[dict], taal: str = "nl") -> str:
    """De lijst van de week voor de PO: per onderwerp de belangrijkste bewering met de tekst van haar eerste note, de
    tellingen, de bronnen, of het al gecheckt is, in welke andere talen het ook rondgaat, of de note over beeld of video
    gaat, en de links, en de andere beweringen over hetzelfde onderwerp eronder. Wat waarschijnlijk geen bewering is,
    staat er niet op (PO 2026-11-22: "'Waarschijnlijk geen bewering' kan allemaal weg"). Hoogstens `MAX_ONDERWERPEN`
    onderwerpen."""
    beweringen = sum(len(o) for o in onderwerpen_)
    meer = max(0, len(onderwerpen_) - MAX_ONDERWERPEN)
    onderwerpen_ = onderwerpen_[:MAX_ONDERWERPEN]
    naam = TAALNAAM.get(taal, taal)
    regels = [f"# De radar in {naam}: {kop['van']} tot {kop['tot']}" if taal != "nl" else
              f"# De radar: {kop['van']} tot {kop['tot']}", "",
              f"{kop['notes']} notes in {naam} op {kop['posts']} posts: {len(onderwerpen_) + meer} onderwerpen met "
              f"{beweringen} beweringen. Uit de Community Notes van X; "
              "alleen werkmateriaal, nooit op de site. Kies er een of twee voor een eigen factcheck (B82).", "",
              "## Onderwerpen", ""]

    def blok(nr: int, g: dict) -> list[str]:
        posts = len(g["posts"])
        uit = [f"{nr}. {_kort(g['tekst'])}",
               f"   - {posts} post{'s' if posts != 1 else ''}, {len(g['notes'])} note{'s' if len(g['notes']) != 1 else ''}"
               f" ({g.get('behulpzaam', 0)} behulpzaam), eerst gezien {g['eerst']}"]
        if g.get("bronnen"):
            uit.append(f"   - bronnen in de notes: {', '.join(g['bronnen'][:6])}")
        if g.get("namen"):
            uit.append("   - bekende naam: " + ", ".join(f"{n} ({w} talen op Wikipedia)" for n, w in g["namen"][:3]))
        if g.get("truc"):
            uit.append(f"   - truc: {', '.join(g['truc'])}")
        if g.get("media"):
            uit.append("   - met beeld of video")
        if g.get("ook_in"):
            uit.append(f"   - ook in: {', '.join(TAALNAAM.get(x, x) for x in g['ook_in'])}")
        if g.get("gecheckt"):
            uit.append(f"   - al gecheckt: {g['gecheckt'][0]}")
        if g.get("archief"):
            a = g["archief"]
            uit.append(f"   - lijkt op een check in het archief: factiz.org/fact-checks/{a['pagina']}/ ({a['score']:.2f})")
        uit.append("   - " + " · ".join([f"https://x.com/i/status/{p}" for p in g["posts"][:3]]
                                        + [f"https://x.com/i/birdwatch/n/{g['notes'][0]}"]))
        return uit

    for i, onderwerp in enumerate(onderwerpen_, 1):
        regels += blok(i, onderwerp[0])
        if len(onderwerp) > 1:
            posts = sum(len(g["posts"]) for g in onderwerp)
            meer = len(onderwerp) - 1
            regels.append(f"   - ook over dit onderwerp ({meer} bewering{'en' if meer != 1 else ''} meer, {posts} posts samen):")
            regels += [f"     - {_kort(g['tekst'], 140)} https://x.com/i/status/{g['posts'][0]}"
                       for g in onderwerp[1:PER_ONDERWERP + 1]]
            if meer > PER_ONDERWERP:
                regels.append(f"     - en nog {meer - PER_ONDERWERP} beweringen")
    if meer:
        regels += ["", f"en nog {meer} onderwerpen"]
    if tips_:
        regels += ["", "## Tips", ""] + [f"- {t['datum']}: {_kort(t['tekst'])}" + (f" ({t['link']})" if t.get("link") else "")
                                         for t in tips_]
    return "\n".join(regels) + "\n"


# --- de bestanden, het net en het model -------------------------------------------------------------------------------

def _rijen(export: Path, naam: str):  # pragma: no cover - bestanden
    csv.field_size_limit(10_000_000)
    for pad in sorted(export.glob(f"{naam}-*.zip")):
        with zipfile.ZipFile(pad) as z:
            for binnen in z.namelist():
                with z.open(binnen) as f:
                    yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t",
                                              quoting=csv.QUOTE_NONE)


def _exports() -> list[Path]:  # pragma: no cover - bestanden
    return sorted(p for p in EXPORTS.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]") if p.is_dir()
                  and (p / "notes-00000.zip").exists())


def _ophalen() -> Path:  # pragma: no cover - het net
    """De nieuwste export van X (de dag ervoor of eerder, de export loopt achter), als die er nog niet is; daarna blijven
    hoogstens `HOUD` exports staan."""
    import subprocess

    for terug in range(0, 6):
        dag = date.today() - timedelta(days=terug)
        pad = f"{dag:%Y/%m/%d}"
        kop = subprocess.run(["curl", "-s", "-I", "--max-time", "30", f"{BRON}/{pad}/{BESTANDEN[0]}.zip"],
                             capture_output=True, text=True).stdout
        eerste_regel = kop.splitlines()[0] if kop else ""
        if " 200" in eerste_regel:
            break
    else:
        raise SystemExit("geen export van X gevonden in de laatste zes dagen")
    doel = EXPORTS / dag.isoformat()
    if (doel / "notes-00000.zip").exists():
        print(f"de export van {dag} is er al")
        return doel
    tijdelijk = EXPORTS / f".{dag.isoformat()}"
    tijdelijk.mkdir(parents=True, exist_ok=True)
    for f in BESTANDEN:
        uit = tijdelijk / f"{Path(f).name}.zip"
        r = subprocess.run(["curl", "-s", "--fail", "--retry", "3", "-o", str(uit), f"{BRON}/{pad}/{f}.zip"])
        if r.returncode or not zipfile.is_zipfile(uit):
            raise SystemExit(f"ophalen van {f} mislukte")
    tijdelijk.rename(doel)
    for oud in _exports()[:-HOUD]:
        shutil.rmtree(oud)
        print(f"weg: {oud.name}")
    print(f"opgehaald: de export van {dag}")
    return doel


def _datum(millis: str) -> str:
    return datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).date().isoformat()


def overzicht(kop: dict, per_taal: dict[str, list[dict]], kernen: dict, drempel: float = TALEN_DREMPEL) -> str:
    """Wat dezelfde week in meer talen rondgaat (B85), voor de keuze van een check die internationaal speelt: per bewering
    de taal met de meeste posts, de andere talen en de tellingen; een bewering die al op een eerdere lijkt, staat er niet
    nog eens. `per_taal` en `kernen` in dezelfde volgorde per taal."""
    import numpy as np

    kandidaten = sorted(((t, i, g) for t, gs in per_taal.items() for i, g in enumerate(gs) if g.get("ook_in")),
                        key=lambda x: (-len(x[2]["ook_in"]), -len(x[2]["posts"]), x[0], x[1]))
    gekozen: list[tuple] = []
    for t, i, g in kandidaten:
        v = kernen[t][i]
        if any(float(kernen[t2][i2] @ v) >= drempel for t2, i2, _ in gekozen):
            continue
        gekozen.append((t, i, g))
        if len(gekozen) >= MAX_ONDERWERPEN:
            break
    regels = [f"# De radar over de talen heen: {kop['van']} tot {kop['tot']}", "",
              f"{len(kandidaten)} beweringen gingen dezelfde week ook in een andere taal rond; hieronder de {len(gekozen)} "
              "die in de meeste talen tegelijk rondgingen. Alleen werkmateriaal, nooit op de site.", ""]
    for n, (t, _, g) in enumerate(gekozen, 1):
        regels += [f"{n}. [{TAALNAAM.get(t, t)}] {_kort(g['tekst'])}",
                   f"   - ook in: {', '.join(TAALNAAM.get(x, x) for x in g['ook_in'])}",
                   f"   - {len(g['posts'])} posts, {len(g['notes'])} notes, eerst gezien {g['eerst']}"
                   + (", met beeld of video" if g.get("media") else "") + (", al gecheckt" if g.get("gecheckt") else ""),
                   "   - " + " · ".join(f"https://x.com/i/status/{p}" for p in g["posts"][:3])]
    return "\n".join(regels) + "\n"


def _lijst(melding: bool, tot: str | None = None, weken: int = 1,
           talen: tuple[str, ...] = TALEN, lijsten: tuple[str, ...] = LIJSTEN) -> list[Path]:  # pragma: no cover
    """De lijst per taal van de week tot en met `tot` (standaard vandaag), en met `weken` ook die van de weken ervoor, elk in
    een eigen bestand (het Nederlands in `<dag>.md`, een andere taal in `<dag>-<taal>.md`), met per week een overzicht van
    wat in meer talen rondging (`<dag>-talen.md`). De export wordt één keer gelezen; alleen de notes van de weken zelf
    worden ingebed, elk één keer."""
    import numpy as np

    from doublecheck.config import load_config
    from doublecheck.embedding import _load_model, normaliseer_voor_embedding

    exports = _exports()
    if not exports:
        raise SystemExit("geen export: eerst `ophalen`")
    export = exports[-1]
    status = {r["noteId"]: r["currentStatus"] for r in _rijen(export, "noteStatusHistory")}
    eind = date.fromisoformat(tot) if tot else date.today()
    eindes = [(eind - timedelta(days=7 * i)).isoformat() for i in range(weken)][::-1]
    # eerst ruim, de week volgt uit de laatste note; met `tot` een eerdere week uit dezelfde export
    grens = (date.fromisoformat(eindes[0]) - timedelta(days=14)).isoformat()
    ruw = []    # alleen wat de lijst gebruikt: de hele rij van elke note van drie weken houdt het geheugen vol
    for r in _rijen(export, "notes"):
        dag = _datum(r["createdAtMillis"])
        if dag < grens or (tot and dag > tot):
            continue
        ruw.append((dag, {"noteId": r["noteId"], "tweetId": r["tweetId"], "summary": r.get("summary") or "",
                          "media": r.get("isMediaNote") == "1" or r.get("misleadingManipulatedMedia") == "1",
                          "bewerkt": r.get("misleadingManipulatedMedia") == "1",
                          "oud": r.get("misleadingOutdatedInformation") == "1"}))
    weken_ = []
    for einde in eindes:
        van = (date.fromisoformat(einde) - timedelta(days=14)).isoformat()
        binnen = [d for d, _ in ruw if van <= d <= einde]
        if binnen:
            laatste = max(binnen)
            weken_.append(((date.fromisoformat(laatste) - timedelta(days=6)).isoformat(), laatste))
    alle = []
    for dag, r in ruw:
        if not any(b <= dag <= e for b, e in weken_):
            continue
        tekst = html.unescape((r.get("summary") or "").strip())
        taal = taal_van(tekst)
        if taal not in talen:
            continue
        alle.append({"note": r["noteId"], "post": r["tweetId"], "datum": dag, "tekst": tekst, "taal": taal,
                     "status": status.get(r["noteId"], ""), "media": r["media"], "bewerkt": r["bewerkt"], "oud": r["oud"]})
    if not alle:
        raise SystemExit("geen notes in deze talen en weken van de export")
    versie = load_config(None).model_versions.text_embedding
    model = _load_model(versie, "mps")
    model.max_seq_length = 256
    import torch

    # de vectoren van eerdere runs: per note alleen het nummer en de vector, nooit de tekst (zoals #37.0)
    opslag = MAP / "vectoren" / versie.replace("/", "_")
    vector = {}
    if (opslag / "nummers.json").exists():
        nummers = json.loads((opslag / "nummers.json").read_text(encoding="utf-8"))
        vector = dict(zip(nummers, np.load(opslag / "vectoren.npy")))
    nieuw = [n for n in alle if n["note"] not in vector]
    for begin in range(0, len(nieuw), 2000):     # in stukken, en het geheugen van de grafische chip tussendoor vrij
        deel = nieuw[begin:begin + 2000]
        vector.update(zip((n["note"] for n in deel), model.encode(
            [normaliseer_voor_embedding(n["tekst"]) for n in deel], normalize_embeddings=True, batch_size=32,
            show_progress_bar=False).astype(np.float32)))
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        print(f"ingebed: {min(begin + 2000, len(nieuw))} van {len(nieuw)} nieuwe", flush=True)
    if nieuw:
        opslag.mkdir(parents=True, exist_ok=True)
        nummers = list(vector)
        np.save(opslag / "vectoren.npy", np.stack([vector[n] for n in nummers]).astype(np.float32))
        (opslag / "nummers.json").write_text(json.dumps(nummers), encoding="utf-8")
    archief = json.loads((VECTOREN / "vectoren.json").read_text(encoding="utf-8"))
    xa = np.load(VECTOREN / "vectoren.npy") if archief.get("model") == versie else None
    from doublecheck import berichtcontrole as bc
    from doublecheck.speuren import eerste_dag_domeinen

    # de factchecksites zoals bij het speuren (#32.43): zonder nieuwsmedia met een eigen factcheckrubriek, die alleen tellen
    # met de rubriek in het adres; een gewoon artikel van de BBC of de VRT is geen factcheck
    domeinen = zonder_nieuwsmedia(eerste_dag_domeinen(bc.herkomstlijst()["sites"]))
    # de bekende namen uit het register van de nieuwste uitgave (alleen lezen); zonder uitgave geen namen
    uitgaven = sorted(PUBLICATIE.glob("20*/publicatie.db"))
    namen_index = bekende_namen(uitgaven[-1], wikidata=WIKIDATA) if uitgaven else None
    paden: list[Path] = []
    (MAP / "lijst").mkdir(parents=True, exist_ok=True)
    for begin, einde in weken_:
        per_taal, kernen, vectoren_, notes_ = {}, {}, {}, {}
        for taal in talen:
            week = sorted((n for n in alle if n["taal"] == taal and begin <= n["datum"] <= einde),
                          key=lambda n: (n["datum"], n["note"]))
            if not week:
                continue
            v = np.stack([vector[n["note"]] for n in week])
            groepen = groepeer(week, v)
            teksten = {n["note"]: n["tekst"] for n in week}
            index = {n["note"]: i for i, n in enumerate(week)}
            for g in groepen:
                samen = " ".join(teksten[n] for n in g["notes"])
                g["bronnen"] = bronnen(samen)
                g["gecheckt"] = al_gecheckt(samen, domeinen)
                g["geen_bewering"] = geen_bewering(g["tekst"])
                g["archief"] = None
                g["_kern"] = index[g["notes"][0]]
                g["namen"] = namen_in(samen, namen_index)[:3] if namen_index else []
            per_taal[taal] = zonder_weg([g for g in groepen if not g["geen_bewering"]], tips(WEG))
            kernen[taal] = np.stack([v[g["_kern"]] for g in per_taal[taal]]) if per_taal[taal] else np.empty((0, v.shape[1]))
            vectoren_[taal], notes_[taal] = v, (week, groepen)
        for taal, lijst in ook_in(kernen).items():
            for g, andere in zip(per_taal[taal], lijst):
                g["ook_in"] = andere
        kop_alle = {"van": begin, "tot": einde}
        for taal in (x for x in per_taal if x in lijsten):
            week, groepen = notes_[taal]
            v = vectoren_[taal]
            beweringen = per_taal[taal]
            per = onderwerpen(beweringen, v, [g["_kern"] for g in beweringen], sleutel=rangorde_radar)
            # het archief alleen voor wat op de lijst komt: een vraag per bewering
            for o in per[:MAX_ONDERWERPEN]:
                for g in o:
                    if xa is not None:
                        s = xa @ v[g["_kern"]]
                        beste = int(np.argmax(s))
                        if float(s[beste]) >= ARCHIEF_VLOER:
                            g["archief"] = {"pagina": archief["namen"][beste], "score": float(s[beste])}
            kop = {"van": min(n["datum"] for n in week), "tot": max(n["datum"] for n in week), "notes": len(week),
                   "posts": len({n["post"] for n in week})}
            uit = MAP / "lijst" / (f"{einde}.md" if taal == "nl" else f"{einde}-{taal}.md")
            uit.write_text(pagina(kop, per, [t for t in tips(TIPS) if kop["van"] <= t["datum"]] if taal == lijsten[0] else [],
                                  taal=taal), encoding="utf-8")
            print(f"{TAALNAAM[taal]}: {kop['notes']} notes op {kop['posts']} posts, {len(per)} onderwerpen: {uit.name}")
            paden.append(uit)
        if len(per_taal) > 1:
            uit = MAP / "lijst" / f"{einde}-talen.md"
            uit.write_text(overzicht(kop_alle, per_taal, kernen), encoding="utf-8")
            print(f"over de talen heen: {uit.name}")
            paden.append(uit)
    if melding and paden and sys.platform == "darwin":
        import subprocess

        subprocess.run(["osascript", "-e", f'display notification "{meldtekst(paden)}" with title "Factiz"'], check=False)
    return paden


def meldtekst(paden: list[Path]) -> str:
    """De tekst van de melding op de Mac: hoeveel lijsten, en waar de Engelse staat (PO 2026-11-22: "weet niet waar ik
    deze kan terugvinden"; sinds 2026-11-23 de enige lijst); zonder Engelse lijst de map. Zonder aanhalingstekens, die
    breken de opdracht voor osascript."""
    en = next((p for p in paden if p.stem.endswith("-en")), None)
    plek = (f"de Engelse in {en.relative_to(WORTEL).as_posix()}" if en
            else f"in {(MAP / 'lijst').relative_to(WORTEL).as_posix()}/")
    return f"De radar van deze week: {len(paden)} lijsten, {plek}".replace('"', "")


def _weg(nummers: list[str], taal: str, dag: str | None) -> None:  # pragma: no cover - bestanden
    """Haalt onderwerpen uit de lijst van een week (zonder `--tot` de nieuwste) en onthoudt hun posts en notes in `WEG`."""
    if not nummers or not all(n.isdigit() for n in nummers):
        raise SystemExit("weg vraagt de nummers van de onderwerpen, bijvoorbeeld: weg 4 5 8 11")
    # de nieuwste lijst in die taal: het Nederlands heet <dag>.md, een andere taal <dag>-<taal>.md (sinds B89 alleen Engels)
    patroon = r"\d{4}-\d{2}-\d{2}" + ("" if taal == "nl" else f"-{re.escape(taal)}")
    lijsten = sorted(p for p in (MAP / "lijst").glob("*.md") if re.fullmatch(patroon, p.stem))
    dag = dag or (lijsten[-1].stem[:10] if lijsten else None)
    pad = MAP / "lijst" / (f"{dag}.md" if taal == "nl" else f"{dag}-{taal}.md")
    if not dag or not pad.exists():
        raise SystemExit(f"geen lijst: {pad}")
    tekst, weg = haal_weg(pad.read_text(encoding="utf-8"), [int(n) for n in nummers])
    if len(weg) != len(set(nummers)):
        raise SystemExit(f"niet elk nummer staat in {pad.name}")
    pad.write_text(tekst, encoding="utf-8")
    with WEG.open("a", encoding="utf-8") as f:
        for w in weg:
            f.write(json.dumps({"dag": dag, "taal": taal, **w}, ensure_ascii=False) + "\n")
    print(f"{len(weg)} onderwerpen uit {pad.name}; ze komen niet terug")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="De radar van de eigen redactie (PLAN #37.1)")
    p.add_argument("stap", choices=["ophalen", "lijst", "tip", "weg"])
    p.add_argument("tekst", nargs="*", help="tip: wat er rondgaat; weg: de nummers die weg mogen")
    p.add_argument("--link", help="tip: waar het rondgaat")
    p.add_argument("--melding", action="store_true", help="lijst: een melding op de Mac")
    p.add_argument("--tot", help="lijst: een eerdere week, tot en met deze dag (JJJJ-MM-DD)")
    p.add_argument("--weken", type=int, default=1, help="lijst: ook zoveel weken terug, elk een eigen lijst")
    p.add_argument("--taal", default="alle", help="lijst: de talen die de radar leest: alle talen van de site, of een "
                   "paar als nl,en; weg: de lijst (standaard de Engelse)")
    p.add_argument("--lijsten", default=",".join(LIJSTEN), help="lijst: de talen waarvan een lijst op schijf komt "
                   "(standaard alleen het Engels, PO 2026-11-23)")
    a = p.parse_args()
    if a.stap == "ophalen":
        _ophalen()
    elif a.stap == "lijst":
        talen = TALEN if a.taal == "alle" else tuple(x.strip() for x in a.taal.split(",") if x.strip())
        onbekend = [x for x in talen if x not in TAALNAAM]
        if onbekend:
            raise SystemExit(f"geen taal van de site: {', '.join(onbekend)}")
        lijsten = tuple(x.strip() for x in a.lijsten.split(",") if x.strip())
        if not lijsten or any(x not in talen for x in lijsten):
            raise SystemExit("--lijsten moet een of meer talen uit --taal zijn")
        _lijst(a.melding, a.tot, a.weken, talen, lijsten)
    elif a.stap == "weg":
        _weg(a.tekst, LIJSTEN[0] if a.taal == "alle" else a.taal, a.tot)
    else:
        if not a.tekst:
            raise SystemExit("een tip vraagt een tekst")
        tip_erbij(TIPS, " ".join(a.tekst), link=a.link)
        print("tip erbij")


if __name__ == "__main__":  # pragma: no cover
    main()
