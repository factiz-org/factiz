"""De zoekproef van het platform (PLAN #33.3): werkt zoeken op woorden in elk schrift?

    python -m factiz_site.zoekproef [<publicatie.db>]

Vijftig pagina's uit de publicatiedatabase, tien per groep van schriften, met een vast zaad. De zoekvraag is een stuk
uit de bewering zelf; goed is: de pagina staat bij de eerste tien. De eis ligt vast in PLAN: minstens 45 van de 50, en
in elke groep minstens 8 van de 10. Dit meet of het zoeken in elk schrift werkt, niet of het een vraag begrijpt.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

from factiz_site import db

ZAAD = 3303
PER_GROEP = 10
ZONDER_SPATIES = frozenset({"zh", "ja", "th", "km", "lo", "my"})
_GROEP = {
    "arabisch": {"ar", "fa", "ur", "ps", "sd", "ug", "ckb"},
    "indiaas": {"hi", "ta", "te", "bn", "ml", "kn", "mr", "gu", "pa", "as", "si", "ne", "or"},
    "zonder spaties": set(ZONDER_SPATIES),
    "latijns": {"en", "es", "pt", "de", "nl", "fr", "it", "id", "tr", "tl", "pl", "ms", "az", "ca", "gl", "hr", "sw",
                "af", "ro", "ga", "vi"},
}


def groep(taal: str) -> str:
    return next((naam for naam, talen in _GROEP.items() if taal in talen), "overig")


def vraag_uit(tekst: str, taal: str) -> str:
    """Een stuk uit de bewering zelf: drie opeenvolgende woorden vanaf het midden, of bij een schrift zonder spaties
    vier opeenvolgende tekens vanaf het midden."""
    if taal in ZONDER_SPATIES:
        tekens = "".join(tekst.split())
        begin = max(0, len(tekens) // 2 - 1)
        return tekens[begin:begin + 4]
    woorden = tekst.split()
    if len(woorden) <= 3:
        return " ".join(woorden)
    begin = len(woorden) // 2
    return " ".join(woorden[begin:begin + 3])


def meet(bestand: str | Path, per_groep: int = PER_GROEP, zaad: int = ZAAD) -> dict:
    pub = db.Publicatie(bestand)
    pub.afkortingen_klaar(60)      # zoals de server draait, met de index van de afkortingen (#34.2ab)
    conn = sqlite3.connect(f"{Path(bestand).resolve().as_uri()}?mode=ro", uri=True)
    per: dict[str, list[tuple[str, str, str]]] = {}
    for nummer, bewering, taal in conn.execute("SELECT nummer, bewering, taal FROM pagina ORDER BY nummer"):
        per.setdefault(groep(taal), []).append((nummer, bewering, taal))
    conn.close()
    rng = random.Random(zaad)
    uitslag = {"vragen": 0, "goed": 0, "per_groep": {}, "missers": []}
    for naam in sorted(per):
        proef = rng.sample(per[naam], min(per_groep, len(per[naam])))
        goed = 0
        for nummer, bewering, taal in proef:
            vraag = vraag_uit(db.schoon(bewering), taal)
            raak = nummer in [r["nummer"] for r in pub.zoek(vraag)[0][:10]]
            goed += raak
            if not raak:
                uitslag["missers"].append({"groep": naam, "taal": taal, "nummer": nummer, "vraag": vraag})
        uitslag["per_groep"][naam] = {"vragen": len(proef), "goed": goed}
        uitslag["vragen"] += len(proef)
        uitslag["goed"] += goed
    return uitslag


def gehaald(uitslag: dict) -> bool:
    """De eis van PLAN #33.3: negen op de tien in totaal, en in elke groep acht op de tien."""
    return (uitslag["goed"] * 10 >= uitslag["vragen"] * 9
            and all(g["goed"] * 10 >= g["vragen"] * 8 for g in uitslag["per_groep"].values()))


def main() -> None:  # pragma: no cover - CLI
    from factiz_site.app import _standaard_pad

    bestand = sys.argv[1] if len(sys.argv) > 1 else _standaard_pad()
    u = meet(bestand)
    for naam, g in u["per_groep"].items():
        print(f"{naam:15} {g['goed']:2} van {g['vragen']}")
    print(f"samen           {u['goed']} van {u['vragen']}; eis gehaald: {gehaald(u)}")
    for m in u["missers"]:
        print("  gemist:", m["groep"], m["taal"], m["nummer"], repr(m["vraag"]))
    raise SystemExit(0 if gehaald(u) else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
