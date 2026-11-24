"""De waarheidsmeter (B44, PLAN #31.9).

De wens van de PO (2026-10-26): een screenshot inslepen en een stand zien op een
meter van groen naar rood, in woorden als "zeer waarschijnlijk onwaar", net als
Pangram nooit 100%. De stand is geen gevoel van het model maar een gemeten
aandeel: van de berichten met hetzelfde oordeel en dezelfde soort bron, hoeveel
bleken waar. Vijf gemeten standen (1, 3, 5, 7, 9), de laag altijd erbij. De
uiteinden 0 en 10 bestaan alleen voor de feitenbasis van B34: *in strijd met
een vastgesteld feit* en *vastgesteld feit*, in woorden, nooit als "100%"
(B44, besloten door PO 2026-10-26).

De regels, vastgelegd vóór de ijking:
- de stand volgt uit het 95%-interval van het aandeel waar, niet uit het
  puntgetal: 1 als de bovengrens hoogstens 10% is, 9 als de ondergrens minstens
  90% is, 3 en 7 aan de kant van de helft, anders 5;
- een klasse met minder dan 30 berichten blijft op 5: twijfel versoepelt nooit;
- de meter wijst nooit tegen het oordeel in: *klopt niet* en *let op* hooguit 5,
  *klopt* minstens 5, *onzeker* altijd 5 (anders zou de mix van de meetset de
  naald verzetten);
- de uitersten 1 en 9 met een check van een redactie (laag 1), of zonder
  factcheck voor een soort bewering die de ijkronde vrijgeeft (`VRIJE_SOORTEN`,
  leeg tot die ronde); anders hoogstens 3 en 7;
- 0 en 10 alleen als het bericht een vastgesteld feit uit de feitenbasis
  bevestigt of tegenspreekt; voorwaarde is nul fouten op de kern en de
  minimale paren (B34, PLAN #31.9). Gemeten met de feitenstap
  (`doublecheck/feitstap.py`): stand 10 haalde het met twee sleutels
  (`feitstap-v3`, BENCHMARK §154), stand 0 niet. Stand 0 is dicht
  (`OPEN_UITEINDEN`): een bericht dat een vastgesteld feit tegenspreekt krijgt
  de gemeten stand van 1 tot 9.

    python -m doublecheck.meter
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
STANDEN = {0: "in strijd met een vastgesteld feit", 1: "zeer waarschijnlijk onwaar", 3: "waarschijnlijk onwaar",
           5: "onzeker", 7: "waarschijnlijk waar", 9: "zeer waarschijnlijk waar", 10: "vastgesteld feit"}
MIN_N = 30
# Soorten bewering waar de ijkronde stand 1 en 9 zonder check van een redactie draagt; leeg tot die ronde.
VRIJE_SOORTEN: frozenset[str] = frozenset()
# PO 2026-10-26, na §154: "stand 10 gaat open voor de 40 kernfeiten [...] en stand 0 blijft dicht."
OPEN_UITEINDEN: frozenset[int] = frozenset({10})
# De machine van vraag v4 (v5 = v4 met bijschrift), zonder kaal model en zonder omgekeerd zoeken.
IJKRONDES = ((4, ("b",)), (5, ("b",)), (7, ("a", "b")))
UIT = WORTEL / "data" / "meter" / "ijking-verificatie-v4.json"


def laag_van_antwoord(bronnen: list[dict]) -> str:
    """De sterkste bron die het antwoord noemt: een check van een redactie, het web, of niets."""
    soorten = {b.get("soort") for b in bronnen}
    if "geheugen" in soorten:
        return "redactie"
    return "web" if soorten & {"web", "beeld"} else "geen bron"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - r) / d), min(1.0, (c + r) / d)


def stand(waar: int, n: int, laag: str, oordeel: str, soort: str | None = None) -> int:
    """De gemeten stand van een klasse volgens de regels hierboven (1 tot 9; 0 en
    10 komen nooit uit een meting, alleen uit de feitenbasis)."""
    if n < MIN_N or oordeel not in ("klopt niet", "let op", "klopt"):
        return 5
    laag_grens, hoog_grens = wilson(waar, n)
    s = 1 if hoog_grens <= 0.10 else 9 if laag_grens >= 0.90 else 3 if hoog_grens <= 0.50 else 7 if laag_grens >= 0.50 \
        else 5
    s = min(s, 5) if oordeel in ("klopt niet", "let op") else max(s, 5)
    return s if laag == "redactie" or soort in VRIJE_SOORTEN else min(max(s, 3), 7)


def ijktabel(rijen: list[tuple[str, str, str]]) -> dict[tuple[str, str], dict]:
    """Per (oordeel, laag): hoeveel berichten, hoeveel waar, het interval en de stand.
    `rijen`: (oordeel, laag, label) met label *waar* of *onwaar*."""
    tel: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for oordeel, laag, label in rijen:
        tel[(oordeel, laag)][0] += label == "waar"
        tel[(oordeel, laag)][1] += 1
    uit = {}
    for (oordeel, laag), (waar, n) in tel.items():
        lo, hi = wilson(waar, n)
        s = stand(waar, n, laag, oordeel)
        uit[(oordeel, laag)] = {"oordeel": oordeel, "laag": laag, "n": n, "waar": waar, "aandeel waar": round(waar / n, 4),
                                "interval": [round(lo, 4), round(hi, 4)], "stand": s, "woorden": STANDEN[s]}
    return uit


def meterstand(tabel: dict[tuple[str, str], dict], oordeel: str, laag: str, feit: str | None = None) -> dict:
    """De stand voor één antwoord; een klasse zonder ijking staat op 5. `feit`:
    *waar* of *onwaar* als de feitenstap met twee sleutels (`feitstap-v3`) het
    bericht een vastgesteld feit uit de feitenbasis zag bevestigen of
    tegenspreken; dan 10 of 0, met de feitenbasis als laag, maar alleen als dat
    uiteinde open is (`OPEN_UITEINDEN`). Anders de gemeten stand."""
    s = {"waar": 10, "onwaar": 0}.get(feit)
    if s in OPEN_UITEINDEN:
        return {"stand": s, "woorden": STANDEN[s], "laag": "feitenbasis", "n": None, "aandeel waar": None}
    rij = tabel.get((oordeel, laag))
    s = rij["stand"] if rij else 5
    return {"stand": s, "woorden": STANDEN[s], "laag": laag, "n": rij["n"] if rij else 0,
            "aandeel waar": rij["aandeel waar"] if rij else None}


def ijkrijen() -> list[tuple[str, str, str]]:  # pragma: no cover - op de antwoorden van de rondes
    from doublecheck import verificatie as v

    rijen = []
    for ronde, omstandigheden in IJKRONDES:
        stukken = {s["id"]: s for s in v.gekozen_stukken(ronde)}
        for (om, id_), a in v.antwoorden(ronde, "sonnet").items():
            s = stukken.get(id_)
            if om in omstandigheden and s and s["label"] in ("waar", "onwaar") \
                    and a["oordeel"] in ("klopt niet", "let op", "onzeker", "klopt"):
                rijen.append((a["oordeel"], laag_van_antwoord(a["bronnen"]), s["label"]))
    return rijen


def main() -> None:  # pragma: no cover - CLI
    rijen = ijkrijen()
    tabel = ijktabel(rijen)
    UIT.parent.mkdir(parents=True, exist_ok=True)
    waar = sum(r[2] == "waar" for r in rijen)
    UIT.write_text(json.dumps({"rondes": [list(r) for r in IJKRONDES], "n": len(rijen), "aandeel waar in de mix":
                               round(waar / len(rijen), 4), "klassen": sorted(tabel.values(), key=lambda r: -r["n"])},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rijen)} oordelen, {waar / len(rijen):.0%} waar in de mix")
    for r in sorted(tabel.values(), key=lambda r: (r["stand"], -r["n"])):
        lo, hi = r["interval"]
        print(f"stand {r['stand']} | {r['oordeel']:10} | {r['laag']:9} | n={r['n']:4} | waar {r['aandeel waar']:5.0%} "
              f"({lo:.0%}–{hi:.0%}) | {r['woorden']}")


if __name__ == "__main__":
    main()
