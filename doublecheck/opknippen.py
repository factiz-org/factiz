"""Opknippen en maskeren vóór de controlestap (B43, DR3, PLAN #31.10).

Naar het model gaat alleen de bewering: de tekst van het bericht, zonder de
chatomgeving en zonder persoonsgegevens. Het beeld zelf verlaat de server nooit.

- `knip`: weg met de regels die bij de app horen en niet bij het bericht: de
  statusbalk, de kop van de groep of het gesprek (en de naam erboven), de
  afzender, "Forwarded", tijden, dagscheiders, de invoerbalk en de knoppen
  onder een post.
- `maskeer`: telefoonnummers, e-mailadressen, handles en links naar een
  persoon of nummer worden een label. Getallen in de bewering zelf (jaren,
  bedragen, percentages) blijven staan: een telefoonnummer begint met + of 0,
  of heeft de vorm (555) 123-4567.

- `zwart_beeld` (B55): het beeld dat naar het model gaat, met zwart wat het
  maskeren uit de tekst zou halen (nummers, e-mailadressen, handles, links naar
  een persoon) en de regels met een naam (de kop van een groep of contact, een
  afzender); opnieuw opgeslagen, dus zonder metadata.

Wat hier doorheen komt, wordt nergens gelogd of bewaard (DR3).
"""

from __future__ import annotations

import re

_TIJD = re.compile(r"\b\d{1,2}[:.]\d{2}(\s?[AaPp]\.?[Mm]\.?)?\b")
_STATUSRESTEN = re.compile(r"\b(LTE|[345]G|5GE|Wi-?Fi|AM|PM|KB/s)\b|\d{1,3}\s?%|[^\w\s]|\d", re.I)
_LOS = {"forwarded", "forwarded many times", "doorgestuurd", "vaak doorgestuurd", "today", "yesterday",
        "vandaag", "gisteren", "type a message", "message", "bericht", "typ een bericht", "edited", "bewerkt",
        "translate post", "translate tweet", "show more", "see more", "meer weergeven"}
_KNOPPEN = {"reply", "replies", "retweet", "retweets", "repost", "reposts", "quote", "quotes", "like", "likes",
            "share", "shares", "comment", "comments", "view", "views", "bookmark", "bookmarks", "follow",
            "following", "send", "save", "volgen", "reageren", "delen", "vind-ik-leuk", "opmerkingen", "k", "m"}
_KOPWOORDEN = re.compile(r"\b(participants?|members?|online|typing|last seen|tap here for group info|deelnemers|"
                         r"leden|laatst gezien|typt)\b", re.I)
_TELEFOON = re.compile(r"\+\d[\d\s\-().]{6,}\d|\(\d{3}\)\s?\d{3}[-\s]\d{4}|\b\d{3}-\d{3}-\d{4}\b"
                       r"|\b0\d{1,4}[-\s]?\d{6,8}\b|\b0\d{3,4}\s\d{3}\s?\d{3,4}\b")
_EMAIL = re.compile(r"[\w.+-]+ ?@ ?[\w-]+(\.[\w-]+)+")  # §155: de OCR zet soms een spatie rond de @
_WAME = re.compile(r"(https?://)?(wa\.me|api\.whatsapp\.com/send\?phone=)/?\d+", re.I)
_PROFIEL = re.compile(r"(https?://)?(www\.)?(t\.me|instagram\.com|facebook\.com|fb\.com|x\.com|twitter\.com|"
                      r"tiktok\.com)/[A-Za-z0-9_.]+/?", re.I)  # tiktok.com/@naam vangt de handleregel
# §252: de OCR zet soms een underscore vlak voor de @ ("_@naam"); een e-mailadres is dan al gemaskeerd
_HANDLE = re.compile(r"(?<![A-Za-z0-9@.])@[A-Za-z0-9_]{2,30}(\.[A-Za-z0-9_]+)*")


def _woorden(regel: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", regel)


def _is_omgeving(regel: str) -> bool:
    """Een regel die alleen bij de app hoort, op zichzelf bekeken."""
    kaal = " ".join(re.sub(r"[^\w\s-]", " ", regel).split()).lower()
    if not kaal:
        return True
    if kaal in _LOS:
        return True
    if not _STATUSRESTEN.sub(" ", _TIJD.sub(" ", regel)).strip():
        return True  # alleen tijden, percentages, netwerk en tekens: de statusbalk of een tijdstempel
    woorden = [w.lower() for w in _woorden(regel)]
    if woorden and all(w in _KNOPPEN for w in woorden):
        return True  # de knoppen en tellers onder een post
    if regel.lstrip().startswith("~"):
        return True  # een afzender die niet in de contacten staat
    return bool(_TELEFOON.search(regel)) and len(_woorden(_TELEFOON.sub(" ", regel))) <= 5  # afzender met nummer


def knip(tekst: str) -> str:
    """De regels van het bericht zelf; de kop van een gesprek gaat er samen met
    de naam erboven af."""
    regels = [r for r in tekst.splitlines() if r.strip()]  # de OCR zet soms lege regels tussen kop en naam
    weg = set()
    for i, regel in enumerate(regels):
        if _KOPWOORDEN.search(regel) and len(_woorden(regel)) <= 6:
            weg.add(i)
            if i > 0 and 0 < len(_woorden(regels[i - 1])) <= 5:
                weg.add(i - 1)  # de naam van de groep of het contact
        elif _is_omgeving(regel):
            weg.add(i)
    return "\n".join(r.strip() for i, r in enumerate(regels) if i not in weg and r.strip())


def maskeer(tekst: str) -> str:
    """Persoonsgegevens worden een label; de rest blijft letter voor letter staan."""
    tekst = _EMAIL.sub("[e-mail]", tekst)
    tekst = _WAME.sub("[telefoon]", tekst)
    tekst = _PROFIEL.sub(lambda m: m.group(0).split("/")[0 if not m.group(1) else 2] + "/[handle]", tekst)
    tekst = _TELEFOON.sub("[telefoon]", tekst)
    return _HANDLE.sub("[handle]", tekst)


def opknippen(tekst: str) -> str:
    """Wat naar het model gaat: eerst knippen, dan maskeren."""
    return maskeer(knip(tekst))


# --- B55: het beeld voor het model (PLAN #32.36) -------------------------------------------------------------------

_PERSOONLIJK = (_EMAIL, _WAME, _PROFIEL, _TELEFOON, _HANDLE)
_RAND = 3  # pixels rond een zwart vak, zodat geen randje van een letter blijft staan


def namen_regels(regels: list[str]) -> set[int]:
    """De regels met een naam, zoals `knip` ze weghaalt: de kop van een groep of gesprek met de naam erboven, een
    afzender die niet in de contacten staat ("~ Naam"), en een afzender met zijn nummer."""
    uit = set()
    for i, regel in enumerate(regels):
        if _KOPWOORDEN.search(regel) and len(_woorden(regel)) <= 6:
            uit.add(i)
            if i > 0 and 0 < len(_woorden(regels[i - 1])) <= 5:
                uit.add(i - 1)
        elif regel.lstrip().startswith("~") or (_TELEFOON.search(regel)
                                                 and len(_woorden(_TELEFOON.sub(" ", regel))) <= 5):
            uit.add(i)
    return uit


def zwarte_vakken(regels: list[list[dict]]) -> list[tuple[int, int, int, int]]:
    """Per regel de woorden zoals de tekstherkenning ze las (`tekst`, `links`, `boven`, `breedte`, `hoogte`); terug de
    vakken (links, boven, rechts, onder) die zwart moeten: een hele regel met een naam, en elk woord dat het maskeren van
    de tekst een label zou geven."""
    teksten = [" ".join(w["tekst"] for w in r) for r in regels]
    namen = namen_regels(teksten)
    vakken = []
    for i, r in enumerate(regels):
        treffers = [] if i in namen else [m.span() for patroon in _PERSOONLIJK for m in patroon.finditer(teksten[i])]
        plek = 0
        for w in r:
            begin, eind = plek, plek + len(w["tekst"])
            plek = eind + 1
            if i in namen or any(begin < te and eind > tb for tb, te in treffers):
                vakken.append((w["links"], w["boven"], w["links"] + w["breedte"], w["boven"] + w["hoogte"]))
    return vakken


def zwart_beeld(beeld: bytes, ocr) -> tuple[bytes, int]:
    """Het beeld voor het model (B55): gelezen met de tekstherkenning van het product, de vakken van `zwarte_vakken`
    zwart, en opnieuw opgeslagen zonder metadata, in het geheugen. Geeft de bytes en het aantal zwarte vakken."""
    import io

    import pytesseract
    from PIL import ImageDraw

    from doublecheck.image_fingerprint import as_image
    from doublecheck.ocr import _pakketten

    afbeelding = as_image(beeld).convert("RGB")
    pakketten, _ = _pakketten(afbeelding, ocr)
    try:
        data = pytesseract.image_to_data(afbeelding, lang=pakketten, timeout=ocr.timeout_seconds,
                                         output_type=pytesseract.Output.DICT)
    except RuntimeError:  # de tijdgrens: dan geen vakken, wel zonder metadata
        data = {"text": []}
    regels: dict[tuple, list[dict]] = {}
    for i, woord in enumerate(data["text"]):
        if str(woord).strip():
            regels.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(
                {"tekst": str(woord), "links": data["left"][i], "boven": data["top"][i],
                 "breedte": data["width"][i], "hoogte": data["height"][i]})
    vakken = zwarte_vakken(list(regels.values()))
    tekenaar = ImageDraw.Draw(afbeelding)
    for links, boven, rechts, onder in vakken:
        tekenaar.rectangle((links - _RAND, boven - _RAND, rechts + _RAND, onder + _RAND), fill="black")
    uit = io.BytesIO()
    if beeld[:3] == b"\xff\xd8\xff":
        afbeelding.save(uit, format="JPEG", quality=92)
    else:
        afbeelding.save(uit, format="PNG")
    return uit.getvalue(), len(vakken)
