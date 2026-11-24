"""De talen van het platform (B74, B79): vijftien, met Engels op de hoofdmap, uit de ene lijst `teksten/sitetalen.json`
die ook het lab en de site lezen. Vaste teksten komen uit een woordenlijst per taal; een model vertaalt hier niets."""

from __future__ import annotations

import functools
import json
from pathlib import Path

_MAP = Path(__file__).resolve().parent / "teksten"
_SITETALEN = json.loads((_MAP / "sitetalen.json").read_text(encoding="utf-8"))["talen"]
TALEN = tuple(t["code"] for t in _SITETALEN)
STANDAARD = "en"
EIGEN_NAAM = {t["code"]: t["naam"] for t in _SITETALEN}
# de code naar buiten (lang, hreflang) en in het adres: pt-BR en /pt-br/, zh-Hant en /zh-hant/ (B79)
BCP47 = {t["code"]: t["bcp47"] for t in _SITETALEN}
PAD = {t["code"]: t["pad"] for t in _SITETALEN}
_VAN_PAD = {t["pad"]: t["code"] for t in _SITETALEN if t["pad"]}
RTL = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})
BASIS = "https://factiz.org"
LABELS = ("onwaar", "misleidend", "onwaar-of-misleidend", "waar", "deels-waar", "omstreden", "satire", "onbewezen")

# De naam van een taal in die taal zelf, voor de taal van een bewering of een check.
TAALNAAM = {
    "af": "Afrikaans", "am": "አማርኛ", "ar": "العربية", "as": "অসমীয়া", "az": "Azərbaycanca", "bn": "বাংলা",
    "ca": "Català", "de": "Deutsch", "en": "English", "es": "Español", "fa": "فارسی", "fr": "Français",
    "ga": "Gaeilge", "gl": "Galego", "gu": "ગુજરાતી", "he": "עברית", "hi": "हिन्दी", "hr": "Hrvatski",
    "id": "Bahasa Indonesia", "it": "Italiano", "ja": "日本語", "km": "ខ្មែរ", "kn": "ಕನ್ನಡ", "ko": "한국어",
    "lo": "ລາວ", "ml": "മലയാളം", "mn": "Монгол", "mr": "मराठी", "ms": "Bahasa Melayu", "ne": "नेपाली",
    "nl": "Nederlands", "pa": "ਪੰਜਾਬੀ", "pl": "Polski", "pt": "Português", "ro": "Română", "ru": "Русский",
    "si": "සිංහල", "sw": "Kiswahili", "ta": "தமிழ்", "te": "తెలుగు", "th": "ไทย", "tl": "Filipino",
    "tr": "Türkçe", "ur": "اردو", "vi": "Tiếng Việt", "zh": "中文",
    # erbij gekomen met de herstelde taallabels (PLAN #33.5)
    "bs": "Bosanski", "om": "Afaan Oromoo", "sl": "Slovenščina", "so": "Soomaali", "sr": "Српски", "ti": "ትግርኛ",
    "uk": "Українська",
}


@functools.cache
def teksten(taal: str) -> dict:
    if taal not in TALEN:
        raise KeyError(taal)
    return json.loads((_MAP / f"{taal}.json").read_text(encoding="utf-8"))["teksten"]


def tekst(taal: str, sleutel: str, **waarden) -> str:
    """Een vaste tekst, met de blanco's ingevuld. Een sleutel die niet bestaat is een fout, geen lege plek."""
    vorm = teksten(taal)[sleutel]
    return vorm.format(**waarden) if waarden else vorm


# Een naam die Factiz bewust weglaat (maatregel 2, PLAN #34.2bw, SPECS E9.S8 AC13): in de uitgave staat op haar plek dit
# merkteken. Het platform laat het nooit zo naar buiten: in de gegevens wordt het ⟦naam weggelaten⟧ in de taal van de site
# (de site maakt daar een sticker van), in een titel, omschrijving, de gestructureerde gegevens en het deelplaatje
# [naam weggelaten]. De naam zelf staat nergens in de uitgave.
WEGGELATEN = "⟦redacted⟧"


def plat(taal: str, tekst_: str) -> str:
    """Een tekst voor een titel, omschrijving, gestructureerde gegevens of het deelplaatje: een weggelaten naam als
    [naam weggelaten] in de taal van de site."""
    return tekst_.replace(WEGGELATEN, f"[{tekst(taal, 'weggelaten')}]") if tekst_ and WEGGELATEN in tekst_ else tekst_


def gemerkt(taal: str) -> str:
    """Hoe een weggelaten naam in de gegevens staat: ⟦naam weggelaten⟧ in de taal van de site; de site maakt er een
    sticker van."""
    return f"⟦{tekst(taal, 'weggelaten')}⟧"


def pad(taal: str, *delen: str) -> str:
    """Het adres binnen de site: Engels op de hoofdmap, de andere talen onder hun code."""
    stukken = ([] if taal == STANDAARD else [PAD[taal]]) + [d for d in delen if d]
    return "/" + "".join(f"{s}/" for s in stukken)


def eigen_talen(taal_bewering: str, vertalingen) -> tuple[str, ...]:
    """De talen van de site waarin een pagina eigen hoofdtekst heeft: de bewering zelf, of een vertaling ervan. Alleen daar
    is ze vindbaar (PLAN #34.2c, DESIGNSYSTEEM §6): een pagina waarvan alleen menu en knoppen vertaald zijn, is voor een
    zoekmachine een kopie. Ligt er geen, dan de hoofdmap, zodat er altijd één vindbare versie is."""
    talen = tuple(t for t in TALEN if t == taal_bewering or t in vertalingen)
    return talen or (STANDAARD,)


def x_default(talen: tuple[str, ...]) -> str:
    """Waar een bezoeker heen gaat wiens taal er niet bij is: de hoofdmap als die erbij hoort, anders de eerste."""
    return STANDAARD if STANDAARD in talen else talen[0]


def taal_van_pad(urlpad: str) -> str:
    eerste = urlpad.strip("/").split("/", 1)[0]
    return _VAN_PAD.get(eerste, STANDAARD)


def richting(taal: str) -> str:
    return "rtl" if (taal or "").split("-")[0].lower() in RTL else "ltr"


def taalnaam(code: str) -> str:
    return TAALNAAM.get((code or "").split("-")[0].lower(), code or "")


@functools.cache
def _talen() -> dict:
    return json.loads((_MAP / "talen.json").read_text(encoding="utf-8"))["talen"]


def taalnaam_in(taal: str, code: str) -> str:
    """De naam van een taal in de taal van de site (*Hindi*, *hindi*), voor de regel bij een vertaling; een code
    zonder naam blijft de code."""
    kort = (code or "").split("-")[0].lower()
    return _talen().get(kort, {}).get(taal, code or "")


_DUIZENDTAL = {t["code"]: t["duizendtal"] for t in _SITETALEN}


def opsomming(taal: str, namen: list[str]) -> str:
    """`Snopes, Maldita en AFP`: namen achter elkaar, de laatste met het woord voor *en* in de taal van de site."""
    namen = list(namen)
    if len(namen) < 2:
        return "".join(namen)
    return f"{', '.join(namen[:-1])} {tekst(taal, 'opsomming_en')} {namen[-1]}"


# het oordeel van de redacties als stempel (PLAN #34.2cc, DESIGN §4y): dezelfde woorden als de eigen checks waar ze er zijn
_STEMPEL_EIGEN = {"onwaar": "eigen_oordeel_onwaar", "misleidend": "eigen_oordeel_misleidend",
                  "onbewezen": "eigen_oordeel_onbewezen", "waar": "eigen_oordeel_klopt"}


def stempel(taal: str, klasse: str | None) -> str:
    """Het woord op het stempel: *Onwaar*, zonder *Bekend als*, want wie het zegt staat erachter (`volgens`)."""
    if klasse in _STEMPEL_EIGEN:
        return tekst(taal, _STEMPEL_EIGEN[klasse])
    return tekst(taal, "stempel_" + klasse.replace("-", "_") if klasse in LABELS else "stempel_geen")


def volgens(taal: str, klasse: str | None, namen: list[str], hoogstens: int = 4) -> str:
    """Wie het oordeel draagt, klein achter het stempel (PO 2026-11-19): *volgens DW en BR24*,
    tot vier namen allemaal, daarboven drie en *en 2 andere*; bij omstreden *tussen*, want dan zijn ze het oneens; zonder
    oordeel *door*."""
    namen = list(namen or [])
    if not namen:
        return ""
    vast = max(1, hoogstens - 1)       # zoveel namen voor *en N andere*; in een titel één (`hoogstens=1`)
    # nooit *en 1 andere*: is er één naam meer, dan staat die er gewoon
    heel = len(namen) <= max(hoogstens, vast + 1)
    lijst = namen if heel else namen[:vast] + [tekst(taal, "stempel_andere", n=getal(taal, len(namen) - vast))]
    soort = "stempel_tussen" if klasse == "omstreden" else "stempel_volgens" if klasse in LABELS else "stempel_door"
    return tekst(taal, soort, wie=opsomming(taal, lijst))


def oordeel_kop(taal: str, klasse: str | None, namen: list[str]) -> str:
    """Het stempel met wie het zegt in één regel, voor een titel en een omschrijving: *Onwaar volgens Vera Files*,
    *Onwaar volgens FactCheck.org en 3 andere*; hoogstens één naam, want een titel is kort."""
    return f"{stempel(taal, klasse)} {volgens(taal, klasse, namen, hoogstens=1)}".strip()


def volgens_namen(veld) -> list[str]:
    """De redacties achter het oordeel van een pagina, uit de kolom `volgens` (JSON) van de uitgave."""
    try:
        return [str(n) for n in json.loads(veld or "[]")]
    except (TypeError, ValueError):
        return []


def getal(taal: str, n: int) -> str:
    return f"{n:,}".replace(",", _DUIZENDTAL[taal])


def datum(taal: str, iso: str) -> str:
    """`2024-03-05` in de vorm van de taal; een datum die er niet is of niet klopt, blijft leeg."""
    try:
        jaar, maand, dag = (int(x) for x in (iso or "").split("-"))
        naam = teksten(taal)["maanden"][maand - 1]
    except (ValueError, IndexError):
        return ""
    if not 1 <= dag <= 31:
        return ""
    dagtekst = "1er" if taal == "fr" and dag == 1 else str(dag)
    return teksten(taal)["datum_vorm"].format(dag=dagtekst, maand=naam, jaar=jaar)


def maand_jaar(taal: str, maand: str) -> str:
    """`2026-11` als maand met haar jaar in de vorm van de taal (`november 2026`, `2026年11月`), uit CLDR (PLAN #37.11);
    een maand die er niet is, blijft leeg."""
    try:
        jaar, m = (int(x) for x in (maand or "").split("-"))
    except ValueError:
        return ""
    if not 1 <= m <= 12:
        return ""
    t = teksten(taal)
    return t["maand_jaar_vorm"].format(maand=t["maanden_jaar"][m - 1], jaar=jaar)


def label(taal: str, klasse: str | None) -> str:
    sleutel = "label_" + klasse.replace("-", "_") if klasse in LABELS else "label_geen"
    return tekst(taal, sleutel)


def telregel(taal: str, redacties: int, talen: int, eerste: str, laatste: str) -> str:
    """`3 newsrooms, 3 languages, 2023–2024`: een telling, nooit een schatting."""
    delen = [tekst(taal, "redacties_een" if redacties == 1 else "redacties_meer", n=getal(taal, redacties)),
             tekst(taal, "talen_een" if talen == 1 else "talen_meer", n=getal(taal, talen))]
    van, tot = (eerste or "")[:4], (laatste or "")[:4]
    if van and tot:
        delen.append(van if van == tot else f"{van}–{tot}")
    return ", ".join(delen)
