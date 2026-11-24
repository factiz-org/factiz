"""Hoofdletters in normaal schrift, voor de weergave op het platform (PLAN #34.2ae, SPECS E9.S15).

Een bewering die in hoofdletters rondging (*WHO CONDEMNS LOCKDOWN…*), en haar vertaling die het schreeuwen overnam, zijn
op de site moeilijk te lezen. Met opmaak alleen kan het niet goed: *WHO* wordt *Who*, *STF* wordt *Stf*. Een taalmodel
geeft elke tekst één keer normaal schrift (`hoofdletters-v1`, Haiku, tien per vraag), met een harde controle: het
resultaat mag alleen in hoofd- en kleine letters afwijken (`alleen_hoofdletters`). Wat de controle niet haalt, blijft in
hoofdletters. Een vertaling is tekst van Factiz en staat in de uitgave in normaal schrift; de bewering zelf is het citaat
en blijft zoals ze rondging, met het normale schrift ernaast (`publiceren`, tabel `bewering_normaal`). Pas na mijn
leesproef van 100 (`poort`). Het lab houdt zijn teksten.

    python -m doublecheck.hoofdletters kandidaten|vragen [--proef N]|lezen|tellen

Leest de nieuwste publicatiedatabase (openbare beweringen en eigen vertalingen), alleen-lezen. Uitvoer in
`data/hoofdletters/`; mijn lezing in `docs/steekproeven/34.2ae-hoofdletters.json`.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "hoofdletters"
ANTWOORDEN = MAP / "antwoorden.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2ae-hoofdletters.json"
VERSIE = "hoofdletters-v1"
GRENS = 1.00            # dollar
SCHATTING = 0.00006     # per tekst, direct gevraagd, tien per vraag
PER_VRAAG = 10
DRADEN = 8
ZAAD = 3424
AANDEEL = 0.8           # van de letters met een hoofd- en kleine vorm in hoofdletters
MIN_LETTERS = 12
PROEF_N = 100
MAX_KLEIN = 5           # kleine fouten (een hoofdletter te veel of te weinig die niets verandert) in de leesproef
LEESLABELS = ("goed", "klein", "fout", "twijfel")


class Weigering(Exception):
    pass


def in_hoofdletters(tekst: str) -> bool:
    """Of een tekst in hoofdletters geschreven is: minstens `AANDEEL` van de letters die een hoofd- en een kleine vorm
    hebben, bij minstens `MIN_LETTERS` zulke letters. Een schrift zonder hoofdletters (Devanagari, Arabisch, Chinees)
    is het nooit."""
    letters = [t for t in tekst or "" if t.isalpha() and t.lower() != t.upper()]
    return len(letters) >= MIN_LETTERS and sum(t.isupper() for t in letters) >= AANDEEL * len(letters)


def alleen_hoofdletters(was: str, nieuw: str) -> bool:
    """Of `nieuw` alleen in hoofd- en kleine letters van `was` afwijkt: dezelfde tekens op dezelfde plek, met witruimte
    samengevoegd. Een woord erbij, een leesteken anders of een teken weg: nee."""
    a, b = " ".join((was or "").split()), " ".join((nieuw or "").split())
    return bool(a) and len(a) == len(b) and all(x == y or x.lower() == y.lower() or x.upper() == y.upper()
                                                for x, y in zip(a, b))


def letterverzoek(teksten: list[str]) -> dict:
    """Eén vraag over een rijtje teksten: geef elke tekst normaal schrift, verander niets anders."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You restore normal capitalisation to texts that were written in capital letters, for a public archive of "
        "fact-checked claims. For each numbered text, return the same text in the normal capitalisation of its language:\n"
        "- a capital at the start of each sentence, the rest in lower case;\n"
        "- capitals for proper names: people, places, countries, organisations, parties, institutions, brands, titles of "
        "newspapers and programmes;\n"
        "- keep every acronym and abbreviation in capitals as that language writes it (WHO, UN, STF, PT, BH, FBI, CNN, "
        "COVID-19);\n"
        "- if part of a text is already in normal capitalisation, keep it.\n"
        "Change nothing else: the same letters, words, punctuation, numbers and order. Do not translate, correct, shorten "
        "or add anything, and do not add quotation marks.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "tekst"],
            "properties": {"nr": {"type": "integer"}, "tekst": {"type": "string"}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 6000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_letters(tekst: str | None, originelen: list[str]) -> list[str | None]:
    """De antwoorden op nummer: alleen een tekst die alleen in hoofd- en kleine letters afwijkt, iets verandert en niet
    meer in hoofdletters staat. Een nummer dat ontbreekt of twee keer voorkomt, telt niet."""
    uit: list[str | None] = [None] * len(originelen)
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        gezien = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr, nieuw = a.get("nr"), " ".join(str(a.get("tekst") or "").split())
        if not (isinstance(nr, int) and 1 <= nr <= len(originelen) and gezien[nr] == 1):
            continue
        was = originelen[nr - 1]
        if alleen_hoofdletters(was, nieuw) and nieuw != " ".join(was.split()) and not in_hoofdletters(nieuw):
            uit[nr - 1] = nieuw
    return uit


def sleutel(antwoord: dict) -> str:
    """Hoe een antwoord in de leesproef heet: de pagina en de taal (leeg voor de bewering zelf)."""
    return f"{antwoord['pagina']}:{antwoord['taal']}"


def _laatste(antwoorden: list[dict]) -> dict[str, dict]:
    return {sleutel(a): a for a in antwoorden if a.get("tekst")}


def leesproef(antwoorden: list[dict], zaad: int = ZAAD) -> list[dict]:
    """De honderd antwoorden die ik lees: willekeurig uit wat de controle doorliet. Bij dezelfde antwoorden altijd
    dezelfde."""
    laatste = _laatste(antwoorden)
    gekozen = random.Random(zaad).sample(sorted(laatste), min(PROEF_N, len(laatste)))
    return [laatste[k] for k in gekozen]


def poort(antwoorden: list[dict], pad: str | Path = LABELS) -> tuple[bool, str]:
    """Mag het normale schrift in de uitgave? Alleen als alle honderd gelezen zijn, zonder fout die verandert wat je
    leest en zonder twijfel, en met hoogstens `MAX_KLEIN` kleine."""
    proef = [sleutel(a) for a in leesproef(antwoorden)]
    if not proef:
        return False, "niets om te lezen"
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False, "nog niets gelezen"
    gelezen = Counter(labels.get(k) for k in proef if labels.get(k) in LEESLABELS)
    if sum(gelezen.values()) < len(proef):
        return False, f"{sum(gelezen.values())} van de {len(proef)} gelezen"
    if gelezen["fout"] or gelezen["twijfel"]:
        return False, f"{gelezen['fout']} fout en {gelezen['twijfel']} twijfel"
    if gelezen["klein"] > MAX_KLEIN:
        return False, f"{gelezen['klein']} kleine fouten, hoogstens {MAX_KLEIN}"
    return True, f"{gelezen['goed']} goed en {gelezen['klein']} klein van de {len(proef)}"


def geldig(antwoorden: list[dict], pad: str | Path = LABELS) -> tuple[dict[tuple[str, str], dict], str]:
    """Het normale schrift voor de uitgave, per (pagina, taal), met de tekst waarbij het hoort; niets als de poort dicht
    is. De uitgave legt het alleen naast een tekst die nog precies zo luidt."""
    open_, reden = poort(antwoorden, pad)
    if not open_:
        return {}, reden
    return {(a["pagina"], a["taal"]): {"was": a["was"], "tekst": a["tekst"]} for a in _laatste(antwoorden).values()}, reden


def voor_de_uitgave() -> tuple[dict[tuple[str, str], dict], str]:  # pragma: no cover - bestanden
    return geldig(_jsonl(ANTWOORDEN))


def alles() -> dict[tuple[str, str], dict]:  # pragma: no cover - bestanden
    """Alles wat de controle doorliet, zonder poort: alleen voor een voorbeeld op de eigen computer."""
    return {(a["pagina"], a["taal"]): {"was": a["was"], "tekst": a["tekst"]} for a in _laatste(_jsonl(ANTWOORDEN)).values()}


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _kandidaten() -> list[dict]:  # pragma: no cover - een bestand
    """Elke tekst in hoofdletters in de nieuwste uitgave: de bewering (taal leeg) en elke vertaling (de doeltaal). Een
    uitgave waarin het normale schrift al staat, heeft de vertalingen al omgezet: die komen van de bewering ernaast."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    uit = [{"pagina": nr, "taal": "", "was": tekst} for nr, tekst in pub.execute("SELECT nummer, bewering FROM pagina")
           if in_hoofdletters(tekst)]
    uit += [{"pagina": nr, "taal": taal, "was": tekst}
            for nr, taal, tekst in pub.execute("SELECT pagina, taal, tekst FROM vertaling") if in_hoofdletters(tekst)]
    return uit


def _vragen(proef: int | None) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(ANTWOORDEN)
    klaar = {(a["pagina"], a["taal"], a["was"]) for a in eerder if a.get("tekst")}   # wat de controle niet haalde, mag nog eens
    werk = [k for k in _kandidaten() if (k["pagina"], k["taal"], k["was"]) not in klaar]
    if proef:
        werk = random.Random(ZAAD).sample(werk, min(proef, len(werk)))
    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
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
        try:
            msg = client.messages.create(**letterverzoek([k["was"] for k in groep]))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for k, nieuw in zip(groep, lees_letters(tekst, [k["was"] for k in groep])):
                f.write(json.dumps({**k, "tekst": nieuw, "versie": VERSIE, "kosten": round(kosten / len(groep), 7)},
                                   ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(ANTWOORDEN)
    print(f"{len(_laatste(nu))} in normaal schrift, {sum(not a.get('tekst') for a in nu)} bleven in hoofdletters; "
          f"${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["kandidaten", "vragen", "lezen", "tellen"])
    p.add_argument("--proef", type=int)
    a = p.parse_args()
    try:
        if a.stap == "vragen":
            return _vragen(a.proef)
        if a.stap == "kandidaten":
            k = _kandidaten()
            print(f"{sum(not x['taal'] for x in k)} beweringen en {sum(bool(x['taal']) for x in k)} vertalingen in hoofdletters")
            return
        antwoorden = _jsonl(ANTWOORDEN)
        if a.stap == "lezen":
            MAP.mkdir(parents=True, exist_ok=True)
            uit = [{"sleutel": sleutel(x), "was": x["was"], "tekst": x["tekst"]} for x in leesproef(antwoorden)]
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", len(uit))
            return
        print(f"{len(_laatste(antwoorden))} in normaal schrift, {sum(not x.get('tekst') for x in antwoorden)} bleven in "
              f"hoofdletters; ${sum(x.get('kosten', 0.0) for x in antwoorden):.3f}")
        print("de poort:", poort(antwoorden))
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
