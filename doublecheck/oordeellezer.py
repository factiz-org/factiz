"""De oordelen die de tabel niet leest, gelezen voor het platform (PLAN #34.2o, DESIGNSYSTEEM §4).

13% van de pagina's staat op *Gecheckt*: de redactie gaf een oordeel, maar `verdicts.py` kent het niet. Soms is het een
taal die de tabel niet heeft (Singalees "අසත්‍යයි" is "onwaar"), soms vrije tekst ("Non. Plusieurs éléments permettent
d'établir que cette histoire ne tient pas la route"). De tabel raadt nooit, en dat blijft zo: hier stelt Haiku een
oordeel voor, met de regels van de tabel, en pas een leesproef laat het toe. Elke korte formulering krijgt daarbij een
letterlijke vertaling in de vijf talen van de site, zodat een bezoeker de woorden van de redactie kan lezen.

Het lab houdt zijn oordelen: de lezing geldt alleen in de publicatiedatabase, zoals de taallabels (33.5).

    python -m doublecheck.oordeellezer werk|vragen [--proef N]|lezen|tellen

Leest de nieuwste publicatiedatabase (openbare oordelen van redacties), alleen-lezen. Uitvoer in `data/oordelen/`;
mijn lezing in `docs/steekproeven/34.2o-oordelen.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "oordelen"
ANTWOORDEN = MAP / "antwoorden.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2o-oordelen.json"
VERSIE = "oordeel-lezer-v2"
# v1 las alleen de woorden van de redactie. Gestopt na 100 van de 200 gelezen: twee keer de verkeerde kant op, omdat
# vrije tekst pas iets zegt naast de bewering ("de voordelen van een biopsie wegen zwaarder" bij "een biopsie laat kanker
# uitzaaien" werd waar), en bij twee zinnen vertaalde het alleen het oordeelwoord. v2 krijgt de bewering erbij als de
# formulering zeldzaam is, en vertaalt elke zin.
MET_BEWERING = 3        # checks: tot hier is een formulering een eigen tekst bij één bewering, geen vast label
# De kantregel (na 150 gelezen in de ontwikkelset): elke fout naar de andere kant was een *waar* uit vrije tekst; het
# model beoordeelde de zin van de redactie ("bloed van een gevaccineerde is even veilig") in plaats van de bewering
# ("bloedtransfusies zijn gevaarlijk door de vaccins"). Uit vrije tekst tellen dus alleen deze oordelen; een *waar* of
# *deels waar* daaruit blijft *Gecheckt*. Twijfel versoepelt nooit.
KANT_VRIJ = frozenset({"onwaar", "misleidend", "onbewezen"})
SOORTEN = ("waar", "deels-waar", "misleidend", "onwaar", "onbewezen", "geen")
TALEN = ("en", "nl", "de", "es", "fr")
KORT = 80               # tekens: daaronder een formulering, daarboven vrije tekst
MAX_TEKENS = 600        # van vrije tekst in de vraag
MAX_GLOS = 120
PER_VRAAG = 20
DRADEN = 8
GRENS = 2.50            # dollar, v1 en v2 samen (v1 kostte $0,84)
SCHATTING = 0.00003     # per formulering, rechtstreeks
ZAAD = 34218            # v1 trok met 34215 en v2 eerst met 34217; wat daarvan gelezen is, is de ontwikkelset
PROEF_OORDELEN, PROEF_GLOSSEN = 200, 50
MAX_BUUR = 5            # fouten tussen buren plus twijfel
HARD = ("fout_kant", "fout_verzonnen")
ZACHT = ("fout_buur", "twijfel")
LABELS_GELDIG = ("goed",) + HARD + ZACHT


class Weigering(Exception):
    """De grens in dollars is bereikt, of er ontbreekt iets."""


def sleutel(tekst: str | None) -> str:
    """De formulering zoals ze geteld en opgezocht wordt: witruimte telt niet."""
    return " ".join((tekst or "").split())


def werkset(rijen) -> list[dict]:
    """Wat er gevraagd wordt, uit rijen (eigen woorden, oordeel van de tabel, adres van de check, aantal checks, een
    bewering waar ze bij horen): elke
    formulering die de tabel `onbekend` noemt (om haar oordeel), en elke korte formulering (om haar vertaling; het
    oordeel ernaast is dan alleen een maat voor het model). Wat de eigen lijst van een redactie geen oordeel noemt,
    gaat niet naar het model (`verdicts.geen_oordeel`)."""
    from doublecheck.evidence import _host
    from doublecheck.verdicts import geen_oordeel

    per: dict[str, dict] = {}
    for eigen, oordeel, url, aantal, bewering in rijen:
        tekst = sleutel(eigen)
        if not tekst or (oordeel == "onbekend" and geen_oordeel(tekst, _host(url))):
            continue
        w = per.setdefault(tekst, {"tekst": tekst, "kort": len(tekst) <= KORT, "tabel": None, "checks": 0,
                                   "bewering": sleutel(bewering), "_onbekend": False})
        w["checks"] += aantal
        if oordeel == "onbekend":
            w["_onbekend"] = True
        else:
            w["tabel"] = w["tabel"] or oordeel
    uit = []
    for w in per.values():
        onbekend = w.pop("_onbekend")
        if w["checks"] > MET_BEWERING:           # een vast label: de bewering van één check zou het model sturen
            w["bewering"] = None
        if onbekend and w["tabel"] is None or w["kort"]:
            uit.append(w)
    return sorted(uit, key=lambda w: (-w["checks"], w["tekst"]))


def verzoek(teksten: list[tuple]) -> dict:
    """Eén vraag over een rijtje formuleringen (tekst, kort, bewering of niets): welk oordeel trok de redactie over de
    bewering, en voor de korte een letterlijke vertaling van de hele tekst. De regels zijn die van de tabel in
    `verdicts.py`."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You read the verdicts that fact-checking newsrooms gave to claims, in any language, for a public archive. "
        "Each numbered item is the verdict text of a newsroom, and for a rare text also the claim it was about. Say "
        "what the newsroom concluded about the claim, with exactly one of these words:\n"
        "- waar: true, correct, accurate.\n"
        "- deels-waar: partly true, half true, mostly true, mostly false, mixed, exaggerated.\n"
        "- misleidend: misleading, missing context, out of context, an old photo or video shown as new.\n"
        "- onwaar: false, fake, fabricated, a hoax, doctored, altered or manipulated media, AI-generated material shown "
        "as real, satire presented as news.\n"
        "- onbewezen: unproven, unverified, no evidence either way.\n"
        "- geen: no verdict on the claim (an explainer, analysis or context note, a scale value without a legend such "
        "as \"1\" or \"3\", a rating of a change of position), or a text you cannot read with certainty.\n"
        "Judge the whole text, and read it against the claim when the claim is given: a text that only states facts "
        "still has a verdict if those facts show the claim to be true, false or misleading. If it starts with a verdict "
        "word and then qualifies it (\"True, but ...\"), give the qualified verdict. When in doubt, answer geen: a "
        "missing verdict is better than a wrong one.\n"
        "For a verdict marked [short], also give a literal translation of the whole verdict text, every sentence of it, "
        "into English (en), Dutch (nl), German (de), Spanish (es) and French (fr): translate all the words, add "
        "nothing, leave nothing out and explain nothing; if it is already in that language, repeat it. Never translate "
        "the claim. For the other verdicts, give empty strings.")
    glos = {"type": "object", "additionalProperties": False, "required": list(TALEN),
            "properties": {t: {"type": "string"} for t in TALEN}}
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "soort", "glos"],
            "properties": {"nr": {"type": "integer"}, "soort": {"type": "string", "enum": list(SOORTEN)}, "glos": glos}}}}}
    vraag = "\n".join(f"{i}.{' [short]' if w[1] else ''} Verdict: {w[0][:MAX_TEKENS]}"
                      + (f"\n   Claim: {w[2][:MAX_TEKENS]}" if len(w) > 2 and w[2] else "") for i, w in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 6000, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_antwoord(tekst: str | None, teksten: list[tuple]) -> list[dict | None]:
    """De antwoorden op een rijtje, op nummer. Een soort telt alleen als ze bekend is; een vertaling alleen bij een korte
    formulering en alleen als ze in alle vijf talen staat. Een nummer dat ontbreekt of twee keer voorkomt, telt niet."""
    n = len(teksten)
    uit: list[dict | None] = [None] * n
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        gezien = Counter(a.get("nr") for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return uit
    for a in antwoorden:
        nr = a.get("nr")
        if not (isinstance(nr, int) and 1 <= nr <= n and gezien[nr] == 1):
            continue
        soort = a.get("soort") if a.get("soort") in SOORTEN else None
        g = a.get("glos") if isinstance(a.get("glos"), dict) else {}
        glos = {t: sleutel(g.get(t))[:MAX_GLOS] for t in TALEN}
        uit[nr - 1] = {"soort": soort, "glos": glos if teksten[nr - 1][1] and all(glos.values()) and soort else None}
    return uit


def lezingen(antwoorden: list[dict], versie: str = VERSIE) -> dict[str, dict]:
    """Per formulering de laatste leesbare lezing van deze versie (een antwoord zonder versie telt als deze)."""
    return {a["tekst"]: a for a in antwoorden if a.get("soort") and a.get("versie", versie) == versie}


def telt(a: dict) -> bool:
    """Of een lezing naar de uitgave mag: een oordeel waar de tabel er geen had, en uit vrije tekst alleen een oordeel
    van `KANT_VRIJ`."""
    return (a["tabel"] is None and a["soort"] not in (None, "geen")
            and (a["checks"] > MET_BEWERING or a["soort"] in KANT_VRIJ))


def _gewogen(rijen: list[dict], n: int, kies: random.Random) -> list[str]:
    """`n` formuleringen zonder terugleggen, met een kans naar het aantal checks (Efraimidis en Spirakis)."""
    sleutels = sorted(((kies.random() ** (1 / max(1, r["checks"])), r["tekst"]) for r in sorted(rijen, key=lambda r: r["tekst"])),
                      reverse=True)
    return [t for _, t in sleutels[:n]]


def leesproef(antwoorden: list[dict], zaad: int = ZAAD, gezien: frozenset[str] = frozenset()) -> dict[str, list[str]]:
    """Wat ik lees: 200 formuleringen waarvan de lezing naar de uitgave zou gaan (`telt`; daar hangt de poort van de
    oordelen aan), getrokken naar het aantal checks, en 50 korte formuleringen met een oordeel uit de tabel en een
    vertaling (met de korte uit de 200 de poort van de vertalingen). Nooit wat ik al las in de ontwikkelset (`gezien`).
    Bij dezelfde antwoorden altijd dezelfde."""
    lezing = {t: a for t, a in lezingen(antwoorden).items() if t not in gezien}
    kies = random.Random(zaad)
    oordelen = _gewogen([a for a in lezing.values() if telt(a)], PROEF_OORDELEN, kies)
    gekozen = set(oordelen)
    glossen = _gewogen([a for a in lezing.values() if a["tabel"] and a.get("glos") and a["tekst"] not in gekozen],
                       PROEF_GLOSSEN, kies)
    return {"oordelen": oordelen, "glossen": glossen}


def poort(antwoorden: list[dict], pad: str | Path = LABELS) -> dict[str, tuple[bool, str]]:
    """Twee poorten. De oordelen: alle 200 gelezen, geen enkele fout naar de andere kant of verzonnen oordeel, en
    hoogstens 5 fouten tussen buren of twijfel. De vertalingen: elke vertaling in de proef gelezen, geen betekenisfout."""
    lezing = lezingen(antwoorden)
    try:
        d = json.loads(Path(pad).read_text(encoding="utf-8"))
        o_labels, g_labels = d.get("oordelen", {}), d.get("glossen", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {"oordelen": (False, "nog niets gelezen"), "glossen": (False, "nog niets gelezen")}
    proef = leesproef(antwoorden, gezien=frozenset(d.get("ontwikkeling", {})))
    gelezen = [o_labels.get(t) for t in proef["oordelen"]]
    if not proef["oordelen"]:
        p_o = (False, "niets om te lezen")
    elif any(l not in LABELS_GELDIG for l in gelezen):
        p_o = (False, f"{sum(l in LABELS_GELDIG for l in gelezen)} van de {len(gelezen)} gelezen")
    elif any(l in HARD for l in gelezen):
        p_o = (False, f"{sum(l in HARD for l in gelezen)} fout(en) naar de andere kant of verzonnen")
    elif sum(l in ZACHT for l in gelezen) > MAX_BUUR:
        p_o = (False, f"{sum(l in ZACHT for l in gelezen)} fouten tussen buren of twijfel, hoogstens {MAX_BUUR}")
    else:
        p_o = (True, f"{gelezen.count('goed')} van de {len(gelezen)} goed, {sum(l in ZACHT for l in gelezen)} buur of twijfel")
    met_glos = [t for t in proef["oordelen"] if lezing.get(t, {}).get("glos")] + proef["glossen"]
    g_gelezen = [g_labels.get(t) for t in met_glos]
    if not met_glos:
        p_g = (False, "niets om te lezen")
    elif any(l not in ("goed", "fout") for l in g_gelezen):
        p_g = (False, f"{sum(l in ('goed', 'fout') for l in g_gelezen)} van de {len(g_gelezen)} gelezen")
    elif "fout" in g_gelezen:
        p_g = (False, f"{g_gelezen.count('fout')} vertaling(en) fout")
    else:
        p_g = (True, f"{len(g_gelezen)} vertalingen goed")
    return {"oordelen": p_o, "glossen": p_g}


def voor_uitgave(antwoorden: list[dict], poorten: dict[str, tuple[bool, str]]) -> tuple[dict[str, str], dict[str, dict]]:
    """Wat de publicatiedatabase krijgt: per formulering die de tabel niet kende het gelezen oordeel (nooit *geen*, nooit
    over de tabel heen), en per korte formulering haar vertalingen; elk alleen als zijn poort open is."""
    lezing = lezingen(antwoorden)
    oordelen = {t: a["soort"] for t, a in lezing.items() if telt(a)} if poorten["oordelen"][0] else {}
    glossen = {t: a["glos"] for t, a in lezing.items() if a.get("glos")} if poorten["glossen"][0] else {}
    return oordelen, glossen


def geldige_lezingen() -> tuple[dict[str, str], dict[str, dict], dict]:  # pragma: no cover - bestanden
    antwoorden = _jsonl(ANTWOORDEN)
    poorten = poort(antwoorden)
    return (*voor_uitgave(antwoorden, poorten), poorten)


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _rijen() -> list[tuple[str, str, str, int]]:  # pragma: no cover - een bestand
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    return list(pub.execute("SELECT c.oordeel_eigen, c.oordeel, min(c.url), count(*), min(p.bewering) FROM check_ c "
                            "JOIN pagina p ON p.nummer = c.pagina "
                            "GROUP BY c.oordeel_eigen, c.oordeel, substr(c.url, 1, instr(substr(c.url, 9), '/') + 8)"))


def _vragen(proef: int | None) -> None:  # pragma: no cover - een model
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    werk = werkset(_rijen())
    eerder = _jsonl(ANTWOORDEN)
    klaar = {a["tekst"] for a in eerder if a.get("soort") and a.get("versie") == VERSIE}
    open_ = [w for w in werk if w["tekst"] not in klaar]
    if proef:
        open_ = random.Random(ZAAD).sample(open_, min(proef, len(open_)))
    groepen = [open_[i:i + PER_VRAAG] for i in range(0, len(open_), PER_VRAAG)]
    if not groepen:
        print("niets te vragen")
        return
    uitgegeven = sum(a.get("kosten", 0.0) for a in eerder)
    if uitgegeven + SCHATTING * len(open_) > GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} uitgegeven plus ${SCHATTING * len(open_):.2f} is meer dan ${GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[dict]) -> None:
        teksten = [(w["tekst"], w["kort"], w.get("bewering")) for w in groep]
        try:
            msg = client.messages.create(**verzoek(teksten))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, ANTWOORDEN.open("a", encoding="utf-8") as f:
            for w, a in zip(groep, lees_antwoord(tekst, teksten)):
                f.write(json.dumps({**w, "soort": (a or {}).get("soort"), "glos": (a or {}).get("glos"),
                                    "versie": VERSIE, "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, groepen))
    nu = _jsonl(ANTWOORDEN)
    print(f"{sum(bool(a.get('soort')) for a in nu)} beantwoord, {sum(not a.get('soort') for a in nu)} zonder antwoord; "
          f"${sum(a.get('kosten', 0.0) for a in nu):.3f} van ${GRENS:.2f}")


def _tellen() -> None:  # pragma: no cover - bestanden
    antwoorden = _jsonl(ANTWOORDEN)
    lezing = lezingen(antwoorden)
    if not lezing:
        print(f"nog geen lezingen van {VERSIE}")
        return
    nieuw = [a for a in lezing.values() if a["tabel"] is None]
    print(f"{len(lezing)} gelezen; zonder oordeel uit de tabel {len(nieuw)} formuleringen, "
          f"{sum(a['checks'] for a in nieuw)} checks")
    print("het model zegt:", Counter(a["soort"] for a in nieuw).most_common(),
          "| checks:", {s: sum(a["checks"] for a in nieuw if a["soort"] == s) for s in SOORTEN})
    bekend = [a for a in lezing.values() if a["tabel"]]
    if bekend:
        zelfde = sum(a["checks"] for a in bekend if a["soort"] == a["tabel"])
        print(f"met een oordeel uit de tabel: {len(bekend)} formuleringen; het model zegt hetzelfde bij "
              f"{sum(a['soort'] == a['tabel'] for a in bekend)} ({zelfde} van {sum(a['checks'] for a in bekend)} checks); "
              "anders:", Counter((a["tabel"], a["soort"]) for a in bekend if a["soort"] != a["tabel"]).most_common(10))
    print(f"vertaald: {sum(bool(a.get('glos')) for a in lezing.values())}; "
          f"${sum(a.get('kosten', 0.0) for a in antwoorden):.3f} van ${GRENS:.2f}")
    print("de poort:", poort(antwoorden))


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["werk", "vragen", "lezen", "tellen"])
    p.add_argument("--proef", type=int)
    a = p.parse_args()
    try:
        if a.stap == "werk":
            werk = werkset(_rijen())
            print(f"{len(werk)} formuleringen: {sum(w['tabel'] is None for w in werk)} zonder oordeel uit de tabel "
                  f"({sum(w['checks'] for w in werk if w['tabel'] is None)} checks), {sum(w['kort'] for w in werk)} kort; "
                  f"geschat ${SCHATTING * len(werk):.2f}")
        elif a.stap == "vragen":
            _vragen(a.proef)
        elif a.stap == "lezen":
            antwoorden = _jsonl(ANTWOORDEN)
            try:
                gezien = frozenset(json.loads(LABELS.read_text(encoding="utf-8")).get("ontwikkeling", {}))
            except OSError:
                gezien = frozenset()
            lezing, proef = lezingen(antwoorden), leesproef(antwoorden, gezien=gezien)
            uit = {soort: [{k: lezing[t].get(k) for k in ("tekst", "soort", "tabel", "checks", "glos")} for t in teksten]
                   for soort, teksten in proef.items()}
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", {k: len(v) for k, v in uit.items()})
        else:
            _tellen()
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
