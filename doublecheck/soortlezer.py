"""De soort nepnieuws, een voormeting (PLAN #34.2aj, stap 4 van het voorstel voor een kaart van de factchecks).

De vraag vóór een leesronde over de hele uitgave: kan een taalmodel de soort (de truc: valse context, bewerkt, verzonnen,
satire, ...) uit de bewering en de woorden van de redactie halen, zonder het artikel te lezen? De woorden van de
redacties zeggen het zelden (*false*, *disinformation*), en #32.39 haalde met het hele artikel 84 van 100.

De set zijn de factchecks uit #32.39 die in de uitgave staan, met de soort die Haiku uit het artikel las (`truc-v1`) en,
waar nagelezen, of die klopte. `soort-v1` stelt dezelfde vraag op dezelfde schaal, maar krijgt alleen de bewering (met de
Engelse vertaling als die er is), de woorden van de redacties en het oordeel. Nooit het artikel. Gemeten op zes
samengevoegde soorten, want de buren lopen door elkaar (§216). De eisen staan vooraf in PLAN #34.2aj.

    python -m doublecheck.soortlezer set|vragen [--proef N]|tellen|lezen

Leest `data/werkwijze/` (de antwoorden van #32.39), `docs/steekproeven/32.39-werkwijze.json` en de nieuwste
publicatiedatabase, alleen-lezen. Uitvoer in `data/soort/`. Haiku direct, tien per vraag, grens $1.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

from doublecheck.werkwijze import TRUCS, VORMEN

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "soort"
SET = MAP / "set.jsonl"
ANTWOORDEN = MAP / "antwoorden.jsonl"
WERKWIJZE = WORTEL / "data" / "werkwijze"
NAGELEZEN = WORTEL / "docs" / "steekproeven" / "32.39-werkwijze.json"
VERSIE = "soort-v1"
GRENS = 1.00            # dollar
SCHATTING = 0.0003      # per factcheck, direct gevraagd, tien per vraag
PER_VRAAG = 10
DRADEN = 8
ZAAD = 3427
# De eisen van PLAN #34.2aj, vooraf vastgelegd op 2026-11-15.
PRECISIE = 0.90         # op de bevestigde, van wat niet onduidelijk is
DEKKING = 0.50          # niet onduidelijk
OVEREENKOMST = 0.75     # met truc-v1 op de hele set (plafond ~84%)
# Zes samengevoegde soorten: de buren die in §216 door elkaar liepen, samen.
GROEPEN = {"false context": "uit zijn verband", "false connection": "uit zijn verband", "misleading": "misleidend",
           "fabricated": "verzonnen", "imposter": "nagemaakt of bewerkt", "manipulated": "nagemaakt of bewerkt",
           "ai-generated": "AI-gemaakt", "satire": "satire"}


class Weigering(Exception):
    pass


def soortverzoek(items: list[dict]) -> dict:
    """Eén vraag over een rijtje factchecks: per factcheck de vorm en de soort, alleen uit de bewering, de woorden van de
    redacties en het oordeel. Een item heeft `bewering`, `engels` (of leeg), `oordelen` (de woorden van de redacties) en
    `label`; geen artikeltekst."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You classify fact-checked claims for a public archive. For each numbered claim you get the claim as it was "
        "shared (with an English translation if there is one), the rating words the fact-checkers used, and the "
        "overall verdict. You do NOT get the fact-check article. Decide only from what is given.\n"
        "- vorm, the form of the content the claim is about: " + ", ".join(VORMEN) + ".\n"
        "- soort, how the content misleads:\n"
        "  - fabricated: made up, entirely false\n"
        "  - imposter: it pretends to come from a real outlet, person or institution (a logo, a fake account, a fake "
        "front page)\n"
        "  - manipulated: a real image, video, audio or document that was edited\n"
        "  - ai-generated: an image, video or voice made with AI\n"
        "  - false connection: the headline, caption or visuals do not match the content\n"
        "  - false context: genuine content shared with a false date, place or story\n"
        "  - misleading: true facts used to mislead (cherry-picking, missing context)\n"
        "  - satire: satire or parody taken as real\n"
        "  - unclear: the claim and the rating words do not show how it misleads\n"
        "Say unclear whenever you would have to guess. A claim that a video or photo shows something does not by itself "
        "tell whether the footage is old, edited or made with AI. A rating word that names the kind (altered, satire, "
        "missing context, out of context, fabricated, imposter) counts.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "vorm", "soort"],
            "properties": {"nr": {"type": "integer"}, "vorm": {"type": "string", "enum": list(VORMEN)},
                           "soort": {"type": "string", "enum": list(TRUCS)}}}}}}
    regels = []
    for i, k in enumerate(items, 1):
        delen = [f"{i}. Claim: {' '.join((k.get('bewering') or '').split())}"]
        if k.get("engels"):
            delen.append(f"   English: {' '.join(k['engels'].split())}")
        delen.append(f"   Rating words: {'; '.join(k.get('oordelen') or []) or '(none)'}")
        delen.append(f"   Verdict: {k.get('label') or 'unknown'}")
        regels.append("\n".join(delen))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 3000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "\n\n".join(regels)}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_soorten(tekst: str | None, n: int) -> list[dict | None]:
    """De antwoorden op nummer: alleen een bekende vorm en soort; een nummer dat ontbreekt, buiten het rijtje valt of
    twee keer voorkomt, telt niet."""
    uit: list[dict | None] = [None] * n
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        gezien = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr = a.get("nr")
        if (isinstance(nr, int) and 1 <= nr <= n and gezien[nr] == 1 and a.get("vorm") in VORMEN
                and a.get("soort") in TRUCS):
            uit[nr - 1] = {"vorm": a["vorm"], "soort": a["soort"]}
    return uit


def groep(soort: str | None) -> str | None:
    """De samengevoegde soort; onduidelijk (of geen antwoord) heeft er geen."""
    return GROEPEN.get(soort or "")


def telling(rijen: list[dict]) -> dict:
    """Per rij `soort` (uit de bewering), `truc` (uit het artikel, `truc-v1`) en `bevestigd` (True als de soort uit
    het artikel nagelezen en goed bevonden is, anders False of None). Telt op de samengevoegde soorten."""
    gedekt = [r for r in rijen if groep(r.get("soort"))]
    bevestigd = [r for r in rijen if r.get("bevestigd") and groep(r.get("truc"))]
    bev_gedekt = [r for r in bevestigd if groep(r.get("soort"))]
    beide = [r for r in gedekt if groep(r.get("truc"))]
    per_groep: dict[str, dict[str, int]] = {}
    for r in beide:
        g = per_groep.setdefault(groep(r["truc"]), {"artikel": 0, "zelfde": 0})
        g["artikel"] += 1
        g["zelfde"] += groep(r["soort"]) == groep(r["truc"])
    deel = lambda a, b: a / b if b else 0.0  # noqa: E731
    return {"n": len(rijen), "gedekt": len(gedekt), "dekking": deel(len(gedekt), len(rijen)),
            "bevestigd": len(bevestigd), "bevestigd_gedekt": len(bev_gedekt),
            "bevestigd_goed": sum(groep(r["soort"]) == groep(r["truc"]) for r in bev_gedekt),
            "precisie": deel(sum(groep(r["soort"]) == groep(r["truc"]) for r in bev_gedekt), len(bev_gedekt)),
            "overeenkomst_n": len(beide),
            "overeenkomst": deel(sum(groep(r["soort"]) == groep(r["truc"]) for r in beide), len(beide)),
            "vorm": deel(sum(r.get("vorm") == r.get("vorm_artikel") for r in rijen if r.get("vorm")),
                         sum(1 for r in rijen if r.get("vorm"))),
            "per_groep": per_groep}


def lat(t: dict) -> tuple[bool, list[str]]:
    """De drie eisen van PLAN #34.2aj; geeft ook wat er niet gehaald is."""
    mis = []
    if t["precisie"] < PRECISIE:
        mis.append(f"precisie {t['bevestigd_goed']} van {t['bevestigd_gedekt']} ({t['precisie']:.0%}), eis {PRECISIE:.0%}")
    if t["dekking"] < DEKKING:
        mis.append(f"dekking {t['gedekt']} van {t['n']} ({t['dekking']:.0%}), eis {DEKKING:.0%}")
    if t["overeenkomst"] < OVEREENKOMST:
        mis.append(f"overeenkomst met truc-v1 {t['overeenkomst']:.0%}, eis {OVEREENKOMST:.0%}")
    return not mis, mis


# --- bestanden en het model -------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase")
    return sqlite3.connect(f"{paden[-1].as_uri()}?mode=ro&immutable=1", uri=True)


def _set() -> list[dict]:  # pragma: no cover - bestanden
    """De factchecks uit #32.39 die in de uitgave staan, met wat het model mag zien en de soort uit het artikel."""
    pub = _publicatie()
    pagina_van: dict[str, str] = {}
    for pagina, url, link in pub.execute("SELECT pagina, url, link FROM check_"):
        pagina_van.setdefault(url, pagina)
        if link:
            pagina_van.setdefault(link, pagina)
    nagelezen = json.loads(NAGELEZEN.read_text(encoding="utf-8"))["claude"]
    adres = {x["id"]: x["url"] for x in _jsonl(WERKWIJZE / "set.jsonl")}
    uit = []
    for a in _jsonl(WERKWIJZE / "antwoorden.jsonl"):
        try:
            d = json.loads(a["antwoord"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        pagina = pagina_van.get(adres.get(a["id"], ""))
        if not (d.get("fact_check") is True and pagina and d.get("truc") in TRUCS):
            continue
        bewering, label = pub.execute("SELECT bewering, label FROM pagina WHERE nummer = ?", (pagina,)).fetchone()
        engels = pub.execute("SELECT tekst FROM vertaling WHERE pagina = ? AND taal = 'en'", (pagina,)).fetchone()
        oordelen = sorted({o.strip() for (o,) in pub.execute("SELECT oordeel_eigen FROM check_ WHERE pagina = ?",
                                                                (pagina,)) if o.strip()})
        bevestigd = nagelezen[a["id"]]["truc"] == "goed" if a["id"] in nagelezen else None
        uit.append({"id": a["id"], "pagina": pagina, "bewering": bewering, "engels": engels[0] if engels else "",
                    "oordelen": oordelen, "label": label or "", "truc": d["truc"], "vorm_artikel": d.get("vorm"),
                    "bevestigd": bevestigd})
    return uit


def _vragen(proef: int | None) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(ANTWOORDEN)
    klaar = {a["id"] for a in eerder if a.get("soort")}
    werk = [k for k in _jsonl(SET) if k["id"] not in klaar]
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

    def een(groep_: list[dict]) -> None:
        try:
            msg = client.messages.create(**soortverzoek(groep_))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for k, antwoord in zip(groep_, lees_soorten(tekst, len(groep_))):
                f.write(json.dumps({"id": k["id"], "versie": VERSIE, **(antwoord or {"vorm": None, "soort": None}),
                                    "kosten": round(kosten / len(groep_), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(ANTWOORDEN)
    print(f"{sum(bool(a.get('soort')) for a in nu)} gelezen; ${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def _rijen() -> list[dict]:  # pragma: no cover - bestanden
    antwoord = {a["id"]: a for a in _jsonl(ANTWOORDEN) if a.get("soort")}
    return [{**k, "soort": antwoord[k["id"]]["soort"], "vorm": antwoord[k["id"]]["vorm"]}
            for k in _jsonl(SET) if k["id"] in antwoord]


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["set", "vragen", "tellen", "lezen"])
    p.add_argument("--proef", type=int)
    a = p.parse_args()
    if a.stap == "set":
        rijen = _set()
        MAP.mkdir(parents=True, exist_ok=True)
        SET.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")
        print(f"{len(rijen)} factchecks, {sum(r['bevestigd'] is not None for r in rijen)} nagelezen, "
              f"{sum(bool(r['bevestigd']) for r in rijen)} bevestigd")
        return
    if a.stap == "vragen":
        return _vragen(a.proef)
    rijen = _rijen()
    if a.stap == "lezen":
        # wat ik lees: de bevestigde waar de bewering een andere soort gaf, en een willekeurige greep uit de rest
        mis = [r for r in rijen if r["bevestigd"] and groep(r["soort"]) and groep(r["soort"]) != groep(r["truc"])]
        rest = random.Random(ZAAD).sample(rijen, min(30, len(rijen)))
        uit = [{k: r[k] for k in ("id", "bewering", "engels", "oordelen", "label", "truc", "soort", "vorm")} for r in mis + rest]
        (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(MAP / "te-lezen.json", len(mis), "verschillen en", len(rest), "willekeurig")
        return
    t = telling(rijen)
    print(json.dumps({k: v for k, v in t.items()}, ensure_ascii=False, indent=1))
    print("de lat:", lat(t))
    print(f"${sum(x.get('kosten', 0.0) for x in _jsonl(ANTWOORDEN)):.3f}")


if __name__ == "__main__":  # pragma: no cover
    main()
