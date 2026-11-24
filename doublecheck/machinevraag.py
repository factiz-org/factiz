"""De vraag aan de machine (verificatie-v1 tot en met v4, B43, #31.8): de vraag zelf, het geheugen, en het lezen van het antwoord en de bronnen; de kern van de controle (PLAN #32.7c)."""

from __future__ import annotations

import base64
import re
from pathlib import Path


PROMPTVERSIE = "verificatie-v1"


MODEL = "haiku"


ZOEKEN_PER_1000 = 10.0  # dollar, ook in de Batch API


MAX_ZOEKEN = 3


N_GEHEUGEN = 5


VLOER_GEHEUGEN = 0.50


OORDELEN = ("klopt", "klopt niet", "let op", "onzeker", "satire", "geen bewering")


SYSTEEM = ("You are a careful fact-checker. You decide whether the main factual claim in a message is accurate, "
           "based only on evidence you can point to: fact-checks in the Factiz memory that is given to you, or "
           "reliable sources you find with web search. You never rely on your own knowledge alone.")


SYSTEEM_KAAL = ("You are a careful fact-checker. You decide whether the main factual claim in a message is accurate, "
                "based on your own knowledge.")


VRAAG = """Steps:
1. State the main factual claim of the message in one sentence, in the language of the message. If the message makes no checkable factual claim (an advertisement, an opinion, a greeting, fiction), the verdict is "geen bewering".
2. Look at the Factiz memory. If a listed fact-check is about this same claim (same subject, same event, same direction), you may use its verdict; cite it as [F1], [F2] and so on.
3. Otherwise search the web, in the language of the claim and in English, for reliable sources: news agencies, quality media, official bodies, scientific sources, encyclopedias.
4. Decide:
   - "klopt niet" only if a fact-check in the memory rates this same claim false or misleading, or a reliable source you found directly contradicts the claim. Quote the decisive passage.
   - "klopt" only if a reliable source directly confirms the claim. Quote it.
   - "satire" if the message comes from a satirical source.
   - "onzeker" in every other case: no decisive source, sources that disagree, or doubt. A surprising claim is not false because it is surprising.
End your answer with exactly these three lines:
BEWERING: <the claim>
OORDEEL: <klopt | klopt niet | onzeker | satire | geen bewering>
UITLEG: <one sentence in Dutch>"""


# v2 (ronde 2): de twee oorzaken van de valse vlaggen in ronde 1 (§145), en het
# label [F..] dat twee antwoorden vergaten.
VRAAG_V2 = VRAAG.replace(
    "cite it as [F1], [F2] and so on.",
    "cite it as [F1], [F2] and so on. Always write the label when you rely on a memory fact-check.").replace(
    '   - "onzeker" in every other case:',
    "   - Judge the claim as of the time the message circulated, not as of today: later events do not make an "
    "earlier claim false.\n"
    "   - A small deviation in a number, date or distance that does not change the core of the claim (rounding, "
    "a year off by one in a recollection, 84 km called 100 km) is not \"klopt niet\"; fact-checkers rate such "
    "claims true or mostly true.\n"
    '   - "onzeker" in every other case:')


# v3 (ronde 3) = v2; met omgekeerd zoeken komen het blok [R..] en deze regel erbij.
REGEL_BEELDZOEKEN = ("If these pages show the image in another context, place or time than the caption says, that "
                     "contradicts the caption; cite the [R..]. A page that merely shows the same image is not proof "
                     "either way.")


# v4 (ronde 4): *let op* naast *klopt niet*, en een bron die laat zien wat er wél
# gebeurde telt als tegenspraak (het model vond de ICID-erkenning bij de
# UNESCO-claim en zei toch *onzeker*, ronde 2).
REGEL_LET_OP = ('"let op" if {grond}, but you have a concrete reason to doubt it. Name the reason in UITLEG; it must '
                "be one of these: (1) an event this big would have been reported by reliable sources and none do (the "
                "death of a well-known person, a new law, a decision by many countries); (2) the message follows a "
                "known pattern of false claims, such as old or unrelated footage presented as new, or a fake that "
                "circulated before; (3) for health and science: the claim goes beyond what the scientific evidence "
                'shows. Not finding anything about a small local event is not a reason: that is "onzeker".')


VRAAG_V4 = VRAAG_V2.replace(
    "or a reliable source you found directly contradicts the claim.",
    "or a reliable source you found directly contradicts the claim or shows what actually happened instead (another "
    "body gave the recognition, the photo was taken elsewhere or earlier, the person said something else).").replace(
    '   - "onzeker" in every other case: no decisive source, sources that disagree, or doubt.',
    "   - " + REGEL_LET_OP.format(grond="no source contradicts the claim") + "\n"
    '   - "onzeker" in every other case: no decisive source, sources that disagree, or doubt without one of these '
    "reasons.").replace(
    "<klopt | klopt niet | onzeker | satire | geen bewering>",
    "<klopt | klopt niet | let op | onzeker | satire | geen bewering>")


# De nulmeting: hetzelfde model zonder geheugen en zonder zoeken.
VRAAG_V4_KAAL = "\n".join((
    "You have no search tool and no fact-checks: judge from your own knowledge.",
    VRAAG.splitlines()[0],
    VRAAG.splitlines()[1],
    "2. Decide:",
    '   - "klopt niet" if you know the claim is false or misleading.',
    '   - "klopt" if you know the claim is accurate.',
    *[r for r in VRAAG_V2.splitlines() if r.startswith(('   - "satire"', "   - Judge the claim", "   - A small"))],
    "   - " + REGEL_LET_OP.format(grond="you do not know the claim to be false"),
    '   - "onzeker" in every other case. A surprising claim is not false because it is surprising.',
    *VRAAG_V4.splitlines()[-4:]))


# v5 (ronde 5) = v4, met het bijschrift onder het beeld en met omgekeerd zoeken het blok [R..].
VRAGEN = {"verificatie-v1": VRAAG, "verificatie-v2": VRAAG_V2, "verificatie-v3": VRAAG_V2, "verificatie-v4": VRAAG_V4,
          "verificatie-v5": VRAAG_V4}


VRAGEN_KAAL = {"verificatie-v4": VRAAG_V4_KAAL}


_OORDEEL_EN = {"onwaar": "false", "misleidend": "misleading", "deels-waar": "partly true", "waar": "true",
               "onbewezen": "unproven", "onbekend": "unrated", "satire": "satire"}


def lees_antwoord(tekst: str) -> tuple[str, str | None, str | None]:
    """(oordeel, bewering, uitleg) uit de laatste regels van die naam; het
    oordeel is "onleesbaar" als de regel ontbreekt of buiten de oordelen valt."""
    def laatste(naam: str) -> str | None:
        regels = re.findall(rf"^[\s*_#>-]*{naam}[\s*_]*:[\s*_]*(.*)$", tekst, flags=re.I | re.M)
        return regels[-1].strip().strip("*_ ").strip() if regels else None

    oordeel = (laatste("OORDEEL") or "").lower().strip(" .\"'")
    return (oordeel if oordeel in OORDELEN else "onleesbaar"), laatste("BEWERING"), laatste("UITLEG")


def bronnen_uit(blokken: list[dict], geheugen: list[dict], beeldpaginas: list[dict] = ()) -> list[dict]:
    """De bronnen van een antwoord: eerst de passages die de API citeert (letterlijk
    uit de bron), dan de checks uit het geheugen en de pagina's van het
    omgekeerd zoeken die het antwoord noemt."""
    web, mem, gezien = [], [], set()
    for b in blokken:
        if b.get("type") != "text":
            continue
        for c in b.get("citations") or []:
            if c.get("type") == "web_search_result_location" and (c["url"], c.get("cited_text")) not in gezien:
                gezien.add((c["url"], c.get("cited_text")))
                web.append({"soort": "web", "url": c["url"], "titel": c.get("title"), "citaat": c.get("cited_text")})
        for n in re.findall(r"\[F(\d+)\]", b.get("text") or ""):
            k = int(n) - 1
            if 0 <= k < len(geheugen) and ("F", k) not in gezien:
                gezien.add(("F", k))
                mem.append({"soort": "geheugen", "url": geheugen[k].get("url"), "claim": geheugen[k]["claim"]})
        for n in re.findall(r"\[R(\d+)\]", b.get("text") or ""):
            k = int(n) - 1
            if 0 <= k < len(beeldpaginas) and ("R", k) not in gezien:
                gezien.add(("R", k))
                mem.append({"soort": "beeld", "url": beeldpaginas[k]["url"], "titel": beeldpaginas[k].get("titel")})
    return web + mem


def verberg(kandidaten: list[dict], eigen: set[str]) -> list[dict]:
    """Het geheugen zonder de eigen check (omstandigheid b), hooguit `N_GEHEUGEN`."""
    return [k for k in kandidaten if k["claim"] not in eigen][:N_GEHEUGEN]


def zonder_factchecks_aan(omstandigheid: str) -> bool:
    """In (b) moet het model het zelf bewijzen: factchecksites geblokkeerd, op
    het web en in het omgekeerd zoeken."""
    return omstandigheid.startswith("b")


def vraagtekst(s: dict, kandidaten: list[dict], versie: str, beeldpaginas: list[dict] | None = None,
               kaal: bool = False) -> str:
    """De tekst onder het bericht (of onder het beeld): vanaf v2 eerst de datum;
    in v3 het bijschrift onder het beeld, en met omgekeerd zoeken het blok [R..]
    met zijn regel; kaal zonder geheugen en met de vraag zonder zoeken."""
    if s["soort"] == "beeld":
        kop = ("The message is the image above, posted with this caption:\n" + s["tekst"]
               if versie in ("verificatie-v3", "verificatie-v5") and s.get("tekst") else "The message is the image above.")
    else:
        kop = f"Message:\n{s['tekst']}"
    if versie in ("verificatie-v2", "verificatie-v3", "verificatie-v4", "verificatie-v5"):
        kop += (f"\n\nThis message circulated around {s['datum']}." if s.get("datum")
                else "\n\nThe date of this message is unknown.")
    if kaal:
        return f"{kop}\n\n{VRAGEN_KAAL[versie]}"
    extra = ""
    if beeldpaginas is not None:
        from doublecheck.beeldzoeken import beeldzoek_tekst

        extra = f"\n\n{beeldzoek_tekst(beeldpaginas)}\n{REGEL_BEELDZOEKEN}"
    return f"{kop}\n\n{geheugen_tekst(kandidaten)}{extra}\n\n{VRAGEN[versie]}"


def geheugen_tekst(kandidaten: list[dict]) -> str:
    if not kandidaten:
        return "Factiz memory: no fact-check found for this message."
    regels = [f"[F{n}] {k.get('redactie', '?')}, {k.get('datum', '?')}, rated "
              f"{_OORDEEL_EN.get(k.get('oordeel'), k.get('oordeel'))}: {' '.join(str(k.get('tekst', '')).split())[:400]}"
              for n, k in enumerate(kandidaten, 1)]
    return ("Factiz memory (fact-checks by editors; they may or may not be about this claim):\n" + "\n".join(regels))


def kandidaten_uit(lees, lijst) -> list[dict]:  # pragma: no cover - op de database
    """De checks boven de vloer uit één zoekuitslag, met oordeel, redactie,
    datum en link van de jongste check (ook voor de route, #31.10)."""
    kandidaten = []
    for c in lijst:
        if c.similarity < VLOER_GEHEUGEN:
            continue
        tekst = lees.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (c.claim_id,)).fetchone()[0]
        fc = lees.execute("SELECT publisher, verdict_normalized, review_date, url FROM factcheck "
                          "WHERE claim_id = ? ORDER BY review_date DESC LIMIT 1", (c.claim_id,)).fetchone()
        kandidaten.append({"claim": c.claim_id, "gelijkenis": round(c.similarity, 4), "tekst": tekst,
                           "redactie": fc["publisher"], "oordeel": fc["verdict_normalized"],
                           "datum": str(fc["review_date"])[:10], "url": fc["url"]})
    return kandidaten


def verzoek(s: dict, kandidaten: list[dict], omstandigheid: str, blok: list[str], model: str = MODEL,
            versie: str = PROMPTVERSIE, beeldpaginas: list[dict] | None = None) -> dict:  # pragma: no cover
    from doublecheck.modellen import MODELLEN

    kaal = omstandigheid == "k"
    zoeken = {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_ZOEKEN}
    if zonder_factchecks_aan(omstandigheid):
        zoeken["blocked_domains"] = blok
    inhoud = [{"type": "text", "text": vraagtekst(s, kandidaten, versie, beeldpaginas, kaal=kaal)}]
    if s["soort"] == "beeld":
        pad = Path(s["beeld"])
        soort = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(pad.suffix.lower(), "image/jpeg")
        inhoud.insert(0, {"type": "image", "source": {"type": "base64", "media_type": soort,
                                                      "data": base64.b64encode(pad.read_bytes()).decode()}})
    params = {"model": MODELLEN[model]["id"], "max_tokens": 4_000, "system": SYSTEEM_KAAL if kaal else SYSTEEM,
              "messages": [{"role": "user", "content": inhoud}], "output_config": {"effort": "low"}}
    if not kaal:
        params["tools"] = [zoeken]
    return {"custom_id": f"{omstandigheid}-{s['id']}", "params": params}
