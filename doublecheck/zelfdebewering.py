"""Eén bewering, meer redacties (PLAN #34.2bp, SPECS E9.S31).

Het lab voegt alleen samen wat zijn meting draagt, dus dezelfde bewering in andere woorden of een andere taal staat vaak
op een eigen pagina, met een check van een andere redactie. Dit zoekt die paren: de buren van *Lijkt op* (bge-m3 op de
tekst zoals de site haar toont, `doublecheck.lijktop`) waarbij de twee pagina's geen redactie delen, en een vraag aan
Haiku per paar of het dezelfde bewering is (`zelfde-bewering-v1`). Alleen *ja* telt, en alleen een paar dat het model
zelf beoordeelde: geen ketting van A via B naar C.

De uitkomst gaat pas in een uitgave als mijn lezing van 100 willekeurige paren met *ja*, buiten de proef waarop de vraag
werd bijgesteld, er minstens 98 dezelfde bewering vindt (twijfel telt als niet). Op de site een verwijzing, nooit een
samenvoeging: elke pagina houdt haar eigen bewering en oordeel (DR2, DR5).

    python -m doublecheck.zelfdebewering kandidaten|proef [--n 50]|vragen|lezen|tellen

Leest de nieuwste publicatiedatabase en `data/lijktop/paren.jsonl`, alleen lezen; uitvoer in `data/zelfde/`, mijn lezing
in `docs/steekproeven/34.2bp-zelfde-bewering.json`. Haiku direct, tien paren per vraag, grens $2.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
from collections import Counter
from pathlib import Path

from doublecheck.lijktop import getoond

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "zelfde"
KANDIDATEN = MAP / "kandidaten.jsonl"
ANTWOORDEN = MAP / "antwoorden.jsonl"
PAREN = WORTEL / "data" / "lijktop" / "paren.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2bp-zelfde-bewering.json"
VERSIE = "zelfde-bewering-v2"       # v1: 21 van 24 ja dezelfde bewering in de proef; v2 met de datum en de regel voor
                                    # een algemene beschrijving van een foto of video
OORDELEN = ("ja", "nee", "twijfel")
PER_VRAAG = 10
DRADEN = 8
GRENS = 5.00                 # dollar voor alle vragen samen (PLAN #34.2bp; $2 tot de tweede lezer erbij kwam)
SCHATTING = 0.00006          # per paar bij Haiku, direct met tien per vraag (gemeten $0,055 per 1.000)
SONNET_KEER = 20             # Sonnet kost per token twintig keer zoveel als Haiku
PROEF, LEES, GOED = 50, 100, 98
# In de proef lag elk fout *ja* onder 0,84 (vier, alle bij een algemene beschrijving van een foto of video) en waren alle
# 17 vanaf 0,84 dezelfde bewering; vastgelegd vóór de leesproef van de poort (PLAN #34.2bp).
VLOER = 0.84
# De eerste leesproef van de poort: 91 van 100 met *ja* van Haiku dezelfde bewering, de missers vooral een algemene
# beschrijving van een foto of video. Daarom leest een tweede lezer (Sonnet) elk *ja* van Haiku opnieuw met dezelfde vraag;
# alleen *ja* van beide telt (PLAN #34.2bp).
TWEEDE = "sonnet"
# Op dezelfde 116 gelezen paren: Haiku en Sonnet samen 90 van 95, de missers een algemene beschrijving van een foto of
# video ("beelden van de overstroming in Libië"). Met tekst alleen is niet te zien of het hetzelfde beeld is. Daarom telt
# een bewering over een foto of video alleen als beide pagina's een persoon uit het namenregister delen (74 van 75).
BEELDWOORDEN = re.compile(r"\b(videos?|photos?|photographs?|images?|pictures?|footage|visuals|clips?|scenes|foto'?s?|"
                          r"beelden|afbeeldingen?|filmpjes?)\b", re.IGNORECASE)
BEELDREGEL = MAP / "beeldregel.jsonl"
ZAAD = 34212
MAX_TEKST = 500
_STUUR = re.compile("[‪-‮⁦-⁩﻿\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


class Weigering(Exception):
    """De stap mag zo niet draaien."""


def paar(a: str, b: str) -> str:
    """De sleutel van een paar, in vaste volgorde."""
    return "|".join(sorted((a, b)))


def kandidaten(paren: list[dict], redacties: dict[str, set[str]]) -> list[dict]:
    """De paren van *Lijkt op* tussen twee pagina's die er allebei nog zijn en geen redactie delen; per paar één keer, met
    de hoogste score, op volgorde van de sleutel."""
    beste: dict[str, float] = {}
    for p in paren:
        a, b = p["pagina"], p["ander"]
        if a == b or a not in redacties or b not in redacties or redacties[a] & redacties[b]:
            continue
        k = paar(a, b)
        beste[k] = max(beste.get(k, 0.0), float(p["score"]))
    return [{"paar": k, "score": round(s, 4)} for k, s in sorted(beste.items())]


def _kort(tekst: str) -> str:
    return " ".join(_STUUR.sub("", tekst or "").split())[:MAX_TEKST]


def tekst_van(taal: str, bewering: str, vertalingen: dict[str, str], datum: str = "") -> dict:
    """Wat het model van een pagina ziet: de tekst zoals de site haar toont, het origineel als dat anders is, en de dag
    van de eerste check."""
    toon = getoond(taal, bewering, vertalingen)
    uit = {"taal": taal or "und", "datum": (datum or "")[:10], "getoond": _kort(toon)}
    if _kort(bewering) != uit["getoond"]:
        uit["origineel"] = _kort(bewering)
    return uit


_SYSTEEM = """You help the editors of a public archive of fact-checked claims. Each numbered item is a pair of claims, A \
and B, checked by two different fact-checking newsrooms. Say whether A and B are the same claim.

Same claim: they assert the same thing about the same subject. The same event or subject, and the same who, what, where, \
when and numbers as far as they are mentioned. Other wording, another language, a shorter or longer form of the same \
assertion, or the same claim resurfacing in another year: still the same claim.

Not the same claim: one adds or changes a detail that changes what is claimed (another person, place, date, number, \
object, cause or consequence); one claims the opposite; or they are two different claims about the same story, person \
or topic. A claim about a photo or video and a claim about the event itself are the same claim only if they assert the \
same thing.

Many claims describe a photo or video. If both describe it only in general terms that could fit many different photos \
or videos ("video shows an Israeli attack on Lebanon", "photos show atrocities against Hindus in Bengal", "Gandhi with \
the British army"), answer "twijfel", unless a specific detail ties them to the same item: a named person doing a \
specific thing, a specific place, an unusual object or event, or the same quote. Each claim comes with the day it was \
first checked; that it was checked on a nearby day is not enough on its own.

Do not judge whether a claim is true. Answer for every pair:
- "nr": the number of the pair.
- "oordeel": "ja" (the same claim), "nee" (not the same claim) or "twijfel" (you cannot tell from the text).
- "reden": at most 15 words in English."""

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {"antwoorden": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["nr", "oordeel", "reden"],
                               "properties": {"nr": {"type": "integer"}, "oordeel": {"type": "string", "enum": list(OORDELEN)},
                                              "reden": {"type": "string"}}}}}}


def _blok(letter: str, t: dict) -> str:
    regel = f"{letter} ({t['taal']}{', first checked ' + t['datum'] if t.get('datum') else ''}): {t['getoond']}"
    if t.get("origineel"):
        regel += f"\n   original: {t['origineel']}"
    return regel


def versie_van(model: str) -> str:
    """De naam van de vraag per lezer: Haiku is de eerste, een ander model leest met dezelfde vraag opnieuw."""
    return VERSIE if model == "haiku" else f"{VERSIE}/{model}"


def verzoek(paren: list[tuple[dict, dict]], model: str = "haiku") -> dict:
    """Eén vraag over een rijtje paren (A, B), elk als `tekst_van`. Nooit het oordeel van een redactie: dat zegt niets
    over of het dezelfde bewering is."""
    from doublecheck.modellen import MODELLEN

    if not 1 <= len(paren) <= PER_VRAAG:
        raise Weigering(f"tussen 1 en {PER_VRAAG} paren per vraag")
    tekst = "\n\n".join(f"{i}.\n{_blok('A', a)}\n{_blok('B', b)}" for i, (a, b) in enumerate(paren, 1))
    return {"model": MODELLEN[model]["id"], "max_tokens": 3000, "system": _SYSTEEM,
            "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}


def lees(tekst: str | None, n: int) -> list[dict | None]:
    """De antwoorden op een rijtje van `n` paren, op nummer. Een nummer dat ontbreekt, buiten het rijtje valt of twee keer
    voorkomt telt niet, een oordeel buiten de drie ook niet."""
    uit: list[dict | None] = [None] * n
    try:
        antwoorden = json.loads(tekst)["antwoorden"]  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, KeyError):
        return uit
    if not isinstance(antwoorden, list):
        return uit
    geteld = Counter(a.get("nr") for a in antwoorden if isinstance(a, dict) and isinstance(a.get("nr"), int))
    for a in antwoorden:
        if not isinstance(a, dict) or not isinstance(a.get("nr"), int) or not 1 <= a["nr"] <= n or geteld[a["nr"]] != 1:
            continue
        if a.get("oordeel") in OORDELEN:
            reden = a.get("reden") if isinstance(a.get("reden"), str) else ""
            uit[a["nr"] - 1] = {"oordeel": a["oordeel"], "reden": " ".join(_STUUR.sub("", reden).split())[:160]}
    return uit


def proef(kandidaten_: list[dict], n: int = PROEF, zaad: int = ZAAD) -> list[str]:
    """De paren van de proef: willekeurig, met een vast zaad, verdeeld over de vakken van de score zoals ze voorkomen."""
    sleutels = [k["paar"] for k in kandidaten_]
    return sorted(random.Random(zaad).sample(sleutels, min(n, len(sleutels))))


def boven_vloer(antwoorden: dict[str, dict], scores: dict[str, float], vloer: float = VLOER) -> dict[str, dict]:
    """Alleen de antwoorden op paren met een score vanaf de vloer: daaronder telt ook een *ja* niet."""
    return {k: a for k, a in antwoorden.items() if scores.get(k, 0.0) >= vloer}


def leesproef(antwoorden: dict[str, dict], uitgesloten: set[str] | frozenset[str], n: int = LEES,
              zaad: int = ZAAD + 1) -> list[str]:
    """De paren voor de poort: willekeurig uit wat het model *ja* noemde, behalve de proef."""
    ja = sorted(k for k, a in antwoorden.items() if a.get("oordeel") == "ja" and k not in uitgesloten)
    return sorted(random.Random(zaad).sample(ja, min(n, len(ja))))


def poort(labels: dict[str, str], gekozen: list[str]) -> tuple[bool, str]:
    """Open als elk gekozen paar gelezen is en er minstens `GOED` van de `LEES` dezelfde bewering zijn."""
    if len(gekozen) < LEES:
        return False, f"te weinig paren met ja voor de leesproef ({len(gekozen)} van {LEES})"
    open_ = [k for k in gekozen if k not in labels]
    if open_:
        return False, f"{len(open_)} van {LEES} nog niet gelezen"
    goed = sum(labels[k] == "zelfde" for k in gekozen)
    return goed >= GOED, f"{goed} van {LEES} dezelfde bewering (eis {GOED})"


def over_een_beeld(*teksten: str) -> bool:
    """Of een van de beweringen, zoals de site haar toont, over een foto of video gaat."""
    return any(BEELDWOORDEN.search(t or "") for t in teksten)


def beeldregel(a: dict, b: dict, personen_a: set[str], personen_b: set[str]) -> bool:
    """Of een paar de regel voor beelden haalt: geen foto of video, of dezelfde persoon op beide pagina's."""
    return not over_een_beeld(a.get("getoond", ""), b.get("getoond", "")) or bool(personen_a & personen_b)


def met_beeldregel(antwoorden: dict[str, dict], gehaald: dict[str, bool]) -> dict[str, dict]:
    """Een *ja* dat de regel voor beelden niet haalt, wordt *twijfel*; een paar zonder uitkomst van de regel ook."""
    return {k: a if a.get("oordeel") != "ja" or gehaald.get(k) else
            {"oordeel": "twijfel", "reden": "een foto of video zonder dezelfde persoon op beide pagina's"}
            for k, a in antwoorden.items()}


def beide_ja(eerste: dict[str, dict], tweede: dict[str, dict]) -> dict[str, dict]:
    """Een paar telt als beide lezers *ja* zeggen; de rest wordt *nee* van de tweede, of blijft wat de eerste zei."""
    return {k: (tweede.get(k) or {"oordeel": "twijfel", "reden": "nog niet door de tweede lezer"}) if a.get("oordeel") == "ja"
            else a for k, a in eerste.items()}


def voor_uitgave(antwoorden: dict[str, dict], open_: bool) -> dict[str, list[str]]:
    """Per pagina de andere pagina's met dezelfde bewering, in beide richtingen; leeg zolang de poort dicht is."""
    uit: dict[str, list[str]] = {}
    if not open_:
        return uit
    for k, a in sorted(antwoorden.items()):
        if a.get("oordeel") != "ja":
            continue
        x, y = k.split("|")
        uit.setdefault(x, []).append(y)
        uit.setdefault(y, []).append(x)
    return {p: sorted(set(v)) for p, v in sorted(uit.items())}


# --- bestanden ------------------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def antwoorden(model: str = "haiku") -> dict[str, dict]:  # pragma: no cover - een bestand
    """Het laatste geldige antwoord per paar van één lezer."""
    uit: dict[str, dict] = {}
    for r in _jsonl(ANTWOORDEN):
        if r.get("versie") == versie_van(model) and r.get("uit"):
            uit[r["paar"]] = r["uit"]
    return uit


def _beeldregel() -> dict[str, bool]:  # pragma: no cover - een bestand
    return {r["paar"]: r["gehaald"] for r in _jsonl(BEELDREGEL)}


def samen() -> dict[str, dict]:  # pragma: no cover - bestanden
    """De uitkomst: *ja* alleen als Haiku het zegt, het paar de regel voor beelden haalt en Sonnet het ook zegt."""
    return beide_ja(met_beeldregel(antwoorden(), _beeldregel()), antwoorden(TWEEDE))


def _schrijf_beeldregel(sleutels: list[str]) -> None:  # pragma: no cover - bestanden
    """De regel voor beelden voor elk paar, op de tekst zoals de site haar toont en de personen van de uitgave."""
    pub = _publicatie()
    tekst = _teksten(pub, {p for k in sleutels for p in k.split("|")})
    soort = dict(pub.execute("SELECT nummer, soort FROM naam"))
    personen: dict[str, set[str]] = {}
    for p, n in pub.execute("SELECT pagina, naam FROM pagina_naam"):
        if soort.get(n) == "persoon":
            personen.setdefault(p, set()).add(n)
    with BEELDREGEL.open("w", encoding="utf-8") as f:
        for k in sleutels:
            a, b = k.split("|")
            if a in tekst and b in tekst:
                f.write(json.dumps({"paar": k, "gehaald": beeldregel(tekst[a], tekst[b], personen.get(a, set()),
                                                                      personen.get(b, set()))}) + "\n")


def _labels() -> dict:  # pragma: no cover - een bestand
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def _scores() -> dict[str, float]:  # pragma: no cover - een bestand
    return {k["paar"]: k["score"] for k in _jsonl(KANDIDATEN)}


def geldige_paren() -> tuple[dict[str, list[str]], str]:  # pragma: no cover - bestanden
    """Wat `publiceren` meeneemt: de paren als de poort open is, en de reden."""
    lezing = _labels()
    open_, reden = poort(lezing.get("leesproef", {}), lezing.get("gekozen", []))
    return voor_uitgave(boven_vloer(samen(), _scores()), open_), reden


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise SystemExit("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    return sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)


def _teksten(pub: sqlite3.Connection, nummers: set[str]) -> dict[str, dict]:  # pragma: no cover - een bestand
    vert: dict[str, dict[str, str]] = {}
    for nr, taal, tekst in pub.execute("SELECT pagina, taal, tekst FROM vertaling WHERE taal IN ('en', 'nl')"):
        if nr in nummers:
            vert.setdefault(nr, {})[taal] = tekst
    return {nr: tekst_van(taal, bewering, vert.get(nr, {}), datum)
            for nr, bewering, taal, datum in pub.execute("SELECT nummer, bewering, taal, eerste_datum FROM pagina")
            if nr in nummers}


def _kandidaten() -> None:  # pragma: no cover - bestanden
    pub = _publicatie()
    redacties: dict[str, set[str]] = {}
    for nr, r in pub.execute("SELECT pagina, redactie FROM check_"):
        redacties.setdefault(nr, set()).add(r)
    uit = kandidaten(_jsonl(PAREN), redacties)
    MAP.mkdir(parents=True, exist_ok=True)
    KANDIDATEN.write_text("".join(json.dumps(k) + "\n" for k in uit), encoding="utf-8")
    print(f"{len(uit)} paren zonder gedeelde redactie, over {len({p for k in uit for p in k['paar'].split('|')})} pagina's")


def _vragen(sleutels: list[str], model: str = "haiku") -> None:  # pragma: no cover - een model
    """Vraagt de vraag aan één lezer over de paren die van hem nog geen antwoord hebben, tien per vraag, direct en
    tegelijk."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    rijen = _jsonl(ANTWOORDEN)
    versie = versie_van(model)
    klaar = {r["paar"] for r in rijen if r.get("versie") == versie and r.get("uit")}
    werk = [k for k in sleutels if k not in klaar]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(r.get("kosten", 0.0) for r in rijen)
    geschat = SCHATTING * len(werk) * (1 if model == "haiku" else SONNET_KEER)
    if uitgegeven + geschat > GRENS:
        raise Weigering(f"geschat ${uitgegeven + geschat:.2f}, boven de grens van ${GRENS:.2f}")
    pub = _publicatie()
    tekst = _teksten(pub, {p for k in werk for p in k.split("|")})
    werk = [k for k in werk if all(p in tekst for p in k.split("|"))]
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN[model]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[str]) -> None:
        try:
            msg = client.messages.create(**verzoek([tuple(tekst[p] for p in k.split("|")) for k in groep], model))
            # direct, dus zonder batchkorting: twee keer de batchprijs
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            antwoord = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for k, g in zip(groep, lees(antwoord, len(groep))):
                f.write(json.dumps({"paar": k, "versie": versie, "uit": g, "kosten": round(kosten / len(groep), 7)},
                                   ensure_ascii=False) + "\n")

    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(ANTWOORDEN)
    print(f"{model}: {len(antwoorden(model))} paren beantwoord: "
          f"{dict(Counter(a['oordeel'] for a in antwoorden(model).values()))}; "
          f"${sum(r.get('kosten', 0.0) for r in nu):.3f} van ${GRENS:.2f}")


def _te_lezen(sleutels: list[str], uit: Path) -> None:  # pragma: no cover - bestanden
    pub, ant = _publicatie(), antwoorden()
    tekst = _teksten(pub, {p for k in sleutels for p in k.split("|")})
    score = {k["paar"]: k["score"] for k in _jsonl(KANDIDATEN)}
    with uit.open("w", encoding="utf-8") as f:
        for k in sleutels:
            a, b = (tekst.get(p, {}) for p in k.split("|"))
            f.write(json.dumps({"paar": k, "score": score.get(k), "model": ant.get(k), "A": a, "B": b},
                               ensure_ascii=False) + "\n")
    print(f"{len(sleutels)} paren in {uit}")


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stap", choices=["kandidaten", "proef", "vragen", "tweede", "lezen", "tellen"])
    ap.add_argument("--n", type=int, default=PROEF)
    ap.add_argument("--alleen-gelezen", action="store_true", help="tweede: alleen de paren die ik al las")
    a = ap.parse_args()
    if a.stap == "kandidaten":
        _kandidaten()
        return
    kand = _jsonl(KANDIDATEN)
    if not kand:
        raise SystemExit("eerst `kandidaten`")
    p = proef(kand, a.n)
    if a.stap == "proef":
        _vragen(p)
        _te_lezen(p, MAP / "proef-te-lezen.jsonl")
    elif a.stap == "vragen":
        _vragen([k["paar"] for k in kand if k["score"] >= VLOER])
    elif a.stap == "tweede":
        # de tweede lezer alleen over wat Haiku *ja* noemde vanaf de vloer
        ja = sorted(k for k, x in boven_vloer(antwoorden(), _scores()).items() if x.get("oordeel") == "ja")
        _schrijf_beeldregel(ja)
        gehaald = _beeldregel()
        werk = {k for k in ja if gehaald.get(k)}
        if a.alleen_gelezen:
            lezing = _labels()
            werk &= set(lezing.get("proef", {})) | set(lezing.get("leesproef_haiku", {}).get("paren", {}))
        print(f"{len(ja)} paren met ja van Haiku, {sum(gehaald.get(k, False) for k in ja)} halen de regel voor beelden")
        _vragen(sorted(werk), TWEEDE)
    elif a.stap == "lezen":
        lezing = _labels()
        eerder = set(p) | set(lezing.get("leesproef_haiku", {}).get("paren", {}))
        gekozen = leesproef(boven_vloer(samen(), _scores()), eerder, zaad=ZAAD + 2)
        _te_lezen(gekozen, MAP / "leesproef-2-te-lezen.jsonl")
    else:
        ant, lezing = boven_vloer(samen(), _scores()), _labels()
        gekozen = lezing.get("gekozen", [])
        open_, reden = poort(lezing.get("leesproef", {}), gekozen)
        print(f"{len(ant)} paren: {dict(Counter(x['oordeel'] for x in ant.values()))}")
        proeflabels = lezing.get("proef", {})
        if proeflabels:
            zelfde = [k for k, v in proeflabels.items() if v == "zelfde"]
            gemist = [k for k in zelfde if (ant.get(k) or {}).get("oordeel") != "ja"]
            print(f"proef: {len(proeflabels)} gelezen, {len(zelfde)} dezelfde bewering, waarvan het model {len(gemist)} miste")
        print(("poort open: " if open_ else "poort dicht: ") + reden)


if __name__ == "__main__":  # pragma: no cover
    main()
