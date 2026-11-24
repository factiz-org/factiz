"""De vraag zoals mensen haar stellen, per factcheck (PLAN #34.2cf, SPECS E9.S8 AC11).

Wie wil weten of iets klopt, typt een vraag: *Klopt het dat …?*, *Is it true that …?*, *Did X say …?*, *Is … a hoax?*.
Een factcheckpagina had alleen de bewering als stelling, *Klopt dit?* als kop en een titel met de bewering afgekapt op 45
tekens. Hier krijgt elke pagina, in de taal waarin ze vindbaar is (die van de bewering, anders `x_default`), één
**zoekvraag** en een kort **onderwerp**: een naamwoordgroep, nooit een bewering, voor de titel. Een taalmodel schrijft ze
(`zoekvraag-v5`, Haiku, tien per vraag in één taal). De vraag verraadt het antwoord nooit: het antwoord is het oordeel van de
redacties, nooit een eigen oordeel (DR2). Ze gaan pas in de uitgave na mijn leesproef van 200 zonder fout (`poort`).

    python -m doublecheck.zoekvragen kandidaten|vragen [--proef N]|lezen|tellen|indienen|ophalen [--wacht M]

Leest de nieuwste publicatiedatabase (openbare beweringen en de vertalingen van Factiz), alleen-lezen. Uitvoer in
`data/zoekvragen/`; mijn lezing in `docs/steekproeven/34.2cf-zoekvragen.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

from factiz_site import i18n

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "zoekvragen"
ANTWOORDEN = MAP / "antwoorden.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2cf-zoekvragen.json"
VERSIE = "zoekvraag-v5"
GRENS = 12.00           # dollar, alles samen; de volle ronde via de Batch API, geschat ~$7,60 (v5 kostte direct $0,000143 per pagina)
SCHATTING = 0.00015     # per pagina, direct gevraagd, tien per vraag, effort medium
SCHATTING_BATCH = 0.00008
BATCHES = MAP / "batches.jsonl"
PER_VRAAG = 10
DRADEN = 8
ZAAD = 2213            # de poort; 2211 en 2212 waren de ontwikkelsets waarop v2 tot v5 gemaakt zijn (34.2cf-zoekvragen-ontwikkel.json)
ONTWIKKEL_ZAAD = 2212
PROEF_N = 200
MIN_GELEZEN = 190      # van de 200 kreeg een paar geen vraag (die houden Klopt dit?): 194 en 195 in de proeven
MAX_KLEIN = 5
MAX_FOUT = 0.01        # B77 en B87 (PO 2026-11-22: "Ja is goed hoor"): hoogstens 1 op de 100, naar boven afgerond
MAX_VRAAG = 160
MAX_ONDERWERP = 70
LEESLABELS = ("goed", "klein", "fout", "twijfel")
VRAAGTEKENS = ("?", "？", "؟")
EINDE_ZIN = (".", "!", "?", "。", "！", "？", "؟", "।")

# De namen van de talen voor het model: een code alleen is voor een paar schriften dubbelzinnig.
TAALNAMEN = {"en": "English", "nl": "Dutch", "de": "German", "es": "Spanish", "fr": "French", "pt": "Portuguese",
             "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic", "fa": "Persian", "hi": "Hindi", "id": "Indonesian",
             "tr": "Turkish", "ja": "Japanese", "zh": "Chinese (traditional characters, as used in Taiwan)"}


class Weigering(Exception):
    pass


def doeltaal(taal_bewering: str, vertalingen) -> str:
    """De taal waarin een factcheck vindbaar is (stand 2, `site/src/lib/vindbaar.js`): die van de bewering als het een
    taal van de site is, anders waar `x_default` heen wijst (het Engels, anders de eerste vertaling)."""
    if taal_bewering in i18n.TALEN:
        return taal_bewering
    return i18n.x_default(i18n.eigen_talen(taal_bewering, vertalingen))


def bron(taal_bewering: str, bewering: str, vertalingen: dict[str, str]) -> tuple[str, str]:
    """De taal van de vraag en de tekst waaruit ze komt: de bewering zelf, of haar vertaling in die taal. Ligt er geen
    vertaling, dan de bewering, en schrijft het model de vraag in de doeltaal."""
    taal = doeltaal(taal_bewering, vertalingen)
    return taal, (bewering if taal == taal_bewering else vertalingen.get(taal) or bewering)


def kop_uit_adres(url: str) -> str:
    """De kop die EUvsDisinfo een zaak geeft, uit het adres van haar pagina (`/report/<kop>/`): de kern van de
    desinformatie in een paar woorden (*wests-support-for-ukraine-fosters-russophobia*). Hun beweringen zijn een lange
    samenvatting, en zonder kop vroeg het model in 9 van de 13 fouten naar een waar bijfeit (zoekvraag-v4). Bij andere
    redacties niet: daar noemt het adres vaak de bevinding."""
    m = re.search(r"euvsdisinfo\.eu/report/([a-z0-9-]+)", url or "")
    if not m:
        return ""
    return re.sub(r"-\d+$", "", m.group(1)).replace("-", " ").strip()


def vraag_klopt(vraag: str, bewering: str) -> bool:
    """Een bruikbare zoekvraag: één regel, eindigt op een vraagteken (ook ？ en ؟), 5 tot `MAX_VRAAG` tekens (een
    Chinese vraag is kort), met één vraagteken (in de ontwikkelset waren het er twee, en de tweede vraag was een andere),
    en niet de bewering met een vraagteken erachter, tenzij de bewering zelf al een vraag is."""
    v, b = " ".join((vraag or "").split()), " ".join((bewering or "").split())
    kaal = lambda t: t.rstrip("?？؟.!。 ").casefold()
    return (5 <= len(v) <= MAX_VRAAG and v.endswith(VRAAGTEKENS) and sum(v.count(t) for t in VRAAGTEKENS) == 1
            and (kaal(v) != kaal(b) or b.endswith(VRAAGTEKENS)))


def schriften(tekst: str) -> set[str]:
    """De schriften van de letters in een tekst, naar het eerste woord van hun Unicode-naam (LATIN, ARABIC, HEBREW,
    CJK, …); hiragana en katakana tellen als Japans schrift."""
    uit = set()
    for t in tekst:
        if t.isalpha():
            naam = unicodedata.name(t, "").split(" ")[0]
            uit.add("JAPANS" if naam in ("HIRAGANA", "KATAKANA", "CJK") else naam)
    return uit


TAALSCHRIFT = {"ar": "ARABIC", "fa": "ARABIC", "hi": "DEVANAGARI", "ru": "CYRILLIC", "uk": "CYRILLIC", "ja": "JAPANS",
               "zh": "JAPANS"}


def schrift_klopt(vraag: str, bron: str, taal: str) -> bool:
    """Geen letter uit een schrift dat niet bij de taal hoort, niet Latijns is (namen, afkortingen) en niet in de
    bewering staat. In de ontwikkelset stond een Hebreeuwse letter midden in een Arabische naam (zoekvraag-v2)."""
    toegestaan = {"LATIN", TAALSCHRIFT.get(taal, "LATIN")} | schriften(bron)
    return schriften(vraag) <= toegestaan


def onderwerp_klopt(onderwerp: str, vraag: str) -> bool:
    """Een bruikbaar onderwerp: kort (2 tot `MAX_ONDERWERP` tekens; een Chinees woord is twee tekens) en geen zin, dus
    niet eindigend op een punt, uitroep- of vraagteken; en niet de vraag zelf."""
    o = " ".join((onderwerp or "").split())
    return 2 <= len(o) <= MAX_ONDERWERP and not o.endswith(EINDE_ZIN) and o.casefold() != " ".join((vraag or "").split()).casefold()


# Een taal met een eigen schrift: het onderwerp moet er tekens van hebben (een naamwoordgroep is te kort om de taal te
# herkennen, het schrift niet).
SCHRIFT = {"ar": ("\u0600", "\u06ff"), "fa": ("\u0600", "\u06ff"), "hi": ("\u0900", "\u097f"),
           "ru": ("\u0400", "\u04ff"), "uk": ("\u0400", "\u04ff"), "zh": ("\u4e00", "\u9fff"),
           "ja": ("\u3040", "\u9fff")}
_HERKENNER = None


def _taal_van(tekst: str, talen: tuple[str, ...]) -> tuple[str, float]:
    """De taal van een tekst volgens py3langid, gekozen uit `talen` (de talen van de site), met hoe zeker."""
    global _HERKENNER
    if _HERKENNER is None:
        from py3langid.langid import MODEL_FILE, LanguageIdentifier
        _HERKENNER = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
        _HERKENNER.set_languages(list(talen))
    taal, zeker = _HERKENNER.classify(tekst)
    return taal, float(zeker)


def in_taal(tekst: str, taal: str) -> bool:
    """Of een vraag in de gevraagde taal staat: py3langid, beperkt tot de talen van de site. Het model schreef op een
    Spaanse pagina soms Nederlands en op een Portugese Engels (zoekvraag-v1, de proef van 2026-11-22)."""
    return _taal_van(tekst, i18n.TALEN)[0] == taal


# De talen waarin het model weglekte (zoekvraag-v1): het Nederlands van mijn voorbeelden en het Engels van de opdracht.
LEKTALEN = ("en", "nl")


def onderwerp_in_taal(onderwerp: str, taal: str) -> bool:
    """Of een onderwerp in de gevraagde taal staat. Met een eigen schrift: er staan tekens van dat schrift in. Met het
    Latijnse schrift is een naamwoordgroep vaak vooral namen, en dan noemt py3langid een kort Engels onderwerp met 99%
    zekerheid Indonesisch. Dus alleen vanaf drie woorden, en alleen de vraag of het de gevraagde taal is of een van de
    `LEKTALEN`: daarin lekte het model weg (een Nederlands onderwerp op een Engelse pagina, een Engels op een Portugese)."""
    if taal in SCHRIFT:
        van, tot = SCHRIFT[taal]
        return any(van <= t <= tot for t in onderwerp)
    if len(onderwerp.split()) < 3:
        return True
    _taal_van(onderwerp, i18n.TALEN)
    kansen = dict(_HERKENNER.rank(onderwerp))
    return max({taal, *LEKTALEN}, key=lambda t: kansen.get(t, 0.0)) == taal


# Hoe een zoeker de vraag begint, per taal van de site: voorbeelden voor het model, in de taal zelf.
VORMEN = {
    "en": '"Is it true that …?", "Did … say that …?", "Does this photo show …?", "Is the video of … real?", "Is … a hoax?"',
    "nl": '"Klopt het dat …?", "Is het waar dat …?", "Heeft … gezegd dat …?", "Is deze foto van … echt?", "Is … nep?"',
    "de": '"Stimmt es, dass …?", "Hat … gesagt, dass …?", "Ist das Foto von … echt?", "Ist … ein Fake?"',
    "es": '"¿Es cierto que …?", "¿Dijo … que …?", "¿Es real la foto de …?", "¿Es falso que …?"',
    "fr": '"Est-il vrai que … ?", "… a-t-il dit que … ?", "La photo de … est-elle authentique ?", "… est-ce un fake ?"',
    "pt": '"É verdade que …?", "… disse que …?", "A foto de … é verdadeira?", "É fake que …?"',
    "ru": '"Правда ли, что …?", "Говорил ли …, что …?", "Это фото … настоящее?", "Это фейк, что …?"',
    "uk": '"Чи правда, що …?", "Чи казав …, що …?", "Це фото … справжнє?", "Чи це фейк, що …?"',
    "ar": '"هل صحيح أن …؟", "هل قال … إن …؟", "هل الصورة … حقيقية؟"',
    "fa": '"آیا درست است که …؟", "آیا … گفته است که …؟", "آیا این عکس … واقعی است؟"',
    "hi": '"क्या यह सच है कि …?", "क्या … ने कहा कि …?", "क्या … की यह तस्वीर असली है?"',
    "id": '"Benarkah …?", "Apakah benar … mengatakan …?", "Apakah foto … asli?", "Apakah … hoaks?"',
    "tr": '"… doğru mu?", "… … dedi mi?", "… fotoğrafı gerçek mi?"',
    "ja": '"…は本当ですか？", "…は…と言ったのですか？", "…の写真は本物ですか？"',
    "zh": '"…是真的嗎？", "…真的說過…嗎？", "…的照片是真的嗎？"',
}


def vraagverzoek(taal: str, teksten: list[str], koppen: list[str] | None = None) -> dict:
    """Eén vraag over een rijtje beweringen voor pagina's in dezelfde taal: de taal staat één keer bovenaan, met de
    vormen waarmee een zoeker in die taal begint (in v1 stonden talen door elkaar en schreef het model vaak in de
    verkeerde). In v3 de regels uit de ontwikkelset van v2 (7 fout en 22 klein van 198): geen spreker, naam, context of
    medium erbij, niet de bevinding van de factchecker, aanhalingen niet vertalen, één vraag. In v4 een voorbeeld voor
    een citaat zonder spreker en voor de bevinding van de factchecker, en effort medium: v3 schreef nog "a politician"
    en "this 2013 picture". In v5 (uit de tweede ontwikkelset, 13 fout van 195): de kop van EUvsDisinfo, de ontkenning
    niet omdraaien, bij een post vragen naar wat die zegt, en woorden niet veranderen."""
    from doublecheck.modellen import MODELLEN

    naam = TAALNAMEN.get(taal, taal)
    systeem = (
        f"You write search questions in {naam} for a public archive of fact-checked claims. Each numbered item is a claim "
        f"as it circulated online, sometimes in another language. For each item return, always in {naam}:\n"
        "\n"
        f"1. vraag: the question an ordinary {naam}-speaking person would type into a search engine to find out whether "
        f"this claim is true. Use the form that is most natural for this claim, for example {VORMEN.get(taal, VORMEN['en'])}. "
        "Rules:\n"
        "- Neutral: the question never reveals or presupposes the answer. Never \"why is … false\", never \"the fake "
        "claim that\", never \"debunked\".\n"
        "- Keep the names, places, numbers and dates that make the claim specific, and leave out the rest: filler such "
        "as BREAKING, hashtags, emoji, \"viral post claims\", side remarks.\n"
        "- Add nothing that is not in the claim: no country, year, event, institution or explanation, even if you know "
        "it.\n"
        "- Write names exactly as the claim writes them: never add a first name, surname or title, and never a name that "
        "is not in the claim. If the claim quotes someone without naming the speaker, ask whether what the quote says "
        "is true, and never name or describe a speaker (not \"a politician\", not \"an official\", not \"someone\"): "
        "for “When she was governor of South Carolina, she was rated 50th in education” ask \"Was South Carolina rated "
        "50th in education when she was governor?\"\n"
        "- Mention a photo, video or image only if the claim does, and then ask whether it shows that.\n"
        "- Some claims were written by the fact-checker and already contain the finding (\"An old photo from 2013 is "
        "shared as …\", \"People are falsely sharing …\", \"An edited photo …\"). Ask about what was claimed online, "
        "without the finding. \"2013 picture of a Sikh protest shared as the Delhi farmer rally\" becomes \"Does this "
        "picture show Sikhs at the Delhi farmer rally?\"; \"A post made before Dilip Kumar's death is claimed to be his "
        "last video\" becomes \"Is this Dilip Kumar's last video?\"; \"Photo edited for propaganda against Sonia Gandhi\" "
        "becomes \"Is this photo of Sonia Gandhi real?\"\n"
        "- Keep words in quotation marks, nicknames and terms from other languages as written; do not translate them.\n"
        "- Keep the polarity of the claim: a yes to your question must mean the claim is true. If the claim says "
        "something is not so, ask whether it is not so: \"There was nothing nefarious about the secrecy\" becomes "
        "\"Was there nothing nefarious about the secrecy?\", never \"Was the secrecy nefarious?\"; \"The video is fake\" "
        "never becomes \"Is the video authentic?\".\n"
        "- If the claim reports what a post or message says, ask about what that post says, not about the opposite.\n"
        "- Keep the exact words for things, places and products; do not split, merge or replace them.\n"
        "- Some items start with the fact-checker's headline in brackets. It names the main message of the claim: ask "
        "about that message as the claim states it, not about a side fact or a true event the claim mentions.\n"
        "- Exactly one question, with one question mark and no \"or\" alternatives, at most 110 characters.\n"
        "\n"
        f"2. onderwerp: what the claim is about, as a short neutral noun phrase in {naam} of at most 50 characters: the "
        "people, things, place or event. Never a statement, never a verdict, no full stop. Names exactly as in the claim, "
        "and nothing that is not in the claim (no year, event or country of your own).")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "vraag", "onderwerp"],
            "properties": {"nr": {"type": "integer"}, "vraag": {"type": "string"}, "onderwerp": {"type": "string"}}}}}}
    koppen = koppen or [""] * len(teksten)
    vraag = f"Write in {naam}.\n\n" + "\n".join(
        f"{i}. {f'[headline: {k}] ' if k else ''}{' '.join((t or '').split())}" for i, (t, k) in enumerate(zip(teksten, koppen), 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 4000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": schema}}}


def lees_vragen(tekst: str | None, taal: str, teksten: list[str]) -> list[dict | None]:
    """De antwoorden op nummer: alleen een vraag en een onderwerp die de controle halen (`vraag_klopt`,
    `onderwerp_klopt`) en in de gevraagde taal staan (`in_taal`, `onderwerp_in_taal`). Een nummer dat ontbreekt of twee
    keer voorkomt, telt niet."""
    uit: list[dict | None] = [None] * len(teksten)
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        gezien = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr = a.get("nr")
        if not (isinstance(nr, int) and 1 <= nr <= len(teksten) and gezien[nr] == 1):
            continue
        vraag, onderwerp = " ".join(str(a.get("vraag") or "").split()), " ".join(str(a.get("onderwerp") or "").split())
        if (vraag_klopt(vraag, teksten[nr - 1]) and onderwerp_klopt(onderwerp, vraag) and in_taal(vraag, taal)
                and onderwerp_in_taal(onderwerp, taal) and schrift_klopt(vraag, teksten[nr - 1], taal)
                and schrift_klopt(onderwerp, teksten[nr - 1], taal)):
            uit[nr - 1] = {"vraag": vraag, "onderwerp": onderwerp}
    return uit


def _laatste(antwoorden: list[dict]) -> dict[str, dict]:
    return {a["pagina"]: a for a in antwoorden if a.get("vraag") and a.get("versie") == VERSIE}


def proefpaginas(kandidaten: list[str], zaad: int = ZAAD) -> list[str]:
    """De pagina's van de proef: willekeurig, bij dezelfde kandidaten altijd dezelfde."""
    return random.Random(zaad).sample(sorted(kandidaten), min(PROEF_N, len(kandidaten)))


def poort(antwoorden: list[dict], pad: str | Path = LABELS) -> tuple[bool, str]:
    """Mogen de zoekvragen in de uitgave? Alleen als ik er minstens `MIN_GELEZEN` las, elk nog precies zoals het antwoord
    nu luidt, zonder twijfel, met hoogstens 1 fout op de 100 (naar boven afgerond op een hele fout, B87, zoals B77) en
    hoogstens `MAX_KLEIN` kleine."""
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False, "nog niets gelezen"
    laatste = _laatste(antwoorden)
    gelezen = Counter(l["label"] for p, l in labels.items()
                      if l.get("label") in LEESLABELS and p in laatste
                      and (l.get("vraag"), l.get("onderwerp")) == (laatste[p]["vraag"], laatste[p]["onderwerp"]))
    n = sum(gelezen.values())
    if n < MIN_GELEZEN:
        return False, f"{n} gelezen, minstens {MIN_GELEZEN}"
    if gelezen["twijfel"] or gelezen["fout"] > math.ceil(MAX_FOUT * n):
        return False, f"{gelezen['fout']} fout (hoogstens {math.ceil(MAX_FOUT * n)}) en {gelezen['twijfel']} twijfel"
    if gelezen["klein"] > MAX_KLEIN:
        return False, f"{gelezen['klein']} kleine fouten, hoogstens {MAX_KLEIN}"
    return True, f"{gelezen['goed']} goed, {gelezen['klein']} klein en {gelezen['fout']} fout van de {n}"


def geldig(antwoorden: list[dict], pad: str | Path = LABELS) -> tuple[dict[str, dict], str]:
    """De zoekvragen voor de uitgave, per pagina, met de taal en de tekst waaruit ze kwamen; niets als de poort dicht is.
    De uitgave neemt een vraag alleen over als die tekst nog precies zo luidt."""
    open_, reden = poort(antwoorden, pad)
    if not open_:
        return {}, reden
    return {p: {k: a[k] for k in ("taal", "bron", "vraag", "onderwerp")} for p, a in _laatste(antwoorden).items()}, reden


def voor_de_uitgave() -> tuple[dict[str, dict], str]:  # pragma: no cover - bestanden
    return geldig(_jsonl(ANTWOORDEN))


def alles() -> dict[str, dict]:  # pragma: no cover - bestanden
    """Alles wat de controle doorliet, zonder poort: alleen voor een voorbeeld op de eigen computer."""
    return {p: {k: a[k] for k in ("taal", "bron", "vraag", "onderwerp")} for p, a in _laatste(_jsonl(ANTWOORDEN)).items()}


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _kandidaten() -> list[dict]:  # pragma: no cover - een bestand
    """Elke pagina van de nieuwste uitgave, met de taal van de vraag en de tekst waaruit ze komt."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    vertalingen: dict[str, dict[str, str]] = {}
    for pagina, taal, tekst in pub.execute("SELECT pagina, taal, tekst FROM vertaling"):
        vertalingen.setdefault(pagina, {})[taal] = tekst
    koppen: dict[str, str] = {}
    for pagina, url in pub.execute("SELECT pagina, url FROM check_ WHERE url LIKE '%euvsdisinfo.eu/report/%' ORDER BY pagina, volg"):
        koppen.setdefault(pagina, kop_uit_adres(url))
    uit = []
    for nummer, taal_bewering, bewering in pub.execute("SELECT nummer, taal, bewering FROM pagina"):
        taal, tekst = bron(taal_bewering, bewering, vertalingen.get(nummer, {}))
        uit.append({"pagina": nummer, "taal": taal, "bron": tekst, **({"kop": koppen[nummer]} if koppen.get(nummer) else {})})
    return uit


def _vragen(proef: int | None, zaad: int = ZAAD) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(ANTWOORDEN)
    klaar = {(a["pagina"], a["taal"], a["bron"]) for a in eerder if a.get("vraag") and a.get("versie") == VERSIE}
    alle = _kandidaten()
    werk = [k for k in alle if (k["pagina"], k["taal"], k["bron"]) not in klaar]
    if proef:
        gekozen = set(proefpaginas([k["pagina"] for k in alle], zaad)[:proef])
        werk = [k for k in werk if k["pagina"] in gekozen]
    groepen = _groepen(werk)
    if not groepen:
        print("niets te vragen")
        return
    uitgegeven = sum(a.get("kosten", 0.0) for a in eerder)
    if uitgegeven + SCHATTING * len(werk) > GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} uitgegeven plus ${SCHATTING * len(werk):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[dict]) -> None:
        taal, teksten = groep[0]["taal"], [k["bron"] for k in groep]
        try:
            msg = client.messages.create(**vraagverzoek(taal, teksten, [k.get("kop", "") for k in groep]))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for k, a in zip(groep, lees_vragen(tekst, taal, teksten)):
                f.write(json.dumps({**k, **(a or {"vraag": None, "onderwerp": None}), "versie": VERSIE,
                                    "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(ANTWOORDEN)
    print(f"{len(_laatste(nu))} met een zoekvraag, {sum(not a.get('vraag') for a in nu)} zonder; "
          f"${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def _groepen(werk: list[dict]) -> list[list[dict]]:
    per_taal: dict[str, list[dict]] = {}
    for k in werk:
        per_taal.setdefault(k["taal"], []).append(k)
    return [lijst[i:i + PER_VRAAG] for lijst in per_taal.values() for i in range(0, len(lijst), PER_VRAAG)]


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    """Wat er al uitging: de antwoorden, en de schatting van een batch die nog loopt."""
    return (sum(a.get("kosten", 0.0) for a in _jsonl(ANTWOORDEN))
            + sum(b["schatting"] for b in _jsonl(BATCHES) if b.get("werkelijk") is None))


def _indienen() -> None:  # pragma: no cover - de Batch API, op openbare beweringen
    """De volle ronde via de Batch API: alles wat nog geen zoekvraag van deze versie heeft en niet al in een batch zit."""
    from datetime import date

    import anthropic

    from doublecheck.varianten import laad_sleutel

    klaar = {(a["pagina"], a["taal"], a["bron"]) for a in _jsonl(ANTWOORDEN) if a.get("vraag") and a.get("versie") == VERSIE}
    lopend = {p for b in _jsonl(BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    werk = [k for k in _kandidaten() if (k["pagina"], k["taal"], k["bron"]) not in klaar and k["pagina"] not in lopend]
    groepen = _groepen(werk)
    if not groepen:
        print("niets te vragen")
        return
    schatting = SCHATTING_BATCH * len(werk)
    if _uitgegeven() + schatting > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${schatting:.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client = anthropic.Anthropic(max_retries=6)
    verzoeken = [{"custom_id": f"g{i}", "params": vraagverzoek(g[0]["taal"], [k["bron"] for k in g], [k.get("kop", "") for k in g])}
                 for i, g in enumerate(groepen)]
    batch = client.messages.batches.create(requests=verzoeken)
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / f"batch-{batch.id}.json").write_text(json.dumps({f"g{i}": g for i, g in enumerate(groepen)}, ensure_ascii=False),
                                                encoding="utf-8")
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": batch.id, "paginas": [k["pagina"] for k in werk], "schatting": round(schatting, 4),
                            "versie": VERSIE, "dag": date.today().isoformat(), "werkelijk": None}) + "\n")
    print(f"batch {batch.id}: {len(werk)} pagina's in {len(groepen)} vragen, schatting ${schatting:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        batches, open_ = _jsonl(BATCHES), 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            groepen = json.loads((MAP / f"batch-{b['id']}.json").read_text(encoding="utf-8"))
            werkelijk, goed, zonder = 0.0, 0, 0
            with ANTWOORDEN.open("a", encoding="utf-8") as f:
                for r in client.messages.batches.results(b["id"]):
                    groep = groepen.get(r.custom_id) or []
                    if not groep:
                        continue
                    if r.result.type != "succeeded":
                        zonder += len(groep)
                        continue
                    msg = r.result.message
                    kosten = kosten_batch(bc.gebruik_uit(msg), "haiku")
                    werkelijk += kosten
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(x, "text", "") or "" for x in msg.content)
                    for k, a in zip(groep, lees_vragen(tekst, groep[0]["taal"], [x["bron"] for x in groep])):
                        goed += bool(a)
                        zonder += not a
                        f.write(json.dumps({**k, **(a or {"vraag": None, "onderwerp": None}), "versie": b["versie"],
                                            "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
            BATCHES.write_text("".join(json.dumps(x) + "\n" for x in batches), encoding="utf-8")
            print(f"batch {b['id']}: {goed} met een zoekvraag, {zonder} zonder, ${werkelijk:.2f}")
        if not open_ or time.time() > einde:
            print(f"{open_} batches nog open; samen ${_uitgegeven():.2f} van ${GRENS:.2f}")
            return
        time.sleep(60)


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["kandidaten", "vragen", "lezen", "tellen", "indienen", "ophalen"])
    p.add_argument("--proef", type=int)
    p.add_argument("--wacht", type=int, default=0, help="minuten wachten tot de batch klaar is")
    p.add_argument("--zaad", type=int, default=ZAAD, help=f"de poort {ZAAD}, de ontwikkelset {ONTWIKKEL_ZAAD}")
    a = p.parse_args()
    try:
        if a.stap == "vragen":
            return _vragen(a.proef, a.zaad)
        if a.stap == "indienen":
            return _indienen()
        if a.stap == "ophalen":
            return _ophalen(a.wacht)
        if a.stap == "kandidaten":
            k = _kandidaten()
            print(f"{len(k)} pagina's; per taal van de vraag:", Counter(x["taal"] for x in k).most_common(15))
            return
        antwoorden = _jsonl(ANTWOORDEN)
        if a.stap == "lezen":
            laatste = _laatste(antwoorden)
            proef = [p for p in proefpaginas([k["pagina"] for k in _kandidaten()], a.zaad) if p in laatste]
            MAP.mkdir(parents=True, exist_ok=True)
            uit = [{"pagina": p, "taal": laatste[p]["taal"], "bron": laatste[p]["bron"], "vraag": laatste[p]["vraag"],
                    "onderwerp": laatste[p]["onderwerp"]} for p in proef]
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", len(uit))
            return
        print(f"{len(_laatste(antwoorden))} met een zoekvraag, {sum(not x.get('vraag') for x in antwoorden)} zonder; "
              f"${sum(x.get('kosten', 0.0) for x in antwoorden):.3f}")
        print("de poort:", poort(antwoorden))
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
