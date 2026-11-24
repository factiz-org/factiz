"""Een stroom van consensus naast de factchecks: de eerste meting met het nieuwsoverzicht van Wikipedia (PLAN #32.55, PO
2026-11-07: "De echte work ground zit hem dus in een soort database met consensus, laten we zeggen Wikipedia"; "graag").

Per bericht de dagen van Portal:Current events van zijn datum tot drie dagen ervoor; de drie regels die er met bge-m3 het
meest op lijken; Haiku zegt per regel of die het bericht bevestigt, tegenspreekt of niets zegt. Geen enkel bericht komt
uit het overzicht zelf. De eisen staan vast in PLAN #32.55.

    python -m doublecheck.consensus set|ophalen|kiezen
    python -m doublecheck.consensus vragen [--proef N]|lezen|tellen
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "consensus"
LABELS = WORTEL / "docs" / "steekproeven" / "32.55-portaal.json"
MAANDEN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
           "December")
DAGEN_TERUG = 3
N_REGELS = 3
MODEL = "haiku"
BUDGET = 2.0
SETS_WAAR = {"K": True, "F": True, "W": True, "W-merk": True, "O": False}
RELATIES = ("bevestigt", "spreekt tegen", "niets")
EIS_NUT, EIS_VEILIG, EIS_ALARM = 35, 1, 2

SYSTEEM = ("You compare a message with lines from a daily overview of news events. You only say whether a line confirms "
           "the message, contradicts it, or says nothing about it.")
VRAAG = """The message (it circulated around {datum}):
{bericht}

Lines from an overview of news events of the days up to then:
{regels}

For each line, say:
- "bevestigt": the line reports the same event or fact as the main claim of the message, and agrees with it (the same
  who, what and where; small differences in wording or rounding do not matter);
- "spreekt tegen": the line is about the same event or fact, but says something that cannot be true if the message is
  true (another cause, place, person, number, or that it did not happen);
- "niets": the line is about something else, or only about the same topic or person.
If in doubt, "niets"."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["regels"],
          "properties": {"regels": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["nr", "relatie"],
              "properties": {"nr": {"type": "integer"}, "relatie": {"type": "string", "enum": list(RELATIES)}}}}}}


class Weigering(Exception):
    """Tellen kan niet: een bevestiging of tegenspraak zonder label."""


def portaaltitel(dag: dt.date) -> str:
    return f"Portal:Current events/{dag.year} {MAANDEN[dag.month - 1]} {dag.day}"


def venster(datum: str | None) -> list[dt.date]:
    """De dagen van het overzicht voor een bericht: zijn datum en de drie dagen ervoor; zonder geldige datum geen."""
    try:
        dag = dt.date.fromisoformat((datum or "")[:10])
    except ValueError:
        return []
    return [dag - dt.timedelta(days=n) for n in range(DAGEN_TERUG, -1, -1)]


def kies_set(duel: list[dict], vers: list[dict]) -> list[dict]:
    """De set E: het duel en de verse Engelse set van #32.43, elk bericht één keer, met of het waar is. Een set die niet
    in `SETS_WAAR` staat, weigert: de ware sets van de eindtoets en W' komen uit het overzicht zelf."""
    uit, gezien = [], set()
    for r in [*duel, *vers]:
        if r["set"] not in SETS_WAAR:
            raise ValueError(f"set {r['set']!r} hoort niet in deze meting")
        if r["id"] in gezien:
            continue
        gezien.add(r["id"])
        uit.append({"id": r["id"], "set": r["set"], "tekst": r["tekst"], "datum": r.get("datum"),
                    "waar": SETS_WAAR[r["set"]]})
    return uit


def kandidaten(vraag: np.ndarray, regels: np.ndarray, n: int = N_REGELS) -> list[int]:
    """De `n` regels die het meest op het bericht lijken (cosinus op genormaliseerde vectoren), beste eerst."""
    if len(regels) == 0:
        return []
    v = vraag / (np.linalg.norm(vraag) or 1.0)
    r = regels / np.maximum(np.linalg.norm(regels, axis=1, keepdims=True), 1e-12)
    return [int(i) for i in np.argsort(-(r @ v), kind="stable")[:n]]


def verzoek(bericht: str, datum: str | None, regels: list[str]) -> dict:
    from doublecheck.modellen import MODELLEN

    tekst = VRAAG.format(datum=datum or "an unknown date", bericht=bericht,
                         regels="\n".join(f"[{i}] {r}" for i, r in enumerate(regels, 1)))
    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 1500, "system": SYSTEEM,
            "messages": [{"role": "user", "content": tekst}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}}


def lees_relaties(tekst: str, n: int) -> list[str]:
    """Per regel de relatie; een ongeldig antwoord of nummer telt als *niets* (twijfel versoepelt nooit)."""
    uit = ["niets"] * n
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return uit
    for r in d.get("regels", []) if isinstance(d, dict) else []:
        if isinstance(r, dict) and type(r.get("nr")) is int and 1 <= r["nr"] <= n and r.get("relatie") in RELATIES:
            uit[r["nr"] - 1] = r["relatie"]
    return uit


def samen(relaties: list[str]) -> str:
    """Eén tegenspraak weegt zwaarder dan een bevestiging."""
    return "spreekt tegen" if "spreekt tegen" in relaties else ("bevestigt" if "bevestigt" in relaties else "niets")


def telling(berichten: list[dict], antwoorden: dict[str, dict], labels: dict[str, str]) -> dict:
    """Per waar en nep; weigert zolang een *bevestigt* of *spreekt tegen* geen label (*terecht*, *onterecht*) heeft."""
    open_ = [i for i, a in antwoorden.items() if a["uitkomst"] != "niets" and labels.get(i) not in ("terecht", "onterecht")]
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    uit: dict[str, Counter] = {"waar": Counter(), "nep": Counter()}
    for b in berichten:
        t = uit["waar" if b["waar"] else "nep"]
        t["n"] += 1
        a = antwoorden.get(b["id"])
        if a is None:
            t["zonder overzicht"] += 1
        elif a["uitkomst"] == "niets":
            t["niets"] += 1
        else:
            t[f"{a['uitkomst']} {labels[b['id']]}"] += 1
    w, n = uit["waar"], uit["nep"]
    return {"waar": dict(w), "nep": dict(n),
            "eisen": {f"1 nut (minstens {EIS_NUT})": w["bevestigt terecht"] >= EIS_NUT,
                      f"2 veilig (hoogstens {EIS_VEILIG})": n["bevestigt onterecht"] <= EIS_VEILIG,
                      f"3 geen vals alarm (hoogstens {EIS_ALARM})": w["spreekt tegen onterecht"] <= EIS_ALARM}}


# --- de bestanden, het netwerk en de modellen --------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")


def _set() -> None:  # pragma: no cover - op de bestanden
    pad = UIT / "set-en.jsonl"
    if pad.exists():
        raise SystemExit("de set ligt al vast")
    rijen = kies_set(_jsonl(WORTEL / "data" / "duel" / "duel-2026-11-07-berichten.jsonl"),
                     _jsonl(WORTEL / "data" / "talen" / "vers" / "en.jsonl"))
    _schrijf(pad, rijen)
    print(len(rijen), Counter(r["set"] for r in rijen), Counter(r["waar"] for r in rijen))


def _ophalen() -> None:  # pragma: no cover - netwerk
    """Elke nodige dag van het overzicht, 50 titels per verzoek, één verzoek tegelijk (`koppen._wiki`); hervatbaar."""
    from doublecheck.eindtoets import portal_zinnen
    from doublecheck.koppen import _wiki

    pad = UIT / "portaal-en.json"
    klaar = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {}
    dagen = sorted({d for r in _jsonl(UIT / "set-en.jsonl") for d in venster(r["datum"])} - {dt.date.fromisoformat(k)
                                                                                              for k in klaar})
    print(f"{len(dagen)} dagen op te halen, {len(klaar)} al klaar")
    for i in range(0, len(dagen), 50):
        stuk = dagen[i:i + 50]
        titels = {portaaltitel(d): d for d in stuk}
        antwoord = _wiki({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                          "titles": "|".join(titels)})
        normaal = {n["to"]: n["from"] for n in antwoord["query"].get("normalized", [])}
        for p in antwoord["query"]["pages"]:
            dag = titels.get(normaal.get(p["title"], p["title"]))
            if dag is None:
                continue
            tekst = p["revisions"][0]["slots"]["main"]["content"] if "revisions" in p else ""
            klaar[dag.isoformat()] = portal_zinnen(tekst)
        for d in stuk:  # een dag zonder pagina telt als leeg, zodat hij niet opnieuw gevraagd wordt
            klaar.setdefault(d.isoformat(), [])
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps(klaar, ensure_ascii=False), encoding="utf-8")
        print(f"{min(i + 50, len(dagen))} van {len(dagen)}; met regels: {sum(bool(v) for v in klaar.values())}", flush=True)


def _kiezen() -> None:  # pragma: no cover - het model op de Mac
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts

    versie = load_config(None).model_versions.text_embedding
    portaal = json.loads((UIT / "portaal-en.json").read_text(encoding="utf-8"))
    berichten = _jsonl(UIT / "set-en.jsonl")
    alle_regels = sorted({r for v in portaal.values() for r in v})
    print(f"{len(berichten)} berichten, {len(alle_regels)} regels")
    vec_regel = {r: f.vector for r, f in zip(alle_regels, fingerprint_texts(alle_regels, versie))}
    vec_bericht = [f.vector for f in fingerprint_texts([b["tekst"] for b in berichten], versie)]
    uit = []
    for b, v in zip(berichten, vec_bericht):
        regels = sorted({r for d in venster(b["datum"]) for r in portaal.get(d.isoformat(), [])})
        keus = kandidaten(v, np.array([vec_regel[r] for r in regels]) if regels else np.zeros((0, len(v))))
        uit.append({"id": b["id"], "regels": [regels[i] for i in keus]})
    _schrijf(UIT / "kandidaten-en.jsonl", uit)
    print(f"met regels: {sum(bool(r['regels']) for r in uit)} van {len(uit)}")


def _vragen(proef: int | None) -> None:  # pragma: no cover - de Batch API op openbare berichten
    import anthropic

    from doublecheck.berichtcontrole import gebruik_uit
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.uitkomsten import batch_met_grens
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    berichten = {b["id"]: b for b in _jsonl(UIT / "set-en.jsonl")}
    pad = UIT / "antwoorden-en.jsonl"
    klaar = {a["id"]: a for a in _jsonl(pad)}
    uitgegeven = sum(a["kosten"] for a in klaar.values())
    werk = [k for k in _jsonl(UIT / "kandidaten-en.jsonl") if k["regels"] and k["id"] not in klaar][:proef or None]
    if uitgegeven + 0.004 * len(werk) > BUDGET:
        raise SystemExit(f"boven de grens: al ${uitgegeven:.2f}")
    nummers = {f"c{i:04d}": k for i, k in enumerate(werk)}
    antwoorden = {}
    batch_met_grens(anthropic.Anthropic(max_retries=6),
                    {c: verzoek(berichten[k["id"]]["tekst"], berichten[k["id"]]["datum"], k["regels"])
                     for c, k in nummers.items()}, antwoorden.update, aangemeld=lambda b, ids: None,
                    afgemeld=lambda b: None)
    nieuw = []
    for c, msg in antwoorden.items():
        k = nummers[c]
        tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
        relaties = lees_relaties(tekst, len(k["regels"]))
        nieuw.append({"id": k["id"], "regels": k["regels"], "relaties": relaties, "uitkomst": samen(relaties),
                      "kosten": round(kosten_batch(gebruik_uit(msg), MODEL), 6)})
    _schrijf(pad, [*klaar.values(), *nieuw])
    print(f"{len(nieuw)} beantwoord; {Counter(a['uitkomst'] for a in nieuw)}; samen "
          f"${uitgegeven + sum(a['kosten'] for a in nieuw):.3f}")


def _lees_labels() -> dict[str, str]:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {r["id"]: r["label"] for r in d.get("labels", [])}


def _lezen() -> None:  # pragma: no cover - op de bestanden
    berichten = {b["id"]: b for b in _jsonl(UIT / "set-en.jsonl")}
    labels = _lees_labels()
    open_ = [a for a in _jsonl(UIT / "antwoorden-en.jsonl") if a["uitkomst"] != "niets" and a["id"] not in labels]
    _schrijf(UIT / "te-labelen-en.jsonl", [{"id": a["id"], "set": berichten[a["id"]]["set"],
                                            "waar": berichten[a["id"]]["waar"], "datum": berichten[a["id"]]["datum"],
                                            "bericht": berichten[a["id"]]["tekst"], "uitkomst": a["uitkomst"],
                                            "regels": [f"{r} [{x}]" for r, x in zip(a["regels"], a["relaties"])]}
                                           for a in open_])
    print(f"{len(open_)} te labelen in {UIT / 'te-labelen-en.jsonl'}")


def _tellen() -> None:  # pragma: no cover - op de bestanden
    berichten = _jsonl(UIT / "set-en.jsonl")
    antwoorden = {a["id"]: a for a in _jsonl(UIT / "antwoorden-en.jsonl")}
    t = telling(berichten, antwoorden, _lees_labels())
    t["kosten"] = round(sum(a["kosten"] for a in antwoorden.values()), 3)
    (UIT / "telling-en.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(t, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Het nieuwsoverzicht van Wikipedia als consensus (PLAN #32.55)")
    parser.add_argument("stap", choices=("set", "ophalen", "kiezen", "vragen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    {"set": _set, "ophalen": _ophalen, "kiezen": _kiezen, "vragen": lambda: _vragen(args.proef), "lezen": _lezen,
     "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
