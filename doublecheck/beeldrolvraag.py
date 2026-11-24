"""De rol van elk beeld in een factcheckartikel (rol-v1, PLAN #32.21): de kern van *vastleggen bij de bron*.

Een treffer op een beeld uit een factcheckartikel zegt alleen "dit beeld is gecheckt" als het het virale beeld is.
Een origineel, een bewijsbeeld (een kaart, een nieuwsbericht, een schermbeeld van een AI-detector) of huisstijl zegt
iets anders (§193). Per artikel één vraag aan Haiku over de openbare artikeltekst rond de beelden. In `rol-v1` gaat geen
beeld mee; in `rol-v2` alleen het deelbeeld, want dat staat in de kop van de pagina, zonder tekst eromheen (PLAN #32.21,
PO 2026-11-02). In `rol-v3` gaat elk beeld mee: `rol-v2` miste de virale beelden in het artikel, waar het alleen de tekst
zag (§198, PLAN #32.26). Een antwoord dat niet te lezen is, maakt een beeld nooit viraal.
"""

from __future__ import annotations

import json

ROLLEN = ("viraal", "origineel", "bewijs", "huisstijl", "onbekend")
_ENGELS = {"viral": "viraal", "original": "origineel", "evidence": "bewijs", "house": "huisstijl",
           "unknown": "onbekend"}
MAX_BEELDEN = 12          # ruim boven wat de oogst per artikel neemt (5)
MAX_CONTEXT = 300         # tekens per stuk tekst rond een beeld


VRAAG_V1 = """Below is a fact-check article: the claim it checks, its title, and for each image in the article the \
text around it (alt text, caption, the sentence before and after). Give each image [B1], [B2], ... one role:
- "viral": the image that circulated and was fact-checked, or a screenshot of the post that shared it. The article's \
share image counts as viral when it shows the viral image, even with a stamp or label on it.
- "original": the authentic photo or video the viral image was taken or edited from.
- "evidence": other material the fact-checker shows: a map, a news article, a document, a chart, search results, a \
screenshot of an AI-detection tool or of a reverse image search, a photo of another event.
- "house": a logo, an author photo, a rating graphic, a banner, an advertisement, a thumbnail of another article.
- "unknown": the text does not make clear which of these it is.

Decide only from the text given. Use "unknown" when unsure; never guess "viral".

Claim checked: {claim}
Title: {titel}

{beelden}"""


# rol-v2: dezelfde rollen woord voor woord; alleen het deelbeeld gaat zelf mee
VRAAG_V2 = VRAAG_V1.replace(
    "the sentence before and after). ",
    "the sentence before and after). The article's share image is also shown above, as an image. ").replace(
    "Decide only from the text given.", "Decide from the text given and, for the share image, from the image itself.")


# rol-v3: dezelfde rollen woord voor woord; elk beeld gaat mee, na zijn label, en de regel van de PO (2026-11-02) voor
# een beeld van de factchecker met het virale beeld erin geldt nu ook binnen het artikel
VRAAG_V3 = VRAAG_V1.replace(
    "the sentence before and after). ",
    "the sentence before and after). Each image is also shown above, in order, right after its label [B1], [B2], ... "
).replace(
    '- "unknown": the text does not make clear which of these it is.',
    '- "unknown": the text does not make clear which of these it is.\n\nAn image made by the fact-checker that shows '
    'the viral image (with a stamp, a label, or next to the original) also counts as viral.').replace(
    "Decide only from the text given.", "Decide from the text given and from the images themselves.")


VRAGEN = {"rol-v1": {"model": "haiku", "vraag": VRAAG_V1, "deelbeeld": False},
          "rol-v2": {"model": "haiku", "vraag": VRAAG_V2, "deelbeeld": True},
          "rol-v3": {"model": "haiku", "vraag": VRAAG_V3, "deelbeeld": False, "alle": True}}

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["rollen"],
           "properties": {"rollen": {"type": "array", "items": {
               "type": "object", "additionalProperties": False, "required": ["beeld", "rol"],
               "properties": {"beeld": {"type": "string"}, "rol": {"type": "string", "enum": list(_ENGELS)}}}}}}


def _kort(tekst, n: int = MAX_CONTEXT) -> str:
    tekst = " ".join((tekst or "").split())
    return tekst if len(tekst) <= n else tekst[: n - 1] + "…"


def verzoek(claim: str, titel: str, beelden: list[dict], versie: str = "rol-v1",
            deelbeeld: bytes | None = None, beelden_bytes: list[bytes] | None = None) -> dict:
    """De vraag aan het model: de claim, de titel en per beeld de tekst eromheen (hoogstens `MAX_BEELDEN`), met vaste
    JSON. `beelden`: per beeld `alt`, `onderschrift`, `voor`, `na` en `deel` (het deelbeeld). `rol-v2` vraagt de bytes
    van het deelbeeld en toont alleen dat beeld; `rol-v3` vraagt de bytes van elk beeld (`beelden_bytes`, in dezelfde
    volgorde) en toont ze allemaal, elk na zijn label; verkleind en alleen in het geheugen. `rol-v1` toont nooit een
    beeld."""
    from doublecheck.beschrijvingvraag import _jpeg
    from doublecheck.modellen import MODELLEN

    if versie not in VRAGEN:
        raise ValueError(f"rolvraag {versie!r} bestaat niet in de code")
    v = VRAGEN[versie]
    if v["deelbeeld"] != (deelbeeld is not None):
        raise ValueError(f"{versie} {'vraagt' if v['deelbeeld'] else 'toont geen'} deelbeeld")
    n = min(len(beelden), MAX_BEELDEN)
    if v.get("alle"):
        if beelden_bytes is None or len(beelden_bytes) != n or any(b is None for b in beelden_bytes):
            raise ValueError(f"{versie} vraagt de bytes van alle {n} beelden")
    elif beelden_bytes is not None:
        raise ValueError(f"{versie} toont niet elk beeld")
    if deelbeeld is not None and not any(b.get("deel") for b in beelden[:MAX_BEELDEN]):
        raise ValueError("een deelbeeld zonder deelbeeld in het artikel")
    regels = []
    for i, b in enumerate(beelden[:MAX_BEELDEN], 1):
        delen = [("the article's share image, shown above" if deelbeeld is not None else "the article's share image")
                 if b.get("deel") else None,
                 f'alt text: "{_kort(b.get("alt"))}"' if b.get("alt") else None,
                 f'caption: "{_kort(b.get("onderschrift"))}"' if b.get("onderschrift") else None,
                 f'before: "{_kort(b.get("voor"))}"' if b.get("voor") else None,
                 f'after: "{_kort(b.get("na"))}"' if b.get("na") else None]
        regels.append(f"[B{i}] " + ("; ".join(d for d in delen if d) or "(no text around it)"))
    tekst = v["vraag"].format(claim=_kort(claim, 600), titel=_kort(titel, 300), beelden="\n".join(regels))
    inhoud = []
    for i, b in enumerate(beelden_bytes or [], 1):
        inhoud += [{"type": "text", "text": f"[B{i}]"},
                   {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(b)}}]
    if deelbeeld is not None:
        inhoud.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(deelbeeld)}})
    inhoud.append({"type": "text", "text": tekst})
    return {"model": MODELLEN[v["model"]]["id"], "max_tokens": 600,
            "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees_rollen(tekst: str | None, n: int) -> list[str]:
    """De rol van elk van de n beelden uit het JSON-antwoord, in het Nederlands. Onleesbaar, ontbrekend, een onbekend
    woord of twee verschillende rollen voor één beeld: *onbekend*."""
    uit = ["onbekend"] * n
    try:
        d = json.loads(tekst) if isinstance(tekst, str) else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or not isinstance(d.get("rollen"), list):
        return uit
    gezien: dict[int, set[str]] = {}
    for r in d["rollen"]:
        if not isinstance(r, dict) or not isinstance(r.get("beeld"), str):
            continue
        nr = r["beeld"].strip().upper().removeprefix("[").removesuffix("]")
        if not nr.startswith("B") or not nr[1:].isdigit() or not 1 <= int(nr[1:]) <= n:
            continue
        gezien.setdefault(int(nr[1:]) - 1, set()).add(_ENGELS.get(r.get("rol"), "onbekend"))
    for i, rollen in gezien.items():
        uit[i] = rollen.pop() if len(rollen) == 1 else "onbekend"
    return uit
