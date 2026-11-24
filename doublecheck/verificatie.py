"""Controleren met bronnen (PLAN #31.8, voorstel B43).

De vraag van de PO (2026-10-25): een machine die per bericht zegt of de
bewering klopt of fout is, en bij een fout de bronnen levert die het bewijzen.
De opzet heeft twee onderdelen: een model (eerst Haiku 5.5) dat leest, het
geheugen van Factiz raadpleegt en zelf op het web zoekt; en Factiz eromheen.
Dit is de goedkope toets van die hypothese, vóór er iets gebouwd wordt.

De regel: *klopt niet* alleen met een check uit het geheugen over dezelfde
bewering, of met een betrouwbare bron die haar rechtstreeks tegenspreekt, met
citaat; *klopt* alleen met een bron die haar bevestigt; anders *onzeker*.

Twee omstandigheden op dezelfde 100 stukken uit de toetshelft van de
basisset: (a) zoals in het echt, geheugen en web aan; (b) een nieuwe claim:
geen geheugen en de sites van redacties op het web geblokkeerd, zodat het
model het zelf moet bewijzen. Alleen de eigen check verbergen was niet genoeg:
in de proef vond het model de check van een andere redactie over dezelfde
claim (2026-10-25).

De bronnen zijn wat de API citeert (`cited_text`, letterlijk uit de bron) en
de checks uit het geheugen die het antwoord noemt ([F1]..[F5]). Offline, op
openbare data (B26).

Ronde 2 (PO 2026-10-25): vraag `verificatie-v2` met de datum van het bericht
en een regel over kleine afwijkingen in getallen (de twee oorzaken van de
valse vlaggen in ronde 1, §145), op 100 nieuwe stukken, met Haiku en Sonnet.

Ronde 4 (PO 2026-10-26): vraag `verificatie-v4` met vier uitkomsten. Naast
*klopt niet* (bewezen) komt *let op*: een concrete reden tot twijfel zonder
bron die het tegenspreekt, als signaal. Op de 100 stukken van ronde 2, Sonnet
zonder geheugen (`b`) en kaal, zonder zoeken (`k`): de nulmeting voor wat een
model zonder gereedschap weet.

    python -m doublecheck.verificatie geheugen [--ronde 2]
    python -m doublecheck.verificatie indienen --omstandigheid a|b|k [--ronde 2 --model haiku|sonnet] [--proef 5]
    python -m doublecheck.verificatie ophalen|lezen|tellen [--ronde 2 --model haiku|sonnet]
"""

from __future__ import annotations

import base64
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from doublecheck.machinevraag import (  # noqa: F401 - verhuisd naar de kern (PLAN #32.7c)
    MAX_ZOEKEN,
    MODEL,
    N_GEHEUGEN,
    OORDELEN,
    PROMPTVERSIE,
    REGEL_BEELDZOEKEN,
    REGEL_LET_OP,
    SYSTEEM,
    SYSTEEM_KAAL,
    VLOER_GEHEUGEN,
    VRAAG,
    VRAAG_V2,
    VRAAG_V4,
    VRAAG_V4_KAAL,
    VRAGEN,
    VRAGEN_KAAL,
    ZOEKEN_PER_1000,
    _OORDEEL_EN,
    bronnen_uit,
    geheugen_tekst,
    kandidaten_uit,
    lees_antwoord,
    verberg,
    verzoek,
    vraagtekst,
    zonder_factchecks_aan,
)

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "verificatie"
LABELS = WORTEL / "docs" / "steekproeven" / "31.8-verificatie.json"
ZAAD = 3145
BUDGET = 15.0  # PO 2026-10-25, per ronde: "grens $15"
OMSTANDIGHEDEN = ("a", "b", "bR", "aR", "k", "w")  # R = omgekeerd zoeken (3, 5); k = kaal (4); w = web (7)

# Per laag het aantal in de steekproef (plan van 2026-10-25, samen 100).
LAGEN = {"onwaar, oud": 13, "onwaar, vers": 12, "beeld onwaar": 15, "ware check": 25, "kernfeit": 10,
         "betrouwbaar artikel": 15, "webtekst": 10}

# Bekende factchecksites die niet (genoeg) in ons geheugen staan; met paden waar
# een site meer is dan alleen checks.
EXTRA_GEBLOKKEERD = ("snopes.com", "factcheck.afp.com", "fullfact.org", "factcheck.org", "leadstories.com",
                     "checkyourfact.com", "reuters.com/fact-check", "apnews.com/hub/ap-fact-check",
                     "usatoday.com/news/factcheck", "nieuwscheckers.nl", "correctiv.org/faktencheck",
                     "maldita.es", "newtral.es", "altnews.in", "boomlive.in", "vishvasnews.com",
                     "africacheck.org", "chequeado.com", "demagog.org.pl", "faktisk.no")
N_GEBLOKKEERD = 100

# Ronde 5 blokkeert ook de redacties van M4FC die nog ontbraken, en de factcheckers die
# in ronde 4 door de blokkade lekten (§147); bij een nieuwssite alleen het factcheckpad.
EXTRA_BLOK_R5 = ("211check.org", "congocheck.net", "dfrac.org", "factchecker.gr", "fatabyyano.net",
                 "indiatoday.in/fact-check", "larepublica.pe/verificador", "mythdetector.ge", "poligrafo.sapo.pt",
                 "tjekdet.dk", "rappler.com/newsbreak/fact-check", "newsmobile.in/nm-fact-checker", "cyberpeace.org",
                 "smhoaxslayer.com", "aap.com.au/factcheck", "telugupost.com/english-factcheck",
                 "aajtak.in/fact-check", "misbar.com", "medium.com/pesa-check")
RONDES = {1: {"map": UIT, "zaad": ZAAD, "versie": "verificatie-v1", "modellen": ("haiku",),
              "omstandigheden": ("a", "b")},
          2: {"map": UIT / "ronde-2", "zaad": ZAAD + 1, "versie": "verificatie-v2", "modellen": ("haiku", "sonnet"),
              "omstandigheden": ("a", "b")},
          # Ronde 3 (PO 2026-10-25): 50 beelden, elk met de valse claim en met het ware verhaal.
          3: {"map": UIT / "ronde-3", "zaad": ZAAD + 2, "versie": "verificatie-v3", "modellen": ("sonnet",),
              "omstandigheden": ("b", "bR", "aR"), "budget": 20.0},  # PO 2026-10-25: "grens $20"
          # Ronde 4 (PO 2026-10-26: "grens $60" voor de vier rondes van het haalbaarheidsplan, deze ~$6).
          4: {"map": UIT / "ronde-4", "stukken": 2, "versie": "verificatie-v4", "modellen": ("sonnet",),
              "omstandigheden": ("b", "k"), "budget": 7.0},
          # Ronde 5, de beeldenronde: 50 ware beelden uit M4FC tegenover 50 ongebruikte onware (PLAN #31.8).
          5: {"map": UIT / "ronde-5", "zaad": ZAAD + 4, "versie": "verificatie-v5", "modellen": ("sonnet",),
              "omstandigheden": ("b", "bR", "aR"), "budget": 12.0, "extra_blok": EXTRA_BLOK_R5,
              "vorm_gelijk": False},  # 3 kale foto's op 150 onware kandidaten: niet te evenaren
          # Ronde 6, in het wild: echte tiplineberichten, zoals in het echt (PLAN #31.8).
          6: {"map": UIT / "ronde-6", "zaad": ZAAD + 5, "versie": "verificatie-v4", "modellen": ("sonnet",),
              "omstandigheden": ("a",), "budget": 12.0},
          # Ronde 7, de bewijsronde: de vastgezette machine; w = de Verifyr-vloer, alleen op de evergreens.
          7: {"map": UIT / "ronde-7", "zaad": ZAAD + 6, "versie": "verificatie-v4", "modellen": ("sonnet",),
              "omstandigheden": ("a", "b", "w"), "budget": 30.0, "extra_blok": EXTRA_BLOK_R5,
              "lagen": {"w": ("evergreen",), "a": ("ware check", "onwaar, oud", "onwaar, vers"),
                        "b": ("ware check", "onwaar, oud", "onwaar, vers")}}}
N_PAREN = 50
N_ONWAAR_KANDIDATEN = 150
TIPLINES = WORTEL / "data" / "extern" / "meedan-tiplines" / "claim_detection_dataset.csv"
DATUM_WILD = "2019–2021 (exact date unknown)"  # de tiplines van Kazemi e.a. liepen 2019 tot en met 2021
N_PER_TAAL = 50
EVERGREENS = WORTEL / "docs" / "steekproeven" / "31.8-evergreens-50.json"
N_BEWIJS_WAAR, N_BEWIJS_ONWAAR = 300, 100


class Weigering(Exception):
    """Tellen of indienen kan niet: een oordeel dat telt zonder label, of boven het budget."""


# --- de steekproef ------------------------------------------------------------------

def laag_van(s: dict) -> str | None:
    if s.get("laag"):
        return s["laag"]
    if s["soort"] == "tekst" and s["bron"] == "claimreview":
        if s["label"] == "onwaar":
            return "onwaar, vers" if s.get("vers") else "onwaar, oud"
        return "ware check" if s["label"] == "waar" else None
    if s["soort"] == "beeld" and s["label"] == "onwaar":
        return "beeld onwaar"
    return {"n3-kern": "kernfeit", "sheffield-trustworthy": "betrouwbaar artikel"}.get(s["bron"]) \
        or ("webtekst" if s["soort"] == "webtekst" else None)


def steekproef(stukken: list[dict], zaad: int = ZAAD, uitsluiten: list[dict] = ()) -> list[dict]:
    """Per laag een vast aantal uit de toetshelft, willekeurig en telkens
    dezelfde; van de kern elk stuk een ander feit (de kern heeft per feit
    meerdere formuleringen). `uitsluiten`: de stukken van een eerdere ronde,
    en van de kern ook hun feiten."""
    rng = random.Random(zaad)
    weg = {s["id"] for s in uitsluiten}
    weg_feit = {s.get("feit") for s in uitsluiten if s.get("feit")}
    per_laag: dict[str, list] = defaultdict(list)
    for s in sorted(stukken, key=lambda s: s["id"]):
        if s["id"] in weg or (s.get("feit") and s["feit"] in weg_feit):
            continue
        if s["helft"] == "toets" and (laag := laag_van(s)) in LAGEN:
            per_laag[laag].append(s)
    gekozen = []
    for laag in sorted(LAGEN):
        groep = per_laag[laag]
        if laag == "kernfeit":
            per_feit: dict[str, list] = defaultdict(list)
            for s in groep:
                per_feit[s.get("feit") or s["sleutel"]].append(s)
            feiten = rng.sample(sorted(per_feit), LAGEN[laag])
            gekozen += [rng.choice(per_feit[f]) for f in feiten]
        else:
            gekozen += rng.sample(groep, LAGEN[laag])
    return gekozen


def onware_kandidaten(beelden: list[dict], gebruikt: set[str], n: int = N_ONWAAR_KANDIDATEN,
                      zaad: int = ZAAD + 4) -> list[dict]:
    """Ronde 5: onware beelden uit de toetshelft die nooit eerder gebruikt zijn,
    willekeurig en telkens dezelfde; daaruit komt na de vormcheck de onware helft."""
    groep = sorted((s for s in beelden if s["label"] == "onwaar" and s["helft"] == "toets"
                    and s["sleutel"] not in gebruikt), key=lambda s: s["id"])
    return sorted(random.Random(zaad).sample(groep, min(n, len(groep))), key=lambda s: s["id"])


def beeldset(waar: list[dict], onwaar: list[dict], vorm: dict[str, tuple[bool, bool]], n: int = N_PAREN,
             zaad: int = ZAAD + 4, gelijk: bool = True) -> list[dict]:
    """Ronde 5: `n` ware en `n` onware beelden, zonder stempel van een
    factchecker (dan verraadt het beeld het oordeel) en, met `gelijk`, in beide
    helften evenveel kale foto's, zodat de vorm niets verraadt; zo dicht
    mogelijk bij de helft kaal. Weigert als de vorm niet gelijk te krijgen is.
    Zonder `gelijk` elke helft willekeurig (de vorm bleek niet te evenaren,
    PLAN #31.8). `vorm`: per sleutel (kaal, stempel)."""
    def schoon(groep: list[dict]) -> tuple[list[dict], list[dict]]:
        ok = sorted((s for s in groep if s["sleutel"] in vorm and not vorm[s["sleutel"]][1]), key=lambda s: s["id"])
        return [s for s in ok if vorm[s["sleutel"]][0]], [s for s in ok if not vorm[s["sleutel"]][0]]

    (wk, wt), (ok, ot) = schoon(waar), schoon(onwaar)
    if not gelijk:
        rng = random.Random(zaad)
        w, o = sorted(wk + wt, key=lambda s: s["id"]), sorted(ok + ot, key=lambda s: s["id"])
        if len(w) < n or len(o) < n:
            raise Weigering(f"te weinig beelden zonder stempel: waar {len(w)}, onwaar {len(o)}")
        return sorted(rng.sample(w, n) + rng.sample(o, n), key=lambda s: s["id"])
    laag, hoog = max(0, n - min(len(wt), len(ot))), min(len(wk), len(ok), n)
    if laag > hoog:
        raise Weigering(f"vorm niet gelijk te krijgen: kaal waar {len(wk)}, onwaar {len(ok)}; "
                        f"met tekst waar {len(wt)}, onwaar {len(ot)}")
    n_kaal = min(max(n // 2, laag), hoog)
    rng = random.Random(zaad)
    gekozen = rng.sample(wk, n_kaal) + rng.sample(wt, n - n_kaal) + rng.sample(ok, n_kaal) + rng.sample(ot, n - n_kaal)
    return sorted(gekozen, key=lambda s: s["id"])


def wilde_steekproef(rijen: list[dict], n_per_taal: int = N_PER_TAAL, zaad: int = ZAAD + 5) -> list[dict]:
    """Ronde 6: per taal `n_per_taal` berichten van sociale media en tiplines
    (niet de claims van factchecksites) met een duidelijke meerderheid van de
    annotatoren, willekeurig en telkens dezelfde."""
    rng = random.Random(zaad)
    per_taal: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rijen):
        if r["source"] == "social media" and r["majority_label"] in ("Yes", "No"):
            per_taal[r["language"]].append(i)
    uit = []
    for taal in sorted(per_taal):
        for i in sorted(rng.sample(per_taal[taal], min(n_per_taal, len(per_taal[taal])))):
            r = rijen[i]
            uit.append({"id": f"t-{i:05d}", "sleutel": f"tipline:{i:05d}", "soort": "tekst", "bron": "tipline",
                        "label": "bewering" if r["majority_label"] == "Yes" else "geen bewering", "laag": taal,
                        "taal": taal, "helft": "toets", "tekst": r["text"], "datum": DATUM_WILD, "zaak": None,
                        "vers": False})
    return uit


def bewijsset(stukken: list[dict], gebruikt: set[str], n_waar: int = N_BEWIJS_WAAR, n_onwaar: int = N_BEWIJS_ONWAAR,
              zaad: int = ZAAD + 6) -> list[dict]:
    """Ronde 7: ware en onware checks in het Engels uit de toetshelft, nooit
    eerder gebruikt, willekeurig en telkens dezelfde."""
    from doublecheck.leerstof import taalcode

    def groep(lagen: tuple[str, ...]) -> list[dict]:
        return sorted((s for s in stukken if s["helft"] == "toets" and s["id"] not in gebruikt
                       and taalcode(s.get("taal")) == "en" and laag_van(s) in lagen), key=lambda s: s["id"])

    rng = random.Random(zaad)
    gekozen = rng.sample(groep(("ware check",)), n_waar) + rng.sample(groep(("onwaar, oud", "onwaar, vers")), n_onwaar)
    return sorted(gekozen, key=lambda s: s["id"])


def evergreen_stukken() -> list[dict]:
    """De Verifyr-vloer: de 50 evergreens die vóór de meting zijn vastgelegd."""
    d = json.loads(EVERGREENS.read_text(encoding="utf-8"))
    return [{"id": f"e-{g['groep']:05d}", "sleutel": f"evergreen:{g['groep']}", "soort": "tekst", "bron": "evergreen",
             "label": "onwaar", "laag": "evergreen", "helft": "toets", "tekst": g["tekst"], "datum": None, "zaak": None,
             "vers": False} for g in d["gekozen"]]


def doet_mee(ronde: int, omstandigheid: str, s: dict) -> bool:
    """Of een stuk in deze run meedoet; zonder lagen in de ronde doet alles mee."""
    lagen = (RONDES[ronde].get("lagen") or {}).get(omstandigheid)
    return lagen is None or laag_van(s) in lagen


def extra_domeinen(ronde: int) -> set[str]:
    """De extra geblokkeerde domeinen zonder pad, voor het filter op het omgekeerd zoeken."""
    return {d for d in RONDES[ronde].get("extra_blok", ()) if "/" not in d}


def beeldparen(beelden: list[dict], zonder_claim: set[str], m4fc: dict[int, dict], gebruikt: set[str],
               n: int = N_PAREN, zaad: int = ZAAD + 2) -> list[dict]:
    """Ronde 3: beelden die zelf geen bewering doen (Haiku las er geen in, #30.12)
    met een bruikbaar waar verhaal in M4FC, nooit eerder gebruikt; eerst de
    toetshelft, dan willekeurig uit de rest. Elk beeld twee keer: met de valse
    claim en met het ware verhaal, dezelfde datum. (Eerst "foto zonder tekst":
    daar bleken schermafdrukken van de virale post met de valse claim tussen te
    zitten, 2026-10-25.)"""
    def bruikbaar(s: dict) -> bool:
        x = m4fc.get(int(s["sleutel"].split(":")[1])) or {}
        return (s["sleutel"] in zonder_claim and s["sleutel"] not in gebruikt
                and bool(x.get("use_true_caption")) and x.get("true_caption") not in (None, "", "not enough information"))

    kandidaten = sorted((s for s in beelden if bruikbaar(s)), key=lambda s: s["id"])
    toets = [s for s in kandidaten if s["helft"] == "toets"]
    rest = [s for s in kandidaten if s["helft"] != "toets"]
    rng = random.Random(zaad)
    gekozen = rng.sample(toets, min(n, len(toets)))
    gekozen += rng.sample(rest, min(n - len(gekozen), len(rest)))
    uit = []
    for s in sorted(gekozen, key=lambda s: s["id"]):
        x = m4fc[int(s["sleutel"].split(":")[1])]
        basis = {k: s.get(k) for k in ("sleutel", "soort", "bron", "helft", "datum", "zaak", "beeld", "vers")}
        uit.append({**basis, "id": f"{s['id']}o", "label": "onwaar", "laag": "beeld onwaar", "tekst": x["claim"]})
        uit.append({**basis, "id": f"{s['id']}w", "label": "waar", "laag": "beeld waar", "tekst": x["true_caption"]})
    return uit


# --- het antwoord -------------------------------------------------------------------


def zoekopdrachten(blokken: list[dict]) -> list[str]:
    return [b["input"]["query"] for b in blokken
            if b.get("type") == "server_tool_use" and (b.get("input") or {}).get("query")]


def geheugen_voor(omstandigheid: str, g: dict) -> list[dict]:
    """Wat het model uit het geheugen krijgt: in (a) de beste checks, in (b)
    en kaal (k) en op het web (w) niets."""
    return [] if omstandigheid.startswith("b") or omstandigheid in ("k", "w") else verberg(g["kandidaten"], set())


def met_beeldzoeken(omstandigheid: str) -> bool:
    return omstandigheid.endswith("R")


# --- tellen -------------------------------------------------------------------------

def uitkomst(label: str, oordeel: str) -> str:
    """Wat een oordeel betekent voor het stuk; "te lezen" moet een label krijgen
    voordat het telt."""
    if oordeel in ("klopt niet", "let op"):
        return "te lezen"
    if label == "onwaar":
        return "te lezen" if oordeel == "klopt" else "gemist"
    if label == "waar":
        return "bevestigd" if oordeel == "klopt" else "onzeker"
    if label in ("bewering", "geen bewering") and oordeel == "klopt":
        return "te lezen"  # ronde 6: elk oordeel met bron wordt gelezen
    return "goed" if oordeel == "geen bewering" else "anders"


def _label(labels: dict[str, str], sleutel: str) -> str:
    if sleutel not in labels:
        raise Weigering(f"geen label voor {sleutel} in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def telling(stukken: list[dict], antwoorden: dict[tuple, dict], labels: dict[str, str]) -> dict:
    """Per omstandigheid: per laag van de onware stukken bewezen, *klopt niet*
    zonder bewijs, *klopt* en gemist; per laag van de ware stukken *klopt niet*,
    *klopt* en onzeker, met de valse vlaggen gelezen; de webtekst. Weigert
    zolang een oordeel dat telt geen label heeft. Een *klopt niet* zonder één
    bron is zonder bewijs, en hoeft niet gelezen. *Let op* (ronde 4) telt bij
    een onwaar stuk alleen met een reden die klopt, en is bij een waar stuk een
    valse waarschuwing; die kolommen staan er alleen als het voorkomt."""
    uit: dict = {}
    for (om, id_), a in sorted(antwoorden.items()):
        s = next((x for x in stukken if x["id"] == id_), None)
        if s is None:
            continue
        laag, o = laag_van(s), a["oordeel"]
        h = uit.setdefault(om, {"onwaar": {}, "waar": {}, "ware stukken klopt niet": {"n": 0, "vals": 0, "terecht": 0},
                                "kern klopt niet": 0,
                                "webtekst": {"n": 0, "geen bewering": 0, "klopt niet vals": 0, "klopt niet terecht": 0,
                                             "anders": 0}})
        sleutel = f"{om}:{id_}"
        if s["label"] == "onwaar":
            d = h["onwaar"].setdefault(laag, {"n": 0, "bewezen": 0, "klopt niet zonder bewijs": 0, "klopt": 0,
                                              "onzeker": 0})
            d["n"] += 1
            if o == "klopt niet":
                bewezen = bool(a["bronnen"]) and _label(labels, sleutel) == "bewijst"
                d["bewezen" if bewezen else "klopt niet zonder bewijs"] += 1
            elif o == "klopt":
                if _label(labels, sleutel) == "bijschrift waar":  # de set had het mis, niet de machine
                    d["klopt, bijschrift waar"] = d.get("klopt, bijschrift waar", 0) + 1
                else:
                    d["klopt"] += 1
            elif o == "let op":
                k = "let op" if _label(labels, sleutel) == "terecht" else "let op toevallig"
                d[k] = d.get(k, 0) + 1
            else:
                d["onzeker"] += 1
        elif s["label"] == "waar":
            d = h["waar"].setdefault(laag, {"n": 0, "klopt niet": 0, "klopt": 0, "onzeker": 0})
            d["n"] += 1
            v = h["ware stukken klopt niet"]
            v["n"] += 1
            if o == "klopt niet":
                d["klopt niet"] += 1
                v["terecht" if _label(labels, sleutel) == "terecht" else "vals"] += 1
                h["kern klopt niet"] += s["bron"] == "n3-kern"
            elif o == "let op":
                d["let op"] = d.get("let op", 0) + 1
                w = h.setdefault("ware stukken let op", {"vals": 0, "terecht": 0})
                w["terecht" if _label(labels, sleutel) == "terecht" else "vals"] += 1
            else:
                d["klopt" if o == "klopt" else "onzeker"] += 1
        else:
            w = h["webtekst"]
            w["n"] += 1
            if o == "klopt niet":
                w["klopt niet terecht" if _label(labels, sleutel) == "terecht" else "klopt niet vals"] += 1
            elif o == "let op":
                k = "let op terecht" if _label(labels, sleutel) == "terecht" else "let op vals"
                w[k] = w.get(k, 0) + 1
            else:
                w["geen bewering" if o == "geen bewering" else "anders"] += 1
    return uit


def telling_wild(stukken: list[dict], antwoorden: dict[tuple, dict], labels: dict[str, str]) -> dict:
    """Ronde 6, per taal en samen: hoe vaak het model het eens is met de
    annotatoren over "bevat een bewering", de oordelen, wat er van de oordelen
    met bron overblijft bij lezen, elke *let op* gelezen, hoe vaak een check
    uit het geheugen meedoet (en standhoudt), en de kosten per bericht.
    Weigert zolang een oordeel met bron of een *let op* geen label heeft."""
    per_id = {s["id"]: s for s in stukken}
    uit: dict = {}
    for (om, id_), a in sorted(antwoorden.items()):
        s = per_id.get(id_)
        if s is None:
            continue
        o, sleutel = a["oordeel"], f"{om}:{id_}"
        model_bewering = o != "geen bewering"
        for groep in (s["laag"], "totaal"):
            h = uit.setdefault(groep, {"n": 0, "eens": 0, "annotatoren: bewering": 0, "model: bewering": 0,
                                       "oordelen": {}, "met bron": {"n": 0, "houdt stand": 0, "houdt geen stand": 0},
                                       "let op": {"n": 0, "terecht": 0, "toevallig": 0},
                                       "met check uit het geheugen": 0, "kosten": 0.0})
            h["n"] += 1
            h["eens"] += model_bewering == (s["label"] == "bewering")
            h["annotatoren: bewering"] += s["label"] == "bewering"
            h["model: bewering"] += model_bewering
            h["oordelen"][o] = h["oordelen"].get(o, 0) + 1
            h["kosten"] += a.get("kosten") or 0.0
            if o in ("klopt niet", "klopt") and a["bronnen"]:
                staat = _label(labels, sleutel) == "houdt stand"
                h["met bron"]["n"] += 1
                h["met bron"]["houdt stand" if staat else "houdt geen stand"] += 1
                h["met check uit het geheugen"] += staat and any(b["soort"] == "geheugen" for b in a["bronnen"])
            elif o == "let op":
                h["let op"]["n"] += 1
                h["let op"]["terecht" if _label(labels, sleutel) == "terecht" else "toevallig"] += 1
    for h in uit.values():
        h["kosten per bericht"] = round(h["kosten"] / h["n"], 5)
        h["kosten"] = round(h["kosten"], 2)
    return uit


# --- met de database, het model en de API -------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad) if pad.exists() else []


def map_van(ronde: int, model: str | None = None) -> Path:
    """Ronde 1 houdt haar bestanden in `data/verificatie/`; vanaf ronde 2 per model een map."""
    basis = RONDES[ronde]["map"]
    return basis if ronde == 1 or model is None else basis / model


def labels_van(ronde: int, model: str) -> Path:
    return LABELS if ronde == 1 else LABELS.with_name(f"31.8-verificatie-r{ronde}-{model}.json")


def gekozen_stukken(ronde: int = 1) -> list[dict]:  # pragma: no cover - op de basisset
    if RONDES[ronde].get("stukken"):
        return gekozen_stukken(RONDES[ronde]["stukken"])  # ronde 4 verkent op de stukken van ronde 2
    if ronde == 7:
        from doublecheck import basisset

        gebruikt = {s["id"] for r in (1, 2) for s in gekozen_stukken(r)}
        return bewijsset(basisset.lees(), gebruikt) + evergreen_stukken()
    if ronde == 6:
        import csv

        with TIPLINES.open(encoding="utf-8") as f:
            return wilde_steekproef(list(csv.DictReader(f)))
    if ronde == 5:
        from doublecheck import beeldzoeken

        vorm = beeldzoeken.lees_vormen(5)
        if not vorm:
            raise SystemExit("eerst `python -m doublecheck.beeldzoeken waar` en `... vorm indienen|ophalen`")
        return beeldset(*kandidaten_ronde5(), vorm, zaad=RONDES[5]["zaad"], gelijk=RONDES[5]["vorm_gelijk"])
    from doublecheck import basisset

    alle = basisset.lees()
    eerder: list[dict] = []
    for r in range(1, min(ronde, 3)):
        eerder += steekproef(alle, zaad=RONDES[r]["zaad"], uitsluiten=eerder)
    if ronde < 3:
        return steekproef(alle, zaad=RONDES[ronde]["zaad"], uitsluiten=eerder)
    from doublecheck import bewering

    v1 = bewering.antwoorden("antwoorden.jsonl")
    zonder_claim = {i["sleutel"] for i in bewering.items() if i["set"] == "P3" and v1.get(i["id"], ("?",))[0] == "geen"}
    m4fc = dict(enumerate(json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8"))))
    return beeldparen([s for s in alle if s["soort"] == "beeld"], zonder_claim, m4fc, {s["sleutel"] for s in eerder},
                      zaad=RONDES[3]["zaad"])


def kandidaten_ronde5() -> tuple[list[dict], list[dict]]:  # pragma: no cover - op de basisset en M4FC
    """De ware beelden die zijn opgehaald, en de onware kandidaten: nooit
    gebruikt in ronde 1 tot en met 3, met de claim van M4FC als bijschrift en
    de publicatiedatum van de check, net als de ware."""
    from doublecheck import basisset, beeldzoeken

    m4fc = json.loads(beeldzoeken.M4FC_JSON.read_text(encoding="utf-8"))
    gebruikt = {s["sleutel"] for r in (1, 2, 3) for s in gekozen_stukken(r)}
    beelden = [s for s in basisset.lees() if s["soort"] == "beeld"]
    onwaar = []
    for s in onware_kandidaten(beelden, gebruikt):
        x = m4fc[int(s["sleutel"].split(":")[1])]
        onwaar.append({**s, "laag": "beeld onwaar", "tekst": x["claim"],
                       "datum": (x.get("fc_pub_date") or "")[:10] or s.get("datum")})
    return beeldzoeken.ware_stukken(m4fc), onwaar


def _zoektekst(s: dict, beeldzinnen: dict[str, str]) -> str | None:
    if s["soort"] == "beeld" and s.get("tekst"):
        return s["tekst"][:600]  # ronde 3: het bijschrift
    if s["soort"] == "beeld":
        return beeldzinnen.get(s["sleutel"])  # wat Haiku eerder in het beeld las (#30.12)
    return s["tekst"][:600]


def geheugen_zoeken(ronde: int = 1) -> Path:  # pragma: no cover - met bge-m3 en de database
    """Per stuk de beste checks uit het geheugen (top 8 vanaf de vloer, zodat er
    in omstandigheid b na het verbergen nog vijf over kunnen zijn), met oordeel,
    redactie, datum en link van de jongste check."""
    import sqlite3

    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.leerling import _beeldzinnen
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    lees = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    lees.row_factory = sqlite3.Row
    stukken = gekozen_stukken(ronde)
    beeldzinnen = _beeldzinnen()
    teksten = [(s, t) for s in stukken if (t := _zoektekst(s, beeldzinnen))]
    lijsten = search_texts(conn, fingerprint_texts([t for _, t in teksten], config.model_versions.text_embedding),
                           8, varianten=True)
    map_ = map_van(ronde)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / "geheugen.jsonl"
    with pad.open("w", encoding="utf-8") as f:
        for (s, t), lijst in zip(teksten, lijsten):
            f.write(json.dumps({"id": s["id"], "zoektekst": t, "kandidaten": kandidaten_uit(lees, lijst),
                                "eigen": sorted(eigen_cluster(lees, s.get("zaak")))}, ensure_ascii=False) + "\n")
    for s in stukken:
        if not _zoektekst(s, beeldzinnen):
            with pad.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": s["id"], "zoektekst": None, "kandidaten": [], "eigen": []}) + "\n")
    return pad


def eigen_cluster(lees, zaak: str | None) -> set[str]:  # pragma: no cover - op de database
    """De eigen check van een stuk en de claims die er één bewering mee vormen."""
    from doublecheck.clustering import cluster_members

    if not zaak or not lees.execute("SELECT 1 FROM claim WHERE claim_id = ?", (zaak,)).fetchone():
        return set()
    return cluster_members(lees, zaak) | {zaak}


def geblokkeerd() -> list[str]:  # pragma: no cover - op de database
    """De domeinen van de redacties in ons geheugen (de eerste honderd dekken
    97,6% van de checks) en de bekende factchecksites erbuiten."""
    import sqlite3
    from collections import Counter
    from urllib.parse import urlparse

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    teller: Counter = Counter()
    for (url,) in conn.execute("SELECT url FROM factcheck"):
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if host:
            teller[host] += 1
    return list(dict.fromkeys([h for h, _ in teller.most_common(N_GEBLOKKEERD)] + list(EXTRA_GEBLOKKEERD)))


def factcheck_domeinen() -> set[str]:  # pragma: no cover - op de database
    """Alle domeinen van de redacties in ons geheugen (427) en de bekende andere,
    voor het filter op het omgekeerd zoeken (alleen de domeinen, zonder pad)."""
    import sqlite3
    from urllib.parse import urlparse

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    uit = {(urlparse(u).hostname or "").lower().removeprefix("www.") for (u,) in conn.execute("SELECT url FROM factcheck")}
    return {d for d in uit if d} | {e.split("/")[0] for e in EXTRA_GEBLOKKEERD}


def beeldpaginas_voor(omstandigheid: str, s: dict, gevonden: dict[str, dict], domeinen: set[str]) -> list[dict] | None:
    """Wat het model uit het omgekeerd zoeken krijgt: niets zonder R; in (b)
    zonder de pagina's van factcheckers."""
    if not met_beeldzoeken(omstandigheid):
        return None
    from doublecheck.beeldzoeken import N_IN_VRAAG, zonder_factchecks

    paginas = (gevonden.get(s.get("sleutel")) or {}).get("paginas", [])
    if zonder_factchecks_aan(omstandigheid):
        paginas = zonder_factchecks(paginas, domeinen)
    return paginas[:N_IN_VRAAG]


# Gemeten in ronde 1 (Haiku): (a) 11.000 tokens in, 0,7 zoekopdrachten; (b) 25.000 en 1,8; ~1.300 uit.
_VERBRUIK = {"a": (12_000, 1), "b": (26_000, 2), "aR": (14_000, 1), "bR": (28_000, 2), "k": (3_000, 0),
             "w": (20_000, 2)}


def kosten(n: int, model: str = MODEL, omstandigheid: str = "b", uit_per_stuk: int = 1_500) -> float:
    """Ruim boven wat ronde 1 werkelijk gebruikte, per omstandigheid."""
    from doublecheck.leraar import MODELLEN

    m = MODELLEN[model]
    in_per_stuk, zoeken = _VERBRUIK[omstandigheid]
    return n * ((in_per_stuk * m["in"] + uit_per_stuk * m["uit"]) / 1e6 + zoeken * ZOEKEN_PER_1000 / 1000)


def al_ingediend(ronde: int = 1) -> float:
    """Wat een ronde samen kost, de proef meegerekend, over alle modellen: van
    een afgeronde batch het werkelijke bedrag, van een lopende de schatting."""
    mappen = [map_van(ronde)] if ronde == 1 else [map_van(ronde, m) for m in RONDES[ronde]["modellen"]]
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for map_ in mappen
               for naam in ("batches.jsonl", "proef-batches.jsonl", "fout-batches.jsonl") for b in _jsonl(map_ / naam))


def antwoorden(ronde: int = 1, model: str = MODEL) -> dict[tuple, dict]:
    """Per (omstandigheid, id) het laatste leesbare antwoord."""
    uit: dict[tuple, dict] = {}
    for r in _jsonl(map_van(ronde, model) / "antwoorden.jsonl"):
        sleutel = (r["omstandigheid"], r["id"])
        if r["oordeel"] != "onleesbaar" or sleutel not in uit:
            uit[sleutel] = r
    return uit


def _lees_labels(ronde: int = 1, model: str = MODEL) -> dict[str, str]:
    pad = labels_van(ronde, model)
    if not pad.exists():
        return {}
    return {r["sleutel"]: r["label"] for r in json.loads(pad.read_text(encoding="utf-8"))["labels"]}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="Controleren met bronnen (#31.8)")
    parser.add_argument("stap", choices=("geheugen", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("--omstandigheid", choices=OMSTANDIGHEDEN)
    parser.add_argument("--proef", type=int, default=0)
    parser.add_argument("--ronde", type=int, choices=tuple(RONDES), default=1)
    parser.add_argument("--model", choices=("haiku", "sonnet", "opus"), default=MODEL)
    args = parser.parse_args()
    if args.model not in RONDES[args.ronde]["modellen"]:
        raise SystemExit(f"ronde {args.ronde} is voor {', '.join(RONDES[args.ronde]['modellen'])}")
    if args.omstandigheid and args.omstandigheid not in RONDES[args.ronde]["omstandigheden"]:
        raise SystemExit(f"ronde {args.ronde} kent {', '.join(RONDES[args.ronde]['omstandigheden'])}")
    if args.stap == "geheugen":
        print(geheugen_zoeken(args.ronde))
        return
    versie = RONDES[args.ronde]["versie"]
    map_ = map_van(args.ronde, args.model)
    stukken = gekozen_stukken(args.ronde)
    per_id = {s["id"]: s for s in stukken}
    geheugen = {r["id"]: r for r in _jsonl(map_van(args.ronde) / "geheugen.jsonl")}
    gevonden: dict[str, dict] = {}
    if args.ronde >= 3:
        from doublecheck import beeldzoeken

        gevonden = beeldzoeken.lees(args.ronde)
    if args.stap == "tellen":
        tel = telling_wild if args.ronde == 6 else telling
        print(json.dumps(tel(stukken, antwoorden(args.ronde, args.model), _lees_labels(args.ronde, args.model)),
                         ensure_ascii=False, indent=1))
        return
    if args.stap == "lezen":
        labels = _lees_labels(args.ronde, args.model)
        for (om, id_), a in sorted(antwoorden(args.ronde, args.model).items()):
            s = per_id[id_]
            if uitkomst(s["label"], a["oordeel"]) != "te lezen" or f"{om}:{id_}" in labels:
                continue
            if s["label"] == "onwaar" and a["oordeel"] == "klopt niet" and not a["bronnen"]:
                continue
            print(f"\n[{om}:{id_} · {laag_van(s)} · label {s['label']}] OORDEEL {a['oordeel']}\n"
                  f"  BERICHT: {(s.get('tekst') or s.get('beeld') or '')[:300]}\n  BEWERING: {a.get('bewering')}\n"
                  f"  UITLEG: {a.get('uitleg')}")
            for b in a["bronnen"]:
                print(f"  BRON ({b['soort']}): {b.get('url')} — {b.get('citaat') or b.get('claim')}")
        return
    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    map_.mkdir(parents=True, exist_ok=True)
    batches = map_ / "batches.jsonl"
    if args.stap == "indienen":
        if not args.omstandigheid:
            raise SystemExit("--omstandigheid a, b of k")
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        nog = [s for s in stukken if f"{args.omstandigheid}-{s['id']}" not in ingediend
               and doet_mee(args.ronde, args.omstandigheid, s)]
        kies = nog[:: max(1, len(nog) // args.proef)][: args.proef] if args.proef else nog
        if not kies:
            raise SystemExit("niets in te dienen")
        geschat = kosten(len(kies), args.model, args.omstandigheid)
        al, budget = al_ingediend(args.ronde), RONDES[args.ronde].get("budget", BUDGET)
        if al + geschat > budget:
            raise Weigering(f"geweigerd: ${al:.2f} al ingediend plus ${geschat:.2f} is meer dan ${budget:.2f}")
        blok = geblokkeerd() + list(RONDES[args.ronde].get("extra_blok", ()))
        domeinen = (factcheck_domeinen() | extra_domeinen(args.ronde)) if met_beeldzoeken(args.omstandigheid) else set()
        if met_beeldzoeken(args.omstandigheid) and any(s.get("sleutel") not in gevonden for s in kies):
            raise SystemExit("eerst `python -m doublecheck.beeldzoeken`: niet elk beeld is opgezocht")
        verzoeken = []
        for s in kies:
            kandidaten = geheugen_voor(args.omstandigheid, geheugen.get(s["id"], {"kandidaten": [], "eigen": []}))
            paginas = beeldpaginas_voor(args.omstandigheid, s, gevonden, domeinen)
            verzoeken.append(verzoek(s, kandidaten, args.omstandigheid, blok, args.model, versie, paginas))
        batch = client.messages.batches.create(requests=verzoeken)
        with batches.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": versie, "model": MODELLEN[args.model]["id"],
                                "schatting": round(geschat, 3), "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} berichten ({args.omstandigheid}), naar schatting ${geschat:.2f};"
              f" ronde {args.ronde} samen ${al_ingediend(args.ronde):.2f} van ${budget:.2f}")
        return
    m = MODELLEN[args.model]
    domeinen = (factcheck_domeinen() | extra_domeinen(args.ronde)) if gevonden else set()
    alle = _jsonl(batches)
    klaar = {k for k, a in antwoorden(args.ronde, args.model).items() if a["oordeel"] != "onleesbaar"}
    with (map_ / "antwoorden.jsonl").open("a", encoding="utf-8") as uit:
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                om, id_ = r.custom_id.split("-", 1)
                if r.result.type != "succeeded":
                    rij = {"omstandigheid": om, "id": id_, "oordeel": "onleesbaar", "bronnen": [], "fout": r.result.type}
                else:
                    msg = r.result.message
                    blokken = [blok.model_dump() for blok in msg.content]
                    zoek = getattr(msg.usage.server_tool_use, "web_search_requests", 0) if msg.usage.server_tool_use else 0
                    prijs = (msg.usage.input_tokens * m["in"] + msg.usage.output_tokens * m["uit"]) / 1e6 \
                        + zoek * ZOEKEN_PER_1000 / 1000
                    werkelijk += prijs
                    tekst = "".join(bl.get("text") or "" for bl in blokken if bl.get("type") == "text")
                    oordeel, bewering, uitleg = lees_antwoord(tekst)
                    kandidaten = geheugen_voor(om, geheugen.get(id_, {"kandidaten": [], "eigen": []}))
                    paginas = beeldpaginas_voor(om, per_id[id_], gevonden, domeinen) or []
                    rij = {"omstandigheid": om, "id": id_, "oordeel": oordeel, "bewering": bewering, "uitleg": uitleg,
                           "bronnen": bronnen_uit(blokken, kandidaten, paginas),
                           "zoekopdrachten": zoekopdrachten(blokken),
                           "zoekverzoeken": zoek, "in": msg.usage.input_tokens, "uit": msg.usage.output_tokens,
                           "kosten": round(prijs, 5), "stop": msg.stop_reason, "tekst": tekst, "prompt": versie,
                           "model": m["id"]}
                if (om, id_) in klaar:
                    continue
                uit.write(json.dumps(rij, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    batches.write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
    teller = defaultdict(int)
    for (om, _), a in antwoorden(args.ronde, args.model).items():
        teller[(om, a["oordeel"])] += 1
    print(dict(teller), f"werkelijk ${sum(b.get('werkelijk') or 0 for b in alle):.2f}")


if __name__ == "__main__":
    main()
