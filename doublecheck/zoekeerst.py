"""Zoeken eerst: de simpele versie tegen de huidige keten (PLAN #32.9).

De route van de eerste versie, met wat er nu staat: eerst de database (kring 1), anders één zoekvraag bij Brave,
dat de grote media wel ziet (BBC, Reuters, AP, de NYT, NU.nl; `data/zoekeerst/toegang.json`), en Sonnet die het
bericht en de top 10 leest. Welke bronnen tellen, zegt de bronnenlijst: groen alleen met twee goede uitgevers,
rood alleen met een goede tegenspraak. Verder niets.

    python -m doublecheck.hittewacht -- python -m doublecheck.zoekeerst draaien
    python -m doublecheck.zoekeerst tellen
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from doublecheck.zoekcontrole import (  # noqa: F401 - de kern van B51; de meting leent, niet andersom (#32.7c)
    N_RESULTATEN,
    OORDELEN,
    SCHEMA,
    SYSTEEM,
    VRAAG,
    brave,
    kleur_van,
    lees_oordeel,
    leesverzoek,
    resultaten_uit,
    zoekvraag,
)

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "zoekeerst"
BUDGET = 2.0  # PLAN #32.9
JUIST = {"K": "rood", "V": "rood", "W": "groen"}


def vergelijk(stukken: list[dict], kleuren: dict[str, str | None]) -> dict:
    """Per deel en samen: juist (rood bij K en V, groen bij W), fout (de omgekeerde kleur), geen kleur."""
    uit: dict[str, Counter] = {}
    for s in stukken:
        if s["id"] not in kleuren:
            continue
        k = kleuren[s["id"]]
        uitkomst = "geen kleur" if k is None else ("juist" if k == JUIST[s["deel"]] else "fout")
        for d in (s["deel"], "samen"):
            uit.setdefault(d, Counter({"n": 0, "juist": 0, "fout": 0, "geen kleur": 0}))
            uit[d]["n"] += 1
            uit[d][uitkomst] += 1
    return {k: dict(v) for k, v in uit.items()}


# --- de CLI --------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _sleutel() -> str:  # pragma: no cover - op .env
    for r in (WORTEL / ".env").read_text(encoding="utf-8").splitlines():
        if r.startswith("BRAVE_API_KEY="):
            return r.split("=", 1)[1].strip().strip('"')
    raise SystemExit("geen BRAVE_API_KEY in .env")


def main() -> None:  # pragma: no cover - CLI, live
    import argparse
    import time

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck import eindtoets as e
    from doublecheck.config import load_config
    from doublecheck.snelantwoord import percentiel
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="Zoeken eerst (PLAN #32.9)")
    parser.add_argument("stap", choices=("draaien", "tellen"))
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    stukken = _jsonl(e.UIT / "set.jsonl")
    pad = UIT / "antwoorden.jsonl"
    if args.stap == "draaien":
        laad_sleutel()
        client, sleutel, config = anthropic.Anthropic(), _sleutel(), load_config(None)
        conn = connect(str(WORTEL / "doublecheck.db"))
        tabel, sites = bc.ijktabel(config), bc.herkomstlijst()["sites"]
        gedaan = {r["id"] for r in _jsonl(pad)}
        for s in stukken:
            if s["id"] in gedaan:
                continue
            if sum(r["kosten"] for r in _jsonl(pad)) > BUDGET:
                raise SystemExit(f"gestopt: boven de grens van ${BUDGET:.2f}")
            begin = time.perf_counter()
            snel = None if s["deel"] == "V" else bc.snel_antwoord(  # bij V doet de eigen check alsof hij er niet is
                api.los_op(conn, config, s["tekst"], None, None).model_dump(), tabel, s["tekst"],
                config.model_versions.text_embedding)
            if snel is not None:
                rij = {"id": s["id"], "route": "database", "kleur": snel["kleur"], "oordeel": snel["oordeel"],
                       "kosten": 0.0}
            else:
                resultaten = resultaten_uit(brave(zoekvraag(s["tekst"]), sleutel), sites)
                msg = client.messages.create(**leesverzoek(s["tekst"], resultaten, s.get("datum"), config))
                antwoord = lees_oordeel("".join(getattr(b, "text", "") or "" for b in msg.content))
                rij = {"id": s["id"], "route": "zoeken", "kleur": kleur_van(antwoord, resultaten), **antwoord,
                       "resultaten": [{k: r[k] for k in ("nr", "url", "site", "band", "titel")} for r in resultaten],
                       "kosten": round(bc.kosten(bc.gebruik_uit(msg)) + 0.005, 5)}
            rij["seconden"] = round(time.perf_counter() - begin, 2)
            with pad.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rij, ensure_ascii=False) + "\n")
            print(f"{s['id']}: {rij['oordeel']} ({rij['kleur']}), {rij['seconden']} s", flush=True)
        return
    nieuw = {r["id"]: r for r in _jsonl(pad)}
    oud = {r["id"]: r for r in _jsonl(e.UIT / "antwoorden.jsonl")}
    tijden = lambda rs: {"p50": percentiel(rs, .5), "p95": percentiel(rs, .95)} if rs else {}  # noqa: E731
    uit = {"simpel": vergelijk(stukken, {i: r["kleur"] for i, r in nieuw.items()}),
           "huidige keten": vergelijk(stukken, {i: r["kleur"] for i, r in oud.items()}),
           "tijd simpel (V en W)": tijden([r["seconden"] for i, r in nieuw.items() if not i.startswith("K")]),
           "tijd keten (V en W)": tijden([r["seconden"] for i, r in oud.items() if not i.startswith("K")]),
           "kosten simpel": round(sum(r["kosten"] for r in nieuw.values()), 2),
           "kosten keten": round(sum(r["kosten"] for r in oud.values()), 2),
           "verschillen": [(s["id"], oud.get(s["id"], {}).get("kleur"), nieuw.get(s["id"], {}).get("kleur"))
                           for s in stukken if oud.get(s["id"], {}).get("kleur") != nieuw.get(s["id"], {}).get("kleur")]}
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
