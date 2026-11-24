"""De taal van een bewering nalopen voor het platform (PLAN #33.5, SPECS E9.S3).

In het lab komt de taal van een bewering uit `taal.corpus_taal` (py3langid op de tekst). Op korte zinnen met namen gaat
dat soms mis: Portugees wordt Spaans of Galicisch, Engels wordt Indonesisch, Assamees wordt Bengaals. Een verkeerd
label geeft op het platform een verkeerde taal in de pagina, in het filter en bij een vertaling. Een regel per site kan
een fout niet scheiden van een echte minderheidstaal (Kannada bij een Indiase redactie is echt, Spaans bij een
Braziliaanse niet), dus krijgt elke bewering met een verdacht label een tweede lezing van Haiku, zonder het oude label
erbij. De correcties gelden alleen in de publicatiedatabase en pas na een leesproef; het lab houdt zijn labels (een
taalwissel daar raakt de cijfers per markt, B14).

    python -m doublecheck.taallabels kandidaten|vragen [--proef N]|lezen|tellen

Leest de publicatiedatabase (openbare beweringen), alleen-lezen. Uitvoer in `data/talen/labels/`; mijn lezing in
`docs/steekproeven/33.5-taallabels.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "talen" / "labels"
ANTWOORDEN = MAP / "antwoorden.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "33.5-taallabels.json"
VERSIE = "taal-v1"
GRENS = 0.50            # dollar
SCHATTING = 0.00004     # per bewering, direct gevraagd, tien per vraag
PER_VRAAG = 10
DRADEN = 8
ZAAD = 3350
MAX_TEKENS = 300        # van een bewering in de vraag: genoeg om de taal te zien
ALTIJD = frozenset({"und", "gl", ""})   # onbekend, en het label waar de leesproef van B32 een fout vond
ZELDZAAM = 0.10         # een label onder dit aandeel bij de eigen site is verdacht
MIN_SITE = 50           # een site met minder pagina's zegt niets over wat zeldzaam is
PROEF_N, PROEF_ONGEWIJZIGD, PROEF_AANDEEL = 100, 50, 0.95
# De codes van ISO 639-1.
CODES = frozenset("""aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz
ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja
jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng
nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw
ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu""".split())


class Weigering(Exception):
    """De grens in dollars is bereikt, of er ontbreekt iets."""


def kandidaten(rijen: list[tuple[str, str, str]], zeldzaam: float = ZELDZAAM, min_site: int = MIN_SITE) -> set[str]:
    """De nummers met een verdacht label, uit rijen (nummer, taal, site): onbekend of Galicisch, of een taal die bij
    de eigen site zeldzaam is. Verdacht is geen fout: het is wie een tweede lezing krijgt."""
    per_site: dict[str, Counter] = defaultdict(Counter)
    for _, taal, site in rijen:
        per_site[site][taal] += 1
    uit = set()
    for nummer, taal, site in rijen:
        totaal = sum(per_site[site].values())
        if taal in ALTIJD or (totaal >= min_site and per_site[site][taal] / totaal < zeldzaam):
            uit.add(nummer)
    return uit


def taalverzoek(teksten: list[str]) -> dict:
    """Eén vraag over een rijtje teksten: in welke taal is elk geschreven. Het oude label gaat niet mee."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You identify the language of short texts for a public archive of fact-checked claims. For each numbered text, "
        'answer with the ISO 639-1 two-letter code of the language it is written in (for example "en", "pt", "hi").\n'
        "- Judge by the words and the grammar of the text itself, not by the names of people or places in it.\n"
        "- Take care with close pairs: Portuguese, Spanish and Galician; Indonesian and Malay; Assamese and Bengali; "
        "Hindi, Marathi and Nepali; Persian and Urdu.\n"
        "- If a text mixes two languages, give the language of most of its words.\n"
        '- If the text has no words of any language (only a name, a number or a link), or its language has no '
        'two-letter code, answer "und".')
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "taal"],
            "properties": {"nr": {"type": "integer"}, "taal": {"type": "string"}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())[:MAX_TEKENS]}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 1500, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_talen(tekst: str | None, n: int) -> list[str | None]:
    """De antwoorden op een rijtje van `n` teksten, op nummer: alleen een bekende code of `und` telt. Een nummer dat
    ontbreekt of twee keer voorkomt, telt niet."""
    uit: list[str | None] = [None] * n
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        gezien = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr, taal = a.get("nr"), str(a.get("taal") or "").strip().lower()
        if isinstance(nr, int) and 1 <= nr <= n and gezien[nr] == 1 and (taal in CODES or taal == "und"):
            uit[nr - 1] = taal
    return uit


def correcties(antwoorden: list[dict]) -> dict[str, str]:
    """Per nummer de taal volgens het model, alleen waar die leesbaar is en afwijkt van het label."""
    return {a["nummer"]: a["taal"] for a in antwoorden if a.get("taal") and a["taal"] != a.get("was")}


def leesproef(antwoorden: list[dict], zaad: int = ZAAD) -> dict[str, list[str]]:
    """De nummers die nagelezen worden: honderd willekeurige waar het model het label wijzigde (daar hangt de poort
    aan) en vijftig waar het het label liet staan. Bij dezelfde antwoorden altijd dezelfde."""
    gewijzigd = sorted(correcties(antwoorden))
    rest = sorted({a["nummer"] for a in antwoorden if a.get("taal")} - set(gewijzigd))
    kies = random.Random(zaad)
    return {"gewijzigd": kies.sample(gewijzigd, min(PROEF_N, len(gewijzigd))),
            "ongewijzigd": kies.sample(rest, min(PROEF_ONGEWIJZIGD, len(rest)))}


def poort(antwoorden: list[dict], pad: str | Path = LABELS) -> tuple[bool, str]:
    """Mogen de correcties in de uitgave? Alleen als van de honderd nagelezen wijzigingen er minstens 95 kloppen;
    twijfel telt als fout."""
    proef = leesproef(antwoorden)["gewijzigd"]
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
        gelezen = [labels[nr] for nr in proef if labels.get(nr) in ("goed", "fout", "twijfel")]
    except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
        return False, "nog niets gelezen"
    if not proef:
        return False, "geen wijzigingen om te lezen"
    if len(gelezen) < len(proef):
        return False, f"{len(gelezen)} van de {len(proef)} gelezen"
    goed, nodig = sum(w == "goed" for w in gelezen), math.ceil(PROEF_AANDEEL * len(proef))
    if goed < nodig:
        return False, f"{goed} van de {len(proef)} goed, de eis is {nodig}"
    return True, f"{goed} van de {len(proef)} goed"


def geldige_correcties() -> tuple[dict[str, str], str]:  # pragma: no cover - bestanden
    """De correcties voor de publicatiedatabase, of geen als de leesproef ze niet draagt; met de reden."""
    antwoorden = _jsonl(ANTWOORDEN)
    open_, reden = poort(antwoorden)
    return (correcties(antwoorden) if open_ else {}), reden


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _site(url: str) -> str:
    host = urlsplit(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _rijen() -> dict[str, tuple[str, str, str]]:  # pragma: no cover - een bestand
    """Elke bewering in de nieuwste uitgave: nummer -> (tekst, taal, site van de eerste check van haar pagina)."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    site = {nr: _site(url) for nr, url in pub.execute("SELECT pagina, url FROM check_ WHERE volg = 0")}
    uit = {nr: (tekst, taal, site.get(nr, "")) for nr, tekst, taal in pub.execute("SELECT nummer, bewering, taal FROM pagina")}
    for pagina, nr, tekst, taal in pub.execute("SELECT pagina, nummer, tekst, taal FROM formulering"):
        uit.setdefault(nr, (tekst, taal, site.get(pagina, "")))
    return uit


def _vragen(proef: int | None) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    rijen = _rijen()
    eerder = _jsonl(ANTWOORDEN)
    klaar = {a["nummer"] for a in eerder if a.get("taal")}
    # wie al een antwoord heeft, hoort erbij: na een uitgave met correcties is haar label niet meer verdacht
    verdacht = sorted((kandidaten([(nr, taal, site) for nr, (_, taal, site) in rijen.items()]) | klaar) - klaar)
    if proef:
        verdacht = random.Random(ZAAD).sample(verdacht, min(proef, len(verdacht)))
    werk = [verdacht[i:i + PER_VRAAG] for i in range(0, len(verdacht), PER_VRAAG)]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(a.get("kosten", 0.0) for a in eerder)
    if uitgegeven + SCHATTING * len(verdacht) > GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} uitgegeven plus ${SCHATTING * len(verdacht):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[str]) -> None:
        try:
            msg = client.messages.create(**taalverzoek([rijen[nr][0] for nr in groep]))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for nr, taal in zip(groep, lees_talen(tekst, len(groep))):
                f.write(json.dumps({"nummer": nr, "was": rijen[nr][1], "taal": taal, "versie": VERSIE,
                                    "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, werk))
    nu = _jsonl(ANTWOORDEN)
    print(f"{sum(bool(a.get('taal')) for a in nu)} beantwoord, {sum(not a.get('taal') for a in nu)} zonder antwoord; "
          f"{len(correcties(nu))} wijzigingen; ${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["kandidaten", "vragen", "lezen", "tellen"])
    p.add_argument("--proef", type=int)
    a = p.parse_args()
    try:
        if a.stap == "vragen":
            return _vragen(a.proef)
        rijen = _rijen()
        if a.stap == "kandidaten":
            verdacht = kandidaten([(nr, taal, site) for nr, (_, taal, site) in rijen.items()])
            print(f"{len(verdacht)} van {len(rijen)} beweringen met een verdacht label")
            print("per label:", Counter(rijen[nr][1] for nr in verdacht).most_common(20))
            print("per site:", Counter(rijen[nr][2] for nr in verdacht).most_common(12))
            return
        antwoorden = _jsonl(ANTWOORDEN)
        laatste = {x["nummer"]: x for x in antwoorden if x.get("taal")}
        proef = leesproef(antwoorden)
        if a.stap == "lezen":
            uit = {soort: [{"nummer": nr, "was": laatste[nr]["was"], "taal": laatste[nr]["taal"], "site": rijen[nr][2],
                            "tekst": rijen[nr][0][:MAX_TEKENS]} for nr in nummers if nr in rijen]
                   for soort, nummers in proef.items()}
            MAP.mkdir(parents=True, exist_ok=True)
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", {k: len(v) for k, v in uit.items()})
            return
        wijzig = correcties(antwoorden)
        print(f"{len(laatste)} beantwoord; {len(wijzig)} wijzigingen; ${sum(x.get('kosten', 0.0) for x in antwoorden):.3f}")
        print("van -> naar:", Counter((laatste[nr]["was"], t) for nr, t in wijzig.items()).most_common(25))
        print("de poort:", poort(antwoorden))
        try:
            d = json.loads(LABELS.read_text(encoding="utf-8"))
            rest = [d.get("ongewijzigd", {}).get(nr) for nr in proef["ongewijzigd"]]
            print(f"ongewijzigd nagelezen: {sum(w is not None for w in rest)} van {len(rest)}, "
                  f"waarvan fout of twijfel {sum(w in ('fout', 'twijfel') for w in rest)}")
        except (OSError, json.JSONDecodeError):
            pass
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
