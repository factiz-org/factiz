"""Welke redactie zit er achter een factcheck? *(PLAN.md #17.7, B12, DR7)*

DR7 draagt de belofte uit B12 — *"weerlegd door 14 factcheckers in 6 talen"* —
en dat moet veertien redacties betekenen, geen veertien schrijfwijzen. Het
`author`-veld van ClaimReview levert dat niet: er staan claimanten in
(`Donald Trump` als uitgever op politifact.com), individuele journalisten (68
namen op thequint.com) en spellingvarianten (`PesaCheck` naast `Pesa Check`).

**De identiteit hangt aan de host van de factcheck, niet aan de naam.** Eén
canonieke naam per host, en gelijke namen zijn dezelfde redactie. Dat is een
functie en geen vereniging, dus er kan geen ketting ontstaan — de poging om
namen en hosts transitief samen te voegen smolt 230 namen over 32 hosts tot één
blok (BENCHMARK.md §48c).

**De lijst is een witte lijst (B28, #25.29), met de hand nagekeken.** Wat
erin staat, heeft iemand gelezen en een redactie of kennisinstelling genoemd
(`docs/steekproeven/25.29-uitgevers.json`); in een database die de toelating
draagt, is alleen een claim met een check van zo'n host vindbaar (toelating.py).
`--voorstel` meet het corpus opnieuw, maar laat nooit zelf toe: een nieuwe host
komt in `te_beoordelen`, met de naam die de meting voorstelt. Vroeger kwam een
host met vijf checks en een dominante naam vanzelf in het register, en zo
kwamen er een witgoedwinkel en een casinosite in. Een host die bij het nalopen
rommel bleek, komt niet terug in `te_beoordelen`.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

UITGEVERS_PATH = Path(__file__).parent / "uitgevers.json"

META = (
    "Host → canonieke uitgeversnaam (#17.7), en de witte lijst van uitgevers (B28, #25.29): "
    "elke host hier is met de hand nagekeken en een redactie of kennisinstelling genoemd, in "
    "docs/steekproeven/25.29-uitgevers.json. In een database die de toelating draagt, is alleen "
    "een claim met een check van zo'n host vindbaar, en tonen antwoorden alleen zulke checks. "
    "`python -m doublecheck.uitgevers --voorstel` laat nooit zelf toe: een nieuwe host komt in "
    "`te_beoordelen`, met de naam die de meting voorstelt. Toelaten is een regel hier, met een "
    "label in het steekproefbestand; de suite controleert dat die twee gelijk zijn. "
    "`geweerd`: wat bij het nalopen rommel bleek; de import weigert het en "
    "`python -m doublecheck.opruimen` haalt het uit het corpus (PO 2026-10-13)."
)

# Een voorstel telt alleen als de dominante naam de host echt draagt. Onder deze
# grenzen is het net zo goed een journalist of een claimant.
MIN_AANDEEL = 0.5
MIN_CHECKS = 5


def load_hosts(path: str | Path = UITGEVERS_PATH) -> dict[str, str]:
    """Host → canonieke uitgeversnaam. Alleen de nagekeken regels."""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))["hosts"]


@functools.cache
def load_geweerd(path: str | Path = UITGEVERS_PATH) -> dict[str, str]:
    """Host → reden, voor wat bij het nalopen rommel bleek (#25.29): de
    import weigert het en `opruimen` haalt het uit het corpus. Eén keer per
    proces gelezen, want de import vraagt het per check."""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8")).get("geweerd", {})


def stel_voor(rijen) -> tuple[dict[str, str], list[dict]]:
    """Bouw een voorstel uit (publisher, url)-paren.

    Geeft de regels die de grenzen halen, plus wat er met de hand beoordeeld
    moet worden. Beide zijn nodig: een lijst zonder zichtbare twijfelgevallen
    doet alsof hij compleet is.
    """
    import collections

    from doublecheck.evidence import _URLNAAM, _host, _uitgeversleutel

    per_host: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for uitgever, url in rijen:
        host = _host(url)
        if host and not _URLNAAM.match(uitgever.strip()):
            per_host[host][uitgever.strip()] += 1

    hosts: dict[str, str] = {}
    twijfel: list[dict] = []
    for host, telling in per_host.items():
        # Spellingvarianten van dezelfde naam eerst samennemen.
        per_sleutel: dict[str, collections.Counter] = collections.defaultdict(
            collections.Counter
        )
        for naam, aantal in telling.items():
            per_sleutel[_uitgeversleutel(naam)][naam] += aantal
        beste = max(per_sleutel.values(), key=lambda c: sum(c.values()))
        aantal = sum(beste.values())
        totaal = sum(telling.values())
        naam = beste.most_common(1)[0][0]
        if aantal >= MIN_CHECKS and aantal / totaal >= MIN_AANDEEL:
            hosts[host] = naam
        else:
            twijfel.append({
                "host": host, "voorstel": naam,
                "aandeel": round(aantal / totaal, 3), "checks": totaal,
            })
    return hosts, sorted(twijfel, key=lambda t: -t["checks"])


def voeg_voorstel_samen(hosts: dict[str, str], twijfel: list[dict], huidig: dict[str, str],
                        geweerd=frozenset(), bestaand=()) -> tuple[dict[str, str], list[dict]]:
    """Het register blijft wat er met de hand in staat; wat de meting nieuw
    vindt, wacht in `te_beoordelen` (SPECS E2.S6-AC4). Een host die bij het
    nalopen rommel bleek (`geweerd`), komt er niet meer in. Wat een mens bij
    een host opschreef (`bestaand`, zoals de reden), blijft staan; de meting
    ververst alleen haar eigen velden."""
    eerder = {t["host"]: t for t in bestaand}
    kandidaten = [{"host": h, "voorstel": n, "naam_zeker": True} for h, n in sorted(hosts.items())] + list(twijfel)
    uit = [{**eerder.get(t["host"], {}), **t} for t in kandidaten
           if t["host"] not in huidig and t["host"] not in geweerd]
    return dict(huidig), uit


def main() -> None:
    import argparse
    import sqlite3

    parser = argparse.ArgumentParser(
        description="Doublecheck: canonieke uitgever per host (#17.7)"
    )
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--voorstel", action="store_true",
                        help="genereer een nieuw voorstel en schrijf het weg")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rijen = conn.execute("SELECT publisher, url FROM factcheck").fetchall()
    conn.close()
    hosts, twijfel = stel_voor(rijen)

    huidig = load_hosts()
    geweerd = load_geweerd()
    bestaand = json.loads(UITGEVERS_PATH.read_text(encoding="utf-8")).get("te_beoordelen", []) \
        if UITGEVERS_PATH.exists() else []
    _, te_beoordelen = voeg_voorstel_samen(hosts, twijfel, huidig, set(geweerd), bestaand)
    al_bekend = {t["host"] for t in bestaand}
    nieuw = [t for t in te_beoordelen if t["host"] not in al_bekend]
    print(f"{len(rijen)} factchecks · register (toegelaten): {len(huidig)} hosts · geweerd: {len(geweerd)}"
          f" · te beoordelen: {len(te_beoordelen)}, waarvan nieuw: {len(nieuw)}")
    if nieuw:
        print("\nnieuw te beoordelen (niet vindbaar tot iemand ze toelaat, B28):")
        for t in nieuw[:15]:
            print(f"   {t.get('checks', '?'):>5} checks  {t['host'][:40]:<40} -> {t['voorstel'][:32]}")

    if args.voorstel:
        # Het register blijft wat er met de hand in staat (B28): het voorstel
        # vult alleen `te_beoordelen` aan.
        hosts, twijfel = huidig, te_beoordelen
        UITGEVERS_PATH.write_text(
            json.dumps({
                "_meta": META,
                "hosts": dict(sorted(hosts.items())),
                "te_beoordelen": twijfel,
                "geweerd": dict(sorted(geweerd.items())),
            }, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"\nweggeschreven naar {UITGEVERS_PATH}")


if __name__ == "__main__":
    main()
