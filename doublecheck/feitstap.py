"""De feitenstap vóór de waarheidsmeter (B44, PLAN #31.9).

Stand 10 (*vastgesteld feit*) en stand 0 (*in strijd met een vastgesteld feit*)
mogen alleen naar buiten na nul fouten op de kern en de minimale paren. De
feitenstap koppelt een bericht aan een feit uit de feitenbasis (B34): eerst
lokaal de drie dichtstbijzijnde feiten ophalen (bge-m3, over de laagformuleringen
en de zin van elk feit), dan één kort oordeel van Sonnet: bevestigt het bericht
een van die feiten, spreekt het er een tegen, of geen van beide. De vastgezette
machine (vraag v4) verandert niet.

De meetset ligt vast vóór de eerste vraag (PLAN #31.9): de poortformuleringen
van de kern (K), valse varianten (V), ware verwante zinnen (W), samengestelde
berichten (S), de minimale paren (Pw, Pn) en ongerelateerde berichten (O).
V, W en S schrijft Haiku 5.5; elke zin is gelezen voordat hij meedoet. Een
K die op 10 komt bij zijn eigen feit is goed volgens de vaste regel; elke andere
0 of 10, en elke K die niet op 10 kwam, wordt gelezen voordat hij telt.

`feitstap-v2` (§152, PO 2026-10-26): de vloer op 0,55, en *bevestigt* alleen als
het bericht geen eigen datum, tijdstip, getal, naam of plaats toevoegt. Gemeten op
nieuwe delen (K2, V2, Dw en Dn: het feit met een waar of vals eigen detail, O2) en
nog eens op de delen van v1, als controle.

`feitstap-v3` (§153, PO 2026-10-26, de laatste ronde): twee sleutels. A is de vraag
van v2, B dezelfde vraag met de feiten omgekeerd en het waarom in het Engels; 0 en
10 alleen als beide hetzelfde zeggen. Een gemiste tien telt apart van een
verkeerde stand. Nieuwe delen K3, V3, W3, Dw3, Dn3 en O3.

    python -m doublecheck.feitstap varianten indienen|ophalen|lezen [--versie v1|v2]
    python -m doublecheck.feitstap set
    python -m doublecheck.feitstap laag
    python -m doublecheck.feitstap indienen [--proef 10]|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from doublecheck.feitvraag import (  # noqa: F401 - verhuisd naar de kern (PLAN #32.7c)
    KERN,
    N_KANDIDATEN,
    SLEUTELS,
    SYSTEEM,
    VERSIE,
    VLOER,
    VRAAG,
    VRAAG_V2,
    VRAAG_V3B,
    _SCHEMA,
    _index,
    _verzoek,
    kandidaten,
    lees_feitoordeel,
    twee_sleutels,
    verzoek_id,
    volgorde,
    vraag,
    zinnen_van_feiten,
)

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "feitstap"
SET = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-set.json"
LABELS = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-labels.json"
SET_V2 = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-v2-set.json"
LABELS_V2 = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-v2-labels.json"
SET_V3 = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-v3-set.json"
LABELS_V3 = WORTEL / "docs" / "steekproeven" / "31.9-feitstap-v3-labels.json"
VARIANT_VERSIE = "feitstap-varianten-v1"
VARIANT_VERSIE_V2 = "feitstap-varianten-v2"
VARIANT_VERSIE_V3 = "feitstap-varianten-v3"
BUDGET = 5.0  # PO 2026-10-26: "grens $5"
ZAAD = 3190
N_ONGERELATEERD = 300
MAX_TEKENS = 1_200
TALEN_ANDERS = ("es", "pt", "it", "tr", "id", "ar")
_TAALNAAM = {"es": "Spanish", "pt": "Portuguese", "it": "Italian", "tr": "Turkish", "id": "Indonesian",
             "ar": "Arabic"}
DELEN = ("K", "K2", "K3", "V", "V2", "V3", "W", "W3", "S", "Dw", "Dw3", "Dn", "Dn3", "Pw", "Pn", "O", "O2", "O3")
KERNDELEN = ("K", "K2", "K3")
WAAR_DETAIL = ("Dw", "Dw3")


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


# --- ophalen ---------------------------------------------------------------------------


# --- het oordeel -----------------------------------------------------------------------


def stand_van(richting: str) -> int | None:
    return {"bevestigt": 10, "spreekt tegen": 0}.get(richting)


def uit_verzoek_id(custom_id: str) -> tuple[str, str]:
    stuk_id, _, sleutel = custom_id.rpartition("__")
    return stuk_id, sleutel


# --- tellen ----------------------------------------------------------------------------

def telling(stukken: list[dict], antwoorden: dict[str, dict], labels: dict[str, str],
            missers_apart: bool = False) -> dict:
    """Per deel en samen: hoeveel op 10, hoeveel op 0, en de fouten. Een K of K2
    die op 10 komt bij zijn eigen feit is goed (vaste regel), en een Dw (waar
    eigen detail) op 10 bij zijn eigen feit is geen fout maar telt mee in *op 10*.
    Elke andere 0 of 10, en elke K of K2 die niet op 10 kwam, heeft een label
    nodig: *terecht*, *fout* of *set fout* (de zin zelf deugt niet; telt apart).
    Weigert zolang er een ontbreekt. `missers_apart` (v3): een kernformulering
    op *geen* is een gemiste tien, telt zonder label en nooit als fout; een 0 of
    10 bij een ander feit blijft een verkeerde stand met label."""
    uit: dict = {}
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        stand = stand_van(a["richting"])
        vrij = s["deel"] in KERNDELEN + WAAR_DETAIL and a["richting"] == "bevestigt" and a.get("feit") == s["feit"]
        mis = missers_apart and s["deel"] in KERNDELEN and stand is None
        label = labels.get(s["id"])
        if (stand is not None or s["deel"] in KERNDELEN) and not (vrij or mis) and label is None:
            raise Weigering(f"{s['id']} ({s['deel']}, stand {stand}) heeft geen label; eerst lezen")
        for groep in (s["deel"], "totaal"):
            h = uit.setdefault(groep, {"n": 0, "op 10": 0, "op 0": 0, "fouten": 0, "set fout": 0}
                               | ({"gemist": 0} if missers_apart else {}))
            if label == "set fout" and not mis:
                h["set fout"] += 1
                continue
            h["n"] += 1
            h["op 10"] += stand == 10
            h["op 0"] += stand == 0
            h["fouten"] += label == "fout" and not mis
            if missers_apart:
                h["gemist"] += mis
    return uit


# --- met de bestanden, het model en de API ---------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in Path(pad).read_text(encoding="utf-8").splitlines() if x.strip()] \
        if Path(pad).exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")


VARIANT_VRAAG = """Here is an established fact:
"{zin}"

Write test sentences for a fact-checking system:
- "vals_en": 4 short English sentences that each contradict this fact by changing exactly one thing: (1) the date or year, (2) the place or the actor, (3) a number or size, (4) the opposite claim. Each must be clearly false, not vague, and must not be true in another reading. If the fact has no date or number, change another concrete detail instead.
- "vals_anders": 2 such false sentences, different from each other, written in {taal}.
- "waar_verwant": 2 short English sentences that are true and well established, about the same topic, but that state a different fact: not a paraphrase of this fact and not its opposite.
- "samengesteld": 1 English message that states this fact correctly as a lead-in and then makes a different main claim, such as an unrelated conspiracy claim or an opinion.
Write only the sentences, without explanations."""
_VARIANT_SCHEMA = {"type": "object", "properties": {
    "vals_en": {"type": "array", "items": {"type": "string"}},
    "vals_anders": {"type": "array", "items": {"type": "string"}},
    "waar_verwant": {"type": "array", "items": {"type": "string"}},
    "samengesteld": {"type": "array", "items": {"type": "string"}}},
    "required": ["vals_en", "vals_anders", "waar_verwant", "samengesteld"], "additionalProperties": False}


VARIANT_VRAAG_V2 = """Here is an established fact:
"{zin}"

Write test sentences for a fact-checking system:
- "kern": 8 sentences that each state exactly this fact in other words, as a person might write it: (1) a plain English sentence, (2) an English social media post of one or two sentences, then one sentence each in Spanish, Portuguese, Italian, Turkish, Indonesian and Arabic, in that order. Do not copy the fact word for word. A sentence may leave out a detail of the fact, but must not add a date, time, number, name or place that the fact does not state, and must not change anything.
- "vals_en": 4 short English sentences that each contradict this fact by changing exactly one thing: (1) the date or year, (2) the place or the actor, (3) a number or size, (4) the opposite claim. Each must be clearly false, not vague, and must not be true in another reading. If the fact has no date or number, change another concrete detail instead.
- "vals_anders": 2 such false sentences, different from each other, written in {taal}.
- "detail_waar": 2 English sentences that state this fact correctly and add one extra concrete detail that the fact does not state (a date, a time of day, a number, a name or a place). The added detail must be true and well established.
- "detail_vals": 2 English sentences that state this fact correctly and add one extra concrete detail that the fact does not state. The added detail must be clearly false, and must not change anything the fact itself states.
Write only the sentences, without explanations."""
_VARIANT_SCHEMA_V2 = {"type": "object", "properties": {
    soort: {"type": "array", "items": {"type": "string"}}
    for soort in ("kern", "vals_en", "vals_anders", "detail_waar", "detail_vals")},
    "required": ["kern", "vals_en", "vals_anders", "detail_waar", "detail_vals"], "additionalProperties": False}
_KERN_TALEN = ("en", "en", "es", "pt", "it", "tr", "id", "ar")
VARIANT_VRAAG_V3 = """Here is an established fact:
"{zin}"

Sentences already written for this fact (do not repeat them and do not paraphrase them closely):
{gebruikt}

Write new test sentences for a fact-checking system:
- "kern": 8 sentences that each state exactly this fact, worded differently from the sentences above, as people write in messages and posts: (1) an English news headline, (2) an English chat message, then one sentence each in Spanish, Portuguese, Italian, Turkish, Indonesian and Arabic, in that order, each worded differently from a literal translation of the fact. A sentence may leave out a detail of the fact, but must not add a date, time, number, name or place that the fact does not state, and must not change anything.
- "vals_en": 4 short English sentences that each contradict this fact in another way than the false sentences above: (1) a wrong date or year, (2) a wrong place or actor, (3) a wrong number or size, (4) the fact presented as a myth or a lie. Each must be clearly false, not vague, and must not be true in another reading. If the fact has no date or number, change another concrete detail instead.
- "vals_anders": 2 such false sentences, different from each other, written in {taal}.
- "waar": 3 short sentences that are true and well established, about the same topic, but that state a different fact than this one: not a paraphrase of this fact and not its opposite. Two in English (one of them with a date or a number), and one in {taal_een}.
- "detail_waar": 2 English sentences that state this fact correctly and add one extra concrete detail that the fact does not state (a date, a time of day, a number, a name or a place), other than the details above. The added detail must be true and well established.
- "detail_vals": 2 English sentences that state this fact correctly and add one extra concrete detail that the fact does not state, other than the details above. The added detail must be clearly false, and must not change anything the fact itself states.
Write only the sentences, without explanations."""
_VARIANT_SCHEMA_V3 = {"type": "object", "properties": {
    soort: {"type": "array", "items": {"type": "string"}}
    for soort in ("kern", "vals_en", "vals_anders", "waar", "detail_waar", "detail_vals")},
    "required": ["kern", "vals_en", "vals_anders", "waar", "detail_waar", "detail_vals"], "additionalProperties": False}
# Per versie de nieuwe delen: (deel, soort in het antwoord van Haiku, talen naar positie).
_NIEUWE_DELEN = {
    "v2": (("K2", "kern", "kern"), ("V2", "vals_en", "en"), ("V2", "vals_anders", "anders"),
           ("Dw", "detail_waar", "en"), ("Dn", "detail_vals", "en")),
    "v3": (("K3", "kern", "kern"), ("V3", "vals_en", "en"), ("V3", "vals_anders", "anders"),
           ("W3", "waar", "waar"), ("Dw3", "detail_waar", "en"), ("Dn3", "detail_vals", "en")),
}

VERSIES = {
    "v1": {**KERN["v1"], "uit": UIT, "set": SET, "labels": LABELS,
           "budget": BUDGET, "variant_versie": VARIANT_VERSIE, "variant_vraag": VARIANT_VRAAG,
           "variant_schema": _VARIANT_SCHEMA, "taal_schuif": 0},
    # PO 2026-10-26: "bouw feitstap-v2 [...] (vloer 0,55, strengere regel voor bevestigt) [...] grens $3."
    "v2": {**KERN["v2"], "uit": UIT / "v2", "set": SET_V2,
           "labels": LABELS_V2, "budget": 3.0, "variant_versie": VARIANT_VERSIE_V2,
           "variant_vraag": VARIANT_VRAAG_V2, "variant_schema": _VARIANT_SCHEMA_V2, "taal_schuif": 1},
    # PO 2026-10-26: "twee sleutels, verkeerde standen en gemiste tienen apart [...] grens $5. Dit is de laatste ronde."
    "v3": {**KERN["v3"], "uit": UIT / "v3",
           "set": SET_V3, "labels": LABELS_V3, "budget": 5.0, "variant_versie": VARIANT_VERSIE_V3,
           "variant_vraag": VARIANT_VRAAG_V3, "variant_schema": _VARIANT_SCHEMA_V3, "taal_schuif": 2},
}
_PER_VERZOEK = {"feitstap-v1": 0.004, "feitstap-v2": 0.0015, "feitstap-v3": 0.0013}  # v2 kostte $0,0012 per verzoek


def taal_voor(i: int) -> tuple[str, str]:
    """De twee andere talen voor de valse varianten van het i-de feit, om de beurt."""
    return TALEN_ANDERS[(2 * i) % len(TALEN_ANDERS)], TALEN_ANDERS[(2 * i + 1) % len(TALEN_ANDERS)]


def nieuwe_zinnen(rijen: list[dict], volgorde: dict[str, int], versie: str) -> list[dict]:
    """De zinnen van Haiku (v2: K2, V2, Dw, Dn; v3: K3, V3, W3, Dw3, Dn3), met taal
    naar positie; nog zonder oordeel. `volgorde`: het nummer van elk feit in de kern."""
    teller: dict[str, int] = {}
    uit = []
    for r in sorted(rijen, key=lambda r: volgorde[r["feit"]]):
        anders = taal_voor(volgorde[r["feit"]] + VERSIES[versie]["taal_schuif"])
        talen = {"kern": _KERN_TALEN, "anders": anders, "waar": ("en", "en", anders[0])}
        for deel, soort, taalsoort in _NIEUWE_DELEN[versie]:
            for j, tekst in enumerate(r[soort]):
                rij_talen = talen.get(taalsoort, ())
                n = teller[deel] = teller.get(deel, -1) + 1
                uit.append({"id": f"{deel}-{n:03d}", "deel": deel, "feit": r["feit"],
                            "taal": "en" if taalsoort == "en" else rij_talen[j] if j < len(rij_talen) else "?",
                            "soort": soort, "tekst": tekst})
    return uit


def zinnen_v2(rijen: list[dict], volgorde: dict[str, int]) -> list[dict]:
    return nieuwe_zinnen(rijen, volgorde, "v2")


def kern_items(kern: list[dict]) -> list[dict]:
    """K: de poortformuleringen, die de laag nooit zag."""
    uit = []
    for feit in kern:
        for f in feit["formuleringen"]:
            if f.get("rol") == "poort":
                uit.append({"id": f"K{len(uit):04d}", "deel": "K", "feit": feit["id"], "taal": f["taal"],
                            "tekst": f["tekst"], "bron": "kern"})
    return uit


def paar_items(paren: list[dict]) -> list[dict]:
    """Pw en Pn: de ware en de valse zin van elk minimaal paar."""
    uit = []
    for i, p in enumerate(paren):
        uit.append({"id": f"Pw{i:03d}", "deel": "Pw", "feit": p["feit"], "taal": "en", "tekst": p["waar"],
                    "bron": f"wikipedia:{p['revid']}"})
        uit.append({"id": f"Pn{i:03d}", "deel": "Pn", "feit": p["feit"], "taal": "en", "tekst": p["nep"],
                    "bron": f"wikipedia:{p['revid']}"})
    return uit


def gekozen_varianten(pad: Path = SET, bron: str = VARIANT_VERSIE) -> list[dict]:
    """V, W en S (v2: K2, V2, Dw, Dn): de gelezen en goedgekeurde zinnen uit het setbestand."""
    if not Path(pad).exists():
        return []
    return [{k: z[k] for k in ("id", "deel", "feit", "taal", "tekst")} | {"bron": bron}
            for z in json.loads(Path(pad).read_text(encoding="utf-8"))["zinnen"] if z["oordeel"] == "goed"]


def ongerelateerd(deel: str = "O", n: int = N_ONGERELATEERD,
                  zaad: int = ZAAD) -> list[dict]:  # pragma: no cover - op de rondes
    """O: berichten uit de rondes 4, 6 en 7, zonder kern, paren en evergreens.
    O2: n andere (v2); O3: de rest, die nog in geen set zat (v3)."""
    from doublecheck import verificatie as v

    gezien, pool = set(), []
    for ronde in (4, 6, 7):
        for s in v.gekozen_stukken(ronde):
            if s["soort"] == "beeld" or s.get("bron") in ("n3-kern", "n3-paar", "evergreen") or s["id"] in gezien:
                continue
            gezien.add(s["id"])
            pool.append(s)
    pool.sort(key=lambda s: s["id"])
    o = random.Random(zaad).sample(pool, n)
    rest = [s for s in pool if s["id"] not in {x["id"] for x in o}]
    o2 = random.Random(zaad + 1).sample(rest, n)
    gekozen = {"O": o, "O2": o2, "O3": [s for s in rest if s["id"] not in {x["id"] for x in o2}]}[deel]
    return [{"id": f"{deel}{'' if deel == 'O' else '-'}{i:03d}", "deel": deel, "feit": None, "taal": s.get("taal"),
             "tekst": " ".join((s.get("tekst") or "").split())[:MAX_TEKENS], "bron": s["id"]}
            for i, s in enumerate(gekozen)]


def maak_set(v: dict = VERSIES["v1"]) -> list[dict]:  # pragma: no cover - met het model
    """Alle stukken met hun kandidaten, één keer, in `set.jsonl` van de versie.
    v2 meet de delen van v1 opnieuw en de nieuwe delen erbij."""
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.feitenbasis import lees_kern, lees_paren

    eerder = list(VERSIES.values())[: list(VERSIES.values()).index(v) + 1]
    if not all(Path(w["set"]).exists() for w in eerder):
        raise SystemExit(f"eerst de varianten lezen en {Path(v['set']).name} schrijven")
    varianten = [z for w in eerder for z in gekozen_varianten(w["set"], w["variant_versie"])]
    stukken = kern_items(lees_kern()) + varianten + paar_items(lees_paren()) + ongerelateerd()
    stukken += [s for deel in ("O2", "O3")[: len(eerder) - 1] for s in ongerelateerd(deel)]
    index, versie = _index()
    vingers = fingerprint_texts([s["tekst"] for s in stukken], versie)
    for s, fp in zip(stukken, vingers):
        s["kandidaten"] = [[f, round(g, 4)] for f, g in kandidaten(fp.vector, index, v["vloer"])]
    _schrijf(v["uit"] / "set.jsonl", stukken)
    return stukken


def lees_set(uit: Path = UIT) -> list[dict]:
    return _jsonl(uit / "set.jsonl")


def laag_route(stukken: list[dict], uit: Path = UIT) -> None:  # pragma: no cover - met het model en de rechter
    """De lokale feitenlaag (`feitenlaag.herken`) op elk stuk, ter vergelijking."""
    from doublecheck import feitenlaag
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts

    config = load_config(None)
    vingers = fingerprint_texts([s["tekst"] for s in stukken], config.model_versions.text_embedding)
    rijen = []
    for s, fp in zip(stukken, vingers):
        h = feitenlaag.herken(s["tekst"], fp, config)
        rijen.append({"id": s["id"], "feit": h.feit if h else None, "score": round(h.score, 4) if h else None})
    _schrijf(uit / "laag.jsonl", rijen)


def _kosten(msg, model: str) -> float:  # pragma: no cover
    from doublecheck.leraar import MODELLEN

    m = MODELLEN[model]
    return (msg.usage.input_tokens * m["in"] + msg.usage.output_tokens * m["uit"]) / 1e6


def al_uitgegeven(uit: Path = UIT) -> float:
    """Wat er voor deze versie is ingediend: van een afgeronde batch het werkelijke
    bedrag, van een lopende de schatting."""
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
               for naam in ("varianten-batches.jsonl", "batches.jsonl", "batches-vervangen.jsonl")
               for b in _jsonl(Path(uit) / naam))


def antwoorden_sonnet(stukken: list[dict], uit: Path = UIT) -> dict[str, dict]:
    """Per stuk de richting en het feit; zonder kandidaat geen vraag, dus *geen*."""
    gelezen = {r["id"]: r for r in _jsonl(uit / "antwoorden.jsonl")}
    uit = {}
    for s in stukken:
        if not s.get("kandidaten"):
            uit[s["id"]] = {"richting": "geen", "feit": None}
        elif s["id"] in gelezen:
            uit[s["id"]] = gelezen[s["id"]]
    return uit


def antwoorden_sleutel(stukken: list[dict], uit: Path, sleutel: str, terug: Path | None = None) -> dict[str, dict]:
    """Per stuk het antwoord van één sleutel (v3). Voor A tellen ook de antwoorden van
    v2 (`terug`): dezelfde vraag. Zonder kandidaat geen vraag, dus *geen*."""
    gelezen = {r["id"]: r for r in _jsonl(terug / "antwoorden.jsonl")} if terug else {}
    gelezen |= {r["id"]: r for r in _jsonl(uit / "antwoorden.jsonl") if r.get("sleutel", "A") == sleutel}
    uit_ = {}
    for s in stukken:
        if not s.get("kandidaten"):
            uit_[s["id"]] = {"richting": "geen", "feit": None}
        elif s["id"] in gelezen:
            uit_[s["id"]] = gelezen[s["id"]]
    return uit_


def antwoorden_laag(stukken: list[dict], uit: Path = UIT) -> dict[str, dict]:
    laag = {r["id"]: r for r in _jsonl(uit / "laag.jsonl")}
    return {s["id"]: {"richting": "bevestigt" if laag[s["id"]]["feit"] else "geen", "feit": laag[s["id"]]["feit"]}
            for s in stukken if s["id"] in laag}


def antwoorden_beide(sonnet: dict[str, dict], laag: dict[str, dict]) -> dict[str, dict]:
    """10 alleen als Sonnet en de laag hetzelfde feit bevestigen; 0 komt van Sonnet."""
    uit = {}
    for i, a in sonnet.items():
        b = laag.get(i)
        if a["richting"] == "bevestigt" and not (b and b["feit"] == a["feit"]):
            uit[i] = {"richting": "geen", "feit": None}
        else:
            uit[i] = a
    return uit


def labels_voor(antwoorden: dict[str, dict], paden: tuple[Path, ...] = (LABELS,)) -> dict[str, str]:
    """De labels die bij precies deze uitkomst horen (stand en feit). Het eerste
    bestand gaat voor: in v2 houdt een uitkomst die gelijk is aan v1 haar label."""
    uit: dict[str, str] = {}
    for pad in paden:
        if not Path(pad).exists():
            continue
        for r in json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]:
            a = antwoorden.get(r["id"])
            if a and r["id"] not in uit and stand_van(a["richting"]) == r["stand"] and a.get("feit") == r["feit"]:
                uit[r["id"]] = r["label"]
    return uit


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="De feitenstap (B44, PLAN #31.9)")
    parser.add_argument("stap", choices=("varianten", "set", "laag", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("deel", nargs="?", choices=("indienen", "ophalen", "lezen"), help="bij varianten")
    parser.add_argument("--proef", type=int, default=0, help="indienen: per deel de eerste N")
    parser.add_argument("--route", choices=("sonnet", "laag", "beide", "a", "b"), default="sonnet",
                        help="v3: sonnet is de twee sleutels samen, a en b elk apart")
    parser.add_argument("--versie", choices=tuple(VERSIES), default="v3")
    args = parser.parse_args()
    v = VERSIES[args.versie]
    eerder = list(VERSIES.values())[: list(VERSIES).index(args.versie) + 1]
    uit_map, lab, twee = v["uit"], tuple(w["labels"] for w in reversed(eerder)), "vraag_b" in v
    if args.stap == "set":
        stukken = maak_set(v)
        print(len(stukken), "stukken;", sum(1 for s in stukken if s["kandidaten"]), "met een kandidaat")
        return
    if args.stap == "laag":
        laag_route(lees_set(uit_map), uit_map)
        return
    stukken = lees_set(uit_map)
    if args.stap in ("lezen", "tellen"):
        if twee:
            a_ = antwoorden_sleutel(stukken, uit_map, "A", VERSIES["v2"]["uit"])
            b_ = antwoorden_sleutel(stukken, uit_map, "B")
            antwoorden = {"sonnet": twee_sleutels({i: x for i, x in a_.items() if i in b_}, b_),
                          "a": a_, "b": b_}[args.route]
        else:
            sonnet = antwoorden_sonnet(stukken, uit_map)
            antwoorden = {"sonnet": sonnet, "laag": antwoorden_laag(stukken, uit_map),
                          "beide": antwoorden_beide(sonnet, antwoorden_laag(stukken, uit_map))}[args.route]
        if args.stap == "tellen":
            print(json.dumps(telling(stukken, antwoorden, labels_voor(antwoorden, lab), missers_apart=twee),
                             ensure_ascii=False, indent=1))
            return
        labels, zin = labels_voor(antwoorden, lab), zinnen_van_feiten()
        for s in stukken:
            a = antwoorden.get(s["id"])
            if a is None:
                continue
            stand = stand_van(a["richting"])
            vrij = s["deel"] in KERNDELEN + WAAR_DETAIL and a["richting"] == "bevestigt" and a.get("feit") == s["feit"]
            mis = twee and s["deel"] in KERNDELEN and stand is None
            if (stand is None and s["deel"] not in KERNDELEN) or vrij or mis or s["id"] in labels:
                continue
            waarom = f"A: {a_[s['id']].get('waarom')}\n  WAAROM B: {b_[s['id']].get('waarom')}" if twee \
                and args.route == "sonnet" else a.get("waarom")
            print(f"\n[{s['id']} · {s['deel']} · verwacht {s['feit']}] stand {stand} bij {a.get('feit')}"
                  f"\n  BERICHT: {s['tekst'][:300]}\n  FEIT: {zin.get(a.get('feit'), '-')}\n  WAAROM {waarom}")
        return
    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    uit_map.mkdir(parents=True, exist_ok=True)
    if args.stap == "varianten":
        from doublecheck.feitenbasis import lees_kern

        kern, batches = lees_kern(), uit_map / "varianten-batches.jsonl"
        if args.deel == "indienen":
            klaar = {r["feit"] for r in _jsonl(uit_map / "varianten.jsonl")}  # een kapot antwoord gaat opnieuw
            if al_uitgegeven(uit_map) + 0.2 > v["budget"]:
                raise Weigering(f"geweigerd: ${al_uitgegeven(uit_map):.2f} plus $0,20 is meer dan ${v['budget']:.2f}")
            gebruikt: dict[str, list[str]] = {}  # v3: de zinnen van v2 per feit, om niet te herhalen
            if len(eerder) > 1 and Path(eerder[-2]["set"]).exists():
                for z in json.loads(Path(eerder[-2]["set"]).read_text(encoding="utf-8"))["zinnen"]:
                    gebruikt.setdefault(z["feit"], []).append(z["tekst"])
            verzoeken = []
            for i, f in enumerate(kern):
                if f["id"] in klaar:
                    continue
                talen = taal_voor(i + v["taal_schuif"])
                verzoeken.append(_verzoek(f"var-{f['id']}", "haiku", None, v["variant_vraag"].format(
                    zin=f["zin"], taal=" and ".join(_TAALNAAM[t] for t in talen), taal_een=_TAALNAAM[talen[0]],
                    gebruikt="\n".join(f"- {z}" for z in gebruikt.get(f["id"], []))), v["variant_schema"], 4_000))
            if not verzoeken:
                raise SystemExit("alle feiten hebben varianten")
            batch = client.messages.batches.create(requests=verzoeken)
            with batches.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": batch.id, "versie": v["variant_versie"], "schatting": 0.2,
                                     "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
            print(f"batch {batch.id}: {len(verzoeken)} feiten")
        elif args.deel == "ophalen":
            alle, rijen, kapot = _jsonl(batches), {r["feit"]: r for r in _jsonl(uit_map / "varianten.jsonl")}, []
            for b in alle:
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    return
                werkelijk = 0.0
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded":
                        kapot.append((r.custom_id, r.result.type))
                        continue
                    werkelijk += _kosten(r.result.message, "haiku")
                    tekst = "".join(getattr(bl, "text", "") or "" for bl in r.result.message.content)
                    try:
                        rijen.setdefault(r.custom_id.removeprefix("var-"),
                                         {"feit": r.custom_id.removeprefix("var-"), **json.loads(tekst)})
                    except json.JSONDecodeError:
                        kapot.append((r.custom_id, r.result.message.stop_reason))
                b["werkelijk"] = round(werkelijk, 4)
            _schrijf(uit_map / "varianten.jsonl", list(rijen.values()))
            _schrijf(batches, alle)
            print(len(rijen), "feiten met varianten;", "kapot (opnieuw indienen):", kapot,
                  f"werkelijk ${sum(b['werkelijk'] for b in alle):.3f}")
        else:
            zin = {f["id"]: f["zin"] for f in kern}
            for r in _jsonl(uit_map / "varianten.jsonl"):
                print(f"\n## {r['feit']}: {zin[r['feit']]}")
                for soort in v["variant_schema"]["required"]:
                    for t in r[soort]:
                        print(f"  {soort}: {t}")
        return
    batches = uit_map / "batches.jsonl"
    if args.stap == "indienen":
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        if twee:  # A is er al voor alles wat v2 beantwoordde: dezelfde vraag
            beantwoord = {"A": set(antwoorden_sleutel(stukken, uit_map, "A", VERSIES["v2"]["uit"])),
                          "B": set(antwoorden_sleutel(stukken, uit_map, "B"))}
            nog = [(s, k) for s in stukken if s["kandidaten"] for k in SLEUTELS
                   if s["id"] not in beantwoord[k] and verzoek_id(s["id"], k) not in ingediend]
        else:
            nog = [(s, "A") for s in stukken if s["kandidaten"] and s["id"] not in ingediend]
        if args.proef:  # per deel de eerste N stukken, met al hun sleutels
            gekozen_ids = {i for d in DELEN for i in list(dict.fromkeys(s["id"] for s, _ in nog
                                                                         if s["deel"] == d))[: args.proef]}
            nog = [(s, k) for s, k in nog if s["id"] in gekozen_ids]
        if not nog:
            raise SystemExit("niets in te dienen")
        zin = zinnen_van_feiten()
        geschat = len(nog) * _PER_VERZOEK[v["naam"]]
        if al_uitgegeven(uit_map) + geschat > v["budget"]:
            raise Weigering(f"geweigerd: ${al_uitgegeven(uit_map):.2f} plus ${geschat:.2f}"
                            f" is meer dan ${v['budget']:.2f}")
        verzoeken = [_verzoek(verzoek_id(s["id"], k) if twee else s["id"], "sonnet", SYSTEEM,
                              vraag(s["tekst"], [(f, zin[f]) for f in volgorde(s["kandidaten"], k)],
                                    v["vraag_b"] if k == "B" else v["vraag"]), _SCHEMA, 500) for s, k in nog]
        batch = client.messages.batches.create(requests=verzoeken)
        with batches.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": batch.id, "versie": v["naam"], "model": MODELLEN["sonnet"]["id"],
                                 "schatting": round(geschat, 3), "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} berichten, naar schatting ${geschat:.2f};"
              f" samen ${al_uitgegeven(uit_map):.2f} van ${v['budget']:.2f}")
        return
    per_id = {s["id"]: s for s in stukken}
    alle = _jsonl(batches)
    klaar = {verzoek_id(r["id"], r["sleutel"]) if twee else r["id"] for r in _jsonl(uit_map / "antwoorden.jsonl")}
    with (uit_map / "antwoorden.jsonl").open("a", encoding="utf-8") as uit:
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id in klaar or r.result.type != "succeeded":
                    continue
                werkelijk += _kosten(r.result.message, "sonnet")
                tekst = "".join(getattr(bl, "text", "") or "" for bl in r.result.message.content)
                stuk_id, sleutel = uit_verzoek_id(r.custom_id) if twee else (r.custom_id, "A")
                feiten = volgorde(per_id[stuk_id]["kandidaten"], sleutel)
                richting, nummer = lees_feitoordeel(tekst, len(feiten))
                try:
                    waarom = json.loads(tekst).get("waarom")
                except json.JSONDecodeError:
                    waarom = None
                uit.write(json.dumps({"id": stuk_id, "richting": richting,
                                      "feit": feiten[nummer - 1] if nummer else None, "waarom": waarom,
                                      "versie": v["naam"]} | ({"sleutel": sleutel} if twee else {}),
                                     ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    _schrijf(batches, alle)
    print(f"werkelijk ${al_uitgegeven(uit_map):.2f} van ${v['budget']:.2f}")


if __name__ == "__main__":
    main()
