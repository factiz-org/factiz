"""De enige module die de publicatiedatabase leest. Alleen lezen, alleen vaste vragen met ingevulde waarden."""

from __future__ import annotations

import bisect
import heapq
import itertools
import json
import math
import re
import sqlite3
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import numpy as np

SCHEMA = 21      # 21: elke vertaling in het zoekregister en de woordenlijst als tabel `woord` (#37.16); 20: voorlopige vertalingen met een banner (B93); 19: de zinnen van de wereldlijst per taal (#37.12 punt 5); 18: de wereldlijst, wat de redacties vonden en waar het rondging (#37.12, B91); 17: pagina's buiten zoekmachines om een privépersoon (#34.2bw); 16: de zoekvraag per factcheck (#34.2cf, B87); 15: het adres van een eigen check met jaar en maand, en de gelezen vertalingen (#37.11); 14: de begrippen van een dossier (#34.2ca); 13: de eigen factchecks (#37.4, B82); 12: dezelfde bewering bij een andere redactie (#34.2bp); 11: een kolom per sitetaal voor vijftien talen (#34.2be, B79); 10: de soort volgens de redactie en de vorm (#34.2ak); 9: een bewering in hoofdletters in normaal schrift (#34.2ae); 6: de vertaalde woorden van een redactie en lijkt op (#34.2o, #34.2p); 7: waarom het niet klopt
#                  (#34.2j, B77); 8: de andere schrijfwijzen van een naam volgens Wikidata, voor het zoeken (#34.2z)
from factiz_site.i18n import TALEN as SITETALEN  # noqa: E402  de vijftien talen (B79)
EIGEN_BRON = "factiz-redactie"   # de eigen redactie als bron van het archief (#37.4, `publiceren.EIGEN_BRON`)
NUMMER = re.compile(r"[0-9a-f]{16}")
SLEUTEL = re.compile(r"[a-z][a-z0-9-]{1,39}")
QNUMMER = re.compile(r"Q[1-9][0-9]{0,11}")      # het nummer van een naam bij Wikidata (PLAN #33.7)
NAAMSOORTEN = ("persoon", "organisatie", "plaats")
ANDERE_LETTER = "0"                             # waar een naam staat die niet met een letter van a tot z begint
# Filters waarbij meer waarden tegelijk gekozen kunnen worden: binnen één filter is dat "of", tussen filters "en"
# (SPECS E9.S12). De andere filters hebben één waarde.
MEER = ("oordeel", "soort", "vorm", "taal", "jaar")     # in deze volgorde in het filterformulier
FACETTEN = ("thema", "onderdeel", "oordeel", "soort", "vorm", "taal", "jaar", "land", "redactie")
# De soort volgens de redactie en de vorm uit de woorden van de bewering (PLAN #34.2ak, SPECS E9.S19), in deze volgorde
# getoond; dezelfde waarden als de uitgave (`soortvorm` in het lab, de tabel `kenmerk`).
SOORTEN = ("bewerkt", "context", "verzonnen", "satire", "ai")
VORMEN = ("video", "beeld")
# Tekens die de leesrichting van wat volgt omdraaien of onzichtbaar sturen, en stuurtekens. Het verbindingsteken dat
# het Perzisch en de Indiase schriften nodig hebben (U+200C, U+200D) blijft, net als de gewone richtingsmarkering.
_STUUR = re.compile("[‪-‮⁦-⁩﻿\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


PER_BLAD = 25
# Een sitemap noemt hoogstens 50.000 adressen (sitemaps.org); daarboven een volgend deel (PLAN #34.2bt).
SITEMAP_DEEL = 50000


def uitgave_dag(release: str | None) -> str:
    """De dag van een uitgave uit haar naam (`2026-11-16b` is van 16 november), of leeg (PLAN #34.2bz)."""
    m = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2})[a-z]?", release or "")
    return m.group(1) if m else ""

MAX_VRAAG = 200          # tekens van een zoekvraag
MAX_TERMEN = 12
# een geplakt bericht (PLAN #34.2au, SPECS E9.S6 AC5): zoeken op de opvallendste woorden
MAX_PLAKTEKST = 1000     # tekens van een geplakt bericht
_RANDTEKENS = ".,;:!?¡¿…\"'“”‘’«»()[]"
MAX_PLAKWOORDEN = 80     # woorden van een geplakt bericht
BERICHT_WOORDEN = 6      # vanaf zoveel woorden is een vraag zonder treffer een bericht
BERICHT_TERMEN = 10      # de zeldzaamste woorden die tellen
BERICHT_GEWOON = 0.02    # een woord in meer dan dit deel van de pagina's telt niet
BERICHT_DEEL = 0.3       # een treffer heeft minstens dit deel van het gewicht van de beste
BERICHT_DEKKING = 0.4    # en minstens dit deel van de opvallende woorden van het bericht (gemeten, PLAN #34.2au)
BERICHT_MAX = 100        # hoogstens zoveel treffers
BERICHT_ZWAK = 10        # zonder treffer: hoogstens zoveel met de meeste van dezelfde woorden, en dat gezegd
MAX_KENMERK = 6          # woorden in de naam van een land, redactie, thema of onderdeel (#34.2ac)
AANVUL_MIN = 3           # letters van het woord dat je typt, voordat het zoeken het afmaakt (#34.2ac)
# Verkennen (PLAN #34.2ah, SPECS E9.S17): hoeveel jaren de tijd toont (tot het jaar van de nieuwste check) en hoeveel
# landen het waar; de verhouding alleen voor een land met genoeg factchecks, en genoeg over het thema, anders zegt één
# factcheck meer of minder al "twee keer zo vaak".
VERKEN_JAREN = 11
VERKEN_LANDEN = 10
VERHOUDING_LAND = 300
VERHOUDING_THEMA = 20
# Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18): de namen in de meeste factchecks, en een lijn tussen twee namen
# die samen in minstens zoveel factchecks staan.
NETWERK_NAMEN = 70
NETWERK_SAMEN = 25
LABELS = ("onwaar", "misleidend", "onwaar-of-misleidend", "waar", "deels-waar", "omstreden", "satire", "onbewezen")
# De volgordes van een lijst (SPECS E9.S10 AC2). Zonder keuze: de nieuwste eerst; bij zoeken de beste treffer eerst.
# Nieuw en oud sorteren op de datum die de lijst toont (de laatste check), anders lijkt de volgorde willekeurig. Een
# bewering zonder datum staat in elke volgorde achteraan.
VOLGORDES = {
    "nieuw": "p.laatste_datum DESC, p.nummer",
    "oud": "p.laatste_datum = '', p.laatste_datum, p.nummer",
    "redacties": "p.redacties DESC, p.laatste_datum DESC, p.nummer",
}
LIJST_VOLGORDES = ("oud", "redacties")           # naast de standaard (nieuw)
ZOEK_VOLGORDES = ("nieuw", "oud", "redacties")   # naast de standaard (de beste treffer)
_RIJ = ("p.nummer, p.bewering, p.taal, p.richting, p.label, p.checks, p.redacties, p.laatste_datum, p.thema, p.land, p.volgens, "
        "v.tekst AS vertaling, e.tekst AS vertaling_en")
# Bij elke rij twee vertalingen, als ze er liggen: die in de taal van de site (de eerste ingevulde waarde van de
# vraag) en de Engelse, voor waar de eerste ontbreekt (B32). Wat getoond wordt, beslist de app.
VERTAALTAAL = "en"
_MET_VERTALING = (" LEFT JOIN vertaling v ON v.pagina = p.nummer AND v.taal = ?"
                  f" LEFT JOIN vertaling e ON e.pagina = p.nummer AND e.taal = '{VERTAALTAAL}'")


class Ongeldig(Exception):
    """Het bestand is geen publicatiedatabase die deze site kent."""


def schoon(waarde):
    """Tekst uit de database komt uit het wild: stuurtekens gaan eruit voordat iets de pagina bereikt."""
    return _STUUR.sub("", waarde) if isinstance(waarde, str) else waarde


def _toetsenbord(tekst: str) -> str:
    """Wat een toetsenbord anders typt dan de tekst schrijft, gelijkgemaakt (#34.2be): brede letters en cijfers van een
    Chinees of Japans toetsenbord (ｖａｃｃｉｎｅ), en andere tekens voor dezelfde letter, met NFKC."""
    return unicodedata.normalize("NFKC", tekst)


# ی en ي, ک en ك (en ى aan het eind): dezelfde letter op een Perzisch en een Arabisch toetsenbord
_NAAR_PERZISCH = str.maketrans({"\u064a": "\u06cc", "\u0643": "\u06a9", "\u0649": "\u06cc"})
_NAAR_ARABISCH = str.maketrans({"\u06cc": "\u064a", "\u06a9": "\u0643"})


def toetsenbordvormen(stuk: str) -> list[str]:
    """Hetzelfde woord zoals een ander toetsenbord het typt: met Perzische of Arabische letters. Alleen de andere vormen."""
    return sorted({stuk.translate(_NAAR_PERZISCH), stuk.translate(_NAAR_ARABISCH)} - {stuk})


def zoektermen(vraag: str | None) -> list[str]:
    """De stukken van een zoekvraag: gesplitst op witruimte, niet op "woordtekens". Zo blijft een woord in het
    Devanagari of Tamil heel (daar hoort een klinkerteken bij het woord, en is het geen letter), en knipt het
    zoekregister elk stuk zelf op dezelfde manier als de tekst. Een stuk zonder letter of cijfer valt weg."""
    schone = _toetsenbord(schoon(vraag or ""))[:MAX_VRAAG]
    return [stuk for stuk in schone.split() if any(teken.isalnum() for teken in stuk)][:MAX_TERMEN]


def _zin(stuk: str) -> str:
    """Eén stuk als letterlijke zin voor het zoekregister: tussen aanhalingstekens kan niets een opdracht zijn."""
    return '"' + stuk.replace('"', " ") + '"'


# --- randgevallen (PLAN #34.2y) ----------------------------------------------------------------------------------
# Wat een lezer als hetzelfde woord ziet, vindt hetzelfde: enkelvoud en meervoud, aan elkaar of met een streepje,
# bijzondere letters die anders getypt worden, en de schrijfwijzen die het namenregister kent. Tussen aanhalingstekens
# precies wat er staat. Alles wordt aan de kant van de vraag gedaan, met de woorden die in het register staan: de
# uitgave verandert er niet voor. Wat precies zo geschreven staat, komt bovenaan.
_AANHALING = re.compile('["“”„«»]')
FAMILIE = 100        # een woord van zes letters of meer vindt ook de langere woorden die ermee beginnen, tot zoveel beweringen
MAX_VORMEN = 16      # andere vormen per stuk van de vraag, hoogstens
GEWOON = 10          # een schrijfwijze van een naam die zoveel keer vaker voorkomt dan de andere, is ook een gewoon woord
AFKORTING_ZEKER = 0.5  # een afkorting in hoofdletters is een naam als zoveel van haar pagina's aan die naam hangt (#34.2ab)
_ANDERS = {"ß": "ss", "œ": "oe", "æ": "ae", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "ı": "i", "þ": "th"}
_BIJZONDER = re.compile("[" + "".join(_ANDERS) + "]")
_LETTERS = re.compile("[a-z]+")
_MEDEKLINKER = frozenset("bcdfghjklmnpqrstvwxz")
# Een streepje binnen een stuk dat verder uit Latijnse letters en cijfers bestaat (COVID-19, e-mail). Geen punt: U.S.
# aan elkaar is us, en dat is een ander woord.
_GELEED = re.compile("[a-z0-9]+(?:[-‐‑–—][a-z0-9]+)+")
# Schriften waarin een woord geen grenzen heeft: daar zoekt de site op tekens, niet op woorden. Het Koreaans schrijft
# wel spaties en blijft bij het register op woorden.
_ZONDER_GRENS = re.compile("[฀-໿က-႟ក-៿぀-ヿ㐀-䶿一-鿿豈-﫿]")


_HOOFD = "A-ZÀ-ÖØ-Þ"
_LOS_IN_HOOFDLETTERS = re.compile(rf"(?<![^\W_])[{_HOOFD}]{{2,3}}(?![^\W_])")
_HOOFDWOORD = re.compile(rf"[{_HOOFD}]{{2}}")


def los_in_hoofdletters(tekst: str, woorden: set[str]) -> set[str]:
    """Welke van deze afkortingen los in hoofdletters in de tekst staan, niet midden in een kop die in hoofdletters
    staat: naast een ander woord in hoofdletters zegt een woord in hoofdletters niets (UN HOMBRE is "een man") (#34.2ab).
    WHO's telt; OMSzorg niet."""
    uit = set()
    for m in _LOS_IN_HOOFDLETTERS.finditer(tekst):
        w = m.group()
        if w not in woorden or w in uit:
            continue
        voor, na = tekst[max(0, m.start() - 3):m.start()], tekst[m.end():m.end() + 3]
        if (len(voor) == 3 and voor[2].isspace() and _HOOFDWOORD.fullmatch(voor[:2])) or \
                (len(na) == 3 and na[0].isspace() and _HOOFDWOORD.fullmatch(na[1:])):
            continue
        uit.add(w)
    return uit


def _is_afkorting(vorm: str, langst: int) -> bool:
    """Is dit een afkorting in hoofdletters: alleen letters, 2 tot `langst`, allemaal hoofdletters (PLAN #34.2ab)?"""
    v = (vorm or "").strip()
    return 2 <= len(v) <= langst and v.isalpha() and v.isupper()


def _lijkt(w: str, op: list[str]) -> bool:
    """Lijkt w op een van de woorden in `op`, met de maat van de schrijfwijzen van een naam (PLAN #34.2y)?"""
    return any(_afstand(_ascii(w), _ascii(k), max(2, len(_ascii(k)) // 3)) <= max(2, len(_ascii(k)) // 3) for k in op)


def bijnaam_telt(vorm: str, enkel: list[str]) -> bool:
    """Telt een bijnaam van een organisatie of plaats mee voor het zoeken (PLAN #34.2z)? Alleen een bijnaam van één
    woord die in hoofdletters geschreven is (NAVO, OTAN) of lijkt op een naam van één woord (Kyjiw bij Kyiv). Een
    afkorting met een punt nooit: zonder de punt lijkt Géorg. op een voornaam en Brés. op niets."""
    v = vorm.strip()
    if not v or v.endswith(".") or len(zoektermen(v)) != 1:
        return False
    w = v.strip(LEESTEKENS)
    return (w.isupper() and w.isalpha() and len(w) >= 4) or _lijkt(w, enkel)


def zoekdelen(vraag: str | None, lang: bool = False) -> list[tuple[str, bool]]:
    """De stukken van een zoekvraag, met bij elk of het precies zo bedoeld is. Wat tussen aanhalingstekens staat ("…",
    “…”, „…“, «…») is één stuk dat precies zo moet voorkomen: één woord zonder andere vormen, of meer woorden achter
    elkaar. Een aanhalingsteken zonder partner telt niet. De rest wordt gesplitst zoals `zoektermen`: op witruimte. `lang`
    is een geplakt bericht: meer tekens en meer woorden (#34.2au)."""
    schone = _toetsenbord(schoon(vraag or ""))[:MAX_PLAKTEKST if lang else MAX_VRAAG]
    stukken = _AANHALING.split(schone)
    if len(stukken) % 2 == 0:                  # een oneven aantal aanhalingstekens: het laatste is geen paar
        stukken[-2:] = [" ".join(stukken[-2:])]
    uit: list[tuple[str, bool]] = []
    for i, stuk in enumerate(stukken):
        woorden = [w for w in stuk.split() if any(t.isalnum() for t in w)]
        if i % 2 and woorden:
            uit.append((" ".join(woorden), True))
        else:
            uit += [(w, False) for w in woorden]
    return uit[:MAX_PLAKWOORDEN if lang else MAX_TERMEN]


def _indexvorm(tekst: str) -> str:
    """Een woord zoals het register op woorden het bewaart: kleine letters en zonder accenten. ß, œ en ł zijn daar geen
    accenten en blijven staan."""
    return "".join(t for t in unicodedata.normalize("NFD", tekst.lower()) if unicodedata.category(t) != "Mn")


def _ascii(tekst: str) -> str:
    """Het woord zoals iemand het typt zonder bijzondere letters: ß als ss, œ als oe, ł als l, ı als i."""
    return "".join(_ANDERS.get(t, t) for t in _indexvorm(tekst))


def woordrij(term: str, doc: int) -> tuple[str, int, int, int, str | None]:
    """Een rij van de tabel `woord` (#37.16): het woord uit het zoekregister, in hoeveel beweringen het staat, zijn lengte,
    of het een spelfout mag verbeteren of een woord afmaken (minstens twee beweringen, alleen letters), en bij een woord
    met een bijzondere letter hoe iemand het zonder typt (cœur onder coeur, straße onder strasse, #34.2y). De uitgave
    maakt de tabel met deze regel; Python en TypeScript lezen haar, zodat de Worker de woorden niet in zijn geheugen
    hoeft te houden (met elke vertaling 1,4 miljoen)."""
    gewoon = _ascii(term) if _BIJZONDER.search(term) else ""
    return term, doc, len(term), int(doc >= 2 and term.isalpha()), gewoon if len(gewoon) >= 4 else None


def _op(w: str) -> set[str]:
    """De vormen met een meervoudsuitgang erbij (zie `vormen`)."""
    uit = set()
    if len(w) >= 4:
        if not w.endswith("s"):
            uit.add(w + "s")
        if not w.endswith("e"):
            uit.add(w + "en")             # na een e is het meervoud -n, en -een een ander woord (crimeen)
        if w[-1] in _MEDEKLINKER:
            uit.add(w + "es")
        if w.endswith("y"):
            uit.add(w[:-1] + "ies")
        if w.endswith(("au", "eu")):
            uit.add(w + "x")
    if len(w) >= 5 and w.endswith("al"):
        uit.add(w[:-2] + "aux")
    if len(w) >= 6:
        uit.add(w + "n" if w.endswith("e") else w + "e")
    if len(w) >= 8 and w.endswith("um"):
        uit.add(w[:-2] + "a")
    return uit


def _af(w: str) -> set[str]:
    """De vormen met de meervoudsuitgang eraf: dezelfde regels als `_op`, terug."""
    uit = set()
    if w.endswith("s") and len(w) >= 5 and not w.endswith(("ss", "us", "is")):     # boss, virus en paris zijn enkelvoud
        uit.add(w[:-1])
    if w.endswith("es") and len(w) >= 6 and w[-3] in _MEDEKLINKER:
        uit.add(w[:-2])
    if w.endswith("en") and len(w) >= 6:
        uit.add(w[:-2])
    if w.endswith("e") and len(w) >= 7:
        uit.add(w[:-1])
    if w.endswith("en") and len(w) >= 7:
        uit.add(w[:-1])
    if w.endswith("ies") and len(w) >= 6:
        uit.add(w[:-3] + "y")
    if w.endswith("aux") and len(w) >= 6 and not w.endswith("eaux"):            # réseaux is réseau met een x
        uit.add(w[:-3] + "al")
    if w.endswith(("aux", "eux")) and len(w) >= 5:
        uit.add(w[:-1])
    if w.endswith("a") and len(w) >= 7:
        uit.add(w[:-1] + "um")
    return uit


def vormen(woord: str) -> set[str]:
    """Enkelvoud en meervoud van een woord in Latijnse letters, in de vijf talen van de site (PLAN #34.2y): de vormen
    met één meervoudsuitgang meer of minder. Alleen uitgangen die zelden een ander woord maken, en pas vanaf een
    lengte waarop dat zo blijft: -s, -en en -es (na een medeklinker) vanaf vier letters, -e en -n (na een e) vanaf zes,
    -y en -ies, -al en -aux, -au en -eu met een x, en -um en -a vanaf acht letters. Niet -a, -o of -er: dan wordt crime
    crimea en kind kinder. Een woord met een teken buiten a tot z (een ander schrift, een cijfer) heeft geen vormen."""
    w = _ascii(woord)
    if not _LETTERS.fullmatch(w):
        return set()
    return (_op(w) | _af(w)) - {w}


# Leestekens aan de rand van een woord tellen niet mee in een suggestie ("Trump," uit "Donald Trump, Jr.").
LEESTEKENS = ".,;:!?()[]{}\"'«»„“”‘’"


def _alfabet(naam: str) -> str:
    """Waarop een naam in het register gesorteerd wordt: zonder hoofdletters en zonder accenten, zodat Å bij de A
    staat en É bij de E."""
    return "".join(t for t in unicodedata.normalize("NFKD", naam.casefold()) if unicodedata.category(t) != "Mn").strip()


def _letter(naam: str) -> str:
    eerste = _alfabet(naam)[:1]
    return eerste if "a" <= eerste <= "z" else ANDERE_LETTER


# Spelfouten (PLAN #34.2i): in een schrift zonder spaties tussen woorden is een "woord" geen woord, dus daar niets verbeteren.
_ZONDER_SPATIES = re.compile("[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
                             "\uac00-\ud7af\uf900-\ufaff]")


def _afstand(a: str, b: str, grens: int) -> int:
    """Hoeveel letters a en b verschillen (invoegen, weglaten, vervangen, of twee buren omgedraaid), met een grens: alles
    erboven heet grens + 1, en dan stopt het rekenen."""
    if abs(len(a) - len(b)) > grens:
        return grens + 1
    vorige2: list[int] = []
    vorige = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        rij = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            rij[j] = min(vorige[j] + 1, rij[j - 1] + 1, vorige[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rij[j] = min(rij[j], vorige2[j - 2] + 1)
        if min(rij) > grens:
            return grens + 1
        vorige2, vorige = vorige, rij
    return vorige[-1]


def _rij(rij: sqlite3.Row) -> dict:
    return {sleutel: schoon(rij[sleutel]) for sleutel in rij.keys()}


class Publicatie:
    def __init__(self, pad: str | Path):
        self.pad = Path(pad).resolve()
        if not self.pad.is_file():
            raise Ongeldig(f"geen bestand: {self.pad}")
        self._lokaal = threading.local()
        self._woorden: tuple[set[str], dict[tuple[str, int], list[tuple[str, int]]]] | None = None   # pas bij de eerste spelfout
        self._woordslot = threading.Lock()
        try:
            meta = dict(self._conn().execute("SELECT sleutel, waarde FROM meta").fetchall())
        except sqlite3.DatabaseError as fout:
            raise Ongeldig(f"niet te lezen: {fout}") from None
        if meta.get("schema") != str(SCHEMA):
            raise Ongeldig(f"schema {meta.get('schema')!r}, deze site kent schema {SCHEMA}")
        self.release = meta.get("release", "")
        # de gemeten foutmarge van de punten van EUvsDisinfo, die de site bij het blok laat zien (B77)
        self.waarom_meting = json.loads(meta["waarom_meting"]) if meta.get("waarom_meting") else None
        c = self._conn()
        # een bewering in hoofdletters in normaal schrift, naast het citaat (#34.2ae): een paar honderd, in het geheugen
        self._normaal = {nr: schoon(t) for nr, t in c.execute("SELECT pagina, tekst FROM bewering_normaal")}
        # de soort volgens de redactie en de vorm (#34.2ak): een paar procent van de pagina's, in het geheugen
        self._kenmerk = {nr: (soort, vorm) for nr, soort, vorm in c.execute("SELECT pagina, soort, vorm FROM kenmerk")}
        self.tellingen = {
            "paginas": c.execute("SELECT COUNT(*) FROM pagina").fetchone()[0],
            "checks": c.execute("SELECT COUNT(*) FROM check_").fetchone()[0],
            "talen": c.execute("SELECT COUNT(DISTINCT taal) FROM pagina").fetchone()[0],
            "redacties": c.execute("SELECT COUNT(DISTINCT redactie) FROM check_").fetchone()[0],
        }
        # het bestand verandert niet zolang de site draait, dus dit hoeft één keer
        self._nieuwste = {taal: [self._bewering_rij(r) for r in c.execute(
            f"SELECT {_RIJ} FROM pagina p{_MET_VERTALING} "
            "WHERE p.laatste_datum <> '' ORDER BY p.laatste_datum DESC, p.nummer LIMIT 50", (taal,))]
            for taal in SITETALEN}
        self._bronnen = [_rij(r) for r in c.execute("SELECT * FROM bron ORDER BY bron")]
        # Waarop gefilterd kan worden, met de aantallen: één keer geteld.
        self.facetten = {
            "taal": [(r[0], r[1]) for r in c.execute(
                "SELECT taal, COUNT(*) FROM pagina GROUP BY taal ORDER BY COUNT(*) DESC, taal")],
            "jaar": [(r[0], r[1]) for r in c.execute(
                "SELECT substr(laatste_datum, 1, 4), COUNT(*) FROM pagina WHERE laatste_datum <> '' "
                "GROUP BY 1 ORDER BY 1 DESC")],
            "oordeel": [(r[0] or "geen", r[1]) for r in c.execute(
                "SELECT label, COUNT(*) FROM pagina GROUP BY label ORDER BY COUNT(*) DESC")],
            "redactie": [(schoon(r[0]), r[1]) for r in c.execute(
                "SELECT redactie, COUNT(DISTINCT pagina) FROM check_ GROUP BY redactie "
                "ORDER BY COUNT(DISTINCT pagina) DESC, redactie")],
        }
        # Thema's en landen (PLAN #33.4): alleen als het bestand ze draagt, en alleen wat een pagina heeft. Een
        # bewering met een tweede thema telt bij beide thema's; een onderdeel hoort bij het eerste thema.
        per_thema: dict[str, int] = {}
        for thema, tweede, n in c.execute(
                "SELECT thema, tweede, COUNT(*) FROM pagina WHERE thema IS NOT NULL GROUP BY thema, tweede"):
            for sleutel in {thema, tweede} - {""}:
                per_thema[sleutel] = per_thema.get(sleutel, 0) + n
        per_deel = {(r[0], r[1]): r[2] for r in c.execute(
            "SELECT thema, onderdeel, COUNT(*) FROM pagina WHERE onderdeel <> '' GROUP BY thema, onderdeel")}
        self.themas: list[dict] = []
        self._thema: dict[str, dict] = {}
        for r in (_rij(r) for r in c.execute("SELECT * FROM thema ORDER BY volg")):
            ding = {"sleutel": r["sleutel"], "ouder": r["ouder"], "naam": {t: r[f"naam_{t}"] for t in SITETALEN}}
            if r["ouder"] is None and per_thema.get(r["sleutel"]):
                ding.update(aantal=per_thema[r["sleutel"]], onderdelen=[])
                self.themas.append(ding)
                self._thema[ding["sleutel"]] = ding
            elif r["ouder"] in self._thema and per_deel.get((r["ouder"], r["sleutel"])):
                ding["aantal"] = per_deel[(r["ouder"], r["sleutel"])]
                self._thema[r["ouder"]]["onderdelen"].append(ding)
        self._deel = {(t["sleutel"], o["sleutel"]): o for t in self.themas for o in t["onderdelen"]}
        self.landen = {r["code"]: {t: r[f"naam_{t}"] for t in SITETALEN}
                       for r in (_rij(r) for r in c.execute("SELECT * FROM land"))}
        self.facetten["thema"] = [(t["sleutel"], t["aantal"]) for t in self.themas]
        self.facetten["land"] = [(r[0], r[1]) for r in c.execute(
            "SELECT land, COUNT(*) FROM pagina WHERE land <> '' GROUP BY land ORDER BY COUNT(*) DESC, land")
            if r[0] in self.landen]
        for wat, waarden, kolom in (("soort", SOORTEN, 0), ("vorm", VORMEN, 1)):
            telling = Counter(k[kolom] for k in self._kenmerk.values() if k[kolom])
            self.facetten[wat] = [(w, telling[w]) for w in waarden if telling[w]]
        self._bekend = {soort: {waarde for waarde, _ in rijen} for soort, rijen in self.facetten.items()}
        self._lijsten: dict[tuple, tuple[list[dict], int]] = {}
        self._facetvoorraad: dict[tuple, dict[str, dict[str, int]]] = {}
        self._bouw_kenmerken(c)
        # de nieuwste check in de uitgave: tot daar loopt het lopende jaar van Verkennen (#34.2ah)
        self.nieuwste_datum = c.execute("SELECT COALESCE(MAX(laatste_datum), '') FROM pagina").fetchone()[0]
        # hoeveel factchecks een thema hebben, elk één keer: het midden van de ring
        self.met_thema = int(np.sum(self._kolom["thema"] >= 0))
        # Dossiers (PLAN #33.6): het zijn er weinig, dus één keer gelezen. De kerngetallen worden hier uit de tabellen
        # gerekend en staan nergens getypt (SPECS E9.S7 AC5).
        self._dossier: dict[str, dict] = {}
        for r in (_rij(r) for r in c.execute("SELECT * FROM dossier ORDER BY sleutel")):
            self._dossier[r["sleutel"]] = {
                "sleutel": r["sleutel"], "soort": r["soort"], "concept": bool(r["concept"]), "thema": r["thema"],
                "onderdeel": r["onderdeel"], "naam": {t: r[f"naam_{t}"] for t in SITETALEN},
                "inleiding": {t: r[f"inleiding_{t}"] for t in SITETALEN},
                "vastgesteld": ({"door": r["vastgesteld_door"], "url": r["vastgesteld_url"],
                                 "datum": r["vastgesteld_datum"]} if r["vastgesteld_door"] else None),
                "stand": self._stand(c, r["sleutel"])}
        begrip: dict[str, dict[str, list[str]]] = {}
        for sleutel, taal, b in c.execute("SELECT dossier, taal, begrip FROM dossier_begrip ORDER BY dossier, taal, volg"):
            begrip.setdefault(sleutel, {}).setdefault(taal, []).append(b)
        for d in self._dossier.values():
            # de begrippen per taal van de site (#34.2ca); een taal zonder eigen begrippen valt terug op het Engels
            d["begrippen"] = begrip.get(d["sleutel"], {})
            d["verwant"] = [self._dossier[v] for (v,) in c.execute(
                "SELECT verwant FROM dossier_verwant WHERE dossier = ? ORDER BY verwant", (d["sleutel"],))
                if v in self._dossier]
        # in het overzicht: wat het laatst is aangevuld, staat boven
        self.dossiers = sorted(self._dossier.values(), key=lambda d: d["stand"]["laatste"], reverse=True)
        # de eigen factchecks (#37.4, B82): een handvol, in het geheugen; de gepubliceerde eerst, de nieuwste boven
        self.eigen = [{**json.loads(g), "concept": bool(concept)} for concept, g in c.execute(
            "SELECT concept, gegevens FROM eigen_check ORDER BY concept, datum DESC, sleutel")]
        # hun pagina's in het archief, met de eigen redactie als bron: een rij in een lijst krijgt het zegel (D12)
        # (pagina -> de sleutel van de check, via haar adres, PLAN #37.11)
        adressen = {pad: e["sleutel"] for e in self.eigen for pad in (e.get("paden") or {}).values()}
        self.eigen_paginas = {nr: adressen[urlsplit(url).path] for nr, url in c.execute(
            "SELECT pagina, url FROM check_ WHERE bron = ? ORDER BY pagina", (EIGEN_BRON,)) if urlsplit(url).path in adressen}
        self._van: dict[str, list[str]] = {}
        for nummer, sleutel in c.execute(
                "SELECT i.pagina, i.dossier FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier "
                "WHERE i.soort = 'factcheck' ORDER BY d.soort = 'netwerk', d.sleutel"):
            self._van.setdefault(nummer, []).append(sleutel)      # het verhaal eerst, dan de netwerken
        self._tijdlijnen: dict[tuple[str, str], list[dict]] = {}
        # Namen (PLAN #33.7): publieke personen, organisaties en plaatsen met hun nummer bij Wikidata. Eén keer gelezen;
        # het register staat per taal van de site op alfabet, zonder tellingen (SPECS E9.S11 AC5).
        self.namen_concept = bool(meta.get("namen_concept"))
        self._naam = {r["nummer"]: {"nummer": r["nummer"], "soort": r["soort"],
                                    "naam": {t: r[f"naam_{t}"] for t in SITETALEN}, "paginas": r["paginas"]}
                      for r in (_rij(r) for r in c.execute("SELECT * FROM naam"))}
        self._bekend["naam"] = set(self._naam)
        self._netwerk: dict[tuple[int, int], dict] = {}
        self._dossier_jaren: dict[str, dict[str, int]] = {}
        # de andere schrijfwijzen die Wikidata van een naam kent (PLAN #34.2z): alleen voor het zoeken, nooit getoond
        self._naamvormen: dict[str, list[str]] = {}
        for nummer, vorm in c.execute("SELECT naam, vorm FROM naam_vorm ORDER BY naam, vorm"):
            self._naamvormen.setdefault(nummer, []).append(vorm)
        self._register: dict[tuple[str, str], dict[str, list[dict]]] = {}
        for taal in SITETALEN:
            for soort in NAAMSOORTEN:
                per_letter: dict[str, list[dict]] = {}
                for n in sorted((n for n in self._naam.values() if n["soort"] == soort),
                                key=lambda n: (_alfabet(n["naam"][taal]), int(n["nummer"][1:]))):
                    per_letter.setdefault(_letter(n["naam"][taal]), []).append(n)
                self._register[(taal, soort)] = dict(sorted(per_letter.items(), key=lambda x: (x[0] == ANDERE_LETTER, x[0])))

        # Ingangen (SPECS E9.S12): een zoekvraag die precies een thema, dossier, redactie of naam is, wijst naar de pagina
        # die alles daarover bij elkaar heeft. Bij een persoon volstaat een deel van de naam dat bij niemand anders hoort.
        self._ingang: dict[str, list[dict]] = {}
        self._naam_ingang: dict[str, dict] = {}        # per nummer de ingang van een naam (voor een afkorting, #34.2ab)

        def ingang(tekst: str, wat: dict) -> None:
            sleutel = _alfabet(" ".join(zoektermen(tekst)))
            if sleutel and wat not in self._ingang.setdefault(sleutel, []):
                self._ingang[sleutel].append(wat)

        for th in self.themas:
            wat = {"soort": "thema", "thema": th["sleutel"], "naam": th["naam"], "aantal": th["aantal"]}
            for taal in SITETALEN:
                ingang(th["naam"][taal], wat)
            for o in th["onderdelen"]:
                deel = {"soort": "onderdeel", "thema": th["sleutel"], "onderdeel": o["sleutel"], "naam": o["naam"],
                        "aantal": o["aantal"]}
                for taal in SITETALEN:
                    ingang(o["naam"][taal], deel)
        for d in self.dossiers:
            wat = {"soort": "dossier", "sleutel": d["sleutel"], "naam": d["naam"], "aantal": d["stand"]["factchecks"]}
            for taal in SITETALEN:
                ingang(d["naam"][taal], wat)
        for redactie, n in self.facetten["redactie"]:
            ingang(redactie, {"soort": "redactie", "redactie": redactie, "naam": redactie, "aantal": n})
        delen: dict[str, list[dict]] = {}
        for n in self._naam.values():
            wat = {"soort": "naam", "nummer": n["nummer"], "naamsoort": n["soort"], "naam": n["naam"], "aantal": n["paginas"]}
            self._naam_ingang[n["nummer"]] = wat
            for taal in SITETALEN:
                ingang(n["naam"][taal], wat)
                if n["soort"] == "persoon":
                    for stuk in zoektermen(n["naam"][taal]):
                        sleutel = _alfabet(stuk)
                        if len(sleutel) >= 4 and wat not in delen.setdefault(sleutel, []):
                            delen[sleutel].append(wat)
        # een deel van de naam van een persoon ("trump", "selenskyj"): de personen met dat deel, de vaakst genoemde eerst
        self._ingang_deel = {sleutel: sorted(lijst, key=lambda w: -w["aantal"]) for sleutel, lijst in delen.items()}
        # Suggesties tijdens het typen (PLAN #34.2b): per ingang de woorden van haar naam in elke taal, zonder accenten,
        # zodat "zel" Zelensky vindt en "selen" Selenskyj. Een paar duizend ingangen: doorlopen kost een paar ms.
        self._suggestie: list[tuple[frozenset[str], dict]] = []
        gezien: set[str] = set()
        for lijst in self._ingang.values():
            for wat in lijst:
                sleutel = repr(sorted((k, str(v)) for k, v in wat.items() if k != "naam"))
                if sleutel in gezien:
                    continue
                gezien.add(sleutel)
                namen = wat["naam"].values() if isinstance(wat["naam"], dict) else [wat["naam"]]
                woorden = frozenset(s for naam in namen for w in zoektermen(naam) if (s := _alfabet(w).strip(LEESTEKENS)))
                self._suggestie.append((woorden, wat))
        self._schrijfwijzen = self._bouw_schrijfwijzen()
        self._afkortingen = self._bouw_afkortingen()
        self._afkortingskeuze: dict[str, dict | None] = {}
        self._afkortingslot = threading.Lock()
        # waar elke afkorting los in hoofdletters staat: een keer de hele tekst lezen (~2 s), in een eigen draad, zodat
        # het openen er niet op wacht. Tot dat klaar is, leest het zoeken een afkorting niet als naam
        self._hoofdletters: dict[str, set[str]] = {}
        self._hoofdletters_klaar = threading.Event()
        self._kenmerken = self._bouw_kenmerknamen()          # land, redactie, thema en onderdeel in een vraag (#34.2ac)
        self._kenmerksets: dict[tuple, str] = {}             # per kenmerk en woord de verzameling, de laatste 64
        self._kenmerkslot = threading.Lock()
        self._adressen: dict[str, str] | None = None         # de adressen van de factcheckartikelen, bij de eerste link
        self._adresslot = threading.Lock()
        self._voorvoegsels: tuple[list[str], list[int]] | None = None    # de woorden op volgorde, om af te maken
        self._woordenlijst()             # bij het openen, zodat geen lezer erop wacht (#34.2y)
        threading.Thread(target=self._bouw_hoofdletters, daemon=True).start()   # als laatste: het openen wacht er niet op

    def _bewering_rij(self, r: sqlite3.Row) -> dict:
        """Een rij met een bewering, met haar normale schrift als ze in hoofdletters rondging (#34.2ae)."""
        rij = _rij(r)
        rij["normaal"] = self._normaal.get(rij.get("nummer"))
        rij["kenmerk"] = self._kenmerk.get(rij.get("nummer"))
        return rij

    def _bouw_kenmerknamen(self) -> dict[tuple[str, ...], dict]:
        """De namen die een stuk van de vraag verruimen (PLAN #34.2ac, SPECS E9.S14 AC3): een land, een redactie, een
        thema en een onderdeel, in de vijf talen van de site, als de woorden zonder hoofdletters en accenten. Een naam
        die bij twee verschillende dingen hoort, telt voor geen van beide: twijfel verruimt niets."""
        uit: dict[tuple[str, ...], dict] = {}
        dubbel: set[tuple[str, ...]] = set()

        def zet(naam: str, wat: dict) -> None:
            sleutel = tuple(s for w in zoektermen(naam) if (s := _alfabet(w).strip(LEESTEKENS)))
            if not sleutel or len(sleutel) > MAX_KENMERK:
                return
            if sleutel in uit and uit[sleutel] != wat:
                dubbel.add(sleutel)
            uit.setdefault(sleutel, wat)

        for code, _ in self.facetten["land"]:
            for taal in SITETALEN:
                zet(self.landen[code][taal], {"soort": "land", "waarde": code})
        for redactie, _ in self.facetten["redactie"]:
            zet(redactie, {"soort": "redactie", "waarde": redactie})
        for th in self.themas:
            for taal in SITETALEN:
                zet(th["naam"][taal], {"soort": "thema", "waarde": th["sleutel"]})
                for o in th["onderdelen"]:
                    zet(o["naam"][taal], {"soort": "onderdeel", "waarde": o["sleutel"], "thema": th["sleutel"]})
        return {k: v for k, v in uit.items() if k not in dubbel}

    def _lees_kenmerken(self, delen: list[tuple[str, bool]]) -> tuple[list[tuple[str, bool]], dict[int, dict]]:
        """De stukken van de vraag met de namen van een land, redactie, thema of onderdeel samengenomen tot één stuk, en
        bij welk stuk welk kenmerk hoort. De langste naam eerst ("Sri Lanka" voor een kortere); nooit tussen
        aanhalingstekens, en nooit een afkorting in hoofdletters: die is al een naam (#34.2ab)."""
        uit: list[tuple[str, bool]] = []
        kenmerken: dict[int, dict] = {}
        i = 0
        while i < len(delen):
            gevonden = None
            if not delen[i][1]:
                for lengte in range(min(MAX_KENMERK, len(delen) - i), 0, -1):
                    stuk = delen[i:i + lengte]
                    if any(p for _, p in stuk):
                        continue
                    sleutel = tuple(_alfabet(t).strip(LEESTEKENS) for t, _ in stuk)
                    if sleutel in self._kenmerken and not (lengte == 1 and self.afkorting(stuk[0][0]) is not None):
                        gevonden = (lengte, self._kenmerken[sleutel])
                        break
            if gevonden:
                lengte, wat = gevonden
                kenmerken[len(uit)] = wat
                uit.append((" ".join(t for t, _ in delen[i:i + lengte]), False))
                i += lengte
            else:
                uit.append(delen[i])
                i += 1
        return uit, kenmerken

    def _kenmerk_voorwaarde(self, wat: dict, match: str) -> tuple[str, list]:
        """Het stuk verruimd: het woord, of het kenmerk. Nooit een versmalling: wat het woord vond, blijft. De verzameling
        komt uit het geheugen (dezelfde rijen als de filters, `_masker`) en het register op woorden, één keer per kenmerk
        en woord, zodat de vraag geen hele tabel doorloopt."""
        sleutel = (wat["soort"], wat["waarde"], wat.get("thema", ""), match)
        with self._kenmerkslot:
            lijst = self._kenmerksets.get(sleutel)
        if lijst is None:
            filters = {"land": {"land": wat["waarde"]}, "redactie": {"redactie": wat["waarde"]},
                       "thema": {"thema": wat["waarde"]},
                       "onderdeel": {"thema": wat.get("thema"), "onderdeel": wat["waarde"]}}[wat["soort"]]
            m = self._masker(filters)
            plekken = [self._plek[n] for (n,) in self._conn().execute("SELECT nummer FROM zoek WHERE zoek MATCH ?", (match,))
                       if n in self._plek]
            m[plekken] = True
            lijst = json.dumps(self._op_plek[m].tolist())
            with self._kenmerkslot:
                if len(self._kenmerksets) >= 64:
                    self._kenmerksets.pop(next(iter(self._kenmerksets)))
                self._kenmerksets[sleutel] = lijst
        return "p.nummer IN (SELECT value FROM json_each(?))", [lijst]

    def _bouw_schrijfwijzen(self) -> dict[str, tuple[str, ...]]:
        """De schrijfwijzen van één naam in de vijf talen van de site (PLAN #34.2y), uit het namenregister en de landen:
        Zelensky, Zelenskyy, Selenskyj en Zelenski; Kiev, Kyiv en Kiew; Oekraïne, Ukraine en Ucrania. Van een persoon
        telt de achternaam (het laatste woord), en alleen als die in de andere talen op elkaar lijkt: Melinda Gates heet
        in het Spaanse register Melinda French, en dat is een ander woord. Van een plaats, organisatie of land telt een
        naam van één woord; een naam van meer woorden heeft niet in elke taal dezelfde volgorde (Verenigde Staten,
        Estados Unidos). Woorden van minder dan vier letters doen niet mee (WHO, OMS).
        Een schrijfwijze die meer dan `GEWOON` keer zo vaak voorkomt als de andere van haar naam, is ook een gewoon
        woord (Said bij Saied, Sind bij Sindh, Ganz bij Gantz) en wordt nooit toegevoegd. Een schrijfwijze die in drie
        talen gelijk is, staat vanzelf twee tot drie keer zo vaak in het register als de Nederlandse of Duitse (Paris en
        Parijs, Berlin en Berlijn), want niet elke bewering heeft een Nederlandse of Duitse vertaling.
        En een vraag krijgt er alleen schrijfwijzen bij die minstens zo vaak voorkomen als de hare: wie Oekraïne typt,
        krijgt Ukraine en Ucrania erbij (die staan in bijna elke bewering, het Nederlands in minder dan de helft), maar wie
        India typt niet het Nederlandse indien, dat ook "als" betekent.
        De bijnamen die Wikidata kent (PLAN #34.2z, `naam_vorm`) komen erbij met dezelfde maat. Van een persoon het laatste
        woord, als het lijkt op een achternaam die al telt; zo ook een achternaam uit de vijf namen die verder van de
        meest gebruikte af staat (Loekasjenko via Loukachenko). Eén stap, niet verder: Jr., een vadersnaam als
        Grigorevich en een naam in een ander schrift vallen weg. Van een organisatie of plaats een bijnaam van één woord,
        als hij lijkt op een naam van één woord (Kyjiw bij Kyiv) of in hoofdletters geschreven is (NAVO, OTAN); Capital
        bij Kyiv en World bij de aarde dus niet.
        Per schrijfwijze zonder bijzondere letters: de schrijfwijzen die er dan bij komen. Uit de uitgave, niet uit een
        vraag; één keer geteld bij het openen."""
        groepen: list[list[str]] = []
        for nummer, n in self._naam.items():
            stukken = [zoektermen(n["naam"][taal]) for taal in SITETALEN]
            vormen = self._naamvormen.get(nummer, [])
            if n["soort"] == "persoon":
                laatste = [s[-1].strip(LEESTEKENS) for s in stukken if s]
                if not laatste:
                    continue
                vaakst = Counter(_ascii(w) for w in laatste).most_common(1)[0][0]
                grens = max(2, len(vaakst) // 3)
                kern = [w for w in laatste if _afstand(_ascii(w), vaakst, grens) <= grens]
                verder = [w for w in laatste if w not in kern]
                verder += [s[-1].strip(LEESTEKENS) for s in (zoektermen(v) for v in vormen) if s and s[-1][-1] != "."]
                groepen.append(kern + [w for w in verder if _lijkt(w, kern)])
            else:
                enkel = [s[0] for s in stukken if len(s) == 1]
                groepen.append(enkel + [v.strip().strip(LEESTEKENS) for v in vormen if bijnaam_telt(v, enkel)])
        for namen in self.landen.values():
            groepen.append([s[0] for s in (zoektermen(namen[taal]) for taal in SITETALEN) if len(s) == 1])
        c = self._conn()
        hoe_vaak: dict[str, int] = {}

        def tel(w: str) -> int:
            if (vorm := _indexvorm(w)) not in hoe_vaak:
                try:
                    hoe_vaak[vorm] = c.execute("SELECT COUNT(*) FROM zoek WHERE zoek MATCH ?", (_zin(w),)).fetchone()[0]
                except sqlite3.OperationalError:
                    hoe_vaak[vorm] = 0
            return hoe_vaak[vorm]

        uit: dict[str, dict[str, None]] = {}
        for groep in groepen:
            groep = sorted({w.strip(LEESTEKENS) for w in groep})
            groep = [w for w in groep if len(_ascii(w)) >= 4 and any(t.isalpha() for t in w)]
            if len({_indexvorm(w) for w in groep}) < 2:
                continue
            gewoon = {w for w in groep
                      if tel(w) > GEWOON * max(1, *(tel(o) for o in groep if _indexvorm(o) != _indexvorm(w)))}
            for w in groep:
                eigen = max(tel(o) for o in groep if _ascii(o) == _ascii(w))
                for o in groep:
                    if _ascii(o) != _ascii(w) and o not in gewoon and tel(o) >= eigen:
                        uit.setdefault(_ascii(w), {})[o] = None
        return {sleutel: tuple(andere) for sleutel, andere in uit.items()}

    def _bouw_afkortingen(self) -> dict[str, set[str]]:
        """De afkortingen van 2 of 3 letters van de namen, zoals iemand ze in hoofdletters typt (PLAN #34.2ab): WHO, OMS
        en WGO voor de Wereldgezondheidsorganisatie, uit de vijf namen en de bijnamen. Per afkorting de namen die haar
        dragen. Of ze echt die naam is, rekent `afkorting` pas uit bij de eerste vraag. Een langere afkorting (NATO) loopt
        al via de schrijfwijzen van 34.2z."""
        uit: dict[str, set[str]] = {}
        for nummer, n in self._naam.items():
            for v in {*n["naam"].values(), *self._naamvormen.get(nummer, [])}:
                if _is_afkorting(v, 3):
                    uit.setdefault(v.strip(), set()).add(nummer)
        return uit

    def _bouw_hoofdletters(self) -> None:
        """Per afkorting de pagina's waar ze los in hoofdletters staat, in de bewaarde tekst van het register (die kent
        hoofdletters, het register zelf niet). Lukt dat niet, dan blijft de index leeg en geldt geen afkorting als naam
        (twijfel versoepelt nooit)."""
        index: dict[str, set[str]] = {}
        try:
            woorden = set(self._afkortingen)
            c = sqlite3.connect(f"{self.pad.as_uri()}?mode=ro&immutable=1", uri=True)
            try:
                for nummer, tekst in c.execute("SELECT c0, c1 FROM zoek_content"):
                    for w in los_in_hoofdletters(tekst or "", woorden):
                        index.setdefault(w, set()).add(nummer)
            finally:
                c.close()
            self._hoofdletters = index
        except sqlite3.Error:
            self._hoofdletters = {}
        finally:
            self._hoofdletters_klaar.set()

    def afkortingen_klaar(self, wacht: float | None = None) -> bool:
        """Is de index van de afkortingen in hoofdletters klaar? Met `wacht` hoogstens zoveel seconden erop wachten
        (de randproef en de tests; de server wacht niet)."""
        return self._hoofdletters_klaar.wait(wacht)

    def _in_hoofdletters(self, woord: str) -> set[str] | None:
        """De pagina's waar dit woord los in hoofdletters staat, niet in een kop die helemaal in hoofdletters staat;
        `None` zolang de index niet klaar is."""
        if not self._hoofdletters_klaar.is_set():
            return None
        return self._hoofdletters.get(woord, set())

    def afkorting(self, stuk: str) -> dict | None:
        """Is dit stuk van de vraag, zo getypt, de afkorting van een naam (PLAN #34.2ab)? Alleen 2 of 3 letters in
        hoofdletters, van precies één naam, en alleen als de afkorting in de uitgave vooral die naam is: van de pagina's
        waar ze in hoofdletters staat, is minstens `AFKORTING_ZEKER` aan de naam gekoppeld. WHO haalt dat (89%), AFP
        niet (25%, daar is het meestal het persbureau). Dan wat de naam vindt: haar pagina's in het namenregister; waar
        een van haar zekere afkortingen in hoofdletters staat; en haar namen in de vijf talen en haar andere vormen,
        een andere vorm alleen als ook die vooral bij de naam staat (zo niet *the States* bij de Verenigde Staten).
        Eén keer uitgerekend, daarna onthouden."""
        a = (stuk or "").strip(LEESTEKENS)
        if not _is_afkorting(a, 3):
            return None
        with self._afkortingslot:
            if a in self._afkortingskeuze:
                return self._afkortingskeuze[a]
        uit = None
        namen = self._afkortingen.get(a) or set()
        if len(namen) == 1:
            nummer = next(iter(namen))
            c = self._conn()
            gekoppeld = {r[0] for r in c.execute("SELECT pagina FROM pagina_naam WHERE naam = ?", (nummer,))}

            def zeker(paginas: set[str]) -> bool:
                return len(paginas & gekoppeld) >= AFKORTING_ZEKER * len(paginas)

            hoofd = self._in_hoofdletters(a)
            if hoofd is None:
                return None                     # de index is er nog niet: niet als naam, en niets onthouden
            if gekoppeld and (not hoofd or zeker(hoofd)):
                n = self._naam[nummer]
                namen_ = [v for v in n["naam"].values() if not _is_afkorting(v, 3)]
                hoofdletters = set(hoofd)
                tekst = sorted(set(namen_))
                enkel = [st[0] for st in (zoektermen(x) for x in namen_) if len(st) == 1]
                for v in sorted(set(self._naamvormen.get(nummer, []))):
                    v = v.strip()
                    if _is_afkorting(v, 3):
                        if v != a and len(self._afkortingen.get(v) or ()) == 1:
                            hb = self._in_hoofdletters(v)
                            if hb and zeker(hb):
                                hoofdletters |= hb
                        continue
                    if v in tekst or (len(zoektermen(v)) < 2 and not bijnaam_telt(v, enkel)):
                        continue
                    try:
                        paginas = {r[0] for r in c.execute("SELECT nummer FROM zoek WHERE zoek MATCH ?", (_zin(v),))}
                    except sqlite3.OperationalError:
                        continue
                    if paginas and zeker(paginas):
                        tekst.append(v)
                uit = {"nummer": nummer, "tekst": tekst, "hoofdletters": sorted(hoofdletters)}
        with self._afkortingslot:
            self._afkortingskeuze[a] = uit
        return uit

    @staticmethod
    def _stand(c: sqlite3.Connection, sleutel: str) -> dict:
        """*Waar staan we nu*: geteld uit de factchecks in het dossier en hun checks."""
        binnen = "(SELECT pagina FROM dossier_item WHERE dossier = ? AND soort = 'factcheck')"
        eerste, laatste, redacties = c.execute(
            f"SELECT MIN(NULLIF(datum, '')), MAX(datum), COUNT(DISTINCT redactie) FROM check_ WHERE pagina IN {binnen}",
            (sleutel,)).fetchone()
        talen: set[str] = set()
        for (lijst,) in c.execute(f"SELECT talen FROM pagina WHERE nummer IN {binnen}", (sleutel,)):
            talen.update(json.loads(lijst or "[]"))
        aantal, laatste_item = c.execute(
            "SELECT SUM(soort = 'factcheck'), MAX(datum) FROM dossier_item WHERE dossier = ?", (sleutel,)).fetchone()
        return {"factchecks": aantal or 0, "eerste": eerste or "", "talen": len(talen - {"und"}),
                "redacties": redacties or 0, "laatste": max(laatste or "", laatste_item or "")}

    def _conn(self) -> sqlite3.Connection:
        """Eén verbinding per draad, alleen-lezen en onveranderlijk geopend: schrijven kan niet."""
        conn = getattr(self._lokaal, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"{self.pad.as_uri()}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            self._lokaal.conn = conn
        return conn

    def nieuwste(self, n: int = 10, vertaal: str = VERTAALTAAL) -> list[dict]:
        return self._nieuwste.get(vertaal, self._nieuwste[VERTAALTAAL])[:n]

    def bronnen(self) -> list[dict]:
        return list(self._bronnen)

    def verwijzing(self, nummer: str) -> str | None:
        if not NUMMER.fullmatch(nummer or ""):
            return None
        rij = self._conn().execute("SELECT pagina FROM verwijzing WHERE nummer = ?", (nummer,)).fetchone()
        return rij[0] if rij else None

    def pagina(self, nummer: str) -> dict | None:
        if not NUMMER.fullmatch(nummer or ""):
            return None
        c = self._conn()
        rij = c.execute("SELECT * FROM pagina WHERE nummer = ?", (nummer,)).fetchone()
        if rij is None:
            return None
        p = _rij(rij)
        rijen = c.execute("SELECT taal, tekst, voorlopig FROM vertaling WHERE pagina = ?", (nummer,)).fetchall()
        p["vertalingen"] = {taal: schoon(tekst) for taal, tekst, _ in rijen}
        # een voorlopige vertaling (B93): op de pagina met een banner, nooit voor een zoekmachine
        p["voorlopig"] = {taal for taal, _, voorlopig in rijen if voorlopig}
        p["normaal"] = self._normaal.get(nummer)
        p["kenmerk"] = self._kenmerk.get(nummer)
        # de vraag zoals een zoeker haar typt (#34.2cf, B87): per pagina opgevraagd, niet in het geheugen
        vraag = c.execute("SELECT taal, vraag, onderwerp FROM zoekvraag WHERE pagina = ?", (nummer,)).fetchone()
        p["zoekvraag"] = _rij(vraag) if vraag else None
        # maatregel 2 (#34.2bw): een privépersoon in een gevoelige context, of nog niet gelezen; nooit in een zoekmachine
        p["afgeschermd"] = c.execute("SELECT 1 FROM afscherming WHERE pagina = ?", (nummer,)).fetchone() is not None
        p["checks_lijst"] = self._checks(nummer)
        p["formuleringen"] = [_rij(r) for r in c.execute(
            "SELECT nummer, tekst, taal, richting FROM formulering WHERE pagina = ? ORDER BY nummer", (nummer,))]
        p["opgedoken"] = [_rij(r) for r in c.execute(
            "SELECT o.naam, o.soort, o.niveau, o.datum, o.url, b.naam AS bron_naam FROM opgedoken o "
            "JOIN bron b ON b.bron = o.bron WHERE o.pagina = ? ORDER BY o.datum DESC, o.naam LIMIT 200", (nummer,))]
        gebruikt = {k["bron"] for k in p["checks_lijst"]}
        p["bronnen"] = [b for b in self._bronnen if b["bron"] in gebruikt]
        return p

    def _checks(self, nummer: str) -> list[dict]:
        """De checks van een pagina in de volgorde van de uitgave, elk met de woorden van de redactie letterlijk vertaald
        (#34.2o); witruimte telt niet."""
        c = self._conn()
        checks = [_rij(r) for r in c.execute("SELECT * FROM check_ WHERE pagina = ? ORDER BY volg", (nummer,))]
        for k in checks:
            k["glossen"] = {taal: schoon(glos) for taal, glos in c.execute(
                "SELECT taal, glos FROM oordeel_glos WHERE tekst = ?", (" ".join((k["oordeel_eigen"] or "").split()),))}
        return checks

    @staticmethod
    def _sitemap_waar(taal: str, stand: int, schema: int = SCHEMA) -> tuple[str, list]:
        """Welke pagina's in deze taal en stand vindbaar zijn, als SQL (PLAN #34.2bt, SPECS E9.S8 AC3, DESIGNSYSTEEM §6).
        Stand 3: de taal van de bewering of een vertaling erin (`i18n.eigen_talen`), en in het Engels ook een pagina zonder
        eigen taal en zonder vertaling in een sitetaal. Stand 2: elke pagina één keer, in de taal van haar bewering als dat
        een sitetaal is, anders waar `x_default` heen wijst: het Engels als dat er is, anders de eerste sitetaal met een
        vertaling. Stand 1: zoals 2, alleen de kern (B73 punt 5): meer dan één redactie, Ook gecheckt door, of in een
        dossier. In geen stand een afgeschermde pagina (#34.2bw), en een voorlopige vertaling (B93) telt niet. `schema` is
        dat van de uitgave: IndexNow legt de vorige ernaast, en die kan ouder zijn (afscherming sinds 17, voorlopig sinds
        20); één nummer in plaats van een schakelaar per schema."""
        talen = list(SITETALEN)
        tl = ",".join("?" * len(talen))
        # een voorlopige vertaling (B93) telt niet: zoekmachines zien haar niet
        geldig = " AND v.voorlopig = 0" if schema >= 20 else ""
        heeft = f"EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer AND v.taal = ?{geldig})"
        geen = lambda deel: (f"NOT EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer{geldig} AND v.taal IN "
                             f"({','.join('?' * len(deel))}))") if deel else "1"
        vreemd = f"p.taal NOT IN ({tl})"
        if stand == 3:
            waar, args = f"p.taal = ? OR {heeft}", [taal, taal]
        else:
            eerder = talen[:talen.index(taal)]
            waar = f"p.taal = ? OR ({vreemd} AND {heeft} AND {geen(eerder)})"
            args = [taal, *talen, taal, *eerder]
        if taal == "en":
            waar += f" OR ({vreemd} AND {geen(talen)})"
            args += [*talen, *talen]
        if stand == 1:
            waar = (f"({waar}) AND (p.redacties > 1 OR EXISTS (SELECT 1 FROM zelfde z WHERE z.pagina = p.nummer) "
                    "OR EXISTS (SELECT 1 FROM dossier_item d WHERE d.pagina = p.nummer AND d.soort = 'factcheck'))")
        if schema >= 17:
            waar = f"({waar}) AND NOT EXISTS (SELECT 1 FROM afscherming a WHERE a.pagina = p.nummer)"
        return waar, args

    def sitemap_telling(self, taal: str, stand: int) -> int:
        waar, args = self._sitemap_waar(taal, stand)
        return self._conn().execute(f"SELECT COUNT(*) FROM pagina p WHERE {waar}", args).fetchone()[0]

    def sitemap_deel(self, taal: str, stand: int, deel: int) -> list[tuple[str, str | None]]:
        """Het deel van de factchecks voor de sitemap, op nummer: (nummer, de datum van de nieuwste check)."""
        waar, args = self._sitemap_waar(taal, stand)
        return [(r[0], r[1]) for r in self._conn().execute(
            f"SELECT p.nummer, p.laatste_datum FROM pagina p WHERE {waar} ORDER BY p.nummer LIMIT ? OFFSET ?",
            [*args, SITEMAP_DEEL, deel * SITEMAP_DEEL])]

    def sitemap_namen(self) -> list[str]:
        """De namen met een eigen pagina, op nummer; in een uitgave met namen als concept geen."""
        return [] if self.namen_concept else sorted(self._naam)

    def zelfde(self, nummer: str, vertaal: str = VERTAALTAAL) -> list[dict]:
        """*Ook gecheckt door* (#34.2bp, SPECS E9.S31): de andere pagina's met dezelfde bewering bij een andere redactie,
        elk met haar checks. Een verwijzing: elke pagina houdt haar eigen bewering en oordeel (DR2, DR5)."""
        if not NUMMER.fullmatch(nummer or ""):
            return []
        rijen = [self._bewering_rij(r) for r in self._conn().execute(
            f"SELECT {_RIJ}, p.eerste_datum FROM zelfde z JOIN pagina p ON p.nummer = z.ander{_MET_VERTALING} "
            "WHERE z.pagina = ? ORDER BY z.volg", (vertaal, nummer))]
        for r in rijen:
            r["checks_lijst"] = self._checks(r["nummer"])
        return rijen

    def waarom(self, nummer: str) -> dict | None:
        """*Waarom het niet klopt* (#34.2j, B77): hoogstens drie punten uit de weerlegging van EUvsDisinfo, in volgorde,
        met de link naar de case; niets als de uitgave er geen heeft."""
        if not NUMMER.fullmatch(nummer or ""):
            return None
        rijen = self._conn().execute("SELECT punt, url FROM waarom WHERE pagina = ? ORDER BY volg", (nummer,)).fetchall()
        return {"punten": [r[0] for r in rijen], "url": rijen[0][1]} if rijen else None

    def samenvatting(self, nummer: str, taal: str, brontaal: str) -> dict | None:
        """Bij een overzicht van de wereldlijst (#37.12, B91): wat de redacties vonden en waar het rondging, in volgorde,
        elke zin met de links van de checks die haar dragen; in `taal` als die vertaling er is (punt 5), anders in de taal
        van het overzicht. Niets bij elke andere pagina."""
        if not NUMMER.fullmatch(nummer or ""):
            return None
        rijen = self._conn().execute("SELECT taal, soort, zin, bronnen FROM samenvatting WHERE pagina = ? AND taal IN (?, ?) "
                                     "ORDER BY volg", (nummer, taal, brontaal)).fetchall()
        gekozen = taal if any(r[0] == taal for r in rijen) else brontaal
        zinnen = [{"soort": s, "zin": z, "bronnen": json.loads(b)} for t_, s, z, b in rijen if t_ == gekozen]
        return {"taal": gekozen, "brontaal": brontaal, "rijen": zinnen} if zinnen else None

    def lijkt_op(self, nummer: str, vertaal: str = VERTAALTAAL) -> list[dict]:
        """*Lijkt op* (#34.2p): de andere pagina's over hetzelfde verhaal, in de volgorde van de uitgave (de hoogste
        score eerst). Een verwijzing: elke pagina houdt haar eigen bewering en oordeel."""
        if not NUMMER.fullmatch(nummer or ""):
            return []
        return [self._bewering_rij(r) for r in self._conn().execute(
            f"SELECT {_RIJ}, p.eerste_datum FROM lijkt_op l JOIN pagina p ON p.nummer = l.ander{_MET_VERTALING} "
            "WHERE l.pagina = ? ORDER BY l.volg", (vertaal, nummer))]

    def dossier_jaren(self, sleutel: str) -> dict[str, int]:
        """Per jaar hoeveel factchecks van een dossier er zijn (het jaar van de laatste check), voor de contextkaart
        (PLAN #34.2an); een factcheck zonder datum telt niet mee."""
        if sleutel not in self._dossier_jaren:
            self._dossier_jaren[sleutel] = dict(sorted(Counter(
                d[:4] for (d,) in self._conn().execute(
                    "SELECT p.laatste_datum FROM dossier_item i JOIN pagina p ON p.nummer = i.pagina "
                    "WHERE i.dossier = ? AND i.soort = 'factcheck'", (sleutel,)) if d[:4].isdigit()).items()))
        return self._dossier_jaren[sleutel]

    def dossier(self, sleutel: str) -> dict | None:
        return self._dossier.get(sleutel) if SLEUTEL.fullmatch(sleutel or "") else None

    @property
    def heeft_namen(self) -> bool:
        return bool(self._naam)

    def naam(self, nummer: str) -> dict | None:
        return self._naam.get(nummer) if QNUMMER.fullmatch(nummer or "") else None

    def netwerk(self) -> dict:
        """Het netwerk van namen (SPECS E9.S18): de `NETWERK_NAMEN` namen in de meeste factchecks (bij gelijke aantallen
        het laagste nummer van Wikidata eerst), per naam het thema waarin hij het vaakst voorkomt (een tweede thema telt
        mee; bij gelijkspel het eerste thema van de uitgave), en elk paar dat samen in minstens `NETWERK_SAMEN`
        factchecks staat. Eén keer per uitgave gerekend, in het geheugen: dezelfde vraag in SQL kost een seconde."""
        sleutel = (NETWERK_NAMEN, NETWERK_SAMEN)
        if sleutel not in self._netwerk:
            top = sorted(self._naam.values(), key=lambda n: (-n["paginas"], int(n["nummer"][1:])))[:NETWERK_NAMEN]
            ids = [n["nummer"] for n in top]
            per_pagina: dict[str, list[str]] = {}
            per_thema: dict[str, Counter] = {q: Counter() for q in ids}
            if ids:
                vraag = ",".join("?" * len(ids))
                # het thema per pagina staat al in het geheugen (`_bouw_kenmerken`); een JOIN met pagina kost seconden
                thema_van = self._waarde["thema"]
                for pagina, naam in self._conn().execute(
                        f"SELECT pagina, naam FROM pagina_naam WHERE naam IN ({vraag})", ids):
                    per_pagina.setdefault(pagina, []).append(naam)
                    plek = self._plek.get(pagina)
                    if plek is None:
                        continue
                    for code in {int(self._kolom["thema"][plek]), int(self._kolom["tweede"][plek])} - {-1}:
                        if thema_van[code] in self._thema:
                            per_thema[naam][thema_van[code]] += 1
            samen: Counter = Counter()
            for namen in per_pagina.values():
                samen.update(itertools.combinations(sorted(namen), 2))
            volg = {t["sleutel"]: i for i, t in enumerate(self.themas)}
            thema = {q: min(c, key=lambda t: (-c[t], volg[t])) if c else None for q, c in per_thema.items()}
            self._netwerk[sleutel] = {
                "namen": [(n["nummer"], n["paginas"], thema[n["nummer"]]) for n in top],
                "randen": sorted((a, b, k) for (a, b), k in samen.items() if k >= NETWERK_SAMEN)}
        return self._netwerk[sleutel]

    def namen_van(self, nummer: str) -> list[dict]:
        """De namen bij een factcheck, in de volgorde waarin ze bij de bewering genoemd zijn."""
        if not self._naam or not NUMMER.fullmatch(nummer or ""):
            return []
        return [self._naam[q] for (q,) in self._conn().execute(
            "SELECT naam FROM pagina_naam WHERE pagina = ? ORDER BY volg", (nummer,)) if q in self._naam]

    def letters(self, taal: str, soort: str) -> list[str]:
        """De letters waaronder dit soort namen staat, in de taal van de site."""
        return list(self._register.get((taal, soort), {}))

    def register(self, taal: str, soort: str, letter: str) -> list[dict]:
        return self._register.get((taal, soort), {}).get(letter, [])

    def dossiers_van(self, nummer: str) -> list[dict]:
        """De dossiers waar deze factcheck in staat: hoogstens één verhaal, daarna de netwerken."""
        return [self._dossier[s] for s in self._van.get(nummer, ())]

    def toeschrijvingen(self, nummer: str) -> list[dict]:
        """Aan welk netwerk een netwerkdossier deze factcheck toeschrijft, met de bron die deze factcheck aan het netwerk
        koppelt (B62, PLAN #34.2h): per factcheck, niet die van het netwerk als geheel. Alleen dossiers die op de site staan."""
        if not NUMMER.fullmatch(nummer or ""):
            return []
        rijen = self._conn().execute(
            "SELECT i.dossier, i.bron, i.url, i.niveau FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier "
            "WHERE i.pagina = ? AND i.soort = 'factcheck' AND d.soort = 'netwerk' AND i.bron <> '' ORDER BY i.dossier",
            (nummer,))
        return [{"sleutel": r["dossier"], "bron": r["bron"], "url": r["url"], "niveau": r["niveau"]}
                for r in rijen if r["dossier"] in self._dossier]

    def varianten(self, nummer: str, vertaal: str = VERTAALTAAL) -> dict | None:
        """*Komt ook voor als*: de andere factchecks van dezelfde versie in het verhaaldossier (hetzelfde bericht in
        andere woorden of een andere taal, door een mens goedgekeurd), op de datum van hun eerste check. Met de telling
        over de hele versie, deze pagina erbij: hoeveel checks, in hoeveel talen. Niets als de pagina geen versie heeft."""
        if not NUMMER.fullmatch(nummer or ""):
            return None
        c = self._conn()
        eigen = c.execute(
            "SELECT i.dossier, i.versie FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier "
            "WHERE i.pagina = ? AND i.soort = 'factcheck' AND i.versie <> '' AND d.soort = 'verhaal'", (nummer,)).fetchone()
        if eigen is None:
            return None
        binnen = "(SELECT pagina FROM dossier_item WHERE dossier = ? AND versie = ? AND soort = 'factcheck')"
        rijen = [self._bewering_rij(r) for r in c.execute(
            f"SELECT {_RIJ}, p.eerste_datum FROM pagina p{_MET_VERTALING} WHERE p.nummer IN {binnen} AND p.nummer <> ? "
            "ORDER BY p.eerste_datum = '', p.eerste_datum, p.nummer", (vertaal, eigen[0], eigen[1], nummer))]
        if not rijen:
            return None
        redacties: dict[str, list[str]] = {}
        for pagina, redactie in c.execute(
                f"SELECT DISTINCT pagina, redactie FROM check_ WHERE pagina IN {binnen} ORDER BY redactie", (eigen[0], eigen[1])):
            redacties.setdefault(pagina, []).append(schoon(redactie))
        for r in rijen:
            r["redactienamen"] = redacties.get(r["nummer"], [])
        checks = c.execute(f"SELECT COUNT(*) FROM check_ WHERE pagina IN {binnen}", (eigen[0], eigen[1])).fetchone()[0]
        talen: set[str] = set()
        for (lijst,) in c.execute(f"SELECT talen FROM pagina WHERE nummer IN {binnen}", (eigen[0], eigen[1])):
            talen.update(json.loads(lijst or "[]"))
        return {"rijen": rijen, "checks": checks, "talen": len(talen - {"und"})}

    def dossiers_bij(self, thema: str, onderdeel: str | None = None) -> list[dict]:
        return [d for d in self.dossiers if d["thema"] == thema and (onderdeel is None or d["onderdeel"] == onderdeel)]

    def tijdlijn(self, sleutel: str, vertaal: str = VERTAALTAAL) -> list[dict]:
        """De items van een dossier in de volgorde van het bestand: de nieuwste boven, zonder datum onderaan. Een
        factcheck draagt de rij van zijn pagina (zoals in een lijst, met de vertalingen) en zijn redacties."""
        if (sleutel, vertaal) in self._tijdlijnen:
            return self._tijdlijnen[(sleutel, vertaal)]
        c = self._conn()
        redacties: dict[str, list[str]] = {}
        for nummer, redactie in c.execute(
                "SELECT DISTINCT k.pagina, k.redactie FROM check_ k JOIN dossier_item i ON i.pagina = k.pagina "
                "WHERE i.dossier = ? ORDER BY k.redactie", (sleutel,)):
            redacties.setdefault(nummer, []).append(schoon(redactie))
        items = []
        for r in (self._bewering_rij(r) for r in c.execute(
                f"SELECT i.soort AS item_soort, i.datum AS item_datum, {', '.join(f'i.titel_{t}' for t in SITETALEN)}, "
                f"i.bron, i.url, i.niveau, {_RIJ} FROM dossier_item i "
                f"LEFT JOIN pagina p ON p.nummer = i.pagina{_MET_VERTALING} WHERE i.dossier = ? ORDER BY i.volg",
                (vertaal, sleutel))):
            factcheck = r["item_soort"] == "factcheck" and r["nummer"] is not None
            items.append({
                "soort": r["item_soort"], "datum": r["item_datum"], "titel": {t: r[f"titel_{t}"] for t in SITETALEN},
                "bron": r["bron"], "url": r["url"], "niveau": r["niveau"],
                "rij": {k: r[k] for k in ("nummer", "bewering", "taal", "richting", "label", "checks", "redacties",
                                          "laatste_datum", "vertaling", "vertaling_en", "volgens")} if factcheck else None,
                "redacties": redacties.get(r["nummer"], []) if factcheck else []})
        self._tijdlijnen[(sleutel, vertaal)] = items
        return items

    def kent(self, soort: str, waarde: str) -> bool:
        return waarde in self._bekend.get(soort, ())

    def thema(self, sleutel: str) -> dict | None:
        """Een thema uit de vaste lijst dat minstens één pagina heeft."""
        return self._thema.get(sleutel)

    def deel(self, thema: str, sleutel: str) -> dict | None:
        """Een onderdeel, alleen bij het thema waar het onder hoort."""
        return self._deel.get((thema, sleutel))

    @staticmethod
    def _waar(filters: dict, zonder: tuple[str, ...] = ()) -> tuple[list[str], list] | None:
        """De filters als vaste stukken SQL met hun ingevulde waarden; niets als de keuze niets kan opleveren. Een
        filter uit `MEER` mag een rijtje waarden hebben (een van die waarden volstaat). `zonder` laat filters buiten
        beschouwing: zo telt een filter zichzelf niet mee in zijn eigen aantallen."""
        f = {k: v for k, v in filters.items() if v not in (None, "", ()) and k not in zonder}

        def rij(waarde) -> list[str]:
            return list(waarde) if isinstance(waarde, (tuple, list)) else [waarde]

        waar, waarden = [], []
        if "taal" in f:
            talen = rij(f["taal"])
            waar.append(f"p.taal IN ({', '.join('?' * len(talen))})")
            waarden += talen
        if "jaar" in f:
            jaren = rij(f["jaar"])
            waar.append(f"substr(p.laatste_datum, 1, 4) IN ({', '.join('?' * len(jaren))})")
            waarden += jaren
        if "oordeel" in f:
            oordelen = rij(f["oordeel"])
            echte = [o for o in oordelen if o != "geen"]
            stukken = ([f"p.label IN ({', '.join('?' * len(echte))})"] if echte else []) + (
                ["p.label IS NULL"] if "geen" in oordelen else [])
            waar.append("(" + " OR ".join(stukken) + ")")
            waarden += echte
        if "redactie" in f:
            waar.append("p.nummer IN (SELECT pagina FROM check_ WHERE redactie = ?)")
            waarden.append(f["redactie"])
        for wat in ("soort", "vorm"):
            if wat in f:
                keuze = rij(f[wat])
                waar.append(f"p.nummer IN (SELECT pagina FROM kenmerk WHERE {wat} IN ({', '.join('?' * len(keuze))}))")
                waarden += keuze
        if "onderdeel" in f:
            if "thema" not in f:
                return None                    # een onderdeel bestaat alleen binnen zijn thema
            waar.append("p.thema = ? AND p.onderdeel = ?")
            waarden += [f["thema"], f["onderdeel"]]
        elif "thema" in f:
            waar.append("(p.thema = ? OR p.tweede = ?)")
            waarden += [f["thema"], f["thema"]]
        if "land" in f:
            waar.append("p.land = ?")
            waarden.append(f["land"])
        if "naam" in f:
            waar.append("p.nummer IN (SELECT pagina FROM pagina_naam WHERE naam = ?)")
            waarden.append(f["naam"])
        return waar, waarden

    def _bouw_kenmerken(self, c: sqlite3.Connection) -> None:
        """Per factcheck de kenmerken waarop gefilterd wordt, als getallen in het geheugen (een paar megabyte): zo telt
        de site de aantallen bij elke filterwaarde in een paar milliseconden, ook bij tienduizenden factchecks."""
        rijen = c.execute("SELECT nummer, taal, substr(laatste_datum, 1, 4), COALESCE(label, 'geen'), land, "
                          "COALESCE(thema, ''), tweede, onderdeel FROM pagina ORDER BY nummer").fetchall()
        self._plek = {r[0]: i for i, r in enumerate(rijen)}
        self._op_plek = np.array([r[0] for r in rijen])        # het nummer op elke plek (voor een verruimd stuk, #34.2ac)
        self._code: dict[str, dict[str, int]] = {}
        self._waarde: dict[str, list[str]] = {}
        kolom: dict[str, np.ndarray] = {}
        for soort, i in (("taal", 1), ("jaar", 2), ("oordeel", 3), ("land", 4), ("thema", 5), ("tweede", 6)):
            alle = sorted({r[i] for r in rijen} - {""})
            if soort == "tweede":                 # het tweede thema gebruikt de codes van het thema
                code = self._code["thema"]
            else:
                code = {w: n for n, w in enumerate(alle)}
                self._code[soort], self._waarde[soort] = code, alle
            kolom[soort] = np.fromiter((code.get(r[i], -1) for r in rijen), dtype=np.int32, count=len(rijen))
        delen = sorted({(r[5], r[7]) for r in rijen if r[5] and r[7]})
        self._code["onderdeel"] = {d: n for n, d in enumerate(delen)}
        self._waarde["onderdeel"] = [d[1] for d in delen]
        kolom["onderdeel"] = np.fromiter((self._code["onderdeel"].get((r[5], r[7]), -1) for r in rijen), dtype=np.int32,
                                         count=len(rijen))
        for wat, waarden, plek in (("soort", SOORTEN, 0), ("vorm", VORMEN, 1)):
            self._code[wat], self._waarde[wat] = {w: n for n, w in enumerate(waarden)}, list(waarden)
            kolom[wat] = np.fromiter((self._code[wat].get((self._kenmerk.get(r[0]) or ("", ""))[plek], -1) for r in rijen),
                                     dtype=np.int32, count=len(rijen))
        self._kolom = kolom
        paren = c.execute("SELECT DISTINCT pagina, redactie FROM check_").fetchall()
        alle = sorted({schoon(r[1]) for r in paren})
        self._code["redactie"], self._waarde["redactie"] = {w: n for n, w in enumerate(alle)}, alle
        self._redactie_plek = np.fromiter((self._plek[r[0]] for r in paren), dtype=np.int64, count=len(paren))
        self._redactie_code = np.fromiter((self._code["redactie"][schoon(r[1])] for r in paren), dtype=np.int32,
                                          count=len(paren))

    def _masker(self, filters: dict, zonder: tuple[str, ...] = ()) -> np.ndarray:
        """Welke factchecks door de filters komen, als een rij van waar en onwaar; dezelfde regels als `_waar`."""
        f = {k: v for k, v in filters.items() if v not in (None, "", ()) and k not in zonder}
        n = len(self._plek)
        m = np.ones(n, dtype=bool)

        def codes(soort: str, waarde) -> list[int]:
            rij = waarde if isinstance(waarde, (tuple, list)) else [waarde]
            return [self._code[soort][w] for w in rij if w in self._code[soort]]

        for soort in ("taal", "jaar", "oordeel", "land", "soort", "vorm"):
            if soort in f:
                m &= np.isin(self._kolom[soort], codes(soort, f[soort]))
        if "onderdeel" in f:
            m &= self._kolom["onderdeel"] == self._code["onderdeel"].get((f.get("thema"), f["onderdeel"]), -2)
        elif "thema" in f:
            c = self._code["thema"].get(f["thema"], -2)
            m &= (self._kolom["thema"] == c) | (self._kolom["tweede"] == c)
        if "redactie" in f:
            r = np.zeros(n, dtype=bool)
            r[self._redactie_plek[self._redactie_code == self._code["redactie"].get(f["redactie"], -2)]] = True
            m &= r
        if "naam" in f:
            r = np.zeros(n, dtype=bool)
            plekken = [self._plek[p] for (p,) in self._conn().execute(
                "SELECT pagina FROM pagina_naam WHERE naam = ?", (f["naam"],)) if p in self._plek]
            r[plekken] = True
            m &= r
        return m

    def _tel_facetten(self, basis: np.ndarray | None, filters: dict) -> dict[str, dict[str, int]]:
        """Per filter hoeveel factchecks elke waarde heeft binnen wat nu getoond wordt (`basis`: de treffers van een
        zoekvraag, of alles) en binnen alle andere filters. Het filter zelf telt niet mee, zodat er een tweede waarde
        bij gekozen kan worden."""
        uit: dict[str, dict[str, int]] = {}

        def masker(*zonder: str) -> np.ndarray:
            m = self._masker(filters, zonder)
            return m & basis if basis is not None else m

        def tel(soort: str, m: np.ndarray, kolom: np.ndarray | None = None) -> dict[str, int]:
            k = (self._kolom[soort] if kolom is None else kolom)[m]
            k = k[k >= 0]
            aantallen = np.bincount(k, minlength=len(self._waarde[soort]))
            return {self._waarde[soort][i]: int(a) for i, a in enumerate(aantallen) if a}

        for soort in ("taal", "jaar", "oordeel", "land", "soort", "vorm"):
            uit[soort] = tel(soort, masker(soort))
        m = masker("thema", "onderdeel")
        thema = self._kolom["thema"][m]
        tweede = self._kolom["tweede"][m]
        tweede = tweede[(tweede >= 0) & (tweede != thema)]
        aantallen = np.bincount(thema[thema >= 0], minlength=len(self._waarde["thema"])) + np.bincount(
            tweede, minlength=len(self._waarde["thema"]))
        uit["thema"] = {self._waarde["thema"][i]: int(a) for i, a in enumerate(aantallen) if a}
        uit["onderdeel"] = {}
        if filters.get("thema"):
            m = masker("onderdeel") & (self._kolom["thema"] == self._code["thema"].get(filters["thema"], -2))
            uit["onderdeel"] = tel("onderdeel", m)
        m = masker("redactie")
        codes = self._redactie_code[m[self._redactie_plek]]
        aantallen = np.bincount(codes, minlength=len(self._waarde["redactie"]))
        uit["redactie"] = {self._waarde["redactie"][i]: int(a) for i, a in enumerate(aantallen) if a}
        return uit

    def facetten_van(self, **filters) -> dict[str, dict[str, int]]:
        """De aantallen per filterwaarde voor een lijst met deze filters. Het bestand verandert niet, dus een antwoord
        blijft geldig."""
        sleutel = tuple(sorted(filters.items()))
        if sleutel not in self._facetvoorraad:
            if len(self._facetvoorraad) > 2000:
                self._facetvoorraad.clear()
            self._facetvoorraad[sleutel] = self._tel_facetten(None, filters)
        return self._facetvoorraad[sleutel]

    def verkennen(self, thema: str | None = None) -> dict:
        """Wat Verkennen toont (PLAN #34.2ah, SPECS E9.S17), met dezelfde tellingen als de filters van de lijst: per jaar
        de laatste `VERKEN_JAREN` tot het jaar van de nieuwste check, wat ervoor ligt en wat geen datum heeft, en de landen
        met hun aantal. Met een thema alles binnen dat thema (een tweede thema telt mee, zoals op de lijst)."""
        if thema:
            tel = self.facetten_van(thema=thema)
            jaren, landen, totaal = tel["jaar"], tel["land"], self._thema[thema]["aantal"]
        else:
            jaren, landen, totaal = dict(self.facetten["jaar"]), dict(self.facetten["land"]), self.tellingen["paginas"]
        jaren = {j: n for j, n in jaren.items() if len(j) == 4 and j.isdigit()}
        landen = {c: n for c, n in landen.items() if c in self.landen}
        laatste = int(self.nieuwste_datum[:4]) if self.nieuwste_datum[:4].isdigit() else None
        reeks = [] if laatste is None else [str(j) for j in range(laatste - VERKEN_JAREN + 1, laatste + 1)]
        eerder = sum(n for j, n in jaren.items() if reeks and j < reeks[0])
        return {"totaal": totaal, "jaren": [(j, jaren.get(j, 0)) for j in reeks], "eerder": eerder,
                "zonder_datum": totaal - sum(jaren.values()),
                "landen": sorted(landen.items(), key=lambda r: (-r[1], r[0])),
                "met_land": sum(landen.values())}

    def verhoudingen(self, thema: str, hoeveel: int | None = -1) -> list[tuple[str, float, int, int]]:
        """Per land hoe vaak het thema voorkomt bij de factchecks over dat land, gedeeld door hoe vaak het voorkomt bij
        alle factchecks met een land (SPECS E9.S17 AC4): (land, verhouding, aantal over het thema, aantal over het land),
        de hoogste eerst, alleen voor een land boven beide drempels."""
        alle = {c: n for c, n in self.facetten["land"]}
        binnen = {c: n for c, n in self.facetten_van(thema=thema)["land"].items() if c in alle}
        t, n = sum(binnen.values()), sum(alle.values())
        if not t:
            return []
        rijen = [(c, (a / alle[c]) / (t / n), a, alle[c]) for c, a in binnen.items()
                 if alle[c] >= VERHOUDING_LAND and a >= VERHOUDING_THEMA]
        rijen.sort(key=lambda r: (-r[1], -r[2], r[0]))
        # zonder `hoeveel` de top van `VERKEN_LANDEN`; met `hoeveel=None` allemaal, voor de kaart (#34.2am)
        return rijen if hoeveel is None else rijen[:VERKEN_LANDEN if hoeveel == -1 else hoeveel]

    def lijst(self, *, blad: int = 1, vertaal: str = VERTAALTAAL, sorteer: str | None = None,
              **filters) -> tuple[list[dict], int]:
        """De factchecks met de filters die gezet zijn, in de gekozen volgorde (zonder keuze de nieuwste eerst). De
        vraag is opgebouwd uit vaste stukken; elke waarde gaat als ingevulde waarde mee. Het bestand verandert niet,
        dus een antwoord blijft geldig."""
        volgorde = VOLGORDES[sorteer if sorteer in LIJST_VOLGORDES else "nieuw"]
        sleutel = (tuple(sorted(filters.items())), sorteer, blad, vertaal)
        if sleutel in self._lijsten:
            return self._lijsten[sleutel]
        stukken = self._waar(filters)
        if stukken is None:
            return [], 0
        waar, waarden = stukken
        filter_ = (" WHERE " + " AND ".join(waar)) if waar else ""
        c = self._conn()
        totaal = c.execute(f"SELECT COUNT(*) FROM pagina p{filter_}", waarden).fetchone()[0]
        rijen = [self._bewering_rij(r) for r in c.execute(
            f"SELECT {_RIJ} FROM pagina p{_MET_VERTALING}{filter_} ORDER BY {volgorde} LIMIT ? OFFSET ?",
            (vertaal, *waarden, PER_BLAD, (blad - 1) * PER_BLAD))]
        if len(self._lijsten) > 5000:
            self._lijsten.clear()
        self._lijsten[sleutel] = (rijen, totaal)
        return rijen, totaal

    def _groep(self, stuk: str, precies: bool) -> tuple[str, str, list[str]]:
        """Eén stuk van de vraag voor het register op woorden (PLAN #34.2y): de voorwaarde met de andere vormen erbij,
        de voorwaarde voor precies dit stuk, en wat in de tekst gemarkeerd wordt. Andere vormen alleen van een stuk in
        Latijnse letters, en alleen woorden die in het register staan: enkelvoud en meervoud (`vormen`), dezelfde letters
        anders getypt (oeuvre, œuvre), aan elkaar of met een streepje (covid19, COVID-19; Corona-Virus, Coronavirus),
        de schrijfwijzen van een naam (`_bouw_schrijfwijzen`), en bij een woord van zes letters of meer de langere woorden
        die ermee beginnen, zolang die samen in hoogstens `FAMILIE` beweringen staan. Tussen aanhalingstekens: niets
        anders dan het stuk zelf."""
        exact = _zin(stuk)
        if precies:
            return exact, exact, [stuk]
        if (afkorting := self.afkorting(stuk)) is not None:
            # een afkorting in hoofdletters is een naam (#34.2ab): haar pagina's in het namenregister, en haar namen
            tekst = afkorting["tekst"]
            match = "(" + " OR ".join(_zin(t) for t in tekst) + ")" if tekst else exact
            return match, match, [stuk, *tekst], afkorting
        alle, _, bijzonder = self._woordenlijst()

        def bestaand(woord: str) -> list[str]:
            return ([woord] if woord in alle else []) + bijzonder.get(woord, [])

        woorden: list[str] = []          # andere vormen die in het register staan
        zinnen: list[str] = []           # andere schrijfwijzen, als zin (meer woorden achter elkaar mag)
        begin = None
        a = _ascii(stuk).strip(LEESTEKENS)
        if _GELEED.fullmatch(a):                                       # COVID-19 → covid19, e-mail → email
            woorden += bestaand("".join(re.findall("[a-z0-9]+", a)))
        elif re.fullmatch("[a-z0-9]+", a) and not a.isalpha() and not a.isdigit():
            zinnen.append(" ".join(re.findall("[a-z]+|[0-9]+", a)))    # covid19 → covid 19, 5G → 5 g
        namen = self._schrijfwijzen.get(a, ())
        if _LETTERS.fullmatch(a):
            woorden += bestaand(a)                                     # coeur → cœur, Strasse → straße
            basis = [a] + sorted(k for k in _af(a) if bestaand(k))
            for b in basis:
                for v in sorted({b} | _op(b)):
                    woorden += bestaand(v)
            kortste = min(basis, key=len)
            if len(kortste) >= 6 and self._familie(kortste) <= FAMILIE:
                begin = kortste
            if len(a) >= 8:                                            # Coronavirus → corona virus
                for i in range(4, len(a) - 3):
                    links, rechts = bestaand(a[:i]), bestaand(a[i:])
                    if links and rechts:
                        zinnen.append(f"{links[0]} {rechts[0]}")
        zinnen += namen
        zinnen += toetsenbordvormen(stuk)                              # کرونا ↔ كرونا (#34.2be)
        eigen = _indexvorm(stuk)
        andere: list[str] = []
        for x in woorden + zinnen:
            if _indexvorm(x) != eigen and x not in andere:
                andere.append(x)
        andere = andere[:MAX_VORMEN]
        if not andere and not begin:
            return exact, exact, [stuk]
        match = "(" + " OR ".join([exact, *(_zin(x) for x in andere), *([_zin(begin) + "*"] if begin else [])]) + ")"
        return match, exact, [stuk, *andere, *([begin + "*"] if begin else [])]

    def _familie(self, begin: str) -> int:
        """In hoeveel beweringen een woord staat dat met `begin` begint, geteld tot één boven `FAMILIE`."""
        return self._conn().execute("SELECT COUNT(*) FROM (SELECT 1 FROM zoek WHERE zoek MATCH ? LIMIT ?)",
                                    (_zin(begin) + "*", FAMILIE + 1)).fetchone()[0]

    def _zoekbron(self, delen: list[tuple[str, bool]], groepen: list[tuple] | None = None,
                  ruim: bool = False) -> tuple[str, list[str], list, str | None, list] | None:
        """Waar de treffers van een vraag vandaan komen: het register en de voorwaarde, met de ingevulde waarden en de
        volgorde van de beste treffer. Eerst het register op woorden (elk stuk moet erin staan, in een van zijn vormen;
        accenten tellen niet), dan het register op drietallen van tekens (een deel van een woord), en bij een stuk van
        één of twee tekens gewoon doorlezen. Een vraag in een schrift zonder woordgrenzen (Chinees, Japans, Thai) gaat
        meteen naar de tekens: daar is een "woord" alleen wat toevallig los staat. Welk register geldt, hangt alleen van
        de vraag af. Met andere vormen erbij staat wat precies zo geschreven is bovenaan. Met `ruim` volstaat één van de
        stukken: dat is geen treffer maar een gedeeltelijke, en de app zegt dat erbij."""
        c = self._conn()
        termen = [t for t, _ in delen]
        groepen = groepen if groepen is not None else [self._groep(t, p) for t, p in delen]

        def woorden(match: str, exact: str) -> tuple | None:
            try:
                if not c.execute("SELECT 1 FROM zoek WHERE zoek MATCH ? LIMIT 1", (match,)).fetchone():
                    return None
            except sqlite3.OperationalError:
                return None                    # een stuk dat het register niet kan lezen, is gewoon geen treffer
            if match == exact:
                return "zoek JOIN pagina p ON p.nummer = zoek.nummer", ["zoek MATCH ?"], [match], "zoek.rank, p.nummer", []
            return ("zoek JOIN pagina p ON p.nummer = zoek.nummer", ["zoek MATCH ?"], [match],
                    "p.nummer NOT IN (SELECT nummer FROM zoek WHERE zoek MATCH ?), zoek.rank, p.nummer", [exact])

        if ruim:
            if len(termen) < 2:
                return None
            return woorden(" OR ".join(g[0] for g in groepen), " OR ".join(g[1] for g in groepen))
        namen = [g for g in groepen if len(g) > 3]
        if namen:
            # een afkorting is een naam (#34.2ab): een pagina die het namenregister aan haar koppelt, of waar een van
            # haar namen staat. Een land, redactie, thema of onderdeel verruimt zijn stuk (#34.2ac): het woord, of het
            # kenmerk. De andere stukken zoeken in het register op woorden, zoals altijd. Geen terugval op stukjes van
            # woorden: WHO zou dan elk who vinden
            voorwaarden, waarden = [], []
            for g in namen:
                if "kenmerk" in g[3]:
                    voorwaarde, w = self._kenmerk_voorwaarde(g[3]["kenmerk"], g[0])
                    voorwaarden.append(voorwaarde)
                    waarden += w
                    continue
                voorwaarden.append("(p.nummer IN (SELECT pagina FROM pagina_naam WHERE naam = ?) OR p.nummer IN "
                                   "(SELECT nummer FROM zoek WHERE zoek MATCH ?) OR p.nummer IN (SELECT value FROM json_each(?)))")
                waarden += [g[3]["nummer"], g[0], json.dumps(g[3]["hoofdletters"])]
            rest = [g for g in groepen if len(g) <= 3]
            if not rest:
                bron = ("pagina p", voorwaarden, waarden, None, [])
                if any("kenmerk" in g[3] for g in namen):
                    # alleen kenmerken: wat het woord vond eerst, daarna de rest van het land, thema of de redactie
                    woord = " AND ".join(g[0] for g in namen)
                    bron = (*bron[:3], f"p.nummer NOT IN (SELECT nummer FROM zoek WHERE zoek MATCH ?), {VOLGORDES['nieuw']}",
                            [woord])
            else:
                bron = woorden(" AND ".join(g[0] for g in rest), " AND ".join(g[1] for g in rest))
                if bron is None:
                    return None
                van, basis, basiswaarden, rang, rangwaarden = bron
                bron = van, [*basis, *voorwaarden], [*basiswaarden, *waarden], rang, rangwaarden
            # samen niets: dan geen bron, zodat een spelfout of een deel van de woorden nog kan
            if not c.execute(f"SELECT 1 FROM {bron[0]} WHERE {' AND '.join(bron[1])} LIMIT 1", bron[2]).fetchone():
                return None
            return bron
        if not all(_ZONDER_GRENS.search(t) for t in termen):
            if (bron := woorden(" AND ".join(g[0] for g in groepen), " AND ".join(g[1] for g in groepen))) is not None:
                return bron
        drie = [t for t in termen if len(t) >= 3]
        if drie:
            match = " ".join(_zin(t) for t in drie)
            try:
                if c.execute("SELECT 1 FROM zoek3 WHERE zoek3 MATCH ? LIMIT 1", (match,)).fetchone():
                    return "zoek3 JOIN pagina p ON p.nummer = zoek3.nummer", ["zoek3 MATCH ?"], [match], "zoek3.rank, p.nummer", []
            except sqlite3.OperationalError:
                pass
        kort = [t for t in termen if len(t) >= 2 or _ZONDER_GRENS.search(t)]
        if kort and any(len(t) <= 2 for t in kort):
            lijkt = ["zoek3.tekst LIKE ? ESCAPE '\\'" for _ in kort]
            patronen = ["%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for t in kort]
            if c.execute(f"SELECT 1 FROM zoek3 WHERE {' AND '.join(lijkt)} LIMIT 1", patronen).fetchone():
                return "zoek3 JOIN pagina p ON p.nummer = zoek3.nummer", lijkt, patronen, None, []
        return None

    def _uit_bron(self, bron, blad: int, vertaal: str, sorteer: str | None, filters: dict) -> tuple[list[dict], int]:
        van, basis, basiswaarden, rang, rangwaarden = bron
        stukken = self._waar(filters)
        if stukken is None:
            return [], 0
        waar = " AND ".join([*basis, *stukken[0]])
        waarden = [*basiswaarden, *stukken[1]]
        c = self._conn()
        if sorteer in ZOEK_VOLGORDES or not rang:
            volgorde, rangwaarden = VOLGORDES[sorteer if sorteer in ZOEK_VOLGORDES else "nieuw"], []
        else:
            volgorde = rang
        totaal = c.execute(f"SELECT COUNT(*) FROM {van} WHERE {waar}", waarden).fetchone()[0]
        rijen = [self._bewering_rij(r) for r in c.execute(
            f"SELECT {_RIJ} FROM {van}{_MET_VERTALING} WHERE {waar} ORDER BY {volgorde} LIMIT ? OFFSET ?",
            (vertaal, *waarden, *rangwaarden, PER_BLAD, (max(1, blad) - 1) * PER_BLAD))]
        return rijen, totaal

    def _woordenlijst(self) -> tuple[set[str], dict[tuple[str, int], list[tuple[str, int]]], dict[str, list[str]]]:
        """Elk woord in het zoekregister; de woorden die in minstens twee beweringen staan, per beginletter en lengte
        (voor een spelfout, #34.2i); en de woorden met een bijzondere letter onder hoe iemand ze zonder die letter typt
        (cœur onder coeur, straße onder strasse, #34.2y). Uit de tabel `woord` (`woordrij`, #37.16), op de volgorde van de
        woorden; eén keer gelezen, bij het openen. Het zijn de woorden van de uitgave, niet die van een vraag."""
        with self._woordslot:
            if self._woorden is None:
                alle: set[str] = set()
                emmers: dict[tuple[str, int], list[tuple[str, int]]] = {}
                bijzonder: dict[str, list[str]] = {}
                for term, doc, kandidaat, gewoon in self._conn().execute(
                        "SELECT term, doc, kandidaat, gewoon FROM woord ORDER BY term"):
                    alle.add(term)
                    if kandidaat:
                        emmers.setdefault((term[0], len(term)), []).append((term, doc))
                    if gewoon:
                        bijzonder.setdefault(gewoon, []).append(term)
                self._woorden = (alle, emmers, bijzonder)
        return self._woorden

    def verbeter(self, termen: list[str]) -> list[str] | None:
        """Een spelfout verbeterd (PLAN #34.2i, Baymard #355, #1001): een woord dat nergens staat, wordt het dichtstbijzijnde
        woord dat in minstens twee beweringen staat, met dezelfde beginletter; één letter verschil bij een woord tot vijf
        letters, twee bij een langer; bij gelijk verschil het vaakste. Een woord dat bestaat, een getal, een woord met tekens
        die geen letter zijn (zoals de klinkertekens van het Devanagari) en een schrift zonder spaties blijven zoals ze zijn:
        twijfel verbetert niets. Niets als er niets te verbeteren viel."""
        alle, emmers, _ = self._woordenlijst()
        uit, veranderd = [], False
        for term in termen:
            w = _alfabet(term) if term.isascii() else term.casefold()
            if len(w) < 4 or not w.isalpha() or w in alle or term.casefold() in alle or _ZONDER_SPATIES.search(w):
                uit.append(term)
                continue
            grens = 1 if len(w) <= 5 else 2
            beste: tuple[int, int, str] | None = None
            for lengte in range(len(w) - grens, len(w) + grens + 1):
                for kandidaat, doc in emmers.get((w[0], lengte), ()):
                    d = _afstand(w, kandidaat, grens)
                    if d <= grens and (beste is None or (d, -doc) < beste[:2]):
                        beste = (d, -doc, kandidaat)
            uit.append(beste[2] if beste else term)
            veranderd = veranderd or beste is not None
        return uit if veranderd else None

    def zoek(self, vraag: str | None, blad: int = 1, vertaal: str = VERTAALTAAL, sorteer: str | None = None,
             **filters) -> tuple[list[dict], int]:
        """Zoeken op woorden, met dezelfde filters en volgordes als de lijst: alleen factchecks waarin elk stuk van de
        vraag staat. De filters versmallen daarna. De vraag wordt nergens bewaard: geen voorraad, geen logboek."""
        delen = zoekdelen(vraag)
        bron = self._zoekbron(delen) if delen else None
        return self._uit_bron(bron, blad, vertaal, sorteer, filters) if bron else ([], 0)

    def zoek_ruim(self, vraag: str | None, blad: int = 1, vertaal: str = VERTAALTAAL, sorteer: str | None = None,
                  letterlijk: bool = False, bericht: bool = False, **filters) -> dict:
        """Wat de zoekpagina nodig heeft: de treffers, hun aantal, de aantallen per filterwaarde binnen de treffers, en
        hoeveel treffers er zonder filters zijn. Staat nergens elk stuk van de vraag, dan de factchecks waarin een deel
        ervan staat, met `deels` erbij: dat zijn geen treffers en de pagina zegt dat (SPECS E9.S6 AC4). `gelezen` zegt
        welk land, welke redactie, welk thema of onderdeel een stuk verruimde (#34.2ac); `letterlijk` zet dat uit. Met
        `bericht` zoekt een geplakt bericht op zijn opvallendste woorden (#34.2au); `bericht` in het antwoord zegt dat."""
        bron, deels, verbeterd, delen, markeer, gelezen, is_bericht = self._keuze(vraag, letterlijk, bericht)
        termen = [t for t, _ in delen]
        if bron is None:
            return {"rijen": [], "totaal": 0, "deels": False, "facetten": {}, "zonder_filters": 0, "termen": termen,
                    "markeer": [], "verbeterd": None, "gelezen": [], "bericht": is_bericht}
        rijen, totaal = self._uit_bron(bron, blad, vertaal, sorteer, filters)
        treffers = np.zeros(len(self._plek), dtype=bool)
        treffers[[self._plek[n] for n in self._nummers(bron)]] = True
        return {"rijen": rijen, "totaal": totaal, "deels": deels, "termen": termen, "markeer": markeer,
                "zonder_filters": int(treffers.sum()), "facetten": self._tel_facetten(treffers, filters),
                "verbeterd": verbeterd, "gelezen": gelezen, "bericht": is_bericht}

    def _groepen(self, delen: list[tuple[str, bool]], letterlijk: bool) -> tuple[list[tuple[str, bool]], list[tuple]]:
        """De stukken en hun groepen voor het register; met een land, redactie, thema of onderdeel als één verruimd stuk,
        behalve `letterlijk` (#34.2ac)."""
        kenmerken: dict[int, dict] = {}
        if not letterlijk:
            delen, kenmerken = self._lees_kenmerken(delen)
        groepen = [self._groep(t, p) for t, p in delen]
        for i, wat in kenmerken.items():
            groepen[i] = (*groepen[i][:3], {"kenmerk": wat, "woord": delen[i][0]})
        return delen, groepen

    def _keuze(self, vraag: str | None, letterlijk: bool = False, bericht: bool = False) -> tuple:
        """Welke bron een vraag krijgt: elk stuk; anders een verbeterde spelfout (#34.2i), nooit tussen
        aanhalingstekens; en pas daarna een deel van de vraag (E9.S6 AC4). Met de stukken, wat de tekst markeert en
        welke kenmerken een stuk verruimden (alleen bij een echte treffer, #34.2ac). Met `bericht` is een vraag van meer
        dan `MAX_TERMEN` woorden meteen een geplakt bericht, en een vraag van `BERICHT_WOORDEN` woorden of meer zonder
        treffer ook (#34.2au); het laatste veld zegt of dat zo was."""
        ruw = zoekdelen(vraag)
        if not ruw:
            return None, False, None, ruw, [], [], False
        lang = zoekdelen(vraag, lang=True) if bericht else ruw
        berichtwoorden = [t for t, p in lang if not p]
        if bericht and len(berichtwoorden) > MAX_TERMEN:
            return (*self._berichtbron(lang), [], True)
        delen, groepen = self._groepen(ruw, letterlijk)
        bron, deels, verbeterd = self._zoekbron(delen, groepen), False, None
        if bron is None:
            beter = self.verbeter([t for t, p in ruw if not p])
            if beter:
                vrij = iter(beter)
                nieuw_ruw = [(t if p else next(vrij), p) for t, p in ruw]
                nieuw, nieuwe_groepen = self._groepen(nieuw_ruw, letterlijk)
                if (bron := self._zoekbron(nieuw, nieuwe_groepen)) is not None:
                    delen, groepen = nieuw, nieuwe_groepen
                    verbeterd = " ".join(f'"{t}"' if p else t for t, p in nieuw_ruw)
        if bron is None and bericht and len(berichtwoorden) >= BERICHT_WOORDEN:
            return (*self._berichtbron(lang), [], True)
        if bron is None:
            bron, deels = self._zoekbron(delen, groepen, ruim=True), True
        gelezen = [] if deels or bron is None else [
            dict(g[3]["kenmerk"], woord=g[3]["woord"]) for g in groepen if len(g) > 3 and "kenmerk" in g[3]]
        return bron, deels, verbeterd, delen, [m for g in groepen for m in g[2]], gelezen, False

    def _berichtbron(self, delen: list[tuple[str, bool]]) -> tuple:
        """Een geplakt bericht (PLAN #34.2au, SPECS E9.S6 AC5): de tien zeldzaamste woorden die in de uitgave staan, nooit
        een woord in meer dan 2% van de pagina's. Een treffer heeft minstens 40% van de opvallende woorden van het bericht
        (tot tien, ook die nergens staan, en minstens twee),
        en een gewicht van minstens 30% van de beste; het gewicht van een woord is hoe zeldzaam het is. Hoogstens
        `BERICHT_MAX`, de beste eerst. Geeft de bron (of niets), de woorden die telden en wat de tekst markeert, in de
        vorm van `_keuze`."""
        c = self._conn()
        n = len(self._plek)
        grens = max(BERICHT_GEWOON * n, 3)
        kandidaten, gezien, opvallend = [], set(), 0
        for plek, (term, _) in enumerate(delen):
            kern = "".join(t for t in _indexvorm(term) if t.isalnum())
            if len(kern) < 3 or kern in gezien:
                continue
            gezien.add(kern)
            groep = self._groep(term, False)
            try:
                df = c.execute("SELECT count(*) FROM zoek WHERE zoek MATCH ?", (groep[0],)).fetchone()[0]
            except sqlite3.OperationalError:
                continue
            if df <= grens:
                opvallend += 1                 # ook een woord dat nergens staat: een treffer moet het bericht dekken
            if 0 < df <= grens:
                kandidaten.append((df, plek, term, groep))
        # de zeldzaamste tien, en die in de volgorde van het bericht (zo leest de uitleg op de pagina)
        gekozen = sorted(sorted(kandidaten)[:BERICHT_TERMEN], key=lambda k: k[1])
        delen_uit = [(term.strip(_RANDTEKENS) or term, False) for _, _, term, _ in gekozen]   # "Doorsturen!!" als Doorsturen
        markeer = [m for _, _, _, groep in gekozen for m in groep[2]]
        if len(gekozen) < 2:
            return None, False, None, delen_uit, markeer      # te weinig opvallends: niets, ook niet zwak
        gewicht: Counter = Counter()
        aantal: Counter = Counter()
        for df, _, _, groep in gekozen:
            w = math.log(n / df)
            for (nummer,) in c.execute("SELECT nummer FROM zoek WHERE zoek MATCH ?", (groep[0],)):
                gewicht[nummer] += w
                aantal[nummer] += 1
        nodig = max(2, math.ceil(min(opvallend, BERICHT_TERMEN) * BERICHT_DEKKING))
        beste = max((g for nr, g in gewicht.items() if aantal[nr] >= nodig), default=0)
        treffers = sorted((nr for nr, g in gewicht.items() if aantal[nr] >= nodig and g >= BERICHT_DEEL * beste),
                          key=lambda nr: (-gewicht[nr], -aantal[nr], nr))[:BERICHT_MAX]
        zwak = not treffers
        if zwak:
            # geen factcheck lijkt duidelijk op het bericht: de tien met de meeste van dezelfde woorden, gewogen zoals het
            # register weegt (alle woorden, de zeldzame zwaarder); geen treffers, en de pagina zegt dat (E9.S6 AC4)
            ruim = self._zoekbron(delen, None, ruim=True)
            if ruim is None:
                return None, False, None, delen_uit, markeer
            van, basis, waarden, rang, rangwaarden = ruim
            treffers = [r[0] for r in c.execute(
                f"SELECT p.nummer FROM {van} WHERE {' AND '.join(basis)} ORDER BY {rang} LIMIT ?",
                [*waarden, *rangwaarden, BERICHT_ZWAK])]
            if not treffers:
                return None, False, None, delen_uit, markeer
        lijst = json.dumps(treffers)
        bron = ("pagina p", ["p.nummer IN (SELECT value FROM json_each(?))"], [lijst],
                "(SELECT key FROM json_each(?) WHERE value = p.nummer)", [lijst])
        return bron, zwak, None, delen_uit, markeer

    def _nummers(self, bron: tuple) -> list[str]:
        van, basis, basiswaarden = bron[:3]
        return [r[0] for r in self._conn().execute(f"SELECT p.nummer FROM {van} WHERE {' AND '.join(basis)}", basiswaarden)]

    def tel(self, vraag: str | None) -> int:
        """Hoeveel factchecks een vraag vindt, zonder filters en zonder een deel van de woorden (voor een suggestie,
        #34.2ac). Een spelfout telt mee zoals het zoeken haar verbetert."""
        bron, deels = self._keuze(vraag)[:2]
        if bron is None or deels:
            return 0
        van, basis, waarden = bron[:3]
        return self._conn().execute(f"SELECT COUNT(*) FROM {van} WHERE {' AND '.join(basis)}", waarden).fetchone()[0]

    def treffers(self, vraag: str | None, letterlijk: bool = False) -> list[str]:
        """De nummers achter het aantal zonder filters: alles wat de vraag vindt, op welke manier ook (voor de
        randproef van #34.2y). De vraag wordt nergens bewaard."""
        bron = self._keuze(vraag, letterlijk)[0]
        return self._nummers(bron) if bron else []

    def suggesties(self, vraag: str | None, taal: str, n: int = 4) -> tuple[list[dict], list[str]]:
        """Ingangen tijdens het typen: elk stuk van de vraag is het begin van een woord in de naam (in een van de talen
        van de site). Een naam die precies zo heet eerst, dan de meeste factchecks. Daarbij de woorden die het laatste
        stuk afmaken ("zel" wordt "zelensky"), voor de zoekvragen in de suggesties (#359)."""
        stukken = [_alfabet(s) for s in zoektermen(vraag)]
        stukken = [s for s in stukken if s]
        if not stukken or len("".join(stukken)) < 2:
            return [], []
        heel = " ".join(stukken)
        treffers: list[tuple[int, int, dict]] = []
        aanvullingen: dict[str, int] = {}
        for woorden, wat in self._suggestie:
            if all(any(w.startswith(s) for w in woorden) for s in stukken):
                namen = wat["naam"].values() if isinstance(wat["naam"], dict) else [wat["naam"]]
                precies = any(_alfabet(" ".join(zoektermen(naam))) == heel for naam in namen)
                treffers.append((0 if precies else 1, -wat["aantal"], wat))
                for w in woorden:
                    if w.startswith(stukken[-1]) and w != stukken[-1]:
                        aanvullingen[w] = aanvullingen.get(w, 0) + wat["aantal"]
        treffers.sort(key=lambda x: (x[0], x[1]))
        ingangen = [dict(w, naam=w["naam"][taal] if isinstance(w["naam"], dict) else w["naam"]) for _, _, w in treffers[:n]]
        voor = " ".join(stukken[:-1])
        woorden = [f"{voor} {w}".strip() for w, _ in sorted(aanvullingen.items(), key=lambda x: -x[1])[:3]]
        return ingangen, woorden

    def ingangen(self, vraag: str | None, taal: str) -> list[dict]:
        """Is de vraag precies een naam, een thema, een dossier of een redactie, dan is dat een ingang: de pagina die
        alles daarover bij elkaar heeft. Bij een persoon volstaat een deel van de naam ("trump"): dan de personen met
        dat deel, de vaakst genoemde eerst. Hoogstens drie."""
        sleutel = _alfabet(" ".join(zoektermen(vraag)))
        if not sleutel:
            return []
        uit: list[dict] = []
        stukken = zoektermen(vraag)
        if len(stukken) == 1 and (afkorting := self.afkorting(stukken[0])) is not None:
            uit.append(self._naam_ingang[afkorting["nummer"]])        # WHO: de Wereldgezondheidsorganisatie (#34.2ab)
        for i in [*self._ingang.get(sleutel, []), *self._ingang_deel.get(sleutel, [])]:
            if i not in uit:
                uit.append(i)
        return [dict(i, naam=i["naam"][taal] if isinstance(i["naam"], dict) else i["naam"]) for i in uit[:3]]

    # --- zoeken dat meedenkt (PLAN #34.2ac, SPECS E9.S14) -------------------------------------------------------------

    def doorsturen(self, vraag: str | None, letterlijk: bool = False) -> dict | None:
        """Waar een vraag meteen heen gaat, of niets. Een geplakte link van een factcheckartikel uit de uitgave, of van een
        factcheck op Factiz: die factcheck (AC5). De hele vraag precies de volledige naam van één persoon uit het
        namenregister of van één dossier, in een van de vijf talen: die pagina (AC4). Gemeten: bij een persoon valt 0 tot
        2% van wat de naam als woord vindt buiten haar pagina, bij een plaats, organisatie, thema of onderdeel 7 tot 77%;
        die blijven dus een zoekvraag. Niet tussen aanhalingstekens, niet `letterlijk`."""
        if letterlijk or not vraag:
            return None
        vraag = schoon(vraag).strip()
        if (nummer := self._factcheck_van_link(vraag)) is not None:
            return {"soort": "factcheck", "nummer": nummer, "naam": self._bewering(nummer)}
        if any(p for _, p in zoekdelen(vraag)):
            return None
        lijst = self._ingang.get(sleutel(vraag), [])
        if len(lijst) == 1 and (lijst[0]["soort"] == "dossier"
                                or (lijst[0]["soort"] == "naam" and lijst[0]["naamsoort"] == "persoon")):
            return dict(lijst[0])
        return None

    def _bewering(self, nummer: str) -> str:
        rij = self._conn().execute("SELECT bewering FROM pagina WHERE nummer = ?", (nummer,)).fetchone()
        return schoon(rij[0]) if rij else ""

    def _factcheck_van_link(self, vraag: str) -> str | None:
        """Het nummer van de factcheck achter een geplakte link: een artikel van een redactie in de uitgave, met of zonder
        https, www of m., hoofdletters, een volgvraag (utm_…) of een #; of een factcheck op factiz.org."""
        if any(t.isspace() for t in vraag) or "." not in vraag or "/" not in vraag.split("://", 1)[-1].strip("/"):
            return None
        vorm = adresvorm(vraag)
        if vorm is None:
            return None
        if m := _FACTIZ_LINK.fullmatch(vorm[-1]):
            return m[1] if m[1] in self._plek else None
        with self._adresslot:
            if self._adressen is None:
                self._adressen = {}
                for nummer, url in self._conn().execute("SELECT pagina, url FROM check_ ORDER BY pagina, volg"):
                    if (v := adresvorm(url)) is not None:
                        for k in v:
                            self._adressen.setdefault(k, nummer)
        for k in vorm:
            if k in self._adressen:
                return self._adressen[k]
        return None

    def aanvulling(self, vraag: str | None) -> str | None:
        """De vraag met het woord dat je typt afgemaakt (AC2), of niets: het woord dat het vaakst in de uitgave staat en
        ermee begint (in minstens twee beweringen), en alleen als de hele vraag dan iets vindt. Het getypte blijft zoals
        het getypt is; erbij komt alleen de rest. Niets bij een woord dat al bestaat, korter dan `AANVUL_MIN` letters,
        tussen aanhalingstekens, na een spatie, met een cijfer of teken, of in een schrift zonder spaties."""
        if not vraag or vraag != vraag.rstrip() or any(t in vraag for t in '"“”„«»'):
            return None
        laatste = vraag.split()[-1]
        w = _indexvorm(laatste)
        if len(w) < AANVUL_MIN or len(w) != len(laatste) or not w.isalpha() or _ZONDER_SPATIES.search(w):
            return None
        alle, emmers, _ = self._woordenlijst()
        if w in alle:
            return None
        if self._voorvoegsels is None:
            paren = sorted((t, d) for lijst in emmers.values() for t, d in lijst)
            self._voorvoegsels = ([t for t, _ in paren], [d for _, d in paren])
        woorden, docs = self._voorvoegsels
        van, tot = bisect.bisect_left(woorden, w), bisect.bisect_left(woorden, w + "\U0010ffff")
        for _, woord in heapq.nlargest(3, ((docs[i], woorden[i]) for i in range(van, tot))):
            heel = vraag + woord[len(w):]
            delen, groepen = self._groepen(zoekdelen(heel), False)
            if self._zoekbron(delen, groepen) is not None:
                return heel
        return None


_FACTIZ_LINK = re.compile(r"factiz\.org/(?:(?:nl|en|de|es|fr)/)?fact-checks/([0-9a-f]{16})")
_VOLGVRAAG = re.compile(r"^(utm_|fbclid$|gclid$|igshid$|mc_|ref$|amp$|s$)")


def sleutel(tekst: str) -> str:
    """Een vraag of naam zoals het register van ingangen haar kent: de stukken zonder hoofdletters en accenten."""
    return _alfabet(" ".join(zoektermen(tekst)))


def adresvorm(adres: str) -> tuple[str, ...] | None:
    """Een link zoals het zoeken haar vergelijkt (PLAN #34.2ac): zonder https, www of m., in kleine letters, zonder / aan het
    eind en zonder #. Eerst met de vraag erachter zonder volgvragen (utm_…), daarna zonder vraag. Niets als het geen
    adres is."""
    try:
        deel = urlsplit(adres.strip() if "://" in adres else "https://" + adres.strip())
    except ValueError:
        return None
    host = (deel.hostname or "").lower()
    for voor in ("www.", "m.", "amp."):
        host = host.removeprefix(voor)
    if "." not in host or not deel.path.strip("/"):
        return None
    pad = deel.path.rstrip("/").lower()
    vragen = [(k, v) for k, v in parse_qsl(deel.query, keep_blank_values=True) if not _VOLGVRAAG.match(k.lower())]
    met = f"{host}{pad}?{urlencode(vragen)}".lower() if vragen else None
    return tuple(v for v in (met, f"{host}{pad}") if v)
