"""De controle per bericht, de simpele versie (B51, PLAN #32.10).

Eerst de database (kring 1): een check die één kant op wijst, geeft het antwoord meteen. Anders één zoekvraag bij
een zoekdienst die de grote media ziet (Brave), de top 10 met per resultaat de band uit de bronnenlijst, en Sonnet
die het bericht en de resultaten leest. De bronnenlijst beslist de kleur: groen alleen met twee goede uitgevers,
rood alleen met een goede tegenspraak. Gemeten in BENCHMARK §179 (51 van 60 juist, p95 4,3 s).

Alleen de gemaskeerde tekst gaat naar buiten (`berichtcontrole.bericht_uit`); het beeld alleen als
`[berichtcontrole] beeld` aan staat, een besluit van de PO (REQUIREMENTS §9).
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from functools import lru_cache
from urllib.parse import urlsplit

from doublecheck import bronnen as br
from doublecheck import opknippen
from doublecheck.kruiscontrole import eigenaar

N_RESULTATEN = 10
ZOEKPRIJS = 0.005  # Brave: $5 per 1.000 zoekvragen
ZOEKERS = ("brave-v1",)
# wat gelezen mag worden; v1 kent er drie, v2 tot en met v5 vier, v6 zeven
OORDELEN = ("klopt", "klopt niet", "onzeker", "misleidend", "klopt grotendeels", "geen bewering", "satire")
ZONDER_KLEUR = ("klopt grotendeels", "geen bewering", "satire")  # nooit rood, oranje of groen (B46, B48)
# De negen uitkomsten van besluit A en B48: wat Factiz over een bericht zegt (#32.31)
UITKOMSTEN = ("geen bewering", "satire", "klopt", "klopt grotendeels", "klopt niet", "misleidend",
              "over een bewering", "beeld nodig", "niet bevestigd", "onzeker",  # *niet bevestigd*: B57, alleen v9
              "foto niet bij de bron")  # #32.54, DESIGN §4m: alleen met `[berichtcontrole] fotobron`
_UIT_KLEUR = {"rood": "klopt niet", "oranje": "misleidend", "groen": "klopt"}
_TAG = re.compile(r"<[^>]+>")

SYSTEEM = "You check whether a message is true, using the web search results you are given. Be decisive and concise."
VRAAG = """Message:
{bericht}

{datum}

Top results of a web search for this message (with how reliable each website is, from our list of sources):
{resultaten}

Decide:
- "klopt": the results show the main claim of the message is true;
- "klopt niet": the results show it is false (a fact-check, or a reliable outlet saying otherwise);
- "onzeker": the results do not settle it.
In fresh news, numbers that differ somewhat between sources (deaths, injured) are not a contradiction.
Give the numbers of the results that confirm the main claim and of those that contradict it, and one short sentence in Dutch."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["oordeel", "steunt", "spreekt_tegen", "uitleg"],
          "properties": {"oordeel": {"type": "string", "enum": ["klopt", "klopt niet", "onzeker"]},
                         "steunt": {"type": "array", "items": {"type": "integer"}},
                         "spreekt_tegen": {"type": "array", "items": {"type": "integer"}},
                         "uitleg": {"type": "string"}}}
# v2 (#32.11): de lezer kan ook *misleidend* zeggen, en groen mag ook met één goede plus één andere uitgever.
VRAAG_V2 = VRAAG.replace(
    '''- "klopt niet": the results show it is false (a fact-check, or a reliable outlet saying otherwise);''',
    '''- "klopt niet": the results show it is false (a fact-check, or a reliable outlet saying otherwise);
- "misleidend": the results show it is misleading: partly true, something real shown in a false context, or leaving out what changes its meaning;''')
SCHEMA_V2 = {**SCHEMA, "properties": {**SCHEMA["properties"],
                                      "oordeel": {"type": "string", "enum": ["klopt", "klopt niet", "misleidend", "onzeker"]}}}
# v3 (#32.12): vier punten uit de fouten van §181, en een veld voor een bewering over een beeld.
VRAAG_V3 = VRAAG_V2.replace(
    '''In fresh news, numbers that differ somewhat between sources (deaths, injured) are not a contradiction.
Give the numbers of the results that confirm the main claim and of those that contradict it, and one short sentence in Dutch.''',
    '''In fresh news, numbers that differ somewhat between sources (deaths, injured) are not a contradiction.
Four more rules:
- If the main claim is about what a photo or video shows ("Video shows...", "Photo of...", "Visuals of..."), reports that the event happened do not confirm this image: an old or unrelated image is often shared with a real event. Say "klopt" only if a result is about this image itself.
- A different cause, perpetrator, place, or a clearly different number in the main claim is not a small difference: if the results show the event happened but differently on one of these, say "misleidend", or "klopt niet" if the core is wrong. A reason the message gives ("because...", "after...", "due to...") is part of the main claim: say "klopt" only if the results give that same reason.
- If the message is itself a fact-check or a debunk, judge the message: it is "klopt" when the results confirm that the claim it debunks is false.
- The date says when the message circulated. A true old article is not misleading because it is old; call it "misleidend" for its age only if the message presents old news as new.
Give the numbers of the results that confirm the main claim and of those that contradict it, one short sentence in Dutch, and over_beeld: true if the main claim is about what a specific photo or video shows, otherwise false.''')
SCHEMA_V3 = {**SCHEMA_V2, "required": [*SCHEMA_V2["required"], "over_beeld"],
             "properties": {**SCHEMA_V2["properties"], "over_beeld": {"type": "boolean"}}}
# v4 (#32.13): het antwoord in twee lagen: het onderliggende feit dat de resultaten bevestigen, en hoe het echt zit.
VRAAG_V4 = VRAAG_V3.replace(
    '''Give the numbers of the results that confirm the main claim and of those that contradict it, one short sentence in Dutch, and over_beeld''',
    '''Many false messages take a real event and add something false: an old or unrelated image, another cause, a false frame. So also give two layers:
- feit: the underlying fact the results confirm, in one short sentence in the same language as the message (English for an English message). Only what the results themselves say happened (who, what, where, when), leaving out every part of the message they do not confirm. If the main claim is about what a photo or video shows, feit is the event itself without the image: what the text of the results says happened, never what an image is said to show. Leave it empty only if the results confirm nothing. feit_steunt: the numbers of the results that confirm this fact.
- anders: if the results show how it really is where the message differs (where the image really comes from, the real cause, the real number), say so in one short sentence in the same language as the message, and put those results in the contradicting numbers; otherwise leave it empty.
Give the numbers of the results that confirm the main claim and of those that contradict it, one short sentence in Dutch, and over_beeld''')
SCHEMA_V4 = {**SCHEMA_V3, "required": [*SCHEMA_V3["required"], "feit", "feit_steunt", "anders"],
             "properties": {**SCHEMA_V3["properties"], "feit": {"type": "string"},
                            "feit_steunt": {"type": "array", "items": {"type": "integer"}},
                            "anders": {"type": "string"}}}
# v5 (#32.28): ook de beste 5 checks uit de database, als eigen soort bron met het oordeel van de redactie, en per
# check of die over dezelfde bewering gaat; bij een check waarvan het beeld de screenshot bevestigt, staat dat erbij.
BEELDZIN = "The image in the screenshot matches the viral image in this fact-check."
VRAAG_V5 = VRAAG_V3.replace(
    '''{resultaten}

Decide:''',
    '''{resultaten}

Fact-checks from our database, found by the words of the message (each one checks one specific claim; the rating is the fact-checker's):
{checks}

Decide:''').replace(
    '''- "klopt niet": the results show it is false (a fact-check, or a reliable outlet saying otherwise);''',
    '''- "klopt niet": the results show it is false (a fact-check in the results, a fact-check from our database about this same claim, or a reliable outlet saying otherwise);''').replace(
    '''Four more rules:''', '''Five more rules:''').replace(
    '''call it "misleidend" for its age only if the message presents old news as new.''',
    '''call it "misleidend" for its age only if the message presents old news as new.
- A fact-check from our database counts only if it checks this same claim: the same event, statement or image, not just the same topic or the same person. One that checks this same claim and rates it false or misleading is a contradiction, like a fact-check in the results; one about another claim says nothing about this message.''').replace(
    '''otherwise false.''',
    '''otherwise false; and checks: for each fact-check from our database its number (1 for [D1]) and zelfde: true only if it checks this same claim, otherwise false.''')
SCHEMA_V5 = {**SCHEMA_V3, "required": [*SCHEMA_V3["required"], "checks"],
             "properties": {**SCHEMA_V3["properties"], "checks": {"type": "array", "items": {
                 "type": "object", "additionalProperties": False, "required": ["nr", "zelfde"],
                 "properties": {"nr": {"type": "integer"}, "zelfde": {"type": "boolean"}}}}}}
TEGEN_IN_DATABASE = ("onwaar", "misleidend")  # zoals kring 1 (`berichtcontrole.ONWAAR`)


def _vervang(tekst: str, paren: list[tuple[str, str]]) -> str:
    """Een vraag uit de vorige; een stuk dat er niet in staat, is een fout, geen stille vraag die gelijk blijft."""
    for oud, nieuw in paren:
        if oud not in tekst:
            raise ValueError(f"niet in de vraag: {oud[:60]!r}")
        tekst = tekst.replace(oud, nieuw)
    return tekst


# v6 (#32.31): alle uitkomsten van besluit A en B48: geen bewering, satire (alleen met een bron), klopt grotendeels
# (met het detail), en de vorm: een bericht over een bewering van een ander. *Beeld nodig* zet de code, niet de lezer.
SYSTEEM_V6 = ("You say what a message is and, if it makes a claim, whether that claim is true, using the web search "
              "results you are given. Be decisive and concise.")
VRAAG_V6 = _vervang(VRAAG_V5, [
    ('''Decide:
- "klopt": the results show the main claim of the message is true;''',
     '''Decide what the message is:
- "geen bewering": the message makes no checkable factual claim: a greeting, an opinion or feeling, a joke, an advertisement or offer, a personal or group message, a request, or a question that asks something without claiming it. An opinion with a checkable fact in it is a claim: judge that fact;
- "satire": the message is satire, meant as a joke, and a result or a fact-check from our database says so (a satirical site, or a fact-checker rating it satire); give those numbers as confirming. Without such a source, judge it like any other claim;
- "klopt": the results show the main claim of the message is true;
- "klopt grotendeels": the results confirm the main claim, but exactly one smaller detail is wrong: a date or day, a number, a place or a name that the main claim does not turn on. Something defensible (one source says Tuesday, another Wednesday; a rounded number) is not a wrong detail;'''),
    ('''- If the message is itself a fact-check or a debunk, judge the message: it is "klopt" when the results confirm that the claim it debunks is false.''',
     '''- vorm, how the message presents its main claim: "over een bewering" if it attributes the claim to another person or group and keeps its distance, or refutes, examines or questions it: a news report on what a party says, alleges or accuses others of; a fact-check or debunk; an investigation of allegations; or a question whether the claim is true ("Is it true that ...?"). Then judge that claim itself: a debunked claim the results show to be false is "klopt niet". Otherwise "zelf": the message asserts the claim in its own voice, also when it backs it with an authority or a source ("doctors confirm that ...", "according to a report ...") or passes on a rumour as fact. If in doubt, "zelf".'''),
    ('''zelfde: true only if it checks this same claim, otherwise false.''',
     '''zelfde: true only if it checks this same claim, otherwise false; vorm; and detail: only for "klopt grotendeels" the wrong words exactly as they appear in the message, the right value exactly as the result gives it, and the number of that result (nr); otherwise empty words, an empty value and nr 0.'''),
])
# v7 (#32.32): de zin uit `vorm-v2` terug, zodat een nieuwsbericht over een uitspraak de uitspraak zelf beweert, en wat
# te verdedigen is, is geen vals detail (§207).
VRAAG_V7 = _vervang(VRAAG_V6, [
    ('''Something defensible (one source says Tuesday, another Wednesday; a rounded number) is not a wrong detail;''',
     '''Only if a reliable result states the right value. It is not a wrong detail if it can be defended: one source says Tuesday, another Wednesday; a rounded number; a number, title or status that changed over time; nearly the same thing in other words ("suspended" and "deleted"); or a description that is also true ("business administrator" and "software engineer"). If in doubt, it is not a wrong detail;'''),
    ('''"over een bewering" if it attributes the claim to another person or group and keeps its distance, or refutes, examines or questions it: a news report on what a party says, alleges or accuses others of; a fact-check or debunk; an investigation of allegations; or a question whether the claim is true ("Is it true that ...?").''',
     '''"over een bewering" if it refutes, examines or questions a claim of another person or group, or attributes the claim to them and clearly keeps its distance ("rumours say ...", "unverified posts claim ..."): a fact-check or debunk; an investigation of allegations; or a question whether the claim is true ("Is it true that ...?").'''),
    ('''also when it backs it with an authority or a source ("doctors confirm that ...", "according to a report ...") or passes on a rumour as fact. If in doubt, "zelf".''',
     '''also when it backs it with an authority or a source ("doctors confirm that ...", "according to a report ...", "..., reports X"), passes on a rumour as fact, or casts doubt on something in its own voice. If the claim is that a person said, wrote or did something, and the message states that as fact, the message asserts it: a news report on what someone says or accuses others of ("Putin says ...", "UK accuses Russia of ...") is judged on whether that person really said it. If in doubt, "zelf".'''),
])
# v8 (#32.40, PO 2026-11-04): de lezer zoekt verder zoals een factchecker. Tenzij betrouwbare sites in de resultaten
# het al beslissen, geeft hij tot drie zoekvragen: op de eigen site van wie het bericht noemt,
# naar het echte nieuws, en naar de bron zelf. Daarna leest hij alles nog één keer (`VRAAG_V8_TWEEDE`). Verder gelijk
# aan v7.
SPEURSOORTEN = ("eigen site", "echt nieuws", "bron zelf")
VRAAG_V8 = _vervang(VRAAG_V7, [
    ('''otherwise empty words, an empty value and nr 0.''',
     '''otherwise empty words, an empty value and nr 0.
Finally, verder_zoeken: unless results from reliable websites (band goed or official) already settle the main claim, give the further web searches a fact-checker would do, at most three, each of one kind. Also when the main claim is about what a photo or video shows and no result is about that image itself:
- "eigen site": on the website of the outlet, person or institution the message names or presents as its source (by name or logo), to see whether they really published or said this; give that website's domain in site;
- "echt nieuws": the real event in plain words (who, what, where, when), without the message's own framing, to find what credible news media reported;
- "bron zelf": the report, statistics, law or statement the message relies on; give the domain of its official or institutional website in site if you know it, otherwise leave site empty.
Each search at most 12 words, in the language most likely to find it. Otherwise an empty list.'''),
])
VRAAG_V8_TWEEDE = _vervang(VRAAG_V7, [
    ('''Top results of a web search for this message (with how reliable each website is, from our list of sources):''',
     '''Results of a web search for this message, and of the further searches a fact-checker would do (with how reliable each website is, from our list of sources). A further search on one website that finds nothing only means no matching page was found there; on its own that does not show the message is false:'''),
])
# v9 (#32.41, B57): één lezing. Haiku bedenkt vooraf de zoekvragen (`speurvraag`), alles gaat tegelijk naar de
# zoekdienst, en de lezer leest één keer, met de resultaten per zoekvraag zoals de tweede lezing van v8, en zegt of
# betrouwbare media of een officiële bron het zouden melden als het waar was (`zou_gemeld`, voor *niet bevestigd*).
VRAAG_V9 = _vervang(VRAAG_V8_TWEEDE, [
    ("otherwise empty words, an empty value and nr 0.",
     "otherwise empty words, an empty value and nr 0.\nFinally, zou_gemeld: true if reliable news media or an official "
     "source would surely have reported the main claim if it were true (a notable event, a statement of a public "
     "figure, a decision of a government, company or institution, a scientific or health finding); false for a small, "
     "local, personal or private matter."),
])
SCHEMA_V6 = {**SCHEMA_V5, "required": [*SCHEMA_V5["required"], "vorm", "detail"],
             "properties": {**SCHEMA_V5["properties"],
                            "oordeel": {"type": "string", "enum": ["geen bewering", "satire", "klopt", "klopt grotendeels",
                                                                  "klopt niet", "misleidend", "onzeker"]},
                            "vorm": {"type": "string", "enum": ["zelf", "over een bewering"]},
                            "detail": {"type": "object", "additionalProperties": False,
                                       "required": ["woorden", "juist", "nr"],
                                       "properties": {"woorden": {"type": "string"}, "juist": {"type": "string"},
                                                      "nr": {"type": "integer"}}}}}
SCHEMA_V9 = {**SCHEMA_V6, "required": [*SCHEMA_V6["required"], "zou_gemeld"],
             "properties": {**SCHEMA_V6["properties"], "zou_gemeld": {"type": "boolean"}}}
SCHEMA_V8 = {**SCHEMA_V6, "required": [*SCHEMA_V6["required"], "verder_zoeken"],
             "properties": {**SCHEMA_V6["properties"], "verder_zoeken": {"type": "array", "items": {
                 "type": "object", "additionalProperties": False, "required": ["soort", "vraag", "site"],
                 "properties": {"soort": {"type": "string", "enum": list(SPEURSOORTEN)},
                                "vraag": {"type": "string"}, "site": {"type": "string"}}}}}}
# v12 (#32.49, BENCHMARK §235): de vraag van v9 met een uitleg die helpt: drie tot vijf feitelijke zinnen in plaats
# van één (wie, wat, wanneer, en wat er echt gebeurde), ook bij geen bewering; zonder kleurende woorden
SYSTEEM_V12 = _vervang(SYSTEEM_V6, [("Be decisive and concise.", "Be decisive, and explain factually.")])
VRAAG_V12 = _vervang(VRAAG_V9, [(
    "Give the numbers of the results that confirm the main claim and of those that contradict it, one short sentence in "
    "Dutch, and over_beeld:",
    "Give the numbers of the results that confirm the main claim and of those that contradict it; an explanation (uitleg) "
    "in Dutch of three to five short, factual sentences, for a reader who wants to understand the message: what the "
    "message says or shows; what the results and fact-checks report about it (who, what, when, numbers), naming the "
    "outlets or fact-checkers; if it is false or misleading, what really happened; if it makes no claim, is satire, or is "
    "about a claim of another, whether it is a real headline, article or post, from whom and when, and what it is about. "
    "Use only facts from the results and the fact-checks; no judging words (such as tragic, shocking or clickbait) and no "
    "opinion. Do not mention our database, and leave out results and fact-checks that are about another claim; and "
    "over_beeld:")])

# v13 (#32.51, BENCHMARK §236, B60): de uitleg begint met het oordeel en de kern, nooit met wat het bericht zegt; twee
# korte alinea's; bij een kop zonder bewering eerst van wie de kop is
VRAAG_V13 = _vervang(VRAAG_V12, [(
    "in Dutch of three to five short, factual sentences, for a reader who wants to understand the message: what the "
    "message says or shows; what the results and fact-checks report about it (who, what, when, numbers), naming the "
    "outlets or fact-checkers; if it is false or misleading, what really happened; if it makes no claim, is satire, or is "
    "about a claim of another, whether it is a real headline, article or post, from whom and when, and what it is about.",
    "in Dutch of three to five short, factual sentences, for a reader who wants to understand the message. Begin with the "
    "verdict and the core fact in one sentence, with the date when known (for example \"Dit klopt: op 6 november "
    "benoemde ...\" or \"Dit klopt niet: de video komt uit 2019 en toont ...\"); never begin by restating what the message "
    "says, the reader already sees it. Then, after an empty line, what the results and fact-checks report (who, what, "
    "when, numbers), naming the outlets or fact-checkers, and if it is false or misleading, what really happened. If the "
    "message makes no claim (for example only a headline), is satire, or is about a claim of another, the first sentence "
    "says whose headline, article or post it is and when, and then what it is about.")])

# v15 (#32.56, §240): de vraag van v13, en elke zin met het nummer van zijn bron; wat geen nummer heeft, laat de code weg
VRAAG_V15 = _vervang(VRAAG_V13, [(
    "leave out results and fact-checks that are about another claim; and over_beeld:",
    "leave out results and fact-checks that are about another claim. End every sentence with the number of the result "
    "that states it, in square brackets: [n] for result n, [D1] for the first fact-check from our database; a sentence "
    "may carry several numbers. Name only outlets that appear in the results you cite, and leave out any fact you cannot "
    "give a number for. A sentence that only gives the verdict (\"Dit klopt niet.\") needs no number; and over_beeld:")])
# v16 (#32.56, §241): de vraag van v15, en een datum, getal of naam alleen als de aangewezen bron hem noemt
VRAAG_V16 = _vervang(VRAAG_V15, [(
    "and leave out any fact you cannot give a number for.",
    "and leave out any fact you cannot give a number for. Give a date, number or name only if the result you cite "
    "states it.")])

# v17 (#32.64): de woorden van v16, maar het vaste deel (vanaf "Decide what the message is") gaat vooraan in het
# systeembericht, zodat het tussen vragen bewaard wordt (`cache_control`); hier staat alleen wat per bericht verschilt
_V16_KNIP = VRAAG_V16.index("{checks}") + len("{checks}")
VRAAG_V17_KOP, VRAAG_V17_REGELS = VRAAG_V16[:_V16_KNIP], VRAAG_V16[_V16_KNIP:]

# De vraag aan de lezer per versie, met de regel voor de kleur; v1 is die van de meting in §179. `database`: de lezer
# leest ook de checks uit de database, en draait nooit zonder.
LEZERS = {"lezer-v1": {"systeem": SYSTEEM, "vraag": VRAAG, "schema": SCHEMA, "regel": "streng"},
          "lezer-v2": {"systeem": SYSTEEM, "vraag": VRAAG_V2, "schema": SCHEMA_V2, "regel": "ruim"},
          "lezer-v3": {"systeem": SYSTEEM, "vraag": VRAAG_V3, "schema": SCHEMA_V3, "regel": "ruim"},
          "lezer-v4": {"systeem": SYSTEEM, "vraag": VRAAG_V4, "schema": SCHEMA_V4, "regel": "ruim"},
          "lezer-v5": {"systeem": SYSTEEM, "vraag": VRAAG_V5, "schema": SCHEMA_V5, "regel": "ruim", "database": True},
          "lezer-v6": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V6, "schema": SCHEMA_V6, "regel": "ruim", "database": True},
          "lezer-v7": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V7, "schema": SCHEMA_V6, "regel": "ruim", "database": True,
                       "detail": "streng"},
          "lezer-v8": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V8, "schema": SCHEMA_V8, "regel": "ruim", "database": True,
                       "detail": "streng", "tweede": {"vraag": VRAAG_V8_TWEEDE, "schema": SCHEMA_V6}},
          "lezer-v9": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V9, "schema": SCHEMA_V9, "regel": "ruim", "database": True,
                       "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True},
          # v10 (#32.43): de vraag van v9; *niet bevestigd* niet bij oud nieuws en niet bij een onafhankelijke
          # bevestiging zonder band (§223, §224, `onbevestigd_weg`)
          "lezer-v10": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V9, "schema": SCHEMA_V9, "regel": "ruim",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band")},
          # v11 (#32.46): v10, en een echte kop die woord voor woord op de eigen site van het genoemde medium staat,
          # mag groen worden (§232, `eigen_kop`)
          "lezer-v11": {"systeem": SYSTEEM_V6, "vraag": VRAAG_V9, "schema": SCHEMA_V9, "regel": "ruim",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True},
          # v12 (#32.49): v11 met een uitleg die helpt, meer ruimte voor die uitleg, en ook bij een check uit de database
          # een uitleg (`met_uitleg`; de kleur blijft van de check)
          "lezer-v12": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V12, "schema": SCHEMA_V9, "regel": "ruim",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True, "max_tokens": 1000,
                        "uitleg_database": True},
          # v13 (#32.51): v12, meteen de kern; een echte kop op de eigen site van het genoemde medium klopt (B60,
          # `kleur_van`); en "de database" gaat uit de uitleg (`zonder_database`)
          "lezer-v13": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V13, "schema": SCHEMA_V9, "regel": "ruim",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True, "max_tokens": 1000,
                        "uitleg_database": True, "kop_klopt": True, "zonder_database": True},
          # v14 (#32.56, B61, §238): v13, en één goede bron is genoeg voor groen als de lezer *klopt* zegt, niets het
          # tegenspreekt en de bewering niet over een beeld gaat (`_gedragen` met regel "een")
          "lezer-v14": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V13, "schema": SCHEMA_V9, "regel": "een",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True, "max_tokens": 1000,
                        "uitleg_database": True, "kop_klopt": True, "zonder_database": True},
          # v15 (#32.56, §240): v14, elke zin met het nummer van zijn bron (`met_bronnen` laat de rest weg), en bij B61 telt
          # het bericht zelf niet als de ene goede bron (`zelfde_artikel`)
          "lezer-v15": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V15, "schema": SCHEMA_V9, "regel": "een",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True, "max_tokens": 1000,
                        "uitleg_database": True, "kop_klopt": True, "zonder_database": True, "met_bronnen": True,
                        "eigen_niet": True},
          # v16 (#32.56, §241): v15, en een getal in een zin alleen als de aangewezen bron of het bericht het noemt
          "lezer-v16": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V16, "schema": SCHEMA_V9, "regel": "een",
                        "database": True, "detail": "streng", "vooraf": "speurvraag-v1", "onbevestigd": True,
                        "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True, "max_tokens": 1000,
                        "uitleg_database": True, "kop_klopt": True, "zonder_database": True, "met_bronnen": True,
                        "eigen_niet": True, "getallen": True},
          # v17 (#32.64): v16 met het vaste deel vooraan, bewaard tussen vragen, en geen breuk na een initiaal
          "lezer-v17": {"systeem": SYSTEEM_V12, "vraag": VRAAG_V17_KOP, "regels": VRAAG_V17_REGELS, "schema": SCHEMA_V9,
                        "regel": "een", "database": True, "detail": "streng", "vooraf": "speurvraag-v1",
                        "onbevestigd": True, "uitzonderingen": ("oud jaartal", "zonder band"), "eigen_kop": True,
                        "max_tokens": 1000, "uitleg_database": True, "kop_klopt": True, "zonder_database": True,
                        "met_bronnen": True, "eigen_niet": True, "getallen": True, "initialen": True}}
# v18 (#32.54, PO 2026-11-08: "Mag je ook doorvoeren"): v17 met een eerste zin die bij de uitkomst past (`eerste_zin`);
# dezelfde vraag aan het model, alleen code na het lezen
LEZERS["lezer-v18"] = {**LEZERS["lezer-v17"], "eerste_zin": True}
SPEUR_BIJ = ("onzeker", "beeld nodig")  # alleen dan zoekt de speurstap verder (#32.40)
MAX_SPEURVRAGEN, MAX_SPEURWOORDEN = 3, 12
_DOMEIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def zoekvraag(tekst: str) -> str:
    """De zoekvraag is het bericht zelf: de eerste 50 woorden, hoogstens 400 tekens (de grens van Brave)."""
    return " ".join(tekst.split()[:50])[:400].strip()


@lru_cache(maxsize=1)
def _staat() -> dict:
    from doublecheck import staatsmedia

    return staatsmedia.lees()


EIGEN_DOMEIN = "factiz.org"  # #32.68: Factiz telt nooit als bron voor zichzelf (geen kringloop, ROUTEKAART-V1 §6)


def van_factiz(url: str) -> bool:
    """Is dit een pagina van Factiz zelf, op factiz.org of een subdomein ervan?"""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == EIGEN_DOMEIN or host.endswith("." + EIGEN_DOMEIN)


def resultaten_uit(antwoord: dict, sites: dict, staat: dict | None = None) -> list[dict]:
    """De resultaten van de zoekdienst, genummerd, met per resultaat de site, de soort en de band uit de bronnenlijst,
    of de site een IFCN-ondertekenaar is (`factcheck`), en het label voor staatsmedia (#32.11). Een pagina van Factiz
    zelf valt eruit vóór het nummeren (#32.68): onze eigen pagina's over wat er rondgaat dragen nooit ons oordeel."""
    from doublecheck import staatsmedia

    staat = _staat() if staat is None else staat
    uit = []
    rijen = [r for r in antwoord.get("web", {}).get("results", []) if not van_factiz(r["url"])]
    for i, r in enumerate(rijen[:N_RESULTATEN], 1):
        b = br.beoordeel(r["url"], sites)
        fragment = " ".join([r.get("description") or "", *(r.get("extra_snippets") or [])[:2]])
        uit.append({"nr": i, "url": r["url"], "titel": _TAG.sub("", r.get("title") or ""),
                    "site": b.get("site") or (urlsplit(r["url"]).hostname or "").removeprefix("www."),
                    "soort": b.get("soort"), "band": b.get("band"), "fragment": _TAG.sub("", fragment).strip(),
                    "factcheck": any(br.reden(naam) == "IFCN" for _, naam in b.get("bronnen") or []),
                    "staatsmedia": (staatsmedia.label(r["url"], staat) or {}).get("naam")})
    return uit


def media_soort(data: bytes) -> str:
    """Het soort beeld uit de eerste bytes."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def leesverzoek(tekst: str, resultaten: list[dict], datum: str | None, config, beeld: bytes | None = None,
                checks: list[dict] | None = None, groepen: list[dict] | None = None) -> dict:
    """De vraag aan Sonnet: het bericht en de top 10, met vast JSON-schema; het model zoekt niet zelf. Het beeld gaat
    alleen mee als `[berichtcontrole] beeld` aan staat. `checks`: de checks uit de database, alleen voor een lezer die
    ze leest (v5), en die draait nooit zonder. `groepen`: de verdere zoekvragen van de speurstap (v8, #32.40); dan is
    het de tweede lezing, met de resultaten per zoekvraag en zonder nieuwe zoekvragen."""
    from doublecheck.berichtcontrole import VersieFout
    from doublecheck.machinevraag import _OORDEEL_EN

    c = config.berichtcontrole
    if c.lezer not in LEZERS:
        raise VersieFout(f"lezer {c.lezer!r} bestaat niet in de code")
    if bool(LEZERS[c.lezer].get("database")) != (checks is not None):
        raise VersieFout(f"lezer {c.lezer!r} " + ("leest de checks uit de database; die ontbreken" if checks is None
                                                   else "leest geen checks uit de database"))
    if LEZERS[c.lezer].get("vooraf") and groepen is None:
        groepen = []  # v9 leest altijd per zoekvraag, ook als er geen eigen zoekvraag was
    if groepen is not None and not (LEZERS[c.lezer].get("tweede") or LEZERS[c.lezer].get("vooraf")):
        raise VersieFout(f"lezer {c.lezer!r} kent geen tweede lezing")
    regels = (_speurregels(resultaten, groepen) if groepen is not None else _regels(resultaten)) or "(no results)"
    checkregels = "\n".join(f"[D{i}] {k['redactie']}, {k['datum']}, rated {_OORDEEL_EN.get(k['oordeel'], k['oordeel'])}"
                            f" — {' '.join(str(k['tekst']).split())[:400]}\n    {k['url']}"
                            + (f"\n    {BEELDZIN}" if k.get("beeld") else "")
                            for i, k in enumerate(checks or [], 1)) or "(none)"
    wanneer = f"This message circulated around {datum}." if datum else "The date of this message is unknown."
    lezer = LEZERS[c.lezer]["tweede"] if groepen is not None and "tweede" in LEZERS[c.lezer] else LEZERS[c.lezer]
    vraag = lezer["vraag"].format(bericht=tekst, datum=wanneer, resultaten=regels, checks=checkregels)
    inhoud = vraag
    if beeld is not None and c.beeld:
        inhoud = [{"type": "image", "source": {"type": "base64", "media_type": media_soort(beeld),
                                               "data": base64.b64encode(beeld).decode()}},
                  {"type": "text", "text": vraag}]
    systeem = LEZERS[c.lezer]["systeem"]
    if LEZERS[c.lezer].get("regels"):  # v17: het vaste deel vooraan, bewaard tussen vragen
        systeem = [{"type": "text", "text": systeem + "\n\n" + LEZERS[c.lezer]["regels"].strip(),
                    "cache_control": {"type": "ephemeral"}}]
    return {"model": c.model_id, "max_tokens": LEZERS[c.lezer].get("max_tokens", 600),
            "system": systeem,
            "messages": [{"role": "user", "content": inhoud}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": lezer["schema"]}}}


def _regels(resultaten: list[dict]) -> str:
    return "\n".join(f"[{r['nr']}] {r['site']} ({r['band'] or r['soort'] or 'unknown'}) — {r['titel']}\n    "
                     f"{r['fragment'][:400]}" for r in resultaten)


def _speurregels(resultaten: list[dict], groepen: list[dict]) -> str:
    """De resultaten per zoekvraag: eerst die van het bericht zelf, dan per verdere zoekvraag de nieuwe resultaten,
    welke eerdere ze ook vond, of dat ze niets vond."""
    stukken = ["Search 1, the message itself:\n" + (_regels([r for r in resultaten if not r.get("via")])
                                                     or "(no results)")]
    for i, g in enumerate(groepen, 1):
        waar = f", on {g['site']}" if g.get("site") and g["soort"] != "echt nieuws" else ""
        nieuw = [r for r in resultaten if r.get("via") == i]
        ook = [n for n in g["nrs"] if n not in {r["nr"] for r in nieuw}]
        stuk = f"Further search {i} ({g['soort']}{waar}): {g['vraag']}\n" + (_regels(nieuw) or "")
        if ook:
            stuk += ("\n" if nieuw else "") + "also found: " + ", ".join(f"[{n}]" for n in ook)
        if not g["nrs"]:
            stuk += "(no results)"
        stukken.append(stuk.rstrip())
    return "\n\n".join(stukken)


def _domein(site: str) -> str:
    """Een adres of domein als kale domeinnaam ("https://www.euronews.com/news" wordt "euronews.com"), of leeg."""
    s = (site or "").strip().lower()
    s = urlsplit(s if "//" in s else f"//{s}").hostname or ""
    s = s.removeprefix("www.")
    return s if _DOMEIN.match(s) else ""


def speurvragen(verder) -> list[dict]:
    """De verdere zoekvragen van de lezer (v8), streng gelezen: een bekende soort, een vraag van hoogstens
    `MAX_SPEURWOORDEN` woorden, bij *eigen site* een echt domein; dubbele vragen één keer, hoogstens drie."""
    uit = []
    for v in verder if isinstance(verder, list) else []:
        if not isinstance(v, dict) or v.get("soort") not in SPEURSOORTEN or not isinstance(v.get("vraag"), str):
            continue
        vraag = " ".join(v["vraag"].split()[:MAX_SPEURWOORDEN])
        site = _domein(v.get("site") if isinstance(v.get("site"), str) else "")
        if not vraag or (v["soort"] == "eigen site" and not site):
            continue
        rij = {"soort": v["soort"], "vraag": vraag, "site": "" if v["soort"] == "echt nieuws" else site}
        if rij not in uit:
            uit.append(rij)
    return uit[:MAX_SPEURVRAGEN]


def brave_vraag(v: dict) -> str:
    """De zoekvraag aan Brave: op de eigen site of de site van de bron met `site:`, het echte nieuws op het hele web."""
    return f"site:{v['site']} {v['vraag']}" if v.get("site") and v["soort"] != "echt nieuws" else v["vraag"]


def _voeg_samen(resultaten: list[dict], verder: list[dict], antwoorden: list[dict | None], sites: dict
                ) -> tuple[list[dict], list[dict]]:
    """De resultaten van de verdere zoekvragen bij die van het bericht. Een nieuwe pagina krijgt het volgende nummer en
    `via` (welke zoekvraag); een pagina die er al was, houdt haar nummer. Per zoekvraag de nummers die ze vond, hoeveel
    resultaten er kwamen, en of ze mislukte (een antwoord dat None is)."""
    alle = list(resultaten)
    per_url = {r["url"]: r["nr"] for r in alle}
    groepen = []
    for i, (v, antwoord) in enumerate(zip(verder, antwoorden), 1):
        gevonden = resultaten_uit(antwoord, sites) if antwoord is not None else []
        nrs = []
        for r in gevonden:
            if r["url"] not in per_url:
                per_url[r["url"]] = len(alle) + 1
                alle.append({**r, "nr": len(alle) + 1, "via": i})
            nrs.append(per_url[r["url"]])
        groepen.append({**v, "nrs": list(dict.fromkeys(nrs)), "gevonden": len(gevonden), "fout": antwoord is None})
    return alle, groepen


def _veilig(zoek, q: str) -> dict | None:
    """Een zoekvraag die mislukt, telt als geen resultaat en laat de controle nooit vallen (#32.41)."""
    try:
        return zoek(q)
    except Exception:  # noqa: BLE001 - elke fout van de zoekdienst
        return None


def speur(verder: list[dict], resultaten: list[dict], zoek, sites: dict) -> tuple[list[dict], list[dict]]:
    """De speurstap (#32.40): de verdere zoekvragen tegelijk bij de zoekdienst, de top 10 met de band uit de
    bronnenlijst, samengevoegd met de resultaten van het bericht (`_voeg_samen`)."""
    from concurrent.futures import ThreadPoolExecutor

    if not verder:
        return list(resultaten), []
    with ThreadPoolExecutor(len(verder)) as pool:
        antwoorden = list(pool.map(lambda v: _veilig(zoek, brave_vraag(v)), verder))
    return _voeg_samen(resultaten, verder, antwoorden, sites)


def zoek_tegelijk(bericht: str, verder: list[dict], zoek, sites: dict) -> tuple[list[dict], list[dict]]:
    """Het bericht zelf en de zoekvragen vooraf tegelijk bij de zoekdienst (v9); de resultaten van het bericht eerst."""
    from concurrent.futures import ThreadPoolExecutor

    vragen = [zoekvraag(bericht)] + [brave_vraag(v) for v in verder]
    with ThreadPoolExecutor(len(vragen)) as pool:
        antwoorden = list(pool.map(lambda q: _veilig(zoek, q), vragen))
    eerste = resultaten_uit(antwoorden[0], sites) if antwoorden[0] is not None else []
    return _voeg_samen(eerste, verder, antwoorden[1:], sites)


def lees_oordeel(tekst: str) -> dict:
    """Het antwoord van Sonnet, streng gelezen; wat niet klopt, is *onzeker*. `over_beeld` (v3) ontbreekt bij v1 en
    v2 en is dan nee; een veld dat geen ja of nee zegt, telt als ja (twijfel versoepelt nooit). Het feit en wat er
    echt gebeurde (v4) zijn leeg als ze ontbreken of geen tekst zijn: dan toont de pagina ze niet. De vorm (v6) is
    alleen *over een bewering* bij precies die woorden, anders *zelf* (bij twijfel zelf, zoals `vorm-v2`); het detail
    alleen met twee zinnen en een echt nummer, anders leeg."""
    try:
        d = json.loads(tekst)
    except json.JSONDecodeError:
        d = {}
    leeg = {"woorden": "", "juist": "", "nr": 0}
    if not isinstance(d, dict) or d.get("oordeel") not in OORDELEN:
        return {"oordeel": "onzeker", "steunt": [], "spreekt_tegen": [], "uitleg": "", "over_beeld": False,
                "feit": "", "feit_steunt": [], "anders": "", "zelfde": [], "vorm": "zelf", "detail": leeg,
                "verder": [], "zou_gemeld": False}
    nummers = lambda k: [n for n in d.get(k) or [] if isinstance(n, int)]  # noqa: E731
    zin = lambda k: d[k].strip() if isinstance(d.get(k), str) else ""  # noqa: E731
    # v5: alleen een check met een echt nummer en een gewoon ja gaat over dezelfde bewering
    zelfde = [c["nr"] for c in (d["checks"] if isinstance(d.get("checks"), list) else [])
              if isinstance(c, dict) and type(c.get("nr")) is int and c.get("zelfde") is True]
    detail = d.get("detail")
    if not (isinstance(detail, dict) and isinstance(detail.get("woorden"), str) and isinstance(detail.get("juist"), str)
            and type(detail.get("nr")) is int):
        detail = leeg
    return {"oordeel": d["oordeel"], "steunt": nummers("steunt"), "spreekt_tegen": nummers("spreekt_tegen"),
            "uitleg": d.get("uitleg") if isinstance(d.get("uitleg"), str) else "",
            "over_beeld": "over_beeld" in d and d["over_beeld"] is not False,
            "feit": zin("feit"), "feit_steunt": nummers("feit_steunt"), "anders": zin("anders"),
            "zelfde": list(dict.fromkeys(zelfde)),
            "vorm": "over een bewering" if d.get("vorm") == "over een bewering" else "zelf",
            "detail": {"woorden": detail["woorden"].strip(), "juist": detail["juist"].strip(), "nr": detail["nr"]},
            "verder": speurvragen(d.get("verder_zoeken")), "zou_gemeld": d.get("zou_gemeld") is True}


def _goed(r: dict) -> bool:
    return r.get("band") == "goed" or r.get("soort") == "officieel"


def gekozen_checks(antwoord: dict, checks: list[dict] | None) -> list[dict]:
    """De checks uit de database die de lezer bij dezelfde bewering zette (v5); een nummer dat niet bestaat, telt niet."""
    return [checks[n - 1] for n in antwoord.get("zelfde", []) if checks and 1 <= n <= len(checks)]


def kleur_van(antwoord: dict, resultaten: list[dict], regel: str = "streng", beeld_gezien: bool = False,
              checks: list[dict] | None = None, bericht: str = "", kopregel: bool = False,
              kop_klopt: bool = False, eigen_niet: bool = False) -> str | None:
    """De bronnenlijst beslist.
    - Rood (*klopt niet*) of oranje (*misleidend*) met minstens één goede tegenspraak; een factcheck van een
      IFCN-ondertekenaar telt daarbij ook bij een lagere band (#32.10b), en een check uit de database die de lezer bij
      dezelfde bewering zet en die onwaar of misleidend zegt, zoals in kring 1 (#32.28).
    - Groen (*klopt*) zonder goede tegenspraak en met twee verschillende goede uitgevers; met `regel="ruim"`
      (#32.11) ook met één goede plus één andere onafhankelijke uitgever: niet laag, geen platform, geen staatsmedia.
      Een bewering over wat een beeld toont, wordt zonder het beeld nooit groen (#31.15, #32.12). Een check uit de
      database maakt nooit groen.
    - Geen bewering, satire, klopt grotendeels en een bericht over een bewering van een ander: nooit een kleur (v6).
    - Met `kopregel` (v11, §232) ook groen bij een echte kop die woord voor woord op de eigen, goede site van het
      genoemde medium staat (`eigen_kop`), als niets het tegenspreekt.
    - Met `kop_klopt` (v13, B60) ook groen bij *geen bewering* als het bericht een echte kop is (`echte_kop_klopt`).
    - Anders geen kleur."""
    if kop_klopt and echte_kop_klopt(antwoord, bericht, resultaten):
        return "groen"
    if antwoord["oordeel"] in ZONDER_KLEUR or antwoord.get("vorm") == "over een bewering":
        return None
    per_nr = {r["nr"]: r for r in resultaten}
    voor = [per_nr[n] for n in antwoord["steunt"] if n in per_nr]
    tegen = [per_nr[n] for n in antwoord["spreekt_tegen"]
             if n in per_nr and (_goed(per_nr[n]) or per_nr[n].get("factcheck"))]
    tegen += [k for k in gekozen_checks(antwoord, checks) if k["oordeel"] in TEGEN_IN_DATABASE]
    if tegen and antwoord["oordeel"] in ("klopt niet", "misleidend"):
        return "rood" if antwoord["oordeel"] == "klopt niet" else "oranje"
    if antwoord["oordeel"] != "klopt" or tegen or (antwoord.get("over_beeld") and not beeld_gezien):
        return None
    if regel == "een" and antwoord.get("over_beeld"):  # B61 geldt niet voor een bewering over een beeld
        regel = "ruim"
    if regel == "een" and eigen_niet:  # v15: het bericht zelf is niet de ene goede bron
        gedragen = _gedragen(voor, "ruim") or _gedragen([r for r in voor if not zelfde_artikel(bericht, r)], "een")
    else:
        gedragen = _gedragen(voor, regel)
    if gedragen or (kopregel and not antwoord["spreekt_tegen"] and eigen_kop(bericht, voor)):
        return "groen"
    return None


# Media met hun eigen sites, voor een kop die het bericht onder hun naam brengt (v11, #32.46, §232). Een medium telt
# alleen met band *goed* in de bronnenlijst; de lijst zegt alleen welke site bij welke naam hoort.
MEDIA = {
    "BBC News": ("bbc.com", "bbc.co.uk"), "BBC": ("bbc.com", "bbc.co.uk"), "The Guardian": ("theguardian.com",),
    "NPR": ("npr.org",), "DW": ("dw.com",), "Deutsche Welle": ("dw.com",), "France 24": ("france24.com",),
    "Al Jazeera": ("aljazeera.com",), "Euronews": ("euronews.com",), "Sky News": ("news.sky.com", "sky.com"),
    "The Independent": ("independent.co.uk",), "Daily Mail": ("dailymail.co.uk",), "The Sun": ("thesun.co.uk",),
    "Daily Mirror": ("mirror.co.uk",), "Daily Express": ("express.co.uk",), "GB News": ("gbnews.com",),
    "The Times": ("thetimes.co.uk", "thetimes.com"), "The Telegraph": ("telegraph.co.uk",), "CNN": ("cnn.com",),
    "NBC News": ("nbcnews.com",), "CBS News": ("cbsnews.com",), "ABC News": ("abcnews.go.com",),
    "Fox News": ("foxnews.com",), "New York Post": ("nypost.com",), "The New York Times": ("nytimes.com",),
    "The Washington Post": ("washingtonpost.com",), "The Wall Street Journal": ("wsj.com",), "USA Today": ("usatoday.com",),
    "The Hill": ("thehill.com",), "Newsweek": ("newsweek.com",), "HuffPost": ("huffpost.com",), "Breitbart": ("breitbart.com",),
    "Newsmax": ("newsmax.com",), "Politico": ("politico.com",), "Politico Europe": ("politico.eu",),
    "Associated Press": ("apnews.com",), "AP": ("apnews.com",), "Reuters": ("reuters.com",), "AFP": ("afp.com",),
    "Bloomberg": ("bloomberg.com",), "FT": ("ft.com",), "Financial Times": ("ft.com",), "The Economist": ("economist.com",),
    "TVP World": ("tvpworld.com",), "The Jerusalem Report": ("jpost.com",), "La Croix": ("la-croix.com",),
    "Libération": ("liberation.fr",), "Le Monde": ("lemonde.fr",), "El País": ("elpais.com",), "El Mundo": ("elmundo.es",),
    "La Vanguardia": ("lavanguardia.com",), "20minutos": ("20minutos.es",), "RTVE": ("rtve.es",),
    "La Voz de Galicia": ("lavozdegalicia.es",), "Público": ("publico.pt",), "RTP": ("rtp.pt",),
    "Observador": ("observador.pt",), "Folha": ("folha.uol.com.br",), "g1": ("g1.globo.com",),
    "Tagesschau": ("tagesschau.de",), "Der Spiegel": ("spiegel.de",), "Die Zeit": ("zeit.de",), "FAZ": ("faz.net",),
    "NOS": ("nos.nl",), "NRC": ("nrc.nl",), "de Volkskrant": ("volkskrant.nl",), "VRT NWS": ("vrt.be",), "HLN": ("hln.be",),
    "franceinfo": ("franceinfo.fr", "francetvinfo.fr"), "Le Soir": ("lesoir.be",), "La Libre": ("lalibre.be",),
}
MIN_KOPWOORDEN = 5


def kop_gewoon(tekst: str) -> str:
    """Kleine letters, zonder leestekens en symbolen (Unicode-categorie P en S), zodat een rechte en een gekrulde
    apostrof gelijk zijn; letters en combinerende tekens blijven, in elk schrift."""
    import unicodedata

    return " ".join("".join(" " if unicodedata.category(t)[0] in "PS" else t for t in tekst.lower()).split())


def kop_treffers(bericht: str, voor: list[dict]) -> list[dict]:
    """De bronnen die een echte kop op de eigen site laten zien (v11, §232): de eerste regel van het bericht is een
    medium uit `MEDIA` (ongeacht hoofdletters en leestekens), de rest een kop van minstens `MIN_KOPWOORDEN` woorden, en de
    bron staat op de site van dát medium, met band *goed*, met een titel die de kop woord voor woord bevat."""
    merk, _, kop = bericht.partition("\n")
    sites = {kop_gewoon(m): v for m, v in MEDIA.items()}.get(kop_gewoon(merk))
    kop = kop_gewoon(kop)
    if not sites or len(kop.split()) < MIN_KOPWOORDEN:
        return []
    return [b for b in voor if b.get("band") == "goed"
            and any((b.get("site") or "") == s or (b.get("site") or "").endswith("." + s) for s in sites)
            and kop in kop_gewoon(b.get("titel") or "")]


def eigen_kop(bericht: str, voor: list[dict]) -> bool:
    """Een echte kop op de eigen site (`kop_treffers`). Of de lezer *klopt* zei en niets het tegenspreekt, beslist
    `kleur_van`."""
    return bool(kop_treffers(bericht, voor))


def echte_kop_klopt(antwoord: dict, bericht: str, resultaten: list[dict]) -> bool:
    """B60: een bericht zonder bewering dat een echte kop is, op de eigen site van het genoemde medium (`kop_treffers`
    in alle resultaten, want de lezer noemt bij *geen bewering* geen bevestiging), zonder tegenspraak en niet over een
    bewering van een ander."""
    return (antwoord["oordeel"] == "geen bewering" and antwoord.get("vorm") != "over een bewering"
            and not antwoord["spreekt_tegen"] and eigen_kop(bericht, resultaten))


def _gedragen(voor: list[dict], regel: str) -> bool:
    """Twee verschillende goede uitgevers; met de ruime regel ook één goede plus één andere onafhankelijke; met de regel
    "een" (B61, v14) is één goede genoeg."""
    goed = {eigenaar(r["site"]) for r in voor if _goed(r)}
    if regel == "een":
        return bool(goed)
    anders = {eigenaar(r["site"]) for r in voor if not _goed(r) and r.get("band") != "laag"
              and r.get("soort") != "platform" and not r.get("staatsmedia")} - goed
    return len(goed) >= 2 or bool(regel == "ruim" and goed and anders)


def feit_van(antwoord: dict, resultaten: list[dict], kleur: str | None, regel: str = "ruim") -> str | None:
    """Wat klopt (#32.13): het onderliggende feit, alleen als de bewering niet groen is en de bronnen van het feit
    dezelfde regel halen als groen. Bij *klopt* alleen voor een bewering over een beeld: dan is het feit de
    gebeurtenis zonder het beeld; anders is het de bewering zelf."""
    if not antwoord.get("feit") or kleur == "groen" or (antwoord["oordeel"] == "klopt"
                                                         and not antwoord.get("over_beeld")):
        return None
    per_nr = {r["nr"]: r for r in resultaten}
    voor = [per_nr[n] for n in antwoord.get("feit_steunt", []) if n in per_nr]
    return antwoord["feit"] if _gedragen(voor, regel) else None


def _onafhankelijk(r: dict) -> bool:
    return _goed(r) or (r.get("band") != "laag" and r.get("soort") != "platform" and not r.get("staatsmedia"))


def verbetering(antwoord: dict, bericht: str, resultaten: list[dict], streng: bool = False) -> dict | None:
    """Het foute detail bij *klopt grotendeels* (B48, v6): alleen als de foute woorden letterlijk in het bericht
    staan, de juiste waarde letterlijk in de titel of het fragment van het genoemde resultaat, de foute woorden daar
    niet, en dat resultaat geen lage band, geen platform en geen staatsmedia is (zoals `detail-v3`). `streng` (v7,
    #32.32): het resultaat moet betrouwbaar zijn (goed of officieel), en de foute woorden staan in geen resultaat dat de
    lezer als bevestigend noemt; dan zegt een bron het ook zo. Anders None."""
    from doublecheck.berichtcontrole import _gewoon, plaats

    d = antwoord.get("detail") or {}
    per_nr = {x["nr"]: x for x in resultaten}
    r = per_nr.get(d.get("nr"))
    woorden, juist = _gewoon(d.get("woorden", "")), _gewoon(d.get("juist", ""))
    if r is None or not woorden or not juist or woorden == juist or not (_goed(r) if streng else _onafhankelijk(r)):
        return None
    passage = _gewoon(f"{r['titel']} {r['fragment']}")
    p = plaats(bericht, d["woorden"])
    if juist not in passage or woorden in passage or p is None:
        return None
    if streng and any(woorden in _gewoon(f"{per_nr[n]['titel']} {per_nr[n]['fragment']}")
                      for n in antwoord.get("steunt", []) if n in per_nr):
        return None
    return {"woorden": bericht[p[0]:p[1]], "juist": d["juist"], "nr": r["nr"], "url": r["url"], "site": r["site"],
            "begin": p[0], "eind": p[1]}


def _satire_bron(antwoord: dict, resultaten: list[dict], checks: list[dict] | None) -> bool:
    """Satire alleen met een bron die het zegt: een genoemd resultaat, of een check bij dezelfde bewering die satire
    zegt."""
    nummers = {r["nr"] for r in resultaten}
    return (any(n in nummers for n in antwoord["steunt"])
            or any(k["oordeel"] == "satire" for k in gekozen_checks(antwoord, checks)))


def uitkomst_van(antwoord: dict, kleur: str | None, correctie: dict | None, beeld_gezien: bool, satire: bool) -> str:
    """Wat Factiz zegt, een van de negen van besluit A en B48 (#32.31). Een bericht over een bewering van een ander
    eerst, dan geen bewering en satire (alleen met een bron), dan de kleur. Zonder kleur: *beeld nodig* bij een
    bewering over een beeld zonder het beeld, *klopt grotendeels* alleen met een geldige verbetering, en anders
    *onzeker*; het oordeel van de lezer staat ernaast."""
    if antwoord.get("vorm") == "over een bewering":
        return "over een bewering"
    if antwoord["oordeel"] == "geen bewering":  # groen alleen bij een echte kop (B60, v13)
        return "klopt" if kleur == "groen" else "geen bewering"
    if antwoord["oordeel"] == "satire":
        return "satire" if satire else "onzeker"
    if kleur in _UIT_KLEUR:
        return _UIT_KLEUR[kleur]
    if antwoord.get("over_beeld") and not beeld_gezien:
        return "beeld nodig"
    if antwoord["oordeel"] == "klopt grotendeels" and correctie is not None:
        return "klopt grotendeels"
    return "onzeker"


def zelf_gezocht(groepen: list[dict]) -> bool:
    """Minstens één eigen zoekvraag gaf een antwoord; een zoekvraag die mislukte, is geen zoekvraag (#32.41)."""
    return any(not g.get("fout") for g in groepen)


def onbevestigd(antwoord: dict, resultaten: list[dict], uitkomst: str, gezocht: bool,
                checks: list[dict] | None = None) -> bool:
    """*Niet bevestigd* (B57): het zou *onzeker* of *beeld nodig* zijn, betrouwbare media of een officiële bron zouden
    het melden als het waar was (`zou_gemeld`), de controle zocht zelf verder (`zelf_gezocht`), geen goede of
    officiële site bevestigt het, en geen check uit de database gaat over dezelfde bewering: dan meldt een redactie het
    wel. Twijfel versoepelt nooit: zonder een gewoon ja op `zou_gemeld` niet."""
    per_nr = {r["nr"]: r for r in resultaten}
    return (uitkomst in ("onzeker", "beeld nodig") and antwoord.get("zou_gemeld") is True and gezocht
            and not any(_goed(per_nr[n]) for n in antwoord["steunt"] if n in per_nr)
            and not gekozen_checks(antwoord, checks))


# Een jaartal in Arabische cijfers, 1990 tot en met 2099; een getal van meer cijfers is geen jaartal (§223)
JAARTAL = re.compile(r"(?<![0-9])(199[0-9]|20[0-9]{2})(?![0-9])")
OUD_JAREN = 3  # oud nieuws: het nieuwste jaartal ligt minstens zo veel kalenderjaren terug (in 2026: 2023 of eerder)


def oud_jaartal(tekst: str, jaar: int | None) -> bool:
    """Oud nieuws volgens wat Factiz zelf ziet (v10, regel a2 van §223): het nieuwste jaartal in het bericht ligt
    minstens `OUD_JAREN` kalenderjaren voor `jaar`, het jaar van de controle. Twijfel versoepelt nooit: zonder jaartal,
    zonder `jaar`, of met een jaartal in een ander schrift is het niet oud, en een jaartal in de toekomst (een doel voor
    2030) telt mee als nieuwste."""
    jaartallen = [int(j) for j in JAARTAL.findall(tekst)]
    return jaar is not None and bool(jaartallen) and max(jaartallen) <= jaar - OUD_JAREN


def bevestigd_zonder_band(bronnen: list[dict]) -> bool:
    """Een onafhankelijke bron die het bericht bevestigt en geen band heeft (v10, regel b van §223): geen platform, geen
    staatsmedia, geen lage of wisselende band, en niet ook tegensprekend (`bronnen_van` geeft dan *spreekt tegen*)."""
    return any(b.get("rol") == "bevestigt" and b.get("band") is None and b.get("soort") != "platform"
               and not b.get("staatsmedia") for b in bronnen)


def onbevestigd_weg(bericht: str, bronnen: list[dict], jaar: int | None, regels: tuple[str, ...]) -> str | None:
    """Welke regel van de lezer *niet bevestigd* weer *onzeker* maakt, of None (v10, #32.43)."""
    if "oud jaartal" in regels and oud_jaartal(bericht, jaar):
        return "oud jaartal"
    if "zonder band" in regels and bevestigd_zonder_band(bronnen):
        return "zonder band"
    return None


def na_lezen(antwoord: dict, bericht: str, resultaten: list[dict], checks: list[dict] | None, lezer: str,
             beeld_gezien: bool, gezocht: bool = False, jaar: int | None = None) -> dict:
    """Alles na het antwoord van de lezer, op één plek voor `controleer` en de metingen (#32.31): de kleur, de
    uitkomst, de verbetering, bij een bericht over een bewering de kleur van die bewering zelf, de bronnen, en het
    feit en wat er echt gebeurde (v4). `jaar`: het jaar van de controle, voor oud nieuws (v10); `onbevestigd_weg`
    zegt welke regel *niet bevestigd* weer *onzeker* maakte, zodat een meting ook telt wat v9 gezegd zou hebben."""
    regel = LEZERS[lezer]["regel"]
    kopregel = bool(LEZERS[lezer].get("eigen_kop"))
    kop_klopt = bool(LEZERS[lezer].get("kop_klopt"))
    kleur = kleur_van(antwoord, resultaten, regel, beeld_gezien, checks, bericht, kopregel, kop_klopt,
                      bool(LEZERS[lezer].get("eigen_niet")))
    correctie = (verbetering(antwoord, bericht, resultaten, LEZERS[lezer].get("detail") == "streng")
                 if antwoord["oordeel"] == "klopt grotendeels" else None)
    over = antwoord.get("vorm") == "over een bewering"
    uitkomst = uitkomst_van(antwoord, kleur, correctie, beeld_gezien, _satire_bron(antwoord, resultaten, checks))
    bronnen, weg = bronnen_van(antwoord, resultaten, checks), None
    if kop_klopt and kleur == "groen" and antwoord["oordeel"] == "geen bewering":  # B60: de pagina van de kop
        al = {b.get("url") for b in bronnen}
        bronnen += [{**{k: r.get(k) for k in ("url", "site", "titel", "band", "soort", "staatsmedia")},
                     "rol": "bevestigt de kop"} for r in kop_treffers(bericht, resultaten) if r.get("url") not in al]
    uitleg = antwoord["uitleg"] or None
    if uitleg and LEZERS[lezer].get("zonder_database"):
        uitleg = zonder_database(uitleg) or None
    if uitleg and LEZERS[lezer].get("met_bronnen"):  # v15: alleen zinnen met het nummer van hun bron
        uitleg = met_bronnen(uitleg, resultaten, checks, bericht, bool(LEZERS[lezer].get("getallen")),
                             bool(LEZERS[lezer].get("initialen"))) or None
    if LEZERS[lezer].get("onbevestigd") and onbevestigd(antwoord, resultaten, uitkomst, gezocht, checks):
        weg = onbevestigd_weg(bericht, bronnen, jaar, LEZERS[lezer].get("uitzonderingen", ()))
        uitkomst = "niet bevestigd" if weg is None else uitkomst
    if uitleg and LEZERS[lezer].get("eerste_zin"):  # v18: de eerste zin past bij de uitkomst
        uitleg = eerste_zin(uitleg, uitkomst)
    return {"oordeel": antwoord["oordeel"], "kleur": kleur, "uitkomst": uitkomst,
            "vorm": antwoord.get("vorm", "zelf"), "correctie": correctie,
            "kleur_bewering": kleur_van({**antwoord, "vorm": "zelf"}, resultaten, regel, beeld_gezien, checks, bericht,
                                        kopregel) if over else None,
            "uitleg": uitleg, "bronnen": bronnen,
            "over_beeld": antwoord["over_beeld"], "feit": feit_van(antwoord, resultaten, kleur, regel),
            "anders": anders_van(antwoord, kleur), "onbevestigd_weg": weg}


_EINDE_ZIN = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÝÄÖÜ0-9\"'„“(])")
_NUMMER = re.compile(r"\[(D?\d+)\]")
_GETAL = re.compile(r"\d+(?:[.,]\d+)*")
# v17: niet breken na een initiaal ("Joseph M. Juran"), wel na een woord of getal (§243)
_EINDE_ZIN_INIT = re.compile(r"(?<=[.!?])(?<!\b[A-ZÀ-Ý]\.)\s+(?=[A-ZÀ-ÝÄÖÜ0-9\"'„“(])")
_NA_DE_PUNT = re.compile(r"\s*([.!?])((?:\s*\[D?\d+\])+)")  # "... oud. [4]" wordt "... oud [4]." (§241)
_ALLEEN_OORDEEL = re.compile(r"^(?:dit|het bericht|het)\s+(?:klopt(?: niet| grotendeels)?|is (?:misleidend|satire|geen "
                             r"bewering|niet bevestigd))\s*[.!]?$", re.IGNORECASE)


# v18: een eerste zin met een oordeel dat de regels niet geven, wordt wat de regels wel zeggen (§247)
_OORDEEL_VOORAAN = re.compile(r"^\s*Dit (klopt grotendeels|klopt niet|klopt|is misleidend)\b[ \t]*([:.!,;]?)[ \t]*")
_ZONDER_KLEUR = {"klopt": "Mogelijk klopt dit, maar we vonden niet genoeg betrouwbare bronnen om het te bevestigen",
                 "klopt grotendeels": "Mogelijk klopt dit, maar we vonden niet genoeg betrouwbare bronnen om het te "
                                      "bevestigen",
                 "klopt niet": "Mogelijk klopt dit niet, maar we vonden geen betrouwbare bron die het tegenspreekt",
                 "is misleidend": "Mogelijk is dit misleidend, maar we vonden geen betrouwbare bron die het tegenspreekt"}


def eerste_zin(uitleg: str, uitkomst: str) -> str:
    """Begint de uitleg met een oordeel ("Dit klopt", "Dit klopt niet", "Dit is misleidend") terwijl de uitkomst
    *onzeker* of *niet bevestigd* is, dan zegt de eerste zin wat de regels wel zeggen; de rest van de zin blijft."""
    m = _OORDEEL_VOORAAN.match(uitleg or "")
    if m is None or uitkomst not in ("onzeker", "niet bevestigd"):
        return uitleg
    rest = uitleg[m.end():]
    if m.group(2) in (":", ",", ";") and rest.strip() and not rest.startswith("\n"):
        return f"{_ZONDER_KLEUR[m.group(1)]}: {rest}"
    return f"{_ZONDER_KLEUR[m.group(1)]}.{'' if rest.startswith(chr(10)) or not rest else ' '}{rest}"


def _nummer_voor_de_punt(alinea: str) -> str:
    return _NA_DE_PUNT.sub(lambda m: " " + " ".join(m.group(2).split()).replace("] [", "][") + m.group(1), alinea)


def zinnen(tekst: str) -> list[str]:
    """De zinnen van een uitleg, over de alinea's heen; een punt in een getal of een afkorting met een kleine letter erna
    breekt niet, en een bronnummer ná de punt hoort bij de zin ervoor."""
    uit = []
    for alinea in (tekst or "").split("\n\n"):
        uit += [z.strip() for z in _EINDE_ZIN.split(_nummer_voor_de_punt(alinea.strip())) if z.strip()]
    return uit


def _genoemd_klopt(zin: str, nummers: list[str], resultaten: list[dict], checks: list[dict] | None) -> bool:
    """Elk medium dat de zin noemt (`MEDIA`), staat in zijn eigen bronnen: als site, in de titel of het fragment (een
    bericht van Reuters via Yahoo), of als redactie van een check."""
    per_nr = {str(r["nr"]): r for r in resultaten}
    eigen = [per_nr[n] for n in nummers if n in per_nr]
    redacties = {str(checks[int(n[1:]) - 1].get("redactie") or "").lower() for n in nummers
                 if n.startswith("D") and checks and 1 <= int(n[1:]) <= len(checks)}
    tekst = " ".join(f"{r.get('titel') or ''} {r.get('fragment') or ''}" for r in eigen).lower()
    for naam, sites in MEDIA.items():
        if not re.search(rf"(?<!\w){re.escape(naam)}(?!\w)", zin):
            continue
        if not (any((r.get("site") or "") == s or (r.get("site") or "").endswith("." + s) for r in eigen for s in sites)
                or naam.lower() in tekst or naam.lower() in redacties):
            return False
    return True


def _getallen(tekst: str) -> set[str]:
    """De getallen in een tekst, zonder punt, komma en voorloopnullen: 1.776, 1,776 en 1776 zijn hetzelfde, 3,5 en 3.5
    ook, en de 05 van 2026-01-05 is 5."""
    return {re.sub(r"[.,]", "", g).lstrip("0") or "0" for g in _GETAL.findall(tekst or "")}


def _getallen_kloppen(zin: str, nummers: list[str], resultaten: list[dict], checks: list[dict] | None,
                      bericht: str = "") -> bool:
    """Elk getal in de zin (een datum, jaartal, bedrag of percentage) staat in wat de lezer zag van de bronnen die de zin
    aanwijst (site, titel, fragment tot 400 tekens; bij een check redactie, datum en bewering), of in het bericht zelf
    (v16, §241)."""
    eigen = _getallen(_NUMMER.sub(" ", zin))
    if not eigen:
        return True
    per_nr = {str(r["nr"]): r for r in resultaten}
    gezien = [f"{per_nr[n].get('site') or ''} {per_nr[n].get('titel') or ''} {(per_nr[n].get('fragment') or '')[:400]}"
              for n in nummers if n in per_nr]
    gezien += [f"{k.get('redactie') or ''} {k.get('datum') or ''} {' '.join(str(k.get('tekst') or '').split())[:400]}"
               for n in nummers if n.startswith("D") and checks and 1 <= int(n[1:]) <= len(checks)
               for k in [checks[int(n[1:]) - 1]]]
    return eigen <= _getallen(" ".join(gezien) + " " + (bericht or ""))


def met_bronnen(uitleg: str, resultaten: list[dict], checks: list[dict] | None, bericht: str = "",
                getallen: bool = False, initialen: bool = False) -> str:
    """De uitleg met alleen de zinnen die een geldig nummer van een bron dragen ([n] of [Dk]), en die geen medium noemen
    dat niet in hun bronnen staat; een kaal oordeel ("Dit klopt niet.") mag zonder nummer (v15, §240). Met `getallen`
    ook geen getal dat de aangewezen bronnen en het bericht niet noemen (v16, §241)."""
    geldig = {str(r["nr"]) for r in resultaten} | {f"D{i}" for i in range(1, len(checks or []) + 1)}
    alineas = []
    for alinea in (uitleg or "").split("\n\n"):
        houden = []
        for zin in (_EINDE_ZIN_INIT if initialen else _EINDE_ZIN).split(_nummer_voor_de_punt(alinea.strip())):
            zin = zin.strip()
            nummers = _NUMMER.findall(zin)
            if not zin:
                continue
            if not nummers:
                if _ALLEEN_OORDEEL.match(zin):
                    houden.append(zin)
                continue
            if (all(n in geldig for n in nummers) and _genoemd_klopt(zin, nummers, resultaten, checks)
                    and (not getallen or _getallen_kloppen(zin, nummers, resultaten, checks, bericht))):
                houden.append(zin)
        if houden:
            alineas.append(" ".join(houden))
    return "\n\n".join(alineas)


def _kop_woorden(bericht: str, n: int = 6) -> str:
    regels = [r for r in (bericht or "").split("\n") if r.strip()]
    if len(regels) > 1 and kop_gewoon(regels[0]) in {kop_gewoon(m) for m in MEDIA}:
        regels = regels[1:]
    return " ".join(kop_gewoon(regels[0] if regels else "").split()[:n])


def zelfde_artikel(bericht: str, r: dict) -> bool:
    """Of een resultaat het bericht zelf is: de eerste zes woorden van de kop staan woord voor woord in de titel."""
    kop = _kop_woorden(bericht)
    return len(kop.split()) >= 5 and kop in kop_gewoon(r.get("titel") or "")


_ONZE_DATABASE = re.compile(r"(?i)\b(?:uit|in) (?:de|onze) database\b(?! van)|\bdatabase-?check|\bonze database")


def zonder_database(tekst: str) -> str:
    """De uitleg zonder "de database" (v13): de lezer heeft het soms over de checks uit onze database, wat een lezer
    niets zegt (§236). Een stuk tussen haakjes daarover gaat eruit, een zin daarover ook; een database in het nieuws
    ("een militaire database van het ministerie") blijft. De alinea's blijven."""
    tekst = re.sub(r"\s*\([^()]*\)", lambda m: "" if _ONZE_DATABASE.search(m.group(0)) else m.group(0), tekst)
    alineas = []
    for alinea in tekst.split("\n\n"):
        zinnen = [z for z in re.split(r"(?<=[.!?])\s+", alinea.strip()) if z and not _ONZE_DATABASE.search(z)]
        if zinnen:
            alineas.append(" ".join(zinnen))
    return "\n\n".join(alineas)


def anders_van(antwoord: dict, kleur: str | None) -> str | None:
    """Wat er echt gebeurde (#32.13): alleen bij rood of oranje, dus met een goede tegenspraak of een factcheck."""
    return (antwoord.get("anders") or None) if kleur in ("rood", "oranje") else None


def bronnen_van(antwoord: dict, resultaten: list[dict], checks: list[dict] | None = None) -> list[dict]:
    """Wat het antwoord laat zien: de resultaten die de lezer noemde, met hun band en of ze de bewering bevestigen,
    tegenspreken, of alleen het onderliggende feit bevestigen (#32.13). Een resultaat met twee rollen krijgt de
    laatste: tegenspreken weegt het zwaarst. Daarna de checks uit de database die de lezer bij dezelfde bewering
    zette, in de vorm van kring 1 (v5)."""
    per_nr = {r["nr"]: r for r in resultaten}
    rollen = ([(n, "bevestigt het feit") for n in antwoord.get("feit_steunt", [])]
              + [(n, "bevestigt") for n in antwoord["steunt"]] + [(n, "spreekt tegen") for n in antwoord["spreekt_tegen"]])
    web = [{**{k: per_nr[n].get(k) for k in ("url", "site", "titel", "band", "soort", "staatsmedia")}, "rol": rol}
           for n, rol in dict(rollen).items() if n in per_nr]
    return web + [{"soort": "check van een redactie", "url": k["url"], "redactie": k["redactie"],
                   "oordeel": k["oordeel"], "datum": k["datum"], "titel": None,
                   "rol": "spreekt tegen" if k["oordeel"] in TEGEN_IN_DATABASE else "zelfde bewering"}
                  for k in gekozen_checks(antwoord, checks)]


def brave(q: str, sleutel: str) -> dict:  # pragma: no cover - netwerk
    import urllib.parse
    import urllib.request

    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": q, "count": N_RESULTATEN, "extra_snippets": "true"})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": sleutel})
    return json.load(urllib.request.urlopen(req, timeout=15))


def checks_uit(geheugen: list[dict]) -> list[dict]:
    """De checks voor `lezer-v5` uit de kandidaten van de database (`berichtcontrole.geheugen_met`): per check de
    bewering, de redactie, het oordeel, de datum en het adres, zoals in de meting van #32.28; nooit met de zin over het
    beeld, want het beeld vergelijkt het product nog niet (#32.30)."""
    return [{"claim": k["claim"], "tekst": k["tekst"], "redactie": k["redactie"], "oordeel": k["oordeel"],
             "datum": k["datum"], "url": k["url"], "beeld": False} for k in geheugen]


def uit_kring1(uit: dict, bericht: str, versies: dict) -> dict:
    """Het antwoord van kring 1 in de vorm van de controle: de kleur van de check zet de uitkomst, gratis."""
    return {"route": "database", "oordeel": uit["oordeel"], "kleur": uit["kleur"], "uitleg": None,
            "bronnen": uit["bronnen"], "gelezen": bericht, "kosten": 0.0, "versies": versies, "over_beeld": False,
            "feit": None, "anders": None, "uitkomst": _UIT_KLEUR.get(uit["kleur"], "onzeker"), "vorm": "zelf",
            "correctie": None, "kleur_bewering": None}


EENS_MET_CHECK = {"rood": ("klopt niet", "misleidend"), "oranje": ("klopt niet", "misleidend"),
                  "groen": ("klopt", "klopt grotendeels")}


def zin_van_redactie(bronnen: list[dict]) -> str | None:
    """Wat er zonder lezer bij een check uit de database staat: wie het controleerde en wat die zei."""
    zinnen = [f"Dit is al gecontroleerd: {b['redactie']} noemde het {b.get('oordeel') or 'onwaar'}."
              for b in bronnen if b.get("redactie")]
    return " ".join(zinnen) or None


def met_uitleg(kring1: dict, gelezen: dict | None) -> dict:
    """Een antwoord uit de database (kring 1) met de uitleg van de lezer (v12, #32.49). De kleur, de uitkomst en de
    route blijven van de check; de lezer geeft alleen de uitleg, wat er echt gebeurde en zijn bronnen erbij. Is de lezer
    het niet eens met de check, of was er geen lezing, dan blijft de zin van de redactie: een uitleg die het oordeel
    tegenspreekt, helpt niemand."""
    uit = {**kring1, "uitleg": zin_van_redactie(kring1["bronnen"])}
    if gelezen is None:
        return uit
    uit["kosten"] = kring1["kosten"] + gelezen.get("kosten", 0.0)
    if gelezen["oordeel"] not in EENS_MET_CHECK.get(kring1["kleur"], ()):
        return uit
    al = {b.get("url") for b in kring1["bronnen"]}
    return {**uit, "uitleg": gelezen.get("uitleg") or uit["uitleg"], "anders": gelezen.get("anders"),
            "bronnen": kring1["bronnen"] + [b for b in gelezen["bronnen"] if b.get("url") not in al]}


def controleer(kosten_conn, bericht: str, config, client, zoek, snel, sites: dict, dag: str | None,
               datum: str | None = None, beeld: bytes | None = None, bewaak=None,
               checks: list[dict] | None = None, zoek_checks=None, beeldstap=None, foto_haler=None,
               foto: bool = True, voor_model=None) -> dict:
    """De hele controle. `bericht`: de gemaskeerde tekst; `zoek(q)`: de zoekdienst; `snel(tekst)`: kring 1, het
    antwoord uit de database of None; `dag`: voor de kosten per dag; `datum`: wanneer het bericht rondging;
    `bewaak()`: de daggrens, pas na kring 1, want een antwoord uit de database kost niets; `checks`: de beste checks
    uit de database, voor een lezer die ze leest (v5, #32.28); `zoek_checks(bericht)`: haalt ze pas op als kring 1
    niets gaf en de lezer ze leest (het product, #32.30)."""
    from doublecheck import berichtcontrole as bc

    c = config.berichtcontrole
    versies = {"reader": c.lezer, "search": c.zoeker, "model": c.model_id}
    # §251, nagemeten: kring 1, de checks uit de database en het zwartmaken tegelijk maakte het op twee kernen trager
    # (kring 1 van 0,4 naar 3,6 s, de database van 0,5 naar 3,5 s: hetzelfde taalmodel op de processor); dus na elkaar
    uit = snel(bericht) if c.kring1 else None
    if uit is not None:
        eerst = uit_kring1(uit, bericht, versies)
        if not LEZERS.get(c.lezer, {}).get("uitleg_database"):
            return foto_bij_bron(eerst, beeld, config, foto_haler) if foto else eerst
        try:  # v12: de lezer legt het uit; lukt dat niet (de daggrens, een fout), dan het antwoord uit de database
            gelezen = controleer(kosten_conn, bericht, config, client, zoek, lambda _: None, sites, dag, datum, beeld,
                                 bewaak, checks, zoek_checks, beeldstap, foto=False, voor_model=voor_model)
        except Exception:  # noqa: BLE001 - het oordeel staat al vast; de uitleg is een toegift
            gelezen = None
        # #32.54: ook een groen uit de database krijgt de foto bij de bron, zoals in de meting
        return foto_bij_bron(met_uitleg(eerst, gelezen), beeld, config, foto_haler) if foto else met_uitleg(eerst, gelezen)
    if c.zoeker not in ZOEKERS:
        raise bc.VersieFout(f"zoeker {c.zoeker!r} bestaat niet in de code")
    if checks is None and zoek_checks is not None and LEZERS.get(c.lezer, {}).get("database"):
        checks = zoek_checks(bericht)
    if bool(LEZERS.get(c.lezer, {}).get("database")) != (checks is not None):  # vóór de zoekvraag, die kost geld
        raise bc.VersieFout(f"lezer {c.lezer!r} en de checks uit de database passen niet bij elkaar")
    if LEZERS.get(c.lezer, {}).get("vooraf") and not c.speurvraag_model:  # vóór elke vraag die geld kost (DR6)
        raise bc.VersieFout(f"lezer {c.lezer!r} vraagt een model voor de zoekvragen vooraf; `speurvraag_model` is leeg")
    if bewaak is not None:
        bewaak()
    if LEZERS.get(c.lezer, {}).get("vooraf"):
        gelezen = _een_lezing(kosten_conn, bericht, config, client, zoek, sites, dag, datum, beeld, checks, versies,
                              voor_model)
        return foto_bij_bron(gelezen, beeld, config, foto_haler) if foto else gelezen
    if beeldstap is not None and config.beeldstap.aan and beeld is not None and checks is not None:
        # #32.35: de beeldstap (lokaal) en het zwartmaken lopen tegelijk met de zoekvraag; de checks krijgen het beeld
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(2) as pool:
            stap = pool.submit(beeldstap, beeld, bericht, checks)
            zwart = pool.submit(opknippen.zwart_beeld, beeld, config.ocr) if c.beeld else None
            resultaten = resultaten_uit(zoek(zoekvraag(bericht)), sites)
            checks = stap.result()
            voor_model = zwart.result()[0] if zwart is not None else None
    else:
        resultaten = resultaten_uit(zoek(zoekvraag(bericht)), sites)
        # B55: het beeld gaat alleen zwartgemaakt mee, en alleen met de schakelaar aan
        voor_model = opknippen.zwart_beeld(beeld, config.ocr)[0] if beeld is not None and c.beeld else None
    msg = client.messages.create(**leesverzoek(bericht, resultaten, datum, config, voor_model, checks))
    antwoord = lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
    kosten = bc.kosten(bc.gebruik_uit(msg)) + ZOEKPRIJS
    gezien = beeld is not None and c.beeld
    uit = na_lezen(antwoord, bericht, resultaten, checks, c.lezer, gezien)
    groepen = []
    if c.speuren and LEZERS[c.lezer].get("tweede") and uit["uitkomst"] in SPEUR_BIJ and antwoord["verder"]:
        # #32.40: de speurstap, met de daggrens opnieuw vóór de verdere zoekvragen
        if bewaak is not None:
            bc.boek(kosten_conn, dag, kosten)
            kosten_eerst, kosten = kosten, 0.0
            bewaak()
        else:
            kosten_eerst = 0.0
        resultaten, groepen = speur(antwoord["verder"], resultaten, zoek, sites)
        msg = client.messages.create(**leesverzoek(bericht, resultaten, datum, config, voor_model, checks, groepen))
        antwoord = lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
        kosten += bc.kosten(bc.gebruik_uit(msg)) + ZOEKPRIJS * len(groepen)
        bc.boek(kosten_conn, dag, kosten)
        kosten += kosten_eerst
        uit = na_lezen(antwoord, bericht, resultaten, checks, c.lezer, gezien)
    else:
        bc.boek(kosten_conn, dag, kosten)
    return {"route": "zoeken", "gelezen": bericht, "kosten": kosten, "versies": versies, **uit,
            "speurstap": [{k: g[k] for k in ("soort", "vraag", "site", "gevonden")} for g in groepen]}


def foto_bij_bron(uit: dict, beeld: bytes | None, config, foto_haler=None) -> dict:
    """De foto bij de bron (#32.54, DESIGN §4m): bij een groen antwoord met een beeld, als `[berichtcontrole] fotobron`
    een versie noemt, kijken of de foto op de goede pagina's staat die het bericht bevestigen. Een pagina of beeld dat
    niet opent, telt als niet gevonden: dan geen groen voor het bericht als geheel (twijfel versoepelt nooit). Het beeld
    blijft in het geheugen (DR3)."""
    from doublecheck import fotobron as fb

    c = config.berichtcontrole
    if not c.fotobron or beeld is None or not fb.moet_zoeken(uit, True):
        return uit
    beelden_van, beeld_van = (foto_haler or fb.haler)()

    def veilig(f):
        def doe(url):
            try:
                return f(url)
            except Exception:  # noqa: BLE001 - een pagina of beeld dat niet opent, is niet gevonden
                return None
        return doe

    s = config.beeldstap
    vondst = fb.zoek(beeld, fb.paginas(uit["bronnen"], c.fotobron), veilig(beelden_van), veilig(beeld_van),
                     drempel_pdq=s.drempel_pdq, min_punten=s.min_punten, min_dekking=s.min_dekking, versie=c.fotobron)
    uit = fb.toepassen(uit, vondst)
    return {**uit, "versies": {**uit.get("versies", {}), "photo": c.fotobron}}


def _een_lezing(kosten_conn, bericht: str, config, client, zoek, sites: dict, dag: str | None, datum: str | None,
                beeld: bytes | None, checks: list[dict] | None, versies: dict, voor_model: bytes | None = None) -> dict:
    """De controle in één lezing (v9, #32.41): het zwartgemaakte beeld; de zoekvragen vooraf van het kleine model,
    terwijl het bericht zelf al gezocht wordt; de zoekvragen tegelijk; en één keer lezen."""
    from concurrent.futures import ThreadPoolExecutor

    from doublecheck import berichtcontrole as bc
    from doublecheck import speurvraag as sv

    c = config.berichtcontrole
    if voor_model is None and beeld is not None and c.beeld:
        voor_model = opknippen.zwart_beeld(beeld, config.ocr)[0]
    with ThreadPoolExecutor(1) as pool:
        eerste = pool.submit(_veilig, zoek, zoekvraag(bericht))
        plan = client.messages.create(**sv.verzoek(bericht, datum, c.speurvraag_model, voor_model))
        verder = sv.lees("".join(getattr(b, "text", "") or "" for b in plan.content))
        antwoord_eerste = eerste.result()
    resultaten = resultaten_uit(antwoord_eerste, sites) if antwoord_eerste is not None else []
    resultaten, groepen = speur(verder, resultaten, zoek, sites)
    msg = client.messages.create(**leesverzoek(bericht, resultaten, datum, config, voor_model, checks, groepen))
    antwoord = lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
    kosten = sv.kosten(bc.gebruik_uit(plan)) + bc.kosten(bc.gebruik_uit(msg)) + ZOEKPRIJS * (1 + len(groepen))
    bc.boek(kosten_conn, dag, kosten)
    uit = na_lezen(antwoord, bericht, resultaten, checks, c.lezer, voor_model is not None,
                   gezocht=zelf_gezocht(groepen), jaar=int((dag or date.today().isoformat())[:4]))
    return {"route": "zoeken", "gelezen": bericht, "kosten": kosten, "versies": {**versies, "plan": sv.VERSIE}, **uit,
            "speurstap": [{k: g[k] for k in ("soort", "vraag", "site", "gevonden")} for g in groepen]}
